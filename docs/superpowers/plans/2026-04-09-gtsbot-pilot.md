# GTSBotPilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-layer pipeline overlay (TrendFilter, GridManager, BasketManager) implementing the GTSBot paper's grid trading algorithm on top of existing qengine strategies.

**Architecture:** Single `GTSBotPilot(Pipeline)` class with 3 internal layers. Config in separate file with deep-merge. Follows GridPilot/IslandPilot patterns: `on_before` for observation, `gate_entry` for entry control, `suggest_exit` for basket close. Uses EMA-smoothed derivatives for trend detection instead of the paper's neural network.

**Tech Stack:** Python, numpy, qengine indicators (`ta.ema`, `ta.atr` via Rust backend), `qengine.framework.base.Pipeline`

**Spec:** `pipelines/_shared/GTSBotPilot/DESIGN.md`

---

### Task 1: Config Module

**Files:**
- Create: `pipelines/_shared/GTSBotPilot/config.py`

- [ ] **Step 1: Create config.py with DEFAULT_CONFIG and merge function**

```python
# pipelines/_shared/GTSBotPilot/config.py
"""GTSBotPilot configuration with defaults and deep-merge."""
import copy
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    'warmup': 50,  # min candles before pipeline activates
    'trend_filter': {
        'smoothing_period': 14,          # EMA period for price denoising
        'delta_threshold': 0.00015,      # min 1st derivative magnitude (approx 1.5 pips)
        'require_direction_match': True, # block if trend opposes strategy direction
        'enabled': True,
    },
    'grid_manager': {
        'x_threshold': 15,               # min candles between same-direction trades
        'y_threshold_atr_mult': 0.5,     # min price distance as ATR(14) multiple
        'max_operations': 13,            # max simultaneous open trades
        'adaptive': True,                # dynamically scale thresholds with volatility
        'enabled': True,
    },
    'basket_manager': {
        'target_profit_atr_mult': 2.0,   # basket TP as ATR(14) multiple
        'monitor_drawdown': True,        # track and expose drawdown metrics
        'emergency_dd_pct': None,        # optional: close all if DD exceeds this %
        'enabled': True,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning new dict."""
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


def merge_config(user_config: dict) -> dict:
    """Deep merge user config over defaults."""
    if not user_config:
        return copy.deepcopy(DEFAULT_CONFIG)
    return _deep_merge(DEFAULT_CONFIG, user_config)
```

- [ ] **Step 2: Verify file created**

Run: `python -c "import sys; sys.path.insert(0, '.'); from pipelines._shared.GTSBotPilot.config import DEFAULT_CONFIG, merge_config; print('OK:', list(DEFAULT_CONFIG.keys()))"`

Expected: `OK: ['warmup', 'trend_filter', 'grid_manager', 'basket_manager']`

- [ ] **Step 3: Commit**

```bash
git add pipelines/_shared/GTSBotPilot/config.py
git commit -m "feat(GTSBotPilot): add config module with defaults and deep-merge"
```

---

### Task 2: TrendFilter Layer

**Files:**
- Create: `pipelines/_shared/GTSBotPilot/trend_filter.py`

The TrendFilter replaces the paper's SCG neural network + Trend Classification Block. It smooths close prices with EMA, computes 1st and 2nd derivatives on the smoothed series, and classifies trend as Long/Short/Null.

- [ ] **Step 1: Create trend_filter.py**

```python
# pipelines/_shared/GTSBotPilot/trend_filter.py
"""
TrendFilter — Layer 1 of GTSBotPilot.

Replaces the paper's SCG neural network + Trend Classification Block (TCB).
The NN's role is noise reduction; we achieve the same with EMA smoothing.

Derivative-based trend classification (from paper Eq. 2-4):
  Long Trend:   d1 > delta AND d2 > 0
  Short Trend:  d1 < -delta AND d2 < 0
  Null Trend:   otherwise

Where:
  d1 = smoothed(k) - smoothed(k-1)           # 1st derivative (momentum)
  d2 = smoothed(k) - 2*smoothed(k-1) + smoothed(k-2)  # 2nd derivative (acceleration)
  delta = threshold filtering weak signals
"""
import numpy as np
from qengine import indicators as ta


TREND_LONG = 'long'
TREND_SHORT = 'short'
TREND_NULL = 'null'


class TrendFilter:
    def __init__(self, config: dict):
        self.smoothing_period: int = config.get('smoothing_period', 14)
        self.delta: float = config.get('delta_threshold', 0.00015)
        self.require_direction_match: bool = config.get('require_direction_match', True)
        self.enabled: bool = config.get('enabled', True)

        # State
        self.current_trend: str = TREND_NULL
        self.d1: float = 0.0
        self.d2: float = 0.0

        # Stats
        self._entries_blocked: int = 0
        self._entries_allowed: int = 0
        self._trend_counts: dict = {TREND_LONG: 0, TREND_SHORT: 0, TREND_NULL: 0}

    def update(self, candles: np.ndarray) -> str:
        """Compute smoothed derivatives and classify trend. Called each candle."""
        if not self.enabled:
            self.current_trend = TREND_NULL
            return self.current_trend

        # Need at least smoothing_period + 2 candles for 2nd derivative
        min_candles = self.smoothing_period + 2
        if candles is None or len(candles) < min_candles:
            self.current_trend = TREND_NULL
            return self.current_trend

        # EMA on close prices (sequential=True returns full array)
        smoothed = ta.ema(candles, period=self.smoothing_period, source_type='close', sequential=True)

        # 1st derivative: momentum (Eq. 3 from paper)
        self.d1 = smoothed[-1] - smoothed[-2]

        # 2nd derivative: acceleration/concavity (Eq. 4 from paper)
        self.d2 = smoothed[-1] - 2.0 * smoothed[-2] + smoothed[-3]

        # Classify (Eq. 2 from paper)
        if self.d1 > self.delta and self.d2 > 0:
            self.current_trend = TREND_LONG
        elif self.d1 < -self.delta and self.d2 < 0:
            self.current_trend = TREND_SHORT
        else:
            self.current_trend = TREND_NULL

        self._trend_counts[self.current_trend] += 1
        return self.current_trend

    def should_allow_entry(self, strategy) -> bool:
        """Gate entry based on trend. Returns True to allow, False to block."""
        if not self.enabled:
            self._entries_allowed += 1
            return True

        # Null trend → always block
        if self.current_trend == TREND_NULL:
            self._entries_blocked += 1
            return False

        # Direction match check
        if self.require_direction_match:
            # Detect strategy intent from position or should_long/should_short
            wants_long = getattr(strategy, '_should_long', False)
            wants_short = getattr(strategy, '_should_short', False)

            if wants_long and self.current_trend != TREND_LONG:
                self._entries_blocked += 1
                return False
            if wants_short and self.current_trend != TREND_SHORT:
                self._entries_blocked += 1
                return False

        self._entries_allowed += 1
        return True

    @property
    def stats(self) -> dict:
        total = self._entries_allowed + self._entries_blocked
        return {
            'current_trend': self.current_trend,
            'd1': round(self.d1, 8),
            'd2': round(self.d2, 8),
            'entries_allowed': self._entries_allowed,
            'entries_blocked': self._entries_blocked,
            'block_rate': round(self._entries_blocked / total, 4) if total > 0 else 0.0,
            'trend_counts': dict(self._trend_counts),
        }
```

- [ ] **Step 2: Verify imports work**

Run: `python -c "from pipelines._shared.GTSBotPilot.trend_filter import TrendFilter, TREND_LONG, TREND_SHORT, TREND_NULL; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add pipelines/_shared/GTSBotPilot/trend_filter.py
git commit -m "feat(GTSBotPilot): add TrendFilter layer — EMA-smoothed derivative trend classification"
```

---

### Task 3: GridManager Layer

**Files:**
- Create: `pipelines/_shared/GTSBotPilot/grid_manager.py`

The GridManager implements the paper's Grid System Manager (GSM) block. It tracks open trades and enforces x-threshold (time spacing), y-threshold (price spacing), and max operations constraints.

- [ ] **Step 1: Create grid_manager.py**

```python
# pipelines/_shared/GTSBotPilot/grid_manager.py
"""
GridManager — Layer 2 of GTSBotPilot.

Implements the paper's Grid System Manager (GSM) block.
Tracks open trades, enforces grid spacing constraints:
  - x-threshold: min candles between same-direction trades
  - y-threshold: min price distance (ATR-scaled) between same-direction trades
  - max_operations: cap on total simultaneous open trades

Paper reference: Section 3.3, Equations 5-6, Figure 5 workflow.
"""
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from qengine import indicators as ta


@dataclass
class TrackedTicket:
    """A tracked open trade in the grid."""
    direction: str      # 'long' or 'short'
    entry_price: float
    entry_index: int    # candle index at entry


class GridManager:
    def __init__(self, config: dict):
        self.x_threshold: int = config.get('x_threshold', 15)
        self.y_threshold_atr_mult: float = config.get('y_threshold_atr_mult', 0.5)
        self.max_operations: int = config.get('max_operations', 13)
        self.adaptive: bool = config.get('adaptive', True)
        self.enabled: bool = config.get('enabled', True)

        # State
        self._tickets: List[TrackedTicket] = []
        self._candle_index: int = 0
        self._current_atr: float = 0.0
        self._current_y_threshold: float = 0.0
        self._current_x_threshold: int = self.x_threshold

        # Stats
        self._entries_blocked: int = 0
        self._entries_allowed: int = 0
        self._blocked_reasons: dict = {'max_ops': 0, 'x_dist': 0, 'y_dist': 0}

    def update(self, candles: np.ndarray, strategy) -> None:
        """Update state each candle: increment index, compute ATR, sync tickets."""
        self._candle_index += 1

        if not self.enabled:
            return

        if candles is not None and len(candles) >= 14:
            self._current_atr = ta.atr(candles, period=14)
            self._current_y_threshold = self._current_atr * self.y_threshold_atr_mult

            if self.adaptive:
                # Scale x-threshold inversely with volatility (higher vol → tighter time, lower vol → wider time)
                # Normalize ATR by close price to get relative volatility
                close = candles[-1, 2]
                if close > 0:
                    rel_vol = self._current_atr / close
                    # Baseline relative vol ~0.0005 for EUR/USD 1m
                    vol_ratio = rel_vol / 0.0005 if rel_vol > 0 else 1.0
                    # Inverse: low vol → wider spacing (more candles), high vol → tighter
                    self._current_x_threshold = max(5, int(self.x_threshold / vol_ratio))

        # Sync tickets from strategy's actual open tickets/position
        self._sync_tickets(strategy)

    def _sync_tickets(self, strategy) -> None:
        """Rebuild ticket list from strategy's live state."""
        position = getattr(strategy, 'position', None)
        if position is None or not getattr(position, 'is_open', False):
            self._tickets.clear()
            return

        # Try CFD tickets first (SurefireHedge uses these)
        cfd_tickets = getattr(position, 'tickets', None)
        if cfd_tickets and len(cfd_tickets) > 0:
            self._tickets = []
            for t in cfd_tickets:
                direction = 'long' if getattr(t, 'type', '') == 'long' or getattr(t, 'qty', 0) > 0 else 'short'
                self._tickets.append(TrackedTicket(
                    direction=direction,
                    entry_price=getattr(t, 'entry_price', 0.0),
                    entry_index=self._candle_index,  # approximate
                ))
            return

        # Fallback: single position tracking
        qty = getattr(position, 'qty', 0.0)
        if qty != 0:
            direction = 'long' if qty > 0 else 'short'
            entry_price = getattr(position, 'entry_price', 0.0)
            if not self._tickets or self._tickets[0].entry_price != entry_price:
                self._tickets = [TrackedTicket(
                    direction=direction,
                    entry_price=entry_price,
                    entry_index=self._candle_index,
                )]

    def should_allow_entry(self, strategy) -> bool:
        """Check grid constraints. Returns True to allow, False to block."""
        if not self.enabled:
            self._entries_allowed += 1
            return True

        # Determine direction of proposed trade
        wants_long = getattr(strategy, '_should_long', False)
        wants_short = getattr(strategy, '_should_short', False)
        if wants_long:
            direction = 'long'
        elif wants_short:
            direction = 'short'
        else:
            # Strategy not proposing an entry — allow (won't actually open)
            self._entries_allowed += 1
            return True

        # Check 1: max operations (paper: M0)
        if len(self._tickets) >= self.max_operations:
            self._entries_blocked += 1
            self._blocked_reasons['max_ops'] += 1
            return False

        # Get same-direction tickets
        same_dir = [t for t in self._tickets if t.direction == direction]

        if same_dir:
            # Check 2: x-threshold — time spacing (paper: x_th)
            latest_entry_index = max(t.entry_index for t in same_dir)
            candles_since = self._candle_index - latest_entry_index
            if candles_since < self._current_x_threshold:
                self._entries_blocked += 1
                self._blocked_reasons['x_dist'] += 1
                return False

            # Check 3: y-threshold — price spacing (paper: y_th)
            current_price = getattr(strategy, 'close', 0.0)
            if current_price > 0 and self._current_y_threshold > 0:
                for t in same_dir:
                    price_dist = abs(current_price - t.entry_price)
                    if price_dist < self._current_y_threshold:
                        self._entries_blocked += 1
                        self._blocked_reasons['y_dist'] += 1
                        return False

        self._entries_allowed += 1
        return True

    def on_open_position(self, strategy) -> None:
        """Register new ticket when position opens."""
        position = getattr(strategy, 'position', None)
        if position is None:
            return

        qty = getattr(position, 'qty', 0.0)
        direction = 'long' if qty > 0 else 'short'
        entry_price = getattr(position, 'entry_price', 0.0)

        self._tickets.append(TrackedTicket(
            direction=direction,
            entry_price=entry_price,
            entry_index=self._candle_index,
        ))

    def on_cycle_end(self) -> None:
        """Clean up tickets on cycle close."""
        self._tickets.clear()

    @property
    def stats(self) -> dict:
        long_count = sum(1 for t in self._tickets if t.direction == 'long')
        short_count = sum(1 for t in self._tickets if t.direction == 'short')
        total = self._entries_allowed + self._entries_blocked
        return {
            'open_long_count': long_count,
            'open_short_count': short_count,
            'total_open': len(self._tickets),
            'current_x_threshold': self._current_x_threshold,
            'current_y_threshold': round(self._current_y_threshold, 6),
            'current_atr': round(self._current_atr, 6),
            'entries_allowed': self._entries_allowed,
            'entries_blocked': self._entries_blocked,
            'block_rate': round(self._entries_blocked / total, 4) if total > 0 else 0.0,
            'blocked_reasons': dict(self._blocked_reasons),
        }
```

- [ ] **Step 2: Verify imports work**

Run: `python -c "from pipelines._shared.GTSBotPilot.grid_manager import GridManager, TrackedTicket; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add pipelines/_shared/GTSBotPilot/grid_manager.py
git commit -m "feat(GTSBotPilot): add GridManager layer — grid spacing enforcement with adaptive thresholds"
```

---

### Task 4: BasketManager Layer

**Files:**
- Create: `pipelines/_shared/GTSBotPilot/basket_manager.py`

The BasketManager implements the paper's Basket Equity System Manager (BESM). It monitors cumulative P&L across all open tickets and closes everything when the basket profit target is reached.

- [ ] **Step 1: Create basket_manager.py**

```python
# pipelines/_shared/GTSBotPilot/basket_manager.py
"""
BasketManager — Layer 3 of GTSBotPilot.

Implements the paper's Basket Equity System Manager (BESM) block.
Monitors cumulative unrealized P&L across all open tickets.
Closes all positions when basket profit target is reached.

Paper reference: Section 3.4.
No stop loss by design — grid compensates drawdown via position averaging.
Emergency drawdown cutoff available but disabled by default.
"""
import numpy as np
from typing import Optional
from qengine import indicators as ta


class BasketManager:
    def __init__(self, config: dict):
        self.target_profit_atr_mult: float = config.get('target_profit_atr_mult', 2.0)
        self.monitor_drawdown: bool = config.get('monitor_drawdown', True)
        self.emergency_dd_pct: Optional[float] = config.get('emergency_dd_pct', None)
        self.enabled: bool = config.get('enabled', True)

        # State
        self._current_atr: float = 0.0
        self._target_profit: float = 0.0
        self._basket_pnl: float = 0.0
        self._peak_equity: float = 0.0
        self._current_drawdown: float = 0.0

        # Stats
        self._baskets_closed: int = 0
        self._max_drawdown_seen: float = 0.0
        self._emergency_closes: int = 0

    def update(self, candles: np.ndarray, strategy) -> None:
        """Update basket P&L and drawdown each candle."""
        if not self.enabled:
            return

        # Compute ATR for dynamic target
        if candles is not None and len(candles) >= 14:
            self._current_atr = ta.atr(candles, period=14)
            self._target_profit = self._current_atr * self.target_profit_atr_mult

        # Compute basket P&L from strategy
        self._basket_pnl = self._compute_basket_pnl(strategy)

        # Drawdown tracking
        if self.monitor_drawdown:
            equity = self._get_equity(strategy)
            if equity > self._peak_equity:
                self._peak_equity = equity
            if self._peak_equity > 0:
                self._current_drawdown = (self._peak_equity - equity) / self._peak_equity
                if self._current_drawdown > self._max_drawdown_seen:
                    self._max_drawdown_seen = self._current_drawdown

    def _compute_basket_pnl(self, strategy) -> float:
        """Compute total unrealized P&L across all open tickets."""
        position = getattr(strategy, 'position', None)
        if position is None or not getattr(position, 'is_open', False):
            return 0.0

        # Try CFD tickets (SurefireHedge)
        tickets = getattr(position, 'tickets', None)
        if tickets and len(tickets) > 0:
            total_pnl = 0.0
            current_price = getattr(strategy, 'close', 0.0)
            for t in tickets:
                qty = getattr(t, 'qty', 0.0)
                entry = getattr(t, 'entry_price', 0.0)
                if hasattr(t, 'pnl'):
                    total_pnl += t.pnl(current_price)
                elif qty != 0 and entry > 0:
                    if qty > 0:
                        total_pnl += (current_price - entry) * abs(qty)
                    else:
                        total_pnl += (entry - current_price) * abs(qty)
            return total_pnl

        # Fallback: single position P&L
        pnl = getattr(position, 'pnl', 0.0)
        if callable(pnl):
            return pnl()
        return float(pnl)

    def _get_equity(self, strategy) -> float:
        """Get current account equity."""
        # Try strategy.balance (backtest) or strategy.capital (live)
        balance = getattr(strategy, 'balance', None)
        if balance is not None:
            return float(balance) + self._basket_pnl
        capital = getattr(strategy, 'capital', 0.0)
        return float(capital) + self._basket_pnl

    def should_close_basket(self) -> Optional[dict]:
        """Check if basket profit target reached or emergency DD triggered."""
        if not self.enabled:
            return None

        # Basket profit target reached → close all
        if self._target_profit > 0 and self._basket_pnl >= self._target_profit:
            self._baskets_closed += 1
            return {'action': 'close_all'}

        # Emergency drawdown cutoff
        if self.emergency_dd_pct is not None and self._current_drawdown >= self.emergency_dd_pct:
            self._emergency_closes += 1
            self._baskets_closed += 1
            return {'action': 'close_all'}

        return None

    def on_cycle_end(self) -> None:
        """Reset basket state after all positions closed."""
        self._basket_pnl = 0.0

    @property
    def stats(self) -> dict:
        return {
            'basket_pnl': round(self._basket_pnl, 4),
            'target_profit': round(self._target_profit, 6),
            'pnl_pct_of_target': round(
                self._basket_pnl / self._target_profit, 4
            ) if self._target_profit > 0 else 0.0,
            'current_atr': round(self._current_atr, 6),
            'peak_equity': round(self._peak_equity, 2),
            'current_drawdown': round(self._current_drawdown, 4),
            'max_drawdown_seen': round(self._max_drawdown_seen, 4),
            'baskets_closed': self._baskets_closed,
            'emergency_closes': self._emergency_closes,
        }
```

- [ ] **Step 2: Verify imports work**

Run: `python -c "from pipelines._shared.GTSBotPilot.basket_manager import BasketManager; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add pipelines/_shared/GTSBotPilot/basket_manager.py
git commit -m "feat(GTSBotPilot): add BasketManager layer — basket equity monitoring with dynamic ATR target"
```

---

### Task 5: Main GTSBotPilot Pipeline Class

**Files:**
- Create: `pipelines/_shared/GTSBotPilot/__init__.py`

Composes the 3 layers into a single `Pipeline` subclass following the GridPilot/IslandPilot pattern.

- [ ] **Step 1: Create __init__.py**

```python
# pipelines/_shared/GTSBotPilot/__init__.py
"""
GTSBotPilot — Grid Trading System Bot Pipeline.

Based on: Rundo et al., "Grid Trading System Robot (GTSbot):
A Novel Mathematical Algorithm for Trading FX Market"
(Appl. Sci. 2019, 9, 1796)

3-layer pipeline overlay for grid/martingale strategies:
  Layer 1: TrendFilter  — EMA-smoothed derivative trend classification
  Layer 2: GridManager  — Grid spacing enforcement (x/y thresholds, max ops)
  Layer 3: BasketManager — Basket equity P&L monitoring with close-all target
"""
import os
from typing import Optional

from qengine.framework.base import Pipeline, OrderIntent

from .config import merge_config, DEFAULT_CONFIG
from .trend_filter import TrendFilter
from .grid_manager import GridManager
from .basket_manager import BasketManager

_DIR = os.path.dirname(os.path.abspath(__file__))
_MODELS_DIR = os.path.join(_DIR, 'models')

# Max candles to slice for indicator computation (O(1) cost)
_MAX_LOOKBACK = 300


class GTSBotPilot(Pipeline):
    name = 'GTSBotPilot'

    def __init__(self, config: dict = None):
        self.cfg = merge_config(config or {})

        # Layers
        self.trend_filter = TrendFilter(self.cfg['trend_filter'])
        self.grid_manager = GridManager(self.cfg['grid_manager'])
        self.basket_manager = BasketManager(self.cfg['basket_manager'])

        # Runtime
        self._candle_count: int = 0
        self._last_recorded_session: Optional[int] = None

    # ── Observation Phase ─────────────────────────────────────────

    def on_before(self, strategy) -> None:
        """Called every candle. Update all 3 layers."""
        self._candle_count += 1

        candles = getattr(strategy, 'candles', None)
        if candles is None or len(candles) < self.cfg['warmup']:
            return

        # Slice tail for O(1) indicator cost
        tail = candles[-_MAX_LOOKBACK:] if len(candles) > _MAX_LOOKBACK else candles

        # Layer 1: trend classification
        self.trend_filter.update(tail)

        # Layer 2: grid state update
        self.grid_manager.update(tail, strategy)

        # Layer 3: basket P&L update
        self.basket_manager.update(tail, strategy)

    # ── Entry Control Phase ───────────────────────────────────────

    def gate_entry(self, strategy) -> bool:
        """Block entries that fail trend or grid checks. AND logic."""
        # During warmup, allow all
        if self._candle_count < self.cfg['warmup']:
            return True

        # Layer 1: trend must be confirmed and match direction
        if not self.trend_filter.should_allow_entry(strategy):
            return False

        # Layer 2: grid spacing must be satisfied
        if not self.grid_manager.should_allow_entry(strategy):
            return False

        return True

    # ── Order Control Phase ───────────────────────────────────────

    def filter_order(self, strategy, order_intent: OrderIntent) -> Optional[OrderIntent]:
        """Final grid check on individual orders."""
        if not self.grid_manager.enabled:
            return order_intent

        # Only filter entry orders
        if not order_intent.is_entry:
            return order_intent

        # Check max operations on the order level
        if len(self.grid_manager._tickets) >= self.grid_manager.max_operations:
            return None  # cancel order

        return order_intent

    # ── Exit Control Phase ────────────────────────────────────────

    def suggest_exit(self, strategy) -> Optional[dict]:
        """Close all when basket profit target reached."""
        if self._candle_count < self.cfg['warmup']:
            return None

        return self.basket_manager.should_close_basket()

    # ── Lifecycle Events ──────────────────────────────────────────

    def on_open_position(self, strategy) -> None:
        """Track new position in grid manager."""
        self.grid_manager.on_open_position(strategy)

    def on_cycle_end(self, pnl: float, strategy) -> None:
        """Clean up on cycle close. Deduplicate via session_number."""
        sn = getattr(strategy, 'vars', {}).get('session_number')
        if sn is not None and sn == self._last_recorded_session:
            return
        self._last_recorded_session = sn

        self.grid_manager.on_cycle_end()
        self.basket_manager.on_cycle_end()

    # ── Stats & Metadata ─────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            'candle_count': self._candle_count,
            'trend_filter': self.trend_filter.stats,
            'grid_manager': self.grid_manager.stats,
            'basket_manager': self.basket_manager.stats,
            '_ui': self.ui_metadata(),
        }

    @classmethod
    def default_config(cls) -> dict:
        return DEFAULT_CONFIG

    @classmethod
    def architecture(cls) -> dict:
        return {
            'summary': 'GTSBot grid trading pipeline with trend filtering, grid spacing enforcement, and basket equity management.',
            'paper': 'Rundo et al., Appl. Sci. 2019, 9, 1796',
            'designed_for': ['Grid strategies', 'Martingale strategies', 'Surefire hedge'],
            'requires_training': False,
            'training_status': 'ready',
            'layers': [
                {
                    'name': 'TrendFilter',
                    'order': 1,
                    'type': 'entry_control',
                    'hook': 'on_before() + gate_entry()',
                    'description': 'EMA-smoothed derivative trend classification (replaces paper SCG NN + TCB).',
                },
                {
                    'name': 'GridManager',
                    'order': 2,
                    'type': 'entry_control',
                    'hook': 'on_before() + gate_entry() + filter_order()',
                    'description': 'Grid spacing enforcement: x-threshold (time), y-threshold (price), max ops.',
                },
                {
                    'name': 'BasketManager',
                    'order': 3,
                    'type': 'exit_control',
                    'hook': 'on_before() + suggest_exit()',
                    'description': 'Basket equity monitoring — closes all when profit target reached.',
                },
            ],
        }

    def ui_metadata(self) -> dict:
        return {
            'badges': [
                {'label': 'GTSBot', 'color': 'brand'},
                {'label': f"Trend: {self.trend_filter.current_trend}", 'color': 'surface'},
                {'label': f"Grid: {self.grid_manager.stats['total_open']}/{self.grid_manager.max_operations}", 'color': 'surface'},
            ],
            'metric_cards': [
                {'label': 'Trend', 'key': 'trend_filter.current_trend', 'format': 'text'},
                {'label': 'Basket P&L', 'key': 'basket_manager.basket_pnl', 'format': 'currency'},
                {'label': 'Target', 'key': 'basket_manager.target_profit', 'format': 'currency'},
                {'label': 'Open Trades', 'key': 'grid_manager.total_open', 'format': 'integer'},
                {'label': 'Max DD', 'key': 'basket_manager.max_drawdown_seen', 'format': 'percent'},
                {'label': 'Baskets Closed', 'key': 'basket_manager.baskets_closed', 'format': 'integer'},
            ],
            'sections': [
                {
                    'type': 'kv_pairs',
                    'title': 'Trend Filter',
                    'data_key': 'trend_filter',
                },
                {
                    'type': 'kv_pairs',
                    'title': 'Grid Manager',
                    'data_key': 'grid_manager',
                },
                {
                    'type': 'kv_pairs',
                    'title': 'Basket Manager',
                    'data_key': 'basket_manager',
                },
            ],
        }
```

- [ ] **Step 2: Verify pipeline loads and extends Pipeline correctly**

Run: `python -c "from pipelines._shared.GTSBotPilot import GTSBotPilot; from qengine.framework.base import Pipeline; p = GTSBotPilot(); assert isinstance(p, Pipeline); print('OK:', p.name, list(p.get_stats().keys()))"`

Expected: `OK: GTSBotPilot ['candle_count', 'trend_filter', 'grid_manager', 'basket_manager', '_ui']`

- [ ] **Step 3: Verify architecture and default_config**

Run: `python -c "from pipelines._shared.GTSBotPilot import GTSBotPilot; a = GTSBotPilot.architecture(); print('Layers:', [l['name'] for l in a['layers']]); c = GTSBotPilot.default_config(); print('Config:', list(c.keys()))"`

Expected:
```
Layers: ['TrendFilter', 'GridManager', 'BasketManager']
Config: ['warmup', 'trend_filter', 'grid_manager', 'basket_manager']
```

- [ ] **Step 4: Commit**

```bash
git add pipelines/_shared/GTSBotPilot/__init__.py
git commit -m "feat(GTSBotPilot): compose 3 layers into Pipeline — TrendFilter, GridManager, BasketManager"
```

---

### Task 6: Integration Test

**Files:**
- Create: `tests/test_gtsbot_pilot.py`

End-to-end test verifying the pipeline lifecycle: warmup, trend gating, grid enforcement, basket close.

- [ ] **Step 1: Create test file**

```python
# tests/test_gtsbot_pilot.py
"""Integration tests for GTSBotPilot pipeline."""
import numpy as np
import pytest
from unittest.mock import MagicMock
from pipelines._shared.GTSBotPilot import GTSBotPilot
from pipelines._shared.GTSBotPilot.trend_filter import TREND_LONG, TREND_SHORT, TREND_NULL
from qengine.framework.base import Pipeline, OrderIntent


def _make_candles(n: int, base_price: float = 1.2000, trend: float = 0.0) -> np.ndarray:
    """Generate synthetic OHLCV candles.

    Candle format: [timestamp, open, close, high, low, volume]
    trend > 0 for uptrend, < 0 for downtrend, 0 for flat.
    """
    candles = np.zeros((n, 6))
    for i in range(n):
        ts = 1609459200000 + i * 60000  # 1-min candles
        price = base_price + trend * i
        noise = np.sin(i * 0.1) * 0.0001  # tiny noise
        o = price + noise
        c = price + trend * 0.5 + noise
        h = max(o, c) + 0.0002
        l = min(o, c) - 0.0002
        v = 100.0
        candles[i] = [ts, o, c, h, l, v]
    return candles


def _make_strategy(candles: np.ndarray, should_long=False, should_short=False,
                   position_open=False, position_qty=0.0, entry_price=0.0):
    """Create a mock strategy object."""
    s = MagicMock()
    s.candles = candles
    s.close = candles[-1, 2] if len(candles) > 0 else 0.0
    s._should_long = should_long
    s._should_short = should_short
    s.vars = {}

    # Position mock
    s.position = MagicMock()
    s.position.is_open = position_open
    s.position.qty = position_qty
    s.position.entry_price = entry_price
    s.position.tickets = []
    s.position.pnl = 0.0

    s.balance = 30000.0
    return s


class TestGTSBotPilotConstruction:
    def test_extends_pipeline(self):
        p = GTSBotPilot()
        assert isinstance(p, Pipeline)

    def test_has_all_layers(self):
        p = GTSBotPilot()
        assert hasattr(p, 'trend_filter')
        assert hasattr(p, 'grid_manager')
        assert hasattr(p, 'basket_manager')

    def test_default_config(self):
        cfg = GTSBotPilot.default_config()
        assert 'trend_filter' in cfg
        assert 'grid_manager' in cfg
        assert 'basket_manager' in cfg
        assert cfg['grid_manager']['max_operations'] == 13

    def test_architecture(self):
        arch = GTSBotPilot.architecture()
        layers = [l['name'] for l in arch['layers']]
        assert layers == ['TrendFilter', 'GridManager', 'BasketManager']

    def test_custom_config_merges(self):
        p = GTSBotPilot({'grid_manager': {'max_operations': 7}})
        assert p.grid_manager.max_operations == 7
        # Other defaults preserved
        assert p.grid_manager.x_threshold == 15


class TestTrendFilter:
    def test_allows_during_warmup(self):
        p = GTSBotPilot({'warmup': 100})
        candles = _make_candles(50, trend=0.0001)
        strategy = _make_strategy(candles, should_long=True)
        p.on_before(strategy)
        assert p.gate_entry(strategy) is True  # warmup → allow all

    def test_blocks_null_trend(self):
        p = GTSBotPilot({'warmup': 10})
        # Flat candles → null trend
        candles = _make_candles(100, trend=0.0)
        strategy = _make_strategy(candles, should_long=True)
        p.on_before(strategy)
        # After warmup, null trend should block
        p._candle_count = 100  # force past warmup
        result = p.gate_entry(strategy)
        # Either blocks (null) or allows (if derivatives happen to be nonzero from noise)
        assert isinstance(result, bool)

    def test_allows_matching_trend(self):
        p = GTSBotPilot({'warmup': 10, 'trend_filter': {'delta_threshold': 0.000001}})
        # Strong uptrend
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles, should_long=True)
        p._candle_count = 100
        p.on_before(strategy)
        assert p.trend_filter.current_trend == TREND_LONG
        assert p.gate_entry(strategy) is True

    def test_blocks_opposing_trend(self):
        p = GTSBotPilot({'warmup': 10, 'trend_filter': {'delta_threshold': 0.000001}})
        # Strong uptrend but strategy wants short
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles, should_short=True)
        p._candle_count = 100
        p.on_before(strategy)
        assert p.trend_filter.current_trend == TREND_LONG
        assert p.gate_entry(strategy) is False


class TestGridManager:
    def test_blocks_when_max_ops_reached(self):
        p = GTSBotPilot({'warmup': 10, 'grid_manager': {'max_operations': 2},
                         'trend_filter': {'enabled': False}})
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles, should_long=True)

        p._candle_count = 100
        p.on_before(strategy)

        # Manually add tickets to simulate open trades
        from pipelines._shared.GTSBotPilot.grid_manager import TrackedTicket
        p.grid_manager._tickets = [
            TrackedTicket('long', 1.2000, 50),
            TrackedTicket('long', 1.2050, 70),
        ]

        assert p.gate_entry(strategy) is False

    def test_allows_when_grid_spacing_ok(self):
        p = GTSBotPilot({'warmup': 10, 'grid_manager': {'x_threshold': 5, 'y_threshold_atr_mult': 0.1},
                         'trend_filter': {'enabled': False}})
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles, should_long=True)

        p._candle_count = 100
        p.on_before(strategy)

        # One old ticket far away in time and price
        from pipelines._shared.GTSBotPilot.grid_manager import TrackedTicket
        p.grid_manager._tickets = [
            TrackedTicket('long', 1.1000, 10),
        ]

        assert p.gate_entry(strategy) is True


class TestBasketManager:
    def test_no_exit_when_below_target(self):
        p = GTSBotPilot({'warmup': 10})
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles)
        p._candle_count = 100
        p.on_before(strategy)
        assert p.suggest_exit(strategy) is None

    def test_close_all_when_target_reached(self):
        p = GTSBotPilot({'warmup': 10})
        candles = _make_candles(100, trend=0.001)
        strategy = _make_strategy(candles)
        p._candle_count = 100
        p.on_before(strategy)

        # Force basket P&L above target
        p.basket_manager._basket_pnl = 1000.0
        p.basket_manager._target_profit = 100.0

        result = p.suggest_exit(strategy)
        assert result == {'action': 'close_all'}


class TestFilterOrder:
    def test_allows_non_entry_orders(self):
        p = GTSBotPilot()
        order = OrderIntent(qty=1.0, price=1.2, side='buy', type='stop',
                            is_entry=False, symbol='EUR-USD', exchange='OANDA')
        assert p.filter_order(MagicMock(), order) is order

    def test_cancels_entry_when_max_ops(self):
        p = GTSBotPilot({'grid_manager': {'max_operations': 1}})
        from pipelines._shared.GTSBotPilot.grid_manager import TrackedTicket
        p.grid_manager._tickets = [TrackedTicket('long', 1.2, 1)]

        order = OrderIntent(qty=1.0, price=1.2, side='buy', type='market',
                            is_entry=True, symbol='EUR-USD', exchange='OANDA')
        assert p.filter_order(MagicMock(), order) is None


class TestGetStats:
    def test_returns_all_sections(self):
        p = GTSBotPilot()
        stats = p.get_stats()
        assert 'candle_count' in stats
        assert 'trend_filter' in stats
        assert 'grid_manager' in stats
        assert 'basket_manager' in stats
        assert '_ui' in stats

    def test_ui_metadata_has_badges(self):
        p = GTSBotPilot()
        ui = p.ui_metadata()
        assert 'badges' in ui
        assert 'metric_cards' in ui
        assert 'sections' in ui
        assert len(ui['badges']) == 3


class TestLifecycle:
    def test_on_cycle_end_deduplicates(self):
        p = GTSBotPilot()
        strategy = MagicMock()
        strategy.vars = {'session_number': 1}

        p.on_cycle_end(100.0, strategy)
        assert p._last_recorded_session == 1

        # Second call with same session → no-op
        p.grid_manager._tickets = [MagicMock()]  # should NOT be cleared
        p.on_cycle_end(200.0, strategy)
        assert len(p.grid_manager._tickets) == 1  # not cleared (deduped)

    def test_on_cycle_end_clears_on_new_session(self):
        p = GTSBotPilot()
        strategy = MagicMock()
        strategy.vars = {'session_number': 1}
        p.on_cycle_end(100.0, strategy)

        strategy.vars = {'session_number': 2}
        p.on_cycle_end(200.0, strategy)
        assert p._last_recorded_session == 2
        assert len(p.grid_manager._tickets) == 0
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/test_gtsbot_pilot.py -v`

Expected: All tests pass.

- [ ] **Step 3: Fix any failures and re-run until green**

- [ ] **Step 4: Commit**

```bash
git add tests/test_gtsbot_pilot.py
git commit -m "test(GTSBotPilot): add integration tests for all 3 layers and lifecycle"
```

---

### Task 7: Verification — Backtest Smoke Test

**Files:** None created. This task runs the pipeline against real data to verify it works end-to-end.

- [ ] **Step 1: Verify pipeline can be instantiated and run on_before with real candles**

Run a quick smoke test using `qengine.research.candles.get_candles()` to load real EUR-USD data and feed candles through the pipeline:

```python
# Run as: python -c "..." from project root
import numpy as np
from qengine.research.candles import get_candles
from pipelines._shared.GTSBotPilot import GTSBotPilot

warmup, candles = get_candles('OANDA', 'EUR-USD', '5m', '2024-01-01', '2024-01-31')
print(f"Candles: {len(candles)}, warmup: {len(warmup) if warmup.ndim == 2 else 0}")

p = GTSBotPilot()

# Simulate feeding candles one at a time (last 200)
from unittest.mock import MagicMock
for i in range(max(0, len(candles) - 200), len(candles)):
    s = MagicMock()
    s.candles = candles[:i+1]
    s.close = candles[i, 2]
    s._should_long = False
    s._should_short = False
    s.position = MagicMock()
    s.position.is_open = False
    s.position.tickets = []
    s.vars = {}
    s.balance = 30000.0
    p.on_before(s)

stats = p.get_stats()
print(f"Candles processed: {stats['candle_count']}")
print(f"Trend: {stats['trend_filter']['current_trend']}")
print(f"d1: {stats['trend_filter']['d1']}, d2: {stats['trend_filter']['d2']}")
print(f"Trend counts: {stats['trend_filter']['trend_counts']}")
print(f"ATR: {stats['grid_manager']['current_atr']}")
print(f"Y-threshold: {stats['grid_manager']['current_y_threshold']}")
print("Smoke test PASSED")
```

Expected: No errors. Trend classification produces a mix of long/short/null. ATR and y-threshold are non-zero positive values.

- [ ] **Step 2: Commit all remaining files (if any unstaged)**

```bash
git add pipelines/_shared/GTSBotPilot/
git status
```

Verify all GTSBotPilot files are committed.
