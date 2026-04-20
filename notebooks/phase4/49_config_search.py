"""
49 — Systematic Configuration Search

Finds profitable Martingale configurations on the REAL engine by sweeping
key parameters that determine cycle profitability:

1. Timeframe: affects signal quality and cycle speed
2. hedge_value: wider hedges = fewer busts, slower cycles
3. tp_value: TP distance, determines win size
4. max_levels: depth capacity, determines bust severity
5. sizing_curve + sizing_factor: exposure growth rate
6. signal_mode: entry signal quality

Each choice is justified by the math of Martingale risk:
- Win probability per cycle: P(win) = 1 - P(bust) where bust = reaching max_levels
- Expected value: E[V] = P(win) * avg_win - P(bust) * avg_bust_loss
- For E[V] > 0: need P(win) * avg_win > P(bust) * avg_bust_loss
- Wider hedges reduce P(bust) but also reduce avg_win (fewer cycles/time)
- Key ratio: hedge_dist / tp_dist determines the asymmetry
"""

import sys, os, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.chdir(str(Path(__file__).resolve().parents[2]))

from qengine.research.backtest import backtest
from qengine.research.candles import get_candles
import qengine.helpers as jh
import numpy as np

RESULTS_DIR = Path(__file__).resolve().parent / 'results'

ex, sym = 'OANDA', 'EUR-USD'
key = f'{ex}-{sym}'

# Cache candles to avoid reloading
_candle_cache = {}

def get_cached_candles(start, end):
    cache_key = f'{start}_{end}'
    if cache_key not in _candle_cache:
        w, t = get_candles(exchange=ex, symbol=sym, timeframe='1m',
            start_date_timestamp=jh.date_to_timestamp(start),
            finish_date_timestamp=jh.date_to_timestamp(end), warmup_candles_num=10000)
        _candle_cache[cache_key] = (w, t)
    return _candle_cache[cache_key]


def run_bt(start, end, tf, hp_overrides, label=''):
    w, t = get_cached_candles(start, end)
    c = {key: {'exchange': ex, 'symbol': sym, 'candles': t}}
    wd = {key: {'exchange': ex, 'symbol': sym, 'candles': w}} if w.ndim == 2 and len(w) > 0 else None

    hp = {key: hp_overrides}

    result = backtest(
        config={'starting_balance': 10000, 'fee': 0, 'type': 'cfd', 'exchange': ex, 'warm_up_candles': 10000},
        routes=[{'exchange': ex, 'symbol': sym, 'timeframe': tf, 'strategy': 'Martingale'}],
        data_routes=[], candles=c, warmup_candles=wd,
        hyperparameters=hp,
        generate_equity_curve=False, generate_logs=False)

    m = result.get('metrics', {})
    return {
        'label': label,
        'timeframe': tf,
        'hp': hp_overrides,
        'sessions': m.get('total_sessions', 0),
        'session_wr': m.get('session_win_rate', 0),
        'bust_rate': m.get('bust_rate', 0),
        'bust_count': m.get('bust_count', m.get('total_busts', 0)),
        'pf': m.get('profit_factor', 0),
        'net_pct': m.get('net_profit_percentage', 0),
        'max_dd': m.get('max_drawdown', 0),
        'trades': m.get('total', 0),
        'sharpe': m.get('sharpe_ratio', 0),
    }


def print_result(r):
    wr = f"{r['session_wr']:.1%}" if isinstance(r['session_wr'], float) else str(r['session_wr'])
    pf = f"{r['pf']:.3f}" if isinstance(r['pf'], (int, float)) and r['pf'] < 100 else 'inf'
    print(f"  {r['label']:<45} Sess={r['sessions']:>4} WR={wr:>6} Busts={r['bust_count']:>3} "
          f"PF={pf:>7} Net={r['net_pct']:>7.2f}% DD={r['max_dd']:>7.2f}%")


# ============================================================
# PHASE 1: Timeframe sweep with original defaults
# ============================================================
print("=" * 110)
print("PHASE 1: Timeframe sweep (original preset)")
print("=" * 110)

# Use 2023 H1 as search period, 2023 H2 as validation
search_start, search_end = '2023-01-01', '2023-06-30'

base_hp = {'preset': 'original'}
for tf in ['5m', '15m', '30m', '1h', '4h']:
    try:
        r = run_bt(search_start, search_end, tf, base_hp, f'original {tf}')
        print_result(r)
    except Exception as e:
        print(f"  original {tf}: ERROR {e}")


# ============================================================
# PHASE 2: Hedge/TP distance sweep on best timeframe candidates
# ============================================================
print(f"\n{'='*110}")
print("PHASE 2: Hedge/TP distance sweep (fixed_pips mode)")
print("Rationale: hedge_dist/tp_dist ratio determines win/bust asymmetry")
print("=" * 110)

for tf in ['30m', '1h']:
    print(f"\n--- {tf} ---")
    for hedge in [15, 20, 25, 30]:
        for tp in [10, 15, 20, 25]:
            hp = {
                'preset': 'original',
                'hedge_mode': 'fixed_pips',
                'hedge_value': hedge,
                'tp_mode': 'fixed_pips',
                'tp_value': tp,
            }
            label = f'{tf} hedge={hedge} tp={tp} ratio={hedge/tp:.1f}'
            try:
                r = run_bt(search_start, search_end, tf, hp, label)
                # Only print profitable or near-profitable
                if r['pf'] >= 0.95:
                    print_result(r)
            except Exception as e:
                pass


# ============================================================
# PHASE 3: Max levels + sizing curve sweep on best configs
# ============================================================
print(f"\n{'='*110}")
print("PHASE 3: Max levels + sizing curve (on best hedge/tp combos)")
print("Rationale: fewer levels = fewer busts but lower win recovery")
print("=" * 110)

for tf in ['30m', '1h']:
    print(f"\n--- {tf} ---")
    for hedge, tp in [(20, 15), (25, 15), (25, 20), (30, 20)]:
        for max_lvl in [3, 4, 5]:
            for curve, factor in [('geometric', 1.5), ('sqrt', 2.0), ('linear', 2.0), ('fibonacci', 2.0)]:
                hp = {
                    'preset': 'original',
                    'hedge_mode': 'fixed_pips',
                    'hedge_value': hedge,
                    'tp_mode': 'fixed_pips',
                    'tp_value': tp,
                    'max_levels': max_lvl,
                    'sizing_curve': curve,
                    'sizing_factor': factor,
                }
                label = f'{tf} h={hedge} t={tp} L={max_lvl} {curve[:3]} f={factor}'
                try:
                    r = run_bt(search_start, search_end, tf, hp, label)
                    if r['pf'] >= 1.0 and r['sessions'] >= 20:
                        print_result(r)
                except Exception as e:
                    pass


# ============================================================
# PHASE 4: Signal mode sweep on profitable configs
# ============================================================
print(f"\n{'='*110}")
print("PHASE 4: Signal mode sweep on promising configs")
print("=" * 110)

# Collect all profitable configs from phase 3 manually,
# or test the most promising combos with different signals
for tf in ['30m', '1h']:
    print(f"\n--- {tf} ---")
    for signal in ['random', 'ema_cross', 'rsi', 'macd', 'supertrend']:
        for hedge, tp, max_lvl in [(25, 15, 4), (25, 20, 4), (30, 20, 4), (20, 15, 4)]:
            hp = {
                'preset': 'original',
                'signal_mode': signal,
                'hedge_mode': 'fixed_pips',
                'hedge_value': hedge,
                'tp_mode': 'fixed_pips',
                'tp_value': tp,
                'max_levels': max_lvl,
                'sizing_curve': 'sqrt',
                'sizing_factor': 2.0,
            }
            label = f'{tf} {signal} h={hedge} t={tp} L={max_lvl}'
            try:
                r = run_bt(search_start, search_end, tf, hp, label)
                if r['pf'] >= 1.0 and r['sessions'] >= 20:
                    print_result(r)
            except Exception as e:
                pass


# ============================================================
# PHASE 5: Validate best configs on out-of-sample
# ============================================================
print(f"\n{'='*110}")
print("PHASE 5: Out-of-sample validation (2023 H2 + 2024)")
print("=" * 110)

# Best configs will be validated here
# For now, test a few promising combos
val_periods = [
    ('2023-07-01', '2023-12-31', '2023 H2 (OOS)'),
    ('2024-01-01', '2024-12-31', '2024 (OOS)'),
]

# Will be populated based on Phase 3-4 results
best_configs = [
    {'tf': '30m', 'hp': {'preset': 'original', 'hedge_mode': 'fixed_pips', 'hedge_value': 25,
     'tp_mode': 'fixed_pips', 'tp_value': 15, 'max_levels': 4, 'sizing_curve': 'sqrt', 'sizing_factor': 2.0}},
    {'tf': '1h', 'hp': {'preset': 'original', 'hedge_mode': 'fixed_pips', 'hedge_value': 30,
     'tp_mode': 'fixed_pips', 'tp_value': 20, 'max_levels': 4, 'sizing_curve': 'sqrt', 'sizing_factor': 2.0}},
    {'tf': '30m', 'hp': {'preset': 'original', 'hedge_mode': 'fixed_pips', 'hedge_value': 20,
     'tp_mode': 'fixed_pips', 'tp_value': 15, 'max_levels': 4, 'sizing_curve': 'sqrt', 'sizing_factor': 2.0}},
]

for cfg in best_configs:
    for start, end, label in val_periods:
        try:
            r = run_bt(start, end, cfg['tf'], cfg['hp'], f"{cfg['tf']} h={cfg['hp']['hedge_value']} t={cfg['hp']['tp_value']} | {label}")
            print_result(r)
        except Exception as e:
            print(f"  ERROR: {e}")

print("\nDone.")
