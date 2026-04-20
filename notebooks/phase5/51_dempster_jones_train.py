"""
51 — Offline seed training for DempsterJonesPilot.

Runs a short initial GA using nested qengine backtests to produce a warm
starting population. The resulting population is saved to
    pipelines/_shared/DempsterJonesPilot/models/initial_population.json

and auto-loaded by the pipeline on construction. The online walk-forward
GA then takes over from this seed.

Usage:
    /Users/naresh/miniconda3/bin/python3 notebooks/phase5/51_dempster_jones_train.py [--smoke]

--smoke flag shrinks the training window + population for a quick smoke test.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

# Make project importable + set cwd (qengine checks for strategies/ etc.)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

import numpy as np

import qengine.helpers as jh
from qengine.research.backtest import backtest
from qengine.research.candles import get_candles

from pipelines._shared.DempsterJonesPilot.walk_forward_ga import (
    WalkForwardGA,
    Genome,
    build_gene_bounds_from_strategy,
    composite_fitness,
    SAFE_CATEGORICAL_OPTIONS,
)
from pipelines._shared.DempsterJonesPilot.config import DEFAULT_CONFIG


# --------------------------------------------------------------------------
# CLI / paths
# --------------------------------------------------------------------------

PIPELINE_DIR = PROJECT_ROOT / "pipelines" / "_shared" / "DempsterJonesPilot"
MODELS_DIR = PIPELINE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = MODELS_DIR / "initial_population.json"


def _parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="Quick smoke test: 3 months, pop=6, 2 generations.")
    ap.add_argument("--train-start", default="2022-01-01")
    ap.add_argument("--train-end", default="2023-12-31")
    ap.add_argument("--pop-size", type=int, default=20)
    ap.add_argument("--generations", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    return ap.parse_args()


# --------------------------------------------------------------------------
# Fitness via nested backtests
# --------------------------------------------------------------------------

def _build_hp_from_genome(genes: dict, strategy_cls) -> dict:
    """Map genome genes onto strategy hyperparameter overrides.

    Mirrors IslandPilot._apply_genome logic so seed population explores the
    same execution space as the online GA does at runtime.
    """
    try:
        hp_list = strategy_cls().hyperparameters()
    except Exception:
        return {"preset": "custom"}

    specs = {h["name"]: h for h in hp_list if isinstance(h, dict) and "name" in h}
    tunable_groups = {"General", "Grid / Hedge", "Take Profit"}
    hp = {"preset": "custom"}

    for hp_name, spec in specs.items():
        if spec.get("group", "") not in tunable_groups:
            continue
        if hp_name not in genes:
            continue

        val = genes[hp_name]
        hp_type = spec.get("type")
        if hp_type == "categorical":
            options = spec.get("options", [])
            safe = SAFE_CATEGORICAL_OPTIONS.get(hp_name)
            if safe:
                options = [o for o in options if o in safe]
            if not options:
                continue
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                idx = max(0, min(int(round(val)), len(options) - 1))
                hp[hp_name] = options[idx]
            elif val in options:
                hp[hp_name] = val
        elif hp_type in (int, float) or hp_type in ("int", "float"):
            try:
                lo = spec.get("min", float("-inf"))
                hi = spec.get("max", float("inf"))
                num = max(lo, min(hi, float(val)))
                if hp_type in (int, "int"):
                    num = int(round(num))
                hp[hp_name] = num
            except (TypeError, ValueError):
                continue
    return hp


def make_fitness_fn(trading_1m, warmup_1m, strategy_cls,
                    exchange="OANDA", symbol="EUR-USD",
                    weights=None):
    """Build a fitness function that runs a real backtest per genome.

    Returns fitness (float) — returns a strongly negative value on failure
    so the GA discards broken configs.
    """
    key = f"{exchange}-{symbol}"
    weights = weights or DEFAULT_CONFIG["fitness"]

    def fitness_fn(genes: dict) -> float:
        hp = _build_hp_from_genome(genes, strategy_cls)
        candles_dict = {key: {"exchange": exchange, "symbol": symbol,
                              "candles": trading_1m}}
        warmup_dict = None
        if warmup_1m is not None and warmup_1m.ndim == 2 and len(warmup_1m) > 0:
            warmup_dict = {key: {"exchange": exchange, "symbol": symbol,
                                 "candles": warmup_1m}}

        try:
            result = backtest(
                config={
                    "starting_balance": 10000,
                    "fee": 0,
                    "type": "cfd",
                    "exchange": exchange,
                    "warm_up_candles": 10000,
                },
                routes=[{"exchange": exchange, "symbol": symbol,
                         "timeframe": "30m", "strategy": "Martingale"}],
                data_routes=[],
                candles=candles_dict,
                warmup_candles=warmup_dict,
                hyperparameters=hp,  # flat dict — route-keyed form is silently ignored by backtest_mode.py:864
                generate_equity_curve=False,
                generate_logs=False,
            )
        except Exception as e:
            print(f"  [genome failed: {type(e).__name__}: {e}]")
            return -1000.0

        m = result.get("metrics", {})
        pf = m.get("profit_factor", 0) or 0
        max_dd = abs(m.get("max_drawdown", -100) or -100)
        sessions = m.get("total_sessions", 0) or 0
        bust_rate = m.get("bust_rate", 1.0)
        if bust_rate is None:
            bust_rate = 1.0

        if sessions < 5:
            return -500.0

        return composite_fitness(pf=float(pf), max_dd=float(max_dd),
                                 bust_rate=float(bust_rate),
                                 sessions=int(sessions), weights=weights)

    return fitness_fn


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    args = _parse_args()

    if args.smoke:
        args.train_start = "2022-01-01"
        args.train_end = "2022-03-31"
        args.pop_size = 6
        args.generations = 2
        print(f"[smoke mode] train {args.train_start} → {args.train_end}, "
              f"pop={args.pop_size}, gens={args.generations}")

    # 1. Load EUR-USD 1m candles
    ex, sym = "OANDA", "EUR-USD"
    print(f"Loading candles {args.train_start} → {args.train_end} ...")
    t0 = time.time()
    warmup_1m, trading_1m = get_candles(
        exchange=ex, symbol=sym, timeframe="1m",
        start_date_timestamp=jh.date_to_timestamp(args.train_start),
        finish_date_timestamp=jh.date_to_timestamp(args.train_end),
        warmup_candles_num=10000,
    )
    print(f"  Loaded {len(trading_1m)} trading + "
          f"{len(warmup_1m) if warmup_1m.ndim == 2 else 0} warmup candles "
          f"({time.time() - t0:.1f}s)")

    # 2. Instantiate strategy to discover gene bounds
    from strategies._admin.Martingale import Martingale
    bounds = build_gene_bounds_from_strategy(Martingale())
    print(f"Gene bounds discovered: {len(bounds)} genes")
    for name, (lo, hi, dt) in list(bounds.items())[:10]:
        print(f"  {name}: [{lo}, {hi}] {dt.__name__}")
    if len(bounds) > 10:
        print(f"  ... ({len(bounds) - 10} more)")

    # 3. Build GA
    ga = WalkForwardGA(
        bounds=bounds,
        population_size=args.pop_size,
        elitism=max(1, args.pop_size // 10),
        crossover_rate=0.7,
        mutation_rate=0.2,
        mutation_sigma=0.05,
        tournament_k=3,
        seed=args.seed,
    )

    # 4. Build fitness fn
    fitness_fn = make_fitness_fn(trading_1m, warmup_1m, Martingale,
                                 exchange=ex, symbol=sym)

    # 5. Evolve
    print(f"\nRunning {args.generations} generations "
          f"({args.pop_size} genomes each, nested backtest per eval):")
    for g in range(args.generations):
        g_start = time.time()
        stats = ga.step(fitness_fn)
        elapsed = time.time() - g_start
        print(f"  gen {ga.generation:>2}  best={stats['best']:8.3f}  "
              f"mean={stats['mean']:8.3f}  worst={stats['worst']:8.3f}  "
              f"({elapsed:.0f}s)")

    # Final evaluation of current population so saved fitness reflects it
    ga.evaluate(fitness_fn)

    # 6. Save seed population
    data = {
        "meta": {
            "train_start": args.train_start,
            "train_end": args.train_end,
            "pop_size": args.pop_size,
            "generations": args.generations,
            "seed": args.seed,
        },
        "population": [g.to_dict() for g in ga.population],
    }
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\nSaved {len(ga.population)} genomes → {OUT_PATH}")

    # Print top 3 for quick eyeballing
    ranked = sorted(
        ga.population,
        key=lambda g: g.fitness if g.fitness is not None else -np.inf,
        reverse=True,
    )
    print("\nTop 3 genomes:")
    for i, g in enumerate(ranked[:3], 1):
        genes_str = {k: (round(v, 4) if isinstance(v, float) else v)
                     for k, v in g.genes.items()
                     if isinstance(v, (int, float, str, bool))}
        print(f"  #{i}  fitness={g.fitness}")
        print(f"      genes={genes_str}")

    print("\nDone.")


if __name__ == "__main__":
    main()
