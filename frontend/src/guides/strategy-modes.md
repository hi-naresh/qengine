## _section_guide
QEngine supports three exchange types, each with different position handling. The type is auto-detected from your broker configuration. Use self.exchange_type to check at runtime.

## cfd
CFD (Forex/CFD) — OANDA, IG Markets, IBKR

True hedging with independent tickets. Multiple positions in the same symbol simultaneously. Each ticket has its own entry price, quantity, and P&L.

Key properties and methods:
- self.hedge_mode = True
- self.close_all_tickets(price) — close all open tickets at given price
- self.close_ticket(id, price) — close a specific ticket
- on_ticket_opened(self, order) — callback when ticket opens
- on_ticket_closed(self, order) — callback when ticket closes

## futures
Futures (Crypto Futures) — netting mode

One position per symbol. Supports leverage and funding rates. New orders in the same direction increase the position; opposite direction reduces or reverses it.

Key properties:
- self.leverage — current leverage multiplier
- self.mark_price — current mark price (for liquidation)
- self.funding_rate — current funding rate

## spot
Spot (Crypto Spot) — simplest mode

No leverage, no shorting. Buy and sell actual assets. Position is simply the amount of asset held.

Key properties:
- self.is_spot_trading — True when in spot mode
- self.balance — available quote currency
- self.portfolio_value — total value in quote currency

## detection
Exchange type is auto-detected from your broker. Check at runtime:
- self.exchange_type returns 'cfd', 'futures', or 'spot'
- self.is_cfd_mode — True for CFD brokers
- self.is_futures_trading — True for futures
- self.is_spot_trading — True for spot

## cached_decorator
```python
from qengine.services.cache import cached

class MyStrategy(Strategy):
    @cached
    def atr_value(self):
        return ta.atr(self.candles, 14)

    def should_long(self):
        # computed only once per candle thanks to @cached
        return self.price > self.atr_value * 100
```
