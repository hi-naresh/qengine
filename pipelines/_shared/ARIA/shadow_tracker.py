"""
ShadowTracker — counterfactual session simulator for ARIA.

When the pipeline blocks an entry or aborts a cycle, the shadow tracker
records the decision point and then monitors the market to determine
what *would* have happened.  These "shadow sessions" provide ground-truth
evidence for whether gate/abort decisions were correct.

Two types of shadow sessions:

1. **Gate block shadows** — entry was blocked by CycleGate.
   Tracks price from the block point for ``track_bars`` candles.
   Simulates a basic grid cycle: would TP have been hit? Or bust?

2. **Abort shadows** — cycle was killed by RiskShield.
   Tracks price from the abort point for ``track_bars`` candles.
   Determines if the cycle would have recovered to TP or busted deeper.

Shadow sessions are stored with ``is_shadow: True`` in the Observer
and used by MetaEvaluator to compute true protection value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class _PendingShadow:
    """A shadow session being tracked (waiting for resolution)."""
    shadow_type: str          # 'gate_block' or 'abort'
    entry_price: float        # price at decision point
    direction: str            # 'long' or 'short' (what would have been entered)
    level_at_decision: int    # hedge level when decision was made
    hp_snapshot: dict         # HP that would have been used
    market_state: dict        # MarketState at decision point
    danger_at_decision: float
    gate_confidence: float    # P(profitable) from gate
    bars_tracked: int = 0
    high_price: float = 0.0   # highest price seen since decision
    low_price: float = 0.0    # lowest price seen since decision
    max_adverse: float = 0.0  # max adverse excursion in pips
    max_favorable: float = 0.0  # max favorable excursion in pips
    resolved: bool = False
    outcome: str = ''         # 'would_tp', 'would_bust', 'inconclusive'
    phantom_pnl: float = 0.0


class ShadowTracker:
    """Tracks counterfactual outcomes for blocked/aborted decisions.

    Parameters
    ----------
    config : dict, optional
        - ``track_bars`` (int): bars to monitor after decision. Default 500.
        - ``max_pending`` (int): max concurrent shadows. Default 20.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self._track_bars: int = int(config.get('track_bars', 500))
        self._max_pending: int = int(config.get('max_pending', 20))
        self._pending: List[_PendingShadow] = []
        self._completed: List[dict] = []
        self._max_completed: int = 5000

    # ------------------------------------------------------------------
    # Record decision points
    # ------------------------------------------------------------------

    def on_gate_block(self, strategy, market_state: dict,
                      gate_confidence: float, hp_snapshot: dict) -> None:
        """Record a gate block for shadow tracking."""
        if len(self._pending) >= self._max_pending:
            return  # cap concurrent shadows

        price = float(getattr(strategy, 'price', 0.0))
        # Determine what direction the strategy would have entered
        # (simple heuristic: use the last signal direction or random)
        direction = 'long'  # default; overridden below if we can determine

        shadow = _PendingShadow(
            shadow_type='gate_block',
            entry_price=price,
            direction=direction,
            level_at_decision=0,
            hp_snapshot=dict(hp_snapshot) if hp_snapshot else {},
            market_state={k: v for k, v in market_state.items() if k != 'features'},
            danger_at_decision=market_state.get('danger', 0.5),
            gate_confidence=gate_confidence or 0.5,
            high_price=price,
            low_price=price,
        )
        self._pending.append(shadow)

    def on_abort(self, strategy, market_state: dict,
                 abort_reason: str, hp_snapshot: dict) -> None:
        """Record an abort for shadow tracking."""
        if len(self._pending) >= self._max_pending:
            return

        price = float(getattr(strategy, 'price', 0.0))
        sv = getattr(strategy, 'vars', {})
        level = int(sv.get('level', 0))
        direction = sv.get('session_dir', 'long')

        shadow = _PendingShadow(
            shadow_type='abort',
            entry_price=price,
            direction=direction or 'long',
            level_at_decision=level,
            hp_snapshot=dict(hp_snapshot) if hp_snapshot else {},
            market_state={k: v for k, v in market_state.items() if k != 'features'},
            danger_at_decision=market_state.get('danger', 0.5),
            gate_confidence=0.0,
            high_price=price,
            low_price=price,
        )
        self._pending.append(shadow)

    # ------------------------------------------------------------------
    # Update every candle
    # ------------------------------------------------------------------

    def update(self, strategy) -> List[dict]:
        """Update all pending shadows with current price. Returns newly resolved shadows."""
        price = float(getattr(strategy, 'price', 0.0))
        if price <= 0:
            return []

        hp = getattr(strategy, 'hp', {})
        resolved = []
        still_pending = []

        for shadow in self._pending:
            shadow.bars_tracked += 1
            shadow.high_price = max(shadow.high_price, price)
            shadow.low_price = min(shadow.low_price, price)

            # Compute excursions
            if shadow.direction == 'long':
                shadow.max_favorable = max(shadow.max_favorable,
                                           price - shadow.entry_price)
                shadow.max_adverse = max(shadow.max_adverse,
                                         shadow.entry_price - price)
            else:
                shadow.max_favorable = max(shadow.max_favorable,
                                           shadow.entry_price - price)
                shadow.max_adverse = max(shadow.max_adverse,
                                         price - shadow.entry_price)

            # Check resolution
            tp_distance = self._estimate_tp_distance(shadow, hp)
            bust_distance = self._estimate_bust_distance(shadow, hp)

            if shadow.max_favorable >= tp_distance:
                shadow.resolved = True
                shadow.outcome = 'would_tp'
                shadow.phantom_pnl = tp_distance * 10000  # rough pips
            elif shadow.max_adverse >= bust_distance:
                shadow.resolved = True
                shadow.outcome = 'would_bust'
                shadow.phantom_pnl = -bust_distance * 10000
            elif shadow.bars_tracked >= self._track_bars:
                shadow.resolved = True
                shadow.outcome = 'inconclusive'
                # Use current excursion as phantom PnL
                if shadow.direction == 'long':
                    shadow.phantom_pnl = (price - shadow.entry_price) * 10000
                else:
                    shadow.phantom_pnl = (shadow.entry_price - price) * 10000

            if shadow.resolved:
                record = self._to_record(shadow)
                resolved.append(record)
                self._completed.append(record)
            else:
                still_pending.append(shadow)

        self._pending = still_pending

        # Cap completed
        if len(self._completed) > self._max_completed:
            self._completed = self._completed[-self._max_completed:]

        return resolved

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def completed_shadows(self) -> List[dict]:
        return self._completed

    def get_shadow_stats(self) -> dict:
        """Summary stats for the dashboard."""
        if not self._completed:
            return {
                'total_shadows': 0,
                'gate_block_shadows': 0,
                'abort_shadows': 0,
            }

        gate_shadows = [s for s in self._completed if s['shadow_type'] == 'gate_block']
        abort_shadows = [s for s in self._completed if s['shadow_type'] == 'abort']

        # Gate block analysis: how many blocked entries would have been profitable?
        gate_would_tp = sum(1 for s in gate_shadows if s['outcome'] == 'would_tp')
        gate_would_bust = sum(1 for s in gate_shadows if s['outcome'] == 'would_bust')
        gate_correct = gate_would_bust  # blocking a future bust = correct
        gate_wrong = gate_would_tp      # blocking a future win = wrong

        # Abort analysis: how many aborted cycles would have recovered?
        abort_would_tp = sum(1 for s in abort_shadows if s['outcome'] == 'would_tp')
        abort_would_bust = sum(1 for s in abort_shadows if s['outcome'] == 'would_bust')
        abort_correct = abort_would_bust
        abort_wrong = abort_would_tp

        # Phantom PnL saved
        phantom_saved = sum(abs(s['phantom_pnl']) for s in self._completed
                           if s['outcome'] == 'would_bust')

        return {
            'total_shadows': len(self._completed),
            'pending': len(self._pending),
            'gate_block_shadows': len(gate_shadows),
            'gate_correct_blocks': gate_correct,
            'gate_wrong_blocks': gate_wrong,
            'gate_block_accuracy': (gate_correct / max(len(gate_shadows), 1)),
            'abort_shadows': len(abort_shadows),
            'abort_correct': abort_correct,
            'abort_wrong': abort_wrong,
            'abort_accuracy': (abort_correct / max(len(abort_shadows), 1)),
            'phantom_pnl_saved': round(phantom_saved, 2),
            'outcomes': {
                'would_tp': sum(1 for s in self._completed if s['outcome'] == 'would_tp'),
                'would_bust': sum(1 for s in self._completed if s['outcome'] == 'would_bust'),
                'inconclusive': sum(1 for s in self._completed if s['outcome'] == 'inconclusive'),
            },
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def state_dict(self) -> dict:
        return {
            'completed': self._completed[-500:],
            'track_bars': self._track_bars,
        }

    def load_state_dict(self, d: dict) -> None:
        self._completed = d.get('completed', [])
        self._track_bars = d.get('track_bars', self._track_bars)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _estimate_tp_distance(self, shadow: _PendingShadow, hp: dict) -> float:
        """Estimate TP distance from HP snapshot or strategy HP."""
        # Use shadow's HP snapshot if available, else current strategy HP
        shp = shadow.hp_snapshot if shadow.hp_snapshot else hp
        tp_mode = shp.get('tp_mode', 'fixed_pips')
        tp_value = float(shp.get('tp_value', 20.0))

        if tp_mode == 'fixed_pips':
            return tp_value * 0.0001  # pips to price for FX
        elif tp_mode == 'atr_based':
            # Rough ATR estimate from price volatility
            return shadow.entry_price * 0.002 * tp_value
        elif tp_mode == 'bucket_pct':
            return shadow.entry_price * tp_value / 100.0
        else:
            return tp_value * 0.0001

    def _estimate_bust_distance(self, shadow: _PendingShadow, hp: dict) -> float:
        """Estimate bust distance based on max_levels and hedge spacing."""
        shp = shadow.hp_snapshot if shadow.hp_snapshot else hp
        max_levels = int(shp.get('max_levels', 6))
        hedge_value = float(shp.get('hedge_value', 10.0))
        hedge_mode = shp.get('hedge_mode', 'fixed_pips')

        if hedge_mode == 'fixed_pips':
            # Bust = price moved max_levels * hedge_distance against us
            return (max_levels + 1) * hedge_value * 0.0001
        elif hedge_mode == 'atr_based':
            return (max_levels + 1) * shadow.entry_price * 0.002 * hedge_value
        elif hedge_mode == 'percentage':
            return (max_levels + 1) * shadow.entry_price * hedge_value / 100.0
        else:
            return (max_levels + 1) * hedge_value * 0.0001

    @staticmethod
    def _to_record(shadow: _PendingShadow) -> dict:
        """Convert resolved shadow to a storable dict."""
        return {
            'is_shadow': True,
            'shadow_type': shadow.shadow_type,
            'outcome': shadow.outcome,
            'phantom_pnl': round(shadow.phantom_pnl, 2),
            'entry_price': shadow.entry_price,
            'direction': shadow.direction,
            'level_at_decision': shadow.level_at_decision,
            'bars_tracked': shadow.bars_tracked,
            'max_adverse': round(shadow.max_adverse, 6),
            'max_favorable': round(shadow.max_favorable, 6),
            'danger_at_decision': shadow.danger_at_decision,
            'gate_confidence': round(shadow.gate_confidence, 4),
            'market_state': shadow.market_state,
        }
