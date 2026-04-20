"""
53 — CoEvolGPPilot offline training.

Fits a 3-state HMM / GMM on the top-K features selected by mutual information
against a proxy target (sign of the next 20-candle return), then evolves one
genetic population per state against the real qengine backtest engine. Saves
the artefacts into ``pipelines/_shared/CoEvolGPPilot/models/``.

Usage:
    python3 53_coevol_gp_train.py                 # full run (2022-2024)
    python3 53_coevol_gp_train.py --smoke         # 2-month smoke run
    python3 53_coevol_gp_train.py --start 2023-06-01 --end 2023-07-31
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Project path setup — mirrors other phaseX scripts.
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

# Reuse phase4 utilities for candle loading / plotting conventions.
PHASE4_DIR = PROJECT_ROOT / 'notebooks' / 'phase4'
if str(PHASE4_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE4_DIR))
from utils import load_candles, concat_candles  # noqa: E402

import qengine.helpers as jh  # noqa: E402
from qengine.framework.components.feature_selector import (  # noqa: E402
    FeaturePool, compute_feature_matrix, select_features,
)
from qengine.framework.components.island_evolver import (  # noqa: E402
    IslandEvolver, Genome, GENE_BOUNDS, build_gene_bounds_from_strategy,
)
from qengine.research.backtest import backtest  # noqa: E402
from qengine.research.candles import get_candles  # noqa: E402

# Pipeline package
from pipelines._shared.CoEvolGPPilot.config import (  # noqa: E402
    DEFAULT_CONFIG, STATE_IDS,
)
from pipelines._shared.CoEvolGPPilot.hmm_regime import (  # noqa: E402
    HMMRegimeModel, hmmlearn_available,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PHASE5_DIR = Path(__file__).resolve().parent
PLOTS_DIR = PHASE5_DIR / 'plots'
RESULTS_DIR = PHASE5_DIR / 'results'
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

PIPELINE_MODELS = (
    PROJECT_ROOT / 'pipelines' / '_shared' / 'CoEvolGPPilot' / 'models'
)
PIPELINE_MODELS.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    ts = time.strftime('%H:%M:%S')
    print(f'[{ts}] {msg}', flush=True)


# ---------------------------------------------------------------------------
# Feature matrix computation (reusable helper)
# ---------------------------------------------------------------------------

def _build_feature_matrix(candles: np.ndarray):
    """Compute the full feature matrix and return both matrix + names."""
    log(f'Computing feature matrix on {len(candles)} candles...')
    pool = FeaturePool()
    matrix, names = compute_feature_matrix(candles, pool)
    log(f'Matrix: {matrix.shape} — features: {names}')
    return matrix, names


def _proxy_target(candles: np.ndarray, horizon: int = 20) -> np.ndarray:
    """Binary proxy: sign of the next ``horizon``-candle return.

    Paper uses cycle-outcome labels; we approximate by forward-return sign which
    correlates with Martingale cycle outcomes on low-noise timeframes.
    """
    close = candles[:, 2].astype(np.float64)
    future = np.full_like(close, np.nan)
    future[:-horizon] = close[horizon:]
    ret = (future - close) / (close + 1e-12)
    target = (ret > 0).astype(int)
    target[np.isnan(future)] = 0
    return target


# ---------------------------------------------------------------------------
# Backtest-based fitness
# ---------------------------------------------------------------------------

def _make_fitness_fn(trading_1m, warmup_1m, exchange: str, symbol: str):
    key = f'{exchange}-{symbol}'
    weights = DEFAULT_CONFIG['fitness_weights']

    candles = {key: {'exchange': exchange, 'symbol': symbol, 'candles': trading_1m}}
    warmup_dict = (
        {key: {'exchange': exchange, 'symbol': symbol, 'candles': warmup_1m}}
        if warmup_1m.ndim == 2 and len(warmup_1m) > 0
        else None
    )

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
    cat_maps = {
        'sizing_curve': {0: 'geometric', 1: 'sqrt', 2: 'linear', 3: 'fibonacci'},
        'base_size_mode': {0: 'pct_equity', 1: 'capital_aware'},
        'hedge_mode': {0: 'fixed_pips', 1: 'atr_based', 2: 'percentage'},
        'hedge_expand': {0: 'no', 1: 'yes'},
        'tp_mode': {0: 'fixed_pips', 1: 'atr_based', 2: 'bucket_pct', 3: 'risk_reward'},
    }

    def _fitness(genes: dict) -> float:
        hp = {'preset': 'custom'}
        for gene_name, hp_name in gene_to_hp.items():
            if gene_name not in genes:
                continue
            val = genes[gene_name]
            if gene_name in cat_maps:
                if isinstance(val, (int, float)):
                    val = cat_maps[gene_name].get(
                        int(round(val)), list(cat_maps[gene_name].values())[0]
                    )
            elif isinstance(val, float) and gene_name in (
                'max_levels', 'hedge_atr_period', 'tp_atr_period',
            ):
                val = int(round(val))
            hp[hp_name] = val

        try:
            result = backtest(
                config={
                    'starting_balance': 10000,
                    'fee': 0,
                    'type': 'cfd',
                    'exchange': exchange,
                    'warm_up_candles': 10000,
                },
                routes=[{
                    'exchange': exchange, 'symbol': symbol,
                    'timeframe': '30m', 'strategy': 'Martingale',
                }],
                data_routes=[],
                candles=candles,
                warmup_candles=warmup_dict,
                hyperparameters=hp,  # flat dict — route-keyed form is silently ignored by backtest_mode.py:864
                generate_equity_curve=False,
                generate_logs=False,
            )
        except Exception:
            return -1000.0

        m = result.get('metrics', {}) or {}
        pf = m.get('profit_factor', 0) or 0
        max_dd = abs(m.get('max_drawdown', -100) or 100)
        sessions = m.get('total_sessions', 0) or 0
        bust_rate = m.get('bust_rate', 1.0) or 1.0
        if sessions < 10:
            return -1000.0

        return (
            weights['pf'] * (pf - 1.0) * 100
            + weights['dd'] * max(0.0, 100 - max_dd * 5)
            + weights['bust'] * (1.0 - bust_rate) * 100
            + weights['sessions'] * min(sessions / 100.0, 1.0) * 100
        )

    return _fitness


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def plot_posterior_timeline(posteriors: np.ndarray, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 4))
    t = np.arange(len(posteriors))
    colors = ['#2ca02c', '#1f77b4', '#d62728']
    for i in range(posteriors.shape[1]):
        ax.plot(t, posteriors[:, i], label=STATE_IDS[i], color=colors[i], linewidth=0.6, alpha=0.9)
    ax.set_title('CoEvolGPPilot: HMM/GMM posterior probabilities on training window')
    ax.set_xlabel('candle index')
    ax.set_ylabel('p(state | obs)')
    ax.set_ylim(-0.02, 1.02)
    ax.legend(loc='upper right', fontsize=9)
    fig.tight_layout()
    fig.savefig(str(out_path), dpi=120, bbox_inches='tight')
    plt.close(fig)


def plot_state_usage(posteriors: np.ndarray, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    usage = posteriors.mean(axis=0)
    bars = ax.bar(STATE_IDS, usage, color=['#2ca02c', '#1f77b4', '#d62728'])
    ax.set_ylim(0, 1)
    ax.set_ylabel('Mean posterior probability')
    ax.set_title('Average state usage on training window')
    for bar, v in zip(bars, usage):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.01, f'{v:.2f}',
                ha='center', fontsize=9)
    fig.tight_layout()
    fig.savefig(str(out_path), dpi=120, bbox_inches='tight')
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2022-01-01')
    parser.add_argument('--end', default='2023-12-31')
    parser.add_argument('--smoke', action='store_true',
                        help='Run a 2-month smoke test instead of the full window.')
    parser.add_argument('--generations', type=int,
                        default=DEFAULT_CONFIG['evolution']['max_generations'])
    parser.add_argument('--pop-size', type=int,
                        default=DEFAULT_CONFIG['evolution']['population_size'])
    parser.add_argument('--top-k', type=int,
                        default=DEFAULT_CONFIG['hmm']['top_k_features'])
    parser.add_argument('--no-evolve', action='store_true',
                        help='Fit HMM only; skip GA (handy for debugging).')
    args = parser.parse_args()

    if args.smoke:
        args.start = '2023-06-01'
        args.end = '2023-07-31'
        args.generations = max(1, min(args.generations, 2))
        args.pop_size = max(4, min(args.pop_size, 6))

    log('=' * 60)
    log('Script 53 — CoEvolGPPilot offline training')
    log(f'hmmlearn available: {hmmlearn_available()}')
    log(f'Training window:    {args.start} → {args.end}')
    log(f'Top-K features:     {args.top_k}')
    log(f'GA population:      {args.pop_size}')
    log(f'GA generations:     {args.generations}')
    log('=' * 60)

    # 1. Load EUR-USD 30m candles for feature/HMM training
    log('Loading EUR-USD 30m candles for HMM fitting...')
    warmup_30m, trading_30m = load_candles(
        timeframe='30m',
        start_date=args.start,
        end_date=args.end,
        warmup_candles_num=500,
    )
    candles_30m = concat_candles(warmup_30m, trading_30m)
    log(f'30m candles: {candles_30m.shape}')

    # 2. Compute features & pick top-K by MI against proxy target
    feature_matrix, feature_names = _build_feature_matrix(candles_30m)
    target = _proxy_target(candles_30m, horizon=20)
    log('Selecting top-K features by mutual information...')
    selected_indices, scores = select_features(
        feature_matrix, target, k=args.top_k,
    )
    if not selected_indices:
        log('WARNING: no features selected — using first 5 by default.')
        selected_indices = list(range(min(5, feature_matrix.shape[1])))
        scores = [0.0] * len(selected_indices)
    selected_names = [feature_names[i] for i in selected_indices]
    log(f'Selected features: {list(zip(selected_names, [round(s, 4) for s in scores]))}')

    X_all = feature_matrix[:, selected_indices]
    valid_mask = ~np.any(np.isnan(X_all), axis=1)
    X_train = X_all[valid_mask]
    log(f'Valid feature rows for HMM fitting: {X_train.shape}')

    # 3. Fit HMM (or GMM fallback)
    log('Fitting HMM...')
    hmm = HMMRegimeModel(
        n_states=DEFAULT_CONFIG['hmm']['n_states'],
        n_mix=DEFAULT_CONFIG['hmm']['n_mix'],
        covariance_type=DEFAULT_CONFIG['hmm']['covariance_type'],
        n_iter=DEFAULT_CONFIG['hmm']['n_iter'],
        tol=DEFAULT_CONFIG['hmm']['tol'],
        random_state=DEFAULT_CONFIG['hmm']['random_state'],
    )
    hmm.fit(X_train)
    hmm.feature_names = selected_names
    hmm.feature_indices = selected_indices
    log(f'HMM fitted. Backend: {hmm.backend}')

    # Posteriors on the training window for plotting/inspection
    posteriors_train = hmm.posteriors(np.nan_to_num(X_all, nan=0.0))
    log(f'Posterior matrix: {posteriors_train.shape}')

    # 4. Persist HMM artefacts immediately
    hmm.save(str(PIPELINE_MODELS / 'hmm.pkl'))
    hmm.save_metadata_json(str(PIPELINE_MODELS / 'hmm_meta.json'))
    log(f'HMM saved to {PIPELINE_MODELS}')

    # 5. Plots
    plot_posterior_timeline(posteriors_train, PLOTS_DIR / '53_hmm_posteriors.png')
    plot_state_usage(posteriors_train, PLOTS_DIR / '53_state_usage.png')
    log(f'Plots saved to {PLOTS_DIR}')

    # 6. Build evolver (one island per HMM state) and run a short GA
    if args.no_evolve:
        log('Skipping GA (--no-evolve).')
        return

    log('Loading 1m candles for real-engine backtests...')
    ex, sym = 'OANDA', 'EUR-USD'
    warmup_1m, trading_1m = get_candles(
        exchange=ex,
        symbol=sym,
        timeframe='1m',
        start_date_timestamp=jh.date_to_timestamp(args.start),
        finish_date_timestamp=jh.date_to_timestamp(args.end),
        warmup_candles_num=10000,
    )
    log(f'1m candles: trading={len(trading_1m)}, '
        f"warmup={len(warmup_1m) if warmup_1m.ndim == 2 else 0}")

    # Build strategy-aware gene bounds so the GA tunes the Martingale HPs
    try:
        from strategies._admin.Martingale import Martingale
        s = Martingale.__new__(Martingale)
        s.hp = {}
        gene_bounds = build_gene_bounds_from_strategy(s)
    except Exception as exc:
        log(f'Could not load Martingale HP spec ({exc}); using default bounds.')
        gene_bounds = dict(GENE_BOUNDS)
    log(f'Gene bounds: {len(gene_bounds)} genes')

    evolver = IslandEvolver(
        leaf_ids=list(STATE_IDS),
        config={
            'pop_size': args.pop_size,
            'elitism': DEFAULT_CONFIG['evolution']['elitism_count'],
            'crossover_rate': DEFAULT_CONFIG['evolution']['crossover_rate'],
            'mutation_rate': DEFAULT_CONFIG['evolution']['mutation_rate'],
            'mutation_sigma': DEFAULT_CONFIG['evolution']['mutation_sigma_pct'],
            'tournament_k': DEFAULT_CONFIG['evolution']['tournament_k'],
        },
        gene_bounds=gene_bounds,
    )

    fitness_fn = _make_fitness_fn(trading_1m, warmup_1m, ex, sym)

    log('Starting GA evolution...')
    for gen in range(args.generations):
        gen_start = time.time()
        log(f'-- Generation {gen + 1}/{args.generations} --')
        for sid in STATE_IDS:
            pop = evolver.populations[sid]
            n_eval = 0
            for ind in pop.individuals:
                if ind.fitness is None:
                    ind.fitness = fitness_fn(ind.genes)
                    n_eval += 1
            if n_eval:
                best = max(
                    (g.fitness for g in pop.individuals if g.fitness is not None),
                    default=None,
                )
                log(f'  {sid}: evaluated {n_eval}, best fitness so far = {best}')
        # Evolve each population
        for sid in STATE_IDS:
            pop = evolver.populations[sid]
            pop.evolve(
                elitism=DEFAULT_CONFIG['evolution']['elitism_count'],
                crossover_rate=DEFAULT_CONFIG['evolution']['crossover_rate'],
                mutation_rate=DEFAULT_CONFIG['evolution']['mutation_rate'],
                mutation_sigma=DEFAULT_CONFIG['evolution']['mutation_sigma_pct'],
                tournament_k=DEFAULT_CONFIG['evolution']['tournament_k'],
            )
        log(f'  Generation {gen + 1} done in {time.time() - gen_start:.0f}s')

    # Evaluate final offspring once so best_per_state makes sense
    log('Evaluating final offspring...')
    for sid in STATE_IDS:
        pop = evolver.populations[sid]
        for ind in pop.individuals:
            if ind.fitness is None:
                ind.fitness = fitness_fn(ind.genes)

    # 7. Persist evolver + compact genome summary
    evolver.save(str(PIPELINE_MODELS / 'island_evolver.json'))
    genomes_summary = {}
    for sid in STATE_IDS:
        try:
            genomes_summary[sid] = evolver.get_best_genome(sid)
        except Exception:
            genomes_summary[sid] = {}
    with open(PIPELINE_MODELS / 'island_genomes.json', 'w') as f:
        json.dump(genomes_summary, f, indent=2)
    log(f'Evolver saved to {PIPELINE_MODELS}')

    # 8. Save a training summary JSON
    summary = {
        'start': args.start,
        'end': args.end,
        'smoke': args.smoke,
        'hmmlearn_available': hmmlearn_available(),
        'hmm_backend': hmm.backend,
        'selected_features': selected_names,
        'mi_scores': [float(s) for s in scores],
        'generations': args.generations,
        'population_size': args.pop_size,
        'n_states': len(STATE_IDS),
        'state_usage': {
            sid: float(posteriors_train[:, i].mean())
            for i, sid in enumerate(STATE_IDS)
        },
        'best_fitness': {
            sid: (genomes_summary[sid] or {}).get('fitness')
            for sid in STATE_IDS
        },
    }
    with open(RESULTS_DIR / '53_coevol_gp_training.json', 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    log(f'Summary saved to {RESULTS_DIR}/53_coevol_gp_training.json')
    log('Done.')


if __name__ == '__main__':
    main()
