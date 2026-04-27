import qengine.helpers as jh
from qengine.config import config
from qengine.exceptions import InvalidConfig
from qengine.models import SpotExchange, FuturesExchange, Exchange
from qengine.models.CFDExchange import CFDExchange
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
        elif exchange_type == 'cfd':
            store.exchanges.storage[name] = CFDExchange(
                name, starting_assets, fee,
                default_leverage=config['env']['exchanges'][name].get('futures_leverage', 30),
            )
            # Always apply structural broker settings (min_order_qty, stop_out_level).
            # Full cost settings (spread, slippage, swap) only when cost_model=True.
            if jh.is_backtesting():
                cost_model_on = config.get('app', {}).get('cost_model', True)
                _apply_backtest_cost_settings(store.exchanges.storage[name], cost_model=cost_model_on)
        else:
            raise InvalidConfig(
                f'Value for exchange type in your config file is not valid. '
                f'Supported values are "spot", "futures", "cfd". '
                f'Your value is "{exchange_type}"'
            )


def _apply_backtest_cost_settings(exchange: CFDExchange, cost_model: bool = True) -> None:
    """Apply backtest settings to a CFD exchange.

    When cost_model=True: apply all settings (spread, slippage, swap, structural).
    When cost_model=False: apply only structural settings (min_order_qty, stop_out_level)
    that affect execution correctness regardless of cost modelling.
    """
    try:
        from qengine.controllers.settings_controller import get_backtest_cost_settings
        bt = get_backtest_cost_settings(exchange.name)
    except Exception:
        bt = {}

    if not cost_model:
        # Only inject structural broker parameters (not cost parameters)
        exchange._bt_cost_settings = {
            'min_order_qty': bt.get('min_order_qty', 0),
            'stop_out_level': bt.get('stop_out_level', 50.0),
        }
        return

    from qengine.core.instruments import instrument_registry

    # Store full backtest cost config on the exchange
    exchange._bt_cost_settings = bt

    # Apply spread from settings to all symbols on this exchange's routes
    spread_pips = bt.get('spread_pips', 2.0)
    for route in config['app'].get('considering_symbols', []):
        pip_size = instrument_registry.get_pip_size(route)
        if pip_size > 0:
            exchange.set_spread(route, pip_size * spread_pips)

    # Apply swap rates per symbol.
    # Priority: per-symbol dict in settings > global swap_long/swap_short > broker defaults
    # Rates are per standard lot (100,000 units) per night in account currency.
    # Negative = charge, Positive = credit.
    swap_rates_dict = bt.get('swap_rates', {})
    global_swap_long = bt.get('swap_long', 0.0)
    global_swap_short = bt.get('swap_short', 0.0)

    for route in config['app'].get('considering_symbols', []):
        symbol_rates = swap_rates_dict.get(route)
        if symbol_rates:
            # Per-symbol override in settings
            exchange.set_swap_rates(
                route,
                swap_long=symbol_rates.get('long', 0.0),
                swap_short=symbol_rates.get('short', 0.0),
            )
        elif global_swap_long != 0.0 or global_swap_short != 0.0:
            # Global swap rates from settings (applies to all symbols)
            exchange.set_swap_rates(route, swap_long=global_swap_long, swap_short=global_swap_short)
        else:
            # Broker-specific defaults for known pairs
            defaults = _DEFAULT_SWAP_RATES.get(exchange.name, {}).get(route)
            if defaults:
                exchange.set_swap_rates(route, swap_long=defaults[0], swap_short=defaults[1])


# Default swap rates per broker/symbol (per lot per night, in USD).
# Based on OANDA UK financing rates page (approximate, rate-environment dependent).
# These represent post-2022 rate-hiking environment (USD rates ~5%).
# Formula: Size × (benchmark_rate + admin_fee) / 365
# OANDA admin fee for FX: 1.0%
# EUR benchmark: ESTR ~3.65%, USD benchmark: SOFR ~5.33% (as of early 2025)
# Long EUR/USD: you borrow USD (pay SOFR+1%), earn EUR (receive ESTR-1%)
#   = -(SOFR+1% - (ESTR-1%)) * 100000 / 365 = -(6.33% - 2.65%) * 100000 / 365 = -$10.08/lot/night
# Short EUR/USD: you borrow EUR (pay ESTR+1%), earn USD (receive SOFR-1%)
#   = -(ESTR+1% - (SOFR-1%)) * 100000 / 365 = -(4.65% - 4.33%) * 100000 / 365 = -$0.88/lot/night
_DEFAULT_SWAP_RATES = {
    'OANDA': {
        'EUR-USD': (-10.0, -0.9),    # long pays ~$10/lot/night, short pays ~$0.9
        'GBP-USD': (-5.5, -2.5),     # GBP rate closer to USD
        'USD-JPY': (8.0, -14.0),     # long earns (USD rate > JPY rate)
        'AUD-USD': (-4.0, -3.5),     # both negative (admin fee)
        'EUR-GBP': (-3.0, -1.5),     # EUR vs GBP differential
    },
    'IG': {
        'EUR-USD': (-9.5, -1.2),
        'GBP-USD': (-5.0, -3.0),
        'USD-JPY': (7.5, -13.5),
    },
}
