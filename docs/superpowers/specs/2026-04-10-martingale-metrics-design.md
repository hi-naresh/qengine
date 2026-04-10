# Martingale-Native Metrics Framework

## Problem

The current backtest metrics are inherited from a generic trading engine (Jesse fork). They assume independent trades with roughly normal return distributions. For a martingale/surefire hedging system:

- **The session is the atomic unit**, not the individual trade. A "losing trade" at L2 is structurally required, not a signal of poor edge.
- **Returns are bimodal**: many small wins, rare catastrophic losses. Sharpe/Sortino/Calmar assume normal-ish distributions and produce misleading values.
- **The central question is survival**, not risk-adjusted return. A system with positive arithmetic EV can still be guaranteed to ruin if geometric growth is negative.

## Design

### New Metric Groups (replace current layout)

The backtest results page reorganizes into **4 groups** replacing the current 5 (Performance, Hedge Session Stats, Risk, Trade Statistics, Forex):

1. **Session Performance** — the bottom line, measured at the right unit
2. **Survival & Ruin** — will this system survive long-term?
3. **Structural Diagnostics** — where do sessions go wrong?
4. **Capital & Costs** — efficiency and drag

Trade-level metrics are **hidden by default** behind a collapsible "Raw Trade Data" section for debugging only.

---

### Group 1: Session Performance

The primary results. Every metric here uses the **session** as its unit.

| Key | Label | Formula / Source | Notes |
|-----|-------|-----------------|-------|
| `total_sessions` | Sessions | Count of completed hedge sessions | Already exists in `hedge_metrics` |
| `session_win_rate` | Session Win Rate | winning_sessions / total_sessions | Already exists |
| `session_profit_factor` | Session Profit Factor | sum(winning_session_pnls) / abs(sum(losing_session_pnls)) | **NEW**. The true profit factor. |
| `ev_per_session` | EV / Session | mean(session_pnls) | Already exists |
| `median_session_pnl` | Median Session PnL | median(session_pnls) | **NEW**. Median resists bust distortion better than mean. |
| `net_profit` | Net Profit | finishing_balance - starting_balance | Keep from current |
| `net_profit_percentage` | Net Profit % | (net_profit / starting_balance) * 100 | Keep from current |
| `annual_return` | Annual Return (CAGR) | CAGR of daily balance | Keep from current |
| `starting_balance` | Starting Balance | — | Keep |
| `finishing_balance` | Finishing Balance | — | Keep |

---

### Group 2: Survival & Ruin

The metrics that answer: "will this blow up?"

| Key | Label | Formula / Source | Notes |
|-----|-------|-----------------|-------|
| `bust_rate` | Bust Rate | busts / total_sessions | **NEW** as a top-level metric (currently buried in hedge stats as just a count). |
| `bust_count` | Busts | count of bust sessions | Already exists as `total_busts` |
| `wins_to_recover` | Wins to Recover (WTR) | abs(avg_bust_loss) / avg_session_win | **NEW**. "One bust erases N wins." The most intuitive cost-of-bust metric. |
| `geometric_growth_rate` | Geometric Growth Rate | mean(ln(1 + r_session)) where r_session = session_pnl / balance_at_session_start | **NEW**. If negative, guaranteed ruin regardless of arithmetic EV. THE long-run survival metric. |
| `survival_100` | P(Survive 100 sessions) | (1 - bust_rate) ^ 100 | **NEW**. |
| `survival_500` | P(Survive 500 sessions) | (1 - bust_rate) ^ 500 | **NEW**. |
| `survival_half_life` | Half-Life (sessions) | ln(0.5) / ln(1 - bust_rate) | **NEW**. Number of sessions at which P(survive) = 50%. Infinite if bust_rate = 0. |
| `worst_bust_pnl` | Worst Bust PnL | min(bust_session_pnls) | Already exists |
| `avg_bust_loss` | Avg Bust Loss | mean(bust_session_pnls) | **NEW**. |
| `bust_severity_std` | Bust Severity Spread | std(bust_session_pnls) | **NEW**. Are all busts similar or do some blow up much worse? |
| `max_drawdown` | Max Drawdown % | max drawdown of daily balance | Keep from current |
| `max_consecutive_session_losses` | Max Consec. Losses | — | Already exists |
| `margin_closeouts` | Margin Close-outs | — | Keep |
| `account_blown` | Account Blown | — | Keep |

---

### Group 3: Structural Diagnostics

Where sessions go wrong. The Markov chain view of the system.

| Key | Label | Formula / Source | Notes |
|-----|-------|-----------------|-------|
| `depth_distribution` | Depth Distribution | histogram: count of sessions by max_level reached | **NEW** as a structured metric. Currently exists as `depth_breakdown` but only in comparison view. Promote to primary. |
| `level_transitions` | Level Transition Matrix | For each level L: P(win at L), P(escalate to L+1) | **NEW**. Computed from trade metadata. Each session that reaches level L either wins at L or escalates. This is the full Markov chain. |
| `ev_by_depth` | EV Decomposition by Depth | For each max_depth D: count, total_pnl, avg_pnl | **NEW**. Shows which levels actually generate profit vs. destroy it. |
| `time_at_depth` | Time at Depth | For each level L: total bars (or hours) spent | **NEW**. Deep levels tie up capital longer. Computed from trade holding periods grouped by level. |
| `avg_legs_per_session` | Avg Legs / Session | — | Already exists |
| `max_legs_in_session` | Max Legs in Session | — | Already exists |
| `sessions_with_1_leg` | L0 Wins (1-leg sessions) | — | Already exists, relabel |
| `l0_win_rate` | L0 Win Rate | sessions_won_at_L0 / total_sessions | **NEW**. The "entry quality" metric. Higher = less reliance on hedging. |

---

### Group 4: Capital & Costs

How efficiently capital is used, and what friction costs.

| Key | Label | Formula / Source | Notes |
|-----|-------|-----------------|-------|
| `capital_efficiency` | Capital Efficiency | net_profit / (peak_margin_used * holding_time_fraction) | **NEW**. Time-weighted: if peak margin is used 20% of the time, that's better than 80%. |
| `peak_margin_used` | Peak Margin Used | — | Keep |
| `peak_equity_usage_pct` | Peak Equity Used % | — | Keep |
| `worst_floating_pnl` | Worst Floating Loss | — | Keep |
| `fee` | Total Fees | — | Keep |
| `total_spread_cost` | Total Spread Cost | — | Keep (CFD only) |
| `total_swap_cost` | Total Swap Cost | — | Keep (CFD only) |
| `total_pips` | Total Pips | — | Keep (CFD only) |
| `avg_pips_per_trade` | Avg Pips / Trade | — | Keep (CFD only) |
| `cost_drag_pct` | Cost Drag % | (fees + spread + swap) / gross_profit * 100 | **NEW**. What fraction of gross profit is eaten by friction. |

---

### Hidden Section: Raw Trade Data (collapsed by default)

For debugging only. Not shown unless user expands.

| Metric | Reason it's demoted |
|--------|-------------------|
| Total Trades | Leg count, not session count |
| Winning/Losing Trades | ~50/50 by design |
| Longs/Shorts count/% | Always ~50/50 |
| Win Rate (trade-level) | Misleading |
| Largest Win/Loss (trade) | Bust leg always largest loss |
| Win/Loss streaks (trade) | Artifact of depth |
| Avg Win/Loss per trade | Wrong unit |
| Win/Loss Ratio (trade) | Wrong unit |
| Expectancy per trade | Wrong unit |
| Expected net per 100 trades | Wrong unit |
| Open trades / Open P&L | Only relevant during execution |
| Win rate longs / shorts | Always similar |

---

### Removed Entirely (from backend computation for martingale mode)

| Metric | Reason |
|--------|--------|
| Sharpe Ratio | Assumes normal returns. Bimodal martingale returns make this meaningless. |
| Smart Sharpe | Same |
| Sortino Ratio | Same (downside deviation of bimodal dist is not useful) |
| Smart Sortino | Same |
| Calmar Ratio | CAGR/MaxDD — MaxDD is always a bust, CAGR is dominated by bust timing. Not diagnostic. |
| Omega Ratio | Threshold-based, still assumes continuous distribution |
| Serenity Index | Composite of ulcer index + CVaR, both assume continuity |
| Kelly Criterion | Current impl uses trade-level W and R. Session-level Kelly is subsumed by geometric growth rate. |
| VaR 95% / 99% | Percentile of daily returns — busts are tail events beyond any VaR threshold. Survival probability replaces this. |
| CVaR 95% / 99% | Same — expected shortfall of daily returns misses the session-level bust structure. |

These are not computed when `is_martingale_mode` is true. They remain available for non-martingale strategies.

---

## Implementation

### Detection: `is_martingale_mode`

A backtest is martingale-mode if trades carry session metadata (`meta.session` is not None). This is already checked in `metrics.py:626`. Use the same condition to switch metric groups.

### Backend Changes (`qengine/services/metrics.py`)

1. **New function**: `_calculate_martingale_metrics(trades_list, daily_balance, starting_balance)` — computes all Tier 1-3 new metrics.

2. **Modify `trades()` function**:
   - When `has_sessions` is True: skip Sharpe/Sortino/Calmar/Omega/Serenity/Kelly/VaR/CVaR computation.
   - Add `is_martingale: True` flag to response.
   - Add new metrics from `_calculate_martingale_metrics()`.
   - Move trade-level stats into a `raw_trade_stats` sub-dict.

3. **New computations needed**:
   - `geometric_growth_rate`: requires tracking balance at each session start. Iterate sessions in order, compute `ln(1 + pnl/balance)` for each, take mean.
   - `level_transitions`: from trade metadata, for each session trace the level progression. Count transitions L→win and L→L+1.
   - `time_at_depth`: sum holding periods of trades grouped by their level metadata.
   - `capital_efficiency`: `net_profit / (peak_margin * fraction_of_time_in_position)`. Time in position from trade timestamps vs. total backtest duration.
   - `survival_*` and `half_life`: pure math from bust_rate, computed at the end.

### Frontend Changes (`Backtest.vue`)

1. **Conditional rendering**: check `metrics.is_martingale` to switch between martingale layout and generic layout.

2. **Replace metric key arrays**:
   - `perfKeys` → `sessionPerfKeys` (when martingale)
   - `riskKeys` → `survivalKeys` (when martingale)
   - `tradeKeys` → hidden, replaced by `structuralKeys`
   - New `capitalKeys` group
   - `hedgeKeys` → absorbed into session performance and structural groups

3. **New section headers**: "Session Performance", "Survival & Ruin", "Structural Diagnostics", "Capital & Costs"

4. **Collapsible "Raw Trade Data"**: accordion at bottom, closed by default.

5. **Visual additions**:
   - Depth distribution as a small horizontal bar chart inline
   - Level transition matrix as a mini heatmap or table
   - Survival curve as a sparkline (P(survive) vs N sessions)

### Files Changed

| File | Change |
|------|--------|
| `qengine/services/metrics.py` | Add `_calculate_martingale_metrics()`, modify `trades()` to branch on `has_sessions`, skip irrelevant ratio calculations |
| `frontend/src/views/Backtest.vue` | Conditional metric groups, new key arrays, collapsible raw trades section, new headers |
| `frontend/src/components/MetricTooltip.vue` | Add tooltip descriptions for all new metrics |

### Non-goals

- No changes to `PipelineStats` / Pipeline Intelligence tab — that system is already martingale-aware.
- No changes to live trading metrics — this is backtest-only for now.
- No changes to the equity curve chart or trade list table.
