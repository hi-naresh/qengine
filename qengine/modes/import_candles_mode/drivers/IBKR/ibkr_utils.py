from qengine.enums import timeframes


def timeframe_to_bar_size(tf: str) -> str:
    """Convert QEngine timeframe to IBKR bar size string."""
    mapping = {
        timeframes.MINUTE_1: '1 min',
        timeframes.MINUTE_3: '3 mins',
        timeframes.MINUTE_5: '5 mins',
        timeframes.MINUTE_15: '15 mins',
        timeframes.MINUTE_30: '30 mins',
        timeframes.HOUR_1: '1 hour',
        timeframes.HOUR_2: '2 hours',
        timeframes.HOUR_3: '3 hours',
        timeframes.HOUR_4: '4 hours',
        timeframes.DAY_1: '1 day',
        timeframes.WEEK_1: '1 week',
        timeframes.MONTH_1: '1 month',
    }
    return mapping.get(tf, '1 hour')


def timeframe_to_duration(tf: str, count: int) -> str:
    """Calculate IBKR duration string based on timeframe and count."""
    minutes = {
        timeframes.MINUTE_1: 1,
        timeframes.MINUTE_3: 3,
        timeframes.MINUTE_5: 5,
        timeframes.MINUTE_15: 15,
        timeframes.MINUTE_30: 30,
        timeframes.HOUR_1: 60,
        timeframes.HOUR_2: 120,
        timeframes.HOUR_3: 180,
        timeframes.HOUR_4: 240,
        timeframes.DAY_1: 1440,
        timeframes.WEEK_1: 10080,
    }.get(tf, 60)

    total_minutes = minutes * count
    days = max(1, total_minutes // 1440 + 1)

    if days <= 365:
        return f'{days} D'
    else:
        years = max(1, days // 365)
        return f'{years} Y'


def symbol_to_contract_params(symbol: str) -> dict:
    """Convert internal symbol to IBKR contract parameters."""
    base = symbol.split('-')[0]
    quote = symbol.split('-')[1]

    # Forex
    forex_currencies = {
        'EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY',
        'SEK', 'NOK', 'DKK', 'SGD', 'HKD', 'TRY', 'ZAR', 'MXN',
    }
    if base in forex_currencies and quote in forex_currencies:
        return {
            'sec_type': 'CASH',
            'symbol': base,
            'currency': quote,
            'exchange': 'IDEALPRO',
        }

    # Commodities - metals
    metal_map = {'XAU': 'GC', 'XAG': 'SI', 'XPT': 'PL', 'XPD': 'PA'}
    if base in metal_map:
        return {
            'sec_type': 'FUT',
            'symbol': metal_map[base],
            'currency': quote,
            'exchange': 'COMEX' if base in ('XAU', 'XAG') else 'NYMEX',
        }

    # Energy
    energy_map = {'WTI': 'CL', 'BCO': 'COIL', 'NATGAS': 'NG'}
    if base in energy_map:
        return {
            'sec_type': 'FUT',
            'symbol': energy_map[base],
            'currency': quote,
            'exchange': 'NYMEX' if base != 'BCO' else 'IPE',
        }

    # Default: treat as stock/CFD
    return {
        'sec_type': 'CFD',
        'symbol': base,
        'currency': quote,
        'exchange': 'SMART',
    }
