#!/usr/bin/env python3
"""
Step 15: Data & Feature Engineering for Regime Detection
=========================================================
Phase A of the ML research pipeline. Builds the feature matrix that all
subsequent modelling scripts will consume.

Pipeline:
  1. Load all available 1m EUR-USD data, resample to 5m/15m/1H/4H/D1
  2. Compute 5 regime features x 5 timeframes = 25 features per 5m bar
  3. Run full surefire cycle simulation (12-level, sqrt(2), 0.5% base)
  4. Build feature matrix: one row per cycle, 25 features + labels
  5. Split: 2024-01 to 2025-06 development, 2025-06 to 2026-03 holdout
  6. Save as parquet files

Features (per timeframe):
  - Choppiness Index (14-period)
  - Hurst Exponent (20-bar rolling R/S)
  - ATR ratio (ATR14 / ATR50)
  - ADX (14-period)
  - Range/ATR (20-bar high-low range / ATR14)

Data available: OANDA EUR-USD 1m from 2024-01-01 to 2026-03-21.
"""

import os, sys, time
os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime, timezone

import qengine.indicators as ta
import qengine.helpers as jh
from qengine.research import get_candles

# =============================================================================
# CONFIGURATION
# =============================================================================
EXCHANGE = 'OANDA'
SYMBOL = 'EUR-USD'
DATA_START = '2006-01-02'
DATA_END = '2025-12-31'
SPLIT_DATE = '2021-01-01'  # dev / holdout boundary (2006-2020 dev, 2021-2025 holdout)

# Surefire cycle parameters
MAX_LEVELS = 12
MULTIPLIER_FN = lambda n: np.sqrt(2) ** n
BASE_PCT = 0.005        # 0.5% of equity per base lot
TP_ATR_MULT = 0.8       # TP distance = ATR * this
HEDGE_RATIO = 2.0       # TP / hedge distance
EQUITY_START = 10_000
LEVERAGE = 30
PRICE_PER_LOT = 100_000

# Feature parameters
HURST_WINDOW = 20       # rolling window for Hurst R/S
CHOP_PERIOD = 14
ADX_PERIOD = 14
ATR_SHORT = 14
ATR_LONG = 50
RANGE_WINDOW = 20

# Output
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 80)
print("STEP 15: DATA & FEATURE ENGINEERING FOR REGIME DETECTION")
print("=" * 80)


# =============================================================================
# SECTION 1: LOAD 1-MINUTE DATA
# =============================================================================
print("\n[1/6] Loading 1m EUR-USD candles...")
t0 = time.time()

_, candles_1m = get_candles(
    EXCHANGE, SYMBOL, '1m',
    jh.date_to_timestamp(DATA_START),
    jh.date_to_timestamp(DATA_END),
    warmup_candles_num=0
)

print(f"  Loaded {len(candles_1m):,} 1m candles in {time.time()-t0:.1f}s")
print(f"  Range: {datetime.fromtimestamp(candles_1m[0,0]/1000, tz=timezone.utc).date()} "
      f"to {datetime.fromtimestamp(candles_1m[-1,0]/1000, tz=timezone.utc).date()}")


# =============================================================================
# SECTION 2: RESAMPLE TO HIGHER TIMEFRAMES
# =============================================================================
print("\n[2/6] Resampling to 5m, 15m, 1H, 4H, D1...")
t0 = time.time()


def resample_candles(candles_1m: np.ndarray, factor: int) -> np.ndarray:
    """
    Resample 1-minute candles to a higher timeframe by grouping `factor`
    consecutive 1m bars into one bar.

    Candle format: [timestamp, open, close, high, low, volume]
    """
    n = len(candles_1m)
    # Trim to exact multiple of factor
    trim = n - (n % factor)
    c = candles_1m[:trim].reshape(-1, factor, 6)

    out = np.empty((len(c), 6), dtype=np.float64)
    out[:, 0] = c[:, 0, 0]             # timestamp = first bar's timestamp
    out[:, 1] = c[:, 0, 1]             # open = first bar's open
    out[:, 2] = c[:, -1, 2]            # close = last bar's close
    out[:, 3] = c[:, :, 3].max(axis=1) # high = max of highs
    out[:, 4] = c[:, :, 4].min(axis=1) # low = min of lows
    out[:, 5] = c[:, :, 5].sum(axis=1) # volume = sum
    return out


TIMEFRAMES = {
    '5m':  5,
    '15m': 15,
    '1H':  60,
    '4H':  240,
    'D1':  1440,
}

candles = {}
for tf_name, factor in TIMEFRAMES.items():
    candles[tf_name] = resample_candles(candles_1m, factor)
    print(f"  {tf_name}: {len(candles[tf_name]):,} bars (factor={factor})")

print(f"  Resampling done in {time.time()-t0:.1f}s")


# =============================================================================
# SECTION 3: COMPUTE REGIME FEATURES
# =============================================================================
print("\n[3/6] Computing regime features (5 indicators x 5 timeframes)...")
t0 = time.time()


def rolling_hurst_rs(prices: np.ndarray, window: int = 20) -> np.ndarray:
    """
    Rolling Hurst exponent via R/S analysis.

    For each position i, uses prices[i-window+1 : i+1] to compute the
    rescaled range statistic and estimate H. Returns NaN where insufficient
    data exists.

    Uses a simplified single-scale R/S (the whole window as one chunk)
    which is fast and adequate for a rolling feature.
    """
    n = len(prices)
    H = np.full(n, np.nan, dtype=np.float64)

    for i in range(window - 1, n):
        segment = prices[i - window + 1: i + 1]
        # Returns (log differences)
        returns = np.diff(segment)
        if len(returns) < 2:
            continue

        mean_r = np.mean(returns)
        std_r = np.std(returns, ddof=0)
        if std_r < 1e-12:
            H[i] = 0.5  # no variation -> random walk default
            continue

        # Cumulative deviation from mean
        cumdev = np.cumsum(returns - mean_r)
        R = np.max(cumdev) - np.min(cumdev)
        RS = R / std_r

        if RS <= 0:
            H[i] = 0.5
            continue

        # Single-scale estimate: H = log(R/S) / log(n)
        # For a single scale this is a rough estimate; for a rolling
        # feature the relative ordering matters more than absolute value.
        H[i] = np.log(RS) / np.log(len(returns))

    return H


def rolling_range_over_atr(candles_tf: np.ndarray, range_window: int,
                           atr_arr: np.ndarray) -> np.ndarray:
    """
    (Highest high - lowest low) over `range_window` bars, divided by ATR.
    Measures how far price has traveled relative to average volatility.
    High values = trending, low values = ranging.
    """
    n = len(candles_tf)
    result = np.full(n, np.nan, dtype=np.float64)
    highs = candles_tf[:, 3]
    lows = candles_tf[:, 4]

    for i in range(range_window - 1, n):
        hh = np.max(highs[i - range_window + 1: i + 1])
        ll = np.min(lows[i - range_window + 1: i + 1])
        if atr_arr[i] > 1e-12 and not np.isnan(atr_arr[i]):
            result[i] = (hh - ll) / atr_arr[i]

    return result


def compute_features_for_tf(candles_tf: np.ndarray, tf_name: str) -> dict:
    """
    Compute all 5 regime features for one timeframe.
    Returns dict of feature_name -> np.ndarray (length = len(candles_tf)).
    """
    prefix = tf_name

    # 1. Choppiness Index
    chop = ta.chop(candles_tf, period=CHOP_PERIOD, sequential=True)

    # 2. Hurst exponent (rolling R/S on close prices)
    closes = candles_tf[:, 2]
    hurst = rolling_hurst_rs(closes, window=HURST_WINDOW)

    # 3. ATR ratio (ATR14 / ATR50)
    atr_short = ta.atr(candles_tf, period=ATR_SHORT, sequential=True)
    atr_long = ta.atr(candles_tf, period=ATR_LONG, sequential=True)
    with np.errstate(divide='ignore', invalid='ignore'):
        atr_ratio = np.where(
            (atr_long > 1e-12) & ~np.isnan(atr_long),
            atr_short / atr_long,
            np.nan
        )

    # 4. ADX
    adx = ta.adx(candles_tf, period=ADX_PERIOD, sequential=True)

    # 5. Range / ATR
    range_atr = rolling_range_over_atr(candles_tf, RANGE_WINDOW, atr_short)

    return {
        f'{prefix}_chop':      chop,
        f'{prefix}_hurst':     hurst,
        f'{prefix}_atr_ratio': atr_ratio,
        f'{prefix}_adx':       adx,
        f'{prefix}_range_atr': range_atr,
    }


# Compute features for every timeframe
all_features = {}  # tf_name -> {feature_name: array}
for tf_name in TIMEFRAMES:
    print(f"  Computing features for {tf_name}...")
    all_features[tf_name] = compute_features_for_tf(candles[tf_name], tf_name)
    for fname, arr in all_features[tf_name].items():
        valid = np.sum(~np.isnan(arr))
        print(f"    {fname}: {valid:,} valid / {len(arr):,} total")

print(f"  Features computed in {time.time()-t0:.1f}s")


# =============================================================================
# SECTION 3b: ALIGN HIGHER-TIMEFRAME FEATURES TO 5m BARS
# =============================================================================
print("\n  Aligning all features to 5m bar grid...")

# Build a timestamp -> index lookup for each higher TF
# For each 5m bar, find the most recent completed bar in each higher TF
# and pull that bar's features forward (forward-fill, no lookahead).

candles_5m = candles['5m']
ts_5m = candles_5m[:, 0]
n_5m = len(candles_5m)

# For the 5m timeframe, features are already aligned 1:1
features_5m = all_features['5m']  # already the right length

# For higher TFs, map each 5m bar to the most recent completed higher-TF bar
aligned_features = {}

# Copy 5m features directly
for fname, arr in features_5m.items():
    aligned_features[fname] = arr.copy()

for tf_name in ['15m', '1H', '4H', 'D1']:
    tf_candles = candles[tf_name]
    tf_timestamps = tf_candles[:, 0]
    tf_features = all_features[tf_name]

    # For each 5m timestamp, find index of most recent TF bar that started
    # at or before this 5m bar's timestamp.
    # Use searchsorted: tf_timestamps is sorted.
    # searchsorted('right') gives index of first element > ts_5m[i],
    # so index - 1 is the most recent completed bar.
    indices = np.searchsorted(tf_timestamps, ts_5m, side='right') - 1

    for fname, arr in tf_features.items():
        aligned = np.full(n_5m, np.nan, dtype=np.float64)
        valid_mask = (indices >= 0) & (indices < len(arr))
        aligned[valid_mask] = arr[indices[valid_mask]]
        aligned_features[fname] = aligned

feature_names = sorted(aligned_features.keys())
print(f"  Total features aligned to 5m grid: {len(feature_names)}")
for fn in feature_names:
    valid = np.sum(~np.isnan(aligned_features[fn]))
    print(f"    {fn}: {valid:,} / {n_5m:,}")


# =============================================================================
# SECTION 4: SUREFIRE CYCLE SIMULATION
# =============================================================================
print("\n[4/6] Running surefire cycle simulation on 5m data...")
print(f"  Parameters: {MAX_LEVELS} levels, sqrt(2) multiplier, "
      f"{BASE_PCT*100:.1f}% base, TP={TP_ATR_MULT}xATR, hedge_ratio={HEDGE_RATIO}")
t0 = time.time()

# Compute indicators needed for entry signals and simulation
ema_fast = ta.ema(candles_5m, period=8, sequential=True)
ema_slow = ta.ema(candles_5m, period=21, sequential=True)
atr_sim = ta.atr(candles_5m, period=14, sequential=True)

# Warmup offset: need enough bars for longest indicator
WARMUP = max(ATR_LONG, ADX_PERIOD * 2, HURST_WINDOW, 60)


def simulate_cycles(candles_5m, ema_fast, ema_slow, atr_arr, offset):
    """
    Run full surefire cycle simulation.
    Returns list of cycle dicts, each containing:
      - entry_bar, end_bar, outcome, win_level, pnl, levels_used, etc.
    """
    n = len(candles_5m)
    closes = candles_5m[:, 2]
    highs = candles_5m[:, 3]
    lows = candles_5m[:, 4]

    equity = EQUITY_START
    cycles = []
    i = offset

    while i < n - 1:
        # Look for EMA 8/21 crossover (bullish only for simplicity,
        # then alternate direction from hedge logic)
        if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]):
            i += 1
            continue
        if np.isnan(ema_fast[i-1]) or np.isnan(ema_slow[i-1]):
            i += 1
            continue

        # Detect crossover
        is_bull_cross = (ema_fast[i-1] < ema_slow[i-1]) and (ema_fast[i] >= ema_slow[i])
        is_bear_cross = (ema_fast[i-1] > ema_slow[i-1]) and (ema_fast[i] <= ema_slow[i])

        if not (is_bull_cross or is_bear_cross):
            i += 1
            continue

        if np.isnan(atr_arr[i]) or atr_arr[i] < 1e-6:
            i += 1
            continue

        # Cycle entry
        entry_bar = i
        tp_dist = atr_arr[i] * TP_ATR_MULT
        h_dist = tp_dist / HEDGE_RATIO
        entry_price = closes[i]
        direction = 1 if is_bull_cross else -1

        base_lots = equity * BASE_PCT / PRICE_PER_LOT * LEVERAGE
        if base_lots < 0.001:
            i += 1
            continue

        # Compute affordable levels (margin + potential loss < 95% equity)
        affordable = MAX_LEVELS
        for test_n in range(1, MAX_LEVELS + 1):
            cum_size = sum(base_lots * MULTIPLIER_FN(k) for k in range(test_n))
            cum_margin = cum_size * PRICE_PER_LOT / LEVERAGE
            cum_loss = cum_size * h_dist * PRICE_PER_LOT
            if cum_margin + cum_loss > equity * 0.95:
                affordable = test_n - 1
                break
        affordable = max(affordable, 2)

        # Walk through levels
        cycle_pnl = 0.0
        win_level = -1
        positions = []
        j = i + 1
        entry = entry_price

        for level in range(affordable):
            size = base_lots * MULTIPLIER_FN(level)
            tp_price = entry + direction * tp_dist
            sl_price = entry - direction * h_dist
            positions.append((size, entry, direction, tp_price, sl_price))

            won = False
            lost = False
            while j < n:
                h = highs[j]
                lo = lows[j]

                if direction == 1:  # long
                    if h >= tp_price:
                        won = True
                        break
                    if lo <= sl_price:
                        lost = True
                        break
                else:  # short
                    if lo <= tp_price:
                        won = True
                        break
                    if h >= sl_price:
                        lost = True
                        break
                j += 1

            if won:
                # All previous legs lost, this leg won
                for sz, ent, d, tp_p, sl_p in positions[:-1]:
                    cycle_pnl -= sz * h_dist * PRICE_PER_LOT
                cycle_pnl += size * tp_dist * PRICE_PER_LOT
                win_level = level
                break
            elif lost:
                entry = sl_price
                direction *= -1
                j += 1
            else:
                # Ran out of data
                break

        # Bust: all levels exhausted
        if win_level == -1 and j < n:
            for sz, ent, d, tp_p, sl_p in positions:
                cycle_pnl -= sz * h_dist * PRICE_PER_LOT

        # Skip incomplete cycles (ran out of data)
        if j >= n and win_level == -1:
            i = j
            continue

        equity_before = equity
        equity += cycle_pnl

        cycles.append({
            'entry_bar': entry_bar,
            'end_bar': j,
            'timestamp': candles_5m[entry_bar, 0],
            'outcome': 'win' if win_level >= 0 else 'bust',
            'win_level': win_level,
            'is_bust': win_level == -1,
            'levels_used': len(positions),
            'pnl': cycle_pnl,
            'pnl_pct': cycle_pnl / equity_before * 100 if equity_before > 0 else 0,
            'equity_before': equity_before,
            'equity_after': equity,
            'duration_bars': j - entry_bar,
            'direction': 1 if is_bull_cross else -1,
            'entry_price': closes[entry_bar],
            'atr_at_entry': atr_arr[entry_bar],
        })

        i = j + 1  # no overlapping cycles

    return cycles, equity


cycles, final_equity = simulate_cycles(candles_5m, ema_fast, ema_slow, atr_sim, WARMUP)

n_cycles = len(cycles)
n_wins = sum(1 for c in cycles if not c['is_bust'])
n_busts = sum(1 for c in cycles if c['is_bust'])
bust_rate = n_busts / n_cycles * 100 if n_cycles > 0 else 0

print(f"  Simulation complete in {time.time()-t0:.1f}s")
print(f"  Total cycles: {n_cycles:,}")
print(f"  Wins: {n_wins:,} ({n_wins/n_cycles*100:.1f}%)")
print(f"  Busts: {n_busts:,} ({bust_rate:.2f}%)")
print(f"  Final equity: ${final_equity:,.2f} (from ${EQUITY_START:,})")

# Level distribution
from collections import Counter
level_counts = Counter(c['win_level'] for c in cycles)
print("  Level distribution:")
for lvl in sorted(level_counts.keys()):
    cnt = level_counts[lvl]
    label = f"L{lvl}" if lvl >= 0 else "BUST"
    print(f"    {label}: {cnt:,} ({cnt/n_cycles*100:.1f}%)")


# =============================================================================
# SECTION 5: BUILD FEATURE MATRIX
# =============================================================================
print("\n[5/6] Building feature matrix (one row per cycle)...")
t0 = time.time()

rows = []
for c in cycles:
    bar = c['entry_bar']
    row = {
        # Metadata
        'entry_bar': bar,
        'timestamp': c['timestamp'],
        'entry_price': c['entry_price'],
        'atr_at_entry': c['atr_at_entry'],
        'direction': c['direction'],

        # Labels
        'level_reached': c['win_level'] if c['win_level'] >= 0 else c['levels_used'],
        'is_bust': int(c['is_bust']),
        'pnl': c['pnl'],
        'pnl_pct': c['pnl_pct'],
        'duration_bars': c['duration_bars'],
        'levels_used': c['levels_used'],

        # Derived label: "choppy bust" = bust in high-chop regime
        # (will be computed after features are attached)
    }

    # Attach all 25 features at the cycle entry bar
    for fname in feature_names:
        arr = aligned_features[fname]
        row[fname] = arr[bar] if bar < len(arr) else np.nan

    rows.append(row)

df = pd.DataFrame(rows)

# Compute choppy_bust: bust where 5m choppiness > median at entry
chop_median = np.nanmedian(aligned_features['5m_chop'])
df['choppy_bust'] = ((df['is_bust'] == 1) & (df['5m_chop'] > chop_median)).astype(int)

# Add datetime column for easier analysis
df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)

print(f"  Feature matrix shape: {df.shape}")
print(f"  Columns: {list(df.columns)}")
print(f"  Feature columns (25): {feature_names}")

# Check for NaN features
nan_counts = df[feature_names].isna().sum()
print(f"\n  NaN counts per feature:")
for fn in feature_names:
    nc = nan_counts[fn]
    if nc > 0:
        print(f"    {fn}: {nc} ({nc/len(df)*100:.1f}%)")
if nan_counts.sum() == 0:
    print(f"    (none -- all features fully populated)")

print(f"  Built in {time.time()-t0:.1f}s")


# =============================================================================
# SECTION 6: TRAIN / HOLDOUT SPLIT & SAVE
# =============================================================================
print("\n[6/6] Splitting and saving...")

split_ts = jh.date_to_timestamp(SPLIT_DATE)  # already in ms
df_dev = df[df['timestamp'] < split_ts].copy()
df_holdout = df[df['timestamp'] >= split_ts].copy()

print(f"  Development set: {len(df_dev):,} cycles "
      f"({df_dev['datetime'].min().date()} to {df_dev['datetime'].max().date()})")
print(f"    Wins: {(df_dev['is_bust']==0).sum()}, Busts: {(df_dev['is_bust']==1).sum()} "
      f"({df_dev['is_bust'].mean()*100:.2f}% bust rate)")

print(f"  Holdout set:     {len(df_holdout):,} cycles "
      f"({df_holdout['datetime'].min().date()} to {df_holdout['datetime'].max().date()})")
print(f"    Wins: {(df_holdout['is_bust']==0).sum()}, Busts: {(df_holdout['is_bust']==1).sum()} "
      f"({df_holdout['is_bust'].mean()*100:.2f}% bust rate)")

# Save as parquet
dev_path = os.path.join(OUTPUT_DIR, '15_features_dev.parquet')
holdout_path = os.path.join(OUTPUT_DIR, '15_features_holdout.parquet')
full_path = os.path.join(OUTPUT_DIR, '15_features_full.parquet')

df_dev.to_parquet(dev_path, index=False)
df_holdout.to_parquet(holdout_path, index=False)
df.to_parquet(full_path, index=False)

print(f"\n  Saved: {dev_path}")
print(f"  Saved: {holdout_path}")
print(f"  Saved: {full_path}")


# =============================================================================
# DIAGNOSTIC PLOTS
# =============================================================================
print("\n  Generating diagnostic plots...")

fig, axes = plt.subplots(3, 2, figsize=(16, 18))

# Plot 1: Feature correlation heatmap (dev set)
ax = axes[0, 0]
feat_cols = [fn for fn in feature_names if fn in df_dev.columns]
corr = df_dev[feat_cols].corr()
im = ax.imshow(corr.values, cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')
ax.set_xticks(range(len(feat_cols)))
ax.set_xticklabels([f.replace('_', '\n', 1) for f in feat_cols], fontsize=5, rotation=90)
ax.set_yticks(range(len(feat_cols)))
ax.set_yticklabels([f.replace('_', '\n', 1) for f in feat_cols], fontsize=5)
ax.set_title('Feature Correlation Matrix (Dev Set)')
plt.colorbar(im, ax=ax, fraction=0.046)

# Plot 2: Feature distributions — bust vs win (dev set, 5m features)
ax = axes[0, 1]
feat_5m = [fn for fn in feature_names if fn.startswith('5m_')]
busts_df = df_dev[df_dev['is_bust'] == 1]
wins_df = df_dev[df_dev['is_bust'] == 0]
x_pos = np.arange(len(feat_5m))
width = 0.35
bust_means = [busts_df[f].mean() for f in feat_5m]
win_means = [wins_df[f].mean() for f in feat_5m]
# Normalize for display
all_means = np.array(bust_means + win_means)
scale = np.max(np.abs(all_means[~np.isnan(all_means)])) if len(all_means) > 0 else 1
bust_normed = np.array(bust_means) / scale
win_normed = np.array(win_means) / scale
ax.bar(x_pos - width/2, bust_normed, width, label='Bust', color='#e74c3c', alpha=0.8)
ax.bar(x_pos + width/2, win_normed, width, label='Win', color='#27ae60', alpha=0.8)
ax.set_xticks(x_pos)
ax.set_xticklabels([f.replace('5m_', '') for f in feat_5m], fontsize=9)
ax.set_ylabel('Normalized Mean')
ax.set_title('5m Features: Bust vs Win (Dev Set)')
ax.legend()
ax.grid(True, alpha=0.3, axis='y')

# Plot 3: Level distribution
ax = axes[1, 0]
levels = sorted(level_counts.keys())
counts = [level_counts[lv] for lv in levels]
labels = [f'L{lv}' if lv >= 0 else 'BUST' for lv in levels]
colors = ['#27ae60' if lv >= 0 else '#e74c3c' for lv in levels]
ax.bar(range(len(levels)), counts, color=colors, edgecolor='black', alpha=0.8)
ax.set_xticks(range(len(levels)))
ax.set_xticklabels(labels, fontsize=8)
for idx, (lv, cnt) in enumerate(zip(levels, counts)):
    ax.text(idx, cnt + 0.5, f'{cnt}\n({cnt/n_cycles*100:.1f}%)',
            ha='center', fontsize=7)
ax.set_ylabel('Count')
ax.set_title(f'Cycle Outcome Distribution (n={n_cycles})')
ax.grid(True, alpha=0.3, axis='y')

# Plot 4: Equity curve with bust markers
ax = axes[1, 1]
eq_curve = [EQUITY_START]
for c in cycles:
    eq_curve.append(eq_curve[-1] + c['pnl'])
ax.plot(range(len(eq_curve)), eq_curve, 'b-', linewidth=0.8, alpha=0.8)
bust_idxs = [i+1 for i, c in enumerate(cycles) if c['is_bust']]
if bust_idxs:
    ax.scatter(bust_idxs, [eq_curve[bi] for bi in bust_idxs],
               color='red', s=40, zorder=5, marker='v', label=f'Busts ({len(bust_idxs)})')
# Mark split point
split_cycle = None
for ci, c in enumerate(cycles):
    if c['timestamp'] >= split_ts:
        split_cycle = ci + 1
        break
if split_cycle:
    ax.axvline(x=split_cycle, color='orange', linestyle='--', linewidth=2,
               label=f'Dev/Holdout split ({SPLIT_DATE})')
ax.set_xlabel('Cycle #')
ax.set_ylabel('Equity ($)')
ax.set_title('Equity Curve with Dev/Holdout Split')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Plot 5: Feature importance proxy — point-biserial correlation with bust
ax = axes[2, 0]
from scipy import stats as sp_stats
correlations = {}
for fn in feature_names:
    valid = df_dev[[fn, 'is_bust']].dropna()
    if len(valid) > 10:
        r, p = sp_stats.pointbiserialr(valid['is_bust'], valid[fn])
        correlations[fn] = (r, p)
if correlations:
    sorted_feats = sorted(correlations.keys(), key=lambda x: abs(correlations[x][0]), reverse=True)
    top_n = min(25, len(sorted_feats))
    top_feats = sorted_feats[:top_n]
    rs = [correlations[f][0] for f in top_feats]
    ps = [correlations[f][1] for f in top_feats]
    colors_corr = ['#e74c3c' if p < 0.05 else '#95a5a6' for p in ps]
    ax.barh(range(top_n), rs, color=colors_corr, edgecolor='black', alpha=0.8)
    ax.set_yticks(range(top_n))
    ax.set_yticklabels([f.replace('_', ' ') for f in top_feats], fontsize=7)
    ax.set_xlabel('Point-biserial r with bust')
    ax.set_title('Feature-Bust Correlation (red = p<0.05)')
    ax.axvline(x=0, color='black', linewidth=0.5)
    ax.grid(True, alpha=0.3, axis='x')

# Plot 6: Timeline of cycles colored by outcome
ax = axes[2, 1]
timestamps_dt = [datetime.fromtimestamp(c['timestamp']/1000, tz=timezone.utc)
                 for c in cycles]
pnl_pcts = [c['pnl_pct'] for c in cycles]
colors_tl = ['#e74c3c' if c['is_bust'] else '#27ae60' for c in cycles]
ax.scatter(timestamps_dt, pnl_pcts, c=colors_tl, s=10, alpha=0.6)
ax.axhline(y=0, color='black', linewidth=0.5)
if split_cycle:
    split_dt = datetime.fromtimestamp(split_ts/1000, tz=timezone.utc)
    ax.axvline(x=split_dt, color='orange', linestyle='--', linewidth=2,
               label=f'Split: {SPLIT_DATE}')
ax.set_xlabel('Date')
ax.set_ylabel('Cycle P&L %')
ax.set_title('Cycle P&L Over Time (green=win, red=bust)')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)
ax.tick_params(axis='x', rotation=30)

plt.suptitle(
    f'Step 15: Feature Engineering Diagnostics\n'
    f'{n_cycles} cycles | {len(feature_names)} features | '
    f'Dev: {len(df_dev)} cycles | Holdout: {len(df_holdout)} cycles',
    fontsize=13, fontweight='bold', y=1.01
)
plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, '15_data_features.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  Saved: {OUTPUT_DIR}/15_data_features.png")


# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"""
  Data: {EXCHANGE} {SYMBOL} 1m -> resampled to 5m/15m/1H/4H/D1
  Period: {DATA_START} to {DATA_END}
  Split: Dev < {SPLIT_DATE}, Holdout >= {SPLIT_DATE}

  Cycle simulation:
    {MAX_LEVELS} levels, sqrt(2) multiplier, {BASE_PCT*100:.1f}% base
    TP = {TP_ATR_MULT} x ATR, hedge ratio = {HEDGE_RATIO}
    Total cycles: {n_cycles:,}
    Bust rate: {bust_rate:.2f}%

  Feature matrix:
    {len(feature_names)} features (5 indicators x 5 timeframes)
    Dev set: {len(df_dev):,} cycles ({df_dev['is_bust'].mean()*100:.2f}% busts)
    Holdout: {len(df_holdout):,} cycles ({df_holdout['is_bust'].mean()*100:.2f}% busts)

  Top correlated features with bust (dev set):""")

if correlations:
    for fn in sorted_feats[:5]:
        r, p = correlations[fn]
        sig = "*" if p < 0.05 else ""
        print(f"    {fn}: r={r:+.4f} (p={p:.4f}){sig}")

print(f"""
  Output files:
    {dev_path}
    {holdout_path}
    {full_path}
    {OUTPUT_DIR}/15_data_features.png
""")
print("=" * 80)
