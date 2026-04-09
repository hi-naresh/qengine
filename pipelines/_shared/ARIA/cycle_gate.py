"""
CycleGate — Layer 2 of the ARIA pipeline.

An online logistic regression classifier that learns to block bad entries.
Predicts P(profitable | market_state, account_state) and blocks entries
when the predicted probability falls below an adaptive threshold.

The model starts permissive (all entries allowed) and gradually tightens
as it accumulates cycle outcomes.  During a configurable warmup period
the gate always allows entry but still collects data and updates weights.

Feature vector (17 dimensions):
  - 4 continuous market features: danger, trend_strength, volatility, efficiency
  - 5 regime one-hot: regime_id encoded as k binary features (k_max=5)
  - 3 account features: equity drawdown %, consecutive busts, cycles since bust
  - 4 session one-hot: Asian / London / Overlap / New York
  - 1 bias term

Update rule (SGD with L2 regularisation):
  w += lr * (y - p) * x - lr * l2 * w
  where y=1 if profitable, y=0 if bust, p = sigmoid(w·x)
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_N_FEATURES = 17          # 4 market + 5 regime + 3 account + 4 session + 1 bias
_K_MAX_DEFAULT = 5        # max regime clusters (one-hot width)
_SESSION_NAMES = ('asian', 'london', 'overlap', 'new_york')
_MAX_THRESHOLD = 0.4      # ceiling for adaptive threshold
_THRESHOLD_RAMP = 0.01    # threshold increment per cycle after warmup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sigmoid(z: float) -> float:
    """Numerically stable sigmoid function."""
    z = max(-500.0, min(500.0, z))  # clip to avoid overflow
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _session_from_hour(hour: float) -> str:
    """Map UTC hour to trading session name.

    Sessions:
      00–08  Asian
      08–12  London
      12–17  Overlap (London + New York)
      17–22  New York
      22–24  Asian (overnight)

    Parameters
    ----------
    hour : float
        UTC hour, typically in [0, 24).

    Returns
    -------
    str
        One of ``'asian'``, ``'london'``, ``'overlap'``, ``'new_york'``.
    """
    if 0 <= hour < 8:
        return 'asian'
    if 8 <= hour < 12:
        return 'london'
    if 12 <= hour < 17:
        return 'overlap'
    if 17 <= hour < 22:
        return 'new_york'
    return 'asian'


def _safe_float(x, default: float = 0.0) -> float:
    """Convert to float, replacing None / NaN / Inf with *default*."""
    if x is None:
        return default
    try:
        f = float(x)
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return f


# ---------------------------------------------------------------------------
# Feature builder
# ---------------------------------------------------------------------------

def _build_features(
    market_state: dict,
    strategy,
    *,
    k_max: int = _K_MAX_DEFAULT,
    peak_equity: float = 0.0,
) -> np.ndarray:
    """Construct the 17-dimensional feature vector for the classifier.

    Parameters
    ----------
    market_state : dict
        MarketState dict from MarketBrain (keys: danger, trend_strength,
        volatility, efficiency, regime_id, ...).
    strategy
        Live strategy object with ``.balance``, ``.vars``, ``.candles``.
    k_max : int
        Number of regime slots for one-hot encoding.
    peak_equity : float
        Highest equity observed so far (for drawdown calculation).

    Returns
    -------
    np.ndarray
        Shape ``(17,)`` feature vector with a bias term at the end.
    """
    x = np.zeros(_N_FEATURES, dtype=np.float64)

    # --- 4 continuous market features [0:4] ---
    x[0] = _safe_float(market_state.get('danger'), 0.5)
    x[1] = _safe_float(market_state.get('trend_strength'), 0.0)
    x[2] = _safe_float(market_state.get('volatility'), 0.0)
    x[3] = _safe_float(market_state.get('efficiency'), 0.5)

    # --- 5 regime one-hot [4:9] ---
    regime_id = int(_safe_float(market_state.get('regime_id'), 0.0))
    if 0 <= regime_id < k_max:
        x[4 + regime_id] = 1.0

    # --- 3 account features [9:12] ---
    equity = _safe_float(getattr(strategy, 'balance', 0.0))

    # Drawdown %: how far equity has fallen from peak
    if peak_equity > 0:
        dd_pct = max(0.0, (peak_equity - equity) / peak_equity)
    else:
        dd_pct = 0.0
    x[9] = min(dd_pct, 1.0)  # clip to [0, 1]

    sv = getattr(strategy, 'vars', {}) if hasattr(strategy, 'vars') else {}
    x[10] = min(_safe_float(sv.get('consecutive_busts'), 0.0), 20.0) / 20.0  # normalise

    # Cycles since last bust — derive from sessions list
    sessions = sv.get('sessions', [])
    cycles_since_bust = 0
    for sess in reversed(sessions):
        pnl = _safe_float(sess.get('pnl'), 0.0)
        if pnl < 0:
            break
        cycles_since_bust += 1
    x[11] = min(cycles_since_bust, 100.0) / 100.0  # normalise

    # --- 4 session one-hot [12:16] ---
    candles = getattr(strategy, 'candles', None)
    if candles is not None and hasattr(candles, '__len__') and len(candles) > 0:
        try:
            ts_ms = float(candles[-1][0])
            # Candle timestamps are milliseconds since epoch
            hour = (ts_ms / 1000.0 / 3600.0) % 24.0
        except (IndexError, TypeError, ValueError):
            hour = 0.0
    else:
        hour = 0.0

    session = _session_from_hour(hour)
    session_idx = _SESSION_NAMES.index(session) if session in _SESSION_NAMES else 0
    x[12 + session_idx] = 1.0

    # --- 1 bias [16] ---
    x[16] = 1.0

    return x


# ---------------------------------------------------------------------------
# CycleGate
# ---------------------------------------------------------------------------

class CycleGate:
    """Online logistic regression entry gate for the ARIA pipeline.

    Learns from completed trading cycles to predict P(profitable) and
    blocks entries when that probability falls below an adaptive threshold.

    Parameters
    ----------
    config : dict, optional
        Recognised keys:

        - ``warmup_cycles`` (int, default 30) — cycles before gating starts.
        - ``learning_rate`` (float, default 0.01) — SGD step size.
        - ``l2_lambda`` (float, default 0.001) — L2 regularisation strength.
        - ``k_max`` (int, default 5) — max regime clusters (one-hot width).
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self._warmup = int(cfg.get('warmup_cycles', 30))
        self._lr = float(cfg.get('learning_rate', 0.01))
        self._l2 = float(cfg.get('l2_lambda', 0.001))
        self._k_max = int(cfg.get('k_max', _K_MAX_DEFAULT))

        self._weights = np.zeros(_N_FEATURES, dtype=np.float64)
        self._n_cycles = 0
        self._peak_equity = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, market_state: dict, strategy) -> float:
        """Return P(profitable | features).

        Does **not** update weights — call :meth:`update` after a cycle
        completes to perform an SGD step.

        Parameters
        ----------
        market_state : dict
            Current MarketState dict from MarketBrain.
        strategy
            Live strategy object.

        Returns
        -------
        float
            Predicted probability in (0, 1).
        """
        self._track_equity(strategy)
        x = _build_features(
            market_state, strategy,
            k_max=self._k_max,
            peak_equity=self._peak_equity,
        )
        z = float(np.dot(self._weights, x))
        return _sigmoid(z)

    def gate(self, market_state: dict, strategy) -> Tuple[bool, float]:
        """Decide whether to allow a new entry.

        Parameters
        ----------
        market_state : dict
            Current MarketState dict from MarketBrain.
        strategy
            Live strategy object.

        Returns
        -------
        (allowed, confidence)
            ``allowed`` is True if the entry should proceed.
            ``confidence`` is the raw P(profitable) prediction.
        """
        p = self.predict(market_state, strategy)
        threshold = self._current_threshold()
        allowed = self._n_cycles < self._warmup or p >= threshold
        return allowed, p

    def update(self, market_state: dict, strategy, profitable: bool) -> None:
        """Perform one SGD weight update after a cycle completes.

        Parameters
        ----------
        market_state : dict
            MarketState dict (at cycle end or entry — either works since
            the model is not sensitive to exact timing).
        strategy
            Live strategy object.
        profitable : bool
            True if the cycle ended profitably, False otherwise.
        """
        self._track_equity(strategy)
        x = _build_features(
            market_state, strategy,
            k_max=self._k_max,
            peak_equity=self._peak_equity,
        )
        y = 1.0 if profitable else 0.0
        z = float(np.dot(self._weights, x))
        p = _sigmoid(z)

        # SGD step: w += lr * (y - p) * x - lr * l2 * w
        gradient = self._lr * (y - p) * x
        decay = self._lr * self._l2 * self._weights
        self._weights = self._weights + gradient - decay

        self._n_cycles += 1

    # ------------------------------------------------------------------
    # Threshold
    # ------------------------------------------------------------------

    def _current_threshold(self) -> float:
        """Adaptive threshold that ramps up after warmup.

        Returns 0.0 during warmup (allow everything).  After warmup,
        increases by 0.01 per cycle, capped at 0.4.
        """
        if self._n_cycles <= self._warmup:
            return 0.0
        return min(_MAX_THRESHOLD, _THRESHOLD_RAMP * (self._n_cycles - self._warmup))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _track_equity(self, strategy) -> None:
        """Update peak equity for drawdown calculation."""
        equity = _safe_float(getattr(strategy, 'balance', 0.0))
        if equity > self._peak_equity:
            self._peak_equity = equity

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def n_cycles(self) -> int:
        """Number of cycles the gate has processed."""
        return self._n_cycles

    @property
    def weights(self) -> np.ndarray:
        """Current weight vector (read-only copy)."""
        return self._weights.copy()

    @property
    def threshold(self) -> float:
        """Current adaptive threshold."""
        return self._current_threshold()

    @property
    def is_warmed_up(self) -> bool:
        """True if the warmup period has elapsed."""
        return self._n_cycles >= self._warmup

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def state_dict(self) -> dict:
        """Serialize gate state for persistence."""
        return {
            'weights': self._weights.tolist(),
            'n_cycles': self._n_cycles,
            'peak_equity': self._peak_equity,
            'warmup': self._warmup,
            'lr': self._lr,
            'l2': self._l2,
            'k_max': self._k_max,
        }

    def load_state_dict(self, d: dict) -> None:
        """Restore gate state from a previously saved dict."""
        weights = d.get('weights')
        if weights is not None:
            w = np.asarray(weights, dtype=np.float64)
            if w.shape == (_N_FEATURES,):
                self._weights = w
        self._n_cycles = int(d.get('n_cycles', 0))
        self._peak_equity = float(d.get('peak_equity', 0.0))
        self._warmup = int(d.get('warmup', self._warmup))
        self._lr = float(d.get('lr', self._lr))
        self._l2 = float(d.get('l2', self._l2))
        self._k_max = int(d.get('k_max', self._k_max))
