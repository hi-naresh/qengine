# Changelog

All notable changes to QEngine (forked from [Jesse](https://github.com/jesse-ai/jesse)) are documented here.

---

## [2.1.0] - 2026-03-26

### CFD Ticket System (True Hedging Engine)

A complete sub-position (ticket) system enabling MT4/MT5-style independent trade management within a single position.

**CFDTicket Class** (`models/Position.py`)
- New `CFDTicket` class with fields: `id`, `type` (long/short), `qty`, `entry_price`, `opened_at`, `exchange_trade_id`
- `pnl(price)` — per-ticket profit calculation
- `to_dict()` — serialization for Redis/API publishing

**Position Ticket Management** (`models/Position.py`)
- `open_ticket(type, qty, entry_price, opened_at)` — create independent sub-position
- `close_ticket(ticket_id, exit_price)` — close specific ticket, returns `{ticket, pnl}`
- `close_all_tickets(exit_price)` — close all tickets, returns list of `{ticket, pnl}`
- `get_ticket(ticket_id)` — retrieve ticket by ID
- `tickets` property — returns copy of ticket list
- `ticket_count` property — number of open tickets
- `_sync_from_tickets()` — recalculate net qty and weighted avg entry_price from all tickets
- `gross_exposure` property — sum of all tickets' absolute qty (for margin, not just net)
- `is_cfd_mode` property — auto-detected from exchange type (`cfd`), NOT a strategy flag

**Modified Position Properties for CFD**
- `pnl` — CFD mode: sums per-ticket PnL instead of single position calc
- `is_open` — CFD mode: True if any tickets exist
- `is_close` — CFD mode: True if no tickets
- `margin_used` — CFD mode: uses `gross_exposure * current_price * margin_rate` (not net qty)
- `liquidation_price` — added `'cfd'` to mode check
- `to_dict()` — includes serialized tickets array and `pip_pnl` for CFD
- `leverage` — added CFD branch returning `exchange.default_leverage`
- `mode` — returns `'cfd'` for CFD exchange type (was `'forex_cfd'`)

**Strategy API for CFD** (`strategies/Strategy.py`)
- `close_all_tickets(exit_price, meta)` — close all tickets with optional metadata dict
- `close_ticket(ticket_id, exit_price, meta)` — close specific ticket by ID
- `on_ticket_opened(order)` — callback when new ticket added while others exist
- `on_ticket_closed(order)` — callback when ticket closed but others remain
- Per-ticket closed trade recording via `closed_trade_service.record_ticket_close()`
- `_check()` now allows entry while position is open in CFD mode
- `_on_updated_position()` — rewritten effect detection for CFD: `ticket_opened`, `ticket_closed`, `opening_position`, `closing_position`
- `_terminate()` — added CFD section: calls `close_all_tickets()` on backtest end

**Order Model Changes** (`models/Order.py`)
- New field: `ticket_id` — links order to specific CFDTicket
- New field: `vars` (JSONField) — exchange-specific metadata (e.g., OANDA trade_id)
- New field: `fee` (FloatField) — per-order fee tracking

**Position Service** (`services/position_service.py`)
- New `_handle_cfd_order()` function — manages CFD order execution with independent tickets
  - Reduce-only: closes specific ticket by `ticket_id` or all tickets
  - Non-reduce-only: opens new ticket, links OANDA trade_id from `order.vars['trade_id']`
  - Records per-ticket PnL via `closed_trade_service.record_ticket_close()`
- `on_executed_order()` — new CFD branch routes to `_handle_cfd_order()` instead of netting logic

**Closed Trade Service** (`services/closed_trade_service.py`)
- New `record_ticket_close()` — creates individual ClosedTrade per CFD ticket with `meta: {cfd_ticket: True, ticket_id}`

**Order Service** (`services/order_service.py`)
- CFD mode skip: doesn't add to single-trade tracking for non-reduce_only CFD orders
- Fee calculation: `fee_rate * notional_value` at execution time

**Exchange Type Unification**
- Unified exchange type `cfd` replacing `forex_cfd` and `multi_asset`
- All brokers (OANDA, IG Markets, IBKR) use `type: 'cfd'` in `info.py`
- `ForexCFDExchange` handles all CFD brokers with single code path
- Backward compatibility maintained (old type names still accepted in validation)

### Spread Cost Model (Rewritten)

**Order Execution** (`services/order_service.py`)
- Spread shifts entry fill price: buy += spread, sell -= spread (not separate deduction)
- Slippage applied after spread, also shifts against trader
- `charge_fee()` skipped entirely for CFD exchanges — spread replaces it
- Each adjustment logged with original and adjusted prices

**ForexCFDExchange Cost Methods** (`models/ForexCFDExchange.py`)
- `set_spread(symbol, spread)` — configure spread in price units per symbol
- `get_spread(symbol)` — returns spread with optional randomness (backtest only)
- `get_slippage(symbol)` — returns slippage in price units with randomness factor
- `charge_spread(symbol, qty)` — deducts spread + optional per-lot commission from balance
- `set_swap_rates(symbol, swap_long, swap_short)` — per-symbol overnight rates
- `charge_overnight_swap(symbol, qty, position_type)` — daily swap charge (annualized / 365)
- Backtest cost settings dict: `spread_pips`, `spread_randomness`, `slippage_pips`, `slippage_randomness`, `commission_per_lot`, `swap_enabled`, `stop_out_level`
- `_total_spread_cost` accumulator for total trading costs
- `_overnight_charges` accumulator for swap costs

**Exchange Service** (`services/exchange_service.py`)
- `_apply_backtest_cost_settings()` — loads cost model from DB settings, applies per-symbol spread

### OANDA Live Trading

**OandaDriver** (`live_drivers/OANDA/OandaDriver.py` — 426 lines)
- `_submit_market_order()` — POST to `/orders`, extracts `trade_id` from `orderFillTransaction.tradeOpened.tradeID`
- Returns `{order_id, fill_price, trade_id}` dict for full trade linkage
- `set_trade_tp_sl(trade_id, take_profit, stop_loss)` — PUT to `/trades/{id}/orders` with GTC TP/SL
- `cancel_trade_tp_sl(trade_id)` — fetches dependent order IDs, cancels each individually
- `get_open_trades()` — returns individual open trades from `/openTrades` with TP/SL details
- `close_trade(trade_id, units)` — closes individual trade via `/trades/{id}/close`
- Integer units: `int(round(abs(qty)))` required for standard FX pairs
- STOP order validation: STOP SELL requires price < current bid, STOP BUY requires price > current ask
- Symbol conversion: `symbol_to_instrument('EUR-USD')` → `'EUR_USD'`

**Trade Sync** (`modes/forex_live_mode.py`)
- `_sync_trades_with_broker()` — polls `get_open_trades()` every 3s
- Compares broker trade IDs against internal `ticket.exchange_trade_id`
- Detects broker-closed trades (TP/SL hit), closes internal tickets, records trades
- `_enrich_order_from_broker()` — queries `/orders/{id}` then `/transactions/{tx_id}` for actual fill price and trade_id

### IG Markets Live Trading

**IGMarketsDriver** (`live_drivers/IG/IGMarketsDriver.py` — 667 lines)
- `_authenticate()` — login with CST + security token headers
- `_resolve_cfd_account_id()` — auto-detects CFD vs Spread Betting account, switches to CFD
- Expiry: uses `expiry: '-'` for perpetual CFD (NOT `'DFB'` which causes `REJECT_SPREADBET_ORDER_ON_CFD_ACCOUNT`)
- Currency from instrument: `instrument.currencies[0].name` (ISO code like 'USD'), NOT `.code`
- Cancel working orders: IG requires POST with `_method: 'DELETE'` header, not HTTP DELETE

**Lightstreamer Streaming** (`_run_lightstreamer()`)
- Raw HTTP protocol — no library dependency, rate-limit free
- Session creation: POST to `{ls_endpoint}/lightstreamer/create_session.txt` with CST/XST auth
- Subscription via ControlAddress for each epic with schema: `BID OFFER UPDATE_TIME MARKET_STATE`
- Partial update handling: maintains `last_prices` cache, merges sparse updates
- `trust_env=False` on requests.Session to bypass proxy for LS control address
- Auto-reconnection with 5s retry on stream errors

**Deal Confirmation** (`_confirm_deal()`)
- Two-step flow: POST returns `dealReference`, then GET `/confirms/{ref}` for status
- Retry logic for transient REJECTED/UNKNOWN responses (wait 1s, retry once)
- Raises on REJECTED status (prevents false fill detection in order sync)

**Rate Limiting** (`_safe_request()`)
- 403 = rate limit (NOT auth failure), exponential backoff (5s initial → 30s max, factor 1.5)
- 401 triggers re-auth with 10s cooldown to prevent auth loop
- Resets backoff to 5s on success

**Position Sync**
- Reverse `DEFAULT_EPIC_MAP` converts IG instrument names (`EUR/USD`) to qengine symbols (`EUR-USD`)
- Order sync: 10s interval (vs OANDA 3s) due to API rate limits
- Position sync: 60s interval

### Live Trading Infrastructure

**Forex Live Mode** (`modes/forex_live_mode.py` — 1,352 lines, NEW)
- Replaces external `jesse_live` plugin for native forex/CFD live trading
- `run()` — main entry: configures driver, syncs account, fetches precisions, enters trading loop
- Multi-tier broker sync with configurable intervals:
  - Orders: 3s (OANDA) / 10s (IG) — detect fills
  - Trades: 3s (OANDA) / 10s (IG) — detect broker-side TP/SL closes
  - Positions: 30s (OANDA) / 60s (IG) — fallback safety sync
  - Account: 30s with exponential backoff (doubles to max 5 min on failure)
- `_sync_orders_with_broker()` — detects filled orders by comparing broker pending vs internal active
- `_sync_positions_with_broker()` — safety fallback: force-closes internal position if broker shows flat
- `_graceful_shutdown()` — cancel all orders → close all positions → wait 2s → compute session report
- Paper trading: demo brokers route to practice APIs automatically
- `_CandleBuilder` — accumulates ticks into OHLCV candles aligned to timeframe boundaries

**Redis State Publishing** (`_publish_state()`)
- Positions: symbol, type, qty, entry_price, current_price, pnl, leverage, tickets array (id, type, qty, entry_price, pnl, pips, trade_id, opened_at)
- Orders: id, symbol, side, type, qty, filled_qty, price, status, reduce_only
- Closed trades: realized PnL, win/loss, per-trade history
- Account summary: balance, equity, NAV, available_margin, margin_used, unrealized_pnl, currency, account_id, trade counts
- Strategy state: name, symbol, timeframe, position status, hyperparameters, current_session (level, TP/hedge prices, legs), sessions history
- Log streaming: Redis list trimmed to 2,000 entries
- State: 24h expiry, Reports: 7-day expiry
- Pub/sub `live-update` events for real-time dashboard

**Session Reports** (`_compute_session_report()`)
- Computed at session end: total trades, win rate, total PnL, avg win/loss, largest win/loss, winning streak, max drawdown, duration, full trade list

**Base Driver Architecture** (`live_drivers/base.py` — 198 lines, NEW)
- `ForexLiveDriver(ExchangeDriver)` abstract base class
- Abstract methods: `_submit_market_order`, `_submit_limit_order`, `_submit_stop_order`, `_cancel_order_on_exchange`, `_cancel_all_orders_on_exchange`, `_fetch_precisions`, `start_price_stream`, `get_account_summary`, `get_open_positions`, `get_open_orders`
- Optional methods with defaults: `get_open_trades()` → `[]`, `set_trade_tp_sl()` → pass, `cancel_trade_tp_sl()` → pass, `close_trade()` → `{}`
- Concrete: `market_order()`, `limit_order()`, `stop_order()`, `cancel_order()`, `cancel_all_orders()`
- Market orders return `{order_id, fill_price, trade_id}` dict; stores `trade_id` in `order.vars`
- `configure(api_key, account_id, **kwargs)` — generic configuration
- Driver registry in `live_drivers/__init__.py`: maps broker IDs to driver classes

**IBKR Driver** (`live_drivers/IBKR/IBKRDriver.py` — 227 lines)
- `IBKRLiveDriver` and `IBKRPaperDriver` classes
- TWS socket API integration via `ib_insync`

### SurefireHedge Strategies (Complete Rewrite)

**Surefire (V1)** — `strategies/Surefire/` (1,010 lines)
- Renamed from `SurefireHedge`
- Manual directional entry (long/short/random), fixed TP/SL distances in pips
- 4 sizing operators: `multiplier` (m^n), `sqrt` (sqrt(m)^n), `linear` (1+n), `fibonacci`
- Full OANDA broker integration:
  - Per-trade TP/SL via `driver.set_trade_tp_sl()`
  - Hedge STOP orders via `driver._submit_stop_order()`
  - Broker order retry with throttle (3 retries, then every 10 ticks)
  - `broker_orders_set` flag with independent TP/SL and hedge tracking
- CFD ticket mode: multiple simultaneous tickets across hedge levels
- Session tracking with cooldown management
- Recursive retry protection (`_depth` parameter limiting to 5)
- Spread buffer for STOP order breach detection

**SurefireV2** — `strategies/SurefireV2/` (672 lines)
- Renamed from `SurefireHedgeV2`
- Indicator-based entry: `ema` (fast/slow crossover), `rsi` (OB/OS zones), `macd` (line crosses signal), `supertrend` (direction), `ema_rsi`, `ema_macd`, `triple` (all three must agree)
- Bucket threshold exit: closes when floating PnL >= `bucket_pct` of equity (no fixed TP lines)
- Dynamic ATR-based hedge distance: `ATR(period) * hedge_atr_mult` with minimum floor (15 pips)
- Circuit breakers: `max_daily_loss_pct` (2%), `max_consec_busts` (3), ATR expansion detection (2x avg → reduce size to 0.1%)
- `SafetySizing` integration: worst-case loss calc, affordability checks, dynamic level computation
- Session filters: `london`, `new_york`, `overlap`, `london_ny`, `any`
- Cooldown skip after `bucket_hit` for immediate re-entry
- Halt state tracking: `_halted`, `_halt_until_index`, `_halt_reason`
- Monitoring: `_bust_rate()`, `_daily_drawdown()`, consecutive bust counter, extensive `watch_list()`

### Safety Sizing Module

**SafetySizing** (`services/safety_sizing.py` — 135 lines, NEW)
- `max_exposure_units()` — total notional if all levels fire
- `worst_case_loss()` — dollar loss if all levels fire + final loses
- `max_safe_initial_size()` — largest base size where worst-case < threshold
- `can_afford_cycle()` — binary safety check before cycle start
- `dynamic_size()` — scale down base_size if exceeds limit
- `levels_affordable()` — auto-compute max levels based on current balance
- `exposure_ratio()` — worst-case as % of balance (>1 = potential ruin)
- Configurable: `max_risk_per_cycle_pct` (15%), `max_total_exposure_pct` (50%), `margin_buffer_pct` (20%)

### SurefireHedge V2 Research (9 Phases, 50 Findings)

Comprehensive quantitative research in `notebooks/surefire_v2/` (14 scripts, 10,000+ lines):

- **Phase 1-3**: Indicators provide zero edge (~33% win rate = baseline). Bust anatomy: P(bust)=7.5%, one bust erases 6.5 wins. Conditional win probability increases with depth (L0=32%, L4=43%). Cooldown ineffective.
- **Phase 4**: Corrected Monte Carlo — 0% ruin at $10k across all configs (10k sims x 2k cycles). Phase 1 was wrong (independent Bernoulli model).
- **Phase 5**: Capital scaling validated — identical % returns at $10k/$100k/$1M. Optimal: 12 levels, sqrt(2) multiplier, 0.3-0.5% base → 99.7% win rate, Sharpe 0.166. EUR-USD supports up to $10M without liquidity issues.
- **Phase 6**: Deep tail risk — levels 6+ are NET NEGATIVE with sqrt multiplier. Martingale invariant: P(bust) x severity = constant. Kurtosis=601. Recovery: 93 median cycles (34h trading).
- **Phase 7**: Mathematical risk framework — critical p*m threshold: sqrt(2) gives 0.80 (helps), 2x gives 1.13 (hurts). Optimization is MINLP (5 vars) but trivially solvable. ML targets validated: P5 (entry quality), P6 (regime detection).
- **Phase 8**: Blind out-of-sample backtest (2025-02 to 2026-03) — test OUTPERFORMS train. 99.9% win rate, PF 21.5, 12.8% return. Per-level P(lose) stable (L0: 0.623 train vs 0.634 test). No overfitting via bootstrap test.
- **Phase 9**: Loss path classification — 98.7% of busts are "choppy range" (inherent geometric constraint). No pre-entry signal predicts busts (Cohen's d < 0.1). Temporal: higher bust rate at Asian session transitions (10.4% at 03:00 UTC).

### Dashboard UI (Complete Redesign)

**Live Trading Dashboard** — `LiveTrade.vue` (1,324 lines)
- Multi-session tabs with add/remove/switch
- 6 detail tabs: Positions (expandable tickets sub-table), Orders (status badges), Logs (filterable by level), Session (surefire state), Closed Trades, Report
- 10 account metric cards in 2→4→5 responsive grid: Balance, NAV, Unrealized P&L, Realized P&L, Position Value, Margin Used/Available, Leverage, Trade counts (W/L), Open trades
- Color-coded P&L indicators, margin utilization threshold colors
- Session state panel: level, TP/hedge prices, legs table with level progression, past sessions
- New Session modal: broker selection, symbol picker, strategy selector, hyperparameter controls
- Demo vs Live account warnings with color-coded indicators

**Backtest UI** — `Backtest.vue` (2,799 lines)
- Multi-workspace tabs with status indicators (running=green pulse, results=brand, empty=gray)
- Workspace switching blocked during active runs
- Hyperparameter system: typed inputs (int/float/string/select) with min/max, conditional visibility, reset-to-defaults, inline descriptions
- Exposure table with lots/units toggle and meta info (contract size, leverage, current price)
- AI-assisted strategy fixing via inline editor with LLM refinement prompt
- Progress bar with ETA during runs
- Cost model configuration (spread, slippage, swap)
- Export options: Charts, TradingView, CSV, JSON

**Charting** — `TradeChart.vue` (1,000+ lines)
- Lightweight Charts integration for candlesticks and equity curves
- 8 timeframes: 1m, 5m, 15m, 30m, 1h, 4h, 1D, 1W
- Zoom, fit, auto-scale controls
- Progressive rendering with progress tracking
- Full-screen expand mode
- Multiple chart tabs

**Mobile-First Responsive Design**
- `BottomNav.vue` (229 lines) — fixed bottom navigation replacing sidebar on mobile
  - 3-button interface: Home, Trading (bottom sheet), More (bottom sheet)
  - Bottom sheets with 3-column icon grids for sub-routes
  - Glassmorphism: `backdrop-filter: blur(24px)`, semi-transparent backgrounds, `rounded-3xl` pill shape
- `Sidebar.vue` (141 lines) — desktop fixed left sidebar with SVG icons, active states, theme toggle, logout
- Adaptive layouts: 1→2→4→5 column grids across breakpoints
- Touch-optimized button sizes (py-3-4), collapsible sections
- Bottom padding adjustments (`pb-24 lg:pb-8`) for nav clearance
- Charts: full height on mobile, 300-450px on desktop

**Dashboard Home** — `Dashboard.vue` (411 lines)
- Running tasks display with progress indicators
- Activity counts: backtests, optimizations, Monte Carlo, live sessions
- Recent sessions timeline
- Market status indicators
- Connected brokers grid
- LLM status display
- Pip value calculator

**Toast Notification System** — `ToastContainer.vue`
- 4 types: success (green), error (red), warning (amber), info (blue)
- Responsive positioning: bottom-right (desktop), bottom-center (mobile)
- Slide animations (mobile up, desktop right), click-to-dismiss, auto-dismiss

**Optimization UI** — `Optimization.vue` (1,550 lines)
- Training/testing date ranges with split configuration
- 7 objective functions: Sharpe, Calmar, Sortino, Omega, Serenity, Smart Sharpe, Smart Sortino
- Trials per parameter configuration
- CPU core allocation
- Best candidates selection count

**Monte Carlo UI** — `MonteCarlo.vue` (1,383 lines)
- Trade shuffle vs candle simulation modes
- Pipeline types: Moving Block Bootstrap, Gaussian Noise
- Configurable block sizes and sigma values
- Scenario count (5-1000)

**Strategy Editor** — `Strategies.vue` (927 lines)
- AI Strategy Generator panel (LLM-powered)
- Strategy playground with market scenarios
- Multi-tab editor with modified indicator
- Create/delete/edit operations
- AI refinement prompt input

**WebSocket Client** — `useWebSocket.js`
- Shared connection pool (singleton pattern)
- Automatic reconnection with exponential backoff (2s→4s→8s→16s→30s max)
- GZIP decompression for large payloads
- Message dispatching to multiple listeners
- Connection status tracking (`wsConnected` ref)
- Toast notifications for connection events
- Events: `backtest.*`, `optimize.*`, `monte-carlo.*`, `candles.*`, `live.*`, ping/pong

### Performance Optimizations

**Candle Import** (`services/candle_service.py`)
- Eliminated per-batch DB queries during import — single query for range validation
- Removed O(n^2) fill operation for gap detection
- Eager tuple materialization from Peewee queries (prevents lazy evaluation overhead)
- Vectorized NumPy candle generation: open from first, close from last, high/low from max/min, volume summed — no loops
- Comprehensive timestamp validation: verifies earliest/latest available candles cover requested range, raises `CandleNotFoundInDatabase` with diagnostics
- Optional Redis cache for candle batches (7-day expiry, keyed by date range + exchange + symbol)

**WebSocket**
- Fixed event name mismatches between backend publishers and frontend listeners
- GZIP decompression support for large payloads
- Shared connection pool eliminates duplicate connections

### Deployment

- Railway deployment: `railway.toml` with Dockerfile.prod builder, health checks, concurrency limits
- `docker-entrypoint.sh`: Redis URL parsing, DATABASE_URL parsing, auto .env generation, fallback to embedded Redis, connection pooling detection, graceful fallback to uvicorn if CLI fails
- Dockerfile.prod: multi-stage (Node.js 20-alpine for frontend build + Python 3.12-slim-bookworm for backend), embedded Redis
- Dockerfile fixes: CMD/WORKDIR in final stage, numpy version pinning (1.25.0), numba compatibility (>=0.61.3)
- DB credential fallback from environment variables
- Port configuration fixes for cloud platforms

### Bug Fixes

- `Strategy._execute()` wrapped in try/finally to prevent `_is_executing` deadlock on errors
- Use `jh.is_live()` (covers both livetrade AND papertrade) instead of `jh.is_livetrading()` in strategies
- Cancel→resubmit loop: TP/SL and hedge STOP orders tracked independently to prevent re-placement every tick
- OANDA STOP order validation with spread buffer for pre-check
- IG Markets: `_confirm_deal` now raises on rejection (prevents false fill detection in order sync)
- IG Markets: 403 treated as rate limit, not auth failure (was triggering re-auth loops)
- WebSocket event name mismatches causing silent data drops on frontend
- DB URL parsing for empty string environment variables
- Maintenance UI wired to actual backend clear endpoints
- Overlapping UI elements fixed in navigation
- Mobile nav position fixed

---

## [2.0.0] - 2026-03-22

### Complete Rebrand and Platform Overhaul

QEngine v2.0.0 transforms the Jesse crypto trading framework into a multi-asset algorithmic trading platform for forex, commodities, and CFDs. Every file, import, config, and reference renamed from `jesse` to `qengine` (540+ files).

### Core Platform Changes

**Package Rename**
- All imports: `from jesse.*` → `from qengine.*` across entire codebase
- CLI: `jesse` → `qengine run`
- Database: `jesse_db` → `qengine_db`, `jesse_user` → `qengine_user`
- Internal fields: `jesse_submitted` → `engine_submitted`
- Route paths: `/jesse-trade/*` → `/marketplace/*`
- Service files: `jesse_trade.py` → `upstream_api.py`
- PyPI version check URL updated

**Application Server** (`__init__.py`, `cli.py`)
- FastAPI replacing Flask — full async support
- Uvicorn server with configurable host/port
- Lifespan context manager (modern FastAPI pattern)
- `_restore_saved_settings()` — auto-restores LLM config and broker API keys from DB on startup
- `_sync_broker_keys_to_db()` — syncs broker credentials from app_settings to ExchangeApiKeys table
- Static file mounting with favicon for web dashboard
- Automatic database migrations on startup
- Python Language Server auto-installation for strategy editor

**Configuration** (`config.py`, `info.py`)
- Separated `exchange_info` and `broker_info` registries
- Dynamic broker configuration with default leverage per broker
- Cost model flag in app config
- `broker_info` dictionary with metadata per broker: name, type, asset_classes, fee_model, default_leverage, supported_modes, API_type
- `backtesting_exchanges` and `live_trading_exchanges` lists filtered from broker_info
- Settlement currency tracking per broker

**Database** (`services/db.py`, `services/migrator.py`)
- PostgreSQL-only architecture (removed SQLite support)
- Connection pooling with keepalive settings
- SSL mode support
- New migrations: Candle (`timeframe` field, composite index), ClosedTrade (session tracking, soft delete, timestamps), Order (`updated_at`, `session_mode`, `engine_submitted`, `submitted_via`, `fee`)

### New Exchange Model: ForexCFDExchange

**ForexCFDExchange** (`models/ForexCFDExchange.py` — 280 lines, NEW)
- Inherits from Exchange, adds CFD-specific behavior
- Spread-based fee model: per-symbol spread in price units with optional randomness
- Slippage simulation with configurable randomness
- Overnight swap rates: per-symbol long/short daily rates, charged at 5pm NY rollover
- Commission per lot: optional fixed commission on top of spread
- Available margin calculation: wallet balance - used margin (open positions + pending orders)
- Default leverage: configurable per exchange (OANDA=30x, IBKR=50x)
- Live trading properties: `_wallet_balance`, `_available_margin`, `_started_balance`
- `update_from_stream()` — updates balance/margin from broker API in live mode
- Order lifecycle: `on_order_submission()` (margin check), `on_order_execution()`, `on_order_cancellation()`

### Instrument Registry

**InstrumentRegistry** (`core/instruments.py` — NEW)
- `Instrument` dataclass: symbol, asset_class, pip_size, contract_size, min_lot, lot_step, base/quote currencies, margin_rate, trading_hours, swap rates
- Asset class inference from symbol: FOREX, COMMODITY, INDEX, STOCK, CRYPTO
- Pip size inference: JPY/HUF pairs = 0.01, others = 0.0001
- Default instruments database for major FX and commodity pairs
- `get_pip_size()`, `get_contract_size()`, `get_margin_rate()` lookups

### Market Hours System

**MarketHours** (`core/market_hours.py` — NEW)
- Forex: Sunday 5pm ET to Friday 5pm ET (continuous)
- Commodity: similar with daily break 5pm-6pm ET
- Index CFDs: extended hours (Sunday 6pm for US indices)
- DST handling: approximate US DST calculations for NY timezone
- `is_market_open(timestamp, symbol)` — checks if market accepting orders
- `is_rollover_time(timestamp)` — True at 5pm NY daily (swap charge time)
- `current_session(timestamp)` — returns Tokyo/London/New_York/Overlap/Off
- `next_market_open()`, `next_market_close()` — scheduling helpers
- `minutes_to_close()` — countdown for session-aware strategies

### Strategy Framework Enhancements

**New Properties** (`strategies/Strategy.py`)
- `hedge_mode: bool` (default False) — allows simultaneous long+short, bypasses ConflictingRules
- `chart_label: str` — optional label prefix on chart markers (e.g., 'S1·O2')
- `_cached_price: float` — caches price during execution cycle for consistency
- `shared_vars` — returns `store.vars` for cross-route data sharing
- `is_cfd_trading` / `is_forex_cfd_trading` — True if exchange type is 'cfd'
- `asset_class` — returns forex/commodity/index/stock/crypto
- `spread` — current spread in price units from exchange
- `pip_size` — pip size for the instrument
- `market_is_open` — whether market is currently open
- `session` — current forex session (tokyo/london/new_york/overlap/off)
- `minutes_to_close` — countdown to session close
- `swap_long` / `swap_short` — overnight swap rates
- `contract_size` — e.g., 100000 for forex standard lot
- `volume` — current candle volume from `current_candle[5]`

**New Methods**
- `pips_to_price(pips)` — converts pips to price distance
- `price_to_pips(price_distance)` — converts price distance to pips
- `lot_size_for_risk(risk_pct, stop_pips)` — calculates lot size for given risk % and stop distance
- `liquidate()` — closes entire position at market immediately
- `candles_pipeline()` — returns optional candle pipeline for data manipulation

**Modified Methods**
- `on_close_position(order, closed_trade)` — SIGNATURE CHANGED: now receives `closed_trade` parameter
- `_check()` — hedge mode: when both `should_long` and `should_short` return True, executes BOTH if `hedge_mode=True`
- `_execute()` — price caching at start, try/finally to prevent `_is_executing` deadlock
- `price` property — returns cached price during execution for consistency
- `leverage` property — added CFD branch returning `exchange.default_leverage`
- `portfolio_value` property — rewritten: CFD mode sums unrealized PnL (not scaled by leverage)
- `_handle_executed_order_for_chart()` — builds chart markers with position type, chart_label prefix, order ID

**New Enums** (`enums/__init__.py`)
- `brokers` dataclass: OANDA, OANDA_DEMO, IG_MARKETS, IG_MARKETS_DEMO, IBKR, IBKR_PAPER
- `asset_classes`: FOREX, COMMODITY, INDEX, STOCK, CRYPTO
- `live_session_modes`: LIVETRADE, PAPERTRADE
- `live_session_statuses`: DRAFT, STARTING, RUNNING, STOPPING, STOPPED, TERMINATED, ERROR
- `order_submitted_via`: STOP_LOSS, TAKE_PROFIT
- `migration_actions`: ADD_INDEX, DROP_INDEX
- Order status: LIQUIDATED (new)

**New Exceptions**
- `InsufficientMargin` — raised when margin level drops below stop-out
- `CandleNotFoundInDatabase` — enhanced with symbol, exchange, start_date, type detail

### Backtest Engine Enhancements

**Backtest Mode** (`modes/backtest_mode.py` — significantly expanded)
- Floating PnL tracking: `daily_floating_pnl` array for unrealized PnL visualization
- Margin tracking: `daily_margin_used`, `peak_margin_used`, `peak_equity_usage_pct`
- Market hours integration: skips execution when forex markets closed
- Overnight swap charges at 5pm NY rollover for open positions
- Margin call handling: stop-out at 50% margin level with forced position closure (`_check_for_margin_call()`)
- Gap handling: `_apply_gap_execution_prices()` applies slippage on weekend gaps for stop/limit orders
- Session statistics: per-session max/min floating PnL, peak margin, margin block leg info
- Session logging: market open/close events, backtest start/completion with trade counts
- Cost model flag: `cost_model: bool = True` controls swap/spread application
- Two simulation modes: `_step_simulator()` (per-candle) vs `_skip_simulator()` (fast batch)
- Redis integration: `is_process_active()` for process status checking
- Full HTML report generation: `_generate_full_report()`

**Store State Enhancements** (`store/state_app.py`)
- `daily_floating_pnl` — array of daily unrealized PnL
- `daily_margin_used` — array of daily margin used
- `worst_floating_pnl` — worst unrealized PnL during backtest
- `peak_margin_used` — peak margin used
- `peak_equity_usage_pct` — peak equity usage percentage
- `session_stats` — per-session tracking dict for hedge strategies

**Charts & Visualization** (`services/charts.py`)
- `floating_pnl_curve()` — unrealized PnL over time
- `margin_usage_curve()` — margin used over time
- Benchmark comparison: portfolio vs individual symbol performance

**Metrics & Reporting** (`services/metrics.py`, `report.py`)
- `worst_floating_pnl` metric
- `peak_margin_used` metric
- `peak_equity_usage_pct` metric
- `_calculate_hedge_session_metrics()` — win rate and P&L per session
- `hedge_sessions()` — grouped trade sessions with per-session stats

### Broker Integrations (Candle Import Drivers)

**OANDA** (`modes/import_candles_mode/drivers/OANDA/`)
- `OandaForex.py`, `OandaMain.py` — live + demo candle import
- Sub-minute granularity support: S5, S10, S15, S30
- Symbol conversion utilities

**IG Markets** (`modes/import_candles_mode/drivers/IG/`)
- `IGMarketsForex.py`, `IGMarketsMain.py` — live + demo
- Epic-based instrument mapping

**IBKR** (`modes/import_candles_mode/drivers/IBKR/`)
- `IBKRForex.py`, `IBKRMain.py`
- TWS socket-based candle fetch

**Crypto exchanges preserved**: Binance, Bybit, Coinbase, Gate, Hyperliquid, Apex, Bitfinex + CSV import

### API Controllers (22 endpoints)

**New Controllers**
- `broker_controller.py` — `/broker/list`, `/broker/grouped`, `/broker/supported-symbols`, `/broker/precisions`
- `llm_controller.py` — `/llm/generate`, `/llm/refine`, `/llm/validate`, `/llm/config`, `/llm/ai-generate-and-save`
- `live_controller.py` — `/live` (start), `/live/cancel`, `/live/logs`, `/live/orders`, `/live/sessions`, session CRUD
- `settings_controller.py` — `/settings` GET/POST for LLM config, broker credentials, notification settings
- `websocket_controller.py` — WebSocket connection management

**Enhanced Controllers**
- `backtest_controller.py` — session persistence, strategy code capture
- `optimization_controller.py` — best candidates count, training/testing split config
- `monte_carlo_controller.py` — candle pipeline configuration
- `strategy_controller.py` — AI generation/refinement integration
- `candles_controller.py` — multi-broker import support
- `system_controller.py` — broker metadata in general info
- `playground_controller.py` — real-time strategy testing

**Request Models** (`services/web.py`)
- `BacktestRequestJson`, `OptimizationRequestJson`, `LiveRequestJson`
- `ImportCandlesRequestJson`, `MonteCarloRequestJson`
- `GenerateStrategyRequestJson`, `RefineStrategyRequestJson`, `ValidateStrategyRequestJson`
- All broker/exchange management request models

### LLM Engine

**LLM Service** (`services/llm_engine.py` — NEW)
- Providers: Anthropic (Claude), OpenAI (GPT), Google Gemini, any OpenAI-compatible API
- Auto-configuration from env vars, .env file, or database UI
- `generate_strategy()` — create strategy from natural language description
- `refine_strategy()` — improve existing strategy with feedback
- `validate_strategy()` — syntax check Python code
- Returns: code, explanation, validity flag, errors
- Full prompt engineering for trading context
- Configurable temperature, max_tokens

### Database Models (New)

- `BacktestSession` — session tracking with results, charts, logs, strategy code
- `OptimizationSession` — optimization tracking with best candidates
- `MonteCarloSession` — Monte Carlo session tracking
- `LiveSession` — live/paper trading session with status, state, notes
- `ExchangeApiKeys` — broker credential management
- `NotificationApiKeys` — notification service credentials
- `LiveEquitySnapshot` — equity curve tracking for live sessions
- `Issue` — bug/issue reporting and tracking
- `Option` — application settings persistence (key-value)

### Repositories (New)

- `backtest_session_repository.py`
- `optimization_session_repository.py`
- `monte_carlo_session_repository.py`
- `live_session_repository.py`
- `closed_trade_repository.py` — enhanced with session tracking, soft delete
- `candle_repository.py`
- `order_repository.py` — UUID fields cast to text for search
- `live_equity_repository.py`
- `open_tab_repository.py` — UI state persistence

### WebSocket Manager

**ConnectionManager** (`services/ws_manager.py` — NEW)
- Redis pub/sub integration for cross-process messaging
- Heartbeat mechanism (30s interval)
- Pattern-based subscription (channel patterns)
- Exponential backoff for failures
- Multiple concurrent connection handling

### Research Module

**Research API** (`research/candles.py`, `research/backtest.py`)
- `get_candles(exchange, symbol, timeframe, start, finish)` — returns `(warmup_candles, trading_candles)` tuple
- `store_candles()` — store numpy arrays of 1m candles to database
- `fake_candle()`, `fake_range_candles()`, `candles_from_close_prices()` — test helpers
- `backtest()` — run backtest from research notebooks
- `monte_carlo_trades()`, `monte_carlo_candles()` — Monte Carlo simulation from notebooks

### Candle Pipelines

**Monte Carlo Pipelines** (`candle_pipelines/`)
- `BaseCandlesPipeline` — base class
- `GaussianNoiseCandlesPipeline` — add realistic price noise with configurable sigma
- `GaussianResamplerCandlesPipeline` — resample candles
- `MovingBlockBootstrapCandlesPipeline` — block bootstrap for scenario generation

### Optimization Engine

**Optuna Integration** (`modes/optimize_mode/`)
- `Optimize.py` — main runner with Optuna hyperparameter optimization
- `fitness.py` — 7 objective functions: Sharpe, Calmar, Sortino, Omega, Serenity, Smart Sharpe, Smart Sortino
- Training/testing split (70/30) with cross-validation
- Configurable trials count and best candidates tracking
- Ray distributed computing support
- Results persistence in PostgreSQL

### Monte Carlo Engine

**Scenario Generation** (`modes/monte_carlo_mode/`)
- `MonteCarloRunner.py` — main scenario generation and analysis
- Trade shuffling mode: randomize trade order, analyze equity curve distribution
- Candle perturbation mode: add noise to price data, re-run backtest
- Statistical output: confidence intervals, percentiles, p-values
- Ray-powered parallel scenario execution

### Dashboard (Vue 3 — Complete Rewrite)

**Frontend Stack**
- Vue 3 + Vite + Tailwind CSS replacing old Nuxt 3 UI
- Served at root `/` (was `/te/`)
- 13 views: Dashboard, Brokers, Tools, Strategies, Backtest, Optimization, Monte Carlo, Live Trade, Import Data, LLM Studio, Issues, Settings, Login
- Dark theme with accent colors, glassmorphism cards
- Real-time WebSocket updates for all operations

**API Client** (`api.js`)
- RESTful endpoints for all features
- Token-based authentication (localStorage)
- Comprehensive endpoint coverage: strategies, backtests, optimization, live trading, brokers, market data, LLM

### Infrastructure

**Docker** (`Dockerfile`, `Dockerfile.prod`, `docker-compose.yml`)
- Dev: Python 3.11-slim-bullseye with pytest support
- Prod: Multi-stage — Node.js 20-alpine frontend build + Python 3.12-slim-bookworm backend
- Embedded Redis in production image
- docker-compose: PostgreSQL 16-alpine, Redis 7-alpine, app service, Caddy reverse proxy (80/443)
- Volume mounts for strategies and storage

**Auth** (`services/auth.py`)
- Token-based authentication
- Simple password-based auth for dashboard access

**Multiprocessing** (`services/multiprocessing.py`)
- Process manager for async task execution (backtest, live, optimization, Monte Carlo)

**LSP** (`services/lsp.py`)
- Pyright Language Server for in-browser strategy code intelligence

### Preserved from Jesse

- `jesse_rust` external dependency (Rust indicator library, unchanged)
- MIT License with Jesse copyright acknowledgment
- Core event-driven backtesting engine logic
- Strategy execution model and order management
- Technical indicators (170+, via jesse_rust)
- Crypto exchange support (Binance, Bybit, etc.)

### Removed

- Old Nuxt 3 dashboard (16MB, 438 files in `static/_nuxt/`)
- Legacy static files (`404.html`, `200.html`, old favicons)
- Crypto-only exchange configurations
- `tradeengine` and `jesse` egg-info directories
- SQLite database support
- Flask-based API server

---

## [1.x] - Jesse Foundation

The original Jesse framework by jesse-ai provided the foundation:
- Event-driven backtesting engine
- Strategy base class with order management
- Technical indicators (via jesse_rust)
- Crypto exchange support (Binance, Bybit, Coinbase, etc.)
- Basic CLI interface
- Flask-based API server
- Nuxt 3 dashboard

See [Jesse on GitHub](https://github.com/jesse-ai/jesse) for the original project history.
