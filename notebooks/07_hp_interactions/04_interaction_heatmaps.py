#!/usr/bin/env python3
"""
Compile all pairwise interaction data into a unified figure for pipeline bounds.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

csv1 = os.path.join(RESULTS, 'sizing_x_levels.csv')
csv2 = os.path.join(RESULTS, 'hedge_x_tp.csv')
csv3 = os.path.join('notebooks', '01_finite_capital', 'results', 'capital_boundary.csv')

fig, axes = plt.subplots(1, 3, figsize=(18, 5))
fig.suptitle('HP Interaction Maps — Pipeline Gene Bound Justification', fontsize=13)

if os.path.exists(csv1):
    df1 = pd.read_csv(csv1)
    pivot = df1.pivot(index='sf', columns='ml', values='bust_rate')
    axes[0].imshow(pivot.values, aspect='auto', cmap='RdYlGn_r')
    axes[0].set_title('sizing_factor × max_levels\n(bust rate)')
    axes[0].set_xlabel('max_levels')
    axes[0].set_ylabel('sizing_factor')

if os.path.exists(csv2):
    df2 = pd.read_csv(csv2)
    axes[1].bar(range(len(df2)), df2['bust_rate'], color='steelblue')
    axes[1].set_xticks(range(len(df2)))
    axes[1].set_xticklabels(df2['label'], rotation=15, ha='right', fontsize=8)
    axes[1].set_title('hedge × TP ratio\n(bust rate)')

if os.path.exists(csv3):
    df3 = pd.read_csv(csv3)
    for cfg in df3['config'].unique():
        sub = df3[df3['config'] == cfg]
        axes[2].plot(sub['equity'], sub['bust_rate'], 'o-', label=cfg)
    axes[2].set_xscale('log')
    axes[2].set_title('Equity sensitivity\n(bust rate vs capital)')
    axes[2].set_xlabel('Starting equity ($)')
    axes[2].legend()

plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'interaction_heatmaps.png'))
print('Unified interaction heatmaps saved.')
print('Use these to update IslandPilot _BOUND_OVERRIDES in island_evolver.py')
