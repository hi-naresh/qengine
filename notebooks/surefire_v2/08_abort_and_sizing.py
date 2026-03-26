#!/usr/bin/env python3
"""
Step 8: Early Abort & Dynamic Sizing Strategies
================================================
Tests concrete tail-risk mitigations:

1. EARLY ABORT: What if we cap max levels at 3 or 4 instead of 5?
   - Compare equity curves for max_levels = 3, 4, 5, 6, 7
   - At each cap, we take a controlled loss vs risking deeper bust

2. DYNAMIC MULTIPLIER: What if the multiplier shrinks at deeper levels?
   - Standard: 2x, 2x, 2x, 2x → sizes: 1, 2, 4, 8, 16
   - Conservative: 2x, 1.8x, 1.5x, 1.3x → sizes: 1, 2, 3.6, 5.4, 7.0
   - Aggressive: 2x, 2x, 2x, 2x, 2x, 2x → more levels, same mult

3. HYBRID: Best abort level + dynamic sizing combined

4. MARGIN-AWARE: At what balance does each level become unaffordable?
"""

import os, sys
os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timezone
import time

import qengine.indicators as ta
import qengine.helpers as jh
from qengine.research import get_candles

# ─── Parameters ──────────────────────────────────────────────────────────────
TP_ATR_MULTIPLE = 0.8
RISK_REWARD = 2.0
ATR_PERIOD = 14
PIP_SIZE = 0.0001
BASE_SIZE = 0.1
PIP_VALUE = 10.0
MAX_BARS_PER_LEVEL = 500
EMA_FAST = 8
EMA_SLOW = 21
STARTING_BALANCE = 10_000

OUTPUT_DIR = 'notebooks/surefire_v2'

# ─── Load Data ───────────────────────────────────────────────────────────────
print("Loading EUR-USD 5m candles...")
t0 = time.time()
warmup_candles, candles = get_candles('OANDA', 'EUR-USD', '5m',
    jh.date_to_timestamp('2024-01-01'), jh.date_to_timestamp('2026-03-01'),
    warmup_candles_num=210)
if warmup_candles is not None and warmup_candles.ndim == 2 and len(warmup_candles) > 0:
    candles = np.concatenate([warmup_candles, candles], axis=0)

print(f"Total candles: {len(candles):,} ({time.time()-t0:.1f}s)")

timestamps = candles[:, 0]
opens  = candles[:, 1]
closes = candles[:, 2]
highs  = candles[:, 3]
lows   = candles[:, 4]

ema_fast = ta.ema(candles, period=EMA_FAST, sequential=True)
ema_slow = ta.ema(candles, period=EMA_SLOW, sequential=True)
atr_arr  = ta.atr(candles, period=ATR_PERIOD, sequential=True)

# ─── Find signals ────────────────────────────────────────────────────────────
min_start = max(ATR_PERIOD + 5, EMA_SLOW + 5)
signals = []
for i in range(min_start, len(candles) - MAX_BARS_PER_LEVEL):
    if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]) or np.isnan(ema_fast[i-1]) or np.isnan(ema_slow[i-1]):
        continue
    if np.isnan(atr_arr[i]) or atr_arr[i] <= 0:
        continue
    if ema_fast[i-1] <= ema_slow[i-1] and ema_fast[i] > ema_slow[i]:
        signals.append((i, 'long'))
    elif ema_fast[i-1] >= ema_slow[i-1] and ema_fast[i] < ema_slow[i]:
        signals.append((i, 'short'))

print(f"Total signals: {len(signals):,}")

# ─── Level simulator ─────────────────────────────────────────────────────────
def simulate_level(entry_price, direction, tp_dist, hedge_dist, start_bar):
    if direction == 'long':
        tp_price = entry_price + tp_dist
        sl_price = entry_price - hedge_dist
    else:
        tp_price = entry_price - tp_dist
        sl_price = entry_price + hedge_dist

    max_bar = min(start_bar + MAX_BARS_PER_LEVEL, len(highs))
    for j in range(start_bar, max_bar):
        h, l = highs[j], lows[j]
        if direction == 'long':
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


# ─── Configurable cycle simulator ────────────────────────────────────────────
def simulate_cycle(entry_bar, initial_direction, max_levels=5, multipliers=None):
    """
    Simulate a full hedge cycle with configurable max levels and multipliers.

    multipliers: list of floats, size multiplier for each level.
                 e.g., [1.0, 2.0, 4.0, 8.0, 16.0] for standard 2x
                 If None, uses standard 2x doubling.
    """
    if multipliers is None:
        multipliers = [BASE_SIZE * (2.0 ** lvl) for lvl in range(max_levels)]
    else:
        # multipliers here are the SIZE at each level (not the factor)
        pass

    entry_price = closes[entry_bar]
    direction = initial_direction
    current_bar = entry_bar + 1
    total_pnl = 0.0
    level_pnls = []

    for level in range(max_levels):
        current_atr = atr_arr[min(current_bar, len(atr_arr)-1)]
        if np.isnan(current_atr) or current_atr <= 0:
            current_atr = atr_arr[entry_bar]
        if np.isnan(current_atr) or current_atr <= 0:
            return None

        tp_dist = current_atr * TP_ATR_MULTIPLE
        hedge_dist = tp_dist / RISK_REWARD
        size = multipliers[level]
        tp_pips = tp_dist / PIP_SIZE
        sl_pips = hedge_dist / PIP_SIZE

        result = simulate_level(entry_price, direction, tp_dist, hedge_dist, current_bar)

        if result[0] == 'tp':
            profit = tp_pips * PIP_VALUE * size
            total_pnl += profit
            level_pnls.append(profit)
            return {
                'outcome': 'win', 'win_level': level, 'total_pnl': total_pnl,
                'entry_bar': entry_bar, 'end_bar': result[1],
                'level_pnls': level_pnls, 'max_level': level,
                'total_exposure': sum(multipliers[:level+1]),
            }
        elif result[0] == 'sl':
            loss = sl_pips * PIP_VALUE * size
            total_pnl -= loss
            level_pnls.append(-loss)
            entry_price = result[2]
            direction = 'short' if direction == 'long' else 'long'
            current_bar = result[1] + 1
            if current_bar >= len(highs):
                return None
        elif result[0] == 'timeout':
            return None

    # All levels exhausted → bust (or abort)
    return {
        'outcome': 'bust', 'win_level': -1, 'total_pnl': total_pnl,
        'entry_bar': entry_bar, 'end_bar': current_bar,
        'level_pnls': level_pnls, 'max_level': max_levels - 1,
        'total_exposure': sum(multipliers),
    }


def run_config(max_levels, multipliers, label):
    """Run full simulation with a given config."""
    cycles = []
    next_allowed = 0
    for bar, direction in signals:
        if bar < next_allowed:
            continue
        result = simulate_cycle(bar, direction, max_levels=max_levels, multipliers=multipliers)
        if result is None:
            continue
        cycles.append(result)
        next_allowed = result['end_bar'] + 1

    if len(cycles) == 0:
        return {'label': label, 'total': 0, 'wins': 0, 'busts': 0,
                'p_bust': 0, 'net_pnl': 0, 'cycles': []}

    wins = [c for c in cycles if c['outcome'] == 'win']
    busts_list = [c for c in cycles if c['outcome'] == 'bust']
    total = len(cycles)
    net_pnl = sum(c['total_pnl'] for c in cycles)
    avg_win = np.mean([c['total_pnl'] for c in wins]) if wins else 0
    avg_bust = np.mean([c['total_pnl'] for c in busts_list]) if busts_list else 0
    max_exposure = max(c['total_exposure'] for c in cycles)

    # Equity curve
    balance = np.zeros(total + 1)
    balance[0] = STARTING_BALANCE
    for i, c in enumerate(cycles):
        balance[i+1] = balance[i] + c['total_pnl']

    # Max drawdown
    peak = np.maximum.accumulate(balance)
    dd = (balance - peak) / peak * 100
    max_dd = np.min(dd)

    # Profit factor
    gross_profit = sum(c['total_pnl'] for c in wins)
    gross_loss = abs(sum(c['total_pnl'] for c in busts_list))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    return {
        'label': label,
        'total': total,
        'wins': len(wins),
        'busts': len(busts_list),
        'p_bust': len(busts_list) / total,
        'net_pnl': net_pnl,
        'avg_win': avg_win,
        'avg_bust': avg_bust,
        'bust_erase': abs(avg_bust / avg_win) if avg_win > 0 else 0,
        'max_dd_pct': max_dd,
        'profit_factor': pf,
        'max_exposure': max_exposure,
        'balance': balance,
        'cycles': cycles,
    }


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1: VARYING MAX LEVELS (Early Abort)
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TEST 1: EARLY ABORT — Max Levels from 2 to 7")
print("=" * 80)

abort_results = {}
for max_lvl in [2, 3, 4, 5, 6, 7]:
    mults = [BASE_SIZE * (2.0 ** lvl) for lvl in range(max_lvl)]
    label = f"Max {max_lvl} levels"
    r = run_config(max_lvl, mults, label)
    abort_results[max_lvl] = r
    print(f"\n  {label}: {r['total']} cycles, {r['wins']} wins, {r['busts']} busts")
    print(f"    P(bust)={r['p_bust']:.4f}, Net=${r['net_pnl']:,.2f}, PF={r['profit_factor']:.3f}")
    print(f"    Avg win=${r['avg_win']:.2f}, Avg bust=${r['avg_bust']:.2f}, Bust erases {r['bust_erase']:.1f} wins")
    print(f"    Max DD={r['max_dd_pct']:.1f}%, Max exposure={r['max_exposure']:.1f} lots")

# Comparison table
print(f"\n  {'EARLY ABORT COMPARISON':^90}")
print(f"  {'Config':<20} {'Cycles':>8} {'P(bust)':>10} {'Net P&L':>12} {'PF':>8} {'MaxDD%':>8} {'BustErases':>12} {'MaxExposure':>12}")
print(f"  {'-'*90}")
for ml, r in abort_results.items():
    print(f"  {'Max '+str(ml)+' levels':<20} {r['total']:>8} {r['p_bust']:>10.4f} {r['net_pnl']:>12,.2f} "
          f"{r['profit_factor']:>8.3f} {r['max_dd_pct']:>8.1f} {r['bust_erase']:>12.1f} {r['max_exposure']:>12.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2: DYNAMIC MULTIPLIER STRATEGIES
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TEST 2: DYNAMIC MULTIPLIER — Size progression strategies")
print("=" * 80)

# Define multiplier strategies (sizes at each level, not factors)
multiplier_configs = {
    'Standard 2x': [0.1, 0.2, 0.4, 0.8, 1.6],           # 1x, 2x, 4x, 8x, 16x
    'Conservative': [0.1, 0.2, 0.36, 0.54, 0.70],        # 1x, 2x, 3.6x, 5.4x, 7x
    'Aggressive decay': [0.1, 0.2, 0.35, 0.525, 0.656],   # 2x, 1.75x, 1.5x, 1.25x
    'Flat after L2': [0.1, 0.2, 0.4, 0.4, 0.4],           # Double twice then hold
    'Sqrt scaling': [0.1, 0.2, 0.283, 0.346, 0.4],         # sqrt(2) multiplier
    'Linear': [0.1, 0.2, 0.3, 0.4, 0.5],                   # linear growth
    'All-in L0-L2 only': [0.1, 0.2, 0.4, 0.0001, 0.0001], # Effectively 3 levels but keep structure
}

sizing_results = {}
for name, mults in multiplier_configs.items():
    r = run_config(5, mults, name)
    sizing_results[name] = r
    total_mult = sum(m / BASE_SIZE for m in mults)
    print(f"\n  {name}: sizes={[f'{m:.3f}' for m in mults]}")
    print(f"    {r['total']} cycles, P(bust)={r['p_bust']:.4f}, Net=${r['net_pnl']:,.2f}")
    print(f"    PF={r['profit_factor']:.3f}, MaxDD={r['max_dd_pct']:.1f}%, Bust erases {r['bust_erase']:.1f} wins")

# Comparison table
print(f"\n  {'DYNAMIC SIZING COMPARISON':^100}")
print(f"  {'Strategy':<22} {'Sizes':<30} {'P(bust)':>8} {'Net P&L':>10} {'PF':>6} {'MaxDD%':>8} {'BustErases':>10}")
print(f"  {'-'*94}")
for name, r in sizing_results.items():
    mults = multiplier_configs[name]
    sizes_str = ','.join(f'{m/BASE_SIZE:.1f}x' for m in mults)
    print(f"  {name:<22} {sizes_str:<30} {r['p_bust']:>8.4f} {r['net_pnl']:>10,.0f} "
          f"{r['profit_factor']:>6.3f} {r['max_dd_pct']:>8.1f} {r['bust_erase']:>10.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3: HYBRID — Best abort + best sizing
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TEST 3: HYBRID STRATEGIES — Combining abort level + sizing")
print("=" * 80)

hybrid_configs = {
    'Baseline (5 lvl, 2x)': (5, [0.1, 0.2, 0.4, 0.8, 1.6]),
    '4 lvl + 2x': (4, [0.1, 0.2, 0.4, 0.8]),
    '4 lvl + conservative': (4, [0.1, 0.2, 0.36, 0.54]),
    '4 lvl + sqrt': (4, [0.1, 0.2, 0.283, 0.346]),
    '4 lvl + linear': (4, [0.1, 0.2, 0.3, 0.4]),
    '3 lvl + 2x': (3, [0.1, 0.2, 0.4]),
    '3 lvl + conservative': (3, [0.1, 0.2, 0.36]),
    '6 lvl + sqrt': (6, [0.1, 0.2, 0.283, 0.346, 0.4, 0.448]),
    '6 lvl + linear': (6, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]),
    '7 lvl + sqrt': (7, [0.1, 0.2, 0.283, 0.346, 0.4, 0.448, 0.490]),
}

hybrid_results = {}
for name, (ml, mults) in hybrid_configs.items():
    r = run_config(ml, mults, name)
    hybrid_results[name] = r

print(f"\n  {'HYBRID COMPARISON':^110}")
print(f"  {'Config':<25} {'Levels':>6} {'Cycles':>7} {'P(bust)':>8} {'Net P&L':>10} {'PF':>6} "
      f"{'MaxDD%':>8} {'BustErases':>10} {'MaxExp':>8}")
print(f"  {'-'*98}")
for name, r in hybrid_results.items():
    ml = hybrid_configs[name][0]
    print(f"  {name:<25} {ml:>6} {r['total']:>7} {r['p_bust']:>8.4f} {r['net_pnl']:>10,.0f} "
          f"{r['profit_factor']:>6.3f} {r['max_dd_pct']:>8.1f} {r['bust_erase']:>10.1f} {r['max_exposure']:>8.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4: MARGIN ANALYSIS — What balance is needed for each level?
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TEST 4: MARGIN ANALYSIS — Required balance per level")
print("=" * 80)

# Typical EUR-USD margin requirement: ~5% (20:1 leverage) or ~3.33% (30:1)
# Per lot margin = price * 100,000 * margin_rate
avg_price = np.mean(closes[~np.isnan(closes)])
print(f"\n  Avg EUR-USD price: {avg_price:.5f}")

for leverage in [20, 30, 50]:
    margin_rate = 1 / leverage
    print(f"\n  {'='*60}")
    print(f"  Leverage: {leverage}:1 (margin rate: {margin_rate*100:.2f}%)")
    print(f"  {'Level':<8} {'Size (lots)':<14} {'Margin Required':<18} {'Cumulative Margin':<20} {'+ Max Loss':<14}")
    print(f"  {'-'*72}")

    cum_margin = 0
    cum_max_loss = 0
    for lvl in range(7):
        size = BASE_SIZE * (2.0 ** lvl)
        margin = avg_price * size * 100_000 * margin_rate
        cum_margin += margin

        # Max loss at this level: hedge_dist * size * pip_value
        avg_atr = np.nanmean(atr_arr[ATR_PERIOD:])
        tp_dist = avg_atr * TP_ATR_MULTIPLE
        hedge_dist = tp_dist / RISK_REWARD
        level_loss = hedge_dist / PIP_SIZE * PIP_VALUE * size
        cum_max_loss += level_loss

        total_needed = cum_margin + cum_max_loss
        print(f"  L{lvl:<7} {size:<14.2f} ${margin:<17,.2f} ${cum_margin:<19,.2f} ${total_needed:<13,.2f}")

    print(f"\n  To safely run all levels, need: ${cum_margin + cum_max_loss:,.2f} minimum balance")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 5: RISK-ADJUSTED COMPARISON — Sharpe-like metric
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TEST 5: RISK-ADJUSTED METRICS")
print("=" * 80)

all_configs = {}
all_configs.update(abort_results)
all_configs.update({f'sizing_{k}': v for k, v in sizing_results.items()})
all_configs.update({f'hybrid_{k}': v for k, v in hybrid_results.items()})

print(f"\n  {'Config':<35} {'Net P&L':>10} {'MaxDD%':>8} {'Calmar':>8} {'PF':>8} {'P(bust)':>8} {'Score':>8}")
print(f"  {'-'*88}")

scored = []
for key, r in all_configs.items():
    if r['total'] < 50:
        continue
    label = r['label'] if 'label' in r else str(key)
    # Calmar-like ratio: Net P&L / Max DD
    max_dd_abs = abs(r['max_dd_pct']) if r['max_dd_pct'] < 0 else 0.01
    calmar = r['net_pnl'] / (max_dd_abs * STARTING_BALANCE / 100) if max_dd_abs > 0.01 else 0

    # Composite score: reward P&L and PF, penalize bust rate and drawdown
    score = (r['profit_factor'] * 10 +
             max(0, r['net_pnl']) / 1000 -
             r['p_bust'] * 50 -
             abs(r['max_dd_pct']) * 0.5)

    scored.append((label, r, calmar, score))
    print(f"  {label:<35} {r['net_pnl']:>10,.0f} {r['max_dd_pct']:>8.1f} {calmar:>8.2f} "
          f"{r['profit_factor']:>8.3f} {r['p_bust']:>8.4f} {score:>8.1f}")

# Best by score
scored.sort(key=lambda x: x[3], reverse=True)
print(f"\n  TOP 5 BY COMPOSITE SCORE:")
for i, (label, r, calmar, score) in enumerate(scored[:5]):
    print(f"  #{i+1}: {label} (score={score:.1f}, PF={r['profit_factor']:.3f}, P(bust)={r['p_bust']:.4f})")


# ══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════════════════════
plt.style.use('seaborn-v0_8-darkgrid')

# ─── Chart 1: Early abort equity curves ──────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(18, 14))

# Panel 1: Equity curves for different max levels
ax = axes[0, 0]
colors_abort = ['#95a5a6', '#f39c12', '#e74c3c', '#2ecc71', '#3498db', '#9b59b6']
for i, (ml, r) in enumerate(abort_results.items()):
    bal = r['balance']
    ax.plot(range(len(bal)), bal, label=f'Max {ml} levels (PF={r["profit_factor"]:.2f})',
            color=colors_abort[i], linewidth=1.5 if ml == 5 else 1.0,
            linestyle='-' if ml >= 4 else '--')
ax.axhline(y=STARTING_BALANCE, color='gray', linestyle=':', alpha=0.5)
ax.set_xlabel('Cycle #')
ax.set_ylabel('Balance ($)')
ax.set_title('Equity Curves: Early Abort at Different Levels', fontweight='bold')
ax.legend(fontsize=8, loc='upper left')

# Panel 2: P(bust) vs Max Levels
ax = axes[0, 1]
ml_keys = sorted(abort_results.keys())
pbusts = [abort_results[ml]['p_bust'] * 100 for ml in ml_keys]
net_pnls = [abort_results[ml]['net_pnl'] for ml in ml_keys]

ax2 = ax.twinx()
bars = ax.bar(ml_keys, pbusts, color='#e74c3c', alpha=0.7, edgecolor='black', label='P(bust) %')
line = ax2.plot(ml_keys, net_pnls, 'bo-', linewidth=2, markersize=8, label='Net P&L')
ax.set_xlabel('Max Levels')
ax.set_ylabel('P(bust) %', color='red')
ax2.set_ylabel('Net P&L ($)', color='blue')
ax.set_title('P(bust) vs Net P&L by Max Levels', fontweight='bold')
ax.legend(loc='upper left')
ax2.legend(loc='upper right')

# Panel 3: Dynamic sizing equity curves
ax = axes[1, 0]
sizing_colors = plt.cm.Set2(np.linspace(0, 1, len(sizing_results)))
for i, (name, r) in enumerate(sizing_results.items()):
    bal = r['balance']
    lw = 2.0 if name == 'Standard 2x' else 1.0
    ax.plot(range(len(bal)), bal, label=f'{name} (PF={r["profit_factor"]:.2f})',
            color=sizing_colors[i], linewidth=lw)
ax.axhline(y=STARTING_BALANCE, color='gray', linestyle=':', alpha=0.5)
ax.set_xlabel('Cycle #')
ax.set_ylabel('Balance ($)')
ax.set_title('Equity Curves: Dynamic Sizing Strategies', fontweight='bold')
ax.legend(fontsize=7, loc='upper left')

# Panel 4: Bust severity comparison (avg bust loss)
ax = axes[1, 1]
# Compare bust severity across all configs
configs_for_compare = []
for name, r in hybrid_results.items():
    if r['busts'] > 0:
        configs_for_compare.append((name, r['avg_bust'], r['bust_erase'], r['p_bust']))

configs_for_compare.sort(key=lambda x: x[1])  # sort by avg bust (most negative first)
names_c = [c[0] for c in configs_for_compare]
bust_losses = [c[1] for c in configs_for_compare]
bust_erases = [c[2] for c in configs_for_compare]

y_pos = range(len(names_c))
bars = ax.barh(y_pos, bust_losses, color='#e74c3c', edgecolor='black', alpha=0.8)
for i, (bar, erase) in enumerate(zip(bars, bust_erases)):
    ax.text(bar.get_width() - 0.5, bar.get_y() + bar.get_height()/2,
            f'erases {erase:.0f} wins', va='center', ha='right', fontsize=8, color='white', fontweight='bold')
ax.set_yticks(y_pos)
ax.set_yticklabels(names_c, fontsize=8)
ax.set_xlabel('Average Bust Loss ($)')
ax.set_title('Bust Severity by Strategy', fontweight='bold')
ax.axvline(x=0, color='black', linewidth=0.5)

plt.suptitle('Surefire V2: Abort & Sizing Strategies — EUR-USD 5m (2024-2026)',
             fontsize=14, fontweight='bold', y=1.01)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/08_abort_sizing.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUTPUT_DIR}/08_abort_sizing.png")


# ─── Chart 2: Risk-adjusted scatter ──────────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 8))

for label, r, calmar, score in scored:
    color = '#2ecc71' if score > 10 else '#f39c12' if score > 0 else '#e74c3c'
    size = max(20, min(200, abs(r['net_pnl']) / 50))
    ax.scatter(r['p_bust'] * 100, r['net_pnl'], s=size, color=color, edgecolors='black',
               alpha=0.8, linewidth=0.5)
    ax.annotate(label, (r['p_bust'] * 100, r['net_pnl']), fontsize=7,
                xytext=(5, 5), textcoords='offset points')

ax.axhline(y=0, color='black', linestyle=':', alpha=0.5)
ax.set_xlabel('P(bust) %', fontsize=12)
ax.set_ylabel('Net P&L ($)', fontsize=12)
ax.set_title('Risk vs Return: All Strategy Configurations\n(size = magnitude of P&L, green = good score)',
             fontsize=13, fontweight='bold')
ax.grid(True, alpha=0.3)

plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/08_risk_return_scatter.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/08_risk_return_scatter.png")


# ─── Chart 3: Best hybrid equity curves ──────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(18, 7))

# Top 5 hybrids
ax = axes[0]
top5 = scored[:5]
for i, (label, r, calmar, score) in enumerate(top5):
    bal = r['balance']
    ax.plot(range(len(bal)), bal, label=f'{label}', linewidth=1.5)
# Also show baseline
baseline = abort_results.get(5)
if baseline:
    ax.plot(range(len(baseline['balance'])), baseline['balance'],
            label='Baseline (5 lvl, 2x)', color='gray', linestyle='--', linewidth=1)
ax.axhline(y=STARTING_BALANCE, color='gray', linestyle=':', alpha=0.3)
ax.set_xlabel('Cycle #')
ax.set_ylabel('Balance ($)')
ax.set_title('Top 5 Strategies by Composite Score', fontweight='bold')
ax.legend(fontsize=8)

# Drawdown comparison
ax = axes[1]
for i, (label, r, calmar, score) in enumerate(top5):
    bal = r['balance']
    peak = np.maximum.accumulate(bal)
    dd_pct = (bal - peak) / peak * 100
    ax.plot(range(len(dd_pct)), dd_pct, label=f'{label}', linewidth=1.2)
ax.set_xlabel('Cycle #')
ax.set_ylabel('Drawdown %')
ax.set_title('Drawdown Comparison — Top 5 Strategies', fontweight='bold')
ax.legend(fontsize=8)
ax.set_ylim(None, 5)

plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/08_best_strategies.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/08_best_strategies.png")


print("\n" + "=" * 80)
print("COMPLETE — All abort and sizing strategies tested.")
print("=" * 80)
