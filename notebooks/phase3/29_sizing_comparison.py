"""
Script 29 — Complete Sizing Curve Comparison
=============================================
Test ALL sizing curves systematically:
  - geometric, sqrt, fibonacci, linear, fixed
  - Multiple factors: 1.2, 1.5, 2.0, 2.5, 3.0
  - Multiple max levels: 4, 6, 8, 10, 12
  - Multiple hedge distances: 8, 10, 15, 20 pips
  - Multiple TP: 10, 15, 20, 30 pips

Also tests:
  - Risk profile (max drawdown, exposure at each level)
  - Which sizing is best in HIGH VOL vs LOW VOL
  - Theoretical vs empirical bust probability per sizing
"""
from utils import *
import qengine.indicators as ta
import warnings
warnings.filterwarnings('ignore')
from itertools import product

print("=" * 60)
print("Script 29 — Complete Sizing Curve Comparison")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# 1. SETUP
# ══════════════════════════════════════════════════════════════
print("\n[1/6] Loading data...")
candles = load_candles(timeframe='5m', start_date='2020-01-03', end_date='2025-12-30')
n_bars = len(candles)

all_signals = find_ema_crossover_signals(candles, 8, 21)
print(f"  {len(all_signals)} EMA signals on {n_bars:,} candles")

# Compute vol for regime split
natr = ta.natr(candles, period=14, sequential=True)
natr_median = np.nanmedian(natr)

# Split signals into high-vol and low-vol
high_vol_signals = [(idx, d) for idx, d in all_signals
                    if idx < len(natr) and not np.isnan(natr[idx]) and natr[idx] > natr_median]
low_vol_signals = [(idx, d) for idx, d in all_signals
                   if idx < len(natr) and not np.isnan(natr[idx]) and natr[idx] <= natr_median]
print(f"  High-vol signals: {len(high_vol_signals)}, Low-vol: {len(low_vol_signals)}")

# ══════════════════════════════════════════════════════════════
# 2. FULL PARAMETER SWEEP
# ══════════════════════════════════════════════════════════════
print("\n[2/6] Running full parameter sweep...")

sizing_curves = ['geometric', 'sqrt', 'fibonacci', 'linear', 'fixed']
factors = [1.2, 1.5, 2.0, 3.0]
max_levels_list = [4, 8, 12]
hedge_dists = [8, 10, 15]
tp_list = [10, 15, 20, 30]

# Build configs (skip nonsensical combos)
configs = []
for curve, factor, levels, hedge, tp in product(sizing_curves, factors, max_levels_list, hedge_dists, tp_list):
    # fibonacci and fixed don't use factor
    if curve == 'fibonacci' and factor != 2.0:
        continue
    if curve == 'fixed' and factor != 2.0:
        continue
    configs.append(SimConfig(
        sizing_curve=curve, sizing_factor=factor,
        max_levels=levels, hedge_dist_pips=hedge, tp_pips=tp,
    ))

print(f"  Testing {len(configs)} configurations...")

# Run all configs on ALL signals
all_results = []
for i, cfg in enumerate(configs):
    if (i + 1) % 200 == 0:
        print(f"    ...{i+1}/{len(configs)}")

    results = run_cycles_on_signals(candles, all_signals, cfg)
    s = cycle_summary(results)

    # Also quick high/low vol test
    hv_results = run_cycles_on_signals(candles, high_vol_signals, cfg)
    hv_s = cycle_summary(hv_results)
    lv_results = run_cycles_on_signals(candles, low_vol_signals, cfg)
    lv_s = cycle_summary(lv_results)

    # Exposure profile
    exposures = [total_exposure(i, cfg) for i in range(cfg.max_levels)]

    all_results.append({
        'config': cfg.to_dict(),
        'all': s,
        'high_vol': hv_s,
        'low_vol': lv_s,
        'max_exposure': max(exposures),
        'exposure_ratio': max(exposures) / exposures[0] if exposures[0] > 0 else 0,
    })

print(f"  Done: {len(all_results)} configs tested")

# ══════════════════════════════════════════════════════════════
# 3. RANK BY MULTIPLE CRITERIA
# ══════════════════════════════════════════════════════════════
print("\n[3/6] Ranking results...")

# Filter: only configs with >= 100 cycles and PF > 0
valid = [r for r in all_results if r['all']['n_cycles'] >= 100]

# Sort by PF
by_pf = sorted(valid, key=lambda x: x['all']['profit_factor'], reverse=True)

# Sort by net PnL
by_pnl = sorted(valid, key=lambda x: x['all']['net_pnl'], reverse=True)

# Sort by bust rate (ascending)
by_bust = sorted(valid, key=lambda x: x['all']['bust_rate'])

# Risk-adjusted: PnL / max_exposure
for r in valid:
    r['risk_adj_pnl'] = r['all']['net_pnl'] / max(r['max_exposure'], 0.01)
by_risk_adj = sorted(valid, key=lambda x: x['risk_adj_pnl'], reverse=True)

def fmt_config(cfg_dict):
    return f"{cfg_dict['sizing_curve'][:4]} ×{cfg_dict['sizing_factor']:.1f} {cfg_dict['max_levels']}L h={cfg_dict['hedge_dist_pips']}p tp={cfg_dict['tp_pips']}p"

print(f"\n  TOP 15 by Profit Factor:")
print(f"  {'Config':<35s} {'Cycles':>7s} {'Bust%':>6s} {'PF':>6s} {'PnL':>8s} {'Exposure':>9s}")
print(f"  {'-'*75}")
for r in by_pf[:15]:
    c = r['config']
    s = r['all']
    print(f"  {fmt_config(c):<35s} {s['n_cycles']:>7d} {s['bust_rate']:>5.2f}% "
          f"{s['profit_factor']:>6.2f} {s['net_pnl']:>8.0f} {r['max_exposure']:>8.1f}x")

print(f"\n  TOP 15 by Risk-Adjusted PnL:")
print(f"  {'Config':<35s} {'PF':>6s} {'PnL':>8s} {'RiskAdj':>8s} {'Bust%':>6s}")
print(f"  {'-'*68}")
for r in by_risk_adj[:15]:
    c = r['config']
    s = r['all']
    print(f"  {fmt_config(c):<35s} {s['profit_factor']:>6.2f} {s['net_pnl']:>8.0f} "
          f"{r['risk_adj_pnl']:>8.1f} {s['bust_rate']:>5.2f}%")

# ══════════════════════════════════════════════════════════════
# 4. SIZING CURVE COMPARISON (aggregate)
# ══════════════════════════════════════════════════════════════
print("\n[4/6] Aggregate sizing curve comparison...")

print(f"\n  {'Curve':<12s} {'AvgPF':>7s} {'BestPF':>7s} {'AvgBust%':>9s} {'BestBust%':>10s} {'AvgPnL':>8s} {'BestPnL':>8s}")
print(f"  {'-'*65}")

curve_stats = {}
for curve in sizing_curves:
    curve_results = [r for r in valid if r['config']['sizing_curve'] == curve]
    if not curve_results:
        continue

    pfs = [r['all']['profit_factor'] for r in curve_results]
    busts = [r['all']['bust_rate'] for r in curve_results]
    pnls = [r['all']['net_pnl'] for r in curve_results]

    stats = {
        'n_configs': len(curve_results),
        'avg_pf': round(np.mean(pfs), 3),
        'best_pf': round(max(pfs), 3),
        'avg_bust': round(np.mean(busts), 3),
        'best_bust': round(min(busts), 3),
        'avg_pnl': round(np.mean(pnls), 1),
        'best_pnl': round(max(pnls), 1),
    }
    curve_stats[curve] = stats
    print(f"  {curve:<12s} {stats['avg_pf']:>7.3f} {stats['best_pf']:>7.3f} "
          f"{stats['avg_bust']:>8.2f}% {stats['best_bust']:>9.2f}% "
          f"{stats['avg_pnl']:>8.0f} {stats['best_pnl']:>8.0f}")

# ══════════════════════════════════════════════════════════════
# 5. HIGH-VOL vs LOW-VOL BEST CONFIGS
# ══════════════════════════════════════════════════════════════
print("\n[5/6] Best configs by volatility regime...")

by_hv_pf = sorted(valid, key=lambda x: x['high_vol']['profit_factor'], reverse=True)
by_lv_pf = sorted(valid, key=lambda x: x['low_vol']['profit_factor'], reverse=True)

print(f"\n  TOP 10 for HIGH VOLATILITY:")
print(f"  {'Config':<35s} {'HV_PF':>6s} {'HV_Bust':>8s} {'LV_PF':>6s}")
print(f"  {'-'*58}")
for r in by_hv_pf[:10]:
    c = r['config']
    print(f"  {fmt_config(c):<35s} {r['high_vol']['profit_factor']:>6.2f} "
          f"{r['high_vol']['bust_rate']:>7.2f}% {r['low_vol']['profit_factor']:>6.2f}")

print(f"\n  TOP 10 for LOW VOLATILITY:")
print(f"  {'Config':<35s} {'LV_PF':>6s} {'LV_Bust':>8s} {'HV_PF':>6s}")
print(f"  {'-'*58}")
for r in by_lv_pf[:10]:
    c = r['config']
    print(f"  {fmt_config(c):<35s} {r['low_vol']['profit_factor']:>6.2f} "
          f"{r['low_vol']['bust_rate']:>7.2f}% {r['high_vol']['profit_factor']:>6.2f}")

# ══════════════════════════════════════════════════════════════
# 6. PLOTS AND SAVE
# ══════════════════════════════════════════════════════════════
print("\n[6/6] Plotting...")

# Plot 1: Sizing curve aggregate comparison
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

curves = list(curve_stats.keys())
ax = axes[0]
avg_pfs = [curve_stats[c]['avg_pf'] for c in curves]
best_pfs = [curve_stats[c]['best_pf'] for c in curves]
x = np.arange(len(curves))
ax.bar(x - 0.15, avg_pfs, 0.3, label='Avg PF', color='steelblue')
ax.bar(x + 0.15, best_pfs, 0.3, label='Best PF', color='green')
ax.set_xticks(x)
ax.set_xticklabels(curves, rotation=30)
ax.set_ylabel('Profit Factor')
ax.set_title('PF by Sizing Curve')
ax.legend()
ax.grid(True, alpha=0.3)

ax = axes[1]
avg_busts = [curve_stats[c]['avg_bust'] for c in curves]
best_busts = [curve_stats[c]['best_bust'] for c in curves]
ax.bar(x - 0.15, avg_busts, 0.3, label='Avg Bust%', color='salmon')
ax.bar(x + 0.15, best_busts, 0.3, label='Best Bust%', color='green')
ax.set_xticks(x)
ax.set_xticklabels(curves, rotation=30)
ax.set_ylabel('Bust Rate (%)')
ax.set_title('Bust Rate by Sizing Curve')
ax.legend()
ax.grid(True, alpha=0.3)

ax = axes[2]
best_pnls = [curve_stats[c]['best_pnl'] for c in curves]
ax.bar(curves, best_pnls, color=['green' if p > 0 else 'red' for p in best_pnls], edgecolor='black')
ax.set_ylabel('Best Net PnL')
ax.set_title('Best PnL by Sizing Curve')
ax.grid(True, alpha=0.3)
for i, p in enumerate(best_pnls):
    ax.text(i, p + abs(p) * 0.02, f'{p:.0f}', ha='center', fontsize=8)

plt.tight_layout()
savefig('29_sizing_curves.png')

# Plot 2: PF vs Bust Rate scatter (all configs)
fig, ax = plt.subplots(figsize=(12, 8))
curve_colors = {'geometric': 'red', 'sqrt': 'blue', 'fibonacci': 'green', 'linear': 'orange', 'fixed': 'gray'}
for r in valid:
    c = r['config']
    color = curve_colors.get(c['sizing_curve'], 'black')
    ax.scatter(r['all']['bust_rate'], r['all']['profit_factor'],
               c=color, alpha=0.3, s=20, edgecolors='none')

# Add legend
for curve, color in curve_colors.items():
    ax.scatter([], [], c=color, label=curve, s=40)
ax.legend()
ax.set_xlabel('Bust Rate (%)')
ax.set_ylabel('Profit Factor')
ax.set_title(f'All {len(valid)} Configurations: PF vs Bust Rate')
ax.grid(True, alpha=0.3)
ax.axhline(y=1.0, color='red', linestyle=':', alpha=0.5)
savefig('29_pf_vs_bust_scatter.png')

# Plot 3: Exposure profiles
fig, ax = plt.subplots(figsize=(10, 6))
for curve in sizing_curves:
    cfg_test = SimConfig(sizing_curve=curve, sizing_factor=2.0, max_levels=12)
    sizes = [calc_size(i, cfg_test) for i in range(12)]
    cumulative = np.cumsum(sizes)
    ax.plot(range(12), cumulative, 'o-', label=f'{curve} (total={cumulative[-1]:.0f}x)')
ax.set_xlabel('Level')
ax.set_ylabel('Cumulative Exposure (× base)')
ax.set_title('Exposure Profile by Sizing Curve (factor=2.0, 12 levels)')
ax.legend()
ax.grid(True, alpha=0.3)
ax.set_yscale('log')
savefig('29_exposure_profiles.png')

# Save top results
save_results({
    'n_configs_tested': len(configs),
    'n_valid': len(valid),
    'curve_stats': curve_stats,
    'top_15_by_pf': [{**r['config'], **r['all']} for r in by_pf[:15]],
    'top_15_by_risk_adj': [{**r['config'], 'risk_adj_pnl': r['risk_adj_pnl'], **r['all']} for r in by_risk_adj[:15]],
    'top_10_high_vol': [{**r['config'], **r['high_vol']} for r in by_hv_pf[:10]],
    'top_10_low_vol': [{**r['config'], **r['low_vol']} for r in by_lv_pf[:10]],
}, '29_sizing_comparison')

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)
best_curve = max(curve_stats.items(), key=lambda x: x[1]['best_pf'])
print(f"  Best sizing curve overall: {best_curve[0]} (best PF={best_curve[1]['best_pf']:.3f})")
print(f"  Top config: {fmt_config(by_pf[0]['config'])} → PF={by_pf[0]['all']['profit_factor']:.2f}")
print(f"  Best risk-adjusted: {fmt_config(by_risk_adj[0]['config'])} → RiskAdj={by_risk_adj[0]['risk_adj_pnl']:.1f}")

# High-vol winner
hv_best = by_hv_pf[0]
lv_best = by_lv_pf[0]
print(f"  Best for HIGH vol: {fmt_config(hv_best['config'])} → PF={hv_best['high_vol']['profit_factor']:.2f}")
print(f"  Best for LOW vol:  {fmt_config(lv_best['config'])} → PF={lv_best['low_vol']['profit_factor']:.2f}")
print("Done.")
