#!/usr/bin/env python3
"""
Step 16b: Supervised Danger Score Entry Gate (replaces 16_online_hmm.py)
=========================================================================
The HMM approach FAILED because unsupervised regimes maximise data likelihood,
not bust separation. This script replaces it with a direct supervised danger
score that uses known predictive features with fixed weights.

KEY FINDINGS (from investigation):
- Choppiness Index (5m, 15m, D1) significantly higher for busts (p<0.002)
- ADX lower for busts (weaker trends, p=0.05)
- Hurst near 0.5 = more random = more dangerous (p=0.02)
- D1_range_atr is the #1 predictor (47% GBM importance)
- Composite danger score (top 5%): bust rate 3.5x separation
- Simple chop > 62: bust rate 2.1x separation

PIPELINE:
1. Load 20yr feature matrix (60,370 cycles, 103 busts)
2. Build DangerScorer class (online, no fitting required)
3. Compute danger scores for all 60k cycles
4. Optimal threshold via walk-forward
5. Permutation test (1000 shuffles)
6. GBM validation (supervised, for comparison only)
7. Comparison table
8. Save outputs + diagnostic plots
9. Bucket cycles into danger levels (replaces HMM regimes)

DEPENDS ON: notebooks/phase2/results/15_features_full.parquet (from script 15)
"""

import os
import sys
import json
import time
import warnings

os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats as sp_stats

warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning)

# --- Paths -------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, 'data')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

FEATURE_PATH = os.path.join(OUTPUT_DIR, '15_features_full.parquet')

# --- Parameters ---------------------------------------------------------------
N_PERMUTATIONS = 1000
WALK_FORWARD_YEARS = 1          # test window size
ADAPTIVE_LOOKBACK = 5000        # cycles for adaptive threshold recalculation
CANDIDATE_PERCENTILES = [70, 75, 80, 85, 90, 95]

np.random.seed(42)

print("=" * 80)
print("STEP 16b: SUPERVISED DANGER SCORE ENTRY GATE")
print("=" * 80)


# =============================================================================
# PART 1: LOAD DATA
# =============================================================================
print(f"\n[1/9] Loading feature matrix from: {FEATURE_PATH}")
t0 = time.time()

if not os.path.exists(FEATURE_PATH):
    print(f"ERROR: Feature matrix not found at {FEATURE_PATH}")
    print("Run script 15 first.")
    sys.exit(1)

df = pd.read_parquet(FEATURE_PATH)
print(f"  Loaded {len(df):,} rows x {len(df.columns)} columns in {time.time()-t0:.1f}s")
print(f"  Busts: {df['is_bust'].sum()} / {len(df)} ({df['is_bust'].mean()*100:.3f}%)")
print(f"  Date range: {df['datetime'].min().date()} to {df['datetime'].max().date()}")

# Identify feature columns
FEATURE_SUFFIXES = ('_adx', '_atr_ratio', '_chop', '_hurst', '_range_atr')
feature_cols = sorted([c for c in df.columns if any(c.endswith(s) for s in FEATURE_SUFFIXES)])
print(f"  Feature columns ({len(feature_cols)}): {feature_cols}")


# =============================================================================
# PART 2: DANGER SCORER CLASS
# =============================================================================
print(f"\n[2/9] Building DangerScorer class...")


class DangerScorer:
    """Online danger score for surefire hedge entry gating.

    Computes a composite danger score in [0, 1] from market features.
    Higher score = more dangerous conditions (choppy, low trend, compressed).

    The scorer maintains running mean/std for online z-score normalisation
    and requires NO fitting on labelled data -- weights are fixed from
    prior GBM importance analysis.

    Components (weighted by GBM importance):
    - D1_range_atr (inverted, 0.30) -- daily range compression
    - 5m_chop (0.15) + 15m_chop (0.15) + D1_chop (0.10) -- choppiness
    - 5m_adx (inverted, 0.10) -- low trend strength
    - 5m_hurst distance from 0.5 (inverted, 0.10) -- randomness
    - 1H_atr_ratio (0.10) -- volatility expansion/contraction
    """

    # Fixed weights from GBM importance analysis
    WEIGHTS = {
        'D1_range_atr': 0.30,   # inverted: LOW range = danger
        '5m_chop':      0.15,   # HIGH chop = danger
        '15m_chop':     0.15,   # HIGH chop = danger
        'D1_chop':      0.10,   # HIGH chop = danger
        '5m_adx':       0.10,   # inverted: LOW adx = danger
        '5m_hurst':     0.10,   # closeness to 0.5 = danger
        '1H_atr_ratio': 0.10,   # HIGH atr_ratio = volatility expansion = danger
    }

    FEATURE_KEYS = list(WEIGHTS.keys())

    def __init__(self):
        """Initialise with empty running stats."""
        self.means = {}
        self.vars = {}     # running variance (Welford's)
        self.n = 0

    def update_stats(self, features_dict):
        """Online update of running mean/variance using Welford's algorithm.

        Args:
            features_dict: dict mapping feature name -> float value.
                           NaN values are skipped.
        """
        self.n += 1
        for key in self.FEATURE_KEYS:
            val = features_dict.get(key, np.nan)
            if np.isnan(val):
                continue

            if key not in self.means:
                self.means[key] = val
                self.vars[key] = 0.0
            else:
                old_mean = self.means[key]
                self.means[key] += (val - old_mean) / self.n
                self.vars[key] += (val - old_mean) * (val - self.means[key])

    def _get_std(self, key):
        """Return current running std for a feature."""
        if key not in self.vars or self.n < 2:
            return 1.0
        return max(np.sqrt(self.vars[key] / (self.n - 1)), 1e-10)

    def _zscore(self, key, val):
        """Z-score a value using running stats. Returns 0 if stats unavailable."""
        if key not in self.means or np.isnan(val):
            return 0.0
        return (val - self.means[key]) / self._get_std(key)

    def score(self, features_dict):
        """Compute danger score from current features.

        Args:
            features_dict: dict mapping feature name -> float value.

        Returns:
            float in [0, 1] where higher = more dangerous.
        """
        if self.n < 30:
            # Not enough history for reliable z-scores
            return 0.5

        components = {}

        # D1_range_atr: LOW = compressed daily range = DANGER
        # Invert: danger = -z(range_atr), then clip to [0,1] via sigmoid
        z = self._zscore('D1_range_atr', features_dict.get('D1_range_atr', np.nan))
        components['D1_range_atr'] = -z  # negative z = below average = danger

        # Choppiness: HIGH = choppy = DANGER
        for key in ['5m_chop', '15m_chop', 'D1_chop']:
            z = self._zscore(key, features_dict.get(key, np.nan))
            components[key] = z  # positive z = above average chop = danger

        # ADX: LOW = weak trend = DANGER
        z = self._zscore('5m_adx', features_dict.get('5m_adx', np.nan))
        components['5m_adx'] = -z  # negative z = below average trend = danger

        # Hurst: CLOSE TO 0.5 = random walk = DANGER
        # Distance from 0.5: smaller = more dangerous
        hurst_val = features_dict.get('5m_hurst', np.nan)
        if not np.isnan(hurst_val):
            dist_from_half = abs(hurst_val - 0.5)
            z = self._zscore('5m_hurst', dist_from_half)
            # We z-score the distance, then invert: small distance = danger
            components['5m_hurst'] = -z
        else:
            components['5m_hurst'] = 0.0

        # 1H ATR ratio: HIGH = volatility expansion
        # This is ambiguous -- high vol can mean trend OR whipsaw.
        # Empirically: high atr_ratio at entry correlates with busts
        z = self._zscore('1H_atr_ratio', features_dict.get('1H_atr_ratio', np.nan))
        components['1H_atr_ratio'] = z  # positive z = above average vol = danger

        # Weighted sum of z-scores
        raw_score = sum(self.WEIGHTS[k] * components[k] for k in self.FEATURE_KEYS)

        # Sigmoid transform to [0, 1]
        # Scale factor of 1.5 maps +/- 2 sigma to roughly 0.05-0.95
        danger = 1.0 / (1.0 + np.exp(-1.5 * raw_score))

        return float(danger)

    def get_params(self):
        """Return current running stats as a serialisable dict."""
        stds = {k: self._get_std(k) for k in self.FEATURE_KEYS if k in self.means}
        return {
            'n': self.n,
            'means': dict(self.means),
            'stds': stds,
            'weights': dict(self.WEIGHTS),
        }

    @classmethod
    def from_params(cls, params):
        """Reconstruct a DangerScorer from saved params.

        Note: This restores means/stds but Welford variance state is
        approximated (sufficient for continued scoring, not exact for
        continued update_stats).
        """
        scorer = cls()
        scorer.n = params['n']
        scorer.means = dict(params['means'])
        # Reconstruct vars from stds: var_sum = std^2 * (n-1)
        scorer.vars = {}
        for k, std in params['stds'].items():
            scorer.vars[k] = (std ** 2) * max(scorer.n - 1, 1)
        return scorer


# Quick sanity check
_test_scorer = DangerScorer()
print(f"  DangerScorer created. Features used: {DangerScorer.FEATURE_KEYS}")
print(f"  Weights sum to: {sum(DangerScorer.WEIGHTS.values()):.2f}")


# =============================================================================
# PART 3: COMPUTE DANGER SCORES FOR ALL 60k CYCLES
# =============================================================================
print(f"\n[3/9] Computing danger scores for {len(df):,} cycles...")
t0 = time.time()

scorer = DangerScorer()
danger_scores = np.zeros(len(df))

# We also need to track hurst distance from 0.5 in our running stats
# The scorer handles this internally in score(), but for update_stats
# we need to pass the raw hurst value AND separately track the distance.
# Actually, for the hurst z-score to work, we need update_stats to see
# the distance-from-0.5 value, not the raw hurst.

# Override: feed distance-from-0.5 as the hurst value to update_stats
for idx in range(len(df)):
    row = df.iloc[idx]

    # Build features dict from row
    features = {}
    for key in DangerScorer.FEATURE_KEYS:
        if key == '5m_hurst':
            # For stats tracking, use the distance from 0.5
            raw_hurst = row.get('5m_hurst', np.nan)
            if not np.isnan(raw_hurst):
                features['5m_hurst'] = abs(raw_hurst - 0.5)
            else:
                features['5m_hurst'] = np.nan
        else:
            features[key] = row.get(key, np.nan)

    # Update running stats BEFORE scoring (online: we see this cycle's
    # features at entry time, so updating stats first is correct --
    # we know the features, we just don't know the outcome yet)
    scorer.update_stats(features)

    # Score using raw features (scorer handles hurst internally)
    raw_features = {key: row.get(key, np.nan) for key in DangerScorer.FEATURE_KEYS}
    danger_scores[idx] = scorer.score(raw_features)

    if (idx + 1) % 10000 == 0:
        print(f"    {idx+1:,} / {len(df):,} scored...")

elapsed = time.time() - t0
print(f"  Scored {len(df):,} cycles in {elapsed:.1f}s")
print(f"  Score stats: mean={np.mean(danger_scores):.4f}, std={np.std(danger_scores):.4f}")
print(f"  Score range: [{np.min(danger_scores):.4f}, {np.max(danger_scores):.4f}]")
print(f"  Median: {np.median(danger_scores):.4f}")

# Distribution by bust vs win
bust_mask = df['is_bust'].values.astype(bool)
win_mask = ~bust_mask
print(f"\n  Bust scores:  mean={danger_scores[bust_mask].mean():.4f}, "
      f"median={np.median(danger_scores[bust_mask]):.4f}")
print(f"  Win scores:   mean={danger_scores[win_mask].mean():.4f}, "
      f"median={np.median(danger_scores[win_mask]):.4f}")

# Mann-Whitney U test
u_stat, u_pval = sp_stats.mannwhitneyu(
    danger_scores[bust_mask], danger_scores[win_mask], alternative='greater'
)
print(f"  Mann-Whitney U test (busts > wins): U={u_stat:.0f}, p={u_pval:.4f}")

# Bust rate by decile
print(f"\n  Bust rate by danger score decile:")
decile_edges = np.percentile(danger_scores, np.arange(0, 101, 10))
for i in range(10):
    lo, hi = decile_edges[i], decile_edges[i + 1]
    if i == 9:
        mask = (danger_scores >= lo) & (danger_scores <= hi)
    else:
        mask = (danger_scores >= lo) & (danger_scores < hi)
    n_in = mask.sum()
    n_busts = bust_mask[mask].sum()
    rate = n_busts / n_in * 100 if n_in > 0 else 0
    print(f"    Decile {i}: [{lo:.4f}, {hi:.4f}] "
          f"n={n_in:>6}, busts={n_busts:>3}, rate={rate:.3f}%")


# =============================================================================
# PART 4: OPTIMAL THRESHOLD VIA WALK-FORWARD
# =============================================================================
print(f"\n[4/9] Walk-forward threshold optimisation...")
t0 = time.time()

# Add year column for walk-forward splits
df['year'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).dt.year
years = sorted(df['year'].unique())
print(f"  Years in data: {years[0]} to {years[-1]} ({len(years)} years)")

# Walk-forward: for each test year, train on all prior years
wf_results = []

for test_year in years[2:]:  # need at least 2 years of training
    train_mask = df['year'].values < test_year
    test_mask = df['year'].values == test_year

    train_scores = danger_scores[train_mask]
    train_busts = bust_mask[train_mask]
    test_scores = danger_scores[test_mask]
    test_busts = bust_mask[test_mask]

    if test_busts.sum() == 0 and len(test_busts) < 100:
        continue

    best_metric = -np.inf
    best_pct = None
    best_threshold = None

    for pct in CANDIDATE_PERCENTILES:
        threshold = np.percentile(train_scores, pct)

        # On train set: measure separation
        train_skip = train_scores >= threshold
        train_kept = ~train_skip

        if train_kept.sum() == 0:
            continue

        train_bust_rate_kept = train_busts[train_kept].mean() if train_kept.sum() > 0 else 0
        train_bust_rate_skip = train_busts[train_skip].mean() if train_skip.sum() > 0 else 0
        train_overall_bust_rate = train_busts.mean()

        # Metric: bust_reduction * trade_retention
        bust_reduction = 1.0 - (train_bust_rate_kept / max(train_overall_bust_rate, 1e-10))
        trade_retention = train_kept.mean()
        metric = bust_reduction * trade_retention

        if metric > best_metric:
            best_metric = metric
            best_pct = pct
            best_threshold = threshold

    if best_threshold is None:
        continue

    # Apply best threshold to test year
    test_skip = test_scores >= best_threshold
    test_kept = ~test_skip

    test_bust_rate_all = test_busts.mean() * 100
    test_bust_rate_kept = (test_busts[test_kept].mean() * 100) if test_kept.sum() > 0 else 0
    test_busts_avoided = test_busts[test_skip].sum()
    test_busts_total = test_busts.sum()
    test_skip_rate = test_skip.mean() * 100

    wf_results.append({
        'test_year': int(test_year),
        'train_years': f"{years[0]}-{test_year-1}",
        'best_percentile': best_pct,
        'threshold': float(best_threshold),
        'metric': float(best_metric),
        'test_cycles': int(len(test_scores)),
        'test_busts': int(test_busts_total),
        'test_bust_rate_all': float(test_bust_rate_all),
        'test_bust_rate_kept': float(test_bust_rate_kept),
        'test_skip_rate': float(test_skip_rate),
        'test_busts_avoided': int(test_busts_avoided),
    })

    print(f"  {test_year}: train on {years[0]}-{test_year-1}, "
          f"best pct={best_pct}, thresh={best_threshold:.4f}, "
          f"skip={test_skip_rate:.1f}%, "
          f"bust rate: {test_bust_rate_all:.3f}% -> {test_bust_rate_kept:.3f}%, "
          f"avoided {test_busts_avoided}/{test_busts_total} busts")

# Overall walk-forward summary
total_test_cycles = sum(r['test_cycles'] for r in wf_results)
total_test_busts = sum(r['test_busts'] for r in wf_results)
total_busts_avoided = sum(r['test_busts_avoided'] for r in wf_results)
avg_skip_rate = np.mean([r['test_skip_rate'] for r in wf_results])
avg_bust_rate_kept = np.mean([r['test_bust_rate_kept'] for r in wf_results])

print(f"\n  Walk-forward summary ({len(wf_results)} test years):")
print(f"    Total test cycles: {total_test_cycles:,}")
print(f"    Total busts: {total_test_busts}")
print(f"    Busts avoided: {total_busts_avoided}")
print(f"    Avg skip rate: {avg_skip_rate:.1f}%")
print(f"    Avg kept bust rate: {avg_bust_rate_kept:.3f}%")

# Select the final optimal threshold using the full training data
# Use the most common best percentile from walk-forward
from collections import Counter
pct_counts = Counter(r['best_percentile'] for r in wf_results)
optimal_pct = pct_counts.most_common(1)[0][0] if pct_counts else 90
optimal_threshold = np.percentile(danger_scores, optimal_pct)

print(f"\n  Optimal percentile: {optimal_pct}th (most common in WF)")
print(f"  Optimal threshold: {optimal_threshold:.4f}")
print(f"  Walk-forward done in {time.time()-t0:.1f}s")


# =============================================================================
# PART 5: PERMUTATION TEST
# =============================================================================
print(f"\n[5/9] Permutation test ({N_PERMUTATIONS} shuffles)...")
t0 = time.time()

# Observed: bust rate in top 10% vs bottom 90%
top_mask = danger_scores >= np.percentile(danger_scores, 90)
bot_mask = ~top_mask
observed_bust_rate_top = bust_mask[top_mask].mean()
observed_bust_rate_bot = bust_mask[bot_mask].mean()
observed_separation = observed_bust_rate_top / max(observed_bust_rate_bot, 1e-10)

print(f"  Observed: top 10% bust rate = {observed_bust_rate_top*100:.3f}%")
print(f"  Observed: bottom 90% bust rate = {observed_bust_rate_bot*100:.3f}%")
print(f"  Observed separation ratio: {observed_separation:.2f}x")

null_separations = np.zeros(N_PERMUTATIONS)

for perm in range(N_PERMUTATIONS):
    shuffled = np.random.permutation(bust_mask)
    rate_top = shuffled[top_mask].mean()
    rate_bot = shuffled[bot_mask].mean()
    null_separations[perm] = rate_top / max(rate_bot, 1e-10)

    if (perm + 1) % 200 == 0:
        print(f"    {perm+1}/{N_PERMUTATIONS} permutations...")

perm_p_value = np.mean(null_separations >= observed_separation)
print(f"\n  Permutation test results:")
print(f"    Observed separation: {observed_separation:.3f}x")
print(f"    Null distribution: mean={null_separations.mean():.3f}, "
      f"std={null_separations.std():.3f}, max={null_separations.max():.3f}")
print(f"    p-value: {perm_p_value:.4f}")

if perm_p_value < 0.01:
    perm_gate = 'PASS'
    print(f"    GATE: PASS (p < 0.01) -- danger score has REAL signal")
elif perm_p_value < 0.05:
    perm_gate = 'MARGINAL'
    print(f"    GATE: MARGINAL (0.01 < p < 0.05)")
else:
    perm_gate = 'FAIL'
    print(f"    GATE: FAIL (p >= 0.05) -- no significant separation")

print(f"  Permutation test done in {time.time()-t0:.1f}s")


# =============================================================================
# PART 6: GBM VALIDATION
# =============================================================================
print(f"\n[6/9] GBM validation (supervised, for comparison only)...")
t0 = time.time()

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, precision_recall_curve, average_precision_score
from sklearn.model_selection import StratifiedKFold

# Use dev/holdout split: 2006-2020 dev, 2021+ holdout
SPLIT_YEAR = 2021
dev_mask = df['year'].values < SPLIT_YEAR
holdout_mask = df['year'].values >= SPLIT_YEAR

X_all = df[feature_cols].values.astype(np.float64)
y_all = bust_mask.astype(int)

# Handle NaNs: fill with column median from dev set
X_dev = X_all[dev_mask].copy()
X_holdout = X_all[holdout_mask].copy()
y_dev = y_all[dev_mask]
y_holdout = y_all[holdout_mask]

# Fill NaN with dev medians
dev_medians = np.nanmedian(X_dev, axis=0)
for j in range(X_dev.shape[1]):
    nan_dev = np.isnan(X_dev[:, j])
    X_dev[nan_dev, j] = dev_medians[j]
    nan_hold = np.isnan(X_holdout[:, j])
    X_holdout[nan_hold, j] = dev_medians[j]

print(f"  Dev set: {len(X_dev):,} cycles, {y_dev.sum()} busts ({y_dev.mean()*100:.3f}%)")
print(f"  Holdout: {len(X_holdout):,} cycles, {y_holdout.sum()} busts ({y_holdout.mean()*100:.3f}%)")

# Train GBM
gbm = GradientBoostingClassifier(
    n_estimators=200,
    max_depth=3,
    learning_rate=0.05,
    min_samples_leaf=20,
    subsample=0.8,
    random_state=42,
)
gbm.fit(X_dev, y_dev)

# Predict probabilities
gbm_probs_dev = gbm.predict_proba(X_dev)[:, 1]
gbm_probs_holdout = gbm.predict_proba(X_holdout)[:, 1]

# AUC
auc_dev = roc_auc_score(y_dev, gbm_probs_dev)
auc_holdout = roc_auc_score(y_holdout, gbm_probs_holdout)
ap_dev = average_precision_score(y_dev, gbm_probs_dev)
ap_holdout = average_precision_score(y_holdout, gbm_probs_holdout)

print(f"\n  GBM Performance:")
print(f"    Dev AUC: {auc_dev:.4f}, AP: {ap_dev:.4f}")
print(f"    Holdout AUC: {auc_holdout:.4f}, AP: {ap_holdout:.4f}")

# Feature importance
gbm_importances = gbm.feature_importances_
importance_order = np.argsort(gbm_importances)[::-1]
print(f"\n  GBM Feature Importance (top 10):")
for rank, idx in enumerate(importance_order[:10]):
    print(f"    {rank+1}. {feature_cols[idx]}: {gbm_importances[idx]:.4f}")

# Precision-recall at various thresholds (holdout)
print(f"\n  GBM Precision-Recall at thresholds (holdout):")
for pct in [90, 95, 97, 99]:
    thresh = np.percentile(gbm_probs_holdout, pct)
    flagged = gbm_probs_holdout >= thresh
    if flagged.sum() > 0:
        precision = y_holdout[flagged].mean()
        recall = y_holdout[flagged].sum() / max(y_holdout.sum(), 1)
        print(f"    Top {100-pct}%: precision={precision*100:.1f}%, "
              f"recall={recall*100:.1f}%, flagged={flagged.sum()}")

# GBM-based threshold for comparison table
gbm_thresh_90 = np.percentile(gbm_probs_holdout, 90)
gbm_skip = gbm_probs_holdout >= gbm_thresh_90

print(f"  GBM validation done in {time.time()-t0:.1f}s")


# =============================================================================
# PART 7: COMPARISON TABLE
# =============================================================================
print(f"\n[7/9] Building comparison table...")

overall_bust_rate = bust_mask.mean() * 100
overall_busts = bust_mask.sum()

# Helper: compute stats for a given skip mask
def compute_filter_stats(skip_mask, label):
    kept = ~skip_mask
    n_total = len(skip_mask)
    n_skip = skip_mask.sum()
    skip_pct = n_skip / n_total * 100
    n_kept = kept.sum()
    busts_kept = bust_mask[kept].sum() if n_kept > 0 else 0
    bust_rate_kept = (busts_kept / n_kept * 100) if n_kept > 0 else 0
    busts_avoided = bust_mask[skip_mask].sum()
    # P&L impact: sum of pnl for kept cycles vs all
    pnl_all = df['pnl'].sum()
    pnl_kept = df['pnl'].values[kept].sum() if n_kept > 0 else 0
    pnl_impact = (pnl_kept - pnl_all) / abs(pnl_all) * 100 if abs(pnl_all) > 0 else 0
    return {
        'method': label,
        'skip_pct': skip_pct,
        'bust_rate': bust_rate_kept,
        'busts_avoided': int(busts_avoided),
        'pnl_impact': pnl_impact,
    }

comparison_rows = []

# No filter baseline
comparison_rows.append({
    'method': 'No filter',
    'skip_pct': 0.0,
    'bust_rate': overall_bust_rate,
    'busts_avoided': 0,
    'pnl_impact': 0.0,
})

# Danger score at various percentiles
for pct in [80, 85, 90, 95]:
    thresh = np.percentile(danger_scores, pct)
    skip = danger_scores >= thresh
    row = compute_filter_stats(skip, f'Danger > {pct}th pct')
    comparison_rows.append(row)

# Walk-forward adaptive threshold
wf_skip = np.zeros(len(df), dtype=bool)
for r in wf_results:
    yr_mask = df['year'].values == r['test_year']
    yr_thresh = r['threshold']
    wf_skip[yr_mask] = danger_scores[yr_mask] >= yr_thresh
# For years not in WF results, use the optimal threshold
for yr in years[:2]:
    yr_mask = df['year'].values == yr
    wf_skip[yr_mask] = danger_scores[yr_mask] >= optimal_threshold
row = compute_filter_stats(wf_skip, 'WF adaptive')
comparison_rows.append(row)

# GBM threshold (holdout only, so compute on full data for fair comparison)
# Train GBM on dev, predict full
gbm_probs_full = np.zeros(len(df))
gbm_probs_full[dev_mask] = gbm_probs_dev
gbm_probs_full[holdout_mask] = gbm_probs_holdout
gbm_skip_full = gbm_probs_full >= np.percentile(gbm_probs_full[gbm_probs_full > 0], 90)
row = compute_filter_stats(gbm_skip_full, 'GBM top 10%')
comparison_rows.append(row)

# Simple chop > 62 baseline
chop_skip = df['5m_chop'].values > 62
row = compute_filter_stats(chop_skip, 'Chop > 62')
comparison_rows.append(row)

print(f"\n  {'Method':<22} {'Skip%':>7} {'Bust Rate':>10} {'Avoided':>9} {'P&L Impact':>11}")
print(f"  {'-'*62}")
for r in comparison_rows:
    print(f"  {r['method']:<22} {r['skip_pct']:>6.1f}% {r['bust_rate']:>9.3f}% "
          f"{r['busts_avoided']:>8} {r['pnl_impact']:>+10.1f}%")


# =============================================================================
# PART 8: SAVE OUTPUTS
# =============================================================================
print(f"\n[8/9] Saving outputs...")

# 1. Danger scores
scores_path = os.path.join(DATA_DIR, 'danger_scores.npy')
np.save(scores_path, danger_scores)
print(f"  Saved: {scores_path} ({len(danger_scores):,} scores)")

# 2. Threshold results
threshold_data = {
    'optimal_percentile': int(optimal_pct),
    'optimal_threshold': float(optimal_threshold),
    'walk_forward_results': wf_results,
    'permutation_test': {
        'gate': perm_gate,
        'p_value': float(perm_p_value),
        'observed_separation': float(observed_separation),
        'null_mean': float(null_separations.mean()),
        'null_std': float(null_separations.std()),
        'n_permutations': N_PERMUTATIONS,
    },
    'comparison_table': comparison_rows,
}
threshold_path = os.path.join(DATA_DIR, 'danger_threshold.json')
with open(threshold_path, 'w') as f:
    json.dump(threshold_data, f, indent=2)
print(f"  Saved: {threshold_path}")

# 3. Scorer params for online use
params = scorer.get_params()
params_path = os.path.join(DATA_DIR, 'danger_scorer_params.json')
with open(params_path, 'w') as f:
    json.dump(params, f, indent=2)
print(f"  Saved: {params_path}")

# 4. GBM results
gbm_results = {
    'dev_auc': float(auc_dev),
    'holdout_auc': float(auc_holdout),
    'dev_ap': float(ap_dev),
    'holdout_ap': float(ap_holdout),
    'feature_importance': {feature_cols[i]: float(gbm_importances[i])
                           for i in importance_order[:15]},
}
gbm_path = os.path.join(DATA_DIR, 'danger_gbm_results.json')
with open(gbm_path, 'w') as f:
    json.dump(gbm_results, f, indent=2)
print(f"  Saved: {gbm_path}")


# =============================================================================
# PART 9: DANGER LEVELS (replaces HMM regimes)
# =============================================================================
print(f"\n[9/9] Bucketing cycles into danger levels...")

# Compute percentile thresholds from online scorer perspective
# (using the full-dataset percentiles for labelling; in live the scorer
# would use its own running percentiles)
pct_50 = np.percentile(danger_scores, 50)
pct_75 = np.percentile(danger_scores, 75)
pct_90 = np.percentile(danger_scores, 90)
pct_95 = np.percentile(danger_scores, 95)

danger_levels = np.zeros(len(df), dtype=int)
danger_levels[danger_scores >= pct_50] = 1
danger_levels[danger_scores >= pct_75] = 2
danger_levels[danger_scores >= pct_90] = 3
danger_levels[danger_scores >= pct_95] = 4

level_names = {0: 'safe', 1: 'caution', 2: 'warning', 3: 'danger', 4: 'extreme'}

print(f"\n  {'Level':<10} {'Name':<10} {'Count':>8} {'Pct':>7} {'Busts':>7} {'Bust Rate':>10}")
print(f"  {'-'*55}")
for lv in range(5):
    mask = danger_levels == lv
    n_in = mask.sum()
    n_busts = bust_mask[mask].sum()
    rate = n_busts / n_in * 100 if n_in > 0 else 0
    print(f"  {lv:<10} {level_names[lv]:<10} {n_in:>8} {n_in/len(df)*100:>6.1f}% "
          f"{n_busts:>7} {rate:>9.3f}%")

# Save danger levels as replacement for regime labels
level_df = pd.DataFrame({
    'danger_score': danger_scores,
    'danger_level': danger_levels,
    'danger_level_name': [level_names[lv] for lv in danger_levels],
})
# Carry over key metadata from original df
for col in ['entry_bar', 'timestamp', 'is_bust', 'pnl', 'pnl_pct',
            'direction', 'duration_bars', 'levels_used', 'datetime']:
    if col in df.columns:
        level_df[col] = df[col].values

levels_path = os.path.join(DATA_DIR, 'danger_levels.parquet')
level_df.to_parquet(levels_path, index=False)
print(f"\n  Saved: {levels_path}")

# Also save thresholds for online use
level_thresholds = {
    'percentiles': {50: float(pct_50), 75: float(pct_75),
                    90: float(pct_90), 95: float(pct_95)},
    'level_names': level_names,
}
level_thresh_path = os.path.join(DATA_DIR, 'danger_level_thresholds.json')
with open(level_thresh_path, 'w') as f:
    json.dump(level_thresholds, f, indent=2, default=str)
print(f"  Saved: {level_thresh_path}")


# =============================================================================
# DIAGNOSTIC PLOTS
# =============================================================================
print(f"\n  Generating diagnostic plots...")

plt.style.use('seaborn-v0_8-darkgrid')
fig = plt.figure(figsize=(24, 24))
gs = fig.add_gridspec(4, 3, hspace=0.40, wspace=0.30)

# --- Plot 1: Danger score distribution (bust vs win) -------------------------
ax1 = fig.add_subplot(gs[0, 0])
bins = np.linspace(0, 1, 50)
ax1.hist(danger_scores[win_mask], bins=bins, alpha=0.6, color='#27ae60',
         label=f'Win (n={win_mask.sum():,})', density=True)
ax1.hist(danger_scores[bust_mask], bins=bins, alpha=0.7, color='#e74c3c',
         label=f'Bust (n={bust_mask.sum()})', density=True)
ax1.axvline(optimal_threshold, color='black', linestyle='--', linewidth=2,
            label=f'Threshold ({optimal_pct}th pct)')
ax1.set_xlabel('Danger Score')
ax1.set_ylabel('Density')
ax1.set_title('Danger Score Distribution: Bust vs Win', fontweight='bold')
ax1.legend(fontsize=8)

# --- Plot 2: Bust rate by decile ---------------------------------------------
ax2 = fig.add_subplot(gs[0, 1])
decile_rates = []
decile_labels = []
for i in range(10):
    lo, hi = decile_edges[i], decile_edges[i + 1]
    if i == 9:
        mask = (danger_scores >= lo) & (danger_scores <= hi)
    else:
        mask = (danger_scores >= lo) & (danger_scores < hi)
    n_in = mask.sum()
    rate = bust_mask[mask].mean() * 100 if n_in > 0 else 0
    decile_rates.append(rate)
    decile_labels.append(f'D{i}')

colors_dec = ['#27ae60'] * 7 + ['#f39c12'] * 2 + ['#e74c3c']
ax2.bar(range(10), decile_rates, color=colors_dec, edgecolor='black', alpha=0.8)
ax2.axhline(overall_bust_rate, color='black', linestyle='--', linewidth=1,
            label=f'Overall: {overall_bust_rate:.3f}%')
ax2.set_xticks(range(10))
ax2.set_xticklabels(decile_labels)
ax2.set_xlabel('Danger Score Decile')
ax2.set_ylabel('Bust Rate (%)')
ax2.set_title('Bust Rate by Danger Score Decile', fontweight='bold')
ax2.legend(fontsize=8)
for i, rate in enumerate(decile_rates):
    if rate > 0:
        ax2.text(i, rate + 0.005, f'{rate:.2f}%', ha='center', fontsize=7)

# --- Plot 3: Permutation test ------------------------------------------------
ax3 = fig.add_subplot(gs[0, 2])
ax3.hist(null_separations, bins=50, color='#3498db', alpha=0.7, edgecolor='black',
         density=True, label='Null distribution')
ax3.axvline(observed_separation, color='red', linewidth=2, linestyle='--',
            label=f'Observed: {observed_separation:.2f}x')
ax3.set_xlabel('Bust Rate Separation (top 10% / bottom 90%)')
ax3.set_ylabel('Density')
ax3.set_title(f'Permutation Test (p={perm_p_value:.4f})\nGate: {perm_gate}',
              fontweight='bold')
ax3.legend(fontsize=8)

# --- Plot 4: Walk-forward results ---------------------------------------------
ax4 = fig.add_subplot(gs[1, 0])
wf_years = [r['test_year'] for r in wf_results]
wf_bust_all = [r['test_bust_rate_all'] for r in wf_results]
wf_bust_kept = [r['test_bust_rate_kept'] for r in wf_results]
wf_skip_rates = [r['test_skip_rate'] for r in wf_results]

ax4_twin = ax4.twinx()
ax4.bar(np.array(range(len(wf_years))) - 0.2, wf_bust_all, 0.4,
        color='#e74c3c', alpha=0.6, label='All bust rate')
ax4.bar(np.array(range(len(wf_years))) + 0.2, wf_bust_kept, 0.4,
        color='#27ae60', alpha=0.6, label='Kept bust rate')
ax4_twin.plot(range(len(wf_years)), wf_skip_rates, 'k--o', markersize=4,
              label='Skip rate %')
ax4.set_xticks(range(len(wf_years)))
ax4.set_xticklabels(wf_years, fontsize=7, rotation=45)
ax4.set_xlabel('Test Year')
ax4.set_ylabel('Bust Rate (%)')
ax4_twin.set_ylabel('Skip Rate (%)')
ax4.set_title('Walk-Forward Threshold Results', fontweight='bold')
ax4.legend(loc='upper left', fontsize=7)
ax4_twin.legend(loc='upper right', fontsize=7)

# --- Plot 5: GBM feature importance ------------------------------------------
ax5 = fig.add_subplot(gs[1, 1])
top_n = min(15, len(feature_cols))
top_idx = importance_order[:top_n]
ax5.barh(range(top_n), gbm_importances[top_idx], color='#3498db',
         edgecolor='black', alpha=0.8)
ax5.set_yticks(range(top_n))
ax5.set_yticklabels([feature_cols[i] for i in top_idx], fontsize=7)
ax5.set_xlabel('GBM Feature Importance')
ax5.set_title('GBM Feature Importance (top 15)', fontweight='bold')
ax5.invert_yaxis()

# --- Plot 6: GBM ROC (holdout) -----------------------------------------------
ax6 = fig.add_subplot(gs[1, 2])
from sklearn.metrics import roc_curve
fpr, tpr, _ = roc_curve(y_holdout, gbm_probs_holdout)
ax6.plot(fpr, tpr, 'b-', linewidth=2, label=f'GBM (AUC={auc_holdout:.3f})')
# Also plot danger score ROC on holdout
ds_holdout = danger_scores[holdout_mask]
fpr_ds, tpr_ds, _ = roc_curve(y_holdout, ds_holdout)
auc_ds_holdout = roc_auc_score(y_holdout, ds_holdout)
ax6.plot(fpr_ds, tpr_ds, 'r--', linewidth=2,
         label=f'DangerScore (AUC={auc_ds_holdout:.3f})')
ax6.plot([0, 1], [0, 1], 'k:', alpha=0.5)
ax6.set_xlabel('False Positive Rate')
ax6.set_ylabel('True Positive Rate')
ax6.set_title('ROC Curve (Holdout)', fontweight='bold')
ax6.legend(fontsize=8)

# --- Plot 7: Danger score time series ----------------------------------------
ax7 = fig.add_subplot(gs[2, :])
timestamps_dt = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
ax7.scatter(timestamps_dt[win_mask], danger_scores[win_mask],
            c='#27ae60', s=2, alpha=0.15, label='Win')
ax7.scatter(timestamps_dt[bust_mask], danger_scores[bust_mask],
            c='#e74c3c', s=40, alpha=0.9, marker='v', zorder=5,
            label=f'Bust (n={bust_mask.sum()})')
ax7.axhline(optimal_threshold, color='black', linestyle='--', linewidth=1.5,
            label=f'Threshold ({optimal_pct}th pct = {optimal_threshold:.3f})')
ax7.set_xlabel('Date')
ax7.set_ylabel('Danger Score')
ax7.set_title('Danger Score Over Time', fontweight='bold')
ax7.legend(fontsize=8, loc='upper left')
ax7.tick_params(axis='x', rotation=30)

# --- Plot 8: Danger level distribution with bust rates ------------------------
ax8 = fig.add_subplot(gs[3, 0])
level_counts = [np.sum(danger_levels == lv) for lv in range(5)]
level_bust_rates = []
for lv in range(5):
    mask = danger_levels == lv
    rate = bust_mask[mask].mean() * 100 if mask.sum() > 0 else 0
    level_bust_rates.append(rate)

colors_lv = ['#27ae60', '#2ecc71', '#f39c12', '#e67e22', '#e74c3c']
bars = ax8.bar(range(5), level_counts, color=colors_lv, edgecolor='black', alpha=0.8)
ax8.set_xticks(range(5))
ax8.set_xticklabels([f'L{i}\n{level_names[i]}' for i in range(5)], fontsize=8)
ax8.set_ylabel('Count')
ax8.set_title('Danger Level Distribution', fontweight='bold')
for i, (cnt, rate) in enumerate(zip(level_counts, level_bust_rates)):
    ax8.text(i, cnt + 50, f'{cnt:,}\n({rate:.2f}%)', ha='center', fontsize=7)

# --- Plot 9: Comparison table as text ----------------------------------------
ax9 = fig.add_subplot(gs[3, 1])
ax9.axis('off')
table_data = []
headers = ['Method', 'Skip%', 'Bust Rate', 'Avoided', 'P&L']
for r in comparison_rows:
    table_data.append([
        r['method'],
        f"{r['skip_pct']:.1f}%",
        f"{r['bust_rate']:.3f}%",
        str(r['busts_avoided']),
        f"{r['pnl_impact']:+.1f}%",
    ])
table = ax9.table(cellText=table_data, colLabels=headers,
                   loc='center', cellLoc='center')
table.auto_set_font_size(False)
table.set_fontsize(8)
table.scale(1.0, 1.5)
# Color header
for j in range(len(headers)):
    table[0, j].set_facecolor('#3498db')
    table[0, j].set_text_props(color='white', fontweight='bold')
# Color best row (highest busts avoided with reasonable skip)
ax9.set_title('Filter Comparison', fontweight='bold', pad=20)

# --- Plot 10: Cumulative bust avoidance curve ---------------------------------
ax10 = fig.add_subplot(gs[3, 2])
# Sort by danger score descending
sorted_idx = np.argsort(danger_scores)[::-1]
cum_busts = np.cumsum(bust_mask[sorted_idx])
total_busts = bust_mask.sum()
pct_skipped = np.arange(1, len(df) + 1) / len(df) * 100
pct_busts_caught = cum_busts / total_busts * 100

ax10.plot(pct_skipped, pct_busts_caught, 'b-', linewidth=2)
ax10.plot([0, 100], [0, 100], 'k:', alpha=0.5, label='Random')
# Mark key points
for pct in [5, 10, 20]:
    idx = int(len(df) * pct / 100)
    caught = pct_busts_caught[idx] if idx < len(pct_busts_caught) else 100
    ax10.plot(pct, caught, 'ro', markersize=8)
    ax10.annotate(f'{pct}% skip\n{caught:.0f}% busts', (pct, caught),
                  textcoords="offset points", xytext=(10, -10), fontsize=7)
ax10.set_xlabel('% Cycles Skipped (highest danger first)')
ax10.set_ylabel('% Busts Caught')
ax10.set_title('Cumulative Bust Capture Curve', fontweight='bold')
ax10.legend(fontsize=8)
ax10.set_xlim(0, 50)
ax10.set_ylim(0, 100)

plt.suptitle(
    f'Step 16b: Supervised Danger Score Entry Gate\n'
    f'{len(df):,} cycles | {bust_mask.sum()} busts | '
    f'Permutation {perm_gate} (p={perm_p_value:.4f}) | '
    f'GBM AUC={auc_holdout:.3f} | '
    f'Threshold={optimal_pct}th pct',
    fontsize=14, fontweight='bold', y=1.01
)

plt.tight_layout()
plot_path = os.path.join(OUTPUT_DIR, '16b_danger_score.png')
fig.savefig(plot_path, dpi=150, bbox_inches='tight')
plt.close()
print(f"  Saved plot: {plot_path}")


# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

print(f"""
  DATA:
    Feature matrix: {len(df):,} cycles, {bust_mask.sum()} busts ({overall_bust_rate:.3f}%)
    Date range: {df['datetime'].min().date()} to {df['datetime'].max().date()}

  DANGER SCORER (online, no fitting):
    Features: {DangerScorer.FEATURE_KEYS}
    Score range: [{danger_scores.min():.4f}, {danger_scores.max():.4f}]
    Bust mean score: {danger_scores[bust_mask].mean():.4f}
    Win mean score:  {danger_scores[win_mask].mean():.4f}
    Mann-Whitney p:  {u_pval:.4f}

  PERMUTATION TEST:
    Separation: {observed_separation:.2f}x (top 10% vs bottom 90%)
    p-value: {perm_p_value:.4f}
    Gate: {perm_gate}

  WALK-FORWARD THRESHOLD:
    Optimal percentile: {optimal_pct}th
    Optimal threshold: {optimal_threshold:.4f}
    Avg skip rate: {avg_skip_rate:.1f}%
    Avg kept bust rate: {avg_bust_rate_kept:.3f}%
    Total busts avoided: {total_busts_avoided}/{total_test_busts}

  GBM VALIDATION (supervised):
    Holdout AUC: {auc_holdout:.4f}
    Holdout AP:  {ap_holdout:.4f}
    DangerScore holdout AUC: {auc_ds_holdout:.4f}

  DANGER LEVELS (replaces HMM regimes):""")
for lv in range(5):
    mask = danger_levels == lv
    n_in = mask.sum()
    rate = bust_mask[mask].mean() * 100 if n_in > 0 else 0
    print(f"    Level {lv} ({level_names[lv]:>8}): {n_in:>6} cycles, bust rate {rate:.3f}%")

print(f"""
  COMPARISON TABLE:""")
print(f"    {'Method':<22} {'Skip%':>7} {'Bust Rate':>10} {'Avoided':>9} {'P&L':>8}")
for r in comparison_rows:
    print(f"    {r['method']:<22} {r['skip_pct']:>6.1f}% {r['bust_rate']:>9.3f}% "
          f"{r['busts_avoided']:>8} {r['pnl_impact']:>+7.1f}%")

print(f"""
  SAVED ARTIFACTS:
    {scores_path}
    {threshold_path}
    {params_path}
    {gbm_path}
    {levels_path}
    {level_thresh_path}
    {plot_path}
""")
print("=" * 80)
