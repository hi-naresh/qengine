#!/usr/bin/env python3
"""
Safe region of (sizing_factor, max_levels) given $10k equity, 30:1 leverage.
Use margin cushion map + empirical bust_rate to draw the feasibility frontier.
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

candles = load_candles()
SFS = [1.3, 1.5, 1.7, 2.0, 2.5, 3.0]
MLS = [3, 4, 5, 6, 7, 8]

records = []
total = len(SFS) * len(MLS)
i = 0
for sf in SFS:
    for ml in MLS:
        i += 1
        hp = {**CANONICAL_HP, 'sizing_factor': sf, 'max_levels': ml}
        r = run_backtest(hp, candles=candles)
        df = sessions_to_df(r.get('sessions', []))
        if df.empty: continue
        bust_rate = df['is_bust'].mean()
        total_pnl = df['pnl'].sum()
        records.append({'sf': sf, 'ml': ml, 'bust_rate': bust_rate, 'total_pnl': total_pnl})
        print(f'[{i}/{total}] sf={sf} ml={ml}: bust_rate={bust_rate:.4f}')

df_r = pd.DataFrame(records)
df_r.to_csv(os.path.join(RESULTS, 'sizing_x_levels.csv'), index=False)

pivot = df_r.pivot(index='sf', columns='ml', values='bust_rate')
fig, ax = plt.subplots(figsize=(9, 6))
im = ax.imshow(pivot.values, aspect='auto', cmap='RdYlGn_r', vmin=0, vmax=0.05)
ax.set_xticks(range(len(pivot.columns))); ax.set_xticklabels(pivot.columns)
ax.set_yticks(range(len(pivot.index))); ax.set_yticklabels([f'{s:.1f}' for s in pivot.index])
ax.set_xlabel('max_levels'); ax.set_ylabel('sizing_factor')
ax.set_title('Bust rate: sizing_factor × max_levels\n(Green = safe, Red = high bust)')
for r in range(pivot.shape[0]):
    for c in range(pivot.shape[1]):
        v = pivot.values[r, c]
        if not np.isnan(v):
            ax.text(c, r, f'{v:.3f}', ha='center', va='center', fontsize=8)
plt.colorbar(im, ax=ax)
save_fig(fig, os.path.join(RESULTS, 'sizing_x_levels_heatmap.png'))
print('Saved. Safe region = green zone. Log boundary to 09_synthesis/02_pipeline_implications.md')
