# Novelty Review — Cross-Pipeline Summary

Synthesis of four parallel literature reviews (arXiv + Google Scholar + Semantic Scholar). Full per-pipeline reports linked below.

| Pipeline       | Verdict                       | Closest prior art                                  | Publishable? |
|----------------|-------------------------------|----------------------------------------------------|--------------|
| **IslandPilot**| Partial — combination novel   | CGA-Agent 2025, QuantEvolve 2025, Dynamic Island Spectral 2018 | **Yes, as systems contribution** |
| **ARIA**       | Partial — wiring novel        | PRBO 2022 (Cliff), FinCon NeurIPS 2024, Regime-Weighted Conformal 2025 | **Yes, as system paper** |
| **GridPilot**  | Partial — Q-abort framing novel | Theate & Ernst TDQN 2020, MQL5 #8826 (non-academic) | **Yes, with negative-HMM result as headline** |
| **GTSBotPilot**| **Not novel**                 | Rundo 2019 (the basis); Yeh et al. 2022 already benchmarked | **No — use as baseline only** |

Per-pipeline reports:
- `docs/novelty_island_pilot.md`
- `docs/novelty_aria.md`
- `docs/novelty_grid_pilot.md`
- `docs/novelty_gtsbot_pilot.md`

## Cross-cutting findings

### What is genuinely missing in the academic literature
- **Martingale + ML/RL.** The academic evolutionary-trading and RL-trading lines almost entirely ignore martingale/grid cycle strategies — they target directional returns or portfolio allocation. This is the *empirical gap* every one of these pipelines exploits.
- **Stateful cycle-level meta-controllers.** Existing RL-trading work treats each bar as an independent decision. None of the surveyed work exposes cycle state (level, duration, danger-at-entry vs danger-now) as the agent's observation space the way GridPilot's Q-abort does.
- **Per-regime evolved execution genomes** (vs evolved entry signals or evolved portfolio weights). Single-population GA + regime-conditioned fitness exists; isolated populations per regime with macro-sibling migration does not.

### What is *not* novel — drop these claims if they ever appear
- Island-model GA, hierarchical GMM regime detection, online k-means, Welford normalization, percentile gates, choppiness/Hurst/ADX features, EMA-derivative trend classification, contextual bandits over hyperparameters, conformal prediction for finance, basket equity profit targets. All textbook or well-cited.
- "Regime-aware" anything as a standalone claim.

## Recommended paper strategy

The supervisor's filter ("only publish with good claims") cuts out three of four pipelines as standalone papers. The defensible plays:

### Option A — single paper, IslandPilot-led (recommended)
**Title direction:** "Regime-Specialized Evolutionary Execution for Grid/Martingale Strategies on FX"

- **Core contribution:** Hierarchical GMM regime tree → island-model GA topology with macro-sibling migration → per-regime execution genome applied to martingale cycle control.
- **Empirical headline:** 40% drawdown reduction on baseline-losing strategy without changing entry logic (already in `pipeline_comparison.md`).
- **Use GTSBotPilot as a baseline** in the comparison section — its 82.7% win rate gives reviewers a strong benchmark to beat (or to lose to honestly, with explanation).
- **Use ARIA and GridPilot as ablation siblings** — "we also tried conformal kill switches and Q-learning aborts; here's why island-GA dominated in our setting."
- **Required citations:** CGA-Agent (arXiv 2510.07943), QuantEvolve (arXiv 2510.18569), Dynamic Island Spectral (arXiv 1801.01620), Rundo 2019 (Appl. Sci. 9:1796), Yeh et al. 2022 (Electronics 11:3259).

### Option B — system paper covering ARIA
**Title direction:** "ARIA: A Six-Layer Adaptive Architecture for Stateful Cycle-Trading Strategies"

- **Frame as systems integration.** Don't claim component novelty.
- **Core contribution:** the integration of conformal-kill-switch + Thompson-sampled HP arms + degradation-aware exploration boost over a martingale strategy class the adaptive-trading literature ignores.
- **Risk:** sample size (15 cycles in current test). Must extend to 12+ months and let conformal calibrate.
- **Venue:** ACM ICAIF or finance-ML workshop, not NeurIPS/ICML.

### Option C — negative-result paper, GridPilot-led
**Title direction:** "Bust Events Are IID: Why HMM Regime Filters Fail for Grid/Martingale Strategies"

- **Core contribution:** the Phase-2 negative result already in memory — HMM regime gate failed (p=0.405) on 60k cycles, contradicting practitioner folk wisdom.
- **Q-abort overlay** as the constructive part: a tabular meta-controller works where the regime gate doesn't.
- **Strength:** negative results with clean p-values are publishable.
- **Risk:** the constructive Q-abort component (1625 states, frozen, eval-mode) is small; reviewers may want a stronger positive contribution.

## Final recommendation

**Go with Option A (IslandPilot-led).** It has:
1. The clearest single novelty claim (regime-specialized island GA + macro-sibling migration on martingale execution).
2. A defensible empirical headline (40% DD reduction).
3. A slot for the other three pipelines as honest comparisons.
4. The supervisor-friendly framing — one bold systems claim, not a vague "we built a pipeline".

GTSBotPilot is **not publishable as a standalone**. ARIA needs more data before it's defensible. GridPilot's negative HMM result is great but small.
