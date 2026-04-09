"""
MarketBrain — Layer 1 of the ARIA pipeline.

Extracts market features from strategy candle data every candle,
produces a MarketState dict, and maintains online regime clustering.

Features are computed from a 300-bar tail of strategy.candles using
qengine indicators. Danger scoring uses Welford online normalization
with weighted feature combination and sigmoid output.

Regime detection uses incremental k-means on the 4D state vector
[danger, trend_strength, volatility, efficiency].
"""

import math
import numpy as np
import qengine.indicators as ta


# ---------------------------------------------------------------------------
# Welford online normalizer (self-contained, mirrors DangerScorer pattern)
# ---------------------------------------------------------------------------

class _WelfordNormalizer:
    """Online mean/variance via Welford's algorithm. O(1) per update."""

    __slots__ = ('n', 'mean', 'm2')

    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, x: float) -> float:
        """Add observation, return z-score (0.0 during warmup)."""
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.m2 += delta * delta2
        if self.n < 2:
            return 0.0
        var = self.m2 / (self.n - 1)
        std = math.sqrt(var) if var > 0 else 1e-8
        return (x - self.mean) / std

    def state_dict(self) -> dict:
        return {'n': self.n, 'mean': self.mean, 'm2': self.m2}

    def load_state_dict(self, d: dict):
        self.n = d['n']
        self.mean = d['mean']
        self.m2 = d['m2']


# ---------------------------------------------------------------------------
# Danger feature definitions: (key, weight, inverted)
# Inverted means high raw value = LOW danger (negate z-score).
# ---------------------------------------------------------------------------

_DANGER_FEATURES = [
    ('range_atr',      0.25, True),   # low range/ATR = choppy = danger
    ('chop',           0.20, False),  # high choppiness = danger
    ('adx',            0.15, True),   # low ADX = no trend = danger
    ('hurst',          0.15, True),   # close to 0.5 = random = danger
    ('atr_ratio',      0.15, False),  # high ATR ratio = volatile = danger
    ('ema_slope_mag',  0.10, True),   # flat slope = danger
]

EPS = 1e-12
_MIN_CANDLES = 50
_TAIL_SIZE = 300
_HURST_WINDOW = 100


# ---------------------------------------------------------------------------
# Incremental k-means for regime clustering
# ---------------------------------------------------------------------------

class _IncrementalKMeans:
    """
    Simple online k-means over 4D state vectors.

    Starts with k=1 centroid, grows up to k_max when a cluster's
    variance exceeds a split threshold.
    """

    def __init__(self, k_max: int = 5, split_var_threshold: float = 0.15):
        self.k_max = k_max
        self.split_var_threshold = split_var_threshold
        # Each centroid: {'mean': np.array(4,), 'n': int, 'm2': np.array(4,)}
        self.centroids: list[dict] = []
        self._init_first_centroid()

    def _init_first_centroid(self):
        self.centroids = [{
            'mean': np.zeros(4),
            'n': 0,
            'm2': np.zeros(4),
        }]

    @property
    def k(self) -> int:
        return len(self.centroids)

    def update(self, x: np.ndarray) -> tuple[int, float]:
        """
        Assign x to nearest centroid, update it, return (cluster_id, confidence).

        Confidence = 1 - d_nearest / (d_second_nearest + eps).
        If only one centroid, confidence is based on distance decay.
        """
        distances = np.array([np.linalg.norm(x - c['mean']) for c in self.centroids])
        nearest = int(np.argmin(distances))
        d_nearest = distances[nearest]

        # Update centroid via Welford (running mean + variance)
        c = self.centroids[nearest]
        c['n'] += 1
        delta = x - c['mean']
        c['mean'] = c['mean'] + delta / c['n']
        delta2 = x - c['mean']
        c['m2'] = c['m2'] + delta * delta2

        # Confidence calculation
        if self.k == 1:
            # Single cluster: confidence decays with distance from centroid
            confidence = 1.0 / (1.0 + d_nearest)
        else:
            sorted_d = np.sort(distances)
            d_second = sorted_d[1]
            confidence = 1.0 - d_nearest / (d_second + EPS)
            confidence = max(0.0, min(1.0, confidence))

        # Check split condition
        self._maybe_split()

        return nearest, confidence

    def _maybe_split(self):
        """Split the highest-variance cluster if it exceeds threshold and k < k_max."""
        if self.k >= self.k_max:
            return
        for i, c in enumerate(self.centroids):
            if c['n'] < 10:
                continue
            var = c['m2'] / (c['n'] - 1 + EPS)
            max_var = float(np.max(var))
            if max_var > self.split_var_threshold:
                # Split: create two centroids offset along the max-variance dimension
                dim = int(np.argmax(var))
                offset = np.zeros(4)
                offset[dim] = math.sqrt(max_var) * 0.5
                new_a = {
                    'mean': c['mean'] + offset,
                    'n': c['n'] // 2,
                    'm2': c['m2'] * 0.25,  # reduce variance estimate
                }
                new_b = {
                    'mean': c['mean'] - offset,
                    'n': c['n'] // 2,
                    'm2': c['m2'] * 0.25,
                }
                self.centroids[i] = new_a
                self.centroids.append(new_b)
                break  # one split per update

    def state_dict(self) -> dict:
        return {
            'k_max': self.k_max,
            'split_var_threshold': self.split_var_threshold,
            'centroids': [
                {'mean': c['mean'].tolist(), 'n': c['n'], 'm2': c['m2'].tolist()}
                for c in self.centroids
            ],
        }

    def load_state_dict(self, d: dict):
        self.k_max = d['k_max']
        self.split_var_threshold = d['split_var_threshold']
        self.centroids = [
            {'mean': np.array(c['mean']), 'n': c['n'], 'm2': np.array(c['m2'])}
            for c in d['centroids']
        ]


# ---------------------------------------------------------------------------
# Feature extraction helpers
# ---------------------------------------------------------------------------

def _safe_float(x) -> float:
    """Convert indicator output to a safe float, replacing NaN/Inf with 0."""
    if x is None:
        return 0.0
    f = float(x)
    if math.isnan(f) or math.isinf(f):
        return 0.0
    return f


def _hurst_rs(closes: np.ndarray, window: int = _HURST_WINDOW) -> float:
    """
    Simplified Hurst exponent via rescaled range (R/S) on the last `window` bars.

    Returns value in roughly [0, 1]:
      ~0.5 = random walk, >0.5 = trending, <0.5 = mean-reverting.
    Falls back to 0.5 if insufficient data.
    """
    if len(closes) < window:
        return 0.5
    series = closes[-window:]
    returns = np.diff(np.log(series + EPS))
    if len(returns) < 2:
        return 0.5

    mean_r = np.mean(returns)
    deviate = np.cumsum(returns - mean_r)
    r = float(np.max(deviate) - np.min(deviate))
    s = float(np.std(returns, ddof=1))
    if s < EPS:
        return 0.5

    rs = r / s
    # H = log(R/S) / log(n)
    n = len(returns)
    if rs < EPS or n < 2:
        return 0.5
    h = math.log(rs) / math.log(n)
    # Clamp to [0, 1]
    return max(0.0, min(1.0, h))


def _extract_features(candles: np.ndarray, fee_rate: float = 0.0) -> dict:
    """
    Compute all market features from a candle array.

    Parameters
    ----------
    candles : np.ndarray
        Shape (N, 6) with columns [timestamp, open, close, high, low, volume].
    fee_rate : float
        Strategy fee/spread rate for normalised spread feature.

    Returns
    -------
    dict of feature name -> float value.
    """
    closes = candles[:, 2]   # close column

    # Volatility
    natr_14 = _safe_float(ta.natr(candles, period=14))
    natr_50 = _safe_float(ta.natr(candles, period=50))

    atr_14 = _safe_float(ta.atr(candles, period=14))
    atr_50 = _safe_float(ta.atr(candles, period=50))
    atr_ratio = atr_14 / (atr_50 + EPS)

    # Trend
    adx_14 = _safe_float(ta.adx(candles, period=14))

    # EMA slopes
    ema_8 = ta.ema(candles, period=8, sequential=True)
    ema_21 = ta.ema(candles, period=21, sequential=True)
    ema_slope_8 = float(ema_8[-1] - ema_8[-2]) / (abs(float(ema_8[-2])) + EPS)
    ema_slope_21 = float(ema_21[-1] - ema_21[-2]) / (abs(float(ema_21[-2])) + EPS)

    # Hurst exponent
    hurst = _hurst_rs(closes)

    # Choppiness index
    chop_14 = _safe_float(ta.chop(candles, period=14))

    # Range / ATR — bar range normalised by ATR
    bar_range = float(candles[-1, 3] - candles[-1, 4])  # high - low
    range_atr = bar_range / (atr_14 + EPS)

    # Spread normalised by ATR
    spread_norm = fee_rate / (natr_14 / 100.0 + EPS) if natr_14 > 0 else 0.0

    return {
        'natr_14': natr_14,
        'natr_50': natr_50,
        'atr_ratio': atr_ratio,
        'adx': adx_14,
        'ema_slope_8': ema_slope_8,
        'ema_slope_21': ema_slope_21,
        'hurst': hurst,
        'chop': chop_14,
        'range_atr': range_atr,
        'spread_norm': spread_norm,
        'ema_slope_mag': abs(ema_slope_8) + abs(ema_slope_21),
    }


# ---------------------------------------------------------------------------
# MarketBrain
# ---------------------------------------------------------------------------

class MarketBrain:
    """
    ARIA Layer 1 -- market feature extraction, danger scoring, and regime detection.

    Called once per candle via ``update(strategy)``. Produces a MarketState dict
    consumed by the Observer (Layer 2) and ActionSelector (Layer 3).

    Parameters
    ----------
    config : dict, optional
        - warmup (int): bars before danger/regime outputs are trusted. Default 50.
        - k_max (int): max regime clusters. Default 5.
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self._warmup = config.get('warmup', 50)
        self._k_max = config.get('k_max', 5)

        # Danger scoring: Welford normalizers per feature
        self._normalizers = {f[0]: _WelfordNormalizer() for f in _DANGER_FEATURES}
        self._danger = 0.5

        # Regime clustering
        self._cluster = _IncrementalKMeans(k_max=self._k_max)
        self._regime_id = 0
        self._regime_confidence = 0.5

        # State tracking
        self._update_count = 0
        self._current_state: dict = self._neutral_state()
        self._features: dict = {}

    # ----- public API -----

    def update(self, strategy) -> dict:
        """
        Extract features from strategy candles and return a MarketState dict.

        Parameters
        ----------
        strategy : qengine Strategy instance
            Must have `.candles` (np.ndarray) and optionally `.fee_rate` (float).

        Returns
        -------
        dict — MarketState with keys: danger, trend_strength, volatility,
               efficiency, regime_id, regime_confidence, features.
        """
        candles = strategy.candles
        if candles is None or len(candles) < _MIN_CANDLES:
            self._current_state = self._neutral_state()
            return self._current_state

        # Use a 300-bar tail to keep indicator cost bounded
        tail = candles[-_TAIL_SIZE:] if len(candles) > _TAIL_SIZE else candles

        # Extract raw features
        fee_rate = getattr(strategy, 'fee_rate', 0.0)
        self._features = _extract_features(tail, fee_rate)

        self._update_count += 1

        # Compute danger score
        self._danger = self._compute_danger(self._features)

        # Derived state signals (all normalised [0, 1])
        trend_strength = min(1.0, max(0.0, self._features['adx'] / 60.0))
        volatility = min(1.0, max(0.0, self._features['natr_14'] / 2.0))
        efficiency = self._features['hurst']  # already [0, 1]

        # Regime clustering
        if self._update_count <= self._warmup:
            self._regime_id = 0
            self._regime_confidence = 0.5
        else:
            state_vec = np.array([
                self._danger, trend_strength, volatility, efficiency
            ])
            self._regime_id, self._regime_confidence = self._cluster.update(state_vec)

        self._current_state = {
            'danger': round(self._danger, 6),
            'trend_strength': round(trend_strength, 6),
            'volatility': round(volatility, 6),
            'efficiency': round(efficiency, 6),
            'regime_id': self._regime_id,
            'regime_confidence': round(self._regime_confidence, 6),
            'features': {k: round(v, 8) for k, v in self._features.items()},
        }
        return self._current_state

    @property
    def current_state(self) -> dict:
        """Return last computed MarketState."""
        return self._current_state

    # ----- persistence -----

    def state_dict(self) -> dict:
        """Serialize full state for persistence."""
        return {
            'update_count': self._update_count,
            'danger': self._danger,
            'regime_id': self._regime_id,
            'regime_confidence': self._regime_confidence,
            'warmup': self._warmup,
            'k_max': self._k_max,
            'normalizers': {k: v.state_dict() for k, v in self._normalizers.items()},
            'cluster': self._cluster.state_dict(),
            'current_state': self._current_state,
        }

    def load_state_dict(self, d: dict):
        """Restore from persisted state."""
        self._update_count = d['update_count']
        self._danger = d['danger']
        self._regime_id = d['regime_id']
        self._regime_confidence = d['regime_confidence']
        self._warmup = d.get('warmup', 50)
        self._k_max = d.get('k_max', 5)
        for k, v in d.get('normalizers', {}).items():
            if k in self._normalizers:
                self._normalizers[k].load_state_dict(v)
        self._cluster.load_state_dict(d['cluster'])
        self._current_state = d.get('current_state', self._neutral_state())

    # ----- internals -----

    def _compute_danger(self, features: dict) -> float:
        """
        Welford-normalised weighted danger score with sigmoid output.

        During warmup, feeds data to normalizers but returns 0.5 (neutral).
        """
        if self._update_count < self._warmup:
            for key, _, _ in _DANGER_FEATURES:
                if key in features:
                    self._normalizers[key].update(features[key])
            return 0.5

        weighted_sum = 0.0
        total_weight = 0.0

        for key, weight, inverted in _DANGER_FEATURES:
            if key not in features:
                continue
            z = self._normalizers[key].update(features[key])
            if inverted:
                z = -z
            weighted_sum += weight * z
            total_weight += weight

        if total_weight > 0:
            weighted_sum /= total_weight

        # Sigmoid maps (-inf, inf) -> (0, 1)
        return 1.0 / (1.0 + math.exp(-weighted_sum))

    @staticmethod
    def _neutral_state() -> dict:
        """Default state when data is insufficient."""
        return {
            'danger': 0.5,
            'trend_strength': 0.0,
            'volatility': 0.0,
            'efficiency': 0.5,
            'regime_id': 0,
            'regime_confidence': 0.0,
            'features': {},
        }
