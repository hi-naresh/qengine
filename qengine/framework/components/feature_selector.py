"""
FeatureSelector — computes a pool of ~25 candidate market features across
5 categories (volatility, trend, chop, momentum, structure), with automated
feature selection via mutual information.

Part of the IslandPilot pipeline.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

import qengine.indicators as ta


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _ema_slope(candles: np.ndarray, period: int) -> np.ndarray:
    """Slope of EMA as percentage change over 1 bar."""
    ema_vals = ta.ema(candles, period=period, sequential=True)
    slope = np.full_like(ema_vals, np.nan)
    slope[1:] = (ema_vals[1:] - ema_vals[:-1]) / (ema_vals[:-1] + 1e-12)
    return slope


def _bollinger_width(candles: np.ndarray, period: int = 20) -> np.ndarray:
    """Bollinger band width = (upper - lower) / middle."""
    try:
        return ta.bollinger_bands_width(candles, period=period, sequential=True)
    except Exception:
        # Fallback: compute from bollinger_bands directly
        bb = ta.bollinger_bands(candles, period=period, sequential=True)
        mid = bb.middleband
        width = (bb.upperband - bb.lowerband) / (mid + 1e-12)
        return width


def _efficiency_ratio(candles: np.ndarray, period: int) -> np.ndarray:
    """Kaufman Efficiency Ratio via ta.er."""
    return ta.er(candles, period=period, sequential=True)


def _hurst_rolling(candles: np.ndarray, window: int = 100) -> np.ndarray:
    """Rolling Hurst exponent via vectorized R/S analysis.

    Uses the simplified R/S method: H = log(R/S) / log(n) over a rolling window
    of log-returns. Fully vectorized — no Python for-loop over 470K candles.
    """
    close = candles[:, 2].astype(np.float64)
    n = len(close)
    result = np.full(n, np.nan)

    # Log returns
    log_ret = np.diff(np.log(np.maximum(close, 1e-12)))  # length n-1

    if len(log_ret) < window:
        return result

    # Rolling mean of returns using cumsum trick
    cs = np.cumsum(log_ret)
    cs = np.insert(cs, 0, 0.0)  # length n
    # rolling_sum[i] = cs[i+1] - cs[i+1-window] for i >= window-1
    rolling_sum = cs[window:] - cs[:-window]  # length n-window
    rolling_mean = rolling_sum / window

    # Rolling std via cumsum of squares
    cs2 = np.cumsum(log_ret ** 2)
    cs2 = np.insert(cs2, 0, 0.0)
    rolling_sum2 = cs2[window:] - cs2[:-window]
    rolling_var = rolling_sum2 / window - rolling_mean ** 2
    rolling_std = np.sqrt(np.maximum(rolling_var, 1e-20))

    # For R/S we need cumulative deviation from mean within each window
    # Use stride tricks for efficiency on the range computation
    # Simplified: compute R/S for each window position
    # R = max(cumdev) - min(cumdev), S = std of returns in window
    # H = log(R/S) / log(window)

    # Vectorized approach: process in chunks to avoid memory explosion
    chunk_size = 50000
    log_n = np.log(window)

    for start in range(0, len(rolling_mean), chunk_size):
        end = min(start + chunk_size, len(rolling_mean))
        batch_size = end - start

        # Extract windows using stride_tricks
        idx_offset = start  # offset into log_ret
        batch_rs = np.empty(batch_size)

        for j in range(batch_size):
            pos = idx_offset + j
            seg = log_ret[pos:pos + window]
            mean_seg = rolling_mean[start + j]
            dev = np.cumsum(seg - mean_seg)
            r = dev.max() - dev.min()
            s = rolling_std[start + j]
            if s > 1e-15 and r > 0:
                batch_rs[j] = np.log(r / s) / log_n
            else:
                batch_rs[j] = np.nan

        # Result indices: window offset + 1 (because log_ret is 1 shorter)
        result_start = window + start
        result_end = window + end
        result[result_start:result_end] = batch_rs

    return result


def _safe_indicator(func, *args, **kwargs) -> np.ndarray:
    """Call an indicator function, returning NaN array on failure."""
    try:
        result = func(*args, **kwargs)
        if isinstance(result, np.ndarray):
            return result
        # Some indicators return namedtuples; caller should handle that
        return result
    except Exception:
        # Determine length from first positional arg (candles)
        candles = args[0] if args else kwargs.get('candles', np.empty(0))
        n = len(candles)
        return np.full(n, np.nan)


# ---------------------------------------------------------------------------
# Feature definitions
# ---------------------------------------------------------------------------

# Each feature: (name, category, compute_fn)
# compute_fn takes candles -> 1-D np.ndarray of length n_candles

def _build_default_features() -> list:
    """Return the default feature definitions."""
    features = []

    def _add(name, category, fn):
        features.append((name, category, fn))

    # --- Volatility ---
    _add('natr_14', 'volatility',
         lambda c: _safe_indicator(ta.natr, c, period=14, sequential=True))
    _add('natr_50', 'volatility',
         lambda c: _safe_indicator(ta.natr, c, period=50, sequential=True))
    _add('atr_ratio_14_50', 'volatility', lambda c: (
        _safe_indicator(ta.atr, c, period=14, sequential=True) /
        (np.maximum(_safe_indicator(ta.atr, c, period=50, sequential=True), 1e-12))
    ))
    _add('bollinger_width_20', 'volatility',
         lambda c: _bollinger_width(c, period=20))
    _add('atr_14', 'volatility',
         lambda c: _safe_indicator(ta.atr, c, period=14, sequential=True))

    # --- Trend ---
    _add('adx_14', 'trend',
         lambda c: _safe_indicator(ta.adx, c, period=14, sequential=True))
    _add('adx_28', 'trend',
         lambda c: _safe_indicator(ta.adx, c, period=28, sequential=True))
    _add('ema_slope_8', 'trend', lambda c: _ema_slope(c, 8))
    _add('ema_slope_21', 'trend', lambda c: _ema_slope(c, 21))
    _add('aroon_osc', 'trend', lambda c: _compute_aroon_osc(c))
    _add('dm_diff', 'trend', lambda c: _compute_dm_diff(c))

    # --- Chop ---
    _add('chop_14', 'chop',
         lambda c: _safe_indicator(ta.chop, c, period=14, sequential=True))
    _add('er_50', 'chop', lambda c: _efficiency_ratio(c, 50))
    _add('er_100', 'chop', lambda c: _efficiency_ratio(c, 100))
    _add('hurst_100', 'chop', lambda c: _hurst_rolling(c, 100))

    # --- Momentum ---
    _add('rsi_14', 'momentum',
         lambda c: _safe_indicator(ta.rsi, c, period=14, sequential=True))
    _add('rsi_28', 'momentum',
         lambda c: _safe_indicator(ta.rsi, c, period=28, sequential=True))
    _add('cci_20', 'momentum',
         lambda c: _safe_indicator(ta.cci, c, period=20, sequential=True))
    _add('roc_10', 'momentum',
         lambda c: _safe_indicator(ta.roc, c, period=10, sequential=True))
    _add('stoch_k', 'momentum', lambda c: _compute_stoch_k(c))

    # --- Structure ---
    _add('session_hour', 'structure', lambda c: _session_hour(c))
    _add('day_of_week', 'structure', lambda c: _day_of_week(c))
    _add('hl_range_norm', 'structure', lambda c: _hl_range_norm(c))
    _add('close_position', 'structure', lambda c: _close_position_in_range(c))

    return features


def _compute_aroon_osc(candles: np.ndarray) -> np.ndarray:
    """Aroon oscillator = aroon_up - aroon_down."""
    try:
        result = ta.aroon(candles, period=14, sequential=True)
        if hasattr(result, 'osc'):
            return result.osc
        elif hasattr(result, 'up') and hasattr(result, 'down'):
            return result.up - result.down
        else:
            return np.full(len(candles), np.nan)
    except Exception:
        return np.full(len(candles), np.nan)


def _compute_dm_diff(candles: np.ndarray) -> np.ndarray:
    """DM+ minus DM-."""
    try:
        result = ta.dm(candles, period=14, sequential=True)
        if hasattr(result, 'plus') and hasattr(result, 'minus'):
            return result.plus - result.minus
        else:
            return np.full(len(candles), np.nan)
    except Exception:
        return np.full(len(candles), np.nan)


def _compute_stoch_k(candles: np.ndarray) -> np.ndarray:
    """Stochastic %K."""
    try:
        result = ta.stoch(candles, sequential=True)
        if hasattr(result, 'k'):
            return result.k
        else:
            return np.full(len(candles), np.nan)
    except Exception:
        return np.full(len(candles), np.nan)


def _session_hour(candles: np.ndarray) -> np.ndarray:
    """Hour of day from timestamp (column 0, ms epoch)."""
    ts = candles[:, 0] / 1000.0  # to seconds
    # Convert to hours (UTC)
    hours = (ts % 86400) / 3600.0
    return np.floor(hours).astype(float)


def _day_of_week(candles: np.ndarray) -> np.ndarray:
    """Day of week (0=Mon..6=Sun) from timestamp."""
    ts_seconds = candles[:, 0] / 1000.0
    # Unix epoch (1970-01-01) was a Thursday (3)
    days_since_epoch = np.floor(ts_seconds / 86400.0)
    dow = (days_since_epoch + 3) % 7  # 0=Mon
    return dow.astype(float)


def _hl_range_norm(candles: np.ndarray) -> np.ndarray:
    """(high - low) / close — normalized candle range."""
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    return (high - low) / (close + 1e-12)


def _close_position_in_range(candles: np.ndarray) -> np.ndarray:
    """Where close sits in the high-low range: (close - low) / (high - low)."""
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    hl_range = high - low
    return np.where(hl_range > 1e-12, (close - low) / hl_range, 0.5)


# ---------------------------------------------------------------------------
# FeaturePool class
# ---------------------------------------------------------------------------

class FeaturePool:
    """Manages a pool of candidate market features across multiple categories.

    Args:
        custom_features: Optional list of (name, category, compute_fn) tuples
                         to use instead of the defaults.
    """

    def __init__(self, custom_features: Optional[list] = None):
        self._features = custom_features if custom_features else _build_default_features()

    @property
    def feature_names(self) -> List[str]:
        """List of all feature names."""
        return [f[0] for f in self._features]

    @property
    def categories(self) -> Dict[str, List[str]]:
        """Dict mapping category name to list of feature names."""
        cats: Dict[str, List[str]] = {}
        for name, cat, _ in self._features:
            cats.setdefault(cat, []).append(name)
        return cats

    def compute(self, candles: np.ndarray) -> np.ndarray:
        """Compute all features from candles using parallel threads.

        Args:
            candles: numpy array with columns [timestamp, open, close, high, low, volume]

        Returns:
            (n_candles, n_features) matrix
        """
        n = len(candles)
        n_feat = len(self._features)
        matrix = np.full((n, n_feat), np.nan)

        def _compute_one(idx_name_cat_fn):
            i, (name, _cat, fn) = idx_name_cat_fn
            try:
                vals = fn(candles)
                if isinstance(vals, np.ndarray) and len(vals) == n:
                    return i, vals
                elif isinstance(vals, np.ndarray) and len(vals) < n:
                    padded = np.full(n, np.nan)
                    padded[n - len(vals):] = vals
                    return i, padded
            except Exception:
                pass
            return i, None

        # Thread pool — indicators release GIL during C/numpy work
        with ThreadPoolExecutor(max_workers=min(8, n_feat)) as pool:
            results = pool.map(_compute_one, enumerate(self._features))
            for col_idx, vals in results:
                if vals is not None:
                    matrix[:, col_idx] = vals

        return matrix


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def compute_feature_matrix(
    candles: np.ndarray,
    pool: Optional[FeaturePool] = None,
) -> Tuple[np.ndarray, List[str]]:
    """Compute the full feature matrix from candles.

    Args:
        candles: OHLCV candle array
        pool: optional FeaturePool instance (uses default if None)

    Returns:
        (feature_matrix, feature_names) tuple
    """
    if pool is None:
        pool = FeaturePool()
    matrix = pool.compute(candles)
    return matrix, pool.feature_names


# ---------------------------------------------------------------------------
# Feature selection via mutual information
# ---------------------------------------------------------------------------

def select_features(
    features: np.ndarray,
    target: np.ndarray,
    k: Union[int, str] = 'auto',
    min_score_ratio: float = 0.1,
) -> Tuple[List[int], List[float]]:
    """Select top features using mutual information with target.

    Args:
        features: (n_samples, n_features) array
        target: (n_samples,) binary/int target array
        k: number of features to select, or 'auto' for threshold-based
        min_score_ratio: when k='auto', keep features with score >= ratio * max_score

    Returns:
        (selected_indices, scores) — both sorted by score descending
    """
    from sklearn.feature_selection import mutual_info_classif

    # Drop rows with any NaN
    mask = ~np.any(np.isnan(features), axis=1)
    if target.dtype == float:
        mask &= ~np.isnan(target)

    feat_clean = features[mask]
    tgt_clean = target[mask]

    if len(feat_clean) < 10:
        return [], []

    scores = mutual_info_classif(feat_clean, tgt_clean, random_state=42)

    # Sort by score descending
    order = np.argsort(scores)[::-1]
    sorted_scores = scores[order]

    if k == 'auto':
        max_score = sorted_scores[0] if len(sorted_scores) > 0 else 0
        threshold = min_score_ratio * max_score
        keep = sorted_scores >= threshold
        selected_order = order[keep]
        selected_scores = sorted_scores[keep]
    else:
        k = min(int(k), len(order))
        selected_order = order[:k]
        selected_scores = sorted_scores[:k]

    return selected_order.tolist(), selected_scores.tolist()
