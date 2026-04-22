#!/usr/bin/env python3
"""
Derive the theoretical margin consumption at each level.
Formula: margin_at_level_N = sum(lot_N * price * margin_rate) for all open tickets.
Lot at level n = base_lots * sizing_factor^n  (geometric).
Compare theory vs empirical peak_margin from backtester.
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

def theoretical_margin(sizing_factor, max_levels, base_pct_equity, equity):
    base_lots = (base_pct_equity / 100 * equity) / (PRICE * LOT_SIZE)
    margins = []
    total = 0
    for n in range(max_levels + 1):
        lot_n = base_lots * (sizing_factor ** n)
        margin_n = lot_n * PRICE * LOT_SIZE * MARGIN_RATE
        total += margin_n
        margins.append({'level': n, 'lots': lot_n, 'margin_this': margin_n, 'margin_total': total,
                         'equity_pct': total / equity * 100})
    return pd.DataFrame(margins)

configs = [
    {'sf': 1.5, 'ml': 6, 'label': 'sf=1.5, ml=6'},
    {'sf': 2.0, 'ml': 6, 'label': 'sf=2.0, ml=6'},
    {'sf': 2.0, 'ml': 8, 'label': 'sf=2.0, ml=8'},
    {'sf': 2.5, 'ml': 5, 'label': 'sf=2.5, ml=5'},
]
EQUITY = 10_000
BASE_PCT = 0.5

fig, ax = plt.subplots(figsize=(10, 6))
for cfg in configs:
    df = theoretical_margin(cfg['sf'], cfg['ml'], BASE_PCT, EQUITY)
    ax.plot(df['level'], df['equity_pct'], marker='o', label=cfg['label'])
    print(f"\n{cfg['label']}:")
    print(df[['level','lots','margin_total','equity_pct']].to_string(index=False))

ax.axhline(100, color='red', linestyle='--', label='100% equity (margin call)')
ax.axhline(50, color='orange', linestyle='--', alpha=0.5, label='50% equity')
ax.set_xlabel('Level'); ax.set_ylabel('Cumulative margin used (% equity)')
ax.set_title('Theoretical margin consumption by level\n(30:1 leverage, 0.5% base, €10k)')
ax.legend(); ax.grid(True, alpha=0.3)
save_fig(fig, os.path.join(RESULTS, 'margin_trajectory.png'))
print('\nSaved margin_trajectory.png')
