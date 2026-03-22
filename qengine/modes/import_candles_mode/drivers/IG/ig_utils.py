from qengine.enums import timeframes


# IG Markets uses "epic" codes for instruments
# This is a default mapping; can be extended via config
DEFAULT_EPIC_MAP = {
    # Forex
    'EUR-USD': 'CS.D.EURUSD.CFD.IP',
    'GBP-USD': 'CS.D.GBPUSD.CFD.IP',
    'USD-JPY': 'CS.D.USDJPY.CFD.IP',
    'USD-CHF': 'CS.D.USDCHF.CFD.IP',
    'AUD-USD': 'CS.D.AUDUSD.CFD.IP',
    'NZD-USD': 'CS.D.NZDUSD.CFD.IP',
    'USD-CAD': 'CS.D.USDCAD.CFD.IP',
    'EUR-GBP': 'CS.D.EURGBP.CFD.IP',
    'EUR-JPY': 'CS.D.EURJPY.CFD.IP',
    'GBP-JPY': 'CS.D.GBPJPY.CFD.IP',
    # Commodities
    'XAU-USD': 'CS.D.USCGC.TODAY.IP',
    'XAG-USD': 'CS.D.USCSI.TODAY.IP',
    'BCO-USD': 'CC.D.LCO.UNC.IP',
    'WTI-USD': 'CC.D.CL.UNC.IP',
    # Indices
    'US30-USD': 'IX.D.DOW.IFD.IP',
    'SPX500-USD': 'IX.D.SPTRD.IFD.IP',
    'NAS100-USD': 'IX.D.NASDAQ.IFD.IP',
    'UK100-GBP': 'IX.D.FTSE.CFD.IP',
    'DE30-EUR': 'IX.D.DAX.IFD.IP',
}


def symbol_to_epic(symbol: str, epic_map: dict = None) -> str:
    """Convert internal symbol to IG Markets epic code."""
    if epic_map and symbol in epic_map:
        return epic_map[symbol]
    return DEFAULT_EPIC_MAP.get(symbol, symbol)


def timeframe_to_resolution(tf: str) -> str:
    """Convert QEngine timeframe to IG resolution."""
    mapping = {
        timeframes.MINUTE_1: 'MINUTE',
        timeframes.MINUTE_3: 'MINUTE_3',
        timeframes.MINUTE_5: 'MINUTE_5',
        timeframes.MINUTE_15: 'MINUTE_15',
        timeframes.MINUTE_30: 'MINUTE_30',
        timeframes.HOUR_1: 'HOUR',
        timeframes.HOUR_2: 'HOUR_2',
        timeframes.HOUR_3: 'HOUR_3',
        timeframes.HOUR_4: 'HOUR_4',
        timeframes.DAY_1: 'DAY',
        timeframes.WEEK_1: 'WEEK',
        timeframes.MONTH_1: 'MONTH',
    }
    return mapping.get(tf, 'HOUR')


def get_api_url(demo: bool = False) -> str:
    if demo:
        return 'https://demo-api.ig.com/gateway/deal'
    return 'https://api.ig.com/gateway/deal'
