#!/usr/bin/env python3
"""
Step 5: Full Surefire Hedge Cycle Simulation on Real Price Data
================================================================
Simulates COMPLETE multi-level hedge cycles on EUR-USD 5m candles,
measuring P(bust) under different filter regimes (session, volatility, combined).
"""

import os, sys
os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timezone
from collections import defaultdict
import time

import qengine.indicators as ta
import qengine.helpers as jh
from qengine.research import get_candles

# ─── Parameters ───────────────────────────────────────────────────────────────
TP_ATR_MULTIPLE = 0.8
RISK_REWARD = 2.0        # tp_dist = RISK_REWARD * hedge_dist  =>  hedge_dist = tp_dist / RISK_REWARD
MULTIPLIER = 2.0
MAX_LEVELS = 5            # levels 0-4; bust if all 5 lose
ATR_PERIOD = 14
PIP_SIZE = 0.0001
BASE_SIZE = 0.1           # lots
PIP_VALUE = 10.0          # USD per pip per standard lot (1.0 lot)
MAX_BARS_PER_LEVEL = 500  # timeout safety per level

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Load Data ────────────────────────────────────────────────────────────────
print("Loading EUR-USD 5m candles from OANDA...")
t0 = time.time()
warmup_candles, candles = get_candles('OANDA', 'EUR-USD', '5m',
    jh.date_to_timestamp('2024-01-01'), jh.date_to_timestamp('2026-03-01'),
    warmup_candles_num=210)
if warmup_candles is not None and warmup_candles.ndim == 2 and len(warmup_candles) > 0:
    candles = np.concatenate([warmup_candles, candles], axis=0)

print(f"Total candles: {len(candles):,} ({time.time()-t0:.1f}s)")

# ─── Compute Indicators ──────────────────────────────────────────────────────
timestamps = candles[:, 0]
opens  = candles[:, 1]
closes = candles[:, 2]
highs  = candles[:, 3]
lows   = candles[:, 4]

ema8  = ta.ema(candles, period=8, sequential=True)
ema21 = ta.ema(candles, period=21, sequential=True)
atr   = ta.atr(candles, period=ATR_PERIOD, sequential=True)

print(f"Indicators computed. ATR range: {np.nanmin(atr[ATR_PERIOD:]):.6f} - {np.nanmax(atr[ATR_PERIOD:]):.6f}")

# ─── Helper Functions ─────────────────────────────────────────────────────────
def get_utc_hour(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).hour

def get_session(hour):
    if 0 <= hour < 8:
        return 'Tokyo'
    elif 8 <= hour < 13:
        return 'London'
    elif 13 <= hour < 17:
        return 'Overlap'
    elif 17 <= hour < 22:
        return 'NY'
    else:
        return 'Off'

def compute_atr_percentile(atr_arr, idx, lookback=1000):
    """ATR percentile over trailing lookback bars."""
    start = max(0, idx - lookback)
    window = atr_arr[start:idx+1]
    window = window[~np.isnan(window)]
    if len(window) < 50:
        return 50.0  # default
    return (np.sum(window < atr_arr[idx]) / len(window)) * 100.0


# ─── Core Simulation: One Level ──────────────────────────────────────────────
def simulate_one_level(entry_price, direction, tp_dist, hedge_dist, start_bar):
    """
    Walk forward from start_bar, check if TP or SL is hit first.
    Returns: ('tp', end_bar) or ('sl', end_bar, sl_price) or ('timeout', end_bar)
    """
    if direction == 'long':
        tp_price = entry_price + tp_dist
        sl_price = entry_price - hedge_dist
    else:
        tp_price = entry_price - tp_dist
        sl_price = entry_price + hedge_dist

    max_bar = min(start_bar + MAX_BARS_PER_LEVEL, len(highs))

    for j in range(start_bar, max_bar):
        h = highs[j]
        l = lows[j]

        if direction == 'long':
            # Check if both hit on same bar: assume SL hit first (conservative)
            if l <= sl_price and h >= tp_price:
                return ('sl', j, sl_price)
            if h >= tp_price:
                return ('tp', j)
            if l <= sl_price:
                return ('sl', j, sl_price)
        else:
            if h >= sl_price and l <= tp_price:
                return ('sl', j, sl_price)
            if l <= tp_price:
                return ('tp', j)
            if h >= sl_price:
                return ('sl', j, sl_price)

    return ('timeout', max_bar - 1)


# ─── Core Simulation: Full Cycle ─────────────────────────────────────────────
def simulate_full_cycle(entry_bar, initial_direction):
    """
    Simulate a complete surefire hedge cycle starting at entry_bar.
    Returns dict with cycle results.
    """
    entry_price = closes[entry_bar]
    direction = initial_direction
    current_bar = entry_bar + 1  # start scanning from next bar
    total_pnl = 0.0
    level_results = []

    for level in range(MAX_LEVELS):
        # Compute ATR-based distances at current bar
        current_atr = atr[min(current_bar, len(atr)-1)]
        if np.isnan(current_atr) or current_atr <= 0:
            current_atr = atr[entry_bar]  # fallback
        if np.isnan(current_atr) or current_atr <= 0:
            return None  # can't compute distances

        tp_dist = current_atr * TP_ATR_MULTIPLE
        hedge_dist = tp_dist / RISK_REWARD

        size = BASE_SIZE * (MULTIPLIER ** level)
        tp_pips = tp_dist / PIP_SIZE
        sl_pips = hedge_dist / PIP_SIZE

        result = simulate_one_level(entry_price, direction, tp_dist, hedge_dist, current_bar)

        if result[0] == 'tp':
            # Win at this level
            profit = tp_pips * PIP_VALUE * size
            total_pnl += profit
            end_bar = result[1]
            level_results.append({
                'level': level, 'outcome': 'tp', 'direction': direction,
                'entry_price': entry_price, 'size': size,
                'tp_pips': tp_pips, 'sl_pips': sl_pips,
                'pnl': profit, 'end_bar': end_bar
            })
            return {
                'outcome': 'win', 'win_level': level, 'total_pnl': total_pnl,
                'entry_bar': entry_bar, 'end_bar': end_bar,
                'bars_taken': end_bar - entry_bar,
                'levels': level_results
            }

        elif result[0] == 'sl':
            # Loss at this level, hedge fires
            loss = sl_pips * PIP_VALUE * size
            total_pnl -= loss
            end_bar = result[1]
            sl_price = result[2]
            level_results.append({
                'level': level, 'outcome': 'sl', 'direction': direction,
                'entry_price': entry_price, 'size': size,
                'tp_pips': tp_pips, 'sl_pips': sl_pips,
                'pnl': -loss, 'end_bar': end_bar
            })
            # Next level: opposite direction, entry at SL price
            entry_price = sl_price
            direction = 'short' if direction == 'long' else 'long'
            current_bar = end_bar + 1
            if current_bar >= len(highs):
                return None  # ran out of data

        elif result[0] == 'timeout':
            # Timeout - treat as inconclusive, skip
            return None

    # If we get here, all MAX_LEVELS levels lost => BUST
    return {
        'outcome': 'bust', 'win_level': -1, 'total_pnl': total_pnl,
        'entry_bar': entry_bar, 'end_bar': level_results[-1]['end_bar'],
        'bars_taken': level_results[-1]['end_bar'] - entry_bar,
        'levels': level_results
    }


# ─── Find EMA Crossover Signals ──────────────────────────────────────────────
print("\nFinding EMA 8/21 crossover signals...")
min_start = max(ATR_PERIOD + 5, 25)  # need enough data for indicators
signals = []

for i in range(min_start, len(candles) - MAX_BARS_PER_LEVEL):
    if np.isnan(ema8[i]) or np.isnan(ema21[i]) or np.isnan(ema8[i-1]) or np.isnan(ema21[i-1]):
        continue
    if np.isnan(atr[i]) or atr[i] <= 0:
        continue

    # Bullish crossover: ema8 crosses above ema21
    if ema8[i-1] <= ema21[i-1] and ema8[i] > ema21[i]:
        signals.append((i, 'long'))
    # Bearish crossover: ema8 crosses below ema21
    elif ema8[i-1] >= ema21[i-1] and ema8[i] < ema21[i]:
        signals.append((i, 'short'))

print(f"Total crossover signals: {len(signals):,}")

# ─── Precompute signal metadata ──────────────────────────────────────────────
signal_hours = np.array([get_utc_hour(timestamps[s[0]]) for s in signals])
signal_sessions = np.array([get_session(h) for h in signal_hours])
signal_atr_pctiles = np.array([compute_atr_percentile(atr, s[0]) for s in signals])
signal_bars = np.array([s[0] for s in signals])

print(f"Session distribution: {dict(zip(*np.unique(signal_sessions, return_counts=True)))}")
print(f"ATR percentile range: {signal_atr_pctiles.min():.1f} - {signal_atr_pctiles.max():.1f}")


# ─── Run Simulation with Filter ──────────────────────────────────────────────
def run_simulation(signal_mask, label=""):
    """
    Run full cycle simulation on filtered signals.
    Signals are processed in order; cycles cannot overlap.
    """
    filtered_indices = np.where(signal_mask)[0]
    cycles = []
    next_allowed_bar = 0

    for idx in filtered_indices:
        bar, direction = signals[idx]
        if bar < next_allowed_bar:
            continue  # skip, previous cycle hasn't ended

        result = simulate_full_cycle(bar, direction)
        if result is None:
            continue

        cycles.append(result)
        next_allowed_bar = result['end_bar'] + 1  # no overlapping cycles

    # Compute statistics
    if len(cycles) == 0:
        return {
            'label': label, 'total': 0, 'wins': 0, 'busts': 0,
            'p_bust': 0, 'win_by_level': {}, 'avg_win_pnl': 0,
            'avg_bust_pnl': 0, 'net_pnl': 0, 'cycles': cycles,
            'bust_erase_ratio': 0
        }

    total = len(cycles)
    wins = [c for c in cycles if c['outcome'] == 'win']
    busts = [c for c in cycles if c['outcome'] == 'bust']
    n_wins = len(wins)
    n_busts = len(busts)
    p_bust = n_busts / total if total > 0 else 0

    # Win by level
    win_by_level = defaultdict(int)
    for c in wins:
        win_by_level[c['win_level']] += 1

    # P&L stats
    win_pnls = [c['total_pnl'] for c in wins]
    bust_pnls = [c['total_pnl'] for c in busts]
    avg_win_pnl = np.mean(win_pnls) if win_pnls else 0
    avg_bust_pnl = np.mean(bust_pnls) if bust_pnls else 0
    net_pnl = sum(c['total_pnl'] for c in cycles)

    # How many winning cycles does one bust erase?
    bust_erase = abs(avg_bust_pnl / avg_win_pnl) if avg_win_pnl != 0 else 0

    # Bars taken stats
    win_bars = [c['bars_taken'] for c in wins]
    bust_bars = [c['bars_taken'] for c in busts]

    return {
        'label': label,
        'total': total,
        'wins': n_wins,
        'busts': n_busts,
        'p_bust': p_bust,
        'win_by_level': dict(win_by_level),
        'avg_win_pnl': avg_win_pnl,
        'avg_bust_pnl': avg_bust_pnl,
        'net_pnl': net_pnl,
        'bust_erase_ratio': bust_erase,
        'avg_win_bars': np.mean(win_bars) if win_bars else 0,
        'avg_bust_bars': np.mean(bust_bars) if bust_bars else 0,
        'cycles': cycles,
    }


def print_result(r, show_levels=True):
    """Print results for one filter configuration."""
    print(f"\n  {'Metric':<30} {'Value':>15}")
    print(f"  {'-'*45}")
    print(f"  {'Total Cycles':<30} {r['total']:>15,}")
    print(f"  {'Wins':<30} {r['wins']:>15,}")
    print(f"  {'Busts':<30} {r['busts']:>15,}")
    print(f"  {'P(bust)':<30} {r['p_bust']:>15.4f}  ({r['p_bust']*100:.2f}%)")
    if show_levels and r['win_by_level']:
        for lvl in sorted(r['win_by_level'].keys()):
            count = r['win_by_level'][lvl]
            pct = count / r['total'] * 100 if r['total'] > 0 else 0
            print(f"  {"  Win at Level "+str(lvl):<30} {count:>10,}  ({pct:.1f}%)")
    print(f"  {'Avg Win P&L ($)':<30} {r['avg_win_pnl']:>15.2f}")
    print(f"  {'Avg Bust P&L ($)':<30} {r['avg_bust_pnl']:>15.2f}")
    print(f"  {'Net P&L ($)':<30} {r['net_pnl']:>15.2f}")
    print(f"  {'Bust Erases N Wins':<30} {r['bust_erase_ratio']:>15.1f}")
    print(f"  {'Avg Win Duration (bars)':<30} {r['avg_win_bars']:>15.1f}")
    print(f"  {'Avg Bust Duration (bars)':<30} {r['avg_bust_bars']:>15.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 1: UNFILTERED
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ANALYSIS 1: UNFILTERED — All EMA 8/21 Crossover Signals")
print("=" * 80)

mask_all = np.ones(len(signals), dtype=bool)
result_unfiltered = run_simulation(mask_all, "Unfiltered")
print_result(result_unfiltered)


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 2: SESSION FILTER
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ANALYSIS 2: SESSION FILTER")
print("=" * 80)
print("Sessions (UTC): Tokyo 0-8, London 8-13, Overlap 13-17, NY 17-22, Off 22-24")

session_filters = {
    'Tokyo Only': signal_sessions == 'Tokyo',
    'London Only': signal_sessions == 'London',
    'Overlap Only': signal_sessions == 'Overlap',
    'NY Only': signal_sessions == 'NY',
    'London+Overlap+NY': np.isin(signal_sessions, ['London', 'Overlap', 'NY']),
    'Any (unfiltered)': np.ones(len(signals), dtype=bool),
}

session_results = {}
for name, mask in session_filters.items():
    print(f"\n--- {name} (signals available: {mask.sum():,}) ---")
    r = run_simulation(mask, name)
    session_results[name] = r
    print_result(r, show_levels=False)

# Session comparison table
print(f"\n{'SESSION COMPARISON TABLE':^80}")
print(f"{'Filter':<25} {'Cycles':>8} {'Wins':>8} {'Busts':>8} {'P(bust)':>10} {'Net P&L':>12} {'Bust/Win':>10}")
print("-" * 81)
for name, r in session_results.items():
    print(f"{name:<25} {r['total']:>8,} {r['wins']:>8,} {r['busts']:>8,} "
          f"{r['p_bust']:>10.4f} {r['net_pnl']:>12.2f} {r['bust_erase_ratio']:>10.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 3: VOLATILITY FILTER (ATR Percentile)
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ANALYSIS 3: VOLATILITY FILTER — ATR Percentile Windows")
print("=" * 80)

vol_filters = {
    'Any (no filter)': (0, 100),
    'ATR pctile [10-90]': (10, 90),
    'ATR pctile [20-80]': (20, 80),
    'ATR pctile [30-70]': (30, 70),
    'ATR pctile [40-60]': (40, 60),
    'Low vol [0-30]': (0, 30),
    'Mid vol [30-70]': (30, 70),
    'High vol [70-100]': (70, 100),
}

vol_results = {}
for name, (lo, hi) in vol_filters.items():
    mask = (signal_atr_pctiles >= lo) & (signal_atr_pctiles <= hi)
    print(f"\n--- {name} (signals available: {mask.sum():,}) ---")
    r = run_simulation(mask, name)
    vol_results[name] = r
    print_result(r, show_levels=False)

# Volatility comparison table
print(f"\n{'VOLATILITY COMPARISON TABLE':^80}")
print(f"{'Filter':<25} {'Cycles':>8} {'Wins':>8} {'Busts':>8} {'P(bust)':>10} {'Net P&L':>12} {'Bust/Win':>10}")
print("-" * 81)
for name, r in vol_results.items():
    print(f"{name:<25} {r['total']:>8,} {r['wins']:>8,} {r['busts']:>8,} "
          f"{r['p_bust']:>10.4f} {r['net_pnl']:>12.2f} {r['bust_erase_ratio']:>10.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 4: COMBINED BEST FILTERS
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ANALYSIS 4: COMBINED BEST FILTERS")
print("=" * 80)

# Find best session (lowest P(bust) with at least 20 cycles)
best_session = None
best_session_pbust = 1.0
for name, r in session_results.items():
    if name == 'Any (unfiltered)':
        continue
    if r['total'] >= 20 and r['p_bust'] < best_session_pbust:
        best_session_pbust = r['p_bust']
        best_session = name

# Find best volatility filter (lowest P(bust) with at least 20 cycles)
best_vol = None
best_vol_pbust = 1.0
for name, r in vol_results.items():
    if name == 'Any (no filter)':
        continue
    if r['total'] >= 20 and r['p_bust'] < best_vol_pbust:
        best_vol_pbust = r['p_bust']
        best_vol = name

print(f"\nBest session filter: {best_session} (P(bust) = {best_session_pbust:.4f})")
print(f"Best volatility filter: {best_vol} (P(bust) = {best_vol_pbust:.4f})")

# Combined filter
combined_configs = []

# Best session + best vol
if best_session and best_vol:
    session_mask = session_filters.get(best_session, mask_all)
    lo, hi = vol_filters[best_vol]
    vol_mask = (signal_atr_pctiles >= lo) & (signal_atr_pctiles <= hi)
    combined_mask = session_mask & vol_mask
    label = f"{best_session} + {best_vol}"
    combined_configs.append((label, combined_mask))

# Also test some explicit combos
explicit_combos = [
    ("London+Overlap+NY + ATR[20-80]",
     np.isin(signal_sessions, ['London', 'Overlap', 'NY']) & (signal_atr_pctiles >= 20) & (signal_atr_pctiles <= 80)),
    ("London+Overlap+NY + ATR[30-70]",
     np.isin(signal_sessions, ['London', 'Overlap', 'NY']) & (signal_atr_pctiles >= 30) & (signal_atr_pctiles <= 70)),
    ("London+Overlap + ATR[20-80]",
     np.isin(signal_sessions, ['London', 'Overlap']) & (signal_atr_pctiles >= 20) & (signal_atr_pctiles <= 80)),
    ("Overlap Only + ATR[20-80]",
     (signal_sessions == 'Overlap') & (signal_atr_pctiles >= 20) & (signal_atr_pctiles <= 80)),
    ("Overlap Only + ATR[30-70]",
     (signal_sessions == 'Overlap') & (signal_atr_pctiles >= 30) & (signal_atr_pctiles <= 70)),
]
combined_configs.extend(explicit_combos)

combined_results = {}
for label, mask in combined_configs:
    print(f"\n--- {label} (signals available: {mask.sum():,}) ---")
    r = run_simulation(mask, label)
    combined_results[label] = r
    print_result(r, show_levels=True)

# Combined comparison table
print(f"\n{'COMBINED FILTER COMPARISON TABLE':^90}")
print(f"{'Filter':<45} {'Cycles':>8} {'Wins':>8} {'Busts':>8} {'P(bust)':>10} {'Net P&L':>12}")
print("-" * 91)
# Include unfiltered baseline
print(f"{'Unfiltered (baseline)':<45} {result_unfiltered['total']:>8,} {result_unfiltered['wins']:>8,} "
      f"{result_unfiltered['busts']:>8,} {result_unfiltered['p_bust']:>10.4f} {result_unfiltered['net_pnl']:>12.2f}")
for label, r in combined_results.items():
    print(f"{label:<45} {r['total']:>8,} {r['wins']:>8,} {r['busts']:>8,} "
          f"{r['p_bust']:>10.4f} {r['net_pnl']:>12.2f}")


# ══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════════════════════

# ─── Chart 1: Session P(bust) bar chart ───────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# Panel 1: Session P(bust)
ax = axes[0]
names = [n for n in session_results if n != 'Any (unfiltered)']
pbusts = [session_results[n]['p_bust'] for n in names]
totals = [session_results[n]['total'] for n in names]
colors = ['#e74c3c' if p > 0.15 else '#f39c12' if p > 0.10 else '#27ae60' for p in pbusts]
bars = ax.bar(range(len(names)), pbusts, color=colors, edgecolor='black', alpha=0.8)
ax.set_xticks(range(len(names)))
ax.set_xticklabels(names, rotation=30, ha='right', fontsize=9)
ax.set_ylabel('P(bust)')
ax.set_title('P(bust) by Session Filter')
for i, (bar, t) in enumerate(zip(bars, totals)):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
            f'n={t}', ha='center', fontsize=8)
ax.axhline(y=result_unfiltered['p_bust'], color='red', linestyle='--', alpha=0.5, label=f'Unfiltered: {result_unfiltered["p_bust"]:.3f}')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3, axis='y')

# Panel 2: Volatility P(bust)
ax = axes[1]
names_v = [n for n in vol_results if n != 'Any (no filter)']
pbusts_v = [vol_results[n]['p_bust'] for n in names_v]
totals_v = [vol_results[n]['total'] for n in names_v]
colors_v = ['#e74c3c' if p > 0.15 else '#f39c12' if p > 0.10 else '#27ae60' for p in pbusts_v]
bars = ax.bar(range(len(names_v)), pbusts_v, color=colors_v, edgecolor='black', alpha=0.8)
ax.set_xticks(range(len(names_v)))
ax.set_xticklabels(names_v, rotation=30, ha='right', fontsize=9)
ax.set_ylabel('P(bust)')
ax.set_title('P(bust) by Volatility Filter')
for i, (bar, t) in enumerate(zip(bars, totals_v)):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
            f'n={t}', ha='center', fontsize=8)
ax.axhline(y=result_unfiltered['p_bust'], color='red', linestyle='--', alpha=0.5, label=f'Unfiltered: {result_unfiltered["p_bust"]:.3f}')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3, axis='y')

# Panel 3: Net P&L comparison
ax = axes[2]
all_results = {'Unfiltered': result_unfiltered}
all_results.update(session_results)
all_results.update(vol_results)
# Only show ones with >= 20 cycles
filtered_names = [n for n, r in all_results.items() if r['total'] >= 20 and n not in ['Any (unfiltered)', 'Any (no filter)']]
net_pnls = [all_results[n]['net_pnl'] for n in filtered_names]
colors_pnl = ['#27ae60' if p > 0 else '#e74c3c' for p in net_pnls]
bars = ax.barh(range(len(filtered_names)), net_pnls, color=colors_pnl, edgecolor='black', alpha=0.8)
ax.set_yticks(range(len(filtered_names)))
ax.set_yticklabels(filtered_names, fontsize=8)
ax.set_xlabel('Net P&L ($)')
ax.set_title('Net P&L by Filter')
ax.axvline(x=0, color='black', linewidth=0.5)
ax.grid(True, alpha=0.3, axis='x')

plt.suptitle('Surefire Hedge V2: Full Cycle Simulation on EUR-USD 5m (2024-01 to 2026-03)',
             fontsize=13, y=1.02)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/05_bust_rate_by_filter.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUTPUT_DIR}/05_bust_rate_by_filter.png")


# ─── Chart 2: Win-level distribution ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))

# Unfiltered level distribution
r = result_unfiltered
levels = list(range(MAX_LEVELS))
level_counts = [r['win_by_level'].get(lv, 0) for lv in levels]
level_counts.append(r['busts'])  # add bust
labels = [f'Win L{lv}' for lv in levels] + ['BUST']
colors_lv = ['#2ecc71', '#27ae60', '#f39c12', '#e67e22', '#e74c3c', '#c0392b']

bars = ax.bar(labels, level_counts, color=colors_lv[:len(labels)], edgecolor='black', alpha=0.8)
for bar, count in zip(bars, level_counts):
    pct = count / r['total'] * 100 if r['total'] > 0 else 0
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
            f'{count}\n({pct:.1f}%)', ha='center', fontsize=9)

ax.set_ylabel('Number of Cycles')
ax.set_title(f'Surefire Hedge Cycle Outcomes (Unfiltered)\n'
             f'Total: {r["total"]} cycles, P(bust) = {r["p_bust"]:.4f} ({r["p_bust"]*100:.2f}%)')
ax.grid(True, alpha=0.3, axis='y')
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/05_bust_rate_level_distribution.png', dpi=150)
plt.close()
print(f"Saved: {OUTPUT_DIR}/05_bust_rate_level_distribution.png")


# ─── Chart 3: Equity curve from cycles ───────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 6))

# Plot cumulative P&L for unfiltered
cum_pnl = np.cumsum([c['total_pnl'] for c in result_unfiltered['cycles']])
cycle_nums = np.arange(1, len(cum_pnl) + 1)

# Color the line segments: green when cumPnL increasing, red when bust
ax.plot(cycle_nums, cum_pnl, 'b-', linewidth=1.0, alpha=0.8, label='Cumulative P&L')

# Mark bust events
bust_indices = [i for i, c in enumerate(result_unfiltered['cycles']) if c['outcome'] == 'bust']
if bust_indices:
    ax.scatter([i+1 for i in bust_indices], [cum_pnl[i] for i in bust_indices],
               color='red', s=80, zorder=5, marker='v', label=f'Bust events ({len(bust_indices)})')

ax.axhline(y=0, color='black', linewidth=0.5)
ax.set_xlabel('Cycle Number')
ax.set_ylabel('Cumulative P&L ($)')
ax.set_title(f'Surefire Hedge V2: Equity Curve (Unfiltered)\n'
             f'{len(result_unfiltered["cycles"])} cycles, {len(bust_indices)} busts, '
             f'Net P&L = ${result_unfiltered["net_pnl"]:,.2f}')
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/05_bust_rate_equity_curve.png', dpi=150)
plt.close()
print(f"Saved: {OUTPUT_DIR}/05_bust_rate_equity_curve.png")


# ─── Chart 4: Combined filters comparison ────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# All configs for comparison
all_configs = {'Unfiltered': result_unfiltered}
all_configs.update(combined_results)
valid_configs = {n: r for n, r in all_configs.items() if r['total'] >= 10}

# Panel 1: P(bust) comparison
ax = axes[0]
names_c = list(valid_configs.keys())
pbusts_c = [valid_configs[n]['p_bust'] for n in names_c]
colors_c = ['#e74c3c' if p > 0.15 else '#f39c12' if p > 0.10 else '#27ae60' for p in pbusts_c]
bars = ax.barh(range(len(names_c)), pbusts_c, color=colors_c, edgecolor='black', alpha=0.8)
ax.set_yticks(range(len(names_c)))
ax.set_yticklabels(names_c, fontsize=8)
ax.set_xlabel('P(bust)')
ax.set_title('P(bust) — Combined Filters')
for i, (bar, n) in enumerate(zip(bars, names_c)):
    t = valid_configs[n]['total']
    ax.text(bar.get_width() + 0.005, bar.get_y() + bar.get_height()/2,
            f'n={t}', va='center', fontsize=8)
ax.grid(True, alpha=0.3, axis='x')

# Panel 2: Net P&L comparison
ax = axes[1]
net_pnls_c = [valid_configs[n]['net_pnl'] for n in names_c]
colors_pnl_c = ['#27ae60' if p > 0 else '#e74c3c' for p in net_pnls_c]
bars = ax.barh(range(len(names_c)), net_pnls_c, color=colors_pnl_c, edgecolor='black', alpha=0.8)
ax.set_yticks(range(len(names_c)))
ax.set_yticklabels(names_c, fontsize=8)
ax.set_xlabel('Net P&L ($)')
ax.set_title('Net P&L — Combined Filters')
ax.axvline(x=0, color='black', linewidth=0.5)
ax.grid(True, alpha=0.3, axis='x')

plt.suptitle('Surefire Hedge V2: Combined Filter Analysis', fontsize=13)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/05_bust_rate_combined.png', dpi=150)
plt.close()
print(f"Saved: {OUTPUT_DIR}/05_bust_rate_combined.png")


# ─── Final Summary ───────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("FINAL SUMMARY")
print("=" * 80)

r = result_unfiltered
print(f"\nUNFILTERED BASELINE:")
print(f"  Total cycles:         {r['total']:,}")
print(f"  Wins:                 {r['wins']:,}  ({r['wins']/r['total']*100:.1f}%)" if r['total'] > 0 else "")
print(f"  Busts:                {r['busts']:,}  ({r['busts']/r['total']*100:.1f}%)" if r['total'] > 0 else "")
print(f"  P(bust):              {r['p_bust']:.4f}")
print(f"  Avg win P&L:          ${r['avg_win_pnl']:.2f}")
print(f"  Avg bust P&L:         ${r['avg_bust_pnl']:.2f}")
print(f"  One bust erases:      {r['bust_erase_ratio']:.1f} winning cycles")
print(f"  Net P&L:              ${r['net_pnl']:,.2f}")

# Find absolute best combined filter
all_tested = {}
all_tested.update(session_results)
all_tested.update(vol_results)
all_tested.update(combined_results)
all_tested['Unfiltered'] = result_unfiltered

print(f"\nBEST FILTER BY P(BUST) (min 20 cycles):")
best = min([(n, r) for n, r in all_tested.items() if r['total'] >= 20],
           key=lambda x: x[1]['p_bust'])
print(f"  {best[0]}")
print(f"  P(bust) = {best[1]['p_bust']:.4f}, Cycles = {best[1]['total']}, Net P&L = ${best[1]['net_pnl']:,.2f}")

print(f"\nBEST FILTER BY NET P&L (min 20 cycles):")
best_pnl = max([(n, r) for n, r in all_tested.items() if r['total'] >= 20],
               key=lambda x: x[1]['net_pnl'])
print(f"  {best_pnl[0]}")
print(f"  Net P&L = ${best_pnl[1]['net_pnl']:,.2f}, P(bust) = {best_pnl[1]['p_bust']:.4f}, Cycles = {best_pnl[1]['total']}")

print(f"\nFILES SAVED:")
print(f"  {OUTPUT_DIR}/05_full_cycle_simulation.py")
print(f"  {OUTPUT_DIR}/05_bust_rate_by_filter.png")
print(f"  {OUTPUT_DIR}/05_bust_rate_level_distribution.png")
print(f"  {OUTPUT_DIR}/05_bust_rate_equity_curve.png")
print(f"  {OUTPUT_DIR}/05_bust_rate_combined.png")
print("=" * 80)
