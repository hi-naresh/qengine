## _section_guide
Every strategy is a Python class that extends Strategy. Create one via the New Strategy button or AI Generate. Each strategy lives in strategies/YourName/__init__.py.

## example_code
```python
# strategies/ExampleStrategy/__init__.py
import qengine.indicators as ta
from qengine.strategies import Strategy

class ExampleStrategy(Strategy):
    """EMA crossover strategy with session filtering and ATR-based stops."""

    def hyperparameters(self):
        return [
            {'name': 'fast_ema',  'type': int,   'min': 5,   'max': 20,  'default': 8},
            {'name': 'slow_ema',  'type': int,   'min': 15,  'max': 50,  'default': 21},
            {'name': 'risk_pct',  'type': float, 'min': 0.5, 'max': 3.0, 'default': 1.0},
            {'name': 'stop_pips', 'type': int,   'min': 20,  'max': 80,  'default': 40},
            {'name': 'rr_ratio',  'type': float, 'min': 1.0, 'max': 4.0, 'default': 2.0},
        ]

    def before(self):
        # Runs before each candle's logic - compute indicators here
        self.fast = ta.ema(self.candles, self.hp.get('fast_ema', 8))
        self.slow = ta.ema(self.candles, self.hp.get('slow_ema', 21))

    def should_long(self) -> bool:
        # Only trade during active sessions
        if self.session not in ('london', 'new_york', 'overlap'):
            return False
        return self.fast > self.slow and self.price > self.fast

    def go_long(self):
        stop_pips = self.hp.get('stop_pips', 40)
        rr = self.hp.get('rr_ratio', 2.0)
        qty = self.lot_size_for_risk(self.hp.get('risk_pct', 1.0), stop_pips)

        self.buy = qty, self.price
        self.stop_loss = qty, self.price - self.pips_to_price(stop_pips)
        self.take_profit = qty, self.price + self.pips_to_price(stop_pips * rr)

    def should_short(self) -> bool:
        if self.session not in ('london', 'new_york', 'overlap'):
            return False
        return self.fast < self.slow and self.price < self.fast

    def go_short(self):
        stop_pips = self.hp.get('stop_pips', 40)
        rr = self.hp.get('rr_ratio', 2.0)
        qty = self.lot_size_for_risk(self.hp.get('risk_pct', 1.0), stop_pips)

        self.sell = qty, self.price
        self.stop_loss = qty, self.price + self.pips_to_price(stop_pips)
        self.take_profit = qty, self.price - self.pips_to_price(stop_pips * rr)

    def should_cancel_entry(self) -> bool:
        # Cancel pending entries before weekend
        if self.minutes_to_close is not None and self.minutes_to_close < 60:
            return True
        return False

    def filters(self):
        # Additional entry conditions (all must pass)
        return [self.filter_atr_above_minimum]

    def filter_atr_above_minimum(self):
        return ta.atr(self.candles, 14) > self.pips_to_price(5)
```
