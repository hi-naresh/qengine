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
from dataclasses import dataclass
from typing import List
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

        self._tickets: List[TrackedTicket] = []
        self._candle_index: int = 0
        self._current_atr: float = 0.0
        self._current_y_threshold: float = 0.0
        self._current_x_threshold: int = self.x_threshold

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
                close = candles[-1, 2]
                if close > 0:
                    rel_vol = self._current_atr / close
                    vol_ratio = rel_vol / 0.0005 if rel_vol > 0 else 1.0
                    self._current_x_threshold = max(5, int(self.x_threshold / vol_ratio))

        self._sync_tickets(strategy)

    def _sync_tickets(self, strategy) -> None:
        """Rebuild ticket list from strategy's live state."""
        position = getattr(strategy, 'position', None)
        if position is None or not getattr(position, 'is_open', False):
            self._tickets.clear()
            return

        cfd_tickets = getattr(position, 'tickets', None)
        if cfd_tickets and len(cfd_tickets) > 0:
            self._tickets = []
            for t in cfd_tickets:
                direction = 'long' if getattr(t, 'type', '') == 'long' or getattr(t, 'qty', 0) > 0 else 'short'
                self._tickets.append(TrackedTicket(
                    direction=direction,
                    entry_price=getattr(t, 'entry_price', 0.0),
                    entry_index=self._candle_index,
                ))
            return

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

        wants_long = getattr(strategy, '_should_long', False)
        wants_short = getattr(strategy, '_should_short', False)
        if wants_long:
            direction = 'long'
        elif wants_short:
            direction = 'short'
        else:
            self._entries_allowed += 1
            return True

        if len(self._tickets) >= self.max_operations:
            self._entries_blocked += 1
            self._blocked_reasons['max_ops'] += 1
            return False

        same_dir = [t for t in self._tickets if t.direction == direction]

        if same_dir:
            latest_entry_index = max(t.entry_index for t in same_dir)
            candles_since = self._candle_index - latest_entry_index
            if candles_since < self._current_x_threshold:
                self._entries_blocked += 1
                self._blocked_reasons['x_dist'] += 1
                return False

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
