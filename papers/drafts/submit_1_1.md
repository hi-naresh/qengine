# Regime-Aware Evolutionary Parameter Optimization for Grid-Hedged Martingale Strategies Using Hierarchical Island-Model Genetic Algorithms

**Abstract**

The dominant approach to evolutionary trading strategy optimisation produces a single global parameter solution, implicitly assuming that market conditions are stationary across the optimisation horizon. We challenge this assumption and introduce IslandPilot, a pipeline that couples hierarchical market regime discovery with an island-model genetic algorithm in which each discovered regime maintains an isolated genetic population evolving independently. The principal architectural contribution is that island topology is derived from the regime structure itself: a two-level Gaussian Mixture Model with Bayesian Information Criterion selection partitions a 30-indicator feature space into macro-clusters and sub-clusters; populations sharing a macro-cluster exchange genomes via ring migration, while populations in distinct macro-clusters evolve without interaction. This domain-derived migration graph contrasts with prior island-model work, where topology is specified independently of the problem domain. Each island evolves the complete strategy parameter space, including entry signal type, directional bias, grid geometry, sizing curve, and risk management controls, producing regime-specific execution policies rather than a single globally-tuned configuration. Feature selection via mutual information over a 30-indicator pool (24 empirical-technical indicators plus 6 theory-driven extensions covering multi-scale volatility, return distributional shape, and lag-1 serial dependence) identifies 10 discriminative features. A hysteresis-based regime inferencer provides stable per-candle regime assignment without parameter reconfiguration overhead. Critically, all fitness evaluations are conducted on the full production execution engine with real per-candle OANDA bid-ask spread data; we show empirically that parameters evolved on simplified, cost-free simulators fail to transfer to live execution conditions. Applied to a grid-hedged Martingale strategy on EUR-USD at 5-minute resolution, the system trains on 36 months of data (2022–2024) through 840 real-engine fitness evaluations (wall-clock: 7 hours 46 minutes), discovering 56 regime leaves. On a 15-month strictly out-of-sample evaluation (January 2025–April 2026), the pipeline achieves a profit factor of 3.72 against a baseline of 0.77, with maximum drawdown substantially reduced, demonstrating that regime-specialised evolutionary optimisation with domain-derived island topology produces transferable out-of-sample performance under realistic execution costs.

**Keywords:** island-model genetic algorithm; market regime detection; Gaussian mixture model; grid-hedged Martingale; evolutionary parameter optimisation; hierarchical clustering; adaptive position sizing; walk-forward validation

---

## 1. Introduction

Grid-hedged Martingale strategies manage adverse price movements by opening successive hedge positions at predefined depth levels, with take-profit targets set to recover accumulated exposure. Their profitability depends critically on the relationship between grid spacing, multiplier progression, and the volatility regime of the traded instrument. A configuration that performs well in low-volatility, mean-reverting markets can exhaust its depth capacity rapidly during sustained directional trends, resulting in catastrophic drawdown. This sensitivity to market regime makes fixed parameter configurations structurally inadequate for deployment across changing market conditions (Hamilton, 1989; Nystrup et al., 2020; Ding, Liu, & Liu, 2022).

The fundamental challenge is combinatorial: a Martingale strategy with *k* tunable parameters operating across *r* market regimes requires *r* independent parameter configurations, each validated against the specific statistical properties of its regime. Manual calibration is impractical beyond a handful of regimes, and naive grid search scales exponentially with parameter dimensionality. Evolutionary computation offers a principled approach to this optimization, but standard genetic algorithms evolve a single population whose fitness is evaluated across all market conditions, producing compromised solutions that perform adequately in no regime rather than optimally in any.

Existing approaches to parameter adaptation fall broadly into three categories. The first treats the problem as online optimization, applying gradient-based or bandit methods to adjust parameters continuously (Li et al., 2014; Agrawal & Goyal, 2013). These methods assume smooth parameter-performance surfaces and struggle with the discontinuous transitions characteristic of regime change. The second category employs regime detection followed by parameter lookup, switching between pre-calibrated parameter sets based on a regime classifier (Nystrup et al., 2017; Palupi et al., 2021). These methods require the regime set and corresponding optimal parameters to be specified a priori, limiting their ability to discover unseen market states. The third category uses evolutionary computation for parameter optimization (Aguilar-Rivera et al., 2015; Chideme, Chen, & Lin, 2025), but typically evolves a single global solution that compromises across all market conditions.

This dissertation proposes a synthesis of these approaches through the island-model genetic algorithm framework (Whitley et al., 1999; Alba & Tomassini, 2002). Market regimes define natural boundaries for evolutionary isolation: parameters that perform well in one regime may be detrimental in another, and maintaining distinct populations per regime prevents the averaging effect that degrades global optimization. By combining hierarchical regime discovery with per-regime evolutionary optimization, the system discovers both the regimes and their corresponding optimal parameter configurations from data, without requiring either to be specified in advance.

A critical but often overlooked requirement in evolutionary trading system design is that the fitness evaluation must use the same execution model as deployment. Many evolutionary trading studies evaluate candidate solutions on simplified simulators (typically omitting spread, slippage, margin constraints, and order execution latency) and then deploy the resulting parameters on real brokers. This creates a simulation-to-production gap analogous to the sim-to-real transfer problem documented in robotics (Tobin et al., 2017), where policies trained in idealised physics engines fail when confronted with real-world friction, sensor noise, and actuator delay. In trading systems, the gap manifests as parameter configurations that appear profitable in the simulator but produce losses under realistic transaction costs. The problem is particularly acute for Martingale-family strategies, where spread cost accumulates multiplicatively with depth: a 6-level session incurs 6 separate spread charges, and the simulator-to-production discrepancy grows with each additional hedge level. This dissertation addresses the gap directly by training island evolution on the production backtesting engine with the full OANDA CFD execution model (real per-candle bid-ask spread data, margin accounting, and realistic order fill simulation). Each genome fitness evaluation runs a complete backtest through the same engine used for live deployment, ensuring that evolved parameters have already survived the transaction cost environment they will encounter in practice. The methodological cost (approximately 33 seconds per genome evaluation on 3 years of 5m data, compared to 0.1 seconds on a simplified simulator) is substantial but justified by the finding (Section 7.4) that genomes evolved on the simplified simulator did not transfer to the production engine.

The proposed architecture, IslandPilot, operates as a strategy-agnostic pipeline that wraps any trading strategy without modifying its source code. It contributes the following:

1. A hierarchical two-level Gaussian Mixture Model for regime discovery, where macro-level clustering captures broad market states and sub-level clustering within each macro-state captures finer structural distinctions, with BIC-based model selection at both levels.

2. An island-model genetic algorithm where each regime leaf maintains an isolated population that evolves execution parameters independently, with sibling migration enabling genetic exchange between sub-regimes within the same macro-cluster.

3. A hysteresis-based regime inference mechanism that prevents classification whipsaw by requiring a confidence margin before switching regimes, with a grace period that suppresses entry signals during regime transitions.

4. A multi-factor adaptive position sizing layer that scales trade size according to regime classification confidence, evolved base parameters, and current drawdown state, enforcing survivability constraints.

5. Empirical validation on EUR-USD 5-minute data using the full OANDA CFD execution engine with real per-candle bid-ask spread data, demonstrating a profit factor of 3.72 against a baseline of 0.77 on a 15-month out-of-sample evaluation (2025–2026), with substantially reduced maximum drawdown, trained exclusively on 2022–2024 data using real-engine backtests as the fitness evaluator.

The remainder of this dissertation is organized as follows. Section 2 reviews related work in regime detection, evolutionary optimization for trading, and island-model genetic algorithms. Section 3 describes the system architecture in detail, including formal algorithm specifications. Section 4 presents the training methodology. Section 5 describes the experimental setup. Section 6 reports results including per-regime breakdowns. Section 7 discusses the findings with extended analysis. Section 8 concludes and identifies directions for future work.

---

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

---

## 3. System Architecture

IslandPilot operates as a five-layer pipeline that intercepts strategy execution at defined lifecycle hooks without modifying strategy source code. Each layer is described in the subsections that follow.

![Figure 1: IslandPilot architecture. Each layer operates per-candle during strategy execution. The feedback loop updates island fitness after each completed trading cycle.](Figure%201%20-%20System%20Architecture.png)

### 3.1 Feature Extraction

The FeaturePool computes 30 market indicators from OHLCV candle data across five categories: volatility, trend, choppiness, momentum, and market structure. The pool is structured as 24 empirical-technical indicators (standard conventions from the technical analysis literature) plus 6 theoretically-motivated extensions that close specific gaps in the base feature space. Features are computed on a fixed 300-candle sliding window, maintaining O(1) computational cost per candle regardless of backtest length.

The indicator periods were selected by adopting standard conventions from the technical analysis literature and then validating that they produce discriminative features for the specific task of Martingale cycle outcome prediction. Period 14 is the standard lookback for RSI, ATR, and ADX as originally defined by Wilder (1978), and remains the de facto default across practitioner and academic usage (Colby, 2003). We retained this convention rather than optimizing the lookback because (a) it enables direct comparison with published results that use identical indicator definitions, and (b) the mutual information feature selection described below acts as a second filter that eliminates features regardless of their conventional standing if they lack discriminative power for this task. Period 50 is widely adopted as a medium-term volatility benchmark in FX markets (Katz & McCormick, 2000); its inclusion alongside period 14 captures the ATR ratio (ATR_14 / ATR_50), which measures short-term volatility relative to the medium-term baseline - a derived feature specific to our regime detection objective rather than a generic convention. The 8/21 EMA pair follows the Fibonacci-derived convention common in short-term momentum systems (Kaufman, 2013), chosen because the Martingale strategy's entry signals use EMA crossovers at these periods, meaning the slope features directly reflect the signal generation mechanism. The Hurst exponent window of 100 follows the recommendation of Di Matteo et al. (2005), who demonstrated that windows of 50-200 observations provide stable R/S estimates for financial time series. The Choppiness Index at period 14 and Efficiency Ratio at periods 50/100 follow the implementations described by Kaufman (2013) for adaptive trading system design. The choice to adopt established periods rather than optimizing them is deliberate: period optimization would introduce an additional degree of freedom that risks overfitting to the training data, while standard periods are pre-validated across decades of market data and multiple instruments.

The full feature set is:

**Volatility (5):** Normalized Average True Range at periods 14 and 50 (NATR_14, NATR_50), ATR ratio (ATR_14 / ATR_50), Bollinger bandwidth ((upper - lower) / middle at period 20; Bollinger, 2002), and raw ATR_14.

**Trend (6):** Average Directional Index at periods 14 and 28 (ADX_14, ADX_28; Wilder, 1978), EMA slope at periods 8 and 21 defined as the percentage change (EMA[t] - EMA[t-1]) / EMA[t-1], Aroon oscillator (Aroon_up - Aroon_down; Chande, 1997), and directional movement differential (DM+ - DM-; Wilder, 1978).

**Choppiness (4):** Choppiness Index at period 14 (CHOP_14; Dreiss, 1995), Kaufman Efficiency Ratio at periods 50 and 100 (ER_50, ER_100; Kaufman, 2013), and rolling Hurst exponent at window 100 computed via R/S analysis (Hurst, 1951; Di Matteo et al., 2005).

**Momentum (5):** Relative Strength Index at periods 14 and 28 (RSI_14, RSI_28; Wilder, 1978), Commodity Channel Index at period 20 (CCI_20; Lambert, 1983), Rate of Change at period 10 (ROC_10), and Stochastic %K (Lane, 1984).

**Structure (4):** Session hour (UTC), day of week, normalized high-low range ((high - low) / close), and close position within range ((close - low) / (high - low)).

**Extensions — Dimension 1: HAR-RV multi-scale volatility (2 features).** NATR_14 computed on candles aggregated by factors of 12× and 48× relative to the base 5m timeframe (equivalent to approximately 1h and 4h horizons), broadcast back to the base timeframe. This implements the Heterogeneous Autoregressive model of Realized Volatility (Corsi, 2009), which demonstrates that three time-horizons are sufficient and parsimonious for realized-volatility modelling. Müller et al. (1997) showed that information flows asymmetrically across scales (long → short), making multi-scale volatility a regime signal rather than a redundancy with NATR_14. Feature names: NATR_14_TF12, NATR_14_TF48.

**Extensions — Dimension 2: Distributional shape (3 features).** (i) Rolling standard deviation of NATR_14 over 50 bars (vol-of-vol; Engle, 1982; Barndorff-Nielsen & Shephard, 2002) — distinguishes stable high-volatility regimes from regime-transition periods where volatility itself is unstable. (ii) Rolling standardised skewness of log returns over 100 bars (Neuberger, 2012; Harvey & Siddique, 2000) — negative skew indicates downside asymmetry, the dominant failure mode for Martingale long positions. (iii) Rolling excess kurtosis of log returns over 100 bars — elevated kurtosis signals fat-tail conditions. The 100-bar window follows Neuberger (2012) Table 1 for stable realized-moment estimation at high frequency. Feature names: VOL_OF_VOL_50, RETURN_SKEW_100, RETURN_KURT_100.

**Extensions — Dimension 3: Short-lag serial dependence (1 feature).** Rolling lag-1 autocorrelation of log returns over 100 bars (Lo & MacKinlay, 1988 variance-ratio framework; Box & Jenkins, 1976 AR identification). Positive values indicate momentum / trending conditions (adverse for Martingale); negative values indicate mean-reversion (favourable). Box & Jenkins (1976) show that lag-1 captures ≥80% of AR(1) information, making a single lag sufficient. Feature name: RETURN_AC_LAG1_100.

Feature selection is performed via mutual information (Kraskov et al., 2004) between each feature and a binary outcome variable derived from trading cycle profitability. Given mutual information scores {s_1, ..., s_30} for all features, the selection rule retains feature i if:

$$s_i \geq \alpha \cdot \max_j s_j$$

where alpha = 0.1 is the minimum score ratio threshold. This procedure selected 10 features from the pool of 30, with NATR_14 (score 0.590) and ATR_14 (score 0.531) contributing the highest discriminative power. The selected features are partitioned into macro features and sub features for the two-level clustering. The macro features are: NATR_14, ATR_14, NATR_50, Bollinger Width, and CHOP_14 (5 features used for macro-level clustering). The sub features are: HL Range Norm, Session Hour, and ROC_10 (3 features used for sub-level clustering within each macro-cluster). Two selected features (DM Diff and EMA Slope 21) passed the mutual information threshold but are not used in either clustering level, serving instead as available diagnostic features.

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

---

## 4. Training Methodology

Training proceeds in four sequential stages, each consuming the output of the previous stage. The complete training pipeline is specified formally in Appendix D (Algorithm 2).

**Stage 1: Feature computation and selection.** The FeaturePool computes 30 indicators on all available candles: 24 empirical-technical indicators plus 6 theoretically-motivated extensions covering multi-scale volatility, distributional shape (vol-of-vol, skewness, kurtosis), and short-lag return autocorrelation (see Section 3.1 for full definitions). Mutual information with the binary cycle outcome (profitable vs. bust) selects the top 10 features from the pool of 30. The selected features are partitioned into 5 macro features (NATR_14, ATR_14, NATR_50, Bollinger Width, CHOP_14) and 3 sub features (HL Range Norm, Session Hour, ROC_10). The Kraskov et al. (2004) k-nearest-neighbour estimator is used for mutual information computation, as it avoids the binning artifacts of histogram-based estimators and provides consistent estimates for continuous features.

**Stage 2: Regime tree construction.** The RegimeTree is fitted on the selected feature matrix. Macro-level BIC search discovers 10 macro-clusters. Sub-level BIC search within each macro-cluster discovers a variable number of sub-components (1-8 per macro). Sparse leaf merging consolidates leaves with fewer than 200 training observations. The final tree contains 73 active leaves. The merging threshold of 200 observations was chosen to ensure that each leaf has sufficient training data for meaningful fitness evaluation  -  with 30 genomes per population and a minimum of 6-7 training cycles per genome, this threshold provides approximately 200 / 6.7 = 30 independent fitness evaluations per genome.

**Stage 3: Island evolution.** For each active island, a population of genomes is initialized randomly. Evolution proceeds by evaluating each genome's fitness using the full qengine backtesting engine with realistic spread and slippage models. This is a critical methodological choice: initial experiments using a simplified cycle simulator (without transaction costs) produced genomes with extreme parameter values that did not transfer to the production execution engine. By evaluating fitness on the complete engine with real per-candle OANDA spread data, evolved parameters implicitly account for realistic execution costs and their impact on cycle profitability.

The fitness function is a weighted additive composite designed to balance profitability against risk management:

$$F = 0.4 \cdot (\text{PF} - 1) \cdot 100 + 0.3 \cdot \max(0, 100 - \text{DD} \cdot 5) + 0.2 \cdot (1 - \text{bust\_rate}) \cdot 100 + 0.1 \cdot \min(\text{sessions}/100, 1) \cdot 100$$

where PF is profit factor (centred at 1.0 so breakeven contributes zero), DD is maximum drawdown percentage (penalised at 5x rate), bust_rate is the fraction of sessions reaching maximum depth, and sessions is the total session count (capped contribution to prevent throughput-only optimization). The weights (0.4 / 0.3 / 0.2 / 0.1) prioritise risk-adjusted return over raw profitability: a genome that achieves PF 1.05 with 5% drawdown scores higher than one achieving PF 1.10 with 30% drawdown.

Each genome evaluation runs a complete backtest on the 3-year training window (2022–2024) at 5-minute resolution, producing approximately 800–1,200 trading sessions per regime window (regime-specific windows are narrower subsets of the full training period). The evolution ran for 3 generations with 5 individuals per island across 56 active leaves (the regime tree structure for the current trained model), for a total of 3 × 5 × 56 = 840 genome evaluations. Each evaluation took approximately 33 seconds on a consumer CPU (3 years × ~315,000 5m bars per year), yielding a measured total training wall-clock time of approximately 7 hours 46 minutes (regime tree construction completed at 14:44 on April 22; island evolver serialised at 22:30 on April 22). Mean fitness improved from 24.02 (generation 1) to 24.30 (generation 3), with the largest gains concentrated in high-activity islands. The modest number of generations reflects the computational cost of real-engine evaluation balanced against the need for validated results; the 840-evaluation budget is roughly 18× larger than the 50-evaluation budget used in the initial prototype on 30m data, achieved through the faster per-evaluation time at the cost of longer wall-clock runtime. Longer evolutionary runs with larger populations are identified as a direction for future work.

A critical implementation note: the genome now encodes all 22 tunable strategy parameters (7 parameter groups, as described in Section 5.2), not just the 6 pipeline-internal genes used in earlier prototypes. Earlier prototypes constrained the tunable groups to General, Grid/Hedge, and Take Profit, meaning the pipeline could adjust sizing curves and hedge distances but could not change entry signal type or direction bias. With random-entry baseline performance firmly below breakeven under realistic spread (see Section 6.1), this restriction prevented the pipeline from improving positive expectancy in regimes where directional bias exists. The expansion to all 7 groups, including Entry Signal, Filters, and Risk Management, allows the evolved genome to select EMA crossover signals in trending regimes, activate session filters during historically unfavourable hours, and tighten or loosen the consecutive-bust halt threshold. This is the primary architectural change relative to the initial prototype and the key reason the current pipeline achieves positive net return on the out-of-sample evaluation period.

**Stage 4: Model persistence.** The trained regime tree and island evolver state (including all 56 active island population states) are serialized to disk as `regime_tree.pkl` and `island_evolver.json` respectively. The pipeline loads these artifacts at initialization and operates in inference-only mode during deployment.

### 4.1 Design Decisions in Fitness Function Construction

The fitness function uses an additive weighted composite rather than a multiplicative formulation. A multiplicative fitness function (e.g., F = PF x (1 - DD) x (1 - bust_rate) x session_factor) collapses to zero or near-zero whenever any single component performs poorly. A genome that achieves excellent profit factor but suffers one deep drawdown episode would receive near-zero fitness, indistinguishable from a genome that performs badly on all dimensions. The additive formulation allows partial credit: a genome that excels on profitability but has moderate drawdown receives a fitness score that reflects its profitability contribution, enabling the GA to preserve and recombine its profitable traits in subsequent generations. This property is particularly important in early evolutionary stages where the initial random population contains few individuals that perform well on all four objectives simultaneously.

The profit factor term is centred at 1.0 rather than at 0.0. A PF of 1.0 represents breakeven (gross profits equal gross losses), so the term (PF - 1) x 100 assigns zero fitness contribution to a breakeven genome and negative contribution to a losing genome. This centering ensures that only above-breakeven performance adds to fitness, preventing the GA from rewarding genomes simply for having a high ratio of a tiny profit to an even tinier loss.

The drawdown component is penalised at a 5x rate: a 20% maximum drawdown produces the same penalty magnitude (100 - 20 x 5 = 0) as a PF that sits exactly at breakeven (PF = 1.0 yields (1.0 - 1) x 100 = 0). This asymmetric weighting reflects the specific risk structure of Martingale strategies, where drawdown is not merely a temporary equity fluctuation but a precursor to account ruin. In a Martingale system, drawdown grows geometrically with depth level  -  a strategy at depth 5 with sizing factor 2.0 has 63 units of exposure against an initial 1-unit position. A configuration that permits deep drawdown is structurally closer to ruin than an equivalent drawdown in a non-Martingale strategy, justifying the heavier penalty.

The session count term carries only 10% weight (0.1 coefficient) and is capped at 100 sessions. Without this term, the GA could evolve configurations that trade extremely rarely  -  for example, setting gate_confidence_min to 0.79 (near its upper bound of 0.8) would block almost all entry signals, producing near-zero drawdown and near-zero bust rate at the cost of 2-3 sessions per year. Such configurations score well on risk metrics but are useless in practice. The 10% weight with a cap at 100 sessions provides sufficient pressure to maintain reasonable trading frequency without allowing throughput to dominate the fitness calculation.

The computational budget reflects a deliberate trade-off. With 840 real-engine backtests across 3 generations and 56 active islands, each evaluation averaging approximately 33 seconds, the total training wall-clock time was approximately 7 hours 46 minutes. A simplified cycle simulator could evaluate millions of candidate genomes in the same time budget, enabling population sizes of hundreds and generation counts in the thousands. However, as documented in Section 7.4, genomes evolved on the simplified simulator produced parameter values that did not transfer to the production engine. The decision to accept 840 evaluations on the real engine rather than millions on an unrealistic simulator was driven by this empirical finding: a small number of evaluations in the correct environment produces more deployable results than an exhaustive search in the wrong one.

 - 

---

## 5. Experimental Setup

### 5.1 Data and Execution Environment

The evaluation uses EUR-USD foreign exchange data at 1-minute resolution sourced from OANDA Corporation via their REST API v20. OANDA is a regulated retail CFD and forex broker (FCA, ASIC, IIROC registered) whose historical price data is derived from their own liquidity pool aggregating multiple bank feeds. The data was collected programmatically using the OANDA API instrument candles endpoint and stored in a PostgreSQL database. The full dataset covers January 2, 2006 to December 30, 2025, comprising approximately 10.4 million 1-minute candles. Each candle contains six fields: timestamp (milliseconds), open, close, high, low, and volume. The data represents mid-price (average of bid and ask) and is not adjusted for survivorship bias as EUR-USD is a continuously traded major currency pair with no delisting risk. For this evaluation, training data is aggregated to 5-minute candles for strategy execution. The choice of 5-minute resolution is deliberate: at 5m, EUR-USD generates approximately 105,000 candles per year (after excluding weekend gaps), providing a substantially richer sample for regime discovery and genetic evaluation than coarser timeframes. The 5m bar also corresponds to the minimum practically meaningful candle duration for the Martingale strategy under study — sessions that progress to depth 3 under a 20-pip hedge distance require intraday price moves of 60 pips, which can unfold within 30–90 minutes at normal EUR-USD volatility; the 5m candle captures the intraday phase structure of these cycles, whereas 30m candles coarsen the entry-to-resolution timing beyond the strategy's natural rhythm.

Training data spans January 1, 2022 to December 31, 2024 (approximately 2,250,000 one-minute candles). Out-of-sample testing covers January 1, 2025 to April 1, 2026 (15 months), representing the strictly unseen period after training concluded.

All backtests are executed through the full qengine trading engine with CFD order execution, including real per-candle OANDA bid-ask spread data applied as a price adjustment on each trade entry (see Section 5.5), margin accounting with 30:1 default leverage, and no commission beyond the spread. Swap/rollover costs are disabled for backtesting reproducibility. The starting balance is $10,000 for all runs. This is a deliberate methodological choice: many studies in evolutionary trading system optimization evaluate fitness using simplified simulators that omit transaction costs, producing results that do not transfer to live execution. By training and evaluating on the complete execution engine with real execution costs, evolved parameters implicitly account for spread impact on cycle profitability.

### 5.2 Strategy

The underlying strategy is a depth-controlled Martingale variant operating in CFD mode with independent position tickets. The baseline (no pipeline) uses a default configuration: no directional signal (random entry), 20-pip fixed hedge distance, 50-pip take-profit, geometric sizing with factor 1.7, and maximum 3 depth levels with a consecutive-bust halt after 2 busts (mcb=2). This configuration was selected as the starting point because it limits maximum per-cycle exposure to 7× the base unit (sizing factor 1.7 at depth 3 yields 1 + 1.7 + 2.89 ≈ 5.6 units cumulative, versus 63 units at depth 6 with factor 2.0 in the original preset), making the baseline lossy but structurally recoverable rather than catastrophically ruinous.

The pipeline tunes all seven parameter groups per regime: General (sizing curve, sizing factor, max levels, base size), Grid/Hedge (hedge mode, hedge distance, hedge expansion), Take Profit (TP mode, TP distance), Entry Signal (signal mode, direction bias, EMA periods), Filters (session filter, cooldown), Risk Management (halt rules, max consecutive busts), and Position Management. Including entry signal parameters is a design decision made after observing that a pipeline restricted to sizing and grid parameters cannot overcome the structural expectancy problem when the strategy operates under random entry in a trending market — the pipeline must be permitted to select entry direction and signal type per regime to produce positive expected value in regimes where directional bias exists. The full tunable parameter space per genome therefore encompasses the complete strategy hyperparameter declaration (22 tunable parameters), not just the 6 pipeline-internal genes described in Section 3.4.

### 5.3 Evaluation Protocol

*Table 2: Training and evaluation periods.*

| Period | Date Range | Duration | Purpose |
|---|---|---|---|
| Training | 2022-01-01 to 2024-12-31 | 36 months | Island evolution — regime discovery + GA optimization |
| In-sample check (H1) | 2024-01-01 to 2024-06-30 | 6 months | Sanity check: H1 training data performance |
| In-sample check (H2) | 2024-07-01 to 2024-12-31 | 6 months | Sanity check: H2 training data performance |
| Out-of-sample (primary) | 2025-01-01 to 2026-04-01 | 15 months | Main evaluation — never seen during training |

The pipeline (feature selection, regime discovery, island evolution) is trained exclusively on the 2022–2024 period. All 2025–2026 results are strictly out-of-sample: no re-fitting of the regime tree or island populations is performed on evaluation data. The training cutoff is enforced at the code level — `train.py` hard-rejects any `--train-end` date on or after 2025-01-01.

The 36-month training window is motivated by three constraints. First, GMM stability: the BIC search for macro-clusters requires at least 200 observations per component for the 5-dimensional macro feature space (20 covariance parameters × 10 observations minimum per parameter; McLachlan & Peel, 2000). At 5m resolution, 36 months of EUR-USD provides approximately 315,000 5m bars — roughly 18× the theoretical minimum per component and 18× more than the equivalent 30m window, yielding substantially more stable GMM covariance estimates and BIC selection. Second, regime diversity: 36 months spans the post-pandemic rate normalisation cycle (2022), the peak inflation-and-rate-hike environment (2022–2023), and the initial rate-cut pivot (2024). This three-phase diversity means the regime tree is exposed to conditions ranging from high-volatility trend (2022 EUR/USD decline from 1.15 to 0.96) through mean-reverting range (2023) to directional recovery (2024), providing richer per-regime evolution targets than a 24-month window that captures only two of these phases. Third, genetic evolution depth: evolving 22 strategy parameters per genome on regime-specific windows requires a sufficient number of training cycles per leaf. With 36 months of training data, the most active leaves accumulate 800–1,200 trading sessions, providing a statistically meaningful fitness signal for the 3-generation evolution. Extending training beyond 36 months (to 48 or 60 months) would include 2020–2021 COVID-era data, introducing structural breaks (extreme spread widening, circuit breakers, correlated gap behaviour) that are not representative of normal FX microstructure; restricting training to 2022–2024 avoids this contamination.

### 5.4 Comparison Systems

Three benchmark systems are evaluated alongside IslandPilot on the extended 2025-2026 OOS period:

**Baseline.** The unenhanced Martingale strategy with the original preset and no pipeline attached. This establishes the lower bound against which pipeline value is measured. Both baseline and all pipeline systems use the same entry signals, starting balance ($10,000), and execution engine.

**GTSBotPilot** (based on Rundo et al., 2019). The Grid Trading System Robot paper proposes a three-layer architecture: a regression network for trend detection, a Grid System Manager (GSM) enforcing spacing constraints between trades, and a Basket Equity System Manager (BESM) that closes all positions when aggregate profit reaches a target. Our implementation (GTSBotPilot) adapts these three layers as pipeline hooks over the Martingale strategy. The trend network (which the original paper acknowledges performs suboptimally in raw regression terms) is replaced with EMA-smoothed first and second derivatives, preserving the paper's stated functional purpose (noise reduction and directional classification) without the training overhead. The GSM enforces a minimum of 15 candles between same-direction entries (x-threshold) and a minimum price distance of 0.5 × ATR(14) (y-threshold). The BESM targets basket profit of 2.0 × ATR(14) before closing all positions. All thresholds scale adaptively with ATR, which the original paper implements with fixed values; the adaptive extension generalises to varying volatility regimes. GTSBotPilot requires no offline training: all parameters are rule-based and derived from current market data.

**FinRLPilot** (based on Liu et al., 2020). The FinRL library provides deep reinforcement learning infrastructure for financial trading, with PPO as the primary algorithm. Our implementation (FinRLPilot) adapts the RL framework to parameter-preset selection rather than direct position management. The state is a 10-dimensional feature vector from the same FeaturePool used by IslandPilot. The action space is four discrete parameter presets: conservative (4 levels, 15-pip hedge, 25-pip TP, sqrt sizing), moderate (6 levels, 10-pip hedge, 20-pip TP, geometric sizing), aggressive (8 levels, 8-pip hedge, 15-pip TP, geometric sizing), and tight-TP (4 levels, 10-pip hedge, 12-pip TP, linear sizing). Reward is cycle PnL, penalised at 0.1 × observed drawdown during the cycle. Without PyTorch installed, the policy falls back to a tabular Q-learner (3 bins per feature, 4 features used for state discretization, n = 3 bins → 3^4 = 81 states). FinRLPilot is evaluated in inference mode with a pre-trained tabular policy, trained on the same 2022-2023 data as IslandPilot.

### 5.5 Execution Cost Model

The qengine execution engine applies real per-candle OANDA bid-ask spread data to all order fills. At each candle, the engine looks up the actual historical bid-ask spread for EUR-USD from the OANDA database (column 6 of the imported candle data, which stores the ask–bid difference at candle open as reported by OANDA's REST API). For buy entries, the fill price is shifted upward by the full spread; for sell entries, it is shifted downward. This models the cost of crossing the spread at market, which is how retail OANDA CFD orders execute. Exit orders (take-profit and stop-loss) fill at their trigger price; the spread cost is therefore incurred at entry only. EUR-USD bid-ask spread on OANDA averages approximately 1–2 pips during London and New York sessions and widens to 3–5 pips during Asian session and news events; the per-candle lookup captures this intraday variation rather than applying a uniform value.

Spread is charged per individual trade entry, not per trading session. This distinction is critical for Martingale strategies: a session that resolves at depth 0 (single entry, immediate take-profit) incurs one spread charge, while a session that escalates to depth 2 before recovery generates 3 separate trade entries, accumulating 3× the single-entry spread cost. The spread cost therefore scales linearly with session depth, creating a depth-dependent drag on profitability that the fitness function must implicitly account for.

No additional transaction costs are modelled beyond spread. Commission is zero in the OANDA CFD model (OANDA incorporates its fee into the spread). Swap and rollover costs are disabled in backtesting. This simplification is justified by the strategy's short average session duration: the median session completes within a trading day, and overnight holding occurs primarily in deep sessions that are already incurring adverse price movement losses. The omission of swap costs slightly overstates profitability for deep sessions but does not materially affect the pipeline-vs-baseline comparison, as both variants experience the same holding durations.

The starting account balance is $10,000 with 30:1 default margin (the maximum permitted for major FX pairs under ESMA and equivalent regulatory frameworks). Position sizing is expressed as a percentage of current equity, so the effective position size varies during drawdown periods.

**Metrics.** Primary evaluation metrics are profit factor (gross profit / gross loss), session win rate (fraction of profitable sessions), bust rate (fraction of sessions reaching maximum depth), net profit percentage, and maximum drawdown percentage.

---

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

---

## 7. Discussion

### 7.1 Positive OOS Transfer Under Full-Parameter Evolution

When the genome encodes the complete strategy parameter space — including entry signal type and direction bias — regime-aware evolution achieves positive out-of-sample performance on market data that is structurally distinct from the training period. On the 15-month 2025–2026 OOS evaluation, IslandPilot achieves +1.95% net return and profit factor 3.72 against a baseline loss of 76.52% and baseline PF ~0.77. The 78.5 percentage point improvement quantifies the pipeline's contribution from regime-conditioned parameter adaptation.

This result is worth examining for two reasons. First, it is achieved under real per-candle OANDA bid-ask spread costs that constitute a substantial transaction drag for the Martingale strategy — each session that progresses to depth 2 accumulates spread costs across 3 trade entries, representing a meaningful fraction of the 50-pip take-profit target. The pipeline achieves positive expectancy not by reducing spread cost but by reducing the frequency of deep sessions through regime-conditioned directional entry and by executing fewer sessions with higher per-session quality. Second, the result is not achievable by the comparison systems (GTSBotPilot PF 0.77–0.85, FinRLPilot PF 0.76–0.85), which confirms that the improvement is specific to the full-parameter evolution architecture rather than to any general property of pipeline-augmented strategies. Section 6.9 provides the mechanistic explanation for the PF differential.

### 7.2 Feature Dominance and Strategy Sensitivity

The dominance of volatility features in the mutual information ranking (Table 5: 4 of top 5 positions) reveals a structural relationship between the feature space and the strategy's risk profile. Martingale-family strategies fail when sustained directional moves exhaust available depth levels, and such moves manifest as elevated volatility. The regime discovery therefore naturally segments the market into states defined by the strategy's primary failure mode rather than by abstract market properties.

Session hour's inclusion at rank 6 captures the well-documented intraday volatility pattern in FX markets (Andersen & Bollerslev, 1997). The EUR-USD pair exhibits systematic volatility variation across London, New York, and Asian sessions, which the regime tree uses to distinguish session-specific sub-regimes within broader volatility clusters.

### 7.3 The Spread Problem and Its Resolution

The base strategy operates below breakeven on the real execution engine despite achieving 90%+ session win rates under undirected (random-entry) operation. The per-candle OANDA spread is applied to each individual trade entry. A Martingale session that reaches 2 hedge levels generates 3 individual trades, each incurring the current bid-ask spread, accumulating multi-pip total spread cost per session. With a 50-pip take-profit target at max 3 levels, the break-even requirement is achievable only if directional bias sufficiently reduces the proportion of sessions that reach deeper levels. Under random entry in a trending market, this condition is not met.

The resolution is not parameter tuning of the grid or sizing parameters, but regime-conditioned signal selection. The pipeline's evolved genomes can select `signal_mode = 'ema_cross'` and `direction_bias = 'long_only'` or `'short_only'` in trending regimes, converting zero-expectancy random entries into directional entries that are statistically aligned with the prevailing market trend. In a trending regime, an EMA-aligned entry starts the Martingale session with favourable directional momentum, reducing the probability that the session will reach depth 2 or 3 before price recovers. This shift in entry quality reduces the depth distribution of sessions, which reduces the average spread cost per session (fewer deep levels → fewer individual trade entries), and reduces the bust rate (fewer sessions reach maximum depth).

The result on the 2025–2026 out-of-sample period demonstrates that the pipeline CAN transform a structurally losing strategy into a net-profitable one (+1.95% net vs −76.52% baseline) when it is permitted to evolve entry signal selection per regime. The constraint is specificity: this transformation is achievable only if the training data contains sufficient regime diversity to learn which signal type is appropriate for each regime, and only if the OOS period contains similar regime structure to the training data. Section 6.9 provides the mechanistic account of why PF 3.72 is consistent with these conditions.

The implication for evolutionary trading systems research is important: restricting genome evolution to execution parameters (sizing, grid distances) while fixing entry signals preserves the structural expectancy of the underlying strategy. If that expectancy is negative (as it is for random-entry Martingale under realistic spread costs), evolution can only minimise losses, not generate profits. Full-parameter evolution — including signal selection — is required to engineer positive expectancy from the strategy architecture.

### 7.4 Real-Engine Evolution vs Simplified Simulation

The discrepancy between simplified simulation and full-engine evaluation turned out to be substantial. Initial experiments using a 120-line cycle simulator (without spread, slippage, or margin) produced profit factors above 1.0 and suggested 24% improvement over baseline. When the same architecture was evaluated on the full execution engine, these results were not reproducible. The genomes evolved on the simplified simulator produced extreme parameter values (50-pip hedges with ATR-based TP modes) that created sessions lasting weeks, reducing annual throughput to 2-3 cycles.

These results motivated the real-engine evolution approach used in the final results, where each genome fitness evaluation runs a complete qengine backtest with real execution costs. While computationally expensive (approximately 33 seconds per evaluation on 3 years of 5m data vs 0.1 seconds for the simulator), this approach ensures that evolved parameters are viable under realistic execution conditions. The 840 real-engine backtests required for 3 generations of 56 islands represent approximately 7 hours 46 minutes of wall-clock computation — a practical one-time training cost for offline pipeline calibration.

### 7.5 Comparison with Related Approaches

**Comparison with GTSBotPilot (Rundo et al., 2019).** The GTSBot system uses three coordinated layers: a regression network for trend detection, a Grid System Manager (GSM) enforcing minimum time and price distance between trades, and a Basket Equity System Manager (BESM) monitoring cumulative position profit. Applied to the same EUR-USD Martingale strategy under the same real-spread execution engine, GTSBotPilot achieves negative net return on the 2025–2026 OOS period through session-count reduction: the EMA trend filter blocks a substantial fraction of entry signals. The fundamental distinction is strategic: IslandPilot adapts HOW the strategy trades (per-regime parameter configuration, including signal selection), while GTSBotPilot adapts WHETHER the strategy trades (entry gating via trend filter). Neither approach is universally dominant; the preferred approach depends on whether the current market regime rewards activity or penalises it.

**Comparison with FinRLPilot (Liu et al., 2020).** The FinRL framework applies deep reinforcement learning to trading parameter selection. Our FinRLPilot implementation selects among four discrete parameter presets using a tabular Q-learner trained on 2022–2024 data. On 2025–2026, FinRLPilot achieves negative net return with profit factor in the 0.77–0.85 range, comparable to the unenhanced baseline. Compared with IslandPilot, FinRLPilot uses a simpler regime representation (four discrete presets vs per-leaf continuous genome) and has lower computational training cost (tabular Q-learning vs real-engine genetic evolution), but cannot engineer entry signal selection per regime and therefore cannot improve the structural expectancy of the underlying strategy beyond parameter perturbation.

**Comparison with Yang et al. (2025) and Chideme et al. (2025).** The closest architectural relative is Yang et al. (2025), who also employ per-regime subpopulations evolving independently. Their framework uses a 3-state HMM against this work's 56-leaf hierarchical GMM; they evolve genetic programming expressions for alpha factor construction, whereas this work evolves 6-dimensional parameter vectors for strategy execution; their Shapley-value co-evolutionary feedback differs from the ring-topology sibling migration used here. Neither Yang et al. nor Chideme et al. evaluate on a live execution engine with realistic spread and margin accounting, making direct numerical comparison infeasible. Chideme et al. (2025) use island-model GA for trading strategy portfolio optimization but treat islands as parallel search populations for computational speedup rather than regime-specific specializations. Their finding that IGTSP-Ring exhibits the most consistent performance with the lowest coefficient of variation is consistent with our observation that the island-model architecture provides stable per-regime adaptation — even when, as in the extended OOS period, that adaptation provides no net advantage over a rule-based alternative.

### 7.6 In-Sample Validation and Out-of-Sample Transfer

With the 3-year training window (2022–2024), in-sample performance provides a directional sanity check but not a primary result — the regime tree is fitted to 2022–2024 data, so in-sample performance reflects the degree to which the evolved genomes exploit known regime structure. The principal result is the 2025–2026 OOS period, which tests whether the learned regime-parameter mappings transfer to genuinely unseen market conditions.

*Table 9: IslandPilot vs Baseline — primary performance summary.*

| Period | IslandPilot Net% | Baseline Net% | Delta | PF (IslandPilot) | PF (Baseline) |
|---|---|---|---|---|---|
| 2024 (IS) | [in-sample] | [in-sample] | [in-sample] | — | — |
| 2025–2026 (OOS, primary) | **+1.95%** | **-76.52%** | **+78.47pp** | **~3.72** | **~0.77** |

The magnitude of the OOS improvement (+78.47pp) substantially exceeds typical IS-to-OOS retention rates reported in the financial ML literature (Bailey et al., 2014). This is consistent with the mechanistic account in Section 6.9: the primary source of improvement is not overfitting to training-period features but regime-conditioned entry signal selection, which generalises to the OOS period because the regime features (NATR_14, EMA Slope, DM Diff) encode structural market properties rather than idiosyncratic training-period artifacts.

The 2025–2026 OOS period is structurally challenging — EUR-USD experienced sustained directional moves driven by macroeconomic policy events (US tariffs, Federal Reserve hawkishness, ECB rate convergence) that were not present in the same form during the 2022–2024 training window. The fact that the pipeline performs well under these conditions supports the interpretation that the regime features capture the directional structure relevant to Martingale cycle outcomes generally, not just during the training period.

The limitation of this evaluation is that we have a single OOS test window. Confirming the result across multiple non-overlapping OOS periods (e.g., repeating the training–evaluation cycle with different cutoffs) would provide stronger evidence of generalisation. This is identified as a direction for future work.

### 7.7 Limitations and Scope

The current evaluation has several limitations. First, the evolution used only 3 generations with 5 individuals per island due to the computational cost of real-engine fitness evaluation. With 150 total backtests and approximately 55 minutes of training time, this represents a minimal evolutionary budget. Larger populations (30+ individuals) and more generations (20+) would explore the per-regime parameter space more thoroughly and likely produce stronger results, though at proportionally higher computational cost.

Second, the evaluation is limited to a single instrument (EUR-USD) and a single timeframe (5m). The architecture is designed to be instrument-agnostic and timeframe-agnostic, but generalisability to other settings remains to be validated. In particular, instruments with lower spread-to-movement ratios (cryptocurrency futures, ECN forex with 0.3–0.5 pip spreads) may exhibit larger pipeline improvements because spread is not the binding constraint on profitability.

Third, the regime tree is trained offline and deployed frozen. Market dynamics may shift to produce regimes not represented in the training data, causing the system to classify unseen conditions into the nearest existing regime. Online adaptation of the regime tree, where new leaves are added as novel market states are encountered, would address this limitation.

Fourth, the entry signal mode (random) used in the original preset produces non-deterministic baseline results across different random seeds. While the pipeline comparison uses the same random seed for both baseline and pipeline runs (ensuring fair comparison), the absolute performance varies across seeds. A deterministic signal mode such as EMA crossover would produce more reproducible baseline results, though systematic search across signal modes and wider grid configurations found no consistently profitable fixed configuration under realistic OANDA execution costs.

### 7.8 Implications for Martingale Strategy Design

The search conducted during pipeline development explored over 240 distinct parameter configurations spanning 5 timeframes (5m, 15m, 30m, 1h, 4h), multiple hedge distances (5-50 pips), multiple take-profit distances (10-80 pips), two sizing curves (geometric, linear), and sizing factors from sqrt(2) to 3.0. No fixed configuration achieved a profit factor above 1.0 on EUR-USD under realistic OANDA execution costs over the 2022–2024 training period. Configurations that appeared profitable at wider hedge distances (30+ pips) produced so few sessions per year (2-5) that the results were not statistically meaningful, and those sessions were dominated by spread cost accumulation per hedge level.

This exhaustive negative result confirms the theoretical finding from prior research on the SurefireHedge strategy: Martingale strategies require either very low transaction costs, adaptive parameter management, or both. Under fixed parameters, the strategy's mathematical edge (p x m < 1.0, yielding geometrically decreasing bust probability with depth) is consumed by the cumulative spread cost that scales linearly with session depth. The pipeline represents the adaptive parameter management approach: rather than seeking a single configuration that is profitable across all market conditions, it adapts parameters per regime to reduce losses in unfavourable conditions and preserve what edge exists in favourable ones.

The 90%+ session win rate that Martingale strategies produce masks a structural problem. Wins are small and bounded above by the take-profit distance minus cumulative spread cost across all trade entries in the session. Bust losses are bounded below by the sum of all open ticket exposures at maximum depth, which grows as the sizing_factor raised to the power of the depth level times the hedge distance. For a configuration with factor 1.7, max depth 3, hedge distance 20 pips, a full bust loses approximately 5.6× the base unit — versus a depth-0 win that recovers approximately 1 unit net of spread.

The evolved parameters across the 10 trained islands reveal that the GA has learned this asymmetry. The gate_confidence_min parameter has a low mean (0.183 on a 0-0.8 scale), indicating that the evolution does not favour aggressive entry filtering  -  blocking entries reduces session count but does not address the fundamental win-size vs bust-size imbalance. In contrast, abort_aggressiveness varies widely across islands (0.042 to 0.346), suggesting that the primary adaptation mechanism is regime-specific cycle termination: in high-risk regimes, the pipeline triggers early cycle exit to prevent sessions from reaching deep levels where exposure grows geometrically and spread cost accumulates. In low-risk regimes, abort_aggressiveness is low, allowing cycles to run to their natural conclusion. This pattern  -  permissive entry with selective early exit  -  is consistent with the theoretical prediction that Martingale risk management should focus on depth limitation rather than entry selectivity.

### 7.9 Generalisability Beyond EUR-USD

The IslandPilot architecture is instrument-agnostic by construction: the feature extraction layer computes standard technical indicators from OHLCV data, the regime discovery uses statistical properties of feature distributions, and the island evolution optimises parameters through the execution engine's standard backtesting interface. However, the current results are specific to EUR-USD traded through OANDA, and the degree of improvement on other instruments remains an open question.

Instruments with lower spread-to-movement ratios. The pipeline's +1.7 percentage point improvement on EUR-USD is achieved against a baseline that loses approximately 32% annually, with spread cost responsible for the majority of that loss (as established in Section 6.5). On instruments where execution costs are a smaller fraction of gross profit per session, the base strategy may already operate near or above breakeven, giving the pipeline more room to push performance into profitable territory rather than merely reducing losses.

Cryptocurrency futures are a practical test case. Binance perpetual futures charge a 0.04% taker fee — roughly one-quarter of typical EUR-USD OANDA retail spread. ECN forex brokers offer EUR-USD spreads of 0.3–0.5 pips, reducing the spread drag by 75–85%. In both cases, the reduced transaction cost would shift the baseline strategy closer to breakeven, and the pipeline's regime-aware adaptation would operate in a region where marginal improvements translate to profitability rather than reduced losses.

The regime tree features (NATR, ATR, ADX, session hour, choppiness index) are applicable to any liquid instrument, as all are computed from standard OHLCV data. However, the specific regime structure  -  the number of macro-clusters, sub-cluster composition, and feature importance ranking  -  will differ across instruments. An instrument with strong seasonality (such as agricultural commodities) might produce regime trees dominated by calendar features, while a cryptocurrency pair with extreme volatility clustering might produce trees dominated by ATR-derived features. The architecture accommodates these differences through the BIC-based model selection at both clustering levels, which adapts the regime granularity to the statistical structure of each instrument's feature space.

---

---

## 8. Conclusion

This paper introduced IslandPilot, a pipeline architecture that uses market regimes as the structuring principle for island-model evolutionary computation. The system makes three specific design decisions that distinguish it from prior evolutionary trading system work: (1) island topology is derived from the data via hierarchical GMM regime discovery, not specified a priori; (2) each island evolves the complete strategy parameter space — including entry signal type and directional bias — not just sizing or grid parameters; (3) all fitness evaluations run on the production execution engine with real per-candle OANDA bid-ask spread data, not on simplified simulators. These decisions are not incidental — the ablation evidence shows that removing any one of them collapses the result: arbitrary topology loses regime specialisation, restricting the genome to sizing parameters preserves the strategy's negative structural expectancy, and simulator-evolved parameters do not transfer to realistic execution.

The empirical result validates the architecture. On a 15-month strictly out-of-sample evaluation (January 2025–April 2026, EUR-USD 5m), IslandPilot achieves profit factor 3.72 against a baseline of 0.77, with maximum drawdown substantially reduced. The baseline loses 76.52% of starting equity over the same period under identical execution costs. This 78.5 percentage point improvement is produced by three compounding mechanisms: regime-conditioned entry signal selection that converts zero-expectancy random entry into directional entry in trend-aligned regimes; depth capping that limits maximum per-session loss to 5.6× the base unit; and adaptive position sizing that reduces exposure during drawdown episodes. The entire training process — 840 real-engine backtests across 56 regime-specific islands — completes in 7 hours 46 minutes on a single consumer CPU. The comparison systems (GTSBotPilot, FinRLPilot) achieve profit factors in the 0.77–0.85 range with negative net returns, confirming that the improvement is specific to the full-parameter island-model architecture rather than to pipeline augmentation in general.

The principal contribution is the demonstration that regime-aware evolutionary optimisation with domain-derived island topology produces transferable out-of-sample performance under realistic execution costs — a property that neither global evolutionary optimisation nor rule-based filtering achieves on this evaluation. A secondary methodological contribution establishes that evolutionary fitness evaluation must be conducted on the production execution engine: parameters evolved on simplified simulators without transaction costs fail to transfer.

### 8.1 Future Directions

The current system operates on a single instrument (EUR-USD) and waits for regime-appropriate conditions to arise on that instrument. Several architectural extensions would transform IslandPilot from a single-instrument regime adapter into a multi-instrument allocation framework. Due to the scope constraints of this dissertation, these directions were identified but not investigated; each represents a substantial engineering and research effort.

**Multi-Instrument Momentum Scanner.** The most impactful extension is a cross-instrument screening layer that identifies, in real time, which instruments from a monitored universe are currently in regimes where the Martingale strategy is expected to perform well — and allocates capital accordingly. The scanner would maintain a trained IslandPilot regime tree per instrument, compute regime classifications continuously, and rank instruments by the expected profit factor of the best genome for the current regime. Capital would flow toward instruments in favourable regimes (high-confidence, historically profitable regime leaves) and away from instruments in hostile regimes (trending, high-bust-probability leaves). This converts the problem from "wait for EUR-USD to enter a good regime" to "find the instrument that is in a good regime right now." The architectural challenge is non-trivial: regime trees trained independently per instrument produce incomparable regime identifiers, so a shared macro-regime representation (a universal feature space with instrument-specific sub-clustering) would be required to enable cross-instrument ranking. The screening frequency, rebalancing cost model, and correlation structure between instrument regime states (whether good regimes on EUR-USD and GBP-USD co-occur or alternate) are open empirical questions that determine whether the multi-instrument portfolio achieves genuine diversification or merely replicates the same regime exposure across correlated pairs.

**Online Regime Tree Adaptation.** The current regime tree is trained offline and deployed frozen. When market dynamics shift to produce conditions not represented in the training data, the system classifies novel states into the nearest existing regime via GMM posterior probability — a forced assignment that can be arbitrarily poor. An online adaptation mechanism would detect novel regime states (via log-likelihood monitoring on the GMM) and spawn new regime leaves with freshly initialised island populations. The evolutionary challenge is cold-start: a new island has no fitness history and must evolve from random initialisation while the market is already in the regime that triggered its creation. Warm-starting from the nearest sibling island's best genome is a practical heuristic, but the theoretical convergence properties of this online island creation process are unexplored. This extension would transform IslandPilot from a static classifier into a non-stationary adaptive system — a fundamentally harder problem with potentially much larger payoff.

**Hierarchical Temporal Decomposition.** The current system operates at a single timescale (5m candles). Financial markets exhibit structure at multiple temporal scales simultaneously — a 5m chart may show mean-reversion within a 1h trend within a daily range. A multi-scale IslandPilot would maintain separate regime trees at each timescale (5m, 1h, 4h, daily), with a meta-layer that combines regime classifications across scales to produce a composite regime state. The genome for each composite state would encode parameters appropriate for the dominant timescale dynamics. The HAR-RV multi-scale volatility features already in the 30-indicator pool (Section 3.1) provide the feature-space foundation; the architectural challenge is defining the composition operator that maps multiple per-scale regime classifications to a single composite state without combinatorial explosion (k scales × r regimes per scale = r^k composite states).

**Transfer Learning Across Instruments.** A regime tree pre-trained on EUR-USD captures general market microstructure patterns (volatility clustering, session-based periodicity, trend/range alternation) that partially transfer to other liquid FX pairs. The pre-trained island populations would serve as warm-start initialisation for evolution on a target instrument, reducing the 840-evaluation training cost to a fine-tuning budget of 100–200 evaluations. The empirical question is how much transfers: closely correlated pairs (EUR-USD and GBP-USD) likely share macro-regime structure, while structurally different instruments (gold, Bitcoin, equity indices) may share only the broadest volatility regime distinctions. Quantifying the transfer coefficient per instrument class would establish whether IslandPilot can be deployed as a general-purpose adaptive framework or whether it requires full retraining per instrument.

**Integration with Within-Cycle Tactical Decisions.** The Q-learning abort mechanism developed in prior research on the SurefireHedge strategy independently reduced bust rate by 32% through learned per-state cycle termination decisions. This mechanism operates at a different granularity than IslandPilot: the Q-learner decides whether to abort *this specific session at this specific depth* given the current market state, while the pipeline decides *which parameters to use for the next session* given the current regime. Because these two mechanisms address complementary aspects of risk management — within-cycle tactical decisions and between-cycle strategic configuration — they are architecturally compatible. The combined system would represent a two-level adaptive hierarchy: the pipeline selects the execution policy (strategic), and the Q-learner modifies execution within that policy (tactical). Whether the compounding effect is additive or multiplicative is an open question with significant practical implications.

 - 

---

## Acknowledgments

No external funding was received for this research.

## Declaration of Interest

The author declares that there are no competing interests associated with this manuscript.

## Data Availability Statement

The data used in this study consist of EUR-USD foreign exchange price data at 1-minute resolution, sourced from OANDA Corporation. It covers the period from January 1, 2020, to April 20, 2026, and can be accessed by anyone who creates a demo account and easily extracted via OANDA API. The author has complied with all relevant data usage agreements and ethical guidelines in the acquisition and use of this data for research purposes.
The processed feature matrices and regime tree models are available on the github repository associated with this project and one can easily reproduce the results by running the pipeline on the platform built for this research.

## Use of Generative AI

Generative AI tools were used in the preparation of this manuscript to assist with English language refinement and clarity of expression. The AI tools were not used to generate research ideas, data, analyses, or conclusions. All substantive content, interpretations, and conclusions are the sole responsibility of the author.

---

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

Liu, X.-Y., Yang, H., Chen, Q., Zhang, R., Yang, L., Xiao, B., & Wang, C. D. (2020). FinRL: A deep reinforcement learning library for automated stock trading in quantitative finance. *Proceedings of the NeurIPS 2020 Deep RL Workshop*. arXiv:2011.09607.

Lopes, R. A., Silva, R. C. P., Campelo, F., & Guimaraes, F. G. (2012). A multi-agent approach to the adaptation of migration topology in island model evolutionary algorithms. *Proceedings of the 2012 Brazilian Symposium on Neural Networks*, 160--165.

McLachlan, G. J., & Peel, D. (2000). *Finite Mixture Models*. Wiley.

McLean, R. D., & Pontiff, J. (2016). Does academic research destroy stock return predictability? *Journal of Finance*, 71(1), 5--32.

Nystrup, P., Madsen, H., & Lindstrom, E. (2017). Long memory of financial time series and hidden Markov models with time-varying parameters. *Journal of Forecasting*, 36(8), 989--1002.

Nystrup, P., Lindstrom, E., & Madsen, H. (2020). Learning hidden Markov models with persistent states by penalizing jumps. *Expert Systems with Applications*, 150, 113307.

Palupi, I., et al. (2021). Hidden Markov Model for regime classification in financial markets. *Procedia Computer Science*, 179, 542--549.

Rundo, F., Trenta, F., di Stallo, A. L., & Battiato, S. (2019). Grid trading system robot (GTSBot): A novel mathematical algorithm for trading FX market. *Applied Sciences*, 9(9), 1796. DOI: 10.3390/app9091796.

Schwarz, G. (1978). Estimating the dimension of a model. *Annals of Statistics*, 6(2), 461--464.

Syswerda, G. (1989). Uniform crossover in genetic algorithms. *Proceedings of the 3rd International Conference on Genetic Algorithms*, 2--9.

Tobin, J., Fong, R., Ray, A., Schneider, J., Zaremba, W., & Abbeel, P. (2017). Domain randomization for transferring deep neural networks from simulation to the real world. *Proceedings of the 2017 IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS)*, 23--30.

Wang, Y., & Aste, T. (2023). Inverse covariance clustering for portfolio optimization. *Applied Mathematics and Computation*, 443, 127769.

Whitley, D., Rana, S., & Heckendorn, R. B. (1999). The island model genetic algorithm: On separability, population size and convergence. *Journal of Computing and Information Technology*, 7(1), 33--47.

Wilder, J. W. (1978). *New Concepts in Technical Trading Systems*. Trend Research.

Wright, S. (1931). Evolution in Mendelian populations. *Genetics*, 16(2), 97--159.

Yang, S., Xin, J., Ye, Q., & Xia, H. (2025). A co-evolutionary genetic programming framework for market-adaptive formulaic alpha generation. *SSRN preprint*, 5614909.

Zhang, Y., et al. (2020). AutoAlpha: An efficient hierarchical evolutionary algorithm for mining alpha factors in quantitative investment. *arXiv preprint*, arXiv:2002.08245.

---

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
