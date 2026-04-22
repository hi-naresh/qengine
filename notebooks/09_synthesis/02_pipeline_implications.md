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

## ARIA Abort Policy — set abort level at Pareto-optimal K
**Source:** `06_abort_theory/01_abort_vs_no_abort.py` (pending completion)
**Before:** Abort level K = 4 (from prior Phase 2 research)
**After:** [Update once 01_abort_vs_no_abort.py sweep completes]
**Why:** The empirical Pareto-optimal K (bust_reduction / PnL_sacrifice efficiency) may differ from the theoretically derived level. The point-of-no-return analysis shows EV is already negative at level 0, so the abort policy's goal is variance reduction, not EV improvement. Optimal K balances bust frequency reduction vs total trades sacrificed.

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

<!-- To be filled when sweeps complete:
## IslandPilot — safe region bounds from sizing×levels heatmap
## ARIA — volatility-adjusted hedge distance
-->
