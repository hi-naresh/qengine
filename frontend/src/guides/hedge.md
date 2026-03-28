## _section_guide
Hedge session metrics are specific to grid/surefire-hedge strategies that operate in discrete "sessions" — each session starts with an initial trade and may add hedge legs at progressively larger sizes until either a take-profit is hit (session win) or the maximum level is reached (session loss/bust). Session win rate and EV per session determine long-run profitability. Average and max legs reveal how deep the grid typically goes — more legs means more capital at risk. Consecutive session losses are critical because each loss is typically much larger than each win.

## total_sessions
Total number of hedge sessions completed during the backtest. Each session is one full cycle from initial entry through resolution (TP hit or bust).

## session_win_rate
Percentage of sessions that ended profitably (TP hit). A grid/hedge strategy typically has a very high session win rate (90%+) but large losses when sessions fail.

## avg_session_win
Average dollar profit from winning sessions. This is typically small and consistent due to fixed TP targets.

## avg_session_loss
Average dollar loss from losing sessions (busts). This is typically much larger than the average win — often 10-100x larger depending on the number of grid levels.

## ev_per_session
Expected value (average P&L) per session. Calculated as (Win Rate x Avg Win) - (Loss Rate x Avg Loss). Positive EV means the strategy is profitable over many sessions. Even a tiny negative EV compounds into guaranteed long-run losses.

## avg_legs_per_session
Average number of hedge levels reached per session. Lower is better — it means most sessions resolve early without deep grid exposure. A value of 1.5 means most sessions close at level 0 or 1.

## max_legs_in_session
The deepest grid level reached in any single session. This is your worst-case capital exposure. Higher max legs means more margin was committed simultaneously.

## sessions_with_1_leg
Number (or percentage) of sessions that resolved with only the initial trade — no hedging needed. Higher is better; it means the initial entry direction was correct most of the time.

## max_consecutive_session_wins
Longest streak of consecutive winning sessions. In grid strategies this is typically very long (50-200+) due to the high base win rate.

## max_consecutive_session_losses
Longest streak of consecutive losing sessions. This is the most dangerous metric for grid strategies — consecutive busts can wipe out hundreds of winning sessions. Even 2-3 consecutive busts can be account-ending.
