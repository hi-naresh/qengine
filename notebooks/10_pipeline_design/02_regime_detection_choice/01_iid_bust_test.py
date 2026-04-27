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
