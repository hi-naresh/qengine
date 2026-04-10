# Paper-Derived Action Items for QEngine Pipeline

Generated: 2026-04-10
Updated: 2026-04-10

---

## Priority 1: Martingale Index as Pipeline Metric ✅ DONE
**Source**: martingale_index.pdf (Dimitrov & Shafer, 2025)
**Effort**: Medium | **Impact**: High

**What**: Compute M = Cov(G, 1/K) for each backtest run, where G = net gain per cycle, K = max capital at risk per cycle.

**Why**: Decomposes E(R) = M + E(G)·E(1/K). A high M means most of the apparent return is structural martingale illusion, not genuine edge. This answers "how much of our win rate is real?"

**Implementation**: Added to `_calculate_martingale_metrics()` in `qengine/services/metrics.py`.
- G = session PnL, K = legs per session (exposure proxy)
- Returns `martingale_index` and `martingale_contribution_pct`
- **Finding**: M = 0.905, 48.5% of return is structural illusion on 2020-2024 EUR-USD

---

## Priority 2: Markov Transition Matrix of Depth States ✅ DONE
**Source**: linear_reward.pdf (Chen, 2025) — Section 3.5, Fig 6
**Effort**: Medium | **Impact**: High

**What**: Build empirical depth-to-depth transition matrix T[i,j] = P(next cycle depth = j | current cycle depth = i) from backtest cycle data.

**Why**: Reveals whether deep cycles cluster (regime-dependent) or are IID. Our Phase 2 found busts are IID — this provides a richer view.

**Implementation**: Added to `_calculate_martingale_metrics()` in `qengine/services/metrics.py`.
- Returns `depth_transition_matrix` (NxN list) and `depth_stationary` (stationary distribution)
- **Finding**: Rows are near-uniform — confirms busts are IID/shock-driven, not gradually escalating

**TODO**: Visualize as heatmap in Pipeline Intelligence tab (frontend)

---

## Priority 3: NPD-PR Fan Visualization (Depth-Aligned Price Fan)
**Source**: linear_reward.pdf (Chen, 2025) — Section 3.6, Fig 4
**Effort**: Medium | **Impact**: Medium

**What**: For each backtest cycle, normalize entry prices by first entry price and plot against depth (not time). Creates a fan chart showing price deformation across all cycles.

**Why**: Visually identifies the "depth barrier" — the level beyond which price behavior changes qualitatively (fan collapses). In Chen's data this was depth 9; ours may differ per instrument. Directly shows where the strategy's structural assumptions break down.

**Implementation**:
- For each cycle: collect entry prices at each level
- Normalize: price_ratio[k] = entry_price[k] / entry_price[0]
- Plot all cycles overlaid, x-axis = level depth, y-axis = normalized price
- Highlight cycles that busted vs resolved
- Add dashed line at detected "collapse boundary"
- Include in Pipeline Intelligence tab as "Depth Fan" chart

**Files to modify**: Pipeline analysis, frontend chart component

---

## Priority 4: d'Alembert Null-Hypothesis Baseline
**Source**: martingale_index.pdf (Dimitrov & Shafer, 2025) — Section 3.3
**Effort**: Low | **Impact**: Medium

**What**: Run a pure d'Alembert strategy (no entry signal — just sizing ladder + stop-when-ahead) on same data as SurefireHedge. Compare returns.

**Why**: If SurefireHedge doesn't meaningfully exceed the d'Alembert return, our EMA crossover entry signal adds no value — it's all structural martingale profit. This is the strongest possible test of "does entry quality matter?"

**Implementation**:
- Create `strategies/DAlembertBaseline/` strategy
- Entry: random direction each bar (or alternate long/short)
- Sizing: same sqrt(2) ladder as SurefireHedge
- TP: same as SurefireHedge
- Backtest on same EUR-USD data
- Compare: PF, return, bust rate, Martingale Index M
- If SurefireHedge M < d'Alembert M with better return, entry signal has genuine value

---

## Priority 5: Quadratic Exposure Fit (R-squared Health Metric) ✅ DONE
**Source**: linear_reward.pdf (Chen, 2025) — Section 4.2
**Effort**: Low | **Impact**: Low-Medium

**What**: Fit E(n) = αn² + βn + γ to cumulative exposure at each level. Report R² as "exposure health" metric.

**Why**: If exposure deviates from quadratic (R² < 0.95), the multiplier configuration may be suboptimal. Chen found R² > 0.95 consistently. This is a quick sanity check on parameter quality.

**Implementation**: Added to `_calculate_martingale_metrics()` in `qengine/services/metrics.py`.
- Returns `exposure_fit_r2` and `exposure_coefficients` [α, β, γ]
- **Finding**: R² = 1.0 with sqrt(2) — exposure is actually linear (α ≈ 0), healthier than quadratic

---

## Priority 6: Depth Barrier Auto-Detection ✅ DONE
**Source**: linear_reward.pdf (Chen, 2025) — Section 4.3, 5.1
**Effort**: Medium | **Impact**: Medium

**What**: Automatically detect the depth beyond which win rate degrades sharply (the "no-man's-land" boundary). Suggest max-level cap.

**Why**: Chen found depth >= 9 was qualitatively different. Our system uses 12 levels. The actual safe boundary depends on instrument volatility and spacing.

**Implementation**: Added to `_calculate_martingale_metrics()` in `qengine/services/metrics.py`.
- Returns `depth_barrier` (level where win_rate < 70% with n >= 3) and `depth_barrier_details`
- **Finding**: Barrier at L1 — only L0 cycles are profitable (100% WR). All L1+ cycles lose on average.

**TODO**: Display as annotation on depth chart in frontend

---

## Priority 7: Triangular Loss Growth Validation ✅ DONE
**Source**: bi_ruin_problem.pdf (Taranto & Khan, 2020) — Theorem 2
**Effort**: Low | **Impact**: Low

**What**: Validate that our empirical loss accumulation follows triangular number series n(n+1)/2 rather than exponential 2^n.

**Why**: Taranto proves GTP losses grow as T(n) = n(n+1)/2. With sqrt(2) multiplier, our actual growth should be even slower. Confirming this empirically validates our multiplier choice and provides a publishable comparison point.

**Implementation**: Added to `_calculate_martingale_metrics()` in `qengine/services/metrics.py`.
- Fits cumulative loss vs triangular T(n), exponential 2^n, and quadratic
- Returns `loss_growth_validation` with R² for each fit and `best_fit`
- **Finding**: Quadratic best fit (R²=0.71) > triangular (0.59) ≈ exponential (0.59). Sub-exponential validated.

---

## Priority 8: Protective Sell Accuracy Metric ✅ DONE
**Source**: 1830483.1830694.pdf (Wilson & Banzhaf, GECCO 2010)
**Effort**: Low | **Impact**: Medium

**What**: Separate backtest trade accuracy into "profitable buys" (entries that led to profitable cycles) and "protective sells" (exits/close-all that prevented further drawdown).

**Why**: Win rate conflates entry quality with exit quality. A high protective sell % means our TP/close-all logic is good at timing exits. A high profitable buy % means our EMA crossover picks good entry points. Separating them reveals which component needs improvement.

**Implementation**:
- For each cycle: was the entry direction correct? (profitable buy = cycle resolved in profit)
- For each close-all/abort: did price continue against us after exit? (protective sell = price moved further adverse within N bars after exit)
- Report both metrics alongside win rate in backtest summary
- Wilson achieved 85-100% profitable buys and 90-97% protective sells with LGP

**Files to modify**: Backtest report generation, pipeline metrics

---

## Priority 9: Analytical Ruin Probability (Gamma Distribution Formula) ✅ DONE
**Source**: ruin_prob.pdf (Karathanasopoulos et al., 2021) — Proposition 1
**Effort**: Low | **Impact**: High

**What**: Compute closed-form survival probability from backtest cycle statistics using the Gamma distribution formula:
```
P_survive = ∫(1/w to ∞) f(x; α, β) dx

where α = 2μ/σ² - 1,  β = 2k₀/σ²
```
Special case when μ/σ² = 1: `P_survive = exp(-2k₀ / μw)`

**Calibration from backtest**:
- `μ` = mean return per cycle (after spread/costs) = cost-adjusted expected return
- `σ` = std dev of per-cycle returns
- `k₀` = fixed cost per cycle (spread cost in $ terms)
- `w` = current equity / initial equity (normalized wealth)

**Why**: Gives an **analytical** ruin probability to complement our empirical bust-rate. If the analytical P(ruin) diverges significantly from empirical, it flags model assumptions that don't hold (e.g., non-IID cycles, fat tails). Also provides the critical condition `μ/σ² > 1/2` as a quick parameter health check.

**Implementation**:
- Add `_calculate_ruin_probability()` to `qengine/services/metrics.py`
- Inputs: cycle PnL array, spread cost, equity
- Returns: `analytical_ruin_prob`, `survival_condition_ratio` (μ/σ²), `survival_condition_met` (bool)
- Add "Ruin Probability" card to Pipeline Intelligence tab
- Show: analytical P(survive), empirical P(survive) from bust rate, and whether they agree
- Color-code: green if μ/σ² > 1, yellow if 0.5 < μ/σ² < 1, red if μ/σ² ≤ 0.5

**Files to modify**: `qengine/services/metrics.py`, frontend Pipeline Intelligence tab

---

## Priority 10: Survival Condition Validator (μ/σ² > 1/2 Check) ✅ DONE
**Source**: ruin_prob.pdf — Lemma 1
**Effort**: Low | **Impact**: High

**What**: Before running a full backtest, compute `μ/σ²` from a quick sample or from config parameters and flag configurations that fail the survival condition.

**Why**: The paper proves that when `μ/σ² ≤ 1/2`, the fund **cannot** survive permanently — ruin probability is exactly 1.0 regardless of initial wealth. This is a hard mathematical boundary. Any parameter set that falls below it is guaranteed to bust eventually. This should be a pre-flight check in the pipeline.

**Implementation**:
- Add to pipeline config validation step
- Estimate μ and σ from first N cycles of backtest (warm-up phase)
- If μ/σ² ≤ 0.5: show red warning "Configuration mathematically guaranteed to ruin"
- If 0.5 < μ/σ² < 1.0: show yellow warning "Marginal survival — sensitive to parameter changes"
- If μ/σ² ≥ 1.0: show green "Survival condition comfortably met"
- Display in Pipeline Intelligence as a gauge or traffic light

**Files to modify**: Pipeline scan/validation, frontend

---

## Priority 11: Minimum Account Size Calculator ✅ DONE
**Source**: ruin_prob.pdf — Eq (9), Fig 1
**Effort**: Low | **Impact**: Medium

**What**: Given strategy parameters (μ, σ, k₀), compute minimum initial wealth `w_min` needed to achieve a target survival probability (e.g., 95%).

From the special case: `P_survive = exp(-2k₀/μw)` → solving for w:
```
w_min = -2k₀ / (μ · ln(P_target))
```
For the general case, invert the Gamma CDF numerically.

**Why**: Users ask "how much capital do I need?" This gives a mathematically grounded answer, not a guess. The paper's Fig 1 shows survival probability is near-zero below a wealth threshold, then jumps rapidly — finding that threshold is the answer.

**Implementation**:
- Add `calculate_min_account_size(target_survival, spread_cost, mu, sigma)` utility
- Display in backtest summary: "Minimum recommended account: $X for 95% survival"
- Incorporate into session comparison view

**Files to modify**: `qengine/services/metrics.py`, backtest report

---

## Priority 12: Fixed Cost Sensitivity Chart ✅ DONE
**Source**: ruin_prob.pdf — Fig 1 (right panel), Fig 10 (tornado diagram)
**Effort**: Low | **Impact**: Medium

**What**: Plot survival probability as a function of spread/fixed cost, showing how sensitive the strategy is to execution costs.

**Why**: The paper shows survival probability decreases exponentially with fixed cost (Eq 9). For FX, the "fixed cost" is spread + swap. This chart answers: "If my broker widens spreads by 0.5 pips, how much does my survival probability drop?" The tornado diagram (Fig 10) shows Δ (expected return) and σ₀ (additional volatility) are the most sensitive parameters.

**Implementation**:
- Sweep k₀ from 0 to 2x current spread, compute P_survive at each point
- Plot as curve in Pipeline Intelligence tab
- Mark current operating point
- Add vertical line at "break-even spread" where P_survive drops below 50%

**Files to modify**: Frontend Pipeline Intelligence tab

---

## Priority 13: Multi-Instrument Survival Improvement (Theoretical Bound)
**Source**: ruin_prob.pdf — Proposition 2, Section 3
**Effort**: Medium | **Impact**: Medium

**What**: Use Proposition 2's two-asset model to compute the theoretical survival improvement from adding a second instrument. The condition becomes `(a + μ̄)/2b > 1` which is **easier to satisfy** than the single-asset condition.

**Why**: Our Phase 2 identified multi-instrument diversification as the next step. This gives the theoretical framework: adding a second pair with different volatility characteristics provably improves survival probability. The paper shows that even a **short position** in a low-return asset can help (by hedging). This maps to our CFD hedging model.

**Implementation**:
- When comparing multi-pair backtest configs, compute both single-asset and two-asset survival conditions
- Show improvement: "Adding GBP-USD improves survival condition from 0.8 to 1.2"
- Use to rank which second instrument gives the best survival improvement
- Feed into the market scanner as a selection criterion

**Files to modify**: Multi-pair pipeline comparison, market scanner

---

## Priority 14: Dynamic Grid Repositioning (Micro-Martingale Concept)
**Source**: 2.pdf (Chen, 2025) — Section 2.4
**Effort**: High | **Impact**: Medium

**What**: During a drawdown, cancel unfilled orders at higher levels and reallocate to lower price zones. Total order count stays constant, but grid density increases at structurally lower prices.

**Why**: This is the one actionable concept from the crypto paper. Instead of waiting for price to hit pre-set hedge levels, dynamically shift unactivated levels downward when the market enters consolidation after a displacement. This accelerates cost-basis improvement without increasing total exposure.

**Constraints for our system**:
- Only reposition during displacement→consolidation transitions (not during active selloff)
- Total notional exposure must not increase
- Only applies to unactivated levels (can't move already-filled tickets)
- Requires ATR-based detection of "consolidation after displacement"

**Implementation**:
- Add `should_reposition_grid()` check in `update_position()` 
- Detect: price has fallen >N ATR but ATR itself is now contracting
- Shift unfilled hedge levels closer to current price (tighter spacing)
- Track original vs repositioned levels for reporting

**Files to modify**: SurefireHedgeV3 strategy, pipeline reporting

---

## Priority 15: Integral Take-Profit (Weighted Cost-Basis Exit)
**Source**: 2.pdf (Chen, 2025) — Section 2.3
**Effort**: Medium | **Impact**: Low-Medium

**What**: Instead of a fixed TP% from weighted average entry, continuously track a "cumulative gain integral" that accounts for micro-position density and local entry spacing. Trigger TP when the integral exceeds ~1% of adjusted cost basis.

**Why**: Our current TP is a fixed % from the weighted average entry price. The integral approach would trigger TP sooner during bounces from heavily-weighted lower entries, and later during bounces from lightly-weighted upper entries. In practice, this may improve holding time without sacrificing profit per cycle.

**Assessment**: The difference from our current weighted-average TP may be marginal. Our TP already weights by position size. The integral formulation is more general but may not materially change results for our 12-level grid. **Test empirically before committing.**

**Implementation**:
- Add alternative TP calculation mode to SurefireHedgeV3
- Compare holding time and profit distributions vs current TP
- If improvement > 5% in either metric, adopt; otherwise discard

**Files to modify**: SurefireHedgeV3 strategy

---

## Priority 16: Live Trade Strategy Drift Detector (Future)
**Source**: ForexAgent.pdf (Shu et al., 2026)
**Effort**: High | **Impact**: Low (until multi-user)

**What**: Feed live trade logs into an LLM classifier to verify trades match SurefireHedge pattern vs drifting into pure martingale or random behavior.

**Why**: In multi-user system, ensures users' live strategies match what was backtested. Low priority until we have multiple live accounts.

---

## Papers Disposition

### Keep in `checked/` (useful reference):
- linear_reward.pdf — Core theoretical validation (DMT framework, R(t), depth fan)
- martingale_index.pdf — Martingale Index metric definition
- bi_ruin_problem.pdf — GTP theorem, triangular loss proof
- drawdown.pdf — DDE/SDE for grid equity, σ sensitivity validation
- **ruin_prob.pdf** — Closed-form ruin probability, survival condition, minimum wealth formula

### Move to `checked/` (limited use):
- heavy_tailed.pdf — Finite-sequence expectation theory, academic interest only
- ForexAgent.pdf — LLM strategy classifier, future reference
- dynamic_grid.pdf, hedge_seq.pdf — Not relevant
- GTSBot.pdf, BiLSTM-Attention_Model.pdf, multi-pair.pdf — Previously reviewed
- **2.pdf** — Crypto micro-martingale. Grid repositioning concept extracted (P14). Rest is crypto-specific, not applicable to FX/CFD
- 1830483.1830694.pdf — LGP forex (Wilson & Banzhaf), drawdown-penalized fitness idea saved
- ZABCIC-MATIC-SENIORTHESIS-2019.pdf — Martingale-like options sizing, too simple for us
- quantum_fuzzy_agent.pdf — QPL + fuzzy RL sizing, not applicable
- Quantum-Inspired_AI.pdf — QIAI optimizer for LSTM prediction, not applicable
- PHD_THESIS_SALMAN.pdf — DC paradigm for entries, idea saved to ideas.md
