# High-Level Logic

How QEngine's core systems work internally -- backtesting, optimization, Monte Carlo simulation, strategy execution, candle processing, and order management.

---

## Table of Contents
1. [Candle Data Pipeline](#1-candle-data-pipeline)
2. [Backtest Engine](#2-backtest-engine)
3. [Strategy Execution Cycle](#3-strategy-execution-cycle)
4. [Order Lifecycle](#4-order-lifecycle)
5. [Position Management](#5-position-management)
6. [Optimization Engine](#6-optimization-engine)
7. [Monte Carlo Simulation](#7-monte-carlo-simulation)
8. [Market Hours and Forex Logic](#8-market-hours-and-forex-logic)
9. [Metrics Calculation](#9-metrics-calculation)
10. [Live Trading](#10-live-trading)

---

## 1. Candle Data Pipeline

### Storage Format
Candles are stored as NumPy arrays with 6 columns:
```
[timestamp, open, close, high, low, volume]
```
Timestamps are in milliseconds (Unix epoch).

### Data Flow
1. **Import**: Historical 1-minute candles are fetched from broker APIs and stored in PostgreSQL (`candle` table)
2. **Load**: On backtest start, candles are loaded from DB for the requested date range
3. **Warmup**: An additional block of candles (default 240) is pre-loaded before the start date so indicators have enough data from candle #1
4. **Generation**: Higher timeframe candles (5m, 15m, 1h, 4h, etc.) are generated on-the-fly by aggregating consecutive 1-minute candles during simulation

### Candle Generation Logic
```
For a 15-minute candle at index i:
  Source = 1m candles from [i-14] to [i]
  Open   = first candle's open
  Close  = last candle's close
  High   = max of all highs
  Low    = min of all lows
  Volume = sum of all volumes
  Time   = first candle's timestamp
```

### Candle Pipelines
Custom `BaseCandlesPipeline` classes can transform 1m candles before they enter the simulator. Used by Monte Carlo candles mode to inject noise (Gaussian) or resample (Moving Block Bootstrap).

---

## 2. Backtest Engine

The backtest engine (`backtest_mode.py`) is a **minute-by-minute event-driven simulator**.

### Initialization Phase
```
1. Set config (trading mode = 'backtest')
2. Initialize routes (exchange, symbol, timeframe, strategy)
3. Reset the in-memory store
4. Validate routes
5. Initialize exchange state (balances, fees, leverage)
6. Initialize order and position state
7. Load candles from database
8. Inject warmup candles into the store
```

### Main Simulation Loop
For each 1-minute candle `i` in the date range:

```python
for i in range(total_minutes):
    # 1. Advance clock
    store.app.time = candle[i].timestamp + 60_000

    # 2. Check for overnight swap charges (forex rollover at 5pm NY)
    if is_rollover_time:
        charge_overnight_swap()

    # 3. For each symbol being traded:
    for symbol in symbols:
        # a. Get the 1m candle (possibly through a pipeline)
        candle = get_candle_from_pipeline(raw_candles[i])

        # b. Fix price gaps (jumped candles)
        candle = fix_jumped_candle(previous_candle, candle)

        # c. Add 1m candle to store
        candle_service.add_candle(candle, '1m')

        # d. Simulate price change effects on open orders
        simulate_price_change_effect(candle)

        # e. Generate higher timeframe candles when boundary is hit
        for timeframe in [5m, 15m, 1h, 4h, ...]:
            if (i + 1) % timeframe_minutes == 0:
                generated = aggregate_1m_candles(timeframe)
                add_candle(generated, timeframe)

    # 4. Execute strategies on their timeframe boundaries
    for route in routes:
        if market_is_open(route.symbol):
            if route.timeframe == '1m' or is_timeframe_boundary(i, route.timeframe):
                route.strategy._execute()
            update_active_orders(route)

    # 5. Execute any pending market orders
    execute_simulated_market_orders()

    # 6. Track daily portfolio balance (every 1440 minutes = 1 day)
    if i % 1440 == 0:
        save_daily_portfolio_balance()
```

### Price Change Effect Simulation
When a new 1m candle arrives, the simulator checks if any pending limit/stop orders should have triggered within that candle's range:
- **Stop orders**: Triggered if candle high >= stop price (buy) or candle low <= stop price (sell)
- **Limit orders**: Triggered if candle low <= limit price (buy) or candle high >= limit price (sell)
- **Liquidation**: If position margin drops below maintenance margin

### Fast Mode vs Step Mode
- **Step mode** (default): Full minute-by-minute simulation with all event handling
- **Fast mode** (`_skip_simulator`): Skips intermediate candle processing for optimization speed; trades execute at candle close prices only

### Output
The simulator returns:
- `metrics`: All performance metrics (Sharpe, win rate, PnL, drawdown, etc.)
- `trades`: List of all closed trades with entry/exit details
- `equity_curve`: Balance over time for charting
- `floating_pnl_curve`: Unrealized P&L over time
- `margin_usage_curve`: Margin utilization over time
- `hyperparameters`: Strategy hyperparameter values used
- `logs`: Execution logs (if debug mode enabled)

---

## 3. Strategy Execution Cycle

Each time a strategy's timeframe candle completes, `strategy._execute()` runs:

```
_execute()
  |-- Cache current price (ensures consistency within one cycle)
  |-- before()                          # User hook: pre-processing
  |-- _check()                          # Core decision engine
  |     |
  |     |-- If has entry orders and position is closed:
  |     |     should_cancel_entry()? --> cancel all orders, reset
  |     |
  |     |-- If position is open:
  |     |     update_position()         # User hook: adjust SL/TP
  |     |     detect_and_handle_modifications()
  |     |
  |     |-- simulate_market_order_execution()
  |     |
  |     |-- If position is closed and no entry orders:
  |     |     _reset()                  # Clear all order state
  |     |     should_long()? --> _execute_long() --> go_long() --> submit orders
  |     |     should_short()? --> _execute_short() --> go_short() --> submit orders
  |     |
  |-- after()                           # User hook: post-processing
  |-- Clear cached methods
  |-- Clear cached price
  |-- Increment index
```

### Entry Flow (go_long example)
```
should_long() returns True
  --> _execute_long()
      --> go_long()           # User sets: self.buy, self.stop_loss, self.take_profit
      --> Validate self.buy format
      --> _prepare_buy()      # Normalize to numpy array [(qty, price), ...]
      --> Validate SL and TP
      --> Execute filters()   # All must return True
      --> _submit_buy_orders()
          --> For each order point:
              price == current? --> buy_at_market()
              price > current?  --> start_profit_at() (stop order)
              price < current?  --> buy_at()          (limit order)
```

### Exit Flow
When a position closes (SL or TP hit):
```
Order executes --> Position qty changes
  --> _on_updated_position()
      --> Detect effect: opening / closing / increasing / reducing
      --> If closing:
          --> Get last closed trade
          --> Broadcast 'route-close-position'
          --> Cancel remaining orders
          --> on_close_position(order, closed_trade)
```

---

## 4. Order Lifecycle

### Order Types
| Type | Behavior |
|------|----------|
| `MARKET` | Execute immediately at current price |
| `LIMIT` | Execute when price reaches order price (better) |
| `STOP` | Execute when price reaches order price (worse) |
| `STOP_LIMIT` | Becomes a limit order when stop price is reached |

### Order Statuses
```
ACTIVE --> EXECUTED (filled)
       --> CANCELED (by strategy or system)
       --> PARTIALLY_FILLED --> EXECUTED
       --> QUEUED (live mode: waiting for valid price)
       --> REJECTED (live mode: broker rejected)
       --> LIQUIDATED (margin call)
```

### Backtest Order Execution
In backtest mode, orders execute against the 1m candle OHLC data:
- The simulator checks each active order against the current candle's high/low range
- If an order's trigger price falls within the candle range, it executes at the order price
- Market orders execute at the current close price
- Orders are processed in FIFO order

---

## 5. Position Management

### Position States
```
CLOSED (qty = 0)  <-->  OPEN (qty != 0)
                         |-- LONG (qty > 0)
                         |-- SHORT (qty < 0)
```

### P&L Calculation (Forex/CFD)
```
For LONG:  PnL = (current_price - entry_price) * abs(qty)
For SHORT: PnL = (entry_price - current_price) * abs(qty)
```

### Margin Model
```
Required Margin = abs(qty) * entry_price / leverage
Available Margin = wallet_balance - used_margin + unrealized_pnl
```

If available margin drops to zero, an `InsufficientMargin` exception stops the backtest (simulating a margin call).

### ForexCFDExchange
The `ForexCFDExchange` model handles forex-specific concerns:
- Spread-based fees (not commission)
- Leverage (default 30x for forex)
- Overnight swap charges at 5pm NY rollover
- Contract sizes (e.g., 100,000 for standard forex lot)
- Pip-based calculations

---

## 6. Optimization Engine

The optimizer (`optimize_mode/Optimize.py`) uses **Optuna + Ray** for distributed hyperparameter search.

### How It Works

```
1. SPLIT DATA
   Date range split: 70% training / 30% testing
   Both periods include warmup candles

2. DEFINE SEARCH SPACE
   Read strategy.hyperparameters()
   Each param has: name, type, min, max, default
   Types: int, float, categorical

3. RUN TRIALS (parallel via Ray)
   For each trial (default 200):
     a. Optuna suggests hyperparameter values (TPE sampler)
     b. Ray worker runs isolated backtest on TRAINING data
     c. Calculate fitness score
     d. Run isolated backtest on TESTING data
     e. Return (score, training_metrics, testing_metrics)

4. COLLECT RESULTS
   Sort by fitness score
   Return top N candidates (default 20)
```

### Fitness Function
The fitness score balances **trade quality** with **trade quantity**:

```python
# Quality: normalized risk-adjusted ratio
ratio = training_metrics[objective_function]  # e.g., Sharpe ratio
ratio_normalized = normalize(ratio, -0.5, 5)  # scale to [0, 1]

# Quantity: log-scaled trade count effect
total_effect_rate = log10(total_trades) / log10(optimal_total)
total_effect_rate = min(total_effect_rate, 1)

# Combined score
score = total_effect_rate * ratio_normalized
```

### Available Objective Functions
| Function | What It Measures |
|----------|-----------------|
| `sharpe` | Risk-adjusted return (default) |
| `calmar` | Return / max drawdown |
| `sortino` | Downside risk-adjusted return |
| `omega` | Probability-weighted gains vs losses |
| `serenity` | Composite risk metric |
| `smart sharpe` | Sharpe with autocorrelation penalty |
| `smart sortino` | Sortino with autocorrelation penalty |

### Requirements
- Minimum 5 trades in training data (otherwise score = 0.0001)
- Negative ratio = invalid configuration
- NaN score = invalid configuration

---

## 7. Monte Carlo Simulation

Monte Carlo analysis stress-tests a strategy by running it across many randomized scenarios. QEngine supports two modes:

### Trade Shuffling (monte_carlo_trades)
**Question answered**: "How robust is this strategy if the order of trades had been different?"

```
1. Take the list of closed trades from the original backtest
2. For each scenario (default: e.g., 100):
   a. Randomly shuffle the trade order
   b. Reconstruct the equity curve from shuffled trades
   c. Calculate metrics (return, max drawdown, Sharpe, etc.)
3. Aggregate results:
   - Percentiles (5th, 25th, 50th, 75th, 95th)
   - Confidence intervals (90%, 95%)
   - P-values for statistical significance
```

### Candle Perturbation (monte_carlo_candles)
**Question answered**: "Would this strategy still work if prices had been slightly different?"

```
1. Take the original candle data
2. For each scenario:
   a. Apply a candle pipeline to transform the data:
      - GaussianNoiseCandlesPipeline: adds random noise to OHLCV
      - MovingBlockBootstrapCandlesPipeline: resamples candle blocks
   b. Run a full backtest on the transformed candles
   c. Collect metrics and equity curve
3. Compare scenario results to the original
```

### Parallelism
Both modes use **Ray** to distribute scenarios across CPU cores. Each scenario is an independent backtest that can run in parallel.

### Statistical Output
- **Confidence intervals**: "With 95% confidence, max drawdown will be between X% and Y%"
- **P-values**: "Is the original result statistically significant vs random?"
- **Percentile distributions**: Understand best/worst/median case scenarios

---

## 8. Market Hours and Forex Logic

### Market Sessions
QEngine models real forex market hours:
```
Tokyo:    00:00 - 09:00 UTC
London:   07:00 - 16:00 UTC
New York: 12:00 - 21:00 UTC
Overlap:  12:00 - 16:00 UTC (London + NY)
```

### Weekend Handling
Forex markets close Friday 21:00 UTC and reopen Sunday 21:00 UTC. During backtesting:
- Strategies are **not executed** when market is closed
- Market open/close transitions are logged
- No orders are placed during closed hours

### Overnight Swap
At the daily rollover (5pm New York time):
- Positions held overnight are charged swap rates
- `ForexCFDExchange.charge_overnight_swap()` debits/credits the wallet balance
- Accessible via `self.swap_long` and `self.swap_short` in strategies

### Pip Calculations
```
Standard pairs (EUR-USD): 1 pip = 0.0001
JPY pairs (USD-JPY):      1 pip = 0.01
```
`self.pip_size`, `self.pips_to_price()`, `self.price_to_pips()` handle conversions.

---

## 9. Metrics Calculation

After backtest completion, the `metrics` service calculates:

| Metric | Description |
|--------|-------------|
| `total` | Total number of closed trades |
| `win_rate` | Percentage of winning trades |
| `net_profit` | Absolute profit/loss |
| `net_profit_percentage` | Return as % of starting balance |
| `max_drawdown` | Largest peak-to-trough decline |
| `sharpe_ratio` | Risk-adjusted return |
| `calmar_ratio` | Annual return / max drawdown |
| `sortino_ratio` | Return / downside deviation |
| `omega_ratio` | Gain probability / loss probability |
| `serenity_index` | Composite robustness metric |
| `smart_sharpe` | Sharpe with autocorrelation adjustment |
| `smart_sortino` | Sortino with autocorrelation adjustment |
| `average_win` | Average profit per winning trade |
| `average_loss` | Average loss per losing trade |
| `profit_factor` | Gross profit / gross loss |
| `expectancy` | Expected value per trade |
| `max_consecutive_wins` | Longest winning streak |
| `max_consecutive_losses` | Longest losing streak |
| `average_holding_period` | Mean trade duration |
| `kelly_criterion` | Optimal bet fraction |
| `total_open_trades` | Trades still open at backtest end |

---

## 10. Live Trading

### Architecture
```
Live Mode Process
  |-- Broker Driver (OANDA/IG/IBKR)
  |     |-- Price feed (REST polling or streaming)
  |     |-- Order execution (REST API)
  |     |-- Account state sync
  |
  |-- Candle Builder
  |     |-- Aggregates ticks/prices into 1m candles
  |     |-- Generates higher timeframe candles
  |
  |-- Strategy Executor
  |     |-- Same strategy._execute() as backtest
  |     |-- But orders route to real broker
  |
  |-- State Manager
  |     |-- Persists orders/trades to PostgreSQL
  |     |-- Publishes updates via Redis --> WebSocket
  |
  |-- Session Manager
  |     |-- Start/stop/restart sessions
  |     |-- Error recovery and reconnection
```

### Paper Trading
Paper trading uses the same live infrastructure but simulates order execution locally. Orders are "filled" at the current market price without actually being sent to the broker.

### Key Differences from Backtest
| Aspect | Backtest | Live |
|--------|----------|------|
| Price source | Historical DB | Real-time broker feed |
| Order execution | Simulated against candle OHLC | Sent to broker API |
| Timing | Instant (minutes per year) | Real-time (1 candle = 1 minute) |
| State | In-memory only | Persisted to PostgreSQL |
| Recovery | N/A | Reconnects on failure |
| Notifications | None | Discord/Telegram/email |

---

Previous: [ARCHITECTURE.md](./ARCHITECTURE.md) | Next: [STRATEGY.md](./STRATEGY.md)
