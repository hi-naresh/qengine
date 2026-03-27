"""
SurefirePilot — SurefireV2 hedge strategy with GridPilot protection framework.

Identical hedge mechanics to SurefireV2 (indicator signal + bucket exit + CFD tickets),
but wrapped with:
  - DangerScorer: continuous market danger assessment (7 features, online)
  - Entry Gate: blocks entry when danger > 95th percentile
  - Q-Abort: learned mid-cycle abort at dangerous (level, duration, danger) states
  - Stats Collector: tracks cycles, busts, aborts, danger distributions

Works in both backtest and live modes without code changes.
"""
import math
import os
from collections import deque

import qengine.helpers as jh
import qengine.indicators as ta
from qengine.framework.pilot_strategy import PilotStrategy
from qengine.services.safety_sizing import SafetySizing

_FIB = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]
_BARS_PER_DAY = {'1m': 1440, '5m': 288, '15m': 96, '1h': 24, '4h': 6}

# Default path for pre-trained Q-table
_DEFAULT_Q_TABLE = os.path.join(
    os.path.dirname(__file__), '..', '..', 'notebooks', 'phase2', 'data', 'q_table_v2.npy'
)


class SurefirePilot(PilotStrategy):

    def __init__(self):
        super().__init__()

        self.hedge_mode = True

        # Hedge cycle state
        self.vars['level'] = 0
        self.vars['session_dir'] = None
        self.vars['cycle_active'] = False
        self.vars['legs'] = []
        self.vars['hedge_trigger_price'] = None

        # Session tracking
        self.vars['session_number'] = 0
        self.vars['order_in_session'] = 0
        self.vars['sessions'] = []
        self.vars['current_session_pnl'] = 0
        self.vars['cooldown_until'] = 0
        self.vars['last_cycle_outcome'] = None

        # Safety
        self.vars['_safety'] = SafetySizing(
            max_risk_per_cycle_pct=0.15,
            max_total_exposure_pct=0.50,
        )

        # Circuit breakers
        self.vars['_day_start_balance'] = None
        self.vars['_day_start_index'] = 0
        self.vars['_halted'] = False
        self.vars['_halt_until_index'] = 0
        self.vars['_halt_reason'] = None
        self.vars['_consecutive_busts'] = 0
        self.vars['_cycle_outcomes'] = deque(maxlen=200)

    # ── FRAMEWORK CONFIG ────────────────────────────────────────────

    def pilot_config(self) -> dict:
        q_path = self.hp.get('pilot_q_table_path') or _DEFAULT_Q_TABLE
        if not os.path.isabs(q_path):
            q_path = os.path.abspath(q_path)

        return {
            'enable_danger_scorer': self.hp.get('pilot_enable_danger', True),
            'enable_entry_gate': self.hp.get('pilot_enable_gate', True),
            'enable_q_abort': self.hp.get('pilot_enable_abort', True),
            'entry_gate_percentile': self.hp.get('pilot_gate_pct', 95),
            'q_table_path': q_path if os.path.exists(q_path) else None,
            'q_alpha': self.hp.get('pilot_q_alpha', 0.01),
            'q_epsilon': self.hp.get('pilot_q_epsilon', 0.0),
        }

    # ── HYPERPARAMETERS ─────────────────────────────────────────────

    def hyperparameters(self):
        return [
            # Strategy params (same as SurefireV2)
            {'name': 'initial_size',    'type': float, 'min': 0.1,  'max': 50.0, 'default': 2.0},
            {'name': 'sizing_operator', 'type': 'categorical',
             'options': ['multiplier', 'sqrt', 'linear', 'fibonacci'], 'default': 'sqrt'},
            {'name': 'sizing_factor',   'type': float, 'min': 1.1,  'max': 5.0,  'default': 2.0},
            {'name': 'max_levels',      'type': int,   'min': 0,    'max': 8,    'default': 6},
            {'name': 'bucket_pct',      'type': float, 'min': 0.01, 'max': 1.0,  'default': 0.1},
            {'name': 'signal_mode',     'type': 'categorical',
             'options': ['ema', 'rsi', 'macd', 'supertrend', 'ema_rsi', 'ema_macd', 'triple'],
             'default': 'ema'},
            {'name': 'atr_period',      'type': int,   'min': 10,   'max': 20,   'default': 14},
            {'name': 'hedge_atr_mult',  'type': float, 'min': 0.3,  'max': 3.0,  'default': 1.5},
            {'name': 'ema_fast',        'type': int,   'min': 5,    'max': 20,   'default': 8},
            {'name': 'ema_slow',        'type': int,   'min': 15,   'max': 50,   'default': 21},
            {'name': 'rsi_period',      'type': int,   'min': 7,    'max': 21,   'default': 14},
            {'name': 'rsi_ob',          'type': float, 'min': 60,   'max': 80,   'default': 70},
            {'name': 'rsi_os',          'type': float, 'min': 20,   'max': 40,   'default': 30},
            {'name': 'macd_fast',       'type': int,   'min': 8,    'max': 15,   'default': 12},
            {'name': 'macd_slow',       'type': int,   'min': 20,   'max': 30,   'default': 26},
            {'name': 'macd_signal',     'type': int,   'min': 5,    'max': 12,   'default': 9},
            {'name': 'st_period',       'type': int,   'min': 7,    'max': 14,   'default': 10},
            {'name': 'st_factor',       'type': float, 'min': 1.5,  'max': 5.0,  'default': 3.0},
            {'name': 'session_filter',  'type': 'categorical',
             'options': ['london', 'new_york', 'overlap', 'london_ny', 'any'],
             'default': 'london_ny'},
            {'name': 'cooldown_bars',   'type': int,   'min': 1,    'max': 50,   'default': 10},
            {'name': 'max_daily_loss_pct', 'type': float, 'min': 1.0, 'max': 5.0, 'default': 2.0},
            {'name': 'max_consec_busts',   'type': int,   'min': 2,   'max': 10,  'default': 3},
            {'name': 'atr_expansion_mult', 'type': float, 'min': 1.5, 'max': 3.0, 'default': 2.0},

            # Pilot framework params
            {'name': 'pilot_enable_danger', 'type': 'categorical', 'options': [True, False], 'default': True},
            {'name': 'pilot_enable_gate',   'type': 'categorical', 'options': [True, False], 'default': True},
            {'name': 'pilot_enable_abort',  'type': 'categorical', 'options': [True, False], 'default': True},
            {'name': 'pilot_gate_pct',      'type': int,   'min': 85, 'max': 99, 'default': 95},
            {'name': 'pilot_q_alpha',       'type': float, 'min': 0.001, 'max': 0.1, 'default': 0.01},
            {'name': 'pilot_q_epsilon',     'type': float, 'min': 0.0, 'max': 0.1, 'default': 0.0},
        ]

    # ── PROPERTIES ──────────────────────────────────────────────────

    @property
    def initial_size(self) -> float:
        return self.hp.get('initial_size', 2.0)

    @property
    def sizing_operator(self) -> str:
        return self.hp.get('sizing_operator', 'sqrt')

    @property
    def sizing_factor(self) -> float:
        return self.hp.get('sizing_factor', 2.0)

    @property
    def max_levels(self) -> int:
        val = self.hp.get('max_levels', 6)
        return self._auto_max_levels() if val == 0 else val

    @property
    def bucket_pct(self) -> float:
        return self.hp.get('bucket_pct', 0.1)

    @property
    def signal_mode(self) -> str:
        return self.hp.get('signal_mode', 'ema')

    @property
    def safety(self) -> SafetySizing:
        return self.vars['_safety']

    def _bucket_threshold(self) -> float:
        return self.balance * self.bucket_pct / 100.0

    # ── DISTANCES ───────────────────────────────────────────────────

    def _current_atr_pips(self) -> float:
        period = self.hp.get('atr_period', 14)
        return self.price_to_pips(ta.atr(self.candles, period=period))

    @property
    def hedge_distance(self) -> float:
        mult = self.hp.get('hedge_atr_mult', 0.5)
        return max(self._current_atr_pips() * mult, 15.0)

    def _is_atr_expanded(self) -> bool:
        mult = self.hp.get('atr_expansion_mult', 2.0)
        period = self.hp.get('atr_period', 14)
        atr_series = ta.atr(self.candles, period=period, sequential=True)
        current = atr_series[-1]
        if len(atr_series) < 200:
            return False
        avg = float(atr_series[-200:].mean())
        return current > mult * avg if avg > 0 else False

    # ── SIZING ──────────────────────────────────────────────────────

    def _base_qty(self) -> float:
        pct = self.initial_size
        if self._is_atr_expanded():
            pct = min(pct, 0.1)
        margin = self.balance * pct / 100
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
        else:
            return m ** level

    def _size_for_level(self, level: int) -> float:
        base = self.vars.get('_cycle_base_qty') or self._base_qty()
        return base * self._multiplier_factor(level)

    def _auto_max_levels(self) -> int:
        hedge_pips = self.hedge_distance
        if hedge_pips <= 0:
            return 3
        initial = self._base_qty()
        if initial <= 0:
            return 3
        pip_value = self.pip_size * self.contract_size
        m = math.sqrt(self.sizing_factor) if self.sizing_operator == 'sqrt' else self.sizing_factor
        affordable = self.safety.levels_affordable(
            balance=self.balance, initial_size=initial,
            multiplier=m, hedge_pips=hedge_pips, pip_value=pip_value,
        )
        return max(3, min(affordable, 8))

    # ── SIGNALS ─────────────────────────────────────────────────────

    def _signal_ema(self):
        fast = ta.ema(self.candles, period=self.hp.get('ema_fast', 8))
        slow = ta.ema(self.candles, period=self.hp.get('ema_slow', 21))
        return 'long' if fast > slow else 'short'

    def _signal_rsi(self):
        val = ta.rsi(self.candles, period=self.hp.get('rsi_period', 14))
        ob = self.hp.get('rsi_ob', 70)
        os_ = self.hp.get('rsi_os', 30)
        if val <= os_:
            return 'long'
        elif val >= ob:
            return 'short'
        return None

    def _signal_macd(self):
        m = ta.macd(self.candles,
                    fast_period=self.hp.get('macd_fast', 12),
                    slow_period=self.hp.get('macd_slow', 26),
                    signal_period=self.hp.get('macd_signal', 9))
        if m.macd > m.signal:
            return 'long'
        elif m.macd < m.signal:
            return 'short'
        return None

    def _signal_supertrend(self):
        st = ta.supertrend(self.candles,
                           period=self.hp.get('st_period', 10),
                           factor=self.hp.get('st_factor', 3.0))
        if st.trend > 0:
            return 'long'
        elif st.trend < 0:
            return 'short'
        return None

    def _signal_ema_rsi(self):
        ema_dir = self._signal_ema()
        rsi_dir = self._signal_rsi()
        return ema_dir if rsi_dir is None or ema_dir == rsi_dir else None

    def _signal_ema_macd(self):
        ema_dir = self._signal_ema()
        macd_dir = self._signal_macd()
        return ema_dir if macd_dir is None or ema_dir == macd_dir else None

    def _signal_triple(self):
        signals = [s for s in [self._signal_ema(), self._signal_rsi(), self._signal_macd()] if s is not None]
        if signals and all(s == signals[0] for s in signals):
            return signals[0]
        return None

    _SIGNAL_MAP = {
        'ema': '_signal_ema', 'rsi': '_signal_rsi', 'macd': '_signal_macd',
        'supertrend': '_signal_supertrend', 'ema_rsi': '_signal_ema_rsi',
        'ema_macd': '_signal_ema_macd', 'triple': '_signal_triple',
    }

    def _get_signal(self):
        return getattr(self, self._SIGNAL_MAP.get(self.signal_mode, '_signal_ema'))()

    # ── CIRCUIT BREAKERS ────────────────────────────────────────────

    def _bars_per_day(self) -> int:
        return _BARS_PER_DAY.get(self.timeframe, 288)

    def _check_daily_reset(self):
        if self.vars['_day_start_balance'] is None:
            self.vars['_day_start_balance'] = self.balance
            self.vars['_day_start_index'] = self.index
            return
        if self.index - self.vars['_day_start_index'] >= self._bars_per_day():
            self.vars['_day_start_balance'] = self.balance
            self.vars['_day_start_index'] = self.index
            self.vars['_consecutive_busts'] = 0
            if self.vars['_halted'] and self.index >= self.vars['_halt_until_index']:
                self.vars['_halted'] = False
                self.vars['_halt_reason'] = None

    def _check_circuit_breakers(self) -> bool:
        self._check_daily_reset()
        if self.vars['_halted']:
            if self.index >= self.vars['_halt_until_index']:
                self.vars['_halted'] = False
                self.vars['_halt_reason'] = None
            else:
                return True

        day_start = self.vars['_day_start_balance']
        if day_start and day_start > 0:
            if (day_start - self.balance) / day_start >= self.hp.get('max_daily_loss_pct', 2.0) / 100.0:
                self.vars['_halted'] = True
                self.vars['_halt_until_index'] = self.index + self._bars_per_day()
                self.vars['_halt_reason'] = 'daily_loss'
                return True

        if self.vars['_consecutive_busts'] >= self.hp.get('max_consec_busts', 3):
            self.vars['_halted'] = True
            self.vars['_halt_until_index'] = self.index + self._bars_per_day()
            self.vars['_halt_reason'] = 'consec_busts'
            return True

        return False

    def _can_enter(self) -> bool:
        if self._check_circuit_breakers():
            return False

        pref = self.hp.get('session_filter', 'london_ny')
        if pref != 'any':
            current = self.session
            if pref == 'london_ny' and current not in ('london', 'new_york', 'overlap'):
                return False
            elif pref == 'london' and current not in ('london', 'overlap'):
                return False
            elif pref == 'new_york' and current not in ('new_york', 'overlap'):
                return False
            elif pref == 'overlap' and current != 'overlap':
                return False

        if self.vars['last_cycle_outcome'] != 'bucket_hit':
            if self.current_candle[0] <= self.vars['cooldown_until']:
                return False

        return True

    # ── SESSION TRACKING ────────────────────────────────────────────

    def _start_new_session(self):
        self.vars['session_number'] += 1
        self.vars['order_in_session'] = 0
        self.vars['current_session_pnl'] = 0
        self.vars['legs'] = []
        self.vars['_cycle_base_qty'] = self._base_qty()

    def _close_session(self, outcome: str):
        self.vars['sessions'].append({
            'session': self.vars['session_number'],
            'legs': len(self.vars['legs']),
            'pnl': round(self.vars['current_session_pnl'], 6),
            'outcome': outcome,
            'max_level': self.vars['level'],
        })

    def _reset_cycle(self, outcome: str):
        self._close_session(outcome)
        cooldown_bars = self.hp.get('cooldown_bars', 10)
        bar_ms = jh.timeframe_to_one_minutes(self.timeframe) * 60_000
        self.vars['cooldown_until'] = self.current_candle[0] + cooldown_bars * bar_ms
        self.vars['last_cycle_outcome'] = outcome

        self.vars['_cycle_outcomes'].append(outcome)
        if outcome in ('max_levels', 'max_level_sl'):
            self.vars['_consecutive_busts'] += 1
        else:
            self.vars['_consecutive_busts'] = 0

        self.vars['level'] = 0
        self.vars['session_dir'] = None
        self.vars['cycle_active'] = False
        self.vars['hedge_trigger_price'] = None
        self.vars['legs'] = []

    def _session_floating_pnl(self) -> float:
        current_price = self.price
        total = 0.0
        for leg in self.vars['legs']:
            if leg['dir'] == 'long':
                total += leg['qty'] * (current_price - leg['entry'])
            else:
                total += leg['qty'] * (leg['entry'] - current_price)
        return total

    def _session_meta(self, exit_reason: str) -> dict:
        return {
            'session': self.vars['session_number'],
            'level': self.vars['level'],
            'exit_reason': exit_reason,
        }

    # ── PILOT ENTRY (overrides PilotStrategy) ───────────────────────

    def pilot_should_long(self) -> bool:
        if self.vars['cycle_active']:
            return False
        if not self._can_enter():
            return False
        direction = self._get_signal()
        return direction == 'long' if direction else False

    def pilot_should_short(self) -> bool:
        if self.vars['cycle_active']:
            return False
        if not self._can_enter():
            return False
        direction = self._get_signal()
        return direction == 'short' if direction else False

    def go_long(self):
        self._start_new_session()
        size = self._size_for_level(0)
        entry = self.price
        hedge_dist = self.pips_to_price(self.hedge_distance)

        self.buy = size, entry

        self.vars['level'] = 0
        self.vars['session_dir'] = 'long'
        self.vars['cycle_active'] = True
        self.vars['hedge_trigger_price'] = entry - hedge_dist
        self.vars['legs'].append({
            'dir': 'long', 'qty': size, 'entry': entry,
            'hedge': entry - hedge_dist,
        })
        self.vars['order_in_session'] = 1
        self.chart_label = f'S{self.vars["session_number"]}.L0'

    def go_short(self):
        self._start_new_session()
        size = self._size_for_level(0)
        entry = self.price
        hedge_dist = self.pips_to_price(self.hedge_distance)

        self.sell = size, entry

        self.vars['level'] = 0
        self.vars['session_dir'] = 'short'
        self.vars['cycle_active'] = True
        self.vars['hedge_trigger_price'] = entry + hedge_dist
        self.vars['legs'].append({
            'dir': 'short', 'qty': size, 'entry': entry,
            'hedge': entry + hedge_dist,
        })
        self.vars['order_in_session'] = 1
        self.chart_label = f'S{self.vars["session_number"]}.L0'

    # ── PILOT UPDATE POSITION (overrides PilotStrategy) ─────────────

    def pilot_update_position(self):
        if not self.vars['cycle_active']:
            return

        current_price = self.price

        # Bucket check
        floating = self._session_floating_pnl()
        if floating >= self._bucket_threshold():
            self.vars['current_session_pnl'] = floating
            self.close_all_tickets(current_price, meta=self._session_meta('bucket_hit'))
            self._reset_cycle('bucket_hit')
            return

        # Hedge / SL check
        hedge_price = self.vars['hedge_trigger_price']
        last_leg = self.vars['legs'][-1] if self.vars['legs'] else None
        if not last_leg:
            return

        last_dir = last_leg['dir']

        # Max level → stop loss
        if self.vars['level'] + 1 >= self.max_levels:
            sl_hit = ((last_dir == 'long' and current_price <= hedge_price) or
                      (last_dir == 'short' and current_price >= hedge_price))
            if sl_hit:
                self._handle_max_level_sl(hedge_price)
            return

        # Hedge trigger
        hedge_hit = ((last_dir == 'long' and current_price <= hedge_price) or
                     (last_dir == 'short' and current_price >= hedge_price))
        if hedge_hit:
            self._handle_hedge_trigger(hedge_price)

    def _handle_max_level_sl(self, sl_price: float):
        self.vars['current_session_pnl'] = self._session_floating_pnl()
        self.close_all_tickets(sl_price, meta=self._session_meta('max_level_sl'))
        self._reset_cycle('max_level_sl')

    def _handle_hedge_trigger(self, hedge_price: float):
        level = self.vars['level'] + 1
        if level >= self.max_levels:
            self._handle_max_level_sl(hedge_price)
            return

        self.vars['level'] = level
        last_dir = self.vars['legs'][-1]['dir']
        new_dir = 'short' if last_dir == 'long' else 'long'
        new_size = self._size_for_level(level)

        entry_price = self.price
        hedge_dist = self.pips_to_price(self.hedge_distance)

        if new_dir == 'long':
            new_hedge = entry_price - hedge_dist
            self.broker.buy_at_market(new_size)
        else:
            new_hedge = entry_price + hedge_dist
            self.broker.sell_at_market(new_size)

        self.vars['hedge_trigger_price'] = new_hedge
        self.vars['legs'].append({
            'dir': new_dir, 'qty': new_size, 'entry': entry_price,
            'hedge': new_hedge,
        })
        self.vars['order_in_session'] += 1
        self.chart_label = f'S{self.vars["session_number"]}.L{level}'

    # ── ABORT (overrides PilotStrategy._execute_abort) ──────────────

    def _execute_abort(self):
        """Q-abort: close all tickets and reset cycle."""
        self.vars['current_session_pnl'] = self._session_floating_pnl()
        self.vars['last_cycle_outcome'] = 'q_abort'
        self.close_all_tickets(self.price, meta=self._session_meta('q_abort'))
        self._reset_cycle('q_abort')

    # ── CALLBACKS ───────────────────────────────────────────────────

    def pilot_on_close_position(self, order, closed_trade):
        pass

    def on_open_position(self, order) -> None:
        pass

    def on_ticket_opened(self, order) -> None:
        pass

    def should_cancel_entry(self) -> bool:
        return False

    def filters(self) -> list:
        return []

    # ── MONITORING ──────────────────────────────────────────────────

    def _bust_rate(self) -> float:
        outcomes = self.vars['_cycle_outcomes']
        if len(outcomes) == 0:
            return 0.0
        return sum(1 for o in outcomes if o in ('max_levels', 'max_level_sl')) / len(outcomes) * 100.0

    def _daily_drawdown(self) -> float:
        day_start = self.vars.get('_day_start_balance')
        if not day_start or day_start <= 0:
            return 0.0
        return (day_start - self.balance) / day_start * 100.0

    def watch_list(self) -> list:
        pilot_stats = self._pilot.stats if self._pilot else {}
        danger = self._pilot.danger if self._pilot else 0.5
        return [
            ['session', self.vars['session_number']],
            ['level', self.vars['level']],
            ['max_levels', self.max_levels],
            ['tickets_open', self.position.ticket_count],
            ['signal', self._get_signal() or 'HALT'],
            ['danger', f'{danger:.3f}'],
            ['pilot_gates', pilot_stats.get('gates_blocked', 0)],
            ['pilot_aborts', pilot_stats.get('aborts', 0)],
            ['pilot_busts', pilot_stats.get('busts', 0)],
            ['base_qty', round(self._base_qty(), 2)],
            ['hedge_pips', round(self.hedge_distance, 1)],
            ['bucket_target', round(self._bucket_threshold(), 2)],
            ['session_pnl', round(self._session_floating_pnl(), 2)],
            ['cycle_active', self.vars['cycle_active']],
            ['halted', self.vars['_halted']],
            ['bust_rate', f'{self._bust_rate():.1f}%'],
            ['daily_dd', f'{self._daily_drawdown():.2f}%'],
            ['completed', len(self.vars['sessions'])],
        ]

    def before_terminate(self):
        if self.vars['cycle_active'] and self.position.is_open:
            self.vars['current_session_pnl'] = self._session_floating_pnl()
            self.close_all_tickets(self.price, meta=self._session_meta('terminated'))
            self._reset_cycle('terminated')

        # Save framework state for next session
        if self._pilot:
            self._pilot.save_state()

    def terminate(self):
        pass
