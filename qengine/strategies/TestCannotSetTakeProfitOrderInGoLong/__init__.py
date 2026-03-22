from qengine.strategies import Strategy
import qengine.helpers as jh
from qengine import utils


class TestCannotSetTakeProfitOrderInGoLong(Strategy):
    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 1, self.price
        self.take_profit = 1, self.price + 1

    def should_cancel_entry(self):
        return False
