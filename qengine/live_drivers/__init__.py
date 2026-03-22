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
