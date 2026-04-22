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

## Q6: Can the abort EV curve (from 01_abort_vs_no_abort.py) be approximated analytically?
**From:** `06_abort_theory/01_abort_vs_no_abort.py` (pending results)

The empirical abort EV curve gives the optimal K by PnL and bust_rate. The analytical derivation would give a formula: EV(K) = f(win_rate, avg_win, avg_bust, K) that generalizes across HP configurations.

**Why it matters:** An analytic formula means pipeline components can compute optimal abort level dynamically without requiring empirical sweep for each configuration.
