"""
Phase 3 shared utilities — Chop-Focused Martingale Research.

Core thesis: 98.7% of busts happen in choppy ranges. If we detect and handle
chop correctly, the strategy is profitable in all other conditions by default.

Modules:
  - Grid/hedge cycle simulator (candle-based + pure-math MC)
  - Chop detection (multiple methods: Choppiness Index, Hurst, ADX, fractal dim)
  - N-regime discovery (data-driven clustering, not hardcoded 3)
  - Era relevance testing (structural break detection)
"""
import os
import sys
import json
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

# ── Project bootstrap ──
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

_PHASE3_DIR = os.path.dirname(os.path.abspath(__file__))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── Constants ──
FIB = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]
PIP = 0.0001  # EUR-USD pip value


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CycleResult:
    """Result of a single hedge cycle."""
    bust: bool
    level_reached: int
    pnl: float
    bars_held: int
    entry_idx: int = 0
    direction: int = 1
    level_pnls: List[float] = field(default_factory=list)
    chop_score_at_entry: float = 0.0  # Chop score when cycle started

    @property
    def is_win(self):
        return not self.bust and self.pnl > 0


@dataclass
class SimConfig:
    """Grid simulator configuration."""
    sizing_curve: str = 'sqrt'
    sizing_factor: float = 2.0
    base_size: float = 1.0
    max_levels: int = 12
    hedge_dist_pips: float = 10.0
    hedge_expand: bool = False
    hedge_expand_factor: float = 1.2
    tp_pips: float = 20.0
    tp_mode: str = 'fixed'
    abort_level: int = 0
    max_bars: int = 5000

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}

    @staticmethod
    def from_dict(d):
        c = SimConfig()
        for k, v in d.items():
            if hasattr(c, k):
                setattr(c, k, v)
        return c


# ══════════════════════════════════════════════════════════════════════════════
# SIZING & GRID HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def calc_size(level: int, cfg: SimConfig) -> float:
    base, m = cfg.base_size, cfg.sizing_factor
    if cfg.sizing_curve == 'geometric':
        return base * (m ** level)
    elif cfg.sizing_curve == 'sqrt':
        return base * (m ** 0.5) ** level
    elif cfg.sizing_curve == 'linear':
        return base * (1 + level)
    elif cfg.sizing_curve == 'fibonacci':
        return base * FIB[min(level, len(FIB) - 1)]
    elif cfg.sizing_curve == 'fixed':
        return base
    return base


def hedge_distance(level: int, cfg: SimConfig) -> float:
    dist = cfg.hedge_dist_pips
    if cfg.hedge_expand:
        dist *= cfg.hedge_expand_factor ** level
    return dist


def total_exposure(level: int, cfg: SimConfig) -> float:
    return sum(calc_size(i, cfg) for i in range(level + 1))


def effective_multiplier(cfg: SimConfig) -> float:
    sizes = [calc_size(i, cfg) for i in range(cfg.max_levels)]
    ratios = [sizes[i+1] / sizes[i] for i in range(len(sizes)-1) if sizes[i] > 0]
    return np.mean(ratios) if ratios else cfg.sizing_factor


def theoretical_bust_prob(p: float, m: float, N: int) -> float:
    pm = p * m
    if pm >= 1.0 or m <= 1.0:
        return 1.0
    return min(1.0, (pm ** N) / (m - 1))


# ══════════════════════════════════════════════════════════════════════════════
# CHOP DETECTION — THE CORE PROBLEM
# ══════════════════════════════════════════════════════════════════════════════

def compute_chop_features(candles: np.ndarray, windows: Tuple[int, ...] = (100,)
                           ) -> Dict[str, np.ndarray]:
    """Compute choppiness indicators — vectorized for speed on large datasets.

    Features per window:
      1. choppiness_index — CHOP(window): >61.8 = choppy
      2. efficiency_ratio — |net move| / sum(|bar moves|). Near 0 = choppy
      3. adx — Average Directional Index. <20 = no trend (choppy)
      4. atr_ratio — ATR(14) / ATR(50). <0.8 = compressing vol
      5. range_vs_atr — period range / (ATR * window)
    """
    n = len(candles)
    close = candles[:, 2]
    high = candles[:, 3]
    low = candles[:, 4]

    # True Range — vectorized
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    tr[1:] = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1]))
    )

    # ATR at two scales
    atr14 = _ema_array(tr, 14)
    atr50 = _ema_array(tr, 50)

    features = {}
    features['atr_ratio'] = np.where(atr50 > 0, atr14 / atr50, 1.0)

    # ADX (computed once, reused)
    adx = _compute_adx(candles, period=14)

    for w in windows:
        if n < w + 10:
            continue
        suffix = f'_{w}'

        # 1. Choppiness Index — vectorized with cumsum
        cum_tr = np.cumsum(tr)
        sum_tr = np.full(n, np.nan)
        sum_tr[w:] = cum_tr[w:] - cum_tr[:-w]

        # Rolling high/low via stride tricks or simple loop on downsampled
        # Use a fast rolling approach
        from numpy.lib.stride_tricks import sliding_window_view
        if n >= w:
            hi_windows = sliding_window_view(high, w)  # shape (n-w+1, w)
            lo_windows = sliding_window_view(low, w)
            rolling_hi = np.max(hi_windows, axis=1)
            rolling_lo = np.min(lo_windows, axis=1)
            rng = rolling_hi - rolling_lo

            chop_idx = np.full(n, np.nan)
            # Align: rolling windows start at index w-1
            start = w - 1
            end = start + len(rng)
            sum_tr_slice = sum_tr[start:end]
            valid = (rng > 0) & (~np.isnan(sum_tr_slice)) & (sum_tr_slice > 0)
            chop_idx[start:end] = np.where(valid,
                100 * np.log10(sum_tr_slice / np.where(rng > 0, rng, 1)) / np.log10(w),
                np.nan)
            features[f'choppiness_index{suffix}'] = chop_idx

            # 5. Range vs ATR — vectorized
            range_atr = np.full(n, np.nan)
            atr_windows = sliding_window_view(atr14, w)
            mean_atr = np.nanmean(atr_windows, axis=1)
            valid_atr = mean_atr > 0
            range_atr[start:end] = np.where(valid_atr, rng / (mean_atr * w), np.nan)
            features[f'range_vs_atr{suffix}'] = range_atr

        # 2. Efficiency Ratio — vectorized
        er = np.full(n, np.nan)
        net_move = np.abs(close[w:] - close[:-w])
        cum_abs = np.cumsum(np.abs(np.diff(close)))
        cum_abs = np.concatenate([[0], cum_abs])  # prepend 0
        sum_moves_arr = cum_abs[w:] - cum_abs[:-w]
        er[w:] = np.where(sum_moves_arr > 0, net_move / sum_moves_arr, 0)
        features[f'efficiency_ratio{suffix}'] = er

        # 3. ADX (already computed)
        features[f'adx{suffix}'] = adx

    return features


def compute_all_indicators(candles: np.ndarray) -> Dict[str, np.ndarray]:
    """Compute ~80+ indicators across all categories for a full indicator screen.

    Handles multi-output indicators (namedtuples) by extracting each field
    separately.  Silently skips any indicator that errors.  Only keeps features
    with meaningful variance (not all-constant or all-NaN).

    Args:
        candles: numpy array with columns [timestamp, open, close, high, low, volume]

    Returns:
        Dict[str, np.ndarray] mapping indicator name to 1-D float array aligned
        to the input candle series.
    """
    import qengine.indicators as ta

    raw: Dict[str, np.ndarray] = {}

    def _add(name: str, arr) -> None:
        """Store a single array under *name* after basic sanity checks."""
        if arr is None:
            return
        a = np.asarray(arr, dtype=float)
        if a.ndim != 1 or len(a) != len(candles):
            return
        raw[name] = a

    def _try_simple(name: str, fn, *args, **kwargs) -> None:
        """Call fn(candles, *args, sequential=True, **kwargs) and store result."""
        try:
            result = fn(candles, *args, sequential=True, **kwargs)
            if hasattr(result, '_fields'):
                # namedtuple — caller should use _try_multi instead; skip
                return
            _add(name, result)
        except Exception:
            pass

    def _try_multi(prefix: str, fn, fields, *args, **kwargs) -> None:
        """Call fn and extract named fields from the returned namedtuple."""
        try:
            result = fn(candles, *args, **kwargs)
            if not hasattr(result, '_fields'):
                # some indicators return array directly even without sequential
                return
            for field_name in fields:
                if hasattr(result, field_name):
                    arr = getattr(result, field_name)
                    _add(f'{prefix}_{field_name}', arr)
        except Exception:
            pass

    # ── Trend strength ─────────────────────────────────────────────────────────
    _try_simple('adx_14',      ta.adx,         14)
    _try_simple('adx_28',      ta.adx,         28)
    _try_simple('adxr',        ta.adxr,        14)
    _try_simple('aroonosc',    ta.aroonosc,    14)
    _try_simple('chop_14',     ta.chop,        14)
    _try_simple('chop_50',     ta.chop,        50)
    _try_simple('dx_14',       ta.dx,          14)
    _try_simple('er_10',       ta.er,          10)
    _try_simple('er_50',       ta.er,          50)
    _try_simple('er_100',      ta.er,          100)
    _try_simple('pfe_10',      ta.pfe,         10)
    _try_simple('pfe_20',      ta.pfe,         20)
    _try_simple('cfo',         ta.cfo)
    _try_simple('cmo_14',      ta.cmo,         14)
    _try_simple('dpo',         ta.dpo)
    _try_simple('fosc',        ta.fosc)

    # ── Volatility ─────────────────────────────────────────────────────────────
    _try_simple('atr_14',      ta.atr,         14)
    _try_simple('atr_50',      ta.atr,         50)
    _try_simple('natr_14',     ta.natr,        14)
    _try_simple('natr_50',     ta.natr,        50)
    _try_simple('bbw_20',      ta.bollinger_bands_width, 20)
    _try_simple('bbw_50',      ta.bollinger_bands_width, 50)
    _try_simple('cvi',         ta.cvi)
    _try_simple('ui',          ta.ui)
    _try_simple('mass',        ta.mass)
    _try_simple('stddev_20',   ta.stddev,      20)
    _try_simple('trange',      ta.trange)

    # ── Momentum ───────────────────────────────────────────────────────────────
    _try_simple('rsi_14',      ta.rsi,         14)
    _try_simple('rsi_28',      ta.rsi,         28)
    _try_simple('cci_20',      ta.cci,         20)
    _try_simple('mfi_14',      ta.mfi,         14)
    _try_simple('willr',       ta.willr)
    _try_simple('apo',         ta.apo)
    _try_simple('bop',         ta.bop)
    _try_simple('mom_14',      ta.mom,         14)
    _try_simple('roc_14',      ta.roc,         14)
    _try_simple('trix_14',     ta.trix,        14)
    _try_simple('tsi',         ta.tsi)
    _try_simple('ultosc',      ta.ultosc)
    _try_simple('lrsi',        ta.lrsi)
    _try_simple('rsx',         ta.rsx)
    _try_simple('ift_rsi',     ta.ift_rsi)
    _try_simple('dti',         ta.dti)
    _try_simple('qstick',      ta.qstick)
    _try_simple('rvi_10',      ta.rvi,         10)
    _try_simple('cc',          ta.cc)
    _try_simple('dec_osc',     ta.dec_osc)
    _try_simple('emv',         ta.emv)
    _try_simple('efi_13',      ta.efi,         13)
    _try_simple('chande',      ta.chande)

    # ── Volume ─────────────────────────────────────────────────────────────────
    _try_simple('ad',          ta.ad)
    _try_simple('adosc',       ta.adosc)
    _try_simple('obv',         ta.obv)
    _try_simple('nvi',         ta.nvi)
    _try_simple('pvi',         ta.pvi)
    _try_simple('vosc',        ta.vosc)
    _try_simple('vpt',         ta.vpt)
    _try_simple('kvo',         ta.kvo)
    _try_simple('wad',         ta.wad)
    _try_simple('mwdx',        ta.mwdx)
    _try_simple('marketfi',    ta.marketfi)

    # ── Cycle / quality ────────────────────────────────────────────────────────
    _try_simple('cg',          ta.cg)
    _try_simple('reflex',      ta.reflex)
    _try_simple('trendflex',   ta.trendflex)
    _try_simple('edcf',        ta.edcf)
    _try_simple('decycler',    ta.decycler)
    _try_simple('roofing',     ta.roofing)

    # ── Regression ─────────────────────────────────────────────────────────────
    _try_simple('linreg_slope_20',  ta.linearreg_slope, 20)
    _try_simple('linreg_slope_50',  ta.linearreg_slope, 50)
    _try_simple('linreg_angle_20',  ta.linearreg_angle, 20)

    # ── Distribution shape ─────────────────────────────────────────────────────
    _try_simple('kurtosis_20', ta.kurtosis,    20)
    _try_simple('skew_20',     ta.skew,        20)
    _try_simple('zscore_20',   ta.zscore,      20)

    # ── Multi-output indicators ────────────────────────────────────────────────
    # squeeze_momentum — default already has sequential=True
    try:
        sm = ta.squeeze_momentum(candles)
        _add('squeeze_momentum_squeeze',  sm.squeeze)
        _add('squeeze_momentum_momentum', sm.momentum)
    except Exception:
        pass

    # damiani_volatmeter
    _try_multi('damiani', ta.damiani_volatmeter, ['vol', 'anti'], sequential=True)

    # fisher
    _try_multi('fisher', ta.fisher, ['fisher', 'signal'], sequential=True)

    # aroon — note fields are (down, up)
    _try_multi('aroon', ta.aroon, ['down', 'up'], sequential=True)

    # di
    _try_multi('di', ta.di, ['plus', 'minus'], sequential=True)

    # dm
    _try_multi('dm', ta.dm, ['plus', 'minus'], sequential=True)

    # stoch
    _try_multi('stoch', ta.stoch, ['k', 'd'], sequential=True)

    # bollinger_bands
    _try_multi('bb', ta.bollinger_bands, ['upperband', 'middleband', 'lowerband'], sequential=True)

    # keltner
    _try_multi('kc', ta.keltner, ['upperband', 'middleband', 'lowerband'], sequential=True)

    # donchian
    _try_multi('dc', ta.donchian, ['upperband', 'middleband', 'lowerband'], sequential=True)

    # supertrend
    _try_multi('supertrend', ta.supertrend, ['trend', 'changed'], sequential=True)

    # voss
    _try_multi('voss', ta.voss, ['voss', 'filt'], sequential=True)

    # bandpass
    _try_multi('bp', ta.bandpass, ['bp', 'bp_normalized', 'signal', 'trigger'], sequential=True)

    # correlation_cycle
    _try_multi('cc_cycle', ta.correlation_cycle, ['real', 'imag', 'angle', 'state'], sequential=True)

    # eri
    _try_multi('eri', ta.eri, ['bull', 'bear'], sequential=True)

    # kdj
    _try_multi('kdj', ta.kdj, ['k', 'd', 'j'], sequential=True)

    # macd
    _try_multi('macd', ta.macd, ['macd', 'signal', 'hist'], sequential=True)

    # ppo — returns scalar/array (not a namedtuple)
    _try_simple('ppo', ta.ppo)

    # vi
    _try_multi('vi', ta.vi, ['plus', 'minus'], sequential=True)

    # waddah — no sequential param; returns WaddahAttarExplosionTuple
    try:
        w = ta.waddah_attar_explosion(candles)
        _add('waddah_explosion', w.explosion_line)
        _add('waddah_trend',     w.trend_power)
    except Exception:
        pass

    # wt (Wavetrend) — use wt1 and wt2
    _try_multi('wt', ta.wt, ['wt1', 'wt2'], sequential=True)

    # ao (Awesome Oscillator) — osc and change
    _try_multi('ao', ta.ao, ['osc', 'change'], sequential=True)

    # srsi
    _try_multi('srsi', ta.srsi, ['k', 'd'], sequential=True)

    # kst
    _try_multi('kst', ta.kst, ['line', 'signal'], sequential=True)

    # ── Filter: remove constant / all-NaN features ─────────────────────────────
    features: Dict[str, np.ndarray] = {}
    for name, arr in raw.items():
        valid = arr[~np.isnan(arr)]
        if len(valid) < 10:
            continue
        if np.nanstd(arr) < 1e-12:
            continue
        features[name] = arr

    return features


def chop_score(features: Dict[str, np.ndarray], window: int = 100) -> np.ndarray:
    """Combine chop indicators into a single 0-1 score.
    Higher = more choppy. This is the composite score we'll calibrate against busts.
    """
    n = len(next(iter(features.values())))
    score = np.zeros(n)
    count = np.zeros(n)
    suffix = f'_{window}'

    # Each indicator contributes a 0-1 signal
    # Choppiness Index: >61.8 is choppy (Fibonacci level)
    k = f'choppiness_index{suffix}'
    if k in features:
        v = features[k]
        valid = ~np.isnan(v)
        contrib = np.clip((v - 38.2) / (61.8 - 38.2), 0, 1)  # 38.2-61.8 → 0-1
        score[valid] += contrib[valid]
        count[valid] += 1

    # Hurst: <0.5 = choppy
    k = f'hurst{suffix}'
    if k in features:
        v = features[k]
        valid = ~np.isnan(v)
        contrib = np.clip(1 - v / 0.5, 0, 1)  # 0.5→0, 0→1
        score[valid] += contrib[valid]
        count[valid] += 1

    # ADX: <20 = no trend
    k = f'adx{suffix}'
    if k in features:
        v = features[k]
        valid = ~np.isnan(v)
        contrib = np.clip(1 - v / 25, 0, 1)  # 25→0, 0→1
        score[valid] += contrib[valid]
        count[valid] += 1

    # Efficiency Ratio: near 0 = choppy
    k = f'efficiency_ratio{suffix}'
    if k in features:
        v = features[k]
        valid = ~np.isnan(v)
        contrib = np.clip(1 - v / 0.3, 0, 1)  # 0.3→0, 0→1
        score[valid] += contrib[valid]
        count[valid] += 1

    # Fractal dim: >1.5 = noisy/choppy
    k = f'fractal_dim{suffix}'
    if k in features:
        v = features[k]
        valid = ~np.isnan(v)
        contrib = np.clip((v - 1.2) / (1.8 - 1.2), 0, 1)
        score[valid] += contrib[valid]
        count[valid] += 1

    # ATR ratio: <0.8 = compressing
    k = 'atr_ratio'
    if k in features:
        v = features[k]
        valid = ~np.isnan(v)
        contrib = np.clip(1 - v / 1.0, 0, 1)
        score[valid] += contrib[valid]
        count[valid] += 1

    # Normalize to [0, 1]
    count = np.where(count > 0, count, 1)
    return score / count


def label_chop_zones(chop_scores: np.ndarray, threshold: float = 0.6,
                      min_bars: int = 20) -> np.ndarray:
    """Label contiguous choppy zones from chop scores.

    Returns array of zone IDs (0 = not choppy, 1+ = zone index).
    Zones shorter than min_bars are removed.
    """
    n = len(chop_scores)
    is_choppy = chop_scores >= threshold
    labels = np.zeros(n, dtype=int)
    zone_id = 0
    in_zone = False
    zone_start = 0

    for i in range(n):
        if is_choppy[i] and not in_zone:
            in_zone = True
            zone_start = i
        elif not is_choppy[i] and in_zone:
            in_zone = False
            if i - zone_start >= min_bars:
                zone_id += 1
                labels[zone_start:i] = zone_id

    # Handle zone that extends to end
    if in_zone and n - zone_start >= min_bars:
        zone_id += 1
        labels[zone_start:n] = zone_id

    return labels


# ══════════════════════════════════════════════════════════════════════════════
# N-REGIME DISCOVERY (data-driven, not hardcoded)
# ══════════════════════════════════════════════════════════════════════════════

def discover_regimes(features: Dict[str, np.ndarray], max_regimes: int = 10,
                      method: str = 'bic') -> Tuple[np.ndarray, int, Dict]:
    """Automatically discover the right number of regimes from data.

    Uses BIC/silhouette to find optimal N, then clusters.
    Returns (labels, n_regimes, diagnostics).
    """
    # Build feature matrix from available features
    keys = sorted(features.keys())
    arrays = []
    for k in keys:
        v = features[k]
        arrays.append(v)
    X = np.column_stack(arrays)
    valid = ~np.any(np.isnan(X), axis=1)
    X_valid = X[valid]

    if len(X_valid) < max_regimes * 10:
        return np.zeros(len(X), dtype=int), 1, {'error': 'too few valid samples'}

    # Standardize
    mu = X_valid.mean(axis=0)
    sd = X_valid.std(axis=0)
    sd = np.where(sd > 0, sd, 1)
    X_norm = (X_valid - mu) / sd

    # Subsample for GMM fitting (full data too slow for >1M rows)
    max_fit_samples = 100000
    if len(X_norm) > max_fit_samples:
        rng = np.random.default_rng(42)
        fit_idx = rng.choice(len(X_norm), max_fit_samples, replace=False)
        X_fit = X_norm[fit_idx]
    else:
        X_fit = X_norm

    # Try GMM with BIC for model selection
    best_n = 2
    best_bic = np.inf
    bics = {}

    try:
        from sklearn.mixture import GaussianMixture
        for n in range(2, max_regimes + 1):
            gmm = GaussianMixture(n_components=n, random_state=42, max_iter=100, n_init=3)
            gmm.fit(X_fit)
            bic = gmm.bic(X_fit)
            bics[n] = bic
            if bic < best_bic:
                best_bic = bic
                best_n = n

        # Fit final model on subsample, predict on all
        gmm = GaussianMixture(n_components=best_n, random_state=42, max_iter=200, n_init=5)
        gmm.fit(X_fit)
        labels_valid = gmm.predict(X_norm)
    except ImportError:
        # Fallback to KMeans
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        best_score = -1
        for n in range(2, min(max_regimes + 1, 8)):
            km = KMeans(n_clusters=n, random_state=42, n_init=10)
            pred = km.fit_predict(X_fit)
            score = silhouette_score(X_fit, pred, sample_size=min(5000, len(X_fit)))
            bics[n] = -score
            if score > best_score:
                best_score = score
                best_n = n
        km = KMeans(n_clusters=best_n, random_state=42, n_init=10)
        km.fit(X_fit)
        labels_valid = km.predict(X_norm)

    # Map back to full array
    labels = np.full(len(X), -1, dtype=int)
    labels[valid] = labels_valid

    diagnostics = {
        'n_regimes': best_n,
        'bics': {str(k): float(v) for k, v in bics.items()},
        'features_used': keys,
        'n_valid_bars': int(valid.sum()),
    }

    return labels, best_n, diagnostics


def regime_chop_overlap(regime_labels: np.ndarray, chop_zones: np.ndarray) -> Dict[int, float]:
    """For each regime, compute what % of its bars fall in choppy zones."""
    regimes = set(regime_labels) - {-1}
    overlap = {}
    for r in sorted(regimes):
        mask = regime_labels == r
        n_total = mask.sum()
        if n_total == 0:
            overlap[r] = 0.0
            continue
        n_chop = (mask & (chop_zones > 0)).sum()
        overlap[r] = round(n_chop / n_total * 100, 1)
    return overlap


# ══════════════════════════════════════════════════════════════════════════════
# ERA / DATA RELEVANCE
# ══════════════════════════════════════════════════════════════════════════════

def split_into_eras(candles: np.ndarray, era_years: int = 3) -> List[Tuple[str, np.ndarray]]:
    """Split candles into non-overlapping eras for relevance testing."""
    import qengine.helpers as jh
    timestamps = candles[:, 0]
    eras = []

    import arrow
    first_ts = timestamps[0]
    last_ts = timestamps[-1]
    start = jh.timestamp_to_arrow(first_ts).floor('year')
    end = jh.timestamp_to_arrow(last_ts).ceil('year')

    current = start
    while current < end:
        era_end = current.shift(years=era_years)
        start_ms = jh.arrow_to_timestamp(current)
        end_ms = jh.arrow_to_timestamp(era_end)
        mask = (timestamps >= start_ms) & (timestamps < end_ms)
        era_candles = candles[mask]
        if len(era_candles) > 1000:
            label = f"{current.year}-{min(era_end.year - 1, end.year)}"
            eras.append((label, era_candles))
        current = era_end

    return eras


def era_bust_profile(era_candles: np.ndarray, cfg: SimConfig,
                      n_signals: int = 500) -> Dict[str, Any]:
    """Compute bust/chop profile for a single era."""
    rng = np.random.default_rng(hash(len(era_candles)) % 2**32)
    signals = random_signals(len(era_candles), avg_spacing=max(len(era_candles) // n_signals, 30), rng=rng)
    results = run_cycles_on_signals(era_candles, signals, cfg)
    s = cycle_summary(results)

    # Compute chop characteristics
    feats = compute_chop_features(era_candles, windows=(100,))
    cs = chop_score(feats, window=100)
    valid = ~np.isnan(cs)

    return {
        **s,
        'mean_chop': round(float(np.nanmean(cs)), 4),
        'pct_choppy': round(float(np.mean(cs[valid] > 0.6) * 100), 1) if valid.any() else 0,
        'mean_atr_ratio': round(float(np.nanmean(feats.get('atr_ratio', [1.0]))), 4),
    }


# ══════════════════════════════════════════════════════════════════════════════
# GRID SIMULATOR
# ══════════════════════════════════════════════════════════════════════════════

def simulate_cycle_on_candles(candles: np.ndarray, entry_idx: int, direction: int,
                               cfg: SimConfig, pip_value: float = PIP,
                               chop_score_val: float = 0.0) -> Optional[CycleResult]:
    """Simulate one hedge cycle on real candle data."""
    n_bars = len(candles)
    if entry_idx >= n_bars:
        return None

    level = 0
    entry_price = candles[entry_idx, 2]
    level_entries = [entry_price]
    level_dirs = [direction]
    level_sizes = [calc_size(0, cfg)]
    level_pnls = []
    bars = 0

    tp_dist = cfg.tp_pips * pip_value
    h_dist = hedge_distance(0, cfg) * pip_value

    if direction == 1:
        tp_price = entry_price + tp_dist
        hedge_price = entry_price - h_dist
    else:
        tp_price = entry_price - tp_dist
        hedge_price = entry_price + h_dist

    for bar_idx in range(entry_idx + 1, min(entry_idx + cfg.max_bars, n_bars)):
        bars += 1
        high = candles[bar_idx, 3]
        low = candles[bar_idx, 4]

        # Check TP
        last_dir = level_dirs[-1]
        tp_hit = (last_dir == 1 and high >= tp_price) or (last_dir == -1 and low <= tp_price)

        if tp_hit:
            close_price = tp_price
            total_pnl = 0.0
            for i in range(len(level_entries)):
                leg_pnl = level_dirs[i] * (close_price - level_entries[i]) * level_sizes[i] / pip_value
                level_pnls.append(leg_pnl)
                total_pnl += leg_pnl
            return CycleResult(bust=False, level_reached=level, pnl=total_pnl,
                               bars_held=bars, entry_idx=entry_idx, direction=direction,
                               level_pnls=level_pnls, chop_score_at_entry=chop_score_val)

        # Check hedge trigger
        hedge_hit = (last_dir == 1 and low <= hedge_price) or (last_dir == -1 and high >= hedge_price)

        if hedge_hit:
            if cfg.abort_level > 0 and level + 1 >= cfg.abort_level:
                return _close_all(level + 1, hedge_price, level_entries, level_dirs,
                                  level_sizes, pip_value, bars, entry_idx, direction, True, chop_score_val)

            if level + 1 >= cfg.max_levels:
                return _close_all(level + 1, hedge_price, level_entries, level_dirs,
                                  level_sizes, pip_value, bars, entry_idx, direction, True, chop_score_val)

            level += 1
            new_dir = -last_dir
            new_entry = hedge_price
            level_entries.append(new_entry)
            level_dirs.append(new_dir)
            level_sizes.append(calc_size(level, cfg))

            tp_dist = cfg.tp_pips * pip_value
            tp_price = new_entry + tp_dist if new_dir == 1 else new_entry - tp_dist
            h_dist = hedge_distance(level, cfg) * pip_value
            hedge_price = new_entry - h_dist if new_dir == 1 else new_entry + h_dist

    # Data ran out
    if bars > 0:
        close_price = candles[min(entry_idx + bars, n_bars - 1), 2]
        return _close_all(level, close_price, level_entries, level_dirs,
                          level_sizes, pip_value, bars, entry_idx, direction, True, chop_score_val)
    return None


def _close_all(level, close_price, entries, dirs, sizes, pip_value,
               bars, entry_idx, direction, bust, chop_score_val):
    level_pnls = []
    total_pnl = 0.0
    for i in range(len(entries)):
        leg_pnl = dirs[i] * (close_price - entries[i]) * sizes[i] / pip_value
        level_pnls.append(leg_pnl)
        total_pnl += leg_pnl
    return CycleResult(bust=bust, level_reached=level, pnl=total_pnl,
                       bars_held=bars, entry_idx=entry_idx, direction=direction,
                       level_pnls=level_pnls, chop_score_at_entry=chop_score_val)


def simulate_monte_carlo(p_lose: float, cfg: SimConfig, n_trials: int = 100000,
                          rng: np.random.Generator = None) -> List[CycleResult]:
    """Pure-math MC simulator."""
    if rng is None:
        rng = np.random.default_rng(42)
    results = []
    for _ in range(n_trials):
        level = 0
        total_pnl = 0.0
        bust = False
        while level < cfg.max_levels:
            size = calc_size(level, cfg)
            h_dist = hedge_distance(level, cfg)
            if rng.random() < p_lose:
                total_pnl -= h_dist * size
                level += 1
            else:
                total_pnl += cfg.tp_pips * size
                break
        else:
            bust = True
        results.append(CycleResult(bust=bust, level_reached=level, pnl=total_pnl,
                                    bars_held=0, direction=1))
    return results


# ══════════════════════════════════════════════════════════════════════════════
# BATCH SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

def run_cycles_on_signals(candles: np.ndarray, signals: List[Tuple[int, int]],
                           cfg: SimConfig, pip_value: float = PIP,
                           chop_scores: np.ndarray = None,
                           non_overlapping: bool = True) -> List[CycleResult]:
    """Run simulator on signals. Optionally tags each cycle with its chop score."""
    results = []
    last_exit_idx = -1

    for entry_idx, direction in sorted(signals, key=lambda x: x[0]):
        if non_overlapping and entry_idx <= last_exit_idx:
            continue
        cs = float(chop_scores[entry_idx]) if chop_scores is not None and entry_idx < len(chop_scores) else 0.0
        result = simulate_cycle_on_candles(candles, entry_idx, direction, cfg, pip_value, cs)
        if result is not None:
            results.append(result)
            last_exit_idx = entry_idx + result.bars_held

    return results


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY STATISTICS
# ══════════════════════════════════════════════════════════════════════════════

def cycle_summary(cycles: List[CycleResult]) -> Dict[str, Any]:
    if not cycles:
        return {'n_cycles': 0, 'n_wins': 0, 'n_busts': 0, 'win_rate': 0,
                'bust_rate': 0, 'net_pnl': 0, 'profit_factor': 0}

    n = len(cycles)
    wins = [c for c in cycles if c.is_win]
    busts = [c for c in cycles if c.bust]
    all_pnls = [c.pnl for c in cycles]
    win_pnls = [c.pnl for c in wins]
    bust_pnls = [c.pnl for c in busts]

    gross_profit = sum(p for p in all_pnls if p > 0)
    gross_loss = abs(sum(p for p in all_pnls if p < 0))
    levels = [c.level_reached for c in cycles]

    return {
        'n_cycles': n,
        'n_wins': len(wins),
        'n_busts': len(busts),
        'win_rate': round(len(wins) / n * 100, 2),
        'bust_rate': round(len(busts) / n * 100, 2),
        'net_pnl': round(sum(all_pnls), 2),
        'avg_win_pnl': round(np.mean(win_pnls), 2) if win_pnls else 0,
        'avg_bust_pnl': round(np.mean(bust_pnls), 2) if bust_pnls else 0,
        'profit_factor': round(gross_profit / gross_loss, 2) if gross_loss > 0 else float('inf'),
        'bust_erase_ratio': round(abs(np.mean(bust_pnls)) / np.mean(win_pnls), 1) if win_pnls and bust_pnls else 0,
        'avg_level': round(np.mean(levels), 2),
        'max_level': max(levels),
        'avg_bars': round(np.mean([c.bars_held for c in cycles]), 1),
        'level_dist': {i: levels.count(i) for i in range(max(levels) + 1) if levels.count(i) > 0},
    }


def equity_curve(cycles: List[CycleResult], initial_balance: float = 10000) -> np.ndarray:
    return initial_balance + np.cumsum([c.pnl for c in cycles])


def max_drawdown(eq: np.ndarray) -> Tuple[float, float]:
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    return abs(dd.min()), abs((dd / peak).min() * 100)


# ══════════════════════════════════════════════════════════════════════════════
# CANDLE LOADING & SIGNAL GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def load_candles(exchange='OANDA', symbol='EUR-USD', timeframe='5m',
                  start_date='2006-01-01', end_date='2025-12-31',
                  warmup_candles_num=0) -> np.ndarray:
    import qengine.helpers as jh
    from qengine.research import get_candles
    warmup, trading = get_candles(
        exchange, symbol, timeframe,
        jh.date_to_timestamp(start_date),
        jh.date_to_timestamp(end_date),
        warmup_candles_num=warmup_candles_num,
    )
    if warmup is not None and warmup.ndim == 2 and len(warmup) > 0:
        return np.concatenate([warmup, trading], axis=0)
    return trading


def find_ema_crossover_signals(candles: np.ndarray, fast_period: int = 8,
                                 slow_period: int = 21) -> List[Tuple[int, int]]:
    close = candles[:, 2]
    n = len(close)
    if n < slow_period + 1:
        return []

    fast = np.full(n, np.nan)
    slow = np.full(n, np.nan)
    fast[fast_period - 1] = np.mean(close[:fast_period])
    af = 2.0 / (fast_period + 1)
    for i in range(fast_period, n):
        fast[i] = af * close[i] + (1 - af) * fast[i-1]
    slow[slow_period - 1] = np.mean(close[:slow_period])
    a_s = 2.0 / (slow_period + 1)
    for i in range(slow_period, n):
        slow[i] = a_s * close[i] + (1 - a_s) * slow[i-1]

    signals = []
    for i in range(slow_period + 1, n):
        if np.isnan(fast[i]) or np.isnan(slow[i]) or np.isnan(fast[i-1]) or np.isnan(slow[i-1]):
            continue
        if fast[i-1] <= slow[i-1] and fast[i] > slow[i]:
            signals.append((i, 1))
        elif fast[i-1] >= slow[i-1] and fast[i] < slow[i]:
            signals.append((i, -1))
    return signals


def random_signals(n_candles: int, avg_spacing: int = 50,
                    rng: np.random.Generator = None) -> List[Tuple[int, int]]:
    if rng is None:
        rng = np.random.default_rng(42)
    signals = []
    idx = rng.integers(20, avg_spacing)
    while idx < n_candles - 100:
        signals.append((int(idx), rng.choice([1, -1])))
        idx += rng.integers(avg_spacing // 2, avg_spacing * 2)
    return signals


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _ema_array(data: np.ndarray, period: int) -> np.ndarray:
    n = len(data)
    out = np.full(n, np.nan)
    if n < period:
        return out
    out[period - 1] = np.mean(data[:period])
    alpha = 2.0 / (period + 1)
    for i in range(period, n):
        out[i] = alpha * data[i] + (1 - alpha) * out[i-1]
    return out


def _hurst_rs(series: np.ndarray) -> float:
    """Rescaled range Hurst exponent."""
    n = len(series)
    if n < 10:
        return 0.5
    mean = np.mean(series)
    deviations = series - mean
    cumulative = np.cumsum(deviations)
    R = np.max(cumulative) - np.min(cumulative)
    S = np.std(series, ddof=1)
    if S == 0:
        return 0.5
    RS = R / S
    if RS <= 0:
        return 0.5
    return np.log(RS) / np.log(n)


def _fractal_dimension(series: np.ndarray) -> float:
    """Simplified Higuchi fractal dimension estimate."""
    n = len(series)
    if n < 10:
        return 1.5
    max_k = min(n // 4, 10)
    if max_k < 2:
        return 1.5

    ks = np.arange(1, max_k + 1)
    Lk = np.zeros(max_k)

    for ki, k in enumerate(ks):
        lengths = []
        for m in range(1, k + 1):
            indices = np.arange(m - 1, n, k)
            if len(indices) < 2:
                continue
            seg = series[indices]
            length = np.sum(np.abs(np.diff(seg))) * (n - 1) / (k * (len(seg) - 1)) / k
            lengths.append(length)
        Lk[ki] = np.mean(lengths) if lengths else 0

    # Fit log-log line
    valid = Lk > 0
    if valid.sum() < 2:
        return 1.5
    log_k = np.log(ks[valid])
    log_L = np.log(Lk[valid])
    # Linear regression
    slope = np.polyfit(log_k, log_L, 1)[0]
    return abs(slope)


def _compute_adx(candles: np.ndarray, period: int = 14) -> np.ndarray:
    """Vectorized ADX computation."""
    n = len(candles)
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]

    # Vectorized DM and TR
    up = np.empty(n); up[0] = 0
    up[1:] = high[1:] - high[:-1]
    down = np.empty(n); down[0] = 0
    down[1:] = low[:-1] - low[1:]

    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    tr = np.empty(n); tr[0] = high[0] - low[0]
    tr[1:] = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1]))
    )

    atr = _ema_array(tr, period)
    plus_di = np.where(atr > 0, _ema_array(plus_dm, period) / atr * 100, 0)
    minus_di = np.where(atr > 0, _ema_array(minus_dm, period) / atr * 100, 0)

    di_sum = plus_di + minus_di
    dx = np.where(di_sum > 0, np.abs(plus_di - minus_di) / di_sum * 100, 0)
    adx = _ema_array(dx, period)

    return adx


# ══════════════════════════════════════════════════════════════════════════════
# I/O
# ══════════════════════════════════════════════════════════════════════════════

def save_results(data, name: str, subdir: str = 'results'):
    path = os.path.join(_PHASE3_DIR, subdir, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if isinstance(data, np.ndarray):
        np.save(path if path.endswith('.npy') else path + '.npy', data)
    elif isinstance(data, (dict, list)):
        with open(path if path.endswith('.json') else path + '.json', 'w') as f:
            json.dump(data, f, indent=2, default=str)
    else:
        import pickle
        with open(path if path.endswith('.pkl') else path + '.pkl', 'wb') as f:
            pickle.dump(data, f)


def load_results(name: str, subdir: str = 'results'):
    base = os.path.join(_PHASE3_DIR, subdir, name)
    for ext in ['.json', '.npy', '.pkl', '']:
        path = base + ext if not base.endswith(ext) else base
        if os.path.exists(path):
            if path.endswith('.json'):
                with open(path) as f:
                    return json.load(f)
            elif path.endswith('.npy'):
                return np.load(path, allow_pickle=True)
            elif path.endswith('.pkl'):
                import pickle
                with open(path, 'rb') as f:
                    return pickle.load(f)
    raise FileNotFoundError(f"No results found for {name}")


def savefig(name: str):
    path = os.path.join(_PHASE3_DIR, 'plots', name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: plots/{name}")
