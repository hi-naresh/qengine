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

# Pipeline-level genes (always present in every genome).
# Strategy-specific genes are added dynamically from strategy.hyperparameters()
# by the IslandPilot pipeline during training — see _build_gene_bounds().
GENE_BOUNDS: Dict[str, Tuple[float, float, type]] = {
    "gate_confidence_min":    (0.0, 0.5, float),    # min regime confidence to allow entry (was 0.8 — too restrictive, blocks most entries)
    "abort_aggressiveness":   (0.0, 0.4, float),    # 0=never abort, 0.4=abort at danger>0.6 (conservative)
    "base_size_pct":          (0.5, 3.0, float),    # base position scale as % of equity (was 5.0, causes ruin at high levels)
    "hysteresis_margin":      (0.05, 0.30, float),  # margin needed to switch regime
    "confidence_sensitivity": (0.5, 2.0, float),    # how aggressively confidence scales size
    "recovery_aggression":    (0.3, 1.0, float),    # how aggressively drawdown reduces size
}


def build_gene_bounds_from_strategy(strategy) -> Dict[str, Tuple[float, float, type]]:
    """Extend GENE_BOUNDS with tunable strategy HP discovered at runtime.

    Reads strategy.hyperparameters() and adds numeric params from
    'General', 'Grid / Hedge', and 'Take Profit' groups.
    Categorical params are encoded as int indices.
    """
    bounds = dict(GENE_BOUNDS)

    if not hasattr(strategy, 'hyperparameters'):
        return bounds

    try:
        hp_list = strategy.hyperparameters()
    except Exception:
        return bounds

    # Entry Signal excluded — pipeline controls execution, not signal timing.
    _TUNABLE_GROUPS = {'General', 'Grid / Hedge', 'Take Profit'}

    # Tighter bounds for params that cause margin blowups when extreme.
    # Bounds are set so that the worst-case total exposure across all
    # curve/factor/level combos stays under ~100x base, which keeps
    # bust losses within 15% of equity at reasonable base sizes.
    #
    # Key constraint: geometric 2.0 @ 6 levels = 127x (borderline).
    # Capping factor at 2.0 and levels at 6 ensures all curves stay safe.
    # The SimConfig.from_genome() method applies a second equity-aware
    # cap at runtime, reducing levels further if the account cannot afford them.
    _BOUND_OVERRIDES = {
        'max_levels': (2, 6, int),            # was (2,8) — geo 2.0 @ 8 = 511x exposure
        'sizing_factor': (1.2, 2.0, float),   # was (1.2,2.5) — 2.5^8 = 1526x per ticket
        'hedge_value': (8, 40, float),         # pips — narrower to avoid tiny/huge grids
        'tp_value': (8, 40, float),            # pips
        'base_size_value': (0.5, 3.0, float),  # was (0.5,5.0) — 5% base + geo 2.0 @ 6 = ruin
    }
    # Skip params that shouldn't be evolved (meta/structural)
    _SKIP_PARAMS = {'preset', 'sizing_custom_sequence', 'max_bust_dd_pct', 'model_lookback'}

    for spec in hp_list:
        if not isinstance(spec, dict) or 'name' not in spec:
            continue
        group = spec.get('group', '')
        if group not in _TUNABLE_GROUPS:
            continue

        name = spec['name']
        if name in bounds or name in _SKIP_PARAMS:
            continue

        # Use override bounds if available
        if name in _BOUND_OVERRIDES:
            bounds[name] = _BOUND_OVERRIDES[name]
            continue

        hp_type = spec.get('type')
        if hp_type in (int, 'int') and 'min' in spec and 'max' in spec:
            bounds[name] = (spec['min'], spec['max'], int)
        elif hp_type in (float, 'float') and 'min' in spec and 'max' in spec:
            bounds[name] = (spec['min'], spec['max'], float)
        elif hp_type == 'categorical' and 'options' in spec:
            # Filter to safe/validated options for known params
            _SAFE = {
                'signal_mode': {'random', 'ema_cross', 'rsi', 'macd', 'supertrend', 'stoch', 'ema_rsi', 'ema_macd', 'triple'},
                'sizing_curve': {'geometric', 'sqrt', 'linear', 'fibonacci'},
                'hedge_mode': {'fixed_pips', 'atr_based', 'percentage'},
                'tp_mode': {'fixed_pips', 'atr_based', 'bucket_pct', 'risk_reward'},
                'base_size_mode': {'pct_equity', 'capital_aware'},  # only % modes, not fixed units
            }
            opts = spec['options']
            safe = _SAFE.get(name)
            if safe:
                opts = [o for o in opts if o in safe]
            if opts:
                bounds[name] = (0, len(opts) - 1, int)

    return bounds

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
    def random(cls, seed: Optional[int] = None, bounds: Optional[Dict] = None) -> "Genome":
        """Create a genome with uniformly random genes within bounds."""
        _bounds = bounds or GENE_BOUNDS
        rng = np.random.RandomState(seed)
        genes: Dict[str, Any] = {}
        for name, (lo, hi, dtype) in _bounds.items():
            if dtype is int:
                genes[name] = int(rng.randint(lo, hi + 1))
            else:
                genes[name] = float(rng.uniform(lo, hi))
        g = cls(genes)
        return g

    # -- operators ---------------------------------------------------------

    def crossover(self, other: "Genome", seed: Optional[int] = None, bounds: Optional[Dict] = None) -> "Genome":
        """Uniform crossover — each gene picked from self or other with 50% probability."""
        _bounds = bounds or GENE_BOUNDS
        rng = np.random.RandomState(seed)
        child_genes: Dict[str, Any] = {}
        for name in _bounds:
            if name in self.genes and name in other.genes:
                child_genes[name] = self.genes[name] if rng.rand() < 0.5 else other.genes[name]
            elif name in self.genes:
                child_genes[name] = self.genes[name]
            elif name in other.genes:
                child_genes[name] = other.genes[name]
        return Genome(child_genes)

    def mutate(self, sigma_pct: float = 0.05, seed: Optional[int] = None, bounds: Optional[Dict] = None) -> "Genome":
        """Gaussian mutation — perturb each gene by sigma_pct of its range, clamped."""
        _bounds = bounds or GENE_BOUNDS
        rng = np.random.RandomState(seed)
        new_genes: Dict[str, Any] = {}
        for name, (lo, hi, dtype) in _bounds.items():
            val = self.genes.get(name, (lo + hi) / 2)
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
    def from_dict(cls, d: dict, bounds: Optional[Dict] = None) -> "Genome":
        """Deserialise genome. Accepts any gene set — missing genes filled from bounds."""
        _bounds = bounds or GENE_BOUNDS
        raw = d.get("genes", d)
        genes = dict(raw) if isinstance(raw, dict) else {}
        # Keep all genes that are in bounds
        filtered = {k: v for k, v in genes.items() if k in _bounds}
        # Fill missing genes with midpoint defaults
        for name, (lo, hi, dtype) in _bounds.items():
            if name not in filtered:
                filtered[name] = (lo + hi) / 2 if dtype is float else (lo + hi) // 2
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

    def __init__(self, island_id: str, size: int = 30, seed: Optional[int] = None,
                 gene_bounds: Optional[Dict] = None):
        self.island_id = island_id
        self.size = size
        self._seed = seed
        self.gene_bounds = gene_bounds or GENE_BOUNDS
        rng = np.random.RandomState(seed)
        self.individuals: List[Genome] = [
            Genome.random(seed=int(rng.randint(0, 2**31)), bounds=self.gene_bounds)
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
                child = p1.crossover(p2, seed=int(rng.randint(0, 2**31)), bounds=self.gene_bounds)
            else:
                child = Genome(dict(p1.genes))
            if rng.rand() < mutation_rate:
                child = child.mutate(sigma_pct=mutation_sigma, seed=int(rng.randint(0, 2**31)), bounds=self.gene_bounds)
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
        gene_bounds: Optional[Dict] = None,
    ):
        config = config or {}
        pop_size = config.get("pop_size", 30)
        seed = config.get("seed", None)

        self.leaf_ids = list(leaf_ids)
        self.config = config
        self.sibling_groups = sibling_groups or {}
        self.gene_bounds = gene_bounds or GENE_BOUNDS
        self.populations: Dict[str, Population] = {}
        self.migration_log: List[dict] = []
        self.outcome_log: List[dict] = []

        rng = np.random.RandomState(seed)
        for lid in self.leaf_ids:
            self.populations[lid] = Population(
                island_id=lid,
                size=pop_size,
                gene_bounds=self.gene_bounds,
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
            gene_arrays: Dict[str, list] = {name: [] for name in self.gene_bounds}
            for ind in pop.individuals:
                for name in self.gene_bounds:
                    val = ind.genes.get(name)
                    if isinstance(val, (int, float)):
                        gene_arrays[name].append(val)
            stats[lid] = {
                name: float(np.std(vals)) if len(vals) > 1 else 0.0
                for name, vals in gene_arrays.items()
            }
        return stats

    # -- persistence -------------------------------------------------------

    def save(self, path: str) -> None:
        """Save evolver state to JSON."""
        # Serialize gene_bounds for reload
        serialized_bounds = {
            name: [lo, hi, dtype.__name__]
            for name, (lo, hi, dtype) in self.gene_bounds.items()
        }
        data = {
            "leaf_ids": self.leaf_ids,
            "config": self.config,
            "sibling_groups": self.sibling_groups,
            "gene_bounds": serialized_bounds,
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
        _TYPE_MAP = {"int": int, "float": float}
        with open(path) as f:
            data = json.load(f)

        # Restore gene_bounds
        raw_bounds = data.get("gene_bounds", {})
        if raw_bounds:
            gene_bounds = {
                name: (vals[0], vals[1], _TYPE_MAP.get(vals[2], float))
                for name, vals in raw_bounds.items()
            }
        else:
            gene_bounds = dict(GENE_BOUNDS)

        evolver = cls.__new__(cls)
        evolver.leaf_ids = data["leaf_ids"]
        evolver.config = data["config"]
        evolver.sibling_groups = data.get("sibling_groups", {})
        evolver.gene_bounds = gene_bounds
        evolver.migration_log = data.get("migration_log", [])
        evolver.outcome_log = data.get("outcome_log", [])
        evolver.populations = {}
        for lid, pdata in data["populations"].items():
            pop = Population.__new__(Population)
            pop.island_id = pdata["island_id"]
            pop.size = pdata["size"]
            pop._seed = None
            pop.gene_bounds = gene_bounds
            pop.individuals = [Genome.from_dict(gd, bounds=gene_bounds) for gd in pdata["individuals"]]
            evolver.populations[lid] = pop
        return evolver
