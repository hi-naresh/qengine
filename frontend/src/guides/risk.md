## _section_guide
Risk metrics quantify how much pain your account endures to generate returns. Max Drawdown is the deepest peak-to-trough decline — it tells you the worst period you would have lived through. Sharpe, Sortino, and Calmar ratios measure return per unit of risk (higher is better). VaR and CVaR estimate tail losses — the worst-case scenarios. A strategy with great returns but terrible risk metrics may blow up in live trading. Always check drawdown and tail risk before trusting the profit numbers.

## max_drawdown
The largest peak-to-trough dollar decline in equity. If your account grew to $15,000 then dropped to $12,000 before recovering, max drawdown is $3,000. This is the worst loss you would have experienced.

## max_drawdown_percentage
Max drawdown expressed as a percentage of the peak equity. A 20% max drawdown means at worst your account was down 20% from its highest point. Most professional traders target max drawdown under 20-25%.

## sharpe_ratio
Return divided by volatility (standard deviation of returns), annualized. Measures reward per unit of total risk. Above 1.0 is acceptable, above 2.0 is very good, above 3.0 is exceptional. Negative means the strategy lost money.

## smart_sharpe
A corrected version of the Sharpe ratio that accounts for autocorrelation and skewness in returns. More accurate than standard Sharpe for strategies with serial correlation (like trend-following).

## sortino_ratio
Like Sharpe but only penalizes downside volatility (losses), not upside volatility (gains). Better for strategies with asymmetric returns. A strategy that has big winners and small losers will have a higher Sortino than Sharpe.

## smart_sortino
Corrected Sortino ratio that accounts for autocorrelation, similar to Smart Sharpe. More robust for strategies with clustered returns.

## calmar_ratio
Annual return divided by max drawdown. Measures how much return you get per unit of worst-case pain. A Calmar of 2.0 means you earn 2x your max drawdown annually. Higher is better; above 1.0 is generally acceptable.

## omega_ratio
Probability-weighted ratio of gains to losses relative to a threshold (usually 0). Unlike Sharpe, it considers the entire return distribution, not just mean and variance. Values above 1.0 indicate profitable strategies; higher is better.

## serenity_index
A composite risk-adjusted metric that penalizes drawdown duration and depth. Higher values indicate smoother, more consistent equity growth. Useful for comparing strategies that have similar returns but different drawdown profiles.

## kelly_criterion
The mathematically optimal fraction of your bankroll to risk per trade, based on win rate and win/loss ratio. For example, 0.15 means risking 15% per trade maximizes long-run growth. In practice, traders use half-Kelly or less to reduce volatility.

## var_95
Value at Risk at 95% confidence. The maximum expected loss on 95% of trading days. If VaR 95% is -$500, on 95% of days you lose less than $500. On the worst 5% of days, losses exceed this amount.

## var_99
Value at Risk at 99% confidence. The maximum expected loss on 99% of trading days. More conservative than VaR 95% — only 1% of days are expected to be worse than this.

## cvar_95
Conditional Value at Risk (Expected Shortfall) at 95%. The average loss in the worst 5% of days. Unlike VaR which is a threshold, CVaR tells you how bad the tail actually is. Always worse than VaR.

## cvar_99
Conditional Value at Risk at 99%. The average loss in the worst 1% of days. This captures extreme tail risk — the kind of losses that can blow accounts.

## worst_floating_pnl
The worst unrealized (floating) loss experienced at any point during the backtest, across all open positions. This can be much worse than realized max drawdown if trades were held through deep adverse moves before recovering.

## peak_margin_used
The highest amount of margin (collateral) used at any single point. Important for leveraged accounts — if peak margin approaches your balance, you were close to a margin call.

## peak_equity_usage_pct
Peak margin used as a percentage of account equity. Values above 80-90% indicate extreme leverage usage and high risk of margin closeout.

## margin_closeouts
Number of times the account hit a margin closeout (forced liquidation). Any value above 0 means the strategy blew through margin requirements. This is a critical failure indicator.

## account_blown
Whether the account balance went to zero or below. A boolean flag — if true, the strategy is not viable at this position size.
