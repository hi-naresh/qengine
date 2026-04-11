#!/usr/bin/env python3
"""
ARIA R(t) Structural Stress Validation
=======================================
Runs Martingale strategy on 2024-2025 EUR-USD with and without ARIA pipeline
to measure the impact of the R(t) stress accumulator on bust rate, PF, and
reward linearity.

Two runs:
  1. Baseline: Martingale with no pipeline
  2. ARIA: Martingale with ARIA pipeline (includes R(t) structural stress)
"""
import os
import sys
import time

os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import numpy as np
from qengine.research import get_candles, backtest
import arrow

# ── Config ──────────────────────────────────────────────────────────
EXCHANGE = 'OANDA'
SYMBOL = 'EUR-USD'
# Use 2024-2025 as test period (blind to phase2 research which used 2006-2023)
START = int(arrow.get('2024-01-01').timestamp() * 1000)
FINISH = int(arrow.get('2025-06-30').timestamp() * 1000)
TIMEFRAME = '5m'

BASE_CONFIG = {
    'starting_balance': 10_000,
    'fee': 0.0,
    'type': 'cfd',
    'exchange': EXCHANGE,
    'warm_up_candles': 500,
}

# Standard martingale HPs (from phase2 validated config)
BASE_HP = {
    'preset': 'custom',
    'signal_mode': 'ema',
    'direction_bias': 'both',
    'entry_on_crossover': 'yes',
    'ema_fast': 8,
    'ema_slow': 21,
    'hedge_mode': 'atr_based',
    'hedge_value': 1.5,
    'hedge_atr_period': 14,
    'hedge_expand': 'no',
    'tp_mode': 'atr_based',
    'tp_value': 1.0,
    'tp_atr_period': 14,
    'sizing_curve': 'geometric',
    'sizing_factor': 1.4142,
    'sizing_custom_sequence': 'none',
    'base_size_mode': 'pct_equity',
    'base_size_value': 0.5,
    'max_levels': 12,
    'max_bust_dd_pct': 20,
    'session_filter': 'any',
    'day_filter': 'any',
    'vol_filter': 'none',
    'trend_filter': 'none',
    'spread_filter': 'none',
    'confidence_gate': 'none',
    'cooldown_mode': 'none',
    'cooldown_value': 10,
    'max_daily_loss_pct': 0,
    'max_weekly_loss_pct': 0,
    'max_consec_busts': 0,
    'max_exposure_pct': 0,
    'abort_mode': 'level_based',
    'abort_level': 10,
}

# ARIA pipeline config
ARIA_CONFIG = [
    {
        'name': 'ARIA',
        'gate_enabled': True,
        'hp_engine_enabled': False,    # Disable HP mutation to isolate R(t) effect
        'brain_warmup': 50,
        'gate_warmup_cycles': 10,
        'gate_learning_rate': 0.05,
        'conformal_alpha': 0.1,
        'conformal_safety': 0.8,
        'fallback_level': 8,
        'max_ruin_prob': 0.5,
        'max_cycle_bars': 2000,
        'danger_abort_threshold': 0.85,
        'stress_abort_threshold': 1.5,
        'stress_abort_min_level': 2,
        'meta_enabled': True,
        'meta_window': 100,
        'meta_degradation_sigma': 1.0,
    }
]

# ── Load candles ────────────────────────────────────────────────────
print("=" * 70)
print("ARIA R(t) STRUCTURAL STRESS VALIDATION")
print("=" * 70)
print(f"\nLoading candles: {EXCHANGE} {SYMBOL}")
print(f"  Period: 2024-01-01 to 2025-06-30")
t0 = time.time()
warmup, candles = get_candles(EXCHANGE, SYMBOL, '1m', START, FINISH, warmup_candles_num=500)
print(f"  Loaded {len(candles):,} 1m candles in {time.time()-t0:.1f}s")

candles_dict = {
    f'{EXCHANGE}-{SYMBOL}': {
        'exchange': EXCHANGE,
        'symbol': SYMBOL,
        'candles': candles,
    }
}

warmup_dict = None
if warmup is not None and warmup.ndim == 2 and len(warmup) > 0:
    warmup_dict = {
        f'{EXCHANGE}-{SYMBOL}': {
            'exchange': EXCHANGE,
            'symbol': SYMBOL,
            'candles': warmup,
        }
    }

routes = [{'exchange': EXCHANGE, 'strategy': 'Martingale', 'symbol': SYMBOL, 'timeframe': TIMEFRAME}]
data_routes = []


def run_bt(label, pipeline_configs=None):
    """Run a single backtest and return results."""
    print(f"\n{'─'*50}")
    print(f"Running: {label}")
    t0 = time.time()

    result = backtest(
        config=BASE_CONFIG,
        routes=[dict(r) for r in routes],
        data_routes=data_routes,
        candles=candles_dict,
        warmup_candles=warmup_dict,
        hyperparameters=BASE_HP,
        generate_equity_curve=True,
        fast_mode=False,
        pipeline_configs=pipeline_configs,
    )

    elapsed = time.time() - t0
    m = result.get('metrics', {})
    ps = result.get('pipeline_stats', {})

    print(f"  Completed in {elapsed:.1f}s")
    print(f"  Total trades: {m.get('total', 0)}")
    print(f"  Win rate:     {m.get('win_rate', 0):.1f}%")
    print(f"  Net profit:   {m.get('net_profit_percentage', 0):.2f}%")
    print(f"  Profit factor:{m.get('profit_factor', 0):.2f}")
    print(f"  Max drawdown: {m.get('max_drawdown', 0):.2f}%")

    if ps:
        # Print ARIA-specific stats
        for route_key, route_stats in ps.items():
            ss = route_stats.get('structural_stress', {})
            if ss:
                print(f"\n  R(t) Stats:")
                print(f"    R(t) total:          {ss.get('r_t', 0):.4f}")
                print(f"    Normalised R(t):     {ss.get('normalised_rt', 0):.4f}")
                print(f"    Recent stress rate:  {ss.get('recent_stress_rate', 0):.4f}")
                print(f"    Stress velocity:     {ss.get('stress_velocity', 0):.4f}")
                print(f"    N cycles tracked:    {ss.get('n_cycles', 0)}")

            gate = route_stats.get('gate', {})
            if gate:
                print(f"  Gate Stats:")
                print(f"    Cycles seen:  {gate.get('n_cycles', 0)}")
                print(f"    Warmed up:    {gate.get('warmed_up', False)}")

    return result, elapsed


# ── Run both variants ───────────────────────────────────────────────
results = {}

# 1. Baseline: no pipeline
results['baseline'], t1 = run_bt('Martingale (baseline, no pipeline)')

# 2. ARIA with R(t)
results['aria_rt'], t2 = run_bt('Martingale + ARIA (with R(t))', pipeline_configs=ARIA_CONFIG)

# ── Summary comparison ──────────────────────────────────────────────
print("\n" + "=" * 70)
print("COMPARISON SUMMARY")
print("=" * 70)
print(f"{'Metric':<25} {'Baseline':>12} {'ARIA+R(t)':>12} {'Delta':>12}")
print("─" * 70)

m1 = results['baseline'].get('metrics', {})
m2 = results['aria_rt'].get('metrics', {})

metrics_to_compare = [
    ('Total trades', 'total', '{:>12}', '{:>12}'),
    ('Win rate %', 'win_rate', '{:>11.1f}%', '{:>11.1f}%'),
    ('Net profit %', 'net_profit_percentage', '{:>11.2f}%', '{:>11.2f}%'),
    ('Profit factor', 'profit_factor', '{:>12.2f}', '{:>12.2f}'),
    ('Max drawdown %', 'max_drawdown', '{:>11.2f}%', '{:>11.2f}%'),
    ('Sharpe ratio', 'sharpe_ratio', '{:>12.2f}', '{:>12.2f}'),
]

for label, key, fmt1, fmt2 in metrics_to_compare:
    v1 = m1.get(key, 0)
    v2 = m2.get(key, 0)
    try:
        delta = v2 - v1
        delta_str = f"{delta:>+11.2f}" if isinstance(v1, float) else f"{delta:>+12}"
    except (TypeError, ValueError):
        delta_str = "N/A"
    print(f"{label:<25} {fmt1.format(v1)} {fmt2.format(v2)} {delta_str}")

# ── Reward linearity test ───────────────────────────────────────────
print("\n" + "=" * 70)
print("REWARD LINEARITY (R² of cumulative PnL vs time)")
print("=" * 70)

for label, res in results.items():
    eq = res.get('equity_curve', [])
    if eq and len(eq) > 10:
        if isinstance(eq[0], dict):
            values = [e.get('balance', e.get('equity', 0)) for e in eq]
        elif isinstance(eq[0], (list, tuple)):
            values = [e[1] if len(e) > 1 else e[0] for e in eq]
        else:
            values = list(eq)

        values = np.array(values, dtype=float)
        x = np.arange(len(values))
        if len(x) > 1:
            # R² of linear fit
            coeffs = np.polyfit(x, values, 1)
            predicted = np.polyval(coeffs, x)
            ss_res = np.sum((values - predicted) ** 2)
            ss_tot = np.sum((values - np.mean(values)) ** 2)
            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            slope = coeffs[0]
            print(f"  {label:<20}: R² = {r_squared:.4f}, slope = {slope:.4f}/bar")
        else:
            print(f"  {label:<20}: insufficient data")
    else:
        print(f"  {label:<20}: no equity curve")

print(f"\n  Elapsed: baseline={t1:.0f}s, ARIA={t2:.0f}s")
print("\nDone.")
