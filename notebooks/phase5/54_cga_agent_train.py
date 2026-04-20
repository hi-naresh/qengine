"""
54 — CGAAgentPilot offline warm-start training.

Trains (warm-starts) the CGAAgentPilot population by:

  1. Loading EUR-USD 30m candles for 2022-01-01 → 2023-12-31 via
     qengine.research.candles.get_candles() (checks warmup.ndim == 2).
  2. Running 5 generations of a standard GA on the first 6 months
     against a Martingale strategy via qengine's real backtest engine.
  3. Saving the warm-started population + AgentCoordinator state into
     pipelines/_shared/CGAAgentPilot/models/.
  4. Plotting best-fitness and mutation-σ trajectories.

Smoke-mode: set SMOKE=1 env var for a 2-month window + 2 generations.

Reference: notebooks/phase4/50_real_engine_evolution.py
"""

import os
import sys
import json
import time
from pathlib import Path

# --- path setup (match notebooks/phase4 pattern) ------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.chdir(str(Path(__file__).resolve().parents[2]))

import numpy as np

# headless plotting — no jupyter available in conda env
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from qengine.research.backtest import backtest
from qengine.research.candles import get_candles
from qengine.framework.components.island_evolver import (
    build_gene_bounds_from_strategy,
    GENE_BOUNDS,
    Genome,
)
import qengine.helpers as jh

# Pipeline imports
from pipelines._shared.CGAAgentPilot import CGAAgentPilot
from pipelines._shared.CGAAgentPilot.rolling_ga import RollingGA, compute_fitness
from pipelines._shared.CGAAgentPilot.agent_coordinator import AgentCoordinator
from pipelines._shared.CGAAgentPilot.config import DEFAULT_CONFIG


SMOKE = bool(int(os.environ.get('SMOKE', '0')))
SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_MODELS = (Path(__file__).resolve().parents[2]
                   / 'pipelines' / '_shared' / 'CGAAgentPilot' / 'models')
PIPELINE_MODELS.mkdir(parents=True, exist_ok=True)
PLOTS_DIR = SCRIPT_DIR / 'plots'
PLOTS_DIR.mkdir(exist_ok=True)
RESULTS_DIR = SCRIPT_DIR / 'results'
RESULTS_DIR.mkdir(exist_ok=True)


# -----------------------------------------------------------------------
# 1. Load candles
# -----------------------------------------------------------------------

EX, SYM = 'OANDA', 'EUR-USD'
KEY = f'{EX}-{SYM}'

if SMOKE:
    TRAIN_START, TRAIN_END = '2022-01-01', '2022-03-01'
    WARMSTART_START, WARMSTART_END = '2022-01-01', '2022-02-01'
    MAX_GENS = 2
    POP_SIZE = 8
else:
    TRAIN_START, TRAIN_END = '2022-01-01', '2023-12-31'
    WARMSTART_START, WARMSTART_END = '2022-01-01', '2022-07-01'
    MAX_GENS = 5
    POP_SIZE = DEFAULT_CONFIG['ga']['population_size']

print(f'Mode: {"SMOKE" if SMOKE else "FULL"}')
print(f'Loading 1m candles {WARMSTART_START} to {WARMSTART_END} '
      f'(backtest engine requires 1m; route timeframe is 30m) ...')

# qengine.research.backtest requires candles at 1m — the engine aggregates
# to the route's declared timeframe (30m) internally.
warmup_1m, trading_1m = get_candles(
    exchange=EX,
    symbol=SYM,
    timeframe='1m',
    start_date_timestamp=jh.date_to_timestamp(WARMSTART_START),
    finish_date_timestamp=jh.date_to_timestamp(WARMSTART_END),
    warmup_candles_num=10000,
)

if not (warmup_1m.ndim == 2 and len(warmup_1m) > 0):
    warmup_1m = None
    print('  (no warmup candles — start-of-data)')

print(f'Warm-start data: {len(trading_1m)} trading 1m candles, '
      f'{len(warmup_1m) if warmup_1m is not None else 0} warmup candles')


# -----------------------------------------------------------------------
# 2. Prepare gene bounds (need a live strategy instance)
# -----------------------------------------------------------------------
# We discover Martingale HP spec dynamically by instantiating the strategy
# via qengine's registry, the same way IslandPilot does it at training time.

print('Resolving Martingale hyperparameter spec ...')
from strategies._admin.Martingale import Martingale
_dummy = Martingale.__new__(Martingale)
gene_bounds = build_gene_bounds_from_strategy(_dummy)
# Inject pipeline-level genes from config
for name, spec in DEFAULT_CONFIG['pipeline_gene_bounds'].items():
    lo, hi, dtype = spec
    _type = int if dtype == 'int' else float
    gene_bounds[name] = (lo, hi, _type)
print(f'  {len(gene_bounds)} gene dimensions')


# -----------------------------------------------------------------------
# 3. Fitness = per-genome real backtest over the warm-start window
# -----------------------------------------------------------------------

HP_SPEC = {
    h['name']: h for h in _dummy.hyperparameters()
    if isinstance(h, dict) and 'name' in h
}
_TUNABLE_GROUPS = {'General', 'Grid / Hedge', 'Take Profit'}
_SAFE_OPTIONS = {
    'signal_mode': {'random', 'ema_cross', 'rsi', 'macd', 'supertrend',
                    'stoch', 'ema_rsi', 'ema_macd', 'triple'},
    'hedge_mode': {'fixed_pips', 'atr_based', 'percentage'},
    'tp_mode': {'fixed_pips', 'atr_based', 'bucket_pct', 'risk_reward'},
    'base_size_mode': {'pct_equity', 'capital_aware'},
    'sizing_curve': {'geometric', 'sqrt', 'linear', 'fibonacci'},
}


def genome_to_hp(genes: dict) -> dict:
    """Translate genome genes -> Martingale HP overrides (mirrors pipeline)."""
    hp = {'preset': 'custom'}
    for name, spec in HP_SPEC.items():
        group = spec.get('group', '')
        if group not in _TUNABLE_GROUPS or name not in genes:
            continue
        val = genes[name]
        hp_type = spec.get('type')
        if hp_type == 'categorical':
            options = spec.get('options', [])
            safe = _SAFE_OPTIONS.get(name)
            if safe:
                options = [o for o in options if o in safe]
            if not options:
                continue
            if isinstance(val, (int, float)):
                idx = max(0, min(int(round(val)), len(options) - 1))
                hp[name] = options[idx]
            elif val in options:
                hp[name] = val
        elif hp_type in (int, float) or hp_type in ('int', 'float'):
            lo = spec.get('min', float('-inf'))
            hi = spec.get('max', float('inf'))
            val = max(lo, min(hi, float(val)))
            if hp_type in (int, 'int'):
                val = int(round(val))
            hp[name] = val
    return hp


def evaluate_genome(genes: dict) -> float:
    """Run a real backtest with this genome and return composite fitness."""
    hp = genome_to_hp(genes)
    candles = {KEY: {'exchange': EX, 'symbol': SYM, 'candles': trading_1m}}
    warmup_dict = (
        {KEY: {'exchange': EX, 'symbol': SYM, 'candles': warmup_1m}}
        if warmup_1m is not None else None
    )
    try:
        result = backtest(
            config={'starting_balance': 10000, 'fee': 0, 'type': 'cfd',
                    'exchange': EX, 'warm_up_candles': 10000},
            routes=[{'exchange': EX, 'symbol': SYM,
                     'timeframe': '30m', 'strategy': 'Martingale'}],
            data_routes=[],
            candles=candles,
            warmup_candles=warmup_dict,
            hyperparameters=hp,  # flat dict — route-keyed form is silently ignored by backtest_mode.py:864
            generate_equity_curve=False,
            generate_logs=False,
        )
        m = result.get('metrics', {}) or {}
        pf = m.get('profit_factor', 0) or 0
        max_dd = abs(m.get('max_drawdown', -100) or -100)
        sessions = m.get('total_sessions', 0) or 0
        bust_rate = m.get('bust_rate', 1.0) or 0.0

        if sessions < 3:
            return -100.0

        return (
            0.4 * (pf - 1.0) * 100.0
            + 0.3 * max(0.0, 100.0 - max_dd * 5.0)
            + 0.2 * (1.0 - bust_rate) * 100.0
            + 0.1 * min(sessions / 100.0, 1.0) * 100.0
        )
    except Exception as e:
        print(f'  backtest error: {e!r}')
        return -100.0


# -----------------------------------------------------------------------
# 4. Warm-start the population with N generations of standard GA
# -----------------------------------------------------------------------

print(f'\nWarm-starting RollingGA: {POP_SIZE} individuals x {MAX_GENS} generations ...')

ga = RollingGA(
    gene_bounds=gene_bounds,
    population_size=POP_SIZE,
    rolling_window_cycles=DEFAULT_CONFIG['rolling_window_cycles'],
    elitism=DEFAULT_CONFIG['ga']['elitism'],
)

coordinator = AgentCoordinator(
    cfg=DEFAULT_CONFIG['coordinator'],
    ga_cfg=DEFAULT_CONFIG['ga'],
)

best_history = []
sigma_history = []

t0 = time.time()
for gen in range(MAX_GENS):
    gen_t = time.time()
    print(f'\n--- Generation {gen + 1}/{MAX_GENS} ---')

    # Evaluate everyone (standard GA — not rolling-window scoring)
    for i, ind in enumerate(ga.population.individuals):
        if ind.fitness is None:
            ind.fitness = evaluate_genome(ind.genes)
            if (i + 1) % max(1, POP_SIZE // 4) == 0:
                print(f'  evaluated {i + 1}/{POP_SIZE} '
                      f'(gen wall: {time.time() - gen_t:.0f}s)')

    fitnesses = [g.fitness for g in ga.population.individuals
                 if g.fitness is not None]
    best = max(fitnesses) if fitnesses else -999.0
    fstd = float(np.std(fitnesses)) if len(fitnesses) > 1 else 0.0
    best_history.append(best)
    sigma_history.append(coordinator.mutation_sigma)

    # Feed the agent coordinator (even in warm-start) so its adjustment_log
    # is primed with warm-start feedback.
    coordinator.adjust(
        retrain_idx=gen,
        best_fitness=best,
        fitness_std=fstd,
        market_vol_percentile=None,
    )

    print(f'  gen {gen + 1}: best={best:.2f} mean_std={fstd:.2f} '
          f'sigma→{coordinator.mutation_sigma:.3f} '
          f'k→{coordinator.tournament_k} '
          f'elapsed={time.time() - gen_t:.0f}s')

    # Advance one generation (standard GA evolve; not the rolling retrain)
    ga.population.evolve(
        elitism=ga.elitism,
        crossover_rate=coordinator.crossover_rate,
        mutation_rate=DEFAULT_CONFIG['ga']['mutation_rate'],
        mutation_sigma=coordinator.mutation_sigma,
        tournament_k=coordinator.tournament_k,
    )
    # Re-index outcome buffers for new individuals
    from collections import deque
    new_buffers = {}
    for g in ga.population.individuals:
        if g.id in ga._outcomes:
            new_buffers[g.id] = ga._outcomes[g.id]
        else:
            new_buffers[g.id] = deque(maxlen=ga.rolling_window_cycles)
    ga._outcomes = new_buffers
    ga.generation += 1

# Re-evaluate final population so persisted fitnesses are accurate
print('\nFinal evaluation of warm-started population ...')
for ind in ga.population.individuals:
    if ind.fitness is None:
        ind.fitness = evaluate_genome(ind.genes)


# -----------------------------------------------------------------------
# 5. Save state
# -----------------------------------------------------------------------

print(f'\nSaving to {PIPELINE_MODELS} ...')
pipeline = CGAAgentPilot()
pipeline._ga = ga
pipeline._gene_bounds = gene_bounds
pipeline.coordinator = coordinator
_n_30m = len(trading_1m) // 30 if trading_1m is not None else 0
pipeline._candle_count = _n_30m
pipeline._last_retrain_candle = _n_30m  # next retrain 30d after this
pipeline._retrain_count = MAX_GENS
pipeline.save_state(str(PIPELINE_MODELS))

# Also mirror into phase5/results for archival
(RESULTS_DIR / 'models').mkdir(exist_ok=True)
pipeline.save_state(str(RESULTS_DIR / 'models'))

summary = {
    'mode': 'smoke' if SMOKE else 'full',
    'train_start': WARMSTART_START,
    'train_end': WARMSTART_END,
    'generations': MAX_GENS,
    'population_size': POP_SIZE,
    'wall_seconds': round(time.time() - t0, 1),
    'best_fitness_history': [round(x, 3) for x in best_history],
    'sigma_history': [round(x, 4) for x in sigma_history],
    'final_best_fitness': round(ga.best_fitness(), 3),
    'final_mutation_sigma': round(coordinator.mutation_sigma, 4),
    'final_crossover_rate': round(coordinator.crossover_rate, 4),
    'final_tournament_k': coordinator.tournament_k,
    'n_adjustments': len(coordinator.adjustment_log),
}
with open(RESULTS_DIR / '54_cga_agent_train.json', 'w') as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))


# -----------------------------------------------------------------------
# 6. Plot best fitness + mutation sigma
# -----------------------------------------------------------------------

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
xs = list(range(1, len(best_history) + 1))
ax1.plot(xs, best_history, marker='o', color='tab:blue')
ax1.set_ylabel('Best Fitness')
ax1.set_title(f'CGAAgentPilot warm-start ({"smoke" if SMOKE else "full"})')
ax1.grid(True, alpha=0.3)

ax2.plot(xs, sigma_history, marker='s', color='tab:orange')
ax2.set_ylabel('Mutation σ')
ax2.set_xlabel('Generation')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plot_path = PLOTS_DIR / '54_cga_agent_train.png'
plt.savefig(plot_path, dpi=120)
plt.close()
print(f'Plot saved: {plot_path}')
print('Done.')
