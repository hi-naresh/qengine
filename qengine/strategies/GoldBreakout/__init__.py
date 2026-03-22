import qengine.indicators as ta
from qengine.strategies import Strategy


class GoldBreakout(Strategy):
    """XAU-USD (gold) breakout strategy.

    Enters on Donchian channel breakout with ATR-based stops.
    Demonstrates commodity trading with wider stops.
    """

    def hyperparameters(self):
        return [
            {'name': 'channel_period', 'type': int, 'min': 10, 'max': 50, 'default': 20},
            {'name': 'atr_period', 'type': int, 'min': 10, 'max': 30, 'default': 14},
            {'name': 'atr_multiplier', 'type': float, 'min': 1.5, 'max': 4.0, 'default': 2.5},
            {'name': 'risk_pct', 'type': float, 'min': 0.5, 'max': 2.0, 'default': 1.0},
        ]

    @property
    def atr(self):
        return ta.atr(self.candles, self.hp.get('atr_period', 14))

    @property
    def channel_high(self):
        period = self.hp.get('channel_period', 20)
        return ta.highestprice(self.candles, period)

    @property
    def channel_low(self):
        period = self.hp.get('channel_period', 20)
        return ta.lowestprice(self.candles, period)

    def should_long(self) -> bool:
        return self.price > self.channel_high

    def go_long(self):
        atr_mult = self.hp.get('atr_multiplier', 2.5)
        stop_distance = self.atr * atr_mult
        risk_pct = self.hp.get('risk_pct', 1.0)

        stop_pips = self.price_to_pips(stop_distance)
        qty = self.lot_size_for_risk(risk_pct, stop_pips) if stop_pips > 0 else 0.01
        entry = self.price
        stop = entry - stop_distance
        tp = entry + stop_distance * 2

        self.buy = qty, entry
        self.stop_loss = qty, stop
        self.take_profit = qty, tp

    def should_short(self) -> bool:
        return self.price < self.channel_low

    def go_short(self):
        atr_mult = self.hp.get('atr_multiplier', 2.5)
        stop_distance = self.atr * atr_mult
        risk_pct = self.hp.get('risk_pct', 1.0)

        stop_pips = self.price_to_pips(stop_distance)
        qty = self.lot_size_for_risk(risk_pct, stop_pips) if stop_pips > 0 else 0.01
        entry = self.price
        stop = entry + stop_distance
        tp = entry - stop_distance * 2

        self.sell = qty, entry
        self.stop_loss = qty, stop
        self.take_profit = qty, tp

    def should_cancel_entry(self) -> bool:
        return False
