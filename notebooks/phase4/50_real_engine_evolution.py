"""
50 — Real Engine Island Evolution

Trains IslandPilot genomes using the ACTUAL qengine backtest engine instead
of the toy simulator. Each genome evaluation runs a real backtest with spread,
slippage, and proper order execution.

Flow:
1. Load regime tree from phase4 models (already trained)
2. For each regime island, evolve a population of genomes
3. Fitness = real backtest PF on training data subset
4. Save trained models for pipeline deployment
"""

import sys, os, json, time, copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.chdir(str(Path(__file__).resolve().parents[2]))

import numpy as np
from qengine.research.backtest import backtest
from qengine.research.candles import get_candles
from qengine.framework.components.regime_tree import RegimeTree
from qengine.framework.components.island_evolver import IslandEvolver, Genome, GENE_BOUNDS, build_gene_bounds_from_strategy
from qengine.framework.components.feature_selector import FeaturePool
import qengine.helpers as jh

MODELS_DIR = Path(__file__).resolve().parent / 'results' / 'models'
PIPELINE_MODELS = Path(__file__).resolve().parents[2] / 'pipelines' / '_shared' / 'IslandPilot' / 'models'

print("Loading models and data...")

# Load regime tree
tree = RegimeTree.load(str(MODELS_DIR / 'regime_tree.pkl'))
print(f"Tree: {tree.n_leaves} leaves, {tree.n_macro} macro clusters")

# Load 1m candles for training period
ex, sym = 'OANDA', 'EUR-USD'
key = f'{ex}-{sym}'

train_start, train_end = '2022-01-01', '2023-12-31'  # 2 years training
warmup_1m, trading_1m = get_candles(
    exchange=ex, symbol=sym, timeframe='1m',
    start_date_timestamp=jh.date_to_timestamp(train_start),
    finish_date_timestamp=jh.date_to_timestamp(train_end),
    warmup_candles_num=10000)

print(f"Training data: {len(trading_1m)} 1m candles ({train_start} to {train_end})")


def evaluate_genome(genes: dict) -> float:
    """Evaluate a genome by running a real qengine backtest.

    Returns fitness score combining PF, drawdown control, and session count.
    """
    candles = {key: {'exchange': ex, 'symbol': sym, 'candles': trading_1m}}
    warmup_dict = {key: {'exchange': ex, 'symbol': sym, 'candles': warmup_1m}} if warmup_1m.ndim == 2 and len(warmup_1m) > 0 else None

    # Build HP overrides from genome (only General + Grid/Hedge + TP)
    hp = {'preset': 'original'}

    # Map genome genes to strategy HP names
    gene_to_hp = {
        'sizing_curve': 'sizing_curve',
        'sizing_factor': 'sizing_factor',
        'base_size_mode': 'base_size_mode',
        'base_size_value': 'base_size_value',
        'max_levels': 'max_levels',
        'hedge_mode': 'hedge_mode',
        'hedge_value': 'hedge_value',
        'hedge_atr_period': 'hedge_atr_period',
        'hedge_expand': 'hedge_expand',
        'hedge_expand_factor': 'hedge_expand_factor',
        'tp_mode': 'tp_mode',
        'tp_value': 'tp_value',
        'tp_atr_period': 'tp_atr_period',
    }

    # Categorical mappings
    from qengine.framework.components.island_evolver import SIZING_CURVE_MAP
    cat_maps = {
        'sizing_curve': {0: 'geometric', 1: 'sqrt', 2: 'linear', 3: 'fibonacci'},
        'base_size_mode': {0: 'pct_equity', 1: 'capital_aware'},
        'hedge_mode': {0: 'fixed_pips', 1: 'atr_based', 2: 'percentage'},
        'hedge_expand': {0: 'no', 1: 'yes'},
        'tp_mode': {0: 'fixed_pips', 1: 'atr_based', 2: 'bucket_pct', 3: 'risk_reward'},
    }

    for gene_name, hp_name in gene_to_hp.items():
        if gene_name in genes:
            val = genes[gene_name]
            if gene_name in cat_maps:
                if isinstance(val, (int, float)):
                    val = cat_maps[gene_name].get(int(round(val)), list(cat_maps[gene_name].values())[0])
            elif isinstance(val, float) and gene_name in ('max_levels', 'hedge_atr_period', 'tp_atr_period'):
                val = int(round(val))
            hp[hp_name] = val

    try:
        result = backtest(
            config={'starting_balance': 10000, 'fee': 0, 'type': 'cfd', 'exchange': ex, 'warm_up_candles': 10000},
            routes=[{'exchange': ex, 'symbol': sym, 'timeframe': '30m', 'strategy': 'Martingale'}],
            data_routes=[],
            candles=candles,
            warmup_candles=warmup_dict,
            hyperparameters={key: hp},
            generate_equity_curve=False,
            generate_logs=False,
        )

        m = result.get('metrics', {})
        pf = m.get('profit_factor', 0)
        net_pct = m.get('net_profit_percentage', 0)
        max_dd = abs(m.get('max_drawdown', -100))
        sessions = m.get('total_sessions', 0)
        bust_rate = m.get('bust_rate', 1.0)

        if sessions < 10:
            return -1000.0  # Too few sessions

        # Fitness: weighted combination emphasising risk-adjusted return
        # PF > 1 is positive, drawdown penalty, bust penalty, session bonus
        fitness = (
            0.4 * (pf - 1.0) * 100  # PF contribution (0 at breakeven)
            + 0.3 * max(0, 100 - max_dd * 5)  # DD penalty (lower DD = higher)
            + 0.2 * (1.0 - bust_rate) * 100  # Bust avoidance
            + 0.1 * min(sessions / 100, 1.0) * 100  # Session count (capped at 100)
        )

        return fitness

    except Exception as e:
        return -1000.0


# Create evolver with proper gene bounds
print("\nCreating evolver...")
leaf_ids = [str(lid) for lid in tree.leaf_ids]

# Use a small population and few generations since each eval is a full backtest
evolver = IslandEvolver(
    leaf_ids=leaf_ids,
    config={
        'pop_size': 5,  # Small population - each eval is expensive
        'elitism': 1,
        'crossover_rate': 0.7,
        'mutation_rate': 0.3,
        'mutation_sigma': 0.1,
        'tournament_k': 2,
    }
)

print(f"Evolver: {len(evolver.populations)} islands, {5} genomes each")
print(f"Total evaluations per generation: {len(evolver.populations) * 5} = {len(evolver.populations) * 5} backtests")
print(f"Estimated time per generation: {len(evolver.populations) * 5 * 30}s = {len(evolver.populations) * 5 * 30 / 60:.0f} minutes")

# Run evolution - just 3 generations given cost
MAX_GENS = 3
print(f"\nRunning {MAX_GENS} generations...")

for gen in range(MAX_GENS):
    gen_start = time.time()
    print(f"\n=== Generation {gen+1}/{MAX_GENS} ===")

    eval_count = 0
    for lid in evolver.leaf_ids[:10]:  # Only first 10 islands to limit time
        pop = evolver.populations.get(lid)
        if pop is None:
            continue

        for ind in pop.individuals:
            if ind.fitness is None:
                ind.fitness = evaluate_genome(ind.genes)
                eval_count += 1
                if eval_count % 5 == 0:
                    elapsed = time.time() - gen_start
                    print(f"  Evaluated {eval_count} genomes ({elapsed:.0f}s)")

    # Evolve populations
    for lid in evolver.leaf_ids[:10]:
        pop = evolver.populations.get(lid)
        if pop is None:
            continue
        pop.evolve(elitism=1, crossover_rate=0.7, mutation_rate=0.3, mutation_sigma=0.1, tournament_k=2)

    # Report best per island
    gen_elapsed = time.time() - gen_start
    print(f"\n  Generation {gen+1} completed in {gen_elapsed:.0f}s")
    for lid in evolver.leaf_ids[:10]:
        pop = evolver.populations.get(lid)
        if pop:
            best = max(pop.individuals, key=lambda x: x.fitness if x.fitness is not None else -9999)
            if best.fitness is not None:
                print(f"  Island {lid}: best fitness = {best.fitness:.2f}")

# Save models
print("\nSaving models...")
evolver.save(str(MODELS_DIR / 'island_evolver.json'))
evolver.save(str(PIPELINE_MODELS / 'island_evolver.json'))

# Also save simple genomes
genomes_data = {}
for lid in evolver.leaf_ids:
    try:
        gd = evolver.get_best_genome(lid)
        if gd:
            genomes_data[lid] = gd
    except:
        pass

with open(str(MODELS_DIR / 'island_genomes.json'), 'w') as f:
    json.dump(genomes_data, f, indent=2)
with open(str(PIPELINE_MODELS / 'island_genomes.json'), 'w') as f:
    json.dump(genomes_data, f, indent=2)

print(f"Saved {len(genomes_data)} genomes to models/")
print("Done.")
