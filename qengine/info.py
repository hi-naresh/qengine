from qengine.enums import brokers, timeframes
from qengine.services.env import ENV_VALUES, is_dev_env


# Upstream API endpoints (jesse.trade marketplace — retained for strategy marketplace compatibility)
if is_dev_env():
    QENGINE_API_URL = ENV_VALUES.get('QENGINE_API_URL', 'http://localhost:8040/api')
    QENGINE_API2_URL = ENV_VALUES.get('QENGINE_API2_URL', 'http://localhost:8080')
else:
    QENGINE_API_URL = 'https://api1.jesse.trade/api'
    QENGINE_API2_URL = 'https://api2.jesse.trade'

ALL_TIMEFRAMES = [
    timeframes.MINUTE_1, timeframes.MINUTE_3, timeframes.MINUTE_5,
    timeframes.MINUTE_15, timeframes.MINUTE_30, timeframes.MINUTE_45,
    timeframes.HOUR_1, timeframes.HOUR_2, timeframes.HOUR_3,
    timeframes.HOUR_4, timeframes.HOUR_6, timeframes.HOUR_8,
    timeframes.HOUR_12, timeframes.DAY_1,
]

# exchange_info is what the frontend reads from /system/general-info
# to populate exchange dropdowns. Map broker_info into the format the UI expects.
exchange_info = {}

broker_info = {
    brokers.OANDA: {
        'name': 'OANDA',
        'type': 'forex_cfd',
        'url': 'https://www.oanda.com',
        'asset_classes': ['forex', 'commodity', 'index'],
        'fee_model': 'spread',
        'default_leverage': 30,
        'supported_timeframes': ALL_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'paper_trading': True,
            'live_trading': True,
        },
        'api_type': 'rest_streaming',
        'settlement_currency': 'USD',
    },
    brokers.OANDA_DEMO: {
        'name': 'OANDA Demo',
        'type': 'forex_cfd',
        'url': 'https://www.oanda.com',
        'asset_classes': ['forex', 'commodity', 'index'],
        'fee_model': 'spread',
        'default_leverage': 30,
        'supported_timeframes': ALL_TIMEFRAMES,
        'modes': {
            'backtesting': False,
            'paper_trading': True,
            'live_trading': True,
        },
        'api_type': 'rest_streaming',
        'settlement_currency': 'USD',
    },
    brokers.IG_MARKETS: {
        'name': 'IG Markets',
        'type': 'cfd',
        'url': 'https://www.ig.com',
        'asset_classes': ['forex', 'commodity', 'index', 'stock'],
        'fee_model': 'spread',
        'default_leverage': 30,
        'supported_timeframes': ALL_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'paper_trading': True,
            'live_trading': True,
        },
        'api_type': 'rest_streaming',
        'settlement_currency': 'USD',
    },
    brokers.IG_MARKETS_DEMO: {
        'name': 'IG Markets Demo',
        'type': 'cfd',
        'url': 'https://www.ig.com',
        'asset_classes': ['forex', 'commodity', 'index', 'stock'],
        'fee_model': 'spread',
        'default_leverage': 30,
        'supported_timeframes': ALL_TIMEFRAMES,
        'modes': {
            'backtesting': False,
            'paper_trading': True,
            'live_trading': True,
        },
        'api_type': 'rest_streaming',
        'settlement_currency': 'USD',
    },
    brokers.IBKR: {
        'name': 'Interactive Brokers',
        'type': 'multi_asset',
        'url': 'https://www.interactivebrokers.com',
        'asset_classes': ['forex', 'commodity', 'stock', 'index'],
        'fee_model': 'commission',
        'default_leverage': 50,
        'supported_timeframes': ALL_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'paper_trading': True,
            'live_trading': True,
        },
        'api_type': 'tws_socket',
        'settlement_currency': 'USD',
    },
    brokers.IBKR_PAPER: {
        'name': 'Interactive Brokers Paper',
        'type': 'multi_asset',
        'url': 'https://www.interactivebrokers.com',
        'asset_classes': ['forex', 'commodity', 'stock', 'index'],
        'fee_model': 'commission',
        'default_leverage': 50,
        'supported_timeframes': ALL_TIMEFRAMES,
        'modes': {
            'backtesting': False,
            'paper_trading': True,
            'live_trading': True,
        },
        'api_type': 'tws_socket',
        'settlement_currency': 'USD',
    },
}

# Build exchange_info from broker_info for the frontend UI
# The frontend reads this from /system/general-info to populate exchange dropdowns
exchange_info = {}
for _k, _v in broker_info.items():
    exchange_info[_k] = {
        'name': _v['name'],
        'fee': 0,  # forex uses spread-based fees, not fixed fee rate
        'type': _v['type'],
        'modes': _v['modes'],
        'required_live_plan': 'free',
        'settlement_currency': _v.get('settlement_currency', 'USD'),
    }

# list of supported brokers for backtesting
backtesting_exchanges = [k for k, v in broker_info.items() if v.get('modes', {}).get('backtesting') is True]
backtesting_exchanges = list(sorted(backtesting_exchanges))

# list of supported brokers for live trading
live_trading_exchanges = [k for k, v in broker_info.items() if v.get('modes', {}).get('live_trading') is True]
live_trading_exchanges = list(sorted(live_trading_exchanges))

# used for backtesting, and live trading when local candle generation is enabled:
qengine_supported_timeframes = ALL_TIMEFRAMES
