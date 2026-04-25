## 6. Results

### 6.1 Primary Out-of-Sample Result

Table 5 reports the primary comparison on the 15.5-month strictly out-of-sample period (Jan 2025 to mid-Apr 2026), under identical execution conditions: $10,000 starting balance and the qengine production engine with real per-candle OANDA spread, swap, and slippage. The pipeline was trained exclusively on 2022–2024; no 2025–2026 data entered fitting of any genome, regime tree, or parameter.

*Table 5: Pipeline vs baseline, primary out-of-sample result (5m EUR-USD, 2025-01-01 to 2026-04-19).*

| Metric | Baseline | IslandPilot | Delta |
|---|---|---|---|
| Sessions | 1,619 | 72 | -96.0% |
| Trades | 5,238 | 245 | -95.3% |
| Profit factor | 0.717 | 0.877 | +0.160 (+22%) |
| Net profit % | -87.38% | -0.83% | +86.55 pp |
| Max drawdown % | 84.73% | 0.75% | -83.98 pp (≈113× smaller) |
| Annual return | -89.65% | -0.91% | +88.74 pp |
| Session win rate | 83.3% | 43.1% | -40.2 pp |
| Bust rate | 16.8% | 50.0% | +33.2 pp |
| Level-0 win rate | 26.4% | 5.6% | -20.8 pp |
| Peak equity usage | 63.7% | 10.3% | -53.4 pp |
| Worst bust P&L | -$148.99 | -$71.79 | +$77.20 |
| Cost drag | 29.9% | 19.2% | -10.7 pp |
| Gross profit | +$21,432 | +$475 | (scale-adjusted) |
| Gross loss | -$29,893 | -$542 | (scale-adjusted) |

Three findings dominate Table 5: drawdown collapses by approximately two orders of magnitude (84.73% → 0.75%), peak equity usage falls from 63.7% to 10.3%, and profit factor rises from 0.717 to 0.877 while remaining sub-unity. The pipeline does not produce positive absolute expectancy: PF < 1.0 means gross losses still exceed gross profits, and the run finishes at -0.83% rather than above zero. The honest reading: regime-structured evolutionary optimisation cannot manufacture directional alpha absent from a random-entry Martingale on a mean-zero spot FX signal. The contribution is capital preservation — the approach bounds the drawdown envelope and collapses peak exposure enough to convert a catastrophic strategy into a near-breakeven one.

**Market regime context.** The 2025 to 2026 evaluation period was structurally hostile to undifferentiated Martingale strategies. EUR-USD experienced a sustained decline from approximately 1.0500 to 1.0300 in early 2025, driven by US tariff policy announcements and Federal Reserve hawkishness, followed by a recovery above 1.0800 by April 2026 as US growth concerns and ECB rate convergence shifted the balance. These directional moves increase the probability of multi-level adverse runs: a strategy entering long during a sustained downtrend reaches hedge level after hedge level without recovering, ultimately hitting the maximum depth limit. The baseline's 84.73% drawdown and 87.38% net loss reflect this: without regime-aware selectivity or depth discipline, the strategy enters indiscriminately and accumulates catastrophic depth-5 busts during directional phases (271 depth-5 busts account for the -$12,784 loss that drives the baseline's net result).

**Why the baseline loses 87.4%.** The baseline operates the `'original'` preset with a random entry signal (signal_mode='none', long_only) under a 10-pip hedge distance, 20-pip take-profit, 6 maximum depth levels (depths 0 to 5), and geometric sizing with factor 2.0. A depth-5 bust costs the cumulative geometric sum 1 + 2 + 4 + 8 + 16 + 32 = 63 base units. Across 1,619 sessions, 272 busts occur (16.8% bust rate), with 271 reaching depth 5 (depth distribution table in Section 6.4). These deep busts contribute approximately -$12,784 to the gross loss denominator, overwhelming the +$4,323 in gross profit from depths 0 to 4 and driving net equity from $10,000 to $1,262.

**Comparison systems.** Comparison against GTSBotPilot (Rundo et al., 2019) and FinRLPilot (Liu et al., 2020) on this exact OOS window and cost model is deferred to Section 7 once honest re-run values are available. The primary result here establishes the baseline-to-pipeline comparison alone, which is the load-bearing scientific claim.

### 6.2 Fitness Evolution

The Iteration 1 training run on cloud hardware (Google Cloud `c2-standard-60` spot instance, 60 vCPU / 240 GB RAM, 60 parallel workers, europe-west2-c) evolves 63 active islands (regime leaves, grouped into 10 macro-clusters) with 10 individuals per island across 20 generations, yielding 63 × 10 × 20 = 12,600 real-engine genome evaluations. Wall-clock was 10 hours 33 minutes (37,966 seconds), with per-generation mean 1,888 s (approximately 31.5 minutes) and per-generation range 1,843 s to 1,917 s, indicating stable throughput across the run.

*Table 6: Training run configurations.*

| Run | Islands × Pop × Gens | Total Evals | Hardware | Wall-clock | Role |
|---|---|---|---|---|---|
| **Iteration 1 cloud (full 2022 to 2024)** | 63 × 10 × 20 | 12,600 | c2-standard-60 (spot), 60 workers | 10 h 33 min | **Primary reported result (Section 6.1, 6.4–6.6)** |
| Iteration 2 pre-flight (3-month) | 63 × 8 × 8 | 4,032 | Consumer CPU, 9 workers | ≈ 2.8 h | Architectural validation only (§5.6, §6.7); not the source of §6.1 numbers |

Iteration 1's per-generation fitness trajectory across the 20-generation cloud run shows the canonical mean best-fitness climbing from 55.96 at generation 1 (min 51.53, max 58.98) to 58.87 at generation 20 (min 58.09, max 59.20), with sibling migration firing every 4 generations (at generations 4, 8, 12, 16, 20). The min-fitness rise from 51.5 to 58.1 indicates that the weakest islands converged toward the elite configuration over the run rather than diverging — a signal that the per-island GA dynamics produced consistent rather than scattered evolution under the 3-group, 20-gene search space.

For Iteration 2 architectural validation (Section 5.6), the GA convergence trajectory on the 3-month consumer-CPU pre-flight is described in §6.7. The two trajectories should not be conflated: they characterise different iterations of the pipeline operating on different windows with different population sizes and different generation budgets.

Each genome evaluation runs a complete backtest on the regime-specific activation window within the training period (or the full window for islands without a dedicated contiguous activation region of at least 30 days). Evaluation time is dominated by the engine's candle iteration cost at 5m resolution; the cloud configuration's 60-worker parallelism amortises this across the 12,600 evaluations with near-linear scaling. On the Iteration 1 cloud run, no leaf accumulated a 30-day contiguous window under the fallback feature partition, so all 63 islands evolved on the full 2022–2024 training window. The fitness-isolation mechanism remains available in code for future windows where regime-specific contiguous activation regions do form.

### 6.3 Feature Importance

Feature importance varies with the training window, the forward-outcome definition, and the MI estimator's bandwidth. We report two representative outcomes corresponding to different operating points of the pipeline.

**Primary configuration (5m, 2022–2024, multi-scale volatility label).** On the 2022–2024 training window with forward bars = 288 (≈ 1 trading day at 5m) as the outcome horizon, the Kraskov MI procedure (α = 0.1) selected three features above the threshold: NATR_14_TF12 (multi-scale NATR at 1h aggregation), NATR_14_TF48 (NATR at 4h aggregation), and NATR_50 (medium-term base NATR). All three are volatility-family features, consistent with the theoretical expectation that Martingale cycle outcomes are dominated by volatility regime. Because the procedure retained fewer than 5 features (the minimum required for a stable 5-macro × 3-sub split), the selection fell back to the full 30-feature pool (Section 4, Stage 1). Under the fallback, the macro/sub partition was made by lag-10 autocorrelation: features with autocorrelation ≥ 0.7 at lag 10 (slow-changing, regime-like) were assigned to the macro partition (15 features including the three multi-scale NATRs, NATR_50, NATR_14, ATR_14, ADX_14/28, vol-of-vol, return skew and kurtosis, lag-1 autocorrelation, Hurst exponent, ATR ratio, session hour, day of week), and features with autocorrelation < 0.7 (faster-changing, signal-like) were assigned to the sub partition (15 features including RSI_14/28, Bollinger width, DM differential, ROC_10, stochastic, CCI, EMA slopes, efficiency ratios, Aroon oscillator, choppiness, HL range, close position).

*Table 7: Top features by mutual information on the 2022–2024 training window.*

| Rank | Feature | Category | MI Score (normalised) | Selection |
|---|---|---|---|---|
| 1 | NATR_14_TF12 | Volatility (1h aggregation) | 1.000 | Above α threshold |
| 2 | NATR_14_TF48 | Volatility (4h aggregation) | ~0.65 | Above α threshold |
| 3 | NATR_50 | Volatility (medium-term) | ~0.40 | Above α threshold |
| 4+ | (remaining 27 features) | Various | < α · max | Below threshold |

**Secondary configuration (prototype, alternate outcome label).** An earlier training run on a different window and forward-outcome definition retained 10 features above the threshold (NATR_14, ATR_14, NATR_50, BB Width, HL Range, Session Hour, CHOP_14, ROC_10, DM Diff, EMA Slope 21), with MI scores of 0.590 down to 0.116. Under this configuration no fallback triggered and the macro/sub partition was made from the selected subset. Both configurations produce stable regime trees; the primary configuration's fallback is the more conservative choice, ensuring sub-level clustering has sufficient features for BIC to distinguish sub-regime structure.

The 6 theory-driven extension features (NATR_14_TF12, NATR_14_TF48, VOL_OF_VOL_50, RETURN_SKEW_100, RETURN_KURT_100, RETURN_AC_LAG1_100) include the two features that rank first and second under the primary MI procedure (the multi-scale NATRs, which implement the HAR-RV framework of Corsi, 2009). This empirically validates the theoretical motivation for including multi-scale volatility in the feature pool: on 5m EUR-USD, 1h and 4h aggregated volatility carry more discriminative power for Martingale outcome prediction than any single-scale volatility feature. The remaining four extensions (vol-of-vol, skew, kurtosis, lag-1 autocorrelation) fall below the MI threshold but remain in the pool as available diagnostic features and for instruments where distributional shape may be more discriminative.

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

*Table 9: Evolved pipeline-level parameter ranges across 63 trained islands.*

| Parameter | Min | Max | Mean | Purpose |
|---|---|---|---|---|
| gate_confidence_min | 0.000 | 0.349 | ≈ 0.18 | Entry selectivity per regime |
| abort_aggressiveness | 0.042 | 0.346 | ≈ 0.21 | Cycle termination sensitivity |
| confidence_sensitivity | 0.736 | 2.000 | ≈ 1.46 | Confidence-based size scaling exponent |
| recovery_aggression | 0.308 | 0.894 | ≈ 0.57 | Drawdown-based size reduction rate |
| hysteresis_margin | 0.071 | 0.270 | ≈ 0.18 | Regime switch reluctance |

The abort_aggressiveness range (0.042 to 0.346) indicates that the GA has learned when to cut losses early: high-abort-aggressiveness islands terminate sessions before they reach maximum depth, accepting a small certain loss over a potentially catastrophic bust. Low-abort-aggressiveness islands let sessions run, reflecting regimes where recovery probability is higher. The confidence_sensitivity exponent evolves above unity in most regimes (mean ≈ 1.46), producing convex scaling that aggressively penalises low-confidence regime classifications, a conservative stance consistent with the general Martingale risk asymmetry.

Beyond the pipeline-level genes, the Iteration 1 strategy genome encodes 14 evolved parameters across three groups (5 General, 6 Grid/Hedge, 3 Take Profit; see Section 3.4 Table 2). The cloud-trained population exhibits meaningful per-island variation in these genes: evolved `max_levels` ranges within [2, 6] across islands under Iteration 1's bound (the depth distribution above shows pipeline sessions reaching depth 6 because the strategy interprets `max_levels = N` as "open L0 plus up to N hedges", so an island that evolves `max_levels = 6` can reach session depth 6); evolved `sizing_factor` distributes within [1.2, 2.0] under Iteration 1's bound; evolved `tp_value` and `hedge_value` span their configured ranges; mode genes evolve preferences for one of `fixed_pips`, `atr_based`, `bucket_pct`, or `risk_reward` per regime. The load-bearing controls for the observed drawdown collapse are exactly these depth-related strategy genes (`max_levels`, `sizing_factor`, `hedge_value`) combined with the pipeline-level genes (`gate_confidence_min`, `abort_aggressiveness`, `recovery_aggression`). Iteration 1 has no `signal_mode` or `direction_bias` gene; entry direction is therefore not regime-conditioned in the cloud-trained model. The mechanism analysis in §6.6 follows directly from this fact.

The Iteration 2 design endpoint (Section 3.4 Table 3, Section 5.2) extends the genome to include `signal_mode`, `direction_bias`, and per-regime risk-management and position-management parameters. Whether these widen the OOS performance envelope beyond Iteration 1's capital-preservation result is one of the open empirical questions identified for the conference-paper extension.

### 6.5 Transaction Cost Analysis

The OANDA CFD execution model applies the real per-candle bid-ask spread on each trade entry for EUR-USD (see Section 5.5). EUR-USD spread on OANDA averages 1–2 pips during liquid London and New York sessions and widens to 3–5 pips during Asian session and around news events. The impact of this spread on Martingale cycle profitability is substantial and regime-dependent.

A session that resolves at depth level 0 (single entry, no hedges) incurs one spread charge against the baseline's 20-pip take-profit target. A session that escalates to depth level 2 before recovering generates 3 individual trade entries, accumulating 3× the single-entry spread cost. Since the spread varies per candle, the actual cost-to-profit ratio depends on when during the trading day each entry occurs, creating a time-of-day effect that the regime tree's session-hour feature partially captures.

The depth-dependent spread cost explains why the baseline strategy operates below break-even (PF 0.717 on the OOS period) despite an 83.3% session win rate. The strategy wins frequently but the wins are bounded by the take-profit target minus cumulative spread cost, while bust losses at depth 5 with sizing factor 2.0 cost the cumulative geometric sum of 63 base units. The pipeline's total cost drag is 19.2% against the baseline's 29.9%, a 10.7 percentage-point reduction. This cost saving is a consequence of session-count collapse (72 vs 1,619 sessions means 96% fewer spread-incurring entries) rather than per-session cost engineering. The pipeline is not better at avoiding spread cost per session; it simply trades far less often.

### 6.6 Mechanism Analysis: What the Pipeline Actually Does

The headline result, 87.38% baseline net loss collapsing to 0.83% pipeline net loss under identical cost conditions, requires a mechanistic explanation. A plausible-sounding narrative would attribute the improvement to per-regime signal engineering: the pipeline picks better entries in each regime, avoiding bust-prone conditions, and therefore wins more often. That narrative is false under the honest OOS data. The metrics that would indicate an entry-quality mechanism move in the opposite direction:

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

**Mechanism 1: Session-volume collapse (regime-gated selectivity).** The pipeline opens 72 sessions against the baseline's 1,619, a 96% reduction. The reduction is produced by the regime inferencer's hysteresis-gated entry (Section 3.6) combined with the per-island `gate_confidence_min` parameter evolved by the GA (mean ≈ 0.18 across islands). In most candles of the OOS period, either the regime confidence is below the evolved threshold or the currently-classified regime has an evolved genome that prohibits entry under current feature values. The pipeline sits out most of the market. This is the dominant contribution to the reduced drawdown: each avoided session is an avoided opportunity to accumulate a depth-5 bust.

**Mechanism 2: Position-size compression (peak-exposure bounding).** Peak equity usage falls from 63.7% (baseline) to 10.3% (pipeline), a reduction of 53.4 percentage points in absolute terms and 84% in relative terms. The AdaptiveSizer (Section 3.5) reduces position size via three multiplicative factors: confidence (f_conf), drawdown (f_dd), and base size (f_base). The evolved `confidence_sensitivity` exponent (mean ≈ 1.46 across islands) produces convex scaling that aggressively penalises regimes where GMM posterior probability is spread across multiple leaves; the evolved `recovery_aggression` parameter (mean ≈ 0.57) scales position down during drawdown. The combined effect is that the pipeline rarely commits more than ten percent of equity to open exposure, even when it does open sessions. A baseline depth-5 bust at full sizing costs up to -$148.99 (worst-case observed); the pipeline's worst-case bust at compressed sizing is -$71.79, a 52% reduction in worst-case loss magnitude.

**Mechanism 3: Catastrophic-chain avoidance (depth distribution shift).** The baseline's loss is driven by 271 depth-5 busts (Section 6.1). The pipeline's 72 sessions show a shallower depth distribution: depth 5 accounts for only 2 sessions (2.8%) and depth 6 for 4 sessions (5.6%). The majority of pipeline sessions resolve at depths 1 to 4 (62 of 72, or 86%). This shift reflects both the evolved `max_levels` parameter per island (Iteration 1 bound range [2, 6]; some islands evolved to the upper bound and produced the depth-6 sessions observed in Table 8) and the evolved `abort_aggressiveness` (mean ≈ 0.21), which terminates sessions early in regimes where continued hedging is evaluated as having low recovery probability. The practical effect is that when pipeline sessions do bust, they bust shallow rather than deep.

**What the three mechanisms together do not do.** None of these mechanisms manufactures positive expectancy. The pipeline's profit factor remains 0.877, below break-even. The pipeline still loses money on the OOS window (-0.83% net). The three mechanisms collectively bound the loss envelope tightly enough that the loss is immaterial relative to account size (under one percentage point over 15.5 months), but they do not convert a zero-expectancy random-entry Martingale into a positive-expectancy strategy. For that, either a different entry signal would need to carry genuine directional edge in each regime, or the underlying instrument would need to supply an exploitable structural asymmetry.

**Why the drawdown collapse is a structural rather than statistical result.** Mechanisms 1 to 3 operate independently and compound multiplicatively on the drawdown path. Selectivity removes most paths to drawdown (fewer sessions). Size compression reduces the per-session equity impact. Depth-distribution shift removes the tail of the per-session loss distribution. A 113-fold drawdown reduction is therefore not a statistical artefact of a lucky OOS window; it is the structural consequence of three risk-bounding mechanisms operating in combination. The reproducibility of this specific 0.75% number on a different OOS window is not guaranteed, but the qualitative result (drawdown under one percent against a baseline that loses more than eighty percent) is expected to hold across any window where the learned regime structure is recognisable.

### 6.7 Iteration 2 Architectural Validation (Pre-flight)

The Iteration 2 expanded gene set (Section 3.4 Table 3) is implemented in source but has not been executed at scale on the full 2022–2024 window. Its full-scale evaluation is identified in §8.1 as a target of the conference-paper extension this work is heading towards. To confirm that the Iteration 2 pipeline produces genomes that converge correctly under the wider 57-gene search space — separately from any claim about the §6 OOS numbers — we ran a short architectural-validation protocol on a 3-month training window (2024 Q1) with a 3-month held-out OOS window (2024 Q2), under the pre-flight validation harness described in Section 5.6.

This validation is **not** a primary performance result and is **not** the source of the §6 numbers. The 3-month training window produces only 3 to 7 sessions per island over the 3-month OOS window, insufficient for statistical confidence in per-island profitability. Its purpose is to verify that the corrected pipeline (categorical-gene resolver, retired legacy `base_size_pct`, expanded `_TUNABLE_GROUPS`, NaN/inf-safe fitness composite) produces a converging GA over the wider search space rather than degenerate fitness signals — the failure mode that would otherwise consume cloud compute without producing usable genomes.

Under this protocol, the Iteration 2 GA produced monotonic mean-fitness improvement across 8 generations (57.9 → 125.6, with minimum-fitness rising 2.5 → 19.9), 13 of 20 top-fitness genomes produced positive OOS P&L on 2024 Q2 with mean L0 win rate 70% to 80% across the profitable subset, and 7 distinct signal modes were selected across the 63 islands. These observations are properties of the Iteration 2 implementation under a short validation horizon. The §6 numbers, in contrast, are produced by the Iteration 1 cloud-trained model on a 15.5-month production OOS window; the two results characterise different iterations of the pipeline and are not directly comparable.

The Iteration 2 architectural-validation result is reported here so that reviewers can locate the evidence that the wider-search pipeline is implementation-ready. Whether Iteration 2's full-scale evaluation reproduces the qualitative pre-flight characteristics (per-regime signal differentiation, fitness convergence) at the production scale is one of the empirical questions the conference-paper extension is designed to answer.

---
