"""
Tests for the CFDTicket system: open_ticket, close_ticket, close_all_tickets,
pnl(), _sync_from_tickets, and _handle_cfd_order in position_service.
"""
import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from qengine.models.Position import Position, CFDTicket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_cfd_exchange():
    """Create a mock exchange with type='cfd'."""
    ex = MagicMock()
    ex.type = 'cfd'
    ex.default_leverage = 30
    ex.fee_rate = 0
    return ex


def _make_cfd_position(**kwargs):
    """Create a Position in CFD mode."""
    ex = _make_cfd_exchange()
    p = Position({
        'exchange': ex,
        'exchange_name': 'TestCFD',
        'symbol': 'EUR-USD',
        'current_price': kwargs.get('current_price', 1.1000),
    })
    return p


# ===========================================================================
# CFDTicket unit tests
# ===========================================================================
class TestCFDTicket:
    def test_init_long(self):
        t = CFDTicket('long', 10000, 1.1000, 1000000)
        assert t.type == 'long'
        assert t.qty == 10000
        assert t.entry_price == 1.1000
        assert t.opened_at == 1000000
        assert t.exchange_trade_id is None
        assert t.id is not None

    def test_init_short(self):
        t = CFDTicket('short', -5000, 1.2000, 2000000)
        assert t.type == 'short'
        assert t.qty == 5000  # always abs
        assert t.entry_price == 1.2000

    def test_pnl_long_profit(self):
        t = CFDTicket('long', 10000, 1.1000, 0)
        pnl = t.pnl(1.1050)
        assert pnl == pytest.approx(10000 * 0.0050, abs=1e-6)

    def test_pnl_long_loss(self):
        t = CFDTicket('long', 10000, 1.1000, 0)
        pnl = t.pnl(1.0950)
        assert pnl == pytest.approx(10000 * -0.0050, abs=1e-6)

    def test_pnl_short_profit(self):
        t = CFDTicket('short', 10000, 1.1000, 0)
        pnl = t.pnl(1.0950)
        assert pnl == pytest.approx(10000 * 0.0050, abs=1e-6)

    def test_pnl_short_loss(self):
        t = CFDTicket('short', 10000, 1.1000, 0)
        pnl = t.pnl(1.1050)
        assert pnl == pytest.approx(10000 * -0.0050, abs=1e-6)

    def test_pnl_zero_when_price_unchanged(self):
        t = CFDTicket('long', 10000, 1.1000, 0)
        assert t.pnl(1.1000) == 0.0

    def test_to_dict(self):
        t = CFDTicket('long', 5000, 1.1000, 100)
        d = t.to_dict()
        assert d['type'] == 'long'
        assert d['qty'] == 5000
        assert d['entry_price'] == 1.1000
        assert d['opened_at'] == 100
        assert d['id'] == t.id
        assert d['exchange_trade_id'] is None

    def test_exchange_trade_id_can_be_set(self):
        t = CFDTicket('long', 1000, 1.1, 0)
        t.exchange_trade_id = 'OANDA-123'
        assert t.exchange_trade_id == 'OANDA-123'
        assert t.to_dict()['exchange_trade_id'] == 'OANDA-123'


# ===========================================================================
# Position CFD ticket management
# ===========================================================================
class TestPositionTicketManagement:
    def test_is_cfd_mode(self):
        p = _make_cfd_position()
        assert p.is_cfd_mode is True

    def test_is_not_cfd_mode_for_futures(self):
        ex = MagicMock()
        ex.type = 'futures'
        p = Position({'exchange': ex})
        assert p.is_cfd_mode is False

    def test_is_not_cfd_mode_without_exchange(self):
        p = Position()
        assert p.is_cfd_mode is False

    def test_open_ticket_long(self):
        p = _make_cfd_position()
        ticket = p.open_ticket('long', 10000, 1.1000, 100)
        assert isinstance(ticket, CFDTicket)
        assert ticket.type == 'long'
        assert ticket.qty == 10000
        assert p.ticket_count == 1
        assert p.qty == 10000
        assert p.entry_price == 1.1000

    def test_open_ticket_short(self):
        p = _make_cfd_position()
        ticket = p.open_ticket('short', 5000, 1.2000, 200)
        assert ticket.type == 'short'
        assert p.qty == -5000
        assert p.ticket_count == 1

    def test_open_multiple_same_direction(self):
        p = _make_cfd_position()
        p.open_ticket('long', 10000, 1.1000, 100)
        p.open_ticket('long', 5000, 1.1020, 200)

        assert p.ticket_count == 2
        assert p.qty == 15000
        # Weighted average entry
        expected_entry = (10000 * 1.1000 + 5000 * 1.1020) / 15000
        assert p.entry_price == pytest.approx(expected_entry, abs=1e-8)

    def test_open_opposing_tickets_hedged(self):
        """In CFD mode, opposing tickets coexist (hedging)."""
        p = _make_cfd_position()
        p.open_ticket('long', 10000, 1.1000, 100)
        p.open_ticket('short', 10000, 1.1050, 200)

        assert p.ticket_count == 2
        # Net qty should be 0
        assert p.qty == 0

    def test_gross_exposure_with_hedge(self):
        p = _make_cfd_position()
        p.open_ticket('long', 10000, 1.1000, 100)
        p.open_ticket('short', 5000, 1.1050, 200)

        assert p.gross_exposure == 15000  # sum of abs qty
        assert p.qty == 5000  # net is long 5000

    def test_is_open_with_tickets(self):
        p = _make_cfd_position()
        assert p.is_close is True
        assert p.is_open is False

        p.open_ticket('long', 1000, 1.1, 100)
        assert p.is_open is True
        assert p.is_close is False

    def test_is_close_after_closing_all(self):
        p = _make_cfd_position()
        p.open_ticket('long', 1000, 1.1, 100)
        p.close_all_tickets(1.1050)

        assert p.is_close is True
        assert p.ticket_count == 0
        assert p.qty == 0

    def test_close_ticket_by_id(self):
        p = _make_cfd_position()
        t1 = p.open_ticket('long', 10000, 1.1000, 100)
        t2 = p.open_ticket('long', 5000, 1.1020, 200)

        result = p.close_ticket(t1.id, 1.1050)
        assert result is not None
        assert result['ticket'].id == t1.id
        assert result['pnl'] == pytest.approx(10000 * 0.0050, abs=1e-6)

        # t2 should still be open
        assert p.ticket_count == 1
        assert p.qty == 5000

    def test_close_ticket_nonexistent(self):
        p = _make_cfd_position()
        result = p.close_ticket('nonexistent-id', 1.1)
        assert result is None

    def test_close_all_tickets(self):
        p = _make_cfd_position()
        p.open_ticket('long', 10000, 1.1000, 100)
        p.open_ticket('short', 5000, 1.1050, 200)

        results = p.close_all_tickets(1.1025)
        assert len(results) == 2

        # Long ticket PnL: 10000 * (1.1025 - 1.1000) = 25
        # Short ticket PnL: 5000 * (1.1050 - 1.1025) = 12.5
        total_pnl = sum(r['pnl'] for r in results)
        assert total_pnl == pytest.approx(25 + 12.5, abs=1e-4)

        assert p.qty == 0
        assert p.ticket_count == 0
        assert p.exit_price == 1.1025

    def test_get_ticket(self):
        p = _make_cfd_position()
        t = p.open_ticket('long', 1000, 1.1, 100)
        found = p.get_ticket(t.id)
        assert found is t
        assert p.get_ticket('nonexistent') is None

    def test_tickets_property_returns_copy(self):
        p = _make_cfd_position()
        p.open_ticket('long', 1000, 1.1, 100)
        tickets = p.tickets
        assert len(tickets) == 1
        # Modifying the copy should not affect the internal list
        tickets.clear()
        assert p.ticket_count == 1

    def test_sync_from_tickets_empty(self):
        p = _make_cfd_position()
        p.open_ticket('long', 1000, 1.1, 100)
        assert p.qty == 1000
        # Manually empty tickets
        p._tickets = []
        p._sync_from_tickets()
        assert p.qty == 0

    def test_previous_qty_tracked(self):
        p = _make_cfd_position()
        assert p.qty == 0
        p.open_ticket('long', 1000, 1.1, 100)
        assert p.previous_qty == 0
        p.open_ticket('long', 500, 1.12, 200)
        assert p.previous_qty == 1000

    def test_pnl_cfd_mode_sums_tickets(self):
        p = _make_cfd_position(current_price=1.1050)
        p.open_ticket('long', 10000, 1.1000, 100)
        p.open_ticket('short', 5000, 1.1100, 200)

        # Long PnL: 10000 * (1.1050 - 1.1000) = 50
        # Short PnL: 5000 * (1.1100 - 1.1050) = 25
        assert p.pnl == pytest.approx(75.0, abs=1e-4)

    def test_pnl_cfd_mode_no_tickets(self):
        p = _make_cfd_position(current_price=1.1)
        assert p.pnl == 0

    def test_close_ticket_sets_exit_price_when_last(self):
        p = _make_cfd_position()
        t = p.open_ticket('long', 1000, 1.1, 100)
        p.close_ticket(t.id, 1.15)
        assert p.exit_price == 1.15
        assert p.closed_at is not None

    def test_close_ticket_does_not_set_exit_when_more_open(self):
        p = _make_cfd_position()
        t1 = p.open_ticket('long', 1000, 1.1, 100)
        t2 = p.open_ticket('short', 500, 1.12, 200)
        p.close_ticket(t1.id, 1.15)
        # Still has t2 open
        assert p.exit_price is None or p.ticket_count > 0


# ===========================================================================
# _handle_cfd_order tests (position_service)
# ===========================================================================
class TestHandleCfdOrder:
    """Tests for position_service._handle_cfd_order."""

    def _make_mock_order(self, qty, price, reduce_only=False, ticket_id=None):
        order = MagicMock()
        order.qty = qty
        order.price = price
        order.reduce_only = reduce_only
        order.ticket_id = ticket_id
        order.vars = {}
        return order

    @patch('qengine.services.position_service.jh')
    @patch('qengine.services.position_service.closed_trade_service')
    @patch('qengine.services.position_service.logger')
    def test_open_new_ticket(self, mock_logger, mock_cts, mock_jh):
        mock_jh.now_to_timestamp.return_value = 1000
        p = _make_cfd_position()

        from qengine.services.position_service import _handle_cfd_order
        order = self._make_mock_order(qty=10000, price=1.1000)

        _handle_cfd_order(p, order)

        assert p.ticket_count == 1
        assert p.tickets[0].type == 'long'
        assert p.tickets[0].qty == 10000

    @patch('qengine.services.position_service.jh')
    @patch('qengine.services.position_service.closed_trade_service')
    @patch('qengine.services.position_service.logger')
    def test_open_short_ticket(self, mock_logger, mock_cts, mock_jh):
        mock_jh.now_to_timestamp.return_value = 1000
        p = _make_cfd_position()

        from qengine.services.position_service import _handle_cfd_order
        order = self._make_mock_order(qty=-5000, price=1.1050)

        _handle_cfd_order(p, order)

        assert p.ticket_count == 1
        assert p.tickets[0].type == 'short'

    @patch('qengine.services.position_service.jh')
    @patch('qengine.services.position_service.closed_trade_service')
    @patch('qengine.services.position_service.logger')
    def test_close_specific_ticket(self, mock_logger, mock_cts, mock_jh):
        mock_jh.now_to_timestamp.return_value = 1000
        p = _make_cfd_position()
        t = p.open_ticket('long', 10000, 1.1000, 100)

        from qengine.services.position_service import _handle_cfd_order
        order = self._make_mock_order(qty=-10000, price=1.1050, reduce_only=True, ticket_id=t.id)

        _handle_cfd_order(p, order)

        assert p.ticket_count == 0
        assert p.exchange.add_realized_pnl.called

    @patch('qengine.services.position_service.jh')
    @patch('qengine.services.position_service.closed_trade_service')
    @patch('qengine.services.position_service.logger')
    def test_close_all_tickets_via_reduce_only(self, mock_logger, mock_cts, mock_jh):
        mock_jh.now_to_timestamp.return_value = 1000
        p = _make_cfd_position()
        p.open_ticket('long', 10000, 1.1000, 100)
        p.open_ticket('short', 5000, 1.1050, 200)

        from qengine.services.position_service import _handle_cfd_order
        # reduce_only with no ticket_id → close all
        order = self._make_mock_order(qty=-5000, price=1.1025, reduce_only=True, ticket_id=None)

        _handle_cfd_order(p, order)

        assert p.ticket_count == 0

    @patch('qengine.services.position_service.jh')
    @patch('qengine.services.position_service.closed_trade_service')
    @patch('qengine.services.position_service.logger')
    def test_oanda_trade_id_stored_on_ticket(self, mock_logger, mock_cts, mock_jh):
        mock_jh.now_to_timestamp.return_value = 1000
        p = _make_cfd_position()

        from qengine.services.position_service import _handle_cfd_order
        order = self._make_mock_order(qty=10000, price=1.1)
        order.vars = {'trade_id': 'OANDA-456'}

        _handle_cfd_order(p, order)

        assert p.tickets[0].exchange_trade_id == 'OANDA-456'

    @patch('qengine.services.position_service.jh')
    @patch('qengine.services.position_service.closed_trade_service')
    @patch('qengine.services.position_service.logger')
    def test_first_ticket_sets_opened_at(self, mock_logger, mock_cts, mock_jh):
        mock_jh.now_to_timestamp.return_value = 5000
        p = _make_cfd_position()
        assert p.opened_at is None

        from qengine.services.position_service import _handle_cfd_order
        order = self._make_mock_order(qty=10000, price=1.1)

        _handle_cfd_order(p, order)

        assert p.opened_at == 5000
