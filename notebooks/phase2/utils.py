#!/usr/bin/env python3
"""
Phase 2 Shared Utilities
========================
Common code used across all phase 2 research scripts:
- SurefireCycleSimulator: full multi-level hedge cycle simulation
- Resampling: 1m candles to higher timeframes
- Feature computation: regime descriptors across multiple timeframes
- Data I/O: save/load results in various formats
- Evaluation: permutation tests, deflated Sharpe, walk-forward splits
"""

import os
import sys
import json
import pickle
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional, Callable, Any

import numpy as np

# ---------------------------------------------------------------------------
# Project bootstrap — ensure qengine is importable from notebooks
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

import qengine.indicators as ta
import qengine.helpers as jh
from qengine.research import get_candles

# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------
PHASE2_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PHASE2_DIR, 'data')
RESULTS_DIR = os.path.join(PHASE2_DIR, 'results')
PLOTS_DIR = os.path.join(PHASE2_DIR, 'plots')


def ensure_data_dir() -> Tuple[str, str, str]:
    """Create notebooks/phase2/data/, results/, and plots/ directories.

    Returns the three directory paths as a tuple.
    """
    for d in (DATA_DIR, RESULTS_DIR, PLOTS_DIR):
        os.makedirs(d, exist_ok=True)
    return DATA_DIR, RESULTS_DIR, PLOTS_DIR


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------
def get_logger(name: str = 'phase2', level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger that writes to stdout."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter('[%(asctime)s] %(levelname)s  %(message)s',
                              datefmt='%Y-%m-%d %H:%M:%S')
        )
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


# ═══════════════════════════════════════════════════════════════════════════
#  1. SUREFIRE CYCLE SIMULATOR
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class CycleResult:
    """Outcome of one complete surefire hedge cycle."""
    level_reached: int          # highest level entered (0-based); -1 means nothing executed
    bust: bool                  # True if all levels exhausted without TP
    pnl: float                  # net P&L of the cycle (in price units, scaled by lot sizes)
    entry_price: float          # price at cycle entry (L0)
    exit_price: float           # price at cycle exit (TP hit or last SL)
    bars_held: int              # number of 5m bars from entry to exit
    entry_idx: int = 0          # candle index where cycle started
    exit_idx: int = 0           # candle index where cycle ended
    direction: int = 1          # initial direction: 1=long, -1=short
    level_details: list = field(default_factory=list)  # per-level info

    def to_dict(self) -> dict:
        return asdict(self)


class SurefireCycleSimulator:
    """Simulate multi-level surefire hedge cycles on OHLCV candle arrays.

    Parameters
    ----------
    n_levels : int
        Maximum number of hedge levels (bust if all exhausted).
    multiplier : float
        Position size multiplier per level. Level i size = base * multiplier^i.
    base_pct : float
        Base position size as fraction of equity (used for P&L scaling).
    tp_atr_mult : float
        Take-profit distance = tp_atr_mult * ATR at entry.
    hedge_atr_mult : float
        Hedge (stop) distance = tp_dist / hedge_ratio.
        Equivalently: hedge_dist = tp_atr_mult * ATR / hedge_ratio.
    hedge_ratio : float
        Ratio TP/hedge. hedge_dist = tp_dist / hedge_ratio.
    max_bars_per_level : int
        Safety timeout per level (bars). Timeout = inconclusive.
    """

    def __init__(
        self,
        n_levels: int = 12,
        multiplier: float = None,
        base_pct: float = 0.005,
        tp_atr_mult: float = 0.8,
        hedge_ratio: float = 2.0,
        max_bars_per_level: int = 500,
    ):
        self.n_levels = n_levels
        # Default multiplier: sqrt(2)
        self.multiplier = multiplier if multiplier is not None else np.sqrt(2)
        self.base_pct = base_pct
        self.tp_atr_mult = tp_atr_mult
        self.hedge_ratio = hedge_ratio
        self.max_bars_per_level = max_bars_per_level

    def _level_size(self, level: int) -> float:
        """Position size at *level* as a multiple of base."""
        return self.multiplier ** level

    def simulate_cycle(
        self,
        candles_5m: np.ndarray,
        entry_idx: int,
        atr_value: float,
        initial_direction: int = 1,
    ) -> Optional[CycleResult]:
        """Run one complete hedge cycle starting at *entry_idx*.

        Parameters
        ----------
        candles_5m : np.ndarray
            Full 5m candle array [timestamp, open, close, high, low, volume].
        entry_idx : int
            Index into *candles_5m* where L0 enters.
        atr_value : float
            ATR value at entry (used to compute TP/hedge distances).
        initial_direction : int
            1 for long, -1 for short.

        Returns
        -------
        CycleResult or None if data runs out or ATR is invalid.
        """
        if np.isnan(atr_value) or atr_value <= 0:
            return None

        highs = candles_5m[:, 3]
        lows = candles_5m[:, 4]
        closes = candles_5m[:, 2]
        n_bars = len(candles_5m)

        tp_dist = atr_value * self.tp_atr_mult
        hedge_dist = tp_dist / self.hedge_ratio

        entry_price_l0 = closes[entry_idx]
        entry_price = entry_price_l0
        direction = initial_direction
        current_bar = entry_idx + 1

        total_pnl = 0.0
        level_details = []

        for level in range(self.n_levels):
            size_mult = self._level_size(level)

            if direction == 1:  # long
                tp_price = entry_price + tp_dist
                sl_price = entry_price - hedge_dist
            else:  # short
                tp_price = entry_price - tp_dist
                sl_price = entry_price + hedge_dist

            max_bar = min(current_bar + self.max_bars_per_level, n_bars)
            outcome = None

            for j in range(current_bar, max_bar):
                h = highs[j]
                l = lows[j]

                if direction == 1:
                    # Conservative: if both hit on same bar, assume SL first
                    if l <= sl_price and h >= tp_price:
                        outcome = 'sl'
                    elif h >= tp_price:
                        outcome = 'tp'
                    elif l <= sl_price:
                        outcome = 'sl'
                else:
                    if h >= sl_price and l <= tp_price:
                        outcome = 'sl'
                    elif l <= tp_price:
                        outcome = 'tp'
                    elif h >= sl_price:
                        outcome = 'sl'

                if outcome is not None:
                    end_bar = j
                    break
            else:
                # Timeout — ran out of bars for this level
                return None

            level_pnl = 0.0
            if outcome == 'tp':
                level_pnl = tp_dist * size_mult
                total_pnl += level_pnl
                # Subtract losses from all previous levels
                for prev in level_details:
                    total_pnl -= prev['hedge_dist'] * prev['size_mult']
                    level_details[level_details.index(prev)]['pnl'] = \
                        -prev['hedge_dist'] * prev['size_mult']

                # Recalculate: total_pnl = tp_win - sum(prev losses)
                # Actually recompute cleanly:
                total_pnl = tp_dist * size_mult
                for prev in level_details:
                    total_pnl += prev['pnl']

                level_details.append({
                    'level': level, 'outcome': 'tp', 'direction': direction,
                    'entry_price': entry_price, 'size_mult': size_mult,
                    'tp_dist': tp_dist, 'hedge_dist': hedge_dist,
                    'pnl': tp_dist * size_mult, 'end_bar': end_bar,
                })

                return CycleResult(
                    level_reached=level,
                    bust=False,
                    pnl=total_pnl,
                    entry_price=entry_price_l0,
                    exit_price=tp_price,
                    bars_held=end_bar - entry_idx,
                    entry_idx=entry_idx,
                    exit_idx=end_bar,
                    direction=initial_direction,
                    level_details=level_details,
                )

            elif outcome == 'sl':
                level_pnl = -hedge_dist * size_mult
                level_details.append({
                    'level': level, 'outcome': 'sl', 'direction': direction,
                    'entry_price': entry_price, 'size_mult': size_mult,
                    'tp_dist': tp_dist, 'hedge_dist': hedge_dist,
                    'pnl': level_pnl, 'end_bar': end_bar,
                })

                # Next level: flip direction, new entry at SL price
                entry_price = sl_price
                direction *= -1
                current_bar = end_bar + 1

                if current_bar >= n_bars:
                    return None  # ran out of data

        # All levels exhausted — BUST
        total_pnl = sum(d['pnl'] for d in level_details)
        last_bar = level_details[-1]['end_bar'] if level_details else entry_idx

        return CycleResult(
            level_reached=self.n_levels - 1,
            bust=True,
            pnl=total_pnl,
            entry_price=entry_price_l0,
            exit_price=sl_price,
            bars_held=last_bar - entry_idx,
            entry_idx=entry_idx,
            exit_idx=last_bar,
            direction=initial_direction,
            level_details=level_details,
        )

    def run_on_signals(
        self,
        candles_5m: np.ndarray,
        atr_array: np.ndarray,
        signals: List[Tuple[int, int]],
    ) -> List[CycleResult]:
        """Run cycle simulation on a list of entry signals.

        Signals are processed in order; overlapping cycles are skipped (a new
        cycle cannot start before the previous one ends).

        Parameters
        ----------
        candles_5m : candle array
        atr_array : ATR values aligned with candles_5m
        signals : list of (bar_index, direction) tuples; direction 1=long, -1=short

        Returns
        -------
        List of CycleResult (excluding None / timeout results).
        """
        results = []
        next_allowed_bar = 0

        for bar_idx, direction in signals:
            if bar_idx < next_allowed_bar:
                continue
            atr_val = atr_array[bar_idx]
            result = self.simulate_cycle(candles_5m, bar_idx, atr_val, direction)
            if result is None:
                continue
            results.append(result)
            next_allowed_bar = result.exit_idx + 1

        return results


# ═══════════════════════════════════════════════════════════════════════════
#  2. RESAMPLING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

# Timeframe string to minutes mapping
_TF_MINUTES = {
    '1m': 1, '5m': 5, '15m': 15, '30m': 30,
    '1h': 60, 'H1': 60, '4h': 240, 'H4': 240,
    '1D': 1440, 'D1': 1440,
}


def resample_candles(candles_1m: np.ndarray, target_tf: str) -> np.ndarray:
    """Resample 1-minute candles to a higher timeframe.

    Parameters
    ----------
    candles_1m : np.ndarray
        1m candles with columns [timestamp, open, close, high, low, volume].
    target_tf : str
        Target timeframe, e.g. '5m', '15m', 'H1', 'H4', 'D1'.

    Returns
    -------
    np.ndarray with the same column layout, resampled.
    """
    target_minutes = _TF_MINUTES.get(target_tf)
    if target_minutes is None:
        raise ValueError(f"Unknown timeframe: {target_tf}. Supported: {list(_TF_MINUTES.keys())}")
    if target_minutes <= 1:
        return candles_1m.copy()

    timestamps = candles_1m[:, 0]
    ms_per_bar = target_minutes * 60 * 1000  # milliseconds

    # Align to timeframe boundaries
    first_ts = timestamps[0]
    aligned_start = first_ts - (first_ts % ms_per_bar)

    # Group candles into bins
    bin_indices = ((timestamps - aligned_start) // ms_per_bar).astype(np.int64)
    unique_bins = np.unique(bin_indices)

    resampled = np.empty((len(unique_bins), 6), dtype=np.float64)

    for i, b in enumerate(unique_bins):
        mask = bin_indices == b
        group = candles_1m[mask]

        resampled[i, 0] = group[0, 0]          # timestamp: first bar's timestamp
        resampled[i, 1] = group[0, 1]          # open: first open
        resampled[i, 2] = group[-1, 2]         # close: last close
        resampled[i, 3] = np.max(group[:, 3])  # high: max high
        resampled[i, 4] = np.min(group[:, 4])  # low: min low
        resampled[i, 5] = np.sum(group[:, 5])  # volume: sum

    return resampled


def resample_all_timeframes(
    candles_1m: np.ndarray,
    timeframes: Tuple[str, ...] = ('5m', '15m', 'H1', 'H4', 'D1'),
) -> Dict[str, np.ndarray]:
    """Resample 1m candles to multiple timeframes.

    Returns a dict keyed by timeframe string.
    """
    result = {'1m': candles_1m}
    for tf in timeframes:
        result[tf] = resample_candles(candles_1m, tf)
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  3. FEATURE COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════

def _rolling_hurst_rs(closes: np.ndarray, window: int = 20) -> np.ndarray:
    """Compute rolling Hurst exponent using the R/S method.

    The qengine ta.hurst_exponent() returns a scalar and does not support
    sequential mode, so we implement a lightweight rolling R/S version here.

    Returns an array of the same length as *closes* (NaN-padded at the start).
    """
    n = len(closes)
    hurst = np.full(n, np.nan)

    for i in range(window, n):
        segment = closes[i - window:i]
        returns = np.diff(segment)
        if len(returns) < 4 or np.std(returns) == 0:
            continue

        # R/S calculation on the returns
        mean_r = np.mean(returns)
        cumdev = np.cumsum(returns - mean_r)
        r = np.max(cumdev) - np.min(cumdev)
        s = np.std(returns, ddof=1)
        if s > 0 and r > 0:
            rs = r / s
            # H ~ log(R/S) / log(n)
            hurst[i] = np.log(rs) / np.log(len(returns))

    return hurst


def _rolling_range_atr(candles: np.ndarray, period: int = 20) -> np.ndarray:
    """Rolling (max high - min low) / ATR over *period* bars.

    Returns array aligned with candles (NaN-padded at start).
    """
    n = len(candles)
    highs = candles[:, 3]
    lows = candles[:, 4]
    atr_arr = ta.atr(candles, period=14, sequential=True)

    result = np.full(n, np.nan)
    for i in range(period, n):
        rng = np.max(highs[i - period:i]) - np.min(lows[i - period:i])
        a = atr_arr[i]
        if not np.isnan(a) and a > 0:
            result[i] = rng / a

    return result


def compute_regime_features(candles: np.ndarray, period: int = 14) -> Dict[str, np.ndarray]:
    """Compute 5 regime-descriptor features for a single timeframe.

    Features (all sequential arrays):
    1. choppiness  — Choppiness Index (14)
    2. hurst       — Rolling Hurst exponent (R/S, 20-bar window)
    3. atr_ratio   — ATR(14) / ATR(50)
    4. adx         — Average Directional Index (14)
    5. range_atr   — 20-bar range / ATR(14)

    Parameters
    ----------
    candles : np.ndarray
        OHLCV candles for one timeframe.
    period : int
        Base period for indicators.

    Returns
    -------
    Dict mapping feature name to np.ndarray (same length as candles).
    """
    closes = candles[:, 2]

    choppiness = ta.chop(candles, period=period, sequential=True)
    hurst = _rolling_hurst_rs(closes, window=20)
    atr14 = ta.atr(candles, period=14, sequential=True)
    atr50 = ta.atr(candles, period=50, sequential=True)

    # Safe division — avoid divide-by-zero
    with np.errstate(divide='ignore', invalid='ignore'):
        atr_ratio = np.where((atr50 > 0) & ~np.isnan(atr50), atr14 / atr50, np.nan)

    adx_arr = ta.adx(candles, period=period, sequential=True)
    range_atr = _rolling_range_atr(candles, period=20)

    return {
        'choppiness': choppiness,
        'hurst': hurst,
        'atr_ratio': atr_ratio,
        'adx': adx_arr,
        'range_atr': range_atr,
    }


def compute_multi_tf_features(
    candles_dict: Dict[str, np.ndarray],
    base_tf: str = '5m',
    timeframes: Tuple[str, ...] = ('5m', '15m', 'H1', 'H4', 'D1'),
) -> Tuple[np.ndarray, List[str]]:
    """Compute 25 regime features (5 features x 5 timeframes).

    Higher-timeframe features are forward-filled to align with the base
    timeframe timestamps.

    Parameters
    ----------
    candles_dict : dict
        Mapping timeframe -> candle array. Must include *base_tf* and all
        entries in *timeframes*.
    base_tf : str
        The base timeframe to align everything to.
    timeframes : tuple of str
        Timeframes to compute features for.

    Returns
    -------
    (feature_matrix, column_names)
        feature_matrix : np.ndarray of shape (n_base_bars, 25)
        column_names   : list of 25 feature names like 'H1_choppiness'
    """
    base_candles = candles_dict[base_tf]
    base_ts = base_candles[:, 0]
    n_base = len(base_candles)
    feature_names = ['choppiness', 'hurst', 'atr_ratio', 'adx', 'range_atr']

    all_columns = []
    col_names = []

    for tf in timeframes:
        candles_tf = candles_dict[tf]
        features = compute_regime_features(candles_tf)

        if tf == base_tf:
            # Already aligned
            for fname in feature_names:
                all_columns.append(features[fname])
                col_names.append(f'{tf}_{fname}')
        else:
            # Forward-fill higher TF features onto base TF timestamps
            tf_ts = candles_tf[:, 0]
            for fname in feature_names:
                arr = features[fname]
                aligned = _forward_fill_align(tf_ts, arr, base_ts)
                all_columns.append(aligned)
                col_names.append(f'{tf}_{fname}')

    feature_matrix = np.column_stack(all_columns)
    return feature_matrix, col_names


def _forward_fill_align(
    source_ts: np.ndarray,
    source_vals: np.ndarray,
    target_ts: np.ndarray,
) -> np.ndarray:
    """Align *source_vals* (at *source_ts*) to *target_ts* via forward-fill.

    For each target timestamp, use the most recent source value whose
    timestamp is <= the target timestamp.
    """
    result = np.full(len(target_ts), np.nan)
    src_idx = 0
    n_src = len(source_ts)

    for i, t in enumerate(target_ts):
        # Advance source index to the latest timestamp <= t
        while src_idx < n_src - 1 and source_ts[src_idx + 1] <= t:
            src_idx += 1
        if source_ts[src_idx] <= t:
            result[i] = source_vals[src_idx]

    return result


# ═══════════════════════════════════════════════════════════════════════════
#  4. DATA I/O HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def save_results(data: Any, name: str, directory: str = None) -> str:
    """Save results to an appropriate format based on type/extension.

    - numpy array -> .npy
    - dict/list with simple types -> .json
    - anything with .to_parquet -> .parquet (pandas DataFrame)
    - fallback -> .pkl

    Parameters
    ----------
    data : any
        The data to save.
    name : str
        Filename (without or with extension). If no extension, one is chosen
        automatically.
    directory : str
        Directory to save in. Defaults to DATA_DIR.

    Returns
    -------
    The full path written.
    """
    ensure_data_dir()
    directory = directory or DATA_DIR
    os.makedirs(directory, exist_ok=True)

    base, ext = os.path.splitext(name)

    if ext == '':
        # Auto-detect format
        if isinstance(data, np.ndarray):
            ext = '.npy'
        elif hasattr(data, 'to_parquet'):
            ext = '.parquet'
        elif isinstance(data, (dict, list)):
            # Check if JSON-serialisable
            try:
                json.dumps(data, default=str)
                ext = '.json'
            except (TypeError, ValueError):
                ext = '.pkl'
        else:
            ext = '.pkl'

    path = os.path.join(directory, base + ext)

    if ext == '.npy':
        np.save(path, data)
    elif ext == '.parquet':
        data.to_parquet(path, index=False)
    elif ext == '.json':
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    elif ext == '.pkl':
        with open(path, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    else:
        # Unknown extension — pickle
        with open(path, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    return path


def load_results(name: str, directory: str = None) -> Any:
    """Load previously saved results.

    The extension in *name* determines the loader:
    - .npy   -> np.load
    - .parquet -> pandas read_parquet
    - .json  -> json.load
    - .pkl   -> pickle.load

    If *name* has no extension, we try .parquet, .npy, .json, .pkl in order.
    """
    directory = directory or DATA_DIR
    base, ext = os.path.splitext(name)

    if ext == '':
        # Try common extensions
        for try_ext in ('.parquet', '.npy', '.json', '.pkl'):
            path = os.path.join(directory, base + try_ext)
            if os.path.exists(path):
                ext = try_ext
                break
        else:
            raise FileNotFoundError(
                f"No file found for '{name}' in {directory} "
                f"(tried .parquet, .npy, .json, .pkl)"
            )

    path = os.path.join(directory, base + ext)

    if ext == '.npy':
        return np.load(path, allow_pickle=True)
    elif ext == '.parquet':
        import pandas as pd
        return pd.read_parquet(path)
    elif ext == '.json':
        with open(path, 'r') as f:
            return json.load(f)
    elif ext == '.pkl':
        with open(path, 'rb') as f:
            return pickle.load(f)
    else:
        raise ValueError(f"Unknown extension: {ext}")


# ═══════════════════════════════════════════════════════════════════════════
#  5. EVALUATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def permutation_test(
    metric_func: Callable[[np.ndarray], float],
    labels: np.ndarray,
    n_permutations: int = 1000,
    seed: int = 42,
) -> Tuple[float, float, np.ndarray]:
    """Non-parametric permutation test for a metric that depends on labels.

    Computes the observed metric, then shuffles labels *n_permutations* times
    and recomputes, producing a null distribution. The p-value is the fraction
    of permuted metrics >= the observed metric.

    Parameters
    ----------
    metric_func : callable
        A function that takes a 1D label array and returns a scalar metric.
        Higher values = stronger signal (e.g. variance of bust rate across regimes).
    labels : np.ndarray
        The real labels (e.g. regime assignments).
    n_permutations : int
        Number of random shuffles.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    (p_value, observed_metric, null_distribution)
    """
    rng = np.random.RandomState(seed)
    observed = metric_func(labels)

    null_dist = np.empty(n_permutations)
    shuffled = labels.copy()
    for i in range(n_permutations):
        rng.shuffle(shuffled)
        null_dist[i] = metric_func(shuffled)

    p_value = np.mean(null_dist >= observed)
    return p_value, observed, null_dist


def deflated_sharpe(
    observed_sr: float,
    n_trials: int,
    n_observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

    Accounts for multiple testing: if you tried *n_trials* strategies, the
    expected maximum Sharpe from pure noise is high. DSR tests whether the
    observed Sharpe exceeds this threshold.

    Parameters
    ----------
    observed_sr : float
        The observed (annualised) Sharpe ratio.
    n_trials : int
        Number of strategy/parameter combinations tested.
    n_observations : int
        Number of return observations used to compute the Sharpe.
    skewness : float
        Skewness of returns (0 for normal).
    kurtosis : float
        Kurtosis of returns (3 for normal).

    Returns
    -------
    dsr : float
        The deflated Sharpe ratio. Values > ~2.0 suggest the observed SR
        is unlikely to be due to multiple testing.
    """
    from scipy.stats import norm

    # Expected maximum SR under the null (Euler-Mascheroni approximation)
    euler_mascheroni = 0.5772156649
    if n_trials < 1:
        n_trials = 1
    expected_max_sr = np.sqrt(2 * np.log(n_trials)) - \
        (np.log(np.pi) + euler_mascheroni) / (2 * np.sqrt(2 * np.log(n_trials))) \
        if n_trials > 1 else 0.0

    # Standard error of the Sharpe ratio
    sr_se = np.sqrt(
        (1 - skewness * observed_sr + ((kurtosis - 1) / 4) * observed_sr ** 2)
        / n_observations
    ) if n_observations > 0 else 1.0

    if sr_se <= 0:
        sr_se = 1e-10

    # DSR = Prob(SR* < observed | H0: SR* ~ expected_max)
    dsr = norm.cdf((observed_sr - expected_max_sr) / sr_se)
    return dsr


def walk_forward_split(
    years: np.ndarray,
    train_start: int = 2006,
) -> List[Tuple[List[int], int]]:
    """Generate expanding-window walk-forward splits.

    Each split trains on [train_start, ..., test_year-1] and tests on
    test_year.

    Parameters
    ----------
    years : np.ndarray or list
        All available years in the dataset (e.g. [2006, 2007, ..., 2025]).
    train_start : int
        First year to include in training.

    Returns
    -------
    List of (train_years, test_year) tuples.
    """
    years = sorted(set(years))
    splits = []
    for i, y in enumerate(years):
        if y <= train_start:
            continue
        train_years = [yr for yr in years if train_start <= yr < y]
        if len(train_years) >= 1:
            splits.append((train_years, y))
    return splits


# ═══════════════════════════════════════════════════════════════════════════
#  6. CONVENIENCE: DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════

def load_candles(
    exchange: str = 'OANDA',
    symbol: str = 'EUR-USD',
    timeframe: str = '1m',
    start_date: str = '2006-01-01',
    end_date: str = '2026-03-21',
    warmup_candles_num: int = 0,
) -> np.ndarray:
    """Load candles from the database, handling warmup concatenation.

    Returns a single contiguous array (warmup prepended if available).
    """
    warmup, trading = get_candles(
        exchange, symbol, timeframe,
        jh.date_to_timestamp(start_date),
        jh.date_to_timestamp(end_date),
        warmup_candles_num=warmup_candles_num,
    )
    if warmup is not None and warmup.ndim == 2 and len(warmup) > 0:
        return np.concatenate([warmup, trading], axis=0)
    return trading


def find_ema_crossover_signals(
    candles: np.ndarray,
    fast_period: int = 8,
    slow_period: int = 21,
    atr_period: int = 14,
    min_start: int = None,
) -> Tuple[List[Tuple[int, int]], np.ndarray]:
    """Find EMA crossover signals on candle array.

    Parameters
    ----------
    candles : np.ndarray
        OHLCV candles.
    fast_period, slow_period : int
        EMA periods.
    atr_period : int
        ATR period (used to validate ATR is available).
    min_start : int
        Minimum bar index to start scanning. Defaults to max(atr_period+5, slow_period+5).

    Returns
    -------
    (signals, atr_array)
        signals : list of (bar_index, direction) where direction is 1 (long) or -1 (short)
        atr_array : full ATR array aligned with candles
    """
    ema_fast = ta.ema(candles, period=fast_period, sequential=True)
    ema_slow = ta.ema(candles, period=slow_period, sequential=True)
    atr_arr = ta.atr(candles, period=atr_period, sequential=True)

    if min_start is None:
        min_start = max(atr_period + 5, slow_period + 5)

    signals = []
    for i in range(min_start, len(candles)):
        if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]):
            continue
        if np.isnan(ema_fast[i - 1]) or np.isnan(ema_slow[i - 1]):
            continue
        if np.isnan(atr_arr[i]) or atr_arr[i] <= 0:
            continue

        # Bullish crossover
        if ema_fast[i - 1] <= ema_slow[i - 1] and ema_fast[i] > ema_slow[i]:
            signals.append((i, 1))
        # Bearish crossover
        elif ema_fast[i - 1] >= ema_slow[i - 1] and ema_fast[i] < ema_slow[i]:
            signals.append((i, -1))

    return signals, atr_arr


# ═══════════════════════════════════════════════════════════════════════════
#  7. SUMMARY STATISTICS
# ═══════════════════════════════════════════════════════════════════════════

def cycle_summary(cycles: List[CycleResult]) -> Dict[str, Any]:
    """Compute summary statistics from a list of CycleResult objects."""
    if not cycles:
        return {'n_cycles': 0}

    n = len(cycles)
    wins = [c for c in cycles if not c.bust]
    busts = [c for c in cycles if c.bust]
    pnls = [c.pnl for c in cycles]

    win_pnls = [c.pnl for c in wins]
    bust_pnls = [c.pnl for c in busts]

    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf')

    # Level distribution
    level_dist = {}
    for c in cycles:
        key = c.level_reached if not c.bust else 'bust'
        level_dist[key] = level_dist.get(key, 0) + 1

    return {
        'n_cycles': n,
        'n_wins': len(wins),
        'n_busts': len(busts),
        'win_rate': len(wins) / n * 100,
        'bust_rate': len(busts) / n * 100,
        'avg_win_pnl': float(np.mean(win_pnls)) if win_pnls else 0.0,
        'avg_bust_pnl': float(np.mean(bust_pnls)) if bust_pnls else 0.0,
        'net_pnl': float(sum(pnls)),
        'profit_factor': pf,
        'avg_bars_held': float(np.mean([c.bars_held for c in cycles])),
        'level_dist': level_dist,
        'bust_erase_ratio': abs(np.mean(bust_pnls) / np.mean(win_pnls))
            if win_pnls and bust_pnls else 0.0,
    }
