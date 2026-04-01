"""
ExamplePipeline — A minimal pipeline template.

This is a starting point for building your own pipeline. A pipeline wraps
a strategy with additional intelligence layers that run at each candle.

Available hooks (all receive the strategy instance):
  Observation:
    on_before(strategy)                          — observe every candle
  Entry control:
    gate_entry(strategy) -> bool                 — allow/block entry
    adjust_size(strategy, qty, side) -> float    — scale position size
  Position management:
    suggest_exit(strategy) -> dict|None          — rich exit control
    should_abort(strategy) -> bool               — simple abort (convenience)
  Order control:
    filter_order(strategy, OrderIntent) -> OrderIntent|None  — modify/cancel orders
  Lifecycle:
    on_open_position(strategy)                   — track entry state
    on_cycle_end(pnl, strategy)                  — learn from outcomes
  Stats:
    get_stats() -> dict                          — dashboard display

See docs/PIPELINE.md for full reference and AI adapter examples.
"""
from qengine.framework.base import Pipeline


class ExamplePipeline(Pipeline):
    """A minimal example pipeline that passes everything through."""

    name = 'ExamplePipeline'

    def __init__(self, config: dict = None):
        self.config = config or {}

    def on_before(self, strategy) -> None:
        pass

    def gate_entry(self, strategy) -> bool:
        return True

    def should_abort(self, strategy) -> bool:
        return False

    def get_stats(self) -> dict:
        return {'status': 'active'}

    @classmethod
    def default_config(cls) -> dict:
        return {}
