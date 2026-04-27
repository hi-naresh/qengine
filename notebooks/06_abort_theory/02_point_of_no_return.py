#!/usr/bin/env python3
"""
Math: at what level is remaining EV negative regardless of outcome?
Point of no return = level where (cost to continue) > (expected recovery value).
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import numpy as np
import pandas as pd

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

bust_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'bust_database.csv')
all_csv  = os.path.join('notebooks', '02_bust_anatomy', 'results', 'all_sessions.csv')

if not os.path.exists(all_csv):
    print('Run bust anatomy first.'); sys.exit(1)

sessions = pd.read_csv(all_csv)
wins  = sessions[~sessions['is_bust']]
busts = sessions[sessions['is_bust']]
avg_win  = wins['pnl'].mean()
avg_bust = busts['pnl'].mean()

print(f'avg_win=${avg_win:.2f}  avg_bust=${avg_bust:.2f}')
print('\nConditional win rate given current level:')

point_of_no_return = None
rows = []
for lvl in range(0, 9):
    at_or_above = sessions[sessions['levels'] >= lvl]
    if at_or_above.empty: continue
    win_from_here = (~at_or_above['is_bust']).mean()
    exp_value = win_from_here * avg_win + (1 - win_from_here) * avg_bust
    rows.append({'level': lvl, 'n_sessions': len(at_or_above), 'p_win_from_here': win_from_here, 'ev': exp_value})
    print(f'  Level {lvl}: P(win | reached) = {win_from_here:.3f}  EV = ${exp_value:.2f}')
    if exp_value < 0 and point_of_no_return is None:
        point_of_no_return = lvl
        print(f'  ** POINT OF NO RETURN: level {lvl} has negative conditional EV **')
        print(f'     Log to observed.md')

df_ponr = pd.DataFrame(rows)
df_ponr.to_csv(os.path.join(RESULTS, 'point_of_no_return.csv'), index=False)

if point_of_no_return is not None:
    print(f'\nConclusion: abort policy should trigger no later than level {point_of_no_return}.')
else:
    print('\nConclusion: all levels show positive conditional EV — no structural point of no return found.')
    print('This means abort can only help by reducing variance, not by improving EV.')
