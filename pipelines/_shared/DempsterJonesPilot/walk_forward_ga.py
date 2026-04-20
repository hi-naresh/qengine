"""
Walk-forward genetic algorithm for DempsterJonesPilot.

A minimal single-population GA that operates on arbitrary gene bounds
(numeric + categorical-as-index). Unlike IslandEvolver, there are no
islands, no migration, and no regime conditioning — this is the flat
baseline from Dempster & Jones (2001).

Fitness is supplied by the caller — the pipeline estimates it from a
rolling buffer of cycle outcomes; the offline training script uses
nested qengine backtests.
"""

import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np


# Pipeline-level genes — always present in every genome.
# Strategy-level genes are added dynamically from strategy.hyperparameters()
# so we work with any strategy that declares tunable HPs.
PIPELINE_GENE_BOUNDS: Dict[str, Tuple[float, float, type]] = {
    'base_size_pct':        (0.5, 5.0, float),
    'abort_aggressiveness': (0.0, 0.4, float),
}


# Strategy categorical options the pipeline is allowed to choose from.
# Mirrors IslandPilot's _SAFE_OPTIONS so both pipelines explore the same
# execution space (keeps comparisons apples-to-apples).
SAFE_CATEGORICAL_OPTIONS: Dict[str, set] = {
    'signal_mode': {'random', 'ema_cross', 'rsi', 'macd', 'supertrend',
                    'stoch', 'ema_rsi', 'ema_macd', 'triple'},
    'sizing_curve': {'geometric', 'sqrt', 'linear', 'fibonacci'},
    'hedge_mode': {'fixed_pips', 'atr_based', 'percentage'},
    'tp_mode': {'fixed_pips', 'atr_based', 'bucket_pct', 'risk_reward'},
    'base_size_mode': {'pct_equity', 'capital_aware'},
}


# Tighter numeric bounds for parameters that blow up margin at extreme values
# (copied from IslandEvolver._BOUND_OVERRIDES to keep the search space safe).
_BOUND_OVERRIDES = {
    'max_levels':      (2, 6, int),
    'sizing_factor':   (1.2, 2.0, float),
    'hedge_value':     (8, 40, float),
    'tp_value':        (8, 40, float),
    'base_size_value': (0.5, 3.0, float),
}

# Parameters to skip (structural / meta)
_SKIP_PARAMS = {'preset', 'sizing_custom_sequence', 'max_bust_dd_pct',
                'model_lookback'}

# Groups the pipeline is allowed to tune
_TUNABLE_GROUPS = {'General', 'Grid / Hedge', 'Take Profit'}


def build_gene_bounds_from_strategy(strategy) -> Dict[str, Tuple[float, float, type]]:
    """Discover gene bounds by inspecting strategy.hyperparameters().

    Returns bounds dict: name -> (lo, hi, dtype). Categorical params are
    encoded as an integer index into a filtered options list.
    """
    bounds = dict(PIPELINE_GENE_BOUNDS)

    if not hasattr(strategy, 'hyperparameters'):
        return bounds

    try:
        hp_list = strategy.hyperparameters()
    except Exception:
        return bounds

    for spec in hp_list:
        if not isinstance(spec, dict) or 'name' not in spec:
            continue
        group = spec.get('group', '')
        if group not in _TUNABLE_GROUPS:
            continue

        name = spec['name']
        if name in bounds or name in _SKIP_PARAMS:
            continue

        if name in _BOUND_OVERRIDES:
            bounds[name] = _BOUND_OVERRIDES[name]
            continue

        hp_type = spec.get('type')
        if hp_type in (int, 'int') and 'min' in spec and 'max' in spec:
            bounds[name] = (spec['min'], spec['max'], int)
        elif hp_type in (float, 'float') and 'min' in spec and 'max' in spec:
            bounds[name] = (spec['min'], spec['max'], float)
        elif hp_type == 'categorical' and 'options' in spec:
            opts = spec['options']
            safe = SAFE_CATEGORICAL_OPTIONS.get(name)
            if safe:
                opts = [o for o in opts if o in safe]
            if opts:
                bounds[name] = (0, len(opts) - 1, int)

    return bounds


# ---------------------------------------------------------------------------
# Genome
# ---------------------------------------------------------------------------

class Genome:
    def __init__(self, genes: Optional[Dict[str, Any]] = None):
        self.genes: Dict[str, Any] = dict(genes) if genes else {}
        self.id: str = uuid.uuid4().hex[:8]
        self.fitness: Optional[float] = None

    @classmethod
    def random(cls, bounds: Dict, rng: Optional[np.random.RandomState] = None) -> 'Genome':
        rng = rng if rng is not None else np.random.RandomState()
        genes: Dict[str, Any] = {}
        for name, (lo, hi, dtype) in bounds.items():
            if dtype is int:
                genes[name] = int(rng.randint(lo, hi + 1))
            else:
                genes[name] = float(rng.uniform(lo, hi))
        return cls(genes)

    def crossover(self, other: 'Genome', bounds: Dict,
                  rng: Optional[np.random.RandomState] = None) -> 'Genome':
        rng = rng if rng is not None else np.random.RandomState()
        child_genes: Dict[str, Any] = {}
        for name in bounds:
            if name in self.genes and name in other.genes:
                child_genes[name] = self.genes[name] if rng.rand() < 0.5 else other.genes[name]
            elif name in self.genes:
                child_genes[name] = self.genes[name]
            elif name in other.genes:
                child_genes[name] = other.genes[name]
        return Genome(child_genes)

    def mutate(self, bounds: Dict, sigma_pct: float = 0.05,
               rng: Optional[np.random.RandomState] = None) -> 'Genome':
        rng = rng if rng is not None else np.random.RandomState()
        new_genes: Dict[str, Any] = {}
        for name, (lo, hi, dtype) in bounds.items():
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

    def to_dict(self) -> dict:
        return {'id': self.id, 'genes': dict(self.genes), 'fitness': self.fitness}

    @classmethod
    def from_dict(cls, d: dict, bounds: Optional[Dict] = None) -> 'Genome':
        raw = d.get('genes', d)
        genes = dict(raw) if isinstance(raw, dict) else {}
        if bounds:
            filtered = {k: v for k, v in genes.items() if k in bounds}
            for name, (lo, hi, dtype) in bounds.items():
                if name not in filtered:
                    filtered[name] = (lo + hi) / 2 if dtype is float else int((lo + hi) // 2)
            genes = filtered
        g = cls(genes)
        g.id = d.get('id', uuid.uuid4().hex[:8])
        g.fitness = d.get('fitness')
        return g

    def __repr__(self) -> str:
        return f'Genome({self.id}, fitness={self.fitness})'


# ---------------------------------------------------------------------------
# Single-population GA
# ---------------------------------------------------------------------------

class WalkForwardGA:
    """Single-population genetic algorithm for walk-forward optimisation."""

    def __init__(
        self,
        bounds: Dict[str, Tuple[float, float, type]],
        population_size: int = 20,
        elitism: int = 2,
        crossover_rate: float = 0.7,
        mutation_rate: float = 0.2,
        mutation_sigma: float = 0.05,
        tournament_k: int = 3,
        seed: Optional[int] = 42,
    ):
        self.bounds = dict(bounds)
        self.population_size = population_size
        self.elitism = elitism
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.mutation_sigma = mutation_sigma
        self.tournament_k = tournament_k
        self._rng = np.random.RandomState(seed)

        self.population: List[Genome] = [
            Genome.random(self.bounds, self._rng) for _ in range(population_size)
        ]
        self.generation: int = 0

    # -- selection / reproduction -----------------------------------------

    def _tournament(self) -> Genome:
        n = len(self.population)
        k = min(self.tournament_k, n)
        picks = self._rng.choice(n, size=k, replace=False)
        contestants = [self.population[i] for i in picks]
        return max(
            contestants,
            key=lambda g: g.fitness if g.fitness is not None else -np.inf,
        )

    def evaluate(self, fitness_fn: Callable[[dict], float]) -> None:
        for ind in self.population:
            ind.fitness = fitness_fn(ind.genes)

    def step(self, fitness_fn: Callable[[dict], float]) -> Dict[str, float]:
        """One generation: evaluate + tournament / crossover / mutation / elitism.

        Returns gen stats: {best, mean, worst}.
        """
        self.evaluate(fitness_fn)

        ranked = sorted(
            self.population,
            key=lambda g: g.fitness if g.fitness is not None else -np.inf,
            reverse=True,
        )

        elites = [Genome(dict(e.genes)) for e in ranked[: self.elitism]]
        for e, src in zip(elites, ranked[: self.elitism]):
            e.fitness = src.fitness
            e.id = src.id

        offspring: List[Genome] = list(elites)
        n = self.population_size
        while len(offspring) < n:
            p1 = self._tournament()
            if self._rng.rand() < self.crossover_rate:
                p2 = self._tournament()
                child = p1.crossover(p2, self.bounds, self._rng)
            else:
                child = Genome(dict(p1.genes))
            if self._rng.rand() < self.mutation_rate:
                child = child.mutate(self.bounds, self.mutation_sigma, self._rng)
            offspring.append(child)

        self.population = offspring[:n]
        self.generation += 1

        fitnesses = [
            g.fitness for g in ranked if g.fitness is not None
        ]
        if not fitnesses:
            return {'best': 0.0, 'mean': 0.0, 'worst': 0.0}
        return {
            'best': float(max(fitnesses)),
            'mean': float(np.mean(fitnesses)),
            'worst': float(min(fitnesses)),
        }

    def run(self, fitness_fn: Callable[[dict], float], generations: int,
            log_fn: Optional[Callable[[int, Dict[str, float]], None]] = None) -> 'Genome':
        """Run the GA for N generations, return the best genome."""
        for _ in range(generations):
            stats = self.step(fitness_fn)
            if log_fn is not None:
                log_fn(self.generation, stats)
        return self.best()

    def best(self) -> Genome:
        return max(
            self.population,
            key=lambda g: g.fitness if g.fitness is not None else -np.inf,
        )

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict:
        bounds_ser = {
            name: [lo, hi, dtype.__name__]
            for name, (lo, hi, dtype) in self.bounds.items()
        }
        return {
            'population_size': self.population_size,
            'elitism': self.elitism,
            'crossover_rate': self.crossover_rate,
            'mutation_rate': self.mutation_rate,
            'mutation_sigma': self.mutation_sigma,
            'tournament_k': self.tournament_k,
            'generation': self.generation,
            'bounds': bounds_ser,
            'population': [g.to_dict() for g in self.population],
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'WalkForwardGA':
        _TYPE_MAP = {'int': int, 'float': float}
        raw_bounds = data.get('bounds', {})
        bounds = {
            name: (vals[0], vals[1], _TYPE_MAP.get(vals[2], float))
            for name, vals in raw_bounds.items()
        }
        ga = cls(
            bounds=bounds,
            population_size=data.get('population_size', 20),
            elitism=data.get('elitism', 2),
            crossover_rate=data.get('crossover_rate', 0.7),
            mutation_rate=data.get('mutation_rate', 0.2),
            mutation_sigma=data.get('mutation_sigma', 0.05),
            tournament_k=data.get('tournament_k', 3),
        )
        ga.generation = data.get('generation', 0)
        pop = data.get('population', [])
        if pop:
            ga.population = [Genome.from_dict(gd, bounds=bounds) for gd in pop]
        return ga


# ---------------------------------------------------------------------------
# Helpers — fitness composition + cycle-buffer scoring
# ---------------------------------------------------------------------------

def composite_fitness(pf: float, max_dd: float, bust_rate: float,
                      sessions: int, weights: Dict[str, float]) -> float:
    """Same fitness formula IslandPilot uses so baselines remain comparable.

    F = w_pf  * (PF - 1) * 100
      + w_dd  * max(0, 100 - DD * dd_scale)
      + w_bust * (1 - bust_rate) * 100
      + w_sess * min(sessions/session_cap, 1) * 100
    """
    w_pf = weights.get('w_pf', 0.4)
    w_dd = weights.get('w_dd', 0.3)
    w_bust = weights.get('w_bust', 0.2)
    w_sess = weights.get('w_sessions', 0.1)
    dd_scale = weights.get('dd_scale', 5.0)
    sess_cap = weights.get('session_cap', 100)

    term_pf = (pf - 1.0) * 100.0
    term_dd = max(0.0, 100.0 - abs(max_dd) * dd_scale)
    term_bust = (1.0 - max(0.0, min(1.0, bust_rate))) * 100.0
    term_sess = min(sessions / max(sess_cap, 1), 1.0) * 100.0

    return (
        w_pf * term_pf
        + w_dd * term_dd
        + w_bust * term_bust
        + w_sess * term_sess
    )


def _normalise_genes(genes: dict, bounds: Dict[str, Tuple[float, float, type]]) -> np.ndarray:
    """Map a gene dict to a 0-1 normalised vector using bounds.

    Missing genes default to 0.5 (mid-range).
    """
    vec = []
    for name, (lo, hi, _dt) in bounds.items():
        val = genes.get(name)
        if val is None:
            vec.append(0.5)
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            vec.append(0.5)
            continue
        rng = (hi - lo) or 1.0
        vec.append(max(0.0, min(1.0, (v - lo) / rng)))
    return np.asarray(vec, dtype=float)


def score_from_buffer(
    genes: dict,
    buffer: List[dict],
    bounds: Dict[str, Tuple[float, float, type]],
    radius: float = 0.25,
    min_similar: int = 3,
    fitness_weights: Optional[Dict[str, float]] = None,
    fallback: float = 0.0,
) -> float:
    """Estimate fitness for a candidate genome from a rolling cycle-outcome buffer.

    Each buffer entry must contain: {'pnl': float, 'genes': dict, 'cycle': int,
    'bust': bool (optional)}.

    Strategy:
      1. Compute L2 distance in normalised gene space.
      2. Take all cycles within radius — if fewer than min_similar, fall back
         to whole buffer (so bootstrapping still works).
      3. Aggregate PF, DD-proxy, bust rate, session count → composite fitness
         (same formula as IslandPilot for comparability).
    """
    if not buffer:
        return fallback

    weights = fitness_weights or {}

    target = _normalise_genes(genes, bounds)

    # Compute distances
    dists = []
    for entry in buffer:
        eg = entry.get('genes') or {}
        vec = _normalise_genes(eg, bounds)
        d = float(np.linalg.norm(target - vec) / max(1.0, np.sqrt(len(target))))
        dists.append(d)
    dists_arr = np.asarray(dists)

    # Select similar cycles
    mask = dists_arr <= radius
    if int(mask.sum()) < min_similar:
        # Fall back to whole buffer (still gives a signal)
        selected = buffer
    else:
        selected = [buffer[i] for i in np.where(mask)[0]]

    # Aggregate stats
    pnls = np.asarray([e.get('pnl', 0.0) for e in selected], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    gross_win = float(wins.sum()) if wins.size else 0.0
    gross_loss = float(-losses.sum()) if losses.size else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 0 else (2.0 if gross_win > 0 else 1.0)

    sessions = len(selected)
    bust_count = sum(1 for e in selected if e.get('bust') or e.get('pnl', 0.0) < -50.0)
    bust_rate = bust_count / sessions if sessions else 0.0

    # DD proxy: max peak-to-trough on cumulative pnl in %
    if pnls.size:
        eq = 10000.0 + np.cumsum(pnls)
        peak = np.maximum.accumulate(eq)
        dd = (peak - eq) / (peak + 1e-12) * 100.0
        max_dd = float(np.max(dd))
    else:
        max_dd = 0.0

    return composite_fitness(pf=pf, max_dd=max_dd, bust_rate=bust_rate,
                             sessions=sessions, weights=weights)
