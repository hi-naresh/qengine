"""
52 — IGTSP Ring Training (offline)
==================================

Trains the IGTSPRingPilot baseline: island-model GA with RING-topology migration
and NO regime structure. Mirrors the IslandPilot training budget (same fitness
formula, same strategy, same tuning groups) so results isolate the contribution
of regime-awareness.

Flow:
    1. Load EUR-USD 1m warmup + trading candles via qengine.research.candles
       for 2022-01-01 → 2023-12-31 (the strategy runs at 30m).
    2. Build a RingEvolver with 8 islands × 10 individuals (gene bounds
       derived from the Martingale strategy's hyperparameters()).
    3. For 10 generations:
         - evaluate every genome in every island via a REAL backtest
         - evolve each population (tournament/crossover/mutation/elitism)
         - at generation 5, perform a ring migration
    4. Save evolver state to
       pipelines/_shared/IGTSPRingPilot/models/evolver.json
    5. Plot per-island best fitness over generations to
       notebooks/phase5/plots/52_igtsp_convergence.png

Run a smoke pass by setting SMOKE=1 in the environment:
    SMOKE=1 python3 52_igtsp_ring_train.py
This shrinks to 2 generations × 4 islands × 4 individuals on a 1-month window.

Reference paper:
    Chideme, K., Chen, C.-H., & Lin, J. C.-W. (2025). Engineering Optimization.
    DOI: 10.1080/0305215X.2025.2592030
"""
import json
import os
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Ensure repo root is on sys.path and cwd so qengine relative imports work
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

import qengine.helpers as jh
from qengine.research.backtest import backtest
from qengine.research.candles import get_candles
from qengine.framework.components.island_evolver import (
    GENE_BOUNDS,
    build_gene_bounds_from_strategy,
)

from pipelines._shared.IGTSPRingPilot.ring_evolver import RingEvolver


# ── Config ─────────────────────────────────────────────────────────────────

SMOKE = os.environ.get("SMOKE", "0") == "1"

EX, SYM = "OANDA", "EUR-USD"
KEY = f"{EX}-{SYM}"
TF = "30m"
STRATEGY = "Martingale"

if SMOKE:
    TRAIN_START, TRAIN_END = "2023-01-01", "2023-02-01"
    N_ISLANDS = 4
    POP_SIZE = 4
    N_GENERATIONS = 2
    MIGRATION_AT_GEN = 1  # migrate at gen 1 in smoke mode (and every interval after)
    MIGRATION_INTERVAL = 1
else:
    TRAIN_START, TRAIN_END = "2022-01-01", "2023-12-31"
    N_ISLANDS = 8
    POP_SIZE = 10
    N_GENERATIONS = 10
    MIGRATION_AT_GEN = 5
    MIGRATION_INTERVAL = 5

STARTING_BALANCE = 10000.0
BUST_FLOOR = -50.0  # heuristic: single-cycle PnL below this counts as a bust

OUT_MODELS = (
    ROOT
    / "pipelines"
    / "_shared"
    / "IGTSPRingPilot"
    / "models"
    / "evolver.json"
)
PLOTS_DIR = ROOT / "notebooks" / "phase5" / "plots"
PLOT_PATH = PLOTS_DIR / "52_igtsp_convergence.png"

OUT_MODELS.parent.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Load candles ───────────────────────────────────────────────────────────

print(
    f"[52] Loading {EX} {SYM} 1m candles "
    f"{TRAIN_START} → {TRAIN_END} (SMOKE={SMOKE})..."
)
t0 = time.time()
warmup_1m, trading_1m = get_candles(
    exchange=EX,
    symbol=SYM,
    timeframe="1m",
    start_date_timestamp=jh.date_to_timestamp(TRAIN_START),
    finish_date_timestamp=jh.date_to_timestamp(TRAIN_END),
    warmup_candles_num=10000,
)
print(
    f"[52]   loaded {len(trading_1m)} trading 1m candles in "
    f"{time.time() - t0:.1f}s"
)


def _warmup_dict(w):
    """Return warmup dict only if warmup has real 2-D data (see MEMORY.md)."""
    if w is None:
        return None
    if not (isinstance(w, np.ndarray) and w.ndim == 2 and len(w) > 0):
        return None
    return {KEY: {"exchange": EX, "symbol": SYM, "candles": w}}


# ── Discover strategy gene bounds ──────────────────────────────────────────

# We need a strategy instance just to call hyperparameters() for bound discovery.
# Importing the strategy module directly is the cheapest path.
import importlib.util

strat_path = ROOT / "strategies" / "_admin" / "Martingale" / "__init__.py"
spec = importlib.util.spec_from_file_location(
    "strategies._admin.Martingale", str(strat_path)
)
strat_mod = importlib.util.module_from_spec(spec)
sys.modules["strategies._admin.Martingale"] = strat_mod
spec.loader.exec_module(strat_mod)

strat_cls = getattr(strat_mod, STRATEGY)


class _StratShim:
    """Minimal shim — only hyperparameters() is needed for bound discovery."""

    def hyperparameters(self_inner):
        return strat_cls.hyperparameters(strat_cls)


gene_bounds = build_gene_bounds_from_strategy(_StratShim())
if not gene_bounds:
    gene_bounds = dict(GENE_BOUNDS)
print(f"[52] Discovered {len(gene_bounds)} tunable genes from strategy")


# ── Genome → strategy HP mapping (same as IslandPilot for fairness) ────────

from qengine.framework.components.island_evolver import SIZING_CURVE_MAP  # noqa: E402

_CAT_MAPS = {
    "sizing_curve": SIZING_CURVE_MAP,
    "base_size_mode": {0: "pct_equity", 1: "capital_aware"},
    "hedge_mode": {0: "fixed_pips", 1: "atr_based", 2: "percentage"},
    "tp_mode": {0: "fixed_pips", 1: "atr_based", 2: "bucket_pct", 3: "risk_reward"},
    "hedge_expand": {0: "no", 1: "yes"},
}

_INT_GENES = {"max_levels", "hedge_atr_period", "tp_atr_period"}


def genome_to_hp(genes: dict) -> dict:
    hp = {"preset": "custom"}
    for g, v in genes.items():
        if g in _CAT_MAPS and isinstance(v, (int, float)):
            mapping = _CAT_MAPS[g]
            idx = int(round(v))
            idx = max(0, min(idx, max(mapping.keys())))
            hp[g] = mapping[idx]
        elif g in _INT_GENES and isinstance(v, float):
            hp[g] = int(round(v))
        else:
            hp[g] = v
    return hp


# ── Fitness (matches IslandPilot for fair comparison) ──────────────────────

def fitness_from_result(m: dict, n_min_sessions: int = 5) -> float:
    pf = m.get("profit_factor", 0.0) or 0.0
    max_dd = abs(m.get("max_drawdown", -100) or 0.0)
    sessions = m.get("total_sessions", 0) or 0
    bust_rate = m.get("bust_rate", None)
    if bust_rate is None:
        # Some versions don't expose bust_rate — default neutral
        bust_rate = 0.5
    if sessions < n_min_sessions:
        return -1000.0
    return (
        0.4 * (pf - 1.0) * 100
        + 0.3 * max(0.0, 100 - max_dd * 5)
        + 0.2 * (1.0 - bust_rate) * 100
        + 0.1 * min(sessions / 100.0, 1.0) * 100
    )


def evaluate_genome(genes: dict) -> float:
    candles = {KEY: {"exchange": EX, "symbol": SYM, "candles": trading_1m}}
    warmup = _warmup_dict(warmup_1m)
    hp = genome_to_hp(genes)
    try:
        result = backtest(
            config={
                "starting_balance": STARTING_BALANCE,
                "fee": 0,
                "type": "cfd",
                "exchange": EX,
                "warm_up_candles": 10000,
            },
            routes=[
                {
                    "exchange": EX,
                    "symbol": SYM,
                    "timeframe": TF,
                    "strategy": STRATEGY,
                }
            ],
            data_routes=[],
            candles=candles,
            warmup_candles=warmup,
            hyperparameters=hp,  # flat dict — route-keyed form is silently ignored by backtest_mode.py:864
            generate_equity_curve=False,
            generate_logs=False,
        )
        m = result.get("metrics", {}) or {}
        return fitness_from_result(m)
    except Exception as e:
        print(f"    [eval] genome failed: {e}")
        return -1000.0


# ── Build evolver ──────────────────────────────────────────────────────────

leaf_ids = [f"pop_{i}" for i in range(N_ISLANDS)]
evolver = RingEvolver(
    leaf_ids=leaf_ids,
    config={
        "pop_size": POP_SIZE,
        "elitism": 1,
        "crossover_rate": 0.7,
        "mutation_rate": 0.2,
        "mutation_sigma": 0.1,
        "tournament_k": 3,
    },
    gene_bounds=gene_bounds,
)

print(
    f"[52] RingEvolver: {len(evolver.populations)} islands × "
    f"{POP_SIZE} genomes = {len(evolver.populations) * POP_SIZE} backtests/gen"
)
total_backtests = len(evolver.populations) * POP_SIZE * N_GENERATIONS
print(f"[52] Total evaluations (10 gens): {total_backtests}")


# ── Evolve ─────────────────────────────────────────────────────────────────

# Track per-island best fitness across generations for the convergence plot.
# Shape: [n_islands][n_generations]
history = {lid: [] for lid in leaf_ids}

for gen in range(1, N_GENERATIONS + 1):
    gen_start = time.time()
    print(f"\n=== Generation {gen}/{N_GENERATIONS} ===")

    # Evaluate every individual that still lacks fitness
    for lid in leaf_ids:
        pop = evolver.populations[lid]
        for ind in pop.individuals:
            if ind.fitness is None:
                ind.fitness = evaluate_genome(ind.genes)

    # Record per-island best BEFORE evolving (so history[i] reflects gen i)
    for lid in leaf_ids:
        pop = evolver.populations[lid]
        best = max(
            pop.individuals,
            key=lambda g: g.fitness if g.fitness is not None else -np.inf,
        )
        history[lid].append(best.fitness if best.fitness is not None else np.nan)
        print(
            f"  [{lid}] best fitness={best.fitness:.3f} "
            f"mean={np.mean([g.fitness for g in pop.individuals if g.fitness is not None]):.3f}"
        )

    # Evolve each population (tournament/crossover/mutation/elitism)
    for lid in leaf_ids:
        pop = evolver.populations[lid]
        pop.evolve(
            elitism=1,
            crossover_rate=0.7,
            mutation_rate=0.2,
            mutation_sigma=0.1,
            tournament_k=3,
        )

    # Ring migration: at gen == MIGRATION_AT_GEN, and every MIGRATION_INTERVAL thereafter
    if gen == MIGRATION_AT_GEN or (
        gen > MIGRATION_AT_GEN
        and (gen - MIGRATION_AT_GEN) % MIGRATION_INTERVAL == 0
    ):
        evolver._generation = gen
        evolver.migrate_ring()
        print(
            f"  [ring] migrated — total migrations: "
            f"{len(evolver.migration_log)}"
        )

    print(f"  generation time: {time.time() - gen_start:.1f}s")


# ── Save artefacts ─────────────────────────────────────────────────────────

evolver.save(str(OUT_MODELS))
print(f"\n[52] Saved evolver state → {OUT_MODELS}")

# Report global best
best = evolver.get_global_best()
if best is not None:
    print(f"[52] Global best fitness={best.get('fitness'):.3f} "
          f"island={best.get('island_id')}")
    print(f"     genes: {best.get('genes')}")


# ── Convergence plot ───────────────────────────────────────────────────────

plt.figure(figsize=(10, 5))
gens_x = np.arange(1, N_GENERATIONS + 1)
for lid in leaf_ids:
    plt.plot(gens_x, history[lid], marker="o", label=lid, alpha=0.85)
# Mark the migration generation(s)
for gen in range(1, N_GENERATIONS + 1):
    if gen == MIGRATION_AT_GEN or (
        gen > MIGRATION_AT_GEN
        and (gen - MIGRATION_AT_GEN) % MIGRATION_INTERVAL == 0
    ):
        plt.axvline(gen, color="grey", linestyle="--", alpha=0.35)
plt.xlabel("Generation")
plt.ylabel("Best fitness")
plt.title(
    f"IGTSPRingPilot — per-island best fitness "
    f"(N={N_ISLANDS}, pop={POP_SIZE}, gens={N_GENERATIONS})"
)
plt.legend(loc="best", fontsize=8, ncol=2)
plt.grid(True, alpha=0.25)
plt.tight_layout()
plt.savefig(str(PLOT_PATH), dpi=120)
plt.close()
print(f"[52] Saved convergence plot → {PLOT_PATH}")


# Dump a small summary JSON next to plots for quick reading
summary = {
    "smoke": SMOKE,
    "n_islands": N_ISLANDS,
    "pop_size": POP_SIZE,
    "n_generations": N_GENERATIONS,
    "migration_at": MIGRATION_AT_GEN,
    "migration_interval": MIGRATION_INTERVAL,
    "train_start": TRAIN_START,
    "train_end": TRAIN_END,
    "history": {lid: [None if (v is None or np.isnan(v)) else float(v)
                      for v in history[lid]] for lid in leaf_ids},
    "n_migrations": len(evolver.migration_log),
    "global_best": best,
}
summary_path = PLOTS_DIR.parent / "52_igtsp_summary.json"
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2, default=str)
print(f"[52] Saved summary → {summary_path}")

print("\n[52] Done.")
