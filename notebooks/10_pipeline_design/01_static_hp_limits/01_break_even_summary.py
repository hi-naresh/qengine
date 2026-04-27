#!/usr/bin/env python3
"""Pivot 01 evidence: 0/25 static (sf, ml) configs cross break-even under real OANDA spread.

Reads the existing anatomy result `notebooks/01_finite_capital/results/break_even.csv`
and produces a 1-figure summary showing margin_of_safety per config, with the zero
line marked. The point of this script is presentation — the underlying data is
already established (Finding 7b in 09_synthesis/01_novel_findings.md).
"""
import os
import sys
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

ANATOMY_CSV = os.path.join(HERE, '..', '..', '01_finite_capital', 'results', 'break_even.csv')
if not os.path.exists(ANATOMY_CSV):
    sys.exit(f'ERROR: anatomy result not found at {ANATOMY_CSV}. Run notebooks/01_finite_capital first.')

df = pd.read_csv(ANATOMY_CSV)
df = df.sort_values('margin_of_safety', ascending=True)

fig, ax = plt.subplots(figsize=(10, 5))
labels = [f"sf={r.sizing_factor:g} ml={r.max_levels:g}" for r in df.itertuples()]
colors = ['crimson' if m < 0 else 'forestgreen' for m in df['margin_of_safety']]
ax.barh(labels, df['margin_of_safety'], color=colors)
ax.axvline(0, color='black', linewidth=1)
ax.set_xlabel('Margin of safety (actual_win_rate - p_min)')
ax.set_title(f'Pivot 01: 0/{len(df)} static configs cross break-even\nReal OANDA spread (mean ~1.57 pips), 18yr EUR-USD')
ax.invert_yaxis()
fig.tight_layout()
out = os.path.join(RESULTS, 'margin_of_safety_per_config.png')
fig.savefig(out, dpi=120)
plt.close(fig)

print(f'Saved {out}')
n_viable = (df['margin_of_safety'] > 0).sum()
n_total = len(df)
print(f'Viable configs: {n_viable}/{n_total}')
print(f'Best (least bad) margin: {df["margin_of_safety"].max():.4f}')
print(f'Worst margin: {df["margin_of_safety"].min():.4f}')
