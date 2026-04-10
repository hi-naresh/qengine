"""AgentDecision dataclass and DecisionExecutor."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentDecision:
    """Structured output from the LLM agent."""
    signal: str = 'no_action'        # 'long', 'short', 'hold', 'close_all', 'no_action'
    confidence: float = 0.5          # 0.0 - 1.0
    sizing_pct: float = 0.02         # position size as % of balance
    tp_pips: Optional[float] = None  # take-profit in pips (None = dynamic)
    sl_pips: Optional[float] = None  # stop-loss in pips (None = dynamic)
    hp_overrides: dict = field(default_factory=dict)  # strategy HP changes
    standing_orders: list = field(default_factory=list)  # valid until next consult
    reasoning: str = ''              # free-text explanation
    ttl_bars: int = 240              # bars this decision is valid for

    @classmethod
    def from_dict(cls, d: dict) -> 'AgentDecision':
        """Parse from LLM JSON response, with safe defaults."""
        return cls(
            signal=d.get('signal', 'no_action'),
            confidence=max(0.0, min(1.0, float(d.get('confidence', 0.5)))),
            sizing_pct=max(0.0, min(0.20, float(d.get('sizing_pct', 0.02)))),
            tp_pips=d.get('tp_pips'),
            sl_pips=d.get('sl_pips'),
            hp_overrides=d.get('hp_overrides', {}),
            standing_orders=d.get('standing_orders', []),
            reasoning=d.get('reasoning', ''),
            ttl_bars=int(d.get('ttl_bars', 240)),
        )

    def to_dict(self) -> dict:
        return {
            'signal': self.signal,
            'confidence': self.confidence,
            'sizing_pct': self.sizing_pct,
            'tp_pips': self.tp_pips,
            'sl_pips': self.sl_pips,
            'hp_overrides': self.hp_overrides,
            'standing_orders': self.standing_orders,
            'reasoning': self.reasoning,
            'ttl_bars': self.ttl_bars,
        }


class DecisionExecutor:
    """
    Applies an AgentDecision to the strategy.

    Maintains the current decision and standing orders between consultations.
    """

    def __init__(self, config: dict):
        self._sizing_cfg = config.get('sizing', {})
        self._current_decision: Optional[AgentDecision] = None
        self._decision_bar: int = 0          # bar when decision was made
        self._suggest_close: bool = False     # flag for suggest_exit

        # Stats
        self.decisions_applied: int = 0
        self.hp_changes: int = 0
        self.entries_allowed: int = 0
        self.entries_blocked: int = 0

    @property
    def current_decision(self) -> Optional[AgentDecision]:
        return self._current_decision

    def apply(self, decision: AgentDecision, strategy, current_bar: int) -> None:
        """Apply a new LLM decision to the strategy."""
        self._current_decision = decision
        self._decision_bar = current_bar
        self._suggest_close = False
        self.decisions_applied += 1

        # Apply HP overrides
        if decision.hp_overrides and hasattr(strategy, 'hp'):
            for key, val in decision.hp_overrides.items():
                if key in strategy.hp:
                    strategy.hp[key] = val
                    self.hp_changes += 1

        # If close_all, flag for suggest_exit
        if decision.signal == 'close_all':
            self._suggest_close = True

    def apply_standing(self, strategy, current_bar: int) -> None:
        """Apply standing orders / enforce current decision without new consult."""
        if self._current_decision is None:
            return

        # Check TTL expiry
        bars_since = current_bar - self._decision_bar
        if bars_since > self._current_decision.ttl_bars:
            # Decision expired — reset to hold
            self._current_decision = AgentDecision(signal='hold', reasoning='TTL expired')
            self._decision_bar = current_bar

    def gate_entry(self, strategy) -> bool:
        """Return True if LLM allows entry in this direction."""
        if self._current_decision is None:
            self.entries_blocked += 1
            return False

        decision = self._current_decision
        min_conf = self._sizing_cfg.get('min_confidence', 0.3)

        # Block if confidence too low
        if decision.confidence < min_conf:
            self.entries_blocked += 1
            return False

        # Block if signal is hold/no_action/close_all
        if decision.signal in ('hold', 'no_action', 'close_all'):
            self.entries_blocked += 1
            return False

        # Check direction match
        wants_long = hasattr(strategy, '_wants_long') and strategy._wants_long
        wants_short = hasattr(strategy, '_wants_short') and strategy._wants_short

        if wants_long and decision.signal != 'long':
            self.entries_blocked += 1
            return False
        if wants_short and decision.signal != 'short':
            self.entries_blocked += 1
            return False

        self.entries_allowed += 1
        return True

    def adjust_size(self, strategy, qty: float) -> float:
        """Scale position size by LLM confidence and sizing recommendation."""
        if self._current_decision is None:
            return qty

        decision = self._current_decision
        max_pct = self._sizing_cfg.get('max_sizing_pct', 0.05)

        # Cap sizing
        sizing = min(decision.sizing_pct, max_pct)

        # Confidence scaling
        if self._sizing_cfg.get('confidence_scaling', True):
            sizing *= decision.confidence

        # Convert % of balance to lot size
        if hasattr(strategy, 'balance') and strategy.balance > 0:
            target_risk = strategy.balance * sizing
            # If strategy has lot_size_for_risk, use its sizing
            if hasattr(strategy, 'lot_size_for_risk') and decision.sl_pips:
                try:
                    return strategy.lot_size_for_risk(sizing * 100, decision.sl_pips)
                except Exception:
                    pass

        return qty  # Fallback: don't modify

    def suggest_exit(self, strategy) -> Optional[dict]:
        """Suggest exit if LLM decided close_all."""
        if self._suggest_close:
            self._suggest_close = False
            return {'action': 'close_all'}

        # Check standing TP/SL
        if self._current_decision and strategy.is_open:
            decision = self._current_decision
            price = strategy.price

            if decision.tp_pips and hasattr(strategy, 'pips_to_price'):
                tp_dist = strategy.pips_to_price(decision.tp_pips)
                if strategy.is_long and price >= strategy.position.entry_price + tp_dist:
                    return {'action': 'close_all'}
                if strategy.is_short and price <= strategy.position.entry_price - tp_dist:
                    return {'action': 'close_all'}

            if decision.sl_pips and hasattr(strategy, 'pips_to_price'):
                sl_dist = strategy.pips_to_price(decision.sl_pips)
                if strategy.is_long and price <= strategy.position.entry_price - sl_dist:
                    return {'action': 'close_all'}
                if strategy.is_short and price >= strategy.position.entry_price + sl_dist:
                    return {'action': 'close_all'}

        return None

    def on_cycle_end(self) -> None:
        """Reset close flag on cycle end."""
        self._suggest_close = False
