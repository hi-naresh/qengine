#!/usr/bin/env python3
"""
Script 18: Contextual Bandit for Entry Decisions (Thompson Sampling)
====================================================================
Online learning agent that decides trade/skip per cycle based on regime.
Uses Thompson Sampling with Beta posteriors and asymmetric bust penalty.

Dependencies: Phase A feature matrix, Phase B regime labels + HMM model.
If those files don't exist yet, generates synthetic regime/cycle data
from the real price simulation for development purposes.

Surefire parameters: 12 levels, sqrt(2) multiplier, 0.5% base.
"""

import os, sys, pickle, time
os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timezone
from collections import defaultdict

import qengine.indicators as ta
import qengine.helpers as jh
from qengine.research import get_candles

# ---- Paths ----------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, 'data')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---- Surefire Parameters ---------------------------------------------------
MAX_LEVELS = 12
MULTIPLIER = np.sqrt(2)
BASE_PCT = 0.005          # 0.5% base position
TP_ATR_MULTIPLE = 0.8
RISK_REWARD = 2.0
ATR_PERIOD = 14
PIP_SIZE = 0.0001
BASE_SIZE = 0.1           # lots
PIP_VALUE = 10.0          # USD per pip per standard lot
MAX_BARS_PER_LEVEL = 500
EMA_FAST = 8
EMA_SLOW = 21

N_REGIMES = 5             # default regime count (overridden if HMM model exists)
BUST_PENALTY_MULTIPLIER = 10  # bust updates beta by this much (asymmetric)
CONFIDENCE_THRESHOLD = 0.5
TRADE_THRESHOLD = 0.4

STARTING_BALANCE = 10_000

# =============================================================================
# Part 1: Load or Generate Cycle Data with Regime Labels
# =============================================================================

def load_price_data():
    """Load EUR-USD 5m candles."""
    print("Loading EUR-USD 5m candles from OANDA...")
    t0 = time.time()
    warmup_candles, candles = get_candles('OANDA', 'EUR-USD', '5m',
        jh.date_to_timestamp('2006-01-02'), jh.date_to_timestamp('2025-12-31'),
        warmup_candles_num=210)
    if warmup_candles is not None and warmup_candles.ndim == 2 and len(warmup_candles) > 0:
        candles = np.concatenate([warmup_candles, candles], axis=0)
    print(f"Total candles: {len(candles):,} ({time.time()-t0:.1f}s)")
    return candles


def compute_indicators(candles):
    """Compute EMA, ATR, and regime-proxy indicators."""
    ema_fast = ta.ema(candles, period=EMA_FAST, sequential=True)
    ema_slow = ta.ema(candles, period=EMA_SLOW, sequential=True)
    atr_arr = ta.atr(candles, period=ATR_PERIOD, sequential=True)
    adx_arr = ta.adx(candles, period=ATR_PERIOD, sequential=True)
    return ema_fast, ema_slow, atr_arr, adx_arr


def find_crossover_signals(ema_fast, ema_slow, atr_arr, candles):
    """Find EMA crossover entry signals."""
    min_start = max(ATR_PERIOD + 5, EMA_SLOW + 5)
    signals = []
    n = len(candles)
    for i in range(min_start, n - MAX_BARS_PER_LEVEL):
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
    return signals


def simulate_level(entry_price, direction, tp_dist, hedge_dist, start_bar,
                   highs, lows):
    """Simulate one level of the hedge from start_bar."""
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


def simulate_full_cycle(entry_bar, initial_direction, candles, atr_arr):
    """Simulate a complete surefire hedge cycle with sqrt(2) multiplier."""
    closes = candles[:, 2]
    highs = candles[:, 3]
    lows = candles[:, 4]

    entry_price = closes[entry_bar]
    direction = initial_direction
    current_bar = entry_bar + 1
    total_pnl = 0.0
    level_pnls = []

    for level in range(MAX_LEVELS):
        current_atr = atr_arr[min(current_bar, len(atr_arr)-1)]
        if np.isnan(current_atr) or current_atr <= 0:
            current_atr = atr_arr[entry_bar]
        if np.isnan(current_atr) or current_atr <= 0:
            return None

        tp_dist = current_atr * TP_ATR_MULTIPLE
        hedge_dist = tp_dist / RISK_REWARD
        size = BASE_SIZE * (MULTIPLIER ** level)
        tp_pips = tp_dist / PIP_SIZE
        sl_pips = hedge_dist / PIP_SIZE

        result = simulate_level(entry_price, direction, tp_dist, hedge_dist,
                                current_bar, highs, lows)

        if result[0] == 'tp':
            profit = tp_pips * PIP_VALUE * size
            total_pnl += profit
            level_pnls.append(profit)
            return {
                'outcome': 'win', 'win_level': level, 'total_pnl': total_pnl,
                'entry_bar': entry_bar, 'end_bar': result[1],
                'level_pnls': level_pnls,
            }
        elif result[0] == 'sl':
            loss = sl_pips * PIP_VALUE * size
            total_pnl -= loss
            level_pnls.append(-loss)
            entry_price = result[2]
            direction = 'short' if direction == 'long' else 'long'
            current_bar = result[1] + 1
            if current_bar >= len(highs):
                return None
        elif result[0] == 'timeout':
            return None

    # All levels exhausted -> bust
    return {
        'outcome': 'bust', 'win_level': -1, 'total_pnl': total_pnl,
        'entry_bar': entry_bar, 'end_bar': current_bar,
        'level_pnls': level_pnls,
    }


def assign_regime_from_features(adx_arr, atr_arr, entry_bar, n_regimes=5):
    """
    Simple regime assignment from ADX + ATR volatility percentile.
    Used as fallback when Phase B HMM model is not available.
    """
    adx_val = adx_arr[entry_bar] if not np.isnan(adx_arr[entry_bar]) else 25.0

    # ATR percentile over trailing 1000 bars
    start = max(0, entry_bar - 1000)
    window = atr_arr[start:entry_bar+1]
    window = window[~np.isnan(window)]
    if len(window) < 50:
        atr_pctile = 50.0
    else:
        atr_pctile = (np.sum(window < atr_arr[entry_bar]) / len(window)) * 100.0

    # Map to regime: 2D grid (ADX low/med/high vs ATR low/high)
    # This gives a rough 5-regime partition
    if adx_val < 20:
        adx_bin = 0  # ranging
    elif adx_val < 35:
        adx_bin = 1  # mild trend
    else:
        adx_bin = 2  # strong trend

    atr_bin = 0 if atr_pctile < 50 else 1  # low vs high vol

    # Map to 0..4 regime
    regime_map = {
        (0, 0): 0,  # ranging + low vol (choppy)
        (0, 1): 1,  # ranging + high vol (volatile chop)
        (1, 0): 2,  # mild trend + low vol
        (1, 1): 3,  # mild trend + high vol
        (2, 0): 4,  # strong trend + low vol
        (2, 1): 4,  # strong trend + high vol (merge)
    }
    regime = regime_map.get((adx_bin, atr_bin), 2)
    confidence = 0.7  # placeholder confidence
    return regime, confidence


def build_cycle_dataset():
    """Build cycles with regime labels from real price data."""
    candles = load_price_data()
    ema_fast, ema_slow, atr_arr, adx_arr = compute_indicators(candles)
    signals = find_crossover_signals(ema_fast, ema_slow, atr_arr, candles)
    print(f"Total signals: {len(signals):,}")

    # Try loading Phase B regime data
    regime_labels_path = os.path.join(DATA_DIR, 'regime_labels.npy')
    hmm_model_path = os.path.join(DATA_DIR, 'hmm_model.pkl')
    use_hmm = os.path.exists(regime_labels_path) and os.path.exists(hmm_model_path)

    if use_hmm:
        print("Loading Phase B HMM regime labels...")
        regime_labels = np.load(regime_labels_path)
        with open(hmm_model_path, 'rb') as f:
            hmm_data = pickle.load(f)
        print(f"Loaded regime labels: {len(regime_labels)} entries")
    else:
        print("Phase B data not found. Using ADX/ATR-based regime proxy.")

    # Simulate cycles
    cycles = []
    next_allowed = 0
    for sig_bar, sig_dir in signals:
        if sig_bar < next_allowed:
            continue

        result = simulate_full_cycle(sig_bar, sig_dir, candles, atr_arr)
        if result is None:
            continue

        # Assign regime
        if use_hmm and sig_bar < len(regime_labels):
            regime = int(regime_labels[sig_bar])
            confidence = 0.8  # default confidence from HMM
        else:
            regime, confidence = assign_regime_from_features(
                adx_arr, atr_arr, sig_bar)

        result['regime'] = regime
        result['confidence'] = confidence
        result['timestamp'] = candles[sig_bar, 0]
        cycles.append(result)
        next_allowed = result['end_bar'] + 1

    print(f"Simulated {len(cycles)} complete cycles")
    print(f"  Wins: {sum(1 for c in cycles if c['outcome']=='win')}")
    print(f"  Busts: {sum(1 for c in cycles if c['outcome']=='bust')}")

    # Report regime distribution
    regimes = np.array([c['regime'] for c in cycles])
    for r in sorted(np.unique(regimes)):
        mask = regimes == r
        n_cycles = mask.sum()
        n_busts = sum(1 for c in cycles if c['regime'] == r and c['outcome'] == 'bust')
        p_bust = n_busts / n_cycles if n_cycles > 0 else 0
        print(f"  Regime {r}: {n_cycles} cycles, {n_busts} busts, P(bust)={p_bust:.4f}")

    return cycles, candles


# =============================================================================
# Part 2: EntryBandit Class (Thompson Sampling)
# =============================================================================

class EntryBandit:
    """
    Contextual bandit for trade/skip decision using Thompson Sampling.

    Context = regime ID. Actions = {trade, skip}.
    Reward = cycle P&L outcome (win > 0 or bust < 0).

    Uses Beta distribution per regime:
      alpha = successes + 1 (prior)
      beta = failures + 1 (prior)

    Bust events get asymmetric penalty: beta incremented by
    BUST_PENALTY_MULTIPLIER instead of 1.
    """

    def __init__(self, n_regimes, bust_penalty=BUST_PENALTY_MULTIPLIER,
                 confidence_threshold=CONFIDENCE_THRESHOLD,
                 trade_threshold=TRADE_THRESHOLD):
        self.n_regimes = n_regimes
        self.bust_penalty = bust_penalty
        self.confidence_threshold = confidence_threshold
        self.trade_threshold = trade_threshold

        # Beta(1,1) = Uniform prior per regime
        self.alpha = np.ones(n_regimes)
        self.beta_param = np.ones(n_regimes)

        # Tracking
        self.history = []  # list of (regime, traded, outcome, alpha_snap, beta_snap)
        self.n_trades = np.zeros(n_regimes, dtype=int)
        self.n_skips = np.zeros(n_regimes, dtype=int)
        self.n_wins = np.zeros(n_regimes, dtype=int)
        self.n_busts = np.zeros(n_regimes, dtype=int)

    def should_trade(self, regime, confidence):
        """
        Thompson Sampling decision.

        1. If regime confidence < threshold, skip (too uncertain).
        2. Sample from Beta(alpha[regime], beta[regime]).
        3. Trade if sampled p_success > trade_threshold.
        """
        if confidence < self.confidence_threshold:
            return False

        regime = min(regime, self.n_regimes - 1)
        p_success = np.random.beta(self.alpha[regime], self.beta_param[regime])
        return p_success > self.trade_threshold

    def get_posterior_mean(self, regime):
        """E[p_success] = alpha / (alpha + beta)."""
        regime = min(regime, self.n_regimes - 1)
        return self.alpha[regime] / (self.alpha[regime] + self.beta_param[regime])

    def update(self, regime, traded, outcome_pnl):
        """
        Update posterior after cycle completes.

        - If not traded: no update (no information from skipping).
        - If traded and won: alpha[regime] += 1
        - If traded and bust: beta[regime] += bust_penalty (asymmetric)
        - If traded and lost (not bust): beta[regime] += 1
        """
        regime = min(regime, self.n_regimes - 1)

        self.history.append((
            regime, traded, outcome_pnl,
            self.alpha.copy(), self.beta_param.copy()
        ))

        if not traded:
            self.n_skips[regime] += 1
            return

        self.n_trades[regime] += 1

        if outcome_pnl > 0:
            self.alpha[regime] += 1
            self.n_wins[regime] += 1
        else:
            # Check if bust (large negative PnL) vs small loss
            # Bust is when total_pnl is very negative (all 12 levels lost)
            is_bust = outcome_pnl < -500  # heuristic threshold
            if is_bust:
                self.beta_param[regime] += self.bust_penalty
                self.n_busts[regime] += 1
            else:
                self.beta_param[regime] += 1

    def get_state(self):
        """Return serializable state."""
        return {
            'alpha': self.alpha.copy(),
            'beta_param': self.beta_param.copy(),
            'n_trades': self.n_trades.copy(),
            'n_skips': self.n_skips.copy(),
            'n_wins': self.n_wins.copy(),
            'n_busts': self.n_busts.copy(),
            'n_regimes': self.n_regimes,
            'bust_penalty': self.bust_penalty,
            'confidence_threshold': self.confidence_threshold,
            'trade_threshold': self.trade_threshold,
        }

    def reset(self):
        """Reset to uniform prior."""
        self.alpha = np.ones(self.n_regimes)
        self.beta_param = np.ones(self.n_regimes)
        self.history = []
        self.n_trades = np.zeros(self.n_regimes, dtype=int)
        self.n_skips = np.zeros(self.n_regimes, dtype=int)
        self.n_wins = np.zeros(self.n_regimes, dtype=int)
        self.n_busts = np.zeros(self.n_regimes, dtype=int)


# =============================================================================
# Part 3: Online Simulation (Chronological, No Lookahead)
# =============================================================================

def run_online_simulation(cycles, n_regimes, label="Bandit"):
    """
    Process cycles chronologically. For each cycle:
    1. Get regime -> bandit decides trade/skip
    2. If traded, observe outcome -> update bandit
    3. Track all metrics.

    Returns bandit and results dict.
    """
    bandit = EntryBandit(n_regimes=n_regimes)

    traded_cycles = []
    skipped_cycles = []
    cumulative_pnl = []
    running_pnl = 0.0
    belief_snapshots = []  # (cycle_idx, alpha_copy, beta_copy)

    for i, cycle in enumerate(cycles):
        regime = cycle['regime']
        confidence = cycle['confidence']

        # Bandit decision
        trade = bandit.should_trade(regime, confidence)

        if trade:
            # Execute the trade, observe outcome
            pnl = cycle['total_pnl']
            bandit.update(regime, traded=True, outcome_pnl=pnl)
            running_pnl += pnl
            traded_cycles.append(cycle)
        else:
            bandit.update(regime, traded=False, outcome_pnl=0)
            skipped_cycles.append(cycle)

        cumulative_pnl.append(running_pnl)

        # Snapshot beliefs periodically
        if i % 20 == 0 or i == len(cycles) - 1:
            belief_snapshots.append((
                i, bandit.alpha.copy(), bandit.beta_param.copy()
            ))

    # Compute metrics
    n_traded = len(traded_cycles)
    n_skipped = len(skipped_cycles)
    n_total = len(cycles)
    n_busts_traded = sum(1 for c in traded_cycles if c['outcome'] == 'bust')
    n_wins_traded = sum(1 for c in traded_cycles if c['outcome'] == 'win')
    bust_rate = n_busts_traded / n_traded if n_traded > 0 else 0

    # Baseline: what if we traded everything?
    n_busts_all = sum(1 for c in cycles if c['outcome'] == 'bust')
    bust_rate_all = n_busts_all / n_total if n_total > 0 else 0
    pnl_all = sum(c['total_pnl'] for c in cycles)

    # Busts that were skipped (good skips)
    busts_skipped = sum(1 for c in skipped_cycles if c['outcome'] == 'bust')
    wins_skipped = sum(1 for c in skipped_cycles if c['outcome'] == 'win')

    results = {
        'label': label,
        'n_total': n_total,
        'n_traded': n_traded,
        'n_skipped': n_skipped,
        'skip_rate': n_skipped / n_total if n_total > 0 else 0,
        'n_busts_traded': n_busts_traded,
        'n_wins_traded': n_wins_traded,
        'bust_rate_traded': bust_rate,
        'bust_rate_all': bust_rate_all,
        'busts_skipped': busts_skipped,
        'wins_skipped': wins_skipped,
        'pnl_traded': running_pnl,
        'pnl_all': pnl_all,
        'cumulative_pnl': np.array(cumulative_pnl),
        'belief_snapshots': belief_snapshots,
        'bandit_state': bandit.get_state(),
    }

    return bandit, results


def run_always_trade_baseline(cycles):
    """Baseline: trade every cycle, no filtering."""
    n_total = len(cycles)
    n_busts = sum(1 for c in cycles if c['outcome'] == 'bust')
    n_wins = sum(1 for c in cycles if c['outcome'] == 'win')
    pnl = sum(c['total_pnl'] for c in cycles)
    cum_pnl = np.cumsum([c['total_pnl'] for c in cycles])

    return {
        'label': 'Always-Trade Baseline',
        'n_total': n_total,
        'n_traded': n_total,
        'n_skipped': 0,
        'skip_rate': 0.0,
        'n_busts_traded': n_busts,
        'n_wins_traded': n_wins,
        'bust_rate_traded': n_busts / n_total if n_total > 0 else 0,
        'bust_rate_all': n_busts / n_total if n_total > 0 else 0,
        'busts_skipped': 0,
        'wins_skipped': 0,
        'pnl_traded': pnl,
        'pnl_all': pnl,
        'cumulative_pnl': cum_pnl,
    }


# =============================================================================
# Part 4: Walk-Forward Evaluation
# =============================================================================

def walk_forward_evaluation(cycles, n_regimes):
    """
    Walk-forward: expanding training window, test on next segment.
    Split cycles into segments by timestamp.
    """
    timestamps = np.array([c['timestamp'] for c in cycles])
    ts_min = timestamps.min()
    ts_max = timestamps.max()

    # Split into yearly-ish segments (or quarterly if data is short)
    total_duration = ts_max - ts_min
    segment_duration = total_duration / 4  # 4 segments for ~2 years of data

    boundaries = [ts_min + i * segment_duration for i in range(5)]
    segments = []
    for i in range(4):
        seg = [c for c in cycles if boundaries[i] <= c['timestamp'] < boundaries[i+1]]
        segments.append(seg)

    print(f"\nWalk-Forward: {len(segments)} segments")
    for i, seg in enumerate(segments):
        n_busts = sum(1 for c in seg if c['outcome'] == 'bust')
        print(f"  Segment {i}: {len(seg)} cycles, {n_busts} busts")

    # Walk-forward: train on segments 0..i, test on segment i+1
    wf_results = []
    for test_idx in range(1, len(segments)):
        train_cycles = []
        for j in range(test_idx):
            train_cycles.extend(segments[j])
        test_cycles = segments[test_idx]

        if len(test_cycles) < 5:
            continue

        # Train bandit on training data
        bandit = EntryBandit(n_regimes=n_regimes)
        for c in train_cycles:
            regime = c['regime']
            confidence = c['confidence']
            trade = bandit.should_trade(regime, confidence)
            if trade:
                bandit.update(regime, traded=True, outcome_pnl=c['total_pnl'])
            else:
                bandit.update(regime, traded=False, outcome_pnl=0)

        # Test: use learned bandit (no more exploration updates)
        test_traded = []
        test_skipped = []
        test_pnl = 0.0

        for c in test_cycles:
            regime = c['regime']
            confidence = c['confidence']
            trade = bandit.should_trade(regime, confidence)
            if trade:
                test_pnl += c['total_pnl']
                test_traded.append(c)
            else:
                test_skipped.append(c)

        n_test = len(test_cycles)
        n_traded = len(test_traded)
        n_busts_traded = sum(1 for c in test_traded if c['outcome'] == 'bust')
        n_busts_all = sum(1 for c in test_cycles if c['outcome'] == 'bust')
        busts_skipped = sum(1 for c in test_skipped if c['outcome'] == 'bust')

        baseline_pnl = sum(c['total_pnl'] for c in test_cycles)

        wf_results.append({
            'test_idx': test_idx,
            'n_train': len(train_cycles),
            'n_test': n_test,
            'n_traded': n_traded,
            'n_skipped': n_test - n_traded,
            'skip_rate': (n_test - n_traded) / n_test if n_test > 0 else 0,
            'bust_rate_bandit': n_busts_traded / n_traded if n_traded > 0 else 0,
            'bust_rate_baseline': n_busts_all / n_test if n_test > 0 else 0,
            'busts_skipped': busts_skipped,
            'pnl_bandit': test_pnl,
            'pnl_baseline': baseline_pnl,
        })

    return wf_results


# =============================================================================
# Part 5: Multiple Bandit Runs (Averaging Over Stochastic Decisions)
# =============================================================================

def run_multiple_simulations(cycles, n_regimes, n_runs=20):
    """Run the bandit simulation multiple times to average out randomness."""
    all_results = []
    for run in range(n_runs):
        np.random.seed(run * 42 + 7)
        _, result = run_online_simulation(cycles, n_regimes, label=f"Run {run}")
        all_results.append(result)

    # Aggregate
    bust_rates = [r['bust_rate_traded'] for r in all_results]
    pnls = [r['pnl_traded'] for r in all_results]
    skip_rates = [r['skip_rate'] for r in all_results]
    busts_skipped = [r['busts_skipped'] for r in all_results]

    return {
        'bust_rate_mean': np.mean(bust_rates),
        'bust_rate_std': np.std(bust_rates),
        'pnl_mean': np.mean(pnls),
        'pnl_std': np.std(pnls),
        'skip_rate_mean': np.mean(skip_rates),
        'skip_rate_std': np.std(skip_rates),
        'busts_skipped_mean': np.mean(busts_skipped),
        'busts_skipped_std': np.std(busts_skipped),
        'all_results': all_results,
    }


# =============================================================================
# MAIN EXECUTION
# =============================================================================

print("=" * 80)
print("  SCRIPT 18: Contextual Bandit for Entry Decisions (Thompson Sampling)")
print("=" * 80)

# ---- Build dataset ---------------------------------------------------------
cycles, candles = build_cycle_dataset()
regimes = np.array([c['regime'] for c in cycles])
n_regimes = max(regimes) + 1
print(f"\nUsing {n_regimes} regimes")

# ---- Baseline --------------------------------------------------------------
print("\n" + "=" * 80)
print("BASELINE: Always-Trade")
print("=" * 80)
baseline = run_always_trade_baseline(cycles)
print(f"  Total cycles: {baseline['n_total']}")
print(f"  Busts: {baseline['n_busts_traded']} ({baseline['bust_rate_traded']*100:.2f}%)")
print(f"  Net P&L: ${baseline['pnl_traded']:,.2f}")

# ---- Online Bandit Simulation (single run) ----------------------------------
print("\n" + "=" * 80)
print("ONLINE BANDIT SIMULATION (single run)")
print("=" * 80)
np.random.seed(42)
bandit, bandit_result = run_online_simulation(cycles, n_regimes)

print(f"  Total cycles: {bandit_result['n_total']}")
print(f"  Traded: {bandit_result['n_traded']} ({(1-bandit_result['skip_rate'])*100:.1f}%)")
print(f"  Skipped: {bandit_result['n_skipped']} ({bandit_result['skip_rate']*100:.1f}%)")
print(f"  Busts (traded): {bandit_result['n_busts_traded']} "
      f"({bandit_result['bust_rate_traded']*100:.2f}%)")
print(f"  Busts (all): {baseline['n_busts_traded']} "
      f"({baseline['bust_rate_traded']*100:.2f}%)")
print(f"  Busts skipped: {bandit_result['busts_skipped']}")
print(f"  Wins skipped: {bandit_result['wins_skipped']}")
print(f"  P&L (bandit): ${bandit_result['pnl_traded']:,.2f}")
print(f"  P&L (baseline): ${baseline['pnl_traded']:,.2f}")

# Per-regime bandit beliefs
print("\n  --- Final Bandit Beliefs ---")
print(f"  {'Regime':<10} {'Alpha':<10} {'Beta':<10} {'E[p_win]':<10} "
      f"{'Trades':<10} {'Busts':<10}")
for r in range(n_regimes):
    a = bandit.alpha[r]
    b = bandit.beta_param[r]
    mean = a / (a + b)
    print(f"  {r:<10} {a:<10.1f} {b:<10.1f} {mean:<10.4f} "
          f"{bandit.n_trades[r]:<10} {bandit.n_busts[r]:<10}")

# ---- Multiple Runs (Average Over Stochasticity) ----------------------------
print("\n" + "=" * 80)
print("MULTI-RUN ANALYSIS (20 runs, averaging stochastic decisions)")
print("=" * 80)
multi_results = run_multiple_simulations(cycles, n_regimes, n_runs=20)
print(f"  Bust rate: {multi_results['bust_rate_mean']*100:.2f}% "
      f"(+/- {multi_results['bust_rate_std']*100:.2f}%)")
print(f"  P&L: ${multi_results['pnl_mean']:,.2f} "
      f"(+/- ${multi_results['pnl_std']:,.2f})")
print(f"  Skip rate: {multi_results['skip_rate_mean']*100:.1f}% "
      f"(+/- {multi_results['skip_rate_std']*100:.1f}%)")
print(f"  Busts skipped: {multi_results['busts_skipped_mean']:.1f} "
      f"(+/- {multi_results['busts_skipped_std']:.1f})")
print(f"\n  Baseline bust rate: {baseline['bust_rate_traded']*100:.2f}%")
print(f"  Baseline P&L: ${baseline['pnl_traded']:,.2f}")

bust_reduction = (1 - multi_results['bust_rate_mean'] / baseline['bust_rate_traded']) * 100 \
    if baseline['bust_rate_traded'] > 0 else 0
print(f"\n  Bust rate reduction: {bust_reduction:.1f}%")

# ---- Walk-Forward Evaluation -----------------------------------------------
print("\n" + "=" * 80)
print("WALK-FORWARD EVALUATION")
print("=" * 80)
np.random.seed(42)
wf_results = walk_forward_evaluation(cycles, n_regimes)

print(f"\n  {'Segment':<10} {'Train':<8} {'Test':<8} {'Traded':<8} {'Skip%':<8} "
      f"{'Bust%(B)':<10} {'Bust%(BL)':<10} {'BustsSkip':<10} "
      f"{'PnL(B)':<12} {'PnL(BL)':<12}")
print(f"  {'-'*100}")
for r in wf_results:
    print(f"  {r['test_idx']:<10} {r['n_train']:<8} {r['n_test']:<8} "
          f"{r['n_traded']:<8} {r['skip_rate']*100:<8.1f} "
          f"{r['bust_rate_bandit']*100:<10.2f} {r['bust_rate_baseline']*100:<10.2f} "
          f"{r['busts_skipped']:<10} "
          f"${r['pnl_bandit']:<11,.2f} ${r['pnl_baseline']:<11,.2f}")

# Count how many segments bandit beats baseline on bust rate
n_better_bust = sum(1 for r in wf_results
                    if r['bust_rate_bandit'] < r['bust_rate_baseline'])
n_better_pnl = sum(1 for r in wf_results
                    if r['pnl_bandit'] > r['pnl_baseline'])
print(f"\n  Bandit beats baseline on bust rate in {n_better_bust}/{len(wf_results)} segments")
print(f"  Bandit beats baseline on P&L in {n_better_pnl}/{len(wf_results)} segments")


# =============================================================================
# CHARTS
# =============================================================================
plt.style.use('seaborn-v0_8-darkgrid')

# ---- Chart 1: Equity Curves (Bandit vs Baseline) ---------------------------
fig, axes = plt.subplots(2, 2, figsize=(18, 14))

ax = axes[0, 0]
cum_pnl_baseline = baseline['cumulative_pnl']
cum_pnl_bandit = bandit_result['cumulative_pnl']

ax.plot(range(len(cum_pnl_baseline)), cum_pnl_baseline,
        label='Always-Trade Baseline', color='#3498db', linewidth=1.2, alpha=0.8)
ax.plot(range(len(cum_pnl_bandit)), cum_pnl_bandit,
        label='Bandit (Thompson Sampling)', color='#e74c3c', linewidth=1.5)
ax.axhline(y=0, color='black', linewidth=0.5, linestyle=':')
ax.set_xlabel('Cycle #')
ax.set_ylabel('Cumulative P&L ($)')
ax.set_title('Equity Curve: Bandit vs Always-Trade', fontweight='bold')
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)

# ---- Chart 2: Bandit Belief Evolution Per Regime ----------------------------
ax = axes[0, 1]
snapshots = bandit_result['belief_snapshots']
cycle_idxs = [s[0] for s in snapshots]

for r in range(n_regimes):
    means = [s[1][r] / (s[1][r] + s[2][r]) for s in snapshots]
    ax.plot(cycle_idxs, means, label=f'Regime {r}', linewidth=1.5, marker='.')

ax.axhline(y=TRADE_THRESHOLD, color='red', linestyle='--', alpha=0.5,
           label=f'Trade threshold ({TRADE_THRESHOLD})')
ax.set_xlabel('Cycle #')
ax.set_ylabel('E[P(success)] per Regime')
ax.set_title('Bandit Belief Evolution Over Time', fontweight='bold')
ax.legend(fontsize=8, loc='best')
ax.set_ylim(0, 1)
ax.grid(True, alpha=0.3)

# ---- Chart 3: Per-Regime Trade/Skip Breakdown ------------------------------
ax = axes[1, 0]
state = bandit_result['bandit_state']
regime_ids = np.arange(n_regimes)
width = 0.35

trades = state['n_trades']
skips = state['n_skips']
wins = state['n_wins']
busts = state['n_busts']

bars1 = ax.bar(regime_ids - width/2, trades, width, label='Traded',
               color='#2ecc71', edgecolor='black', linewidth=0.5)
bars2 = ax.bar(regime_ids + width/2, skips, width, label='Skipped',
               color='#e74c3c', edgecolor='black', linewidth=0.5)

# Annotate bust counts
for i in range(n_regimes):
    if busts[i] > 0:
        ax.text(i - width/2, trades[i] + 0.5, f'{int(busts[i])}B',
                ha='center', fontsize=8, color='red', fontweight='bold')

ax.set_xlabel('Regime')
ax.set_ylabel('Count')
ax.set_title('Trades vs Skips per Regime\n(red numbers = busts among traded)',
             fontweight='bold')
ax.set_xticks(regime_ids)
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3, axis='y')

# ---- Chart 4: Multi-Run Distribution ---------------------------------------
ax = axes[1, 1]
all_bust_rates = [r['bust_rate_traded'] * 100 for r in multi_results['all_results']]
all_pnls = [r['pnl_traded'] for r in multi_results['all_results']]

ax.hist(all_bust_rates, bins=15, color='#3498db', edgecolor='black',
        alpha=0.7, label='Bandit bust rate (20 runs)')
ax.axvline(x=baseline['bust_rate_traded'] * 100, color='red', linewidth=2,
           linestyle='--', label=f'Baseline: {baseline["bust_rate_traded"]*100:.2f}%')
ax.axvline(x=np.mean(all_bust_rates), color='blue', linewidth=2,
           linestyle='-', label=f'Bandit mean: {np.mean(all_bust_rates):.2f}%')
ax.set_xlabel('Bust Rate (%)')
ax.set_ylabel('Frequency')
ax.set_title('Bust Rate Distribution (20 Bandit Runs)', fontweight='bold')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

plt.suptitle('Script 18: Contextual Bandit for Entry Decisions\n'
             f'{len(cycles)} cycles, {n_regimes} regimes, '
             f'sqrt(2) multiplier, {MAX_LEVELS} levels',
             fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/18_entry_bandit.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUTPUT_DIR}/18_entry_bandit.png")


# ---- Chart 5: Walk-Forward Comparison --------------------------------------
if len(wf_results) > 0:
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    seg_ids = [r['test_idx'] for r in wf_results]

    ax = axes[0]
    bust_bandit = [r['bust_rate_bandit'] * 100 for r in wf_results]
    bust_baseline = [r['bust_rate_baseline'] * 100 for r in wf_results]
    x = np.arange(len(seg_ids))
    width = 0.35
    ax.bar(x - width/2, bust_baseline, width, label='Baseline',
           color='#e74c3c', alpha=0.7, edgecolor='black')
    ax.bar(x + width/2, bust_bandit, width, label='Bandit',
           color='#2ecc71', alpha=0.7, edgecolor='black')
    ax.set_xlabel('Test Segment')
    ax.set_ylabel('Bust Rate (%)')
    ax.set_title('Walk-Forward: Bust Rate Comparison', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Seg {s}' for s in seg_ids])
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1]
    pnl_bandit = [r['pnl_bandit'] for r in wf_results]
    pnl_baseline = [r['pnl_baseline'] for r in wf_results]
    ax.bar(x - width/2, pnl_baseline, width, label='Baseline',
           color='#e74c3c', alpha=0.7, edgecolor='black')
    ax.bar(x + width/2, pnl_bandit, width, label='Bandit',
           color='#2ecc71', alpha=0.7, edgecolor='black')
    ax.set_xlabel('Test Segment')
    ax.set_ylabel('P&L ($)')
    ax.set_title('Walk-Forward: P&L Comparison', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Seg {s}' for s in seg_ids])
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    fig.savefig(f'{OUTPUT_DIR}/18_walk_forward.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {OUTPUT_DIR}/18_walk_forward.png")


# =============================================================================
# SAVE OUTPUTS
# =============================================================================

# Save bandit state
bandit_state = bandit.get_state()
np.savez(
    os.path.join(DATA_DIR, 'bandit_state.npz'),
    alpha=bandit_state['alpha'],
    beta_param=bandit_state['beta_param'],
    n_trades=bandit_state['n_trades'],
    n_skips=bandit_state['n_skips'],
    n_wins=bandit_state['n_wins'],
    n_busts=bandit_state['n_busts'],
)
print(f"Saved: {DATA_DIR}/bandit_state.npz")

# Save comparison metrics
comparison = {
    'baseline_bust_rate': baseline['bust_rate_traded'],
    'baseline_pnl': baseline['pnl_traded'],
    'bandit_bust_rate_mean': multi_results['bust_rate_mean'],
    'bandit_bust_rate_std': multi_results['bust_rate_std'],
    'bandit_pnl_mean': multi_results['pnl_mean'],
    'bandit_pnl_std': multi_results['pnl_std'],
    'bandit_skip_rate_mean': multi_results['skip_rate_mean'],
    'bust_reduction_pct': bust_reduction,
    'walk_forward_results': wf_results,
}
with open(os.path.join(DATA_DIR, 'bandit_comparison.pkl'), 'wb') as f:
    pickle.dump(comparison, f)
print(f"Saved: {DATA_DIR}/bandit_comparison.pkl")

# Save learning curves
learning_data = {
    'cumulative_pnl_bandit': bandit_result['cumulative_pnl'],
    'cumulative_pnl_baseline': baseline['cumulative_pnl'],
    'belief_snapshots': bandit_result['belief_snapshots'],
}
with open(os.path.join(DATA_DIR, 'bandit_learning_curves.pkl'), 'wb') as f:
    pickle.dump(learning_data, f)
print(f"Saved: {DATA_DIR}/bandit_learning_curves.pkl")


# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("FINAL SUMMARY")
print("=" * 80)

print(f"""
  Surefire Config: {MAX_LEVELS} levels, sqrt(2) multiplier, 0.5% base
  Total Cycles: {len(cycles)}
  Regimes: {n_regimes}

  ALWAYS-TRADE BASELINE:
    Bust rate: {baseline['bust_rate_traded']*100:.2f}%
    Net P&L:   ${baseline['pnl_traded']:,.2f}

  BANDIT (Thompson Sampling, 20-run average):
    Bust rate: {multi_results['bust_rate_mean']*100:.2f}% (+/- {multi_results['bust_rate_std']*100:.2f}%)
    Net P&L:   ${multi_results['pnl_mean']:,.2f} (+/- ${multi_results['pnl_std']:,.2f})
    Skip rate: {multi_results['skip_rate_mean']*100:.1f}%
    Busts skipped: {multi_results['busts_skipped_mean']:.1f}

  BUST RATE REDUCTION: {bust_reduction:.1f}%

  Walk-forward: bandit beats baseline on bust rate in {n_better_bust}/{len(wf_results)} segments
  Walk-forward: bandit beats baseline on P&L in {n_better_pnl}/{len(wf_results)} segments

  KEY INSIGHT: Thompson Sampling naturally learns which regimes are dangerous.
  The asymmetric bust penalty (beta += {BUST_PENALTY_MULTIPLIER} for busts)
  makes the bandit cautious about regimes where busts occurred.
  Regime-uncertain cycles (confidence < {CONFIDENCE_THRESHOLD}) are always skipped.
""")

print("FILES SAVED:")
print(f"  {OUTPUT_DIR}/18_entry_bandit.png")
print(f"  {OUTPUT_DIR}/18_walk_forward.png")
print(f"  {DATA_DIR}/bandit_state.npz")
print(f"  {DATA_DIR}/bandit_comparison.pkl")
print(f"  {DATA_DIR}/bandit_learning_curves.pkl")
print("=" * 80)
