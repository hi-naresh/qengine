from qengine.models.Candle import Candle
import qengine.helpers as jh
from typing import List
import numpy as np
import arrow


def delete_candles_from_db(exchange: str, symbol: str) -> None:
    """
    Deletes all candles for the given exchange and symbol
    """
    Candle.delete().where(
        Candle.exchange == exchange,
        Candle.symbol == symbol
    ).execute()


def get_existing_candles() -> List[dict]:
    """
    Returns a list of all existing candles grouped by exchange and symbol.
    Includes date range, candle count, and available timeframes.
    """
    from peewee import fn

    # Query: group by exchange, symbol, timeframe to get stats per timeframe
    query = (
        Candle
        .select(
            Candle.exchange,
            Candle.symbol,
            Candle.timeframe,
            fn.MIN(Candle.timestamp).alias('first_ts'),
            fn.MAX(Candle.timestamp).alias('last_ts'),
            fn.COUNT(Candle.id).alias('cnt'),
        )
        .group_by(Candle.exchange, Candle.symbol, Candle.timeframe)
        .order_by(Candle.exchange, Candle.symbol, Candle.timeframe)
        .dicts()
    )

    # Group by (exchange, symbol), merge timeframes
    grouped = {}
    for row in query:
        key = (row['exchange'], row['symbol'])
        if key not in grouped:
            grouped[key] = {
                'first_ts': row['first_ts'],
                'last_ts': row['last_ts'],
                'count': row['cnt'],
                'timeframes': [row['timeframe']],
            }
        else:
            g = grouped[key]
            g['first_ts'] = min(g['first_ts'], row['first_ts'])
            g['last_ts'] = max(g['last_ts'], row['last_ts'])
            g['count'] += row['cnt']
            g['timeframes'].append(row['timeframe'])

    # Count candles with spread data and market-open candles per exchange/symbol
    spread_counts = {}
    market_open_counts = {}
    try:
        from peewee import fn as fn2
        spread_query = (
            Candle
            .select(Candle.exchange, Candle.symbol, fn2.COUNT(Candle.id).alias('cnt'))
            .where(Candle.spread.is_null(False))
            .group_by(Candle.exchange, Candle.symbol)
            .tuples()
        )
        for ex, sym, cnt in spread_query:
            spread_counts[(ex, sym)] = cnt

        vol_query = (
            Candle
            .select(Candle.exchange, Candle.symbol, fn2.COUNT(Candle.id).alias('cnt'))
            .where(Candle.volume > 0)
            .group_by(Candle.exchange, Candle.symbol)
            .tuples()
        )
        for ex, sym, cnt in vol_query:
            market_open_counts[(ex, sym)] = cnt
    except Exception:
        pass

    results = []
    for (exchange, symbol), g in grouped.items():
        start_str = arrow.get(g['first_ts'] / 1000).format('YYYY-MM-DD')
        end_str = arrow.get(g['last_ts'] / 1000).format('YYYY-MM-DD')
        sc = spread_counts.get((exchange, symbol), 0)
        mc = market_open_counts.get((exchange, symbol), 0)
        results.append({
            'exchange': exchange,
            'symbol': symbol,
            'from': start_str,
            'to': end_str,
            'count': g['count'],
            'timeframes': sorted(g['timeframes']),
            'has_spread': sc > 0,
            'spread_coverage': round(sc / mc * 100, 1) if mc > 0 else 0,
            # aliases for Backtest.vue compatibility
            'start_date': start_str,
            'end_date': end_str,
        })

    return results


def fetch_candles_from_db(exchange: str, symbol: str, timeframe: str, start_date: int, finish_date: int) -> tuple:
    res = tuple(
        Candle.select(
            Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
            Candle.volume
        ).where(
            Candle.exchange == exchange,
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
            Candle.timestamp.between(start_date, finish_date)
        ).order_by(Candle.timestamp.asc()).tuples()
    )

    return res


def store_candles_into_db(exchange: str, symbol: str, timeframe: str, candles: np.ndarray, on_conflict='ignore') -> None:
    # make sure the number of candles is more than 0
    if len(candles) == 0:
        raise Exception(f'No candles to store for {exchange}-{symbol}-{timeframe}')

    # convert candles to list of dicts
    candles_list = []
    for candle in candles:
        d = {
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': exchange,
            'timestamp': candle[0],
            'open': candle[1],
            'high': candle[3],
            'low': candle[4],
            'close': candle[2],
            'volume': candle[5],
            'timeframe': timeframe,
        }
        candles_list.append(d)

    if on_conflict == 'ignore':
        Candle.insert_many(candles_list).on_conflict_ignore().execute()
    elif on_conflict == 'replace':
        Candle.insert_many(candles_list).on_conflict(
            conflict_target=['exchange', 'symbol', 'timeframe', 'timestamp'],
            preserve=(Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume),
        ).execute()
    elif on_conflict == 'error':
        Candle.insert_many(candles_list).execute()
    else:
        raise Exception(f'Unknown on_conflict value: {on_conflict}')


def store_candle_into_db(exchange: str, symbol: str, timeframe: str, candle: np.ndarray, on_conflict='ignore') -> None:
    d = {
        'id': jh.generate_unique_id(),
        'exchange': exchange,
        'symbol': symbol,
        'timeframe': timeframe,
        'timestamp': candle[0],
        'open': candle[1],
        'high': candle[3],
        'low': candle[4],
        'close': candle[2],
        'volume': candle[5]
    }

    if on_conflict == 'ignore':
        Candle.insert(**d).on_conflict_ignore().execute()
    elif on_conflict == 'replace':
        Candle.insert(**d).on_conflict(
            conflict_target=['exchange', 'symbol', 'timeframe', 'timestamp'],
            preserve=(Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume),
        ).execute()
    elif on_conflict == 'error':
        Candle.insert(**d).execute()
    else:
        raise Exception(f'Unknown on_conflict value: {on_conflict}')
