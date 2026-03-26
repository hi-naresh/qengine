#!/usr/bin/env python3
"""
Step 16: Online Bayesian HMM Regime Detection (Phase B)
========================================================
Fit a Hidden Markov Model to the feature matrix from Phase A to discover
market regimes, then build an online Bayesian updater for real-time regime
inference during live trading.

PIPELINE:
1. Load feature matrix (25 features + labels from script 15)
2. Standardize features (z-score)
3. Fit HMM with n_states in [3, 5, 7, 10, 15, 20], select by BIC
4. Implement OnlineBayesianHMM class with exponential decay
5. Compute P(bust | regime) for each regime
6. CRITICAL GATE: Permutation test (1000 shuffles) for significance
7. Save model artifacts + plots

DEPENDS ON: notebooks/phase2/data/feature_matrix.parquet (from script 15)
"""

import os
import sys
import json
import time
import pickle
import warnings

os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from sklearn.preprocessing import StandardScaler
from hmmlearn import hmm

warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning)

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, 'data')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

FEATURE_MATRIX_PATH = os.path.join(DATA_DIR, 'feature_matrix.parquet')

# ─── Parameters ───────────────────────────────────────────────────────────────
CANDIDATE_STATES = [3, 5, 7, 10, 15, 20]
N_PERMUTATIONS = 1000
SIGNIFICANCE_REJECT = 0.01   # p < 0.01: regimes have real signal
SIGNIFICANCE_ACCEPT = 0.05   # p > 0.05: busts are IID, stop
HMM_N_ITER = 200
HMM_COVARIANCE_TYPE = 'full'
HMM_RANDOM_STATE = 42
DECAY_LAMBDA = 0.995  # exponential decay for online updates

np.random.seed(42)

# =============================================================================
# PART 1: LOAD AND PREPARE DATA
# =============================================================================
print("=" * 80)
print("STEP 16: ONLINE BAYESIAN HMM REGIME DETECTION")
print("=" * 80)

print(f"\nLoading feature matrix from: {FEATURE_MATRIX_PATH}")
if not os.path.exists(FEATURE_MATRIX_PATH):
    print(f"ERROR: Feature matrix not found at {FEATURE_MATRIX_PATH}")
    print("Run script 15 (Phase A) first to generate the feature matrix.")
    sys.exit(1)

t0 = time.time()
df = pd.read_parquet(FEATURE_MATRIX_PATH)
print(f"Loaded {len(df):,} rows x {len(df.columns)} columns in {time.time()-t0:.1f}s")

# Identify feature columns vs label/metadata columns
# Feature columns are the 25 regime descriptors: {timeframe}_{indicator}
FEATURE_SUFFIXES = ('_adx', '_atr_ratio', '_chop', '_hurst', '_range_atr')
feature_cols = [c for c in df.columns if any(c.endswith(s) for s in FEATURE_SUFFIXES)]
# Label columns for bust detection
LABEL_COLS = ['level_reached', 'is_bust', 'bust_binary', 'choppy_bust', 'choppy_bust_binary',
              'pnl', 'pnl_pct', 'cycle_pnl', 'entry_bar_index', 'entry_bar',
              'timestamp', 'entry_price', 'atr_at_entry', 'direction',
              'duration_bars', 'levels_used', 'datetime']
label_cols_present = [c for c in LABEL_COLS if c in df.columns]

print(f"Feature columns ({len(feature_cols)}): {feature_cols[:10]}{'...' if len(feature_cols)>10 else ''}")
print(f"Label columns ({len(label_cols_present)}): {label_cols_present}")

# Extract features and labels
X_raw = df[feature_cols].values.astype(np.float64)
labels = df[label_cols_present].copy()

# Handle NaN/Inf in features
nan_mask = np.isnan(X_raw) | np.isinf(X_raw)
nan_per_col = nan_mask.sum(axis=0)
nan_cols = [(feature_cols[i], nan_per_col[i]) for i in range(len(feature_cols)) if nan_per_col[i] > 0]
if nan_cols:
    print(f"\nColumns with NaN/Inf: {nan_cols}")

# Drop rows with any NaN
valid_mask = ~nan_mask.any(axis=1)
X_clean = X_raw[valid_mask]
labels_clean = labels[valid_mask].reset_index(drop=True)
print(f"After dropping NaN rows: {len(X_clean):,} / {len(X_raw):,} ({len(X_clean)/len(X_raw)*100:.1f}%)")

if len(X_clean) < 100:
    print("ERROR: Too few valid samples for HMM fitting.")
    sys.exit(1)

# =============================================================================
# PART 2: STANDARDIZE FEATURES
# =============================================================================
print("\n" + "-" * 60)
print("STANDARDIZING FEATURES (z-score)")
print("-" * 60)

scaler = StandardScaler()
X = scaler.fit_transform(X_clean)

print(f"Feature matrix shape: {X.shape}")
print(f"Feature means after scaling (should be ~0): {X.mean(axis=0)[:5].round(6)}")
print(f"Feature stds after scaling (should be ~1):  {X.std(axis=0)[:5].round(4)}")

# =============================================================================
# PART 3: FIT HMM WITH MULTIPLE STATE COUNTS, SELECT BY BIC
# =============================================================================
print("\n" + "=" * 80)
print("FITTING HMM WITH CANDIDATE STATE COUNTS")
print("=" * 80)

n_samples, n_features = X.shape


def compute_bic(model, X_data, n_states, n_feat):
    """Compute BIC for a fitted HMM.
    BIC = -2 * log_likelihood + k * ln(n)
    where k = number of free parameters.
    """
    log_likelihood = model.score(X_data)
    # Free parameters: transition matrix (n_states*(n_states-1)) +
    # means (n_states*n_feat) + covariances (n_states * n_feat*(n_feat+1)/2 for full)
    # + initial state (n_states - 1)
    k_transition = n_states * (n_states - 1)
    k_means = n_states * n_feat
    if HMM_COVARIANCE_TYPE == 'full':
        k_cov = n_states * n_feat * (n_feat + 1) // 2
    elif HMM_COVARIANCE_TYPE == 'diag':
        k_cov = n_states * n_feat
    else:
        k_cov = n_states * n_feat
    k_init = n_states - 1
    k = k_transition + k_means + k_cov + k_init
    n = len(X_data)
    bic = -2 * log_likelihood * n + k * np.log(n)
    return bic, log_likelihood * n, k


results = {}
print(f"\n{'n_states':>10} {'Log-Lik':>14} {'n_params':>10} {'BIC':>16} {'Converged':>10} {'Time (s)':>10}")
print("-" * 75)

for n_states in CANDIDATE_STATES:
    t_start = time.time()
    try:
        model = hmm.GaussianHMM(
            n_components=n_states,
            covariance_type=HMM_COVARIANCE_TYPE,
            n_iter=HMM_N_ITER,
            random_state=HMM_RANDOM_STATE,
            tol=1e-4,
        )
        model.fit(X)
        bic, ll, k = compute_bic(model, X, n_states, n_features)
        elapsed = time.time() - t_start
        converged = model.monitor_.converged
        results[n_states] = {
            'model': model,
            'bic': bic,
            'log_likelihood': ll,
            'n_params': k,
            'converged': converged,
            'time': elapsed,
        }
        print(f"{n_states:>10} {ll:>14.2f} {k:>10} {bic:>16.2f} {str(converged):>10} {elapsed:>10.1f}")
    except Exception as e:
        elapsed = time.time() - t_start
        print(f"{n_states:>10} {'FAILED':>14} {'--':>10} {'--':>16} {'--':>10} {elapsed:>10.1f}  [{e}]")

if not results:
    print("\nERROR: All HMM fits failed.")
    sys.exit(1)

# Select best by BIC (lowest)
best_n = min(results, key=lambda k: results[k]['bic'])
best_result = results[best_n]
best_model = best_result['model']

print(f"\nBEST MODEL: n_states={best_n} (BIC={best_result['bic']:.2f})")
print(f"  Log-likelihood: {best_result['log_likelihood']:.2f}")
print(f"  Parameters: {best_result['n_params']}")
print(f"  Converged: {best_result['converged']}")

# Decode regime labels
regime_labels = best_model.predict(X)
regime_probs = best_model.predict_proba(X)

print(f"\nRegime distribution:")
for r in range(best_n):
    count = np.sum(regime_labels == r)
    pct = count / len(regime_labels) * 100
    print(f"  Regime {r}: {count:>6} samples ({pct:.1f}%)")

# =============================================================================
# PART 4: ONLINE BAYESIAN HMM CLASS
# =============================================================================
print("\n" + "=" * 80)
print("ONLINE BAYESIAN HMM IMPLEMENTATION")
print("=" * 80)


class OnlineBayesianHMM:
    """Online Bayesian regime inference using a pre-trained HMM.

    Takes a fitted hmmlearn GaussianHMM model and performs online
    forward-algorithm updates with exponential decay to weight
    recent observations more heavily.

    Usage:
        online = OnlineBayesianHMM(fitted_model, scaler, decay=0.995)
        for obs in new_observations:
            online.update(obs)
            regime = online.get_regime()
            conf = online.get_confidence()
    """

    def __init__(self, model, scaler, decay=0.995):
        """
        Args:
            model: Fitted hmmlearn.hmm.GaussianHMM
            scaler: Fitted sklearn.preprocessing.StandardScaler
            decay: Exponential decay factor for old observations (0 < decay <= 1).
                   Lower values discount history faster.
        """
        self.model = model
        self.scaler = scaler
        self.n_states = model.n_components
        self.decay = decay

        # Extract model parameters
        self.startprob = model.startprob_
        self.transmat = model.transmat_
        self.means = model.means_
        self.covars = model.covars_

        # Precompute inverse covariances and log-determinants for emission
        self._inv_covars = []
        self._log_det_covars = []
        self._n_features = self.means.shape[1]
        for k in range(self.n_states):
            if model.covariance_type == 'full':
                cov = self.covars[k]
            elif model.covariance_type == 'diag':
                cov = np.diag(self.covars[k])
            else:
                cov = np.diag(self.covars[k])
            # Regularize for numerical stability
            cov += np.eye(self._n_features) * 1e-6
            self._inv_covars.append(np.linalg.inv(cov))
            sign, logdet = np.linalg.slogdet(cov)
            self._log_det_covars.append(logdet)

        # Initialize belief to start probability
        self.belief = self.startprob.copy()
        self._n_updates = 0

    def _emission_log_prob(self, obs_scaled):
        """Compute log P(obs | state=k) for each state k (Gaussian emission)."""
        log_probs = np.zeros(self.n_states)
        for k in range(self.n_states):
            diff = obs_scaled - self.means[k]
            mahal = diff @ self._inv_covars[k] @ diff
            log_probs[k] = -0.5 * (
                self._n_features * np.log(2 * np.pi)
                + self._log_det_covars[k]
                + mahal
            )
        return log_probs

    def update(self, observation):
        """Forward step: update regime belief given a new observation.

        Args:
            observation: Raw (unscaled) feature vector of shape (n_features,)
        """
        # Scale the observation using the fitted scaler
        obs_scaled = self.scaler.transform(observation.reshape(1, -1)).ravel()

        # Exponential decay on prior belief
        if self._n_updates > 0:
            self.belief = self.belief ** self.decay
            self.belief /= self.belief.sum()

        # Forward step: predict -> update
        # Predict: P(z_t | x_{1:t-1}) = sum_j P(z_t | z_{t-1}=j) * P(z_{t-1}=j | x_{1:t-1})
        predicted = self.transmat.T @ self.belief

        # Update: P(z_t | x_{1:t}) proportional to P(x_t | z_t) * P(z_t | x_{1:t-1})
        log_emission = self._emission_log_prob(obs_scaled)
        # Use log-sum-exp for numerical stability
        log_joint = log_emission + np.log(predicted + 1e-300)
        log_joint -= np.max(log_joint)  # shift for stability
        joint = np.exp(log_joint)
        self.belief = joint / (joint.sum() + 1e-300)

        self._n_updates += 1

    def get_regime(self):
        """Return the most likely current regime (integer)."""
        return int(np.argmax(self.belief))

    def get_confidence(self):
        """Return the maximum belief probability (confidence in current regime)."""
        return float(np.max(self.belief))

    def get_belief(self):
        """Return the full belief distribution over regimes."""
        return self.belief.copy()

    def reset(self):
        """Reset belief to the start probability."""
        self.belief = self.startprob.copy()
        self._n_updates = 0


# Verify online HMM matches batch decode
print("Verifying online HMM against batch decode...")
online_hmm = OnlineBayesianHMM(best_model, scaler, decay=DECAY_LAMBDA)
online_regimes = []
online_confidences = []

for i in range(len(X_clean)):
    online_hmm.update(X_clean[i])
    online_regimes.append(online_hmm.get_regime())
    online_confidences.append(online_hmm.get_confidence())

online_regimes = np.array(online_regimes)
online_confidences = np.array(online_confidences)

# Agreement rate (after warm-up period)
warmup = min(50, len(online_regimes) // 10)
batch_regimes = regime_labels
agreement = np.mean(online_regimes[warmup:] == batch_regimes[warmup:])
print(f"  Online vs batch agreement (after {warmup}-sample warmup): {agreement*100:.1f}%")
print(f"  Average online confidence: {online_confidences[warmup:].mean():.3f}")
print(f"  Min online confidence: {online_confidences[warmup:].min():.3f}")

# =============================================================================
# PART 5: COMPUTE P(bust | regime)
# =============================================================================
print("\n" + "=" * 80)
print("COMPUTING P(bust | regime)")
print("=" * 80)

bust_col = 'is_bust' if 'is_bust' in labels_clean.columns else 'bust_binary'
if bust_col not in labels_clean.columns:
    # Fallback: use level_reached to infer bust
    if 'level_reached' in labels_clean.columns:
        # Bust = reached max level (need to infer max from data)
        max_level = labels_clean['level_reached'].max()
        bust_arr = (labels_clean['level_reached'] >= max_level).values.astype(int)
        print(f"  Inferred bust from level_reached >= {max_level}")
    else:
        print("ERROR: No bust indicator in labels.")
        sys.exit(1)
else:
    bust_arr = labels_clean[bust_col].values.astype(int)

overall_bust_rate = bust_arr.mean()
print(f"Overall bust rate: {overall_bust_rate:.4f} ({bust_arr.sum()} / {len(bust_arr)})")

p_bust_per_regime = {}
regime_stats = {}

print(f"\n{'Regime':>8} {'Count':>8} {'Busts':>8} {'P(bust)':>10} {'vs Overall':>12} {'Avg Conf':>10}")
print("-" * 60)

for r in range(best_n):
    mask = (regime_labels == r)
    n_in_regime = mask.sum()
    if n_in_regime == 0:
        p_bust_per_regime[r] = 0.0
        continue

    busts_in_regime = bust_arr[mask].sum()
    p_bust = busts_in_regime / n_in_regime
    p_bust_per_regime[r] = p_bust
    ratio = p_bust / overall_bust_rate if overall_bust_rate > 0 else 0

    avg_conf = regime_probs[mask, r].mean()

    regime_stats[r] = {
        'count': int(n_in_regime),
        'busts': int(busts_in_regime),
        'p_bust': float(p_bust),
        'ratio_vs_overall': float(ratio),
        'avg_confidence': float(avg_conf),
    }

    print(f"{r:>8} {n_in_regime:>8} {busts_in_regime:>8} {p_bust:>10.4f} {ratio:>11.2f}x {avg_conf:>10.3f}")

# Variance of P(bust|regime) across regimes
p_bust_values = np.array([p_bust_per_regime[r] for r in range(best_n)])
p_bust_variance = np.var(p_bust_values)
p_bust_range = p_bust_values.max() - p_bust_values.min()

print(f"\nP(bust|regime) variance: {p_bust_variance:.6f}")
print(f"P(bust|regime) range:    {p_bust_range:.4f} (max - min)")

# =============================================================================
# PART 6: PERMUTATION TEST — CRITICAL GATE
# =============================================================================
print("\n" + "=" * 80)
print("CRITICAL GATE: PERMUTATION TEST FOR REGIME SIGNIFICANCE")
print("=" * 80)
print(f"Testing whether variance of P(bust|regime) is significant...")
print(f"H0: Busts are IID across regimes (regime labels are meaningless)")
print(f"H1: Some regimes have significantly different bust rates")
print(f"Permutations: {N_PERMUTATIONS}")

observed_variance = p_bust_variance
null_variances = np.zeros(N_PERMUTATIONS)

t_perm_start = time.time()
for perm in range(N_PERMUTATIONS):
    shuffled_busts = np.random.permutation(bust_arr)
    perm_p_busts = []
    for r in range(best_n):
        mask = (regime_labels == r)
        n_in = mask.sum()
        if n_in > 0:
            perm_p_busts.append(shuffled_busts[mask].mean())
        else:
            perm_p_busts.append(0.0)
    null_variances[perm] = np.var(perm_p_busts)

    if (perm + 1) % 200 == 0:
        elapsed = time.time() - t_perm_start
        print(f"  {perm+1}/{N_PERMUTATIONS} permutations ({elapsed:.1f}s)")

perm_p_value = np.mean(null_variances >= observed_variance)
print(f"\nPermutation test results:")
print(f"  Observed variance of P(bust|regime): {observed_variance:.6f}")
print(f"  Null distribution: mean={null_variances.mean():.6f}, "
      f"std={null_variances.std():.6f}, max={null_variances.max():.6f}")
print(f"  p-value: {perm_p_value:.4f}")

# Also do a chi-squared test as a secondary check
observed_counts = []
expected_counts = []
for r in range(best_n):
    mask = (regime_labels == r)
    n_in = mask.sum()
    if n_in >= 5:  # chi-sq requires sufficient counts
        observed_counts.append([bust_arr[mask].sum(), n_in - bust_arr[mask].sum()])
        expected_counts.append(n_in)

if len(observed_counts) >= 2:
    chi2_stat, chi2_p_value = sp_stats.chisquare(
        [c[0] for c in observed_counts],
        f_exp=[overall_bust_rate * n for n in expected_counts]
    )[:2] if overall_bust_rate > 0 else (0, 1)
    print(f"  Chi-squared test: chi2={chi2_stat:.4f}, p={chi2_p_value:.4f}")
else:
    chi2_p_value = 1.0
    print(f"  Chi-squared test: insufficient data")

# DECISION GATE
print(f"\n{'='*60}")
if perm_p_value < SIGNIFICANCE_REJECT:
    gate_result = 'PASS'
    print(f"  GATE RESULT: PASS (p={perm_p_value:.4f} < {SIGNIFICANCE_REJECT})")
    print(f"  Regimes have REAL signal for bust prediction.")
    print(f"  Proceed to Phase C (per-regime config optimization).")
elif perm_p_value > SIGNIFICANCE_ACCEPT:
    gate_result = 'FAIL'
    print(f"  GATE RESULT: FAIL (p={perm_p_value:.4f} > {SIGNIFICANCE_ACCEPT})")
    print(f"  Busts appear IID across regimes.")
    print(f"  Regime detection does NOT help predict busts.")
    print(f"  STOP: Do not proceed with per-regime optimization.")
else:
    gate_result = 'MARGINAL'
    print(f"  GATE RESULT: MARGINAL (p={perm_p_value:.4f})")
    print(f"  Between {SIGNIFICANCE_REJECT} and {SIGNIFICANCE_ACCEPT}.")
    print(f"  Weak evidence of regime signal. Proceed with caution.")
print(f"{'='*60}")

# =============================================================================
# PART 7: SAVE ARTIFACTS
# =============================================================================
print("\n" + "-" * 60)
print("SAVING ARTIFACTS")
print("-" * 60)

# 1. Save the best HMM model
model_path = os.path.join(DATA_DIR, 'hmm_model.pkl')
with open(model_path, 'wb') as f:
    pickle.dump({
        'model': best_model,
        'scaler': scaler,
        'n_states': best_n,
        'feature_cols': feature_cols,
        'decay_lambda': DECAY_LAMBDA,
    }, f)
print(f"  Saved HMM model: {model_path}")

# 2. Save regime labels
regime_df = pd.DataFrame({
    'regime': regime_labels,
    'confidence': regime_probs.max(axis=1),
})
for col in label_cols_present:
    regime_df[col] = labels_clean[col].values
regime_path = os.path.join(DATA_DIR, 'regime_labels.parquet')
regime_df.to_parquet(regime_path, index=False)
print(f"  Saved regime labels: {regime_path}")

# 3. Save P(bust|regime) table
pbust_table = {
    'p_bust_per_regime': {int(k): float(v) for k, v in p_bust_per_regime.items()},
    'regime_stats': {int(k): v for k, v in regime_stats.items()},
    'overall_bust_rate': float(overall_bust_rate),
}
pbust_path = os.path.join(DATA_DIR, 'p_bust_per_regime.json')
with open(pbust_path, 'w') as f:
    json.dump(pbust_table, f, indent=2)
print(f"  Saved P(bust|regime): {pbust_path}")

# 4. Save transition matrix
transmat = best_model.transmat_
transmat_path = os.path.join(DATA_DIR, 'transition_matrix.npy')
np.save(transmat_path, transmat)
print(f"  Saved transition matrix: {transmat_path}")

# 5. Save permutation test results
perm_results = {
    'gate_result': gate_result,
    'observed_variance': float(observed_variance),
    'p_value_permutation': float(perm_p_value),
    'p_value_chi_squared': float(chi2_p_value),
    'n_permutations': N_PERMUTATIONS,
    'null_mean': float(null_variances.mean()),
    'null_std': float(null_variances.std()),
    'null_max': float(null_variances.max()),
    'significance_reject': SIGNIFICANCE_REJECT,
    'significance_accept': SIGNIFICANCE_ACCEPT,
    'n_states_selected': best_n,
    'bic_scores': {int(k): float(v['bic']) for k, v in results.items()},
}
perm_path = os.path.join(DATA_DIR, 'permutation_test.json')
with open(perm_path, 'w') as f:
    json.dump(perm_results, f, indent=2)
print(f"  Saved permutation results: {perm_path}")

# 6. Save BIC comparison for all candidates
bic_comparison = {
    int(k): {
        'bic': float(v['bic']),
        'log_likelihood': float(v['log_likelihood']),
        'n_params': int(v['n_params']),
        'converged': bool(v['converged']),
    }
    for k, v in results.items()
}
bic_path = os.path.join(DATA_DIR, 'bic_comparison.json')
with open(bic_path, 'w') as f:
    json.dump(bic_comparison, f, indent=2)
print(f"  Saved BIC comparison: {bic_path}")

# =============================================================================
# PART 8: VISUALIZATION
# =============================================================================
print("\n" + "=" * 80)
print("GENERATING PLOTS")
print("=" * 80)

plt.style.use('seaborn-v0_8-darkgrid')
fig = plt.figure(figsize=(24, 20))
gs = fig.add_gridspec(3, 3, hspace=0.35, wspace=0.3)

# ─── Plot 1: BIC comparison across state counts ──────────────────────────────
ax1 = fig.add_subplot(gs[0, 0])
n_states_list = sorted(results.keys())
bic_list = [results[n]['bic'] for n in n_states_list]
colors_bic = ['#e74c3c' if n == best_n else '#3498db' for n in n_states_list]
ax1.bar(range(len(n_states_list)), bic_list, color=colors_bic, edgecolor='black')
ax1.set_xticks(range(len(n_states_list)))
ax1.set_xticklabels(n_states_list)
ax1.set_xlabel('Number of States')
ax1.set_ylabel('BIC (lower is better)')
ax1.set_title(f'BIC Model Selection\n(Best: {best_n} states)', fontweight='bold')
for i, (n, b) in enumerate(zip(n_states_list, bic_list)):
    ax1.text(i, b, f'{b:.0f}', ha='center', va='bottom', fontsize=7)

# ─── Plot 2: Regime time series ──────────────────────────────────────────────
ax2 = fig.add_subplot(gs[0, 1:])
cmap = plt.cm.Set1
regime_colors = [cmap(r / max(best_n - 1, 1)) for r in regime_labels]
ax2.scatter(range(len(regime_labels)), regime_labels, c=regime_labels,
            cmap='Set1', s=3, alpha=0.5)
ax2.set_xlabel('Sample Index (time-ordered)')
ax2.set_ylabel('Regime')
ax2.set_title(f'Regime Time Series ({best_n} states)', fontweight='bold')
ax2.set_yticks(range(best_n))

# Add bust markers
bust_indices = np.where(bust_arr == 1)[0]
if len(bust_indices) > 0:
    ax2.scatter(bust_indices, regime_labels[bust_indices],
                marker='x', color='red', s=50, zorder=5, label='Busts')
    ax2.legend(fontsize=8)

# ─── Plot 3: P(bust|regime) bar chart ────────────────────────────────────────
ax3 = fig.add_subplot(gs[1, 0])
regimes_sorted = sorted(p_bust_per_regime.keys())
p_bust_bars = [p_bust_per_regime[r] for r in regimes_sorted]
colors_pbust = ['#e74c3c' if p > overall_bust_rate * 1.5 else
                '#f39c12' if p > overall_bust_rate else
                '#2ecc71' for p in p_bust_bars]
bars = ax3.bar(regimes_sorted, p_bust_bars, color=colors_pbust, edgecolor='black')
ax3.axhline(y=overall_bust_rate, color='black', linestyle='--', linewidth=1,
            label=f'Overall: {overall_bust_rate:.4f}')
ax3.set_xlabel('Regime')
ax3.set_ylabel('P(bust | regime)')
ax3.set_title('P(bust) by Regime', fontweight='bold')
ax3.legend(fontsize=8)
for bar, p in zip(bars, p_bust_bars):
    ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
             f'{p:.4f}', ha='center', va='bottom', fontsize=8)

# ─── Plot 4: Transition matrix heatmap ───────────────────────────────────────
ax4 = fig.add_subplot(gs[1, 1])
im = ax4.imshow(transmat, cmap='YlOrRd', vmin=0, vmax=1, aspect='auto')
for i in range(best_n):
    for j in range(best_n):
        val = transmat[i, j]
        color = 'white' if val > 0.5 else 'black'
        ax4.text(j, i, f'{val:.2f}', ha='center', va='center',
                 fontsize=max(6, 10 - best_n), color=color)
ax4.set_xlabel('To Regime')
ax4.set_ylabel('From Regime')
ax4.set_title('Transition Matrix P(i -> j)', fontweight='bold')
ax4.set_xticks(range(best_n))
ax4.set_yticks(range(best_n))
plt.colorbar(im, ax=ax4, fraction=0.046)

# ─── Plot 5: Permutation test null distribution ──────────────────────────────
ax5 = fig.add_subplot(gs[1, 2])
ax5.hist(null_variances, bins=50, color='#3498db', alpha=0.7, edgecolor='black',
         density=True, label='Null distribution')
ax5.axvline(x=observed_variance, color='red', linewidth=2, linestyle='--',
            label=f'Observed: {observed_variance:.6f}')
ax5.set_xlabel('Variance of P(bust|regime)')
ax5.set_ylabel('Density')
ax5.set_title(f'Permutation Test (p={perm_p_value:.4f})\n'
              f'Gate: {gate_result}', fontweight='bold')
ax5.legend(fontsize=8)

# ─── Plot 6: Regime size distribution ─────────────────────────────────────────
ax6 = fig.add_subplot(gs[2, 0])
regime_counts = [np.sum(regime_labels == r) for r in range(best_n)]
ax6.bar(range(best_n), regime_counts, color='#3498db', edgecolor='black')
ax6.set_xlabel('Regime')
ax6.set_ylabel('Count')
ax6.set_title('Regime Size Distribution', fontweight='bold')
ax6.set_xticks(range(best_n))
for r, c in enumerate(regime_counts):
    ax6.text(r, c, f'{c}', ha='center', va='bottom', fontsize=8)

# ─── Plot 7: Online confidence over time ─────────────────────────────────────
ax7 = fig.add_subplot(gs[2, 1])
ax7.plot(online_confidences, linewidth=0.5, alpha=0.7, color='#2c3e50')
ax7.set_xlabel('Sample Index')
ax7.set_ylabel('Confidence (max belief)')
ax7.set_title('Online HMM Confidence Over Time', fontweight='bold')
ax7.axhline(y=1.0/best_n, color='red', linestyle=':', alpha=0.5,
            label=f'Random: {1.0/best_n:.3f}')
ax7.legend(fontsize=8)

# ─── Plot 8: Feature importance by regime (mean z-scores) ────────────────────
ax8 = fig.add_subplot(gs[2, 2])
# Show top features that differ most between regimes
regime_means = np.zeros((best_n, n_features))
for r in range(best_n):
    mask = regime_labels == r
    if mask.sum() > 0:
        regime_means[r] = X[mask].mean(axis=0)

# Feature importance = max range across regimes
feat_range = regime_means.max(axis=0) - regime_means.min(axis=0)
top_k = min(15, n_features)
top_feat_idx = np.argsort(feat_range)[-top_k:]
top_feat_names = [feature_cols[i] for i in top_feat_idx]

im8 = ax8.imshow(regime_means[:, top_feat_idx].T, aspect='auto', cmap='RdBu_r',
                  vmin=-2, vmax=2)
ax8.set_xticks(range(best_n))
ax8.set_xticklabels(range(best_n))
ax8.set_yticks(range(top_k))
ax8.set_yticklabels(top_feat_names, fontsize=7)
ax8.set_xlabel('Regime')
ax8.set_title(f'Top {top_k} Discriminative Features\n(mean z-score by regime)', fontweight='bold')
plt.colorbar(im8, ax=ax8, fraction=0.046)

plt.suptitle(f'Phase B: Online Bayesian HMM Regime Detection\n'
             f'{best_n} states, BIC={best_result["bic"]:.0f}, '
             f'Gate={gate_result} (p={perm_p_value:.4f})',
             fontsize=16, fontweight='bold', y=1.01)

plot_path = os.path.join(OUTPUT_DIR, '16_online_hmm.png')
fig.savefig(plot_path, dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved plot: {plot_path}")

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

print(f"""
  DATA:
    Feature matrix: {len(X_clean):,} samples x {n_features} features
    Bust rate: {overall_bust_rate:.4f} ({bust_arr.sum()}/{len(bust_arr)})

  HMM MODEL:
    Best n_states: {best_n} (selected by BIC)
    BIC: {best_result['bic']:.2f}
    Log-likelihood: {best_result['log_likelihood']:.2f}
    Converged: {best_result['converged']}

  REGIMES:""")
for r in range(best_n):
    count = np.sum(regime_labels == r)
    p = p_bust_per_regime.get(r, 0)
    print(f"    Regime {r}: {count:>6} samples, P(bust)={p:.4f}")

print(f"""
  ONLINE HMM:
    Decay lambda: {DECAY_LAMBDA}
    Batch agreement: {agreement*100:.1f}%
    Average confidence: {online_confidences[warmup:].mean():.3f}

  PERMUTATION TEST:
    Observed variance: {observed_variance:.6f}
    p-value: {perm_p_value:.4f}
    Gate result: {gate_result}

  SAVED ARTIFACTS:
    {model_path}
    {regime_path}
    {pbust_path}
    {transmat_path}
    {perm_path}
    {bic_path}
    {plot_path}
""")
print("=" * 80)
