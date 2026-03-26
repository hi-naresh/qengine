#!/usr/bin/env python3
"""
Script 19b: Q-Learning Abort v2 -- Duration + Danger State Space
=================================================================
Replaces the HMM regime-based state from 19_abort_rl.py with a
duration-and-danger-score state space.

Key finding driving this change:
  Cycles lasting >20 bars (100 min) have 7.36% bust rate vs 0.08% for
  short cycles = 91x separation. Duration is the strongest mid-cycle signal.

State = (current_level, bars_in_cycle_bin, danger_at_entry, danger_now)
  - current_level:    0-12 (13 values)
  - bars_in_cycle:    binned [0-5, 5-10, 10-20, 20-50, 50+] (5 bins)
  - danger_at_entry:  0-4 (5 levels: safe/mild/caution/warning/danger)
  - danger_now:       0-4 (5 levels)
  Total: 13 x 5 x 5 x 5 = 1,625 states (smaller than v1's 2,600)

Action = {continue=0, abort=1}
Reward = realized P&L at cycle termination

Surefire parameters: 12 levels, sqrt(2) multiplier, 0.5% base.
"""

import os, sys, pickle, time
os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict

import qengine.indicators as ta
import qengine.helpers as jh
from qengine.research import get_candles

# ---- Paths -----------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, 'data')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---- Surefire Parameters ---------------------------------------------------
MAX_LEVELS = 12
MULTIPLIER = np.sqrt(2)
BASE_PCT = 0.005
TP_ATR_MULTIPLE = 0.8
RISK_REWARD = 2.0
ATR_PERIOD = 14
PIP_SIZE = 0.0001
BASE_SIZE = 0.1
PIP_VALUE = 10.0
MAX_BARS_PER_LEVEL = 500
EMA_FAST = 8
EMA_SLOW = 21
STARTING_BALANCE = 10_000

# ---- State Space Parameters ------------------------------------------------
N_LEVELS = 13              # 0..12
N_DURATION_BINS = 5        # [0-5, 5-10, 10-20, 20-50, 50+]
N_DANGER_LEVELS = 5        # 0=safe, 1=mild, 2=caution, 3=warning, 4=danger
N_STATES = N_LEVELS * N_DURATION_BINS * N_DANGER_LEVELS * N_DANGER_LEVELS  # 1625
N_ACTIONS = 2              # 0=continue, 1=abort

DURATION_BIN_EDGES = [0, 5, 10, 20, 50]  # bin boundaries (last bin is 50+)
DANGER_THRESHOLDS = [0.3, 0.5, 0.7, 0.85]  # boundaries for danger levels 0-4

# ---- Q-Learning Parameters -------------------------------------------------
ALPHA_LR = 0.1
GAMMA = 0.95
EPSILON_START = 0.15
EPSILON_MIN = 0.02
EPSILON_DECAY = 0.998

ACTION_CONTINUE = 0
ACTION_ABORT = 1

# ---- DangerScorer Weights ---------------------------------------------------
# Component weights (must sum to 1.0)
DANGER_WEIGHTS = {
    'D1_range_atr':  0.30,   # inverse: low range/ATR = choppy = dangerous
    '5m_chop':       0.15,   # high choppiness = dangerous
    '15m_chop':      0.15,   # high choppiness = dangerous
    'D1_chop':       0.10,   # high choppiness = dangerous
    '5m_adx':        0.10,   # inverse: low ADX = no trend = dangerous
    '5m_hurst':      0.10,   # inverse distance from 0.5: near 0.5 = random = dangerous
    '1H_atr_ratio':  0.10,   # high ATR ratio = expanding vol = dangerous
}


# =============================================================================
# Part 1: Duration Binning
# =============================================================================

def bars_to_duration_bin(bars_elapsed):
    """
    Bin bars elapsed into 5 categories:
    0: [0, 5)   -- very short, normal
    1: [5, 10)  -- short
    2: [10, 20) -- medium
    3: [20, 50) -- long (91x bust rate!)
    4: [50+)    -- very long
    """
    if bars_elapsed < 5:
        return 0
    elif bars_elapsed < 10:
        return 1
    elif bars_elapsed < 20:
        return 2
    elif bars_elapsed < 50:
        return 3
    else:
        return 4


def danger_score_to_level(score):
    """
    Map continuous danger score [0, 1] to discrete level 0-4.
    0: < 0.30  (safe)
    1: 0.30-0.50 (mild)
    2: 0.50-0.70 (caution)
    3: 0.70-0.85 (warning)
    4: > 0.85  (danger)
    """
    if np.isnan(score):
        return 2  # default to caution if unknown
    if score < 0.3:
        return 0
    elif score < 0.5:
        return 1
    elif score < 0.7:
        return 2
    elif score < 0.85:
        return 3
    else:
        return 4


# =============================================================================
# Part 2: State Encoding / Decoding
# =============================================================================

def encode_state(level, duration_bin, danger_entry, danger_now):
    """
    Encode (level, duration_bin, danger_entry, danger_now) -> flat index.
    level:        0..12 (13 values)
    duration_bin: 0..4  (5 values)
    danger_entry: 0..4  (5 values)
    danger_now:   0..4  (5 values)
    Total: 13 * 5 * 5 * 5 = 1,625
    """
    lv = min(level, N_LEVELS - 1)
    db = min(duration_bin, N_DURATION_BINS - 1)
    de = min(danger_entry, N_DANGER_LEVELS - 1)
    dn = min(danger_now, N_DANGER_LEVELS - 1)

    idx = (lv * N_DURATION_BINS * N_DANGER_LEVELS * N_DANGER_LEVELS +
           db * N_DANGER_LEVELS * N_DANGER_LEVELS +
           de * N_DANGER_LEVELS +
           dn)
    return idx


def decode_state(idx):
    """Inverse of encode_state."""
    dn = idx % N_DANGER_LEVELS
    idx //= N_DANGER_LEVELS
    de = idx % N_DANGER_LEVELS
    idx //= N_DANGER_LEVELS
    db = idx % N_DURATION_BINS
    idx //= N_DURATION_BINS
    lv = idx
    return lv, db, de, dn


# =============================================================================
# Part 3: DangerScorer
# =============================================================================

class DangerScorer:
    """
    Composite danger score from multiple regime indicators.

    Components (all normalized to [0, 1] where 1 = most dangerous):
    - D1_range_atr: INVERSE -- low range/ATR = choppy = dangerous
    - 5m_chop:      direct  -- high choppiness = dangerous
    - 15m_chop:     direct  -- high choppiness = dangerous
    - D1_chop:      direct  -- high choppiness = dangerous
    - 5m_adx:       INVERSE -- low ADX = no trend = dangerous
    - 5m_hurst:     INVERSE distance from 0.5 -- near 0.5 = random walk = dangerous
    - 1H_atr_ratio: direct  -- high ratio = expanding vol = dangerous
    """

    def __init__(self, candles_5m, candles_15m, candles_1h, candles_d1):
        """Precompute all indicator arrays."""
        print("  Computing danger score components...")
        t0 = time.time()

        # 5m indicators
        self.chop_5m = ta.chop(candles_5m, period=14, sequential=True)
        self.adx_5m = ta.adx(candles_5m, period=14, sequential=True)
        self.hurst_5m = self._rolling_hurst(candles_5m[:, 2], window=20)

        # 15m indicators
        self.chop_15m_raw = ta.chop(candles_15m, period=14, sequential=True)
        self.ts_15m = candles_15m[:, 0]

        # 1H indicators
        atr_1h_short = ta.atr(candles_1h, period=14, sequential=True)
        atr_1h_long = ta.atr(candles_1h, period=50, sequential=True)
        with np.errstate(divide='ignore', invalid='ignore'):
            self.atr_ratio_1h_raw = np.where(
                (atr_1h_long > 1e-12) & ~np.isnan(atr_1h_long),
                atr_1h_short / atr_1h_long, np.nan)
        self.ts_1h = candles_1h[:, 0]

        # D1 indicators
        self.chop_d1_raw = ta.chop(candles_d1, period=14, sequential=True)
        atr_d1 = ta.atr(candles_d1, period=14, sequential=True)
        self.range_atr_d1_raw = self._rolling_range_atr(candles_d1, 20, atr_d1)
        self.ts_d1 = candles_d1[:, 0]

        # 5m timestamps for alignment
        self.ts_5m = candles_5m[:, 0]
        self.n_5m = len(candles_5m)

        # Align higher TF to 5m grid (forward-fill, no lookahead)
        self.chop_15m = self._align_to_5m(self.chop_15m_raw, self.ts_15m)
        self.atr_ratio_1h = self._align_to_5m(self.atr_ratio_1h_raw, self.ts_1h)
        self.chop_d1 = self._align_to_5m(self.chop_d1_raw, self.ts_d1)
        self.range_atr_d1 = self._align_to_5m(self.range_atr_d1_raw, self.ts_d1)

        # Compute running percentiles for normalization (expanding window, no lookahead)
        self._compute_percentile_arrays()

        print(f"  Danger scorer ready ({time.time()-t0:.1f}s)")

    def _rolling_hurst(self, prices, window=20):
        """Rolling Hurst exponent via R/S analysis."""
        n = len(prices)
        H = np.full(n, np.nan, dtype=np.float64)
        for i in range(window - 1, n):
            segment = prices[i - window + 1: i + 1]
            returns = np.diff(segment)
            if len(returns) < 2:
                continue
            mean_r = np.mean(returns)
            std_r = np.std(returns, ddof=0)
            if std_r < 1e-12:
                H[i] = 0.5
                continue
            cumdev = np.cumsum(returns - mean_r)
            R = np.max(cumdev) - np.min(cumdev)
            RS = R / std_r
            if RS <= 0:
                H[i] = 0.5
                continue
            H[i] = np.log(RS) / np.log(len(returns))
        return H

    def _rolling_range_atr(self, candles_tf, window, atr_arr):
        """(HH - LL) over window / ATR."""
        n = len(candles_tf)
        result = np.full(n, np.nan, dtype=np.float64)
        highs = candles_tf[:, 3]
        lows = candles_tf[:, 4]
        for i in range(window - 1, n):
            hh = np.max(highs[i - window + 1: i + 1])
            ll = np.min(lows[i - window + 1: i + 1])
            if atr_arr[i] > 1e-12 and not np.isnan(atr_arr[i]):
                result[i] = (hh - ll) / atr_arr[i]
        return result

    def _align_to_5m(self, values, ts_higher):
        """Forward-fill higher TF values onto 5m grid."""
        aligned = np.full(self.n_5m, np.nan, dtype=np.float64)
        indices = np.searchsorted(ts_higher, self.ts_5m, side='right') - 1
        valid = (indices >= 0) & (indices < len(values))
        aligned[valid] = values[indices[valid]]
        return aligned

    def _compute_percentile_arrays(self):
        """
        For each component, compute its percentile rank using an expanding
        window (up to 5000 bars lookback) to avoid lookahead bias.
        """
        lookback = 5000
        components = {
            'chop_5m': self.chop_5m,
            'adx_5m': self.adx_5m,
            'hurst_5m': self.hurst_5m,
            'chop_15m': self.chop_15m,
            'atr_ratio_1h': self.atr_ratio_1h,
            'chop_d1': self.chop_d1,
            'range_atr_d1': self.range_atr_d1,
        }

        self.pctile = {}
        for name, arr in components.items():
            pct = np.full(self.n_5m, np.nan, dtype=np.float64)
            for i in range(100, self.n_5m):
                start = max(0, i - lookback)
                window = arr[start:i+1]
                window = window[~np.isnan(window)]
                if len(window) < 20:
                    continue
                val = arr[i]
                if np.isnan(val):
                    continue
                pct[i] = np.sum(window <= val) / len(window)
            self.pctile[name] = pct

    def score(self, bar_idx):
        """
        Compute composite danger score at a given 5m bar index.
        Returns float in [0, 1] where 1 = maximum danger.
        """
        if bar_idx < 100 or bar_idx >= self.n_5m:
            return 0.5  # default

        components = {}

        # D1_range_atr (INVERSE: low range = choppy = dangerous)
        p = self.pctile.get('range_atr_d1')
        if p is not None and not np.isnan(p[bar_idx]):
            components['D1_range_atr'] = 1.0 - p[bar_idx]
        else:
            components['D1_range_atr'] = 0.5

        # 5m_chop (direct: high = dangerous)
        p = self.pctile.get('chop_5m')
        if p is not None and not np.isnan(p[bar_idx]):
            components['5m_chop'] = p[bar_idx]
        else:
            components['5m_chop'] = 0.5

        # 15m_chop (direct: high = dangerous)
        p = self.pctile.get('chop_15m')
        if p is not None and not np.isnan(p[bar_idx]):
            components['15m_chop'] = p[bar_idx]
        else:
            components['15m_chop'] = 0.5

        # D1_chop (direct: high = dangerous)
        p = self.pctile.get('chop_d1')
        if p is not None and not np.isnan(p[bar_idx]):
            components['D1_chop'] = p[bar_idx]
        else:
            components['D1_chop'] = 0.5

        # 5m_adx (INVERSE: low ADX = no trend = dangerous)
        p = self.pctile.get('adx_5m')
        if p is not None and not np.isnan(p[bar_idx]):
            components['5m_adx'] = 1.0 - p[bar_idx]
        else:
            components['5m_adx'] = 0.5

        # 5m_hurst (INVERSE distance from 0.5: near 0.5 = random = dangerous)
        h_val = self.hurst_5m[bar_idx] if bar_idx < len(self.hurst_5m) else np.nan
        if not np.isnan(h_val):
            dist = abs(h_val - 0.5)
            # max distance is ~0.5, normalize: danger = 1 - 2*dist (clamped)
            components['5m_hurst'] = max(0.0, min(1.0, 1.0 - 2.0 * dist))
        else:
            components['5m_hurst'] = 0.5

        # 1H_atr_ratio (direct: high = expanding vol = dangerous)
        p = self.pctile.get('atr_ratio_1h')
        if p is not None and not np.isnan(p[bar_idx]):
            components['1H_atr_ratio'] = p[bar_idx]
        else:
            components['1H_atr_ratio'] = 0.5

        # Weighted sum
        score = 0.0
        for key, weight in DANGER_WEIGHTS.items():
            score += weight * components.get(key, 0.5)

        return np.clip(score, 0.0, 1.0)


# =============================================================================
# Part 4: Abort Loss Computation
# =============================================================================

def compute_abort_loss_pnl(level, avg_atr):
    """
    Compute the P&L of aborting at a given level.
    Cumulative loss from levels 0..level-1. Negative value.
    """
    if level == 0:
        return 0.0
    tp_dist = avg_atr * TP_ATR_MULTIPLE
    hedge_dist = tp_dist / RISK_REWARD
    sl_pips = hedge_dist / PIP_SIZE
    total_loss = 0.0
    for l in range(level):
        size = BASE_SIZE * (MULTIPLIER ** l)
        total_loss += sl_pips * PIP_VALUE * size
    return -total_loss


def compute_bust_loss_pnl(avg_atr):
    """Total loss if all MAX_LEVELS are exhausted (bust)."""
    return compute_abort_loss_pnl(MAX_LEVELS, avg_atr)


# =============================================================================
# Part 5: TabularQLearner Class
# =============================================================================

class TabularQLearner:
    """
    Tabular Q-Learning for the abort decision.
    Q-table: N_STATES x N_ACTIONS (1625 x 2)
    """

    def __init__(self, n_states=N_STATES, n_actions=N_ACTIONS,
                 alpha=ALPHA_LR, gamma=GAMMA,
                 epsilon=EPSILON_START, epsilon_min=EPSILON_MIN,
                 epsilon_decay=EPSILON_DECAY):
        self.n_states = n_states
        self.n_actions = n_actions
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay

        # Initialize Q-table: slight optimism for continue
        self.Q = np.zeros((n_states, n_actions))
        self.Q[:, ACTION_CONTINUE] = 0.01

        # Visit counts
        self.visit_count = np.zeros((n_states, n_actions), dtype=int)

        # Training history
        self.episode_rewards = []
        self.episode_aborts = []
        self.epsilon_history = []

    def choose_action(self, state, explore=True):
        """Epsilon-greedy action selection."""
        if explore and np.random.random() < self.epsilon:
            return np.random.randint(self.n_actions)
        return np.argmax(self.Q[state])

    def update(self, state, action, reward, next_state=None, done=True):
        """Q-learning update."""
        self.visit_count[state, action] += 1
        if done or next_state is None:
            target = reward
        else:
            target = reward + self.gamma * np.max(self.Q[next_state])
        self.Q[state, action] += self.alpha * (target - self.Q[state, action])

    def decay_epsilon(self):
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    def get_policy(self):
        return np.argmax(self.Q, axis=1)

    def get_state_dict(self):
        return {
            'Q': self.Q.copy(),
            'visit_count': self.visit_count.copy(),
            'epsilon': self.epsilon,
            'episode_rewards': self.episode_rewards.copy(),
            'episode_aborts': self.episode_aborts.copy(),
        }


# =============================================================================
# Part 6: Data Loading and Resampling
# =============================================================================

def load_price_data():
    """Load EUR-USD 5m candles and resample to higher TFs."""
    print("Loading EUR-USD 5m candles from OANDA...")
    t0 = time.time()
    warmup_candles, candles_5m = get_candles('OANDA', 'EUR-USD', '5m',
        jh.date_to_timestamp('2006-01-02'), jh.date_to_timestamp('2025-12-31'),
        warmup_candles_num=210)
    if warmup_candles is not None and warmup_candles.ndim == 2 and len(warmup_candles) > 0:
        candles_5m = np.concatenate([warmup_candles, candles_5m], axis=0)
    print(f"  5m candles: {len(candles_5m):,} ({time.time()-t0:.1f}s)")

    # Resample to higher timeframes
    def resample(c1, factor):
        n = len(c1)
        trim = n - (n % factor)
        c = c1[:trim].reshape(-1, factor, 6)
        out = np.empty((len(c), 6), dtype=np.float64)
        out[:, 0] = c[:, 0, 0]
        out[:, 1] = c[:, 0, 1]
        out[:, 2] = c[:, -1, 2]
        out[:, 3] = c[:, :, 3].max(axis=1)
        out[:, 4] = c[:, :, 4].min(axis=1)
        out[:, 5] = c[:, :, 5].sum(axis=1)
        return out

    candles_15m = resample(candles_5m, 3)
    candles_1h = resample(candles_5m, 12)
    candles_d1 = resample(candles_5m, 288)

    print(f"  15m: {len(candles_15m):,}, 1H: {len(candles_1h):,}, D1: {len(candles_d1):,}")

    return candles_5m, candles_15m, candles_1h, candles_d1


def compute_indicators(candles_5m):
    ema_fast = ta.ema(candles_5m, period=EMA_FAST, sequential=True)
    ema_slow = ta.ema(candles_5m, period=EMA_SLOW, sequential=True)
    atr_arr = ta.atr(candles_5m, period=ATR_PERIOD, sequential=True)
    return ema_fast, ema_slow, atr_arr


# =============================================================================
# Part 7: Simulate Level for One Leg
# =============================================================================

def simulate_level(entry_price, direction, tp_dist, hedge_dist, start_bar,
                   highs, lows):
    """Simulate one level. Returns (outcome, end_bar, [sl_price])."""
    if direction == 'long':
        tp_price = entry_price + tp_dist
        sl_price = entry_price - hedge_dist
    else:
        tp_price = entry_price - tp_dist
        sl_price = entry_price + hedge_dist

    max_bar = min(start_bar + MAX_BARS_PER_LEVEL, len(highs))
    for j in range(start_bar, max_bar):
        h, l = highs[j], lows[j]
        if direction == 'long':
            if l <= sl_price and h >= tp_price:
                return ('sl', j, sl_price)
            if h >= tp_price:
                return ('tp', j)
            if l <= sl_price:
                return ('sl', j, sl_price)
        else:
            if h >= sl_price and l <= tp_price:
                return ('sl', j, sl_price)
            if l <= tp_price:
                return ('tp', j)
            if h >= sl_price:
                return ('sl', j, sl_price)
    return ('timeout', max_bar - 1)


# =============================================================================
# Part 8: Build Cycle Episodes with Duration + Danger
# =============================================================================

def build_level_episodes(candles_5m, atr_arr, ema_fast, ema_slow, danger_scorer):
    """
    Build cycle episodes with level-by-level outcomes.
    Each level records: bars elapsed since cycle start, danger_score_now.
    """
    closes = candles_5m[:, 2]
    highs = candles_5m[:, 3]
    lows = candles_5m[:, 4]

    min_start = max(ATR_PERIOD + 5, EMA_SLOW + 5, 200)  # need 200 for danger scorer
    signals = []
    for i in range(min_start, len(candles_5m) - MAX_BARS_PER_LEVEL):
        if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]):
            continue
        if np.isnan(ema_fast[i-1]) or np.isnan(ema_slow[i-1]):
            continue
        if np.isnan(atr_arr[i]) or atr_arr[i] <= 0:
            continue
        if ema_fast[i-1] <= ema_slow[i-1] and ema_fast[i] > ema_slow[i]:
            signals.append((i, 'long'))
        elif ema_fast[i-1] >= ema_slow[i-1] and ema_fast[i] < ema_slow[i]:
            signals.append((i, 'short'))

    print(f"  Total signals: {len(signals):,}")

    episodes = []
    next_allowed = 0

    for sig_bar, sig_dir in signals:
        if sig_bar < next_allowed:
            continue

        entry_price = closes[sig_bar]
        direction = sig_dir
        current_bar = sig_bar + 1

        # Danger score at entry
        danger_at_entry = danger_scorer.score(sig_bar)

        level_outcomes = []
        cum_pnl = 0.0
        valid = True

        for level in range(MAX_LEVELS):
            current_atr = atr_arr[min(current_bar, len(atr_arr)-1)]
            if np.isnan(current_atr) or current_atr <= 0:
                current_atr = atr_arr[sig_bar]
            if np.isnan(current_atr) or current_atr <= 0:
                valid = False
                break

            tp_dist = current_atr * TP_ATR_MULTIPLE
            hedge_dist = tp_dist / RISK_REWARD
            size = BASE_SIZE * (MULTIPLIER ** level)
            tp_pips = tp_dist / PIP_SIZE
            sl_pips = hedge_dist / PIP_SIZE

            # Bars elapsed since cycle start
            bars_elapsed = current_bar - sig_bar

            # Current danger score
            danger_now = danger_scorer.score(min(current_bar, danger_scorer.n_5m - 1))

            result = simulate_level(entry_price, direction, tp_dist,
                                    hedge_dist, current_bar, highs, lows)

            if result[0] == 'tp':
                profit = tp_pips * PIP_VALUE * size
                cum_pnl += profit
                level_outcomes.append({
                    'level': level,
                    'outcome': 'win',
                    'level_pnl': profit,
                    'cum_pnl': cum_pnl,
                    'bars_elapsed': bars_elapsed,
                    'danger_now': danger_now,
                    'end_bar': result[1],
                })
                break
            elif result[0] == 'sl':
                loss = sl_pips * PIP_VALUE * size
                cum_pnl -= loss
                level_outcomes.append({
                    'level': level,
                    'outcome': 'loss',
                    'level_pnl': -loss,
                    'cum_pnl': cum_pnl,
                    'bars_elapsed': bars_elapsed,
                    'danger_now': danger_now,
                    'end_bar': result[1],
                })
                entry_price = result[2]
                direction = 'short' if direction == 'long' else 'long'
                current_bar = result[1] + 1
                if current_bar >= len(highs):
                    valid = False
                    break
            elif result[0] == 'timeout':
                valid = False
                break

        if not valid or len(level_outcomes) == 0:
            continue

        last = level_outcomes[-1]
        if last['outcome'] == 'win':
            cycle_outcome = 'win'
        elif len(level_outcomes) == MAX_LEVELS and last['outcome'] == 'loss':
            cycle_outcome = 'bust'
        else:
            cycle_outcome = 'incomplete'
            continue

        episodes.append({
            'entry_bar': sig_bar,
            'danger_at_entry': danger_at_entry,
            'level_outcomes': level_outcomes,
            'cycle_outcome': cycle_outcome,
            'total_pnl': cum_pnl,
            'timestamp': candles_5m[sig_bar, 0],
        })
        next_allowed = last['end_bar'] + 1

    print(f"  Built {len(episodes)} complete episodes")
    n_wins = sum(1 for e in episodes if e['cycle_outcome'] == 'win')
    n_busts = sum(1 for e in episodes if e['cycle_outcome'] == 'bust')
    print(f"    Wins: {n_wins}, Busts: {n_busts} ({n_busts/len(episodes)*100:.2f}%)")

    return episodes


# =============================================================================
# Part 9: Duration / Danger Diagnostic -- Validate Key Finding
# =============================================================================

def duration_danger_diagnostic(episodes):
    """Show bust rates by duration bin and danger level to validate the 91x finding."""
    print("\n" + "-" * 70)
    print("DURATION-DANGER DIAGNOSTIC (validating key findings)")
    print("-" * 70)

    # Bust rate by duration bin (using max bars elapsed in cycle)
    dur_bins = defaultdict(lambda: {'total': 0, 'busts': 0})
    danger_bins = defaultdict(lambda: {'total': 0, 'busts': 0})

    for ep in episodes:
        max_bars = max(lo['bars_elapsed'] for lo in ep['level_outcomes'])
        dbin = bars_to_duration_bin(max_bars)
        dur_bins[dbin]['total'] += 1
        if ep['cycle_outcome'] == 'bust':
            dur_bins[dbin]['busts'] += 1

        dlvl = danger_score_to_level(ep['danger_at_entry'])
        danger_bins[dlvl]['total'] += 1
        if ep['cycle_outcome'] == 'bust':
            danger_bins[dlvl]['busts'] += 1

    bin_labels = ['0-5', '5-10', '10-20', '20-50', '50+']
    print(f"\n  {'Duration Bin':<15} {'Total':<10} {'Busts':<10} {'Bust Rate':<12}")
    print(f"  {'-'*47}")
    for b in range(N_DURATION_BINS):
        d = dur_bins[b]
        rate = d['busts'] / d['total'] * 100 if d['total'] > 0 else 0
        print(f"  {bin_labels[b]:<15} {d['total']:<10} {d['busts']:<10} {rate:<12.2f}%")

    danger_labels = ['safe(<0.3)', 'mild(0.3-0.5)', 'caution(0.5-0.7)',
                     'warning(0.7-0.85)', 'danger(>0.85)']
    print(f"\n  {'Danger Level':<20} {'Total':<10} {'Busts':<10} {'Bust Rate':<12}")
    print(f"  {'-'*52}")
    for b in range(N_DANGER_LEVELS):
        d = danger_bins[b]
        rate = d['busts'] / d['total'] * 100 if d['total'] > 0 else 0
        print(f"  {danger_labels[b]:<20} {d['total']:<10} {d['busts']:<10} {rate:<12.2f}%")

    # Cross-tabulation: bust rate by (duration_bin, danger_level)
    cross = np.zeros((N_DURATION_BINS, N_DANGER_LEVELS, 2))  # [total, busts]
    for ep in episodes:
        max_bars = max(lo['bars_elapsed'] for lo in ep['level_outcomes'])
        dbin = bars_to_duration_bin(max_bars)
        dlvl = danger_score_to_level(ep['danger_at_entry'])
        cross[dbin, dlvl, 0] += 1
        if ep['cycle_outcome'] == 'bust':
            cross[dbin, dlvl, 1] += 1

    print(f"\n  Cross-tab: Bust rate by (Duration, Danger)")
    header = f"  {'Dur \\ Danger':<12}"
    for dl in danger_labels:
        header += f" {dl[:8]:<10}"
    print(header)
    print(f"  {'-'*(12 + 10 * N_DANGER_LEVELS)}")
    for db in range(N_DURATION_BINS):
        row = f"  {bin_labels[db]:<12}"
        for dl in range(N_DANGER_LEVELS):
            total = cross[db, dl, 0]
            busts = cross[db, dl, 1]
            rate = busts / total * 100 if total > 0 else 0
            row += f" {rate:>5.1f}%({int(total):>3})"
        print(row)

    return cross


# =============================================================================
# Part 10: Q-Learning Training
# =============================================================================

def train_q_learner(episodes, n_epochs=50, verbose=True):
    """
    Train tabular Q-learner on historical cycle episodes.
    At each level, Q-learner sees state = (level, duration_bin, danger_entry, danger_now)
    and decides: continue or abort.
    """
    learner = TabularQLearner()

    for epoch in range(n_epochs):
        np.random.shuffle(episodes)
        epoch_rewards = []
        epoch_aborts = 0
        epoch_continues = 0

        for ep in episodes:
            danger_entry = danger_score_to_level(ep['danger_at_entry'])
            levels = ep['level_outcomes']

            for i, lvl in enumerate(levels):
                level = lvl['level']
                duration_bin = bars_to_duration_bin(lvl['bars_elapsed'])
                danger_now = danger_score_to_level(lvl['danger_now'])

                state = encode_state(level, duration_bin, danger_entry, danger_now)
                action = learner.choose_action(state)

                if action == ACTION_ABORT:
                    if i > 0:
                        abort_pnl = levels[i-1]['cum_pnl']
                    else:
                        abort_pnl = 0.0
                    learner.update(state, ACTION_ABORT, abort_pnl, done=True)
                    epoch_rewards.append(abort_pnl)
                    epoch_aborts += 1
                    break

                else:  # continue
                    epoch_continues += 1

                    if lvl['outcome'] == 'win':
                        reward = lvl['cum_pnl']
                        learner.update(state, ACTION_CONTINUE, reward, done=True)
                        epoch_rewards.append(reward)
                        break

                    elif lvl['outcome'] == 'loss':
                        if i == len(levels) - 1:
                            # Bust
                            reward = lvl['cum_pnl']
                            learner.update(state, ACTION_CONTINUE, reward, done=True)
                            epoch_rewards.append(reward)
                        else:
                            # Lost this level, next level coming
                            next_lvl = levels[i+1]
                            next_dur_bin = bars_to_duration_bin(next_lvl['bars_elapsed'])
                            next_danger = danger_score_to_level(next_lvl['danger_now'])
                            next_state = encode_state(
                                next_lvl['level'], next_dur_bin,
                                danger_entry, next_danger)
                            learner.update(state, ACTION_CONTINUE, 0,
                                           next_state=next_state, done=False)

        learner.decay_epsilon()

        avg_reward = np.mean(epoch_rewards) if epoch_rewards else 0
        learner.episode_rewards.append(avg_reward)
        learner.episode_aborts.append(epoch_aborts)
        learner.epsilon_history.append(learner.epsilon)

        if verbose and (epoch % 10 == 0 or epoch == n_epochs - 1):
            print(f"  Epoch {epoch:3d}: avg_reward={avg_reward:8.2f}, "
                  f"aborts={epoch_aborts:5d}, continues={epoch_continues:5d}, "
                  f"epsilon={learner.epsilon:.4f}")

    return learner


# =============================================================================
# Part 11: Evaluation Helpers
# =============================================================================

def evaluate_policy(episodes, learner, explore=False, label="Q-Learner-v2"):
    """Evaluate a policy on episodes. Returns metrics dict."""
    total_pnl = 0.0
    n_traded = 0
    n_aborted = 0
    n_wins = 0
    n_busts = 0
    abort_levels = []
    abort_durations = []
    abort_dangers = []
    cycle_pnls = []

    for ep in episodes:
        danger_entry = danger_score_to_level(ep['danger_at_entry'])
        levels = ep['level_outcomes']
        aborted = False

        for i, lvl in enumerate(levels):
            level = lvl['level']
            duration_bin = bars_to_duration_bin(lvl['bars_elapsed'])
            danger_now = danger_score_to_level(lvl['danger_now'])

            state = encode_state(level, duration_bin, danger_entry, danger_now)
            action = learner.choose_action(state, explore=explore)

            if action == ACTION_ABORT:
                if i > 0:
                    pnl = levels[i-1]['cum_pnl']
                else:
                    pnl = 0.0
                total_pnl += pnl
                cycle_pnls.append(pnl)
                n_aborted += 1
                abort_levels.append(level)
                abort_durations.append(duration_bin)
                abort_dangers.append(danger_now)
                aborted = True
                break

            if lvl['outcome'] == 'win':
                pnl = lvl['cum_pnl']
                total_pnl += pnl
                cycle_pnls.append(pnl)
                n_wins += 1
                break

            if lvl['outcome'] == 'loss' and i == len(levels) - 1:
                pnl = lvl['cum_pnl']
                total_pnl += pnl
                cycle_pnls.append(pnl)
                n_busts += 1

        n_traded += 1

    bust_rate = n_busts / n_traded if n_traded > 0 else 0
    abort_rate = n_aborted / n_traded if n_traded > 0 else 0

    return {
        'label': label,
        'n_episodes': n_traded,
        'n_wins': n_wins,
        'n_busts': n_busts,
        'n_aborted': n_aborted,
        'bust_rate': bust_rate,
        'abort_rate': abort_rate,
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / n_traded if n_traded > 0 else 0,
        'abort_levels': abort_levels,
        'abort_durations': abort_durations,
        'abort_dangers': abort_dangers,
        'cycle_pnls': np.array(cycle_pnls),
    }


def evaluate_never_abort(episodes):
    """Baseline: never abort."""
    total_pnl = 0.0
    n_wins = 0
    n_busts = 0
    cycle_pnls = []

    for ep in episodes:
        pnl = ep['total_pnl']
        total_pnl += pnl
        cycle_pnls.append(pnl)
        if ep['cycle_outcome'] == 'win':
            n_wins += 1
        else:
            n_busts += 1

    n_total = len(episodes)
    return {
        'label': 'Never-Abort',
        'n_episodes': n_total,
        'n_wins': n_wins,
        'n_busts': n_busts,
        'n_aborted': 0,
        'bust_rate': n_busts / n_total if n_total > 0 else 0,
        'abort_rate': 0.0,
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / n_total if n_total > 0 else 0,
        'abort_levels': [],
        'abort_durations': [],
        'abort_dangers': [],
        'cycle_pnls': np.array(cycle_pnls),
    }


def evaluate_threshold_abort(episodes, max_level=4):
    """Simple rule: abort if level >= max_level."""
    total_pnl = 0.0
    n_wins = 0
    n_busts = 0
    n_aborted = 0
    abort_levels = []
    cycle_pnls = []

    for ep in episodes:
        levels = ep['level_outcomes']
        aborted = False

        for i, lvl in enumerate(levels):
            if lvl['level'] >= max_level:
                if i > 0:
                    pnl = levels[i-1]['cum_pnl']
                else:
                    pnl = 0.0
                total_pnl += pnl
                cycle_pnls.append(pnl)
                n_aborted += 1
                abort_levels.append(lvl['level'])
                aborted = True
                break

            if lvl['outcome'] == 'win':
                total_pnl += lvl['cum_pnl']
                cycle_pnls.append(lvl['cum_pnl'])
                n_wins += 1
                break

            if lvl['outcome'] == 'loss' and i == len(levels) - 1:
                total_pnl += lvl['cum_pnl']
                cycle_pnls.append(lvl['cum_pnl'])
                n_busts += 1

    n_total = len(episodes)
    return {
        'label': f'Threshold-Abort (L>={max_level})',
        'n_episodes': n_total,
        'n_wins': n_wins,
        'n_busts': n_busts,
        'n_aborted': n_aborted,
        'bust_rate': n_busts / n_total if n_total > 0 else 0,
        'abort_rate': n_aborted / n_total if n_total > 0 else 0,
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / n_total if n_total > 0 else 0,
        'abort_levels': abort_levels,
        'abort_durations': [],
        'abort_dangers': [],
        'cycle_pnls': np.array(cycle_pnls),
    }


# Simulate the old v1 Q-learner (level + regime) for comparison
def evaluate_old_v1_proxy(episodes):
    """
    Proxy for old Q-learner v1 (level + regime state).
    Since we don't have the trained v1 model, use the known result:
    v1 aborted at levels [6, 9, 10, 11], bust 0.15%, abort 1.16%.
    We approximate by aborting at those exact levels.
    """
    total_pnl = 0.0
    n_wins = 0
    n_busts = 0
    n_aborted = 0
    abort_levels_out = []
    cycle_pnls = []
    v1_abort_levels = {6, 9, 10, 11}

    for ep in episodes:
        levels = ep['level_outcomes']

        for i, lvl in enumerate(levels):
            if lvl['level'] in v1_abort_levels:
                if i > 0:
                    pnl = levels[i-1]['cum_pnl']
                else:
                    pnl = 0.0
                total_pnl += pnl
                cycle_pnls.append(pnl)
                n_aborted += 1
                abort_levels_out.append(lvl['level'])
                break

            if lvl['outcome'] == 'win':
                total_pnl += lvl['cum_pnl']
                cycle_pnls.append(lvl['cum_pnl'])
                n_wins += 1
                break

            if lvl['outcome'] == 'loss' and i == len(levels) - 1:
                total_pnl += lvl['cum_pnl']
                cycle_pnls.append(lvl['cum_pnl'])
                n_busts += 1

    n_total = len(episodes)
    return {
        'label': 'Q-Learner-v1 (proxy)',
        'n_episodes': n_total,
        'n_wins': n_wins,
        'n_busts': n_busts,
        'n_aborted': n_aborted,
        'bust_rate': n_busts / n_total if n_total > 0 else 0,
        'abort_rate': n_aborted / n_total if n_total > 0 else 0,
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / n_total if n_total > 0 else 0,
        'abort_levels': abort_levels_out,
        'abort_durations': [],
        'abort_dangers': [],
        'cycle_pnls': np.array(cycle_pnls),
    }


# =============================================================================
# Part 12: Break-Even Analysis by (Level, Duration Bin)
# =============================================================================

def break_even_analysis(episodes):
    """
    At each (level, duration_bin), compute empirical P(bust | remaining levels)
    and the threshold where abort is optimal.
    """
    print("\n" + "-" * 70)
    print("BREAK-EVEN ANALYSIS: P(bust) threshold by (level, duration_bin)")
    print("-" * 70)

    sizes = np.array([BASE_SIZE * (MULTIPLIER ** l) for l in range(MAX_LEVELS)])
    cum_sizes = np.cumsum(sizes)
    bust_total = cum_sizes[-1]

    # Empirical bust rate from each (level, duration_bin) forward
    # i.e., given you're at level L with duration bin D, what fraction bust?
    forward_busts = np.zeros((MAX_LEVELS, N_DURATION_BINS))
    forward_total = np.zeros((MAX_LEVELS, N_DURATION_BINS))

    for ep in episodes:
        levels = ep['level_outcomes']
        is_bust = ep['cycle_outcome'] == 'bust'
        for lvl in levels:
            level = lvl['level']
            dbin = bars_to_duration_bin(lvl['bars_elapsed'])
            forward_total[level, dbin] += 1
            if is_bust:
                forward_busts[level, dbin] += 1

    bin_labels = ['0-5', '5-10', '10-20', '20-50', '50+']

    print(f"\n  Empirical P(bust | at level L, duration bin D):")
    header = f"  {'Level':<8}"
    for bl in bin_labels:
        header += f" {bl:<12}"
    print(header)
    print(f"  {'-'*(8 + 12 * N_DURATION_BINS)}")

    for level in range(MAX_LEVELS):
        row = f"  L{level:<7}"
        for db in range(N_DURATION_BINS):
            t = forward_total[level, db]
            b = forward_busts[level, db]
            if t > 0:
                rate = b / t * 100
                row += f" {rate:>5.1f}%({int(t):>3})"
            else:
                row += f" {'--':>10} "
        print(row)

    # Break-even threshold
    print(f"\n  Break-even: abort is optimal when empirical P(bust) exceeds:")
    print(f"  {'Level':<8} {'Abort/Bust ratio':<20} {'P(bust) threshold':<20}")
    print(f"  {'-'*48}")

    for level in range(MAX_LEVELS):
        abort_loss = cum_sizes[level]
        p_threshold = abort_loss / bust_total if bust_total > 0 else 0
        print(f"  L{level:<7} {abort_loss/bust_total:<20.4f} > {p_threshold*100:.1f}%")

    return forward_busts, forward_total


# =============================================================================
# Part 13: Walk-Forward Evaluation
# =============================================================================

def walk_forward_q_learning(episodes):
    """Walk-forward: train on expanding window, test on next segment."""
    timestamps = np.array([e['timestamp'] for e in episodes])
    ts_min, ts_max = timestamps.min(), timestamps.max()
    total_dur = ts_max - ts_min
    seg_dur = total_dur / 4

    boundaries = [ts_min + i * seg_dur for i in range(5)]
    segments = []
    for i in range(4):
        seg = [e for e in episodes if boundaries[i] <= e['timestamp'] < boundaries[i+1]]
        segments.append(seg)
        print(f"  Segment {i}: {len(seg)} episodes")

    wf_results = []
    for test_idx in range(1, len(segments)):
        train_eps = []
        for j in range(test_idx):
            train_eps.extend(segments[j])
        test_eps = segments[test_idx]

        if len(test_eps) < 5 or len(train_eps) < 10:
            continue

        learner = train_q_learner(train_eps, n_epochs=30, verbose=False)

        q_result = evaluate_policy(test_eps, learner, explore=False,
                                   label=f'Q-v2 Seg{test_idx}')
        never_result = evaluate_never_abort(test_eps)
        thresh_result = evaluate_threshold_abort(test_eps, max_level=4)
        v1_result = evaluate_old_v1_proxy(test_eps)

        wf_results.append({
            'test_idx': test_idx,
            'n_train': len(train_eps),
            'n_test': len(test_eps),
            'q_learner_v2': q_result,
            'never_abort': never_result,
            'threshold_abort': thresh_result,
            'q_learner_v1': v1_result,
        })

    return wf_results


# =============================================================================
# MAIN EXECUTION
# =============================================================================

print("=" * 80)
print("  SCRIPT 19b: Q-Learning Abort v2 -- Duration + Danger State Space")
print("=" * 80)

# ---- Load data --------------------------------------------------------------
candles_5m, candles_15m, candles_1h, candles_d1 = load_price_data()
ema_fast, ema_slow, atr_arr = compute_indicators(candles_5m)

# ---- Build DangerScorer -----------------------------------------------------
print("\n" + "=" * 80)
print("BUILDING DANGER SCORER")
print("=" * 80)
danger_scorer = DangerScorer(candles_5m, candles_15m, candles_1h, candles_d1)

# ---- Build episodes ---------------------------------------------------------
print("\n" + "=" * 80)
print("BUILDING EPISODES")
print("=" * 80)
episodes = build_level_episodes(candles_5m, atr_arr, ema_fast, ema_slow, danger_scorer)

# ---- Duration/Danger diagnostic ---------------------------------------------
cross_tab = duration_danger_diagnostic(episodes)

# ---- Break-even analysis ----------------------------------------------------
print("\n" + "=" * 80)
print("BREAK-EVEN ANALYSIS")
print("=" * 80)
forward_busts, forward_total = break_even_analysis(episodes)

avg_atr = np.nanmean(atr_arr[ATR_PERIOD:])
print(f"\n  Average ATR: {avg_atr:.6f}")
print(f"  Abort loss in $ at each level (avg ATR):")
for level in range(MAX_LEVELS):
    abort_pnl = compute_abort_loss_pnl(level, avg_atr)
    print(f"    L{level}: ${abort_pnl:,.2f}")
bust_pnl = compute_bust_loss_pnl(avg_atr)
print(f"    Full bust: ${bust_pnl:,.2f}")

# ---- Train Q-Learner v2 ----------------------------------------------------
print("\n" + "=" * 80)
print("Q-LEARNING v2 TRAINING (50 epochs)")
print("=" * 80)
learner = train_q_learner(episodes, n_epochs=50, verbose=True)

# ---- Evaluate ---------------------------------------------------------------
print("\n" + "=" * 80)
print("FOUR-WAY COMPARISON: Q-v2 vs Never-Abort vs Q-v1(proxy) vs Threshold")
print("=" * 80)

q_v2_result = evaluate_policy(episodes, learner, explore=False, label='Q-Learner-v2')
never_result = evaluate_never_abort(episodes)
v1_result = evaluate_old_v1_proxy(episodes)
thresh_result = evaluate_threshold_abort(episodes, max_level=4)

# Also test multiple thresholds
threshold_results = {}
for max_lvl in [4, 5, 6, 7, 8]:
    threshold_results[max_lvl] = evaluate_threshold_abort(episodes, max_level=max_lvl)

all_results = [never_result, v1_result, q_v2_result, thresh_result]

print(f"\n  {'Strategy':<30} {'Episodes':<10} {'Wins':<8} {'Busts':<8} "
      f"{'Aborts':<8} {'Bust%':<8} {'Abort%':<8} {'TotalPnL':<12} {'AvgPnL':<10}")
print(f"  {'-'*102}")
for r in all_results:
    print(f"  {r['label']:<30} {r['n_episodes']:<10} {r['n_wins']:<8} "
          f"{r['n_busts']:<8} {r['n_aborted']:<8} "
          f"{r['bust_rate']*100:<8.2f} {r['abort_rate']*100:<8.2f} "
          f"${r['total_pnl']:<11,.2f} ${r['avg_pnl']:<9,.2f}")

# Additional thresholds
print(f"\n  Threshold variants:")
for max_lvl in sorted(threshold_results.keys()):
    r = threshold_results[max_lvl]
    print(f"  {r['label']:<30} {r['n_episodes']:<10} {r['n_wins']:<8} "
          f"{r['n_busts']:<8} {r['n_aborted']:<8} "
          f"{r['bust_rate']*100:<8.2f} {r['abort_rate']*100:<8.2f} "
          f"${r['total_pnl']:<11,.2f} ${r['avg_pnl']:<9,.2f}")

# ---- Policy Analysis --------------------------------------------------------
print("\n" + "=" * 80)
print("POLICY ANALYSIS: Where does Q-v2 abort?")
print("=" * 80)

policy = learner.get_policy()

# Abort decisions by level
print("\n  Abort policy by level:")
for level in range(MAX_LEVELS):
    n_abort = 0
    n_total = 0
    for db in range(N_DURATION_BINS):
        for de in range(N_DANGER_LEVELS):
            for dn in range(N_DANGER_LEVELS):
                state = encode_state(level, db, de, dn)
                if learner.visit_count[state].sum() > 0:
                    n_total += 1
                    if policy[state] == ACTION_ABORT:
                        n_abort += 1
    pct = n_abort / n_total * 100 if n_total > 0 else 0
    print(f"    L{level}: {n_abort}/{n_total} visited states abort ({pct:.1f}%)")

# Abort decisions by (level, duration_bin)
print("\n  Abort rate by (level, duration_bin) -- visited states only:")
bin_labels = ['0-5', '5-10', '10-20', '20-50', '50+']
header = f"  {'Level':<8}"
for bl in bin_labels:
    header += f" {bl:<10}"
print(header)
print(f"  {'-'*(8 + 10*N_DURATION_BINS)}")
for level in range(MAX_LEVELS):
    row = f"  L{level:<7}"
    for db in range(N_DURATION_BINS):
        n_abort = 0
        n_total = 0
        for de in range(N_DANGER_LEVELS):
            for dn in range(N_DANGER_LEVELS):
                state = encode_state(level, db, de, dn)
                if learner.visit_count[state].sum() > 0:
                    n_total += 1
                    if policy[state] == ACTION_ABORT:
                        n_abort += 1
        if n_total > 0:
            pct = n_abort / n_total * 100
            row += f" {pct:>5.0f}%({n_total:>2})"
        else:
            row += f" {'--':>8}  "
    print(row)

# Abort level distribution from evaluation
if q_v2_result['abort_levels']:
    abort_arr = np.array(q_v2_result['abort_levels'])
    print(f"\n  Abort level distribution (from evaluation):")
    for lvl in sorted(np.unique(abort_arr)):
        count = np.sum(abort_arr == lvl)
        print(f"    Level {lvl}: {count} aborts ({count/len(abort_arr)*100:.1f}%)")

if q_v2_result['abort_durations']:
    dur_arr = np.array(q_v2_result['abort_durations'])
    print(f"\n  Abort duration bin distribution:")
    for db in sorted(np.unique(dur_arr)):
        count = np.sum(dur_arr == db)
        print(f"    Bin {db} ({bin_labels[db]}): {count} aborts ({count/len(dur_arr)*100:.1f}%)")

if q_v2_result['abort_dangers']:
    dng_arr = np.array(q_v2_result['abort_dangers'])
    danger_labels = ['safe', 'mild', 'caution', 'warning', 'danger']
    print(f"\n  Abort danger level distribution:")
    for dl in sorted(np.unique(dng_arr)):
        count = np.sum(dng_arr == dl)
        print(f"    {danger_labels[dl]}: {count} aborts ({count/len(dng_arr)*100:.1f}%)")

# ---- Walk-Forward Evaluation ------------------------------------------------
print("\n" + "=" * 80)
print("WALK-FORWARD EVALUATION (4 segments)")
print("=" * 80)

wf_results = walk_forward_q_learning(episodes)

print(f"\n  {'Seg':<6} {'Train':<8} {'Test':<8} "
      f"{'Qv2-Bust%':<10} {'NvA-Bust%':<10} {'Qv1-Bust%':<10} {'Thr-Bust%':<10} "
      f"{'Qv2-PnL':<12} {'NvA-PnL':<12}")
print(f"  {'-'*106}")
for r in wf_results:
    qv2 = r['q_learner_v2']
    nva = r['never_abort']
    qv1 = r['q_learner_v1']
    thr = r['threshold_abort']
    print(f"  {r['test_idx']:<6} {r['n_train']:<8} {r['n_test']:<8} "
          f"{qv2['bust_rate']*100:<10.2f} {nva['bust_rate']*100:<10.2f} "
          f"{qv1['bust_rate']*100:<10.2f} {thr['bust_rate']*100:<10.2f} "
          f"${qv2['total_pnl']:<11,.2f} ${nva['total_pnl']:<11,.2f}")

n_v2_beats_nva = sum(1 for r in wf_results
                     if r['q_learner_v2']['bust_rate'] < r['never_abort']['bust_rate'])
n_v2_beats_v1 = sum(1 for r in wf_results
                    if r['q_learner_v2']['bust_rate'] < r['q_learner_v1']['bust_rate'])
n_v2_beats_thr = sum(1 for r in wf_results
                     if r['q_learner_v2']['total_pnl'] > r['threshold_abort']['total_pnl'])
print(f"\n  Q-v2 beats never-abort on bust rate: {n_v2_beats_nva}/{len(wf_results)}")
print(f"  Q-v2 beats Q-v1(proxy) on bust rate: {n_v2_beats_v1}/{len(wf_results)}")
print(f"  Q-v2 beats threshold on P&L: {n_v2_beats_thr}/{len(wf_results)}")


# =============================================================================
# CHARTS
# =============================================================================
plt.style.use('seaborn-v0_8-darkgrid')

# ---- Chart 1: Policy Heatmap (level x duration_bin, aggregated over danger) -
fig, axes = plt.subplots(1, 3, figsize=(22, 8))

bin_labels_short = ['0-5', '5-10', '10-20', '20-50', '50+']
danger_labels_short = ['safe', 'mild', 'caut', 'warn', 'dang']

# Panel 1: Abort prob by (level, duration_bin) -- averaged over danger
ax = axes[0]
abort_prob_ld = np.full((MAX_LEVELS, N_DURATION_BINS), np.nan)
for level in range(MAX_LEVELS):
    for db in range(N_DURATION_BINS):
        n_abort = 0
        n_total = 0
        for de in range(N_DANGER_LEVELS):
            for dn in range(N_DANGER_LEVELS):
                state = encode_state(level, db, de, dn)
                if learner.visit_count[state].sum() > 0:
                    n_total += 1
                    if policy[state] == ACTION_ABORT:
                        n_abort += 1
        if n_total > 0:
            abort_prob_ld[level, db] = n_abort / n_total

im = ax.imshow(abort_prob_ld.T, aspect='auto', cmap='RdYlGn_r',
               vmin=0, vmax=1, origin='lower')
ax.set_xlabel('Hedge Level', fontsize=12)
ax.set_ylabel('Duration Bin (bars)', fontsize=12)
ax.set_title('Abort P(abort) by Level x Duration', fontweight='bold')
ax.set_xticks(range(MAX_LEVELS))
ax.set_yticks(range(N_DURATION_BINS))
ax.set_yticklabels(bin_labels_short)
plt.colorbar(im, ax=ax, label='P(abort)')

# Add text annotations
for level in range(MAX_LEVELS):
    for db in range(N_DURATION_BINS):
        val = abort_prob_ld[level, db]
        if not np.isnan(val):
            ax.text(level, db, f'{val:.0%}', ha='center', va='center',
                    fontsize=7, color='black' if val < 0.6 else 'white')

# Panel 2: Abort prob by (level, danger_now) -- averaged over duration
ax = axes[1]
abort_prob_ldg = np.full((MAX_LEVELS, N_DANGER_LEVELS), np.nan)
for level in range(MAX_LEVELS):
    for dn in range(N_DANGER_LEVELS):
        n_abort = 0
        n_total = 0
        for db in range(N_DURATION_BINS):
            for de in range(N_DANGER_LEVELS):
                state = encode_state(level, db, de, dn)
                if learner.visit_count[state].sum() > 0:
                    n_total += 1
                    if policy[state] == ACTION_ABORT:
                        n_abort += 1
        if n_total > 0:
            abort_prob_ldg[level, dn] = n_abort / n_total

im = ax.imshow(abort_prob_ldg.T, aspect='auto', cmap='RdYlGn_r',
               vmin=0, vmax=1, origin='lower')
ax.set_xlabel('Hedge Level', fontsize=12)
ax.set_ylabel('Danger Level (now)', fontsize=12)
ax.set_title('Abort P(abort) by Level x Danger-Now', fontweight='bold')
ax.set_xticks(range(MAX_LEVELS))
ax.set_yticks(range(N_DANGER_LEVELS))
ax.set_yticklabels(danger_labels_short)
plt.colorbar(im, ax=ax, label='P(abort)')

for level in range(MAX_LEVELS):
    for dn in range(N_DANGER_LEVELS):
        val = abort_prob_ldg[level, dn]
        if not np.isnan(val):
            ax.text(level, dn, f'{val:.0%}', ha='center', va='center',
                    fontsize=7, color='black' if val < 0.6 else 'white')

# Panel 3: Abort prob by (duration_bin, danger_now) -- averaged over level
ax = axes[2]
abort_prob_dd = np.full((N_DURATION_BINS, N_DANGER_LEVELS), np.nan)
for db in range(N_DURATION_BINS):
    for dn in range(N_DANGER_LEVELS):
        n_abort = 0
        n_total = 0
        for level in range(MAX_LEVELS):
            for de in range(N_DANGER_LEVELS):
                state = encode_state(level, db, de, dn)
                if learner.visit_count[state].sum() > 0:
                    n_total += 1
                    if policy[state] == ACTION_ABORT:
                        n_abort += 1
        if n_total > 0:
            abort_prob_dd[db, dn] = n_abort / n_total

im = ax.imshow(abort_prob_dd.T, aspect='auto', cmap='RdYlGn_r',
               vmin=0, vmax=1, origin='lower')
ax.set_xlabel('Duration Bin (bars)', fontsize=12)
ax.set_ylabel('Danger Level (now)', fontsize=12)
ax.set_title('Abort P(abort) by Duration x Danger-Now', fontweight='bold')
ax.set_xticks(range(N_DURATION_BINS))
ax.set_xticklabels(bin_labels_short)
ax.set_yticks(range(N_DANGER_LEVELS))
ax.set_yticklabels(danger_labels_short)
plt.colorbar(im, ax=ax, label='P(abort)')

for db in range(N_DURATION_BINS):
    for dn in range(N_DANGER_LEVELS):
        val = abort_prob_dd[db, dn]
        if not np.isnan(val):
            ax.text(db, dn, f'{val:.0%}', ha='center', va='center',
                    fontsize=7, color='black' if val < 0.6 else 'white')

plt.suptitle('Script 19b: Q-Learner v2 Policy Heatmaps (Duration + Danger)\n'
             f'{len(episodes)} episodes, {N_STATES} states, '
             f'{MAX_LEVELS} levels',
             fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/19b_policy_heatmap.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUTPUT_DIR}/19b_policy_heatmap.png")


# ---- Chart 2: Training Curves + Four-Way Comparison -------------------------
fig, axes = plt.subplots(2, 2, figsize=(18, 14))

# Training reward curve
ax = axes[0, 0]
ax.plot(learner.episode_rewards, color='#3498db', linewidth=1.2)
ax.set_xlabel('Epoch')
ax.set_ylabel('Average Reward ($)')
ax.set_title('Q-Learning v2 Training: Average Reward per Epoch', fontweight='bold')
ax.grid(True, alpha=0.3)

# Epsilon decay
ax = axes[0, 1]
ax.plot(learner.epsilon_history, color='#e74c3c', linewidth=1.5)
ax.set_xlabel('Epoch')
ax.set_ylabel('Epsilon')
ax.set_title('Exploration Rate (Epsilon) Decay', fontweight='bold')
ax.grid(True, alpha=0.3)

# Bust rate comparison bar chart
ax = axes[1, 0]
strategies = ['Never-Abort', 'Q-v1 (proxy)', 'Q-v2 (new)', 'Thr L>=4']
bust_rates = [
    never_result['bust_rate'] * 100,
    v1_result['bust_rate'] * 100,
    q_v2_result['bust_rate'] * 100,
    thresh_result['bust_rate'] * 100,
]
colors = ['#e74c3c', '#f39c12', '#2ecc71', '#3498db']
bars = ax.bar(range(len(strategies)), bust_rates, color=colors,
              edgecolor='black', alpha=0.8)
ax.set_xticks(range(len(strategies)))
ax.set_xticklabels(strategies, rotation=15, ha='right', fontsize=10)
ax.set_ylabel('Bust Rate (%)')
ax.set_title('Bust Rate Comparison (4-way)', fontweight='bold')
for bar, rate in zip(bars, bust_rates):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
            f'{rate:.2f}%', ha='center', fontsize=9, fontweight='bold')
ax.grid(True, alpha=0.3, axis='y')

# P&L comparison
ax = axes[1, 1]
pnls = [
    never_result['total_pnl'],
    v1_result['total_pnl'],
    q_v2_result['total_pnl'],
    thresh_result['total_pnl'],
]
pnl_colors = ['#27ae60' if p > 0 else '#e74c3c' for p in pnls]
bars = ax.bar(range(len(strategies)), pnls, color=pnl_colors,
              edgecolor='black', alpha=0.8)
ax.set_xticks(range(len(strategies)))
ax.set_xticklabels(strategies, rotation=15, ha='right', fontsize=10)
ax.set_ylabel('Total P&L ($)')
ax.set_title('Total P&L Comparison (4-way)', fontweight='bold')
ax.axhline(y=0, color='black', linewidth=0.5)
for bar, pnl in zip(bars, pnls):
    y_off = 50 if pnl >= 0 else -100
    ax.text(bar.get_x() + bar.get_width()/2, pnl + y_off,
            f'${pnl:,.0f}', ha='center', fontsize=8)
ax.grid(True, alpha=0.3, axis='y')

plt.suptitle('Script 19b: Q-Learner v2 vs Baselines\n'
             f'{len(episodes)} episodes, {MAX_LEVELS} levels',
             fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/19b_comparison.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/19b_comparison.png")


# ---- Chart 3: Equity Curves -------------------------------------------------
fig, ax = plt.subplots(figsize=(16, 8))

# Never-abort equity
cum_pnl_nva = np.cumsum(never_result['cycle_pnls'])
ax.plot(range(len(cum_pnl_nva)), cum_pnl_nva,
        label='Never-Abort', color='#e74c3c', linewidth=1.0, alpha=0.6)

# Q-v1 proxy equity
cum_pnl_v1 = np.cumsum(v1_result['cycle_pnls'])
ax.plot(range(len(cum_pnl_v1)), cum_pnl_v1,
        label='Q-v1 (proxy: abort L6,9,10,11)', color='#f39c12',
        linewidth=1.0, alpha=0.7, linestyle='--')

# Q-v2 equity
cum_pnl_v2 = np.cumsum(q_v2_result['cycle_pnls'])
ax.plot(range(len(cum_pnl_v2)), cum_pnl_v2,
        label='Q-v2 (duration+danger)', color='#2ecc71', linewidth=1.8)

# Threshold equity
cum_pnl_thr = np.cumsum(thresh_result['cycle_pnls'])
ax.plot(range(len(cum_pnl_thr)), cum_pnl_thr,
        label='Threshold L>=4', color='#3498db',
        linewidth=1.0, alpha=0.7, linestyle=':')

ax.axhline(y=0, color='black', linewidth=0.5, linestyle=':')
ax.set_xlabel('Cycle #')
ax.set_ylabel('Cumulative P&L ($)')
ax.set_title('Equity Curves: 4-Way Abort Strategy Comparison', fontweight='bold',
             fontsize=14)
ax.legend(fontsize=11)
ax.grid(True, alpha=0.3)

plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/19b_equity_curves.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/19b_equity_curves.png")


# ---- Chart 4: Walk-Forward Results ------------------------------------------
if len(wf_results) > 0:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    seg_ids = [r['test_idx'] for r in wf_results]
    x = np.arange(len(seg_ids))
    width = 0.2

    ax = axes[0]
    nva_busts = [r['never_abort']['bust_rate'] * 100 for r in wf_results]
    v1_busts = [r['q_learner_v1']['bust_rate'] * 100 for r in wf_results]
    v2_busts = [r['q_learner_v2']['bust_rate'] * 100 for r in wf_results]
    thr_busts = [r['threshold_abort']['bust_rate'] * 100 for r in wf_results]

    ax.bar(x - 1.5*width, nva_busts, width, label='Never-Abort',
           color='#e74c3c', alpha=0.7, edgecolor='black')
    ax.bar(x - 0.5*width, v1_busts, width, label='Q-v1 (proxy)',
           color='#f39c12', alpha=0.7, edgecolor='black')
    ax.bar(x + 0.5*width, v2_busts, width, label='Q-v2 (new)',
           color='#2ecc71', alpha=0.7, edgecolor='black')
    ax.bar(x + 1.5*width, thr_busts, width, label='Threshold L>=4',
           color='#3498db', alpha=0.7, edgecolor='black')
    ax.set_xlabel('Test Segment')
    ax.set_ylabel('Bust Rate (%)')
    ax.set_title('Walk-Forward: Bust Rate', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Seg {s}' for s in seg_ids])
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1]
    nva_pnls = [r['never_abort']['total_pnl'] for r in wf_results]
    v1_pnls = [r['q_learner_v1']['total_pnl'] for r in wf_results]
    v2_pnls = [r['q_learner_v2']['total_pnl'] for r in wf_results]
    thr_pnls = [r['threshold_abort']['total_pnl'] for r in wf_results]

    ax.bar(x - 1.5*width, nva_pnls, width, label='Never-Abort',
           color='#e74c3c', alpha=0.7, edgecolor='black')
    ax.bar(x - 0.5*width, v1_pnls, width, label='Q-v1 (proxy)',
           color='#f39c12', alpha=0.7, edgecolor='black')
    ax.bar(x + 0.5*width, v2_pnls, width, label='Q-v2 (new)',
           color='#2ecc71', alpha=0.7, edgecolor='black')
    ax.bar(x + 1.5*width, thr_pnls, width, label='Threshold L>=4',
           color='#3498db', alpha=0.7, edgecolor='black')
    ax.set_xlabel('Test Segment')
    ax.set_ylabel('P&L ($)')
    ax.set_title('Walk-Forward: P&L', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Seg {s}' for s in seg_ids])
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')

    plt.suptitle('Script 19b: Walk-Forward 4-Way Comparison',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    fig.savefig(f'{OUTPUT_DIR}/19b_walk_forward.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {OUTPUT_DIR}/19b_walk_forward.png")


# ---- Chart 5: Duration-Danger Bust Rate Heatmap (empirical, not policy) -----
fig, ax = plt.subplots(figsize=(10, 6))

bust_rate_cross = np.full((N_DURATION_BINS, N_DANGER_LEVELS), np.nan)
for db in range(N_DURATION_BINS):
    for dl in range(N_DANGER_LEVELS):
        total = cross_tab[db, dl, 0]
        busts = cross_tab[db, dl, 1]
        if total >= 5:
            bust_rate_cross[db, dl] = busts / total * 100

im = ax.imshow(bust_rate_cross.T, aspect='auto', cmap='YlOrRd',
               vmin=0, origin='lower')
ax.set_xlabel('Duration Bin (bars elapsed)', fontsize=12)
ax.set_ylabel('Danger Level at Entry', fontsize=12)
ax.set_title('Empirical Bust Rate (%) by Duration x Danger at Entry',
             fontweight='bold', fontsize=13)
ax.set_xticks(range(N_DURATION_BINS))
ax.set_xticklabels(bin_labels_short)
ax.set_yticks(range(N_DANGER_LEVELS))
danger_labels_full = ['safe(<0.3)', 'mild(0.3-0.5)', 'caution(0.5-0.7)',
                      'warning(0.7-0.85)', 'danger(>0.85)']
ax.set_yticklabels(danger_labels_full, fontsize=9)
plt.colorbar(im, ax=ax, label='Bust Rate (%)')

for db in range(N_DURATION_BINS):
    for dl in range(N_DANGER_LEVELS):
        val = bust_rate_cross[db, dl]
        total = int(cross_tab[db, dl, 0])
        if not np.isnan(val):
            ax.text(db, dl, f'{val:.1f}%\n(n={total})', ha='center', va='center',
                    fontsize=8, fontweight='bold',
                    color='white' if val > 5 else 'black')
        elif total > 0:
            ax.text(db, dl, f'n={total}', ha='center', va='center',
                    fontsize=7, color='gray')

plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/19b_bust_rate_heatmap.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/19b_bust_rate_heatmap.png")


# =============================================================================
# SAVE OUTPUTS
# =============================================================================

# Save Q-table
np.save(os.path.join(DATA_DIR, 'q_table_v2.npy'), learner.Q)
np.save(os.path.join(DATA_DIR, 'q_visit_count_v2.npy'), learner.visit_count)
print(f"\nSaved: {DATA_DIR}/q_table_v2.npy")
print(f"Saved: {DATA_DIR}/q_visit_count_v2.npy")

# Save full learner state
learner_state = learner.get_state_dict()
with open(os.path.join(DATA_DIR, 'q_learner_v2_state.pkl'), 'wb') as f:
    pickle.dump(learner_state, f)
print(f"Saved: {DATA_DIR}/q_learner_v2_state.pkl")

# Save comparison metrics
comparison = {
    'never_abort': {k: v for k, v in never_result.items()
                    if k not in ('cycle_pnls', 'abort_durations', 'abort_dangers')},
    'q_learner_v1_proxy': {k: v for k, v in v1_result.items()
                           if k not in ('cycle_pnls', 'abort_durations', 'abort_dangers')},
    'q_learner_v2': {k: v for k, v in q_v2_result.items()
                     if k not in ('cycle_pnls', 'abort_durations', 'abort_dangers')},
    'threshold_results': {
        k: {kk: vv for kk, vv in v.items()
            if kk not in ('cycle_pnls', 'abort_durations', 'abort_dangers')}
        for k, v in threshold_results.items()
    },
    'walk_forward': wf_results,
    'state_space': {
        'n_states': N_STATES,
        'dimensions': '(level, duration_bin, danger_entry, danger_now)',
        'n_levels': N_LEVELS,
        'n_duration_bins': N_DURATION_BINS,
        'n_danger_levels': N_DANGER_LEVELS,
        'duration_bin_edges': DURATION_BIN_EDGES,
        'danger_thresholds': DANGER_THRESHOLDS,
    },
    'danger_weights': DANGER_WEIGHTS,
}
with open(os.path.join(DATA_DIR, 'abort_comparison_v2.pkl'), 'wb') as f:
    pickle.dump(comparison, f)
print(f"Saved: {DATA_DIR}/abort_comparison_v2.pkl")


# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("FINAL SUMMARY")
print("=" * 80)

print(f"""
  Surefire Config: {MAX_LEVELS} levels, sqrt(2) multiplier, 0.5% base
  Total Episodes: {len(episodes)}

  STATE SPACE (v2):
    Dimensions: (level, duration_bin, danger_entry, danger_now)
    Size: {N_STATES} states ({N_LEVELS} x {N_DURATION_BINS} x {N_DANGER_LEVELS} x {N_DANGER_LEVELS})
    Duration bins: {bin_labels_short}
    Danger levels: safe(<0.3), mild(0.3-0.5), caution(0.5-0.7), warning(0.7-0.85), danger(>0.85)

  Danger scorer weights:
    D1_range_atr(inv): 0.30, 5m_chop: 0.15, 15m_chop: 0.15, D1_chop: 0.10
    5m_adx(inv): 0.10, 5m_hurst(inv): 0.10, 1H_atr_ratio: 0.10

  FOUR-WAY COMPARISON:
                              Bust%    Abort%   Total P&L
  Never-Abort:              {never_result['bust_rate']*100:>6.2f}%   {never_result['abort_rate']*100:>5.2f}%   ${never_result['total_pnl']:>10,.2f}
  Q-v1 (proxy, L6/9/10/11): {v1_result['bust_rate']*100:>6.2f}%   {v1_result['abort_rate']*100:>5.2f}%   ${v1_result['total_pnl']:>10,.2f}
  Q-v2 (duration+danger):  {q_v2_result['bust_rate']*100:>6.2f}%   {q_v2_result['abort_rate']*100:>5.2f}%   ${q_v2_result['total_pnl']:>10,.2f}
  Threshold (L>=4):         {thresh_result['bust_rate']*100:>6.2f}%   {thresh_result['abort_rate']*100:>5.2f}%   ${thresh_result['total_pnl']:>10,.2f}

  Q-v2 aborts at levels: {np.unique(q_v2_result['abort_levels']).tolist() if q_v2_result['abort_levels'] else 'none'}

  Walk-forward:
    Q-v2 beats never-abort on bust rate: {n_v2_beats_nva}/{len(wf_results)} segments
    Q-v2 beats Q-v1(proxy) on bust rate: {n_v2_beats_v1}/{len(wf_results)} segments
    Q-v2 beats threshold on P&L:         {n_v2_beats_thr}/{len(wf_results)} segments

  KEY INSIGHT: Duration is the strongest mid-cycle signal for bust prediction.
  Cycles lasting >20 bars have dramatically higher bust rates. By incorporating
  duration bins + composite danger score into the state space (instead of HMM
  regime states), the Q-learner can make more targeted abort decisions --
  aborting only when BOTH duration is extended AND danger is elevated.
""")

print("FILES SAVED:")
print(f"  {OUTPUT_DIR}/19b_policy_heatmap.png")
print(f"  {OUTPUT_DIR}/19b_comparison.png")
print(f"  {OUTPUT_DIR}/19b_equity_curves.png")
print(f"  {OUTPUT_DIR}/19b_walk_forward.png")
print(f"  {OUTPUT_DIR}/19b_bust_rate_heatmap.png")
print(f"  {DATA_DIR}/q_table_v2.npy")
print(f"  {DATA_DIR}/q_visit_count_v2.npy")
print(f"  {DATA_DIR}/q_learner_v2_state.pkl")
print(f"  {DATA_DIR}/abort_comparison_v2.pkl")
print("=" * 80)
