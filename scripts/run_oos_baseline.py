"""Run the BASELINE Martingale strategy (default 'original' preset, no pipeline)
on real OANDA EUR-USD data via the actual qengine backtest engine over the
same OOS period 2025-01-01 to 2026-04-20 — for direct comparison with the
pipeline run.

Usage:
    python3 scripts/run_oos_baseline.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _to_ms(s: str) -> int:
    return int((datetime.strptime(s, '%Y-%m-%d') - datetime(1970, 1, 1)).total_seconds() * 1000)


def main():
    start_date = '2025-01-01'
    end_date = '2026-04-20'
    exchange = 'OANDA'
    symbol = 'EUR-USD'
    timeframe = '5m'
    strategy = 'Martingale'
    starting_balance = 10_000

    print('=' * 72)
    print(f'BASELINE Martingale OOS Backtest (default "original" preset, no pipeline)')
    print(f'  Period:   {start_date} → {end_date}')
    print(f'  Route:    {exchange} {symbol} {timeframe} / {strategy}')
    print(f'  Balance:  ${starting_balance:,}')
    print(f'  Preset:   "original" (signal_mode=none, long_only, geom 2.0, max_levels=6,')
    print(f'            hedge 10p, TP 20p)')
    print('=' * 72)

    print('\n[1/3] Loading 1m candles from database...')
    from qengine.research.candles import get_candles
    start_ts = _to_ms(start_date)
    end_ts = _to_ms(end_date) + 86_400_000 - 60_000
    _warmup, candles = get_candles(
        exchange=exchange, symbol=symbol, timeframe='1m',
        start_date_timestamp=start_ts, finish_date_timestamp=end_ts,
    )
    print(f'  Loaded {len(candles):,} 1m candles')

    print('\n[2/3] Running backtest (no pipeline, preset=original)...')
    from qengine.research.backtest import backtest
    import qengine.helpers as jh

    config = {
        'starting_balance': starting_balance,
        'fee': 0.0,
        'type': 'cfd',
        'exchange': exchange,
        'warm_up_candles': 210,
    }
    routes = [{
        'exchange': exchange,
        'strategy': strategy,
        'symbol': symbol,
        'timeframe': timeframe,
    }]
    key = jh.key(exchange, symbol)
    candles_dict = {key: {'exchange': exchange, 'symbol': symbol, 'candles': candles}}

    # Pass the 'original' preset explicitly via hyperparameters so the strategy
    # doesn't fall back to whatever hp defaults may have drifted.
    hp = {
        'preset': 'original',
        'signal_mode': 'none',
        'direction_bias': 'long_only',
        'sizing_curve': 'geometric',
        'sizing_factor': 2.0,
        'max_levels': 6,
        'hedge_mode': 'fixed_pips',
        'hedge_value': 10.0,
        'tp_mode': 'fixed_pips',
        'tp_value': 20.0,
        'base_size_mode': 'pct_equity',
        'base_size_value': 1.0,
    }

    t0 = datetime.utcnow()
    result = backtest(
        config=config,
        routes=routes,
        data_routes=[],
        candles=candles_dict,
        hyperparameters=hp,
        generate_equity_curve=True,
        cost_model=True,
    )
    elapsed = (datetime.utcnow() - t0).total_seconds()
    print(f'  Backtest completed in {elapsed:.1f}s')

    print('\n[3/3] Stats\n')
    m = result.get('metrics', {}) if isinstance(result, dict) else {}
    sessions = result.get('sessions', [])
    trades = result.get('trades', [])

    proper = [s for s in sessions if isinstance(s.get('session'), int)]
    _BUST = {'abort', 'terminate', 'max_level_bust', 'sl_hit', 'margin_call', 'margin_bust', 'max_level_sl'}
    n_bust = sum(1 for s in proper if s.get('outcome') in _BUST)
    n_tp = sum(1 for s in proper if s.get('outcome') == 'tp_hit')
    l0_wins = sum(1 for s in proper if s.get('outcome') == 'tp_hit' and len(s.get('trades', [])) == 1)

    def _fmt(v, dp=2, pct=False, dollar=False):
        if v is None: return 'N/A'
        try:
            vf = float(v)
        except (TypeError, ValueError):
            return str(v)
        import math
        if math.isnan(vf) or math.isinf(vf): return 'N/A'
        if pct: return f'{vf:.{dp}f}%'
        if dollar: return f'${vf:,.{dp}f}'
        return f'{vf:.{dp}f}'

    print(f'{"Sessions":<30} {len(proper):>15}')
    print(f'{"TP-hit sessions":<30} {n_tp:>15}')
    print(f'{"Bust sessions":<30} {n_bust:>15}')
    print(f'{"L0-only wins":<30} {l0_wins:>15}')
    print(f'{"Bust rate":<30} {_fmt(n_bust/max(1,len(proper))*100, 1, pct=True):>15}')
    print(f'{"L0 win rate":<30} {_fmt(l0_wins/max(1,len(proper))*100, 1, pct=True):>15}')
    print(f'{"Total trades":<30} {len(trades):>15}')
    print('-' * 46)
    print(f'{"Starting balance":<30} {_fmt(starting_balance, 2, dollar=True):>15}')
    print(f'{"Finishing balance":<30} {_fmt(m.get("finishing_balance"), 2, dollar=True):>15}')
    print(f'{"Net profit":<30} {_fmt(m.get("net_profit"), 2, dollar=True):>15}')
    print(f'{"Net profit %":<30} {_fmt(m.get("net_profit_percentage"), 2, pct=True):>15}')
    print(f'{"Profit factor":<30} {_fmt(m.get("profit_factor"), 3):>15}')
    print(f'{"Max drawdown %":<30} {_fmt(m.get("max_drawdown_percentage"), 2, pct=True):>15}')
    print(f'{"Sharpe ratio":<30} {_fmt(m.get("sharpe_ratio"), 3):>15}')
    print(f'{"Annual return":<30} {_fmt(m.get("annual_return"), 2, pct=True):>15}')
    print(f'{"Session win rate":<30} {_fmt(m.get("session_win_rate"), 4):>15}')
    print(f'{"Gross profit":<30} {_fmt(m.get("gross_profit"), 2, dollar=True):>15}')
    print(f'{"Gross loss":<30} {_fmt(m.get("gross_loss"), 2, dollar=True):>15}')
    print(f'{"Total spread cost":<30} {_fmt(m.get("total_spread_cost"), 2, dollar=True):>15}')
    print(f'{"Total swap cost":<30} {_fmt(m.get("total_swap_cost"), 2, dollar=True):>15}')
    print(f'{"Total slippage cost":<30} {_fmt(m.get("total_slippage_cost"), 2, dollar=True):>15}')
    print(f'{"Cost drag %":<30} {_fmt(m.get("cost_drag_pct"), 2, pct=True):>15}')
    print(f'{"Peak equity usage":<30} {_fmt(m.get("peak_equity_usage_pct"), 2, pct=True):>15}')
    print(f'{"Worst bust PnL":<30} {_fmt(m.get("worst_bust_pnl"), 2, dollar=True):>15}')
    print(f'{"Max consec. losing sessions":<30} {_fmt(m.get("max_consecutive_session_losses"), 0):>15}')

    dbreak = m.get('depth_breakdown') or []
    if dbreak:
        print('\nDepth breakdown:')
        print(f'  {"Depth":<6} {"Count":>7} {"Wins":>6} {"Losses":>8} {"PnL":>12}')
        for d in dbreak:
            print(f'  {d.get("depth",0):<6} {d.get("count",0):>7} {d.get("wins",0):>6} '
                  f'{d.get("losses",0):>8} ${d.get("pnl",0):>10.2f}')


if __name__ == '__main__':
    main()
