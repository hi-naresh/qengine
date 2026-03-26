#!/usr/bin/env python3
"""
Script 18b: Entry Bandit V2 -- Danger Score Buckets (replaces HMM regimes)
============================================================================
Online Thompson Sampling bandit that decides trade/skip based on a composite
danger score, NOT HMM regime labels.

KEY INSIGHT: HMM regimes failed because they don't separate bust-prone
conditions. The composite danger score (choppiness, ADX, hurst, range_atr)
provides 3.5x separation at the top 5% vs rest.

Danger levels (5 fixed buckets):
  0 (safe):    danger < 0.3
  1 (mild):    0.3 - 0.5
  2 (caution): 0.5 - 0.7
  3 (warning): 0.7 - 0.85
  4 (danger):  > 0.85

Surefire parameters: 12 levels, sqrt(2) multiplier, 0.5% base,
TP = 0.8*ATR, hedge_ratio = 2.0.
"""

import os, sys, pickle, time
os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
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
BASE_PCT = 0.005          # 0.5% of equity per base lot
TP_ATR_MULT = 0.8
HEDGE_RATIO = 2.0
ATR_PERIOD = 14
PIP_SIZE = 0.0001
EQUITY_START = 10_000
LEVERAGE = 30
PRICE_PER_LOT = 100_000
EMA_FAST = 8
EMA_SLOW = 21
ATR_LONG = 50

BUST_PENALTY = 10         # asymmetric: beta += this for busts
TRADE_THRESHOLD = 0.4     # sample must exceed this to trade
HARD_CUTOFF = 0.9         # skip if danger_score > this regardless

N_DANGER_LEVELS = 5
DANGER_THRESHOLDS = [0.3, 0.5, 0.7, 0.85]  # boundaries for 5 buckets

N_RUNS = 20               # multi-run averaging
N_WF_SEGMENTS = 5         # walk-forward segments (4 test folds)

# Feature warmup
WARMUP = max(ATR_LONG, ATR_PERIOD * 2, 21, 60)


# =============================================================================
# Part 1: DangerScorer -- Online Running Stats + Weighted Composite
# =============================================================================

class OnlineNormalizer:
    """Welford's online algorithm for running mean/std normalization."""

    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.M2 = 0.0

    def update(self, x):
        if np.isnan(x):
            return
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.M2 += delta * delta2

    def std(self):
        if self.n < 2:
            return 1.0
        return max(np.sqrt(self.M2 / self.n), 1e-10)

    def normalize(self, x):
        """Return z-score, clamped to [0, 1] via sigmoid-like mapping."""
        if np.isnan(x) or self.n < 30:
            return 0.5  # neutral when insufficient data
        z = (x - self.mean) / self.std()
        # Sigmoid map: z -> [0, 1], centered at 0.5
        return 1.0 / (1.0 + np.exp(-z))


class DangerScorer:
    """
    Composite danger score in [0, 1] from multiple indicators.

    Components (with online normalization):
      D1_range_atr   (inverted, 0.30) -- low range = choppy = dangerous
      5m_chop        (direct,   0.15) -- high choppiness = dangerous
      15m_chop       (direct,   0.15)
      D1_chop        (direct,   0.10)
      5m_adx         (inverted, 0.10) -- low ADX = no trend = dangerous
      5m_hurst       (dist 0.5, 0.10) -- near 0.5 = random walk = dangerous
      1H_atr_ratio   (direct,   0.10) -- high short/long ATR ratio = volatile

    "Inverted" means high raw value = low danger (so we flip the normalized score).
    """

    COMPONENTS = [
        # (feature_name, weight, invert, special)
        ('D1_range_atr', 0.30, True,  None),
        ('5m_chop',      0.15, False, None),
        ('15m_chop',     0.15, False, None),
        ('D1_chop',      0.10, False, None),
        ('5m_adx',       0.10, True,  None),
        ('5m_hurst',     0.10, False, 'dist_half'),  # |H - 0.5| inverted
        ('1H_atr_ratio', 0.10, False, None),
    ]

    def __init__(self):
        self.normalizers = {}
        for name, _, _, _ in self.COMPONENTS:
            self.normalizers[name] = OnlineNormalizer()

    def update_and_score(self, features: dict) -> float:
        """
        Update running stats with new feature values and return composite
        danger score in [0, 1].

        Parameters
        ----------
        features : dict mapping feature name -> raw value

        Returns
        -------
        danger_score : float in [0, 1], higher = more dangerous
        """
        score = 0.0
        total_weight = 0.0

        for name, weight, invert, special in self.COMPONENTS:
            raw = features.get(name, np.nan)

            if special == 'dist_half':
                # Transform: distance from 0.5, inverted
                # Near 0.5 (random walk) = high danger
                if not np.isnan(raw):
                    raw = 1.0 - abs(raw - 0.5) * 2.0  # maps [0,1] range: 0.5->1.0, 0->0, 1->0
                    raw = max(0.0, min(1.0, raw))

            # Update running stats
            self.normalizers[name].update(raw)

            # Get normalized score
            norm = self.normalizers[name].normalize(raw)

            if invert:
                norm = 1.0 - norm

            score += weight * norm
            total_weight += weight

        if total_weight > 0:
            score /= total_weight

        return float(np.clip(score, 0.0, 1.0))

    def get_state(self):
        state = {}
        for name, norm in self.normalizers.items():
            state[name] = {'n': norm.n, 'mean': norm.mean, 'M2': norm.M2}
        return state


def danger_level(score: float) -> int:
    """Map danger score to bucket 0-4 using fixed thresholds."""
    if score < DANGER_THRESHOLDS[0]:
        return 0
    elif score < DANGER_THRESHOLDS[1]:
        return 1
    elif score < DANGER_THRESHOLDS[2]:
        return 2
    elif score < DANGER_THRESHOLDS[3]:
        return 3
    else:
        return 4


DANGER_LABELS = {
    0: 'safe (<0.3)',
    1: 'mild (0.3-0.5)',
    2: 'caution (0.5-0.7)',
    3: 'warning (0.7-0.85)',
    4: 'danger (>0.85)',
}


# =============================================================================
# Part 2: EntryBandit (Thompson Sampling on Danger Levels)
# =============================================================================

class EntryBandit:
    """
    Thompson Sampling bandit over danger levels.

    Per danger level: Beta(alpha, beta) posterior.
    - Trade if sampled p > TRADE_THRESHOLD
    - Hard cutoff: skip if danger_score > HARD_CUTOFF regardless
    - Bust penalty: beta += BUST_PENALTY (asymmetric)
    - No confidence floor (danger score replaces HMM confidence)
    """

    def __init__(self, n_levels=N_DANGER_LEVELS, bust_penalty=BUST_PENALTY,
                 trade_threshold=TRADE_THRESHOLD, hard_cutoff=HARD_CUTOFF):
        self.n_levels = n_levels
        self.bust_penalty = bust_penalty
        self.trade_threshold = trade_threshold
        self.hard_cutoff = hard_cutoff

        # Beta(1,1) = uniform prior
        self.alpha = np.ones(n_levels)
        self.beta_param = np.ones(n_levels)

        # Tracking
        self.n_trades = np.zeros(n_levels, dtype=int)
        self.n_skips = np.zeros(n_levels, dtype=int)
        self.n_wins = np.zeros(n_levels, dtype=int)
        self.n_busts = np.zeros(n_levels, dtype=int)

    def should_trade(self, dlevel: int, danger_score: float) -> bool:
        """Decide whether to trade this cycle."""
        # Hard cutoff: always skip extreme danger
        if danger_score > self.hard_cutoff:
            return False

        dlevel = min(dlevel, self.n_levels - 1)
        p_success = np.random.beta(self.alpha[dlevel], self.beta_param[dlevel])
        return p_success > self.trade_threshold

    def update(self, dlevel: int, traded: bool, is_bust: bool):
        """
        Update posterior after cycle.
        - Skip: no update
        - Trade + win: alpha += 1
        - Trade + bust: beta += bust_penalty (asymmetric)
        """
        dlevel = min(dlevel, self.n_levels - 1)

        if not traded:
            self.n_skips[dlevel] += 1
            return

        self.n_trades[dlevel] += 1

        if is_bust:
            self.beta_param[dlevel] += self.bust_penalty
            self.n_busts[dlevel] += 1
        else:
            self.alpha[dlevel] += 1
            self.n_wins[dlevel] += 1

    def get_posterior_mean(self, dlevel: int) -> float:
        dlevel = min(dlevel, self.n_levels - 1)
        return self.alpha[dlevel] / (self.alpha[dlevel] + self.beta_param[dlevel])

    def get_state(self):
        return {
            'alpha': self.alpha.copy(),
            'beta_param': self.beta_param.copy(),
            'n_trades': self.n_trades.copy(),
            'n_skips': self.n_skips.copy(),
            'n_wins': self.n_wins.copy(),
            'n_busts': self.n_busts.copy(),
        }

    def reset(self):
        self.alpha = np.ones(self.n_levels)
        self.beta_param = np.ones(self.n_levels)
        self.n_trades = np.zeros(self.n_levels, dtype=int)
        self.n_skips = np.zeros(self.n_levels, dtype=int)
        self.n_wins = np.zeros(self.n_levels, dtype=int)
        self.n_busts = np.zeros(self.n_levels, dtype=int)


# =============================================================================
# Part 3: Load Data & Compute Danger Scores
# =============================================================================

def load_price_data():
    """Load EUR-USD 5m candles (20 years)."""
    print("Loading EUR-USD 5m candles from OANDA...")
    t0 = time.time()
    warmup_candles, candles = get_candles('OANDA', 'EUR-USD', '5m',
        jh.date_to_timestamp('2006-01-02'), jh.date_to_timestamp('2025-12-31'),
        warmup_candles_num=210)
    if warmup_candles is not None and warmup_candles.ndim == 2 and len(warmup_candles) > 0:
        candles = np.concatenate([warmup_candles, candles], axis=0)
    print(f"Total candles: {len(candles):,} ({time.time()-t0:.1f}s)")
    return candles


def load_1m_and_resample():
    """Load 1m data and resample to all timeframes needed for danger scorer."""
    print("Loading EUR-USD 1m candles from OANDA...")
    t0 = time.time()
    _, candles_1m = get_candles('OANDA', 'EUR-USD', '1m',
        jh.date_to_timestamp('2006-01-02'), jh.date_to_timestamp('2025-12-31'),
        warmup_candles_num=0)
    print(f"Total 1m candles: {len(candles_1m):,} ({time.time()-t0:.1f}s)")

    def resample(c1m, factor):
        n = len(c1m)
        trim = n - (n % factor)
        c = c1m[:trim].reshape(-1, factor, 6)
        out = np.empty((len(c), 6), dtype=np.float64)
        out[:, 0] = c[:, 0, 0]
        out[:, 1] = c[:, 0, 1]
        out[:, 2] = c[:, -1, 2]
        out[:, 3] = c[:, :, 3].max(axis=1)
        out[:, 4] = c[:, :, 4].min(axis=1)
        out[:, 5] = c[:, :, 5].sum(axis=1)
        return out

    timeframes = {'5m': 5, '15m': 15, '1H': 60, 'D1': 1440}
    candles = {}
    for tf, factor in timeframes.items():
        candles[tf] = resample(candles_1m, factor)
        print(f"  {tf}: {len(candles[tf]):,} bars")

    return candles


def compute_all_features(candles_dict):
    """
    Compute the 7 features needed for DangerScorer across timeframes,
    aligned to the 5m bar grid.
    """
    print("Computing features for danger scorer...")
    t0 = time.time()

    # Features needed: D1_range_atr, 5m_chop, 15m_chop, D1_chop,
    #                  5m_adx, 5m_hurst, 1H_atr_ratio
    c5m = candles_dict['5m']
    c15m = candles_dict['15m']
    c1H = candles_dict['1H']
    cD1 = candles_dict['D1']
    n_5m = len(c5m)
    ts_5m = c5m[:, 0]

    # Compute raw features per timeframe
    # 5m: chop, adx, hurst
    chop_5m = ta.chop(c5m, period=14, sequential=True)
    adx_5m = ta.adx(c5m, period=14, sequential=True)
    hurst_5m = _rolling_hurst(c5m[:, 2], window=20)

    # 15m: chop
    chop_15m_raw = ta.chop(c15m, period=14, sequential=True)

    # 1H: atr_ratio
    atr_short_1H = ta.atr(c1H, period=14, sequential=True)
    atr_long_1H = ta.atr(c1H, period=50, sequential=True)
    with np.errstate(divide='ignore', invalid='ignore'):
        atr_ratio_1H_raw = np.where(
            (atr_long_1H > 1e-12) & ~np.isnan(atr_long_1H),
            atr_short_1H / atr_long_1H, np.nan)

    # D1: chop, range_atr
    chop_D1_raw = ta.chop(cD1, period=14, sequential=True)
    atr_D1 = ta.atr(cD1, period=14, sequential=True)
    range_atr_D1_raw = _rolling_range_atr(cD1, 20, atr_D1)

    # Align higher TF features to 5m grid (forward fill, no lookahead)
    def align_to_5m(tf_candles, tf_feature):
        tf_ts = tf_candles[:, 0]
        indices = np.searchsorted(tf_ts, ts_5m, side='right') - 1
        aligned = np.full(n_5m, np.nan, dtype=np.float64)
        valid = (indices >= 0) & (indices < len(tf_feature))
        aligned[valid] = tf_feature[indices[valid]]
        return aligned

    features = {
        '5m_chop': chop_5m,
        '5m_adx': adx_5m,
        '5m_hurst': hurst_5m,
        '15m_chop': align_to_5m(c15m, chop_15m_raw),
        '1H_atr_ratio': align_to_5m(c1H, atr_ratio_1H_raw),
        'D1_chop': align_to_5m(cD1, chop_D1_raw),
        'D1_range_atr': align_to_5m(cD1, range_atr_D1_raw),
    }

    for name, arr in features.items():
        valid = np.sum(~np.isnan(arr))
        print(f"  {name}: {valid:,} / {n_5m:,} valid")

    print(f"  Features computed in {time.time()-t0:.1f}s")
    return features


def _rolling_hurst(prices, window=20):
    """Rolling Hurst exponent via R/S analysis."""
    n = len(prices)
    H = np.full(n, np.nan, dtype=np.float64)
    for i in range(window - 1, n):
        seg = prices[i - window + 1: i + 1]
        returns = np.diff(seg)
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


def _rolling_range_atr(candles_tf, range_window, atr_arr):
    """(HH - LL) over window / ATR."""
    n = len(candles_tf)
    result = np.full(n, np.nan, dtype=np.float64)
    highs = candles_tf[:, 3]
    lows = candles_tf[:, 4]
    for i in range(range_window - 1, n):
        hh = np.max(highs[i - range_window + 1: i + 1])
        ll = np.min(lows[i - range_window + 1: i + 1])
        if atr_arr[i] > 1e-12 and not np.isnan(atr_arr[i]):
            result[i] = (hh - ll) / atr_arr[i]
    return result


# =============================================================================
# Part 4: Cycle Simulation (matching script 15)
# =============================================================================

def simulate_cycles(candles_5m, features_at_5m):
    """
    Run full surefire cycle simulation on 5m data.
    Returns list of cycle dicts with danger scores computed online.
    """
    n = len(candles_5m)
    closes = candles_5m[:, 2]
    highs = candles_5m[:, 3]
    lows = candles_5m[:, 4]

    ema_fast = ta.ema(candles_5m, period=EMA_FAST, sequential=True)
    ema_slow = ta.ema(candles_5m, period=EMA_SLOW, sequential=True)
    atr_arr = ta.atr(candles_5m, period=ATR_PERIOD, sequential=True)

    MULTIPLIER_FN = lambda k: MULTIPLIER ** k

    equity = EQUITY_START
    scorer = DangerScorer()
    cycles = []
    i = WARMUP

    # Feed initial warmup bars into danger scorer (no cycles, just stats)
    print("  Feeding warmup bars into danger scorer...")
    for wi in range(WARMUP):
        feat = {name: arr[wi] for name, arr in features_at_5m.items()}
        scorer.update_and_score(feat)

    print("  Running cycle simulation...")
    while i < n - 1:
        if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]):
            i += 1
            continue
        if np.isnan(ema_fast[i-1]) or np.isnan(ema_slow[i-1]):
            i += 1
            continue

        is_bull = (ema_fast[i-1] < ema_slow[i-1]) and (ema_fast[i] >= ema_slow[i])
        is_bear = (ema_fast[i-1] > ema_slow[i-1]) and (ema_fast[i] <= ema_slow[i])

        if not (is_bull or is_bear):
            # Still update danger scorer with this bar's features
            feat = {name: arr[i] for name, arr in features_at_5m.items()}
            scorer.update_and_score(feat)
            i += 1
            continue

        if np.isnan(atr_arr[i]) or atr_arr[i] < 1e-6:
            i += 1
            continue

        # Compute danger score at entry
        feat = {name: arr[i] for name, arr in features_at_5m.items()}
        dscore = scorer.update_and_score(feat)
        dlevel = danger_level(dscore)

        # Cycle entry
        entry_bar = i
        entry_price = closes[i]
        direction = 1 if is_bull else -1
        tp_dist = atr_arr[i] * TP_ATR_MULT
        h_dist = tp_dist / HEDGE_RATIO

        base_lots = equity * BASE_PCT / PRICE_PER_LOT * LEVERAGE
        if base_lots < 0.001:
            i += 1
            continue

        # Affordable levels
        affordable = MAX_LEVELS
        for test_n in range(1, MAX_LEVELS + 1):
            cum_size = sum(base_lots * MULTIPLIER_FN(k) for k in range(test_n))
            cum_margin = cum_size * PRICE_PER_LOT / LEVERAGE
            cum_loss = cum_size * h_dist * PRICE_PER_LOT
            if cum_margin + cum_loss > equity * 0.95:
                affordable = test_n - 1
                break
        affordable = max(affordable, 2)

        # Walk through levels
        cycle_pnl = 0.0
        win_level = -1
        positions = []
        j = i + 1
        entry = entry_price

        for level in range(affordable):
            size = base_lots * MULTIPLIER_FN(level)
            tp_price = entry + direction * tp_dist
            sl_price = entry - direction * h_dist
            positions.append((size, entry, direction, tp_price, sl_price))

            won = False
            lost = False
            while j < n:
                h = highs[j]
                lo = lows[j]
                if direction == 1:
                    if h >= tp_price:
                        won = True
                        break
                    if lo <= sl_price:
                        lost = True
                        break
                else:
                    if lo <= tp_price:
                        won = True
                        break
                    if h >= sl_price:
                        lost = True
                        break
                j += 1

            if won:
                for sz, ent, d, tp_p, sl_p in positions[:-1]:
                    cycle_pnl -= sz * h_dist * PRICE_PER_LOT
                cycle_pnl += size * tp_dist * PRICE_PER_LOT
                win_level = level
                break
            elif lost:
                entry = sl_price
                direction *= -1
                j += 1
            else:
                break

        # Bust
        if win_level == -1 and j < n:
            for sz, ent, d, tp_p, sl_p in positions:
                cycle_pnl -= sz * h_dist * PRICE_PER_LOT

        # Skip incomplete
        if j >= n and win_level == -1:
            i = j
            continue

        is_bust = (win_level == -1)
        equity += cycle_pnl

        cycles.append({
            'entry_bar': entry_bar,
            'end_bar': j,
            'timestamp': candles_5m[entry_bar, 0],
            'is_bust': is_bust,
            'pnl': cycle_pnl,
            'win_level': win_level,
            'levels_used': len(positions),
            'danger_score': dscore,
            'danger_level': dlevel,
            'duration_bars': j - entry_bar,
        })

        i = j + 1

    return cycles, scorer


# =============================================================================
# Part 5: Online Bandit Simulation
# =============================================================================

def run_bandit_simulation(cycles, label="Bandit"):
    """
    Process cycles chronologically. For each:
    1. Get danger level -> bandit decides trade/skip
    2. If traded, observe outcome -> update
    """
    bandit = EntryBandit()
    traded = []
    skipped = []
    cum_pnl = []
    running_pnl = 0.0
    belief_snaps = []

    for idx, c in enumerate(cycles):
        dl = c['danger_level']
        ds = c['danger_score']

        trade = bandit.should_trade(dl, ds)

        if trade:
            running_pnl += c['pnl']
            bandit.update(dl, traded=True, is_bust=c['is_bust'])
            traded.append(c)
        else:
            bandit.update(dl, traded=False, is_bust=False)
            skipped.append(c)

        cum_pnl.append(running_pnl)

        if idx % 50 == 0 or idx == len(cycles) - 1:
            belief_snaps.append((
                idx, bandit.alpha.copy(), bandit.beta_param.copy()))

    n_total = len(cycles)
    n_traded = len(traded)
    n_busts_traded = sum(1 for c in traded if c['is_bust'])
    n_busts_all = sum(1 for c in cycles if c['is_bust'])
    busts_skipped = sum(1 for c in skipped if c['is_bust'])
    wins_skipped = sum(1 for c in skipped if not c['is_bust'])
    pnl_all = sum(c['pnl'] for c in cycles)

    return bandit, {
        'label': label,
        'n_total': n_total,
        'n_traded': n_traded,
        'n_skipped': len(skipped),
        'skip_rate': len(skipped) / n_total if n_total > 0 else 0,
        'n_busts_traded': n_busts_traded,
        'bust_rate_traded': n_busts_traded / n_traded if n_traded > 0 else 0,
        'bust_rate_all': n_busts_all / n_total if n_total > 0 else 0,
        'busts_skipped': busts_skipped,
        'wins_skipped': wins_skipped,
        'pnl_traded': running_pnl,
        'pnl_all': pnl_all,
        'cumulative_pnl': np.array(cum_pnl),
        'belief_snapshots': belief_snaps,
        'bandit_state': bandit.get_state(),
    }


def run_threshold_baseline(cycles, threshold=0.85):
    """Simple strategy: skip if danger_score > threshold."""
    traded = [c for c in cycles if c['danger_score'] <= threshold]
    skipped = [c for c in cycles if c['danger_score'] > threshold]

    n_total = len(cycles)
    n_traded = len(traded)
    n_busts_traded = sum(1 for c in traded if c['is_bust'])
    n_busts_all = sum(1 for c in cycles if c['is_bust'])
    busts_skipped = sum(1 for c in skipped if c['is_bust'])
    pnl_traded = sum(c['pnl'] for c in traded)
    pnl_all = sum(c['pnl'] for c in cycles)
    cum_pnl = np.cumsum([c['pnl'] if c['danger_score'] <= threshold else 0.0
                         for c in cycles])

    return {
        'label': f'Skip danger>{threshold}',
        'n_total': n_total,
        'n_traded': n_traded,
        'n_skipped': len(skipped),
        'skip_rate': len(skipped) / n_total if n_total > 0 else 0,
        'n_busts_traded': n_busts_traded,
        'bust_rate_traded': n_busts_traded / n_traded if n_traded > 0 else 0,
        'bust_rate_all': n_busts_all / n_total if n_total > 0 else 0,
        'busts_skipped': busts_skipped,
        'wins_skipped': sum(1 for c in skipped if not c['is_bust']),
        'pnl_traded': pnl_traded,
        'pnl_all': pnl_all,
        'cumulative_pnl': cum_pnl,
    }


def run_always_trade(cycles):
    """Baseline: trade everything."""
    n_total = len(cycles)
    n_busts = sum(1 for c in cycles if c['is_bust'])
    pnl = sum(c['pnl'] for c in cycles)
    cum_pnl = np.cumsum([c['pnl'] for c in cycles])
    return {
        'label': 'Always trade',
        'n_total': n_total,
        'n_traded': n_total,
        'n_skipped': 0,
        'skip_rate': 0.0,
        'n_busts_traded': n_busts,
        'bust_rate_traded': n_busts / n_total if n_total > 0 else 0,
        'bust_rate_all': n_busts / n_total if n_total > 0 else 0,
        'busts_skipped': 0,
        'wins_skipped': 0,
        'pnl_traded': pnl,
        'pnl_all': pnl,
        'cumulative_pnl': cum_pnl,
    }


# =============================================================================
# Part 6: Walk-Forward Evaluation
# =============================================================================

def walk_forward_evaluation(cycles, n_segments=N_WF_SEGMENTS):
    """
    Expanding window walk-forward.
    Split into n_segments by timestamp, train on 0..i, test on i+1.
    """
    timestamps = np.array([c['timestamp'] for c in cycles])
    ts_min, ts_max = timestamps.min(), timestamps.max()
    seg_dur = (ts_max - ts_min) / n_segments
    boundaries = [ts_min + i * seg_dur for i in range(n_segments + 1)]

    segments = []
    for i in range(n_segments):
        seg = [c for c in cycles if boundaries[i] <= c['timestamp'] < boundaries[i+1]]
        segments.append(seg)

    print(f"\nWalk-Forward: {n_segments} segments")
    for i, seg in enumerate(segments):
        n_busts = sum(1 for c in seg if c['is_bust'])
        print(f"  Seg {i}: {len(seg)} cycles, {n_busts} busts")

    wf_results = []
    for test_idx in range(1, n_segments):
        train = []
        for j in range(test_idx):
            train.extend(segments[j])
        test = segments[test_idx]
        if len(test) < 5:
            continue

        # Train bandit
        bandit = EntryBandit()
        for c in train:
            dl = c['danger_level']
            ds = c['danger_score']
            trade = bandit.should_trade(dl, ds)
            if trade:
                bandit.update(dl, traded=True, is_bust=c['is_bust'])
            else:
                bandit.update(dl, traded=False, is_bust=False)

        # Test (frozen beliefs, still sampling)
        test_traded = []
        test_skipped = []
        for c in test:
            dl = c['danger_level']
            ds = c['danger_score']
            if bandit.should_trade(dl, ds):
                test_traded.append(c)
            else:
                test_skipped.append(c)

        n_test = len(test)
        n_traded = len(test_traded)
        n_busts_traded = sum(1 for c in test_traded if c['is_bust'])
        n_busts_all = sum(1 for c in test if c['is_bust'])
        busts_skipped = sum(1 for c in test_skipped if c['is_bust'])
        pnl_bandit = sum(c['pnl'] for c in test_traded)
        pnl_baseline = sum(c['pnl'] for c in test)

        wf_results.append({
            'test_idx': test_idx,
            'n_train': len(train),
            'n_test': n_test,
            'n_traded': n_traded,
            'n_skipped': n_test - n_traded,
            'skip_rate': (n_test - n_traded) / n_test if n_test > 0 else 0,
            'bust_rate_bandit': n_busts_traded / n_traded if n_traded > 0 else 0,
            'bust_rate_baseline': n_busts_all / n_test if n_test > 0 else 0,
            'busts_skipped': busts_skipped,
            'pnl_bandit': pnl_bandit,
            'pnl_baseline': pnl_baseline,
        })

    return wf_results


# =============================================================================
# Part 7: Multi-Run Averaging
# =============================================================================

def run_multiple(cycles, n_runs=N_RUNS):
    """Run bandit n_runs times, averaging over Thompson Sampling stochasticity."""
    all_results = []
    for run in range(n_runs):
        np.random.seed(run * 42 + 7)
        _, result = run_bandit_simulation(cycles, label=f"Run {run}")
        all_results.append(result)

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
print("  SCRIPT 18b: Entry Bandit V2 -- Danger Score Buckets")
print("  (replaces HMM regimes with composite danger scorer)")
print("=" * 80)

# ---- Load data and compute features ----------------------------------------
candles_dict = load_1m_and_resample()
features_at_5m = compute_all_features(candles_dict)
candles_5m = candles_dict['5m']

# ---- Simulate cycles with online danger scoring ----------------------------
print("\n" + "=" * 80)
print("CYCLE SIMULATION + DANGER SCORING")
print("=" * 80)
cycles, scorer = simulate_cycles(candles_5m, features_at_5m)

n_total = len(cycles)
n_busts = sum(1 for c in cycles if c['is_bust'])
print(f"\n  Total cycles: {n_total:,}")
print(f"  Busts: {n_busts} ({n_busts/n_total*100:.3f}%)")

# Danger score distribution
dscores = np.array([c['danger_score'] for c in cycles])
dlevels = np.array([c['danger_level'] for c in cycles])
print(f"\n  Danger score stats: min={dscores.min():.3f}, median={np.median(dscores):.3f}, "
      f"max={dscores.max():.3f}, mean={dscores.mean():.3f}")

print(f"\n  {'Level':<25} {'Cycles':<10} {'Busts':<8} {'Bust%':<10} {'Sep Ratio':<10}")
print(f"  {'-'*65}")
overall_bust_rate = n_busts / n_total if n_total > 0 else 0
for dl in range(N_DANGER_LEVELS):
    mask = dlevels == dl
    nc = mask.sum()
    nb = sum(1 for c in cycles if c['danger_level'] == dl and c['is_bust'])
    br = nb / nc * 100 if nc > 0 else 0
    sep = br / (overall_bust_rate * 100) if overall_bust_rate > 0 else 0
    print(f"  {DANGER_LABELS[dl]:<25} {nc:<10} {nb:<8} {br:<10.3f} {sep:<10.2f}x")


# ---- Baselines -------------------------------------------------------------
print("\n" + "=" * 80)
print("BASELINES")
print("=" * 80)

baseline_always = run_always_trade(cycles)
baseline_thresh = run_threshold_baseline(cycles, threshold=0.85)

print(f"\n  Always-trade: {baseline_always['n_total']} cycles, "
      f"{baseline_always['n_busts_traded']} busts ({baseline_always['bust_rate_traded']*100:.3f}%), "
      f"P&L: ${baseline_always['pnl_traded']:,.2f}")
print(f"  Skip>0.85:   {baseline_thresh['n_traded']} traded, "
      f"{baseline_thresh['n_skipped']} skipped ({baseline_thresh['skip_rate']*100:.1f}%), "
      f"{baseline_thresh['n_busts_traded']} busts ({baseline_thresh['bust_rate_traded']*100:.3f}%), "
      f"avoided {baseline_thresh['busts_skipped']} busts, "
      f"P&L: ${baseline_thresh['pnl_traded']:,.2f}")


# ---- Single Bandit Run -----------------------------------------------------
print("\n" + "=" * 80)
print("ONLINE BANDIT (single run)")
print("=" * 80)
np.random.seed(42)
bandit, bandit_result = run_bandit_simulation(cycles)

print(f"  Traded: {bandit_result['n_traded']} ({(1-bandit_result['skip_rate'])*100:.1f}%)")
print(f"  Skipped: {bandit_result['n_skipped']} ({bandit_result['skip_rate']*100:.1f}%)")
print(f"  Busts (traded): {bandit_result['n_busts_traded']} "
      f"({bandit_result['bust_rate_traded']*100:.3f}%)")
print(f"  Busts skipped: {bandit_result['busts_skipped']}")
print(f"  Wins skipped: {bandit_result['wins_skipped']}")
print(f"  P&L (bandit): ${bandit_result['pnl_traded']:,.2f}")
print(f"  P&L (baseline): ${baseline_always['pnl_traded']:,.2f}")

print("\n  --- Final Bandit Beliefs ---")
print(f"  {'Level':<25} {'Alpha':<10} {'Beta':<10} {'E[p_win]':<10} "
      f"{'Trades':<10} {'Busts':<8}")
for dl in range(N_DANGER_LEVELS):
    a = bandit.alpha[dl]
    b = bandit.beta_param[dl]
    mean = a / (a + b)
    print(f"  {DANGER_LABELS[dl]:<25} {a:<10.1f} {b:<10.1f} {mean:<10.4f} "
          f"{bandit.n_trades[dl]:<10} {bandit.n_busts[dl]:<8}")


# ---- Multi-Run Averaging ---------------------------------------------------
print("\n" + "=" * 80)
print(f"MULTI-RUN ANALYSIS ({N_RUNS} runs)")
print("=" * 80)
multi = run_multiple(cycles, n_runs=N_RUNS)
print(f"  Bust rate: {multi['bust_rate_mean']*100:.3f}% "
      f"(+/- {multi['bust_rate_std']*100:.3f}%)")
print(f"  P&L: ${multi['pnl_mean']:,.2f} (+/- ${multi['pnl_std']:,.2f})")
print(f"  Skip rate: {multi['skip_rate_mean']*100:.1f}% "
      f"(+/- {multi['skip_rate_std']*100:.1f}%)")
print(f"  Busts skipped: {multi['busts_skipped_mean']:.1f} "
      f"(+/- {multi['busts_skipped_std']:.1f})")

bust_reduction_vs_always = (
    (1 - multi['bust_rate_mean'] / baseline_always['bust_rate_traded']) * 100
    if baseline_always['bust_rate_traded'] > 0 else 0)
bust_reduction_vs_thresh = (
    (1 - multi['bust_rate_mean'] / baseline_thresh['bust_rate_traded']) * 100
    if baseline_thresh['bust_rate_traded'] > 0 else 0)
print(f"\n  Bust rate reduction vs always-trade: {bust_reduction_vs_always:.1f}%")
print(f"  Bust rate reduction vs threshold:    {bust_reduction_vs_thresh:.1f}%")


# ---- Walk-Forward ----------------------------------------------------------
print("\n" + "=" * 80)
print("WALK-FORWARD EVALUATION")
print("=" * 80)
np.random.seed(42)
wf_results = walk_forward_evaluation(cycles, n_segments=N_WF_SEGMENTS)

print(f"\n  {'Seg':<6} {'Train':<8} {'Test':<8} {'Traded':<8} {'Skip%':<8} "
      f"{'Bust%(B)':<10} {'Bust%(BL)':<10} {'BustsSkip':<10} "
      f"{'PnL(B)':<12} {'PnL(BL)':<12}")
print(f"  {'-'*96}")
for r in wf_results:
    print(f"  {r['test_idx']:<6} {r['n_train']:<8} {r['n_test']:<8} "
          f"{r['n_traded']:<8} {r['skip_rate']*100:<8.1f} "
          f"{r['bust_rate_bandit']*100:<10.3f} {r['bust_rate_baseline']*100:<10.3f} "
          f"{r['busts_skipped']:<10} "
          f"${r['pnl_bandit']:<11,.2f} ${r['pnl_baseline']:<11,.2f}")

n_better_bust = sum(1 for r in wf_results if r['bust_rate_bandit'] < r['bust_rate_baseline'])
n_better_pnl = sum(1 for r in wf_results if r['pnl_bandit'] > r['pnl_baseline'])
print(f"\n  Bandit beats baseline on bust rate: {n_better_bust}/{len(wf_results)} segments")
print(f"  Bandit beats baseline on P&L:       {n_better_pnl}/{len(wf_results)} segments")


# =============================================================================
# COMPARISON TABLE
# =============================================================================
print("\n" + "=" * 80)
print("COMPARISON TABLE")
print("=" * 80)

strategies = [
    baseline_always,
    baseline_thresh,
    {
        'label': f'Bandit ({N_RUNS}-run avg)',
        'n_traded': int(n_total * (1 - multi['skip_rate_mean'])),
        'skip_rate': multi['skip_rate_mean'],
        'bust_rate_traded': multi['bust_rate_mean'],
        'busts_skipped': multi['busts_skipped_mean'],
        'pnl_traded': multi['pnl_mean'],
    },
]

print(f"\n  {'Strategy':<25} {'Trade%':<10} {'Bust Rate':<12} {'Busts Avoided':<15} {'P&L':<15}")
print(f"  {'-'*75}")
for s in strategies:
    trade_pct = (1 - s.get('skip_rate', 0)) * 100
    bust_r = s['bust_rate_traded'] * 100
    avoided = s.get('busts_skipped', 0)
    pnl = s['pnl_traded']
    print(f"  {s['label']:<25} {trade_pct:<10.1f} {bust_r:<12.3f} "
          f"{avoided:<15} ${pnl:<14,.2f}")


# =============================================================================
# CHARTS
# =============================================================================
plt.style.use('seaborn-v0_8-darkgrid')

fig, axes = plt.subplots(3, 2, figsize=(18, 20))

# ---- Chart 1: Equity Curves ------------------------------------------------
ax = axes[0, 0]
ax.plot(baseline_always['cumulative_pnl'], label='Always Trade',
        color='#3498db', linewidth=1.0, alpha=0.7)
ax.plot(baseline_thresh['cumulative_pnl'], label='Skip >0.85',
        color='#f39c12', linewidth=1.2, alpha=0.8)
ax.plot(bandit_result['cumulative_pnl'], label='Bandit (TS)',
        color='#e74c3c', linewidth=1.5)
ax.axhline(y=0, color='black', linewidth=0.5, linestyle=':')
ax.set_xlabel('Cycle #')
ax.set_ylabel('Cumulative P&L ($)')
ax.set_title('Equity Curves: Bandit vs Baselines', fontweight='bold')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# ---- Chart 2: Belief Evolution Per Danger Level -----------------------------
ax = axes[0, 1]
snaps = bandit_result['belief_snapshots']
cycle_idxs = [s[0] for s in snaps]
colors_dl = ['#27ae60', '#2ecc71', '#f39c12', '#e67e22', '#e74c3c']
for dl in range(N_DANGER_LEVELS):
    means = [s[1][dl] / (s[1][dl] + s[2][dl]) for s in snaps]
    ax.plot(cycle_idxs, means, label=DANGER_LABELS[dl],
            color=colors_dl[dl], linewidth=1.5)
ax.axhline(y=TRADE_THRESHOLD, color='black', linestyle='--', alpha=0.5,
           label=f'Trade threshold ({TRADE_THRESHOLD})')
ax.set_xlabel('Cycle #')
ax.set_ylabel('E[P(success)]')
ax.set_title('Bandit Belief Evolution by Danger Level', fontweight='bold')
ax.legend(fontsize=7, loc='best')
ax.set_ylim(0, 1)
ax.grid(True, alpha=0.3)

# ---- Chart 3: Per-Level Trade/Skip Breakdown --------------------------------
ax = axes[1, 0]
state = bandit_result['bandit_state']
dl_ids = np.arange(N_DANGER_LEVELS)
width = 0.35
bars1 = ax.bar(dl_ids - width/2, state['n_trades'], width, label='Traded',
               color='#2ecc71', edgecolor='black', linewidth=0.5)
bars2 = ax.bar(dl_ids + width/2, state['n_skips'], width, label='Skipped',
               color='#e74c3c', edgecolor='black', linewidth=0.5)
for dl in range(N_DANGER_LEVELS):
    if state['n_busts'][dl] > 0:
        ax.text(dl - width/2, state['n_trades'][dl] + 10,
                f"{int(state['n_busts'][dl])}B",
                ha='center', fontsize=8, color='red', fontweight='bold')
ax.set_xlabel('Danger Level')
ax.set_ylabel('Count')
ax.set_title('Trades vs Skips per Danger Level\n(red = busts among traded)',
             fontweight='bold')
ax.set_xticks(dl_ids)
ax.set_xticklabels([DANGER_LABELS[dl] for dl in range(N_DANGER_LEVELS)],
                    fontsize=7, rotation=15)
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3, axis='y')

# ---- Chart 4: Multi-Run Bust Rate Distribution ------------------------------
ax = axes[1, 1]
all_bust_rates = [r['bust_rate_traded'] * 100 for r in multi['all_results']]
ax.hist(all_bust_rates, bins=15, color='#3498db', edgecolor='black',
        alpha=0.7, label=f'Bandit bust rate ({N_RUNS} runs)')
ax.axvline(x=baseline_always['bust_rate_traded'] * 100, color='red',
           linewidth=2, linestyle='--',
           label=f"Always: {baseline_always['bust_rate_traded']*100:.3f}%")
ax.axvline(x=baseline_thresh['bust_rate_traded'] * 100, color='orange',
           linewidth=2, linestyle='-.',
           label=f"Thresh: {baseline_thresh['bust_rate_traded']*100:.3f}%")
ax.axvline(x=np.mean(all_bust_rates), color='blue', linewidth=2,
           label=f'Bandit mean: {np.mean(all_bust_rates):.3f}%')
ax.set_xlabel('Bust Rate (%)')
ax.set_ylabel('Frequency')
ax.set_title(f'Bust Rate Distribution ({N_RUNS} Bandit Runs)', fontweight='bold')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# ---- Chart 5: Danger Score vs Bust Rate (validation) -----------------------
ax = axes[2, 0]
# Bin danger scores into 20 bins and compute bust rate per bin
n_bins = 20
bin_edges = np.linspace(0, 1, n_bins + 1)
bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
bin_bust_rates = []
bin_counts = []
for bi in range(n_bins):
    lo, hi = bin_edges[bi], bin_edges[bi + 1]
    in_bin = [c for c in cycles if lo <= c['danger_score'] < hi]
    if len(in_bin) >= 5:
        br = sum(1 for c in in_bin if c['is_bust']) / len(in_bin) * 100
        bin_bust_rates.append(br)
        bin_counts.append(len(in_bin))
    else:
        bin_bust_rates.append(np.nan)
        bin_counts.append(len(in_bin))

valid_mask = ~np.isnan(bin_bust_rates)
ax.bar(bin_centers, bin_bust_rates, width=1.0/n_bins * 0.9,
       color='#e74c3c', alpha=0.7, edgecolor='black')
ax.axhline(y=overall_bust_rate * 100, color='blue', linestyle='--',
           label=f'Overall: {overall_bust_rate*100:.3f}%')
# Add count labels
for bi in range(n_bins):
    if bin_counts[bi] > 0 and not np.isnan(bin_bust_rates[bi]):
        ax.text(bin_centers[bi], bin_bust_rates[bi] + 0.01,
                f'n={bin_counts[bi]}', ha='center', fontsize=5, rotation=90)
ax.set_xlabel('Danger Score')
ax.set_ylabel('Bust Rate (%)')
ax.set_title('Bust Rate by Danger Score Bucket', fontweight='bold')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# ---- Chart 6: Walk-Forward Comparison --------------------------------------
ax = axes[2, 1]
if wf_results:
    seg_ids = [r['test_idx'] for r in wf_results]
    x = np.arange(len(seg_ids))
    width = 0.35
    bust_bl = [r['bust_rate_baseline'] * 100 for r in wf_results]
    bust_bd = [r['bust_rate_bandit'] * 100 for r in wf_results]
    ax.bar(x - width/2, bust_bl, width, label='Baseline',
           color='#e74c3c', alpha=0.7, edgecolor='black')
    ax.bar(x + width/2, bust_bd, width, label='Bandit',
           color='#2ecc71', alpha=0.7, edgecolor='black')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Seg {s}' for s in seg_ids])
    ax.set_xlabel('Test Segment')
    ax.set_ylabel('Bust Rate (%)')
    ax.set_title('Walk-Forward: Bust Rate Comparison', fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis='y')
else:
    ax.text(0.5, 0.5, 'No walk-forward results', transform=ax.transAxes,
            ha='center', va='center')

plt.suptitle(
    f'Script 18b: Entry Bandit V2 -- Danger Score Buckets\n'
    f'{n_total} cycles, {N_DANGER_LEVELS} danger levels, '
    f'sqrt(2) multiplier, {MAX_LEVELS} levels, {N_RUNS}-run avg',
    fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/18b_entry_bandit_v2.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUTPUT_DIR}/18b_entry_bandit_v2.png")

# ---- Learning curve plot (multi-run P&L envelope) ---------------------------
fig, ax = plt.subplots(1, 1, figsize=(14, 6))
# Plot all 20 runs as thin lines, plus mean
all_cum_pnls = [r['cumulative_pnl'] for r in multi['all_results']]
min_len = min(len(cp) for cp in all_cum_pnls)
trimmed = np.array([cp[:min_len] for cp in all_cum_pnls])
mean_pnl = trimmed.mean(axis=0)
std_pnl = trimmed.std(axis=0)
xs = np.arange(min_len)

ax.fill_between(xs, mean_pnl - std_pnl, mean_pnl + std_pnl,
                alpha=0.2, color='#e74c3c', label='+/- 1 std')
ax.plot(xs, mean_pnl, color='#e74c3c', linewidth=2, label='Bandit (mean)')
ax.plot(baseline_always['cumulative_pnl'][:min_len],
        color='#3498db', linewidth=1.5, alpha=0.7, label='Always Trade')
ax.axhline(y=0, color='black', linewidth=0.5, linestyle=':')
ax.set_xlabel('Cycle #')
ax.set_ylabel('Cumulative P&L ($)')
ax.set_title(f'Learning Curves ({N_RUNS}-Run Envelope)', fontweight='bold')
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/18b_learning_curves.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/18b_learning_curves.png")


# =============================================================================
# SAVE OUTPUTS
# =============================================================================

# Bandit state
bandit_state = bandit.get_state()
np.savez(
    os.path.join(DATA_DIR, '18b_bandit_state.npz'),
    alpha=bandit_state['alpha'],
    beta_param=bandit_state['beta_param'],
    n_trades=bandit_state['n_trades'],
    n_skips=bandit_state['n_skips'],
    n_wins=bandit_state['n_wins'],
    n_busts=bandit_state['n_busts'],
)
print(f"Saved: {DATA_DIR}/18b_bandit_state.npz")

# Comparison metrics
comparison = {
    'baseline_always': {
        'bust_rate': baseline_always['bust_rate_traded'],
        'pnl': baseline_always['pnl_traded'],
    },
    'baseline_threshold': {
        'bust_rate': baseline_thresh['bust_rate_traded'],
        'pnl': baseline_thresh['pnl_traded'],
        'skip_rate': baseline_thresh['skip_rate'],
        'busts_skipped': baseline_thresh['busts_skipped'],
    },
    'bandit': {
        'bust_rate_mean': multi['bust_rate_mean'],
        'bust_rate_std': multi['bust_rate_std'],
        'pnl_mean': multi['pnl_mean'],
        'pnl_std': multi['pnl_std'],
        'skip_rate_mean': multi['skip_rate_mean'],
        'busts_skipped_mean': multi['busts_skipped_mean'],
    },
    'bust_reduction_vs_always': bust_reduction_vs_always,
    'bust_reduction_vs_thresh': bust_reduction_vs_thresh,
    'walk_forward': wf_results,
    'danger_scorer_state': scorer.get_state(),
    'danger_thresholds': DANGER_THRESHOLDS,
}
with open(os.path.join(DATA_DIR, '18b_bandit_comparison.pkl'), 'wb') as f:
    pickle.dump(comparison, f)
print(f"Saved: {DATA_DIR}/18b_bandit_comparison.pkl")

# Learning curves
learning = {
    'cumulative_pnl_bandit': bandit_result['cumulative_pnl'],
    'cumulative_pnl_baseline': baseline_always['cumulative_pnl'],
    'cumulative_pnl_threshold': baseline_thresh['cumulative_pnl'],
    'belief_snapshots': bandit_result['belief_snapshots'],
    'multi_run_pnls': [r['cumulative_pnl'] for r in multi['all_results']],
}
with open(os.path.join(DATA_DIR, '18b_learning_curves.pkl'), 'wb') as f:
    pickle.dump(learning, f)
print(f"Saved: {DATA_DIR}/18b_learning_curves.pkl")

# Cycle-level data with danger scores (for downstream use)
cycle_df = pd.DataFrame([{
    'entry_bar': c['entry_bar'],
    'timestamp': c['timestamp'],
    'is_bust': c['is_bust'],
    'pnl': c['pnl'],
    'danger_score': c['danger_score'],
    'danger_level': c['danger_level'],
    'win_level': c['win_level'],
    'duration_bars': c['duration_bars'],
} for c in cycles])
cycle_df.to_parquet(os.path.join(OUTPUT_DIR, '18b_cycles_with_danger.parquet'), index=False)
print(f"Saved: {OUTPUT_DIR}/18b_cycles_with_danger.parquet")


# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("FINAL SUMMARY")
print("=" * 80)
print(f"""
  Surefire Config: {MAX_LEVELS} levels, sqrt(2) multiplier, 0.5% base
  Total Cycles: {n_total:,}
  Total Busts:  {n_busts} ({overall_bust_rate*100:.3f}%)

  DANGER SCORE SEPARATION:""")

for dl in range(N_DANGER_LEVELS):
    mask = dlevels == dl
    nc = mask.sum()
    nb = sum(1 for c in cycles if c['danger_level'] == dl and c['is_bust'])
    br = nb / nc * 100 if nc > 0 else 0
    sep = br / (overall_bust_rate * 100) if overall_bust_rate > 0 else 0
    print(f"    {DANGER_LABELS[dl]:<25} {nc:>6} cycles, {nb:>3} busts, "
          f"{br:.3f}% bust rate ({sep:.2f}x)")

print(f"""
  COMPARISON TABLE:
  {'Strategy':<25} {'Trade%':<10} {'Bust Rate':<12} {'Busts Avoided':<15} {'P&L':<15}
  {'-'*75}""")
for s in strategies:
    trade_pct = (1 - s.get('skip_rate', 0)) * 100
    bust_r = s['bust_rate_traded'] * 100
    avoided = s.get('busts_skipped', 0)
    pnl = s['pnl_traded']
    print(f"  {s['label']:<25} {trade_pct:<10.1f} {bust_r:<12.3f} "
          f"{avoided:<15} ${pnl:<14,.2f}")

print(f"""
  BANDIT ({N_RUNS}-run avg):
    Bust rate: {multi['bust_rate_mean']*100:.3f}% (+/- {multi['bust_rate_std']*100:.3f}%)
    P&L:       ${multi['pnl_mean']:,.2f} (+/- ${multi['pnl_std']:,.2f})
    Skip rate: {multi['skip_rate_mean']*100:.1f}%
    Busts skipped: {multi['busts_skipped_mean']:.1f} (+/- {multi['busts_skipped_std']:.1f})

  BUST RATE REDUCTION:
    vs always-trade: {bust_reduction_vs_always:.1f}%
    vs threshold:    {bust_reduction_vs_thresh:.1f}%

  Walk-forward: beats baseline on bust rate {n_better_bust}/{len(wf_results)} segments
  Walk-forward: beats baseline on P&L       {n_better_pnl}/{len(wf_results)} segments

  KEY INSIGHT: Danger score buckets replace HMM regimes. The composite scorer
  (choppiness, ADX, hurst, range_atr) provides empirically validated 3.5x bust
  rate separation at the top 5%. The bandit learns to avoid high-danger buckets
  via asymmetric bust penalty (beta += {BUST_PENALTY}).

  FILES SAVED:
    {OUTPUT_DIR}/18b_entry_bandit_v2.png
    {OUTPUT_DIR}/18b_learning_curves.png
    {DATA_DIR}/18b_bandit_state.npz
    {DATA_DIR}/18b_bandit_comparison.pkl
    {DATA_DIR}/18b_learning_curves.pkl
    {OUTPUT_DIR}/18b_cycles_with_danger.parquet
""")
print("=" * 80)
