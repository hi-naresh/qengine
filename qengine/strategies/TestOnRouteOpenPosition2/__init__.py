from qengine.strategies import Strategy
import qengine.helpers as jh
from qengine import utils


class TestOnRouteOpenPosition2(Strategy):
    def before(self) -> None:
        if self.index == 0:
            assert self.symbol == 'ETH-USDT'

    def should_long(self) -> bool:
        return self.price == 20

    def go_long(self) -> None:
        self.buy = 1, self.price

    def should_cancel_entry(self):
        return False
