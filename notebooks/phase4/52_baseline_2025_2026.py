"""
52 — Baseline Backtest 2025-01-01 to 2026-04-15 (no pipeline, no cost model)

Runs the default Martingale strategy (preset=original) with NO pipeline
on EUR-USD 5m from 2025-01-01 to 2026-04-15. Cost model OFF.
Collects full stats for paper comparison.
"""

import sys
import os
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from qengine.research.backtest import backtest
from qengine.research.candles import get_candles
import qengine.helpers as jh

RESULTS_DIR = Path(__file__).resolve().parent / 'results'
RESULTS_DIR.mkdir(exist_ok=True)

TEST_START = '2025-01-01'
TEST_END = '2026-04-08'
EXCHANGE = 'OANDA'
SYMBOL = 'EUR-USD'
TIMEFRAME = '5m'
STARTING_BALANCE = 10_000
WARMUP = 500


def main():
    print(f"\n{'#'*70}")
    print(f"# Baseline Backtest: {TEST_START} -> {TEST_END}")
    print(f"# Strategy: Martingale (preset=original)  Cost model: OFF")
    print(f"# TF: {TIMEFRAME}  Symbol: {SYMBOL}  Balance: ${STARTING_BALANCE:,}")
    print(f"{'#'*70}")

    # Load candles
    print(f"\nLoading 1m candles...")
    start_ts = jh.date_to_timestamp(TEST_START)
    end_ts = jh.date_to_timestamp(TEST_END)
    warmup_1m, trading_1m = get_candles(
        exchange=EXCHANGE, symbol=SYMBOL, timeframe='1m',
        start_date_timestamp=start_ts, finish_date_timestamp=end_ts,
        warmup_candles_num=WARMUP,
    )
    print(f"  Trading: {len(trading_1m):,} candles   Warmup: {len(warmup_1m) if hasattr(warmup_1m, '__len__') else 0}")

    key = f'{EXCHANGE}-{SYMBOL}'
    candles_dict = {key: {'exchange': EXCHANGE, 'symbol': SYMBOL, 'candles': trading_1m}}
    warmup_dict = None

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

    # Run baseline (no pipeline)
    print(f"\nRunning baseline backtest...")
    t0 = time.time()
    result = backtest(
        config=config, routes=routes, data_routes=[],
        candles=candles_dict, warmup_candles=warmup_dict,
        hyperparameters={'preset': 'original'},
        pipeline_configs=None,
        generate_equity_curve=True,
        generate_logs=False,
        cost_model=False,
    )
    elapsed = time.time() - t0

    metrics = result.get('metrics', {}) or {}
    print(f"\n{'='*70}")
    print(f"RESULTS: Baseline (no pipeline)")
    print(f"{'='*70}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"  Total trades: {metrics.get('total', metrics.get('total_closed_trades', 0))}")
    print(f"  Win rate: {metrics.get('win_rate', 0)*100:.1f}%")
    print(f"  Profit factor: {metrics.get('profit_factor', 0):.4f}")
    print(f"  Net P&L: ${metrics.get('net_profit', 0):.2f} ({metrics.get('net_profit_percentage', 0):.2f}%)")
    print(f"  Max drawdown: {metrics.get('max_drawdown', 0):.2f}%")
    print(f"  Annual return: {metrics.get('annual_return', 0):.2f}%")
    print(f"  Sharpe: {metrics.get('sharpe_ratio', 0):.2f}")

    # Save results
    output = {
        'test_period': {'start': TEST_START, 'end': TEST_END},
        'config': {
            'strategy': 'Martingale',
            'preset': 'original',
            'symbol': SYMBOL,
            'timeframe': TIMEFRAME,
            'cost_model': False,
            'starting_balance': STARTING_BALANCE,
        },
        'elapsed_s': round(elapsed, 2),
        'metrics': metrics,
    }

    out_path = RESULTS_DIR / '52_baseline_2025_2026.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved to: {out_path}")


if __name__ == '__main__':
    main()
