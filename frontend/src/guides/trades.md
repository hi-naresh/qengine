## _section_guide
Trade statistics break down the composition and characteristics of your trades. Total counts and win/loss splits reveal how active the strategy is and its hit rate. Long vs short percentages show directional bias. Streaks indicate clustering — long losing streaks stress drawdown recovery, while long winning streaks may indicate trend-following effectiveness. Average win vs average loss (and their ratio) determine whether the strategy profits from size or frequency.

## total
Total number of trades opened during the backtest period, including both completed and still-open trades.

## total_completed_trades
Number of trades that were both opened and closed during the backtest. This excludes any trades still open at the end of the test.

## total_winning_trades
Number of completed trades that ended with a positive P&L (profit). Used to calculate win rate.

## total_losing_trades
Number of completed trades that ended with a negative P&L (loss). Includes break-even trades that lost to spread/fees.

## total_open_trades
Number of trades still open when the backtest ended. These trades have unrealized P&L that is not included in the net profit calculation.

## longs_count
Number of long (buy) trades taken. Compare with shorts to understand directional bias.

## shorts_count
Number of short (sell) trades taken. Compare with longs to understand directional bias.

## longs_percentage
Percentage of total trades that were long positions. A value near 50% suggests the strategy trades both directions equally.

## shorts_percentage
Percentage of total trades that were short positions. A value near 50% suggests the strategy trades both directions equally.

## largest_winning_trade
Dollar amount of the single most profitable trade. If this is much larger than the average win, profits may be concentrated in a few outlier trades — which is risky because those outliers may not repeat.

## largest_losing_trade
Dollar amount of the single worst trade. Compare with average loss to check for tail risk. A largest loss much bigger than the average suggests occasional blow-up trades.

## winning_streak
Maximum number of consecutive winning trades. Long winning streaks can indicate strong trending conditions or a high-probability setup.

## losing_streak
Maximum number of consecutive losing trades. Important for risk management — your account must survive this many losses in a row. Multiply by average loss to estimate worst-case sequential drawdown.

## average_win
Average dollar profit per winning trade. Compare with average loss to understand the reward-to-risk profile.

## average_loss
Average dollar loss per losing trade. Compare with average win — ideally average win should be larger than average loss, or win rate should compensate.

## average_win_loss
Ratio of average win to average loss. Values above 1.0 mean winners are larger than losers on average. Combined with win rate, this determines expectancy.

## fee
Total fees and commissions paid across all trades. High fees can erode a marginally profitable strategy.

## open_pl
Unrealized profit or loss from trades still open at the end of the backtest. Not included in net profit.
