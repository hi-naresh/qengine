# QEngine Codebase Audit — Dead Code, Unused Functions & Redundancies

**Date**: 2026-04-03 (Updated 2026-04-04)  
**Scope**: Full audit of all classes, functions, and properties across qengine/

---

## Corrections (2026-04-04)

- **`metrics.candles_info()`, `metrics.routes()`, `metrics.hyperparameters()`** — NOT dead. Called from `backtest_mode.py` via `stats.` alias. Removed from dead code list.
- **7 exception classes** — KEPT. Reasonable for future live trading error handling.
- **Orderbook subsystem** — KEPT. Fully implemented, worth wiring into backtest for depth-based slippage.
- **`Trade.py`** — Confirmed dead (market tick aggregation model, never wired). `ClosedTrade` handles strategy trades separately.
- **`tempt_trades` typo** — FIXED to `temp_trades` in `state_closed_trades.py`.

---

## Executive Summary

| Category | Count |
|----------|-------|
| **Total dead functions** | 19 |
| **Dead enum values** | 2 |
| **Redundant/duplicate functions** | 3 pairs |
| **Possibly dead (needs confirmation)** | 14 |
| **Dead strategy** | 1 (SFPilot) |
| **Dead model** | 1 (Trade.py) |
| **Kept for future use** | 7 exceptions, orderbook subsystem |

---

## 1. CONFIRMED DEAD CODE

### 1.1 Dead Helper Functions (`qengine/helpers.py`)

| Function | Description | Recommendation |
|----------|-------------|----------------|
| `clear_file()` | File clearing utility | REMOVE |
| `compressed_response()` | HTTP compression helper | REMOVE |
| `computer_name()` | Returns hostname | REMOVE |
| `current_1m_candle_timestamp()` | Timestamp rounding | REMOVE |
| `generate_short_unique_id()` | Short UUID generator | REMOVE |
| `get_arrow()` | Arrow time object creator | REMOVE |
| `get_quote_asset()` | Duplicate of `quote_asset()` | REMOVE (keep `quote_asset()`) |
| `get_store()` | Store accessor | REMOVE |
| `dd()` (line ~1053) | Debug dump, never called | REMOVE |

### 1.2 Dead Utility Functions (`qengine/utils.py`)

| Function | Line | Description | Recommendation |
|----------|------|-------------|----------------|
| `dd()` | 304 | Debug dump | REMOVE |
| `are_cointegrated()` | 291 | Statistical cointegration test | REMOVE or move to notebooks |
| `calculate_alpha_beta()` | 325 | CAPM analysis | REMOVE or move to notebooks |

### 1.3 Dead Service Functions

| Function | File | Line | Recommendation |
|----------|------|------|----------------|
| `create_logger_file()` | `services/logger.py` | 34 | REMOVE |
| `log_exchange_message()` | `services/logger.py` | 116 | REMOVE |
| `create_trade_from_dict()` | `services/closed_trade_service.py` | 10 | REMOVE |

> **Note**: `metrics.candles_info()`, `metrics.routes()`, and `metrics.hyperparameters()` were initially flagged as dead but are actually called from `backtest_mode.py` via `from qengine.services import metrics as stats`.

### 1.4 Dead Repository Functions

| Function | File | Recommendation |
|----------|------|----------------|
| `store_candles_into_db()` | `repositories/candle_repository.py` | REMOVE |
| `get_simulated_orders()` | `repositories/order_repository.py` | REMOVE |

### 1.5 Dead Model (`models/Trade.py`)

The entire `Trade` class and `store_trade_into_db()` function are dead code:
- `Trade` class is never instantiated
- `store_trade_into_db()` returns immediately at line 44 (all DB code unreachable)
- Trade aggregation uses `DynamicNumpyArray` in `state_trades.py` instead

**Recommendation**: DELETE `Trade.py` entirely.

### 1.6 Unused Exceptions — KEPT (`qengine/exceptions/__init__.py`)

The following 7 exceptions are not currently used but are **kept for future live trading**:
`ExchangeRejectedOrder`, `ExchangeRejectedLeverageNumber`, `ExchangeOrderNotFound`,
`NegativeBalance`, `InvalidExchangeApiKeys`, `ExchangeError`, `NotSupportedError`.

These are reasonable error types for broker integrations and should be wired in as live trading matures.

### 1.7 Dead Enum Values (`qengine/enums/__init__.py`)

| Enum | Value | Recommendation |
|------|-------|----------------|
| `order_statuses.LIQUIDATED` | `'LIQUIDATED'` | REMOVE |
| `order_types.STOP_LIMIT` | `'STOP LIMIT'` | REMOVE |

### 1.8 Dead Strategy

| Strategy | Location | Evidence | Recommendation |
|----------|----------|----------|----------------|
| `SFPilot` | `strategies/_admin/SFPilot/` | Only 2 self-references; not used in routes, tests, or configs | REMOVE or archive |

### 1.9 Dead Framework Method

| Method | File | Line | Recommendation |
|--------|------|------|----------------|
| `PipelineStats.record_cycle_end()` | `framework/stats.py` | 190 | REMOVE (duplicate of `end_cycle()`) |

---

## 2. POSSIBLY DEAD CODE (Needs Confirmation)

These have no grep matches but may be used dynamically or reserved for future features.

### 2.1 Store State Methods

| Method | File | Notes |
|--------|------|-------|
| `OrdersState.reset_trade_orders()` | `store/state_orders.py:25` | No calls found |
| `OrdersState.get_all_orders()` | `store/state_orders.py:72` | No clear external usage |
| `OrdersState.count_active_orders()` | `store/state_orders.py:91` | No grep matches |
| `CandlesState.mark_all_as_initiated()` | `store/state_candles.py:16` | No calls found |
| `ExchangesState.trading_exchange` | `store/state_exchanges.py:16` | Property defined but no usage |
| `AppState.session_stats` | `store/state_app.py:26` | Initialized but never populated |
| `AppState.session_info` | `store/state_app.py:29` | Initialized but never used |
| `StoreClass.vars` | `store/__init__.py:27` | Comment says "shared_vars" but no grep matches |

### 2.2 OrderBook Feature (Entire Subsystem Possibly Dead)

All 7 getter methods in `state_orderbook.py` have commented-out tests:
- `add_orderbook()`, `get_current_orderbook()`, `get_current_asks()`, `get_best_ask()`, `get_current_bids()`, `get_best_bid()`, `get_orderbooks()`

**Recommendation**: Either remove the orderbook feature or re-enable with working tests.

### 2.3 SafetySizing Method

| Method | File | Notes |
|--------|------|-------|
| `SafetySizing.levels_affordable()` | `services/safety_sizing.py:117` | Called in tests but no strategy usage |

---

## 3. REDUNDANT / DUPLICATE CODE

### 3.1 Duplicate Helper Functions

| Function A | Function B | Issue | Fix |
|-----------|-----------|-------|-----|
| `base_asset()` | `get_base_asset()` | Identical implementations | Remove `get_base_asset()` |
| `quote_asset()` | `get_quote_asset()` | Similar (quote_asset has error handling) | Remove `get_quote_asset()` |
| `utils.dd()` | `helpers.dd()` | Both are debug dumps, neither called | Remove both |

### 3.2 Misspelled Variable

| Variable | File | Line | Fix |
|----------|------|------|-----|
| ~~`tempt_trades`~~ | `store/state_closed_trades.py` | 8 | FIXED: renamed to `temp_trades` |

---

## 4. VERIFIED ACTIVE CODE (No Issues)

### 4.1 Models — All Active

| File | Classes | Status |
|------|---------|--------|
| `Position.py` | CFDTicket, Position (all 30+ properties/methods) | ALL USED |
| `Order.py` | Order (all 14 properties) | ALL USED |
| `ClosedTrade.py` | ClosedTrade (all 15 properties) | ALL USED |
| `Exchange.py` | Exchange (abstract base) | ALL USED |
| `FuturesExchange.py` | FuturesExchange (10 methods) | ALL USED |
| `SpotExchange.py` | SpotExchange (8 methods) | ALL USED |
| `ForexCFDExchange.py` | ForexCFDExchange (16 methods) | ALL USED |
| `Route.py` | Route | ALL USED |
| `Candle.py` | Candle | ALL USED |
| `DynamicNumpyArray.py` | DynamicNumpyArray | ALL USED |

### 4.2 Services — All Active (except noted above)

| File | Functions | Status |
|------|-----------|--------|
| `broker.py` | Broker class (10 methods) | ALL USED |
| `order_service.py` | 13 functions | ALL USED |
| `position_service.py` | 12 functions | ALL USED |
| `candle_service.py` | 22 functions | ALL USED |
| `exchange_service.py` | 2 functions | ALL USED |
| `safety_sizing.py` | SafetySizing (7 methods, 1 possibly dead) | MOSTLY USED |
| `notifier.py` | 7 functions | ALL USED |
| `validators.py` | 1 function | USED |

### 4.3 Framework — All Active (except noted above)

| File | Classes | Status |
|------|---------|--------|
| `base.py` | Pipeline (14 methods), PipelineStack (12 methods) | ALL USED |
| `stats.py` | PipelineStats (10 methods, 1 dead) | MOSTLY USED |
| `registry.py` | 6 functions | ALL USED |
| `entry_gate.py` | EntryGate (4 methods) | ALL USED |
| `danger_scorer.py` | WelfordNormalizer, DangerScorer | ALL USED |
| `q_abort.py` | QAbort (8 methods) | ALL USED |

### 4.4 Strategy.py Base Class — All 133 Methods Active

Every method in the Strategy base class is actively used — either as engine hooks (called by the execution loop), API methods (called by user strategies), or chart helpers (used in visualization).

### 4.5 Strategies — Active

| Strategy | References | Status |
|----------|-----------|--------|
| `UniversalMartingale` | 18 | ACTIVE |
| `SurefireV2` | 17 | ACTIVE |
| `Surefire` | 123 | HEAVILY USED |
| `Example` | 36 | ACTIVE (tests) |
| `SFPilot` | 2 | **DEAD** (self-references only) |

### 4.6 Factories, Research, Routes — All Active

All factory functions (`range_candles`, `candles_from_close_prices`, `fake_candle`, `fake_order`), research functions (`backtest`, `get_candles`), and route functions are actively used.

---

## 5. CLEANUP PRIORITY

### Priority 1 — Remove Immediately (Safe, Zero Risk)
- [ ] `models/Trade.py` — entire file (market tick model, never wired)
- [ ] `helpers.py`: `clear_file`, `compressed_response`, `computer_name`, `current_1m_candle_timestamp`, `generate_short_unique_id`, `get_arrow`, `get_quote_asset`, `get_store`, `dd`
- [ ] `utils.py`: `dd`, `are_cointegrated`, `calculate_alpha_beta`
- [ ] `logger.py`: `create_logger_file`, `log_exchange_message`
- [ ] `closed_trade_service.py`: `create_trade_from_dict`
- [ ] `stats.py`: `record_cycle_end`
- [ ] 2 unused enum values (`LIQUIDATED`, `STOP_LIMIT`)

### Priority 2 — Archive (Low Risk)
- [ ] `strategies/_admin/SFPilot/` — archive or delete
- [ ] `repositories/candle_repository.py`: `store_candles_into_db`
- [ ] `repositories/order_repository.py`: `get_simulated_orders`

### Priority 3 — Investigate (Need Confirmation)
- [ ] OrderBook subsystem — decide: keep or remove
- [ ] `StoreClass.vars` — verify if used via shared_vars
- [ ] `AppState.session_stats` / `session_info` — verify intent
- [x] ~~Fix `tempt_trades` typo~~ (DONE)

---

## 6. STATISTICS

| Category | Total | Active | Dead | Possibly Dead |
|----------|-------|--------|------|---------------|
| Models (classes) | 12 | 11 | 1 (Trade) | 0 |
| Services (functions) | 75+ | 72+ | 3 | 1 |
| Store (methods) | 50+ | 42+ | 0 | 8 |
| Framework (methods) | 55+ | 54+ | 1 | 0 |
| Helpers (functions) | 122 | 113 | 9 | 0 |
| Utils (functions) | 20 | 17 | 3 | 0 |
| Exceptions (classes) | 24 | 17 | 0 (7 kept) | 0 |
| Enums (values) | 30+ | 28+ | 2 | 0 |
| Strategies | 5 | 4 | 1 | 0 |
| Repositories (functions) | 20+ | 18+ | 2 | 0 |

**Overall health**: ~97% of codebase is actively used. ~3% is dead code that can be safely removed.

---

## 7. DESIGN NOTES

### Trade.py vs ClosedTrade — Different Purposes
- **Trade** (dead): Market-level tick aggregation (exchange trade stream: price, buy_qty, sell_qty per second bucket)
- **ClosedTrade** (active): Strategy-level position lifecycle (entry -> exit, PnL, fees, holding period)
- Removing Trade.py does NOT affect strategy trade tracking. `TradesState` in-memory buffer kept as placeholder for future tick data.

### Orderbook Subsystem — Future Enhancement
The orderbook is fully implemented (`state_orderbook.py`, 180 lines) but never wired into backtest or live trading. Current backtest uses simple OHLC price-level matching. Orderbook could enable:
- Depth-based slippage (large orders walk the book)
- Partial fill simulation (via existing `execute_order_partially()`)
- Market impact modeling
- Requires: historical orderbook data + integration into `backtest_mode.py` order matching loop

### Exceptions — Kept for Live Trading
7 unused exception classes kept as they map to real broker error scenarios (`ExchangeRejectedOrder`, `NegativeBalance`, etc.) that will be needed as OANDA/IG/IBKR integrations mature.
