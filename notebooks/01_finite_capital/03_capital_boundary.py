#!/usr/bin/env python3
"""
At what starting equity does the config become structurally ruin-prone?
Run same HP at 5 equity levels. Find where bust_rate inflects.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

EQUITY_LEVELS = [1_000, 2_500, 5_000, 10_000, 25_000]
CONFIGS = [
    {'label': 'aggressive', 'sizing_factor': 2.0, 'max_levels': 8},
    {'label': 'conservative', 'sizing_factor': 1.5, 'max_levels': 4},
]

print('Loading candles...')
candles = load_candles()

records = []
for cfg in CONFIGS:
    for eq in EQUITY_LEVELS:
        hp = {**CANONICAL_HP, **cfg}
        hp.pop('label', None)
        r = run_backtest(hp, candles=candles, balance=eq)
        df = sessions_to_df(r.get('sessions', []))
        if df.empty:
            continue
        bust_rate = df['is_bust'].mean()
        metrics   = r.get('metrics', {})
        records.append({
            'config': cfg['label'],
            'equity': eq,
            'bust_rate': round(bust_rate, 4),
            'win_rate':  round(1 - bust_rate, 4),
            'n_sessions': len(df),
            'net_pct': metrics.get('net_profit_percentage', 0),
        })
        print(f"  {cfg['label']} equity={eq:,}: bust_rate={bust_rate:.3f}")

df_r = pd.DataFrame(records)
df_r.to_csv(os.path.join(RESULTS, 'capital_boundary.csv'), index=False)

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
for ax, cfg_label in zip(axes, [c['label'] for c in CONFIGS]):
    sub = df_r[df_r['config'] == cfg_label]
    ax.plot(sub['equity'], sub['bust_rate'], 'o-', color='crimson')
    ax.set_xscale('log')
    ax.set_xlabel('Starting equity ($)')
    ax.set_ylabel('Bust rate')
    ax.set_title(f'{cfg_label} — bust rate vs equity')
    ax.grid(True, alpha=0.3)
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'capital_boundary.png'))

print('\nCapital boundary results:')
print(df_r.to_string(index=False))
print('\nNote: if bust_rate increases sharply below a threshold equity, log that threshold to observed.md')
