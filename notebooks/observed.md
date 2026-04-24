# Observed Anomalies

Empirical results that contradict or extend the math-track predictions. Logged as research progresses.

Format:
```
## [YYYY-MM-DD] Script: <path>
**Observation:** What was found
**Expected (math):** What the formula predicted
**Delta:** How far off, and in which direction
**Status:** unexplained | explained | moved to anomalies.md
```

---

## [2026-04-22] Script: `02_bust_anatomy/03_bust_path_patterns.py`
**Observation:** All 60 busts over 18 years took exactly 7 positions opened with std=0. All busts terminated at level 6 (0-indexed). Config: canonical HP with max_levels=8 override.
**Expected (math):** Busts should occur at varying levels depending on market path, with some std in trade count.
**Delta:** Zero variance in bust structure. Every bust is identical in sequence length and terminal level.
**Status:** explained — with fixed HP and effective_max_levels=7 for sf=2.0 (Finding 19), the bust path is deterministic once effective_max is reached: entry at level 0 + 6 hedges = 7 positions total, bust at level 6. The only stochastic component is the entry point of the sequence.

---

## [2026-04-22] Script: `06_abort_theory/02_point_of_no_return.py`
**Observation:** Unconditional session EV is negative at $−1.70 (this is what the "level 0" row in the CSV reports — averaged over all 3,771 sessions, not a snapshot of the level-0 holding itself). Conditional EV given level k reached is more negative at every deeper level.
**Expected (math):** Positive EV should hold at low levels where win rate is high (98.4%).
**Delta:** EV is negative unconditionally — the strategy is structurally below break-even.
**Status:** explained — observed avg_win is $0.60 after 2-pip spread (ml=8 override) or $0.85 at canonical ml=6; break-even win rate is 99.58% (ml=8) or 98.98% (ml=6), both above actual win rates. Negative EV is a consequence of the cost model applied to the strategy structure. The pre-spread avg_win would depend on the TP distance and average level reached; a specific "no-spread avg_win" figure was not separately measured in this research.

---

## [2026-04-22] Script: `03_margin_mechanics/02_implicit_forced_close.py`
**Observation:** Zero margin calls across all 772 bust events (12 configs: 4 equity × 3 sf; bust counts per config are 33 for sf=1.5, 60 for sf=2.0, 100 for sf=2.5, identical across all 4 equity levels → total 4 × (33+60+100) = 772).
**Expected (math):** Higher sf (2.5) and lower equity ($1k) should trigger margin calls.
**Delta:** Margin mechanism never activates — all exits are via max_level_bust.
**Status:** explained — at 30:1 leverage and 0.5% base sizing, margin utilization stays <9% even at level 8 (sf=2.0). The geometric sizing is proportional to equity, so relative margin usage doesn't change with equity level. Bust counts are identical at each equity level because proportional sizing makes bust structure equity-invariant (Finding 11).

---

## [2026-04-22] Script: `01_finite_capital/03_capital_boundary.py`
**Observation:** Bust rate = 0.016 at ALL equity levels ($1k, $2.5k, $5k, $10k, $25k). Simulation uses fractional position units.
**Expected (math):** Lower equity should correlate with higher bust risk due to less margin buffer.
**Delta:** Zero variation in bust rate across 25x equity range.
**Status:** explained in simulation — proportional base sizing (0.5% of equity) keeps relative position sizes constant. Since bust mechanism is price-driven (max_levels reached), not capital-driven, equity is irrelevant to bust probability in the fractional-unit backtester. Live-trading caveat: OANDA integer-unit rounding (F16) makes base position 10% oversized at $1k equity, which breaks proportional sizing below ~$5k. Equity-invariance is a simulation result; live trading has a weak equity dependence at low equity.

---

## [2026-04-22] Script: `07_hp_interactions/01_sizing_x_levels.py` (observation 1)
**Observation:** Bust_rate at ml=3 is 0.1698 for ALL sizing factors tested (sf=1.3, 1.5, 1.7, 2.0, 2.5, 3.0 all identical). At ml=8, bust_rate is 0.0088 for sf=1.3, 1.5, 1.7 (identical); sf=2.0 plateaus at 0.0159 (effective_max=7); sf=2.5 at 0.0257 (effective_max=6); sf=3.0 at 0.0569 (effective_max=5).
**Expected (math):** Larger sizing_factor should create larger loss per level → harder to recover → higher bust rate.
**Delta:** Within each sf's achievable range, sizing factor has ZERO effect on bust rate. Bust rate is a pure function of effective_max_levels only.
**Status:** explained — bust occurs when price moves adversely through ALL levels without reversing. The probability of this event depends on price dynamics and grid distance, not on the dollar amount staked per level. Sizing factor affects (1) dollar loss per bust magnitude and (2) effective_max_levels via the pre-session margin feasibility cap (F19), but not the bust probability within the achievable depth range.

---

## [2026-04-22] Script: `07_hp_interactions/01_sizing_x_levels.py` (observation 2)
**Observation:** Bust rate DECREASES as max_levels increases (sf=1.3: ml=3 → 0.1698, ml=7 → 0.0159).
**Expected (math):** More levels = more exposure = higher bust rate.
**Delta:** Inverted — more levels = more recovery attempts = lower bust rate.
**Status:** explained — max_levels acts as both a recovery ceiling (can go deeper) and a bust trigger. With low ml=3, cycles that would recover at level 4-5 are instead classified as max_level_bust. With high ml=7, those same cycles recover. Bust rate reflects only cycles that fail to recover within the configured level limit.

---

## [2026-04-22] Script: `01_finite_capital/01_n_to_1_ratio.py`
**Observation:** For sf=2.5: N=66.0 at BOTH ml=6 AND ml=8 (identical). For sf=3.0: N=30.6 at ml=5, ml=6, AND ml=8 (all identical). avg_win and avg_bust are the same across these ml values. Also sf=2.0: bust_rate identical at ml=7 and ml=8.
**Expected (math):** N ratio should differ across ml values since deeper levels produce larger busts.
**Delta:** Complete invariance of N (and bust_rate) across the upper ml range for all sf values above a threshold.
**Status:** explained — `strategies/_admin/Martingale/__init__.py` line 481 computes `effective_max_levels = min(configured_max, _max_affordable_levels())`. For high sf, geometric sizing exhausts margin budget before reaching configured max_levels. Pre-session check caps sessions at the affordable depth. Result: configured ml=8 is effectively ml=5 for sf=3.0, ml=6 for sf=2.0, ml=7 for sf=1.5. This explains the plateau in N-to-1 data — the strategy never actually runs to the configured depth for high sf values. Key implication: pipeline HP bounds for max_levels are meaningless without also constraining sf, since effective_max_levels depends on sf × equity × leverage jointly.

---

## [2026-04-22] Script: `06_abort_theory/01_abort_vs_no_abort.py`
**Observation:** "bust_rate" rises monotonically as abort threshold K decreases (K=1: 53.2%, K=6: 2.4%, K=7: 1.6% no-op). PnL-optimal K=1 cuts total loss by 46% ($−6,406 → $−3,475) but "bust_rate" is 33.5× baseline.
**Expected (math):** Lower bust rate should generally correlate with better PnL.
**Delta:** bust_rate and total_pnl are anti-correlated under active abort policy.
**Status:** explained — the `is_bust` flag in `sessions_to_df` includes ALL terminal outcomes (abort, terminate, max_level_bust, sl_hit, margin_call, etc.). Aborts are counted as busts by definition, so enabling abort mechanically raises the bust_rate numerator. Separating the populations: catastrophic busts (max_level_bust only) DO decrease monotonically as K decreases (K=0→60, K=6→3, K=1→1). The anti-correlation disappears when the metric is cleanly defined. The true finding is that "bust_rate" as aggregated in the research code conflates controlled aborts (~$−0.40 each) with catastrophic busts (~$−144 each), which are economically opposite events.

---

## [2026-04-22] Script: `08_broker_mechanics/01_lot_rounding.py`
**Observation:** At $1k equity, base position target is 4.545 units → rounds to 5 units = 10% rounding error. Only 3 cases exceed 5% threshold, all at $1k equity level 0.
**Expected (math):** Rounding error should be <1% for meaningful position sizes.
**Delta:** 10% error at minimum practical equity level due to OANDA requiring integer units with only ~4-5 units at $1k.
**Status:** explained — at $5k+ equity, error falls to <1.2%. Minimum practical equity for accurate position sizing is $5k, not $1k.

---

## [2026-04-22] Script: `05_market_structure/03_volatility_vs_hedge.py`
**Observation:** At 5-pip hedge, avg_win = −$0.113 (negative). At 10-pip hedge, avg_win = +$0.036 (barely positive). At 40-pip hedge, avg_win = $3.00. Relationship is strictly monotonic but non-linear.
**Expected (math):** avg_win should scale roughly linearly with hedge distance.
**Delta:** 5-pip hedge is structurally unprofitable (negative avg_win) due to spread overhead at 40% of TP.
**Status:** explained — 2 pips spread on a 5-pip TP = 40% overhead. Multiple levels add cumulative spread. Data shows avg_win crosses zero between 5 and 10 pips (closer to 10). Sub-10-pip hedges produce non-positive avg_win at 2-pip spread; the strict "structurally unprofitable" regime is hedge ≤ ~8 pips rather than a round "12-pip" threshold.

---

## [2026-04-22] Script: `07_hp_interactions/01_sizing_x_levels.py`
**Observation:** Bust rate decreases monotonically as max_levels increases: ml=3→0.170, ml=4→0.096, ml=5→0.057, ml=6→0.026, ml=7→0.016, ml=8→0.009 (sf=1.3).
**Expected (math):** More levels means higher max exposure = higher bust probability.
**Delta:** Inverted relationship — bust_rate drops by 95% as ml goes from 3 to 8.
**Status:** explained — bust is defined as failure to recover within the max_levels limit. More levels = more recovery attempts. The bust EVENT requires the market to sustain an adverse run through ALL levels without reversing. With higher ml, fewer sequences achieve this.

---

## [2026-04-22] Script: `01_finite_capital/03_capital_boundary.py`
**Observation:** Conservative config (sf=1.5, ml=4): bust_rate=0.096 vs Aggressive config (sf=2.0, ml=8): bust_rate=0.016.
**Expected (math):** Conservative parameterization (lower sf, lower ml) should produce lower bust rate.
**Delta:** Conservative produces 6x HIGHER bust_rate than aggressive.
**Status:** explained — lower max_levels limits recovery opportunities. A config labeled "conservative" because individual level sizes are smaller actually has a higher bust frequency because cycles have fewer recovery chances. Conservative ≠ lower bust_rate; it means lower bust magnitude but higher bust frequency. True risk is N-to-1 × bust_rate = expected loss per session.
