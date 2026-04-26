## 6. Results

*Table 4a: Scope of claims — which result belongs to which iteration, training window, and OOS window.*

| Section | Iteration | Training window | OOS window | Reports |
|---|---|---|---|---|
| §6.1 Table 5 | Iteration 1 (20 genes, 3 groups) | 2022-2024 (36m) | 2025-01-02 → 2026-04-19 (15.5m) | Headline pipeline-vs-baseline + 4-system comparison |
| §6.2 Fitness evolution | Iteration 1 | 2022-2024 / 2022 H1 | — | Per-generation trajectory across 63 islands + random-search control |
| §6.3 Feature importance | Iteration 1 | 2022-2024 | — | MI ranking + fallback partition + feature-set sensitivity of regime tree |
| §6.4 Pipeline behaviour | Iteration 1 | — | 2025-2026 | Evolved-parameter ranges + depth distribution |
| §6.5 Cost analysis | Iteration 1 | — | 2025-2026 | Spread-cost mechanics |
| §6.6 Mechanism analysis | Iteration 1 | — | 2025-2026 | Three risk-bounding mechanisms + their evidence |
| §6.7 Pipeline comparison | All four pipelines | as above | 2025-01-02 → 2026-04-19 | Engine-controlled four-pipeline comparison + figures |
| §6.8 Iteration 2 pre-flight | Iteration 2 (architectural validation only) | 2024 Q1 (3m) | 2024 Q2 (3m) | Convergence and gene-encoding correctness, not §6.1 source |

The §6 numerical results all come from Iteration 1 acting on 2025–2026 data through the corrected qengine engine. Iteration 2 (the design endpoint described in §3.4.1 Table 3) is implementation-complete in source but is **not** the model that produced §6.1.

### 6.1 Primary Out-of-Sample Result

Table 5 reports the primary engine-controlled comparison across **four pipelines** on the 15.5-month strictly out-of-sample period (2025-01-02 to 2026-04-19), under identical conditions: $10,000 starting balance, the qengine production engine, real per-candle OANDA spread, swap and slippage cost model, and the same Martingale strategy substrate. IslandPilot was trained exclusively on 2022–2024; no 2025–2026 data entered fitting of any genome, regime tree, or parameter. FinRLPilot's tabular Q-learner was trained on the same 2022–2024 window. GTSBotPilot is rule-based and requires no offline training. The Baseline runs the original Martingale preset with no pipeline attached.

*Table 5: Engine-controlled pipeline comparison, EUR-USD 5m, 2025-01-02 to 2026-04-19 (15.5 months OOS).*

| Metric | Baseline | GTSBotPilot¹ | FinRLPilot¹ | **IslandPilot** | IP vs Baseline |
|---|---:|---:|---:|---:|---:|
| Sessions / cycles | 1,619 | 2,812 | 1,170 | **72** | -96.0% |
| Trades | 5,238 | 6,614 | 2,837 | **245** | -95.3% |
| Net profit % | -87.38% | -58.23% | -14.51% | **-0.83%** | +86.55 pp |
| Profit factor | 0.717 | 0.80 | 0.90 | **0.877** | +0.160 (+22%) |
| **Max drawdown %** | **84.73%** | **58.38%** | **17.97%** | **0.75%** | **-83.98 pp (≈113× smaller)** |
| Peak equity usage % | 63.7% | 63.13% | 46.74% | **10.3%** | -53.4 pp |
| Session win rate | 83.3% | 78% | 54% | **43.1%** | -40.2 pp |
| Bust rate² | 16.8% | 1.7% | 19% | **50.0%** | +33.2 pp |
| Worst bust loss | -$148.99 | -$126.55 | -$195.32 | **-$71.79** | +$77.20 |
| Level-0 win rate | 26.4% | 44% | 35% | **5.6%** | -20.8 pp |
| Cost drag % | 29.9% | 15.65% | 10.42% | **19.2%** | -10.7 pp |
| Account blown? | No (1,262 left) | No | No | **No (9,917 left)** | — |

¹ FinRLPilot and GTSBotPilot are in-house re-implementations of the FinRL (Liu et al., 2020) and GTSBot (Rundo et al., 2019) algorithm families running on the same qengine substrate. Full implementation specifications are in Appendix E. The comparison is engine-controlled — same instrument, window, engine, cost model, and base strategy — not a benchmark against the original published external systems. Differences in OOS metrics are attributable to the pipeline layer rather than to engine, broker, fill, or data choices.

² *Bust-rate definitional note.* IslandPilot's 50.0% bust rate counts engine-level CFD margin trips on small dollar amounts; FinRL/GTSBot count strategy-level max-level escapes. The numbers are *not directly comparable in rate*; they are comparable in **absolute worst-bust dollar loss** (IslandPilot -$72 vs FinRL -$195 vs GTSBot -$127) and **net % impact** (IslandPilot -0.83% vs FinRL -14.51% vs GTSBot -58.23%). The high bust-rate reading on IslandPilot reflects how few sessions it opens (72 total) rather than a higher absolute risk profile; full discussion in §6.7.

**Reading the IP-vs-Baseline gap honestly.** The 86.6 pp net-loss gap between IslandPilot and Baseline reflects *both* pipeline value *and* how poor a random-entry Martingale is on a 2-pip-spread instrument under realistic costs — the random-entry preset is a deliberately weak lower bound (acknowledged structurally in §7.7 G3), not a competitively tuned strategy. The four-pipeline comparison in §6.7 (IslandPilot vs FinRLPilot vs GTSBotPilot vs Baseline) is the more informative reference for assessing pipeline contribution against algorithm-family alternatives that themselves bound losses on the same substrate.

Three findings dominate Table 5: drawdown collapses by approximately two orders of magnitude, peak equity usage falls from 63.7% to 10.3%, and profit factor rises while remaining sub-unity. The pipeline does not produce positive absolute expectancy — PF < 1.0 means gross losses still exceed gross profits — so the contribution is capital preservation, not alpha generation: the approach bounds the drawdown envelope and collapses peak exposure enough to convert a catastrophic strategy into a near-breakeven one.

**Market regime context.** The 2025 to 2026 evaluation period was structurally hostile to undifferentiated Martingale strategies. EUR-USD experienced a sustained decline from approximately 1.0500 to 1.0300 in early 2025 driven by US tariff policy and Federal Reserve hawkishness, followed by a recovery above 1.0800 by April 2026 as US growth concerns and ECB rate convergence shifted the balance. These directional moves drive multi-level adverse runs: a strategy entering long during a sustained downtrend reaches hedge level after hedge level without recovering, ultimately hitting the maximum depth limit. Without regime-aware selectivity or depth discipline, the baseline accumulates 271 depth-5 busts (-$12,784 in cumulative loss) during directional phases.

**Why the baseline loses.** The baseline operates the `'original'` preset with a random entry signal (signal_mode='none', long_only) under a 10-pip hedge distance, 20-pip take-profit, 6 maximum depth levels (depths 0 to 5), and geometric sizing with factor 2.0. A depth-5 bust costs the cumulative geometric sum 1 + 2 + 4 + 8 + 16 + 32 = 63 base units. Across 1,619 sessions, 272 busts occur (16.8% bust rate), with 271 reaching depth 5 (depth distribution table in Section 6.4). These deep busts overwhelm the +$4,323 gross profit from depths 0–4, driving net equity from $10,000 to $1,262.

**Comparison systems.** GTSBotPilot and FinRLPilot have been re-run on the canonical OOS window and engine and are reported in Table 5 above. The four-way ordering — IslandPilot ≪ FinRL ≪ GTSBot ≪ Baseline on both net loss and max drawdown — is analysed in §6.7 (mechanism comparison) and §7.5 (architectural comparison), with equity and drawdown trajectories visualised in Figures 5–7.

### 6.2 Fitness Evolution

The Iteration 1 cloud training run (Google Cloud `c2-standard-60` spot, 60 vCPU / 240 GB RAM, 60 parallel workers, europe-west2-c) evolves 63 active islands across 10 macro-clusters, with 10 individuals per island for 20 generations: 12,600 real-engine genome evaluations in 10 h 33 min wall-clock (per-generation mean 1,888 s, range 1,843–1,917 s — stable throughput).

*Table 6: Training run configurations.*

| Run | Islands × Pop × Gens | Total Evals | Hardware | Wall-clock | Role |
|---|---|---|---|---|---|
| **Iteration 1 cloud (full 2022 to 2024)** | 63 × 10 × 20 | 12,600 | c2-standard-60 (spot), 60 workers | 10 h 33 min | **Primary reported result (§6.1, 6.4–6.6)** |
| Iteration 2 pre-flight (3-month) | 63 × 8 × 8 | 4,032 | Consumer CPU, 9 workers | ≈ 2.8 h | Architectural validation only (§5.6, §6.8) |

*Table 6a: Per-generation fitness distribution across 63 islands (Iteration 1 cloud run, source: cloud_training_2026-04-23.log). Migration generations marked ★.*

| Gen | Mean best-fitness | Min | Max | Wall-time (s) |
|---:|---:|---:|---:|---:|
| 1 | 55.964 | 51.529 | 58.977 | 1,843 |
| 2 | 56.507 | 51.974 | 59.077 | 1,917 |
| 3 | 56.974 | 52.900 | 59.077 | 1,903 |
| 4 ★ | 57.881 | 55.981 | 59.077 | 1,900 |
| 5 | 57.952 | 55.981 | 59.077 | 1,895 |
| 6 | 58.008 | 56.145 | 59.084 | 1,892 |
| 7 | 58.073 | 56.495 | 59.084 | 1,884 |
| 8 ★ | 58.394 | 57.440 | 59.084 | 1,884 |
| 9 | 58.425 | 57.440 | 59.084 | 1,880 |
| 10 | 58.478 | 57.440 | 59.084 | 1,880 |
| 11 | 58.498 | 57.440 | 59.084 | 1,882 |
| 12 ★ | 58.652 | 57.579 | 59.084 | 1,879 |
| 13 | 58.665 | 57.579 | 59.084 | 1,882 |
| 14 | 58.681 | 57.579 | 59.180 | 1,885 |
| 15 | 58.690 | 57.680 | 59.180 | 1,883 |
| 16 ★ | 58.782 | 57.841 | 59.180 | 1,883 |
| 17 | 58.789 | 57.841 | 59.180 | 1,887 |
| 18 | 58.797 | 57.841 | 59.180 | 1,884 |
| 19 | 58.805 | 57.841 | 59.200 | 1,883 |
| 20 ★ | 58.867 | 58.090 | 59.200 | 1,880 |

![Figure 8: Per-generation fitness distribution across 63 islands. Vertical dashed lines mark the five sibling-migration events (every 4 generations). The minimum (red) lifts from 51.53 → 58.09 (+12.7%) while the maximum (blue) stays essentially flat (58.98 → 59.20, +0.4%). The min–max envelope compresses from 7.45 at gen 1 to 1.11 at gen 20.](../figures/Figure8_fitness_distribution.png)

Three observations from Figure 8 and Table 6a sharpen the convergence story:

1. **The maximum is essentially flat from generation 1 (58.98 → 59.20, +0.4% over 20 generations).** The elite islands converged on near-optimal genomes within the very first generation; further generations did not improve the *best* island's fitness meaningfully. This indicates that for the 20-gene Iteration 1 search space the GA's exploration phase is short — most of the work happens early, on the best regimes, where regime-specific structure makes a high-fitness configuration accessible quickly.

2. **All convergence comes from the weakest islands rising, not from the best islands improving.** Min-fitness lifted from 51.53 to 58.09 (+12.7%), mean climbed from 55.96 to 58.87 (+5.2%), while max barely moved. The min–max spread compressed from 7.45 to 1.11 over the run — by generation 20 every island is within 1.1 fitness points of the elite, where at generation 1 the spread was nearly seven times larger. This is exactly the *consistent rather than scattered* convergence pattern the regime-conditioned island design was intended to produce.

3. **Migration is doing real work, with diminishing returns.** Generation 4 (the first migration) produces the largest single jump in min-fitness (52.90 → 55.98, **+3.08**). Subsequent migrations contribute progressively less (+0.95, +0.14, +0.16, +0.25 at generations 8, 12, 16, 20). The first migration breaks the worst islands out of poor-initial-population basins by injecting elite genomes from sibling regimes; later migrations operate on already-improved populations where the marginal benefit is smaller. By generation 8 the search is largely converged — extending to 30+ generations would yield only marginal gains on the min-fitness axis given the diminishing-return pattern, supporting the choice of 20 generations as adequate for the 20-gene Iteration 1 search space.

**Random-search control.** A natural sceptical reading of the convergence trajectory above is that the GA may not be contributing search efficiency beyond what uniform random sampling of the same 20-gene parameter space would deliver. The Iteration 1 GA's contribution beyond random sampling is quantified in **Appendix H**: N = 80 random genomes evaluated on the production composite fitness over a 6-month subset of the training window (2022-01-01 → 2022-07-01) yielded mean fitness 7.83 (std 13.4, max 52.6), against the trained-GA mean of 58.87 across the 63 islands at the final generation (std 0.25, min 58.09, max 59.20). The trained mean exceeds the random mean by 51 fitness units — Cohen's d = 5.38, or 3.8 standard deviations of the random-search distribution; 0 of 80 random genomes exceed the trained mean and 0 of 80 exceed the trained max. The random distribution also produces a 46.2% rate of zero-fitness genomes (insufficient activity in the 6-month window or NaN-state from extreme parameter combinations), against 0% in the trained population. The GA contributes search efficiency that random sampling of the same gene-bounds cannot replicate; the result is conservative because the 6-month random-evaluation window is a strict subset of the production training period.

**Why this signature is what the regime-derived topology should produce.** The flat-max / rising-min / shrinking-spread pattern is the predicted fingerprint of a topology in which subpopulations are *aligned with structural partitions* of the fitness landscape (Mahfoud, 1995, niching theorem; §2.3). Under such alignment the elite islands sit on the easy peaks of their own per-regime landscape and are saturated almost immediately (flat max from gen 1), while the lagging islands sit on harder regimes whose initial random populations land far from any peak — and ring migration from sibling islands within the same macro-cluster injects elite genomes that are *plausibly relevant* (drawn from neighbouring sub-regimes), so the lagging islands lift sharply. A flat or random topology, where migration is just population mixing, would predict the opposite signature: a slowly-rising max as new global optima are discovered through cross-pollination, with lagging islands rising only when their migrants happen to be relevant — effectively never, on a multi-modal landscape. The signature observed is thus diagnostic evidence for the topology choice, not just for the GA.

On this run no leaf accumulated a 30-day contiguous activation window under the fallback feature partition, so all 63 islands evolved on the full 2022–2024 training window; the fitness-isolation mechanism remains available in code for future windows where regime-specific contiguous activation regions do form.

### 6.3 Feature Importance

On the 2022–2024 training window with forward bars = 288 (≈ 1 trading day at 5m), the Kraskov MI procedure (α = 0.1) selected three features above the threshold — NATR_14_TF12 (1h aggregation), NATR_14_TF48 (4h aggregation), and NATR_50 (medium-term base NATR) — all volatility-family. The volatility dominance is not a generic property of EUR-USD price prediction; it is specific to the **strategy's failure mode**. Martingale cycles fail when sustained directional moves exhaust the depth ladder, and the per-bar probability of an N-pip adverse run is a monotonically increasing function of realised volatility — so any feature carrying volatility-regime information is, by construction, the most discriminative signal against a depth-escalation outcome label. The MI procedure is therefore selecting features that proxy the strategy's bust-probability driver, not features that proxy returns. Because fewer than 5 features passed the threshold (the minimum for a stable 5-macro × 3-sub split), the fallback rule (§4 Stage 1) broadened selection to the full 30-feature pool with macro/sub partitioning by lag-10 autocorrelation (full feature lists in Appendix A).

*Table 7: Top features by mutual information on the 2022–2024 training window.*

| Rank | Feature | Category | MI Score (normalised) | Selection |
|---|---|---|---|---|
| 1 | NATR_14_TF12 | Volatility (1h aggregation) | 1.000 | Above α threshold |
| 2 | NATR_14_TF48 | Volatility (4h aggregation) | ~0.65 | Above α threshold |
| 3 | NATR_50 | Volatility (medium-term) | ~0.40 | Above α threshold |
| 4+ | (remaining 27 features) | Various | < α · max | Below threshold |

The two top-ranked features are theoretical extensions implementing Corsi's (2009) HAR-RV multi-scale framework: on 5m EUR-USD, 1h and 4h aggregated volatility carry more discriminative power for Martingale outcome prediction than any single-scale volatility feature, empirically validating the theoretical motivation for including multi-scale volatility (§3.1). The remaining four extensions (vol-of-vol, skew, kurtosis, lag-1 autocorrelation) fell below the MI threshold but remain in the pool as diagnostic features. An earlier prototype configuration on a different outcome label retained 10 features without triggering fallback; full details in Appendix A.

**Sensitivity of the regime tree to the feature-set choice.** Because the production tree was built on the fallback feature set rather than the 3 MI-selected features, a reviewer will reasonably ask whether that choice changes the discovered regime structure. The tree was therefore re-fit on the same 2022–2024 training window using only the 3 MI-selected features (Tree A) and compared to the production fallback tree (Tree B). Tree A produced 7 macro / 47 leaves; Tree B produced 10 macro / 63 leaves; partition agreement between the two is **Adjusted Rand Index = 0.034, Normalised Mutual Information = 0.168** — the two trees produce structurally different partitions of the same data. Both pass the structural-validity threshold (separation CV 0.78 and 0.68 respectively, both ≫ 0.15), so neither is degenerate; the divergence is expected by construction because the fallback tree partitions a strictly richer feature space. The downstream PnL consequence — whether the GA evolved against Tree A would produce materially different bottom-line results — would cost roughly 10 hours of additional cloud compute to evaluate and is deferred to future work (§8.1). The sensitivity is reported because the answer "the choice does change regime topology, and we have not measured the performance consequence" is more useful than not asking the question. Full methodology and metric definitions appear in **Appendix I**.

### 6.4 Pipeline Behaviour and Evolved Parameters

The pipeline operates primarily as a regime-gated parameter adaptation mechanism. On the 15.5-month OOS window, the pipeline opens 72 sessions against the baseline's 1,619 (a 96% reduction). The evolved gating parameters and regime-specific genomes together cause the pipeline to refuse entry in most regimes and to deploy capital aggressively only in the small subset of regimes where its evolved configuration confers an acceptable loss profile. The per-session profit factor (0.877 for the pipeline vs 0.717 for the baseline) is modestly better but still below 1.0, reflecting that the selectivity is loss-bounding rather than alpha-generating.

*Table 8: Pipeline session depth distribution (72 sessions, 2025-01-01 to 2026-04-19).*

| Depth | Sessions | Wins | P&L |
|---|---|---|---|
| 0 (L0 only) | 4 | 4 | +$12.23 |
| 1 | 28 | 6 | -$19.22 |
| 2 | 8 | 8 | +$43.50 |
| 3 | 9 | 3 | -$84.00 |
| 4 | 17 | 9 | +$1.24 |
| 5 | 2 | 0 | -$2.16 |
| 6 | 4 | 1 | -$18.33 |

Depths 0 and 2 are net-positive; depths 1, 3, 5, and 6 are net-negative. Depth 4 is approximately neutral. The pipeline's 50% bust rate (36 of 72 sessions) is concentrated at depths 1 and 3 rather than at the catastrophic depth 5 that drives the baseline's loss. Average legs per session is 3.4 with a maximum of 7; the worst single-session loss is -$71.79, compared to the baseline's -$148.99.

The evolved parameters show meaningful differentiation across the 63 islands, reflecting regime-specific adaptation. Table 9 reports the ranges of key pipeline-level parameters across the trained islands.

*Table 9: Evolved pipeline-level parameter statistics across 171 individuals (63 islands × ~3 valid individuals each, extracted from the cloud-trained `island_evolver.json` artefact 2026-04-25).*

| Parameter | Min | Max | Mean | Median | Purpose |
|---|---:|---:|---:|---:|---|
| gate_confidence_min | 0.026 | 0.500 | 0.293 | 0.308 | Entry selectivity per regime |
| abort_aggressiveness | 0.000 | 0.385 | 0.207 | 0.195 | Cycle termination sensitivity |
| confidence_sensitivity | 0.500 | 1.928 | 1.241 | 1.239 | Confidence-based size scaling exponent |
| recovery_aggression | 0.311 | 0.927 | 0.611 | 0.609 | Drawdown-based size reduction rate |
| hysteresis_margin | 0.050 | 0.278 | 0.191 | 0.208 | Regime switch reluctance |

The `gate_confidence_min` mean of 0.29 (and median 0.31) indicates that the GA evolved *moderately restrictive* entry gating — well above the lower bound of 0.0 — meaning the regime confidence must reach approximately 30% before the pipeline allows entry in most evolved configurations. This is the primary lever behind the 96% session-volume collapse (§6.6 Mechanism 1). The `abort_aggressiveness` range (0.000 to 0.385, mean 0.21) shows that the GA has learned when to cut losses early: high-abort-aggressiveness islands terminate sessions before they reach maximum depth, accepting a small certain loss over a potentially catastrophic bust; low-abort-aggressiveness islands let sessions run, reflecting regimes where recovery probability is higher. `confidence_sensitivity` evolves above unity in most regimes (mean 1.24), producing convex scaling that penalises low-confidence regime classifications.

**Strategy-level gene findings (artefact verification).** Two artefact-level findings across the 171 individuals shape the mechanism analysis: (i) 165 of 171 (96.5%) evolved `max_levels` at the Iteration 1 upper bound of 6, with none lower — depth diversity in Table 8 therefore comes from early abort, not from cross-island depth-cap variation (developed in §6.6 Mechanism 3); (ii) 68 of 171 (39.8%) evolved `sizing_factor` below the √2 ≈ 1.414 mathematical-viability floor (range [1.259, 2.000]) — the capital-preservation result emerges *despite* this (interpretation in §7.8). Iteration 1 contains no `signal_mode` or `direction_bias` gene, so entry direction is not regime-conditioned in the cloud-trained model.

### 6.5 Transaction Cost Analysis

The depth-linear spread accumulation specified in §5.5 explains why the baseline operates below break-even (PF 0.717) despite an 83.3% session win rate: per-session wins are bounded by the take-profit minus cumulative spread cost, while depth-5 busts at sizing factor 2.0 lose 63 base units. The pipeline's total cost drag is 19.2% against the baseline's 29.9% (-10.7 pp); the four-pipeline cost-per-trade vs frequency inversion is reported in §6.7 Finding 5.

### 6.6 Mechanism Analysis: What the Pipeline Actually Does

The §6.1 headline result requires a mechanistic explanation. A plausible-sounding narrative would attribute the improvement to per-regime signal engineering: the pipeline picks better entries in each regime, avoiding bust-prone conditions, and therefore wins more often. That narrative is contradicted by the OOS data — the metrics that would indicate an entry-quality mechanism move in the opposite direction:

*Table 10: Mechanism signal matrix.*

| Candidate mechanism | Expected signal | Observed signal | Verdict |
|---|---|---|---|
| Better entries (higher L0 win rate) | L0 win rate ↑ | 26.4% → 5.6% (↓ 20.8 pp) | Rejected |
| Lower bust rate | Bust rate ↓ | 16.8% → 50.0% (↑ 33.2 pp) | Rejected |
| Smaller worst-case bust | Worst bust magnitude ↓ | -$149 → -$72 (-52%) | Confirmed |
| Reduced peak exposure | Peak equity usage ↓ | 63.7% → 10.3% (-84% relative) | Confirmed |
| Catastrophic-chain avoidance | Max DD ↓ | 84.73% → 0.75% (≈ 113× smaller) | Confirmed |
| Session-volume collapse | Sessions ↓ | 1,619 → 72 (-96%) | Confirmed |

The pipeline is, demonstrably, not engineering better entries. Its Level-0 win rate (sessions that close in profit at depth 0 without any hedge) falls by more than twenty percentage points relative to the baseline. Its bust rate triples in relative terms. If the mechanism were "regime-conditioned signal quality produces directional edge per regime," these numbers would rise, not fall. They fall because the pipeline makes a different bet: it trades much less, and when it does trade, it commits a much smaller fraction of equity.

Three mechanisms, all concerned with risk bounding rather than return generation, account for the observed improvement.

**Mechanism 1: Session-volume collapse (regime-gated selectivity).** The pipeline opens 72 sessions against the baseline's 1,619, a 96% reduction. The reduction is produced by the regime inferencer's hysteresis-gated entry (§3.6) combined with the per-island `gate_confidence_min` parameter evolved by the GA (mean 0.29, median 0.31 across 171 individuals; §6.4 Table 9). In most candles of the OOS period, either the regime confidence is below the evolved threshold or the currently-classified regime has an evolved genome that prohibits entry under current feature values. The pipeline sits out most of the market. This is the dominant contribution to the reduced drawdown: each avoided session is an avoided opportunity to accumulate a depth-5 bust.

**Mechanism 2: Position-size compression (peak-exposure bounding).** Peak equity usage falls from 63.7% (baseline) to 10.3% (pipeline), a reduction of 53.4 percentage points in absolute terms and 84% in relative terms. The AdaptiveSizer (§3.5) reduces position size via confidence and drawdown multiplicative factors. The evolved `confidence_sensitivity` exponent (mean 1.24 across islands) produces convex scaling that penalises regimes where GMM posterior probability is spread across multiple leaves; the evolved `recovery_aggression` parameter (mean 0.61) scales position down during drawdown. The combined effect is that the pipeline rarely commits more than ten percent of equity to open exposure, even when it does open sessions. A baseline depth-5 bust at full sizing costs up to -$148.99 (worst-case observed); the pipeline's worst-case bust at compressed sizing is -$71.79, a 52% reduction in worst-case loss magnitude.

**Mechanism 3: Catastrophic-chain avoidance via early abort, not max-depth restriction.** The baseline's loss is driven by 271 depth-5 busts (§6.1). The pipeline's 72 sessions show a shallower depth distribution: depths 5 and 6 together account for only 6 sessions (8.4%); the majority resolve at depths 1–4 (62 of 72, or 86%). The artefact-verified evolved-parameter findings in §6.4 sharpen the mechanism: **`max_levels` evolved uniformly to the Iteration 1 upper bound of 6 across 96.5% of individuals** — every island has the maximum depth ceiling available. The depth-distribution shift therefore comes *not* from per-island depth-cap diversity, but from `abort_aggressiveness` (mean 0.21, range 0.000–0.385) terminating sessions early in regimes where continued hedging is evaluated as having low recovery probability. The practical effect is that when pipeline sessions do escalate, the abort logic intervenes well before the depth ceiling, producing shallow busts rather than deep ones. This is a sharper finding than the original "depth capping" framing: the GA, given the freedom to lower `max_levels`, did not — it found capital preservation through the orthogonal lever of *when to terminate the cycle*, not through the lever of *how deep the cycle is allowed to go*.

**What the three mechanisms together do not do.** None of them manufactures positive expectancy: the pipeline's PF stays sub-unity and the run still finishes net-negative. The mechanisms bound the loss envelope tightly enough to make the loss immaterial relative to account size, but they do not convert a zero-expectancy random-entry Martingale into a positive-expectancy strategy. For that, either a different entry signal would need to carry genuine directional edge in each regime, or the underlying instrument would need to supply an exploitable structural asymmetry.

**Why the drawdown collapse is structural rather than statistical: a back-of-envelope.** The total drawdown reduction can be decomposed multiplicatively across the three mechanisms because each acts on an independent factor of the loss path. Worst-case session drawdown is approximately:

$$ \text{DD} \;\approx\; (\text{session count}) \times (\text{per-session exposure fraction}) \times (\text{worst-case per-session loss / exposure}) $$

Substituting the §6.6 Mechanism observations as approximate isolated multipliers:

| Mechanism | Factor | Baseline → Pipeline | Isolated DD multiplier |
|---|---|---|---|
| 1: session-volume collapse | session count | 1,619 → 72 | × 0.044 (≈ 23× reduction) |
| 2: position-size compression | peak exposure fraction | 63.7% → 10.3% | × 0.16 (≈ 6× reduction) |
| 3: depth-distribution shift | worst-case absolute per-session loss | -$149 → -$72 | × 0.48 (≈ 2× reduction) |
| **Combined (multiplicative)** | | | **× 0.0034 (≈ 290× reduction in upper-bound DD)** |

The Mechanism 3 multiplier is reported on the absolute dollar loss because that is the quantity entering the drawdown path; on a per-unit-exposure basis the worst-case loss intensifies under the pipeline (-$149/63.7% ≈ -$2.34 per exposure-percentage-point baseline vs -$72/10.3% ≈ -$7.0 pipeline) — a caveat worth naming, but one that does not change the dollar-denominated DD computation above because the per-session exposure compression in Mechanism 2 has already absorbed it.

The empirical 113× reduction in *realised* max drawdown is comfortably *bounded above* by the 290× upper bound the three independent mechanisms imply — confirming that the mechanisms compound rather than cannibalise (which would have produced an empirical reduction *larger* than the bound, indicating double-counting). The 113× / 290× ratio implies that some of the per-mechanism upper bound is consumed by mechanisms partially correlating in practice (e.g., size compression is conditioned on regime confidence, which is also what session-count collapse is gated by). The qualitative result — drawdown well under the baseline — is therefore expected on any OOS window where the learned regime structure is recognisable; the exact 0.75% number is not, but a number "much less than 84.7%" is.

### 6.7 Engine-Controlled Comparison Across Pipeline Approaches

The four-pipeline comparison in Table 5 holds instrument, OOS window, execution engine, cost model, and base strategy fixed; differences in OOS metrics are therefore attributable to the *pipeline layer* — the decision mechanism wrapping the Martingale strategy — rather than to engine, broker, fill, or data choices. Figures 5 and 6 visualise the equity and drawdown trajectories; Figure 7 summarises the maximum-drawdown ranking.

![Figure 5: Equity curve comparison across the four pipelines on EUR-USD 5m, 2025-01-02 to 2026-04-19. Same starting balance, same execution engine, same OANDA cost model. IslandPilot's curve sits within ~$80 of the starting balance throughout; FinRLPilot drifts to -$1,451; GTSBotPilot accumulates -$5,823 of cumulative loss; Baseline collapses to -$8,738.](../figures/Figure5_equity_comparison.png)

![Figure 6: Drawdown trajectory comparison. The shaded area below each curve is the percentage drawdown from the running peak. IslandPilot's drawdown envelope stays within 1% of peak throughout; FinRLPilot reaches 17.97%; GTSBotPilot reaches 58.38%; Baseline reaches 84.73%.](../figures/Figure6_drawdown_comparison.png)

![Figure 7: Maximum drawdown comparison across pipelines. The 20% reference line marks a typical retail-tolerance threshold; only IslandPilot and FinRLPilot stay below it.](../figures/Figure7_maxdd_bars.png)

**Six findings frame the architectural comparison** (full implementation specifications for FinRLPilot and GTSBotPilot in Appendix E):

1. **The capital-preservation gap is large and engine-controlled.** IslandPilot's max drawdown is roughly 24× smaller than FinRLPilot's and 78× smaller than GTSBotPilot's (Table 5; Figure 7), with net-loss ordering matching. None of the three is positive OOS — the contribution is bounded loss under unseen 2025–2026 conditions, not alpha generation. Phrased correctly: this is *competitive capital preservation against in-house implementations of two prominent algorithm families on identical engine substrate*, not outperformance against canonical published systems.

2. **Trade-frequency collapse is the mechanism, not a side-effect.** IslandPilot opens 72 sessions; GTSBot opens 2,812 (39× more); FinRL opens 1,170 (16× more). The pipeline's regime-conditioned gate is doing the work — *not* by improving win rate per session (43% vs 54% vs 78%, the lowest of the three) but by *refusing to trade* in regimes where the underlying Martingale is structurally negative-EV. The contribution is **selectivity at the regime layer**, not improved trading inside any one regime.

3. **Q-learning preset selection (FinRL family) under-utilises its action space on this problem.** FinRLPilot has four trained discrete actions; over 1,170 OOS cycles the policy selects `conservative` 87.9% of the time, `moderate` 8.7%, `tight_tp` 3.3%, and `aggressive` 0%. The Q-policy concentrates on its lowest-leverage preset and never selects the highest-leverage one, yet still loses 14.5% — suggesting the algorithm's expressivity is not the bottleneck. The bottleneck is that *coarse discrete preset selection cannot match the granularity that per-regime continuous parameter evolution provides*.

4. **Hand-set rule-based ablation guards (GTSBot family) require parameterisation that hand-tuning cannot supply.** GTSBot's trend-abort module — designed to cut losses at level ≥ 3 — fired **zero times across 2,812 cycles**, despite L3-L5 contributing -$10,704 of pure loss (level performance: L0–L2 grosses +$4,992; L3–L5 grosses -$10,704). The control surface existed but the activation thresholds were never reached given hand-set parameters. This is the core motivation for *evolving safety thresholds rather than hand-setting them*, which is what IslandPilot does for its 5 pipeline-level genes.

5. **Cost-drag rank-order inverts trade-frequency rank-order at the per-trade level.** Total cost-drag percentages: IslandPilot 19.2%, GTSBot 15.65%, FinRL 10.42%. Per-trade IslandPilot pays the highest spread share — yet preserves the most capital. The pipeline is *not* preserving capital by trading more cheaply; it is preserving capital by trading *less often*, which inverts cost-per-trade economics. This nuance is worth declaring rather than burying.

6. **The session-win-rate paradox anchors the story.** Session win rate is **anti-correlated** with net result across the three Martingale-family implementations: GTSBot 78% / -58%, FinRL 54% / -14.5%, IslandPilot 43% / -0.83%. Winning small sessions repeatedly does not pay for the rare deep-level loss; the only way out is reducing exposure to it. A high win rate is misleading if the loss tail is unbounded — the central motivation for the regime-gate contribution.

**Why the differences are this large.** All three non-baseline pipelines have *some* mechanism for limiting downside on the same Martingale strategy, but the mechanisms differ in expressiveness and conditioning. GTSBot's hand-set thresholds never adapt to the regime; FinRL's Q-learner adapts at coarse preset granularity (4 discrete actions, in practice collapsing to 1); IslandPilot adapts at the per-regime continuous-parameter granularity (5 pipeline + 14 strategy parameters per regime, with 63 regimes). The capital-preservation result is *not* unique to evolutionary computation — both FinRL and GTSBot bound losses better than the unenhanced baseline — but the gap to zero (sub-1% net loss vs 14.5% and 58%) is a property of the per-regime continuous-parameter conditioning that only the island-model GA in this work supplies.

### 6.8 Iteration 2 Architectural Validation (Pre-flight)

The Iteration 2 expanded gene set (§3.4.1 Table 3) is implemented in source but has not been executed at full scale; full-scale evaluation is targeted in §8.1. To confirm GA convergence under the wider 57-gene search space we ran the pre-flight protocol (full specification in Appendix F) on a 3-month training window (2024 Q1) with a 3-month held-out OOS window (2024 Q2). This is **not** a primary performance result and **not** the source of the §6.1 numbers — the short window produces only 3–7 sessions per island, insufficient for per-island profitability inference. Its purpose is to verify that the corrected pipeline (categorical-gene resolver, retired legacy `base_size_pct`, expanded `_TUNABLE_GROUPS`, NaN/inf-safe fitness composite) produces a converging GA rather than degenerate fitness signals.

The Iteration 2 GA produced monotonic mean-fitness improvement across 8 generations (57.9 → 125.6, minimum-fitness 2.5 → 19.9); 13 of 20 top-fitness genomes produced positive OOS P&L on 2024 Q2 with mean L0 win rate 70–80% across the profitable subset; 7 distinct signal modes were selected across the 63 islands. These properties confirm Iteration 2 implementation readiness for full-scale evaluation but do not predict the full-scale 15.5-month OOS result — that question is the central open empirical target of the conference-paper extension. The discrimination power of the 13 / 20 criterion is bounded by an empirical baseline-rate analysis (K = 60 random genomes, 0 OOS-profitable, P[≥10 / 20 random profitable] ≤ 6.6 × 10⁻⁸ at the 95% Wilson upper bound on the random profitability rate) reported in **Appendix F**, which substantiates the criterion's positioning as a structural-bug detector rather than a coin-flip-level threshold.

---
