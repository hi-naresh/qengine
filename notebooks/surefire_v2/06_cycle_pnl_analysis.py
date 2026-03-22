#!/usr/bin/env python3
"""
Step 6: Surefire Hedge Cycle P&L Distribution Analysis
======================================================
Simulates complete surefire hedge cycles on real EUR-USD 5m price data.
Shows exactly how one bust erases many winning cycles.
"""

import os, sys
os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import qengine.indicators as ta
import qengine.helpers as jh
from qengine.research import get_candles
from dataclasses import dataclass, field
from typing import List, Optional

# ─── Parameters ───────────────────────────────────────────────────────────────
TP_ATR_MULTIPLE = 0.8
RISK_REWARD = 2.0        # hedge_dist = tp_dist / RISK_REWARD
MULTIPLIER = 2.0
MAX_LEVELS = 5            # levels 0..4
ATR_PERIOD = 14
BASE_SIZE = 0.1           # lots
PIP_VALUE_PER_LOT = 10.0  # USD per pip per standard lot
STARTING_BALANCE = 10_000
EMA_FAST = 8
EMA_SLOW = 21

OUTPUT_DIR = 'notebooks/surefire_v2'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Load Data ────────────────────────────────────────────────────────────────
print("Loading candle data...")
warmup_candles, candles = get_candles('OANDA', 'EUR-USD', '5m',
    jh.date_to_timestamp('2024-01-01'), jh.date_to_timestamp('2026-03-01'),
    warmup_candles_num=210)
if warmup_candles is not None and warmup_candles.ndim == 2 and len(warmup_candles) > 0:
    candles = np.concatenate([warmup_candles, candles], axis=0)

print(f"Total candles: {len(candles)}")
print(f"Date range: {jh.timestamp_to_date(candles[0][0])} to {jh.timestamp_to_date(candles[-1][0])}")

# Candle format: [timestamp, open, close, high, low, volume]
timestamps = candles[:, 0]
opens  = candles[:, 1]
closes = candles[:, 2]
highs  = candles[:, 3]
lows   = candles[:, 4]

# ─── Indicators ───────────────────────────────────────────────────────────────
print("Computing indicators...")
atr = ta.atr(candles, period=ATR_PERIOD, sequential=True)
ema_fast = ta.ema(candles, period=EMA_FAST, sequential=True)
ema_slow = ta.ema(candles, period=EMA_SLOW, sequential=True)

# ─── Find EMA crossover signals ──────────────────────────────────────────────
def find_crossover_signals(ema_f, ema_s):
    """Find EMA crossover events. Returns list of (bar_index, direction)."""
    signals = []
    for i in range(1, len(ema_f)):
        if np.isnan(ema_f[i]) or np.isnan(ema_s[i]):
            continue
        if np.isnan(ema_f[i-1]) or np.isnan(ema_s[i-1]):
            continue
        # Bullish crossover
        if ema_f[i-1] <= ema_s[i-1] and ema_f[i] > ema_s[i]:
            signals.append((i, 'long'))
        # Bearish crossover
        elif ema_f[i-1] >= ema_s[i-1] and ema_f[i] < ema_s[i]:
            signals.append((i, 'short'))
    return signals

signals = find_crossover_signals(ema_fast, ema_slow)
print(f"Total EMA crossover signals: {len(signals)}")

# ─── Cycle Data Structure ────────────────────────────────────────────────────
@dataclass
class CycleResult:
    entry_bar: int
    exit_bar: int
    max_level_reached: int
    cycle_pnl: float
    direction: str
    duration_bars: int
    is_bust: bool
    level_losses: List[float] = field(default_factory=list)
    win_profit: float = 0.0

# ─── Simulate a single hedge level ───────────────────────────────────────────
def simulate_level(bar_idx, direction, size, tp_dist, hedge_dist):
    """
    Simulate one level of the hedge from bar_idx.
    Returns (outcome, exit_bar) where outcome is 'win' or 'loss'.

    For a LONG entry at close[bar_idx]:
      TP = entry + tp_dist, SL = entry - hedge_dist
    For a SHORT entry at close[bar_idx]:
      TP = entry - tp_dist, SL = entry + hedge_dist

    Walk forward bar-by-bar checking if high/low hits TP or SL.
    """
    entry_price = closes[bar_idx]

    if direction == 'long':
        tp_price = entry_price + tp_dist
        sl_price = entry_price - hedge_dist
    else:  # short
        tp_price = entry_price - tp_dist
        sl_price = entry_price + hedge_dist

    for i in range(bar_idx + 1, len(candles)):
        h = highs[i]
        l = lows[i]

        if direction == 'long':
            # Check SL first (conservative: assume worst case)
            if l <= sl_price:
                return ('loss', i)
            if h >= tp_price:
                return ('win', i)
        else:  # short
            if h >= sl_price:
                return ('loss', i)
            if l <= tp_price:
                return ('win', i)

    # Ran out of data
    return ('timeout', len(candles) - 1)

# ─── Simulate complete cycles ────────────────────────────────────────────────
def simulate_cycles(signals):
    """Run sequential surefire hedge cycles on real data."""
    cycles = []
    next_available_bar = 0

    for sig_bar, sig_dir in signals:
        if sig_bar < next_available_bar:
            continue  # skip overlapping
        if sig_bar < ATR_PERIOD + EMA_SLOW + 5:
            continue  # need enough warmup

        current_atr = atr[sig_bar]
        if np.isnan(current_atr) or current_atr <= 0:
            continue

        # Start cycle
        entry_bar = sig_bar
        current_bar = sig_bar
        current_dir = sig_dir
        current_size = BASE_SIZE
        level_losses = []
        max_level = 0
        is_bust = False
        win_profit = 0.0

        for level in range(MAX_LEVELS):
            max_level = level

            # Compute distances from ATR at current bar
            local_atr = atr[current_bar]
            if np.isnan(local_atr) or local_atr <= 0:
                local_atr = current_atr  # fallback

            tp_dist = local_atr * TP_ATR_MULTIPLE
            hedge_dist = tp_dist / RISK_REWARD

            outcome, exit_bar = simulate_level(current_bar, current_dir, current_size, tp_dist, hedge_dist)

            if outcome == 'timeout':
                # Treat as loss for incomplete data
                loss_amount = hedge_dist * PIP_VALUE_PER_LOT * current_size * 10000  # convert price dist to pips
                level_losses.append(loss_amount)
                is_bust = True
                current_bar = exit_bar
                break

            if outcome == 'win':
                win_profit = tp_dist * PIP_VALUE_PER_LOT * current_size * 10000
                current_bar = exit_bar
                break

            if outcome == 'loss':
                loss_amount = hedge_dist * PIP_VALUE_PER_LOT * current_size * 10000
                level_losses.append(loss_amount)
                current_bar = exit_bar

                # Prepare next level: opposite direction, multiplied size
                current_dir = 'short' if current_dir == 'long' else 'long'
                current_size *= MULTIPLIER

                if level == MAX_LEVELS - 1:
                    is_bust = True

        total_loss = sum(level_losses)
        cycle_pnl = win_profit - total_loss

        cycle = CycleResult(
            entry_bar=entry_bar,
            exit_bar=current_bar,
            max_level_reached=max_level,
            cycle_pnl=cycle_pnl,
            direction=sig_dir,
            duration_bars=current_bar - entry_bar,
            is_bust=is_bust,
            level_losses=level_losses,
            win_profit=win_profit,
        )
        cycles.append(cycle)
        next_available_bar = current_bar + 1

    return cycles

print("\nSimulating surefire hedge cycles on real price data...")
cycles = simulate_cycles(signals)
print(f"Total completed cycles: {len(cycles)}")

if len(cycles) == 0:
    print("ERROR: No cycles simulated. Exiting.")
    sys.exit(1)

# ─── Extract arrays ──────────────────────────────────────────────────────────
pnls = np.array([c.cycle_pnl for c in cycles])
levels = np.array([c.max_level_reached for c in cycles])
is_bust = np.array([c.is_bust for c in cycles])
durations = np.array([c.duration_bars for c in cycles])
directions = np.array([c.direction for c in cycles])

# ─── Equity curve ────────────────────────────────────────────────────────────
balance = np.zeros(len(cycles) + 1)
balance[0] = STARTING_BALANCE
for i, c in enumerate(cycles):
    balance[i + 1] = balance[i] + c.cycle_pnl

# ─── Analysis ────────────────────────────────────────────────────────────────

print("\n" + "=" * 80)
print("  SUREFIRE HEDGE V2 -- CYCLE P&L DISTRIBUTION ANALYSIS")
print("  Real Data: EUR-USD 5m | EMA(8)/EMA(21) Crossover Entries")
print("=" * 80)

# --- Key Summary Stats ---
n_cycles = len(cycles)
n_wins = np.sum(~is_bust)
n_busts = np.sum(is_bust)
win_rate = n_wins / n_cycles * 100
total_pnl = np.sum(pnls)
gross_profit = np.sum(pnls[pnls > 0])
gross_loss = np.abs(np.sum(pnls[pnls < 0]))
profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

# Consecutive wins/losses
max_consec_wins = 0
max_consec_losses = 0
curr_wins = 0
curr_losses = 0
for c in cycles:
    if not c.is_bust:
        curr_wins += 1
        curr_losses = 0
        max_consec_wins = max(max_consec_wins, curr_wins)
    else:
        curr_losses += 1
        curr_wins = 0
        max_consec_losses = max(max_consec_losses, curr_losses)

print("\n--- KEY SUMMARY STATS ---")
print(f"  Total cycles:            {n_cycles}")
print(f"  Winning cycles:          {n_wins} ({win_rate:.1f}%)")
print(f"  Bust cycles:             {n_busts} ({100-win_rate:.1f}%)")
print(f"  Total P&L:               ${total_pnl:,.2f}")
print(f"  Gross Profit:            ${gross_profit:,.2f}")
print(f"  Gross Loss:              ${gross_loss:,.2f}")
print(f"  Profit Factor:           {profit_factor:.3f}")
print(f"  Starting Balance:        ${STARTING_BALANCE:,.2f}")
print(f"  Final Balance:           ${balance[-1]:,.2f}")
print(f"  Return:                  {(balance[-1]/STARTING_BALANCE - 1)*100:.1f}%")
print(f"  Largest Single Gain:     ${np.max(pnls):,.2f}")
print(f"  Largest Single Loss:     ${np.min(pnls):,.2f}")
print(f"  Max Consecutive Wins:    {max_consec_wins}")
print(f"  Max Consecutive Losses:  {max_consec_losses}")
print(f"  Avg Duration (bars):     {np.mean(durations):.1f}")

# --- Level Distribution ---
print("\n--- LEVEL DISTRIBUTION ---")
print(f"  {'Level':<8} {'Count':<8} {'Pct':<8} {'Outcome'}")
print(f"  {'-----':<8} {'-----':<8} {'---':<8} {'-------'}")
for lvl in range(MAX_LEVELS):
    # Wins at this level
    win_at_lvl = np.sum((levels == lvl) & (~is_bust))
    # Busts that reached this level as their final
    bust_at_lvl = np.sum((levels == lvl) & (is_bust))
    if win_at_lvl > 0:
        print(f"  L{lvl:<7} {win_at_lvl:<8} {win_at_lvl/n_cycles*100:<7.1f}% WIN")
    if bust_at_lvl > 0:
        print(f"  L{lvl:<7} {bust_at_lvl:<8} {bust_at_lvl/n_cycles*100:<7.1f}% BUST")

# --- Win vs Bust Math ---
print("\n--- WIN vs BUST MATH ---")
print(f"\n  Average P&L by resolution level:")
print(f"  {'Level':<8} {'Avg P&L':<14} {'Count':<8} {'Avg Win Profit':<16} {'Avg Cum Loss'}")
print(f"  {'-----':<8} {'-------':<14} {'-----':<8} {'--------------':<16} {'------------'}")

avg_win_by_level = {}
for lvl in range(MAX_LEVELS):
    mask_win = (levels == lvl) & (~is_bust)
    if np.sum(mask_win) > 0:
        avg_pnl = np.mean(pnls[mask_win])
        avg_win_by_level[lvl] = avg_pnl

        # Get avg win profit and avg cum loss for these cycles
        win_cycles_at_lvl = [c for c in cycles if c.max_level_reached == lvl and not c.is_bust]
        avg_wp = np.mean([c.win_profit for c in win_cycles_at_lvl])
        avg_cl = np.mean([sum(c.level_losses) for c in win_cycles_at_lvl])
        print(f"  L{lvl} WIN  ${avg_pnl:<13,.2f} {np.sum(mask_win):<8} ${avg_wp:<15,.2f} ${avg_cl:,.2f}")

# Bust average
if n_busts > 0:
    avg_bust = np.mean(pnls[is_bust])
    bust_cycles = [c for c in cycles if c.is_bust]
    avg_bust_loss = np.mean([sum(c.level_losses) for c in bust_cycles])
    print(f"  BUST    ${avg_bust:<13,.2f} {n_busts:<8} ${'N/A':<15} ${avg_bust_loss:,.2f}")

# Recovery table
print(f"\n  --- HOW MANY WINS TO RECOVER ONE BUST? ---")
if n_busts > 0:
    print(f"  Average bust loss: ${abs(avg_bust):,.2f}")
    print(f"  {'Win Level':<12} {'Avg Win P&L':<14} {'Wins to Recover 1 Bust'}")
    print(f"  {'---------':<12} {'-----------':<14} {'----------------------'}")
    for lvl, avg_w in sorted(avg_win_by_level.items()):
        if avg_w > 0:
            n_to_recover = abs(avg_bust) / avg_w
            print(f"  L{lvl} win     ${avg_w:<13,.2f} {n_to_recover:.1f}")

    # Overall average win
    if n_wins > 0:
        avg_win_all = np.mean(pnls[~is_bust])
        n_to_recover_all = abs(avg_bust) / avg_win_all if avg_win_all > 0 else float('inf')
        print(f"  {'All wins':<12} ${avg_win_all:<13,.2f} {n_to_recover_all:.1f}")
        print(f"\n  >>> ONE BUST ERASES {n_to_recover_all:.0f} AVERAGE WINNING CYCLES <<<")
else:
    print("  No busts occurred in this sample.")

# --- Drawdown Analysis ---
print("\n--- DRAWDOWN ANALYSIS ---")
running_max = np.maximum.accumulate(balance)
drawdown = balance - running_max
drawdown_pct = drawdown / running_max * 100

max_dd_idx = np.argmin(drawdown)
max_dd = drawdown[max_dd_idx]
max_dd_pct = drawdown_pct[max_dd_idx]
peak_before = running_max[max_dd_idx]

# Find recovery point after max drawdown
recovery_bar = None
for i in range(max_dd_idx, len(balance)):
    if balance[i] >= running_max[max_dd_idx]:
        recovery_bar = i
        break

# Find longest drawdown duration
dd_start = None
max_dd_duration = 0
for i in range(len(drawdown)):
    if drawdown[i] < 0:
        if dd_start is None:
            dd_start = i
    else:
        if dd_start is not None:
            duration = i - dd_start
            max_dd_duration = max(max_dd_duration, duration)
            dd_start = None

print(f"  Max Drawdown:            ${abs(max_dd):,.2f} ({abs(max_dd_pct):.1f}%)")
print(f"  Peak Balance Before:     ${peak_before:,.2f}")
print(f"  Trough Balance:          ${balance[max_dd_idx]:,.2f}")
if recovery_bar:
    print(f"  Recovery after:          {recovery_bar - max_dd_idx} cycles")
else:
    print(f"  Recovery:                NEVER RECOVERED")
print(f"  Longest DD Duration:     {max_dd_duration} cycles")

# Count bust events and their impact
if n_busts > 0:
    print(f"\n  Bust events and their drawdown impact:")
    bust_indices = [i for i, c in enumerate(cycles) if c.is_bust]
    for bi in bust_indices:
        dd_at = drawdown[bi + 1]
        dd_pct_at = drawdown_pct[bi + 1]
        print(f"    Cycle #{bi}: P&L = ${cycles[bi].cycle_pnl:,.2f}, "
              f"Balance after = ${balance[bi+1]:,.2f}, "
              f"Drawdown = ${abs(dd_at):,.2f} ({abs(dd_pct_at):.1f}%)")


# ═══════════════════════════════════════════════════════════════════════════════
#  CHARTS
# ═══════════════════════════════════════════════════════════════════════════════
plt.style.use('seaborn-v0_8-darkgrid')

# --- Chart 1: P&L Distribution Histogram ---
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# Left: full histogram
ax = axes[0]
win_pnls = pnls[~is_bust]
bust_pnls = pnls[is_bust]

# Determine bins
all_min = np.min(pnls)
all_max = np.max(pnls)
bins = np.linspace(all_min, all_max, 50)

ax.hist(win_pnls, bins=bins, color='#2ecc71', alpha=0.8, label=f'Wins (n={len(win_pnls)})', edgecolor='black', linewidth=0.5)
if len(bust_pnls) > 0:
    ax.hist(bust_pnls, bins=bins, color='#e74c3c', alpha=0.8, label=f'Busts (n={len(bust_pnls)})', edgecolor='black', linewidth=0.5)
ax.axvline(x=0, color='black', linestyle='--', alpha=0.7)
ax.set_xlabel('Cycle P&L ($)', fontsize=12)
ax.set_ylabel('Frequency', fontsize=12)
ax.set_title('Cycle P&L Distribution -- Full Range', fontsize=13, fontweight='bold')
ax.legend(fontsize=10)

# Right: zoomed on wins with bust annotation
ax = axes[1]
if len(win_pnls) > 0:
    win_bins = np.linspace(np.min(win_pnls), np.max(win_pnls), 30)
    ax.hist(win_pnls, bins=win_bins, color='#2ecc71', alpha=0.8, edgecolor='black', linewidth=0.5)
ax.set_xlabel('Cycle P&L ($)', fontsize=12)
ax.set_ylabel('Frequency', fontsize=12)
ax.set_title('Winning Cycles P&L (zoomed)', fontsize=13, fontweight='bold')

# Annotate with bust info
if n_busts > 0:
    textstr = (f'Avg Win: ${np.mean(win_pnls):,.2f}\n'
               f'Avg Bust: ${np.mean(bust_pnls):,.2f}\n'
               f'1 Bust = {abs(np.mean(bust_pnls))/np.mean(win_pnls):.0f} wins')
    ax.text(0.97, 0.97, textstr, transform=ax.transAxes, fontsize=11,
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='#fadbd8', alpha=0.9))

plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'results/06_pnl_distribution.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUTPUT_DIR}/06_pnl_distribution.png")

# --- Chart 2: Equity Curve ---
fig, axes = plt.subplots(2, 1, figsize=(16, 10), gridspec_kw={'height_ratios': [3, 1]})

ax = axes[0]
cycle_indices = np.arange(len(balance))
ax.plot(cycle_indices, balance, color='#2c3e50', linewidth=1.5, label='Balance')
ax.fill_between(cycle_indices, STARTING_BALANCE, balance,
                where=balance >= STARTING_BALANCE, color='#2ecc71', alpha=0.2)
ax.fill_between(cycle_indices, STARTING_BALANCE, balance,
                where=balance < STARTING_BALANCE, color='#e74c3c', alpha=0.2)

# Mark bust events
bust_cycle_indices = [i for i, c in enumerate(cycles) if c.is_bust]
for bi in bust_cycle_indices:
    ax.axvline(x=bi+1, color='red', alpha=0.4, linestyle='--', linewidth=0.8)
    ax.scatter(bi+1, balance[bi+1], color='red', s=60, zorder=5, marker='v')

ax.axhline(y=STARTING_BALANCE, color='gray', linestyle=':', alpha=0.5)
ax.set_ylabel('Balance ($)', fontsize=12)
ax.set_title('Equity Curve -- Surefire Hedge V2 on Real EUR-USD 5m Data', fontsize=14, fontweight='bold')
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)

# Drawdown subplot
ax2 = axes[1]
ax2.fill_between(cycle_indices, 0, drawdown_pct, color='#e74c3c', alpha=0.5)
ax2.set_xlabel('Cycle #', fontsize=12)
ax2.set_ylabel('Drawdown (%)', fontsize=12)
ax2.set_title('Drawdown', fontsize=12)
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'results/06_equity_curve.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/06_equity_curve.png")

# --- Chart 3: Level Distribution ---
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Left: bar chart of resolution levels
ax = axes[0]
level_counts_win = []
level_counts_bust = []
level_labels = []
for lvl in range(MAX_LEVELS):
    w = np.sum((levels == lvl) & (~is_bust))
    b = np.sum((levels == lvl) & (is_bust))
    level_counts_win.append(w)
    level_counts_bust.append(b)
    level_labels.append(f'L{lvl}')

x = np.arange(MAX_LEVELS)
width = 0.35
bars1 = ax.bar(x - width/2, level_counts_win, width, label='Win', color='#2ecc71', edgecolor='black', linewidth=0.5)
bars2 = ax.bar(x + width/2, level_counts_bust, width, label='Bust', color='#e74c3c', edgecolor='black', linewidth=0.5)

# Add count labels on bars
for bar in bars1:
    h = bar.get_height()
    if h > 0:
        ax.text(bar.get_x() + bar.get_width()/2., h, f'{int(h)}',
                ha='center', va='bottom', fontsize=9)
for bar in bars2:
    h = bar.get_height()
    if h > 0:
        ax.text(bar.get_x() + bar.get_width()/2., h, f'{int(h)}',
                ha='center', va='bottom', fontsize=9)

ax.set_xlabel('Hedge Level', fontsize=12)
ax.set_ylabel('Count', fontsize=12)
ax.set_title('Cycle Resolution by Level', fontsize=13, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(level_labels)
ax.legend(fontsize=10)

# Right: average P&L by level
ax = axes[1]
avg_pnls_by_level = []
colors = []
labels_pnl = []
for lvl in range(MAX_LEVELS):
    mask = (levels == lvl) & (~is_bust)
    if np.sum(mask) > 0:
        avg_pnls_by_level.append(np.mean(pnls[mask]))
        colors.append('#2ecc71')
        labels_pnl.append(f'L{lvl}\nWin')
if n_busts > 0:
    avg_pnls_by_level.append(np.mean(pnls[is_bust]))
    colors.append('#e74c3c')
    labels_pnl.append('BUST')

bars = ax.bar(range(len(avg_pnls_by_level)), avg_pnls_by_level, color=colors, edgecolor='black', linewidth=0.5)
for i, bar in enumerate(bars):
    h = bar.get_height()
    va = 'bottom' if h >= 0 else 'top'
    ax.text(bar.get_x() + bar.get_width()/2., h, f'${avg_pnls_by_level[i]:,.0f}',
            ha='center', va=va, fontsize=9, fontweight='bold')

ax.axhline(y=0, color='black', linewidth=0.8)
ax.set_xticks(range(len(labels_pnl)))
ax.set_xticklabels(labels_pnl)
ax.set_ylabel('Average Cycle P&L ($)', fontsize=12)
ax.set_title('Average P&L by Resolution Level', fontsize=13, fontweight='bold')

plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'results/06_level_distribution.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/06_level_distribution.png")

print("\n" + "=" * 80)
print("  ANALYSIS COMPLETE")
print("=" * 80)
