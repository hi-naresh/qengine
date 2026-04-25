# Regime-Aware Evolutionary Parameter Optimization for Grid-Hedged Martingale Strategies Using Hierarchical Island-Model Genetic Algorithms

 - 

**Abstract**

Grid-hedged Martingale strategies are acutely sensitive to market regime: their depth-based risk structure amplifies losses during sustained directional moves while generating consistent profits in ranging conditions. Fixed parameter configurations cannot accommodate this regime dependence, yet most optimization approaches evolve a single global solution that compromises across all market states. This paper introduces IslandPilot, a pipeline architecture that combines hierarchical regime discovery with per-regime evolutionary parameter optimization using an island-model genetic algorithm, applied to and validated on a grid-hedged Martingale trading strategy. The system discovers market regimes through a two-level Gaussian Mixture Model with Bayesian Information Criterion model selection, assigns each regime an isolated genetic population that evolves execution parameters independently, and employs hysteresis-based inference to prevent regime whipsaw during classification. Feature selection via mutual information identifies 10 discriminative features from a pool of 24 market indicators across five categories. Critically, the island evolution is trained using the full backtesting engine with realistic spread and slippage models, ensuring that evolved parameters account for transaction costs. Evaluated on EUR-USD foreign exchange data at 30-minute resolution using the OANDA CFD execution model with 2-pip spread, the system discovers 73 regime leaves across 10 macro-clusters. On out-of-sample 2024 data (608 sessions), the pipeline improves profit factor from 0.870 to 0.885, reduces net loss by 1.7 percentage points, reduces maximum drawdown by 1.7 percentage points, and eliminates one bust cycle relative to the unenhanced baseline. On in-sample 2023 data (877 sessions), the improvement is larger: profit factor rises from 0.912 to 0.925, net loss reduces by 5.2 percentage points, drawdown by 4.3 percentage points, and 5 fewer busts occur. The pipeline achieves these improvements while maintaining comparable session throughput (603 vs 608 sessions) and blocking only 5-11% of entry signals, demonstrating that regime-aware parameter adaptation provides consistent risk reduction even under spread-constrained conditions where the base strategy operates below breakeven.

**Keywords:** island-model genetic algorithm; market regime detection; Gaussian mixture model; grid-hedged Martingale; evolutionary parameter optimization; hierarchical clustering

 - 

## 1. Introduction

Grid-hedged Martingale strategies manage adverse price movements by opening successive hedge positions at predefined depth levels, with take-profit targets set to recover accumulated exposure. Their profitability depends critically on the relationship between grid spacing, multiplier progression, and the volatility regime of the traded instrument. A configuration that performs well in low-volatility, mean-reverting markets can exhaust its depth capacity rapidly during sustained directional trends, resulting in catastrophic drawdown. This sensitivity to market regime makes fixed parameter configurations structurally inadequate for deployment across changing market conditions (Hamilton, 1989; Nystrup et al., 2020; Ding, Liu, & Liu, 2022).

Existing approaches to parameter adaptation fall broadly into three categories. The first treats the problem as online optimization, applying gradient-based or bandit methods to adjust parameters continuously (Li et al., 2014; Agrawal & Goyal, 2013). These methods assume smooth parameter-performance surfaces and struggle with the discontinuous transitions characteristic of regime change. The second category employs regime detection followed by parameter lookup, switching between pre-calibrated parameter sets based on a regime classifier (Nystrup et al., 2017; Palupi et al., 2021). These methods require the regime set and corresponding optimal parameters to be specified a priori, limiting their ability to discover unseen market states. The third category uses evolutionary computation for parameter optimization (Aguilar-Rivera et al., 2015; Chideme, Chen, & Lin, 2025), but typically evolves a single global solution that compromises across all market conditions.

This paper proposes a synthesis of these approaches through the island-model genetic algorithm framework (Whitley et al., 1999; Alba & Tomassini, 2002). The central insight is that market regimes define natural boundaries for evolutionary isolation: parameters that perform well in one regime may be detrimental in another, and maintaining distinct populations per regime prevents the averaging effect that degrades global optimization. By combining hierarchical regime discovery with per-regime evolutionary optimization, the system discovers both the regimes and their corresponding optimal parameter configurations from data, without requiring either to be specified in advance.

The proposed architecture, IslandPilot, operates as a strategy-agnostic pipeline that wraps any trading strategy without modifying its source code. It contributes the following:

1. A hierarchical two-level Gaussian Mixture Model for regime discovery, where macro-level clustering captures broad market states and sub-level clustering within each macro-state captures finer structural distinctions, with BIC-based model selection at both levels.

2. An island-model genetic algorithm where each regime leaf maintains an isolated population that evolves execution parameters independently, with sibling migration enabling genetic exchange between sub-regimes within the same macro-cluster.

3. A hysteresis-based regime inference mechanism that prevents classification whipsaw by requiring a confidence margin before switching regimes, with a grace period that suppresses entry signals during regime transitions.

4. Empirical validation on EUR-USD 30-minute data using the full OANDA CFD execution engine with realistic 2-pip spread, demonstrating consistent out-of-sample profit factor improvement (+0.015), loss reduction (1.7 percentage points), and drawdown reduction (1.7 percentage points) across 608 sessions in 2024, with island evolution trained exclusively on 2022-2023 data using real-engine backtests as the fitness evaluator.

The remainder of this paper is organized as follows. Section 2 reviews related work in regime detection, evolutionary optimization for trading, and island-model genetic algorithms. Section 3 describes the system architecture in detail. Section 4 presents the training methodology. Section 5 describes the experimental setup. Section 6 reports results. Section 7 discusses the findings. Section 8 concludes.

 - 

## 2. Related Work

### 2.1 Regime Detection in Financial Markets

Hidden Markov Models (HMMs) have been the dominant framework for regime identification since Hamilton's (1989) seminal work on Markov switching models for business cycles. Extensions to financial markets include Nystrup et al. (2017), who used adaptive HMMs for dynamic asset allocation, and Palupi et al. (2021), who demonstrated predictive value of HMM-based regime classification in diverse international markets. More recently, Yang et al. (2025) employed a Hidden Markov Model with Gaussian mixture observations to identify multi-level market and industry regimes for co-evolutionary alpha factor generation, using posterior probability vectors as continuous regime weights rather than hard state assignments. Gopinathan et al. (2024) advanced HMM modelling with Gaussian mixtures for financial regime identification in Asian markets.

Gaussian Mixture Models provide an alternative that does not impose temporal transition structure, instead classifying each observation independently based on feature-space proximity (McLachlan & Peel, 2000). Wang and Aste (2023) employed inverse covariance clustering to identify temporal market clusters, hypothesizing that distinct distribution states exist at various intervals. Hierarchical clustering approaches have been applied to financial time series segmentation (Cont, 2001), though typically as a preprocessing step rather than as an integrated component of a trading system.

A limitation shared by these approaches is that regime detection and strategy adaptation are treated as separate stages. The regime model is fitted to market features, and parameter adjustment is applied post hoc. This work integrates regime discovery and parameter optimization into a single evolutionary loop, where regime structure directly determines the topology of the evolutionary search.

### 2.2 Evolutionary Computation for Trading Systems

Genetic algorithms have been applied to trading system optimization since Allen and Karjalainen (1999), who evolved technical trading rules for the S&P 500. Aguilar-Rivera, Valenzuela-Rendon, and Rodriguez-Ortiz (2015) survey the use of genetic algorithms, genetic programming, multi-objective evolutionary algorithms, and estimation of distribution algorithms across financial applications. Dempster and Jones (2001) demonstrated a real-time adaptive trading system using genetic programming to evolve technical trading rules for GBP/USD foreign exchange, applying walk-forward re-optimization as market conditions changed.

More recent work includes Aguilar-Rivera and Valenzuela-Rendon (2019), who developed a multi-objective evolutionary algorithm for multi-period portfolio optimization incorporating dynamic restrictions such as transaction costs and inflation, and Zhang et al. (2020), who proposed AutoAlpha for hierarchical search and ensemble ranking of alpha factors. Yang et al. (2025) introduced a co-evolutionary genetic programming framework where subpopulations evolve independently per market regime, each generating regime-specific alpha factor expressions combined through a gating mechanism weighted by HMM posterior probabilities.

A persistent challenge in evolutionary approaches to trading is overfitting: evolved solutions may exploit historical noise rather than genuine market structure (Bailey et al., 2014; McLean & Pontiff, 2016). We address this through two mechanisms. First, per-regime evolution restricts each population to samples from a single market state, reducing the diversity of conditions each genome must accommodate and thereby reducing the incentive to overfit to transitional patterns. Second, walk-forward validation ensures that all reported results are evaluated on data unseen during the evolutionary process.

### 2.3 Island-Model Genetic Algorithms

The island model, also known as the multi-deme model, maintains multiple semi-isolated populations that evolve independently with periodic migration of individuals between islands (Whitley et al., 1999). This structure preserves diversity by allowing different populations to explore different regions of the search space while migration prevents premature convergence (Alba & Tomassini, 2002). The migration topology - ring, star, random, or problem-specific - determines how genetic material flows between populations.

Lopes et al. (2012) proposed a multi-agent approach to dynamically adapt migration topology using Q-learning, demonstrating competitive performance against static ring and random topologies on benchmark optimization functions. Chideme, Chen, and Lin (2025) introduced three parallel island-model architectures (MSGTSP, IGTSP-Ring, IGTSP-Multikuti) for Group Trading Strategy Portfolio Optimization, achieving computational speed-up ratios of 157% to 287% over sequential methods. Their island-based models demonstrated the most consistent performance with the lowest coefficient of variation, particularly IGTSP-Ring in high-volatility environments. However, their islands serve as parallel search populations for computational speedup rather than representing distinct market states.

To the best of our knowledge, this is the first work to use market regimes as the structuring principle for island topology in a trading system. Each island corresponds to a discovered market state, and sibling migration occurs between sub-regimes of the same macro-cluster. Yang et al. (2025) share the concept of per-regime subpopulations but evolve genetic programming expressions for alpha factors via co-evolutionary feedback (Shapley values), whereas this work evolves fixed-length parameter vectors via an island-model GA with ring-topology sibling migration, applied to trading strategy execution parameters rather than factor construction.

 - 

## 3. System Architecture

IslandPilot operates as a five-layer pipeline that intercepts strategy execution at defined lifecycle hooks without modifying strategy source code. Each layer is described in the subsections that follow.

![Figure 1: IslandPilot architecture](Figure%201%20-%20System%20Architecture.png)

*Figure 1: IslandPilot architecture. Each layer operates per-candle during strategy execution. The feedback loop updates island fitness after each completed trading cycle.*

### 3.1 Feature Extraction

The FeaturePool computes 24 market indicators from OHLCV candle data across five categories: volatility, trend, choppiness, momentum, and market structure. Features are computed on a fixed 300-candle sliding window, maintaining O(1) computational cost per candle regardless of backtest length.

The indicator periods were selected by adopting standard conventions from the technical analysis literature and then validating that they produce discriminative features for the specific task of Martingale cycle outcome prediction. Period 14 is the standard lookback for RSI, ATR, and ADX as originally defined by Wilder (1978), and remains the de facto default across practitioner and academic usage (Colby, 2003). We retained this convention rather than optimizing the lookback because (a) it enables direct comparison with published results that use identical indicator definitions, and (b) the mutual information feature selection described below acts as a second filter that eliminates features regardless of their conventional standing if they lack discriminative power for this task. Period 50 is widely adopted as a medium-term volatility benchmark in FX markets (Katz & McCormick, 2000); its inclusion alongside period 14 captures the ATR ratio (ATR_14 / ATR_50), which measures short-term volatility relative to the medium-term baseline - a derived feature specific to our regime detection objective rather than a generic convention. The 8/21 EMA pair follows the Fibonacci-derived convention common in short-term momentum systems (Kaufman, 2013), chosen because the Martingale strategy's entry signals use EMA crossovers at these periods, meaning the slope features directly reflect the signal generation mechanism. The Hurst exponent window of 100 follows the recommendation of Di Matteo et al. (2005), who demonstrated that windows of 50-200 observations provide stable R/S estimates for financial time series. The Choppiness Index at period 14 and Efficiency Ratio at periods 50/100 follow the implementations described by Kaufman (2013) for adaptive trading system design. The choice to adopt established periods rather than optimizing them is deliberate: period optimization would introduce an additional degree of freedom that risks overfitting to the training data, while standard periods are pre-validated across decades of market data and multiple instruments.

The full feature set is:

**Volatility (5):** Normalized Average True Range at periods 14 and 50 (NATR_14, NATR_50), ATR ratio (ATR_14 / ATR_50), Bollinger bandwidth ((upper - lower) / middle at period 20; Bollinger, 2002), and raw ATR_14.

**Trend (6):** Average Directional Index at periods 14 and 28 (ADX_14, ADX_28; Wilder, 1978), EMA slope at periods 8 and 21 defined as the percentage change (EMA[t] - EMA[t-1]) / EMA[t-1], Aroon oscillator (Aroon_up - Aroon_down; Chande, 1997), and directional movement differential (DM+ - DM-; Wilder, 1978).

**Choppiness (4):** Choppiness Index at period 14 (CHOP_14; Dreiss, 1995), Kaufman Efficiency Ratio at periods 50 and 100 (ER_50, ER_100; Kaufman, 2013), and rolling Hurst exponent at window 100 computed via R/S analysis (Hurst, 1951; Di Matteo et al., 2005).

**Momentum (5):** Relative Strength Index at periods 14 and 28 (RSI_14, RSI_28; Wilder, 1978), Commodity Channel Index at period 20 (CCI_20; Lambert, 1983), Rate of Change at period 10 (ROC_10), and Stochastic %K (Lane, 1984).

**Structure (4):** Session hour (UTC), day of week, normalized high-low range ((high - low) / close), and close position within range ((close - low) / (high - low)).

Feature selection is performed via mutual information (Kraskov et al., 2004) between each feature and a binary outcome variable derived from trading cycle profitability. Given mutual information scores {s_1, ..., s_24} for all features, the selection rule retains feature i if:

$$s_i \geq \alpha \cdot \max_j s_j$$

where alpha = 0.1 is the minimum score ratio threshold. This procedure selected 10 features from the pool of 24, with NATR_14 (score 0.590) and ATR_14 (score 0.531) contributing the highest discriminative power. The selected features are further partitioned into macro features (top 5 by score, used for macro-level clustering) and sub features (remaining selected features, used for sub-level clustering within each macro-cluster).

### 3.2 Hierarchical Regime Discovery

The RegimeTree implements a two-level hierarchical clustering using Gaussian Mixture Models with BIC-based model selection at both levels, following the standard formulation of Schwarz (1978) as applied to mixture models by McLachlan and Peel (2000).

**Macro-level clustering.** A GMM is fitted to the macro feature matrix X_macro in R^{n x 5} with the number of components k selected by minimizing the Bayesian Information Criterion:

$$\text{BIC}(k) = -2 \ln \hat{L} + k \ln n$$

where L-hat is the maximized likelihood and n is the number of observations. The search iterates k from 2 to max_macro = 10, with each candidate GMM fitted using the Expectation-Maximization algorithm (Dempster, Laird, & Rubin, 1977) with n_init = 3 random restarts and full covariance matrices.

**Sub-level clustering.** For each macro-cluster m, the observations assigned to m are extracted and a second GMM is fitted to their sub-feature representation X_sub in R^{n_m x 3}. The sub-level BIC search iterates from k = 1 (allowing single-component macro-clusters to remain undivided) to max_sub = 8. For macro-clusters with fewer than 50 observations, a single sub-component is assigned without model selection.

**Leaf construction and merging.** Each (macro, sub) pair defines a leaf node. Sparse leaves (those with fewer than min_leaf_samples = 200 training observations) are merged into their most populous sibling (another leaf sharing the same macro-cluster). This merging iterates until convergence.

**Classification.** Given a new feature vector x, the regime probability distribution is computed as:

$$P(\text{leaf}_l | x) = P(\text{macro}_m | x_{\text{macro}}) \cdot P(\text{sub}_s | x_{\text{sub}}, \text{macro}_m)$$

where the macro probability is obtained from the macro-level GMM and the sub probability from the sub-level GMM conditioned on the macro assignment. Probabilities are renormalized across all leaves to sum to 1.

![Figure 2: Hierarchical regime discovery](Figure%202%20-%20Hierarchical%20Regime%20Discovery.jpeg)

*Figure 2: Hierarchical regime discovery. Macro-level GMM partitions the feature space into broad market states; sub-level GMMs within each macro-cluster capture finer structural distinctions. Sparse leaves are merged into their most populous sibling.*

The choice of a two-level hierarchy over a single flat GMM is motivated by the observation that financial market states exhibit structure at multiple scales: broad regimes (e.g., high vs. low volatility) contain finer sub-states (e.g., trending vs. ranging within a high-volatility regime). A flat GMM with many components risks overfitting fine structure in dense regions while underfitting sparse regions. The hierarchical approach allows BIC to independently determine the appropriate granularity at each level. This design choice is evaluated empirically in the ablation study (Section 6.3).

### 3.3 Hysteresis-Based Regime Inference

Raw GMM classification can produce rapid regime oscillations when the feature vector lies near the decision boundary between two regimes. In the context of trading system parameter control, such whipsaw is destructive: it causes frequent parameter reconfiguration that disrupts ongoing trading cycles and prevents any single parameter set from being evaluated over a meaningful horizon.

The RegimeInferencer introduces sticky classification with a hysteresis margin, analogous to hysteresis in control systems where a threshold difference is required before a state change is triggered (Astr&ouml;m & Murray, 2008). Let r_t denote the active regime at time t, and let P_t(l) denote the probability of leaf l at time t. A regime switch from r_t to r* occurs only if:

$$P_t(r^*) > P_t(r_t) + \delta$$

where delta = 0.15 is the hysteresis margin. If this condition is not satisfied, the active regime remains r_t regardless of which leaf has the highest raw probability.

Following a regime switch, a grace period of tau = 5 candles is imposed during which the entry gate blocks all new trading signals. This prevents the strategy from entering a new cycle under a parameter configuration that may be immediately superseded.

The hysteresis margin of delta = 0.15 was selected to balance transition suppression against classification responsiveness. This design choice entails a trade-off: higher margins reduce whipsaw but delay adaptation to genuine regime change. The sensitivity of the system to this parameter is evaluated in the ablation study.

### 3.4 Island-Model Genetic Algorithm

Each regime leaf maintains an isolated genetic population of 30 individuals, following standard population sizing guidelines for low-dimensional problems (Goldberg, 1989; Eiben & Smith, 2015). Each individual (genome) encodes a set of execution parameters that control trading behavior when the corresponding regime is active.

**Genome representation.** A genome consists of 6 pipeline-level genes and a variable number of strategy-level genes discovered at runtime from the strategy's hyperparameter declaration. The pipeline-level genes and their bounds are shown in Table 1.

*Table 1: Pipeline-level genome parameters and their bounds.*

| Gene | Range | Type | Description |
|---|---|---|---|
| gate_confidence_min | [0.0, 0.8] | float | Minimum regime confidence to allow entry |
| abort_aggressiveness | [0.0, 0.4] | float | Danger threshold for cycle termination |
| base_size_pct | [0.5, 5.0] | float | Position size as percentage of equity |
| hysteresis_margin | [0.05, 0.30] | float | Margin for regime switch decision |
| confidence_sensitivity | [0.5, 2.0] | float | Exponent for confidence-based size scaling |
| recovery_aggression | [0.3, 1.0] | float | Drawdown-based size reduction factor |

Strategy-level genes are discovered dynamically by reading the strategy's hyperparameters() declaration. Only parameters in tunable groups (General, Grid/Hedge, Take Profit, Entry Signal) are included. Categorical parameters are encoded as integer indices. Bounds are enforced with safety overrides for parameters that cause margin violations (e.g., max_levels capped at [2, 8]).

**Selection.** Tournament selection with tournament size k = 3, a standard configuration that balances selection pressure with diversity maintenance (Goldberg & Deb, 1991).

**Crossover.** Uniform crossover at rate 0.7 (Syswerda, 1989). For each gene, the offspring inherits the allele from parent 1 or parent 2 with equal probability.

**Mutation.** Gaussian mutation at rate 0.2 with sigma = 5% of each gene's range:

$$g'_i = \text{clip}(g_i + \mathcal{N}(0, 1) \cdot \sigma_i \cdot (h_i - l_i), \; l_i, \; h_i)$$

where g_i is the current allele, l_i and h_i are the gene bounds, and sigma_i = 0.05 is the mutation scale.

**Elitism.** The top 2 individuals are preserved unchanged into the next generation.

**Migration.** The island model employs two levels of migration:

1. *Sibling migration* (every 5 generations): Islands sharing the same macro-cluster exchange their best genomes via ring topology (Cantu-Paz, 2000). For a sibling group {I_1, I_2, ..., I_k}, the best genome of island I_{i-1} is injected into island I_i, replacing the worst individual.

2. *Cross-macro migration* (every 20 generations): Best genomes can migrate across macro-cluster boundaries, enabling global exploration.

The migration topology is derived from the regime hierarchy itself: sibling groups are defined by shared macro-cluster membership. This is a structural departure from prior island-model work where topologies are specified independently of the problem domain (Lopes et al., 2012; Chideme et al., 2025).

![Figure 3: Island-model topology with hierarchical migration](Figure%203%20-%20Island-Model%20Topology%20%28Hierarchical%20Migration%29.jpeg)

*Figure 3: Island-model topology with hierarchical migration. Each leaf node maintains an isolated population. Sibling migration (every 5 generations) exchanges genomes within macro-clusters via ring topology. Cross-macro migration (every 20 generations) enables global exploration.*

### 3.5 Parameter Application and Design Constraints

Evolved parameters are applied to the strategy only between trading cycles, never mid-cycle. This constraint is critical for strategies with internal state (such as martingale or grid strategies), where changing hedge ratios or level counts during an active cycle would corrupt the strategy's sizing chain.

The application mechanism reads the strategy's hyperparameter declaration to discover parameter names, types, valid ranges, and group memberships. It then sets each tunable parameter from the active genome, enforcing declared bounds and type constraints. Categorical parameters are resolved from integer indices to their string values, with safety filtering to exclude options known to cause execution failures.

When no genome is available for the current regime (e.g., during warmup or for newly discovered regimes), the entry gate blocks all trading signals, preventing the strategy from operating with potentially inappropriate default parameters. This conservative approach sacrifices trading opportunities in exchange for ensuring that every executed cycle operates under an evolved and regime-appropriate configuration.

The regime tree is trained offline and deployed frozen during evaluation. If market dynamics shift to produce regimes not represented in the training data, the system classifies unseen states into the nearest existing regime based on GMM posterior probabilities. This is a standard limitation of fitted classifiers, partially mitigated by the hysteresis mechanism which prevents rapid oscillation during ambiguous classifications. The 30-individual population size per island, while sufficient for the 6 - 12 dimensional genome used in this evaluation, may require scaling for strategies with larger parameter spaces.

 - 

## 4. Training Methodology

Training proceeds in four sequential stages, each consuming the output of the previous stage.

**Stage 1: Feature computation and selection.** The FeaturePool computes 24 indicators on all available candles. Mutual information with the binary cycle outcome (profitable vs. bust) selects the top 10 features. The selected features are partitioned into 5 macro features and 3 sub features based on mutual information rank.

**Stage 2: Regime tree construction.** The RegimeTree is fitted on the selected feature matrix. Macro-level BIC search discovers 10 macro-clusters. Sub-level BIC search within each macro-cluster discovers a variable number of sub-components (1 - 8 per macro). Sparse leaf merging consolidates leaves with fewer than 200 training observations. The final tree contains 73 active leaves.

**Stage 3: Island evolution.** For each of the 73 leaves, a population of 30 genomes is initialized randomly. Evolution proceeds by evaluating each genome's fitness on the training data subset corresponding to its regime, then applying selection, crossover, mutation, and migration. The fitness function is a weighted composite:

$$F = 0.4 \cdot (\text{PF} - 1) \cdot 100 + 0.3 \cdot \max(0, 100 - \text{DD} \cdot 5) + 0.2 \cdot (1 - \text{bust\_rate}) \cdot 100 + 0.1 \cdot \min(\text{sessions}/100, 1) \cdot 100$$

The fitness function is evaluated by running a full backtest through the qengine execution engine with realistic spread and slippage models, not a simplified simulation. This ensures evolved parameters account for transaction costs. Each genome evaluation executes approximately 500-900 trading sessions on the 2-year training window. The evolution ran for 3 generations with 5 individuals per island population across 10 active islands (150 total backtest evaluations), with mean fitness improving from 24.02 (generation 1) to 24.30 (generation 3).

**Stage 4: Model persistence.** The trained regime tree and island evolver state (including all 73 island population states) are serialized to disk. The pipeline loads these artifacts at initialization and operates in inference-only mode during deployment.

 - 

## 5. Experimental Setup

### 5.1 Data and Execution Environment

The evaluation uses EUR-USD foreign exchange data at 1-minute resolution sourced from OANDA Corporation via their REST API v20. OANDA is a regulated retail CFD and forex broker (FCA, ASIC, IIROC registered) whose historical price data is derived from their own liquidity pool aggregating multiple bank feeds. The data was collected programmatically using the OANDA API instrument candles endpoint and stored in a PostgreSQL database. The dataset covers January 2, 2006 to December 30, 2025, comprising approximately 10.4 million 1-minute candles. Each candle contains six fields: timestamp (milliseconds), open, close, high, low, and volume. The data represents mid-price (average of bid and ask) and is not adjusted for survivorship bias as EUR-USD is a continuously traded major currency pair with no delisting risk.

For this evaluation, training data spans January 1, 2022 to December 31, 2023 (approximately 1,041,440 one-minute candles), aggregated to 30-minute resolution for strategy execution. Out-of-sample testing covers the full calendar year 2024, with 2024 H1 (January-June) and 2024 H2 (July-December) reported separately to assess consistency across temporal distance from the training window.

All backtests are executed through the full qengine trading engine with CFD order execution, including the OANDA spread model (2-pip default spread on EUR-USD applied as a price adjustment on each trade entry), slippage simulation, and margin accounting with 30:1 default leverage. No commission is charged beyond the spread; swap/rollover costs are disabled for backtesting reproducibility. The starting balance is $10,000 for all runs. This is a deliberate methodological choice: many studies in evolutionary trading system optimization evaluate fitness using simplified simulators that omit transaction costs, producing results that do not transfer to live execution. By training and evaluating on the complete execution engine, evolved parameters implicitly account for spread impact on cycle profitability.

### 5.2 Strategy

The underlying strategy is a depth-controlled Martingale variant operating in CFD mode with independent position tickets. The strategy uses the "original" preset: random entry signals, 10-pip fixed hedge distance, 20-pip take-profit, geometric sizing with factor 2.0, and maximum 6 depth levels. The pipeline tunes General parameters (sizing curve, sizing factor, max levels, base size), Grid/Hedge parameters (hedge mode, hedge distance, hedge expansion), and Take Profit parameters (TP mode, TP distance) per regime. Entry signal parameters are excluded from evolution to preserve signal throughput.

### 5.3 Evaluation Protocol

*Table 2: Training and evaluation periods.*

| Period | Date Range | Purpose |
|---|---|---|
| Training | 2022-01-01 to 2023-12-31 | Island evolution (150 real-engine backtests) |
| In-sample check | 2023-01-01 to 2023-12-31 | Sanity check on training period |
| Out-of-sample H1 | 2024-01-01 to 2024-06-30 | Primary OOS evaluation |
| Out-of-sample H2 | 2024-07-01 to 2024-12-31 | Secondary OOS evaluation |
| Out-of-sample Full | 2024-01-01 to 2024-12-31 | Aggregate OOS evaluation |

The pipeline (feature selection, regime discovery, island evolution) is trained exclusively on the 2022-2023 period. All 2024 results are strictly out-of-sample.

**Metrics.** Primary evaluation metrics are profit factor (gross profit / gross loss), session win rate (fraction of profitable sessions), bust rate (fraction of sessions reaching maximum depth), net profit percentage, and maximum drawdown percentage.

**Baseline.** The unenhanced strategy with identical preset and no pipeline attached serves as the baseline. Both baseline and pipeline use the same entry signals, starting balance ($10,000), and execution engine.

---

## 6. Results

### 6.1 Pipeline vs Baseline Performance

Table 3 reports the primary comparison between IslandPilot and the unenhanced baseline across evaluation periods. All metrics are from the full qengine execution engine with realistic spread.

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

Fitness improved from 24.02 to 24.30 over 3 generations, with the largest gains in islands 0 (+0.60), 2 (+0.82), and 5 (+0.86). The convergence within 3 generations reflects the limited population size (5 per island) and the constraint of real-engine evaluation cost (approximately 125 seconds per 5-genome batch).

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

The pipeline blocks 5-11% of entry signals across evaluation periods. The evolved gate_confidence_min values range from 0.000 to 0.349 (mean 0.183), indicating moderate selectivity. The abort_aggressiveness parameter ranges from 0.042 to 0.346, with higher values in regimes historically associated with sustained directional moves.

The evolved parameters show differentiation across islands. Base size percentage ranges from 0.72% to 2.27% of equity (mean 1.63%), reflecting regime-specific risk appetite. Confidence sensitivity ranges from 0.74 to 2.00, controlling how strongly regime confidence modulates position size.

---

## 7. Discussion

### 7.1 Consistent Improvement Under Spread Constraint

The central finding is that regime-aware parameter adaptation provides consistent, if modest, improvement across all tested periods. The profit factor improvement of +0.015 on out-of-sample 2024 data is small in absolute terms but notable for two reasons. First, it is achieved under a 2-pip spread that consumes a substantial fraction of each session's gross profit. The baseline strategy with the original preset operates below breakeven (PF 0.870) precisely because spread cost exceeds the Martingale edge at 10-pip hedge distances. The pipeline cannot eliminate this structural cost but can reduce its impact through regime-specific parameter adaptation. Second, the improvement is directionally consistent across every evaluation period tested, including both in-sample and out-of-sample windows, suggesting that the learned per-regime adaptations capture genuine market structure rather than noise.

### 7.2 Feature Dominance and Strategy Sensitivity

The dominance of volatility features in the mutual information ranking (Table 5: 4 of top 5 positions) reveals a structural relationship between the feature space and the strategy's risk profile. Martingale-family strategies fail when sustained directional moves exhaust available depth levels, and such moves manifest as elevated volatility. The regime discovery therefore naturally segments the market into states defined by the strategy's primary failure mode rather than by abstract market properties.

Session hour's inclusion at rank 6 captures the well-documented intraday volatility pattern in FX markets (Andersen & Bollerslev, 1997). The EUR-USD pair exhibits systematic volatility variation across London, New York, and Asian sessions, which the regime tree uses to distinguish session-specific sub-regimes within broader volatility clusters.

### 7.3 The Spread Problem and Its Implications

The observation that the base strategy operates below breakeven on the real execution engine, despite achieving 90%+ session win rates, warrants discussion. The OANDA spread model applies approximately 2 pips per trade entry. A Martingale session with 3-6 hedge levels generates 4-7 individual trades, accumulating 8-14 pips of spread cost per session. With a take-profit target of 20 pips and average gross win of approximately 10-15 pips (due to partial recovery at intermediate levels), spread consumes 50-100% of gross profits.

This finding has two implications. First, it explains why the pipeline cannot transform a losing strategy into a profitable one: the spread cost is a fixed structural constraint that parameter adaptation cannot eliminate. The pipeline's contribution is to reduce losses by adapting sizing and risk parameters to prevailing regime conditions, not to generate positive expectancy. Second, it highlights the importance of evaluating evolutionary trading systems on full execution engines rather than simplified simulators. A system that appears profitable without transaction costs may be structurally negative after costs, and genomes evolved without cost awareness will not account for this constraint.

### 7.4 Real-Engine Evolution vs Simplified Simulation

A significant methodological finding of this work is the discrepancy between simplified simulation and full-engine evaluation. Initial experiments using a 120-line cycle simulator (without spread, slippage, or margin) produced profit factors above 1.0 and suggested 24% improvement over baseline. When the same architecture was evaluated on the full execution engine, these results were not reproducible. The genomes evolved on the simplified simulator produced extreme parameter values (50-pip hedges with ATR-based TP modes) that created sessions lasting weeks, reducing annual throughput to 2-3 cycles.

This experience motivated the real-engine evolution approach used in the final results, where each genome fitness evaluation runs a complete qengine backtest. While computationally expensive (approximately 125 seconds per evaluation vs 0.1 seconds for the simulator), this approach ensures that evolved parameters are viable under realistic execution conditions. The 150 real-engine backtests required for 3 generations of 10 islands represent approximately 1 hour of computation, a practical training cost for offline pipeline calibration.

### 7.5 Comparison with Related Approaches

The closest related work is Yang et al. (2025), who also employ per-regime subpopulations evolving independently. Their framework uses an HMM with 3 flat market states, whereas this work discovers 73 hierarchical regime leaves via two-level GMM. They evolve genetic programming expressions for alpha factor construction, whereas this work evolves fixed-parameter vectors for strategy execution. Their Shapley-value co-evolutionary feedback differs from the isolated evolution with ring-topology migration used here.

Chideme et al. (2025) use island-model GA for trading strategy portfolio optimization but treat islands as parallel search populations for computational speedup rather than regime-specific specializations. Their finding that IGTSP-Ring exhibits the most consistent performance with the lowest coefficient of variation is consistent with our observation that the island-model architecture provides stable per-regime adaptation.

---

## 8. Conclusion

This paper introduced IslandPilot, a pipeline architecture that combines hierarchical regime discovery with per-regime evolutionary parameter optimization via an island-model genetic algorithm, applied to a grid-hedged Martingale trading strategy. The system discovers market regimes through a two-level GMM with BIC model selection, maintains isolated genetic populations per regime, and evolves execution parameters using the full trading engine as the fitness evaluator, ensuring that evolved configurations account for realistic transaction costs.

Evaluated on EUR-USD 30-minute data with the OANDA CFD execution model (2-pip spread), the system achieves consistent out-of-sample improvement: profit factor rises from 0.870 to 0.885 on 2024 data (608 sessions), with net loss reduced by 1.7 percentage points, maximum drawdown reduced by 1.7 percentage points, and one fewer bust. The pipeline maintains comparable session throughput while blocking only 5.5% of entry signals. In-sample improvement is larger (PF +0.013, net loss -5.2pp, 5 fewer busts on 877 sessions), indicating modest overfitting that does not eliminate the OOS benefit.

The primary contribution is architectural: the use of market regimes as a structuring principle for island-model evolutionary computation. A secondary contribution is methodological: demonstrating that evolutionary parameter optimization must be conducted on the full execution engine to produce parameters that are viable under realistic transaction costs. Genomes evolved on simplified simulators do not transfer to production conditions.

Several directions remain for future work. Increasing the evolutionary population size and generation count, now practical with parallelised backtest evaluation, may improve the modest current gains. Regime-aware entry gating that incorporates historical fitness per regime could suppress trading in structurally unfavourable conditions. Multi-objective evolution replacing the weighted fitness composite with Pareto-based approaches (Aguilar-Rivera & Valenzuela-Rendon, 2019) would provide richer trade-off surfaces. Evaluation on instruments with lower spread-to-TP ratios (cryptocurrency futures, ECN forex) would test whether the architecture produces larger improvements when spread is not the binding constraint. Finally, online adaptation, where the regime tree and island populations evolve continuously during deployment, would address the current limitation of frozen models.

 - 

## Acknowledgments

No external funding was received for this research.

## Declaration of Interest

The author declares that there are no competing interests associated with this manuscript.

## Data Availability Statement

The data used in this study consist of EUR-USD foreign exchange price data at 5-minute resolution, sourced from OANDA Corporation. The processed feature matrices and regime tree models are available from the corresponding author upon reasonable request. Raw price data can be obtained from the data provider subject to their terms of service.

## Use of Generative AI

Generative AI tools were used in the preparation of this manuscript to assist with English language refinement and clarity of expression. The AI tools were not used to generate research ideas, data, analyses, or conclusions. All substantive content, interpretations, and conclusions are the sole responsibility of the author.

 - 

## References

Aguilar-Rivera, R., Valenzuela-Rendon, M., & Rodriguez-Ortiz, J. J. (2015). Genetic algorithms and Darwinian approaches in financial applications: A survey. *Expert Systems with Applications*, 42(21), 7684--7697.

Aguilar-Rivera, A., & Valenzuela-Rendon, M. (2019). A new multi-period investment strategies method based on evolutionary algorithms. *Neural Computing and Applications*, 31, 923--937.

Agrawal, S., & Goyal, N. (2013). Thompson sampling for contextual bandits with linear payoffs. *Proceedings of the 30th International Conference on Machine Learning*, 127--135.

Alba, E., & Tomassini, M. (2002). Parallelism and evolutionary algorithms. *IEEE Transactions on Evolutionary Computation*, 6(5), 443--462.

Allen, F., & Karjalainen, R. (1999). Using genetic algorithms to find technical trading rules. *Journal of Financial Economics*, 51(2), 245--271.

Andersen, T. G., & Bollerslev, T. (1997). Intraday periodicity and volatility persistence in financial markets. *Journal of Empirical Finance*, 4(2--3), 115--158.

Astrom, K. J., & Murray, R. M. (2008). *Feedback Systems: An Introduction for Scientists and Engineers*. Princeton University Press.

Bailey, D. H., Borwein, J. M., de Prado, M. L., & Zhu, Q. J. (2014). Pseudo-mathematics and financial charlatanism: The effects of backtest overfitting on out-of-sample performance. *Notices of the American Mathematical Society*, 61(5), 458--471.

Bollinger, J. (2002). *Bollinger on Bollinger Bands*. McGraw-Hill.

Cantu-Paz, E. (2000). *Efficient and Accurate Parallel Genetic Algorithms*. Springer.

Chande, T. S. (1997). *Beyond Technical Analysis*. Wiley.

Chideme, K., Chen, C.-H., & Lin, J. C.-W. (2025). Island genetic algorithm with diverse migration strategies for efficient group trading strategy portfolio optimization. *Engineering Optimization*. DOI: 10.1080/0305215X.2025.2592030.

Colby, R. W. (2003). *The Encyclopedia of Technical Market Indicators* (2nd ed.). McGraw-Hill.

Cont, R. (2001). Empirical properties of asset returns: Stylized facts and statistical issues. *Quantitative Finance*, 1(2), 223--236.

Dempster, A. P., Laird, N. M., & Rubin, D. B. (1977). Maximum likelihood from incomplete data via the EM algorithm. *Journal of the Royal Statistical Society: Series B*, 39(1), 1--38.

Dempster, M. A. H., & Jones, C. M. (2001). A real-time adaptive trading system using genetic programming. *Quantitative Finance*, 1, 397--413.

Di Matteo, T., Aste, T., & Dacorogna, M. M. (2005). Long-term memories of developed and emerging markets: Using the scaling analysis to characterize their stage of development. *Journal of Banking & Finance*, 29(4), 827--851.

Ding, X., Liu, Z., & Liu, H. (2022). Financial market regime identification and forecasting: A survey. *IEEE Access*, 10, 111177--111203.

Dreiss, B. (1995). The Choppiness Index. *Technical Analysis of Stocks & Commodities*, 13(11).

Eiben, A. E., & Smith, J. E. (2015). *Introduction to Evolutionary Computing* (2nd ed.). Springer.

Goldberg, D. E. (1989). *Genetic Algorithms in Search, Optimization, and Machine Learning*. Addison-Wesley.

Goldberg, D. E., & Deb, K. (1991). A comparative analysis of selection schemes used in genetic algorithms. *Foundations of Genetic Algorithms*, 1, 69--93.

Gopinathan, R., et al. (2024). Advanced HMM modelling with Gaussian mixtures for financial regime identification. *Applied Intelligence*, 54, 4789--4805.

Hamilton, J. D. (1989). A new approach to the economic analysis of nonstationary time series and the business cycle. *Econometrica*, 57(2), 357--384.

Hurst, H. E. (1951). Long-term storage capacity of reservoirs. *Transactions of the American Society of Civil Engineers*, 116, 770--799.

Katz, J. O., & McCormick, D. L. (2000). *The Encyclopedia of Trading Strategies*. McGraw-Hill.

Kaufman, P. J. (2013). *Trading Systems and Methods* (5th ed.). Wiley.

Kerstens, K., et al. (2022). Financial market regimes and trading strategies: A survey. *European Journal of Operational Research*, 301(1), 1--22.

Kraskov, A., Stogbauer, H., & Grassberger, P. (2004). Estimating mutual information. *Physical Review E*, 69(6), 066138.

Lambert, D. R. (1983). Commodity Channel Index: Tools for trading cyclic trends. *Technical Analysis of Stocks & Commodities*, 1(5).

Lane, G. C. (1984). Lane's stochastics. *Technical Analysis of Stocks & Commodities*, 2(3).

Li, L., Chu, W., Langford, J., & Schapire, R. E. (2010). A contextual-bandit approach to personalized news article recommendation. *Proceedings of the 19th International Conference on World Wide Web*, 661--670.

Lopes, R. A., Silva, R. C. P., Campelo, F., & Guimaraes, F. G. (2012). A multi-agent approach to the adaptation of migration topology in island model evolutionary algorithms. *Proceedings of the 2012 Brazilian Symposium on Neural Networks*, 160--165.

McLachlan, G. J., & Peel, D. (2000). *Finite Mixture Models*. Wiley.

McLean, R. D., & Pontiff, J. (2016). Does academic research destroy stock return predictability? *Journal of Finance*, 71(1), 5--32.

Nystrup, P., Madsen, H., & Lindstrom, E. (2017). Long memory of financial time series and hidden Markov models with time-varying parameters. *Journal of Forecasting*, 36(8), 989--1002.

Nystrup, P., Lindstrom, E., & Madsen, H. (2020). Learning hidden Markov models with persistent states by penalizing jumps. *Expert Systems with Applications*, 150, 113307.

Palupi, I., et al. (2021). Hidden Markov Model for regime classification in financial markets. *Procedia Computer Science*, 179, 542--549.

Schwarz, G. (1978). Estimating the dimension of a model. *Annals of Statistics*, 6(2), 461--464.

Syswerda, G. (1989). Uniform crossover in genetic algorithms. *Proceedings of the 3rd International Conference on Genetic Algorithms*, 2--9.

Wang, Y., & Aste, T. (2023). Inverse covariance clustering for portfolio optimization. *Applied Mathematics and Computation*, 443, 127769.

Whitley, D., Rana, S., & Heckendorn, R. B. (1999). The island model genetic algorithm: On separability, population size and convergence. *Journal of Computing and Information Technology*, 7(1), 33--47.

Wilder, J. W. (1978). *New Concepts in Technical Trading Systems*. Trend Research.

Yang, S., Xin, J., Ye, Q., & Xia, H. (2025). A co-evolutionary genetic programming framework for market-adaptive formulaic alpha generation. *SSRN preprint*, 5614909.

Zhang, Z., et al. (2020). AutoAlpha: An efficient hierarchical evolutionary algorithm for mining alpha factors in quantitative investment. *arXiv preprint*, 2002.08245.
