#!/usr/bin/env python3
"""
Effective hedge distance = configured_pips - spread_pips.
This shifts all ruin-probability math because the real grid is tighter than configured.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

SPREAD_PIPS = 2.0
CONFIGURED_HEDGES = np.arange(5, 55, 5)
EFFECTIVE = CONFIGURED_HEDGES - SPREAD_PIPS
SHRINKAGE = (CONFIGURED_HEDGES - EFFECTIVE) / CONFIGURED_HEDGES * 100

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
axes[0].plot(CONFIGURED_HEDGES, EFFECTIVE, 'o-', color='steelblue')
axes[0].plot(CONFIGURED_HEDGES, CONFIGURED_HEDGES, '--', color='gray', label='No adjustment')
axes[0].set_xlabel('Configured hedge (pips)'); axes[0].set_ylabel('Effective hedge (pips)')
axes[0].set_title('Effective grid distance after spread'); axes[0].legend()

axes[1].plot(CONFIGURED_HEDGES, SHRINKAGE, 'o-', color='crimson')
axes[1].set_xlabel('Configured hedge (pips)'); axes[1].set_ylabel('Shrinkage (%)')
axes[1].set_title('% grid shrinkage from spread\n(largest at tight grids)')
axes[1].axhline(10, color='orange', linestyle='--', label='10% threshold')
axes[1].legend(); axes[1].grid(True, alpha=0.3)
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'effective_grid_distance.png'))

print('Effective grid distance:')
for c, e, s in zip(CONFIGURED_HEDGES, EFFECTIVE, SHRINKAGE):
    print(f'  configured={c:.0f}  effective={e:.0f}  shrinkage={s:.1f}%')
print('\nKey: with 2-pip spread, a 10-pip grid is effectively 8 pips — 20% tighter.')
