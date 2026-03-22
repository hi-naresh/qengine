#!/usr/bin/env python3
"""Step 4 Research: Cooldown + Session Analysis for Surefire Hedge V2"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os, sys
import numpy as np
from datetime import datetime, timezone

os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import qengine.indicators as ta
import qengine.helpers as jh
from qengine.research import get_candles

# ─── Load data ───────────────────────────────────────────────────────────────
print("Loading EUR-USD 5m candles from OANDA...")
warmup_candles, candles = get_candles('OANDA', 'EUR-USD', '5m',
    jh.date_to_timestamp('2024-01-01'), jh.date_to_timestamp('2026-03-01'),
    warmup_candles_num=210)
if warmup_candles is not None and warmup_candles.ndim == 2 and len(warmup_candles) > 0:
    candles = np.concatenate([warmup_candles, candles], axis=0)

print(f"Total candles: {len(candles)}")

# ─── Constants ────────────────────────────────────────────────────────────────
PIP_SIZE = 0.0001
TP_ATR_MULTIPLE = 0.8
RISK_REWARD = 2.0
ATR_PERIOD = 14
LOOKFORWARD = 500  # max bars to look forward for resolution

# ─── Compute indicators (pass candles, use sequential=True) ──────────────────
close = candles[:, 2]
high = candles[:, 3]
low = candles[:, 4]
timestamps = candles[:, 0]

ema8 = ta.ema(candles, period=8, sequential=True)
ema21 = ta.ema(candles, period=21, sequential=True)
atr = ta.atr(candles, period=ATR_PERIOD, sequential=True)

print(f"EMA8 shape: {ema8.shape}, EMA21 shape: {ema21.shape}, ATR shape: {atr.shape}")

# ─── Simulation function ─────────────────────────────────────────────────────
def simulate_first_leg(entry_price, direction, tp_dist, hedge_dist, future_highs, future_lows):
    if direction == 'long':
        tp_price = entry_price + tp_dist
        hedge_price = entry_price - hedge_dist
        for j in range(len(future_highs)):
            if future_highs[j] >= tp_price and future_lows[j] <= hedge_price:
                return 'loss'
            if future_highs[j] >= tp_price:
                return 'win'
            if future_lows[j] <= hedge_price:
                return 'loss'
    else:
        tp_price = entry_price - tp_dist
        hedge_price = entry_price + hedge_dist
        for j in range(len(future_lows)):
            if future_lows[j] <= tp_price and future_highs[j] >= hedge_price:
                return 'loss'
            if future_lows[j] <= tp_price:
                return 'win'
            if future_highs[j] >= hedge_price:
                return 'loss'
    return 'timeout'

# ─── Helper: get UTC hour from timestamp (ms) ────────────────────────────────
def get_utc_hour(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).hour

def get_session(hour):
    if 0 <= hour < 8:
        return 'Tokyo'
    elif 8 <= hour < 13:
        return 'London'
    elif 13 <= hour < 17:
        return 'Overlap'
    elif 17 <= hour < 22:
        return 'New York'
    else:
        return 'Off Hours'

# ─── Identify crossover signals ──────────────────────────────────────────────
print("\nIdentifying EMA(8)/EMA(21) crossover signals...")
signals = []  # (bar_index, direction, hour, session)
for i in range(211, len(candles) - LOOKFORWARD):
    # Crossover detection
    if ema8[i-1] <= ema21[i-1] and ema8[i] > ema21[i]:
        direction = 'long'
    elif ema8[i-1] >= ema21[i-1] and ema8[i] < ema21[i]:
        direction = 'short'
    else:
        continue

    hour = get_utc_hour(timestamps[i])
    session = get_session(hour)
    signals.append((i, direction, hour, session))

print(f"Total crossover signals: {len(signals)}")

# ─── Run simulation for all signals ──────────────────────────────────────────
print("\nRunning simulation for all signals...")
results = []  # (bar_index, direction, hour, session, outcome, atr_val)
for idx, direction, hour, session in signals:
    entry_price = close[idx]
    atr_val = atr[idx]
    if np.isnan(atr_val) or atr_val < PIP_SIZE:
        continue

    tp_dist = atr_val * TP_ATR_MULTIPLE
    hedge_dist = tp_dist * RISK_REWARD

    future_highs = high[idx+1 : idx+1+LOOKFORWARD]
    future_lows = low[idx+1 : idx+1+LOOKFORWARD]

    outcome = simulate_first_leg(entry_price, direction, tp_dist, hedge_dist, future_highs, future_lows)
    results.append((idx, direction, hour, session, outcome, atr_val))

print(f"Total simulated cycles: {len(results)}")
total_wins = sum(1 for r in results if r[4] == 'win')
total_losses = sum(1 for r in results if r[4] == 'loss')
total_timeouts = sum(1 for r in results if r[4] == 'timeout')
print(f"Overall: {total_wins} wins, {total_losses} losses, {total_timeouts} timeouts")
print(f"Overall win rate (excl timeouts): {total_wins/(total_wins+total_losses)*100:.1f}%")

# ═══════════════════════════════════════════════════════════════════════════════
# (a) SESSION ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("SESSION ANALYSIS")
print("="*70)

sessions_order = ['Tokyo', 'London', 'Overlap', 'New York', 'Off Hours']
session_stats = {}

for sess in sessions_order:
    sess_results = [r for r in results if r[3] == sess]
    wins = sum(1 for r in sess_results if r[4] == 'win')
    losses = sum(1 for r in sess_results if r[4] == 'loss')
    timeouts = sum(1 for r in sess_results if r[4] == 'timeout')
    resolved = wins + losses
    wr = wins / resolved * 100 if resolved > 0 else 0
    avg_atr = np.mean([r[5] for r in sess_results]) if sess_results else 0
    avg_atr_pips = avg_atr / PIP_SIZE

    session_stats[sess] = {
        'wins': wins, 'losses': losses, 'timeouts': timeouts,
        'total': len(sess_results), 'win_rate': wr, 'avg_atr_pips': avg_atr_pips
    }

    print(f"\n{sess:12s}: {len(sess_results):4d} signals | "
          f"W:{wins:4d} L:{losses:4d} T:{timeouts:3d} | "
          f"WR: {wr:5.1f}% | Avg ATR: {avg_atr_pips:.1f} pips")

# ═══════════════════════════════════════════════════════════════════════════════
# (b) COOLDOWN ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("COOLDOWN ANALYSIS")
print("="*70)

cooldown_values = [0, 5, 10, 20, 30, 50, 100, 200]
cooldown_stats = {}

for cd in cooldown_values:
    # Sequential simulation with cooldown
    wins = 0
    losses = 0
    timeouts = 0
    next_allowed_bar = 0
    consecutive_losses = []
    current_streak = 0

    for idx, direction, hour, session, outcome, atr_val in results:
        if idx < next_allowed_bar:
            continue

        if outcome == 'win':
            wins += 1
            if current_streak > 0:
                consecutive_losses.append(current_streak)
            current_streak = 0
            next_allowed_bar = idx + 1  # no extra cooldown after win
        elif outcome == 'loss':
            losses += 1
            current_streak += 1
            next_allowed_bar = idx + 1 + cd  # cooldown after loss
        else:
            timeouts += 1
            next_allowed_bar = idx + 1

    if current_streak > 0:
        consecutive_losses.append(current_streak)

    resolved = wins + losses
    wr = wins / resolved * 100 if resolved > 0 else 0
    total_cycles = wins + losses + timeouts

    # P(next cycle also loses after a loss)
    loss_to_loss = 0
    loss_to_win = 0
    prev_outcome = None
    next_allowed_bar = 0
    for idx, direction, hour, session, outcome, atr_val in results:
        if idx < next_allowed_bar:
            continue
        if prev_outcome == 'loss':
            if outcome == 'win':
                loss_to_win += 1
            elif outcome == 'loss':
                loss_to_loss += 1
        prev_outcome = outcome
        if outcome == 'loss':
            next_allowed_bar = idx + 1 + cd
        else:
            next_allowed_bar = idx + 1

    p_loss_after_loss = loss_to_loss / (loss_to_loss + loss_to_win) * 100 if (loss_to_loss + loss_to_win) > 0 else 0
    avg_consec = np.mean(consecutive_losses) if consecutive_losses else 0
    max_consec = max(consecutive_losses) if consecutive_losses else 0

    cooldown_stats[cd] = {
        'wins': wins, 'losses': losses, 'timeouts': timeouts,
        'total': total_cycles, 'win_rate': wr,
        'p_loss_after_loss': p_loss_after_loss,
        'avg_consec_loss': avg_consec, 'max_consec_loss': max_consec
    }

    print(f"Cooldown {cd:3d} bars: {total_cycles:4d} cycles | "
          f"WR: {wr:5.1f}% | P(loss|loss): {p_loss_after_loss:5.1f}% | "
          f"Avg streak: {avg_consec:.1f} | Max streak: {max_consec}")

# ═══════════════════════════════════════════════════════════════════════════════
# (c) TIME-OF-DAY ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("TIME-OF-DAY ANALYSIS (Win Rate by UTC Hour)")
print("="*70)

hour_stats = {}
for h in range(24):
    hr_results = [r for r in results if r[2] == h]
    wins = sum(1 for r in hr_results if r[4] == 'win')
    losses = sum(1 for r in hr_results if r[4] == 'loss')
    resolved = wins + losses
    wr = wins / resolved * 100 if resolved > 0 else 0
    hour_stats[h] = {'wins': wins, 'losses': losses, 'total': len(hr_results),
                     'resolved': resolved, 'win_rate': wr}
    print(f"  Hour {h:02d}: {resolved:4d} resolved | WR: {wr:5.1f}% | "
          f"(W:{wins}, L:{losses})")

# ═══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ═══════════════════════════════════════════════════════════════════════════════
output_dir = '/Users/naresh/Documents/Research/qengine/notebooks/surefire_v2'
os.makedirs(output_dir, exist_ok=True)

# --- Chart 1: Session Win Rate + ATR ---
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

sess_names = sessions_order
sess_wr = [session_stats[s]['win_rate'] for s in sess_names]
sess_atr = [session_stats[s]['avg_atr_pips'] for s in sess_names]
sess_counts = [session_stats[s]['total'] for s in sess_names]
colors = ['#e74c3c', '#2ecc71', '#f39c12', '#3498db', '#95a5a6']

bars1 = ax1.bar(sess_names, sess_wr, color=colors, edgecolor='black', alpha=0.8)
ax1.axhline(y=33.3, color='red', linestyle='--', alpha=0.5, label='Baseline 33%')
for bar, count in zip(bars1, sess_counts):
    ax1.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.5,
             f'n={count}', ha='center', va='bottom', fontsize=9)
ax1.set_ylabel('Win Rate (%)')
ax1.set_title('Win Rate by Session')
ax1.legend()
ax1.set_ylim(0, max(sess_wr) * 1.3 if max(sess_wr) > 0 else 50)

bars2 = ax2.bar(sess_names, sess_atr, color=colors, edgecolor='black', alpha=0.8)
ax2.set_ylabel('Avg ATR (pips)')
ax2.set_title('Average ATR by Session')
for bar, val in zip(bars2, sess_atr):
    ax2.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.1,
             f'{val:.1f}', ha='center', va='bottom', fontsize=9)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'results/03_session_analysis.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {output_dir}/03_session_analysis.png")

# --- Chart 2: Cooldown Analysis ---
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

cd_vals = cooldown_values
cd_wr = [cooldown_stats[c]['win_rate'] for c in cd_vals]
cd_ploss = [cooldown_stats[c]['p_loss_after_loss'] for c in cd_vals]
cd_cycles = [cooldown_stats[c]['total'] for c in cd_vals]

ax1.plot(cd_vals, cd_wr, 'bo-', linewidth=2, markersize=8)
for x, y, n in zip(cd_vals, cd_wr, cd_cycles):
    ax1.annotate(f'n={n}', (x, y), textcoords="offset points", xytext=(0, 10),
                ha='center', fontsize=8)
ax1.axhline(y=33.3, color='red', linestyle='--', alpha=0.5, label='Baseline 33%')
ax1.set_xlabel('Cooldown Bars After Loss')
ax1.set_ylabel('Win Rate (%)')
ax1.set_title('Win Rate vs Cooldown Period')
ax1.legend()
ax1.grid(True, alpha=0.3)

ax2.plot(cd_vals, cd_ploss, 'rs-', linewidth=2, markersize=8)
ax2.set_xlabel('Cooldown Bars After Loss')
ax2.set_ylabel('P(Loss | Previous Loss) %')
ax2.set_title('Consecutive Loss Probability vs Cooldown')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'results/03_cooldown_analysis.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {output_dir}/03_cooldown_analysis.png")

# --- Chart 3: Time-of-Day Win Rate ---
fig, ax = plt.subplots(figsize=(14, 5))

hours = list(range(24))
hr_wr = [hour_stats[h]['win_rate'] for h in hours]
hr_counts = [hour_stats[h]['resolved'] for h in hours]

# Color bars by session
bar_colors = []
for h in hours:
    sess = get_session(h)
    color_map = {'Tokyo': '#e74c3c', 'London': '#2ecc71', 'Overlap': '#f39c12',
                 'New York': '#3498db', 'Off Hours': '#95a5a6'}
    bar_colors.append(color_map[sess])

bars = ax.bar(hours, hr_wr, color=bar_colors, edgecolor='black', alpha=0.8)
ax.axhline(y=33.3, color='red', linestyle='--', alpha=0.5, label='Baseline 33%')
for h, wr, n in zip(hours, hr_wr, hr_counts):
    if n > 0:
        ax.text(h, wr + 0.5, f'{n}', ha='center', va='bottom', fontsize=7, rotation=90)

ax.set_xlabel('UTC Hour')
ax.set_ylabel('Win Rate (%)')
ax.set_title('Win Rate by Hour of Day (colored by session)')
ax.set_xticks(hours)
ax.legend()
ax.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'results/03_time_of_day.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {output_dir}/03_time_of_day.png")

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("SUMMARY")
print("="*70)

best_session = max(sessions_order, key=lambda s: session_stats[s]['win_rate'])
worst_session = min(sessions_order, key=lambda s: session_stats[s]['win_rate'])
best_hour = max(range(24), key=lambda h: hour_stats[h]['win_rate'] if hour_stats[h]['resolved'] > 10 else 0)
best_cooldown = max(cooldown_values, key=lambda c: cooldown_stats[c]['win_rate'])

print(f"\nBest session:  {best_session} ({session_stats[best_session]['win_rate']:.1f}% WR)")
print(f"Worst session: {worst_session} ({session_stats[worst_session]['win_rate']:.1f}% WR)")
print(f"Best hour:     {best_hour:02d} UTC ({hour_stats[best_hour]['win_rate']:.1f}% WR, n={hour_stats[best_hour]['resolved']})")
print(f"Best cooldown: {best_cooldown} bars ({cooldown_stats[best_cooldown]['win_rate']:.1f}% WR)")

# Does cooldown help?
cd0_wr = cooldown_stats[0]['win_rate']
cd_best_wr = cooldown_stats[best_cooldown]['win_rate']
print(f"\nCooldown improvement: {cd0_wr:.1f}% -> {cd_best_wr:.1f}% ({cd_best_wr - cd0_wr:+.1f}%)")
print(f"P(loss|loss) at cd=0: {cooldown_stats[0]['p_loss_after_loss']:.1f}%")
print(f"P(loss|loss) at cd={best_cooldown}: {cooldown_stats[best_cooldown]['p_loss_after_loss']:.1f}%")

print("\nDone!")
