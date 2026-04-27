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
