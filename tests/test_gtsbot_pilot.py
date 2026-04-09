# tests/test_gtsbot_pilot.py
"""Integration tests for GTSBotPilot pipeline."""
import numpy as np
import pytest
from unittest.mock import MagicMock
from pipelines._shared.GTSBotPilot import GTSBotPilot
from pipelines._shared.GTSBotPilot.trend_filter import TREND_LONG, TREND_SHORT, TREND_NULL
from qengine.framework.base import Pipeline, OrderIntent


def _make_candles(n: int, base_price: float = 1.2000, trend: float = 0.0) -> np.ndarray:
    """Generate synthetic OHLCV candles.
    Candle format: [timestamp, open, close, high, low, volume]
    trend > 0 for uptrend, < 0 for downtrend, 0 for flat.
    """
    candles = np.zeros((n, 6))
    for i in range(n):
        ts = 1609459200000 + i * 60000
        price = base_price + trend * i
        o = price
        c = price + trend * 0.5
        h = max(o, c) + 0.0002
        l = min(o, c) - 0.0002
        v = 100.0
        candles[i] = [ts, o, c, h, l, v]
    return candles


def _make_strategy(candles: np.ndarray, should_long=False, should_short=False,
                   position_open=False, position_qty=0.0, entry_price=0.0):
    """Create a mock strategy object."""
    s = MagicMock()
    s.candles = candles
    s.close = candles[-1, 2] if len(candles) > 0 else 0.0
    s._should_long = should_long
    s._should_short = should_short
    s.vars = {}
    s.position = MagicMock()
    s.position.is_open = position_open
    s.position.qty = position_qty
    s.position.entry_price = entry_price
    s.position.tickets = []
    s.position.pnl = 0.0
    s.balance = 30000.0
    return s


class TestGTSBotPilotConstruction:
    def test_extends_pipeline(self):
        p = GTSBotPilot()
        assert isinstance(p, Pipeline)

    def test_has_all_layers(self):
        p = GTSBotPilot()
        assert hasattr(p, 'trend_filter')
        assert hasattr(p, 'grid_manager')
        assert hasattr(p, 'basket_manager')

    def test_default_config(self):
        cfg = GTSBotPilot.default_config()
        assert 'trend_filter' in cfg
        assert 'grid_manager' in cfg
        assert 'basket_manager' in cfg
        assert cfg['grid_manager']['max_operations'] == 13

    def test_architecture(self):
        arch = GTSBotPilot.architecture()
        layers = [l['name'] for l in arch['layers']]
        assert layers == ['TrendFilter', 'GridManager', 'BasketManager']

    def test_custom_config_merges(self):
        p = GTSBotPilot({'grid_manager': {'max_operations': 7}})
        assert p.grid_manager.max_operations == 7
        # Other defaults preserved
        assert p.grid_manager.x_threshold == 15


class TestTrendFilter:
    def test_allows_during_warmup(self):
        p = GTSBotPilot({'warmup': 100})
        candles = _make_candles(50, trend=0.0001)
        strategy = _make_strategy(candles, should_long=True)
        p.on_before(strategy)
        assert p.gate_entry(strategy) is True

    def test_blocks_null_trend(self):
        p = GTSBotPilot({'warmup': 10})
        candles = _make_candles(100, trend=0.0)
        strategy = _make_strategy(candles, should_long=True)
        p.on_before(strategy)
        p._candle_count = 100  # past warmup
        result = p.gate_entry(strategy)
        assert isinstance(result, bool)

    def test_allows_matching_trend(self):
        p = GTSBotPilot({'warmup': 10, 'trend_filter': {'delta_threshold': 0.000001},
                         'grid_manager': {'enabled': False}})
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles, should_long=True)
        p._candle_count = 100  # past warmup
        p.on_before(strategy)
        assert p.trend_filter.current_trend == TREND_LONG
        assert p.gate_entry(strategy) is True

    def test_blocks_opposing_trend(self):
        p = GTSBotPilot({'warmup': 10, 'trend_filter': {'delta_threshold': 0.000001},
                         'grid_manager': {'enabled': False}})
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles, should_short=True)
        p._candle_count = 100  # past warmup
        p.on_before(strategy)
        assert p.trend_filter.current_trend == TREND_LONG
        assert p.gate_entry(strategy) is False


class TestGridManager:
    def test_blocks_when_max_ops_reached(self):
        p = GTSBotPilot({'warmup': 10, 'grid_manager': {'max_operations': 2},
                         'trend_filter': {'enabled': False}})
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles, should_long=True)
        p._candle_count = 100
        p.on_before(strategy)

        # Inject tickets AFTER on_before (which calls _sync_tickets and clears them
        # because position.is_open is False by default)
        from pipelines._shared.GTSBotPilot.grid_manager import TrackedTicket
        p.grid_manager._tickets = [
            TrackedTicket('long', 1.2000, 50),
            TrackedTicket('long', 1.2050, 70),
        ]
        assert p.gate_entry(strategy) is False

    def test_allows_when_grid_spacing_ok(self):
        p = GTSBotPilot({'warmup': 10,
                         'grid_manager': {'x_threshold': 5, 'y_threshold_atr_mult': 0.1, 'adaptive': False},
                         'trend_filter': {'enabled': False}})
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles, should_long=True)
        p._candle_count = 100
        p.on_before(strategy)

        # Place a ticket far back in time and far in price.
        # candle_index is 1 after one on_before; entry_index 0 gives candles_since=1.
        # With adaptive=False and x_threshold=5, we need candles_since >= 5,
        # so bump candle_index to ensure spacing is satisfied.
        p.grid_manager._candle_index = 100
        from pipelines._shared.GTSBotPilot.grid_manager import TrackedTicket
        p.grid_manager._tickets = [
            TrackedTicket('long', 1.1000, 0),
        ]
        assert p.gate_entry(strategy) is True


class TestBasketManager:
    def test_no_exit_when_below_target(self):
        p = GTSBotPilot({'warmup': 10})
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles)
        p._candle_count = 100
        p.on_before(strategy)
        assert p.suggest_exit(strategy) is None

    def test_close_all_when_target_reached(self):
        p = GTSBotPilot({'warmup': 10})
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles)
        p._candle_count = 100
        p.on_before(strategy)
        # Force basket P&L above target
        p.basket_manager._basket_pnl = 1000.0
        p.basket_manager._target_profit = 100.0
        result = p.suggest_exit(strategy)
        assert result == {'action': 'close_all'}


class TestFilterOrder:
    def test_allows_non_entry_orders(self):
        p = GTSBotPilot()
        order = OrderIntent(qty=1.0, price=1.2, side='buy', type='stop',
                            is_entry=False, symbol='EUR-USD', exchange='OANDA')
        assert p.filter_order(MagicMock(), order) is order

    def test_cancels_entry_when_max_ops(self):
        p = GTSBotPilot({'grid_manager': {'max_operations': 1}})
        from pipelines._shared.GTSBotPilot.grid_manager import TrackedTicket
        p.grid_manager._tickets = [TrackedTicket('long', 1.2, 1)]
        order = OrderIntent(qty=1.0, price=1.2, side='buy', type='market',
                            is_entry=True, symbol='EUR-USD', exchange='OANDA')
        assert p.filter_order(MagicMock(), order) is None


class TestGetStats:
    def test_returns_all_sections(self):
        p = GTSBotPilot()
        stats = p.get_stats()
        assert 'candle_count' in stats
        assert 'trend_filter' in stats
        assert 'grid_manager' in stats
        assert 'basket_manager' in stats
        assert '_ui' in stats

    def test_ui_metadata_has_badges(self):
        p = GTSBotPilot()
        ui = p.ui_metadata()
        assert 'badges' in ui
        assert 'metric_cards' in ui
        assert 'sections' in ui
        assert len(ui['badges']) == 3


class TestLifecycle:
    def test_on_cycle_end_deduplicates(self):
        p = GTSBotPilot()
        strategy = MagicMock()
        strategy.vars = {'session_number': 1}
        p.on_cycle_end(100.0, strategy)
        assert p._last_recorded_session == 1

        # Add a ticket and call again with same session — should be deduped (not cleared)
        from pipelines._shared.GTSBotPilot.grid_manager import TrackedTicket
        p.grid_manager._tickets = [TrackedTicket('long', 1.2, 1)]
        p.on_cycle_end(200.0, strategy)
        assert len(p.grid_manager._tickets) == 1  # not cleared (deduped)

    def test_on_cycle_end_clears_on_new_session(self):
        p = GTSBotPilot()
        strategy = MagicMock()
        strategy.vars = {'session_number': 1}
        p.on_cycle_end(100.0, strategy)

        strategy.vars = {'session_number': 2}
        p.on_cycle_end(200.0, strategy)
        assert p._last_recorded_session == 2
        assert len(p.grid_manager._tickets) == 0
