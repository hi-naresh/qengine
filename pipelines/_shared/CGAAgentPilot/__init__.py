"""
CGAAgentPilot — rolling-window agent-based GA pipeline.

Baseline implementation of the *time-based adaptation* approach described in
Budiharto & Prasetyo (2025), "Agent-Based Genetic Algorithm for Crypto
Trading Strategy Optimization" (arxiv 2510.07943). Re-optimisation is
triggered every 30 calendar days on the trailing 30-day window; a simple
agent coordinator adjusts GA hyperparameters (mutation sigma, crossover
rate, tournament size) based on fitness feedback and market microstructure
signals (NATR percentile).

Designed as the dissertation counterpart to IslandPilot's regime-triggered
evolution, isolating the "adapt on time vs. adapt on regime" question.
"""

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

from qengine.framework.base import Pipeline
from pipelines._shared.components.feature_selector import FeaturePool
from pipelines._shared.components.island_evolver import (
    GENE_BOUNDS,
    Genome,
    build_gene_bounds_from_strategy,
)

from .config import DEFAULT_CONFIG, merge_config
from .rolling_ga import RollingGA, compute_fitness
from .agent_coordinator import AgentCoordinator

_MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')


class CGAAgentPilot(Pipeline):
    name = 'CGAAgentPilot'

    def __init__(self, config: Optional[dict] = None):
        self.cfg = merge_config(config or {})

        # Build gene bounds (pipeline-level first, strategy HP appended on first on_before)
        self._gene_bounds: Optional[Dict] = None
        self._hp_spec: Optional[Dict[str, dict]] = None
        self._ga: Optional[RollingGA] = None

        self.coordinator = AgentCoordinator(
            cfg=self.cfg['coordinator'],
            ga_cfg=self.cfg['ga'],
        )

        # Runtime
        self._candle_count = 0
        self._last_retrain_candle = 0
        self._retrain_count = 0
        self._cycle_count = 0
        self._last_recorded_session: Optional[int] = None
        self._active_genome: Optional[Genome] = None  # currently applied to strategy
        self._vol_buffer: List[float] = []             # trailing NATR values
        self._vol_pctile_now: Optional[float] = None

        self.feature_pool = FeaturePool()

        # Auto-load persisted state
        self._load_pretrained_models()

    # ------------------------------------------------------------------
    # Internal — initialise GA once the strategy is known
    # ------------------------------------------------------------------

    def _ensure_ga_ready(self, strategy) -> None:
        if self._ga is not None:
            return
        # Start from IslandPilot-style dynamic bounds (strategy HP + pipeline).
        try:
            bounds = build_gene_bounds_from_strategy(strategy)
        except Exception:
            bounds = dict(GENE_BOUNDS)

        # Override / inject pipeline-level genes from config
        _TYPE_MAP = {'int': int, 'float': float}
        for name, spec in self.cfg['pipeline_gene_bounds'].items():
            lo, hi, dtype = spec
            bounds[name] = (lo, hi, _TYPE_MAP.get(dtype, float))

        self._gene_bounds = bounds

        # Cache HP spec for genome application
        try:
            hp_list = strategy.hyperparameters()
            self._hp_spec = {
                h['name']: h for h in hp_list
                if isinstance(h, dict) and 'name' in h
            }
        except Exception:
            self._hp_spec = {}

        # If we loaded a persisted RollingGA already, keep it; else construct.
        if self._ga is None:
            self._ga = RollingGA(
                gene_bounds=bounds,
                population_size=self.cfg['ga']['population_size'],
                rolling_window_cycles=self.cfg['rolling_window_cycles'],
                elitism=self.cfg['ga']['elitism'],
            )

    # ------------------------------------------------------------------
    # Pipeline hooks
    # ------------------------------------------------------------------

    def on_before(self, strategy) -> None:
        self._candle_count += 1
        self._ensure_ga_ready(strategy)

        # Update trailing NATR for the volatility agent
        candles = getattr(strategy, 'candles', None)
        if candles is not None and len(candles) >= 30:
            try:
                tail = candles[-300:] if len(candles) > 300 else candles
                feat_matrix = self.feature_pool.compute(tail)
                # Feature index 0 is 'natr_14' by default
                names = self.feature_pool.feature_names
                if 'natr_14' in names:
                    idx = names.index('natr_14')
                    natr = float(feat_matrix[-1, idx])
                    if not np.isnan(natr):
                        self._vol_buffer.append(natr)
                        max_vol = self.cfg['coordinator']['vol_window_candles']
                        if len(self._vol_buffer) > max_vol:
                            self._vol_buffer = self._vol_buffer[-max_vol:]
                        if len(self._vol_buffer) > 50:
                            arr = np.asarray(self._vol_buffer)
                            # empirical CDF rank of latest value
                            self._vol_pctile_now = float(
                                np.searchsorted(np.sort(arr), natr) / len(arr))
            except Exception:
                pass

        # Retrain trigger — only between cycles (no open position / no cycle_active)
        position_open = self._position_open(strategy)
        candles_since_retrain = self._candle_count - self._last_retrain_candle
        if (candles_since_retrain >= self.cfg['retrain_interval_candles']
                and not position_open
                and self._ga is not None):
            self._do_retrain(strategy)
            self._last_retrain_candle = self._candle_count

        # Apply best genome between cycles
        if self._ga is not None and not position_open:
            best = self._ga.get_active_genome()
            self._active_genome = best
            if best is not None:
                self._apply_genome(strategy, best.genes)

    def gate_entry(self, strategy) -> bool:
        if self._candle_count < self.cfg['warmup']:
            return False
        return self._ga is not None and self._active_genome is not None

    def suggest_exit(self, strategy) -> Optional[dict]:
        # Abort via genome's abort_aggressiveness gene (mirrors IslandPilot
        # so the two pipelines remain comparable).
        if self._active_genome is None:
            return None
        aggr = float(self._active_genome.genes.get('abort_aggressiveness', 0.2))
        threshold = 1.0 - aggr
        danger = self._compute_danger(strategy)
        if danger > threshold:
            return {'action': 'close_all'}
        return None

    def on_cycle_end(self, pnl: float, strategy) -> None:
        # Session-number dedupe (same pattern as IslandPilot)
        sn = getattr(strategy, 'vars', {}).get('session_number') if strategy else None
        if sn is not None and sn == self._last_recorded_session:
            return
        self._last_recorded_session = sn

        self._cycle_count += 1
        genome_id = self._active_genome.id if self._active_genome else None
        bust = False
        if strategy and hasattr(strategy, 'vars'):
            bust = bool(strategy.vars.get('last_session_bust', False))
        if self._ga is not None:
            self._ga.record_outcome(genome_id, pnl, bust=bust)

    # ------------------------------------------------------------------
    # Retrain
    # ------------------------------------------------------------------

    def _do_retrain(self, strategy) -> None:
        """Run one GA generation + coordinator adjustment."""
        ga_cfg = self.cfg['ga']
        # score + evolve
        best_f, f_std = self._ga.retrain(
            mutation_sigma=self.coordinator.mutation_sigma,
            crossover_rate=self.coordinator.crossover_rate,
            tournament_k=self.coordinator.tournament_k,
            mutation_rate=ga_cfg.get('mutation_rate', 0.2),
        )
        # coordinator step (updates sigma / crossover / k for NEXT retrain)
        timestamp = None
        candles = getattr(strategy, 'candles', None)
        if candles is not None and len(candles) > 0:
            try:
                timestamp = float(candles[-1, 0])
            except Exception:
                timestamp = None

        self.coordinator.adjust(
            retrain_idx=self._retrain_count,
            best_fitness=best_f,
            fitness_std=f_std,
            market_vol_percentile=self._vol_pctile_now,
            timestamp=timestamp,
        )
        self._retrain_count += 1

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _position_open(self, strategy) -> bool:
        if hasattr(strategy, 'position') and hasattr(strategy.position, 'is_open'):
            if strategy.position.is_open:
                return True
        if hasattr(strategy, 'vars') and strategy.vars.get('cycle_active'):
            return True
        return False

    def _compute_danger(self, strategy) -> float:
        candles = getattr(strategy, 'candles', None)
        if candles is None or len(candles) < 20:
            return 0.0
        closes = candles[-20:, 2]
        if closes[0] == 0:
            return 0.0
        returns = np.diff(closes) / (closes[:-1] + 1e-12)
        vol = np.std(returns)
        return float(np.clip(vol / 0.01, 0.0, 1.0))

    def _apply_genome(self, strategy, genes: dict) -> None:
        """Apply genome values to tunable strategy HP — same policy as IslandPilot."""
        if not hasattr(strategy, 'hp') or not self._hp_spec:
            return

        _TUNABLE_GROUPS = {'General', 'Grid / Hedge', 'Take Profit'}
        _SAFE_OPTIONS = {
            'signal_mode': {'random', 'ema_cross', 'rsi', 'macd', 'supertrend',
                            'stoch', 'ema_rsi', 'ema_macd', 'triple'},
            'hedge_mode': {'fixed_pips', 'atr_based', 'percentage'},
            'tp_mode': {'fixed_pips', 'atr_based', 'bucket_pct', 'risk_reward'},
            'base_size_mode': {'pct_equity', 'capital_aware'},
            'sizing_curve': {'geometric', 'sqrt', 'linear', 'fibonacci'},
        }

        hp = strategy.hp
        for name, spec in self._hp_spec.items():
            group = spec.get('group', '')
            if group not in _TUNABLE_GROUPS or name not in genes:
                continue

            val = genes[name]
            hp_type = spec.get('type')
            if hp_type == 'categorical':
                options = spec.get('options', [])
                safe = _SAFE_OPTIONS.get(name)
                if safe:
                    options = [o for o in options if o in safe]
                if not options:
                    continue
                if isinstance(val, (int, float)):
                    idx = max(0, min(int(round(val)), len(options) - 1))
                    hp[name] = options[idx]
                elif val in options:
                    hp[name] = val
            elif hp_type in (int, float) or hp_type in ('int', 'float'):
                lo = spec.get('min', float('-inf'))
                hi = spec.get('max', float('inf'))
                val = max(lo, min(hi, float(val)))
                if hp_type in (int, 'int'):
                    val = int(round(val))
                hp[name] = val

    # ------------------------------------------------------------------
    # Stats & UI
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        ga = self._ga
        best_genome = None
        if ga is not None:
            bg = ga.get_active_genome()
            if bg is not None:
                best_genome = {
                    'id': bg.id,
                    'fitness': bg.fitness,
                    'genes': {k: (round(v, 4) if isinstance(v, float) else v)
                              for k, v in bg.genes.items()},
                }

        retrain_interval = self.cfg['retrain_interval_candles']
        next_in = max(0, retrain_interval - (self._candle_count - self._last_retrain_candle))

        return {
            'candle_count': self._candle_count,
            'cycle_count': self._cycle_count,
            'retrain_count': self._retrain_count,
            'next_retrain_in_candles': next_in,
            'retrain_interval_candles': retrain_interval,
            'current_mutation_sigma': round(self.coordinator.mutation_sigma, 4),
            'current_crossover_rate': round(self.coordinator.crossover_rate, 4),
            'tournament_k': self.coordinator.tournament_k,
            'current_best_fitness': round(ga.best_fitness(), 4) if ga else None,
            'fitness_std': round(ga.fitness_std(), 4) if ga else None,
            'market_vol_percentile': round(self._vol_pctile_now, 4)
                                    if self._vol_pctile_now is not None else None,
            'best_fitness_history': [round(v, 4) for v in self.coordinator.best_fitness_history],
            'adjustment_log': list(self.coordinator.adjustment_log),
            'best_genome': best_genome,
            '_ui': self.ui_metadata(),
        }

    def ui_metadata(self) -> dict:
        return {
            'badges': [
                {'label': self.name, 'color': 'brand'},
                {'label': f'Retrains: {self._retrain_count}', 'color': 'surface'},
                {'label': f'σ={self.coordinator.mutation_sigma:.3f}', 'color': 'amber'},
            ],
            'metric_cards': [
                {'label': 'Next Retrain (candles)', 'key': 'next_retrain_in_candles',
                 'format': 'int', 'icon': 'chart',
                 'tooltip': 'Candles until the next rolling-window GA retrain'},
                {'label': 'Current Best Fitness', 'key': 'current_best_fitness',
                 'format': 'dec4', 'icon': 'chart',
                 'tooltip': 'Best composite fitness in the current population'},
                {'label': 'Mutation σ', 'key': 'current_mutation_sigma',
                 'format': 'dec4', 'icon': 'chart',
                 'tooltip': 'Agent-controlled Gaussian mutation scale'},
                {'label': 'Crossover rate', 'key': 'current_crossover_rate',
                 'format': 'dec4', 'icon': 'chart'},
                {'label': 'Tournament k', 'key': 'tournament_k',
                 'format': 'int', 'icon': 'chart'},
                {'label': 'Retrains', 'key': 'retrain_count',
                 'format': 'int', 'icon': 'chart'},
            ],
            'sections': [
                {
                    'type': 'audit_table',
                    'title': 'Retrain Audit Log',
                    'data_key': 'adjustment_log',
                    'columns': [
                        {'key': 'retrain', 'label': '#'},
                        {'key': 'best_fitness', 'label': 'Best Fitness', 'format': 'dec4'},
                        {'key': 'fitness_std', 'label': 'Pop σ', 'format': 'dec4'},
                        {'key': 'vol_pctile', 'label': 'Vol pctile', 'format': 'dec4'},
                        {'key': 'sigma_after', 'label': 'Mut σ', 'format': 'dec4'},
                        {'key': 'crossover_after', 'label': 'Xover', 'format': 'dec4'},
                        {'key': 'tournament_k_after', 'label': 'k'},
                        {'key': 'reasons', 'label': 'Reasons'},
                    ],
                    'empty_message': 'No retrains yet.',
                },
                {
                    'type': 'line_chart',
                    'title': 'Fitness Convergence',
                    'data_key': 'best_fitness_history',
                    'series': [{'label': 'Best Fitness', 'key': 'best_fitness_history'}],
                    'empty_message': 'No fitness history yet.',
                },
            ],
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_state(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)
        if self._ga is not None:
            with open(os.path.join(path, 'rolling_ga.json'), 'w') as f:
                json.dump(self._ga.to_dict(), f, indent=2, default=_json_default)
        with open(os.path.join(path, 'coordinator.json'), 'w') as f:
            json.dump(self.coordinator.to_dict(), f, indent=2, default=_json_default)
        runtime = {
            'candle_count': self._candle_count,
            'last_retrain_candle': self._last_retrain_candle,
            'retrain_count': self._retrain_count,
            'cycle_count': self._cycle_count,
            'vol_buffer': list(self._vol_buffer[-2000:]),
        }
        with open(os.path.join(path, 'runtime.json'), 'w') as f:
            json.dump(runtime, f, indent=2)

    def load_state(self, path: str) -> None:
        ga_path = os.path.join(path, 'rolling_ga.json')
        if os.path.exists(ga_path):
            with open(ga_path) as f:
                self._ga = RollingGA.from_dict(json.load(f))
                self._gene_bounds = self._ga.gene_bounds
        coord_path = os.path.join(path, 'coordinator.json')
        if os.path.exists(coord_path):
            with open(coord_path) as f:
                self.coordinator = AgentCoordinator.from_dict(
                    json.load(f), ga_cfg=self.cfg['ga'])
        runtime_path = os.path.join(path, 'runtime.json')
        if os.path.exists(runtime_path):
            with open(runtime_path) as f:
                rt = json.load(f)
            self._candle_count = int(rt.get('candle_count', 0))
            self._last_retrain_candle = int(rt.get('last_retrain_candle', 0))
            self._retrain_count = int(rt.get('retrain_count', 0))
            self._cycle_count = int(rt.get('cycle_count', 0))
            self._vol_buffer = list(rt.get('vol_buffer', []))

    def _load_pretrained_models(self) -> None:
        if not os.path.isdir(_MODELS_DIR):
            return
        try:
            self.load_state(_MODELS_DIR)
        except Exception:
            # Non-fatal — pipeline will initialise fresh
            pass

    @classmethod
    def default_config(cls) -> dict:
        return merge_config({})

    @classmethod
    def architecture(cls) -> dict:
        has_ga = os.path.exists(os.path.join(_MODELS_DIR, 'rolling_ga.json'))
        return {
            'name': 'CGAAgentPilot',
            'summary': 'Rolling-window agent-based GA pipeline. Re-optimises strategy '
                       'parameters every 30 trading days on the trailing 30-day window; '
                       'an agent coordinator tunes GA hyperparameters based on fitness '
                       'trend + market volatility microstructure.',
            'designed_for': ['Martingale', 'SurefireHedge variants'],
            'research_basis': 'Budiharto & Prasetyo (2025) — Agent-Based Genetic Algorithm '
                              'for Crypto Trading Strategy Optimization (arXiv:2510.07943).',
            'requires_training': True,
            'training_status': 'trained' if has_ga else 'untrained',
            'training_description': 'Warm-starts a 30-individual GA population via 5 '
                                    'offline generations, then continuously re-optimises '
                                    'at each rolling 30-day boundary.',
            'layers': [
                {
                    'name': 'FeaturePool (NATR)',
                    'order': 1,
                    'type': 'feature_extractor',
                    'hook': 'on_before()',
                    'description': 'Computes NATR-14 for the volatility agent.',
                },
                {
                    'name': 'RollingGA',
                    'order': 2,
                    'type': 'optimizer',
                    'hook': 'on_before() / on_cycle_end()',
                    'description': 'Single 30-individual population scored by rolling '
                                   'window of cycle outcomes; one generation per retrain.',
                },
                {
                    'name': 'AgentCoordinator',
                    'order': 3,
                    'type': 'meta_controller',
                    'hook': 'on_before()',
                    'description': 'Heuristic agent that adjusts mutation σ, crossover '
                                   'rate and tournament k based on fitness trend + NATR '
                                   'percentile.',
                },
            ],
            'composition_rules': {
                'gate_entry': 'AND — all pipelines must allow',
                'suggest_exit': 'Most aggressive action wins',
            },
        }


def _json_default(obj):
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f'Object of type {type(obj)} is not JSON serializable')
