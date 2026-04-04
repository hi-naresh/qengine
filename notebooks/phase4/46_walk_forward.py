"""
46 — Walk-Forward Validation

3-window walk-forward test of the full IslandPilot pipeline.
Each window: train fresh regime tree + evolve genomes (abbreviated 20 gen),
then test on unseen data. Aggregates mean +/- std across windows.

Window 1: Train 2019-2022, Val 2022-2023, Test 2023-2024
Window 2: Train 2020-2023, Val 2023-2024, Test 2024-2025
Window 3: Train 2021-2024, Val 2024-H1 2025, Test H2 2025
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils import *

import numpy as np
import matplotlib.pyplot as plt

import qengine.indicators as ta
from qengine.framework.components.regime_tree import RegimeTree
from qengine.framework.components.island_evolver import IslandEvolver
from qengine.framework.components.feature_selector import FeaturePool, select_features
from qengine.framework.components.adaptive_sizer import AdaptiveSizer

log = get_logger('46_walk_forward')


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def generate_signals(candles, fast=8, slow=21):
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


def simulate_cycle(candles, entry_idx, direction, cfg):
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
                for _, d, ep, sz in tickets)
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
                    for _, d, ep, sz in tickets)
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
        for _, d, ep, sz in tickets)
    return CycleResult(bust=True, level_reached=current_level,
                       pnl=total_pnl, bars_held=cfg.max_bars,
                       entry_idx=entry_idx, direction=direction)


def run_pipeline_on_data(candles, features, signals, tree, evolver):
    """Run full pipeline and return cycles list."""
    sizer = AdaptiveSizer()
    cycles = []
    equity = 10000.0

    for bar_idx, direction in signals:
        if bar_idx + 50 > len(candles):
            continue
        fv = features[bar_idx]
        if np.any(np.isnan(fv)):
            continue

        regime_id, confidence = tree.classify_best(fv)
        regime_key = str(regime_id)
        if regime_key not in evolver.populations:
            continue

        gd = evolver.get_best_genome(regime_key)
        genes = gd.get('genes', gd)

        gate_conf = genes.get('gate_confidence_min', 0.3)
        if confidence < gate_conf:
            continue

        cfg = SimConfig.from_genome(genes)
        base_qty = calc_size(0, cfg)
        adjusted = sizer.compute(
            base_pct=genes.get('base_size_pct', 1.0),
            confidence=confidence,
            sensitivity=genes.get('confidence_sensitivity', 1.0),
            drawdown_pct=max_drawdown_pct([c.pnl for c in cycles[-50:]]) if cycles else 0.0,
            recovery_aggression=genes.get('recovery_aggression', 0.5),
            balance=equity, qty=base_qty,
        )
        if base_qty > 0:
            cfg.base_size = adjusted

        result = simulate_cycle(candles, bar_idx, direction, cfg)
        cycles.append(result)
        equity += result.pnl

    return cycles


# ---------------------------------------------------------------------------
# Train a fresh tree + evolve
# ---------------------------------------------------------------------------

def train_pipeline(train_candles, pool, n_generations=20):
    """Train regime tree and evolve genomes on training data."""
    log.info("  Computing training features ...")
    train_features = pool.compute(train_candles)

    # Clean NaN rows
    valid = ~np.any(np.isnan(train_features), axis=1)
    X_clean = train_features[valid]
    log.info(f"  Clean features: {X_clean.shape[0]} rows")

    if X_clean.shape[0] < 500:
        log.info("  Too few clean rows, using defaults")
        return None, None

    # Select macro and sub features
    n_feat = X_clean.shape[1]
    # Simple split: first half macro, second half sub
    macro_feats = list(range(min(n_feat // 2, 10)))
    sub_feats = list(range(n_feat // 2, min(n_feat, n_feat // 2 + 10)))

    # Fit tree
    log.info("  Fitting regime tree ...")
    tree = RegimeTree(min_leaf_samples=100, max_macro=6, max_sub=4)
    tree.fit(X_clean, macro_features=macro_feats, sub_features=sub_feats)
    log.info(f"  Tree: {tree.n_leaves} leaves, {tree.n_macro} macro")

    # Evolve genomes
    leaf_ids = [str(lid) for lid in tree.leaf_ids]
    evolver = IslandEvolver(leaf_ids, config={'pop_size': 15, 'seed': 42})

    # Generate training signals and cycles for fitness evaluation
    train_signals = generate_signals(train_candles)
    log.info(f"  Training signals: {len(train_signals)}")

    # Build per-regime signal sets
    regime_signals = {lid: [] for lid in leaf_ids}
    for bar_idx, direction in train_signals:
        if bar_idx >= len(train_features):
            continue
        fv = train_features[bar_idx]
        if np.any(np.isnan(fv)):
            continue
        rid, _ = tree.classify_best(fv)
        rkey = str(rid)
        if rkey in regime_signals:
            regime_signals[rkey].append((bar_idx, direction))

    def _fitness_fn(genes):
        cfg = SimConfig.from_genome(genes)
        # Evaluate on a random subset of training signals
        all_pnls = []
        busts = 0
        for bar_idx, direction in train_signals[:200]:  # cap for speed
            if bar_idx + 50 > len(train_candles):
                continue
            result = simulate_cycle(train_candles, bar_idx, direction, cfg)
            all_pnls.append(result.pnl)
            if result.bust:
                busts += 1
        if not all_pnls:
            return -1.0
        gross_p = sum(p for p in all_pnls if p > 0)
        gross_l = abs(sum(p for p in all_pnls if p < 0))
        pf = gross_p / max(gross_l, 1.0)
        bust_rate = busts / len(all_pnls)
        return pf * (1 - bust_rate)

    for gen in range(n_generations):
        evolver.evolve_all(_fitness_fn, generation=gen)
        if gen % 5 == 0 and gen > 0:
            evolver.migrate_siblings()

    log.info(f"  Evolution done ({n_generations} generations)")
    return tree, evolver


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

WINDOWS = [
    {
        'name': 'W1',
        'train': ('2019-01-01', '2022-12-31'),
        'val':   ('2022-01-01', '2023-12-31'),
        'test':  ('2023-01-01', '2024-12-31'),
    },
    {
        'name': 'W2',
        'train': ('2020-01-01', '2023-12-31'),
        'val':   ('2023-01-01', '2024-12-31'),
        'test':  ('2024-01-01', '2025-06-30'),
    },
    {
        'name': 'W3',
        'train': ('2021-01-01', '2024-12-31'),
        'val':   ('2024-01-01', '2025-06-30'),
        'test':  ('2025-07-01', '2025-12-30'),
    },
]


def main():
    pool = FeaturePool()
    window_results = []

    for window in WINDOWS:
        name = window['name']
        log.info(f"\n{'='*60}")
        log.info(f"Walk-forward window: {name}")
        log.info(f"  Train: {window['train'][0]} to {window['train'][1]}")
        log.info(f"  Test:  {window['test'][0]} to {window['test'][1]}")

        # Load training data
        log.info("  Loading training candles ...")
        w_train, t_train = load_candles(
            start_date=window['train'][0], end_date=window['train'][1])
        train_candles = concat_candles(w_train, t_train)
        log.info(f"  Train candles: {len(train_candles)}")

        # Train pipeline
        tree, evolver = train_pipeline(train_candles, pool, n_generations=20)
        if tree is None:
            log.info(f"  Skipping {name}: training failed")
            window_results.append({
                'window': name, 'train_range': window['train'],
                'test_range': window['test'],
                'n_cycles': 0, 'profit_factor': 0, 'win_rate': 0, 'bust_rate': 1,
            })
            continue

        # Load test data
        log.info("  Loading test candles ...")
        w_test, t_test = load_candles(
            start_date=window['test'][0], end_date=window['test'][1])
        test_candles = concat_candles(w_test, t_test)
        log.info(f"  Test candles: {len(test_candles)}")

        # Compute features and signals on test data
        test_features = pool.compute(test_candles)
        test_signals = generate_signals(test_candles)
        log.info(f"  Test signals: {len(test_signals)}")

        # Run pipeline on test data
        cycles = run_pipeline_on_data(test_candles, test_features, test_signals, tree, evolver)
        stats = cycle_summary(cycles)

        result = {
            'window': name,
            'train_range': window['train'],
            'test_range': window['test'],
            'n_cycles': stats['n_cycles'],
            'profit_factor': stats['profit_factor'],
            'win_rate': stats['win_rate'],
            'bust_rate': stats['bust_rate'],
            'net_pnl': stats['net_pnl'],
            'max_drawdown_pct': stats['max_drawdown_pct'],
            'avg_level': stats['avg_level'],
        }
        window_results.append(result)
        log.info(f"  {name} result: PF={stats['profit_factor']:.2f}, "
                 f"WR={stats['win_rate']:.3f}, busts={stats['n_busts']}")

    # Aggregate
    pfs = [r['profit_factor'] for r in window_results if r['n_cycles'] > 0]
    wrs = [r['win_rate'] for r in window_results if r['n_cycles'] > 0]
    brs = [r['bust_rate'] for r in window_results if r['n_cycles'] > 0]

    agg = {
        'pf_mean': float(np.mean(pfs)) if pfs else 0,
        'pf_std': float(np.std(pfs)) if pfs else 0,
        'wr_mean': float(np.mean(wrs)) if wrs else 0,
        'wr_std': float(np.std(wrs)) if wrs else 0,
        'bust_mean': float(np.mean(brs)) if brs else 0,
        'bust_std': float(np.std(brs)) if brs else 0,
    }
    log.info(f"\nAggregate: PF={agg['pf_mean']:.2f}+/-{agg['pf_std']:.2f}, "
             f"WR={agg['wr_mean']:.3f}+/-{agg['wr_std']:.3f}, "
             f"Bust={agg['bust_mean']:.3f}+/-{agg['bust_std']:.3f}")

    # Plot: grouped bars for PF, WR, Bust Rate
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    window_names = [r['window'] for r in window_results]

    metrics = [
        ('Profit Factor', [r['profit_factor'] for r in window_results], agg['pf_mean'], agg['pf_std']),
        ('Win Rate', [r['win_rate'] for r in window_results], agg['wr_mean'], agg['wr_std']),
        ('Bust Rate', [r['bust_rate'] for r in window_results], agg['bust_mean'], agg['bust_std']),
    ]

    for ax, (title, vals, mean, std) in zip(axes, metrics):
        x = np.arange(len(window_names))
        bars = ax.bar(x, vals, color='steelblue', alpha=0.8, edgecolor='gray')
        ax.axhline(mean, color='red', linestyle='--', alpha=0.6, label=f'mean={mean:.2f}')
        ax.fill_between([-0.5, len(window_names) - 0.5], mean - std, mean + std,
                        color='red', alpha=0.1)
        ax.set_xticks(x)
        ax.set_xticklabels(window_names)
        ax.set_title(title)
        ax.legend(fontsize=8)
        ax.grid(axis='y', alpha=0.3)

    savefig('46_walk_forward')
    log.info("Plot saved")

    results = {
        'windows': window_results,
        'aggregate': agg,
    }
    save_results(results, '46_walk_forward')
    log.info("Results saved")


if __name__ == '__main__':
    main()
