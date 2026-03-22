from qengine.enums import brokers

from qengine.live_drivers.OANDA.OandaDriver import OandaLiveDriver, OandaDemoDriver
from qengine.live_drivers.IG.IGMarketsDriver import IGMarketsLiveDriver, IGMarketsDemoDriver
from qengine.live_drivers.IBKR.IBKRDriver import IBKRLiveDriver, IBKRPaperDriver

live_drivers = {
    brokers.OANDA: OandaLiveDriver,
    brokers.OANDA_DEMO: OandaDemoDriver,
    brokers.IG_MARKETS: IGMarketsLiveDriver,
    brokers.IG_MARKETS_DEMO: IGMarketsDemoDriver,
    brokers.IBKR: IBKRLiveDriver,
    brokers.IBKR_PAPER: IBKRPaperDriver,
}

live_driver_names = list(live_drivers.keys())


def register_driver(name: str, driver_class) -> None:
    """Register a third-party live-trading driver under the given broker name.

    This allows external packages to extend QEngine with new broker integrations
    without modifying the core codebase::

        from qengine.live_drivers import register_driver
        from my_broker import MyBrokerDriver

        register_driver('My Broker', MyBrokerDriver)

    The registered driver will be available for live sessions that reference
    ``'My Broker'`` as the exchange name.
    """
    live_drivers[name] = driver_class
    if name not in live_driver_names:
        live_driver_names.append(name)
