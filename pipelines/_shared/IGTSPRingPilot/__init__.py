"""
IGTSPRingPilot — island-model genetic algorithm pipeline with RING topology.

This is a baseline pipeline for the IslandPilot comparison study. It uses the
SAME island GA machinery but *without* regime structure. Islands are just
parallel search populations sharing a single global fitness function. Ring
topology migrates each island's best genome to its neighbour every K
generations.

Reference:
    Chideme, K., Chen, C.-H., & Lin, J. C.-W. (2025).
    "Island genetic algorithm with diverse migration strategies for
     efficient group trading strategy portfolio optimization."
    Engineering Optimization. DOI: 10.1080/0305215X.2025.2592030

Runtime behaviour:
  - Every candle, applies the *globally*-best genome to strategy.hp
    (between cycles only — never mid-cycle).
  - On cycle end, records PnL against the currently-active genome and
    a round-robin island id (so observation data fans out across all
    populations over time).
  - Every `evolve_every_n_cycles` cycles, runs one GA step (evaluate →
    tournament/crossover/mutation). Every `migration_interval`
    GA steps, ring-migrates best genomes.

Tuning constraints (identical to IslandPilot for fair comparison):
  - Only 'General', 'Grid / Hedge', and 'Take Profit' HP groups
  - Never change HPs mid-cycle (only when position is closed)
  - Discovers tunable HPs from strategy.hyperparameters() at runtime
"""
import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

from qengine.framework.base import Pipeline
from pipelines._shared.components.island_evolver import (
    GENE_BOUNDS,
    Genome,
    build_gene_bounds_from_strategy,
)

from .config import DEFAULT_CONFIG, merge_config
from .ring_evolver import RingEvolver


_MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')

# Groups allowed for evolution/override (same set IslandPilot uses).
_TUNABLE_GROUPS = {'General', 'Grid / Hedge', 'Take Profit'}

_SAFE_OPTIONS = {
    'signal_mode': {'random', 'ema_cross', 'rsi', 'macd', 'supertrend', 'stoch',
                    'ema_rsi', 'ema_macd', 'triple'},
    'hedge_mode': {'fixed_pips', 'atr_based', 'percentage'},
    'tp_mode': {'fixed_pips', 'atr_based', 'bucket_pct', 'risk_reward'},
    'base_size_mode': {'pct_equity', 'capital_aware'},
    'sizing_curve': {'geometric', 'sqrt', 'linear', 'fibonacci'},
}


class IGTSPRingPilot(Pipeline):
    """Island-GA baseline pipeline with ring-topology migration (no regimes)."""

    name = 'IGTSPRingPilot'

    def __init__(self, config: Optional[dict] = None):
        self.cfg = merge_config(config or {})

        # Dummy leaf ids — islands are NOT regimes.
        n_islands = int(self.cfg['n_islands'])
        self._leaf_ids: List[str] = [f'pop_{i}' for i in range(n_islands)]

        # Build evolver with default gene bounds; strategy-aware bounds get
        # rebuilt the first time we see a strategy in on_before().
        evo = self.cfg['evolution']
        self.evolver: RingEvolver = RingEvolver(
            leaf_ids=self._leaf_ids,
            config={
                'pop_size': int(self.cfg['population_size']),
                'elitism': evo['elitism'],
                'crossover_rate': evo['crossover_rate'],
                'mutation_rate': evo['mutation_rate'],
                'mutation_sigma': evo['mutation_sigma_pct'],
                'tournament_k': evo['tournament_k'],
            },
        )
        self._bounds_initialised_from_strategy = False

        # Runtime state
        self._active_genome: Optional[dict] = None
        self._active_island: Optional[str] = None   # round-robin island id
        self._hp_spec: Optional[Dict[str, dict]] = None
        self._candle_count: int = 0
        self._cycle_count: int = 0
        self._last_recorded_session: Optional[int] = None
        self._ga_steps: int = 0
        self._n_migrations: int = 0

        # Rolling cycle buffers per (island, genome-id)
        self._genome_outcomes: Dict[str, List[float]] = {}
        self._cycle_hp_log: List[dict] = []

        # Pending evaluations — cycles completed since last GA step
        self._cycles_since_step: int = 0

        # Auto-load persisted state if available
        self._load_pretrained()

    # ------------------------------------------------------------------
    # Pipeline hooks
    # ------------------------------------------------------------------

    def on_before(self, strategy) -> None:
        self._candle_count += 1

        # Build strategy-aware gene bounds once; re-init populations so they
        # sample within the discovered ranges.
        if not self._bounds_initialised_from_strategy and strategy is not None:
            self._rebuild_bounds_from_strategy(strategy)

        # Cache HP spec for application
        if self._hp_spec is None and hasattr(strategy, 'hyperparameters'):
            try:
                hp_list = strategy.hyperparameters()
                self._hp_spec = {h['name']: h for h in hp_list
                                 if isinstance(h, dict) and 'name' in h}
            except Exception:
                self._hp_spec = {}

        # Pick globally-best genome (shared across all islands, since fitness
        # is not regime-conditioned).
        gd = self.evolver.get_global_best()
        if gd is None:
            # No evaluations yet — use island-0's current first individual
            pop0 = self.evolver.populations.get(self._leaf_ids[0])
            if pop0 and pop0.individuals:
                self._active_genome = dict(pop0.individuals[0].genes)
            else:
                self._active_genome = None
        else:
            self._active_genome = gd.get('genes', gd)

        # Apply genome only between cycles (never mid-cycle)
        position_open = False
        if hasattr(strategy, 'position') and hasattr(strategy.position, 'is_open'):
            position_open = strategy.position.is_open
        elif hasattr(strategy, 'vars') and strategy.vars.get('cycle_active'):
            position_open = True

        if not position_open and self._active_genome is not None:
            self._apply_genome(strategy, self._active_genome)

    def gate_entry(self, strategy) -> bool:
        # Pure parameter optimiser — allow after warmup; no regime filter.
        if self._candle_count < self.cfg['warmup']:
            return False
        return True

    def on_cycle_end(self, pnl: float, strategy) -> None:
        # Dedupe via session_number
        sn = getattr(strategy, 'vars', {}).get('session_number') if strategy else None
        if sn is not None and sn == self._last_recorded_session:
            return
        self._last_recorded_session = sn

        self._cycle_count += 1
        cycle_id = sn if sn is not None else self._cycle_count

        # Round-robin island assignment so each population gets data.
        n = len(self._leaf_ids)
        island_id = self._leaf_ids[self._cycle_count % n] if n > 0 else None
        self._active_island = island_id

        # Record outcome keyed by island (genome id isn't stable once GA
        # replaces individuals, so we use the island's current best as proxy).
        if island_id is not None:
            buf = self._genome_outcomes.setdefault(island_id, [])
            buf.append(float(pnl))
            max_buf = int(self.cfg['cycle_buffer_size'])
            if len(buf) > max_buf:
                del buf[:-max_buf]

        # HP log snapshot
        if self._active_genome is not None:
            genes = self._active_genome if isinstance(self._active_genome, dict) else {}
            self._cycle_hp_log.append({
                'cycle': cycle_id,
                'island': island_id,
                'genes': {k: round(v, 4) if isinstance(v, float) else v
                          for k, v in genes.items()},
            })

        # Trigger a batch GA step every K cycles.
        self._cycles_since_step += 1
        if self._cycles_since_step >= int(self.cfg['evolve_every_n_cycles']):
            self._run_ga_step()
            self._cycles_since_step = 0

    # ------------------------------------------------------------------
    # GA step using buffered outcomes
    # ------------------------------------------------------------------

    def _run_ga_step(self) -> None:
        """Run one generation across all islands using buffered cycle data.

        Fitness is computed from each island's rolling outcome buffer
        (not per-genome). This is a cheap online approximation —
        offline training uses nested backtests for per-genome evaluation.
        """
        island_fitness = {
            lid: self._fitness_from_outcomes(self._genome_outcomes.get(lid, []))
            for lid in self._leaf_ids
        }

        def fitness_fn(_genes: dict) -> float:
            # Same per-island fitness for every individual currently on the
            # island (cheap online proxy). Offline training overrides this.
            lid = self._active_island or self._leaf_ids[0]
            return island_fitness.get(lid, 0.0)

        # Use the evolver's own step: evaluate → evolve → maybe-migrate.
        prev_mig = len(self.evolver.migration_log)
        self.evolver.step(
            fitness_fn=fitness_fn,
            migration_interval=int(self.cfg['migration_interval']),
        )
        self._ga_steps += 1
        new_mig = len(self.evolver.migration_log) - prev_mig
        if new_mig > 0:
            self._n_migrations += new_mig

    def _fitness_from_outcomes(self, pnls: List[float]) -> float:
        """Composite fitness over a rolling cycle buffer.

        Matches IslandPilot's weighted formula for fair comparison:
            F = 0.4*(PF-1)*100
              + 0.3*max(0, 100-DD*5)
              + 0.2*(1-bust_rate)*100
              + 0.1*min(sessions/100, 1)*100
        """
        if not pnls:
            return 0.0

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        pf = (gross_win / gross_loss) if gross_loss > 0 else (gross_win if gross_win > 0 else 0.0)
        if pf > 100:
            pf = 100.0  # cap for stability

        # Approximate DD% from equity curve over this buffer
        equity = np.cumsum(pnls)
        peak = np.maximum.accumulate(equity)
        # Use 10k starting-balance proxy so DD% is comparable to IslandPilot
        start_balance = 10000.0
        running = start_balance + equity
        running_peak = np.maximum.accumulate(running)
        dd_pct = float(((running_peak - running) / running_peak).max() * 100) if len(running) > 0 else 0.0

        # Heuristic bust: losses below a magnitude floor (same proxy
        # the IslandPilot training uses when strategy bust flag is absent).
        bust_floor = -50.0
        n_busts = sum(1 for p in pnls if p < bust_floor)
        bust_rate = n_busts / len(pnls)

        w = self.cfg['fitness_weights']
        fitness = (
            w['profit_factor'] * (pf - 1.0) * 100
            + w['drawdown'] * max(0.0, 100 - dd_pct * 5)
            + w['bust'] * (1.0 - bust_rate) * 100
            + w['sessions'] * min(len(pnls) / 100.0, 1.0) * 100
        )
        return float(fitness)

    # ------------------------------------------------------------------
    # Strategy genome application (same rules as IslandPilot)
    # ------------------------------------------------------------------

    def _rebuild_bounds_from_strategy(self, strategy) -> None:
        """Re-create populations using strategy-discovered gene bounds.

        Called once at the first on_before() that sees a strategy, so we
        sample genes within the strategy's actual HP ranges.
        """
        try:
            bounds = build_gene_bounds_from_strategy(strategy)
        except Exception:
            bounds = dict(GENE_BOUNDS)

        if bounds and bounds != self.evolver.gene_bounds:
            evo = self.cfg['evolution']
            self.evolver = RingEvolver(
                leaf_ids=self._leaf_ids,
                config={
                    'pop_size': int(self.cfg['population_size']),
                    'elitism': evo['elitism'],
                    'crossover_rate': evo['crossover_rate'],
                    'mutation_rate': evo['mutation_rate'],
                    'mutation_sigma': evo['mutation_sigma_pct'],
                    'tournament_k': evo['tournament_k'],
                },
                gene_bounds=bounds,
            )

        self._bounds_initialised_from_strategy = True

    def _apply_genome(self, strategy, genome: dict) -> None:
        """Apply evolved genome to strategy HP. Mirrors IslandPilot rules.

        Only 'General', 'Grid / Hedge', and 'Take Profit' groups are touched.
        """
        if not hasattr(strategy, 'hp') or self._hp_spec is None or not self._hp_spec:
            return

        hp = strategy.hp
        for hp_name, spec in self._hp_spec.items():
            if spec.get('group') not in _TUNABLE_GROUPS:
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
                if isinstance(val, (int, float)):
                    idx = int(round(val))
                    idx = max(0, min(idx, len(options) - 1))
                    hp[hp_name] = options[idx]
                elif val in options:
                    hp[hp_name] = val
            elif hp_type in (int, float) or hp_type in ('int', 'float'):
                lo = spec.get('min', float('-inf'))
                hi = spec.get('max', float('inf'))
                try:
                    val = max(lo, min(hi, float(val)))
                except (TypeError, ValueError):
                    continue
                if hp_type in (int, 'int'):
                    val = int(round(val))
                hp[hp_name] = val

    # ------------------------------------------------------------------
    # Stats & UI metadata
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        fitness_summary = self.evolver.get_fitness_summary()
        diversity = self.evolver.get_diversity_stats()

        best_overall = -float('inf')
        best_island = None
        for lid, s in fitness_summary.items():
            if s.get('best') is not None and s['best'] > best_overall:
                best_overall = s['best']
                best_island = lid

        per_island_table = []
        for lid in self._leaf_ids:
            s = fitness_summary.get(lid, {})
            buf = self._genome_outcomes.get(lid, [])
            per_island_table.append({
                'island': lid,
                'best': s.get('best'),
                'mean': s.get('mean'),
                'std': s.get('std'),
                'cycles_observed': len(buf),
            })

        gb = self.evolver.get_global_best()
        current_best_genes = gb.get('genes', {}) if gb else {}

        return {
            'n_islands': len(self._leaf_ids),
            'population_size': int(self.cfg['population_size']),
            'candle_count': self._candle_count,
            'cycle_count': self._cycle_count,
            'ga_steps': self._ga_steps,
            'migrations': self._n_migrations,
            'migration_topology': 'ring',
            'current_best_fitness': (round(best_overall, 4)
                                     if best_overall > -float('inf') else None),
            'current_best_island': best_island,
            'current_best_genes': {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in current_best_genes.items()
            },
            'per_island': per_island_table,
            'fitness_summary': fitness_summary,
            'diversity': diversity,
            'active_island': self._active_island,
            'active_genome': self._active_genome,
            'cycle_hp_log': self._cycle_hp_log[-200:],
            '_ui': self.ui_metadata(),
        }

    def ui_metadata(self) -> dict:
        return {
            'badges': [
                {'label': self.name, 'color': 'brand'},
                {'label': f'{len(self._leaf_ids)} islands', 'color': 'surface'},
                {'label': 'ring topology', 'color': 'amber'},
                {'label': 'no regimes', 'color': 'surface'},
            ],
            'metric_cards': [
                {'label': 'Islands', 'key': 'n_islands', 'format': 'int', 'icon': 'chart',
                 'tooltip': 'Number of parallel GA populations'},
                {'label': 'Cycles', 'key': 'cycle_count', 'format': 'int', 'icon': 'chart',
                 'tooltip': 'Total trading cycles observed'},
                {'label': 'GA Steps', 'key': 'ga_steps', 'format': 'int', 'icon': 'chart',
                 'tooltip': 'Generations evolved since start'},
                {'label': 'Best Fitness', 'key': 'current_best_fitness', 'format': 'dec4',
                 'icon': 'chart',
                 'tooltip': 'Best fitness across all islands (global)'},
                {'label': 'Migrations', 'key': 'migrations', 'format': 'int', 'icon': 'chart',
                 'tooltip': 'Ring-topology genome transfers'},
                {'label': 'Best Island', 'key': 'current_best_island', 'format': 'text',
                 'icon': 'chart',
                 'tooltip': 'Population holding the current global best'},
            ],
            'sections': [
                {
                    'type': 'kv_table',
                    'title': 'Per-Island Fitness (ring topology)',
                    'data_key': 'per_island',
                    'columns': [
                        {'key': 'island', 'label': 'Island'},
                        {'key': 'best', 'label': 'Best', 'format': 'dec4'},
                        {'key': 'mean', 'label': 'Mean', 'format': 'dec4'},
                        {'key': 'std', 'label': 'Std', 'format': 'dec4'},
                        {'key': 'cycles_observed', 'label': 'Cycles', 'format': 'int'},
                    ],
                    'max_items': 32,
                    'sort_key': 'best',
                    'sort_desc': True,
                    'hide_empty': False,
                    'empty_message': 'No island data yet.',
                },
                {
                    'type': 'kv_pairs',
                    'title': 'Current Global-Best Genome',
                    'data_key': 'current_best_genes',
                    'auto_items': True,
                    'grid': 'full',
                    'empty_message': 'No genome evaluated yet.',
                },
            ],
            # Hint to frontend to render a ring diagram: ordered list of islands
            'ring_order': list(self._leaf_ids),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_state(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)
        self.evolver.save(os.path.join(path, 'evolver.json'))

        runtime = {
            'candle_count': self._candle_count,
            'cycle_count': self._cycle_count,
            'ga_steps': self._ga_steps,
            'n_migrations': self._n_migrations,
            'leaf_ids': self._leaf_ids,
            'genome_outcomes': self._genome_outcomes,
        }
        with open(os.path.join(path, 'runtime.json'), 'w') as f:
            json.dump(runtime, f, indent=2)

    def load_state(self, path: str) -> None:
        evolver_path = os.path.join(path, 'evolver.json')
        if os.path.exists(evolver_path):
            try:
                self.evolver = RingEvolver.load(evolver_path)
                self._leaf_ids = list(self.evolver.leaf_ids)
                self._bounds_initialised_from_strategy = True
            except Exception:
                pass

        runtime_path = os.path.join(path, 'runtime.json')
        if os.path.exists(runtime_path):
            try:
                with open(runtime_path) as f:
                    runtime = json.load(f)
                self._candle_count = runtime.get('candle_count', 0)
                self._cycle_count = runtime.get('cycle_count', 0)
                self._ga_steps = runtime.get('ga_steps', 0)
                self._n_migrations = runtime.get('n_migrations', 0)
                if 'leaf_ids' in runtime:
                    self._leaf_ids = runtime['leaf_ids']
                self._genome_outcomes = {
                    k: list(v) for k, v in runtime.get('genome_outcomes', {}).items()
                }
            except Exception:
                pass

    def _load_pretrained(self) -> None:
        """Auto-load pre-trained ring-evolver state if present."""
        evolver_path = os.path.join(_MODELS_DIR, 'evolver.json')
        if os.path.exists(evolver_path):
            try:
                self.evolver = RingEvolver.load(evolver_path)
                self._bounds_initialised_from_strategy = True
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Class-level config / architecture
    # ------------------------------------------------------------------

    @classmethod
    def default_config(cls) -> dict:
        return merge_config({})

    @classmethod
    def architecture(cls) -> dict:
        return {
            'name': 'IGTSPRingPilot',
            'summary': ('Baseline island-GA pipeline with RING-topology migration. '
                        'Parallel populations optimise ONE global fitness — no regime '
                        'structure. Used as a control for the IslandPilot study.'),
            'designed_for': ['Martingale', 'SurefireHedge variants'],
            'research_basis': ('Chideme, Chen & Lin (2025), Engineering Optimization, '
                               'DOI: 10.1080/0305215X.2025.2592030'),
            'requires_training': True,
            'training_status': (
                'trained' if os.path.exists(os.path.join(_MODELS_DIR, 'evolver.json'))
                else 'untrained'
            ),
            'training_description': ('Offline: 8 islands × 10 individuals, nested real-engine '
                                     'backtests, ring migration every 5 generations.'),
            'training_steps': [
                'Seed 8 populations with random genomes in strategy HP bounds',
                'Evaluate every genome via a real-engine backtest',
                'Tournament selection + uniform crossover + gaussian mutation',
                'Every 5 generations: ring-migrate best genome pop_i → pop_{(i+1)%N}',
                'Persist global best + island populations to disk',
            ],
            'layers': [
                {
                    'name': 'RingEvolver',
                    'order': 1,
                    'type': 'optimizer',
                    'hook': 'on_cycle_end()',
                    'description': ('Island-model GA with ring migration. '
                                    'pop_i → pop_{(i+1) % N} every K generations.'),
                    'algorithm': ('Tournament selection, uniform crossover, gaussian mutation, '
                                  'elitism, ring-topology migration.'),
                    'output': 'Global-best genome across all islands',
                    'config_keys': {
                        'n_islands': 'Parallel populations (default: 8)',
                        'population_size': 'Individuals per island (default: 10)',
                        'migration_interval': 'Generations between migrations (default: 5)',
                        'evolve_every_n_cycles': 'Cycles between GA steps (default: 30)',
                    },
                },
                {
                    'name': 'GlobalBestApplier',
                    'order': 2,
                    'type': 'applier',
                    'hook': 'on_before()',
                    'description': ('Between cycles, writes the global-best genome into '
                                    'strategy.hp for groups General, Grid/Hedge, Take Profit.'),
                    'algorithm': 'Type-checked HP override with bounds enforcement.',
                    'output': 'Mutated strategy.hp dict',
                },
            ],
            'lifecycle': [
                {'hook': 'on_before()', 'description': 'Apply global-best genome (between cycles only).'},
                {'hook': 'gate_entry()', 'description': 'Pass-through after warmup — no regime gating.'},
                {'hook': 'on_cycle_end()', 'description': 'Buffer outcome; every K cycles run GA step + possibly migrate.'},
            ],
            'composition_rules': {
                'gate_entry': 'AND with other pipelines in the stack.',
                'adjust_size': 'Pass-through (strategy owns sizing).',
                'suggest_exit': 'None (pipeline is a pure parameter optimiser).',
                'filter_order': 'Pass-through.',
            },
        }
