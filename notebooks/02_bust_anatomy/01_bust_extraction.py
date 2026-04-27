#!/usr/bin/env python3
"""
Run full backtest, extract every bust session with complete state snapshot.
Saves bust database for all downstream anatomy scripts.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

print('Loading candles (full 2006–2024)...')
candles = load_candles()

hp = {**CANONICAL_HP, 'max_levels': 8}

print('Running full backtest...')
r = run_backtest(hp, candles=candles)
sessions = r.get('sessions', [])
print(f'Total sessions: {len(sessions)}')

df = sessions_to_df(sessions)
busts = df[df['is_bust']].copy()
wins  = df[~df['is_bust']].copy()

print(f'Busts: {len(busts)} ({len(busts)/len(df)*100:.2f}%)')
print(f'Wins:  {len(wins)}')
print(f'Avg bust PnL: ${busts["pnl"].mean():.2f}')
print(f'Avg win  PnL: ${wins["pnl"].mean():.2f}')
print(f'Bust level distribution:\n{busts["levels"].value_counts().sort_index()}')

df.to_csv(os.path.join(RESULTS, 'all_sessions.csv'), index=False)
busts.to_csv(os.path.join(RESULTS, 'bust_database.csv'), index=False)
print(f'\nSaved: all_sessions.csv ({len(df)} rows), bust_database.csv ({len(busts)} rows)')

metrics = r.get('metrics', {})
print(f'\nBacktest metrics: {metrics}')
