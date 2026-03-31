from collections import deque
import bisect


class EntryGate:
    """
    Blocks strategy entries when danger score exceeds a percentile threshold.

    Maintains a rolling window of recent danger scores and computes the
    threshold as the Nth percentile. When the current danger exceeds this
    threshold, entry is blocked.

    Usage:
        gate = EntryGate({'percentile': 75, 'window': 500})
        gate.observe(danger_score)          # feed every candle
        allowed = gate.should_allow(score)  # check before entry
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.percentile = config.get('percentile', 75)
        self.window_size = config.get('window', 500)
        self.enabled = config.get('enabled', True)
        self._scores = deque(maxlen=self.window_size)
        self._sorted_cache = []
        self._cache_dirty = True
        self._threshold = float('inf')  # allow everything until enough data

    def observe(self, score: float):
        """Feed a danger score (call every candle)."""
        self._scores.append(score)
        self._cache_dirty = True

    def _recompute_threshold(self):
        if not self._scores or len(self._scores) < 10:
            self._threshold = float('inf')
            return
        self._sorted_cache = sorted(self._scores)
        idx = int(len(self._sorted_cache) * self.percentile / 100.0)
        idx = min(idx, len(self._sorted_cache) - 1)
        self._threshold = self._sorted_cache[idx]
        self._cache_dirty = False

    def should_allow(self, score: float) -> bool:
        """Returns True if entry is allowed (danger below threshold)."""
        if not self.enabled:
            return True
        if self._cache_dirty:
            self._recompute_threshold()
        return score < self._threshold

    @property
    def current_threshold(self) -> float:
        if self._cache_dirty:
            self._recompute_threshold()
        return self._threshold

    @property
    def stats(self) -> dict:
        return {
            'percentile': self.percentile,
            'threshold': round(self._threshold, 4) if self._threshold != float('inf') else None,
            'window_fill': len(self._scores),
            'window_size': self.window_size,
        }
