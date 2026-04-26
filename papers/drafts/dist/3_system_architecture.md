## 3. System Architecture

IslandPilot operates as a five-layer pipeline that intercepts strategy execution at defined lifecycle hooks (`on_before`, `gate_entry`, `suggest_exit`, `on_cycle_end`) without modifying strategy source code. The five layers, described in subsections §3.1 to §3.5, are: (1) feature extraction from candle data; (2) hierarchical regime discovery; (3) hysteresis-based regime inference; (4) island-model genetic evolution; and (5) adaptive position sizing. Section §3.6 documents parameter application and supporting design constraints that span all five layers.

![Figure 1: IslandPilot architecture. Each layer operates per-candle during strategy execution. The feedback loop updates island fitness after each completed trading cycle.](../figures/Figure1.png)

### 3.1 Feature Extraction

The FeaturePool computes 30 market indicators from OHLCV candle data across five categories — volatility, trend, choppiness, momentum, market structure — comprising 24 empirical-technical indicators (standard conventions: Wilder, 1978; Bollinger, 2002; Chande, 1997; Lambert, 1983; Lane, 1984; Kaufman, 2013) and 6 theoretically-motivated extensions covering HAR-RV multi-scale volatility (Corsi, 2009; Müller et al., 1997), distributional shape (Engle, 1982; Neuberger, 2012), and short-lag serial dependence (Box & Jenkins, 1976; Lo & MacKinlay, 1988). Features are computed on a fixed 300-candle sliding window for O(1) per-candle cost. The complete feature pool with computation details, periods, and indicator-period justifications is given in **Appendix A**. The 5-minute base timeframe is justified in §5.1.

Feature selection uses mutual information (Kraskov et al., 2004) between each feature and a binary forward-outcome label derived from realised range exceeding a volatility threshold (precise label construction in §4 Stage 1). MI is preferred over linear methods such as LASSO or F-test because the relationship between technical-indicator features and Martingale cycle outcomes is plausibly non-linear; MI captures arbitrary statistical dependence without imposing a parametric form. Given MI scores {s_1, ..., s_30}, the selection rule retains feature *i* if:

$$s_i \geq \alpha \cdot \max_j s_j$$

where α = 0.1 is the minimum score-ratio threshold. A fallback rule activates when fewer than five features pass the threshold (the minimum required for a stable macro/sub partition): the pool reverts to all 30 indicators, partitioned by lag-10 autocorrelation (≥ 0.7 → macro/slow-changing; < 0.7 → sub/faster-changing). The empirical outcome on the canonical 2022–2024 training window is reported in §6.3.

![Figure 2: Feature processing and selection. The raw 30-feature pool (24 empirical-technical indicators plus 6 theoretically-motivated extensions) is reduced by a mutual-information filter with score-ratio threshold α = 0.1, then partitioned into a slow-changing macro feature set (input to the macro-level GMM) and a fast-changing sub feature set (input to the sub-level GMM).](../figures/Figure2.png)

### 3.2 Hierarchical Regime Discovery

The RegimeTree implements a two-level hierarchical clustering using Gaussian Mixture Models with BIC-based model selection at both levels, following the standard formulation of Schwarz (1978) as applied to mixture models by McLachlan and Peel (2000).

The choice of a two-level hierarchy over a single flat GMM is motivated by the observation that financial market states exhibit structure at multiple scales: broad regimes (e.g., high vs. low volatility) contain finer sub-states (e.g., trending vs. ranging within a high-volatility regime). A flat GMM with many components risks overfitting fine structure in dense regions while underfitting sparse regions. The hierarchical approach allows BIC to independently determine the appropriate granularity at each level. An empirical ablation comparing flat GMM against the two-level hierarchy is identified as future work.

**Macro-level clustering.** A GMM is fitted to the macro feature matrix X_macro in R^{n x 5} with the number of components k selected by minimising the Bayesian Information Criterion:

$$\text{BIC}(k) = -2 \ln \hat{L} + k \ln n$$

where L-hat is the maximised likelihood and n is the number of observations. BIC selects k ∈ [2, 10] using EM (Dempster, Laird & Rubin, 1977) with n_init = 1 and full covariance matrices; an early ablation indicated that restart variance was immaterial on these sample sizes. BIC is preferred over AIC because the large sample (n ≫ k) on three years of 5-minute data favours BIC's stronger penalty on overfit components (McLachlan & Peel, 2000); cross-validation was avoided because BIC's analytical form delivers comparable selection accuracy at a fraction of the computational cost, important given the per-evaluation cost of the downstream real-engine fitness function.

**Sub-level clustering.** For each macro-cluster m, the observations assigned to m are extracted and a second GMM is fitted to their sub-feature representation X_sub in R^{n_m x 3}. The sub-level BIC search iterates from k = 1 (allowing single-component macro-clusters to remain undivided) to max_sub = 8. For macro-clusters with fewer than 50 observations, a single sub-component is assigned without model selection.

**Leaf construction and merging.** Each (macro, sub) pair defines a leaf node. Sparse leaves (those with fewer than min_leaf_samples = 200 training observations) are merged into their most populous sibling (another leaf sharing the same macro-cluster). The merging iterates until no leaf falls below the threshold.

**Classification.** Given a new feature vector x, the regime probability distribution is computed as:

$$P(\text{leaf}_l | x) = P(\text{macro}_m | x_{\text{macro}}) \cdot P(\text{sub}_s | x_{\text{sub}}, \text{macro}_m)$$

where the macro probability is obtained from the macro-level GMM and the sub probability from the sub-level GMM conditioned on the macro assignment. Probabilities are renormalised across all leaves to sum to 1.

![Figure 3: Two-level hierarchical regime discovery. The macro-level GMM partitions the feature space into broad market states; sub-level GMMs within each macro-cluster capture finer structural distinctions. Sparse leaves (those with fewer than 200 training observations) are merged into their most populous sibling.](../figures/Figure3.png)

### 3.3 Hysteresis-Based Regime Inference

Raw GMM classification can produce rapid regime oscillations when the feature vector lies near the decision boundary between two regimes. In the context of trading system parameter control, such whipsaw is destructive: it causes frequent parameter reconfiguration that disrupts ongoing trading cycles and prevents any single parameter set from being evaluated over a meaningful horizon.

The RegimeInferencer introduces sticky classification with a hysteresis margin, analogous to hysteresis in control systems where a threshold difference is required before a state change is triggered (Astrom & Murray, 2008). Let r_t denote the active regime at time t, and let P_t(l) denote the probability of leaf l at time t. A regime switch from r_t to r* occurs only if:

$$P_t(r^*) > P_t(r_t) + \delta$$

where delta = 0.15 is the hysteresis margin. If this condition is not satisfied, the active regime remains r_t regardless of which leaf has the highest raw probability.

Following a regime switch, a grace period of tau = 5 candles is imposed during which the entry gate blocks all new trading signals. This prevents the strategy from entering a new cycle under a parameter configuration that may be immediately superseded.

The hysteresis margin δ = 0.15 corresponds to requiring approximately a one-and-a-half-fold posterior-probability advantage before switching regimes, suppressing whipsaw under typical GMM posterior distributions on the training window. The margin entails a trade-off: higher values reduce whipsaw but delay adaptation to genuine regime change. The value is a methodological hyperparameter selected to provide stable transitions on the training window.

### 3.4 Island-Model Genetic Algorithm

Each regime leaf maintains an isolated genetic population. The canonical training run uses 10 individuals per island, balancing search coverage against the per-evaluation real-engine cost (Section 4). Each individual (genome) encodes execution parameters that control trading behaviour when the corresponding regime is active.

**Genome representation.** A genome consists of 5 pipeline-level genes and a variable number of strategy-level genes discovered at runtime from the strategy's hyperparameter declaration. The pipeline-level genes and their bounds are shown in Table 1.

*Table 1: Pipeline-level genome parameters and their bounds.*

| Gene | Range | Type | Description |
|---|---|---|---|
| gate_confidence_min | [0.0, 0.5] | float | Minimum regime confidence to allow entry |
| abort_aggressiveness | [0.0, 0.4] | float | Danger threshold for cycle termination |
| hysteresis_margin | [0.05, 0.30] | float | Margin for regime switch decision |
| confidence_sensitivity | [0.5, 2.0] | float | Exponent for confidence-based size scaling |
| recovery_aggression | [0.3, 1.0] | float | Drawdown-based size reduction factor |

Strategy-level genes are discovered dynamically by reading the strategy's `hyperparameters()` declaration. Two iterations of the pipeline differ in genome scope. **Iteration 1** (cloud-trained, 20 evolved parameters: 5 pipeline-level + 1 inert-legacy `base_size_pct` + 14 strategy-level across three groups — General, Grid/Hedge, Take Profit) produces the §6 capital-preservation results. **Iteration 2** (57 evolved parameters across seven strategy-level groups, adding Entry Signal, Filters, Risk Management, Position Management) is the design endpoint identified by Iteration 1's evidence; its full-scale evaluation is the target of the conference-paper extension flagged in Section 8.1 and is not part of the reported §6 numbers. Tables 2 and 3 enumerate the Iteration 1 and Iteration 2 gene sets; numerical claims dependent on the Iteration 2 set are attributed explicitly wherever they appear.

*Table 2: Iteration 1 evolved strategy-level genes by group (cloud-trained Martingale model).*

| Group | Evolved genes | Parameters evolved per island |
|---|---|---|
| General | 5 | `sizing_curve`, `sizing_factor`, `base_size_mode`, `base_size_value`, `max_levels` |
| Grid / Hedge | 6 | `hedge_mode`, `hedge_value`, `hedge_atr_period`, `hedge_expand`, `hedge_expand_factor`, `reposition_atr_contraction` |
| Take Profit | 3 | `tp_mode`, `tp_value`, `tp_atr_period` |
| **Strategy-level total** | **14** | (per genome) |
| Pipeline-level (Table 1) | 5 | `gate_confidence_min`, `abort_aggressiveness`, `hysteresis_margin`, `confidence_sensitivity`, `recovery_aggression` |
| Legacy carrier (Iteration 1 only) | 1 | `base_size_pct` — present in the genome but filtered out by `_apply_genome` at deployment; consumes one GA dimension without affecting the strategy. Retired in Iteration 2. |
| **Genome total (Iteration 1)** | **20** | (5 pipeline + 1 inert legacy + 14 strategy) |

*Table 3: Iteration 2 expanded gene set (design endpoint; not exercised by §6 results).*

| Group | Evolved genes | Notes |
|---|---|---|
| General | 5 | unchanged from Iteration 1 |
| Grid / Hedge | 6 | unchanged from Iteration 1 |
| Take Profit | 3 | unchanged from Iteration 1 |
| Entry Signal | 24 | adds `signal_mode`, `direction_bias`, `entry_on_crossover`, EMA/RSI/MACD/Supertrend/Stochastic/CCI/ADX/dual-indicator periods. Mode-conditional thresholds (`rsi_ob`, `rsi_os`, `stoch_ob`, `stoch_os`, `cci_ob`, `cci_os`, `bb_period`, `bb_std`) and `model_lookback` excluded — they take effect only when their parent signal is active. |
| Filters | 0 | full 13-gene group excluded from evolution; see "Bound safety overrides" below |
| Risk Management | 6 | `max_daily_loss_pct`, `max_weekly_loss_pct`, `max_consec_busts`, `max_exposure_pct`, `cooldown_mode`, `cooldown_value` (subset of declared 12; rest excluded as mode-conditional) |
| Position Management | 3 | `breakeven_mode`, `breakeven_levels`, `equity_curve_filter` |
| **Strategy-level total** | **52** | (per genome) |
| Pipeline-level (Table 1) | 5 | unchanged |
| **Genome total (Iteration 2)** | **57** | legacy `base_size_pct` retired |

**Categorical gene encoding and resolution.** Categorical parameters (e.g., `tp_mode`: 4 options in Iteration 1; `signal_mode`: 9 options in Iteration 2) encode as integer indices into a broker-safe whitelist; the GA evolves over `{0, 1, …, k−1}`. At fitness evaluation time, each integer gene is resolved back to its string value before being passed to the strategy, mirroring the runtime `_apply_genome` hook used in deployment. This round-trip identity is required for correctness: the strategy's internal checks are string-typed, so an unresolved integer would fail every check silently and cause the strategy to emit no orders. Iteration 1 contains four categoricals (`base_size_mode`, `sizing_curve`, `hedge_mode`, `tp_mode`); Iteration 2 adds `signal_mode` and `direction_bias`. Section 4 documents the empirical impact of this correctness condition, which became material in Iteration 2.

**Bound safety overrides (Iteration 2).** `sizing_factor` is clamped to [1.5, 2.5]: the lower bound of 1.5 ≈ √2 enforces mathematical viability — sizing factors below √2 cannot geometrically recover prior losses and produce "TP-hit" sessions with net-negative P&L (Iteration 1's looser bound [1.2, 2.0] permitted such genomes empirically). `max_levels` is clamped to [2, 8] with the joint feasibility constraint `base_size × sizing_factor^max_levels ≤ 20%` of equity enforced at construction and after each mutation/crossover. Gating filters (13 genes total: session/volatility/trend/spread/confidence/day plus thresholds) are excluded from evolution: random initialisation across these categoricals assigns a blocking filter with near-certainty (~99.9% for typical option cardinality), starving the GA of non-zero fitness signal — verified empirically. Mode-conditional thresholds (`rsi_ob/os`, `stoch_ob/os`, `cci_ob/os`, `bb_period`, `bb_std`) are likewise excluded since they take effect only when their parent `signal_mode` is active. Iteration 1 used a narrower set of bounds (`sizing_factor ∈ [1.2, 2.0]`, `max_levels ∈ [2, 6]`) and did not require filter-group or mode-conditional exclusions.

The complete evolutionary algorithm is specified formally in Appendix D (Algorithm 1). The key operators are as follows.

**Selection.** Tournament selection with tournament size k = 3, a standard configuration that balances selection pressure with diversity maintenance (Goldberg & Deb, 1991).

**Crossover.** With probability 0.7, uniform crossover is applied (Syswerda, 1989): for each gene, the offspring inherits the allele from parent 1 or parent 2 with equal probability. With probability 0.3, the offspring is a direct clone of the first parent.

**Mutation.** With probability 0.2, Gaussian mutation is applied to the entire genome; all genes are perturbed simultaneously:

$$g'_i = \text{clip}(g_i + \mathcal{N}(0, 1) \cdot \sigma_i \cdot (h_i - l_i), \; l_i, \; h_i)$$

where g_i is the current allele, l_i and h_i are the gene bounds, and sigma_i = 0.05 is the mutation scale. Integer-typed genes are rounded after perturbation.

**Elitism.** The top 2 individuals are preserved unchanged into the next generation, ensuring monotonic fitness improvement within each island.

The above operator rates are widely used defaults in the genetic-algorithm literature (Eiben & Smith, 2015) and were not tuned in this work.

**Migration.** Sibling migration fires approximately five times over a training run, at intervals of `max(1, generations // 5)` generations (4 generations for the canonical 20-generation run): islands sharing the same macro-cluster exchange their best genomes via ring topology (Cantu-Paz, 2000). For a sibling group {I_1, I_2, ..., I_k}, the best genome of island I_{i-1} is injected into island I_i, replacing the worst individual. Sibling groups are filtered to include only active islands (those with sufficient training signals), so migration only occurs between islands that have been evaluated.

The migration topology is derived from the regime hierarchy itself: sibling groups are defined by shared macro-cluster membership. This differs from prior island-model work where topologies are specified independently of the problem domain (Lopes et al., 2012; Chideme et al., 2025).

![Figure 4: Per-cluster ring migration. Each leaf node maintains an isolated population. Within each macro-cluster, sibling islands form a ring topology and exchange their best genome on each migration event (firing approximately five times over the training run); no migration occurs across macro-clusters, preserving regime-specific specialisation.](../figures/Figure4.png)

The 10-individual population suits Iteration 1's 14-gene strategy genome; larger genomes (Iteration 2's 52 strategy-level genes; Section 5.2) likely warrant proportionally larger populations as future work.

### 3.5 Adaptive Position Sizing

The AdaptiveSizer computes the position size for each trade as a product of three factors:

$$\text{qty} = \text{base\_size} \times f_{\text{conf}}(\text{confidence}) \times f_{\text{dd}}(\text{drawdown})$$

where base_size is the evolved per-regime base position size (base_size_pct of current equity), and the two scaling factors are defined as:

**Confidence factor.** The confidence scaling function maps regime classification confidence to a size multiplier:

$$f_{\text{conf}}(c) = \max\left(0.2, \; c^{\gamma}\right)$$

where c is the regime probability from the inferencer (0 to 1), gamma is the evolved confidence_sensitivity parameter, and 0.2 is the minimum confidence scale floor. Values of gamma > 1 produce convex scaling (aggressively penalising low confidence), while gamma < 1 produces concave scaling (more tolerant of uncertainty).

**Drawdown factor.** The drawdown scaling function reduces position size during drawdown periods, with a threshold below which no reduction occurs:

$$f_{\text{dd}}(d) = \begin{cases} 1.0 & \text{if } d < d_{\text{thresh}} \\ \max\left(0.1, \; 1.0 - \frac{d - d_{\text{thresh}}}{100} \cdot r \cdot 10\right) & \text{otherwise} \end{cases}$$

where d is the current drawdown percentage, d_thresh = 5.0% is the drawdown threshold below which no scaling is applied, r is the evolved recovery_aggression parameter, the factor of 10 accelerates the scaling response, and 0.1 is the minimum drawdown scale floor. The threshold ensures that normal equity fluctuations do not trigger conservative sizing, while the 10x multiplier ensures rapid size reduction once the threshold is breached.

Both factors are bounded to prevent degenerate sizing (confidence floor 0.2, drawdown floor 0.1). The constants were chosen for behavioural plausibility rather than tuned: the 5% drawdown threshold suppresses response to normal equity fluctuations, while the factor-of-10 multiplier reaches the minimum floor at approximately 14% drawdown for `recovery_aggression = 1.0` and 23% drawdown for `recovery_aggression = 0.5`.

### 3.6 Parameter Application and Design Constraints

Evolved parameters are applied to the strategy only between trading cycles, never mid-cycle. This constraint is critical for strategies with internal state (such as martingale or grid strategies), where changing hedge ratios or level counts during an active cycle would corrupt the strategy's sizing chain. The pipeline observes the strategy's `position.is_open` flag and defers genome injection until the position closes; if no evaluable genome is available for the current regime, the entry gate blocks new cycles rather than permitting execution under default parameters.

The application mechanism reads the strategy's hyperparameter declaration to discover parameter names, types, valid ranges, and group memberships. It then sets each tunable parameter from the active genome, enforcing declared bounds and type constraints. Categorical parameters are resolved from integer indices to their string values using the same whitelist applied at genome construction (Section 3.4); this round-trip identity between training-time encoding and deployment-time resolution ensures that the strategy observes the same string value at evaluation and at deployment. After categorical resolution, mode-aware coercion scales numeric companion parameters into their valid per-mode range. For example, `tp_value` is evolved as a pip quantity but interpreted as a fraction of equity when `tp_mode = 'bucket_pct'`, so the pipeline rescales the evolved numeric into the mode-appropriate unit before the strategy reads it.

The regime tree is trained offline and deployed frozen during evaluation. If market dynamics shift to produce regimes not represented in the training data, the system classifies unseen states into the nearest existing regime based on GMM posterior probabilities. This is a standard limitation of fitted classifiers, partially mitigated by the hysteresis mechanism which prevents rapid oscillation during ambiguous classifications.

The hyperparameter choices throughout this section (hysteresis margin §3.3, GA operator rates §3.4, drawdown-function constants §3.5) were selected for behavioural plausibility rather than tuned; sensitivity analyses are identified as future work (§8.1).

 - 
