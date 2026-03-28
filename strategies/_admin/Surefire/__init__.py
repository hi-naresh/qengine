"""
Surefire Forex Hedging Strategy — CFD Mode (Broker-Side Orders)
================================================================
A recovery/martingale hedging strategy using CFD tickets (independent sub-positions).
All tickets stay open simultaneously. When TP price is reached, ALL tickets close together.
Same-direction tickets WIN (larger qty), opposite-direction tickets LOSE (smaller qty).
Net is positive due to martingale sizing.

Order execution: TP and hedge triggers use actual broker orders (not price polling).
  - TP: per-trade takeProfit/stopLoss on OANDA (fills at exact price)
  - Hedge: STOP order on OANDA (triggers at exact price)
  This ensures sub-second execution at the precise pip levels.

How it works:
  Level 0: Open initial ticket in `direction` with `initial_size`.
           TP at +tp_distance, hedge trigger at -hedge_distance.
  Level 1: Hedge trigger hit -> STOP order fills opposite-direction ticket, size = initial * multiplier.
           New TP/hedge set from hedge trigger price.
  Level 2+: Continue adding tickets with increasing size until TP or max_levels.

When TP is hit, OANDA auto-closes all trades. Strategy detects flat position and resets.

Pip reference (for 5-decimal pairs like EUR-USD where price ~ 1.50221):
  1 pip = 0.0001 (4th decimal place)

Parameters (all configurable via hyperparameters / optimization):
  direction      : 'long' or 'short' or 'random'
  initial_size   : % of capital as margin for initial position
  sizing_operator: multiplier / sqrt / linear / fibonacci
  sizing_factor  : base value m (multiplier and sqrt only)
  tp_distance    : take-profit distance in pips
  hedge_distance : hedge trigger distance in pips
  max_levels     : safety cap on hedge levels
"""
import math
import random

import qengine.helpers as jh
from qengine.strategies import Strategy
from qengine.services import logger

# Pre-computed Fibonacci sequence for level sizing (index = hedge level)
_FIB = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]


class Surefire(Strategy):

    def __init__(self):
        super().__init__()

        # Allow entries while position is open (CFD mode)
        self.hedge_mode = True

        # Hedge cycle state
        self.vars['level'] = 0
        self.vars['session_dir'] = None
        self.vars['cycle_active'] = False

        # Per-level tracking: [{dir, qty, entry, tp, hedge, trade_id}]
        self.vars['legs'] = []
        self.vars['tp_price'] = None
        self.vars['hedge_trigger_price'] = None

        # Broker order tracking (exchange order IDs)
        self.vars['hedge_order_id'] = None  # OANDA order ID for hedge STOP

        # Session tracking
        self.vars['session_number'] = 0
        self.vars['order_in_session'] = 0
        self.vars['sessions'] = []
        self.vars['current_session_pnl'] = 0

        # Cooldown: don't re-enter on the same candle a session closed
        self.vars['cooldown_until'] = 0

        # Track expected ticket count to detect hedge fills
        self.vars['expected_tickets'] = 0

        # Whether broker-side TP/SL + hedge STOP were confirmed placed
        self.vars['broker_orders_set'] = False

    # -- Configurable Parameters ----------------------------------------

    def hyperparameters(self):
        return [
            {'name': 'direction',      'type': 'categorical', 'options': ['long', 'short', 'random'], 'default': 'long',
             'description': 'Initial trade direction (random picks per session)'},
            {'name': 'initial_size',   'type': float, 'min': 0.1,  'max': 50.0,    'default': 1.0,
             'description': 'Size: % of equity as margin (OANDA) or contracts (IG)'},
            {'name': 'sizing_operator', 'type': 'categorical', 'options': ['multiplier', 'sqrt', 'linear', 'fibonacci'],
             'default': 'multiplier', 'description': 'Sizing curve: multiplier=m^n, sqrt=sqrt(m)^n, linear=1+n, fibonacci=fib(n)'},
            {'name': 'sizing_factor',  'type': float, 'min': 1.1,  'max': 5.0,     'default': 2.0,
             'description': 'Base value m (used by multiplier and sqrt sizing operators)'},
            {'name': 'tp_distance',    'type': float, 'min': 3,    'max': 200,     'default': 20,
             'description': 'Take-profit distance in pips (1 pip = 0.0001 for EUR-USD)'},
            {'name': 'hedge_distance', 'type': float, 'min': 1,    'max': 200,     'default': 10,
             'description': 'Hedge trigger distance in pips'},
            {'name': 'max_levels',     'type': int,   'min': 1,    'max': 10,      'default': 6,
             'description': 'Max hedge levels before stopping the session'},
        ]

    # -- Helpers --------------------------------------------------------

    @property
    def direction(self) -> str:
        return self.hp.get('direction', 'long')

    @property
    def initial_size(self) -> float:
        return self.hp.get('initial_size', 1.0)

    @property
    def sizing_operator(self) -> str:
        return self.hp.get('sizing_operator', 'multiplier')

    @property
    def sizing_factor(self) -> float:
        return self.hp.get('sizing_factor', 2.0)

    @property
    def tp_distance_pips(self) -> float:
        return self.hp.get('tp_distance', 20)

    @property
    def hedge_distance_pips(self) -> float:
        return self.hp.get('hedge_distance', 10)

    @property
    def max_levels(self) -> int:
        return self.hp.get('max_levels', 6)

    def _base_qty(self) -> float:
        """Calculate base qty for level 0.

        For OANDA (units-based): initial_size = % of capital as margin,
          qty = balance * pct/100 * leverage / price  (returns currency units).
        For IG/contract-based brokers: initial_size used directly as contract size
          (IG size=1 means 1 contract = lotSize * pip_value).
        """
        exchange_name = self.exchange.lower() if hasattr(self, 'exchange') else ''
        if 'ig' in exchange_name:
            # IG uses contract-based sizing — initial_size IS the number of contracts
            return self.initial_size
        # OANDA and others: % of equity as margin
        margin = self.balance * self.initial_size / 100
        return margin * self.leverage / self.price

    def _multiplier_factor(self, level: int) -> float:
        op = self.sizing_operator
        m = self.sizing_factor
        if op == 'sqrt':
            return math.sqrt(m) ** level
        elif op == 'linear':
            return 1 + level
        elif op == 'fibonacci':
            return _FIB[level] if level < len(_FIB) else _FIB[-1]
        else:  # 'multiplier'
            return m ** level

    def _size_for_level(self, level: int) -> float:
        base = self.vars.get('_cycle_base_qty') or self._base_qty()
        return base * self._multiplier_factor(level)

    def _get_driver(self):
        """Get the live broker driver (OANDA, IG, etc.)."""
        if not jh.is_live():
            return None
        from qengine.services.api import api
        return api.drivers.get(self.exchange)

    # -- Session tracking -----------------------------------------------

    def _start_new_session(self):
        self.vars['session_number'] += 1
        self.vars['order_in_session'] = 0
        self.vars['current_session_pnl'] = 0
        self.vars['legs'] = []
        self.vars['hedge_order_id'] = None
        self.vars['expected_tickets'] = 0
        self.vars['broker_orders_set'] = False
        # Cache base qty at cycle start so all levels use consistent sizing
        self.vars['_cycle_base_qty'] = self._base_qty()
        if self.direction == 'random':
            self.vars['session_dir'] = random.choice(['long', 'short'])
        else:
            self.vars['session_dir'] = self.direction
        logger.info(
            f'[Surefire] ═══ SESSION {self.vars["session_number"]} START ═══ '
            f'dir={self.vars["session_dir"]}, price={self.price:.5f}, '
            f'balance={self.balance:.2f}, base_qty={self._base_qty():.0f}'
        )

    def _close_session(self, outcome: str):
        s = self.vars['session_number']
        legs_count = len(self.vars['legs'])
        pnl = round(self.vars['current_session_pnl'], 6)
        max_level = self.vars['level']
        self.vars['sessions'].append({
            'session': s,
            'legs': legs_count,
            'pnl': pnl,
            'outcome': outcome,
            'max_level': max_level,
        })
        logger.info(
            f'[Surefire] ═══ SESSION {s} END ═══ '
            f'outcome={outcome}, levels={max_level}, orders={legs_count}, '
            f'PnL={pnl:.4f}, balance={self.balance:.2f}'
        )

    def _reset_cycle(self, outcome: str):
        self._close_session(outcome)
        self.vars['cooldown_until'] = self.current_candle[0]
        self.vars['level'] = 0
        self.vars['session_dir'] = None
        self.vars['cycle_active'] = False
        self.vars['tp_price'] = None
        self.vars['hedge_trigger_price'] = None
        self.vars['legs'] = []
        self.vars['hedge_order_id'] = None
        self.vars['expected_tickets'] = 0
        self.vars['broker_orders_set'] = False

    # -- Broker Order Management ----------------------------------------

    def _setup_broker_orders(self, _depth=0):
        """Set TP/SL on all OANDA trades and submit hedge STOP order.

        Called after every new ticket opens (level 0 entry or hedge fill).
        Tracks TP/SL and hedge placement separately so a TP/SL retry
        doesn't cancel an already-placed hedge STOP.
        """
        if _depth > 5:
            logger.error('[Surefire] _setup_broker_orders recursion limit — stopping')
            return
        driver = self._get_driver()
        if not driver:
            logger.info('[Surefire] WARNING: _setup_broker_orders: no driver available')
            return

        tp_price = self.vars['tp_price']
        hedge_price = self.vars['hedge_trigger_price']
        last_dir = self.vars['legs'][-1]['dir'] if self.vars['legs'] else None

        if not last_dir or not tp_price or not hedge_price:
            logger.info(
                f'[Surefire] _setup_broker_orders: missing data — '
                f'last_dir={last_dir}, tp={tp_price}, hedge={hedge_price}'
            )
            return

        # Round prices to 5 decimal places (OANDA precision for EUR/USD etc.)
        tp_price = round(tp_price, 5)
        hedge_price = round(hedge_price, 5)

        tp_sl_ok = True

        # -- Set TP/SL on every open OANDA trade --
        tickets = self.position.tickets if self.position.tickets else []
        if not tickets:
            logger.info('[Surefire] _setup_broker_orders: no tickets to set TP/SL on')
            tp_sl_ok = False

        for ticket in tickets:
            trade_id = ticket.exchange_trade_id
            if not trade_id:
                logger.info(f'[Surefire] Ticket {ticket.id[:8]} has no exchange_trade_id, skipping TP/SL')
                tp_sl_ok = False
                continue

            try:
                if last_dir == 'long':
                    if ticket.type == 'long':
                        driver.set_trade_tp_sl(trade_id, take_profit=tp_price)
                    else:
                        driver.set_trade_tp_sl(trade_id, stop_loss=tp_price)
                else:
                    if ticket.type == 'short':
                        driver.set_trade_tp_sl(trade_id, take_profit=tp_price)
                    else:
                        driver.set_trade_tp_sl(trade_id, stop_loss=tp_price)
            except Exception as e:
                logger.error(f'[Surefire] Failed to set TP/SL on trade {trade_id}: {e}')
                tp_sl_ok = False

        # -- Submit hedge order (only if not already placed) --
        hedge_already_placed = bool(self.vars.get('hedge_order_id'))

        level = self.vars['level']
        if level + 1 >= self.max_levels:
            logger.info(f'[Surefire] At max level {level}, no hedge order needed')
            self.vars['broker_orders_set'] = tp_sl_ok
            if tp_sl_ok:
                self.vars['_broker_retry_count'] = 0
            return

        # If hedge STOP is already on OANDA, don't cancel and re-place it
        if hedge_already_placed:
            logger.info(
                f'[Surefire] Hedge STOP already placed (order {self.vars["hedge_order_id"]}), '
                f'skipping re-submission. tp_sl_ok={tp_sl_ok}'
            )
            self.vars['broker_orders_set'] = tp_sl_ok
            if tp_sl_ok:
                self.vars['_broker_retry_count'] = 0
            return

        next_level = level + 1
        next_dir = 'short' if last_dir == 'long' else 'long'
        next_size = self._size_for_level(next_level)
        side = 'buy' if next_dir == 'long' else 'sell'

        # Check if price has already breached the hedge level.
        # OANDA validates STOP SELL against bid, STOP BUY against ask.
        # self.price is mid — add spread buffer to avoid rejection.
        current_price = self.price
        spread_buffer = self.spread or self.pips_to_price(2)  # fallback 2 pips if spread unknown
        already_breached = False
        if next_dir == 'short' and current_price <= hedge_price + spread_buffer:
            already_breached = True
        elif next_dir == 'long' and current_price >= hedge_price - spread_buffer:
            already_breached = True

        if already_breached:
            # Price already at/past hedge — execute immediately as MARKET
            logger.info(
                f'[Surefire] S{self.vars["session_number"]}.L{level}: '
                f'Price {current_price:.5f} within spread of hedge {hedge_price:.5f} '
                f'(spread={spread_buffer:.5f}) — MARKET {side.upper()} {next_size:.0f}'
            )
            self._execute_hedge_market(driver, next_dir, next_level, next_size, side,
                                       hedge_price, current_price, _depth)
            return

        # Price hasn't reached hedge yet — submit STOP order on broker
        try:
            exchange_order_id = driver._submit_stop_order(
                self.symbol, next_size, hedge_price, side, reduce_only=False
            )

            self.vars['hedge_order_id'] = exchange_order_id

            from qengine.services import order_service
            from qengine.enums import order_types
            order = order_service.create_order({
                'id': jh.generate_unique_id(),
                'exchange_id': exchange_order_id,
                'symbol': self.symbol,
                'exchange': self.exchange,
                'side': side,
                'type': order_types.STOP,
                'reduce_only': False,
                'qty': jh.prepare_qty(next_size, side),
                'price': hedge_price,
            })
            order.vars['purpose'] = 'surefire_hedge'
            order.vars['session'] = self.vars['session_number']
            order.vars['level'] = next_level

            logger.info(
                f'[Surefire] S{self.vars["session_number"]}.L{level}: '
                f'TP/SL set on {len(tickets)} trades, hedge STOP {side.upper()} {next_size:.0f} @ {hedge_price:.5f} '
                f'(OANDA order {exchange_order_id}, price={current_price:.5f}, spread={spread_buffer:.5f})'
            )
            self.vars['broker_orders_set'] = tp_sl_ok
            if tp_sl_ok:
                self.vars['_broker_retry_count'] = 0
        except Exception as e:
            logger.error(f'[Surefire] STOP order failed ({e}) — falling back to MARKET')
            self._execute_hedge_market(driver, next_dir, next_level, next_size, side,
                                       hedge_price, current_price, _depth)

    def _execute_hedge_market(self, driver, next_dir, next_level, next_size, side,
                               hedge_price, current_price, _depth):
        """Execute hedge as MARKET order (used when STOP is invalid or rejected)."""
        try:
            result = driver._submit_market_order(
                self.symbol, next_size, current_price, side, reduce_only=False
            )
            from qengine.services import order_service
            from qengine.enums import order_types
            if isinstance(result, dict):
                exchange_order_id = result['order_id']
                fill_price = result.get('fill_price') or current_price
                trade_id = result.get('trade_id')
            else:
                exchange_order_id = result
                fill_price = current_price
                trade_id = None

            order = order_service.create_order({
                'id': jh.generate_unique_id(),
                'exchange_id': exchange_order_id,
                'symbol': self.symbol,
                'exchange': self.exchange,
                'side': side,
                'type': order_types.MARKET,
                'reduce_only': False,
                'qty': jh.prepare_qty(next_size, side),
                'price': fill_price,
            })
            order.vars['purpose'] = 'surefire_hedge'
            order.vars['session'] = self.vars['session_number']
            order.vars['level'] = next_level
            if trade_id:
                order.vars['trade_id'] = trade_id
            order.filled_qty = order.qty
            order_service.execute_order(order)

            # Update level state
            self.vars['level'] = next_level
            tp_dist = self.pips_to_price(self.tp_distance_pips)
            hedge_dist = self.pips_to_price(self.hedge_distance_pips)
            if next_dir == 'long':
                new_tp = round(hedge_price + tp_dist, 5)
                new_hedge = round(hedge_price - hedge_dist, 5)
            else:
                new_tp = round(hedge_price - tp_dist, 5)
                new_hedge = round(hedge_price + hedge_dist, 5)
            self.vars['tp_price'] = new_tp
            self.vars['hedge_trigger_price'] = new_hedge

            new_ticket = self.position.tickets[-1] if self.position.tickets else None
            ticket_trade_id = new_ticket.exchange_trade_id if new_ticket else trade_id
            self.vars['legs'].append({
                'dir': next_dir, 'qty': next_size, 'entry': fill_price,
                'tp': new_tp, 'hedge': new_hedge,
                'trade_id': ticket_trade_id,
            })
            self.vars['order_in_session'] += 1
            self.vars['expected_tickets'] = self.position.ticket_count

            logger.info(
                f'[Surefire] S{self.vars["session_number"]} Order #{self.vars["order_in_session"]} (L{next_level}): '
                f'Hedge MARKET {side.upper()} {next_size:.0f} @ {fill_price:.5f}, '
                f'new TP={new_tp:.5f}, hedge={new_hedge:.5f}'
            )

            # Set up broker orders for the new level (new TP/SL + next hedge)
            self._cancel_all_trade_tp_sl()
            self.vars['broker_orders_set'] = False
            self._setup_broker_orders(_depth=_depth + 1)
        except Exception as e:
            logger.error(f'[Surefire] MARKET hedge also failed: {e}')
            self.vars['broker_orders_set'] = False

    def _cancel_hedge_order(self):
        """Cancel the current hedge STOP order on OANDA."""
        order_id = self.vars.get('hedge_order_id')
        if not order_id:
            return

        driver = self._get_driver()
        if driver:
            try:
                driver._cancel_order_on_exchange(self.symbol, order_id)
                logger.info(f'[Surefire] Cancelled hedge order {order_id}')
            except Exception as e:
                logger.info(f'[Surefire] Failed to cancel hedge order {order_id}: {e}')

        # Also cancel in internal store
        for order in self.entry_orders:
            if order.is_active and getattr(order, 'exchange_id', None) == order_id:
                try:
                    from qengine.services import order_service
                    order_service.cancel_order(order, silent=True)
                except Exception:
                    pass

        self.vars['hedge_order_id'] = None

    def _cancel_all_trade_tp_sl(self):
        """Remove TP/SL from all OANDA trades (e.g., before setting new levels)."""
        driver = self._get_driver()
        if not driver:
            return

        for ticket in self.position.tickets:
            trade_id = ticket.exchange_trade_id
            if trade_id:
                try:
                    driver.cancel_trade_tp_sl(trade_id)
                except Exception as e:
                    logger.info(f'Failed to cancel TP/SL on trade {trade_id}: {e}')

    # -- Entry Conditions -----------------------------------------------

    def should_long(self) -> bool:
        # Only level 0 enters via should_long; higher levels added via hedge STOP orders
        if self.vars['cycle_active']:
            return False
        if self.current_candle[0] <= self.vars['cooldown_until']:
            return False
        return self.vars.get('session_dir', self.direction) == 'long' or \
               (not self.vars['session_dir'] and self.direction == 'long')

    def should_short(self) -> bool:
        if self.vars['cycle_active']:
            return False
        if self.current_candle[0] <= self.vars['cooldown_until']:
            return False
        return self.vars.get('session_dir', self.direction) == 'short' or \
               (not self.vars['session_dir'] and self.direction == 'short')

    # -- Entry Execution (level 0 only) ---------------------------------

    def go_long(self):
        self._start_new_session()
        size = self._size_for_level(0)
        entry = self.price
        tp_dist = self.pips_to_price(self.tp_distance_pips)
        hedge_dist = self.pips_to_price(self.hedge_distance_pips)

        self.buy = size, entry
        # NO take_profit or stop_loss — managed via broker orders

        self.vars['level'] = 0
        self.vars['cycle_active'] = True
        self.vars['tp_price'] = entry + tp_dist
        self.vars['hedge_trigger_price'] = entry - hedge_dist
        self.vars['expected_tickets'] = 1
        self.vars['legs'].append({
            'dir': 'long', 'qty': size, 'entry': entry,
            'tp': entry + tp_dist, 'hedge': entry - hedge_dist,
        })
        self.vars['order_in_session'] = 1
        logger.info(
            f'[Surefire] S{self.vars["session_number"]} Order #1: '
            f'BUY {size:.0f} @ {entry:.5f}, TP={entry + tp_dist:.5f}, hedge={entry - hedge_dist:.5f}'
        )
        self.chart_label = f'S{self.vars["session_number"]}.L0'

    def go_short(self):
        self._start_new_session()
        size = self._size_for_level(0)
        entry = self.price
        tp_dist = self.pips_to_price(self.tp_distance_pips)
        hedge_dist = self.pips_to_price(self.hedge_distance_pips)

        self.sell = size, entry
        # NO take_profit or stop_loss

        self.vars['level'] = 0
        self.vars['cycle_active'] = True
        self.vars['tp_price'] = entry - tp_dist
        self.vars['hedge_trigger_price'] = entry + hedge_dist
        self.vars['expected_tickets'] = 1
        self.vars['legs'].append({
            'dir': 'short', 'qty': size, 'entry': entry,
            'tp': entry - tp_dist, 'hedge': entry + hedge_dist,
        })
        self.vars['order_in_session'] = 1
        logger.info(
            f'[Surefire] S{self.vars["session_number"]} Order #1: '
            f'SELL {size:.0f} @ {entry:.5f}, TP={entry - tp_dist:.5f}, hedge={entry + hedge_dist:.5f}'
        )
        self.chart_label = f'S{self.vars["session_number"]}.L0'

    # -- Lifecycle Hooks -------------------------------------------------

    def before(self):
        """Detect broker-side events and ensure broker orders are in place.

        Handles:
        1. TP filled: OANDA closed all trades via per-trade TP/SL → position is flat.
        2. Hedge filled: Hedge STOP order filled → new ticket appeared.
        3. Retry: If broker orders weren't confirmed, retry setup.
        4. Fallback: If in live mode and price crossed hedge trigger without
           broker STOP filling, execute hedge immediately.
        """
        if not self.vars['cycle_active']:
            return

        # Case 1: Position closed externally (TP/SL fired on OANDA)
        if self.position.is_close:
            tp_price = self.vars['tp_price']
            session_pnl = 0
            for leg in self.vars['legs']:
                if leg['dir'] == 'long':
                    session_pnl += leg['qty'] * (tp_price - leg['entry'])
                else:
                    session_pnl += leg['qty'] * (leg['entry'] - tp_price)
            self.vars['current_session_pnl'] = session_pnl

            logger.info(
                f'[Surefire] S{self.vars["session_number"]}: TP hit at {tp_price:.5f}, '
                f'PnL={session_pnl:.2f}, levels={self.vars["level"]}'
            )

            # Cancel any remaining hedge order
            self._cancel_hedge_order()

            # Record closed trades for each ticket
            self._record_tp_close(tp_price)

            self._reset_cycle('tp_hit')
            return

        # Case 2: New ticket appeared (hedge STOP filled on OANDA)
        current_tickets = self.position.ticket_count
        expected = self.vars['expected_tickets']

        if current_tickets > expected:
            # A new ticket was opened by the hedge STOP order fill
            self._handle_hedge_filled()
            return

        # Case 3: Retry broker order setup if it wasn't confirmed
        # Throttle: only retry every 10 ticks (~10s) to avoid cancel→resubmit loops
        if jh.is_live() and not self.vars.get('broker_orders_set'):
            retry_count = self.vars.get('_broker_retry_count', 0) + 1
            self.vars['_broker_retry_count'] = retry_count
            if retry_count <= 3:
                logger.info(f'[Surefire] Broker orders not confirmed — retry {retry_count}/3...')
                self._setup_broker_orders()
            elif retry_count % 10 == 0:
                logger.info(f'[Surefire] Broker orders still not confirmed (tick {retry_count}), retrying...')
                self._setup_broker_orders()

        # Case 4: Live fallback — price crossed hedge/SL trigger but broker order didn't fill
        if jh.is_live() and self.vars.get('hedge_trigger_price'):
            current_price = self.price
            hedge_price = self.vars['hedge_trigger_price']
            last_dir = self.vars['legs'][-1]['dir'] if self.vars['legs'] else None

            breached = False
            if last_dir == 'long' and current_price <= hedge_price:
                breached = True
            elif last_dir == 'short' and current_price >= hedge_price:
                breached = True

            if breached:
                if self.vars['level'] + 1 >= self.max_levels:
                    # At max level: this is a SL, not a hedge
                    self._handle_max_level_sl(hedge_price)
                elif not bool(self.vars.get('hedge_order_id')):
                    logger.info(
                        f'[Surefire] FALLBACK: Price {current_price:.5f} breached hedge '
                        f'{hedge_price:.5f} but no hedge STOP exists — executing hedge NOW'
                    )
                    self._handle_hedge_trigger(hedge_price)

    def _record_tp_close(self, tp_price: float):
        """Record closed trades for tickets that were closed by OANDA TP/SL.

        Since OANDA handled the close, position._tickets is already empty
        (cleared by position sync or by _handle_cfd_order). We use legs data
        to record the trades.
        """
        from qengine.services import closed_trade_service
        meta = self._session_meta('tp_hit')

        for i, leg in enumerate(self.vars['legs']):
            # Create a synthetic CFDTicket for the trade record
            from qengine.models.Position import CFDTicket
            ticket = CFDTicket(leg['dir'], leg['qty'], leg['entry'], 0)
            if leg['dir'] == 'long':
                pnl = leg['qty'] * (tp_price - leg['entry'])
            else:
                pnl = leg['qty'] * (leg['entry'] - tp_price)

            ticket_meta = dict(meta)
            ticket_meta['leg_index'] = i
            closed_trade_service.record_ticket_close(
                self.position, ticket, tp_price, pnl, meta=ticket_meta
            )

        self.trades_count += len(self.vars['legs'])

    def _handle_hedge_filled(self):
        """Hedge STOP order filled — new ticket added by order sync.

        Sets up the new level: update TP/SL on all trades, submit new hedge STOP.
        """
        level = self.vars['level'] + 1
        last_dir = self.vars['legs'][-1]['dir']
        new_dir = 'short' if last_dir == 'long' else 'long'

        # Find the newly opened ticket (last one in the list)
        new_ticket = self.position.tickets[-1] if self.position.tickets else None
        if not new_ticket:
            logger.error('[Surefire] Hedge fill detected but no new ticket found')
            return

        hedge_price = self.vars['hedge_trigger_price']
        new_size = new_ticket.qty
        actual_entry = new_ticket.entry_price

        # Check if this is a bust (max levels reached) — live mode only path
        # (In backtest, update_position handles SL at max level)
        if level >= self.max_levels:
            logger.info(f'[Surefire] Max levels reached at L{level} (live hedge filled), closing all')
            self._cancel_all_trade_tp_sl()
            self._handle_max_level_sl(actual_entry)
            return

        # Update level state
        self.vars['level'] = level
        tp_dist = self.pips_to_price(self.tp_distance_pips)
        hedge_dist = self.pips_to_price(self.hedge_distance_pips)

        if new_dir == 'long':
            new_tp = hedge_price + tp_dist
            new_hedge = hedge_price - hedge_dist
        else:
            new_tp = hedge_price - tp_dist
            new_hedge = hedge_price + hedge_dist

        self.vars['tp_price'] = new_tp
        self.vars['hedge_trigger_price'] = new_hedge
        self.vars['legs'].append({
            'dir': new_dir, 'qty': new_size, 'entry': actual_entry,
            'tp': new_tp, 'hedge': new_hedge,
            'trade_id': new_ticket.exchange_trade_id,
        })
        self.vars['order_in_session'] += 1
        self.vars['expected_tickets'] = self.position.ticket_count

        logger.info(
            f'[Surefire] S{self.vars["session_number"]} Order #{self.vars["order_in_session"]} (L{level}): '
            f'Hedge filled {"BUY" if new_dir == "long" else "SELL"} {new_size:.0f} @ {actual_entry:.5f}, '
            f'new TP={new_tp:.5f}, new hedge={new_hedge:.5f}'
        )

        # The old hedge STOP already filled — clear it so _setup_broker_orders places a new one
        self.vars['hedge_order_id'] = None
        self.vars['broker_orders_set'] = False
        self._cancel_all_trade_tp_sl()
        self._setup_broker_orders()

        self.chart_label = f'S{self.vars["session_number"]}.L{level}'

    # -- Update Position (fallback for backtest / non-live) ---------------

    def update_position(self):
        """Price-based TP/hedge checks (used in backtest and as live fallback).

        In live trading, broker orders are the primary mechanism. This method:
        - In backtest: handles all TP/hedge logic
        - In live: acts as safety net if broker orders failed
        """
        if not self.vars['cycle_active']:
            return

        # In live mode with confirmed broker orders, skip price checks
        # (OANDA handles execution). But if orders aren't confirmed, fall through.
        if jh.is_live() and self.vars.get('broker_orders_set'):
            return

        current_price = self.price
        tp_price = self.vars['tp_price']
        hedge_price = self.vars['hedge_trigger_price']
        last_leg = self.vars['legs'][-1] if self.vars['legs'] else None

        if not last_leg:
            return

        last_dir = last_leg['dir']

        # Check TP hit
        tp_hit = False
        if last_dir == 'long' and current_price >= tp_price:
            tp_hit = True
        elif last_dir == 'short' and current_price <= tp_price:
            tp_hit = True

        if tp_hit:
            self._handle_tp_hit(tp_price)
            return

        # At max level: hedge_trigger_price acts as STOP-LOSS (no more hedges possible)
        if self.vars['level'] + 1 >= self.max_levels:
            sl_hit = False
            if last_dir == 'long' and current_price <= hedge_price:
                sl_hit = True
            elif last_dir == 'short' and current_price >= hedge_price:
                sl_hit = True

            if sl_hit:
                self._handle_max_level_sl(hedge_price)
            return

        hedge_hit = False
        if last_dir == 'long' and current_price <= hedge_price:
            hedge_hit = True
        elif last_dir == 'short' and current_price >= hedge_price:
            hedge_hit = True

        if hedge_hit:
            self._handle_hedge_trigger(hedge_price)

    def _session_meta(self, exit_reason: str) -> dict:
        """Build session metadata dict for trade records."""
        return {
            'session': self.vars['session_number'],
            'level': self.vars['level'],
            'exit_reason': exit_reason,
        }

    def _handle_tp_hit(self, tp_price: float):
        """TP reached — close all tickets at TP price (backtest path)."""
        session_pnl = 0
        for leg in self.vars['legs']:
            if leg['dir'] == 'long':
                session_pnl += leg['qty'] * (tp_price - leg['entry'])
            else:
                session_pnl += leg['qty'] * (leg['entry'] - tp_price)
        self.vars['current_session_pnl'] = session_pnl

        self.close_all_tickets(tp_price, meta=self._session_meta('tp_hit'))
        self._reset_cycle('tp_hit')

    def _handle_max_level_sl(self, sl_price: float):
        """Max level SL hit — close all tickets and take the loss."""
        session_pnl = 0
        for leg in self.vars['legs']:
            if leg['dir'] == 'long':
                session_pnl += leg['qty'] * (sl_price - leg['entry'])
            else:
                session_pnl += leg['qty'] * (leg['entry'] - sl_price)
        self.vars['current_session_pnl'] = session_pnl

        logger.info(
            f'[Surefire] S{self.vars["session_number"]}: '
            f'Max level SL hit at {sl_price:.5f}, PnL={session_pnl:.2f}, '
            f'levels={self.vars["level"]}'
        )

        if jh.is_live():
            self._cancel_all_trade_tp_sl()
        self.close_all_tickets(sl_price, meta=self._session_meta('max_level_sl'))
        self._reset_cycle('max_level_sl')

    def _handle_hedge_trigger(self, hedge_price: float):
        """Hedge level triggered — add opposite-direction ticket (backtest/fallback path)."""
        if jh.is_live():
            logger.info(f'[Surefire] _handle_hedge_trigger (LIVE FALLBACK) at {hedge_price:.5f}')
        level = self.vars['level'] + 1

        if level >= self.max_levels:
            # Safety net — should be caught by _handle_max_level_sl first
            self._handle_max_level_sl(hedge_price)
            return

        self.vars['level'] = level
        last_dir = self.vars['legs'][-1]['dir']
        new_dir = 'short' if last_dir == 'long' else 'long'
        new_size = self._size_for_level(level)

        tp_dist = self.pips_to_price(self.tp_distance_pips)
        hedge_dist = self.pips_to_price(self.hedge_distance_pips)

        if new_dir == 'long':
            new_tp = hedge_price + tp_dist
            new_hedge = hedge_price - hedge_dist
            self.broker.buy_at_market(new_size)
        else:
            new_tp = hedge_price - tp_dist
            new_hedge = hedge_price + hedge_dist
            self.broker.sell_at_market(new_size)

        self.vars['tp_price'] = new_tp
        self.vars['hedge_trigger_price'] = new_hedge
        self.vars['legs'].append({
            'dir': new_dir, 'qty': new_size, 'entry': hedge_price,
            'tp': new_tp, 'hedge': new_hedge,
        })
        self.vars['order_in_session'] += 1
        # +1 because the order is queued but not yet executed (ticket not yet created)
        self.vars['expected_tickets'] = self.position.ticket_count + 1
        logger.info(
            f'[Surefire] S{self.vars["session_number"]} Order #{self.vars["order_in_session"]} (L{level}): '
            f'Hedge {"BUY" if new_dir == "long" else "SELL"} {new_size:.0f} @ {hedge_price:.5f}, '
            f'TP={new_tp:.5f}, hedge={new_hedge:.5f}'
        )
        self.chart_label = f'S{self.vars["session_number"]}.L{level}'

        # In live mode, set up broker orders for the new level
        if jh.is_live():
            # Store trade ID on leg if available
            ticket = self.position.tickets[-1] if self.position.tickets else None
            if ticket and ticket.exchange_trade_id:
                self.vars['legs'][-1]['trade_id'] = ticket.exchange_trade_id
            self.vars['broker_orders_set'] = False
            self._cancel_all_trade_tp_sl()
            self._setup_broker_orders()

    # -- Callbacks ------------------------------------------------------

    def on_open_position(self, order) -> None:
        """Called when the first ticket opens (level 0 entry filled)."""
        logger.info(
            f'[Surefire] on_open_position called: '
            f'is_live={jh.is_live()}, cycle_active={self.vars["cycle_active"]}, '
            f'order={order.side if order else None} @ {order.price if order else None}, '
            f'tickets={self.position.ticket_count}'
        )

        if jh.is_live() and self.vars['cycle_active']:
            # Update leg entry with actual fill price
            if self.vars['legs'] and order:
                actual_price = order.price
                leg = self.vars['legs'][-1]
                leg['entry'] = actual_price

                # Store trade ID
                ticket = self.position.tickets[-1] if self.position.tickets else None
                trade_id = ticket.exchange_trade_id if ticket else None
                if trade_id:
                    leg['trade_id'] = trade_id

                logger.info(
                    f'[Surefire] Ticket trade_id: {trade_id}, '
                    f'ticket.id: {ticket.id[:8] if ticket else "none"}'
                )

                # Recalculate TP/hedge from actual fill price
                tp_dist = self.pips_to_price(self.tp_distance_pips)
                hedge_dist = self.pips_to_price(self.hedge_distance_pips)

                if leg['dir'] == 'long':
                    self.vars['tp_price'] = actual_price + tp_dist
                    self.vars['hedge_trigger_price'] = actual_price - hedge_dist
                else:
                    self.vars['tp_price'] = actual_price - tp_dist
                    self.vars['hedge_trigger_price'] = actual_price + hedge_dist

                leg['tp'] = self.vars['tp_price']
                leg['hedge'] = self.vars['hedge_trigger_price']

                logger.info(
                    f'[Surefire] S{self.vars["session_number"]}.L0: '
                    f'Filled {leg["dir"]} @ {actual_price:.5f}, '
                    f'TP={self.vars["tp_price"]:.5f}, '
                    f'hedge={self.vars["hedge_trigger_price"]:.5f}, '
                    f'tp_dist_pips={self.tp_distance_pips}, hedge_dist_pips={self.hedge_distance_pips}'
                )
            else:
                logger.info(
                    f'[Surefire] on_open_position: legs={len(self.vars["legs"])}, order={order}'
                )

            self.vars['expected_tickets'] = self.position.ticket_count
            self.vars['broker_orders_set'] = False
            self._setup_broker_orders()

    def on_close_position(self, order, closed_trade) -> None:
        pass

    def on_ticket_opened(self, order) -> None:
        pass

    def should_cancel_entry(self) -> bool:
        return False

    # -- Monitoring -----------------------------------------------------

    def watch_list(self) -> list:
        return [
            ['session', self.vars['session_number']],
            ['level', self.vars['level']],
            ['tickets_open', self.position.ticket_count],
            ['direction', self.vars.get('session_dir') or self.direction],
            ['base_qty', round(self._base_qty(), 2)],
            ['size', round(self._size_for_level(self.vars['level']), 2)],
            ['cycle_active', self.vars['cycle_active']],
            ['tp_price', self.vars.get('tp_price') or '-'],
            ['hedge_price', self.vars.get('hedge_trigger_price') or '-'],
            ['hedge_order', self.vars.get('hedge_order_id') or '-'],
            ['broker_orders_ok', self.vars.get('broker_orders_set', False)],
            ['completed_sessions', len(self.vars['sessions'])],
        ]

    def filters(self) -> list:
        return []

    def before_terminate(self):
        """Close active session BEFORE the engine force-closes tickets.

        This runs before _terminate()'s force-close, so tickets still exist
        and can be closed with session metadata for proper grouping on the UI.
        """
        if self.vars['cycle_active'] and self.position.is_open:
            close_price = self.price
            session_pnl = 0
            for leg in self.vars['legs']:
                if leg['dir'] == 'long':
                    session_pnl += leg['qty'] * (close_price - leg['entry'])
                else:
                    session_pnl += leg['qty'] * (leg['entry'] - close_price)
            self.vars['current_session_pnl'] = session_pnl

            logger.info(
                f'[Surefire] Terminating with active session — '
                f'closing {self.position.ticket_count} tickets at {close_price:.5f}'
            )

            if jh.is_live():
                self._cancel_hedge_order()
                self._cancel_all_trade_tp_sl()

            self.close_all_tickets(close_price, meta=self._session_meta('terminated'))
            self._reset_cycle('terminated')

    def terminate(self):
        # Clean up any remaining broker orders
        if jh.is_live() and self.vars['cycle_active']:
            self._cancel_hedge_order()
            self._cancel_all_trade_tp_sl()
