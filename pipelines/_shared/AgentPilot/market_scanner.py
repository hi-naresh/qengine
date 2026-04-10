"""MarketScanner — lightweight pre-filter that detects trigger events."""
from __future__ import annotations
import math
import numpy as np
import qengine.indicators as ta


class MarketScanner:
    """
    Scans each candle for structural and market triggers.
    Returns (should_consult, trigger_reason) to control when the LLM is called.

    Three trigger types:
      1. Structural: position events, level-up, cycle end
      2. Market: ATR spike, EMA cross, RSI extremes, danger shift
      3. Scheduled: min_interval bars since last consultation
    """

    def __init__(self, config: dict):
        cfg = config.get('scanner', {})
        self._min_interval = cfg.get('min_consult_interval', 240)
        self._atr_spike_mult = cfg.get('atr_spike_mult', 1.5)
        self._rsi_thresholds = cfg.get('rsi_thresholds', [30, 70])
        self._danger_thresholds = cfg.get('danger_thresholds', [0.3, 0.7])
        self._max_hold_bars = cfg.get('max_hold_bars', 480)
        self._enabled = cfg.get('enabled', True)

        # State tracking
        self._last_consult_bar: int = -9999
        self._last_rsi: float = 50.0
        self._last_danger: float = 0.5
        self._last_ema_fast: float = 0.0
        self._last_ema_slow: float = 0.0
        self._atr_history: list[float] = []
        self._atr_mean: float = 0.0
        self._position_open_bar: int = -1
        self._last_level: int = 0

        # Pending structural triggers (set externally)
        self._structural_trigger: str | None = None

        # Stats
        self.triggers_fired: int = 0
        self.trigger_counts: dict = {
            'structural': 0,
            'market': 0,
            'scheduled': 0,
        }

    def set_structural_trigger(self, reason: str) -> None:
        """Set a pending structural trigger (called by AgentPilot hooks)."""
        self._structural_trigger = reason

    def scan(self, strategy, current_bar: int, danger_score: float = 0.5) -> tuple[bool, str]:
        """
        Scan for triggers. Returns (should_consult, trigger_reason).

        Parameters
        ----------
        strategy : Strategy instance
        current_bar : current candle index
        danger_score : danger score from market brain (if available)
        """
        if not self._enabled:
            return False, ''

        # 1. Structural triggers (highest priority)
        if self._structural_trigger:
            reason = self._structural_trigger
            self._structural_trigger = None
            self._last_consult_bar = current_bar
            self.triggers_fired += 1
            self.trigger_counts['structural'] += 1
            return True, reason

        # 2. Check level-up (for Martingale strategy)
        current_level = strategy.vars.get('level', 0) if hasattr(strategy, 'vars') else 0
        if current_level > self._last_level:
            self._last_level = current_level
            self._last_consult_bar = current_bar
            self.triggers_fired += 1
            self.trigger_counts['structural'] += 1
            return True, f'level_up_to_{current_level}'

        # 3. Position held too long without consultation
        if strategy.is_open:
            if self._position_open_bar < 0:
                self._position_open_bar = current_bar
            bars_held = current_bar - self._position_open_bar
            bars_since_consult = current_bar - self._last_consult_bar
            if bars_held > self._max_hold_bars and bars_since_consult > self._min_interval:
                self._last_consult_bar = current_bar
                self.triggers_fired += 1
                self.trigger_counts['structural'] += 1
                return True, 'max_hold_duration'
        else:
            self._position_open_bar = -1

        # 4. Minimum interval check (don't fire market triggers too frequently)
        bars_since = current_bar - self._last_consult_bar
        if bars_since < self._min_interval:
            return False, ''

        # 5. Market triggers
        candles = strategy.candles
        if candles is None or len(candles) < 50:
            return False, ''

        trigger = self._check_market_triggers(candles, danger_score)
        if trigger:
            self._last_consult_bar = current_bar
            self.triggers_fired += 1
            self.trigger_counts['market'] += 1
            return True, trigger

        # 6. Scheduled check-in (fallback)
        if bars_since >= self._min_interval * 2:
            self._last_consult_bar = current_bar
            self.triggers_fired += 1
            self.trigger_counts['scheduled'] += 1
            return True, 'scheduled_checkin'

        return False, ''

    def _check_market_triggers(self, candles: np.ndarray, danger: float) -> str | None:
        """Check market-based triggers. Returns trigger name or None."""
        # ATR spike
        atr_val = float(ta.atr(candles, period=14))
        if not math.isnan(atr_val) and atr_val > 0:
            self._atr_history.append(atr_val)
            if len(self._atr_history) > 100:
                self._atr_history = self._atr_history[-100:]
            self._atr_mean = sum(self._atr_history) / len(self._atr_history)

            if self._atr_mean > 0 and atr_val > self._atr_mean * self._atr_spike_mult:
                return 'atr_spike'

        # EMA crossover
        ema_fast = float(ta.ema(candles, period=8))
        ema_slow = float(ta.ema(candles, period=21))
        if self._last_ema_fast != 0:
            prev_above = self._last_ema_fast > self._last_ema_slow
            curr_above = ema_fast > ema_slow
            if prev_above != curr_above:
                self._last_ema_fast = ema_fast
                self._last_ema_slow = ema_slow
                return 'ema_crossover'
        self._last_ema_fast = ema_fast
        self._last_ema_slow = ema_slow

        # RSI extremes
        rsi_val = float(ta.rsi(candles, period=14))
        if not math.isnan(rsi_val):
            lo, hi = self._rsi_thresholds
            prev_extreme = self._last_rsi <= lo or self._last_rsi >= hi
            curr_extreme = rsi_val <= lo or rsi_val >= hi
            if curr_extreme and not prev_extreme:
                self._last_rsi = rsi_val
                return 'rsi_extreme'
            # Also trigger on exit from extreme
            if prev_extreme and not curr_extreme:
                self._last_rsi = rsi_val
                return 'rsi_normalization'
            self._last_rsi = rsi_val

        # Danger score threshold crossing
        lo_d, hi_d = self._danger_thresholds
        if danger != self._last_danger:
            crossed_up = self._last_danger < hi_d and danger >= hi_d
            crossed_down = self._last_danger > lo_d and danger <= lo_d
            self._last_danger = danger
            if crossed_up:
                return 'danger_high'
            if crossed_down:
                return 'danger_low'

        return None

    def on_cycle_end(self) -> None:
        """Reset per-cycle state."""
        self._last_level = 0
        self._position_open_bar = -1

    # ── Persistence ──

    def state_dict(self) -> dict:
        return {
            'last_consult_bar': self._last_consult_bar,
            'last_rsi': self._last_rsi,
            'last_danger': self._last_danger,
            'last_ema_fast': self._last_ema_fast,
            'last_ema_slow': self._last_ema_slow,
            'atr_history': self._atr_history[-50:],  # keep last 50
            'atr_mean': self._atr_mean,
            'triggers_fired': self.triggers_fired,
            'trigger_counts': self.trigger_counts,
        }

    def load_state_dict(self, d: dict) -> None:
        self._last_consult_bar = d.get('last_consult_bar', -9999)
        self._last_rsi = d.get('last_rsi', 50.0)
        self._last_danger = d.get('last_danger', 0.5)
        self._last_ema_fast = d.get('last_ema_fast', 0.0)
        self._last_ema_slow = d.get('last_ema_slow', 0.0)
        self._atr_history = d.get('atr_history', [])
        self._atr_mean = d.get('atr_mean', 0.0)
        self.triggers_fired = d.get('triggers_fired', 0)
        self.trigger_counts = d.get('trigger_counts', {
            'structural': 0, 'market': 0, 'scheduled': 0,
        })
