#!/usr/bin/env python3
"""
OANDA rounds positions to integer units. Does rounding cause systematic under/over-hedging?
At small equity, rounding error as % of intended position is non-negligible.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import numpy as np
import pandas as pd

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

PRICE = 1.10; EQUITY_LEVELS = [1_000, 2_500, 5_000, 10_000, 25_000]
SFS = [1.5, 2.0, 2.5]; BASE_PCT = 0.5

records = []
for eq in EQUITY_LEVELS:
    for sf in SFS:
        for level in range(9):
            target_notional = (BASE_PCT / 100 * eq)
            target_units_float = target_notional * (sf ** level) / PRICE
            rounded_units = int(round(target_units_float))
            rounding_error_pct = (rounded_units - target_units_float) / target_units_float * 100 if target_units_float > 0 else 0
            records.append({'equity': eq, 'sf': sf, 'level': level,
                            'target_units': target_units_float,
                            'rounded_units': rounded_units,
                            'error_pct': rounding_error_pct})

df = pd.DataFrame(records)
significant = df[df['error_pct'].abs() > 5]
print(f'Rounding errors > 5%: {len(significant)} cases')
print(significant[['equity','sf','level','target_units','rounded_units','error_pct']].head(20).to_string(index=False))

for eq in EQUITY_LEVELS:
    sub = df[df['equity'] == eq]
    print(f'Equity ${eq:,}: max rounding error = {sub["error_pct"].abs().max():.1f}%')

df.to_csv(os.path.join(RESULTS, 'lot_rounding.csv'), index=False)
print('\nSaved lot_rounding.csv')
print('If error > 10% at any level, strategy is systematically mis-hedging at that equity level.')
