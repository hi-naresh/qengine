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
