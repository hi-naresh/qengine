#!/usr/bin/env python3
"""
Does market structure affect how long sessions stay open?
Use trade_count as duration proxy. Split by bust vs win and level depth.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

all_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'all_sessions.csv')
df = pd.read_csv(all_csv)
busts = df[df['is_bust']]
wins  = df[~df['is_bust']]

print(f'Sessions: {len(df)} total, {len(busts)} busts, {len(wins)} wins')
print(f'\nSession duration (trade_count):')
print(f'  Bust: mean={busts["trade_count"].mean():.2f}  median={busts["trade_count"].median()}  std={busts["trade_count"].std():.2f}')
print(f'  Win:  mean={wins["trade_count"].mean():.2f}  median={wins["trade_count"].median()}  std={wins["trade_count"].std():.2f}')

print(f'\nAvg trades by level:')
print(df.groupby('levels')['trade_count'].mean().to_string())

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
axes[0].hist(wins['trade_count'].clip(upper=20), bins=15, alpha=0.7, color='green', label='Win')
axes[0].hist(busts['trade_count'], bins=15, alpha=0.7, color='crimson', label='Bust')
axes[0].set_xlabel('Trade count (duration proxy)'); axes[0].set_title('Session duration: bust vs win')
axes[0].legend()

level_groups = df.groupby('levels')['trade_count'].mean()
axes[1].bar(level_groups.index, level_groups.values, color='steelblue')
axes[1].set_xlabel('Level reached'); axes[1].set_ylabel('Avg trade count')
axes[1].set_title('Average session duration by level depth')
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'holding_time_by_structure.png'))
print('Saved holding_time_by_structure.png')
