## _section_guide
Strategies use lifecycle methods to define trading logic. Two methods are required: should_long() and go_long(). All others are optional and let you handle shorts, position updates, events, and filters.

## required_methods
- should_long(self) -> bool | Return True when conditions are met to open a long position
- go_long(self) | Set <code class="text-surface-400">self.buy</code>, <code class="text-surface-400">self.stop_loss</code>, <code class="text-surface-400">self.take_profit</code> as <code class="text-surface-400">(qty, price)</code> tuples

## optional_methods
- should_short(self) -> bool | Return True to enter short (default: False)
- go_short(self) | Set self.sell, self.stop_loss, self.take_profit for short entry
- before(self) | Runs BEFORE each candle logic — precompute indicators here
- after(self) | Runs AFTER each candle logic
- update_position(self) | Called when position is open — update TP/SL dynamically
- should_cancel_entry(self) -> bool | Cancel pending orders on new candle (default: True)
- on_open_position(self, order) | Called when position opens
- on_close_position(self, order, trade) | Called when position closes with ClosedTrade
- on_increased_position(self, order) | Called when position size increases
- on_reduced_position(self, order) | Called when position size decreases
- on_ticket_opened(self, order) | CFD mode: called when a new ticket opens
- on_ticket_closed(self, order) | CFD mode: called when a ticket closes
- on_cancel(self) | Called after all orders are cancelled
- filters(self) -> list | Return list of filter methods for entry validation
- hyperparameters(self) -> list | Return list of HP dicts for optimization
- watch_list(self) -> list | Return [{key, value}] dicts for live monitoring
- terminate(self) | Called at backtest end / strategy termination
- before_terminate(self) | Called before termination
- dna(self) -> str | Return DNA string for strategy identification

## order_format
Market Order:
```python
self.buy = qty, self.price          # market buy
self.stop_loss = qty, stop_price    # stop loss
self.take_profit = qty, tp_price    # take profit
```

Limit / Stop Order:
```python
self.buy = qty, limit_price         # limit buy (below current)
self.buy = qty, stop_price          # stop buy (above current)
```

Multiple Orders (scale in):
```python
self.buy = [
    (qty1, price1),
    (qty2, price2),
]
```

## filters_example
```python
def filters(self):
    return [
        self.is_volatile_enough,
        self.not_near_weekend,
    ]

def is_volatile_enough(self):
    return ta.atr(self.candles, 14) > 0.001

def not_near_weekend(self):
    return self.minutes_to_close is None \
        or self.minutes_to_close > 120
```

## chart_annotations
- self.chart_label | Label on order markers
- self._add_line_to_candle_chart_values[] | Indicator line on candle chart
- self._add_horizontal_line_to_candle_chart_values[] | Horizontal line
- self._add_extra_line_chart_values[] | Separate indicator pane
