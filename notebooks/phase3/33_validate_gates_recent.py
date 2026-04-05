"""
Script 33 — Validate ALL Gates on 2024-2025
=============================================
The hard question: Do the gates we found (DM_14, vol filter, confidence score)
actually work on the most recent data? Or do they only look good on historical?

Tests:
  1. DM_14 gate on 2024-2025 vs historical
  2. Vol (NATR) filter on 2024-2025
  3. Confidence score gate on 2024-2025
  4. Combined best config on 2024-2025
  5. Walk-forward: train on 2020-2023, test on 2024-2025
"""
from utils import *
import qengine.indicators as ta
import warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("Script 33 — Validate Gates on 2024-2025")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# 1. LOAD TRAIN AND TEST DATA
# ══════════════════════════════════════════════════════════════
print("\n[1/6] Loading train (2020-2023) and test (2024-2025) data...", flush=True)
train_candles = load_candles(timeframe='5m', start_date='2020-01-03', end_date='2023-12-31')
test_candles = load_candles(timeframe='5m', start_date='2024-01-03', end_date='2025-12-30')
print(f"  Train: {len(train_candles):,} candles")
print(f"  Test:  {len(test_candles):,} candles")

cfg = SimConfig(sizing_curve='sqrt', sizing_factor=2.0, max_levels=12,
                hedge_dist_pips=15, tp_pips=15)

train_signals = find_ema_crossover_signals(train_candles, 8, 21)
test_signals = find_ema_crossover_signals(test_candles, 8, 21)
print(f"  Train signals: {len(train_signals)}, Test signals: {len(test_signals)}")

# Baselines
train_results = run_cycles_on_signals(train_candles, train_signals, cfg)
test_results = run_cycles_on_signals(test_candles, test_signals, cfg)
train_base = cycle_summary(train_results)
test_base = cycle_summary(test_results)

print(f"  Train baseline: {train_base['n_cycles']} cycles, bust={train_base['bust_rate']:.2f}%, PF={train_base['profit_factor']:.2f}")
print(f"  Test baseline:  {test_base['n_cycles']} cycles, bust={test_base['bust_rate']:.2f}%, PF={test_base['profit_factor']:.2f}")

# ══════════════════════════════════════════════════════════════
# 2. DM_14 GATE
# ══════════════════════════════════════════════════════════════
print("\n[2/6] Testing DM_14 gate...", flush=True)

# Compute DM on both sets
dm_train = ta.dm(train_candles, period=14, sequential=True)
dm_test = ta.dm(test_candles, period=14, sequential=True)

# Extract plus DM
dm_train_plus = dm_train.plus
dm_test_plus = dm_test.plus

# Find best threshold on TRAIN data
best_pf_train = 0
best_thresh_dm = None
best_direction = None

for direction in ['higher_busts', 'lower_busts']:
    valid = dm_train_plus[~np.isnan(dm_train_plus)]
    for pct in [30, 50, 70]:
        thresh = np.percentile(valid, pct)
        if direction == 'higher_busts':
            filtered = [(idx, d) for idx, d in train_signals
                        if idx < len(dm_train_plus) and (np.isnan(dm_train_plus[idx]) or dm_train_plus[idx] <= thresh)]
        else:
            filtered = [(idx, d) for idx, d in train_signals
                        if idx < len(dm_train_plus) and (np.isnan(dm_train_plus[idx]) or dm_train_plus[idx] >= thresh)]
        if len(filtered) < 30:
            continue
        results = run_cycles_on_signals(train_candles, filtered, cfg)
        s = cycle_summary(results)
        if s['profit_factor'] > best_pf_train:
            best_pf_train = s['profit_factor']
            best_thresh_dm = thresh
            best_direction = direction

print(f"  Train: best DM threshold={best_thresh_dm:.4f}, direction={best_direction}, PF={best_pf_train:.3f}")

# Apply SAME threshold to TEST data
if best_direction == 'higher_busts':
    test_filtered_dm = [(idx, d) for idx, d in test_signals
                        if idx < len(dm_test_plus) and (np.isnan(dm_test_plus[idx]) or dm_test_plus[idx] <= best_thresh_dm)]
else:
    test_filtered_dm = [(idx, d) for idx, d in test_signals
                        if idx < len(dm_test_plus) and (np.isnan(dm_test_plus[idx]) or dm_test_plus[idx] >= best_thresh_dm)]

test_dm_results = run_cycles_on_signals(test_candles, test_filtered_dm, cfg)
test_dm = cycle_summary(test_dm_results)
pct_kept = len(test_filtered_dm) / len(test_signals) * 100

print(f"  Test with DM gate: {test_dm['n_cycles']} cycles, bust={test_dm['bust_rate']:.2f}%, PF={test_dm['profit_factor']:.2f}, kept={pct_kept:.0f}%")
print(f"  Test improvement: PF {test_base['profit_factor']:.2f} → {test_dm['profit_factor']:.2f}")

# ══════════════════════════════════════════════════════════════
# 3. VOL (NATR) FILTER
# ══════════════════════════════════════════════════════════════
print("\n[3/6] Testing NATR vol filter...", flush=True)

natr_train = ta.natr(train_candles, period=14, sequential=True)
natr_test = ta.natr(test_candles, period=14, sequential=True)

# Find percentile cutoff on TRAIN: skip low vol entries
valid_natr = natr_train[~np.isnan(natr_train)]
vol_thresholds = {}

print(f"  {'Cutoff':>8s} {'Train PF':>9s} {'Test PF':>8s} {'Test Bust':>10s} {'Kept%':>6s} {'Verdict':>10s}")
print(f"  {'-'*55}")

for pct in [10, 20, 30, 40, 50]:
    thresh = np.percentile(valid_natr, pct)

    # Train
    train_filt = [(idx, d) for idx, d in train_signals
                  if idx < len(natr_train) and (np.isnan(natr_train[idx]) or natr_train[idx] >= thresh)]
    train_r = run_cycles_on_signals(train_candles, train_filt, cfg)
    train_s = cycle_summary(train_r)

    # Test
    test_filt = [(idx, d) for idx, d in test_signals
                 if idx < len(natr_test) and (np.isnan(natr_test[idx]) or natr_test[idx] >= thresh)]
    test_r = run_cycles_on_signals(test_candles, test_filt, cfg)
    test_s = cycle_summary(test_r)
    kept = len(test_filt) / len(test_signals) * 100

    vol_thresholds[pct] = {
        'threshold': round(thresh, 6),
        'train_pf': train_s['profit_factor'],
        'test_pf': test_s['profit_factor'],
        'test_bust': test_s['bust_rate'],
        'kept': round(kept, 1),
    }

    verdict = "WORKS" if test_s['profit_factor'] > test_base['profit_factor'] else "FAILS"
    print(f"  p{pct:>5d}% {train_s['profit_factor']:>9.2f} {test_s['profit_factor']:>8.2f} "
          f"{test_s['bust_rate']:>9.2f}% {kept:>5.1f}% {verdict:>10s}")

# ══════════════════════════════════════════════════════════════
# 4. CONFIDENCE SCORE
# ══════════════════════════════════════════════════════════════
print("\n[4/6] Testing confidence score gate...", flush=True)

adx_train = ta.adx(train_candles, period=14, sequential=True)
adx_test = ta.adx(test_candles, period=14, sequential=True)
er_train = ta.er(train_candles, period=100, sequential=True)
er_test = ta.er(test_candles, period=100, sequential=True)

def compute_confidence_array(natr_arr, adx_arr, er_arr):
    n = len(natr_arr)
    conf = np.full(n, 0.5)
    for i in range(n):
        score = 0; count = 0
        if not np.isnan(natr_arr[i]):
            score += np.clip(natr_arr[i] / 0.1, 0, 1); count += 1
        if not np.isnan(adx_arr[i]):
            score += np.clip((adx_arr[i] - 15) / 30, 0, 1); count += 1
        if not np.isnan(er_arr[i]):
            score += np.clip(er_arr[i] / 0.4, 0, 1); count += 1
        conf[i] = score / count if count > 0 else 0.5
    return conf

conf_train = compute_confidence_array(natr_train, adx_train, er_train)
conf_test = compute_confidence_array(natr_test, adx_test, er_test)

print(f"  {'Threshold':>10s} {'Train PF':>9s} {'Test PF':>8s} {'Test Bust':>10s} {'Kept%':>6s} {'Verdict':>10s}")
print(f"  {'-'*58}")

conf_results = {}
for thresh in [0.3, 0.4, 0.5, 0.6, 0.7]:
    train_filt = [(idx, d) for idx, d in train_signals
                  if idx < len(conf_train) and conf_train[idx] >= thresh]
    test_filt = [(idx, d) for idx, d in test_signals
                 if idx < len(conf_test) and conf_test[idx] >= thresh]

    if len(train_filt) < 30 or len(test_filt) < 20:
        continue

    train_r = run_cycles_on_signals(train_candles, train_filt, cfg)
    test_r = run_cycles_on_signals(test_candles, test_filt, cfg)
    train_s = cycle_summary(train_r)
    test_s = cycle_summary(test_r)
    kept = len(test_filt) / len(test_signals) * 100

    conf_results[thresh] = {
        'train_pf': train_s['profit_factor'],
        'test_pf': test_s['profit_factor'],
        'test_bust': test_s['bust_rate'],
        'kept': round(kept, 1),
    }

    verdict = "WORKS" if test_s['profit_factor'] > test_base['profit_factor'] else "FAILS"
    print(f"  {thresh:>10.2f} {train_s['profit_factor']:>9.2f} {test_s['profit_factor']:>8.2f} "
          f"{test_s['bust_rate']:>9.2f}% {kept:>5.1f}% {verdict:>10s}")

# ══════════════════════════════════════════════════════════════
# 5. COMBINED BEST CONFIG
# ══════════════════════════════════════════════════════════════
print("\n[5/6] Testing combined best config on 2024-2025...", flush=True)

# Combine: DM gate + NATR p20 filter + confidence >= 0.4
natr_thresh_20 = np.percentile(natr_train[~np.isnan(natr_train)], 20)

strategies = {
    'baseline': test_signals,
    'dm_only': test_filtered_dm,
    'natr_p20': [(idx, d) for idx, d in test_signals
                 if idx < len(natr_test) and (np.isnan(natr_test[idx]) or natr_test[idx] >= natr_thresh_20)],
    'conf_0.4': [(idx, d) for idx, d in test_signals
                 if idx < len(conf_test) and conf_test[idx] >= 0.4],
    'conf_0.5': [(idx, d) for idx, d in test_signals
                 if idx < len(conf_test) and conf_test[idx] >= 0.5],
}

# Combined: DM + NATR + confidence
combined_signals = []
for idx, d in test_signals:
    if idx >= len(dm_test_plus) or idx >= len(natr_test) or idx >= len(conf_test):
        continue
    dm_ok = np.isnan(dm_test_plus[idx]) or (dm_test_plus[idx] <= best_thresh_dm if best_direction == 'higher_busts' else dm_test_plus[idx] >= best_thresh_dm)
    natr_ok = np.isnan(natr_test[idx]) or natr_test[idx] >= natr_thresh_20
    conf_ok = conf_test[idx] >= 0.4
    if dm_ok and natr_ok and conf_ok:
        combined_signals.append((idx, d))
strategies['combined'] = combined_signals

print(f"\n  {'Strategy':<18s} {'Cycles':>7s} {'Bust%':>6s} {'PF':>6s} {'PnL':>8s} {'Kept%':>6s}")
print(f"  {'-'*55}")

test_comparison = {}
for name, sigs in strategies.items():
    results = run_cycles_on_signals(test_candles, sigs, cfg)
    s = cycle_summary(results)
    kept = len(sigs) / len(test_signals) * 100
    test_comparison[name] = {**s, 'kept': round(kept, 1)}
    print(f"  {name:<18s} {s['n_cycles']:>7d} {s['bust_rate']:>5.2f}% {s['profit_factor']:>6.2f} "
          f"{s['net_pnl']:>8.0f} {kept:>5.1f}%")

# ══════════════════════════════════════════════════════════════
# 6. PLOTS AND SAVE
# ══════════════════════════════════════════════════════════════
print("\n[6/6] Plotting...", flush=True)

fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# Train vs Test PF for vol thresholds
ax = axes[0]
pcts = sorted(vol_thresholds.keys())
train_pfs = [vol_thresholds[p]['train_pf'] for p in pcts]
test_pfs = [vol_thresholds[p]['test_pf'] for p in pcts]
x = np.arange(len(pcts))
ax.bar(x - 0.15, train_pfs, 0.3, label='Train (2020-23)', color='steelblue')
ax.bar(x + 0.15, test_pfs, 0.3, label='Test (2024-25)', color='orange')
ax.set_xticks(x)
ax.set_xticklabels([f'p{p}' for p in pcts])
ax.axhline(y=test_base['profit_factor'], color='red', linestyle='--', alpha=0.5, label=f"Test base PF={test_base['profit_factor']:.2f}")
ax.set_ylabel('Profit Factor')
ax.set_title('NATR Vol Filter: Train vs Test')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Strategy comparison on 2024-2025
ax = axes[1]
strat_names = list(test_comparison.keys())
strat_pfs = [test_comparison[s]['profit_factor'] for s in strat_names]
colors = ['green' if pf > test_base['profit_factor'] else 'red' for pf in strat_pfs]
ax.barh(strat_names, strat_pfs, color=colors, edgecolor='black')
ax.axvline(x=test_base['profit_factor'], color='gray', linestyle='--')
ax.axvline(x=1.0, color='red', linestyle=':', alpha=0.5)
ax.set_xlabel('Profit Factor')
ax.set_title('All Gates on 2024-2025 Test Data')
ax.grid(True, alpha=0.3)

# Generalization ratio
ax = axes[2]
if conf_results:
    threshs = sorted(conf_results.keys())
    gen_ratios = [conf_results[t]['test_pf'] / max(conf_results[t]['train_pf'], 0.01) for t in threshs]
    ax.plot(threshs, gen_ratios, 'go-', linewidth=2)
    ax.axhline(y=1.0, color='gray', linestyle='--', label='Perfect generalization')
    ax.set_xlabel('Confidence Threshold')
    ax.set_ylabel('Test PF / Train PF')
    ax.set_title('Generalization Ratio')
    ax.legend()
    ax.grid(True, alpha=0.3)

plt.tight_layout()
savefig('33_validate_gates.png')

save_results({
    'train_baseline': train_base,
    'test_baseline': test_base,
    'dm_gate': {'threshold': best_thresh_dm, 'direction': best_direction,
                'train_pf': best_pf_train, 'test_pf': test_dm['profit_factor'],
                'test_bust': test_dm['bust_rate']},
    'vol_thresholds': vol_thresholds,
    'confidence_gates': conf_results,
    'test_comparison': test_comparison,
}, '33_validate_gates')

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)
print(f"  Test baseline (2024-25): PF={test_base['profit_factor']:.2f}")
best_strat = max(test_comparison.items(), key=lambda x: x[1]['profit_factor'])
print(f"  Best on test: {best_strat[0]} → PF={best_strat[1]['profit_factor']:.2f}")
worst_strat = min(test_comparison.items(), key=lambda x: x[1]['profit_factor'])

# Generalization verdict
dm_gen = test_dm['profit_factor'] / best_pf_train if best_pf_train > 0 else 0
print(f"  DM gate generalization: {dm_gen:.2f} (train PF={best_pf_train:.2f} → test PF={test_dm['profit_factor']:.2f})")

if best_strat[1]['profit_factor'] > test_base['profit_factor'] * 1.05:
    print(f"  VERDICT: Gates provide real improvement on 2024-2025")
else:
    print(f"  VERDICT: Gates do NOT meaningfully improve on 2024-2025")
print("Done.", flush=True)
