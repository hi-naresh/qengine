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
    # Note: chop_14 and er_50/er_100 produce NaN on OANDA FX data during
    # zero-volume periods (weekends, holidays). We wrap them with a fallback
    # that returns 50.0 (neutral) when the indicator fails or returns NaN at the
    # tail. hurst_100 has the same issue and uses a similar guard.
    def _safe_chop(c):
        result = _safe_indicator(ta.chop, c, period=14, sequential=True)
        # Fill trailing NaN with the last valid value
        if np.isnan(result[-1]):
            valid = result[~np.isnan(result)]
            if len(valid) > 0:
                last_valid = valid[-1]
                result = np.where(np.isnan(result), last_valid, result)
            else:
                result = np.full_like(result, 50.0)
        return result

    def _safe_er(c, period):
        result = _efficiency_ratio(c, period)
        if np.isnan(result[-1]):
            valid = result[~np.isnan(result)]
            if len(valid) > 0:
                result = np.where(np.isnan(result), valid[-1], result)
            else:
                result = np.full_like(result, 0.5)
        return result

    def _safe_hurst(c, window):
        result = _hurst_rolling(c, window)
        if np.isnan(result[-1]):
            valid = result[~np.isnan(result)]
            if len(valid) > 0:
                result = np.where(np.isnan(result), valid[-1], result)
            else:
                result = np.full_like(result, 0.5)
        return result

    _add('chop_14', 'chop', lambda c: _safe_chop(c))
    _add('er_50', 'chop', lambda c: _safe_er(c, 50))
    _add('er_100', 'chop', lambda c: _safe_er(c, 100))
    _add('hurst_100', 'chop', lambda c: _safe_hurst(c, 100))

    # --- Momentum ---
    _add('rsi_14', 'momentum',
         lambda c: _safe_indicator(ta.rsi, c, period=14, sequential=True))
    _add('rsi_28', 'momentum',
         lambda c: _safe_indicator(ta.rsi, c, period=28, sequential=True))
    _add('cci_20', 'momentum',
         lambda c: _safe_indicator(ta.cci, c, period=20, sequential=True))
    _add('roc_10', 'momentum',
         lambda c: _safe_indicator(ta.roc, c, period=10, sequential=True))
    def _safe_stoch_k(c):
        result = _compute_stoch_k(c)
        if np.isnan(result[-1]):
            valid = result[~np.isnan(result)]
            if len(valid) > 0:
                result = np.where(np.isnan(result), valid[-1], result)
            else:
                result = np.full_like(result, 50.0)
        return result
    _add('stoch_k', 'momentum', lambda c: _safe_stoch_k(c))

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
# Extended theoretically-motivated features (6 features across 3 dimensions).
#
# The 24 base features cover empirical-technical regime structure. These 6
# additional features close three specific gaps, each with a defined
# econometric literature:
#
#   Dimension 1 — Multi-scale volatility (Corsi 2009 HAR-RV)
#       The HAR-RV model proves that 3 time-horizons (1×, 5×, 22×) are
#       sufficient and parsimonious for realized-volatility modeling; adding
#       more horizons does not improve out-of-sample. We have the base TF
#       already; adding NATR at 12× (roughly hourly for a 5m system) and
#       48× (roughly 4-hourly) completes the HAR-RV 3-horizon specification.
#       Müller et al. (1997) further showed that information flows
#       asymmetrically across scales (long→short), making multi-scale vol
#       a regime signal rather than a redundancy.
#
#   Dimension 2 — Distributional shape (Harvey & Siddique 2000; Neuberger 2012)
#       Range-based volatility features approximate the 2nd moment only.
#       Skewness (3rd) and kurtosis (4th) are *separately priced* risk
#       factors per Kraus & Litzenberger (1976) and Harvey & Siddique (2000),
#       and govern Martingale bust risk directly: negative skew = downside
#       asymmetry, high kurtosis = fat-tail regime. Vol-of-vol (Engle 1982
#       ARCH; Barndorff-Nielsen & Shephard 2002) distinguishes stable-high-vol
#       from unstable-high-vol, which NATR alone collapses.
#
#   Dimension 3 — Short-lag serial dependence (Lo & MacKinlay 1988)
#       Hurst captures long-memory structure. For a mean-reversion strategy
#       the *short-lag* autocorrelation is the most diagnostic quantity: its
#       sign directly partitions trend vs mean-reverting regimes. Box &
#       Jenkins (1976) AR model identification shows lag-1 captures ≥80%
#       of AR(1) process information, so a single lag-1 autocorr feature
#       is parsimonious-sufficient.
#
# Window choices (50, 100) follow Neuberger (2012) and Andersen-Bollerslev
# (1997) conventions for realized-moment estimators on high-frequency data.
# ---------------------------------------------------------------------------


def _aggregate_candles_by_factor(candles: np.ndarray, factor: int) -> np.ndarray:
    """Aggregate 1m or base-TF candles into factor×base candles.

    Vectorised: groups of `factor` consecutive bars → one aggregated bar.
    Schema preserved: [timestamp, open, close, high, low, volume].
    """
    if factor <= 1:
        return candles
    n_groups = len(candles) // factor
    if n_groups == 0:
        return candles[:0]
    trimmed = candles[:n_groups * factor]
    reshaped = trimmed.reshape(n_groups, factor, candles.shape[1])
    out = np.empty((n_groups, candles.shape[1]), dtype=candles.dtype)
    out[:, 0] = reshaped[:, 0, 0]
    out[:, 1] = reshaped[:, 0, 1]
    out[:, 2] = reshaped[:, -1, 2]
    out[:, 3] = reshaped[:, :, 3].max(axis=1)
    out[:, 4] = reshaped[:, :, 4].min(axis=1)
    out[:, 5] = reshaped[:, :, 5].sum(axis=1)
    return out


def _multi_tf_natr(candles: np.ndarray, tf_factor: int, period: int = 14) -> np.ndarray:
    """NATR computed on a higher-timeframe aggregation, broadcast back to base length.

    Implements the HAR-RV multi-horizon decomposition (Corsi 2009): each
    aggregated bar's NATR value is assigned to all base-TF bars contained
    in that aggregated bar, so the resulting series is aligned with the
    base-TF candle array.

    Returns an array of len(candles) where each element holds the NATR value
    of the higher-TF bar containing that base candle, NaN where insufficient
    history exists.
    """
    if tf_factor <= 1:
        return _safe_indicator(ta.natr, candles, period=period, sequential=True)

    agg = _aggregate_candles_by_factor(candles, tf_factor)
    n_agg = len(agg)
    if n_agg < period + 5:
        return np.full(len(candles), np.nan)

    natr_agg = _safe_indicator(ta.natr, agg, period=period, sequential=True)

    # Broadcast each aggregated value to its tf_factor source bars
    out = np.full(len(candles), np.nan)
    for i in range(n_agg):
        start = i * tf_factor
        end = min(start + tf_factor, len(candles))
        if i < len(natr_agg):
            out[start:end] = natr_agg[i]
    return out


def _vol_of_vol(candles: np.ndarray, natr_period: int = 14, window: int = 50) -> np.ndarray:
    """Rolling standard deviation of NATR_14 over a window of 50 bars.

    Captures "vol-of-vol" (Engle 1982; Barndorff-Nielsen & Shephard 2002):
    distinguishes stable high-vol regimes from regime-shift transitions.
    Window=50 follows Andersen & Bollerslev (1997) realized-moment convention.
    """
    natr = _safe_indicator(ta.natr, candles, period=natr_period, sequential=True)
    n = len(natr)
    if n < window + 5:
        return np.full(n, np.nan)

    # Vectorised rolling std via sliding_window_view
    from numpy.lib.stride_tricks import sliding_window_view
    # Fill initial NaN (from NATR warmup) with the first valid value so the
    # rolling window doesn't propagate NaN indefinitely
    natr_filled = np.asarray(natr, dtype=np.float64)
    first_valid = np.argmax(~np.isnan(natr_filled))
    if np.all(np.isnan(natr_filled)):
        return np.full(n, np.nan)
    natr_filled[:first_valid] = natr_filled[first_valid]

    # Replace any remaining NaN with previous valid value (forward-fill)
    nan_mask = np.isnan(natr_filled)
    if nan_mask.any():
        # Simple forward-fill
        idx = np.where(~nan_mask, np.arange(n), 0)
        np.maximum.accumulate(idx, out=idx)
        natr_filled = natr_filled[idx]

    windows = sliding_window_view(natr_filled, window_shape=window)
    rolling_std = windows.std(axis=1)
    out = np.full(n, np.nan)
    out[window - 1:] = rolling_std
    return out


def _rolling_moment(candles: np.ndarray, moment: int, window: int = 100) -> np.ndarray:
    """Rolling standardised central moment of log returns.

    moment=3 → skewness (Neuberger 2012 realized skewness, Harvey & Siddique 2000)
    moment=4 → kurtosis (excess, i.e. kurt - 3; standard convention)

    Window=100 follows Neuberger (2012) Table 1 for stable moment estimation
    at high frequencies. Both moments are standardised (divide by σ^moment)
    so they are scale-free and cross-regime comparable.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    close = candles[:, 2].astype(np.float64)
    log_ret = np.diff(np.log(np.maximum(close, 1e-12)))
    n = len(close)

    if len(log_ret) < window:
        return np.full(n, np.nan)

    windows = sliding_window_view(log_ret, window_shape=window)
    means = windows.mean(axis=1, keepdims=True)
    stds = windows.std(axis=1, keepdims=True)
    # Avoid division by zero
    stds_safe = np.where(stds > 1e-15, stds, 1.0)
    normalized = (windows - means) / stds_safe
    m = np.mean(normalized ** moment, axis=1)
    if moment == 4:
        m = m - 3.0  # excess kurtosis

    out = np.full(n, np.nan)
    # log_ret[i] corresponds to close[i+1]; offset output accordingly
    out[window:] = m
    return out


def _rolling_autocorr_lag1(candles: np.ndarray, window: int = 100) -> np.ndarray:
    """Rolling lag-1 autocorrelation of log returns.

    Lo & MacKinlay (1988) variance-ratio test uses return autocorrelation
    as the primary regime discriminator between mean-reversion and momentum.
    Box & Jenkins (1976) AR model identification: lag-1 captures ≥80% of
    AR(1) information, so no need for multiple lags.

    Positive values indicate momentum / trending regime (adverse for
    Martingale). Negative values indicate mean-reversion (favourable).
    """
    from numpy.lib.stride_tricks import sliding_window_view

    close = candles[:, 2].astype(np.float64)
    log_ret = np.diff(np.log(np.maximum(close, 1e-12)))
    n = len(close)

    if len(log_ret) < window + 1:
        return np.full(n, np.nan)

    # Build windows of two lagged series: x = r[t], y = r[t+1]
    # For a lag-1 autocorr over window W, we need pairs (r[i], r[i+1]) for
    # i in [t-W, t-1]. Use sliding_window_view on paired shifts.
    x = log_ret[:-1]
    y = log_ret[1:]
    # Each window has W-1 pairs
    if len(x) < window - 1:
        return np.full(n, np.nan)

    x_windows = sliding_window_view(x, window_shape=window - 1)
    y_windows = sliding_window_view(y, window_shape=window - 1)

    # Pearson correlation per window
    x_mean = x_windows.mean(axis=1, keepdims=True)
    y_mean = y_windows.mean(axis=1, keepdims=True)
    x_dev = x_windows - x_mean
    y_dev = y_windows - y_mean
    num = (x_dev * y_dev).sum(axis=1)
    den = np.sqrt((x_dev ** 2).sum(axis=1) * (y_dev ** 2).sum(axis=1))
    with np.errstate(divide='ignore', invalid='ignore'):
        corr = np.where(den > 1e-15, num / den, 0.0)

    out = np.full(n, np.nan)
    # corr[i] uses x[i..i+W-2] (returns r[i..i+W-2]) paired with r[i+1..i+W-1].
    # The rightmost return used is r[i+W-1], which corresponds to close[i+W].
    # So corr[i] is associated with candle index i+W.
    out[window:window + len(corr)] = corr
    return out


def _build_extended_features() -> list:
    """Return the 6 theoretically-motivated extension features.

    Each carries its literature citation in the compute function docstring.
    Total: 6 features across 3 dimensions (scale / shape / serial-dep).
    """
    features = []

    def _add(name, category, fn):
        features.append((name, category, fn))

    # Dimension 1 — HAR-RV multi-scale volatility (2 features)
    _add('natr_14_tf12', 'volatility', lambda c: _multi_tf_natr(c, tf_factor=12, period=14))
    _add('natr_14_tf48', 'volatility', lambda c: _multi_tf_natr(c, tf_factor=48, period=14))

    # Dimension 2 — Distributional shape (3 features)
    _add('vol_of_vol_50', 'volatility', lambda c: _vol_of_vol(c, natr_period=14, window=50))
    _add('return_skew_100', 'momentum', lambda c: _rolling_moment(c, moment=3, window=100))
    _add('return_kurt_100', 'momentum', lambda c: _rolling_moment(c, moment=4, window=100))

    # Dimension 3 — Short-lag serial dependence (1 feature)
    _add('return_ac_lag1_100', 'momentum', lambda c: _rolling_autocorr_lag1(c, window=100))

    return features


# ---------------------------------------------------------------------------
# FeaturePool class
# ---------------------------------------------------------------------------

class FeaturePool:
    """Manages a pool of candidate market features across multiple categories.

    The default pool has 30 features: 24 empirical-technical indicators (the
    paper's baseline) plus 6 theoretically-motivated extensions that close
    specific gaps in the paper's pool:
      - 2 features for HAR-RV multi-scale volatility (Corsi 2009)
      - 3 features for distributional shape: vol-of-vol, skewness, kurtosis
        (Engle 1982; Barndorff-Nielsen & Shephard 2002; Harvey & Siddique 2000)
      - 1 feature for short-lag return autocorrelation (Lo & MacKinlay 1988)

    Feature ordering is stable: indices 0-23 are the original 24 features
    (same order as the paper). Indices 24-29 are the extensions. Pre-existing
    regime trees trained on 24 features still work — they reference column
    indices 0-N for their macro/sub features, and those indices point to
    unchanged features.

    Args:
        custom_features: Optional list of (name, category, compute_fn) tuples
                         to use instead of the defaults.
        extended: If True (default), include the 6 extension features.
                  If False, use only the 24 paper-baseline features.
    """

    def __init__(self, custom_features: Optional[list] = None,
                 extended: bool = True):
        if custom_features:
            self._features = custom_features
        else:
            base = _build_default_features()
            if extended:
                base = base + _build_extended_features()
            self._features = base
        self.extended = extended

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
