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
