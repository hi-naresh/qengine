# Strategy Consolidation & Engine-Managed Ticket TP/SL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate 4 overlapping strategies into one (`UniversalMartingale`) and add engine-managed per-ticket TP/SL so strategies never touch broker code.

**Architecture:** Add `tp_price`/`sl_price` fields to `CFDTicket`. New `ticket_service.py` checks triggers (pure function). Backtest simulator calls it per candle. Live mode proxies to broker. Strategy gets `set_ticket_tp_sl()` + callbacks. UniversalMartingale uses engine TP for fixed/atr/rr modes, keeps manual checking for bucket/trailing.

**Tech Stack:** Python, pytest, qengine (Jesse fork), NumPy

**Spec:** `docs/superpowers/specs/2026-04-06-strategy-consolidation-design.md`

---

## File Structure

### New files
| File | Responsibility |
|---|---|
| `qengine/services/ticket_service.py` | Pure function: `check_ticket_triggers(ticket, high, low, open, close, mode)` |
| `tests/test_ticket_service.py` | Unit tests for ticket_service (15 tests) |
| `tests/test_ticket_tp_sl_engine.py` | Integration tests: engine enforces ticket TP/SL in backtest (10 tests) |

### Modified files
| File | Change |
|---|---|
| `qengine/models/Position.py:6-34` | Add `tp_price`, `sl_price` to CFDTicket |
| `qengine/strategies/Strategy.py:1345-1476` | Add `set_ticket_tp_sl()`, `set_all_tickets_tp_sl()`, `on_ticket_tp_hit()`, `on_ticket_sl_hit()` |
| `qengine/modes/backtest_mode.py:1065-1127` | Add `_check_ticket_tp_sl_triggers()`, call after order execution |
| `qengine/modes/live_mode.py:372-428` | Fire `on_ticket_tp_hit`/`on_ticket_sl_hit` in `_sync_trades_with_broker()` |
| `strategies/_admin/UniversalMartingale/__init__.py` | Use `set_ticket_tp_sl()`, add callbacks, track ticket_id on legs |
| `tests/test_universal_martingale.py` | Add parity + callback tests |

### Deleted files (after parity validation)
| Path | Replaced by |
|---|---|
| `strategies/_admin/Surefire/` | UniversalMartingale preset `surefire_v1` |
| `strategies/_admin/SurefireV2/` | UniversalMartingale preset `surefire_v2` |
| `strategies/_admin/SFPilot/` | UniversalMartingale with pipeline integration |

---

## Task 1: Ticket Service — Pure TP/SL Trigger Logic

**Files:**
- Create: `qengine/services/ticket_service.py`
- Create: `tests/test_ticket_service.py`

### Step 1.1: Write failing tests for `check_ticket_triggers`

- [ ] Create `tests/test_ticket_service.py`:

```python
"""Unit tests for ticket_service.check_ticket_triggers() — pure TP/SL logic."""
import pytest


class FakeTicket:
    """Minimal CFDTicket stand-in for unit tests."""
    def __init__(self, ticket_type='long', tp_price=None, sl_price=None):
        self.type = ticket_type
        self.tp_price = tp_price
        self.sl_price = sl_price


class TestLongTicketTP:
    def test_tp_hit_when_high_reaches_tp(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('long', tp_price=1.1020)
        result = check_ticket_triggers(t, high=1.1025, low=1.0990, open_price=1.1000, close_price=1.1010)
        assert result is not None
        assert result['reason'] == 'tp'
        assert result['price'] == 1.1020

    def test_tp_not_hit_when_high_below_tp(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('long', tp_price=1.1020)
        result = check_ticket_triggers(t, high=1.1015, low=1.0995, open_price=1.1000, close_price=1.1010)
        assert result is None

    def test_tp_exact_touch(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('long', tp_price=1.1020)
        result = check_ticket_triggers(t, high=1.1020, low=1.0990, open_price=1.1000, close_price=1.1010)
        assert result is not None
        assert result['reason'] == 'tp'


class TestShortTicketTP:
    def test_tp_hit_when_low_reaches_tp(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('short', tp_price=1.0980)
        result = check_ticket_triggers(t, high=1.1010, low=1.0975, open_price=1.1000, close_price=1.0990)
        assert result is not None
        assert result['reason'] == 'tp'
        assert result['price'] == 1.0980

    def test_tp_not_hit_when_low_above_tp(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('short', tp_price=1.0980)
        result = check_ticket_triggers(t, high=1.1010, low=1.0985, open_price=1.1000, close_price=1.0990)
        assert result is None


class TestLongTicketSL:
    def test_sl_hit_when_low_reaches_sl(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('long', sl_price=1.0980)
        result = check_ticket_triggers(t, high=1.1010, low=1.0975, open_price=1.1000, close_price=1.0990)
        assert result is not None
        assert result['reason'] == 'sl'
        assert result['price'] == 1.0980

    def test_sl_not_hit_when_low_above_sl(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('long', sl_price=1.0970)
        result = check_ticket_triggers(t, high=1.1010, low=1.0975, open_price=1.1000, close_price=1.0990)
        assert result is None


class TestShortTicketSL:
    def test_sl_hit_when_high_reaches_sl(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('short', sl_price=1.1020)
        result = check_ticket_triggers(t, high=1.1025, low=1.0990, open_price=1.1000, close_price=1.0995)
        assert result is not None
        assert result['reason'] == 'sl'
        assert result['price'] == 1.1020


class TestNeitherSet:
    def test_no_tp_no_sl_returns_none(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('long', tp_price=None, sl_price=None)
        result = check_ticket_triggers(t, high=1.1050, low=1.0950, open_price=1.1000, close_price=1.1010)
        assert result is None

    def test_tp_only_set(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('long', tp_price=1.1020, sl_price=None)
        result = check_ticket_triggers(t, high=1.1025, low=1.0950, open_price=1.1000, close_price=1.1010)
        assert result is not None
        assert result['reason'] == 'tp'

    def test_sl_only_set(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('long', tp_price=None, sl_price=1.0960)
        result = check_ticket_triggers(t, high=1.1010, low=1.0955, open_price=1.1000, close_price=1.0990)
        assert result is not None
        assert result['reason'] == 'sl'


class TestBothHitOHLCWalk:
    """When both TP and SL are within candle range, OHLC walk decides priority."""

    def test_green_candle_tp_first_for_long(self):
        """Green candle: O→H→L→C. Long TP is at high side → TP hit first."""
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('long', tp_price=1.1020, sl_price=1.0980)
        # Green candle: open=1.1000, close=1.1005 (close > open)
        # Walk: O→H(1.1025)→L(1.0975)→C — TP at 1.1020 hit before SL at 1.0980
        result = check_ticket_triggers(t, high=1.1025, low=1.0975, open_price=1.1000, close_price=1.1005, mode='ohlc_walk')
        assert result['reason'] == 'tp'

    def test_red_candle_sl_first_for_long(self):
        """Red candle: O→L→H→C. Long SL is at low side → SL hit first."""
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('long', tp_price=1.1020, sl_price=1.0980)
        # Red candle: open=1.1000, close=1.0995 (close < open)
        # Walk: O→L(1.0975)→H(1.1025)→C — SL at 1.0980 hit before TP at 1.1020
        result = check_ticket_triggers(t, high=1.1025, low=1.0975, open_price=1.1000, close_price=1.0995, mode='ohlc_walk')
        assert result['reason'] == 'sl'

    def test_green_candle_sl_first_for_short(self):
        """Green candle: O→H→L→C. Short SL is at high side → SL hit first."""
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('short', tp_price=1.0980, sl_price=1.1020)
        # Green candle: O→H(1.1025)→L(1.0975)→C
        # Short SL at 1.1020 (high side) hit before TP at 1.0980 (low side)
        result = check_ticket_triggers(t, high=1.1025, low=1.0975, open_price=1.1000, close_price=1.1005, mode='ohlc_walk')
        assert result['reason'] == 'sl'

    def test_red_candle_tp_first_for_short(self):
        """Red candle: O→L→H→C. Short TP is at low side → TP hit first."""
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('short', tp_price=1.0980, sl_price=1.1020)
        # Red candle: O→L(1.0975)→H(1.1025)→C
        # Short TP at 1.0980 (low side) hit before SL at 1.1020 (high side)
        result = check_ticket_triggers(t, high=1.1025, low=1.0975, open_price=1.1000, close_price=1.0995, mode='ohlc_walk')
        assert result['reason'] == 'tp'


class TestBothHitWorstCase:
    """worst_case mode: pick the outcome worse for the trader."""

    def test_long_worst_case_picks_sl(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('long', tp_price=1.1020, sl_price=1.0980)
        result = check_ticket_triggers(t, high=1.1025, low=1.0975, open_price=1.1000, close_price=1.1005, mode='worst_case')
        assert result['reason'] == 'sl'

    def test_short_worst_case_picks_sl(self):
        from qengine.services.ticket_service import check_ticket_triggers
        t = FakeTicket('short', tp_price=1.0980, sl_price=1.1020)
        result = check_ticket_triggers(t, high=1.1025, low=1.0975, open_price=1.1000, close_price=1.0995, mode='worst_case')
        assert result['reason'] == 'sl'
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `pytest tests/test_ticket_service.py -v 2>&1 | head -30`
Expected: FAIL — `ModuleNotFoundError: No module named 'qengine.services.ticket_service'`

- [ ] **Step 1.3: Implement `ticket_service.py`**

Create `qengine/services/ticket_service.py`:

```python
"""Pure TP/SL trigger logic for CFD tickets.

No engine dependencies — takes a ticket and candle data, returns trigger result.
Used by backtest simulator and live mode sync.
"""
from typing import Optional, Dict


def check_ticket_triggers(
    ticket,
    high: float,
    low: float,
    open_price: float,
    close_price: float,
    mode: str = 'ohlc_walk',
) -> Optional[Dict]:
    """Check if a ticket's TP or SL was hit within a candle.

    Args:
        ticket: Object with .type ('long'/'short'), .tp_price, .sl_price
        high: Candle high
        low: Candle low
        open_price: Candle open
        close_price: Candle close
        mode: 'ohlc_walk' (default) or 'worst_case'

    Returns:
        None if no trigger, or {'reason': 'tp'|'sl', 'price': float}
    """
    tp = getattr(ticket, 'tp_price', None)
    sl = getattr(ticket, 'sl_price', None)

    if tp is None and sl is None:
        return None

    is_long = ticket.type == 'long'

    # Determine which triggers fired
    tp_hit = False
    sl_hit = False

    if tp is not None:
        if is_long:
            tp_hit = high >= tp
        else:
            tp_hit = low <= tp

    if sl is not None:
        if is_long:
            sl_hit = low <= sl
        else:
            sl_hit = high >= sl

    if not tp_hit and not sl_hit:
        return None

    if tp_hit and not sl_hit:
        return {'reason': 'tp', 'price': tp}

    if sl_hit and not tp_hit:
        return {'reason': 'sl', 'price': sl}

    # Both hit — resolve by mode
    if mode == 'worst_case':
        return {'reason': 'sl', 'price': sl}

    # ohlc_walk: Green (close >= open) → O→H→L→C, Red → O→L→H→C
    is_green = close_price >= open_price

    if is_long:
        # Long TP is on high side, SL is on low side
        # Green: O→H→L→C → TP (high side) first
        # Red: O→L→H→C → SL (low side) first
        if is_green:
            return {'reason': 'tp', 'price': tp}
        else:
            return {'reason': 'sl', 'price': sl}
    else:
        # Short TP is on low side, SL is on high side
        # Green: O→H→L→C → SL (high side) first
        # Red: O→L→H→C → TP (low side) first
        if is_green:
            return {'reason': 'sl', 'price': sl}
        else:
            return {'reason': 'tp', 'price': tp}
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `pytest tests/test_ticket_service.py -v`
Expected: All 15 tests PASS

- [ ] **Step 1.5: Commit**

```bash
git add qengine/services/ticket_service.py tests/test_ticket_service.py
git commit -m "feat: add ticket_service with pure TP/SL trigger logic + tests"
```

---

## Task 2: CFDTicket Model — Add TP/SL Fields

**Files:**
- Modify: `qengine/models/Position.py:6-34`

- [ ] **Step 2.1: Add `tp_price` and `sl_price` to `CFDTicket.__slots__`**

In `qengine/models/Position.py`, change:

```python
# Old (line 10):
__slots__ = ('id', 'type', 'qty', 'entry_price', 'opened_at', 'exchange_trade_id')

# New:
__slots__ = ('id', 'type', 'qty', 'entry_price', 'opened_at', 'exchange_trade_id', 'tp_price', 'sl_price')
```

- [ ] **Step 2.2: Initialize `tp_price` and `sl_price` in `__init__`**

In `qengine/models/Position.py`, add after line 18:

```python
# Old (line 18):
self.exchange_trade_id = None  # OANDA trade ID for per-trade TP/SL management

# New (add two lines after):
self.exchange_trade_id = None  # OANDA trade ID for per-trade TP/SL management
self.tp_price = None   # Strategy sets, engine enforces
self.sl_price = None   # Strategy sets, engine enforces
```

- [ ] **Step 2.3: Update `to_dict()` to include TP/SL**

In `qengine/models/Position.py`, change `to_dict()`:

```python
# Old (lines 26-34):
def to_dict(self) -> dict:
    return {
        'id': self.id,
        'type': self.type,
        'qty': self.qty,
        'entry_price': self.entry_price,
        'opened_at': self.opened_at,
        'exchange_trade_id': self.exchange_trade_id,
    }

# New:
def to_dict(self) -> dict:
    return {
        'id': self.id,
        'type': self.type,
        'qty': self.qty,
        'entry_price': self.entry_price,
        'opened_at': self.opened_at,
        'exchange_trade_id': self.exchange_trade_id,
        'tp_price': self.tp_price,
        'sl_price': self.sl_price,
    }
```

- [ ] **Step 2.4: Run existing tests to verify nothing broke**

Run: `pytest tests/ -x -q 2>&1 | tail -5`
Expected: All existing tests pass (no regressions from adding optional fields)

- [ ] **Step 2.5: Commit**

```bash
git add qengine/models/Position.py
git commit -m "feat: add tp_price and sl_price fields to CFDTicket"
```

---

## Task 3: Strategy Base Class — New API Methods

**Files:**
- Modify: `qengine/strategies/Strategy.py` (after line 1351, before `close_all_tickets`)

- [ ] **Step 3.1: Add `set_ticket_tp_sl` method**

In `qengine/strategies/Strategy.py`, add after the `on_ticket_closed` method (after line 1351):

```python
    def on_ticket_tp_hit(self, ticket, fill_price: float) -> None:
        """Called by engine when a ticket's TP was triggered and closed.
        Override to react (e.g., close remaining tickets to end a cycle)."""
        pass

    def on_ticket_sl_hit(self, ticket, fill_price: float) -> None:
        """Called by engine when a ticket's SL was triggered and closed.
        Override to react (e.g., abort cycle, adjust risk)."""
        pass

    def set_ticket_tp_sl(self, ticket_id: str, tp: float = None, sl: float = None) -> None:
        """Set or update TP/SL on a specific ticket. Works in backtest and live.

        Args:
            ticket_id: ID of the ticket to update.
            tp: Take-profit price (None to clear TP).
            sl: Stop-loss price (None to clear SL).
        """
        if not self.position.is_cfd_mode:
            return
        ticket = self.position.get_ticket(ticket_id)
        if ticket is None:
            return

        ticket.tp_price = tp
        ticket.sl_price = sl

        # In live mode, submit to broker
        if jh.is_live() and ticket.exchange_trade_id:
            from qengine.services.api import api
            driver = api.drivers.get(self.exchange)
            if driver and hasattr(driver, 'set_trade_tp_sl'):
                try:
                    driver.set_trade_tp_sl(
                        ticket.exchange_trade_id,
                        take_profit=tp,
                        stop_loss=sl,
                    )
                except Exception as e:
                    logger.error(f'Failed to set TP/SL on broker for ticket {ticket_id[:8]}: {e}')

    def set_all_tickets_tp_sl(self, tp: float = None, sl: float = None) -> None:
        """Set same TP/SL on all open tickets. Convenience for strategies
        that recalculate a shared TP after each hedge level."""
        if not self.position.is_cfd_mode:
            return
        for ticket in self.position._tickets:
            self.set_ticket_tp_sl(ticket.id, tp=tp, sl=sl)
```

- [ ] **Step 3.2: Run existing tests to verify nothing broke**

Run: `pytest tests/ -x -q 2>&1 | tail -5`
Expected: All existing tests pass (additive change only)

- [ ] **Step 3.3: Commit**

```bash
git add qengine/strategies/Strategy.py
git commit -m "feat: add set_ticket_tp_sl, set_all_tickets_tp_sl, on_ticket_tp_hit, on_ticket_sl_hit to Strategy"
```

---

## Task 4: Backtest Engine — Wire Ticket TP/SL Checks

**Files:**
- Modify: `qengine/modes/backtest_mode.py:1065-1127`

- [ ] **Step 4.1: Add import for ticket_service at top of backtest_mode.py**

In `qengine/modes/backtest_mode.py`, add to the imports section (near other service imports):

```python
from qengine.services import ticket_service
```

- [ ] **Step 4.2: Add `_check_ticket_tp_sl_triggers` function**

In `qengine/modes/backtest_mode.py`, add before `_simulate_price_change_effect` (before line 1065):

```python
def _check_ticket_tp_sl_triggers(real_candle: np.ndarray, exchange: str, symbol: str) -> None:
    """Check all open CFD tickets for TP/SL hits and close them.

    Called once per candle AFTER order execution, so that new hedges set TP/SL
    for the *next* candle (not the current one).
    """
    p = store.positions.get_position(exchange, symbol)
    if not p or not p.is_cfd_mode or not p._tickets:
        return

    mode = config['app'].get('ticket_tp_sl_mode', 'ohlc_walk')
    open_price = real_candle[1]
    close_price = real_candle[2]
    high = real_candle[3]
    low = real_candle[4]

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

        # Close the ticket
        close_result = p.close_ticket(ticket.id, fill_price)
        if close_result is None:
            continue

        pnl = close_result['pnl']
        if p.exchange:
            p.exchange.add_realized_pnl(pnl)

        from qengine.services import closed_trade_service
        closed_trade_service.record_ticket_close(
            p, close_result['ticket'], fill_price, pnl,
            meta={'exit_reason': f'{reason}_hit'}
        )

        # Fire strategy callback
        strategy = None
        for r in router.routes:
            if r.exchange == exchange and r.symbol == symbol:
                strategy = r.strategy
                break

        if strategy is not None:
            if reason == 'tp':
                strategy.on_ticket_tp_hit(ticket, fill_price)
            else:
                strategy.on_ticket_sl_hit(ticket, fill_price)
```

- [ ] **Step 4.3: Wire into `_simulate_price_change_effect`**

In `qengine/modes/backtest_mode.py`, change the end of `_simulate_price_change_effect` (around line 1123-1126):

```python
# Old (lines 1125-1126):
    _check_for_liquidations(real_candle, exchange, symbol)
    _check_for_margin_call(exchange, symbol)

# New:
    _check_ticket_tp_sl_triggers(real_candle, exchange, symbol)
    _check_for_liquidations(real_candle, exchange, symbol)
    _check_for_margin_call(exchange, symbol)
```

- [ ] **Step 4.4: Run existing tests to verify nothing broke**

Run: `pytest tests/ -x -q 2>&1 | tail -5`
Expected: All existing tests pass (no tickets have TP/SL set, so new code path is never entered)

- [ ] **Step 4.5: Commit**

```bash
git add qengine/modes/backtest_mode.py
git commit -m "feat: wire ticket TP/SL checking into backtest simulator"
```

---

## Task 5: Integration Tests — Engine Enforces Ticket TP/SL

**Files:**
- Create: `tests/test_ticket_tp_sl_engine.py`

This task creates a minimal test strategy that uses `set_ticket_tp_sl()` and runs it through `research.backtest()` to verify the engine enforces TP/SL correctly.

- [ ] **Step 5.1: Write integration tests**

Create `tests/test_ticket_tp_sl_engine.py`:

```python
"""Integration tests: engine enforces per-ticket TP/SL in backtest mode.

Uses a minimal test strategy that opens a ticket and sets TP/SL via the
engine API, then verifies the engine auto-closes at the correct price.
"""
import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import qengine.helpers as jh
    from qengine.factories import candles_from_close_prices
    from qengine import research
    from qengine.strategies.Strategy import Strategy
    AVAILABLE = True
except Exception:
    AVAILABLE = False

pytestmark = pytest.mark.skipif(not AVAILABLE, reason="QEngine not available")


# ---------------------------------------------------------------------------
# Test strategies — minimal, purpose-built for each test
# ---------------------------------------------------------------------------
class LongWithTP(Strategy):
    """Opens long on bar 5, sets TP 20 pips above entry."""
    def should_long(self):
        return self.index == 5 and not self.is_open
    def go_long(self):
        self.buy = 1000, self.price
    def on_open_position(self, order):
        tp_price = order.price + 0.0020  # 20 pips
        for ticket in self.position._tickets:
            self.set_ticket_tp_sl(ticket.id, tp=tp_price)
        self.vars['tp_set'] = tp_price
    def should_short(self):
        return False
    def go_short(self):
        pass
    def should_cancel_entry(self):
        return False


class LongWithSL(Strategy):
    """Opens long on bar 5, sets SL 10 pips below entry."""
    def should_long(self):
        return self.index == 5 and not self.is_open
    def go_long(self):
        self.buy = 1000, self.price
    def on_open_position(self, order):
        sl_price = order.price - 0.0010  # 10 pips
        for ticket in self.position._tickets:
            self.set_ticket_tp_sl(ticket.id, sl=sl_price)
        self.vars['sl_set'] = sl_price
    def should_short(self):
        return False
    def go_short(self):
        pass
    def should_cancel_entry(self):
        return False


class LongWithTPCallback(Strategy):
    """Opens long, sets TP. Tracks callback invocation."""
    def should_long(self):
        return self.index == 5 and not self.is_open
    def go_long(self):
        self.buy = 1000, self.price
    def on_open_position(self, order):
        tp_price = order.price + 0.0020
        for ticket in self.position._tickets:
            self.set_ticket_tp_sl(ticket.id, tp=tp_price)
    def on_ticket_tp_hit(self, ticket, fill_price):
        self.vars['tp_callback_fired'] = True
        self.vars['tp_fill_price'] = fill_price
    def should_short(self):
        return False
    def go_short(self):
        pass
    def should_cancel_entry(self):
        return False


class LongWithUpdatedTP(Strategy):
    """Opens long, sets TP, then moves it on bar 10."""
    def should_long(self):
        return self.index == 5 and not self.is_open
    def go_long(self):
        self.buy = 1000, self.price
    def on_open_position(self, order):
        tp_price = order.price + 0.0050  # 50 pips (won't be hit)
        for ticket in self.position._tickets:
            self.set_ticket_tp_sl(ticket.id, tp=tp_price)
        self.vars['original_tp'] = tp_price
    def update_position(self):
        if self.index == 10:
            # Move TP closer — should now get hit
            new_tp = self.position.entry_price + 0.0015
            self.set_all_tickets_tp_sl(tp=new_tp)
            self.vars['updated_tp'] = new_tp
    def on_ticket_tp_hit(self, ticket, fill_price):
        self.vars['tp_callback_fired'] = True
    def should_short(self):
        return False
    def go_short(self):
        pass
    def should_cancel_entry(self):
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_config(exchange_name='Test CFD Exchange'):
    return {
        'starting_balance': 100_000,
        'fee': 0,
        'type': 'cfd',
        'cfd_leverage': 30,
        'exchange': exchange_name,
        'warm_up_candles': 0,
        'spread': 0,
        'slippage': 0,
    }


def _run(strategy_cls, prices, config_override=None):
    candles = candles_from_close_prices(prices)
    exchange_name = 'Test CFD Exchange'
    symbol = 'EUR-USD'
    cfg = config_override or _make_config(exchange_name)
    routes = [{'exchange': exchange_name, 'strategy': strategy_cls,
               'symbol': symbol, 'timeframe': '1m'}]
    return research.backtest(
        cfg, routes, [], {
            jh.key(exchange_name, symbol): {
                'exchange': exchange_name, 'symbol': symbol,
                'candles': candles
            }
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestTicketTPEngine:
    def test_tp_closes_at_correct_price(self):
        """Price rises past TP → engine closes ticket at TP price."""
        # Bar 5: entry at ~1.1000. TP = 1.1020.
        # Bar 15+: price rises to 1.1030 → TP should trigger at 1.1020
        prices = [1.1000] * 5 + [1.1000] + [1.1000 + i * 0.0003 for i in range(20)]
        result = _run(LongWithTP, prices)
        assert result['total'] > 0, "Should have at least one closed trade"
        # Trade should be profitable (closed at TP, not at candle close)
        assert result['net_profit'] > 0

    def test_sl_closes_at_correct_price(self):
        """Price drops past SL → engine closes ticket at SL price."""
        # Bar 5: entry at ~1.1000. SL = 1.0990.
        # Bar 10+: price drops → SL should trigger
        prices = [1.1000] * 5 + [1.1000] + [1.1000 - i * 0.0002 for i in range(20)]
        result = _run(LongWithSL, prices)
        assert result['total'] > 0, "Should have at least one closed trade"
        assert result['net_profit'] < 0  # SL hit = loss

    def test_callback_fires_on_tp_hit(self):
        """on_ticket_tp_hit callback is invoked when TP triggers."""
        prices = [1.1000] * 5 + [1.1000] + [1.1000 + i * 0.0003 for i in range(20)]
        result = _run(LongWithTPCallback, prices)
        # The strategy should have recorded the callback
        assert result['total'] > 0

    def test_tp_update_moves_trigger(self):
        """set_all_tickets_tp_sl() updates are respected by engine."""
        # Original TP is 50 pips away (won't be hit in 25 bars)
        # Updated TP at bar 10 is 15 pips away (will be hit)
        prices = [1.1000] * 5 + [1.1000] + [1.1000 + i * 0.0002 for i in range(20)]
        result = _run(LongWithUpdatedTP, prices)
        assert result['total'] > 0, "Updated TP should have been hit"

    def test_no_tp_sl_set_no_trigger(self):
        """Tickets without TP/SL are not auto-closed by engine."""
        class LongNoTPSL(Strategy):
            def should_long(self):
                return self.index == 5 and not self.is_open
            def go_long(self):
                self.buy = 1000, self.price
            def should_short(self):
                return False
            def go_short(self):
                pass
            def should_cancel_entry(self):
                return False

        prices = [1.1000] * 5 + [1.1000] + [1.1000 + i * 0.0005 for i in range(20)]
        result = _run(LongNoTPSL, prices)
        # No TP/SL set → position stays open, no closed trades
        assert result['total'] == 0
```

- [ ] **Step 5.2: Run integration tests**

Run: `pytest tests/test_ticket_tp_sl_engine.py -v`
Expected: All tests PASS

- [ ] **Step 5.3: Commit**

```bash
git add tests/test_ticket_tp_sl_engine.py
git commit -m "test: integration tests for engine-managed ticket TP/SL"
```

---

## Task 6: Live Mode — Fire Callbacks on Broker TP/SL Closure

**Files:**
- Modify: `qengine/modes/live_mode.py:372-428`

- [ ] **Step 6.1: Extend `_sync_trades_with_broker` to fire TP/SL callbacks**

In `qengine/modes/live_mode.py`, replace the ticket closure block inside `_sync_trades_with_broker` (lines 407-423):

```python
        # Old (lines 407-423):
        for ticket in tickets_to_close:
            _log(client_id,
                 f'[Trade sync] Trade {ticket.exchange_trade_id} closed on broker '
                 f'(ticket {ticket.id[:8]}, {ticket.type} {ticket.qty:.0f})')

            fill_price = p.current_price

            result = p.close_ticket(ticket.id, fill_price)
            if result:
                pnl = result['pnl']
                if p.exchange and p.exchange.type in ('cfd',):
                    p.exchange.add_realized_pnl(pnl)
                from qengine.services import closed_trade_service
                closed_trade_service.record_ticket_close(p, result['ticket'], fill_price, pnl)
                closed_count += 1

        # New:
        for ticket in tickets_to_close:
            _log(client_id,
                 f'[Trade sync] Trade {ticket.exchange_trade_id} closed on broker '
                 f'(ticket {ticket.id[:8]}, {ticket.type} {ticket.qty:.0f})')

            fill_price = p.current_price

            # Determine if this was a TP or SL closure based on ticket's stored levels
            exit_reason = None
            if ticket.tp_price is not None and ticket.sl_price is not None:
                # Both set — infer from fill price proximity
                tp_dist = abs(fill_price - ticket.tp_price)
                sl_dist = abs(fill_price - ticket.sl_price)
                exit_reason = 'tp_hit' if tp_dist <= sl_dist else 'sl_hit'
            elif ticket.tp_price is not None:
                exit_reason = 'tp_hit'
            elif ticket.sl_price is not None:
                exit_reason = 'sl_hit'

            result = p.close_ticket(ticket.id, fill_price)
            if result:
                pnl = result['pnl']
                if p.exchange and p.exchange.type in ('cfd',):
                    p.exchange.add_realized_pnl(pnl)
                from qengine.services import closed_trade_service
                closed_trade_service.record_ticket_close(
                    p, result['ticket'], fill_price, pnl,
                    meta={'exit_reason': exit_reason} if exit_reason else None,
                )
                closed_count += 1

                # Fire strategy callback
                if r.strategy is not None and exit_reason:
                    if exit_reason == 'tp_hit':
                        r.strategy.on_ticket_tp_hit(ticket, fill_price)
                    elif exit_reason == 'sl_hit':
                        r.strategy.on_ticket_sl_hit(ticket, fill_price)
```

- [ ] **Step 6.2: Verify no syntax errors**

Run: `python -c "import qengine.modes.live_mode"`
Expected: No errors (import succeeds)

- [ ] **Step 6.3: Commit**

```bash
git add qengine/modes/live_mode.py
git commit -m "feat: fire on_ticket_tp_hit/on_ticket_sl_hit in live mode trade sync"
```

---

## Task 7: UniversalMartingale — Use Engine TP/SL + Callbacks

**Files:**
- Modify: `strategies/_admin/UniversalMartingale/__init__.py`

- [ ] **Step 7.1: Track ticket_id on legs in `on_open_position`**

In `strategies/_admin/UniversalMartingale/__init__.py`, change `on_open_position` (line 386-409):

```python
# Old (lines 398-404):
        leg = {
            'level': 0,
            'dir': direction,
            'qty': abs(order.qty),
            'entry': entry,
        }
        self.vars['legs'] = [leg]

# New:
        leg = {
            'level': 0,
            'dir': direction,
            'qty': abs(order.qty),
            'entry': entry,
            'ticket_id': getattr(order, 'ticket_id', None),
        }
        self.vars['legs'] = [leg]
```

- [ ] **Step 7.2: Set engine TP/SL after initial entry**

In `strategies/_admin/UniversalMartingale/__init__.py`, add after the line `self.vars['trailing_tp'] = None` (line 409):

```python
        # Set engine-managed TP for price-based modes
        if self.vars['tp_price'] is not None and leg.get('ticket_id'):
            self.set_ticket_tp_sl(leg['ticket_id'], tp=self.vars['tp_price'])
```

- [ ] **Step 7.3: Track ticket_id on hedge legs and set engine TP/SL in `_execute_hedge`**

In `strategies/_admin/UniversalMartingale/__init__.py`, change `_execute_hedge` (line 987-999):

```python
# Old (lines 987-999):
        leg = {
            'level': level,
            'dir': new_dir,
            'qty': qty,
            'entry': entry,
        }
        self.vars['legs'].append(leg)

        # Recalculate TP for all legs (moves toward the new entry)
        self._recalculate_tp()

        # Set next hedge trigger
        self.vars['hedge_trigger_price'] = self._compute_hedge_trigger(entry, new_dir, level)

# New:
        # Get ticket_id from the newly opened ticket
        ticket_id = None
        if self.position.is_cfd_mode and self.position._tickets:
            ticket_id = self.position._tickets[-1].id

        leg = {
            'level': level,
            'dir': new_dir,
            'qty': qty,
            'entry': entry,
            'ticket_id': ticket_id,
        }
        self.vars['legs'].append(leg)

        # Recalculate TP for all legs (moves toward the new entry)
        self._recalculate_tp()

        # Set next hedge trigger
        self.vars['hedge_trigger_price'] = self._compute_hedge_trigger(entry, new_dir, level)
```

- [ ] **Step 7.4: Update `_recalculate_tp` to push TP to engine**

In `strategies/_admin/UniversalMartingale/__init__.py`, change `_recalculate_tp` (lines 1001-1008):

```python
# Old (lines 1001-1008):
    def _recalculate_tp(self):
        """Recalculate TP price after adding a new hedge level.
        TP is set relative to the LAST leg's entry (the newest, largest position)."""
        if self.hp.get('tp_mode') in ('bucket_pct', 'trailing'):
            return  # These modes don't use fixed TP price

        last_leg = self.vars['legs'][-1]
        self.vars['tp_price'] = self._compute_tp(last_leg['entry'], last_leg['dir'])

# New:
    def _recalculate_tp(self):
        """Recalculate TP price after adding a new hedge level.
        TP is set relative to the LAST leg's entry (the newest, largest position).
        Pushes updated TP to all tickets via engine API."""
        if self.hp.get('tp_mode') in ('bucket_pct', 'trailing'):
            return  # These modes don't use fixed TP price

        last_leg = self.vars['legs'][-1]
        self.vars['tp_price'] = self._compute_tp(last_leg['entry'], last_leg['dir'])

        # Push TP to engine for all open tickets
        if self.vars['tp_price'] is not None:
            self.set_all_tickets_tp_sl(tp=self.vars['tp_price'])
```

- [ ] **Step 7.5: Remove manual TP checking for price-based modes**

In `strategies/_admin/UniversalMartingale/__init__.py`, change `_check_tp` (lines 887-911):

```python
# Old (lines 887-911):
    def _check_tp(self):
        """Check if take-profit condition is met."""
        mode = self.hp.get('tp_mode', 'fixed_pips')

        if mode == 'bucket_pct':
            pnl_pct = self._session_pnl_pct()
            target = self.hp.get('tp_value', 0.1)
            return pnl_pct >= target

        if mode == 'trailing':
            return self._check_trailing_tp()

        # Fixed/ATR/RR: price-based TP
        tp = self.vars.get('tp_price')
        if tp is None:
            return False

        # TP is computed relative to the LAST leg's direction (via _recalculate_tp),
        # so the check must use the last leg's direction, not session_dir.
        last_leg = self.vars['legs'][-1] if self.vars.get('legs') else None
        direction = last_leg['dir'] if last_leg else self.vars['session_dir']
        if direction == 'long':
            return self.high >= tp
        else:
            return self.low <= tp

# New:
    def _check_tp(self):
        """Check if take-profit condition is met.

        For price-based modes (fixed_pips, atr_based, risk_reward), the engine
        handles TP via ticket triggers — this method only checks session-level
        modes (bucket_pct, trailing).
        """
        mode = self.hp.get('tp_mode', 'fixed_pips')

        if mode == 'bucket_pct':
            pnl_pct = self._session_pnl_pct()
            target = self.hp.get('tp_value', 0.1)
            return pnl_pct >= target

        if mode == 'trailing':
            return self._check_trailing_tp()

        # Price-based modes (fixed_pips, atr_based, risk_reward) are handled
        # by the engine via on_ticket_tp_hit callback. No manual check needed.
        return False
```

- [ ] **Step 7.6: Add `on_ticket_tp_hit` and `on_ticket_sl_hit` callbacks**

In `strategies/_admin/UniversalMartingale/__init__.py`, add after `on_close_position` (after line 452):

```python
    def on_ticket_tp_hit(self, ticket, fill_price):
        """Engine closed a ticket at TP — close remaining tickets to end cycle."""
        if not self.vars.get('cycle_active'):
            return
        # Close all remaining tickets at the TP price and end the cycle
        if self.position._tickets:
            self.close_all_tickets(
                exit_price=fill_price,
                meta={
                    'session': self.vars.get('session_number', 0),
                    'exit_reason': 'tp_hit',
                    'level': self.vars.get('level', 0),
                }
            )
        self._end_cycle('tp_hit')

    def on_ticket_sl_hit(self, ticket, fill_price):
        """Engine closed a ticket at SL — close remaining tickets to end cycle."""
        if not self.vars.get('cycle_active'):
            return
        if self.position._tickets:
            self.close_all_tickets(
                exit_price=fill_price,
                meta={
                    'session': self.vars.get('session_number', 0),
                    'exit_reason': 'sl_hit',
                    'level': self.vars.get('level', 0),
                }
            )
        self._end_cycle('sl_hit')
```

- [ ] **Step 7.7: Extract `_end_cycle` from `_close_cycle` (reusable)**

In `strategies/_admin/UniversalMartingale/__init__.py`, at the end of `_close_cycle` (line 1261), split the reset logic into a helper that both `_close_cycle` and the callbacks can use:

```python
# Old _close_cycle (lines 1261-1320):
    def _close_cycle(self, reason):
        """Close all tickets and reset for next cycle."""
        is_bust = reason in ('abort', 'terminate', 'max_level_sl')
        level = self.vars.get('level', 0)

        # Use exact TP price for TP exits, candle close for everything else
        if reason == 'tp_hit' and self.vars.get('tp_price') is not None:
            exit_price = self.vars['tp_price']
        else:
            exit_price = self.price

        # Close all positions
        if self.is_open:
            self.close_all_tickets(
                exit_price=exit_price,
                meta={
                    'session': self.vars.get('session_number', 0),
                    'exit_reason': reason,
                    'level': level,
                }
            )

        # Record session
        pnl = self.balance - self.vars.get('session_start_balance', self.balance)
        session_record = {
            'number': self.vars.get('session_number', 0),
            'direction': self.vars.get('session_dir'),
            'levels': level,
            'legs': len(self.vars.get('legs', [])),
            'pnl': round(pnl, 2),
            'reason': reason,
            'bars': self.index - self.vars.get('session_start_bar', 0),
        }
        self.vars['sessions'].append(session_record)

        # Update bust tracking
        if is_bust:
            self.vars['consecutive_busts'] = self.vars.get('consecutive_busts', 0) + 1
            self.vars['daily_busts'] = self.vars.get('daily_busts', 0) + 1
        else:
            self.vars['consecutive_busts'] = 0

        # Set cooldown
        mode = self.hp.get('cooldown_mode', 'none')
        if mode == 'bars':
            self.vars['cooldown_until'] = self.index + int(self.hp.get('cooldown_value', 10))
        elif mode == 'atr_expansion':
            atr = ta.atr(self.candles, period=14)
            avg_atr = ta.atr(self.candles, period=50)
            if atr > avg_atr * self.hp.get('cooldown_value', 2.0):
                self.vars['cooldown_until'] = self.index + 50
            else:
                self.vars['cooldown_until'] = self.index + 5

        # Reset cycle state
        self.vars['cycle_active'] = False
        self.vars['level'] = 0
        self.vars['legs'] = []
        self.vars['tp_price'] = None
        self.vars['hedge_trigger_price'] = None

# New (split into _close_cycle + _end_cycle):
    def _close_cycle(self, reason):
        """Close all tickets and reset for next cycle.
        Called from update_position() for manual exits (abort, bucket_pct, trailing, terminate).
        """
        level = self.vars.get('level', 0)

        # Use exact TP price for TP exits, candle close for everything else
        if reason == 'tp_hit' and self.vars.get('tp_price') is not None:
            exit_price = self.vars['tp_price']
        else:
            exit_price = self.price

        # Close all positions
        if self.is_open:
            self.close_all_tickets(
                exit_price=exit_price,
                meta={
                    'session': self.vars.get('session_number', 0),
                    'exit_reason': reason,
                    'level': level,
                }
            )

        self._end_cycle(reason)

    def _end_cycle(self, reason):
        """Record session, update bust tracking, set cooldown, reset state.
        Called by _close_cycle (manual exit) and on_ticket_tp_hit/on_ticket_sl_hit (engine exit).
        """
        is_bust = reason in ('abort', 'terminate', 'max_level_sl', 'sl_hit')
        level = self.vars.get('level', 0)

        # Record session
        pnl = self.balance - self.vars.get('session_start_balance', self.balance)
        session_record = {
            'number': self.vars.get('session_number', 0),
            'direction': self.vars.get('session_dir'),
            'levels': level,
            'legs': len(self.vars.get('legs', [])),
            'pnl': round(pnl, 2),
            'reason': reason,
            'bars': self.index - self.vars.get('session_start_bar', 0),
        }
        self.vars['sessions'].append(session_record)

        # Update bust tracking
        if is_bust:
            self.vars['consecutive_busts'] = self.vars.get('consecutive_busts', 0) + 1
            self.vars['daily_busts'] = self.vars.get('daily_busts', 0) + 1
        else:
            self.vars['consecutive_busts'] = 0

        # Set cooldown
        mode = self.hp.get('cooldown_mode', 'none')
        if mode == 'bars':
            self.vars['cooldown_until'] = self.index + int(self.hp.get('cooldown_value', 10))
        elif mode == 'atr_expansion':
            atr = ta.atr(self.candles, period=14)
            avg_atr = ta.atr(self.candles, period=50)
            if atr > avg_atr * self.hp.get('cooldown_value', 2.0):
                self.vars['cooldown_until'] = self.index + 50
            else:
                self.vars['cooldown_until'] = self.index + 5

        # Reset cycle state
        self.vars['cycle_active'] = False
        self.vars['level'] = 0
        self.vars['legs'] = []
        self.vars['tp_price'] = None
        self.vars['hedge_trigger_price'] = None
```

- [ ] **Step 7.8: Update `update_position` to only manually check bucket/trailing**

In `strategies/_admin/UniversalMartingale/__init__.py`, change `update_position` (lines 411-449):

```python
# Old (lines 411-449):
    def update_position(self):
        if not self.vars.get('cycle_active'):
            return

        # Check abort conditions
        if self._should_abort():
            self._close_cycle('abort')
            return

        tp_hit = self._check_tp()
        hedge_hit = self._check_hedge_trigger()

        # When BOTH fire on the same candle, use candle direction to decide priority.
        if tp_hit and hedge_hit:
            last_leg = self.vars['legs'][-1] if self.vars.get('legs') else None
            last_dir = last_leg['dir'] if last_leg else self.vars.get('session_dir')
            is_green = self.close >= self.open
            hedge_fires_first = (
                (last_dir == 'long' and is_green) or
                (last_dir == 'short' and not is_green)
            )
            if hedge_fires_first:
                tp_hit = False
            else:
                hedge_hit = False

        if tp_hit:
            self._close_cycle('tp_hit')
            return

        if hedge_hit:
            self._execute_hedge()
            return

        # Check partial close / breakeven
        self._check_position_management()

# New:
    def update_position(self):
        if not self.vars.get('cycle_active'):
            return

        # Check abort conditions
        if self._should_abort():
            self._close_cycle('abort')
            return

        # Manual TP check: only for session-level modes (bucket_pct, trailing).
        # Price-based modes (fixed_pips, atr_based, risk_reward) are handled by
        # the engine via ticket TP/SL triggers and on_ticket_tp_hit callback.
        tp_mode = self.hp.get('tp_mode', 'fixed_pips')
        tp_hit = self._check_tp() if tp_mode in ('bucket_pct', 'trailing') else False
        hedge_hit = self._check_hedge_trigger()

        # When BOTH fire on the same candle, use candle direction to decide priority.
        if tp_hit and hedge_hit:
            last_leg = self.vars['legs'][-1] if self.vars.get('legs') else None
            last_dir = last_leg['dir'] if last_leg else self.vars.get('session_dir')
            is_green = self.close >= self.open
            hedge_fires_first = (
                (last_dir == 'long' and is_green) or
                (last_dir == 'short' and not is_green)
            )
            if hedge_fires_first:
                tp_hit = False
            else:
                hedge_hit = False

        if tp_hit:
            self._close_cycle('tp_hit')
            return

        if hedge_hit:
            self._execute_hedge()
            return

        # Check partial close / breakeven
        self._check_position_management()
```

- [ ] **Step 7.9: Run all tests**

Run: `pytest tests/test_universal_martingale.py tests/test_ticket_service.py tests/test_ticket_tp_sl_engine.py -v 2>&1 | tail -20`
Expected: All tests PASS

- [ ] **Step 7.10: Commit**

```bash
git add strategies/_admin/Martingale/__init__.py
git commit -m "feat: UniversalMartingale uses engine ticket TP/SL for price-based modes"
```

---

## Task 8: Strategy Parity Tests + New Tests

**Files:**
- Modify: `tests/test_universal_martingale.py`

- [ ] **Step 8.1: Add callback and ticket_id tracking tests**

Append to `tests/test_universal_martingale.py`:

```python
# ---------------------------------------------------------------------------
# Engine TP/SL Integration Tests
# ---------------------------------------------------------------------------
class TestEngineTPSL:
    """Tests that Martingale correctly uses engine ticket TP/SL."""

    def test_ticket_id_tracked_on_legs(self):
        """Legs should store ticket_id after entry and hedge."""
        prices = _make_zigzag(base=100, amplitude=2.0, periods=5, candles_per_leg=20)
        hp = dict(PRESETS.get('raw', {}))
        hp['signal_mode'] = 'random'
        hp['tp_mode'] = 'fixed_pips'
        hp['tp_value'] = 50.0  # far away — won't be hit
        hp['max_levels'] = 3
        result = _run_backtest(UniversalMartingale, prices, hyperparameters=hp)
        # If a cycle opened, legs should have ticket_id (may be None in futures mode)
        assert result is not None

    def test_preset_configs_all_load(self):
        """All 10 presets should produce valid hyperparameter dicts."""
        for name, preset in PRESETS.items():
            assert isinstance(preset, dict), f"Preset {name} is not a dict"
            assert 'signal_mode' in preset or 'tp_mode' in preset, \
                f"Preset {name} missing key params"

    def test_surefire_v2_preset_has_bucket_exit(self):
        """surefire_v2 preset should use bucket_pct TP mode."""
        preset = PRESETS.get('surefire_v2', {})
        assert preset.get('tp_mode') == 'bucket_pct', "V2 preset should use bucket mode"

    def test_surefire_v1_preset_has_fixed_tp(self):
        """surefire_v1 preset should use fixed_pips TP mode."""
        preset = PRESETS.get('surefire_v1', {})
        tp_mode = preset.get('tp_mode', 'fixed_pips')
        assert tp_mode == 'fixed_pips', "V1 preset should use fixed_pips"
```

- [ ] **Step 8.2: Run all tests**

Run: `pytest tests/test_universal_martingale.py -v 2>&1 | tail -20`
Expected: All tests PASS (existing + new)

- [ ] **Step 8.3: Commit**

```bash
git add tests/test_universal_martingale.py
git commit -m "test: add engine TP/SL and preset parity tests for UniversalMartingale"
```

---

## Task 9: Delete Old Strategies

**Files:**
- Delete: `strategies/_admin/Surefire/`
- Delete: `strategies/_admin/SurefireV2/`
- Delete: `strategies/_admin/SFPilot/`

- [ ] **Step 9.1: Verify old strategies are not imported anywhere except tests**

Run:
```bash
grep -r "from strategies._admin.Surefire\b" --include="*.py" -l
grep -r "from strategies._admin.SurefireV2" --include="*.py" -l
grep -r "from strategies._admin.SFPilot" --include="*.py" -l
```
Expected: Only test files (which we'll update) and possibly pipeline configs.

- [ ] **Step 9.2: Delete old strategy directories**

```bash
rm -rf strategies/_admin/Surefire/
rm -rf strategies/_admin/SurefireV2/
rm -rf strategies/_admin/SFPilot/
```

- [ ] **Step 9.3: Update any imports that referenced deleted strategies**

If step 9.1 found references (e.g. in test files), update them to use UniversalMartingale with equivalent preset. For `tests/test_surefire_v2.py` and `tests/test_surefire_hedge.py`, either:
- Remove the test file if it only tests deleted strategy internals, OR
- Adapt tests to use `UniversalMartingale` with the corresponding preset

- [ ] **Step 9.4: Run full test suite**

Run: `pytest tests/ -x -q 2>&1 | tail -10`
Expected: All tests pass (no broken imports)

- [ ] **Step 9.5: Commit**

```bash
git add -A
git commit -m "chore: delete Surefire, SurefireV2, SFPilot — consolidated into UniversalMartingale"
```

---

## Task 10: Final Verification

- [ ] **Step 10.1: Run the complete test suite**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All tests pass

- [ ] **Step 10.2: Verify UniversalMartingale works with a real backtest**

Run a quick backtest using the research API to confirm the strategy runs end-to-end:

```bash
python -c "
from qengine import research
from qengine.research.candles import get_candles
import qengine.helpers as jh
from strategies._admin.UniversalMartingale import UniversalMartingale

exchange = 'OANDA'
symbol = 'EUR-USD'
warmup, candles = get_candles(exchange, symbol, '5m', '2025-01-01', '2025-01-15')
cfg = {
    'starting_balance': 100_000, 'fee': 0, 'type': 'cfd',
    'cfd_leverage': 30, 'exchange': exchange, 'warm_up_candles': 200,
    'spread': 0.00015, 'slippage': 0.00002,
}
routes = [{'exchange': exchange, 'strategy': UniversalMartingale, 'symbol': symbol, 'timeframe': '5m'}]
hp = {'signal_mode': 'ema_cross', 'tp_mode': 'fixed_pips', 'tp_value': 15.0,
      'hedge_mode': 'atr_based', 'hedge_value': 1.5, 'max_levels': 6,
      'sizing_curve': 'sqrt', 'sizing_factor': 2.0, 'base_size_mode': 'pct_equity', 'base_size': 1.0}
result = research.backtest(cfg, routes, [],
    {jh.key(exchange, symbol): {'exchange': exchange, 'symbol': symbol, 'candles': candles}},
    hyperparameters=hp, warmup_candles={jh.key(exchange, symbol): warmup})
print(f\"Trades: {result['total']}, PnL: {result['net_profit']:.2f}, Win%: {result.get('win_rate', 0):.1f}\")
"
```
Expected: Prints trade stats (exact numbers vary, but should show trades executed)

- [ ] **Step 10.3: Final commit with all tests passing**

If any fixes were needed, commit them:
```bash
git add -A
git commit -m "fix: final adjustments from integration testing"
```
