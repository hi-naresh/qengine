import threading
from typing import List, Callable

from qengine.enums import brokers
from qengine.live_drivers.base import ForexLiveDriver
from qengine.modes.import_candles_mode.drivers.IBKR.ibkr_utils import symbol_to_contract_params
from qengine.services import logger


class IBKRLiveDriverBase(ForexLiveDriver):
    """
    Interactive Brokers TWS API driver for live/paper trading.
    Uses ib_insync for communication with TWS or IB Gateway.

    Requires:
    - TWS or IB Gateway running on localhost (or configured host)
    - ib_insync package: pip install ib_insync
    """

    def __init__(self, name: str, is_demo: bool = False):
        super().__init__(name=name, is_demo=is_demo)
        self._host = '127.0.0.1'
        self._port = 7496 if not is_demo else 7497
        self._client_id = 1
        self._ib = None

    def configure(self, api_key: str = None, account_id: str = None, **kwargs) -> None:
        # IBKR doesn't use API keys - it connects to local TWS
        self._account_id = account_id
        self._host = kwargs.get('host', self._host)
        self._port = int(kwargs.get('port', self._port))
        self._client_id = int(kwargs.get('client_id', self._client_id))
        self._api_key = 'ibkr-local'  # mark as configured

    @property
    def is_configured(self) -> bool:
        return self._api_key is not None

    def _connect(self) -> None:
        if self._connected and self._ib:
            return
        try:
            from ib_insync import IB
            self._ib = IB()
            self._ib.connect(self._host, self._port, clientId=self._client_id)
            self._connected = True
            logger.info(f'Connected to IBKR TWS at {self._host}:{self._port}')
        except ImportError:
            raise ImportError('ib_insync is required for IBKR live trading. Install: pip install ib_insync')
        except Exception as e:
            raise ConnectionError(f'Could not connect to TWS at {self._host}:{self._port}: {e}')

    def _create_contract(self, symbol: str):
        from ib_insync import Forex, Future, CFD, Contract
        params = symbol_to_contract_params(symbol)

        if params['sec_type'] == 'CASH':
            return Forex(params['symbol'] + params['currency'])
        elif params['sec_type'] == 'FUT':
            return Future(
                symbol=params['symbol'],
                exchange=params['exchange'],
                currency=params['currency'],
            )
        elif params['sec_type'] == 'CFD':
            return CFD(
                symbol=params['symbol'],
                exchange=params['exchange'],
                currency=params['currency'],
            )
        else:
            return Contract(
                symbol=params['symbol'],
                secType=params['sec_type'],
                exchange=params['exchange'],
                currency=params['currency'],
            )

    # ── Order Submission ──

    def _submit_market_order(self, symbol: str, qty: float, current_price: float, side: str, reduce_only: bool) -> str:
        from ib_insync import MarketOrder
        self._connect()
        contract = self._create_contract(symbol)
        action = 'BUY' if side == 'buy' else 'SELL'
        order = MarketOrder(action, abs(qty))
        trade = self._ib.placeOrder(contract, order)
        order_id = str(trade.order.orderId)
        logger.info(f'IBKR market order: {symbol} {action} {abs(qty)} -> ID {order_id}')
        return order_id

    def _submit_limit_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> str:
        from ib_insync import LimitOrder
        self._connect()
        contract = self._create_contract(symbol)
        action = 'BUY' if side == 'buy' else 'SELL'
        order = LimitOrder(action, abs(qty), price)
        trade = self._ib.placeOrder(contract, order)
        order_id = str(trade.order.orderId)
        logger.info(f'IBKR limit order: {symbol} {action} {abs(qty)}@{price} -> ID {order_id}')
        return order_id

    def _submit_stop_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> str:
        from ib_insync import StopOrder
        self._connect()
        contract = self._create_contract(symbol)
        action = 'BUY' if side == 'buy' else 'SELL'
        order = StopOrder(action, abs(qty), price)
        trade = self._ib.placeOrder(contract, order)
        order_id = str(trade.order.orderId)
        logger.info(f'IBKR stop order: {symbol} {action} {abs(qty)}@{price} -> ID {order_id}')
        return order_id

    # ── Order Cancellation ──

    def _cancel_order_on_exchange(self, symbol: str, exchange_order_id: str) -> None:
        self._connect()
        for trade in self._ib.openTrades():
            if str(trade.order.orderId) == exchange_order_id:
                self._ib.cancelOrder(trade.order)
                logger.info(f'IBKR order {exchange_order_id} cancelled')
                return

    def _cancel_all_orders_on_exchange(self, symbol: str) -> None:
        self._connect()
        contract = self._create_contract(symbol)
        for trade in self._ib.openTrades():
            if trade.contract.symbol == contract.symbol:
                self._ib.cancelOrder(trade.order)
        logger.info(f'IBKR all orders cancelled for {symbol}')

    # ── Streaming ──

    def start_price_stream(self, symbols: List[str], callback: Callable) -> None:
        self._connect()

        def _on_tick(tickers):
            for ticker in tickers:
                if ticker.contract:
                    # Map back to our symbol format
                    sym = f'{ticker.contract.symbol}-{ticker.contract.currency}'
                    bid = ticker.bid if ticker.bid > 0 else ticker.last
                    ask = ticker.ask if ticker.ask > 0 else ticker.last
                    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else ticker.last
                    callback({
                        'symbol': sym,
                        'bid': bid,
                        'ask': ask,
                        'price': mid,
                    })

        for symbol in symbols:
            contract = self._create_contract(symbol)
            self._ib.reqMktData(contract)

        self._ib.pendingTickersEvent += _on_tick

        def _run():
            self._ib.run()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    # ── Account Info ──

    def get_account_summary(self) -> dict:
        self._connect()
        summary = {}
        for item in self._ib.accountSummary():
            if item.tag == 'TotalCashBalance' and item.currency == 'USD':
                summary['balance'] = float(item.value)
            elif item.tag == 'UnrealizedPnL':
                summary['unrealized_pnl'] = float(item.value)
            elif item.tag == 'AvailableFunds':
                summary['margin_available'] = float(item.value)
            elif item.tag == 'NetLiquidation':
                summary['nav'] = float(item.value)
        summary.setdefault('balance', 0)
        summary.setdefault('currency', 'USD')
        return summary

    def get_open_positions(self) -> List[dict]:
        self._connect()
        positions = []
        for pos in self._ib.positions():
            positions.append({
                'symbol': f'{pos.contract.symbol}-{pos.contract.currency}',
                'qty': float(pos.position),
                'avg_cost': float(pos.avgCost),
            })
        return positions

    def get_open_orders(self) -> List[dict]:
        self._connect()
        orders = []
        for trade in self._ib.openTrades():
            orders.append({
                'id': str(trade.order.orderId),
                'symbol': f'{trade.contract.symbol}-{trade.contract.currency}',
                'action': trade.order.action,
                'qty': float(trade.order.totalQuantity),
                'type': trade.order.orderType,
                'price': float(trade.order.lmtPrice or trade.order.auxPrice or 0),
            })
        return orders

    def _fetch_precisions(self) -> None:
        pass

    def _disconnect(self) -> None:
        if self._ib and self._connected:
            self._ib.disconnect()
            self._connected = False

    def __del__(self):
        self._disconnect()


class IBKRLiveDriver(IBKRLiveDriverBase):
    def __init__(self):
        super().__init__(name=brokers.IBKR, is_demo=False)


class IBKRPaperDriver(IBKRLiveDriverBase):
    def __init__(self):
        super().__init__(name=brokers.IBKR_PAPER, is_demo=True)
