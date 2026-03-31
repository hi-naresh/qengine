import qengine.helpers as jh
from qengine.modes.utils import get_exchange_type
from qengine.enums import exchanges
from qengine.info import exchange_info, broker_info

# Main configuration used by the QEngine framework. These values are modified
# at runtime based on the mode (backtest, live, or optimize) and user settings.
config = {
    # these values are related to the user's environment
    'env': {
        'caching': {
            'driver': 'pickle'
        },

        'logging': {
            'strategy_execution': True,
            'order_submission': True,
            'order_cancellation': True,
            'order_execution': True,
            'position_opened': True,
            'position_increased': True,
            'position_reduced': True,
            'position_closed': True,
            'shorter_period_candles': False,
            'trading_candles': True,
            'balance_update': True,
            'exchange_ws_reconnection': True
        },

        # fill it later in this file using data in info.py
        'exchanges': {
            exchanges.SANDBOX: {
                'fee': 0,
                'type': 'futures',
                # accepted values are: 'cross' and 'isolated'
                'futures_leverage_mode': 'cross',
                # 1x, 2x, 10x, 50x, etc. Enter as integers
                'futures_leverage': 1,
                'balance': 10_000,
            },
        },

        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # Optimize mode (using Optuna)
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        #
        # Below configurations are related to the optimize mode
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        'optimization': {
            # available ratio options: sharpe, calmar, sortino, omega, serenity, smart sharpe, smart sortino
            'objective_function': 'sharpe',
            # search algorithm: bayesian (TPE), random, cma-es
            'sampler': 'bayesian',
            # number of trials per each hyperparameter
            'trials': 200,
            # number of best candidates to keep and display
            'best_candidates_count': 20,
        },

        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # Data
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        #
        # Below configurations are related to the data
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        'data': {
            # The minimum number of warmup candles that is loaded before each session.
            'warmup_candles_num': 240,
            'generate_candles_from_1m': False,
            'persistency': True,
        },
    },

    # These values are just placeholders used by QEngine at runtime
    'app': {
        # list of currencies to consider
        'considering_symbols': [],
        # The symbol to trade.
        'trading_symbols': [],

        # list of time frames to consider
        'considering_timeframes': [],
        # Which candle type do you intend trade on
        'trading_timeframes': [],

        # list of exchanges to consider
        'considering_exchanges': [],
        # list of exchanges to consider
        'trading_exchanges': [],

        'considering_candles': [],

        # dict of registered live trade drivers
        'live_drivers': {},

        # Accepted values are: 'backtest', 'livetrade', 'fitness'.
        'trading_mode': '',

        # this would enable many console.log()s in the code, which are helpful for debugging.
        'debug_mode': False,

        # this is only used for the live unit tests
        'is_unit_testing': False,
    },
}

# set exchange config values based on exchange_info (legacy, now empty)
for key in exchange_info:
    config['env']['exchanges'][key] = {
        'fee': exchange_info[key]['fee'],
        'type': exchange_info[key]['type'],
        'futures_leverage_mode': 'cross',
        'futures_leverage': 1,
        'balance': 10_000
    }

# set broker config values based on broker_info
for key in broker_info:
    config['env']['exchanges'][key] = {
        'fee': 0,
        'type': broker_info[key]['type'],
        'futures_leverage_mode': 'cross',
        'futures_leverage': broker_info[key].get('default_leverage', 1),
        'balance': 10_000
    }

# register live trading drivers for forex/CFD brokers
try:
    from qengine.live_drivers import live_drivers as _live_drivers
    config['app']['live_drivers'].update(_live_drivers)
except ImportError:
    pass


def set_config(conf: dict) -> None:
    global config

    # optimization mode only
    if jh.is_optimizing():
        # objective function
        if 'objective_function' in conf:
            config['env']['optimization']['objective_function'] = conf['objective_function']
        # warm_up_candles
        if 'warm_up_candles' in conf:
            config['env']['data']['warmup_candles_num'] = int(conf['warm_up_candles'])
        # number of trials per each hyperparameter
        if 'trials' in conf:
            config['env']['optimization']['trials'] = int(conf['trials'])
        # best candidates count
        if 'best_candidates_count' in conf:
            config['env']['optimization']['best_candidates_count'] = int(conf['best_candidates_count'])
        # exchanges - also needed for optimization (used by fitness function)
        for key, e in conf.get('exchanges', {}).items():
            exchange_type = e.get('type', '')
            if not exchange_type:
                exchange_type = get_exchange_type(e['name'])
            config['env']['exchanges'][e['name']] = {
                'fee': float(e.get('fee', 0)),
                'type': exchange_type,
                'balance': float(e.get('balance', 10000))
            }
            if config['env']['exchanges'][e['name']]['type'] in ('futures', 'cfd'):
                default_lev = 1
                if exchange_type in ('cfd',):
                    from qengine.info import broker_info
                    default_lev = broker_info.get(e['name'], {}).get('default_leverage', 30)
                config['env']['exchanges'][e['name']]['futures_leverage'] = int(e.get('futures_leverage', default_lev))
                config['env']['exchanges'][e['name']]['futures_leverage_mode'] = e.get('futures_leverage_mode', 'cross')

    # backtest and live
    if jh.is_backtesting() or jh.is_live():
        # warm_up_candles (use existing default if not provided)
        if 'warm_up_candles' in conf:
            config['env']['data']['warmup_candles_num'] = int(conf['warm_up_candles'])
        # logs
        if 'logging' in conf:
            config['env']['logging'].update(conf['logging'])
        # exchanges
        for key, e in conf.get('exchanges', {}).items():
            if not jh.is_live() and e['type']:
                exchange_type = e['type']
            else:
                exchange_type = get_exchange_type(e['name'])
            config['env']['exchanges'][e['name']] = {
                'fee': float(e['fee']),
                'type': exchange_type,
                'balance': float(e['balance'])
            }
            if config['env']['exchanges'][e['name']]['type'] in ('futures', 'cfd'):
                # For forex/CFD brokers, use broker's default leverage if frontend didn't send it
                default_lev = 1
                if exchange_type in ('cfd',):
                    from qengine.info import broker_info
                    default_lev = broker_info.get(e['name'], {}).get('default_leverage', 30)
                config['env']['exchanges'][e['name']]['futures_leverage'] = int(e.get('futures_leverage', default_lev))
                config['env']['exchanges'][e['name']]['futures_leverage_mode'] = e.get('futures_leverage_mode', 'cross')

        # pipeline configs (framework)
        if 'pipelines' in conf:
            config['app']['pipelines'] = conf['pipelines']

    # live mode only
    if jh.is_live():
        config['env']['notifications'] = conf['notifications']
        config['env']['data']['persistency'] = conf['persistency']
        config['env']['data']['generate_candles_from_1m'] = conf['generate_candles_from_1m']

    # TODO: must become a config value later when we go after multi account support?
    config['env']['identifier'] = 'main'


def reset_config() -> None:
    import copy
    # Mutate in-place instead of rebinding, so all existing references
    # (e.g. `from qengine.config import config as qe_config`) stay valid.
    fresh = copy.deepcopy(backup_config)
    config.clear()
    config.update(fresh)


import copy
backup_config = copy.deepcopy(config)
