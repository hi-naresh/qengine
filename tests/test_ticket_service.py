"""Tests for qengine/services/ticket_service.py — pure TP/SL trigger logic."""
import pytest
from qengine.services.ticket_service import check_ticket_triggers


class FakeTicket:
    def __init__(self, ticket_type='long', tp_price=None, sl_price=None):
        self.type = ticket_type
        self.tp_price = tp_price
        self.sl_price = sl_price


# ---------------------------------------------------------------------------
# Long ticket — TP
# ---------------------------------------------------------------------------

class TestLongTP:
    def test_tp_hit_when_high_exceeds_tp(self):
        ticket = FakeTicket('long', tp_price=1.1050)
        result = check_ticket_triggers(ticket, high=1.1060, low=1.1000, open_price=1.1010, close_price=1.1055)
        assert result == {'reason': 'tp', 'price': 1.1050}

    def test_tp_not_hit_when_high_below_tp(self):
        ticket = FakeTicket('long', tp_price=1.1100)
        result = check_ticket_triggers(ticket, high=1.1060, low=1.1000, open_price=1.1010, close_price=1.1055)
        assert result is None

    def test_tp_exact_touch(self):
        ticket = FakeTicket('long', tp_price=1.1060)
        result = check_ticket_triggers(ticket, high=1.1060, low=1.1000, open_price=1.1010, close_price=1.1055)
        assert result == {'reason': 'tp', 'price': 1.1060}


# ---------------------------------------------------------------------------
# Short ticket — TP
# ---------------------------------------------------------------------------

class TestShortTP:
    def test_tp_hit_when_low_reaches_tp(self):
        ticket = FakeTicket('short', tp_price=1.0950)
        result = check_ticket_triggers(ticket, high=1.1010, low=1.0940, open_price=1.1000, close_price=1.0945)
        assert result == {'reason': 'tp', 'price': 1.0950}

    def test_tp_not_hit_when_low_above_tp(self):
        ticket = FakeTicket('short', tp_price=1.0900)
        result = check_ticket_triggers(ticket, high=1.1010, low=1.0940, open_price=1.1000, close_price=1.0945)
        assert result is None


# ---------------------------------------------------------------------------
# Long ticket — SL
# ---------------------------------------------------------------------------

class TestLongSL:
    def test_sl_hit_when_low_reaches_sl(self):
        ticket = FakeTicket('long', sl_price=1.0980)
        result = check_ticket_triggers(ticket, high=1.1020, low=1.0975, open_price=1.1000, close_price=1.0990)
        assert result == {'reason': 'sl', 'price': 1.0980}

    def test_sl_not_hit_when_low_above_sl(self):
        ticket = FakeTicket('long', sl_price=1.0950)
        result = check_ticket_triggers(ticket, high=1.1020, low=1.0975, open_price=1.1000, close_price=1.0990)
        assert result is None


# ---------------------------------------------------------------------------
# Short ticket — SL
# ---------------------------------------------------------------------------

class TestShortSL:
    def test_sl_hit_when_high_reaches_sl(self):
        ticket = FakeTicket('short', sl_price=1.1050)
        result = check_ticket_triggers(ticket, high=1.1055, low=1.1000, open_price=1.1010, close_price=1.1005)
        assert result == {'reason': 'sl', 'price': 1.1050}

    def test_sl_not_hit_when_high_below_sl(self):
        ticket = FakeTicket('short', sl_price=1.1100)
        result = check_ticket_triggers(ticket, high=1.1055, low=1.1000, open_price=1.1010, close_price=1.1005)
        assert result is None


# ---------------------------------------------------------------------------
# Edge cases: no TP/SL set
# ---------------------------------------------------------------------------

class TestNoTriggers:
    def test_neither_tp_nor_sl_returns_none(self):
        ticket = FakeTicket('long', tp_price=None, sl_price=None)
        result = check_ticket_triggers(ticket, high=1.1060, low=1.0990, open_price=1.1000, close_price=1.1050)
        assert result is None

    def test_tp_only_set_triggers_on_hit(self):
        ticket = FakeTicket('long', tp_price=1.1050, sl_price=None)
        result = check_ticket_triggers(ticket, high=1.1060, low=1.0990, open_price=1.1000, close_price=1.1050)
        assert result == {'reason': 'tp', 'price': 1.1050}

    def test_sl_only_set_triggers_on_hit(self):
        ticket = FakeTicket('long', tp_price=None, sl_price=1.0980)
        result = check_ticket_triggers(ticket, high=1.1060, low=1.0975, open_price=1.1000, close_price=1.0990)
        assert result == {'reason': 'sl', 'price': 1.0980}


# ---------------------------------------------------------------------------
# Both TP and SL hit — ohlc_walk mode
# ---------------------------------------------------------------------------

class TestBothHitOhlcWalk:
    """
    Candle where both TP and SL are within the [low, high] range.
    Long: TP=1.1050 (high side), SL=1.0990 (low side).
    Short: TP=1.0990 (low side), SL=1.1050 (high side).
    Candle: open=1.1020, close=1.1030 (green), high=1.1060, low=1.0985.
    """

    def test_long_green_candle_tp_wins(self):
        """Green candle: O→H→L→C — long TP (high side) is hit before SL."""
        ticket = FakeTicket('long', tp_price=1.1050, sl_price=1.0990)
        result = check_ticket_triggers(
            ticket, high=1.1060, low=1.0985, open_price=1.1020, close_price=1.1030, mode='ohlc_walk'
        )
        assert result == {'reason': 'tp', 'price': 1.1050}

    def test_short_green_candle_sl_wins(self):
        """Green candle: O→H→L→C — short SL (high side) is hit before TP."""
        ticket = FakeTicket('short', tp_price=1.0990, sl_price=1.1050)
        result = check_ticket_triggers(
            ticket, high=1.1060, low=1.0985, open_price=1.1020, close_price=1.1030, mode='ohlc_walk'
        )
        assert result == {'reason': 'sl', 'price': 1.1050}

    def test_long_red_candle_sl_wins(self):
        """Red candle: O→L→H→C — long SL (low side) is hit before TP."""
        ticket = FakeTicket('long', tp_price=1.1050, sl_price=1.0990)
        result = check_ticket_triggers(
            ticket, high=1.1060, low=1.0985, open_price=1.1030, close_price=1.1010, mode='ohlc_walk'
        )
        assert result == {'reason': 'sl', 'price': 1.0990}

    def test_short_red_candle_tp_wins(self):
        """Red candle: O→L→H→C — short TP (low side) is hit before SL."""
        ticket = FakeTicket('short', tp_price=1.0990, sl_price=1.1050)
        result = check_ticket_triggers(
            ticket, high=1.1060, low=1.0985, open_price=1.1030, close_price=1.1010, mode='ohlc_walk'
        )
        assert result == {'reason': 'tp', 'price': 1.0990}


# ---------------------------------------------------------------------------
# Both TP and SL hit — worst_case mode
# ---------------------------------------------------------------------------

class TestBothHitWorstCase:
    def test_long_worst_case_always_sl(self):
        ticket = FakeTicket('long', tp_price=1.1050, sl_price=1.0990)
        result = check_ticket_triggers(
            ticket, high=1.1060, low=1.0985, open_price=1.1020, close_price=1.1030, mode='worst_case'
        )
        assert result == {'reason': 'sl', 'price': 1.0990}

    def test_short_worst_case_always_sl(self):
        ticket = FakeTicket('short', tp_price=1.0990, sl_price=1.1050)
        result = check_ticket_triggers(
            ticket, high=1.1060, low=1.0985, open_price=1.1020, close_price=1.1030, mode='worst_case'
        )
        assert result == {'reason': 'sl', 'price': 1.1050}
