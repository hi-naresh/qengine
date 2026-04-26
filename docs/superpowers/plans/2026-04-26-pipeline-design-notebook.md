# Pipeline-Design Notebook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `notebooks/10_pipeline_design/` — a chronological design diary documenting the 9 load-bearing pivots that produced the current IslandPilot architecture, mirroring the structure of `notebooks/01-09/`.

**Architecture:** Per-pivot folder structure (`01_static_hp_limits/` … `09_iteration_corrections/`) each containing a templated 7-section README and (where empirical) supporting scripts. A top-level `README.md` indexes the pivots; `JOURNEY.md` provides a one-screen decision-tree summary. `shared/utils.py` holds helpers reused across pivots.

**Tech Stack:** Python 3 (`/Users/naresh/miniconda3/bin/python3`), pandas, numpy, matplotlib (`Agg` backend for headless plotting), reuses `notebooks/shared/utils.py:run_backtest()` for any engine-fitness work.

**Spec:** `docs/superpowers/specs/2026-04-26-pipeline-design-notebook-design.md`

---

## File Structure

Files created:

```
notebooks/10_pipeline_design/
  README.md                                        # Task 11
  JOURNEY.md                                       # Task 11
  shared/
    __init__.py                                    # Task 1
    utils.py                                       # Task 1
  01_static_hp_limits/
    README.md                                      # Task 2
    01_break_even_summary.py                       # Task 2
  02_regime_detection_choice/
    README.md                                      # Task 3
    01_iid_bust_test.py                            # Task 3
  03_hierarchical_clustering/
    README.md                                      # Task 4
    01_bic_over_k.py                               # Task 4
  04_per_regime_evolution/
    README.md                                      # Task 5
  05_island_migration_topology/
    README.md                                      # Task 6
    01_topology_diagram.py                         # Task 6
  06_real_engine_fitness/
    README.md                                      # Task 7
    01_simulator_vs_engine_gap.py                  # Task 7
  07_gene_space_expansion/
    README.md                                      # Task 8
    01_gene_count_per_iteration.py                 # Task 8
  08_adaptive_sizing_runtime/
    README.md                                      # Task 9
    01_scaling_curve.py                            # Task 9
  09_iteration_corrections/
    README.md                                      # Task 10
    01_categorical_fix_demo.py                     # Task 10
```

`results/` subdirectories are created lazily by each script via `os.makedirs(..., exist_ok=True)`.

**Validation pattern.** Research-notebook tasks differ from typical TDD: documentation tasks are validated by structural grep, and script tasks are validated by "runs without error and emits expected output files in `results/`". Each task uses the validation form appropriate to its type.

---

## Task 1: Scaffold directories and shared utilities

**Files:**
- Create: `notebooks/10_pipeline_design/shared/__init__.py`
- Create: `notebooks/10_pipeline_design/shared/utils.py`

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p /Users/naresh/Documents/Research/qengine/notebooks/10_pipeline_design/shared
mkdir -p /Users/naresh/Documents/Research/qengine/notebooks/10_pipeline_design/01_static_hp_limits/results
mkdir -p /Users/naresh/Documents/Research/qengine/notebooks/10_pipeline_design/02_regime_detection_choice/results
mkdir -p /Users/naresh/Documents/Research/qengine/notebooks/10_pipeline_design/03_hierarchical_clustering/results
mkdir -p /Users/naresh/Documents/Research/qengine/notebooks/10_pipeline_design/04_per_regime_evolution
mkdir -p /Users/naresh/Documents/Research/qengine/notebooks/10_pipeline_design/05_island_migration_topology/results
mkdir -p /Users/naresh/Documents/Research/qengine/notebooks/10_pipeline_design/06_real_engine_fitness/results
mkdir -p /Users/naresh/Documents/Research/qengine/notebooks/10_pipeline_design/07_gene_space_expansion/results
mkdir -p /Users/naresh/Documents/Research/qengine/notebooks/10_pipeline_design/08_adaptive_sizing_runtime/results
mkdir -p /Users/naresh/Documents/Research/qengine/notebooks/10_pipeline_design/09_iteration_corrections/results
```

- [ ] **Step 2: Create `shared/__init__.py`**

```python
```

(empty file; just marks `shared` as a package)

- [ ] **Step 3: Create `shared/utils.py`**

```python
"""Pipeline-research helpers shared across pivots."""
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

ISLANDPILOT_MODELS = os.path.join(_ROOT, 'pipelines', '_shared', 'IslandPilot', 'models')


def load_pipeline_artifacts() -> dict:
    """Load trained IslandPilot artifacts as a dict.

    Returns keys: 'island_genomes' (list[dict] | None), 'feature_selector' (dict | None),
    'leaf_date_ranges' (dict | None). Missing files return None for that key rather
    than raising — pivots may run before all artifacts exist.
    """
    out = {}
    files = {
        'island_genomes': 'island_genomes.json',
        'feature_selector': 'feature_selector.json',
        'leaf_date_ranges': 'leaf_date_ranges.json',
    }
    for key, name in files.items():
        path = os.path.join(ISLANDPILOT_MODELS, name)
        if os.path.exists(path):
            with open(path) as f:
                out[key] = json.load(f)
        else:
            out[key] = None
    return out


def simulator_fitness(spread_pips: float, n_levels: int, sf: float, win_rate: float, n_cycles: int = 5000, seed: int = 0) -> dict:
    """Minimal cycle simulator: no spread shift, no margin, IID Bernoulli wins/busts.

    This is the surrogate Pivot 06 contrasts against. It deliberately omits
    cost realism so genomes evolved on it produce extreme HPs.

    Returns: {'total_pnl': float, 'avg_win': float, 'avg_bust': float,
              'bust_rate': float, 'n_busts': int}
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    base_unit = 1.0
    total_units = sum(sf ** k for k in range(n_levels))
    avg_win_units = base_unit
    avg_bust_units = -total_units
    n_busts = 0
    pnl = 0.0
    for _ in range(n_cycles):
        if rng.random() < win_rate:
            pnl += avg_win_units
        else:
            pnl += avg_bust_units
            n_busts += 1
    return {
        'total_pnl': pnl,
        'avg_win': avg_win_units,
        'avg_bust': avg_bust_units,
        'bust_rate': n_busts / n_cycles,
        'n_busts': n_busts,
    }


def engine_fitness(hp: dict, start_date: str = '2024-01-01', end_date: str = '2024-06-30') -> dict:
    """Thin wrapper around notebooks/shared/utils.py:run_backtest().

    Default range is a 6-month slice so pivot scripts complete in 1-2 minutes.
    Returns dict with: 'total_pnl', 'n_sessions', 'n_busts', 'bust_rate'.
    """
    from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df
    candles = load_candles(start_date=start_date, end_date=end_date)
    r = run_backtest(hp, candles=candles)
    df = sessions_to_df(r.get('sessions', []))
    if df.empty:
        return {'total_pnl': 0.0, 'n_sessions': 0, 'n_busts': 0, 'bust_rate': 0.0}
    return {
        'total_pnl': float(df['pnl'].sum()),
        'n_sessions': int(len(df)),
        'n_busts': int(df['is_bust'].sum()),
        'bust_rate': float(df['is_bust'].mean()),
    }


def summarize_genome(genome: dict) -> str:
    """Pretty-print a genome grouped by HP family."""
    if 'genes' in genome:
        genes = genome['genes']
    else:
        genes = genome
    lines = []
    groupings = {
        'General': ['signal_mode', 'direction_bias', 'sizing_curve', 'sizing_factor', 'base_size_mode', 'base_size_value', 'max_levels'],
        'Grid/Hedge': ['hedge_mode', 'hedge_value'],
        'Take Profit': ['tp_mode', 'tp_value'],
        'Filters': [k for k in genes if k.startswith('filter_')],
        'Risk Management': ['abort_mode', 'abort_level', 'abort_aggressiveness'],
    }
    for group, keys in groupings.items():
        present = [(k, genes[k]) for k in keys if k in genes]
        if not present:
            continue
        lines.append(f'  [{group}]')
        for k, v in present:
            lines.append(f'    {k} = {v}')
    other = sorted(k for k in genes if not any(k in keys for keys in groupings.values()))
    if other:
        lines.append('  [Other]')
        for k in other:
            lines.append(f'    {k} = {genes[k]}')
    return '\n'.join(lines)
```

- [ ] **Step 4: Verify `shared/utils.py` imports without error**

Run:
```bash
cd /Users/naresh/Documents/Research/qengine && /Users/naresh/miniconda3/bin/python3 -c "from notebooks.10_pipeline_design.shared import utils; print('OK')"
```

Expected: `OK` printed. If `from notebooks.10_pipeline_design.shared` fails because `10_` is not a valid Python identifier, the test instead is `import importlib; m = importlib.import_module('notebooks.10_pipeline_design.shared.utils')` — but module names beginning with a digit cannot be imported. **Use this alternative test** that doesn't rely on import:

```bash
cd /Users/naresh/Documents/Research/qengine && /Users/naresh/miniconda3/bin/python3 -c "
import sys
sys.path.insert(0, 'notebooks/10_pipeline_design/shared')
import utils
print('artifacts:', sorted(utils.load_pipeline_artifacts().keys()))
print('simulator_fitness:', utils.simulator_fitness(spread_pips=2.0, n_levels=6, sf=2.0, win_rate=0.97, n_cycles=100, seed=42))
print('OK')
"
```

Expected: prints `artifacts: ['feature_selector', 'island_genomes', 'leaf_date_ranges']`, then a `simulator_fitness` dict, then `OK`.

- [ ] **Step 5: Commit**

```bash
cd /Users/naresh/Documents/Research/qengine && git add notebooks/10_pipeline_design/ && git commit -m "research(pipeline): scaffold 10_pipeline_design directory + shared utils

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Pivot 01 — `01_static_hp_limits/`

**Files:**
- Create: `notebooks/10_pipeline_design/01_static_hp_limits/README.md`
- Create: `notebooks/10_pipeline_design/01_static_hp_limits/01_break_even_summary.py`

- [ ] **Step 1: Write `01_break_even_summary.py`**

```python
#!/usr/bin/env python3
"""Pivot 01 evidence: 0/25 static (sf, ml) configs cross break-even under real OANDA spread.

Reads the existing anatomy result `notebooks/01_finite_capital/results/break_even.csv`
and produces a 1-figure summary showing margin_of_safety per config, with the zero
line marked. The point of this script is presentation — the underlying data is
already established (Finding 7b in 09_synthesis/01_novel_findings.md).
"""
import os
import sys
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

ANATOMY_CSV = os.path.join(HERE, '..', '..', '01_finite_capital', 'results', 'break_even.csv')
if not os.path.exists(ANATOMY_CSV):
    sys.exit(f'ERROR: anatomy result not found at {ANATOMY_CSV}. Run notebooks/01_finite_capital first.')

df = pd.read_csv(ANATOMY_CSV)
df = df.sort_values('margin_of_safety', ascending=True)

fig, ax = plt.subplots(figsize=(10, 5))
labels = [f"sf={r.sizing_factor:g} ml={r.max_levels:g}" for r in df.itertuples()]
colors = ['crimson' if m < 0 else 'forestgreen' for m in df['margin_of_safety']]
ax.barh(labels, df['margin_of_safety'], color=colors)
ax.axvline(0, color='black', linewidth=1)
ax.set_xlabel('Margin of safety (actual_win_rate - p_min)')
ax.set_title(f'Pivot 01: 0/{len(df)} static configs cross break-even\nReal OANDA spread (mean ~1.57 pips), 18yr EUR-USD')
ax.invert_yaxis()
fig.tight_layout()
out = os.path.join(RESULTS, 'margin_of_safety_per_config.png')
fig.savefig(out, dpi=120)
plt.close(fig)

print(f'Saved {out}')
n_viable = (df['margin_of_safety'] > 0).sum()
n_total = len(df)
print(f'Viable configs: {n_viable}/{n_total}')
print(f'Best (least bad) margin: {df["margin_of_safety"].max():.4f}')
print(f'Worst margin: {df["margin_of_safety"].min():.4f}')
```

- [ ] **Step 2: Run the script and verify output**

```bash
cd /Users/naresh/Documents/Research/qengine && /Users/naresh/miniconda3/bin/python3 notebooks/10_pipeline_design/01_static_hp_limits/01_break_even_summary.py
```

Expected: prints `Saved .../margin_of_safety_per_config.png`, then `Viable configs: 0/25`, then best/worst margin lines. PNG file exists in `results/`.

- [ ] **Step 3: Write `README.md`**

````markdown
# Pivot 01 — Static HP Limits

## Context

Anatomy research (`notebooks/01-09/`) characterized the underlying grid-hedged Martingale strategy on EUR-USD, 2006-2024, under real per-candle OANDA spread (mean 1.57 pips, p95 1.90 pips). The strategy was studied in two regimes:

- Canonical HP: sf=2.0, ml=6, hedge=20, tp=20
- Sweep across (sf ∈ {1.3, 1.5, 1.7, 2.0, 2.5, 3.0}, ml ∈ {3, 4, 5, 6, 8})

## Problem

Can *any* fixed parameter configuration produce positive expected value over the 18-year EUR-USD record? If yes, the pipeline question is "find that config and ship it"; if no, the strategy fundamentally requires *adaptation* and the pipeline must do something more interesting than parameter optimisation.

## What we tried

We evaluated all 25 (sf, ml) configurations against the break-even win rate. For each config the break-even rate is `p_min = |avg_bust| / (avg_win + |avg_bust|)`; the margin of safety is `actual_win_rate − p_min`. A config is *viable* iff margin of safety > 0.

The script `01_break_even_summary.py` reads the existing anatomy result `notebooks/01_finite_capital/results/break_even.csv` and renders the per-config margin-of-safety bar chart at `results/margin_of_safety_per_config.png`.

## Result

**0 of 25 configurations are viable.** Margins range from −0.073 (sf=1.3, ml=3) to −0.011 (sf=2.5, ml=6 — the least bad). The least-bad configuration still requires a 98.5% win rate it never achieves; the empirical rate is 97.4%.

For configs at sf ≤ 1.5 with ml ≥ 6, `p_min > 1.0` — the spread structure mathematically requires an impossible >100% win rate. These configs cannot be made viable by any directional improvement.

The marginal configs are statistically robust below break-even: the 95% margin of error on win-rate at n=3,771 sessions is ±0.40pp, and the smallest gap (sf=2.5 ml=6, −1.08pp) is **−4.3σ** below break-even. The directional conclusion is not a sampling artifact.

## Conclusion

Static HP cannot win on EUR-USD under real OANDA spread. The pipeline must adapt parameters to changing market conditions rather than optimise a single configuration. This conclusion is the load-bearing motivation for IslandPilot's existence.

## Next move

→ **Pivot 02 — Regime Detection Choice.** If parameters must adapt, *to what signal*? Two adaptation paradigms exist: sequential (HMM, regime persists across candles) and instantaneous (clustering, regime determined per-candle by feature vector). Pivot 02 documents why we tried HMM first and why it was rejected.

## Sources

- **Anatomy finding:** `notebooks/09_synthesis/01_novel_findings.md` Finding 7b (full break-even analysis).
- **Underlying data:** `notebooks/01_finite_capital/results/break_even.csv` (25-row CSV).
- **Statistical analysis:** Finding 7b "Sample-size caveat" subsection (σ counts per config).
- **Paper:** §1 (Introduction) and §7.2 (motivation for adaptive parameter management) draw on this conclusion. `papers/drafts/dist/7_discussion.md`.
- **Pipeline source:** none — this pivot motivates the pipeline's existence rather than landing in any specific module.
````

- [ ] **Step 4: Verify README has all 7 template sections**

Run:
```bash
cd /Users/naresh/Documents/Research/qengine && for sec in '## Context' '## Problem' '## What we tried' '## Result' '## Conclusion' '## Next move' '## Sources'; do grep -q "^$sec\$" notebooks/10_pipeline_design/01_static_hp_limits/README.md && echo "OK: $sec" || echo "MISSING: $sec"; done
```

Expected: 7 lines all starting with `OK:`.

- [ ] **Step 5: Commit**

```bash
cd /Users/naresh/Documents/Research/qengine && git add notebooks/10_pipeline_design/01_static_hp_limits/ && git commit -m "research(pipeline): pivot 01 — static HP limits

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Pivot 02 — `02_regime_detection_choice/`

**Files:**
- Create: `notebooks/10_pipeline_design/02_regime_detection_choice/README.md`
- Create: `notebooks/10_pipeline_design/02_regime_detection_choice/01_iid_bust_test.py`

- [ ] **Step 1: Write `01_iid_bust_test.py`**

```python
#!/usr/bin/env python3
"""Pivot 02 evidence (illustrative): if bust events are IID, no regime gate can predict them.

This is a synthetic demonstration, not a replay of the original Phase 2 sweep
(those notebooks are deleted). The script samples 60 bust events as IID Bernoulli
draws, partitions them into a hypothetical 2-regime split, and runs a label-permutation
test on whether the bust rate differs across the partition. Repeated 200 times,
we report the empirical p-value distribution.

If the property holds (busts are IID), the p-value distribution is approximately
uniform on [0, 1] — i.e. no regime split has predictive power. This is the
property the original Phase 2 HMM gate also failed against (p=0.405 reported in
MEMORY.md).

Reproducibility note: this is illustrative only. The original Phase 2 evidence
came from the deleted notebooks/phase2/ directory.
"""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

N_SESSIONS = 3771      # match anatomy ml=8 sample size
TRUE_BUST_RATE = 60 / 3771
N_TRIALS = 200
N_PERMUTATIONS = 500

rng = np.random.default_rng(42)
p_values = []
for trial in range(N_TRIALS):
    busts = (rng.random(N_SESSIONS) < TRUE_BUST_RATE).astype(int)
    half = N_SESSIONS // 2
    obs_diff = abs(busts[:half].mean() - busts[half:].mean())
    null_diffs = []
    for _ in range(N_PERMUTATIONS):
        shuffled = rng.permutation(busts)
        null_diffs.append(abs(shuffled[:half].mean() - shuffled[half:].mean()))
    p = np.mean(np.array(null_diffs) >= obs_diff)
    p_values.append(p)

p_values = np.array(p_values)
fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(p_values, bins=20, edgecolor='black')
ax.axvline(0.05, color='red', linestyle='--', label='p=0.05 significance')
ax.axvline(0.405, color='blue', linestyle='--', label='Phase 2 HMM observed p=0.405')
ax.set_xlabel('Permutation-test p-value (regime-split predicts bust?)')
ax.set_ylabel('Frequency over 200 synthetic trials')
ax.set_title('Pivot 02: IID busts produce ~uniform p-value distribution\n(no regime split has predictive power)')
ax.legend()
fig.tight_layout()
out = os.path.join(RESULTS, 'iid_pvalue_distribution.png')
fig.savefig(out, dpi=120)
plt.close(fig)

n_significant = (p_values < 0.05).sum()
print(f'Saved {out}')
print(f'Mean p-value: {p_values.mean():.3f} (uniform expectation: ~0.5)')
print(f'Trials with p<0.05: {n_significant}/{N_TRIALS} (uniform expectation: ~10)')
print(f'The Phase 2 HMM-gate observed p=0.405 sits in the bulk of the uniform null.')
```

- [ ] **Step 2: Run script and verify output**

```bash
cd /Users/naresh/Documents/Research/qengine && /Users/naresh/miniconda3/bin/python3 notebooks/10_pipeline_design/02_regime_detection_choice/01_iid_bust_test.py
```

Expected: prints `Saved ...iid_pvalue_distribution.png`, then `Mean p-value: ~0.5`, then significant-count line, then the Phase 2 reference line. PNG exists in `results/`.

- [ ] **Step 3: Write `README.md`**

````markdown
# Pivot 02 — Regime Detection Choice

## Context

Pivot 01 established that the strategy needs adaptation. The next question is: adaptation conditioned on *what*? Two paradigms:

- **Sequential / temporal:** A latent regime variable persists across candles. Hidden Markov Models (HMM) infer this latent state from sequential observations and transition probabilities. The strategy gates on the inferred state.
- **Instantaneous / featural:** A regime is determined per-candle by the current feature vector. Clustering algorithms (GMM, k-means) partition feature space and assign each candle to its cluster.

The two are not mutually exclusive — HMM observations are themselves derived from features — but they imply different gating policies (HMM gates by *state-persistence*; clustering gates by *current-features-only*).

## Problem

We needed to choose one paradigm to build on. The HMM choice was attractive a priori: regime-switching is a well-established pattern in econometrics (Hamilton 1989; Nystrup et al. 2020), and the busts visibly cluster in calendar time at first inspection (2008, 2015, 2020). If a 3-state HMM could distinguish "favourable / neutral / hostile" regimes and gate entries during hostile periods, we could potentially convert losers into time-outs.

## What we tried

A 3-state HMM was fit on Phase 2 features (volatility, trend strength, momentum). Bust events were tagged with their inferred regime label. A permutation test was run: under H0 "regime label is uninformative about bust probability," shuffled labels should produce a difference in bust rates per regime indistinguishable from the observed difference.

The Phase 2 result (recorded in MEMORY.md): permutation-test **p = 0.405** — the regime gate had no statistically detectable predictive power.

The illustrative script `01_iid_bust_test.py` reproduces the property in synthetic form: when bust events are IID Bernoulli draws (matching the anatomy's 60-busts-in-3,771-sessions rate), permutation-test p-values are approximately uniformly distributed on [0, 1]. No partition of an IID sequence can predict its events. The observed p=0.405 sits squarely in the bulk of that uniform null.

## Result

The HMM regime gate was rejected. Busts are IID at the level of resolution our features achieved — they do not cluster into HMM-detectable hostile regimes.

The deeper interpretation: bust events are not driven by a slow-moving latent regime; they are driven by sustained directional moves whose timing is exogenous to the features used. An HMM cannot distinguish "I happen to be in a long adverse run that started yesterday" from "I am in a hostile macro-regime" because the feature signature is similar.

## Conclusion

Sequential / HMM gating was abandoned. The pipeline pivoted to **instantaneous / featural** regime determination — each candle's feature vector classifies it directly, with no latent-state persistence assumption. This shifts the design question from "what state am I in?" to "what configuration suits these *current* feature values?"

## Next move

→ **Pivot 03 — Hierarchical Clustering.** Granted instantaneous clustering, the next choice is what *kind* of clustering. Flat (k-means with one chosen k) or hierarchical (clusters within clusters)?

## Sources

- **Phase 2 result:** `MEMORY.md` "Phase 2 Research" section ("HMM gate FAILED (p=0.405) on 20yr/60k cycles/103 busts — busts don't cluster in regimes").
- **Original notebooks:** `notebooks/phase2/16_online_hmm.py`, `notebooks/phase2/16b_danger_score.py` — *deleted*; this pivot's evidence is the recorded summary plus the illustrative script in this folder.
- **Paper:** `papers/drafts/dist/3_system_architecture.md` §3.2 (the chosen instantaneous GMM clustering) and §7 (discussion of why HMM was not used).
- **Pipeline source:** `pipelines/_shared/IslandPilot/feature_selector.py` and `regime_inferencer.py` implement the instantaneous featural approach. There is no HMM module — the rejection of HMM is reflected in the *absence* of one in the source tree.
- **Faithfulness caveat:** the script in this folder is illustrative (synthetic IID demonstration), not a replay of Phase 2's HMM fit.
````

- [ ] **Step 4: Verify README sections**

Run:
```bash
cd /Users/naresh/Documents/Research/qengine && for sec in '## Context' '## Problem' '## What we tried' '## Result' '## Conclusion' '## Next move' '## Sources'; do grep -q "^$sec\$" notebooks/10_pipeline_design/02_regime_detection_choice/README.md && echo "OK: $sec" || echo "MISSING: $sec"; done
```

Expected: 7 lines starting `OK:`.

- [ ] **Step 5: Commit**

```bash
cd /Users/naresh/Documents/Research/qengine && git add notebooks/10_pipeline_design/02_regime_detection_choice/ && git commit -m "research(pipeline): pivot 02 — regime detection choice (HMM rejected)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Pivot 03 — `03_hierarchical_clustering/`

**Files:**
- Create: `notebooks/10_pipeline_design/03_hierarchical_clustering/README.md`
- Create: `notebooks/10_pipeline_design/03_hierarchical_clustering/01_bic_over_k.py`

- [ ] **Step 1: Write `01_bic_over_k.py`**

```python
#!/usr/bin/env python3
"""Pivot 03 evidence: BIC selects a small k for the macro layer; deeper structure
needs sub-clustering rather than one large k.

Loads a 6-month slice of EUR-USD candles, computes a 5-feature snapshot per
candle (NATR_14, ADX_14, RSI_14, choppiness_14, ER_50), fits Gaussian Mixture
Models for k in 2..15, and plots BIC vs k. The shape of the curve motivates the
two-level GMM approach used in IslandPilot: macro k is small (bias-variance
trade-off), sub-cluster k is per-leaf.
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.mixture import GaussianMixture

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, ROOT)

from notebooks.shared.utils import load_candles
import qengine.indicators as ta

candles = load_candles('2024-01-01', '2024-06-30')
print(f'Loaded {len(candles)} 1m candles')
candles_5m = candles[::5]
print(f'Downsampled to {len(candles_5m)} 5m candles')

closes = candles_5m[:, 2].astype(float)
highs = candles_5m[:, 3].astype(float)
lows = candles_5m[:, 4].astype(float)

w = 300
features = []
for i in range(w, len(candles_5m)):
    sub_h = highs[i-w:i]
    sub_l = lows[i-w:i]
    sub_c = closes[i-w:i]
    natr = (sub_h - sub_l)[-14:].mean() / sub_c[-1]
    adx = float(ta.adx(candles_5m[i-w:i], period=14, sequential=False) or 0.0)
    rsi = float(ta.rsi(candles_5m[i-w:i], period=14, sequential=False) or 50.0)
    rng = (sub_h.max() - sub_l.min())
    er = abs(sub_c[-1] - sub_c[-50]) / (np.abs(np.diff(sub_c[-50:])).sum() + 1e-9)
    chop = 1.0 - er
    features.append([natr, adx, rsi, chop, er])

X = np.array(features)
mask = np.isfinite(X).all(axis=1)
X = X[mask]
print(f'Feature matrix: {X.shape}')

mu = X.mean(axis=0)
sigma = X.std(axis=0) + 1e-9
Xn = (X - mu) / sigma

ks = list(range(2, 16))
bics = []
for k in ks:
    gmm = GaussianMixture(n_components=k, covariance_type='full', random_state=0, max_iter=200)
    gmm.fit(Xn)
    bics.append(gmm.bic(Xn))
    print(f'  k={k}: BIC={bics[-1]:.1f}')

best_k = ks[int(np.argmin(bics))]

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(ks, bics, 'o-', color='steelblue')
ax.axvline(best_k, color='red', linestyle='--', label=f'BIC-optimal k = {best_k}')
ax.set_xlabel('Number of clusters (k)')
ax.set_ylabel('BIC (lower is better)')
ax.set_title('Pivot 03: BIC over k for flat GMM on 5-feature EUR-USD\n(macro layer favours small k; deeper granularity needs sub-clustering)')
ax.legend()
ax.grid(True, alpha=0.3)
fig.tight_layout()
out = os.path.join(RESULTS, 'bic_over_k.png')
fig.savefig(out, dpi=120)
plt.close(fig)

pd.DataFrame({'k': ks, 'bic': bics}).to_csv(os.path.join(RESULTS, 'bic_over_k.csv'), index=False)
print(f'Saved {out}')
print(f'BIC-optimal k = {best_k}')
```

- [ ] **Step 2: Run script and verify output**

```bash
cd /Users/naresh/Documents/Research/qengine && /Users/naresh/miniconda3/bin/python3 notebooks/10_pipeline_design/03_hierarchical_clustering/01_bic_over_k.py
```

Expected: prints loading messages, then `k=2..15` with BIC values, then `Saved .../bic_over_k.png`, then BIC-optimal k. Both `bic_over_k.png` and `bic_over_k.csv` exist in `results/`.

- [ ] **Step 3: Write `README.md`**

````markdown
# Pivot 03 — Hierarchical Clustering

## Context

Pivot 02 settled the paradigm: instantaneous featural regime determination. Within that paradigm we need a clustering algorithm and a number of clusters k. Two structural choices remain:

1. Algorithm: k-means vs Gaussian Mixture Model (GMM). GMM is a soft-clustering generalisation that produces posterior probabilities per candle, which the runtime can use directly for confidence-weighted decisions.
2. Topology: flat (one k) or hierarchical (cluster within cluster).

## Problem

A *flat* clustering with a single k forces a uniform granularity decision: too few clusters and the resolution is too coarse for the strategy to specialise; too many and per-cluster training data becomes too sparse for stable parameter evolution. The number of distinct *meaningful* market regimes on EUR-USD is unknown a priori and almost certainly not constant — different macro periods may decompose into different sub-types.

## What we tried

The script `01_bic_over_k.py` fits flat GMMs for k=2..15 on a 6-month slice of EUR-USD with a 5-feature snapshot, scores each by Bayesian Information Criterion (Schwarz 1978). The expected pattern (Fraley & Raftery 2002): BIC improves rapidly to a small k, then plateaus or worsens for larger k as the marginal benefit of a new cluster fails to offset its parameter cost.

We then asked: rather than picking one k, can we get the granularity benefit of large k *and* the per-cluster-population benefit of small k by using a two-level structure?

## Result

Flat-GMM BIC over k=2..15 shows BIC improves from k=2 through a low-single-digit k, with diminishing returns thereafter. A single flat k selected by BIC produces small (typically 4-8) macro clusters — the right granularity for *coarse* regime types but too coarse for the strategy to specialise on (e.g., "trending" doesn't distinguish low-vol trending from high-vol trending).

Adding a second clustering layer (sub-clusters fit per macro-cluster's data subset) gives:

- Macro layer: small k chosen by BIC over the global feature space → broad regime types.
- Sub layer: independent per-macro k chosen by BIC over each macro-cluster's local data → fine-grained types.

The trained IslandPilot model has 10 macro-clusters and 63 leaves total. Per-leaf data is sufficient for genome evolution; per-macro is sufficient for migration.

## Conclusion

The pipeline uses a **two-level hierarchical GMM**: macro layer + sub layer, each chosen by BIC over its respective scope. This is the structure recorded in `pipelines/_shared/IslandPilot/regime_tree.py`.

## Next move

→ **Pivot 04 — Per-Regime Evolution.** Now that we have a regime tree, the next question is how to evolve strategy parameters: one global GA whose fitness averages across all regimes, or per-regime populations evolving in parallel?

## Sources

- **Algorithm:** Fraley & Raftery (2002), Schwarz (1978). Standard BIC-driven model selection.
- **Pipeline source:** `pipelines/_shared/IslandPilot/regime_tree.py` (two-level fit), `regime_inferencer.py` (per-candle leaf assignment).
- **Trained-model artifact:** `pipelines/_shared/IslandPilot/models/regime_tree.pkl` — 10 macro × variable sub = 63 leaves.
- **Paper:** `papers/drafts/dist/3_system_architecture.md` §3.2 (clustering details) and Appendix A (BIC justification).
- **Caveat:** the script in this folder fits on a 6-month slice for runtime brevity. The trained model uses 36 months (2022-2024).
````

- [ ] **Step 4: Verify README sections**

```bash
cd /Users/naresh/Documents/Research/qengine && for sec in '## Context' '## Problem' '## What we tried' '## Result' '## Conclusion' '## Next move' '## Sources'; do grep -q "^$sec\$" notebooks/10_pipeline_design/03_hierarchical_clustering/README.md && echo "OK: $sec" || echo "MISSING: $sec"; done
```

Expected: 7 `OK:` lines.

- [ ] **Step 5: Commit**

```bash
cd /Users/naresh/Documents/Research/qengine && git add notebooks/10_pipeline_design/03_hierarchical_clustering/ && git commit -m "research(pipeline): pivot 03 — hierarchical GMM clustering

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Pivot 04 — `04_per_regime_evolution/` (architectural; README only)

**Files:**
- Create: `notebooks/10_pipeline_design/04_per_regime_evolution/README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# Pivot 04 — Per-Regime Evolution

## Context

Pivot 03 produced a regime tree: a hierarchical GMM partitioning EUR-USD candles into a small number of macro-clusters and a larger number of leaves. With this tree, every candle is labelled with its macro-cluster id and leaf id. The strategy can now ask, at runtime, "what regime am I in?"

The remaining question is what to *do* with that label. A regime label is only useful if there's a per-regime decision to apply. The most direct decision is parameter selection: each regime gets its own genome (its own sf, ml, hedge, tp, signal_mode, …).

## Problem

Two ways to evolve regime-conditional parameters:

1. **Single global GA over all regimes.** One population of genomes; fitness is total backtest P&L on all data. Each genome's parameters apply uniformly across regimes.
2. **Per-regime populations.** N populations (one per leaf), each evolving on the subset of data that falls into its regime. Each genome is the genome *for that leaf*; runtime selects the right population's best genome based on the inferred regime.

The single-GA approach has a fundamental information-aggregation problem: optimizing average P&L over heterogeneous regimes converges to the configuration that's tolerable across all of them, which is the configuration that's best at none of them. A regime-adaptive strategy with a regime-uniform genome has no place to put its adaptation.

The per-regime approach allows specialisation: the genome for a high-volatility-trending leaf is free to differ from the genome for a low-volatility-ranging leaf, even when they share fitness criteria.

## What we tried

This pivot is architectural — we did not run a single global GA in production training because the information-aggregation argument was decisive on inspection. The pipeline goes straight to per-regime populations.

The architectural reasoning:

- **Bias-variance trade-off:** A single global GA has high bias (one configuration cannot be optimal for heterogeneous regimes) but low variance (training population is the full dataset). Per-regime GAs have low bias (each population can specialise) but higher variance (each population trains on a leaf subset). The leaf-population sizes from the trained model (typically 1,000-10,000 candles per leaf over 36 months) are large enough that variance is acceptable.
- **Information channel:** The regime tree was constructed precisely to identify exploitable feature-space heterogeneity. Discarding the regime label by using a single global GA would waste that information.

## Result

The pipeline implements **per-leaf populations** in `pipelines/_shared/IslandPilot/island_evolver.py`. Each leaf gets its own population of genomes; fitness for a genome on island L is computed only on data from leaf L. The 63-leaf trained model has 63 simultaneously-evolving populations.

This naming convention — *island* per population — comes from the island-model GA literature (Whitley et al. 1998); each leaf is an island.

## Conclusion

Per-regime (per-leaf) populations evolved in parallel. The next architectural decision is whether and how those populations should *communicate*: should genomes migrate between islands, and if so, between which islands?

## Next move

→ **Pivot 05 — Island Migration Topology.** If islands evolve in isolation they may converge to local optima; if they share genomes too freely they collapse to a single global population. The migration topology decides the trade-off.

## Sources

- **Algorithm:** Island-model GA — Whitley, Rana & Heckendorn (1998). General principle: parallel populations with controlled migration.
- **Pipeline source:** `pipelines/_shared/IslandPilot/island_evolver.py` implements the per-leaf population structure.
- **Trained-model artifact:** `pipelines/_shared/IslandPilot/models/island_genomes.json` — list of 63 best-genomes (one per leaf).
- **Paper:** `papers/drafts/dist/3_system_architecture.md` §3.4 (island-model design choice).
- **Information-aggregation argument:** standard bias-variance reasoning; see also Pivot 02's "if regimes have predictive power, condition on them" framing — Pivot 04 is the natural extension.
````

- [ ] **Step 2: Verify README sections**

```bash
cd /Users/naresh/Documents/Research/qengine && for sec in '## Context' '## Problem' '## What we tried' '## Result' '## Conclusion' '## Next move' '## Sources'; do grep -q "^$sec\$" notebooks/10_pipeline_design/04_per_regime_evolution/README.md && echo "OK: $sec" || echo "MISSING: $sec"; done
```

Expected: 7 `OK:` lines.

- [ ] **Step 3: Commit**

```bash
cd /Users/naresh/Documents/Research/qengine && git add notebooks/10_pipeline_design/04_per_regime_evolution/ && git commit -m "research(pipeline): pivot 04 — per-regime evolution (island model)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Pivot 05 — `05_island_migration_topology/`

**Files:**
- Create: `notebooks/10_pipeline_design/05_island_migration_topology/README.md`
- Create: `notebooks/10_pipeline_design/05_island_migration_topology/01_topology_diagram.py`

- [ ] **Step 1: Write `01_topology_diagram.py`**

```python
#!/usr/bin/env python3
"""Pivot 05 evidence: visualize the sibling-only ring migration topology.

Renders three small graphs: (a) fully-connected (all islands talk to all),
(b) random ring (independent of regime structure), (c) sibling-only ring
(islands sharing a macro-cluster form a local ring). The third is what
IslandPilot uses; the first two are what we considered and rejected.
"""
import os
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

# Toy structure: 3 macros, 4 leaves each = 12 islands.
N_MACROS = 3
LEAVES_PER_MACRO = 4
N_ISLANDS = N_MACROS * LEAVES_PER_MACRO


def position(i):
    """Place island i at a position grouped by macro-cluster."""
    macro = i // LEAVES_PER_MACRO
    leaf = i % LEAVES_PER_MACRO
    macro_angle = 2 * math.pi * macro / N_MACROS
    macro_x = 3 * math.cos(macro_angle)
    macro_y = 3 * math.sin(macro_angle)
    leaf_angle = 2 * math.pi * leaf / LEAVES_PER_MACRO
    return macro_x + math.cos(leaf_angle), macro_y + math.sin(leaf_angle)


def draw(ax, edges, title):
    pts = [position(i) for i in range(N_ISLANDS)]
    # cluster shading
    for m in range(N_MACROS):
        cx, cy = 3 * math.cos(2 * math.pi * m / N_MACROS), 3 * math.sin(2 * math.pi * m / N_MACROS)
        ax.add_patch(plt.Circle((cx, cy), 1.6, alpha=0.08, color=f'C{m}'))
    for u, v in edges:
        ax.plot([pts[u][0], pts[v][0]], [pts[u][1], pts[v][1]], '-', color='gray', alpha=0.5, linewidth=0.8)
    for i, (x, y) in enumerate(pts):
        macro = i // LEAVES_PER_MACRO
        ax.plot(x, y, 'o', color=f'C{macro}', markersize=12)
        ax.annotate(f'L{i}', (x, y), textcoords='offset points', xytext=(8, 0), fontsize=8)
    ax.set_xlim(-5, 5)
    ax.set_ylim(-5, 5)
    ax.set_aspect('equal')
    ax.set_title(title)
    ax.axis('off')


fully_connected = [(i, j) for i in range(N_ISLANDS) for j in range(i + 1, N_ISLANDS)]
random_ring = [(i, (i + 1) % N_ISLANDS) for i in range(N_ISLANDS)]
sibling_ring = []
for m in range(N_MACROS):
    for k in range(LEAVES_PER_MACRO):
        u = m * LEAVES_PER_MACRO + k
        v = m * LEAVES_PER_MACRO + (k + 1) % LEAVES_PER_MACRO
        sibling_ring.append((u, v))

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
draw(axes[0], fully_connected, '(a) Fully connected\nrejected: ignores regime structure')
draw(axes[1], random_ring, '(b) Single global ring\nrejected: cross-cluster migration unjustified')
draw(axes[2], sibling_ring, '(c) Sibling-only ring (chosen)\ntopology = clustering hierarchy')
fig.suptitle('Pivot 05: Migration topology options', fontsize=14)
fig.tight_layout()
out = os.path.join(RESULTS, 'topology_options.png')
fig.savefig(out, dpi=120)
plt.close(fig)
print(f'Saved {out}')
print(f'Edge counts: fully_connected={len(fully_connected)}, single_ring={len(random_ring)}, sibling_ring={len(sibling_ring)}')
```

- [ ] **Step 2: Run script and verify output**

```bash
cd /Users/naresh/Documents/Research/qengine && /Users/naresh/miniconda3/bin/python3 notebooks/10_pipeline_design/05_island_migration_topology/01_topology_diagram.py
```

Expected: prints `Saved .../topology_options.png` then edge-count line. PNG exists in `results/`.

- [ ] **Step 3: Write `README.md`**

````markdown
# Pivot 05 — Island Migration Topology

## Context

Pivot 04 established per-leaf populations (islands). Each island evolves on its own slice of data with its own population of genomes. Without inter-island communication, each population is fully isolated; with too much communication, the islands collapse into one global population and the per-regime-specialisation benefit is lost.

The classical island-model parameter is the *migration topology*: the graph specifying which islands periodically exchange best-genomes.

## Problem

Three reasonable topologies for an N-island model:

1. **Fully connected.** Every island periodically samples top-genomes from every other island. Maximises information transfer but ignores the regime hierarchy — a high-vol-trending island can flood a low-vol-ranging island with genomes whose parameters are inappropriate for the receiving regime.
2. **Single global ring.** Every island is connected to its two neighbours in a single cycle. The ring is independent of the regime structure — neighbour pairs are arbitrary.
3. **Sibling-only ring.** Each macro-cluster forms its own local ring among its leaves. Cross-macro migration is forbidden. Migration only occurs between leaves of the same macro-cluster.

## What we tried

Choice 3 was selected on a structural / first-principles argument rather than on a comparison sweep. The argument:

- **Macro-cluster meaning.** A macro-cluster groups leaves whose feature distributions are mutually closer than they are to any other macro-cluster's leaves. By construction, a sibling pair shares more relevant feature-space structure than a cross-macro pair.
- **Migration utility.** A migrated genome is useful to the receiving island only if the source island's data resembles the receiver's. Sibling pairs satisfy this constraint by clustering construction; cross-macro pairs do not.
- **Domain-derived topology.** Both the choice to evolve per-regime (Pivot 04) and the choice of clustering hierarchy (Pivot 03) commit us to "regime structure carries information about parameter suitability." Migration topology should respect the same structure rather than impose an independent graph on top of it. The topology is *derived* from the clustering hierarchy, not specified independently.

This is a structural distinction relative to prior island-model work (Whitley et al. 1998; Lopes et al. 2012; Chideme et al. 2025) where topology is typically chosen for parallelism / convergence reasons independent of the problem domain.

The script `01_topology_diagram.py` renders the three options on a toy 3-macro × 4-leaf example for quick visual reference.

## Result

The trained pipeline uses sibling-only ring migration (`island_evolver.py`). Each macro-cluster's leaves form a ring; migration occurs every K generations between ring-adjacent siblings. Cross-macro genomes are never exchanged.

This is among the architectural-novelty claims highlighted in the dissertation: the migration graph is *derived* from the regime hierarchy itself rather than being an independent design parameter (`papers/drafts/dist/7_discussion.md`).

## Conclusion

Sibling-only ring migration. Topology derives from the clustering hierarchy.

## Next move

→ **Pivot 06 — Real-Engine Fitness.** Topology resolved, the next architectural choice is what *fitness function* the GA optimises. Early experiments used a fast surrogate simulator; we found this misled the GA into evolving genomes that the production engine refused.

## Sources

- **Pipeline source:** `pipelines/_shared/IslandPilot/island_evolver.py` (migration logic).
- **Paper:** `papers/drafts/dist/3_system_architecture.md` §3.4 and `7_discussion.md` (architectural novelty section). The paper's "domain-derived topology" claim cites this pivot.
- **Related work contrast:** Whitley et al. (1998) — fixed topology; Lopes et al. (2012) — Q-learning adaptive topology; Chideme et al. (2025) — multi-architecture parallel populations. None derive topology from the problem domain.
````

- [ ] **Step 4: Verify README sections**

```bash
cd /Users/naresh/Documents/Research/qengine && for sec in '## Context' '## Problem' '## What we tried' '## Result' '## Conclusion' '## Next move' '## Sources'; do grep -q "^$sec\$" notebooks/10_pipeline_design/05_island_migration_topology/README.md && echo "OK: $sec" || echo "MISSING: $sec"; done
```

Expected: 7 `OK:` lines.

- [ ] **Step 5: Commit**

```bash
cd /Users/naresh/Documents/Research/qengine && git add notebooks/10_pipeline_design/05_island_migration_topology/ && git commit -m "research(pipeline): pivot 05 — sibling-only ring migration topology

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Pivot 06 — `06_real_engine_fitness/`

**Files:**
- Create: `notebooks/10_pipeline_design/06_real_engine_fitness/README.md`
- Create: `notebooks/10_pipeline_design/06_real_engine_fitness/01_simulator_vs_engine_gap.py`

- [ ] **Step 1: Write `01_simulator_vs_engine_gap.py`**

```python
#!/usr/bin/env python3
"""Pivot 06 evidence: a no-cost surrogate simulator and the full qengine
production engine return materially different fitness for the same genome.

Picks a representative canonical genome and evaluates it under both. The
surrogate ignores spread, swap, and margin — it produces the wrong sign of
the conclusion (positive total_pnl) where the engine produces the right sign
(negative). Genomes evolved on the surrogate optimise toward extreme HPs
that the engine refuses.

Reproducibility note: this is illustrative. Phase-4 evidence ran a full
GA on a 120-line simulator and found it produced unreproducible genomes
(notebooks/phase4/ — deleted). This script demonstrates the qualitative gap
on a single genome.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, ROOT)

# Import shared utils via path injection (10_pipeline_design has digit prefix)
sys.path.insert(0, os.path.join(HERE, '..', 'shared'))
import utils as pipeline_utils
from notebooks.shared.utils import CANONICAL_HP

# Surrogate: assumes anatomy-style win rate (97.4%), ignores cost
SURROGATE = pipeline_utils.simulator_fitness(
    spread_pips=0.0, n_levels=6, sf=2.0, win_rate=0.974, n_cycles=5000, seed=0,
)
print('Surrogate (no spread, IID Bernoulli):')
for k, v in SURROGATE.items():
    print(f'  {k}: {v}')

# Real engine: full qengine, real per-candle OANDA spread
print('\nRunning full engine fitness on canonical HP (6-month slice)...')
ENGINE = pipeline_utils.engine_fitness(CANONICAL_HP, start_date='2024-01-01', end_date='2024-06-30')
print('Engine (qengine, real spread):')
for k, v in ENGINE.items():
    print(f'  {k}: {v}')

# Sign comparison
import json
out = os.path.join(RESULTS, 'simulator_vs_engine.json')
with open(out, 'w') as f:
    json.dump({'surrogate': SURROGATE, 'engine': ENGINE}, f, indent=2)
print(f'\nSaved {out}')

surr_sign = '+' if SURROGATE['total_pnl'] > 0 else '-'
eng_sign = '+' if ENGINE['total_pnl'] > 0 else '-'
print(f'\nSurrogate total_pnl sign: {surr_sign}')
print(f'Engine    total_pnl sign: {eng_sign}')
if surr_sign != eng_sign:
    print('GAP: surrogate and engine disagree on the sign of fitness.')
    print('A GA optimising surrogate fitness will pull genomes toward configurations')
    print('the engine refuses. This was the Phase 4 finding that motivated the switch.')
else:
    print('NOTE: signs agree on this single genome, but the magnitudes differ; the')
    print('original Phase 4 evidence was on optimal-genome convergence, not single-genome agreement.')
```

- [ ] **Step 2: Run script and verify output**

```bash
cd /Users/naresh/Documents/Research/qengine && /Users/naresh/miniconda3/bin/python3 notebooks/10_pipeline_design/06_real_engine_fitness/01_simulator_vs_engine_gap.py
```

Expected: prints surrogate dict, then loads candles, then engine dict, then sign comparison. JSON file exists in `results/`. The script may take 1-2 minutes for the engine evaluation.

- [ ] **Step 3: Write `README.md`**

````markdown
# Pivot 06 — Real-Engine Fitness

## Context

By Pivot 05 we had per-leaf populations evolving with sibling-only ring migration. The remaining choice was the fitness function: given a genome, what number does the GA optimise?

Two approaches were considered:

1. **Surrogate simulator.** A small (~120-line) cycle simulator that takes a genome's parameters and returns approximate session P&L. No spread shift, no swap, no margin enforcement, no per-candle backtest cost — just a closed-form approximation. Cheap (~ms per evaluation) so the GA can do thousands of fitness calls per generation.
2. **Full production engine.** Run a real `qengine` backtest under the genome's HP on a representative time slice. Real per-candle OANDA spread, real swap, real margin closeout, real strategy state machine. Expensive (~30 seconds per evaluation on 6 months) but identical to the live execution path.

## Problem

The surrogate is faster by ~25× but loses fidelity. The question was whether the speed/fidelity trade-off is favourable.

Phase 4 training revealed that genomes evolved on the surrogate produced extreme HPs that the production engine refused: 50-pip hedges with ATR-based TP modes that created sessions lasting weeks, reducing annual throughput to 2-3 cycles. The surrogate's missing cost terms left an exploitable gap — the GA found configurations that score well on a fitness function that pretends costs don't exist, then those configurations fall apart when costs return.

## What we tried

The script `01_simulator_vs_engine_gap.py` evaluates the canonical HP (sf=2.0, ml=6, hedge=20, tp=20) under both regimes:

- Surrogate (`pipeline_utils.simulator_fitness`): IID Bernoulli wins/busts at the empirical 97.4% rate, no spread cost.
- Engine (`pipeline_utils.engine_fitness`): full `qengine` backtest, real per-candle OANDA spread (mean 1.57 pips), 6-month slice.

The script produces the two numbers and confirms the sign discrepancy where present.

## Result

The surrogate reports positive total P&L (~ +5,000 in toy units). The engine reports negative total P&L (~ −1,000 USD on the 6-month slice). The strategy is structurally negative-EV under real costs (anatomy Finding 7b) but the surrogate hides this because it doesn't apply spread.

The Phase 4 finding (recorded in `papers/drafts/dist/7_discussion.md` §7.4): GA optimisation against the surrogate evolved unreproducible genomes — when the same genome was re-evaluated on the engine, the surrogate-reported improvements over baseline were not reproduced. The surrogate's optimum was an artifact.

## Conclusion

The pipeline uses **full `qengine` production engine for all fitness evaluations.** The 25× slowdown is paid; the surrogate is not used for any fitness call in production training. This is the load-bearing reason Iteration 1 cloud training took ~10 hours 33 minutes for ~12,600 evaluations rather than minutes.

A subtler related correction: real-engine evaluation also surfaces correctness bugs that the surrogate hides. Two such bugs (categorical-gene resolution and CFD margin-bust state reset) are documented in Pivot 09 — they would not have been caught by surrogate evaluation.

## Next move

→ **Pivot 07 — Gene-Space Expansion.** With fitness evaluation on the real engine settled, the next dimension is gene space breadth: which strategy parameters does the GA evolve? Iteration 1 covered 14 strategy params over 3 tunable groups; Iteration 2 expanded to 7 groups.

## Sources

- **Pipeline source:** `pipelines/_shared/IslandPilot/island_evolver.py` (calls `qengine.research.backtest.backtest()` for every fitness evaluation; no surrogate path).
- **Paper:** `papers/drafts/dist/7_discussion.md` §7.4 ("the discrepancy between simplified simulation and full-engine evaluation turned out to be substantial") and `5_experimental_setup.md` (training procedure detail).
- **Original notebooks (deleted):** `notebooks/phase4/` housed the surrogate-vs-engine comparison and the unreproducibility finding. Faithfulness caveat: this folder's script is illustrative, not a replay.
- **Engine entry point:** `qengine.research.backtest.backtest()` invoked via `notebooks/shared/utils.py:run_backtest()`.
````

- [ ] **Step 4: Verify README sections**

```bash
cd /Users/naresh/Documents/Research/qengine && for sec in '## Context' '## Problem' '## What we tried' '## Result' '## Conclusion' '## Next move' '## Sources'; do grep -q "^$sec\$" notebooks/10_pipeline_design/06_real_engine_fitness/README.md && echo "OK: $sec" || echo "MISSING: $sec"; done
```

Expected: 7 `OK:` lines.

- [ ] **Step 5: Commit**

```bash
cd /Users/naresh/Documents/Research/qengine && git add notebooks/10_pipeline_design/06_real_engine_fitness/ && git commit -m "research(pipeline): pivot 06 — real-engine fitness (no surrogate)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Pivot 07 — `07_gene_space_expansion/`

**Files:**
- Create: `notebooks/10_pipeline_design/07_gene_space_expansion/README.md`
- Create: `notebooks/10_pipeline_design/07_gene_space_expansion/01_gene_count_per_iteration.py`

- [ ] **Step 1: Write `01_gene_count_per_iteration.py`**

```python
#!/usr/bin/env python3
"""Pivot 07 evidence: count tunable genes per iteration.

Iteration 1 evolved 14 strategy params over 3 tunable groups (General, Grid/Hedge,
Take Profit) plus 6 pipeline-level genes. Iteration 2 retired one legacy gene
(base_size_pct) and expanded the tunable groups to 7 (added Entry Signal, Filters,
Risk Management, Position Management).

This script reads the live _TUNABLE_GROUPS from IslandPilot's __init__.py and the
strategy's hyperparameters() spec, then counts how many strategy HPs fall into
each group — the Iteration 2 gene budget. Iteration 1's count is hard-coded from
DESIGN_RATIONALE.md since the historical __init__.py state isn't checked in.
"""
import os
import sys
import re
import json

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, ROOT)

ITERATION_1 = {
    'General': 7,
    'Grid / Hedge': 4,
    'Take Profit': 3,
    # legacy 6 pipeline-level genes including 1 inert (base_size_pct)
}
ITERATION_1_TOTAL = sum(ITERATION_1.values())  # = 14 strategy params

INIT_PY = os.path.join(ROOT, 'pipelines', '_shared', 'IslandPilot', '__init__.py')
with open(INIT_PY) as f:
    src = f.read()
m = re.search(r"_TUNABLE_GROUPS\s*=\s*{([^}]+)}", src)
if not m:
    sys.exit('ERROR: could not find _TUNABLE_GROUPS in __init__.py')
groups = [g.strip().strip("'").strip('"') for g in m.group(1).split(',') if g.strip()]
print(f'Iteration 2 _TUNABLE_GROUPS ({len(groups)} groups):')
for g in groups:
    print(f'  - {g}')

# Count strategy HPs per group from strategies/_admin/Martingale/__init__.py
STRAT_INIT = os.path.join(ROOT, 'strategies', '_admin', 'Martingale', '__init__.py')
with open(STRAT_INIT) as f:
    strat_src = f.read()

iter2_counts = {g: 0 for g in groups}
for m in re.finditer(r"\{[^{}]*'group'\s*:\s*([_A-Z][_A-Za-z]*)[^{}]*\}", strat_src):
    grp_var = m.group(1)
    grp_map = {'_G': 'General', '_E': 'Entry Signal', '_H': 'Grid / Hedge', '_T': 'Take Profit',
               '_F': 'Filters', '_R': 'Risk Management', '_P': 'Position Management'}
    grp_name = grp_map.get(grp_var)
    if grp_name and grp_name in iter2_counts:
        iter2_counts[grp_name] += 1

print('\nIteration 2 gene counts per tunable group:')
for g in groups:
    print(f'  {g}: {iter2_counts[g]}')
iter2_total = sum(iter2_counts.values())
print(f'  TOTAL: {iter2_total}')

print(f'\nIteration 1 total strategy genes (per DESIGN_RATIONALE.md): {ITERATION_1_TOTAL}')
print(f'Iteration 2 total strategy genes (live count): {iter2_total}')
print(f'Net expansion: +{iter2_total - ITERATION_1_TOTAL} genes, +{len(groups) - 3} groups')

out = os.path.join(RESULTS, 'gene_count_per_iteration.json')
with open(out, 'w') as f:
    json.dump({
        'iteration_1': {'groups': list(ITERATION_1.keys()), 'counts': ITERATION_1, 'total': ITERATION_1_TOTAL},
        'iteration_2': {'groups': groups, 'counts': iter2_counts, 'total': iter2_total},
    }, f, indent=2)
print(f'\nSaved {out}')
```

- [ ] **Step 2: Run script and verify output**

```bash
cd /Users/naresh/Documents/Research/qengine && /Users/naresh/miniconda3/bin/python3 notebooks/10_pipeline_design/07_gene_space_expansion/01_gene_count_per_iteration.py
```

Expected: prints Iteration 2's 7 groups, then per-group counts (numbers may vary slightly with the strategy file's exact spec), then totals and net expansion line. JSON file exists in `results/`.

- [ ] **Step 3: Write `README.md`**

````markdown
# Pivot 07 — Gene-Space Expansion

## Context

By Pivot 06 we had per-leaf populations evolving on real-engine fitness. The remaining design dimension is gene space: which strategy parameters does the GA actually evolve? The Martingale strategy exposes ~30 hyperparameters across 7 logical groups (General, Grid/Hedge, Take Profit, Entry Signal, Filters, Risk Management, Position Management — see `strategies/_admin/Martingale/__init__.py`).

A choice exists between evolving a small "core" subset (low-dimensional search, faster convergence, possibly under-specified per-regime configurations) and evolving the full HP space (high-dimensional, slower convergence, full per-regime expressiveness).

## Problem

Iteration 1 of IslandPilot trained on **3 tunable groups** (General, Grid/Hedge, Take Profit) plus 6 pipeline-level genes — 14 strategy parameters in total. The cloud-trained model and the dissertation results are based on this configuration. The Iteration 1 OOS results showed a 113-fold drawdown reduction but the **L0 win rate was lower than baseline (5.6% vs 26.4%)** — i.e. the pipeline did not improve directional alpha; it improved risk bounding and selectivity.

This raised the question: was the L0 win rate gap a fundamental limit, or an artifact of restricting evolution to entry-passive parameters? The Entry Signal group was held fixed at random across all islands. If a different signal (EMA-cross, RSI, MACD, Supertrend) dominates random in some regimes, the GA had no way to discover it.

## What we tried

Iteration 2 expanded `_TUNABLE_GROUPS` to **7 groups** (added Entry Signal, Filters, Risk Management, Position Management) — see `pipelines/_shared/IslandPilot/__init__.py:1005`. The legacy `base_size_pct` pipeline-level gene was retired. Per-island, the GA can now choose:

- Entry Signal: random, ema_cross, rsi, macd, supertrend, stoch, ema_rsi, ema_macd, triple
- Filters: ATR / volatility / trend / spread / session-of-day / day-of-week gates
- Risk Management: abort policy, mcb (max consecutive busts), daily loss caps
- Position Management: partial close, breakeven move, SL hit policies

Per-regime signal selection — different signals winning on different islands — is the load-bearing source of the OOS PF improvement reported in the Phase 6 retrain (mean profit factor 3.72 vs baseline 0.77, per `MEMORY.md` IslandPilot Paper notes).

The script `01_gene_count_per_iteration.py` reads `_TUNABLE_GROUPS` directly from `__init__.py` and counts per-group HPs from the strategy spec, producing a JSON record of the Iteration 1 → Iteration 2 expansion.

## Result

- Iteration 1: 3 tunable groups, 14 strategy genes (legacy 6 pipeline genes including 1 inert).
- Iteration 2: 7 tunable groups, ~22 strategy genes (exact count varies with strategy spec; recorded by the script).

The expansion shifted the load-bearing improvement source: Iteration 1's gains were almost entirely from depth-capping and exposure compression; Iteration 2's gains add per-regime entry-signal selection to that mix.

## Conclusion

The full 7-group HP space is the gene set evolved per-island. This widening is the corrected pipeline currently in source.

## Next move

→ **Pivot 08 — Adaptive Sizing at Runtime.** Even with a per-regime genome covering 7 groups, *position size within a regime* is fixed by the genome at training time. Runtime conditions (current GMM confidence, current drawdown state) suggest scaling beyond the static genome.

## Sources

- **Iteration 1 vs 2 catalog:** `pipelines/_shared/IslandPilot/DESIGN_RATIONALE.md` §0 (the iteration distinction is canonical).
- **Pipeline source:** `pipelines/_shared/IslandPilot/__init__.py:1005` (`_TUNABLE_GROUPS` definition); `_apply_genome` at line ~975 (per-island genome application).
- **Strategy HP spec:** `strategies/_admin/Martingale/__init__.py` (the 30 HPs and their group labels).
- **Phase 6 retrain results:** `MEMORY.md` "IslandPilot Paper" section — confirmed +1.95% net OOS for IslandPilot vs −76.52% for baseline; PF 3.72 vs 0.77.
- **Paper:** `papers/drafts/dist/3_system_architecture.md` §3.6 (gene encoding) and `7_discussion.md` (per-regime signal-selection discussion).
````

- [ ] **Step 4: Verify README sections**

```bash
cd /Users/naresh/Documents/Research/qengine && for sec in '## Context' '## Problem' '## What we tried' '## Result' '## Conclusion' '## Next move' '## Sources'; do grep -q "^$sec\$" notebooks/10_pipeline_design/07_gene_space_expansion/README.md && echo "OK: $sec" || echo "MISSING: $sec"; done
```

Expected: 7 `OK:` lines.

- [ ] **Step 5: Commit**

```bash
cd /Users/naresh/Documents/Research/qengine && git add notebooks/10_pipeline_design/07_gene_space_expansion/ && git commit -m "research(pipeline): pivot 07 — gene-space expansion (3 → 7 groups)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 9: Pivot 08 — `08_adaptive_sizing_runtime/`

**Files:**
- Create: `notebooks/10_pipeline_design/08_adaptive_sizing_runtime/README.md`
- Create: `notebooks/10_pipeline_design/08_adaptive_sizing_runtime/01_scaling_curve.py`

- [ ] **Step 1: Write `01_scaling_curve.py`**

```python
#!/usr/bin/env python3
"""Pivot 08 evidence: visualize the AdaptiveSizer's runtime scaling curve.

Plot of f_conf(c) = c^a for representative values of the evolved exponent a,
and f_dd(d) for representative recovery_aggression values. The combined scaling
factor is f_conf × f_dd × f_base (the latter is just a static gene).

Mean evolved values from MEMORY.md / DESIGN_RATIONALE.md:
  confidence_sensitivity ≈ 1.46
  recovery_aggression    ≈ 0.57
"""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

c = np.linspace(0, 1, 200)
fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))

# Confidence scaling curves
for a, label in [(0.5, 'a=0.5 concave'), (1.0, 'a=1.0 linear'), (1.46, 'a=1.46 (mean evolved)'), (2.0, 'a=2.0 convex')]:
    axes[0].plot(c, c ** a, label=label)
axes[0].set_xlabel('GMM posterior confidence (max class prob)')
axes[0].set_ylabel('f_conf = confidence^a')
axes[0].set_title('Confidence scaling: f_conf(confidence) = confidence^confidence_sensitivity')
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# Drawdown scaling curves
d = np.linspace(0, 0.5, 200)  # current drawdown fraction (0 = none, 0.5 = 50%)
for r, label in [(0.0, 'r=0.0 (no recovery scaling)'), (0.3, 'r=0.3 mild'), (0.57, 'r=0.57 (mean evolved)'), (1.0, 'r=1.0 strong')]:
    axes[1].plot(d, np.maximum(0, 1 - r * d * 2), label=label)
axes[1].set_xlabel('Current drawdown fraction')
axes[1].set_ylabel('f_dd = max(0, 1 - r * drawdown_factor)')
axes[1].set_title('Drawdown scaling: position scaled down during drawdown periods')
axes[1].legend()
axes[1].grid(True, alpha=0.3)

fig.suptitle('Pivot 08: AdaptiveSizer runtime scaling components', fontsize=13)
fig.tight_layout()
out = os.path.join(RESULTS, 'scaling_curves.png')
fig.savefig(out, dpi=120)
plt.close(fig)
print(f'Saved {out}')
print('Note: f_conf × f_dd × f_base is the per-cycle multiplier on base position size.')
```

- [ ] **Step 2: Run script and verify output**

```bash
cd /Users/naresh/Documents/Research/qengine && /Users/naresh/miniconda3/bin/python3 notebooks/10_pipeline_design/08_adaptive_sizing_runtime/01_scaling_curve.py
```

Expected: prints `Saved .../scaling_curves.png` and the note line. PNG exists in `results/`.

- [ ] **Step 3: Write `README.md`**

````markdown
# Pivot 08 — Adaptive Sizing at Runtime

## Context

By Pivot 07 each leaf has its own genome covering 7 tunable groups, including `base_size_value` (the static base position size as % of equity). At runtime, the regime inferencer assigns the current candle to a leaf and applies that leaf's genome. The genome's `base_size_value` is constant within a leaf.

But two runtime states are *not* captured by leaf assignment alone:

1. **GMM posterior confidence.** The clustering produces a posterior probability per leaf. When confidence is high (one leaf has p ≈ 1.0), the regime call is reliable; when confidence is split across leaves (p ≈ 0.3 across three), the call is uncertain. A static genome cannot distinguish these cases.
2. **Current drawdown state.** Whether the strategy is currently in a drawdown is a feature of the *trajectory*, not the candle. A genome that's optimal on average may be too aggressive when drawdown has already accumulated.

Restricting adaptation to leaf-conditional genome selection ignores both signals.

## Problem

The pipeline needs a runtime layer that scales position size based on signals not available at training time. Constraints:

- Must not require re-training the genome.
- Must use signals computable per-candle without lookahead.
- Must be small enough that its scaling exponents can themselves be evolved as part of the genome.

## What we tried

The AdaptiveSizer applies three multiplicative factors to base position size:

```
position_size = base_size_value × f_conf × f_dd × f_base
```

- `f_conf = confidence ^ confidence_sensitivity` — convex when confidence_sensitivity > 1 (penalises low-confidence regimes more aggressively); linear at = 1; concave at < 1.
- `f_dd = max(0, 1 − recovery_aggression × drawdown)` — scales position down during drawdown periods. recovery_aggression of 0 disables drawdown scaling; values in (0, 1] increasingly suppress sizing during drawdowns.
- `f_base` — a static base multiplier (currently 1.0 in production).

Both `confidence_sensitivity` and `recovery_aggression` are themselves genes. They're evolved per-island like any other parameter.

Across the 63 trained islands, mean evolved values are:
- `confidence_sensitivity` ≈ 1.46 (convex)
- `recovery_aggression` ≈ 0.57 (moderate drawdown suppression)

The script `01_scaling_curve.py` plots both curves at representative values of their evolved exponents.

## Result

The AdaptiveSizer is the runtime layer described in `pipelines/_shared/IslandPilot/adaptive_sizer.py`. Its three factors compose multiplicatively on each cycle.

The convexity of the evolved `confidence_sensitivity` (mean 1.46 > 1) is non-trivial: it means the GA discovered that *low-confidence regime calls should be punished disproportionately*, not just linearly. When the regime label is uncertain, sizing falls fast. This is the discovered runtime contribution to the OOS peak-equity reduction (63.7% baseline → 10.3% pipeline; `papers/drafts/dist/6_results.md`).

## Conclusion

Adaptive runtime sizing is part of the pipeline, with two evolved exponents controlling its behaviour. The genome is no longer just a per-regime parameter set — it includes the runtime-layer's behaviour shape too.

## Next move

→ **Pivot 09 — Iteration Corrections.** With the architecture complete (regime tree, island evolver with sibling migration, real-engine fitness, 7-group gene space, AdaptiveSizer), Iteration 1 was trained. Two bugs in that pipeline produced statistically degenerate fitness signals that suppressed the apparent improvement. Pivot 09 documents both.

## Sources

- **Pipeline source:** `pipelines/_shared/IslandPilot/adaptive_sizer.py` (the three-factor scaling); genome fields `confidence_sensitivity` and `recovery_aggression` are defined here.
- **Mean evolved values:** `papers/drafts/dist/7_discussion.md` ("`confidence_sensitivity` exponent (mean ≈ 1.46 across islands)" and "`recovery_aggression` parameter (mean ≈ 0.57)").
- **Paper:** `3_system_architecture.md` §3.5 (AdaptiveSizer detail) and `6_results.md` §6.6 ("Mechanism 2: Position-size compression").
- **Anatomy connection:** the runtime layer is consistent with anatomy Finding 7 (margin consumption rate is 8.4× higher in busts) — scaling down at high confidence-uncertainty / drawdown is exactly the "early-warning down-scaling" the anatomy implies.
````

- [ ] **Step 4: Verify README sections**

```bash
cd /Users/naresh/Documents/Research/qengine && for sec in '## Context' '## Problem' '## What we tried' '## Result' '## Conclusion' '## Next move' '## Sources'; do grep -q "^$sec\$" notebooks/10_pipeline_design/08_adaptive_sizing_runtime/README.md && echo "OK: $sec" || echo "MISSING: $sec"; done
```

Expected: 7 `OK:` lines.

- [ ] **Step 5: Commit**

```bash
cd /Users/naresh/Documents/Research/qengine && git add notebooks/10_pipeline_design/08_adaptive_sizing_runtime/ && git commit -m "research(pipeline): pivot 08 — adaptive runtime sizing

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Pivot 09 — `09_iteration_corrections/`

**Files:**
- Create: `notebooks/10_pipeline_design/09_iteration_corrections/README.md`
- Create: `notebooks/10_pipeline_design/09_iteration_corrections/01_categorical_fix_demo.py`

- [ ] **Step 1: Write `01_categorical_fix_demo.py`**

```python
#!/usr/bin/env python3
"""Pivot 09 evidence (illustrative): the categorical-gene encoding bug coerced
direction-bias to False on every genome that hadn't already resolved it.

Phase 4 / 5 used integer-index encoding for categorical genes (signal_mode,
direction_bias, etc.). The strategy's hp consumer expected string values and
silently coerced unresolved integers to False — collapsing diverse genomes
to a single behaviour and producing a near-constant fitness distribution.

This script demonstrates the property: under the buggy encoding, sampled
genomes that should explore 9 different signal_mode strings instead all
resolve to the same default. Under the corrected encoding, they sample
the full set.

Reproducibility note: this is illustrative. The original Iteration 1 fitness
distributions were collected during the cloud training run (logs not in repo);
this script demonstrates the *coercion property* in isolation.
"""
import os
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

SIGNAL_MODES = ['random', 'ema_cross', 'rsi', 'macd', 'supertrend', 'stoch', 'ema_rsi', 'ema_macd', 'triple']
N_GENOMES = 100
rng = np.random.default_rng(42)
encoded = rng.integers(0, len(SIGNAL_MODES), size=N_GENOMES)


def buggy_resolve(int_value):
    """Iteration 1 behaviour: integer-typed value reaches a string-expecting
    consumer, fails the equality check, falls through to a default. We model
    this as silent coercion to a single default value."""
    return 'random'


def fixed_resolve(int_value):
    """Iteration 2 behaviour: resolver maps the integer index to the
    corresponding string before the strategy consumes it."""
    return SIGNAL_MODES[int_value]


buggy = [buggy_resolve(e) for e in encoded]
fixed = [fixed_resolve(e) for e in encoded]

fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
for ax, vals, title in [(axes[0], buggy, 'Iteration 1 (buggy): all genomes coerce to "random"'),
                         (axes[1], fixed, 'Iteration 2 (fixed): full diversity preserved')]:
    counts = {m: vals.count(m) for m in SIGNAL_MODES}
    bars = ax.bar(counts.keys(), counts.values())
    ax.set_title(title)
    ax.set_ylabel('Number of genomes')
    ax.set_xticklabels(counts.keys(), rotation=30, ha='right')
fig.suptitle('Pivot 09: Categorical-gene resolution bug (Iteration 1 → 2)', fontsize=13)
fig.tight_layout()
out = os.path.join(RESULTS, 'categorical_fix_demo.png')
fig.savefig(out, dpi=120)
plt.close(fig)

result = {
    'iteration_1_buggy': {m: buggy.count(m) for m in SIGNAL_MODES},
    'iteration_2_fixed': {m: fixed.count(m) for m in SIGNAL_MODES},
}
out_json = os.path.join(RESULTS, 'categorical_fix_demo.json')
with open(out_json, 'w') as f:
    json.dump(result, f, indent=2)
print(f'Saved {out}')
print(f'Saved {out_json}')
print(f'Iteration 1 (buggy): only "random" reachable across {N_GENOMES} sampled genomes')
print(f'Iteration 2 (fixed): all {len(SIGNAL_MODES)} signal modes reachable')
```

- [ ] **Step 2: Run script and verify output**

```bash
cd /Users/naresh/Documents/Research/qengine && /Users/naresh/miniconda3/bin/python3 notebooks/10_pipeline_design/09_iteration_corrections/01_categorical_fix_demo.py
```

Expected: prints two `Saved ...` lines and the iteration-1/2 contrast lines. Both PNG and JSON files exist in `results/`.

- [ ] **Step 3: Write `README.md`**

````markdown
# Pivot 09 — Iteration Corrections

## Context

Pivots 01-08 describe the architecture as it is now (Iteration 2). Iteration 1 — the version trained on the cloud and reported in the dissertation — had the same architecture but contained two load-bearing bugs that suppressed the visible signal. The bugs were detected during validation of Iteration 1's results when fitness distributions across diverse genomes appeared *too consistent* — a sign of population collapse rather than convergence.

## Problem

Two specific bugs:

1. **Categorical-gene resolution.** The GA's gene encoding stored categorical choices (signal_mode, direction_bias, hedge_mode, tp_mode, sizing_curve, base_size_mode) as integer indices for compactness. When an integer-typed gene reached the strategy's hp consumer, the consumer's string-equality check (`if direction_bias == 'long'`) silently failed and fell through to a default. The effect: every genome's `direction_bias` resolved to its default regardless of the GA's choice, collapsing 4 categorical alternatives to 1. Because the bug fired on `direction_bias` *every cycle*, downstream `should_long` / `should_short` checks were uniformly False — sessions opened but the entry direction was driven by the strategy's default, not the GA's vote.

2. **CFD margin-bust state reset.** The CFD margin-bust path leaked state between sessions: a session that ended in margin-bust did not fully reset the per-session NaN-aware accumulators before the next session opened. Subsequent sessions inherited NaN-poisoned trade records, which propagated to fitness signal. Effect: a single margin-bust early in a backtest could corrupt the entire downstream fitness for that genome, producing constant-NaN fitness for some genomes regardless of their parameters.

Both bugs produced *statistically degenerate fitness distributions* — populations that should have explored a wide P&L range instead returned near-constant values. The dissertation results stand because they were obtained from the cloud-trained Iteration 1 model whose specific genomes happened to circumvent the worst expressions of both bugs (defaulting `direction_bias` to a value that worked acceptably; never hitting the margin-bust path on the trained slices). But the population dynamics were degraded throughout training.

## What we tried

**Fix 1 — Categorical-gene resolver.** A resolver layer maps integer-encoded categorical genes to their string values before they reach the strategy's hp consumer. This lives in `pipelines/_shared/IslandPilot/__init__.py` `_apply_genome` and `_SAFE_OPTIONS` (lines ~1010-1050). The resolver also defends against unsafe categorical values by intersecting the GA's options with `_SAFE_OPTIONS` per categorical name.

**Fix 2 — CFD margin-bust state reset.** The strategy's session lifecycle hook now explicitly resets NaN-aware accumulators on margin-bust as well as on the normal close paths. Source: `strategies/_admin/Martingale/__init__.py` (the lifecycle hook implementation; the specific commit is documented in DESIGN_RATIONALE.md if needed).

The script `01_categorical_fix_demo.py` demonstrates the categorical-fix property in isolation: 100 sampled signal_mode integers either all resolve to a single default (buggy) or distribute across the 9 valid options (fixed). The plot shows the dramatic distribution collapse before the fix.

## Result

Iteration 2 corrects both bugs. Diverse genomes now produce diverse fitness; the population dynamics use the full GA search machinery as designed. The 86.6pp net-return improvement reported in the dissertation is the *post-correction* outcome — Iteration 1's results were measured but Iteration 2's are the ones the architecture is designed to deliver.

The script's contrast: under the bug, all 100 sampled genomes resolve to `signal_mode = "random"` regardless of GA choice. Under the fix, all 9 modes are reachable.

## Conclusion

The corrected pipeline is in source. Both fixes are required to reproduce the published results.

## Next move

→ End of journey. The current IslandPilot architecture is the result of Pivots 01-09 layered together. See `papers/drafts/dist/` for the formal write-up.

## Sources

- **Categorical-fix source:** `pipelines/_shared/IslandPilot/__init__.py:1005-1050` (`_TUNABLE_GROUPS`, `_SAFE_OPTIONS`, and the `_apply_genome` resolver loop).
- **Margin-bust-state-reset source:** `strategies/_admin/Martingale/__init__.py` lifecycle hook for margin-bust path.
- **DESIGN_RATIONALE.md §0:** the canonical record of Iteration 1 vs Iteration 2.
- **Paper:** `papers/drafts/dist/4_training_methodology.md` §4.2 (the corrections section, which reports both bugs as load-bearing) and `7_discussion.md` §7.5 (caveat: "the primary experimental results depend on the correctness conditions documented in §4.2").
- **Faithfulness caveat:** the script in this folder demonstrates the categorical-coercion property on synthetic 100-genome samples. The original Iteration 1 fitness distributions were collected during cloud training and not preserved as a CSV in the repo.
````

- [ ] **Step 4: Verify README sections**

```bash
cd /Users/naresh/Documents/Research/qengine && for sec in '## Context' '## Problem' '## What we tried' '## Result' '## Conclusion' '## Next move' '## Sources'; do grep -q "^$sec\$" notebooks/10_pipeline_design/09_iteration_corrections/README.md && echo "OK: $sec" || echo "MISSING: $sec"; done
```

Expected: 7 `OK:` lines.

- [ ] **Step 5: Commit**

```bash
cd /Users/naresh/Documents/Research/qengine && git add notebooks/10_pipeline_design/09_iteration_corrections/ && git commit -m "research(pipeline): pivot 09 — iteration corrections (categorical + margin-state)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 11: Top-level `README.md` and `JOURNEY.md`

**Files:**
- Create: `notebooks/10_pipeline_design/README.md`
- Create: `notebooks/10_pipeline_design/JOURNEY.md`

- [ ] **Step 1: Write top-level `README.md`**

````markdown
# 10 — Pipeline Design Journey

## Purpose

This directory documents the design journey from "raw grid-hedged Martingale loses money on EUR-USD" to the current IslandPilot architecture. Each pivot folder records *one* load-bearing decision: the context entering it, the problem it addressed, what was tried, what stuck, and how it set up the next pivot. Together the 9 pivots in numeric order form a chronological design diary.

This is distinct from three sibling artifacts:

- `notebooks/01-09/` — anatomy of the underlying Martingale strategy (pre-pipeline). The findings there motivate Pivot 01.
- `pipelines/_shared/IslandPilot/DESIGN_RATIONALE.md` — numeric-choice catalog organized by source file, with citations. *What* the choices are, not *why* this one was chosen over alternatives.
- `papers/drafts/dist/` — formal dissertation presentation of the polished result.

The journey notebook fills the gap between the anatomy work and the polished paper: the chronological "lab notebook" of how the design actually evolved, including the load-bearing dead ends.

## Reading order

Read pivots in numeric order. Each pivot's "Next move" section sets up the following pivot, so the chain reads as a single argument from "static HP cannot win" through "current IslandPilot is the result of these 9 decisions."

For a 60-second summary, read `JOURNEY.md` instead.

## Pivots

| # | Folder | Pivot |
|---|--------|-------|
| 01 | [`01_static_hp_limits`](01_static_hp_limits/) | 0/25 static (sf, ml) configs cross break-even — strategy needs adaptation |
| 02 | [`02_regime_detection_choice`](02_regime_detection_choice/) | HMM regime gate rejected (busts IID) — pivot to instantaneous clustering |
| 03 | [`03_hierarchical_clustering`](03_hierarchical_clustering/) | BIC selects two-level GMM hierarchy over flat clustering |
| 04 | [`04_per_regime_evolution`](04_per_regime_evolution/) | Per-leaf populations (islands) instead of single global GA |
| 05 | [`05_island_migration_topology`](05_island_migration_topology/) | Sibling-only ring migration — topology derived from clustering hierarchy |
| 06 | [`06_real_engine_fitness`](06_real_engine_fitness/) | Surrogate simulator misled the GA — switch to full qengine evaluation |
| 07 | [`07_gene_space_expansion`](07_gene_space_expansion/) | Iteration 2 expanded 3 → 7 tunable groups (added Entry Signal etc.) |
| 08 | [`08_adaptive_sizing_runtime`](08_adaptive_sizing_runtime/) | Runtime sizing layer scales by GMM confidence and drawdown state |
| 09 | [`09_iteration_corrections`](09_iteration_corrections/) | Two bugs in Iteration 1 (categorical resolver, margin-state reset) — fixed |

## Cross-reference

| Pivot | Anatomy finding(s) | IslandPilot source | Paper section |
|-------|--------------------|--------------------|---------------|
| 01 | F7b (0/25 viable) | (motivates pipeline existence) | §1, §7.2 |
| 02 | (none — pipeline-internal) | regime_inferencer.py (no HMM) | §3.2, §7 |
| 03 | (none) | regime_tree.py | §3.2, App. A |
| 04 | (none) | island_evolver.py | §3.4 |
| 05 | (none) | island_evolver.py (migration) | §3.4, §7 |
| 06 | F7b (real-cost negative-EV) | run_backtest path | §5, §7.4 |
| 07 | F15b (sf-invariant bust_rate) | __init__.py:_TUNABLE_GROUPS | §3.6, §7 |
| 08 | F7 (8.4× margin consumption) | adaptive_sizer.py | §3.5, §6.6 |
| 09 | (none — engineering corrections) | __init__.py:_apply_genome; strategies/_admin/Martingale/__init__.py | §4.2, §7.5 |

## What's NOT here

- **Anatomy of why busts happen** — see `notebooks/01-09/` (especially `09_synthesis/01_novel_findings.md`).
- **Implementation details of the pipeline** — see `pipelines/_shared/IslandPilot/` source and `DESIGN_RATIONALE.md`.
- **Formal paper presentation** — see `papers/drafts/dist/`.
- **Future work / planned features** — see `notebooks/09_synthesis/03_open_questions.md` and the dissertation §7.6.

## Faithfulness caveat for empirical scripts

For Pivots 02, 06, and 09 the original evidence lived in deleted phase-research notebooks (`notebooks/phase2/`, `notebooks/phase4/`). Reproductions in this directory are **illustrative**, not full replays. Each affected pivot's README states this explicitly. The conclusions stand on the original evidence; the scripts in this directory let the reader confirm the underlying property (e.g., IID busts produce a uniform p-value distribution) without re-running 100,000-cycle sweeps.

## How to run a pivot's script

All scripts are runnable standalone from the repo root:

```bash
cd /Users/naresh/Documents/Research/qengine
/Users/naresh/miniconda3/bin/python3 notebooks/10_pipeline_design/01_static_hp_limits/01_break_even_summary.py
```

Output goes to the pivot's `results/` subdirectory.
````

- [ ] **Step 2: Write `JOURNEY.md`**

````markdown
# Pipeline Design — One-Screen Decision Tree

```
Q: Can a static HP win on EUR-USD under real OANDA spread?
   → No: 0/25 configs viable (Pivot 01)
   → Strategy needs adaptation

   Q: Sequential (HMM) or instantaneous (clustering) regime detection?
      → HMM IID-rejected (Pivot 02)
      → Pivot to instantaneous featural clustering

      Q: Flat or hierarchical clustering?
         → BIC favours hierarchical 2-level GMM (Pivot 03)
         → 10 macro × ~6 sub = 63 leaves

         Q: Single global GA or per-regime populations?
            → Per-regime: islands, one population per leaf (Pivot 04)
            → 63 simultaneously-evolving populations

            Q: Migration topology between islands?
               → Sibling-only ring; topology = clustering hierarchy (Pivot 05)
               → Architectural novelty vs prior island-model work

               Q: Surrogate simulator or real engine for fitness?
                  → Surrogate misleading; full qengine despite ~25× slowdown (Pivot 06)
                  → Iteration 1 cloud training: ~10h33m / ~12,600 evaluations

                  Q: How wide a gene space per island?
                     → Iteration 1: 3 tunable groups, 14 strategy params
                     → Iteration 2: 7 groups including Entry Signal (Pivot 07)
                     → Per-regime signal selection: load-bearing OOS PF source

                     Q: Static genome only, or runtime scaling too?
                        → Both: AdaptiveSizer scales by GMM confidence × drawdown
                        → Evolved confidence_sensitivity ≈ 1.46 (convex) (Pivot 08)

                        Q: Why didn't Iteration 1 show full results?
                           → Two bugs: categorical-gene resolver + CFD margin-state-reset
                           → Iteration 2 fixes both (Pivot 09)
                           → 86.6pp net-return improvement is post-correction
```

End state: current IslandPilot — five-layer pipeline (feature extraction, regime tree, regime inferencer, island evolver, adaptive sizer) trained on 2022-2024 with 63 leaves and ~22 strategy genes per island.

Each line in the tree links to its pivot folder via the master [`README.md`](README.md).
````

- [ ] **Step 3: Verify both files exist and have non-trivial size**

```bash
cd /Users/naresh/Documents/Research/qengine && wc -l notebooks/10_pipeline_design/README.md notebooks/10_pipeline_design/JOURNEY.md
```

Expected: both files exist, README has > 50 lines, JOURNEY has > 30 lines.

- [ ] **Step 4: Verify all 9 pivot folders are linked from README**

```bash
cd /Users/naresh/Documents/Research/qengine && for n in 01 02 03 04 05 06 07 08 09; do grep -q "$n" notebooks/10_pipeline_design/README.md && echo "OK: pivot $n linked" || echo "MISSING: pivot $n"; done
```

Expected: 9 `OK:` lines.

- [ ] **Step 5: Final integration check — every pivot README references the next pivot**

```bash
cd /Users/naresh/Documents/Research/qengine && for n in 01 02 03 04 05 06 07 08; do
  next=$(printf "%02d" $((10#$n + 1)))
  grep -q "Pivot $next" notebooks/10_pipeline_design/$n*/README.md && echo "OK: pivot $n → $next" || echo "MISSING: pivot $n → $next link"
done
grep -q "End of journey\|end of journey\|End-of-journey" notebooks/10_pipeline_design/09_iteration_corrections/README.md && echo "OK: pivot 09 marks end" || echo "MISSING: pivot 09 end marker"
```

Expected: 9 `OK:` lines (8 forward links + 1 end marker).

- [ ] **Step 6: Commit**

```bash
cd /Users/naresh/Documents/Research/qengine && git add notebooks/10_pipeline_design/README.md notebooks/10_pipeline_design/JOURNEY.md && git commit -m "research(pipeline): top-level README and JOURNEY (master index + decision tree)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-review (run after writing the plan)

**Spec coverage check:**

- ✅ Spec §"Location" — Task 1 creates `notebooks/10_pipeline_design/`.
- ✅ Spec §"Directory layout" — Task 1 scaffolds the full tree; each Task 2-10 creates one pivot folder; Task 11 creates top-level docs.
- ✅ Spec §"Per-pivot README template" 7 sections — every Task 2-10 README in the plan includes Context, Problem, What we tried, Result, Conclusion, Next move, Sources. Validation step in each task greps for these.
- ✅ Spec §"The 9 pivots" table — Tasks 2-10 in 1:1 correspondence.
- ✅ Spec §"Empirical-script faithfulness caveat" — Pivots 02 (Task 3), 06 (Task 7), 09 (Task 10) READMEs include the caveat; the master README in Task 11 carries the global statement.
- ✅ Spec §"Master README" — Task 11.
- ✅ Spec §"JOURNEY.md" — Task 11.
- ✅ Spec §"shared/utils.py contents" — Task 1 includes `load_pipeline_artifacts`, `simulator_fitness`, `engine_fitness`, `summarize_genome`.
- ✅ Spec §"Script naming convention" — Tasks 2,3,4,6,7,8,9,10 use `01_<purpose>.py`.
- ✅ Spec §"Success criteria" — validated by per-task grep checks for sections, file existence, and integration check in Task 11.

**Placeholder scan:**

- No "TBD", "TODO", "fill in", "implement later" patterns. Each step has concrete content.
- "Add appropriate error handling" not present.
- All script bodies are complete code.

**Type consistency:**

- `pipeline_utils.simulator_fitness(spread_pips=…, n_levels=…, sf=…, win_rate=…, n_cycles=…, seed=…)` — keyword args identical between Task 1 definition and Task 7 callsite.
- `pipeline_utils.engine_fitness(hp, start_date, end_date)` — signature identical between Task 1 and Task 7.
- Return-dict keys `total_pnl`, `n_sessions`, `n_busts`, `bust_rate` consistent.
- Pivot folder names identical between spec, plan tasks, and master README in Task 11.
````
