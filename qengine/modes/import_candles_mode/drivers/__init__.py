from qengine.enums import brokers
from qengine.modes.import_candles_mode.drivers.OANDA.OandaForex import OandaForex, OandaDemoForex
from qengine.modes.import_candles_mode.drivers.IG.IGMarketsForex import IGMarketsForex, IGMarketsDemoForex
from qengine.modes.import_candles_mode.drivers.IBKR.IBKRForex import IBKRForex, IBKRPaperForex

drivers = {
    brokers.OANDA: OandaForex,
    brokers.OANDA_DEMO: OandaDemoForex,
    brokers.IG_MARKETS: IGMarketsForex,
    brokers.IG_MARKETS_DEMO: IGMarketsDemoForex,
    brokers.IBKR: IBKRForex,
    brokers.IBKR_PAPER: IBKRPaperForex,
}

driver_names = list(drivers.keys())


def register_driver(name: str, driver_class) -> None:
    """Register a third-party candle-import driver under the given exchange name.

    This allows external packages to extend QEngine with new data-source
    integrations without modifying the core codebase::

        from qengine.modes.import_candles_mode.drivers import register_driver
        from my_exchange import MyExchangeCandles

        register_driver('My Exchange', MyExchangeCandles)

    The registered driver will be available for candle-import sessions that
    reference ``'My Exchange'`` as the exchange name.
    """
    drivers[name] = driver_class
    if name not in driver_names:
        driver_names.append(name)
