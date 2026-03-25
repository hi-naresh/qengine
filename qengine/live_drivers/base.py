import os
from abc import abstractmethod
from typing import List, Optional, Callable

import qengine.helpers as jh
from qengine.exchanges.exchange import Exchange as ExchangeDriver
from qengine.models.Order import Order
from qengine.enums import order_types
from qengine.services import order_service, logger
from qengine.store import store


class ForexLiveDriver(ExchangeDriver):
    """
    Base class for all forex/CFD live trading drivers.
    Provides common functionality for OANDA, IG Markets, IBKR.

    Subclasses must implement:
    - _submit_market_order()
    - _submit_limit_order()
    - _submit_stop_order()
    - _cancel_order_on_exchange()
    - _cancel_all_orders_on_exchange()
    - _fetch_precisions()
    - start_price_stream()
    - get_account_summary()
    - get_open_positions()
    - get_open_orders()
    """

    def __init__(self, name: str, is_demo: bool = False):
        super().__init__()
        self.name = name
        self.is_demo = is_demo
        self._api_key: Optional[str] = None
        self._account_id: Optional[str] = None
        self._connected = False
        self._price_callbacks: List[Callable] = []

    def configure(self, api_key: str, account_id: str = None, **kwargs) -> None:
        """Configure the driver with API credentials."""
        self._api_key = api_key
        self._account_id = account_id
        for k, v in kwargs.items():
            setattr(self, f'_{k}', v)

    @property
    def is_configured(self) -> bool:
        return self._api_key is not None

    # ── Exchange ABC Implementation ──

    def market_order(self, symbol: str, qty: float, current_price: float, side: str, reduce_only: bool) -> Order:
        result = self._submit_market_order(symbol, qty, current_price, side, reduce_only)

        # _submit_market_order returns a dict with order_id, fill_price, and trade_id
        if isinstance(result, dict):
            exchange_order_id = result['order_id']
            fill_price = result.get('fill_price') or current_price
            trade_id = result.get('trade_id')
        else:
            # Backwards compatibility if subclass still returns a string
            exchange_order_id = result
            fill_price = current_price
            trade_id = None

        order = order_service.create_order({
            'id': jh.generate_unique_id(),
            'exchange_id': exchange_order_id,
            'symbol': symbol,
            'exchange': self.name,
            'side': side,
            'type': order_types.MARKET,
            'reduce_only': reduce_only,
            'qty': jh.prepare_qty(qty, side),
            'price': fill_price,
        })

        # Store trade_id on the order for CFDTicket linking
        if trade_id:
            order.vars['trade_id'] = trade_id

        # OANDA/broker market orders are FOK — filled immediately on submission.
        # Mark as executed internally so position state updates.
        order.filled_qty = order.qty
        order_service.execute_order(order)

        return order

    def limit_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> Order:
        exchange_order_id = self._submit_limit_order(symbol, qty, price, side, reduce_only)

        return order_service.create_order({
            'id': jh.generate_unique_id(),
            'exchange_id': exchange_order_id,
            'symbol': symbol,
            'exchange': self.name,
            'side': side,
            'type': order_types.LIMIT,
            'reduce_only': reduce_only,
            'qty': jh.prepare_qty(qty, side),
            'price': price,
        })

    def stop_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> Order:
        exchange_order_id = self._submit_stop_order(symbol, qty, price, side, reduce_only)

        return order_service.create_order({
            'id': jh.generate_unique_id(),
            'exchange_id': exchange_order_id,
            'symbol': symbol,
            'exchange': self.name,
            'side': side,
            'type': order_types.STOP,
            'reduce_only': reduce_only,
            'qty': jh.prepare_qty(qty, side),
            'price': price,
        })

    def cancel_all_orders(self, symbol: str) -> List[Order]:
        self._cancel_all_orders_on_exchange(symbol)

        orders = store.orders.get_active_orders(self.name, symbol)
        canceled = []
        for o in orders:
            order_service.cancel_order(o)
            canceled.append(o)
        return canceled

    def cancel_order(self, symbol: str, order_id: str) -> None:
        order = store.orders.get_order_by_id(self.name, symbol, order_id)
        if order and hasattr(order, 'exchange_id') and order.exchange_id:
            self._cancel_order_on_exchange(symbol, order.exchange_id)
        order_service.cancel_order(order)

    # ── Abstract methods for subclasses ──

    @abstractmethod
    def _submit_market_order(self, symbol: str, qty: float, current_price: float, side: str, reduce_only: bool):
        """Submit market order to exchange. Returns dict with 'order_id' and 'fill_price', or a string order ID for backwards compatibility."""
        pass

    @abstractmethod
    def _submit_limit_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> str:
        """Submit limit order to exchange. Returns exchange order ID."""
        pass

    @abstractmethod
    def _submit_stop_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> str:
        """Submit stop order to exchange. Returns exchange order ID."""
        pass

    @abstractmethod
    def _cancel_order_on_exchange(self, symbol: str, exchange_order_id: str) -> None:
        """Cancel a specific order on the exchange."""
        pass

    @abstractmethod
    def _cancel_all_orders_on_exchange(self, symbol: str) -> None:
        """Cancel all orders for a symbol on the exchange."""
        pass

    @abstractmethod
    def start_price_stream(self, symbols: List[str], callback: Callable) -> None:
        """Start real-time price streaming for given symbols."""
        pass

    @abstractmethod
    def get_account_summary(self) -> dict:
        """Get account balance, margin, P&L from exchange."""
        pass

    @abstractmethod
    def get_open_positions(self) -> List[dict]:
        """Get currently open positions from exchange."""
        pass

    @abstractmethod
    def get_open_orders(self) -> List[dict]:
        """Get currently open/pending orders from exchange."""
        pass

    def get_open_trades(self) -> List[dict]:
        """Get individual open trades (for per-trade TP/SL in hedging mode). Optional."""
        return []

    def set_trade_tp_sl(self, trade_id: str, take_profit: float = None, stop_loss: float = None) -> None:
        """Set TP/SL on an individual trade. Optional — only for hedging-mode brokers."""
        pass

    def cancel_trade_tp_sl(self, trade_id: str) -> None:
        """Remove TP/SL from a trade. Optional."""
        pass

    def close_trade(self, trade_id: str, units: float = None) -> dict:
        """Close an individual trade. Optional."""
        return {}
