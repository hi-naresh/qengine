"""
AgentPilot — LLM-as-Trader Pipeline.

An LLM (Claude, Gemini, GPT, or any provider) acts as the full trading brain.
The strategy becomes a pure executor — all decisions about entry, exit, sizing,
HP adjustment, and position management are made by the LLM agent.

Architecture:
  MarketScanner    — detects trigger events worth consulting the LLM
  ContextBuilder   — assembles enriched prompt from market state + journal
  AgentBrain       — LLM API calls, caching, response parsing
  Journal          — structured memory across consultations
  DecisionExecutor — applies LLM decisions to strategy (orders, HPs)
"""
from __future__ import annotations
import json
import os
import time
from typing import Optional

from qengine.framework.base import Pipeline, OrderIntent
from qengine.framework.stats import PipelineStats
from .config import merge_config, DEFAULT_CONFIG
from .market_scanner import MarketScanner
from .context_builder import ContextBuilder
from .agent_brain import AgentBrain
from .journal import Journal
from .decision import AgentDecision, DecisionExecutor


def _log(message: str) -> None:
    """Publish a log message to the frontend via Redis."""
    try:
        from qengine.services.redis import sync_publish
        import qengine.helpers as jh
        sync_publish('log', {
            'id': jh.generate_unique_id(),
            'timestamp': jh.now_to_timestamp(),
            'message': f'[AgentPilot] {message}',
        })
    except Exception:
        pass


class AgentPilot(Pipeline):
    """
    LLM-as-Trader pipeline for Martingale/grid strategies.

    The LLM makes all trading decisions via event-driven consultations.
    Between consultations, standing orders and the current decision are enforced.
    """

    name = 'AgentPilot'

    def __init__(self, config: dict = None):
        self._cfg = merge_config(config)
        self._warmup = self._cfg.get('warmup', 50)

        # Components
        self._scanner = MarketScanner(self._cfg)
        self._brain = AgentBrain(self._cfg)
        # Use compact prompts for local models (much faster inference)
        is_local = self._brain.provider == 'ollama'
        self._context_builder = ContextBuilder(compact=is_local)
        self._journal = Journal(self._cfg)
        self._executor = DecisionExecutor(self._cfg)

        # Standard pipeline stats (for chart data, gate/abort tracking)
        self._stats = PipelineStats()
        self._stats.config_snapshot = self._cfg

        # Consultation log — full request/response for audit
        self._consultation_log: list[dict] = []

        # State
        self._bar_count: int = 0
        self._is_warmed_up: bool = False
        self._danger_score: float = 0.5
        self._last_session_number: int = -1
        self._atr_history: list[float] = []

    # ── Pipeline Hooks ──

    def on_before(self, strategy) -> None:
        self._bar_count += 1

        if self._bar_count < self._warmup:
            return

        if not self._is_warmed_up:
            self._is_warmed_up = True
            _log(f'Warmup complete ({self._warmup} bars). Provider: {self._brain.provider or "none"}, Model: {self._brain.model or "default"}')
            self._scanner.set_structural_trigger('warmup_complete')

        self._update_danger(strategy)

        # Record danger for time-series chart
        ts = float(strategy.time) if hasattr(strategy, 'time') else self._bar_count
        self._stats.record_danger(ts, self._danger_score)

        should_consult, trigger = self._scanner.scan(
            strategy, self._bar_count, self._danger_score
        )

        if should_consult and self._brain.is_configured:
            self._consult_llm(strategy, trigger)
        else:
            self._executor.apply_standing(strategy, self._bar_count)

    def gate_entry(self, strategy) -> bool:
        if not self._is_warmed_up:
            return False

        allowed = self._executor.gate_entry(strategy)
        decision = self._executor.current_decision
        signal = decision.signal if decision else 'none'

        # Record gate decision in stats
        ts = float(strategy.time) if hasattr(strategy, 'time') else self._bar_count
        confidence = decision.confidence if decision else 0.0
        self._stats.record_gate(ts, self._danger_score, allowed, threshold=confidence)

        _log(f'Gate: {"ALLOW" if allowed else "BLOCK"} (signal={signal})')
        return allowed

    def adjust_size(self, strategy, qty: float, side: str) -> float:
        if not self._is_warmed_up:
            return qty
        adjusted = self._executor.adjust_size(strategy, qty)
        if adjusted != qty:
            ts = float(strategy.time) if hasattr(strategy, 'time') else self._bar_count
            self._stats.record_size_adjustment(ts, qty, adjusted, side)
        return adjusted

    def filter_order(self, strategy, order_intent: OrderIntent) -> Optional[OrderIntent]:
        return order_intent

    def suggest_exit(self, strategy) -> Optional[dict]:
        if not self._is_warmed_up:
            return None
        result = self._executor.suggest_exit(strategy)
        if result:
            ts = float(strategy.time) if hasattr(strategy, 'time') else self._bar_count
            self._stats.record_exit_suggestion(ts, result.get('action', 'unknown'), result)
        return result

    def on_open_position(self, strategy) -> None:
        self._scanner.set_structural_trigger('position_opened')
        self._stats.start_cycle(
            timestamp=float(strategy.time) if hasattr(strategy, 'time') else self._bar_count,
            danger_at_entry=self._danger_score,
        )

    def on_cycle_end(self, pnl: float, strategy) -> None:
        sn = strategy.vars.get('session_number', 0) if hasattr(strategy, 'vars') else 0
        if sn == self._last_session_number:
            return
        self._last_session_number = sn

        level = strategy.vars.get('level', 0) if hasattr(strategy, 'vars') else 0
        decision = self._executor.current_decision
        exit_reason = 'agent_close' if (decision and decision.signal == 'close_all') else 'strategy_exit'

        _log(f'Cycle ended: PnL={pnl:.2f} | Session #{sn} | Level {level} | Streak: {self._journal.consecutive_wins}W/{self._journal.consecutive_losses}L')

        # Record in PipelineStats
        self._stats.end_cycle(
            pnl=pnl,
            exit_reason=exit_reason,
            level=level,
            danger_at_exit=self._danger_score,
            session_number=sn,
        )

        self._journal.record_outcome(pnl)
        self._executor.on_cycle_end()
        self._scanner.on_cycle_end()

        if self._brain.is_configured:
            self._scanner.set_structural_trigger(f'cycle_end_pnl_{pnl:.2f}')

    # ── Core Consultation Logic ──

    def _consult_llm(self, strategy, trigger: str) -> None:
        _log(f'Trigger: {trigger} | Bar {self._bar_count} | Price {strategy.price:.5f} | Danger {self._danger_score:.3f}')

        journal_context = self._journal.get_prompt_context()
        system_prompt, user_prompt = self._context_builder.build(
            strategy, trigger, journal_context, self._danger_score
        )

        t0 = time.time()
        decision, raw_response = self._brain.consult_with_raw(system_prompt, user_prompt)
        elapsed = time.time() - t0

        cache_status = 'CACHE HIT' if elapsed < 0.1 else f'{elapsed:.1f}s'
        _log(
            f'Decision: {decision.signal} | Conf: {decision.confidence:.2f} | '
            f'Sizing: {decision.sizing_pct:.1%} | TTL: {decision.ttl_bars} bars | '
            f'[{cache_status}]'
        )
        if decision.reasoning:
            _log(f'Reasoning: {decision.reasoning[:200]}')
        if decision.hp_overrides:
            _log(f'HP overrides: {decision.hp_overrides}')

        # Store full consultation for audit
        consultation_entry = {
            'bar': self._bar_count,
            'trigger': trigger,
            'price': round(strategy.price, 5),
            'danger': round(self._danger_score, 4),
            'elapsed_s': round(elapsed, 2),
            'cached': elapsed < 0.1,
            'request': user_prompt[-2000:],  # last 2000 chars to limit size
            'response': raw_response[:2000] if raw_response else '',
            'decision': decision.to_dict(),
            'position_open': strategy.is_open,
            'level': strategy.vars.get('level', 0) if hasattr(strategy, 'vars') else 0,
            'balance': round(strategy.balance, 2),
        }
        self._consultation_log.append(consultation_entry)
        # Cap at 500 entries
        if len(self._consultation_log) > 500:
            self._consultation_log = self._consultation_log[-500:]

        # Record in journal
        market_snapshot = {
            'price': strategy.price,
            'danger': round(self._danger_score, 3),
            'bar': self._bar_count,
        }
        self._journal.record(
            bar_index=self._bar_count,
            trigger=trigger,
            decision_dict=decision.to_dict(),
            market_snapshot=market_snapshot,
            reasoning=decision.reasoning,
        )

        if decision.reasoning:
            self._journal.thesis = decision.reasoning

        self._executor.apply(decision, strategy, self._bar_count)

    def _update_danger(self, strategy) -> None:
        import math
        try:
            import qengine.indicators as ta
            candles = strategy.candles
            if candles is None or len(candles) < 50:
                return
            atr_14 = float(ta.atr(candles, period=14))
            if math.isnan(atr_14) or atr_14 <= 0:
                return
            self._atr_history.append(atr_14)
            if len(self._atr_history) > 100:
                self._atr_history = self._atr_history[-100:]
            mean_atr = sum(self._atr_history) / len(self._atr_history)
            ratio = atr_14 / mean_atr if mean_atr > 0 else 1.0
            self._danger_score = 1.0 / (1.0 + math.exp(-(ratio - 1.0) * 3.0))
        except Exception:
            pass

    # ── Stats & Persistence ──

    def get_stats(self) -> dict:
        # Get standard PipelineStats analytics (gate, abort, cycles, danger, risk_intel, etc.)
        base = self._stats.to_dict()

        # Downsample large arrays to prevent WebSocket/frontend freeze
        # danger_scores: keep max 500 points (every Nth)
        if base.get('danger_scores') and len(base['danger_scores']) > 500:
            step = len(base['danger_scores']) // 500
            base['danger_scores'] = base['danger_scores'][::step][:500]
        # cycle_outcomes: cap at last 200
        if base.get('cycle_outcomes') and len(base['cycle_outcomes']) > 200:
            base['cycle_outcomes'] = base['cycle_outcomes'][-200:]
        # gate_decisions: cap at last 100
        if base.get('gate_decisions') and len(base['gate_decisions']) > 100:
            base['gate_decisions'] = base['gate_decisions'][-100:]

        # Brain stats
        brain_stats = self._brain.state_dict()
        base['brain'] = {
            'provider': brain_stats.get('provider', 'none'),
            'model': brain_stats.get('model', 'none'),
            'api_calls': brain_stats.get('api_calls', 0),
            'cache_hits': brain_stats.get('cache_hits', 0),
            'cache_misses': brain_stats.get('cache_misses', 0),
            'errors': brain_stats.get('errors', 0),
            'cache_size': brain_stats.get('cache_size', 0),
            'hit_rate': (
                brain_stats['cache_hits'] / max(1, brain_stats['cache_hits'] + brain_stats['cache_misses'])
                if brain_stats.get('cache_hits', 0) + brain_stats.get('cache_misses', 0) > 0
                else 0.0
            ),
        }

        # Scanner stats
        scanner_stats = self._scanner.state_dict()
        base['scanner'] = {
            'triggers_fired': scanner_stats.get('triggers_fired', 0),
            'trigger_counts': scanner_stats.get('trigger_counts', {}),
        }

        # Journal summary
        journal_stats = self._journal.state_dict()
        base['journal'] = {
            'total_consultations': journal_stats.get('total_consultations', 0),
            'entries': len(journal_stats.get('entries', [])),
            'thesis': journal_stats.get('thesis', ''),
            'regime': journal_stats.get('regime_assessment', 'unknown'),
            'consecutive_wins': journal_stats.get('consecutive_wins', 0),
            'consecutive_losses': journal_stats.get('consecutive_losses', 0),
            'lessons': journal_stats.get('lessons', []),
        }

        # Executor stats
        base['executor'] = {
            'decisions_applied': self._executor.decisions_applied,
            'hp_changes': self._executor.hp_changes,
            'entries_allowed': self._executor.entries_allowed,
            'entries_blocked': self._executor.entries_blocked,
            'block_rate': (
                self._executor.entries_blocked /
                max(1, self._executor.entries_allowed + self._executor.entries_blocked)
            ),
        }

        # Current decision
        decision = self._executor.current_decision
        base['current_decision'] = decision.to_dict() if decision else None

        # Consultation log for audit table — SLIM version (no request/response text)
        # Full log with request/response is saved to disk via save_state()
        slim_log = []
        signal_counts = {}
        trigger_counts = {}
        conf_series = []
        for entry in self._consultation_log:
            # Slim entry: strip bulky request/response, keep decision metadata
            slim_log.append({
                'bar': entry.get('bar'),
                'trigger': entry.get('trigger'),
                'price': entry.get('price'),
                'danger': entry.get('danger'),
                'elapsed_s': entry.get('elapsed_s'),
                'cached': entry.get('cached'),
                'decision': entry.get('decision', {}),
                'position_open': entry.get('position_open'),
                'level': entry.get('level'),
                'balance': entry.get('balance'),
            })

            # Signal distribution
            sig = entry.get('decision', {}).get('signal', 'unknown')
            signal_counts[sig] = signal_counts.get(sig, 0) + 1

            # Trigger distribution (simplify repeating triggers)
            trig = entry.get('trigger', 'unknown')
            if trig.startswith('cycle_end_pnl_'):
                trig = 'cycle_end'
            elif trig.startswith('level_up_to_'):
                trig = 'level_up'
            trigger_counts[trig] = trigger_counts.get(trig, 0) + 1

            # Confidence series
            conf_series.append([
                entry.get('bar', 0),
                entry.get('decision', {}).get('confidence', 0),
                entry.get('danger', 0.5),
            ])

        base['consultation_log'] = slim_log
        base['signal_distribution'] = signal_counts
        base['trigger_distribution'] = trigger_counts
        base['confidence_series'] = conf_series

        base['_ui'] = self.ui_metadata()
        return base

    def save_state(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)

        with open(os.path.join(path, 'journal.json'), 'w') as f:
            json.dump(self._journal.state_dict(), f, indent=2)

        with open(os.path.join(path, 'scanner.json'), 'w') as f:
            json.dump(self._scanner.state_dict(), f, indent=2)

        self._brain.save_cache(path)

        with open(os.path.join(path, 'agent_pilot_state.json'), 'w') as f:
            json.dump({
                'bar_count': self._bar_count,
                'danger_score': self._danger_score,
                'atr_history': self._atr_history[-50:],
                'last_session_number': self._last_session_number,
            }, f, indent=2)

        # Save full consultation log for post-analysis
        with open(os.path.join(path, 'consultation_log.json'), 'w') as f:
            json.dump(self._consultation_log, f, indent=2)

    def load_state(self, path: str) -> None:
        journal_file = os.path.join(path, 'journal.json')
        if os.path.exists(journal_file):
            with open(journal_file, 'r') as f:
                self._journal.load_state_dict(json.load(f))

        scanner_file = os.path.join(path, 'scanner.json')
        if os.path.exists(scanner_file):
            with open(scanner_file, 'r') as f:
                self._scanner.load_state_dict(json.load(f))

        self._brain.load_cache(path)

        state_file = os.path.join(path, 'agent_pilot_state.json')
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                d = json.load(f)
                self._bar_count = d.get('bar_count', 0)
                self._danger_score = d.get('danger_score', 0.5)
                self._atr_history = d.get('atr_history', [])
                self._last_session_number = d.get('last_session_number', -1)

        log_file = os.path.join(path, 'consultation_log.json')
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                self._consultation_log = json.load(f)

    @classmethod
    def default_config(cls) -> dict:
        return DEFAULT_CONFIG

    @classmethod
    def architecture(cls) -> dict:
        return {
            'name': 'AgentPilot',
            'description': 'LLM-as-Trader — AI agent makes all trading decisions',
            'layers': [
                {'name': 'MarketScanner', 'type': 'trigger', 'description': 'Detects structural + market events worth consulting the LLM'},
                {'name': 'ContextBuilder', 'type': 'context', 'description': 'Assembles enriched prompt (indicators, position, journal)'},
                {'name': 'AgentBrain', 'type': 'llm', 'description': 'LLM API calls with caching and provider switching'},
                {'name': 'Journal', 'type': 'memory', 'description': 'Structured trading journal — persistent across consultations'},
                {'name': 'DecisionExecutor', 'type': 'executor', 'description': 'Applies LLM decisions to strategy (orders, HPs, standing orders)'},
            ],
        }

    def ui_metadata(self) -> dict:
        return {
            'badges': [
                {'label': 'AgentPilot', 'color': 'brand'},
                {'label': f'{self._brain.provider or "none"}:{self._brain.model or "default"}', 'color': 'surface'},
            ],
            'metric_cards': [
                {'icon': 'chart', 'label': 'Consultations', 'key': 'journal.total_consultations', 'format': 'int', 'tooltip': 'Total LLM API consultations'},
                {'icon': 'shield', 'label': 'Win Rate', 'key': 'cycles.win_rate', 'format': 'pct', 'threshold': [0.5, 0.7]},
                {'icon': 'block', 'label': 'Block Rate', 'key': 'executor.block_rate', 'format': 'pct', 'threshold_inv': [0.3, 0.8]},
                {'icon': 'danger', 'label': 'Avg Danger', 'key': 'danger.mean', 'format': 'dec3', 'threshold_inv': [0.3, 0.6]},
                {'icon': 'filter', 'label': 'Cache Hit Rate', 'key': 'brain.hit_rate', 'format': 'pct', 'threshold': [0.3, 0.6]},
                {'icon': 'layers', 'label': 'HP Changes', 'key': 'executor.hp_changes', 'format': 'int'},
            ],
            'sections': [
                # ── Current Decision (half) ──
                {
                    'type': 'kv_pairs',
                    'title': 'Current Decision',
                    'grid': 'half',
                    'data_key': 'current_decision',
                    'auto_items': True,
                    'empty_message': 'No decision yet',
                },
                # ── Journal Summary (half) ──
                {
                    'type': 'kv_pairs',
                    'title': 'Trading Journal',
                    'grid': 'half',
                    'items': [
                        {'label': 'Thesis', 'key': 'journal.thesis', 'format': 'text'},
                        {'label': 'Regime', 'key': 'journal.regime', 'format': 'text'},
                        {'label': 'Win Streak', 'key': 'journal.consecutive_wins', 'format': 'int'},
                        {'label': 'Loss Streak', 'key': 'journal.consecutive_losses', 'format': 'int'},
                        {'label': 'Total Entries', 'key': 'journal.entries', 'format': 'int'},
                    ],
                },
                # ── Brain / LLM stats (half) ──
                {
                    'type': 'kv_pairs',
                    'title': 'LLM Brain',
                    'grid': 'half',
                    'items': [
                        {'label': 'Provider', 'key': 'brain.provider', 'format': 'text'},
                        {'label': 'Model', 'key': 'brain.model', 'format': 'text'},
                        {'label': 'API Calls', 'key': 'brain.api_calls', 'format': 'int'},
                        {'label': 'Cache Hits', 'key': 'brain.cache_hits', 'format': 'int'},
                        {'label': 'Cache Size', 'key': 'brain.cache_size', 'format': 'int'},
                        {'label': 'Errors', 'key': 'brain.errors', 'format': 'int', 'color': 'red'},
                    ],
                },
                # ── Executor (half) ──
                {
                    'type': 'kv_pairs',
                    'title': 'Decision Executor',
                    'grid': 'half',
                    'items': [
                        {'label': 'Decisions Applied', 'key': 'executor.decisions_applied', 'format': 'int'},
                        {'label': 'Entries Allowed', 'key': 'executor.entries_allowed', 'format': 'int', 'color': 'green'},
                        {'label': 'Entries Blocked', 'key': 'executor.entries_blocked', 'format': 'int', 'color': 'red'},
                        {'label': 'HP Changes', 'key': 'executor.hp_changes', 'format': 'int'},
                    ],
                },
                # ── Confidence + Danger time-series ──
                {
                    'type': 'line_chart',
                    'title': 'Confidence & Danger Over Time',
                    'data_key': 'confidence_series',
                    'show_if': 'confidence_series',
                    'series': [
                        {'index': 1, 'label': 'Confidence', 'color': '#3b82f6', 'width': 2},
                        {'index': 2, 'label': 'Danger', 'color': '#ef4444', 'width': 1.5, 'dashed': True},
                    ],
                    'x_label': 'Bar',
                    'summary_stats': [
                        {'label': 'Current Danger', 'key': 'danger.current', 'format': 'dec3'},
                        {'label': 'Mean Danger', 'key': 'danger.mean', 'format': 'dec3'},
                    ],
                },
                # ── Danger Score time-series ──
                {
                    'type': 'line_chart',
                    'title': 'Danger Score Over Time',
                    'data_key': 'danger_scores',
                    'show_if': 'danger_scores',
                    'series': [
                        {'index': 1, 'label': 'Danger', 'color': '#ef4444', 'width': 1.5},
                    ],
                    'summary_stats': [
                        {'label': 'Current', 'key': 'danger.current', 'format': 'dec3'},
                        {'label': 'High Danger %', 'key': 'danger.high_danger_pct', 'format': 'pct'},
                    ],
                },
                # ── Cycle scatter: Danger vs PnL ──
                {
                    'type': 'scatter',
                    'title': 'Cycle Scatter: Danger at Entry vs PnL',
                    'data_key': 'cycle_outcomes',
                    'show_if': 'cycle_outcomes',
                    'x_key': 'danger_at_entry',
                    'x_label': 'Danger at Entry',
                    'y_key': 'pnl',
                    'y_label': 'PnL',
                    'color_key': 'exit_reason',
                    'size_key': 'level',
                    'color_map': {
                        'agent_close': {'color': '#8b5cf6', 'label': 'Agent Close'},
                        'strategy_exit': {'color': '#3b82f6', 'label': 'Strategy Exit'},
                        'pipeline_abort': {'color': '#f59e0b', 'label': 'Abort'},
                        '_default': {'color': '#64748b', 'label': 'Other'},
                    },
                    'ref_lines': [
                        {'axis': 'y', 'value': 0, 'style': 'dashed', 'color': '#475569'},
                    ],
                    'summary_stats': [
                        {'label': 'Correlation', 'compute': 'correlation', 'x': 'danger_at_entry', 'y': 'pnl'},
                    ],
                },
                # ── Signal Distribution ──
                {
                    'type': 'bar_breakdown',
                    'title': 'Signal Distribution',
                    'data_key': 'signal_distribution',
                    'show_if': 'signal_distribution',
                    'mode': 'count_only',
                    'label_colors': {
                        'long': 'green',
                        'short': 'red',
                        'hold': 'surface',
                        'close_all': 'amber',
                        'no_action': 'surface',
                    },
                },
                # ── Trigger Distribution ──
                {
                    'type': 'bar_breakdown',
                    'title': 'Trigger Distribution',
                    'data_key': 'trigger_distribution',
                    'show_if': 'trigger_distribution',
                    'mode': 'count_only',
                    'label_colors': {
                        'warmup_complete': 'brand',
                        'position_opened': 'green',
                        'cycle_end': 'amber',
                        'level_up': 'red',
                        'ema_crossover': 'blue',
                        'atr_spike': 'red',
                        'scheduled_checkin': 'surface',
                    },
                },
                # ── Per-Level Performance ──
                {
                    'type': 'bar_breakdown',
                    'title': 'Per-Level Performance',
                    'data_key': 'level_performance',
                    'show_if': 'level_performance',
                    'label_prefix': 'L',
                    'label_colors': {
                        '0': 'green', '1': 'brand', '2': 'brand',
                        '3': 'amber', '4': 'amber', '5': 'red',
                    },
                    'mode': 'win_loss',
                    'show_danger': True,
                },
                # ── Risk Intelligence: Danger Buckets ──
                {
                    'type': 'bucket_table',
                    'title': 'Risk Intelligence: Danger Buckets',
                    'data_key': 'risk_intel.danger_buckets',
                    'show_if': 'risk_intel.danger_buckets',
                    'bucket_colors': {
                        'extreme': 'red',
                        'high': 'orange',
                        'medium': 'amber',
                        'low': 'green',
                        'very_low': 'green',
                    },
                },
                # ── Exit Reason Breakdown ──
                {
                    'type': 'exit_reasons',
                    'title': 'Exit Reason Breakdown',
                    'data_key': 'cycles.pnl_by_exit',
                    'show_if': 'cycles.pnl_by_exit',
                },
                # ── Lessons Learned ──
                {
                    'type': 'kv_pairs',
                    'title': 'Lessons Learned (from LLM)',
                    'show_if': 'journal.lessons',
                    'items': [
                        {'label': f'Lesson', 'key': 'journal.lessons', 'format': 'text'},
                    ],
                },
                # ── Full Consultation Audit Log ──
                {
                    'type': 'audit_table',
                    'title': 'LLM Consultation Log',
                    'subtitle': 'Full request/response audit trail — check for data leakage',
                    'sources': [
                        {
                            'data_key': 'consultation_log',
                            'type_label': 'consult',
                            'type_color': 'purple',
                            'map': {
                                'ts': 'bar',
                                'danger': 'danger',
                                'decision': {'key': 'decision.signal'},
                                'outcome_pnl': None,
                            },
                        },
                    ],
                    'columns': [
                        {'key': 'bar', 'label': 'Bar', 'sortable': True, 'format': 'int'},
                        {'key': 'trigger', 'label': 'Trigger', 'sortable': True, 'format': 'text'},
                        {'key': 'price', 'label': 'Price', 'format': 'dec4'},
                        {'key': 'danger', 'label': 'Danger', 'sortable': True, 'format': 'dec3',
                         'color_thresholds': {'red': 0.7, 'amber': 0.5}},
                        {'key': 'decision.signal', 'label': 'Signal', 'format': 'text',
                         'color_map': {'long': 'green', 'short': 'red', 'hold': 'surface', 'close_all': 'amber'}},
                        {'key': 'decision.confidence', 'label': 'Conf', 'sortable': True, 'format': 'dec2'},
                        {'key': 'decision.reasoning', 'label': 'Reasoning', 'format': 'text'},
                        {'key': 'elapsed_s', 'label': 'Time(s)', 'sortable': True, 'format': 'dec1'},
                        {'key': 'cached', 'label': 'Cached', 'format': 'text'},
                        {'key': 'balance', 'label': 'Balance', 'format': 'currency'},
                    ],
                    'filters': [
                        {'value': 'all', 'label': 'All Consultations'},
                        {'value': 'long', 'label': 'Long Signals', 'match': {'decision.signal': 'long'}},
                        {'value': 'short', 'label': 'Short Signals', 'match': {'decision.signal': 'short'}},
                        {'value': 'close', 'label': 'Close All', 'match': {'decision.signal': 'close_all'}},
                    ],
                    'max_rows': 500,
                },
                # ── Gate Decision Audit ──
                {
                    'type': 'audit_table',
                    'title': 'Gate Decision Audit',
                    'subtitle': 'Entry gate decisions with outcome linkage',
                    'sources': [
                        {
                            'data_key': 'gate_decisions',
                            'type_label': 'gate',
                            'type_color': 'blue',
                            'map': {
                                'ts': 'ts',
                                'danger': 'danger',
                                'decision': {'key': 'allowed', 'true': 'ALLOWED', 'false': 'BLOCKED'},
                                'outcome_pnl': 'outcome_pnl',
                            },
                        },
                    ],
                    'columns': [
                        {'key': 'ts', 'label': 'Time', 'sortable': True, 'format': 'datetime'},
                        {'key': 'danger', 'label': 'Danger', 'sortable': True, 'format': 'dec3',
                         'color_thresholds': {'red': 0.7, 'amber': 0.5}},
                        {'key': 'decision', 'label': 'Decision', 'format': 'decision_badge',
                         'color_map': {'ALLOWED': 'green', 'BLOCKED': 'red'}},
                        {'key': 'outcome_pnl', 'label': 'Outcome PnL', 'sortable': True, 'format': 'currency_signed'},
                    ],
                    'filters': [
                        {'value': 'all', 'label': 'All Decisions'},
                        {'value': 'blocked', 'label': 'Blocked Only', 'match': {'decision': 'BLOCKED'}},
                        {'value': 'allowed', 'label': 'Allowed Only', 'match': {'decision': 'ALLOWED'}},
                    ],
                    'max_rows': 200,
                },
            ],
        }
