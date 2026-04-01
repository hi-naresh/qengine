"""
Script 23 — Chop Handling: Intelligent Behavior IN Choppy Markets
==================================================================
Avoidance isn't always possible — sometimes you're already in a cycle when
chop starts. This script tests strategies for handling chop mid-cycle:

  1. Early abort: if chop detected while in cycle, close early
  2. Reduced sizing: shrink position sizes in chop (less exposure)
  3. Wider hedges: increase hedge distance in chop (fewer triggers)
  4. Tighter TP: take profit sooner in chop (grab what you can)
  5. Combined: best of above

The goal: even if caught in chop, limit damage.

Outputs:
  - results/23_chop_handling.json
  - plots/23_handling_strategies.png
  - plots/23_mid_cycle_chop.png
  - plots/23_combined_vs_baseline.png
"""
from utils import *

print("=" * 60)
print("Script 23 — Chop Handling (Mid-Cycle Intelligence)")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# 1. SETUP
# ══════════════════════════════════════════════════════════════
print("\n[1/5] Loading data...")
candles = load_candles(timeframe='5m', start_date='2006-01-03', end_date='2025-12-30')
features = compute_chop_features(candles, windows=(50, 100))
cs = chop_score(features, window=100)

base_cfg = SimConfig(sizing_curve='sqrt', sizing_factor=2.0, max_levels=12,
                      hedge_dist_pips=10, tp_pips=20)
signals = random_signals(len(candles), avg_spacing=50, rng=np.random.default_rng(42))

baseline = run_cycles_on_signals(candles, signals, base_cfg, chop_scores=cs)
base_s = cycle_summary(baseline)
print(f"  Baseline: {base_s['n_cycles']} cycles, bust={base_s['bust_rate']:.2f}%, PF={base_s['profit_factor']:.2f}")

# ══════════════════════════════════════════════════════════════
# 2. CUSTOM SIMULATOR WITH MID-CYCLE CHOP AWARENESS
# ══════════════════════════════════════════════════════════════

def simulate_with_chop_handling(candles, entry_idx, direction, cfg, chop_scores,
                                  strategy='none', chop_thresh=0.6):
    """Extended simulator that can react to chop mid-cycle.

    Strategies:
      - none: standard behavior
      - early_abort: close if chop score rises above threshold while level >= 2
      - reduced_sizing: halve size multiplier when chop detected
      - wider_hedge: double hedge distance when chop detected
      - tighter_tp: halve TP when chop detected
      - combined: abort at level 3+ in chop, wider hedge + tighter TP at lower levels
    """
    n_bars = len(candles)
    if entry_idx >= n_bars:
        return None

    level = 0
    entry_price = candles[entry_idx, 2]
    level_entries = [entry_price]
    level_dirs = [direction]
    level_sizes = [calc_size(0, cfg)]
    bars = 0
    cs_at_entry = chop_scores[entry_idx] if entry_idx < len(chop_scores) else 0

    tp_dist = cfg.tp_pips * PIP
    h_dist = hedge_distance(0, cfg) * PIP

    if direction == 1:
        tp_price = entry_price + tp_dist
        hedge_price = entry_price - h_dist
    else:
        tp_price = entry_price - tp_dist
        hedge_price = entry_price + h_dist

    for bar_idx in range(entry_idx + 1, min(entry_idx + cfg.max_bars, n_bars)):
        bars += 1
        high = candles[bar_idx, 3]
        low = candles[bar_idx, 4]

        # Get current chop score
        current_chop = chop_scores[bar_idx] if bar_idx < len(chop_scores) else 0
        in_chop = not np.isnan(current_chop) and current_chop > chop_thresh

        # Strategy: early abort
        if strategy in ('early_abort', 'combined') and in_chop and level >= 2:
            abort_level = 2 if strategy == 'early_abort' else 3
            if level >= abort_level:
                close_price = candles[bar_idx, 2]
                total_pnl = sum(d * (close_price - e) * s / PIP
                                for e, d, s in zip(level_entries, level_dirs, level_sizes))
                return CycleResult(bust=True, level_reached=level, pnl=total_pnl,
                                   bars_held=bars, entry_idx=entry_idx, direction=direction,
                                   chop_score_at_entry=cs_at_entry)

        # Check TP
        last_dir = level_dirs[-1]
        tp_hit = (last_dir == 1 and high >= tp_price) or (last_dir == -1 and low <= tp_price)
        if tp_hit:
            total_pnl = sum(d * (tp_price - e) * s / PIP
                            for e, d, s in zip(level_entries, level_dirs, level_sizes))
            return CycleResult(bust=False, level_reached=level, pnl=total_pnl,
                               bars_held=bars, entry_idx=entry_idx, direction=direction,
                               chop_score_at_entry=cs_at_entry)

        # Check hedge
        hedge_hit = (last_dir == 1 and low <= hedge_price) or (last_dir == -1 and high >= hedge_price)
        if hedge_hit:
            if level + 1 >= cfg.max_levels:
                close_price = hedge_price
                total_pnl = sum(d * (close_price - e) * s / PIP
                                for e, d, s in zip(level_entries, level_dirs, level_sizes))
                return CycleResult(bust=True, level_reached=level + 1, pnl=total_pnl,
                                   bars_held=bars, entry_idx=entry_idx, direction=direction,
                                   chop_score_at_entry=cs_at_entry)

            level += 1
            new_dir = -last_dir
            new_entry = hedge_price

            # Apply chop-aware adjustments
            if in_chop:
                if strategy == 'reduced_sizing':
                    new_size = calc_size(level, cfg) * 0.5  # Half size in chop
                elif strategy == 'combined':
                    new_size = calc_size(level, cfg) * 0.7
                else:
                    new_size = calc_size(level, cfg)
            else:
                new_size = calc_size(level, cfg)

            level_entries.append(new_entry)
            level_dirs.append(new_dir)
            level_sizes.append(new_size)

            # Adjust TP and hedge for chop
            if in_chop and strategy in ('tighter_tp', 'combined'):
                tp_mult = 0.6  # Tighter TP in chop
            else:
                tp_mult = 1.0

            if in_chop and strategy in ('wider_hedge', 'combined'):
                hedge_mult = 1.5  # Wider hedge in chop
            else:
                hedge_mult = 1.0

            tp_d = cfg.tp_pips * PIP * tp_mult
            tp_price = new_entry + tp_d if new_dir == 1 else new_entry - tp_d

            h_d = hedge_distance(level, cfg) * PIP * hedge_mult
            hedge_price = new_entry - h_d if new_dir == 1 else new_entry + h_d

    # Data ran out
    if bars > 0:
        close_price = candles[min(entry_idx + bars, n_bars - 1), 2]
        total_pnl = sum(d * (close_price - e) * s / PIP
                        for e, d, s in zip(level_entries, level_dirs, level_sizes))
        return CycleResult(bust=True, level_reached=level, pnl=total_pnl,
                           bars_held=bars, entry_idx=entry_idx, direction=direction,
                           chop_score_at_entry=cs_at_entry)
    return None

# ══════════════════════════════════════════════════════════════
# 3. TEST EACH HANDLING STRATEGY
# ══════════════════════════════════════════════════════════════
print("\n[2/5] Testing handling strategies...")

strategies = ['none', 'early_abort', 'reduced_sizing', 'wider_hedge', 'tighter_tp', 'combined']
strategy_results = {}

for strat in strategies:
    results = []
    last_exit = -1
    for entry_idx, direction in sorted(signals, key=lambda x: x[0]):
        if entry_idx <= last_exit:
            continue
        r = simulate_with_chop_handling(candles, entry_idx, direction, base_cfg, cs,
                                         strategy=strat, chop_thresh=0.6)
        if r is not None:
            results.append(r)
            last_exit = entry_idx + r.bars_held

    s = cycle_summary(results)
    bust_red = (base_s['bust_rate'] - s['bust_rate']) / base_s['bust_rate'] * 100 if base_s['bust_rate'] > 0 else 0

    strategy_results[strat] = {
        **s,
        'bust_reduction': round(bust_red, 1),
    }
    print(f"  {strat:18s}: bust={s['bust_rate']:.2f}% (↓{bust_red:.0f}%), "
          f"PF={s['profit_factor']:.2f}, PnL={s['net_pnl']:.0f}")

# ══════════════════════════════════════════════════════════════
# 4. CHOP THRESHOLD SENSITIVITY FOR BEST STRATEGY
# ══════════════════════════════════════════════════════════════
print("\n[3/5] Chop threshold sensitivity for best strategy...")

best_strat = max(strategy_results.items(), key=lambda x: x[1].get('profit_factor', 0) if x[0] != 'none' else 0)
best_strat_name = best_strat[0]
print(f"  Best strategy: {best_strat_name}")

thresh_sensitivity = {}
for t in np.arange(0.3, 0.85, 0.05):
    results = []
    last_exit = -1
    for entry_idx, direction in sorted(signals, key=lambda x: x[0]):
        if entry_idx <= last_exit:
            continue
        r = simulate_with_chop_handling(candles, entry_idx, direction, base_cfg, cs,
                                         strategy=best_strat_name, chop_thresh=t)
        if r is not None:
            results.append(r)
            last_exit = entry_idx + r.bars_held

    s = cycle_summary(results)
    thresh_sensitivity[f'{t:.2f}'] = s

# ══════════════════════════════════════════════════════════════
# 5. PLOTS
# ══════════════════════════════════════════════════════════════
print("\n[4/5] Plotting...")

# Strategy comparison
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

strat_names = list(strategy_results.keys())
bust_rates = [strategy_results[s]['bust_rate'] for s in strat_names]
pfs = [strategy_results[s]['profit_factor'] for s in strat_names]
pnls = [strategy_results[s]['net_pnl'] for s in strat_names]

colors = ['gray'] + ['green' if b < bust_rates[0] else 'red' for b in bust_rates[1:]]
ax1.bar(strat_names, bust_rates, color=colors, edgecolor='black')
ax1.set_ylabel('Bust Rate (%)')
ax1.set_title('Mid-Cycle Chop Handling — Bust Rate')
ax1.tick_params(axis='x', rotation=30)
ax1.grid(True, alpha=0.3)

ax2.bar(strat_names, pfs, color=colors, edgecolor='black')
ax2.set_ylabel('Profit Factor')
ax2.set_title('Mid-Cycle Chop Handling — Profit Factor')
ax2.tick_params(axis='x', rotation=30)
ax2.grid(True, alpha=0.3)

plt.tight_layout()
savefig('23_handling_strategies.png')

# Combined: avoidance (script 22) + handling
# Show what happens if we BOTH skip choppy entries AND handle chop mid-cycle
print("\n[5/5] Combined avoidance + handling...")

# Filter signals with chop score threshold
filtered_signals = [(idx, d) for idx, d in signals
                    if idx < len(cs) and (np.isnan(cs[idx]) or cs[idx] <= 0.6)]

combined_results = []
last_exit = -1
for entry_idx, direction in sorted(filtered_signals, key=lambda x: x[0]):
    if entry_idx <= last_exit:
        continue
    r = simulate_with_chop_handling(candles, entry_idx, direction, base_cfg, cs,
                                     strategy='combined', chop_thresh=0.6)
    if r is not None:
        combined_results.append(r)
        last_exit = entry_idx + r.bars_held

combined_s = cycle_summary(combined_results)
bust_red = (base_s['bust_rate'] - combined_s['bust_rate']) / base_s['bust_rate'] * 100 if base_s['bust_rate'] > 0 else 0

print(f"\n  Avoidance + Handling combined:")
print(f"    Bust: {combined_s['bust_rate']:.2f}% (↓{bust_red:.0f}% from baseline)")
print(f"    PF: {combined_s['profit_factor']:.2f} (baseline: {base_s['profit_factor']:.2f})")
print(f"    PnL: {combined_s['net_pnl']:.0f} (baseline: {base_s['net_pnl']:.0f})")
print(f"    Cycles: {combined_s['n_cycles']} (baseline: {base_s['n_cycles']})")

fig, ax = plt.subplots(figsize=(10, 6))
eq_base = equity_curve(baseline)
eq_combined = equity_curve(combined_results)
ax.plot(eq_base, label=f"Baseline (PF={base_s['profit_factor']:.2f}, bust={base_s['bust_rate']:.1f}%)", alpha=0.7)
ax.plot(eq_combined, label=f"Avoid+Handle (PF={combined_s['profit_factor']:.2f}, bust={combined_s['bust_rate']:.1f}%)", alpha=0.7)
ax.set_xlabel('Cycle #')
ax.set_ylabel('Equity')
ax.set_title('Baseline vs Chop Avoidance + Handling')
ax.legend()
ax.grid(True, alpha=0.3)
savefig('23_combined_vs_baseline.png')

# Save
save_results({
    'baseline': base_s,
    'strategy_results': strategy_results,
    'best_strategy': best_strat_name,
    'threshold_sensitivity': thresh_sensitivity,
    'combined_avoid_handle': combined_s,
    'combined_bust_reduction': round(bust_red, 1),
}, '23_chop_handling')

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)
print(f"  Best mid-cycle strategy: {best_strat_name}")
print(f"  Combined avoidance + handling: bust ↓{bust_red:.0f}%")
print(f"  PF improvement: {base_s['profit_factor']:.2f} → {combined_s['profit_factor']:.2f}")
print("Done.")
