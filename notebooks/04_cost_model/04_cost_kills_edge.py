#!/usr/bin/env python3
"""
At what level does cumulative cost (spread + est. swap) exceed the strategy edge?
Edge = avg_win_pnl (from backtest). If cumulative cost at level N > edge, losing territory.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')

all_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'all_sessions.csv')
if not os.path.exists(all_csv):
    print('Run bust anatomy first.'); import sys; sys.exit(1)

sessions = pd.read_csv(all_csv)
avg_win = sessions[~sessions['is_bust']]['pnl'].mean()
print(f'Average win PnL (edge): ${avg_win:.2f}')

SPREAD_PIPS = 2.0; SWAP_DAILY = 0.7; PIP_VALUE = 10.0; BASE_LOTS = 0.01
SFS = [1.5, 2.0, 2.5]
HOLD_DAYS = {0: 0.5, 1: 1.0, 2: 1.5, 3: 2.5, 4: 4.0, 5: 6.0, 6: 8.0, 7: 12.0, 8: 18.0}

fig, ax = plt.subplots(figsize=(10, 5))
for sf in SFS:
    cum = 0; records = []
    for n in range(9):
        lot_n = BASE_LOTS * (sf ** n)
        cost  = SPREAD_PIPS * lot_n * PIP_VALUE + SWAP_DAILY * HOLD_DAYS.get(n, n) * lot_n * PIP_VALUE
        cum  += cost
        records.append({'level': n, 'cumulative_cost': cum})
    df = pd.DataFrame(records)
    ax.plot(df['level'], df['cumulative_cost'], marker='o', label=f'sf={sf}')

ax.axhline(avg_win, color='green', linestyle='--', linewidth=2, label=f'avg_win=${avg_win:.2f}')
ax.set_xlabel('Level'); ax.set_ylabel('Cumulative cost ($)')
ax.set_title('Cumulative cost vs strategy edge\nCross = cost exceeds edge (losing territory)')
ax.legend(); ax.grid(True, alpha=0.3)
save_fig(fig, os.path.join(RESULTS, 'cost_kills_edge.png'))
print('Plot saved.')

# Find crossing level
for sf in SFS:
    for n in range(9):
        lot_n = BASE_LOTS * (sf ** n)
        cum = sum(SPREAD_PIPS * BASE_LOTS*(sf**k)*PIP_VALUE + SWAP_DAILY*HOLD_DAYS.get(k,k)*BASE_LOTS*(sf**k)*PIP_VALUE for k in range(n+1))
        if cum >= avg_win:
            print(f'sf={sf}: cost exceeds avg_win at level {n} (cum=${cum:.3f} vs avg_win=${avg_win:.2f})')
            break
