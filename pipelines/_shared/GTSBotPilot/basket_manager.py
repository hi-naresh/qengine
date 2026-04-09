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
        self.max_loss_atr_mult: float = config.get('max_loss_atr_mult', 10.0)
        self.monitor_drawdown: bool = config.get('monitor_drawdown', True)
        self.emergency_dd_pct: Optional[float] = config.get('emergency_dd_pct', None)
        self.enabled: bool = config.get('enabled', True)

        self._current_atr: float = 0.0
        self._target_profit: float = 0.0
        self._max_loss: float = 0.0
        self._basket_pnl: float = 0.0
        self._total_qty: float = 0.0
        self._peak_equity: float = 0.0
        self._current_drawdown: float = 0.0

        self._baskets_closed: int = 0
        self._max_drawdown_seen: float = 0.0
        self._emergency_closes: int = 0
        self._loss_cutoffs: int = 0

    def update(self, candles: np.ndarray, strategy) -> None:
        """Update basket P&L and drawdown each candle."""
        if not self.enabled:
            return

        if candles is not None and len(candles) >= 14:
            self._current_atr = ta.atr(candles, period=14)

        self._basket_pnl = self._compute_basket_pnl(strategy)
        self._total_qty = self._compute_total_qty(strategy)

        # Scale TP/SL by total position size so they're in dollar terms
        # target_profit = ATR * mult * qty  (e.g., 0.0003 * 2.0 * 1000 = $0.60)
        # max_loss      = ATR * mult * qty  (e.g., 0.0003 * 10.0 * 1000 = $3.00)
        qty_scale = max(self._total_qty, 1.0)
        self._target_profit = self._current_atr * self.target_profit_atr_mult * qty_scale
        self._max_loss = self._current_atr * self.max_loss_atr_mult * qty_scale

        if self.monitor_drawdown:
            equity = self._get_equity(strategy)
            if equity > self._peak_equity:
                self._peak_equity = equity
            if self._peak_equity > 0:
                self._current_drawdown = (self._peak_equity - equity) / self._peak_equity
                if self._current_drawdown > self._max_drawdown_seen:
                    self._max_drawdown_seen = self._current_drawdown

    def _compute_total_qty(self, strategy) -> float:
        """Compute total absolute quantity across all open tickets."""
        position = getattr(strategy, 'position', None)
        if position is None or not getattr(position, 'is_open', False):
            return 0.0

        tickets = getattr(position, 'tickets', None)
        if tickets and len(tickets) > 0:
            return sum(abs(getattr(t, 'qty', 0.0)) for t in tickets)

        return abs(getattr(position, 'qty', 0.0))

    def _compute_basket_pnl(self, strategy) -> float:
        """Compute total unrealized P&L across all open tickets."""
        position = getattr(strategy, 'position', None)
        if position is None or not getattr(position, 'is_open', False):
            return 0.0

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

        pnl = getattr(position, 'pnl', 0.0)
        if callable(pnl):
            return pnl()
        return float(pnl)

    def _get_equity(self, strategy) -> float:
        """Get current account equity."""
        balance = getattr(strategy, 'balance', None)
        if balance is not None:
            return float(balance) + self._basket_pnl
        capital = getattr(strategy, 'capital', 0.0)
        return float(capital) + self._basket_pnl

    def should_close_basket(self) -> Optional[dict]:
        """Check if basket profit target reached, max loss exceeded, or emergency DD triggered."""
        if not self.enabled:
            return None

        # Profit target hit → close all
        if self._target_profit > 0 and self._basket_pnl >= self._target_profit:
            self._baskets_closed += 1
            return {'action': 'close_all'}

        # Max loss cutoff — prevent catastrophic busts (ATR-scaled)
        if self._max_loss > 0 and self._basket_pnl <= -self._max_loss:
            self._loss_cutoffs += 1
            self._baskets_closed += 1
            return {'action': 'close_all'}

        # Emergency account drawdown
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
            'max_loss': round(self._max_loss, 6),
            'pnl_pct_of_target': round(
                self._basket_pnl / self._target_profit, 4
            ) if self._target_profit > 0 else 0.0,
            'current_atr': round(self._current_atr, 6),
            'peak_equity': round(self._peak_equity, 2),
            'current_drawdown': round(self._current_drawdown, 4),
            'max_drawdown_seen': round(self._max_drawdown_seen, 4),
            'baskets_closed': self._baskets_closed,
            'loss_cutoffs': self._loss_cutoffs,
            'emergency_closes': self._emergency_closes,
        }
