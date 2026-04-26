### MI fallback ablation (regime-tree topology)

The production regime tree was built on the fallback feature set (all
30 features) because the mutual-information selection identified only
3 features (`natr_14_tf12`, `natr_14_tf48`, `natr_50`) as informative
against the cycle-outcome proxy label (cloud training log,
2026-04-23). The fallback rule (`train.py` lines 1164-1169) triggers
whenever fewer than 5 features survive MI selection, on the grounds
that a 3-dim partition produces regimes that switch too rapidly for
the per-leaf island evolution to gather contiguous evaluation windows.

To test whether the fallback materially changed the discovered regime
structure, we re-fit the regime tree on the same training window
(EUR-USD 1m -> 5m, 2022-01-01 -> 2024-12-31,
220,608 clean rows) using only the 3
MI-selected features (Tree A) and compared the resulting topology to a
tree fit on all 30 features (Tree B, the production fallback). All
other regime-tree hyper-parameters (`max_macro=10`,
`max_sub=8`,
`min_leaf_samples=200`,
autocorrelation `lag=10`,
`persistence_threshold=0.7`)
are identical to the production run.

| Metric                              | MI-only (3 feats) | Fallback (30 feats) |
|-------------------------------------|-------------------|---------------------|
| Macro clusters (BIC-selected)       |                 7 |                  10 |
| Total leaves (after sparse merge)   |                47 |                  63 |
| Mean leaf size (samples)            |           4,693.8 |             3,501.7 |
| Std of leaf size (samples)          |           3,677.3 |             2,377.7 |
| Min / max leaf size                 | 596 / 20,061 | 252 / 9,982 |
| Regime separation CV                |             0.783 |               0.679 |
| Adjusted Rand Index (A vs B)        | — | 0.034 |
| Normalised Mutual Info (A vs B)     | — | 0.168 |

ARI = 0.034 is low: the two trees produce structurally different partitions of the same data. The fallback to all 30 features materially changed the discovered regime topology. The production tree absorbs the additional 27 features as informative regime discriminators (most notably trend, time-of-day, distributional skew/kurtosis and serial dependence — dimensions that the 3 NATR-family MI features cannot represent at all), so a large structural divergence is expected by construction, not a sign of instability: the fallback tree partitions a strictly richer feature space. We flag this as a genuine sensitivity of the production pipeline: the choice to fall back changes which regimes the GA evolves against. The performance consequence is not quantified here; a full performance ablation (re-running the per-leaf GA on Tree A) is left to future work. We note that the regime separation CV is comparable for both trees (0.783 vs 0.679 — both well above the 0.15 structural-validity threshold), so neither tree is degenerate.

The shipped production tree (`pipelines/_shared/IslandPilot/models/regime_tree.pkl`)
has 10 macro clusters and
63 leaves; our locally-rebuilt
Tree B has 10 macro / 63 leaves and
agrees with the shipped tree at ARI = 1.0, confirming
the local rebuild faithfully reproduces the production topology. The
ablation above is therefore a like-for-like structural comparison
between the choice that was made (Tree B, 30 features) and the
counterfactual (Tree A, 3 MI features).

This ablation is **structural only**. A full performance ablation —
running the per-leaf GA evolution on Tree A and comparing PnL,
drawdown and bust rate against the production results — would cost
roughly 10 hours of compute and is deferred to future work. The ARI
and NMI metrics above quantify the *partition distance* between the
two trees: ARI = 1 implies identical leaf assignments (and therefore,
under identical GA seeds, identical strategies), while ARI = 0 implies
the partitions are unrelated. The reported ARI = 0.034 sits near
the lower bound and shows that the two regime decompositions are
materially different objects; whether the corresponding evolved
strategies differ in PnL by a large or small amount is a separate
empirical question that this ablation does not resolve.
