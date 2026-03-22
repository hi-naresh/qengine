import pytest

from qengine.enums import brokers
from qengine.exchanges.exchange import Exchange as ExchangeDriver
from qengine.live_drivers.base import ForexLiveDriver


# ── 7.0 Registry Tests ──

def test_live_driver_registry():
    from qengine.live_drivers import live_drivers, live_driver_names
    assert brokers.OANDA in live_drivers
    assert brokers.OANDA_DEMO in live_drivers
    assert brokers.IG_MARKETS in live_drivers
    assert brokers.IG_MARKETS_DEMO in live_drivers
    assert brokers.IBKR in live_drivers
    assert brokers.IBKR_PAPER in live_drivers
    assert len(live_driver_names) == 6


def test_all_live_drivers_extend_exchange_abc():
    from qengine.live_drivers import live_drivers
    for name, driver_cls in live_drivers.items():
        assert issubclass(driver_cls, ExchangeDriver), f'{name} does not extend Exchange ABC'


def test_all_live_drivers_extend_forex_base():
    from qengine.live_drivers import live_drivers
    for name, driver_cls in live_drivers.items():
        assert issubclass(driver_cls, ForexLiveDriver), f'{name} does not extend ForexLiveDriver'


def test_live_drivers_registered_in_config():
    """Live drivers should be registerable in config."""
    from qengine.config import config
    from qengine.live_drivers import live_drivers as ld
    # Re-register (tests may have reset config)
    config['app']['live_drivers'].update(ld)
    assert brokers.OANDA in config['app']['live_drivers']
    assert brokers.IG_MARKETS in config['app']['live_drivers']
    assert brokers.IBKR in config['app']['live_drivers']


# ── 7.1 OANDA Live Driver ──

def test_oanda_live_driver_instantiation():
    from qengine.live_drivers.OANDA.OandaDriver import OandaLiveDriver
    driver = OandaLiveDriver()
    assert driver.name == brokers.OANDA
    assert driver.is_demo is False
    assert 'fxtrade.oanda.com' in driver._rest_url
    assert driver.is_configured is False


def test_oanda_demo_driver_instantiation():
    from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver
    driver = OandaDemoDriver()
    assert driver.name == brokers.OANDA_DEMO
    assert driver.is_demo is True
    assert 'practice' in driver._rest_url
    assert 'practice' in driver._stream_url


def test_oanda_driver_configure():
    from qengine.live_drivers.OANDA.OandaDriver import OandaLiveDriver
    driver = OandaLiveDriver()
    driver.configure(api_key='test-key', account_id='101-001-12345-001')
    assert driver.is_configured is True
    assert driver._api_key == 'test-key'
    assert driver._account_id == '101-001-12345-001'


def test_oanda_driver_headers():
    from qengine.live_drivers.OANDA.OandaDriver import OandaLiveDriver
    driver = OandaLiveDriver()
    driver._api_key = 'test-key'
    headers = driver._headers()
    assert headers['Authorization'] == 'Bearer test-key'
    assert 'application/json' in headers['Content-Type']


def test_oanda_driver_has_all_methods():
    from qengine.live_drivers.OANDA.OandaDriver import OandaLiveDriver
    driver = OandaLiveDriver()
    assert callable(driver.market_order)
    assert callable(driver.limit_order)
    assert callable(driver.stop_order)
    assert callable(driver.cancel_all_orders)
    assert callable(driver.cancel_order)
    assert callable(driver.start_price_stream)
    assert callable(driver.get_account_summary)
    assert callable(driver.get_open_positions)
    assert callable(driver.get_open_orders)
    assert callable(driver._fetch_precisions)


# ── 7.2 IG Markets Live Driver ──

def test_ig_live_driver_instantiation():
    from qengine.live_drivers.IG.IGMarketsDriver import IGMarketsLiveDriver
    driver = IGMarketsLiveDriver()
    assert driver.name == brokers.IG_MARKETS
    assert driver.is_demo is False
    assert 'api.ig.com' in driver._base_url
    assert 'demo' not in driver._base_url


def test_ig_demo_driver_instantiation():
    from qengine.live_drivers.IG.IGMarketsDriver import IGMarketsDemoDriver
    driver = IGMarketsDemoDriver()
    assert driver.name == brokers.IG_MARKETS_DEMO
    assert driver.is_demo is True
    assert 'demo-api.ig.com' in driver._base_url


def test_ig_driver_configure():
    from qengine.live_drivers.IG.IGMarketsDriver import IGMarketsLiveDriver
    driver = IGMarketsLiveDriver()
    driver.configure(api_key='ig-key', username='myuser', password='mypass')
    assert driver.is_configured is True
    assert driver._ig_api_key == 'ig-key'
    assert driver._username == 'myuser'
    assert driver._password == 'mypass'


def test_ig_driver_has_all_methods():
    from qengine.live_drivers.IG.IGMarketsDriver import IGMarketsLiveDriver
    driver = IGMarketsLiveDriver()
    assert callable(driver.market_order)
    assert callable(driver.limit_order)
    assert callable(driver.stop_order)
    assert callable(driver.cancel_all_orders)
    assert callable(driver.cancel_order)
    assert callable(driver.start_price_stream)
    assert callable(driver.get_account_summary)
    assert callable(driver.get_open_positions)
    assert callable(driver.get_open_orders)


# ── 7.3 IBKR Live Driver ──

def test_ibkr_live_driver_instantiation():
    from qengine.live_drivers.IBKR.IBKRDriver import IBKRLiveDriver
    driver = IBKRLiveDriver()
    assert driver.name == brokers.IBKR
    assert driver.is_demo is False
    assert driver._port == 7497
    assert driver.is_configured is False


def test_ibkr_paper_driver_instantiation():
    from qengine.live_drivers.IBKR.IBKRDriver import IBKRPaperDriver
    driver = IBKRPaperDriver()
    assert driver.name == brokers.IBKR_PAPER
    assert driver.is_demo is True


def test_ibkr_driver_configure():
    from qengine.live_drivers.IBKR.IBKRDriver import IBKRLiveDriver
    driver = IBKRLiveDriver()
    driver.configure(account_id='DU12345', host='192.168.1.10', port=7496, client_id=5)
    assert driver.is_configured is True
    assert driver._account_id == 'DU12345'
    assert driver._host == '192.168.1.10'
    assert driver._port == 7496
    assert driver._client_id == 5


def test_ibkr_driver_has_all_methods():
    from qengine.live_drivers.IBKR.IBKRDriver import IBKRLiveDriver
    driver = IBKRLiveDriver()
    assert callable(driver.market_order)
    assert callable(driver.limit_order)
    assert callable(driver.stop_order)
    assert callable(driver.cancel_all_orders)
    assert callable(driver.cancel_order)
    assert callable(driver.start_price_stream)
    assert callable(driver.get_account_summary)
    assert callable(driver.get_open_positions)
    assert callable(driver.get_open_orders)


# ── 7.4 Base Driver Tests ──

def test_base_driver_is_abstract():
    """ForexLiveDriver can't be instantiated directly due to abstract methods."""
    with pytest.raises(TypeError):
        ForexLiveDriver(name='test')


def test_base_driver_default_not_configured():
    from qengine.live_drivers.OANDA.OandaDriver import OandaLiveDriver
    driver = OandaLiveDriver()
    assert driver.is_configured is False
    assert driver._api_key is None


def test_driver_configure_sets_custom_attrs():
    from qengine.live_drivers.OANDA.OandaDriver import OandaLiveDriver
    driver = OandaLiveDriver()
    driver.configure(api_key='key', account_id='acct', custom_field='hello')
    assert driver._custom_field == 'hello'


# ── 7.5 Cross-driver consistency ──

def test_all_drivers_have_name_and_demo_flag():
    from qengine.live_drivers import live_drivers
    for name, cls in live_drivers.items():
        driver = cls()
        assert hasattr(driver, 'name')
        assert hasattr(driver, 'is_demo')
        assert driver.name == name


def test_demo_drivers_are_marked_demo():
    from qengine.live_drivers.OANDA.OandaDriver import OandaDemoDriver
    from qengine.live_drivers.IG.IGMarketsDriver import IGMarketsDemoDriver
    from qengine.live_drivers.IBKR.IBKRDriver import IBKRPaperDriver

    assert OandaDemoDriver().is_demo is True
    assert IGMarketsDemoDriver().is_demo is True
    assert IBKRPaperDriver().is_demo is True


def test_live_drivers_are_not_demo():
    from qengine.live_drivers.OANDA.OandaDriver import OandaLiveDriver
    from qengine.live_drivers.IG.IGMarketsDriver import IGMarketsLiveDriver
    from qengine.live_drivers.IBKR.IBKRDriver import IBKRLiveDriver

    assert OandaLiveDriver().is_demo is False
    assert IGMarketsLiveDriver().is_demo is False
    assert IBKRLiveDriver().is_demo is False
