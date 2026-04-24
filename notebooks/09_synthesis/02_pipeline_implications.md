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

## IslandPilot — max_levels upper bound tightened (superseded by the N-to-1 aware safe region below)
**Source:** `01_finite_capital/01_n_to_1_ratio.py`, `06_abort_theory/02_point_of_no_return.py`
**Before:** max_levels upper bound = 6 (in _BOUND_OVERRIDES or gene bounds)
**After (superseded):** max_levels hard cap = 5 for any config where sf ≤ 1.5; see later "N-to-1 aware safe region" entry for the complete sf-conditioned bounds.
**Why:** At ml=6 with sf ≤ 1.5, the N-to-1 ratio becomes undefined (avg_win ≤ 0 after spread). For sf ≥ 2.0, avg_win remains positive at ml=6 so this cap does not apply uniformly. See Finding 4 and the consolidated safe-region entry below.

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

## ARIA Abort Policy — abort objective must change from "is_bust rate" to total-loss (or catastrophic-bust-only rate)
**Source:** `06_abort_theory/01_abort_vs_no_abort.py` (complete), `06_abort_theory/02_point_of_no_return.py`
**Before:** Abort level K = 4 (from prior Phase 2 research), objective = reduce is_bust rate
**After:** Two valid abort policies:
  - **Policy A (loss minimization):** K=1 — reduces total loss by 46% ($−6,406 → $−3,475); aborts 4,238 sessions (53% abort rate); reduces **catastrophic busts** from 60 → 1
  - **Policy B (balance continuity with catastrophic-bust reduction):** K=6 — total loss $−5,677 ($728 worse than K=1); aborts 90 sessions (2.4% abort rate); reduces catastrophic busts from 60 → 3
  - K=7/8 are no-ops (sf=2.0's effective_max is 7, so abort@7 never fires)
**Why:** Complete abort sweep shows the `is_bust` flag in the backtester includes aborts by definition (see F15/F18), so any policy that fires aborts will mechanically raise "bust_rate". The correct objectives are (1) total dollar loss and (2) count of max_level_bust events specifically. Both favor K=1 strongly. Policy B (K=6) is only justified if operational/regime-learning reasons require more session continuity than K=1 permits.

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
  1. Level count ≥ (effective_max − 2) → yellow (elevated)
  2. Equity-per-leg-pct > 3% → orange (high)
  3. Both level ≥ (effective_max − 1) AND equity-per-leg > 5% → red (abort territory)

Concrete thresholds for the canonical live config (sf=2.0, ml=6, effective_max=6):
  - Level ≥ 4 → yellow; level ≥ 5 + high margin rate → red

**Why:** In the bust-anatomy dataset (ml=8 override), all 60 busts terminated at level 6 with 7 trades and std=0 — bust depth is deterministic given sf. For canonical ml=6, busts terminate at level 5/6 (the effective_max). The level-count signal is nearly deterministic once bust trajectory begins. Adding equity-per-leg as a secondary signal provides earlier warning during the adverse run before the final bust level is reached (Finding 7: bust sessions consume 8.4× more equity per leg than wins).

---

## IslandPilot — N-to-1 aware safe region in (sf, ml) space
**Source:** `01_finite_capital/01_n_to_1_ratio.py`, `01_finite_capital/02_break_even_formula.py`, `07_hp_interactions/01_sizing_x_levels.py`
**Before:** sf and ml evolved with independent bounds
**After:** Add two filters jointly: (a) avg_win > 0 (reject N=nan configs) and (b) configured ml ≤ effective_max(sf) to avoid wasted depth. Combined bounds:
- sf=1.3: max_levels ≤ 4 (avg_win turns 0 at ml=5)
- sf=1.5: max_levels ≤ 5 (avg_win turns 0 at ml=6)
- sf=1.7: max_levels ≤ 5 (by similar logic — conservative reading)
- sf=2.0: max_levels ≤ 7 (effective_max cap; avg_win positive up to this point)
- sf=2.5: max_levels ≤ 6 (effective_max cap; any ml>6 wasted)
- sf=3.0: max_levels ≤ 5 (effective_max cap; any ml>5 wasted)
**Why:** The complete N-to-1 heatmap shows the feasible region is a non-rectangular diagonal band. Existing rectangular bounds (sf ∈ [1.3, 3.0] × ml ∈ [3, 8]) include configurations that are either (a) structurally unprofitable because avg_win ≤ 0, or (b) waste optimizer effort because ml > effective_max silently collapses to effective_max. Enforcing both filters eliminates degenerate individuals from the search space.

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

## IslandPilot — minimize sf for total-loss reduction (inverted from prior intuition)
**Source:** `07_hp_interactions/01_sizing_x_levels.py` (Finding 20)
**Before:** sf treated as "aggressive vs conservative" knob, often biased toward moderate values (2.0)
**After:** Bias sf toward LOW values (1.3-1.5) when minimizing total dollar loss is the objective.
**Why:** Bust_rate is sf-invariant at each fixed ml (Finding 15b), but total realized loss scales 2-3x with sf. At ml=5: sf=1.3 loses $2,968 vs sf=3.0 loses $8,877 over 18 years for identical bust frequency. Low sf is dominance-free on the risk dimension.

**Caveat on avg_win interpretation:** At fixed ml, HIGHER sf produces HIGHER avg_win per session (larger position sizes → larger realized dollar wins). For ml=3: sf=1.3 → $0.71, sf=2.0 → $1.38, sf=3.0 → $2.56. However, at fixed ml, higher sf also produces proportionally larger avg_bust — and over 18 years, the bust-loss term dominates. Hence despite higher per-session avg_win, total cumulative PnL is worse at higher sf. The "best avg_win" and "best total PnL" criteria pick different sf values; total PnL is the correct criterion when evaluating long-run performance.

sf=1.3 ml=3 is the Pareto-optimal starting point by **total_pnl** (−$2,438 over 18 years), though sf=2.0 ml=3 yields higher per-session avg_win ($1.38 vs $0.71) at the cost of 40% more total loss.

## IslandPilot — max_levels hard cap at 5 for sf=2.0 (revised from prior cap of 6)
**Source:** `01_finite_capital/01_n_to_1_ratio.py` (complete), `01_finite_capital/02_break_even_formula.py`
**Before:** max_levels upper bound = 6
**After:** Recommended max_levels ≤ 5 for all configurations, with an exception for sf=2.0 where ml=6 gives N=97.4 (still finite but with margin_of_safety=−0.015)
**Why:** Complete break-even analysis shows 0/25 configs are viable. The "least bad" configs are high-sf with moderate ml. sf=2.0, ml=5 gives N=43.6 (worst case 44 wins erased per bust). Allowing ml=6 for sf=2.0 is acceptable if pipeline's directional edge can close the 1.5% gap vs p_min=98.5%.
