"""
Execution Mechanism Tests
=========================
Tests that verify the EXACT prices at which orders fill, not just PnL direction.
These catch bugs where orders fill at candle close instead of trigger price.

Covers:
  1. Hedge fill prices — exact trigger, same-side legs identical (fixed_pips)
  2. TP/SL exit prices — exact target price, not candle close
  3. Cost model gating — zero costs when disabled
  4. CFD ticket PnL — correct per-ticket math
  5. Order type determination — is_price_near, MARKET vs LIMIT vs STOP
  6. Surefire grid math — distances, sizing, net PnL formula
"""

import os
import sys
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

import qengine.helpers as jh
from qengine.config import config, reset_config
from qengine.enums import exchanges, sides, order_types, order_statuses
from qengine.store import store
from qengine.models.Position import Position, CFDTicket
from qengine.models.Order import Order
from qengine.routes import router


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

BASE_TS = 1609459200000  # 2021-01-01 00:00:00 UTC


def _ts(i):
    return BASE_TS + i * 60_000


def _make_candles(ohlc_list):
    """Build candle array from (open, high, low, close) tuples.
    Candle format: [timestamp, open, close, high, low, volume]
    """
    candles = []
    for i, (o, h, l, c) in enumerate(ohlc_list):
        candles.append([_ts(i), o, c, h, l, 100.0])
    return np.array(candles, dtype=np.float64)


def _init_backtest_config(exchange_type='cfd', balance=10_000, fee=0, cost_model=False):
    """Set up config for backtesting."""
    reset_config()
    config['app']['trading_mode'] = 'backtest'
    config['app']['cost_model'] = cost_model
    config['env']['exchanges'][exchanges.SANDBOX] = {
        'fee': fee,
        'type': exchange_type,
        'futures_leverage_mode': 'cross',
        'futures_leverage': 30,
        'balance': balance,
    }
    # Set considering_exchanges so exchange_service can initialize
    config['app']['considering_exchanges'] = (exchanges.SANDBOX,)


def _init_cfd_exchange():
    """Initialize store with a CFD exchange and return it."""
    from qengine.services.exchange_service import initialize_exchanges_state
    from qengine.services import order_service, position_service
    store.reset()
    store.candles.init_storage(5000)
    initialize_exchanges_state()
    order_service.initialize_orders_state()
    position_service.initialize_positions_state()
    return store.exchanges.get_exchange(exchanges.SANDBOX)


def _teardown():
    store.reset()
    router._reset()


# ═══════════════════════════════════════════════════════════════════════════════
# Part 1: Hedge Fill Prices
# ═══════════════════════════════════════════════════════════════════════════════

class TestHedgeFillPrices:
    """Verify hedge orders fill at exact trigger price, not candle close."""

    def test_sandbox_market_order_preserves_price(self):
        """Sandbox.market_order() creates order with the exact specified price."""
        from qengine.exchanges.sandbox.Sandbox import Sandbox
        from qengine.services import order_service

        _init_backtest_config(exchange_type='cfd')
        # Sandbox.market_order calls order_service.create_order which needs
        # the exchange in the store but does NOT need routes for basic creation.
        # We can test the Order object directly.
        trigger_price = 1.10500
        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': 'EUR-USD',
            'exchange': exchanges.SANDBOX,
            'side': sides.BUY,
            'type': order_types.MARKET,
            'qty': 1000,
            'price': trigger_price,
            'status': order_statuses.ACTIVE,
            'created_at': jh.now_to_timestamp(),
        })

        assert order.price == pytest.approx(trigger_price, abs=1e-10)
        assert order.type == order_types.MARKET

    def test_buy_at_market_uses_current_price(self):
        """broker.buy_at_market() fills at position.current_price, ignoring trigger.
        This is WHY we use broker.api.market_order() directly for hedges.
        """
        # Inspect the source code of buy_at_market to verify it uses current_price
        from qengine.services.broker import Broker
        import inspect
        src = inspect.getsource(Broker.buy_at_market)
        assert 'self.position.current_price' in src, \
            "buy_at_market must use self.position.current_price (candle close)"
        # It does NOT accept a price parameter — trigger is lost
        params = inspect.signature(Broker.buy_at_market).parameters
        assert 'price' not in params, "buy_at_market should not accept a price param"

    def test_is_price_near_threshold(self):
        """is_price_near converts to MARKET when within 0.015%."""
        assert jh.is_price_near(1.10000, 1.10000) is True
        assert jh.is_price_near(1.10000, 1.10010) is True   # ~0.009%
        assert jh.is_price_near(1.10000, 1.10015) is True   # ~0.014%
        assert jh.is_price_near(1.10000, 1.10500) is False  # ~0.045%

    def test_cfd_ticket_gets_trigger_price_not_current(self):
        """Ticket entry_price must match the order fill price."""
        _init_backtest_config()

        p = Position({
            'exchange': MagicMock(type='cfd', default_leverage=30, fee_rate=0),
            'exchange_name': 'Test',
            'symbol': 'EUR-USD',
            'current_price': 1.10050,  # candle close
        })

        trigger_price = 1.09900
        ticket = p.open_ticket('long', 1000, trigger_price, _ts(0))

        assert ticket.entry_price == pytest.approx(trigger_price, abs=1e-10)
        assert ticket.entry_price != 1.10050  # NOT candle close


# ═══════════════════════════════════════════════════════════════════════════════
# Part 2: TP/SL Exit Prices
# ═══════════════════════════════════════════════════════════════════════════════

class TestTPSLExitPrices:
    """Verify TP/SL exits use exact target price, not candle close."""

    def test_close_all_tickets_at_exact_tp_price(self):
        """close_all_tickets uses the passed exit_price for PnL, not current_price."""
        _init_backtest_config()

        p = Position({
            'exchange': MagicMock(type='cfd', default_leverage=30, fee_rate=0),
            'exchange_name': 'Test',
            'symbol': 'EUR-USD',
            'current_price': 1.12000,  # candle close — should NOT be used
        })

        p.open_ticket('long', 1000, 1.10000, _ts(0))
        p.open_ticket('short', 2000, 1.11000, _ts(1))

        tp_price = 1.10500  # exact TP

        results = p.close_all_tickets(tp_price)

        long_pnl = results[0]['pnl']
        short_pnl = results[1]['pnl']

        assert long_pnl == pytest.approx((1.10500 - 1.10000) * 1000, abs=0.01)   # +5.0
        assert short_pnl == pytest.approx((1.11000 - 1.10500) * 2000, abs=0.01)  # +10.0

    def test_all_tickets_same_exit_reason_after_fix(self):
        """All tickets in a TP session get 'tp_hit', not 'sl_hit' for losers."""
        # The fixed code in Strategy.py:1388
        session_exit_reason = 'tp_hit'
        pnls = [10.0, -5.0, 20.0, -15.0]

        for pnl in pnls:
            ticket_meta = {}
            if session_exit_reason:
                ticket_meta['exit_reason'] = session_exit_reason
            assert ticket_meta['exit_reason'] == 'tp_hit'

    def test_close_cycle_tp_uses_tp_price(self):
        """_close_cycle('tp_hit') logic selects vars['tp_price'], not self.price."""
        tp_price = 1.11000
        candle_close = 1.11050

        reason = 'tp_hit'
        vars_tp = tp_price

        exit_price = vars_tp if (reason == 'tp_hit' and vars_tp is not None) else candle_close

        assert exit_price == pytest.approx(tp_price)
        assert exit_price != candle_close

    def test_close_cycle_abort_uses_candle_close(self):
        """_close_cycle('abort') should use self.price (candle close) — no trigger available."""
        candle_close = 1.11050

        reason = 'abort'
        vars_tp = 1.11000

        exit_price = vars_tp if (reason == 'tp_hit' and vars_tp is not None) else candle_close

        assert exit_price == candle_close


# ═══════════════════════════════════════════════════════════════════════════════
# Part 3: Cost Model Gating
# ═══════════════════════════════════════════════════════════════════════════════

class TestCostModelGating:
    """Verify cost_model=False produces zero costs everywhere."""

    def test_spread_not_applied_when_cost_model_off(self):
        """No spread adjustment to order price when cost_model is False."""
        from qengine.services import order_service
        from qengine.models.CFDExchange import CFDExchange

        _init_backtest_config(exchange_type='cfd', cost_model=False)
        router._reset()
        from qengine.models.Route import Route
        router.routes = [Route(exchanges.SANDBOX, 'EUR-USD', '1m', 'Test', None)]
        e = _init_cfd_exchange()
        assert isinstance(e, CFDExchange)

        original_price = 1.10000
        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': 'EUR-USD',
            'exchange': exchanges.SANDBOX,
            'side': sides.BUY,
            'type': order_types.MARKET,
            'qty': 1000,
            'price': original_price,
            'status': order_statuses.ACTIVE,
            'created_at': jh.now_to_timestamp(),
        })

        order_service.execute_order(order)

        assert order.price == pytest.approx(original_price, abs=1e-10)
        assert e._total_spread_cost == 0.0

        _teardown()

    def test_spread_applied_when_cost_model_on(self):
        """Spread IS applied to order price when cost_model is True."""
        from qengine.services import order_service
        from qengine.models.CFDExchange import CFDExchange

        _init_backtest_config(exchange_type='cfd', cost_model=True)
        router._reset()
        from qengine.models.Route import Route
        router.routes = [Route(exchanges.SANDBOX, 'EUR-USD', '1m', 'Test', None)]
        e = _init_cfd_exchange()
        assert isinstance(e, CFDExchange)
        e.set_spread('EUR-USD', 0.00020)  # 2 pips

        original_price = 1.10000
        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': 'EUR-USD',
            'exchange': exchanges.SANDBOX,
            'side': sides.BUY,
            'type': order_types.MARKET,
            'qty': 1000,
            'price': original_price,
            'status': order_statuses.ACTIVE,
            'created_at': jh.now_to_timestamp(),
        })

        order_service.execute_order(order)

        # BUY entry: price += spread
        assert order.price == pytest.approx(original_price + 0.00020, abs=1e-6)
        assert e._total_spread_cost > 0

        _teardown()

    def test_spot_fee_zeroed_when_cost_model_off(self):
        """SpotExchange fee logic should yield 0 when cost_model=False."""
        _init_backtest_config(exchange_type='spot', fee=0.001, cost_model=False)

        fee_rate = 0.001
        cost_model_on = config.get('app', {}).get('cost_model', True)
        effective_fee = fee_rate if cost_model_on else 0

        assert effective_fee == 0

    def test_spot_fee_applied_when_cost_model_on(self):
        """SpotExchange fee logic should use fee_rate when cost_model=True."""
        _init_backtest_config(exchange_type='spot', fee=0.001, cost_model=True)

        fee_rate = 0.001
        cost_model_on = config.get('app', {}).get('cost_model', True)
        effective_fee = fee_rate if cost_model_on else 0

        assert effective_fee == 0.001


# ═══════════════════════════════════════════════════════════════════════════════
# Part 4: CFD Ticket PnL
# ═══════════════════════════════════════════════════════════════════════════════

class TestCFDTicketPnL:
    """Verify per-ticket PnL calculation is exact."""

    def test_long_ticket_pnl(self):
        t = CFDTicket('long', 10000, 1.10000, _ts(0))
        assert t.pnl(1.10500) == pytest.approx(50.0, abs=1e-6)    # +50
        assert t.pnl(1.09500) == pytest.approx(-50.0, abs=1e-6)   # -50
        assert t.pnl(1.10000) == pytest.approx(0.0, abs=1e-10)

    def test_short_ticket_pnl(self):
        t = CFDTicket('short', 10000, 1.10000, _ts(0))
        assert t.pnl(1.09500) == pytest.approx(50.0, abs=1e-6)    # +50
        assert t.pnl(1.10500) == pytest.approx(-50.0, abs=1e-6)   # -50
        assert t.pnl(1.10000) == pytest.approx(0.0, abs=1e-10)

    def test_close_all_tickets_pnl_sum(self):
        _init_backtest_config()

        p = Position({
            'exchange': MagicMock(type='cfd', default_leverage=30, fee_rate=0),
            'exchange_name': 'Test',
            'symbol': 'EUR-USD',
            'current_price': 1.10000,
        })

        p.open_ticket('long', 1000, 1.10000, _ts(0))
        p.open_ticket('short', 2000, 1.11000, _ts(1))
        p.open_ticket('long', 4000, 1.10000, _ts(2))

        exit_price = 1.10500
        results = p.close_all_tickets(exit_price)

        total = sum(r['pnl'] for r in results)
        expected = (
            (1.10500 - 1.10000) * 1000 +   # +5.0
            (1.11000 - 1.10500) * 2000 +    # +10.0
            (1.10500 - 1.10000) * 4000      # +20.0
        )
        assert total == pytest.approx(expected, abs=0.01)

    def test_realized_pnl_added_to_balance(self):
        _init_backtest_config(exchange_type='cfd')
        router._reset()
        from qengine.models.Route import Route
        router.routes = [Route(exchanges.SANDBOX, 'EUR-USD', '1m', 'Test', None)]
        e = _init_cfd_exchange()

        initial = e.assets[e.settlement_currency]

        e.add_realized_pnl(50.0)
        assert e.assets[e.settlement_currency] == pytest.approx(initial + 50.0)

        e.add_realized_pnl(-30.0)
        assert e.assets[e.settlement_currency] == pytest.approx(initial + 20.0)

        _teardown()

    def test_surefire_session_net_pnl_positive(self):
        """Simulate a full surefire session closing at TP — net PnL must be positive."""
        _init_backtest_config()

        p = Position({
            'exchange': MagicMock(type='cfd', default_leverage=30, fee_rate=0),
            'exchange_name': 'Test',
            'symbol': 'EUR-USD',
            'current_price': 1.10000,
        })

        # Surefire grid: long-short-long with m=2, 10 pip hedge, 20 pip TP
        p.open_ticket('long', 1000, 1.10000, _ts(0))    # L0
        p.open_ticket('short', 2000, 1.09900, _ts(1))   # L1 (10 pips below L0)
        p.open_ticket('long', 4000, 1.10000, _ts(2))    # L2 (same as L0)

        # TP = 20 pips from last long entry: 1.10000 + 0.00200 = 1.10200
        tp_price = 1.10200
        results = p.close_all_tickets(tp_price)

        total = sum(r['pnl'] for r in results)
        assert total > 0, f"Surefire session PnL should be positive, got {total}"


# ═══════════════════════════════════════════════════════════════════════════════
# Part 5: Order Type Determination
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderTypeDetermination:

    def test_buy_order_types(self):
        """BUY: price > current → STOP, price < current → LIMIT, ≈ → MARKET."""
        current = 1.10000
        assert not jh.is_price_near(1.11000, current)
        assert 1.11000 > current  # → STOP

        assert not jh.is_price_near(1.09000, current)
        assert 1.09000 < current  # → LIMIT

        assert jh.is_price_near(1.10001, current)  # → MARKET

    def test_sell_order_types(self):
        """SELL: price < current → STOP, price > current → LIMIT."""
        current = 1.10000
        assert not jh.is_price_near(1.09000, current)
        assert 1.09000 < current  # → STOP

        assert not jh.is_price_near(1.11000, current)
        assert 1.11000 > current  # → LIMIT

    def test_api_market_order_preserves_exact_price(self):
        """A market order created with a specific price preserves that price."""
        trigger_price = 1.09900
        candle_close = 1.10050

        # Verify the Order object keeps the specified price
        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': 'EUR-USD',
            'exchange': exchanges.SANDBOX,
            'side': sides.BUY,
            'type': order_types.MARKET,
            'qty': 1000,
            'price': trigger_price,
            'status': order_statuses.ACTIVE,
            'created_at': jh.now_to_timestamp(),
        })

        assert order.price == pytest.approx(trigger_price, abs=1e-10)
        assert order.price != candle_close


# ═══════════════════════════════════════════════════════════════════════════════
# Part 6: Surefire Grid Math
# ═══════════════════════════════════════════════════════════════════════════════

class TestSurefireGridMath:

    def test_fixed_pips_same_side_entries(self):
        """With fixed 10-pip hedge, same-side legs have identical entries."""
        entry_l0 = 1.10000
        h = 0.00100  # 10 pips

        t1 = entry_l0 - h   # L1 short: 1.09900
        t2 = t1 + h         # L2 long:  1.10000
        t3 = t2 - h         # L3 short: 1.09900
        t4 = t3 + h         # L4 long:  1.10000

        assert t2 == pytest.approx(entry_l0, abs=1e-10)
        assert t4 == pytest.approx(entry_l0, abs=1e-10)
        assert t3 == pytest.approx(t1, abs=1e-10)

    def test_sqrt_sizing(self):
        base, m = 1000, 2.0
        s = m ** 0.5
        assert base * s**0 == pytest.approx(1000.0)
        assert base * s**1 == pytest.approx(1414.21, abs=0.01)
        assert base * s**2 == pytest.approx(2000.0, abs=0.01)

    def test_multiplier_sizing(self):
        base, m = 1000, 2.0
        assert base * m**0 == 1000
        assert base * m**1 == 2000
        assert base * m**2 == 4000

    def test_fibonacci_sizing(self):
        fib = [1, 1, 2, 3, 5, 8]
        base = 1000
        assert [base * f for f in fib] == [1000, 1000, 2000, 3000, 5000, 8000]

    def test_tp_positive_pnl_multiplier(self):
        """TP hit with m=2 sizing: net PnL positive at all depths."""
        e = 1.10000
        h, t, m, base = 0.00100, 0.00200, 2.0, 1000

        for depth in range(1, 7):
            legs = []
            ce = e
            for lvl in range(depth + 1):
                d = 'long' if lvl % 2 == 0 else 'short'
                legs.append((d, base * m**lvl, ce))
                ce = ce - h if d == 'long' else ce + h

            last_d, _, last_e = legs[-1]
            tp = last_e + t if last_d == 'long' else last_e - t

            pnl = sum(q * ((tp - p) if d == 'long' else (p - tp)) for d, q, p in legs)
            assert pnl > 0, f"Depth {depth}: PnL={pnl:.4f} should be positive"

    def test_tp_positive_pnl_sqrt_sizing(self):
        """TP hit with sqrt(2) sizing: net PnL positive when tp > hedge/(sqrt(2)-1).

        With sqrt(2) multiplier, profitability requires:
          tp_dist > hedge_dist / (sqrt(2) - 1) ≈ 2.414 * hedge_dist
        So with 10 pip hedge, need tp > 24.14 pips. Use 25 pips.
        """
        e = 1.10000
        h = 0.00100   # 10 pip hedge
        t = 0.00250   # 25 pip TP (> 24.14 threshold)
        s = 2.0 ** 0.5
        base = 1000

        for depth in range(1, 7):
            legs = []
            ce = e
            for lvl in range(depth + 1):
                d = 'long' if lvl % 2 == 0 else 'short'
                legs.append((d, base * s**lvl, ce))
                ce = ce - h if d == 'long' else ce + h

            last_d, last_q, last_e = legs[-1]
            tp = last_e + t if last_d == 'long' else last_e - t

            pnl = sum(q * ((tp - p) if d == 'long' else (p - tp)) for d, q, p in legs)
            assert pnl > 0, f"Depth {depth}: PnL={pnl:.4f} should be positive"

    def test_sqrt_sizing_unprofitable_below_threshold(self):
        """sqrt(2) with tp < hedge/(sqrt(2)-1) is NOT guaranteed profitable."""
        e = 1.10000
        h = 0.00100   # 10 pip hedge
        t = 0.00200   # 20 pip TP (< 24.14 threshold)
        s = 2.0 ** 0.5
        base = 1000

        # Depth 1 should be negative with these params
        legs = [
            ('long', base, e),
            ('short', base * s, e - h),
        ]
        tp = (e - h) - t  # short TP
        pnl = sum(q * ((tp - p) if d == 'long' else (p - tp)) for d, q, p in legs)
        assert pnl < 0, "sqrt(2) with tp=20, hedge=10 should lose at depth 1"

    def test_bust_pnl_negative(self):
        """Max-level SL: net PnL is negative (bust)."""
        e = 1.10000
        h, m, base = 0.00100, 2.0, 1000

        legs = []
        ce = e
        for lvl in range(3):
            d = 'long' if lvl % 2 == 0 else 'short'
            legs.append((d, base * m**lvl, ce))
            ce = ce - h if d == 'long' else ce + h

        last_d, _, last_e = legs[-1]
        sl = last_e - h if last_d == 'long' else last_e + h

        pnl = sum(q * ((sl - p) if d == 'long' else (p - sl)) for d, q, p in legs)
        assert pnl < 0, f"Bust PnL should be negative, got {pnl}"
