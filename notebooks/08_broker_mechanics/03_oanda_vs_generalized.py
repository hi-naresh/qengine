#!/usr/bin/env python3
"""
Generalized broker model: parameterized by (margin_rate, lot_unit, closeout_basis).
Instantiate with OANDA params and show how results change vs an idealized broker.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import numpy as np
import pandas as pd

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

def broker_model(name, margin_rate, min_lot, lot_size, closeout_basis,
                 equity, base_pct, sf, max_levels, spread_pips):
    records = []
    base_lots = (base_pct / 100 * equity) / (1.10 * lot_size)
    margin_used = 0; unrealized = 0; balance = equity
    for n in range(max_levels + 1):
        lot_n = max(min_lot, round(base_lots * (sf ** n) / min_lot) * min_lot)
        margin_n = lot_n * 1.10 * lot_size * margin_rate
        margin_used += margin_n
        unrealized -= spread_pips * 0.0001 * lot_n * lot_size
        nav = balance + unrealized
        check = nav if closeout_basis == 'nav' else balance
        margin_pct = margin_used / check * 100 if check > 0 else 999
        records.append({'broker': name, 'level': n, 'margin_pct': margin_pct,
                        'forced': margin_pct >= 100, 'lots': lot_n})
        if margin_pct >= 100:
            break
    return pd.DataFrame(records)

brokers = [
    dict(name='OANDA (real)', margin_rate=1/30, min_lot=1, lot_size=1,
         closeout_basis='nav', spread_pips=2),
    dict(name='Idealized (no spread, equity-based)', margin_rate=1/30, min_lot=0.001,
         lot_size=100_000, closeout_basis='equity', spread_pips=0),
    dict(name='High-leverage CFD (50:1)', margin_rate=1/50, min_lot=0.001,
         lot_size=100_000, closeout_basis='equity', spread_pips=1),
]

all_results = []
for b in brokers:
    df = broker_model(**b, equity=10_000, base_pct=0.5, sf=2.0, max_levels=8)
    all_results.append(df)
    max_safe_level = df[~df['forced']]['level'].max() if (~df['forced']).any() else -1
    print(f"{b['name']}: max safe level = {max_safe_level}")

combined = pd.concat(all_results)
combined.to_csv(os.path.join(RESULTS, 'oanda_vs_generalized.csv'), index=False)
print('\nSaved oanda_vs_generalized.csv')
print('OANDA real vs idealized broker shows structural gap in achievable levels.')
