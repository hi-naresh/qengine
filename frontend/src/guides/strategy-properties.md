## _section_guide
Strategy properties give you access to price data, position state, account balance, and forex-specific helpers. Access them with self.property_name inside any strategy method.

## price_candle
- price | Current price (close)
- open | Current candle open
- close | Current candle close
- high | Current candle high
- low | Current candle low
- volume | Current candle volume
- candles | All historical candles (numpy array)
- current_candle | Current candle array [timestamp, open, close, high, low, volume]
- index | Current candle index
- timeframe | Strategy timeframe string

## position_balance
- is_long | Position is long (bool)
- is_short | Position is short (bool)
- is_open | Position is open (bool)
- is_close | Position is closed (bool)
- balance | Current wallet balance
- available_margin | Available margin for new trades
- leverage | Current leverage setting
- fee_rate | Exchange fee rate
- portfolio_value | Total portfolio value (balance + unrealized PnL)
- position | Position object with qty, entry_price, pnl, etc.

## forex_cfd
- self.session | Current session: tokyo, london, new_york, overlap, off
- self.spread | Current bid-ask spread
- self.pip_size | Pip size (e.g. 0.0001 for EUR-USD)
- self.market_is_open | Whether market is currently open (bool)
- self.minutes_to_close | Minutes until market close
- self.swap_long | Overnight swap rate for long positions
- self.swap_short | Overnight swap rate for short positions
- self.contract_size | Contract size (e.g. 100000 for standard forex lot)
- self.pips_to_price(n) | Convert pip count to price difference
- self.price_to_pips(d) | Convert price difference to pips
- self.lot_size_for_risk(%, pips) | Calculate lot size for a given risk % and stop in pips
- self.asset_class | Asset class: forex, commodity, index

## hyperparameters_usage
Define tunable parameters for optimization. Access via self.hp['name'] or self.hp.get('name', default).

```python
def hyperparameters(self):
    return [
        {'name': 'period', 'type': 'int', 'min': 5, 'max': 100, 'default': 14},
        {'name': 'threshold', 'type': 'float', 'min': 0.1, 'max': 5.0, 'default': 1.0},
        {'name': 'mode', 'type': 'str', 'options': ['conservative', 'aggressive'], 'default': 'conservative'},
    ]
```

Supported types: int, float, str. For strings, provide options list. Hyperparameters are auto-loaded in Playground.
