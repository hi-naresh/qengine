#!/usr/bin/env python3
"""
At which level do busts actually terminate?
Is it always max_levels (theoretical), or earlier (broker forced close)?
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
if not os.path.exists(CSV):
    print('Run 01_bust_extraction.py first.')
    sys.exit(1)

busts = pd.read_csv(CSV)
all_s = pd.read_csv(os.path.join(RESULTS, 'all_sessions.csv'))

print(f'Total busts: {len(busts)}')
print(f'\nBust exit reasons:')
print(busts['outcome'].value_counts())

print(f'\nLevel reached at bust:')
print(busts['levels'].value_counts().sort_index())

at_max = (busts['levels'] == 8).sum()
below_max = (busts['levels'] < 8).sum()
print(f'\nAt max_levels (8): {at_max} ({at_max/len(busts)*100:.1f}%)')
print(f'Below max_levels:  {below_max} ({below_max/len(busts)*100:.1f}%)')
if below_max > 0:
    print('** ANOMALY: busts occurring before max level — broker forcing close **')
    print('  Log to observed.md: implicit forced close at level < max_levels')

print(f'\nPeak equity usage at bust (peak_equity_pct):')
print(busts['peak_equity_pct'].describe())

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
axes[0].bar(busts['levels'].value_counts().sort_index().index,
            busts['levels'].value_counts().sort_index().values, color='crimson')
axes[0].set_xlabel('Level reached'); axes[0].set_ylabel('Count')
axes[0].set_title('Bust level distribution')

axes[1].hist(busts['peak_equity_pct'].dropna(), bins=20, color='orange', edgecolor='black')
axes[1].set_xlabel('Peak equity usage %'); axes[1].set_ylabel('Count')
axes[1].set_title('Broker margin usage at time of bust')
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'level_cause_of_death.png'))
