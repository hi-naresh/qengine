#!/usr/bin/env python3
"""
Step 7: Deep Bust Anatomy & Last Leg Probability
=================================================
The deepest investigation into WHY and WHEN cycles bust.

Key questions answered:
1. P(win | reached level N) — conditional win probability at each depth
2. Transition matrix: P(reaching L(N+1) | reached L(N))
3. Last leg (L4) win rate — when the final level triggers, how often does it save us?
4. Market conditions at bust vs at win — ATR, session, volatility regime, range
5. Bust clustering — do busts come in bunches? Serial correlation
6. Duration analysis — how long do winning vs busting cycles take?
7. Price behavior before bust — what does price do in the bars leading to a deep cycle?
"""

import os, sys
os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from datetime import datetime, timezone
from collections import defaultdict
import time

import qengine.indicators as ta
import qengine.helpers as jh
from qengine.research import get_candles

# ─── Parameters (same as 05/06 for consistency) ─────────────────────────────
TP_ATR_MULTIPLE = 0.8
RISK_REWARD = 2.0
MULTIPLIER = 2.0
MAX_LEVELS = 5
ATR_PERIOD = 14
PIP_SIZE = 0.0001
BASE_SIZE = 0.1
PIP_VALUE = 10.0
MAX_BARS_PER_LEVEL = 500
EMA_FAST = 8
EMA_SLOW = 21

OUTPUT_DIR = 'notebooks/surefire_v2'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Load Data ───────────────────────────────────────────────────────────────
print("Loading EUR-USD 5m candles...")
t0 = time.time()
warmup_candles, candles = get_candles('OANDA', 'EUR-USD', '5m',
    jh.date_to_timestamp('2024-01-01'), jh.date_to_timestamp('2026-03-01'),
    warmup_candles_num=210)
if warmup_candles is not None and warmup_candles.ndim == 2 and len(warmup_candles) > 0:
    candles = np.concatenate([warmup_candles, candles], axis=0)

print(f"Total candles: {len(candles):,} ({time.time()-t0:.1f}s)")

timestamps = candles[:, 0]
opens  = candles[:, 1]
closes = candles[:, 2]
highs  = candles[:, 3]
lows   = candles[:, 4]

# ─── Indicators ──────────────────────────────────────────────────────────────
ema_fast = ta.ema(candles, period=EMA_FAST, sequential=True)
ema_slow = ta.ema(candles, period=EMA_SLOW, sequential=True)
atr_arr  = ta.atr(candles, period=ATR_PERIOD, sequential=True)
rsi_arr  = ta.rsi(candles, period=14, sequential=True)

# Also compute: Bollinger bandwidth as a proxy for "choppiness"
bb = ta.bollinger_bands(candles, period=20, sequential=True)
bb_width = (bb.upperband - bb.lowerband) / bb.middleband  # normalized bandwidth

print(f"Indicators computed.")

# ─── Helper Functions ────────────────────────────────────────────────────────
def get_utc_hour(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).hour

def get_session(hour):
    if 0 <= hour < 8:   return 'Tokyo'
    elif 8 <= hour < 13: return 'London'
    elif 13 <= hour < 17: return 'Overlap'
    elif 17 <= hour < 22: return 'NY'
    else:                 return 'Off'

def atr_percentile(idx, lookback=1000):
    start = max(0, idx - lookback)
    window = atr_arr[start:idx+1]
    window = window[~np.isnan(window)]
    if len(window) < 50:
        return 50.0
    return (np.sum(window < atr_arr[idx]) / len(window)) * 100.0

def range_ratio(idx, lookback=50):
    """Recent price range / ATR — high means trending, low means chopping."""
    start = max(0, idx - lookback)
    recent_range = np.max(highs[start:idx+1]) - np.min(lows[start:idx+1])
    if np.isnan(atr_arr[idx]) or atr_arr[idx] <= 0:
        return 1.0
    return recent_range / atr_arr[idx]

def bar_range_ratio(idx, lookback=20):
    """Avg bar range / ATR over recent bars — measures if bars are big or small."""
    start = max(0, idx - lookback)
    bar_ranges = highs[start:idx+1] - lows[start:idx+1]
    avg_bar_range = np.mean(bar_ranges)
    if np.isnan(atr_arr[idx]) or atr_arr[idx] <= 0:
        return 1.0
    return avg_bar_range / atr_arr[idx]

# ─── Simulate one level (returns rich data) ──────────────────────────────────
def simulate_level(entry_price, direction, tp_dist, hedge_dist, start_bar):
    if direction == 'long':
        tp_price = entry_price + tp_dist
        sl_price = entry_price - hedge_dist
    else:
        tp_price = entry_price - tp_dist
        sl_price = entry_price + hedge_dist

    max_bar = min(start_bar + MAX_BARS_PER_LEVEL, len(highs))

    for j in range(start_bar, max_bar):
        h, l = highs[j], lows[j]
        if direction == 'long':
            if l <= sl_price and h >= tp_price:
                return ('sl', j, sl_price)
            if h >= tp_price:
                return ('tp', j)
            if l <= sl_price:
                return ('sl', j, sl_price)
        else:
            if h >= sl_price and l <= tp_price:
                return ('sl', j, sl_price)
            if l <= tp_price:
                return ('tp', j)
            if h >= sl_price:
                return ('sl', j, sl_price)

    return ('timeout', max_bar - 1)


# ─── Full cycle simulation with rich metadata ────────────────────────────────
def simulate_full_cycle(entry_bar, initial_direction):
    entry_price = closes[entry_bar]
    direction = initial_direction
    current_bar = entry_bar + 1
    total_pnl = 0.0
    level_results = []

    for level in range(MAX_LEVELS):
        current_atr = atr_arr[min(current_bar, len(atr_arr)-1)]
        if np.isnan(current_atr) or current_atr <= 0:
            current_atr = atr_arr[entry_bar]
        if np.isnan(current_atr) or current_atr <= 0:
            return None

        tp_dist = current_atr * TP_ATR_MULTIPLE
        hedge_dist = tp_dist / RISK_REWARD
        size = BASE_SIZE * (MULTIPLIER ** level)
        tp_pips = tp_dist / PIP_SIZE
        sl_pips = hedge_dist / PIP_SIZE

        result = simulate_level(entry_price, direction, tp_dist, hedge_dist, current_bar)

        level_data = {
            'level': level,
            'direction': direction,
            'entry_price': entry_price,
            'entry_bar': current_bar,
            'size': size,
            'tp_pips': tp_pips,
            'sl_pips': sl_pips,
            'tp_dist': tp_dist,
            'hedge_dist': hedge_dist,
            'atr_at_entry': current_atr,
        }

        if result[0] == 'tp':
            profit = tp_pips * PIP_VALUE * size
            total_pnl += profit
            level_data.update({'outcome': 'tp', 'exit_bar': result[1], 'pnl': profit})
            level_results.append(level_data)
            return {
                'outcome': 'win', 'win_level': level, 'total_pnl': total_pnl,
                'entry_bar': entry_bar, 'end_bar': result[1],
                'bars_taken': result[1] - entry_bar,
                'levels': level_results, 'max_level': level,
            }

        elif result[0] == 'sl':
            loss = sl_pips * PIP_VALUE * size
            total_pnl -= loss
            sl_price = result[2]
            level_data.update({'outcome': 'sl', 'exit_bar': result[1], 'pnl': -loss})
            level_results.append(level_data)
            entry_price = sl_price
            direction = 'short' if direction == 'long' else 'long'
            current_bar = result[1] + 1
            if current_bar >= len(highs):
                return None

        elif result[0] == 'timeout':
            return None

    return {
        'outcome': 'bust', 'win_level': -1, 'total_pnl': total_pnl,
        'entry_bar': entry_bar, 'end_bar': level_results[-1]['exit_bar'],
        'bars_taken': level_results[-1]['exit_bar'] - entry_bar,
        'levels': level_results, 'max_level': MAX_LEVELS - 1,
    }


# ─── Find signals and run simulation ─────────────────────────────────────────
print("Finding EMA crossover signals...")
min_start = max(ATR_PERIOD + 5, EMA_SLOW + 5)
signals = []
for i in range(min_start, len(candles) - MAX_BARS_PER_LEVEL):
    if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]) or np.isnan(ema_fast[i-1]) or np.isnan(ema_slow[i-1]):
        continue
    if np.isnan(atr_arr[i]) or atr_arr[i] <= 0:
        continue
    if ema_fast[i-1] <= ema_slow[i-1] and ema_fast[i] > ema_slow[i]:
        signals.append((i, 'long'))
    elif ema_fast[i-1] >= ema_slow[i-1] and ema_fast[i] < ema_slow[i]:
        signals.append((i, 'short'))

print(f"Total signals: {len(signals):,}")

print("Simulating full hedge cycles (non-overlapping)...")
cycles = []
next_allowed = 0
for bar, direction in signals:
    if bar < next_allowed:
        continue
    result = simulate_full_cycle(bar, direction)
    if result is None:
        continue
    # Attach market context at cycle entry
    result['entry_session'] = get_session(get_utc_hour(timestamps[bar]))
    result['entry_atr_pctile'] = atr_percentile(bar)
    result['entry_atr'] = atr_arr[bar]
    result['entry_rsi'] = rsi_arr[bar] if not np.isnan(rsi_arr[bar]) else 50.0
    result['entry_range_ratio'] = range_ratio(bar)
    result['entry_bar_range_ratio'] = bar_range_ratio(bar)
    result['entry_bb_width'] = bb_width[bar] if not np.isnan(bb_width[bar]) else 0.02
    result['entry_direction'] = direction
    cycles.append(result)
    next_allowed = result['end_bar'] + 1

n_total = len(cycles)
print(f"Completed cycles: {n_total:,}")

wins = [c for c in cycles if c['outcome'] == 'win']
busts = [c for c in cycles if c['outcome'] == 'bust']
n_wins = len(wins)
n_busts = len(busts)

print(f"Wins: {n_wins} ({n_wins/n_total*100:.1f}%), Busts: {n_busts} ({n_busts/n_total*100:.1f}%)")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 1: CONDITIONAL WIN PROBABILITY AT EACH LEVEL
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ANALYSIS 1: CONDITIONAL PROBABILITIES — P(win | reached level N)")
print("=" * 80)

# For each level N, count:
#   - How many cycles REACHED level N (i.e., max_level >= N)
#   - How many of those WON at level N
#   - How many went deeper (lost at level N → reached N+1)

print(f"\n  {'Level':<8} {'Reached':<10} {'Won Here':<12} {'Lost→Deeper':<14} {'P(win|here)':<14} {'P(loss|here)':<14}")
print(f"  {'-'*70}")

reached_counts = []
won_here_counts = []
lost_here_counts = []

for lvl in range(MAX_LEVELS):
    reached = sum(1 for c in cycles if c['max_level'] >= lvl)
    won_at = sum(1 for c in wins if c['win_level'] == lvl)
    # Lost at this level = reached this level but didn't win here
    # (they either won at a deeper level or busted)
    lost_at = reached - won_at  # those who reached this level but went deeper or busted at this level

    # More precisely: lost at this level = went deeper to level N+1
    if lvl < MAX_LEVELS - 1:
        went_deeper = sum(1 for c in cycles if c['max_level'] >= lvl + 1)
    else:
        # At last level, "lost" = bust
        went_deeper = n_busts

    p_win = won_at / reached if reached > 0 else 0
    p_loss = went_deeper / reached if reached > 0 else 0

    reached_counts.append(reached)
    won_here_counts.append(won_at)
    lost_here_counts.append(went_deeper)

    print(f"  L{lvl:<7} {reached:<10} {won_at:<12} {went_deeper:<14} {p_win:<14.4f} {p_loss:<14.4f}")

# Key insight: P(win at last level)
if reached_counts[-1] > 0:
    p_last_leg_win = won_here_counts[-1] / reached_counts[-1]
    print(f"\n  >>> LAST LEG (L{MAX_LEVELS-1}) WIN RATE: {p_last_leg_win:.4f} ({p_last_leg_win*100:.1f}%) <<<")
    print(f"  >>> When L{MAX_LEVELS-1} triggers, {won_here_counts[-1]} of {reached_counts[-1]} cycles are SAVED <<<")
    print(f"  >>> But {n_busts} of {reached_counts[-1]} become CATASTROPHIC BUSTS <<<")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 2: TRANSITION MATRIX — Markov chain of level progression
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ANALYSIS 2: TRANSITION MATRIX — P(next state | current level)")
print("=" * 80)

print(f"\n  From each level, probability of: winning (EXIT) vs losing (→ next level)")
print(f"\n  {'From':<8} {'→ WIN (exit)':<16} {'→ Next Level':<16} {'→ BUST':<12}")
print(f"  {'-'*50}")

for lvl in range(MAX_LEVELS):
    reached = reached_counts[lvl]
    if reached == 0:
        continue
    won = won_here_counts[lvl]
    p_win = won / reached

    if lvl < MAX_LEVELS - 1:
        lost = lost_here_counts[lvl]
        p_next = lost / reached
        print(f"  L{lvl:<7} {p_win:<16.4f} {p_next:<16.4f} {'—':<12}")
    else:
        p_bust = n_busts / reached
        print(f"  L{lvl:<7} {p_win:<16.4f} {'—':<16} {p_bust:<12.4f}")

# Cumulative: P(reaching each level from L0)
print(f"\n  Cumulative: P(reaching level N starting from L0)")
print(f"  {'Level':<8} {'P(reach)':<12} {'Interpretation'}")
print(f"  {'-'*60}")
for lvl in range(MAX_LEVELS):
    p_reach = reached_counts[lvl] / n_total
    interp = ""
    if lvl == 0:
        interp = "Every cycle starts here"
    elif lvl == MAX_LEVELS - 1:
        interp = f"→ {p_reach*100:.1f}% of cycles face the last stand"
    else:
        interp = f"1 in {1/p_reach:.0f} cycles" if p_reach > 0 else "Never"
    print(f"  L{lvl:<7} {p_reach:<12.4f} {interp}")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 3: MARKET CONDITIONS — Bust vs Win profiling
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ANALYSIS 3: MARKET CONDITIONS AT CYCLE ENTRY — Bust vs Win")
print("=" * 80)

def stats_for_group(group, field):
    vals = [c[field] for c in group if field in c and not np.isnan(c[field])]
    if len(vals) == 0:
        return 0, 0, 0
    return np.mean(vals), np.median(vals), np.std(vals)

fields = [
    ('entry_atr_pctile', 'ATR Percentile'),
    ('entry_atr', 'ATR Value'),
    ('entry_rsi', 'RSI(14)'),
    ('entry_range_ratio', 'Range/ATR (50 bars)'),
    ('entry_bar_range_ratio', 'BarRange/ATR (20 bars)'),
    ('entry_bb_width', 'Bollinger Width'),
    ('bars_taken', 'Duration (bars)'),
]

print(f"\n  {'Metric':<25} {'Win Mean':<12} {'Win Med':<12} {'Bust Mean':<12} {'Bust Med':<12} {'Diff %':<10}")
print(f"  {'-'*80}")

for field, label in fields:
    w_mean, w_med, w_std = stats_for_group(wins, field)
    b_mean, b_med, b_std = stats_for_group(busts, field)
    diff_pct = ((b_mean - w_mean) / w_mean * 100) if w_mean != 0 else 0
    print(f"  {label:<25} {w_mean:<12.3f} {w_med:<12.3f} {b_mean:<12.3f} {b_med:<12.3f} {diff_pct:<+10.1f}%")

# Session distribution: bust rate by session
print(f"\n  Bust rate by entry session:")
print(f"  {'Session':<12} {'Total':<8} {'Busts':<8} {'P(bust)':<10}")
print(f"  {'-'*38}")
for sess in ['Tokyo', 'London', 'Overlap', 'NY', 'Off']:
    sess_cycles = [c for c in cycles if c['entry_session'] == sess]
    sess_busts = [c for c in sess_cycles if c['outcome'] == 'bust']
    n_s = len(sess_cycles)
    n_b = len(sess_busts)
    p_b = n_b / n_s if n_s > 0 else 0
    print(f"  {sess:<12} {n_s:<8} {n_b:<8} {p_b:<10.4f}")

# Direction distribution
print(f"\n  Bust rate by initial direction:")
for d in ['long', 'short']:
    d_cycles = [c for c in cycles if c['entry_direction'] == d]
    d_busts = [c for c in d_cycles if c['outcome'] == 'bust']
    n_d = len(d_cycles)
    n_b = len(d_busts)
    p_b = n_b / n_d if n_d > 0 else 0
    print(f"  {d:<12} Total: {n_d}, Busts: {n_b}, P(bust): {p_b:.4f}")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 4: DEEP CYCLES (L3+) — What makes them bust vs recover?
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ANALYSIS 4: DEEP CYCLES (reached L3+) — What separates bust from recovery?")
print("=" * 80)

deep_cycles = [c for c in cycles if c['max_level'] >= 3]
deep_wins = [c for c in deep_cycles if c['outcome'] == 'win']
deep_busts = [c for c in deep_cycles if c['outcome'] == 'bust']

print(f"\n  Cycles reaching L3+: {len(deep_cycles)} ({len(deep_cycles)/n_total*100:.1f}% of all)")
print(f"  Of those: {len(deep_wins)} recovered ({len(deep_wins)/len(deep_cycles)*100:.1f}%), "
      f"{len(deep_busts)} busted ({len(deep_busts)/len(deep_cycles)*100:.1f}%)")

if len(deep_wins) > 0 and len(deep_busts) > 0:
    print(f"\n  Comparing deep-cycle WINS vs BUSTS:")
    print(f"  {'Metric':<25} {'Recovered':<14} {'Busted':<14} {'Significant?'}")
    print(f"  {'-'*65}")

    for field, label in fields:
        dw_vals = [c[field] for c in deep_wins if field in c and not np.isnan(c.get(field, float('nan')))]
        db_vals = [c[field] for c in deep_busts if field in c and not np.isnan(c.get(field, float('nan')))]
        if len(dw_vals) > 0 and len(db_vals) > 0:
            dw_mean = np.mean(dw_vals)
            db_mean = np.mean(db_vals)
            diff = abs(db_mean - dw_mean) / dw_mean * 100 if dw_mean != 0 else 0
            sig = "YES" if diff > 15 else "maybe" if diff > 8 else "no"
            print(f"  {label:<25} {dw_mean:<14.3f} {db_mean:<14.3f} {sig} ({diff:.0f}% diff)")

    # Session breakdown for deep cycles
    print(f"\n  Deep cycle (L3+) bust rate by session:")
    for sess in ['Tokyo', 'London', 'Overlap', 'NY', 'Off']:
        s_deep = [c for c in deep_cycles if c['entry_session'] == sess]
        s_bust = [c for c in s_deep if c['outcome'] == 'bust']
        if len(s_deep) > 0:
            print(f"    {sess:<12} {len(s_deep)} deep, {len(s_bust)} busted ({len(s_bust)/len(s_deep)*100:.1f}%)")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 5: BUST CLUSTERING — Serial correlation
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ANALYSIS 5: BUST CLUSTERING — Do busts come in bunches?")
print("=" * 80)

outcomes = [1 if c['outcome'] == 'bust' else 0 for c in cycles]
outcomes_arr = np.array(outcomes)

# P(bust | previous was bust)
bust_after_bust = 0
bust_after_win = 0
win_after_bust = 0
win_after_win = 0

for i in range(1, len(outcomes)):
    if outcomes[i-1] == 1:  # previous was bust
        if outcomes[i] == 1:
            bust_after_bust += 1
        else:
            win_after_bust += 1
    else:  # previous was win
        if outcomes[i] == 1:
            bust_after_win += 1
        else:
            win_after_win += 1

total_after_bust = bust_after_bust + win_after_bust
total_after_win = bust_after_win + win_after_win

p_bust_after_bust = bust_after_bust / total_after_bust if total_after_bust > 0 else 0
p_bust_after_win = bust_after_win / total_after_win if total_after_win > 0 else 0

print(f"\n  P(bust | previous bust):  {p_bust_after_bust:.4f}  (n={total_after_bust})")
print(f"  P(bust | previous win):   {p_bust_after_win:.4f}  (n={total_after_win})")
print(f"  Unconditional P(bust):    {n_busts/n_total:.4f}")

if total_after_bust > 0:
    clustering_ratio = p_bust_after_bust / p_bust_after_win if p_bust_after_win > 0 else float('inf')
    print(f"\n  Clustering ratio: {clustering_ratio:.2f}x")
    if clustering_ratio > 1.5:
        print(f"  >>> BUSTS CLUSTER! After a bust, next cycle is {clustering_ratio:.1f}x more likely to bust <<<")
    elif clustering_ratio > 1.1:
        print(f"  >>> Mild clustering detected ({clustering_ratio:.2f}x) <<<")
    else:
        print(f"  >>> No significant clustering — busts appear independent <<<")

# Longer lookback: P(bust | bust in last N cycles)
print(f"\n  P(bust) conditional on recent history:")
print(f"  {'Condition':<35} {'P(bust)':<10} {'N':<8}")
print(f"  {'-'*53}")

for lookback in [2, 3, 5, 10]:
    bust_given_recent = 0
    count_given_recent = 0
    no_bust_given_recent = 0
    count_no_recent = 0

    for i in range(lookback, len(outcomes)):
        recent_busts = sum(outcomes[i-lookback:i])
        if recent_busts > 0:
            count_given_recent += 1
            if outcomes[i] == 1:
                bust_given_recent += 1
        else:
            count_no_recent += 1
            if outcomes[i] == 1:
                no_bust_given_recent += 1

    p_with = bust_given_recent / count_given_recent if count_given_recent > 0 else 0
    p_without = no_bust_given_recent / count_no_recent if count_no_recent > 0 else 0
    print(f"  Bust in last {lookback} cycles:  yes   {p_with:<10.4f} {count_given_recent:<8}")
    print(f"  {'':35} no    {p_without:<10.4f} {count_no_recent:<8}")

# Gaps between busts
bust_indices = [i for i, c in enumerate(cycles) if c['outcome'] == 'bust']
if len(bust_indices) > 1:
    gaps = np.diff(bust_indices)
    print(f"\n  Gaps between consecutive busts (in cycles):")
    print(f"  Min: {np.min(gaps)}, Max: {np.max(gaps)}, Mean: {np.mean(gaps):.1f}, Median: {np.median(gaps):.1f}")
    print(f"  Gaps < 3 cycles: {np.sum(gaps < 3)} ({np.sum(gaps < 3)/len(gaps)*100:.1f}%)")
    print(f"  Gaps < 5 cycles: {np.sum(gaps < 5)} ({np.sum(gaps < 5)/len(gaps)*100:.1f}%)")
    print(f"  Gaps < 10 cycles: {np.sum(gaps < 10)} ({np.sum(gaps < 10)/len(gaps)*100:.1f}%)")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 6: LAST LEG DEEP DIVE — What happens at L4?
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ANALYSIS 6: LAST LEG (L4) DEEP DIVE")
print("=" * 80)

l4_cycles = [c for c in cycles if c['max_level'] >= MAX_LEVELS - 1]
l4_wins = [c for c in l4_cycles if c['outcome'] == 'win' and c['win_level'] == MAX_LEVELS - 1]
l4_busts = [c for c in l4_cycles if c['outcome'] == 'bust']

print(f"\n  Cycles reaching L{MAX_LEVELS-1}: {len(l4_cycles)}")
print(f"  Won at L{MAX_LEVELS-1}: {len(l4_wins)} ({len(l4_wins)/len(l4_cycles)*100:.1f}%)")
print(f"  Busted: {len(l4_busts)} ({len(l4_busts)/len(l4_cycles)*100:.1f}%)")

if len(l4_wins) > 0 and len(l4_busts) > 0:
    # P&L comparison: what do we gain from L4 wins vs what we lose from busts?
    l4_win_pnls = [c['total_pnl'] for c in l4_wins]
    l4_bust_pnls = [c['total_pnl'] for c in l4_busts]

    print(f"\n  L{MAX_LEVELS-1} WIN stats:")
    print(f"    Avg cycle P&L:  ${np.mean(l4_win_pnls):,.2f}")
    print(f"    Total profit from L{MAX_LEVELS-1} saves: ${sum(l4_win_pnls):,.2f}")

    print(f"\n  BUST stats:")
    print(f"    Avg cycle P&L:  ${np.mean(l4_bust_pnls):,.2f}")
    print(f"    Total loss from busts: ${sum(l4_bust_pnls):,.2f}")

    print(f"\n  NET from all L{MAX_LEVELS-1} events: ${sum(l4_win_pnls) + sum(l4_bust_pnls):,.2f}")
    net_l4 = sum(l4_win_pnls) + sum(l4_bust_pnls)
    if net_l4 < 0:
        print(f"  >>> L{MAX_LEVELS-1} is NET NEGATIVE — the wins don't cover the busts! <<<")
        print(f"  >>> Would be BETTER to abort before L{MAX_LEVELS-1} in ALL cases <<<")
    else:
        print(f"  >>> L{MAX_LEVELS-1} is NET POSITIVE — the saves outweigh the busts <<<")

    # What about aborting at L3 instead?
    print(f"\n  THOUGHT EXPERIMENT: What if we aborted at L3 (never entered L{MAX_LEVELS-1})?")
    # If we abort at L3, we take the cumulative loss up to L3
    abort_losses = []
    for c in l4_cycles:
        # Sum of losses from L0 to L3 (first 4 levels)
        cum_loss = sum(lvl['pnl'] for lvl in c['levels'][:MAX_LEVELS-1] if lvl['outcome'] == 'sl')
        abort_losses.append(cum_loss)

    avg_abort_loss = np.mean(abort_losses)
    total_abort_loss = sum(abort_losses)

    # Compare: abort everyone at L3 vs play L4
    actual_l4_total = sum(l4_win_pnls) + sum(l4_bust_pnls)
    print(f"    Abort at L3 total loss: ${total_abort_loss:,.2f} (avg ${avg_abort_loss:,.2f} per cycle)")
    print(f"    Play L4 total P&L:      ${actual_l4_total:,.2f}")
    print(f"    Difference:             ${actual_l4_total - total_abort_loss:,.2f}")

    if actual_l4_total > total_abort_loss:
        print(f"    >>> Playing L{MAX_LEVELS-1} is BETTER than aborting at L3 by ${actual_l4_total - total_abort_loss:,.2f} <<<")
    else:
        print(f"    >>> Aborting at L3 SAVES ${total_abort_loss - actual_l4_total:,.2f} vs playing L{MAX_LEVELS-1} <<<")

    # ATR at L4 entry vs L0 entry — has volatility shifted?
    print(f"\n  Volatility shift from L0 to L{MAX_LEVELS-1}:")
    for c in l4_cycles[:5]:  # show first 5 examples
        l0_atr = c['levels'][0]['atr_at_entry']
        l4_atr = c['levels'][-1]['atr_at_entry']
        shift = (l4_atr - l0_atr) / l0_atr * 100
        outcome = "WIN" if c['outcome'] == 'win' else "BUST"
        print(f"    L0 ATR: {l0_atr:.6f} → L{MAX_LEVELS-1} ATR: {l4_atr:.6f} ({shift:+.1f}%) [{outcome}]")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 7: P&L CONTRIBUTION BY LEVEL — Where does the money come from?
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("ANALYSIS 7: P&L CONTRIBUTION BY WIN LEVEL")
print("=" * 80)

print(f"\n  {'Win Level':<12} {'Count':<8} {'Avg P&L':<14} {'Total P&L':<16} {'% of Gross':<12}")
print(f"  {'-'*62}")

total_gross_profit = 0
level_contributions = {}
for lvl in range(MAX_LEVELS):
    lvl_wins = [c for c in wins if c['win_level'] == lvl]
    if len(lvl_wins) > 0:
        pnls = [c['total_pnl'] for c in lvl_wins]
        total = sum(pnls)
        total_gross_profit += total
        level_contributions[lvl] = total

for lvl in range(MAX_LEVELS):
    lvl_wins = [c for c in wins if c['win_level'] == lvl]
    if len(lvl_wins) > 0:
        pnls_list = [c['total_pnl'] for c in lvl_wins]
        total = sum(pnls_list)
        pct = total / total_gross_profit * 100 if total_gross_profit > 0 else 0
        print(f"  L{lvl} win    {len(lvl_wins):<8} ${np.mean(pnls_list):<13,.2f} ${total:<15,.2f} {pct:.1f}%")

bust_total = sum(c['total_pnl'] for c in busts)
print(f"  {'BUST':<12} {n_busts:<8} ${np.mean([c['total_pnl'] for c in busts]) if n_busts > 0 else 0:<13,.2f} ${bust_total:<15,.2f} —")

net_total = total_gross_profit + bust_total
print(f"\n  Gross profit from wins: ${total_gross_profit:,.2f}")
print(f"  Total bust losses:      ${bust_total:,.2f}")
print(f"  NET:                    ${net_total:,.2f}")


# ══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════════════════════
plt.style.use('seaborn-v0_8-darkgrid')

# ─── Chart 1: 4-panel deep analysis ──────────────────────────────────────────
fig = plt.figure(figsize=(20, 16))
gs = gridspec.GridSpec(3, 2, hspace=0.35, wspace=0.3)

# Panel 1: Conditional P(win | reached level N)
ax = fig.add_subplot(gs[0, 0])
levels_x = list(range(MAX_LEVELS))
p_wins = [won_here_counts[i] / reached_counts[i] if reached_counts[i] > 0 else 0 for i in levels_x]
p_losses = [1 - p for p in p_wins]
bar_width = 0.35
bars1 = ax.bar([x - bar_width/2 for x in levels_x], p_wins, bar_width, label='P(win here)', color='#2ecc71', edgecolor='black')
bars2 = ax.bar([x + bar_width/2 for x in levels_x], p_losses, bar_width, label='P(lose → deeper)', color='#e74c3c', edgecolor='black')
for i, (pw, pl) in enumerate(zip(p_wins, p_losses)):
    ax.text(i - bar_width/2, pw + 0.01, f'{pw:.1%}', ha='center', fontsize=9, fontweight='bold')
    ax.text(i + bar_width/2, pl + 0.01, f'{pl:.1%}', ha='center', fontsize=9)
ax.set_xlabel('Level')
ax.set_ylabel('Probability')
ax.set_title('P(win | reached level N) vs P(lose)', fontsize=12, fontweight='bold')
ax.set_xticks(levels_x)
ax.set_xticklabels([f'L{i}' for i in levels_x])
ax.legend(fontsize=10)
ax.set_ylim(0, 1.05)

# Panel 2: Funnel — how many cycles reach each level
ax = fig.add_subplot(gs[0, 1])
reached_pcts = [r / n_total * 100 for r in reached_counts]
colors_funnel = ['#27ae60', '#2ecc71', '#f39c12', '#e67e22', '#e74c3c']
bars = ax.barh(range(MAX_LEVELS), reached_pcts, color=colors_funnel, edgecolor='black')
for i, (bar, count, pct) in enumerate(zip(bars, reached_counts, reached_pcts)):
    ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
            f'{count} ({pct:.1f}%)', va='center', fontsize=10)
ax.set_yticks(range(MAX_LEVELS))
ax.set_yticklabels([f'L{i}' for i in range(MAX_LEVELS)])
ax.set_xlabel('% of all cycles reaching this level')
ax.set_title('Cycle Depth Funnel', fontsize=12, fontweight='bold')
ax.invert_yaxis()

# Panel 3: Market conditions — bust vs win radar-ish comparison
ax = fig.add_subplot(gs[1, 0])
metrics = ['ATR Pctile', 'Range/ATR', 'BarRange/ATR', 'BB Width', 'RSI']
win_vals = [
    np.mean([c['entry_atr_pctile'] for c in wins]),
    np.mean([c['entry_range_ratio'] for c in wins]),
    np.mean([c['entry_bar_range_ratio'] for c in wins]),
    np.mean([c['entry_bb_width'] for c in wins]) * 100,  # scale up
    np.mean([c['entry_rsi'] for c in wins]),
]
bust_vals = [
    np.mean([c['entry_atr_pctile'] for c in busts]),
    np.mean([c['entry_range_ratio'] for c in busts]),
    np.mean([c['entry_bar_range_ratio'] for c in busts]),
    np.mean([c['entry_bb_width'] for c in busts]) * 100,
    np.mean([c['entry_rsi'] for c in busts]),
]
x_pos = np.arange(len(metrics))
ax.bar(x_pos - 0.2, win_vals, 0.35, label='Win cycles', color='#2ecc71', edgecolor='black')
ax.bar(x_pos + 0.2, bust_vals, 0.35, label='Bust cycles', color='#e74c3c', edgecolor='black')
ax.set_xticks(x_pos)
ax.set_xticklabels(metrics, rotation=15, fontsize=9)
ax.set_title('Market Conditions at Entry: Win vs Bust', fontsize=12, fontweight='bold')
ax.legend()

# Panel 4: Bust clustering — gap distribution
ax = fig.add_subplot(gs[1, 1])
if len(bust_indices) > 1:
    gaps = np.diff(bust_indices)
    ax.hist(gaps, bins=min(30, len(gaps)), color='#e74c3c', edgecolor='black', alpha=0.8)
    ax.axvline(x=np.mean(gaps), color='blue', linestyle='--', label=f'Mean: {np.mean(gaps):.1f} cycles')
    ax.axvline(x=np.median(gaps), color='green', linestyle='--', label=f'Median: {np.median(gaps):.1f} cycles')
    ax.set_xlabel('Cycles between consecutive busts')
    ax.set_ylabel('Frequency')
    ax.set_title('Bust Gap Distribution (clustering analysis)', fontsize=12, fontweight='bold')
    ax.legend()
else:
    ax.text(0.5, 0.5, 'Not enough busts for gap analysis', ha='center', va='center', transform=ax.transAxes)

# Panel 5: Last leg analysis — L4 wins vs busts P&L
ax = fig.add_subplot(gs[2, 0])
if len(l4_wins) > 0 and len(l4_busts) > 0:
    l4_w_pnls = [c['total_pnl'] for c in l4_wins]
    l4_b_pnls = [c['total_pnl'] for c in l4_busts]
    # Box plot
    bp = ax.boxplot([l4_w_pnls, l4_b_pnls], labels=[f'L{MAX_LEVELS-1} Win', 'Bust'],
                     patch_artist=True, widths=0.5)
    bp['boxes'][0].set_facecolor('#2ecc71')
    bp['boxes'][1].set_facecolor('#e74c3c')
    ax.axhline(y=0, color='black', linestyle=':', alpha=0.5)
    ax.set_ylabel('Cycle P&L ($)')
    ax.set_title(f'Last Leg Outcomes: L{MAX_LEVELS-1} Win vs Bust', fontsize=12, fontweight='bold')

    # Annotate
    ax.text(0.98, 0.02, f'L{MAX_LEVELS-1} Win Rate: {len(l4_wins)}/{len(l4_cycles)} = {len(l4_wins)/len(l4_cycles)*100:.1f}%',
            transform=ax.transAxes, ha='right', fontsize=10,
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

# Panel 6: P&L contribution by level (stacked)
ax = fig.add_subplot(gs[2, 1])
level_labels = [f'L{i} Win' for i in range(MAX_LEVELS)] + ['Bust']
level_totals = []
for lvl in range(MAX_LEVELS):
    lvl_w = [c for c in wins if c['win_level'] == lvl]
    level_totals.append(sum(c['total_pnl'] for c in lvl_w) if lvl_w else 0)
level_totals.append(bust_total)

colors_contrib = ['#27ae60', '#2ecc71', '#82e0aa', '#f9e79f', '#f5b041', '#e74c3c']
bars = ax.bar(range(len(level_labels)), level_totals, color=colors_contrib[:len(level_labels)], edgecolor='black')
for i, (bar, val) in enumerate(zip(bars, level_totals)):
    va = 'bottom' if val >= 0 else 'top'
    ax.text(bar.get_x() + bar.get_width()/2, val, f'${val:,.0f}', ha='center', va=va, fontsize=9, fontweight='bold')
ax.axhline(y=0, color='black', linewidth=0.8)
ax.set_xticks(range(len(level_labels)))
ax.set_xticklabels(level_labels, rotation=15, fontsize=9)
ax.set_ylabel('Total P&L ($)')
ax.set_title('P&L Contribution by Resolution Level', fontsize=12, fontweight='bold')

plt.suptitle('Surefire V2: Deep Bust Anatomy — EUR-USD 5m (2024-2026)',
             fontsize=15, fontweight='bold', y=1.01)
fig.savefig(f'{OUTPUT_DIR}/07_bust_anatomy.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUTPUT_DIR}/07_bust_anatomy.png")


# ─── Chart 2: Session x Bust heatmap ─────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# Session x Level heatmap
ax = axes[0]
sessions = ['Tokyo', 'London', 'Overlap', 'NY', 'Off']
heatmap_data = np.zeros((len(sessions), MAX_LEVELS + 1))  # +1 for bust column
for si, sess in enumerate(sessions):
    sess_cycles_list = [c for c in cycles if c['entry_session'] == sess]
    n_sess = len(sess_cycles_list)
    if n_sess == 0:
        continue
    for lvl in range(MAX_LEVELS):
        wins_at = sum(1 for c in sess_cycles_list if c['outcome'] == 'win' and c['win_level'] == lvl)
        heatmap_data[si, lvl] = wins_at / n_sess * 100
    busts_at = sum(1 for c in sess_cycles_list if c['outcome'] == 'bust')
    heatmap_data[si, MAX_LEVELS] = busts_at / n_sess * 100

col_labels = [f'L{i} Win' for i in range(MAX_LEVELS)] + ['Bust']
im = ax.imshow(heatmap_data, cmap='RdYlGn_r', aspect='auto')
ax.set_xticks(range(MAX_LEVELS + 1))
ax.set_xticklabels(col_labels, rotation=30, fontsize=9)
ax.set_yticks(range(len(sessions)))
ax.set_yticklabels(sessions)
for i in range(len(sessions)):
    for j in range(MAX_LEVELS + 1):
        ax.text(j, i, f'{heatmap_data[i,j]:.1f}%', ha='center', va='center', fontsize=9,
                color='white' if heatmap_data[i,j] > 20 else 'black')
ax.set_title('Outcome Distribution by Session (%)', fontsize=12, fontweight='bold')
plt.colorbar(im, ax=ax, label='%')

# Bust rate over time (rolling)
ax = axes[1]
window = 50
outcomes_arr_float = outcomes_arr.astype(float)
if len(outcomes_arr_float) >= window:
    rolling_bust = np.convolve(outcomes_arr_float, np.ones(window)/window, mode='valid')
    ax.plot(range(len(rolling_bust)), rolling_bust * 100, color='#e74c3c', linewidth=1.5)
    ax.axhline(y=n_busts/n_total*100, color='blue', linestyle='--', alpha=0.5,
               label=f'Overall: {n_busts/n_total*100:.1f}%')
    ax.set_xlabel('Cycle #')
    ax.set_ylabel('Rolling P(bust) %')
    ax.set_title(f'Rolling Bust Rate ({window}-cycle window)', fontsize=12, fontweight='bold')
    ax.legend()
    ax.set_ylim(0, max(rolling_bust * 100) * 1.3)

plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/07_bust_session_heatmap.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/07_bust_session_heatmap.png")


# ─── Final Summary ───────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("FINAL SUMMARY — KEY INSIGHTS")
print("=" * 80)

print(f"""
  1. CONDITIONAL WIN PROBABILITIES:
     L0: {won_here_counts[0]/reached_counts[0]*100:.1f}% win  |  L1: {won_here_counts[1]/reached_counts[1]*100:.1f}% win  |  L2: {won_here_counts[2]/reached_counts[2]*100:.1f}% win  |  L3: {won_here_counts[3]/reached_counts[3]*100:.1f}% win  |  L4: {won_here_counts[4]/reached_counts[4]*100:.1f}% win

  2. FUNNEL: {reached_counts[0]} → {reached_counts[1]} → {reached_counts[2]} → {reached_counts[3]} → {reached_counts[4]} (cycles reaching each level)

  3. LAST LEG (L{MAX_LEVELS-1}):
     {len(l4_cycles)} cycles reached L{MAX_LEVELS-1}
     {len(l4_wins)} saved ({len(l4_wins)/len(l4_cycles)*100:.1f}%), {len(l4_busts)} busted ({len(l4_busts)/len(l4_cycles)*100:.1f}%)
     Net from L{MAX_LEVELS-1} events: ${sum(c['total_pnl'] for c in l4_cycles):,.2f}

  4. CLUSTERING: P(bust|prev bust) = {p_bust_after_bust:.4f} vs P(bust|prev win) = {p_bust_after_win:.4f}
     Ratio: {clustering_ratio:.2f}x

  5. KEY MARKET DIFFERENCES (Bust vs Win at entry):
""")

for field, label in fields[:3]:
    w_mean = np.mean([c[field] for c in wins])
    b_mean = np.mean([c[field] for c in busts])
    diff = (b_mean - w_mean) / w_mean * 100 if w_mean != 0 else 0
    print(f"     {label}: Win={w_mean:.2f}, Bust={b_mean:.2f} ({diff:+.1f}%)")

print(f"""
  FILES SAVED:
    {OUTPUT_DIR}/07_bust_anatomy.png
    {OUTPUT_DIR}/07_bust_session_heatmap.png
""")
print("=" * 80)
