# GTSBotPilot Pipeline Design

**Based on:** Rundo et al., "Grid Trading System Robot (GTSbot): A Novel Mathematical Algorithm for Trading FX Market" (Appl. Sci. 2019, 9, 1796)

**Type:** Pipeline overlay (Approach A) — wraps existing strategies (e.g., SurefireHedge)

**Location:** `pipelines/_shared/GTSBotPilot/`

---

## Architecture Overview

The strategy handles pure grid mechanics (hedge levels, ticket management, order execution). The pipeline provides all market intelligence:

- **When** to enter (trend/momentum signal)
- **Whether** grid spacing allows it (grid enforcement)
- **When** to close everything (basket profit target)

### Paper → Pipeline Mapping

| Paper Block | Pipeline Layer | Hook(s) |
|---|---|---|
| Regression Network SCG + TCB | TrendFilter | `on_before` + `gate_entry` |
| Grid System Manager (GSM) | GridManager | `on_before` + `gate_entry` + `filter_order` |
| Basket Equity System Manager (BESM) | BasketManager | `on_before` + `suggest_exit` |

---

## Layer 1: TrendFilter

**Hooks:** `on_before()`, `gate_entry()`

**Purpose:** Detect momentum/trend direction, block entries in choppy/null-trend conditions.

### How It Works

The paper uses an SCG neural network to predict next close price, then computes derivatives on the prediction. The NN's actual role is **noise reduction** — its regression performance is "not optimal" but it smooths the price series so derivatives produce clean signals.

We replace the NN with EMA smoothing (same denoising effect, zero training overhead).

1. Smooth close prices via EMA (period configurable, default 14)
2. Compute 1st derivative (momentum): `d1 = smoothed(k) - smoothed(k-1)`
3. Compute 2nd derivative (acceleration): `d2 = smoothed(k) - 2*smoothed(k-1) + smoothed(k-2)`
4. Classify trend:

```
Long Trend    if d1 > delta  AND d2 > 0
Short Trend   if d1 < -delta AND d2 < 0
Null Trend    otherwise
```

Where `delta` is a threshold (default: broker spread) filtering weak signals.

### gate_entry() Logic

- If trend is **Null** → block entry (return False)
- If trend is **Long** and strategy wants long → allow
- If trend is **Short** and strategy wants short → allow
- If trend direction conflicts with strategy direction → block
- Exposes `self.current_trend` for other layers to read

---

## Layer 2: GridManager

**Hooks:** `on_before()`, `gate_entry()`, `filter_order()`

**Purpose:** Enforce grid spacing constraints. Track all open trades and ensure proper time/price distance between same-direction trades.

### How It Works

Tracks all open tickets with their entry price, entry time (candle index), and direction.

Enforces three constraints before allowing a new trade:

1. **x-threshold (time spacing):** Min number of candles since last same-direction trade. Default: 15 candles. Prevents rapid-fire entries in the same direction.

2. **y-threshold (price spacing):** Min price distance from all open same-direction trades. Dynamic — scaled by ATR to adapt to volatility. Default: `0.5 * ATR(14)`. Prevents clustering trades at similar price levels.

3. **Max operations:** Cap on total simultaneous open trades. Default: 13 (odd number to avoid perfect hedging neutrality, per paper).

### Adaptive Thresholds

When `adaptive: True` (default):
- x-threshold scales with inverse volatility (wider spacing in calm markets where false signals cluster)
- y-threshold scales with ATR (wider spacing in volatile markets)

### gate_entry() Logic

```
if total_open_trades >= max_operations → block
if candles_since_last_same_direction < x_threshold → block
if min_price_distance_to_same_direction < y_threshold → block
otherwise → allow
```

### filter_order() Logic

Same checks applied to individual orders. Returns None to cancel orders that violate grid constraints.

### Ticket Tracking

- `on_open_position()` — register new ticket (price, time, direction)
- `on_cycle_end()` — clean up closed tickets
- Reads strategy's CFD tickets if available, falls back to position tracking

---

## Layer 3: BasketManager

**Hooks:** `on_before()`, `suggest_exit()`

**Purpose:** Monitor cumulative P&L across all open tickets. Close everything when basket profit target is reached.

### How It Works

1. Each candle, compute total unrealized P&L across all open tickets
2. Compare against target profit threshold
3. When `basket_pnl >= target_profit` → return `{'action': 'close_all'}`

### Target Profit

- Can be fixed amount or dynamic (ATR-scaled)
- Default: `2.0 * ATR(14)` — adapts to current volatility
- Paper uses no stop loss (grid compensates drawdown), but we track max drawdown as a safety metric

### Drawdown Monitoring

- Track peak equity and current drawdown
- Expose via `get_stats()` for dashboard monitoring
- Optional: emergency close if drawdown exceeds critical threshold (configurable, disabled by default)

---

## Configuration

```python
DEFAULT_CONFIG = {
    'trend_filter': {
        'smoothing_period': 14,          # EMA period for price denoising
        'delta_threshold': 'spread',     # min 1st derivative magnitude ('spread' or float)
        'require_direction_match': True, # block if trend opposes strategy direction
    },
    'grid_manager': {
        'x_threshold': 15,               # min candles between same-direction trades
        'y_threshold_atr_mult': 0.5,     # min price distance as ATR(14) multiple
        'max_operations': 13,            # max simultaneous open trades (odd number)
        'adaptive': True,                # dynamically scale thresholds with volatility
    },
    'basket_manager': {
        'target_profit_atr_mult': 2.0,   # basket TP as ATR(14) multiple
        'monitor_drawdown': True,        # track and expose drawdown metrics
        'emergency_dd_pct': None,        # optional: close all if DD exceeds this % (disabled)
    },
}
```

---

## Data Flow

```
Candle arrives
  → TrendFilter.on_before(): smooth price, compute derivatives, classify trend
  → GridManager.on_before(): update open ticket tracking, compute dynamic thresholds
  → BasketManager.on_before(): compute basket P&L, check target

Strategy fires should_long/should_short (pure mechanics, no market intelligence)
  → TrendFilter.gate_entry(): trend confirmed and matches direction? → allow/block
  → GridManager.gate_entry(): spacing ok? max ops ok? → allow/block
  (Both must allow — AND logic via PipelineStack)

Strategy places order
  → GridManager.filter_order(): final grid constraint check on order

BasketManager.suggest_exit(): basket profit >= target? → close_all
```

---

## Stats & UI

### get_stats()

```python
{
    'trend_filter': {
        'current_trend': 'long' | 'short' | 'null',
        'd1': float,           # 1st derivative value
        'd2': float,           # 2nd derivative value
        'entries_blocked': int,
        'trend_accuracy': float,
    },
    'grid_manager': {
        'open_long_count': int,
        'open_short_count': int,
        'total_open': int,
        'current_x_threshold': int,
        'current_y_threshold': float,
        'entries_blocked': int,
    },
    'basket_manager': {
        'basket_pnl': float,
        'target_profit': float,
        'pnl_pct_of_target': float,
        'peak_equity': float,
        'current_drawdown': float,
        'baskets_closed': int,
    },
}
```

---

## File Structure

```
pipelines/_shared/GTSBotPilot/
├── __init__.py          # Main pipeline: GTSBotPilot class with 3 layers
├── config.py            # DEFAULT_CONFIG + config merging
├── models/              # (reserved for future trained model artifacts)
└── DESIGN.md            # This document
```

---

## Key Design Decisions

1. **EMA smoothing instead of NN** — The paper's NN is functionally a non-linear smoother. EMA achieves the same denoising for derivative computation without training overhead.

2. **Pipeline overlay, not standalone strategy** — Uses existing strategy HPs and grid mechanics. Pipeline adds intelligence layer on top.

3. **Strategy has no smart signals** — The pipeline is the brain (trend detection, grid enforcement, basket management). The strategy is pure execution mechanics.

4. **Dynamic ATR-scaled thresholds** — Paper uses fixed thresholds. We adapt to volatility for robustness across market regimes.

5. **Odd max_operations** — Per paper: avoids perfect hedging neutrality where longs = shorts.

6. **No stop loss by design** — Grid strategy compensates drawdown via position averaging. Emergency DD cutoff available but disabled by default.
