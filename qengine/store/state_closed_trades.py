from qengine.models import ClosedTrade
import qengine.helpers as jh


class ClosedTrades:
    def __init__(self) -> None:
        self.trades = []
        self.temp_trades = {}

    def _get_current_trade(self, exchange: str, symbol: str) -> ClosedTrade:
        key = jh.key(exchange, symbol)
        # if already exists, return it
        if key in self.temp_trades:
            t: ClosedTrade = self.temp_trades[key]
            # set the trade.id if not generated already
            if not t.id:
                t.id = jh.generate_unique_id()
            return t
        # else, create a new trade, store it, and return it
        t = ClosedTrade()
        t.id = jh.generate_unique_id()
        self.temp_trades[key] = t
        return t

    def _reset_current_trade(self, exchange: str, symbol: str) -> None:
        key = jh.key(exchange, symbol)
        self.temp_trades[key] = ClosedTrade()

    @property
    def count(self) -> int:
        return len(self.trades)
