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

# Pipeline-level gene bounds.
# Every bound must be derivable from theory, observed data, or published research.
#
# References used below:
#   [1] Goldberg (1989) Genetic Algorithms — pop sizing, mutation scale
#   [2] Paper Sec 3.4 / Table 7 — observed evolved ranges across 10 islands
#   [3] Martingale ruin math: p×m < 1 (author's phase1 research)
#   [4] Box & Jenkins (1976) — AR persistence threshold at 0.7
GENE_BOUNDS: Dict[str, Tuple[float, float, type]] = {
    # Lower 0.0: some regimes are low-concentration (many near-equal leaves);
    # blocking entries there is correct at any threshold > 0.
    # Upper 0.5: evolved max across 10 islands was 0.349 [2]; 0.5 provides
    # 43% headroom. Beyond 0.5, the gate would block >90% of entries for
    # typical 73-leaf trees (each leaf avg prob ~1/73 ≈ 1.4%, confident
    # signal ≈ 20-40% on dominant leaf).
    "gate_confidence_min":    (0.0, 0.5, float),

    # danger() returns vol/0.01 where vol = std of 20-bar log-returns.
    # EUR-USD 30m typical vol: 0.0003–0.001 → danger ∈ [0.03, 0.10] normally.
    # threshold = 1 − aggressiveness. At upper bound 0.4: threshold = 0.6,
    # meaning abort only when danger > 0.6 (vol > 0.006 = 60-pip std/bar,
    # extreme stress condition). Lower 0.0 = never abort. This range preserves
    # normal session flow while enabling abort only during genuine crises.
    "abort_aggressiveness":   (0.0, 0.4, float),

    # NOTE: `base_size_pct` (legacy pipeline-only gene) removed 2026-04-24.
    # It was never applied to the strategy — cluttered DNA display without
    # effect. The strategy's base is driven by `base_size_value` (pct_equity)
    # or auto-computed from `max_bust_dd_pct` (capital_aware).

    # Hysteresis margin for regime switch. [2] reports evolved range [0.071, 0.270].
    # Lower 0.05: below this, the inferencer switches on noise (< 5pp advantage
    # is within GMM classification uncertainty). Upper 0.30: beyond this,
    # genuine regime changes are suppressed too long (Astrom & Murray 2008,
    # hysteresis control theory — margin must not exceed half the typical
    # regime probability gap at a clear boundary).
    "hysteresis_margin":      (0.05, 0.30, float),

    # Exponent γ in f_conf = max(0.2, confidence^γ). γ=1 is linear scaling.
    # γ<1 (down to 0.5) is concave — tolerant of uncertainty. γ>1 (up to 2.0)
    # is convex — aggressively penalises low confidence. [2] evolved range
    # [0.736, 2.000] with mean 1.458, indicating convex scaling preferred.
    # Lower 0.5 prevents degenerate flat scaling. Upper 2.0 is the paper's
    # empirical maximum.
    "confidence_sensitivity": (0.5, 2.0, float),

    # Factor r in drawdown scaling: f_dd = max(0.1, 1 - depth*r*10).
    # [2] evolved range [0.308, 0.894]. Lower 0.3 ensures always some
    # drawdown response. Upper 1.0 allows maximum drawdown aggression
    # (size halves at 10% DD beyond threshold).
    "recovery_aggression":    (0.3, 1.0, float),
}


def _validate_genome_feasibility(genes: dict) -> dict:
    """Enforce joint feasibility constraints that individual bounds cannot capture.

    Two constraints derived from Martingale ruin mathematics:

    Constraint 1 — TP > hedge distance (positive expectancy):
        A session can only be profitable if the take-profit distance exceeds
        the hedge step. If tp_value ≤ hedge_value, every depth-escalation
        moves the recovery target further away than the hedge step earns,
        making full recovery mathematically impossible within one session.
        (Author's phase1 research on p×m < 1 condition.)

    Constraint 2 — Deepest ticket ≤ 20% of equity (survivability):
        At depth level N, ticket size = base_size_value × sizing_factor^N.
        Keeping this ≤ 20% of equity means that even a worst-case full-bust
        loss at the deepest level loses at most ~20% per ticket. With 6 levels
        and factor 2.0, the total bust exposure is bounded by the geometric
        series, which at ≤ 20% deepest ticket sums to ≤ 40% account loss —
        painful but not account-ending. (Derived from author's phase1 capital
        scaling analysis; 20% threshold consistent with Kelly fraction at
        p×m = 0.80 empirically measured for EUR-USD SurefireHedge.)

    Returns a copy of genes with infeasible values clamped to satisfy constraints.
    """
    g = dict(genes)

    # Constraint 1: tp_value >= hedge_value × 1.5 (meaningful recovery margin).
    # Rationale: TP must clear the hedge distance by a ratio, not a fixed 5-pip
    # nudge. A 35-pip hedge with 40-pip TP leaves just 5 pips of recovery budget
    # once slippage/spread eat in — sessions statistically can't close via TP.
    # 1.5× gives ~50% recovery margin above the hedge step and prevents the GA
    # from collapsing onto the hedge_value + 5 boundary seen in phase6 genomes.
    if 'tp_value' in g and 'hedge_value' in g:
        min_tp = g['hedge_value'] * 1.5
        if g['tp_value'] < min_tp:
            from . import manifest as _manifest
            _manifest.record(
                "feasibility_correction",
                gene="tp_value",
                original=float(g['tp_value']),
                corrected=float(min_tp),
                reason="tp_value < hedge_value * 1.5",
            )
            g['tp_value'] = min_tp

    # Constraint 2: base_size_value × sizing_factor^max_levels ≤ 20.0
    # (Replaces the legacy base_size_pct constraint after that gene was removed
    # — see GENE_BOUNDS note above. base_size_value is the strategy-native HP
    # that the pipeline actually writes, so the survivability bound is enforced
    # directly on it.)
    if 'base_size_value' in g and 'sizing_factor' in g and 'max_levels' in g:
        max_ticket = g['base_size_value'] * (g['sizing_factor'] ** g['max_levels'])
        if max_ticket > 20.0:
            from . import manifest as _manifest
            corrected_base = 20.0 / (g['sizing_factor'] ** g['max_levels'])
            _manifest.record(
                "feasibility_correction",
                gene="base_size_value",
                original=float(g['base_size_value']),
                corrected=float(corrected_base),
                reason="base_size_value * sizing_factor^max_levels > 20",
            )
            g['base_size_value'] = corrected_base

    return g


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

    # Must match _TUNABLE_GROUPS in pipelines/_shared/IslandPilot/__init__.py::_apply_genome.
    # If training evolves fewer groups than inference applies, the unevolved groups fall
    # back to strategy defaults at inference — i.e. the regime tree has no way to
    # specialise them per-leaf. Keep these two sets identical.
    _TUNABLE_GROUPS = {
        'General', 'Grid / Hedge', 'Take Profit',
        'Entry Signal', 'Filters', 'Risk Management', 'Position Management',
    }

    # Tighter bounds for params that cause margin blowups when extreme.
    # Bounds are set so that the worst-case total exposure across all
    # curve/factor/level combos stays under ~100x base, which keeps
    # bust losses within 15% of equity at reasonable base sizes.
    #
    # Key constraint: geometric 2.0 @ 6 levels = 127x (borderline).
    # Capping factor at 2.0 and levels at 6 ensures all curves stay safe.
    # The SimConfig.from_genome() method applies a second equity-aware
    # cap at runtime, reducing levels further if the account cannot afford them.
    # Bounds tuned so that:
    # - base_size × sizing_factor^max_levels ≤ 20 (joint ruin constraint)
    # - max_levels up to 8 allows deep recovery grids with small base sizes
    # - hedge_value / tp_value bounds are sized for fixed_pips mode; the
    #   pipeline rescales per actual mode at apply time (_coerce_mode_value).
    _BOUND_OVERRIDES = {
        'max_levels': (2, 8, int),            # deeper grids allowed
        # Lower bound 1.5 (~sqrt(2)) enforces mathematical viability.
        # Below 1.414 each hedge cannot recover prior losses + spread; GA
        # previously converged on factor ~1.27 which produces "TP Hit"
        # sessions with net-negative PnL (breakeven exit minus spread bleed).
        'sizing_factor': (1.5, 2.5, float),
        'hedge_value': (8, 40, float),         # pips (scaled per-mode at runtime)
        'tp_value': (12, 80, float),           # pips (scaled per-mode at runtime)
        'base_size_value': (0.1, 3.0, float),  # small base + deep levels viable
        # hedge_expand_factor at 1.74^6 = 28x wider hedges at L5, which forces
        # capital_aware sizing to evolve tiny base (→ 70 qty) yet still flags
        # bust when max_levels is reached. Narrow to (1.0, 1.3).
        'hedge_expand_factor': (1.0, 1.3, float),
        # Allow the GA to evolve capital_aware's risk budget per regime.
        'max_bust_dd_pct': (5.0, 20.0, float),
    }
    # Skip gating filters entirely during training — they have many options but
    # only 'none' is permissive. Random init gives P(all off) = (1/4)^5 ≈ 0.1%,
    # so >99% of genomes have some filter blocking all entries → zero sessions.
    # Let filters default to 'none' at inference. Also skip the dependent
    # threshold/period params that are only meaningful when a filter is active.
    _SKIP_PARAMS = {
        'preset', 'sizing_custom_sequence', 'model_lookback',
        # Filters group (make entry fire by default)
        'session_filter', 'trend_filter', 'vol_filter', 'day_filter',
        'spread_filter', 'confidence_gate',
        'trend_filter_period', 'trend_filter_threshold',
        'vol_filter_period', 'vol_filter_min', 'vol_filter_max',
        'spread_filter_max', 'confidence_threshold',
        # Low-information signal dependents (GA-unfriendly: affect output only
        # when that signal_mode is picked). Keep main signal genes evolving.
        'rsi_ob', 'rsi_os', 'stoch_ob', 'stoch_os', 'cci_ob', 'cci_os',
        'bb_period', 'bb_std',
    }

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
        genes = _validate_genome_feasibility(genes)
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
        child_genes = _validate_genome_feasibility(child_genes)
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
        new_genes = _validate_genome_feasibility(new_genes)
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

            # Ring-topology sibling migration: inject i-1's best into island i,
            # but only if the donor's fitness is at least as good as the
            # recipient's mean fitness. This preserves Wright's (1931) shifting
            # balance: migration carries adaptive alleles across demes, but
            # should not degrade a well-converged island with inferior genomes.
            for i, sid in enumerate(valid):
                donor_id = valid[(i - 1) % len(valid)]
                donor_genome = bests[donor_id]
                recipient_pop = self.populations[sid]
                recipient_fitnesses = [g.fitness for g in recipient_pop.individuals
                                       if g.fitness is not None]
                recipient_mean = float(np.mean(recipient_fitnesses)) if recipient_fitnesses else -np.inf

                if donor_genome.fitness is None or donor_genome.fitness >= recipient_mean:
                    from . import manifest as _manifest
                    _manifest.record(
                        "migration",
                        macro=str(donor_id).split("_sub")[0] if "_sub" in str(donor_id) else str(donor_id),
                        donor_island=str(donor_id),
                        recipient_island=str(sid),
                        donor_fitness=float(donor_genome.fitness or 0.0),
                        recipient_mean=float(recipient_mean),
                        accepted=True,
                    )
                    recipient_pop.inject(donor_genome)
                    self.migration_log.append({
                        "from": donor_id,
                        "to": sid,
                        "genome_id": donor_genome.id,
                        "fitness": donor_genome.fitness,
                        "group": group_name,
                        "accepted": True,
                    })
                else:
                    from . import manifest as _manifest
                    _manifest.record(
                        "migration",
                        macro=str(donor_id).split("_sub")[0] if "_sub" in str(donor_id) else str(donor_id),
                        donor_island=str(donor_id),
                        recipient_island=str(sid),
                        donor_fitness=float(donor_genome.fitness or 0.0),
                        recipient_mean=float(recipient_mean),
                        accepted=False,
                    )
                    self.migration_log.append({
                        "from": donor_id,
                        "to": sid,
                        "genome_id": donor_genome.id,
                        "fitness": donor_genome.fitness,
                        "group": group_name,
                        "accepted": False,
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
