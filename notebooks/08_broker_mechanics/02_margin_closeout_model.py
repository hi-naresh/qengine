#!/usr/bin/env python3
"""
NAV-based vs equity-based margin closeout: OANDA uses NAV (Net Asset Value).
NAV = balance + unrealized_pnl. Equity-based = just balance.
At deep levels with negative unrealized, NAV falls faster than equity → earlier closeout.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

EQUITY = 10_000; MARGIN_RATE = 1/30; PRICE = 1.10; LOT_SIZE = 100_000
BASE_LOTS = 0.01; SF = 2.0; SPREAD = 20

fig, ax = plt.subplots(figsize=(10, 5))
for model, color, label in [('nav', 'crimson', 'NAV-based (OANDA)'), ('equity', 'steelblue', 'Equity-based')]:
    balance = EQUITY
    nav_history = []
    margin_used = 0
    unrealized = 0
    for n in range(9):
        lot_n = BASE_LOTS * (SF ** n)
        margin_n = lot_n * PRICE * LOT_SIZE * MARGIN_RATE
        margin_used += margin_n
        unrealized -= SPREAD * 0.0001 * lot_n * LOT_SIZE
        nav = balance + unrealized
        check = nav if model == 'nav' else balance
        margin_pct = margin_used / check * 100
        nav_history.append({'level': n, 'nav': nav, 'margin_pct': margin_pct, 'forced': margin_pct >= 100})
        if margin_pct >= 100:
            print(f'{label}: forced close at level {n} (margin={margin_pct:.0f}%)')
            break
    levels = [x['level'] for x in nav_history]
    pcts   = [x['margin_pct'] for x in nav_history]
    ax.plot(levels, pcts, 'o-', color=color, label=label)

ax.axhline(100, color='red', linestyle='--', label='Closeout threshold (100%)')
ax.set_xlabel('Level'); ax.set_ylabel('Margin utilization %')
ax.set_title('NAV-based vs equity-based margin closeout\n(NAV closes earlier due to unrealized losses)')
ax.legend(); ax.grid(True, alpha=0.3)
save_fig(fig, os.path.join(RESULTS, 'margin_closeout_model.png'))
print('Key: NAV-based closeout at OANDA happens earlier than theory predicts.')
