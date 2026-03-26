#!/usr/bin/env python3
"""
Phase F — Script 20b: Full Pipeline Validation v2
===================================================
Replaces HMM-based regime detection with direct danger scoring.

Architecture:
  Layer 1: DangerScorer — composite of choppiness, ADX, hurst, range_atr
  Layer 2: EntryBandit — Thompson Sampling on 5 danger levels
  Layer 3: Cycle simulation using historical outcomes
  Layer 4: TabularQLearner — duration-aware mid-cycle abort

Validation:
  1. Walk-forward on 20 years (2006-2025), expanding window
  2. Permutation test (200 shuffles) on danger scores
  3. 5-mode comparison: structural, +danger, +bandit, +qlearn, full
  4. PASS/FAIL gates

Requires:
  - notebooks/phase2/results/15_features_full.parquet (60,370 cycles, 103 busts)
"""

import os, sys, json, time, warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, 'data')
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

np.random.seed(42)


# ===========================================================================
# SECTION 0 — Load Data
# ===========================================================================
print("=" * 80)
print("SECTION 0: LOADING DATA")
print("=" * 80)

feat_path = os.path.join(RESULTS_DIR, '15_features_full.parquet')
assert os.path.exists(feat_path), f"Missing: {feat_path}"
df_all = pd.read_parquet(feat_path)
df_all['year'] = pd.to_datetime(df_all['datetime']).dt.year

# Feature columns
FEATURE_SUFFIXES = ('_adx', '_atr_ratio', '_chop', '_hurst', '_range_atr')
FEATURE_COLS = sorted([c for c in df_all.columns
                        if any(c.endswith(s) for s in FEATURE_SUFFIXES)])

# Ensure win_level column exists
if 'win_level' not in df_all.columns:
    df_all['win_level'] = np.where(df_all['is_bust'], -1, df_all['level_reached'].astype(int))

# Fill NaN features with column median (vectorized)
feat_medians = df_all[FEATURE_COLS].median()
df_all[FEATURE_COLS] = df_all[FEATURE_COLS].fillna(feat_medians)

print(f"  Loaded: {len(df_all):,} cycles, {int(df_all['is_bust'].sum())} busts")
print(f"  Years: {df_all['year'].min()}-{df_all['year'].max()} ({df_all['year'].nunique()} years)")
print(f"  Features: {len(FEATURE_COLS)} columns")
print(f"  Feature columns: {FEATURE_COLS}")


# ===========================================================================
# SECTION 1 — Component Definitions
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 1: COMPONENT DEFINITIONS")
print("=" * 80)

# --- Danger score feature mapping ---
# Which features to use and their weights + inversion flags
# Format: (column_name, weight, invert)
# invert=True means higher raw value = LESS dangerous (e.g. high ADX = trending = safer)
DANGER_FEATURES = [
    ('D1_range_atr',  0.30, True),   # low daily range/ATR = compressed = dangerous
    ('5m_chop',       0.15, False),   # high choppiness = dangerous
    ('15m_chop',      0.15, False),   # high choppiness = dangerous
    ('D1_chop',       0.10, False),   # high daily choppiness = dangerous
    ('5m_adx',        0.10, True),    # low ADX = no trend = dangerous
    ('5m_hurst',      0.10, False),   # distance from 0.5 (handled specially)
    ('1H_atr_ratio',  0.10, False),   # high ATR ratio = volatile = dangerous
]

# Verify weights sum to 1
assert abs(sum(w for _, w, _ in DANGER_FEATURES) - 1.0) < 1e-9, "Weights must sum to 1.0"


class DangerScorer:
    """Online danger scorer using weighted composite of market features.

    No fitting required — uses online running mean/std normalization.
    Returns a danger score in [0, 1] where higher = more dangerous for surefire.
    """

    def __init__(self, features_config=None, warmup_min=50, ema_alpha=0.005):
        self.features_config = features_config or DANGER_FEATURES
        self.n_features = len(self.features_config)
        self.warmup_min = warmup_min
        self.ema_alpha = ema_alpha

        # Online stats per raw feature
        self._n = 0
        self._mean = np.zeros(self.n_features)
        self._M2 = np.zeros(self.n_features)  # Welford online variance

    def _update_stats(self, raw_values):
        """Welford online mean/variance update."""
        self._n += 1
        delta = raw_values - self._mean
        self._mean += delta / self._n
        delta2 = raw_values - self._mean
        self._M2 += delta * delta2

    def _get_std(self):
        if self._n < 2:
            return np.ones(self.n_features)
        return np.sqrt(self._M2 / (self._n - 1)).clip(min=1e-8)

    def _extract_raw(self, features_dict):
        """Extract raw values for danger features from a feature dict/row."""
        raw = np.zeros(self.n_features)
        for i, (col, weight, invert) in enumerate(self.features_config):
            val = features_dict.get(col, np.nan)
            if col == '5m_hurst':
                # Special: distance from 0.5 (random walk), inverted
                # Close to 0.5 = mean-reverting market = dangerous for surefire
                val = abs(val - 0.5) if not np.isnan(val) else 0.0
            if np.isnan(val):
                val = self._mean[i] if self._n > 0 else 0.0
            raw[i] = val
        return raw

    def score(self, features_dict):
        """Compute danger score in [0,1] for a single cycle's features.

        Updates online stats and returns normalized weighted composite.
        """
        raw = self._extract_raw(features_dict)
        self._update_stats(raw)

        if self._n < self.warmup_min:
            return 0.5  # neutral during warmup

        # Z-score normalize
        std = self._get_std()
        z = (raw - self._mean) / std

        # Apply inversion: for inverted features, flip sign
        # (low raw value -> high z after inversion -> more dangerous)
        for i, (col, weight, invert) in enumerate(self.features_config):
            if invert:
                z[i] = -z[i]

        # Weighted sum -> sigmoid to [0,1]
        weights = np.array([w for _, w, _ in self.features_config])
        composite = np.dot(weights, z)

        # Sigmoid mapping to [0,1]
        score = 1.0 / (1.0 + np.exp(-composite))
        return float(score)

    def score_batch(self, feature_arrays):
        """Score a batch of cycles. feature_arrays is dict of col -> np.array.

        Returns array of danger scores. Updates online stats sequentially.
        """
        n = len(next(iter(feature_arrays.values())))
        scores = np.empty(n)
        for i in range(n):
            row = {col: feature_arrays[col][i] for col in feature_arrays}
            scores[i] = self.score(row)
        return scores

    def danger_level(self, score):
        """Map score [0,1] to danger level 0-4."""
        if score < 0.2:
            return 0
        elif score < 0.4:
            return 1
        elif score < 0.6:
            return 2
        elif score < 0.8:
            return 3
        else:
            return 4

    def reset(self):
        self._n = 0
        self._mean[:] = 0.0
        self._M2[:] = 0.0


class EntryBandit:
    """Thompson Sampling bandit for trade/skip per danger level (0-4).

    Asymmetric bust penalty: a bust costs 15x a normal loss in beta updates.
    Hard cutoff: always skip if danger > 0.9.
    """

    N_LEVELS = 5
    HARD_CUTOFF = 0.9
    BUST_PENALTY = 15.0

    def __init__(self, threshold=0.35):
        self.alpha = np.ones(self.N_LEVELS)       # successes (wins)
        self.beta_param = np.ones(self.N_LEVELS)   # failures (losses)
        self.threshold = threshold

    def should_trade(self, danger_score, danger_level):
        """Decide whether to trade. Returns True/False."""
        if danger_score > self.HARD_CUTOFF:
            return False

        p = np.random.beta(self.alpha[danger_level], self.beta_param[danger_level])
        return p > self.threshold

    def update(self, danger_level, traded, pnl_pct, is_bust=False):
        """Update posterior for the danger level."""
        if not traded:
            return
        dl = min(danger_level, self.N_LEVELS - 1)
        if pnl_pct > 0:
            self.alpha[dl] += 1.0
        else:
            self.beta_param[dl] += 1.0
            if is_bust:
                self.beta_param[dl] += self.BUST_PENALTY

    def reset(self):
        self.alpha[:] = 1.0
        self.beta_param[:] = 1.0


class TabularQLearner:
    """Duration-aware Q-learner for mid-cycle abort.

    State = (current_level[0-12], bars_bin[0-4], danger_entry[0-4], danger_now[0-4])
    Action = 0 (continue) | 1 (abort)
    Total states: 13 * 5 * 5 * 5 = 1,625
    """

    LEVEL_BINS = 13    # 0-12
    BARS_BINS = 5      # duration bins
    DANGER_BINS = 5    # 0-4
    N_ACTIONS = 2

    # Duration bin edges (bars): [0-5, 6-10, 11-20, 21-50, 51+]
    BARS_EDGES = [0, 6, 11, 21, 51]

    def __init__(self, lr=0.05, gamma=0.95, epsilon=0.03):
        self.n_states = (self.LEVEL_BINS * self.BARS_BINS *
                         self.DANGER_BINS * self.DANGER_BINS)
        self.Q = np.zeros((self.n_states, self.N_ACTIONS))
        self.visits = np.zeros((self.n_states, self.N_ACTIONS), dtype=np.int32)
        self.lr = lr
        self.gamma = gamma
        self.epsilon = epsilon

    @staticmethod
    def _bars_bin(duration_bars):
        """Map duration in bars to bin 0-4."""
        if duration_bars < 6:
            return 0
        elif duration_bars < 11:
            return 1
        elif duration_bars < 21:
            return 2
        elif duration_bars < 51:
            return 3
        else:
            return 4

    def _encode(self, level, bars_bin, danger_entry, danger_now):
        level = min(level, self.LEVEL_BINS - 1)
        bb = min(bars_bin, self.BARS_BINS - 1)
        de = min(danger_entry, self.DANGER_BINS - 1)
        dn = min(danger_now, self.DANGER_BINS - 1)
        idx = (level * self.BARS_BINS * self.DANGER_BINS * self.DANGER_BINS
               + bb * self.DANGER_BINS * self.DANGER_BINS
               + de * self.DANGER_BINS
               + dn)
        return min(idx, self.n_states - 1)

    def choose_action(self, level, bars_bin, danger_entry, danger_now):
        state = self._encode(level, bars_bin, danger_entry, danger_now)
        if np.random.rand() < self.epsilon:
            return np.random.randint(self.N_ACTIONS)
        return int(np.argmax(self.Q[state]))

    def update(self, level, bars_bin, danger_entry, danger_now,
               action, reward, next_state_tuple=None, done=True):
        state = self._encode(level, bars_bin, danger_entry, danger_now)
        self.visits[state, action] += 1

        if done or next_state_tuple is None:
            target = reward
        else:
            ns = self._encode(*next_state_tuple)
            target = reward + self.gamma * np.max(self.Q[ns])

        self.Q[state, action] += self.lr * (target - self.Q[state, action])

    def reset(self):
        self.Q[:] = 0.0
        self.visits[:] = 0

print(f"  Components defined: DangerScorer, EntryBandit, TabularQLearner")
print(f"  Q-learner states: {TabularQLearner().n_states} (13 levels x 5 bars_bins x 5 danger_entry x 5 danger_now)")


# ===========================================================================
# SECTION 2 — Pre-compute Arrays (vectorized)
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 2: PRE-COMPUTING FEATURE ARRAYS")
print("=" * 80)

# Pre-extract arrays for danger scoring features (avoid per-row dict lookups)
danger_col_names = [col for col, _, _ in DANGER_FEATURES]
danger_col_arrays = {}
for col in danger_col_names:
    arr = df_all[col].values.astype(np.float64).copy()
    # Handle hurst distance from 0.5
    if col == '5m_hurst':
        arr = np.abs(arr - 0.5)
    danger_col_arrays[col] = arr

# Pre-extract outcome arrays
pnl_pct_arr = df_all['pnl_pct'].values.astype(np.float64)
is_bust_arr = df_all['is_bust'].values.astype(bool)
win_level_arr = df_all['win_level'].values.astype(np.int32)
levels_used_arr = df_all['levels_used'].values.astype(np.int32)
duration_bars_arr = df_all['duration_bars'].values.astype(np.int32)
year_arr = df_all['year'].values.astype(np.int32)

# Build full feature dict arrays for batch scoring
all_feat_arrays = {}
for col in FEATURE_COLS:
    all_feat_arrays[col] = df_all[col].values.astype(np.float64)

print(f"  Pre-computed {len(danger_col_names)} danger feature arrays")
print(f"  Pre-computed {len(FEATURE_COLS)} full feature arrays")
print(f"  Total cycles: {len(df_all):,}")


# ===========================================================================
# SECTION 3 — run_cycle() and Pipeline Runner
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 3: PIPELINE FUNCTION — run_cycle()")
print("=" * 80)


def run_cycle(idx, scorer, bandit, q_learner, mode='full'):
    """Execute one cycle through the v2 pipeline layers.

    Args:
        idx: integer index into the pre-computed arrays
        scorer: DangerScorer instance
        bandit: EntryBandit instance
        q_learner: TabularQLearner instance
        mode: 'structural' | '+danger' | '+bandit' | '+qlearn' | 'full'

    Returns:
        dict with pnl_pct, traded, aborted, danger_score, etc.
    """
    # Outcome data
    actual_pnl = pnl_pct_arr[idx]
    actual_bust = is_bust_arr[idx]
    actual_levels = levels_used_arr[idx]
    actual_duration = duration_bars_arr[idx]

    # ---- Layer 1: Danger score ----
    if mode == 'structural':
        danger_score = 0.5
        danger_lvl = 2
    else:
        # Build feature dict for this cycle from pre-computed arrays
        feat_row = {}
        for col in danger_col_names:
            feat_row[col] = danger_col_arrays[col][idx]
        # Note: 5m_hurst already transformed to |h-0.5| in pre-compute
        # But scorer also does this, so pass original for non-hurst
        # Actually we need to pass the original values and let scorer handle it
        # Undo the hurst transform for the scorer (it will redo it)
        feat_row_orig = {}
        for col in danger_col_names:
            if col == '5m_hurst':
                feat_row_orig[col] = all_feat_arrays[col][idx]  # original hurst
            else:
                feat_row_orig[col] = danger_col_arrays[col][idx]
        danger_score = scorer.score(feat_row_orig)
        danger_lvl = scorer.danger_level(danger_score)

    # ---- Layer 2: Entry gate ----
    if mode == 'structural':
        do_trade = True
    elif mode == '+danger':
        # Simple threshold: skip if danger > 0.7
        do_trade = danger_score <= 0.7
    elif mode == '+bandit' or mode == 'full':
        do_trade = bandit.should_trade(danger_score, danger_lvl)
    elif mode == '+qlearn':
        do_trade = True  # Q-learn mode has no entry gate
    else:
        do_trade = True

    if not do_trade:
        # Update bandit with skip (no outcome learning)
        return {'pnl_pct': 0.0, 'traded': False, 'aborted': False,
                'danger_score': danger_score, 'danger_level': danger_lvl,
                'is_bust_actual': actual_bust}

    # ---- Layer 3: Use historical outcome ----
    # The cycle outcome is already recorded; we just read it.

    # ---- Layer 4: Mid-cycle Q-learner abort ----
    # Only consider abort for cycles that reach level >= 2 AND duration > 10 bars.
    # These are the cycles most at risk of busting (91x higher bust rate for >20 bars).
    aborted = False
    abort_pnl = 0.0

    if (mode in ('full', '+qlearn') and actual_levels >= 3
            and actual_duration > 20):
        # Consider abort in risky territory:
        #   - Level >= 3 (deep enough in hedge chain)
        #   - Duration > 20 bars (91x higher bust rate empirically)
        # The Q-learner uses danger_entry + danger_now in its state to decide
        entry_danger_lvl = danger_lvl
        bars_bin = TabularQLearner._bars_bin(actual_duration)

        # Check abort at the deepest level reached (not every intermediate level)
        # This is a single abort decision: should we bail out at this depth?
        deepest_lvl = actual_levels - 1
        mid_danger_lvl = danger_lvl

        # Simulate slight danger drift for deep cycles
        if deepest_lvl > 2:
            shift = np.random.choice([-1, 0, 0, 1, 1])  # slight upward bias for long cycles
            mid_danger_lvl = max(0, min(4, mid_danger_lvl + shift))

        action = q_learner.choose_action(
            deepest_lvl, bars_bin, entry_danger_lvl, mid_danger_lvl)

        if action == 1:  # ABORT
            aborted = True
            # Abort cost: small controlled loss. With surefire, closing all hedges
            # at the deepest level means losing roughly the last hedge distance.
            # Scale: base_pct * sqrt(2)^level * partial_loss_fraction
            # Keep small: typical win is ~0.004%, so abort cost ~ 0.05-0.5%
            abort_pnl = -(0.005 * np.sqrt(2) ** min(deepest_lvl, 6) * 0.1) * 100
            abort_pnl = max(abort_pnl, -0.5)  # cap at 0.5% loss

            # Counterfactual reward: what did we gain/lose vs letting it play out?
            reward = abort_pnl - actual_pnl

            q_learner.update(deepest_lvl, bars_bin, entry_danger_lvl,
                             mid_danger_lvl, 1, reward, done=True)

            if mode in ('full', '+bandit'):
                bandit.update(danger_lvl, True, abort_pnl, is_bust=False)

            return {'pnl_pct': abort_pnl, 'traded': True, 'aborted': True,
                    'abort_level': deepest_lvl, 'danger_score': danger_score,
                    'danger_level': danger_lvl, 'is_bust_actual': actual_bust}

        # Q-update for continue (terminal — cycle resolved naturally)
        q_learner.update(deepest_lvl, bars_bin, entry_danger_lvl,
                         mid_danger_lvl, 0, actual_pnl, done=True)

    # Bandit update with actual outcome
    if mode in ('full', '+bandit', '+danger') and do_trade:
        bandit.update(danger_lvl, True, actual_pnl, is_bust=actual_bust)

    return {'pnl_pct': actual_pnl, 'traded': True, 'aborted': False,
            'danger_score': danger_score, 'danger_level': danger_lvl,
            'is_bust_actual': actual_bust}


def run_pipeline(indices, mode='full', scorer=None, bandit=None,
                 q_learner=None, seed=42):
    """Run the pipeline on a set of cycle indices. Returns list of result dicts."""
    np.random.seed(seed)
    if scorer is None:
        scorer = DangerScorer()
    if bandit is None:
        bandit = EntryBandit()
    if q_learner is None:
        q_learner = TabularQLearner()

    results = []
    for idx in indices:
        r = run_cycle(idx, scorer, bandit, q_learner, mode=mode)
        results.append(r)
    return results


def compute_metrics(results, actual_busts=None):
    """Compute summary metrics from pipeline results."""
    traded = [r for r in results if r['traded']]
    skipped = [r for r in results if not r['traded']]
    aborted = [r for r in results if r.get('aborted', False)]

    if not traded:
        return {'n_total': len(results), 'n_traded': 0, 'n_skipped': len(results),
                'skip_rate': 100.0, 'abort_rate': 0.0,
                'bust_rate': 0.0, 'win_rate': 0.0, 'pf': 0.0,
                'max_dd': 0.0, 'total_return': 0.0, 'sharpe': 0.0,
                'n_aborted': 0, 'busts_avoided': 0, 'busts_hit': 0}

    pnls = np.array([r['pnl_pct'] for r in traded])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]

    gross_win = wins.sum() if len(wins) > 0 else 0.0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 1e-9
    pf = gross_win / gross_loss

    # Busts: traded cycles where actual outcome was a bust
    busts_hit = sum(1 for r in traded
                    if r.get('is_bust_actual', False) and not r.get('aborted', False))
    busts_avoided_by_skip = sum(1 for r in skipped if r.get('is_bust_actual', False))
    busts_avoided_by_abort = sum(1 for r in aborted if r.get('is_bust_actual', False))
    busts_avoided = busts_avoided_by_skip + busts_avoided_by_abort

    # Equity curve
    equity = np.empty(len(pnls) + 1)
    equity[0] = 100.0
    for i, p in enumerate(pnls):
        equity[i + 1] = equity[i] * (1 + p / 100)

    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.where(peak > 0, peak, 1.0)
    max_dd = dd.min() * 100

    sharpe = float(np.mean(pnls) / np.std(pnls)) if np.std(pnls) > 0 else 0.0

    return {
        'n_total': len(results),
        'n_traded': len(traded),
        'n_skipped': len(skipped),
        'n_aborted': len(aborted),
        'skip_rate': len(skipped) / len(results) * 100,
        'abort_rate': len(aborted) / len(results) * 100,
        'bust_rate': busts_hit / len(traded) * 100 if traded else 0.0,
        'win_rate': len(wins) / len(traded) * 100,
        'pf': float(pf),
        'max_dd': float(max_dd),
        'total_return': float(equity[-1] / equity[0] - 1) * 100,
        'sharpe': sharpe,
        'busts_avoided': busts_avoided,
        'busts_hit': busts_hit,
        'equity_curve': equity.tolist(),
    }


print("  run_cycle() defined — 4 layers: DangerScore -> EntryGate -> Outcome -> Q-Abort")


# ===========================================================================
# SECTION 4 — Full-Dataset Mode Comparison
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 4: 5-MODE COMPARISON (full dataset)")
print("=" * 80)

MODES = ['structural', '+danger', '+bandit', '+qlearn', 'full']
NICE_NAMES = {
    'structural': 'Structural',
    '+danger':    '+Danger',
    '+bandit':    '+Bandit',
    '+qlearn':    '+Q-Learn',
    'full':       'Full',
}

all_indices = np.arange(len(df_all))
comparison_data = {}

for mode in MODES:
    t0 = time.time()
    results = run_pipeline(all_indices, mode=mode, seed=42)
    metrics = compute_metrics(results)
    comparison_data[mode] = metrics
    elapsed = time.time() - t0
    print(f"  {NICE_NAMES[mode]:<12}: return={metrics['total_return']:>8.2f}%, "
          f"bust_rate={metrics['bust_rate']:.3f}%, "
          f"skip={metrics['skip_rate']:.1f}%, abort={metrics['abort_rate']:.1f}%, "
          f"busts_avoided={metrics['busts_avoided']}, "
          f"PF={metrics['pf']:.2f}, time={elapsed:.1f}s")


# ===========================================================================
# SECTION 5 — Comparison Table
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 5: COMPARISON TABLE")
print("=" * 80)

structural_busts = comparison_data['structural']['busts_hit']

ROWS = [
    ('Bust Rate %',      'bust_rate',       '{:.3f}'),
    ('Skip Rate %',      'skip_rate',       '{:.1f}'),
    ('Abort Rate %',     'abort_rate',      '{:.1f}'),
    ('P&L (total) %',    'total_return',    '{:.2f}'),
    ('Busts Avoided',    'busts_avoided',   '{:d}'),
    ('Busts Hit',        'busts_hit',       '{:d}'),
    ('Win Rate %',       'win_rate',        '{:.1f}'),
    ('Profit Factor',    'pf',              '{:.2f}'),
    ('Max Drawdown %',   'max_dd',          '{:.2f}'),
    ('Sharpe',           'sharpe',          '{:.4f}'),
    ('Traded',           'n_traded',        '{:d}'),
    ('Skipped',          'n_skipped',       '{:d}'),
    ('Aborted',          'n_aborted',       '{:d}'),
]

header = f"  {'Metric':<20}" + "".join(f"{NICE_NAMES[m]:>14}" for m in MODES)
print(f"\n{header}")
print(f"  {'-' * (20 + 14 * len(MODES))}")

for label, key, fmt in ROWS:
    row_str = f"  {label:<20}"
    for mode in MODES:
        val = comparison_data[mode].get(key, 0)
        if isinstance(val, float):
            row_str += f"{fmt.format(val):>14}"
        elif isinstance(val, int):
            row_str += f"{fmt.format(val):>14}"
        else:
            row_str += f"{str(val):>14}"
    print(row_str)


# ===========================================================================
# SECTION 6 — Walk-Forward Validation
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 6: WALK-FORWARD VALIDATION")
print("=" * 80)

all_years = sorted(df_all['year'].unique())
# Use expanding window: train on all years before test year
# First test year needs at least 1 year of training
test_years = all_years[1:]  # skip first year (used only for training)

print(f"  All years: {all_years}")
print(f"  Test years: {test_years} ({len(test_years)} years)")

# Build year->indices mapping
year_indices = {}
for y in all_years:
    year_indices[y] = np.where(year_arr == y)[0]

wf_results = {}

for mode in MODES:
    year_metrics = []
    for test_year in test_years:
        # Expanding window: train on all years < test_year
        train_indices = np.concatenate([year_indices[y] for y in all_years if y < test_year])
        test_idx = year_indices[test_year]

        if len(test_idx) < 10:
            continue

        # Fresh components
        scorer = DangerScorer()
        bandit = EntryBandit()
        q_learner = TabularQLearner()

        # Warm up on training data (last 2000 cycles for speed)
        warmup_start = max(0, len(train_indices) - 2000)
        warmup_indices = train_indices[warmup_start:]
        _ = run_pipeline(warmup_indices, mode=mode, scorer=scorer,
                         bandit=bandit, q_learner=q_learner, seed=test_year)

        # Evaluate on test year (components continue learning online)
        test_results = run_pipeline(test_idx, mode=mode, scorer=scorer,
                                     bandit=bandit, q_learner=q_learner,
                                     seed=test_year + 1000)
        metrics = compute_metrics(test_results)
        metrics['year'] = int(test_year)
        year_metrics.append(metrics)

    wf_results[mode] = year_metrics

# Print walk-forward results
for mode in MODES:
    yrs = wf_results[mode]
    if not yrs:
        continue
    profitable = sum(1 for y in yrs if y['total_return'] > 0)
    returns = [y['total_return'] for y in yrs]

    print(f"\n  MODE: {NICE_NAMES[mode]}")
    print(f"  {'Year':<6} {'Return%':>9} {'BustR%':>8} {'WinR%':>8} {'PF':>7} {'MaxDD%':>8} {'Traded':>7} {'Skip':>6} {'Abort':>6}")
    print(f"  {'-'*68}")
    for y in yrs:
        print(f"  {y['year']:<6} {y['total_return']:>9.2f} {y['bust_rate']:>8.3f} "
              f"{y['win_rate']:>8.1f} {y['pf']:>7.2f} {y['max_dd']:>8.2f} "
              f"{y['n_traded']:>7} {y['n_skipped']:>6} {y['n_aborted']:>6}")
    print(f"  ---")
    print(f"  Profitable: {profitable}/{len(yrs)}, "
          f"Avg return: {np.mean(returns):.2f}%, "
          f"Worst: {np.min(returns):.2f}%, Best: {np.max(returns):.2f}%")


# ===========================================================================
# SECTION 7 — Permutation Test (danger scores)
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 7: PERMUTATION TEST (200 shuffles)")
print("=" * 80)

N_PERMUTATIONS = 200

# Use '+danger' mode for permutation test — this isolates the danger scoring
# contribution without Q-learner noise. Tests whether danger scoring adds real
# value above random feature assignment.
real_metrics_danger = comparison_data['+danger']
real_return = real_metrics_danger['total_return']
real_bust_rate = real_metrics_danger['bust_rate']

print(f"  Real +danger mode: return={real_return:.2f}%, bust_rate={real_bust_rate:.3f}%")
print(f"  Shuffling danger scores (destroys feature-danger relationship)...")

# For permutation: we shuffle the mapping between cycles and their features
# This tests whether the danger scoring adds real value
shuffled_returns = np.empty(N_PERMUTATIONS)
shuffled_bust_rates = np.empty(N_PERMUTATIONS)

for p_i in range(N_PERMUTATIONS):
    # Shuffle feature arrays for danger scoring
    perm = np.random.RandomState(p_i).permutation(len(df_all))

    # Temporarily swap danger_col_arrays
    saved_arrays = {}
    for col in danger_col_names:
        saved_arrays[col] = danger_col_arrays[col].copy()
        danger_col_arrays[col] = danger_col_arrays[col][perm]

    # Also shuffle the full feature arrays used by scorer
    saved_full = {}
    for col in all_feat_arrays:
        if col in danger_col_names or col == '5m_hurst':
            saved_full[col] = all_feat_arrays[col].copy()
            all_feat_arrays[col] = all_feat_arrays[col][perm]

    # Run +danger pipeline with shuffled features (isolates danger scoring)
    perm_results = run_pipeline(all_indices, mode='+danger', seed=p_i + 5000)
    pm = compute_metrics(perm_results)
    shuffled_returns[p_i] = pm['total_return']
    shuffled_bust_rates[p_i] = pm['bust_rate']

    # Restore
    for col in danger_col_names:
        danger_col_arrays[col] = saved_arrays[col]
    for col in saved_full:
        all_feat_arrays[col] = saved_full[col]

    if (p_i + 1) % 50 == 0:
        print(f"    ... {p_i + 1}/{N_PERMUTATIONS} shuffles done")

# p-value: fraction where shuffled beats real
pval_return = float(np.mean(shuffled_returns >= real_return))
pval_bust = float(np.mean(shuffled_bust_rates <= real_bust_rate))

print(f"\n  Danger score permutation test:")
print(f"    Return: real={real_return:.2f}%, shuffled_mean={shuffled_returns.mean():.2f}%, "
      f"p={pval_return:.4f} {'PASS' if pval_return < 0.01 else 'FAIL'}")
print(f"    Bust rate: real={real_bust_rate:.3f}%, shuffled_mean={shuffled_bust_rates.mean():.3f}%, "
      f"p={pval_bust:.4f} {'PASS' if pval_bust < 0.01 else 'FAIL'}")

PERM_PASS = pval_return < 0.01 or pval_bust < 0.01


# ===========================================================================
# SECTION 8 — Summary with PASS/FAIL Gates
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 8: PASS/FAIL GATES")
print("=" * 80)

gates = {}

# Gate 1: Danger score permutation p < 0.01
gates['permutation'] = PERM_PASS
print(f"\n  GATE 1 — Danger Score Permutation (p < 0.01):")
print(f"    p_return = {pval_return:.4f}, p_bust = {pval_bust:.4f}")
print(f"    {'PASS' if PERM_PASS else 'FAIL'}")

# Gate 2: Walk-forward 80%+ profitable years (full mode)
wf_full = wf_results.get('full', [])
n_profitable_full = sum(1 for y in wf_full if y['total_return'] > 0)
n_total_years = len(wf_full)
pct_profitable = n_profitable_full / n_total_years * 100 if n_total_years > 0 else 0
gates['walk_forward'] = pct_profitable >= 80.0
print(f"\n  GATE 2 — Walk-Forward (80%+ profitable years):")
print(f"    Full mode: {n_profitable_full}/{n_total_years} profitable ({pct_profitable:.1f}%)")
for mode in MODES:
    yrs = wf_results.get(mode, [])
    n_prof = sum(1 for y in yrs if y['total_return'] > 0)
    print(f"    {NICE_NAMES[mode]:<12}: {n_prof}/{len(yrs)} profitable")
print(f"    {'PASS' if gates['walk_forward'] else 'FAIL'}")

# Gate 3: Bust rate reduction > 30% (full vs structural)
structural_br = comparison_data['structural']['bust_rate']
full_br = comparison_data['full']['bust_rate']
if structural_br > 0:
    bust_reduction = (structural_br - full_br) / structural_br * 100
else:
    bust_reduction = 0.0
gates['bust_reduction'] = bust_reduction > 30.0
print(f"\n  GATE 3 — Bust Rate Reduction (> 30%):")
print(f"    Structural: {structural_br:.3f}%, Full: {full_br:.3f}%, "
      f"Reduction: {bust_reduction:.1f}%")
print(f"    {'PASS' if gates['bust_reduction'] else 'FAIL'}")

# Gate 4: P&L impact not worse than -10%
structural_ret = comparison_data['structural']['total_return']
full_ret = comparison_data['full']['total_return']
if structural_ret > 0:
    pnl_impact = (full_ret - structural_ret) / structural_ret * 100
elif structural_ret < 0:
    pnl_impact = (structural_ret - full_ret) / abs(structural_ret) * 100
else:
    pnl_impact = 0.0
gates['pnl_impact'] = pnl_impact > -10.0
print(f"\n  GATE 4 — P&L Impact (not worse than -10%):")
print(f"    Structural return: {structural_ret:.2f}%, Full return: {full_ret:.2f}%, "
      f"Impact: {pnl_impact:+.1f}%")
print(f"    {'PASS' if gates['pnl_impact'] else 'FAIL'}")

# Final summary
n_gates = sum(gates.values())
print(f"\n  {'='*60}")
print(f"  GATES PASSED: {n_gates}/4")
for name, passed in gates.items():
    print(f"    {name:<20}: {'PASS' if passed else 'FAIL'}")

if n_gates == 4:
    recommendation = "SHIP FULL PIPELINE (danger + bandit + Q-learner)"
elif n_gates >= 3:
    recommendation = "SHIP WITH CAVEATS — review failing gate"
elif n_gates >= 2:
    # Check which individual components help
    useful = []
    if comparison_data['+danger']['bust_rate'] < structural_br:
        useful.append('+danger')
    if comparison_data['+bandit']['bust_rate'] < structural_br:
        useful.append('+bandit')
    if comparison_data['+qlearn']['bust_rate'] < structural_br:
        useful.append('+qlearn')
    if useful:
        recommendation = f"SHIP PARTIAL ({', '.join(useful)})"
    else:
        recommendation = "SHIP STRUCTURAL ONLY"
else:
    recommendation = "SHIP STRUCTURAL ONLY — adaptive layers not validated"

print(f"\n  >>> {recommendation} <<<")


# ===========================================================================
# SECTION 9 — Plots
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 9: GENERATING PLOTS")
print("=" * 80)

fig = plt.figure(figsize=(24, 20))
gs = GridSpec(3, 3, hspace=0.35, wspace=0.3)
colors = ['#3498db', '#2ecc71', '#e67e22', '#9b59b6', '#e74c3c']

# --- Plot 1: Walk-forward annual returns ---
ax1 = fig.add_subplot(gs[0, 0])
for mi, mode in enumerate(MODES):
    yrs = wf_results.get(mode, [])
    if not yrs:
        continue
    years = [y['year'] for y in yrs]
    rets = [y['total_return'] for y in yrs]
    ax1.plot(years, rets, 'o-', label=NICE_NAMES[mode], markersize=3,
             alpha=0.8, color=colors[mi])
ax1.axhline(y=0, color='black', linewidth=0.5)
ax1.set_xlabel('Year')
ax1.set_ylabel('Return %')
ax1.set_title('Walk-Forward: Annual Returns')
ax1.legend(fontsize=7)
ax1.grid(True, alpha=0.3)

# --- Plot 2: Comparison bar chart (total return) ---
ax2 = fig.add_subplot(gs[0, 1])
mode_labels = [NICE_NAMES[m] for m in MODES]
rets = [comparison_data[m]['total_return'] for m in MODES]
ax2.bar(range(len(MODES)), rets, color=colors, alpha=0.8, edgecolor='black')
ax2.set_xticks(range(len(MODES)))
ax2.set_xticklabels(mode_labels, fontsize=9)
ax2.set_ylabel('Total Return %')
ax2.set_title('Component Comparison: Total Return')
ax2.grid(True, alpha=0.3, axis='y')

# --- Plot 3: Bust rate comparison ---
ax3 = fig.add_subplot(gs[0, 2])
brs = [comparison_data[m]['bust_rate'] for m in MODES]
ax3.bar(range(len(MODES)), brs, color=colors, alpha=0.8, edgecolor='black')
ax3.set_xticks(range(len(MODES)))
ax3.set_xticklabels(mode_labels, fontsize=9)
ax3.set_ylabel('Bust Rate %')
ax3.set_title('Component Comparison: Bust Rate')
ax3.grid(True, alpha=0.3, axis='y')

# --- Plot 4: Equity curves ---
ax4 = fig.add_subplot(gs[1, 0])
for mi, mode in enumerate(MODES):
    eq = comparison_data[mode].get('equity_curve', [100])
    ax4.plot(range(len(eq)), eq, label=NICE_NAMES[mode],
             alpha=0.8, color=colors[mi], linewidth=0.8)
ax4.set_xlabel('Cycle #')
ax4.set_ylabel('Equity (normalized)')
ax4.set_title('Equity Curves by Pipeline Mode')
ax4.legend(fontsize=7)
ax4.grid(True, alpha=0.3)

# --- Plot 5: Permutation test distribution ---
ax5 = fig.add_subplot(gs[1, 1])
ax5.hist(shuffled_returns, bins=40, alpha=0.6, label='Shuffled returns',
         color='steelblue', density=True)
ax5.axvline(x=real_return, color='red', linewidth=2, linestyle='--',
            label=f'Real: {real_return:.2f}%')
ax5.set_xlabel('Total Return %')
ax5.set_ylabel('Density')
ax5.set_title(f'Permutation Test (p={pval_return:.4f})')
ax5.legend(fontsize=8)
ax5.grid(True, alpha=0.3)

# --- Plot 6: Busts avoided breakdown ---
ax6 = fig.add_subplot(gs[1, 2])
avoided = [comparison_data[m]['busts_avoided'] for m in MODES]
hit = [comparison_data[m]['busts_hit'] for m in MODES]
x = np.arange(len(MODES))
w = 0.35
ax6.bar(x - w/2, hit, w, label='Busts Hit', color='#e74c3c', alpha=0.8)
ax6.bar(x + w/2, avoided, w, label='Busts Avoided', color='#2ecc71', alpha=0.8)
ax6.set_xticks(x)
ax6.set_xticklabels(mode_labels, fontsize=9)
ax6.set_ylabel('Count')
ax6.set_title('Busts: Hit vs Avoided')
ax6.legend(fontsize=8)
ax6.grid(True, alpha=0.3, axis='y')

# --- Plot 7: Walk-forward bust rates ---
ax7 = fig.add_subplot(gs[2, 0])
for mi, mode in enumerate(['structural', 'full']):
    yrs = wf_results.get(mode, [])
    if not yrs:
        continue
    years = [y['year'] for y in yrs]
    brs_wf = [y['bust_rate'] for y in yrs]
    ax7.plot(years, brs_wf, 'o-', label=NICE_NAMES[mode], markersize=4,
             alpha=0.8, color=colors[MODES.index(mode)])
ax7.set_xlabel('Year')
ax7.set_ylabel('Bust Rate %')
ax7.set_title('Walk-Forward: Bust Rate by Year')
ax7.legend(fontsize=8)
ax7.grid(True, alpha=0.3)

# --- Plot 8: Skip and abort rates ---
ax8 = fig.add_subplot(gs[2, 1])
skip_rates = [comparison_data[m]['skip_rate'] for m in MODES]
abort_rates = [comparison_data[m]['abort_rate'] for m in MODES]
ax8.bar(x - w/2, skip_rates, w, label='Skip Rate %', color='#f39c12', alpha=0.8)
ax8.bar(x + w/2, abort_rates, w, label='Abort Rate %', color='#9b59b6', alpha=0.8)
ax8.set_xticks(x)
ax8.set_xticklabels(mode_labels, fontsize=9)
ax8.set_ylabel('Rate %')
ax8.set_title('Skip & Abort Rates by Mode')
ax8.legend(fontsize=8)
ax8.grid(True, alpha=0.3, axis='y')

# --- Plot 9: PASS/FAIL summary ---
ax9 = fig.add_subplot(gs[2, 2])
gate_names = list(gates.keys())
gate_vals = [1 if v else 0 for v in gates.values()]
gate_colors = ['#2ecc71' if v else '#e74c3c' for v in gates.values()]
ax9.barh(range(len(gates)), gate_vals, color=gate_colors, alpha=0.8, edgecolor='black')
ax9.set_yticks(range(len(gates)))
ax9.set_yticklabels([n.replace('_', ' ').title() for n in gate_names], fontsize=10)
ax9.set_xlim(-0.1, 1.5)
ax9.set_xlabel('')
ax9.set_title(f'PASS/FAIL Gates ({n_gates}/4)')
for i, (name, passed) in enumerate(gates.items()):
    ax9.text(0.5, i, 'PASS' if passed else 'FAIL', ha='center', va='center',
             fontsize=12, fontweight='bold', color='white')
ax9.set_xticks([])
ax9.grid(False)

plt.suptitle('Phase F v2: Full Pipeline Validation\n'
             'Danger Scoring + Thompson Bandit + Duration-Aware Q-Learner',
             fontsize=14, fontweight='bold', y=0.99)

plot_path = os.path.join(RESULTS_DIR, '20b_full_validation_v2.png')
plt.savefig(plot_path, dpi=150, bbox_inches='tight')
print(f"  Saved: {plot_path}")
plt.close()


# ===========================================================================
# SECTION 10 — Save Results
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 10: SAVING RESULTS")
print("=" * 80)

validation_results = {
    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    'version': 'v2_danger_scoring',
    'recommendation': recommendation,
    'gates': {k: bool(v) for k, v in gates.items()},
    'n_gates_passed': int(n_gates),
    'permutation_test': {
        'n_shuffles': N_PERMUTATIONS,
        'p_return': float(pval_return),
        'p_bust_rate': float(pval_bust),
        'real_return': float(real_return),
        'real_bust_rate': float(real_bust_rate),
        'shuffled_return_mean': float(shuffled_returns.mean()),
        'shuffled_bust_rate_mean': float(shuffled_bust_rates.mean()),
        'pass': bool(PERM_PASS),
    },
    'bust_reduction': {
        'structural_bust_rate': float(structural_br),
        'full_bust_rate': float(full_br),
        'reduction_pct': float(bust_reduction),
    },
    'pnl_impact': {
        'structural_return': float(structural_ret),
        'full_return': float(full_ret),
        'impact_pct': float(pnl_impact),
    },
    'comparison_table': {},
    'walk_forward': {},
}

# Comparison table
for mode in MODES:
    m = comparison_data[mode]
    validation_results['comparison_table'][NICE_NAMES[mode]] = {
        'bust_rate': float(m['bust_rate']),
        'skip_rate': float(m['skip_rate']),
        'abort_rate': float(m['abort_rate']),
        'total_return': float(m['total_return']),
        'busts_avoided': int(m['busts_avoided']),
        'busts_hit': int(m['busts_hit']),
        'win_rate': float(m['win_rate']),
        'pf': float(m['pf']),
        'max_dd': float(m['max_dd']),
        'sharpe': float(m['sharpe']),
        'n_traded': int(m['n_traded']),
        'n_skipped': int(m['n_skipped']),
        'n_aborted': int(m['n_aborted']),
    }

# Walk-forward per mode
for mode in MODES:
    yrs = wf_results.get(mode, [])
    if yrs:
        validation_results['walk_forward'][NICE_NAMES[mode]] = {
            'years': [y['year'] for y in yrs],
            'returns': [float(y['total_return']) for y in yrs],
            'bust_rates': [float(y['bust_rate']) for y in yrs],
            'profitable_years': int(sum(1 for y in yrs if y['total_return'] > 0)),
            'total_years': len(yrs),
        }

results_path = os.path.join(DATA_DIR, 'validation_results_v2.json')
with open(results_path, 'w') as f:
    json.dump(validation_results, f, indent=2)
print(f"  Saved: {results_path}")
print(f"  Saved: {plot_path}")

print("\n" + "=" * 80)
print("VALIDATION v2 COMPLETE")
print("=" * 80)
print(f"\n  Result: {recommendation}")
print(f"  Gates: {n_gates}/4 passed")
print(f"  Output: {results_path}")
print(f"  Plot:   {plot_path}")
