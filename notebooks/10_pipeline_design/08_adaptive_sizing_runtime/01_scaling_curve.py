#!/usr/bin/env python3
"""Pivot 08 evidence: visualize the AdaptiveSizer's runtime scaling curve.

Plot of f_conf(c) = c^a for representative values of the evolved exponent a,
and f_dd(d) for representative recovery_aggression values. The combined scaling
factor is f_conf × f_dd × f_base (the latter is just a static gene).

Mean evolved values from MEMORY.md / DESIGN_RATIONALE.md:
  confidence_sensitivity ≈ 1.46
  recovery_aggression    ≈ 0.57
"""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

c = np.linspace(0, 1, 200)
fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))

# Confidence scaling curves
for a, label in [(0.5, 'a=0.5 concave'), (1.0, 'a=1.0 linear'), (1.46, 'a=1.46 (mean evolved)'), (2.0, 'a=2.0 convex')]:
    axes[0].plot(c, c ** a, label=label)
axes[0].set_xlabel('GMM posterior confidence (max class prob)')
axes[0].set_ylabel('f_conf = confidence^a')
axes[0].set_title('Confidence scaling: f_conf(confidence) = confidence^confidence_sensitivity')
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# Drawdown scaling curves
d = np.linspace(0, 0.5, 200)  # current drawdown fraction (0 = none, 0.5 = 50%)
for r, label in [(0.0, 'r=0.0 (no recovery scaling)'), (0.3, 'r=0.3 mild'), (0.57, 'r=0.57 (mean evolved)'), (1.0, 'r=1.0 strong')]:
    axes[1].plot(d, np.maximum(0, 1 - r * d * 2), label=label)
axes[1].set_xlabel('Current drawdown fraction')
axes[1].set_ylabel('f_dd = max(0, 1 - r * drawdown_factor)')
axes[1].set_title('Drawdown scaling: position scaled down during drawdown periods')
axes[1].legend()
axes[1].grid(True, alpha=0.3)

fig.suptitle('Pivot 08: AdaptiveSizer runtime scaling components', fontsize=13)
fig.tight_layout()
out = os.path.join(RESULTS, 'scaling_curves.png')
fig.savefig(out, dpi=120)
plt.close(fig)
print(f'Saved {out}')
print('Note: f_conf × f_dd × f_base is the per-cycle multiplier on base position size.')
