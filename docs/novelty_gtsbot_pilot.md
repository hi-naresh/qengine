# Novelty Review: GTSBotPilot

**Date**: 2026-04-16
**Subject**: Is the GTSBotPilot pipeline (3-layer pipeline based on Rundo et al. 2019 GTSbot) novel enough to publish?
**Verdict (TL;DR)**: GTSBotPilot is **mostly a faithful re-implementation of Rundo 2019** with two minor simplifications/extensions (derivative trend filter; trend-abort at L3+). The architecture itself is not novel. There is a narrow publishable angle, but only as a baseline/comparison artifact or as part of a larger contribution — not as a standalone "novel pipeline" paper.

---

## 1. Citation count of Rundo 2019

- **Semantic Scholar / typeset.io**: ~31 citations
- **Citing-paper landscape** (sampled via Semantic Scholar API, DOI:10.3390/app9091796):
  - Most citations are from the broader ML-for-finance survey literature, not from papers that *extend* GTSbot architecturally.
  - Direct extensions / engagements with the GTSbot pipeline itself are rare — the most concrete is **Yeh, Hsieh & Huang (2022)**, "ANN and SSO Algorithms for a Newly Developed Flexible Grid Trading Model" (Electronics 11(19), 3259; arXiv:2211.12839), which explicitly benchmarks **GTSbot as one of nine baseline grid methods** vs. their FNN/LSTM-trained "Flexible Grid".
  - **Rundo himself (2019, App. Sci. 9(20), 4460)** "Deep LSTM with Reinforcement Learning Layer..." follows up on the SCG block from GTSbot (replacing the SCG NN with LSTM+RL — exactly the "future work" item from the original).
  - **Rundo et al. (2025, IEEE Access)** "Attractor-Aware Hyperbolic Lipschitz-Constrained-Reinforcement Learning for FX Market" continues the same author's program.
  - **Chen, Chen & Jang (2025)** "Dynamic Grid Trading Strategy: From Zero Expectation to Market Outperformance" cites GTSbot but targets crypto, with a different (dynamic re-pegging) contribution.
  - Other citations (Stasiak 2025, Cohen 2022, Gad 2024, Vetrin 2024, Tungdajahirun 2023, Mehrban 2023, Mroua 2023) cite GTSbot as background, not as a starting architecture.

So: ~31 citations, but **only 1–2 papers actually extend or modify the GTSbot architecture itself** (Yeh 2022 as a benchmark; Rundo 2019b as an internal block swap). The architectural design space around GTSbot is therefore *not* saturated, but it is also not a hot research area.

## 2. Verdict on novelty

GTSBotPilot has three layers, mapping 1-to-1 to Rundo 2019's pipeline:

| GTSBotPilot layer | Rundo 2019 equivalent | Modification? |
|---|---|---|
| TrendFilter (1st/2nd derivative of EMA price) | TCB (Trend Classifier Block) fed by SCG-NN regression of close | **Simplification** — drops the SCG-NN, replaces with a derivative-of-EMA classifier |
| GridManager (x/y thresholds, max ops) | GSM (Grid System Manager) with x-threshold (time) and y-threshold (price ATR) | **Re-implementation, identical semantics** |
| BasketManager (close-all profit target, drawdown emergency close) | BESM (Basket Equity System Manager) | **Re-implementation, identical semantics** |
| Trend-abort at L3+ when trend reverses | Not in Rundo 2019 | **Genuinely new** (small) |

Honest assessment of each "modification":

1. **Derivative trend filter replacing SCG NN**: This is a *downgrade* in ML sophistication, not a novel contribution. Slope/derivative-of-MA is standard textbook trend classification (e.g., MACD = first-derivative proxy; many TradingView/QuantifiedStrategies pieces describe it). It cannot be claimed as novel — at best, "ablation: simpler trend classifier suffices".
2. **Trend-abort at L3+ for martingale grids**: Conceptually present in practitioner EAs ("regime filter disables countertrend grids") but I found **no peer-reviewed paper explicitly modeling level-conditional trend-abort for grid martingales**. This is the most defensible novel sliver, but it is a small algorithmic tweak, not a contribution that would carry a paper.
3. **The 3-layer pipeline itself**: Identical to Rundo 2019's diagram. Cannot be claimed.

**Bottom line**: GTSBotPilot is ~85% re-implementation. It is not a novel pipeline.

## 3. Positioning angle (1 paragraph)

GTSBotPilot is **not viable as a standalone "novel architecture" paper** — Rundo 2019 owns that contribution and Yeh 2022 already established the benchmarking convention. However, it is **highly viable in three other roles**: (a) as a **reproducible open-source baseline** for the IslandPilot paper (which is the user's actual contribution) — "we re-implement Rundo 2019 with modern open tooling and use it as the structural backbone over which IslandPilot evolves regime-aware parameters"; (b) as one arm of an **ablation/comparison study** demonstrating that the SCG-NN trend block can be replaced with a trivial derivative classifier without measurable loss (a small but publishable empirical note); (c) as the **substrate for a real-execution study** showing that Rundo's reported performance does not survive realistic OANDA spreads (which aligns with the user's existing finding in `real_engine_evolution.md` that "spread eats all edge"). Path (a) is the strongest — package GTSBotPilot as the *baseline structural pipeline* in the IslandPilot paper and frame the contribution as the evolutionary/regime layer on top, not the pipeline itself.

## 4. Risk areas (papers that already did the same modifications)

- **Yeh, Hsieh & Huang (2022)**, "ANN and SSO Algorithms for a Newly Developed Flexible Grid Trading Model", *Electronics* 11(19), 3259 — already benchmarks GTSbot as one of 9 grid methods using ROI/MDD/volatility/Sharpe. **Any "GTSbot improvement" paper must beat this on benchmarking rigor**, and they already use FNN+LSTM-trained adaptive grids, which is more sophisticated than the derivative trend filter.
- **Rundo (2019b)**, "Deep LSTM with Reinforcement Learning Layer..." App. Sci. 9(20), 4460 — already replaced the SCG block with LSTM+RL (the *opposite direction* from the derivative-EMA simplification). Reviewers will ask "why did you go simpler when the original author already went deeper?"
- **Rundo et al. (2025)**, "Attractor-Aware Hyperbolic Lipschitz-Constrained-Reinforcement Learning for FX Market", *IEEE Access* — same authors continuing the program; signals the original team is still active in this space.
- **Chen, Chen & Jang (2025)**, "Dynamic Grid Trading Strategy: From Zero Expectation to Market Outperformance", arXiv:2506.11921 — claims dynamic grid re-pegging beats static grids on BTC/ETH; partial overlap with the GridManager layer's role.
- **Pareschi & Zappone (2021)**, arXiv:2108.12333 "Integrating Heuristics and Learning in a Computational Architecture for Cognitive Trading" — overlapping high-level vision (heuristic layers + learning), though not grid-specific.
- **Practitioner literature** (FXPro, Orchard Forex, ForexOp, Admiral Markets, etc.) describes basket-equity profit targets, equity-stop drawdown closes, and trend-filter abort exactly as implemented in GTSBotPilot. None are peer-reviewed, but reviewers may flag these as prior art for the BasketManager and trend-abort components.
- **Specific risk**: If a reviewer types "trend filter martingale grid abort" into Google Scholar they will hit Yeh 2022 within two clicks and immediately ask how GTSBotPilot differs. The honest answer ("it doesn't, structurally") is fatal for a standalone paper but fine for a baseline-in-larger-paper framing.

## 5. Recommendation

- **Do not** publish GTSBotPilot as a standalone "novel pipeline" paper. The architecture is Rundo's, the trend filter is a simplification not an improvement, and Yeh 2022 already occupies the "improved grid" benchmark slot.
- **Do** include it in the IslandPilot paper as the *baseline structural pipeline* — the contribution is the regime-aware evolutionary layer above it, not the pipeline itself.
- The **only sliver of independent novelty** is level-conditional trend-abort for martingale grids (L3+), which is at best a 1–2 page algorithmic note inside a larger paper, not a paper of its own.
- Cite Rundo 2019 prominently and openly — the project is explicitly derivative, and trying to claim otherwise will be caught in review.
