#!/usr/bin/env python3
"""Choppy market: multiple levels open simultaneously = high margin drain rate."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

all_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'all_sessions.csv')
df = pd.read_csv(all_csv)

df['margin_rate'] = df['peak_equity_pct'] / df['trade_count'].clip(lower=1)
print('Margin consumption rate (equity_pct per leg):')
print(f'  Busts: {df[df["is_bust"]]["margin_rate"].mean():.2f}')
print(f'  Wins:  {df[~df["is_bust"]]["margin_rate"].mean():.2f}')

busts = df[df['is_bust']]
print(f'\nFast-drain busts (margin_rate > 10): {(busts["margin_rate"] > 10).sum()} / {len(busts)}')

print('\nMargin rate percentiles by level:')
print(df.groupby('levels')['margin_rate'].describe())

df.to_csv(os.path.join(RESULTS, 'margin_consumption_rate.csv'), index=False)
print('Saved margin_consumption_rate.csv')
