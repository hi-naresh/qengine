"""
Parallel backtest runner.

Runs multiple independent backtests across CPU cores. Each backtest is
fully isolated (separate process) so no state leaks between them.
Useful for:
  - Parameter sweeps (test many configs simultaneously)
  - Walk-forward windows (each window is independent)
  - Pipeline comparison (baseline vs pipeline in parallel)
  - Monte Carlo runs

IMPORTANT: No future data leaks. Each process gets its own copy of candle
data and runs a complete sequential backtest. Parallelism is across RUNS,
never within a single run's candle loop.
"""

import os
import time
from typing import List, Dict, Any, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count


def _run_single_backtest(args: dict) -> dict:
    """Worker function for a single backtest (runs in separate process)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(args['project_root']).resolve()))
    os.chdir(str(Path(args['project_root']).resolve()))

    from qengine.research.backtest import backtest
    from qengine.research.candles import get_candles
    import qengine.helpers as jh

    label = args.get('label', 'unnamed')
    t0 = time.time()

    try:
        # Load candles (each process loads independently - no shared state)
        start_ts = jh.date_to_timestamp(args['start_date'])
        end_ts = jh.date_to_timestamp(args['end_date'])
        warmup_1m, trading_1m = get_candles(
            exchange=args['exchange'],
            symbol=args['symbol'],
            timeframe='1m',
            start_date_timestamp=start_ts,
            finish_date_timestamp=end_ts,
            warmup_candles_num=args.get('warmup', 500),
        )

        key = f"{args['exchange']}-{args['symbol']}"
        candles_dict = {key: {'exchange': args['exchange'], 'symbol': args['symbol'], 'candles': trading_1m}}

        config = {
            'starting_balance': args.get('starting_balance', 10_000),
            'fee': 0,
            'type': 'cfd',
            'exchange': args['exchange'],
            'warm_up_candles': args.get('warmup', 500),
        }
        routes = [{
            'exchange': args['exchange'],
            'symbol': args['symbol'],
            'timeframe': args.get('timeframe', '5m'),
            'strategy': args.get('strategy', 'Martingale'),
        }]

        result = backtest(
            config=config, routes=routes, data_routes=[],
            candles=candles_dict, warmup_candles=None,
            hyperparameters=args.get('hyperparameters', {}),
            pipeline_configs=args.get('pipeline_configs'),
            generate_equity_curve=args.get('equity_curve', False),
            generate_logs=False,
            cost_model=args.get('cost_model', True),
        )

        metrics = result.get('metrics', {})
        elapsed = time.time() - t0

        return {
            'label': label,
            'status': 'ok',
            'elapsed': round(elapsed, 2),
            'metrics': metrics,
            'candles': len(trading_1m),
        }

    except Exception as e:
        import traceback
        return {
            'label': label,
            'status': 'error',
            'error': str(e),
            'traceback': traceback.format_exc(),
            'elapsed': round(time.time() - t0, 2),
        }


def run_parallel(
    runs: List[Dict[str, Any]],
    max_workers: Optional[int] = None,
    project_root: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run multiple backtests in parallel across CPU cores.

    Args:
        runs: List of run configs, each with:
            - label: str (identifier for this run)
            - exchange: str (e.g. 'OANDA')
            - symbol: str (e.g. 'EUR-USD')
            - start_date: str (e.g. '2025-01-01')
            - end_date: str (e.g. '2026-01-01')
            - timeframe: str (default '5m')
            - strategy: str (default 'Martingale')
            - hyperparameters: dict (strategy HP overrides)
            - pipeline_configs: list or None
            - cost_model: bool (default True)
            - starting_balance: float (default 10000)
            - warmup: int (default 500)
        max_workers: Number of parallel processes (default: CPU count - 1)
        project_root: Path to project root (default: cwd)

    Returns:
        List of result dicts with 'label', 'status', 'metrics', 'elapsed'
    """
    if max_workers is None:
        max_workers = max(1, cpu_count() - 1)

    if project_root is None:
        project_root = os.getcwd()

    # Inject project_root into each run config
    for run in runs:
        run['project_root'] = project_root

    results = []
    total = len(runs)
    print(f'Running {total} backtests across {max_workers} cores...')
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_single_backtest, run): run for run in runs}

        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            status = result['status']
            label = result['label']
            elapsed = result['elapsed']
            if status == 'ok':
                pf = result['metrics'].get('profit_factor', 0)
                net = result['metrics'].get('net_profit_percentage', 0)
                print(f'  [{i}/{total}] {label}: PF={pf:.4f}, Net={net:+.2f}% ({elapsed:.1f}s)')
            else:
                print(f'  [{i}/{total}] {label}: ERROR - {result.get("error", "?")} ({elapsed:.1f}s)')

    total_time = time.time() - t0
    print(f'Done. Total: {total_time:.1f}s (vs sequential estimate: {sum(r["elapsed"] for r in results):.1f}s)')
    print(f'Speedup: {sum(r["elapsed"] for r in results) / total_time:.1f}x')

    # Sort by original order
    label_order = {run['label']: i for i, run in enumerate(runs)}
    results.sort(key=lambda r: label_order.get(r['label'], 999))

    return results
