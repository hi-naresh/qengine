"""
Script 25 — Era Relevance: Does Old Data Still Work in 2026?
=============================================================
The user's concern: is 2006-2015 data even relevant for 2024-2026?
Markets change. Spreads tightened, algos dominate, volatility regimes shift.

Tests:
  1. Era-by-era bust profile (3-year windows from 2006 to 2025)
  2. Chop characteristics per era (is chop changing?)
  3. Cross-era generalization: train on era X, test on era Y
  4. Recency weighting: how much does recent data matter?
  5. Verdict: which eras are relevant for 2024-2026?

Outputs:
  - results/25_era_relevance.json
  - plots/25_era_bust_profiles.png
  - plots/25_era_chop_evolution.png
  - plots/25_cross_era_matrix.png
  - plots/25_recency_impact.png
"""
from utils import *

print("=" * 60)
print("Script 25 — Era Relevance")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# 1. SPLIT INTO ERAS
# ══════════════════════════════════════════════════════════════
print("\n[1/5] Loading and splitting into eras...")
candles = load_candles(timeframe='5m', start_date='2006-01-03', end_date='2025-12-30')

eras = split_into_eras(candles, era_years=3)
print(f"  Split into {len(eras)} eras:")
for label, era_candles in eras:
    print(f"    {label}: {len(era_candles):,} candles")

cfg = SimConfig(sizing_curve='sqrt', sizing_factor=2.0, max_levels=12,
                hedge_dist_pips=10, tp_pips=20)

# ══════════════════════════════════════════════════════════════
# 2. ERA-BY-ERA BUST + CHOP PROFILES
# ══════════════════════════════════════════════════════════════
print("\n[2/5] Computing per-era profiles...")

era_profiles = {}
for label, era_candles in eras:
    profile = era_bust_profile(era_candles, cfg)
    era_profiles[label] = profile
    print(f"  {label}: bust={profile['bust_rate']:.1f}%, PF={profile['profit_factor']:.2f}, "
          f"chop={profile['mean_chop']:.3f}, {profile['pct_choppy']:.0f}% choppy")

# Plot
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12), sharex=True)

labels = list(era_profiles.keys())
bust_rates = [era_profiles[l]['bust_rate'] for l in labels]
pfs = [era_profiles[l]['profit_factor'] for l in labels]
chops = [era_profiles[l]['mean_chop'] for l in labels]
pct_choppy = [era_profiles[l]['pct_choppy'] for l in labels]

colors = ['red' if b > 5 else 'orange' if b > 2 else 'green' for b in bust_rates]
ax1.bar(labels, bust_rates, color=colors, edgecolor='black')
ax1.set_ylabel('Bust Rate (%)')
ax1.set_title('Era-by-Era Bust Rate')
ax1.grid(True, alpha=0.3)

ax2.bar(labels, pfs, color='steelblue', edgecolor='black')
ax2.axhline(y=1.0, color='red', linestyle='--', alpha=0.5)
ax2.set_ylabel('Profit Factor')
ax2.set_title('Era-by-Era Profit Factor')
ax2.grid(True, alpha=0.3)

ax3.bar(labels, pct_choppy, color='salmon', edgecolor='black', alpha=0.7, label='% Choppy')
ax3_twin = ax3.twinx()
ax3_twin.plot(labels, chops, 'ko-', label='Mean Chop Score')
ax3.set_ylabel('% Choppy Bars')
ax3_twin.set_ylabel('Mean Chop Score')
ax3.set_xlabel('Era')
ax3.set_title('Chop Evolution Over Time')
ax3.legend(loc='upper left')
ax3_twin.legend(loc='upper right')
ax3.grid(True, alpha=0.3)

plt.tight_layout()
savefig('25_era_bust_profiles.png')

# ══════════════════════════════════════════════════════════════
# 3. CROSS-ERA GENERALIZATION MATRIX
# ══════════════════════════════════════════════════════════════
print("\n[3/5] Cross-era generalization...")

# For each pair (train_era, test_era):
#   1. Find best config on train_era
#   2. Run it on test_era
#   3. Record PF on test_era

# Simplified: test a few key configs, see which eras they work on
test_configs = {
    'sqrt_2x_12L': SimConfig(sizing_curve='sqrt', sizing_factor=2.0, max_levels=12,
                               hedge_dist_pips=10, tp_pips=20),
    'sqrt_1.5x_8L': SimConfig(sizing_curve='sqrt', sizing_factor=1.5, max_levels=8,
                                hedge_dist_pips=10, tp_pips=20),
    'fib_10L': SimConfig(sizing_curve='fibonacci', max_levels=10,
                           hedge_dist_pips=10, tp_pips=20),
    'abort_at_6': SimConfig(sizing_curve='sqrt', sizing_factor=2.0, max_levels=12,
                              hedge_dist_pips=10, tp_pips=20, abort_level=6),
}

cross_era_pf = {}
for cfg_name, cfg in test_configs.items():
    cross_era_pf[cfg_name] = {}
    for label, era_candles in eras:
        profile = era_bust_profile(era_candles, cfg)
        cross_era_pf[cfg_name][label] = profile['profit_factor']

# Heatmap
fig, ax = plt.subplots(figsize=(12, 6))
cfg_names = list(cross_era_pf.keys())
era_labels = list(eras[i][0] for i in range(len(eras)))
matrix = np.array([[cross_era_pf[c].get(e, 0) for e in era_labels] for c in cfg_names])

im = ax.imshow(matrix, aspect='auto', cmap='RdYlGn', vmin=0, vmax=max(5, matrix.max()))
ax.set_xticks(range(len(era_labels)))
ax.set_xticklabels(era_labels, rotation=45)
ax.set_yticks(range(len(cfg_names)))
ax.set_yticklabels(cfg_names)
ax.set_title('Profit Factor by Config × Era')
plt.colorbar(im, ax=ax, label='Profit Factor')

for i in range(len(cfg_names)):
    for j in range(len(era_labels)):
        ax.text(j, i, f'{matrix[i,j]:.1f}', ha='center', va='center', fontsize=8)

plt.tight_layout()
savefig('25_cross_era_matrix.png')

# ══════════════════════════════════════════════════════════════
# 4. RECENCY WEIGHTING
# ══════════════════════════════════════════════════════════════
print("\n[4/5] Recency analysis...")

# Question: if we only use recent N years of data, does the strategy still work?
recency_results = {}
recent_windows = [3, 5, 7, 10, 15, 20]  # Years of data to use

for window in recent_windows:
    start_year = max(2006, 2026 - window)
    end_year = 2025
    try:
        recent_candles = load_candles(timeframe='5m',
                                       start_date=f'{start_year}-01-03',
                                       end_date=f'{end_year}-12-30')
    except Exception:
        continue

    if len(recent_candles) < 1000:
        continue

    # Split: last 2 years = test, rest = train
    split_point = int(len(recent_candles) * 0.8)
    train = recent_candles[:split_point]
    test = recent_candles[split_point:]

    train_sigs = random_signals(len(train), avg_spacing=50, rng=np.random.default_rng(42))
    test_sigs = random_signals(len(test), avg_spacing=50, rng=np.random.default_rng(99))

    train_results = run_cycles_on_signals(train, train_sigs, cfg)
    test_results = run_cycles_on_signals(test, test_sigs, cfg)

    train_s = cycle_summary(train_results)
    test_s = cycle_summary(test_results)

    recency_results[window] = {
        'years': window,
        'start': start_year,
        'train_bust': train_s['bust_rate'],
        'test_bust': test_s['bust_rate'],
        'train_pf': train_s['profit_factor'],
        'test_pf': test_s['profit_factor'],
        'generalization': round(test_s['profit_factor'] / max(train_s['profit_factor'], 0.01), 3),
    }
    print(f"  Last {window}yr ({start_year}-{end_year}): "
          f"train PF={train_s['profit_factor']:.2f}, test PF={test_s['profit_factor']:.2f}, "
          f"gen={recency_results[window]['generalization']:.2f}")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

ws = sorted(recency_results.keys())
train_pfs = [recency_results[w]['train_pf'] for w in ws]
test_pfs = [recency_results[w]['test_pf'] for w in ws]
gens = [recency_results[w]['generalization'] for w in ws]

ax1.plot(ws, train_pfs, 'bo-', label='Train PF')
ax1.plot(ws, test_pfs, 'ro-', label='Test PF')
ax1.set_xlabel('Data Window (years)')
ax1.set_ylabel('Profit Factor')
ax1.set_title('Recency: How Much History Is Useful?')
ax1.legend()
ax1.grid(True, alpha=0.3)

ax2.bar(ws, gens, color=['green' if g > 0.8 else 'orange' if g > 0.5 else 'red' for g in gens])
ax2.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5, label='Perfect generalization')
ax2.set_xlabel('Data Window (years)')
ax2.set_ylabel('Test PF / Train PF')
ax2.set_title('Generalization Ratio')
ax2.legend()
ax2.grid(True, alpha=0.3)

plt.tight_layout()
savefig('25_recency_impact.png')

# ══════════════════════════════════════════════════════════════
# 5. SAVE
# ══════════════════════════════════════════════════════════════
print("\n[5/5] Saving...")
save_results({
    'era_profiles': era_profiles,
    'cross_era_pf': cross_era_pf,
    'recency': recency_results,
}, '25_era_relevance')

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)

# Is chop increasing or decreasing over time?
if len(chops) >= 3:
    chop_trend = np.polyfit(range(len(chops)), chops, 1)[0]
    print(f"  Chop trend over time: {'INCREASING' if chop_trend > 0.001 else 'DECREASING' if chop_trend < -0.001 else 'STABLE'} "
          f"(slope={chop_trend:.5f})")

# Most/least relevant era
if era_profiles:
    most_recent = list(era_profiles.keys())[-1]
    most_choppy = max(era_profiles.items(), key=lambda x: x[1]['pct_choppy'])[0]
    least_choppy = min(era_profiles.items(), key=lambda x: x[1]['pct_choppy'])[0]
    print(f"  Most choppy era: {most_choppy} ({era_profiles[most_choppy]['pct_choppy']:.0f}% choppy)")
    print(f"  Least choppy era: {least_choppy} ({era_profiles[least_choppy]['pct_choppy']:.0f}% choppy)")

# Best recency window
if recency_results:
    best_gen = max(recency_results.items(), key=lambda x: x[1]['generalization'])
    print(f"  Best data window: last {best_gen[0]} years (generalization={best_gen[1]['generalization']:.2f})")

print("Done.")
