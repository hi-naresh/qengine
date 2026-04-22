#!/usr/bin/env python3
"""
2D heatmap: at which (sizing_factor, max_levels) does cumulative margin
exceed 100% equity at OANDA 30:1, given 0.5% base size and $10k?
This defines the structurally infeasible region for pipeline gene bounds.
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

MARGIN_RATE = 1 / 30
PRICE = 1.10
LOT_SIZE = 100_000
EQUITY = 10_000
BASE_PCT = 0.5

SFS = np.round(np.arange(1.2, 3.1, 0.1), 1)
MLS = list(range(2, 13))

data = np.zeros((len(SFS), len(MLS)))
level_at_100 = np.full((len(SFS), len(MLS)), np.nan)

for i, sf in enumerate(SFS):
    for j, ml in enumerate(MLS):
        base_lots = (BASE_PCT / 100 * EQUITY) / (PRICE * LOT_SIZE)
        total_margin = 0
        for n in range(ml + 1):
            lot_n = base_lots * (sf ** n)
            total_margin += lot_n * PRICE * LOT_SIZE * MARGIN_RATE
            if total_margin >= EQUITY and np.isnan(level_at_100[i, j]):
                level_at_100[i, j] = n
        pct = total_margin / EQUITY * 100
        data[i, j] = min(pct, 200)

fig, axes = plt.subplots(1, 2, figsize=(16, 6))

im0 = axes[0].imshow(data, aspect='auto', cmap='RdYlGn_r', vmin=0, vmax=150)
axes[0].set_xticks(range(len(MLS))); axes[0].set_xticklabels(MLS)
axes[0].set_yticks(range(len(SFS))); axes[0].set_yticklabels([f'{s:.1f}' for s in SFS])
axes[0].set_xlabel('max_levels'); axes[0].set_ylabel('sizing_factor')
axes[0].set_title('Total margin at deepest level (% equity)\nRed = margin call territory')
plt.colorbar(im0, ax=axes[0])

im1 = axes[1].imshow(level_at_100, aspect='auto', cmap='RdYlGn', vmin=2, vmax=12)
axes[1].set_xticks(range(len(MLS))); axes[1].set_xticklabels(MLS)
axes[1].set_yticks(range(len(SFS))); axes[1].set_yticklabels([f'{s:.1f}' for s in SFS])
axes[1].set_xlabel('max_levels'); axes[1].set_ylabel('sizing_factor')
axes[1].set_title('Level at which broker forces close (margin = 100%)\nGreen = never hits 100%')
plt.colorbar(im1, ax=axes[1])

plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'margin_cushion_map.png'))

infeasible = [(SFS[i], MLS[j]) for i in range(len(SFS)) for j in range(len(MLS))
              if not np.isnan(level_at_100[i, j]) and level_at_100[i, j] < MLS[j]]
print(f'Infeasible combos (broker closes before max_levels): {len(infeasible)}/{len(SFS)*len(MLS)}')
print('These define the FORBIDDEN region for IslandPilot gene bounds.')
