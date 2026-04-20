"""
51 — Pipeline Comparison on Real Engine (cost model OFF)

Compares baseline Martingale (preset=original, no pipeline) against:
  1. IslandPilot
  2. ARIA
  3. GridPilot
  4. GTSBotPilot

All runs on EUR-USD 5m, 2026-01-01 to 2026-04-15, cost_model=False.
Produces metrics + pipeline_stats per run for paper comparison.
"""

import sys
import os
import json
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from qengine.research.backtest import backtest
from qengine.research.candles import get_candles
import qengine.helpers as jh

RESULTS_DIR = Path(__file__).resolve().parent / 'results'
RESULTS_DIR.mkdir(exist_ok=True)

TEST_START = '2026-01-01'
TEST_END = '2026-04-08'  # last available candle: 2026-04-08 16:59 UTC
EXCHANGE = 'OANDA'
SYMBOL = 'EUR-USD'
TIMEFRAME = '5m'
STARTING_BALANCE = 10_000
WARMUP = 500

# Martingale hyperparameters — force 'original' preset
HP_OVERRIDES = {'preset': 'original'}

RUNS = [
    {'label': 'Baseline',    'pipeline_configs': None},
    {'label': 'IslandPilot', 'pipeline_configs': [{'name': 'IslandPilot'}]},
    {'label': 'ARIA',        'pipeline_configs': [{'name': 'ARIA'}]},
    {'label': 'GridPilot',   'pipeline_configs': [{'name': 'GridPilot'}]},
    {'label': 'GTSBotPilot', 'pipeline_configs': [{'name': 'GTSBotPilot'}]},
]

SUMMARY_METRICS = [
    'total', 'total_closed_trades', 'num_winning_trades', 'num_losing_trades',
    'win_rate', 'profit_factor', 'net_profit', 'net_profit_percentage',
    'max_drawdown', 'annual_return', 'sharpe_ratio', 'calmar_ratio',
    'sortino_ratio', 'winning_streak', 'losing_streak',
    'largest_winning_trade', 'largest_losing_trade',
    'average_winning_trade', 'average_losing_trade',
    'total_winning_trades', 'total_losing_trades',
]


def load_1m_candles():
    start_ts = jh.date_to_timestamp(TEST_START)
    end_ts = jh.date_to_timestamp(TEST_END)
    return get_candles(
        exchange=EXCHANGE, symbol=SYMBOL, timeframe='1m',
        start_date_timestamp=start_ts, finish_date_timestamp=end_ts,
        warmup_candles_num=WARMUP,
    )


def run_one(label, pipeline_configs, candles_dict, warmup_dict):
    print(f"\n{'='*70}\nRunning: {label}\n{'='*70}")
    t0 = time.time()

    config = {
        'starting_balance': STARTING_BALANCE,
        'fee': 0,
        'type': 'cfd',
        'exchange': EXCHANGE,
        'warm_up_candles': WARMUP,
    }
    routes = [{
        'exchange': EXCHANGE, 'symbol': SYMBOL,
        'timeframe': TIMEFRAME, 'strategy': 'Martingale',
    }]

    try:
        result = backtest(
            config=config, routes=routes, data_routes=[],
            candles=candles_dict, warmup_candles=warmup_dict,
            hyperparameters=HP_OVERRIDES,
            pipeline_configs=pipeline_configs,
            generate_equity_curve=True,
            generate_logs=False,
            cost_model=False,  # cost model OFF per user request
        )
    except Exception as e:
        print(f"  FAILED: {e}")
        traceback.print_exc()
        return {'label': label, 'error': str(e), 'elapsed_s': time.time() - t0}

    elapsed = time.time() - t0
    metrics = result.get('metrics', {}) or {}
    ps = result.get('pipeline_stats') or {}

    # Extract a compact summary from pipeline_stats (strip large arrays)
    pipe_summary = {}
    for route_key, stats in ps.items():
        compact = {}
        for k, v in stats.items():
            if k in ('cycle_hp_log', '_ui', '_ui_full', 'danger_scores',
                     'cycle_outcomes', 'gate_decisions', 'abort_decisions',
                     'consultation_log', 'confidence_series', 'cycle_features'):
                compact[f'{k}_count'] = len(v) if isinstance(v, list) else None
            elif isinstance(v, (dict, list, str, int, float, bool)) or v is None:
                try:
                    json.dumps(v)  # test serializability
                    compact[k] = v
                except (TypeError, ValueError):
                    compact[k] = str(v)[:200]
            else:
                compact[k] = str(v)[:200]
        pipe_summary[route_key] = compact

    print(f"  Elapsed: {elapsed:.1f}s  Trades: {metrics.get('total_closed_trades', 0)}")
    print(f"  Net P&L: ${metrics.get('net_profit', 0):.2f}  "
          f"({metrics.get('net_profit_percentage', 0):.2f}%)")
    print(f"  Win rate: {metrics.get('win_rate', 0)*100:.1f}%  "
          f"PF: {metrics.get('profit_factor', 0):.3f}  "
          f"Max DD: {metrics.get('max_drawdown', 0):.2f}%  "
          f"Sharpe: {metrics.get('sharpe_ratio', 0):.2f}")

    return {
        'label': label,
        'pipeline_configs': pipeline_configs,
        'elapsed_s': round(elapsed, 2),
        'metrics': {k: metrics.get(k) for k in SUMMARY_METRICS if k in metrics},
        'pipeline_stats': pipe_summary,
        'n_trades': len(result.get('trades', []) or []),
    }


def main():
    print(f"\n{'#'*70}")
    print(f"# Pipeline Comparison: {TEST_START} → {TEST_END}")
    print(f"# Strategy: Martingale (preset=original)  Cost model: OFF")
    print(f"# TF: {TIMEFRAME}  Symbol: {SYMBOL}  Balance: ${STARTING_BALANCE:,}")
    print(f"{'#'*70}")

    # Load candles ONCE and reuse across runs
    print(f"\nLoading 1m candles…")
    warmup_1m, trading_1m = load_1m_candles()
    print(f"  Trading: {len(trading_1m):,} candles   Warmup: "
          f"{len(warmup_1m) if hasattr(warmup_1m, '__len__') else 0}")

    key = f'{EXCHANGE}-{SYMBOL}'
    candles_dict = {key: {'exchange': EXCHANGE, 'symbol': SYMBOL, 'candles': trading_1m}}
    warmup_dict = None
    if hasattr(warmup_1m, 'ndim') and warmup_1m.ndim == 2 and len(warmup_1m) > 0:
        warmup_dict = {key: {'exchange': EXCHANGE, 'symbol': SYMBOL, 'candles': warmup_1m}}

    # Run all
    all_results = []
    for run in RUNS:
        r = run_one(run['label'], run['pipeline_configs'], candles_dict, warmup_dict)
        all_results.append(r)
        # Persist incrementally so partial failures don't lose work
        out = {
            'test_period': {'start': TEST_START, 'end': TEST_END},
            'config': {
                'strategy': 'Martingale', 'preset': 'original',
                'symbol': SYMBOL, 'timeframe': TIMEFRAME,
                'cost_model': False, 'starting_balance': STARTING_BALANCE,
            },
            'runs': all_results,
        }
        out_path = RESULTS_DIR / '51_pipeline_comparison.json'
        with open(out_path, 'w') as f:
            json.dump(out, f, indent=2, default=str)

    # Comparison table
    print(f"\n\n{'='*70}\nCOMPARISON TABLE\n{'='*70}")
    cols = ['total_closed_trades', 'win_rate', 'profit_factor',
            'net_profit', 'net_profit_percentage', 'max_drawdown',
            'sharpe_ratio', 'sortino_ratio', 'calmar_ratio',
            'losing_streak']
    header = f"{'Metric':<25}" + ''.join(f"{r['label']:>13}" for r in all_results)
    print(header)
    print('-' * len(header))
    for c in cols:
        row = f"{c:<25}"
        for r in all_results:
            v = r.get('metrics', {}).get(c, 0) if 'error' not in r else None
            if v is None:
                row += f"{'—':>13}"
            elif isinstance(v, float):
                row += f"{v:>13.4f}"
            else:
                row += f"{str(v):>13}"
        print(row)

    print(f"\nSaved to: {out_path}")


if __name__ == '__main__':
    main()
