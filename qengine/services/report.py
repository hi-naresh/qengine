import warnings
from typing import List, Any, Union, Dict
import pandas as pd
import qengine.helpers as jh
from qengine.config import config
from qengine.routes import router
from qengine.services import metrics as stats
from qengine.store import store
from qengine.models import Position
from qengine.services import candle_service


# silent (pandas) warnings
warnings.filterwarnings("ignore")


def positions() -> list:
    arr = []

    for r in router.routes:
        if r.strategy is None:
            continue
        p: Position = r.strategy.position
        arr.append({
            'currency': jh.app_currency(),
            'type': p.type,
            'strategy_name': p.strategy.name,
            'symbol': p.symbol,
            'leverage': p.leverage,
            'opened_at': p.opened_at,
            'qty': p.qty,
            'value': p.value,
            'entry': None if p.is_close else p.entry_price,
            'current_price': p.current_price,
            'liquidation_price': p.liquidation_price,
            'pnl': p.pnl,
            'pnl_perc': p.pnl_percentage
        })

    return arr


def candles() -> dict:
    candles_dict = {}
    candle_keys = []

    # add routes
    for e in router.routes:
        if e.strategy is None:
            return {}

        candle_keys.append({
            'exchange': e.exchange,
            'symbol': e.symbol,
            'timeframe': e.timeframe
        })

    for k in candle_keys:
        try:
            c = candle_service.get_current_candle(k['exchange'], k['symbol'], k['timeframe'])
            key = jh.key(k['exchange'], k['symbol'], k['timeframe'])
            candles_dict[key] = {
                'time': int(c[0] / 1000),
                'open': c[1],
                'close': c[2],
                'high': c[3],
                'low': c[4],
                'volume': c[5],
            }
        except IndexError:
            return {}
        except Exception:
            raise

    return candles_dict


def livetrade():
    starting_balance = 0
    current_balance = 0
    exchange_name = ''
    leverage = 1
    leverage_type = 'spot'
    available_margin = 0
    for e in store.exchanges.storage:
        starting_balance = round(store.exchanges.storage[e].started_balance, 2)
        current_balance = round(store.exchanges.storage[e].wallet_balance, 2)
        exchange_name = e
        if store.exchanges.storage[e].type == 'futures':
            leverage = store.exchanges.storage[e].futures_leverage
            leverage_type = store.exchanges.storage[e].futures_leverage_mode
            available_margin = round(store.exchanges.storage[e].available_margin, 2)
        # there's only one exchange, so we can break
        break

    # short trades summary
    if len(store.closed_trades.trades):
        df = pd.DataFrame.from_records([t.to_dict for t in store.closed_trades.trades])
        total = len(df)
        winning_trades = len(df.loc[df['PNL'] > 0])
        losing_trades = len(df.loc[df['PNL'] < 0])
        pnl = round(df['PNL'].sum(), 2)
        pnl_perc = round((pnl / starting_balance) * 100, 2)
    else:
        pnl, pnl_perc, total, winning_trades, losing_trades = 0, 0, 0, 0, 0

    routes = [
        {
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'strategy': r.strategy_name
        } for r in router.routes
    ]

    return {
        'session_id': store.app.session_id,
        'started_at': str(store.app.starting_time),
        'current_time': str(jh.now_to_timestamp()),
        'started_balance': str(starting_balance),
        'current_balance': str(current_balance),
        'debug_mode': str(config['app']['debug_mode']),
        'paper_mode': str(jh.is_paper_trading()),
        'count_error_logs': str(len(store.logs.errors)),
        'count_info_logs': str(len(store.logs.info)),
        'count_active_orders': str(store.orders.count_all_active_orders()),
        'open_positions': str(store.positions.count_open_positions()),
        'pnl': str(pnl),
        'pnl_perc': str(pnl_perc),
        'count_trades': str(total),
        'count_winning_trades': str(winning_trades),
        'count_losing_trades': str(losing_trades),
        'routes': routes,
        'exchange': exchange_name,
        'leverage': leverage,
        "leverage_type": leverage_type,
        'available_margin': available_margin
    }


def portfolio_metrics() -> Union[dict, None]:
    if store.closed_trades.count == 0:
        # Return minimal metrics so frontend knows backtest completed but had no trades
        return {
            'total': 0,
            'total_completed_trades': 0,
            'total_winning_trades': 0,
            'total_losing_trades': 0,
            'starting_balance': store.app.daily_balance[0] if store.app.daily_balance else 0,
            'finishing_balance': store.app.daily_balance[-1] if store.app.daily_balance else 0,
            'net_profit': 0,
            'net_profit_percentage': 0,
            'win_rate': 0,
            'total_open_trades': store.app.total_open_trades,
            'open_pl': store.app.total_open_pl,
        }

    return stats.trades(store.closed_trades.trades, store.app.daily_balance)


def trades() -> List[dict]:
    if store.closed_trades.count == 0:
        return []
    return [t.to_dict_with_orders for t in store.closed_trades.trades]


def hedge_sessions() -> List[dict]:
    """Group trades that have session metadata into hedge sessions.
    Returns a list of session summaries, each containing its trades.
    Trades without meta.session are returned as standalone sessions.
    """
    trades_list = store.closed_trades.trades
    if not trades_list:
        return []

    sessions_map = {}  # session_number -> { trades, pnl, ... }
    standalone = []

    for t in trades_list:
        meta = getattr(t, 'meta', {})
        session_num = meta.get('session')
        if session_num is None:
            standalone.append(t)
            continue

        if session_num not in sessions_map:
            sessions_map[session_num] = {
                'session': session_num,
                'trades': [],
                'total_pnl': 0,
                'total_fee': 0,
                'opened_at': t.opened_at,
                'closed_at': None,
                'outcome': None,
                'levels': 0,
            }

        s = sessions_map[session_num]
        td = t.to_dict_with_orders
        td['meta'] = meta
        s['trades'].append(td)
        s['total_pnl'] += t.pnl
        s['total_fee'] += t.fee
        s['levels'] = max(s['levels'], meta.get('level', 0))
        s['closed_at'] = t.closed_at
        s['outcome'] = meta.get('session_exit_reason', meta.get('exit_reason', s['outcome']))

    # Merge per-session stats tracked during simulation
    session_stats = store.app.session_stats

    result = []
    for num in sorted(sessions_map.keys()):
        s = sessions_map[num]
        s['total_pnl'] = round(s['total_pnl'], 6)
        s['total_fee'] = round(s['total_fee'], 6)
        s['trade_count'] = len(s['trades'])
        # Merge candle-level session stats
        ss = session_stats.get(num, {})
        s['max_float'] = ss.get('max_float', 0.0)
        s['min_float'] = ss.get('min_float', 0.0)
        s['peak_margin'] = ss.get('peak_margin', 0.0)
        s['peak_equity_pct'] = ss.get('peak_equity_pct', 0.0)
        s['margin_block_leg'] = ss.get('margin_block_leg')
        result.append(s)

    # standalone trades as single-trade sessions
    for i, t in enumerate(standalone):
        td = t.to_dict_with_orders
        meta = getattr(t, 'meta', {})
        outcome = meta.get('exit_reason', 'standalone')
        result.append({
            'session': f'standalone-{i + 1}',
            'trades': [td],
            'total_pnl': round(t.pnl, 6),
            'total_fee': round(t.fee, 6),
            'opened_at': t.opened_at,
            'closed_at': t.closed_at,
            'outcome': outcome,
            'levels': 0,
            'trade_count': 1,
            'max_float': 0.0,
            'min_float': 0.0,
            'peak_margin': 0.0,
            'peak_equity_pct': 0.0,
            'margin_block_leg': None,
        })

    return result


def info() -> List[List[Union[str, Any]]]:
    return [
        [
            jh.timestamp_to_time(w['timestamp'])[11:19],
            f"{w['message'][:70]}.."
            if len(w['message']) > 70
            else w['message'],
        ]
        for w in store.logs.info[::-1][0:5]
    ]


def watch_list() -> Dict[str, List[List[Union[str, str]]]]:
    """
    Returns a dictionary of watch lists for all routes keyed by route key
    (exchange-symbol-timeframe). This allows frontend to display watch list
    for the currently selected route without server-side knowledge of the
    selection.
    """
    results: Dict[str, List[List[Union[str, str]]]] = {}

    for r in router.routes:
        strategy = r.strategy

        # skip if strategy object is not initialized yet
        if strategy is None or not store.candles.are_all_initiated:
            results[jh.key(r.exchange, r.symbol, r.timeframe)] = []
            continue

        try:
            watch_list_array = strategy.watch_list()
        except Exception:
            import traceback
            watch_list_array = [
                ('', "The watch list is not available because an error occurred while getting it. Please check your strategy code's watch_list() method."),
                ('', f'ERROR: ```{traceback.format_exc()}```')
            ]

        # loop through the watch list and convert each item into a string
        for index, value in enumerate(watch_list_array):
            if not isinstance(value, tuple) or len(value) != 2:
                raise ValueError("watch_list() must return a list of tuples with 2 values in each. Example: [(key1, value1), (key2, value2)]")

            watch_list_array[index] = (str(value[0]), str(value[1]))

        results[jh.key(r.exchange, r.symbol, r.timeframe)] = watch_list_array if len(watch_list_array) else []

    return results


def errors() -> List[List[Union[str, Any]]]:
    return [
        [
            jh.timestamp_to_time(w['timestamp'])[11:19],
            f"{w['message'][:70]}.."
            if len(w['message']) > 70
            else w['message'],
        ]
        for w in store.logs.errors[::-1][0:5]
    ]


def orders() -> List[dict]:
    route_orders = []

    for r in router.routes:
        r_orders = store.orders.get_orders(r.exchange, r.symbol)
        for o in r_orders:
            o.trade_id = str(o.trade_id) if o.trade_id else None
            o.id = str(o.id) if o.id else None
            route_orders.append(o.to_dict)

    return route_orders
