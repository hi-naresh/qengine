"""
47 — Comparison Baselines

Loads results from scripts 43 (full pipeline) and 44 (ablation),
creates a comparison table and grouped bar chart of IslandPilot
vs No Pipeline vs ablation variants.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils import *

import numpy as np
import matplotlib.pyplot as plt

log = get_logger('47_comparison_baselines')


def main():
    # 1. Load results
    try:
        pipeline_results = load_results('43_full_pipeline_backtest')
    except FileNotFoundError:
        log.error("43_full_pipeline_backtest.json not found. Run script 43 first.")
        return

    try:
        ablation_results = load_results('44_ablation_study')
    except FileNotFoundError:
        log.error("44_ablation_study.json not found. Run script 44 first.")
        return

    # 2. Build comparison table
    # Use pipeline overall stats and ablation variants
    pipeline_overall = pipeline_results.get('overall', {})

    # Gather all variants
    variants = {}

    # Full pipeline from script 43 (authoritative)
    variants['IslandPilot (full)'] = {
        'profit_factor': pipeline_overall.get('profit_factor', 0),
        'win_rate': pipeline_overall.get('win_rate', 0),
        'bust_rate': pipeline_overall.get('bust_rate', 0),
        'net_pnl': pipeline_overall.get('net_pnl', 0),
        'n_cycles': pipeline_overall.get('n_cycles', 0),
        'max_drawdown_pct': pipeline_overall.get('max_drawdown_pct', 0),
    }

    # Ablation variants
    for name, stats in ablation_results.items():
        if name == 'full_pipeline':
            continue  # already have authoritative from script 43
        label = name.replace('_', ' ').title()
        variants[label] = {
            'profit_factor': stats.get('profit_factor', 0),
            'win_rate': stats.get('win_rate', 0),
            'bust_rate': stats.get('bust_rate', 0),
            'net_pnl': stats.get('net_pnl', 0),
            'n_cycles': stats.get('n_cycles', 0),
            'max_drawdown_pct': stats.get('max_drawdown_pct', 0),
        }

    # 3. Print comparison table
    log.info("=== Comparison Table ===")
    log.info(f"{'Variant':<25} {'PF':>8} {'WR':>8} {'Bust%':>8} {'NetPnL':>10} {'Cycles':>7} {'MaxDD%':>8}")
    log.info("-" * 80)
    for name, v in variants.items():
        pf = v['profit_factor']
        pf_str = f"{pf:.2f}" if pf < 100 else "inf"
        log.info(f"{name:<25} {pf_str:>8} {v['win_rate']:.3f}{'':<1} "
                 f"{v['bust_rate']:.3f}{'':<1} {v['net_pnl']:>10.1f} "
                 f"{v['n_cycles']:>7} {v['max_drawdown_pct']:>7.1f}%")

    # 4. Grouped bar chart
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    names = list(variants.keys())
    x = np.arange(len(names))

    # Color scheme: full = blue, no_pipeline = red, others = gray
    colors = []
    for n in names:
        if 'full' in n.lower() or 'islandpilot' in n.lower():
            colors.append('steelblue')
        elif 'no pipeline' in n.lower():
            colors.append('lightcoral')
        else:
            colors.append('lightgray')

    # Profit Factor
    ax = axes[0]
    pfs = [min(variants[n]['profit_factor'], 50) for n in names]  # cap for display
    ax.bar(x, pfs, color=colors, edgecolor='gray', alpha=0.8)
    ax.axhline(1.0, color='red', linestyle='--', alpha=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha='right', fontsize=7)
    ax.set_ylabel('Profit Factor')
    ax.set_title('Profit Factor Comparison')
    ax.grid(axis='y', alpha=0.3)

    # Win Rate
    ax = axes[1]
    wrs = [variants[n]['win_rate'] for n in names]
    ax.bar(x, wrs, color=colors, edgecolor='gray', alpha=0.8)
    ax.axhline(0.5, color='red', linestyle='--', alpha=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha='right', fontsize=7)
    ax.set_ylabel('Win Rate')
    ax.set_title('Win Rate Comparison')
    ax.grid(axis='y', alpha=0.3)

    # Bust Rate
    ax = axes[2]
    brs = [variants[n]['bust_rate'] for n in names]
    ax.bar(x, brs, color=colors, edgecolor='gray', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha='right', fontsize=7)
    ax.set_ylabel('Bust Rate')
    ax.set_title('Bust Rate Comparison')
    ax.grid(axis='y', alpha=0.3)

    savefig('47_comparison_baselines')
    log.info("Plot saved")

    # 5. Save results
    results = {
        'variants': variants,
        'pipeline_n_signals': pipeline_results.get('n_signals', 0),
        'pipeline_n_gated': pipeline_results.get('n_gated', 0),
        'sizer_stats': pipeline_results.get('sizer_stats', {}),
    }
    save_results(results, '47_comparison_baselines')
    log.info("Results saved")


if __name__ == '__main__':
    main()
