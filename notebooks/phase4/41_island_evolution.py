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
    get_logger, MODELS_DIR, CycleResult, SimConfig, calc_size,
    cycle_summary,
)

import json
import numpy as np
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


# ── cycle simulator ──────────────────────────────────────────────────────────

def simulate_cycle(
    candles: np.ndarray,
    entry_idx: int,
    direction: str,
    cfg: SimConfig,
) -> CycleResult:
    """Simulate a single surefire hedging cycle from entry_idx.

    Tracks positions at each level.  TP = all positions net positive.
    Hedge trigger = price moves against current direction by hedge_dist.
    Bust = max_levels exceeded or max_bars elapsed.
    """
    n = len(candles)
    pip = 0.0001  # EUR-USD pip size

    entry_price = float(candles[entry_idx, 2])  # close
    positions = []  # list of (direction, price, size)
    size0 = cfg.base_size
    positions.append((direction, entry_price, size0))

    current_level = 0
    current_dir = direction
    last_entry_price = entry_price

    for bar in range(1, cfg.max_bars + 1):
        ci = entry_idx + bar
        if ci >= n:
            # Ran out of candles — treat as bust
            pnl = _calc_net_pnl(positions, candles[min(ci, n-1), 2], pip)
            return CycleResult(
                bust=True, level_reached=current_level,
                pnl=pnl, bars_held=bar,
                entry_idx=entry_idx, direction=direction,
            )

        high = float(candles[ci, 3])
        low = float(candles[ci, 4])
        close = float(candles[ci, 2])

        # Check TP: can we close all positions at net profit?
        tp_price = _calc_tp_price(positions, cfg.tp_pips, pip)
        if tp_price is not None:
            if current_dir == 'long' and high >= tp_price:
                pnl = _calc_net_pnl(positions, tp_price, pip)
                return CycleResult(
                    bust=False, level_reached=current_level,
                    pnl=pnl, bars_held=bar,
                    entry_idx=entry_idx, direction=direction,
                )
            elif current_dir == 'short' and low <= tp_price:
                pnl = _calc_net_pnl(positions, tp_price, pip)
                return CycleResult(
                    bust=False, level_reached=current_level,
                    pnl=pnl, bars_held=bar,
                    entry_idx=entry_idx, direction=direction,
                )

        # Check hedge trigger
        hedge_price = _calc_hedge_price(last_entry_price, current_dir,
                                         cfg.hedge_dist_pips, pip)
        triggered = False
        if current_dir == 'long' and low <= hedge_price:
            triggered = True
        elif current_dir == 'short' and high >= hedge_price:
            triggered = True

        if triggered:
            current_level += 1
            if current_level > cfg.max_levels:
                # Bust — exceeded max levels
                pnl = _calc_net_pnl(positions, close, pip)
                return CycleResult(
                    bust=True, level_reached=current_level - 1,
                    pnl=pnl, bars_held=bar,
                    entry_idx=entry_idx, direction=direction,
                )
            # Flip direction and add hedge position
            current_dir = 'short' if current_dir == 'long' else 'long'
            new_size = calc_size(current_level, cfg)
            positions.append((current_dir, hedge_price, new_size))
            last_entry_price = hedge_price

    # Max bars elapsed — bust
    final_price = float(candles[min(entry_idx + cfg.max_bars, n-1), 2])
    pnl = _calc_net_pnl(positions, final_price, pip)
    return CycleResult(
        bust=True, level_reached=current_level,
        pnl=pnl, bars_held=cfg.max_bars,
        entry_idx=entry_idx, direction=direction,
    )


def _calc_net_pnl(positions, exit_price, pip):
    """Compute total P&L of all open positions at exit_price."""
    total = 0.0
    for d, entry, size in positions:
        if d == 'long':
            total += (exit_price - entry) / pip * size
        else:
            total += (entry - exit_price) / pip * size
    return total


def _calc_tp_price(positions, tp_pips, pip):
    """Compute TP price: price at which net P&L = tp_pips * base_size.

    For the latest direction, TP is tp_pips beyond the last entry.
    Returns None if no positions.
    """
    if not positions:
        return None
    last_dir, last_entry, _ = positions[-1]
    if last_dir == 'long':
        return last_entry + tp_pips * pip
    else:
        return last_entry - tp_pips * pip


def _calc_hedge_price(entry_price, direction, hedge_pips, pip):
    """Compute hedge trigger price."""
    if direction == 'long':
        return entry_price - hedge_pips * pip
    else:
        return entry_price + hedge_pips * pip


# ── fitness function factory ─────────────────────────────────────────────────

def make_fitness_fn(candles, signals_for_island):
    """Create a fitness function that evaluates a genome on island signals."""

    def fitness_fn(genes: dict) -> float:
        cfg = SimConfig.from_genome({'genes': genes})
        results = []
        for sig in signals_for_island:
            res = simulate_cycle(candles, sig['idx'], sig['direction'], cfg)
            results.append(res)

        if not results:
            return -1e6

        stats = cycle_summary(results)
        # Fitness = net P&L adjusted for bust rate penalty
        # Reward high win rate and PF, penalise busts heavily
        net_pnl = stats['net_pnl']
        bust_rate = stats['bust_rate']
        pf = stats['profit_factor'] if stats['profit_factor'] != float('inf') else 100.0
        pf = min(pf, 100.0)

        # Composite fitness
        fitness = net_pnl * (1.0 - bust_rate) * min(pf, 10.0) / 10.0
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
    log.info("Loading EUR-USD 5m train candles (2006-2018)...")
    warmup, trading = load_candles(
        start_date='2006-01-02', end_date='2018-12-31',
        warmup_candles_num=500,
    )
    candles = concat_candles(warmup, trading)
    log.info(f"Candles shape: {candles.shape}")

    # 3. Compute feature matrix for regime classification
    log.info("Computing feature matrix...")
    pool = FeaturePool()
    feature_matrix, _ = compute_feature_matrix(candles, pool)

    # 4. Generate EMA 8/21 crossover signals
    log.info("Generating EMA 8/21 crossover signals...")
    signals = generate_crossover_signals(candles)
    log.info(f"Total crossover signals: {len(signals)}")

    # 5. Assign signals to leaf islands
    log.info("Assigning signals to regime islands...")
    island_signals = {str(lid): [] for lid in tree.leaf_ids}
    unassigned = 0

    for sig in signals:
        fv = feature_matrix[sig['idx']]
        if np.any(np.isnan(fv[selected_indices])):
            unassigned += 1
            continue
        lid, conf = tree.classify_best(fv)
        sig['regime_id'] = lid
        sig['confidence'] = conf
        island_signals[str(lid)].append(sig)

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

    for gen in range(GA_GENERATIONS):
        # Evaluate and evolve each island with its own fitness function
        for lid in active_ids:
            pop = evolver.populations[lid]
            pop.evaluate(fitness_fns[lid])
            pop.evolve(
                elitism=evolver.config.get('elitism', 2),
                crossover_rate=evolver.config.get('crossover_rate', 0.7),
                mutation_rate=evolver.config.get('mutation_rate', 0.2),
                mutation_sigma=evolver.config.get('mutation_sigma', 0.05),
                tournament_k=evolver.config.get('tournament_k', 3),
            )

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
    # Run final evaluation for each island's best genome
    island_results = {}
    for lid in active_ids:
        best = best_genomes[lid]
        cfg = SimConfig.from_genome(best)
        cycles = []
        for sig in island_signals[lid]:
            res = simulate_cycle(candles, sig['idx'], sig['direction'], cfg)
            res.regime_id = int(lid)
            cycles.append(res)
        stats = cycle_summary(cycles)
        island_results[lid] = {
            'n_signals': len(island_signals[lid]),
            'best_genome': best,
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
