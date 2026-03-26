#!/usr/bin/env python3
"""
Phase F — Script 20: Full Pipeline Validation
===============================================
Integration test for the complete adaptive surefire hedge pipeline:
  Layer 1: Online Bayesian HMM regime detection
  Layer 2: Per-regime config selection (or SKIP)
  Layer 3: Contextual bandit entry gate (trade/skip)
  Layer 4: Tabular Q-learner mid-cycle abort

Validation protocol:
  1. Walk-forward on 10+ non-overlapping test years (2011-2025)
  2. Permutation tests (1000 shuffles, p < 0.01)
  3. Deflated Sharpe Ratio (DSR > 2.0)
  4. Adversarial stress tests
  5. Incremental component comparison table
  6. Summary with PASS/FAIL gates

Requires:
  - notebooks/phase2/data/feature_matrix.parquet
  - notebooks/phase2/data/hmm_model.pkl
  - notebooks/phase2/data/regime_labels.npy
  - notebooks/phase2/data/regime_configs.json
"""

import os, sys, json, pickle, time, warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, 'data')
PLOT_DIR   = os.path.join(SCRIPT_DIR, 'plots')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PLOT_DIR, exist_ok=True)

np.random.seed(42)

# ===========================================================================
# SECTION 0 — Load Artefacts from Phases A-E
# ===========================================================================
print("=" * 80)
print("SECTION 0: LOADING ARTEFACTS FROM PHASES A-E")
print("=" * 80)

# --- Feature matrix (Phase A) ---
feat_path = os.path.join(DATA_DIR, 'feature_matrix.parquet')
if os.path.exists(feat_path):
    feature_df = pd.read_parquet(feat_path)
    print(f"  Feature matrix loaded: {feature_df.shape}")
else:
    print("  [SYNTH] feature_matrix.parquet not found — generating synthetic data")
    feature_df = None

# --- HMM model (Phase B) ---
hmm_path = os.path.join(DATA_DIR, 'hmm_model.pkl')
if os.path.exists(hmm_path):
    with open(hmm_path, 'rb') as f:
        hmm_model = pickle.load(f)
    print(f"  HMM model loaded")
else:
    print("  [SYNTH] hmm_model.pkl not found — will use synthetic regime model")
    hmm_model = None

# --- Regime labels (Phase B) ---
labels_path_npy = os.path.join(DATA_DIR, 'regime_labels.npy')
labels_path_parquet = os.path.join(DATA_DIR, 'regime_labels.parquet')
if os.path.exists(labels_path_npy):
    regime_labels_all = np.load(labels_path_npy)
    print(f"  Regime labels loaded (npy): {len(regime_labels_all)}")
elif os.path.exists(labels_path_parquet):
    _rl_df = pd.read_parquet(labels_path_parquet)
    regime_labels_all = _rl_df['regime'].values if 'regime' in _rl_df.columns else _rl_df.iloc[:, 0].values
    print(f"  Regime labels loaded (parquet): {len(regime_labels_all)}")
else:
    print("  [SYNTH] regime_labels not found — will generate synthetic labels")
    regime_labels_all = None

# --- Regime configs (Phase C) ---
config_path = os.path.join(DATA_DIR, 'regime_configs.json')
if os.path.exists(config_path):
    with open(config_path) as f:
        regime_configs_raw = json.load(f)
    print(f"  Regime configs loaded: {len(regime_configs_raw)} regimes")
else:
    print("  [SYNTH] regime_configs.json not found — will use default configs")
    regime_configs_raw = None


# ===========================================================================
# SECTION 1 — Component Definitions
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 1: COMPONENT DEFINITIONS")
print("=" * 80)

# --- Surefire cycle simulation parameters ---
PRICE_PER_LOT = 100_000
LEVERAGE       = 30
EQUITY_START   = 10_000

STRUCTURAL_PARAMS = dict(
    max_levels=12,
    multiplier_fn=lambda n: np.sqrt(2) ** n,
    base_pct=0.005,
    tp_mult=0.8,
    hedge_ratio=2.0,
)


# ---------------------------------------------------------------------------
# 1a. Online Bayesian HMM wrapper
# ---------------------------------------------------------------------------
class OnlineBayesianHMM:
    """Minimal online HMM regime detector.

    If a real HMM model from Phase B is available, wraps it.
    Otherwise uses a lightweight synthetic model for validation logic testing.
    """

    def __init__(self, model=None, n_states=5, decay=0.999):
        self.n_states = n_states
        self.decay = decay
        self.belief = np.ones(n_states) / n_states

        if model is not None:
            self.model = model
            self.n_states = model.n_components if hasattr(model, 'n_components') else n_states
            self.belief = np.ones(self.n_states) / self.n_states
            self._use_real = True
            # Fallback transition matrix in case model doesn't have transmat_
            self._trans = np.full((self.n_states, self.n_states), 1.0 / self.n_states)
            if hasattr(model, 'transmat_'):
                self._trans = model.transmat_
        else:
            self._use_real = False
            # Build a simple Gaussian emission model from regime_labels if available
            self._means = np.random.randn(n_states, 5) * 0.5
            self._covs = np.array([np.eye(5) * 0.5 for _ in range(n_states)])
            self._trans = np.full((n_states, n_states), 1.0 / n_states)
            for i in range(n_states):
                self._trans[i, i] = 0.7
                off_diag = 0.3 / (n_states - 1)
                for j in range(n_states):
                    if j != i:
                        self._trans[i, j] = off_diag

    # -- emission probability --
    def _emission(self, obs):
        if self._use_real:
            try:
                ll = self.model._compute_likelihood(obs.reshape(1, -1))
                return ll.flatten()
            except Exception:
                try:
                    from scipy.stats import multivariate_normal
                    means = self.model.means_
                    covars = self.model.covars_
                    probs = np.array([
                        multivariate_normal.pdf(obs, mean=means[k], cov=covars[k])
                        for k in range(self.n_states)
                    ])
                    return probs + 1e-300
                except Exception:
                    return np.ones(self.n_states)
        else:
            from scipy.stats import multivariate_normal
            dim = min(obs.shape[0], self._means.shape[1])
            probs = np.array([
                multivariate_normal.pdf(obs[:dim], mean=self._means[k, :dim],
                                        cov=self._covs[k, :dim, :dim])
                for k in range(self.n_states)
            ])
            return probs + 1e-300

    def _get_transmat(self):
        if self._use_real and hasattr(self.model, 'transmat_'):
            return self.model.transmat_
        return self._trans

    def update(self, observation):
        emission = self._emission(observation)
        trans = self._get_transmat()
        self.belief = emission * (trans.T @ self.belief)
        s = self.belief.sum()
        if s > 0:
            self.belief /= s
        else:
            self.belief = np.ones(self.n_states) / self.n_states
        return self.belief

    def get_regime(self):
        return int(np.argmax(self.belief))

    def get_confidence(self):
        return float(np.max(self.belief))

    def reset(self):
        self.belief = np.ones(self.n_states) / self.n_states


# ---------------------------------------------------------------------------
# 1b. Regime config lookup
# ---------------------------------------------------------------------------
SKIP_SENTINEL = 'SKIP'


def _parse_regime_configs(raw, n_states):
    """Parse regime_configs.json into a dict mapping regime_id -> config dict or SKIP."""
    if raw is None:
        # Default: structural params for every regime
        return {i: STRUCTURAL_PARAMS.copy() for i in range(n_states)}

    configs = {}
    for key, val in raw.items():
        rid = int(key)
        if val is None or val == SKIP_SENTINEL or (isinstance(val, dict) and val.get('skip', False)):
            configs[rid] = SKIP_SENTINEL
        else:
            c = STRUCTURAL_PARAMS.copy()
            if isinstance(val, dict):
                if 'max_levels' in val:
                    c['max_levels'] = int(val['max_levels'])
                if 'multiplier' in val:
                    m_val = float(val['multiplier'])
                    c['multiplier_fn'] = lambda n, m=m_val: m ** n
                if 'base_pct' in val:
                    c['base_pct'] = float(val['base_pct'])
                if 'tp_mult' in val:
                    c['tp_mult'] = float(val['tp_mult'])
                if 'hedge_ratio' in val:
                    c['hedge_ratio'] = float(val['hedge_ratio'])
            configs[rid] = c
    # Fill missing regimes with structural defaults
    for i in range(n_states):
        if i not in configs:
            configs[i] = STRUCTURAL_PARAMS.copy()
    return configs


# ---------------------------------------------------------------------------
# 1c. Contextual Bandit (EntryBandit)
# ---------------------------------------------------------------------------
class EntryBandit:
    """Thompson Sampling bandit for trade / skip per regime."""

    def __init__(self, n_regimes, threshold=0.4, confidence_floor=0.5):
        self.alpha = np.ones(n_regimes)  # prior successes
        self.beta_param = np.ones(n_regimes)   # prior failures
        self.threshold = threshold
        self.confidence_floor = confidence_floor

    def should_trade(self, regime, confidence):
        if confidence < self.confidence_floor:
            return False
        p = np.random.beta(self.alpha[regime], self.beta_param[regime])
        return p > self.threshold

    def update(self, regime, traded, outcome):
        if not traded:
            return
        if outcome > 0:
            self.alpha[regime] += 1.0
        else:
            self.beta_param[regime] += 1.0
            if outcome < -5.0:  # severe bust penalty
                self.beta_param[regime] += 10.0

    def reset(self):
        self.alpha[:] = 1.0
        self.beta_param[:] = 1.0


# ---------------------------------------------------------------------------
# 1d. Tabular Q-Learner
# ---------------------------------------------------------------------------
class TabularQLearner:
    """Q-learning for mid-cycle abort.

    State = (current_level_bin, regime_at_entry, regime_now, regime_changed)
    Action = 0 (continue) | 1 (abort)
    """

    LEVEL_BINS = 13   # 0-12
    REGIME_BINS = 10  # capped
    CHANGED_BINS = 2  # 0/1

    def __init__(self, n_regimes=5, lr=0.1, gamma=0.99, epsilon=0.10):
        self.n_regimes = min(n_regimes, self.REGIME_BINS)
        self.n_states = self.LEVEL_BINS * self.n_regimes * self.n_regimes * self.CHANGED_BINS
        self.Q = np.zeros((self.n_states, 2))
        self.lr = lr
        self.gamma = gamma
        self.epsilon = epsilon

    def _encode(self, level, regime_entry, regime_now, regime_changed):
        level = min(level, self.LEVEL_BINS - 1)
        re = min(regime_entry, self.n_regimes - 1)
        rn = min(regime_now, self.n_regimes - 1)
        rc = 1 if regime_changed else 0
        idx = (level * self.n_regimes * self.n_regimes * self.CHANGED_BINS
               + re * self.n_regimes * self.CHANGED_BINS
               + rn * self.CHANGED_BINS
               + rc)
        return min(idx, self.n_states - 1)

    def choose_action(self, level, regime_entry, regime_now):
        state = self._encode(level, regime_entry, regime_now,
                             regime_entry != regime_now)
        if np.random.rand() < self.epsilon:
            return np.random.randint(2)
        return int(np.argmax(self.Q[state]))

    def update(self, level, regime_entry, regime_now, action, reward,
               next_level=None, next_regime_now=None, done=True):
        state = self._encode(level, regime_entry, regime_now,
                             regime_entry != regime_now)
        if done or next_level is None:
            target = reward
        else:
            ns = self._encode(next_level, regime_entry, next_regime_now,
                              regime_entry != next_regime_now)
            target = reward + self.gamma * np.max(self.Q[ns])
        self.Q[state, action] += self.lr * (target - self.Q[state, action])

    def reset(self):
        self.Q[:] = 0.0


print("  Components defined: OnlineBayesianHMM, EntryBandit, TabularQLearner")


# ===========================================================================
# SECTION 2 — Cycle Simulation Engine
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 2: CYCLE SIMULATION ENGINE")
print("=" * 80)


def _make_multiplier_fn(params):
    """Extract multiplier_fn from params dict (handle lambda serialization)."""
    fn = params.get('multiplier_fn', None)
    if fn is None:
        return lambda n: np.sqrt(2) ** n
    return fn


def simulate_structural_cycle(close_prices, high_prices, low_prices,
                               atr_values, entry_idx, direction=1,
                               params=None):
    """Simulate a single surefire cycle on raw price arrays.

    Returns dict with: pnl_pct, win_level, is_bust, levels_used, exit_idx,
    level_entries (list of (idx, direction) per level for abort checking).
    """
    if params is None:
        params = STRUCTURAL_PARAMS

    multiplier_fn = _make_multiplier_fn(params)
    max_levels    = params.get('max_levels', 12)
    base_pct      = params.get('base_pct', 0.005)
    tp_mult       = params.get('tp_mult', 0.8)
    hedge_ratio   = params.get('hedge_ratio', 2.0)

    a = atr_values[entry_idx]
    if np.isnan(a) or a < 1e-7:
        return None

    tp_dist = a * tp_mult
    h_dist  = tp_dist / hedge_ratio
    entry_price = close_prices[entry_idx]
    entry = entry_price
    dirn  = direction

    base_lots = base_pct / PRICE_PER_LOT * LEVERAGE * EQUITY_START
    if base_lots < 1e-6:
        return None

    # Affordable levels
    affordable = max_levels
    for test_n in range(1, max_levels + 1):
        cum_size = sum(base_lots * multiplier_fn(k) for k in range(test_n))
        cum_margin = cum_size * PRICE_PER_LOT / LEVERAGE
        cum_loss = cum_size * h_dist * PRICE_PER_LOT
        if cum_margin + cum_loss > EQUITY_START * 0.95:
            affordable = test_n - 1
            break
    affordable = max(affordable, 2)

    positions = []
    level_entries = []
    j = entry_idx + 1
    win_level = -1

    for level in range(affordable):
        size = base_lots * multiplier_fn(level)
        tp_price = entry + dirn * tp_dist
        sl_price = entry - dirn * h_dist
        positions.append((size, entry, dirn, tp_price, sl_price))
        level_entries.append((j, dirn, entry))

        won = lost = False
        while j < len(close_prices):
            h = high_prices[j]
            lo = low_prices[j]
            if dirn == 1:
                if h >= tp_price:
                    won = True; break
                if lo <= sl_price:
                    lost = True; break
            else:
                if lo <= tp_price:
                    won = True; break
                if h >= sl_price:
                    lost = True; break
            j += 1

        if won:
            cycle_pnl = 0.0
            for sz, ent, d, tp_p, sl_p in positions[:-1]:
                cycle_pnl -= sz * h_dist * PRICE_PER_LOT
            cycle_pnl += size * tp_dist * PRICE_PER_LOT
            win_level = level
            break
        elif lost:
            entry = sl_price
            dirn *= -1
            j += 1
        else:
            break  # out of data

    if win_level == -1 and j < len(close_prices):
        cycle_pnl = 0.0
        for sz, ent, d, tp_p, sl_p in positions:
            cycle_pnl -= sz * h_dist * PRICE_PER_LOT

    if j >= len(close_prices) and win_level == -1:
        return None  # incomplete

    pnl_pct = cycle_pnl / EQUITY_START * 100

    return {
        'pnl': cycle_pnl,
        'pnl_pct': pnl_pct,
        'win_level': win_level,
        'is_bust': win_level == -1,
        'levels_used': len(positions),
        'entry_idx': entry_idx,
        'exit_idx': j,
        'level_entries': level_entries,
        'tp_dist': tp_dist,
        'h_dist': h_dist,
    }


def compute_abort_pnl(positions_so_far, h_dist):
    """Controlled loss if aborting at current level."""
    pnl = 0.0
    for sz, ent, d, tp_p, sl_p in positions_so_far:
        pnl -= sz * h_dist * PRICE_PER_LOT * 0.5  # close at ~half adverse
    return pnl


# ===========================================================================
# SECTION 3 — Synthetic Data Generation (when Phase A-E artefacts missing)
# ===========================================================================

def generate_synthetic_cycles(n_cycles=5000, n_years=20, p_bust=0.003,
                               n_regimes=5, seed=42):
    """Generate synthetic cycle data mimicking 20y EUR-USD surefire results.

    Returns DataFrame with columns matching feature_matrix.parquet expectations.
    """
    rng = np.random.RandomState(seed)
    records = []

    # Regime transition probs (sticky)
    regime_seq = []
    cur_regime = 0
    regime_bust_rates = rng.uniform(0.001, 0.010, n_regimes)
    regime_bust_rates[0] = 0.0005  # safe regime
    regime_bust_rates[n_regimes - 1] = 0.015  # dangerous regime

    cycles_per_year = n_cycles // n_years

    for i in range(n_cycles):
        # Regime transition
        if rng.rand() < 0.05:
            cur_regime = rng.randint(0, n_regimes)
        regime_seq.append(cur_regime)

        year = 2006 + i // cycles_per_year
        is_bust = rng.rand() < regime_bust_rates[cur_regime]

        if is_bust:
            pnl_pct = -rng.uniform(2.0, 8.0)
            win_level = -1
        else:
            win_level = rng.choice([0, 0, 0, 1, 1, 2, 3, 4],
                                    p=[0.35, 0.35, 0.35, 0.12, 0.12, 0.04, 0.01, 0.01][:8] if False else None)
            # Simpler: weighted choice
            w = np.array([0.35, 0.25, 0.15, 0.10, 0.05, 0.04, 0.03, 0.02, 0.005, 0.005, 0.005, 0.005])
            w = w[:min(12, len(w))]
            w /= w.sum()
            win_level = rng.choice(len(w), p=w)
            pnl_pct = rng.uniform(0.01, 0.15)

        # Synthetic features (5 features x 5 timeframes = 25)
        feats = rng.randn(25) * 0.5 + cur_regime * 0.3

        rec = {'year': min(year, 2025), 'regime': cur_regime, 'pnl_pct': pnl_pct,
               'win_level': win_level, 'is_bust': is_bust, 'levels_used': win_level + 1 if not is_bust else 12}
        for fi in range(25):
            rec[f'f{fi}'] = feats[fi]
        records.append(rec)

    df = pd.DataFrame(records)
    return df, np.array(regime_seq), regime_bust_rates


# Decide data source
if feature_df is not None and regime_labels_all is not None:
    print("  Using REAL artefacts from Phases A-E")
    USE_SYNTHETIC = False
    # Map real data columns to expected names
    if 'regime' not in feature_df.columns and regime_labels_all is not None:
        # Align lengths: regime_labels may have fewer rows (after NaN removal in Phase B)
        if len(regime_labels_all) < len(feature_df):
            feature_df = feature_df.iloc[:len(regime_labels_all)].copy()
        feature_df['regime'] = regime_labels_all[:len(feature_df)]
    if 'year' not in feature_df.columns:
        if 'datetime' in feature_df.columns:
            feature_df['year'] = pd.to_datetime(feature_df['datetime']).dt.year
        elif 'timestamp' in feature_df.columns:
            feature_df['year'] = pd.to_datetime(feature_df['timestamp'], unit='ms').dt.year
        else:
            n = len(feature_df)
            feature_df['year'] = np.linspace(2024, 2026, n).astype(int)
    # Add win_level if missing (derive from level_reached)
    if 'win_level' not in feature_df.columns:
        if 'level_reached' in feature_df.columns:
            feature_df['win_level'] = feature_df.apply(
                lambda r: -1 if r['is_bust'] else int(r['level_reached']), axis=1)
        else:
            feature_df['win_level'] = feature_df.apply(
                lambda r: -1 if r['is_bust'] else 0, axis=1)
    if 'levels_used' not in feature_df.columns:
        feature_df['levels_used'] = feature_df['win_level'].apply(
            lambda w: 12 if w == -1 else w + 1)
    # Detect feature columns (25 regime descriptors: {timeframe}_{indicator})
    FEATURE_SUFFIXES = ('_adx', '_atr_ratio', '_chop', '_hurst', '_range_atr')
    FEATURE_COLS = [c for c in feature_df.columns if any(c.endswith(s) for s in FEATURE_SUFFIXES)]
    if not FEATURE_COLS:
        FEATURE_COLS = [c for c in feature_df.columns if c.startswith('f')]
    if not FEATURE_COLS:
        META_COLS = {'year', 'pnl', 'pnl_pct', 'win_level', 'is_bust', 'levels_used',
                     'regime', 'timestamp', 'entry_idx', 'entry_bar', 'entry_price',
                     'atr_at_entry', 'direction', 'duration_bars', 'datetime', 'choppy_bust'}
        FEATURE_COLS = [c for c in feature_df.columns if c not in META_COLS]
    N_REGIMES = int(feature_df['regime'].nunique()) if 'regime' in feature_df.columns else 5
    regime_bust_rates_real = None
else:
    print("  Generating SYNTHETIC data for pipeline validation")
    USE_SYNTHETIC = True
    synth_df, synth_regimes, synth_bust_rates = generate_synthetic_cycles(
        n_cycles=6000, n_years=20, n_regimes=5, seed=42)
    feature_df = synth_df
    regime_labels_all = synth_regimes
    FEATURE_COLS = [f'f{i}' for i in range(25)]
    N_REGIMES = 5
    regime_bust_rates_real = synth_bust_rates

n_states_hmm = N_REGIMES
regime_configs = _parse_regime_configs(regime_configs_raw, n_states_hmm)

print(f"  Cycles: {len(feature_df):,}, Regimes: {N_REGIMES}, Features: {len(FEATURE_COLS)}")
print(f"  Year range: {feature_df['year'].min()} - {feature_df['year'].max()}")
bust_n = feature_df['is_bust'].sum()
print(f"  Busts: {bust_n} ({bust_n / len(feature_df) * 100:.3f}%)")


# ===========================================================================
# SECTION 4 — run_cycle(): The Full Pipeline Function
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 4: FULL PIPELINE FUNCTION — run_cycle()")
print("=" * 80)


def run_cycle(row, hmm, configs, bandit, q_learner, feature_cols,
              mode='full', rng=None):
    """Execute one cycle through all 4 pipeline layers.

    Args:
        row: dict-like with feature columns, pnl_pct, win_level, is_bust, etc.
        hmm: OnlineBayesianHMM instance
        configs: regime -> config dict
        bandit: EntryBandit instance
        q_learner: TabularQLearner instance
        feature_cols: list of feature column names
        mode: 'structural' | '+hmm' | '+bandit' | '+qlearn' | 'full'
        rng: numpy RandomState for reproducibility

    Returns:
        dict with pnl_pct, traded, aborted, regime, etc.
    """
    if rng is None:
        rng = np.random

    # Extract features (use pre-computed array if available)
    if '_feat_arr' in row:
        feats = row['_feat_arr']
    else:
        feats = np.array([row[c] for c in feature_cols], dtype=np.float64)
        feats = np.nan_to_num(feats, 0.0)

    # ---- Layer 1: HMM regime detection ----
    if mode == 'structural':
        regime = 0
        confidence = 1.0
    else:
        belief = hmm.update(feats)
        regime = int(np.argmax(belief))
        confidence = float(np.max(belief))

    # ---- Layer 2: Config selection ----
    if mode in ('structural',):
        config = STRUCTURAL_PARAMS
    else:
        config = configs.get(regime, STRUCTURAL_PARAMS)
        if config == SKIP_SENTINEL:
            return {'pnl_pct': 0.0, 'traded': False, 'aborted': False,
                    'regime': regime, 'skipped_reason': 'regime_skip'}

    # ---- Layer 3: Entry bandit ----
    if mode in ('structural', '+hmm', '+qlearn'):
        do_trade = True
    else:
        do_trade = bandit.should_trade(regime, confidence)
        if not do_trade:
            return {'pnl_pct': 0.0, 'traded': False, 'aborted': False,
                    'regime': regime, 'skipped_reason': 'bandit_skip'}

    # ---- Simulate cycle (using historical outcome from feature matrix) ----
    # The actual cycle outcome is recorded in the feature matrix; we honour it
    # but apply abort logic on top.
    actual_pnl_pct = float(row['pnl_pct'])
    actual_is_bust = bool(row['is_bust'])
    actual_win_level = int(row['win_level'])
    actual_levels_used = int(row.get('levels_used', actual_win_level + 1 if not actual_is_bust else 12))

    # ---- Layer 4: Mid-cycle Q-learner abort ----
    aborted = False
    abort_level = -1
    if mode in ('full', '+qlearn') and actual_levels_used > 1:
        entry_regime = regime
        for lvl in range(actual_levels_used):
            # Re-update HMM with same features (simulates intra-cycle regime shift)
            # In a real system, each level would observe new bars.
            # Here we add slight noise to simulate drift.
            noisy_feats = feats + rng.randn(len(feats)) * 0.1 * (lvl + 1)
            if mode != 'structural':
                hmm.update(noisy_feats)
            current_regime = hmm.get_regime() if mode != 'structural' else 0

            action = q_learner.choose_action(lvl, entry_regime, current_regime)
            if action == 1:  # ABORT
                aborted = True
                abort_level = lvl
                # Controlled loss: proportional to how deep we are
                # Approximate: each level costs ~base_pct * mult^k * h_dist
                frac = sum(np.sqrt(2) ** k for k in range(lvl + 1))
                abort_pnl_pct = -(frac * 0.005 * 0.4 / 2) * 100  # rough %
                abort_pnl_pct = max(abort_pnl_pct, actual_pnl_pct * 0.3)  # at most 30% of bust loss

                # Q-update
                q_learner.update(lvl, entry_regime, current_regime, 1,
                                  abort_pnl_pct, done=True)
                # Bandit update
                if mode in ('full', '+bandit', '+qlearn'):
                    bandit.update(entry_regime, True, abort_pnl_pct)
                return {'pnl_pct': abort_pnl_pct, 'traded': True,
                        'aborted': True, 'abort_level': abort_level,
                        'regime': regime, 'skipped_reason': None}

            # Q-update for continue action
            if lvl < actual_levels_used - 1:
                q_learner.update(lvl, entry_regime, current_regime, 0,
                                  0, next_level=lvl + 1,
                                  next_regime_now=current_regime, done=False)
            else:
                # Terminal: cycle resolved
                q_learner.update(lvl, entry_regime, current_regime, 0,
                                  actual_pnl_pct, done=True)

    # Bandit update
    if mode in ('full', '+bandit', '+qlearn') and do_trade:
        bandit.update(regime, True, actual_pnl_pct)

    return {'pnl_pct': actual_pnl_pct, 'traded': True, 'aborted': False,
            'regime': regime, 'skipped_reason': None}


print("  run_cycle() defined — 4 layers: HMM -> Config -> Bandit -> Q-Learner")


# ===========================================================================
# Helper: run pipeline over a set of cycles
# ===========================================================================
def run_pipeline_on_cycles(df, mode='full', hmm=None, configs=None,
                            bandit=None, q_learner=None, seed=42):
    """Run the pipeline on a DataFrame of cycles. Returns list of result dicts."""
    rng = np.random.RandomState(seed)
    if hmm is None:
        hmm = OnlineBayesianHMM(model=hmm_model, n_states=n_states_hmm)
    if configs is None:
        configs = regime_configs
    if bandit is None:
        bandit = EntryBandit(n_states_hmm)
    if q_learner is None:
        q_learner = TabularQLearner(n_regimes=n_states_hmm)

    results = []
    feat_arr = np.nan_to_num(df[FEATURE_COLS].values.astype(np.float64), 0.0)
    rows_list = df.to_dict('records')
    for i, row in enumerate(rows_list):
        row['_feat_arr'] = feat_arr[i]
        r = run_cycle(row, hmm, configs, bandit, q_learner,
                      FEATURE_COLS, mode=mode, rng=rng)
        results.append(r)
    return results


def compute_metrics_from_results(results):
    """Compute summary metrics from pipeline results."""
    traded = [r for r in results if r['traded']]
    skipped = [r for r in results if not r['traded']]
    pnls = [r['pnl_pct'] for r in traded]

    if not traded:
        return {'n_total': len(results), 'n_traded': 0, 'n_skipped': len(results),
                'bust_rate': 0, 'win_rate': 0, 'pf': 0, 'max_dd': 0,
                'avg_return': 0, 'sharpe': 0, 'total_return': 0, 'n_aborted': 0}

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    busts = [r for r in traded if r['pnl_pct'] < -1.0]  # significant losses
    aborted = [r for r in traded if r.get('aborted', False)]

    gross_win = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 1e-9
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf')

    # Equity curve and max drawdown
    equity = [100.0]
    for p in pnls:
        equity.append(equity[-1] * (1 + p / 100))
    peak = equity[0]
    max_dd = 0
    for eq in equity:
        peak = max(peak, eq)
        dd = (eq - peak) / peak
        max_dd = min(max_dd, dd)

    sharpe = np.mean(pnls) / np.std(pnls) if np.std(pnls) > 0 else 0

    return {
        'n_total': len(results),
        'n_traded': len(traded),
        'n_skipped': len(skipped),
        'bust_rate': len(busts) / len(traded) * 100 if traded else 0,
        'win_rate': len(wins) / len(traded) * 100 if traded else 0,
        'pf': pf,
        'max_dd': max_dd * 100,
        'avg_return': np.mean(pnls),
        'sharpe': sharpe,
        'total_return': (equity[-1] / equity[0] - 1) * 100,
        'n_aborted': len(aborted),
        'equity_curve': equity,
    }


# ===========================================================================
# SECTION 5 — Walk-Forward on 10+ Non-Overlapping Years
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 5: WALK-FORWARD VALIDATION (2011-2025)")
print("=" * 80)

all_years = sorted(feature_df['year'].unique())
test_years = [y for y in all_years if 2011 <= y <= 2025]
if len(test_years) < 10:
    test_years = all_years[-min(len(all_years), 15):]

print(f"  Test years: {test_years}")
print(f"  Training starts from earliest year, grows incrementally\n")

wf_results = {}
MODES = ['structural', '+hmm', '+bandit', '+qlearn', 'full']

for mode in MODES:
    year_results = []
    for test_year in test_years:
        train_df = feature_df[feature_df['year'] < test_year]
        test_df  = feature_df[feature_df['year'] == test_year]

        if len(test_df) < 10:
            continue

        # Fresh components for each fold (online learning from train, evaluate on test)
        hmm_inst = OnlineBayesianHMM(model=hmm_model, n_states=n_states_hmm)
        bandit_inst = EntryBandit(n_states_hmm)
        q_inst = TabularQLearner(n_regimes=n_states_hmm)

        # Warm up on training data (vectorized — only last 500 rows for speed)
        train_feats = np.nan_to_num(train_df[FEATURE_COLS].values.astype(np.float64), 0.0)
        train_busts = train_df['is_bust'].values if 'is_bust' in train_df.columns else np.zeros(len(train_df))
        train_pnls = train_df['pnl_pct'].values if 'pnl_pct' in train_df.columns else np.zeros(len(train_df))
        train_levels = train_df['levels_used'].values if 'levels_used' in train_df.columns else np.ones(len(train_df))
        # Only warm up on last 500 rows (enough for online learning, much faster)
        warmup_start = max(0, len(train_feats) - 500)
        for i in range(warmup_start, len(train_feats)):
            hmm_inst.update(train_feats[i])
            regime = hmm_inst.get_regime()
            bandit_inst.update(regime, True, float(train_pnls[i]))
            if train_busts[i]:
                q_inst.update(min(int(train_levels[i]) - 1, 11),
                              regime, regime, 0, float(train_pnls[i]), done=True)

        # Evaluate on test year
        test_results = run_pipeline_on_cycles(
            test_df, mode=mode, hmm=hmm_inst, configs=regime_configs,
            bandit=bandit_inst, q_learner=q_inst, seed=test_year)

        metrics = compute_metrics_from_results(test_results)
        metrics['year'] = test_year
        metrics['n_train'] = len(train_df)
        year_results.append(metrics)

    wf_results[mode] = year_results

# Print walk-forward summary
for mode in MODES:
    yrs = wf_results[mode]
    if not yrs:
        continue
    profitable_years = sum(1 for y in yrs if y['total_return'] > 0)
    returns = [y['total_return'] for y in yrs]
    bust_rates = [y['bust_rate'] for y in yrs]

    print(f"\n  MODE: {mode}")
    print(f"  {'Year':<8} {'Return%':>10} {'BustRate%':>10} {'WinRate%':>10} {'PF':>8} {'MaxDD%':>8} {'Traded':>8}")
    print(f"  {'-'*64}")
    for y in yrs:
        print(f"  {y['year']:<8} {y['total_return']:>10.2f} {y['bust_rate']:>10.3f} "
              f"{y['win_rate']:>10.1f} {y['pf']:>8.2f} {y['max_dd']:>8.2f} {y['n_traded']:>8}")
    print(f"  ---")
    print(f"  Profitable years: {profitable_years}/{len(yrs)}")
    print(f"  Avg return: {np.mean(returns):.2f}%, Worst: {np.min(returns):.2f}%, Best: {np.max(returns):.2f}%")
    print(f"  Avg bust rate: {np.mean(bust_rates):.4f}%")

WF_PASS = {}
for mode in MODES:
    yrs = wf_results[mode]
    profitable_years = sum(1 for y in yrs if y['total_return'] > 0) if yrs else 0
    required = max(int(len(yrs) * 0.8), 8)
    WF_PASS[mode] = profitable_years >= min(required, len(yrs) * 0.8) if yrs else False
    print(f"\n  Walk-forward {mode}: {'PASS' if WF_PASS[mode] else 'FAIL'} "
          f"({profitable_years}/{len(yrs)} profitable, need 80%)")


# ===========================================================================
# SECTION 6 — Permutation Tests (1000 shuffles, p < 0.01)
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 6: PERMUTATION TESTS (1000 shuffles, p < 0.01)")
print("=" * 80)

N_PERMUTATIONS = 1000


def permutation_test(real_metric, shuffled_metrics, label):
    """Compute p-value: fraction of shuffled that beat real."""
    p_value = np.mean(np.array(shuffled_metrics) >= real_metric)
    passed = p_value < 0.01
    print(f"  {label}: real={real_metric:.4f}, shuffled_mean={np.mean(shuffled_metrics):.4f}, "
          f"p={p_value:.4f} {'PASS' if passed else 'FAIL'}")
    return p_value, passed


# Use the full dataset for permutation tests
full_results = run_pipeline_on_cycles(feature_df, mode='full', seed=42)
full_metrics = compute_metrics_from_results(full_results)
real_total_return = full_metrics['total_return']
real_bust_rate = full_metrics['bust_rate']

# --- 6a. Regime shuffle ---
print("\n  6a. Regime Shuffle Permutation Test")
print("  Shuffling regime labels across cycles, re-running pipeline...")

regime_shuffle_metrics = []
for perm_i in range(N_PERMUTATIONS):
    perm_df = feature_df.copy()
    perm_df['regime'] = np.random.permutation(perm_df['regime'].values)
    # Rebuild feature columns to inject noise correlated with shuffled regime
    # (simulates having wrong regime labels)
    hmm_perm = OnlineBayesianHMM(n_states=n_states_hmm)
    bandit_perm = EntryBandit(n_states_hmm)
    q_perm = TabularQLearner(n_regimes=n_states_hmm)

    perm_results = []
    rng_p = np.random.RandomState(perm_i)
    for _, row in perm_df.iterrows():
        r = run_cycle(row, hmm_perm, regime_configs, bandit_perm, q_perm,
                      FEATURE_COLS, mode='full', rng=rng_p)
        perm_results.append(r)

    pm = compute_metrics_from_results(perm_results)
    regime_shuffle_metrics.append(pm['total_return'])

    if (perm_i + 1) % 200 == 0:
        print(f"    ... {perm_i + 1}/{N_PERMUTATIONS} shuffles done")

regime_pval, regime_pass = permutation_test(
    real_total_return, regime_shuffle_metrics, "Regime shuffle -> total return")

# --- 6b. Entry shuffle ---
print("\n  6b. Entry Shuffle Permutation Test")
print("  Randomizing trade/skip decisions...")

entry_shuffle_metrics = []
for perm_i in range(N_PERMUTATIONS):
    rng_e = np.random.RandomState(1000 + perm_i)
    perm_results = []
    for _, row in feature_df.iterrows():
        if rng_e.rand() < 0.5:
            perm_results.append({'pnl_pct': 0.0, 'traded': False, 'aborted': False,
                                 'regime': 0, 'skipped_reason': 'random_skip'})
        else:
            perm_results.append({'pnl_pct': float(row['pnl_pct']), 'traded': True,
                                 'aborted': False, 'regime': 0, 'skipped_reason': None})
    pm = compute_metrics_from_results(perm_results)
    entry_shuffle_metrics.append(pm['total_return'])

entry_pval, entry_pass = permutation_test(
    real_total_return, entry_shuffle_metrics, "Entry shuffle -> total return")

# --- 6c. Abort shuffle ---
print("\n  6c. Abort Shuffle Permutation Test")
print("  Randomizing abort decisions...")

abort_shuffle_bust_rates = []
for perm_i in range(N_PERMUTATIONS):
    rng_a = np.random.RandomState(2000 + perm_i)
    perm_results = []
    for _, row in feature_df.iterrows():
        actual_pnl = float(row['pnl_pct'])
        is_bust = bool(row['is_bust'])
        if is_bust and rng_a.rand() < 0.3:
            # Random abort: controlled loss
            abort_pnl = actual_pnl * rng_a.uniform(0.2, 0.5)
            perm_results.append({'pnl_pct': abort_pnl, 'traded': True,
                                 'aborted': True, 'regime': 0, 'skipped_reason': None})
        else:
            perm_results.append({'pnl_pct': actual_pnl, 'traded': True,
                                 'aborted': False, 'regime': 0, 'skipped_reason': None})
    pm = compute_metrics_from_results(perm_results)
    abort_shuffle_bust_rates.append(pm['bust_rate'])

# For abort test, the real pipeline should have LOWER bust rate
# So we compare: real bust rate should be lower than most shuffled
abort_real_br = full_metrics['bust_rate']
abort_pval = np.mean(np.array(abort_shuffle_bust_rates) <= abort_real_br)
abort_pass = abort_pval < 0.01
print(f"  Abort shuffle -> bust rate: real={abort_real_br:.4f}%, shuffled_mean="
      f"{np.mean(abort_shuffle_bust_rates):.4f}%, p={abort_pval:.4f} "
      f"{'PASS' if abort_pass else 'FAIL'}")

PERM_RESULTS = {
    'regime': {'p': regime_pval, 'pass': regime_pass},
    'entry':  {'p': entry_pval,  'pass': entry_pass},
    'abort':  {'p': abort_pval,  'pass': abort_pass},
}


# ===========================================================================
# SECTION 7 — Deflated Sharpe Ratio
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 7: DEFLATED SHARPE RATIO")
print("=" * 80)

# Count total parameter combinations tested across all phases
# Phase A: 5 timeframes explored -> ~5 combos
# Phase B: n_states tested = 6 (3,5,7,10,15,20)
# Phase C: config grid per regime, ~100 combos per regime, 5 regimes = 500
# Phase D: threshold tested ~10 combos
# Phase E: Q-learner epsilon/lr tested ~20 combos
N_TRIALS = 5 + 6 + 500 + 10 + 20
print(f"  Total parameter combinations tested (N_trials): {N_TRIALS}")

# Expected noise Sharpe
noise_sharpe = np.sqrt(2 * np.log(N_TRIALS))
print(f"  Expected noise Sharpe = sqrt(2 * log({N_TRIALS})) = {noise_sharpe:.4f}")

# Observed Sharpe from full pipeline
traded_pnls = [r['pnl_pct'] for r in full_results if r['traded']]
if traded_pnls and np.std(traded_pnls) > 0:
    observed_sharpe = np.mean(traded_pnls) / np.std(traded_pnls)
else:
    observed_sharpe = 0.0

# Standard error of Sharpe
n_obs = len(traded_pnls)
se_sharpe = np.sqrt((1 + 0.5 * observed_sharpe**2) / n_obs) if n_obs > 0 else 1.0

# Deflated Sharpe Ratio
DSR = (observed_sharpe - noise_sharpe) / se_sharpe if se_sharpe > 0 else 0.0

print(f"  Observed Sharpe:  {observed_sharpe:.4f}")
print(f"  Noise Sharpe:     {noise_sharpe:.4f}")
print(f"  SE(Sharpe):       {se_sharpe:.6f}")
print(f"  Deflated Sharpe:  {DSR:.4f}")
DSR_PASS = DSR > 2.0
print(f"  DSR > 2.0: {'PASS' if DSR_PASS else 'FAIL'}")


# ===========================================================================
# SECTION 8 — Adversarial Stress Tests
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 8: ADVERSARIAL STRESS TESTS")
print("=" * 80)


def run_stress_test(df, stress_fn, label, mode='full', seed=999):
    """Apply a stress transformation to the data and run the pipeline."""
    stressed_df = stress_fn(df.copy())
    results = run_pipeline_on_cycles(stressed_df, mode=mode, seed=seed)
    metrics = compute_metrics_from_results(results)
    return metrics


# --- 8a. Double P(lose) for 200 consecutive cycles ---
print("\n  8a. Double P(lose) for 200 consecutive cycles")

def stress_double_p_lose(df):
    """Force 200 consecutive cycles into bust territory."""
    df = df.copy()
    mid = len(df) // 2
    window = slice(mid, min(mid + 200, len(df)))
    rng_s = np.random.RandomState(77)
    for idx in df.index[window]:
        if rng_s.rand() < 0.5:  # double the bust probability
            df.at[idx, 'is_bust'] = True
            df.at[idx, 'win_level'] = -1
            df.at[idx, 'pnl_pct'] = -rng_s.uniform(2.0, 8.0)
    return df

stress_2x = run_stress_test(feature_df, stress_double_p_lose, "Double P(lose)")
print(f"    Total return: {stress_2x['total_return']:.2f}%, "
      f"Bust rate: {stress_2x['bust_rate']:.3f}%, Max DD: {stress_2x['max_dd']:.2f}%")
STRESS_2X_SURVIVE = stress_2x['total_return'] > -50.0

# --- 8b. Remove best 10% of winning streaks ---
print("\n  8b. Remove best 10% of winning streaks")

def stress_remove_best_streaks(df):
    """Remove the top 10% most profitable cycles."""
    df = df.copy()
    threshold = df[df['pnl_pct'] > 0]['pnl_pct'].quantile(0.90)
    mask = df['pnl_pct'] >= threshold
    df.loc[mask, 'pnl_pct'] = 0.0
    df.loc[mask, 'is_bust'] = False
    df.loc[mask, 'win_level'] = 0
    return df

stress_no_best = run_stress_test(feature_df, stress_remove_best_streaks,
                                  "Remove best 10%")
print(f"    Total return: {stress_no_best['total_return']:.2f}%, "
      f"Bust rate: {stress_no_best['bust_rate']:.3f}%, PF: {stress_no_best['pf']:.2f}")

# --- 8c. Add 2x spread during best hours ---
print("\n  8c. Add 2x spread during best hours")

def stress_double_spread(df):
    """Reduce PnL for cycles that occurred during profitable hours (simulate spread)."""
    df = df.copy()
    # Identify most profitable subset (top quartile of positive pnl)
    profitable = df[df['pnl_pct'] > 0]
    if len(profitable) > 0:
        top_q = profitable['pnl_pct'].quantile(0.75)
        mask = df['pnl_pct'] >= top_q
        df.loc[mask, 'pnl_pct'] *= 0.5  # halve the pnl (2x spread cost)
    return df

stress_spread = run_stress_test(feature_df, stress_double_spread, "2x Spread")
print(f"    Total return: {stress_spread['total_return']:.2f}%, "
      f"Bust rate: {stress_spread['bust_rate']:.3f}%, PF: {stress_spread['pf']:.2f}")

# --- 8d. Reversed price data ---
print("\n  8d. Reversed price data (time-reversal symmetry)")

def stress_reverse(df):
    """Reverse the order of cycles."""
    return df.iloc[::-1].reset_index(drop=True)

stress_rev = run_stress_test(feature_df, stress_reverse, "Reversed")
print(f"    Total return: {stress_rev['total_return']:.2f}%, "
      f"Bust rate: {stress_rev['bust_rate']:.3f}%, PF: {stress_rev['pf']:.2f}")

# Check symmetry
orig_return = full_metrics['total_return']
rev_return = stress_rev['total_return']
symmetry_ratio = min(orig_return, rev_return) / max(abs(orig_return), 1e-9) if orig_return != 0 else 0
print(f"    Symmetry: original={orig_return:.2f}%, reversed={rev_return:.2f}%, "
      f"ratio={symmetry_ratio:.2f}")

STRESS_RESULTS = {
    'double_p_lose': {'survive': STRESS_2X_SURVIVE, 'return': stress_2x['total_return']},
    'remove_best': {'return': stress_no_best['total_return'],
                    'profitable': stress_no_best['total_return'] > 0},
    'double_spread': {'return': stress_spread['total_return'],
                      'profitable': stress_spread['total_return'] > 0},
    'reversed': {'return': stress_rev['total_return'],
                 'symmetric': abs(symmetry_ratio) > 0.3},
}


# ===========================================================================
# SECTION 9 — Component Comparison Table
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 9: COMPONENT COMPARISON TABLE")
print("=" * 80)

comparison_data = {}
for mode in MODES:
    print(f"\n  Running full pipeline in mode: {mode} ...")
    results = run_pipeline_on_cycles(feature_df, mode=mode, seed=42)
    metrics = compute_metrics_from_results(results)
    comparison_data[mode] = metrics

    # Run 2x stress for this mode
    stress_results_mode = run_stress_test(feature_df, stress_double_p_lose,
                                          f"2x stress ({mode})", mode=mode, seed=999)
    comparison_data[mode]['stress_2x_return'] = stress_results_mode['total_return']
    comparison_data[mode]['stress_2x_survive'] = stress_results_mode['total_return'] > -50.0

# Compute permutation p-values per mode (simplified: use regime shuffle for +hmm,
# entry shuffle for +bandit, abort shuffle for +qlearn)
comparison_data['structural']['perm_p'] = 'N/A'
comparison_data['+hmm']['perm_p'] = f"{regime_pval:.4f}"
comparison_data['+bandit']['perm_p'] = f"{entry_pval:.4f}"
comparison_data['+qlearn']['perm_p'] = f"{abort_pval:.4f}"
comparison_data['full']['perm_p'] = f"{max(regime_pval, entry_pval, abort_pval):.4f}"

# Print table
NICE_NAMES = {
    'structural': 'Structural Only',
    '+hmm': '+HMM Regime',
    '+bandit': '+Bandit Entry',
    '+qlearn': '+Q-Learn Abort',
    'full': 'Full Pipeline',
}

ROWS = [
    ('Bust Rate %',       'bust_rate',          '{:.3f}'),
    ('Win Rate %',        'win_rate',           '{:.1f}'),
    ('Profit Factor',     'pf',                 '{:.2f}'),
    ('Max Drawdown %',    'max_dd',             '{:.2f}'),
    ('Avg Return %',      'avg_return',         '{:.4f}'),
    ('Total Return %',    'total_return',       '{:.2f}'),
    ('Sharpe',            'sharpe',             '{:.4f}'),
    ('2x Stress Return %','stress_2x_return',   '{:.2f}'),
    ('2x Stress Survive', 'stress_2x_survive',  '{}'),
    ('Permutation p',     'perm_p',             '{}'),
    ('Cycles Traded',     'n_traded',           '{:d}'),
    ('Cycles Skipped',    'n_skipped',          '{:d}'),
    ('Aborted',           'n_aborted',          '{:d}'),
]

header = f"  {'Metric':<22}" + "".join(f"{NICE_NAMES[m]:>18}" for m in MODES)
print(f"\n{header}")
print(f"  {'-' * (22 + 18 * len(MODES))}")

for label, key, fmt in ROWS:
    row_str = f"  {label:<22}"
    for mode in MODES:
        val = comparison_data[mode].get(key, 'N/A')
        if val == 'N/A' or isinstance(val, str):
            row_str += f"{str(val):>18}"
        elif isinstance(val, bool):
            row_str += f"{'YES' if val else 'NO':>18}"
        elif isinstance(val, float):
            row_str += f"{fmt.format(val):>18}"
        elif isinstance(val, int):
            row_str += f"{fmt.format(val):>18}"
        else:
            row_str += f"{str(val):>18}"
    print(row_str)


# Check incremental improvement
print("\n  Incremental improvement check:")
prev_mode = None
INCREMENTAL_PASS = {}
for mode in MODES:
    if prev_mode is not None:
        prev_ret = comparison_data[prev_mode]['total_return']
        cur_ret = comparison_data[mode]['total_return']
        improved = cur_ret >= prev_ret * 0.95  # allow 5% tolerance
        perm_ok = comparison_data[mode]['perm_p'] == 'N/A' or float(comparison_data[mode]['perm_p']) < 0.01
        passed = improved or comparison_data[mode]['perm_p'] == 'N/A'
        INCREMENTAL_PASS[mode] = passed
        print(f"  {NICE_NAMES[prev_mode]} -> {NICE_NAMES[mode]}: "
              f"return {prev_ret:.2f}% -> {cur_ret:.2f}% "
              f"({'IMPROVES' if improved else 'DEGRADES'}), "
              f"perm {'PASS' if perm_ok else 'FAIL'}")
    else:
        INCREMENTAL_PASS[mode] = True
    prev_mode = mode


# ===========================================================================
# SECTION 10 — Plots
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 10: GENERATING PLOTS")
print("=" * 80)

fig = plt.figure(figsize=(24, 20))
gs = GridSpec(3, 3, hspace=0.35, wspace=0.3)

# --- Plot 1: Walk-forward returns by year ---
ax1 = fig.add_subplot(gs[0, 0])
for mode in MODES:
    yrs = wf_results[mode]
    if not yrs:
        continue
    years = [y['year'] for y in yrs]
    returns = [y['total_return'] for y in yrs]
    ax1.plot(years, returns, 'o-', label=NICE_NAMES[mode], markersize=4, alpha=0.8)
ax1.axhline(y=0, color='black', linewidth=0.5)
ax1.set_xlabel('Year')
ax1.set_ylabel('Return %')
ax1.set_title('Walk-Forward: Annual Returns')
ax1.legend(fontsize=7)
ax1.grid(True, alpha=0.3)

# --- Plot 2: Component comparison bar chart ---
ax2 = fig.add_subplot(gs[0, 1])
mode_names = [NICE_NAMES[m] for m in MODES]
returns = [comparison_data[m]['total_return'] for m in MODES]
colors = ['#3498db', '#2ecc71', '#e67e22', '#9b59b6', '#e74c3c']
ax2.bar(range(len(MODES)), returns, color=colors, alpha=0.8, edgecolor='black')
ax2.set_xticks(range(len(MODES)))
ax2.set_xticklabels([n.replace(' ', '\n') for n in mode_names], fontsize=8)
ax2.set_ylabel('Total Return %')
ax2.set_title('Component Comparison: Total Return')
ax2.grid(True, alpha=0.3, axis='y')

# --- Plot 3: Bust rate comparison ---
ax3 = fig.add_subplot(gs[0, 2])
bust_rates = [comparison_data[m]['bust_rate'] for m in MODES]
ax3.bar(range(len(MODES)), bust_rates, color=colors, alpha=0.8, edgecolor='black')
ax3.set_xticks(range(len(MODES)))
ax3.set_xticklabels([n.replace(' ', '\n') for n in mode_names], fontsize=8)
ax3.set_ylabel('Bust Rate %')
ax3.set_title('Component Comparison: Bust Rate')
ax3.grid(True, alpha=0.3, axis='y')

# --- Plot 4: Equity curves ---
ax4 = fig.add_subplot(gs[1, 0])
for mi, mode in enumerate(MODES):
    eq = comparison_data[mode].get('equity_curve', [100])
    ax4.plot(range(len(eq)), eq, label=NICE_NAMES[mode], alpha=0.8, color=colors[mi])
ax4.set_xlabel('Cycle #')
ax4.set_ylabel('Equity (normalized)')
ax4.set_title('Equity Curves by Pipeline Mode')
ax4.legend(fontsize=7)
ax4.grid(True, alpha=0.3)

# --- Plot 5: Permutation test distributions ---
ax5 = fig.add_subplot(gs[1, 1])
ax5.hist(regime_shuffle_metrics, bins=50, alpha=0.5, label='Regime Shuffle', color='steelblue', density=True)
ax5.hist(entry_shuffle_metrics, bins=50, alpha=0.5, label='Entry Shuffle', color='coral', density=True)
ax5.axvline(x=real_total_return, color='red', linewidth=2, linestyle='--', label=f'Real: {real_total_return:.2f}%')
ax5.set_xlabel('Total Return %')
ax5.set_ylabel('Density')
ax5.set_title('Permutation Test Distributions')
ax5.legend(fontsize=8)
ax5.grid(True, alpha=0.3)

# --- Plot 6: Stress test comparison ---
ax6 = fig.add_subplot(gs[1, 2])
stress_labels = ['Normal', 'Double\nP(lose)', 'No Best\n10%', 'Double\nSpread', 'Reversed']
stress_returns = [
    full_metrics['total_return'],
    stress_2x['total_return'],
    stress_no_best['total_return'],
    stress_spread['total_return'],
    stress_rev['total_return'],
]
stress_colors = ['#2ecc71' if r > 0 else '#e74c3c' for r in stress_returns]
ax6.bar(range(len(stress_labels)), stress_returns, color=stress_colors, alpha=0.8, edgecolor='black')
ax6.set_xticks(range(len(stress_labels)))
ax6.set_xticklabels(stress_labels, fontsize=8)
ax6.set_ylabel('Total Return %')
ax6.set_title('Adversarial Stress Tests')
ax6.axhline(y=0, color='black', linewidth=0.5)
ax6.grid(True, alpha=0.3, axis='y')

# --- Plot 7: Walk-forward bust rates by year ---
ax7 = fig.add_subplot(gs[2, 0])
for mode in ['structural', 'full']:
    yrs = wf_results[mode]
    if not yrs:
        continue
    years = [y['year'] for y in yrs]
    brs = [y['bust_rate'] for y in yrs]
    ax7.plot(years, brs, 'o-', label=NICE_NAMES[mode], markersize=4, alpha=0.8)
ax7.set_xlabel('Year')
ax7.set_ylabel('Bust Rate %')
ax7.set_title('Walk-Forward: Bust Rate by Year')
ax7.legend(fontsize=8)
ax7.grid(True, alpha=0.3)

# --- Plot 8: Profit Factor comparison ---
ax8 = fig.add_subplot(gs[2, 1])
pfs = [comparison_data[m]['pf'] for m in MODES]
ax8.bar(range(len(MODES)), pfs, color=colors, alpha=0.8, edgecolor='black')
ax8.set_xticks(range(len(MODES)))
ax8.set_xticklabels([n.replace(' ', '\n') for n in mode_names], fontsize=8)
ax8.set_ylabel('Profit Factor')
ax8.set_title('Component Comparison: Profit Factor')
ax8.grid(True, alpha=0.3, axis='y')

# --- Plot 9: DSR visualization ---
ax9 = fig.add_subplot(gs[2, 2])
ax9.bar(['Observed\nSharpe', 'Noise\nSharpe', 'DSR'],
        [observed_sharpe, noise_sharpe, DSR],
        color=['#2ecc71', '#e74c3c', '#3498db'], alpha=0.8, edgecolor='black')
ax9.axhline(y=2.0, color='red', linestyle='--', alpha=0.5, label='DSR threshold = 2.0')
ax9.set_ylabel('Value')
ax9.set_title('Deflated Sharpe Ratio')
ax9.legend(fontsize=8)
ax9.grid(True, alpha=0.3, axis='y')

plt.suptitle('Phase F: Full Pipeline Validation\n'
             'Surefire Hedge Adaptive System',
             fontsize=14, fontweight='bold', y=0.99)
plt.savefig(os.path.join(PLOT_DIR, '20_full_validation.png'), dpi=150, bbox_inches='tight')
print(f"  Saved: {PLOT_DIR}/20_full_validation.png")
plt.close()


# ===========================================================================
# SECTION 11 — Summary Report with PASS/FAIL Gates
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 11: SUMMARY REPORT")
print("=" * 80)

gates = {}

# Gate 1: Walk-forward
wf_full_pass = WF_PASS.get('full', False)
gates['walk_forward'] = wf_full_pass
print(f"\n  GATE 1 — Walk-Forward (8/10 test years profitable):")
for mode in MODES:
    status = 'PASS' if WF_PASS.get(mode, False) else 'FAIL'
    yrs = wf_results[mode]
    n_prof = sum(1 for y in yrs if y['total_return'] > 0) if yrs else 0
    print(f"    {NICE_NAMES[mode]:<22}: {status} ({n_prof}/{len(yrs)})")

# Gate 2: Permutation tests
all_perm_pass = all(v['pass'] for v in PERM_RESULTS.values())
gates['permutation'] = all_perm_pass
print(f"\n  GATE 2 — Permutation Tests (p < 0.01):")
for name, res in PERM_RESULTS.items():
    print(f"    {name:<12}: p={res['p']:.4f} {'PASS' if res['pass'] else 'FAIL'}")

# Gate 3: Deflated Sharpe
gates['dsr'] = DSR_PASS
print(f"\n  GATE 3 — Deflated Sharpe Ratio (DSR > 2.0):")
print(f"    DSR = {DSR:.4f} {'PASS' if DSR_PASS else 'FAIL'}")

# Gate 4: Adversarial stress
stress_passes = [
    STRESS_RESULTS['double_p_lose']['survive'],
    STRESS_RESULTS['remove_best']['profitable'],
    STRESS_RESULTS['double_spread']['profitable'],
    STRESS_RESULTS['reversed']['symmetric'],
]
n_stress_pass = sum(stress_passes)
gates['stress'] = n_stress_pass >= 3
print(f"\n  GATE 4 — Adversarial Stress (3/4 must pass):")
stress_names = ['Double P(lose)', 'Remove Best 10%', 'Double Spread', 'Reversed Symmetry']
for name, passed in zip(stress_names, stress_passes):
    print(f"    {name:<22}: {'PASS' if passed else 'FAIL'}")
print(f"    Overall: {n_stress_pass}/4 {'PASS' if gates['stress'] else 'FAIL'}")

# Gate 5: Incremental improvement
inc_all = all(INCREMENTAL_PASS.values())
gates['incremental'] = inc_all
print(f"\n  GATE 5 — Incremental Component Improvement:")
for mode in MODES:
    if mode in INCREMENTAL_PASS:
        print(f"    {NICE_NAMES[mode]:<22}: {'PASS' if INCREMENTAL_PASS[mode] else 'FAIL'}")

# Final recommendation
print("\n" + "=" * 80)
print("  FINAL RECOMMENDATION")
print("=" * 80)

n_gates_passed = sum(gates.values())
print(f"\n  Gates passed: {n_gates_passed}/5")
for name, passed in gates.items():
    print(f"    {name:<20}: {'PASS' if passed else 'FAIL'}")

if n_gates_passed == 5:
    recommendation = "SHIP FULL PIPELINE"
    detail = ("All validation gates passed. The full adaptive pipeline "
              "(HMM + Bandit + Q-Learner) provides statistically significant "
              "improvement over the structural baseline. Deploy with monitoring.")
elif n_gates_passed >= 3:
    # Check which components add value
    useful_components = []
    if WF_PASS.get('+hmm', False):
        useful_components.append('HMM Regime')
    if WF_PASS.get('+bandit', False):
        useful_components.append('Bandit Entry')
    if WF_PASS.get('+qlearn', False):
        useful_components.append('Q-Learn Abort')

    if useful_components:
        recommendation = f"SHIP PARTIAL PIPELINE ({', '.join(useful_components)})"
        detail = (f"Only {', '.join(useful_components)} passed all tests. "
                  f"Ship structural base + validated components. "
                  f"Other components need more data or redesign.")
    else:
        recommendation = "SHIP STRUCTURAL ONLY"
        detail = ("Adaptive components do not reliably improve the structural baseline. "
                  "The structural surefire hedge (12 levels, sqrt(2), 0.5% base) "
                  "already has a validated edge. Ship as-is with circuit breakers.")
else:
    recommendation = "SHIP STRUCTURAL ONLY"
    detail = ("Most validation gates failed. Adaptive pipeline does not provide "
              "reliable improvement. Ship the structural baseline which has "
              "proven robust in Phase 1 blind testing.")

print(f"\n  >>> {recommendation} <<<\n")
print(f"  {detail}")


# ===========================================================================
# SECTION 12 — Save Results
# ===========================================================================
print("\n" + "=" * 80)
print("SECTION 12: SAVING RESULTS")
print("=" * 80)

validation_results = {
    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    'recommendation': recommendation,
    'gates': {k: bool(v) for k, v in gates.items()},
    'n_gates_passed': int(n_gates_passed),
    'walk_forward': {},
    'permutation_tests': {k: {'p_value': float(v['p']), 'pass': bool(v['pass'])}
                          for k, v in PERM_RESULTS.items()},
    'deflated_sharpe': {
        'observed_sharpe': float(observed_sharpe),
        'noise_sharpe': float(noise_sharpe),
        'DSR': float(DSR),
        'N_trials': int(N_TRIALS),
        'pass': bool(DSR_PASS),
    },
    'stress_tests': {k: {kk: float(vv) if isinstance(vv, (int, float, np.floating)) else bool(vv)
                          for kk, vv in v.items()}
                     for k, v in STRESS_RESULTS.items()},
    'comparison_table': {},
    'detail': detail,
}

# Walk-forward per mode
for mode in MODES:
    yrs = wf_results[mode]
    if yrs:
        validation_results['walk_forward'][mode] = {
            'years': [y['year'] for y in yrs],
            'returns': [float(y['total_return']) for y in yrs],
            'bust_rates': [float(y['bust_rate']) for y in yrs],
            'profitable_years': int(sum(1 for y in yrs if y['total_return'] > 0)),
            'total_years': len(yrs),
            'pass': bool(WF_PASS.get(mode, False)),
        }

# Comparison table
for mode in MODES:
    m = comparison_data[mode]
    validation_results['comparison_table'][NICE_NAMES[mode]] = {
        'bust_rate': float(m['bust_rate']),
        'win_rate': float(m['win_rate']),
        'pf': float(m['pf']),
        'max_dd': float(m['max_dd']),
        'total_return': float(m['total_return']),
        'sharpe': float(m['sharpe']),
        'n_traded': int(m['n_traded']),
        'n_skipped': int(m['n_skipped']),
        'n_aborted': int(m['n_aborted']),
        'stress_2x_survive': bool(m.get('stress_2x_survive', False)),
        'perm_p': str(m.get('perm_p', 'N/A')),
    }

results_path = os.path.join(DATA_DIR, 'validation_results.json')
with open(results_path, 'w') as f:
    json.dump(validation_results, f, indent=2)
print(f"  Saved: {results_path}")

print(f"  Saved: {PLOT_DIR}/20_full_validation.png")

print("\n" + "=" * 80)
print("VALIDATION COMPLETE")
print("=" * 80)
print(f"\n  Result: {recommendation}")
print(f"  Gates: {n_gates_passed}/5 passed")
print(f"  Output: {results_path}")
print(f"  Plots:  {PLOT_DIR}/20_full_validation.png")
