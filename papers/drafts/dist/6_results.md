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

Table 4 reports the fitness progression across 3 evolutionary generations on the 2022–2024 training data, using real-engine backtests on 5-minute EUR-USD candles as the evaluation function. The evolution ran across 56 active islands (regime leaves) with 5 individuals per island, for a total of 840 genome evaluations.

*Table 4: Fitness progression across 3 generations (56 active islands, 5 individuals each).*

| Generation | Total Evaluations | Approx. Time | Notes |
|---|---|---|---|
| 1 | 280 | ~2.6 hours | Initial random populations |
| 2 | 280 | ~2.6 hours | Post-selection, crossover, mutation |
| 3 | 280 | ~2.6 hours | Final generation |
| **Total** | **840** | **7 hours 46 min** | Regime tree saved 14:44, evolver saved 22:30 (April 22) |

Each genome evaluation runs a complete backtest on the regime-specific activation window within the 3-year training period, averaging approximately 33 seconds per evaluation on a consumer CPU. The 7 hour 46 minute wall-clock time covers the full pipeline: regime tree construction (feature computation, mutual information selection, hierarchical GMM fitting) followed by 840 sequential genome evaluations.

The modest number of generations (3) reflects the computational cost of real-engine evaluation balanced against the empirical finding (Section 7.4) that even this minimal budget produces transferable out-of-sample improvement. The 56-island structure means each island receives only 15 evaluations total (3 generations × 5 individuals), which is sufficient for the 6-gene pipeline-internal parameters plus the strategy-level parameters to converge to a regime-appropriate configuration, given that the initial random population already spans the bounded parameter space.

### 6.3 Feature Importance

*Table 5: Selected features ranked by mutual information with cycle profitability.*

| Rank | Feature | Category | MI Score |
|---|---|---|---|
| 1 | NATR_14 | Volatility | 0.590 |
| 2 | ATR_14 | Volatility | 0.531 |
| 3 | NATR_50 | Volatility | 0.338 |
| 4 | Bollinger Width | Volatility | 0.275 |
| 5 | HL Range Norm | Structure | 0.241 |
| 6 | Session Hour | Structure | 0.151 |
| 7 | CHOP_14 | Choppiness | 0.123 |
| 8 | ROC_10 | Momentum | 0.121 |
| 9 | DM Diff | Trend | 0.116 |
| 10 | EMA Slope 21 | Trend | 0.116 |

Mutual information feature selection retains 10 features from the pool of 30, with a threshold of alpha = 0.1 × max_score. Volatility-class features occupy 4 of the top 5 positions, consistent with the observation that grid-hedged Martingale strategies are primarily sensitive to volatility regime — the strategy's bust probability is dominated by sustained directional moves, which manifest as elevated NATR and ATR. The two trend features (DM Diff, EMA Slope 21) that pass the threshold but rank lowest encode the directional information that the evolved genomes exploit for entry signal selection (Section 6.6, Mechanism 1).

The 6 theory-driven extension features (NATR_14_TF12, NATR_14_TF48, VOL_OF_VOL_50, RETURN_SKEW_100, RETURN_KURT_100, RETURN_AC_LAG1_100) did not pass the mutual information threshold for the 2022–2024 training data. This does not invalidate their theoretical motivation (Section 3.1) — it indicates that for the specific task of Martingale cycle outcome prediction on EUR-USD at 5m resolution, the base 24 features already capture the discriminative information that these extensions target. The extensions remain in the feature pool for future evaluations on other instruments or timeframes where distributional shape or multi-scale volatility may be more discriminative.

### 6.4 Pipeline Behaviour and Evolved Parameters

The pipeline operates primarily as a parameter adaptation mechanism rather than a signal filter. On the OOS evaluation period, the pipeline selectively enters the market based on regime confidence and evolved genome parameters, producing substantially fewer sessions than the baseline but with dramatically higher per-session quality (PF 3.72 vs 0.77).

The evolved parameters show meaningful differentiation across the 56 islands, reflecting regime-specific adaptation. Table 6 reports the ranges of key pipeline-level parameters across the trained islands.

*Table 6: Evolved pipeline parameter ranges across 56 trained islands.*

| Parameter | Min | Max | Mean | Purpose |
|---|---|---|---|---|
| gate_confidence_min | 0.000 | 0.349 | ~0.18 | Entry selectivity per regime |
| abort_aggressiveness | 0.042 | 0.346 | ~0.21 | Cycle termination sensitivity |
| base_size_pct | 0.716 | 2.273 | ~1.63 | Position size as % of equity |
| confidence_sensitivity | 0.736 | 2.000 | ~1.46 | Confidence-based size scaling exponent |
| recovery_aggression | 0.308 | 0.894 | ~0.57 | Drawdown-based size reduction rate |
| hysteresis_margin | 0.071 | 0.270 | ~0.18 | Regime switch reluctance |

The variation in base_size_pct (0.72% to 2.27%, a 3.2× range) demonstrates that the evolution has learned regime-specific risk appetite: favourable regimes (low volatility, mean-reverting) warrant larger positions, while hostile regimes (high volatility, trending) require conservative sizing. Similarly, the abort_aggressiveness range (0.042 to 0.346) indicates that the GA has learned when to cut losses early: high-abort-aggressiveness islands terminate sessions before they reach maximum depth, accepting a small certain loss over a potentially catastrophic bust. Low-abort-aggressiveness islands let sessions run, reflecting regimes where recovery probability is higher.

Beyond the 6 pipeline-level genes, the expanded genome encodes strategy-level parameters including `signal_mode` (categorical: random, ema_cross, rsi, macd, etc.), `direction_bias` (long_only, short_only, both), `hedge_value`, `tp_value`, `max_levels`, `sizing_factor`, and risk controls such as `max_consec_busts` and `session_filter`. The regime-specific tuning of these parameters — particularly signal mode and direction bias — is the primary source of the PF improvement (see Section 6.6).

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

### 6.7 Session Win Rate and Profit Factor in Martingale Strategies

The relationship between session win rate and profit factor in Martingale strategies is fundamentally non-linear — a property that has important implications for how pipeline improvements should be evaluated.

In a standard fixed-size strategy, PF scales approximately linearly with the win/loss ratio because wins and losses are of comparable magnitude. In a Martingale strategy, this relationship breaks down. A single bust at maximum depth with sizing factor 1.7 produces a loss equivalent to approximately 5–6 winning sessions. Removing 1 bust from 50 represents a 2% reduction in bust count, but the remaining 49 busts still dominate the loss side of the profit factor calculation.

The pipeline's contribution is not in bust elimination per se but in loss severity reduction and entry quality improvement. Per-regime sizing adaptation adjusts position sizes to be smaller in high-bust-probability regimes, meaning that when busts do occur, the absolute dollar loss is reduced. More importantly, per-regime signal selection reduces the bust probability itself in regimes where directional bias is detectable. This dual mechanism — reduced bust probability AND reduced bust severity — is what produces the PF improvement from 0.77 to 3.72, a transformation that neither bust elimination alone nor severity reduction alone could achieve.

For evaluating Martingale optimisation systems generally, the implication is that session win rate and bust count are necessary but insufficient metrics. The distribution of bust severity (how much each bust loses relative to the average win) and the conditioning of entry quality on market regime are the primary drivers of PF in these strategies.

---
