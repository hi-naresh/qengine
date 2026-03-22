"""
Step 3: ATR Distance Sweep — Heatmap of win rate vs (TP_ATR_MULTIPLE, RISK_REWARD)
"""
import os, sys
os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from itertools import product

from qengine.research import get_candles
import qengine.indicators as ta
import qengine.helpers as jh

# ── Config ──────────────────────────────────────────────────────────────
EXCHANGE = 'OANDA'
SYMBOL = 'EUR-USD'
TIMEFRAME = '5m'
START = '2024-01-01'
END = '2026-03-01'
ATR_PERIOD = 14
PIP_SIZE = 0.0001
MAX_BARS = 200  # timeout after this many bars

TP_MULTS = np.round(np.arange(0.3, 1.55, 0.1), 1)
RR_VALUES = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 3.5]

# ── Load candles ────────────────────────────────────────────────────────
print("Loading candles …")
warmup_candles, candles = get_candles(
    EXCHANGE, SYMBOL, TIMEFRAME,
    jh.date_to_timestamp(START),
    jh.date_to_timestamp(END),
)

if warmup_candles is not None and warmup_candles.ndim == 2 and len(warmup_candles) > 0:
    all_candles = np.concatenate([warmup_candles, candles], axis=0)
else:
    all_candles = candles

print(f"Total candles (with warmup): {len(all_candles)}")
print(f"Trading candles: {len(candles)}")

# ── Compute ATR on full array, then align to trading candles ────────────
atr_full = ta.atr(all_candles, period=ATR_PERIOD, sequential=True)
warmup_len = len(all_candles) - len(candles)
atr = atr_full[warmup_len:]  # aligned with candles

# Candle columns: [timestamp, open, close, high, low, volume]
opens  = candles[:, 1]
closes = candles[:, 2]
highs  = candles[:, 3]
lows   = candles[:, 4]

# ── Simulation function ────────────────────────────────────────────────
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

# ── Sweep ───────────────────────────────────────────────────────────────
print(f"\nSweeping {len(TP_MULTS)} TP multiples x {len(RR_VALUES)} RR values …")
print(f"TP multiples : {list(TP_MULTS)}")
print(f"RR values    : {RR_VALUES}")

# Result matrices
win_rate_matrix  = np.zeros((len(TP_MULTS), len(RR_VALUES)))
timeout_matrix   = np.zeros((len(TP_MULTS), len(RR_VALUES)))
avg_bars_matrix  = np.zeros((len(TP_MULTS), len(RR_VALUES)))
trade_count_matrix = np.zeros((len(TP_MULTS), len(RR_VALUES)))

N = len(candles)
direction = 'long'  # "Always Long" to isolate distance effect

for ti, tp_mult in enumerate(TP_MULTS):
    for ri, rr in enumerate(RR_VALUES):
        wins = 0
        losses = 0
        timeouts = 0
        total_bars = 0
        trades = 0

        for i in range(ATR_PERIOD, N - 1):
            if np.isnan(atr[i]) or atr[i] < PIP_SIZE:
                continue

            entry_price = closes[i]
            tp_dist = atr[i] * tp_mult
            hedge_dist = tp_dist * rr  # SL = TP * RR  (if RR=2, SL is 2x TP)

            end_idx = min(i + 1 + MAX_BARS, N)
            future_h = highs[i+1:end_idx]
            future_l = lows[i+1:end_idx]

            if len(future_h) == 0:
                continue

            result = simulate_first_leg(entry_price, direction, tp_dist, hedge_dist, future_h, future_l)
            trades += 1

            if result == 'win':
                wins += 1
            elif result == 'loss':
                losses += 1
            else:
                timeouts += 1

        if trades > 0:
            win_rate_matrix[ti, ri] = wins / trades * 100
            timeout_matrix[ti, ri] = timeouts / trades * 100
            trade_count_matrix[ti, ri] = trades

        print(f"  TP={tp_mult:.1f}  RR={rr:.1f}  trades={trades}  "
              f"W={wins}  L={losses}  T={timeouts}  "
              f"WR={win_rate_matrix[ti,ri]:.1f}%  TO={timeout_matrix[ti,ri]:.1f}%")

# ── Summary table ───────────────────────────────────────────────────────
print("\n" + "="*90)
print("SUMMARY: Win Rate (%) by TP_ATR_MULT (rows) x RISK_REWARD (cols)")
print("="*90)

header = f"{'TP\\RR':>8}" + "".join(f"{rr:>8.1f}" for rr in RR_VALUES)
print(header)
print("-" * len(header))

for ti, tp_mult in enumerate(TP_MULTS):
    row = f"{tp_mult:>8.1f}"
    for ri in range(len(RR_VALUES)):
        wr = win_rate_matrix[ti, ri]
        row += f"{wr:>8.1f}"
    print(row)

# ── Best combos ─────────────────────────────────────────────────────────
print("\n" + "="*90)
print("TOP 10 COMBOS by Win Rate")
print("="*90)

flat = []
for ti, tp_mult in enumerate(TP_MULTS):
    for ri, rr in enumerate(RR_VALUES):
        flat.append((win_rate_matrix[ti, ri], timeout_matrix[ti, ri], tp_mult, rr))

flat.sort(key=lambda x: -x[0])
print(f"{'Rank':>5}  {'TP_MULT':>8}  {'RR':>6}  {'Win%':>7}  {'TO%':>7}")
print("-" * 45)
for rank, (wr, to, tp, rr) in enumerate(flat[:10], 1):
    print(f"{rank:>5}  {tp:>8.1f}  {rr:>6.1f}  {wr:>7.1f}  {to:>7.1f}")

# ── Also show best expected value (accounting for RR) ───────────────────
print("\n" + "="*90)
print("TOP 10 COMBOS by Expected Value per Trade (in TP units)")
print("  EV = WR * 1.0 - LossRate * RR  (positive = profitable first leg)")
print("="*90)

ev_flat = []
for ti, tp_mult in enumerate(TP_MULTS):
    for ri, rr in enumerate(RR_VALUES):
        wr = win_rate_matrix[ti, ri] / 100
        to = timeout_matrix[ti, ri] / 100
        lr = 1.0 - wr - to
        ev = wr * 1.0 - lr * rr  # win pays 1 TP unit, loss costs RR TP units
        ev_flat.append((ev, win_rate_matrix[ti, ri], timeout_matrix[ti, ri], tp_mult, rr))

ev_flat.sort(key=lambda x: -x[0])
print(f"{'Rank':>5}  {'TP_MULT':>8}  {'RR':>6}  {'Win%':>7}  {'TO%':>7}  {'EV':>8}")
print("-" * 55)
for rank, (ev, wr, to, tp, rr) in enumerate(ev_flat[:10], 1):
    print(f"{rank:>5}  {tp:>8.1f}  {rr:>6.1f}  {wr:>7.1f}  {to:>7.1f}  {ev:>8.3f}")

# ── Heatmap ─────────────────────────────────────────────────────────────
output_dir = 'notebooks/surefire_v2'
os.makedirs(output_dir, exist_ok=True)

fig, axes = plt.subplots(1, 2, figsize=(18, 8))

# Win rate heatmap
im0 = axes[0].imshow(win_rate_matrix, aspect='auto', cmap='RdYlGn', origin='lower')
axes[0].set_xticks(range(len(RR_VALUES)))
axes[0].set_xticklabels([f"{r:.1f}" for r in RR_VALUES])
axes[0].set_yticks(range(len(TP_MULTS)))
axes[0].set_yticklabels([f"{t:.1f}" for t in TP_MULTS])
axes[0].set_xlabel('RISK_REWARD (SL = TP * RR)')
axes[0].set_ylabel('TP_ATR_MULTIPLE')
axes[0].set_title('First-Leg Win Rate (%)\n(Always Long, EUR-USD 5m)')
plt.colorbar(im0, ax=axes[0], label='Win Rate %')

# Annotate cells
for ti in range(len(TP_MULTS)):
    for ri in range(len(RR_VALUES)):
        val = win_rate_matrix[ti, ri]
        color = 'white' if val < 40 or val > 75 else 'black'
        axes[0].text(ri, ti, f"{val:.0f}", ha='center', va='center', fontsize=8, color=color)

# Expected value heatmap
ev_matrix = np.zeros_like(win_rate_matrix)
for ti in range(len(TP_MULTS)):
    for ri, rr in enumerate(RR_VALUES):
        wr = win_rate_matrix[ti, ri] / 100
        to = timeout_matrix[ti, ri] / 100
        lr = 1.0 - wr - to
        ev_matrix[ti, ri] = wr * 1.0 - lr * rr

im1 = axes[1].imshow(ev_matrix, aspect='auto', cmap='RdYlGn', origin='lower')
axes[1].set_xticks(range(len(RR_VALUES)))
axes[1].set_xticklabels([f"{r:.1f}" for r in RR_VALUES])
axes[1].set_yticks(range(len(TP_MULTS)))
axes[1].set_yticklabels([f"{t:.1f}" for t in TP_MULTS])
axes[1].set_xlabel('RISK_REWARD (SL = TP * RR)')
axes[1].set_ylabel('TP_ATR_MULTIPLE')
axes[1].set_title('Expected Value per Trade (TP units)\n(Always Long, EUR-USD 5m)')
plt.colorbar(im1, ax=axes[1], label='EV (TP units)')

for ti in range(len(TP_MULTS)):
    for ri in range(len(RR_VALUES)):
        val = ev_matrix[ti, ri]
        color = 'white' if val < -0.2 or val > 0.3 else 'black'
        axes[1].text(ri, ti, f"{val:.2f}", ha='center', va='center', fontsize=7, color=color)

plt.tight_layout()
chart_path = os.path.join(output_dir, 'results/02_distance_heatmap.png')
plt.savefig(chart_path, dpi=150, bbox_inches='tight')
print(f"\nChart saved to {chart_path}")
print("Done.")
