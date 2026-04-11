"""
ARIA Observer — Layer 5: pure data collection, no ML.

Enriches every trading cycle's session record with ARIA context (market state,
HP snapshot, risk metrics).  These enriched records become training data for
other ARIA layers (CycleGate, HPEngine, MetaEvaluator).

Lifecycle:
    1. on_cycle_open()  — capture entry snapshot (market state, HP, equity, ...)
    2. record_ruin_prob() — called by RiskShield at each hedge level
    3. on_cycle_end()   — merge entry snapshot + exit state + strategy session
                          record into a single enriched dict and store it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _copy_state(market_state: dict) -> dict:
    """Deep-enough copy of MarketState for storage.

    Copies all top-level keys except ``'features'`` (raw feature matrix),
    which is large and not useful for downstream training.
    """
    return {k: v for k, v in market_state.items() if k != 'features'}


# ---------------------------------------------------------------------------
# Observer
# ---------------------------------------------------------------------------

class Observer:
    """Collects enriched session records for every trading cycle.

    Each record merges the strategy's own session dict (``strategy.vars['sessions'][-1]``)
    with ARIA-specific context captured at entry and exit.  The result is a flat
    dict suitable for tabular analysis or as training rows for CycleGate / HPEngine.

    Parameters
    ----------
    config : dict, optional
        ``max_sessions`` — cap on stored records (default 10 000).
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self._enriched_sessions: List[dict] = []
        self._entry_snapshot: Dict[str, Any] = {}
        self._max_sessions: int = int(config.get('max_sessions', 10_000))

    # ------------------------------------------------------------------
    # Cycle hooks
    # ------------------------------------------------------------------

    def on_cycle_open(
        self,
        strategy,
        market_state: dict,
        gate_confidence: Optional[float] = None,
        aria_score: Optional[float] = None,
        start_bar: Optional[int] = None,
    ) -> None:
        """Capture entry snapshot when a new trading cycle starts.

        Parameters
        ----------
        strategy : Strategy
            The active strategy instance (needs ``.hp`` and ``.balance``).
        market_state : dict
            Current MarketState dict from the ARIA state machine.
        gate_confidence : float or None
            P(profitable) from CycleGate, if active.
        aria_score : float or None
            Composite score from MetaEvaluator, if active.
        start_bar : int or None
            Bar index at which the cycle opened.
        """
        self._entry_snapshot = {
            'market_state_at_entry': _copy_state(market_state),
            'hp_used': dict(getattr(strategy, 'hp', {})),
            'regime_id_at_entry': market_state.get('regime_id', 0),
            'danger_at_entry': market_state.get('danger', 0.5),
            'gate_confidence': gate_confidence,
            'equity_at_entry': getattr(strategy, 'balance', 0.0),
            'aria_score_at_entry': aria_score,
            'ruin_probs': [],
            'start_bar': start_bar,
            'level_timestamps': [],
        }

    def record_ruin_prob(self, prob: float) -> None:
        """Append a ruin-probability observation for the current cycle.

        Called by RiskShield each time a new hedge level opens, so the final
        list traces the ruin trajectory across levels.
        """
        if self._entry_snapshot:
            self._entry_snapshot.setdefault('ruin_probs', []).append(
                round(prob, 6)
            )

    def record_level_timestamp(self, bar_index: int) -> None:
        """Append a bar index when a new hedge level opens.

        Called by the pipeline each time the strategy advances to a new level,
        building a timeline of level escalation within the cycle.
        """
        if self._entry_snapshot:
            self._entry_snapshot.setdefault('level_timestamps', []).append(bar_index)

    def on_cycle_end(
        self,
        strategy,
        market_state: dict,
        conformal_bound: Optional[float] = None,
    ) -> dict:
        """Build and store the enriched record when a cycle ends.

        Merges the strategy's last session record with the entry snapshot
        captured in :meth:`on_cycle_open` and the current exit state.

        Parameters
        ----------
        strategy : Strategy
            The active strategy instance.
        market_state : dict
            MarketState dict at cycle close.
        conformal_bound : float or None
            Conformal prediction bound used by the kill switch, if any.

        Returns
        -------
        dict
            The enriched session record, or ``{}`` if no session data exists.
        """
        sessions = getattr(strategy, 'vars', {}).get('sessions', [])
        if not sessions:
            self._entry_snapshot = {}
            return {}

        session_record = sessions[-1]

        enriched: Dict[str, Any] = {
            **session_record,
            **self._entry_snapshot,
            'market_state_at_exit': _copy_state(market_state),
            'danger_at_exit': market_state.get('danger', 0.5),
            'equity_at_exit': getattr(strategy, 'balance', 0.0),
            'conformal_bound_at_kill': conformal_bound,
        }

        self._enriched_sessions.append(enriched)
        self._entry_snapshot = {}

        # Cap stored sessions to prevent unbounded memory growth
        if len(self._enriched_sessions) > self._max_sessions:
            self._enriched_sessions = self._enriched_sessions[-self._max_sessions:]

        return enriched

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def sessions(self) -> List[dict]:
        """All enriched session records collected so far."""
        return self._enriched_sessions

    def get_training_data(self, min_cycles: int = 20) -> List[dict]:
        """Return sessions suitable for training downstream models.

        Returns an empty list when fewer than *min_cycles* have been recorded,
        giving the pipeline time to warm up before any model trains on
        potentially unrepresentative data.
        """
        if len(self._enriched_sessions) < min_cycles:
            return []
        return self._enriched_sessions

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def state_dict(self) -> dict:
        """Serialize observer state for persistence.

        Keeps at most the last 1 000 sessions to limit file size while
        retaining enough history for warm-start training.
        """
        return {
            'enriched_sessions': self._enriched_sessions[-1000:],
        }

    def load_state_dict(self, d: dict) -> None:
        """Restore observer state from a previously saved dict."""
        self._enriched_sessions = d.get('enriched_sessions', [])
