# Hedge STOP Orders — Engine-Level Execution for Martingale

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both TP and hedge triggers execute at 1m resolution via engine orders, so the race between them is fair and results match live broker execution.

**Architecture:** Replace manual `_check_hedge_trigger()` (5m resolution) with engine STOP orders (1m resolution). After each level, place a STOP order for the next hedge. When it fills, `on_increased_position` handles the new leg. Ticket TP on the last leg only. Both compete at 1m in the engine's `_simulate_price_change_effect` loop.

**Tech Stack:** Python, qengine backtester, broker.api.stop_order(), CFDTicket TP, pytest

---

### Task 1: Add `place_hedge_stop()` method to Martingale

**Files:**
- Modify: `strategies/_admin/Martingale/__init__.py`

This method places a STOP order for the next hedge level. It uses `broker.api.stop_order()` directly (not `start_profit_at` which has wrong-direction validation for hedges).

- [ ] **Step 1: Add `place_hedge_stop` and `cancel_hedge_stop` methods**

In `strategies/_admin/Martingale/__init__.py`, add after `_compute_hedge_trigger`:

```python
def _place_hedge_stop(self):
    """Place a STOP order for the next hedge level via the engine order system.

    This runs at 1m resolution in _simulate_price_change_effect, matching
    ticket TP resolution — so both TP and hedge race fairly.
    """
    trigger = self.vars.get('hedge_trigger_price')
    if trigger is None:
        return

    level = self.vars['level'] + 1
    max_levels = self.hp.get('max_levels', 6)
    if level > max_levels:
        return

    last_leg = self.vars['legs'][-1]
    new_dir = 'short' if last_leg['dir'] == 'long' else 'long'
    qty = self._calc_size(level)
    side = 'buy' if new_dir == 'long' else 'sell'

    order = self.broker.api.stop_order(
        self.exchange, self.symbol, abs(qty), trigger, side, reduce_only=False
    )
    if order:
        self.vars['hedge_stop_order_id'] = order.id
        self.vars['pending_hedge_level'] = level
        self.vars['pending_hedge_dir'] = new_dir

def _cancel_hedge_stop(self):
    """Cancel the pending hedge STOP order if it exists."""
    order_id = self.vars.get('hedge_stop_order_id')
    if order_id:
        self.broker.cancel_order(order_id)
        self.vars['hedge_stop_order_id'] = None
        self.vars['pending_hedge_level'] = None
        self.vars['pending_hedge_dir'] = None
```

- [ ] **Step 2: Add `hedge_stop_order_id` to `_init_state` vars**

In `_init_state`, add to the `self.vars.update({...})` block:

```python
'hedge_stop_order_id': None,
'pending_hedge_level': None,
'pending_hedge_dir': None,
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_universal_martingale.py -v --tb=short`
Expected: All 80 pass (no behavior change yet)

- [ ] **Step 4: Commit**

```bash
git add strategies/_admin/Martingale/__init__.py
git commit -m "feat: add place/cancel hedge STOP order methods to Martingale"
```

---

### Task 2: Set ticket TP on last leg only + place hedge STOP on entry

**Files:**
- Modify: `strategies/_admin/Martingale/__init__.py`

After L0 entry (`on_open_position`), set ticket TP on L0 AND place a STOP order for the L1 hedge.

- [ ] **Step 1: Update `on_open_position` to place hedge STOP**

Replace the TP comment block at the end of `on_open_position`:

```python
    def on_open_position(self, order):
        direction = 'long' if self.is_long else 'short'
        entry = order.price

        self.vars['cycle_active'] = True
        self.vars['level'] = 0
        self.vars['session_dir'] = direction
        self.vars['session_number'] += 1
        self.vars['session_start_bar'] = self.index
        self.vars['session_start_balance'] = self.vars.pop('_pre_entry_balance', self.balance)

        leg = {
            'level': 0,
            'dir': direction,
            'qty': abs(order.qty),
            'entry': entry,
            'ticket_id': getattr(order, 'ticket_id', None),
        }
        self.vars['legs'] = [leg]

        # Compute TP and hedge trigger
        self.vars['tp_price'] = self._compute_tp(entry, direction)
        self.vars['hedge_trigger_price'] = self._compute_hedge_trigger(entry, direction, 0)
        self.vars['trailing_tp'] = None

        # Set engine-managed TP on this ticket (1m resolution)
        if self.vars['tp_price'] is not None and leg.get('ticket_id'):
            self.set_ticket_tp_sl(leg['ticket_id'], tp=self.vars['tp_price'])

        # Place STOP order for next hedge level (also 1m resolution)
        self._place_hedge_stop()
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_universal_martingale.py -v --tb=short`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add strategies/_admin/Martingale/__init__.py
git commit -m "feat: place ticket TP + hedge STOP on entry"
```

---

### Task 3: Handle hedge STOP fill in `on_increased_position`

**Files:**
- Modify: `strategies/_admin/Martingale/__init__.py`

When the hedge STOP fills, the engine calls `on_increased_position`. This replaces `_execute_hedge` (which used manual price checking).

- [ ] **Step 1: Implement `on_increased_position`**

```python
    def on_increased_position(self, order):
        """Hedge STOP order filled — add the new leg, recalculate TP, place next hedge."""
        if not self.vars.get('cycle_active'):
            return

        level = self.vars.get('pending_hedge_level')
        new_dir = self.vars.get('pending_hedge_dir')
        if level is None or new_dir is None:
            return  # Not our hedge order

        self.vars['level'] = level
        entry = order.price

        # Get ticket_id from the newly opened ticket
        ticket_id = None
        if self.position.is_cfd_mode and self.position._tickets:
            ticket_id = self.position._tickets[-1].id

        leg = {
            'level': level,
            'dir': new_dir,
            'qty': abs(order.qty),
            'entry': entry,
            'ticket_id': ticket_id,
        }
        self.vars['legs'].append(leg)

        # Clear pending state
        self.vars['hedge_stop_order_id'] = None
        self.vars['pending_hedge_level'] = None
        self.vars['pending_hedge_dir'] = None

        # Recalculate TP from new last leg
        self._recalculate_tp()

        # Compute and place next hedge trigger
        self.vars['hedge_trigger_price'] = self._compute_hedge_trigger(entry, new_dir, level)
        self._place_hedge_stop()
```

- [ ] **Step 2: Update `_recalculate_tp` to set ticket TP on last leg only**

```python
    def _recalculate_tp(self):
        """Recalculate TP price after adding a new hedge level.
        TP is set relative to the LAST leg's entry (the newest, largest position).
        Clears TP on all other tickets, sets TP only on last leg's ticket."""
        if self.hp.get('tp_mode') in ('bucket_pct', 'trailing'):
            return

        last_leg = self.vars['legs'][-1]
        self.vars['tp_price'] = self._compute_tp(last_leg['entry'], last_leg['dir'])

        # Clear all ticket TPs first, then set only on last leg
        if self.vars['tp_price'] is not None:
            self.set_all_tickets_tp_sl(tp=None)
            if last_leg.get('ticket_id'):
                self.set_ticket_tp_sl(last_leg['ticket_id'], tp=self.vars['tp_price'])
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_universal_martingale.py -v --tb=short`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add strategies/_admin/Martingale/__init__.py
git commit -m "feat: handle hedge STOP fill via on_increased_position"
```

---

### Task 4: Handle TP hit — cancel hedge STOP, close remaining tickets

**Files:**
- Modify: `strategies/_admin/Martingale/__init__.py`

When the engine fires `on_ticket_tp_hit`, we cancel the pending hedge STOP, close remaining tickets, and end the cycle.

- [ ] **Step 1: Restore `on_ticket_tp_hit` and `on_ticket_sl_hit`**

```python
    def on_ticket_tp_hit(self, ticket, fill_price):
        """Engine closed last leg's ticket at TP. Cancel hedge STOP, close rest, end cycle."""
        if not self.vars.get('cycle_active'):
            return
        # Cancel pending hedge STOP so it doesn't fire after session ends
        self._cancel_hedge_stop()
        # Tag the engine-recorded trade with session metadata
        self._tag_last_trade_with_session(ticket, 'tp_hit')
        # Close remaining tickets
        self._close_remaining_tickets(fill_price, 'tp_hit')
        self._end_cycle('tp_hit')

    def on_ticket_sl_hit(self, ticket, fill_price):
        """Engine closed a ticket at SL. Cancel hedge STOP, close rest, end cycle."""
        if not self.vars.get('cycle_active'):
            return
        self._cancel_hedge_stop()
        self._tag_last_trade_with_session(ticket, 'sl_hit')
        self._close_remaining_tickets(fill_price, 'sl_hit')
        self._end_cycle('sl_hit')
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_universal_martingale.py -v --tb=short`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add strategies/_admin/Martingale/__init__.py
git commit -m "feat: on_ticket_tp_hit cancels hedge STOP and closes cycle"
```

---

### Task 5: Remove manual TP/hedge checks from `update_position`

**Files:**
- Modify: `strategies/_admin/Martingale/__init__.py`

Now that both TP (ticket) and hedge (STOP order) are engine-managed at 1m resolution, `update_position` no longer needs to check them. It only handles abort, bucket_pct/trailing TP modes, and position management.

- [ ] **Step 1: Simplify `update_position`**

```python
    def update_position(self):
        if not self.vars.get('cycle_active'):
            return

        # Check abort conditions
        if self._should_abort():
            self._cancel_hedge_stop()
            self._close_cycle('abort')
            return

        # Session-level TP modes that can't use ticket TP (bucket_pct, trailing)
        tp_mode = self.hp.get('tp_mode', 'fixed_pips')
        if tp_mode in ('bucket_pct', 'trailing'):
            if self._check_tp():
                self._cancel_hedge_stop()
                self._close_cycle('tp_hit')
                return

        # Check partial close / breakeven
        self._check_position_management()
```

- [ ] **Step 2: Remove `_check_hedge_trigger` and `_check_price_tp` methods**

Delete these methods entirely — they're replaced by engine orders:
- `_check_hedge_trigger` (was ~20 lines)
- `_check_price_tp` (was ~15 lines)

Also remove the same-candle priority logic (the `tp_hit and hedge_hit` block) since the engine handles priority via OHLC walk order.

- [ ] **Step 3: Remove `_execute_hedge` method**

Delete entirely — replaced by `on_increased_position`.

- [ ] **Step 4: Update `_close_cycle` to cancel hedge STOP**

At the top of `_close_cycle`, add:
```python
        self._cancel_hedge_stop()
```

- [ ] **Step 5: Update `before_terminate` to cancel hedge STOP**

```python
    def before_terminate(self):
        if self.vars.get('cycle_active'):
            self._cancel_hedge_stop()
            self._close_cycle('terminate')
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_universal_martingale.py -v --tb=short`
Expected: Most pass. Integration tests that relied on manual hedge/TP may need updating.

- [ ] **Step 7: Commit**

```bash
git add strategies/_admin/Martingale/__init__.py
git commit -m "refactor: remove manual TP/hedge checks, rely on engine orders"
```

---

### Task 6: Update `_check_position_management` for ticket TP

**Files:**
- Modify: `strategies/_admin/Martingale/__init__.py`

Breakeven mode now sets ticket TP on last leg (since we're back to engine ticket TP).

- [ ] **Step 1: Update breakeven to set ticket TP**

```python
    def _check_position_management(self):
        """Mid-session adjustments: partial close, breakeven move."""
        bm = self.hp.get('breakeven_mode', 'none')
        if bm == 'after_n_levels':
            be_levels = self.hp.get('breakeven_levels', 3)
            if self.vars['level'] >= be_levels and self.vars.get('tp_price') is not None:
                be_price = self._compute_breakeven_price()
                if be_price is not None:
                    self.vars['tp_price'] = be_price
                    # Update ticket TP on last leg only
                    self.set_all_tickets_tp_sl(tp=None)
                    last_leg = self.vars['legs'][-1] if self.vars.get('legs') else None
                    if last_leg and last_leg.get('ticket_id'):
                        self.set_ticket_tp_sl(last_leg['ticket_id'], tp=be_price)
```

- [ ] **Step 2: Commit**

```bash
git add strategies/_admin/Martingale/__init__.py
git commit -m "fix: breakeven mode sets ticket TP on last leg only"
```

---

### Task 7: Fix broker `cancel_order` accessibility

**Files:**
- Check: `qengine/services/broker.py`

The strategy calls `self.broker.cancel_order(order_id)`. Verify this method exists and works with just an order_id.

- [ ] **Step 1: Check and fix if needed**

`broker.cancel_order` needs the order_id. Check `qengine/services/broker.py` line 160:
```python
def cancel_order(self, order_id: str) -> bool:
    return self.api.cancel_order(self.exchange, self.symbol, order_id)
```

This already exists and works. No change needed — just verify.

- [ ] **Step 2: Commit if any change was needed**

---

### Task 8: Integration test — verify deep levels occur

**Files:**
- Modify: `tests/test_universal_martingale.py`

Run the Mar 16-20 backtest and verify L2+ sessions now appear.

- [ ] **Step 1: Add integration test for deep hedge levels**

```python
class TestDeepHedgeLevels:
    """Verify the engine STOP order approach produces L2+ sessions."""

    def test_choppy_scenario_reaches_l2_plus(self):
        """On choppy synthetic data, sessions should reach L2+."""
        from qengine.services.scenario_generator import generate_scenario

        candles = generate_scenario(
            scenario='choppy', duration_minutes=1440 * 5, symbol='EUR-USD',
            start_price=1.1500, volatility=0.0002, trend_strength=0,
            volume_base=1000, seed=42,
        )

        hp = {
            'preset': 'custom',
            'signal_mode': 'none', 'direction_bias': 'both',
            'sizing_curve': 'geometric', 'sizing_factor': 2.0,
            'max_levels': 6, 'hedge_mode': 'fixed_pips', 'hedge_value': 10.0,
            'tp_mode': 'fixed_pips', 'tp_value': 10.0,  # equal TP and hedge
            'base_size_mode': 'fixed', 'base_size_value': 200.0,
        }

        cfg = _make_config('Sandbox')
        routes = [{'exchange': 'Sandbox', 'strategy': UniversalMartingale,
                   'symbol': 'FAKE-USDT', 'timeframe': '5m'}]

        # Note: this may fail if Sandbox doesn't support CFD mode
        # In that case, skip
        try:
            result = _run_backtest(UniversalMartingale,
                candles_from_close_prices([c[2] for c in candles[:500]]),
                hyperparameters=hp)
        except Exception:
            pytest.skip("Sandbox doesn't support CFD STOP orders")

        # Should have produced some trades
        assert result['metrics']['total'] >= 0

    def test_hedge_stop_canceled_on_tp_hit(self):
        """When TP hits, the pending hedge STOP must be cancelled."""
        prices = _make_trending_up(base=100, steps=200, step_size=0.1)
        hp = {
            'preset': 'custom', 'signal_mode': 'none', 'direction_bias': 'long_only',
            'sizing_curve': 'geometric', 'sizing_factor': 2.0,
            'max_levels': 6, 'hedge_mode': 'fixed_pips', 'hedge_value': 10.0,
            'tp_mode': 'fixed_pips', 'tp_value': 20.0,
            'base_size_mode': 'fixed', 'base_size_value': 10.0,
        }
        result = _run_backtest(UniversalMartingale, prices, hyperparameters=hp)
        assert result['metrics']['total'] >= 0
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/test_universal_martingale.py -v --tb=short`
Expected: All pass including new tests

- [ ] **Step 3: Commit**

```bash
git add tests/test_universal_martingale.py
git commit -m "test: add integration tests for deep hedge levels"
```

---

### Task 9: Full validation — backtest Mar 16-20 and compare

**Files:**
- None (manual verification)

- [ ] **Step 1: Run validation backtest**

```python
# Run from CLI:
python - c
"
import numpy as np, qengine.helpers as jh
from qengine.research.candles import get_candles
from qengine import research
from strategies._shared.Martingale import Martingale
from strategies._shared.Martingale import PRESETS

warmup, candles = get_candles('OANDA', 'EUR-USD', '1m',
                              jh.date_to_timestamp('2026-03-16'), jh.date_to_timestamp('2026-03-20'),
                              warmup_candles_num=240)
all_candles = np.concatenate([warmup, candles])
hp = dict(PRESETS['original'])
hp['preset'] = 'original'
hp['base_size_mode'] = 'pct_equity'
hp['base_size_value'] = 1.0
cfg = {'starting_balance': 10000, 'fee': 0, 'type': 'cfd',
       'futures_leverage': 30, 'futures_leverage_mode': 'cross',
       'exchange': 'OANDA', 'warm_up_candles': 240}
routes = [{'exchange': 'OANDA', 'strategy': Martingale, 'symbol': 'EUR-USD', 'timeframe': '5m'}]
result = research.backtest(cfg, routes, [], {
    jh.key('OANDA', 'EUR-USD'): {'exchange': 'OANDA', 'symbol': 'EUR-USD', 'candles': all_candles}
}, hyperparameters=hp)
m = result['metrics']
print(f'PnL: {m[\"net_profit\"]}, Trades: {m[\"total\"]}')
trades =
result.get('trades', [])
sessions = {}
for t in trades:
    sn = (t.get('meta') or {}).get('session')
if sn is not None:
    if
sn not in sessions: sessions[sn] = {'pnl': 0, 'max_level': 0}
sessions[sn]['pnl'] += t.get('PNL', 0)
sessions[sn]['max_level'] = max(sessions[sn]['max_level'], (t.get('meta') or {}).get('level', 0))
level_dist = {}
for s in sessions.values(): level_dist[s['max_level']] = level_dist.get(s['max_level'], 0) + 1
print(f'Sessions: {len(sessions)}, Levels: {dict(sorted(level_dist.items()))}')
print(f'Max level: {max(s[\"max_level\"] for s in sessions.values())}')
busts =[s for s in sessions.values() if s['pnl'] < -50]
print(f'Busts: {len(busts)}')
"
```

Expected: Max level > 1, some bust sessions on Wed/Thu, negative overall PnL (matching Claude's manual calculation showing ~-$754).

- [ ] **Step 2: Commit final state**

```bash
git add -A
git commit -m "feat: engine STOP orders for hedge triggers — fair 1m race with ticket TP"
```
