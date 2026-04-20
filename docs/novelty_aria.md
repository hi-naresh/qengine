# ARIA Pipeline — Novelty Review

Scope: assess whether the 6-layer ARIA architecture (MarketBrain, CycleGate,
HPEngine, RiskShield, Observer, MetaEvaluator, plus StructuralStress R(t) and
shadow tracker) is a defensible research contribution. Honest, skeptical read.

## Closest prior work

1. **Conformal Predictive Portfolio Selection (CPPS)** — Kato, arXiv:2410.16333
   (2024). Uses split conformal intervals on return forecasts to size a
   portfolio. Overlaps L4 (RiskShield) at the level of "conformal calibration
   feeding a financial decision," but operates on portfolio weights, not on a
   per-cycle abort rule for a martingale system.
   <https://arxiv.org/abs/2410.16333>

2. **Adaptive Conformal Inference for Crypto VaR** — D'Amico et al., MDPI JRFM
   17(6):248 (2024). ACI tracks VaR online across 4000 crypto assets; closest
   prior art for "online conformal as a risk-management primitive in
   non-exchangeable markets." Differs: VaR estimation, not a binary kill switch
   on a stateful cycle.
   <https://www.mdpi.com/1911-8074/17/6/248>

3. **Regime-Weighted Conformal Risk Control** — referenced in 2025 tail-risk
   literature (Researchgate 400437052). Most direct overlap with L4: combines
   regime weights with conformal calibration. Difference: portfolio VaR vs
   per-level cycle loss caps.
   <https://www.researchgate.net/publication/400437052>

4. **Nonstationary Continuum-Armed Bandit (PRBO)** — Cliff et al.,
   arXiv:2208.02901 (2022). Two-layer "bandit-over-bandit" + Bayesian
   optimization for online strategy-parameter tuning on the Bristol Stock
   Exchange simulator. Strongest overlap with L3 (HPEngine). Differs: continuum
   arms with BO, no regime context, no Thompson Beta-Bernoulli, no per-regime
   posterior decay.
   <https://arxiv.org/abs/2208.02901>

5. **Online Continuous Hyperparameter Optimization for Contextual Bandits** —
   Ding et al., arXiv:2302.09440 (2023). Frames HPO itself as a non-stationary
   contextual bandit. Conceptually identical motivation to L3, but applied to
   ML-model HPs (LinTS exploration rate), not strategy HPs gated by regime.
   <https://arxiv.org/abs/2302.09440>

6. **Strategy Selection via MAB in Financial Markets** — Researchgate
   385097222 (2024). Empirical comparison of UCB / Thompson / epsilon-greedy
   for picking among trading strategies. Same family as L3 but at the
   strategy-selection level (not hyperparameter-selection within one strategy
   conditional on regime).
   <https://www.researchgate.net/publication/385097222>

7. **Informed Contextual MAB with Neuroevolution (iCMAB)** — Desell et al.,
   GECCO Companion 2024. Contextual bandit gated by predicted future context;
   closest spirit to L2 (CycleGate) + L3 combined, but uses RNN/neuroevolution
   and is single-cycle, not session-aware.
   <https://dl.acm.org/doi/10.1145/3638530.3664145>

8. **Adaptive Regime-Aware RL for Portfolio Optimization** — arXiv:2509.14385
   (2025). HMM/probabilistic regime signals fed as state into a constrained-
   reward RL agent. Closest analogue to L1+L6 fused into one RL stack. Differs:
   monolithic policy, no explicit conformal kill switch, no per-cycle bandit
   HPO, applied to portfolio allocation not martingale cycles.
   <https://arxiv.org/html/2509.14385v1>

9. **Adaptive Regime-Aware Stock Prediction with Autoencoder-Gated Dual
   Transformers + SAC** — arXiv:2603.19136 (2026). Three-component stack
   (autoencoder anomaly gate -> regime-specialized transformers -> SAC tuning
   the gate threshold). Architecturally the closest "multi-layer adaptive"
   competitor; overlaps L1 + L4 + L6. Differs: forecasting target, no bandits,
   no conformal calibration, no martingale-cycle semantics.
   <https://arxiv.org/abs/2603.19136>

10. **FinCon: LLM Multi-Agent System with Conceptual Verbal Reinforcement** —
    Yu et al., NeurIPS 2024. Manager/analyst LLM hierarchy with episodic
    self-critique and a CVaR-based risk-control component triggering belief
    updates. Strongest analogue to L6 (MetaEvaluator + degradation detector)
    but realized as LLM verbal reflection, not as Beta-posterior decay.
    <https://arxiv.org/abs/2407.06567>

11. **An Automated FX Trading System Using Adaptive RL** — Dempster &
    Leemans, ESWA (2006). Classical multi-layer FX agent: ML signal +
    risk/utility layer + dynamic optimization. The grandfather of
    "multi-layer adaptive trading agents." ARIA's layering pattern is a
    descendant.
    <https://dl.acm.org/doi/10.1016/j.eswa.2005.10.012>

12. **"Shadow Signals" counterfactual learning for trading** — Nyabuto, dev.to
    blog (2025). Practitioner write-up; describes the exact pattern ARIA's
    shadow tracker implements (persist blocked decisions, score them at fixed
    horizons, train on restraint). Not peer-reviewed. No academic equivalent
    found in the algorithmic-trading literature.

## Verdict per layer

| Layer | Verdict | Rationale |
| --- | --- | --- |
| L1 MarketBrain (online k-means/GMM) | **Prior art exists** | Streaming GMM/online k-means for regime detection is a well-trod pattern (Two Sigma, Macrosynergy, McGreevy thesis). On-the-fly k discovery is a modest engineering twist, not a research contribution. |
| L2 CycleGate (per-cycle online logistic gate) | **Partial / under-explored** | Online SGD logistic regression is textbook; using it as a per-cycle entry gate trained on `(was_profitable)` of a prior martingale cycle, with regime-ID as a feature, has no direct precedent I can find. The packaging — not the algorithm — is the novelty. |
| L3 HPEngine (Thompson Beta-Bernoulli per regime per HP-group) | **Partial** | Bandits for trading-strategy/parameter selection exist (PRBO, Cliff 2022; iCMAB 2024; MAB strategy-selection 2024). The specific instantiation — discrete Beta-Bernoulli arms keyed by `(regime_id, hp_group)` and pulled at cycle boundaries — has not been published in the form described. PRBO is the obvious dominator; the paper must distinguish on (a) regime-keyed posteriors and (b) cycle-event triggering. |
| L4 RiskShield (split-conformal cycle abort + analytical ruin probability) | **Novel-ish** | Conformal prediction in finance is overwhelmingly applied to portfolio VaR / return intervals (CPPS, ACI-VaR, RWC). Using split-conformal residuals on a *per-level loss* signal as an in-cycle abort rule for a stateful martingale is, as far as the search shows, unpublished. Combining it with Wilson-2010 analytical ruin probability is also unusual. This is the strongest single-layer claim. |
| L5 Observer (enriched session recording) | **Not a research contribution** | Engineering / instrumentation. |
| L6 MetaEvaluator (composite ARIA score + Beta-posterior halving on degradation) | **Partial** | CVaR-driven self-critique with belief updates exists in FinCon (2024); composite scoring with bust-penalty + survival-efficiency is a domain-specific recombination. The "halve all Beta posteriors on degradation" trick is a clean, simple non-stationarity response that I could not find in the bandit-trading literature; worth flagging as a small contribution. |
| StructuralStress R(t) accumulator | **Cite as "Chen 2026 style"** | If Chen 2026 is real, it is prior art. ARIA's use is application, not invention. |
| Shadow tracker | **Practitioner pattern, no academic prior art found** | Defensible to claim formal evaluation methodology if you treat shadow rewards as an off-policy estimator and report e.g. doubly-robust scores; otherwise this is described in blog posts but not formalized. |

## Verdict for the combination

**The 6-layer composition is the strongest contribution.** No single paper
combines: streaming regime clustering as a context label, regime-conditioned
Thompson HPO at cycle boundaries, an in-cycle conformal kill switch on
projected per-level loss, and a meta-layer that adaptively boosts bandit
exploration via posterior decay — all wrapped around a stateful
martingale/hedge cycle strategy rather than a single-shot allocation. The
closest competitor architecturally is the autoencoder-gated dual-transformer +
SAC stack (arXiv:2603.19136) and FinCon (NeurIPS 2024), but neither targets
cycle-stateful strategies and neither uses conformal calibration as a kill
switch.

That said, the *components* are nearly all incremental. The contribution is
**system-level**: the way these primitives are wired around martingale cycle
semantics, with explicit empirical evidence that the wrapper turns a
breakeven-to-losing strategy into a survivable one (your real-engine
finding: 87% DD reduction, 85% loss reduction OOS).

## Defensible positioning

> "We present ARIA, a regime-conditioned, conformal-gated, Thompson-tuned
> meta-controller for cycle-based trading strategies. The contribution is
> not any single component — each has antecedents — but the integration of
> split-conformal per-cycle abort with regime-keyed Thompson hyperparameter
> selection and a degradation-aware meta-evaluator, applied to stateful
> martingale/hedge cycles where standard ML wrappers (single-step return
> forecasting, portfolio VaR conformal bounds) do not apply. We show on
> OANDA EUR-USD that the wrapper converts a structurally breakeven strategy
> into a survivable one, with ablations isolating each layer's contribution."

The claim survives because (a) stateful martingale cycles are under-served
by the existing adaptive-trading literature, which targets directional /
portfolio agents, and (b) conformal-as-kill-switch is novel within that class.

## Risk areas

- **PRBO (Cliff 2022, arXiv:2208.02901)** is the most dangerous nearby paper.
  It already does online HP tuning for trading strategies with a hierarchical
  bandit. Differentiation must be sharp: regime-keyed Beta-Bernoulli over
  discrete HP groups, cycle-event triggering, integration with a kill switch.
- **Adaptive Regime-Aware Stock Prediction (arXiv:2603.19136)** is the
  closest "multi-layer adaptive" architecture. Its existence weakens any
  generic "first multi-layer regime-aware adaptive system" claim — do not
  make that claim.
- **FinCon (NeurIPS 2024)** dominates any claim about composite-score-driven
  meta-evaluation with belief updates. L6 must be positioned as a lightweight
  non-LLM analogue, not as a new idea.
- **Regime-Weighted Conformal Risk Control (2025)** is the riskiest L4
  competitor. If the paper formalizes regime-conditioned conformal calibration
  generally, ARIA's L4 reduces to "we apply RWC to per-level cycle loss." Read
  this paper end-to-end before submitting.
- **Shadow tracker** has no academic prior art but also no academic
  formalization. To claim it as a contribution, frame it as off-policy
  evaluation with a defined estimator; otherwise demote it to engineering.

## Honest assessment

L1, L5, and parts of L6 are engineering. L2 and L3 are incremental. L4 is the
strongest single-layer claim. The combination applied to cycle-based
strategies is publishable as a system paper at ACM ICAIF or a finance-ML
workshop if the ablations isolate which layers move the needle (your
44_ablation_study.py) and the paper does not over-claim component novelty. A
top-tier ML venue would likely reject on theoretical grounds; a finance-ML
venue should accept on empirical and engineering grounds.
