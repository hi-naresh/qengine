# Paper-Derived Ideas (Maybe / Future / Low Priority)

These are interesting concepts from papers that aren't immediately actionable
but worth tracking for future consideration.

---

## Drawdown-Penalized Fitness for Autopilot Optimizer
**Source**: 1830483.1830694.pdf (Wilson & Banzhaf, GECCO 2010)

Conservative fitness `f = value / maxDrawdown` outperformed raw profit in 3/4 currency pairs.
When autopilot parameter optimizer runs, it currently optimizes for PF or return.
Could add drawdown-penalized fitness as an alternative optimization target.
Wilson found moderate drawdown penalty works better for high-volatility regimes,
conservative for sustained trends.

**When**: When building autopilot iteration dashboard (Phase 2 Pipeline UX)

---

## Multi-Objective Autopilot (NSGA-II Pareto Front)
**Source**: multi_GA.pdf (Long, Kampouridis, Papastylianou, AI Review 2026)

Instead of single-fitness autopilot (PF or return), use NSGA-II to optimize 3 objectives
simultaneously: total return, bust rate, max drawdown. Produces Pareto front of
non-dominated parameter sets. Select final config using modified Sharpe Ratio:
`mSR = (TR+1)^a × (E[RoR]+1)^b / (Risk+1)^c` with user-adjustable weights a, b, c.
Paper shows MOO3 consistently outperforms single-objective optimization on 110 stocks.
Our 5-variable space (EMA periods, spacing%, TP%, max levels) is small enough for NSGA-II.

**When**: When building autopilot iteration system (after single-objective version works)

---

## Sliding Window Retrain for Entry Signal Parameters
**Source**: Chou et al. (IEEE Access 2014) — QTS trading system

Their system retrains the optimal trading rule combination every N days using a sliding window
(best result: 500-day train / 125-day test). We currently use fixed EMA 8/21 crossover.
The autopilot optimizer could periodically re-optimize EMA periods, spacing%, and TP%
using the most recent N-month window, then apply to the next M-month forward period.
Their finding: long training + short test = best performance; too-long training causes overfitting.

**When**: When building autopilot iteration system

---

## Optimal Entry Rule Count: 3-6 Conditions
**Source**: Chou et al. (IEEE Access 2014) — Section V.D.2

Found that 3-6 simultaneous indicator conditions produce optimal results.
1-2 rules = overtrading/noise. 7+ rules = signals never fire (too restrictive).
We currently use 1 entry condition (EMA crossover). Could consider adding 2-3 lightweight
filters (RSI oversold confirmation, volume threshold, ATR-based volatility gate) without
going overboard. But must monitor that adding ARIA gates doesn't push us into the
"10 rules = zero trades" territory.

**When**: Entry signal refinement research

---

## Directional Changes (DC) Paradigm for Entry Signals
**Source**: PHD_THESIS_SALMAN.pdf (Salman, Essex 2024)

Event-driven alternative to fixed-interval time series. Price movements recorded when they
exceed a threshold θ (e.g., 0.1%-2.5%). Instead of EMA crossover on fixed candles, enter
when a "directional change" of θ% occurs. Salman found GA-optimized multi-threshold
strategies outperformed traditional TA on 200 NYSE stocks over 10 years.
Could replace or supplement EMA crossover as entry trigger — DC events are inherently
adaptive to volatility (large θ = fewer trades in quiet markets, more in volatile).
However, Phase 2 found entry quality matters less than structural parameters, so low priority.

**When**: Entry signal refinement research (after autopilot optimizer)

---
