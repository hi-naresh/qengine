# Open Questions

What this research opens up for future work.

---

## Q1: Can break-even win rate be achieved with entry timing?
**From:** Finding 1 (structural negative EV) + Finding 5 (spread kills edge)

The break-even win rate of 99.58% is 1.17pp above the empirical 98.41%. The question is whether a directional entry filter (EMA crossover, momentum, volatility regime) can improve win rate by >1.17pp without reducing session frequency below a viable threshold.

**Why it matters:** This would identify the minimum edge requirement for any entry filter — not "does it help?" but "does it help enough to cross the break-even threshold?"

**Approach:** Sweep entry filters from Phase 2/3 research, measure ΔWin_rate. Target ΔWin_rate > 0.012.

---

## Q2: Is partial abort (close losing tickets, keep L0) operationally feasible?
**From:** `06_abort_theory/04_partial_abort.py` (heuristic estimate, not full simulation)

The script approximates partial-abort EV using a simplified model: `EV_partial_keep = BASE_WIN_RATE × AVG_WIN + (1 − BASE_WIN_RATE) × (AVG_BUST × 0.7)`. With the observed parameters (win_rate=98.4%, avg_win=$0.60, avg_bust=−$144) this yields **EV ≈ −$1.01** — worse than full abort ($0).

**Caveats on the estimate:**
1. The script reuses BASE_WIN_RATE (computed from full sessions that played out) as the conditional win rate of the L0-only position after partial abort. The true conditional win rate post-partial-abort is unknown and likely differs (the session has already demonstrated adverse price motion, so L0's remaining prospects may be worse than the unconditional base rate).
2. The 0.7× factor on avg_bust is a rough assumption about how much bust magnitude is saved by closing inner legs.
3. Full simulation would require engine support for mid-session ticket selection, which is available in CFD mode (via `close_ticket(id, price)`) but was not exercised in this analysis.

**Status:** heuristic indicates partial abort is likely not viable at the current real-spread regime (~1.5 pips mean OANDA EUR-USD). To be confirmed with a full backtest variant. A necessary (not sufficient) condition for partial abort to become viable: avg_win would need to be roughly >$1.50, which does not occur at any tested (sf, ml) in the current grid under real broker spread.

---

## Q3: Is the N-to-1 ratio stable across time, or regime-dependent?
**From:** Finding 4 (N-to-1 varies with HP) + Phase 2 HMM research

The N-to-1 ratio was computed over the full 18-year dataset. In volatile regimes (e.g., 2008, 2020), bust magnitude may spike because price movements are larger, making the hedge trigger more adverse. Conversely, ranging markets may reduce bust depth.

**Why it matters:** If N varies by regime, the break-even win rate also varies — meaning a fixed abort policy may be over-cautious in ranging markets and under-cautious in trending markets.

**Approach:** Compute N-to-1 separately for each year. Correlate with realized volatility. If N varies >2x across years, regime-conditional abort thresholds are warranted.

---

## Q4: What fixed-spread floor would the strategy need to become positive EV?
**From:** Findings 1, 7b, 14 (structural negative EV under real OANDA spread, mean ~1.5 pips)

The empirical analysis uses real per-candle OANDA spread (2006-2024 full-range: mean 1.57, median 1.50, p95 1.90 pips). Under this regime, 0/25 tested configs are viable. An open question: at what *fixed* spread floor (or different broker with tighter spread) would the system cross from negative to positive EV?

**Why it matters:** The spread threshold identifies which broker environments can support this strategy. A broker offering mean spread <0.5 pips (rare for retail OANDA-class, but available at some institutional venues) might change the picture.

**Approach:** Temporarily disable real-spread loading (clear `spread_data` before backtest) and sweep canonical HP at fixed spreads 0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5 pips. Find the threshold where avg_win becomes positive and where the best config crosses from negative to positive margin of safety. Note: Q7 below overlaps — consolidating them is a to-do.

---

## Q5: Does geometric sizing outperform uniform or Fibonacci sizing?
**From:** `07_hp_interactions/01_sizing_x_levels.py` (sweep is complete for geometric only; non-geometric curves not tested)

The canonical HP uses geometric sizing (sf=2.0). The strategy supports uniform, fibonacci, sqrt, anti_martingale, and custom sequences (see `Martingale/__init__.py`). The 36-config sweep varied sf and ml within the geometric family only — non-geometric curves remain untested.

**Why it matters:** If a non-geometric sizing curve reduces N-to-1 without proportionally reducing win rates, it may shift the system into (less-) negative EV territory. Fibonacci (1,1,2,3,5,8...) grows slower than 2^n, producing smaller bust magnitudes; uniform (1,1,1,...) has the smallest busts but no recovery. Either could trade off differently than the geometric family.

**Approach:** Run 18-year backtests with sizing_curve ∈ {fibonacci, sqrt, linear, anti_martingale} at representative ml values (3, 5, 7). Compare N-to-1, win_rate, and total_pnl to the geometric reference.

---

## Q6: Can the abort EV curve be approximated analytically?
**From:** `06_abort_theory/01_abort_vs_no_abort.py` (complete)

The complete empirical abort EV curve confirms PnL-optimal K=1, bust-rate-optimal K=7 (no-op). The analytical derivation would give a formula: EV(K) = f(win_rate, avg_win, avg_bust, K, p_level_reach[k]) that generalizes across HP configurations.

The key unknown is p_level_reach[k] — the probability that a given cycle reaches exactly level k. If this can be modeled as a geometric random variable parameterized by win_rate and hedge_distance, the formula is:

`EV(K) = p_abort(K) × avg_abort_loss + (1 − p_abort(K)) × EV_no_abort`

where `p_abort(K) = ∑_{k=K}^{max} p_level_reach[k]`

**Why it matters:** Dynamic optimal abort threshold for each config without requiring a sweep per configuration.

---

## Q7: What is the minimum spread for positive EV given optimal HP?
**From:** Findings 1, 5, 7b — all confirmed negative EV under real OANDA spread (mean ~1.5 pips)

Under real OANDA per-candle spread (2006-2024 mean 1.57 pips): 0/25 configs viable. The break-even spread is where avg_win_after_spread crosses zero for the best configuration (e.g. sf=2.0 ml=3 with current avg_win=$1.38). Analytically, break-even spread s satisfies:

`avg_win(s) − 2s × pip_value × n_trades = 0`

Empirically, this threshold should be found by loading the candles but clearing the real-spread store and forcing a fixed `spread` setting at: 0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75 pips.

**Why it matters:** If a sub-1-pip spread (available at some institutional venues) makes sf=2.0 ml=3 viable, it changes the strategy value proposition for those broker environments. Note: overlaps with Q4 — they should be merged.

---

## Q8 (RESOLVED): The high-sf effective_max cap is a designed safety feature
**From:** Finding 19, anomalies.md (resolved entry)

The cap is not a bug. The strategy's `_max_affordable_levels()` method at `strategies/_admin/Martingale/__init__.py:481` computes `effective_max_levels = min(configured_max, affordable_at_session_start)`. For high sf at fixed equity/leverage/base_pct, geometric growth exhausts the margin budget before the configured depth; the pre-session feasibility check caps the session at the affordable depth. Empirically:
- sf=2.0: effective_max = 7 at $10k equity
- sf=2.5: effective_max = 6 at $10k equity  
- sf=3.0: effective_max = 5 at $10k equity
- sf ≤ 1.7: effective_max = configured (margin not binding over tested ml range)

This is a designed safety feature — the strategy refuses to enter a session it cannot fund to the configured max_levels. Zero margin calls across 772 bust events tested (F13) is consistent with this: sessions that would hit margin are never opened.

**Remaining work:** The effective_max lookup is equity-dependent and broker-dependent (leverage). A complete `effective_max_levels(sf, equity, leverage, base_pct)` table for pipeline consumption is a follow-on — currently documented only at $10k × 30:1 × 0.5%.
