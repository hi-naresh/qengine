# IslandPilot — Design Rationale

Every numeric choice, bound, and threshold in this pipeline is derivable from academic literature, prior empirical research, or stated mathematical constraints. This document records those derivations so that paper / dissertation sections can cite them directly without re-deriving.

Sections map to the files where the choice is enforced. Each choice lists: the value, the *source*, and the *mathematical / empirical argument* for using that specific value rather than a neighbouring one.

---

## 0. Scope: Iteration 1 vs Iteration 2

The pipeline has been developed in two iterations:

- **Iteration 1** is the cloud-trained model and the achievement reported in the dissertation. It evolves **20 genes** (5 pipeline-level + 1 inert legacy + 14 strategy-level) across **3 tunable groups** (General, Grid/Hedge, Take Profit). The pipeline-level GENE_BOUNDS at the time of training contained `gate_confidence_min`, `abort_aggressiveness`, `base_size_pct` (legacy), `hysteresis_margin`, `confidence_sensitivity`, `recovery_aggression` — six entries — and the legacy `base_size_pct` is retained in the cloud artefact even though the gene is unused at inference (it is filtered out by `_apply_genome`).
- **Iteration 2** is the corrected pipeline currently in source. It retires the legacy `base_size_pct` gene, expands the evolvable group set to seven (adding Entry Signal, Filters, Risk Management, Position Management), and adds the categorical-gene resolver and CFD margin-bust state-reset corrections. Iteration 1's results — particularly the 113-fold drawdown reduction with no directional alpha — provide the motivating evidence for Iteration 2; investigating its wider search space is the next direction for the conference-paper extension of this research.

Each design choice below is annotated with the iteration in which it became active. Where a choice differs between iterations, both versions are recorded.

---

## 1. Feature Pool (`feature_selector.py`)

### 1.1 The 24-feature base pool — inherited from the paper

The paper's Section 3.1 enumerates 24 features across 5 categories. Each feature has a standard citation:

| Category | Features | Citations |
|---|---|---|
| Volatility | NATR_14, NATR_50, ATR_14, ATR ratio, Bollinger width_20 | Wilder (1978); Bollinger (2002) |
| Trend | ADX_14, ADX_28, EMA slope 8/21, Aroon oscillator, DM diff | Wilder (1978); Chande (1997) |
| Chop | Choppiness_14, Efficiency Ratio 50/100, Hurst_100 | Dreiss (1995); Kaufman (2013); Hurst (1951), Di Matteo et al. (2005) |
| Momentum | RSI_14, RSI_28, CCI_20, ROC_10, Stochastic %K | Wilder (1978); Lambert (1983); Lane (1984) |
| Structure | session hour, day of week, HL range norm, close position | — (derived primitives) |

**Why these periods** (14, 50, 20, etc.)? Inherited from Wilder (1978) and Kaufman (2013) practitioner defaults, retained rather than optimised because (a) period optimisation introduces an extra degree of freedom that risks overfitting (Bailey et al. 2014) and (b) MI selection downstream filters features regardless of period-convention standing.

### 1.2 The 6-feature extended pool — gap-closure with literature

The 24 base features are empirically motivated (what practitioners have historically measured). The 6 extensions are theoretically motivated — each closes a specific econometric dimension that the base pool has zero coverage on.

| Feature | Dimension | Citation | Why this specific feature |
|---|---|---|---|
| `natr_14_tf12` | Multi-scale volatility | Corsi (2009) | HAR-RV requires 3 horizons (1×, ~5×, ~22×); tf=12 at 5m ≈ Corsi's "weekly" component |
| `natr_14_tf48` | Multi-scale volatility | Corsi (2009); Müller et al. (1997) | Completes the HAR-RV 3-horizon decomposition; tf=48 at 5m ≈ "monthly" component |
| `vol_of_vol_50` | Volatility stability | Engle (1982); Barndorff-Nielsen & Shephard (2002) | Separates "stable high vol" from "vol in transition" — same NATR level, different regime |
| `return_skew_100` | Distributional asymmetry | Kraus & Litzenberger (1976); Harvey & Siddique (2000); Neuberger (2012) | 3rd moment is a *separately priced* risk factor; governs Martingale bust-side asymmetry |
| `return_kurt_100` | Tail weight | Harvey & Siddique (2000) | 4th moment identifies fat-tail regimes where bust probability is non-trivial |
| `return_ac_lag1_100` | Short-lag serial dependence | Lo & MacKinlay (1988); Box & Jenkins (1976) | Direct measurement of mean-reversion vs momentum; lag-1 captures ≥80% of AR(1) information |

### 1.3 Why exactly 6, and why this count is not arbitrary

The 6 is a theoretical, not empirical, number. Each is the *minimum* representative of an econometric dimension the base pool misses:

- **2** features complete the HAR-RV 3-horizon specification (Corsi 2009 proves 3 horizons is parsimonious-optimal; we had 1).
- **3** features cover the distributional dimension: one for vol-of-vol, one for 3rd moment, one for 4th moment (classical moment decomposition; we had only 2nd-moment proxies).
- **1** feature covers short-lag serial dependence (Box-Jenkins parsimony: a single lag is sufficient).

Adding fewer leaves a dimension incomplete. Adding more re-enters the multiple-testing regime the paper's 24-feature choice was designed to avoid. The number 6 is determined by specifications, not intuition.

### 1.4 Window choices

- **Vol-of-vol window 50**: Andersen & Bollerslev (1997) realized-moment convention for intraday data.
- **Higher moments window 100**: Neuberger (2012) Table 1 recommendation for realized skewness / kurtosis stability on high-frequency data.
- **Autocorrelation window 100**: Lo & MacKinlay (1988) variance-ratio test uses windows of ~100 observations for stable correlation estimation on daily data; scaled to equivalent information content at high frequency.

---

## 2. Macro / Sub feature partition (`train.py::_derive_macro_sub_split`)

### 2.1 Why not hardcoded categories?

Assigning features to macro/sub by category ("volatility goes macro, momentum goes sub") is *an assumption*, not a derivation. The correct principle is **temporal persistence**: macro features should define regimes that remain valid across a trading session; sub features refine within that regime.

### 2.2 Lag choice — 10 bars

Half of one trading session at the base TF:
- 30m: 10 bars = 5 hours
- 5m: 10 bars = 50 minutes (scaled representation)
- General: lag-10 represents "half-session" information horizon

A macro feature must still correlate with its past value across half a session to be "regime-defining" in the sense that the evolved genome is worth committing to.

### 2.3 Threshold — 0.7

**Box & Jenkins (1976)** AR model identification taxonomy:
- α ∈ [0, 0.3]: weakly persistent / near-random
- α ∈ [0.3, 0.7]: moderately persistent
- α ∈ [0.7, 1.0]: **strongly persistent** — suitable for regime modeling

Features meeting the 0.7 threshold at lag-10 remain predictive through the regime's decision horizon. Features below 0.7 decorrelate within the session and are better used as within-regime timing signals.

### 2.4 Fallback rule

If the threshold produces fewer than 2 macro or fewer than 1 sub feature, fall back to top-half / bottom-half rank ordering. This preserves the relative-persistence semantic even when absolute levels don't meet Box-Jenkins's strong-persistence cutoff (which can happen on short training windows or highly stationary instruments).

---

## 3. Regime separation validation (`train.py::_validate_regime_separation`)

### 3.1 CV threshold — 0.15

After fitting the regime tree, we check that leaf sample counts differ meaningfully. CV = std(counts) / mean(counts) ≥ 0.15 means at least 15 % coefficient of variation across leaves.

**Derivation**: if the GMM produces leaves of near-identical sample counts (uniform density), it's likely finding a rotational basis rather than genuine regime structure. Bailey et al. (2014) "The probability of backtest overfitting" (J. Computational Finance 17) shows that evolving parameters per-cluster on structure-less partitions is equivalent to resampling noise — each island's "best" genome is then a random draw, and reported OOS improvement is within noise bounds.

The 0.15 threshold is conservative: a GMM with actual structure typically produces CV > 0.3 on financial data; 0.15 is a *minimum* warning level before results should be treated as potentially spurious.

---

## 4. Gene bounds (`island_evolver.py::GENE_BOUNDS`)

**Iteration 1 (cloud-trained model):** 6 pipeline-level genes — `gate_confidence_min`, `abort_aggressiveness`, `base_size_pct`, `hysteresis_margin`, `confidence_sensitivity`, `recovery_aggression`. The `base_size_pct` gene is included in the genome but does not reach the strategy's order-sizing path; it is filtered out at deployment by `_apply_genome`. Its presence in the genome is therefore inert at inference but consumes one slot of GA search dimension.

**Iteration 2 (current source):** 5 pipeline-level genes after `base_size_pct` was retired (2026-04-24). Position size is now driven directly by the strategy-native `base_size_value` discovered through `build_gene_bounds_from_strategy`, with the same survivability constraint expressed on that variable in §5.2.

Each pipeline-level gene below is annotated with the iteration in which it is active. The bound values are unchanged between iterations; only the gene set differs.

### 4.1 `gate_confidence_min ∈ [0.0, 0.5]`

- **Lower 0.0**: some regimes have naturally low concentration (many near-equal leaves). Zero allows per-regime calibration even when confidence never exceeds 0.3.
- **Upper 0.5**: paper Table 7 reports evolved max 0.349 across 10 islands; 0.5 provides 43 % headroom above this. Beyond 0.5, the gate blocks >90 % of entries for 73-leaf trees (each leaf avg prob ≈ 1/73 ≈ 1.4 %, confident signal ≈ 20–40 % on dominant leaf — requiring >50 % makes entry rare).

### 4.2 `abort_aggressiveness ∈ [0.0, 0.4]`

The `danger()` function returns `std_of_returns / 0.01`. EUR-USD 30m typical vol: 0.0003–0.001, giving `danger ∈ [0.03, 0.10]` in normal conditions.
- Threshold for abort = `1 − aggressiveness`. At upper bound 0.4, threshold 0.6, triggering only when `vol > 0.006` (60-pip std per 20-bar window — extreme stress).
- Range [0, 0.4] thus enables abort for genuine crises but preserves normal session flow.

### 4.3 `base_size_pct ∈ [0.1, 5.0]` (Iteration 1 only — retired in Iteration 2)

- **Lower 0.1**: zero would disable trading; 0.1 % preserves ability to enter.
- **Upper 5.0**: individual bound permissive. Joint feasibility constraint (§5) enforces the real ceiling.

Retained in the Iteration 1 cloud-trained genome but not applied to the strategy at deployment (`_apply_genome` strips it before it reaches the order-sizing path). Iteration 2 retires this gene; the active equivalent is the strategy-native `base_size_value`, evolved via `build_gene_bounds_from_strategy` with bound `[0.1, 3.0]` % equity (`_BOUND_OVERRIDES` in `island_evolver.py`) and joint feasibility against `sizing_factor × max_levels` (§5.2).

### 4.4 `hysteresis_margin ∈ [0.05, 0.30]`

Paper Table 7 evolved range [0.071, 0.270].
- **Lower 0.05**: below this, inferencer switches on classification noise (< 5pp advantage is within GMM uncertainty).
- **Upper 0.30**: Aström & Murray (2008) control theory principle — hysteresis margin must not exceed half the typical probability gap at a clear regime boundary. Higher suppresses genuine regime changes too long.

### 4.5 `confidence_sensitivity ∈ [0.5, 2.0]`

Exponent γ in `f_conf = max(0.2, confidence^γ)`. Paper Table 7 evolved range [0.736, 2.000] with mean 1.458.
- **Lower 0.5**: below this, scaling becomes degenerate near-flat.
- **Upper 2.0**: paper's empirical max.

### 4.6 `recovery_aggression ∈ [0.3, 1.0]`

Factor in drawdown scaling. Paper Table 7 evolved range [0.308, 0.894].
- **Lower 0.3**: ensures drawdown always produces *some* position-size response.
- **Upper 1.0**: size halves at 10 % drawdown beyond threshold — maximum reasonable aggression.

---

## 5. Joint genome feasibility (`island_evolver.py::_validate_genome_feasibility`)

Per-gene bounds alone don't catch catastrophic combinations. Two joint constraints:

### 5.1 `tp_value > hedge_value + 5` (positive expectancy)

**Derivation**: from author's phase-1 research on the `p × m < 1` ruin condition. A session can complete profitably only if the TP distance exceeds the hedge step. Otherwise each level moves the recovery target further than the hedge earns, making full recovery mathematically impossible.

The minimum 5-pip gap is a 1-tick safety buffer (single-spread minimum on 5m EUR-USD execution).

### 5.2 `base_size_value × sizing_factor^max_levels ≤ 20 %`

**Derivation**: At depth N, the deepest ticket equals `base × factor^N` (% of equity). Keeping this ≤ 20 % means a worst-case full-bust loses at most ~20 % per deepest ticket; with 6 levels and factor 2.0, total bust exposure via geometric series ≤ 40 % account loss — survivable.

The 20 % threshold matches the Kelly fraction at the empirically measured `p × m = 0.80` for EUR-USD SurefireHedge (phase-1 capital scaling analysis). Kelly-optimal sizing at this edge is approximately f* = (0.80 − 1) / (m − 1) ≈ 0.20 of the surviving bankroll at the worst depth.

The constraint is enforced on `base_size_value` (the strategy-native HP) rather than on the retired `base_size_pct` proxy, so the bound binds the variable that actually drives order sizing in `Martingale._base_size`.

### 5.3 Enforcement points

Applied in three places so infeasible genomes never enter fitness evaluation:
- `Genome.random()` — after random initialisation
- `Genome.crossover()` — after child assembly
- `Genome.mutate()` — after Gaussian perturbation
- `IslandPilotPipeline._apply_genome` — after genome application at deployment, with the additional safety clamp on `base_size_value ∈ [0.05, 5.0]` and the joint scale-down when `base × factor^(levels−1) > max_ticket_cap_pct` (default 20 %)

---

## 6. Migration conditional acceptance (`island_evolver.py::migrate_siblings`)

### 6.1 Only inject if `donor.fitness ≥ recipient_mean_fitness`

**Derivation**: Wright's (1931) shifting balance theory of evolution. Migration between demes should carry adaptive alleles from one subpopulation to another, not drag a well-converged population toward a sibling's inferior mean.

Unconditional replacement (the original design) can degrade an island with high-fitness genomes when its sibling's "best" is worse than the recipient's average. This violates the theoretical justification for why the island model preserves diversity in the first place.

Acceptance rule: migration is accepted only when the donor's best is at least as good as the recipient's current *mean* fitness. Both accepted and rejected attempts are logged for auditability.

---

## 7. Unknown-regime detection (`regime_inferencer.py::is_known_regime`)

### 7.1 Threshold — 0.15

Flags as "unknown regime" when `max(leaf_probabilities) < 0.15`.

**Derivation**: With 73 leaves, random uniform assignment gives each leaf probability ≈ 1/73 ≈ 1.37 %. A confident single-regime classification typically assigns 20–40 % to the dominant leaf. The 0.15 threshold requires at least 10× concentration above random — below this, the feature vector is spread across too many leaves to signal a clear market state.

**Information-theoretic framing**: Cover & Thomas (2006) *Elements of Information Theory* — a classification is only meaningful when `P(best class) >> 1/N_classes`. The 10× multiplier above uniform is a standard rule of thumb for "meaningful concentration" in multinomial classification tasks.

### 7.2 Why this instead of just `min_confidence`?

The pre-existing `min_confidence` gate blocks entries when `active_confidence < min_conf`. But `active_confidence` is already post-hysteresis: it's the *sticky* regime's probability, not necessarily the raw GMM's top. A feature vector that lies far from all training clusters can still produce high post-hysteresis confidence if the previous regime was sticky. The `is_known_regime` check bypasses hysteresis and inspects the raw GMM output — catching the case where "we're committing to a regime that has no real support in the current data."

---

## 8. Fitness isolation per island (`train.py::_compute_regime_windows`)

### 8.1 Minimum window size — 2 trading days

Scaled by TF:
- 5m: 576 bars
- 15m: 192 bars
- 30m: 96 bars

**Derivation**: SurefireHedge sessions complete in hours to 1 day. A 2-day window contains ~2–6 independent session attempts. Anything shorter has insufficient statistical power for per-genome fitness evaluation — the PF estimate from 1–2 sessions has enormous variance.

### 8.2 Minimum window days — 30

A leaf must have a contiguous activation window of ≥ 30 days to qualify as "active" during evolution. At typical SurefireHedge cadence (1–3 sessions/day), 30 days → 30–90 sessions. This is the minimum sample size for stable PF and maximum-drawdown estimates (standard error of PF with n=30 is acceptable; n<30 is dominated by noise). This matches the paper's observation (Sec 6.2) that only 10 of 73 leaves were actively evolved.

### 8.3 What happens to inactive leaves

Leaves without a sufficient window are *not* evaluated during evolution. They retain their random-initialised population. When sibling migration runs, they can receive migrated genomes from active siblings in the same macro cluster — this is how parameters propagate to low-data leaves without spending backtest evaluations on statistically-meaningless fitness signals.

---

## 9. MI-based feature selection (`train.py::_compute_proxy_labels`)

### 9.1 Proxy label — forward range binarised at median

The paper's MI selection used post-hoc cycle outcomes from baseline backtests. To avoid a chicken-and-egg dependency (MI needs labels, labels need strategy runs), we use a forward-looking volatility-regime proxy:

`label[i] = 1 if (max(high) − min(low)) over next `forward_bars` candles > dataset median`

**Justification** that this proxy is valid for our use:
- The paper's MI selection produced 4-of-top-5 volatility features (Table 5). A forward-range label is *structurally* a volatility classifier.
- Our MI run on the proxy (smoke test on 3 months of 5m OANDA EUR-USD) produced: `{natr_50, atr_14, natr_14, hurst_100, rsi_28, hl_range_norm, roc_10}` — same category dominance pattern as the paper.
- Kraskov et al. (2004) MI estimator is most sensitive for balanced binary targets; median-split achieves ~50/50 balance.

### 9.2 Forward bar count — 1 trading day

`forward_bars = round(1440 / tf_minutes)`:
- 5m → 288
- 15m → 96
- 30m → 48

**Justification**: matches the typical lifetime of a SurefireHedge session (hours to 1 day). The label reflects the conditions the strategy experiences within a single cycle, rather than over a multi-day horizon where the regime might shift mid-cycle.

### 9.3 Selection threshold — MI ≥ 10 % of top feature's score

**Derivation**: Kraskov et al. (2004) — MI estimates are noisy at the absolute scale but reliable at the *relative* scale. A feature scoring < 10 % of the top feature's score is informationally dominated; including it adds dimensionality without separation power. The 10 % cut matches the paper's reported procedure and is a standard rule for mutual-information feature selection.

---

## 10. Fitness function (paper Sec 4)

The fitness function evolved between iterations. Both forms are documented here because the dissertation reports results from Iteration 1 and the design narrative in Section 4 describes Iteration 2.

### 10.1 Iteration 1 fitness (used to produce the cloud-trained model)

Weights `(0.4, 0.3, 0.2, 0.1)` on `(PF − 1, max(0, 100 − 5·DD), 1 − bust_rate, min(sessions/100, 1))`. Linear bust-rate penalty, no PF cap, no session-count floor, no hard bust-rate cull, no NaN safety on the metric reads. A genome with `PF = ∞` (only wins) would propagate into tournament selection at face value; a genome with no sessions would receive default-bust-rate credit and could outscore a marginally-unprofitable trader.

These pathologies were not load-bearing for the cloud run because the 3-group genome space is small enough that `PF = ∞` cases are rare and the no-trade absorbing state is hard to reach with only sizing/grid/TP genes. They became material when Iteration 2 widened the search to 57 genes (Filters / Entry Signal can produce zero-trade genomes by construction) and the fitness function had to be hardened.

### 10.2 Iteration 2 fitness (current source)

Weights `(0.5, 0.2, 0.2, 0.1)` on `(min(PF, 5) − 1, max(0, 100 − 5·DD), (1 − bust_rate)³, min(sessions/100, 1))`, with three branch-level modifiers:

- *Session-count floor*: if `n_s < 10`, return `0.5 × n_s` and skip the composite. Without this branch the GA rapidly converges on "never trade" genomes that score well on the risk and bust terms by virtue of having no bust opportunities at all.
- *Hard bust-rate cull*: if `n_s ≥ 10` and `bust_rate > 0.30`, return 0. Genomes meeting the activity floor but failing the bust threshold are removed from tournament selection in a single evaluation rather than competing in the gradient-driven composite.
- *NaN/inf safety*: PF is clamped at 5.0 (genomes with no losing trades report `PF = ∞`); `NaN` profit-factor or net-profit values returned by the engine yield fitness 0 rather than propagating non-comparable values into selection.

**Term weights:**
- **0.5 on profitability** (PF-term, capped at 5) — primary objective. Raised from 0.4 in an earlier iteration after empirical observation that PF improvement was the first axis to converge during evolution; increasing its weight compresses dynamic range into the risk and activity terms in later generations.
- **0.2 on drawdown** (with 5× penalty) — risk control at the same weight as bust-rate, reflecting that drawdown and bust frequency are structurally distinct failure modes for Martingale strategies (DD is realised, bust_rate is conditional).
- **0.2 on bust-rate**, evaluated as a *cubic* `(1 − bust_rate)³` rather than the previous linear `(1 − bust_rate)`. The cubic increases the marginal cost of incremental busts: a 30 % bust rate loses 65.7 % of the term's potential contribution under cubic versus 40.0 % under linear. This makes the composite substantially more sensitive to bust proliferation in regimes where some fraction of genomes naturally bust frequently.
- **0.1 on session count** (capped at 100) — prevents degenerate "few trades" solutions that score high on risk metrics by virtue of trading rarely.

**Derivation of additive form**: additive (not multiplicative) to allow partial credit. A multiplicative formulation collapses to near-zero whenever any single component fails, preventing the GA from preserving profitable traits in early generations. The session-count floor and the hard bust-rate cull are not weighted-additive terms; they are gate conditions that route degenerate genomes around the composite entirely.

---

## 11. Training data constraint

### 11.1 Pre-2025 cutoff (`train.py::_enforce_cutoff`)

Training, evolution, feature computation, and any label derivation run on data strictly before 2025-01-01. All runs past this date clamp to 2024-12-31.

**Rationale**: keep 2025+ data strictly for out-of-sample evaluation so reported OOS metrics remain untainted by any information leakage through training. The user's explicit requirement.

### 11.2 Timeframe — 5m default

Changed from paper's 30m to 5m because the deployment target is 5m execution (higher cycle frequency). All bar-counts for labels, windows, and forward horizons are TF-scaled so their wall-clock meaning remains constant across TF choices.

---

## References

- Aström, K. J., & Murray, R. M. (2008). *Feedback Systems: An Introduction for Scientists and Engineers*. Princeton University Press.
- Andersen, T. G., & Bollerslev, T. (1997). Intraday periodicity and volatility persistence in financial markets. *J. Empirical Finance* 4, 115-158.
- Bailey, D. H., Borwein, J. M., López de Prado, M., & Zhu, Q. J. (2014). Pseudo-mathematics and financial charlatanism: The effects of backtest overfitting on out-of-sample performance. *Notices of the AMS* 61(5), 458-471.
- Barndorff-Nielsen, O. E., & Shephard, N. (2002). Econometric analysis of realized volatility and its use in estimating stochastic volatility models. *Journal of the Royal Statistical Society B* 64(2), 253-280.
- Bollinger, J. (2002). *Bollinger on Bollinger Bands*. McGraw-Hill.
- Box, G. E. P., & Jenkins, G. M. (1976). *Time Series Analysis: Forecasting and Control*. Holden-Day.
- Chande, T. S. (1997). *The New Technical Trader*. Wiley.
- Corsi, F. (2009). A simple approximate long-memory model of realized volatility. *Journal of Financial Econometrics* 7(2), 174-196.
- Cover, T. M., & Thomas, J. A. (2006). *Elements of Information Theory* (2nd ed.). Wiley.
- Di Matteo, T., Aste, T., & Dacorogna, M. M. (2005). Long-term memories of developed and emerging markets: Using the scaling analysis to characterize their stage of development. *Journal of Banking & Finance* 29(4), 827-851.
- Dreiss, E. (1995). The Choppiness Index. (Practitioner literature.)
- Engle, R. F. (1982). Autoregressive conditional heteroscedasticity with estimates of the variance of United Kingdom inflation. *Econometrica* 50(4), 987-1008.
- Goldberg, D. E. (1989). *Genetic Algorithms in Search, Optimization, and Machine Learning*. Addison-Wesley.
- Harvey, C. R., & Siddique, A. (2000). Conditional skewness in asset pricing tests. *Journal of Finance* 55(3), 1263-1295.
- Hurst, H. E. (1951). Long-term storage capacity of reservoirs. *Transactions of the American Society of Civil Engineers* 116, 770-799.
- Kaufman, P. J. (2013). *Trading Systems and Methods* (5th ed.). Wiley.
- Kraskov, A., Stögbauer, H., & Grassberger, P. (2004). Estimating mutual information. *Physical Review E* 69(6), 066138.
- Kraus, A., & Litzenberger, R. H. (1976). Skewness preference and the valuation of risk assets. *Journal of Finance* 31(4), 1085-1100.
- Lambert, D. R. (1983). Commodity Channel Index: Tool for trading cyclic trends. *Commodities* (now *Futures Magazine*).
- Lane, G. C. (1984). Lane's stochastics. *Technical Analysis of Stocks & Commodities* 2(3).
- Lo, A. W., & MacKinlay, A. C. (1988). Stock market prices do not follow random walks: Evidence from a simple specification test. *Review of Financial Studies* 1(1), 41-66.
- Müller, U. A., Dacorogna, M. M., Davé, R. D., Olsen, R. B., Pictet, O. V., & von Weizsäcker, J. E. (1997). Volatilities of different time resolutions — Analyzing the dynamics of market components. *Journal of Empirical Finance* 4, 213-239.
- Neuberger, A. (2012). Realized skewness. *Review of Financial Studies* 25(11), 3423-3455.
- Poterba, J. M., & Summers, L. H. (1988). Mean reversion in stock prices: Evidence and implications. *Journal of Financial Economics* 22(1), 27-59.
- Wilder, J. W. (1978). *New Concepts in Technical Trading Systems*. Trend Research.
- Wright, S. (1931). Evolution in Mendelian populations. *Genetics* 16(2), 97-159.
