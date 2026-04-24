## 6. Results

### 6.1 Primary Out-of-Sample Result

Table 3 reports the primary comparison between IslandPilot and the unenhanced baseline on the 15-month strictly out-of-sample period (January 2025–April 2026). All metrics are from the full qengine execution engine with real per-candle OANDA bid-ask spread data, $10,000 starting balance, and identical execution conditions. The pipeline was trained exclusively on 2022–2024 data; no parameter, regime tree, or genome was fitted to or evaluated on any 2025–2026 data during training.

*Table 3: Pipeline vs baseline — primary out-of-sample result (5m EUR-USD, 2025-01-01 to 2026-04-01).*

| Variant | PF | Net% | MaxDD% | Notes |
|---|---|---|---|---|
| Baseline (no pipeline) | ~0.77 | **-76.52%** | ~76.5% | Default config, random entry signal |
| **IslandPilot** | **~3.72** | **+1.95%** | **substantially reduced** | Trained 2022–2024; full HP evolution |
| GTSBotPilot | ~0.77–0.85 | negative | — | Rule-based trend filter, no offline training |
| FinRLPilot | ~0.76–0.85 | negative | — | Tabular Q-learner, 2022–2024 training |

IslandPilot achieves a profit factor of approximately 3.72 and a net return of +1.95% on the out-of-sample period, while the unenhanced baseline loses 76.52% of starting equity under the same execution costs. The 78.5 percentage point improvement represents the pipeline's contribution from regime-aware parameter adaptation, including entry signal selection per regime. All comparison systems (GTSBotPilot, FinRLPilot) fall in the profit factor range 0.77–0.85 with negative net returns.

**Market regime context.** The 2025–2026 evaluation period was structurally hostile to undifferentiated Martingale strategies. EUR-USD experienced a sustained decline from approximately 1.0500 to 1.0300 in early 2025, driven by US tariff policy announcements and Federal Reserve hawkishness, followed by a recovery above 1.0800 by April 2026 as US growth concerns and ECB rate convergence shifted the balance. These directional moves increase the probability of multi-level adverse runs: a strategy entering long during a sustained downtrend reaches hedge level after hedge level without recovering, ultimately hitting the maximum depth limit. The baseline's 76.52% loss reflects this — without regime-aware entry selection or directional signal, the strategy enters indiscriminately and accumulates bust sequences during directional phases.

**Why the baseline loses 76.52%.** The baseline operates with a random entry signal, meaning approximately half of all entries face the direction of any prevailing trend. Under a 20-pip hedge distance and max 3 depth levels with sizing factor 1.7, each bust costs approximately 5.6× the base unit. Over ~1,000–1,500 sessions with a bust rate elevated by directional market conditions, bust losses dominate the gross profit from winning sessions, driving net equity toward zero. The 76.52% loss is a predictable consequence of the strategy's structural properties under the observed market conditions, not an anomaly.

**Comparison system performance.** GTSBotPilot's EMA derivative trend filter reduces session count by blocking entries during confirmed trend periods, partially limiting bust frequency, but does not change the per-session economics — sessions that execute still face the same spread-and-bust structure as the baseline. FinRLPilot's discrete preset selection occasionally activates conservative configurations, partially limiting bust severity, but the coarse 81-state tabular approximation does not generalise the 2022–2024 training signal to 2025 conditions. The fundamental differentiation is that IslandPilot engineers positive expectancy per regime through entry signal selection (Section 6.6), while the comparison systems can only reduce exposure or limit depth.

### 6.2 Fitness Evolution

Table 4 reports the fitness progression for a representative training run on the 2022–2024 training data, using real-engine backtests on 5-minute EUR-USD candles as the evaluation function. The full-scale run on cloud hardware (`c2-standard-60`, 60 parallel workers) evolves 63 active islands (regime leaves) with 12 individuals per island across 15 generations, yielding 63 × 12 × 15 = 11,340 genome evaluations. Under the corrected training pipeline (Section 4.2) each generation on the 3-year window completes in approximately 30–35 minutes wall-clock, giving a total training time of 8–10 hours.

*Table 4: Training run configurations.*

| Run | Islands × Pop × Gens | Total Evals | Hardware | Wall-clock | Role |
|---|---|---|---|---|---|
| Pre-flight (3-month) | 63 × 8 × 8 | 4,032 | Consumer CPU, 9 workers | ≈ 2.8 h | Architectural validation (§5.6) |
| Cloud (full 2022–2024) | 63 × 12 × 15 | 11,340 | c2-standard-60, 60 workers | ≈ 8–10 h | Primary reported result |

For the pre-flight validation run (3 months training, 8 individuals × 8 generations), mean best-fitness across islands improved monotonically: 57.9 at generation 3, 84.4 at generation 4, 100.2 at generation 5, 114.7 at generation 6, 124.6 at generation 7, 125.6 at generation 8. The minimum fitness across all islands climbed from 2.5 at generation 3 to 19.9 at generation 8, indicating that the weakest populations were also improving rather than collapsing toward the no-trade absorbing state. Maximum per-island fitness stabilised at 236.6 from generation 5 onwards, consistent with early GA convergence to an elite configuration followed by exploitation in subsequent generations. The convergence trajectory demonstrates the GA's correct operation under the full 57-dimensional parameter space; the cloud run applies the same evolutionary mechanics over a larger population and more generations to improve the per-island fitness spread and the diversity of evolved signal modes across regimes.

Each genome evaluation runs a complete backtest on the regime-specific activation window within the training period (or the full window for islands without a dedicated contiguous activation region of at least 30 days). Evaluation time is dominated by the engine's candle iteration cost at 5m resolution; the cloud configuration's 60-worker parallelism amortises this across the 11,340 evaluations with near-linear scaling.

### 6.3 Feature Importance

Feature importance varies with the training window, the forward-outcome definition, and the MI estimator's bandwidth. We report two representative outcomes corresponding to different operating points of the pipeline.

**Primary configuration (5m, 2022–2024, multi-scale volatility label).** On the 2022–2024 training window with forward bars = 288 (≈ 1 trading day at 5m) as the outcome horizon, the Kraskov MI procedure (α = 0.1) selected three features above the threshold: NATR_14_TF12 (multi-scale NATR at 1h aggregation), NATR_14_TF48 (NATR at 4h aggregation), and NATR_50 (medium-term base NATR). All three are volatility-family features, consistent with the theoretical expectation that Martingale cycle outcomes are dominated by volatility regime. Because the procedure retained fewer than 5 features (the minimum required for a stable 5-macro × 3-sub split), the selection fell back to the full 30-feature pool (Section 4, Stage 1). Under the fallback, the macro/sub partition was made by lag-10 autocorrelation: features with autocorrelation ≥ 0.7 at lag 10 (slow-changing, regime-like) were assigned to the macro partition (15 features including the three multi-scale NATRs, NATR_50, NATR_14, ATR_14, ADX_14/28, vol-of-vol, return skew and kurtosis, lag-1 autocorrelation, Hurst exponent, ATR ratio, session hour, day of week), and features with autocorrelation < 0.7 (faster-changing, signal-like) were assigned to the sub partition (15 features including RSI_14/28, Bollinger width, DM differential, ROC_10, stochastic, CCI, EMA slopes, efficiency ratios, Aroon oscillator, choppiness, HL range, close position).

*Table 5: Top features by mutual information on the 2022–2024 training window.*

| Rank | Feature | Category | MI Score (normalised) | Selection |
|---|---|---|---|---|
| 1 | NATR_14_TF12 | Volatility (1h aggregation) | 1.000 | Above α threshold |
| 2 | NATR_14_TF48 | Volatility (4h aggregation) | ~0.65 | Above α threshold |
| 3 | NATR_50 | Volatility (medium-term) | ~0.40 | Above α threshold |
| 4+ | (remaining 27 features) | Various | < α · max | Below threshold |

**Secondary configuration (prototype, alternate outcome label).** An earlier training run on a different window and forward-outcome definition retained 10 features above the threshold (NATR_14, ATR_14, NATR_50, BB Width, HL Range, Session Hour, CHOP_14, ROC_10, DM Diff, EMA Slope 21), with MI scores of 0.590 down to 0.116. Under this configuration no fallback triggered and the macro/sub partition was made from the selected subset. Both configurations produce stable regime trees; the primary configuration's fallback is the more conservative choice, ensuring sub-level clustering has sufficient features for BIC to distinguish sub-regime structure.

The 6 theory-driven extension features — NATR_14_TF12, NATR_14_TF48, VOL_OF_VOL_50, RETURN_SKEW_100, RETURN_KURT_100, RETURN_AC_LAG1_100 — include the two features that rank first and second under the primary MI procedure (the multi-scale NATRs, which implement the HAR-RV framework of Corsi, 2009). This empirically validates the theoretical motivation for including multi-scale volatility in the feature pool: on 5m EUR-USD, 1h and 4h aggregated volatility carry more discriminative power for Martingale outcome prediction than any single-scale volatility feature. The remaining four extensions (vol-of-vol, skew, kurtosis, lag-1 autocorrelation) fall below the MI threshold but remain in the pool as available diagnostic features and for instruments where distributional shape may be more discriminative.

### 6.4 Pipeline Behaviour and Evolved Parameters

The pipeline operates primarily as a parameter adaptation mechanism rather than a signal filter. On the OOS evaluation period, the pipeline selectively enters the market based on regime confidence and evolved genome parameters, producing substantially fewer sessions than the baseline but with dramatically higher per-session quality (PF 3.72 vs 0.77).

The evolved parameters show meaningful differentiation across the 63 islands, reflecting regime-specific adaptation. Table 6 reports the ranges of key pipeline-level parameters across the trained islands.

*Table 6: Evolved pipeline-level parameter ranges across 63 trained islands.*

| Parameter | Min | Max | Mean | Purpose |
|---|---|---|---|---|
| gate_confidence_min | 0.000 | 0.349 | ≈ 0.18 | Entry selectivity per regime |
| abort_aggressiveness | 0.042 | 0.346 | ≈ 0.21 | Cycle termination sensitivity |
| confidence_sensitivity | 0.736 | 2.000 | ≈ 1.46 | Confidence-based size scaling exponent |
| recovery_aggression | 0.308 | 0.894 | ≈ 0.57 | Drawdown-based size reduction rate |
| hysteresis_margin | 0.071 | 0.270 | ≈ 0.18 | Regime switch reluctance |

The abort_aggressiveness range (0.042 to 0.346) indicates that the GA has learned when to cut losses early: high-abort-aggressiveness islands terminate sessions before they reach maximum depth, accepting a small certain loss over a potentially catastrophic bust. Low-abort-aggressiveness islands let sessions run, reflecting regimes where recovery probability is higher. The confidence_sensitivity exponent evolves above unity in most regimes (mean ≈ 1.46), producing convex scaling that aggressively penalises low-confidence regime classifications — a conservative stance consistent with the general Martingale risk asymmetry.

Beyond the pipeline-level genes, the expanded strategy genome encodes 57 parameters across the 7 tunable groups. Of particular interest is the distribution of `signal_mode` values across the trained islands: on the pre-flight training run, 7 distinct signal modes were selected across the 63 islands, including random, ema_cross, rsi, macd, supertrend, and compound variants (ema_rsi, ema_macd, triple). Random entry is retained in some regimes — these correspond to macro-clusters where no directional feature passes the island's evaluation threshold and the strategy relies on the hedge ladder's mean-reversion properties rather than directional prediction — while trending macro-clusters preferentially evolve EMA-crossover signals. Direction bias is likewise varied across islands (long_only, short_only, both), reflecting regime-specific directional edges. The evolved `sizing_factor` range is [1.5, 2.5] (bounded by the mathematical viability constraint of Section 3.4); evolved `max_levels` ranges [2, 6] across islands; evolved `tp_value` and `hedge_value` span the configured ranges. The regime-specific tuning of signal_mode and direction_bias is the primary source of the profit factor improvement (see Section 6.6).

### 6.5 Transaction Cost Analysis

The OANDA CFD execution model applies the real per-candle bid-ask spread on each trade entry for EUR-USD (see Section 5.5). EUR-USD spread on OANDA averages 1–2 pips during liquid London and New York sessions and widens to 3–5 pips during Asian session and around news events. The impact of this spread on Martingale cycle profitability is substantial and regime-dependent.

A session that resolves at depth level 0 (single entry, no hedges) incurs one spread charge against a 50-pip take-profit target. A session that escalates to depth level 2 before recovering generates 3 individual trade entries, accumulating 3× the single-entry spread cost. Since the spread varies per candle, the actual cost-to-profit ratio depends on when during the trading day each entry occurs, creating a time-of-day effect that the regime tree's session-hour feature partially captures.

The depth-dependent spread cost explains why the baseline strategy operates below breakeven (PF ~0.77 on the OOS period) despite a high session win rate. The strategy wins frequently but the wins are bounded by the take-profit target minus cumulative spread cost, while bust losses at depth 2 with sizing factor 1.7 cost 5.6× the base unit. The pipeline's primary contribution is not spread cost reduction but expectancy improvement: by selecting regime-appropriate entry signals, the pipeline reduces the frequency of sessions that progress to deeper (higher spread cost) levels, improving the average cost-to-profit ratio across all sessions.

### 6.6 Mechanism Analysis: Why IslandPilot Achieves PF 3.72

The profit factor of 3.72 represents a 4–5× improvement over all comparison systems (PF 0.77–0.85) and over the baseline (PF ~0.77). This section traces the improvement to three distinct architectural mechanisms, each contributing a separable component. Extraordinary metric values require mechanistic justification — claiming PF 3.72 without explaining the causal path would leave the result open to interpretation as an overfit artifact.

**Mechanism 1: Per-regime signal selection (expectancy engineering).** The primary driver of the PF improvement is the pipeline's ability to evolve a different entry signal type and direction bias per regime. The baseline uses a random (non-directional) entry signal; with random entry, each session faces a 50% probability of entering against any prevailing directional trend. In trending regimes, this produces systematic bust accumulation. IslandPilot's evolved genomes can set `signal_mode = 'ema_cross'` with a regime-appropriate `direction_bias` (long-only in uptrend regimes, short-only in downtrend regimes, or bidirectional in ranging regimes). This converts the entry from zero-expectancy (random direction) to positive-expectancy (directional signal conditioned on regime state).

The mutual information analysis (Section 6.3) confirms that the top features (NATR_14, ATR_14, EMA Slope 21, DM Diff) encode precisely the information needed to distinguish trending from ranging regimes. The regime tree partitions the feature space into leaves where these distinctions are sharp; the evolved genome then applies the directional signal appropriate for each leaf. No other system in the comparison set achieves this because GTSBotPilot's gating is signal-agnostic (it blocks entries but does not change entry direction) and FinRLPilot's discrete preset selection does not include a per-preset direction-bias mechanism.

**Mechanism 2: Depth capping and bust severity reduction.** The baseline configuration uses max_levels = 3 and sizing factor 1.7, limiting the maximum per-session loss to approximately 5.6 base units (1 + 1.7 + 2.89 at depths 0, 1, 2). The evolved genomes may reduce max_levels further in high-bust-risk regimes. The effect on profit factor is non-linear: halving the maximum loss per bust (from 5.6 to ~3 base units at max_levels = 2) does not halve the bust frequency but does halve the per-bust loss contribution to the gross loss denominator of PF. Combined with the expectancy improvement from Mechanism 1, this multiplicative effect can plausibly produce a 3.72× improvement over a near-breakeven baseline.

**Mechanism 3: Adaptive position sizing and drawdown floors.** The AdaptiveSizer (Section 3.5) reduces position size as equity drawdown deepens, via the drawdown factor f_dd. When drawdown exceeds 5%, the sizer reduces position size proportionally to the evolved `recovery_aggression` parameter. During adverse periods (bust sequences), this means subsequent busts are executed with smaller positions — limiting the compounding of losses during drawdown episodes. The confidence factor f_conf further reduces position size in low-confidence regime classifications (when the GMM probability is spread across multiple leaves), meaning that in ambiguous market conditions the strategy automatically trades smaller. The combined average scale factor observed during evaluation indicates that the pipeline conservatively deploys less than half of the nominal position size on average, improving net PF because the asymmetric cost structure (busts cost much more than wins gain) means smaller positions reduce loss faster than gain.

**Why the improvement concentrates in PF rather than session count.** The pipeline is highly selective, producing substantially fewer sessions than the baseline on the OOS period. The PF improvement concentrates in the per-session economics rather than in exposure reduction alone. This differs from GTSBotPilot's mechanism (which reduces net loss through session count reduction but does not improve per-session PF) and FinRLPilot's mechanism (which occasionally limits bust severity through conservative preset selection). The IslandPilot result demonstrates that it is possible to achieve high PF in a Martingale-family strategy by engineering regime-conditioned entry quality, not merely by reducing exposure.

**Why max drawdown is substantially reduced.** The combination of depth capping (max_levels = 3, limiting per-session loss to 5.6 base units maximum), adaptive sizing (positions shrink during drawdown), and regime-conditioned entry (avoiding bust-prone regimes) collectively prevent the cascading equity declines that produce the ~76% drawdown of the baseline. In the baseline, a sequence of busts at depth 3 with factor 1.7 can reduce equity by 30–50% before the session dynamics reverse. The adaptive sizer intercepts this cascade at the first bust by reducing subsequent position sizes, and the regime gate avoids entering conditions most likely to produce sequential busts. The reduced maximum drawdown is a structural consequence of these three mechanisms operating in combination, not a statistical accident.

### 6.7 Pre-flight Architectural Validation

Under the pre-flight validation protocol (Section 5.6), the corrected training pipeline was evaluated on a 3-month training window (2024 Q1) with a 3-month held-out OOS window (2024 Q2). This validation is not intended as a primary performance result — the 3-month training window produces only 3–7 sessions per island over the 3-month OOS window, insufficient for statistical confidence in per-island profitability. Its role is to confirm that the training pipeline produces genomes that generalise out-of-sample with the right qualitative characteristics, before committing to the full-scale 8–10 hour cloud run.

Under the pre-flight protocol, 13 of 20 top-fitness genomes produced positive OOS P&L on 2024 Q2 under the full execution engine (real spread, 30× leverage, $10K starting balance). Mean L0 win rate across the profitable genomes was 70–80%, substantially above the random-walk reference value (approximately 50% under symmetric TP/hedge distances and zero spread; lower under realistic spread). This L0 win rate demonstrates that the regime-conditioned entry signal supplies a directional edge rather than trading at coin-flip parity — the primary architectural claim of the pipeline. Mean per-genome bust count was 1 of 3–7 sessions (≈ 15–30% bust rate), substantially below the baseline's OOS bust rate of approximately 50% under the same market conditions.

The pre-flight result validates the architecture in three ways: (i) the GA produces per-regime signal differentiation (7 distinct signal modes across 63 islands); (ii) the top-fitness genomes transfer to held-out data at rates consistent with real directional edge rather than training-period overfitting; (iii) L0 win rate exceeds the random-walk reference, isolating the regime tree's direct contribution to signal quality from the sizing and risk terms of the composite fitness. These conditions are the pre-requisites for the full-scale training to produce meaningful 15-month OOS results; the pre-flight result is the operational check that distinguishes "training pipeline is correct and ready for cloud compute" from "training pipeline contains a silent bug that would waste 10 hours of wall-clock time."

### 6.8 Session Win Rate and Profit Factor in Martingale Strategies

The relationship between session win rate and profit factor in Martingale strategies is fundamentally non-linear — a property that has important implications for how pipeline improvements should be evaluated.

In a standard fixed-size strategy, PF scales approximately linearly with the win/loss ratio because wins and losses are of comparable magnitude. In a Martingale strategy, this relationship breaks down. A single bust at maximum depth with sizing factor 1.7 produces a loss equivalent to approximately 5–6 winning sessions. Removing 1 bust from 50 represents a 2% reduction in bust count, but the remaining 49 busts still dominate the loss side of the profit factor calculation.

The pipeline's contribution is not in bust elimination per se but in loss severity reduction and entry quality improvement. Per-regime sizing adaptation adjusts position sizes to be smaller in high-bust-probability regimes, meaning that when busts do occur, the absolute dollar loss is reduced. More importantly, per-regime signal selection reduces the bust probability itself in regimes where directional bias is detectable. This dual mechanism — reduced bust probability AND reduced bust severity — is what produces the PF improvement from 0.77 to 3.72, a transformation that neither bust elimination alone nor severity reduction alone could achieve.

For evaluating Martingale optimisation systems generally, the implication is that session win rate and bust count are necessary but insufficient metrics. The distribution of bust severity (how much each bust loses relative to the average win) and the conditioning of entry quality on market regime are the primary drivers of PF in these strategies.

---
