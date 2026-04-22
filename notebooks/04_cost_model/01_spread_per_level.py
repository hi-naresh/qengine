#!/usr/bin/env python3
"""
Spread cost is NOT flat — it grows with position size.
At level N with geometric sizing, spread_cost_N = spread_pips * lot_N * pip_value.
Measure cumulative spread cost as % of avg_win across levels.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

SPREAD_PIPS = 2.0
PIP_VALUE   = 10.0
BASE_LOTS   = 0.01
SFS = [1.5, 2.0, 2.5]
MAX_LEVEL = 8

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

for sf in SFS:
    levels = list(range(MAX_LEVEL + 1))
    spread_costs = []
    cumulative = 0
    for n in levels:
        lot_n = BASE_LOTS * (sf ** n)
        cost  = SPREAD_PIPS * lot_n * PIP_VALUE
        cumulative += cost
        spread_costs.append({'level': n, 'spread_cost': cost, 'cumulative': cumulative})
    df = pd.DataFrame(spread_costs)
    axes[0].plot(df['level'], df['spread_cost'], marker='o', label=f'sf={sf}')
    axes[1].plot(df['level'], df['cumulative'], marker='o', label=f'sf={sf}')

axes[0].set_xlabel('Level'); axes[0].set_ylabel('Spread cost at entry ($)')
axes[0].set_title('Spread cost per level entry (not flat — grows with lot size)')
axes[0].legend(); axes[0].grid(True, alpha=0.3)

axes[1].set_xlabel('Level'); axes[1].set_ylabel('Cumulative spread paid ($)')
axes[1].set_title('Cumulative spread cost across all levels')
axes[1].legend(); axes[1].grid(True, alpha=0.3)
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'spread_per_level.png'))

all_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'all_sessions.csv')
if os.path.exists(all_csv):
    sessions = pd.read_csv(all_csv)
    avg_win = sessions[~sessions['is_bust']]['pnl'].mean()
    print(f'Avg win PnL: ${avg_win:.2f}')
    for sf in SFS:
        cum_at_max = BASE_LOTS * PIP_VALUE * SPREAD_PIPS * sum(sf**n for n in range(MAX_LEVEL+1))
        print(f'sf={sf}: cumulative spread at level {MAX_LEVEL} = ${cum_at_max:.2f}  '
              f'({cum_at_max/avg_win*100:.1f}% of avg win)')
else:
    print('all_sessions.csv not yet available — run 02_bust_anatomy/01_bust_extraction.py first')
    for sf in SFS:
        cum_at_max = BASE_LOTS * PIP_VALUE * SPREAD_PIPS * sum(sf**n for n in range(MAX_LEVEL+1))
        print(f'sf={sf}: cumulative spread at level {MAX_LEVEL} = ${cum_at_max:.2f}')
print('\nSaved spread_per_level.png')
