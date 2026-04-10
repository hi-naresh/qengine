from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class OrderIntent:
    """
    Lightweight representation of an order before it reaches the broker.
    Pipelines see intent, not execution details.
    """
    qty: float
    price: float
    side: str       # 'buy' or 'sell'
    type: str       # 'market', 'limit', 'stop'
    is_entry: bool  # True for entry orders, False for SL/TP
    symbol: str
    exchange: str


class Pipeline(ABC):
    """
    Base class for all pipelines.

    A pipeline wraps any Strategy with intelligence layers — entry gating,
    position sizing, exit management, order filtering, and outcome learning —
    without modifying the strategy code.

    Hook lifecycle (per candle):
        on_before(strategy)                    → observe market state
        gate_entry(strategy) → bool            → allow/block entry
        adjust_size(strategy, qty, side) → qty → scale position size
        filter_order(strategy, intent) → intent → modify/cancel orders
        suggest_exit(strategy) → action|None   → graduated exit control
        on_open_position(strategy)             → track entry state
        on_cycle_end(pnl, strategy)            → learn from outcomes

    Composition rules when stacked via PipelineStack:
        on_before        → all run in order
        gate_entry       → AND — all must allow (any veto blocks)
        adjust_size      → multiplicative chain (each scales previous output)
        filter_order     → sequential chain (any None cancels)
        suggest_exit     → most aggressive action wins
        on_open_position → all run in order
        on_cycle_end     → all run in order
    """

    name: str = ''

    # ── Observation ──

    def on_before(self, strategy) -> None:
        """Called every candle, after strategy.before(). Update internal state."""
        pass

    # ── Entry Control ──

    def gate_entry(self, strategy) -> bool:
        """Allow (True) or block (False) the entry."""
        return True

    def adjust_size(self, strategy, qty: float, side: str) -> float:
        """Scale position size. Called after gate allows, before orders are submitted.

        Args:
            strategy: the strategy instance
            qty: total proposed quantity (sum of all entry points)
            side: 'long' or 'short'

        Returns:
            Adjusted quantity. Return 0 to cancel the entry entirely.
        """
        return qty

    # ── Position Management ──

    def suggest_exit(self, strategy) -> Optional[dict]:
        """Suggest an exit action, or None to do nothing.

        Called every candle while a position is open.

        Supported actions:
            {'action': 'close_all'}                   — close entire position
            {'action': 'partial_close', 'pct': 0.5}   — close % of position
            {'action': 'tighten_sl', 'price': 1.234}   — move stop loss
            {'action': 'set_tp', 'price': 1.250}       — set/move take profit

        Default implementation delegates to should_abort() for simple abort logic.
        Override this OR should_abort, not both.
        """
        if self.should_abort(strategy):
            return {'action': 'close_all'}
        return None

    def should_abort(self, strategy) -> bool:
        """Simple abort hook — return True to force-close the position.

        This is a convenience method. The default suggest_exit() delegates to it.
        For richer exit control (partial close, SL/TP adjustment), override
        suggest_exit() instead.
        """
        return False

    # ── Order Control ──

    def filter_order(self, strategy, order_intent: OrderIntent) -> Optional[OrderIntent]:
        """Inspect/modify an order before it reaches the broker.

        Args:
            strategy: the strategy instance
            order_intent: lightweight order description

        Returns:
            The (possibly modified) OrderIntent, or None to cancel the order.
        """
        return order_intent

    # ── Lifecycle Events ──

    def on_open_position(self, strategy) -> None:
        """Called when a position opens. Use for tracking entry state."""
        pass

    def on_cycle_end(self, pnl: float, strategy) -> None:
        """Called when a position closes. Use for learning/reward updates."""
        pass

    # ── Stats & Persistence ──

    @abstractmethod
    def get_stats(self) -> dict:
        """Return pipeline-specific stats for the dashboard."""

    def save_state(self, path: str) -> None:
        """Persist learned state to disk (Q-tables, model weights, etc.)."""
        pass

    def load_state(self, path: str) -> None:
        """Restore learned state from disk."""
        pass

    @classmethod
    def default_config(cls) -> dict:
        """Default configuration for this pipeline (shown in frontend)."""
        return {}

    @classmethod
    def architecture(cls) -> dict:
        """Return pipeline architecture metadata for the frontend.

        Override in subclasses to provide rich layer descriptions.
        Returns dict with keys: layers, composition_rules, state_space, features, etc.
        """
        return {}

    def ui_metadata(self) -> dict:
        """Return UI rendering hints for the Pipeline Intelligence tab.

        The frontend uses this to dynamically render the correct widgets
        for any pipeline — no hardcoded assumptions about layers.

        Structure:
            badges: [{label, color}] — header badges
            metric_cards: [{label, key, format, color?, threshold?, sub?}]
            sections: [{type, title, key?, ...}] — ordered list of UI widgets

        Section types:
            scatter      — X vs Y scatter chart (needs x_key, y_key, color_key, size_key)
            line_chart   — time-series line(s) with optional bands (needs series[])
            bar_breakdown — horizontal win/loss bars (needs key to dict of {count, wins, pnl})
            bucket_table — table with distribution bars (needs key to dict of buckets)
            kv_pairs     — key-value detail rows (needs key or items[])
            audit_table  — sortable/filterable log (needs columns[], data_key)
            exit_reasons — outcome breakdown by exit reason (needs key)
        """
        return {'badges': [], 'metric_cards': [], 'sections': []}


class PipelineStack:
    """
    Manages one or more Pipeline instances on a single strategy.

    Composition rules:
        gate_entry    → AND (all must allow)
        adjust_size   → multiplicative chain
        suggest_exit  → most aggressive action wins
        filter_order  → sequential chain, any None cancels
        others        → all run in order
    """

    def __init__(self, pipelines: list):
        self.pipelines: list[Pipeline] = pipelines
        self._cycle_hp_log: list = []       # [{cycle, hp}, ...] — HP snapshot per session
        self._last_recorded_session = None  # double-fire guard

    def on_before(self, strategy) -> None:
        for p in self.pipelines:
            p.on_before(strategy)

    def gate_entry(self, strategy) -> bool:
        return all(p.gate_entry(strategy) for p in self.pipelines)

    def adjust_size(self, strategy, qty: float, side: str) -> float:
        for p in self.pipelines:
            qty = p.adjust_size(strategy, qty, side)
            if qty <= 0:
                return 0.0
        return qty

    def suggest_exit(self, strategy) -> Optional[dict]:
        suggestions = []
        for p in self.pipelines:
            s = p.suggest_exit(strategy)
            if s is not None:
                suggestions.append(s)
        if not suggestions:
            return None
        # close_all wins immediately
        if any(s['action'] == 'close_all' for s in suggestions):
            return {'action': 'close_all'}
        # largest partial_close wins
        partials = [s for s in suggestions if s['action'] == 'partial_close']
        if partials:
            return max(partials, key=lambda s: s.get('pct', 0))
        # tightest SL wins (for long: highest price; for short: lowest price)
        sl_tightens = [s for s in suggestions if s['action'] == 'tighten_sl']
        if sl_tightens:
            # Can't determine long/short here without strategy, take first
            # The caller (Strategy._update_position) knows the direction
            return sl_tightens[0]
        # closest TP wins
        tp_sets = [s for s in suggestions if s['action'] == 'set_tp']
        if tp_sets:
            return tp_sets[0]
        # Unknown action — pass through first suggestion
        return suggestions[0]

    def should_abort(self, strategy) -> bool:
        """Convenience: delegates to suggest_exit and checks for close_all."""
        suggestion = self.suggest_exit(strategy)
        return suggestion is not None and suggestion.get('action') == 'close_all'

    def filter_order(self, strategy, order_intent: OrderIntent) -> Optional[OrderIntent]:
        for p in self.pipelines:
            order_intent = p.filter_order(strategy, order_intent)
            if order_intent is None:
                return None
        return order_intent

    def on_cycle_end(self, pnl: float, strategy) -> None:
        # Snapshot strategy HP per session (works for ANY pipeline)
        sn = getattr(strategy, 'vars', {}).get('session_number') if strategy else None
        if sn is not None and sn != self._last_recorded_session:
            self._last_recorded_session = sn
            hp = getattr(strategy, 'hp', None)
            if hp:
                snap = {k: (round(v, 4) if isinstance(v, float) else v)
                        for k, v in hp.items()
                        if isinstance(v, (int, float, str, bool))}
                self._cycle_hp_log.append({'cycle': sn, 'hp': snap})

        for p in self.pipelines:
            p.on_cycle_end(pnl, strategy)

    def on_open_position(self, strategy) -> None:
        for p in self.pipelines:
            p.on_open_position(strategy)

    def get_stats(self) -> dict:
        return {p.name: p.get_stats() for p in self.pipelines}

    def save_state(self, base_path: str) -> None:
        import os
        for p in self.pipelines:
            p_path = os.path.join(base_path, p.name)
            os.makedirs(p_path, exist_ok=True)
            p.save_state(p_path)

    def load_state(self, base_path: str) -> None:
        import os
        for p in self.pipelines:
            p_path = os.path.join(base_path, p.name)
            if os.path.isdir(p_path):
                p.load_state(p_path)
