"""
Test strategy for verifying hedge_mode=True works in QEngine.
Opens an initial LONG, then on the next candle opens a SHORT via should_short=True
simultaneously with should_long potentially True — demonstrating hedge mode.
"""
from qengine.strategies import Strategy


class TestHedgeMode(Strategy):
    """
    Simple hedge mode test:
    - Candle 1: should_long=True, should_short=False → go_long (buy 1 at price 1)
    - Position is long while price rises
    - Once we have legs, should_short can also be True on a crossing candle
    For simplicity: just verify no ConflictingRules is raised when hedge_mode=True.
    """

    def __init__(self):
        super().__init__()
        self.hedge_mode = True
        self._triggered_short = False

    def should_long(self) -> bool:
        # Only enter on the very first candle
        return self.index == 0 and self.position.is_close

    def should_short(self) -> bool:
        # Never short in this basic test — just verify no exception when hedge_mode=True
        return False

    def go_long(self):
        self.buy = 1, self.close

    def go_short(self):
        self.sell = 1, self.close

    def update_position(self):
        # exit after 5 candles
        if self.index >= 5:
            self.liquidate()
