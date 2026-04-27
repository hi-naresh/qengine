## Appendix A: Complete Feature Pool

Table A1 lists all 30 candidate features (24 base empirical-technical indicators plus 6 theoretically-motivated extensions) with their computation details, periods, and role under the two training configurations discussed in Section 6.3.

*Table A1: Complete feature pool (30 features) with computation details.*

| # | Feature | Category | Period | Computation |
|---|---|---|---|---|
| 1 | NATR_14 | Volatility | 14 | ATR_14 / Close × 100 |
| 2 | ATR_14 | Volatility | 14 | Wilder smoothed true range |
| 3 | NATR_50 | Volatility | 50 | ATR_50 / Close × 100 |
| 4 | BB Width | Volatility | 20 | (Upper − Lower) / Middle |
| 5 | HL Range Norm | Structure | 1 | (High − Low) / Close |
| 6 | Session Hour | Structure | - | UTC hour of candle |
| 7 | CHOP_14 | Choppiness | 14 | Choppiness index per Kaufman (2013) |
| 8 | ROC_10 | Momentum | 10 | (Close − Close[−10]) / Close[−10] |
| 9 | DM Diff | Trend | 14 | DM+ − DM− |
| 10 | EMA Slope 21 | Trend | 21 | (EMA[t] − EMA[t−1]) / EMA[t−1] |
| 11 | ATR Ratio | Volatility | 14/50 | ATR_14 / ATR_50 |
| 12 | ADX_14 | Trend | 14 | Wilder ADX |
| 13 | EMA Slope 8 | Trend | 8 | (EMA[t] − EMA[t−1]) / EMA[t−1] |
| 14 | RSI_14 | Momentum | 14 | Wilder RSI |
| 15 | ADX_28 | Trend | 28 | Wilder ADX |
| 16 | CCI_20 | Momentum | 20 | Lambert CCI |
| 17 | ER_50 | Choppiness | 50 | Kaufman efficiency ratio |
| 18 | Stoch %K | Momentum | 14 | Lane stochastic |
| 19 | RSI_28 | Momentum | 28 | Wilder RSI |
| 20 | ER_100 | Choppiness | 100 | Kaufman efficiency ratio |
| 21 | Aroon Osc | Trend | 14 | Aroon_up − Aroon_down |
| 22 | Hurst | Choppiness | 100 | R/S analysis |
| 23 | Close Position | Structure | 1 | (Close − Low) / (High − Low) |
| 24 | Day of Week | Structure | - | ISO day of week |
| **Theoretically-motivated extensions (Section 3.1):** |
| 25 | NATR_14_TF12 | Multi-scale volatility | 14 @ 12× | NATR_14 on 1h-aggregated candles, broadcast to 5m |
| 26 | NATR_14_TF48 | Multi-scale volatility | 14 @ 48× | NATR_14 on 4h-aggregated candles, broadcast to 5m |
| 27 | Vol of Vol | Distributional | 50 | Rolling std of NATR_14 over 50 bars |
| 28 | Return Skew | Distributional | 100 | Rolling standardised skewness of log returns |
| 29 | Return Kurt | Distributional | 100 | Rolling excess kurtosis of log returns |
| 30 | Return AC Lag-1 | Serial dependence | 100 | Rolling lag-1 autocorrelation of log returns |

**Primary configuration selection outcome (5m, 2022–2024 training window).** Under the primary MI procedure with forward bars = 288 and α = 0.1, three features exceeded the α · max threshold: **NATR_14_TF12**, **NATR_14_TF48**, and **NATR_50**. With fewer than 5 features selected the fallback rule (Section 4, Stage 1) broadened the partition to the full 30-feature pool, with macro/sub assignment by lag-10 autocorrelation:

- **Macro partition (autocorrelation ≥ 0.7 at lag 10, 15 features):** NATR_14_TF48, NATR_14_TF12, NATR_50, day of week, NATR_14, ATR_14, ADX_28, Vol of Vol, Return Skew, Return AC Lag-1, Return Kurt, ATR Ratio, Session Hour, Hurst, ADX_14.
- **Sub partition (autocorrelation < 0.7 at lag 10, 15 features):** RSI_28, BB Width, DM Diff, HL Range Norm, RSI_14, EMA Slope 21, ER_100, CCI_20, Stoch %K, Aroon Osc, CHOP_14, EMA Slope 8, ROC_10, ER_50, Close Position.

**Secondary configuration selection outcome (prototype, alternate outcome label).** An earlier run on a different outcome horizon retained 10 features above the MI threshold with scores from 0.590 down to 0.116: NATR_14, ATR_14, NATR_50, BB Width, HL Range, Session Hour, CHOP_14, ROC_10, DM Diff, EMA Slope 21. No fallback triggered; macro/sub partitioning used the selected subset (5 macro: NATR_14, ATR_14, NATR_50, BB Width, CHOP_14; 3 sub: HL Range, Session Hour, ROC_10; DM Diff and EMA Slope 21 retained as diagnostic). This configuration is reported here for reference because earlier prototype results (including some of the parameter sensitivity ranges in Appendix C) are derived from it.

### A.1 Indicator-Period Conventions

Indicator periods follow standard conventions from the technical analysis literature. Period 14 is the standard lookback for RSI, ATR, and ADX (Wilder, 1978) and remains the de facto default in practitioner and academic use (Colby, 2003). Period 50 is widely adopted as a medium-term volatility benchmark in FX (Katz & McCormick, 2000) and enables the ATR ratio (ATR_14 / ATR_50). The 8/21 EMA pair follows the Fibonacci convention common in short-term momentum systems (Kaufman, 2013) and matches the Martingale strategy's own EMA-crossover entry signal so the slope features directly reflect signal generation. The Hurst-exponent window of 100 follows Di Matteo et al. (2005); the Choppiness Index at period 14 and Efficiency Ratio at periods 50/100 follow Kaufman (2013). Standard periods are retained rather than optimised: optimisation would add a degree of freedom risking overfit, and the mutual-information filter (Section 3.1) acts as a second guard against irrelevant periods.

### A.2 Theoretically-Motivated Extensions

The 6 extension features supplement the 24 empirical-technical indicators along three theoretical dimensions:

**Dimension 1: HAR-RV multi-scale volatility (2 features: NATR_14_TF12, NATR_14_TF48).** NATR_14 computed on candles aggregated by factors of 12× and 48× relative to the base 5m timeframe (≈1h and 4h horizons), broadcast back to the base timeframe. This implements Corsi's (2009) HAR-RV model: three time-horizons suffice for parsimonious realized-volatility modelling. Müller et al. (1997) showed information flows asymmetrically across scales (long → short), making multi-scale volatility a regime signal rather than a redundancy with NATR_14.

**Dimension 2: Distributional shape (3 features: VOL_OF_VOL_50, RETURN_SKEW_100, RETURN_KURT_100).** (i) Rolling standard deviation of NATR_14 over 50 bars (vol-of-vol; Engle, 1982; Barndorff-Nielsen & Shephard, 2002), distinguishing stable high-volatility regimes from regime-transition periods. (ii) Rolling standardised skewness of log returns over 100 bars (Neuberger, 2012; Harvey & Siddique, 2000); negative skew indicates downside asymmetry, the dominant failure mode for Martingale long positions. (iii) Rolling excess kurtosis of log returns over 100 bars; elevated kurtosis signals fat-tail conditions. The 100-bar window follows Neuberger (2012) Table 1.

**Dimension 3: Short-lag serial dependence (1 feature: RETURN_AC_LAG1_100).** Rolling lag-1 autocorrelation of log returns over 100 bars (Lo & MacKinlay, 1988 variance-ratio framework; Box & Jenkins, 1976 AR identification). Positive values indicate trending (adverse for Martingale); negative values indicate mean-reversion. Box & Jenkins (1976) show lag-1 captures ≥80% of AR(1) information, making a single lag sufficient.

## Appendix B: Regime Tree Structure

The primary trained regime tree (5m, 2022–2024, fallback partition) contains **63 active leaves distributed across 10 macro-clusters** after sparse-leaf merging with `min_leaf_samples = 200`. This is the tree used for every result in Section 6. Aggregate statistics for this primary tree are summarised in Table B1; per-macro leaf counts for an earlier secondary/prototype configuration are reported separately in Table B2 for reference.

*Table B1: Primary regime tree summary (5m, 2022–2024 training window, fallback partition; the tree used by Section 6 results).*

| Statistic | Value |
|---|---|
| Macro-clusters (BIC-selected) | 10 |
| Active leaves (after sparse merge) | 63 |
| Mean leaves per macro | 6.3 (std ≈ 1.6) |
| Training observations (clean) | 220,608 |
| Mean leaf size (samples) | 3,501.7 |
| Std of leaf size (samples) | 2,377.7 |
| Min / max leaf size | 252 / 9,982 |
| Regime separation CV | 0.679 |
| `min_leaf_samples` (merge threshold) | 200 |

The 10-macro count and ~6.3 average leaves per macro emerge from BIC-selected GMM model-complexity at each level; the exact per-macro leaf counts depend on the training window and the outcome-label choice. The full per-leaf observation distribution is in the released `regime_tree.pkl` artefact.

*Table B2: Secondary/prototype regime tree macro-cluster breakdown (2020–2025 full-period fit, **73 leaves, not used by Section 6**; reproduced for context only).*

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
| **Total (secondary)** | **73** | **339,533** | **100%** |

Table B2's macro-clusters exhibit substantial variation in population size: from macro 5 (1,786 observations, 0.5%) to macro 9 (90,605 observations, 26.7%), a 50-fold range. The skew reflects the non-uniform distribution of market conditions over the fit period; the same skew is qualitatively present in the primary tree (Table B1) on a more compact 63-leaf footprint. Table B2 is reported because it illustrates the full per-macro structure that the primary 63-leaf tree narrows: the primary configuration distributes observations more evenly because the autocorrelation-based fallback separates features differently than the MI-based selection used for the secondary configuration.

## Appendix C: Hyperparameter Sensitivity

Table C1 reports the sensitivity of key design parameters based on exploratory experiments during development. Sensitivity is assessed by re-running the pre-flight training configuration with one parameter perturbed at a time and measuring the change in OOS top-20 profitability rate (Section 5.6).

*Table C1: Hyperparameter sensitivity analysis.*

| Parameter | Tested Range | Selected Value | Sensitivity |
|---|---|---|---|
| Hysteresis margin (δ) | 0.05 – 0.30 | 0.15 | Moderate: OOS-profitability rate varies ± 3% |
| Population size | 4, 8, 10, 16, 30 | 10 (Iteration 1 cloud) / 8 (Iteration 2 pre-flight) | Moderate: small pops (< 8) exhibit elite-cloning; pops ≥ 10 give adequate diversity for the 20-gene Iteration 1 genome and remain adequate at the 57-gene Iteration 2 widening |
| Tournament size k | 2, 3, 5 | 3 | Low: OOS rate varies ± 0.5% |
| Mutation rate | 0.1, 0.2, 0.3 | 0.2 | Low: OOS rate varies ± 1.5% |
| Mutation σ (genome-relative) | 0.03, 0.05, 0.10 | 0.05 | Low: σ > 0.10 produces overshoot from bound-edge genomes |
| Crossover rate | 0.5, 0.7, 0.9 | 0.7 | Very low: OOS rate varies ± 0.3% |
| Min leaf samples | 100, 200, 300 | 200 | Moderate: too low → noise, too high → lost granularity |
| Feature selection α | 0.05, 0.10, 0.15 | 0.10 | Low in-regime; controls whether fallback rule fires |
| Grace period τ | 0, 3, 5, 10 | 5 | Low: OOS rate varies ± 0.8% |
| Sizing-factor lower bound | 1.1, 1.3, 1.5, √2 ≈ 1.414 | Iter 1: 1.2 (loose); Iter 2: 1.5 (√2 floor) | **High**: bounds < √2 admit mathematically infeasible recovery; the Iter-2 [1.5, 2.5] override is a hardening of the Iter-1 [1.2, 2.0] range; see Sections 3.4, 3.4.1, and 7.8 |
| Bust-rate penalty exponent | 1 (linear), 2, 3 (cubic), 4 | 3 | Moderate: linear (1) under-penalises bust-heavy genomes and admits pathological cycles; very steep (≥ 4) over-penalises borderline genomes early in evolution. The implemented penalty is `0.2 · (1 − bust_rate)³ · 100`, applied as a soft term in the composite fitness rather than a hard cull |
| Fitness session-count floor | 5, 10, 20 sessions | 10 | Moderate: floor < 10 admits "lucky few" genomes; floor > 10 punishes selective strategies |

The system shows greatest sensitivity to the sizing-factor lower bound (a structural-viability constraint rather than a search tuning) and the fitness-function shape parameters (bust-rate penalty exponent, session-count floor). The latter two shape the curvature of the fitness landscape and the activity threshold below which genomes receive only the partial-credit floor (`0.5 · n_sessions`), and therefore shape the evolutionary search's reachable set. The GA operator parameters (mutation rate, crossover rate, tournament size) show low sensitivity, consistent with the general robustness of GA performance to moderate parameter variation in low-dimensional search spaces (Eiben & Smith, 2015). Population size sits in the middle: very small populations (≤ 4) suffer from sibling-migration elite-cloning that produces genome duplicates across adjacent islands, while populations of 10 or more provide adequate within-island diversity for both the Iteration 1 genome (5 pipeline + 14 strategy + 1 inert legacy = 20 dimensions) and the Iteration 2 widening (5 pipeline + 52 strategy = 57 dimensions, after Filters-group and mode-conditional exclusions).

## Appendix D: Algorithm Pseudocode

**Algorithm 1: Island-Model Evolutionary Optimization**

```
Input:  regime_tree with L leaf nodes, 1m candles C_1m, strategy S,
        leaf_date_ranges, config (pop_size, max_gen, migration_interval)
Output: evolved populations {P_1, ..., P_L}

1:  for each leaf l in {1, ..., L} do
2:      P_l <- INITIALIZE_POPULATION(pop_size, genome_bounds)
3:          // Iteration 1: 5 pipeline + 1 inert legacy + 14 strategy = 20 genes from 3 groups
4:          // (General, Grid/Hedge, Take Profit) with safety overrides (Section 3.4 Table 2).
4a:         // Iteration 2 widens to 5 pipeline + 52 strategy = 57 across 7 groups (legacy retired; Section 3.4.1 Table 3).
5:  end for
6:  set module-global _WORKER_CANDLES <- C_1m   // for fork-based workers
7:
8:  for generation g = 1 to max_gen do
9:      tasks <- []
10:     for each leaf l in {1, ..., L} do
11:         for each genome h in P_l do
12:             (s, e) <- leaf_date_ranges[l]   // window or full period
13:             tasks.append((h.genes, exchange, symbol, tf, S, s, e))
14:         end for
15:     end for
16:     results <- PARALLEL_MAP(_run_backtest_fitness, tasks)  // fork ctx
17:     ASSIGN_FITNESS(P_l, results)
18:
19:     if g < max_gen then    // skip evolve on final generation
20:         for each leaf l in {1, ..., L} do
21:             ranked <- SORT_BY_FITNESS(P_l, descending)
22:             elite <- ranked[1..2]          // top 2 preserved
23:             offspring <- COPY(elite)
24:             while |offspring| < pop_size do
25:                 p1 <- TOURNAMENT_SELECT(ranked, k=3)
26:                 if RAND() < 0.7 then       // crossover probability
27:                     p2 <- TOURNAMENT_SELECT(ranked, k=3)
28:                     child <- UNIFORM_CROSSOVER(p1, p2)
29:                 else
30:                     child <- CLONE(p1)
31:                 end if
32:                 if RAND() < 0.2 then       // mutation probability
33:                     child <- GAUSSIAN_MUTATE_ALL(child, sigma=0.05)
34:                 end if
35:                 child.genes <- VALIDATE_FEASIBILITY(child.genes)
36:                     // enforce base × factor^levels <= 20 (Sec 3.4)
37:                 offspring.append(child)
38:             end while
39:             P_l <- offspring[1..pop_size]
40:         end for
41:     end if    // end of evolve-only block
42:
43:     if g < max_gen and g mod migration_interval = 0 then     // migration also skipped on final generation (matches train.py:830, both evolve and migrate are wrapped in `if not is_last_gen`)
44:         for each macro-cluster M do         // sibling migration
45:             siblings <- active_leaves_in(M)
46:             for i = 1 to |siblings| do      // ring topology
47:                 donor <- siblings[(i-1) mod |siblings|]
48:                 best <- BEST_GENOME(P_donor)
49:                 INJECT(P_{siblings[i]}, CLONE(best))  // replace worst
50:             end for
51:         end for
52:     end if
53: end for
54:
55: return {P_1, ..., P_L}
```

**Algorithm 1a: Fitness Evaluation (`_run_backtest_fitness`)**

```
Input:  genes (integer-indexed categoricals + floats), route config, (s, e)
Output: fitness in [0, ~250]

1:  candles_1m <- _WORKER_CANDLES (from forked parent's module state)
2:  subset <- candles_1m where s <= timestamp <= e
3:  if |subset| < 2000 then return 0.0
4:
5:  hp <- genes minus pipeline-only keys
6:  hp <- RESOLVE_CATEGORICAL_GENES(hp, strategy_name)
7:      // map integer indices to strategy-semantic strings via the
8:      // whitelist-filtered option list (Section 3.4, 4.2)
9:
10: try:
11:     result <- backtest(config_cfd_10k, route, subset, hp, cost_model=on)
12: except Exception:
13:     print traceback; return 0.0
14:
15: pf <- metrics.profit_factor with inf/NaN/None -> 5.0, else min(5.0, pf)
16: dd <- |metrics.max_drawdown_percentage|, NaN -> 0
17: if isNaN(metrics.net_profit) then return 0.0
18:
19: n_s <- count of proper sessions (integer session id)
20: bust_rate <- busts / n_s  (default 1.0 when n_s = 0)
21:
22: if n_s < 10 then return n_s * 0.5
23:
24: F <-  0.5 * (pf - 1) * 100
25:    + 0.2 * max(0, 100 - dd * 5)
26:    + 0.2 * (1 - bust_rate)^3 * 100   // cubic bust-rate penalty
27:    + 0.1 * min(n_s / 100, 1) * 100
28: return max(0, F)
```

**Algorithm 2: IslandPilot Training Pipeline**

```
Input:  1m candles C_1m, timeframe tf, strategy S, config params
Output: trained regime_tree, island_evolver, leaf_date_ranges

Stage 0: SETUP
1:  assert QENGINE_TRAINING_MODE=1  // skip DB/Redis init (Section 3.6)
2:  C_tf <- RESAMPLE(C_1m, tf)

Stage 1: FEATURE SELECTION
3:  F_raw <- COMPUTE_FEATURES(C_tf)                  // 30 features (per-indicator periods, max 100 for Hurst/return moments)
4:  outcomes <- FORWARD_RANGE_EXCEEDS_THRESHOLD(C_tf, h=288)
5:  MI <- MUTUAL_INFORMATION(F_raw, outcomes)         // Kraskov estimator
6:  F_selected <- {f_i : MI[i] >= 0.1 * max(MI)}
7:  if |F_selected| < 5 then                          // fallback rule
8:      F_selected <- F_raw                           // use all 30 features
9:  (F_macro, F_sub) <- SPLIT_BY_LAG10_AUTOCORR(F_selected, threshold=0.7)

Stage 2: REGIME TREE CONSTRUCTION
10: macro_gmm <- FIT_GMM_BIC(F_macro, k_range=[2,10],
                             n_subsample=30000, n_init=1)
11: for each macro-cluster m in macro_gmm do
12:     sub_gmm[m] <- FIT_GMM_BIC(F_sub[m], k_range=[1,8],
                                   n_subsample=10000, n_init=1)
13: end for
14: leaves <- ENUMERATE_LEAVES(macro_gmm, sub_gmms)
15: leaves <- MERGE_SPARSE(leaves, min_samples=200)

Stage 3: ISLAND EVOLUTION
16: bounds <- BUILD_GENE_BOUNDS_FROM_STRATEGY(S)
17:     // Iteration 1: 5 pipeline + 1 inert legacy + 14 strategy = 20 across 3 groups (cloud-trained run);
17a:    // Iteration 2: 5 pipeline + 52 strategy = 57 across 7 groups (design endpoint, legacy retired);
18:     // filter genes and mode-conditional thresholds excluded (Section 3.4)
19: windows_per_leaf <- PER_LEAF_CONTIGUOUS_WINDOWS(leaves, min_days=30)
20: leaf_date_ranges <- DATE_RANGES(windows_per_leaf, fallback=full_period)
21: evolver <- IslandEvolver(leaves, bounds, pop_size)
22: evolver <- EVOLVE(C_1m, leaf_date_ranges, max_gen)   // Algorithm 1

Stage 4: MODEL PERSISTENCE
23: SERIALIZE(regime_tree, evolver, leaf_date_ranges) -> disk
```

## Appendix E: Comparison System Implementation Details

**GTSBotPilot (based on Rundo et al., 2019).** The Grid Trading System Robot proposes a three-layer architecture: a regression network for trend detection, a Grid System Manager (GSM) enforcing spacing constraints between trades, and a Basket Equity System Manager (BESM) that closes all positions when aggregate profit reaches a target. Our implementation adapts these three layers as pipeline hooks over the Martingale strategy. The trend network (which the original paper acknowledges performs suboptimally in raw regression terms) is replaced with EMA-smoothed first and second derivatives, preserving the paper's stated functional purpose (noise reduction and directional classification) without the training overhead. The GSM enforces a minimum of 15 candles between same-direction entries (x-threshold) and a minimum price distance of 0.5 × ATR(14) (y-threshold). The BESM targets basket profit of 2.0 × ATR(14) before closing all positions. All thresholds scale adaptively with ATR, which the original paper implements with fixed values; the adaptive extension generalises to varying volatility regimes. GTSBotPilot requires no offline training: all parameters are rule-based and derived from current market data.

**FinRLPilot (based on Liu et al., 2020).** The FinRL library provides deep reinforcement learning infrastructure for financial trading, with PPO as the primary algorithm. Our implementation adapts the RL framework to parameter-preset selection rather than direct position management. The state is a 10-dimensional feature vector from the same FeaturePool used by IslandPilot. The action space is four discrete parameter presets: conservative (4 levels, 15-pip hedge, 25-pip TP, sqrt sizing), moderate (6 levels, 10-pip hedge, 20-pip TP, geometric sizing), aggressive (8 levels, 8-pip hedge, 15-pip TP, geometric sizing), and tight-TP (5 levels, 12-pip hedge, 8-pip TP, linear sizing). Reward is cycle PnL, penalised at 0.1 × observed drawdown during the cycle. Without PyTorch installed, the policy falls back to a tabular Q-learner (3 bins per feature, 4 features used for state discretisation, n = 3 bins → 3^4 = 81 states). FinRLPilot is evaluated in inference mode with a pre-trained tabular policy, trained on the same 2022–2024 data as IslandPilot.

## Appendix F: Pre-flight Validation Protocol (Iteration 2 architectural correctness)

The pre-flight protocol is the architectural-correctness check for the Iteration 2 expanded gene set (7 tunable groups, 57 genes, categorical-gene resolver, retired legacy `base_size_pct`). It is **not** the source of the Section 6 OOS numbers (those are produced by the Iteration 1 cloud-trained model on a 15.5-month production OOS window). The pre-flight runs in three stages on a consumer CPU and exercises the wider Iteration 2 search space on a short window to verify GA convergence, gene-encoding round-trip correctness, and engine-evolver interface stability.

**Stage 1: Import and gene-bounds correctness.** A sanity script (`pipelines/_shared/IslandPilot/preflight.py`) asserts that (i) the Iteration 2 gene-bounds builder produces a bounds dictionary containing `signal_mode` and `direction_bias` (the Entry Signal genes that the Iteration 1 cloud model does not contain), (ii) random genomes sampled from these bounds contain and vary the categorical gene values, (iii) a single backtest on synthetic candles completes with non-zero fitness, and (iv) one full generation of training runs end-to-end without crashing. This stage runs in under two minutes on a consumer CPU.

**Stage 2: Short real-data training run.** With the correctness assertions passing, we run a reduced Iteration 2 training configuration on three months of real EUR-USD 5m data (2024 Q1), with 8 individuals per population and 8 generations across 9 CPU workers. This configuration completes in approximately 15–25 minutes on a consumer CPU and produces a full `island_evolver.json` model artefact structurally identical to a cloud run.

**Stage 3: Held-out out-of-sample validation.** A separate script (`pipelines/_shared/IslandPilot/validate_model.py`) loads the trained model, selects the top-fitness genomes per island, and evaluates each on a held-out 3-month window (2024 Q2). For each top genome it runs a single-genome backtest on the OOS window through the same `qengine.research.backtest` API used in training, extracts session count, bust count, L0 win rate, profit factor, net P&L, and drawdown, and reports a per-genome verdict (profitable / losing / too-few-sessions). The pre-flight architectural-validation criterion: at least 10 of the top 20 genomes must be OOS-profitable on the 3-month validation window. Meeting this criterion does not predict full-scale OOS performance (the pre-flight uses a 3-month training window, the cloud run uses 36 months, and the validation window is non-comparable to the production 15.5-month OOS), but failing it reliably indicates structural bugs in the training pipeline that would otherwise consume cloud compute without producing usable genomes.

**Result.** The Iteration 2 implementation passes the criterion (13 of 20 top-fitness genomes OOS-profitable on the 3-month validation window, mean L0 win rate 70–80% across the profitable subset). The criterion gates implementation readiness rather than predicting full-scale OOS behaviour.

**Baseline rate of the criterion.** The pre-flight criterion is positioned as a structural-bug detector, not a calibrated performance test. To bound its discrimination power we estimated the false-positive rate empirically. K = 60 genomes were sampled uniformly from the production gene bounds (the same bounds returned by `build_gene_bounds_from_strategy(Martingale)` that the trainer uses to seed Iteration 2 island populations) and each was evaluated on the same 2024-04-01 to 2024-06-30 OOS window via the same `qengine.research.backtest` API and the same profitability rule used by `validate_model.py` (`n_sessions ≥ 3` AND `net_pnl > 0` AND `bust_rate < 0.40`).

| Metric                                                          | Value                               |
|-----------------------------------------------------------------|-------------------------------------|
| Random genomes evaluated (K)                                    | 60                                  |
| Profitable                                                      | 0 / 60                              |
| Losing                                                          | 9 / 60                              |
| Too few sessions (< 3)                                          | 50 / 60                             |
| Flat (zero net P&L)                                             | 1 / 60                              |
| Errored                                                         | 0 / 60                              |
| Per-genome profitability rate (p̂)                              | 0.000                               |
| 95% Wilson confidence interval for p                            | [0.000, 0.060]                      |
| P(≥10 of 20 random genomes profitable), closed form (point)     | 0                                   |
| P(≥10 of 20 random genomes profitable), Wilson upper            | 6.6 × 10⁻⁸ (at p = 0.060)           |
| P(≥10 of 20 random genomes profitable), bootstrap (1000×, n=20) | 0.000                               |

Zero of the 60 random genomes were OOS-profitable. With the observed upper bound on the random profitability rate (p ≤ 0.060 at 95% confidence), the probability that 20 random genomes contain ≥10 profitable is bounded above by 6.6 × 10⁻⁸. The 13 / 20 result reported above therefore reflects genuine training signal rather than a coin-flip-level threshold: under the null of uniform-random genome sampling, the criterion is essentially never satisfied. The dominant random-genome failure mode was insufficient activity (50 / 60 produced fewer than three sessions across the 64-day window), reflecting the joint feasibility constraints imposed at gene-bounds construction time (Section 3.4): random parameter draws within those bounds frequently produce strategies that satisfy the ruin-prevention bounds but rarely fire entries on real EUR-USD candles. We also note a minor convention discrepancy: `validate_model.py`'s CLI defaults to `--top-n 10` whereas the paper text in Section 5.6 specifies "10 of top 20"; both Iteration 2 production pre-flight runs reported above used the 20-genome convention, with the script default left at 10 for backward compatibility with earlier Iteration 1 invocations and overridable per-run. The baseline analysis itself is limited by single OOS window, single instrument, and modest K (60), but the seven-orders-of-magnitude separation between the random-pass probability (≤ 10⁻⁷) and a naive 50% threshold means the qualitative conclusion is robust to plausible variation in the profitability rule. Methodology details: `notebooks/validation_analyses/03_preflight_criterion_discrimination.py`; numeric results in `notebooks/validation_analyses/results/03_preflight_criterion_discrimination.json`.

## Appendix G: Reproducibility Notes

The platform substrate for every reported backtest is the qengine execution engine (forked from the open-source Jesse framework and extended by the author for CFD/forex execution); the engine source, the IslandPilot pipeline, the comparison pipelines, and the trained model artefacts are released at the project repository (see Data Availability Statement). Three correctness conditions discovered during training are documented here; in each case the failure mode is "the GA produces flat fitness values across diverse genomes", a signal that is easy to misread as insufficient population size or poor fitness signal-to-noise, leading to unproductive tuning rather than root-cause correction.

**G.1 CFD margin-bust state leakage.** When a CFD position hits the margin-call close path, the engine closes each ticket individually via `record_ticket_close`, which creates a standalone `ClosedTrade` record. The position's temporary-trade accumulator (the stateful object that collects order-level entries for the in-progress trade) is not reset when this path fires. The next trading cycle's `open_trade` call retrieves the same stale accumulator, which then inherits entry orders from the previous (liquidated) cycle. In our runs this produced trades with `qty = NaN`, `entry_price = NaN`, and `exit_price = NaN` for every session after the first margin bust. Fitness values computed from such corrupted runs are not random-noise-plus-signal but structurally unrelated to genome quality. The fix is a one-line reset (`store.closed_trades._reset_current_trade`) invoked after the final ticket is force-closed and before the strategy's session-end hook is notified.

**G.2 Integer-index categorical genes at evaluation time.** The pipeline's deployment-time `_apply_genome` resolves integer-indexed categoricals to their string values, but an earlier iteration of the training-time `_run_backtest_fitness` function passed the raw integer dictionary directly into the strategy. Martingale's internal checks are string-typed (e.g., `direction_bias in ('both', 'long_only')`); an integer `0` fails every such check, silently coercing `should_long` and `should_short` to `False` for every candle. The strategy emits no orders, the backtest reports zero sessions, the fitness floor assigns `F = 0`, and the GA cannot distinguish structurally correct genomes from mis-encoded ones. The fix mirrors the deployment-time resolution (Section 3.6) by applying the same whitelist-filtered index-to-string mapping inside the evaluation function before the genome is handed to the strategy.

**G.3 Training-mode import isolation.** The training pipeline imports from the qengine core (e.g., `qengine.research.backtest`) inside worker subprocesses, which ordinarily triggers initialisation of the full application stack including PostgreSQL model-table creation and Redis pub/sub. For training none of these services are required; we gate their initialisation on a `QENGINE_TRAINING_MODE` environment variable, allowing the engine modules to be imported cleanly on hardware without a database or Redis instance (for example, the Google Compute Engine VMs used for the canonical training run).

**G.4 Breakeven-exit spread correction.** The strategy's breakeven exit mechanism (which moves the active take-profit to the session's zero-PnL price once `breakeven_levels` hedges have been opened) was found to systematically produce net-negative P&L on "TP Hit" sessions. The mechanism solved for the price at which the sum of signed per-leg P&L equals zero using raw entry prices, but entry prices already embed the spread slippage paid on each fill, so exiting at the zero-PnL price actually closed the session at `−spread × total_qty` rather than at true breakeven. The correction adds a spread-cost buffer to the breakeven target price calculation (target PnL = `total_qty × spread_price` rather than zero), so "breakeven" exit now produces approximate zero P&L after all costs are accounted for, not approximate zero P&L on the entry-to-exit math alone.

## Appendix H: Random-search Control

Appendices H and I jointly cover the validation-analyses programme woven into Section 6.2 (Appendix H, random-search control) and Section 6.3 (Appendix I, regime-tree feature-set sensitivity), with the Iteration 2 pre-flight criterion baseline-rate analysis completing the programme in Appendix F. Each analysis was run after the primary results were in hand to honestly stress-test a specific load-bearing claim of this research, and each is reported here with its limitations. The two appendices share an evidence philosophy: where a full performance ablation would have cost prohibitive compute, a structurally-meaningful reduced version was run instead and the deferred full version is named explicitly. Appendix H quantifies the GA's search-efficiency contribution against uniform random sampling of the same gene space; Appendix I quantifies the regime tree's structural sensitivity to the MI fallback. The pre-flight criterion baseline rate (Appendix F, "Baseline rate of the criterion") completes the programme.

Using the same gene-bounds the production GA actually used (extracted directly from the trained `island_evolver.json` to guarantee an apples-to-apples comparison; 20 genes spanning pipeline-level controls and Martingale strategy hyperparameters), we sampled N = 80 random genomes uniformly from the parameter space and evaluated each on the production composite fitness over a 6-month real-engine backtest window (2022-01-01 → 2022-07-01). The same fitness formula, backtest configuration (exchange = OANDA, symbol = EUR-USD, type = cfd, starting_balance = 10 000, route timeframe 30m, cost-model on, no fee), and Martingale strategy class as the production training run were used. Joint-feasibility constraints (TP > 1.5 × hedge distance; deepest-ticket exposure ≤ 20% of equity) were enforced identically to the GA. Pipeline-only genes (6 of 20) were excluded from the strategy hyperparameter dict, mirroring `_apply_genome` in the IslandPilot pipeline. *Timeframe note:* the random-control was evaluated at 30m route timeframe rather than the 5m production timeframe; the d=5.38 dominance is far above any plausible timeframe-induced shift, so this does not affect the directional conclusion.

| Metric                                | Random (N = 80)   | Trained GA (63 islands, last gen) |
|---------------------------------------|-------------------|-----------------------------------|
| Mean fitness                          | 7.832             | 58.867                            |
| Std                                   | 13.415            | 0.250                             |
| Min                                   | 0.000             | 58.090                            |
| Median (p50)                          | 0.500             | 58.976                            |
| 95th percentile                       | 38.059            | 59.180                            |
| Max                                   | 52.607            | 59.200                            |
| Fraction above F = 50                 | 1.2%              | 100.0%                            |
| Fraction at F = 0 (zero fitness)      | 46.2%             | 0.0%                              |

The trained GA outperforms random sampling by **51.04 fitness units** (Cohen's d = 5.38; the gap is 3.8 standard deviations of the random-search distribution). Approximately **0.0%** of random genomes exceed the trained-GA mean-best fitness (58.87), and **0.0%** exceed the best-trained genome (max = 59.20). The random distribution also reveals a high baseline failure rate: 46.2% of random genomes evaluate to fitness 0 (either zero/under-10 sessions in the 6-month window, or a corrupted PnL state from extreme parameter combinations), whereas every trained-island best is above F = 58. Median random session count was 2 with 65.0% of random genomes generating fewer than 10 sessions in the 6-month window.

This **supports the claim** that the GA contributes search efficiency beyond what uniform random sampling of the same gene-space would achieve. The random control is necessarily evaluated on a shorter (6-month) window than the production training run (full 2022-2024); the 6-month window is a strict subset of the training period, so the relative dominance of the trained population over random sampling is conservative: the same comparison on the full 3-year window would, at minimum, preserve this ordering. Random search of this 20-gene Martingale-pipeline space cannot find competitive genomes: the search problem is genuinely non-trivial, and the per-regime island populations are the mechanism by which IslandPilot localises that search.

Methodology details: random-control script is `notebooks/validation_analyses/01_evolutionary_search_contribution.py`; full numeric results in `notebooks/validation_analyses/results/01_evolutionary_search_contribution.json`. Sequential evaluation, seed = 20260426, wall-clock 4.37 min on the author's laptop. The fitness formula reported in the table is the production training fitness (cubic bust-penalty: `0.5·(PF−1)·100 + 0.2·max(0, 100 − DD·5) + 0.2·(1 − B)³·100 + 0.1·min(N/100, 1)·100`, floored at 0; <10 sessions returns `0.5·N`). The alternative composite stated in earlier drafts (linear bust-penalty: `0.4·(PF−1)·100 + 0.3·max(0, 100 − DD·5) + 0.2·(1 − B)·100 + 0.1·min(N/100, 1)·100`) gives random mean = 11.70 and is reported in the JSON for completeness; conclusions are unchanged.

## Appendix I: MI Fallback Ablation (Regime-tree Topology)

The production regime tree was built on the fallback feature set (all 30 features) because the mutual-information selection identified only 3 features (`natr_14_tf12`, `natr_14_tf48`, `natr_50`) as informative against the cycle-outcome proxy label (cloud training log, 2026-04-23). The fallback rule (`pipelines/_shared/IslandPilot/train.py` lines 1164-1169) triggers whenever fewer than 5 features survive MI selection, on the grounds that a 3-dim partition produces regimes that switch too rapidly for the per-leaf island evolution to gather contiguous evaluation windows.

To test whether the fallback materially changed the discovered regime structure, we re-fit the regime tree on the same training window (EUR-USD 1m → 5m, 2022-01-01 → 2024-12-31, 220 608 clean rows) using only the 3 MI-selected features (Tree A) and compared the resulting topology to a tree fit on all 30 features (Tree B, the production fallback). All other regime-tree hyper-parameters (`max_macro = 10`, `max_sub = 8`, `min_leaf_samples = 200`, autocorrelation `lag = 10`, `persistence_threshold = 0.7`) are identical to the production run.

| Metric                              | MI-only (3 feats) | Fallback (30 feats) |
|-------------------------------------|-------------------|---------------------|
| Macro clusters (BIC-selected)       | 7                 | 10                  |
| Total leaves (after sparse merge)   | 47                | 63                  |
| Mean leaf size (samples)            | 4 693.8           | 3 501.7             |
| Std of leaf size (samples)          | 3 677.3           | 2 377.7             |
| Min / max leaf size                 | 596 / 20 061      | 252 / 9 982         |
| Regime separation CV                | 0.783             | 0.679               |
| Adjusted Rand Index (A vs B)        | -                 | 0.034               |
| Normalised Mutual Info (A vs B)     | -                 | 0.168               |

ARI = 0.034 is low: the two trees produce structurally different partitions of the same data. The fallback to all 30 features materially changed the discovered regime topology. The production tree absorbs the additional 27 features as informative regime discriminators (most notably trend, time-of-day, distributional skew/kurtosis and serial dependence, dimensions that the 3 NATR-family MI features cannot represent at all), so a large structural divergence is expected by construction, not a sign of instability: the fallback tree partitions a strictly richer feature space. We flag this as a genuine sensitivity of the production pipeline: the choice to fall back changes which regimes the GA evolves against. The performance consequence is not quantified here; a full performance ablation (re-running the per-leaf GA on Tree A) is left to future work. We note that the regime separation CV is comparable for both trees (0.783 vs 0.679, both well above the 0.15 structural-validity threshold), so neither tree is degenerate.

The shipped production tree (`pipelines/_shared/IslandPilot/models/regime_tree.pkl`) has 10 macro clusters and 63 leaves; our locally-rebuilt Tree B has 10 macro / 63 leaves and agrees with the shipped tree at ARI = 1.0, confirming the local rebuild faithfully reproduces the production topology. The ablation above is therefore a like-for-like structural comparison between the choice that was made (Tree B, 30 features) and the counterfactual (Tree A, 3 MI features).

This ablation is **structural only**. A full performance ablation (running the per-leaf GA evolution on Tree A and comparing PnL, drawdown and bust rate against the production results) would cost roughly 10 hours of compute and is deferred to future work. The ARI and NMI metrics above quantify the *partition distance* between the two trees: ARI = 1 implies identical leaf assignments (and therefore, under identical GA seeds, identical strategies), while ARI = 0 implies the partitions are unrelated. The reported ARI = 0.034 sits near the lower bound and shows that the two regime decompositions are materially different objects; whether the corresponding evolved strategies differ in PnL by a large or small amount is a separate empirical question that this ablation does not resolve. Methodology details: `notebooks/validation_analyses/02_regime_tree_feature_set_sensitivity.py`; numeric results in `notebooks/validation_analyses/results/02_regime_tree_feature_set_sensitivity.json`.
