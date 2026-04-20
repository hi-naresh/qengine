# IslandPilot — Novelty / Prior-Art Review

Date: 2026-04-16
Reviewer: literature scan via arXiv, Google Scholar, Semantic Scholar.

## What is being claimed

IslandPilot is a pipeline that wraps Martingale/grid forex strategies with:

1. Hierarchical GMM regime discovery with BIC at two levels (macro, then sub-regimes), yielding 15-80 leaf "islands".
2. An island-model GA — one population per leaf regime, tournament + uniform crossover + Gaussian mutation, with sibling migration limited to islands sharing the same macro cluster.
3. A per-regime execution genome (sizing curve, sizing factor, max_levels, hedge ATR mult, TP, abort aggressiveness, base size, hysteresis margin).
4. Hysteresis-based runtime regime inference (soft GMM posteriors + sticky hard switching with margin threshold).
5. Adaptive sizing = confidence x drawdown x base.
6. Applied specifically to Martingale / hedged-grid cycles, not generic trend-following.

## Closest prior art

### A. Island-model GA (general)

- **Whitley, Rana & Heckendorn (1999), "The Island Model Genetic Algorithm: On Separability, Population Size and Convergence"**, Journal of Computing & Information Technology — foundational. Establishes that island GA preserves diversity and beats panmictic GA on multimodal landscapes. No finance / no regime. https://www.researchgate.net/publication/2244494
- **Lardeux & Goeffon (2010), "A Dynamic Island-Based Genetic Algorithms Framework"** — dynamic migration topology, generic. https://link.springer.com/chapter/10.1007/978-3-642-17298-4_16
- **Meignan et al. (2018), "Dynamic Island Model based on Spectral Clustering"**, arXiv:1801.01620 — uses spectral clustering on the *genome space* to redefine islands during the run. This is the closest methodological relative: clustering-driven island assignment. Crucially, the clustering is on *individuals*, not on the *environment*. https://arxiv.org/pdf/1801.01620

Overlap with IslandPilot: the island-GA mechanic itself, including diversity-preservation argument.
Difference: IslandPilot's island assignment is driven by **exogenous market regime** (GMM on returns), not by genome similarity. Migration is restricted to *macro-siblings*, which is a hierarchy-aware twist not present in the dynamic-island work.

### B. GA in Forex / trading rule optimization

- **Hirabayashi, Aranha & Iba (2009), "Optimization of the trading rule in foreign exchange using genetic algorithm"**, GECCO — single-population GA for FX rule discovery. https://dl.acm.org/doi/10.1145/1569901.1570106
- **Hryshko & Downs (2004 / 2012), "A Forex trading system based on a genetic algorithm"**, Journal of Heuristics — single-population GA, technical-rule chromosome. https://link.springer.com/article/10.1007/s10732-012-9201-y
- **Myszkowski & Bicz (2010), "Evolutionary algorithm in Forex trade strategy generation"**, IMCSIT. Decision-tree chromosome, no regime, no island. https://www.semanticscholar.org/paper/52a2e27a59a7c989033dc422f914393eef9e9a01
- **Chou et al. (2014), "A Rule-Based Dynamic Decision-Making Stock Trading System Based on Quantum-Inspired Tabu Search Algorithm"**, IEEE TSMC — sliding-window re-optimization of rule combinations. Not island, not GMM. (PDF previously in `papers/drafts/`.)

Overlap: GA for trading-rule optimization is well-trodden, single-population.
Difference: none of these evolve *per-regime* genomes. They evolve one rule and rely on sliding window for adaptation.

### C. Regime-aware GA / RL for trading

- **Wu, Chen et al. (2025), "Agent-Based Genetic Algorithm for Crypto Trading Strategy Optimization"**, arXiv:2510.07943 — CGA-Agent: GA + multi-agent coordination, claims "regime-aware adaptation". Single-population GA with regime-conditioned fitness; does **not** maintain per-regime populations and does not use GMM. https://arxiv.org/abs/2510.07943
- **QuantEvolve (2025)**, arXiv:2510.18569 — quality-diversity (MAP-Elites style) over strategy ideas, with regime detection in some seed strategies. Different mechanic (QD, not island GA), no per-regime sub-populations of execution parameters. https://arxiv.org/html/2510.18569v1
- **"Adaptive and Regime-Aware RL for Portfolio Optimization" (2025)**, arXiv:2509.14385 — regime-aware RL (PPO/LSTM/Transformer) for asset allocation. No GA, no GMM hierarchy, no martingale. https://arxiv.org/html/2509.14385

Overlap: the *idea* of regime-conditioned strategy adaptation is mainstream.
Difference: IslandPilot binds regime to a *separate evolved population per regime* with restricted migration, which neither CGA-Agent nor QuantEvolve do.

### D. GMM / hierarchical regime detection

- **Two Sigma, "A Machine Learning Approach to Regime Modeling"** — uses GMM/HMM on macro factors. https://www.twosigma.com/articles/a-machine-learning-approach-to-regime-modeling/
- **Botte & Bao (2025) etc.** — agglomerative & GMM hierarchical merging with BIC; the BIC-then-merge recipe (Baudry, Raftery et al. 2010, "Combining Mixture Components for Clustering") is standard practice in `mclust`. https://pmc.ncbi.nlm.nih.gov/articles/PMC2953822/
- **Macrosynergy / LSEG articles** survey GMM, HMM, agglomerative for regime labelling. https://macrosynergy.com/research/classifying-market-regimes/
- **"Multivariate Regime Identification … via GMM and Gradient Boosting"** (Springer 2025). https://link.springer.com/chapter/10.1007/978-3-032-08462-0_27

Overlap: hierarchical GMM with BIC is *not novel as a method* — it's a standard pattern in model-based clustering and has been applied to macro regimes.
Difference: IslandPilot uses the hierarchy *structurally* — the macro level constrains GA migration topology and the leaf level binds genomes. That structural use of the hierarchy (regime tree -> island topology) is the genuinely new piece.

### E. Martingale / grid + ML

- **MQL5 community articles, e.g. "Machine learning in Grid and Martingale trading systems"** (mql5.com/en/articles/8826) — practitioner literature, no academic per-regime evolution.
- **Anti-martingale / regime-aware grid sizing** appears only in trading-blog literature, not peer-reviewed.

Overlap: applying ML to martingale is rare in academia and mostly negative ("don't bet on it"). No paper applies a per-regime island GA to Martingale execution parameters.

### F. Niching / multimodal GA

- **Bessaou, Pétrowski & Siarry (2000), "Island Model Cooperating with Speciation for Multimodal Optimization"** — island + speciation. Generic optimization, no finance. https://link.springer.com/chapter/10.1007/3-540-45356-3_43

## Verdict

**Partial novelty — the *combination* is novel, the *components* are not.**

- Island GA: 30+ years old.
- GMM regime detection: standard.
- Hierarchical BIC-merging GMM: standard (Baudry-Raftery 2010, mclust).
- GA on trading rules: textbook (Allen & Karjalainen 1999 onward).
- Regime-conditioned trading strategy: trivially common (HMM gating, RL regime-aware).
- **Binding regime hierarchy to GA island topology, with restricted-to-macro-sibling migration, evolving execution genomes specifically for hedged-Martingale cycles**: I found no paper that does this exact pipeline.

## Positioning angle (defensible)

Frame the paper as a *systems contribution*, not a methodological one. Defensible claim:

> "We present the first end-to-end pipeline that uses a hierarchical GMM regime tree to define the topology of an island-model GA, evolves separate execution genomes per leaf regime with macro-sibling migration, and applies the result to hedged-Martingale forex execution — a strategy class for which adaptive parameterization has previously been studied only in practitioner literature. We show that the hierarchical island structure is necessary for diversity preservation across regimes, and report a 87% drawdown reduction and 85% loss reduction OOS versus fixed configs, attributable primarily to regime-aware risk management rather than alpha generation."

Things to *not* claim:
- Do not claim novelty of island GA, GMM regimes, or hierarchical GMM individually — reviewers will reject immediately.
- Do not claim the strategy generates alpha — your own notes say it is "breakeven-to-losing on all fixed configs after spread"; the contribution is risk control, not return.
- Do not claim regime-conditioning is novel — frame the *structural binding* (regime tree -> island topology) as the contribution.

## Risk areas

1. **arXiv:1801.01620 (Dynamic Island Model based on Spectral Clustering)** is the most dangerous comparison. A reviewer who knows it will ask: "How is your regime-tree island assignment conceptually different from clustering individuals into dynamic islands?" Answer ready: their clustering is endogenous (genome-space, for diversity); ours is exogenous (environment-space, for specialization). Also their islands have no semantic meaning, ours do.
2. **arXiv:2510.07943 (CGA-Agent)** is the most recent regime-aware GA-for-trading paper (October 2025). You must cite it and explicitly say "single-population GA with regime-conditioned fitness, vs our per-regime population with restricted migration".
3. **QuantEvolve (arXiv:2510.18569)** is concurrent quality-diversity work. Cite it and contrast: QD over strategy ideas vs island GA over execution parameters.
4. **The mclust / Baudry-Raftery 2010 hierarchical-GMM pattern** must be cited; otherwise reviewers will think you reinvented it.
5. **No single paper dominates the work.** No one has put all five components together for hedged-Martingale execution. The combination + the application domain is genuinely empty space.

## Required citations to include in the paper

- Whitley et al. 1999 (island GA foundation)
- Meignan/Lardeux dynamic island work (closest mechanism)
- Allen & Karjalainen 1999 (canonical GA-for-trading)
- Hryshko & Downs 2012 (GA forex)
- Hirabayashi, Aranha & Iba 2009 (GA forex)
- Baudry, Celeux, Raftery et al. 2010 (hierarchical merging of GMM components)
- Two Sigma regime-modeling article (industry standard reference for GMM/HMM regimes)
- arXiv:2510.07943 (CGA-Agent, contemporary regime-aware GA trading)
- arXiv:2510.18569 (QuantEvolve, contemporary QD-based strategy evolution)
- Chou et al. 2014 IEEE TSMC (rule-based dynamic trading w/ tabu search; you already have the PDF)

## Bottom line

The pipeline is **novel as a combination** for a strategy class (hedged-Martingale) where academic ML treatment is sparse. It is **not novel methodologically** at the component level. A supervisor will accept the systems-contribution framing if the contribution is honestly bounded to (a) the hierarchy-to-island-topology binding, (b) the specific application to Martingale execution, and (c) the empirical demonstration that the structure matters for risk control. Overclaiming the GA, the GMM, or the regime-conditioning will get the paper rejected.
