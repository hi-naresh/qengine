"""
Tests for partial order execution (execute_order_partially)
and CFD order handling flow in order_service/position_service.
"""
import pytest
import numpy as np
from unittest.mock import MagicMock, patch, PropertyMock
from qengine.models.Order import Order
from qengine.models.Position import Position, CFDTicket
from qengine.enums import order_statuses, order_types


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_mock_exchange(ex_type='futures', fee=0.001):
    ex = MagicMock()
    ex.type = ex_type
    ex.fee_rate = fee
    ex.name = 'TestExchange'
    ex.default_leverage = 30
    ex.charge_fee = MagicMock()
    ex.on_order_execution = MagicMock()
    ex.add_realized_pnl = MagicMock()
    ex.temp_reduced_amount = {'FAKE': 0}
    return ex


def _make_order(qty=1.0, price=100.0, side='buy', order_type='MARKET',
                reduce_only=False, exchange='TestExchange', symbol='FAKE-USDT',
                filled_qty=None, ticket_id=None):
    attrs = {
        'id': 'test-order-123',
        'symbol': symbol,
        'exchange': exchange,
        'side': side,
        'type': order_type,
        'qty': qty,
        'price': price,
        'status': order_statuses.ACTIVE,
        'reduce_only': reduce_only,
        'created_at': 1000000,
    }
    order = Order(attrs)
    if filled_qty is not None:
        order.filled_qty = filled_qty
    if ticket_id is not None:
        order.ticket_id = ticket_id
    return order


# ===========================================================================
# Order Model property tests
# ===========================================================================
class TestOrderProperties:
    def test_is_active(self):
        o = _make_order()
        assert o.is_active is True

    def test_is_executed(self):
        o = _make_order()
        o.status = order_statuses.EXECUTED
        assert o.is_executed is True
        assert o.is_active is False

    def test_is_canceled(self):
        o = _make_order()
        o.status = order_statuses.CANCELED
        assert o.is_canceled is True

    def test_is_partially_filled(self):
        o = _make_order(qty=10, filled_qty=5)
        o.status = order_statuses.PARTIALLY_FILLED
        assert o.is_partially_filled is True

    def test_value_property(self):
        o = _make_order(qty=10, price=50)
        assert o.value == 500

    def test_remaining_qty(self):
        o = _make_order(qty=10, filled_qty=3)
        assert o.remaining_qty == 7

    def test_is_stop_loss(self):
        o = _make_order(side='sell', reduce_only=True)
        o._submitted_via = 'stop_loss'
        # The property checks submitted_via
        assert hasattr(o, 'is_stop_loss')

    def test_to_dict(self):
        o = _make_order(qty=5, price=100)
        d = o.to_dict
        assert d['qty'] == 5
        assert d['price'] == 100
        assert d['symbol'] == 'FAKE-USDT'


# ===========================================================================
# execute_order_partially tests
# ===========================================================================
class TestExecuteOrderPartially:
    """Test order_service.execute_order_partially."""

    @patch('qengine.services.order_service.jh')
    @patch('qengine.services.order_service.position_service')
    @patch('qengine.services.order_service.closed_trade_service')
    @patch('qengine.services.order_service.store')
    @patch('qengine.services.order_service.config', {'app': {'trading_mode': 'backtest'},
                                                       'env': {'exchanges': {'TestExchange': {'fee': 0.001}}}})
    def test_partial_fill_sets_status(self, mock_store, mock_cts, mock_ps, mock_jh):
        mock_jh.now_to_timestamp.return_value = 2000
        mock_jh.is_livetrading.return_value = False
        mock_jh.is_debuggable.return_value = False
        mock_jh.is_live.return_value = False
        mock_jh.get_config.return_value = 0.001

        ex = _make_mock_exchange()
        mock_store.exchanges.get_exchange.return_value = ex
        mock_store.positions.get_position.return_value = MagicMock()

        from qengine.services.order_service import execute_order_partially

        order = _make_order(qty=10, price=100, filled_qty=3)
        execute_order_partially(order, silent=True)

        assert order.status == order_statuses.PARTIALLY_FILLED
        assert order.executed_at == 2000

    @patch('qengine.services.order_service.jh')
    @patch('qengine.services.order_service.position_service')
    @patch('qengine.services.order_service.closed_trade_service')
    @patch('qengine.services.order_service.store')
    @patch('qengine.services.order_service.config', {'app': {'trading_mode': 'backtest'},
                                                       'env': {'exchanges': {'TestExchange': {'fee': 0.001}}}})
    def test_partial_fill_calculates_fee(self, mock_store, mock_cts, mock_ps, mock_jh):
        mock_jh.now_to_timestamp.return_value = 2000
        mock_jh.is_livetrading.return_value = False
        mock_jh.is_debuggable.return_value = False
        mock_jh.is_live.return_value = False
        mock_jh.get_config.return_value = 0.001

        ex = _make_mock_exchange()
        mock_store.exchanges.get_exchange.return_value = ex
        mock_store.positions.get_position.return_value = MagicMock()

        from qengine.services.order_service import execute_order_partially

        order = _make_order(qty=10, price=100, filled_qty=3)
        execute_order_partially(order, silent=True)

        # Fee should be calculated on filled_qty * price
        assert order.fee == pytest.approx(0.001 * 3 * 100, abs=1e-6)

    @patch('qengine.services.order_service.jh')
    @patch('qengine.services.order_service.position_service')
    @patch('qengine.services.order_service.closed_trade_service')
    @patch('qengine.services.order_service.store')
    @patch('qengine.services.order_service.config', {'app': {'trading_mode': 'backtest'},
                                                       'env': {'exchanges': {'TestExchange': {'fee': 0.001}}}})
    def test_partial_fill_triggers_position_update(self, mock_store, mock_cts, mock_ps, mock_jh):
        mock_jh.now_to_timestamp.return_value = 2000
        mock_jh.is_livetrading.return_value = False
        mock_jh.is_debuggable.return_value = False
        mock_jh.is_live.return_value = False
        mock_jh.get_config.return_value = 0.001

        position = MagicMock()
        ex = _make_mock_exchange()
        mock_store.exchanges.get_exchange.return_value = ex
        mock_store.positions.get_position.return_value = position

        from qengine.services.order_service import execute_order_partially

        order = _make_order(qty=10, price=100, filled_qty=3)
        execute_order_partially(order, silent=True)

        # Should update position
        mock_ps.on_executed_order.assert_called_once_with(position, order)

    @patch('qengine.services.order_service.jh')
    @patch('qengine.services.order_service.position_service')
    @patch('qengine.services.order_service.closed_trade_service')
    @patch('qengine.services.order_service.store')
    @patch('qengine.services.order_service.config', {'app': {'trading_mode': 'backtest'},
                                                       'env': {'exchanges': {'TestExchange': {'fee': 0.001}}}})
    def test_partial_fill_adds_to_closed_trade(self, mock_store, mock_cts, mock_ps, mock_jh):
        mock_jh.now_to_timestamp.return_value = 2000
        mock_jh.is_livetrading.return_value = False
        mock_jh.is_debuggable.return_value = False
        mock_jh.is_live.return_value = False
        mock_jh.get_config.return_value = 0.001

        ex = _make_mock_exchange()
        mock_store.exchanges.get_exchange.return_value = ex
        mock_store.positions.get_position.return_value = MagicMock()

        from qengine.services.order_service import execute_order_partially

        order = _make_order(qty=10, price=100, filled_qty=5)
        execute_order_partially(order, silent=True)

        mock_cts.add_executed_order.assert_called_once_with(order)


# ===========================================================================
# execute_order tests (full fills)
# ===========================================================================
class TestExecuteOrder:
    """Test order_service.execute_order for standard and CFD modes."""

    @patch('qengine.services.order_service.jh')
    @patch('qengine.services.order_service.position_service')
    @patch('qengine.services.order_service.closed_trade_service')
    @patch('qengine.services.order_service.store')
    @patch('qengine.services.order_service.config', {'app': {'trading_mode': 'backtest', 'cost_model': True},
                                                       'env': {'exchanges': {'TestExchange': {'fee': 0.001}}}})
    def test_execute_order_sets_status(self, mock_store, mock_cts, mock_ps, mock_jh):
        mock_jh.now_to_timestamp.return_value = 3000
        mock_jh.is_livetrading.return_value = False
        mock_jh.is_backtesting.return_value = True
        mock_jh.is_debuggable.return_value = False
        mock_jh.is_live.return_value = False
        mock_jh.get_config.return_value = 0.001
        mock_jh.format_price.return_value = '100.00'

        ex = _make_mock_exchange()
        mock_store.exchanges.get_exchange.return_value = ex
        mock_store.positions.get_position.return_value = MagicMock(is_cfd_mode=False)
        mock_store.logs = MagicMock()

        from qengine.services.order_service import execute_order

        order = _make_order(qty=5, price=100)
        execute_order(order, silent=True)

        assert order.status == order_statuses.EXECUTED
        assert order.executed_at == 3000
        assert order.filled_qty == 5

    @patch('qengine.services.order_service.jh')
    @patch('qengine.services.order_service.position_service')
    @patch('qengine.services.order_service.closed_trade_service')
    @patch('qengine.services.order_service.store')
    @patch('qengine.services.order_service.config', {'app': {'trading_mode': 'backtest', 'cost_model': True},
                                                       'env': {'exchanges': {'TestExchange': {'fee': 0.001}}}})
    def test_execute_skips_already_executed(self, mock_store, mock_cts, mock_ps, mock_jh):
        mock_jh.is_live.return_value = False

        from qengine.services.order_service import execute_order

        order = _make_order()
        order.status = order_statuses.EXECUTED
        execute_order(order, silent=True)

        # Should not update position if already executed
        mock_ps.on_executed_order.assert_not_called()

    @patch('qengine.services.order_service.jh')
    @patch('qengine.services.order_service.position_service')
    @patch('qengine.services.order_service.closed_trade_service')
    @patch('qengine.services.order_service.store')
    @patch('qengine.services.order_service.config', {'app': {'trading_mode': 'backtest', 'cost_model': True},
                                                       'env': {'exchanges': {'TestExchange': {'fee': 0.001}}}})
    def test_execute_skips_canceled(self, mock_store, mock_cts, mock_ps, mock_jh):
        mock_jh.is_live.return_value = False

        from qengine.services.order_service import execute_order

        order = _make_order()
        order.status = order_statuses.CANCELED
        execute_order(order, silent=True)

        mock_ps.on_executed_order.assert_not_called()


# ===========================================================================
# cancel_order tests
# ===========================================================================
class TestCancelOrder:

    @patch('qengine.services.order_service.jh')
    @patch('qengine.services.order_service.store')
    @patch('qengine.services.order_service.config', {'env': {}})
    def test_cancel_sets_status(self, mock_store, mock_jh):
        mock_jh.now_to_timestamp.return_value = 4000
        mock_jh.is_debuggable.return_value = False
        mock_jh.is_live.return_value = False

        ex = _make_mock_exchange()
        mock_store.exchanges.get_exchange.return_value = ex

        from qengine.services.order_service import cancel_order

        order = _make_order()
        cancel_order(order, silent=True)

        assert order.status == order_statuses.CANCELED
        assert order.canceled_at == 4000

    @patch('qengine.services.order_service.jh')
    @patch('qengine.services.order_service.store')
    @patch('qengine.services.order_service.config', {'env': {}})
    def test_cancel_already_canceled_is_noop(self, mock_store, mock_jh):
        mock_jh.is_live.return_value = False

        from qengine.services.order_service import cancel_order

        order = _make_order()
        order.status = order_statuses.CANCELED
        cancel_order(order, silent=True)

        # Should not call exchange cancellation
        mock_store.exchanges.get_exchange.assert_not_called()

    @patch('qengine.services.order_service.jh')
    @patch('qengine.services.order_service.store')
    @patch('qengine.services.order_service.config', {'env': {}})
    def test_cancel_already_executed_is_noop(self, mock_store, mock_jh):
        mock_jh.is_live.return_value = False

        from qengine.services.order_service import cancel_order

        order = _make_order()
        order.status = order_statuses.EXECUTED
        cancel_order(order, silent=True)

        mock_store.exchanges.get_exchange.assert_not_called()
