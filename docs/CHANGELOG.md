# Changelog

All notable changes to QEngine are documented here.

---

## [2.0.0] - 2026-03-22

### Complete Rebrand and Platform Overhaul

QEngine v2.0.0 is a major release that transforms the Jesse-based crypto trading framework into a multi-asset algorithmic trading platform focused on forex, commodities, and CFDs.

### Added

**Core Platform**
- Full package rename from `jesse` to `qengine` (540+ files, all imports, CLI, configs)
- New `qengine run` CLI command to start the application server
- FastAPI-based backend with 22 API controllers
- Uvicorn server with configurable host/port
- Automatic database migrations on startup
- Application settings persistence (LLM config, broker keys restored on startup)

**Forex/CFD Engine**
- `ForexCFDExchange` model with spread-based fees, leverage, and margin calculations
- Market hours system (Tokyo, London, New York sessions with overlap detection)
- Weekend market closure handling in backtesting
- Overnight swap/rollover charges at 5pm NY time
- Pip-based calculations (`pips_to_price()`, `price_to_pips()`, `lot_size_for_risk()`)
- Contract size and pip size per instrument
- Market session awareness (`self.session`, `self.market_is_open`, `self.minutes_to_close`)

**Broker Integrations**
- OANDA (live + demo) with REST streaming API
- IG Markets (live + demo) with REST streaming API
- Interactive Brokers (live + paper) with TWS socket API
- Broker credential management through dashboard Settings
- Built-in live trading drivers (no external plugin needed for forex/CFD)

**Dashboard (Vue 3)**
- Complete Vue 3 + Vite + Tailwind CSS frontend replacing the old Nuxt 3 UI
- Dashboard served at root `/` (previously at `/te/`)
- 12 views: Dashboard, Brokers, Tools, Strategies, Backtest, Optimization, Monte Carlo, Live Trade, Import Data, LLM Studio, Issues, Settings + Login
- Workspace tabs for Backtest, Optimization, Monte Carlo
- Session tabs for Live Trading
- Editor tabs for Strategies with Pyright LSP code intelligence
- Issues/Tickets system with CRUD, status filtering, and priority management
- Settings with Maintenance tab (clear issues, sessions, etc.)
- Real-time WebSocket updates for all operations

**LLM Engine**
- AI-powered strategy generation and refinement
- Support for Anthropic (Claude), OpenAI (GPT), and Google Gemini
- Auto-configuration from environment variables
- In-dashboard LLM Studio interface

**Optimization**
- Optuna-based hyperparameter optimization with Ray distributed computing
- 7 objective functions: Sharpe, Calmar, Sortino, Omega, Serenity, Smart Sharpe, Smart Sortino
- Training/testing split (70/30) with cross-validation
- Configurable trials count and best candidates tracking
- Results persistence in PostgreSQL

**Monte Carlo Simulation**
- Trade shuffling mode (randomize trade order, analyze equity curve distribution)
- Candle perturbation mode (add noise to price data, re-run backtest)
- Gaussian noise and Moving Block Bootstrap candle pipelines
- Statistical output: confidence intervals, percentiles, p-values
- Ray-powered parallel scenario execution

**Strategy Framework Enhancements**
- `on_close_position(order, closed_trade)` now receives the closed trade object
- `self.chart_label` for annotating chart markers
- `hedge_mode` flag for simultaneous long+short positions
- `self.liquidate()` method for immediate position closure
- `self.shared_vars` for cross-route data sharing
- `self.daily_balances` access
- Session-level trade grouping support
- Forex-specific properties: `spread`, `pip_size`, `swap_long`, `swap_short`, `contract_size`, `asset_class`

**Data and Analytics**
- Floating PnL curve tracking during backtests
- Margin usage curve tracking
- Backtest session persistence (results, charts, logs stored in DB)
- Strategy source code capture with backtest results
- Backtest execution logs (market events, position changes)
- Market open/close event logging

**Infrastructure**
- Redis pub/sub for real-time frontend communication
- WebSocket manager for connected client management
- Pyright LSP server for in-browser code intelligence
- Docker support (Dockerfile + multi-stage build)
- Database migration system with field-level operations

### Changed
- Database names: `jesse_db` -> `qengine_db`, `jesse_user` -> `qengine_user`
- All internal variable names updated from Jesse nomenclature
- `jesse_submitted` field renamed to `engine_submitted` in Order model
- Route paths: `/jesse-trade/*` -> `/marketplace/*`
- Service files: `jesse_trade.py` -> `upstream_api.py`
- PyPI version check URL updated to `qengine`
- All strategy imports: `from jesse.strategies import Strategy` -> `from qengine.strategies import Strategy`

### Preserved
- `jesse_rust` external dependency (Rust indicator library, unchanged)
- Upstream `jesse.trade` API URLs (marketplace compatibility)
- MIT License with Jesse copyright acknowledgment
- All 175+ technical indicators
- Core backtesting engine logic and strategy execution model

### Removed
- Old Nuxt 3 dashboard (16MB, 438 files in `static/_nuxt/`)
- Legacy static files (`404.html`, `200.html`, old favicons)
- Crypto-specific exchange configurations
- `tradeengine` and `jesse` egg-info directories

---

## [1.x] - Jesse Foundation

The original Jesse framework by jesse-ai provided the foundation:
- Event-driven backtesting engine
- Strategy base class with order management
- Technical indicators (via jesse_rust)
- Crypto exchange support
- Basic CLI interface

See [Jesse on GitHub](https://github.com/jesse-ai/jesse) for the original project history.
