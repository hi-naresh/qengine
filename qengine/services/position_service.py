from qengine.config import config
from qengine.models import Position
from qengine.store import store
import qengine.helpers as jh
from qengine.exceptions import EmptyPosition, OpenPositionError
from qengine.services import closed_trade_service
from qengine.enums import trade_types
from qengine.utils import sum_floats, subtract_floats
from qengine.enums import order_types
from qengine.models import Order
from qengine.services import logger


def initialize_positions_state() -> None:
    for exchange in config['app']['trading_exchanges']:
        for symbol in config['app']['trading_symbols']:
            key: str = f'{exchange}-{symbol}'
            store.positions.storage[key] = create_position(exchange, symbol)


def create_position(exchange_name: str, symbol: str, attributes: dict = None) -> Position:
    p = Position(attributes)
    if p.id is None:
        p.id = jh.generate_unique_id()
    p.exchange_name = exchange_name
    p.exchange = store.exchanges.get_exchange(exchange_name)
    p.symbol = symbol
    return p


def _mutating_close(position: Position, close_price: float) -> None:
    if position.is_close and position._can_mutate_qty:
        raise EmptyPosition('The position is already closed.')

    position.exit_price = close_price
    position.closed_at = jh.now_to_timestamp()

    if position.exchange and position.exchange.type in ('futures', 'cfd'):
        # just to prevent confusion
        close_qty = abs(position.qty)
        estimated_profit = jh.estimate_PNL(
            close_qty, position.entry_price,
            close_price, position.type
        )
        position.exchange.add_realized_pnl(estimated_profit)
        position.exchange.temp_reduced_amount[jh.base_asset(position.symbol)] += abs(close_qty * close_price)

    if position._can_mutate_qty:
        _update_qty(position, 0, operation='set')

    # reset entry_price
    position.entry_price = None

    _close(position)


def _close(position: Position):
    closed_trade_service.close_trade(position)


def _mutating_reduce(position: Position, qty: float, price: float) -> None:
    if not position._can_mutate_qty:
        return

    if position.is_open is False:
        raise EmptyPosition('The position is closed.')

    # just to prevent confusion
    qty = abs(qty)

    estimated_profit = jh.estimate_PNL(qty, position.entry_price, price, position.type)

    if position.exchange and position.exchange.type in ('futures', 'cfd'):
        position.exchange.add_realized_pnl(estimated_profit)
        position.exchange.temp_reduced_amount[jh.base_asset(position.symbol)] += abs(qty * price)

    if position.type == trade_types.LONG:
        _update_qty(position, qty, operation='subtract')
    elif position.type == trade_types.SHORT:
        _update_qty(position, qty, operation='add')


def _mutating_increase(position: Position, qty: float, price: float) -> None:
    if not position.is_open:
        raise OpenPositionError('position must be already open in order to increase its size')

    qty = abs(qty)

    position.entry_price = jh.estimate_average_price(
        qty, price, position.qty,
        position.entry_price
    )

    if position._can_mutate_qty:
        if position.type == trade_types.LONG:
            _update_qty(position, qty, operation='add')
        elif position.type == trade_types.SHORT:
            _update_qty(position, qty, operation='subtract')


def _mutating_open(position: Position, qty: float, price: float) -> None:
    if position.is_open and position._can_mutate_qty:
        raise OpenPositionError('an already open position cannot be opened')

    position.entry_price = price
    position.exit_price = None

    if position._can_mutate_qty:
        _update_qty(position, qty, operation='set')

    position.opened_at = jh.now_to_timestamp()

    _open(position)


def _update_qty(position: Position, qty: float, operation='set'):
    position.previous_qty = position.qty

    if position.exchange_type == 'spot':
        if operation == 'set':
            position.qty = qty * (1 - position.exchange.fee_rate)
        elif operation == 'add':
            position.qty = sum_floats(position.qty, qty * (1 - position.exchange.fee_rate))
        elif operation == 'subtract':
            position.qty = subtract_floats(position.qty, qty)

    elif position.exchange_type in ('futures', 'cfd'):
        if operation == 'set':
            position.qty = qty
        elif operation == 'add':
            position.qty = sum_floats(position.qty, qty)
        elif operation == 'subtract':
            position.qty = subtract_floats(position.qty, qty)
    else:
        raise NotImplementedError(f'exchange type not implemented: {position.exchange_type}')


def _handle_cfd_order(position: Position, order: Order) -> None:
    """Handle order execution in CFD mode (independent tickets)."""
    qty = order.qty
    price = order.price
    ticket_type = 'long' if qty > 0 else 'short'

    if order.reduce_only:
        # reduce_only in CFD mode: close specific ticket or all tickets
        if hasattr(order, 'ticket_id') and order.ticket_id:
            result = position.close_ticket(order.ticket_id, price)
            if result:
                ticket = result['ticket']
                pnl = result['pnl']
                if position.exchange and position.exchange.type in ('cfd',):
                    position.exchange.add_realized_pnl(pnl)
                closed_trade_service.record_ticket_close(position, ticket, price, pnl)
                logger.info(f'CFD: closed ticket {ticket.id[:8]} at {price}, PnL: {round(pnl, 2)}')
        else:
            # No ticket_id: close all tickets (forced close, e.g. end of backtest)
            results = position.close_all_tickets(price)
            total_pnl = sum(r['pnl'] for r in results)
            if position.exchange and position.exchange.type in ('cfd',):
                position.exchange.add_realized_pnl(total_pnl)
            for r in results:
                closed_trade_service.record_ticket_close(position, r['ticket'], price, r['pnl'])
            logger.info(f'CFD: closed all {len(results)} tickets at {price}, total PnL: {round(total_pnl, 2)}')
    else:
        # Non-reduce_only: open a new ticket
        ticket = position.open_ticket(ticket_type, qty, price, jh.now_to_timestamp())
        if position.ticket_count == 1:
            position.opened_at = jh.now_to_timestamp()
        # Link the order to its ticket
        order.ticket_id = ticket.id
        # Store OANDA trade ID on ticket (for per-trade TP/SL management)
        if order.vars.get('trade_id'):
            ticket.exchange_trade_id = order.vars['trade_id']
        logger.info(
            f'CFD: opened {ticket_type} ticket {ticket.id[:8]}, qty: {abs(qty):.2f} at {price} '
            f'(ticket #{position.ticket_count}, net qty: {position.qty:.2f}, '
            f'trade_id: {ticket.exchange_trade_id})'
        )


def _open(position: Position, p_orders: list = None):
    closed_trade_service.open_trade(position, p_orders)


def on_executed_order(position: Position, order: Order) -> None:
    # futures (live)
    if jh.is_livetrading() and position.exchange_type == 'futures':
        if order.is_partially_filled:
            before_qty = position.qty - order.filled_qty
        else:
            before_qty = position.qty - order.qty
        after_qty = position.qty
        if before_qty != 0 and after_qty == 0:
            _close(position)
    # spot (live)
    elif jh.is_livetrading() and position.exchange_type == 'spot':
        before_qty = position.previous_qty
        after_qty = position.qty
        qty = order.qty
        price = order.price
        closing_position = before_qty > position._min_qty > after_qty
        if closing_position:
            _mutating_close(position, price)
        opening_position = before_qty < position._min_qty < after_qty
        if opening_position:
            _mutating_open(position, qty, price)
        increasing_position = after_qty > before_qty > position._min_qty
        if increasing_position:
            _mutating_increase(position, qty, price)
        reducing_position = position._min_qty < after_qty < before_qty
        if reducing_position:
            _mutating_reduce(position, qty, price)
    else:  # backtest (both futures and spot)
        qty = order.qty
        price = order.price

        # For CFD, spread is already embedded in entry fill price
        # (applied in order_service), so no separate fee charge needed.
        if position.exchange and position.exchange.type == 'futures':
            position.exchange.charge_fee(qty * price)

        # ── CFD mode: independent tickets ──
        if position.is_cfd_mode:
            _handle_cfd_order(position, order)
        # ── Standard netting mode ──
        # order opens position
        elif position.qty == 0:
            change_balance = order.type == order_types.MARKET
            _mutating_open(position, qty, price)
        # order closes position
        elif (sum_floats(position.qty, qty)) == 0:
            _mutating_close(position, price)
        # order increases the size of the position
        elif position.qty * qty > 0:
            if order.reduce_only:
                logger.info('Did not increase position because order is a reduce_only order')
            else:
                _mutating_increase(position, qty, price)
        # order reduces the size of the position
        elif position.qty * qty < 0:
            if abs(qty) > abs(position.qty):
                if order.reduce_only:
                    logger.info(
                        f'Executed order is bigger than the current position size but it is a reduce_only order so it just closes it. Order QTY: {qty}, Position QTY: {position.qty}')
                    _mutating_close(position, price)
                else:
                    logger.info(
                        f'Executed order is big enough to not close, but flip the position type. Order QTY: {qty}, Position QTY: {position.qty}')
                    diff_qty = sum_floats(position.qty, qty)
                    _mutating_close(position, price)
                    _mutating_open(position, diff_qty, price)
            else:
                _mutating_reduce(position, qty, price)

    if position.strategy:
        position.strategy._on_updated_position(order)


def update_from_stream(position: Position, data: dict, is_initial: bool, open_trade: dict = None, p_orders: list = None) -> None:
    """
    Used for updating the position from the WS stream (only for live trading)
    """
    before_qty = abs(position.qty)
    after_qty = abs(data['qty'])

    if position.exchange_type in ('futures', 'cfd'):
        position.entry_price = data['entry_price']
        position._liquidation_price = data.get('liquidation_price')
    else:  # spot
        if after_qty > position._min_qty and position.entry_price is None:
            position.entry_price = position.current_price

    if position.qty != data['qty']:
        position.previous_qty = position.qty
        position.qty = data['qty']

    opening_position = before_qty <= position._min_qty < after_qty
    closing_position = before_qty > position._min_qty >= after_qty
    if opening_position:
        position.opened_at = jh.now_to_timestamp()
        if not open_trade:
            _open(position, p_orders)
    elif closing_position:
        position.closed_at = jh.now_to_timestamp()
