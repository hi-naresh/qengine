import qengine.helpers as jh
from qengine.enums import exchanges, brokers, asset_classes, timeframes
from qengine.core.instruments import instrument_registry, Instrument
from qengine.info import broker_info, backtesting_exchanges, live_trading_exchanges
from qengine.config import config
from qengine.routes import router


# ── 1.1 Enum Tests ──

def test_brokers_enum():
    assert brokers.SANDBOX == 'Sandbox'
    assert brokers.OANDA == 'OANDA'
    assert brokers.OANDA_DEMO == 'OANDA Demo'
    assert brokers.IG_MARKETS == 'IG Markets'
    assert brokers.IG_MARKETS_DEMO == 'IG Markets Demo'
    assert brokers.IBKR == 'Interactive Brokers'
    assert brokers.IBKR_PAPER == 'Interactive Brokers Paper'


def test_asset_classes_enum():
    assert asset_classes.FOREX == 'forex'
    assert asset_classes.COMMODITY == 'commodity'
    assert asset_classes.INDEX == 'index'
    assert asset_classes.STOCK == 'stock'
    assert asset_classes.CRYPTO == 'crypto'


def test_exchanges_sandbox_still_exists():
    assert exchanges.SANDBOX == 'Sandbox'


# ── 1.2 Instrument Registry Tests ──

def test_registry_has_major_forex_pairs():
    for symbol in ['EUR-USD', 'GBP-USD', 'USD-JPY', 'USD-CHF', 'AUD-USD', 'NZD-USD', 'USD-CAD']:
        inst = instrument_registry.get(symbol)
        assert inst is not None, f'{symbol} not in registry'
        assert inst.asset_class == 'forex'


def test_registry_has_commodities():
    for symbol in ['XAU-USD', 'XAG-USD', 'BCO-USD', 'WTI-USD']:
        inst = instrument_registry.get(symbol)
        assert inst is not None, f'{symbol} not in registry'
        assert inst.asset_class == 'commodity'


def test_registry_has_indices():
    for symbol in ['US30-USD', 'SPX500-USD', 'NAS100-USD']:
        inst = instrument_registry.get(symbol)
        assert inst is not None, f'{symbol} not in registry'
        assert inst.asset_class == 'index'


def test_forex_pip_sizes():
    assert instrument_registry.get_pip_size('EUR-USD') == 0.0001
    assert instrument_registry.get_pip_size('GBP-USD') == 0.0001
    assert instrument_registry.get_pip_size('USD-JPY') == 0.01
    assert instrument_registry.get_pip_size('EUR-JPY') == 0.01
    assert instrument_registry.get_pip_size('GBP-JPY') == 0.01


def test_commodity_pip_sizes():
    assert instrument_registry.get_pip_size('XAU-USD') == 0.01
    assert instrument_registry.get_pip_size('XAG-USD') == 0.001


def test_contract_sizes():
    assert instrument_registry.get_contract_size('EUR-USD') == 100_000
    assert instrument_registry.get_contract_size('XAU-USD') == 100
    assert instrument_registry.get_contract_size('US30-USD') == 1


def test_instrument_currencies():
    inst = instrument_registry.get('EUR-USD')
    assert inst.base_currency == 'EUR'
    assert inst.quote_currency == 'USD'


def test_list_by_asset_class():
    forex_list = instrument_registry.list_by_asset_class('forex')
    assert 'EUR-USD' in forex_list
    assert 'XAU-USD' not in forex_list

    commodity_list = instrument_registry.list_by_asset_class('commodity')
    assert 'XAU-USD' in commodity_list
    assert 'EUR-USD' not in commodity_list


def test_register_custom_instrument():
    custom = Instrument(
        symbol='TEST-USD',
        asset_class='forex',
        pip_size=0.0001,
        contract_size=100_000,
        min_lot=0.01,
        lot_step=0.01,
        base_currency='TEST',
        quote_currency='USD',
        margin_rate=0.05,
        trading_hours='forex',
    )
    instrument_registry.register(custom)
    assert instrument_registry.get('TEST-USD') is not None
    assert instrument_registry.get_pip_size('TEST-USD') == 0.0001


def test_infer_asset_class_unknown_symbol():
    ac = instrument_registry.get_asset_class('XAU-EUR')
    assert ac == 'commodity'

    ac = instrument_registry.get_asset_class('US30-EUR')
    assert ac == 'index'

    ac = instrument_registry.get_asset_class('CHF-JPY')
    assert ac == 'forex'


def test_infer_pip_size_unknown_symbol():
    pip = instrument_registry.get_pip_size('UNKNOWN-JPY')
    assert pip == 0.01

    pip = instrument_registry.get_pip_size('UNKNOWN-USD')
    assert pip == 0.0001


# ── 1.3 Helper Function Tests ──

def test_get_asset_class_helper():
    assert jh.get_asset_class('EUR-USD') == 'forex'
    assert jh.get_asset_class('XAU-USD') == 'commodity'
    assert jh.get_asset_class('SPX500-USD') == 'index'


def test_get_pip_size_helper():
    assert jh.get_pip_size('EUR-USD') == 0.0001
    assert jh.get_pip_size('USD-JPY') == 0.01
    assert jh.get_pip_size('XAU-USD') == 0.01


def test_get_contract_size_helper():
    assert jh.get_contract_size('EUR-USD') == 100_000
    assert jh.get_contract_size('XAU-USD') == 100


def test_base_and_quote_asset_forex():
    assert jh.base_asset('EUR-USD') == 'EUR'
    assert jh.quote_asset('EUR-USD') == 'USD'
    assert jh.base_asset('XAU-USD') == 'XAU'
    assert jh.quote_asset('GBP-JPY') == 'JPY'


# ── 1.4 Broker Info Tests ──

def test_broker_info_oanda():
    info = broker_info[brokers.OANDA]
    assert info['type'] == 'cfd'
    assert info['fee_model'] == 'spread'
    assert info['settlement_currency'] == 'USD'
    assert 'forex' in info['asset_classes']
    assert 'commodity' in info['asset_classes']
    assert info['modes']['backtesting'] is True
    assert info['modes']['live_trading'] is True


def test_broker_info_ig():
    info = broker_info[brokers.IG_MARKETS]
    assert info['type'] == 'cfd'
    assert 'stock' in info['asset_classes']
    assert info['modes']['backtesting'] is True


def test_broker_info_ibkr():
    info = broker_info[brokers.IBKR]
    assert info['type'] == 'cfd'
    assert info['fee_model'] == 'commission'
    assert info['default_leverage'] == 50


def test_backtesting_exchanges_list():
    assert brokers.OANDA in backtesting_exchanges
    assert brokers.IG_MARKETS in backtesting_exchanges
    assert brokers.IBKR in backtesting_exchanges
    assert brokers.OANDA_DEMO not in backtesting_exchanges


def test_live_trading_exchanges_list():
    assert brokers.OANDA in live_trading_exchanges
    assert brokers.OANDA_DEMO in live_trading_exchanges


# ── 1.5 Config Tests ──

def test_brokers_in_config():
    assert brokers.OANDA in config['env']['exchanges']
    assert brokers.IG_MARKETS in config['env']['exchanges']
    assert brokers.IBKR in config['env']['exchanges']
    assert config['env']['exchanges'][brokers.OANDA]['type'] == 'cfd'
    assert config['env']['exchanges'][brokers.IBKR]['futures_leverage'] == 50


def test_sandbox_still_in_config():
    assert exchanges.SANDBOX in config['env']['exchanges']
    assert config['env']['exchanges'][exchanges.SANDBOX]['balance'] == 10_000


# ── 1.6 Routes - No Same Quote Constraint ──

def test_routes_allow_different_quote_currencies():
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'EUR-USD', 'timeframe': '1m', 'strategy': 'Test19'},
        {'exchange': exchanges.SANDBOX, 'symbol': 'GBP-JPY', 'timeframe': '1m', 'strategy': 'Test19'},
    ])
    assert len(router.routes) == 2
    assert router.routes[0].symbol == 'EUR-USD'
    assert router.routes[1].symbol == 'GBP-JPY'


def test_routes_app_currency_fallback():
    router.initiate(
        [{'exchange': exchanges.SANDBOX, 'symbol': 'EUR-USD', 'timeframe': timeframes.HOUR_1, 'strategy': 'Test19'}])
    assert jh.app_currency() == 'USD'


def test_routes_broker_settlement_currency():
    router.initiate(
        [{'exchange': brokers.OANDA, 'symbol': 'EUR-USD', 'timeframe': timeframes.HOUR_1, 'strategy': 'Test19'}])
    assert jh.app_currency() == 'USD'
