## _section_guide
Performance metrics measure overall profitability and return characteristics of your strategy. Start with Net Profit % for the bottom line, then check Annual Return for time-adjusted performance. Win Rate and Profit Factor together reveal whether the strategy profits from many small wins or fewer large ones. A high win rate with low profit factor suggests small gains that may not survive costs; a low win rate with high profit factor means the strategy relies on letting winners run.

## gross_pnl
Total profit and loss from all closed trades before any fees, spread costs, or swap charges are deducted. This is the raw trading edge before friction.

## net_profit
Final profit after subtracting all costs — fees, spread, and swap. This is what actually hits your account. Compare with Gross PnL to see how much friction erodes your edge.

## net_profit_percentage
Net profit expressed as a percentage of your starting balance. A 10% return on $10,000 means $1,000 net profit. This normalizes results so you can compare across different account sizes.

## annual_return
Net profit annualized to a 12-month rate. If your backtest covers 6 months and returns 5%, the annual return is roughly 10%. Useful for comparing strategies tested over different time periods.

## win_rate
Percentage of closed trades that were profitable. A 60% win rate means 6 out of 10 trades made money. Win rate alone does not determine profitability — a 30% win rate can be highly profitable if winners are much larger than losers (see Profit Factor).

## profit_factor
Gross profit divided by gross loss. A value of 2.0 means you earned $2 for every $1 lost. Values above 1.0 are profitable; below 1.0 means the strategy loses money. Above 1.5 is generally considered good, above 2.0 is strong.

## expectancy
Average dollar amount you expect to make per trade. Calculated as (Win Rate x Avg Win) - (Loss Rate x Avg Loss). Positive expectancy means the strategy is profitable on average. Multiply by number of trades to estimate total profit.

## starting_balance
The initial account balance used for this backtest. All percentage-based metrics are calculated relative to this value.

## finishing_balance
Account balance at the end of the backtest. Finishing Balance minus Starting Balance equals Net Profit.
