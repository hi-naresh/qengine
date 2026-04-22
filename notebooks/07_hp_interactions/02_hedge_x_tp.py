#!/usr/bin/env python3
"""Degenerate case: hedge == TP. Also test hedge > TP and hedge < TP."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)
candles = load_candles()

configs = [
    {'hedge': 10, 'tp': 5,  'label': 'hedge > TP'},
    {'hedge': 10, 'tp': 10, 'label': 'hedge == TP (degenerate)'},
    {'hedge': 10, 'tp': 15, 'label': 'hedge < TP (1.5x)'},
    {'hedge': 10, 'tp': 20, 'label': 'hedge < TP (2x)'},
    {'hedge': 10, 'tp': 30, 'label': 'hedge < TP (3x)'},
]
records = []
for cfg in configs:
    hp = {**CANONICAL_HP, 'hedge_value': cfg['hedge'], 'tp_value': cfg['tp']}
    r = run_backtest(hp, candles=candles)
    df = sessions_to_df(r.get('sessions', []))
    if df.empty: continue
    records.append({'label': cfg['label'], 'hedge': cfg['hedge'], 'tp': cfg['tp'],
                    'bust_rate': df['is_bust'].mean(), 'total_pnl': df['pnl'].sum(),
                    'n_sessions': len(df)})
    print(f"{cfg['label']}: bust_rate={df['is_bust'].mean():.4f}  pnl=${df['pnl'].sum():.2f}")

pd.DataFrame(records).to_csv(os.path.join(RESULTS, 'hedge_x_tp.csv'), index=False)
print('\nIf hedge==TP shows anomalous bust_rate, log to anomalies.md')
