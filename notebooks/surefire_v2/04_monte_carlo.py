#!/usr/bin/env python3
"""
Step 8: Monte Carlo Stress Test for Surefire V2
=====================================================
Simulates martingale-hedging cycles across different Level 0 win rates
to quantify probability of ruin and required win rate for viability.
"""

import os
os.chdir('/Users/naresh/Documents/Research/qengine')

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dataclasses import dataclass
from typing import Dict, List, Tuple
import time

# ─── Parameters ───────────────────────────────────────────────────────────────
TP_PIPS = 30            # representative TP for ATR*0.8 on EURUSD 5m
HEDGE_PIPS = 15         # tp / risk_reward (risk_reward=2.0)
PIP_VALUE = 10          # USD per pip per standard lot
INITIAL_SIZE = 0.1      # lots
MULTIPLIER = 2.0        # martingale multiplier
MAX_LEVELS = 5          # max hedge levels (0..5 = 6 attempts total)
STARTING_BALANCE = 10_000
N_SIMULATIONS = 10_000
N_CYCLES = 1_000

WIN_RATES = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

OUTPUT_DIR = 'notebooks/surefire_v2'
os.makedirs(OUTPUT_DIR, exist_ok=True)

np.random.seed(42)

# ─── Exact Math ───────────────────────────────────────────────────────────────
def exact_math(p: float, max_levels: int = MAX_LEVELS) -> Dict:
    """
    Exact mathematical analysis of one martingale cycle.

    At each level k (0..max_levels):
      - size = INITIAL_SIZE * MULTIPLIER^k
      - If win at level k: profit = TP_PIPS * PIP_VALUE * size_k
      - Cumulative loss entering level k = sum of HEDGE_PIPS * PIP_VALUE * size_j for j<k
      - Net profit if win at level k = TP profit at k - cumulative loss

    If all levels lose: total loss = sum of HEDGE_PIPS * PIP_VALUE * size_j for j=0..max_levels
    """
    results = {}

    # Per-level calculations
    sizes = [INITIAL_SIZE * MULTIPLIER**k for k in range(max_levels + 1)]

    # Cumulative loss entering each level (loss from previous levels' SL hits)
    cum_loss = [0.0]
    for k in range(1, max_levels + 1):
        cum_loss.append(cum_loss[-1] + HEDGE_PIPS * PIP_VALUE * sizes[k-1])

    # TP profit at each level
    tp_profit = [TP_PIPS * PIP_VALUE * sizes[k] for k in range(max_levels + 1)]

    # Net profit if win at level k
    net_profit = [tp_profit[k] - cum_loss[k] for k in range(max_levels + 1)]

    # Probability of winning at exactly level k: (1-p)^k * p
    p_win_at = [(1 - p)**k * p for k in range(max_levels + 1)]

    # Probability of total bust (all levels lose)
    p_bust = (1 - p)**(max_levels + 1)

    # Total loss on bust
    total_bust_loss = cum_loss[-1] + HEDGE_PIPS * PIP_VALUE * sizes[-1]

    # Expected profit per cycle
    expected = sum(p_win_at[k] * net_profit[k] for k in range(max_levels + 1)) \
               + p_bust * (-total_bust_loss)

    results['sizes'] = sizes
    results['cum_loss'] = cum_loss
    results['tp_profit'] = tp_profit
    results['net_profit'] = net_profit
    results['p_win_at'] = p_win_at
    results['p_bust'] = p_bust
    results['total_bust_loss'] = total_bust_loss
    results['expected_per_cycle'] = expected
    results['p_win_overall'] = 1 - p_bust

    # Expected cycles before ruin (rough: balance / expected_loss_per_bust * 1/p_bust)
    if p_bust > 0 and expected < 0:
        # Negative expectation: approximate cycles to ruin
        results['approx_cycles_to_ruin'] = abs(STARTING_BALANCE / expected)
    elif p_bust > 0:
        # Positive expectation but bust still possible
        # Gambler's ruin approximation
        results['approx_cycles_to_ruin'] = None  # complex, use simulation
    else:
        results['approx_cycles_to_ruin'] = float('inf')

    return results


# ─── Print Exact Math ────────────────────────────────────────────────────────
print("=" * 80)
print("EXACT MATHEMATICAL ANALYSIS OF MARTINGALE HEDGE CYCLE")
print("=" * 80)
print(f"\nParameters: TP={TP_PIPS} pips, Hedge SL={HEDGE_PIPS} pips, "
      f"Pip Value=${PIP_VALUE}, Initial Size={INITIAL_SIZE} lots")
print(f"Multiplier={MULTIPLIER}x, Max Levels={MAX_LEVELS}, "
      f"Starting Balance=${STARTING_BALANCE:,.0f}")

print(f"\n{'Level':<8} {'Size':<10} {'TP Profit':<12} {'Cum Loss':<12} {'Net Profit':<12}")
print("-" * 54)

# Show for a reference win rate
ref = exact_math(0.50)
for k in range(MAX_LEVELS + 1):
    print(f"  {k:<6} {ref['sizes'][k]:<10.2f} ${ref['tp_profit'][k]:<10.2f} "
          f"${ref['cum_loss'][k]:<10.2f} ${ref['net_profit'][k]:<10.2f}")

print(f"\n  BUST (all lose): Total loss = ${ref['total_bust_loss']:,.2f}")
print(f"  Note: Bust loss = {ref['total_bust_loss'] / STARTING_BALANCE * 100:.1f}% of starting balance")

print(f"\n{'Win Rate':<10} {'P(bust/cycle)':<15} {'P(bust/1000)':<15} "
      f"{'E[profit/cycle]':<17} {'Cycles to Ruin':<15}")
print("-" * 72)

for wr in WIN_RATES:
    m = exact_math(wr)
    p_bust_1000 = 1 - (1 - m['p_bust'])**1000  # P(at least one bust in 1000)
    ctr = m.get('approx_cycles_to_ruin')
    ctr_str = f"{ctr:,.0f}" if ctr is not None and ctr != float('inf') else "Inf" if ctr == float('inf') else "N/A (E>0)"
    print(f"  {wr:<8.0%} {m['p_bust']:<15.6f} {p_bust_1000:<15.6f} "
          f"${m['expected_per_cycle']:<15.2f} {ctr_str}")


# ─── Monte Carlo Simulation ──────────────────────────────────────────────────
print("\n" + "=" * 80)
print("MONTE CARLO SIMULATION: 10,000 paths x 1,000 cycles each")
print("=" * 80)

# Pre-compute cycle outcomes for efficiency
# For each level, the size and the PnL impact
sizes_arr = np.array([INITIAL_SIZE * MULTIPLIER**k for k in range(MAX_LEVELS + 1)])
# Loss at each level (SL hit)
level_loss = HEDGE_PIPS * PIP_VALUE * sizes_arr  # loss if SL hit at this level
# Profit at each level (TP hit)
level_tp = TP_PIPS * PIP_VALUE * sizes_arr  # profit if TP hit at this level


def simulate_cycles(win_rate: float, n_sims: int = N_SIMULATIONS,
                    n_cycles: int = N_CYCLES) -> Dict:
    """
    Vectorized Monte Carlo simulation of martingale hedge cycles.
    Returns statistics about ruin probability, drawdown, final balances.
    """
    # Generate all random outcomes at once: shape (n_sims, n_cycles, max_levels+1)
    # Each value is True if that level wins
    rand = np.random.random((n_sims, n_cycles, MAX_LEVELS + 1))
    wins = rand < win_rate  # True = win at this level

    # For each cycle, compute PnL
    # Strategy: at each level, if win -> collect TP, done. If lose -> go next.
    # PnL = TP at winning level - sum of SL losses at all prior levels
    # If no level wins -> total loss

    cycle_pnl = np.zeros((n_sims, n_cycles))

    for k in range(MAX_LEVELS + 1):
        if k == 0:
            # Level 0 winners: profit = TP at level 0, no prior losses
            won_here = wins[:, :, 0]
            cycle_pnl[won_here] = level_tp[0]
        else:
            # Won at level k: must have lost levels 0..k-1
            lost_all_prior = np.all(~wins[:, :, :k], axis=2)
            won_here = lost_all_prior & wins[:, :, k]
            # Net = TP at level k - cumulative losses from levels 0..k-1
            cum_losses = np.sum(level_loss[:k])
            cycle_pnl[won_here] = level_tp[k] - cum_losses

    # Total bust: lost all levels
    all_lost = np.all(~wins, axis=2)
    total_loss = np.sum(level_loss)
    cycle_pnl[all_lost] = -total_loss

    # Compute equity curves
    cum_pnl = np.cumsum(cycle_pnl, axis=1)
    balances = STARTING_BALANCE + cum_pnl

    # Ruin: balance <= 0 at any point
    ruin_mask = np.any(balances <= 0, axis=1)
    p_ruin = np.mean(ruin_mask)

    # Final balances (for non-ruined paths, or last positive value)
    final_balances = balances[:, -1]

    # Max drawdown per simulation
    running_max = np.maximum.accumulate(balances, axis=1)
    drawdowns = (running_max - balances) / running_max
    max_dd = np.max(drawdowns, axis=1)

    # Sharpe-like ratio: mean(cycle_pnl) / std(cycle_pnl) * sqrt(252*24)
    mean_pnl = np.mean(cycle_pnl, axis=1)
    std_pnl = np.std(cycle_pnl, axis=1)
    # Avoid division by zero
    sharpe = np.where(std_pnl > 0, mean_pnl / std_pnl * np.sqrt(1000), 0)

    return {
        'p_ruin': p_ruin,
        'n_ruined': int(np.sum(ruin_mask)),
        'median_final': np.median(final_balances),
        'mean_final': np.mean(final_balances),
        'p5_final': np.percentile(final_balances, 5),
        'p95_final': np.percentile(final_balances, 95),
        'median_max_dd': np.median(max_dd),
        'mean_max_dd': np.mean(max_dd),
        'median_sharpe': np.median(sharpe),
        'balances': balances,  # keep for plotting sample paths
        'cycle_pnl': cycle_pnl,
    }


# Run sweep
results = {}
t0 = time.time()

for wr in WIN_RATES:
    t1 = time.time()
    results[wr] = simulate_cycles(wr)
    elapsed = time.time() - t1
    r = results[wr]
    print(f"  Win rate {wr:.0%}: P(ruin)={r['p_ruin']:.4f} | "
          f"Median final=${r['median_final']:>12,.2f} | "
          f"Max DD={r['median_max_dd']:.1%} | "
          f"Sharpe={r['median_sharpe']:.2f} | "
          f"({elapsed:.1f}s)")

total_time = time.time() - t0
print(f"\nTotal simulation time: {total_time:.1f}s")


# ─── Chart 1: P(ruin) vs Win Rate ────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))

p_ruins = [results[wr]['p_ruin'] for wr in WIN_RATES]
ax.plot(WIN_RATES, p_ruins, 'ro-', linewidth=2, markersize=8, label='MC Simulation')

# Add exact theoretical P(at least one bust in 1000 cycles) for comparison
p_bust_exact = []
for wr in WIN_RATES:
    m = exact_math(wr)
    # P(ruin) is more complex than just P(bust), but bust probability is a lower bound
    p_at_least_one_bust = 1 - (1 - m['p_bust'])**N_CYCLES
    p_bust_exact.append(min(p_at_least_one_bust, 1.0))
ax.plot(WIN_RATES, p_bust_exact, 'b--', linewidth=1.5, alpha=0.7,
        label='P(at least 1 bust in 1000) [exact]')

# Threshold lines
ax.axhline(y=0.01, color='green', linestyle=':', alpha=0.7, label='1% ruin threshold')
ax.axhline(y=0.05, color='orange', linestyle=':', alpha=0.7, label='5% ruin threshold')
ax.axvline(x=0.33, color='red', linestyle='--', alpha=0.5, label='Observed: 33% win rate')
ax.axvline(x=0.65, color='blue', linestyle='--', alpha=0.5, label='Target: 65% win rate')

ax.set_xlabel('Level 0 Win Rate', fontsize=12)
ax.set_ylabel('Probability of Ruin (balance <= 0)', fontsize=12)
ax.set_title('Monte Carlo: P(Ruin) vs Level 0 Win Rate\n'
             f'({N_SIMULATIONS:,} sims x {N_CYCLES:,} cycles, '
             f'multiplier={MULTIPLIER}x, max_levels={MAX_LEVELS})', fontsize=13)
ax.legend(loc='upper right', fontsize=9)
ax.set_xlim(0.28, 0.82)
ax.set_ylim(-0.02, 1.05)
ax.grid(True, alpha=0.3)

# Annotate key points
for wr in [0.33, 0.50, 0.65, 0.75]:
    # Find closest win rate in results
    closest = min(WIN_RATES, key=lambda x: abs(x - wr))
    r = results[closest]
    ax.annotate(f'{closest:.0%}: P(ruin)={r["p_ruin"]:.2%}',
                xy=(closest, r['p_ruin']),
                xytext=(closest + 0.03, r['p_ruin'] + 0.08),
                fontsize=8, ha='left',
                arrowprops=dict(arrowstyle='->', color='gray', lw=0.8))

plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/04_monte_carlo_ruin_vs_winrate.png', dpi=150)
plt.close()
print(f"\nSaved: {OUTPUT_DIR}/04_monte_carlo_ruin_vs_winrate.png")


# ─── Chart 2: Sample Equity Curves ──────────────────────────────────────────
fig, axes = plt.subplots(2, 3, figsize=(16, 10))
sample_rates = [0.30, 0.40, 0.50, 0.60, 0.70, 0.80]

for idx, wr in enumerate(sample_rates):
    ax = axes[idx // 3][idx % 3]
    r = results[wr]
    balances = r['balances']

    # Plot 50 random paths
    n_sample = min(50, N_SIMULATIONS)
    sample_idx = np.random.choice(N_SIMULATIONS, n_sample, replace=False)

    for i in sample_idx:
        color = 'red' if np.any(balances[i] <= 0) else 'green' if balances[i, -1] > STARTING_BALANCE else 'gray'
        alpha = 0.4 if color == 'gray' else 0.6
        ax.plot(balances[i], color=color, alpha=alpha, linewidth=0.5)

    ax.axhline(y=STARTING_BALANCE, color='black', linestyle='--', alpha=0.3)
    ax.axhline(y=0, color='red', linestyle='-', alpha=0.5)
    ax.set_title(f'Win Rate = {wr:.0%}\nP(ruin)={r["p_ruin"]:.2%}, '
                 f'Median Final=${r["median_final"]:,.0f}', fontsize=10)
    ax.set_xlabel('Cycle #')
    ax.set_ylabel('Balance ($)')
    ax.grid(True, alpha=0.2)

fig.suptitle('Sample Equity Curves by Level 0 Win Rate\n'
             f'(50 paths shown per panel, {N_SIMULATIONS:,} total simulated)',
             fontsize=14, y=1.02)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/04_monte_carlo_equity_curves.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/04_monte_carlo_equity_curves.png")


# ─── Chart 3: Summary Statistics ─────────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Panel 1: Median final balance
ax = axes[0][0]
medians = [results[wr]['median_final'] for wr in WIN_RATES]
p5s = [results[wr]['p5_final'] for wr in WIN_RATES]
p95s = [results[wr]['p95_final'] for wr in WIN_RATES]
ax.fill_between(WIN_RATES, p5s, p95s, alpha=0.2, color='blue', label='5th-95th percentile')
ax.plot(WIN_RATES, medians, 'bo-', linewidth=2, label='Median')
ax.axhline(y=STARTING_BALANCE, color='gray', linestyle='--', alpha=0.5, label='Starting balance')
ax.set_xlabel('Level 0 Win Rate')
ax.set_ylabel('Final Balance ($)')
ax.set_title('Final Balance Distribution')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Panel 2: Max drawdown
ax = axes[0][1]
mdd = [results[wr]['median_max_dd'] for wr in WIN_RATES]
ax.plot(WIN_RATES, mdd, 'rs-', linewidth=2)
ax.set_xlabel('Level 0 Win Rate')
ax.set_ylabel('Median Max Drawdown (%)')
ax.set_title('Median Maximum Drawdown')
ax.grid(True, alpha=0.3)

# Panel 3: P(ruin) on log scale
ax = axes[1][0]
p_ruins_plot = [max(r, 1e-5) for r in p_ruins]  # avoid log(0)
ax.semilogy(WIN_RATES, p_ruins_plot, 'ro-', linewidth=2, markersize=8)
ax.axhline(y=0.01, color='green', linestyle=':', label='1% threshold')
ax.axhline(y=0.05, color='orange', linestyle=':', label='5% threshold')
ax.axvline(x=0.33, color='red', linestyle='--', alpha=0.5, label='Observed 33%')
ax.set_xlabel('Level 0 Win Rate')
ax.set_ylabel('P(Ruin) [log scale]')
ax.set_title('P(Ruin) - Log Scale')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Panel 4: Expected profit per cycle
ax = axes[1][1]
expected = [exact_math(wr)['expected_per_cycle'] for wr in WIN_RATES]
colors = ['green' if e > 0 else 'red' for e in expected]
ax.bar(WIN_RATES, expected, width=0.04, color=colors, alpha=0.7, edgecolor='black')
ax.axhline(y=0, color='black', linewidth=0.5)
ax.set_xlabel('Level 0 Win Rate')
ax.set_ylabel('Expected Profit per Cycle ($)')
ax.set_title('Expected Profit per Cycle (Exact)')
ax.grid(True, alpha=0.3)

fig.suptitle('Monte Carlo Summary Statistics\n'
             f'Martingale {MULTIPLIER}x, {MAX_LEVELS} max levels, '
             f'{N_SIMULATIONS:,} sims x {N_CYCLES:,} cycles',
             fontsize=13)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/04_monte_carlo_summary.png', dpi=150)
plt.close()
print(f"Saved: {OUTPUT_DIR}/04_monte_carlo_summary.png")


# ─── Final Conclusions ───────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("CONCLUSIONS")
print("=" * 80)

# Find win rate needed for <1% ruin
for wr in WIN_RATES:
    if results[wr]['p_ruin'] < 0.01:
        wr_1pct = wr
        break
else:
    wr_1pct = None

# Find win rate needed for <5% ruin
for wr in WIN_RATES:
    if results[wr]['p_ruin'] < 0.05:
        wr_5pct = wr
        break
else:
    wr_5pct = None

print(f"\n1. WIN RATE NEEDED FOR <1% RUIN (over {N_CYCLES} cycles):")
if wr_1pct:
    print(f"   -> Level 0 win rate >= {wr_1pct:.0%}")
    print(f"      At {wr_1pct:.0%}: P(ruin) = {results[wr_1pct]['p_ruin']:.4f}, "
          f"Median final = ${results[wr_1pct]['median_final']:,.2f}")
else:
    print(f"   -> No tested win rate achieves <1% ruin! Even 80% has "
          f"P(ruin) = {results[0.80]['p_ruin']:.4f}")

print(f"\n2. WIN RATE NEEDED FOR <5% RUIN (over {N_CYCLES} cycles):")
if wr_5pct:
    print(f"   -> Level 0 win rate >= {wr_5pct:.0%}")
else:
    print(f"   -> No tested win rate achieves <5% ruin!")

print(f"\n3. OBSERVED 33% WIN RATE (closest: 30% and 35%):")
for wr in [0.30, 0.35]:
    r = results[wr]
    m = exact_math(wr)
    print(f"   {wr:.0%} win rate:")
    print(f"      P(ruin)         = {r['p_ruin']:.4f} ({r['p_ruin']:.1%})")
    print(f"      Median final    = ${r['median_final']:,.2f}")
    print(f"      E[profit/cycle] = ${m['expected_per_cycle']:.2f}")
    print(f"      Median max DD   = {r['median_max_dd']:.1%}")
    print(f"      P(bust/cycle)   = {m['p_bust']:.6f}")

print(f"\n4. KEY WIN RATE SCENARIOS:")
for wr in [0.50, 0.65, 0.75]:
    r = results[wr]
    m = exact_math(wr)
    print(f"   {wr:.0%} win rate:")
    print(f"      P(ruin)         = {r['p_ruin']:.4f} ({r['p_ruin']:.1%})")
    print(f"      Median final    = ${r['median_final']:,.2f}")
    print(f"      E[profit/cycle] = ${m['expected_per_cycle']:.2f}")
    print(f"      Median max DD   = {r['median_max_dd']:.1%}")
    print(f"      Bust loss       = ${m['total_bust_loss']:,.2f} ({m['total_bust_loss']/STARTING_BALANCE:.0%} of balance)")

print(f"\n5. THE CORE PROBLEM:")
bust_loss = exact_math(0.50)['total_bust_loss']
print(f"   A single bust (all {MAX_LEVELS+1} levels lose) costs ${bust_loss:,.2f}")
print(f"   That's {bust_loss/STARTING_BALANCE:.0%} of starting balance with $10k")
print(f"   With 0.1 lot initial size, the max position is "
      f"{INITIAL_SIZE * MULTIPLIER**MAX_LEVELS:.1f} lots at level {MAX_LEVELS}")
print(f"   Even with 65% win rate, P(bust per cycle) = {(1-0.65)**6:.6f}")
print(f"   Over 1000 cycles: P(at least one bust) = {1-(1-(1-0.65)**6)**1000:.4f}")

print(f"\n6. VERDICT:")
print(f"   - At observed 33% win rate: GUARANTEED RUIN. Strategy is not viable.")
print(f"   - Need >= {wr_1pct:.0%} win rate for <1% ruin probability" if wr_1pct else
      f"   - Even 80% win rate insufficient for <1% ruin")
print(f"   - The martingale multiplier creates catastrophic tail risk")
print(f"   - Each bust wipes out many winning cycles")
print(f"   - The plan's requirement of >65% Level 0 win rate is a MINIMUM,")
print(f"     and even that may not be sufficient depending on bust loss magnitude")

print("\n" + "=" * 80)
print("FILES SAVED:")
print(f"  {OUTPUT_DIR}/04_monte_carlo_ruin_vs_winrate.png")
print(f"  {OUTPUT_DIR}/04_monte_carlo_equity_curves.png")
print(f"  {OUTPUT_DIR}/04_monte_carlo_summary.png")
print("=" * 80)
