"""
63_preflight_baseline.py — IslandPilot pre-flight criterion false-positive rate.

The pre-flight architectural-validation criterion (Appendix F): "≥10 of top-20
genomes are OOS-profitable on the 3-month validation window (2024 Q2)".

Reviewers will ask: what is the probability a *random* (untrained) genome,
sampled uniformly from the production gene bounds, would be classified
profitable under the same rule? If random genomes routinely satisfy the
criterion, it has weak discriminating power.

This script:
  1. Builds the same production gene bounds used by the IslandPilot trainer
     (build_gene_bounds_from_strategy + Martingale).
  2. Samples K random genomes.
  3. Evaluates each on the 2024-04-01 → 2024-06-30 OOS window using the
     EXACT same backtest API and profitability rule as
     pipelines/_shared/IslandPilot/validate_model.py:
        net_pnl > 0 AND bust_rate < 0.40 AND n_sessions >= 3
  4. Computes the per-genome profitability rate p, its 95% Wilson CI, and
     the closed-form binomial probability that 20 random genomes contain
     ≥10 profitable. Also performs a 1000-sample bootstrap of 20-genome
     cohorts as a non-parametric cross-check.

Honest limitations:
  - Single OOS window (2024 Q2)
  - Single instrument (EUR-USD)
  - Modest K (30 by default, 60 if --k 60)
  - Random init reflects uniform sampling within bounds, not unconditional
    parameter space. Bounds themselves are designed for viability — so this
    measures the criterion's discrimination power *given* the production
    sample distribution, not against arbitrary parameter chaos.

Usage:
    QENGINE_TRAINING_MODE=1 /Users/naresh/miniconda3/bin/python3 \
        notebooks/validation_analyses/03_preflight_criterion_discrimination.py [--k 30] [--seed 0]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Repo-root sys.path / matplotlib backend / training-mode env
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
_REPO = _THIS_FILE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault('QENGINE_TRAINING_MODE', '1')

# matplotlib not strictly needed but follow project convention if added later
try:
    import matplotlib  # noqa: F401
    matplotlib.use('Agg')
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Constants — match validate_model.py exactly
# ---------------------------------------------------------------------------

OOS_START = '2024-04-01'
OOS_END = '2024-06-30'   # inclusive of full day
EXCHANGE = 'OANDA'
SYMBOL = 'EUR-USD'
TIMEFRAME = '5m'
STRATEGY = 'Martingale'
CANDLES_FILE = str(_REPO / 'candles_oanda_eurusd_1m_2022_2024.npy')

# Pipeline-only genes that must be stripped before passing HP to the strategy.
# Mirrors validate_model.py and train.py._run_backtest_fitness.
_PIPELINE_ONLY = {
    'gate_confidence_min', 'abort_aggressiveness', 'base_size_pct',
    'hysteresis_margin', 'confidence_sensitivity', 'recovery_aggression',
}

_BUST_OUTCOMES = {
    'abort', 'terminate', 'max_level_bust', 'sl_hit',
    'margin_call', 'margin_bust', 'max_level_sl',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date_to_ms(s: str) -> int:
    return int(datetime.strptime(s, '%Y-%m-%d').timestamp() * 1000)


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple:
    """Wilson score 95% CI for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p) — straight summation, ample for n=20."""
    if p <= 0:
        return 1.0 if k >= 0 else 0.0
    if p >= 1:
        return 0.0 if k < n else 1.0
    log_p = math.log(p)
    log_q = math.log(1 - p)
    log_fact = [0.0] * (n + 1)
    for i in range(1, n + 1):
        log_fact[i] = log_fact[i - 1] + math.log(i)

    def log_binom(nn, kk):
        return log_fact[nn] - log_fact[kk] - log_fact[nn - kk]

    total = 0.0
    for i in range(0, k + 1):
        total += math.exp(log_binom(n, i) + i * log_p + (n - i) * log_q)
    return min(1.0, max(0.0, total))


def _bootstrap_cohort_pass_rate(per_genome_profitable: list, cohort_size: int = 20,
                                threshold: int = 10, n_iter: int = 1000,
                                seed: int = 0) -> float:
    """Bootstrap: sample (with replacement) cohorts of `cohort_size` genomes
    from the K evaluated, count how many cohorts have >= `threshold` profitable.
    """
    rng = np.random.RandomState(seed)
    arr = np.array(per_genome_profitable, dtype=int)
    if len(arr) == 0:
        return 0.0
    pass_count = 0
    for _ in range(n_iter):
        sample = rng.choice(arr, size=cohort_size, replace=True)
        if int(sample.sum()) >= threshold:
            pass_count += 1
    return pass_count / n_iter


# ---------------------------------------------------------------------------
# Strategy / bounds loading (mirrors train.py)
# ---------------------------------------------------------------------------

def _load_strategy_class(strategy_name: str):
    """Load Martingale (or any strategy) without triggering the DB chain."""
    import importlib
    import types

    strategy_file = _REPO / 'strategies' / '_admin' / strategy_name / '__init__.py'
    if not strategy_file.exists():
        strategy_file = _REPO / 'strategies' / strategy_name / '__init__.py'
    if not strategy_file.exists():
        raise FileNotFoundError(f"Strategy {strategy_name} not found")

    parent = str(strategy_file.parent.parent)
    inserted = parent not in sys.path
    if inserted:
        sys.path.insert(0, parent)

    stub = types.ModuleType('qengine.strategies')
    class _LiteStrategy: pass
    stub.Strategy = _LiteStrategy
    stub.cached = lambda f: f
    orig = sys.modules.get('qengine.strategies')
    sys.modules['qengine.strategies'] = stub

    try:
        mod = importlib.import_module(strategy_name)
        cls = getattr(mod, strategy_name, None)
        if cls is None:
            raise ImportError(f"No class {strategy_name} in module")
        return cls
    finally:
        if orig is None:
            sys.modules.pop('qengine.strategies', None)
        else:
            sys.modules['qengine.strategies'] = orig
        if inserted and parent in sys.path:
            sys.path.remove(parent)


def _build_bounds():
    from pipelines._shared.IslandPilot.island_evolver import build_gene_bounds_from_strategy
    cls = _load_strategy_class(STRATEGY)
    dummy = cls.__new__(cls)
    return build_gene_bounds_from_strategy(dummy)


# ---------------------------------------------------------------------------
# Backtest invocation — mirrors validate_model.py exactly
# ---------------------------------------------------------------------------

def _trim_to_contiguous_start(candles_1m: np.ndarray) -> np.ndarray:
    """Same as train._trim_to_contiguous_start — first-pair gap fix."""
    while len(candles_1m) > 2 and candles_1m[1, 0] - candles_1m[0, 0] != 60_000:
        candles_1m = candles_1m[1:]
    return candles_1m


def _evaluate_genome(genes: dict, candles_subset: np.ndarray) -> dict:
    """Run a backtest on the OOS window for one genome and return a verdict dict.

    Mirrors validate_model.py's evaluation logic and profitability rule:
        profitable iff (n_sessions >= 3) AND (net_pnl > 0) AND (bust_rate < 0.40)
    """
    from qengine.research.backtest import backtest as run_bt
    from pipelines._shared.IslandPilot.train import _resolve_categorical_genes

    # Strip pipeline-only genes — same as validate_model
    hp = {k: v for k, v in genes.items() if k not in _PIPELINE_ONLY}
    hp = _resolve_categorical_genes(hp, STRATEGY)
    # Force preset='custom' so the strategy honours genome HPs (per task spec).
    hp.setdefault('preset', 'custom')

    config = {
        'starting_balance': 10_000,
        'fee': 0.0,
        'type': 'cfd',
        'exchange': EXCHANGE,
        'warm_up_candles': 210,
    }
    routes = [{
        'exchange': EXCHANGE, 'strategy': STRATEGY,
        'symbol': SYMBOL, 'timeframe': TIMEFRAME,
    }]
    candles_dict = {
        f'{EXCHANGE}-{SYMBOL}': {
            'exchange': EXCHANGE, 'symbol': SYMBOL,
            'candles': candles_subset,
        },
    }

    try:
        r = run_bt(
            config=config, routes=routes, data_routes=[],
            candles=candles_dict, hyperparameters=hp,
            generate_equity_curve=False, generate_logs=False,
            cost_model=True,
        )
    except Exception as e:
        return {
            'errored': True,
            'error': f'{type(e).__name__}: {e}',
            'n_sessions': 0, 'n_bust': 0, 'net_pnl': 0.0,
            'bust_rate': 0.0, 'profit_factor': None,
            'verdict': 'errored',
        }

    metrics = r.get('metrics', {}) if isinstance(r, dict) else {}
    sessions = r.get('sessions', []) if isinstance(r, dict) else []
    proper = [s for s in sessions if isinstance(s.get('session'), int)]
    n_sessions = len(proper)
    n_bust = sum(1 for s in proper if s.get('outcome') in _BUST_OUTCOMES)
    bust_rate = (n_bust / n_sessions) if n_sessions > 0 else 1.0

    net_pnl = metrics.get('net_profit', 0.0) or 0.0
    try:
        net_pnl = float(net_pnl)
        if math.isnan(net_pnl) or math.isinf(net_pnl):
            net_pnl = 0.0
    except (TypeError, ValueError):
        net_pnl = 0.0

    pf = metrics.get('profit_factor')
    try:
        pf = float(pf) if pf is not None else None
        if pf is not None and (math.isnan(pf) or math.isinf(pf)):
            pf = None
    except (TypeError, ValueError):
        pf = None

    # Mirror validate_model.py's verdict rule exactly
    if n_sessions < 3:
        verdict = 'too_few_sessions'
    elif net_pnl > 0 and bust_rate < 0.40:
        verdict = 'profitable'
    elif net_pnl < 0:
        verdict = 'losing'
    else:
        verdict = 'flat'

    return {
        'errored': False,
        'n_sessions': n_sessions, 'n_bust': n_bust,
        'bust_rate': round(bust_rate, 4),
        'net_pnl': round(net_pnl, 2),
        'profit_factor': (round(pf, 4) if pf is not None else None),
        'verdict': verdict,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--k', type=int, default=30,
                        help='Number of random genomes to evaluate (default 30).')
    parser.add_argument('--seed', type=int, default=0,
                        help='Master seed for genome sampling.')
    parser.add_argument('--candles-file', default=CANDLES_FILE)
    parser.add_argument('--out', default=str(_THIS_FILE.parent / 'results' / '63_preflight_baseline.json'))
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print('=' * 78)
    print('IslandPilot Pre-flight Criterion — False-Positive (Random) Baseline')
    print('=' * 78)
    print(f'OOS window:    {OOS_START} → {OOS_END}')
    print(f'Strategy:      {STRATEGY}')
    print(f'Instrument:    {EXCHANGE} {SYMBOL} {TIMEFRAME}')
    print(f'Candles file:  {args.candles_file}')
    print(f'K genomes:     {args.k}')
    print(f'Master seed:   {args.seed}')
    print('-' * 78)

    # --- Load candles & subset to OOS window ---
    if not Path(args.candles_file).exists():
        print(f'ERROR: candles file not found: {args.candles_file}')
        sys.exit(1)

    print(f'Loading 1m candles from {args.candles_file} ...')
    candles_1m = np.load(args.candles_file)
    print(f'  Loaded {len(candles_1m):,} 1m candles.')

    ts_start = _date_to_ms(OOS_START)
    ts_end = _date_to_ms(OOS_END) + 86_400_000
    mask = (candles_1m[:, 0] >= ts_start) & (candles_1m[:, 0] <= ts_end)
    subset = candles_1m[mask]
    subset = _trim_to_contiguous_start(subset)
    print(f'  OOS subset: {len(subset):,} 1m candles '
          f'({len(subset)/1440:.1f} trading days approx).')
    if len(subset) < 2000:
        print('ERROR: OOS subset too small.')
        sys.exit(1)

    # --- Build production gene bounds ---
    print('\nBuilding production gene bounds from Martingale strategy ...')
    bounds = _build_bounds()
    print(f'  {len(bounds)} genes in bounds.')

    # --- Sample K random genomes & evaluate each ---
    from pipelines._shared.IslandPilot.island_evolver import Genome

    rng = np.random.RandomState(args.seed)
    seeds = [int(rng.randint(0, 2**31)) for _ in range(args.k)]

    per_genome = []
    n_profitable = 0
    n_losing = 0
    n_few = 0
    n_flat = 0
    n_errored = 0
    t0 = time.time()

    print(f'\nEvaluating {args.k} random genomes on OOS window ...')
    print(f'{"i":>3} {"seed":>10} {"n_sess":>7} {"busts":>6} {"PF":>6} '
          f'{"net$":>9} {"verdict":<18} {"elapsed":>8}')
    print('-' * 78)

    for i, gseed in enumerate(seeds, start=1):
        g = Genome.random(seed=gseed, bounds=bounds)
        res = _evaluate_genome(g.genes, subset)
        elapsed_total = time.time() - t0

        if res['errored']:
            n_errored += 1
        elif res['verdict'] == 'profitable':
            n_profitable += 1
        elif res['verdict'] == 'losing':
            n_losing += 1
        elif res['verdict'] == 'too_few_sessions':
            n_few += 1
        else:
            n_flat += 1

        pf_str = (f'{res["profit_factor"]:.2f}'
                  if res.get('profit_factor') is not None else 'N/A')
        print(f'{i:>3} {gseed:>10} {res["n_sessions"]:>7} '
              f'{res["n_bust"]:>6} {pf_str:>6} {res["net_pnl"]:>9.2f} '
              f'{res["verdict"]:<18} {elapsed_total:>7.0f}s'
              f'   [profitable so far: {n_profitable}/{i}]')

        per_genome.append({
            'i': i, 'seed': gseed,
            'genes': g.genes,
            **res,
        })

    print('-' * 78)
    elapsed = time.time() - t0
    print(f'\nTotal eval time: {elapsed:.1f}s ({elapsed/60:.2f} min)')
    print(f'  Profitable:        {n_profitable}/{args.k}')
    print(f'  Losing:            {n_losing}/{args.k}')
    print(f'  Too few sessions:  {n_few}/{args.k}')
    print(f'  Flat:              {n_flat}/{args.k}')
    print(f'  Errored:           {n_errored}/{args.k}')

    # --- Compute statistics ---
    # Denominator: K minus errored genomes (errored = data not informative).
    n_evaluated = args.k - n_errored
    p_hat = n_profitable / n_evaluated if n_evaluated > 0 else 0.0
    wilson_lo, wilson_hi = _wilson_ci(n_profitable, n_evaluated)

    # Closed-form binomial: P(X >= 10 | X ~ Binomial(20, p_hat))
    # = 1 - F_binomial(9; 20, p_hat)
    p_pass_closed = 1 - _binom_cdf(9, 20, p_hat)

    # Wilson-CI envelope on the pass probability
    p_pass_lo = 1 - _binom_cdf(9, 20, wilson_lo)
    p_pass_hi = 1 - _binom_cdf(9, 20, wilson_hi)

    # Bootstrap from observed binary outcomes (only over evaluated genomes)
    binary = [1 if g['verdict'] == 'profitable' else 0
              for g in per_genome if not g['errored']]
    p_pass_boot = _bootstrap_cohort_pass_rate(
        binary, cohort_size=20, threshold=10, n_iter=1000, seed=args.seed)

    # Same statistics for the script-default 10-of-10 framing
    p_pass_10of10_closed = 1 - _binom_cdf(4, 10, p_hat)  # >=5 / 10 (loose)
    p_pass_10top_closed  = 1 - _binom_cdf(9, 10, p_hat)  # all-10 / 10 (strict)

    print('\n' + '=' * 78)
    print('STATISTICS')
    print('=' * 78)
    print(f'Evaluated genomes (excl. errored): {n_evaluated}')
    print(f'Per-genome profitability rate p:   {p_hat:.4f}')
    print(f'Wilson 95% CI:                     [{wilson_lo:.4f}, {wilson_hi:.4f}]')
    print()
    print('Pre-flight criterion: ≥10 of 20 random genomes profitable')
    print(f'  Closed-form (binomial, p̂):       P = {p_pass_closed:.4f}')
    print(f'  Closed-form (Wilson lo, hi):     P ∈ [{p_pass_lo:.4f}, {p_pass_hi:.4f}]')
    print(f'  Bootstrap (1000×, n=20, ≥10):    P = {p_pass_boot:.4f}')
    print()
    print('Auxiliary thresholds (for script-default --top-n 10 framing):')
    print(f'  ≥5 / 10 random genomes profitable:  P = {p_pass_10of10_closed:.4f}')
    print(f'  10 / 10 random genomes profitable:  P = {p_pass_10top_closed:.4f}')

    # Verdict on criterion strength
    if p_pass_closed < 0.05:
        strength = 'strong'
        comment = ('Criterion has meaningful discrimination power: '
                   'random genomes are very unlikely to clear it. Defensible '
                   'as a structural-bug detector.')
    elif p_pass_closed < 0.30:
        strength = 'moderate'
        comment = ('Criterion has partial discrimination power. Random '
                   'pass rate is non-trivial but well below 1/2 — passing '
                   'still indicates non-random behaviour, but the criterion '
                   'is closer to a sanity check than a calibrated test.')
    else:
        strength = 'weak'
        comment = ('Random genomes pass the criterion frequently. The '
                   'criterion is closer to a coin flip than a discriminating '
                   'test. Recalibration to a higher threshold (e.g. 14/20) '
                   'would be advisable to retain bug-detection power.')
    print(f'\nVerdict on criterion strength: {strength.upper()}')
    print(comment)

    # --- Persist JSON result ---
    payload = {
        'meta': {
            'script': str(_THIS_FILE),
            'generated_at_utc': datetime.utcnow().isoformat() + 'Z',
            'oos_start': OOS_START,
            'oos_end': OOS_END,
            'exchange': EXCHANGE,
            'symbol': SYMBOL,
            'timeframe': TIMEFRAME,
            'strategy': STRATEGY,
            'candles_file': args.candles_file,
            'master_seed': args.seed,
            'K': args.k,
            'gene_bounds_count': len(bounds),
            'profitability_rule': (
                'n_sessions >= 3 AND net_pnl > 0 AND bust_rate < 0.40 '
                '(mirrors pipelines/_shared/IslandPilot/validate_model.py)'
            ),
            'eval_total_seconds': round(elapsed, 1),
        },
        'counts': {
            'profitable': n_profitable,
            'losing': n_losing,
            'too_few_sessions': n_few,
            'flat': n_flat,
            'errored': n_errored,
            'evaluated_excl_errored': n_evaluated,
        },
        'statistics': {
            'p_profitable': p_hat,
            'wilson_95_ci': [wilson_lo, wilson_hi],
            'p_pass_10_of_20_closed_form': p_pass_closed,
            'p_pass_10_of_20_wilson_lo': p_pass_lo,
            'p_pass_10_of_20_wilson_hi': p_pass_hi,
            'p_pass_10_of_20_bootstrap_1000x': p_pass_boot,
            'p_pass_5_of_10_closed_form': p_pass_10of10_closed,
            'p_pass_10_of_10_closed_form': p_pass_10top_closed,
        },
        'verdict': {
            'criterion_strength': strength,
            'comment': comment,
        },
        'per_genome': per_genome,
    }

    with open(out_path, 'w') as f:
        json.dump(payload, f, indent=2, default=str)
    print(f'\nWrote results → {out_path}')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
