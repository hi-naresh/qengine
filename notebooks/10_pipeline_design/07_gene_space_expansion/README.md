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
