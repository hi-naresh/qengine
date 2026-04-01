"""
Script 24 — N-Regime Island Optimization
==========================================
Not 3 hardcoded regimes — let the DATA tell us how many regimes exist
and what they look like. Then optimize params for each.

Normal regimes handle themselves (strategy profits by default).
Choppy regimes need special configs (or avoidance).

Approach:
  1. Let GMM/BIC find optimal N regimes from chop features
  2. Profile each regime: which are choppy? which are easy?
  3. Optimize config per regime (only choppy ones need work)
  4. Build a regime-switching policy
  5. Compare: N-island vs 3-island vs single config

Outputs:
  - results/24_n_regime.json
  - plots/24_regime_discovery.png
  - plots/24_regime_profiles.png
  - plots/24_per_regime_optima.png
  - plots/24_switching_equity.png
"""
from utils import *

print("=" * 60)
print("Script 24 — N-Regime Island Optimization")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# 1. DISCOVER REGIMES
# ══════════════════════════════════════════════════════════════
print("\n[1/5] Loading data and discovering regimes...")
candles = load_candles(timeframe='5m', start_date='2006-01-03', end_date='2025-12-30')
features = compute_chop_features(candles, windows=(50, 100, 200))
cs = chop_score(features, window=100)

# Let the model find N
labels, n_regimes, diagnostics = discover_regimes(features, max_regimes=10)
print(f"  Discovered {n_regimes} regimes (method: BIC)")
print(f"  BICs: {diagnostics.get('bics', {})}")

# Also compute chop zones for overlay
chop_zones = label_chop_zones(cs, threshold=0.6, min_bars=50)

# Profile each regime
regime_profiles = {}
for r in range(n_regimes):
    mask = labels == r
    n_bars = mask.sum()
    if n_bars < 100:
        continue

    mean_chop = np.nanmean(cs[mask])
    pct_choppy = np.mean(cs[mask] > 0.6) * 100 if np.any(~np.isnan(cs[mask])) else 0
    mean_vol = np.nanmean(features['atr_ratio'][mask])

    # Get feature means
    feat_means = {}
    for k, v in features.items():
        valid = mask & ~np.isnan(v)
        if valid.any():
            feat_means[k] = round(float(np.mean(v[valid])), 4)

    regime_profiles[r] = {
        'n_bars': int(n_bars),
        'pct_of_data': round(n_bars / len(candles) * 100, 1),
        'mean_chop_score': round(mean_chop, 4),
        'pct_choppy': round(pct_choppy, 1),
        'mean_atr_ratio': round(mean_vol, 4),
        'feature_means': feat_means,
    }

    # Classify
    if mean_chop > 0.55:
        rtype = 'CHOPPY'
    elif mean_chop > 0.4:
        rtype = 'MIXED'
    else:
        rtype = 'TRENDING'

    regime_profiles[r]['type'] = rtype
    print(f"  Regime {r}: {rtype:8s} | {n_bars:>8,} bars ({n_bars/len(candles)*100:.1f}%) | "
          f"chop={mean_chop:.3f} | {pct_choppy:.0f}% choppy")

# Chop overlap
overlap = regime_chop_overlap(labels, chop_zones)
print(f"\n  Chop zone overlap per regime: {overlap}")

# Plot regime discovery
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# BIC curve
bics = diagnostics.get('bics', {})
if bics:
    ns = sorted([int(k) for k in bics.keys()])
    ax = axes[0, 0]
    ax.plot(ns, [bics[str(n)] for n in ns], 'bo-')
    ax.axvline(x=n_regimes, color='red', linestyle='--', label=f'Selected: N={n_regimes}')
    ax.set_xlabel('Number of Regimes')
    ax.set_ylabel('BIC')
    ax.set_title('Model Selection (lower BIC = better)')
    ax.legend()
    ax.grid(True, alpha=0.3)

# Regime timeline (sample)
ax = axes[0, 1]
step = max(1, len(candles) // 5000)
idx = np.arange(0, len(candles), step)
colors_r = plt.cm.Set1(np.linspace(0, 1, max(n_regimes, 2)))
for r in range(n_regimes):
    mask = labels[idx] == r
    ax.scatter(idx[mask], candles[idx, 2][mask], s=0.5, c=[colors_r[r]], label=f'R{r}')
ax.set_title('Regime Timeline')
ax.legend(markerscale=10, fontsize=8)

# Chop score by regime
ax = axes[1, 0]
regime_chops = []
regime_labels_plot = []
for r in range(n_regimes):
    mask = labels == r
    valid = mask & ~np.isnan(cs)
    if valid.any():
        regime_chops.append(cs[valid])
        regime_labels_plot.append(f"R{r} ({regime_profiles.get(r, {}).get('type', '?')})")

ax.boxplot(regime_chops, labels=regime_labels_plot)
ax.axhline(y=0.6, color='red', linestyle='--', alpha=0.5, label='Chop threshold')
ax.set_ylabel('Chop Score')
ax.set_title('Chop Score Distribution per Regime')
ax.legend()
ax.grid(True, alpha=0.3)

# Regime sizes
ax = axes[1, 1]
sizes = [regime_profiles[r]['pct_of_data'] for r in range(n_regimes) if r in regime_profiles]
types = [regime_profiles[r]['type'] for r in range(n_regimes) if r in regime_profiles]
type_colors = {'CHOPPY': 'red', 'MIXED': 'orange', 'TRENDING': 'green'}
ax.bar(range(len(sizes)), sizes, color=[type_colors.get(t, 'gray') for t in types])
ax.set_xticks(range(len(sizes)))
ax.set_xticklabels([f'R{r}\n{types[i]}' for i, r in enumerate(sorted(regime_profiles.keys()))])
ax.set_ylabel('% of Data')
ax.set_title('Regime Sizes')
ax.grid(True, alpha=0.3)

plt.tight_layout()
savefig('24_regime_discovery.png')

# ══════════════════════════════════════════════════════════════
# 2. OPTIMIZE PER REGIME
# ══════════════════════════════════════════════════════════════
print("\n[2/5] Optimizing config per regime...")

all_signals = random_signals(len(candles), avg_spacing=50, rng=np.random.default_rng(42))

# Group signals by regime
regime_signals = {r: [] for r in range(n_regimes)}
for idx, d in all_signals:
    if idx < len(labels) and labels[idx] >= 0:
        regime_signals[labels[idx]].append((idx, d))

# Config search space (trimmed for speed)
search_configs = []
for curve in ['sqrt', 'fibonacci']:
    for factor in [1.5, 2.0]:
        for levels in [8, 12]:
            for hedge in [10, 15]:
                for tp in [15, 20]:
                    if curve == 'fibonacci' and factor != 2.0:
                        continue
                    search_configs.append(SimConfig(
                        sizing_curve=curve, sizing_factor=factor,
                        max_levels=levels, hedge_dist_pips=hedge, tp_pips=tp,
                    ))

# For CHOPPY regimes: also test abort configs
for cfg in list(search_configs):
    for abort in [4, 6]:
        abort_cfg = SimConfig(**cfg.to_dict())
        abort_cfg.abort_level = abort
        search_configs.append(abort_cfg)

print(f"  Search space: {len(search_configs)} configs × {n_regimes} regimes")

regime_optima = {}
for r in range(n_regimes):
    if r not in regime_profiles:
        continue
    sigs = regime_signals[r]
    if len(sigs) < 30:
        print(f"  Regime {r}: too few signals ({len(sigs)}), skipping")
        continue

    rtype = regime_profiles[r]['type']
    best_score = -999
    best_cfg = None
    best_s = None

    for cfg in search_configs:
        # For trending regimes, skip abort configs (they don't need it)
        if rtype == 'TRENDING' and cfg.abort_level > 0:
            continue
        # For choppy, prefer configs with abort
        results = run_cycles_on_signals(candles, sigs, cfg, chop_scores=cs)
        if len(results) < 10:
            continue
        s = cycle_summary(results)

        # Score: PF × safety, with extra weight on bust reduction for choppy regimes
        if rtype == 'CHOPPY':
            score = s['profit_factor'] * (1 - s['bust_rate'] / 50)  # Penalize busts more
        else:
            score = s['profit_factor'] * (1 - s['bust_rate'] / 100)

        if score > best_score:
            best_score = score
            best_cfg = cfg
            best_s = s

    if best_cfg:
        regime_optima[r] = {
            'config': best_cfg.to_dict(),
            'summary': best_s,
            'type': rtype,
            'score': round(best_score, 4),
        }
        print(f"  Regime {r} ({rtype}): {best_cfg.sizing_curve} ×{best_cfg.sizing_factor:.1f}, "
              f"{best_cfg.max_levels}L, h={best_cfg.hedge_dist_pips}p, tp={best_cfg.tp_pips}p"
              f"{f', abort@{best_cfg.abort_level}' if best_cfg.abort_level > 0 else ''}"
              f" → bust={best_s['bust_rate']:.1f}%, PF={best_s['profit_factor']:.2f}")

# ══════════════════════════════════════════════════════════════
# 3. REGIME-SWITCHING SIMULATION
# ══════════════════════════════════════════════════════════════
print("\n[3/5] Regime-switching simulation...")

# Switching: use regime-specific config
switching_results = []
for r in range(n_regimes):
    if r not in regime_optima:
        # Fallback to baseline config
        cfg = SimConfig()
    else:
        cfg = SimConfig.from_dict(regime_optima[r]['config'])
    sigs = regime_signals[r]
    results = run_cycles_on_signals(candles, sigs, cfg, chop_scores=cs)
    switching_results.extend(results)

# Sort by entry_idx for proper equity curve
switching_results.sort(key=lambda c: c.entry_idx)
switching_s = cycle_summary(switching_results)

# Static baseline
static_cfg = SimConfig(sizing_curve='sqrt', sizing_factor=2.0, max_levels=12,
                        hedge_dist_pips=10, tp_pips=20)
static_results = run_cycles_on_signals(candles, all_signals, static_cfg, chop_scores=cs)
static_s = cycle_summary(static_results)

# Chop-avoidance only (skip entries in chop)
avoid_signals = [(idx, d) for idx, d in all_signals
                 if idx < len(cs) and (np.isnan(cs[idx]) or cs[idx] <= 0.6)]
avoid_results = run_cycles_on_signals(candles, avoid_signals, static_cfg, chop_scores=cs)
avoid_s = cycle_summary(avoid_results)

print(f"\n  Static:    bust={static_s['bust_rate']:.1f}%, PF={static_s['profit_factor']:.2f}, PnL={static_s['net_pnl']:.0f}")
print(f"  Avoid:     bust={avoid_s['bust_rate']:.1f}%, PF={avoid_s['profit_factor']:.2f}, PnL={avoid_s['net_pnl']:.0f}")
print(f"  N-Switch:  bust={switching_s['bust_rate']:.1f}%, PF={switching_s['profit_factor']:.2f}, PnL={switching_s['net_pnl']:.0f}")

# ══════════════════════════════════════════════════════════════
# 4. EQUITY CURVES
# ══════════════════════════════════════════════════════════════
print("\n[4/5] Plotting...")

fig, ax = plt.subplots(figsize=(14, 7))
eq1 = equity_curve(static_results)
eq2 = equity_curve(avoid_results)
eq3 = equity_curve(switching_results)
ax.plot(eq1, label=f"Static (PF={static_s['profit_factor']:.2f}, bust={static_s['bust_rate']:.1f}%)", alpha=0.7)
ax.plot(eq2, label=f"Chop Avoidance (PF={avoid_s['profit_factor']:.2f}, bust={avoid_s['bust_rate']:.1f}%)", alpha=0.7)
ax.plot(eq3, label=f"N-Regime Switch (PF={switching_s['profit_factor']:.2f}, bust={switching_s['bust_rate']:.1f}%)", alpha=0.7)
ax.set_xlabel('Cycle #')
ax.set_ylabel('Equity')
ax.set_title(f'Strategy Comparison ({n_regimes}-regime switching)')
ax.legend()
ax.grid(True, alpha=0.3)
savefig('24_switching_equity.png')

# Per-regime optima bar chart
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
r_labels = []
r_busts = []
r_pfs = []
r_colors = []
for r in sorted(regime_optima.keys()):
    info = regime_optima[r]
    rtype = info['type']
    r_labels.append(f"R{r}\n({rtype})")
    r_busts.append(info['summary']['bust_rate'])
    r_pfs.append(info['summary']['profit_factor'])
    r_colors.append({'CHOPPY': 'red', 'MIXED': 'orange', 'TRENDING': 'green'}.get(rtype, 'gray'))

ax1.bar(r_labels, r_busts, color=r_colors, edgecolor='black')
ax1.set_ylabel('Bust Rate (%)')
ax1.set_title('Per-Regime Optimal — Bust Rate')
ax1.grid(True, alpha=0.3)

ax2.bar(r_labels, r_pfs, color=r_colors, edgecolor='black')
ax2.set_ylabel('Profit Factor')
ax2.set_title('Per-Regime Optimal — Profit Factor')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
savefig('24_per_regime_optima.png')

# ══════════════════════════════════════════════════════════════
# 5. SAVE
# ══════════════════════════════════════════════════════════════
save_results({
    'n_regimes': n_regimes,
    'regime_profiles': regime_profiles,
    'regime_optima': {str(k): v for k, v in regime_optima.items()},
    'comparison': {
        'static': static_s,
        'avoid': avoid_s,
        'n_switch': switching_s,
    },
    'diagnostics': diagnostics,
}, '24_n_regime')

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)
print(f"  Data-driven regime count: {n_regimes}")
choppy_regimes = [r for r in regime_profiles if regime_profiles[r]['type'] == 'CHOPPY']
print(f"  Choppy regimes: {len(choppy_regimes)} ({sum(regime_profiles[r]['pct_of_data'] for r in choppy_regimes):.1f}% of data)")
print(f"  N-switch vs static PF: {static_s['profit_factor']:.2f} → {switching_s['profit_factor']:.2f}")
print("Done.")
