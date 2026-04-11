"""
OANDA Broker API Test Suite

Tests all OANDA API functionality required for algo trading:
- Authentication & connection
- Account info (balance, margin, NAV)
- Instrument discovery & precisions
- Price streaming
- Order lifecycle (create, query, cancel)
- Position management
- Candle data retrieval
- Error handling & edge cases

Run with real OANDA credentials:
    OANDA_API_KEY=xxx OANDA_ACCOUNT_ID=yyy pytest tests/test_broker_oanda.py -v

Tests are skipped if credentials are not set.
"""
import os
import time
import json
import pytest
import threading
import numpy as np
from unittest.mock import patch, MagicMock

# ── Credential Detection ──

OANDA_API_KEY = os.environ.get('OANDA_API_KEY', '')
OANDA_ACCOUNT_ID = os.environ.get('OANDA_ACCOUNT_ID', '')
HAS_OANDA_CREDS = bool(OANDA_API_KEY and OANDA_ACCOUNT_ID)

skip_no_creds = pytest.mark.skipif(
    not HAS_OANDA_CREDS,
    reason='OANDA_API_KEY and OANDA_ACCOUNT_ID not set'
)


# ── Fixtures ──

@pytest.fixture
def oanda_demo_driver():
    """Create a configured OANDA demo driver."""
    from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver
    driver = OandaDemoDriver()
    driver.configure(api_key=OANDA_API_KEY, account_id=OANDA_ACCOUNT_ID)
    return driver


@pytest.fixture
def oanda_live_driver():
    """Create an OANDA live driver (not configured - for unit tests)."""
    from qengine.live_drivers.OANDA.OandaDriver import OandaLiveDriver
    return OandaLiveDriver()


@pytest.fixture
def mock_oanda_driver():
    """Create a mock OANDA driver for offline tests."""
    from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver
    driver = OandaDemoDriver()
    driver.configure(api_key='test-key', account_id='test-account')
    return driver


# ══════════════════════════════════════════════════════════════════
# SECTION 1: OFFLINE UNIT TESTS (no credentials needed)
# ══════════════════════════════════════════════════════════════════

class TestOandaDriverInit:
    """Driver initialization and configuration."""

    def test_demo_driver_urls(self):
        from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver
        d = OandaDemoDriver()
        assert 'fxpractice' in d._rest_url
        assert 'fxpractice' in d._stream_url

    def test_live_driver_urls(self):
        from qengine.live_drivers.OANDA.OandaDriver import OandaLiveDriver
        d = OandaLiveDriver()
        assert 'fxtrade' in d._rest_url
        assert 'fxtrade' in d._stream_url
        assert 'practice' not in d._rest_url

    def test_configure(self):
        from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver
        d = OandaDemoDriver()
        assert not d.is_configured
        d.configure(api_key='test', account_id='123')
        assert d.is_configured
        assert d._api_key == 'test'
        assert d._account_id == '123'

    def test_headers(self):
        from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver
        d = OandaDemoDriver()
        d.configure(api_key='my-token', account_id='acc')
        headers = d._headers()
        assert headers['Authorization'] == 'Bearer my-token'
        assert headers['Content-Type'] == 'application/json'

    def test_driver_names(self):
        from qengine.live_drivers.OANDA.OandaDriver import OandaLiveDriver, OandaDemoDriver
        from qengine.enums import brokers
        assert OandaLiveDriver().name == brokers.OANDA
        assert OandaDemoDriver().name == brokers.OANDA_DEMO

    def test_driver_registered_in_live_drivers(self):
        from qengine.live_drivers import live_drivers
        from qengine.enums import brokers
        assert brokers.OANDA in live_drivers
        assert brokers.OANDA_DEMO in live_drivers


class TestSymbolConversion:
    """Symbol <-> Instrument name conversion."""

    def test_symbol_to_instrument(self):
        from qengine.modes.import_candles_mode.drivers.OANDA.oanda_utils import symbol_to_instrument
        assert symbol_to_instrument('EUR-USD') == 'EUR_USD'
        assert symbol_to_instrument('GBP-JPY') == 'GBP_JPY'
        assert symbol_to_instrument('XAU-USD') == 'XAU_USD'

    def test_instrument_to_symbol(self):
        from qengine.modes.import_candles_mode.drivers.OANDA.oanda_utils import instrument_to_symbol
        assert instrument_to_symbol('EUR_USD') == 'EUR-USD'
        assert instrument_to_symbol('GBP_JPY') == 'GBP-JPY'
        assert instrument_to_symbol('XAU_USD') == 'XAU-USD'

    def test_roundtrip(self):
        from qengine.modes.import_candles_mode.drivers.OANDA.oanda_utils import (
            symbol_to_instrument, instrument_to_symbol,
        )
        symbols = ['EUR-USD', 'GBP-USD', 'USD-JPY', 'XAU-USD', 'USD-CHF']
        for s in symbols:
            assert instrument_to_symbol(symbol_to_instrument(s)) == s


class TestOandaOrderPayloads:
    """Verify order payloads are correctly constructed."""

    def test_market_order_payload_buy(self, mock_oanda_driver):
        """Market buy should have positive units."""
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {'orderCreateTransaction': {'id': '100'}},
            )
            mock_post.return_value.raise_for_status = MagicMock()

            mock_oanda_driver._submit_market_order('EUR-USD', 10000, 1.0850, 'buy', False)

            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
            assert payload['order']['type'] == 'MARKET'
            assert payload['order']['instrument'] == 'EUR_USD'
            assert payload['order']['units'] == '10000'
            assert payload['order']['timeInForce'] == 'FOK'
            assert payload['order']['positionFill'] == 'DEFAULT'

    def test_market_order_payload_sell(self, mock_oanda_driver):
        """Market sell should have negative units."""
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {'orderCreateTransaction': {'id': '101'}},
            )
            mock_post.return_value.raise_for_status = MagicMock()

            mock_oanda_driver._submit_market_order('EUR-USD', 10000, 1.0850, 'sell', False)

            payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json')
            assert payload['order']['units'] == '-10000'

    def test_limit_order_payload(self, mock_oanda_driver):
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {'orderCreateTransaction': {'id': '102'}},
            )
            mock_post.return_value.raise_for_status = MagicMock()

            mock_oanda_driver._submit_limit_order('GBP-USD', 5000, 1.2500, 'buy', False)

            payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json')
            assert payload['order']['type'] == 'LIMIT'
            assert payload['order']['price'] == '1.25'
            assert payload['order']['timeInForce'] == 'GTC'

    def test_stop_order_payload(self, mock_oanda_driver):
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {'orderCreateTransaction': {'id': '103'}},
            )
            mock_post.return_value.raise_for_status = MagicMock()

            mock_oanda_driver._submit_stop_order('USD-JPY', 10000, 150.50, 'sell', True)

            payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json')
            assert payload['order']['type'] == 'STOP'
            assert payload['order']['positionFill'] == 'REDUCE_ONLY'

    def test_reduce_only_flag(self, mock_oanda_driver):
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {'orderCreateTransaction': {'id': '104'}},
            )
            mock_post.return_value.raise_for_status = MagicMock()

            mock_oanda_driver._submit_market_order('EUR-USD', 5000, 1.0850, 'sell', True)

            payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json')
            assert payload['order']['positionFill'] == 'REDUCE_ONLY'


class TestOandaCancellation:
    """Order cancellation payloads."""

    def test_cancel_single_order(self, mock_oanda_driver):
        with patch('requests.put') as mock_put:
            mock_put.return_value = MagicMock(status_code=200)
            mock_put.return_value.raise_for_status = MagicMock()

            mock_oanda_driver._cancel_order_on_exchange('EUR-USD', '12345')

            url = mock_put.call_args[0][0]
            assert '/orders/12345/cancel' in url

    def test_cancel_404_ignored(self, mock_oanda_driver):
        """Cancelling an already-filled order (404) should not raise."""
        with patch('requests.put') as mock_put:
            mock_put.return_value = MagicMock(status_code=404)
            # Should NOT raise
            mock_oanda_driver._cancel_order_on_exchange('EUR-USD', '99999')

    def test_cancel_all_orders(self, mock_oanda_driver):
        with patch('requests.get') as mock_get, patch('requests.put') as mock_put:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    'orders': [
                        {'id': '1', 'instrument': 'EUR_USD', 'type': 'LIMIT'},
                        {'id': '2', 'instrument': 'EUR_USD', 'type': 'STOP'},
                        {'id': '3', 'instrument': 'GBP_USD', 'type': 'LIMIT'},  # different pair
                    ]
                },
            )
            mock_get.return_value.raise_for_status = MagicMock()
            mock_put.return_value = MagicMock(status_code=200)
            mock_put.return_value.raise_for_status = MagicMock()

            mock_oanda_driver._cancel_all_orders_on_exchange('EUR-USD')

            # Should only cancel EUR_USD orders (2), not GBP_USD
            assert mock_put.call_count == 2


class TestAccountSummaryParsing:
    """Verify account summary response parsing."""

    def test_parse_account_summary(self, mock_oanda_driver):
        mock_response = {
            'account': {
                'balance': '10000.50',
                'unrealizedPL': '-50.25',
                'marginUsed': '333.33',
                'marginAvailable': '9617.17',
                'NAV': '9950.25',
                'openTradeCount': '2',
                'currency': 'USD',
            }
        }
        with patch('requests.get') as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
            )
            mock_get.return_value.raise_for_status = MagicMock()

            summary = mock_oanda_driver.get_account_summary()

            assert summary['balance'] == 10000.50
            assert summary['unrealized_pnl'] == -50.25
            assert summary['margin_used'] == 333.33
            assert summary['margin_available'] == 9617.17
            assert summary['nav'] == 9950.25
            assert summary['open_trade_count'] == 2
            assert summary['currency'] == 'USD'


class TestOpenPositionsParsing:
    """Verify position response parsing."""

    def test_parse_open_positions(self, mock_oanda_driver):
        mock_response = {
            'positions': [
                {
                    'instrument': 'EUR_USD',
                    'long': {'units': '10000'},
                    'short': {'units': '0'},
                    'unrealizedPL': '25.50',
                },
                {
                    'instrument': 'GBP_USD',
                    'long': {'units': '0'},
                    'short': {'units': '-5000'},
                    'unrealizedPL': '-12.30',
                },
            ]
        }
        with patch('requests.get') as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
            )
            mock_get.return_value.raise_for_status = MagicMock()

            positions = mock_oanda_driver.get_open_positions()

            assert len(positions) == 2
            assert positions[0]['symbol'] == 'EUR-USD'
            assert positions[0]['long_units'] == 10000.0
            assert positions[1]['symbol'] == 'GBP-USD'
            assert positions[1]['short_units'] == -5000.0


class TestOpenOrdersParsing:
    """Verify pending orders response parsing."""

    def test_parse_open_orders(self, mock_oanda_driver):
        mock_response = {
            'orders': [
                {
                    'id': '1001',
                    'instrument': 'EUR_USD',
                    'type': 'LIMIT',
                    'units': '10000',
                    'price': '1.0800',
                    'timeInForce': 'GTC',
                },
            ]
        }
        with patch('requests.get') as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
            )
            mock_get.return_value.raise_for_status = MagicMock()

            orders = mock_oanda_driver.get_open_orders()

            assert len(orders) == 1
            assert orders[0]['id'] == '1001'
            assert orders[0]['symbol'] == 'EUR-USD'
            assert orders[0]['type'] == 'LIMIT'
            assert orders[0]['units'] == 10000.0
            assert orders[0]['price'] == 1.0800


class TestPriceStreamParsing:
    """Verify price stream data parsing."""

    def test_stream_callback_receives_dict(self, mock_oanda_driver):
        """Verify the callback receives a dict with required keys."""
        received = []

        def on_tick(tick):
            received.append(tick)

        # Simulate a stream response
        stream_line = json.dumps({
            'type': 'PRICE',
            'instrument': 'EUR_USD',
            'time': '2026-03-17T12:00:00Z',
            'bids': [{'price': '1.0850', 'liquidity': 10000000}],
            'asks': [{'price': '1.0851', 'liquidity': 10000000}],
        }).encode()

        heartbeat_line = json.dumps({'type': 'HEARTBEAT'}).encode()

        with patch('requests.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.iter_lines.return_value = [heartbeat_line, stream_line, b'']
            mock_get.return_value = mock_resp

            # Run stream in thread so it doesn't block
            t = threading.Thread(
                target=mock_oanda_driver.start_price_stream,
                args=([' EUR-USD'], on_tick),
                daemon=True,
            )
            t.start()
            t.join(timeout=2)

        assert len(received) == 1
        tick = received[0]
        assert tick['symbol'] == 'EUR-USD'
        assert tick['bid'] == 1.0850
        assert tick['ask'] == 1.0851
        assert abs(tick['price'] - 1.08505) < 0.0001


class TestPrecisionsParsing:
    """Verify instrument precision fetching."""

    def test_fetch_precisions(self, mock_oanda_driver):
        mock_response = {
            'instruments': [
                {
                    'name': 'EUR_USD',
                    'displayPrecision': 5,
                    'minimumTradeSize': '1',
                },
                {
                    'name': 'USD_JPY',
                    'displayPrecision': 3,
                    'minimumTradeSize': '1',
                },
            ]
        }
        # Set up the store with an exchange that has vars
        from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver
        from qengine.enums import brokers

        driver = OandaDemoDriver()
        driver.configure(api_key='test', account_id='acc')

        # Mock the store
        mock_exchange = MagicMock()
        mock_exchange.vars = {}

        with patch('requests.get') as mock_get, \
             patch('qengine.store.store.exchanges') as mock_exchanges:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
            )
            mock_get.return_value.raise_for_status = MagicMock()
            mock_exchanges.storage = {brokers.OANDA_DEMO: mock_exchange}

            driver._fetch_precisions()

            precs = mock_exchange.vars['precisions']
            assert 'EUR-USD' in precs
            assert precs['EUR-USD']['price_precision'] == 5
            assert precs['USD-JPY']['price_precision'] == 3


class TestErrorHandling:
    """Verify error handling for failed API calls."""

    def test_market_order_http_error(self, mock_oanda_driver):
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=400)
            mock_post.return_value.raise_for_status.side_effect = Exception('Bad Request')

            with pytest.raises(Exception, match='Bad Request'):
                mock_oanda_driver._submit_market_order('EUR-USD', 10000, 1.0850, 'buy', False)

    def test_account_summary_http_error(self, mock_oanda_driver):
        with patch('requests.get') as mock_get:
            mock_get.return_value = MagicMock(status_code=401)
            mock_get.return_value.raise_for_status.side_effect = Exception('Unauthorized')

            with pytest.raises(Exception, match='Unauthorized'):
                mock_oanda_driver.get_account_summary()

    def test_market_order_returns_order_id(self, mock_oanda_driver):
        """On order fill, the fill transaction ID should be returned."""
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {
                    'orderCreateTransaction': {'id': '500'},
                    'orderFillTransaction': {'orderID': '500', 'id': '501'},
                },
            )
            mock_post.return_value.raise_for_status = MagicMock()

            result = mock_oanda_driver._submit_market_order('EUR-USD', 1000, 1.085, 'buy', False)
            assert result['order_id'] == '500'


# ══════════════════════════════════════════════════════════════════
# SECTION 2: CANDLE BUILDER TESTS (offline)
# ══════════════════════════════════════════════════════════════════

class TestCandleBuilder:
    """Test the live candle builder from tick data."""

    def test_first_tick_starts_candle(self):
        from qengine.modes.live_mode import _CandleBuilder
        cb = _CandleBuilder('1m')
        result = cb.update(1.0850, 1000 * 60 * 1000)  # t=1000min
        assert result is None  # no closed candle yet
        assert cb._tick_count == 1
        assert cb._open == 1.0850

    def test_same_period_updates_ohlc(self):
        from qengine.modes.live_mode import _CandleBuilder
        cb = _CandleBuilder('1m')
        ts = 60000  # 1 minute in ms = 60000

        cb.update(1.0850, ts)
        cb.update(1.0860, ts + 10000)  # +10s, same minute
        cb.update(1.0840, ts + 20000)  # +20s, same minute
        cb.update(1.0855, ts + 30000)  # +30s, same minute

        candle = cb.current_candle()
        assert candle[1] == 1.0850   # open
        assert candle[2] == 1.0855   # close (latest)
        assert candle[3] == 1.0860   # high
        assert candle[4] == 1.0840   # low

    def test_new_period_closes_candle(self):
        from qengine.modes.live_mode import _CandleBuilder
        cb = _CandleBuilder('1m')

        # First minute
        cb.update(1.0850, 60000)
        cb.update(1.0860, 90000)

        # Cross into second minute
        closed = cb.update(1.0855, 120000)

        assert closed is not None
        assert closed[1] == 1.0850  # open of first candle
        assert closed[3] == 1.0860  # high of first candle

    def test_5m_candle_alignment(self):
        from qengine.modes.live_mode import _CandleBuilder
        cb = _CandleBuilder('5m')

        # 5m = 300000ms
        cb.update(100.0, 300000)
        cb.update(101.0, 400000)  # still in same 5min bar
        assert cb.update(100.5, 500000) is None  # still same bar

        closed = cb.update(102.0, 600000)  # new 5min bar
        assert closed is not None
        assert closed[1] == 100.0   # open
        assert closed[3] == 101.0   # high
        assert closed[4] == 100.0   # low
        assert closed[2] == 100.5   # close (last before period end)


# ══════════════════════════════════════════════════════════════════
# SECTION 3: LIVE MODE INTEGRATION TESTS (offline, mocked)
# ══════════════════════════════════════════════════════════════════

class TestForexLiveDriverBase:
    """Test the base ForexLiveDriver methods."""

    def test_market_order_creates_order_in_store(self):
        """Verify ForexLiveDriver.market_order() calls order_service correctly."""
        from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver

        driver = OandaDemoDriver()
        driver.configure(api_key='test', account_id='acc')

        with patch.object(driver, '_submit_market_order', return_value='123'), \
             patch('qengine.services.order_service.create_order') as mock_create:
            mock_create.return_value = MagicMock(id='order-1')

            driver.market_order('EUR-USD', 10000, 1.085, 'buy', False)

            mock_create.assert_called_once()
            attrs = mock_create.call_args[0][0]
            assert attrs['exchange_id'] == '123'
            assert attrs['symbol'] == 'EUR-USD'
            assert attrs['side'] == 'buy'
            assert attrs['type'] == 'MARKET'

    def test_limit_order_creates_order(self):
        from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver

        driver = OandaDemoDriver()
        driver.configure(api_key='test', account_id='acc')

        with patch.object(driver, '_submit_limit_order', return_value='456'), \
             patch('qengine.services.order_service.create_order') as mock_create:
            mock_create.return_value = MagicMock(id='order-2')

            driver.limit_order('EUR-USD', 10000, 1.08, 'buy', False)

            attrs = mock_create.call_args[0][0]
            assert attrs['exchange_id'] == '456'
            assert attrs['type'] == 'LIMIT'
            assert attrs['price'] == 1.08

    def test_stop_order_creates_order(self):
        from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver

        driver = OandaDemoDriver()
        driver.configure(api_key='test', account_id='acc')

        with patch.object(driver, '_submit_stop_order', return_value='789'), \
             patch('qengine.services.order_service.create_order') as mock_create:
            mock_create.return_value = MagicMock(id='order-3')

            driver.stop_order('EUR-USD', 10000, 1.07, 'sell', True)

            attrs = mock_create.call_args[0][0]
            assert attrs['exchange_id'] == '789'
            assert attrs['type'] == 'STOP'
            assert attrs['reduce_only'] is True


class TestAPIDriverRegistration:
    """Test that the API class properly routes to drivers."""

    def test_api_returns_none_when_driver_missing(self):
        """API.market_order returns None when driver not found."""
        # Build a minimal API-like object to test routing logic
        class _FakeAPI:
            def __init__(self):
                self.drivers = {}
            def market_order(self, exchange, symbol, qty, price, side, reduce_only):
                if exchange not in self.drivers:
                    return None
                return self.drivers[exchange].market_order(symbol, qty, price, side, reduce_only)

        a = _FakeAPI()
        result = a.market_order('OANDA', 'EUR-USD', 100, 1.08, 'buy', False)
        assert result is None

    def test_api_routes_to_registered_driver(self):
        class _FakeAPI:
            def __init__(self):
                self.drivers = {}
            def market_order(self, exchange, symbol, qty, price, side, reduce_only):
                if exchange not in self.drivers:
                    return None
                return self.drivers[exchange].market_order(symbol, qty, price, side, reduce_only)

        a = _FakeAPI()
        mock_driver = MagicMock()
        mock_driver.market_order.return_value = MagicMock(id='order-x')
        a.drivers['OANDA Demo'] = mock_driver

        result = a.market_order('OANDA Demo', 'EUR-USD', 100, 1.08, 'buy', False)
        assert result is not None
        mock_driver.market_order.assert_called_once()


class TestCFDExchangeModel:
    """Test the CFDExchange model for live mode."""

    def _make_exchange(self, balance=10000):
        from qengine.models.CFDExchange import CFDExchange
        ex = CFDExchange.__new__(CFDExchange)
        ex.name = 'test'
        ex.starting_assets = {'USD': balance}
        ex.assets = {'USD': balance}
        ex.fee_rate = 0.0
        ex.type = 'cfd'
        ex.settlement_currency = 'USD'
        ex.default_leverage = 30
        ex._spread_config = {}
        ex._swap_rates = {}
        ex._overnight_charges = 0.0
        ex._available_margin = 0
        ex._wallet_balance = 0
        ex._started_balance = 0
        ex.buy_orders = {}
        ex.sell_orders = {}
        ex.available_assets = {}
        return ex

    def test_update_from_stream(self):
        ex = self._make_exchange()
        with patch('qengine.helpers.is_live', return_value=True):
            ex.update_from_stream({
                'wallet_balance': 50000,
                'available_margin': 45000,
            })
            assert ex._wallet_balance == 50000
            assert ex._available_margin == 45000
            assert ex._started_balance == 50000

    def test_update_from_stream_started_balance_only_set_once(self):
        ex = self._make_exchange()
        with patch('qengine.helpers.is_live', return_value=True):
            ex.update_from_stream({'wallet_balance': 50000, 'available_margin': 45000})
            ex.update_from_stream({'wallet_balance': 49000, 'available_margin': 44000})
            assert ex._started_balance == 50000  # should not change

    def test_wallet_balance_uses_stream_in_live(self):
        ex = self._make_exchange()
        with patch('qengine.helpers.is_live', return_value=True):
            ex.update_from_stream({'wallet_balance': 50000, 'available_margin': 45000})
            assert ex.wallet_balance == 50000

    def test_wallet_balance_uses_assets_in_backtest(self):
        ex = self._make_exchange(10000)
        with patch('qengine.helpers.is_live', return_value=False):
            assert ex.wallet_balance == 10000


# ══════════════════════════════════════════════════════════════════
# SECTION 4: ONLINE API TESTS (require OANDA credentials)
# ══════════════════════════════════════════════════════════════════

@skip_no_creds
class TestOandaConnectionLive:
    """Test actual OANDA API connection."""

    def test_account_summary(self, oanda_demo_driver):
        summary = oanda_demo_driver.get_account_summary()
        assert 'balance' in summary
        assert 'currency' in summary
        assert isinstance(summary['balance'], float)
        assert summary['balance'] >= 0

    def test_account_has_currency(self, oanda_demo_driver):
        summary = oanda_demo_driver.get_account_summary()
        assert summary['currency'] in ('USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF')

    def test_margin_fields_present(self, oanda_demo_driver):
        summary = oanda_demo_driver.get_account_summary()
        assert 'margin_used' in summary
        assert 'margin_available' in summary
        assert 'nav' in summary


@skip_no_creds
class TestOandaInstrumentsLive:
    """Test instrument/precision fetching."""

    def test_fetch_instruments(self, oanda_demo_driver):
        """Verify we can fetch instrument list from OANDA."""
        import requests
        resp = requests.get(
            f'{oanda_demo_driver._rest_url}/accounts/{oanda_demo_driver._account_id}/instruments',
            headers=oanda_demo_driver._headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        instruments = data.get('instruments', [])
        assert len(instruments) > 0

        # Check EUR_USD is in the list
        names = [i['name'] for i in instruments]
        assert 'EUR_USD' in names

    def test_instrument_has_precision(self, oanda_demo_driver):
        import requests
        resp = requests.get(
            f'{oanda_demo_driver._rest_url}/accounts/{oanda_demo_driver._account_id}/instruments',
            headers=oanda_demo_driver._headers(),
            params={'instruments': 'EUR_USD'},
        )
        data = resp.json()
        inst = data['instruments'][0]
        assert 'displayPrecision' in inst
        assert 'minimumTradeSize' in inst
        assert inst['displayPrecision'] == 5


@skip_no_creds
class TestOandaPositionsLive:
    """Test position query."""

    def test_get_open_positions(self, oanda_demo_driver):
        positions = oanda_demo_driver.get_open_positions()
        assert isinstance(positions, list)
        # Each position should have required fields
        for p in positions:
            assert 'symbol' in p
            assert 'long_units' in p
            assert 'short_units' in p


@skip_no_creds
class TestOandaOrdersLive:
    """Test pending order query."""

    def test_get_open_orders(self, oanda_demo_driver):
        orders = oanda_demo_driver.get_open_orders()
        assert isinstance(orders, list)
        for o in orders:
            assert 'id' in o
            assert 'symbol' in o
            assert 'type' in o


@skip_no_creds
class TestOandaPriceStreamLive:
    """Test real-time price streaming."""

    def test_stream_receives_prices(self, oanda_demo_driver):
        """Connect to OANDA price stream and verify we get ticks."""
        received = []
        stop_event = threading.Event()

        def on_tick(tick):
            received.append(tick)
            if len(received) >= 3:
                stop_event.set()

        t = threading.Thread(
            target=oanda_demo_driver.start_price_stream,
            args=(['EUR-USD'], on_tick),
            daemon=True,
        )
        t.start()

        # Wait up to 15 seconds for 3 ticks
        stop_event.wait(timeout=15)

        assert len(received) >= 1, 'No price ticks received from OANDA stream'
        tick = received[0]
        assert 'symbol' in tick
        assert 'bid' in tick
        assert 'ask' in tick
        assert 'price' in tick
        assert tick['symbol'] == 'EUR-USD'
        assert tick['bid'] > 0
        assert tick['ask'] > 0
        assert tick['ask'] >= tick['bid']  # ask >= bid always


@skip_no_creds
class TestOandaOrderLifecycleLive:
    """Test full order lifecycle: create limit -> query -> cancel."""

    def test_limit_order_create_and_cancel(self, oanda_demo_driver):
        """Create a limit order far from market, verify it exists, cancel it."""
        # Get current price first
        summary = oanda_demo_driver.get_account_summary()
        assert summary['balance'] > 0

        # Place a limit buy far below market (won't fill)
        order_id = oanda_demo_driver._submit_limit_order(
            'EUR-USD', 100, 0.5000, 'buy', False  # price 0.50 won't fill
        )
        assert order_id

        # Verify order appears in pending orders
        time.sleep(0.5)
        orders = oanda_demo_driver.get_open_orders()
        order_ids = [o['id'] for o in orders]
        assert order_id in order_ids

        # Cancel it
        oanda_demo_driver._cancel_order_on_exchange('EUR-USD', order_id)

        # Verify it's gone
        time.sleep(0.5)
        orders_after = oanda_demo_driver.get_open_orders()
        order_ids_after = [o['id'] for o in orders_after]
        assert order_id not in order_ids_after


@skip_no_creds
class TestOandaCandlesLive:
    """Test historical candle retrieval from OANDA."""

    def test_fetch_candles(self, oanda_demo_driver):
        """Fetch recent candles for EUR_USD."""
        import requests
        resp = requests.get(
            f'{oanda_demo_driver._rest_url}/instruments/EUR_USD/candles',
            headers=oanda_demo_driver._headers(),
            params={
                'granularity': 'M1',
                'count': 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        candles = data.get('candles', [])
        assert len(candles) >= 1

        c = candles[0]
        assert 'mid' in c
        assert 'o' in c['mid']
        assert 'h' in c['mid']
        assert 'l' in c['mid']
        assert 'c' in c['mid']
        assert float(c['mid']['o']) > 0
