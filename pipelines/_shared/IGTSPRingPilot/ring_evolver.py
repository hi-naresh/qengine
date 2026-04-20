"""
RingEvolver — thin wrapper around IslandEvolver that enforces a
ring-topology migration schedule instead of regime-sibling migration.

Islands are plain parallel search populations (NOT regimes). They all
optimise against the SAME global fitness function. Every K generations,
each island sends its best genome to the next island in the ring:
    pop_i -> pop_{(i+1) % N}
replacing the worst individual in the receiving population.

This matches:
    Chideme, Chen & Lin (2025), Engineering Optimization,
    DOI: 10.1080/0305215X.2025.2592030

The wrapper reuses `IslandEvolver` machinery (populations, tournament
selection, crossover, mutation, elitism) but overrides `migrate_siblings`
with `migrate_ring` so there are no regime/macro coupling effects.
"""
from typing import Callable, Dict, List, Optional

import numpy as np

from qengine.framework.components.island_evolver import (
    IslandEvolver,
    Genome,
    Population,
    GENE_BOUNDS,
)


class RingEvolver(IslandEvolver):
    """IslandEvolver with forced ring-topology migration."""

    def __init__(
        self,
        leaf_ids: List[str],
        config: Optional[dict] = None,
        gene_bounds: Optional[Dict] = None,
    ):
        # Build a single sibling group containing ALL islands in ring order.
        # We don't actually use the parent's migrate_siblings; we override it
        # below with migrate_ring. But keeping the group list lets save/load
        # round-trip cleanly.
        ring_groups = {'ring': list(leaf_ids)}
        super().__init__(
            leaf_ids=leaf_ids,
            config=config,
            sibling_groups=ring_groups,
            gene_bounds=gene_bounds,
        )
        self._generation: int = 0

    # ------------------------------------------------------------------
    # Ring migration
    # ------------------------------------------------------------------

    def migrate_ring(self) -> None:
        """Each island sends its best genome to the next island in the ring.

        pop_i.best → pop_{(i+1) % N}.replace(worst)
        """
        order = [lid for lid in self.leaf_ids if lid in self.populations]
        if len(order) < 2:
            return

        # Snapshot the best genome from each island BEFORE injecting,
        # so the injection order doesn't self-contaminate.
        bests: Dict[str, Genome] = {}
        for lid in order:
            pop = self.populations[lid]
            best = max(
                pop.individuals,
                key=lambda g: g.fitness if g.fitness is not None else -np.inf,
            )
            clone = Genome(dict(best.genes))
            clone.fitness = best.fitness
            bests[lid] = clone

        # Inject donor (predecessor in ring) into each receiver
        for i, receiver_id in enumerate(order):
            donor_id = order[(i - 1) % len(order)]
            donor_genome = bests[donor_id]
            self.populations[receiver_id].inject(donor_genome)
            self.migration_log.append({
                'from': donor_id,
                'to': receiver_id,
                'genome_id': donor_genome.id,
                'fitness': donor_genome.fitness,
                'generation': self._generation,
                'topology': 'ring',
            })

    # Disable the parent's sibling-based migration — we only do ring.
    def migrate_siblings(self) -> None:  # type: ignore[override]
        self.migrate_ring()

    # ------------------------------------------------------------------
    # Step API: one GA generation across all islands + optional migration
    # ------------------------------------------------------------------

    def step(
        self,
        fitness_fn: Callable[[dict], float],
        migration_interval: int = 5,
    ) -> None:
        """Run one generation: evaluate → evolve → (maybe) migrate."""
        self._generation += 1

        ev = self.config
        elitism = ev.get('elitism', 1)
        crossover_rate = ev.get('crossover_rate', 0.7)
        mutation_rate = ev.get('mutation_rate', 0.2)
        mutation_sigma = ev.get('mutation_sigma', 0.1)
        tournament_k = ev.get('tournament_k', 3)

        for pop in self.populations.values():
            pop.evaluate(fitness_fn)
            pop.evolve(
                elitism=elitism,
                crossover_rate=crossover_rate,
                mutation_rate=mutation_rate,
                mutation_sigma=mutation_sigma,
                tournament_k=tournament_k,
            )

        if migration_interval > 0 and self._generation % migration_interval == 0:
            self.migrate_ring()

    # ------------------------------------------------------------------
    # Persistence — ensure loaded instances are RingEvolver and have
    # the _generation counter restored.
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str) -> "RingEvolver":  # type: ignore[override]
        base = IslandEvolver.load(path)
        # Re-cast to RingEvolver so migrate_siblings uses ring topology
        ring = cls.__new__(cls)
        ring.leaf_ids = base.leaf_ids
        ring.config = base.config
        ring.sibling_groups = base.sibling_groups or {'ring': list(base.leaf_ids)}
        ring.gene_bounds = base.gene_bounds
        ring.migration_log = base.migration_log
        ring.outcome_log = base.outcome_log
        ring.populations = base.populations
        ring._generation = 0
        # Try to infer generation count from migration log
        if ring.migration_log:
            gens = [m.get('generation', 0) for m in ring.migration_log
                    if isinstance(m, dict) and 'generation' in m]
            if gens:
                ring._generation = max(gens)
        return ring

    # ------------------------------------------------------------------
    # Global best (across all islands, since all share the same fitness)
    # ------------------------------------------------------------------

    def get_global_best(self) -> Optional[dict]:
        """Return the genome with the highest fitness across ALL islands.

        Falls back to None if no genome has been evaluated yet.
        """
        best: Optional[Genome] = None
        best_from: Optional[str] = None
        for lid, pop in self.populations.items():
            for ind in pop.individuals:
                if ind.fitness is None:
                    continue
                if best is None or ind.fitness > (best.fitness or -np.inf):
                    best = ind
                    best_from = lid
        if best is None:
            return None
        out = best.to_dict()
        out['island_id'] = best_from
        return out
