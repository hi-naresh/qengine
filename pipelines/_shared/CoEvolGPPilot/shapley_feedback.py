"""
Approximate Shapley value feedback for CoEvolGPPilot.

The paper (Yang, Xin, Ye & Xia, 2025) uses per-state Shapley values to credit
each sub-population's contribution to overall portfolio performance and scale
selection pressure accordingly.

Exact Shapley computation is exponential in the number of players. The paper's
proposal — already itself an approximation — suggests credit-assignment from
posterior weights at the time of decision. We implement the simplest faithful
version:

    φ_i = <credit_i>                               (average per-cycle pnl
                                                    credited to state i by the
                                                    posterior at entry)

    phi_norm_i = (φ_i - min_j φ_j) / (max_j φ_j - min_j φ_j + ε)

This preserves the sign and ranking structure while mapping into [0, 1]; the
ranking is then used to scale tournament pressure and mutation sigma per
island (large phi → sharper selection, small phi → wider exploration).

This module is deliberately simple and dependency-free so it stays easy to
reason about in the dissertation's methodology section.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple

import numpy as np


class ShapleyFeedback:
    """Tracks posterior-weighted per-state PnL credit and derives Shapley-style
    fitness pressure scalars per island."""

    def __init__(
        self,
        state_ids: List[str],
        update_interval: int = 30,
        min_samples_per_state: int = 5,
        pressure_min: float = 0.5,
        pressure_max: float = 1.5,
        max_history: int = 500,
    ):
        self.state_ids = list(state_ids)
        self.update_interval = int(update_interval)
        self.min_samples = int(min_samples_per_state)
        self.pressure_min = float(pressure_min)
        self.pressure_max = float(pressure_max)
        self.max_history = int(max_history)

        # Rolling windows of per-state credits (one per state)
        self._credits: Dict[str, Deque[float]] = {
            s: deque(maxlen=self.max_history) for s in self.state_ids
        }
        # Latest Shapley-style values (mean credit per state)
        self.phi: Dict[str, float] = {s: 0.0 for s in self.state_ids}
        # Latest pressure scalars (centered on 1.0)
        self.pressure: Dict[str, float] = {s: 1.0 for s in self.state_ids}
        # Cycles observed since last update
        self._cycles_since_update: int = 0
        # History of phi snapshots for the UI / paper plots
        self.history: List[dict] = []

    # -- observation -------------------------------------------------------

    def record_cycle(self, pnl: float, posteriors: np.ndarray) -> None:
        """Credit ``pnl`` to each state by its posterior weight at entry.

        ``posteriors`` must be a 1-D array of length ``len(state_ids)`` summing
        to ~1. If it doesn't sum to 1 we normalise.
        """
        if posteriors is None:
            return
        p = np.asarray(posteriors, dtype=np.float64).ravel()
        if p.size != len(self.state_ids):
            return
        s = p.sum()
        if s <= 0:
            return
        p = p / s

        for state_id, weight in zip(self.state_ids, p):
            self._credits[state_id].append(float(pnl) * float(weight))

        self._cycles_since_update += 1
        if self._cycles_since_update >= self.update_interval:
            self._recompute()
            self._cycles_since_update = 0

    # -- recompute phi / pressure -----------------------------------------

    def _recompute(self) -> None:
        means: Dict[str, float] = {}
        for s in self.state_ids:
            samples = list(self._credits[s])
            if len(samples) >= self.min_samples:
                means[s] = float(np.mean(samples))
            else:
                means[s] = 0.0
        self.phi = means

        # Map phi values into [pressure_min, pressure_max]
        vals = np.array([means[s] for s in self.state_ids])
        lo, hi = vals.min(), vals.max()
        spread = hi - lo
        if spread < 1e-9:
            for s in self.state_ids:
                self.pressure[s] = 1.0
        else:
            # Normalise to [0, 1] then to [pressure_min, pressure_max]
            norm = (vals - lo) / spread
            scaled = self.pressure_min + norm * (self.pressure_max - self.pressure_min)
            for s, v in zip(self.state_ids, scaled):
                self.pressure[s] = float(v)

        self.history.append({
            'phi': dict(self.phi),
            'pressure': dict(self.pressure),
        })
        if len(self.history) > 200:
            self.history = self.history[-200:]

    # -- public API --------------------------------------------------------

    def get_pressure(self, state_id: str) -> float:
        return float(self.pressure.get(state_id, 1.0))

    def get_stats(self) -> dict:
        return {
            'phi': {s: round(v, 6) for s, v in self.phi.items()},
            'pressure': {s: round(v, 4) for s, v in self.pressure.items()},
            'samples_per_state': {s: len(c) for s, c in self._credits.items()},
            'cycles_since_update': self._cycles_since_update,
            'update_interval': self.update_interval,
            'history_len': len(self.history),
        }

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            'state_ids': self.state_ids,
            'update_interval': self.update_interval,
            'min_samples': self.min_samples,
            'pressure_min': self.pressure_min,
            'pressure_max': self.pressure_max,
            'max_history': self.max_history,
            'credits': {s: list(c) for s, c in self._credits.items()},
            'phi': self.phi,
            'pressure': self.pressure,
            'cycles_since_update': self._cycles_since_update,
            'history': self.history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ShapleyFeedback':
        inst = cls(
            state_ids=data['state_ids'],
            update_interval=data.get('update_interval', 30),
            min_samples_per_state=data.get('min_samples', 5),
            pressure_min=data.get('pressure_min', 0.5),
            pressure_max=data.get('pressure_max', 1.5),
            max_history=data.get('max_history', 500),
        )
        for s, vals in data.get('credits', {}).items():
            if s in inst._credits:
                inst._credits[s].extend(vals)
        inst.phi = dict(data.get('phi', inst.phi))
        inst.pressure = dict(data.get('pressure', inst.pressure))
        inst._cycles_since_update = int(data.get('cycles_since_update', 0))
        inst.history = list(data.get('history', []))
        return inst
