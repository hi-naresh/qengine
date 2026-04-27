"""Block-bootstrap significance test for the §6.1 Baseline-vs-IslandPilot result.

Reads per-session P&L CSVs produced by 04_bootstrap_dump_sessions.py and computes
95% confidence intervals on:
  - Net profit difference (% of starting balance):  IslandPilot - Baseline
  - Profit factor difference:                       IslandPilot - Baseline

We use the **moving block bootstrap** (Künsch 1989) on the time-ordered session
P&L sequence to preserve any short-range serial dependence in the per-session
outcome (Martingale sessions can correlate when adjacent sessions span the same
directional run). Block length is set to roughly the square-root of session count
per stream, the standard rule for stationary block bootstrap.

Two independent block draws are taken (one per stream) because Baseline and
IslandPilot operate independent session calendars (different entry gates produce
different session counts and start times). Pairing is done at the **per-stream
metric level**, which preserves marginal distributions while remaining valid
under independent draws.

Output:
  results/04_bootstrap_results.json — point estimates, 95% CI, p-values, config
  paper_inserts/04_bootstrap.md     — text block for paper §6.1
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
RES = REPO / 'notebooks' / 'validation_analyses' / 'results'
INSERTS = REPO / 'notebooks' / 'validation_analyses' / 'paper_inserts'

STARTING_BALANCE = 10_000.0
N_BOOT = 10_000
ALPHA = 0.05
SEED = 20260426

rng = np.random.default_rng(SEED)


def _load_session_pnls(path: Path) -> np.ndarray:
    if not path.exists():
        raise SystemExit(f'expected session CSV missing: {path}')
    pnls = []
    with open(path) as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                pnls.append(float(row['pnl_usd']))
            except (KeyError, ValueError, TypeError):
                continue
    return np.asarray(pnls, dtype=float)


def _profit_factor(pnls: np.ndarray) -> float:
    gp = float(pnls[pnls > 0].sum())
    gl = float(-pnls[pnls < 0].sum())
    if gl <= 0:
        return float('inf') if gp > 0 else float('nan')
    return gp / gl


def _net_profit_pct(pnls: np.ndarray) -> float:
    return float(pnls.sum()) / STARTING_BALANCE * 100.0


def _moving_block_indices(n: int, block_len: int, rng) -> np.ndarray:
    """Return n indices drawn by moving-block bootstrap from a length-n series."""
    if n <= 0:
        return np.empty(0, dtype=int)
    n_blocks = int(math.ceil(n / block_len))
    starts = rng.integers(0, n - block_len + 1, size=n_blocks) if n > block_len else np.zeros(n_blocks, dtype=int)
    out = np.concatenate([np.arange(s, s + block_len) for s in starts])
    return out[:n]


def _bootstrap_metrics(pnls: np.ndarray, block_len: int, n_boot: int, rng) -> dict:
    n = len(pnls)
    npp = np.empty(n_boot, dtype=float)
    pf = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = _moving_block_indices(n, block_len, rng)
        sample = pnls[idx]
        npp[b] = _net_profit_pct(sample)
        v = _profit_factor(sample)
        pf[b] = v if math.isfinite(v) else np.nan
    return {'net_profit_pct_boot': npp, 'pf_boot': pf}


def _percentile_ci(arr: np.ndarray, alpha: float = ALPHA) -> tuple[float, float]:
    finite = arr[np.isfinite(arr)]
    if len(finite) == 0:
        return float('nan'), float('nan')
    lo = float(np.percentile(finite, 100.0 * alpha / 2))
    hi = float(np.percentile(finite, 100.0 * (1 - alpha / 2)))
    return lo, hi


def _bootstrap_p_value(diff_boot: np.ndarray, point_estimate: float) -> float:
    """Two-sided p-value via centring the bootstrap distribution at zero
    (testing H0: diff == 0). Returns the fraction of |centred draws| that
    are at least as extreme as the observed point estimate."""
    finite = diff_boot[np.isfinite(diff_boot)]
    if len(finite) == 0:
        return float('nan')
    centred = finite - finite.mean()
    extreme = np.sum(np.abs(centred) >= abs(point_estimate))
    return float((extreme + 1) / (len(finite) + 1))


def main():
    base_path = RES / '04_baseline_sessions.csv'
    isl_path = RES / '04_islandpilot_sessions.csv'

    base = _load_session_pnls(base_path)
    isl = _load_session_pnls(isl_path)

    # Block length: round( sqrt(N) ) per stream, conventional for stationary
    # block bootstrap on weakly-dependent series.
    bl_base = max(2, int(round(math.sqrt(len(base)))))
    bl_isl = max(2, int(round(math.sqrt(len(isl)))))

    print(f'Baseline    : N={len(base)}, block={bl_base}, '
          f'point net%={_net_profit_pct(base):.3f}, '
          f'point PF={_profit_factor(base):.4f}')
    print(f'IslandPilot : N={len(isl)}, block={bl_isl}, '
          f'point net%={_net_profit_pct(isl):.3f}, '
          f'point PF={_profit_factor(isl):.4f}')

    print(f'\nRunning {N_BOOT:,} block-bootstrap draws per stream…')
    boot_b = _bootstrap_metrics(base, bl_base, N_BOOT, rng)
    boot_i = _bootstrap_metrics(isl, bl_isl, N_BOOT, rng)

    # Pair the two independent draws to form difference distributions
    diff_npp = boot_i['net_profit_pct_boot'] - boot_b['net_profit_pct_boot']
    # PF difference: handle non-finite (no losses) by dropping those draws
    pf_b, pf_i = boot_b['pf_boot'], boot_i['pf_boot']
    finite_mask = np.isfinite(pf_b) & np.isfinite(pf_i)
    diff_pf = pf_i[finite_mask] - pf_b[finite_mask]

    point_npp_diff = _net_profit_pct(isl) - _net_profit_pct(base)
    point_pf_diff = _profit_factor(isl) - _profit_factor(base)

    ci_npp = _percentile_ci(diff_npp)
    ci_pf = _percentile_ci(diff_pf)

    p_npp = _bootstrap_p_value(diff_npp, point_npp_diff)
    p_pf = _bootstrap_p_value(diff_pf, point_pf_diff)

    # Marginal CIs on each pipeline (useful descriptive)
    ci_base_npp = _percentile_ci(boot_b['net_profit_pct_boot'])
    ci_isl_npp = _percentile_ci(boot_i['net_profit_pct_boot'])
    ci_base_pf = _percentile_ci(pf_b[np.isfinite(pf_b)])
    ci_isl_pf = _percentile_ci(pf_i[np.isfinite(pf_i)])

    out = {
        'config': {
            'n_boot': N_BOOT, 'alpha': ALPHA, 'seed': SEED,
            'starting_balance': STARTING_BALANCE,
            'block_len_baseline': bl_base, 'block_len_islandpilot': bl_isl,
            'n_sessions_baseline': len(base), 'n_sessions_islandpilot': len(isl),
        },
        'point_estimates': {
            'baseline_net_profit_pct': _net_profit_pct(base),
            'islandpilot_net_profit_pct': _net_profit_pct(isl),
            'baseline_profit_factor': _profit_factor(base),
            'islandpilot_profit_factor': _profit_factor(isl),
            'diff_net_profit_pp': point_npp_diff,
            'diff_profit_factor': point_pf_diff,
        },
        'ci_95_difference': {
            'net_profit_pp': {'lo': ci_npp[0], 'hi': ci_npp[1]},
            'profit_factor': {'lo': ci_pf[0], 'hi': ci_pf[1]},
        },
        'ci_95_marginal': {
            'baseline_net_pct': {'lo': ci_base_npp[0], 'hi': ci_base_npp[1]},
            'islandpilot_net_pct': {'lo': ci_isl_npp[0], 'hi': ci_isl_npp[1]},
            'baseline_pf': {'lo': ci_base_pf[0], 'hi': ci_base_pf[1]},
            'islandpilot_pf': {'lo': ci_isl_pf[0], 'hi': ci_isl_pf[1]},
        },
        'p_values_two_sided': {
            'net_profit_pp_diff_eq_0': p_npp,
            'profit_factor_diff_eq_0': p_pf,
        },
    }

    out_path = RES / '04_bootstrap_results.json'
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print(f'\nResults → {out_path.relative_to(REPO)}')

    # Compose paper insert
    INSERTS.mkdir(parents=True, exist_ok=True)
    md = INSERTS / '04_bootstrap.md'
    pe = out['point_estimates']
    ci = out['ci_95_difference']
    cm = out['ci_95_marginal']
    pv = out['p_values_two_sided']

    def _f(v, dp=3): return 'NaN' if v is None or (isinstance(v, float) and not math.isfinite(v)) else f'{v:.{dp}f}'

    md.write_text(
        f"### Block-Bootstrap Significance (insert for §6.1)\n\n"
        f"Method: moving-block bootstrap (Künsch 1989) on the time-ordered "
        f"per-session P&L sequence; "
        f"N = {N_BOOT:,} resamples per stream; "
        f"block length √N (Baseline {bl_base}, IslandPilot {bl_isl}); "
        f"two-sided percentile 95% CIs; seed = {SEED}.\n\n"
        f"| Quantity | Point | 95% CI (paired difference) |\n"
        f"|---|---:|---:|\n"
        f"| Baseline net profit % | {_f(pe['baseline_net_profit_pct'], 2)} | [{_f(cm['baseline_net_pct']['lo'], 2)}, {_f(cm['baseline_net_pct']['hi'], 2)}] (marginal) |\n"
        f"| IslandPilot net profit % | {_f(pe['islandpilot_net_profit_pct'], 2)} | [{_f(cm['islandpilot_net_pct']['lo'], 2)}, {_f(cm['islandpilot_net_pct']['hi'], 2)}] (marginal) |\n"
        f"| **IP − Baseline net profit (pp)** | **{_f(pe['diff_net_profit_pp'], 2)}** | **[{_f(ci['net_profit_pp']['lo'], 2)}, {_f(ci['net_profit_pp']['hi'], 2)}]** |\n"
        f"| Baseline profit factor | {_f(pe['baseline_profit_factor'], 4)} | [{_f(cm['baseline_pf']['lo'], 4)}, {_f(cm['baseline_pf']['hi'], 4)}] (marginal) |\n"
        f"| IslandPilot profit factor | {_f(pe['islandpilot_profit_factor'], 4)} | [{_f(cm['islandpilot_pf']['lo'], 4)}, {_f(cm['islandpilot_pf']['hi'], 4)}] (marginal) |\n"
        f"| **IP − Baseline profit factor** | **{_f(pe['diff_profit_factor'], 4)}** | **[{_f(ci['profit_factor']['lo'], 4)}, {_f(ci['profit_factor']['hi'], 4)}]** |\n\n"
        f"Two-sided bootstrap p-values (H₀ : diff = 0): "
        f"net-profit p = {_f(pv['net_profit_pp_diff_eq_0'], 4)}, "
        f"profit-factor p = {_f(pv['profit_factor_diff_eq_0'], 4)}.\n"
    )
    print(f'Paper insert → {md.relative_to(REPO)}')


if __name__ == '__main__':
    main()
