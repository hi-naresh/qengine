"""Pure TP/SL trigger logic for CFD tickets.

No engine dependencies — takes a ticket and candle data, returns trigger result.
Used by backtest simulator and live mode sync.
"""
from typing import Optional, Dict


def check_ticket_triggers(
    ticket,
    high: float,
    low: float,
    open_price: float,
    close_price: float,
    mode: str = 'ohlc_walk',
) -> Optional[Dict]:
    """Check if a ticket's TP or SL was hit within a candle.

    Args:
        ticket: Object with .type ('long'/'short'), .tp_price, .sl_price
        high: Candle high
        low: Candle low
        open_price: Candle open
        close_price: Candle close
        mode: 'ohlc_walk' (default) or 'worst_case'

    Returns:
        None if no trigger, or {'reason': 'tp'|'sl', 'price': float}
    """
    tp = getattr(ticket, 'tp_price', None)
    sl = getattr(ticket, 'sl_price', None)

    if tp is None and sl is None:
        return None

    is_long = ticket.type == 'long'

    # Determine which triggers fired
    tp_hit = False
    sl_hit = False

    if tp is not None:
        if is_long:
            tp_hit = high >= tp
        else:
            tp_hit = low <= tp

    if sl is not None:
        if is_long:
            sl_hit = low <= sl
        else:
            sl_hit = high >= sl

    if not tp_hit and not sl_hit:
        return None

    if tp_hit and not sl_hit:
        return {'reason': 'tp', 'price': tp}

    if sl_hit and not tp_hit:
        return {'reason': 'sl', 'price': sl}

    # Both hit — resolve by mode
    if mode == 'worst_case':
        return {'reason': 'sl', 'price': sl}

    # ohlc_walk: Green (close >= open) → O→H→L→C, Red → O→L→H→C
    is_green = close_price >= open_price

    if is_long:
        # Long TP is on high side, SL is on low side
        # Green: O→H→L→C → TP (high side) first
        # Red: O→L→H→C → SL (low side) first
        if is_green:
            return {'reason': 'tp', 'price': tp}
        else:
            return {'reason': 'sl', 'price': sl}
    else:
        # Short TP is on low side, SL is on high side
        # Green: O→H→L→C → SL (high side) first
        # Red: O→L→H→C → TP (low side) first
        if is_green:
            return {'reason': 'sl', 'price': sl}
        else:
            return {'reason': 'tp', 'price': tp}
