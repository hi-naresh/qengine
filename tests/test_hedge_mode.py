"""
Tests for:
1. hedge_mode core patch — ConflictingRules gated properly
2. SurefireRecovery pure-logic unit tests (no QEngine runtime)
3. size_to_qty correct signature
"""
import sys, os
import pytest
from unittest.mock import PropertyMock, patch

# ─── QEngine test harness ───────────────────────────────────────────────────────
from qengine import exceptions
from qengine.enums import exchanges
from qengine.factories import candles_from_close_prices
from qengine.modes import backtest_mode
from qengine.store import store
from qengine.strategies import Strategy
from qengine.testing_utils import set_up
import qengine.helpers as jh


# ─── 1. ConflictingRules raised without hedge_mode ────────────────────────────

class _BothTrue(Strategy):
    """Both should_long and should_short return True — no hedge_mode."""
    def should_long(self): return self.position.is_close
    def should_short(self): return self.position.is_close
    def go_long(self):  self.buy  = 1, self.close
    def go_short(self): self.sell = 1, self.close


def test_conflicting_rules_raised_without_hedge_mode():
    set_up(is_futures_trading=True)
    routes  = [{'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': _BothTrue}]
    candles = {jh.key(exchanges.SANDBOX, 'BTC-USDT'): {
        'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USDT',
        'candles': candles_from_close_prices(range(1, 20)),
    }}
    with pytest.raises(exceptions.ConflictingRules):
        backtest_mode.run('000', False, {}, exchanges.SANDBOX, routes, [], '2019-04-01', '2019-04-02', candles)


# ─── 2. No exception when hedge_mode=True ────────────────────────────────────

class _BothTrueHedge(Strategy):
    def __init__(self):
        super().__init__()
        self.hedge_mode = True

    def should_long(self): return self.position.is_close
    def should_short(self): return self.position.is_close

    def go_long(self):  self.buy  = 0.001, self.close
    def go_short(self): self.sell = 0.001, self.close

    def update_position(self):
        if self.index >= 5:
            self.liquidate()


def test_no_conflicting_rules_with_hedge_mode():
    set_up(is_futures_trading=True)
    routes  = [{'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': _BothTrueHedge}]
    candles = {jh.key(exchanges.SANDBOX, 'BTC-USDT'): {
        'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USDT',
        'candles': candles_from_close_prices(range(100, 120)),
    }}
    # Must not raise
    backtest_mode.run('000', False, {}, exchanges.SANDBOX, routes, [], '2019-04-01', '2019-04-02', candles)


# ─── 3. hedge_mode defaults to False ─────────────────────────────────────────

def test_hedge_mode_defaults_to_false():
    class _S(Strategy):
        def should_long(self): return False
        def go_long(self): pass
    assert _S().hedge_mode is False


# ─── 4. SurefireRecovery — pure unit tests ───────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'algo-bot'))


def _make_surefire():
    from strategies.SurefireRecovery import SurefireRecovery
    return SurefireRecovery()


def test_surefire_hedge_mode_enabled():
    assert _make_surefire().hedge_mode is True


def test_surefire_initial_legs_empty():
    assert _make_surefire()._legs() == []


def test_surefire_reset_session():
    s = _make_surefire()
    s.vars.update({'legs': [{'x': 1}], 'zone_top': 1.1,
                   'zone_bottom': 0.9, 'last_trigger': 'bottom'})
    s._reset_session()
    assert s._legs() == []
    assert s._zone_top() is None
    assert s._zone_bottom() is None
    assert s._last_trigger() is None


def _close(s, price):
    """Patch close price for unit tests."""
    return patch.object(type(s), 'close', new_callable=PropertyMock, return_value=price)


def test_surefire_basket_pnl_empty():
    s = _make_surefire()
    with _close(s, 45000.0):
        assert s._basket_pnl() == 0.0


def test_surefire_basket_pnl_single_long():
    s = _make_surefire()
    s.vars['legs'] = [{'direction': 'long', 'entry': 40000.0, 'qty': 0.1, 'tp': 41000.0}]
    with _close(s, 41000.0):
        assert abs(s._basket_pnl() - 100.0) < 1e-6  # (41000-40000)*0.1


def test_surefire_basket_pnl_long_and_short():
    s = _make_surefire()
    s.vars['legs'] = [
        {'direction': 'long',  'entry': 40000.0, 'qty': 0.1,  'tp': 41000.0},
        {'direction': 'short', 'entry': 39800.0, 'qty': 0.15, 'tp': 38800.0},
    ]
    # price=39900: long=(39900-40000)*0.1=-10, short=(39800-39900)*0.15=-15, net=-25
    with _close(s, 39900.0):
        assert abs(s._basket_pnl() - (-25.0)) < 1e-6


def test_surefire_tp_long_hit():
    s = _make_surefire()
    s.vars['legs'] = [{'direction': 'long', 'entry': 40000.0, 'qty': 0.1, 'tp': 41000.0}]
    with _close(s, 41001.0): assert s._any_leg_hit_tp() is True
    with _close(s, 40999.0): assert s._any_leg_hit_tp() is False


def test_surefire_tp_short_hit():
    s = _make_surefire()
    s.vars['legs'] = [{'direction': 'short', 'entry': 40000.0, 'qty': 0.1, 'tp': 39000.0}]
    with _close(s, 38999.0): assert s._any_leg_hit_tp() is True
    with _close(s, 39001.0): assert s._any_leg_hit_tp() is False


def test_surefire_zone_bottom_crossing():
    s = _make_surefire()
    s.vars.update({'zone_top': 41000.0, 'zone_bottom': 39000.0, 'last_trigger': None})
    with _close(s, 38999.0): assert s._crossed_bottom() is True
    s.vars['last_trigger'] = 'bottom'
    with _close(s, 38999.0): assert s._crossed_bottom() is False  # retrigger guard


def test_surefire_zone_top_crossing():
    s = _make_surefire()
    s.vars.update({'zone_top': 41000.0, 'zone_bottom': 39000.0, 'last_trigger': None})
    with _close(s, 41001.0): assert s._crossed_top() is True
    s.vars['last_trigger'] = 'top'
    with _close(s, 41001.0): assert s._crossed_top() is False  # retrigger guard


def test_surefire_should_long_only_when_flat_and_no_legs():
    """should_long=True when direction=0 (buy), flat, no legs."""
    from strategies.SurefireRecovery import SurefireRecovery

    class _FlatPosition:
        is_close = True

    class _OpenPosition:
        is_close = False

    s = SurefireRecovery()
    s.hp['initial_direction'] = 0  # buy first
    s.position = _FlatPosition()
    assert s.should_long() is True   # flat + no legs + buy direction

    s.vars['legs'] = [{'direction': 'long', 'entry': 1.0, 'qty': 1.0, 'tp': 2.0}]
    assert s.should_long() is False  # legs exist → False

    s.vars['legs'] = []
    s.position = _OpenPosition()
    assert s.should_long() is False  # position open → False


def test_surefire_should_short_always_false():
    """should_short=False when initial_direction=0 (buy), True when direction=1 (sell)."""
    from strategies.SurefireRecovery import SurefireRecovery

    class _FlatPosition:
        is_close = True

    s0 = SurefireRecovery()
    s0.hp['initial_direction'] = 0   # buy first
    s0.position = _FlatPosition()
    assert s0.should_short() is False
    assert s0.should_long()  is True

    s1 = SurefireRecovery()
    s1.hp['initial_direction'] = 1   # sell first
    s1.position = _FlatPosition()
    assert s1.should_short() is True
    assert s1.should_long()  is False


def test_surefire_next_qty_multiplier():
    """Each successive leg uses lot_multiplier^n sizing."""
    from strategies.SurefireRecovery import SurefireRecovery
    s = SurefireRecovery()
    with patch.object(type(s), 'balance',  new_callable=PropertyMock, return_value=10000.0), \
         patch.object(type(s), 'leverage', new_callable=PropertyMock, return_value=1), \
         patch.object(type(s), 'close',    new_callable=PropertyMock, return_value=50000.0), \
         patch.object(type(s), 'fee_rate', new_callable=PropertyMock, return_value=0.001):
        q0 = s._next_qty()           # 0 legs → multiplier^0 = 1×
        s.vars['legs'] = [{}]
        q1 = s._next_qty()           # 1 leg  → multiplier^1 = 2×
        s.vars['legs'] = [{}, {}]
        q2 = s._next_qty()           # 2 legs → multiplier^2 = 4×

        # Allow tolerance of ±1 precision unit (0.000001)
        m = s.hp['lot_multiplier']   # 2.0
        assert abs(q1 / q0 - m)       < 0.01  # ~2×
        assert abs(q2 / q0 - m ** 2)  < 0.01  # ~4×


# ─── 5. size_to_qty API ──────────────────────────────────────────────────────

def test_size_to_qty_correct_signature():
    from qengine.utils import size_to_qty
    qty = size_to_qty(1000.0, 50000.0, precision=6, fee_rate=0.001)
    assert qty > 0 and isinstance(qty, float)


def test_size_to_qty_no_capital_kwarg():
    from qengine.utils import size_to_qty
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        size_to_qty(capital=1000.0, entry_price=50000.0)
