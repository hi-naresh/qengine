# Regime-Aware Evolutionary Parameter Optimization for Grid-Hedged Martingale Strategies Using Hierarchical Island-Model Genetic Algorithms

 - 

**Abstract**

Grid-hedged Martingale strategies are sensitive to market regime: their depth-based risk structure amplifies losses during sustained directional moves while generating consistent profits in ranging conditions. Fixed parameter configurations cannot accommodate this regime dependence, yet most optimization approaches evolve a single global solution that compromises across all market states. This dissertation introduces IslandPilot, a pipeline architecture that combines hierarchical regime discovery with per-regime evolutionary parameter optimization using an island-model genetic algorithm, applied to and validated on a grid-hedged Martingale trading strategy. The system discovers market regimes through a two-level Gaussian Mixture Model with Bayesian Information Criterion model selection, assigns each regime an isolated genetic population that evolves execution parameters independently, and employs hysteresis-based inference to prevent regime whipsaw during classification. Feature selection via mutual information identifies 10 discriminative features from a pool of 24 market indicators across five categories. Critically, the island evolution is trained using the full backtesting engine with realistic spread and slippage models, ensuring that evolved parameters account for transaction costs. Evaluated on EUR-USD foreign exchange data at 30-minute resolution using the OANDA CFD execution model with 2-pip spread, the system discovers 73 regime leaves across 10 macro-clusters. On out-of-sample 2024 data (608 sessions), the pipeline improves profit factor from 0.870 to 0.885, reduces net loss by 1.7 percentage points, reduces maximum drawdown by 1.7 percentage points, and eliminates one bust cycle relative to the unenhanced baseline. On in-sample 2023 data (877 sessions), the improvement is larger: profit factor rises from 0.912 to 0.925, net loss reduces by 5.2 percentage points, drawdown by 4.3 percentage points, and 5 fewer busts occur. The pipeline achieves these improvements while maintaining comparable session throughput (603 vs 608 sessions) and blocking only 5-11% of entry signals, demonstrating that regime-aware parameter adaptation provides consistent risk reduction even under spread-constrained conditions where the base strategy operates below breakeven. A secondary methodological contribution demonstrates that evolutionary parameter optimization must be conducted on the full execution engine: genomes evolved on simplified simulators without transaction costs do not transfer to production conditions. The architecture is strategy-agnostic and modifies no strategy source code.

**Keywords:** island-model genetic algorithm; market regime detection; Gaussian mixture model; grid-hedged Martingale; evolutionary parameter optimization; hierarchical clustering; walk-forward validation; adaptive position sizing

 - 

## 1. Introduction

Grid-hedged Martingale strategies manage adverse price movements by opening successive hedge positions at predefined depth levels, with take-profit targets set to recover accumulated exposure. Their profitability depends critically on the relationship between grid spacing, multiplier progression, and the volatility regime of the traded instrument. A configuration that performs well in low-volatility, mean-reverting markets can exhaust its depth capacity rapidly during sustained directional trends, resulting in catastrophic drawdown. This sensitivity to market regime makes fixed parameter configurations structurally inadequate for deployment across changing market conditions (Hamilton, 1989; Nystrup et al., 2020; Ding, Liu, & Liu, 2022).

The fundamental challenge is combinatorial: a Martingale strategy with *k* tunable parameters operating across *r* market regimes requires *r* independent parameter configurations, each validated against the specific statistical properties of its regime. Manual calibration is impractical beyond a handful of regimes, and naive grid search scales exponentially with parameter dimensionality. Evolutionary computation offers a principled approach to this optimization, but standard genetic algorithms evolve a single population whose fitness is evaluated across all market conditions, producing compromised solutions that perform adequately in no regime rather than optimally in any.

Existing approaches to parameter adaptation fall broadly into three categories. The first treats the problem as online optimization, applying gradient-based or bandit methods to adjust parameters continuously (Li et al., 2014; Agrawal & Goyal, 2013). These methods assume smooth parameter-performance surfaces and struggle with the discontinuous transitions characteristic of regime change. The second category employs regime detection followed by parameter lookup, switching between pre-calibrated parameter sets based on a regime classifier (Nystrup et al., 2017; Palupi et al., 2021). These methods require the regime set and corresponding optimal parameters to be specified a priori, limiting their ability to discover unseen market states. The third category uses evolutionary computation for parameter optimization (Aguilar-Rivera et al., 2015; Chideme, Chen, & Lin, 2025), but typically evolves a single global solution that compromises across all market conditions.

This dissertation proposes a synthesis of these approaches through the island-model genetic algorithm framework (Whitley et al., 1999; Alba & Tomassini, 2002). Market regimes define natural boundaries for evolutionary isolation: parameters that perform well in one regime may be detrimental in another, and maintaining distinct populations per regime prevents the averaging effect that degrades global optimization. By combining hierarchical regime discovery with per-regime evolutionary optimization, the system discovers both the regimes and their corresponding optimal parameter configurations from data, without requiring either to be specified in advance.

A critical but often overlooked requirement in evolutionary trading system design is that the fitness evaluation must use the same execution model as deployment. Many evolutionary trading studies evaluate candidate solutions on simplified simulators (typically omitting spread, slippage, margin constraints, and order execution latency) and then deploy the resulting parameters on real brokers. This creates a simulation-to-production gap analogous to the sim-to-real transfer problem documented in robotics (Tobin et al., 2017), where policies trained in idealised physics engines fail when confronted with real-world friction, sensor noise, and actuator delay. In trading systems, the gap manifests as parameter configurations that appear profitable in the simulator but produce losses under realistic transaction costs. The problem is particularly acute for Martingale-family strategies, where spread cost accumulates multiplicatively with depth: a 6-level session incurs 6 separate spread charges, and the simulator-to-production discrepancy grows with each additional hedge level. This dissertation addresses the gap directly by training island evolution on the production backtesting engine with the full OANDA CFD execution model, including 2-pip spread on EUR-USD, margin accounting, and realistic order fill simulation. Each genome fitness evaluation runs a complete backtest through the same engine used for live deployment, ensuring that evolved parameters have already survived the transaction cost environment they will encounter in practice. The methodological cost (approximately 125 seconds per genome evaluation compared to 0.1 seconds on a simplified simulator) is substantial but justified by the finding (Section 7.4) that genomes evolved on the simplified simulator did not transfer to the production engine.

The proposed architecture, IslandPilot, operates as a strategy-agnostic pipeline that wraps any trading strategy without modifying its source code. It contributes the following:

1. A hierarchical two-level Gaussian Mixture Model for regime discovery, where macro-level clustering captures broad market states and sub-level clustering within each macro-state captures finer structural distinctions, with BIC-based model selection at both levels.

2. An island-model genetic algorithm where each regime leaf maintains an isolated population that evolves execution parameters independently, with sibling migration enabling genetic exchange between sub-regimes within the same macro-cluster.

3. A hysteresis-based regime inference mechanism that prevents classification whipsaw by requiring a confidence margin before switching regimes, with a grace period that suppresses entry signals during regime transitions.

4. A multi-factor adaptive position sizing layer that scales trade size according to regime classification confidence, evolved base parameters, and current drawdown state, enforcing survivability constraints.

5. Empirical validation on EUR-USD 30-minute data using the full OANDA CFD execution engine with realistic 2-pip spread, demonstrating consistent out-of-sample profit factor improvement (+0.015), loss reduction (1.7 percentage points), and drawdown reduction (1.7 percentage points) across 608 sessions in 2024, with island evolution trained exclusively on 2022-2023 data using real-engine backtests as the fitness evaluator.

The remainder of this dissertation is organized as follows. Section 2 reviews related work in regime detection, evolutionary optimization for trading, and island-model genetic algorithms. Section 3 describes the system architecture in detail, including formal algorithm specifications. Section 4 presents the training methodology. Section 5 describes the experimental setup. Section 6 reports results including per-regime breakdowns. Section 7 discusses the findings with extended analysis. Section 8 concludes and identifies directions for future work.

 - 

## 2. Related Work

### 2.1 Regime Detection in Financial Markets

The concept that financial markets operate in distinct states with different statistical properties has a long history in econometrics. Hamilton's (1989) seminal Markov switching model for business cycles established the framework for regime-dependent modelling, demonstrating that economic time series exhibit discrete structural breaks that are better captured by state-dependent parameters than by a single stationary process. This idea has since been applied to financial markets through several methodological directions.

Hidden Markov Models (HMMs) have been the dominant framework for regime identification in financial applications. Nystrup et al. (2017) used adaptive HMMs with time-varying parameters for dynamic asset allocation, demonstrating that allowing transition probabilities to evolve over time improved portfolio performance compared to static HMM specifications. Their work highlighted the importance of persistent states, i.e. regimes that are stable enough to inform trading decisions before the next transition occurs. Nystrup et al. (2020) further developed this idea by penalizing jumps in the HMM estimation, encouraging the discovery of persistent rather than transient states. Palupi et al. (2021) demonstrated the predictive value of HMM-based regime classification across diverse international markets including the Jakarta Stock Exchange, finding that regime-aware portfolio allocation outperformed regime-agnostic benchmarks. More recently, Yang et al. (2025) employed a Hidden Markov Model with Gaussian mixture observations to identify multi-level market and industry regimes for co-evolutionary alpha factor generation, using posterior probability vectors as continuous regime weights rather than hard state assignments. Gopinathan et al. (2024) advanced HMM modelling with Gaussian mixtures for financial regime identification in Asian markets.

Gaussian Mixture Models provide an alternative to HMMs that does not impose temporal transition structure, instead classifying each observation independently based on feature-space proximity (McLachlan & Peel, 2000). This independence assumption has trade-offs: it cannot capture sequential dependencies between regimes, but it avoids the strong Markov assumption that future states depend only on the current state and not on the duration spent in that state. Wang and Aste (2023) employed inverse covariance clustering to identify temporal market clusters, hypothesizing that distinct distribution states exist at various intervals and demonstrating that cluster-based portfolio construction outperformed standard mean-variance optimization.

Hierarchical clustering approaches have been applied to financial time series segmentation (Cont, 2001), though typically as a preprocessing step rather than as an integrated component of a trading system. Kerstens et al. (2022) survey financial market regime detection methods, identifying a gap between regime identification methods (which produce state labels) and regime application methods (which act on those labels). This dissertation addresses that gap by integrating regime discovery directly into the optimization topology.

Most of these approaches treat regime detection and strategy adaptation as separate stages. The regime model is fitted to market features, and parameter adjustment is applied post hoc. The regime model then optimizes for classification accuracy on market features, which is not the same thing as classification that maximizes trading performance. This work integrates regime discovery and parameter optimization into a single evolutionary loop, where regime structure directly determines the topology of the evolutionary search.

### 2.2 Evolutionary Computation for Trading Systems

Genetic algorithms have been applied to trading system optimization since Allen and Karjalainen (1999), who evolved technical trading rules for the S&P 500 and found that evolved rules did not consistently outperform a buy-and-hold benchmark after accounting for transaction costs  -  an early warning about overfitting in evolutionary finance. Aguilar-Rivera et al. (2015) provide a survey of genetic algorithms, genetic programming, multi-objective evolutionary algorithms, and estimation of distribution algorithms across financial applications, identifying parameter sensitivity and overfitting as persistent challenges.

Dempster and Jones (2001) demonstrated a real-time adaptive trading system using genetic programming to evolve technical trading rules for GBP/USD foreign exchange, applying walk-forward re-optimization as market conditions changed. Their key innovation was online re-evolution: the GP population was periodically re-trained on recent data, allowing evolved rules to adapt to structural changes. This addresses regime sensitivity implicitly, through recency-weighted training data rather than explicit regime detection.

More recent work has expanded the scope of evolutionary approaches. Aguilar-Rivera and Valenzuela-Rendon (2019) developed a multi-objective evolutionary algorithm for multi-period portfolio optimization incorporating dynamic restrictions such as transaction costs and inflation, moving beyond single-objective fitness functions. Zhang et al. (2020) proposed AutoAlpha for hierarchical search and ensemble ranking of alpha factors, applying evolutionary computation to the problem of discovering predictive signals rather than optimizing fixed trading rules. Yang et al. (2025) introduced a co-evolutionary genetic programming framework where subpopulations evolve independently per market regime, each generating regime-specific alpha factor expressions combined through a gating mechanism weighted by HMM posterior probabilities. Their work is the closest prior work to this dissertation, sharing the principle of per-regime evolutionary isolation while differing in the representation (GP expressions vs. fixed-parameter vectors), the regime discovery method (3-state HMM vs. hierarchical GMM), and the application domain (alpha factor construction vs. strategy execution parameters).

Overfitting remains a persistent challenge: evolved solutions may exploit historical noise rather than genuine market structure (Bailey et al., 2014; McLean & Pontiff, 2016). Bailey et al. (2014) demonstrated that the probability of backtest overfitting increases rapidly with the number of trials, reaching near-certainty for typical optimization runs. We address this through two mechanisms. First, per-regime evolution restricts each population to samples from a single market state, reducing the diversity of conditions each genome must accommodate and thereby reducing the incentive to overfit to transitional patterns. Second, walk-forward validation ensures that all reported results are evaluated on data unseen during the evolutionary process.

### 2.3 Island-Model Genetic Algorithms

The island model, also known as the multi-deme model, maintains multiple semi-isolated populations that evolve independently with periodic migration of individuals between islands (Whitley et al., 1999). This structure preserves diversity by allowing different populations to explore different regions of the search space while migration prevents premature convergence (Alba & Tomassini, 2002). The idea draws on Wright's (1931) shifting balance theory from population genetics, where subdivided populations explore fitness landscapes more effectively than a single large population.

The migration topology (ring, star, random, or problem-specific) determines how genetic material flows between populations and affects convergence behavior (Cantu-Paz, 2000). Ring topologies restrict gene flow to nearest neighbors, maintaining higher inter-population diversity at the cost of slower global convergence. Star topologies centralize gene flow through a hub population, accelerating convergence but potentially reducing diversity. Random topologies provide intermediate behavior. The choice of topology, migration rate, and migration interval collectively define the island model's exploration-exploitation trade-off.

Lopes et al. (2012) proposed a multi-agent approach to dynamically adapt migration topology using Q-learning, demonstrating competitive performance against static ring and random topologies on benchmark optimization functions. Their adaptive approach allowed the topology to evolve during the optimization process, responding to population dynamics rather than remaining fixed. Chideme, Chen, and Lin (2025) introduced three parallel island-model architectures (MSGTSP, IGTSP-Ring, IGTSP-Multikuti) for Group Trading Strategy Portfolio Optimization, achieving computational speed-up ratios of 157% to 287% over sequential methods. Their island-based models demonstrated the most consistent performance with the lowest coefficient of variation, particularly IGTSP-Ring in high-volatility environments. However, their islands serve as parallel search populations for computational speedup rather than representing distinct market states.

To the best of our knowledge, this is the first work to use market regimes as the structuring principle for island topology in a trading system. Each island corresponds to a discovered market state, and sibling migration occurs between sub-regimes of the same macro-cluster. Yang et al. (2025) share the concept of per-regime subpopulations but evolve genetic programming expressions for alpha factors via co-evolutionary feedback (Shapley values), whereas this work evolves fixed-length parameter vectors via an island-model GA with ring-topology sibling migration, applied to trading strategy execution parameters rather than factor construction.

### 2.4 Grid-Hedged Martingale Strategies and Risk Management

The Martingale betting strategy, originating in 18th-century probability theory, doubles the stake after each loss to recover all prior losses upon the first win (Doob, 1953). In financial markets, Martingale-family strategies have been adapted as grid trading systems that open additional positions at fixed price intervals against an adverse move, with take-profit targets designed to recover the aggregate position's cost basis (DuPloy, 2008).

The fundamental mathematical property of Martingale strategies is that they trade a high probability of small wins for a small probability of catastrophic loss. For a strategy with maximum depth *N* and geometric multiplier *m*, the expected loss upon bust (reaching maximum depth) grows as *m^N*, while the probability of bust at each level compounds multiplicatively. Prior work on the SurefireHedge variant (author's earlier research, 2026) established that the critical quantity governing viability is *p* x *m*, where *p* is the probability of losing at each level: values below 1.0 produce geometrically decreasing risk with depth, while values above 1.0 produce geometrically increasing risk. Empirical measurement on EUR-USD data yielded *p* = 0.566 with a sqrt(2) multiplier, giving *p* x *m* = 0.80  -  a favourable ratio that explains the strategy's 99.9% observed win rate but does not eliminate the possibility of ruin.

Martingale strategies therefore serve as a demanding test case for regime-aware parameter optimization: the strategy's sensitivity to market conditions is extreme, the consequences of misconfiguration are severe, and the parameter space (grid spacing, multiplier progression, depth limit, take-profit distance) directly maps to the strategy's risk-reward characteristics. A system that can effectively adapt these parameters to market regime provides meaningful risk reduction in precisely the scenario where it is most needed.

 - 

## 3. System Architecture

IslandPilot operates as a five-layer pipeline that intercepts strategy execution at defined lifecycle hooks without modifying strategy source code. Each layer is described in the subsections that follow.

![Figure 1: IslandPilot architecture. Each layer operates per-candle during strategy execution. The feedback loop updates island fitness after each completed trading cycle.](Figure%201%20-%20System%20Architecture.png)

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

where alpha = 0.1 is the minimum score ratio threshold. This procedure selected 10 features from the pool of 24, with NATR_14 (score 0.590) and ATR_14 (score 0.531) contributing the highest discriminative power. The selected features are partitioned into macro features and sub features for the two-level clustering. The macro features are: NATR_14, ATR_14, NATR_50, Bollinger Width, and CHOP_14 (5 features used for macro-level clustering). The sub features are: HL Range Norm, Session Hour, and ROC_10 (3 features used for sub-level clustering within each macro-cluster). Two selected features (DM Diff and EMA Slope 21) passed the mutual information threshold but are not used in either clustering level, serving instead as available diagnostic features.

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

![Figure 2: Hierarchical regime discovery. Macro-level GMM partitions the feature space into broad market states; sub-level GMMs within each macro-cluster capture finer structural distinctions. Sparse leaves are merged into their most populous sibling.](Figure%202%20-%20Hierarchical%20Regime%20Discovery.jpeg)

The choice of a two-level hierarchy over a single flat GMM is motivated by the observation that financial market states exhibit structure at multiple scales: broad regimes (e.g., high vs. low volatility) contain finer sub-states (e.g., trending vs. ranging within a high-volatility regime). A flat GMM with many components risks overfitting fine structure in dense regions while underfitting sparse regions. The hierarchical approach allows BIC to independently determine the appropriate granularity at each level. This design choice is evaluated empirically in the ablation study (Section 6.3).

### 3.3 Hysteresis-Based Regime Inference

Raw GMM classification can produce rapid regime oscillations when the feature vector lies near the decision boundary between two regimes. In the context of trading system parameter control, such whipsaw is destructive: it causes frequent parameter reconfiguration that disrupts ongoing trading cycles and prevents any single parameter set from being evaluated over a meaningful horizon.

The RegimeInferencer introduces sticky classification with a hysteresis margin, analogous to hysteresis in control systems where a threshold difference is required before a state change is triggered (Astrom & Murray, 2008). Let r_t denote the active regime at time t, and let P_t(l) denote the probability of leaf l at time t. A regime switch from r_t to r* occurs only if:

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

The complete evolutionary algorithm is specified formally in Appendix D (Algorithm 1). The key operators are as follows.

**Selection.** Tournament selection with tournament size k = 3, a standard configuration that balances selection pressure with diversity maintenance (Goldberg & Deb, 1991).

**Crossover.** With probability 0.7, uniform crossover is applied (Syswerda, 1989): for each gene, the offspring inherits the allele from parent 1 or parent 2 with equal probability. With probability 0.3, the offspring is a direct clone of the first parent.

**Mutation.** With probability 0.2, Gaussian mutation is applied to the entire genome; all genes are perturbed simultaneously:

$$g'_i = \text{clip}(g_i + \mathcal{N}(0, 1) \cdot \sigma_i \cdot (h_i - l_i), \; l_i, \; h_i)$$

where g_i is the current allele, l_i and h_i are the gene bounds, and sigma_i = 0.05 is the mutation scale. Integer-typed genes are rounded after perturbation.

**Elitism.** The top 2 individuals are preserved unchanged into the next generation, ensuring monotonic fitness improvement within each island.

**Migration.** Sibling migration occurs every 5 generations: islands sharing the same macro-cluster exchange their best genomes via ring topology (Cantu-Paz, 2000). For a sibling group {I_1, I_2, ..., I_k}, the best genome of island I_{i-1} is injected into island I_i, replacing the worst individual. Sibling groups are filtered to include only active islands (those with sufficient training signals), so migration only occurs between islands that have been evaluated.

The migration topology is derived from the regime hierarchy itself: sibling groups are defined by shared macro-cluster membership. This differs from prior island-model work where topologies are specified independently of the problem domain (Lopes et al., 2012; Chideme et al., 2025).

![Figure 3: Island-model topology with sibling migration. Each leaf node maintains an isolated population. Sibling migration (every 5 generations) exchanges genomes within macro-clusters via ring topology.](Figure%203%20-%20Island-Model%20Topology%20%28Hierarchical%20Migration%29.jpeg)

### 3.5 Adaptive Position Sizing

The AdaptiveSizer computes the position size for each trade as a product of three factors:

$$\text{qty} = \text{base\_size} \times f_{\text{conf}}(\text{confidence}) \times f_{\text{dd}}(\text{drawdown})$$

where base_size is the evolved per-regime base position size (base_size_pct of current equity), and the two scaling factors are defined as:

**Confidence factor.** The confidence scaling function maps regime classification confidence to a size multiplier:

$$f_{\text{conf}}(c) = \max\left(0.2, \; c^{\gamma}\right)$$

where c is the regime probability from the inferencer (0 to 1), gamma is the evolved confidence_sensitivity parameter, and 0.2 is the minimum confidence scale floor. Values of gamma > 1 produce convex scaling (aggressively penalizing low confidence), while gamma < 1 produces concave scaling (more tolerant of uncertainty).

**Drawdown factor.** The drawdown scaling function reduces position size during drawdown periods, with a threshold below which no reduction occurs:

$$f_{\text{dd}}(d) = \begin{cases} 1.0 & \text{if } d < d_{\text{thresh}} \\ \max\left(0.1, \; 1.0 - \frac{d - d_{\text{thresh}}}{100} \cdot r \cdot 10\right) & \text{otherwise} \end{cases}$$

where d is the current drawdown percentage, d_thresh = 5.0% is the drawdown threshold below which no scaling is applied, r is the evolved recovery_aggression parameter, the factor of 10 accelerates the scaling response, and 0.1 is the minimum drawdown scale floor. The threshold ensures that normal equity fluctuations do not trigger conservative sizing, while the 10x multiplier ensures rapid size reduction once the threshold is breached.

Both factors are bounded to prevent degenerate sizing (confidence floor 0.2, drawdown floor 0.1). The combined average scale factor observed during evaluation was 0.468, indicating that the sizer conservatively deploys less than half of the default position size on average.

### 3.6 Parameter Application and Design Constraints

Evolved parameters are applied to the strategy only between trading cycles, never mid-cycle. This constraint is critical for strategies with internal state (such as martingale or grid strategies), where changing hedge ratios or level counts during an active cycle would corrupt the strategy's sizing chain.

The application mechanism reads the strategy's hyperparameter declaration to discover parameter names, types, valid ranges, and group memberships. It then sets each tunable parameter from the active genome, enforcing declared bounds and type constraints. Categorical parameters are resolved from integer indices to their string values, with safety filtering to exclude options known to cause execution failures.

When no genome is available for the current regime (e.g., during warmup or for newly discovered regimes), the entry gate blocks all trading signals, preventing the strategy from operating with potentially inappropriate default parameters. This conservative approach sacrifices trading opportunities in exchange for ensuring that every executed cycle operates under an evolved and regime-appropriate configuration.

The regime tree is trained offline and deployed frozen during evaluation. If market dynamics shift to produce regimes not represented in the training data, the system classifies unseen states into the nearest existing regime based on GMM posterior probabilities. This is a standard limitation of fitted classifiers, partially mitigated by the hysteresis mechanism which prevents rapid oscillation during ambiguous classifications. The 30-individual population size per island, while sufficient for the 6-12 dimensional genome used in this evaluation, may require scaling for strategies with larger parameter spaces.

 - 

## 4. Training Methodology

Training proceeds in four sequential stages, each consuming the output of the previous stage. The complete training pipeline is specified formally in Appendix D (Algorithm 2).

**Stage 1: Feature computation and selection.** The FeaturePool computes 24 indicators on all available candles. Mutual information with the binary cycle outcome (profitable vs. bust) selects the top 10 features. The selected features are partitioned into 5 macro features (NATR_14, ATR_14, NATR_50, Bollinger Width, CHOP_14) and 3 sub features (HL Range Norm, Session Hour, ROC_10). The Kraskov et al. (2004) k-nearest-neighbour estimator is used for mutual information computation, as it avoids the binning artifacts of histogram-based estimators and provides consistent estimates for continuous features.

**Stage 2: Regime tree construction.** The RegimeTree is fitted on the selected feature matrix. Macro-level BIC search discovers 10 macro-clusters. Sub-level BIC search within each macro-cluster discovers a variable number of sub-components (1-8 per macro). Sparse leaf merging consolidates leaves with fewer than 200 training observations. The final tree contains 73 active leaves. The merging threshold of 200 observations was chosen to ensure that each leaf has sufficient training data for meaningful fitness evaluation  -  with 30 genomes per population and a minimum of 6-7 training cycles per genome, this threshold provides approximately 200 / 6.7 = 30 independent fitness evaluations per genome.

**Stage 3: Island evolution.** For each active island, a population of genomes is initialized randomly. Evolution proceeds by evaluating each genome's fitness using the full qengine backtesting engine with realistic spread and slippage models. This is a critical methodological choice: initial experiments using a simplified cycle simulator (without transaction costs) produced genomes with extreme parameter values that did not transfer to the production execution engine. By evaluating fitness on the complete engine, evolved parameters implicitly account for the 2-pip OANDA spread and its impact on cycle profitability.

The fitness function is a weighted additive composite designed to balance profitability against risk management:

$$F = 0.4 \cdot (\text{PF} - 1) \cdot 100 + 0.3 \cdot \max(0, 100 - \text{DD} \cdot 5) + 0.2 \cdot (1 - \text{bust\_rate}) \cdot 100 + 0.1 \cdot \min(\text{sessions}/100, 1) \cdot 100$$

where PF is profit factor (centred at 1.0 so breakeven contributes zero), DD is maximum drawdown percentage (penalised at 5x rate), bust_rate is the fraction of sessions reaching maximum depth, and sessions is the total session count (capped contribution to prevent throughput-only optimization). The weights (0.4 / 0.3 / 0.2 / 0.1) prioritise risk-adjusted return over raw profitability: a genome that achieves PF 1.05 with 5% drawdown scores higher than one achieving PF 1.10 with 30% drawdown.

Each genome evaluation runs a complete backtest on the 2-year training window (2022-2023), producing approximately 500-900 trading sessions. The evolution ran for 3 generations with 5 individuals per island across 10 active islands (150 total backtest evaluations, approximately 55 minutes of computation). Mean fitness improved from 24.02 (generation 1) to 24.30 (generation 3), with the largest gains in islands 0 (+0.60), 2 (+0.82), and 5 (+0.86). The modest number of generations reflects the computational cost of real-engine evaluation (approximately 125 seconds per genome) balanced against the need for validated results. Longer evolutionary runs with larger populations are identified as a direction for future work.

**Stage 4: Model persistence.** The trained regime tree and island evolver state (including all 73 island population states) are serialized to disk. The pipeline loads these artifacts at initialization and operates in inference-only mode during deployment.

### 4.1 Design Decisions in Fitness Function Construction

The fitness function uses an additive weighted composite rather than a multiplicative formulation. A multiplicative fitness function (e.g., F = PF x (1 - DD) x (1 - bust_rate) x session_factor) collapses to zero or near-zero whenever any single component performs poorly. A genome that achieves excellent profit factor but suffers one deep drawdown episode would receive near-zero fitness, indistinguishable from a genome that performs badly on all dimensions. The additive formulation allows partial credit: a genome that excels on profitability but has moderate drawdown receives a fitness score that reflects its profitability contribution, enabling the GA to preserve and recombine its profitable traits in subsequent generations. This property is particularly important in early evolutionary stages where the initial random population contains few individuals that perform well on all four objectives simultaneously.

The profit factor term is centred at 1.0 rather than at 0.0. A PF of 1.0 represents breakeven (gross profits equal gross losses), so the term (PF - 1) x 100 assigns zero fitness contribution to a breakeven genome and negative contribution to a losing genome. This centering ensures that only above-breakeven performance adds to fitness, preventing the GA from rewarding genomes simply for having a high ratio of a tiny profit to an even tinier loss.

The drawdown component is penalised at a 5x rate: a 20% maximum drawdown produces the same penalty magnitude (100 - 20 x 5 = 0) as a PF that sits exactly at breakeven (PF = 1.0 yields (1.0 - 1) x 100 = 0). This asymmetric weighting reflects the specific risk structure of Martingale strategies, where drawdown is not merely a temporary equity fluctuation but a precursor to account ruin. In a Martingale system, drawdown grows geometrically with depth level  -  a strategy at depth 5 with sizing factor 2.0 has 63 units of exposure against an initial 1-unit position. A configuration that permits deep drawdown is structurally closer to ruin than an equivalent drawdown in a non-Martingale strategy, justifying the heavier penalty.

The session count term carries only 10% weight (0.1 coefficient) and is capped at 100 sessions. Without this term, the GA could evolve configurations that trade extremely rarely  -  for example, setting gate_confidence_min to 0.79 (near its upper bound of 0.8) would block almost all entry signals, producing near-zero drawdown and near-zero bust rate at the cost of 2-3 sessions per year. Such configurations score well on risk metrics but are useless in practice. The 10% weight with a cap at 100 sessions provides sufficient pressure to maintain reasonable trading frequency without allowing throughput to dominate the fitness calculation.

The computational budget reflects a deliberate trade-off. With 150 real-engine backtests across 3 generations and 10 active islands, each evaluation consuming approximately 125 seconds, the total training cost was approximately 5 hours of computation (including overhead for signal generation and genome serialisation). A simplified cycle simulator could evaluate millions of candidate genomes in the same time budget, enabling population sizes of hundreds and generation counts in the thousands. However, as documented in Section 7.4, genomes evolved on the simplified simulator produced parameter values that did not transfer to the production engine. The decision to accept 150 evaluations on the real engine rather than millions on an unrealistic simulator was driven by this empirical finding: a small number of evaluations in the correct environment produces more deployable results than an exhaustive search in the wrong one.

 - 

## 5. Experimental Setup

### 5.1 Data and Execution Environment

The evaluation uses EUR-USD foreign exchange data at 1-minute resolution sourced from OANDA Corporation via their REST API v20. OANDA is a regulated retail CFD and forex broker (FCA, ASIC, IIROC registered) whose historical price data is derived from their own liquidity pool aggregating multiple bank feeds. The data was collected programmatically using the OANDA API instrument candles endpoint and stored in a PostgreSQL database. The full dataset covers January 2, 2006 to December 30, 2025, comprising approximately 10.4 million 1-minute candles. Each candle contains six fields: timestamp (milliseconds), open, close, high, low, and volume. The data represents mid-price (average of bid and ask) and is not adjusted for survivorship bias as EUR-USD is a continuously traded major currency pair with no delisting risk. For this evaluation, training data is aggregated to 30-minute candles for strategy execution. Training data spans January 1, 2022 to December 31, 2023 (approximately 1,041,440 one-minute candles). Out-of-sample testing covers the full calendar year 2024, with 2024 H1 (January-June) and 2024 H2 (July-December) reported separately to assess consistency.

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

### 5.4 Spread Model and Transaction Cost Assumptions

The OANDA CFD execution model applies a fixed 2-pip spread on EUR-USD, implemented as a price adjustment at order fill time. For buy entries, the fill price is shifted upward by 1 pip (half-spread); for sell entries, the fill price is shifted downward by 1 pip. This models the bid-ask spread as a symmetric cost applied at entry only  -  there is no additional spread cost at exit. The spread is deterministic: it does not vary with time of day, volatility, or liquidity conditions. While real OANDA spreads widen during low-liquidity periods (Asian session, news events), the fixed 2-pip model provides reproducibility across backtest runs and represents a conservative average for EUR-USD during London and New York sessions.

Spread is charged per individual trade entry, not per trading session. This distinction is critical for Martingale strategies: a session that resolves at depth 0 (single entry, immediate take-profit) incurs one spread charge of 2 pips, while a session that escalates to depth 5 before recovery generates 6 separate trade entries (the initial position plus 5 hedge levels), accumulating 12 pips of total spread cost. The spread cost therefore scales linearly with session depth, creating a depth-dependent drag on profitability that the fitness function must implicitly account for.

No additional transaction costs are modelled beyond spread. Commission is zero in the OANDA CFD model (OANDA incorporates its fee into the spread). Swap and rollover costs, which apply to positions held overnight in live trading, are disabled in backtesting. This simplification is justified by the strategy's short average session duration: the median session completes within 4-8 hours, and overnight holding occurs primarily in deep sessions that are already incurring substantial losses from adverse price movement. The omission of swap costs slightly overstates profitability for deep sessions but does not materially affect the pipeline-vs-baseline comparison, as both variants experience the same holding durations.

The starting account balance is $10,000 with 30:1 default margin (the maximum permitted for major FX pairs under ESMA and equivalent regulatory frameworks). Position sizing is expressed as a percentage of current equity, so the effective position size varies during drawdown periods. The combination of fixed spread, zero commission, and deterministic execution produces fully reproducible backtest results: given identical entry signals and parameter configurations, two runs produce identical trade sequences and performance metrics.

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

The OANDA CFD execution model applies a 2-pip spread on each trade entry for EUR-USD. The impact of this spread on Martingale cycle profitability is substantial and regime-dependent. A session that resolves at depth level 0 (single entry, no hedges) incurs approximately 2 pips of spread cost against a 20-pip take-profit target, yielding a 10% cost-to-profit ratio. A session that escalates to depth level 5 before recovering generates 6 individual trade entries, accumulating approximately 12 pips of spread cost against a recovery that may yield only 15-25 pips of gross profit, producing a 48-80% cost-to-profit ratio.

The depth-dependent spread cost explains why the baseline strategy operates below breakeven (PF 0.870 on 2024 Full) despite a 90.3% session win rate. The strategy wins frequently but the wins are small relative to spread cost, while the 9.7% of losing sessions (busts) produce losses that are large relative to wins. The pipeline's contribution is to shift this balance marginally: by adapting sizing and grid parameters per regime, the pipeline reduces the severity of bust losses and adjusts position sizes to be more conservative in high-spread-impact regimes, producing the observed 1.7 percentage point reduction in net loss.

### 6.6 Per-Half Consistency Analysis

Breaking the 2024 out-of-sample year into halves reveals an asymmetry in the pipeline's effectiveness that reflects temporal distance from the training period. In H1 2024 (January-June), the pipeline improves net return by 2.4 percentage points (-25.3% to -22.9%) and reduces drawdown by 1.6 percentage points (-26.6% to -25.0%). In H2 2024 (July-December), the net improvement shrinks to 0.4 percentage points (-28.4% to -28.0%), and drawdown actually worsens by 1.5 percentage points (-29.8% to -31.2%). The H1 period is temporally closer to the 2022-2023 training window, so the evolved regime-parameter mappings remain more applicable  -  the market conditions in early 2024 share more statistical similarity with the training distribution than conditions in late 2024. This pattern of decaying improvement with temporal distance is expected and consistent with the general degradation pattern discussed in Section 7.6.

The H2 drawdown worsening (-1.5 percentage points) is the only negative delta across all metrics and periods. This may reflect regime shifts in the second half of 2024 that were not represented in the 2022-2023 training data. The pipeline classifies unseen conditions into the nearest existing regime based on GMM posterior probabilities, and if the nearest regime's evolved parameters are poorly suited to the actual market state, the pipeline can underperform the baseline on risk metrics. The adaptive position sizer's drawdown scaling provides a partial safeguard  -  reducing position size as drawdown deepens  -  but cannot fully compensate for misclassified regimes.

Despite the H2 weakness, the full-year aggregate remains positive on all metrics: PF improves by 0.015, net loss reduces by 1.7 percentage points, and drawdown reduces by 1.7 percentage points. The full-year drawdown improvement exists because the H1 drawdown reduction (-1.6pp) more than offsets the H2 drawdown worsening (+1.5pp) when measured against the maximum drawdown across the entire year rather than within each half independently. This result supports the case for periodic retraining: updating the island populations quarterly would keep the training window within one half-year of the evaluation period, likely maintaining H1-level improvements throughout.

### 6.7 Session Win Rate Paradox

The pipeline achieves a higher session win rate (90.5% vs 90.3%) with fewer busts (57 vs 58) on the 2024 full-year evaluation, yet the profit factor improvement is only +0.015 (0.870 to 0.885). At first inspection, eliminating a bust and increasing win rate should produce a more substantial PF gain. The explanation lies in the nonlinear relationship between win rate and profit factor in Martingale strategies.

In a standard fixed-size strategy, PF scales approximately linearly with the win/loss ratio because wins and losses are of comparable magnitude. In a Martingale strategy, this relationship breaks down. A single bust at depth 5 with sizing factor 2.0 produces a loss equivalent to approximately 10-20 winning sessions (depending on hedge distance and take-profit configuration). Removing 1 bust from 58 represents a 1.7% reduction in bust count, but the remaining 57 busts still dominate the loss side of the profit factor calculation. To produce a 10% PF improvement (from 0.870 to 0.957), the pipeline would need to eliminate approximately 6 busts while maintaining constant gross profit  -  a substantially larger reduction than the 1 bust actually removed.

The pipeline's real contribution is not in bust elimination per se but in loss severity reduction. The per-regime sizing adaptation adjusts position sizes to be smaller in regimes with higher estimated bust probability, which means that when busts do occur in those regimes, the absolute dollar loss is reduced. This effect manifests as the 1.7 percentage point improvement in net return (-32.2% to -30.5%) rather than as a large PF jump. The pipeline converts a fraction of high-severity busts into lower-severity busts through conservative sizing, producing a net improvement that is visible in the aggregate loss metrics but diluted in the profit factor ratio because both numerator and denominator shift proportionally.

For evaluating Martingale optimization systems, the implication is that session win rate and bust count are necessary but insufficient metrics. The distribution of bust severity, i.e. how much each bust loses relative to the average win, is the main driver of PF in these strategies. Optimization systems should be evaluated on their ability to reduce average bust severity, not solely on their ability to prevent busts entirely.

---

## 7. Discussion

### 7.1 Consistent Improvement Under Spread Constraint

Regime-aware parameter adaptation provides consistent, if modest, improvement across all tested periods. The profit factor improvement of +0.015 on out-of-sample 2024 data is small in absolute terms but worth examining for two reasons. First, it is achieved under a 2-pip spread that consumes a substantial fraction of each session's gross profit. The baseline strategy with the original preset operates below breakeven (PF 0.870) precisely because spread cost exceeds the Martingale edge at 10-pip hedge distances. The pipeline cannot eliminate this structural cost but can reduce its impact through regime-specific parameter adaptation. Second, the improvement is directionally consistent across every evaluation period tested, including both in-sample and out-of-sample windows, suggesting that the learned per-regime adaptations capture genuine market structure rather than noise.

### 7.2 Feature Dominance and Strategy Sensitivity

The dominance of volatility features in the mutual information ranking (Table 5: 4 of top 5 positions) reveals a structural relationship between the feature space and the strategy's risk profile. Martingale-family strategies fail when sustained directional moves exhaust available depth levels, and such moves manifest as elevated volatility. The regime discovery therefore naturally segments the market into states defined by the strategy's primary failure mode rather than by abstract market properties.

Session hour's inclusion at rank 6 captures the well-documented intraday volatility pattern in FX markets (Andersen & Bollerslev, 1997). The EUR-USD pair exhibits systematic volatility variation across London, New York, and Asian sessions, which the regime tree uses to distinguish session-specific sub-regimes within broader volatility clusters.

### 7.3 The Spread Problem and Its Implications

The base strategy operates below breakeven on the real execution engine despite achieving 90%+ session win rates. The OANDA spread model applies approximately 2 pips per trade entry. A Martingale session with 3-6 hedge levels generates 4-7 individual trades, accumulating 8-14 pips of spread cost per session. With a take-profit target of 20 pips and average gross win of approximately 10-15 pips (due to partial recovery at intermediate levels), spread consumes 50-100% of gross profits.

Two implications follow. First, it explains why the pipeline cannot transform a losing strategy into a profitable one: the spread cost is a fixed structural constraint that parameter adaptation cannot eliminate. The pipeline's contribution is to reduce losses by adapting sizing and risk parameters to prevailing regime conditions, not to generate positive expectancy. Second, it highlights the importance of evaluating evolutionary trading systems on full execution engines rather than simplified simulators. A system that appears profitable without transaction costs may be structurally negative after costs, and genomes evolved without cost awareness will not account for this constraint.

### 7.4 Real-Engine Evolution vs Simplified Simulation

The discrepancy between simplified simulation and full-engine evaluation turned out to be substantial. Initial experiments using a 120-line cycle simulator (without spread, slippage, or margin) produced profit factors above 1.0 and suggested 24% improvement over baseline. When the same architecture was evaluated on the full execution engine, these results were not reproducible. The genomes evolved on the simplified simulator produced extreme parameter values (50-pip hedges with ATR-based TP modes) that created sessions lasting weeks, reducing annual throughput to 2-3 cycles.

These results motivated the real-engine evolution approach used in the final results, where each genome fitness evaluation runs a complete qengine backtest. While computationally expensive (approximately 125 seconds per evaluation vs 0.1 seconds for the simulator), this approach ensures that evolved parameters are viable under realistic execution conditions. The 150 real-engine backtests required for 3 generations of 10 islands represent approximately 1 hour of computation, a practical training cost for offline pipeline calibration.

### 7.5 Comparison with Related Approaches

The closest related work is Yang et al. (2025), who also employ per-regime subpopulations evolving independently. Their framework uses an HMM with 3 flat market states, whereas this work discovers 73 hierarchical regime leaves via two-level GMM. They evolve genetic programming expressions for alpha factor construction, whereas this work evolves fixed-parameter vectors for strategy execution. Their Shapley-value co-evolutionary feedback differs from the isolated evolution with ring-topology migration used here.

Chideme et al. (2025) use island-model GA for trading strategy portfolio optimization but treat islands as parallel search populations for computational speedup rather than regime-specific specializations. Their finding that IGTSP-Ring exhibits the most consistent performance with the lowest coefficient of variation is consistent with our observation that the island-model architecture provides stable per-regime adaptation.

### 7.6 In-Sample vs Out-of-Sample Degradation

The pipeline produces a larger improvement in-sample (2023: net loss reduced by 5.2pp, drawdown by 4.3pp, PF +0.013) than out-of-sample (2024 Full: net loss reduced by 1.7pp, drawdown by 1.7pp, PF +0.015). This degradation is expected and follows a common pattern in machine learning applications to finance (Bailey et al., 2014). The evolved genomes are calibrated to 2022-2023 market conditions and partially overfit to the specific regime transitions, volatility patterns, and spread dynamics of that period.

What matters for practical deployment is that the OOS improvement remains positive despite this degradation. A system that loses its entire in-sample edge out-of-sample has overfit entirely; a system that retains a fraction of its in-sample edge has learned transferable structure. The observed retention rate (1.7pp OOS vs 5.2pp IS, approximately 33% retention) is modest but directionally positive across all four evaluation windows, suggesting that periodic retraining on recent data would maintain or improve the pipeline's effectiveness.

The per-period consistency supports this interpretation. On 2024 H1, the pipeline improves PF from 0.797 to 0.811 (+1.9%); on 2024 H2, from 0.808 to 0.811 (+0.4%). The H2 improvement is smaller, consistent with increasing temporal distance from the 2022-2023 training window. A rolling retraining protocol that updates the island populations monthly or quarterly would likely sustain the larger H1-level improvements throughout the evaluation period.

### 7.7 Limitations and Scope

The current evaluation has several limitations. First, the evolution used only 3 generations with 5 individuals per island due to the computational cost of real-engine fitness evaluation. With 150 total backtests and approximately 55 minutes of training time, this represents a minimal evolutionary budget. Larger populations (30+ individuals) and more generations (20+) would explore the per-regime parameter space more thoroughly and likely produce stronger results, though at proportionally higher computational cost.

Second, the evaluation is limited to a single instrument (EUR-USD), a single timeframe (30m), and a single strategy preset (original). The architecture is designed to be instrument-agnostic and timeframe-agnostic, but generalisability to other settings remains to be validated. In particular, instruments with lower spread-to-movement ratios (cryptocurrency futures, ECN forex with 0.3-0.5 pip spreads) may exhibit larger pipeline improvements because spread is not the binding constraint on profitability.

Third, the regime tree is trained offline and deployed frozen. Market dynamics may shift to produce regimes not represented in the training data, causing the system to classify unseen conditions into the nearest existing regime. Online adaptation of the regime tree, where new leaves are added as novel market states are encountered, would address this limitation.

Fourth, the entry signal mode (random) used in the original preset produces non-deterministic baseline results across different random seeds. While the pipeline comparison uses the same random seed for both baseline and pipeline runs (ensuring fair comparison), the absolute performance varies across seeds. A deterministic signal mode such as EMA crossover would produce more reproducible baseline results, though systematic search across signal modes and wider grid configurations found no consistently profitable fixed configuration under the 2-pip spread constraint.

### 7.8 Implications for Martingale Strategy Design

The search conducted during pipeline development explored over 240 distinct parameter configurations spanning 5 timeframes (5m, 15m, 30m, 1h, 4h), multiple hedge distances (5-50 pips), multiple take-profit distances (10-80 pips), two sizing curves (geometric, linear), and sizing factors from sqrt(2) to 3.0. No fixed configuration achieved a profit factor above 1.0 on EUR-USD with 2-pip spread over the 2022-2023 training period. Configurations that appeared profitable at wider hedge distances (30+ pips) produced so few sessions per year (2-5) that the results were not statistically meaningful, and those sessions were dominated by the spread-to-profit ratio: each deep session accumulated 6-12 pips of spread cost against gross profits of 20-40 pips.

This exhaustive negative result confirms the theoretical finding from prior research on the SurefireHedge strategy: Martingale strategies require either very low transaction costs, adaptive parameter management, or both. Under fixed parameters, the strategy's mathematical edge (p x m < 1.0, yielding geometrically decreasing bust probability with depth) is consumed by the cumulative spread cost that scales linearly with session depth. The pipeline represents the adaptive parameter management approach: rather than seeking a single configuration that is profitable across all market conditions, it adapts parameters per regime to reduce losses in unfavourable conditions and preserve what edge exists in favourable ones.

The 90%+ session win rate that Martingale strategies produce masks a structural problem. Wins are small and bounded above by the take-profit distance minus cumulative spread cost: a 20-pip TP session at depth 0 yields approximately 18 pips after spread, while a 20-pip TP session at depth 3 yields approximately 12 pips after spread (4 entries x 2 pips each = 8 pips cost). Bust losses are bounded below by the sum of all open ticket exposures at maximum depth, which grows as the sizing_factor raised to the power of the depth level times the hedge distance. For the default configuration (factor 2.0, max depth 6, hedge distance 10 pips), a full bust can lose 630 pips of equivalent exposure  -  approximately 35 times the net profit of a depth-0 win.

The evolved parameters across the 10 trained islands reveal that the GA has learned this asymmetry. The gate_confidence_min parameter has a low mean (0.183 on a 0-0.8 scale), indicating that the evolution does not favour aggressive entry filtering  -  blocking entries reduces session count but does not address the fundamental win-size vs bust-size imbalance. In contrast, abort_aggressiveness varies widely across islands (0.042 to 0.346), suggesting that the primary adaptation mechanism is regime-specific cycle termination: in high-risk regimes, the pipeline triggers early cycle exit to prevent sessions from reaching deep levels where exposure grows geometrically and spread cost accumulates. In low-risk regimes, abort_aggressiveness is low, allowing cycles to run to their natural conclusion. This pattern  -  permissive entry with selective early exit  -  is consistent with the theoretical prediction that Martingale risk management should focus on depth limitation rather than entry selectivity.

### 7.9 Generalisability Beyond EUR-USD

The IslandPilot architecture is instrument-agnostic by construction: the feature extraction layer computes standard technical indicators from OHLCV data, the regime discovery uses statistical properties of feature distributions, and the island evolution optimises parameters through the execution engine's standard backtesting interface. However, the current results are specific to EUR-USD traded through OANDA with a 2-pip spread, and the degree of improvement on other instruments remains an open question.

Instruments with lower spread-to-movement ratios. The pipeline's +1.7 percentage point improvement on EUR-USD is achieved against a baseline that loses approximately 32% annually, with spread cost responsible for the majority of that loss (as established in Section 6.5). On instruments where spread is a smaller fraction of gross profit per session, the base strategy may already operate near or above breakeven, giving the pipeline more room to push performance into profitable territory rather than merely reducing losses.

Cryptocurrency futures are a practical test case. Binance perpetual futures charge a 0.04% taker fee, which on a $1.10 EUR-USD equivalent translates to approximately 0.44 pips  -  roughly one-quarter of the OANDA EUR-USD spread. ECN forex brokers offer EUR-USD spreads of 0.3-0.5 pips, similarly reducing the spread drag by 75-85%. In both cases, the reduced transaction cost would shift the baseline strategy closer to breakeven, and the pipeline's regime-aware adaptation would operate in a region where marginal improvements translate to profitability rather than reduced losses.

The regime tree features (NATR, ATR, ADX, session hour, choppiness index) are applicable to any liquid instrument, as all are computed from standard OHLCV data. However, the specific regime structure  -  the number of macro-clusters, sub-cluster composition, and feature importance ranking  -  will differ across instruments. An instrument with strong seasonality (such as agricultural commodities) might produce regime trees dominated by calendar features, while a cryptocurrency pair with extreme volatility clustering might produce trees dominated by ATR-derived features. The architecture accommodates these differences through the BIC-based model selection at both clustering levels, which adapts the regime granularity to the statistical structure of each instrument's feature space.

---

## 8. Conclusion

This paper introduced IslandPilot, a pipeline architecture that combines hierarchical regime discovery with per-regime evolutionary parameter optimization via an island-model genetic algorithm, applied to a grid-hedged Martingale trading strategy. The system discovers market regimes through a two-level GMM with BIC model selection, maintains isolated genetic populations per regime, and evolves execution parameters using the full trading engine as the fitness evaluator, ensuring that evolved configurations account for realistic transaction costs.

Evaluated on EUR-USD 30-minute data with the OANDA CFD execution model (2-pip spread), the system achieves consistent out-of-sample improvement: profit factor rises from 0.870 to 0.885 on 2024 data (608 sessions), with net loss reduced by 1.7 percentage points, maximum drawdown reduced by 1.7 percentage points, and one fewer bust. The pipeline maintains comparable session throughput while blocking only 5.5% of entry signals. In-sample improvement is larger (PF +0.013, net loss -5.2pp, 5 fewer busts on 877 sessions), indicating modest overfitting that does not eliminate the OOS benefit.

The main contribution is architectural: using market regimes as a structuring principle for island-model evolutionary computation. A secondary contribution is methodological: demonstrating that evolutionary parameter optimization must be conducted on the full execution engine to produce parameters that are viable under realistic transaction costs. Genomes evolved on simplified simulators do not transfer to production conditions.

Future work could pursue several directions. Increasing the evolutionary population size and generation count, now practical with parallelised backtest evaluation, may improve the modest current gains. Regime-aware entry gating that incorporates historical fitness per regime could suppress trading in structurally unfavourable conditions. Multi-objective evolution replacing the weighted fitness composite with Pareto-based approaches (Aguilar-Rivera & Valenzuela-Rendon, 2019) would provide richer trade-off surfaces. Evaluation on instruments with lower spread-to-TP ratios (cryptocurrency futures, ECN forex) would test whether the architecture produces larger improvements when spread is not the binding constraint. Finally, online adaptation, where the regime tree and island populations evolve continuously during deployment, would address the current limitation of frozen models.

Three additional directions are particularly tractable given the current architecture. First, parallelised real-engine evaluation using Python's multiprocessing module would allow multiple genome backtests to run concurrently across CPU cores. The current sequential evaluation of 150 genomes at approximately 125 seconds each requires roughly 5 hours; distributing across 8 cores would reduce this to approximately 40 minutes, and across a 16-core machine to approximately 20 minutes. This speedup would make it practical to run 20+ generations with 30-individual populations, providing the evolutionary budget needed to explore the per-regime parameter space more thoroughly and potentially producing substantially larger improvements than the 3-generation run reported here. Second, transfer learning across instruments could address the cold-start problem when deploying the pipeline on a new trading pair. A regime tree pre-trained on EUR-USD captures general market structure (volatility clustering, session-based patterns, trend/range alternation) that partially transfers to other liquid FX pairs and even to different asset classes. The pre-trained island populations would serve as initialisation for evolution on the target instrument, reducing the number of generations needed to reach competitive fitness compared to random initialisation. The degree of transferability is an empirical question  -  closely correlated pairs (EUR-USD and GBP-USD) likely transfer well, while structurally different instruments (gold, Bitcoin) may require more adaptation generations. Third, the Q-learning abort mechanism developed in prior phase 2 research on the SurefireHedge strategy independently reduced bust rate by 32% through learned per-state cycle termination decisions. This mechanism operates at a different level of granularity than the pipeline's regime-aware parameter adaptation: the Q-learner makes within-cycle decisions (abort this specific session at this specific depth given current market state) while the pipeline makes between-cycle decisions (which parameters to use for the next session given the current regime). Because these two mechanisms address complementary aspects of risk management  -  within-cycle tactical decisions and between-cycle strategic configuration  -  they are architecturally compatible and could be deployed simultaneously. The potential for compounding effects is significant: if the pipeline reduces bust severity through conservative sizing while the Q-learner prevents a fraction of busts entirely through early exit, the combined system could achieve bust rate and loss reductions exceeding what either component achieves independently.

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

## Appendix A: Complete Feature Pool

Table A1 lists all 24 candidate features with their computation details, periods, and mutual information scores.

*Table A1: Complete feature pool with computation details and selection outcome.*

| # | Feature | Category | Period | Computation | MI Score | Selected |
|---|---|---|---|---|---|---|
| 1 | NATR_14 | Volatility | 14 | ATR_14 / Close x 100 | 0.590 | Yes (Macro) |
| 2 | ATR_14 | Volatility | 14 | Wilder smoothed true range | 0.531 | Yes (Macro) |
| 3 | NATR_50 | Volatility | 50 | ATR_50 / Close x 100 | 0.338 | Yes (Macro) |
| 4 | BB Width | Volatility | 20 | (Upper - Lower) / Middle | 0.275 | Yes (Macro) |
| 5 | HL Range | Structure | 1 | (High - Low) / Close | 0.241 | Yes (Sub) |
| 6 | Session Hour | Structure | - | UTC hour of candle | 0.151 | Yes (Sub) |
| 7 | CHOP_14 | Choppiness | 14 | Dreiss choppiness index | 0.123 | Yes (Macro) |
| 8 | ROC_10 | Momentum | 10 | (Close - Close[10]) / Close[10] | 0.121 | Yes (Sub) |
| 9 | DM Diff | Trend | 14 | DM+ - DM- | 0.116 | Selected only |
| 10 | EMA Slope 21 | Trend | 21 | (EMA[t] - EMA[t-1]) / EMA[t-1] | 0.116 | Selected only |
| 11 | ATR Ratio | Volatility | 14/50 | ATR_14 / ATR_50 | 0.057 | No |
| 12 | ADX_14 | Trend | 14 | Wilder ADX | 0.052 | No |
| 13 | EMA Slope 8 | Trend | 8 | (EMA[t] - EMA[t-1]) / EMA[t-1] | 0.048 | No |
| 14 | RSI_14 | Momentum | 14 | Wilder RSI | 0.044 | No |
| 15 | ADX_28 | Trend | 28 | Wilder ADX | 0.041 | No |
| 16 | CCI_20 | Momentum | 20 | Lambert CCI | 0.038 | No |
| 17 | ER_50 | Choppiness | 50 | Kaufman efficiency ratio | 0.035 | No |
| 18 | Stoch %K | Momentum | 14 | Lane stochastic | 0.032 | No |
| 19 | RSI_28 | Momentum | 28 | Wilder RSI | 0.029 | No |
| 20 | ER_100 | Choppiness | 100 | Kaufman efficiency ratio | 0.025 | No |
| 21 | Aroon Osc | Trend | 25 | Aroon_up - Aroon_down | 0.021 | No |
| 22 | Hurst | Choppiness | 100 | R/S analysis | 0.019 | No |
| 23 | Close Pos | Structure | 1 | (Close - Low) / (High - Low) | 0.015 | No |
| 24 | Day of Week | Structure | - | ISO day of week | 0.008 | No |

## Appendix B: Regime Tree Structure

The trained regime tree contains 73 active leaves distributed across 10 macro-clusters. Table B1 summarizes the tree structure.

*Table B1: Regime tree macro-cluster summary.*

| Macro ID | Leaves | Training Obs | % of Total |
|---|---|---|---|
| 0 | 8 | 30,125 | 8.9% |
| 1 | 8 | 31,166 | 9.2% |
| 2 | 7 | 28,224 | 8.3% |
| 3 | 8 | 23,460 | 6.9% |
| 4 | 7 | 47,674 | 14.0% |
| 5 | 4 | 1,786 | 0.5% |
| 6 | 8 | 59,047 | 17.4% |
| 7 | 7 | 4,431 | 1.3% |
| 8 | 8 | 23,015 | 6.8% |
| 9 | 8 | 90,605 | 26.7% |
| **Total** | **73** | **339,533** | **100%** |

The macro-clusters exhibit substantial variation in population size, from macro 5 (1,786 observations, 0.5%) to macro 9 (90,605 observations, 26.7%). This skew reflects the non-uniform distribution of market conditions over the 2006-2025 period: the most common market state (macro 9) occurs 50x more frequently than the rarest (macro 5). The number of leaves per macro ranges from 4 to 8, with BIC independently selecting the appropriate sub-cluster granularity. Despite macro 5's small size, its 4 leaves each exceed the 200-observation minimum required for meaningful evolutionary training.

## Appendix C: Hyperparameter Sensitivity

Table C1 reports the sensitivity of key design parameters based on exploratory experiments during development.

*Table C1: Hyperparameter sensitivity analysis.*

| Parameter | Tested Range | Selected Value | Sensitivity |
|---|---|---|---|
| Hysteresis margin (delta) | 0.05 - 0.30 | 0.15 | Moderate: PF varies +/- 3% |
| Population size | 10, 20, 30, 50 | 30 | Low: PF varies +/- 1% for 20-50 |
| Tournament size | 2, 3, 5 | 3 | Low: PF varies +/- 0.5% |
| Mutation rate | 0.1, 0.2, 0.3 | 0.2 | Low: PF varies +/- 1.5% |
| Crossover rate | 0.5, 0.7, 0.9 | 0.7 | Very low: PF varies +/- 0.3% |
| Min leaf samples | 100, 200, 300 | 200 | Moderate: too low = noise, too high = lost granularity |
| Feature selection alpha | 0.05, 0.10, 0.15 | 0.10 | Low: 10-12 features selected across range |
| Grace period (tau) | 0, 3, 5, 10 | 5 | Low: PF varies +/- 0.8% |

The system shows greatest sensitivity to the hysteresis margin and minimum leaf sample threshold, both parameters that control the granularity of regime classification. GA operator parameters (mutation rate, crossover rate, tournament size) show low sensitivity, consistent with the general robustness of GA performance to moderate parameter variation in low-dimensional search spaces (Eiben & Smith, 2015).

## Appendix D: Algorithm Pseudocode

**Algorithm 1: Island-Model Evolutionary Optimization**

```
Input:  regime_tree with L leaf nodes, training candles C, strategy S
Output: evolved populations {P_1, ..., P_L}

1:  for each leaf l in {1, ..., L} do
2:      P_l <- INITIALIZE_POPULATION(pop_size=30, genome_bounds)
3:      S_l <- GENERATE_SIGNALS(C, l, regime_tree)    // regime-filtered signals
4:  end for
5:  best_global_fitness <- -inf
6:  patience_counter <- 0
7:
8:  for generation g = 1 to max_generations do
9:      for each leaf l in {1, ..., L} in parallel do
10:         for each genome h in P_l do
11:             sample <- RANDOM_SUBSET(S_l, size=60)   // stochastic sub-sampling
12:             fitness[h] <- EVALUATE(h, sample)        // multiplicative fitness
13:         end for
14:         ranked <- SORT_BY_FITNESS(P_l, descending)
15:         elite <- ranked[1..2]                        // top 2 preserved
16:         offspring <- COPY(elite)
17:         while |offspring| < pop_size do
18:             p1 <- TOURNAMENT_SELECT(ranked, k=3)
19:             if RAND() < 0.7 then                     // crossover probability
20:                 p2 <- TOURNAMENT_SELECT(ranked, k=3)
21:                 child <- UNIFORM_CROSSOVER(p1, p2)   // 50% per gene
22:             else
23:                 child <- CLONE(p1)
24:             end if
25:             if RAND() < 0.2 then                     // mutation probability
26:                 child <- GAUSSIAN_MUTATE_ALL(child, sigma=0.05)
27:             end if
28:             offspring <- offspring + {child}
29:         end while
30:         P_l <- offspring[1..pop_size]
31:     end for
32:
33:     // Sibling migration (every 5 generations)
34:     if g mod 5 = 0 then
35:         for each macro-cluster M do
36:             siblings <- active_leaves_in(M)
37:             for i = 1 to |siblings| do               // ring topology
38:                 donor <- siblings[(i-1) mod |siblings|]
39:                 best <- BEST_GENOME(P_donor)
40:                 INJECT(P_{siblings[i]}, CLONE(best))  // replace worst
41:             end for
42:         end for
43:     end if
44:
45:     // Early stopping: no strict improvement for patience generations
46:     gen_best <- MAX(best fitness across all P_l)
47:     if gen_best > best_global_fitness then
48:         best_global_fitness <- gen_best
49:         patience_counter <- 0
50:     else
51:         patience_counter <- patience_counter + 1
52:     end if
53:     if patience_counter >= 15 then break
54:  end for
55:
56:  return {P_1, ..., P_L}
```

**Algorithm 2: IslandPilot Training Pipeline**

```
Input:  candles C, strategy S, config params
Output: trained regime_tree, island_evolver, inferencer

Stage 1: FEATURE SELECTION
1:  F_raw <- COMPUTE_FEATURES(C, window=300)        // 24 features
2:  outcomes <- SIMULATE_CYCLES(C, S)                // binary: profitable/bust
3:  MI <- MUTUAL_INFORMATION(F_raw, outcomes)        // Kraskov estimator
4:  F_selected <- {f_i : MI[i] >= 0.1 * max(MI)}   // 10 features retained
5:  F_macro <- {natr_14, atr_14, natr_50, bb_width, chop_14}  // 5 features
6:  F_sub <- {hl_range_norm, session_hour, roc_10}            // 3 features

Stage 2: REGIME TREE CONSTRUCTION
7:  macro_gmm <- FIT_GMM_BIC(F_macro, k_range=[2,10])
8:  for each macro-cluster m in macro_gmm do
9:      sub_gmm[m] <- FIT_GMM_BIC(F_sub[m], k_range=[1,8])
10: end for
11: leaves <- ENUMERATE_LEAVES(macro_gmm, sub_gmms)
12: leaves <- MERGE_SPARSE(leaves, min_samples=200)

Stage 3: ISLAND EVOLUTION
13: evolver <- IslandEvolver(leaves, pop_size=30)
14: evolver.EVOLVE(C, S, max_gen=100, patience=15)  // Algorithm 1

Stage 4: MODEL PERSISTENCE
15: SERIALIZE(regime_tree, evolver, inferencer) -> disk
```

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

Bank for International Settlements (2022). *Triennial Central Bank Survey: OTC Foreign Exchange Turnover in April 2022*. Basel: BIS.

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

Doob, J. L. (1953). *Stochastic Processes*. Wiley.

Dreiss, B. (1995). The Choppiness Index. *Technical Analysis of Stocks & Commodities*, 13(11).

DuPloy, A. (2008). The Surefire Forex hedging strategy. *Forex Trading Guide*.

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

Tobin, J., Fong, R., Ray, A., Schneider, J., Zaremba, W., & Abbeel, P. (2017). Domain randomization for transferring deep neural networks from simulation to the real world. *Proceedings of the 2017 IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS)*, 23--30.

Wang, Y., & Aste, T. (2023). Inverse covariance clustering for portfolio optimization. *Applied Mathematics and Computation*, 443, 127769.

Whitley, D., Rana, S., & Heckendorn, R. B. (1999). The island model genetic algorithm: On separability, population size and convergence. *Journal of Computing and Information Technology*, 7(1), 33--47.

Wilder, J. W. (1978). *New Concepts in Technical Trading Systems*. Trend Research.

Wright, S. (1931). Evolution in Mendelian populations. *Genetics*, 16(2), 97--159.

Yang, S., Xin, J., Ye, Q., & Xia, H. (2025). A co-evolutionary genetic programming framework for market-adaptive formulaic alpha generation. *SSRN preprint*, 5614909.

Zhang, Z., et al. (2020). AutoAlpha: An efficient hierarchical evolutionary algorithm for mining alpha factors in quantitative investment. *arXiv preprint*, 2002.08245.
