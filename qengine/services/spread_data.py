"""
Real spread data store.

Stores per-candle spread values (ask - bid at candle open) loaded from DB.
The CFDExchange cost model reads from here instead of using a fixed spread
when real data is available.

Usage:
    from qengine.services import spread_data

    # During candle loading (candle_service.py):
    spread_data.set_spread('OANDA', 'EUR-USD', timestamp_ms, 0.00018)

    # During execution (CFDExchange.get_spread):
    real_spread = spread_data.get_spread('OANDA', 'EUR-USD', timestamp_ms)
    # Returns None if no real data for this timestamp
"""

from typing import Optional, Dict

# Storage: {f"{exchange}-{symbol}": {timestamp_ms: spread_price_units}}
_spread_store: Dict[str, Dict[int, float]] = {}

# Stats
_hits = 0
_misses = 0


def set_spread(exchange: str, symbol: str, timestamp_ms: int, spread: float) -> None:
    """Store a real spread value for a specific candle."""
    key = f"{exchange}-{symbol}"
    if key not in _spread_store:
        _spread_store[key] = {}
    _spread_store[key][timestamp_ms] = spread


def get_spread(exchange: str, symbol: str, timestamp_ms: int) -> Optional[float]:
    """Get real spread for a specific candle timestamp.

    Returns None if no real spread data exists (fallback to fixed spread).
    """
    global _hits, _misses
    key = f"{exchange}-{symbol}"
    store = _spread_store.get(key)
    if store is None:
        _misses += 1
        return None
    val = store.get(int(timestamp_ms))
    if val is not None:
        _hits += 1
    else:
        _misses += 1
    return val


def has_data(exchange: str, symbol: str) -> bool:
    """Check if real spread data is loaded for this exchange/symbol."""
    key = f"{exchange}-{symbol}"
    return key in _spread_store and len(_spread_store[key]) > 0


def stats() -> dict:
    """Return hit/miss stats for monitoring."""
    total = _hits + _misses
    return {
        'hits': _hits,
        'misses': _misses,
        'hit_rate': _hits / total if total > 0 else 0.0,
        'symbols_loaded': len(_spread_store),
        'total_candles': sum(len(v) for v in _spread_store.values()),
    }


def clear() -> None:
    """Clear all stored spread data (between backtests)."""
    global _hits, _misses
    _spread_store.clear()
    _hits = 0
    _misses = 0
