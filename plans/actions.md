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

## Priority 8: Live Trade Strategy Drift Detector (Future)
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

### Move to `checked/` (limited use):
- heavy_tailed.pdf — Finite-sequence expectation theory, academic interest only
- ForexAgent.pdf — LLM strategy classifier, future reference
- dynamic_grid.pdf, hedge_seq.pdf — Not relevant
- GTSBot.pdf, BiLSTM-Attention_Model.pdf, multi-pair.pdf, ruin_prob.pdf — Previously reviewed
