from typing import Union, List, Dict
import numpy as np
import qengine.helpers as jh


class CFDTicket:
    """An independent sub-position (ticket) within a CFD position.
    Like MT4/MT5 tickets — each has its own entry, qty, direction, and PnL."""

    __slots__ = ('id', 'type', 'qty', 'entry_price', 'opened_at', 'exchange_trade_id')

    def __init__(self, ticket_type: str, qty: float, entry_price: float, opened_at: int):
        self.id = jh.generate_unique_id()
        self.type = ticket_type  # 'long' or 'short'
        self.qty = abs(qty)
        self.entry_price = entry_price
        self.opened_at = opened_at
        self.exchange_trade_id = None  # OANDA trade ID for per-trade TP/SL management

    def pnl(self, price: float) -> float:
        diff = price - self.entry_price
        if self.type == 'short':
            diff = -diff
        return self.qty * diff

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'type': self.type,
            'qty': self.qty,
            'entry_price': self.entry_price,
            'opened_at': self.opened_at,
            'exchange_trade_id': self.exchange_trade_id,
        }


class Position:
    id: str = None
    entry_price: float = None
    exit_price: float = None
    current_price: float = None
    qty: float = 0
    previous_qty: float = 0
    opened_at: int = None
    closed_at: int = None
    _mark_price: float = None
    _funding_rate: float = None
    _next_funding_timestamp: int = None
    _liquidation_price: float = None
    exchange_name: str = None
    exchange = None
    symbol: str = None
    strategy = None

    # CFD mode: independent tickets on same symbol
    _tickets: List[CFDTicket] = None

    def __init__(self, attributes: dict = None) -> None:
        if attributes is None:
            attributes = {}

        self._tickets = []

        for a in attributes:
            setattr(self, a, attributes[a])

    @property
    def is_cfd_mode(self) -> bool:
        """CFD mode is determined by exchange type, not a strategy flag."""
        if self.exchange is None:
            return False
        return self.exchange.type == 'cfd'

    # ── CFD Ticket Management ────────────────────────────────────

    def open_ticket(self, ticket_type: str, qty: float, entry_price: float, opened_at: int) -> CFDTicket:
        """Open a new independent ticket in CFD mode."""
        ticket = CFDTicket(ticket_type, qty, entry_price, opened_at)
        self._tickets.append(ticket)
        self._sync_from_tickets()
        return ticket

    def close_ticket(self, ticket_id: str, exit_price: float) -> dict:
        """Close a specific ticket. Returns {ticket, pnl}."""
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            return None
        pnl = ticket.pnl(exit_price)
        self._tickets = [t for t in self._tickets if t.id != ticket_id]
        self._sync_from_tickets()
        if not self._tickets:
            self.exit_price = exit_price
            self.closed_at = jh.now_to_timestamp()
        return {'ticket': ticket, 'pnl': pnl}

    def close_all_tickets(self, exit_price: float) -> List[dict]:
        """Close all tickets at exit_price. Returns list of {ticket, pnl}."""
        results = []
        for ticket in self._tickets:
            pnl = ticket.pnl(exit_price)
            results.append({'ticket': ticket, 'pnl': pnl})
        self._tickets = []
        self.previous_qty = self.qty
        self.qty = 0
        self.entry_price = None
        self.exit_price = exit_price
        self.closed_at = jh.now_to_timestamp()
        return results

    def get_ticket(self, ticket_id: str) -> Union[CFDTicket, None]:
        for t in self._tickets:
            if t.id == ticket_id:
                return t
        return None

    @property
    def tickets(self) -> List[CFDTicket]:
        return list(self._tickets)

    @property
    def ticket_count(self) -> int:
        return len(self._tickets)

    def _sync_from_tickets(self):
        """Recalculate net qty and entry_price from tickets."""
        if not self._tickets:
            self.previous_qty = self.qty
            self.qty = 0
            return

        net = 0.0
        for t in self._tickets:
            if t.type == 'long':
                net += t.qty
            else:
                net -= t.qty

        self.previous_qty = self.qty
        self.qty = net

        # Set entry_price to weighted average of dominant direction (for display)
        dominant = 'long' if net >= 0 else 'short'
        dom_tickets = [t for t in self._tickets if t.type == dominant]
        if dom_tickets:
            total_qty = sum(t.qty for t in dom_tickets)
            if total_qty > 0:
                self.entry_price = sum(t.qty * t.entry_price for t in dom_tickets) / total_qty

    @property
    def gross_exposure(self) -> float:
        """Sum of all tickets' absolute qty (for margin in CFD mode)."""
        if not self._tickets:
            return abs(self.qty)
        return sum(t.qty for t in self._tickets)

    # ── Standard Properties ──────────────────────────────────────

    @property
    def mark_price(self) -> float:
        if not jh.is_live():
            return self.current_price
        if self.exchange_type == 'spot':
            return self.current_price
        return self._mark_price

    @property
    def funding_rate(self) -> float:
        if not jh.is_live():
            return 0
        if self.exchange_type == 'spot':
            raise ValueError('funding rate is not applicable to spot trading')
        return self._funding_rate

    @property
    def next_funding_timestamp(self) -> Union[int, None]:
        if not jh.is_live():
            return None
        if self.exchange_type == 'spot':
            raise ValueError('funding rate is not applicable to spot trading')
        return self._next_funding_timestamp

    @property
    def value(self) -> float:
        if self.is_close:
            return 0
        if self.current_price is None:
            return None
        return abs(self.current_price * self.qty)

    @property
    def type(self) -> str:
        if self.is_long:
            return 'long'
        elif self.is_short:
            return 'short'
        return 'close'

    @property
    def pnl_percentage(self) -> float:
        return self.roi

    @property
    def roi(self) -> float:
        if self.pnl == 0:
            return 0
        return self.pnl / self.total_cost * 100

    @property
    def total_cost(self) -> float:
        if self.is_close:
            return np.nan
        base_cost = self.entry_price * abs(self.qty)
        if self.strategy:
            return base_cost / self.leverage
        return base_cost

    @property
    def leverage(self) -> Union[int, np.float64]:
        if self.exchange_type == 'spot':
            return 1
        if self.exchange_type in ('cfd',):
            return self.exchange.default_leverage
        if self.strategy:
            return self.strategy.leverage
        else:
            return np.nan

    @property
    def exchange_type(self) -> str:
        if self.exchange is None:
            return 'futures'
        return self.exchange.type

    @property
    def entry_margin(self) -> float:
        return self.total_cost

    @property
    def pnl(self) -> float:
        # CFD mode: sum per-ticket PnL
        if self.is_cfd_mode and self._tickets:
            if self.current_price is None:
                return 0
            return sum(t.pnl(self.current_price) for t in self._tickets)

        if abs(self.qty) < self._min_qty:
            return 0
        if self.entry_price is None:
            return 0
        if self.value is None:
            return 0
        diff = self.value - abs(self.entry_price * self.qty)
        return -diff if self.type == 'short' else diff

    @property
    def is_open(self) -> bool:
        if self.is_cfd_mode and self._tickets:
            return True
        return self.type in ['long', 'short']

    @property
    def is_close(self) -> bool:
        if self.is_cfd_mode:
            return len(self._tickets) == 0
        return self.type == 'close'

    @property
    def is_long(self) -> bool:
        return self.qty > self._min_qty

    @property
    def is_short(self) -> bool:
        return self.qty < -abs(self._min_qty)

    @property
    def mode(self) -> str:
        if self.exchange.type == 'spot':
            return 'spot'
        elif self.exchange.type == 'cfd':
            return 'cfd'
        else:
            return self.exchange.futures_leverage_mode

    @property
    def pip_pnl(self) -> float:
        if self.is_close:
            return 0
        pip_size = jh.get_pip_size(self.symbol)
        if pip_size == 0:
            return 0
        diff = self.current_price - self.entry_price
        if self.type == 'short':
            diff = -diff
        return diff / pip_size

    @property
    def margin_used(self) -> float:
        if self.is_close:
            return 0
        from qengine.core.instruments import instrument_registry
        inst = instrument_registry.get(self.symbol)
        # In CFD mode, use gross exposure (sum of all tickets) for margin
        if self.is_cfd_mode and self._tickets:
            gross_notional = self.gross_exposure * (self.current_price or self.entry_price or 0)
            if inst and inst.margin_rate > 0:
                return gross_notional * inst.margin_rate
            return gross_notional / self.leverage if self.leverage else gross_notional
        # Standard mode
        if inst and inst.margin_rate > 0:
            notional = abs(self.qty) * self.entry_price
            return notional * inst.margin_rate
        return self.total_cost

    @property
    def liquidation_price(self) -> Union[float, np.float64]:
        if self.is_close:
            return np.nan
        if jh.is_livetrading():
            return self._liquidation_price
        if self.mode in ['cross', 'spot', 'cfd']:
            return np.nan
        elif self.mode == 'isolated':
            if self.type == 'long':
                return self.entry_price * (1 - self._initial_margin_rate + 0.004)
            elif self.type == 'short':
                return self.entry_price * (1 + self._initial_margin_rate - 0.004)
            else:
                return np.nan
        else:
            return np.nan

    @property
    def _initial_margin_rate(self) -> float:
        return 1 / self.leverage

    @property
    def bankruptcy_price(self) -> Union[float, np.float64]:
        if self.type == 'long':
            return self.entry_price * (1 - self._initial_margin_rate)
        elif self.type == 'short':
            return self.entry_price * (1 + self._initial_margin_rate)
        else:
            return np.nan

    @property
    def to_dict(self):
        d = {
            'entry_price': self.entry_price,
            'qty': self.qty,
            'current_price': self.current_price,
            'value': self.value,
            'type': self.type,
            'exchange': self.exchange_name,
            'pnl': self.pnl,
            'pnl_percentage': self.pnl_percentage,
            'leverage': self.leverage,
            'liquidation_price': self.liquidation_price,
            'bankruptcy_price': self.bankruptcy_price,
            'mode': self.mode,
        }
        if self.exchange_type in ('cfd',):
            d['pip_pnl'] = self.pip_pnl
            d['margin_used'] = self.margin_used
            d['tickets'] = [t.to_dict() for t in self._tickets]
        return d

    @property
    def _min_notional_size(self) -> float:
        if not (jh.is_livetrading() and self.exchange_type == 'spot'):
            return 0
        return self.exchange.vars['precisions'][self.symbol]['min_notional_size']

    @property
    def _min_qty(self) -> float:
        if not (jh.is_livetrading() and self.exchange_type == 'spot'):
            return 0
        if 'min_qty' in self.exchange.vars['precisions'][self.symbol]:
            return self.exchange.vars['precisions'][self.symbol]['min_qty']
        if self._min_notional_size and self.current_price:
            return self._min_notional_size / self.current_price
        else:
            return 0

    @property
    def _can_mutate_qty(self):
        return not (self.exchange_type == 'spot' and jh.is_livetrading())
