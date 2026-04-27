#!/usr/bin/env python3
"""
Minimum win rate for positive expectancy.
EV = p*avg_win + (1-p)*avg_bust = 0  →  p_min = |avg_bust| / (avg_win + |avg_bust|)
Novel target: margin of safety = actual_win_rate - p_min. Is it stable?
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from notebooks.shared.utils import sessions_to_df, save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')

csv = os.path.join(RESULTS, 'n_to_1_ratio.csv')
if not os.path.exists(csv):
    print('Run 01_n_to_1_ratio.py first.')
    sys.exit(1)

df = pd.read_csv(csv)

df['p_min'] = df['avg_bust'].abs() / (df['avg_win'] + df['avg_bust'].abs())
df['margin_of_safety'] = df['win_rate'] - df['p_min']
df['is_viable'] = df['margin_of_safety'] > 0

print('Break-even analysis:')
print(df[['sizing_factor','max_levels','win_rate','p_min','margin_of_safety','is_viable']].to_string(index=False))

df.to_csv(os.path.join(RESULTS, 'break_even.csv'), index=False)

pivot = df.pivot(index='sizing_factor', columns='max_levels', values='margin_of_safety')
fig, ax = plt.subplots(figsize=(8, 5))
im = ax.imshow(pivot.values, aspect='auto', cmap='RdYlGn', vmin=-0.1, vmax=0.2)
ax.set_xticks(range(len(pivot.columns))); ax.set_xticklabels(pivot.columns)
ax.set_yticks(range(len(pivot.index)));  ax.set_yticklabels(pivot.index)
ax.set_xlabel('max_levels'); ax.set_ylabel('sizing_factor')
ax.set_title('Margin of safety = actual_win_rate - break_even_win_rate')
for r in range(pivot.shape[0]):
    for c in range(pivot.shape[1]):
        v = pivot.values[r, c]
        if not np.isnan(v):
            ax.text(c, r, f'{v:.3f}', ha='center', va='center', fontsize=8)
plt.colorbar(im, ax=ax)
save_fig(fig, os.path.join(RESULTS, 'break_even_safety_margin.png'))

viable = df[df['is_viable']]
print(f'\nViable configs (margin_of_safety > 0): {len(viable)}/{len(df)}')
print('Log to anomalies.md any configs with p_min > actual win_rate (structurally losing).')
