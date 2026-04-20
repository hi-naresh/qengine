"""
48 — Real Engine Backtest with IslandPilot Pipeline

Runs the ACTUAL qengine backtest engine (not the toy simulator from scripts 43/44)
with IslandPilot pipeline attached to the Martingale strategy.

This produces the authoritative numbers for the paper.
"""

import sys
import os
import json
import numpy as np
from pathlib import Path

# Project root setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from qengine.research.backtest import backtest
from qengine.research.candles import get_candles
import qengine.helpers as jh

RESULTS_DIR = Path(__file__).resolve().parent / 'results'
RESULTS_DIR.mkdir(exist_ok=True)


def load_1m_candles(exchange, symbol, start_date, end_date, warmup_num=500):
    """Load 1m candles from DB. Returns (warmup_1m, trading_1m)."""
    start_ts = jh.date_to_timestamp(start_date)
    end_ts = jh.date_to_timestamp(end_date)

    warmup, trading = get_candles(
        exchange=exchange,
        symbol=symbol,
        timeframe='1m',
        start_date_timestamp=start_ts,
        finish_date_timestamp=end_ts,
        warmup_candles_num=warmup_num,
    )
    return warmup, trading


def run_backtest(start_date, end_date, pipeline_configs=None, hp_overrides=None,
                 starting_balance=10000, label=''):
    """Run a single backtest and return the result dict."""
    exchange = 'OANDA'
    symbol = 'EUR-USD'
    timeframe = '5m'

    warmup_1m, trading_1m = load_1m_candles(exchange, symbol, start_date, end_date, warmup_num=500)

    key = f'{exchange}-{symbol}'

    # Prepare candles dict (must be 1m)
    candles = {
        key: {
            'exchange': exchange,
            'symbol': symbol,
            'candles': trading_1m,
        }
    }

    # Warmup candles
    warmup_dict = None
    if warmup_1m.ndim == 2 and len(warmup_1m) > 0:
        warmup_dict = {
            key: {
                'exchange': exchange,
                'symbol': symbol,
                'candles': warmup_1m,
            }
        }

    config = {
        'starting_balance': starting_balance,
        'fee': 0,        # CFD spread is handled by the engine
        'type': 'cfd',
        'exchange': exchange,
        'warm_up_candles': 500,
    }

    routes = [
        {
            'exchange': exchange,
            'symbol': symbol,
            'timeframe': timeframe,
            'strategy': 'Martingale',
        }
    ]

    print(f"\n{'='*60}")
    print(f"Running: {label or 'backtest'}")
    print(f"Period: {start_date} to {end_date}")
    print(f"Pipeline: {'IslandPilot' if pipeline_configs else 'None'}")
    print(f"Balance: ${starting_balance:,}")
    print(f"{'='*60}")

    result = backtest(
        config=config,
        routes=routes,
        data_routes=[],
        candles=candles,
        warmup_candles=warmup_dict,
        hyperparameters=hp_overrides,
        pipeline_configs=pipeline_configs,
        generate_equity_curve=True,
        generate_logs=True,
    )

    # Print metrics
    m = result.get('metrics', {})
    print(f"\n--- Metrics ---")
    for key in ['total', 'win_rate', 'profit_factor', 'net_profit_percentage',
                'net_profit', 'max_drawdown', 'annual_return', 'sharpe_ratio',
                'calmar_ratio', 'sortino_ratio', 'winning_streak', 'losing_streak',
                'largest_winning_trade', 'largest_losing_trade', 'total_closed_trades',
                'num_winning_trades', 'num_losing_trades']:
        if key in m:
            val = m[key]
            if isinstance(val, float):
                print(f"  {key}: {val:.4f}")
            else:
                print(f"  {key}: {val}")

    # Print pipeline stats
    ps = result.get('pipeline_stats')
    if ps:
        print(f"\n--- Pipeline Stats ---")
        for route_key, stats in ps.items():
            print(f"  Route: {route_key}")
            for k, v in stats.items():
                if k in ('cycle_hp_log', '_ui', 'danger_scores', 'cycle_outcomes'):
                    print(f"    {k}: [{len(v) if isinstance(v, list) else type(v).__name__}]")
                elif isinstance(v, dict):
                    print(f"    {k}:")
                    for kk, vv in v.items():
                        print(f"      {kk}: {vv}")
                else:
                    print(f"    {k}: {v}")

    return result


def main():
    # Test period: 2025 H2 (same as research scripts)
    test_start = '2025-07-01'
    test_end = '2025-12-30'

    # --- Run 1: With IslandPilot pipeline ---
    pipeline_result = run_backtest(
        test_start, test_end,
        pipeline_configs=[{'name': 'IslandPilot'}],
        label='WITH IslandPilot Pipeline',
    )

    # --- Run 2: Without pipeline (baseline) ---
    baseline_result = run_backtest(
        test_start, test_end,
        pipeline_configs=None,
        label='WITHOUT Pipeline (Baseline)',
    )

    # --- Comparison ---
    pm = pipeline_result.get('metrics', {})
    bm = baseline_result.get('metrics', {})

    print(f"\n{'='*60}")
    print(f"COMPARISON: Pipeline vs Baseline")
    print(f"{'='*60}")
    print(f"{'Metric':<30} {'Pipeline':>12} {'Baseline':>12} {'Delta':>12}")
    print(f"{'-'*66}")
    for key in ['total_closed_trades', 'win_rate', 'profit_factor', 'net_profit_percentage',
                'net_profit', 'max_drawdown', 'sharpe_ratio', 'calmar_ratio', 'sortino_ratio']:
        pv = pm.get(key, 0)
        bv = bm.get(key, 0)
        if isinstance(pv, float):
            delta = pv - bv
            print(f"{key:<30} {pv:>12.4f} {bv:>12.4f} {delta:>+12.4f}")
        else:
            print(f"{key:<30} {str(pv):>12} {str(bv):>12}")

    # Save results
    save_data = {
        'pipeline': {
            'metrics': pm,
            'pipeline_stats': pipeline_result.get('pipeline_stats'),
            'n_trades': len(pipeline_result.get('trades', [])),
        },
        'baseline': {
            'metrics': bm,
            'n_trades': len(baseline_result.get('trades', [])),
        },
        'test_period': {'start': test_start, 'end': test_end},
    }

    out_path = RESULTS_DIR / '48_real_backtest.json'
    with open(out_path, 'w') as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == '__main__':
    main()
