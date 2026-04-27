"""
AdaptiveSizer — position size scaling based on confidence and drawdown.

Applies multiplicative confidence and drawdown factors to a base quantity,
with configurable sensitivity, floors, and risk caps.

Part of the IslandPilot pipeline.
"""

import json
from typing import Any, Dict, Optional

import numpy as np


class AdaptiveSizer:
    """Scales position size by confidence and drawdown factors."""

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self.drawdown_threshold_pct = config.get("drawdown_threshold_pct", 5.0)
        self.min_confidence_scale = config.get("min_confidence_scale", 0.2)
        self.min_drawdown_scale = config.get("min_drawdown_scale", 0.1)
        self.max_risk_per_cycle_pct = config.get("max_risk_per_cycle_pct", 15.0)

        # Tracking stats
        self._calls: int = 0
        self._sum_confidence_scale: float = 0.0
        self._sum_drawdown_factor: float = 0.0
        self._sum_combined: float = 0.0

    def compute(
        self,
        base_pct: float,
        confidence: float,
        sensitivity: float,
        drawdown_pct: float,
        recovery_aggression: float,
        balance: float,
        qty: float,
        strategy: Any = None,
    ) -> float:
        """
        Compute adjusted position quantity.

        Three multiplicative factors:
        - confidence_scale = max(min_scale, confidence^sensitivity)
        - drawdown_factor = 1.0 if dd < threshold, else max(min_dd_scale, 1 - depth * aggression)
        - combined = confidence_scale * drawdown_factor
        - adjusted = qty * combined, capped by max_risk_pct of balance, floored at qty * 0.01
        """
        # Confidence scaling
        confidence_scale = max(self.min_confidence_scale, confidence ** sensitivity)

        # Drawdown scaling
        if drawdown_pct < self.drawdown_threshold_pct:
            drawdown_factor = 1.0
        else:
            depth = (drawdown_pct - self.drawdown_threshold_pct) / 100.0
            drawdown_factor = max(
                self.min_drawdown_scale,
                1.0 - depth * recovery_aggression * 10.0,
            )

        combined = confidence_scale * drawdown_factor
        adjusted = qty * combined

        # Cap by max risk
        if balance > 0:
            max_qty = balance * (self.max_risk_per_cycle_pct / 100.0)
            adjusted = min(adjusted, max_qty)

        # Floor: never return zero
        floor = qty * 0.01
        adjusted = max(adjusted, floor)

        # Track stats
        self._calls += 1
        self._sum_confidence_scale += confidence_scale
        self._sum_drawdown_factor += drawdown_factor
        self._sum_combined += combined

        return adjusted

    def get_stats(self) -> Dict[str, float]:
        """Return average scaling stats."""
        if self._calls == 0:
            return {
                "calls": 0,
                "avg_confidence_scale": 0.0,
                "avg_drawdown_factor": 0.0,
                "avg_combined": 0.0,
            }
        return {
            "calls": self._calls,
            "avg_confidence_scale": self._sum_confidence_scale / self._calls,
            "avg_drawdown_factor": self._sum_drawdown_factor / self._calls,
            "avg_combined": self._sum_combined / self._calls,
        }

    def save(self, path: str) -> None:
        data = {
            "config": {
                "drawdown_threshold_pct": self.drawdown_threshold_pct,
                "min_confidence_scale": self.min_confidence_scale,
                "min_drawdown_scale": self.min_drawdown_scale,
                "max_risk_per_cycle_pct": self.max_risk_per_cycle_pct,
            },
            "stats": {
                "calls": self._calls,
                "sum_confidence_scale": self._sum_confidence_scale,
                "sum_drawdown_factor": self._sum_drawdown_factor,
                "sum_combined": self._sum_combined,
            },
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "AdaptiveSizer":
        with open(path) as f:
            data = json.load(f)
        obj = cls(data["config"])
        stats = data.get("stats", {})
        obj._calls = stats.get("calls", 0)
        obj._sum_confidence_scale = stats.get("sum_confidence_scale", 0.0)
        obj._sum_drawdown_factor = stats.get("sum_drawdown_factor", 0.0)
        obj._sum_combined = stats.get("sum_combined", 0.0)
        return obj
