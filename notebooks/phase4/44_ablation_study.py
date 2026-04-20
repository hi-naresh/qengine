"""
44 — Ablation Study (Fixed v2)

Matches script 43 exactly for full_pipeline baseline, then removes one
component at a time. Script 43 uses tree.classify_best (no RegimeInferencer),
so the full pipeline here also uses tree.classify_best.

Variants:
- full_pipeline:    matches script 43 (classify_best + evolved genome + gate + adaptive sizer)
- flat_clustering:  macro-level only (no sub-regime distinction)
- single_global:    ignore regime, use single global best genome
- random_configs:   random genomes instead of evolved
- uniform_sizing:   no adaptive sizer (fixed position size)
- no_gate:          no confidence gating (all signals trade)
- no_pipeline:      raw EMA signals, fixed params, no regime awareness
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils import *

import numpy as np
import matplotlib.pyplot as plt

import qengine.indicators as ta
from qengine.framework.components.regime_tree import RegimeTree
from qengine.framework.components.island_evolver import IslandEvolver, Genome
from qengine.framework.components.adaptive_sizer import AdaptiveSizer
from qengine.framework.components.feature_selector import FeaturePool

log = get_logger('44_ablation_study')


# ---------------------------------------------------------------------------
# Shared helpers (identical to script 43)
# ---------------------------------------------------------------------------

def generate_signals(candles: np.ndarray, fast: int = 8, slow: int = 21) -> list:
    ema_fast = ta.ema(candles, period=fast, sequential=True)
    ema_slow = ta.ema(candles, period=slow, sequential=True)
    signals = []
    for i in range(1, len(candles)):
        if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]):
            continue
        if np.isnan(ema_fast[i - 1]) or np.isnan(ema_slow[i - 1]):
            continue
        if ema_fast[i - 1] <= ema_slow[i - 1] and ema_fast[i] > ema_slow[i]:
            signals.append((i, 'long'))
        elif ema_fast[i - 1] >= ema_slow[i - 1] and ema_fast[i] < ema_slow[i]:
            signals.append((i, 'short'))
    return signals


def simulate_cycle(candles: np.ndarray, entry_idx: int, direction: str,
                   cfg: SimConfig) -> CycleResult:
    n = len(candles)
    entry_price = candles[entry_idx, 2]
    pip = 0.0001

    tickets = [(0, direction, entry_price, calc_size(0, cfg))]
    current_level = 0
    current_dir = direction

    if direction == 'long':
        tp_price = entry_price + cfg.tp_pips * pip
        hedge_price = entry_price - cfg.hedge_dist_pips * pip
    else:
        tp_price = entry_price - cfg.tp_pips * pip
        hedge_price = entry_price + cfg.hedge_dist_pips * pip

    for bar in range(entry_idx + 1, min(entry_idx + cfg.max_bars, n)):
        price = candles[bar, 2]
        high = candles[bar, 3]
        low = candles[bar, 4]

        tp_hit = (current_dir == 'long' and high >= tp_price) or \
                 (current_dir == 'short' and low <= tp_price)

        if tp_hit:
            total_pnl = sum(
                (tp_price - ep) * sz / pip if d == 'long' else (ep - tp_price) * sz / pip
                for _, d, ep, sz in tickets
            )
            return CycleResult(bust=False, level_reached=current_level,
                               pnl=total_pnl, bars_held=bar - entry_idx,
                               entry_idx=entry_idx, direction=direction)

        hedge_hit = (current_dir == 'long' and low <= hedge_price) or \
                    (current_dir == 'short' and high >= hedge_price)

        if hedge_hit:
            current_level += 1
            if current_level >= cfg.max_levels:
                total_pnl = sum(
                    (price - ep) * sz / pip if d == 'long' else (ep - price) * sz / pip
                    for _, d, ep, sz in tickets
                )
                return CycleResult(bust=True, level_reached=current_level,
                                   pnl=total_pnl, bars_held=bar - entry_idx,
                                   entry_idx=entry_idx, direction=direction)

            new_dir = 'short' if current_dir == 'long' else 'long'
            tickets.append((current_level, new_dir, hedge_price, calc_size(current_level, cfg)))
            current_dir = new_dir
            if new_dir == 'long':
                tp_price = hedge_price + cfg.tp_pips * pip
                hedge_price = hedge_price - cfg.hedge_dist_pips * pip
            else:
                tp_price = hedge_price - cfg.tp_pips * pip
                hedge_price = hedge_price + cfg.hedge_dist_pips * pip

    last_price = candles[min(entry_idx + cfg.max_bars - 1, n - 1), 2]
    total_pnl = sum(
        (last_price - ep) * sz / pip if d == 'long' else (ep - last_price) * sz / pip
        for _, d, ep, sz in tickets
    )
    return CycleResult(bust=True, level_reached=current_level,
                       pnl=total_pnl, bars_held=cfg.max_bars,
                       entry_idx=entry_idx, direction=direction)


# ---------------------------------------------------------------------------
# Core pipeline run — parameterized for ablation
# ---------------------------------------------------------------------------

def run_pipeline(candles, features, signals, tree, evolver,
                 use_regime=True,
                 use_evolved=True,
                 use_gate=True,
                 use_adaptive_size=True,
                 use_sub_regimes=True,
                 single_global_genome=None,
                 random_seed=None):
    """
    Parameterized pipeline runner. Matches script 43 when all flags are True.

    Args:
        use_regime: classify regime and pick per-regime genome
        use_evolved: use evolved genomes (False = default SimConfig)
        use_gate: apply confidence gating
        use_adaptive_size: apply adaptive position sizing
        use_sub_regimes: True = per-leaf genome, False = best genome from macro cluster
        single_global_genome: if set, use this genome for all signals
        random_seed: if set, use random genomes
    """
    sizer = AdaptiveSizer() if use_adaptive_size else None
    cycles = []
    equity = 10000.0

    # Build macro -> leaves mapping for flat_clustering
    macro_to_leaves = {}
    if tree is not None:
        for leaf_id, (macro_id, _sub_id) in tree._leaf_map.items():
            macro_to_leaves.setdefault(macro_id, []).append(str(leaf_id))

    for bar_idx, direction in signals:
        if bar_idx + 50 > len(candles):
            continue

        genes = None
        confidence = 0.5  # default for non-regime variants

        if random_seed is not None:
            # Random genome
            genes = Genome.random(seed=random_seed + bar_idx).to_dict().get('genes', {})
        elif single_global_genome is not None:
            # Single global
            genes = single_global_genome
        elif use_regime and tree is not None and evolver is not None:
            # Regime-aware
            fv = features[bar_idx]
            if np.any(np.isnan(fv)):
                continue

            regime_id, confidence = tree.classify_best(fv)
            regime_key = str(regime_id)

            if use_sub_regimes:
                # Per-leaf genome (full pipeline)
                if regime_key not in evolver.populations:
                    continue
                gd = evolver.get_best_genome(regime_key)
                genes = gd.get('genes', gd)
            else:
                # Flat clustering: best genome from macro cluster
                macro_id = None
                for lid, (mid, _sid) in tree._leaf_map.items():
                    if lid == regime_id:
                        macro_id = mid
                        break
                if macro_id is None:
                    continue
                best_fitness = -np.inf
                for leaf_key in macro_to_leaves.get(macro_id, []):
                    if leaf_key in evolver.populations:
                        gd = evolver.get_best_genome(leaf_key)
                        f = gd.get('fitness', -np.inf)
                        if f is not None and f > best_fitness:
                            best_fitness = f
                            genes = gd.get('genes', gd)

            if genes is None:
                continue

            # Confidence gate
            if use_gate:
                gate_conf = genes.get('gate_confidence_min', 0.3)
                if confidence < gate_conf:
                    continue

        if genes is None and not use_evolved:
            # No pipeline / no genome
            cfg = SimConfig()
        elif genes is None:
            continue
        else:
            cfg = SimConfig.from_genome(genes, equity=equity)

        # Adaptive sizing
        if sizer is not None and genes is not None:
            base_qty = calc_size(0, cfg)
            adjusted = sizer.compute(
                base_pct=genes.get('base_size_pct', 1.0),
                confidence=confidence,  # ACTUAL confidence from GMM
                sensitivity=genes.get('confidence_sensitivity', 1.0),
                drawdown_pct=max_drawdown_pct([c.pnl for c in cycles[-50:]]) if cycles else 0.0,
                recovery_aggression=genes.get('recovery_aggression', 0.5),
                balance=equity,
                qty=base_qty,
            )
            if base_qty > 0:
                cfg.base_size = adjusted

        result = simulate_cycle(candles, bar_idx, direction, cfg)
        cycles.append(result)
        equity += result.pnl

    return cycles


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Load models
    tree_path = MODELS_DIR / 'regime_tree.pkl'
    tree = RegimeTree.load(str(tree_path)) if tree_path.exists() else None

    evolver_path = MODELS_DIR / 'island_evolver.json'
    if not evolver_path.exists():
        evolver_path = MODELS_DIR / 'island_genomes.json'

    evolver = None
    if evolver_path.exists():
        try:
            evolver = IslandEvolver.load(str(evolver_path))
        except (KeyError, Exception):
            import json as _json
            with open(str(evolver_path)) as f:
                genomes_data = _json.load(f)
            leaf_ids = list(genomes_data.keys())
            evolver = IslandEvolver(leaf_ids=leaf_ids, config={})
            for lid, gdata in genomes_data.items():
                genome = Genome.from_dict(gdata if 'genes' not in gdata else gdata['genes'])
                genome.fitness = gdata.get('fitness', 0.0)
                if lid in evolver.populations:
                    evolver.populations[lid].individuals[0] = genome

    if tree is None or evolver is None:
        log.error("Models not found. Run scripts 40-41 first.")
        return

    log.info(f"Loaded tree ({tree.n_leaves} leaves) and evolver ({len(evolver.populations)} islands)")

    # Find global best genome for single_global variant
    best_fitness = -np.inf
    global_genes = None
    for lid in evolver.leaf_ids:
        gd = evolver.get_best_genome(lid)
        f = gd.get('fitness', -np.inf)
        if f is not None and f > best_fitness:
            best_fitness = f
            global_genes = gd.get('genes', gd)

    # Load test candles
    log.info("Loading test candles 2025-07-01 to 2025-12-30 ...")
    warmup, trading = load_candles(start_date='2025-07-01', end_date='2025-12-30')
    candles = concat_candles(warmup, trading)
    log.info(f"Candles: {len(candles)} bars")

    pool = FeaturePool()
    features = pool.compute(candles)
    signals = generate_signals(candles)
    log.info(f"Generated {len(signals)} signals")

    # Define variants — each removes exactly one component from full_pipeline
    variants = {
        'full_pipeline': dict(
            use_regime=True, use_evolved=True, use_gate=True,
            use_adaptive_size=True, use_sub_regimes=True,
        ),
        'flat_clustering': dict(
            use_regime=True, use_evolved=True, use_gate=True,
            use_adaptive_size=True, use_sub_regimes=False,  # macro-level only
        ),
        'no_gate': dict(
            use_regime=True, use_evolved=True, use_gate=False,  # no confidence gating
            use_adaptive_size=True, use_sub_regimes=True,
        ),
        'uniform_sizing': dict(
            use_regime=True, use_evolved=True, use_gate=True,
            use_adaptive_size=False, use_sub_regimes=True,  # no adaptive sizer
        ),
        'single_global': dict(
            use_regime=False, use_evolved=True, use_gate=False,
            use_adaptive_size=True, use_sub_regimes=True,
            single_global_genome=global_genes,
        ),
        'random_configs': dict(
            use_regime=True, use_evolved=False, use_gate=False,
            use_adaptive_size=True, use_sub_regimes=True,
            random_seed=42,
        ),
        'no_pipeline': dict(
            use_regime=False, use_evolved=False, use_gate=False,
            use_adaptive_size=False, use_sub_regimes=True,
        ),
    }

    results = {}
    for name, kwargs in variants.items():
        log.info(f"Running variant: {name} ...")
        cycles = run_pipeline(candles, features, signals, tree, evolver, **kwargs)
        stats = cycle_summary(cycles)
        results[name] = stats
        pf_str = f"{stats['profit_factor']:.4f}" if stats['profit_factor'] < 100 else "inf"
        log.info(f"  {name}: n={stats['n_cycles']}, PF={pf_str}, "
                 f"WR={stats['win_rate']:.3f}, busts={stats['n_busts']}, "
                 f"net_pnl={stats['net_pnl']:.1f}, maxDD={stats['max_drawdown_pct']:.1f}%")

    # Verify full_pipeline matches script 43
    fp = results['full_pipeline']
    log.info(f"\n=== VERIFICATION vs Script 43 ===")
    log.info(f"This script:  PF={fp['profit_factor']:.4f}, cycles={fp['n_cycles']}, net_pnl={fp['net_pnl']:.0f}")
    log.info(f"Script 43:    PF=1.3409, cycles=1225, net_pnl=7829")
    pf_diff = abs(fp['profit_factor'] - 1.3409)
    if pf_diff < 0.01:
        log.info(f"MATCH (PF diff = {pf_diff:.4f})")
    else:
        log.warning(f"MISMATCH (PF diff = {pf_diff:.4f})")

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    names = list(results.keys())
    pfs = [min(results[n]['profit_factor'], 50) for n in names]

    colors = ['steelblue' if n == 'full_pipeline' else 'lightcoral' if n == 'no_pipeline'
              else 'lightgray' for n in names]
    y_pos = np.arange(len(names))
    ax.barh(y_pos, pfs, color=colors, edgecolor='gray', alpha=0.8)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names)
    ax.set_xlabel('Profit Factor')
    ax.set_title('Ablation Study: Component Contribution')
    ax.axvline(1.0, color='red', linestyle='--', alpha=0.5, label='Break-even')
    ax.legend()
    ax.grid(axis='x', alpha=0.3)

    savefig('44_ablation_study')
    log.info("Plot saved")

    save_results(results, '44_ablation_study')
    log.info("Results saved")

    # Summary table
    log.info("\n=== Ablation Summary ===")
    log.info(f"{'Variant':<20} {'Cycles':>7} {'PF':>8} {'WR':>8} {'Busts':>7} {'Net PnL':>10} {'MaxDD%':>8}")
    log.info("-" * 75)
    for name in names:
        s = results[name]
        pf_str = f"{s['profit_factor']:.4f}" if s['profit_factor'] < 100 else "inf"
        log.info(f"{name:<20} {s['n_cycles']:>7} {pf_str:>8} "
                 f"{s['win_rate']:.3f}{'':<1} {s['n_busts']:>7} {s['net_pnl']:>10.1f} {s['max_drawdown_pct']:>7.1f}%")

    # Component contribution (delta from full)
    fp_pf = fp['profit_factor']
    log.info(f"\n=== Component Contribution (delta from full_pipeline PF={fp_pf:.4f}) ===")
    for name in names:
        if name == 'full_pipeline':
            continue
        s = results[name]
        delta = fp_pf - s['profit_factor']
        if fp_pf > 0 and fp_pf < float('inf'):
            pct = delta / fp_pf * 100
            log.info(f"  {name}: PF={s['profit_factor']:.4f}  delta={delta:+.4f} ({pct:+.1f}%)")
        else:
            log.info(f"  {name}: PF={s['profit_factor']:.4f}  delta={delta:+.4f}")


if __name__ == '__main__':
    main()
