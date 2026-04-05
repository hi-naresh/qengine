from typing import List
import qengine.helpers as jh
import qengine.services.logger as logger
from qengine.config import config
from qengine.services.notifier import notify
from qengine.enums import order_statuses
from qengine.models.Order import Order
from qengine.models.CFDExchange import CFDExchange
from qengine.store import store
from qengine.repositories import order_repository
from qengine.enums import order_types
from qengine.services import closed_trade_service
from qengine.services import position_service


def create_order(attributes: dict, should_silent: bool = False, should_store: bool = True) -> Order:
    if attributes.get('created_at') is None:
        attributes['created_at'] = jh.now_to_timestamp()
    
    order = Order(attributes)
    
    # if for example we are in a live trade mode:
    if not should_silent:
        if jh.is_live():
            _notify_submission(order)

        if (order.is_active or order.is_queued):
            txt: str = f'{"QUEUED" if order.is_queued else "SUBMITTED"} order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
            if order.price:
                txt += f', ${jh.format_price(order.price)}'
            # Always log to in-memory store for backtest results
            if jh.is_backtesting():
                store.logs.add(txt, 'order')
            if jh.is_debuggable('order_submission'):
                logger.info(txt)
    
    # If it's an order to close pre-existing positions, we don't want to include it in calculations.
    if should_store:
        e = store.exchanges.get_exchange(order.exchange)
        e.on_order_submission(order)

        store.orders.add_order(order)

        # if it's paper trading or backtesting (basicly not live trading), we add the order to the to_execute list to later simulate the execution.
        if not jh.is_livetrading() and order.type == order_types.MARKET:
            store.orders.to_execute.append(order)
        
        # if it's live/paper trading, we store the order in the database.
        if jh.is_live():
            order_repository.store_or_update(order)
    
    return order


def execute_order(order: Order, silent: bool = False) -> None:
    if order.is_canceled or order.is_executed:
        return
    
    order.executed_at = jh.now_to_timestamp()
    order.status = order_statuses.EXECUTED

    # Set filled_qty if not already set (e.g. by the live driver before calling execute_order)
    if not order.filled_qty:
        order.filled_qty = order.qty

    # Set order fee if not already set
    if order.fee is None:
        fee_rate = jh.get_config(f'env.exchanges.{order.exchange}.fee')
        notional = abs(order.filled_qty or order.qty) * order.price
        order.fee = fee_rate * notional

    if not silent:
        txt = f'EXECUTED order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
        if order.price:
            txt += f', ${jh.format_price(order.price)}'

        # Always log to in-memory store for backtest results
        if jh.is_backtesting():
            store.logs.add(txt, 'order')
        if jh.is_debuggable('order_execution'):
            logger.info(txt)

        if jh.is_live():
            try:
                if config.get('env', {}).get('notifications', {}).get('events', {}).get('executed_orders', False):
                    notify(txt)
            except (KeyError, TypeError, AttributeError):
                pass

    # In CFD mode, trade records are managed per-ticket by record_ticket_close(),
    # so skip the normal single-trade tracking for non-reduce_only orders.
    p = store.positions.get_position(order.exchange, order.symbol)
    if not (p and p.is_cfd_mode and not order.reduce_only):
        closed_trade_service.add_executed_order(order)

    e = store.exchanges.get_exchange(order.exchange)

    # Apply spread and slippage for forex/CFD exchanges (only when cost model is enabled)
    cost_model_enabled = config.get('app', {}).get('cost_model', True)
    if isinstance(e, CFDExchange) and not jh.is_livetrading():
        # Remove from pending order tracking BEFORE price changes
        e.on_order_execution(order)

        if cost_model_enabled:
            # Spread: shift entry fill price against the trader.
            # In real forex, spread is the bid-ask gap embedded in fill prices.
            # Entry orders cross the spread; exit orders (TP/SL) fill at their
            # trigger price and the PnL naturally captures the spread cost.
            p = store.positions.get_position(order.exchange, order.symbol)
            if p and p.is_cfd_mode:
                # In CFD mode, all non-reduce_only orders are entries (new tickets)
                is_entry = not order.reduce_only
            else:
                is_entry = (p is None or p.is_close or
                            (p.is_open and not order.reduce_only and p.qty * order.qty > 0))
            if is_entry:
                spread = e.get_spread(order.symbol)
                if spread > 0:
                    if order.side == 'buy':
                        order.price += spread
                    else:
                        order.price -= spread
                    e._total_spread_cost += spread * abs(order.filled_qty or order.qty)
                    logger.info(
                        f'Applied spread of {round(spread, 6)} to {order.symbol} {order.side} entry. '
                        f'Adjusted price: {order.price}'
                    )

            # Apply slippage: shift execution price against the trader
            slippage = e.get_slippage(order.symbol)
            if slippage > 0:
                if order.side == 'buy':
                    order.price += slippage
                else:
                    order.price -= slippage
                logger.info(
                    f'Applied slippage of {round(slippage, 6)} to {order.symbol} {order.side} order. '
                    f'Adjusted price: {order.price}'
                )
    else:
        e.on_order_execution(order)
    
    p = store.positions.get_position(order.exchange, order.symbol)
    if p:
        position_service.on_executed_order(p, order)


def execute_order_partially(order: Order, silent: bool = False) -> None:
    order.executed_at = jh.now_to_timestamp()
    order.status = order_statuses.PARTIALLY_FILLED
    
    # set order fee for non-live modes if not already set. In live trading, the fee is fetched by the exchange.
    if not jh.is_livetrading() and order.fee is None:
        fee_rate = jh.get_config(f'env.exchanges.{order.exchange}.fee')
        notional = abs(order.filled_qty or order.qty) * order.price
        order.fee = fee_rate * notional
    
    if not silent:
        txt = f"PARTIALLY FILLED: {order.symbol}, {order.type}, {order.side}, filled qty: {order.filled_qty}, remaining qty: {order.remaining_qty}, price: {jh.format_price(order.price)}"
        
        if jh.is_debuggable('order_execution'):
            logger.info(txt)
        
        if jh.is_live():
            try:
                if config.get('env', {}).get('notifications', {}).get('events', {}).get('executed_orders', False):
                    notify(txt)
            except (KeyError, TypeError, AttributeError):
                pass
    
    closed_trade_service.add_executed_order(order)
    
    p = store.positions.get_position(order.exchange, order.symbol)
    
    if p:
        position_service.on_executed_order(p, order)


def execute_simulated_market_orders() -> None:
    if not store.orders.to_execute:
        return

    for o in store.orders.to_execute:
        execute_order(o)

    store.orders.to_execute = []


def cancel_order(order: Order, silent: bool = False, source: str = '') -> None:
    if order.is_canceled or order.is_executed:
        return
    
    if source == 'stream' and order.is_queued:
        return
    
    order.canceled_at = jh.now_to_timestamp()
    order.status = order_statuses.CANCELED
    
    if not silent:
        txt = f'CANCELED order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
        if order.price:
            txt += f', ${jh.format_price(order.price)}'
        if jh.is_debuggable('order_cancellation'):
            logger.info(txt)
        if jh.is_live():
            try:
                if config.get('env', {}).get('notifications', {}).get('events', {}).get('cancelled_orders', False):
                    notify(txt)
            except (KeyError, TypeError, AttributeError):
                pass
    
    e = store.exchanges.get_exchange(order.exchange)
    e.on_order_cancellation(order)


def queue_order(order: Order) -> None:
    order.status = order_statuses.QUEUED
    order.canceled_at = None
    if jh.is_debuggable('order_submission'):
        txt = f'QUEUED order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
        if order.price:
            txt += f', ${jh.format_price(order.price)}'
        logger.info(txt)
    _notify_submission(order)


def resubmit_order(order: Order) -> None:
    if not order.is_queued:
        raise Exception(f'Cannot resubmit an order that is not queued. Current status: {order.status}')
    
    order.id = jh.generate_unique_id()
    order.status = order_statuses.ACTIVE
    order.canceled_at = None
    if jh.is_debuggable('order_submission'):
        txt: str = f'SUBMITTED order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
        if order.price:
            txt += f', ${jh.format_price(order.price)}'
        logger.info(txt)
    _notify_submission(order)


def _notify_submission(order: Order) -> None:
    try:
        if not config.get('env', {}).get('notifications', {}).get('events', {}).get('submitted_orders', False):
            return
    except (KeyError, TypeError, AttributeError):
        return

    if order.is_active or order.is_queued:
        txt = f'{"QUEUED" if order.is_queued else "SUBMITTED"} order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
        if order.price:
            txt += f', ${jh.format_price(order.price)}'
        notify(txt)


def initialize_orders_state() -> None:
    for exchange in config['app']['trading_exchanges']:
        for symbol in config['app']['trading_symbols']:
            key = f'{exchange}-{symbol}'
            store.orders.storage[key] = []
            store.orders.active_storage[key] = []


def get_entry_orders(exchange: str, symbol: str) -> List[Order]:
    p = store.positions.get_position(exchange, symbol)
    # return all orders if position is not opened yet
    if p.is_close:
        return store.orders.get_orders(exchange, symbol).copy()

    # In CFD hedge mode, net qty can be ~0 while tickets are open (type="close")
    # Return all active non-canceled orders since both sides are valid entries
    if p.type == 'close':
        return [o for o in store.orders.get_active_orders(exchange, symbol) if not o.is_canceled]

    all_orders = store.orders.get_active_orders(exchange, symbol)
    p_side = jh.type_to_side(p.type)
    entry_orders = [o for o in all_orders if (o.side == p_side and not o.is_canceled)]

    return entry_orders


def get_exit_orders(exchange: str, symbol: str) -> List[Order]:
    """
    excludes cancel orders but includes executed orders
    """
    all_orders = store.orders.get_orders(exchange, symbol)
    # return empty if no orders
    if len(all_orders) == 0:
        return []
    # return empty if position is not opened yet
    p = store.positions.get_position(exchange, symbol)
    if p.is_close:
        return []
    else:
        exit_orders = [o for o in all_orders if o.side != jh.type_to_side(p.type)]

    # exclude cancelled orders
    exit_orders = [o for o in exit_orders if not o.is_canceled]

    return exit_orders


def get_active_exit_orders(exchange: str, symbol: str) -> List[Order]:
    """
    excludes cancel orders but includes executed orders
    """
    all_orders = store.orders.get_active_orders(exchange, symbol)
    # return empty if no orders
    if len(all_orders) == 0:
        return []
    # return empty if position is not opened yet
    p = store.positions.get_position(exchange, symbol)
    if p.is_close:
        return []
    else:
        exit_orders = [o for o in all_orders if o.side != jh.type_to_side(p.type)]

    # exclude cancelled orders
    exit_orders = [o for o in exit_orders if not o.is_canceled]

    return exit_orders


def update_active_orders(exchange: str, symbol: str):
    key = f'{exchange}-{symbol}'
    active_orders = [
        order
        for order in store.orders.get_active_orders(exchange, symbol)
        if not order.is_canceled and not order.is_executed
    ]
    store.orders.active_storage[key] = active_orders
