import math
from datetime import datetime
from typing import List

import numpy as np
import pandas as pd

import qengine.helpers as jh
from qengine.models import ClosedTrade
from qengine.models.CFDExchange import CFDExchange
from qengine.core.instruments import instrument_registry
from qengine.store import store
from qengine.routes import router


def _get_annualization_periods() -> int:
    """Return the correct annualization period based on the trading exchange type."""
    trading_exchange = store.exchanges.trading_exchange
    if isinstance(trading_exchange, CFDExchange):
        return 252  # ~252 trading days for forex/commodity/stock
    return 365  # crypto: 24/7


def candles_info(candles_array: np.ndarray) -> dict:
    period = jh.date_diff_in_days(
        jh.timestamp_to_arrow(candles_array[0][0]),
        jh.timestamp_to_arrow(candles_array[-1][0])) + 1

    if period > 365:
        duration = f'{period} days ({round(period / 365, 2)} years)'
    elif period > 30:
        duration = f'{period} days ({round(period / 30, 2)} months)'
    else:
        duration = f'{period} days'

    # type of the exchange
    trading_exchange = store.exchanges.trading_exchange

    info = {
        'duration': duration,
        'starting_time': candles_array[0][0],
        'finishing_time': (candles_array[-1][0] + 60_000),
        'exchange_type': trading_exchange.type,
        'exchange': trading_exchange.name,
    }

    # if the exchange type is futures, also display leverage
    if trading_exchange.type == 'futures':
        info['leverage'] = trading_exchange.futures_leverage
        info['leverage_mode'] = trading_exchange.futures_leverage_mode
    elif isinstance(trading_exchange, CFDExchange):
        info['leverage'] = trading_exchange.default_leverage
        info['leverage_mode'] = 'fixed'

    return info


def routes(routes_arr: list) -> list:
    return [{
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'strategy_name': r.strategy_name,
            } for r in routes_arr]


def _prepare_returns(returns, rf=0.0, periods=252):
    """
    Helper function to prepare returns data by converting to pandas Series and
    adjusting for risk-free rate if provided.
    Drops NaN values (pct_change produces NaN in first row).
    """
    if isinstance(returns, pd.DataFrame):
        returns = returns[returns.columns[0]]

    returns = returns.dropna()

    if rf != 0:
        returns = returns - (rf / periods)

    return returns


def sharpe_ratio(returns, rf=0.0, periods=365, annualize=True, smart=False):
    """
    Calculates the sharpe ratio of access returns
    """
    returns = _prepare_returns(returns, rf, periods)
    divisor = returns.std(ddof=1)

    if smart:
        divisor = divisor * autocorr_penalty(returns)

    if divisor == 0:
        return pd.Series([0])

    res = returns.mean() / divisor

    if annualize:
        res = res * np.sqrt(1 if periods is None else periods)

    # Always convert to pandas Series
    return pd.Series([res])


def sortino_ratio(returns, rf=0, periods=365, annualize=True, smart=False):
    """
    Calculates the sortino ratio of access returns
    """
    returns = _prepare_returns(returns, rf, periods)

    downside = np.sqrt((returns[returns < 0] ** 2).sum() / len(returns))

    # Handle division by zero
    if downside == 0:
        res = np.inf if returns.mean() > 0 else -np.inf
    else:
        if smart:
            downside = downside * autocorr_penalty(returns)

        res = returns.mean() / downside

        if annualize:
            res = res * np.sqrt(1 if periods is None else periods)

    # Always convert to pandas Series
    return pd.Series([res])


def autocorr_penalty(returns):
    """
    Calculates the autocorrelation penalty for returns
    """
    num = len(returns)
    coef = np.abs(np.corrcoef(returns[:-1], returns[1:])[0, 1])
    corr = [((num - x) / num) * coef**x for x in range(1, num)]
    return np.sqrt(1 + 2 * np.sum(corr))


def calmar_ratio(returns):
    """
    Calculates the calmar ratio (CAGR% / MaxDD%)
    """
    # Get daily returns
    returns = _prepare_returns(returns)

    # Calculate CAGR exactly as in cagr() function
    first_value = 1
    last_value = (1 + returns).prod()
    days = (returns.index[-1] - returns.index[0]).days
    years = float(days) / 365

    if years == 0:
        return pd.Series([0.0])

    # Prevent overflow by limiting the ratio
    ratio = last_value / first_value
    # Clip ratio to prevent overflow in power calculation
    ratio = np.clip(ratio, 1e-10, 1e10)
    with np.errstate(over='ignore', under='ignore'):
        cagr_ratio = ratio ** (1 / years) - 1

    # Calculate Max Drawdown using cumulative returns
    cum_returns = (1 + returns).cumprod()
    # Prepend 1.0 as starting point (same fix as max_drawdown)
    cum_returns = pd.concat([pd.Series([1.0]), cum_returns]).reset_index(drop=True)
    rolling_max = cum_returns.expanding(min_periods=1).max()
    drawdown = cum_returns / rolling_max - 1
    max_dd = abs(drawdown.min())

    # Calculate Calmar
    result = cagr_ratio / max_dd if max_dd != 0 else 0

    # Always convert to pandas Series
    return pd.Series([result])


def max_drawdown(returns):
    """
    Calculates the maximum drawdown
    """
    returns = returns.dropna()
    if len(returns) < 1:
        return pd.Series([0.0])
    prices = (returns + 1).cumprod()
    # Prepend 1.0 as the starting point so the first return is measured
    # against the initial balance. Without this, a single-entry cumprod
    # divides by itself → ratio=1.0 → 0% drawdown even when losing money.
    prices = pd.concat([pd.Series([1.0]), prices]).reset_index(drop=True)
    result = (prices / prices.expanding(min_periods=0).max()).min() - 1

    # Always convert to pandas Series
    return pd.Series([result])


def calculate_max_underwater_period(daily_balance: list) -> int:
    """
    Calculate the maximum time it takes for balance to recover from a drawdown
    Args:
        daily_balance: List of daily balances
    Returns:
        Maximum underwater period in days
    """
    if len(daily_balance) < 2:
        return 0

    max_period = 0
    current_peak = daily_balance[0]
    peak_date_index = 0

    for i in range(1, len(daily_balance)):
        current_balance = daily_balance[i]

        # if we've recovered to or above the previous peak, update the peak
        if current_balance >= current_peak:
            current_peak = current_balance
            peak_date_index = i

        # if we're below the previous peak, calculate underwater period
        else:
            days_underwater = i - peak_date_index

            # update max period if this is the longest underwater period so far
            if days_underwater > max_period:
                max_period = days_underwater

    return max_period


def cagr(returns, rf=0.0, compounded=True, periods=365):
    """
    Calculates the communicative annualized growth return (CAGR%)
    """
    returns = _prepare_returns(returns, rf)

    # Get first and last values of cumulative returns
    first_value = 1
    last_value = (1 + returns).prod()

    # Calculate years exactly as quantstats does
    days = (returns.index[-1] - returns.index[0]).days
    years = float(days) / 365

    # Handle edge case
    if years == 0:
        return pd.Series([0.0])

    # Prevent overflow by limiting the ratio
    ratio = last_value / first_value
    # Clip ratio to prevent overflow in power calculation
    ratio = np.clip(ratio, 1e-10, 1e10)
    # Calculate CAGR using quantstats formula
    with np.errstate(over='ignore', under='ignore'):
        result = ratio ** (1 / years) - 1

    return pd.Series([result])


def omega_ratio(returns, rf=0.0, required_return=0.0, periods=365):
    """
    Determines the Omega ratio of a strategy
    """
    returns = _prepare_returns(returns, rf, periods)

    if periods == 1:
        return_threshold = required_return
    else:
        return_threshold = (1 + required_return) ** (1.0 / periods) - 1

    returns_less_thresh = returns - return_threshold
    numer = returns_less_thresh[returns_less_thresh > 0.0].sum()
    denom = -1.0 * returns_less_thresh[returns_less_thresh < 0.0].sum()

    result = numer / denom if denom > 0.0 else np.nan

    # Always convert to pandas Series
    return pd.Series([result])


def serenity_index(returns, rf=0):
    """
    Calculates the serenity index score
    """
    dd = to_drawdown_series(returns)
    std = float(returns.std())
    if std == 0:
        return pd.Series([0])
    pitfall = float(-conditional_value_at_risk(dd) / std)
    ui = float(ulcer_index(returns))
    denom = ui * pitfall
    if denom == 0:
        return pd.Series([0])
    result = (returns.sum() - rf) / denom

    # Always convert to pandas Series
    return pd.Series([result])


def ulcer_index(returns):
    """
    Calculates the ulcer index score (downside risk measurement)
    """
    dd = to_drawdown_series(returns)
    return np.sqrt(np.divide((dd**2).sum(), returns.shape[0] - 1))


def to_drawdown_series(returns):
    """
    Convert returns series to drawdown series
    """
    prices = (1 + returns).cumprod()
    dd = prices / np.maximum.accumulate(prices) - 1.0
    return dd.replace([np.inf, -np.inf, -0], 0)


def conditional_value_at_risk(returns, sigma=1, confidence=0.95):
    """
    Calculates the conditional daily value-at-risk (aka expected shortfall)
    """
    if len(returns) < 2:
        return 0

    returns = _prepare_returns(returns)
    # Sort returns from worst to best
    sorted_returns = np.sort(returns)
    # Find the index based on confidence level
    index = int((1 - confidence) * len(sorted_returns))

    # Handle empty slice warning
    if index == 0:
        return sorted_returns[0] if len(sorted_returns) > 0 else 0

    # Calculate CVaR as the mean of worst losses
    c_var = sorted_returns[:index].mean()
    return c_var if ~np.isnan(c_var) else 0


def _calculate_forex_metrics(trades_list: List[ClosedTrade]) -> dict:
    """Calculate forex-specific metrics: pips, swap costs, spread costs."""
    trading_exchange = store.exchanges.trading_exchange
    if not isinstance(trading_exchange, CFDExchange):
        return {}

    total_pips = 0.0
    for t in trades_list:
        pip_size = instrument_registry.get_pip_size(t.symbol)
        if pip_size > 0:
            price_diff = t.exit_price - t.entry_price
            if t.type == 'short':
                price_diff *= -1
            total_pips += price_diff / pip_size

    avg_pips = total_pips / len(trades_list) if trades_list else 0.0
    total_swap_cost = trading_exchange._overnight_charges
    total_spread_cost = trading_exchange._total_spread_cost

    return {
        'total_pips': round(total_pips, 1),
        'avg_pips_per_trade': round(avg_pips, 1),
        'total_swap_cost': round(total_swap_cost, 2),
        'total_spread_cost': round(total_spread_cost, 2),
    }


def _parse_sessions(trades_list: List[ClosedTrade]) -> list:
    """Extract session structures from a list of ClosedTrade objects.

    Returns list of dicts with keys:
        pnl, legs, max_level, exit_reason, holding_seconds, leg_levels, leg_holdings
    """
    sessions_map = {}   # session_num -> accumulated data
    session_order = []  # preserve insertion order for stable output

    for t in trades_list:
        meta = getattr(t, 'meta', {}) or {}
        session_num = meta.get('session')
        if session_num is None:
            session_num = f'standalone-{id(t)}'

        if session_num not in sessions_map:
            sessions_map[session_num] = {
                'pnl': 0.0, 'legs': 0, 'max_level': 0,
                'exit_reason': None, 'leg_levels': [], 'leg_holdings': [],
            }
            session_order.append(session_num)

        s = sessions_map[session_num]
        s['pnl'] += t.pnl
        s['legs'] += 1

        level = meta.get('level', 0)
        if isinstance(level, (int, float)):
            level = int(level)
            if level > s['max_level']:
                s['max_level'] = level
            s['leg_levels'].append(level)
        else:
            s['leg_levels'].append(0)

        hp = getattr(t, 'holding_period', None)
        s['leg_holdings'].append(hp if hp is not None else 0)

        reason = meta.get('session_exit_reason', meta.get('exit_reason'))
        if reason:
            s['exit_reason'] = reason

    result = []
    for sn in session_order:
        s = sessions_map[sn]
        result.append({
            'pnl': s['pnl'],
            'legs': s['legs'],
            'max_level': s['max_level'],
            'exit_reason': s['exit_reason'],
            'holding_seconds': sum(s['leg_holdings']),
            'leg_levels': s['leg_levels'],
            'leg_holdings': s['leg_holdings'],
        })
    return result


def _calculate_hedge_session_metrics(trades_list: List[ClosedTrade]) -> dict:
    """Calculate hedge session-level metrics from trade metadata."""
    sessions = _parse_sessions(trades_list)
    if not sessions:
        return {}

    total_sessions = len(sessions)
    session_pnls = [s['pnl'] for s in sessions]
    session_legs = [s['legs'] for s in sessions]

    winning_sessions = [p for p in session_pnls if p > 0]
    losing_sessions = [p for p in session_pnls if p <= 0]

    session_win_rate = len(winning_sessions) / total_sessions if total_sessions > 0 else 0
    avg_session_win = np.mean(winning_sessions) if winning_sessions else 0.0
    avg_session_loss = np.mean(losing_sessions) if losing_sessions else 0.0
    avg_legs = np.mean(session_legs)
    max_legs = max(session_legs)
    sessions_1_leg = sum(1 for l in session_legs if l == 1)

    # Expected value per session
    ev_per_session = np.mean(session_pnls)

    # Consecutive wins/losses at session level
    session_pnl_arr = np.array(session_pnls)
    wins = (session_pnl_arr > 0).astype(int)
    max_consec_wins = _max_consecutive(wins, 1)
    max_consec_losses = _max_consecutive(wins, 0)

    # Bust metrics — sessions ending in bust/max_levels/margin_call
    bust_outcomes = {'bust', 'max_levels', 'margin_call', 'liquidation'}
    bust_pnls = [s['pnl'] for s in sessions if s['exit_reason'] in bust_outcomes]
    total_busts = len(bust_pnls)
    worst_bust_pnl = round(min(bust_pnls), 2) if bust_pnls else 0.0

    # Loss sessions — any session that ended with PnL <= 0 (includes busts, aborts, etc.)
    total_losing_sessions = len(losing_sessions)

    # Depth analysis — how many sessions reached each max level, and win/loss at each
    depth_stats = {}
    for s in sessions:
        depth = s['max_level']
        if depth not in depth_stats:
            depth_stats[depth] = {'count': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0}
        depth_stats[depth]['count'] += 1
        depth_stats[depth]['pnl'] += s['pnl']
        if s['pnl'] > 0:
            depth_stats[depth]['wins'] += 1
        else:
            depth_stats[depth]['losses'] += 1

    # Convert to sorted list for frontend
    depth_breakdown = []
    for depth in sorted(depth_stats.keys()):
        d = depth_stats[depth]
        depth_breakdown.append({
            'depth': depth,
            'count': d['count'],
            'wins': d['wins'],
            'losses': d['losses'],
            'pnl': round(d['pnl'], 2),
        })

    return {
        'total_sessions': total_sessions,
        'session_win_rate': round(session_win_rate, 4),
        'avg_session_win': round(avg_session_win, 2),
        'avg_session_loss': round(avg_session_loss, 2),
        'ev_per_session': round(ev_per_session, 2),
        'avg_legs_per_session': round(avg_legs, 2),
        'max_legs_in_session': max_legs,
        'sessions_with_1_leg': sessions_1_leg,
        'max_consecutive_session_wins': max_consec_wins,
        'max_consecutive_session_losses': max_consec_losses,
        'total_busts': total_busts,
        'worst_bust_pnl': worst_bust_pnl,
        'total_losing_sessions': total_losing_sessions,
        'depth_breakdown': depth_breakdown,
    }


def _calculate_martingale_metrics(sessions: list, starting_balance: float,
                                  total_fees: float = 0.0, total_spread: float = 0.0,
                                  total_swap: float = 0.0, gross_profit: float = 0.0) -> dict:
    """Calculate martingale/surefire-specific metrics from parsed sessions.

    Args:
        sessions: list of session dicts (from _parse_sessions or test helpers) with keys:
            pnl, legs, max_level, exit_reason, holding_seconds, leg_levels, leg_holdings
        starting_balance: account balance before first session
        total_fees: total trading fees across all trades
        total_spread: total spread cost across all trades
        total_swap: total overnight swap charges
        gross_profit: sum of winning trade PnLs (before costs)
    """
    if not sessions:
        return {}

    total_sessions = len(sessions)
    session_pnls = [s['pnl'] for s in sessions]

    # --- Session Performance ---
    winning_pnls = [p for p in session_pnls if p > 0]
    losing_pnls = [p for p in session_pnls if p <= 0]

    sum_wins = sum(winning_pnls)
    sum_losses_abs = abs(sum(losing_pnls))

    if sum_losses_abs == 0:
        session_profit_factor = float('inf') if sum_wins > 0 else 0.0
    else:
        session_profit_factor = sum_wins / sum_losses_abs

    median_session_pnl = float(np.median(session_pnls))

    # --- Survival & Ruin ---
    bust_outcomes = {'bust', 'max_levels', 'margin_call', 'liquidation'}
    bust_sessions = [s for s in sessions if s['exit_reason'] in bust_outcomes]
    bust_count = len(bust_sessions)
    bust_rate = bust_count / total_sessions

    bust_pnls = [s['pnl'] for s in bust_sessions]
    avg_bust_loss = float(np.mean(bust_pnls)) if bust_pnls else 0.0

    if len(bust_pnls) >= 2:
        bust_severity_std = float(np.std(bust_pnls, ddof=1))
    else:
        bust_severity_std = 0.0

    avg_session_win = float(np.mean(winning_pnls)) if winning_pnls else 0.0
    wins_to_recover = abs(avg_bust_loss) / avg_session_win if avg_session_win > 0 and bust_pnls else 0.0

    # Geometric growth rate — track running balance
    running_balance = starting_balance
    log_returns = []
    for s in sessions:
        if running_balance > 0:
            ratio = 1 + s['pnl'] / running_balance
            lr = math.log(ratio) if ratio > 0 else float('-inf')
        else:
            lr = float('-inf')
        log_returns.append(lr)
        running_balance += s['pnl']

    geometric_growth_rate = float(np.mean(log_returns)) if log_returns else 0.0

    # Survival
    if bust_rate == 0:
        survival_100 = 1.0
        survival_500 = 1.0
        survival_half_life = float('inf')
    elif bust_rate >= 1.0:
        survival_100 = 0.0
        survival_500 = 0.0
        survival_half_life = 0.0
    else:
        survival_100 = (1 - bust_rate) ** 100
        survival_500 = (1 - bust_rate) ** 500
        survival_half_life = math.log(0.5) / math.log(1 - bust_rate)

    # --- Structural Diagnostics ---

    # Level transitions
    level_data = {}  # level -> {entries, wins, escalations}
    for s in sessions:
        max_lv = s['max_level']
        for lv in range(max_lv + 1):
            if lv not in level_data:
                level_data[lv] = {'entries': 0, 'wins': 0, 'escalations': 0}
            level_data[lv]['entries'] += 1
            if lv < max_lv:
                level_data[lv]['escalations'] += 1
            elif lv == max_lv and s['pnl'] > 0:
                level_data[lv]['wins'] += 1

    level_transitions = []
    for lv in sorted(level_data.keys()):
        d = level_data[lv]
        entries = d['entries']
        level_transitions.append({
            'level': lv,
            'entries': entries,
            'wins': d['wins'],
            'escalations': d['escalations'],
            'p_win': d['wins'] / entries if entries > 0 else 0.0,
            'p_escalate': d['escalations'] / entries if entries > 0 else 0.0,
        })

    # EV by depth (keyed by max_level)
    ev_by_depth = {}
    for s in sessions:
        ml = s['max_level']
        if ml not in ev_by_depth:
            ev_by_depth[ml] = {'count': 0, 'total_pnl': 0.0, 'wins': 0}
        ev_by_depth[ml]['count'] += 1
        ev_by_depth[ml]['total_pnl'] += s['pnl']
        if s['pnl'] > 0:
            ev_by_depth[ml]['wins'] += 1

    for ml in ev_by_depth:
        d = ev_by_depth[ml]
        d['avg_pnl'] = d['total_pnl'] / d['count']
        d['win_rate'] = d['wins'] / d['count']

    # Time at depth
    time_at_depth = {}
    for s in sessions:
        for lv, holding in zip(s['leg_levels'], s['leg_holdings']):
            time_at_depth[lv] = time_at_depth.get(lv, 0.0) + holding

    # L0 win rate
    l0_wins = sum(1 for s in sessions if s['max_level'] == 0 and s['pnl'] > 0)
    l0_win_rate = l0_wins / total_sessions

    # --- Capital & Costs ---
    if gross_profit > 0:
        cost_drag_pct = (total_fees + total_spread + total_swap) / gross_profit * 100
    else:
        cost_drag_pct = 0.0

    return {
        # Session Performance
        'session_profit_factor': session_profit_factor,
        'median_session_pnl': median_session_pnl,
        # Survival & Ruin
        'bust_rate': bust_rate,
        'bust_count': bust_count,
        'wins_to_recover': wins_to_recover,
        'geometric_growth_rate': geometric_growth_rate,
        'survival_100': survival_100,
        'survival_500': survival_500,
        'survival_half_life': survival_half_life,
        'avg_bust_loss': avg_bust_loss,
        'bust_severity_std': bust_severity_std,
        # Structural Diagnostics
        'level_transitions': level_transitions,
        'ev_by_depth': ev_by_depth,
        'time_at_depth': time_at_depth,
        'l0_win_rate': l0_win_rate,
        # Capital & Costs
        'cost_drag_pct': cost_drag_pct,
    }


def _max_consecutive(arr: np.ndarray, value: int) -> int:
    """Count max consecutive occurrences of `value` in array."""
    max_count = 0
    count = 0
    for v in arr:
        if v == value:
            count += 1
            max_count = max(max_count, count)
        else:
            count = 0
    return max_count


def trades(trades_list: List[ClosedTrade], daily_balance: list, final: bool = True) -> dict:
    starting_balance = 0
    current_balance = 0

    for e in store.exchanges.storage:
        starting_balance += store.exchanges.storage[e].starting_assets[jh.app_currency()]
        current_balance += store.exchanges.storage[e].assets[jh.app_currency()]

    if not trades_list:
        return {'total': 0, 'win_rate': 0, 'net_profit_percentage': 0}

    df = pd.DataFrame.from_records([t.to_dict for t in trades_list])

    total_completed = len(df)
    winning_trades = df.loc[df['PNL'] > 0]
    total_winning_trades = len(winning_trades)
    losing_trades = df.loc[df['PNL'] < 0]
    total_losing_trades = len(losing_trades)

    arr = df['PNL'].to_numpy()
    pos = np.clip(arr, 0, 1).astype(bool).cumsum()
    neg = np.clip(arr, -1, 0).astype(bool).cumsum()
    current_streak = np.where(arr >= 0, pos - np.maximum.accumulate(np.where(arr <= 0, pos, 0)),
                              -neg + np.maximum.accumulate(np.where(arr >= 0, neg, 0)))

    s_min = current_streak.min()
    losing_streak = 0 if s_min > 0 else abs(s_min)

    s_max = current_streak.max()
    winning_streak = max(s_max, 0)

    largest_losing_trade = 0 if total_losing_trades == 0 else losing_trades['PNL'].min()
    largest_winning_trade = 0 if total_winning_trades == 0 else winning_trades['PNL'].max()
    if len(winning_trades) == 0:
        win_rate = 0
    else:
        # Use total trades as denominator (not just wins+losses) so breakeven trades
        # don't inflate win rate
        win_rate = len(winning_trades) / total_completed

    # calculate the long and short win rate (denominator = all trades of that type)
    winning_longs = df.loc[(df['type'] == 'long') & (df['PNL'] > 0)]
    total_longs = len(df.loc[df['type'] == 'long'])
    win_rate_longs = len(winning_longs) / total_longs if total_longs > 0 else 0

    winning_shorts = df.loc[(df['type'] == 'short') & (df['PNL'] > 0)]
    total_shorts = len(df.loc[df['type'] == 'short'])
    win_rate_shorts = len(winning_shorts) / total_shorts if total_shorts > 0 else 0

    longs_count = len(df.loc[df['type'] == 'long'])
    shorts_count = len(df.loc[df['type'] == 'short'])
    longs_percentage = longs_count / (longs_count + shorts_count) * 100 if (longs_count + shorts_count) > 0 else 0
    shorts_percentage = 100 - longs_percentage
    fee = df['fee'].sum()
    gross_pnl = df['PNL'].sum()
    # True net profit = finishing balance - starting balance (includes spreads, swaps, fees)
    net_profit = current_balance - starting_balance
    net_profit_percentage = (net_profit / starting_balance) * 100 if starting_balance > 0 else 0
    average_win = winning_trades['PNL'].mean()
    average_loss = abs(losing_trades['PNL'].mean())
    ratio_avg_win_loss = average_win / average_loss if average_loss != 0 else float('inf')
    expectancy = (0 if np.isnan(average_win) else average_win) * win_rate - (
        0 if np.isnan(average_loss) else average_loss) * (1 - win_rate)
    expectancy = expectancy
    expectancy_percentage = (expectancy / starting_balance) * 100
    expected_net_profit_every_100_trades = expectancy_percentage * 100
    average_holding_period = df['holding_period'].mean()
    average_winning_holding_period = winning_trades['holding_period'].mean()
    average_losing_holding_period = losing_trades['holding_period'].mean()
    gross_profit = winning_trades['PNL'].sum()
    gross_loss = losing_trades['PNL'].sum()

    start_date = datetime.fromtimestamp(store.app.starting_time / 1000)
    date_index = pd.date_range(start=start_date, periods=len(daily_balance))

    daily_return = pd.DataFrame(daily_balance, index=date_index).pct_change(1)

    total_open_trades = store.app.total_open_trades
    open_pl = store.app.total_open_pl

    # Helper function to safely convert values
    def safe_convert(value, convert_type=float):
        try:
            if isinstance(value, pd.Series):
                value = value.iloc[0]
            if np.isnan(value):
                return np.nan
            return convert_type(value)
        except BaseException:
            return np.nan

    # Use asset-class-aware annualization periods
    periods = _get_annualization_periods()

    max_dd = np.nan if len(daily_return) < 2 else max_drawdown(daily_return).iloc[0] * 100
    max_underwater_period = np.nan if len(daily_balance) < 2 else calculate_max_underwater_period(daily_balance)
    annual_return = np.nan if len(daily_return) < 2 else cagr(daily_return, periods=periods).iloc[0] * 100
    sharpe = np.nan if len(daily_return) < 2 else sharpe_ratio(daily_return, periods=periods).iloc[0]
    calmar = np.nan if len(daily_return) < 2 else calmar_ratio(daily_return).iloc[0]
    sortino = np.nan if len(daily_return) < 2 else sortino_ratio(daily_return, periods=periods).iloc[0]
    omega = np.nan if len(daily_return) < 2 else omega_ratio(daily_return, periods=periods).iloc[0]
    serenity = np.nan if len(daily_return) < 2 else serenity_index(daily_return).iloc[0]

    # Forex-specific metrics
    forex_metrics = _calculate_forex_metrics(trades_list)

    # Profit factor
    profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')

    # Kelly Criterion: W - (1-W)/R where W=win_rate, R=avg_win/avg_loss ratio
    if ratio_avg_win_loss != 0 and not np.isinf(ratio_avg_win_loss):
        kelly = win_rate - ((1 - win_rate) / ratio_avg_win_loss)
    else:
        kelly = 0.0

    # VaR and CVaR on daily returns
    if len(daily_return) >= 2:
        dr_clean = daily_return.dropna().iloc[:, 0] if isinstance(daily_return, pd.DataFrame) else daily_return.dropna()
        sorted_returns = np.sort(dr_clean.values)
        n = len(sorted_returns)

        # VaR: loss at given percentile (expressed as currency amount)
        var_95_pct = sorted_returns[int(0.05 * n)] if n > 20 else np.nan
        var_99_pct = sorted_returns[int(0.01 * n)] if n > 100 else np.nan
        var_95 = var_95_pct * starting_balance if not np.isnan(var_95_pct) else np.nan
        var_99 = var_99_pct * starting_balance if not np.isnan(var_99_pct) else np.nan

        # CVaR (Expected Shortfall): mean of losses beyond VaR threshold
        idx_95 = int(0.05 * n)
        idx_99 = int(0.01 * n)
        cvar_95 = sorted_returns[:idx_95].mean() * starting_balance if idx_95 > 0 else np.nan
        cvar_99 = sorted_returns[:idx_99].mean() * starting_balance if idx_99 > 0 else np.nan
    else:
        var_95, var_99, cvar_95, cvar_99 = np.nan, np.nan, np.nan, np.nan

    # Peak/risk metrics from simulation tracking
    worst_floating_pnl = store.app.worst_floating_pnl
    peak_margin_used = store.app.peak_margin_used
    peak_equity_usage_pct = store.app.peak_equity_usage_pct
    margin_closeouts = store.app.total_liquidations
    account_blown = bool(current_balance <= 0 or (starting_balance > 0 and current_balance / starting_balance < 0.02))

    # Hedge session metrics (only if trades have session metadata)
    has_sessions = any(hasattr(t, 'meta') and getattr(t, 'meta', {}).get('session') is not None for t in trades_list)
    hedge_metrics = _calculate_hedge_session_metrics(trades_list) if has_sessions else {}

    return {
        'total': safe_convert(total_completed, int),
        'total_winning_trades': safe_convert(total_winning_trades, int),
        'total_losing_trades': safe_convert(total_losing_trades, int),
        'starting_balance': safe_convert(starting_balance),
        'finishing_balance': safe_convert(current_balance),
        'win_rate': safe_convert(win_rate),
        'win_rate_longs': safe_convert(win_rate_longs),
        'win_rate_shorts': safe_convert(win_rate_shorts),
        'ratio_avg_win_loss': safe_convert(ratio_avg_win_loss),
        'longs_count': safe_convert(longs_count, int),
        'longs_percentage': safe_convert(longs_percentage),
        'shorts_percentage': safe_convert(shorts_percentage),
        'shorts_count': safe_convert(shorts_count, int),
        'fee': safe_convert(fee),
        'gross_pnl': safe_convert(gross_pnl),
        'net_profit': safe_convert(net_profit),
        'net_profit_percentage': safe_convert(net_profit_percentage),
        'average_win': safe_convert(average_win),
        'average_loss': safe_convert(average_loss),
        'expectancy': safe_convert(expectancy),
        'expectancy_percentage': safe_convert(expectancy_percentage),
        'expected_net_profit_every_100_trades': safe_convert(expected_net_profit_every_100_trades),
        'average_holding_period': safe_convert(average_holding_period),
        'average_winning_holding_period': safe_convert(average_winning_holding_period),
        'average_losing_holding_period': safe_convert(average_losing_holding_period),
        'gross_profit': safe_convert(gross_profit),
        'gross_loss': safe_convert(gross_loss),
        'max_drawdown': safe_convert(max_dd),
        'max_underwater_period': safe_convert(max_underwater_period),
        'annual_return': safe_convert(annual_return),
        'sharpe_ratio': safe_convert(sharpe),
        'calmar_ratio': safe_convert(calmar),
        'sortino_ratio': safe_convert(sortino),
        'omega_ratio': safe_convert(omega),
        'serenity_index': safe_convert(serenity),
        'total_open_trades': safe_convert(total_open_trades, int),
        'open_pl': safe_convert(open_pl),
        'winning_streak': safe_convert(winning_streak, int),
        'losing_streak': safe_convert(losing_streak, int),
        'largest_losing_trade': safe_convert(largest_losing_trade),
        'largest_winning_trade': safe_convert(largest_winning_trade),
        'current_streak': safe_convert(current_streak[-1], int),
        # New hedging/risk metrics
        'profit_factor': safe_convert(profit_factor),
        'kelly_criterion': safe_convert(kelly),
        'var_95': safe_convert(var_95),
        'var_99': safe_convert(var_99),
        'cvar_95': safe_convert(cvar_95),
        'cvar_99': safe_convert(cvar_99),
        'worst_floating_pnl': safe_convert(worst_floating_pnl),
        'peak_margin_used': safe_convert(peak_margin_used),
        'peak_equity_usage_pct': safe_convert(peak_equity_usage_pct),
        'margin_closeouts': safe_convert(margin_closeouts, int),
        'account_blown': account_blown,
        **forex_metrics,
        **hedge_metrics,
    }


def hyperparameters(routes_arr: list) -> list:
    if routes_arr[0].strategy.hp is None:
        return []
    # only for the first route
    hp = []

    # add DNA
    dna_value = routes_arr[0].strategy.dna()
    if dna_value is not None and len(dna_value) > 16:
        formatted_dna = f"{dna_value[:5]}*****{dna_value[-5:]}"
        hp.append(['DNA', formatted_dna])
    else:
        hp.append(['DNA', dna_value])

    # add hyperparameters
    for key in routes_arr[0].strategy.hp:
        hp.append([
            key, routes_arr[0].strategy.hp[key]
        ])
    return hp
