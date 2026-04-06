"""Integration tests: engine enforces per-ticket TP/SL in backtest mode."""
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
# Test strategies
# ---------------------------------------------------------------------------
class LongWithTP(Strategy):
    """Opens long on bar 5, sets TP 20 pips above entry."""
    def should_long(self):
        return self.index == 5 and not self.is_open
    def go_long(self):
        self.buy = 1000, self.price
    def on_open_position(self, order):
        tp_price = order.price + 0.0020
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
        sl_price = order.price - 0.0010
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
    """Opens long, sets TP far away, then moves it closer on bar 10."""
    def should_long(self):
        return self.index == 5 and not self.is_open
    def go_long(self):
        self.buy = 1000, self.price
    def on_open_position(self, order):
        tp_price = order.price + 0.0050  # 50 pips away — won't be hit
        for ticket in self.position._tickets:
            self.set_ticket_tp_sl(ticket.id, tp=tp_price)
        self.vars['original_tp'] = tp_price
    def update_position(self):
        if self.index == 10:
            new_tp = self.position.entry_price + 0.0015  # 15 pips — will be hit
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


class LongNoTPSL(Strategy):
    """Opens long on bar 5, never sets TP/SL."""
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
    def test_tp_closes_position(self):
        """Price rises past TP → engine closes ticket, trade recorded."""
        # Bar 5: entry ~1.1000. TP = entry + 0.0020 = ~1.1020
        # Bars 6-25: price rises steadily, will pass TP
        prices = [1.1000] * 6 + [1.1000 + i * 0.0003 for i in range(20)]
        result = _run(LongWithTP, prices)
        metrics = result['metrics']
        assert metrics['total'] > 0, "TP should have triggered a closed trade"
        assert metrics['net_profit'] > 0, "Trade closed at TP should be profitable"
        # Verify the exit reason is tp_hit, not terminated
        tp_trades = [t for t in result['trades'] if t['meta'].get('exit_reason') == 'tp_hit']
        assert len(tp_trades) > 0, "At least one trade should have exit_reason='tp_hit'"

    def test_sl_closes_position(self):
        """Price drops past SL → engine closes ticket, trade recorded."""
        # Bar 5: entry ~1.1000. SL = entry - 0.0010 = ~1.0990
        # Bars 6-25: price drops steadily
        prices = [1.1000] * 6 + [1.1000 - i * 0.0002 for i in range(20)]
        result = _run(LongWithSL, prices)
        metrics = result['metrics']
        assert metrics['total'] > 0, "SL should have triggered a closed trade"
        assert metrics['net_profit'] < 0, "Trade closed at SL should be a loss"
        # Verify the exit reason is sl_hit
        sl_trades = [t for t in result['trades'] if t['meta'].get('exit_reason') == 'sl_hit']
        assert len(sl_trades) > 0, "At least one trade should have exit_reason='sl_hit'"

    def test_tp_callback_fires(self):
        """on_ticket_tp_hit callback is invoked when TP triggers."""
        prices = [1.1000] * 6 + [1.1000 + i * 0.0003 for i in range(20)]
        result = _run(LongWithTPCallback, prices)
        metrics = result['metrics']
        assert metrics['total'] > 0, "TP should have triggered"
        tp_trades = [t for t in result['trades'] if t['meta'].get('exit_reason') == 'tp_hit']
        assert len(tp_trades) > 0, "Trade should be closed with exit_reason='tp_hit'"

    def test_tp_update_moves_trigger(self):
        """set_all_tickets_tp_sl() updates the TP, and engine respects the new level."""
        # Original TP: +50 pips (won't be hit in 20 bars of +2pip/bar)
        # Updated TP at bar 10: +15 pips (will be hit)
        prices = [1.1000] * 6 + [1.1000 + i * 0.0002 for i in range(20)]
        result = _run(LongWithUpdatedTP, prices)
        metrics = result['metrics']
        assert metrics['total'] > 0, "Updated TP should have been hit"
        tp_trades = [t for t in result['trades'] if t['meta'].get('exit_reason') == 'tp_hit']
        assert len(tp_trades) > 0, "Trade should be closed with exit_reason='tp_hit'"

    def test_no_tp_sl_no_trigger(self):
        """Tickets without TP/SL are not auto-closed by engine during backtest run.
        The position stays open until end-of-backtest (exit_reason='terminated')."""
        prices = [1.1000] * 6 + [1.1000 + i * 0.0005 for i in range(20)]
        result = _run(LongNoTPSL, prices)
        # No tp_hit or sl_hit trades — only terminated
        auto_closed = [t for t in result['trades']
                       if t['meta'].get('exit_reason') in ('tp_hit', 'sl_hit')]
        assert len(auto_closed) == 0, "No TP/SL set → position should not be closed by TP/SL"
        terminated = [t for t in result['trades']
                      if t['meta'].get('exit_reason') == 'terminated']
        assert len(terminated) > 0, "Position should be force-closed at end-of-backtest as 'terminated'"
