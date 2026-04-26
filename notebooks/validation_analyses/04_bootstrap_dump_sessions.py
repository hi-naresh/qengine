"""Run Baseline and IslandPilot on the canonical 15.5-month OOS window
(2025-01-02 to 2026-04-19) and dump per-session P&L records to disk so a
block-bootstrap CI analysis can be run in 04_bootstrap_significance.py.

Output files (relative to repo root):
  notebooks/validation_analyses/results/04_baseline_sessions.csv
  notebooks/validation_analyses/results/04_islandpilot_sessions.csv

Each CSV row is one session with columns:
  session_id, opened_at_ms, closed_at_ms, outcome, levels, n_trades, pnl_usd
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / 'notebooks' / 'validation_analyses' / 'results'
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _to_ms(s: str) -> int:
    return int((datetime.strptime(s, '%Y-%m-%d') - datetime(1970, 1, 1)).total_seconds() * 1000)


def _session_pnl(s: dict) -> float:
    for k in ('total_pnl', 'session_pnl', 'pnl', 'net_pnl'):
        v = s.get(k)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        return f
    trades = s.get('trades') or []
    total = 0.0
    for t in trades:
        try:
            total += float(t.get('pnl', 0) or 0)
        except (TypeError, ValueError):
            pass
    return total


def _dump_sessions(sessions: list, out_path: Path) -> int:
    proper = [s for s in sessions if isinstance(s.get('session'), int)]
    proper.sort(key=lambda s: s.get('opened_at', 0) or 0)
    with open(out_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['session_id', 'opened_at_ms', 'closed_at_ms',
                    'outcome', 'levels', 'n_trades', 'pnl_usd'])
        for s in proper:
            w.writerow([
                s.get('session', ''),
                s.get('opened_at', ''),
                s.get('closed_at', ''),
                s.get('outcome', ''),
                s.get('levels', len(s.get('trades') or []) - 1),
                len(s.get('trades') or []),
                f"{_session_pnl(s):.6f}",
            ])
    return len(proper)


def run_one(label: str, hp, pipeline_configs, out_path: Path):
    print(f'\n{"="*72}')
    print(f'{label}')
    print('=' * 72)

    from qengine.research.candles import get_candles
    from qengine.research.backtest import backtest
    import qengine.helpers as jh

    start_date = '2025-01-01'
    end_date = '2026-04-20'
    exchange, symbol, tf = 'OANDA', 'EUR-USD', '5m'
    start_ts = _to_ms(start_date)
    end_ts = _to_ms(end_date) + 86_400_000 - 60_000

    print(f'  loading 1m candles {start_date} → {end_date}…')
    _warmup, candles = get_candles(
        exchange=exchange, symbol=symbol, timeframe='1m',
        start_date_timestamp=start_ts, finish_date_timestamp=end_ts,
    )
    print(f'  loaded {len(candles):,} 1m candles')

    config = {'starting_balance': 10_000, 'fee': 0.0, 'type': 'cfd',
              'exchange': exchange, 'warm_up_candles': 210}
    routes = [{'exchange': exchange, 'strategy': 'Martingale',
               'symbol': symbol, 'timeframe': tf}]
    key = jh.key(exchange, symbol)
    cdict = {key: {'exchange': exchange, 'symbol': symbol, 'candles': candles}}

    t0 = datetime.utcnow()
    result = backtest(
        config=config, routes=routes, data_routes=[], candles=cdict,
        hyperparameters=hp, pipeline_configs=pipeline_configs,
        generate_equity_curve=False, cost_model=True,
    )
    elapsed = (datetime.utcnow() - t0).total_seconds()
    sessions = result.get('sessions', []) or []
    metrics = result.get('metrics', {}) or {}
    n = _dump_sessions(sessions, out_path)
    print(f'  ran in {elapsed:.1f}s, dumped {n} sessions → {out_path.name}')
    print(f'  net_profit={metrics.get("net_profit")}  pf={metrics.get("profit_factor")}')


def main():
    baseline_hp = {
        'preset': 'original', 'signal_mode': 'none', 'direction_bias': 'long_only',
        'sizing_curve': 'geometric', 'sizing_factor': 2.0, 'max_levels': 6,
        'hedge_mode': 'fixed_pips', 'hedge_value': 10.0,
        'tp_mode': 'fixed_pips', 'tp_value': 20.0,
        'base_size_mode': 'pct_equity', 'base_size_value': 1.0,
    }

    run_one(
        'Baseline — Martingale "original" preset, no pipeline',
        hp=baseline_hp, pipeline_configs=None,
        out_path=OUT_DIR / '04_baseline_sessions.csv',
    )

    run_one(
        'IslandPilot — trained model',
        hp=None, pipeline_configs=[{'name': 'IslandPilot'}],
        out_path=OUT_DIR / '04_islandpilot_sessions.csv',
    )


if __name__ == '__main__':
    main()
