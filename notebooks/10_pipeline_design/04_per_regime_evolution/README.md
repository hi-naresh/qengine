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
