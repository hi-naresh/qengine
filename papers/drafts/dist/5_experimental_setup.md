## 5. Experimental Setup

### 5.1 Data and Execution Environment

The evaluation uses EUR-USD foreign exchange data at 1-minute resolution from OANDA Corporation (REST API v20), stored in a PostgreSQL database. The full dataset covers January 2, 2006 to December 30, 2025 (~10.4M 1-minute candles, mid-price; no survivorship adjustment as EUR-USD is a continuously traded major). For this evaluation, training data is aggregated to 5-minute candles. The 5m resolution balances signal granularity against computational cost: it yields ~105,000 candles per year (after weekend exclusion), supplying a richer regime-discovery sample than coarser timeframes, and matches the entry-to-resolution rhythm of the Martingale strategy under study (depth-3 sessions at 20-pip hedge spacing typically resolve in 30–90 minutes, intervals that 30m candles coarsen beyond the strategy's natural cycle).

Training data spans January 1, 2022 to December 31, 2024 (1,106,233 one-minute candles, resampled to 221,246 5-minute candles, yielding 220,608 clean feature rows after warmup and gap removal). Out-of-sample testing covers January 1, 2025 to April 19, 2026 (15.5 months), representing the strictly unseen period after training concluded.

All backtests run through the full qengine trading engine with CFD order execution, real per-candle OANDA bid-ask spread (§5.5), 30:1 margin, no commission beyond spread, and disabled swap/rollover (for reproducibility). Starting balance is $10,000. Evolved parameters therefore implicitly account for spread impact rather than relying on a simplified simulator (see §1 for sim-to-prod motivation).

### 5.2 Strategy

The underlying strategy is a Martingale (Surefire Forex Hedging) variant operating in CFD mode with independent position tickets. The strategy declares two presets: an `'original'` preset reflecting the forum-default hyperparameters widely circulated in retail forex literature, and a `'custom'` preset that exposes all hyperparameters for per-regime evolution. The baseline (no pipeline) uses the `'original'` preset: no directional signal (random entry, `signal_mode = 'none'`, `direction_bias = 'long_only'`), 10-pip fixed hedge distance, 20-pip take-profit, geometric sizing with factor 2.0, and maximum 6 depth levels (depths 0 to 5). Under this configuration a depth-5 bust accumulates the geometric sum 1 + 2 + 4 + 8 + 16 + 32 = 63 base units of exposure (per-bust loss observed in §6.1 is consistent with this).

The pipeline has been developed in two iterations differing in genome scope: Iteration 1 (cloud-trained, 20 evolved parameters across three strategy-level groups) produces the §6 results; Iteration 2 (57 evolved parameters across seven groups, design endpoint) is implementation-complete but not full-scale evaluated. Full gene enumerations are in §3.4 Tables 2 and 3.

The Iteration 1 to Iteration 2 expansion is motivated by structural reasoning: a pipeline restricted to sizing, grid, and take-profit parameters cannot alter entry direction by construction. Under the Martingale's symmetric TP/hedge geometry and ~2-pip OANDA spread, random entry has negative expectancy regardless of direction, so Iteration 1 can only manage exposure (confirmed in §6.1: drawdown collapses ~113×, L0 win rate falls below the random-entry reference). Whether Iteration 2's per-regime signal selection produces directional edge under realistic costs is the natural extension this work motivates.

### 5.3 Evaluation Protocol

*Table 4: Training and evaluation periods.*

| Period | Date Range | Duration | Purpose |
|---|---|---|---|
| Training | 2022-01-01 to 2024-12-31 | 36 months | Island evolution; regime discovery and GA optimisation |
| In-sample check (H1) | 2024-01-01 to 2024-06-30 | 6 months | Sanity check: H1 training data performance |
| In-sample check (H2) | 2024-07-01 to 2024-12-31 | 6 months | Sanity check: H2 training data performance |
| Out-of-sample (primary) | 2025-01-01 to 2026-04-19 | 15.5 months | Main evaluation, never seen during training |

The pipeline (feature selection, regime discovery, island evolution) is trained exclusively on the 2022–2024 period. All 2025–2026 results are strictly out-of-sample: no re-fitting of the regime tree or island populations is performed on evaluation data. The training cutoff is enforced at the code level: `train.py` hard-rejects any `--train-end` date on or after 2025-01-01.

The 36-month training window is motivated by three constraints. First, GMM stability: the BIC search for macro-clusters requires at least 200 observations per component for the 5-dimensional macro feature space (20 covariance parameters × 10 observations minimum per parameter; McLachlan & Peel, 2000). At 5m resolution, 36 months of EUR-USD provides approximately 315,000 5m bars, roughly 18× the theoretical minimum per component and 18× more than the equivalent 30m window, yielding substantially more stable GMM covariance estimates and BIC selection. Second, regime diversity: 36 months spans the post-pandemic rate normalisation cycle (2022), the peak inflation-and-rate-hike environment (2022–2023), and the initial rate-cut pivot (2024). This three-phase diversity means the regime tree is exposed to conditions ranging from high-volatility trend (2022 EUR/USD decline from 1.15 to 0.96) through mean-reverting range (2023) to directional recovery (2024), providing richer per-regime evolution targets than a 24-month window that captures only two of these phases. Third, genetic evolution depth: evolving 14 strategy-level genes per genome (Iteration 1) requires a sufficient number of training cycles per leaf. With 36 months of training data the cloud run accumulates approximately 220,608 clean 5m feature rows after warmup and gap removal, providing a statistically meaningful fitness signal for the 20-generation evolution. (no leaf accumulated a 30-day contiguous activation window in this run, so the fitness-isolation mechanism did not engage; see §6.2.) Extending to 48+ months would include 2020–2021 COVID-era anomalies (extreme spreads, circuit breakers, correlated gap behaviour) unrepresentative of normal FX microstructure; 2022–2024 avoids this contamination.

### 5.4 Comparison Systems

Three benchmark systems are evaluated alongside IslandPilot on the 2025–2026 OOS period:

**Baseline.** The unenhanced Martingale strategy with the original preset and no pipeline attached — the lower bound against which pipeline value is measured. All systems share the same entry signals, starting balance ($10,000), and execution engine.

**GTSBotPilot** adapts Rundo et al. (2019) as pipeline hooks over the Martingale strategy: a trend layer (EMA-smoothed derivatives replacing the original regression network), an ATR-scaled grid spacing manager, and a basket equity manager closing positions at 2.0 × ATR(14) profit. Rule-based, no offline training required.

**FinRLPilot** adapts Liu et al. (2020) FinRL infrastructure to discrete parameter-preset selection across four hedge/TP/depth configurations using a tabular Q-learner trained on 2022–2024 data.

Full implementation details for both comparison systems are in **Appendix E**. Honest re-runs of GTSBotPilot and FinRLPilot under the same production execution engine on the canonical 2025-01-01 to 2026-04-19 OOS window are pending; the primary baseline-vs-pipeline comparison in §6 establishes the load-bearing scientific claim, and comparison-system results will be integrated in the journal extension.

### 5.5 Execution Cost Model

The qengine execution engine applies real per-candle OANDA bid-ask spread data to all order fills. At each candle, the engine looks up the actual historical bid-ask spread for EUR-USD from the OANDA database (column 6 of the imported candle data, storing the ask–bid difference at candle open as reported by OANDA's REST API). For buy entries, the fill price is shifted upward by the full spread; for sell entries, it is shifted downward. This models the cost of crossing the spread at market, which is how retail OANDA CFD orders execute. Exit orders (take-profit and stop-loss) fill at their trigger price; the spread cost is therefore incurred at entry only. EUR-USD bid-ask spread on OANDA averages approximately 1–2 pips during London and New York sessions and widens to 3–5 pips during Asian session and news events; the per-candle lookup captures this intraday variation rather than applying a uniform value.

Spread is charged per individual trade entry, not per trading session. This distinction is critical for Martingale strategies: a session that resolves at depth 0 (single entry, immediate take-profit) incurs one spread charge, while a session that escalates to depth 2 before recovery generates 3 separate trade entries, accumulating 3× the single-entry spread cost. The spread cost therefore scales linearly with session depth, creating a depth-dependent drag on profitability that the fitness function must implicitly account for.

A correction was applied to the strategy's breakeven exit mechanism to include a spread-cost buffer in the target-price calculation (full description in **Appendix G**); without this, "breakeven" sessions systematically closed at net-negative P&L because raw entry prices already embed the spread slippage.

No additional transaction costs are modelled beyond spread. Commission is zero in the OANDA CFD model (OANDA incorporates its fee into the spread). Swap and rollover costs are disabled in backtesting. This simplification is justified by the strategy's short average session duration: the median session completes within a trading day, and overnight holding occurs primarily in deep sessions that are already incurring adverse price movement losses. The omission of swap costs slightly overstates profitability for deep sessions but does not materially affect the pipeline-vs-baseline comparison, as both variants experience the same holding durations.

The starting account balance is $10,000 with 30:1 default margin (the maximum permitted for major FX pairs under ESMA and equivalent regulatory frameworks). Position sizing is expressed as a percentage of current equity, so the effective position size varies during drawdown periods. Leverage enters the sizing calculation as `qty = (balance × base_size_pct ÷ 100) × leverage ÷ price`, consistent with retail CFD platforms where margin is reserved rather than capital actually deployed. Under the default `base_size_value = 1.0` and 30:1 leverage, an L0 position represents approximately 1% of equity as margin and 30% of equity as notional exposure.

**Metrics.** Primary evaluation metrics are profit factor (gross profit / gross loss), session win rate (fraction of profitable sessions), bust rate (fraction of sessions reaching maximum depth), net profit percentage, and maximum drawdown percentage. Additionally we report L0 win rate (fraction of sessions resolving at the initial depth level without requiring a hedge), a structural metric particularly informative for IslandPilot evaluation: under random entry with symmetric TP/hedge distances and zero spread, a Brownian-motion hit-time argument gives L0 win rate ≈ TP_distance / (TP_distance + hedge_distance). Regime-conditioned entry signals that supply a directional edge push L0 win rate above this random-walk reference, while a regime tree that contributes no directional information recovers the reference value. We therefore treat L0 win rate as a proxy for the regime tree's direct contribution to signal quality, separate from the downstream sizing and risk parameters that also evolve.

### 5.6 Pre-flight Validation Protocol (Iteration 2 architectural correctness)

The pre-flight protocol verifies that the Iteration 2 expanded gene set (7 tunable groups, 57 genes, categorical-gene resolver, retired legacy `base_size_pct`) achieves GA convergence and gene-encoding correctness on a short window before committing cloud compute. It is **not** the source of the §6 OOS numbers (those come from the Iteration 1 cloud-trained model). The protocol runs in three stages on a consumer CPU: (1) import and gene-bounds correctness assertions; (2) short real-data training on 2024 Q1 (8 individuals × 8 generations × 9 workers, ~15–25 min wall-clock); (3) held-out OOS validation on 2024 Q2 with criterion: ≥ 10 of top-20 genomes OOS-profitable. Full protocol specification and validation result are in **Appendix F**.

---
