## Appendix A: Complete Feature Pool

Table A1 lists all 30 candidate features — 24 base empirical-technical indicators plus 6 theoretically-motivated extensions — with their computation details, periods, and role under the two training configurations discussed in Section 6.3.

*Table A1: Complete feature pool (30 features) with computation details.*

| # | Feature | Category | Period | Computation |
|---|---|---|---|---|
| 1 | NATR_14 | Volatility | 14 | ATR_14 / Close × 100 |
| 2 | ATR_14 | Volatility | 14 | Wilder smoothed true range |
| 3 | NATR_50 | Volatility | 50 | ATR_50 / Close × 100 |
| 4 | BB Width | Volatility | 20 | (Upper − Lower) / Middle |
| 5 | HL Range Norm | Structure | 1 | (High − Low) / Close |
| 6 | Session Hour | Structure | — | UTC hour of candle |
| 7 | CHOP_14 | Choppiness | 14 | Dreiss choppiness index |
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
| 21 | Aroon Osc | Trend | 25 | Aroon_up − Aroon_down |
| 22 | Hurst | Choppiness | 100 | R/S analysis |
| 23 | Close Position | Structure | 1 | (Close − Low) / (High − Low) |
| 24 | Day of Week | Structure | — | ISO day of week |
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

## Appendix B: Regime Tree Structure

The primary trained regime tree (5m, 2022–2024, fallback partition) contains 63 active leaves distributed across 10 macro-clusters after sparse-leaf merging with `min_leaf_samples = 200`. The 10 macro-cluster count and ~6.3 average leaves per macro emerge from BIC-selected GMM model-complexity at each level; the exact per-macro leaf counts depend on the training window and the outcome-label choice. An earlier prototype run (secondary configuration) produced 73 active leaves with macro counts as documented in Table B1 below; the primary configuration produces a somewhat more compact tree (63 leaves) due to the fallback partition using autocorrelation-based feature separation rather than MI-based selection.

*Table B1: Regime tree macro-cluster summary (secondary/prototype configuration, 2006–2025 full-period fit, 73 leaves).*

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

The macro-clusters exhibit substantial variation in population size — from macro 5 (1,786 observations, 0.5%) to macro 9 (90,605 observations, 26.7%), a 50× range. This skew reflects the non-uniform distribution of market conditions over the fit period: the most common macro state occurs 50× more frequently than the rarest. The number of leaves per macro ranges from 4 to 8, with BIC independently selecting the appropriate sub-cluster granularity. Despite macro 5's small population, its 4 leaves each exceed the 200-observation minimum required for meaningful evolutionary training.

For the primary 5m 2022–2024 configuration, the 63-leaf tree distributes observations across the same 10 macro-clusters with proportionally similar relative populations, producing 6.3 average leaves per macro (std ≈ 1.6) and a minimum leaf size comfortably above the merging threshold. We report the secondary-configuration numbers in Table B1 because they illustrate the full tree-structure space: the primary configuration's leaf distribution is narrower because autocorrelation-based fallback separates features more evenly across levels.

## Appendix C: Hyperparameter Sensitivity

Table C1 reports the sensitivity of key design parameters based on exploratory experiments during development. Sensitivity is assessed by re-running the pre-flight training configuration with one parameter perturbed at a time and measuring the change in OOS top-20 profitability rate (Section 5.6).

*Table C1: Hyperparameter sensitivity analysis.*

| Parameter | Tested Range | Selected Value | Sensitivity |
|---|---|---|---|
| Hysteresis margin (δ) | 0.05 – 0.30 | 0.15 | Moderate: OOS-profitability rate varies ± 3% |
| Population size | 4, 8, 12, 16, 30 | 12 (cloud) / 8 (pre-flight) | Moderate: small pops (< 8) exhibit elite-cloning; pops ≥ 12 give adequate diversity |
| Tournament size k | 2, 3, 5 | 3 | Low: OOS rate varies ± 0.5% |
| Mutation rate | 0.1, 0.2, 0.3 | 0.2 | Low: OOS rate varies ± 1.5% |
| Mutation σ (genome-relative) | 0.03, 0.05, 0.10 | 0.05 | Low: σ > 0.10 produces overshoot from bound-edge genomes |
| Crossover rate | 0.5, 0.7, 0.9 | 0.7 | Very low: OOS rate varies ± 0.3% |
| Min leaf samples | 100, 200, 300 | 200 | Moderate: too low → noise, too high → lost granularity |
| Feature selection α | 0.05, 0.10, 0.15 | 0.10 | Low in-regime; controls whether fallback rule fires |
| Grace period τ | 0, 3, 5, 10 | 5 | Low: OOS rate varies ± 0.8% |
| Sizing-factor lower bound | 1.1, 1.3, 1.5, √2 ≈ 1.414 | 1.5 | **High**: bounds < √2 admit mathematically infeasible recovery; see Sections 3.4 and 7.8 |
| Fitness bust-rate cull | 0.20, 0.30, 0.40, none | 0.30 | Moderate: cull at 0.20 over-restricts early GA; cull at 0.40 admits pathological genomes |
| Fitness session-count floor | 5, 10, 20 sessions | 10 | Moderate: floor < 10 admits "lucky few" genomes; floor > 10 punishes selective strategies |

The system shows greatest sensitivity to the sizing-factor lower bound (a structural-viability constraint rather than a search tuning) and the fitness-function shape parameters (bust-rate cull, session-count floor). The latter two determine which genomes receive any fitness signal at all and therefore shape the evolutionary search's reachable set. The GA operator parameters (mutation rate, crossover rate, tournament size) show low sensitivity, consistent with the general robustness of GA performance to moderate parameter variation in low-dimensional search spaces (Eiben & Smith, 2015). Population size sits in the middle: very small populations (≤ 4) suffer from sibling-migration elite-cloning that produces genome duplicates across adjacent islands, while populations ≥ 12 provide adequate within-island diversity for the 57-dimensional genome space.

## Appendix D: Algorithm Pseudocode

**Algorithm 1: Island-Model Evolutionary Optimization**

```
Input:  regime_tree with L leaf nodes, 1m candles C_1m, strategy S,
        leaf_date_ranges, config (pop_size, max_gen, migration_interval)
Output: evolved populations {P_1, ..., P_L}

1:  for each leaf l in {1, ..., L} do
2:      P_l <- INITIALIZE_POPULATION(pop_size, genome_bounds)
3:          // genome bounds: 5 pipeline genes + 57 strategy genes from
4:          // 7 tunable groups, with safety overrides (Section 3.4)
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
41:
42:         if g mod migration_interval = 0 then
43:             for each macro-cluster M do      // sibling migration
44:                 siblings <- active_leaves_in(M)
45:                 for i = 1 to |siblings| do   // ring topology
46:                     donor <- siblings[(i-1) mod |siblings|]
47:                     best <- BEST_GENOME(P_donor)
48:                     INJECT(P_{siblings[i]}, CLONE(best))  // replace worst
49:                 end for
50:             end for
51:         end if
52:     end if    // end of non-final-generation block
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
23: if bust_rate > 0.30 then return 0.0
24:
25: F <-  0.5 * (pf - 1) * 100
26:    + 0.2 * max(0, 100 - dd * 5)
27:    + 0.2 * (1 - bust_rate)^3 * 100
28:    + 0.1 * min(n_s / 100, 1) * 100
29: return max(0, F)
```

**Algorithm 2: IslandPilot Training Pipeline**

```
Input:  1m candles C_1m, timeframe tf, strategy S, config params
Output: trained regime_tree, island_evolver, leaf_date_ranges

Stage 0: SETUP
1:  assert QENGINE_TRAINING_MODE=1  // skip DB/Redis init (Section 3.6)
2:  C_tf <- RESAMPLE(C_1m, tf)

Stage 1: FEATURE SELECTION
3:  F_raw <- COMPUTE_FEATURES(C_tf, window=300)      // 30 features
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
17:     // 5 pipeline + 57 strategy genes across 7 tunable groups;
18:     // filter genes excluded from evolution (Section 3.4)
19: windows_per_leaf <- PER_LEAF_CONTIGUOUS_WINDOWS(leaves, min_days=30)
20: leaf_date_ranges <- DATE_RANGES(windows_per_leaf, fallback=full_period)
21: evolver <- IslandEvolver(leaves, bounds, pop_size)
22: evolver <- EVOLVE(C_1m, leaf_date_ranges, max_gen)   // Algorithm 1

Stage 4: MODEL PERSISTENCE
23: SERIALIZE(regime_tree, evolver, leaf_date_ranges) -> disk
```

 - 
