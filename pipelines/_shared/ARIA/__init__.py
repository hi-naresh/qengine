"""
ARIA Pipeline — Adaptive Regime-Intelligent Architecture

A strategy-agnostic intelligence layer that governs any strategy via the
Pipeline ABC.  Six internal layers:

  L1  MarketBrain   — feature extraction + online regime clustering
  L2  CycleGate     — online logistic regression entry gate
  L3  HPEngine      — contextual bandit HP selection
  L4  RiskShield    — conformal kill + liquidity gate + margin survival
  L5  Observer      — enriched session recording
  L6  MetaEvaluator — ARIA score + reward loop               (Phase 3)

Active layers: L1 + L2 + L3 + L4 + L5.
L2 and L3 have warmup periods — they learn online from cycle outcomes.
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
from .config import default_config

_MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')


class ARIAPipeline(Pipeline):
    """
    ARIA — wraps any strategy with 6 intelligence layers.

    Active layers: MarketBrain (L1), CycleGate (L2), HPEngine (L3),
    RiskShield (L4), Observer (L5).  MetaEvaluator (L6) is Phase 3.

    L2 and L3 have configurable warmup periods — they learn online from
    cycle outcomes.  During warmup, gate allows everything and HPs stay
    at strategy defaults.
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

        # Stats tracking (reuses existing PipelineStats)
        self._stats = PipelineStats()
        self._stats.config_snapshot = cfg

        # Internal state
        self._market_state: dict = {}
        self._cycle_active = False
        self._gate_confidence: float = None
        self._hp_selection: dict = {}

    # ── Observation (every candle) ──

    def on_before(self, strategy) -> None:
        """L1: update market state. L3: register HP schema + inject structural HPs."""
        self._market_state = self._brain.update(strategy)

        # Lazy HP schema registration (once)
        if self._hp_engine_enabled and not self._hp_registered:
            if hasattr(strategy, 'hyperparameters'):
                self._hp_engine.register_strategy(strategy)
                self._hp_registered = True

        # L3: between cycles, select and inject structural HPs
        sv = getattr(strategy, 'vars', {})
        if self._hp_engine_enabled and not sv.get('cycle_active', False):
            regime_id = self._market_state.get('regime_id', 0)
            self._hp_selection = self._hp_engine.select(regime_id)
            if self._hp_selection:
                self._hp_engine.inject_structural(strategy, self._hp_selection)

        # Record danger for time-series charting
        ts = strategy.candles[-1][0] if strategy.candles is not None and len(strategy.candles) > 0 else 0
        danger = self._market_state.get('danger', 0.5)
        self._stats.record_danger(ts, danger)

    # ── Entry Control ──

    def gate_entry(self, strategy) -> bool:
        """L2: CycleGate predicts P(profitable) and blocks low-confidence entries."""
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
        """L3: HPEngine injects TP/hedge values from bandit selection."""
        if self._hp_engine_enabled and self._hp_selection:
            return self._hp_engine.inject_order(order_intent, self._hp_selection)
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
            aria_score=None,        # Phase 3: from MetaEvaluator
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

        # TODO Phase 3: MetaEvaluator score + reward

    # ── Stats & Persistence ──

    def get_stats(self) -> dict:
        """Pipeline stats for the dashboard."""
        stats = self._stats.to_dict()
        stats['brain'] = {
            'regime_id': self._market_state.get('regime_id', 0),
            'regime_confidence': self._market_state.get('regime_confidence', 0.0),
            'danger': self._market_state.get('danger', 0.5),
            'trend_strength': self._market_state.get('trend_strength', 0.0),
            'volatility': self._market_state.get('volatility', 0.0),
            'efficiency': self._market_state.get('efficiency', 0.5),
            'num_regimes': self._brain._cluster.k,
        }
        stats['gate'] = {
            'n_cycles': self._gate.n_cycles,
            'warmed_up': self._gate.is_warmed_up,
            'threshold': round(self._gate.threshold, 4),
            'enabled': self._gate_enabled,
        }
        stats['hp_engine'] = {
            'n_cycles': self._hp_engine.n_cycles,
            'warmed_up': self._hp_engine.is_warmed_up,
            'registered': self._hp_registered,
            'enabled': self._hp_engine_enabled,
            'current_selection': self._hp_selection,
        }
        stats['observer'] = {
            'total_enriched_sessions': len(self._observer.sessions),
        }
        stats['shield'] = {
            'conformal_cycles': self._shield.conformal._total_cycles,
            'calibration_levels': len(self._shield.conformal._calibration),
        }
        return stats

    def save_state(self, path: str) -> None:
        """Persist all layer state to disk."""
        os.makedirs(path, exist_ok=True)
        state = {
            'brain': self._brain.state_dict(),
            'gate': self._gate.state_dict(),
            'hp_engine': self._hp_engine.state_dict(),
            'shield': self._shield.state_dict(),
            'observer': self._observer.state_dict(),
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
                {'name': 'MetaEvaluator', 'type': 'evaluation', 'status': 'pending',
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
                {'label': 'ARIA v0.2', 'color': 'blue'},
                {'label': 'Phase 2', 'color': 'green'},
            ],
            'metric_cards': [
                {'label': 'Danger', 'key': 'brain.danger', 'format': '.2f',
                 'threshold': {'warn': 0.6, 'critical': 0.8}},
                {'label': 'Regime', 'key': 'brain.regime_id', 'format': 'd'},
                {'label': 'Regimes Found', 'key': 'brain.num_regimes', 'format': 'd'},
                {'label': 'Regime Confidence', 'key': 'brain.regime_confidence', 'format': '.2f'},
                {'label': 'Cycles', 'key': 'cycles.total', 'format': 'd'},
                {'label': 'Win Rate', 'key': 'cycles.win_rate', 'format': '.1%'},
                {'label': 'Aborts', 'key': 'aborts_triggered', 'format': 'd'},
                {'label': 'Conformal Cycles', 'key': 'shield.conformal_cycles', 'format': 'd'},
            ],
            'sections': [
                {'type': 'scatter', 'title': 'Danger at Entry vs PnL',
                 'x_key': 'danger_at_entry', 'y_key': 'pnl',
                 'color_key': 'exit_reason', 'size_key': 'level'},
                {'type': 'line_chart', 'title': 'Danger Score',
                 'series': [{'key': 'danger_scores', 'label': 'Danger', 'color': '#ef4444'}]},
                {'type': 'bar_breakdown', 'title': 'Level Performance',
                 'key': 'level_performance'},
                {'type': 'bucket_table', 'title': 'Risk Intelligence',
                 'key': 'risk_intel.danger_buckets'},
                {'type': 'exit_reasons', 'title': 'Exit Reasons',
                 'key': 'cycles.pnl_by_exit'},
            ],
        }
