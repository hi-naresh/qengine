"""
PnL Truth Tests — verify that all PnL calculations are mathematically correct.

Tests CFDTicket.pnl(), Position.pnl, ClosedTrade.pnl, ClosedTrade.entry_price,
ClosedTrade.exit_price, ClosedTrade.roi, and edge cases.

Every assertion includes a comment with the hand-calculated expected value.
"""
import pytest
import numpy as np
from unittest.mock import MagicMock

from qengine.models.Position import Position, CFDTicket
from qengine.models.ClosedTrade import ClosedTrade
from qengine.libs.dynamic_numpy_array import DynamicNumpyArray


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_exchange(exchange_type='futures', fee_rate=0.001, default_leverage=1):
    ex = MagicMock()
    ex.type = exchange_type
    ex.fee_rate = fee_rate
    ex.default_leverage = default_leverage
    return ex


def _make_position(qty, entry_price, current_price, exchange_type='futures'):
    """Create a Position with fields set directly (no broker/store needed)."""
    ex = _mock_exchange(exchange_type)
    pos = Position.__new__(Position)
    pos._tickets = []
    pos.exchange = ex
    pos.exchange_name = 'test'
    pos.symbol = 'BTC-USDT'
    pos.qty = qty
    pos.entry_price = entry_price
    pos.current_price = current_price
    pos.opened_at = 1000000
    pos.closed_at = None
    pos.exit_price = None
    pos.strategy = None
    pos._mark_price = None
    pos._funding_rate = None
    pos._next_funding_timestamp = None
    pos._liquidation_price = None
    pos.previous_qty = 0
    pos.id = 'test-pos-1'
    return pos


def _make_closed_trade(trade_type, buy_orders, sell_orders, leverage=1, order_fees=None):
    """
    Create a ClosedTrade with explicit buy/sell order arrays.

    buy_orders / sell_orders: list of (qty, price) tuples
    order_fees: list of fee floats (one per order total), or None for zero fees
    """
    trade = ClosedTrade({
        'type': trade_type,
        'opened_at': 1000000,
        'closed_at': 2000000,
    })
    trade.leverage = leverage

    for qty, price in buy_orders:
        trade.buy_orders.append(np.array([qty, price]))
    for qty, price in sell_orders:
        trade.sell_orders.append(np.array([qty, price]))

    # Create mock order objects with fees
    total_orders = len(buy_orders) + len(sell_orders)
    if order_fees is None:
        order_fees = [0.0] * total_orders
    for fee in order_fees:
        mock_order = MagicMock()
        mock_order.fee = fee
        trade.orders.append(mock_order)

    return trade


# ===========================================================================
# 1. CFDTicket PnL
# ===========================================================================
class TestCFDTicketPnL:
    def test_long_win(self):
        # long qty=1000, entry=1.1000, current=1.1050
        # pnl = 1000 * (1.1050 - 1.1000) = 1000 * 0.005 = 5.0
        t = CFDTicket('long', 1000, 1.1000, 1000000)
        assert t.pnl(1.1050) == pytest.approx(5.0)

    def test_long_loss(self):
        # long qty=1000, entry=1.1000, current=1.0950
        # pnl = 1000 * (1.0950 - 1.1000) = 1000 * (-0.005) = -5.0
        t = CFDTicket('long', 1000, 1.1000, 1000000)
        assert t.pnl(1.0950) == pytest.approx(-5.0)

    def test_short_win(self):
        # short qty=1000, entry=1.1000, current=1.0950
        # diff = 1.0950 - 1.1000 = -0.005, negated = 0.005
        # pnl = 1000 * 0.005 = 5.0
        t = CFDTicket('short', 1000, 1.1000, 1000000)
        assert t.pnl(1.0950) == pytest.approx(5.0)

    def test_short_loss(self):
        # short qty=1000, entry=1.1000, current=1.1050
        # diff = 1.1050 - 1.1000 = 0.005, negated = -0.005
        # pnl = 1000 * (-0.005) = -5.0
        t = CFDTicket('short', 1000, 1.1000, 1000000)
        assert t.pnl(1.1050) == pytest.approx(-5.0)

    def test_zero_pnl(self):
        # price == entry => pnl = 0
        t = CFDTicket('long', 1000, 1.1000, 1000000)
        assert t.pnl(1.1000) == pytest.approx(0.0)

    def test_zero_pnl_short(self):
        # price == entry => pnl = 0 for short too
        t = CFDTicket('short', 1000, 1.1000, 1000000)
        assert t.pnl(1.1000) == pytest.approx(0.0)

    def test_fractional_qty(self):
        # long qty=0.5, entry=50000, current=50100
        # pnl = 0.5 * (50100 - 50000) = 0.5 * 100 = 50.0
        t = CFDTicket('long', 0.5, 50000, 1000000)
        assert t.pnl(50100) == pytest.approx(50.0)

    def test_negative_qty_normalized(self):
        # CFDTicket stores abs(qty), so passing -1000 should give qty=1000
        t = CFDTicket('long', -1000, 1.1000, 1000000)
        assert t.qty == 1000
        # pnl = 1000 * (1.1050 - 1.1000) = 5.0
        assert t.pnl(1.1050) == pytest.approx(5.0)

    def test_large_pip_move(self):
        # long qty=100000, entry=1.1000, current=1.2000 (1000 pip move)
        # pnl = 100000 * 0.1 = 10000.0
        t = CFDTicket('long', 100000, 1.1000, 1000000)
        assert t.pnl(1.2000) == pytest.approx(10000.0)

    def test_tiny_pip_move(self):
        # long qty=1000, entry=1.10000, current=1.10001 (0.1 pip)
        # pnl = 1000 * 0.00001 = 0.01
        t = CFDTicket('long', 1000, 1.10000, 1000000)
        assert t.pnl(1.10001) == pytest.approx(0.01)


# ===========================================================================
# 2. Position PnL (non-CFD / futures mode)
# ===========================================================================
class TestPositionPnL:
    def test_long_position_profit(self):
        # long: qty=10, entry=100, current=110
        # value = abs(110 * 10) = 1100
        # cost = abs(100 * 10) = 1000
        # pnl = 1100 - 1000 = 100
        pos = _make_position(qty=10, entry_price=100, current_price=110)
        assert pos.pnl == pytest.approx(100.0)

    def test_long_position_loss(self):
        # long: qty=10, entry=100, current=90
        # value = 900, cost = 1000, pnl = 900 - 1000 = -100
        pos = _make_position(qty=10, entry_price=100, current_price=90)
        assert pos.pnl == pytest.approx(-100.0)

    def test_short_position_profit(self):
        # short: qty=-10, entry=100, current=90
        # value = abs(90 * -10) = 900
        # cost = abs(100 * -10) = 1000
        # diff = 900 - 1000 = -100
        # short => pnl = -(-100) = 100
        pos = _make_position(qty=-10, entry_price=100, current_price=90)
        assert pos.pnl == pytest.approx(100.0)

    def test_short_position_loss(self):
        # short: qty=-10, entry=100, current=110
        # value = 1100, cost = 1000
        # diff = 1100 - 1000 = 100
        # short => pnl = -100
        pos = _make_position(qty=-10, entry_price=100, current_price=110)
        assert pos.pnl == pytest.approx(-100.0)

    def test_zero_move(self):
        # price unchanged => pnl = 0
        pos = _make_position(qty=5, entry_price=100, current_price=100)
        assert pos.pnl == pytest.approx(0.0)

    def test_value_property(self):
        # value = abs(current_price * qty)
        # qty=10, current=110 => value = 1100
        pos = _make_position(qty=10, entry_price=100, current_price=110)
        assert pos.value == pytest.approx(1100.0)

    def test_value_short_position(self):
        # value = abs(90 * -10) = 900
        pos = _make_position(qty=-10, entry_price=100, current_price=90)
        assert pos.value == pytest.approx(900.0)

    def test_fractional_btc(self):
        # long: qty=0.01, entry=50000, current=51000
        # pnl = abs(51000*0.01) - abs(50000*0.01) = 510 - 500 = 10
        pos = _make_position(qty=0.01, entry_price=50000, current_price=51000)
        assert pos.pnl == pytest.approx(10.0)


# ===========================================================================
# 3. Position PnL in CFD mode (summing tickets)
# ===========================================================================
class TestPositionCFDPnL:
    def test_single_long_ticket(self):
        # one long ticket: qty=1000, entry=1.1000, current=1.1050
        # pnl = 1000 * 0.005 = 5.0
        pos = _make_position(qty=1000, entry_price=1.1000, current_price=1.1050,
                             exchange_type='cfd')
        pos._tickets = [CFDTicket('long', 1000, 1.1000, 1000000)]
        assert pos.pnl == pytest.approx(5.0)

    def test_multiple_tickets_summed(self):
        # ticket1: long qty=1000, entry=1.1000, current=1.1050 => pnl = 5.0
        # ticket2: short qty=500, entry=1.1020, current=1.1050 => pnl = 500*(-0.003) = -1.5
        # total = 5.0 + (-1.5) = 3.5
        pos = _make_position(qty=500, entry_price=1.1000, current_price=1.1050,
                             exchange_type='cfd')
        pos._tickets = [
            CFDTicket('long', 1000, 1.1000, 1000000),
            CFDTicket('short', 500, 1.1020, 1000000),
        ]
        assert pos.pnl == pytest.approx(3.5)

    def test_empty_tickets_returns_zero(self):
        # CFD mode but no tickets => falls through to normal calc
        pos = _make_position(qty=0, entry_price=1.1000, current_price=1.1050,
                             exchange_type='cfd')
        pos._tickets = []
        # qty=0 => pnl = 0
        assert pos.pnl == pytest.approx(0.0)


# ===========================================================================
# 4. ClosedTrade PnL
# ===========================================================================
class TestClosedTradePnL:
    def test_long_profit_no_fee(self):
        # long: qty=10, entry=100, exit=110, fee=0
        # pnl = 10 * (110 - 100) = 100
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 110)],
        )
        assert trade.pnl == pytest.approx(100.0)

    def test_long_loss_no_fee(self):
        # long: qty=10, entry=100, exit=90, fee=0
        # pnl = 10 * (90 - 100) = -100
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 90)],
        )
        assert trade.pnl == pytest.approx(-100.0)

    def test_short_profit_no_fee(self):
        # short: qty=10, entry=100, exit=90, fee=0
        # profit = 10 * (90 - 100) = -100, then *-1 = 100
        trade = _make_closed_trade(
            'short',
            buy_orders=[(10, 90)],
            sell_orders=[(10, 100)],
        )
        assert trade.pnl == pytest.approx(100.0)

    def test_short_loss_no_fee(self):
        # short: qty=10, entry=100, exit=110, fee=0
        # profit = 10 * (110 - 100) = 100, then *-1 = -100
        trade = _make_closed_trade(
            'short',
            buy_orders=[(10, 110)],
            sell_orders=[(10, 100)],
        )
        assert trade.pnl == pytest.approx(-100.0)

    def test_long_profit_with_fee(self):
        # long: qty=10, entry=100, exit=110
        # raw pnl = 10 * (110-100) = 100
        # fees: 1.0 (buy) + 1.1 (sell) = 2.1
        # net pnl = 100 - 2.1 = 97.9
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 110)],
            order_fees=[1.0, 1.1],
        )
        assert trade.pnl == pytest.approx(97.9)

    def test_fee_turns_profit_to_loss(self):
        # long: qty=10, entry=100, exit=100.5
        # raw pnl = 10 * 0.5 = 5.0
        # fees: 3.0 + 3.0 = 6.0
        # net pnl = 5.0 - 6.0 = -1.0
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 100.5)],
            order_fees=[3.0, 3.0],
        )
        assert trade.pnl == pytest.approx(-1.0)

    def test_entry_price_weighted_avg_long(self):
        # long with two buy fills:
        # buy 6 @ 100 + buy 4 @ 105
        # weighted entry = (6*100 + 4*105) / (6+4) = (600+420)/10 = 102.0
        trade = _make_closed_trade(
            'long',
            buy_orders=[(6, 100), (4, 105)],
            sell_orders=[(10, 110)],
        )
        assert trade.entry_price == pytest.approx(102.0)
        assert trade.qty == pytest.approx(10.0)

    def test_exit_price_weighted_avg_long(self):
        # long with two sell fills:
        # sell 7 @ 110 + sell 3 @ 115
        # weighted exit = (7*110 + 3*115) / (7+3) = (770+345)/10 = 111.5
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(7, 110), (3, 115)],
        )
        assert trade.exit_price == pytest.approx(111.5)

    def test_entry_price_weighted_avg_short(self):
        # short: entry = weighted avg of sell_orders
        # sell 5 @ 200 + sell 5 @ 210
        # weighted entry = (5*200 + 5*210) / 10 = 2050/10 = 205.0
        trade = _make_closed_trade(
            'short',
            buy_orders=[(10, 190)],
            sell_orders=[(5, 200), (5, 210)],
        )
        assert trade.entry_price == pytest.approx(205.0)

    def test_exit_price_weighted_avg_short(self):
        # short: exit = weighted avg of buy_orders
        # buy 3 @ 190 + buy 7 @ 195
        # weighted exit = (3*190 + 7*195) / 10 = (570+1365)/10 = 193.5
        trade = _make_closed_trade(
            'short',
            buy_orders=[(3, 190), (7, 195)],
            sell_orders=[(10, 200)],
        )
        assert trade.exit_price == pytest.approx(193.5)

    def test_pnl_with_multiple_fills(self):
        # long: buy 6@100 + buy 4@105 => entry = 102
        #        sell 7@110 + sell 3@115 => exit = 111.5
        # qty = 10
        # pnl = 10 * (111.5 - 102) = 10 * 9.5 = 95.0
        trade = _make_closed_trade(
            'long',
            buy_orders=[(6, 100), (4, 105)],
            sell_orders=[(7, 110), (3, 115)],
        )
        assert trade.pnl == pytest.approx(95.0)

    def test_size_property(self):
        # size = qty * entry_price = 10 * 100 = 1000
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 110)],
        )
        assert trade.size == pytest.approx(1000.0)


# ===========================================================================
# 5. ClosedTrade ROI
# ===========================================================================
class TestClosedTradeROI:
    def test_roi_basic_long(self):
        # long: entry=100, qty=10, leverage=1
        # total_cost = 100 * 10 / 1 = 1000
        # pnl = 10 * (110 - 100) = 100
        # roi = 100 / 1000 * 100 = 10.0%
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 110)],
            leverage=1,
        )
        assert trade.roi == pytest.approx(10.0)

    def test_roi_with_leverage(self):
        # long: entry=100, qty=10, leverage=5
        # total_cost = 100 * 10 / 5 = 200
        # pnl = 10 * (110 - 100) = 100
        # roi = 100 / 200 * 100 = 50.0%
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 110)],
            leverage=5,
        )
        assert trade.roi == pytest.approx(50.0)

    def test_roi_negative(self):
        # long: entry=100, qty=10, leverage=1
        # total_cost = 1000
        # pnl = 10 * (95 - 100) = -50
        # roi = -50 / 1000 * 100 = -5.0%
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 95)],
            leverage=1,
        )
        assert trade.roi == pytest.approx(-5.0)

    def test_roi_short_with_leverage(self):
        # short: entry (sell_orders) = 100, qty=10, leverage=10
        # total_cost = 100 * 10 / 10 = 100
        # pnl = 10 * (90 - 100) * -1 = 100
        # roi = 100 / 100 * 100 = 100.0%
        trade = _make_closed_trade(
            'short',
            buy_orders=[(10, 90)],
            sell_orders=[(10, 100)],
            leverage=10,
        )
        assert trade.roi == pytest.approx(100.0)

    def test_roi_with_fees(self):
        # long: entry=100, qty=10, leverage=1
        # total_cost = 1000
        # raw pnl = 10 * (110-100) = 100, fee=5, net pnl=95
        # roi = 95 / 1000 * 100 = 9.5%
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 110)],
            leverage=1,
            order_fees=[2.5, 2.5],
        )
        assert trade.roi == pytest.approx(9.5)

    def test_total_cost_property(self):
        # entry=100, qty=10, leverage=2
        # total_cost = 100 * 10 / 2 = 500
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 110)],
            leverage=2,
        )
        assert trade.total_cost == pytest.approx(500.0)


# ===========================================================================
# 6. Edge Cases
# ===========================================================================
class TestPnLEdgeCases:
    def test_cfd_ticket_zero_qty(self):
        # qty=0 => pnl = 0 regardless of price move
        t = CFDTicket('long', 0, 1.1000, 1000000)
        assert t.pnl(1.2000) == pytest.approx(0.0)

    def test_cfd_ticket_zero_entry_price(self):
        # entry=0, current=100 => pnl = 1000 * (100 - 0) = 100000
        t = CFDTicket('long', 1000, 0.0, 1000000)
        assert t.pnl(100.0) == pytest.approx(100000.0)

    def test_very_large_position(self):
        # qty=1_000_000, entry=1.1000, current=1.1001 (0.1 pip)
        # pnl = 1_000_000 * 0.0001 = 100.0
        t = CFDTicket('long', 1_000_000, 1.1000, 1000000)
        assert t.pnl(1.1001) == pytest.approx(100.0)

    def test_very_small_pip_move(self):
        # qty=1, entry=1.00000, current=1.00001 (0.01 pip)
        # pnl = 1 * 0.00001 = 0.00001
        t = CFDTicket('long', 1, 1.00000, 1000000)
        assert t.pnl(1.00001) == pytest.approx(0.00001)

    def test_position_zero_qty(self):
        # qty=0 => pnl should be 0
        pos = _make_position(qty=0, entry_price=100, current_price=110)
        assert pos.pnl == pytest.approx(0.0)

    def test_position_none_current_price(self):
        # current_price=None => value=None => pnl=0
        pos = _make_position(qty=10, entry_price=100, current_price=None)
        assert pos.pnl == pytest.approx(0.0)

    def test_closed_trade_holding_period(self):
        # opened_at=1000000, closed_at=2000000
        # holding = (2000000 - 1000000) / 1000 = 1000 seconds
        trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 110)],
        )
        assert trade.holding_period == pytest.approx(1000.0)

    def test_closed_trade_symmetry(self):
        # A long +10 from 100->110 and a short +10 from 110->100
        # should yield the same PnL
        long_trade = _make_closed_trade(
            'long',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 110)],
        )
        short_trade = _make_closed_trade(
            'short',
            buy_orders=[(10, 100)],
            sell_orders=[(10, 110)],
        )
        # long pnl = 10*(110-100) = 100
        # short pnl = 10*(100-110)*-1 = 100  (entry=sell@110, exit=buy@100)
        # Wait — for short, entry = sell_orders, exit = buy_orders
        # short entry = 110, exit = 100
        # pnl = 10*(100-110)*-1 = 100
        assert long_trade.pnl == pytest.approx(short_trade.pnl)

    def test_cfd_ticket_short_large_adverse_move(self):
        # short qty=10000, entry=1.1000, current=1.2000 (1000 pips against)
        # diff = 1.2000 - 1.1000 = 0.1, negated = -0.1
        # pnl = 10000 * (-0.1) = -1000.0
        t = CFDTicket('short', 10000, 1.1000, 1000000)
        assert t.pnl(1.2000) == pytest.approx(-1000.0)

    def test_many_partial_fills(self):
        # 5 buy fills at different prices, 3 sell fills
        # buys: 2@100, 3@102, 5@104, 1@106, 4@108
        # total qty = 15
        # weighted entry = (200+306+520+106+432)/15 = 1564/15 = 104.2667
        # sells: 5@112, 5@114, 5@110
        # weighted exit = (560+570+550)/15 = 1680/15 = 112.0
        # pnl = 15 * (112.0 - 104.2667) = 15 * 7.7333 = 116.0
        trade = _make_closed_trade(
            'long',
            buy_orders=[(2, 100), (3, 102), (5, 104), (1, 106), (4, 108)],
            sell_orders=[(5, 112), (5, 114), (5, 110)],
        )
        expected_entry = (2*100 + 3*102 + 5*104 + 1*106 + 4*108) / 15
        expected_exit = (5*112 + 5*114 + 5*110) / 15
        expected_pnl = 15 * (expected_exit - expected_entry)
        assert trade.entry_price == pytest.approx(expected_entry)
        assert trade.exit_price == pytest.approx(expected_exit)
        assert trade.pnl == pytest.approx(expected_pnl)
        # hand calc: entry=104.2667, exit=112.0, pnl=116.0
        assert trade.pnl == pytest.approx(116.0)
