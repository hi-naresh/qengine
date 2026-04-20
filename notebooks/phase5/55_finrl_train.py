"""
55 — FinRLPilot offline training.

Trains the FinRLPilot policy over EUR-USD 30m data from 2022-01-01 to
2023-12-31. The policy selects among 4 Martingale parameter presets
(conservative / moderate / aggressive / tight-TP) once per cycle.

Training approach (offline RL / warm-start):

1. Seed a RANDOM-policy rollout: run a real qengine backtest with FinRLPilot in
   `train` mode and epsilon forced high. This collects (state, action, reward)
   tuples into the replay buffer.
2. Issue `policy.update()` on the collected buffer to produce an initial policy
   consistent with the offline data.
3. Optionally repeat with smaller epsilon for a few passes to fine-tune.

We deliberately AVOID building a full gym `Env` subclass — the qengine backtest
runner is a much cleaner driver, and the FinRLPilot itself already exposes the
gym-like hooks we need (on_before / on_cycle_end).

Output:
  - plots/55_reward_curve.png — reward per cycle during training
  - pipelines/_shared/FinRLPilot/models/policy_tabular.npz (or .pt / .zip)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Ensure we import from the project root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import qengine.helpers as jh
from qengine.research.backtest import backtest
from qengine.research.candles import get_candles

from pipelines._shared.FinRLPilot import FinRLPilot
from pipelines._shared.FinRLPilot.ppo_agent import BACKEND

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EXCHANGE = 'OANDA'
SYMBOL = 'EUR-USD'
TIMEFRAME = '30m'
ROUTE_TIMEFRAME = '30m'     # strategy route tf
START_DATE = os.environ.get('FINRL_START', '2022-01-01')
END_DATE = os.environ.get('FINRL_END', '2023-12-31')

# Smoke-test knobs. Keep these short for a first run; increase for real training.
N_COLLECT_EPISODES = int(os.environ.get('FINRL_EPISODES', '2'))
N_FINETUNE_PASSES = int(os.environ.get('FINRL_PASSES', '3'))

OUT_PLOT = Path(__file__).parent / 'plots' / '55_reward_curve.png'
OUT_JSON = Path(__file__).parent / 'results' / '55_finrl_train.json'
MODELS_DIR = ROOT / 'pipelines' / '_shared' / 'FinRLPilot' / 'models'


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_training_candles():
    print(f'Loading {SYMBOL} 1m candles {START_DATE} → {END_DATE} ...')
    warmup, trading = get_candles(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        timeframe='1m',
        start_date_timestamp=jh.date_to_timestamp(START_DATE),
        finish_date_timestamp=jh.date_to_timestamp(END_DATE),
        warmup_candles_num=10000,
    )
    warmup_is_valid = isinstance(warmup, np.ndarray) and warmup.ndim == 2 and len(warmup) > 0
    print(f'  trading candles: {len(trading)}, warmup present: {warmup_is_valid}')
    return warmup if warmup_is_valid else None, trading


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def run_collection_episode(pipeline: FinRLPilot, warmup, trading, episode_idx: int) -> dict:
    """Run one full backtest with FinRLPilot in train mode.

    Returns a metrics dict with reward stats.
    """
    key = f'{EXCHANGE}-{SYMBOL}'
    candles = {key: {'exchange': EXCHANGE, 'symbol': SYMBOL, 'candles': trading}}
    warmup_dict = (
        {key: {'exchange': EXCHANGE, 'symbol': SYMBOL, 'candles': warmup}}
        if warmup is not None else None
    )

    # Pipeline config — train mode, moderate epsilon for exploration.
    # NOTE: the qengine backtest re-instantiates pipelines from pipeline_configs,
    # so we can't inject our in-memory `pipeline` object directly. Instead we
    # pass the same config and merge the resulting policy into `pipeline` after
    # the backtest finishes.
    pipeline_cfg = [{
        'name': 'FinRLPilot',
        'mode': 'train',
        'update_every_cycles': 16,
        'policy': {
            'lr': 0.2,
            'gamma': 0.99,
            'entropy_coef': 0.3 if episode_idx == 0 else 0.15,
        },
    }]

    print(f'\n[episode {episode_idx+1}] backtest running ...')
    t0 = time.time()
    try:
        result = backtest(
            config={
                'starting_balance': 10000,
                'fee': 0,
                'type': 'cfd',
                'exchange': EXCHANGE,
                'warm_up_candles': 10000,
            },
            routes=[{
                'exchange': EXCHANGE,
                'symbol': SYMBOL,
                'timeframe': ROUTE_TIMEFRAME,
                'strategy': 'Martingale',
            }],
            data_routes=[],
            candles=candles,
            warmup_candles=warmup_dict,
            hyperparameters={key: {'preset': 'custom'}},
            pipeline_configs=pipeline_cfg,
            generate_equity_curve=False,
            generate_logs=False,
        )
    except Exception as e:
        print(f'  backtest failed: {e}')
        return {'episode': episode_idx, 'error': str(e)}

    elapsed = time.time() - t0
    metrics = result.get('metrics', {}) or {}
    # pipeline_stats is keyed by route ("{EXCHANGE}-{SYMBOL}") and returns the
    # flat stats dict for the single pipeline on that route.
    pstats = result.get('pipeline_stats', {}) or {}
    finrl_stats = pstats.get(key, {}) if isinstance(pstats, dict) else {}
    # Track reward series across episodes so we can plot a real curve
    reward_ts = finrl_stats.get('reward_timeseries') or []
    # Full transitions (real state vectors) — used to replay into the final
    # policy during Stage 2. Train-mode pipelines export these.
    transitions = finrl_stats.get('transitions') or []

    print(f'  done in {elapsed:.1f}s; sessions={metrics.get("total_sessions", "?")} '
          f'net_pct={metrics.get("net_profit_percentage", 0):.3f}')

    # Copy learned state from the in-backtest pipeline (if returned) back into
    # the persistent `pipeline` instance. Since pipeline_configs spins up a new
    # instance, we have to rely on the reward_history/action_counts in stats.
    return {
        'episode': episode_idx,
        'elapsed_s': round(elapsed, 2),
        'metrics': {
            k: metrics.get(k)
            for k in (
                'total_sessions', 'net_profit', 'net_profit_percentage',
                'profit_factor', 'max_drawdown', 'win_rate', 'bust_rate',
            )
        },
        'finrl_stats': {
            k: finrl_stats.get(k)
            for k in (
                'backend', 'cycle_count', 'mean_reward', 'mean_reward_100',
                'action_counts_named', 'total_updates',
            )
        },
        'reward_timeseries': reward_ts,
        'transitions': transitions,
    }


def main():
    os.makedirs(OUT_PLOT.parent, exist_ok=True)
    os.makedirs(OUT_JSON.parent, exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)

    print(f'Policy backend detected: {BACKEND}')

    warmup, trading = load_training_candles()

    # Because `pipeline_configs` instantiates pipelines inside the backtest, we
    # need an alternative route for collecting experience: build our own driver
    # that runs the backtest and then immediately instantiates a pipeline with
    # the SAME config for the post-hoc update. For the smoke test we:
    #   - run N backtests in train mode to see the pipeline log rewards
    #   - construct a FINAL in-memory pipeline and replay all collected rewards
    #     to fit its policy
    # This mirrors offline RL: collect → replay → fit.

    # Stage 1 — collection backtests
    collection_results = []
    for i in range(N_COLLECT_EPISODES):
        r = run_collection_episode(None, warmup, trading, i)
        collection_results.append(r)

    # Stage 2 — replay + fit on an in-memory pipeline using REAL states.
    # Each collection episode exports `transitions` = list of
    # {ts, state, action, reward, pnl} dicts with real FeaturePool state
    # vectors captured during the ephemeral in-backtest pipeline run. We
    # replay them into a fresh pipeline's policy and call update().
    print('\n[stage 2] fitting final policy on collected transitions...')
    final_pipeline = FinRLPilot({
        'mode': 'train',
        'policy': {'lr': 0.1, 'gamma': 0.99, 'entropy_coef': 0.05},
    })
    reward_samples: list = []
    n_transitions = 0
    for ep in collection_results:
        for tr in ep.get('transitions') or []:
            state = np.asarray(tr.get('state', []), dtype=np.float64)
            if state.size == 0:
                continue
            action = int(tr['action'])
            reward = float(tr.get('reward', tr.get('pnl', 0.0)))
            final_pipeline.policy.record(state, action, reward, done=True)
            reward_samples.append(reward)
            n_transitions += 1
    print(f'  replayed {n_transitions} real (state, action, reward) transitions')

    # Run several fine-tune passes
    update_results = []
    for i in range(N_FINETUNE_PASSES):
        res = final_pipeline.policy.update()
        update_results.append(res)
        print(f'  pass {i+1}/{N_FINETUNE_PASSES}: {res}')

    # Stage 3 — save weights
    out_path = MODELS_DIR / (
        'policy.zip' if BACKEND == 'sb3'
        else 'policy.pt' if BACKEND == 'torch'
        else 'policy_tabular.npz'
    )
    print(f'\nSaving policy → {out_path}')
    final_pipeline.policy.save(str(out_path))

    # Stage 4 — plot reward curve
    print(f'Plotting reward curve → {OUT_PLOT}')
    plt.figure(figsize=(10, 4))
    if reward_samples:
        plt.plot(reward_samples, lw=0.8, alpha=0.7, label='per-sample reward')
        # Rolling mean
        ws = max(1, len(reward_samples) // 20)
        if len(reward_samples) > ws:
            arr = np.array(reward_samples, dtype=float)
            rolling = np.convolve(arr, np.ones(ws) / ws, mode='valid')
            plt.plot(np.arange(len(rolling)) + ws - 1, rolling,
                     color='red', lw=1.6, label=f'rolling mean (w={ws})')
    else:
        plt.text(0.5, 0.5, 'No reward samples collected',
                 ha='center', va='center', transform=plt.gca().transAxes)
    plt.xlabel('Training sample')
    plt.ylabel('Reward')
    plt.title(f'FinRLPilot training reward curve (backend: {BACKEND})')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_PLOT, dpi=100)
    plt.close()

    # Stage 5 — dump metrics
    out = {
        'backend': BACKEND,
        'start_date': START_DATE,
        'end_date': END_DATE,
        'timeframe': ROUTE_TIMEFRAME,
        'n_collect_episodes': N_COLLECT_EPISODES,
        'n_finetune_passes': N_FINETUNE_PASSES,
        'episodes': collection_results,
        'updates': update_results,
        'final_policy_stats': final_pipeline.policy.stats(),
        'n_reward_samples': len(reward_samples),
    }
    with open(OUT_JSON, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print(f'Saved metrics → {OUT_JSON}')
    print('\nDone.')


if __name__ == '__main__':
    main()
