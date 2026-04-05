from collections import deque
import bisect


class EntryGate:
    """
    Blocks strategy entries when danger score exceeds a percentile threshold.

    Maintains a rolling window of recent danger scores with an incrementally
    maintained sorted list for O(log n) threshold lookups.

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
        self._sorted = []  # incrementally maintained sorted list
        self._threshold = float('inf')  # allow everything until enough data

    def observe(self, score: float):
        """Feed a danger score (call every candle). O(log n) via bisect."""
        # If window is full, remove the oldest score from sorted list
        if len(self._scores) == self.window_size:
            old = self._scores[0]
            idx = bisect.bisect_left(self._sorted, old)
            if idx < len(self._sorted) and self._sorted[idx] == old:
                self._sorted.pop(idx)
        self._scores.append(score)
        bisect.insort(self._sorted, score)
        # Recompute threshold inline
        n = len(self._sorted)
        if n < 10:
            self._threshold = float('inf')
        else:
            idx = min(int(n * self.percentile / 100.0), n - 1)
            self._threshold = self._sorted[idx]

    def should_allow(self, score: float) -> bool:
        """Returns True if entry is allowed (danger below threshold)."""
        if not self.enabled:
            return True
        return score < self._threshold

    @property
    def current_threshold(self) -> float:
        return self._threshold

    @property
    def stats(self) -> dict:
        return {
            'percentile': self.percentile,
            'threshold': round(self._threshold, 4) if self._threshold != float('inf') else None,
            'window_fill': len(self._scores),
            'window_size': self.window_size,
        }
