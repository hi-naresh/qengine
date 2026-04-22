#!/usr/bin/env python3
"""Wrong hedge distance in volatile regime: bust_rate by hedge_value setting."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

candles = load_candles()
HEDGE_VALUES = [5, 10, 15, 20, 30, 40]
records = []
for hv in HEDGE_VALUES:
    hp = {**CANONICAL_HP, 'hedge_value': hv, 'tp_value': hv}
    r = run_backtest(hp, candles=candles)
    df = sessions_to_df(r.get('sessions', []))
    if df.empty: continue
    records.append({'hedge_pips': hv, 'bust_rate': df['is_bust'].mean(),
                    'avg_win': df[~df['is_bust']]['pnl'].mean() if (~df['is_bust']).any() else 0,
                    'n_sessions': len(df)})
    print(f'  hedge={hv}pips: bust_rate={df["is_bust"].mean():.4f}')

df_r = pd.DataFrame(records)
df_r.to_csv(os.path.join(RESULTS, 'volatility_vs_hedge.csv'), index=False)
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(df_r['hedge_pips'], df_r['bust_rate'], 'o-', color='crimson')
ax.set_xlabel('Hedge distance (pips)'); ax.set_ylabel('Bust rate')
ax.set_title('Bust rate vs hedge distance')
ax.grid(True, alpha=0.3)
save_fig(fig, os.path.join(RESULTS, 'volatility_vs_hedge.png'))
print(df_r.to_string(index=False))
