import qengine.indicators as ta
from qengine.strategies import Strategy


class ForexMA(Strategy):
    """Example: Simple forex moving average crossover strategy.

    Demonstrates forex-specific properties:
    - self.session for session-based trading
    - self.lot_size_for_risk() for pip-based position sizing
    - self.pips_to_price() for stop/TP calculation
    - self.minutes_to_close for weekend risk management
    """

    def hyperparameters(self):
        return [
            {'name': 'fast_period', 'type': int, 'min': 10, 'max': 50, 'default': 20},
            {'name': 'slow_period', 'type': int, 'min': 30, 'max': 100, 'default': 50},
            {'name': 'risk_pct', 'type': float, 'min': 0.5, 'max': 3.0, 'default': 1.0},
            {'name': 'stop_pips', 'type': int, 'min': 20, 'max': 100, 'default': 50},
            {'name': 'rr_ratio', 'type': float, 'min': 1.0, 'max': 4.0, 'default': 2.0},
        ]

    @property
    def fast_period(self):
        return self.hp.get('fast_period', 20)

    @property
    def slow_period(self):
        return self.hp.get('slow_period', 50)

    def should_long(self) -> bool:
        if self.session not in ('london', 'new_york', 'overlap'):
            return False

        fast = ta.sma(self.candles, self.fast_period)
        slow = ta.sma(self.candles, self.slow_period)
        return fast > slow and self.price > fast

    def go_long(self):
        risk_pct = self.hp.get('risk_pct', 1.0)
        stop_pips = self.hp.get('stop_pips', 50)
        rr = self.hp.get('rr_ratio', 2.0)

        qty = self.lot_size_for_risk(risk_pct=risk_pct, stop_pips=stop_pips)
        entry = self.price
        stop = entry - self.pips_to_price(stop_pips)
        tp = entry + self.pips_to_price(stop_pips * rr)

        self.buy = qty, entry
        self.stop_loss = qty, stop
        self.take_profit = qty, tp

    def should_short(self) -> bool:
        if self.session not in ('london', 'new_york', 'overlap'):
            return False

        fast = ta.sma(self.candles, self.fast_period)
        slow = ta.sma(self.candles, self.slow_period)
        return fast < slow and self.price < fast

    def go_short(self):
        risk_pct = self.hp.get('risk_pct', 1.0)
        stop_pips = self.hp.get('stop_pips', 50)
        rr = self.hp.get('rr_ratio', 2.0)

        qty = self.lot_size_for_risk(risk_pct=risk_pct, stop_pips=stop_pips)
        entry = self.price
        stop = entry + self.pips_to_price(stop_pips)
        tp = entry - self.pips_to_price(stop_pips * rr)

        self.sell = qty, entry
        self.stop_loss = qty, stop
        self.take_profit = qty, tp

    def should_cancel_entry(self) -> bool:
        # Close before weekend (within 60 minutes of market close)
        if self.minutes_to_close is not None and self.minutes_to_close < 60:
            return True
        return False
