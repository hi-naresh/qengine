# pipelines/_shared/GTSBotPilot/trend_filter.py
"""
TrendFilter — Layer 1 of GTSBotPilot.

Replaces the paper's SCG neural network + Trend Classification Block (TCB).
The NN's role is noise reduction; we achieve the same with EMA smoothing.

Derivative-based trend classification (from paper Eq. 2-4):
  Long Trend:   d1 > delta AND d2 > 0
  Short Trend:  d1 < -delta AND d2 < 0
  Null Trend:   otherwise

Where:
  d1 = smoothed(k) - smoothed(k-1)           # 1st derivative (momentum)
  d2 = smoothed(k) - 2*smoothed(k-1) + smoothed(k-2)  # 2nd derivative (acceleration)
  delta = threshold filtering weak signals
"""
import numpy as np
from qengine import indicators as ta


TREND_LONG = 'long'
TREND_SHORT = 'short'
TREND_NULL = 'null'


class TrendFilter:
    def __init__(self, config: dict):
        self.smoothing_period: int = config.get('smoothing_period', 14)
        self.delta_atr_mult: float = config.get('delta_atr_mult', 0.02)
        self.require_direction_match: bool = config.get('require_direction_match', True)
        self.enabled: bool = config.get('enabled', True)

        # State
        self.current_trend: str = TREND_NULL
        self.d1: float = 0.0
        self.d2: float = 0.0
        self.delta: float = 0.0  # adaptive, computed from ATR

        # Stats
        self._entries_blocked: int = 0
        self._entries_allowed: int = 0
        self._trend_counts: dict = {TREND_LONG: 0, TREND_SHORT: 0, TREND_NULL: 0}

    def update(self, candles: np.ndarray) -> str:
        """Compute smoothed derivatives and classify trend. Called each candle."""
        if not self.enabled:
            self.current_trend = TREND_NULL
            return self.current_trend

        min_candles = self.smoothing_period + 2
        if candles is None or len(candles) < min_candles:
            self.current_trend = TREND_NULL
            return self.current_trend

        smoothed = ta.ema(candles, period=self.smoothing_period, source_type='close', sequential=True)

        self.d1 = smoothed[-1] - smoothed[-2]
        self.d2 = smoothed[-1] - 2.0 * smoothed[-2] + smoothed[-3]

        # Adaptive delta: scale by ATR so threshold adjusts to volatility
        if len(candles) >= 14:
            atr = ta.atr(candles, period=14)
            self.delta = atr * self.delta_atr_mult
        # Fallback: use price-based fraction if ATR unavailable
        if self.delta <= 0:
            close = candles[-1, 2]
            self.delta = close * 0.00001  # 1 pip equivalent

        if self.d1 > self.delta and self.d2 > 0:
            self.current_trend = TREND_LONG
        elif self.d1 < -self.delta and self.d2 < 0:
            self.current_trend = TREND_SHORT
        else:
            self.current_trend = TREND_NULL

        self._trend_counts[self.current_trend] += 1
        return self.current_trend

    def should_allow_entry(self, strategy) -> bool:
        """Gate entry based on trend. Returns True to allow, False to block."""
        if not self.enabled:
            self._entries_allowed += 1
            return True

        if self.current_trend == TREND_NULL:
            self._entries_blocked += 1
            return False

        if self.require_direction_match:
            wants_long = getattr(strategy, '_should_long', False)
            wants_short = getattr(strategy, '_should_short', False)

            if wants_long and self.current_trend != TREND_LONG:
                self._entries_blocked += 1
                return False
            if wants_short and self.current_trend != TREND_SHORT:
                self._entries_blocked += 1
                return False

        self._entries_allowed += 1
        return True

    @property
    def stats(self) -> dict:
        total = self._entries_allowed + self._entries_blocked
        return {
            'current_trend': self.current_trend,
            'd1': round(self.d1, 8),
            'd2': round(self.d2, 8),
            'entries_allowed': self._entries_allowed,
            'entries_blocked': self._entries_blocked,
            'block_rate': round(self._entries_blocked / total, 4) if total > 0 else 0.0,
            'trend_counts': dict(self._trend_counts),
        }
