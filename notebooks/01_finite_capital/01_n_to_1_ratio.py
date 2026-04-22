#!/usr/bin/env python3
"""
How many wins does 1 bust erase?
Sweeps (sizing_factor, max_levels) and computes N = |avg_bust_pnl| / avg_win_pnl.
Novel target: is N stable across configs, or does it vary exploitably?
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

SIZING_FACTORS = [1.3, 1.5, 2.0, 2.5, 3.0]
MAX_LEVELS     = [3, 4, 5, 6, 8]

print('Loading candles...')
candles = load_candles()

records = []
total = len(SIZING_FACTORS) * len(MAX_LEVELS)
i = 0
for sf in SIZING_FACTORS:
    for ml in MAX_LEVELS:
        i += 1
        hp = {**CANONICAL_HP, 'sizing_factor': sf, 'max_levels': ml}
        r = run_backtest(hp, candles=candles)
        df = sessions_to_df(r.get('sessions', []))
        if df.empty:
            continue
        wins  = df[~df['is_bust']]
        busts = df[df['is_bust']]
        if wins.empty or busts.empty:
            continue
        avg_win  = wins['pnl'].mean()
        avg_bust = busts['pnl'].mean()
        n_ratio  = abs(avg_bust) / avg_win if avg_win > 0 else np.nan
        records.append({
            'sizing_factor': sf, 'max_levels': ml,
            'avg_win': round(avg_win, 2),
            'avg_bust': round(avg_bust, 2),
            'n_ratio': round(n_ratio, 1),
            'n_sessions': len(df),
            'n_busts': len(busts),
            'win_rate': round(len(wins)/len(df), 4),
        })
        print(f'  [{i}/{total}] sf={sf} ml={ml}: N={n_ratio:.1f}  '
              f'busts={len(busts)} win_rate={len(wins)/len(df):.3f}')

results = pd.DataFrame(records)
results.to_csv(os.path.join(RESULTS, 'n_to_1_ratio.csv'), index=False)

# Heatmap of N
pivot = results.pivot(index='sizing_factor', columns='max_levels', values='n_ratio')
fig, ax = plt.subplots(figsize=(8, 5))
im = ax.imshow(pivot.values, aspect='auto', cmap='YlOrRd')
ax.set_xticks(range(len(pivot.columns))); ax.set_xticklabels(pivot.columns)
ax.set_yticks(range(len(pivot.index)));  ax.set_yticklabels(pivot.index)
ax.set_xlabel('max_levels'); ax.set_ylabel('sizing_factor')
ax.set_title('N-to-1 ratio: wins erased by 1 bust')
for r in range(pivot.shape[0]):
    for c in range(pivot.shape[1]):
        v = pivot.values[r, c]
        if not np.isnan(v):
            ax.text(c, r, f'{v:.0f}', ha='center', va='center', fontsize=9)
plt.colorbar(im, ax=ax)
save_fig(fig, os.path.join(RESULTS, 'n_to_1_heatmap.png'))

print('\nResults:')
print(results.to_string(index=False))
print(f'\nN ratio range: {results["n_ratio"].min():.1f} – {results["n_ratio"].max():.1f}')
print('Check observed.md if range > 3x across configs (exploitable variation)')
