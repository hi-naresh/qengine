"""
Validate a trained IslandPilot model by running the EXACT same backtest API
that training uses, on HELD-OUT data, and reporting actual P&L.

Not via UI — purely the training-equivalent path. This tells you whether the
cloud run will produce something useful.

Usage:
    QENGINE_TRAINING_MODE=1 python3 -m pipelines._shared.IslandPilot.validate_model \
        --test-start 2024-02-01 --test-end 2024-02-29 \
        [--top-n 10]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _date_to_ms(s: str) -> int:
    return int(datetime.strptime(s, '%Y-%m-%d').timestamp() * 1000)


def main():
    os.environ.setdefault('QENGINE_TRAINING_MODE', '1')

    p = argparse.ArgumentParser()
    p.add_argument('--candles-file', default='candles_oanda_eurusd_1m_2022_2024.npy')
    p.add_argument('--test-start', default='2024-02-01')
    p.add_argument('--test-end', default='2024-02-29')
    p.add_argument('--top-n', type=int, default=10, help='Top N islands by training fitness to evaluate OOS')
    p.add_argument('--exchange', default='OANDA')
    p.add_argument('--symbol', default='EUR-USD')
    p.add_argument('--timeframe', default='5m')
    p.add_argument('--strategy', default='Martingale')
    args = p.parse_args()

    from pipelines._shared.IslandPilot.island_evolver import IslandEvolver
    from pipelines._shared.IslandPilot.train import _resolve_categorical_genes
    import pipelines._shared.IslandPilot.train as _tm
    from qengine.research.backtest import backtest as run_bt

    # Load trained model
    models_dir = _REPO / 'pipelines' / '_shared' / 'IslandPilot' / 'models'
    ev = IslandEvolver.load(str(models_dir / 'island_evolver.json'))

    # Load candles
    candles = np.load(args.candles_file)
    _tm._WORKER_CANDLES = candles
    ts_start = _date_to_ms(args.test_start)
    ts_end = _date_to_ms(args.test_end) + 86_400_000

    # Pick top N islands by training fitness
    best_per: list = []
    for lid, pop in ev.populations.items():
        best = max(pop.individuals, key=lambda x: x.fitness if x.fitness is not None else -999)
        if best.fitness is not None and best.fitness > 0:
            best_per.append((lid, best))
    best_per.sort(key=lambda x: x[1].fitness, reverse=True)
    top = best_per[:args.top_n]

    print(f'Trained islands (positive fitness): {len(best_per)} / {len(ev.populations)}')
    print(f'Evaluating top {len(top)} on OOS window {args.test_start} → {args.test_end}')
    print('')
    print(f'{"Island":<8} {"TrainFit":<10} {"Sessions":<10} {"Busts":<7} {"L0Win%":<8} {"PF":<8} {"NetPnL$":<10} {"DD%":<7} {"Verdict"}')
    print('-' * 90)

    mask = (candles[:, 0] >= ts_start) & (candles[:, 0] <= ts_end)
    subset = candles[mask]

    _PIPELINE_ONLY = {'gate_confidence_min', 'abort_aggressiveness', 'base_size_pct',
                      'hysteresis_margin', 'confidence_sensitivity', 'recovery_aggression'}

    aggregate = {'profitable': 0, 'losing': 0, 'no_trades': 0, 'total_pnl': 0.0}

    for lid, ind in top:
        hp = {k: v for k, v in ind.genes.items() if k not in _PIPELINE_ONLY}
        hp = _resolve_categorical_genes(hp, args.strategy)

        config = {'starting_balance': 10_000, 'fee': 0.0, 'type': 'cfd',
                  'exchange': args.exchange, 'warm_up_candles': 210}
        routes = [{'exchange': args.exchange, 'strategy': args.strategy,
                   'symbol': args.symbol, 'timeframe': args.timeframe}]
        cdict = {f'{args.exchange}-{args.symbol}': {'exchange': args.exchange,
                 'symbol': args.symbol, 'candles': subset}}

        try:
            r = run_bt(config=config, routes=routes, data_routes=[],
                       candles=cdict, hyperparameters=hp,
                       generate_equity_curve=False, cost_model=True)
        except Exception as e:
            print(f'{lid:<8} {ind.fitness:<10.2f} ERROR: {e}')
            continue

        m = r.get('metrics', {})
        sessions = r.get('sessions', [])
        proper = [s for s in sessions if isinstance(s.get('session'), int)]
        n_sessions = len(proper)
        _BUST = {'abort', 'terminate', 'max_level_bust', 'sl_hit', 'margin_call', 'margin_bust', 'max_level_sl'}
        n_bust = sum(1 for s in proper if s.get('outcome') in _BUST)
        l0_wins = sum(1 for s in proper if s.get('outcome') == 'tp_hit' and len(s.get('trades', [])) == 1)
        l0_rate = (l0_wins / n_sessions) if n_sessions > 0 else 0

        pf = m.get('profit_factor')
        pf_str = f'{pf:.2f}' if isinstance(pf, (int, float)) and pf is not None else 'N/A'
        net_pnl = m.get('net_profit', 0) or 0
        dd = m.get('max_drawdown_percentage')
        dd_str = f'{abs(dd):.1f}' if isinstance(dd, (int, float)) and dd is not None else 'N/A'

        # Verdict
        verdict = ''
        if n_sessions < 3:
            verdict = '⚠ too few sessions'
            aggregate['no_trades'] += 1
        elif net_pnl > 0 and (n_bust / max(1, n_sessions)) < 0.40:
            verdict = '✓ profitable'
            aggregate['profitable'] += 1
        elif net_pnl < 0:
            verdict = '✗ losing'
            aggregate['losing'] += 1
        else:
            verdict = '~ flat'
        aggregate['total_pnl'] += net_pnl

        print(f'{lid:<8} {ind.fitness:<10.2f} {n_sessions:<10} {n_bust:<7} '
              f'{l0_rate*100:<8.1f} {pf_str:<8} {net_pnl:<10.2f} {dd_str:<7} {verdict}')

    print('-' * 90)
    print(f'\nAggregate OOS over top {len(top)} islands:')
    print(f'  Profitable: {aggregate["profitable"]} / Losing: {aggregate["losing"]} / No trades: {aggregate["no_trades"]}')
    print(f'  Combined net P&L (if you ran all): ${aggregate["total_pnl"]:.2f}')

    # Verdict
    win_rate = aggregate['profitable'] / max(1, len(top))
    print('')
    if win_rate >= 0.5 and aggregate['total_pnl'] > 0:
        print('✓ VERDICT: Architecture works. Cloud training is safe to commit to.')
    elif win_rate >= 0.3:
        print('~ VERDICT: Partial signal. Cloud training may produce usable genomes but not guaranteed.')
    else:
        print('✗ VERDICT: Most genomes lose OOS. Do NOT commit to cloud yet.')


if __name__ == '__main__':
    main()
