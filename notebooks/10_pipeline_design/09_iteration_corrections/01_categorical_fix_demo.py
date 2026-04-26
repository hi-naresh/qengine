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
