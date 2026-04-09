"""
GTSBotPilot — Grid Trading System Bot Pipeline.

Based on: Rundo et al., "Grid Trading System Robot (GTSbot):
A Novel Mathematical Algorithm for Trading FX Market"
(Appl. Sci. 2019, 9, 1796)

3-layer pipeline overlay for grid/martingale strategies:
  Layer 1: TrendFilter  — EMA-smoothed derivative trend classification
  Layer 2: GridManager  — Grid spacing enforcement (x/y thresholds, max ops)
  Layer 3: BasketManager — Basket equity P&L monitoring with close-all target
"""
import os
from typing import Optional

from qengine.framework.base import Pipeline, OrderIntent

from .config import merge_config, DEFAULT_CONFIG
from .trend_filter import TrendFilter
from .grid_manager import GridManager
from .basket_manager import BasketManager

_DIR = os.path.dirname(os.path.abspath(__file__))
_MODELS_DIR = os.path.join(_DIR, 'models')

# Max candles to slice for indicator computation (O(1) cost)
_MAX_LOOKBACK = 300


class GTSBotPilot(Pipeline):
    name = 'GTSBotPilot'

    def __init__(self, config: dict = None):
        self.cfg = merge_config(config or {})

        # Layers
        self.trend_filter = TrendFilter(self.cfg['trend_filter'])
        self.grid_manager = GridManager(self.cfg['grid_manager'])
        self.basket_manager = BasketManager(self.cfg['basket_manager'])

        # Runtime
        self._candle_count: int = 0
        self._last_recorded_session: Optional[int] = None

    # ── Observation Phase ─────────────────────────────────────────

    def on_before(self, strategy) -> None:
        """Called every candle. Update all 3 layers."""
        self._candle_count += 1

        candles = getattr(strategy, 'candles', None)
        if candles is None or len(candles) < self.cfg['warmup']:
            return

        # Slice tail for O(1) indicator cost
        tail = candles[-_MAX_LOOKBACK:] if len(candles) > _MAX_LOOKBACK else candles

        # Layer 1: trend classification
        self.trend_filter.update(tail)

        # Layer 2: grid state update
        self.grid_manager.update(tail, strategy)

        # Layer 3: basket P&L update
        self.basket_manager.update(tail, strategy)

    # ── Entry Control Phase ───────────────────────────────────────

    def gate_entry(self, strategy) -> bool:
        """Block entries that fail trend or grid checks. AND logic."""
        # During warmup, allow all
        if self._candle_count < self.cfg['warmup']:
            return True

        # Layer 1: trend must be confirmed and match direction
        if not self.trend_filter.should_allow_entry(strategy):
            return False

        # Layer 2: grid spacing must be satisfied
        if not self.grid_manager.should_allow_entry(strategy):
            return False

        return True

    # ── Order Control Phase ───────────────────────────────────────

    def filter_order(self, strategy, order_intent: OrderIntent) -> Optional[OrderIntent]:
        """Final grid check on individual orders."""
        if not self.grid_manager.enabled:
            return order_intent

        # Only filter entry orders
        if not order_intent.is_entry:
            return order_intent

        # Check max operations on the order level
        if len(self.grid_manager._tickets) >= self.grid_manager.max_operations:
            return None  # cancel order

        return order_intent

    # ── Exit Control Phase ────────────────────────────────────────

    def suggest_exit(self, strategy) -> Optional[dict]:
        """Close all when basket profit target reached."""
        if self._candle_count < self.cfg['warmup']:
            return None

        return self.basket_manager.should_close_basket()

    # ── Lifecycle Events ──────────────────────────────────────────

    def on_open_position(self, strategy) -> None:
        """Track new position in grid manager."""
        self.grid_manager.on_open_position(strategy)

    def on_cycle_end(self, pnl: float, strategy) -> None:
        """Clean up on cycle close. Deduplicate via session_number."""
        sn = getattr(strategy, 'vars', {}).get('session_number')
        if sn is not None and sn == self._last_recorded_session:
            return
        self._last_recorded_session = sn

        self.grid_manager.on_cycle_end()
        self.basket_manager.on_cycle_end()

    # ── Stats & Metadata ─────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            'candle_count': self._candle_count,
            'trend_filter': self.trend_filter.stats,
            'grid_manager': self.grid_manager.stats,
            'basket_manager': self.basket_manager.stats,
            '_ui': self.ui_metadata(),
        }

    @classmethod
    def default_config(cls) -> dict:
        return DEFAULT_CONFIG

    @classmethod
    def architecture(cls) -> dict:
        return {
            'summary': 'GTSBot grid trading pipeline with trend filtering, grid spacing enforcement, and basket equity management.',
            'paper': 'Rundo et al., Appl. Sci. 2019, 9, 1796',
            'designed_for': ['Grid strategies', 'Martingale strategies', 'Surefire hedge'],
            'requires_training': False,
            'training_status': 'ready',
            'layers': [
                {
                    'name': 'TrendFilter',
                    'order': 1,
                    'type': 'entry_control',
                    'hook': 'on_before() + gate_entry()',
                    'description': 'EMA-smoothed derivative trend classification (replaces paper SCG NN + TCB).',
                },
                {
                    'name': 'GridManager',
                    'order': 2,
                    'type': 'entry_control',
                    'hook': 'on_before() + gate_entry() + filter_order()',
                    'description': 'Grid spacing enforcement: x-threshold (time), y-threshold (price), max ops.',
                },
                {
                    'name': 'BasketManager',
                    'order': 3,
                    'type': 'exit_control',
                    'hook': 'on_before() + suggest_exit()',
                    'description': 'Basket equity monitoring — closes all when profit target reached.',
                },
            ],
        }

    def ui_metadata(self) -> dict:
        return {
            'badges': [
                {'label': 'GTSBot', 'color': 'brand'},
                {'label': f"Trend: {self.trend_filter.current_trend}", 'color': 'surface'},
                {'label': f"Grid: {self.grid_manager.stats['total_open']}/{self.grid_manager.max_operations}", 'color': 'surface'},
            ],
            'metric_cards': [
                {'label': 'Trend', 'key': 'trend_filter.current_trend', 'format': 'text'},
                {'label': 'Basket P&L', 'key': 'basket_manager.basket_pnl', 'format': 'currency'},
                {'label': 'Target', 'key': 'basket_manager.target_profit', 'format': 'currency'},
                {'label': 'Open Trades', 'key': 'grid_manager.total_open', 'format': 'integer'},
                {'label': 'Max DD', 'key': 'basket_manager.max_drawdown_seen', 'format': 'percent'},
                {'label': 'Baskets Closed', 'key': 'basket_manager.baskets_closed', 'format': 'integer'},
            ],
            'sections': [
                {
                    'type': 'kv_pairs',
                    'title': 'Trend Filter',
                    'data_key': 'trend_filter',
                },
                {
                    'type': 'kv_pairs',
                    'title': 'Grid Manager',
                    'data_key': 'grid_manager',
                },
                {
                    'type': 'kv_pairs',
                    'title': 'Basket Manager',
                    'data_key': 'basket_manager',
                },
            ],
        }
