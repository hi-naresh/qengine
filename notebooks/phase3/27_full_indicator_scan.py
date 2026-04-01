"""
Script 27 — Full Indicator Scan (incremental/resumable)
========================================================
Saves results after each batch of indicators so we can resume if killed.
"""
from utils import *
import qengine.indicators as ta
import inspect, gc, sys, os, json
import warnings
warnings.filterwarnings('ignore')

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results', '27_incremental.json')

print("=" * 60)
print("Script 27 — Full Indicator Scan")
print("=" * 60, flush=True)

# Load previous results if resuming
prev = {}
if os.path.exists(RESULTS_FILE):
    with open(RESULTS_FILE) as f:
        prev = json.load(f)
    print(f"  Resuming: {len(prev.get('auc_results', {}))} AUCs already computed", flush=True)

# ══════════════════════════════════════════════════════════════
print("\n[1/4] Loading data...", flush=True)
CANDLE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results', '27_candles.npy')
if os.path.exists(CANDLE_CACHE):
    candles = np.load(CANDLE_CACHE)
    print("  Loaded cached candles", flush=True)
else:
    candles = load_candles(timeframe='5m', start_date='2023-06-01', end_date='2025-12-30')
    os.makedirs(os.path.dirname(CANDLE_CACHE), exist_ok=True)
    np.save(CANDLE_CACHE, candles)
n_bars = len(candles)
print(f"  {n_bars:,} candles", flush=True)

cfg = SimConfig(sizing_curve='sqrt', sizing_factor=2.0, max_levels=12,
                hedge_dist_pips=10, tp_pips=20)

all_signals = find_ema_crossover_signals(candles, 8, 21)

# Cache baseline results to avoid recomputation on resume
import pickle
BASELINE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results', '27_baseline.pkl')
if os.path.exists(BASELINE_CACHE):
    with open(BASELINE_CACHE, 'rb') as f:
        baseline_results = pickle.load(f)
    print("  Loaded cached baseline", flush=True)
else:
    baseline_results = run_cycles_on_signals(candles, all_signals, cfg)
    os.makedirs(os.path.dirname(BASELINE_CACHE), exist_ok=True)
    with open(BASELINE_CACHE, 'wb') as f:
        pickle.dump(baseline_results, f)

baseline = cycle_summary(baseline_results)
print(f"  Baseline: {baseline['n_cycles']} cycles, bust={baseline['bust_rate']:.2f}%, PF={baseline['profit_factor']:.2f}", flush=True)

# ══════════════════════════════════════════════════════════════
print("\n[2/4] Computing AUC for all indicators...", flush=True)

all_names = sorted([n for n in dir(ta) if not n.startswith('_') and callable(getattr(ta, n))])

COMPLEX_FIELDS = {
    'bollinger_bands': 'middleband', 'macd': 'macd', 'stoch': 'slowk', 'stochf': 'fastk',
    'aroon': 'aroon', 'di': 'plus', 'dm': 'plus', 'donchian': 'middleband',
    'fisher': 'fisher', 'keltner': 'middleband', 'supertrend': 'trend',
    'ichimoku_cloud_seq': 'conversion_line', 'squeeze_momentum': 'squeeze',
    'srsi': 'k', 'kdj': 'k', 'kst': 'line', 'ao': 'osc', 'volume': 'volume',
    'vi': 'plus', 'vwmacd': 'macd', 'wt': 'wt1', 'bandpass': 'bp',
    'emd': 'mean', 'mama': 'mama', 'eri': 'bull', 'correlation_cycle': 'real',
    'rsmk': 'rsmk', 'ttm_trend': 'trend', 'vpci': 'vpci', 'voss': 'voss',
    'hull_suit': 'signal', 'pma': 'predict', 'mab': 'fast', 'itrend': 'signal',
    'minmax': 'min', 'pivot': 'pp', 'alligator': 'jaw', 'gatorosc': 'upper',
    'acosc': 'ac', 'cksp': 'long_stop', 'damiani_volatmeter': 'vol',
}
SKIP = {'heikin_ashi_candles', 'damiani_volatmeter'}  # damiani hangs on large datasets

from sklearn.metrics import roc_auc_score

auc_results = prev.get('auc_results', {})
entry_values = {}  # rebuilt each run for gate testing
failed = prev.get('failed', [])
already_done = set(auc_results.keys()) | set(k for k, _ in failed)
computed = len(auc_results)

for ind_i, name in enumerate(all_names):
    if name in SKIP:
        continue
    fn = getattr(ta, name)
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
    except:
        continue
    if 'sequential' not in params:
        continue

    has_period = 'period' in params
    key = f"{name}_14" if has_period else name

    if key in already_done:
        continue

    try:
        kwargs = {'candles': candles, 'sequential': True}
        if has_period:
            kwargs['period'] = 14
        result = fn(**kwargs)

        if isinstance(result, np.ndarray):
            arr = result
        else:
            field = COMPLEX_FIELDS.get(name)
            arr = None
            if field:
                arr = getattr(result, field, None)
            if arr is None:
                for attr in dir(result):
                    if not attr.startswith('_'):
                        val = getattr(result, attr)
                        if isinstance(val, np.ndarray) and len(val) == n_bars:
                            arr = val
                            break
            if arr is None:
                del result
                failed.append((key, 'no array'))
                continue

        if len(arr) != n_bars:
            del result, arr
            failed.append((key, f'len={len(arr)}'))
            continue

        arr = arr.astype(np.float64)
        valid_mask = ~np.isnan(arr)
        if valid_mask.sum() < 1000 or np.std(arr[valid_mask]) == 0:
            del result, arr
            failed.append((key, 'no variation'))
            continue

        computed += 1
        bust_vals = [float(arr[c.entry_idx]) for c in baseline_results
                     if c.bust and c.entry_idx < n_bars and valid_mask[c.entry_idx]]
        win_vals = [float(arr[c.entry_idx]) for c in baseline_results
                    if c.is_win and c.entry_idx < n_bars and valid_mask[c.entry_idx]]

        if len(bust_vals) >= 3 and len(win_vals) >= 30:
            labels = [1]*len(bust_vals) + [0]*len(win_vals)
            values = bust_vals + win_vals
            auc = roc_auc_score(labels, values)
            best_auc = max(auc, 1-auc)
            direction = 'higher_busts' if auc >= 0.5 else 'lower_busts'
            cohens_d = abs(np.mean(bust_vals) - np.mean(win_vals)) / max(
                np.sqrt((np.var(bust_vals) + np.var(win_vals)) / 2), 1e-10)

            all_entry_vals = bust_vals + win_vals
            auc_results[key] = {
                'auc': round(best_auc, 4), 'direction': direction,
                'cohens_d': round(cohens_d, 4),
                'p30': round(float(np.percentile(all_entry_vals, 30)), 6),
                'p50': round(float(np.percentile(all_entry_vals, 50)), 6),
                'p70': round(float(np.percentile(all_entry_vals, 70)), 6),
            }
            entry_values[key] = {str(c.entry_idx): float(arr[c.entry_idx])
                                 for c in baseline_results
                                 if c.entry_idx < n_bars and valid_mask[c.entry_idx]}

        del result, arr
        gc.collect()

    except Exception as e:
        failed.append((key, str(e)[:60]))
        gc.collect()
        continue

    # Save incrementally every 10 indicators
    if True:  # Save after EVERY indicator
        os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
        with open(RESULTS_FILE, 'w') as f:
            json.dump({'auc_results': auc_results, 'failed': failed, 'baseline': baseline}, f, indent=2, default=str)
        print(f"    [{computed} computed, {len(auc_results)} AUCs] saved checkpoint", flush=True)

# Final save
os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
with open(RESULTS_FILE, 'w') as f:
    json.dump({'auc_results': auc_results, 'failed': failed, 'baseline': baseline}, f, indent=2, default=str)
print(f"  Phase 1 done: {computed} computed, {len(auc_results)} AUCs", flush=True)

# ══════════════════════════════════════════════════════════════
print("\n[3/4] Testing top 30 as entry gates...", flush=True)

ranked_auc = sorted(auc_results.items(), key=lambda x: x[1]['auc'], reverse=True)
gate_results = {}

for rank, (key, auc_info) in enumerate(ranked_auc[:30]):
    if key not in entry_values:
        # Need to recompute this indicator to get entry values
        name = key.replace('_14', '') if key.endswith('_14') else key
        fn = getattr(ta, name, None)
        if fn is None:
            continue
        try:
            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())
            kwargs = {'candles': candles, 'sequential': True}
            if 'period' in params:
                kwargs['period'] = 14
            result = fn(**kwargs)
            if isinstance(result, np.ndarray):
                arr = result
            else:
                field = COMPLEX_FIELDS.get(name)
                arr = getattr(result, field, None) if field else None
                if arr is None:
                    for attr in dir(result):
                        if not attr.startswith('_'):
                            val = getattr(result, attr)
                            if isinstance(val, np.ndarray) and len(val) == n_bars:
                                arr = val
                                break
            if arr is None or len(arr) != n_bars:
                continue
            arr = arr.astype(np.float64)
            valid_mask = ~np.isnan(arr)
            entry_values[key] = {str(c.entry_idx): float(arr[c.entry_idx])
                                 for c in baseline_results
                                 if c.entry_idx < n_bars and valid_mask[c.entry_idx]}
            del result, arr
            gc.collect()
        except:
            continue

    ev = entry_values.get(key, {})
    if not ev:
        continue

    direction = auc_info['direction']
    best_pf = 0
    best_gate = None

    for pct_key in ['p30', 'p50', 'p70']:
        thresh = auc_info[pct_key]
        if direction == 'higher_busts':
            filtered = [(idx, d) for idx, d in all_signals
                        if str(idx) not in ev or ev[str(idx)] <= thresh]
        else:
            filtered = [(idx, d) for idx, d in all_signals
                        if str(idx) not in ev or ev[str(idx)] >= thresh]

        if len(filtered) < 30:
            continue
        results = run_cycles_on_signals(candles, filtered, cfg)
        s = cycle_summary(results)
        if s['profit_factor'] > best_pf:
            best_pf = s['profit_factor']
            pct_kept = len(filtered) / len(all_signals) * 100
            bust_red = ((baseline['bust_rate'] - s['bust_rate']) / baseline['bust_rate'] * 100
                        if baseline['bust_rate'] > 0 else 0)
            best_gate = {
                'threshold': round(thresh, 6), 'bust_rate': round(s['bust_rate'], 3),
                'bust_reduction_pct': round(bust_red, 1), 'profit_factor': round(best_pf, 3),
                'net_pnl': round(s['net_pnl'], 1), 'pct_kept': round(pct_kept, 1),
                'n_cycles': s['n_cycles'], 'auc': auc_info['auc'],
            }
    if best_gate:
        gate_results[key] = best_gate

ranked_gates = sorted(gate_results.items(), key=lambda x: x[1]['profit_factor'], reverse=True)

print(f"\n  TOP 20 BUST PREDICTORS (AUC):")
print(f"  {'Indicator':<30s} {'AUC':>6s} {'d':>6s}")
for name, r in ranked_auc[:20]:
    print(f"  {name:<30s} {r['auc']:>6.4f} {r['cohens_d']:>6.3f}")

print(f"\n  TOP 20 ENTRY GATES (by PF):")
print(f"  {'Indicator':<30s} {'Bust%':>6s} {'BustRed':>8s} {'PF':>6s} {'PnL':>7s} {'Kept%':>6s}")
for name, r in ranked_gates[:20]:
    print(f"  {name:<30s} {r['bust_rate']:>5.2f}% {r['bust_reduction_pct']:>+7.0f}% "
          f"{r['profit_factor']:>6.3f} {r['net_pnl']:>7.0f} {r['pct_kept']:>5.1f}%")

# ══════════════════════════════════════════════════════════════
print("\n[4/4] Plotting...", flush=True)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))
top_n = min(25, len(ranked_gates))
names_list = [r[0] for r in ranked_gates[:top_n]]
pfs = [r[1]['profit_factor'] for r in ranked_gates[:top_n]]
bust_reds = [r[1]['bust_reduction_pct'] for r in ranked_gates[:top_n]]
y = np.arange(top_n)
colors = ['green' if pf > baseline['profit_factor'] * 1.2 else 'orange'
          if pf > baseline['profit_factor'] else 'gray' for pf in pfs]
ax1.barh(y, pfs, color=colors, edgecolor='black', linewidth=0.5)
ax1.axvline(x=baseline['profit_factor'], color='red', linestyle='--',
            label=f"Baseline PF={baseline['profit_factor']:.2f}")
ax1.set_yticks(y); ax1.set_yticklabels(names_list, fontsize=7)
ax1.set_xlabel('Profit Factor'); ax1.set_title(f'Top {top_n} Indicators as Entry Gates')
ax1.legend(); ax1.invert_yaxis()

ax2.barh(y, bust_reds, color=['green' if b > 0 else 'red' for b in bust_reds],
         edgecolor='black', linewidth=0.5)
ax2.set_yticks(y); ax2.set_yticklabels(names_list, fontsize=7)
ax2.set_xlabel('Bust Reduction (%)'); ax2.set_title('Bust Reduction per Gate')
ax2.invert_yaxis()
plt.tight_layout(); savefig('27_full_indicator_scan.png')

fig, ax = plt.subplots(figsize=(10, 5))
all_aucs = [r[1]['auc'] for r in ranked_auc]
ax.hist(all_aucs, bins=25, color='steelblue', edgecolor='black')
ax.axvline(x=0.55, color='red', linestyle='--', label='AUC=0.55')
ax.set_xlabel('AUC'); ax.set_ylabel('Count')
ax.set_title(f'AUC Distribution ({len(ranked_auc)} indicators)'); ax.legend()
savefig('27_auc_distribution.png')

save_results({
    'baseline': baseline, 'n_computed': computed,
    'top_20_auc': {k: v for k, v in ranked_auc[:20]},
    'top_20_gates': {k: v for k, v in ranked_gates[:20]},
    'all_gates': gate_results,
}, '27_full_indicator_scan')

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)
if ranked_gates:
    best = ranked_gates[0]
    print(f"  Best gate: {best[0]} -> PF={best[1]['profit_factor']:.3f}, bust red {best[1]['bust_reduction_pct']:.0f}%")
    strong = [r for r in ranked_gates if r[1]['profit_factor'] > baseline['profit_factor'] * 1.2]
    print(f"  Indicators beating baseline by >20%: {len(strong)} of {len(gate_results)}")
print("Done.", flush=True)
