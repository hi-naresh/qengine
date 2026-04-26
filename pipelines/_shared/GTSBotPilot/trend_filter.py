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
        self.confirm_bars: int = config.get('confirm_bars', 2)
        self.null_tolerance: int = config.get('null_tolerance', 1)  # NULL bars allowed within streak
        self.require_acceleration: bool = config.get('require_acceleration', False)
        self.require_direction_match: bool = config.get('require_direction_match', True)
        self.enabled: bool = config.get('enabled', True)

        # State
        self.current_trend: str = TREND_NULL
        self.d1: float = 0.0
        self.d2: float = 0.0
        self.delta: float = 0.0  # adaptive, computed from ATR
        self._raw_trend: str = TREND_NULL       # single-bar classification
        self._confirm_count: int = 0            # consecutive bars confirming same trend
        self._null_streak: int = 0              # consecutive NULL bars within a streak
        self._pending_trend: str = TREND_NULL   # trend being confirmed

        # Stats
        self._entries_blocked: int = 0
        self._entries_allowed: int = 0
        self._trend_counts: dict = {TREND_LONG: 0, TREND_SHORT: 0, TREND_NULL: 0}

    def update(self, candles: np.ndarray) -> str:
        """Compute smoothed derivatives and classify trend. Called each candle.

        Requires confirm_bars consecutive candles agreeing on direction
        before confirming a trend. This prevents single-bar noise from
        triggering entries — only sustained momentum is confirmed.
        """
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

        # Single-bar raw classification
        # Paper formula: d1 > delta AND d2 > 0 (requires acceleration).
        # With require_acceleration=False (default), only d1 is checked —
        # the d2 condition is too noisy on raw EMA without the paper's SCG NN smoother.
        if self.require_acceleration:
            is_long = self.d1 > self.delta and self.d2 > 0
            is_short = self.d1 < -self.delta and self.d2 < 0
        else:
            is_long = self.d1 > self.delta
            is_short = self.d1 < -self.delta

        if is_long:
            self._raw_trend = TREND_LONG
        elif is_short:
            self._raw_trend = TREND_SHORT
        else:
            self._raw_trend = TREND_NULL

        # Confirmation: require confirm_bars consecutive same-direction bars.
        # null_tolerance allows N null bars within a streak without full reset —
        # prevents choppy 1-minute candles from destroying every confirmation streak.
        if self._raw_trend == TREND_NULL:
            if self._pending_trend != TREND_NULL and self._null_streak < self.null_tolerance:
                # Within tolerance: pause streak, don't reset
                self._null_streak += 1
            else:
                # Exceeded tolerance — full reset
                self._null_streak = 0
                self._confirm_count = 0
                self._pending_trend = TREND_NULL
                self.current_trend = TREND_NULL
        elif self._raw_trend == self._pending_trend:
            # Same direction — resume/increment streak
            self._null_streak = 0
            self._confirm_count += 1
            if self._confirm_count >= self.confirm_bars:
                self.current_trend = self._pending_trend
        else:
            # Direction changed — start new streak
            self._null_streak = 0
            self._pending_trend = self._raw_trend
            self._confirm_count = 1
            if self.confirm_bars <= 1:
                self.current_trend = self._raw_trend
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
