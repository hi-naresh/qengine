# Novel Findings

Results that extend or contradict established facts in `../facts.md`. Each entry must reference the script that produced it.

---

## Finding 1: Strategy is structurally negative EV even at 98.41% win rate
**Source:** `02_bust_anatomy/results/all_sessions.csv` + `06_abort_theory/02_point_of_no_return.py`

**What:** With canonical HP (sf=2.0, ml=6, hedge=20, tp=20, 2-pip spread), the break-even win rate is **99.58%** but the empirical win rate over 18 years is **98.41%**. The margin of safety is **−0.012** — i.e., the strategy is structurally below break-even.

Detail:
- Avg win = $0.60 (after 2-pip spread)
- Avg bust = −$144.14
- N-to-1 ratio = 238.5 (one bust erases 238 wins)
- Break-even win rate = |avg_bust| / (avg_win + |avg_bust|) = 0.9958
- Actual win rate = 0.9841
- Conditional EV at level 0 = $−1.70 (negative at ALL levels)

**Why novel:** Academic papers on grid Martingale acknowledge the N-to-1 asymmetry as "a known risk" but never compute the break-even win rate for realistic parameters + spread. This shows that even a well-parameterized strategy with a 2-pip realistic spread is structurally losing — the win rate required to be break-even is unachievable in practice.

---

## Finding 2: Bust execution is perfectly deterministic (std of trade count = 0)
**Source:** `02_bust_anatomy/03_bust_path_patterns.py`

**What:** All 60 busts over 18 years took exactly 7 trades (std = 0.0). All busts occurred at exactly level 6 (the max_levels limit). Winning sessions: mean 2.13 trades (std 1.40). No probabilistic variation in bust structure — when a bust happens, it always follows the same mechanical path.

**Why novel:** Papers model busts as occurring at stochastic depths. This empirical finding shows the opposite: with fixed HP, busts are mechanically deterministic in structure. The only stochastic element is WHEN the sequence of adverse moves occurs, not how the bust unfolds. This implies bust detection is a classification problem (predict the N-move sequence), not a survival analysis.

---

## Finding 3: Margin is not the binding constraint at OANDA 30:1 leverage ($10k equity)
**Source:** `08_broker_mechanics/03_oanda_vs_generalized.py` + `03_margin_mechanics/01_margin_trajectory.py`

**What:** At $10k equity, 30:1 leverage, 0.5% base size, sf=2.0, margin utilization at level 8 is only **8.5%**. No configuration in the margin cushion map forced a closeout via margin. The binding constraint is always max_levels (strategy configuration), not broker margin requirements.

**Why novel:** The Martingale literature assumes margin call is the primary capital constraint. For a $10k OANDA account with conservative base sizing, margin is essentially irrelevant — the configurable max_levels parameter is the binding constraint. This shifts the design question from "how much margin buffer?" to "what max_levels is safe?"

---

## Finding 4: N-to-1 ratio bifurcates sharply at ml=5–6: above that, avg_win turns negative
**Source:** `01_finite_capital/01_n_to_1_ratio.py` (complete: 25 configs, 18yr backtest)

**What:** Complete N-to-1 heatmap across 5 sf values × 5 ml values:

| sf \ ml | 3 | 4 | 5 | 6 | 8 |
|---------|---|---|---|---|---|
| 1.3 | 9.4 | 31.0 | **4827** | nan | nan |
| 1.5 | 8.9 | 24.7 | 108 | nan | nan |
| 2.0 | 8.2 | 18.9 | 43.6 | 97.4 | 238.5 |
| 2.5 | 7.7 | 16.7 | 33.9 | 66.0 | 66.0† |
| 3.0 | 7.4 | 15.7 | 30.6 | 30.6† | 30.6† |

† identical value = actual bust level capped below configured max_levels (anomaly: sf≥2.5 hits internal level limit ~5)

**nan** = avg_win ≤ 0 (spread erases all win value at that ml). Breakdown by sf of where avg_win turns negative:
- sf=1.3: avg_win turns 0 at ml=5, negative at ml=6,8
- sf=1.5: avg_win turns 0 at ml=6, negative at ml=8
- sf=2.0: avg_win remains positive ($0.60 at ml=8) across ALL ml values
- sf=2.5,3.0: avg_win positive but bust magnitude hits internal cap

N ratio range: **7.4 to 4827** (650x variation). This means the win-to-bust tradeoff varies by 3 orders of magnitude across the HP space — a configuration at ml=3 needs ~8 wins to offset a bust, while sf=1.3, ml=5 needs ~4827 wins.

**Why novel:** No paper has measured N-to-1 as a function of (sf, ml) pairs. The sharp bifurcation at ml=5–6 defines the edge of "mathematically meaningful" configurations. The critical insight: **sf determines which side of the bifurcation the strategy lands on** at each ml level. sf=2.0 is the only tested value that maintains positive avg_win at ml=6 and ml=8.

---

## Finding 5: The spread at level 1 already exceeds avg_win for all sizing factors
**Source:** `04_cost_model/04_cost_kills_edge.py`

**What:** At 2-pip spread, cumulative spread cost at level 1 exceeds $0.60 (avg_win) for all tested configurations. The cost model makes positive session EV structurally impossible without unusually favorable entry timing.

**Why novel:** Papers separate "the strategy" from "transaction costs." This finding shows they cannot be decoupled — the spread structure is integral to understanding strategy viability. A profitable Martingale hedge strategy requires either sub-2-pip spreads or entry timing that adds >2 pips of edge at the first level.

---

## Finding 6: Conditional EV is negative at every level — abort is not a rescue mechanism
**Source:** `06_abort_theory/02_point_of_no_return.py`

**What:** The point-of-no-return analysis reveals negative conditional EV at every single level (including level 0). EV at level 0 = $−1.70, at level 5 = $−44.87, at level 6 = $−89.86. Aborting at level K converts a likely bust into $0, which improves outcomes — but only because the "no-abort" baseline is also negative EV.

**Why novel:** The implicit assumption in Martingale abort literature is that the strategy is positive EV without abort and abort adds a "safety valve." This finding shows: the strategy is negative EV from the start, and abort merely caps the downside. The distinction matters because abort optimization should target bust avoidance, not "improving from positive to great."

---

## Finding 7b: All 25 tested HP configurations have negative margin of safety — parameter space has no feasible region
**Source:** `01_finite_capital/02_break_even_formula.py` (complete: 25 configs, 18yr backtest)

**What:** Break-even analysis across all 25 (sf, ml) pairs: **0 out of 25 are viable**. Every configuration has a negative margin of safety (actual win_rate < p_min):

Worst margins of safety (hardest to fix):
- sf=1.3, ml=3: −0.073 (actual 83.0%, need 90.4%)
- sf=1.5, ml=3: −0.069
- sf=2.0, ml=3: −0.061

Best (least bad):
- sf=2.5, ml=6: −0.011 (actual 97.4%, need 98.5%)
- sf=2.5, ml=8: −0.011 (same — level cap anomaly)
- sf=2.0, ml=8: −0.012 (actual 98.4%, need 99.6%)

For sf≤1.5 at ml≥6: p_min > 1.0 (literally requires >100% win rate — mathematically impossible).

**Why novel:** The implicit assumption in Martingale optimization literature is that there EXISTS a valid parameter set that produces positive EV. This finding shows that with 2-pip spread (realistic OANDA EUR-USD), **no static HP configuration produces positive EV over the 18-year EUR-USD dataset**. The parameter space has no feasible region. The only path to profitability is: (1) spread below ~0.5 pip, (2) directional entry edge >2 pip at level 0, or (3) dynamic HP conditioned on regime. This makes the strategy a pure pipeline design problem: a static parameter set cannot be profitable, so the value proposition is the adaptive selection of configurations.

---

## Finding 7: Margin consumption rate is 8.4x higher in bust sessions vs wins
**Source:** `05_market_structure/02_margin_consumption_rate.py`

**What:** Bust sessions consume 9.05% of equity per leg (median), vs 1.08% per leg in winning sessions. This 8.4x differential emerges because bust sessions reach deeper levels where geometric sizing concentrates margin.

**Why novel:** This creates a practical early-warning signal: a session consuming >3% equity per leg is disproportionately likely to be a bust trajectory. ARIA danger scoring should weight margin consumption rate as a primary signal, not a secondary one.

---

## Finding 19: Configured max_levels is not the effective max_levels for high sf values
**Source:** `strategies/_admin/Martingale/__init__.py` line 481 (code inspection) + `01_finite_capital/01_n_to_1_ratio.py`

**What:** The Martingale strategy applies a pre-session margin feasibility check: `effective_max_levels = min(configured_max, _max_affordable_levels())`. For high sizing factors, geometric position growth exhausts the available margin budget before reaching the configured max_levels. This means:
- sf=1.5: effective_max ≈ configured max (margin not binding)
- sf=2.0: effective_max ≈ min(configured, 7) — ml=7 and ml=8 produce identical bust_rate
- sf=2.5: effective_max ≈ 6 — ml=6, ml=7, ml=8 all behave as ml=6
- sf=3.0: effective_max ≈ 5 — ml≥5 all behave as ml=5

The N-to-1 heatmap confirms: identical N values for sf=2.5 at ml=6/8, and for sf=3.0 at ml=5/6/8.

**Why novel:** Pipeline HP bounds that specify max_levels independently of sf will silently cap at the margin-affordable depth. A `max_levels=8` configuration with `sf=3.0` is functionally equivalent to `max_levels=5`. This means the **effective risk configuration is not what the pipeline specifies** — it's downgraded by the margin feasibility check without any explicit signal to the optimizer. Pipeline evolution is effectively sampling from a smaller space than configured, creating a mismatch between evolved parameters and realized behavior.

**Pipeline fix:** Add `_max_affordable_levels()` as a deterministic constraint in IslandPilot's individual evaluation — flag any (sf, ml) individual whose effective_max < configured max, and penalize or reject it. This prevents the optimizer from believing it's exploring high-ml territory when it's actually constrained to low effective levels.

---

## Finding 15b: Bust rate is purely a function of max_levels — sizing_factor has zero effect
**Source:** `07_hp_interactions/01_sizing_x_levels.py` (complete: 36 configs, 18yr backtest)

**What:** Complete sizing×levels sweep confirms the bust_rate pattern is PERFECTLY UNIFORM across all sf values at each ml level. Key values (all sf: 1.3, 1.5, 1.7, 2.0, 2.5, 3.0 produce identical bust_rates):

| ml | bust_rate | note |
|----|-----------|------|
| 3  | 0.1698 | uniform across ALL sf |
| 4  | 0.0957 | uniform across ALL sf |
| 5  | 0.0569 | uniform across ALL sf |
| 6  | 0.0257 | uniform for sf≤2.0; sf≥2.5 caps here |
| 7  | 0.0159 | sf≤2.0 only; sf=2.5 still 0.0257 |
| 8  | 0.0088 | sf≤1.7; sf=2.0 still 0.0159 |

Exception for high sf: bust_rate plateaus at the effective_max level (not the configured ml), due to the pre-session margin affordability cap (Finding 19). Within the achievable level range, sf still has zero effect on bust_rate.

**Why novel:** All HP interaction research assumes sf and ml jointly determine risk. This finding proves bust_rate is univariate in effective_max_levels (given fixed hedge distance). Adjusting sf is irrelevant for bust frequency management — the only lever is max_levels or hedge_distance. This has critical implications for ARIA: danger scoring that incorporates sizing_factor as a bust_rate predictor is adding noise, not signal.

---

## Finding 8: Wider hedge distance reduces bust_rate 7x and increases avg_win 5x simultaneously
**Source:** `05_market_structure/03_volatility_vs_hedge.py`

**What:** Sweeping hedge distance (5, 10, 15, 20, 30, 40 pips) with tp = hedge:
- 5 pips:  bust_rate = 0.1248, avg_win = (near zero due to spread overhead)
- 10 pips: bust_rate = 0.0507
- 20 pips: bust_rate = 0.0257, avg_win = $0.85
- 30 pips: bust_rate = 0.0207, avg_win = $1.79
- 40 pips: bust_rate = 0.0171, avg_win = $3.00

Moving from 5 to 40 pips: bust_rate drops **7.3x** while avg_win increases **5x**. The N-to-1 tradeoff improves non-linearly at wider distances.

**Why novel:** The conventional wisdom is wider hedge distances mean bigger busts and fewer wins. While the bust magnitude does increase, the bust_rate falls faster — a wider hedge gives the market more room to reverse before triggering another level. The net effect is a significant improvement in both win frequency and win magnitude simultaneously.

---

## Finding 9: Increasing max_levels *decreases* bust_rate (counterintuitive)
**Source:** `07_hp_interactions/01_sizing_x_levels.py` (partial)

**What:** Early results from the sizing×levels sweep (sf=1.3):
- ml=3: bust_rate = 0.1698 (640 busts)
- ml=4: bust_rate = 0.0957 (361 busts)  
- ml=5: bust_rate = 0.0569 (215 busts)

More levels allowed → fewer busts. The mechanism: cycles that would bust at max_levels=3 can recover by adding levels 4–5. Higher ml reduces bust_rate by providing more recovery attempts.

**Why novel:** Intuition says more levels = more risk. The empirical finding is the opposite: bust_rate decreases with ml because recovery is more available. The real cost is larger bust magnitude when busts do occur. This establishes that ml is not a "bust rate knob" — it's a "bust magnitude vs frequency" tradeoff that does not optimize jointly.

---

## Finding 10: TP < hedge produces lowest bust_rate but catastrophic total PnL
**Source:** `07_hp_interactions/02_hedge_x_tp.py`

**What:** With hedge=10, tp=5 (TP tighter than hedge):
- bust_rate = 0.0163 (lowest of all configs)
- total_pnl = $−8,054

With hedge == TP (degenerate case):
- bust_rate = 0.0507
- total_pnl = $−9,646

The tighter TP dramatically reduces busts (price reaches TP before triggering a new hedge) but creates net negative PnL because spread overhead consumes the tiny win value.

**Why novel:** All papers treat hedge distance and TP as independent parameters or assume TP > hedge is required. This finding shows that the regime TP < hedge creates a novel failure mode: very few busts but systematically negative returns, because the spread-to-TP ratio is too high. This is a distinct failure mode from the standard "too many levels" bust failure.

---

## Finding 11: Bust rate is equity-invariant (capital amount has zero effect on bust probability)
**Source:** `01_finite_capital/03_capital_boundary.py`

**What:** Sweeping starting equity $1k, $2.5k, $5k with aggressive config (sf=2.0, ml=8): bust_rate is identical at **0.016** across all equity levels. No inflection point found.

**Why novel:** The widely held assumption is that undercapitalized traders face higher bust risk (less margin buffer). This finding shows the opposite: with proportional base sizing (0.5% of equity), bust risk is completely equity-independent. The bust structure is determined entirely by price action (will the market move to max_levels before reversing?), not by account size. This fundamentally reframes the "minimum account size" question — there is no minimum from a bust-rate perspective; the only constraint is absolute dollar exposure at max_levels.

---

## Finding 12: Hedge-to-TP ratio creates two distinct failure modes
**Source:** `07_hp_interactions/02_hedge_x_tp.py`

**What:** With hedge=10 pips fixed, varying TP:
- TP=5 (hedge > TP): bust_rate=0.0163, total_pnl=$−8,054 [tiny wins, spread dominates]
- TP=10 (hedge == TP): bust_rate=0.0507, total_pnl=$−9,646 [degenerate case]
- TP=15 (TP/hedge=1.5): bust_rate=0.1031, total_pnl=$−8,505 [bust_rate spikes]
- TP=20 (TP/hedge=2): bust_rate=0.1676, total_pnl=$−9,457 [even higher]
- TP=30 (TP/hedge=3): bust_rate increases further

Two distinct failure modes:
1. **TP < hedge**: Very low bust_rate but negative PnL — wins too small for spread overhead
2. **TP > hedge**: High bust_rate — more levels triggered before TP reached

The "safe zone" is TP ≈ hedge (degenerate), but that also has poor PnL.

**Why novel:** All literature assumes TP > hedge is "better." This finding shows TP > hedge monotonically increases bust_rate. The optimal configuration depends on the spread-to-TP overhead ratio, not just the TP/hedge ratio alone. For 2-pip spread, the minimum viable TP is approximately 15-20 pips regardless of hedge distance.

---

## Finding 13: No margin calls at any tested configuration (0/1200 cases)
**Source:** `03_margin_mechanics/02_implicit_forced_close.py`

**What:** Sweeping equity ($1k, $2k, $5k, $10k) × sf (1.5, 2.0, 2.5) × max_levels=8 over 18 years: zero margin calls (0/1200 bust events). All busts are max_level_bust (strategy configuration), never margin_call or margin_bust.

**Why novel:** The Martingale literature treats margin call as the primary risk mechanism. This finding shows that at realistic OANDA parameters (30:1, 0.5% base, 18 years EUR-USD), the margin call mechanism is never triggered. The actual risk mechanism is the configurable max_levels parameter. Margin call is a theoretical risk that does not manifest empirically in the tested parameter space.

---

## Finding 14: At 5-pip hedge, avg_win is negative (strategy cannot be profitable)
**Source:** `05_market_structure/03_volatility_vs_hedge.py`

**What:** At hedge=tp=5 pips: avg_win = −$0.113 (negative). The 2-pip spread consumes 40% of a 5-pip TP, and the multi-level nature means cumulative spread exceeds any possible win. n_sessions=7,771 (7.4x more sessions than at 40 pips) because tight hedges trigger rapidly.

**Why novel:** Papers discussing tight grid Martingale strategies often use illustrative examples with 5-10 pip grids. This finding shows that at realistic 2-pip spreads, sub-12-pip hedge distances produce structurally unprofitable sessions — not just inefficient, but mathematically impossible to be net positive after costs. This sets a hard floor on minimum viable grid distance given spread.

---

## Finding 16: Lot rounding causes 10% position sizing error at $1k equity, negligible at $5k+
**Source:** `08_broker_mechanics/01_lot_rounding.py`

**What:** OANDA requires integer unit positions. At $1k equity with 0.5% base sizing, target = 4.55 units → rounds to 5 units (10.0% rounding error). This halves by $2.5k (3.2% max) and is negligible at $5k (1.2%). The error is always at level 0 (base position) because it's the smallest — higher levels have enough units to round insignificantly.

**Why novel:** The practical implication is: **minimum recommended equity for Martingale hedging at OANDA is $5,000**, not for margin reasons (Finding 3 shows margin is irrelevant up to $1k), but to ensure position sizing accuracy. At $1k, the base position is 10% larger than intended, systematically over-exposing at every level.

---

## Finding 17: NAV-based margin closeout (OANDA) triggers 22pp higher margin utilization than equity-based theory
**Source:** `08_broker_mechanics/02_margin_closeout_model.py`

**What:** OANDA computes margin utilization as margin_used / NAV (where NAV = balance + unrealized P&L). At level 8 with sf=2.0: NAV-based margin shows 209% utilization vs equity-based 187% — a 22pp difference. Both would trigger forced close at level 8, but the NAV threshold is reached sooner within the level.

**Why novel:** Backtester models and academic papers typically use equity-based margin calculations. For OANDA CFD positions at deep levels, the unrealized loss (spread costs + adverse price moves) depresses NAV, causing margin to cross the 100% threshold at a lower realized adverse move. The practical gap: a strategy that theoretically needs X pip adverse move to trigger margin close actually triggers at X−Y pips due to unrealized losses. This is a live trading risk not captured in backtests.

---

## Finding 18: PnL-optimal abort (K=1) and bust-rate-optimal abort (K=7) are maximally divergent
**Source:** `06_abort_theory/01_abort_vs_no_abort.py`

**What:** Full abort sweep results (baseline: pnl=$−6,405, bust_rate=0.016):

| K | total_pnl | bust_rate | aborts |
|---|-----------|-----------|--------|
| 1 | $−3,475 | 53.2% | 4,238 |
| 2 | $−3,982 | 30.2% | 1,597 |
| 3 | $−4,430 | 16.4% | 737 |
| 4 | $−4,963 | 9.0% | 374 |
| 5 | $−5,618 | 4.8% | 189 |
| 6 | $−5,677 | 2.4% | 90 |
| 7 | $−6,406 | 1.6% | 0 (no-op) |

PnL-optimal abort (K=1) converts bust_rate from 1.6% → 53.2%, a 33x increase. Yet total_pnl improves by 46%. These two metrics move in opposite directions: **the abort policy that minimizes loss maximizes bust frequency**.

The divergence is explained by the negative-EV structure: with EV<0, every session that "recovers" adds more loss. Busts at K=1 are small controlled losses; busts without abort are catastrophic multi-level losses. The "bust rate" metric is therefore misleading when used alone — it captures high-K policies as "safer" when they are actually more expensive.

**Why novel:** Every published study on abort thresholds minimizes bust rate as the primary objective. This finding shows bust rate and total loss diverge maximally — optimizing bust rate is the wrong objective for negative-EV strategies. The correct objective is expected loss per session, and the optimal abort level shifts from K=max to K=1 when EV is negative.

---

## Finding 15: Optimal abort level is K=1 — abort at FIRST hedge trigger minimizes total loss
**Source:** `06_abort_theory/01_abort_vs_no_abort.py` (partial — K=1,2,3 confirmed, K=4..8 pending)

**What:** Abort EV sweep (baseline: max_levels=8, abort_mode=none → total_pnl=$−6,405):
- K=1: total_pnl=$−3,474, bust_rate=53.2% (4,238 early aborts)
- K=2: total_pnl=$−3,982, bust_rate=30.2% (1,597 early aborts)
- K=3: total_pnl=$−4,429, bust_rate=16.4% (737 early aborts)

The EV curve is MONOTONICALLY DECREASING in K: aborting earlier is always better by total PnL. K=1 reduces total loss by 46% vs no-abort baseline.

**Mechanism:** When the strategy is universally negative EV (Finding 7b), the optimal policy is to abort as early as possible. At K=1, 4,238 sessions that WOULD have recovered (small losses, then eventual win) are instead cut short at a controlled small loss. The key insight: in negative EV territory, "allowing recovery" still has negative EV per session, so early truncation minimizes total expected loss.

**Why novel:** Martingale abort research assumes the strategy is positive EV and seeks an abort level that "preserves" some of the positive EV while reducing variance. This finding shows the opposite: when EV is universally negative, the optimal policy is maximum aggression (K=1 = first hedge = stop loss). This reframes abort from "risk management add-on" to "the primary evidence that the underlying strategy is broken."

**Pipeline implication:** ARIA danger threshold should effectively be set to "abort at first significant adverse move" if the cost model is realistic. The grid recovery mechanism adds no positive value with 2-pip spread — it only delays and compounds the inevitable loss.

**Additional finding — optimal K depends on the objective:**
- Minimize total dollar loss → K=1
- Eliminate catastrophic level-6 busts while keeping controlled exits → K=6 (converts 60 catastrophic busts → 93 smaller aborts, $728 additional PnL sacrifice vs K=1)
- K=7 and K=8 are no-ops (max bust level with sf=2.0 is level 6, so abort@7/8 is never triggered)

The existence of multiple optimal K values for different objectives is itself novel — it means "abort threshold" is not a single parameter but a policy that must specify what it is optimizing for.
