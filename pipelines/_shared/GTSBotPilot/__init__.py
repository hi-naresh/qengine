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
from qengine.framework.stats import PipelineStats

from .config import merge_config, DEFAULT_CONFIG
from .trend_filter import TrendFilter, TREND_LONG, TREND_SHORT, TREND_NULL
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

        # Stats — per-cycle outcome tracking for Pipeline Intelligence UI
        self._stats = PipelineStats(config_snapshot=self.cfg)

        # Runtime
        self._candle_count: int = 0
        self._last_recorded_session: Optional[int] = None
        self._trend_at_entry: str = TREND_NULL
        self._cycle_start_index: int = 0

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

        # Record trend strength as danger-like score for charting
        # Map: null=0.5 (neutral), long/short confirmed=low danger, choppy=high
        ts = candles[-1, 0] if len(candles) > 0 else 0
        if self.trend_filter.current_trend == TREND_NULL:
            danger = 0.7  # choppy = risky
        else:
            # Stronger trend = lower danger; scale by delta threshold
            d1_abs = abs(self.trend_filter.d1)
            delta = self.trend_filter.delta
            strength = min(d1_abs / (delta * 5), 1.0) if delta > 0 else 0.5
            danger = max(0.05, 0.5 - strength * 0.45)
        self._stats.record_danger(ts, danger)

    # ── Entry Control Phase ───────────────────────────────────────

    def gate_entry(self, strategy) -> bool:
        """Block entries that fail trend or grid checks. AND logic."""
        # During warmup, allow all
        if self._candle_count < self.cfg['warmup']:
            return True

        candles = getattr(strategy, 'candles', None)
        ts = candles[-1, 0] if candles is not None and len(candles) > 0 else 0
        danger = self._stats.danger_scores[-1][1] if self._stats.danger_scores else 0.5

        # Layer 1: trend must be confirmed and match direction
        if not self.trend_filter.should_allow_entry(strategy):
            self._stats.record_gate(ts, danger, allowed=False, threshold=0.5)
            return False

        # Layer 2: grid spacing must be satisfied
        if not self.grid_manager.should_allow_entry(strategy):
            self._stats.record_gate(ts, danger, allowed=False, threshold=0.5)
            return False

        self._stats.record_gate(ts, danger, allowed=True, threshold=0.5)
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

        result = self.basket_manager.should_close_basket()
        if result is not None:
            candles = getattr(strategy, 'candles', None)
            ts = candles[-1, 0] if candles is not None and len(candles) > 0 else 0
            self._stats.record_exit_suggestion(ts, result['action'], {
                'basket_pnl': self.basket_manager._basket_pnl,
                'target': self.basket_manager._target_profit,
            })
        return result

    # ── Lifecycle Events ──────────────────────────────────────────

    def on_open_position(self, strategy) -> None:
        """Track new position in grid manager. Snapshot entry state for cycle tracking."""
        self.grid_manager.on_open_position(strategy)

        # Snapshot for cycle outcome
        self._trend_at_entry = self.trend_filter.current_trend
        self._cycle_start_index = self._candle_count
        danger = self._stats.danger_scores[-1][1] if self._stats.danger_scores else 0.5
        candles = getattr(strategy, 'candles', None)
        ts = candles[-1, 0] if candles is not None and len(candles) > 0 else 0
        self._stats.start_cycle(ts, danger)

    def on_cycle_end(self, pnl: float, strategy) -> None:
        """Record cycle outcome and clean up. Deduplicate via session_number."""
        sn = getattr(strategy, 'vars', {}).get('session_number')
        if sn is not None and sn == self._last_recorded_session:
            return
        self._last_recorded_session = sn

        # Determine exit reason
        if self.basket_manager._baskets_closed > 0 and self.basket_manager._basket_pnl >= self.basket_manager._target_profit:
            exit_reason = 'basket_tp'
        elif self.basket_manager._emergency_closes > 0:
            exit_reason = 'emergency_dd'
        else:
            exit_reason = 'strategy_exit'

        # Record cycle outcome with full metadata
        level = getattr(strategy, 'vars', {}).get('level', 0)
        duration = self._candle_count - self._cycle_start_index
        danger_now = self._stats.danger_scores[-1][1] if self._stats.danger_scores else None

        self._stats.end_cycle(
            pnl=pnl,
            exit_reason=exit_reason,
            level=level,
            danger_at_exit=danger_now,
            duration_bars=duration,
            session_number=sn,
            hp_snapshot={
                'trend_at_entry': self._trend_at_entry,
                'trend_at_exit': self.trend_filter.current_trend,
                'grid_open_at_exit': len(self.grid_manager._tickets),
                'basket_pnl': round(self.basket_manager._basket_pnl, 4),
                'atr': round(self.grid_manager._current_atr, 6),
            },
        )

        self.grid_manager.on_cycle_end()
        self.basket_manager.on_cycle_end()

    # ── Stats & Metadata ─────────────────────────────────────────

    def get_stats(self) -> dict:
        # Merge PipelineStats analytics (cycle_outcomes, gate, danger, etc.)
        stats = self._stats.to_dict()

        # Add layer-specific stats
        stats['candle_count'] = self._candle_count
        stats['trend_filter'] = self.trend_filter.stats
        stats['grid_manager'] = self.grid_manager.stats
        stats['basket_manager'] = self.basket_manager.stats
        stats['_ui'] = self.ui_metadata()
        return stats

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
                {'label': 'Cycles', 'key': 'cycles_completed', 'format': 'integer'},
                {'label': 'Win Rate', 'key': 'cycles.win_rate', 'format': 'percent'},
                {'label': 'Block Rate', 'key': 'block_rate', 'format': 'percent'},
                {'label': 'Basket P&L', 'key': 'basket_manager.basket_pnl', 'format': 'currency'},
                {'label': 'Max DD', 'key': 'basket_manager.max_drawdown_seen', 'format': 'percent'},
                {'label': 'Baskets Closed', 'key': 'basket_manager.baskets_closed', 'format': 'integer'},
            ],
            'sections': [
                {
                    'type': 'scatter',
                    'title': 'Cycle Outcomes — Danger vs P&L',
                    'data_key': 'cycle_outcomes',
                    'x_field': 'danger_at_entry',
                    'y_field': 'pnl',
                    'color_field': 'exit_reason',
                    'size_field': 'level',
                },
                {
                    'type': 'line_chart',
                    'title': 'Trend Danger Score',
                    'series': [
                        {'data_key': 'danger_scores', 'label': 'Danger', 'color': '#ef4444'},
                    ],
                },
                {
                    'type': 'exit_reasons',
                    'title': 'Exit Reason Breakdown',
                    'data_key': 'cycles.pnl_by_exit',
                },
                {
                    'type': 'bucket_table',
                    'title': 'Danger Buckets — Win Rate by Risk Level',
                    'data_key': 'risk_intel.danger_buckets',
                },
                {
                    'type': 'audit_table',
                    'title': 'Gate Decisions (last 200)',
                    'data_key': 'gate_decisions',
                    'columns': ['ts', 'danger', 'threshold', 'allowed', 'outcome_pnl'],
                },
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
                {
                    'type': 'kv_pairs',
                    'title': 'Protection Value',
                    'data_key': 'protection',
                },
            ],
        }
