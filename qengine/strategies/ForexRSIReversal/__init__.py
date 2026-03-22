import qengine.indicators as ta
from qengine.strategies import Strategy


class ForexRSIReversal(Strategy):
    """GBP-JPY RSI reversal with session filter.

    Buys on oversold RSI during London/NY sessions,
    sells on overbought RSI. Uses pip-based risk management.
    """

    def hyperparameters(self):
        return [
            {'name': 'rsi_period', 'type': int, 'min': 7, 'max': 21, 'default': 14},
            {'name': 'oversold', 'type': int, 'min': 20, 'max': 35, 'default': 30},
            {'name': 'overbought', 'type': int, 'min': 65, 'max': 80, 'default': 70},
            {'name': 'risk_pct', 'type': float, 'min': 0.5, 'max': 2.0, 'default': 1.0},
            {'name': 'stop_pips', 'type': int, 'min': 30, 'max': 80, 'default': 40},
        ]

    @property
    def rsi(self):
        return ta.rsi(self.candles, self.hp.get('rsi_period', 14))

    def should_long(self) -> bool:
        if self.session not in ('london', 'new_york', 'overlap'):
            return False
        return self.rsi < self.hp.get('oversold', 30)

    def go_long(self):
        stop_pips = self.hp.get('stop_pips', 40)
        qty = self.lot_size_for_risk(self.hp.get('risk_pct', 1.0), stop_pips)
        entry = self.price
        stop = entry - self.pips_to_price(stop_pips)
        tp = entry + self.pips_to_price(stop_pips * 2)

        self.buy = qty, entry
        self.stop_loss = qty, stop
        self.take_profit = qty, tp

    def should_short(self) -> bool:
        if self.session not in ('london', 'new_york', 'overlap'):
            return False
        return self.rsi > self.hp.get('overbought', 70)

    def go_short(self):
        stop_pips = self.hp.get('stop_pips', 40)
        qty = self.lot_size_for_risk(self.hp.get('risk_pct', 1.0), stop_pips)
        entry = self.price
        stop = entry + self.pips_to_price(stop_pips)
        tp = entry - self.pips_to_price(stop_pips * 2)

        self.sell = qty, entry
        self.stop_loss = qty, stop
        self.take_profit = qty, tp

    def should_cancel_entry(self) -> bool:
        return False
