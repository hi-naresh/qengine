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
