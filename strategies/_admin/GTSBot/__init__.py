"""
GTSBot — Pure same-direction grid strategy implementing Rundo et al. (2019).

Paper: "Grid Trading System Robot (GTSbot): A Novel Mathematical Algorithm
for Trading FX Market" (Appl. Sci. 2019, 9, 1796)

This strategy implements the paper's core mechanic:
  1. Enter in the confirmed trend direction (EMA crossover for timing)
  2. Add MORE positions in the SAME direction when price moves against us
     (grid averaging down for longs, averaging up for shorts)
  3. Close ALL when basket profit target is reached

This is the pure GTSBot algorithm — NO hedging in the opposite direction.
It is designed to run WITH the GTSBotPilot pipeline which provides:
  - Entry quality gating (TrendFilter: d1/d2 derivatives confirm trend)
  - Grid spacing enforcement (GridManager: x/y thresholds, max ops)
  - Basket equity exit (BasketManager: close_all when TP reached)

Without the pipeline attached, the strategy still functions but uses a
simple basket P&L TP as fallback.

Usage:
    config = {
        'strategy': {'name': 'GTSBot'},
        'app': {
            'pipelines': [{'name': 'GTSBotPilot', 'config': {...}}]
        }
    }
"""
import numpy as np
import qengine.indicators as ta
from qengine.strategies import Strategy


class GTSBot(Strategy):

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                        HYPERPARAMETERS                                ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def hyperparameters(self):
        _G = 'General'
        _E = 'Entry Signal'
        _Grid = 'Grid'
        _TP = 'Take Profit'

        return [
            # ── General ──
            {'name': 'lot_size', 'type': float, 'group': _G,
             'min': 0.001, 'max': 10.0, 'default': 0.01,
             'description': 'Base lot size for L0 entry'},
            {'name': 'max_levels', 'type': int, 'group': _G,
             'min': 1, 'max': 20, 'default': 13,
             'description': 'Max grid levels (paper uses 13)'},
            {'name': 'sizing_curve', 'type': 'categorical', 'group': _G,
             'options': ['fixed', 'geometric', 'linear'],
             'default': 'geometric',
             'description': 'fixed=same qty each level, geometric=mult^level, linear=level*base'},
            {'name': 'sizing_multiplier', 'type': float, 'group': _G,
             'min': 1.0, 'max': 3.0, 'default': 1.5,
             'description': 'Geometric multiplier per level (1.5 = 50% more each level)'},

            # ── Entry Signal ──
            {'name': 'ema_fast', 'type': int, 'group': _E,
             'min': 3, 'max': 50, 'default': 8},
            {'name': 'ema_slow', 'type': int, 'group': _E,
             'min': 10, 'max': 200, 'default': 21},
            {'name': 'entry_on_crossover', 'type': 'categorical', 'group': _E,
             'options': ['yes', 'no'], 'default': 'yes',
             'description': 'yes=only on crossover moment, no=while fast>slow (more entries)'},

            # ── Grid Spacing ──
            {'name': 'grid_spacing_atr', 'type': float, 'group': _Grid,
             'min': 0.3, 'max': 5.0, 'default': 1.5,
             'description': 'Min price distance to add next level (ATR multiples)'},
            {'name': 'grid_expand', 'type': 'categorical', 'group': _Grid,
             'options': ['no', 'yes'], 'default': 'no',
             'description': 'Expand grid spacing at deeper levels (wider gaps)'},
            {'name': 'grid_expand_factor', 'type': float, 'group': _Grid,
             'min': 1.0, 'max': 2.0, 'default': 1.2,
             'depends_on': {'grid_expand': ['yes']}},

            # ── Take Profit (fallback when no pipeline attached) ──
            {'name': 'tp_atr_mult', 'type': float, 'group': _TP,
             'min': 0.5, 'max': 10.0, 'default': 2.0,
             'description': 'Basket TP = ATR * mult * total_qty (pipeline uses this if attached)'},
            {'name': 'sl_atr_mult', 'type': float, 'group': _TP,
             'min': 0.0, 'max': 30.0, 'default': 10.0,
             'description': 'Basket SL = ATR * mult * total_qty. 0 = disabled'},
        ]

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                          LIFECYCLE                                    ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def before(self):
        if self.index == 0:
            self.vars.update({
                'session_number': 0,
                'level': 0,
                'direction': None,
                'grid_prices': [],       # entry prices for each grid level
                'grid_qtys': [],         # qty entered at each level
            })

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                        ENTRY SIGNALS                                  ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def should_long(self) -> bool:
        if len(self.candles) < self.hp['ema_slow'] + 3:
            return False
        fast = ta.ema(self.candles, period=self.hp['ema_fast'])
        slow = ta.ema(self.candles, period=self.hp['ema_slow'])
        if self.hp.get('entry_on_crossover', 'yes') == 'yes':
            fast_prev = ta.ema(self.candles[:-1], period=self.hp['ema_fast'])
            slow_prev = ta.ema(self.candles[:-1], period=self.hp['ema_slow'])
            return fast > slow and fast_prev <= slow_prev
        return fast > slow

    def should_short(self) -> bool:
        if len(self.candles) < self.hp['ema_slow'] + 3:
            return False
        fast = ta.ema(self.candles, period=self.hp['ema_fast'])
        slow = ta.ema(self.candles, period=self.hp['ema_slow'])
        if self.hp.get('entry_on_crossover', 'yes') == 'yes':
            fast_prev = ta.ema(self.candles[:-1], period=self.hp['ema_fast'])
            slow_prev = ta.ema(self.candles[:-1], period=self.hp['ema_slow'])
            return fast < slow and fast_prev >= slow_prev
        return fast < slow

    def go_long(self):
        self.vars['session_number'] += 1
        self.vars['level'] = 0
        self.vars['direction'] = 'long'
        self.vars['grid_prices'] = []
        self.vars['grid_qtys'] = []
        qty = self._level_qty(0)
        self.buy = qty, self.price

    def go_short(self):
        self.vars['session_number'] += 1
        self.vars['level'] = 0
        self.vars['direction'] = 'short'
        self.vars['grid_prices'] = []
        self.vars['grid_qtys'] = []
        qty = self._level_qty(0)
        self.sell = qty, self.price

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                      POSITION MANAGEMENT                              ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def update_position(self):
        level = self.vars.get('level', 0)
        direction = self.vars.get('direction')
        grid_prices = self.vars.get('grid_prices', [])

        if not grid_prices or direction is None:
            return

        # Pipeline handles exit (suggest_exit → close_all), but also check
        # standalone basket TP/SL if no pipeline is managing exit.
        if not self._pipelines:
            self._check_standalone_exit()

        # Don't add more levels if at max
        if level >= self.hp['max_levels']:
            return

        atr = ta.atr(self.candles, period=14) if len(self.candles) >= 14 else 0
        if atr <= 0:
            return

        # Grid spacing: expands at deeper levels if configured
        spacing = atr * self.hp['grid_spacing_atr']
        if self.hp.get('grid_expand', 'no') == 'yes':
            expand_factor = self.hp.get('grid_expand_factor', 1.2)
            spacing *= (expand_factor ** level)

        last_price = grid_prices[-1]

        if direction == 'long' and self.close <= last_price - spacing:
            # Price dropped far enough — average down (add another long)
            new_qty = self._level_qty(level + 1)
            self.buy = new_qty, self.price
            # level incremented in on_open_position via position tracking

        elif direction == 'short' and self.close >= last_price + spacing:
            # Price rose far enough — average up (add another short)
            new_qty = self._level_qty(level + 1)
            self.sell = new_qty, self.price

    def _check_standalone_exit(self):
        """Fallback basket TP/SL when no pipeline is attached."""
        pnl = self.position.pnl
        if len(self.candles) < 14:
            return
        atr = ta.atr(self.candles, period=14)
        total_qty = abs(self.position.qty)
        qty_scale = max(total_qty, 1.0)

        target = atr * self.hp['tp_atr_mult'] * qty_scale
        if pnl >= target:
            self.liquidate()
            return

        sl_mult = self.hp.get('sl_atr_mult', 0.0)
        if sl_mult > 0:
            max_loss = atr * sl_mult * qty_scale
            if pnl <= -max_loss:
                self.liquidate()

    def on_open_position(self, order=None):
        """Track each new grid entry."""
        if order is None:
            return
        entry_price = getattr(order, 'price', self.price) or self.price
        self.vars['grid_prices'].append(entry_price)
        self.vars['grid_qtys'].append(getattr(order, 'qty', 0.0))
        # level = number of grid entries so far (0-indexed)
        self.vars['level'] = max(0, len(self.vars['grid_prices']) - 1)

    def on_close_position(self, order=None):
        """Reset state on position close."""
        self.vars['level'] = 0
        self.vars['direction'] = None
        self.vars['grid_prices'] = []
        self.vars['grid_qtys'] = []

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                          HELPERS                                      ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def _level_qty(self, level: int) -> float:
        """Compute lot size for a given grid level."""
        base = self.hp['lot_size']
        curve = self.hp.get('sizing_curve', 'geometric')
        if curve == 'fixed':
            return base
        elif curve == 'linear':
            return base * (level + 1)
        else:  # geometric (default)
            mult = self.hp.get('sizing_multiplier', 1.5)
            return base * (mult ** level)
