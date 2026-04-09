"""
MetaEvaluator — Layer 6 of the ARIA pipeline.

Rolling-window composite score (ARIA score) that measures whether the
pipeline is improving.  The score drives a reward signal for CycleGate
and HPEngine, and triggers exploration boosts when performance degrades.

ARIA score formula (over a rolling window of N cycles):

    score = survival_efficiency * 0.4
          - bust_penalty * 0.3
          + cvar_95_normalised * 0.3

where:
  - survival_efficiency = shallow_wins / total_cycles
    (shallow_win = tp_hit with levels <= 2)
  - bust_penalty = confident_busts / total_cycles
    (confident_bust = bust where gate_confidence > 0.5)
  - cvar_95_normalised = percentile(pnls, 5) / initial_capital

The score is a formula, not a trained model.  It is computed after each
cycle and used to:
  1. Provide a composite reward signal (instead of raw PnL)
  2. Detect performance degradation → boost L3 exploration
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np


_BUST_REASONS = frozenset({
    'abort', 'max_level_bust', 'margin_call', 'sl_hit',
    'max_level_sl', 'terminate',
})


class MetaEvaluator:
    """Rolling-window ARIA score with degradation detection.

    Parameters
    ----------
    config : dict, optional
        - ``window`` (int): rolling window size. Default 100.
        - ``degradation_sigma`` (float): number of std deviations below
          rolling mean that triggers an exploration boost. Default 1.0.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self._window: int = int(config.get('window', 100))
        self._degradation_sigma: float = float(config.get('degradation_sigma', 1.0))

        self._scores: List[float] = []
        self._current_score: float = 0.0
        self._initial_capital: float = 0.0
        self._degradation_triggered: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, enriched_sessions: list,
                 initial_capital: float = 10_000.0) -> float:
        """Compute the ARIA score over the most recent window of sessions.

        Parameters
        ----------
        enriched_sessions : list of dict
            Enriched session records from the Observer.
        initial_capital : float
            Starting capital for CVaR normalisation.

        Returns
        -------
        float — the ARIA score (higher = better, can be negative).
        """
        self._initial_capital = initial_capital
        window = enriched_sessions[-self._window:]
        if not window:
            self._current_score = 0.0
            return 0.0

        n = len(window)
        pnls = [s.get('pnl', 0.0) for s in window]

        # 1. Survival efficiency: shallow wins / total
        shallow_wins = sum(
            1 for s in window
            if s.get('reason') == 'tp_hit' and s.get('levels', 99) <= 2
        )
        survival_efficiency = shallow_wins / n

        # 2. Bust penalty: confident busts / total
        confident_busts = sum(
            1 for s in window
            if s.get('reason') in _BUST_REASONS
            and (s.get('gate_confidence') or 0) > 0.5
        )
        bust_penalty = confident_busts / n

        # 3. CVaR 95 normalised
        if len(pnls) >= 10:
            cvar_95 = float(np.percentile(pnls, 5))
        else:
            cvar_95 = min(pnls) if pnls else 0.0
        capital = max(initial_capital, 1.0)
        cvar_normalised = cvar_95 / capital

        score = (
            survival_efficiency * 0.4
            - bust_penalty * 0.3
            + cvar_normalised * 0.3
        )

        self._current_score = round(score, 6)
        self._scores.append(self._current_score)

        # Keep scores bounded
        if len(self._scores) > 10_000:
            self._scores = self._scores[-10_000:]

        # Check for degradation
        self._degradation_triggered = self._check_degradation()

        return self._current_score

    def should_boost_exploration(self) -> bool:
        """True if ARIA score has dropped significantly, suggesting
        the pipeline should explore more aggressively.

        Resets after being read (one-shot trigger).
        """
        if self._degradation_triggered:
            self._degradation_triggered = False
            return True
        return False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_score(self) -> float:
        """Most recently computed ARIA score."""
        return self._current_score

    @property
    def score_history(self) -> list:
        """Full history of ARIA scores."""
        return self._scores

    @property
    def rolling_mean(self) -> float:
        """Rolling mean of recent scores."""
        if len(self._scores) < 10:
            return self._current_score
        recent = self._scores[-self._window:]
        return float(np.mean(recent))

    @property
    def rolling_std(self) -> float:
        """Rolling std of recent scores."""
        if len(self._scores) < 10:
            return 0.0
        recent = self._scores[-self._window:]
        return float(np.std(recent))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_degradation(self) -> bool:
        """Detect if current score is significantly below rolling average."""
        if len(self._scores) < 20:
            return False

        recent = self._scores[-self._window:]
        mean = float(np.mean(recent))
        std = float(np.std(recent))

        if std < 1e-8:
            return False

        return self._current_score < mean - self._degradation_sigma * std

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def state_dict(self) -> dict:
        return {
            'window': self._window,
            'degradation_sigma': self._degradation_sigma,
            'scores': self._scores[-1000:],
            'current_score': self._current_score,
            'initial_capital': self._initial_capital,
        }

    def load_state_dict(self, d: dict) -> None:
        self._window = d.get('window', self._window)
        self._degradation_sigma = d.get('degradation_sigma', self._degradation_sigma)
        self._scores = d.get('scores', [])
        self._current_score = d.get('current_score', 0.0)
        self._initial_capital = d.get('initial_capital', 0.0)
