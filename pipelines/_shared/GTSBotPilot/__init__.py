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

        # A/B comparison: capture strategy's original/default HPs on first call
        self._strategy_original_hp: Optional[dict] = None
        self._strategy_preset: Optional[str] = None

        # Runtime
        self._candle_count: int = 0
        self._last_recorded_session: Optional[int] = None
        self._trend_at_entry: str = TREND_NULL
        self._cycle_start_index: int = 0

    # ── Observation Phase ─────────────────────────────────────────

    def on_before(self, strategy) -> None:
        """Called every candle. Update all 3 layers."""
        self._candle_count += 1

        # Capture strategy's original HPs once (for A/B comparison)
        if self._strategy_original_hp is None:
            self._capture_strategy_hp(strategy)

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
        if self.basket_manager._basket_pnl >= self.basket_manager._target_profit and self.basket_manager._target_profit > 0:
            exit_reason = 'basket_tp'
        elif self.basket_manager._loss_cutoffs > 0 and self.basket_manager._basket_pnl <= -self.basket_manager._max_loss:
            exit_reason = 'loss_cutoff'
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

    # ── A/B Comparison ────────────────────────────────────────────

    def _capture_strategy_hp(self, strategy) -> None:
        """Snapshot strategy's original preset and HPs before pipeline modifies anything."""
        self._strategy_preset = getattr(strategy, 'preset', None) or getattr(strategy, '_preset', 'unknown')

        # Get HPs from strategy.hp dict (the live HP values)
        hp = getattr(strategy, 'hp', None)
        if hp and isinstance(hp, dict):
            self._strategy_original_hp = {k: v for k, v in hp.items()}
        else:
            self._strategy_original_hp = {}

        # Also capture hyperparameters() definition if available
        hp_defs = getattr(strategy, 'hyperparameters', None)
        if callable(hp_defs):
            try:
                defs = hp_defs()
                # Extract just the defaults from the definitions
                for d in defs:
                    name = d.get('name', '')
                    if name and name not in self._strategy_original_hp:
                        self._strategy_original_hp[name] = d.get('default')
            except Exception:
                pass

    def _build_ab_comparison(self) -> dict:
        """Build A/B comparison data: original preset vs pipeline-enhanced run."""
        outcomes = self._stats.cycle_outcomes
        if not outcomes:
            return {}

        wins = [c for c in outcomes if c['pnl'] > 0]
        losses = [c for c in outcomes if c['pnl'] <= 0]
        total_pnl = sum(c['pnl'] for c in outcomes)
        total_wins_pnl = sum(c['pnl'] for c in wins)
        total_loss_pnl = sum(c['pnl'] for c in losses)

        return {
            'strategy_preset': self._strategy_preset,
            'strategy_original_hp': self._strategy_original_hp or {},
            'pipeline_config': self.cfg,
            'pipeline_results': {
                'total_cycles': len(outcomes),
                'wins': len(wins),
                'losses': len(losses),
                'win_rate': round(len(wins) / len(outcomes), 4) if outcomes else 0,
                'total_pnl': round(total_pnl, 4),
                'avg_pnl': round(total_pnl / len(outcomes), 4) if outcomes else 0,
                'avg_win': round(total_wins_pnl / len(wins), 4) if wins else 0,
                'avg_loss': round(total_loss_pnl / len(losses), 4) if losses else 0,
                'profit_factor': round(total_wins_pnl / abs(total_loss_pnl), 4) if total_loss_pnl != 0 else float('inf'),
                'entries_blocked': self._stats.entries_blocked,
                'entries_allowed': self._stats.entries_allowed,
                'block_rate': round(self._stats.entries_blocked / max(self._stats.total_gate_checks, 1), 4),
                'max_drawdown': round(self.basket_manager._max_drawdown_seen, 4),
                'baskets_closed': self.basket_manager._baskets_closed,
                'loss_cutoffs': self.basket_manager._loss_cutoffs,
            },
        }

    # ── Stats & Metadata ─────────────────────────────────────────

    def get_stats(self) -> dict:
        # Merge PipelineStats analytics (cycle_outcomes, gate, danger, etc.)
        stats = self._stats.to_dict()

        # Add layer-specific stats
        stats['candle_count'] = self._candle_count
        stats['trend_filter'] = self.trend_filter.stats
        stats['grid_manager'] = self.grid_manager.stats
        stats['basket_manager'] = self.basket_manager.stats

        # A/B comparison: strategy original vs pipeline-enhanced
        stats['ab_comparison'] = self._build_ab_comparison()

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
                {'icon': 'chart', 'label': 'Cycles', 'key': 'cycles_completed', 'format': 'int'},
                {'icon': 'shield', 'label': 'Win Rate', 'key': 'cycles.win_rate', 'format': 'pct',
                 'threshold': [0.5, 0.7]},
                {'icon': 'block', 'label': 'Block Rate', 'key': 'block_rate', 'format': 'pct',
                 'sub_template': '{entries_blocked} blocked / {entries_allowed} allowed'},
                {'icon': 'danger', 'label': 'Avg Danger', 'key': 'danger.mean', 'format': 'dec3',
                 'threshold_inv': [0.4, 0.6]},
                {'icon': 'filter', 'label': 'Baskets Closed', 'key': 'basket_manager.baskets_closed', 'format': 'int'},
                {'icon': 'layers', 'label': 'Protection', 'key': 'protection.total_protection_value', 'format': 'currency',
                 'prefix': '+', 'color': 'green'},
            ],
            'sections': [
                # A/B comparison: strategy original preset vs pipeline
                {
                    'type': 'kv_pairs',
                    'title': 'A/B Comparison — Strategy Original Preset',
                    'show_if': 'ab_comparison.strategy_preset',
                    'grid': 'half',
                    'items': [
                        {'label': 'Strategy Preset', 'key': 'ab_comparison.strategy_preset', 'format': 'text'},
                        {'label': 'Hedge Distance', 'key': 'ab_comparison.strategy_original_hp.hedge_distance', 'format': 'dec4'},
                        {'label': 'TP Distance', 'key': 'ab_comparison.strategy_original_hp.tp_distance', 'format': 'dec4'},
                        {'label': 'Max Levels', 'key': 'ab_comparison.strategy_original_hp.max_levels', 'format': 'int'},
                        {'label': 'Sizing Curve', 'key': 'ab_comparison.strategy_original_hp.sizing_curve', 'format': 'text'},
                        {'label': 'Entry Signal', 'key': 'ab_comparison.strategy_original_hp.signal_mode', 'format': 'text'},
                    ],
                },
                {
                    'type': 'kv_pairs',
                    'title': 'A/B Comparison — Pipeline Results',
                    'show_if': 'ab_comparison.pipeline_results',
                    'grid': 'half',
                    'items': [
                        {'label': 'Win Rate', 'key': 'ab_comparison.pipeline_results.win_rate', 'format': 'pct',
                         'threshold': [0.5, 0.7]},
                        {'label': 'Total PnL', 'key': 'ab_comparison.pipeline_results.total_pnl', 'format': 'currency'},
                        {'label': 'Profit Factor', 'key': 'ab_comparison.pipeline_results.profit_factor', 'format': 'dec3'},
                        {'label': 'Entries Blocked', 'template': '<red>{ab_comparison.pipeline_results.entries_blocked}</red> / {ab_comparison.pipeline_results.entries_allowed} allowed ({ab_comparison.pipeline_results.block_rate:.1f}%)'},
                        {'label': 'Max Drawdown', 'key': 'ab_comparison.pipeline_results.max_drawdown', 'format': 'pct', 'color': 'red'},
                        {'label': 'Loss Cutoffs', 'key': 'ab_comparison.pipeline_results.loss_cutoffs', 'format': 'int', 'color': 'red'},
                    ],
                },
                # Cycle scatter: danger at entry vs PnL
                {
                    'type': 'scatter',
                    'title': 'Cycle Scatter: Danger at Entry vs PnL',
                    'subtitle': 'Each dot = one cycle. Color = exit reason, size = level reached',
                    'data_key': 'cycle_outcomes',
                    'x_key': 'danger_at_entry', 'x_label': 'Danger at Entry',
                    'y_key': 'pnl', 'y_label': 'PnL',
                    'color_key': 'exit_reason',
                    'size_key': 'level',
                    'color_map': {
                        'basket_tp': {'color': '#4ade80', 'label': 'Basket TP'},
                        'loss_cutoff': {'color': '#fbbf24', 'label': 'Loss Cutoff'},
                        'strategy_exit': {'color': '#818cf8', 'label': 'Strategy Exit'},
                        'emergency_dd': {'color': '#f87171', 'label': 'Emergency DD'},
                        '_default': {'color': '#64748b', 'label': 'Other'},
                    },
                    'ref_lines': [
                        {'axis': 'y', 'value': 0, 'style': 'dashed', 'color': '#333'},
                    ],
                    'summary_stats': [
                        {'label': 'Correlation', 'compute': 'correlation', 'x': 'danger_at_entry', 'y': 'pnl'},
                        {'label': 'High-Danger PnL', 'compute': 'sum_filtered', 'key': 'pnl', 'filter': 'danger_at_entry > 0.7'},
                        {'label': 'Low-Danger PnL', 'compute': 'sum_filtered', 'key': 'pnl', 'filter': 'danger_at_entry <= 0.3'},
                    ],
                },
                # Danger score time-series
                {
                    'type': 'line_chart',
                    'title': 'Trend Danger Score (Choppiness)',
                    'subtitle': 'Higher = choppier market, entries more likely blocked',
                    'data_key': 'danger_scores',
                    'show_if': 'danger_scores',
                    'empty_message': 'No danger data yet — pipeline still warming up.',
                    'series': [
                        {'index': 1, 'label': 'Danger', 'color': '#ef4444', 'width': 1.5, 'axis': 'left'},
                    ],
                    'x_label': 'Time',
                },
                # Per-level performance
                {
                    'type': 'bar_breakdown',
                    'title': 'Per-Level Performance',
                    'data_key': 'level_performance',
                    'empty_message': 'No level data recorded yet.',
                    'label_prefix': 'L',
                    'label_colors': {
                        '0': 'green', '1': 'brand', '2': 'brand',
                        '3': 'amber', '4': 'amber', '5': 'amber',
                    },
                },
                # Trend filter + Grid manager analysis (half-width pair)
                {
                    'type': 'kv_pairs',
                    'title': 'Trend Filter Analysis',
                    'grid': 'half',
                    'items': [
                        {'label': 'Current Trend', 'key': 'trend_filter.current_trend', 'format': 'text'},
                        {'label': '1st Derivative (d1)', 'key': 'trend_filter.d1', 'format': 'dec4'},
                        {'label': '2nd Derivative (d2)', 'key': 'trend_filter.d2', 'format': 'dec4'},
                        {'label': 'Trend Counts', 'template': '<green>{trend_filter.trend_counts.long}</green> long / <red>{trend_filter.trend_counts.short}</red> short / {trend_filter.trend_counts.null} null'},
                        {'label': 'Block Rate', 'key': 'trend_filter.block_rate', 'format': 'pct'},
                    ],
                },
                {
                    'type': 'kv_pairs',
                    'title': 'Grid Manager Analysis',
                    'grid': 'half',
                    'items': [
                        {'label': 'Open Trades', 'template': '{grid_manager.open_long_count} long / {grid_manager.open_short_count} short'},
                        {'label': 'Current ATR', 'key': 'grid_manager.current_atr', 'format': 'dec4'},
                        {'label': 'X-Threshold (candles)', 'key': 'grid_manager.current_x_threshold', 'format': 'int'},
                        {'label': 'Y-Threshold (price)', 'key': 'grid_manager.current_y_threshold', 'format': 'dec4'},
                        {'label': 'Blocked', 'template': '{grid_manager.blocked_reasons.max_ops} max-ops / {grid_manager.blocked_reasons.x_dist} x-dist / {grid_manager.blocked_reasons.y_dist} y-dist'},
                    ],
                },
                # Basket + Protection (half-width pair)
                {
                    'type': 'kv_pairs',
                    'title': 'Basket Manager',
                    'grid': 'half',
                    'items': [
                        {'label': 'Basket P&L', 'key': 'basket_manager.basket_pnl', 'format': 'currency'},
                        {'label': 'Target Profit', 'key': 'basket_manager.target_profit', 'format': 'dec4'},
                        {'label': 'Max Loss Cutoff', 'key': 'basket_manager.max_loss', 'format': 'dec4', 'color': 'red'},
                        {'label': 'Baskets Closed', 'template': '{basket_manager.baskets_closed} TP / <red>{basket_manager.loss_cutoffs}</red> cutoff / <red>{basket_manager.emergency_closes}</red> emerg'},
                        {'label': 'Max DD Seen', 'key': 'basket_manager.max_drawdown_seen', 'format': 'pct', 'color': 'red'},
                    ],
                },
                {
                    'type': 'kv_pairs',
                    'title': 'Protection Value',
                    'grid': 'half',
                    'items': [
                        {'label': 'Est. Saved by Blocks', 'key': 'protection.est_pnl_saved_by_blocks', 'format': 'currency', 'prefix': '+', 'color': 'green'},
                        {'label': 'Saved by Aborts', 'key': 'protection.pnl_saved_by_aborts', 'format': 'currency', 'prefix': '+', 'color': 'green'},
                        {'label': 'Total Protection', 'key': 'protection.total_protection_value', 'format': 'currency', 'prefix': '+', 'color': 'green'},
                        {'label': 'Gate Allow Accuracy', 'key': 'gate.allow_accuracy', 'format': 'pct', 'threshold': [0.5, 0.6]},
                        {'label': 'PnL of Allowed', 'key': 'gate.pnl_of_allowed', 'format': 'currency'},
                    ],
                },
                # Exit reason breakdown
                {
                    'type': 'exit_reasons',
                    'title': 'Exit Reason Breakdown',
                    'data_key': 'cycles.pnl_by_exit',
                    'show_if': 'cycles.pnl_by_exit',
                },
                # Danger buckets
                {
                    'type': 'bucket_table',
                    'title': 'Risk Intelligence: Danger Buckets',
                    'data_key': 'risk_intel.danger_buckets',
                    'show_if': 'risk_intel.danger_buckets',
                    'bucket_colors': {
                        'extreme': 'red', 'high': 'orange', 'medium': 'amber',
                        'low': 'green', 'very_low': 'green-light',
                    },
                },
                # Gate decision audit table
                {
                    'type': 'audit_table',
                    'title': 'Decision Audit Log',
                    'subtitle': 'Gate decisions with outcome linkage',
                    'sources': [
                        {
                            'data_key': 'gate_decisions',
                            'type_label': 'gate',
                            'type_color': 'blue',
                            'map': {
                                'ts': 'ts', 'danger': 'danger', 'threshold': 'threshold',
                                'decision': {'key': 'allowed', 'true': 'ALLOWED', 'false': 'BLOCKED'},
                                'outcome_pnl': 'outcome_pnl',
                            },
                        },
                    ],
                    'columns': [
                        {'key': 'ts', 'label': 'Time', 'sortable': True, 'format': 'datetime'},
                        {'key': 'type', 'label': 'Type', 'format': 'badge'},
                        {'key': 'danger', 'label': 'Danger', 'sortable': True, 'format': 'dec3',
                         'color_thresholds': {'red': 0.7, 'amber': 0.5, 'green': 0}},
                        {'key': 'decision', 'label': 'Decision', 'format': 'badge',
                         'color_map': {'ALLOWED': 'green', 'BLOCKED': 'red'}},
                        {'key': 'outcome_pnl', 'label': 'Outcome PnL', 'sortable': True, 'format': 'currency_signed',
                         'color_thresholds': {'green': 0.01, 'red': -999999}},
                    ],
                    'max_rows': 200,
                },
            ],
        }
