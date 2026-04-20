"""
RollingGA — single-population GA with rolling-window outcome scoring.

Wraps the IslandPilot `Population`/`Genome` primitives but swaps the
fitness-function model: instead of evaluating every individual against a
callable, genomes are scored retrospectively from a rolling buffer of
trading outcomes tagged with the genome that was active at the time.

Fitness composite (matches IslandPilot's real-engine recipe):

    F = 0.4*(PF-1)*100
      + 0.3*max(0, 100 - DD*5)
      + 0.2*(1 - bust_rate)*100
      + 0.1*min(sessions/100, 1)*100

A genome is scored from its own rolling cycle outcomes if present; missing
or too-sparse outcomes fall back to the population-wide composite so an
untested genome isn't unfairly penalised.
"""

from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

from qengine.framework.components.island_evolver import (
    GENE_BOUNDS,
    Genome,
    Population,
)


# ---------------------------------------------------------------------------
# Fitness
# ---------------------------------------------------------------------------

def compute_fitness(outcomes: List[dict]) -> float:
    """Composite fitness over a list of per-cycle outcomes.

    Each outcome: {'pnl': float, 'bust': bool, 'peak_dd': float (optional)}
    """
    if not outcomes:
        return -50.0

    sessions = len(outcomes)
    pnls = [o['pnl'] for o in outcomes]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss > 1e-9:
        pf = gross_win / gross_loss
    else:
        pf = gross_win + 1.0 if gross_win > 0 else 0.0

    # Max drawdown from running-sum equity curve (in units of PnL — proxy)
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    dd_series = peak - equity
    max_dd = float(np.max(dd_series)) if len(dd_series) else 0.0
    # Normalise DD by mean absolute cycle PnL to get a unitless "DD%"
    scale = np.mean(np.abs(pnls)) + 1e-9
    dd_pct = min(100.0, 100.0 * max_dd / max(scale, 1e-6))

    busts = sum(1 for o in outcomes if o.get('bust'))
    bust_rate = busts / sessions if sessions else 0.0

    return (
        0.4 * (pf - 1.0) * 100.0
        + 0.3 * max(0.0, 100.0 - dd_pct * 5.0)
        + 0.2 * (1.0 - bust_rate) * 100.0
        + 0.1 * min(sessions / 100.0, 1.0) * 100.0
    )


# ---------------------------------------------------------------------------
# RollingGA
# ---------------------------------------------------------------------------

class RollingGA:
    """Single-population GA keyed to rolling cycle outcomes.

    Not thread-safe. One instance per pipeline.
    """

    def __init__(
        self,
        gene_bounds: Optional[Dict] = None,
        population_size: int = 30,
        rolling_window_cycles: int = 120,
        elitism: int = 2,
        seed: Optional[int] = None,
    ):
        self.gene_bounds = gene_bounds or GENE_BOUNDS
        self.population_size = population_size
        self.rolling_window_cycles = rolling_window_cycles
        self.elitism = elitism

        self.population = Population(
            island_id='cga',
            size=population_size,
            seed=seed,
            gene_bounds=self.gene_bounds,
        )

        # Per-genome rolling outcome buffer
        self._outcomes: Dict[str, Deque[dict]] = {
            g.id: deque(maxlen=rolling_window_cycles)
            for g in self.population.individuals
        }

        # Global (whole-population) rolling buffer — used as a prior for
        # newly-minted genomes that have no history.
        self._global_outcomes: Deque[dict] = deque(maxlen=rolling_window_cycles * 4)

        # Active genome pointer — updated by pipeline.on_before between cycles.
        self.active_genome_id: Optional[str] = None
        self.generation = 0

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_active_genome(self) -> Optional[Genome]:
        """Return the Genome with the highest fitness (or a warm default)."""
        fitness_known = [g for g in self.population.individuals if g.fitness is not None]
        if fitness_known:
            best = max(fitness_known, key=lambda g: g.fitness)
        else:
            best = self.population.individuals[0]
        self.active_genome_id = best.id
        return best

    def get_best_genome_dict(self) -> dict:
        g = self.get_active_genome()
        return g.to_dict() if g else {}

    def fitness_std(self) -> float:
        vals = [g.fitness for g in self.population.individuals if g.fitness is not None]
        return float(np.std(vals)) if len(vals) > 1 else 0.0

    def best_fitness(self) -> float:
        vals = [g.fitness for g in self.population.individuals if g.fitness is not None]
        return float(max(vals)) if vals else -999.0

    # ------------------------------------------------------------------
    # Outcome recording
    # ------------------------------------------------------------------

    def record_outcome(self, genome_id: Optional[str], pnl: float, bust: bool = False) -> None:
        """Attach a cycle outcome to the genome that was active at the time."""
        rec = {'pnl': float(pnl), 'bust': bool(bust)}
        self._global_outcomes.append(rec)
        if genome_id and genome_id in self._outcomes:
            self._outcomes[genome_id].append(rec)

    # ------------------------------------------------------------------
    # Retrain (one GA generation)
    # ------------------------------------------------------------------

    def retrain(
        self,
        mutation_sigma: float,
        crossover_rate: float,
        tournament_k: int,
        mutation_rate: float = 0.2,
    ) -> Tuple[float, float]:
        """Score the current population and advance one generation.

        Returns (best_fitness, fitness_std) AFTER scoring, BEFORE evolve —
        i.e. reflecting the just-closed window.
        """
        # --- 1. Score each individual from its rolling window ---
        global_outcomes = list(self._global_outcomes)
        global_fitness = compute_fitness(global_outcomes) if global_outcomes else -50.0
        min_cycles_for_own_fitness = 8

        for g in self.population.individuals:
            own = list(self._outcomes.get(g.id, []))
            if len(own) >= min_cycles_for_own_fitness:
                g.fitness = compute_fitness(own)
            else:
                # Blend: new genomes inherit the global baseline so they're
                # neither rewarded nor punished for their absence.
                g.fitness = global_fitness

        best = self.best_fitness()
        std = self.fitness_std()

        # --- 2. Evolve one generation ---
        prev_ids = {g.id for g in self.population.individuals}
        self.population.evolve(
            elitism=self.elitism,
            crossover_rate=crossover_rate,
            mutation_rate=mutation_rate,
            mutation_sigma=mutation_sigma,
            tournament_k=tournament_k,
        )

        # --- 3. Re-index outcome buffers to current genome ids ---
        # Keep buffers for any surviving (elite / cloned) genome; spawn fresh
        # buffers for new children.
        new_buffers: Dict[str, Deque[dict]] = {}
        for g in self.population.individuals:
            if g.id in self._outcomes:
                new_buffers[g.id] = self._outcomes[g.id]
            else:
                new_buffers[g.id] = deque(maxlen=self.rolling_window_cycles)
        self._outcomes = new_buffers

        self.generation += 1
        return best, std

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            'generation': self.generation,
            'population_size': self.population_size,
            'rolling_window_cycles': self.rolling_window_cycles,
            'elitism': self.elitism,
            'individuals': [g.to_dict() for g in self.population.individuals],
            'outcomes': {gid: list(buf) for gid, buf in self._outcomes.items()},
            'global_outcomes': list(self._global_outcomes),
            'active_genome_id': self.active_genome_id,
            'gene_bounds': {
                name: [lo, hi, dtype.__name__]
                for name, (lo, hi, dtype) in self.gene_bounds.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'RollingGA':
        _TYPE_MAP = {'int': int, 'float': float}
        raw_bounds = d.get('gene_bounds', {})
        gene_bounds = (
            {name: (v[0], v[1], _TYPE_MAP.get(v[2], float))
             for name, v in raw_bounds.items()}
            if raw_bounds else dict(GENE_BOUNDS)
        )
        inst = cls(
            gene_bounds=gene_bounds,
            population_size=int(d.get('population_size', 30)),
            rolling_window_cycles=int(d.get('rolling_window_cycles', 120)),
            elitism=int(d.get('elitism', 2)),
        )
        inst.generation = int(d.get('generation', 0))
        inst.population.individuals = [
            Genome.from_dict(gd, bounds=gene_bounds) for gd in d.get('individuals', [])
        ]
        if not inst.population.individuals:
            # Keep the default random population rather than leave empty
            pass
        # Restore buffers
        inst._outcomes = {
            g.id: deque(d.get('outcomes', {}).get(g.id, []),
                        maxlen=inst.rolling_window_cycles)
            for g in inst.population.individuals
        }
        inst._global_outcomes = deque(
            d.get('global_outcomes', []),
            maxlen=inst.rolling_window_cycles * 4,
        )
        inst.active_genome_id = d.get('active_genome_id')
        return inst
