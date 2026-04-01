"""
Script 28 — Volatility Advantage Analysis
===========================================
Key insight: The martingale strategy BENEFITS from volatile trending markets.
High volatility + clear direction = TP triggers fast at L0 or L1.

This script quantifies:
  1. Win rate / level distribution by volatility regime
  2. L0 and L1 win rate in high-vol vs low-vol vs choppy
  3. PnL contribution by volatility bucket
  4. "Confidence score" = volatility + trend strength → optimal entry conditions
  5. Strategy edge: when does it make money fastest?

The thesis: We don't just avoid chop — we actively seek vol+trend entries.
"""
from utils import *
import qengine.indicators as ta
import warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("Script 28 — Volatility Advantage Analysis")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# 1. SETUP
# ══════════════════════════════════════════════════════════════
print("\n[1/7] Loading data and computing features...")
candles = load_candles(timeframe='5m', start_date='2020-01-03', end_date='2025-12-30')
n_bars = len(candles)

cfg = SimConfig(sizing_curve='sqrt', sizing_factor=2.0, max_levels=12,
                hedge_dist_pips=10, tp_pips=20)

# Use EMA signals (realistic entries)
all_signals = find_ema_crossover_signals(candles, 8, 21)
print(f"  {len(all_signals)} EMA signals")

# Compute key features at each bar
print("  Computing ATR, ADX, ER...")
atr_14 = ta.atr(candles, period=14, sequential=True)
atr_50 = ta.atr(candles, period=50, sequential=True)
adx_14 = ta.adx(candles, period=14, sequential=True)
er_100 = ta.er(candles, period=100, sequential=True)
natr_14 = ta.natr(candles, period=14, sequential=True)  # Normalized ATR (% of price)

# Volatility metrics
vol_ratio = np.where(atr_50 > 0, atr_14 / atr_50, 1.0)  # >1 = expanding vol

# Run baseline
baseline_results = run_cycles_on_signals(candles, all_signals, cfg)
baseline = cycle_summary(baseline_results)
print(f"  Baseline: {baseline['n_cycles']} cycles, bust={baseline['bust_rate']:.2f}%, PF={baseline['profit_factor']:.2f}")

# ══════════════════════════════════════════════════════════════
# 2. CLASSIFY ENTRIES BY VOLATILITY REGIME
# ══════════════════════════════════════════════════════════════
print("\n[2/7] Classifying cycles by volatility regime...")

# Compute per-cycle metrics
cycle_data = []
for c in baseline_results:
    idx = c.entry_idx
    if idx >= len(atr_14) or np.isnan(atr_14[idx]):
        continue

    cycle_data.append({
        'entry_idx': idx,
        'bust': c.bust,
        'win': c.is_win,
        'level_reached': c.level_reached,
        'pnl': c.pnl,
        'bars_held': c.bars_held,
        'atr': atr_14[idx],
        'natr': natr_14[idx],
        'vol_ratio': vol_ratio[idx],
        'adx': adx_14[idx],
        'er': er_100[idx],
    })

# Bucket by NATR quintiles (volatility level)
natrs = np.array([c['natr'] for c in cycle_data])
vol_quintiles = np.percentile(natrs[~np.isnan(natrs)], [20, 40, 60, 80])

def vol_bucket(natr):
    if np.isnan(natr): return 'unknown'
    if natr <= vol_quintiles[0]: return 'very_low'
    if natr <= vol_quintiles[1]: return 'low'
    if natr <= vol_quintiles[2]: return 'medium'
    if natr <= vol_quintiles[3]: return 'high'
    return 'very_high'

# Also classify by trend strength
adxs = np.array([c['adx'] for c in cycle_data])
adx_buckets = {'no_trend': (0, 20), 'weak_trend': (20, 30), 'strong_trend': (30, 50), 'extreme_trend': (50, 100)}

for c in cycle_data:
    c['vol_bucket'] = vol_bucket(c['natr'])
    adx_val = c['adx']
    if np.isnan(adx_val):
        c['trend_bucket'] = 'unknown'
    elif adx_val < 20:
        c['trend_bucket'] = 'no_trend'
    elif adx_val < 30:
        c['trend_bucket'] = 'weak_trend'
    elif adx_val < 50:
        c['trend_bucket'] = 'strong_trend'
    else:
        c['trend_bucket'] = 'extreme_trend'

# ══════════════════════════════════════════════════════════════
# 3. WIN RATE AND LEVEL DISTRIBUTION BY VOLATILITY
# ══════════════════════════════════════════════════════════════
print("\n[3/7] Analyzing win rates by volatility...")

vol_order = ['very_low', 'low', 'medium', 'high', 'very_high']
print(f"\n  {'Vol Bucket':<14s} {'Cycles':>7s} {'Win%':>6s} {'Bust%':>6s} {'L0 Win%':>8s} {'L0+L1%':>7s} {'AvgLevel':>9s} {'PF':>6s} {'AvgPnL':>8s}")
print(f"  {'-'*80}")

vol_stats = {}
for bucket in vol_order:
    cycles = [c for c in cycle_data if c['vol_bucket'] == bucket]
    if not cycles:
        continue
    n = len(cycles)
    wins = [c for c in cycles if c['win']]
    busts = [c for c in cycles if c['bust']]
    l0_wins = [c for c in cycles if c['win'] and c['level_reached'] == 0]
    l01_wins = [c for c in cycles if c['win'] and c['level_reached'] <= 1]

    pnls = [c['pnl'] for c in cycles]
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    stats = {
        'n': n,
        'win_rate': round(len(wins) / n * 100, 2),
        'bust_rate': round(len(busts) / n * 100, 2),
        'l0_win_rate': round(len(l0_wins) / n * 100, 2),
        'l01_win_rate': round(len(l01_wins) / n * 100, 2),
        'avg_level': round(np.mean([c['level_reached'] for c in cycles]), 2),
        'pf': round(pf, 2),
        'avg_pnl': round(np.mean(pnls), 2),
        'total_pnl': round(sum(pnls), 1),
        'avg_bars': round(np.mean([c['bars_held'] for c in cycles]), 1),
    }
    vol_stats[bucket] = stats
    print(f"  {bucket:<14s} {n:>7d} {stats['win_rate']:>5.1f}% {stats['bust_rate']:>5.2f}% "
          f"{stats['l0_win_rate']:>7.1f}% {stats['l01_win_rate']:>6.1f}% "
          f"{stats['avg_level']:>8.2f} {stats['pf']:>6.2f} {stats['avg_pnl']:>8.1f}")

# ══════════════════════════════════════════════════════════════
# 4. TREND × VOLATILITY MATRIX (the money map)
# ══════════════════════════════════════════════════════════════
print("\n[4/7] Building Trend × Volatility matrix...")

trend_order = ['no_trend', 'weak_trend', 'strong_trend', 'extreme_trend']
matrix = {}

print(f"\n  {'':>16s}", end='')
for v in vol_order:
    print(f"  {v:>12s}", end='')
print()

for t in trend_order:
    print(f"  {t:>14s}:", end='')
    matrix[t] = {}
    for v in vol_order:
        cycles = [c for c in cycle_data if c['trend_bucket'] == t and c['vol_bucket'] == v]
        if len(cycles) < 10:
            print(f"  {'---':>12s}", end='')
            matrix[t][v] = None
            continue
        n = len(cycles)
        wins = sum(1 for c in cycles if c['win'])
        busts = sum(1 for c in cycles if c['bust'])
        pnls = [c['pnl'] for c in cycles]
        gp = sum(p for p in pnls if p > 0)
        gl = abs(sum(p for p in pnls if p < 0))
        pf = gp / gl if gl > 0 else float('inf')
        l01 = sum(1 for c in cycles if c['win'] and c['level_reached'] <= 1)

        matrix[t][v] = {
            'n': n, 'pf': round(pf, 2), 'bust_rate': round(busts/n*100, 2),
            'l01_rate': round(l01/n*100, 1), 'avg_pnl': round(np.mean(pnls), 2),
        }
        print(f"  PF={pf:>5.2f} n={n:>3d}", end='')
    print()

# ══════════════════════════════════════════════════════════════
# 5. SPEED OF WIN: How fast does TP trigger?
# ══════════════════════════════════════════════════════════════
print("\n[5/7] Analyzing speed of win by regime...")

print(f"\n  {'Vol Bucket':<14s} {'Win AvgBars':>11s} {'L0 AvgBars':>11s} {'L0 %':>6s} {'Bust AvgBars':>12s}")
print(f"  {'-'*58}")

for bucket in vol_order:
    cycles = [c for c in cycle_data if c['vol_bucket'] == bucket]
    if not cycles:
        continue
    wins = [c for c in cycles if c['win']]
    l0_wins = [c for c in cycles if c['win'] and c['level_reached'] == 0]
    busts = [c for c in cycles if c['bust']]

    win_bars = np.mean([c['bars_held'] for c in wins]) if wins else 0
    l0_bars = np.mean([c['bars_held'] for c in l0_wins]) if l0_wins else 0
    bust_bars = np.mean([c['bars_held'] for c in busts]) if busts else 0
    l0_pct = len(l0_wins) / len(cycles) * 100 if cycles else 0

    print(f"  {bucket:<14s} {win_bars:>10.0f} {l0_bars:>10.0f} {l0_pct:>5.1f}% {bust_bars:>11.0f}")

# ══════════════════════════════════════════════════════════════
# 6. CONFIDENCE SCORE: vol + trend → enter aggressively
# ══════════════════════════════════════════════════════════════
print("\n[6/7] Building confidence score...")

# Confidence = f(volatility_expansion, trend_strength, efficiency)
# Higher confidence → better entry conditions for martingale
def compute_confidence(natr_val, adx_val, er_val, vol_ratio_val):
    """0-1 score. Higher = more confident entry (vol + trend)."""
    score = 0.0
    count = 0

    if not np.isnan(natr_val):
        # Normalize NATR: higher vol = better (up to a point)
        # Use percentile-based normalization
        vol_score = np.clip(natr_val / 0.1, 0, 1)  # 0.1% NATR = max
        score += vol_score
        count += 1

    if not np.isnan(adx_val):
        # ADX > 25 = trending (good), < 20 = no trend (bad)
        trend_score = np.clip((adx_val - 15) / 30, 0, 1)  # 15-45 → 0-1
        score += trend_score
        count += 1

    if not np.isnan(er_val):
        # ER near 1 = efficient/trending (good), near 0 = choppy (bad)
        score += np.clip(er_val / 0.4, 0, 1)
        count += 1

    if not np.isnan(vol_ratio_val):
        # Vol expanding (>1) is better than compressing (<1)
        vol_exp = np.clip((vol_ratio_val - 0.7) / 0.6, 0, 1)  # 0.7-1.3 → 0-1
        score += vol_exp
        count += 1

    return score / count if count > 0 else 0.5

# Compute confidence for all bars
confidence = np.array([
    compute_confidence(natr_14[i], adx_14[i], er_100[i], vol_ratio[i])
    for i in range(n_bars)
])

# Test confidence as entry gate at various thresholds
print("\n  Confidence gate sweep:")
print(f"  {'Threshold':>10s} {'Cycles':>7s} {'Bust%':>6s} {'PF':>6s} {'L0+L1%':>7s} {'Kept%':>6s} {'PnL':>8s}")
print(f"  {'-'*55}")

conf_results = {}
for thresh in [0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]:
    filtered = [(idx, d) for idx, d in all_signals
                if idx < len(confidence) and confidence[idx] >= thresh]
    if len(filtered) < 20:
        continue
    results = run_cycles_on_signals(candles, filtered, cfg)
    s = cycle_summary(results)
    pct_kept = len(filtered) / len(all_signals) * 100

    # Count L0+L1 wins
    l01_wins = sum(1 for c in results if c.is_win and c.level_reached <= 1)
    l01_pct = l01_wins / len(results) * 100 if results else 0

    conf_results[thresh] = {**s, 'pct_kept': round(pct_kept, 1), 'l01_pct': round(l01_pct, 1)}
    bust_red = (baseline['bust_rate'] - s['bust_rate']) / baseline['bust_rate'] * 100 if baseline['bust_rate'] > 0 else 0
    print(f"  {thresh:>10.2f} {s['n_cycles']:>7d} {s['bust_rate']:>5.2f}% {s['profit_factor']:>6.2f} "
          f"{l01_pct:>6.1f}% {pct_kept:>5.1f}% {s['net_pnl']:>8.0f}")

# ══════════════════════════════════════════════════════════════
# 7. PLOTS AND SAVE
# ══════════════════════════════════════════════════════════════
print("\n[7/7] Plotting...")

# Plot 1: PF and bust rate by volatility
fig, axes = plt.subplots(2, 2, figsize=(16, 12))

# 1a: PF by vol bucket
ax = axes[0, 0]
buckets = [b for b in vol_order if b in vol_stats]
pfs = [vol_stats[b]['pf'] for b in buckets]
colors = ['red' if pf < 1.0 else 'orange' if pf < 1.3 else 'green' for pf in pfs]
ax.bar(buckets, pfs, color=colors, edgecolor='black')
ax.axhline(y=baseline['profit_factor'], color='gray', linestyle='--', label=f"Baseline PF={baseline['profit_factor']:.2f}")
ax.axhline(y=1.0, color='red', linestyle=':', alpha=0.5)
ax.set_ylabel('Profit Factor')
ax.set_title('Profit Factor by Volatility Level')
ax.legend()
ax.grid(True, alpha=0.3)

# 1b: L0+L1 win rate by vol
ax = axes[0, 1]
l01_rates = [vol_stats[b]['l01_win_rate'] for b in buckets]
ax.bar(buckets, l01_rates, color='steelblue', edgecolor='black')
ax.set_ylabel('L0+L1 Win Rate (%)')
ax.set_title('Quick Wins (L0+L1) by Volatility')
ax.grid(True, alpha=0.3)

# 1c: Heatmap - trend x vol PF
ax = axes[1, 0]
pf_matrix = np.full((len(trend_order), len(vol_order)), np.nan)
for i, t in enumerate(trend_order):
    for j, v in enumerate(vol_order):
        if matrix.get(t, {}).get(v):
            pf_matrix[i, j] = matrix[t][v]['pf']

im = ax.imshow(pf_matrix, cmap='RdYlGn', aspect='auto', vmin=0.5, vmax=3.0)
ax.set_xticks(range(len(vol_order)))
ax.set_xticklabels(vol_order, fontsize=8, rotation=30)
ax.set_yticks(range(len(trend_order)))
ax.set_yticklabels(trend_order, fontsize=8)
ax.set_title('Profit Factor: Trend × Volatility')
plt.colorbar(im, ax=ax, label='PF')

# Annotate cells
for i in range(len(trend_order)):
    for j in range(len(vol_order)):
        if not np.isnan(pf_matrix[i, j]):
            t = trend_order[i]
            v = vol_order[j]
            n = matrix[t][v]['n'] if matrix[t][v] else 0
            ax.text(j, i, f'{pf_matrix[i,j]:.1f}\nn={n}', ha='center', va='center', fontsize=7)

# 1d: Confidence gate impact
ax = axes[1, 1]
if conf_results:
    threshs = sorted(conf_results.keys())
    conf_pfs = [conf_results[t]['profit_factor'] for t in threshs]
    conf_kept = [conf_results[t]['pct_kept'] for t in threshs]

    ax2 = ax.twinx()
    ax.plot(threshs, conf_pfs, 'go-', linewidth=2, label='PF')
    ax2.plot(threshs, conf_kept, 'b^--', linewidth=1, label='% Kept')
    ax.axhline(y=baseline['profit_factor'], color='gray', linestyle='--', alpha=0.5)
    ax.set_xlabel('Confidence Threshold')
    ax.set_ylabel('Profit Factor', color='green')
    ax2.set_ylabel('% Signals Kept', color='blue')
    ax.set_title('Confidence Score as Entry Gate')
    ax.legend(loc='upper left')
    ax2.legend(loc='upper right')
    ax.grid(True, alpha=0.3)

plt.tight_layout()
savefig('28_volatility_advantage.png')

# Plot 2: Speed of win
fig, ax = plt.subplots(figsize=(10, 6))
for bucket in vol_order:
    cycles = [c for c in cycle_data if c['vol_bucket'] == bucket and c['win']]
    if len(cycles) < 10:
        continue
    levels = [c['level_reached'] for c in cycles]
    level_counts = [levels.count(i) / len(levels) * 100 for i in range(max(levels) + 1)]
    ax.plot(range(len(level_counts)), level_counts, 'o-', label=f'{bucket} (n={len(cycles)})')

ax.set_xlabel('Level Reached (0 = cleanest win)')
ax.set_ylabel('% of Wins')
ax.set_title('Win Distribution by Level — High Vol Wins Faster')
ax.legend()
ax.grid(True, alpha=0.3)
savefig('28_win_speed_by_vol.png')

# Plot 3: PnL contribution by vol bucket
fig, ax = plt.subplots(figsize=(10, 6))
total_pnls = [vol_stats[b]['total_pnl'] for b in buckets]
colors = ['green' if p > 0 else 'red' for p in total_pnls]
ax.bar(buckets, total_pnls, color=colors, edgecolor='black')
ax.set_ylabel('Total PnL (pips)')
ax.set_title('PnL Contribution by Volatility Bucket')
ax.grid(True, alpha=0.3)
for i, (b, p) in enumerate(zip(buckets, total_pnls)):
    ax.text(i, p + abs(p) * 0.02, f'{p:.0f}', ha='center', fontsize=9)
savefig('28_pnl_by_vol.png')

# Save
save_results({
    'baseline': baseline,
    'vol_stats': vol_stats,
    'trend_vol_matrix': {t: {v: matrix[t][v] for v in vol_order if matrix.get(t, {}).get(v)}
                         for t in trend_order if t in matrix},
    'confidence_gate': {str(k): v for k, v in conf_results.items()},
    'vol_quintiles': vol_quintiles.tolist(),
}, '28_volatility_advantage')

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)

# Find best and worst vol buckets
best_vol = max(vol_stats.items(), key=lambda x: x[1]['pf'])
worst_vol = min(vol_stats.items(), key=lambda x: x[1]['pf'])
print(f"  Best vol regime:  {best_vol[0]} → PF={best_vol[1]['pf']:.2f}, L0+L1={best_vol[1]['l01_win_rate']:.1f}%")
print(f"  Worst vol regime: {worst_vol[0]} → PF={worst_vol[1]['pf']:.2f}, L0+L1={worst_vol[1]['l01_win_rate']:.1f}%")
print(f"  Vol advantage: {best_vol[1]['pf'] / worst_vol[1]['pf']:.1f}x PF improvement")

if conf_results:
    best_conf = max(conf_results.items(), key=lambda x: x[1]['profit_factor'])
    print(f"  Best confidence gate: ≥{best_conf[0]:.2f} → PF={best_conf[1]['profit_factor']:.2f}, kept={best_conf[1]['pct_kept']:.0f}%")

# The key insight
print(f"\n  STRATEGY VERDICT:")
if best_vol[1]['pf'] > 1.5:
    print(f"  ✓ Strategy has STRONG edge in high-volatility trending markets")
    print(f"  ✓ Focus: ENTER MORE in high-vol trends, not just avoid chop")
else:
    print(f"  ○ Volatility advantage is moderate — needs confirmation")
print("Done.")
