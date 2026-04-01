"""
Script 21 — Anatomy of Choppy Markets (Where Busts Happen)
===========================================================
Phase 2 proved 98.7% of busts happen in "choppy range" zones.
This script dissects what "choppy" actually looks like across 20 years of data
and tests multiple chop detection methods head-to-head.

Questions:
  1. What do bust zones look like? (feature fingerprint)
  2. Which chop indicator best predicts busts?
  3. How early can we detect a chop zone before it causes a bust?
  4. Is there a universal chop threshold, or is it adaptive?

Outputs:
  - results/21_chop_anatomy.json
  - plots/21_bust_zone_fingerprint.png
  - plots/21_indicator_vs_bust.png
  - plots/21_early_warning.png
  - plots/21_chop_timeline.png
"""
from utils import *

print("=" * 60)
print("Script 21 — Anatomy of Choppy Markets")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# 1. LOAD DATA & RUN BASELINE SIMULATION
# ══════════════════════════════════════════════════════════════
print("\n[1/5] Loading data and running baseline simulation...")
candles = load_candles(timeframe='5m', start_date='2006-01-03', end_date='2025-12-30')
print(f"  Loaded {len(candles):,} candles")

cfg = SimConfig(sizing_curve='sqrt', sizing_factor=2.0, max_levels=12,
                hedge_dist_pips=10, tp_pips=20)
signals = random_signals(len(candles), avg_spacing=50, rng=np.random.default_rng(42))

# Compute ALL chop features before simulation
print("  Computing chop features (this takes a moment)...")
features = compute_chop_features(candles, windows=(50, 100, 200))
cs = chop_score(features, window=100)

# Run simulation, tagging each cycle with its chop score
results = run_cycles_on_signals(candles, signals, cfg, chop_scores=cs)
s = cycle_summary(results)
print(f"  Cycles: {s['n_cycles']}, Busts: {s['n_busts']} ({s['bust_rate']:.2f}%)")

busts = [c for c in results if c.bust]
wins = [c for c in results if c.is_win]

# ══════════════════════════════════════════════════════════════
# 2. BUST ZONE FINGERPRINT
# ══════════════════════════════════════════════════════════════
print("\n[2/5] Computing bust zone fingerprint...")

# For each cycle, extract feature values at entry
feature_keys = sorted([k for k in features.keys() if not np.all(np.isnan(features[k]))])

bust_features = {k: [] for k in feature_keys}
win_features = {k: [] for k in feature_keys}

for c in busts:
    idx = c.entry_idx
    if idx >= len(candles):
        continue
    for k in feature_keys:
        val = features[k][idx]
        if not np.isnan(val):
            bust_features[k].append(val)

for c in wins:
    idx = c.entry_idx
    if idx >= len(candles):
        continue
    for k in feature_keys:
        val = features[k][idx]
        if not np.isnan(val):
            win_features[k].append(val)

# Plot fingerprint: mean ± std for busts vs wins
fig, ax = plt.subplots(figsize=(14, 7))
short_names = [k.replace('choppiness_index', 'CHOP').replace('efficiency_ratio', 'ER')
               .replace('hurst', 'Hurst').replace('fractal_dim', 'FracDim')
               .replace('range_vs_atr', 'RngATR').replace('adx', 'ADX')
               .replace('atr_ratio', 'ATR_R') for k in feature_keys]

x = np.arange(len(feature_keys))
bust_means = []
win_means = []
bust_stds = []
separations = []

for k in feature_keys:
    bm = np.mean(bust_features[k]) if bust_features[k] else 0
    wm = np.mean(win_features[k]) if win_features[k] else 0
    bs = np.std(bust_features[k]) if bust_features[k] else 0
    ws = np.std(win_features[k]) if win_features[k] else 0

    bust_means.append(bm)
    win_means.append(wm)
    bust_stds.append(bs)

    # Cohen's d: separation between bust and win distributions
    pooled_std = np.sqrt((bs**2 + ws**2) / 2) if (bs + ws) > 0 else 1
    separations.append(abs(bm - wm) / pooled_std)

# Normalize for visualization
bust_norm = np.array(bust_means) / (np.abs(bust_means) + np.abs(win_means) + 1e-10)
win_norm = np.array(win_means) / (np.abs(bust_means) + np.abs(win_means) + 1e-10)

ax.barh(x - 0.2, bust_norm, 0.35, label='Bust zones', color='red', alpha=0.7)
ax.barh(x + 0.2, win_norm, 0.35, label='Win zones', color='green', alpha=0.7)
ax.set_yticks(x)
ax.set_yticklabels(short_names, fontsize=8)
ax.set_xlabel('Normalized Feature Value')
ax.set_title('Bust Zone Fingerprint: Feature Values at Entry')
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
savefig('21_bust_zone_fingerprint.png')

# ══════════════════════════════════════════════════════════════
# 3. WHICH INDICATOR BEST PREDICTS BUSTS?
# ══════════════════════════════════════════════════════════════
print("\n[3/5] Testing each indicator as bust predictor...")

# For each indicator, compute AUC (area under ROC) for bust prediction
from functools import partial

indicator_auc = {}
for k in feature_keys:
    bust_vals = bust_features[k]
    win_vals = win_features[k]
    if len(bust_vals) < 5 or len(win_vals) < 5:
        continue

    # Simple AUC via Mann-Whitney U
    all_vals = bust_vals + win_vals
    all_labels = [1] * len(bust_vals) + [0] * len(win_vals)
    n_busts = len(bust_vals)
    n_wins = len(win_vals)

    # Sort by value, count concordant pairs
    pairs = sorted(zip(all_vals, all_labels), key=lambda x: x[0])
    concordant = 0
    n_pos_seen = 0
    for val, label in pairs:
        if label == 0:
            concordant += n_pos_seen
        else:
            n_pos_seen += 1

    auc = concordant / (n_busts * n_wins) if n_busts * n_wins > 0 else 0.5
    # Ensure AUC > 0.5 (flip if needed — we want "higher = more choppy = more bust")
    auc = max(auc, 1 - auc)

    indicator_auc[k] = round(auc, 4)
    print(f"  {k:30s}: AUC = {auc:.4f}  (Cohen's d = {separations[feature_keys.index(k)]:.3f})")

# Rank by AUC
ranked = sorted(indicator_auc.items(), key=lambda x: x[1], reverse=True)

fig, ax = plt.subplots(figsize=(10, 7))
names_r = [r[0] for r in ranked]
aucs = [r[1] for r in ranked]
colors = ['red' if a > 0.65 else 'orange' if a > 0.55 else 'gray' for a in aucs]
ax.barh(range(len(ranked)), aucs, color=colors)
ax.set_yticks(range(len(ranked)))
ax.set_yticklabels([n.replace('choppiness_index', 'CHOP').replace('efficiency_ratio', 'ER')
                    for n in names_r], fontsize=8)
ax.axvline(x=0.5, color='gray', linestyle='--', label='Random (0.5)')
ax.set_xlabel('AUC (bust prediction)')
ax.set_title('Chop Indicator Ranking — Bust Prediction Power')
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
savefig('21_indicator_vs_bust.png')

# ══════════════════════════════════════════════════════════════
# 4. EARLY WARNING: HOW MANY BARS BEFORE BUST?
# ══════════════════════════════════════════════════════════════
print("\n[4/5] Early warning analysis...")

# For each bust, look at chop score N bars BEFORE entry
# Can we see chop building up?
lookbacks = [10, 20, 50, 100, 200]
early_warning = {}

for lb in lookbacks:
    bust_scores = []
    win_scores = []
    for c in busts:
        idx = c.entry_idx - lb
        if 0 <= idx < len(cs) and not np.isnan(cs[idx]):
            bust_scores.append(cs[idx])
    for c in wins[:len(busts) * 3]:  # Sample wins
        idx = c.entry_idx - lb
        if 0 <= idx < len(cs) and not np.isnan(cs[idx]):
            win_scores.append(cs[idx])

    if bust_scores and win_scores:
        separation = abs(np.mean(bust_scores) - np.mean(win_scores))
        early_warning[lb] = {
            'bust_mean': round(np.mean(bust_scores), 4),
            'win_mean': round(np.mean(win_scores), 4),
            'separation': round(separation, 4),
        }
        print(f"  {lb} bars before: bust_chop={np.mean(bust_scores):.3f}, "
              f"win_chop={np.mean(win_scores):.3f}, sep={separation:.4f}")

fig, ax = plt.subplots(figsize=(10, 6))
lbs = sorted(early_warning.keys())
bust_vals = [early_warning[lb]['bust_mean'] for lb in lbs]
win_vals = [early_warning[lb]['win_mean'] for lb in lbs]
ax.plot(lbs, bust_vals, 'ro-', label='Before busts', markersize=8)
ax.plot(lbs, win_vals, 'go-', label='Before wins', markersize=8)
ax.fill_between(lbs, bust_vals, win_vals, alpha=0.15, color='orange')
ax.set_xlabel('Bars BEFORE entry')
ax.set_ylabel('Mean Chop Score')
ax.set_title('Early Warning: Chop Score Before Busts vs Wins')
ax.legend()
ax.grid(True, alpha=0.3)
ax.invert_xaxis()
savefig('21_early_warning.png')

# ══════════════════════════════════════════════════════════════
# 5. CHOP TIMELINE WITH BUST OVERLAY
# ══════════════════════════════════════════════════════════════
print("\n[5/5] Chop timeline...")

# Show 2 years of data with chop zones and bust markers
# Use 2018-2019 as example
import arrow
ts = candles[:, 0]
start_ts = arrow.get('2018-01-01').int_timestamp * 1000
end_ts = arrow.get('2020-01-01').int_timestamp * 1000
mask = (ts >= start_ts) & (ts < end_ts)
idx_range = np.where(mask)[0]

if len(idx_range) > 0:
    step = max(1, len(idx_range) // 5000)  # Downsample for plotting
    plot_idx = idx_range[::step]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), sharex=True,
                                     gridspec_kw={'height_ratios': [2, 1]})

    ax1.plot(plot_idx, candles[plot_idx, 2], linewidth=0.5, color='gray')
    ax1.set_ylabel('Price')
    ax1.set_title('EUR-USD 2018-2019 with Chop Zones and Busts')

    # Shade choppy zones
    chop_zones = label_chop_zones(cs, threshold=0.6, min_bars=50)
    for zone_id in range(1, chop_zones.max() + 1):
        zone_mask = chop_zones[plot_idx] == zone_id
        if zone_mask.any():
            zone_indices = plot_idx[zone_mask]
            ax1.axvspan(zone_indices[0], zone_indices[-1], alpha=0.2, color='red')

    # Mark busts
    bust_entries = [c.entry_idx for c in busts if c.entry_idx in set(plot_idx)]
    if bust_entries:
        ax1.scatter(bust_entries, candles[bust_entries, 2], marker='x', color='red', s=100, zorder=5, label='Bust')
    ax1.legend()

    # Chop score
    ax2.plot(plot_idx, cs[plot_idx], linewidth=0.5, color='steelblue')
    ax2.axhline(y=0.6, color='red', linestyle='--', alpha=0.5, label='Chop threshold')
    ax2.fill_between(plot_idx, 0, cs[plot_idx], where=cs[plot_idx] > 0.6,
                     alpha=0.3, color='red')
    ax2.set_ylabel('Chop Score')
    ax2.set_xlabel('Bar Index')
    ax2.legend()
    ax2.set_ylim(0, 1)

    plt.tight_layout()
    savefig('21_chop_timeline.png')

# ══════════════════════════════════════════════════════════════
# SAVE & SUMMARY
# ══════════════════════════════════════════════════════════════
save_results({
    'baseline': s,
    'indicator_auc': indicator_auc,
    'indicator_ranking': [r[0] for r in ranked],
    'early_warning': early_warning,
    'best_predictor': ranked[0][0] if ranked else 'none',
    'best_auc': ranked[0][1] if ranked else 0.5,
}, '21_chop_anatomy')

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)
if ranked:
    print(f"  Best bust predictor: {ranked[0][0]} (AUC = {ranked[0][1]:.4f})")
    print(f"  Top 3: {', '.join(f'{r[0]}={r[1]:.3f}' for r in ranked[:3])}")
if early_warning:
    best_lead = max(early_warning.items(), key=lambda x: x[1]['separation'])
    print(f"  Best early warning: {best_lead[0]} bars ahead (sep={best_lead[1]['separation']:.4f})")
print(f"  Composite chop score: bust_entry={np.mean([c.chop_score_at_entry for c in busts]):.3f} "
      f"vs win_entry={np.mean([c.chop_score_at_entry for c in wins]):.3f}")
print("Done.")
