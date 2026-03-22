"""
Base Broker Driver Test Suite

Tests common functionality shared across all forex/CFD broker drivers:
- ForexLiveDriver base class behavior
- Broker service (strategy -> API -> driver pipeline)
- Order flow integration
- Account sync flow
- Live mode initialization

These tests are all offline (mocked) and require no credentials.
"""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock, PropertyMock


class TestForexLiveDriverABC:
    """Verify the ForexLiveDriver abstract base class."""

    def test_cannot_instantiate_directly(self):
        """ForexLiveDriver is abstract - subclass must implement methods."""
        from qengine.live_drivers.base import ForexLiveDriver
        with pytest.raises(TypeError):
            ForexLiveDriver('test')

    def test_all_abstract_methods_declared(self):
        from qengine.live_drivers.base import ForexLiveDriver
        import inspect
        abstract_methods = {
            name for name, _ in inspect.getmembers(ForexLiveDriver)
            if getattr(getattr(ForexLiveDriver, name, None), '__isabstractmethod__', False)
        }
        expected = {
            '_submit_market_order',
            '_submit_limit_order',
            '_submit_stop_order',
            '_cancel_order_on_exchange',
            '_cancel_all_orders_on_exchange',
            'start_price_stream',
            'get_account_summary',
            'get_open_positions',
            'get_open_orders',
        }
        assert expected.issubset(abstract_methods)


class TestAllDriversImplementABC:
    """Every registered driver must implement all abstract methods."""

    def test_oanda_implements_all(self):
        from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver
        d = OandaDemoDriver()
        d.configure(api_key='test', account_id='acc')
        # If any abstract method is missing, instantiation would have failed
        assert d is not None

    def test_ig_implements_all(self):
        from qengine.live_drivers.IG.IGMarketsDriver import IGMarketsDemoDriver
        d = IGMarketsDemoDriver()
        d.configure(api_key='test', account_id='acc')
        assert d is not None

    def test_ibkr_implements_all(self):
        from qengine.live_drivers.IBKR.IBKRDriver import IBKRPaperDriver
        d = IBKRPaperDriver()
        d.configure(api_key='test', account_id='acc')
        assert d is not None


def _make_broker(exchange='OANDA', symbol='EUR-USD', timeframe='1h', current_price=1.085):
    """Helper to create a Broker with mocked API singleton."""
    from qengine.services.broker import Broker
    mock_pos = MagicMock()
    mock_pos.current_price = current_price
    mock_pos.is_close = False
    mock_pos.type = 'long'

    mock_api = MagicMock()
    b = Broker.__new__(Broker)
    b.position = mock_pos
    b.symbol = symbol
    b.timeframe = timeframe
    b.exchange = exchange
    b.api = mock_api
    return b, mock_api


class TestBrokerService:
    """Test the Broker class that strategies use."""

    def test_broker_fields(self):
        b, _ = _make_broker()
        assert b.exchange == 'OANDA'
        assert b.symbol == 'EUR-USD'

    def test_broker_buy_at_market(self):
        b, mock_api = _make_broker()
        mock_api.market_order.return_value = MagicMock(id='order-1')

        b.buy_at_market(10000)
        mock_api.market_order.assert_called_once_with(
            'OANDA', 'EUR-USD', 10000, 1.085, 'buy', reduce_only=False
        )

    def test_broker_sell_at_market(self):
        b, mock_api = _make_broker()
        mock_api.market_order.return_value = MagicMock(id='order-2')

        b.sell_at_market(5000)
        mock_api.market_order.assert_called_once_with(
            'OANDA', 'EUR-USD', 5000, 1.085, 'sell', reduce_only=False
        )

    def test_broker_buy_at_limit(self):
        b, mock_api = _make_broker()
        mock_api.limit_order.return_value = MagicMock(id='order-3')

        b.buy_at(10000, 1.08)
        mock_api.limit_order.assert_called_once_with(
            'OANDA', 'EUR-USD', 10000, 1.08, 'buy', reduce_only=False
        )

    def test_broker_validates_zero_qty(self):
        from qengine.exceptions import InvalidStrategy
        b, _ = _make_broker()

        with pytest.raises(InvalidStrategy):
            b.buy_at_market(0)

    def test_broker_validates_negative_price(self):
        b, _ = _make_broker()

        with pytest.raises(ValueError):
            b.buy_at(10000, -1.0)

    def test_broker_cancel_all(self):
        b, mock_api = _make_broker()
        b.cancel_all_orders()
        mock_api.cancel_all_orders.assert_called_once_with('OANDA', 'EUR-USD')


class TestBrokerReducePosition:
    """Test reduce_position_at order type selection."""

    def test_reduce_sell_above_price_is_limit(self):
        b, mock_api = _make_broker()
        mock_api.limit_order.return_value = MagicMock()

        with patch('qengine.helpers.is_price_near', return_value=False):
            b.reduce_position_at(10000, 1.10, 1.085)  # sell above current -> limit
            mock_api.limit_order.assert_called_once()

    def test_reduce_sell_below_price_is_stop(self):
        b, mock_api = _make_broker()
        mock_api.stop_order.return_value = MagicMock()

        with patch('qengine.helpers.is_price_near', return_value=False):
            b.reduce_position_at(10000, 1.07, 1.085)  # sell below current -> stop
            mock_api.stop_order.assert_called_once()

    def test_reduce_near_price_is_market(self):
        b, mock_api = _make_broker()
        mock_api.market_order.return_value = MagicMock()

        with patch('qengine.helpers.is_price_near', return_value=True):
            b.reduce_position_at(10000, 1.085, 1.085)
            mock_api.market_order.assert_called_once()


class TestLiveModeAccountSync:
    """Test the account sync flow in forex_live_mode."""

    def test_sync_account_balance(self):
        from qengine.modes.forex_live_mode import _sync_account_balance

        mock_driver = MagicMock()
        mock_driver.get_account_summary.return_value = {
            'balance': 50000.0,
            'margin_available': 45000.0,
        }

        mock_exchange = MagicMock()

        with patch('qengine.store.store.exchanges') as mock_exchanges:
            mock_exchanges.storage = {'OANDA Demo': mock_exchange}

            _sync_account_balance('OANDA Demo', mock_driver, 'test-session')

            mock_exchange.update_from_stream.assert_called_once_with({
                'wallet_balance': 50000.0,
                'available_margin': 45000.0,
            })

    def test_sync_account_balance_handles_error(self):
        from qengine.modes.forex_live_mode import _sync_account_balance

        mock_driver = MagicMock()
        mock_driver.get_account_summary.side_effect = Exception('Network error')

        # Should not raise
        _sync_account_balance('OANDA Demo', mock_driver, 'test-session')


class TestLiveDriverRegistration:
    """Test that all brokers are properly registered."""

    def test_all_brokers_have_drivers(self):
        from qengine.live_drivers import live_drivers
        from qengine.enums import brokers
        expected_brokers = [
            brokers.OANDA, brokers.OANDA_DEMO,
            brokers.IG_MARKETS, brokers.IG_MARKETS_DEMO,
            brokers.IBKR, brokers.IBKR_PAPER,
        ]
        for b in expected_brokers:
            assert b in live_drivers, f'Missing driver for {b}'

    def test_all_drivers_are_subclass_of_base(self):
        from qengine.live_drivers import live_drivers
        from qengine.live_drivers.base import ForexLiveDriver
        for name, cls in live_drivers.items():
            assert issubclass(cls, ForexLiveDriver), f'{name} is not a ForexLiveDriver subclass'

    def test_driver_names_match_keys(self):
        from qengine.live_drivers import live_drivers
        for name, cls in live_drivers.items():
            instance = cls()
            assert instance.name == name, f'Driver {cls.__name__}.name={instance.name} != key={name}'


class TestCandleBuilderEdgeCases:
    """Edge cases for the candle builder."""

    def test_hour_candle_alignment(self):
        from qengine.modes.forex_live_mode import _CandleBuilder
        cb = _CandleBuilder('1h')
        # 1h = 3,600,000 ms
        ts = 3600000 * 5  # 5th hour

        cb.update(100.0, ts)
        cb.update(105.0, ts + 1000000)  # ~16min in

        # Cross into next hour
        closed = cb.update(103.0, ts + 3600000)
        assert closed is not None
        assert closed[1] == 100.0   # open
        assert closed[3] == 105.0   # high

    def test_daily_candle_alignment(self):
        from qengine.modes.forex_live_mode import _CandleBuilder
        cb = _CandleBuilder('1D')
        # 1D = 86,400,000 ms
        day_ms = 86400000
        ts = day_ms * 10  # day 10

        cb.update(1.08, ts)
        cb.update(1.09, ts + day_ms // 2)  # noon

        # Next day
        closed = cb.update(1.085, ts + day_ms)
        assert closed is not None

    def test_single_tick_candle(self):
        """A candle with only one tick should have O=H=L=C."""
        from qengine.modes.forex_live_mode import _CandleBuilder
        cb = _CandleBuilder('1m')

        cb.update(50.0, 60000)  # one tick in first minute

        # Cross to second minute
        closed = cb.update(51.0, 120000)
        assert closed is not None
        assert closed[1] == 50.0  # open
        assert closed[2] == 50.0  # close
        assert closed[3] == 50.0  # high
        assert closed[4] == 50.0  # low
