#!/usr/bin/env python3
"""
Script 21: GridPilot Framework Backtest Validation
====================================================
Runs SurefirePilot vs SurefireV2 (baseline) on the same data
to validate the framework reduces busts without destroying P&L.

Compares:
  1. SurefireV2 (baseline) — no framework
  2. SurefirePilot (full) — danger scorer + entry gate + Q-abort
  3. SurefirePilot (danger only) — scorer + gate, no Q-abort
  4. SurefirePilot (Q-abort only) — Q-abort, no gate
"""
import os
import sys
import time

os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import numpy as np
from qengine.research import get_candles, backtest

# ── Config ──────────────────────────────────────────────────────────
import arrow

EXCHANGE = 'OANDA'
SYMBOL = 'EUR-USD'
START = int(arrow.get('2020-01-01').timestamp() * 1000)
FINISH = int(arrow.get('2025-12-31').timestamp() * 1000)
TIMEFRAME = '5m'

BASE_CONFIG = {
    'starting_balance': 10_000,
    'fee': 0.0,
    'type': 'cfd',
    'exchange': EXCHANGE,
    'warm_up_candles': 500,
}

BASE_HP = {
    'initial_size': 2.0,
    'sizing_operator': 'sqrt',
    'sizing_factor': 2.0,
    'max_levels': 6,
    'bucket_pct': 0.1,
    'signal_mode': 'ema',
    'atr_period': 14,
    'hedge_atr_mult': 1.5,
    'ema_fast': 8,
    'ema_slow': 21,
    'session_filter': 'london_ny',
    'cooldown_bars': 10,
    'max_daily_loss_pct': 2.0,
    'max_consec_busts': 3,
    'atr_expansion_mult': 2.0,
}

# ── Load candles ────────────────────────────────────────────────────
print("=" * 70)
print("GRIDPILOT FRAMEWORK BACKTEST VALIDATION")
print("=" * 70)
print(f"\nLoading candles: {EXCHANGE} {SYMBOL} {START} to {FINISH}...")
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

# Routes: main route + data routes for multi-TF features
routes = [{'exchange': EXCHANGE, 'strategy': None, 'symbol': SYMBOL, 'timeframe': TIMEFRAME}]
data_routes = [
    {'exchange': EXCHANGE, 'symbol': SYMBOL, 'timeframe': '15m'},
    {'exchange': EXCHANGE, 'symbol': SYMBOL, 'timeframe': '1h'},
    {'exchange': EXCHANGE, 'symbol': SYMBOL, 'timeframe': '1D'},
]


def run_backtest(strategy_name, hp, label):
    """Run a single backtest and return results."""
    print(f"\n{'─'*50}")
    print(f"Running: {label} ({strategy_name})")
    t0 = time.time()

    routes_copy = [dict(r) for r in routes]
    routes_copy[0]['strategy'] = strategy_name

    result = backtest(
        config=BASE_CONFIG,
        routes=routes_copy,
        data_routes=data_routes,
        candles=candles_dict,
        warmup_candles=warmup_dict,
        hyperparameters=hp,
        generate_equity_curve=True,
        fast_mode=False,
    )

    elapsed = time.time() - t0
    m = result.get('metrics', {})
    print(f"  Completed in {elapsed:.1f}s")
    print(f"  Total trades: {m.get('total', 0)}")
    print(f"  Win rate: {m.get('win_rate', 0):.1f}%")
    print(f"  Net profit: {m.get('net_profit_percentage', 0):.2f}%")
    print(f"  Profit factor: {m.get('profit_factor', 0):.2f}")
    print(f"  Max drawdown: {m.get('max_drawdown', 0):.2f}%")

    return result, elapsed


# ── Run all variants ────────────────────────────────────────────────
results = {}

# 1. Baseline: SurefireV2 (no framework)
results['baseline'], _ = run_backtest('SurefireV2', BASE_HP, 'SurefireV2 (baseline)')

# 2. Full pilot: danger + gate + Q-abort
pilot_hp_full = {**BASE_HP, 'pilot_enable_danger': True, 'pilot_enable_gate': True, 'pilot_enable_abort': True}
results['full'], _ = run_backtest('SurefirePilot', pilot_hp_full, 'SurefirePilot (full)')

# 3. Danger only: scorer + gate, no Q-abort
pilot_hp_danger = {**BASE_HP, 'pilot_enable_danger': True, 'pilot_enable_gate': True, 'pilot_enable_abort': False}
results['danger_only'], _ = run_backtest('SurefirePilot', pilot_hp_danger, 'SurefirePilot (danger+gate only)')

# 4. Q-abort only: no gate
pilot_hp_abort = {**BASE_HP, 'pilot_enable_danger': True, 'pilot_enable_gate': False, 'pilot_enable_abort': True}
results['abort_only'], _ = run_backtest('SurefirePilot', pilot_hp_abort, 'SurefirePilot (Q-abort only)')

# ── Summary ─────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"{'Mode':<30} {'Trades':>7} {'WinRate':>8} {'NetPnL%':>9} {'PF':>6} {'MaxDD':>7}")
print("─" * 70)
for label, res in results.items():
    m = res.get('metrics', {})
    print(f"{label:<30} {m.get('total', 0):>7} {m.get('win_rate', 0):>7.1f}% {m.get('net_profit_percentage', 0):>8.2f}% {m.get('profit_factor', 0):>6.2f} {m.get('max_drawdown', 0):>6.2f}%")

print("\nDone.")
