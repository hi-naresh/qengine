#!/usr/bin/env python3
"""
Fixed-level abort vs margin-state-aware abort: which produces better outcomes?
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
csv = os.path.join(RESULTS, 'abort_vs_no_abort.csv')
if not os.path.exists(csv):
    print('Run 01_abort_vs_no_abort.py first.'); sys.exit(1)

df = pd.read_csv(csv)
print('Abort level analysis:')
print(df[['label','total_pnl','bust_rate','n_busts']].to_string(index=False))

baseline = df[df['abort_level'] == 0].iloc[0]
abort_rows = df[df['abort_level'] > 0].copy()
abort_rows['pnl_sacrifice'] = baseline['total_pnl'] - abort_rows['total_pnl']
abort_rows['bust_reduction'] = baseline['bust_rate'] - abort_rows['bust_rate']
# efficiency = bust reduction per dollar of PnL sacrificed (avoid div by zero)
abort_rows['efficiency'] = abort_rows['bust_reduction'] / (abort_rows['pnl_sacrifice'].abs() + 1)

best = abort_rows.loc[abort_rows['efficiency'].idxmax()]
print(f'\nPareto-optimal abort level: K={best["abort_level"]}')
print(f'  Bust reduction: {best["bust_reduction"]:.4f} ({best["bust_reduction"]/baseline["bust_rate"]*100:.1f}%)')
print(f'  PnL sacrifice:  ${best["pnl_sacrifice"]:.2f}')
print(f'\nConclusion: fixed-level abort at K={best["abort_level"]} is the optimal static policy.')
print('Next: test if margin-aware dynamic abort can improve on this — see 07_hp_interactions/')
