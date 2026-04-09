"""
ARIA Pipeline — Adaptive Regime-Intelligent Architecture

A strategy-agnostic intelligence layer that governs any strategy via the
Pipeline ABC.  Six internal layers:

  L1  MarketBrain   — feature extraction + online regime clustering
  L2  CycleGate     — online logistic regression entry gate
  L3  HPEngine      — contextual bandit HP selection
  L4  RiskShield    — conformal kill + liquidity gate + margin survival
  L5  Observer      — enriched session recording
  L6  MetaEvaluator — ARIA score + reward loop

All 6 layers active.  L2 and L3 have warmup periods — they learn
online from cycle outcomes.  L6 drives exploration boosts on degradation.
"""

import os
import json
from typing import Optional

from qengine.framework.base import Pipeline, OrderIntent
from qengine.framework.stats import PipelineStats

from .market_brain import MarketBrain
from .cycle_gate import CycleGate
from .hp_engine import HPEngine
from .risk_shield import RiskShield
from .observer import Observer
from .meta_evaluator import MetaEvaluator
from .config import default_config

_MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')


class ARIAPipeline(Pipeline):
    """
    ARIA — wraps any strategy with 6 intelligence layers.

    All 6 layers active: MarketBrain (L1), CycleGate (L2), HPEngine (L3),
    RiskShield (L4), Observer (L5), MetaEvaluator (L6).

    L2 and L3 have configurable warmup periods — they learn online from
    cycle outcomes.  During warmup, gate allows everything and HPs stay
    at strategy defaults.  L6 detects performance degradation and triggers
    exploration boosts in L3.
    """

    name = 'ARIA'

    def __init__(self, config: dict = None):
        cfg = {**default_config(), **(config or {})}
        self._config = cfg

        # L1 — MarketBrain
        self._brain = MarketBrain({
            'warmup': cfg['brain_warmup'],
            'k_max': cfg['brain_k_max'],
        })

        # L2 — CycleGate
        self._gate = CycleGate({
            'warmup_cycles': cfg['gate_warmup_cycles'],
            'learning_rate': cfg['gate_learning_rate'],
            'k_max': cfg['brain_k_max'],
        })
        self._gate_enabled = cfg.get('gate_enabled', True)

        # L3 — HPEngine
        self._hp_engine = HPEngine({
            'warmup_cycles': cfg['hp_warmup_cycles'],
            'max_arms': cfg['hp_max_arms_per_group'],
            'k_max': cfg['brain_k_max'],
        })
        self._hp_engine_enabled = cfg.get('hp_engine_enabled', True)
        self._hp_registered = False

        # L4 — RiskShield
        self._shield = RiskShield({
            'conformal_alpha': cfg['conformal_alpha'],
            'conformal_safety': cfg['conformal_safety'],
            'fallback_level': cfg['fallback_level'],
            'max_ruin_prob': cfg['max_ruin_prob'],
        })

        # L5 — Observer
        self._observer = Observer({
            'max_sessions': cfg['max_sessions'],
        })

        # L6 — MetaEvaluator
        self._meta = MetaEvaluator({
            'window': cfg['meta_window'],
        })
        self._meta_enabled = cfg.get('meta_enabled', True)

        # Stats tracking (reuses existing PipelineStats)
        self._stats = PipelineStats()
        self._stats.config_snapshot = cfg

        # Internal state
        self._market_state: dict = {}
        self._cycle_active = False
        self._gate_confidence: float = None
        self._hp_selection: dict = {}
        self._aria_score: float = 0.0
        self._candle_count = 0
        self._candle_warmup = cfg.get('brain_warmup', 50)
        self._hp_selected_this_cycle = False
        self._preset_forced = False

    # ── Observation (every candle) ──

    def on_before(self, strategy) -> None:
        """L1: update market state. L3: register HP schema + inject structural HPs."""
        self._candle_count += 1
        self._market_state = self._brain.update(strategy)

        # Force preset to 'custom' on first candle so ARIA controls all HPs.
        # Must happen before strategy's _init_state() applies preset defaults.
        if not self._preset_forced and hasattr(strategy, 'hp'):
            strategy.hp['preset'] = 'custom'
            self._preset_forced = True

        # Lazy HP schema registration (once)
        if self._hp_engine_enabled and not self._hp_registered:
            if hasattr(strategy, 'hyperparameters'):
                self._hp_engine.register_strategy(strategy)
                self._hp_registered = True

        # L3: select HPs ONCE between cycles (not every candle).
        # Only after candle warmup so brain has market context.
        sv = getattr(strategy, 'vars', {})
        cycle_active = sv.get('cycle_active', False)
        if (self._hp_engine_enabled
                and not cycle_active
                and not self._hp_selected_this_cycle
                and self._candle_count > self._candle_warmup):
            regime_id = self._market_state.get('regime_id', 0)
            self._hp_selection = self._hp_engine.select(regime_id)
            if self._hp_selection:
                self._hp_engine.inject_hp(strategy, self._hp_selection)
            self._hp_selected_this_cycle = True

        # Record danger for time-series charting
        ts = strategy.candles[-1][0] if strategy.candles is not None and len(strategy.candles) > 0 else 0
        danger = self._market_state.get('danger', 0.5)
        self._stats.record_danger(ts, danger)

    # ── Entry Control ──

    def gate_entry(self, strategy) -> bool:
        """L2: CycleGate predicts P(profitable) and blocks low-confidence entries."""
        # During candle warmup, always allow — brain still calibrating
        if self._candle_count <= self._candle_warmup:
            return True

        danger = self._market_state.get('danger', 0.5)
        ts = strategy.candles[-1][0] if strategy.candles is not None and len(strategy.candles) > 0 else 0

        if self._gate_enabled:
            allowed, confidence = self._gate.gate(self._market_state, strategy)
            self._gate_confidence = confidence
            threshold = self._gate.threshold
        else:
            allowed = True
            self._gate_confidence = None
            threshold = None

        self._stats.record_gate(ts, danger, allowed=allowed, threshold=threshold)
        return allowed

    # ── Position Management ──

    def suggest_exit(self, strategy) -> Optional[dict]:
        """L4: RiskShield checks conformal kill + liquidity + margin."""
        if not getattr(strategy, 'is_open', False):
            return None

        result = self._shield.check(strategy, self._market_state)
        if result is not None:
            # Record abort decision
            sv = getattr(strategy, 'vars', {})
            level = int(sv.get('level', 0))
            ts = strategy.candles[-1][0] if strategy.candles is not None and len(strategy.candles) > 0 else 0
            self._stats.record_abort(
                timestamp=ts,
                level=level,
                danger=self._market_state.get('danger', 0.5),
                action='abort',
                danger_entry=self._observer._entry_snapshot.get('danger_at_entry'),
            )
            self._stats.record_exit_suggestion(ts, 'close_all', result)

        # Track ruin prob for Observer
        ruin_probs = self._shield.ruin_probs_this_cycle
        if ruin_probs:
            self._observer.record_ruin_prob(ruin_probs[-1])

        return result

    # ── Order Control ──

    def filter_order(self, strategy, order_intent: OrderIntent) -> Optional[OrderIntent]:
        """Pass through — all HPs are injected structurally on strategy.hp."""
        return order_intent

    # ── Lifecycle Events ──

    def on_open_position(self, strategy) -> None:
        """L5: Observer captures entry snapshot with gate confidence."""
        self._cycle_active = True

        # Observer records entry state
        self._observer.on_cycle_open(
            strategy,
            self._market_state,
            gate_confidence=self._gate_confidence,
            aria_score=self._aria_score if self._meta_enabled else None,
        )

        # Stats
        danger = self._market_state.get('danger', 0.5)
        ts = strategy.candles[-1][0] if strategy.candles is not None and len(strategy.candles) > 0 else 0
        self._stats.start_cycle(ts, danger)

    def on_cycle_end(self, pnl: float, strategy) -> None:
        """L5: Observer records enriched outcome. L4: RiskShield updates calibration."""
        if not self._cycle_active:
            return
        self._cycle_active = False
        self._hp_selected_this_cycle = False  # allow fresh HP selection for next cycle

        # Observer builds enriched record
        enriched = self._observer.on_cycle_end(
            strategy,
            self._market_state,
            conformal_bound=None,  # TODO: expose from RiskShield
        )

        # RiskShield updates conformal calibration
        level = enriched.get('levels', 0) if enriched else 0
        self._shield.record_cycle(level, pnl)

        # Stats
        exit_reason = enriched.get('reason', '') if enriched else ''
        danger_at_exit = self._market_state.get('danger', 0.5)
        sv = getattr(strategy, 'vars', {})
        duration = enriched.get('bars', 0) if enriched else 0
        self._stats.end_cycle(
            pnl=pnl,
            exit_reason=exit_reason,
            level=level,
            danger_at_exit=danger_at_exit,
            duration_bars=duration,
        )

        # L2: CycleGate SGD update
        profitable = pnl > 0
        if self._gate_enabled:
            self._gate.update(self._market_state, strategy, profitable)

        # L3: HPEngine bandit posterior update
        if self._hp_engine_enabled:
            self._hp_engine.update(profitable)

        # L6: MetaEvaluator — compute ARIA score and check for degradation
        if self._meta_enabled:
            initial_capital = self._observer.sessions[0].get('equity_at_entry', 10_000) if self._observer.sessions else 10_000
            self._aria_score = self._meta.evaluate(
                self._observer.sessions, initial_capital
            )

            # Exploration boost: if score degraded, reset HP engine bandits
            # toward priors to encourage re-exploration
            if self._meta.should_boost_exploration() and self._hp_engine_enabled:
                self._boost_exploration()

    # ── Internal Helpers ──

    def _boost_exploration(self):
        """Decay HPEngine bandit posteriors toward priors to encourage re-exploration.

        Called when MetaEvaluator detects performance degradation.
        Halves the evidence (alpha, beta) to soften posteriors while
        keeping the learned direction.
        """
        for group_name, regime_map in self._hp_engine._bandits.items():
            for regime_id, bandit in regime_map.items():
                # Decay toward prior: new_a = 1 + (a - 1) * 0.5
                bandit.alpha = 1.0 + (bandit.alpha - 1.0) * 0.5
                bandit.beta = 1.0 + (bandit.beta - 1.0) * 0.5

    # ── Stats & Persistence ──

    def get_stats(self) -> dict:
        """Pipeline stats for the dashboard.

        Merges PipelineStats analytics with ARIA layer-specific stats
        and attaches ``_ui`` metadata for the frontend to render.
        """
        stats = self._stats.to_dict()

        # ── Brain (L1) ──
        stats['brain'] = {
            'regime_id': self._market_state.get('regime_id', 0),
            'regime_confidence': self._market_state.get('regime_confidence', 0.0),
            'danger': self._market_state.get('danger', 0.5),
            'trend_strength': self._market_state.get('trend_strength', 0.0),
            'volatility': self._market_state.get('volatility', 0.0),
            'efficiency': self._market_state.get('efficiency', 0.5),
            'num_regimes': self._brain._cluster.k,
        }

        # ── Gate (L2) — merge into PipelineStats gate section ──
        gate_extra = {
            'n_cycles': self._gate.n_cycles,
            'warmed_up': self._gate.is_warmed_up,
            'threshold': round(self._gate.threshold, 4),
            'enabled': self._gate_enabled,
        }
        stats['gate'] = {**stats.get('gate', {}), **gate_extra}

        # ── HP Engine (L3) ──
        stats['hp_engine'] = {
            'n_cycles': self._hp_engine.n_cycles,
            'warmed_up': self._hp_engine.is_warmed_up,
            'registered': self._hp_registered,
            'enabled': self._hp_engine_enabled,
            'current_selection': self._hp_selection,
            'groups': list(self._hp_engine._groups.keys()) if self._hp_engine._groups else [],
            'arms_per_group': {g: len(a) for g, a in self._hp_engine._group_arms.items()},
        }

        # ── Shield (L4) ──
        stats['shield'] = {
            'conformal_cycles': self._shield.conformal._total_cycles,
            'calibration_levels': len(self._shield.conformal._calibration),
            'conformal_active': self._shield.conformal._total_cycles >= 20,
            'ruin_probs_this_cycle': self._shield.ruin_probs_this_cycle[-5:],
        }

        # ── Observer (L5) ──
        stats['observer'] = {
            'total_enriched_sessions': len(self._observer.sessions),
        }

        # ── Meta (L6) — build ARIA score time-series for charting ──
        score_history = self._meta.score_history
        stats['meta'] = {
            'aria_score': self._aria_score,
            'rolling_mean': round(self._meta.rolling_mean, 6),
            'rolling_std': round(self._meta.rolling_std, 6),
            'score_history_len': len(score_history),
            'enabled': self._meta_enabled,
            # Time-series: [[index, score], ...] for line_chart rendering
            'score_series': [[i, round(s, 4)] for i, s in enumerate(score_history[-500:])],
        }

        # ── UI metadata for frontend rendering ──
        stats['_ui'] = self.ui_metadata()

        return stats

    def generate_report(self) -> dict:
        """Generate an exportable pipeline report.

        Returns a structured dict suitable for JSON export or HTML rendering.
        Includes all ARIA layer summaries, key metrics, and decision analysis.
        """
        stats = self.get_stats()
        sessions = self._observer.sessions

        # Compute summary metrics
        total_cycles = stats.get('cycles', {}).get('total', 0)
        wins = stats.get('cycles', {}).get('wins', 0)
        losses = stats.get('cycles', {}).get('losses', 0)

        report = {
            'pipeline': 'ARIA',
            'version': '1.0.0',
            'summary': {
                'total_cycles': total_cycles,
                'wins': wins,
                'losses': losses,
                'win_rate': stats.get('cycles', {}).get('win_rate', 0),
                'avg_pnl': stats.get('cycles', {}).get('avg_pnl', 0),
                'avg_win': stats.get('cycles', {}).get('avg_win', 0),
                'avg_loss': stats.get('cycles', {}).get('avg_loss', 0),
                'protection_value': stats.get('protection', {}).get('total_protection_value', 0),
                'aria_score': self._aria_score,
            },
            'layers': {
                'L1_MarketBrain': {
                    'regimes_discovered': self._brain._cluster.k,
                    'current_danger': stats['brain']['danger'],
                    'danger_mean': stats.get('danger', {}).get('mean'),
                    'danger_std': stats.get('danger', {}).get('std'),
                },
                'L2_CycleGate': {
                    'enabled': self._gate_enabled,
                    'cycles_processed': self._gate.n_cycles,
                    'warmed_up': self._gate.is_warmed_up,
                    'threshold': round(self._gate.threshold, 4),
                    'entries_blocked': stats.get('entries_blocked', 0),
                    'block_rate': stats.get('block_rate', 0),
                    'gate_accuracy': stats.get('gate', {}).get('allow_accuracy', 0),
                    'pnl_saved_by_blocks': stats.get('gate', {}).get('est_pnl_saved_by_blocks', 0),
                },
                'L3_HPEngine': {
                    'enabled': self._hp_engine_enabled,
                    'cycles_processed': self._hp_engine.n_cycles,
                    'warmed_up': self._hp_engine.is_warmed_up,
                    'groups': stats.get('hp_engine', {}).get('groups', []),
                    'arms_per_group': stats.get('hp_engine', {}).get('arms_per_group', {}),
                    'current_selection': self._hp_selection,
                },
                'L4_RiskShield': {
                    'conformal_calibration_cycles': self._shield.conformal._total_cycles,
                    'conformal_active': self._shield.conformal._total_cycles >= 20,
                    'calibrated_levels': len(self._shield.conformal._calibration),
                    'aborts_triggered': stats.get('aborts_triggered', 0),
                    'abort_rate': stats.get('abort_rate', 0),
                    'pnl_saved_by_aborts': stats.get('abort', {}).get('pnl_saved_by_aborts', 0),
                },
                'L5_Observer': {
                    'enriched_sessions': len(sessions),
                },
                'L6_MetaEvaluator': {
                    'enabled': self._meta_enabled,
                    'aria_score': self._aria_score,
                    'rolling_mean': round(self._meta.rolling_mean, 6),
                    'rolling_std': round(self._meta.rolling_std, 6),
                    'score_observations': len(self._meta.score_history),
                },
            },
            'risk_intel': stats.get('risk_intel', {}),
            'level_performance': stats.get('level_performance', {}),
            'exit_breakdown': stats.get('cycles', {}).get('pnl_by_exit', {}),
            'danger_distribution': stats.get('danger', {}),
            'cycle_outcomes': stats.get('cycle_outcomes', []),
        }
        return report

    def save_state(self, path: str) -> None:
        """Persist all layer state to disk."""
        os.makedirs(path, exist_ok=True)
        state = {
            'brain': self._brain.state_dict(),
            'gate': self._gate.state_dict(),
            'hp_engine': self._hp_engine.state_dict(),
            'shield': self._shield.state_dict(),
            'observer': self._observer.state_dict(),
            'meta': self._meta.state_dict(),
        }
        with open(os.path.join(path, 'aria_state.json'), 'w') as f:
            json.dump(state, f)

    def load_state(self, path: str) -> None:
        """Restore all layer state from disk."""
        state_path = os.path.join(path, 'aria_state.json')
        if not os.path.exists(state_path):
            return
        with open(state_path, 'r') as f:
            state = json.load(f)
        if 'brain' in state:
            self._brain.load_state_dict(state['brain'])
        if 'gate' in state:
            self._gate.load_state_dict(state['gate'])
        if 'hp_engine' in state:
            self._hp_engine.load_state_dict(state['hp_engine'])
        if 'shield' in state:
            self._shield.load_state_dict(state['shield'])
        if 'observer' in state:
            self._observer.load_state_dict(state['observer'])
        if 'meta' in state:
            self._meta.load_state_dict(state['meta'])

    @classmethod
    def default_config(cls) -> dict:
        return default_config()

    @classmethod
    def architecture(cls) -> dict:
        return {
            'name': 'ARIA',
            'version': '0.1.0',
            'layers': [
                {'name': 'MarketBrain', 'type': 'feature_extraction', 'status': 'active',
                 'description': 'Online feature extraction + regime clustering'},
                {'name': 'CycleGate', 'type': 'entry_gate', 'status': 'active',
                 'description': 'Online logistic regression entry gate'},
                {'name': 'HPEngine', 'type': 'hp_selection', 'status': 'active',
                 'description': 'Contextual bandit HP selection'},
                {'name': 'RiskShield', 'type': 'risk_management', 'status': 'active',
                 'description': 'Conformal kill + liquidity gate + margin survival'},
                {'name': 'Observer', 'type': 'data_collection', 'status': 'active',
                 'description': 'Enriched session recording'},
                {'name': 'MetaEvaluator', 'type': 'evaluation', 'status': 'active',
                 'description': 'ARIA score + reward loop'},
            ],
            'composition_rules': {
                'gate_entry': 'AND (all must allow)',
                'suggest_exit': 'close_all on any kill trigger',
                'filter_order': 'sequential pass-through (Phase 2: HP injection)',
            },
        }

    def ui_metadata(self) -> dict:
        return {
            'badges': [
                {'label': 'ARIA', 'color': 'brand'},
                {'label': f'{self._brain._cluster.k} Regimes', 'color': 'surface'},
                {'label': 'Gate Active' if self._gate.is_warmed_up else 'Gate Warming',
                 'color': 'green' if self._gate.is_warmed_up else 'amber',
                 'show_if': 'gate.enabled'},
                {'label': 'HP Active' if self._hp_engine.is_warmed_up else 'HP Warming',
                 'color': 'green' if self._hp_engine.is_warmed_up else 'amber',
                 'show_if': 'hp_engine.enabled'},
                {'label': 'Conformal' if self._shield.conformal._total_cycles >= 20 else 'Fallback',
                 'color': 'green' if self._shield.conformal._total_cycles >= 20 else 'amber'},
            ],
            'metric_cards': [
                {'label': 'Protection Value', 'key': 'protection.total_protection_value',
                 'format': 'currency', 'prefix': '+', 'color': 'green', 'icon': 'shield',
                 'tooltip': 'Estimated PnL saved by gate blocks + abort early-exits'},
                {'label': 'ARIA Score', 'key': 'meta.aria_score', 'format': 'dec4', 'icon': 'chart',
                 'tooltip': 'Composite score: survival efficiency, bust penalty, CVaR95'},
                {'label': 'Gate Accuracy', 'key': 'gate.allow_accuracy', 'format': 'pct',
                 'threshold': [0.5, 0.7], 'icon': 'filter',
                 'tooltip': '% of allowed entries that were profitable'},
                {'label': 'Entries Blocked', 'key': 'block_rate', 'format': 'pct', 'color': 'amber',
                 'sub_template': '{entries_blocked} / {total_gate_checks}', 'icon': 'block',
                 'tooltip': '% of entry signals rejected by the CycleGate'},
                {'label': 'Abort Rate', 'key': 'abort_rate', 'format': 'pct', 'color': 'red',
                 'sub_template': '{aborts_triggered} aborts', 'icon': 'abort',
                 'tooltip': '% of active cycles terminated early by RiskShield'},
                {'label': 'Win Rate', 'key': 'cycles.win_rate', 'format': 'pct',
                 'threshold': [0.4, 0.6],
                 'sub_template': '{cycles.wins}W / {cycles.losses}L', 'icon': 'chart',
                 'tooltip': '% of completed cycles that ended in profit'},
                {'label': 'Avg Danger', 'key': 'danger.mean', 'format': 'dec3',
                 'threshold_inv': [0.5, 0.7],
                 'sub_template': 'std {danger.std}', 'icon': 'danger',
                 'tooltip': 'Mean danger score (0=safe, 1=extreme risk)'},
                {'label': 'Regimes', 'key': 'brain.num_regimes', 'format': 'int', 'icon': 'layers',
                 'sub_template': 'current: {brain.regime_id}',
                 'tooltip': 'Online k-means clusters discovered'},
            ],
            'sections': [
                # ── Danger Score time-series (always has data after warmup) ──
                {
                    'type': 'line_chart',
                    'title': 'Danger Score Over Time',
                    'subtitle': 'Market danger assessment from MarketBrain (L1)',
                    'data_key': 'danger_scores',
                    'empty_message': 'Danger scorer still warming up.',
                    'series': [
                        {'index': 1, 'label': 'Danger', 'color': '#ef4444',
                         'width': 1.5, 'axis': 'left'},
                    ],
                    'x_label': 'Time',
                    'summary_stats': [
                        {'label': 'Current', 'key': 'danger.current', 'format': 'dec3'},
                        {'label': 'Mean', 'key': 'danger.mean', 'format': 'dec3'},
                        {'label': 'Std', 'key': 'danger.std', 'format': 'dec3'},
                        {'label': 'High %', 'key': 'danger.high_danger_pct', 'format': 'pct'},
                    ],
                },
                # ── Cycle scatter: danger at entry vs PnL ──
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
                        'tp_hit': {'color': '#4ade80', 'label': 'TP Hit'},
                        'bucket_hit': {'color': '#4ade80', 'label': 'TP Hit'},
                        'pipeline_abort': {'color': '#fbbf24', 'label': 'Aborted'},
                        'abort': {'color': '#fbbf24', 'label': 'Aborted'},
                        'max_level_bust': {'color': '#f87171', 'label': 'Max Level'},
                        'max_level_sl': {'color': '#f87171', 'label': 'Max Level'},
                        'sl_hit': {'color': '#f87171', 'label': 'SL Hit'},
                        'margin_call': {'color': '#dc2626', 'label': 'Margin Call'},
                        '_default': {'color': '#64748b', 'label': 'Other'},
                    },
                    'ref_lines': [
                        {'axis': 'y', 'value': 0, 'style': 'dashed', 'color': '#333'},
                        {'axis': 'x', 'key': 'gate.avg_danger_at_block', 'style': 'dashed',
                         'color': 'rgba(239,68,68,0.4)', 'label': 'gate threshold'},
                    ],
                    'summary_stats': [
                        {'label': 'Correlation', 'compute': 'correlation',
                         'x': 'danger_at_entry', 'y': 'pnl'},
                        {'label': 'High-Danger PnL', 'compute': 'sum_filtered',
                         'key': 'pnl', 'filter': 'danger_at_entry > 0.7'},
                        {'label': 'Low-Danger PnL', 'compute': 'sum_filtered',
                         'key': 'pnl', 'filter': 'danger_at_entry <= 0.3'},
                        {'label': 'Gate Threshold', 'key': 'gate.threshold',
                         'format': 'dec3', 'color': 'red'},
                    ],
                },
                # ── ARIA Score Convergence ──
                {
                    'type': 'line_chart',
                    'title': 'ARIA Score Convergence',
                    'subtitle': 'Composite score tracking pipeline improvement over cycles',
                    'data_key': 'meta.score_series',
                    'show_if': 'meta.score_series',
                    'empty_message': 'No ARIA score data yet. Cycles need to complete first.',
                    'series': [
                        {'index': 1, 'label': 'ARIA Score', 'color': '#818cf8',
                         'width': 2, 'axis': 'left'},
                    ],
                    'x_label': 'Cycle',
                    'summary_stats': [
                        {'label': 'Current', 'key': 'meta.aria_score', 'format': 'dec4'},
                        {'label': 'Mean', 'key': 'meta.rolling_mean', 'format': 'dec4'},
                        {'label': 'Std', 'key': 'meta.rolling_std', 'format': 'dec4'},
                        {'label': 'Observations', 'key': 'meta.score_history_len', 'format': 'int'},
                    ],
                },
                # ── Per-level performance ──
                {
                    'type': 'bar_breakdown',
                    'title': 'Per-Level Performance',
                    'data_key': 'level_performance',
                    'empty_message': 'No level data yet.',
                    'label_prefix': 'L',
                    'label_colors': {
                        '0': 'green', '1': 'brand', '2': 'brand',
                        '3': 'amber', '4': 'amber', '5': 'amber',
                    },
                    'default_label_color': 'red',
                    'show_danger': True,
                },
                # ── Entry Gate Analysis ──
                {
                    'type': 'kv_pairs',
                    'title': 'Entry Gate (L2) Analysis',
                    'items': [
                        {'label': 'Allow Accuracy', 'key': 'gate.allow_accuracy',
                         'format': 'pct', 'threshold': [0.5, 0.6]},
                        {'label': 'Correct / Wrong Allows',
                         'template': '<green>{gate.correct_allows}</green> / <red>{gate.wrong_allows}</red>'},
                        {'label': 'PnL of Allowed Entries', 'key': 'gate.pnl_of_allowed',
                         'format': 'currency_signed'},
                        {'label': 'Est. Saved by Blocks', 'key': 'gate.est_pnl_saved_by_blocks',
                         'format': 'currency', 'prefix': '+', 'color': 'green'},
                        {'label': 'Avg Danger @ Block / Allow',
                         'template': '<red>{gate.avg_danger_at_block:.3f}</red> / <green>{gate.avg_danger_at_allow:.3f}</green>'},
                        {'label': 'Gate Threshold', 'key': 'gate.threshold', 'format': 'dec3'},
                        {'label': 'Gate Warmed Up', 'template': '{gate.warmed_up}'},
                    ],
                    'grid': 'half',
                },
                # ── Risk Shield (L4) Analysis ──
                {
                    'type': 'kv_pairs',
                    'title': 'Risk Shield (L4) Analysis',
                    'items': [
                        {'label': 'PnL Saved by Aborts', 'key': 'abort.pnl_saved_by_aborts',
                         'format': 'currency', 'prefix': '+', 'color': 'green'},
                        {'label': 'Cut Losses / Cut Profits',
                         'template': '<green>{abort.aborts_at_loss}</green> / <red>{abort.aborts_at_profit}</red>'},
                        {'label': 'Avg Level @ Abort', 'key': 'abort.avg_level_at_abort',
                         'format': 'dec1'},
                        {'label': 'Avg PnL @ Abort', 'key': 'abort.avg_pnl_at_abort',
                         'format': 'currency_signed'},
                        {'label': 'Conformal Calibration', 'key': 'shield.conformal_cycles',
                         'format': 'int'},
                        {'label': 'Conformal Active', 'template': '{shield.conformal_active}'},
                        {'label': 'Calibrated Levels', 'key': 'shield.calibration_levels',
                         'format': 'int'},
                    ],
                    'grid': 'half',
                },
                # ── Danger bucket table ──
                {
                    'type': 'bucket_table',
                    'title': 'Risk Intelligence: Danger Buckets',
                    'data_key': 'risk_intel.danger_buckets',
                    'show_if': 'risk_intel.danger_buckets',
                    'bucket_colors': {
                        'extreme': 'red', 'high': 'orange', 'medium': 'amber',
                        'low': 'green', 'very_low': 'green-light',
                    },
                    'columns': ['count', 'win_rate', 'pnl', 'avg_pnl', 'distribution'],
                    'footer_stats': [
                        {'label': 'High-Danger Entries', 'key': 'risk_intel.high_danger_entries',
                         'color': 'red'},
                        {'label': 'High-Danger Win Rate',
                         'key': 'risk_intel.high_danger_entry_winrate', 'format': 'pct'},
                        {'label': 'Avg Danger Before Bust',
                         'key': 'risk_intel.avg_danger_before_bust', 'format': 'dec3', 'color': 'red'},
                        {'label': 'Max Danger During Bust',
                         'key': 'risk_intel.avg_max_danger_during_bust', 'format': 'dec3', 'color': 'red'},
                    ],
                    'peak_danger': {'key': 'risk_intel.peak_danger_window'},
                },
                # ── Decision audit table ──
                {
                    'type': 'audit_table',
                    'title': 'Decision Audit Log',
                    'subtitle': 'Every gate and abort decision with outcome linkage',
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
                        {
                            'data_key': 'abort_decisions',
                            'type_label': 'abort',
                            'type_color': 'purple',
                            'map': {
                                'ts': 'ts', 'danger': 'danger',
                                'decision': {'key': 'action', 'abort': 'ABORT', '_default': 'continue'},
                                'level': 'level',
                                'outcome_pnl': 'pnl_at_abort',
                            },
                        },
                    ],
                    'columns': [
                        {'key': 'ts', 'label': 'Time', 'sortable': True, 'format': 'datetime'},
                        {'key': 'type', 'label': 'Type', 'format': 'badge'},
                        {'key': 'danger', 'label': 'Danger', 'sortable': True, 'format': 'dec3',
                         'color_thresholds': {'red': 0.7, 'amber': 0.5, 'green': 0}},
                        {'key': 'threshold', 'label': 'Threshold', 'format': 'dec3'},
                        {'key': 'decision', 'label': 'Decision', 'format': 'decision_badge'},
                        {'key': 'level', 'label': 'Level', 'format': 'int'},
                        {'key': 'outcome_pnl', 'label': 'Outcome PnL', 'sortable': True,
                         'format': 'currency_signed'},
                    ],
                    'filters': [
                        {'value': 'all', 'label': 'All Decisions'},
                        {'value': 'gate_blocked', 'label': 'Gate: Blocked',
                         'match': {'type': 'gate', 'decision': 'BLOCKED'}},
                        {'value': 'gate_allowed', 'label': 'Gate: Allowed',
                         'match': {'type': 'gate', 'decision': 'ALLOWED'}},
                        {'value': 'abort_triggered', 'label': 'Abort: Triggered',
                         'match': {'type': 'abort', 'decision': 'ABORT'}},
                        {'value': 'abort_continued', 'label': 'Abort: Continued',
                         'match': {'type': 'abort', 'decision': 'continue'}},
                    ],
                    'max_rows': 200,
                },
                # ── Exit reason breakdown ──
                {
                    'type': 'exit_reasons',
                    'title': 'Outcome Breakdown by Exit Reason',
                    'data_key': 'cycles.pnl_by_exit',
                    'show_if': 'cycles.pnl_by_exit',
                    'reason_colors': {
                        'tp_hit': 'green', 'bucket_hit': 'green',
                        'pipeline_abort': 'amber', 'abort': 'amber',
                        'max_level_bust': 'red', 'max_level_sl': 'red',
                        'sl_hit': 'red', 'margin_call': 'red',
                    },
                },
            ],
        }
