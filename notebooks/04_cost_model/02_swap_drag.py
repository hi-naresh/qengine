#!/usr/bin/env python3
"""Swap accumulates with hold time. Deeper levels = longer hold = more swap drag."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

SWAP_PIPS_PER_DAY = -0.7
PIP_VALUE = 10.0
BASE_LOTS = 0.01
SFS = [1.5, 2.0, 2.5]

HOLD_DAYS_PER_LEVEL = {0: 0.5, 1: 1.0, 2: 1.5, 3: 2.5, 4: 4.0, 5: 6.0, 6: 8.0, 7: 12.0, 8: 18.0}

fig, ax = plt.subplots(figsize=(10, 5))
for sf in SFS:
    swap_costs = []
    for n, hold_days in HOLD_DAYS_PER_LEVEL.items():
        lot_n = BASE_LOTS * (sf ** n)
        swap  = abs(SWAP_PIPS_PER_DAY) * hold_days * lot_n * PIP_VALUE
        swap_costs.append({'level': n, 'swap_cost': swap})
    df = pd.DataFrame(swap_costs)
    ax.plot(df['level'], df['swap_cost'], marker='o', label=f'sf={sf}')

ax.set_xlabel('Level'); ax.set_ylabel('Swap cost ($)')
ax.set_title('Estimated swap drag by level\n(grows with both lot size AND hold time)')
ax.legend(); ax.grid(True, alpha=0.3)
save_fig(fig, os.path.join(RESULTS, 'swap_drag.png'))
print('Swap drag plot saved.')
print('Note: actual hold days need empirical measurement from bust_anatomy sessions.')
