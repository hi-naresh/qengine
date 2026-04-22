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
**From:** `06_abort_theory/04_partial_abort.py`

The theoretical analysis shows partial abort (keeping L0 running while closing deeper losing tickets) has positive EV if L0 retains its base win rate. This requires the engine to support closing individual tickets while keeping others open — which CFD mode already supports via `close_ticket(id, price)`.

**Why it matters:** Partial abort could improve on full abort by preserving the L0 position's directional edge rather than surrendering all unrealized exposure.

**Approach:** Implement a strategy variant that closes all tickets except L0 when a configurable margin threshold is exceeded. Run empirical comparison vs full abort and no-abort.

---

## Q3: Is the N-to-1 ratio stable across time, or regime-dependent?
**From:** Finding 4 (N-to-1 varies with HP) + Phase 2 HMM research

The N-to-1 ratio was computed over the full 18-year dataset. In volatile regimes (e.g., 2008, 2020), bust magnitude may spike because price movements are larger, making the hedge trigger more adverse. Conversely, ranging markets may reduce bust depth.

**Why it matters:** If N varies by regime, the break-even win rate also varies — meaning a fixed abort policy may be over-cautious in ranging markets and under-cautious in trending markets.

**Approach:** Compute N-to-1 separately for each year. Correlate with realized volatility. If N varies >2x across years, regime-conditional abort thresholds are warranted.

---

## Q4: What is the minimum spread at which the strategy becomes positive EV?
**From:** Finding 5 (spread kills edge at level 1)

The analysis was conducted at 2-pip spread. The break-even spread (where avg_win_after_spread > 0) is a function of (sf, ml, hedge, tp). Computing this analytically would give a "minimum broker quality" requirement.

**Why it matters:** The spread threshold identifies which brokers can support this strategy. A 1-pip broker might change the entire picture.

**Approach:** Rerun canonical HP backtest at spreads 0, 0.5, 1, 1.5, 2, 2.5, 3 pips. Find the spread where avg_win = 0 and where the system crosses from negative to positive EV.

---

## Q5: Does geometric sizing outperform uniform or Fibonacci sizing?
**From:** `07_hp_interactions/01_sizing_x_levels.py` (pending results)

The canonical HP uses geometric sizing (sf=2.0). The strategy was designed with this in mind, but it's possible that uniform sizing (1x at each level) or Fibonacci sizing (1, 1, 2, 3, 5, 8) would produce a different N-to-1 profile while maintaining acceptable win rates.

**Why it matters:** If a non-geometric sizing curve reduces N-to-1 without proportionally reducing win rates, it may shift the system into positive EV territory.

**Approach:** Implement uniform and Fibonacci sizing modes in the Martingale strategy. Run full 18-year backtests and compare N-to-1, win_rate, and EV.

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
**From:** Findings 1, 5, 7b — all confirmed negative EV at 2-pip spread

With 2-pip spread: 0/25 configs viable. The break-even spread is where avg_win_after_spread crosses zero for the best configuration (sf=2.0, ml=3: avg_win=1.38 before spread adjustment). Analytically, break-even spread s satisfies:

`avg_win(s) − 2s × pip_value × n_trades = 0`

Empirically, this threshold should be found by re-running the canonical backtest at spreads: 0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0 pips.

**Why it matters:** If a 1-pip spread (available at some brokers) makes sf=2.0, ml=3 viable, it changes the entire strategy value proposition for those broker environments.

---

## Q8: Does the high-sf level capping anomaly reflect a configurable strategy parameter or a bug?
**From:** anomalies.md — sf=2.5 caps at level 5 stats despite max_levels=8; sf=3.0 caps at level 4-5

The N-to-1 results confirm: for sf≥2.5, increasing max_levels beyond ~5 produces no change in N ratio, win_rate, or avg_bust. This strongly suggests an internal strategy limit at ~level 5 for high sf values.

**Hypothesis:** The Martingale strategy has an internal equity check: if adding a new hedge would reduce equity below some threshold (e.g., 50%), the cycle terminates before reaching configured max_levels. With sf=3.0 and base_size=0.5%, the L5 position is 0.5% × 3^5 = 12.2% of equity — at this point, unrealized losses may trigger a pre-configured internal guard.

**Why it matters:** If this is a bug (unintended early termination), it should be fixed. If it's a feature (implicit safety limit), it should be documented as an HP interaction that reduces effective max_levels for high sf values — the configured max_levels may not be the actual limit in live trading.
