# QEngine Repository Guide for AI Agents

## Overview
QEngine is a **multi-asset algorithmic trading platform** for forex, commodities, indices, and stocks. It provides a complete workflow for developing, backtesting, optimizing, and live-trading strategies through a modern web dashboard. Built on the Jesse framework foundation, QEngine extends it with realistic forex/CFD modeling, built-in broker integrations, and an LLM-powered strategy studio.

## Key Characteristics

### Core Platform
- **Self-contained**: No external live plugin needed -- broker drivers are built-in
- **jesse_rust integrates here** -- Rust indicator functions called from this codebase (external PyPI package, not renamed)
- **Vue 3 dashboard is embedded** -- Frontend builds to `qengine/static/` and serves at root `/`
- **Upstream jesse.trade APIs** -- Marketplace endpoints retained for strategy marketplace compatibility

### Features
- **Realistic forex backtesting**: Spread-based fees, overnight swap charges, market hours (Tokyo/London/NY), weekend closures, margin calls, pip-based calculations
- **Built-in broker drivers**: OANDA, IG Markets, Interactive Brokers (live + demo/paper)
- **ForexCFDExchange model**: Proper leverage, margin, contract size, and PnL modeling for CFDs
- **Monte Carlo simulation**: Trade shuffling + candle perturbation with statistical confidence analysis
- **LLM strategy generation**: Claude, GPT, Gemini integration for AI-assisted strategy creation
- **Issues/tickets system**: Built-in project tracking
- **Session persistence**: Backtest results, optimization trials, and live sessions stored in PostgreSQL

### Technology Stack
- **Python 3.10+** -- Primary language
- **FastAPI + Uvicorn** -- API framework and ASGI server
- **Peewee ORM** -- PostgreSQL database access
- **Redis** -- Pub/sub for real-time WebSocket relay, live session state
- **Vue 3 + Vite + Tailwind CSS** -- Dashboard frontend
- **NumPy + Pandas** -- Array operations and data handling
- **Optuna + Ray** -- Distributed hyperparameter optimization
- **jesse_rust** -- Rust-based technical indicators (175+)

## Development Workflow

### Making Changes
When implementing features or fixing bugs:

1. **Understand the scope** -- Does the change affect the backend, frontend, or both?
2. **Implement the code** in the appropriate module (controller, service, model, mode)
3. **Write/update tests** -- Maintain test coverage
4. **Run tests** to verify changes:
   ```bash
   python -m pytest tests/ -v
   ```
5. **Build frontend** if UI changed:
   ```bash
   cd frontend && npm run build
   ```
6. **Consider live trading** -- Does this change affect live order execution or broker drivers?
7. **Don't restart server** unless specifically asked

### Python Environment
```bash
source .venv/bin/activate
# Or use conda:
conda activate qengine
```

### Running QEngine Backend
```bash
# From the project root (where .env exists)
qengine run
# Server runs at http://localhost:9000

# Or directly:
python -m qengine
```

### Running Frontend Dev Server
```bash
cd frontend
npm run dev
# Dev server at http://localhost:3000, proxies API to :9000
```

### Running Tests
```bash
# All tests
python -m pytest tests/ -v

# Phase-specific tests
python -m pytest tests/test_phase*.py -v

# Broker integration tests
python -m pytest tests/test_broker*.py -v
```

## Important Notes

### Debugging
- **Use `jh.debug()` for all debugging output** -- Never use plain `print()` in production code
- Log format: `[timestamp] ==> Your message here`
- Use `self.log()` inside strategies for backtest/live logging
- Backtest logs are persisted and viewable in the dashboard

### API Routes
- **22 controllers** in `qengine/controllers/` -- follow existing patterns
- Default to POST endpoints unless specifically asked for GET
- Use FastAPI decorators and Pydantic models
- Return proper HTTP status codes and JSON responses
- Real-time updates go through Redis pub/sub --> WebSocket, not HTTP polling

### Code Style
- Don't write comments for functions unless asked
- Never try to install new packages without asking first
- Follow existing patterns and conventions
- Import at the top of the file
- Use `snake_case` for functions/variables, `PascalCase` for classes

### jesse_rust Integration
- When using Rust indicator functions, **assume they exist** -- don't add existence checks
- All 175+ indicators are in `qengine/indicators/` and call jesse_rust internally
- The package name is `jesse_rust` (not renamed -- it's an external PyPI dependency)

### Forex/CFD Considerations
When working on trading logic, be aware of:
- **Spreads**: Forex uses spread-based fees, not commission (except IBKR)
- **Leverage**: Default 30x for forex, 50x for IBKR -- affects margin calculations
- **Market hours**: Forex closes Friday 21:00 UTC, opens Sunday 21:00 UTC
- **Rollover**: Overnight swap charges at 5pm NY time
- **Pip sizes**: 0.0001 for standard pairs, 0.01 for JPY pairs
- **Contract sizes**: 100,000 for standard forex lot
- **Margin calls**: Simulated in backtest, real in live -- handle `InsufficientMargin` exceptions

### Live Trading Architecture
- Each live session runs in a **separate process** (via `multiprocessing`)
- State is published to **Redis** keys prefixed `qengine:live:`
- The frontend receives updates via **WebSocket** (Redis pub/sub relay)
- Broker drivers are in `qengine/live_drivers/` (OANDA, IG, IBKR)
- Account sync happens every 30s with exponential backoff on failure

## File Structure
```
qengine/                          # Main Python package
  __init__.py                     # FastAPI app, route registration, SPA serving
  cli.py                          # CLI commands (qengine run, install-live)
  config.py                       # Runtime configuration
  version.py                      # Version (2.0.0)
  controllers/                    # 22 FastAPI route handlers
    backtest_controller.py
    optimization_controller.py
    monte_carlo_controller.py
    live_controller.py
    broker_controller.py
    llm_controller.py
    settings_controller.py
    issue_controller.py
    websocket_controller.py
    ...
  models/                         # 24 Peewee ORM models
    Order.py, Position.py, ClosedTrade.py
    ForexCFDExchange.py, FuturesExchange.py, SpotExchange.py
    BacktestSession.py, OptimizationSession.py, MonteCarloSession.py
    LiveSession.py, Issue.py, Option.py, ExchangeApiKeys.py
    ...
  services/                       # 40+ business logic modules
    broker.py                     # Order routing and execution
    candle_service.py             # Candle data management (largest service)
    order_service.py              # Order lifecycle
    position_service.py           # Position tracking
    llm_engine.py                 # AI strategy generation
    redis.py                      # Pub/sub for real-time updates
    db.py                         # PostgreSQL connection
    metrics.py                    # Trading performance metrics
    lsp.py                        # Pyright language server
    ...
  modes/                          # Execution modes
    backtest_mode.py              # Minute-by-minute simulator
    live_mode.py            # Live/paper trading for forex/CFD
    optimize_mode/                # Optuna + Ray optimization
    monte_carlo_mode/             # Monte Carlo simulation
    import_candles_mode/          # Historical data import
  strategies/                     # Base Strategy class (1850+ lines)
    Strategy.py
  indicators/                     # 175+ technical indicators
  live_drivers/                   # Broker-specific drivers
    OANDA/, IG/, IBKR/
  store/                          # In-memory state management
  core/                           # Market hours, instruments
  enums/                          # Order types, sides, timeframes, brokers
  static/                         # Built Vue 3 frontend

frontend/                         # Vue 3 + Vite + Tailwind source
  src/views/                      # 12 page components
  src/components/                 # Shared UI components
  src/composables/                # WebSocket, API composables
  vite.config.js                  # Dev proxy to backend

strategies/                       # User strategies directory
  SurefireHedge/
  SurefireHedgeV2/

tests/                            # Test suite
storage/                          # Runtime data (logs, temp files)
docs/                             # Documentation
```

## Backtesting Engine

### How It Works (Realistic Simulation)
The backtest engine is a **minute-by-minute event-driven simulator** that models real market conditions:

1. **Candle-by-candle processing**: Iterates through every 1-minute candle in the date range
2. **Price effect simulation**: Checks pending orders against each candle's OHLC range (not just close price)
3. **Market hours enforcement**: Skips strategy execution when forex market is closed
4. **Overnight swaps**: Charges swap rates at daily rollover (5pm NY)
5. **Margin tracking**: Monitors margin usage and triggers margin calls when depleted
6. **Higher timeframe generation**: Builds 5m, 15m, 1h, 4h candles from 1m data on-the-fly
7. **Warmup candles**: Pre-loads 240 candles before start date for indicator initialization

### Fast Mode vs Step Mode
- **Step mode** (default): Full minute-by-minute simulation -- most accurate
- **Fast mode**: Batch processing for optimization speed (100x+ faster, slightly less accurate)

### Output
- Metrics (Sharpe, Calmar, Sortino, win rate, drawdown, etc.)
- Equity curve, floating PnL curve, margin usage curve
- All closed trades with entry/exit details
- Strategy execution logs
- Chart data (candles, orders, custom indicators)

## Live Trading Execution

### Architecture
```
Live Session Process (per session)
  |-- Broker Driver (OANDA/IG/IBKR API)
  |     |-- Price streaming (REST polling or WebSocket)
  |     |-- Order submission/cancellation
  |     |-- Account balance sync (every 30s)
  |
  |-- Candle Builder (ticks -> 1m -> higher TFs)
  |-- Strategy Executor (same _execute() as backtest)
  |-- Redis State Publisher (positions, orders, logs)
  |-- WebSocket Relay --> Dashboard
```

### Broker Drivers
| Broker | API Type | Connection |
|--------|----------|------------|
| OANDA | REST + Streaming | `api-fxtrade.oanda.com` / `api-fxpractice.oanda.com` |
| IG Markets | REST + Lightstreamer | `api.ig.com` / `demo-api.ig.com` |
| Interactive Brokers | TWS Socket | `localhost:7496` (live) / `localhost:7497` (paper) |

### Key Behaviors
- Orders route through the same `Broker` class as backtest -- strategies don't know the difference
- Account sync with exponential backoff (30s -> 60s -> 120s -> 300s max on failure)
- Graceful shutdown: cancel orders, close positions, compute session report
- Session state persisted to Redis (24h TTL) and PostgreSQL (permanent)

## Optimization & Monte Carlo

### Optimization
- **Optuna** suggests hyperparameters (TPE sampler)
- **Ray** distributes trials across CPU cores
- 70/30 training/testing split
- 7 objective functions: Sharpe, Calmar, Sortino, Omega, Serenity, Smart Sharpe, Smart Sortino
- Fitness = trade_quality_ratio * log_scaled_trade_count

### Monte Carlo
- **Trade shuffling**: Randomize trade order, reconstruct equity curves, calculate confidence intervals
- **Candle perturbation**: Add Gaussian noise or block-bootstrap resample prices, re-run backtest
- Both modes use Ray for parallel scenario execution
- Statistical output: percentiles, confidence intervals, p-values

## Database
- **PostgreSQL** via Peewee ORM
- DB name: `qengine_db`, user: `qengine_user`
- Key tables: `order`, `closedtrade`, `candle`, `backtestsession`, `optimizationsession`, `montecarlosession`, `livesession`, `issue`, `option`, `exchangeapikeys`
- Migrations run automatically on `qengine run`

## Environment Variables (.env)
```
POSTGRES_HOST, POSTGRES_NAME, POSTGRES_PORT, POSTGRES_USERNAME, POSTGRES_PASSWORD
REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD
APP_PORT (default 9000), APP_HOST (default 0.0.0.0)
PASSWORD (required -- dashboard login)
IS_DEV_ENV (optional -- skips PyPI update checks)
GEMINI_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY (optional -- LLM engine)
```

## Project Origin
QEngine v2.0.0 is built upon [Jesse](https://github.com/jesse-ai/jesse) (MIT License). The Jesse copyright is acknowledged. External dependencies `jesse_rust` and upstream `jesse.trade` API URLs are preserved for compatibility.
