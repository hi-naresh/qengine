"""Run BOTH baseline and pipeline on the same 2025-2026 OOS window and compute
rigorous comparison metrics including exact max drawdown from the equity curve.

Usage:
    python3 scripts/run_oos_compare.py
"""
from __future__ import annotations

import os
import sys
import math
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _to_ms(s: str) -> int:
    return int((datetime.strptime(s, '%Y-%m-%d') - datetime(1970, 1, 1)).total_seconds() * 1000)


def compute_max_dd(equity_curve):
    """Compute max drawdown from equity curve (list of dicts with 'equity' or
    a list/array of floats). Returns (max_dd_pct, peak_equity, trough_equity).
    """
    if equity_curve is None or len(equity_curve) == 0:
        return None, None, None

    # Handle various equity curve representations
    eq = []
    for pt in equity_curve:
        if isinstance(pt, dict):
            v = pt.get('equity', pt.get('value', pt.get('balance')))
        else:
            v = pt
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            eq.append(float(v))
    if not eq:
        return None, None, None
    eq_arr = np.array(eq, dtype=float)

    peak = eq_arr[0]
    max_dd = 0.0
    peak_at_max_dd = peak
    trough_at_max_dd = peak
    running_peak = peak
    for v in eq_arr:
        if v > running_peak:
            running_peak = v
        dd = (running_peak - v) / running_peak if running_peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            peak_at_max_dd = running_peak
            trough_at_max_dd = v
    return max_dd * 100.0, peak_at_max_dd, trough_at_max_dd


def run(label: str, hp: dict, pipeline_configs=None):
    print(f'\n{"="*72}')
    print(f'{label}')
    print('=' * 72)

    from qengine.research.candles import get_candles
    from qengine.research.backtest import backtest
    import qengine.helpers as jh

    start_date = '2025-01-01'
    end_date = '2026-04-20'
    exchange, symbol, tf = 'OANDA', 'EUR-USD', '5m'
    start_ts = _to_ms(start_date)
    end_ts = _to_ms(end_date) + 86_400_000 - 60_000

    _warmup, candles = get_candles(
        exchange=exchange, symbol=symbol, timeframe='1m',
        start_date_timestamp=start_ts, finish_date_timestamp=end_ts,
    )
    config = {'starting_balance': 10_000, 'fee': 0.0, 'type': 'cfd',
              'exchange': exchange, 'warm_up_candles': 210}
    routes = [{'exchange': exchange, 'strategy': 'Martingale',
               'symbol': symbol, 'timeframe': tf}]
    key = jh.key(exchange, symbol)
    cdict = {key: {'exchange': exchange, 'symbol': symbol, 'candles': candles}}

    t0 = datetime.utcnow()
    result = backtest(
        config=config, routes=routes, data_routes=[], candles=cdict,
        hyperparameters=hp, pipeline_configs=pipeline_configs,
        generate_equity_curve=True, cost_model=True,
    )
    print(f'  run time: {(datetime.utcnow() - t0).total_seconds():.1f}s')

    m = result.get('metrics', {}) or {}
    sessions = result.get('sessions', []) or []
    trades = result.get('trades', []) or []
    eq_curve = result.get('equity_curve') or result.get('charts', {}).get('equity_curve')

    proper = [s for s in sessions if isinstance(s.get('session'), int)]
    _BUST = {'abort', 'terminate', 'max_level_bust', 'sl_hit',
             'margin_call', 'margin_bust', 'max_level_sl'}
    n_bust = sum(1 for s in proper if s.get('outcome') in _BUST)
    l0_wins = sum(1 for s in proper if s.get('outcome') == 'tp_hit'
                  and len(s.get('trades', [])) == 1)

    # Exact max DD from equity curve
    max_dd_pct, peak, trough = compute_max_dd(eq_curve)

    # Fallback: if no equity curve, compute from session running balance
    if max_dd_pct is None:
        running_bal = 10_000.0
        sessions_sorted = sorted(proper, key=lambda s: s.get('opened_at', 0))
        equities = [running_bal]
        for s in sessions_sorted:
            pnl = s.get('total_pnl', 0) or 0
            try:
                running_bal += float(pnl)
            except (TypeError, ValueError):
                pass
            equities.append(running_bal)
        max_dd_pct, peak, trough = compute_max_dd(equities)

    return {
        'label': label,
        'n_sessions': len(proper),
        'n_trades': len(trades),
        'n_bust': n_bust,
        'l0_wins': l0_wins,
        'net_profit': m.get('net_profit'),
        'net_profit_pct': m.get('net_profit_percentage'),
        'profit_factor': m.get('profit_factor'),
        'finishing_balance': m.get('finishing_balance'),
        'annual_return': m.get('annual_return'),
        'session_win_rate': m.get('session_win_rate'),
        'peak_equity_usage': m.get('peak_equity_usage_pct'),
        'cost_drag': m.get('cost_drag_pct'),
        'worst_bust': m.get('worst_bust_pnl'),
        'max_consec_losses': m.get('max_consecutive_session_losses'),
        'total_spread': m.get('total_spread_cost'),
        'gross_profit': m.get('gross_profit'),
        'gross_loss': m.get('gross_loss'),
        'max_dd_pct': max_dd_pct,
        'max_dd_peak': peak,
        'max_dd_trough': trough,
    }


def _fmt(v, dp=2, pct=False, dollar=False, default='N/A'):
    if v is None: return default
    try:
        vf = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(vf) or math.isinf(vf): return default
    if pct: return f'{vf:.{dp}f}%'
    if dollar: return f'${vf:,.{dp}f}'
    return f'{vf:.{dp}f}'


def main():
    print('OOS comparison: IslandPilot vs Baseline (original preset)')
    print(f'Period: 2025-01-01 → 2026-04-20  |  Route: OANDA EUR-USD 5m / Martingale  |  $10K')

    baseline_hp = {
        'preset': 'original', 'signal_mode': 'none', 'direction_bias': 'long_only',
        'sizing_curve': 'geometric', 'sizing_factor': 2.0, 'max_levels': 6,
        'hedge_mode': 'fixed_pips', 'hedge_value': 10.0,
        'tp_mode': 'fixed_pips', 'tp_value': 20.0,
        'base_size_mode': 'pct_equity', 'base_size_value': 1.0,
    }

    baseline = run('Baseline — Martingale "original" preset, no pipeline',
                   hp=baseline_hp, pipeline_configs=None)
    pipeline = run('IslandPilot — trained model (57 genes, 2024 Q1 pre-flight training)',
                   hp=None, pipeline_configs=[{'name': 'IslandPilot'}])

    print('\n')
    print('=' * 88)
    print('  Side-by-side comparison')
    print('=' * 88)
    labels = [
        ('Sessions',              'n_sessions',         lambda x: f'{x:,}' if x else '0',       None),
        ('Trades',                'n_trades',           lambda x: f'{x:,}' if x else '0',       None),
        ('Starting balance',      None,                 lambda x: '$10,000.00',                  None),
        ('Finishing balance',     'finishing_balance',  lambda x: _fmt(x, 2, dollar=True),       None),
        ('Net profit',            'net_profit',         lambda x: _fmt(x, 2, dollar=True),       None),
        ('Net profit %',          'net_profit_pct',     lambda x: _fmt(x, 2, pct=True),          None),
        ('Profit factor',         'profit_factor',      lambda x: _fmt(x, 3),                    None),
        ('Max drawdown %',        'max_dd_pct',         lambda x: _fmt(x, 2, pct=True),          None),
        ('Annual return %',       'annual_return',      lambda x: _fmt(x, 2, pct=True),          None),
        ('Session win rate',      'session_win_rate',   lambda x: _fmt(x*100 if x else 0, 2, pct=True), None),
        ('Bust rate',             None,                 lambda rec: f"{rec['n_bust']/max(1,rec['n_sessions'])*100:.1f}%  ({rec['n_bust']}/{rec['n_sessions']})", True),
        ('L0 win rate',           None,                 lambda rec: f"{rec['l0_wins']/max(1,rec['n_sessions'])*100:.1f}%  ({rec['l0_wins']}/{rec['n_sessions']})", True),
        ('Peak equity usage',     'peak_equity_usage',  lambda x: _fmt(x, 2, pct=True),          None),
        ('Cost drag',             'cost_drag',          lambda x: _fmt(x, 2, pct=True),          None),
        ('Worst bust PnL',        'worst_bust',         lambda x: _fmt(x, 2, dollar=True),       None),
        ('Max consec. losses',    'max_consec_losses',  lambda x: _fmt(x, 0),                    None),
        ('Total spread cost',     'total_spread',       lambda x: _fmt(x, 2, dollar=True),       None),
        ('Gross profit',          'gross_profit',       lambda x: _fmt(x, 2, dollar=True),       None),
        ('Gross loss',            'gross_loss',         lambda x: _fmt(x, 2, dollar=True),       None),
    ]

    print(f'  {"Metric":<28} {"Baseline":>25} {"IslandPilot":>25}')
    print('  ' + '-' * 80)
    for name, key, fmt, is_record_fn in labels:
        if is_record_fn:
            b = fmt(baseline)
            p = fmt(pipeline)
        else:
            b = fmt(baseline.get(key))
            p = fmt(pipeline.get(key))
        print(f'  {name:<28} {b:>25} {p:>25}')

    print('\n  Max DD context:')
    print(f'    Baseline: peak ${baseline.get("max_dd_peak", 0):.2f} → trough ${baseline.get("max_dd_trough", 0):.2f}')
    print(f'    Pipeline: peak ${pipeline.get("max_dd_peak", 0):.2f} → trough ${pipeline.get("max_dd_trough", 0):.2f}')


if __name__ == '__main__':
    main()
