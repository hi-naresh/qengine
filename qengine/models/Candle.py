import peewee
from qengine.services.db import database
import qengine.helpers as jh
import numpy as np


if database.is_closed():
    database.open_connection()


class Candle(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    timestamp = peewee.BigIntegerField()
    open = peewee.FloatField()
    close = peewee.FloatField()
    high = peewee.FloatField()
    low = peewee.FloatField()
    volume = peewee.FloatField()
    exchange = peewee.CharField()
    symbol = peewee.CharField()
    timeframe = peewee.CharField()
    # Real spread from broker (ask - bid) at candle open, in price units.
    # NULL = not available (legacy data or broker doesn't provide it).
    spread = peewee.FloatField(null=True, default=None)

    # partial candles: 5 * 1m candle = 5m candle while 1m == partial candle
    is_partial = True

    class Meta:
        from qengine.services.db import database

        database = database.db
        indexes = (
            (('exchange', 'symbol', 'timeframe', 'timestamp'), True),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)


# if database is open, create the table
if database.is_open():
    Candle.create_table()
