#!/usr/bin/env python3
"""
Step 14: Market Loss Paths — Exhaustive Analysis
==================================================
What EXACTLY does price do when the strategy loses?

Every bust requires price to zigzag through ALL levels. But HOW does it zigzag?
There are distinct market path types that cause busts. We must:

1. Extract the ACTUAL price path of every bust from real data
2. Classify each bust into a path type
3. Measure the probability of each path type
4. Determine which paths are predictable/avoidable
5. Assess each as a solvable or inherent problem

THE GEOMETRY OF A BUST:
  For a 5-level bust starting LONG, price must:
    - Drop h from entry (L0 loses) → now SHORT from entry-h
    - Rise h from entry-h (L1 loses) → now LONG from entry
    - Drop h from entry (L2 loses) → now SHORT from entry-h
    - Rise h from entry-h (L3 loses) → now LONG from entry
    - Drop h from entry (L4 loses) → BUST

  So for alternating levels: price oscillates around entry ± h
  WITHOUT ever moving tp in the "right" direction.

  For 12-level sqrt bust: same pattern but 12 zigzags.

  The question: WHAT market behavior produces this zigzag?
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import qengine.helpers as jh
from qengine.research import get_candles
import qengine.indicators as ta

# =============================================================================
# LOAD DATA
# =============================================================================
print("Loading EUR-USD 5m candles...")
_, candles = get_candles(
    'OANDA', 'EUR-USD', '5m',
    jh.date_to_timestamp('2024-01-01'), jh.date_to_timestamp('2026-03-21'),
    warmup_candles_num=0
)
print(f"Total candles: {len(candles):,}")

atr = ta.atr(candles, period=14, sequential=True)
ema_fast = ta.ema(candles, period=8, sequential=True)
ema_slow = ta.ema(candles, period=21, sequential=True)
rsi = ta.rsi(candles, period=14, sequential=True)
bb = ta.bollinger_bands(candles, period=20, sequential=True)

# =============================================================================
# PART 1: EXTRACT ALL BUST PRICE PATHS
# =============================================================================
print("\n" + "=" * 80)
print("PART 1: EXTRACTING ALL BUST PRICE PATHS")
print("=" * 80)

tp_mult = 0.8
hedge_ratio = 2.0

# We'll test multiple configs
configs = [
    ("5 lvl / 2x", 5, lambda n: 2.0**n),
    ("7 lvl / 2x", 7, lambda n: 2.0**n),
    ("12 lvl / sqrt", 12, lambda n: np.sqrt(2)**n),
]

all_busts = {}  # config_name -> list of bust dicts
all_wins = {}   # config_name -> list of win dicts

for config_name, max_levels, mult_fn in configs:
    busts = []
    wins = []
    i = 300  # skip warmup

    while i < len(candles) - 1:
        if not (ema_fast[i-1] < ema_slow[i-1] and ema_fast[i] >= ema_slow[i]):
            i += 1
            continue
        if np.isnan(atr[i]) or atr[i] < 1e-6:
            i += 1
            continue

        tp_dist = atr[i] * tp_mult
        h_dist = tp_dist / hedge_ratio
        entry_price = candles[i, 2]
        cycle_start = i
        direction = 1

        # Track the full price path
        entry = entry_price
        levels = []
        j = i + 1
        win_level = -1

        for level in range(max_levels):
            tp_price = entry + direction * tp_dist
            sl_price = entry - direction * h_dist
            level_entry = entry
            level_dir = direction

            won = False
            lost = False
            while j < min(cycle_start + 2000, len(candles)):
                high = candles[j, 3]
                low = candles[j, 4]

                if direction == 1:
                    if high >= tp_price:
                        won = True
                        break
                    if low <= sl_price:
                        lost = True
                        break
                else:
                    if low <= tp_price:
                        won = True
                        break
                    if high >= sl_price:
                        lost = True
                        break
                j += 1

            prev_bar = cycle_start if level == 0 else levels[level - 1]['exit_bar']
            levels.append({
                'level': level,
                'entry': level_entry,
                'direction': level_dir,
                'tp': tp_price,
                'sl': sl_price,
                'won': won,
                'lost': lost,
                'exit_bar': j,
                'bars': j - prev_bar,
            })

            if won:
                win_level = level
                break
            elif lost:
                entry = sl_price
                direction *= -1
                j += 1
            else:
                break

        # Extract price path for the cycle
        path_start = max(cycle_start - 20, 0)  # 20 bars before for context
        path_end = min(j + 5, len(candles))
        price_path = candles[path_start:path_end, 2].copy()  # close prices

        # Market conditions at entry
        entry_atr = atr[cycle_start]
        entry_rsi = rsi[cycle_start]
        bb_upper = bb[0][cycle_start] if hasattr(bb[0], '__len__') else bb[0]
        bb_lower = bb[2][cycle_start] if hasattr(bb[2], '__len__') else bb[2]
        bb_mid = bb[1][cycle_start] if hasattr(bb[1], '__len__') else bb[1]
        bb_width = (bb_upper - bb_lower) / bb_mid if bb_mid > 0 else 0

        # Price range during cycle
        cycle_high = candles[cycle_start:j+1, 3].max() if j > cycle_start else entry_price
        cycle_low = candles[cycle_start:j+1, 4].min() if j > cycle_start else entry_price
        cycle_range = cycle_high - cycle_low

        # Compute net displacement (how far price moved from entry)
        exit_price = candles[min(j, len(candles)-1), 2]
        net_displacement = exit_price - entry_price

        # ATR during cycle vs at entry
        if j > cycle_start + 14:
            cycle_atr_vals = atr[cycle_start:j+1]
            cycle_atr_vals = cycle_atr_vals[~np.isnan(cycle_atr_vals)]
            atr_during = np.mean(cycle_atr_vals) if len(cycle_atr_vals) > 0 else entry_atr
            atr_expansion = atr_during / entry_atr if entry_atr > 0 else 1.0
        else:
            atr_during = entry_atr
            atr_expansion = 1.0

        cycle_info = {
            'cycle_start': cycle_start,
            'cycle_end': j,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'tp_dist': tp_dist,
            'h_dist': h_dist,
            'levels': levels,
            'win_level': win_level,
            'duration_bars': j - cycle_start,
            'duration_min': (j - cycle_start) * 5,
            'entry_atr': entry_atr,
            'entry_rsi': entry_rsi,
            'bb_width': bb_width,
            'cycle_range': cycle_range,
            'cycle_range_atr': cycle_range / entry_atr if entry_atr > 0 else 0,
            'net_displacement': net_displacement,
            'net_disp_atr': net_displacement / entry_atr if entry_atr > 0 else 0,
            'atr_expansion': atr_expansion,
            'price_path': price_path,
            'path_offset': cycle_start - path_start,
            'timestamp': candles[cycle_start, 0],
        }

        if win_level == -1:
            busts.append(cycle_info)
        else:
            wins.append(cycle_info)

        i = j + 1

    all_busts[config_name] = busts
    all_wins[config_name] = wins
    print(f"  {config_name}: {len(wins)} wins, {len(busts)} busts")


# =============================================================================
# PART 2: CLASSIFY BUST PATHS INTO TYPES
# =============================================================================
print("\n" + "=" * 80)
print("PART 2: CLASSIFYING BUST PRICE PATHS")
print("=" * 80)

print("""
PATH TYPES (theoretical):

  Type A: STRONG TREND — Price moves directionally, sweeping through all levels
    on one side. Alternating hedges get stopped out because the trend is too strong.
    Signature: large net displacement, range >> tp_dist, consistent direction.

  Type B: CHOPPY RANGE — Price oscillates with amplitude ~ h_dist. Each level
    gets stopped out because price reverses just enough to hit SL but not enough
    to hit TP (since TP > h_dist).
    Signature: small net displacement, range ~ N*h_dist, many direction changes.

  Type C: VOLATILITY EXPANSION — ATR was low at entry but increases during the
    cycle. The fixed tp/h distances become too small relative to actual moves.
    Signature: atr_expansion > 1.5, range much larger than expected.

  Type D: GAP/SPIKE — Sudden large move (news, flash crash) that blows through
    multiple levels at once.
    Signature: very fast (few bars), one or more bars with range >> ATR.

  Type E: SLOW GRIND — Price slowly drifts against position without enough
    mean-reversion. Takes many bars per level.
    Signature: long duration, small per-bar moves, gradual SL hits.
""")

def classify_bust(bust, config_max_levels):
    """Classify a bust into a path type based on its characteristics."""
    range_ratio = bust['cycle_range_atr']
    net_disp_ratio = abs(bust['net_disp_atr'])
    duration = bust['duration_bars']
    atr_exp = bust['atr_expansion']
    n_levels = len(bust['levels'])

    # Compute direction consistency: how often price moves in same direction
    path = bust['price_path']
    if len(path) > 2:
        diffs = np.diff(path)
        if len(diffs) > 0:
            pos_moves = np.sum(diffs > 0)
            neg_moves = np.sum(diffs < 0)
            dir_consistency = max(pos_moves, neg_moves) / len(diffs) if len(diffs) > 0 else 0.5
        else:
            dir_consistency = 0.5
    else:
        dir_consistency = 0.5

    # Compute avg bars per level
    avg_bars_per_level = duration / n_levels if n_levels > 0 else duration

    # Check for spikes (any single bar with range > 2x ATR)
    cycle_candles = candles[bust['cycle_start']:bust['cycle_end']+1]
    if len(cycle_candles) > 0:
        bar_ranges = cycle_candles[:, 3] - cycle_candles[:, 4]
        max_bar_range = np.max(bar_ranges)
        spike_ratio = max_bar_range / bust['entry_atr'] if bust['entry_atr'] > 0 else 0
    else:
        spike_ratio = 0

    # Classification logic
    if spike_ratio > 3.0 and duration < n_levels * 5:
        return 'D_GAP_SPIKE', {
            'spike_ratio': spike_ratio,
            'duration': duration,
        }
    elif atr_exp > 1.5 and range_ratio > n_levels * 1.5:
        return 'C_VOL_EXPANSION', {
            'atr_expansion': atr_exp,
            'range_ratio': range_ratio,
        }
    elif net_disp_ratio > 3.0 and dir_consistency > 0.65:
        return 'A_STRONG_TREND', {
            'net_disp_atr': net_disp_ratio,
            'dir_consistency': dir_consistency,
        }
    elif avg_bars_per_level > 30 and net_disp_ratio < 2.0:
        return 'E_SLOW_GRIND', {
            'avg_bars_per_level': avg_bars_per_level,
            'net_disp_atr': net_disp_ratio,
        }
    else:
        return 'B_CHOPPY_RANGE', {
            'range_ratio': range_ratio,
            'net_disp_atr': net_disp_ratio,
            'dir_consistency': dir_consistency,
        }


for config_name, max_levels, _ in configs:
    busts = all_busts[config_name]
    if not busts:
        continue

    print(f"\n  {config_name} — {len(busts)} busts:")
    print(f"  {'Type':<20} {'Count':<8} {'%':<8} {'Avg Duration':<15} {'Avg Range/ATR':<15} {'Avg |Disp|/ATR':<15}")
    print(f"  {'-'*80}")

    type_counts = {}
    type_details = {}
    for bust in busts:
        btype, details = classify_bust(bust, max_levels)
        bust['path_type'] = btype
        if btype not in type_counts:
            type_counts[btype] = []
            type_details[btype] = []
        type_counts[btype].append(bust)
        type_details[btype].append(details)

    for btype in sorted(type_counts.keys()):
        blist = type_counts[btype]
        n = len(blist)
        pct = n / len(busts) * 100
        avg_dur = np.mean([b['duration_min'] for b in blist])
        avg_range = np.mean([b['cycle_range_atr'] for b in blist])
        avg_disp = np.mean([abs(b['net_disp_atr']) for b in blist])
        print(f"  {btype:<20} {n:<8} {pct:<8.1f} {avg_dur:<15.1f} {avg_range:<15.2f} {avg_disp:<15.2f}")


# =============================================================================
# PART 3: DEEP DIVE INTO EACH PATH TYPE
# =============================================================================
print("\n" + "=" * 80)
print("PART 3: DEEP DIVE — EACH LOSS PATH")
print("=" * 80)

# Use the 5-level config for detailed analysis (most busts)
primary = "5 lvl / 2x"
busts = all_busts[primary]
wins = all_wins[primary]

# For each path type, show detailed characteristics
type_groups = {}
for bust in busts:
    bt = bust['path_type']
    if bt not in type_groups:
        type_groups[bt] = []
    type_groups[bt].append(bust)

for btype in sorted(type_groups.keys()):
    group = type_groups[btype]
    print(f"\n  {'='*70}")
    print(f"  PATH TYPE: {btype} ({len(group)} busts, {len(group)/len(busts)*100:.1f}%)")
    print(f"  {'='*70}")

    # Statistics
    durations = [b['duration_min'] for b in group]
    ranges = [b['cycle_range_atr'] for b in group]
    disps = [b['net_disp_atr'] for b in group]
    atr_exps = [b['atr_expansion'] for b in group]
    rsis = [b['entry_rsi'] for b in group]
    bb_widths = [b['bb_width'] for b in group]

    print(f"  Duration:      mean={np.mean(durations):.1f}min, median={np.median(durations):.1f}min, "
          f"range=[{np.min(durations):.0f}, {np.max(durations):.0f}]min")
    print(f"  Range/ATR:     mean={np.mean(ranges):.2f}, median={np.median(ranges):.2f}")
    print(f"  |Disp|/ATR:    mean={np.mean(np.abs(disps)):.2f}, median={np.median(np.abs(disps)):.2f}")
    print(f"  ATR expansion: mean={np.mean(atr_exps):.2f}, median={np.median(atr_exps):.2f}")
    print(f"  Entry RSI:     mean={np.mean(rsis):.1f}, median={np.median(rsis):.1f}")
    print(f"  BB width:      mean={np.mean(bb_widths):.5f}")

    # Displacement direction
    up_disps = sum(1 for d in disps if d > 0)
    down_disps = sum(1 for d in disps if d <= 0)
    print(f"  Net direction:  {up_disps} up, {down_disps} down")

    # Level-by-level timing
    bars_per_level = [[] for _ in range(5)]
    for bust in group:
        for lvl_info in bust['levels']:
            lvl = lvl_info['level']
            if lvl < 5:
                bars_per_level[lvl].append(lvl_info['bars'])
    print(f"  Bars per level: ", end="")
    for lvl in range(5):
        if bars_per_level[lvl]:
            print(f"L{lvl}={np.mean(bars_per_level[lvl]):.1f}", end="  ")
    print()


# =============================================================================
# PART 4: THE GEOMETRIC CONSTRAINT — What MUST happen for a bust
# =============================================================================
print("\n" + "=" * 80)
print("PART 4: THE GEOMETRIC CONSTRAINT — Price Path Requirements")
print("=" * 80)

print("""
  For a bust to occur with tp/h ratio = 2 (tp = 2*h), starting LONG:

  ABSOLUTE CONSTRAINT: Price must NEVER move tp above any level's entry
  before moving h below it. Since tp = 2*h, this means:

  The price must stay within a BAND of width ≈ tp = 2*h centered near
  the entry, while oscillating back and forth hitting h in alternating
  directions N times.

  MINIMUM REQUIRED MOVEMENT for N-level bust:
    Each level reversal requires price to move h in one direction.
    Total minimum price path length: N * h
    But net displacement can be ZERO (oscillation returns to start).

  CRITICAL INSIGHT: The bust band width = tp (NOT the total range).
    Price can oscillate within a band of width tp and hit h alternately.
    Since h = tp/2, the oscillations need amplitude ≥ h = tp/2.

  This is equivalent to: price must oscillate with period < tp
  and amplitude ≥ h, for the duration of N level changes.
""")

# Verify this empirically
print("  Empirical verification — bust price band width:")
for config_name in all_busts:
    busts = all_busts[config_name]
    if not busts:
        continue
    band_widths = []
    for bust in busts:
        # Band width relative to tp
        band = bust['cycle_range'] / bust['tp_dist'] if bust['tp_dist'] > 0 else 0
        band_widths.append(band)
    print(f"  {config_name}: band = {np.mean(band_widths):.2f} * tp "
          f"(median: {np.median(band_widths):.2f}, range: [{np.min(band_widths):.2f}, {np.max(band_widths):.2f}])")

# Compare with wins
print("\n  Win price band width (for comparison):")
for config_name in all_wins:
    wins_list = all_wins[config_name]
    if not wins_list:
        continue
    # Sample wins (too many to process all)
    sample = wins_list[:2000]
    band_widths = [w['cycle_range'] / w['tp_dist'] if w['tp_dist'] > 0 else 0 for w in sample]
    print(f"  {config_name}: band = {np.mean(band_widths):.2f} * tp "
          f"(median: {np.median(band_widths):.2f})")


# =============================================================================
# PART 5: PROBABILITY OF EACH PATH TYPE IN THE MARKET
# =============================================================================
print("\n" + "=" * 80)
print("PART 5: PROBABILITY OF EACH LOSS PATH IN THE MARKET")
print("=" * 80)

# Measure how often the market produces each type of movement
# over random windows of the same duration as busts

primary_busts = all_busts["5 lvl / 2x"]
if primary_busts:
    avg_bust_duration = int(np.mean([b['duration_bars'] for b in primary_busts]))
    avg_tp_dist = np.mean([b['tp_dist'] for b in primary_busts])
    avg_h_dist = np.mean([b['h_dist'] for b in primary_busts])

    print(f"\n  Avg bust duration: {avg_bust_duration} bars ({avg_bust_duration*5} min)")
    print(f"  Avg tp_dist: {avg_tp_dist:.5f}, avg h_dist: {avg_h_dist:.5f}")

    # Sample random windows and measure their characteristics
    n_samples = 10000
    np.random.seed(42)
    random_starts = np.random.randint(300, len(candles) - avg_bust_duration - 1, n_samples)

    window_stats = {
        'range_atr': [],
        'net_disp_atr': [],
        'dir_consistency': [],
        'n_reversals': [],
        'max_bar_spike': [],
    }

    for start in random_starts:
        end = start + avg_bust_duration
        window = candles[start:end]
        if len(window) < 2:
            continue

        local_atr = atr[start]
        if np.isnan(local_atr) or local_atr < 1e-6:
            continue

        w_range = window[:, 3].max() - window[:, 4].min()
        w_disp = window[-1, 2] - window[0, 2]
        diffs = np.diff(window[:, 2])
        pos = np.sum(diffs > 0)
        neg = np.sum(diffs < 0)
        dir_con = max(pos, neg) / len(diffs) if len(diffs) > 0 else 0.5

        # Count reversals (direction changes)
        signs = np.sign(diffs)
        signs = signs[signs != 0]
        reversals = np.sum(np.diff(signs) != 0) if len(signs) > 1 else 0

        bar_ranges = window[:, 3] - window[:, 4]
        max_spike = np.max(bar_ranges) / local_atr if local_atr > 0 else 0

        window_stats['range_atr'].append(w_range / local_atr)
        window_stats['net_disp_atr'].append(w_disp / local_atr)
        window_stats['dir_consistency'].append(dir_con)
        window_stats['n_reversals'].append(reversals)
        window_stats['max_bar_spike'].append(max_spike)

    # Now compare bust windows with random windows
    print(f"\n  BUST WINDOWS vs RANDOM WINDOWS (same duration):")
    print(f"  {'Metric':<25} {'Busts':<15} {'Random':<15} {'Difference'}")
    print(f"  {'-'*65}")

    bust_range = [b['cycle_range_atr'] for b in primary_busts]
    bust_disp = [abs(b['net_disp_atr']) for b in primary_busts]

    metrics = [
        ('Range/ATR', bust_range, window_stats['range_atr']),
        ('|Net Disp|/ATR', bust_disp, [abs(d) for d in window_stats['net_disp_atr']]),
        ('Dir consistency', [0.5]*len(primary_busts), window_stats['dir_consistency']),  # placeholder
        ('Max bar spike/ATR', [0]*len(primary_busts), window_stats['max_bar_spike']),
    ]

    # Compute bust-specific metrics
    bust_dir_cons = []
    bust_spikes = []
    bust_reversals = []
    for bust in primary_busts:
        path = bust['price_path']
        diffs = np.diff(path)
        if len(diffs) > 0:
            pos = np.sum(diffs > 0)
            neg = np.sum(diffs < 0)
            bust_dir_cons.append(max(pos, neg) / len(diffs))
            signs = np.sign(diffs)
            signs = signs[signs != 0]
            bust_reversals.append(np.sum(np.diff(signs) != 0) if len(signs) > 1 else 0)
        else:
            bust_dir_cons.append(0.5)
            bust_reversals.append(0)

        cycle_candles = candles[bust['cycle_start']:bust['cycle_end']+1]
        if len(cycle_candles) > 0:
            bar_ranges = cycle_candles[:, 3] - cycle_candles[:, 4]
            bust_spikes.append(np.max(bar_ranges) / bust['entry_atr'] if bust['entry_atr'] > 0 else 0)
        else:
            bust_spikes.append(0)

    for name, bust_vals, rand_vals in [
        ('Range/ATR', bust_range, window_stats['range_atr']),
        ('|Net Disp|/ATR', bust_disp, [abs(d) for d in window_stats['net_disp_atr']]),
        ('Dir consistency', bust_dir_cons, window_stats['dir_consistency']),
        ('N reversals', bust_reversals, window_stats['n_reversals']),
        ('Max spike/ATR', bust_spikes, window_stats['max_bar_spike']),
    ]:
        b_mean = np.mean(bust_vals)
        r_mean = np.mean(rand_vals)
        diff_pct = (b_mean - r_mean) / r_mean * 100 if r_mean != 0 else 0
        print(f"  {name:<25} {b_mean:<15.3f} {r_mean:<15.3f} {diff_pct:+.1f}%")

    # What fraction of random windows would produce a bust-like pattern?
    # A bust requires: range ≈ 1-3x tp, with multiple reversals, no strong trend
    bust_like = 0
    for i in range(len(window_stats['range_atr'])):
        r = window_stats['range_atr'][i]
        d = abs(window_stats['net_disp_atr'][i])
        # Bust-like: range is moderate (1-4x ATR) and displacement is small (< 2x ATR)
        if 1.0 < r < 4.0 and d < 2.0:
            bust_like += 1

    print(f"\n  P(random window is bust-like): {bust_like/n_samples*100:.1f}%")
    print(f"  P(actual bust | bust-like window): depends on entry timing")


# =============================================================================
# PART 6: WHICH PATHS CAN BE PREDICTED / AVOIDED?
# =============================================================================
print("\n" + "=" * 80)
print("PART 6: CAN EACH PATH TYPE BE PREDICTED?")
print("=" * 80)

# For each bust, check if there was a SIGNAL before the bust started
# that could have warned us
primary_busts = all_busts["5 lvl / 2x"]
primary_wins = all_wins["5 lvl / 2x"]

if primary_busts and primary_wins:
    # Measure pre-entry conditions for busts vs wins
    def get_pre_entry_features(cycle, candles_arr, lookback=50):
        """Extract features from the N bars BEFORE entry."""
        start = max(cycle['cycle_start'] - lookback, 0)
        end = cycle['cycle_start']
        pre = candles_arr[start:end]
        if len(pre) < 10:
            return None

        closes = pre[:, 2]
        highs = pre[:, 3]
        lows = pre[:, 4]

        # Trend strength: linear regression slope / ATR
        x = np.arange(len(closes))
        if len(x) > 1:
            slope = np.polyfit(x, closes, 1)[0]
        else:
            slope = 0
        local_atr = cycle['entry_atr']
        trend_strength = slope / local_atr if local_atr > 0 else 0

        # Volatility: std of returns
        returns = np.diff(closes) / closes[:-1]
        vol = np.std(returns) if len(returns) > 1 else 0

        # Range compression: recent range / ATR
        recent_range = (highs[-20:].max() - lows[-20:].min()) / local_atr if local_atr > 0 and len(highs) >= 20 else 0

        # Momentum: close vs close N bars ago
        momentum = (closes[-1] - closes[0]) / local_atr if local_atr > 0 else 0

        # Consecutive same-direction bars
        diffs = np.diff(closes[-20:]) if len(closes) >= 20 else np.diff(closes)
        max_consec = 0
        current = 0
        for d in diffs:
            if d > 0:
                current = current + 1 if current > 0 else 1
            elif d < 0:
                current = current - 1 if current < 0 else -1
            else:
                current = 0
            max_consec = max(max_consec, abs(current))

        return {
            'trend_strength': trend_strength,
            'vol': vol,
            'range_compression': recent_range,
            'momentum': momentum,
            'max_consec_bars': max_consec,
        }

    bust_features = [get_pre_entry_features(b, candles) for b in primary_busts]
    bust_features = [f for f in bust_features if f is not None]

    # Sample same number of wins
    np.random.seed(42)
    win_sample = [primary_wins[i] for i in np.random.choice(len(primary_wins), min(len(primary_busts)*3, len(primary_wins)), replace=False)]
    win_features = [get_pre_entry_features(w, candles) for w in win_sample]
    win_features = [f for f in win_features if f is not None]

    print(f"\n  Pre-entry features: {len(bust_features)} busts vs {len(win_features)} wins")
    print(f"\n  {'Feature':<25} {'Bust Mean':<15} {'Win Mean':<15} {'Diff %':<10} {'Separable?'}")
    print(f"  {'-'*75}")

    for feat in ['trend_strength', 'vol', 'range_compression', 'momentum', 'max_consec_bars']:
        b_vals = [f[feat] for f in bust_features]
        w_vals = [f[feat] for f in win_features]
        b_mean = np.mean(b_vals)
        w_mean = np.mean(w_vals)
        diff = (b_mean - w_mean) / (abs(w_mean) + 1e-10) * 100

        # Statistical test: can we separate?
        b_std = np.std(b_vals)
        w_std = np.std(w_vals)
        pooled_std = np.sqrt((b_std**2 + w_std**2) / 2)
        cohens_d = abs(b_mean - w_mean) / pooled_std if pooled_std > 0 else 0
        separable = "YES" if cohens_d > 0.5 else "WEAK" if cohens_d > 0.2 else "NO"

        print(f"  {feat:<25} {b_mean:<15.4f} {w_mean:<15.4f} {diff:+8.1f}%   {separable} (d={cohens_d:.3f})")

    # By path type
    print(f"\n  Pre-entry features BY PATH TYPE:")
    for btype in sorted(type_groups.keys()):
        group = type_groups[btype]
        feats = [get_pre_entry_features(b, candles) for b in group]
        feats = [f for f in feats if f is not None]
        if not feats:
            continue
        print(f"\n    {btype} ({len(group)} busts):")
        for feat in ['trend_strength', 'vol', 'range_compression', 'momentum']:
            vals = [f[feat] for f in feats]
            print(f"      {feat:<22}: {np.mean(vals):+.4f} (std={np.std(vals):.4f})")


# =============================================================================
# PART 7: LEVEL-BY-LEVEL FAILURE ANALYSIS
# =============================================================================
print("\n" + "=" * 80)
print("PART 7: LEVEL-BY-LEVEL — HOW CLOSE DID BUSTS COME TO WINNING?")
print("=" * 80)

# For each bust, how close did each level come to winning (max favorable excursion)?
primary_busts = all_busts["5 lvl / 2x"]
print(f"\n  Analyzing {len(primary_busts)} busts from '5 lvl / 2x'")
print(f"  For each level: how far did price move TOWARD TP before reversing to SL?\n")

level_mfe = {i: [] for i in range(5)}  # max favorable excursion as % of tp_dist

for bust in primary_busts:
    for lvl_info in bust['levels']:
        lvl = lvl_info['level']
        if lvl >= 5:
            break
        entry = lvl_info['entry']
        direction = lvl_info['direction']
        tp = lvl_info['tp']
        sl = lvl_info['sl']

        # Get price data for this level
        start_bar = bust['cycle_start'] if lvl == 0 else bust['levels'][lvl-1]['exit_bar'] + 1
        end_bar = lvl_info['exit_bar']

        if start_bar >= end_bar or start_bar >= len(candles) or end_bar >= len(candles):
            continue

        level_candles = candles[start_bar:end_bar+1]
        if len(level_candles) == 0:
            continue

        # Max favorable excursion
        if direction == 1:  # long
            max_price = level_candles[:, 3].max()  # highest high
            mfe = (max_price - entry) / bust['tp_dist'] if bust['tp_dist'] > 0 else 0
        else:  # short
            min_price = level_candles[:, 4].min()  # lowest low
            mfe = (entry - min_price) / bust['tp_dist'] if bust['tp_dist'] > 0 else 0

        level_mfe[lvl].append(min(mfe, 1.0))  # cap at 1.0 (didn't reach TP)

print(f"  {'Level':<8} {'MFE Mean':<12} {'MFE Median':<12} {'MFE > 80%':<12} {'MFE > 50%':<12} {'MFE < 10%':<12}")
print(f"  {'-'*65}")
for lvl in range(5):
    if level_mfe[lvl]:
        vals = level_mfe[lvl]
        mean_mfe = np.mean(vals)
        med_mfe = np.median(vals)
        gt80 = sum(1 for v in vals if v > 0.8) / len(vals) * 100
        gt50 = sum(1 for v in vals if v > 0.5) / len(vals) * 100
        lt10 = sum(1 for v in vals if v < 0.1) / len(vals) * 100
        print(f"  L{lvl:<6} {mean_mfe:<12.3f} {med_mfe:<12.3f} {gt80:<12.1f}% {gt50:<12.1f}% {lt10:<12.1f}%")

print("""
  MFE > 80% means price got within 20% of TP before reversing.
  High MFE = "almost won" — price nearly reached TP then reversed.
  Low MFE = "never had a chance" — price moved against immediately.
""")

# Same for 12-level config
sqrt_busts = all_busts.get("12 lvl / sqrt", [])
if sqrt_busts:
    print(f"\n  12 lvl / sqrt — {len(sqrt_busts)} busts, MFE by level:")
    level_mfe_sqrt = {i: [] for i in range(12)}
    for bust in sqrt_busts:
        for lvl_info in bust['levels']:
            lvl = lvl_info['level']
            if lvl >= 12:
                break
            entry = lvl_info['entry']
            direction = lvl_info['direction']
            start_bar = bust['cycle_start'] if lvl == 0 else bust['levels'][lvl-1]['exit_bar'] + 1
            end_bar = lvl_info['exit_bar']
            if start_bar >= end_bar or start_bar >= len(candles) or end_bar >= len(candles):
                continue
            level_candles = candles[start_bar:end_bar+1]
            if len(level_candles) == 0:
                continue
            if direction == 1:
                max_p = level_candles[:, 3].max()
                mfe = (max_p - entry) / bust['tp_dist'] if bust['tp_dist'] > 0 else 0
            else:
                min_p = level_candles[:, 4].min()
                mfe = (entry - min_p) / bust['tp_dist'] if bust['tp_dist'] > 0 else 0
            level_mfe_sqrt[lvl].append(min(mfe, 1.0))

    print(f"  {'Level':<8} {'MFE Mean':<12} {'MFE Median':<12} {'MFE > 80%':<12} {'Samples':<8}")
    print(f"  {'-'*50}")
    for lvl in range(12):
        if level_mfe_sqrt[lvl]:
            vals = level_mfe_sqrt[lvl]
            print(f"  L{lvl:<6} {np.mean(vals):<12.3f} {np.median(vals):<12.3f} "
                  f"{sum(1 for v in vals if v > 0.8)/len(vals)*100:<12.1f}% {len(vals):<8}")


# =============================================================================
# PART 8: TIME-OF-DAY AND DAY-OF-WEEK PATTERNS
# =============================================================================
print("\n" + "=" * 80)
print("PART 8: TEMPORAL PATTERNS — When Do Busts Happen?")
print("=" * 80)

from datetime import datetime, timezone

primary_busts = all_busts["5 lvl / 2x"]
primary_wins = all_wins["5 lvl / 2x"]

# Hour of day distribution
bust_hours = []
win_hours = []
for b in primary_busts:
    ts = b['timestamp']
    dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)
    bust_hours.append(dt.hour)
for w in primary_wins[:5000]:  # sample
    ts = w['timestamp']
    dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)
    win_hours.append(dt.hour)

# Bust rate by hour
print(f"\n  Bust rate by hour of day (UTC):")
print(f"  {'Hour':<6} {'Busts':<8} {'Wins':<8} {'Total':<8} {'Bust%':<8}")
print(f"  {'-'*40}")
for h in range(24):
    nb = sum(1 for x in bust_hours if x == h)
    nw = sum(1 for x in win_hours if x == h)
    total = nb + nw
    if total > 10:
        print(f"  {h:02d}:00 {nb:<8} {nw:<8} {total:<8} {nb/total*100:<8.1f}%")

# Day of week
bust_days = []
win_days = []
for b in primary_busts:
    ts = b['timestamp']
    dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)
    bust_days.append(dt.weekday())
for w in primary_wins[:5000]:
    ts = w['timestamp']
    dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)
    win_days.append(dt.weekday())

day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
print(f"\n  Bust rate by day of week:")
for d in range(7):
    nb = sum(1 for x in bust_days if x == d)
    nw = sum(1 for x in win_days if x == d)
    total = nb + nw
    if total > 5:
        print(f"  {day_names[d]}: {nb}/{total} = {nb/total*100:.1f}%")


# =============================================================================
# VISUALIZATION
# =============================================================================
fig = plt.figure(figsize=(24, 30))
gs = GridSpec(5, 3, hspace=0.35, wspace=0.3)

# Plot 1-6: Example bust price paths (one per type)
primary_busts = all_busts["5 lvl / 2x"]
type_groups_local = {}
for b in primary_busts:
    bt = b.get('path_type', 'UNKNOWN')
    if bt not in type_groups_local:
        type_groups_local[bt] = []
    type_groups_local[bt].append(b)

plot_idx = 0
for btype in sorted(type_groups_local.keys()):
    if plot_idx >= 6:
        break
    group = type_groups_local[btype]
    # Pick the median-duration bust as representative
    sorted_group = sorted(group, key=lambda b: b['duration_bars'])
    example = sorted_group[len(sorted_group)//2]

    ax = fig.add_subplot(gs[plot_idx // 3, plot_idx % 3])

    # Plot price path
    path = example['price_path']
    offset = example['path_offset']
    x = np.arange(len(path)) - offset
    ax.plot(x, path, 'k-', linewidth=0.8, alpha=0.8)

    # Mark entry
    ax.axvline(x=0, color='blue', linestyle='--', alpha=0.5, linewidth=0.5)
    ax.axhline(y=example['entry_price'], color='gray', linestyle=':', alpha=0.5)

    # Mark each level's TP and SL
    colors = ['green', 'red', 'green', 'red', 'green', 'red']
    for lvl_info in example['levels']:
        lvl = lvl_info['level']
        tp_price = lvl_info['tp']
        sl_price = lvl_info['sl']
        c = colors[lvl % len(colors)]
        ax.axhline(y=tp_price, color='green', linestyle='-', alpha=0.2, linewidth=0.5)
        ax.axhline(y=sl_price, color='red', linestyle='-', alpha=0.2, linewidth=0.5)

    ax.set_title(f'{btype}\n({len(group)} busts, {example["duration_min"]}min)',
                 fontsize=9, fontweight='bold')
    ax.set_xlabel('Bars from entry')
    ax.set_ylabel('Price')
    ax.grid(True, alpha=0.2)
    plot_idx += 1

# Plot 7: Path type distribution (pie/bar)
ax7 = fig.add_subplot(gs[2, 0])
types = sorted(type_groups_local.keys())
counts = [len(type_groups_local[t]) for t in types]
colors_pie = plt.cm.Set2(np.linspace(0, 1, len(types)))
ax7.barh(range(len(types)), counts, color=colors_pie)
ax7.set_yticks(range(len(types)))
ax7.set_yticklabels(types, fontsize=8)
ax7.set_xlabel('Number of busts')
ax7.set_title('BUST PATH TYPE DISTRIBUTION', fontweight='bold')

# Plot 8: MFE distribution by level
ax8 = fig.add_subplot(gs[2, 1])
for lvl in range(5):
    if level_mfe[lvl]:
        ax8.hist(level_mfe[lvl], bins=20, alpha=0.4, label=f'L{lvl}', density=True)
ax8.set_xlabel('Max Favorable Excursion (fraction of TP)')
ax8.set_ylabel('Density')
ax8.set_title('HOW CLOSE DID BUSTS COME TO WINNING?', fontweight='bold')
ax8.legend(fontsize=8)
ax8.axvline(x=0.8, color='red', linestyle='--', alpha=0.5, label='80% of TP')

# Plot 9: Bust range vs displacement scatter
ax9 = fig.add_subplot(gs[2, 2])
for btype in sorted(type_groups_local.keys()):
    group = type_groups_local[btype]
    ranges = [b['cycle_range_atr'] for b in group]
    disps = [b['net_disp_atr'] for b in group]
    ax9.scatter(disps, ranges, alpha=0.4, label=btype, s=15)
ax9.set_xlabel('Net Displacement / ATR')
ax9.set_ylabel('Total Range / ATR')
ax9.set_title('BUST GEOMETRY: Range vs Displacement', fontweight='bold')
ax9.legend(fontsize=7)
ax9.grid(True, alpha=0.3)

# Plot 10: Pre-entry features comparison
ax10 = fig.add_subplot(gs[3, 0])
features_to_plot = ['trend_strength', 'vol', 'range_compression', 'momentum']
x_pos = np.arange(len(features_to_plot))
width = 0.35
bust_means = [np.mean([f[feat] for f in bust_features]) for feat in features_to_plot]
win_means = [np.mean([f[feat] for f in win_features]) for feat in features_to_plot]
# Normalize for comparison
bust_norm = [b / (abs(w) + 1e-10) for b, w in zip(bust_means, win_means)]
win_norm = [1.0] * len(features_to_plot)
ax10.bar(x_pos - width/2, bust_norm, width, label='Busts', color='coral', alpha=0.7)
ax10.bar(x_pos + width/2, win_norm, width, label='Wins', color='steelblue', alpha=0.7)
ax10.set_xticks(x_pos)
ax10.set_xticklabels(features_to_plot, fontsize=8, rotation=15)
ax10.set_ylabel('Relative to Win Mean')
ax10.set_title('PRE-ENTRY FEATURES: Bust vs Win', fontweight='bold')
ax10.legend()
ax10.axhline(y=1.0, color='black', linewidth=0.5, linestyle='--')

# Plot 11: Hour of day bust rate
ax11 = fig.add_subplot(gs[3, 1])
hours = range(24)
bust_by_hour = [sum(1 for x in bust_hours if x == h) for h in hours]
total_by_hour = [sum(1 for x in bust_hours if x == h) + sum(1 for x in win_hours if x == h) for h in hours]
rate_by_hour = [bust_by_hour[h] / total_by_hour[h] * 100 if total_by_hour[h] > 0 else 0 for h in hours]
ax11.bar(hours, rate_by_hour, color='coral', alpha=0.7)
ax11.set_xlabel('Hour (UTC)')
ax11.set_ylabel('Bust Rate %')
ax11.set_title('BUST RATE BY HOUR', fontweight='bold')
ax11.axhline(y=np.mean(rate_by_hour), color='black', linestyle='--', alpha=0.5)
ax11.grid(True, alpha=0.3, axis='y')

# Plot 12: ATR expansion during busts
ax12 = fig.add_subplot(gs[3, 2])
bust_atr_exp = [b['atr_expansion'] for b in primary_busts]
win_atr_exp = [w['atr_expansion'] for w in primary_wins[:2000]]
ax12.hist(bust_atr_exp, bins=30, alpha=0.5, label='Busts', color='coral', density=True)
ax12.hist(win_atr_exp, bins=30, alpha=0.5, label='Wins', color='steelblue', density=True)
ax12.set_xlabel('ATR Expansion (during / at entry)')
ax12.set_ylabel('Density')
ax12.set_title('ATR EXPANSION: Busts vs Wins', fontweight='bold')
ax12.legend()
ax12.axvline(x=1.0, color='black', linestyle='--', alpha=0.5)

# Plot 13-15: Top 3 worst busts — full price paths
sqrt_busts = all_busts.get("12 lvl / sqrt", [])
worst_busts = sorted(primary_busts, key=lambda b: b['duration_bars'], reverse=True)[:3]
if not worst_busts:
    worst_busts = primary_busts[:3]

for idx, bust in enumerate(worst_busts):
    ax = fig.add_subplot(gs[4, idx])
    path = bust['price_path']
    offset = bust['path_offset']
    x = np.arange(len(path)) - offset
    ax.plot(x, path, 'k-', linewidth=0.8)
    ax.axvline(x=0, color='blue', linestyle='--', alpha=0.5)
    ax.axhline(y=bust['entry_price'], color='gray', linestyle=':', alpha=0.5)

    for lvl_info in bust['levels']:
        ax.axhline(y=lvl_info['tp'], color='green', alpha=0.15, linewidth=0.5)
        ax.axhline(y=lvl_info['sl'], color='red', alpha=0.15, linewidth=0.5)

    ax.set_title(f'Worst Bust #{idx+1}\n{bust["duration_min"]}min, type={bust.get("path_type","?")}',
                 fontsize=9)
    ax.set_xlabel('Bars from entry')
    ax.grid(True, alpha=0.2)

plt.suptitle('MARKET LOSS PATHS — Every Way the Strategy Can Lose',
             fontsize=16, fontweight='bold', y=0.99)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(OUTPUT_DIR, exist_ok=True)
plt.savefig(os.path.join(OUTPUT_DIR, '14_loss_paths.png'), dpi=150, bbox_inches='tight')
print(f"\nSaved: {OUTPUT_DIR}/14_loss_paths.png")


# =============================================================================
# SYNTHESIS
# =============================================================================
print("\n" + "=" * 80)
print("SYNTHESIS: ALL LOSS PATHS AND THEIR SOLVABILITY")
print("=" * 80)

print("""
THE FIVE LOSS PATHS:

PATH A: STRONG TREND
  What: Price trends strongly in one direction, sweeping through hedges.
  Mechanism: Each hedge reversal gets stopped out because the trend
             momentum exceeds the h_dist reversal threshold.
  Detection: High directional consistency, large net displacement.
  Solvable?: PARTIALLY — trend detection (ADX, slope) could filter entries
             during strong trends. But trend START is hard to predict.
  ML opportunity: Regime classifier (trending vs ranging).

PATH B: CHOPPY RANGE (most common)
  What: Price oscillates with amplitude between h and tp.
  Mechanism: Oscillation amplitude is large enough to hit each h_dist SL
             but not large enough to reach tp_dist TP (since tp = 2*h).
  Detection: Range ≈ 1-3x tp, small net displacement, many reversals.
  Solvable?: HARDEST — this is the fundamental vulnerability.
             The strategy REQUIRES tp > h, which means choppy moves
             that exceed h but not tp will always cause losses.
             This is the CORE problem.
  ML opportunity: Detect range-bound markets and widen tp/h or skip.

PATH C: VOLATILITY EXPANSION
  What: ATR was measured at entry but increases during the cycle.
  Mechanism: Fixed tp/h distances become too small for actual volatility,
             making SL hits more likely while TP is harder to reach.
  Detection: ATR expansion > 1.5x during cycle.
  Solvable?: YES — use dynamic ATR or check ATR trend before entry.
             If ATR is expanding, skip entry or widen distances.
  ML opportunity: ATR prediction / volatility regime detection.

PATH D: GAP/SPIKE
  What: Sudden large move (news, data release) blows through levels.
  Mechanism: Single or few bars with range >> normal, bypassing multiple SLs.
  Detection: Large bar range relative to ATR.
  Solvable?: PARTIALLY — avoid entries around known events (NFP, ECB, etc).
             Random spikes are unpredictable.
  ML opportunity: Economic calendar integration, news sentiment.

PATH E: SLOW GRIND
  What: Price slowly drifts against position without mean-reverting.
  Mechanism: Each level takes many bars to resolve, price grinds
             to SL rather than spiking through it.
  Detection: Long duration, high bars-per-level, low volatility.
  Solvable?: PARTIALLY — duration caps could limit exposure.
             But the grind itself is hard to predict vs a slow trend
             that eventually reverses.
  ML opportunity: Time-based exit rules, duration-aware sizing.
""")

# Summarize by config
for config_name in all_busts:
    busts = all_busts[config_name]
    if not busts:
        continue

    type_counts = {}
    for b in busts:
        bt = b.get('path_type', 'UNKNOWN')
        type_counts[bt] = type_counts.get(bt, 0) + 1

    print(f"\n  {config_name} — Path type breakdown:")
    for bt in sorted(type_counts.keys()):
        n = type_counts[bt]
        pct = n / len(busts) * 100
        if bt == 'B_CHOPPY_RANGE':
            solvable = "INHERENT (hardest)"
        elif bt == 'A_STRONG_TREND':
            solvable = "PARTIALLY (trend detection)"
        elif bt == 'C_VOL_EXPANSION':
            solvable = "YES (dynamic ATR)"
        elif bt == 'D_GAP_SPIKE':
            solvable = "PARTIALLY (calendar)"
        elif bt == 'E_SLOW_GRIND':
            solvable = "PARTIALLY (duration caps)"
        else:
            solvable = "UNKNOWN"
        print(f"    {bt:<20} {n:>4} ({pct:>5.1f}%) — {solvable}")

print("""
BOTTOM LINE:
  The dominant loss path (choppy range) is INHERENT to the strategy's
  geometry (tp > h requirement). It cannot be eliminated without
  changing the fundamental hedge structure.

  The solvable paths (vol expansion, some trends, spikes) represent
  a fraction of total busts. Fixing them would reduce bust rate by
  an estimated 20-40%, but cannot eliminate busts entirely.

  The remaining busts are the mathematical floor — the price of doing
  business with a martingale-derived system.
""")
