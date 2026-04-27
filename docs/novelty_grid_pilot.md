# GridPilot Novelty Review

Scope: assess prior art for the three-layer GridPilot pipeline (DangerScorer + percentile EntryGate + tabular Q-abort) applied to grid/martingale forex strategies. Searches: arXiv, Semantic Scholar, Google Scholar, ResearchGate, ACM DL, MDPI, ScienceDirect (via WebSearch + WebFetch, April 2026).

---

## 1. Closest Prior Work

### Grid / martingale strategies + ML

1. **Aloud, "Grid Trading System Robot (GTSbot): A Novel Mathematical Algorithm for Trading FX Market"** (J. Eng. Sci. & Tech., 2018). Pure mathematical/heuristic GTS for FX; no RL, no danger gate. Overlap: defines the strategy family GridPilot protects. Difference: no learning component, no abort, no entry filter.
   https://www.researchgate.net/publication/332728626

2. **MQL5 community article — "Machine learning in Grid and Martingale trading systems. Would you bet on it?"** (MQL5 Articles #8826, 2020). Trains boosted/NN classifiers to filter grid/martingale entries. Overlap: ML entry filter for martingale-class strategies. Difference: supervised classification, not RL; no abort policy; not peer-reviewed; no danger-score formalism.
   https://www.mql5.com/en/articles/8826

3. **Liu (Medium, 2024) — "Optimizing Grid Trading Parameters with Technical Indicators and AI."** LSTM/transformer maps indicator state to grid configuration parameters. Overlap: ML over grid trading. Difference: parameter generator, not protective overlay; supervised; no Q-learning, no abort, no danger index, no martingale risk control.

### Q-learning / RL for trading exits & position management

4. **Theate & Ernst, "An Application of Deep Reinforcement Learning to Algorithmic Trading" (TDQN)** (arXiv:2004.06627, 2020; Expert Systems with Applications 2021). Deep DQN policy on equities, action space {long, short, flat}. Overlap: Q-learning over financial state. Difference: monolithic agent that picks the *trade*, not a meta-controller that aborts a martingale cycle; no martingale, no grid, deep network, no danger index.

5. **Shi et al., "Quantitative Trading using Deep Q Learning"** (arXiv:2304.06037, 2023). DQN for entry/exit on equities. Same delta as #4.

6. **"Deep Reinforcement Learning for Trading"** (Zhang, Zohren, Roberts, arXiv:1911.10107, 2019). DQN/PG/A2C on futures with volatility-scaled rewards. Overlap: RL exit decisions in markets. Difference: futures contracts, no martingale, deep nets, no separate gating layer.

7. **Almahdi & Yang, "An adaptive portfolio trading system: A risk-return portfolio optimization using recurrent reinforcement learning with expected maximum drawdown"** (Expert Systems with Applications, 2017/2019). RRL with drawdown in objective. Overlap: RL with drawdown control. Difference: portfolio level, recurrent policy gradient, no abort, no martingale, no tabular Q.

8. **"Embedded draw-down constraint reward function for deep reinforcement learning"** (Applied Soft Computing, 2022, ScienceDirect S1568494622004082). DRL where drawdown is folded into reward. Same delta as #7; reward shaping rather than hard-stop policy.

9. **Vadori, Ganesh, Reddy, Veloso, "Risk-Sensitive Reinforcement Learning: a Martingale Approach to Reward Uncertainty"** (ACM ICAIF 2020 / arXiv:2006.12686). Uses Doob martingale decomposition of cumulative reward to define a risk measure; tested on grid-world and portfolios. Overlap: keyword "martingale" + RL. Difference: martingale here is a probability-theory construct, not the betting strategy; nothing to do with grid trading or doubling-down forex bots.

### Regime / risk-state gates for trading

10. **Hassan & Nath, "Stock market forecasting using HMM"** and the QuantStart HMM regime-filter pattern (widely reproduced in QuantInsti, LSEG Devportal). Overlap: state-driven entry gate using probabilistic regime model. Difference: HMM (latent state), not a deterministic z-score composite; not tied to martingale; reports show regime gating reduces drawdown — exactly the hypothesis GridPilot empirically *rejected* on its data (HMM gate p=0.405).

11. **Dixon & Akcora, multi-feature regime detection with Random Forests** (QuantInsti tutorials and follow-on work). ML classifier that outputs regime label as filter. Difference: classification, not a continuous danger score; no online Welford normalization; no martingale.

### Hierarchical / meta-controller RL for trading

12. **Qin et al., "EarnHFT: Efficient Hierarchical Reinforcement Learning for High Frequency Trading"** (AAAI 2024, arXiv:2309.12891). Router selects per-regime sub-agent. Overlap: meta-controller layered above an inner trading policy. Difference: HFT, deep nets, sub-agents are policies (not abort/continue); not protective of a fixed strategy.

13. **"Commission Fee is not Enough: A Hierarchical Reinforced Framework for Portfolio Management"** (AAAI 2021). Two-level RL. Same delta as #12.

### Indicator stack (DangerScorer feature set)

14. Choppiness Index (Dreiss, 1991), ADX (Wilder, 1978), Hurst exponent (Hurst, 1951; Peters 1991), ATR (Wilder, 1978). Combining choppiness + ADX + Hurst as a multi-timeframe trend/no-trend filter is *standard practice* on TradingView/LuxAlgo and in trader literature (e.g. weighted confluence scores, Stonehill Forex 2023). No academic paper specifically formalises the exact DangerScorer composite, but the building blocks and the "weighted confluence" idiom are well known.

---

## 2. Verdict per Component

| Component | Verdict | Reasoning |
|---|---|---|
| **DangerScorer** (z-scored multi-TF chop/ADX/Hurst/ATR with online Welford) | **Partial novelty** | Each feature is textbook; weighted composites of trend/chop indicators exist in trader literature. The specific online z-scored composite for *martingale* risk gating is, to our knowledge, not in the academic record, but it would be a stretch to call the indicator stack itself novel. |
| **Percentile EntryGate** (block top-N% danger) | **Prior art exists** | Regime/volatility filters that block trades above a percentile or HMM threshold are routine (HMM filter, ADX>20, Choppiness<60). The contribution is at best the calibration on danger output. |
| **Tabular Q-abort** (1625-state frozen policy controlling cycle abort for a martingale) | **Novel in the specific framing** | Tabular Q-learning for *exit* decisions exists (cs229.stanford 2009, several Medium tutorials, github WenchenLi/q-learning-trader). What is new here: (a) the agent does not pick the trade — it sits on top of a deterministic martingale cycle and emits {continue, abort}; (b) state explicitly conditions on hedge level, cycle duration, and danger-at-entry vs danger-now; (c) tabular and frozen, deliberately tiny model trained on 60k cycles. No paper found does this combination. |
| **Combination: DangerScorer + percentile gate + tabular Q-abort wrapped around a martingale grid bot in forex** | **Novel** | None of the surveyed work composes a multi-timeframe danger composite, a percentile entry filter, and a tabular Q-abort meta-controller specifically as a *protective overlay* on a martingale/grid strategy. Closest analogues (HMM regime filter for trend strategies, deep RL meta-controllers for HFT, drawdown-aware reward shaping) each cover one face only. |

---

## 3. Defensible Positioning

GridPilot can defensibly be framed as: **"A protective meta-overlay for fixed-rule martingale forex strategies, decoupling risk control from the trading policy. We show that, on 20 years of EUR-USD, a tabular Q-abort agent (449 visited states) trained on cycle-level features and conditioned on a real-time multi-timeframe danger composite reduces bust rate by 32% with only a 0.16% abort rate, while an HMM regime gate on the same data fails (p=0.405) — a direct empirical refutation of the dominant 'regime-filter for grid bots' folk wisdom."**

The novelty hooks worth emphasising:
- **Decoupled architecture**: the trading rule stays interpretable and unchanged; the RL component only emits abort.
- **Tabular, frozen, 1625-state policy**: a deliberately small RL model that is auditable, deterministic at inference, and trainable on a single CPU. This is unfashionable but defensible against deep-RL baselines.
- **Negative HMM result**: probably the most defensible single contribution because it contradicts widely-reproduced regime-gating advice. Few papers publish a clean "regime gate doesn't work for grid bots, busts are IID" finding with this much data.
- **Cycle-level RL, not bar-level**: the abort agent acts at the granularity of a martingale cycle (per hedge level), which is structurally different from the bar-level RL agents that dominate the literature.

---

## 4. Risk Areas (papers that could undercut the claim)

- **TDQN (Theate & Ernst 2020)** and the "Deep RL for Trading" line will be cited by reviewers as "RL already does exit decisions". Pre-empt by stating that GridPilot is a *meta-controller* over a fixed strategy, not a competing end-to-end policy, and that the comparison metric is bust-rate reduction at fixed strategy P&L — not Sharpe of a free agent.
- **Drawdown-aware RL papers (Almahdi & Yang; Embedded Drawdown Constraint, ASOC 2022)** could be argued to "already do drawdown control via reward shaping". Difference: reward shaping changes the policy continuously; GridPilot's abort is a discrete kill-switch on top of an unchanged base policy and is interpretable.
- **MQL5 article #8826** is the closest in spirit (ML filter for grid/martingale) and a reviewer who finds it will note prior art on the *concept*. However it is not peer-reviewed, uses supervised filters not RL, and lacks the danger-score and abort components. Cite it explicitly to neutralise.
- **HMM regime-filter literature** is large; reviewers may say "a known technique would have worked". The negative-result section mitigates this if presented with full statistics on the tested data window (60k cycles, 103 busts, p=0.405).
- No paper found *dominates* GridPilot in the precise framing (protective overlay for martingale forex with tabular Q-abort + danger composite). The risk is positioning, not preemption.

---

## 5. Suggested citations to include in the paper

Theate & Ernst 2020 (TDQN); Zhang, Zohren & Roberts 2019; Vadori et al. 2020; Almahdi & Yang 2017; Embedded Drawdown Constraint (ASOC 2022); Aloud GTSbot 2018; Qin et al. EarnHFT (AAAI 2024); HMM regime-filter line (Hassan & Nath; QuantStart pattern); MQL5 article #8826 (only non-academic, but the closest match — cite to demonstrate awareness).

---

Word count: ~1,050.
