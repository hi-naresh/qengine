"""
SurefireHedge V2 — Timing + Momentum Aware
============================================
Solves the two fatal flaws of V1:
  1. TIMING:   V1 enters every bar blindly. V2 waits for momentum + volatility confirmation.
  2. MOMENTUM: V1 uses a static direction. V2 aligns with current momentum and re-checks at each hedge level.

Additionally:
  - ATR-scaled distances: TP and hedge distances auto-calibrate to current volatility.
  - Safety sizing: position size dynamically capped so worst-case cycle never threatens the account.
  - Cooldown: after a failed cycle, waits before re-entering to avoid the same chop.

The goal: push Level 0 win rate above 65-70%, making deep hedge levels rare events
that finite balance can comfortably survive.
"""
import qengine.indicators as ta
import qengine.helpers as jh
from qengine.strategies import Strategy
from qengine.services.safety_sizing import SafetySizing


class SurefireHedgeV2(Strategy):

    def __init__(self):
        super().__init__()

        # Hedge cycle state
        self.vars['level'] = 0
        self.vars['cycle_active'] = False
        self.vars['cycle_direction'] = None     # direction chosen at cycle start
        self.vars['hedge_direction'] = None     # current leg direction (may differ from cycle_direction)

        # Session tracking
        self.vars['session_number'] = 0
        self.vars['order_in_session'] = 0
        self.vars['sessions'] = []
        self.vars['current_session_trades'] = []
        self.vars['current_session_pnl'] = 0

        # Cooldown state
        self.vars['last_cycle_end_index'] = -9999
        self.vars['last_cycle_outcome'] = None   # 'tp_hit', 'max_levels', None

        # Safety sizing instance
        self.vars['_safety'] = SafetySizing(
            max_risk_per_cycle_pct=0.15,
            max_total_exposure_pct=0.50,
        )

        # Cached ATR distances (recalculated per cycle)
        self.vars['_tp_pips'] = 0
        self.vars['_hedge_pips'] = 0

    # ──────────────────────────────────────────────────────────────
    #  HYPERPARAMETERS
    # ──────────────────────────────────────────────────────────────

    def hyperparameters(self):
        return [
            # --- DISTANCE CALIBRATION (primary) ---
            {'name': 'atr_period',         'type': int,   'min': 7,    'max': 50,   'default': 14},
            {'name': 'tp_atr_multiple',    'type': float, 'min': 0.3,  'max': 1.5,  'default': 0.8},
            {'name': 'risk_reward',        'type': float, 'min': 1.2,  'max': 3.5,  'default': 2.0},

            # --- MOMENTUM (for direction) ---
            {'name': 'mom_method',         'type': str,   'options': ['ema_cross', 'rsi_midline', 'macd_hist'],
                                                                       'default': 'ema_cross'},
            {'name': 'fast_period',        'type': int,   'min': 3,    'max': 30,   'default': 8},
            {'name': 'slow_period',        'type': int,   'min': 10,   'max': 100,  'default': 21},
            {'name': 'adx_threshold',      'type': float, 'min': 10.0, 'max': 40.0, 'default': 20.0},

            # --- ENTRY FILTERS ---
            {'name': 'cooldown_bars',      'type': int,   'min': 1,    'max': 200,  'default': 10},
            {'name': 'min_atr_pips',       'type': float, 'min': 1.0,  'max': 30.0, 'default': 5.0},
            {'name': 'max_atr_pips',       'type': float, 'min': 30.0, 'max': 300.0,'default': 150.0},
            {'name': 'session_filter',     'type': str,   'options': ['london', 'new_york', 'overlap', 'london_ny', 'any'],
                                                                       'default': 'london_ny'},

            # --- HEDGE MECHANICS (secondary, narrow ranges) ---
            {'name': 'multiplier',         'type': float, 'min': 1.5,  'max': 2.5,  'default': 2.0},
            {'name': 'max_levels',         'type': int,   'min': 3,    'max': 6,    'default': 5},
            {'name': 'base_size',          'type': float, 'min': 0.01, 'max': 100.0,'default': 1.0},

            # --- SAFETY ---
            {'name': 'max_risk_pct',       'type': float, 'min': 0.05, 'max': 0.25, 'default': 0.15},
        ]

    # ──────────────────────────────────────────────────────────────
    #  PROPERTY ACCESSORS
    # ──────────────────────────────────────────────────────────────

    @property
    def atr_period(self) -> int:
        return self.hp.get('atr_period', 14)

    @property
    def tp_atr_multiple(self) -> float:
        return self.hp.get('tp_atr_multiple', 0.8)

    @property
    def risk_reward(self) -> float:
        return self.hp.get('risk_reward', 2.0)

    @property
    def multiplier(self) -> float:
        return self.hp.get('multiplier', 2.0)

    @property
    def max_levels(self) -> int:
        return self.hp.get('max_levels', 5)

    @property
    def base_size(self) -> float:
        return self.hp.get('base_size', 1.0)

    @property
    def cooldown_bars(self) -> int:
        return self.hp.get('cooldown_bars', 10)

    @property
    def adx_threshold(self) -> float:
        return self.hp.get('adx_threshold', 20.0)

    @property
    def max_risk_pct(self) -> float:
        return self.hp.get('max_risk_pct', 0.15)

    @property
    def safety(self) -> SafetySizing:
        return self.vars['_safety']

    # ──────────────────────────────────────────────────────────────
    #  INDICATORS / SIGNALS
    # ──────────────────────────────────────────────────────────────

    def _current_atr(self) -> float:
        """Current ATR value in price units."""
        return ta.atr(self.candles, period=self.atr_period)

    def _current_atr_pips(self) -> float:
        """Current ATR in pips."""
        return self.price_to_pips(self._current_atr())

    def _compute_distances(self):
        """Calculate TP and hedge distances in pips based on current ATR."""
        atr_pips = self._current_atr_pips()
        tp_pips = atr_pips * self.tp_atr_multiple
        hedge_pips = tp_pips / self.risk_reward

        # Floor: never below minimum viable
        tp_pips = max(tp_pips, 3.0)
        hedge_pips = max(hedge_pips, 1.5)

        self.vars['_tp_pips'] = tp_pips
        self.vars['_hedge_pips'] = hedge_pips

    def _momentum_direction(self) -> str:
        """Determine direction based on configured momentum method."""
        method = self.hp.get('mom_method', 'ema_cross')
        fast = self.hp.get('fast_period', 8)
        slow = self.hp.get('slow_period', 21)

        if method == 'ema_cross':
            fast_ema = ta.ema(self.candles, period=fast)
            slow_ema = ta.ema(self.candles, period=slow)
            return 'long' if fast_ema > slow_ema else 'short'

        elif method == 'rsi_midline':
            rsi = ta.rsi(self.candles, period=fast)
            return 'long' if rsi > 50 else 'short'

        elif method == 'macd_hist':
            m = ta.macd(self.candles, fast_period=fast, slow_period=slow, signal_period=9)
            return 'long' if m.hist > 0 else 'short'

        return 'long'

    def _momentum_strength(self) -> float:
        """ADX-based momentum strength, normalised to [0, 1]."""
        adx = ta.adx(self.candles, period=14)
        return min(adx / 50.0, 1.0)

    def _has_momentum_confirmation(self) -> bool:
        """Is momentum strong enough to justify an entry?"""
        return ta.adx(self.candles, period=14) >= self.adx_threshold

    # ──────────────────────────────────────────────────────────────
    #  FILTERS (the core of V2)
    # ──────────────────────────────────────────────────────────────

    def filters(self) -> list:
        return [
            self._filter_momentum,
            self._filter_volatility,
            self._filter_session,
            self._filter_cooldown,
            self._filter_affordability,
        ]

    def _filter_momentum(self) -> bool:
        """Only enter when there's directional conviction (ADX > threshold)."""
        # Only applies to new cycles (Level 0). Mid-cycle hedges skip this.
        if self.vars['level'] > 0:
            return True
        return self._has_momentum_confirmation()

    def _filter_volatility(self) -> bool:
        """Only enter when ATR is in the tradeable sweet spot."""
        # Only for new cycles
        if self.vars['level'] > 0:
            return True
        atr_pips = self._current_atr_pips()
        min_atr = self.hp.get('min_atr_pips', 5.0)
        max_atr = self.hp.get('max_atr_pips', 150.0)
        return min_atr <= atr_pips <= max_atr

    def _filter_session(self) -> bool:
        """Only start new cycles during configured trading sessions."""
        if self.vars['level'] > 0:
            return True
        session_pref = self.hp.get('session_filter', 'london_ny')
        if session_pref == 'any':
            return True
        current = self.session
        if session_pref == 'london_ny':
            return current in ('london', 'new_york', 'overlap')
        return current == session_pref

    def _filter_cooldown(self) -> bool:
        """Wait after a failed cycle before re-entering."""
        if self.vars['level'] > 0:
            return True
        # Only enforce cooldown after losses (not after wins)
        if self.vars['last_cycle_outcome'] == 'tp_hit':
            return True
        bars_since = self.index - self.vars['last_cycle_end_index']
        return bars_since >= self.cooldown_bars

    def _filter_affordability(self) -> bool:
        """Can the account survive worst-case for this cycle?"""
        if self.vars['level'] > 0:
            return True
        hedge_pips = self.vars.get('_hedge_pips', 0)
        if hedge_pips <= 0:
            # Distances not computed yet, compute now
            self._compute_distances()
            hedge_pips = self.vars['_hedge_pips']
        pip_value = self.pip_size * self.contract_size
        return self.safety.can_afford_cycle(
            balance=self.balance,
            initial_size=self.base_size,
            multiplier=self.multiplier,
            max_levels=self.max_levels,
            hedge_pips=hedge_pips,
            pip_value=pip_value,
            max_risk_pct=self.max_risk_pct,
        )

    # ──────────────────────────────────────────────────────────────
    #  SIZING
    # ──────────────────────────────────────────────────────────────

    def _safe_initial_size(self) -> float:
        """Initial size capped by safety sizing."""
        hedge_pips = self.vars['_hedge_pips']
        pip_value = self.pip_size * self.contract_size
        return self.safety.dynamic_size(
            balance=self.balance,
            base_size=self.base_size,
            multiplier=self.multiplier,
            max_levels=self.max_levels,
            hedge_pips=hedge_pips,
            pip_value=pip_value,
            max_risk_pct=self.max_risk_pct,
        )

    def _size_for_level(self, level: int) -> float:
        """Position size at a given hedge level, safety-capped."""
        initial = self._safe_initial_size()
        return initial * (self.multiplier ** level)

    # ──────────────────────────────────────────────────────────────
    #  SESSION TRACKING
    # ──────────────────────────────────────────────────────────────

    def _start_new_session(self):
        self.vars['session_number'] += 1
        self.vars['order_in_session'] = 0
        self.vars['current_session_trades'] = []
        self.vars['current_session_pnl'] = 0

    def _set_chart_label(self):
        self.vars['order_in_session'] += 1
        s = self.vars['session_number']
        o = self.vars['order_in_session']
        lvl = self.vars['level']
        self.chart_label = f'S{s}.L{lvl}'

    def _close_session(self, outcome: str):
        s = self.vars['session_number']
        self.vars['sessions'].append({
            'session': s,
            'trades': len(self.vars['current_session_trades']),
            'trade_ids': list(self.vars['current_session_trades']),
            'pnl': round(self.vars['current_session_pnl'], 6),
            'outcome': outcome,
            'max_level': self.vars['level'],
        })

    def _reset_cycle(self, outcome: str):
        """Reset cycle state after TP hit or max levels reached."""
        self._close_session(outcome)
        self.vars['last_cycle_end_index'] = self.index
        self.vars['last_cycle_outcome'] = outcome
        self.vars['level'] = 0
        self.vars['cycle_active'] = False
        self.vars['cycle_direction'] = None
        self.vars['hedge_direction'] = None

    # ──────────────────────────────────────────────────────────────
    #  ENTRY CONDITIONS
    # ──────────────────────────────────────────────────────────────

    def should_long(self) -> bool:
        # Max levels reached — force reset
        if self.vars['level'] >= self.max_levels:
            if self.vars['cycle_active']:
                self._reset_cycle('max_levels')
            return False

        # Mid-cycle hedge: direction was already set
        if self.vars['cycle_active'] and self.vars['level'] > 0:
            return self.vars['hedge_direction'] == 'long'

        # New cycle: compute distances, determine momentum direction
        self._compute_distances()
        direction = self._momentum_direction()
        return direction == 'long'

    def should_short(self) -> bool:
        if self.vars['level'] >= self.max_levels:
            if self.vars['cycle_active']:
                self._reset_cycle('max_levels')
            return False

        if self.vars['cycle_active'] and self.vars['level'] > 0:
            return self.vars['hedge_direction'] == 'short'

        self._compute_distances()
        direction = self._momentum_direction()
        return direction == 'short'

    # ──────────────────────────────────────────────────────────────
    #  ENTRY EXECUTION
    # ──────────────────────────────────────────────────────────────

    def go_long(self):
        level = self.vars['level']
        tp_pips = self.vars['_tp_pips']
        hedge_pips = self.vars['_hedge_pips']

        if level == 0:
            self._start_new_session()
            self.vars['cycle_direction'] = 'long'

        self._set_chart_label()

        size = self._size_for_level(level)
        entry = self.price
        tp = entry + self.pips_to_price(tp_pips)
        sl = entry - self.pips_to_price(hedge_pips)

        self.buy = size, entry
        self.take_profit = size, tp
        self.stop_loss = size, sl

        self.vars['cycle_active'] = True

    def go_short(self):
        level = self.vars['level']
        tp_pips = self.vars['_tp_pips']
        hedge_pips = self.vars['_hedge_pips']

        if level == 0:
            self._start_new_session()
            self.vars['cycle_direction'] = 'short'

        self._set_chart_label()

        size = self._size_for_level(level)
        entry = self.price
        tp = entry - self.pips_to_price(tp_pips)
        sl = entry + self.pips_to_price(hedge_pips)

        self.sell = size, entry
        self.take_profit = size, tp
        self.stop_loss = size, sl

        self.vars['cycle_active'] = True

    # ──────────────────────────────────────────────────────────────
    #  POSITION CLOSE HANDLING
    # ──────────────────────────────────────────────────────────────

    def on_close_position(self, order, closed_trade):
        s = self.vars['session_number']
        o = self.vars['order_in_session']
        level = self.vars['level']

        closed_trade.meta = {
            'session': s,
            'order_in_session': o,
            'level': level,
            'label': f'S{s}.L{level}',
        }

        self.vars['current_session_trades'].append(str(closed_trade.id))
        self.vars['current_session_pnl'] += closed_trade.pnl

        if order.is_take_profit:
            # TP hit — cycle won. Reset.
            closed_trade.meta['exit_reason'] = 'tp_hit'
            self._reset_cycle('tp_hit')

        elif order.is_stop_loss:
            # SL hit — hedge fires. Increase level, determine next direction.
            closed_trade.meta['exit_reason'] = 'sl_hit'
            self.vars['level'] += 1

            if self.vars['level'] >= self.max_levels:
                # Can't hedge further, cycle is done
                self._reset_cycle('max_levels')
            else:
                # Re-check momentum for the hedge direction
                # This is the key V2 improvement: don't blindly reverse,
                # align the (larger) hedge leg with current momentum
                new_direction = self._momentum_direction()

                # If momentum is unclear (ADX low), fall back to simple reversal
                if not self._has_momentum_confirmation():
                    current_dir = self.vars.get('hedge_direction') or self.vars['cycle_direction']
                    new_direction = 'short' if current_dir == 'long' else 'long'

                self.vars['hedge_direction'] = new_direction

                # Recompute distances for the new leg (ATR may have changed)
                self._compute_distances()

    def should_cancel_entry(self) -> bool:
        if self.vars['level'] >= self.max_levels:
            if self.vars['cycle_active']:
                self._reset_cycle('max_levels')
            return True
        return False

    def update_position(self):
        pass

    # ──────────────────────────────────────────────────────────────
    #  MONITORING
    # ──────────────────────────────────────────────────────────────

    def watch_list(self) -> list:
        return [
            ['session', self.vars['session_number']],
            ['level', self.vars['level']],
            ['direction', self.vars.get('hedge_direction') or self.vars.get('cycle_direction', '—')],
            ['cycle_active', self.vars['cycle_active']],
            ['tp_pips', round(self.vars.get('_tp_pips', 0), 1)],
            ['hedge_pips', round(self.vars.get('_hedge_pips', 0), 1)],
            ['atr_pips', round(self._current_atr_pips(), 1)],
            ['adx', round(ta.adx(self.candles, period=14), 1)],
            ['momentum', self._momentum_direction()],
            ['safe_size', round(self._safe_initial_size(), 4)],
            ['completed_sessions', len(self.vars['sessions'])],
        ]

    def terminate(self):
        pass
