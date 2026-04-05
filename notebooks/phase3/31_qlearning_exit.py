"""
Script 31 — Q-Learning Mid-Cycle Exit with Vol/Trend Features
================================================================
Integrates Phase 2 Q-learning abort (proven -32% bust rate) with
Phase 3 vol/trend features. Key improvement: replaces the "danger score"
with a vol/trend confidence score that's validated on recent data.

State: (level, duration_bin, vol_regime, trend_strength)
Action: continue or abort
Reward: realized PnL at cycle termination

This is the only mid-cycle approach that showed real bust reduction.
"""
from utils import *
import qengine.indicators as ta
import warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("Script 31 — Q-Learning Mid-Cycle Exit")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════
N_LEVELS = 13           # 0..12
N_DUR_BINS = 5          # [0-5, 5-10, 10-20, 20-50, 50+]
N_VOL_BINS = 3          # low, medium, high
N_TREND_BINS = 3        # weak, medium, strong
N_STATES = N_LEVELS * N_DUR_BINS * N_VOL_BINS * N_TREND_BINS  # 585
N_ACTIONS = 2           # continue=0, abort=1

# Q-learning params
ALPHA = 0.1
GAMMA = 0.95
EPSILON_START = 0.15
EPSILON_MIN = 0.02
EPSILON_DECAY = 0.998
N_EPISODES = 5

DUR_EDGES = [0, 5, 10, 20, 50]

def dur_bin(bars):
    for i, e in enumerate(DUR_EDGES):
        if bars < e:
            return max(0, i - 1)
    return N_DUR_BINS - 1

def vol_bin(natr_val, natr_p33, natr_p66):
    if np.isnan(natr_val): return 1
    if natr_val < natr_p33: return 0
    if natr_val < natr_p66: return 1
    return 2

def trend_bin(adx_val):
    if np.isnan(adx_val): return 1
    if adx_val < 20: return 0
    if adx_val < 35: return 1
    return 2

def encode(level, d_bin, v_bin, t_bin):
    lv = min(level, N_LEVELS - 1)
    return lv * (N_DUR_BINS * N_VOL_BINS * N_TREND_BINS) + \
           d_bin * (N_VOL_BINS * N_TREND_BINS) + \
           v_bin * N_TREND_BINS + t_bin


# ══════════════════════════════════════════════════════════════
# 1. LOAD DATA
# ══════════════════════════════════════════════════════════════
print("\n[1/5] Loading data...", flush=True)
candles = load_candles(timeframe='5m', start_date='2020-01-03', end_date='2025-12-30')
n_bars = len(candles)
print(f"  {n_bars:,} candles", flush=True)

# Precompute indicators
print("  Computing NATR, ADX...", flush=True)
natr = ta.natr(candles, period=14, sequential=True)
adx = ta.adx(candles, period=14, sequential=True)

# NATR percentiles for vol binning
valid_natr = natr[~np.isnan(natr)]
natr_p33 = np.percentile(valid_natr, 33)
natr_p66 = np.percentile(valid_natr, 66)
print(f"  NATR percentiles: p33={natr_p33:.4f}, p66={natr_p66:.4f}", flush=True)

cfg = SimConfig(sizing_curve='fibonacci', sizing_factor=2.0, max_levels=10,
                hedge_dist_pips=15, tp_pips=15)
signals = find_ema_crossover_signals(candles, 8, 21)
print(f"  {len(signals)} EMA signals", flush=True)


# ══════════════════════════════════════════════════════════════
# 2. SIMULATE WITH Q-LEARNING
# ══════════════════════════════════════════════════════════════
print("\n[2/5] Training Q-learning agent...", flush=True)

def simulate_with_q(candles, signals, cfg, q_table, natr, adx,
                    natr_p33, natr_p66, epsilon=0.0, learn=False, rng=None):
    """Run cycles with Q-learning abort decisions at each bar."""
    if rng is None:
        rng = np.random.default_rng(42)

    results = []
    last_exit = -1
    n = len(candles)

    for entry_idx, direction in sorted(signals, key=lambda x: x[0]):
        if entry_idx <= last_exit:
            continue

        level = 0
        entry_price = candles[entry_idx, 2]
        level_entries = [entry_price]
        level_dirs = [direction]
        level_sizes = [calc_size(0, cfg)]

        tp_dist = cfg.tp_pips * PIP
        h_dist = hedge_distance(0, cfg) * PIP
        if direction == 1:
            tp_price = entry_price + tp_dist
            hedge_price = entry_price - h_dist
        else:
            tp_price = entry_price - tp_dist
            hedge_price = entry_price + h_dist

        bars = 0
        aborted = False
        states_visited = []

        for bar_idx in range(entry_idx + 1, min(entry_idx + cfg.max_bars, n)):
            bars += 1
            high = candles[bar_idx, 3]
            low = candles[bar_idx, 4]

            # Q-learning decision (every bar while in cycle)
            if level > 0 and bars > 2:  # Only consider abort after level 1+
                d = dur_bin(bars)
                v = vol_bin(natr[bar_idx] if bar_idx < len(natr) else np.nan, natr_p33, natr_p66)
                t = trend_bin(adx[bar_idx] if bar_idx < len(adx) else np.nan)
                state = encode(level, d, v, t)
                states_visited.append(state)

                # Epsilon-greedy
                if rng.random() < epsilon:
                    action = rng.integers(0, 2)
                else:
                    action = np.argmax(q_table[state])

                if action == 1:  # ABORT
                    close_price = candles[bar_idx, 2]
                    total_pnl = sum(level_dirs[i] * (close_price - level_entries[i]) * level_sizes[i] / PIP
                                    for i in range(len(level_entries)))
                    result = CycleResult(bust=True, level_reached=level, pnl=total_pnl,
                                         bars_held=bars, entry_idx=entry_idx, direction=direction)
                    results.append(result)
                    last_exit = bar_idx
                    aborted = True

                    # Q-update for abort
                    if learn:
                        reward = total_pnl
                        for s in states_visited:
                            q_table[s, 1] += ALPHA * (reward - q_table[s, 1])
                    break

            # Check TP
            last_dir = level_dirs[-1]
            tp_hit = (last_dir == 1 and high >= tp_price) or (last_dir == -1 and low <= tp_price)
            if tp_hit:
                close_price = tp_price
                total_pnl = sum(level_dirs[i] * (close_price - level_entries[i]) * level_sizes[i] / PIP
                                for i in range(len(level_entries)))
                result = CycleResult(bust=False, level_reached=level, pnl=total_pnl,
                                     bars_held=bars, entry_idx=entry_idx, direction=direction)
                results.append(result)
                last_exit = bar_idx

                if learn:
                    reward = total_pnl
                    for s in states_visited:
                        q_table[s, 0] += ALPHA * (reward - q_table[s, 0])
                break

            # Check hedge
            hedge_hit = (last_dir == 1 and low <= hedge_price) or (last_dir == -1 and high >= hedge_price)
            if hedge_hit:
                if level + 1 >= cfg.max_levels:
                    close_price = hedge_price
                    total_pnl = sum(level_dirs[i] * (close_price - level_entries[i]) * level_sizes[i] / PIP
                                    for i in range(len(level_entries)))
                    result = CycleResult(bust=True, level_reached=level+1, pnl=total_pnl,
                                         bars_held=bars, entry_idx=entry_idx, direction=direction)
                    results.append(result)
                    last_exit = bar_idx

                    if learn:
                        for s in states_visited:
                            q_table[s, 0] += ALPHA * (total_pnl - q_table[s, 0])
                    break

                level += 1
                new_dir = -last_dir
                level_entries.append(hedge_price)
                level_dirs.append(new_dir)
                level_sizes.append(calc_size(level, cfg))
                tp_price = hedge_price + tp_dist if new_dir == 1 else hedge_price - tp_dist
                h_dist = hedge_distance(level, cfg) * PIP
                hedge_price = hedge_price - h_dist if new_dir == 1 else hedge_price + h_dist

        if not aborted and bars > 0 and bar_idx == min(entry_idx + cfg.max_bars, n) - 1:
            close_price = candles[min(entry_idx + bars, n - 1), 2]
            total_pnl = sum(level_dirs[i] * (close_price - level_entries[i]) * level_sizes[i] / PIP
                            for i in range(len(level_entries)))
            result = CycleResult(bust=True, level_reached=level, pnl=total_pnl,
                                 bars_held=bars, entry_idx=entry_idx, direction=direction)
            results.append(result)
            last_exit = entry_idx + bars

    return results


# Train over multiple episodes
rng = np.random.default_rng(42)
q_table = np.zeros((N_STATES, N_ACTIONS))
epsilon = EPSILON_START

# Baseline (no Q-learning)
baseline_results = run_cycles_on_signals(candles, signals, cfg)
baseline = cycle_summary(baseline_results)
print(f"  Baseline: {baseline['n_cycles']} cycles, bust={baseline['bust_rate']:.2f}%, PF={baseline['profit_factor']:.2f}")

for ep in range(N_EPISODES):
    results = simulate_with_q(candles, signals, cfg, q_table, natr, adx,
                               natr_p33, natr_p66, epsilon=epsilon, learn=True, rng=rng)
    s = cycle_summary(results)
    epsilon = max(EPSILON_MIN, epsilon * EPSILON_DECAY)
    print(f"  Episode {ep+1}: {s['n_cycles']} cycles, bust={s['bust_rate']:.2f}%, "
          f"PF={s['profit_factor']:.2f}, aborts={sum(1 for c in results if c.bust and c.level_reached < cfg.max_levels)}", flush=True)

# ══════════════════════════════════════════════════════════════
# 3. EVALUATE TRAINED POLICY
# ══════════════════════════════════════════════════════════════
print("\n[3/5] Evaluating trained policy (epsilon=0)...", flush=True)

q_results = simulate_with_q(candles, signals, cfg, q_table, natr, adx,
                              natr_p33, natr_p66, epsilon=0.0, learn=False, rng=rng)
q_summary = cycle_summary(q_results)
n_aborts = sum(1 for c in q_results if c.bust and c.level_reached < cfg.max_levels)
abort_rate = n_aborts / len(q_results) * 100 if q_results else 0

print(f"  Q-policy: {q_summary['n_cycles']} cycles, bust={q_summary['bust_rate']:.2f}%, PF={q_summary['profit_factor']:.2f}")
print(f"  Aborts: {n_aborts} ({abort_rate:.1f}% of cycles)")
bust_red = ((baseline['bust_rate'] - q_summary['bust_rate']) / baseline['bust_rate'] * 100
            if baseline['bust_rate'] > 0 else 0)
print(f"  Bust reduction: {bust_red:+.0f}%")

# ══════════════════════════════════════════════════════════════
# 4. WALK-FORWARD: TRAIN 2020-2023, TEST 2024-2025
# ══════════════════════════════════════════════════════════════
print("\n[4/5] Walk-forward validation...", flush=True)

# Split data
split_idx = int(n_bars * 0.7)  # ~2020-2023
train_c = candles[:split_idx]
test_c = candles[split_idx:]
train_sigs = [(idx, d) for idx, d in signals if idx < split_idx]
test_sigs = [(idx - split_idx, d) for idx, d in signals if idx >= split_idx and idx - split_idx < len(test_c)]

natr_train = natr[:split_idx]
natr_test = natr[split_idx:]
adx_train = adx[:split_idx]
adx_test = adx[split_idx:]

# Train on train data
q_wf = np.zeros((N_STATES, N_ACTIONS))
epsilon = EPSILON_START
for ep in range(N_EPISODES):
    simulate_with_q(train_c, train_sigs, cfg, q_wf, natr_train, adx_train,
                    natr_p33, natr_p66, epsilon=epsilon, learn=True, rng=rng)
    epsilon = max(EPSILON_MIN, epsilon * EPSILON_DECAY)

# Evaluate on test
test_base_results = run_cycles_on_signals(test_c, test_sigs, cfg)
test_base = cycle_summary(test_base_results)

test_q_results = simulate_with_q(test_c, test_sigs, cfg, q_wf, natr_test, adx_test,
                                  natr_p33, natr_p66, epsilon=0.0, learn=False, rng=rng)
test_q = cycle_summary(test_q_results)

print(f"  Test baseline: {test_base['n_cycles']} cycles, bust={test_base['bust_rate']:.2f}%, PF={test_base['profit_factor']:.2f}")
print(f"  Test Q-policy: {test_q['n_cycles']} cycles, bust={test_q['bust_rate']:.2f}%, PF={test_q['profit_factor']:.2f}")

# ══════════════════════════════════════════════════════════════
# 5. Q-TABLE ANALYSIS AND PLOTS
# ══════════════════════════════════════════════════════════════
print("\n[5/5] Analyzing Q-table and plotting...", flush=True)

# Which states trigger abort?
abort_states = []
for s in range(N_STATES):
    if q_table[s, 1] > q_table[s, 0] and (q_table[s, 0] != 0 or q_table[s, 1] != 0):
        level = s // (N_DUR_BINS * N_VOL_BINS * N_TREND_BINS)
        rem = s % (N_DUR_BINS * N_VOL_BINS * N_TREND_BINS)
        d = rem // (N_VOL_BINS * N_TREND_BINS)
        rem2 = rem % (N_VOL_BINS * N_TREND_BINS)
        v = rem2 // N_TREND_BINS
        t = rem2 % N_TREND_BINS
        abort_states.append({'level': level, 'duration': d, 'vol': v, 'trend': t,
                             'q_continue': round(q_table[s, 0], 2),
                             'q_abort': round(q_table[s, 1], 2)})

print(f"  States where Q prefers abort: {len(abort_states)} of {N_STATES}")
if abort_states:
    print(f"  Sample abort states:")
    vol_names = ['low_vol', 'med_vol', 'high_vol']
    trend_names = ['weak', 'medium', 'strong']
    dur_names = ['0-5', '5-10', '10-20', '20-50', '50+']
    for s in sorted(abort_states, key=lambda x: x['q_abort'] - x['q_continue'], reverse=True)[:10]:
        print(f"    L{s['level']} dur={dur_names[s['duration']]} vol={vol_names[s['vol']]} "
              f"trend={trend_names[s['trend']]} → abort={s['q_abort']:.1f} vs cont={s['q_continue']:.1f}")

# Plot
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# Equity curves
ax = axes[0]
eq_base = equity_curve(baseline_results, 10000)
eq_q = equity_curve(q_results, 10000)
ax.plot(eq_base, label=f'Baseline (PF={baseline["profit_factor"]:.2f})', alpha=0.7)
ax.plot(eq_q, label=f'Q-policy (PF={q_summary["profit_factor"]:.2f})', alpha=0.7)
ax.set_xlabel('Cycle')
ax.set_ylabel('Equity ($)')
ax.set_title('Equity: Baseline vs Q-Learning Exit')
ax.legend()
ax.grid(True, alpha=0.3)

# Abort heatmap: level × duration
ax = axes[1]
abort_matrix = np.zeros((N_LEVELS, N_DUR_BINS))
for s in range(N_STATES):
    level = s // (N_DUR_BINS * N_VOL_BINS * N_TREND_BINS)
    rem = s % (N_DUR_BINS * N_VOL_BINS * N_TREND_BINS)
    d = rem // (N_VOL_BINS * N_TREND_BINS)
    q_diff = q_table[s, 1] - q_table[s, 0]
    abort_matrix[level, d] += q_diff

im = ax.imshow(abort_matrix[:8, :], cmap='RdYlGn_r', aspect='auto')
ax.set_xticks(range(N_DUR_BINS))
ax.set_xticklabels(['0-5', '5-10', '10-20', '20-50', '50+'], fontsize=8)
ax.set_yticks(range(8))
ax.set_yticklabels([f'L{i}' for i in range(8)])
ax.set_xlabel('Duration (bars)')
ax.set_ylabel('Level')
ax.set_title('Abort Preference (red=abort, green=continue)')
plt.colorbar(im, ax=ax)

# Walk-forward comparison
ax = axes[2]
strats = ['Baseline', 'Q-Policy']
train_pfs = [baseline['profit_factor'], q_summary['profit_factor']]
test_pfs = [test_base['profit_factor'], test_q['profit_factor']]
x = np.arange(len(strats))
ax.bar(x - 0.15, train_pfs, 0.3, label='Full (2020-25)', color='steelblue')
ax.bar(x + 0.15, test_pfs, 0.3, label='Test (2024-25)', color='orange')
ax.set_xticks(x)
ax.set_xticklabels(strats)
ax.set_ylabel('Profit Factor')
ax.set_title('Walk-Forward: Train vs Test')
ax.legend()
ax.grid(True, alpha=0.3)

plt.tight_layout()
savefig('31_qlearning_exit.png')

save_results({
    'baseline': baseline,
    'q_policy': q_summary,
    'bust_reduction_pct': round(bust_red, 1),
    'n_aborts': n_aborts,
    'abort_rate_pct': round(abort_rate, 1),
    'walk_forward': {
        'test_baseline': test_base,
        'test_q_policy': test_q,
    },
    'n_abort_states': len(abort_states),
}, '31_qlearning_exit')

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)
print(f"  Baseline: bust={baseline['bust_rate']:.2f}%, PF={baseline['profit_factor']:.2f}")
print(f"  Q-policy: bust={q_summary['bust_rate']:.2f}%, PF={q_summary['profit_factor']:.2f}")
print(f"  Bust reduction: {bust_red:+.0f}%")
print(f"  Abort rate: {abort_rate:.1f}%")
print(f"  Walk-forward test PF: {test_base['profit_factor']:.2f} → {test_q['profit_factor']:.2f}")
print("Done.", flush=True)
