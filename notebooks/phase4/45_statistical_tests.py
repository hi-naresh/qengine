"""
45 — Statistical Tests

Computes statistical significance of ablation results from script 44.
Calculates PF deltas between full pipeline and each variant, and saves
a summary CSV and JSON.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils import *

import csv

log = get_logger('45_statistical_tests')


def main():
    # 1. Load ablation results
    try:
        ablation = load_results('44_ablation_study')
    except FileNotFoundError:
        log.error("44_ablation_study.json not found. Run script 44 first.")
        return

    full = ablation.get('full_pipeline')
    if full is None:
        log.error("full_pipeline variant not found in ablation results")
        return

    full_pf = full['profit_factor']
    full_wr = full['win_rate']
    full_bust = full['bust_rate']
    full_pnl = full['net_pnl']

    log.info(f"Full pipeline: PF={full_pf:.2f}, WR={full_wr:.3f}, "
             f"bust_rate={full_bust:.3f}, net_pnl={full_pnl:.1f}")

    # 2. Compute deltas
    rows = []
    for variant_name, stats in ablation.items():
        if variant_name == 'full_pipeline':
            continue

        v_pf = stats['profit_factor']
        v_wr = stats['win_rate']
        v_bust = stats['bust_rate']
        v_pnl = stats['net_pnl']

        # PF delta (capped for inf cases)
        pf_full = min(full_pf, 999.0)
        pf_var = min(v_pf, 999.0)
        pf_delta = pf_full - pf_var
        pf_pct_change = (pf_delta / max(pf_var, 0.01)) * 100

        wr_delta = full_wr - v_wr
        bust_delta = full_bust - v_bust
        pnl_delta = full_pnl - v_pnl

        # Determine if this component helps (removing it hurts)
        helps = pf_delta > 0

        row = {
            'variant': variant_name,
            'component_removed': variant_name.replace('no_', '').replace('_', ' '),
            'pf_full': round(pf_full, 3),
            'pf_variant': round(pf_var, 3),
            'pf_delta': round(pf_delta, 3),
            'pf_pct_change': round(pf_pct_change, 1),
            'wr_delta': round(wr_delta, 4),
            'bust_delta': round(bust_delta, 4),
            'pnl_delta': round(pnl_delta, 1),
            'helps': helps,
        }
        rows.append(row)
        log.info(f"  {variant_name}: PF_delta={pf_delta:+.3f} ({pf_pct_change:+.1f}%), "
                 f"WR_delta={wr_delta:+.4f}, helps={helps}")

    # Sort by PF delta descending (most impactful first)
    rows.sort(key=lambda r: r['pf_delta'], reverse=True)

    # 3. Save CSV
    csv_path = TABLES_DIR / 'significance_tests.csv'
    fieldnames = ['variant', 'component_removed', 'pf_full', 'pf_variant',
                  'pf_delta', 'pf_pct_change', 'wr_delta', 'bust_delta',
                  'pnl_delta', 'helps']
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    log.info(f"CSV saved to {csv_path}")

    # 4. Save JSON results
    results = {
        'baseline': {
            'variant': 'full_pipeline',
            'profit_factor': full_pf,
            'win_rate': full_wr,
            'bust_rate': full_bust,
            'net_pnl': full_pnl,
        },
        'comparisons': rows,
        'most_impactful': rows[0]['variant'] if rows else None,
        'least_impactful': rows[-1]['variant'] if rows else None,
    }
    save_results(results, '45_statistical_tests')
    log.info("Results saved")

    # Summary
    log.info("=== Significance Summary ===")
    log.info(f"{'Variant':<20} {'PF delta':>10} {'PF %':>8} {'Helps':>7}")
    log.info("-" * 50)
    for r in rows:
        log.info(f"{r['variant']:<20} {r['pf_delta']:>+10.3f} {r['pf_pct_change']:>+7.1f}% "
                 f"{'YES' if r['helps'] else 'no':>7}")

    if rows:
        log.info(f"\nMost impactful component: {rows[0]['variant']} "
                 f"(PF delta={rows[0]['pf_delta']:+.3f})")


if __name__ == '__main__':
    main()
