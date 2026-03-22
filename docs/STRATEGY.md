# Strategy Guide

A complete guide to writing trading strategies in QEngine -- from the simplest possible strategy to advanced multi-route hedging systems.

---

## Table of Contents
1. [Quick Start: Your First Strategy](#1-quick-start-your-first-strategy)
2. [Strategy Structure](#2-strategy-structure)
3. [Core Methods (Required)](#3-core-methods-required)
4. [Lifecycle Methods (Optional)](#4-lifecycle-methods-optional)
5. [Properties Reference](#5-properties-reference)
6. [Order Types and Entry Patterns](#6-order-types-and-entry-patterns)
7. [Stop Loss and Take Profit](#7-stop-loss-and-take-profit)
8. [Filters](#8-filters)
9. [Using Indicators](#9-using-indicators)
10. [Hyperparameters and Optimization](#10-hyperparameters-and-optimization)
11. [Multi-Point Orders](#11-multi-point-orders)
12. [Dynamic Position Management](#12-dynamic-position-management)
13. [Multi-Route Strategies](#13-multi-route-strategies)
14. [Forex/CFD-Specific Features](#14-forexcfd-specific-features)
15. [Charting and Visualization](#15-charting-and-visualization)
16. [Logging and Debugging](#16-logging-and-debugging)
17. [Caching](#17-caching)
18. [Complete Example: SurefireHedge](#18-complete-example-surefirehedge)
19. [Indicator Reference](#19-indicator-reference)

---

## 1. Quick Start: Your First Strategy

Create a file `strategies/MyFirstStrategy/__init__.py`:

```python
from qengine.strategies import Strategy
import qengine.indicators as ta


class MyFirstStrategy(Strategy):

    def should_long(self) -> bool:
        # Buy when fast EMA crosses above slow EMA
        fast = ta.ema(self.candles, 10)
        slow = ta.ema(self.candles, 30)
        return fast > slow

    def go_long(self):
        # Enter at current price with full available qty
        qty = self.balance * self.leverage / self.price
        self.buy = qty, self.price
        self.stop_loss = qty, self.price - self.pips_to_price(20)
        self.take_profit = qty, self.price + self.pips_to_price(40)

    def should_short(self) -> bool:
        fast = ta.ema(self.candles, 10)
        slow = ta.ema(self.candles, 30)
        return fast < slow

    def go_short(self):
        qty = self.balance * self.leverage / self.price
        self.sell = qty, self.price
        self.stop_loss = qty, self.price + self.pips_to_price(20)
        self.take_profit = qty, self.price - self.pips_to_price(40)
```

That's a complete, runnable strategy.

---

## 2. Strategy Structure

Every strategy:
- Lives in `strategies/StrategyName/__init__.py`
- Extends the `Strategy` base class
- Must implement `should_long()` and `go_long()`
- Optionally implements `should_short()` and `go_short()`

```python
from qengine.strategies import Strategy


class MyStrategy(Strategy):
    # REQUIRED
    def should_long(self) -> bool: ...
    def go_long(self): ...

    # OPTIONAL (defaults to False / no-op)
    def should_short(self) -> bool: ...
    def go_short(self): ...
```

---

## 3. Core Methods (Required)

### `should_long() -> bool`
Called every candle when position is closed and no entry orders exist. Return `True` to trigger `go_long()`.

```python
def should_long(self) -> bool:
    return ta.rsi(self.candles) < 30
```

### `go_long()`
Set entry, stop loss, and take profit orders for a long position.

```python
def go_long(self):
    qty = 1000   # units to buy
    self.buy = qty, self.price               # entry: (qty, price)
    self.stop_loss = qty, self.price * 0.98  # exit if price drops 2%
    self.take_profit = qty, self.price * 1.04  # exit if price rises 4%
```

### `should_short() -> bool` (optional)
Same as `should_long` but for short positions. Defaults to `False`.

### `go_short()` (optional)
Same as `go_long` but uses `self.sell` instead of `self.buy`.

```python
def go_short(self):
    qty = 1000
    self.sell = qty, self.price
    self.stop_loss = qty, self.price * 1.02
    self.take_profit = qty, self.price * 0.96
```

---

## 4. Lifecycle Methods (Optional)

All of these have default no-op implementations. Override only what you need.

### Execution Hooks
```python
def before(self):
    """Called BEFORE the strategy decision logic each candle."""
    pass

def after(self):
    """Called AFTER the strategy decision logic each candle."""
    pass
```

### Position Events
```python
def on_open_position(self, order):
    """Position just opened. Modify SL/TP here if needed."""
    pass

def on_close_position(self, order, closed_trade):
    """Position just closed. Access trade results via closed_trade."""
    pass

def on_increased_position(self, order):
    """Position size was increased (added to existing position)."""
    pass

def on_reduced_position(self, order):
    """Position size was reduced (partial close)."""
    pass
```

### Position Management
```python
def update_position(self):
    """Called every candle while position is open.
    Use to implement trailing stops, dynamic TP, etc."""
    pass
```

### Cancel Logic
```python
def should_cancel_entry(self) -> bool:
    """Should pending entry orders be cancelled?
    Default: True (cancel on new candle if not yet filled)."""
    return True

def on_cancel(self):
    """Called after entry orders are cancelled."""
    pass
```

### Termination
```python
def before_terminate(self):
    """Called at the end of backtest, before position is force-closed."""
    pass

def terminate(self):
    """Called at the very end of backtest."""
    pass
```

### Multi-Route Events
```python
def on_route_open_position(self, strategy):
    """Another route opened a position."""
    pass

def on_route_close_position(self, strategy):
    """Another route closed a position."""
    pass

def on_route_increased_position(self, strategy):
    """Another route increased its position."""
    pass

def on_route_reduced_position(self, strategy):
    """Another route reduced its position."""
    pass

def on_route_canceled(self, strategy):
    """Another route cancelled its orders."""
    pass
```

---

## 5. Properties Reference

### Price Data
| Property | Type | Description |
|----------|------|-------------|
| `self.price` | `float` | Current close price (cached during execution) |
| `self.open` | `float` | Current candle open |
| `self.close` | `float` | Current candle close |
| `self.high` | `float` | Current candle high |
| `self.low` | `float` | Current candle low |
| `self.volume` | `float` | Current candle volume |
| `self.current_candle` | `np.ndarray` | Full candle array `[time, open, close, high, low, volume]` |
| `self.candles` | `np.ndarray` | All candles for this route (2D array) |

### Account
| Property | Type | Description |
|----------|------|-------------|
| `self.balance` | `float` | Current wallet balance |
| `self.available_margin` | `float` | Available margin |
| `self.leveraged_available_margin` | `float` | Available margin * leverage |
| `self.leverage` | `int` | Current leverage setting |
| `self.fee_rate` | `float` | Exchange fee rate |
| `self.portfolio_value` | `float` | Total portfolio value (balance + positions) |

### Position
| Property | Type | Description |
|----------|------|-------------|
| `self.position` | `Position` | Current position object |
| `self.position.qty` | `float` | Position quantity (+ long, - short, 0 closed) |
| `self.position.entry_price` | `float` | Average entry price |
| `self.position.current_price` | `float` | Latest price |
| `self.position.pnl` | `float` | Unrealized P&L |
| `self.position.pnl_percentage` | `float` | Unrealized P&L as percentage |
| `self.position.value` | `float` | Position value in quote currency |
| `self.position.type` | `str` | `'long'`, `'short'`, or `'close'` |
| `self.position.is_open` | `bool` | Is position open? |
| `self.position.is_close` | `bool` | Is position closed? |
| `self.is_long` | `bool` | Shortcut: position is long |
| `self.is_short` | `bool` | Shortcut: position is short |
| `self.is_open` | `bool` | Shortcut: position is open |
| `self.is_close` | `bool` | Shortcut: position is closed |

### Orders
| Property | Type | Description |
|----------|------|-------------|
| `self.entry_orders` | `list[Order]` | All entry orders for this route |
| `self.exit_orders` | `list[Order]` | All exit orders for this route |
| `self.active_exit_orders` | `list[Order]` | Active exit orders only |
| `self.orders` | `list[Order]` | All orders for this route |

### Trades
| Property | Type | Description |
|----------|------|-------------|
| `self.trades` | `list[ClosedTrade]` | All closed trades |
| `self.trades_count` | `int` | Number of trades |
| `self.metrics` | `dict` | Current performance metrics |

### Time and State
| Property | Type | Description |
|----------|------|-------------|
| `self.time` | `int` | Current timestamp (ms) |
| `self.index` | `int` | Current candle index |
| `self.is_backtesting` | `bool` | In backtest mode? |
| `self.is_livetrading` | `bool` | In live trading mode? |
| `self.is_papertrading` | `bool` | In paper trading mode? |
| `self.is_live` | `bool` | In any live mode? |

### Strategy Info
| Property | Type | Description |
|----------|------|-------------|
| `self.name` | `str` | Strategy class name |
| `self.symbol` | `str` | Trading symbol (e.g., `'EUR-USD'`) |
| `self.exchange` | `str` | Exchange/broker name |
| `self.timeframe` | `str` | Candle timeframe (e.g., `'1h'`) |
| `self.hp` | `dict` | Current hyperparameter values |
| `self.vars` | `dict` | Custom variable storage (persists across candles) |
| `self.shared_vars` | `dict` | Shared between all routes |

### Exit Price Helpers
| Property | Type | Description |
|----------|------|-------------|
| `self.average_entry_price` | `float` | Weighted average entry price |
| `self.average_stop_loss` | `float` | Weighted average SL price |
| `self.average_take_profit` | `float` | Weighted average TP price |

### Forex/CFD Properties
| Property | Type | Description |
|----------|------|-------------|
| `self.spread` | `float` | Current spread (price units) |
| `self.pip_size` | `float` | Pip size for this instrument |
| `self.contract_size` | `float` | Contract size (e.g., 100000) |
| `self.market_is_open` | `bool` | Is market currently open? |
| `self.session` | `str` | Current session: `'tokyo'`, `'london'`, `'new_york'`, `'overlap'`, `'off'` |
| `self.minutes_to_close` | `int` | Minutes until market close |
| `self.swap_long` | `float` | Overnight swap rate (long) |
| `self.swap_short` | `float` | Overnight swap rate (short) |
| `self.asset_class` | `str` | `'forex'`, `'commodity'`, `'index'`, etc. |

---

## 6. Order Types and Entry Patterns

QEngine automatically determines order type from the price you set:

```python
def go_long(self):
    qty = 1000

    # MARKET order (price == current price)
    self.buy = qty, self.price

    # LIMIT order (price < current price for buys)
    self.buy = qty, self.price - 0.0010

    # STOP order (price > current price for buys)
    self.buy = qty, self.price + 0.0010
```

The logic is symmetric for `go_short()` using `self.sell`.

---

## 7. Stop Loss and Take Profit

Set in `go_long()` / `go_short()` alongside the entry:

```python
def go_long(self):
    qty = 1000
    entry = self.price
    self.buy = qty, entry
    self.stop_loss = qty, entry - self.pips_to_price(20)
    self.take_profit = qty, entry + self.pips_to_price(40)
```

### Dynamic Stop Loss (Trailing Stop)
Modify in `update_position()`:

```python
def update_position(self):
    if self.is_long:
        # Trail stop loss to 15 pips below current price
        new_sl = self.price - self.pips_to_price(15)
        # Only move stop loss up, never down
        if new_sl > self.average_stop_loss:
            self.stop_loss = self.position.qty, new_sl
```

### Deferred SL/TP
You can set SL/TP in `on_open_position()` instead:

```python
def go_long(self):
    self.buy = 1000, self.price
    # Don't set SL/TP here

def on_open_position(self, order):
    # Set after position is confirmed open
    self.stop_loss = self.position.qty, self.position.entry_price - self.pips_to_price(20)
    self.take_profit = self.position.qty, self.position.entry_price + self.pips_to_price(40)
```

---

## 8. Filters

Filters run after `go_long()` / `go_short()` but before orders are submitted. If any filter returns `False`, the entry is skipped.

```python
def filters(self) -> list:
    return [
        self.filter_min_volatility,
        self.filter_session_time,
    ]

def filter_min_volatility(self):
    """Only trade when ATR is above 5 pips."""
    atr_value = ta.atr(self.candles, 14)
    return self.price_to_pips(atr_value) > 5

def filter_session_time(self):
    """Only trade during London or New York sessions."""
    return self.session in ('london', 'new_york', 'overlap')
```

> **Important**: Pass method references without `()`. Correct: `self.my_filter`. Wrong: `self.my_filter()`.

---

## 9. Using Indicators

Import the indicators module:
```python
import qengine.indicators as ta
```

All indicators take `candles` (a 2D numpy array) as the first argument:

```python
def should_long(self) -> bool:
    rsi = ta.rsi(self.candles, period=14)
    macd_result = ta.macd(self.candles)  # returns (macd, signal, histogram)
    upper, middle, lower = ta.bollinger_bands(self.candles)
    atr_value = ta.atr(self.candles, period=14)

    return rsi < 30 and self.price < lower
```

### Using Candles from Other Timeframes/Symbols

```python
def should_long(self) -> bool:
    # Get 4h candles for the same symbol
    candles_4h = self.get_candles(self.exchange, self.symbol, '4h')
    trend_rsi = ta.rsi(candles_4h, 14)

    # Get candles for a different symbol (must be in data_routes)
    gold_candles = self.get_candles(self.exchange, 'XAU-USD', '1h')
    gold_rsi = ta.rsi(gold_candles, 14)

    return trend_rsi > 50 and gold_rsi < 40
```

### Common Indicators
```python
# Moving Averages
ta.sma(candles, period=20)       # Simple
ta.ema(candles, period=20)       # Exponential
ta.wma(candles, period=20)       # Weighted
ta.hma(candles, period=20)       # Hull
ta.dema(candles, period=20)      # Double Exponential
ta.tema(candles, period=20)      # Triple Exponential
ta.kama(candles, period=20)      # Kaufman Adaptive

# Oscillators
ta.rsi(candles, period=14)                  # RSI
ta.stochastic(candles, fastk=14, slowk=3)   # Stochastic (k, d)
ta.cci(candles, period=20)                  # CCI
ta.willr(candles, period=14)                # Williams %R
ta.mfi(candles, period=14)                  # Money Flow Index
ta.ao(candles)                              # Awesome Oscillator

# Trend
ta.macd(candles, fast=12, slow=26, signal=9)  # (macd, signal, hist)
ta.adx(candles, period=14)                     # ADX
ta.supertrend(candles, period=10, factor=3)    # (trend, direction)
ta.ichimoku_cloud(candles)                     # Ichimoku components
ta.aroon(candles, period=14)                   # (up, down)

# Volatility
ta.atr(candles, period=14)                    # Average True Range
ta.bollinger_bands(candles, period=20, devup=2, devdn=2)  # (upper, mid, lower)
ta.keltner(candles, period=20, multiplier=1.5) # Keltner channels
ta.donchian(candles, period=20)               # (upper, lower)

# Volume
ta.obv(candles)                   # On-Balance Volume
ta.ad(candles)                    # Accumulation/Distribution
ta.vwap(candles)                  # Volume-Weighted Average Price
```

175+ indicators available total. See `qengine/indicators/` for the complete list.

---

## 10. Hyperparameters and Optimization

Define tunable parameters that the optimizer can search:

```python
def hyperparameters(self) -> list:
    return [
        {'name': 'rsi_period',    'type': int,   'min': 5,   'max': 30,  'default': 14},
        {'name': 'rsi_threshold', 'type': float, 'min': 20,  'max': 40,  'default': 30},
        {'name': 'atr_period',    'type': int,   'min': 7,   'max': 28,  'default': 14},
        {'name': 'direction',     'type': str,   'options': ['long', 'short', 'both'], 'default': 'both'},
    ]
```

Access values via `self.hp`:

```python
def should_long(self) -> bool:
    rsi = ta.rsi(self.candles, self.hp['rsi_period'])
    return rsi < self.hp['rsi_threshold']
```

### Hyperparameter Types
| Type | Fields | Description |
|------|--------|-------------|
| `int` | `min`, `max`, `default` | Integer range |
| `float` | `min`, `max`, `default` | Float range |
| `str` (categorical) | `options`, `default` | Pick from list |

When not running optimization, `self.hp` uses the `default` values.

---

## 11. Multi-Point Orders

Enter or exit at multiple price levels:

```python
def go_long(self):
    qty = 1000

    # Enter in two tranches
    self.buy = [
        (qty * 0.5, self.price),           # 50% at market
        (qty * 0.5, self.price - 0.0005),  # 50% limit below
    ]

    # Take profit at two levels
    self.take_profit = [
        (qty * 0.5, self.price + 0.0020),  # close half at +20 pips
        (qty * 0.5, self.price + 0.0040),  # close rest at +40 pips
    ]

    # Single stop loss
    self.stop_loss = qty, self.price - 0.0015
```

---

## 12. Dynamic Position Management

### Increasing Position (Pyramiding)
```python
def update_position(self):
    # Add to position if price moved in our favor
    if self.is_long and self.increased_count < 3:
        if self.price > self.position.entry_price + self.pips_to_price(10):
            add_qty = 500
            self.buy = [
                (self.position.qty + add_qty, self.price)
            ]
```

### Reducing Position (Partial Close)
```python
def update_position(self):
    if self.is_long and self.reduced_count == 0:
        # Close half at +20 pips profit
        if self.price > self.position.entry_price + self.pips_to_price(20):
            half = abs(self.position.qty) / 2
            self.take_profit = half, self.price
```

### Immediate Close (Liquidate)
```python
def update_position(self):
    # Emergency exit
    if some_condition:
        self.liquidate()
```

`self.liquidate()` closes the entire position at market price immediately.

---

## 13. Multi-Route Strategies

Trade multiple symbols simultaneously and react to events on other routes:

```python
class CorrelatedStrategy(Strategy):

    def should_long(self) -> bool:
        # Only go long EUR-USD if gold is also bullish
        for r in self.routes:
            if r.symbol == 'XAU-USD' and r.strategy.is_long:
                return ta.rsi(self.candles) < 40
        return False

    def on_route_open_position(self, strategy):
        """React when another route opens a position."""
        if strategy.symbol == 'GBP-USD':
            # Hedge: if GBP-USD goes long, go short here
            pass

    def on_route_close_position(self, strategy):
        """React when another route closes."""
        pass
```

### Shared Variables
Share data between routes:
```python
# In route A:
self.shared_vars['signal'] = 'bullish'

# In route B:
if self.shared_vars.get('signal') == 'bullish':
    ...
```

---

## 14. Forex/CFD-Specific Features

### Pip-Based Calculations
```python
# Convert pips to price distance
distance = self.pips_to_price(20)  # 20 pips = 0.0020 for EUR-USD

# Convert price distance to pips
pips = self.price_to_pips(0.0020)  # = 20 for EUR-USD

# Risk-based position sizing
# "Risk 1% of balance with a 20-pip stop loss"
qty = self.lot_size_for_risk(risk_pct=1.0, stop_pips=20)
```

### Market Session Awareness
```python
def should_long(self) -> bool:
    # Only trade during London session
    if self.session != 'london':
        return False
    # Don't trade if market closes soon
    if self.minutes_to_close and self.minutes_to_close < 60:
        return False
    return self.my_signal()
```

### Spread Awareness
```python
def filters(self) -> list:
    return [self.filter_spread]

def filter_spread(self):
    """Skip trades when spread is too wide."""
    spread_pips = self.price_to_pips(self.spread)
    return spread_pips < 3  # max 3 pip spread
```

---

## 15. Charting and Visualization

Add custom lines to the backtest chart:

### Lines on Candle Chart
```python
def after(self):
    # Plot EMA on the candle chart
    ema_val = ta.ema(self.candles, 20)
    self.add_line_to_candle_chart('EMA 20', ema_val, color='#2196F3')
```

### Horizontal Lines
```python
def on_open_position(self, order):
    self.add_horizontal_line_to_candle_chart(
        'Stop Loss', self.average_stop_loss, color='#e91e63', line_style='dotted'
    )
```

### Extra Charts (Separate Panels)
```python
def after(self):
    rsi = ta.rsi(self.candles, 14)
    self.add_extra_line_chart('RSI', 'RSI 14', rsi, color='#FF9800')
    self.add_horizontal_line_to_extra_chart('RSI', 'Overbought', 70, color='red', line_style='dotted')
    self.add_horizontal_line_to_extra_chart('RSI', 'Oversold', 30, color='green', line_style='dotted')
```

### Chart Labels for Orders
```python
def go_long(self):
    self.chart_label = 'Signal A'  # Shows on the chart marker
    self.buy = 1000, self.price
    ...
```

---

## 16. Logging and Debugging

```python
# Log a message (visible in backtest results and live logs)
self.log('RSI crossed below 30, entering long')

# Log with error level
self.log('Something unexpected happened', log_type='error')

# Log and send notification (live mode only)
self.log('Position opened!', send_notification=True)
```

### Watch List (Live Mode Monitoring)
```python
def watch_list(self) -> list:
    return [
        ['RSI', round(ta.rsi(self.candles, 14), 2)],
        ['Position', self.position.type],
        ['PnL', round(self.position.pnl, 2)],
        ['Balance', round(self.balance, 2)],
    ]
```

---

## 17. Caching

Use the `@cached` decorator for expensive indicator calculations:

```python
from qengine.services.cache import cached

class MyStrategy(Strategy):

    @property
    @cached
    def rsi_value(self):
        """Calculated once per candle, then cached."""
        return ta.rsi(self.candles, 14)

    def should_long(self) -> bool:
        return self.rsi_value < 30

    def go_long(self):
        # Uses cached value, no recalculation
        if self.rsi_value < 20:
            qty = 2000  # extra size for strong signal
        else:
            qty = 1000
        self.buy = qty, self.price
        ...
```

Cache is automatically cleared after each candle execution cycle.

---

## 18. Complete Example: SurefireHedge

A full martingale hedging strategy that demonstrates advanced features:

```python
from qengine.strategies import Strategy
import qengine.helpers as jh


class SurefireHedge(Strategy):

    def __init__(self):
        super().__init__()
        self.vars['level'] = 0           # Current hedge level
        self.vars['next_dir'] = None     # Next trade direction after SL hit
        self.vars['cycle_active'] = False
        self.vars['session_number'] = 0
        self.vars['order_in_session'] = 0
        self.vars['cooldown_until'] = 0

    def hyperparameters(self):
        return [
            {'name': 'direction',      'type': str,   'options': ['long', 'short'], 'default': 'long'},
            {'name': 'initial_size',   'type': float, 'min': 0.1,  'max': 50.0,  'default': 1.0},
            {'name': 'multiplier',     'type': float, 'min': 1.1,  'max': 5.0,   'default': 2.0},
            {'name': 'tp_distance',    'type': float, 'min': 3,    'max': 200,   'default': 20},
            {'name': 'hedge_distance', 'type': float, 'min': 1,    'max': 200,   'default': 10},
            {'name': 'max_levels',     'type': int,   'min': 1,    'max': 10,    'default': 6},
        ]

    def _base_qty(self) -> float:
        margin = self.balance * self.hp['initial_size'] / 100
        return margin * self.leverage / self.price

    def _size_for_level(self, level: int) -> float:
        return self._base_qty() * (self.hp['multiplier'] ** level)

    # -- Entry Conditions --

    def should_long(self) -> bool:
        if self.current_candle[0] <= self.vars['cooldown_until']:
            return False
        if self.vars['level'] >= self.hp['max_levels']:
            return False
        direction = self.vars['next_dir'] or self.hp['direction']
        return direction == 'long'

    def should_short(self) -> bool:
        if self.current_candle[0] <= self.vars['cooldown_until']:
            return False
        if self.vars['level'] >= self.hp['max_levels']:
            return False
        direction = self.vars['next_dir'] or self.hp['direction']
        return direction == 'short'

    # -- Entry Execution --

    def go_long(self):
        level = self.vars['level']
        size = self._size_for_level(level)
        entry = self.price
        tp = entry + self.pips_to_price(self.hp['tp_distance'])
        sl = entry - self.pips_to_price(self.hp['hedge_distance'])

        self.buy = size, entry
        self.take_profit = size, tp
        self.stop_loss = size, sl
        self.vars['cycle_active'] = True

    def go_short(self):
        level = self.vars['level']
        size = self._size_for_level(level)
        entry = self.price
        tp = entry - self.pips_to_price(self.hp['tp_distance'])
        sl = entry + self.pips_to_price(self.hp['hedge_distance'])

        self.sell = size, entry
        self.take_profit = size, tp
        self.stop_loss = size, sl
        self.vars['cycle_active'] = True

    # -- Position Close Handling --

    def on_close_position(self, order, closed_trade):
        if order.is_take_profit:
            # TP hit: cycle complete, reset
            self.vars['level'] = 0
            self.vars['next_dir'] = None
            self.vars['cycle_active'] = False
            self.vars['cooldown_until'] = self.current_candle[0]
        elif order.is_stop_loss:
            # SL hit: reverse and increase level
            current = self.vars['next_dir'] or self.hp['direction']
            self.vars['next_dir'] = 'short' if current == 'long' else 'long'
            self.vars['level'] += 1

    def update_position(self):
        pass

    def watch_list(self) -> list:
        return [
            ['level', self.vars['level']],
            ['cycle_active', self.vars['cycle_active']],
            ['balance', round(self.balance, 2)],
        ]
```

---

## 19. Indicator Reference

QEngine includes **175+ technical indicators**. Here are the categories:

### Moving Averages (25+)
`sma`, `ema`, `wma`, `dema`, `tema`, `hma`, `kama`, `alma`, `frama`, `jma`, `vwma`, `smma`, `zlema`, `epma`, `fwma`, `hwma`, `cwma`, `sinwma`, `swma`, `pwma`, `sqwma`, `srwma`, `vpwma`, `t3`, `trima`, `vidya`, `mcginley_dynamic`, `wilders`, `rma`

### Oscillators (20+)
`rsi`, `stochastic`, `stochf`, `cci`, `willr`, `mfi`, `ao`, `apo`, `cmo`, `dpo`, `roc`, `rocp`, `rocr`, `mom`, `tsi`, `ppo`, `ift_rsi`, `srsi`, `lrsi`, `fisher`, `wt`

### Trend Indicators (15+)
`macd`, `adx`, `adxr`, `aroon`, `aroonosc`, `supertrend`, `ichimoku_cloud`, `ichimoku_cloud_seq`, `alligator`, `gatorosc`, `di`, `dm`, `dx`, `itrend`, `kst`

### Volatility (15+)
`atr`, `natr`, `bollinger_bands`, `bollinger_bands_width`, `keltner`, `donchian`, `trange`, `chop`, `cvi`, `damiani_volatmeter`, `hurst_exponent`, `ttm_squeeze`, `squeeze_momentum`, `stiffness`, `stddev`

### Volume (10+)
`obv`, `ad`, `adosc`, `emv`, `efi`, `kvo`, `mwdx`, `nvi`, `pvi`, `vpt`, `vwap`, `volume`, `vosc`, `vpci`

### Support/Resistance
`pivot`, `support_resistance_with_break`, `sar`

### Statistical
`linearreg`, `linearreg_slope`, `linearreg_angle`, `linearreg_intercept`, `beta`, `correl`, `kurtosis`, `skew`, `zscore`, `tsf`

### Signal Processing
`bandpass`, `high_pass`, `high_pass_2_pole`, `supersmoother`, `supersmoother_3_pole`, `roofing`, `decycler`, `correlation_cycle`, `gauss`, `reflex`, `trendflex`, `edcf`, `voss`

### Custom
`heikin_ashi_candles`, `hull_suit`, `ttm_trend`, `waddah_attr_explosion`, `stc`, `kdj`

---

Previous: [HIGH-LEVEL-LOGIC.md](./HIGH-LEVEL-LOGIC.md) | Next: [README.md](./README.md)
