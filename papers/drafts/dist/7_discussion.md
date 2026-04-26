## 7. Discussion

### 7.1 Capital Preservation Without Alpha Generation

§6.6 establishes the mechanism: drawdown collapses through risk bounding, not entry-quality engineering. The interpretive question is what this result *category* — capital preservation without alpha — means for evaluating optimisation systems applied to negative-expectancy strategy classes.

Two implications follow. First, the standard metric set in the trading-systems literature (PF, session win rate, bust count) is necessary but insufficient for Martingale-family evaluation: under the §6.6 mechanism matrix, all three moved against the pipeline while survivability metrics (worst-bust magnitude, peak equity usage) moved in its favour. Future evaluations of risk-bounding architectures on this strategy class should report worst-bust dollar magnitude and peak-exposure as primary metrics; otherwise an architecture that preserves capital is indistinguishable from one that hands it back.

Second, the result is narrower than the architecture's stated ambition. The pipeline succeeds at the *bounded-loss* problem and is silent on the *positive-expectancy* problem; both are valid targets for regime-aware evolutionary search but have different fitness-landscape geometry. A reader who concludes from §6.1 that regime-aware GA is "the right tool for FX trading" has over-extended the scope. The right reading is narrower: a fit for trading-system problems whose primary failure mode is exposure-driven and whose alpha source is independent of the optimisation. §7.3 develops the consequences for entry-signal evolution under realistic costs.

### 7.2 Feature Dominance and Strategy Sensitivity

The §6.3 finding — that volatility-family features dominate MI because they proxy the strategy's bust-probability driver, not because they predict returns — has two further consequences.

First, Müller et al. (1997)'s asymmetric information-flow argument — long-horizon volatility shapes short-horizon more than the converse — is consistent with the §6.3 multi-scale ranking and grounds why multi-scale aggregated NATR is not redundant with the base NATR. Second, regime-tree segmentation is therefore *strategy-conditioned*: the same 30-feature pool applied to a momentum strategy would likely surface trend-strength features as MI-dominant, partitioning the same EUR-USD history into different leaves. The pipeline's regime taxonomy is an artefact of strategy + features + label, not a property of the market alone (epistemic-harm framing in §7.10 Tier 4).

The four extension features below threshold (vol-of-vol, return skew, kurtosis, lag-1 autocorrelation) are retained as diagnostic features and as candidates for instruments with stronger distributional asymmetries than major FX.

### 7.3 The Spread Problem and What the Pipeline Does About It

The depth-linear spread accumulation driving §6.5 is structural to grid-hedged Martingale on liquid spot FX, not specific to OANDA, the 2-pip EUR-USD environment, or the `'original'` preset. Any venue charging spread per entry produces the same depth-cost coupling; any strategy whose recovery opens additional positions with each adverse move pays it. The consequence is that *no fixed-parameter configuration of this strategy class can be profitable on a major-FX instrument under realistic spread* — confirmed empirically by the 240-config search in §7.8. The §6.6 risk-bounding mechanisms collapse drawdown by avoiding the cost structure, not by negotiating it.

This shapes how the OOS result should be cited. It **demonstrates** that regime-structured evolution can bound a Martingale's loss envelope under realistic costs without evolving the entry signal — Iteration 1's 20-gene genome has no `signal_mode` or `direction_bias`. It **does not refute** the possibility that an entry-signal-evolving variant (Iteration 2) could cross PF = 1.0; that experiment has not been run at full scale (§6.8 confirms readiness; §8.1 commits the work).

The methodological implication: claims of "evolutionary alpha generation" on FX should be evaluated against the specific combination of entry signal, cost model, and OOS window, because each axis can absorb a substantial fraction of the apparent edge. The present result isolates the *bounded-loss* axis cleanly because entry is held random; future work varying entry signal separately can isolate any alpha contribution.

### 7.4 Real-Engine Evolution vs Simplified Simulation

The gap between simplified simulation and full-engine evaluation is substantial. Initial experiments on a simplified cycle simulator (no spread, swap, slippage, or margin accounting) produced PF > 1.0 and apparent improvements; the same architecture on the full engine did not reproduce these. Genomes evolved on the simplified simulator produced extreme parameter values (50-pip hedges with ATR-based TP) that created sessions lasting weeks, reducing throughput to a handful of cycles per year. The lesson is direct: parameters evolved on cost-free simulators exploit the simulator's missing constraints, and these are precisely the configurations that fail under realistic execution.

Real-engine evaluation also surfaces correctness conditions that simpler simulators render unnecessary — the CFD margin-bust state-leakage and categorical-gene encoding bugs in §4.2 and Appendix G. Both produced statistically degenerate fitness distributions (nearly constant across diverse genomes) rather than obviously wrong outputs, making them hard to diagnose by population-level metrics alone. The implication: real-engine fitness evaluation demands explicit correctness at the engine–evolver interface; the pipeline must be validated end-to-end before any full training run. This is one axis along which the present work goes beyond the headline: surfacing the boundary conditions under which evolutionary trading systems can be trusted at all.

### 7.5 Comparison with Related Approaches

The engine-controlled comparison in §6.7 (Figures 5–7, Table 5) tests the four pipelines under identical conditions. Beyond the headline metrics, two architectural lessons emerge from the comparison.

**Hand-set rule-based gating fails because the activation thresholds are wrong.** GTSBotPilot's trend-abort module — designed to cut losses at level ≥ 3 — fired zero times across 2,812 OOS cycles despite L3–L5 contributing -$10,704 against L0–L2's +$4,992 gross (§6.7 Finding 4). The control surface existed but hand-set thresholds were never reached given actual OOS feature trajectories. IslandPilot's `gate_confidence_min` and `abort_aggressiveness` are evolved per regime, so the GA discovers operationally meaningful thresholds that hand-set GTSBot could not. The distinction is not "rule-based vs evolutionary" but "static vs regime-conditioned learned thresholds" — what Rundo et al. (2019)'s GTSBot leaves on the table is per-regime learning, not the rule structure.

**Discrete preset selection (FinRL family) under-utilises its action space.** FinRLPilot has four trained discrete actions; over 1,170 OOS cycles the Q-policy collapsed onto `conservative` (87.9%), with `aggressive` zero — concentrating on the safest preset and still losing capital. The reading is that algorithm *expressivity* is not the bottleneck on this strategy/instrument; the bottleneck is *representational granularity*. IslandPilot's per-regime continuous genome (5 pipeline + 14 strategy across 63 regimes) supplies orders-of-magnitude finer granularity, which produces the §6.7 gap. A deeper deep-RL baseline (PPO with continuous actions, or extended FinRL with richer state encoding) is the natural extension (§8.1); the present FinRLPilot result is a *floor*, not a ceiling.

**Comparison with Yang et al. (2025) and Chideme et al. (2025).** Architectural overlap and distinction (HMM vs hierarchical GMM; GP expressions vs fixed-length parameter vectors; co-evolutionary feedback vs ring sibling migration; problem-derived vs heuristic topology) is detailed in §2.2 and §2.3. Neither prior work evaluates on a live execution engine with realistic spread and margin accounting, so direct numerical comparison is infeasible. A journal-extension comparison against Yang et al.'s reported numbers under their own protocol is in scope.

### 7.6 In-Sample Validation and Out-of-Sample Transfer

With a 3-year training window (2022–2024), in-sample performance provides a directional sanity check but not a primary result — the regime tree is fitted to that window, so in-sample numbers reflect how thoroughly genomes exploit known regime structure. The principal result is the 2025–2026 OOS period (Table 5, §6.1), testing whether the learned regime–parameter mappings transfer to genuinely unseen conditions.

The §6.1 OOS magnitude is substantial but not an alpha claim — the PF delta is modest and still sub-unity. The improvement transfers because it rests on structural risk-bounding (selectivity, size compression, depth capping; §6.6) rather than on a fragile directional signal. A directional mechanism would be more vulnerable to regime shift between train and eval (Bailey et al., 2014); a risk-bounding mechanism generalises as long as the regime tree's feature space recognises OOS regimes at all — which it does, because the macro/sub partition is built on slow-changing volatility and structural features whose distributional properties evolve smoothly across windows.

The 2025–2026 OOS period was structurally challenging: EUR-USD experienced sustained directional moves driven by macroeconomic events (US tariffs, Fed hawkishness, ECB rate convergence) absent from the training window. Under these conditions the pipeline *survives* (preserves capital) rather than *thrives* (generates alpha); the baseline does not survive. Single-window limitation and walk-forward extension are addressed in §7.7.

### 7.7 Limitations and Scope

Limitations are split into two groups: scope constraints (deliberate boundaries on what was attempted) and reviewer-grade empirical gaps (analyses a reviewer will reasonably ask for, with the specific experiment that would close each).

**Scope constraints.**

*Computational budget.* Full-scale training uses 12,600 evaluations (20 gens × 10 individuals × 63 islands). Larger populations and more generations would explore the per-regime space more thoroughly and are the first axis of future scaling.

*Single instrument and timeframe.* Evaluation is limited to EUR-USD 5m. The architecture is instrument- and timeframe-agnostic by construction, but generalisability is empirically open. Instruments with lower spread-to-movement ratios (crypto futures, ECN forex with 0.3–0.5 pip spreads) may exhibit larger pipeline improvements since spread is not the binding constraint there.

*Frozen regime tree.* Novel states are forced into the nearest existing leaf via GMM posterior, a classification that can be arbitrarily poor when conditions diverge sharply from training (§3.6; online-adaptation in §8.1).

*Negative result on alpha.* This work does not demonstrate positive alpha on EUR-USD under realistic costs (PF 0.877 < 1.0). The contribution is bounded loss, not generated profit (§7.1). Reproduction depends on the correctness conditions in §4.2 and Appendix G; without them, practitioners will reproduce the statistically degenerate fitness signals from early development rather than the headline numbers.

**Reviewer-grade empirical gaps.** Five gaps are named so a reviewer can locate them at a glance. Each lists the gap, the closing experiment, and its compute budget.

*G1. Statistical stability of the headline drawdown.* The §6.1 0.75% drawdown is a single-realisation OOS measurement. The trained genomes are stochastic functions of the GA's random seed, so the headline has an uncharacterised seed-induced distribution. *Closing experiment:* re-run Iteration 1 with K = 10 distinct seeds (~105 cloud-hours), report mean ± 95% block-bootstrap CI on max DD. *Status:* deferred to journal extension.

*G2. Multi-window OOS robustness.* The 15.5-month evaluation is one window. The qualitative claim (drawdown well below baseline) is expected to generalise but is not verified across windows. *Closing experiment:* walk-forward with three overlapping 12-month training windows ending at quarterly cutoffs through 2024 and three corresponding 6-month OOS windows in 2025; report DD and PF distributions. CPCV adaptation to per-regime islands is the more rigorous variant (Lopez de Prado, 2018; Arian et al., 2024). *Compute:* ~30–60 cloud-hours. *Status:* deferred to journal extension.

*G3. Within-class baseline strawman acknowledgment.* The baseline runs the `'original'` preset with random entry, which is by construction negative-expectancy on a 2-pip-spread instrument under any directional macro shock — a *deliberately weak* within-class reference. The 86.6 pp gap is real under engine-controlled comparison, but a meaningful fraction reflects how poor a random-entry Martingale is, not how good IslandPilot is. The §6.7 four-pipeline comparison is the more informative reference. *Closing comparison:* a non-Martingale baseline of comparable training compute (regime-conditioned mean-reversion or trend-following under the same fitness composite). *Status:* out of dissertation scope; the §1 strategy-class justification stands as why this comparison is methodologically distinct rather than apples-to-apples.

*G4. Topology ablation: GA on the alternate regime tree.* §6.3 / Appendix I show ARI = 0.034 between the production fallback tree and the 3-MI-feature tree (Tree A) — structurally different partitions. PnL consequence is unmeasured. *Closing experiment:* re-run Iteration 1 GA on Tree A with identical seeds, population, budget; compare OOS DD, PF, bust rate. *Compute:* ~10 cloud-hours. *Status:* deferred to journal extension; a comparable-or-better Tree A would weaken the "topology-from-regimes is doing the work" claim, a substantially worse result would strengthen it.

*G5. Flat-island GA control on the same gene space.* The "topology-from-regimes" claim implies the regime-derived topology does work a flat or single-population GA on the same 20-gene space could not. §6.2's random-search control compares against uniform sampling, not a panmictic GA. *Closing experiment:* single-population GA with N = 630 individuals (matching IslandPilot's total population), 20 generations, fitness on the *aggregate* 36-month window rather than per-regime, same operators and seeds. Report OOS DD, PF, bust rate. *Compute:* ~10–12 cloud-hours. *Status:* the most reviewer-load-bearing missing comparison; deferred to journal extension. A panmictic GA achieving comparable OOS would substantially weaken the architectural contribution claim, so this gap should close before journal version.

In-progress validations and direct empirical extensions are listed in §8.1.

### 7.8 Implications for Martingale Strategy Design

The exhaustive 240-config fixed-parameter sweep preceding this work returned no profitable configuration on EUR-USD under realistic OANDA costs over 2022–2024 — confirming the §2.4 structural argument empirically. The interpretive question is what the artefact-verified evolved-parameter pattern (§6.4) implies for the *design space* of adaptive Martingale management more generally.

Two implications follow from the pattern of choices the GA actually made.

**Termination beats truncation.** Given freedom to evolve `max_levels` anywhere in [2, 6], the GA fixed it at the ceiling for 96.5% of individuals and instead spent its expressive budget on `abort_aggressiveness` (range 0.000–0.385). The lesson: *when* to terminate matters more than *how deep* the cycle is allowed to go, at least under this fitness composite. A Martingale design that hard-codes a low depth ceiling forfeits the regime-conditioned timing information an evolved abort policy carries; conversely, leaving depth uncapped and relying entirely on a learned abort can plausibly recover the same envelope. Whether this is universal or specific to the §4 composite (which weights bust rate cubically) is open and worth a targeted ablation.

**Recovery-arithmetic floors are not load-bearing under a working regime gate.** 40% of Iteration 1 genomes evolved `sizing_factor` below the √2 viability threshold, yet capital preservation still emerges. The implication is not that the √2 floor is wrong — it is correct under the textbook recovery argument — but that under a sufficiently selective gate the infeasible-recovery genomes are simply *not deployed in regimes where their infeasibility binds*. The gate masks the mathematical violation. Iteration 2's explicit [1.5, 2.5] floor is therefore belt-and-braces hardening rather than a precondition: the gate is the binding safeguard.

Both implications generalise beyond Martingale to any negative-expectancy strategy class managed by a selective adaptation layer: the adaptation layer can substitute for, but does not replace, the underlying mathematical constraints. A practitioner should not infer recovery-arithmetic constraints are dispensable in production — only that under a working gate they become operationally redundant rather than structurally necessary. Removing the gate exposes them again.

### 7.9 Generalisability Beyond EUR-USD

IslandPilot is instrument-agnostic by construction — feature pool, regime discovery, and island evolution all operate through standard OHLCV and the engine's backtesting interface — but current results are specific to EUR-USD on OANDA. On instruments where execution costs are a smaller fraction of gross profit per session (crypto futures with ~0.04% taker fees, ECN forex with 0.3–0.5 pip spreads), the base strategy may already operate near breakeven, shifting the pipeline's contribution from loss bounding to genuine return improvement. Whether it can cross PF = 1.0 on such instruments is an open empirical question and natural extension target.

The regime-tree features (NATR, ATR, ADX, session hour, choppiness) apply to any liquid instrument, but specific regime structure will differ. An instrument with strong seasonality might produce trees dominated by calendar features; a high-volatility crypto pair by ATR-derived features. The architecture accommodates these automatically through BIC-based model selection at both clustering levels, adapting granularity to each instrument's feature-space statistics. Establishing transfer of the regime-structured island topology across pairs (preliminary GBP-USD and USD-JPY work) and across asset classes (crypto, equity indices) is one direction the conference-paper extension targets (§8.1).

**Macro-event scope.** The 2025–2026 OOS window encompasses macroeconomic events (US tariffs, Fed policy shifts, ECB rate convergence) absent from the 2022–2024 training window. The pipeline survived through *exposure bounding and abort-driven termination* rather than regime recognition of the novel macro states — the regime tree was not retrained on 2025–2026 data. This supports the robustness of the capital-preservation mechanism (which compounds multiplicatively on the loss path independent of regime-tree accuracy) but does **not** validate the tree's macro taxonomy under structural breaks. Online adaptation (§8.1) is the architectural response; without it, replication on a window with different structural breaks should expect the same *qualitative* result (DD well below baseline), not the same *quantitative* number.

### 7.10 Ethics and Responsible-Deployment Considerations

Ethics here is treated as design rationale rather than post-hoc reflection. Three design decisions short-circuit specific harm chains in the trading-systems literature: production-engine fitness evaluation (§1, §4) addresses the simulator-overstatement chain by trading ~10× computational cost for realistic execution; full reporting of unfavourable primary metrics in Table 5 (PF < 1.0, 50% bust rate, 5.6% L0 win rate) refuses the selective-reporting mechanism by which overstated priors propagate into the practitioner community; and the Appendix G correctness-condition disclosure (§4.2) transfers the diagnostic burden for non-obvious, fitness-degenerating engine bugs from the replicator to the original author. Each is methodological *and* ethical.

The 10× cost trade-off is worth interrogating, not asserted as unalloyed good. The choice was viable here because (a) cloud-credit access to a 60-vCPU spot VM absorbed per-evaluation cost into ~10 wall-clock hours; (b) the 20-gene Iteration 1 space was tractable at this budget; (c) the alternative — discovering simulator-only genomes were unusable months later in deployment — has a higher amortised cost than 10× per-evaluation compute. None of these conditions is universal: a group without spot-VM access, or on a 200-gene genome, or under a per-deadline time-box, may face a different trade. The ethical commitment ("evaluate on production-equivalent conditions") is invariant; the *implementation* is contingent on available compute. Future work should report the equivalent budget breakdown so the trade-off can be replicated on its own terms.

The research touches a four-tier harm surface; the design or reporting decision that mitigates each tier is summarised below.

*Table 11: Harm tiers and their mitigants.*

| Tier | Harm | Mitigant |
|---|---|---|
| 1 — Individual | Retail trader clones the artefact, encounters a structural break not in the 2022–2024 training data, sustains loss. | Deployment disclaimer (front-matter); explicit PF < 1.0 and single-window framing in §6.1, §7.1, §7.7; demo-account paper-trading recommendation; Appendix G correctness conditions. |
| 2 — Research community | Citers propagate the §6.1 drawdown headline without noting sample size (72 sessions), single 15.5-month window, or absence of significance testing. | §7.7 limitations; Table 4a scope-of-claims map; explicit ask that replicators report all five Table 5 metrics. |
| 3 — Market microstructure | At scale, multi-instrument deployment of correlated instances could move the spread the model assumed — an ML-derived system influencing the prices it depends on. | Out of scope at single-account dissertation evaluation. Production extension responsibility: monitor fill quality, latency, effective-spread asymmetry; pull back if the strategy moves the prices it consumes. |
| 4 — Epistemic | "Regime discovery" misread as identification of *causal* market states; subsequent work cites this paper as having "mapped EUR-USD regime structure." | Hedged language throughout ("the regime tree the pipeline uses", not "the regimes of EUR-USD"); documented sensitivity to feature-set choice (§6.3 / Appendix I, ARI = 0.034 between two valid trees). |

Data governance is addressed in §5.1 (OANDA Developer Programme terms; no personal or counterparty data; release scope through the project repository); the bidirectional generative-AI use declaration is in front-matter. Live deployment is the operator's regulatory responsibility, not the researcher's; reproduction on real capital must be preceded by demo-account paper trading over a comparable horizon — no guarantee of profit, capital preservation, or replicability of the §6 numbers is offered or implied (full disclaimer in front-matter).

---
