import qengine.helpers as jh
from qengine.config import config
from qengine.exceptions import InvalidConfig
from qengine.models import SpotExchange, FuturesExchange, Exchange
from qengine.models.ForexCFDExchange import ForexCFDExchange
from qengine.modes.utils import get_exchange_type
from qengine.store import store


def initialize_exchanges_state() -> None:
    for name in config['app']['considering_exchanges']:
        starting_assets = config['env']['exchanges'][name]['balance']
        fee = config['env']['exchanges'][name]['fee']
        exchange_type = get_exchange_type(name)

        if exchange_type == 'spot':
            store.exchanges.storage[name] = SpotExchange(name, starting_assets, fee)
        elif exchange_type == 'futures':
            store.exchanges.storage[name] = FuturesExchange(
                name, starting_assets, fee,
                futures_leverage_mode=config['env']['exchanges'][name]['futures_leverage_mode'],
                futures_leverage=config['env']['exchanges'][name]['futures_leverage'],
            )
        elif exchange_type in ('forex_cfd', 'cfd', 'multi_asset'):
            store.exchanges.storage[name] = ForexCFDExchange(
                name, starting_assets, fee,
                default_leverage=config['env']['exchanges'][name].get('futures_leverage', 30),
            )
            # Apply backtest cost settings from DB if backtesting and cost model enabled
            if jh.is_backtesting() and config.get('app', {}).get('cost_model', True):
                _apply_backtest_cost_settings(store.exchanges.storage[name])
        else:
            raise InvalidConfig(
                f'Value for exchange type in your config file is not valid. '
                f'Supported values are "spot", "futures", "forex_cfd", "cfd", "multi_asset". '
                f'Your value is "{exchange_type}"'
            )


def _apply_backtest_cost_settings(exchange: ForexCFDExchange) -> None:
    """Apply saved backtest cost/randomness settings to a ForexCFD exchange."""
    try:
        from qengine.controllers.settings_controller import get_backtest_cost_settings
        bt = get_backtest_cost_settings(exchange.name)
    except Exception:
        return

    from qengine.core.instruments import instrument_registry

    # Store backtest cost config on the exchange for use during simulation
    exchange._bt_cost_settings = bt

    # Apply spread from settings to all symbols on this exchange's routes
    spread_pips = bt.get('spread_pips', 2.0)
    for route in config['app'].get('considering_symbols', []):
        pip_size = instrument_registry.get_pip_size(route)
        if pip_size > 0:
            exchange.set_spread(route, pip_size * spread_pips)
