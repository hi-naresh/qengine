from qengine.enums import timeframes


def symbol_to_instrument(symbol: str) -> str:
    """Convert internal symbol format to OANDA instrument format.
    EUR-USD -> EUR_USD
    XAU-USD -> XAU_USD
    """
    return symbol.replace('-', '_')


def instrument_to_symbol(instrument: str) -> str:
    """Convert OANDA instrument format to internal symbol format.
    EUR_USD -> EUR-USD
    """
    return instrument.replace('_', '-')


def timeframe_to_granularity(tf: str) -> str:
    """Convert QEngine timeframe to OANDA granularity."""
    mapping = {
        # Sub-minute granularities (OANDA-specific)
        '5s': 'S5',
        '10s': 'S10',
        '15s': 'S15',
        '30s': 'S30',
        # Standard timeframes
        timeframes.MINUTE_1: 'M1',
        timeframes.MINUTE_3: 'M3',  # Not natively supported, handled by 1m aggregation
        timeframes.MINUTE_5: 'M5',
        timeframes.MINUTE_15: 'M15',
        timeframes.MINUTE_30: 'M30',
        timeframes.MINUTE_45: 'M45',  # Not standard, use M30 or M15
        timeframes.HOUR_1: 'H1',
        timeframes.HOUR_2: 'H2',
        timeframes.HOUR_3: 'H3',
        timeframes.HOUR_4: 'H4',
        timeframes.HOUR_6: 'H6',
        timeframes.HOUR_8: 'H8',
        timeframes.HOUR_12: 'H12',
        timeframes.DAY_1: 'D',
        timeframes.WEEK_1: 'W',
        timeframes.MONTH_1: 'M',
    }
    return mapping.get(tf, 'H1')


# Number of seconds per granularity (for sub-minute support)
GRANULARITY_SECONDS = {
    '5s': 5, '10s': 10, '15s': 15, '30s': 30,
    '1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800,
}

# How many candles of this granularity fit in 1 minute
CANDLES_PER_MINUTE = {
    '5s': 12, '10s': 6, '15s': 4, '30s': 2, '1m': 1,
}


def get_api_url(practice: bool = False) -> str:
    if practice:
        return 'https://api-fxpractice.oanda.com'
    return 'https://api-fxtrade.oanda.com'
