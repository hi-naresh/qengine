## _section_guide
Monte Carlo simulation is a statistical technique that generates thousands of randomized "what-if" scenarios from your backtest results. Instead of relying on a single historical outcome, it reshuffles or perturbs your trades and candles to reveal how sensitive your strategy is to the order and timing of market events.

For grid and surefire-hedge strategies, this is especially important because they are highly path-dependent: the sequence of wins, losses, and bust cascades dramatically changes the equity curve. A single backtest may look profitable, but Monte Carlo reveals whether that result was lucky sequencing or genuinely robust. It answers: "If the same trades happened in a different order, would I still survive?"

What to look for:
- P(Ruin) — probability of total account wipeout across all scenarios. Should be 0%.
- P(Bust) — probability of hitting a severe drawdown threshold. Lower is safer.
- Worst 5% vs Median — how bad things get in tail scenarios. Narrow gap = robust strategy.
- Equity curve fan — tight bundle = consistent outcomes; wide spread = high variance / path-dependent risk.

## p_ruin
Probability of Ruin — the fraction of simulated scenarios where the account balance dropped to zero or below. Even 0.01% (1 in 10,000 scenarios) means ruin is structurally possible. For any strategy you plan to trade live, this must be 0.00%.

## p_bust
Probability of Bust — the fraction of scenarios where max drawdown exceeded a threshold (typically 50-70% of peak equity). Unlike P(Ruin) which is total wipeout, P(Bust) catches severe but survivable drawdowns. Below 1% is acceptable; below 0.1% is strong.

## avg_max_consecutive_losses
Average of the maximum consecutive losing streaks across all simulated scenarios. This tells you the typical worst-case losing streak you should prepare for. Multiply by your average loss to estimate the drawdown from sequential losses alone.

## p95_max_consecutive_losses
The 95th percentile of maximum consecutive losing streaks. In 95% of scenarios, the worst losing streak was this long or shorter. This is a more conservative planning number than the average — size your positions to survive this many consecutive losses.

## total_return
Total percentage return of the strategy. In Monte Carlo context, shown as Original (from actual backtest), Worst 5% (5th percentile across scenarios), Median (50th percentile), and Best 5% (95th percentile). The gap between Worst 5% and Best 5% reveals how much returns depend on trade ordering.

## net_profit_percentage
Net profit as a percentage of starting balance, shown across Monte Carlo percentiles. Compare the Worst 5% with the Original to see downside sensitivity.

## max_drawdown
Maximum peak-to-trough equity decline, shown across Monte Carlo percentiles. The Worst 5% max drawdown is your planning number — expect drawdowns at least this bad under adverse sequencing.

## sharpe_ratio
Risk-adjusted return metric shown across MC percentiles. A median Sharpe well above 1.0 with a Worst 5% still positive suggests robust risk-adjusted performance regardless of trade ordering.

## calmar_ratio
Annual return divided by max drawdown, shown across MC percentiles. Sensitive to drawdown variation — the Worst 5% Calmar dropping sharply indicates the strategy's returns don't compensate for tail drawdowns.

## sortino_ratio
Like Sharpe but only penalizes downside volatility. Shown across MC percentiles. Less sensitive to beneficial variance (big winners) than Sharpe.

## win_rate
Percentage of winning trades, shown across MC percentiles. For trade-shuffle Monte Carlo, this stays constant (same trades, different order). For candle-simulation MC, it varies because different price paths produce different trade outcomes.

## total
Total number of trades across MC scenarios. Constant for trade-shuffle (same trades reshuffled), variable for candle-simulation (different price paths generate different trade counts).

## annual_return
Annualized return shown across MC percentiles. Compare Worst 5% with Original to understand the range of annual outcomes under different trade sequencing.
