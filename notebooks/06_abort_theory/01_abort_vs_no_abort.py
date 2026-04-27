#!/usr/bin/env python3
"""
Does aborting at level K improve long-run EV?
Run same HP with abort_mode=level_threshold at K=1..7, compare to no-abort baseline.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

candles = load_candles()
records = []

# Baseline: no abort
hp_base = {**CANONICAL_HP, 'max_levels': 8, 'abort_mode': 'none'}
r = run_backtest(hp_base, candles=candles)
df_base = sessions_to_df(r.get('sessions', []))
base_pnl    = df_base['pnl'].sum()
base_busts  = df_base['is_bust'].sum()
base_bust_r = df_base['is_bust'].mean()
records.append({'abort_level': 0, 'label': 'no_abort', 'total_pnl': base_pnl,
                'bust_rate': base_bust_r, 'n_busts': base_busts})
print(f'Baseline (no abort): total_pnl=${base_pnl:.2f}  bust_rate={base_bust_r:.4f}')

# Abort at each level
for k in range(1, 9):
    hp = {**CANONICAL_HP, 'max_levels': 8, 'abort_mode': 'level_threshold', 'abort_level': k}
    r = run_backtest(hp, candles=candles)
    df = sessions_to_df(r.get('sessions', []))
    if df.empty: continue
    total_pnl  = df['pnl'].sum()
    bust_rate  = df['is_bust'].mean()
    aborts     = (df['outcome'] == 'abort').sum()
    records.append({'abort_level': k, 'label': f'abort@{k}', 'total_pnl': total_pnl,
                    'bust_rate': bust_rate, 'n_busts': df['is_bust'].sum(),
                    'n_aborts': aborts})
    print(f'abort@{k}: total_pnl=${total_pnl:.2f}  bust_rate={bust_rate:.4f}  aborts={aborts}')

df_r = pd.DataFrame(records)
df_r.to_csv(os.path.join(RESULTS, 'abort_vs_no_abort.csv'), index=False)

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
abort_rows = df_r[df_r['abort_level'] > 0]
axes[0].plot(abort_rows['abort_level'], abort_rows['bust_rate'], 'o-', color='crimson', label='Abort')
axes[0].axhline(base_bust_r, color='black', linestyle='--', label=f'No abort ({base_bust_r:.3f})')
axes[0].set_xlabel('Abort level'); axes[0].set_ylabel('Bust rate')
axes[0].set_title('Bust rate by abort level'); axes[0].legend()

axes[1].plot(abort_rows['abort_level'], abort_rows['total_pnl'], 'o-', color='steelblue', label='Abort')
axes[1].axhline(base_pnl, color='black', linestyle='--', label=f'No abort (${base_pnl:.0f})')
axes[1].set_xlabel('Abort level'); axes[1].set_ylabel('Total PnL ($)')
axes[1].set_title('Total PnL by abort level'); axes[1].legend()
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'abort_vs_no_abort.png'))

# Key finding: is there an optimal K?
if len(abort_rows) > 0:
    best_pnl_row = abort_rows.loc[abort_rows['total_pnl'].idxmax()]
    print(f'\nBest abort level by PnL: K={best_pnl_row["abort_level"]} (${best_pnl_row["total_pnl"]:.2f})')
    best_bust_row = abort_rows.loc[abort_rows['bust_rate'].idxmin()]
    print(f'Best abort level by bust_rate: K={best_bust_row["abort_level"]} ({best_bust_row["bust_rate"]:.4f})')
    if best_pnl_row['abort_level'] != best_bust_row['abort_level']:
        print('** FINDING: PnL-optimal and bust-rate-optimal abort levels differ — log to observed.md **')
