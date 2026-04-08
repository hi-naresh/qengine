"""
IslandEvolver — genetic algorithm engine for per-regime parameter tuning.

Manages independent populations (islands) per regime leaf, with tournament
selection, uniform crossover, gaussian mutation, elitism, and sibling-based
migration.

Part of the IslandPilot pipeline.
"""

import json
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Gene definitions
# ---------------------------------------------------------------------------

# Pipeline-level genes only. Strategy HP (sizing, hedge, TP) are NOT included —
# those belong to the user/optimizer, not the pipeline.
GENE_BOUNDS: Dict[str, Tuple[float, float, type]] = {
    "gate_confidence_min":    (0.0, 1.0, float),   # min regime confidence to allow entry
    "abort_aggressiveness":   (0.0, 1.0, float),   # danger threshold for mid-cycle abort
    "base_size_pct":          (0.5, 5.0, float),    # base position scale as % of equity
    "hysteresis_margin":      (0.05, 0.30, float),  # margin needed to switch regime
    "confidence_sensitivity": (0.5, 2.0, float),    # how aggressively confidence scales size
    "recovery_aggression":    (0.3, 1.0, float),    # how aggressively drawdown reduces size
}

# Legacy — kept for backward compat with old genomes that have these keys
SIZING_CURVE_MAP = {0: "geometric", 1: "sqrt", 2: "linear", 3: "fibonacci"}
SIZING_CURVE_REVERSE = {v: k for k, v in SIZING_CURVE_MAP.items()}


# ---------------------------------------------------------------------------
# Genome
# ---------------------------------------------------------------------------

class Genome:
    """Single candidate solution with genes, id, and fitness."""

    def __init__(self, genes: Optional[Dict[str, Any]] = None):
        self.genes: Dict[str, Any] = genes or {}
        self.id: str = uuid.uuid4().hex[:8]
        self.fitness: Optional[float] = None

    # -- factory -----------------------------------------------------------

    @classmethod
    def random(cls, seed: Optional[int] = None) -> "Genome":
        """Create a genome with uniformly random genes within bounds."""
        rng = np.random.RandomState(seed)
        genes: Dict[str, Any] = {}
        for name, (lo, hi, dtype) in GENE_BOUNDS.items():
            if dtype is int:
                genes[name] = int(rng.randint(lo, hi + 1))
            else:
                genes[name] = float(rng.uniform(lo, hi))
        g = cls(genes)
        return g

    # -- operators ---------------------------------------------------------

    def crossover(self, other: "Genome", seed: Optional[int] = None) -> "Genome":
        """Uniform crossover — each gene picked from self or other with 50% probability."""
        rng = np.random.RandomState(seed)
        child_genes: Dict[str, Any] = {}
        for name in GENE_BOUNDS:
            if rng.rand() < 0.5:
                child_genes[name] = self.genes[name]
            else:
                child_genes[name] = other.genes[name]
        return Genome(child_genes)

    def mutate(self, sigma_pct: float = 0.05, seed: Optional[int] = None) -> "Genome":
        """Gaussian mutation — perturb each gene by sigma_pct of its range, clamped."""
        rng = np.random.RandomState(seed)
        new_genes: Dict[str, Any] = {}
        for name, (lo, hi, dtype) in GENE_BOUNDS.items():
            val = self.genes[name]
            spread = (hi - lo) * sigma_pct
            perturbed = val + rng.randn() * spread
            perturbed = max(lo, min(hi, perturbed))
            if dtype is int:
                perturbed = int(round(perturbed))
            new_genes[name] = perturbed
        g = Genome(new_genes)
        g.fitness = None
        return g

    # -- serialisation -----------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise genome."""
        d = dict(self.genes)
        # Convert legacy sizing_curve int -> string if present
        if "sizing_curve" in d and isinstance(d["sizing_curve"], int):
            d["sizing_curve"] = SIZING_CURVE_MAP.get(d["sizing_curve"], d["sizing_curve"])
        return {"id": self.id, "genes": d, "fitness": self.fitness}

    @classmethod
    def from_dict(cls, d: dict) -> "Genome":
        """Deserialise genome. Handles both old (11-gene) and new (6-gene) formats."""
        raw = d.get("genes", d)
        if isinstance(raw, dict):
            genes = dict(raw)
        else:
            genes = {}
        # Only keep genes that are in GENE_BOUNDS (ignore legacy strategy params)
        filtered = {k: v for k, v in genes.items() if k in GENE_BOUNDS}
        # Fill missing genes with midpoint defaults
        for name, (lo, hi, dtype) in GENE_BOUNDS.items():
            if name not in filtered:
                filtered[name] = (lo + hi) / 2 if dtype == float else (lo + hi) // 2
        g = cls(filtered)
        g.id = d.get("id", uuid.uuid4().hex[:8])
        g.fitness = d.get("fitness")
        return g

    def __repr__(self) -> str:
        return f"Genome({self.id}, fitness={self.fitness})"


# ---------------------------------------------------------------------------
# Population
# ---------------------------------------------------------------------------

class Population:
    """A single island population with tournament selection and elitism."""

    def __init__(self, island_id: str, size: int = 30, seed: Optional[int] = None):
        self.island_id = island_id
        self.size = size
        self._seed = seed
        rng = np.random.RandomState(seed)
        self.individuals: List[Genome] = [
            Genome.random(seed=int(rng.randint(0, 2**31)))
            for _ in range(size)
        ]

    def evaluate(self, fitness_fn: Callable[[dict], float]) -> None:
        """Evaluate all individuals using the provided fitness function."""
        for ind in self.individuals:
            ind.fitness = fitness_fn(ind.genes)

    def evolve(
        self,
        elitism: int = 2,
        crossover_rate: float = 0.7,
        mutation_rate: float = 0.2,
        mutation_sigma: float = 0.05,
        tournament_k: int = 3,
    ) -> None:
        """One generation: tournament selection, crossover, mutation, elitism."""
        rng = np.random.RandomState(None)
        n = len(self.individuals)

        # Sort by fitness descending (higher = better)
        ranked = sorted(
            self.individuals,
            key=lambda g: g.fitness if g.fitness is not None else -np.inf,
            reverse=True,
        )

        # Elites survive unchanged
        elites = ranked[:elitism]

        def _tournament() -> Genome:
            contestants = rng.choice(ranked, size=min(tournament_k, n), replace=False)
            return max(
                contestants,
                key=lambda g: g.fitness if g.fitness is not None else -np.inf,
            )

        offspring: List[Genome] = list(elites)
        while len(offspring) < n:
            p1 = _tournament()
            if rng.rand() < crossover_rate:
                p2 = _tournament()
                child = p1.crossover(p2, seed=int(rng.randint(0, 2**31)))
            else:
                child = Genome(dict(p1.genes))
            if rng.rand() < mutation_rate:
                child = child.mutate(sigma_pct=mutation_sigma, seed=int(rng.randint(0, 2**31)))
            offspring.append(child)

        self.individuals = offspring[:n]

    def inject(self, genome: Genome) -> None:
        """Replace the worst individual with the given genome."""
        if not self.individuals:
            self.individuals.append(genome)
            return
        worst_idx = min(
            range(len(self.individuals)),
            key=lambda i: self.individuals[i].fitness if self.individuals[i].fitness is not None else -np.inf,
        )
        self.individuals[worst_idx] = genome


# ---------------------------------------------------------------------------
# IslandEvolver
# ---------------------------------------------------------------------------

class IslandEvolver:
    """Manages per-regime island populations with sibling migration."""

    def __init__(
        self,
        leaf_ids: List[str],
        config: Optional[dict] = None,
        sibling_groups: Optional[Dict[str, List[str]]] = None,
    ):
        config = config or {}
        pop_size = config.get("pop_size", 30)
        seed = config.get("seed", None)

        self.leaf_ids = list(leaf_ids)
        self.config = config
        self.sibling_groups = sibling_groups or {}
        self.populations: Dict[str, Population] = {}
        self.migration_log: List[dict] = []
        self.outcome_log: List[dict] = []

        rng = np.random.RandomState(seed)
        for lid in self.leaf_ids:
            self.populations[lid] = Population(
                island_id=lid,
                size=pop_size,
                seed=int(rng.randint(0, 2**31)),
            )

    # -- core API ----------------------------------------------------------

    def get_best_genome(self, regime_id: str) -> dict:
        """Return the best genome for the given regime as a dict."""
        pop = self.populations[regime_id]
        best = max(
            pop.individuals,
            key=lambda g: g.fitness if g.fitness is not None else -np.inf,
        )
        return best.to_dict()

    def evolve_all(self, fitness_fn: Callable[[dict], float], generation: int = 0) -> None:
        """Evaluate and evolve all island populations."""
        for pop in self.populations.values():
            pop.evaluate(fitness_fn)
            pop.evolve(
                elitism=self.config.get("elitism", 2),
                crossover_rate=self.config.get("crossover_rate", 0.7),
                mutation_rate=self.config.get("mutation_rate", 0.2),
                mutation_sigma=self.config.get("mutation_sigma", 0.05),
                tournament_k=self.config.get("tournament_k", 3),
            )

    def migrate_siblings(self) -> None:
        """Exchange the best genome between sibling islands."""
        for group_name, siblings in self.sibling_groups.items():
            valid = [s for s in siblings if s in self.populations]
            if len(valid) < 2:
                continue
            # Gather best from each island
            bests: Dict[str, Genome] = {}
            for sid in valid:
                pop = self.populations[sid]
                best = max(
                    pop.individuals,
                    key=lambda g: g.fitness if g.fitness is not None else -np.inf,
                )
                # Clone
                clone = Genome(dict(best.genes))
                clone.fitness = best.fitness
                bests[sid] = clone

            # Inject each island's best into the next sibling (ring topology)
            for i, sid in enumerate(valid):
                donor_id = valid[(i - 1) % len(valid)]
                donor_genome = bests[donor_id]
                self.populations[sid].inject(donor_genome)
                self.migration_log.append({
                    "from": donor_id,
                    "to": sid,
                    "genome_id": donor_genome.id,
                    "fitness": donor_genome.fitness,
                    "group": group_name,
                })

    def record_outcome(self, **kwargs) -> None:
        """Record an outcome for logging/analysis."""
        self.outcome_log.append(dict(kwargs))

    # -- stats / inspection ------------------------------------------------

    def get_fitness_summary(self) -> Dict[str, dict]:
        """Return fitness summary per island."""
        summary = {}
        for lid, pop in self.populations.items():
            fitnesses = [g.fitness for g in pop.individuals if g.fitness is not None]
            if fitnesses:
                summary[lid] = {
                    "best": max(fitnesses),
                    "worst": min(fitnesses),
                    "mean": float(np.mean(fitnesses)),
                    "std": float(np.std(fitnesses)),
                    "n": len(fitnesses),
                }
            else:
                summary[lid] = {"best": None, "worst": None, "mean": None, "std": None, "n": 0}
        return summary

    def get_migration_log(self) -> List[dict]:
        return list(self.migration_log)

    def get_diversity_stats(self) -> Dict[str, dict]:
        """Return gene-diversity stats per island (std of each gene)."""
        stats = {}
        for lid, pop in self.populations.items():
            gene_arrays: Dict[str, list] = {name: [] for name in GENE_BOUNDS}
            for ind in pop.individuals:
                for name in GENE_BOUNDS:
                    gene_arrays[name].append(ind.genes[name])
            stats[lid] = {
                name: float(np.std(vals)) if vals else 0.0
                for name, vals in gene_arrays.items()
            }
        return stats

    # -- persistence -------------------------------------------------------

    def save(self, path: str) -> None:
        """Save evolver state to JSON."""
        data = {
            "leaf_ids": self.leaf_ids,
            "config": self.config,
            "sibling_groups": self.sibling_groups,
            "migration_log": self.migration_log,
            "outcome_log": self.outcome_log,
            "populations": {},
        }
        for lid, pop in self.populations.items():
            data["populations"][lid] = {
                "island_id": pop.island_id,
                "size": pop.size,
                "individuals": [g.to_dict() for g in pop.individuals],
            }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "IslandEvolver":
        """Load evolver state from JSON."""
        with open(path) as f:
            data = json.load(f)
        evolver = cls.__new__(cls)
        evolver.leaf_ids = data["leaf_ids"]
        evolver.config = data["config"]
        evolver.sibling_groups = data.get("sibling_groups", {})
        evolver.migration_log = data.get("migration_log", [])
        evolver.outcome_log = data.get("outcome_log", [])
        evolver.populations = {}
        for lid, pdata in data["populations"].items():
            pop = Population.__new__(Population)
            pop.island_id = pdata["island_id"]
            pop.size = pdata["size"]
            pop._seed = None
            pop.individuals = [Genome.from_dict(gd) for gd in pdata["individuals"]]
            evolver.populations[lid] = pop
        return evolver
