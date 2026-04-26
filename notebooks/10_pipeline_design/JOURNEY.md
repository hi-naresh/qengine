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
