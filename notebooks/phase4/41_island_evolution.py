"""
Script 41 — Island Evolution
==============================
Loads the regime tree from script 40, generates EMA 8/21 crossover signals,
assigns them to leaf islands, and runs a genetic algorithm to evolve
per-regime surefire parameters.

Part of Phase 4 (IslandPilot) research.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils import (
    load_candles, concat_candles, save_results, load_results, savefig,
    get_logger, MODELS_DIR, RESULTS_DIR, CycleResult, SimConfig, calc_size,
    cycle_summary,
)

import json
import os
import numpy as np
import numba
import matplotlib.pyplot as plt

from qengine.framework.components.island_evolver import (
    IslandEvolver, Genome, GENE_BOUNDS,
)
from qengine.framework.components.regime_tree import RegimeTree
from qengine.framework.components.feature_selector import (
    FeaturePool, compute_feature_matrix,
)
import qengine.indicators as ta

log = get_logger('41_island_evolution')

# ── configuration ────────────────────────────────────────────────────────────

GA_GENERATIONS = 100
EARLY_STOP_PATIENCE = 15
MIN_SIGNALS_PER_ISLAND = 20
MIGRATION_EVERY = 5  # generations


# ── signal generation ────────────────────────────────────────────────────────

def generate_crossover_signals(candles: np.ndarray) -> list:
    """Generate EMA 8/21 crossover entry signals.

    Returns list of dicts: {idx, direction, entry_price}.
    Crossover = fast crosses above slow (long) or below (short).
    """
    ema_fast = ta.ema(candles, period=8, sequential=True)
    ema_slow = ta.ema(candles, period=21, sequential=True)

    signals = []
    for i in range(1, len(candles)):
        if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]):
            continue
        if np.isnan(ema_fast[i-1]) or np.isnan(ema_slow[i-1]):
            continue

        # Bullish crossover
        if ema_fast[i-1] <= ema_slow[i-1] and ema_fast[i] > ema_slow[i]:
            signals.append({
                'idx': i,
                'direction': 'long',
                'entry_price': float(candles[i, 2]),  # close
            })
        # Bearish crossover
        elif ema_fast[i-1] >= ema_slow[i-1] and ema_fast[i] < ema_slow[i]:
            signals.append({
                'idx': i,
                'direction': 'short',
                'entry_price': float(candles[i, 2]),  # close
            })

    return signals


# ── cycle simulator (Numba JIT compiled) ─────────────────────────────────────
#
# The inner loop is compiled to machine code via @numba.njit.
# Same logic as the Python version — just ~50-100x faster.
# Returns raw floats: (bust, level_reached, pnl, bars_held)

# Pre-compute sizing tables for each curve type (avoids string ops in JIT)
# curve_id: 0=geometric, 1=sqrt, 2=linear, 3=fibonacci
_FIB = np.array([1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233], dtype=np.float64)


@numba.njit(cache=True)
def _calc_size_jit(level, curve_id, factor, base_size):
    """Position size at hedge level (JIT)."""
    if curve_id == 0:  # geometric
        return base_size * (factor ** level)
    elif curve_id == 1:  # sqrt
        return base_size * (factor ** 0.5) ** level
    elif curve_id == 2:  # linear
        return base_size * (1.0 + level)
    elif curve_id == 3:  # fibonacci
        idx = min(level, 12)
        return base_size * _FIB[idx]
    return base_size


@numba.njit(cache=True)
def _simulate_cycle_jit(
    close_arr, high_arr, low_arr,
    entry_idx, direction_int,  # +1 = long, -1 = short
    base_size, curve_id, sizing_factor,
    tp_pips, hedge_dist_pips, max_levels, max_bars,
):
    """JIT-compiled surefire cycle simulator.

    Returns: (bust_int, level_reached, pnl, bars_held)
      bust_int: 1 = bust, 0 = win
    """
    pip = 0.0001
    n = len(close_arr)

    # Position arrays (pre-allocate for max_levels+1 positions)
    max_pos = max_levels + 2
    pos_dir = np.zeros(max_pos, dtype=np.float64)    # +1 or -1
    pos_entry = np.zeros(max_pos, dtype=np.float64)
    pos_size = np.zeros(max_pos, dtype=np.float64)

    entry_price = close_arr[entry_idx]
    pos_dir[0] = direction_int
    pos_entry[0] = entry_price
    pos_size[0] = base_size
    n_pos = 1

    current_level = 0
    current_dir = direction_int  # +1 long, -1 short
    last_entry_price = entry_price

    for bar in range(1, max_bars + 1):
        ci = entry_idx + bar
        if ci >= n:
            # Out of data — bust
            exit_price = close_arr[n - 1]
            pnl = 0.0
            for p in range(n_pos):
                pnl += pos_dir[p] * (exit_price - pos_entry[p]) / pip * pos_size[p]
            return 1, current_level, pnl, bar

        high = high_arr[ci]
        low = low_arr[ci]
        close = close_arr[ci]

        # TP price: tp_pips beyond last entry in current direction
        if current_dir > 0:
            tp_price = last_entry_price + tp_pips * pip
        else:
            tp_price = last_entry_price - tp_pips * pip

        # Check TP hit
        tp_hit = False
        if current_dir > 0 and high >= tp_price:
            tp_hit = True
        elif current_dir < 0 and low <= tp_price:
            tp_hit = True

        if tp_hit:
            pnl = 0.0
            for p in range(n_pos):
                pnl += pos_dir[p] * (tp_price - pos_entry[p]) / pip * pos_size[p]
            return 0, current_level, pnl, bar

        # Hedge price
        if current_dir > 0:
            hedge_price = last_entry_price - hedge_dist_pips * pip
        else:
            hedge_price = last_entry_price + hedge_dist_pips * pip

        # Check hedge trigger
        hedge_hit = False
        if current_dir > 0 and low <= hedge_price:
            hedge_hit = True
        elif current_dir < 0 and high >= hedge_price:
            hedge_hit = True

        if hedge_hit:
            current_level += 1
            if current_level > max_levels:
                pnl = 0.0
                for p in range(n_pos):
                    pnl += pos_dir[p] * (close - pos_entry[p]) / pip * pos_size[p]
                return 1, current_level - 1, pnl, bar
            # Flip direction, add position
            current_dir = -current_dir
            new_size = _calc_size_jit(current_level, curve_id, sizing_factor, base_size)
            pos_dir[n_pos] = current_dir
            pos_entry[n_pos] = hedge_price
            pos_size[n_pos] = new_size
            n_pos += 1
            last_entry_price = hedge_price

    # Max bars — bust
    exit_price = close_arr[min(entry_idx + max_bars, n - 1)]
    pnl = 0.0
    for p in range(n_pos):
        pnl += pos_dir[p] * (exit_price - pos_entry[p]) / pip * pos_size[p]
    return 1, current_level, pnl, max_bars


# Sizing curve name → int mapping for JIT
_CURVE_MAP = {'geometric': 0, 'sqrt': 1, 'linear': 2, 'fibonacci': 3}


def simulate_cycle(candles, entry_idx, direction, cfg):
    """Wrapper: calls JIT simulator, returns CycleResult."""
    direction_int = 1 if direction == 'long' else -1
    curve_id = _CURVE_MAP.get(cfg.sizing_curve, 1)

    bust_int, level, pnl, bars = _simulate_cycle_jit(
        candles[:, 2], candles[:, 3], candles[:, 4],
        entry_idx, direction_int,
        cfg.base_size, curve_id, cfg.sizing_factor,
        cfg.tp_pips, cfg.hedge_dist_pips, cfg.max_levels, cfg.max_bars,
    )
    return CycleResult(
        bust=bool(bust_int), level_reached=int(level),
        pnl=float(pnl), bars_held=int(bars),
        entry_idx=entry_idx, direction=direction,
    )


# ── fitness function factory ─────────────────────────────────────────────────

# Max bars per cycle for fitness eval (most cycles resolve within 200 bars;
# 500 is generous while 10x faster than the default 5000)
_FITNESS_MAX_BARS = 500
# Max signals to evaluate per genome (stochastic fitness — rotated each call)
_FITNESS_SAMPLE_SIZE = 60


def make_fitness_fn(candles, signals_for_island):
    """Create a fitness function that evaluates a genome on island signals.

    Uses stochastic sub-sampling: each call evaluates a random subset of signals
    (rotated via a counter), keeping evaluation fast while covering all signals
    over multiple generations.
    """
    n_signals = len(signals_for_island)
    _call_count = [0]  # mutable counter for rotation

    # Precompute signal indices and directions as arrays for fast access
    sig_indices = np.array([s['idx'] for s in signals_for_island], dtype=np.int64)
    sig_dirs = [s['direction'] for s in signals_for_island]

    def fitness_fn(genes: dict) -> float:
        cfg = SimConfig.from_genome({'genes': genes})
        cfg.max_bars = _FITNESS_MAX_BARS

        # Stochastic sub-sample: rotate through signals
        _call_count[0] += 1
        if n_signals <= _FITNESS_SAMPLE_SIZE:
            sample_idx = range(n_signals)
        else:
            rng = np.random.RandomState(_call_count[0] % 10000)
            sample_idx = rng.choice(n_signals, _FITNESS_SAMPLE_SIZE, replace=False)

        wins = 0
        busts = 0
        total_pnl = 0.0
        gross_profit = 0.0
        gross_loss = 0.0

        for si in sample_idx:
            res = simulate_cycle(candles, int(sig_indices[si]), sig_dirs[si], cfg)
            total_pnl += res.pnl
            if res.bust:
                busts += 1
                gross_loss += abs(res.pnl)
            else:
                wins += 1
                gross_profit += res.pnl

        n_eval = len(sample_idx)
        if n_eval == 0:
            return -1e6

        bust_rate = busts / n_eval
        pf = gross_profit / (gross_loss + 1e-10)
        pf = min(pf, 100.0)

        # Composite fitness
        fitness = total_pnl * (1.0 - bust_rate) * min(pf, 10.0) / 10.0
        return fitness

    return fitness_fn


# ── plots ────────────────────────────────────────────────────────────────────

def plot_convergence(history):
    """Plot best fitness per island over generations."""
    fig, ax = plt.subplots(figsize=(10, 6))
    for island_id, gen_fitness in history.items():
        ax.plot(gen_fitness, label=f"Island {island_id}", alpha=0.7)
    ax.set_xlabel('Generation')
    ax.set_ylabel('Best Fitness')
    ax.set_title('GA Convergence — Best Fitness per Island')
    ax.legend(fontsize=7, ncol=2, loc='lower right')
    ax.grid(True, alpha=0.3)
    savefig('41_fitness_convergence')
    log.info("Saved fitness convergence plot")


def plot_diversity(diversity_history):
    """Plot average gene diversity over generations."""
    fig, ax = plt.subplots(figsize=(10, 6))
    gens = sorted(diversity_history.keys())
    # Average diversity across all islands and genes
    avg_div = []
    for g in gens:
        all_stds = []
        for island_stats in diversity_history[g].values():
            all_stds.extend(island_stats.values())
        avg_div.append(np.mean(all_stds) if all_stds else 0.0)

    ax.plot(gens, avg_div, 'b-', linewidth=2)
    ax.set_xlabel('Generation')
    ax.set_ylabel('Mean Gene Std Dev')
    ax.set_title('Population Diversity Over Generations')
    ax.grid(True, alpha=0.3)
    savefig('41_diversity')
    log.info("Saved diversity plot")


def plot_migration(migration_log, n_generations):
    """Plot cumulative migrations over generations."""
    if not migration_log:
        log.info("No migrations to plot")
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    # Count migrations per generation-equivalent (every MIGRATION_EVERY gens)
    migration_counts = {}
    for i, entry in enumerate(migration_log):
        gen_bucket = i // max(1, len(migration_log) // n_generations)
        migration_counts[gen_bucket] = migration_counts.get(gen_bucket, 0) + 1

    gens = sorted(migration_counts.keys())
    counts = [migration_counts[g] for g in gens]
    cumulative = np.cumsum(counts)
    ax.plot(gens, cumulative, 'r-', linewidth=2)
    ax.set_xlabel('Migration Event')
    ax.set_ylabel('Cumulative Migrations')
    ax.set_title('Sibling Migration Over Evolution')
    ax.grid(True, alpha=0.3)
    savefig('41_migration')
    log.info("Saved migration plot")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    log.info("="*60)
    log.info("Script 41 — Island Evolution")
    log.info("="*60)

    # 1. Load regime tree and feature selector from script 40
    tree_path = str(MODELS_DIR / 'regime_tree.pkl')
    log.info(f"Loading regime tree from {tree_path}")
    tree = RegimeTree.load(tree_path)
    log.info(f"Tree: {tree.n_macro} macro, {tree.n_leaves} leaves, "
             f"leaf IDs={tree.leaf_ids}")

    selector_info = load_results('feature_selector', subdir='models')
    selected_indices = selector_info['selected_indices']
    feature_names = selector_info['all_feature_names']
    log.info(f"Loaded feature selector: {len(selected_indices)} features")

    # 2. Load same train candles
    log.info("Loading EUR-USD 5m train candles (2020-2024H1)...")
    warmup, trading = load_candles(
        start_date='2020-01-01', end_date='2024-06-30',
        warmup_candles_num=500,
    )
    candles = concat_candles(warmup, trading)
    log.info(f"Candles shape: {candles.shape}")

    # 3. Compute feature matrix for regime classification
    cache_path = RESULTS_DIR / 'feature_matrix_cache.npz'
    pool = FeaturePool()
    if cache_path.exists():
        log.info("Loading cached feature matrix...")
        cached = np.load(str(cache_path), allow_pickle=True)
        feature_matrix = cached['matrix']
        if feature_matrix.shape[0] != len(candles):
            log.info("Cache shape mismatch, recomputing...")
            feature_matrix, _ = compute_feature_matrix(candles, pool)
    else:
        log.info("Computing feature matrix...")
        feature_matrix, _ = compute_feature_matrix(candles, pool)

    # 4. Generate EMA 8/21 crossover signals
    log.info("Generating EMA 8/21 crossover signals...")
    signals = generate_crossover_signals(candles)
    log.info(f"Total crossover signals: {len(signals)}")

    # 5. Assign signals to leaf islands (vectorized)
    log.info("Assigning signals to regime islands...")
    island_signals = {str(lid): [] for lid in tree.leaf_ids}

    sig_indices = np.array([s['idx'] for s in signals])
    sig_features = feature_matrix[sig_indices]

    # Filter out NaN rows
    valid_sigs = ~np.any(np.isnan(sig_features[:, selected_indices]), axis=1)
    valid_features = sig_features[valid_sigs]

    # Batch classify
    labels, confs = tree.classify_batch(valid_features)

    # Assign back
    valid_idx = 0
    unassigned = 0
    for i, sig in enumerate(signals):
        if not valid_sigs[i]:
            unassigned += 1
            continue
        lid = int(labels[valid_idx])
        sig['regime_id'] = lid
        sig['confidence'] = float(confs[valid_idx])
        island_signals[str(lid)].append(sig)
        valid_idx += 1

    log.info(f"Unassigned (NaN features): {unassigned}")
    for lid in tree.leaf_ids:
        count = len(island_signals[str(lid)])
        log.info(f"  Island {lid}: {count} signals")

    # 6. Build sibling groups from tree._leaf_map
    sibling_groups = {}
    macro_to_leaves = {}
    for lid, (macro_id, sub_id) in tree._leaf_map.items():
        macro_to_leaves.setdefault(macro_id, []).append(str(lid))

    for macro_id, leaves in macro_to_leaves.items():
        if len(leaves) >= 2:
            sibling_groups[f"macro_{macro_id}"] = leaves

    log.info(f"Sibling groups: {sibling_groups}")

    # 7. Filter active islands (>= MIN_SIGNALS_PER_ISLAND signals)
    active_ids = [lid for lid in island_signals
                  if len(island_signals[lid]) >= MIN_SIGNALS_PER_ISLAND]
    log.info(f"Active islands (>={MIN_SIGNALS_PER_ISLAND} signals): "
             f"{len(active_ids)} / {len(island_signals)}")

    if not active_ids:
        log.info("No active islands — aborting evolution")
        save_results({'error': 'no_active_islands'}, '41_island_evolution')
        return

    # Filter sibling groups to only active islands
    active_set = set(active_ids)
    filtered_siblings = {}
    for gname, members in sibling_groups.items():
        active_members = [m for m in members if m in active_set]
        if len(active_members) >= 2:
            filtered_siblings[gname] = active_members

    # 8. Create IslandEvolver
    log.info("Initialising IslandEvolver...")
    evolver = IslandEvolver(
        leaf_ids=active_ids,
        config={
            'pop_size': 30,
            'seed': 42,
            'elitism': 2,
            'crossover_rate': 0.7,
            'mutation_rate': 0.2,
            'mutation_sigma': 0.05,
            'tournament_k': 3,
        },
        sibling_groups=filtered_siblings,
    )

    # 9. Build per-island fitness functions
    fitness_fns = {}
    for lid in active_ids:
        fitness_fns[lid] = make_fitness_fn(candles, island_signals[lid])

    # 10. GA evolution loop
    log.info(f"Starting evolution: {GA_GENERATIONS} generations, "
             f"patience={EARLY_STOP_PATIENCE}")

    convergence_history = {lid: [] for lid in active_ids}
    diversity_history = {}
    best_global_fitness = -np.inf
    patience_counter = 0

    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
    n_workers = min(os.cpu_count() or 4, len(active_ids), 8)
    log.info(f"Using {n_workers} parallel workers for island evaluation")

    evo_cfg = evolver.config

    def _evaluate_and_evolve(lid):
        pop = evolver.populations[lid]
        pop.evaluate(fitness_fns[lid])
        pop.evolve(
            elitism=evo_cfg.get('elitism', 2),
            crossover_rate=evo_cfg.get('crossover_rate', 0.7),
            mutation_rate=evo_cfg.get('mutation_rate', 0.2),
            mutation_sigma=evo_cfg.get('mutation_sigma', 0.05),
            tournament_k=evo_cfg.get('tournament_k', 3),
        )

    for gen in range(GA_GENERATIONS):
        # Evaluate and evolve islands in parallel (threads — shared memory for candles)
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            list(pool.map(_evaluate_and_evolve, active_ids))

        # Migration every N generations
        if (gen + 1) % MIGRATION_EVERY == 0:
            evolver.migrate_siblings()

        # Track convergence
        summary = evolver.get_fitness_summary()
        gen_best = -np.inf
        for lid in active_ids:
            best_f = summary[lid]['best'] if summary[lid]['best'] is not None else -np.inf
            convergence_history[lid].append(best_f)
            gen_best = max(gen_best, best_f)

        # Track diversity
        diversity_history[gen] = evolver.get_diversity_stats()

        # Early stopping
        if gen_best > best_global_fitness:
            best_global_fitness = gen_best
            patience_counter = 0
        else:
            patience_counter += 1

        if (gen + 1) % 10 == 0:
            log.info(f"  Gen {gen+1:3d}: best_fitness={gen_best:.2f}, "
                     f"patience={patience_counter}/{EARLY_STOP_PATIENCE}")

        if patience_counter >= EARLY_STOP_PATIENCE:
            log.info(f"Early stopping at generation {gen+1} "
                     f"(no improvement for {EARLY_STOP_PATIENCE} gens)")
            break

    final_gen = gen + 1
    log.info(f"Evolution complete after {final_gen} generations")

    # 11. Collect best genomes
    best_genomes = {}
    for lid in active_ids:
        best = evolver.get_best_genome(lid)
        best_genomes[lid] = best
        log.info(f"  Island {lid}: fitness={best['fitness']:.2f}, "
                 f"genes={best['genes']}")

    # 12. Save island genomes
    genomes_path = str(MODELS_DIR / 'island_genomes.json')
    with open(genomes_path, 'w') as f:
        json.dump(best_genomes, f, indent=2, default=str)
    log.info(f"Best genomes saved to {genomes_path}")

    # Save full evolver state
    evolver_path = str(MODELS_DIR / 'island_evolver.json')
    evolver.save(evolver_path)
    log.info(f"Full evolver state saved to {evolver_path}")

    # 13. Plots
    log.info("Generating plots...")
    plot_convergence(convergence_history)
    plot_diversity(diversity_history)
    plot_migration(evolver.get_migration_log(), final_gen)

    # 14. Save results summary
    # Run final evaluation for each island's best genome (parallel)
    log.info("Running final evaluation on all signals...")

    def _eval_island(lid):
        best = best_genomes[lid]
        cfg = SimConfig.from_genome(best)
        cycles = []
        for sig in island_signals[lid]:
            res = simulate_cycle(candles, sig['idx'], sig['direction'], cfg)
            res.regime_id = int(lid)
            cycles.append(res)
        return lid, cycle_summary(cycles), cycles

    island_results = {}
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        for lid, stats, _cycles in pool.map(_eval_island, active_ids):
            island_results[lid] = {
                'n_signals': len(island_signals[lid]),
                'best_genome': best_genomes[lid],
                'cycle_stats': stats,
            }

    results = {
        'n_candles': int(candles.shape[0]),
        'total_signals': len(signals),
        'n_active_islands': len(active_ids),
        'active_island_ids': active_ids,
        'generations_run': final_gen,
        'early_stopped': patience_counter >= EARLY_STOP_PATIENCE,
        'best_global_fitness': float(best_global_fitness),
        'sibling_groups': filtered_siblings,
        'n_migrations': len(evolver.get_migration_log()),
        'island_results': island_results,
    }
    save_results(results, '41_island_evolution')
    log.info("Results saved to 41_island_evolution.json")

    # 15. Copy trained models to pipeline's models/ directory for UI use
    pipeline_models = Path(__file__).resolve().parents[2] / 'pipelines' / '_shared' / 'IslandPilot' / 'models'
    pipeline_models.mkdir(parents=True, exist_ok=True)
    import shutil
    src_tree = MODELS_DIR / 'regime_tree.pkl'
    src_genomes = MODELS_DIR / 'island_genomes.json'
    src_evolver = MODELS_DIR / 'island_evolver.json'
    for src in [src_tree, src_genomes, src_evolver]:
        if src.exists():
            shutil.copy2(str(src), str(pipeline_models / src.name))
    log.info(f"Models copied to {pipeline_models} (pipeline ready for UI)")
    log.info("Done.")


if __name__ == '__main__':
    main()
