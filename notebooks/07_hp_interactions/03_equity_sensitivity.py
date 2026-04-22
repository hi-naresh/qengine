#!/usr/bin/env python3
"""Survivability sensitivity to starting equity — extend capital boundary analysis."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd

cap_csv = os.path.join('notebooks', '01_finite_capital', 'results', 'capital_boundary.csv')
if not os.path.exists(cap_csv):
    print('Run 01_finite_capital/03_capital_boundary.py first.'); sys.exit(1)

df = pd.read_csv(cap_csv)
print('Equity sensitivity (from capital boundary data):')
print(df[['config','equity','bust_rate','net_pct']].to_string(index=False))

# Find inflection: where bust_rate increases sharply
for config in df['config'].unique():
    sub = df[df['config'] == config].sort_values('equity')
    sub = sub.copy()
    sub['bust_delta'] = sub['bust_rate'].diff()
    inflection = sub.loc[sub['bust_delta'].idxmax()]
    print(f"\n{config}: bust_rate inflects at equity=${inflection['equity']:,} "
          f"(Δbust_rate={inflection['bust_delta']:.4f})")
    print(f'  This is the minimum safe equity for this config.')
