# Architecture

Technical architecture of the QEngine platform.

---

## Tech Stack

| Layer          | Technology                                   |
|----------------|----------------------------------------------|
| Backend        | Python 3.10+, FastAPI, Uvicorn               |
| Database       | PostgreSQL (Peewee ORM)                      |
| Cache/PubSub   | Redis (real-time WebSocket relay)             |
| Frontend       | Vue 3 + Vite + Tailwind CSS                  |
| Indicators     | `jesse_rust` (Rust-based, via PyPI)           |
| Optimization   | Optuna + Ray (distributed multi-core)         |
| Monte Carlo    | Ray (parallel scenario simulation)            |
| LLM Engine     | Anthropic / OpenAI / Google Gemini            |
| Code Editor    | Pyright LSP (in-browser strategy editing)     |
| Live Trading   | Built-in broker drivers (OANDA, IG, IBKR)     |

---

## Directory Structure

```
jesse-master/
|-- qengine/                    # Main Python package
|   |-- __init__.py             # FastAPI app, route registration, SPA serving
|   |-- cli.py                  # Click CLI (`qengine run`, `qengine install-live`)
|   |-- config.py               # Runtime configuration (exchanges, optimization, data)
|   |-- version.py              # Version string (2.0.0)
|   |-- constants.py            # Timeframe mappings, constants
|   |-- exceptions.py           # Custom exception classes
|   |-- helpers.py              # Utility functions (timestamps, formatting, validation)
|   |
|   |-- controllers/            # FastAPI route handlers (22 controllers)
|   |   |-- backtest_controller.py
|   |   |-- optimization_controller.py
|   |   |-- monte_carlo_controller.py
|   |   |-- live_controller.py
|   |   |-- strategy_controller.py
|   |   |-- broker_controller.py
|   |   |-- llm_controller.py
|   |   |-- issue_controller.py
|   |   |-- settings_controller.py
|   |   |-- websocket_controller.py
|   |   |-- ... (12 more)
|   |
|   |-- models/                 # Peewee ORM models (24 models)
|   |   |-- Order.py            # Trade orders
|   |   |-- Position.py         # Open positions (in-memory)
|   |   |-- ClosedTrade.py      # Completed trades
|   |   |-- Trade.py            # Trade tracking
|   |   |-- Candle.py           # OHLCV candle data
|   |   |-- Exchange.py         # Exchange state
|   |   |-- ForexCFDExchange.py # Forex/CFD-specific exchange
|   |   |-- BacktestSession.py  # Backtest results persistence
|   |   |-- OptimizationSession.py
|   |   |-- MonteCarloSession.py
|   |   |-- LiveSession.py      # Live trading sessions
|   |   |-- Issue.py            # Issue/ticket tracking
|   |   |-- Option.py           # Key-value settings storage
|   |   |-- ExchangeApiKeys.py  # Broker credentials
|   |   |-- ... (10 more)
|   |
|   |-- services/               # Business logic layer (40+ services)
|   |   |-- broker.py           # Order routing and execution
|   |   |-- candle_service.py   # Candle data management
|   |   |-- order_service.py    # Order lifecycle management
|   |   |-- position_service.py # Position tracking
|   |   |-- exchange_service.py # Exchange state management
|   |   |-- db.py               # PostgreSQL connection management
|   |   |-- redis.py            # Redis pub/sub for real-time updates
|   |   |-- web.py              # FastAPI app creation, CORS, middleware
|   |   |-- ws_manager.py       # WebSocket connection manager
|   |   |-- llm_engine.py       # AI strategy generation (Claude/GPT/Gemini)
|   |   |-- lsp.py              # Pyright language server management
|   |   |-- metrics.py          # Trading performance metrics
|   |   |-- auth.py             # JWT authentication
|   |   |-- migrator.py         # Database schema migrations
|   |   |-- safety_sizing.py    # Position sizing safety checks
|   |   |-- scenario_generator.py # Monte Carlo scenario generation
|   |   |-- ... (20+ more)
|   |
|   |-- modes/                  # Execution modes
|   |   |-- backtest_mode.py    # Backtest simulation engine
|   |   |-- optimize_mode/      # Hyperparameter optimization (Optuna + Ray)
|   |   |   |-- Optimize.py     # Optimizer class
|   |   |   |-- fitness.py      # Fitness function (Sharpe, Calmar, etc.)
|   |   |-- monte_carlo_mode/   # Monte Carlo simulation
|   |   |   |-- MonteCarloRunner.py
|   |   |-- import_candles_mode/ # Historical data import
|   |   |-- forex_live_mode.py  # Live/paper trading for forex/CFD
|   |   |-- data_provider.py    # Data feed management
|   |
|   |-- strategies/             # Strategy framework
|   |   |-- Strategy.py         # Base Strategy class (1850+ lines)
|   |
|   |-- indicators/             # 175+ technical indicators
|   |   |-- rsi.py, macd.py, bollinger_bands.py, atr.py, ...
|   |
|   |-- store/                  # In-memory state management
|   |-- routes/                 # Route/symbol configuration
|   |-- core/                   # Core modules (market hours, instruments)
|   |-- live_drivers/           # Broker-specific live trading drivers
|   |-- candle_pipelines/       # Custom candle transformation pipelines
|   |-- research/               # Research utilities (isolated backtests)
|   |-- repositories/           # Data access layer
|   |-- enums/                  # Enumerations (order types, sides, timeframes)
|   |-- lsp/                    # Language server protocol files
|   |-- static/                 # Built frontend (served at /)
|
|-- frontend/                   # Vue 3 + Vite dashboard source
|   |-- src/
|   |   |-- views/              # 12 page components
|   |   |-- components/         # Shared UI components
|   |   |-- composables/        # Vue composables (WebSocket, API)
|   |   |-- router.js           # Hash-based routing
|   |-- vite.config.js
|   |-- package.json
|
|-- strategies/                 # User strategies directory
|   |-- SurefireHedge/
|   |-- SurefireHedgeV2/
|
|-- storage/                    # Runtime data (logs, temp files)
|-- tests/                      # Test suite
|-- setup.py                    # Package configuration
|-- requirements.txt            # Python dependencies
|-- Dockerfile                  # Container build
|-- .env                        # Environment configuration
```

---

## Data Flow

### Backtest Flow
```
Dashboard (Vue 3)
  |-- POST /backtest (routes, dates, config)
  |     |
  |     v
  BacktestController
  |     |
  |     v
  backtest_mode.run()
  |     |-- Load candles from DB (candle_service)
  |     |-- Initialize store (exchanges, positions, orders)
  |     |-- Run simulator (candle-by-candle)
  |     |     |-- For each 1m candle:
  |     |     |     |-- Update exchange prices
  |     |     |     |-- Check/execute pending orders
  |     |     |     |-- Execute strategy._check()
  |     |     |     |-- strategy.before() -> should_long/should_short -> go_long/go_short -> after()
  |     |     |-- Calculate metrics
  |     |
  |     v
  Results --> Redis pub/sub --> WebSocket --> Dashboard
  Results --> PostgreSQL (BacktestSession)
```

### Live Trading Flow
```
Dashboard
  |-- POST /live/start (routes, config, broker)
  |     |
  |     v
  LiveController --> forex_live_mode.run()
  |     |
  |     |-- Connect to broker API (OANDA/IG/IBKR)
  |     |-- Subscribe to price feeds
  |     |-- For each candle update:
  |     |     |-- Update store prices
  |     |     |-- Execute strategy._check()
  |     |     |-- Route orders through broker driver
  |     |
  |     v
  Real-time updates --> Redis --> WebSocket --> Dashboard
```

### Optimization Flow
```
Dashboard
  |-- POST /optimization (routes, dates, trials, objective)
  |     |
  |     v
  OptimizationController --> Optimizer (Ray + Optuna)
  |     |
  |     |-- Split data: 70% training / 30% testing
  |     |-- Ray distributes trials across CPU cores
  |     |-- Each trial:
  |     |     |-- Optuna suggests hyperparameters
  |     |     |-- Run isolated backtest with those params
  |     |     |-- Calculate fitness score
  |     |-- Collect best candidates
  |     |
  |     v
  Results --> Redis --> WebSocket --> Dashboard
```

---

## Key Design Patterns

### Store Pattern
The `store` is a singleton in-memory state container that holds:
- **Candles**: Price data for all symbols/timeframes
- **Orders**: Active and historical orders
- **Positions**: Current position state per exchange/symbol
- **Exchanges**: Exchange state (balance, fees, leverage)
- **Logs**: Execution logs
- **App state**: Session ID, time, trading mode

### Broker Abstraction
The `Broker` class provides a unified interface for order operations:
- `buy_at_market()`, `sell_at_market()`
- `buy_at()`, `sell_at()` (limit orders)
- `start_profit_at()` (stop orders)
- `reduce_position_at()` (exit orders)
- `cancel_order()`, `cancel_all_orders()`

In backtest mode, orders execute against historical data. In live mode, they route to the real broker API.

### Real-time Communication
```
Backend Event --> Redis PUBLISH --> WebSocket Manager --> Connected Clients
```
Redis pub/sub decouples the computation processes (backtest, optimization) from the WebSocket server, enabling multi-process architectures.

### Strategy Lifecycle
```
__init__() --> before() --> should_long()/should_short() --> go_long()/go_short()
    |              |                                              |
    |              v                                              v
    |          after()                                    Orders submitted
    |              |                                              |
    |              v                                              v
    |         [next candle]                              on_open_position()
    |              |                                              |
    |              v                                              v
    |      update_position()                    on_close_position(order, trade)
    |              |
    v              v
terminate()   [repeat]
```

---

## Database Schema (Key Tables)

| Table | Purpose |
|-------|---------|
| `order` | All orders (active, executed, canceled) |
| `closedtrade` | Completed trade records |
| `candle` | Historical OHLCV data |
| `exchangeapikeys` | Encrypted broker credentials |
| `option` | App settings (JSON key-value) |
| `backtestsession` | Backtest results and metrics |
| `optimizationsession` | Optimization trial results |
| `montecarlosession` | Monte Carlo simulation results |
| `livesession` | Live trading session state |
| `issue` | Issue/ticket tracking |
| `opentab` | Dashboard workspace tabs |
| `log` | System and strategy logs |

---

## Security

- Dashboard login protected by `PASSWORD` env variable
- JWT tokens for API authentication
- Broker API keys stored encrypted in PostgreSQL
- CORS configured via FastAPI middleware
- No external telemetry or tracking

---

Previous: [RUN.md](./RUN.md) | Next: [HIGH-LEVEL-LOGIC.md](./HIGH-LEVEL-LOGIC.md)
