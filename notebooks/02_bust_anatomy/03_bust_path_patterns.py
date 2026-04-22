#!/usr/bin/env python3
"""
Characterize the time-between-levels in bust paths vs win paths.
Fast escalation (choppy) vs slow escalation (normal)?
Not prediction — pure characterization of structural sub-types.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
CSV = os.path.join(RESULTS, 'bust_database.csv')
ALL_CSV = os.path.join(RESULTS, 'all_sessions.csv')

all_s = pd.read_csv(ALL_CSV)
busts = pd.read_csv(CSV)
wins  = all_s[~all_s['is_bust']]

all_s['pnl_per_level'] = all_s['pnl'] / (all_s['levels'] + 1)
bust_rows = all_s[all_s['is_bust']]
win_rows  = all_s[~all_s['is_bust']]

print('PnL per level at bust vs win:')
print(f'  Bust: mean={bust_rows["pnl_per_level"].mean():.2f}  std={bust_rows["pnl_per_level"].std():.2f}')
print(f'  Win:  mean={win_rows["pnl_per_level"].mean():.2f}  std={win_rows["pnl_per_level"].std():.2f}')

print('\nLegs in bust sessions:')
print(bust_rows['trade_count'].describe())
print('\nLegs in win sessions:')
print(win_rows['trade_count'].describe())

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
axes[0].hist(bust_rows['trade_count'].dropna(), bins=15, alpha=0.7, label='Bust', color='crimson')
axes[0].hist(win_rows['trade_count'].clip(upper=20).dropna(), bins=15, alpha=0.7, label='Win', color='green')
axes[0].set_xlabel('Legs (trade count)'); axes[0].set_title('Legs per session: bust vs win')
axes[0].legend()

axes[1].hist(bust_rows['peak_equity_pct'].dropna(), bins=15, alpha=0.7, label='Bust', color='crimson')
axes[1].hist(win_rows['peak_equity_pct'].dropna(), bins=15, alpha=0.7, label='Win', color='green')
axes[1].set_xlabel('Peak equity usage %'); axes[1].set_title('Peak equity usage: bust vs win')
axes[1].legend()
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'bust_path_patterns.png'))
print(f'\nSaved: bust_path_patterns.png')
