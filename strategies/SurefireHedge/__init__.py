"""
Surefire Forex Hedging Strategy
================================
A recovery/martingale hedging strategy that opens progressively larger
opposite positions when price moves against you, until a take-profit is hit.

How it works:
  Level 0: Open initial trade in `direction` with `initial_size`.
           TP at +tp_distance, SL (hedge trigger) at -hedge_distance.
  Level 1: SL hit -> reverse direction, size = initial_size * multiplier.
           TP at +tp_distance, SL at -hedge_distance.
  Level 2: SL hit -> reverse again, size = initial_size * multiplier^2.
           ...continues until a TP is hit or max_levels is reached.

When any TP hits, the accumulated profit from the larger position
should exceed the accumulated losses from all smaller losing legs.
The strategy resets to Level 0 and waits for the next entry signal.

Pip reference (for 5-decimal pairs like EUR-USD where price ≈ 1.50221):
  1 pip = 0.0001 (4th decimal place)
  The 5th decimal (0.00001) is a "pipette" or 1/10th of a pip.
  e.g. 10 pips above 1.50221 = 1.50221 + 0.0010 = 1.50321

Distances (symmetric for both directions):
  TP (reward)        = tp_distance pips
  SL (hedge trigger) = hedge_distance pips

  Example with tp_distance=10, hedge_distance=5, multiplier=2:
    Buy at 1.50221 -> TP=1.50321 (+10 pips), SL=1.50171 (-5 pips)
    SL hit -> Sell 2x at 1.50171 -> TP=1.50071 (-10 pips), SL=1.50221 (+5 pips)
    If Sell TP hits: profit=10*2x=20, loss=5*1x=5, net=+15

Sessions:
  A "session" (S1, S2, ...) groups all trades in one hedge cycle.
  Each trade within a session is labeled O1, O2, etc.
  Chart markers show "S{n}.O{m}" for easy visual identification.

Parameters (all configurable via hyperparameters / optimization):
  direction      : 'long' or 'short' -- initial trade direction
  initial_size   : % of capital to use as margin for initial position (e.g. 1.0 = 1%)
                   actual qty = (balance * initial_size/100 * leverage) / entry_price
  multiplier     : size multiplier per level (e.g. 2.0 = double each hedge)
  tp_distance    : take-profit distance in pips (reward)
  hedge_distance : hedge trigger (SL) distance in pips (risk)
  max_levels     : safety cap on hedge levels (default 5)
"""
import random
from qengine.strategies import Strategy
import qengine.helpers as jh


class SurefireHedge(Strategy):

    def __init__(self):
        super().__init__()
        # Hedge cycle state
        self.vars['level'] = 0
        self.vars['next_dir'] = None
        self.vars['session_dir'] = None
        self.vars['cycle_active'] = False
        self.vars['entry_price'] = 0

        # Session tracking
        self.vars['session_number'] = 0
        self.vars['order_in_session'] = 0
        self.vars['sessions'] = []

        # Current session accumulator
        self.vars['current_session_trades'] = []
        self.vars['current_session_pnl'] = 0

        # Cooldown: don't re-enter on the same candle a session closed
        self.vars['cooldown_until'] = 0

    # -- Configurable Parameters ----------------------------------------

    def hyperparameters(self):
        return [
            {'name': 'direction',      'type': 'categorical', 'options': ['long', 'short', 'random'], 'default': 'long',
             'description': 'Initial trade direction (random picks per session)'},
            {'name': 'initial_size',   'type': float, 'min': 0.1,  'max': 50.0,    'default': 1.0,
             'description': '% of equity used as margin for initial position'},
            {'name': 'multiplier',     'type': float, 'min': 1.1,  'max': 5.0,     'default': 2.0,
             'description': 'Size multiplier per hedge level (2.0 = double each level)'},
            {'name': 'tp_distance',    'type': float, 'min': 3,    'max': 200,     'default': 20,
             'description': 'Take-profit distance in pips (1 pip = 0.0001 for EUR-USD)'},
            {'name': 'hedge_distance', 'type': float, 'min': 1,    'max': 200,     'default': 10,
             'description': 'Hedge trigger (SL) distance in pips — reversal point'},
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
    def multiplier(self) -> float:
        return self.hp.get('multiplier', 2.0)

    @property
    def tp_distance(self) -> float:
        return self.hp.get('tp_distance', 10)

    @property
    def hedge_distance(self) -> float:
        return self.hp.get('hedge_distance', 5)

    @property
    def max_levels(self) -> int:
        return self.hp.get('max_levels', 5)

    def _base_qty(self) -> float:
        """Calculate base qty from initial_size (% of capital as margin).
        margin = balance * initial_size / 100
        qty = margin * leverage / price
        """
        margin = self.balance * self.initial_size / 100
        qty = margin * self.leverage / self.price
        return qty

    def _size_for_level(self, level: int) -> float:
        """Position size at a given hedge level."""
        return self._base_qty() * (self.multiplier ** level)

    def _get_tp_distance(self) -> float:
        """TP distance in pips (reward). Same for both directions."""
        return self.tp_distance

    def _get_sl_distance(self) -> float:
        """SL (hedge trigger) distance in pips. Same for both directions."""
        return self.hedge_distance

    def _current_direction(self) -> str:
        """Which direction should the NEXT trade be?"""
        if self.vars['next_dir'] is not None:
            return self.vars['next_dir']
        # At level 0 (new session about to start), pick direction
        if self.direction == 'random':
            if 'session_dir' not in self.vars or not self.vars['session_dir']:
                self.vars['session_dir'] = random.choice(['long', 'short'])
            return self.vars['session_dir']
        return self.direction

    def _start_new_session(self):
        """Begin a new hedge session."""
        self.vars['session_number'] += 1
        self.vars['order_in_session'] = 0
        self.vars['current_session_trades'] = []
        self.vars['current_session_pnl'] = 0
        self.vars['session_open_price'] = self.price
        # Pick random direction for this session if configured
        if self.direction == 'random':
            self.vars['session_dir'] = random.choice(['long', 'short'])
        else:
            self.vars['session_dir'] = self.direction

    def _set_chart_label(self):
        """Set chart_label for the current order: S{n}.O{m}"""
        self.vars['order_in_session'] += 1
        s = self.vars['session_number']
        o = self.vars['order_in_session']
        self.chart_label = f'S{s}.O{o}'

    def _close_session(self, outcome: str):
        """Finalize the current session and store its summary."""
        s = self.vars['session_number']
        self.vars['sessions'].append({
            'session': s,
            'trades': len(self.vars['current_session_trades']),
            'trade_ids': list(self.vars['current_session_trades']),
            'pnl': round(self.vars['current_session_pnl'], 6),
            'outcome': outcome,
        })

    # -- Entry Conditions -----------------------------------------------

    def should_long(self) -> bool:
        # Don't re-enter on the same candle a session just closed
        if self.current_candle[0] <= self.vars['cooldown_until']:
            return False
        if self.vars['level'] >= self.max_levels:
            if self.vars['cycle_active']:
                self._close_session('max_levels')
                self.vars['level'] = 0
                self.vars['next_dir'] = None
                self.vars['session_dir'] = None
                self.vars['cycle_active'] = False
                self.vars['cooldown_until'] = self.current_candle[0]
            return False
        return self._current_direction() == 'long'

    def should_short(self) -> bool:
        if self.current_candle[0] <= self.vars['cooldown_until']:
            return False
        if self.vars['level'] >= self.max_levels:
            if self.vars['cycle_active']:
                self._close_session('max_levels')
                self.vars['level'] = 0
                self.vars['next_dir'] = None
                self.vars['session_dir'] = None
                self.vars['cycle_active'] = False
                self.vars['cooldown_until'] = self.current_candle[0]
            return False
        return self._current_direction() == 'short'

    # -- Entry Execution ------------------------------------------------

    def go_long(self):
        level = self.vars['level']
        if level == 0:
            self._start_new_session()

        self._set_chart_label()

        size = self._size_for_level(level)
        entry = self.price
        tp = entry + self.pips_to_price(self._get_tp_distance())
        sl = entry - self.pips_to_price(self._get_sl_distance())

        self.buy = size, entry
        self.take_profit = size, tp
        self.stop_loss = size, sl

        self.vars['entry_price'] = entry
        self.vars['tp_price'] = tp
        self.vars['sl_price'] = sl
        self.vars['cycle_active'] = True

    def go_short(self):
        level = self.vars['level']
        if level == 0:
            self._start_new_session()

        self._set_chart_label()

        size = self._size_for_level(level)
        entry = self.price
        tp = entry - self.pips_to_price(self._get_tp_distance())
        sl = entry + self.pips_to_price(self._get_sl_distance())

        self.sell = size, entry
        self.take_profit = size, tp
        self.stop_loss = size, sl

        self.vars['entry_price'] = entry
        self.vars['tp_price'] = tp
        self.vars['sl_price'] = sl
        self.vars['cycle_active'] = True

    # -- Position Close Handling ----------------------------------------

    def on_close_position(self, order, closed_trade):
        """Called when position closes (TP or SL hit)."""
        s = self.vars['session_number']
        o = self.vars['order_in_session']

        # Tag the trade with session metadata
        closed_trade.meta = {
            'session': s,
            'order_in_session': o,
            'level': self.vars['level'],
            'label': f'S{s}.O{o}',
            'tp_price': self.vars.get('tp_price'),
            'sl_price': self.vars.get('sl_price'),
            'session_open_price': self.vars.get('session_open_price'),
            'qty': closed_trade.qty,
        }

        # Accumulate session data
        self.vars['current_session_trades'].append(str(closed_trade.id))
        self.vars['current_session_pnl'] += closed_trade.pnl

        if order.is_take_profit:
            closed_trade.meta['exit_reason'] = 'tp_hit'
            self._close_session('tp_hit')
            # TP hit -- cycle is over, reset to Level 0
            self.vars['level'] = 0
            self.vars['next_dir'] = None
            self.vars['session_dir'] = None
            self.vars['cycle_active'] = False
            self.vars['cooldown_until'] = self.current_candle[0]
        elif order.is_stop_loss:
            closed_trade.meta['exit_reason'] = 'sl_hit'
            # SL hit -- hedge: reverse direction and increase level
            current = self._current_direction()
            next_dir = 'short' if current == 'long' else 'long'
            self.vars['level'] += 1
            self.vars['next_dir'] = next_dir

    def should_cancel_entry(self) -> bool:
        # Safety: if we've exceeded max hedge levels, stop trading this cycle
        if self.vars['level'] >= self.max_levels:
            self._close_session('max_levels')
            self.vars['level'] = 0
            self.vars['next_dir'] = None
            self.vars['session_dir'] = None
            self.vars['cycle_active'] = False
            return True
        return False

    def update_position(self):
        pass

    # -- Monitoring -----------------------------------------------------

    def watch_list(self) -> list:
        return [
            ['session', self.vars['session_number']],
            ['level', self.vars['level']],
            ['order_in_session', self.vars['order_in_session']],
            ['direction', self._current_direction()],
            ['base_qty', round(self._base_qty(), 2)],
            ['size', round(self._size_for_level(self.vars['level']), 2)],
            ['cycle_active', self.vars['cycle_active']],
            ['completed_sessions', len(self.vars['sessions'])],
        ]

    def filters(self) -> list:
        return []

    def terminate(self):
        pass
