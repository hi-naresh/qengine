"""
DempsterJonesPilot — walk-forward genetic-algorithm baseline pipeline.

Implements the adaptive parameter-tuning scheme from:
    Dempster, M. A. H., & Jones, C. M. (2001).
    A real-time adaptive trading system using genetic programming.
    Quantitative Finance, 1(4), 397-413.

Classical "flat" baseline for the IslandPilot comparison:
  - Single population (no islands, no regimes)
  - Rolling 3-month (90 trading day) fitness window
  - Re-optimises every 90 trading days (~4320 30m candles)
  - Applies best genome to the next period, passes through otherwise

Used to isolate how much of IslandPilot's performance comes from regime
awareness vs. the walk-forward GA machinery itself.
"""

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

from qengine.framework.base import Pipeline

from .config import DEFAULT_CONFIG, merge_config
from .walk_forward_ga import (
    WalkForwardGA,
    Genome,
    build_gene_bounds_from_strategy,
    score_from_buffer,
)


_MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
_INITIAL_POP_PATH = os.path.join(_MODELS_DIR, 'initial_population.json')

# Groups the pipeline is allowed to tune — mirrors IslandPilot for fairness.
_TUNABLE_GROUPS = {'General', 'Grid / Hedge', 'Take Profit'}

# Validated categorical options — only values known to work in the strategy.
#
# `base_size_mode` is pinned to {'pct_equity'} on purpose. The strategy's
# `capital_aware` mode in Martingale._capital_aware_base_size() sizes so that a
# full-bust loss is ≤ max_bust_dd_pct (default 20%) of balance. Combined with
# short hedge distances (8-10 pips) and moderate sizing curves, this produces
# base qty well below broker minimums at $10k balance — genomes that evolve
# into capital_aware mode render the pipeline unexecutable in live. Fixing
# mode to pct_equity also matches IslandPilot's preset-level convention, so
# the two pipelines remain comparable on equity-based sizing.
_SAFE_OPTIONS = {
    'signal_mode': {'random', 'ema_cross', 'rsi', 'macd', 'supertrend',
                    'stoch', 'ema_rsi', 'ema_macd', 'triple'},
    'hedge_mode': {'fixed_pips', 'atr_based', 'percentage'},
    'tp_mode': {'fixed_pips', 'atr_based', 'bucket_pct', 'risk_reward'},
    'base_size_mode': {'pct_equity'},
    'sizing_curve': {'geometric', 'sqrt', 'linear', 'fibonacci'},
}


class DempsterJonesPilot(Pipeline):
    """Flat single-population walk-forward GA pipeline."""

    name = 'DempsterJonesPilot'

    def __init__(self, config: Optional[dict] = None):
        self.cfg = merge_config(config or {})

        # Runtime state
        self._candle_count: int = 0
        self._last_retrain_candle: int = 0
        self._retrain_count: int = 0
        self._cycle_count: int = 0
        self._last_recorded_session: Optional[int] = None
        self._abort_count: int = 0
        self._gate_allow_count: int = 0
        self._gate_block_count: int = 0

        # Genome state
        self._ga: Optional[WalkForwardGA] = None
        self._bounds: Optional[Dict] = None
        self._active_genome: Optional[Dict[str, Any]] = None
        self._hp_spec: Optional[Dict[str, dict]] = None

        # Rolling cycle buffer (pnl, genes, cycle, bust, candle) for fitness
        self._cycle_buffer: List[Dict[str, Any]] = []

        # Per-cycle HP log for the UI audit table
        self._cycle_hp_log: List[dict] = []

        # Retrain audit log
        self._retrain_log: List[dict] = []

        # Fitness history (for convergence charts)
        self._fitness_history: List[dict] = []

        # Deferred: the GA is built the first time we see a strategy
        # (so we can auto-discover the strategy's gene bounds).
        self._initial_population_seed: Optional[list] = None
        self._try_load_seed_population()

    # ------------------------------------------------------------------
    # Pipeline hooks
    # ------------------------------------------------------------------

    def on_before(self, strategy) -> None:
        self._candle_count += 1

        # Lazy init: build GA once we can see strategy.hyperparameters()
        if self._ga is None:
            self._init_ga_from_strategy(strategy)

        # Trigger retrain on quarterly boundary (only between cycles).
        retrain_cfg = self.cfg['retrain']
        interval = retrain_cfg['interval_candles']
        warmup = retrain_cfg['warmup_candles']
        position_open = self._is_position_open(strategy)

        if (
            self._ga is not None
            and self._candle_count >= warmup
            and (self._candle_count - self._last_retrain_candle) >= interval
            and (not retrain_cfg['only_between_cycles'] or not position_open)
        ):
            self._run_retrain()
            self._last_retrain_candle = self._candle_count

        # Apply the current best genome to strategy HPs (only when flat).
        if self._active_genome is not None and not position_open:
            self._apply_genome(strategy, self._active_genome)

    def gate_entry(self, strategy) -> bool:
        """Simple gate — just respect warmup. No regime filtering."""
        if self._candle_count < self.cfg['warmup']:
            self._gate_block_count += 1
            return False
        self._gate_allow_count += 1
        return True

    def suggest_exit(self, strategy) -> Optional[dict]:
        """Volatility-based abort governed by the active genome.

        Same formula as IslandPilot so the two pipelines abort on identical
        triggers — the only difference is how the aggressiveness parameter is
        chosen (per-regime vs. flat walk-forward).
        """
        if self._active_genome is None:
            return None
        aggressiveness = float(self._active_genome.get('abort_aggressiveness', 0.2))
        threshold = 1.0 - aggressiveness
        danger = self._compute_danger(strategy)
        if danger > threshold:
            self._abort_count += 1
            return {'action': 'close_all'}
        return None

    def on_cycle_end(self, pnl: float, strategy) -> None:
        """Record (pnl, active_genome) so the rolling GA can score genomes."""
        # Deduplicate via session_number (IslandPilot pattern)
        sn = getattr(strategy, 'vars', {}).get('session_number') if strategy else None
        if sn is not None and sn == self._last_recorded_session:
            return
        self._last_recorded_session = sn

        self._cycle_count += 1
        cycle_id = sn if sn is not None else self._cycle_count

        # Detect bust from strategy vars if available
        is_bust = False
        if strategy and hasattr(strategy, 'vars'):
            is_bust = bool(strategy.vars.get('last_session_bust', False))

        # Record into rolling buffer (gene snapshot, not reference)
        active_genes = dict(self._active_genome) if self._active_genome else {}
        self._cycle_buffer.append({
            'cycle': cycle_id,
            'pnl': float(pnl) if pnl is not None else 0.0,
            'bust': is_bust,
            'candle': self._candle_count,
            'genes': active_genes,
        })

        # Trim buffer to the trailing window (by candles, not by cycle count).
        window_candles = self.cfg['retrain']['interval_candles']
        min_candle = self._candle_count - window_candles
        self._cycle_buffer = [
            e for e in self._cycle_buffer if e['candle'] >= min_candle
        ]

        # Log per-cycle HP snapshot for the UI audit table
        entry: Dict[str, Any] = {
            'cycle': cycle_id,
            'candle': self._candle_count,
            'pnl': round(float(pnl), 4) if pnl is not None else 0.0,
            'bust': is_bust,
        }
        if active_genes:
            entry['genes'] = {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in active_genes.items()
                if isinstance(v, (int, float, str, bool))
            }
        self._cycle_hp_log.append(entry)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_position_open(self, strategy) -> bool:
        if hasattr(strategy, 'position') and hasattr(strategy.position, 'is_open'):
            return bool(strategy.position.is_open)
        if hasattr(strategy, 'vars') and strategy.vars.get('cycle_active'):
            return True
        return False

    def _init_ga_from_strategy(self, strategy) -> None:
        """Build the GA + seed population by inspecting the strategy."""
        try:
            self._bounds = build_gene_bounds_from_strategy(strategy)
        except Exception:
            return

        if not self._bounds:
            return

        ga_cfg = self.cfg['ga']
        self._ga = WalkForwardGA(
            bounds=self._bounds,
            population_size=ga_cfg['population_size'],
            elitism=ga_cfg['elitism_count'],
            crossover_rate=ga_cfg['crossover_rate'],
            mutation_rate=ga_cfg['mutation_rate'],
            mutation_sigma=ga_cfg['mutation_sigma_pct'],
            tournament_k=ga_cfg['tournament_k'],
            seed=ga_cfg['seed'],
        )

        # If we have a shipped seed population, inject it.
        if self._initial_population_seed:
            try:
                seeded = [
                    Genome.from_dict(gd, bounds=self._bounds)
                    for gd in self._initial_population_seed
                ]
                # Keep up to population_size; top up with fresh random genomes.
                pop_size = self._ga.population_size
                self._ga.population = (seeded[:pop_size] + self._ga.population)[:pop_size]
            except Exception:
                pass

        # Seed _active_genome with population mean so we never run naked
        best = self._ga.best()
        if best is not None and best.genes:
            self._active_genome = dict(best.genes)

    def _try_load_seed_population(self) -> None:
        """Optional: load a pre-trained initial population from disk."""
        if not os.path.exists(_INITIAL_POP_PATH):
            return
        try:
            with open(_INITIAL_POP_PATH) as f:
                data = json.load(f)
            self._initial_population_seed = data.get('population', data)
        except Exception:
            self._initial_population_seed = None

    def _run_retrain(self) -> None:
        """Run the GA on the current cycle buffer and adopt the best genome."""
        if self._ga is None or self._bounds is None:
            return

        retrain_cfg = self.cfg['retrain']
        ga_cfg = self.cfg['ga']
        fitness_cfg = self.cfg['fitness']

        if len(self._cycle_buffer) < retrain_cfg['min_cycles_for_retrain']:
            # Record that we skipped a retrain for UI transparency
            self._retrain_log.append({
                'candle': self._candle_count,
                'cycles_in_buffer': len(self._cycle_buffer),
                'skipped': True,
                'reason': 'insufficient_cycles',
            })
            return

        # Build fitness_fn closure over the frozen buffer snapshot
        buffer_snapshot = list(self._cycle_buffer)
        radius = self.cfg['fitness_radius']
        min_similar = self.cfg['fitness_min_similar']
        fallback = self.cfg['initial_noise_fitness']

        def fitness_fn(genes: dict) -> float:
            return score_from_buffer(
                genes=genes,
                buffer=buffer_snapshot,
                bounds=self._bounds,
                radius=radius,
                min_similar=min_similar,
                fitness_weights=fitness_cfg,
                fallback=fallback,
            )

        # Run GA for N generations
        gen_stats: List[dict] = []
        def _log(gen_idx: int, stats: dict) -> None:
            gen_stats.append({'gen': gen_idx, **stats})

        self._ga.run(fitness_fn, generations=ga_cfg['generations_per_retrain'], log_fn=_log)

        # Adopt the best genome as the new active config
        best = self._ga.best()
        new_genes = dict(best.genes) if best and best.genes else None
        prev = self._active_genome
        self._active_genome = new_genes

        self._retrain_count += 1

        self._retrain_log.append({
            'candle': self._candle_count,
            'retrain_id': self._retrain_count,
            'cycles_in_buffer': len(buffer_snapshot),
            'generations_run': ga_cfg['generations_per_retrain'],
            'best_fitness': round(best.fitness, 4) if best and best.fitness is not None else None,
            'prev_genes': {k: (round(v, 4) if isinstance(v, float) else v)
                           for k, v in (prev or {}).items()
                           if isinstance(v, (int, float, str, bool))},
            'new_genes': {k: (round(v, 4) if isinstance(v, float) else v)
                          for k, v in (new_genes or {}).items()
                          if isinstance(v, (int, float, str, bool))},
            'gen_stats': gen_stats,
            'skipped': False,
        })

        # Flat fitness history for convergence charting
        if gen_stats:
            for gs in gen_stats:
                self._fitness_history.append({
                    'retrain': self._retrain_count,
                    'gen': gs['gen'],
                    'best': gs['best'],
                    'mean': gs['mean'],
                })

    def _apply_genome(self, strategy, genome: dict) -> None:
        """Apply genome to strategy HP — discovered dynamically at runtime.

        Mirrors IslandPilot._apply_genome so both pipelines drive the strategy
        through the same keyhole.
        """
        if not hasattr(strategy, 'hp') or not hasattr(strategy, 'hyperparameters'):
            return

        if self._hp_spec is None:
            try:
                hp_list = strategy.hyperparameters()
                self._hp_spec = {h['name']: h for h in hp_list
                                 if isinstance(h, dict) and 'name' in h}
            except Exception:
                self._hp_spec = {}

        if not self._hp_spec:
            return

        hp = strategy.hp
        for hp_name, spec in self._hp_spec.items():
            group = spec.get('group', '')
            if group not in _TUNABLE_GROUPS:
                continue
            if hp_name not in genome:
                continue

            val = genome[hp_name]
            hp_type = spec.get('type')

            if hp_type == 'categorical':
                options = spec.get('options', [])
                safe = _SAFE_OPTIONS.get(hp_name)
                if safe:
                    options = [o for o in options if o in safe]
                if not options:
                    continue
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    idx = int(round(val))
                    idx = max(0, min(idx, len(options) - 1))
                    hp[hp_name] = options[idx]
                elif val in options:
                    hp[hp_name] = val
            elif hp_type in (int, float) or hp_type in ('int', 'float'):
                try:
                    lo = spec.get('min', float('-inf'))
                    hi = spec.get('max', float('inf'))
                    numeric = max(lo, min(hi, float(val)))
                    if hp_type in (int, 'int'):
                        numeric = int(round(numeric))
                    hp[hp_name] = numeric
                except (TypeError, ValueError):
                    continue

    def _compute_danger(self, strategy) -> float:
        candles = getattr(strategy, 'candles', None)
        if candles is None or len(candles) < 20:
            return 0.0
        closes = candles[-20:, 2]
        if closes[0] == 0:
            return 0.0
        returns = np.diff(closes) / (closes[:-1] + 1e-12)
        vol = float(np.std(returns))
        return float(np.clip(vol / 0.01, 0.0, 1.0))

    # ------------------------------------------------------------------
    # Stats & UI
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        total_gate = self._gate_allow_count + self._gate_block_count
        interval = self.cfg['retrain']['interval_candles']
        candles_since = self._candle_count - self._last_retrain_candle
        next_retrain_in = max(0, interval - candles_since) if self._ga is not None else interval

        # Current genome (serializable snapshot)
        current_genome = None
        if self._active_genome:
            current_genome = {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in self._active_genome.items()
                if isinstance(v, (int, float, str, bool))
            }

        population_summary = None
        if self._ga is not None:
            fitnesses = [g.fitness for g in self._ga.population if g.fitness is not None]
            population_summary = {
                'size': len(self._ga.population),
                'generation': self._ga.generation,
                'best_fitness': round(max(fitnesses), 4) if fitnesses else None,
                'mean_fitness': round(float(np.mean(fitnesses)), 4) if fitnesses else None,
                'evaluated': len(fitnesses),
            }

        stats: Dict[str, Any] = {
            'candle_count': self._candle_count,
            'cycle_count': self._cycle_count,
            'retrain_count': self._retrain_count,
            'last_retrain_candle': self._last_retrain_candle,
            'next_retrain_in_candles': next_retrain_in,
            'buffer_size': len(self._cycle_buffer),
            'entries_allowed': self._gate_allow_count,
            'entries_blocked': self._gate_block_count,
            'total_gate_checks': total_gate,
            'block_rate': round(self._gate_block_count / total_gate, 4) if total_gate else 0.0,
            'aborts_triggered': self._abort_count,
            'has_genome': self._active_genome is not None,
            'current_genome': current_genome,
            'population': population_summary,
            'fitness_history': self._fitness_history[-200:],   # cap for transport
            'retrain_log': self._retrain_log[-50:],            # cap for transport
            'cycle_hp_log': self._cycle_hp_log[-500:],
        }
        stats['_ui'] = self.ui_metadata()
        return stats

    def ui_metadata(self) -> dict:
        return {
            'badges': [
                {'label': self.name, 'color': 'brand'},
                {'label': f'Retrains: {self._retrain_count}', 'color': 'surface'},
                {'label': 'Genome active' if self._active_genome else 'No genome',
                 'color': 'green' if self._active_genome else 'red'},
                {'label': f'Buffer: {len(self._cycle_buffer)} cycles', 'color': 'surface'},
            ],
            'metric_cards': [
                {'label': 'Retrains', 'key': 'retrain_count', 'format': 'int', 'icon': 'chart',
                 'tooltip': 'Completed walk-forward re-optimisations'},
                {'label': 'Next retrain in', 'key': 'next_retrain_in_candles', 'format': 'int',
                 'icon': 'chart',
                 'tooltip': 'Candles remaining until next quarterly re-optimisation'},
                {'label': 'Buffer cycles', 'key': 'buffer_size', 'format': 'int',
                 'icon': 'chart',
                 'tooltip': 'Cycles retained in the trailing fitness window'},
                {'label': 'Aborts triggered', 'key': 'aborts_triggered', 'format': 'int',
                 'color': 'amber', 'icon': 'block',
                 'tooltip': 'Volatility-driven emergency exits'},
                {'label': 'Entries blocked', 'key': 'block_rate', 'format': 'pct',
                 'color': 'amber', 'icon': 'block',
                 'sub_template': '{entries_blocked} / {total_gate_checks}',
                 'tooltip': 'Gate-entry rejection rate (warmup only)'},
                {'label': 'Cycles completed', 'key': 'cycle_count', 'format': 'int', 'icon': 'chart',
                 'tooltip': 'Total completed trading cycles'},
            ],
            'sections': [
                {
                    'type': 'kv_pairs',
                    'title': 'Current Genome',
                    'data_key': 'current_genome',
                    'show_if': 'current_genome',
                    'empty_message': 'GA has not produced a genome yet.',
                    'auto_items': True,
                    'grid': 'full',
                },
                {
                    'type': 'kv_pairs',
                    'title': 'Population',
                    'data_key': 'population',
                    'show_if': 'population',
                    'empty_message': 'GA not yet initialised.',
                    'auto_items': True,
                    'grid': 'full',
                },
                {
                    'type': 'audit_table',
                    'title': 'Retrain Log',
                    'data_key': 'retrain_log',
                    'empty_message': 'No retrains yet. First retrain fires after warmup + 90 days.',
                    'columns': [
                        {'key': 'retrain_id', 'label': '#', 'format': 'int'},
                        {'key': 'candle', 'label': 'Candle', 'format': 'int'},
                        {'key': 'cycles_in_buffer', 'label': 'Cycles', 'format': 'int'},
                        {'key': 'generations_run', 'label': 'Gens', 'format': 'int'},
                        {'key': 'best_fitness', 'label': 'Best Fitness', 'format': 'dec4'},
                        {'key': 'skipped', 'label': 'Skipped', 'format': 'bool'},
                    ],
                    'max_items': 50,
                },
                {
                    'type': 'line_chart',
                    'title': 'Fitness Convergence',
                    'data_key': 'fitness_history',
                    'show_if': 'fitness_history',
                    'empty_message': 'Fitness history populated after first retrain.',
                    'x_key': 'gen',
                    'series': [
                        {'key': 'best', 'label': 'Best'},
                        {'key': 'mean', 'label': 'Mean'},
                    ],
                },
                {
                    'type': 'audit_table',
                    'title': 'Cycle HP Log',
                    'data_key': 'cycle_hp_log',
                    'empty_message': 'No cycles completed yet.',
                    'columns': [
                        {'key': 'cycle', 'label': 'Cycle', 'format': 'int'},
                        {'key': 'candle', 'label': 'Candle', 'format': 'int'},
                        {'key': 'pnl', 'label': 'PnL', 'format': 'dec4'},
                        {'key': 'bust', 'label': 'Bust', 'format': 'bool'},
                    ],
                    'max_items': 200,
                },
            ],
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_state(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)
        state = {
            'cfg': self.cfg,
            'candle_count': self._candle_count,
            'last_retrain_candle': self._last_retrain_candle,
            'retrain_count': self._retrain_count,
            'cycle_count': self._cycle_count,
            'active_genome': self._active_genome,
            'cycle_buffer': self._cycle_buffer[-2000:],  # cap for disk size
            'fitness_history': self._fitness_history[-2000:],
            'retrain_log': self._retrain_log[-200:],
            'cycle_hp_log': self._cycle_hp_log[-2000:],
            'ga': self._ga.to_dict() if self._ga is not None else None,
        }
        with open(os.path.join(path, 'state.json'), 'w') as f:
            json.dump(state, f, indent=2, default=str)

    def load_state(self, path: str) -> None:
        state_path = os.path.join(path, 'state.json')
        if not os.path.exists(state_path):
            return
        try:
            with open(state_path) as f:
                state = json.load(f)
        except Exception:
            return

        self._candle_count = state.get('candle_count', 0)
        self._last_retrain_candle = state.get('last_retrain_candle', 0)
        self._retrain_count = state.get('retrain_count', 0)
        self._cycle_count = state.get('cycle_count', 0)
        self._active_genome = state.get('active_genome')
        self._cycle_buffer = state.get('cycle_buffer', [])
        self._fitness_history = state.get('fitness_history', [])
        self._retrain_log = state.get('retrain_log', [])
        self._cycle_hp_log = state.get('cycle_hp_log', [])

        ga_data = state.get('ga')
        if ga_data:
            try:
                self._ga = WalkForwardGA.from_dict(ga_data)
                self._bounds = self._ga.bounds
            except Exception:
                self._ga = None

    @classmethod
    def default_config(cls) -> dict:
        return merge_config({})

    @classmethod
    def architecture(cls) -> dict:
        """Rich metadata for the frontend Pipeline Architecture tab."""
        has_seed = os.path.exists(_INITIAL_POP_PATH)
        return {
            'name': 'DempsterJonesPilot',
            'summary': 'Flat walk-forward genetic-algorithm pipeline — re-optimises '
                       'strategy parameters every ~90 trading days using a single '
                       'population, with no regime conditioning. Classical baseline '
                       'for comparisons against regime-aware pipelines.',
            'designed_for': ['Martingale', 'SurefireHedge variants'],
            'research_basis': 'Dempster & Jones (2001), "A real-time adaptive trading '
                              'system using genetic programming," Quantitative Finance 1(4), 397-413.',
            'paper_citation': 'Dempster, M. A. H., & Jones, C. M. (2001). '
                              'A real-time adaptive trading system using genetic programming. '
                              'Quantitative Finance, 1(4), 397-413.',
            'requires_training': False,
            'training_status': 'seeded' if has_seed else 'cold_start',
            'training_description': 'Optional: run the offline seeding script to give '
                                    'the GA a warm starting population. Pipeline will '
                                    'self-optimise online from the first retrain otherwise.',
            'training_steps': [
                'Optional: run notebooks/phase5/51_dempster_jones_train.py',
                'Script produces pipelines/_shared/DempsterJonesPilot/models/initial_population.json',
                'Pipeline auto-loads the seed population on construction.',
            ],
            'layers': [
                {
                    'name': 'WalkForwardGA',
                    'order': 1,
                    'type': 'optimizer',
                    'hook': 'on_before()',
                    'description': 'Single-population GA that re-optimises strategy HPs every '
                                   '~90 trading days on the trailing cycle-outcome buffer.',
                    'algorithm': 'Tournament selection (k=3), uniform crossover, Gaussian mutation, elitism.',
                    'output': 'Best genome applied to strategy HP between cycles.',
                    'config_keys': {
                        'population_size': 'GA population size (default: 20)',
                        'generations_per_retrain': 'Generations per retrain (default: 10)',
                        'crossover_rate': 'Uniform crossover rate (default: 0.7)',
                        'mutation_rate': 'Gaussian mutation probability (default: 0.2)',
                        'mutation_sigma_pct': 'Mutation stdev as % of range (default: 0.05)',
                        'elitism_count': 'Top-N survivors per generation (default: 2)',
                    },
                },
                {
                    'name': 'RollingFitnessBuffer',
                    'order': 2,
                    'type': 'fitness_estimator',
                    'hook': 'on_cycle_end()',
                    'description': 'Maintains the last 90 days of (pnl, genes) cycle records. '
                                   'Scoring uses gene-space L2 proximity + cycle PF/DD/bust aggregation.',
                    'algorithm': 'Local-neighbourhood fitness score (falls back to global buffer if sparse).',
                    'output': 'Fitness in [-inf, +inf] using the IslandPilot composite formula.',
                    'config_keys': {
                        'fitness_radius': 'Normalised gene-distance cut-off (default: 0.25)',
                        'fitness_min_similar': 'Minimum matched cycles before local score applies (default: 3)',
                        'rolling_window_days': 'Trailing window for fitness estimation (default: 90 days)',
                    },
                },
                {
                    'name': 'VolatilityAbort',
                    'order': 3,
                    'type': 'exit_controller',
                    'hook': 'suggest_exit()',
                    'description': 'Simple close-to-close vol danger signal — aborts when danger '
                                   'exceeds (1 - genome.abort_aggressiveness). Same kernel as IslandPilot.',
                    'algorithm': 'Standard deviation of recent 20-bar log returns, normalised to [0, 1].',
                    'output': 'suggest_exit action "close_all" when triggered.',
                },
            ],
            'lifecycle': [
                {'hook': 'on_before()', 'description': 'Count candles → if quarterly boundary reached '
                                                       'and no position open, run GA retrain → apply best genome'},
                {'hook': 'gate_entry()', 'description': 'Block only during warmup — no regime filtering'},
                {'hook': 'suggest_exit()', 'description': 'Abort on volatility spike using genome-tuned threshold'},
                {'hook': 'on_cycle_end()', 'description': 'Append (pnl, genes, cycle) to rolling buffer, '
                                                         'trim older than 90 days'},
            ],
            'composition_rules': {
                'gate_entry': 'AND (always allows outside warmup)',
                'adjust_size': 'Pass-through — sizing governed by the strategy',
                'suggest_exit': 'close_all when vol exceeds genome threshold',
                'filter_order': 'Pass-through',
            },
            'differences_from_islandpilot': [
                'No regime discovery (single population instead of per-regime islands).',
                'No migration between sub-populations.',
                'No hysteresis / regime inferencer (gate is warmup-only).',
                'No adaptive sizer — position sizing stays in the strategy.',
                'Retrains periodically rather than continuously after every cycle.',
            ],
        }
