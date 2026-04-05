"""
Script 30 — Practical Sizing with Real Capital Constraints
===========================================================
Given actual account capital, compute:
  1. Max affordable levels per sizing curve at specific lot sizes
  2. Margin requirements per level (OANDA 50:1, 30:1 for EU)
  3. Max drawdown in $ at each bust level
  4. Expected bust recovery: how many winning cycles to recover a bust?
  5. Kelly criterion: optimal fraction of capital to risk
  6. Practical recommendation: what to actually trade with $10K, $50K, $100K

This is the "can I actually trade this?" analysis.
"""
from utils import *
import warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("Script 30 — Practical Sizing with Real Capital")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════
PIP_VALUE_STANDARD = 10.0    # $10 per pip for 1 standard lot (100K units) on EUR-USD
PIP_VALUE_MINI = 1.0         # $1 per pip for 0.1 lot (10K units)
PIP_VALUE_MICRO = 0.10       # $0.10 per pip for 0.01 lot (1K units)

LEVERAGE_OANDA = 50          # OANDA US: 50:1
LEVERAGE_EU = 30             # EU regulated: 30:1
MARGIN_PER_LOT_50 = 100000 / 50  # $2,000 per standard lot at 50:1
MARGIN_PER_LOT_30 = 100000 / 30  # $3,333 per standard lot at 30:1

ACCOUNT_SIZES = [5000, 10000, 25000, 50000, 100000]

# ══════════════════════════════════════════════════════════════
# 1. LOAD DATA AND GET REAL CYCLE STATS
# ══════════════════════════════════════════════════════════════
print("\n[1/5] Loading data for empirical stats...", flush=True)
candles = load_candles(timeframe='5m', start_date='2020-01-03', end_date='2025-12-30')
signals = find_ema_crossover_signals(candles, 8, 21)
print(f"  {len(candles):,} candles, {len(signals)} signals", flush=True)

# ══════════════════════════════════════════════════════════════
# 2. FOR EACH SIZING CURVE: COMPUTE REAL $ EXPOSURE
# ══════════════════════════════════════════════════════════════
print("\n[2/5] Computing exposure profiles per sizing curve...", flush=True)

sizing_curves = ['geometric', 'sqrt', 'fibonacci', 'linear', 'fixed']
factors = [1.5, 2.0]
max_levels_list = [4, 6, 8, 10, 12]

# Base lot = micro lot (0.01) = 1000 units
# At 50:1 leverage, margin = 1000/50 = $20 per micro lot

print(f"\n  EXPOSURE PROFILE: lots and margin at each level")
print(f"  (Base = 1 micro lot = 0.01 lot = 1000 units, pip value = $0.10)")
print(f"  {'Curve':<12s} {'Factor':>6s} {'Levels':>6s} | {'Lots@Max':>10s} {'TotalLots':>10s} {'Margin50:1':>11s} {'MaxDD(10p)':>11s}")
print(f"  {'-'*75}")

exposure_data = []

for curve in sizing_curves:
    for factor in factors:
        if curve in ('fibonacci', 'fixed') and factor != 2.0:
            continue
        for max_lvl in max_levels_list:
            cfg = SimConfig(sizing_curve=curve, sizing_factor=factor,
                            max_levels=max_lvl, hedge_dist_pips=15, tp_pips=15)

            # Size at each level (in units of base lot)
            sizes = [calc_size(i, cfg) for i in range(max_lvl)]
            total_lots = sum(sizes)  # in micro lots

            # Margin needed = total_lots * margin_per_micro
            margin_50 = total_lots * 20  # $20 per micro lot at 50:1
            margin_30 = total_lots * 33.33

            # Max drawdown if bust: each level loses hedge_dist * size
            # Worst case: all levels hit, price goes against each
            max_dd_pips = 0
            for i in range(max_lvl):
                # Level i loses hedge_distance pips * size at that level
                h_dist = hedge_distance(i, cfg)
                max_dd_pips += h_dist * sizes[i]
            max_dd_dollars = max_dd_pips * PIP_VALUE_MICRO  # $0.10 per pip per micro

            exposure_data.append({
                'curve': curve, 'factor': factor, 'max_levels': max_lvl,
                'sizes': sizes, 'total_lots': round(total_lots, 2),
                'max_lot': round(sizes[-1], 2),
                'margin_50': round(margin_50, 2),
                'margin_30': round(margin_30, 2),
                'max_dd_dollars': round(max_dd_dollars, 2),
                'max_dd_pips': round(max_dd_pips, 2),
            })

            print(f"  {curve:<12s} {factor:>6.1f} {max_lvl:>6d} | "
                  f"{sizes[-1]:>10.1f} {total_lots:>10.1f} "
                  f"${margin_50:>10.0f} ${max_dd_dollars:>10.0f}")

# ══════════════════════════════════════════════════════════════
# 3. FOR EACH ACCOUNT SIZE: WHAT'S AFFORDABLE?
# ══════════════════════════════════════════════════════════════
print("\n[3/5] Computing max affordable levels per account size...", flush=True)

MAX_RISK_PCT = 0.20  # Risk at most 20% of account on a single bust

print(f"\n  MAX AFFORDABLE LEVELS (bust DD < {MAX_RISK_PCT*100:.0f}% of account)")
print(f"  (Base = 1 micro lot, hedge=15p, tp=15p)")
print(f"\n  {'Curve':<10s} {'×':>4s} |", end='')
for acct in ACCOUNT_SIZES:
    print(f" ${acct/1000:.0f}K", end='')
print()
print(f"  {'-'*60}")

affordable = {}
for curve in sizing_curves:
    for factor in factors:
        if curve in ('fibonacci', 'fixed') and factor != 2.0:
            continue
        key = f"{curve[:5]}_x{factor}"
        affordable[key] = {}
        print(f"  {curve:<10s} {factor:>4.1f} |", end='')
        for acct in ACCOUNT_SIZES:
            max_dd_limit = acct * MAX_RISK_PCT
            best_lvl = 0
            for e in exposure_data:
                if e['curve'] == curve and e['factor'] == factor:
                    if e['max_dd_dollars'] <= max_dd_limit and e['margin_50'] <= acct * 0.5:
                        best_lvl = max(best_lvl, e['max_levels'])
            affordable[key][acct] = best_lvl
            print(f"   {best_lvl:>3d}L", end='')
        print()

# ══════════════════════════════════════════════════════════════
# 4. SIMULATE WITH REAL DOLLAR P&L
# ══════════════════════════════════════════════════════════════
print("\n[4/5] Simulating with real dollar P&L per account size...", flush=True)

print(f"\n  EXPECTED RETURNS (micro lot base, 5yr simulation)")
print(f"  {'Account':>8s} {'Curve':<10s} {'×':>3s} {'Lvls':>4s} | {'Cycles':>6s} {'Busts':>5s} {'PF':>5s} {'NetPnL$':>9s} {'MaxDD$':>8s} {'DD%':>5s} {'ROI%':>6s}")
print(f"  {'-'*85}")

sim_results = []
for acct in [10000, 50000, 100000]:
    for curve in ['sqrt', 'geometric', 'fibonacci']:
        for factor in [1.5, 2.0]:
            if curve in ('fibonacci',) and factor != 2.0:
                continue
            key = f"{curve[:5]}_x{factor}"
            max_lvl = affordable.get(key, {}).get(acct, 0)
            if max_lvl < 4:
                continue

            cfg = SimConfig(sizing_curve=curve, sizing_factor=factor,
                            max_levels=max_lvl, hedge_dist_pips=15, tp_pips=15)

            results = run_cycles_on_signals(candles, signals, cfg)
            s = cycle_summary(results)

            # Convert pip P&L to dollars (micro lot)
            net_pnl_dollars = s['net_pnl'] * PIP_VALUE_MICRO
            # Max single bust loss
            sizes = [calc_size(i, cfg) for i in range(max_lvl)]
            bust_dd_pips = sum(hedge_distance(i, cfg) * sizes[i] for i in range(max_lvl))
            bust_dd_dollars = bust_dd_pips * PIP_VALUE_MICRO

            # Equity curve for max drawdown
            eq = equity_curve(results, initial_balance=acct)
            peak = np.maximum.accumulate(eq)
            dd_dollars = (peak - eq).max()
            dd_pct = ((peak - eq) / peak).max() * 100

            roi = net_pnl_dollars / acct * 100

            result = {
                'account': acct, 'curve': curve, 'factor': factor,
                'max_levels': max_lvl, **s,
                'net_pnl_dollars': round(net_pnl_dollars, 2),
                'bust_dd_dollars': round(bust_dd_dollars, 2),
                'max_dd_dollars': round(dd_dollars, 2),
                'max_dd_pct': round(dd_pct, 2),
                'roi_pct': round(roi, 2),
            }
            sim_results.append(result)

            print(f"  ${acct:>7,} {curve:<10s} {factor:>3.1f} {max_lvl:>4d} | "
                  f"{s['n_cycles']:>6d} {s['n_busts']:>5d} {s['profit_factor']:>5.2f} "
                  f"${net_pnl_dollars:>8.0f} ${dd_dollars:>7.0f} {dd_pct:>4.1f}% {roi:>5.1f}%")

# ══════════════════════════════════════════════════════════════
# 5. BUST RECOVERY ANALYSIS
# ══════════════════════════════════════════════════════════════
print("\n[5/5] Bust recovery analysis...", flush=True)

print(f"\n  BUST RECOVERY: How many wins to recover a single bust?")
print(f"  {'Curve':<10s} {'×':>3s} {'Lvls':>4s} | {'AvgWinPnL':>10s} {'BustLoss':>10s} {'WinsToRecover':>14s}")
print(f"  {'-'*58}")

for curve in ['sqrt', 'geometric', 'fibonacci']:
    for factor in [1.5, 2.0]:
        if curve in ('fibonacci',) and factor != 2.0:
            continue
        for max_lvl in [6, 8, 10, 12]:
            cfg = SimConfig(sizing_curve=curve, sizing_factor=factor,
                            max_levels=max_lvl, hedge_dist_pips=15, tp_pips=15)

            results = run_cycles_on_signals(candles, signals, cfg)
            wins = [c for c in results if c.is_win]
            busts = [c for c in results if c.bust]

            if not wins or not busts:
                continue

            avg_win = np.mean([c.pnl for c in wins])
            avg_bust = abs(np.mean([c.pnl for c in busts]))
            recovery = avg_bust / avg_win if avg_win > 0 else float('inf')

            print(f"  {curve:<10s} {factor:>3.1f} {max_lvl:>4d} | "
                  f"{avg_win:>10.1f}p {avg_bust:>10.1f}p {recovery:>13.0f} wins")

# ══════════════════════════════════════════════════════════════
# PLOTS
# ══════════════════════════════════════════════════════════════
print("\n  Plotting...", flush=True)

# Plot 1: Max affordable levels per account
fig, ax = plt.subplots(figsize=(12, 6))
x = np.arange(len(ACCOUNT_SIZES))
width = 0.12
curves_to_plot = ['sqrt_x1.5', 'sqrt_x2.0', 'geom_x1.5', 'geom_x2.0', 'fibon_x2.0']
colors = ['steelblue', 'royalblue', 'orange', 'darkorange', 'green']
for i, (key, color) in enumerate(zip(curves_to_plot, colors)):
    if key in affordable:
        vals = [affordable[key].get(a, 0) for a in ACCOUNT_SIZES]
        ax.bar(x + i * width, vals, width, label=key, color=color)
ax.set_xticks(x + width * 2)
ax.set_xticklabels([f'${a/1000:.0f}K' for a in ACCOUNT_SIZES])
ax.set_ylabel('Max Affordable Levels')
ax.set_title(f'Max Levels Affordable (bust DD < {MAX_RISK_PCT*100:.0f}% of account)')
ax.legend()
ax.grid(True, alpha=0.3)
savefig('30_affordable_levels.png')

# Plot 2: ROI vs max DD for simulated configs
if sim_results:
    fig, ax = plt.subplots(figsize=(10, 7))
    for r in sim_results:
        color = {'sqrt': 'blue', 'geometric': 'red', 'fibonacci': 'green'}.get(r['curve'], 'gray')
        marker = {10000: 'o', 50000: 's', 100000: '^'}.get(r['account'], 'o')
        ax.scatter(r['max_dd_pct'], r['roi_pct'], c=color, marker=marker, s=80,
                   edgecolors='black', linewidth=0.5)
    # Legend
    for curve, color in [('sqrt', 'blue'), ('geometric', 'red'), ('fibonacci', 'green')]:
        ax.scatter([], [], c=color, label=curve, s=40)
    for acct, marker in [(10000, 'o'), (50000, 's'), (100000, '^')]:
        ax.scatter([], [], c='gray', marker=marker, label=f'${acct/1000:.0f}K', s=40)
    ax.set_xlabel('Max Drawdown (%)')
    ax.set_ylabel('5yr ROI (%)')
    ax.set_title('Return vs Risk by Config and Account Size')
    ax.legend()
    ax.grid(True, alpha=0.3)
    savefig('30_roi_vs_drawdown.png')

# Plot 3: Bust recovery (wins needed)
fig, ax = plt.subplots(figsize=(10, 6))
for curve in ['sqrt', 'fibonacci']:
    factor = 2.0 if curve == 'fibonacci' else 2.0
    levels = []
    recoveries = []
    for max_lvl in range(4, 13):
        cfg = SimConfig(sizing_curve=curve, sizing_factor=factor,
                        max_levels=max_lvl, hedge_dist_pips=15, tp_pips=15)
        results = run_cycles_on_signals(candles, signals, cfg)
        wins = [c for c in results if c.is_win]
        busts = [c for c in results if c.bust]
        if wins and busts:
            avg_win = np.mean([c.pnl for c in wins])
            avg_bust = abs(np.mean([c.pnl for c in busts]))
            levels.append(max_lvl)
            recoveries.append(avg_bust / avg_win if avg_win > 0 else 0)
    if levels:
        ax.plot(levels, recoveries, 'o-', label=f'{curve} x{factor}')

ax.set_xlabel('Max Levels')
ax.set_ylabel('Winning Cycles to Recover 1 Bust')
ax.set_title('Bust Recovery Cost by Level Count')
ax.legend()
ax.grid(True, alpha=0.3)
savefig('30_bust_recovery.png')

# Save
save_results({
    'exposure_data': exposure_data,
    'affordable': affordable,
    'sim_results': sim_results,
}, '30_practical_sizing')

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)

# Best practical config per account size
for acct in [10000, 50000, 100000]:
    acct_results = [r for r in sim_results if r['account'] == acct and r['roi_pct'] > 0]
    if acct_results:
        best = max(acct_results, key=lambda x: x['roi_pct'])
        print(f"  ${acct/1000:.0f}K best: {best['curve']} x{best['factor']} {best['max_levels']}L "
              f"→ ROI={best['roi_pct']:.1f}%, maxDD={best['max_dd_pct']:.1f}%, "
              f"PF={best['profit_factor']:.2f}")
print("Done.", flush=True)
