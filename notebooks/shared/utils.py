"""Shared utilities for all martingale anatomy research scripts."""
import os
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from qengine.research.candles import get_candles
from qengine.research.backtest import backtest

EXCHANGE = 'OANDA'
SYMBOL = 'EUR-USD'
TIMEFRAME = '5m'
DATA_END = '2024-12-31'

BUST_REASONS = {
    'abort', 'terminate', 'max_level_bust', 'sl_hit',
    'margin_call', 'margin_bust', 'max_level_sl',
}

BASE_CONFIG = {
    'starting_balance': 10_000,
    'fee': 0.0,
    'type': 'cfd',
    'exchange': 'OANDA',
    'warm_up_candles': 210,
}

BASE_ROUTES = [{
    'exchange': EXCHANGE,
    'strategy': 'Martingale',
    'symbol': SYMBOL,
    'timeframe': TIMEFRAME,
}]


def load_candles(start_date='2006-01-02', end_date=DATA_END):
    """Load EUR-USD candles. Always use end_date <= 2024-12-31."""
    assert end_date <= DATA_END, f"No 2025+ data allowed. Got {end_date}"
    warmup, candles = get_candles(
        exchange=EXCHANGE, symbol=SYMBOL, timeframe=TIMEFRAME,
        start_date=start_date, finish_date=end_date,
    )
    if warmup.ndim == 2 and len(warmup) > 0:
        return np.concatenate([warmup, candles], axis=0)
    return candles


def make_candles_dict(candles):
    key = f'{EXCHANGE}-{SYMBOL}'
    return {key: {'exchange': EXCHANGE, 'symbol': SYMBOL, 'candles': candles}}


def run_backtest(hp: dict, candles=None, start_date='2006-01-02',
                 balance=10_000) -> dict:
    """Run a single backtest, return result with result['sessions']."""
    if candles is None:
        candles = load_candles(start_date=start_date)
    cfg = {**BASE_CONFIG, 'starting_balance': balance}
    return backtest(
        config=cfg,
        routes=BASE_ROUTES,
        data_routes=[],
        candles=make_candles_dict(candles),
        hyperparameters=hp,
        generate_equity_curve=False,
    )


def sessions_to_df(sessions: list):
    """Convert result['sessions'] to a pandas DataFrame."""
    import pandas as pd
    rows = []
    for s in sessions:
        if not isinstance(s.get('session'), int):
            continue
        rows.append({
            'session': s['session'],
            'levels': s.get('levels', 0),
            'pnl': s.get('total_pnl', 0),
            'is_bust': s.get('outcome', '') in BUST_REASONS,
            'outcome': s.get('outcome', ''),
            'peak_margin': s.get('peak_margin', 0),
            'peak_equity_pct': s.get('peak_equity_pct', 0),
            'opened_at': s.get('opened_at'),
            'closed_at': s.get('closed_at'),
            'trade_count': s.get('trade_count', 0),
        })
    return pd.DataFrame(rows)


def save_fig(fig, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {path}')


CANONICAL_HP = {
    'preset': 'custom',
    'signal_mode': 'random',
    'direction_bias': 'both',
    'sizing_curve': 'geometric',
    'sizing_factor': 2.0,
    'base_size_mode': 'pct_equity',
    'base_size_value': 0.5,
    'max_levels': 6,
    'hedge_mode': 'fixed_pips',
    'hedge_value': 20.0,
    'tp_mode': 'fixed_pips',
    'tp_value': 20.0,
}
