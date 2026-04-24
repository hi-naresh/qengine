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

Each regime leaf maintains an isolated genetic population, with the per-island population size selected to provide adequate search coverage over the full strategy parameter space while remaining feasible for real-engine evaluation (see Section 4 for the computational budget trade-off). The evaluations reported in this paper use populations of 10–12 individuals per island. Each individual (genome) encodes a set of execution parameters that control trading behaviour when the corresponding regime is active.

**Genome representation.** A genome consists of 6 pipeline-level genes and a variable number of strategy-level genes discovered at runtime from the strategy's hyperparameter declaration. The pipeline-level genes and their bounds are shown in Table 1.

*Table 1: Pipeline-level genome parameters and their bounds.*

| Gene | Range | Type | Description |
|---|---|---|---|
| gate_confidence_min | [0.0, 0.5] | float | Minimum regime confidence to allow entry |
| abort_aggressiveness | [0.0, 0.4] | float | Danger threshold for cycle termination |
| hysteresis_margin | [0.05, 0.30] | float | Margin for regime switch decision |
| confidence_sensitivity | [0.5, 2.0] | float | Exponent for confidence-based size scaling |
| recovery_aggression | [0.3, 1.0] | float | Drawdown-based size reduction factor |

Strategy-level genes are discovered dynamically by reading the strategy's `hyperparameters()` declaration. Seven tunable parameter groups are evolved: General (sizing curve, sizing factor, max levels, base size), Grid/Hedge (hedge mode, hedge distance, hedge expansion), Take Profit (TP mode, TP distance), Entry Signal (signal mode, direction bias, indicator periods), Filters, Risk Management (daily/weekly loss limits, consecutive-bust halt), and Position Management (breakeven mechanism). Table 2 summarises the per-group gene counts for the Martingale strategy evaluated in this paper, yielding 57 evolved genes in total.

*Table 2: Evolved strategy-level genes by group (Martingale strategy).*

| Group | Genes | Key evolved parameters |
|---|---|---|
| General | 5 | sizing_curve, sizing_factor, base_size_mode, base_size_value, max_levels |
| Grid / Hedge | 5 | hedge_mode, hedge_value, hedge_atr_period, hedge_expand, hedge_expand_factor |
| Take Profit | 3 | tp_mode, tp_value, tp_atr_period |
| Entry Signal | 29 | signal_mode, direction_bias, entry_on_crossover, and 26 indicator-specific parameters |
| Filters | — | excluded from evolution; see below |
| Risk Management | 6 | max_daily_loss_pct, max_weekly_loss_pct, max_consec_busts, max_exposure_pct, cooldown_mode, cooldown_value |
| Position Management | 3 | breakeven_mode, breakeven_levels, equity_curve_filter |

**Categorical gene encoding and resolution.** Categorical parameters (e.g., `signal_mode` with 9 valid options) are encoded as integer indices into a filtered option list: the strategy declares its full option set, a whitelist of broker-safe options is applied, and the GA evolves over `{0, 1, …, k−1}` where k is the whitelisted cardinality. At fitness evaluation time, each integer gene is resolved back to its string value before being passed to the strategy, mirroring the runtime `_apply_genome` hook used in deployment. This round-trip symmetry — encoding at evolution time, resolution at evaluation time — is required for correctness: the strategy's internal checks (e.g., `direction_bias in {'both', 'long_only'}`) are string-typed, so an unresolved integer would fail every such check silently and cause the strategy to emit no orders (Section 4 documents the empirical impact of this correctness condition).

**Bound safety overrides.** Several strategy parameters have bounds tightened below their declared ranges to prevent mathematically infeasible configurations:

- `sizing_factor` is clamped to [1.5, 2.5]. The lower bound of 1.5 (≈√2) enforces mathematical viability: for a Martingale hedge at depth N, the hedge leg's recovery profit must exceed the sum of prior adverse-direction leg losses plus spread bleed. Sizing factors below √2 cannot geometrically recover prior losses and produce "TP-hit" sessions with net-negative P&L, where the take-profit order fires but the session is still in deficit due to asymmetric cumulative exposure.
- `max_levels` is clamped to [2, 8]. The joint feasibility constraint `base_size × sizing_factor^max_levels ≤ 20%` of equity is enforced at genome construction and after each mutation/crossover operation, ensuring the deepest ticket cannot exceed 20% of account equity under any combination of evolved parameters.
- Gating filters (session filter, volatility filter, trend filter, spread filter, confidence gate, day filter) are **excluded from evolution** and allowed to take their strategy-default value of `'none'`. Their option lists contain many blocking settings and exactly one permissive setting; uniform random initialisation therefore assigns a blocking filter with probability (k−1)/k per filter, and with five independently-drawn filters the probability that no filter blocks entry is (1/k)^5 ≈ 0.1% for typical k = 4. Including these genes in the evolvable set collapses the activity-generating sub-space to a vanishingly small fraction of the genome, starving the GA of non-zero fitness signal. We verified this empirically: when filter genes were included, over 90% of random-init genomes produced zero trading sessions across the full training window, yielding fitness values dominated by their default-bust-rate penalty rather than any real performance differential. Excluding filters from evolution while leaving them addressable through the strategy's hyperparameter interface preserves the downstream user's ability to enable filters manually without entangling them with the GA search.
- `rsi_ob`, `rsi_os`, `stoch_ob`, `stoch_os`, `cci_ob`, `cci_os`, `bb_period`, `bb_std` are likewise excluded. These threshold parameters are conditional on their parent `signal_mode` being selected; evolving them unconditionally produces wasted search dimensions since they take effect only when their parent signal is active.

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

Evolved parameters are applied to the strategy only between trading cycles, never mid-cycle. This constraint is critical for strategies with internal state (such as martingale or grid strategies), where changing hedge ratios or level counts during an active cycle would corrupt the strategy's sizing chain. The pipeline observes the strategy's `position.is_open` flag and defers genome injection until the position closes; if no evaluable genome is available for the current regime, the entry gate blocks new cycles rather than permitting execution under default parameters.

The application mechanism reads the strategy's hyperparameter declaration to discover parameter names, types, valid ranges, and group memberships. It then sets each tunable parameter from the active genome, enforcing declared bounds and type constraints. Categorical parameters are resolved from integer indices to their string values using the same whitelist applied at genome construction (Section 3.4); this round-trip identity between training-time encoding and deployment-time resolution ensures that the strategy observes the same string value at evaluation and at deployment. After categorical resolution, mode-aware coercion scales numeric companion parameters into their valid per-mode range — for example, `tp_value` is evolved as a pip quantity but interpreted as a fraction of equity when `tp_mode = 'bucket_pct'`, so the pipeline rescales the evolved numeric into the mode-appropriate unit before the strategy reads it.

**Training-mode import isolation.** The training pipeline imports from the qengine core (e.g., `qengine.research.backtest`) inside worker subprocesses, which ordinarily triggers initialisation of the full application stack including PostgreSQL model-table creation and Redis pub/sub. For training, none of these services are required; we gate their initialisation on a `QENGINE_TRAINING_MODE` environment variable, allowing the engine modules to be imported cleanly on hardware without a database or Redis instance (for example, Google Compute Engine VMs). This isolation is the difference between the training script running at all and failing at module load with a `psycopg2.OperationalError`.

The regime tree is trained offline and deployed frozen during evaluation. If market dynamics shift to produce regimes not represented in the training data, the system classifies unseen states into the nearest existing regime based on GMM posterior probabilities. This is a standard limitation of fitted classifiers, partially mitigated by the hysteresis mechanism which prevents rapid oscillation during ambiguous classifications. The 10–12 individuals per island used in our evaluation are sufficient for the 57-dimensional genome produced by the Martingale strategy; strategies with substantially larger parameter spaces may require proportionally larger populations and are an explicit direction for future work.

 - 
