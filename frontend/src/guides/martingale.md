## _section_guide
Martingale metrics use the **session** as the atomic unit — not the individual trade. A session is one full cycle from initial entry through resolution (TP hit or bust). Standard trade-level metrics (Sharpe, win rate per trade, etc.) are misleading for martingale systems because individual legs are structurally required, not independent bets.

## session_profit_factor
Ratio of total winning session PnL to total losing session PnL. The true profit factor for martingale systems. A value above 1.0 means winning sessions outweigh losing sessions in dollar terms.

## median_session_pnl
The middle value when all session PnLs are sorted. More robust than mean EV because a single bust can heavily skew the average. If median is positive but mean is negative, busts are dominating arithmetic returns.

## bust_rate
Fraction of sessions that ended in bust (max levels, margin call, liquidation). THE most important probability for martingale systems. Even 1% bust rate compounds dangerously over hundreds of sessions.

## bust_count
Total number of sessions that ended in bust during the backtest.

## wins_to_recover
How many winning sessions it takes to recover from one average bust. Calculated as |avg_bust_loss| / avg_session_win. If WTR = 78, one bust erases 78 winning sessions.

## geometric_growth_rate
The average of ln(1 + session_return) across all sessions. If negative, the system is mathematically guaranteed to approach zero balance given enough sessions — even if arithmetic EV is positive. Positive = wealth compounds. Negative = wealth erodes.

## survival_100
Probability of completing 100 sessions without a single bust. At 1% bust rate: 36.6%. At 2%: 13.3%.

## survival_500
Probability of completing 500 sessions without a single bust. At 1% bust rate: 0.66%. Shows the long-run fragility of even low bust rates.

## survival_half_life
Number of sessions at which there is a 50% chance of having experienced at least one bust. At 1% bust rate: ~69 sessions. Infinite if no busts observed.

## avg_bust_loss
Average dollar loss across all bust sessions. Combined with bust_rate and avg_session_win, fully characterizes the risk/reward structure.

## bust_severity_std
Standard deviation of bust losses. Low = busts are predictable in size. High = some busts are far worse than others (possible margin cascade or liquidity issues).

## level_transitions
Markov chain view of the system. For each level: how many sessions entered, won, or escalated. Shows exactly where sessions go wrong.

## ev_by_depth
Expected value decomposition by session depth. Shows which max-levels generate profit vs. destroy it. Healthy system: L0-L2 contribute most profit.

## time_at_depth
Total time spent at each hedge level across all sessions. Deep levels tie up more capital for longer.

## l0_win_rate
Fraction of all sessions that won at level 0 (no hedging needed). Higher is better — measures entry quality.

## cost_drag_pct
Total costs (fees + spread + swap) as a percentage of gross profit. Shows how much friction eats into returns.
