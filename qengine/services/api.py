import threading
from typing import Union

import qengine.helpers as jh
from qengine.models.Order import Order
from qengine.services import logger


class API:
    """Unified exchange API facade.

    Drivers are **not** initialised at construction time.  Call
    :meth:`initiate_drivers` explicitly once the session configuration is
    ready (i.e. after ``config['app']['considering_exchanges']`` is populated).
    This avoids the eager-instantiation problem where importing this module
    before the config is set up would raise an exception.
    """

    def __init__(self) -> None:
        self.drivers = {}

    def initiate_drivers(self) -> None:
        considering_exchanges = jh.get_config('app.considering_exchanges')

        # A helpful assertion
        if not len(considering_exchanges):
            raise Exception('No exchange is available for initiating in the API class')

        for e in considering_exchanges:
            if jh.is_live():
                def initiate_ws(exchange_name: str) -> None:
                    exchange_class = jh.get_config(f'app.live_drivers.{exchange_name}')
                    self.drivers[exchange_name] = exchange_class()

                threading.Thread(target=initiate_ws, args=[e]).start()
            else:
                from qengine.exchanges import Sandbox
                self.drivers[e] = Sandbox(e)

    def market_order(
        self,
        exchange: str,
        symbol: str,
        qty: float,
        current_price: float,
        side: str,
        reduce_only: bool
    ) -> Union[Order, None]:
        if exchange not in self.drivers:
            logger.info(f'Exchange "{exchange}" driver not initiated yet. Trying again in the next candle')
            return None
        return self.drivers[exchange].market_order(symbol, qty, current_price, side, reduce_only)

    def limit_order(
        self,
        exchange: str,
        symbol: str,
        qty: float,
        price: float,
        side: str,
        reduce_only: bool
    ) -> Union[Order, None]:
        if exchange not in self.drivers:
            logger.info(f'Exchange "{exchange}" driver not initiated yet. Trying again in the next candle')
            return None
        return self.drivers[exchange].limit_order(symbol, qty, price, side, reduce_only)

    def stop_order(
        self, exchange: str,
        symbol: str,
        qty: float,
        price: float,
        side: str,
        reduce_only: bool
    ) -> Union[Order, None]:
        if exchange not in self.drivers:
            logger.info(f'Exchange "{exchange}" driver not initiated yet. Trying again in the next candle')
            return None
        return self.drivers[exchange].stop_order(symbol, qty, price, side, reduce_only)

    def cancel_all_orders(self, exchange: str, symbol: str) -> bool:
        if exchange not in self.drivers:
            logger.info(f'Exchange "{exchange}" driver not initiated yet. Trying again in the next candle')
            return False
        return self.drivers[exchange].cancel_all_orders(symbol)

    def cancel_order(self, exchange: str, symbol: str, order_id: str) -> bool:
        if exchange not in self.drivers:
            logger.info(f'Exchange "{exchange}" driver not initiated yet. Trying again in the next candle')
            return False
        return self.drivers[exchange].cancel_order(symbol, order_id)


# Module-level singleton.  Drivers are intentionally **not** initialised here;
# call api.initiate_drivers() after the session config has been populated.
api = API()
