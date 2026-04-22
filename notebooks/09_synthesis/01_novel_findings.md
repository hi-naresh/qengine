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

## Finding 4: Bust severity grows faster than geometrically with max_levels
**Source:** `01_finite_capital/01_n_to_1_ratio.py` (partial results)

**What:** Early results from the N-to-1 sweep: N ratio increases super-geometrically with max_levels.
- ml=3: N ≈ 9.4 (manageable)
- ml=4: N ≈ 18.9–31.0 (depending on sf)
- ml=5: N ≈ 43.6–4827 (sf-dependent, bifurcation)
- ml≥6: N = nan (avg_win ≤ 0 after spread, infinite bust/win ratio)

The transition at ml=5–6 is sharp: sf=1.3 gives N=4827 while sf=2.0 gives N=43.6 at ml=5. At ml≥6, spread fully erodes avg_win to near-zero, making N undefined.

**Why novel:** No paper has measured N-to-1 as a function of (sf, ml) pairs. The sharp bifurcation at ml=5–6 is a structurally significant threshold that defines the edge of "mathematically meaningful" configurations.

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

## Finding 7: Margin consumption rate is 8.4x higher in bust sessions vs wins
**Source:** `05_market_structure/02_margin_consumption_rate.py`

**What:** Bust sessions consume 9.05% of equity per leg (median), vs 1.08% per leg in winning sessions. This 8.4x differential emerges because bust sessions reach deeper levels where geometric sizing concentrates margin.

**Why novel:** This creates a practical early-warning signal: a session consuming >3% equity per leg is disproportionately likely to be a bust trajectory. ARIA danger scoring should weight margin consumption rate as a primary signal, not a secondary one.

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

<!-- To be filled when abort sweep completes:
- Finding 15: Optimal abort level K (from 06_abort_theory/01_abort_vs_no_abort.py)
-->
