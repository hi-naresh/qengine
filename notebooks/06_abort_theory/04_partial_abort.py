#!/usr/bin/env python3
"""
Can closing only the worst-performing tickets (not all) outperform full abort?
Simulate: at level K, close only tickets with pnl < -threshold, keep best.
This is a heuristic test — full simulation requires engine changes.
Use N-to-1 math to estimate impact.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
all_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'all_sessions.csv')
if not os.path.exists(all_csv):
    print('Run bust anatomy first.'); sys.exit(1)

sessions = pd.read_csv(all_csv)
wins  = sessions[~sessions['is_bust']]
busts = sessions[sessions['is_bust']]

BASE_WIN_RATE = len(wins) / len(sessions)
AVG_WIN = wins['pnl'].mean()
AVG_BUST = busts['pnl'].mean()

print('Partial abort analysis (theoretical):')
print(f'Base win rate: {BASE_WIN_RATE:.3f}')
print(f'Avg win: ${AVG_WIN:.2f}  Avg bust: ${AVG_BUST:.2f}')

for K in [3, 4, 5, 6]:
    # Full abort: realize full bust loss at level K
    # Partial: lose levels 1..K-1, keep L0 → L0 has p(win) chance
    # Geometric: level K loss ≈ 2^K * base_unit loss
    # Rough model: partial saves the L0 win if lucky
    ev_full_abort   = 0  # abort = 0 PnL, just stop
    ev_partial_keep = BASE_WIN_RATE * AVG_WIN + (1 - BASE_WIN_RATE) * (AVG_BUST * 0.7)
    print(f'  K={K}: EV(full_abort)=$0  EV(partial_keep_L0)=${ev_partial_keep:.2f}')

print('\nConclusion: partial abort can be positive EV if L0 ticket retains base win rate.')
print('Requires engine support to close individual tickets. Log to 09_synthesis/03_open_questions.md')
