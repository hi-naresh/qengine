# Pipeline Implications

Direct changes to IslandPilot gene bounds, ARIA danger thresholds, and any other pipeline components justified by research findings.

Format:
```
## <Component> — <Change>
**Source:** script that justified this
**Before:** current value/bound
**After:** new value/bound
**Why:** the finding that drives this change
```

---

## IslandPilot — max_levels upper bound tightened
**Source:** `01_finite_capital/01_n_to_1_ratio.py`, `06_abort_theory/02_point_of_no_return.py`
**Before:** max_levels upper bound = 6 (in _BOUND_OVERRIDES or gene bounds)
**After:** max_levels hard cap = **5** for any config where sf ≥ 1.5
**Why:** At ml=6 with any realistic sf, the N-to-1 ratio becomes undefined (avg_win ≤ 0 after spread). The strategy becomes structurally unresolvable. ml=5 is the last level where some sf values (≤ 1.5) have finite N. See Finding 4.

---

## IslandPilot — sizing_factor × max_levels cross-constraint
**Source:** `01_finite_capital/01_n_to_1_ratio.py` (partial)
**Before:** sf and ml evolved independently with separate bounds
**After:** Add cross-constraint: `(sf, ml)` pairs must satisfy `sf^ml * base_size < max_position_limit`
**Why:** The N-to-1 ratio is a joint function of (sf, ml) not either alone. At sf=1.3/ml=5, N=4827 (barely viable). At sf=2.0/ml=5, N=43.6 (much more manageable). The interaction is non-linear. The safe region is a diagonal band, not a rectangle.

---

## ARIA Danger Scoring — add margin consumption rate feature
**Source:** `05_market_structure/02_margin_consumption_rate.py`
**Before:** ARIA uses price-based features (ATR, trend strength, level count)
**After:** Add `equity_per_leg_pct` = (peak_equity_pct / levels) as a real-time danger feature
**Why:** Bust sessions consume 9.05% equity per leg vs 1.08% for wins (8.4x ratio). This is calculable in real time during a session and provides an early warning signal before the bust is "confirmed." Threshold: equity_per_leg_pct > 3% → escalate danger score.

---

## ARIA Abort Policy — abort objective must change from bust-rate to total-loss
**Source:** `06_abort_theory/01_abort_vs_no_abort.py` (complete), `06_abort_theory/02_point_of_no_return.py`
**Before:** Abort level K = 4 (from prior Phase 2 research), objective = reduce bust_rate
**After:** Two valid abort policies:
  - **Policy A (loss minimization):** K=1 — reduces total loss by 46% ($−6,405 → $−3,475) at cost of 53.2% abort rate (most sessions cut at first hedge)
  - **Policy B (catastrophic bust elimination):** K=6 — eliminates level-6 busts, costs only $728 more vs K=1 in total PnL sacrifice, reduces bust_rate from 1.6% → 2.4%
  - K=7/8 are no-ops (max bust level is 6 for sf=2.0)
**Why:** Complete abort sweep shows PnL-optimal and bust-rate-optimal abort levels are maximally divergent (Finding 18). Bust rate as an objective leads to K=7 (no-op). Since strategy EV is universally negative, the correct objective is minimizing total loss. Policy B (K=6) is recommended for live trading: it eliminates catastrophic drawdowns while preserving more session-level continuity than K=1.

---

## IslandPilot — break-even win rate awareness in fitness function
**Source:** `02_bust_anatomy/results/all_sessions.csv`, `01_finite_capital/02_break_even_formula.py`
**Before:** Fitness = returns-based (profit factor, net return)
**After:** Add penalty when `actual_win_rate < break_even_win_rate(config)` for any evaluated individual
**Why:** The break-even win rate is config-dependent and must be met for the strategy to be viable. Evolved configurations with marginal safety (win_rate − p_min < 0.005) should be penalized even if they show positive returns on the in-sample period (the margin is too thin to be robust).

---

## Live Trading Diagnostics — session danger gauge calibration
**Source:** `05_market_structure/02_margin_consumption_rate.py`, `02_bust_anatomy/03_bust_path_patterns.py`
**Before:** Session danger gauge uses level count as primary signal
**After:** Use two signals simultaneously:
  1. Level count ≥ 4 → yellow (elevated)
  2. Equity-per-leg-pct > 3% → orange (high)
  3. Both level ≥ 5 AND equity-per-leg > 5% → red (abort territory)
**Why:** All busts are at exactly level 6 with 7 trades and std=0 — the level count signal is nearly deterministic. Adding equity-per-leg as a secondary signal provides earlier warning at levels 4-5 where the path to bust is still reversible.

---

## IslandPilot — N-to-1 aware safe region in (sf, ml) space
**Source:** `01_finite_capital/01_n_to_1_ratio.py`, `01_finite_capital/02_break_even_formula.py`
**Before:** sf and ml evolved with independent bounds
**After:** Add feasibility filter: reject any (sf, ml) individual where avg_win ≤ 0 (i.e., where N=nan). From the complete heatmap:
- sf ≤ 1.3: max_levels ≤ 4 (avg_win turns 0 at ml=5)
- sf ≤ 1.5: max_levels ≤ 5 (avg_win turns 0 at ml=6)
- sf = 2.0: max_levels ≤ 8 (avg_win positive throughout, min $0.60)
- sf ≥ 2.5: max_levels ≤ 5 (level capping anomaly — ml>5 gives no extra recovery)
**Why:** The complete N-to-1 heatmap shows that the "feasible" region is a non-rectangular diagonal band. The current rectangular bounds (sf ∈ [1.3, 3.0] × ml ∈ [3, 8]) include many configurations where avg_win ≤ 0 (structurally impossible to profit). Filtering these reduces search space and avoids degenerate solutions.

## Live Trading Position Sizing — minimum equity $5k for OANDA
**Source:** `08_broker_mechanics/01_lot_rounding.py`
**Before:** No stated minimum equity requirement beyond margin
**After:** Minimum recommended equity = **$5,000** for OANDA EUR-USD trading
**Why:** At $1k equity, OANDA integer unit rounding causes 10% position sizing error at level 0 (target 4.5 units → rounds to 5 units). This systematically over-sizes every position by 10%. At $5k, error falls to 1.2% — within acceptable range. Margin is not the binding constraint (Finding 3) but position accuracy is.

## IslandPilot — effective_max_levels constraint for optimizer correctness
**Source:** `strategies/_admin/Martingale/__init__.py` line 481, N-to-1 heatmap (Finding 19)
**Before:** Pipeline evolves (sf, ml) pairs with configured max_levels as the binding parameter
**After:** Add `_max_affordable_levels(sf, equity, leverage, base_pct)` check to IslandPilot individual evaluation. Reject or heavily penalize any individual where `effective_max < configured_max`. The lookup table from the research:
- sf=1.5: effective_max = configured_max (no cap at standard equity)
- sf=2.0: effective_max ≈ 7 (configured ml=8 behaves as ml=7)
- sf=2.5: effective_max ≈ 6 (configured ml≥7 behaves as ml=6)
- sf=3.0: effective_max ≈ 5 (configured ml≥6 behaves as ml=5)
**Why:** Without this constraint, the optimizer believes it's exploring higher max_levels territory when it's actually constrained to lower effective levels. Parameter estimates become unreliable and the evolved hp doesn't reflect actual behavior.

## IslandPilot — max_levels hard cap at 5 for sf=2.0 (revised from prior cap of 6)
**Source:** `01_finite_capital/01_n_to_1_ratio.py` (complete), `01_finite_capital/02_break_even_formula.py`
**Before:** max_levels upper bound = 6
**After:** Recommended max_levels ≤ 5 for all configurations, with an exception for sf=2.0 where ml=6 gives N=97.4 (still finite but with margin_of_safety=−0.015)
**Why:** Complete break-even analysis shows 0/25 configs are viable. The "least bad" configs are high-sf with moderate ml. sf=2.0, ml=5 gives N=43.6 (worst case 44 wins erased per bust). Allowing ml=6 for sf=2.0 is acceptable if pipeline's directional edge can close the 1.5% gap vs p_min=98.5%.
