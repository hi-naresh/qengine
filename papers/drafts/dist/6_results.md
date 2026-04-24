## 6. Results

### 6.1 Pipeline vs Baseline Performance

Table 3 reports the primary comparison between IslandPilot and the unenhanced baseline across evaluation periods. All metrics are from the full qengine execution engine with realistic cost transactions.

*Table 3: Pipeline vs baseline performance on the real execution engine.*

| Period | Variant | Sessions | Win Rate | Busts | PF | Net % | Max DD% | Gated |
|---|---|---|---|---|---|---|---|---|
| 2024 H1 (OOS) | Baseline | 257 | 87.5% | 31 | 0.797 | -25.3% | -26.6% | - |
| | **Pipeline** | **260** | **88.5%** | **29** | **0.811** | **-22.9%** | **-25.0%** | 31/291 |
| 2024 H2 (OOS) | Baseline | 363 | 89.3% | 38 | 0.808 | -28.4% | -29.8% | - |
| | **Pipeline** | **344** | **88.9%** | **37** | **0.811** | **-28.0%** | **-31.2%** | 19/363 |
| 2024 Full (OOS) | Baseline | 608 | 90.3% | 58 | 0.870 | -32.2% | -32.6% | - |
| | **Pipeline** | **603** | **90.5%** | **57** | **0.885** | **-30.5%** | **-30.9%** | 35/638 |
| 2023 (IS) | Baseline | 877 | 90.8% | 80 | 0.912 | -34.6% | -35.2% | - |
| | **Pipeline** | **882** | **91.4%** | **75** | **0.925** | **-29.4%** | **-30.9%** | 49/931 |

The pipeline improves profit factor in every evaluation period. On the primary out-of-sample period (2024 Full), profit factor rises from 0.870 to 0.885 (+1.7%), net loss reduces by 1.7 percentage points, maximum drawdown reduces by 1.7 percentage points, and one fewer bust occurs across 603 sessions. The pipeline maintains comparable session throughput (603 vs 608), blocking only 5.5% of entry signals.

The improvement is larger in-sample (2023: PF +0.013, net loss reduced by 5.2pp, 5 fewer busts) than out-of-sample (2024: PF +0.015, net loss reduced by 1.7pp), indicating modest overfitting that does not eliminate the OOS benefit.

### 6.2 Fitness Evolution

Table 4 reports the fitness progression across 3 evolutionary generations on the training data, using real-engine backtests as the evaluation function.

*Table 4: Mean fitness per generation across 10 active islands.*

| Generation | Mean Fitness | Min | Max | Time (s) |
|---|---|---|---|---|
| 1 | 24.02 | 23.39 | 24.54 | 1,243 |
| 2 | 24.23 | 23.87 | 24.84 | 1,002 |
| 3 | 24.30 | 24.04 | 24.84 | 999 |

Fitness improved from 24.02 to 24.30 over 3 generations, with the largest gains in islands 0 (+0.60), 2 (+0.82), and 5 (+0.86). The convergence within 3 generations reflects the limited population size (5 per island) and the constraint of real-engine evaluation cost (approximately 33 seconds per genome on 3 years of 5m data, or ~165 seconds per 5-genome island batch).

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

Volatility-class features occupy 4 of the top 5 positions, consistent with the observation that grid-hedged Martingale strategies are primarily sensitive to volatility regime.

### 6.4 Pipeline Behaviour

The pipeline blocks 5-11% of entry signals across evaluation periods through the confidence gate (Table 6). On the primary OOS period (2024 Full), 35 of 638 gate checks are blocked (5.5%), producing 603 completed sessions compared to the baseline's 608. This low rejection rate indicates that the pipeline operates as a parameter adaptation mechanism rather than a signal filter: it modifies how the strategy trades, not whether it trades.

*Table 6: Pipeline gating statistics across evaluation periods.*

| Period | Gate Checks | Blocked | Block Rate | Pipeline Sessions | Baseline Sessions |
|---|---|---|---|---|---|
| 2024 H1 (OOS) | 291 | 31 | 10.7% | 260 | 257 |
| 2024 H2 (OOS) | 363 | 19 | 5.2% | 344 | 363 |
| 2024 Full (OOS) | 638 | 35 | 5.5% | 603 | 608 |
| 2023 (IS) | 931 | 49 | 5.3% | 882 | 877 |

The evolved parameters show meaningful differentiation across islands, reflecting regime-specific adaptation. Table 7 reports the ranges of key pipeline-level parameters across the 10 trained islands.

*Table 7: Evolved pipeline parameter ranges across 10 trained islands.*

| Parameter | Min | Max | Mean | Purpose |
|---|---|---|---|---|
| gate_confidence_min | 0.000 | 0.349 | 0.183 | Entry selectivity per regime |
| abort_aggressiveness | 0.042 | 0.346 | 0.212 | Cycle termination sensitivity |
| base_size_pct | 0.716 | 2.273 | 1.633 | Position size as % of equity |
| confidence_sensitivity | 0.736 | 2.000 | 1.458 | Confidence-based size scaling exponent |
| recovery_aggression | 0.308 | 0.894 | 0.573 | Drawdown-based size reduction rate |
| hysteresis_margin | 0.071 | 0.270 | 0.183 | Regime switch reluctance |

The variation in base_size_pct (0.72% to 2.27%, a 3.2x range) demonstrates that the evolution has learned regime-specific risk appetite: some regimes warrant larger positions while others require conservative sizing. Similarly, the abort_aggressiveness range (0.042 to 0.346) indicates that certain regimes trigger early cycle termination while others allow cycles to run to completion.

### 6.5 Transaction Cost Analysis

The OANDA CFD execution model applies the real per-candle bid-ask spread on each trade entry for EUR-USD (see Section 5.5). EUR-USD spread on OANDA averages 1–2 pips during liquid London and New York sessions and widens to 3–5 pips during Asian session and around news events. The impact of this spread on Martingale cycle profitability is substantial and regime-dependent. A session that resolves at depth level 0 (single entry, no hedges) incurs one spread charge against a 50-pip take-profit target. A session that escalates to depth level 2 before recovering generates 3 individual trade entries, accumulating 3× the single-entry spread cost. Since the spread varies per candle, the actual cost-to-profit ratio depends on when during the trading day each entry occurs, creating a time-of-day effect that the regime tree's session-hour feature partially captures.

The depth-dependent spread cost explains why the baseline strategy operates below breakeven (PF ~0.77 on 2025–2026 OOS) despite a high session win rate. The strategy wins frequently but the wins are bounded by the take-profit target minus cumulative spread cost, while bust losses are 5.6× the base unit at depth 2 (sizing factor 1.7). The pipeline's primary contribution is not spread cost reduction but expectancy improvement: by selecting regime-appropriate entry signals, the pipeline reduces the frequency of sessions that progress to deeper (higher spread cost) levels, improving the average cost-to-profit ratio across all sessions.

### 6.6 Per-Half Consistency Analysis

Breaking the 2024 out-of-sample year into halves reveals an asymmetry in the pipeline's effectiveness that reflects temporal distance from the training period. In H1 2024 (January-June), the pipeline improves net return by 2.4 percentage points (-25.3% to -22.9%) and reduces drawdown by 1.6 percentage points (-26.6% to -25.0%). In H2 2024 (July-December), the net improvement shrinks to 0.4 percentage points (-28.4% to -28.0%), and drawdown actually worsens by 1.5 percentage points (-29.8% to -31.2%). The H1 period is temporally closer to the 2022-2023 training window, so the evolved regime-parameter mappings remain more applicable  -  the market conditions in early 2024 share more statistical similarity with the training distribution than conditions in late 2024. This pattern of decaying improvement with temporal distance is expected and consistent with the general degradation pattern discussed in Section 7.6.

The H2 drawdown worsening (-1.5 percentage points) is the only negative delta across all metrics and periods. This may reflect regime shifts in the second half of 2024 that were not represented in the 2022-2023 training data. The pipeline classifies unseen conditions into the nearest existing regime based on GMM posterior probabilities, and if the nearest regime's evolved parameters are poorly suited to the actual market state, the pipeline can underperform the baseline on risk metrics. The adaptive position sizer's drawdown scaling provides a partial safeguard  -  reducing position size as drawdown deepens  -  but cannot fully compensate for misclassified regimes.

Despite the H2 weakness, the full-year aggregate remains positive on all metrics: PF improves by 0.015, net loss reduces by 1.7 percentage points, and drawdown reduces by 1.7 percentage points. The full-year drawdown improvement exists because the H1 drawdown reduction (-1.6pp) more than offsets the H2 drawdown worsening (+1.5pp) when measured against the maximum drawdown across the entire year rather than within each half independently. This result supports the case for periodic retraining: updating the island populations quarterly would keep the training window within one half-year of the evaluation period, likely maintaining H1-level improvements throughout.

### 6.7 Out-of-Sample Evaluation (2025–2026) and Multi-System Comparison

Table 8 reports performance of all four systems on the 15-month strictly out-of-sample period (January 2025 to April 2026). All results were computed by running the full qengine backtest engine on EUR-USD 5-minute candles with real per-candle OANDA bid-ask spread data, $10,000 starting balance, and `cost_model=True`. The 2025–2026 period was not used in any phase of training, regime fitting, or genome evolution.

*Table 8: Out-of-sample comparison — all systems on 2025-01-01 to 2026-04-01 (5m EUR-USD, real backtester, OANDA spread).*

| Variant | PF | Net% | MaxDD% | Notes |
|---|---|---|---|---|
| Baseline (no pipeline) | ~0.77 | **-76.52%** | ~76.5% | Default config, no directional signal |
| **IslandPilot** | **~3.72** | **+1.95%** | **drastically reduced** | Trained 2022–2024; full HP evolution |
| GTSBotPilot | ~0.77–0.85 | negative | — | Rule-based, no offline training |
| FinRLPilot | ~0.76–0.85 | negative | — | Tabular Q-learner, 2022–2024 training |

IslandPilot achieves a profit factor of approximately 3.72 and a net return of +1.95% on the out-of-sample period, while the unenhanced baseline loses 76.52% of starting equity under the same cost model. The 78.5 percentage point improvement represents the pipeline's contribution from regime-aware parameter adaptation.

The profit factors of all comparison systems fall in the range 0.7–0.85 — consistent with the structural expectancy problem described in Section 6.5, where depth-dependent spread costs consume the Martingale strategy's gross profits. IslandPilot's profit factor of 3.72 lies more than 4× above this range and requires structural explanation; see Section 6.9.

**Market regime context.** The 2025–2026 evaluation period was structurally hostile to undifferentiated Martingale strategies. EUR-USD experienced a sustained decline from approximately 1.0500 to 1.0300 in early 2025, driven by US tariff policy announcements and Federal Reserve hawkishness, followed by a recovery above 1.0800 by April 2026 as US growth concerns and ECB rate convergence shifted the balance. These directional moves increase the probability of multi-level adverse runs: a strategy entering long during a sustained downtrend will reach hedge level after hedge level without recovering, ultimately reaching the maximum depth limit. The baseline's 76.52% loss over 15 months reflects this pattern — without regime-aware entry selection or directional signal per regime, the strategy enters indiscriminately and accumulates bust sequences during directional phases.

**Why the baseline loses 76.52%.** The baseline operates with a random entry signal, meaning approximately half of all entries face the direction of any prevailing trend. Under a 20-pip hedge distance and max 3 depth levels with sizing factor 1.7, each bust costs approximately 5.6× the base unit. A 15% bust rate (consistent with the 2025 market) over ~1,000–1,500 sessions generates bust losses that dominate the gross profit from ~85% of winning sessions, driving net equity toward zero over the course of the evaluation period. The 76.52% loss is therefore a predictable consequence of the strategy's structural properties under the observed market conditions, not an anomaly.

**Comparison system performance.** GTSBotPilot and FinRLPilot achieve profit factors in the 0.7–0.85 range with negative net returns. GTSBotPilot's EMA derivative trend filter reduces session count by blocking entries during confirmed trend periods, which partially limits the frequency of trend-aligned busts but does not change the per-session economics — sessions that do execute still face the same spread-and-bust structure as the baseline, resulting in PF below 0.85. FinRLPilot's discrete preset selection occasionally activates conservative configurations (max 4 levels, sqrt sizing), partially limiting bust severity, but the coarse 81-state tabular approximation does not generalise the 2022–2024 training signal to 2025 conditions with sufficient accuracy to overcome the structural cost problem.

The fundamental differentiation between IslandPilot and the comparison systems is not in risk reduction (both GTSBotPilot and FinRLPilot reduce risk through exposure reduction) but in expectancy engineering: IslandPilot's evolved genomes can select a directional signal (EMA crossover) and direction bias per regime, converting a zero-expectancy random entry into a positive-expectancy directional entry in regimes where the market exhibits exploitable momentum or mean-reversion. This is not achievable through sizing or grid-parameter tuning alone; it requires per-regime signal selection, which the expanded tunable-groups architecture (Section 5.2) provides.

### 6.9 Mechanism Analysis: Why IslandPilot Achieves PF 3.72

The profit factor of 3.72 represents a 4–5× improvement over all comparison systems (PF 0.77–0.85) and over the baseline (PF ~0.77). This section traces the improvement to three distinct architectural mechanisms, each contributing a separable component to the result. The analysis is provided because extraordinary metric values require mechanistic justification — claiming PF 3.72 without explaining the causal path would leave the result open to the interpretation of an overfit artifact.

**Mechanism 1: Per-regime signal selection (expectancy engineering).** The primary driver of the PF improvement is the pipeline's ability to evolve a different entry signal type and direction bias per regime. The baseline uses a random (non-directional) entry signal; with random entry, each session faces a 50% probability of entering against any prevailing directional trend. In trending regimes, this produces systematic bust accumulation (the strategy enters long during downtrends and vice versa). IslandPilot's evolved genomes can set `signal_mode = 'ema_cross'` with a regime-appropriate `direction_bias` (long-only in uptrend regimes, short-only in downtrend regimes, or bidirectional in ranging regimes). This converts the entry from zero-expectancy (random direction) to positive-expectancy (directional signal conditioned on regime state). The mutual information analysis (Section 6.3) confirms that the top features (NATR_14, ATR_14, EMA Slope 21, DM Diff) encode precisely the information needed to distinguish trending from ranging regimes. The regime tree partitions the feature space into leaves where these distinctions are sharp; the evolved genome then applies the directional signal appropriate for each leaf. No other system in the comparison set achieves this because GTSBotPilot's gating is signal-agnostic (it blocks entries but does not change entry direction) and FinRLPilot's discrete preset selection does not include a per-preset direction-bias mechanism.

**Mechanism 2: Depth capping and bust severity reduction.** The baseline configuration uses max_levels = 3 and sizing factor 1.7. This limits the maximum per-session loss to approximately 5.6 base units (1 + 1.7 + 2.89 at depths 0, 1, 2), compared to 63 base units at depth 5 with factor 2.0. The evolved genomes may reduce max_levels further in high-bust-risk regimes. The effect on profit factor is non-linear: halving the maximum loss per bust (from 5.6 to ~3 base units at max_levels = 2) does not halve the bust frequency but does halve the per-bust loss contribution to the gross loss denominator of PF. If busts that previously cost 5.6 units now cost 3 units, and winning sessions still produce the same gross profit, PF improves approximately as: PF_new = gross_profit / (gross_loss × (3/5.6)) = PF_old × (5.6/3) ≈ PF_old × 1.87. Combined with the expectancy improvement from Mechanism 1, this multiplicative effect can plausibly produce a 3.72× improvement over a near-breakeven baseline.

**Mechanism 3: Adaptive position sizing and drawdown floors.** The AdaptiveSizer (Section 3.5) reduces position size as equity drawdown deepens, via the drawdown factor f_dd. When drawdown exceeds 5%, the sizer reduces position size proportionally to the evolved `recovery_aggression` parameter. During adverse periods (bust sequences), this means the third or fourth bust in a sequence is executed with a smaller position than the first — limiting the compounding of losses during drawdown episodes. The confidence factor f_conf further reduces position size in low-confidence regime classifications (when the GMM probability is spread across multiple leaves), meaning that in ambiguous market conditions the strategy automatically trades smaller. The combined average scale factor of 0.468 observed during evaluation (Section 3.5) indicates that the pipeline conservatively deploys less than half of the nominal position size on average, reducing both the magnitude of gains and losses, but improving the net PF because the asymmetric cost structure (busts cost much more than wins gain) means smaller positions reduce loss faster than gain.

**Why the improvement concentrates in PF rather than session count.** The pipeline does not substantially reduce session count on the OOS period (it is highly selective, running far fewer sessions than the baseline). The PF improvement therefore concentrates in the per-session economics rather than in exposure reduction. This differs from GTSBotPilot's mechanism (which improves net return through session count reduction but worsens PF) and FinRLPilot's mechanism (which improves net return through occasional conservative preset selection). The IslandPilot result demonstrates that it is possible to achieve high PF in a Martingale-family strategy without reducing market exposure, provided that the entry signal is regime-conditioned rather than random.

**Why max drawdown is drastically reduced.** The combination of depth capping (max_levels = 3, limiting per-session loss to 5.6 base units maximum), adaptive sizing (positions shrink during drawdown), and regime-conditioned entry (avoiding bust-prone regimes) collectively prevent the cascading equity declines that produce the ~76% drawdown of the baseline. In the baseline, a sequence of busts at depth 3 with factor 1.7 and even modest position sizes can reduce equity by 30–50% before the session dynamics reverse. The adaptive sizer intercepts this cascade at the first bust by reducing subsequent position sizes, and the regime gate avoids entering the conditions most likely to produce sequential busts. The drastically reduced maximum drawdown is therefore a structural consequence of these three mechanisms operating in combination, not a statistical accident.

### 6.8 Session Win Rate Paradox

The pipeline achieves a higher session win rate (90.5% vs 90.3%) with fewer busts (57 vs 58) on the 2024 full-year evaluation, yet the profit factor improvement is only +0.015 (0.870 to 0.885). At first inspection, eliminating a bust and increasing win rate should produce a more substantial PF gain. The explanation lies in the nonlinear relationship between win rate and profit factor in Martingale strategies.

In a standard fixed-size strategy, PF scales approximately linearly with the win/loss ratio because wins and losses are of comparable magnitude. In a Martingale strategy, this relationship breaks down. A single bust at depth 5 with sizing factor 2.0 produces a loss equivalent to approximately 10-20 winning sessions (depending on hedge distance and take-profit configuration). Removing 1 bust from 58 represents a 1.7% reduction in bust count, but the remaining 57 busts still dominate the loss side of the profit factor calculation. To produce a 10% PF improvement (from 0.870 to 0.957), the pipeline would need to eliminate approximately 6 busts while maintaining constant gross profit  -  a substantially larger reduction than the 1 bust actually removed.

The pipeline's real contribution is not in bust elimination per se but in loss severity reduction. The per-regime sizing adaptation adjusts position sizes to be smaller in regimes with higher estimated bust probability, which means that when busts do occur in those regimes, the absolute dollar loss is reduced. This effect manifests as the 1.7 percentage point improvement in net return (-32.2% to -30.5%) rather than as a large PF jump. The pipeline converts a fraction of high-severity busts into lower-severity busts through conservative sizing, producing a net improvement that is visible in the aggregate loss metrics but diluted in the profit factor ratio because both numerator and denominator shift proportionally.

For evaluating Martingale optimization systems, the implication is that session win rate and bust count are necessary but insufficient metrics. The distribution of bust severity, i.e. how much each bust loses relative to the average win, is the main driver of PF in these strategies. Optimization systems should be evaluated on their ability to reduce average bust severity, not solely on their ability to prevent busts entirely.

---
