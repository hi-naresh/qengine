# Strategy Consolidation & Engine-Managed Ticket TP/SL

**Date:** 2026-04-06
**Status:** Approved
**Branch:** `pipelines`

## Problem

Four overlapping Surefire-family strategies exist (`Surefire`, `SurefireV2`, `SFPilot`, `UniversalMartingale`) that implement the same martingale grid logic with slight variations. `Surefire` (V1) has ~50 lines of broker-specific code (`driver.set_trade_tp_sl()`, `driver._submit_stop_order()`) baked directly into the strategy, violating the engine's abstraction layer. A strategy should be pure trading logic — the engine should handle execution identically in backtest, live, and optimization modes.

## Goals

1. **One strategy** — consolidate to `UniversalMartingale` (which already replicates V1/V2/SFPilot via presets)
2. **Engine-managed ticket TP/SL** — strategy sets TP/SL on tickets, engine enforces them (simulates in backtest, submits to broker in live)
3. **Strategy never touches broker** — no `driver.*`, no `is_live()` checks, no `broker_orders_set` flags
4. **Any strategy type works** — the API is generic, not martingale-specific
5. **Configurable execution** — backtest TP/SL priority mode is user-selectable

## Architecture

```
Strategy (brain)
  │  calls: set_ticket_tp_sl(ticket_id, tp, sl)
  │  calls: set_all_tickets_tp_sl(tp, sl)
  │  calls: self.buy / self.sell / close_all_tickets()
  │  receives: on_ticket_tp_hit(), on_ticket_sl_hit()
  │
Engine (broker abstraction)
  │  ticket_service.check_ticket_triggers() — pure TP/SL logic
  │
  ├─ Backtest: simulator checks ticket TP/SL within candle walk
  └─ Live: submits TP/SL to broker via driver, syncs closures back
```

Strategy decides *what* (entries, exits, TP/SL levels, dynamic updates). Engine decides *how* (order routing, execution simulation, broker submission). Strategy doesn't know which mode it's running in.

## Data Model Changes

### CFDTicket

Add `tp_price` and `sl_price` fields:

```python
class CFDTicket:
    __slots__ = ('id', 'type', 'qty', 'entry_price', 'opened_at',
                 'exchange_trade_id', 'tp_price', 'sl_price')

    def __init__(self, ticket_type, qty, entry_price, opened_at):
        # ... existing fields ...
        self.tp_price = None    # Strategy sets, engine enforces
        self.sl_price = None    # Strategy sets, engine enforces
```

`to_dict()` updated to include `tp_price` and `sl_price`.

No other model changes. `Position`, `Order`, `CFDExchange` stay as-is.

## Strategy Base Class API

### New methods on `Strategy`

```python
def set_ticket_tp_sl(self, ticket_id: str, tp: float = None, sl: float = None):
    """Set or update TP/SL on a specific ticket. Works in backtest and live.

    - Finds ticket by ID in position._tickets
    - Sets ticket.tp_price and ticket.sl_price
    - In live mode: calls driver.set_trade_tp_sl(ticket.exchange_trade_id, tp, sl)
    - Passing None clears that side (e.g., tp=None removes TP, keeps SL)
    """

def set_all_tickets_tp_sl(self, tp: float = None, sl: float = None):
    """Convenience: set same TP/SL on all open tickets.

    Used by martingale strategies that recalculate TP after each hedge —
    all tickets share one session-level TP that moves.
    """
```

### New callbacks on `Strategy`

```python
def on_ticket_tp_hit(self, ticket: CFDTicket, fill_price: float):
    """Called by engine when a ticket's TP was triggered and the ticket was closed.
    Override to react (e.g., close remaining tickets to end a cycle).
    Default: no-op."""
    pass

def on_ticket_sl_hit(self, ticket: CFDTicket, fill_price: float):
    """Called by engine when a ticket's SL was triggered and the ticket was closed.
    Override to react (e.g., abort cycle, adjust risk).
    Default: no-op."""
    pass
```

These are called by the engine (both backtest and live), not by the strategy. The strategy overrides them to react.

### Existing methods — no changes

- `close_all_tickets(exit_price, meta)` — stays as-is
- `close_ticket(ticket_id, exit_price, meta)` — stays as-is
- `on_ticket_opened(order)` — stays as-is
- `on_ticket_closed(order)` — stays as-is

## Ticket Service

### `qengine/services/ticket_service.py`

Pure function, no engine dependencies. ~100 lines.

```python
def check_ticket_triggers(ticket, high, low, open_price, close_price, mode='ohlc_walk'):
    """Check if a ticket's TP or SL was hit within a candle.

    Args:
        ticket: CFDTicket with tp_price and/or sl_price set
        high: candle high price
        low: candle low price
        open_price: candle open price
        close_price: candle close price
        mode: 'ohlc_walk' or 'worst_case'

    Returns:
        None if no trigger, or dict:
        {'reason': 'tp' | 'sl', 'price': float}

    Modes:
        ohlc_walk:
            Green candle (close >= open): assume O → H → L → C
            Red candle (close < open): assume O → L → H → C
            Whichever TP/SL is hit first in that walk wins.

        worst_case:
            If both TP and SL could fire on same candle,
            pick the one worse for the trader (conservative).
            If only one fires, return that one.
    """
```

Logic details:
- Long ticket: TP fires when `high >= tp_price`, SL fires when `low <= sl_price`
- Short ticket: TP fires when `low <= tp_price`, SL fires when `high >= sl_price`
- If neither `tp_price` nor `sl_price` is set, returns `None`
- Fill price is the trigger price (TP or SL), not the candle close

## Engine Integration — Backtest Mode

### In `_simulate_price_change_effect()` (`backtest_mode.py`)

After the existing order execution loop and before liquidation checks, add ticket TP/SL checking:

```python
# After line 1123 (after order execution loop ends):

# Check ticket TP/SL triggers
_check_ticket_tp_sl_triggers(real_candle, exchange, symbol)

# Existing:
_check_for_liquidations(real_candle, exchange, symbol)
_check_for_margin_call(exchange, symbol)
```

### New function `_check_ticket_tp_sl_triggers()`

```python
def _check_ticket_tp_sl_triggers(real_candle, exchange, symbol):
    """Check all open tickets for TP/SL hits and close them."""
    p = store.positions.get_position(exchange, symbol)
    if not p or not p.is_cfd_mode or not p._tickets:
        return

    mode = config['app'].get('ticket_tp_sl_mode', 'ohlc_walk')
    high, low = real_candle[3], real_candle[4]
    open_price, close_price = real_candle[1], real_candle[2]

    # Iterate a copy — tickets may be removed during iteration
    for ticket in list(p._tickets):
        if ticket.tp_price is None and ticket.sl_price is None:
            continue

        result = ticket_service.check_ticket_triggers(
            ticket, high, low, open_price, close_price, mode=mode
        )
        if result is None:
            continue

        fill_price = result['price']
        reason = result['reason']

        # Close the ticket via position
        p.close_ticket(ticket.id, fill_price)

        # Record closed trade
        # (uses existing record_ticket_close infrastructure)

        # Fire strategy callback
        strategy = router.get_strategy(exchange, symbol)
        if reason == 'tp':
            strategy.on_ticket_tp_hit(ticket, fill_price)
        else:
            strategy.on_ticket_sl_hit(ticket, fill_price)
```

Ticket TP/SL checks participate in the same candle as order execution. They run after orders because orders (new hedges) may update TP/SL levels that should be checked on the *next* candle, not the current one.

## Engine Integration — Live Mode

### In `Strategy.set_ticket_tp_sl()`

```python
def set_ticket_tp_sl(self, ticket_id, tp=None, sl=None):
    ticket = self._find_ticket(ticket_id)
    if ticket is None:
        return

    ticket.tp_price = tp
    ticket.sl_price = sl

    # Live mode: submit to broker
    if jh.is_live() and ticket.exchange_trade_id:
        driver = self.broker.api
        if hasattr(driver, 'set_trade_tp_sl'):
            driver.set_trade_tp_sl(
                ticket.exchange_trade_id,
                take_profit=tp,
                stop_loss=sl
            )
```

Note: `is_live()` check is in the *engine layer* (`Strategy` base class), not in the concrete strategy. The concrete strategy (`UniversalMartingale`) never checks `is_live()`.

### In `_detect_per_trade_tp_sl_closures()` (`forex_live_mode.py`)

Extend existing function to fire the new callbacks:

```python
# After detecting a broker-side closure:
if ticket.tp_price and abs(fill_price - ticket.tp_price) < threshold:
    strategy.on_ticket_tp_hit(ticket, fill_price)
elif ticket.sl_price and abs(fill_price - ticket.sl_price) < threshold:
    strategy.on_ticket_sl_hit(ticket, fill_price)
else:
    # Broker closed for unknown reason (manual, margin, etc.)
    strategy.on_ticket_closed(ticket)
```

## Strategy Consolidation

### Keep: `UniversalMartingale`

Changes to `strategies/_admin/UniversalMartingale/__init__.py`:

1. **Track ticket IDs on legs:**
   ```python
   # In _execute_hedge() and initial entry, after order fills:
   leg['ticket_id'] = order.ticket_id  # or from on_ticket_opened
   ```

2. **Use engine TP/SL for applicable modes** (`fixed_pips`, `atr_based`, `risk_reward`):
   ```python
   # After opening any leg:
   tp = self._compute_tp(entry, direction)
   self.set_all_tickets_tp_sl(tp=tp)  # Engine enforces
   ```

3. **Keep manual checking** for `bucket_pct` and `trailing` modes — these are session-level checks that can't be expressed as per-ticket TP/SL:
   ```python
   # In update_position():
   if self.tp_mode in ('bucket_pct', 'trailing'):
       if self._check_tp():
           self._close_cycle('tp_hit')
   # For other modes, engine handles TP via ticket triggers
   ```

4. **Override callbacks:**
   ```python
   def on_ticket_tp_hit(self, ticket, fill_price):
       if self.vars['cycle_active']:
           self.close_all_tickets(exit_price=fill_price,
                                  meta={'exit_reason': 'tp_hit'})
           self._end_cycle('tp_hit')

   def on_ticket_sl_hit(self, ticket, fill_price):
       if self.vars['cycle_active']:
           self.close_all_tickets(exit_price=fill_price,
                                  meta={'exit_reason': 'sl_hit'})
           self._end_cycle('sl_hit')
   ```

5. **Remove manual TP price checking** for fixed/atr/rr modes from `_check_tp()` — engine does this now.

### Delete: `Surefire`, `SurefireV2`, `SFPilot`

- `Surefire` → replicated by `UniversalMartingale(preset='surefire_v1')`
- `SurefireV2` → replicated by `UniversalMartingale(preset='surefire_v2')`
- `SFPilot` → replicated by `UniversalMartingale` with pipeline integration

### Presets

All 10 existing presets remain unchanged. Behavior is identical — only the execution path changes (engine-enforced vs strategy-polled).

## Configuration

### New config option

```python
# In backtest config (config['app']):
'ticket_tp_sl_mode': 'ohlc_walk'   # default
# Options: 'ohlc_walk', 'worst_case'
```

- `ohlc_walk`: Green candle O→H→L→C, red candle O→L→H→C. First trigger wins.
- `worst_case`: If both TP and SL could fire, pick worse for trader.

Live mode ignores this — broker determines execution priority.

## Testing

### Layer 1: Unit tests — `tests/test_ticket_service.py` (~15 tests)

Pure `check_ticket_triggers()` logic, no engine:

- `test_tp_hit_long_ticket` — high >= tp_price triggers
- `test_tp_hit_short_ticket` — low <= tp_price triggers
- `test_sl_hit_long_ticket` — low <= sl_price triggers
- `test_sl_hit_short_ticket` — high >= sl_price triggers
- `test_no_trigger` — price in range, nothing fires
- `test_both_hit_ohlc_walk_green` — green candle priority
- `test_both_hit_ohlc_walk_red` — red candle priority
- `test_both_hit_worst_case` — pessimistic mode picks worse
- `test_tp_only_set` — SL is None, only TP checked
- `test_sl_only_set` — TP is None, only SL checked
- `test_neither_set` — both None, returns None
- `test_exact_price_touch` — price == tp_price triggers
- `test_gap_past_tp` — open gaps past TP, fills at TP price

### Layer 2: Integration tests — `tests/test_ticket_tp_sl_engine.py` (~10 tests)

Uses `research.backtest()` with synthetic candles:

- `test_ticket_tp_closes_at_correct_price` — verify fill price matches TP
- `test_ticket_sl_closes_at_correct_price` — verify fill price matches SL
- `test_tp_update_moves_trigger` — `set_ticket_tp_sl()` updates are respected
- `test_callback_fires_on_tp_hit` — `on_ticket_tp_hit` called
- `test_callback_fires_on_sl_hit` — `on_ticket_sl_hit` called
- `test_multiple_tickets_independent_tp` — each ticket has own TP
- `test_ohlc_walk_vs_worst_case_mode` — configurable mode works
- `test_backtest_matches_manual_check` — same results as old manual TP logic
- `test_non_cfd_mode_ignores_ticket_tp_sl` — futures/spot mode unaffected
- `test_no_tp_sl_set_no_trigger` — tickets without TP/SL are ignored

### Layer 3: Strategy tests — `tests/test_universal_martingale.py` (extend, ~12 new tests)

- `test_surefire_v1_preset_cycle_completes` — preset replicates V1 behavior
- `test_surefire_v2_preset_bucket_exit` — preset replicates V2 behavior
- `test_tp_recalculation_after_hedge` — TP moves when new leg added
- `test_all_tickets_close_on_tp_hit` — one ticket TP triggers full cycle close
- `test_hedge_and_tp_same_candle_priority` — dual-fire resolution
- `test_trailing_tp_mode_still_manual` — bucket/trailing bypass engine TP
- `test_preset_configs_load_correctly` — all 10 presets valid
- `test_on_ticket_tp_hit_ends_cycle` — callback fires and ends cycle
- `test_on_ticket_sl_hit_ends_cycle` — callback fires and ends cycle
- `test_ticket_id_tracked_on_legs` — legs store ticket_id
- `test_set_all_tickets_tp_sl_updates_all` — convenience method works
- `test_live_mode_submits_tp_to_broker` — mock driver, verify `set_trade_tp_sl` called

### Parity validation (one-time, pre-deletion)

Before deleting V1/V2/SFPilot:
1. Run each old strategy on a fixed candle set, capture all trades
2. Run UniversalMartingale with equivalent preset on same candles
3. Diff trade lists — must match (entry prices, exit prices, PnL, levels)

This is manual validation, not a permanent test.

## File Changes

### New files (3)

| File | Purpose | ~Lines |
|---|---|---|
| `qengine/services/ticket_service.py` | `check_ticket_triggers()` pure TP/SL logic | ~100 |
| `tests/test_ticket_service.py` | Unit tests for ticket_service | ~150 |
| `tests/test_ticket_tp_sl_engine.py` | Integration tests for engine ticket TP/SL | ~200 |

### Modified files (5)

| File | Change | ~Lines changed |
|---|---|---|
| `qengine/models/Position.py` | Add `tp_price`, `sl_price` to CFDTicket | ~10 |
| `qengine/strategies/Strategy.py` | Add `set_ticket_tp_sl()`, `set_all_tickets_tp_sl()`, `on_ticket_tp_hit()`, `on_ticket_sl_hit()` | ~60 |
| `qengine/modes/backtest_mode.py` | Add `_check_ticket_tp_sl_triggers()`, call it in `_simulate_price_change_effect()` | ~40 |
| `qengine/modes/forex_live_mode.py` | Fire `on_ticket_tp_hit`/`on_ticket_sl_hit` in `_detect_per_trade_tp_sl_closures()` | ~20 |
| `strategies/_admin/UniversalMartingale/__init__.py` | Use `set_ticket_tp_sl()`, add callbacks, track ticket_id on legs | ~80 |

### Extended test files (1)

| File | Change | ~Lines added |
|---|---|---|
| `tests/test_universal_martingale.py` | Parity + preset + callback tests | ~150 |

### Deleted files (3 directories)

| Path | Reason |
|---|---|
| `strategies/_admin/Surefire/` | Replaced by UniversalMartingale preset `surefire_v1` |
| `strategies/_admin/SurefireV2/` | Replaced by UniversalMartingale preset `surefire_v2` |
| `strategies/_admin/SFPilot/` | Replaced by UniversalMartingale with pipeline integration |

## Implementation Order

1. `ticket_service.py` + unit tests (standalone, no dependencies)
2. `CFDTicket` model changes (tiny, safe)
3. `Strategy.py` new API methods (additive, nothing breaks)
4. `backtest_mode.py` integration (wire ticket checks into simulator)
5. `forex_live_mode.py` callback wiring (extend existing sync)
6. `UniversalMartingale` refactor (use new API, add callbacks)
7. Integration + parity tests
8. Delete old strategies

Steps 1-3 are safe additions that break nothing. Step 4 is the core engine change. Steps 5-8 depend on 4.
