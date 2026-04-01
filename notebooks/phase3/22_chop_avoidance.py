"""
Script 22 — Chop Avoidance: Can We Just Skip Choppy Entries?
=============================================================
Simplest possible solution: if chop score > threshold, don't enter.
How much does this help? What's the cost (missed good trades)?

Tests:
  1. Sweep chop threshold: 0.3 → 0.9 — bust rate / PF / missed trades
  2. Per-indicator filters: which single indicator works best as gate?
  3. Composite filter: combine top indicators
  4. Cost-benefit: bust reduction vs opportunity cost

Outputs:
  - results/22_chop_avoidance.json
  - plots/22_threshold_sweep.png
  - plots/22_single_indicator_gates.png
  - plots/22_composite_filter.png
  - plots/22_cost_benefit.png
"""
from utils import *

print("=" * 60)
print("Script 22 — Chop Avoidance")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# 1. SETUP
# ══════════════════════════════════════════════════════════════
print("\n[1/5] Loading data...")
candles = load_candles(timeframe='5m', start_date='2006-01-03', end_date='2025-12-30')
cfg = SimConfig(sizing_curve='sqrt', sizing_factor=2.0, max_levels=12,
                hedge_dist_pips=10, tp_pips=20)

all_signals = random_signals(len(candles), avg_spacing=50, rng=np.random.default_rng(42))
ema_signals = find_ema_crossover_signals(candles, 8, 21)

print("  Computing chop features...")
features = compute_chop_features(candles, windows=(50, 100, 200))
cs = chop_score(features, window=100)

# Baseline (no filter)
baseline_results = run_cycles_on_signals(candles, all_signals, cfg, chop_scores=cs)
baseline = cycle_summary(baseline_results)
print(f"  Baseline: {baseline['n_cycles']} cycles, {baseline['bust_rate']:.2f}% bust, PF={baseline['profit_factor']:.2f}")

# ══════════════════════════════════════════════════════════════
# 2. CHOP THRESHOLD SWEEP
# ══════════════════════════════════════════════════════════════
print("\n[2/5] Sweeping chop thresholds...")

thresholds = np.arange(0.25, 0.95, 0.05)
threshold_results = {}

for t in thresholds:
    # Filter signals: skip if chop score at entry > threshold
    filtered = [(idx, d) for idx, d in all_signals
                if idx < len(cs) and (np.isnan(cs[idx]) or cs[idx] <= t)]
    results = run_cycles_on_signals(candles, filtered, cfg, chop_scores=cs)
    s = cycle_summary(results)

    pct_kept = len(filtered) / len(all_signals) * 100
    bust_reduction = ((baseline['bust_rate'] - s['bust_rate']) / baseline['bust_rate'] * 100
                      if baseline['bust_rate'] > 0 else 0)

    threshold_results[f'{t:.2f}'] = {
        **s,
        'threshold': round(t, 2),
        'signals_kept': len(filtered),
        'pct_kept': round(pct_kept, 1),
        'bust_reduction_pct': round(bust_reduction, 1),
    }
    print(f"  t={t:.2f}: kept={pct_kept:.0f}%, bust={s['bust_rate']:.2f}% "
          f"(↓{bust_reduction:.0f}%), PF={s['profit_factor']:.2f}")

# Plot
fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 5))

ts_list = [threshold_results[k]['threshold'] for k in sorted(threshold_results)]
bust_rates = [threshold_results[k]['bust_rate'] for k in sorted(threshold_results)]
pfs = [threshold_results[k]['profit_factor'] for k in sorted(threshold_results)]
kept_pcts = [threshold_results[k]['pct_kept'] for k in sorted(threshold_results)]

ax1.plot(ts_list, bust_rates, 'ro-')
ax1.axhline(y=baseline['bust_rate'], color='gray', linestyle='--', label=f'Baseline ({baseline["bust_rate"]:.1f}%)')
ax1.set_xlabel('Chop Threshold')
ax1.set_ylabel('Bust Rate (%)')
ax1.set_title('Bust Rate vs Chop Threshold')
ax1.legend()
ax1.grid(True, alpha=0.3)

ax2.plot(ts_list, pfs, 'bo-')
ax2.axhline(y=baseline['profit_factor'], color='gray', linestyle='--', label=f'Baseline (PF={baseline["profit_factor"]:.2f})')
ax2.set_xlabel('Chop Threshold')
ax2.set_ylabel('Profit Factor')
ax2.set_title('Profit Factor vs Chop Threshold')
ax2.legend()
ax2.grid(True, alpha=0.3)

ax3.plot(ts_list, kept_pcts, 'go-')
ax3.set_xlabel('Chop Threshold')
ax3.set_ylabel('Signals Kept (%)')
ax3.set_title('Trade Opportunity Cost')
ax3.grid(True, alpha=0.3)

plt.tight_layout()
savefig('22_threshold_sweep.png')

# ══════════════════════════════════════════════════════════════
# 3. SINGLE INDICATOR GATES
# ══════════════════════════════════════════════════════════════
print("\n[3/5] Testing individual indicator gates...")

# For each indicator, find best threshold and test as standalone gate
indicator_gates = {}
feature_keys = sorted([k for k in features.keys() if not np.all(np.isnan(features[k]))])

for k in feature_keys:
    vals = features[k]
    best_pf = 0
    best_thresh = None
    best_bust = baseline['bust_rate']
    best_kept = 100

    # Determine direction: does higher value = more choppy?
    bust_vals = [vals[c.entry_idx] for c in baseline_results if c.bust and c.entry_idx < len(vals) and not np.isnan(vals[c.entry_idx])]
    win_vals = [vals[c.entry_idx] for c in baseline_results if c.is_win and c.entry_idx < len(vals) and not np.isnan(vals[c.entry_idx])]

    if not bust_vals or not win_vals:
        continue

    bust_higher = np.mean(bust_vals) > np.mean(win_vals)

    # Try percentile-based thresholds
    all_valid = vals[~np.isnan(vals)]
    if len(all_valid) < 100:
        continue

    for pct in [25, 30, 40, 50, 60, 70, 75, 80]:
        thresh = np.percentile(all_valid, pct)

        if bust_higher:
            # Higher = choppier → reject signals above threshold
            filtered = [(idx, d) for idx, d in all_signals
                        if idx < len(vals) and (np.isnan(vals[idx]) or vals[idx] <= thresh)]
        else:
            # Lower = choppier → reject signals below threshold
            filtered = [(idx, d) for idx, d in all_signals
                        if idx < len(vals) and (np.isnan(vals[idx]) or vals[idx] >= thresh)]

        if len(filtered) < 50:
            continue

        results = run_cycles_on_signals(candles, filtered, cfg)
        s = cycle_summary(results)

        if s['profit_factor'] > best_pf:
            best_pf = s['profit_factor']
            best_thresh = thresh
            best_bust = s['bust_rate']
            best_kept = len(filtered) / len(all_signals) * 100

    indicator_gates[k] = {
        'best_threshold': round(best_thresh, 4) if best_thresh is not None else None,
        'bust_higher': bust_higher,
        'bust_rate': round(best_bust, 2),
        'profit_factor': round(best_pf, 2),
        'pct_kept': round(best_kept, 1),
        'bust_reduction': round((baseline['bust_rate'] - best_bust) / baseline['bust_rate'] * 100, 1)
                          if baseline['bust_rate'] > 0 else 0,
    }

# Rank by bust reduction
ranked_gates = sorted(indicator_gates.items(), key=lambda x: x[1]['bust_reduction'], reverse=True)
print(f"\n  Top indicator gates:")
for name, g in ranked_gates[:8]:
    short = name.replace('choppiness_index', 'CHOP').replace('efficiency_ratio', 'ER')
    print(f"    {short:25s}: bust↓{g['bust_reduction']:+.0f}%, PF={g['profit_factor']:.2f}, kept={g['pct_kept']:.0f}%")

fig, ax = plt.subplots(figsize=(12, 7))
gate_names = [r[0].replace('choppiness_index', 'CHOP').replace('efficiency_ratio', 'ER')
              for r in ranked_gates[:12]]
reductions = [r[1]['bust_reduction'] for r in ranked_gates[:12]]
pfs_g = [r[1]['profit_factor'] for r in ranked_gates[:12]]

x = np.arange(len(gate_names))
ax.barh(x, reductions, color=['green' if r > 20 else 'orange' if r > 10 else 'gray' for r in reductions])
ax.set_yticks(x)
ax.set_yticklabels(gate_names, fontsize=8)
ax.set_xlabel('Bust Rate Reduction (%)')
ax.set_title('Single Indicator Gate — Bust Reduction')
for i, (red, pf) in enumerate(zip(reductions, pfs_g)):
    ax.text(red + 0.5, i, f'PF={pf:.1f}', fontsize=7, va='center')
ax.grid(True, alpha=0.3)
plt.tight_layout()
savefig('22_single_indicator_gates.png')

# ══════════════════════════════════════════════════════════════
# 4. COMPOSITE FILTER (top 3 indicators)
# ══════════════════════════════════════════════════════════════
print("\n[4/5] Building composite filter...")

# Use composite chop score with different thresholds + the best single indicator
composite_results = {}

# Test: composite score only
for t in [0.4, 0.5, 0.55, 0.6, 0.65, 0.7]:
    filtered = [(idx, d) for idx, d in all_signals
                if idx < len(cs) and (np.isnan(cs[idx]) or cs[idx] <= t)]
    results = run_cycles_on_signals(candles, filtered, cfg, chop_scores=cs)
    s = cycle_summary(results)
    composite_results[f'composite_{t}'] = {**s, 'pct_kept': round(len(filtered) / len(all_signals) * 100, 1)}

# Test: composite + best single indicator (AND logic)
if ranked_gates:
    best_gate_name = ranked_gates[0][0]
    best_gate_info = ranked_gates[0][1]
    best_gate_vals = features[best_gate_name]
    best_gate_thresh = best_gate_info['best_threshold']
    gate_higher = best_gate_info['bust_higher']

    for t in [0.5, 0.6, 0.7]:
        filtered = []
        for idx, d in all_signals:
            if idx >= len(cs) or idx >= len(best_gate_vals):
                continue
            chop_ok = np.isnan(cs[idx]) or cs[idx] <= t
            if gate_higher:
                gate_ok = np.isnan(best_gate_vals[idx]) or best_gate_vals[idx] <= best_gate_thresh
            else:
                gate_ok = np.isnan(best_gate_vals[idx]) or best_gate_vals[idx] >= best_gate_thresh
            if chop_ok and gate_ok:
                filtered.append((idx, d))

        results = run_cycles_on_signals(candles, filtered, cfg, chop_scores=cs)
        s = cycle_summary(results)
        composite_results[f'composite_{t}+{best_gate_name[:15]}'] = {
            **s, 'pct_kept': round(len(filtered) / len(all_signals) * 100, 1)
        }

print(f"\n  Composite filter results:")
for name, r in composite_results.items():
    bust_red = (baseline['bust_rate'] - r['bust_rate']) / baseline['bust_rate'] * 100 if baseline['bust_rate'] > 0 else 0
    print(f"    {name:40s}: bust={r['bust_rate']:.1f}% (↓{bust_red:.0f}%), "
          f"PF={r['profit_factor']:.2f}, kept={r['pct_kept']:.0f}%")

fig, ax = plt.subplots(figsize=(12, 6))
comp_names = list(composite_results.keys())
comp_busts = [composite_results[n]['bust_rate'] for n in comp_names]
comp_pfs = [composite_results[n]['profit_factor'] for n in comp_names]
comp_kept = [composite_results[n]['pct_kept'] for n in comp_names]

ax.scatter(comp_kept, comp_busts, s=[pf * 50 for pf in comp_pfs], c=comp_pfs,
           cmap='RdYlGn', edgecolors='black', zorder=3)
for i, n in enumerate(comp_names):
    ax.annotate(n.replace('composite_', ''), (comp_kept[i], comp_busts[i]),
                fontsize=7, rotation=15)
ax.axhline(y=baseline['bust_rate'], color='gray', linestyle='--', alpha=0.5)
ax.set_xlabel('Signals Kept (%)')
ax.set_ylabel('Bust Rate (%)')
ax.set_title('Composite Chop Filter — Bust Rate vs Opportunity (size = PF)')
plt.colorbar(ax.collections[0], ax=ax, label='Profit Factor')
ax.grid(True, alpha=0.3)
plt.tight_layout()
savefig('22_composite_filter.png')

# ══════════════════════════════════════════════════════════════
# 5. COST-BENEFIT: NET PNL IMPACT
# ══════════════════════════════════════════════════════════════
print("\n[5/5] Cost-benefit analysis...")

fig, ax = plt.subplots(figsize=(10, 6))

# Baseline net PnL
base_pnl = baseline['net_pnl']

# For key thresholds, show net PnL
key_thresholds = [0.4, 0.5, 0.6, 0.7, 0.8]
pnls = [base_pnl]
labels = ['No filter']
for t in key_thresholds:
    k = f'composite_{t}'
    if k in composite_results:
        pnls.append(composite_results[k]['net_pnl'])
        labels.append(f't={t}')

colors = ['gray'] + ['green' if p > base_pnl else 'red' for p in pnls[1:]]
ax.bar(labels, pnls, color=colors, edgecolor='black')
ax.set_ylabel('Net PnL (pips)')
ax.set_title('Net PnL: Filtering vs No Filter')
ax.grid(True, alpha=0.3)

# Annotate
for i, (lbl, pnl) in enumerate(zip(labels, pnls)):
    ax.text(i, pnl + abs(pnl) * 0.02, f'{pnl:.0f}', ha='center', fontsize=9)

savefig('22_cost_benefit.png')

# ══════════════════════════════════════════════════════════════
# SAVE
# ══════════════════════════════════════════════════════════════
save_results({
    'baseline': baseline,
    'threshold_sweep': threshold_results,
    'indicator_gates': indicator_gates,
    'composite_results': composite_results,
    'best_single_gate': ranked_gates[0][0] if ranked_gates else None,
}, '22_chop_avoidance')

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)
best_composite = min(composite_results.items(), key=lambda x: x[1]['bust_rate'])
print(f"  Best composite: {best_composite[0]} → bust={best_composite[1]['bust_rate']:.1f}%, "
      f"PF={best_composite[1]['profit_factor']:.2f}, kept={best_composite[1]['pct_kept']:.0f}%")
if ranked_gates:
    print(f"  Best single gate: {ranked_gates[0][0]} → bust↓{ranked_gates[0][1]['bust_reduction']:.0f}%")
print("Done.")
