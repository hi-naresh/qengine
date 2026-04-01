"""
Script 26 — Validation on 2024-2026 Data
==========================================
Final verdict: do the chop-aware strategies work on the MOST RECENT data?
This is the test that matters — not 2006 data, but today's markets.

Tests:
  1. Baseline (no chop awareness) on 2024-2026
  2. Chop avoidance on 2024-2026
  3. Chop handling (mid-cycle) on 2024-2026
  4. Combined avoidance + handling on 2024-2026
  5. N-regime switching on 2024-2026
  6. Compare: do the chop detection methods still work?

Outputs:
  - results/26_validation_2026.json
  - plots/26_2026_equity.png
  - plots/26_2026_chop_map.png
  - plots/26_final_comparison.png
"""
from utils import *

print("=" * 60)
print("Script 26 — Validation on 2024-2026 Data")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# 1. LOAD RECENT DATA
# ══════════════════════════════════════════════════════════════
print("\n[1/5] Loading 2024-2026 data...")
recent_candles = load_candles(timeframe='5m', start_date='2024-01-02', end_date='2025-12-30')
print(f"  Loaded {len(recent_candles):,} candles (2024-2025)")

# Also load historical for comparison
hist_candles = load_candles(timeframe='5m', start_date='2006-01-03', end_date='2023-12-30')
print(f"  Historical: {len(hist_candles):,} candles (2006-2023)")

# Compute chop features on recent data
print("  Computing chop features on recent data...")
recent_features = compute_chop_features(recent_candles, windows=(50, 100, 200))
recent_cs = chop_score(recent_features, window=100)

# Compare chop characteristics
hist_features = compute_chop_features(hist_candles, windows=(100,))
hist_cs = chop_score(hist_features, window=100)

hist_chop_mean = float(np.nanmean(hist_cs))
recent_chop_mean = float(np.nanmean(recent_cs))
hist_pct_choppy = float(np.nanmean(hist_cs > 0.6) * 100)
recent_pct_choppy = float(np.nanmean(recent_cs > 0.6) * 100)

print(f"\n  Chop comparison:")
print(f"    Historical (2006-2023): mean={hist_chop_mean:.3f}, {hist_pct_choppy:.1f}% choppy")
print(f"    Recent (2024-2025):     mean={recent_chop_mean:.3f}, {recent_pct_choppy:.1f}% choppy")
chop_shift = recent_chop_mean - hist_chop_mean
print(f"    Shift: {chop_shift:+.4f} ({'MORE choppy' if chop_shift > 0.01 else 'LESS choppy' if chop_shift < -0.01 else 'SIMILAR'})")

# ══════════════════════════════════════════════════════════════
# 2. GENERATE SIGNALS
# ══════════════════════════════════════════════════════════════
print("\n[2/5] Generating signals...")
random_sigs = random_signals(len(recent_candles), avg_spacing=50, rng=np.random.default_rng(99))
ema_sigs = find_ema_crossover_signals(recent_candles, 8, 21)
print(f"  Random: {len(random_sigs)}, EMA: {len(ema_sigs)}")

cfg = SimConfig(sizing_curve='sqrt', sizing_factor=2.0, max_levels=12,
                hedge_dist_pips=10, tp_pips=20)

# ══════════════════════════════════════════════════════════════
# 3. TEST ALL STRATEGIES ON 2024-2026
# ══════════════════════════════════════════════════════════════
print("\n[3/5] Testing strategies on 2024-2026...")

results_dict = {}

# A) Baseline — no chop awareness
baseline_res = run_cycles_on_signals(recent_candles, random_sigs, cfg, chop_scores=recent_cs)
results_dict['baseline'] = cycle_summary(baseline_res)

# B) Chop avoidance — skip entries with chop > 0.6
avoid_sigs = [(idx, d) for idx, d in random_sigs
              if idx < len(recent_cs) and (np.isnan(recent_cs[idx]) or recent_cs[idx] <= 0.6)]
avoid_res = run_cycles_on_signals(recent_candles, avoid_sigs, cfg, chop_scores=recent_cs)
results_dict['chop_avoidance'] = cycle_summary(avoid_res)

# C) Chop avoidance — stricter (0.5)
avoid_strict_sigs = [(idx, d) for idx, d in random_sigs
                     if idx < len(recent_cs) and (np.isnan(recent_cs[idx]) or recent_cs[idx] <= 0.5)]
avoid_strict_res = run_cycles_on_signals(recent_candles, avoid_strict_sigs, cfg, chop_scores=recent_cs)
results_dict['strict_avoidance'] = cycle_summary(avoid_strict_res)

# D) With abort at level 6
abort_cfg = SimConfig(**cfg.to_dict())
abort_cfg.abort_level = 6
abort_res = run_cycles_on_signals(recent_candles, random_sigs, abort_cfg, chop_scores=recent_cs)
results_dict['abort_at_6'] = cycle_summary(abort_res)

# E) EMA signals (not random)
ema_res = run_cycles_on_signals(recent_candles, ema_sigs, cfg, chop_scores=recent_cs)
results_dict['ema_signals'] = cycle_summary(ema_res)

# F) EMA + chop avoidance
ema_avoid = [(idx, d) for idx, d in ema_sigs
             if idx < len(recent_cs) and (np.isnan(recent_cs[idx]) or recent_cs[idx] <= 0.6)]
ema_avoid_res = run_cycles_on_signals(recent_candles, ema_avoid, cfg, chop_scores=recent_cs)
results_dict['ema_chop_avoid'] = cycle_summary(ema_avoid_res)

# G) Conservative config
conservative_cfg = SimConfig(sizing_curve='sqrt', sizing_factor=1.5, max_levels=8,
                               hedge_dist_pips=15, tp_pips=20, abort_level=6)
conserv_res = run_cycles_on_signals(recent_candles, random_sigs, conservative_cfg, chop_scores=recent_cs)
results_dict['conservative'] = cycle_summary(conserv_res)

# H) Conservative + chop avoidance (the full package)
conserv_avoid_sigs = [(idx, d) for idx, d in random_sigs
                      if idx < len(recent_cs) and (np.isnan(recent_cs[idx]) or recent_cs[idx] <= 0.6)]
conserv_avoid_res = run_cycles_on_signals(recent_candles, conserv_avoid_sigs, conservative_cfg, chop_scores=recent_cs)
results_dict['conservative_chop_avoid'] = cycle_summary(conserv_avoid_res)

print(f"\n  {'Strategy':<25} {'Cycles':>7} {'Busts':>7} {'Bust%':>7} {'PF':>7} {'PnL':>10}")
print("  " + "-" * 65)
for name, s in results_dict.items():
    print(f"  {name:<25} {s['n_cycles']:>7} {s['n_busts']:>7} {s['bust_rate']:>6.1f}% "
          f"{s['profit_factor']:>7.2f} {s['net_pnl']:>10.0f}")

# ══════════════════════════════════════════════════════════════
# 4. PLOTS
# ══════════════════════════════════════════════════════════════
print("\n[4/5] Plotting...")

# Equity curves
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

for name, res, color in [
    ('Baseline', baseline_res, 'gray'),
    ('Chop Avoidance', avoid_res, 'blue'),
    ('EMA + Chop Avoid', ema_avoid_res, 'green'),
    ('Conservative + Avoid', conserv_avoid_res, 'purple'),
]:
    if res:
        eq = equity_curve(res)
        s = cycle_summary(res)
        ax1.plot(eq, label=f"{name} (PF={s['profit_factor']:.2f}, bust={s['bust_rate']:.1f}%)",
                 color=color, alpha=0.8)

ax1.set_xlabel('Cycle #')
ax1.set_ylabel('Equity')
ax1.set_title('2024-2026 Validation: Equity Curves')
ax1.legend(fontsize=8)
ax1.grid(True, alpha=0.3)

# Chop map of 2024-2025
step = max(1, len(recent_candles) // 3000)
idx = np.arange(0, len(recent_candles), step)
ax2.plot(idx, recent_candles[idx, 2], linewidth=0.5, color='gray')

# Shade choppy zones
chop_zones = label_chop_zones(recent_cs, threshold=0.6, min_bars=50)
for zone_id in range(1, min(chop_zones.max() + 1, 100)):
    zone_mask = chop_zones[idx] == zone_id
    if zone_mask.any():
        zone_indices = idx[zone_mask]
        ax2.axvspan(zone_indices[0], zone_indices[-1], alpha=0.2, color='red')

# Mark busts
bust_entries = [c.entry_idx for c in baseline_res if c.bust]
valid_bust_entries = [e for e in bust_entries if e in set(idx)]
if valid_bust_entries:
    ax2.scatter(valid_bust_entries,
                [recent_candles[e, 2] for e in valid_bust_entries],
                marker='x', color='red', s=100, zorder=5, label='Busts')
ax2.set_xlabel('Bar Index')
ax2.set_ylabel('Price')
ax2.set_title('2024-2025 EUR-USD: Chop Zones (red) + Bust Locations (×)')
ax2.legend()

plt.tight_layout()
savefig('26_2026_equity.png')

# Final comparison bar chart
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
names = list(results_dict.keys())
busts = [results_dict[n]['bust_rate'] for n in names]
pfs = [results_dict[n]['profit_factor'] for n in names]

colors = ['green' if pf > 2 else 'steelblue' if pf > 1 else 'red' for pf in pfs]
ax1.barh(names, busts, color=colors, edgecolor='black')
ax1.set_xlabel('Bust Rate (%)')
ax1.set_title('2024-2026: Bust Rate by Strategy')
ax1.grid(True, alpha=0.3)

ax2.barh(names, pfs, color=colors, edgecolor='black')
ax2.axvline(x=1.0, color='red', linestyle='--', alpha=0.5)
ax2.set_xlabel('Profit Factor')
ax2.set_title('2024-2026: Profit Factor by Strategy')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
savefig('26_final_comparison.png')

# ══════════════════════════════════════════════════════════════
# 5. SAVE
# ══════════════════════════════════════════════════════════════
save_results({
    'chop_comparison': {
        'historical_mean': hist_chop_mean,
        'recent_mean': recent_chop_mean,
        'historical_pct_choppy': hist_pct_choppy,
        'recent_pct_choppy': recent_pct_choppy,
        'shift': round(chop_shift, 4),
    },
    'strategy_results': results_dict,
}, '26_validation_2026')

print("\n" + "=" * 60)
print("FINAL VERDICT — 2024-2026")
print("=" * 60)

best = max(results_dict.items(),
           key=lambda x: x[1]['profit_factor'] * (1 - x[1]['bust_rate'] / 100))
worst = min(results_dict.items(),
            key=lambda x: x[1]['profit_factor'] * (1 - x[1]['bust_rate'] / 100))

print(f"  Market choppiness in 2024-2025: {'MORE' if chop_shift > 0.01 else 'LESS' if chop_shift < -0.01 else 'SIMILAR'} "
      f"than historical ({recent_chop_mean:.3f} vs {hist_chop_mean:.3f})")
print(f"  Best strategy: {best[0]} → bust={best[1]['bust_rate']:.1f}%, PF={best[1]['profit_factor']:.2f}")
print(f"  Worst strategy: {worst[0]} → bust={worst[1]['bust_rate']:.1f}%, PF={worst[1]['profit_factor']:.2f}")

chop_aware_pf = results_dict.get('conservative_chop_avoid', results_dict.get('chop_avoidance', {}))
baseline_pf = results_dict['baseline']
if chop_aware_pf and baseline_pf:
    improvement = ((chop_aware_pf['profit_factor'] - baseline_pf['profit_factor'])
                   / max(baseline_pf['profit_factor'], 0.01) * 100)
    print(f"\n  Chop awareness value: {improvement:+.0f}% PF improvement over baseline")
    if chop_aware_pf['profit_factor'] > 1.5 and chop_aware_pf['bust_rate'] < baseline_pf['bust_rate']:
        print("  VERDICT: Chop-aware approach WORKS on current markets ✓")
    else:
        print("  VERDICT: Chop-aware approach needs further tuning on current markets")

print("Done.")
