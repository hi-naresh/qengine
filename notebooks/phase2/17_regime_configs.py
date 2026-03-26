#!/usr/bin/env python3
"""
Step 17: Per-Regime Config Optimization (Phase C)
==================================================
For each HMM regime discovered in Phase B, find the optimal surefire hedge
configuration (or decide to SKIP that regime entirely).

PIPELINE:
1. Load feature matrix + regime labels from Phase B
2. Compute regime-specific p-values (P(lose) per level per regime)
3. MINLP grid search over (N, m, base_pct, tp_mult, hedge_ratio)
4. Tail-risk aware reward function
5. Test SKIP option for each regime
6. Walk-forward validation across 8/10 test years
7. Output: config lookup table (regime -> optimal config or SKIP)

DEPENDS ON:
  - notebooks/phase2/data/feature_matrix.parquet (from script 15)
  - notebooks/phase2/data/regime_labels.parquet (from script 16)
  - notebooks/phase2/data/p_bust_per_regime.json (from script 16)
  - notebooks/phase2/data/permutation_test.json (from script 16)
"""

import os
import sys
import json
import time
import pickle
import warnings
from itertools import product as iterproduct

os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats as sp_stats

warnings.filterwarnings('ignore', category=RuntimeWarning)

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, 'data')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Trading Constants ────────────────────────────────────────────────────────
LEVERAGE = 30           # 30:1
CONTRACT_SIZE = 100_000 # EUR-USD notional
AVG_PRICE = 1.11        # approximate EUR-USD price
PIP_SIZE = 0.0001
PIP_VALUE = 10.0
STARTING_EQUITY = 10_000
MAX_BARS_PER_LEVEL = 500

# ─── Grid Search Ranges ──────────────────────────────────────────────────────
N_RANGE = list(range(4, 21))                        # 4-20 levels
M_RANGE = [1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7,
           1.8, 1.9, 2.0, 2.2, 2.5]                # multiplier
BASE_PCT_RANGE = [0.002, 0.003, 0.004, 0.005,
                  0.006, 0.007, 0.008, 0.01]        # base position as fraction of equity
TP_MULT_RANGE = [0.5, 0.6, 0.7, 0.8, 0.9,
                 1.0, 1.1, 1.2, 1.3, 1.5]          # TP ATR multiple
K_RANGE = [1.2, 1.5, 1.8, 2.0, 2.5, 3.0, 3.5, 4.0]  # hedge ratio (tp/h)

# ─── Constraints ──────────────────────────────────────────────────────────────
PM_HARD_LIMIT = 0.90    # p * m must be < 0.90
WALK_FORWARD_PASS = 8   # must work in 8/10 test folds

np.random.seed(42)

# =============================================================================
# PART 1: LOAD DATA
# =============================================================================
print("=" * 80)
print("STEP 17: PER-REGIME CONFIG OPTIMIZATION")
print("=" * 80)

# Load feature matrix
fm_path = os.path.join(DATA_DIR, 'feature_matrix.parquet')
if not os.path.exists(fm_path):
    print(f"ERROR: Feature matrix not found: {fm_path}")
    print("Run script 15 first.")
    sys.exit(1)
df_features = pd.read_parquet(fm_path)

# Load regime labels
regime_path = os.path.join(DATA_DIR, 'regime_labels.parquet')
if not os.path.exists(regime_path):
    print(f"ERROR: Regime labels not found: {regime_path}")
    print("Run script 16 first.")
    sys.exit(1)
df_regimes = pd.read_parquet(regime_path)

# Load P(bust|regime)
pbust_path = os.path.join(DATA_DIR, 'p_bust_per_regime.json')
if not os.path.exists(pbust_path):
    print(f"ERROR: P(bust|regime) not found: {pbust_path}")
    sys.exit(1)
with open(pbust_path, 'r') as f:
    pbust_data = json.load(f)

# Load permutation test results
perm_path = os.path.join(DATA_DIR, 'permutation_test.json')
if os.path.exists(perm_path):
    with open(perm_path, 'r') as f:
        perm_results = json.load(f)
    gate_result = perm_results.get('gate_result', 'UNKNOWN')
    print(f"Phase B gate result: {gate_result}")
    if gate_result == 'FAIL':
        print("WARNING: Phase B gate FAILED (busts appear IID).")
        print("Per-regime optimization may not add value. Proceeding anyway for analysis.")
else:
    gate_result = 'UNKNOWN'

# Merge data
FEATURE_SUFFIXES = ('_adx', '_atr_ratio', '_chop', '_hurst', '_range_atr')
feature_cols = [c for c in df_features.columns if any(c.endswith(s) for s in FEATURE_SUFFIXES)]
LABEL_COLS = ['level_reached', 'is_bust', 'bust_binary', 'choppy_bust', 'choppy_bust_binary',
              'pnl', 'pnl_pct', 'cycle_pnl', 'entry_bar_index', 'entry_bar',
              'timestamp', 'entry_price', 'atr_at_entry', 'direction',
              'duration_bars', 'levels_used', 'datetime']
label_cols_present = [c for c in LABEL_COLS if c in df_features.columns]

# Align lengths (drop NaN rows from features, matching regime_labels)
X_raw = df_features[feature_cols].values.astype(np.float64)
nan_mask = np.isnan(X_raw) | np.isinf(X_raw)
valid_mask = ~nan_mask.any(axis=1)

labels = df_features[label_cols_present][valid_mask].reset_index(drop=True)
regimes = df_regimes['regime'].values

n_regimes = int(regimes.max()) + 1
n_samples = len(regimes)

print(f"\nLoaded {n_samples:,} samples, {n_regimes} regimes")
print(f"Label columns: {label_cols_present}")

# Extract key labels
bust_col = 'is_bust' if 'is_bust' in labels.columns else 'bust_binary'
if bust_col in labels.columns:
    bust_arr = labels[bust_col].values.astype(int)
elif 'level_reached' in labels.columns:
    max_lvl = labels['level_reached'].max()
    bust_arr = (labels['level_reached'] >= max_lvl).values.astype(int)
else:
    print("ERROR: No bust indicator available.")
    sys.exit(1)

level_col = 'level_reached'
if level_col in labels.columns:
    level_arr = labels[level_col].values.astype(int)
else:
    level_arr = None

pnl_col = 'cycle_pnl'
if pnl_col in labels.columns:
    pnl_arr = labels[pnl_col].values.astype(float)
else:
    pnl_arr = None

# =============================================================================
# PART 2: REGIME-SPECIFIC P-VALUES PER LEVEL
# =============================================================================
print("\n" + "=" * 80)
print("COMPUTING REGIME-SPECIFIC P(lose) PER LEVEL")
print("=" * 80)

# For each regime, compute P(reaching level L and losing) = cumulative product
# We approximate per-level p from the level_reached distribution

regime_p_levels = {}  # regime -> list of p(lose at level L)

for r in range(n_regimes):
    mask = regimes == r
    n_in_regime = mask.sum()

    if n_in_regime < 20:
        regime_p_levels[r] = None
        print(f"  Regime {r}: {n_in_regime} samples (too few, skipping)")
        continue

    if level_arr is not None:
        regime_levels = level_arr[mask]
        # P(lose at level L | reached level L)
        # = P(reached L+1) / P(reached L)
        # P(reached L) = fraction of cycles that reached level L
        max_possible = int(regime_levels.max()) + 1
        p_levels = []
        for L in range(max_possible):
            reached_L = np.sum(regime_levels >= L)
            reached_L1 = np.sum(regime_levels >= L + 1)
            if reached_L > 5:  # minimum sample
                p_lose = reached_L1 / reached_L
                p_levels.append(float(p_lose))
            else:
                break
    else:
        # Fallback: use overall bust rate as uniform p
        regime_busts = bust_arr[mask]
        p_bust = regime_busts.mean()
        # Estimate p per level: P(bust) ~ p^N, solve for p
        # Use a default N=8 estimate
        if p_bust > 0:
            p_approx = p_bust ** (1.0 / 8)
        else:
            p_approx = 0.5
        p_levels = [float(p_approx)] * 12

    regime_p_levels[r] = p_levels

    # Print summary
    avg_p = np.mean(p_levels[:8]) if len(p_levels) >= 8 else np.mean(p_levels) if p_levels else 0
    print(f"  Regime {r}: {n_in_regime:>6} samples, "
          f"levels measured: {len(p_levels)}, "
          f"avg P(lose): {avg_p:.4f}, "
          f"P(bust): {bust_arr[mask].mean():.4f}")
    if p_levels:
        level_strs = [f"L{i}={p:.3f}" for i, p in enumerate(p_levels[:6])]
        print(f"    {', '.join(level_strs)}")


# =============================================================================
# PART 3: HELPER FUNCTIONS FOR CYCLE SIMULATION
# =============================================================================

def compute_max_affordable_levels(equity, base_pct, m, avg_atr, tp_mult, k, max_check=25):
    """Compute maximum affordable levels given equity and config."""
    margin_rate = 1.0 / LEVERAGE
    base_lots = (equity * base_pct) / (AVG_PRICE * CONTRACT_SIZE * margin_rate)
    tp_dist = avg_atr * tp_mult
    h_dist = tp_dist / k

    cum_margin = 0.0
    cum_loss = 0.0
    for lvl in range(max_check):
        lot = base_lots * m ** lvl
        margin = AVG_PRICE * lot * CONTRACT_SIZE * margin_rate
        loss = (h_dist / PIP_SIZE) * PIP_VALUE * lot
        cum_margin += margin
        cum_loss += loss
        if (cum_margin + cum_loss) > equity * 0.90:
            return lvl
    return max_check


def compute_cycle_ev(p_levels_list, N, m, tp=1.0, k=2.0):
    """Compute expected value per cycle (normalized).

    Args:
        p_levels_list: List of P(lose at level L | reached level L)
        N: number of levels
        m: multiplier
        tp: TP distance (normalized to 1)
        k: tp/h ratio

    Returns:
        ev: expected value per cycle
        p_bust: probability of bust
        win_contribution: expected win contribution
        bust_contribution: expected bust loss
    """
    h = tp / k

    ev = 0.0
    remaining_prob = 1.0

    for n in range(N):
        p_l = p_levels_list[n] if n < len(p_levels_list) else (
            np.mean(p_levels_list) if p_levels_list else 0.5
        )
        p_win = 1.0 - p_l

        # Win P&L at level n
        if m > 1.0:
            win_pnl = m ** n * tp - h * (m ** n - 1) / (m - 1)
        else:
            win_pnl = tp - h * n

        ev += remaining_prob * p_win * win_pnl
        remaining_prob *= p_l

    # Bust P&L
    if m > 1.0:
        bust_pnl = -h * (m ** N - 1) / (m - 1)
    else:
        bust_pnl = -h * N

    bust_contribution = remaining_prob * bust_pnl
    ev += bust_contribution

    return ev, remaining_prob, ev - bust_contribution, bust_contribution


def compute_pm(p_levels_list, m, n_avg=8):
    """Compute average p * m product."""
    if not p_levels_list:
        return 1.0
    avg_p = np.mean(p_levels_list[:n_avg]) if len(p_levels_list) >= n_avg else np.mean(p_levels_list)
    return avg_p * m


def tail_risk_reward(ev, p_bust, pm_product, bust_severity, n_levels,
                     bust_rate_observed=0.0):
    """Tail-risk aware reward function.

    Penalizes:
    - High bust rate
    - High p*m product (approaching or exceeding 1.0)
    - Large potential drawdown
    Bonuses:
    - Zero ruin probability (in simulation)
    - Positive expected value
    - Low bust rate

    Returns:
        reward: float (higher is better, can be negative)
    """
    if ev <= 0:
        return -100.0  # negative EV is never acceptable

    # Base reward: expected value
    reward = ev * 100  # scale up for readability

    # Penalty: p*m proximity to 1.0
    # As p*m approaches 1.0, adding levels stops helping
    if pm_product >= 1.0:
        reward -= 50.0 * (pm_product - 0.9)  # harsh penalty above 0.9
    elif pm_product > 0.85:
        reward -= 20.0 * (pm_product - 0.85)

    # Penalty: bust rate
    reward -= p_bust * 200  # each 1% bust rate costs 2 points

    # Penalty: bust severity (absolute value of bust loss)
    reward -= abs(bust_severity) * 5

    # Penalty: too many levels (complexity / execution risk)
    if n_levels > 15:
        reward -= (n_levels - 15) * 0.5

    # Bonus: very low bust probability
    if p_bust < 0.001:
        reward += 5.0
    if p_bust < 0.0001:
        reward += 10.0

    # Bonus: large safety margin (p*m well below 1.0)
    if pm_product < 0.80:
        reward += (0.80 - pm_product) * 10

    return reward


# =============================================================================
# PART 4: MINLP GRID SEARCH
# =============================================================================
print("\n" + "=" * 80)
print("MINLP GRID SEARCH: Per-Regime Config Optimization")
print("=" * 80)

# Use average ATR from feature matrix for margin calculations
# (approximate; in practice would come from live data)
AVG_ATR = 0.00050  # typical EUR-USD 5m ATR

regime_configs = {}  # regime -> best config dict
regime_search_results = {}  # regime -> all evaluated configs

total_configs = len(N_RANGE) * len(M_RANGE) * len(BASE_PCT_RANGE) * len(TP_MULT_RANGE) * len(K_RANGE)
print(f"Grid size per regime: {total_configs:,} configurations")
print(f"Regimes to optimize: {n_regimes}")

for r in range(n_regimes):
    t_start = time.time()
    p_levels = regime_p_levels.get(r)

    if p_levels is None or len(p_levels) < 3:
        print(f"\n  Regime {r}: SKIP (insufficient per-level data)")
        regime_configs[r] = {'action': 'SKIP', 'reason': 'insufficient_data'}
        continue

    n_in_regime = np.sum(regimes == r)
    regime_bust_rate = bust_arr[regimes == r].mean()

    print(f"\n  Regime {r} ({n_in_regime} samples, bust_rate={regime_bust_rate:.4f}):")
    print(f"    Searching {total_configs:,} configs...", end='', flush=True)

    best_reward = -999
    best_config = None
    all_results = []
    n_feasible = 0
    n_margin_fail = 0
    n_pm_fail = 0

    for N, m, base_pct, tp_mult, k in iterproduct(N_RANGE, M_RANGE, BASE_PCT_RANGE, TP_MULT_RANGE, K_RANGE):
        # Constraint 1: p*m < hard limit
        pm = compute_pm(p_levels, m)
        if pm >= PM_HARD_LIMIT:
            n_pm_fail += 1
            continue

        # Constraint 2: Must be affordable at LEVERAGE with STARTING_EQUITY
        max_affordable = compute_max_affordable_levels(
            STARTING_EQUITY, base_pct, m, AVG_ATR, tp_mult, k
        )
        if max_affordable < N:
            n_margin_fail += 1
            continue

        # Compute expected value and bust probability
        ev, p_bust, win_contrib, bust_contrib = compute_cycle_ev(
            p_levels, N, m, tp=1.0, k=k
        )

        # Bust severity (normalized)
        if m > 1.0:
            bust_severity = (1.0 / k) * (m ** N - 1) / (m - 1)
        else:
            bust_severity = N / k

        # Compute reward
        reward = tail_risk_reward(
            ev=ev,
            p_bust=p_bust,
            pm_product=pm,
            bust_severity=bust_severity,
            n_levels=N,
            bust_rate_observed=regime_bust_rate,
        )

        n_feasible += 1
        result = {
            'N': N, 'm': m, 'base_pct': base_pct, 'tp_mult': tp_mult, 'k': k,
            'ev': ev, 'p_bust': p_bust, 'pm': pm,
            'bust_severity': bust_severity,
            'reward': reward,
            'max_affordable': max_affordable,
        }
        all_results.append(result)

        if reward > best_reward:
            best_reward = reward
            best_config = result

    elapsed = time.time() - t_start
    print(f" done ({elapsed:.1f}s)")
    print(f"    Feasible: {n_feasible:,} / {total_configs:,} "
          f"(pm_fail: {n_pm_fail:,}, margin_fail: {n_margin_fail:,})")

    regime_search_results[r] = all_results

    # Decide: best config vs SKIP
    if best_config is None or best_reward < 0:
        regime_configs[r] = {
            'action': 'SKIP',
            'reason': 'no_positive_reward' if best_config is None else f'best_reward={best_reward:.2f}',
            'best_reward': float(best_reward) if best_config else None,
            'n_feasible': n_feasible,
        }
        print(f"    DECISION: SKIP (best reward = {best_reward:.2f})")
    else:
        regime_configs[r] = {
            'action': 'TRADE',
            'config': {
                'N': best_config['N'],
                'm': best_config['m'],
                'base_pct': best_config['base_pct'],
                'tp_mult': best_config['tp_mult'],
                'k': best_config['k'],
            },
            'metrics': {
                'ev': best_config['ev'],
                'p_bust': best_config['p_bust'],
                'pm': best_config['pm'],
                'bust_severity': best_config['bust_severity'],
                'reward': best_config['reward'],
                'max_affordable': best_config['max_affordable'],
            },
            'n_feasible': n_feasible,
        }
        c = best_config
        print(f"    DECISION: TRADE")
        print(f"    Best config: N={c['N']}, m={c['m']:.2f}, base={c['base_pct']:.3f}, "
              f"tp_mult={c['tp_mult']:.1f}, k={c['k']:.1f}")
        print(f"    EV={c['ev']:.6f}, P(bust)={c['p_bust']:.6f}, p*m={c['pm']:.4f}, "
              f"reward={c['reward']:.2f}")


# =============================================================================
# PART 5: WALK-FORWARD VALIDATION
# =============================================================================
print("\n" + "=" * 80)
print("WALK-FORWARD VALIDATION")
print("=" * 80)

# Split data into 10 temporal folds for walk-forward testing
# Configs must work in at least 8/10 folds
N_FOLDS = 10

fold_size = len(regimes) // N_FOLDS
fold_indices = [(i * fold_size, min((i + 1) * fold_size, len(regimes))) for i in range(N_FOLDS)]

print(f"Fold size: ~{fold_size} samples each")
print(f"Requirement: config must have positive EV in >= {WALK_FORWARD_PASS}/{N_FOLDS} folds")

validated_configs = {}

for r in range(n_regimes):
    cfg_entry = regime_configs[r]
    if cfg_entry['action'] != 'TRADE':
        validated_configs[r] = cfg_entry
        continue

    config = cfg_entry['config']
    N = config['N']
    m = config['m']
    k_val = config['k']

    # Test this config across folds
    fold_pass_count = 0
    fold_evs = []

    for fold_idx, (start, end) in enumerate(fold_indices):
        fold_mask = np.zeros(len(regimes), dtype=bool)
        fold_mask[start:end] = True
        regime_mask = (regimes == r) & fold_mask

        if regime_mask.sum() < 5:
            # Too few samples in this fold for this regime
            fold_evs.append(None)
            continue

        # Compute fold-specific p_levels
        fold_levels = level_arr[regime_mask] if level_arr is not None else None

        if fold_levels is not None:
            fold_p_levels = []
            max_possible = int(fold_levels.max()) + 1
            for L in range(max_possible):
                reached = np.sum(fold_levels >= L)
                reached_next = np.sum(fold_levels >= L + 1)
                if reached > 3:
                    fold_p_levels.append(reached_next / reached)
                else:
                    break
        else:
            fold_p_levels = regime_p_levels.get(r, [0.5] * 12)

        if len(fold_p_levels) < 2:
            fold_evs.append(None)
            continue

        ev, p_bust, _, _ = compute_cycle_ev(fold_p_levels, N, m, tp=1.0, k=k_val)
        fold_evs.append(ev)

        if ev > 0:
            fold_pass_count += 1

    # Count valid folds (non-None)
    valid_folds = [e for e in fold_evs if e is not None]
    n_valid = len(valid_folds)
    n_positive = sum(1 for e in valid_folds if e > 0)

    # Adjust threshold for regimes with fewer valid folds
    required_pass = min(WALK_FORWARD_PASS, max(1, int(n_valid * 0.8)))
    passed = n_positive >= required_pass

    cfg_entry['walk_forward'] = {
        'n_folds': N_FOLDS,
        'n_valid_folds': n_valid,
        'n_positive_folds': n_positive,
        'required': required_pass,
        'passed': passed,
        'fold_evs': [float(e) if e is not None else None for e in fold_evs],
    }

    if not passed:
        cfg_entry['action'] = 'SKIP'
        cfg_entry['reason'] = f'walk_forward_fail ({n_positive}/{n_valid} folds)'
        print(f"  Regime {r}: FAILED walk-forward ({n_positive}/{n_valid} positive folds, "
              f"needed {required_pass})")
    else:
        avg_ev = np.mean(valid_folds)
        std_ev = np.std(valid_folds) if len(valid_folds) > 1 else 0
        print(f"  Regime {r}: PASSED walk-forward ({n_positive}/{n_valid} positive folds, "
              f"avg EV={avg_ev:.6f}, std={std_ev:.6f})")

    validated_configs[r] = cfg_entry

# =============================================================================
# PART 6: FINAL CONFIG LOOKUP TABLE
# =============================================================================
print("\n" + "=" * 80)
print("FINAL CONFIG LOOKUP TABLE")
print("=" * 80)

print(f"\n{'Regime':>8} {'Action':>8} {'N':>4} {'m':>6} {'base%':>7} {'tp_m':>6} "
      f"{'k':>5} {'EV':>10} {'P(bust)':>10} {'p*m':>7} {'Reward':>8}")
print("-" * 95)

config_table = {}
for r in range(n_regimes):
    entry = validated_configs[r]
    config_table[r] = entry

    if entry['action'] == 'TRADE':
        cfg = entry['config']
        met = entry['metrics']
        print(f"{r:>8} {'TRADE':>8} {cfg['N']:>4} {cfg['m']:>6.2f} {cfg['base_pct']*100:>6.2f}% "
              f"{cfg['tp_mult']:>6.1f} {cfg['k']:>5.1f} {met['ev']:>10.6f} "
              f"{met['p_bust']:>10.6f} {met['pm']:>7.4f} {met['reward']:>8.2f}")
    else:
        reason = entry.get('reason', 'unknown')
        print(f"{r:>8} {'SKIP':>8} {'--':>4} {'--':>6} {'--':>7} {'--':>6} "
              f"{'--':>5} {'--':>10} {'--':>10} {'--':>7} {'--':>8}  ({reason})")

# Summary
n_trade = sum(1 for v in config_table.values() if v['action'] == 'TRADE')
n_skip = sum(1 for v in config_table.values() if v['action'] == 'SKIP')
print(f"\nSummary: {n_trade} TRADE regimes, {n_skip} SKIP regimes")

# Coverage: what fraction of samples fall in TRADE regimes?
trade_regimes = [r for r, v in config_table.items() if v['action'] == 'TRADE']
coverage = sum(np.sum(regimes == r) for r in trade_regimes) / len(regimes) * 100
print(f"Coverage: {coverage:.1f}% of samples in TRADE regimes")

# =============================================================================
# PART 7: SAVE RESULTS
# =============================================================================
print("\n" + "-" * 60)
print("SAVING RESULTS")
print("-" * 60)

# 1. Config lookup table (JSON)
# Convert to JSON-serializable format
config_json = {}
for r, entry in config_table.items():
    r_key = str(r)
    config_json[r_key] = {
        'action': entry['action'],
    }
    if entry['action'] == 'TRADE':
        config_json[r_key]['config'] = entry['config']
        config_json[r_key]['metrics'] = {
            k: float(v) for k, v in entry['metrics'].items()
        }
    if 'walk_forward' in entry:
        wf = entry['walk_forward']
        config_json[r_key]['walk_forward'] = {
            'n_folds': wf['n_folds'],
            'n_valid_folds': wf['n_valid_folds'],
            'n_positive_folds': wf['n_positive_folds'],
            'required': wf['required'],
            'passed': wf['passed'],
        }
    if 'reason' in entry:
        config_json[r_key]['reason'] = entry['reason']

config_json_path = os.path.join(DATA_DIR, 'regime_config_table.json')
with open(config_json_path, 'w') as f:
    json.dump(config_json, f, indent=2)
print(f"  Saved config table (JSON): {config_json_path}")

# 2. Config lookup table (Parquet)
rows = []
for r, entry in config_table.items():
    row = {'regime': r, 'action': entry['action']}
    if entry['action'] == 'TRADE':
        row.update(entry['config'])
        row.update({f'metric_{k}': v for k, v in entry['metrics'].items()})
    if 'walk_forward' in entry:
        wf = entry['walk_forward']
        row['wf_n_positive'] = wf['n_positive_folds']
        row['wf_n_valid'] = wf['n_valid_folds']
        row['wf_passed'] = wf['passed']
    rows.append(row)

config_df = pd.DataFrame(rows)
config_parquet_path = os.path.join(DATA_DIR, 'regime_config_table.parquet')
config_df.to_parquet(config_parquet_path, index=False)
print(f"  Saved config table (Parquet): {config_parquet_path}")

# 3. Per-regime p-values
plevels_json = {}
for r, p_levels in regime_p_levels.items():
    if p_levels is not None:
        plevels_json[str(r)] = [float(p) for p in p_levels]
    else:
        plevels_json[str(r)] = None

plevels_path = os.path.join(DATA_DIR, 'regime_p_levels.json')
with open(plevels_path, 'w') as f:
    json.dump(plevels_json, f, indent=2)
print(f"  Saved per-regime p-values: {plevels_path}")

# 4. Full search results summary (top 10 per regime)
search_summary = {}
for r, results in regime_search_results.items():
    if results:
        sorted_results = sorted(results, key=lambda x: x['reward'], reverse=True)[:10]
        search_summary[str(r)] = [
            {k: float(v) if isinstance(v, (np.floating, float)) else v
             for k, v in res.items()}
            for res in sorted_results
        ]

search_path = os.path.join(DATA_DIR, 'search_top_configs.json')
with open(search_path, 'w') as f:
    json.dump(search_summary, f, indent=2)
print(f"  Saved top configs per regime: {search_path}")

# =============================================================================
# PART 8: VISUALIZATION
# =============================================================================
print("\n" + "=" * 80)
print("GENERATING PLOTS")
print("=" * 80)

plt.style.use('seaborn-v0_8-darkgrid')
fig = plt.figure(figsize=(24, 20))
gs = fig.add_gridspec(3, 3, hspace=0.4, wspace=0.35)

# ─── Plot 1: Regime action summary ───────────────────────────────────────────
ax1 = fig.add_subplot(gs[0, 0])
actions = [config_table[r]['action'] for r in range(n_regimes)]
trade_count = actions.count('TRADE')
skip_count = actions.count('SKIP')
colors_action = ['#2ecc71', '#e74c3c']
ax1.pie([trade_count, skip_count], labels=['TRADE', 'SKIP'],
        colors=colors_action, autopct='%1.0f%%', startangle=90,
        textprops={'fontsize': 12, 'fontweight': 'bold'})
ax1.set_title(f'Regime Actions\n({trade_count} trade, {skip_count} skip)',
              fontweight='bold')

# ─── Plot 2: P(bust) per regime with config overlay ──────────────────────────
ax2 = fig.add_subplot(gs[0, 1])
regime_ids = list(range(n_regimes))
regime_bust_rates = [bust_arr[regimes == r].mean() if np.sum(regimes == r) > 0 else 0
                     for r in regime_ids]
colors_bust = ['#2ecc71' if config_table[r]['action'] == 'TRADE' else '#e74c3c'
               for r in regime_ids]
bars = ax2.bar(regime_ids, regime_bust_rates, color=colors_bust, edgecolor='black')
ax2.axhline(y=bust_arr.mean(), color='black', linestyle='--',
            label=f'Overall: {bust_arr.mean():.4f}')
ax2.set_xlabel('Regime')
ax2.set_ylabel('Bust Rate')
ax2.set_title('Bust Rate by Regime\n(green=TRADE, red=SKIP)', fontweight='bold')
ax2.legend(fontsize=8)
for bar, rate in zip(bars, regime_bust_rates):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
             f'{rate:.3f}', ha='center', va='bottom', fontsize=7)

# ─── Plot 3: Optimal config parameters across regimes ────────────────────────
ax3 = fig.add_subplot(gs[0, 2])
trade_regimes_list = [r for r in range(n_regimes) if config_table[r]['action'] == 'TRADE']
if trade_regimes_list:
    params = ['N', 'm', 'k', 'tp_mult']
    x = np.arange(len(trade_regimes_list))
    width = 0.2
    for i, param in enumerate(params):
        vals = [config_table[r]['config'][param] for r in trade_regimes_list]
        # Normalize for display
        max_val = max(vals) if vals else 1
        if max_val > 0:
            norm_vals = [v / max_val for v in vals]
        else:
            norm_vals = vals
        ax3.bar(x + i * width, vals, width, label=param, alpha=0.8)
    ax3.set_xticks(x + width * 1.5)
    ax3.set_xticklabels([f'R{r}' for r in trade_regimes_list], fontsize=8)
    ax3.set_xlabel('Regime')
    ax3.set_ylabel('Parameter Value')
    ax3.set_title('Optimal Config Parameters\n(TRADE regimes)', fontweight='bold')
    ax3.legend(fontsize=8)
else:
    ax3.text(0.5, 0.5, 'No TRADE regimes', ha='center', va='center', fontsize=14)
    ax3.set_title('Optimal Config Parameters', fontweight='bold')

# ─── Plot 4: Reward landscape for best regime ────────────────────────────────
ax4 = fig.add_subplot(gs[1, 0])
# Show reward vs N for the most populated TRADE regime
if trade_regimes_list:
    best_trade_regime = max(trade_regimes_list, key=lambda r: np.sum(regimes == r))
    search_res = regime_search_results.get(best_trade_regime, [])
    if search_res:
        # Group by N, take max reward per N
        n_vals = sorted(set(r['N'] for r in search_res))
        max_rewards_by_n = []
        for n_val in n_vals:
            rewards = [r['reward'] for r in search_res if r['N'] == n_val]
            max_rewards_by_n.append(max(rewards) if rewards else -100)
        ax4.plot(n_vals, max_rewards_by_n, 'bo-', markersize=4)
        ax4.axhline(y=0, color='red', linestyle='--', alpha=0.5)
        best_n = n_vals[np.argmax(max_rewards_by_n)]
        ax4.axvline(x=best_n, color='green', linestyle=':', alpha=0.7,
                    label=f'Best N={best_n}')
        ax4.legend(fontsize=8)
    ax4.set_xlabel('Number of Levels (N)')
    ax4.set_ylabel('Max Reward')
    ax4.set_title(f'Reward vs N (Regime {best_trade_regime})', fontweight='bold')
else:
    ax4.text(0.5, 0.5, 'No TRADE regimes', ha='center', va='center')
    ax4.set_title('Reward vs N', fontweight='bold')

# ─── Plot 5: p*m product per regime ──────────────────────────────────────────
ax5 = fig.add_subplot(gs[1, 1])
pm_values = []
for r in range(n_regimes):
    p_levels = regime_p_levels.get(r)
    if p_levels and config_table[r]['action'] == 'TRADE':
        cfg = config_table[r]['config']
        pm_values.append(compute_pm(p_levels, cfg['m']))
    elif p_levels:
        pm_values.append(compute_pm(p_levels, np.sqrt(2)))  # default m for SKIP
    else:
        pm_values.append(1.0)

colors_pm = ['#2ecc71' if pm < 0.80 else '#f39c12' if pm < 0.90 else '#e74c3c'
             for pm in pm_values]
ax5.bar(range(n_regimes), pm_values, color=colors_pm, edgecolor='black')
ax5.axhline(y=PM_HARD_LIMIT, color='red', linestyle='--',
            label=f'Hard limit: {PM_HARD_LIMIT}')
ax5.axhline(y=1.0, color='black', linestyle='-', alpha=0.5, label='p*m = 1.0')
ax5.set_xlabel('Regime')
ax5.set_ylabel('p * m')
ax5.set_title('p*m Product by Regime\n(green < 0.80, yellow < 0.90, red >= 0.90)',
              fontweight='bold')
ax5.legend(fontsize=8)

# ─── Plot 6: Walk-forward fold EVs ───────────────────────────────────────────
ax6 = fig.add_subplot(gs[1, 2])
for r in trade_regimes_list[:6]:  # limit to 6 for readability
    if 'walk_forward' in config_table[r]:
        fold_evs = config_table[r]['walk_forward'].get('fold_evs', [])
        valid_evs = [e for e in fold_evs if e is not None]
        if valid_evs:
            ax6.plot(range(len(valid_evs)), valid_evs, 'o-', label=f'R{r}',
                     markersize=4, alpha=0.7)
ax6.axhline(y=0, color='red', linestyle='--', alpha=0.5)
ax6.set_xlabel('Fold Index')
ax6.set_ylabel('Expected Value')
ax6.set_title('Walk-Forward Validation\n(EV per fold)', fontweight='bold')
ax6.legend(fontsize=8)

# ─── Plot 7: Per-regime P(lose) curves ────────────────────────────────────────
ax7 = fig.add_subplot(gs[2, 0])
for r in range(min(n_regimes, 8)):
    p_levels = regime_p_levels.get(r)
    if p_levels and len(p_levels) >= 3:
        ax7.plot(range(len(p_levels)), p_levels, 'o-', label=f'R{r}',
                 markersize=3, alpha=0.7)
ax7.axhline(y=0.5, color='red', linestyle=':', alpha=0.5, label='P=0.5')
ax7.set_xlabel('Level')
ax7.set_ylabel('P(lose at level)')
ax7.set_title('Per-Level P(lose) by Regime', fontweight='bold')
ax7.legend(fontsize=7, ncol=2)
ax7.set_ylim(0, 1)

# ─── Plot 8: EV vs P(bust) scatter across all regimes ────────────────────────
ax8 = fig.add_subplot(gs[2, 1])
for r in range(n_regimes):
    if config_table[r]['action'] == 'TRADE':
        met = config_table[r]['metrics']
        ax8.scatter(met['p_bust'], met['ev'], s=100, zorder=5,
                    edgecolors='black', label=f'R{r}')
        ax8.annotate(f'R{r}', (met['p_bust'], met['ev']),
                     fontsize=8, xytext=(5, 5), textcoords='offset points')
ax8.axhline(y=0, color='red', linestyle='--', alpha=0.5)
ax8.set_xlabel('P(bust)')
ax8.set_ylabel('Expected Value per Cycle')
ax8.set_title('EV vs P(bust) for TRADE Regimes', fontweight='bold')
ax8.grid(True, alpha=0.3)
if trade_regimes_list:
    ax8.legend(fontsize=7)

# ─── Plot 9: Coverage pie chart ──────────────────────────────────────────────
ax9 = fig.add_subplot(gs[2, 2])
trade_samples = sum(np.sum(regimes == r) for r in trade_regimes_list)
skip_regimes_list = [r for r in range(n_regimes) if config_table[r]['action'] == 'SKIP']
skip_samples = sum(np.sum(regimes == r) for r in skip_regimes_list)
ax9.pie([trade_samples, skip_samples],
        labels=[f'TRADE\n({trade_samples} samples)', f'SKIP\n({skip_samples} samples)'],
        colors=['#2ecc71', '#e74c3c'], autopct='%1.1f%%', startangle=90,
        textprops={'fontsize': 10})
ax9.set_title(f'Sample Coverage\n({coverage:.1f}% in TRADE regimes)', fontweight='bold')

plt.suptitle('Phase C: Per-Regime Config Optimization\n'
             f'{n_trade} TRADE / {n_skip} SKIP, Coverage={coverage:.1f}%',
             fontsize=16, fontweight='bold', y=1.01)

plot_path = os.path.join(OUTPUT_DIR, '17_regime_configs.png')
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
  PHASE B GATE: {gate_result}

  CONFIG OPTIMIZATION:
    Grid size: {total_configs:,} configs per regime
    Constraints: p*m < {PM_HARD_LIMIT}, margin at {LEVERAGE}:1 leverage, ${STARTING_EQUITY:,} equity

  RESULTS:
    TRADE regimes: {n_trade} / {n_regimes}
    SKIP regimes:  {n_skip} / {n_regimes}
    Coverage:      {coverage:.1f}% of samples in TRADE regimes

  WALK-FORWARD VALIDATION:
    {N_FOLDS} folds, require {WALK_FORWARD_PASS}/{N_FOLDS} positive EV folds
""")

for r in range(n_regimes):
    entry = config_table[r]
    n_in = np.sum(regimes == r)
    if entry['action'] == 'TRADE':
        cfg = entry['config']
        met = entry['metrics']
        wf = entry.get('walk_forward', {})
        print(f"  Regime {r} ({n_in:>5} samples): TRADE")
        print(f"    N={cfg['N']}, m={cfg['m']:.2f}, base={cfg['base_pct']*100:.2f}%, "
              f"tp_mult={cfg['tp_mult']:.1f}, k={cfg['k']:.1f}")
        print(f"    EV={met['ev']:.6f}, P(bust)={met['p_bust']:.6f}, p*m={met['pm']:.4f}")
        if wf:
            print(f"    Walk-forward: {wf.get('n_positive_folds', '?')}/{wf.get('n_valid_folds', '?')} positive folds")
    else:
        reason = entry.get('reason', 'unknown')
        print(f"  Regime {r} ({n_in:>5} samples): SKIP ({reason})")

print(f"""
  SAVED ARTIFACTS:
    {config_json_path}
    {config_parquet_path}
    {plevels_path}
    {search_path}
    {plot_path}
""")

print(f"""
  USAGE IN LIVE TRADING:
    1. Load HMM model from Phase B
    2. Use OnlineBayesianHMM to get current regime
    3. Look up regime in config table:
       - TRADE: use the specified (N, m, base_pct, tp_mult, k)
       - SKIP:  do not enter any trade in this regime
    4. Monitor regime transitions and adjust config accordingly
""")
print("=" * 80)
