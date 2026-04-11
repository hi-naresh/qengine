"""
ARIA Structural Stress R(t) — log-constructible execution stress accumulator.

Based on Chen (2026). R(t) = X + C + U + F + M + V where each component
measures a different aspect of execution-level stress. Zero learned parameters.
"""
from __future__ import annotations

import math
from statistics import median
from typing import List


class StructuralStress:
    """Computes and accumulates R(t) structural stress across trading cycles."""

    def __init__(self) -> None:
        self._cycle_stresses: List[dict] = []
        self._r_t: float = 0.0
        self._all_bars: List[int] = []
        self._all_level_gaps: List[float] = []
        self._all_cycle_gaps: List[int] = []

    # ── Component methods ───────────────────────────────────────────────

    def _compute_X(self, levels: int, max_levels: int) -> float:
        """Excess depth beyond designed coverage."""
        if max_levels <= 0:
            return 0.0
        depth_ratio = levels / max_levels
        return max(0.0, depth_ratio - 0.7)

    def _compute_C(self, levels: int, multiplier: float) -> float:
        """Exposure concentration in deep layers."""
        if levels <= 1:
            return 0.0
        exposures = [multiplier ** k for k in range(levels)]
        total = sum(exposures)
        if total == 0:
            return 0.0
        # Top 30% of levels (by index, i.e. deepest)
        n_top = max(1, math.ceil(levels * 0.3))
        top_sum = sum(sorted(exposures, reverse=True)[:n_top])
        return top_sum / total

    def _compute_U(self, bars: int) -> float:
        """Time-under-stress (normalised excess holding)."""
        if not self._all_bars:
            return 0.0
        med = median(self._all_bars)
        if med <= 0:
            return 0.0
        return max(0.0, (bars - med) / med)

    def _compute_F(self, level_timestamps: list) -> float:
        """Entry clustering (rapid level consumption)."""
        if len(level_timestamps) < 2 or not self._all_level_gaps:
            return 0.0
        gaps = [
            level_timestamps[i + 1] - level_timestamps[i]
            for i in range(len(level_timestamps) - 1)
        ]
        med = median(self._all_level_gaps)
        below = sum(1 for g in gaps if g < med)
        return below / len(gaps)

    def _compute_V(self, pnl: float, expected_tp: float, reason: str) -> float:
        """Rebound deficit."""
        if expected_tp <= 0:
            return 0.0
        return min(1.0, max(0.0, 1.0 - pnl / expected_tp))

    def _compute_M(self, gap_bars: int) -> float:
        """Inter-cycle overlap (binary)."""
        if not self._all_cycle_gaps or gap_bars < 0:
            return 0.0
        med = median(self._all_cycle_gaps)
        return 1.0 if gap_bars < med * 0.5 else 0.0

    # ── Record cycle ────────────────────────────────────────────────────

    def record_cycle(self, session: dict) -> dict:
        """Record a completed cycle and return its stress decomposition."""
        X = self._compute_X(session['levels'], session['max_levels'])
        C = self._compute_C(session['levels'], session['multiplier'])
        U = self._compute_U(session['bars'])
        F = self._compute_F(session.get('level_timestamps', []))
        M = self._compute_M(session.get('gap_bars', -1))
        V = self._compute_V(session['pnl'], session['expected_tp'], session.get('reason', ''))

        total = X + C + U + F + M + V

        result = {
            'X': round(X, 6),
            'C': round(C, 6),
            'U': round(U, 6),
            'F': round(F, 6),
            'M': round(M, 6),
            'V': round(V, 6),
            'total': round(total, 6),
        }

        self._cycle_stresses.append(result)
        self._r_t += total

        # Update reference stats
        self._all_bars.append(session['bars'])
        timestamps = session.get('level_timestamps', [])
        if len(timestamps) >= 2:
            for i in range(len(timestamps) - 1):
                self._all_level_gaps.append(float(timestamps[i + 1] - timestamps[i]))
        gap = session.get('gap_bars', -1)
        if gap >= 0:
            self._all_cycle_gaps.append(gap)

        # Cap lists at 1000
        self._cycle_stresses = self._cycle_stresses[-1000:]
        self._all_bars = self._all_bars[-1000:]
        self._all_level_gaps = self._all_level_gaps[-1000:]
        self._all_cycle_gaps = self._all_cycle_gaps[-1000:]

        return result

    # ── Derived signals ─────────────────────────────────────────────────

    @property
    def r_t(self) -> float:
        """Cumulative R(t) sum."""
        return self._r_t

    @property
    def normalised_rt(self) -> float:
        """Normalised R(t): min(1, R(t) / n_cycles)."""
        n = len(self._cycle_stresses)
        if n == 0:
            return 0.0
        return min(1.0, self._r_t / n)

    @property
    def recent_stress_rate(self) -> float:
        """Mean of last 10 cycle totals, capped at 1."""
        if not self._cycle_stresses:
            return 0.0
        recent = self._cycle_stresses[-10:]
        return min(1.0, sum(s['total'] for s in recent) / len(recent))

    @property
    def stress_velocity(self) -> float:
        """Acceleration: mean(last 5) - mean(totals[-20:-5])."""
        if len(self._cycle_stresses) < 20:
            return 0.0
        recent_5 = self._cycle_stresses[-5:]
        older = self._cycle_stresses[-20:-5]
        mean_recent = sum(s['total'] for s in recent_5) / len(recent_5)
        mean_older = sum(s['total'] for s in older) / len(older)
        return mean_recent - mean_older

    def inter_cycle_gap_ratio(self, last_gap: int) -> float:
        """Normalised gap ratio: min(1, (last_gap / median_gap) / 3)."""
        if not self._all_cycle_gaps or last_gap < 0:
            return 1.0
        med = median(self._all_cycle_gaps)
        if med <= 0:
            return 1.0
        return min(1.0, (last_gap / med) / 3.0)

    # ── State persistence ───────────────────────────────────────────────

    def state_dict(self) -> dict:
        return {
            'cycle_stresses': self._cycle_stresses[-1000:],
            'r_t': self._r_t,
            'all_bars': self._all_bars[-1000:],
            'all_level_gaps': self._all_level_gaps[-1000:],
            'all_cycle_gaps': self._all_cycle_gaps[-1000:],
        }

    def load_state_dict(self, d: dict) -> None:
        self._cycle_stresses = d.get('cycle_stresses', [])
        self._r_t = d.get('r_t', 0.0)
        self._all_bars = d.get('all_bars', [])
        self._all_level_gaps = d.get('all_level_gaps', [])
        self._all_cycle_gaps = d.get('all_cycle_gaps', [])
