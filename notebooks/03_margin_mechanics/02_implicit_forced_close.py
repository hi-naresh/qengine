#!/usr/bin/env python3
"""When does the broker force-close before theoretical max_levels?"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

candles = load_candles()
records = []

for equity in [1_000, 2_000, 5_000, 10_000]:
    for sf in [1.5, 2.0, 2.5]:
        hp = {**CANONICAL_HP, 'sizing_factor': sf, 'max_levels': 8}
        r = run_backtest(hp, candles=candles, balance=equity)
        df = sessions_to_df(r.get('sessions', []))
        if df.empty: continue
        busts = df[df['is_bust']]
        if busts.empty: continue
        avg_bust_level = busts['levels'].mean()
        margin_call_busts = busts[busts['outcome'].isin(['margin_call', 'margin_bust'])].shape[0]
        records.append({
            'equity': equity, 'sizing_factor': sf,
            'n_busts': len(busts),
            'avg_bust_level': round(avg_bust_level, 2),
            'max_bust_level': int(busts['levels'].max()),
            'margin_call_count': margin_call_busts,
            'margin_call_pct': round(margin_call_busts / len(busts) * 100, 1),
        })
        print(f'  equity={equity:,} sf={sf}: avg_bust_level={avg_bust_level:.1f}  '
              f'margin_calls={margin_call_busts}/{len(busts)}')

df_r = pd.DataFrame(records)
df_r.to_csv(os.path.join(RESULTS, 'implicit_forced_close.csv'), index=False)
print(df_r[['equity','sizing_factor','avg_bust_level','max_bust_level','margin_call_pct']].to_string(index=False))

forced_early = df_r[df_r['max_bust_level'] < 8]
if not forced_early.empty:
    print(f'\n** FINDING: {len(forced_early)} configs show broker closing before max_levels=8 **')
    print('Log to observed.md: implicit forced close at level < configured max_levels')
