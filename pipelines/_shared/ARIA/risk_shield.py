"""
RiskShield — Layer 4 of the ARIA pipeline.

Three sub-components that decide whether to abort a cycle mid-trade
to protect the account:

  4a. ConformalKill  — online conformal prediction on loss sequences
  4b. LiquidityGate  — affordability, spread cost, and ruin checks
  4c. MarginSurvival — exposure-based ruin probability estimate

The main RiskShield class orchestrates all three and exposes a single
``check()`` method called every candle while a position is open.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_CALIBRATION = 500       # max loss samples kept per level
_MIN_CALIBRATION_CYCLES = 20 # cycles before conformal prediction activates
_MIN_LEVEL_SAMPLES = 5       # minimum per-level samples for prediction
_MAX_CYCLE_BARS = 2000       # hard abort after this many bars (≈7 days at 5m)


# ===================================================================
# 4a  Conformal Kill Switch
# ===================================================================

class ConformalKill:
    """Online conformal prediction on loss sequences per hedge level.

    Before each hedge level decision, predict the loss if we continue.
    Kill if ``predicted_loss + uncertainty_bound > available_margin * safety_factor``.

    Until we have at least ``_MIN_CALIBRATION_CYCLES`` observed cycles the
    predictor falls back to a simple level threshold (abort at ``fallback_level``).
    """

    def __init__(self, alpha: float = 0.1, safety_factor: float = 0.8,
                 fallback_level: int = 6):
        self.alpha = float(np.clip(alpha, 0.01, 0.5))
        self.safety_factor = float(np.clip(safety_factor, 0.1, 1.0))
        self.fallback_level = int(max(1, fallback_level))

        # {level: [loss_value, ...]} — only negative-PnL entries are stored
        self._calibration: dict[int, list[float]] = {}
        self._total_cycles: int = 0

    # ----- public -----

    def should_kill(self, level: int, equity: float,
                    margin_used: float) -> tuple[bool, str]:
        """Decide whether to kill the current cycle.

        Returns
        -------
        (should_kill, reason)
            reason is one of: ``'fallback_level'``, ``'insufficient_data'``,
            ``'conformal_kill'``, ``'ok'``.
        """
        if equity <= 0:
            return True, 'zero_equity'

        # --- fallback mode ---
        if self._total_cycles < _MIN_CALIBRATION_CYCLES:
            return level >= self.fallback_level, 'fallback_level'

        losses = self._calibration.get(level)
        if losses is None or len(losses) < _MIN_LEVEL_SAMPLES:
            return False, 'insufficient_data'

        arr = np.asarray(losses, dtype=np.float64)
        predicted_loss = float(np.median(arr))
        residuals = np.abs(arr - predicted_loss)
        bound = float(np.quantile(residuals, 1.0 - self.alpha))

        available = max(equity - margin_used, 0.0)
        threshold = available * self.safety_factor
        if predicted_loss + bound > threshold:
            return True, 'conformal_kill'

        return False, 'ok'

    def record_cycle(self, level_reached: int, pnl: float) -> None:
        """Record a completed cycle's outcome for calibration.

        We store the absolute loss value at every level *up to and including*
        ``level_reached`` so that higher levels accumulate data from all cycles
        that passed through them.
        """
        self._total_cycles += 1
        if pnl >= 0:
            return  # only losses contribute to the kill calibration

        loss = abs(pnl)
        for lvl in range(level_reached + 1):
            bucket = self._calibration.setdefault(lvl, [])
            bucket.append(loss)
            # keep bounded
            if len(bucket) > _MAX_CALIBRATION:
                bucket[:] = bucket[-_MAX_CALIBRATION:]

    # ----- serialisation -----

    def state_dict(self) -> dict:
        return {
            'alpha': self.alpha,
            'safety_factor': self.safety_factor,
            'fallback_level': self.fallback_level,
            'calibration': {str(k): v for k, v in self._calibration.items()},
            'total_cycles': self._total_cycles,
        }

    def load_state_dict(self, d: dict) -> None:
        self.alpha = float(d.get('alpha', self.alpha))
        self.safety_factor = float(d.get('safety_factor', self.safety_factor))
        self.fallback_level = int(d.get('fallback_level', self.fallback_level))
        self._total_cycles = int(d.get('total_cycles', 0))
        self._calibration = {}
        for k, v in d.get('calibration', {}).items():
            self._calibration[int(k)] = list(v)


# ===================================================================
# 4b  Liquidity Gate
# ===================================================================

class LiquidityGate:
    """Pre-hedge liquidity and affordability checks.

    Three conditions must hold before allowing a new hedge level:

    1. **Affordable** — we can afford the next position size given
       available margin and leverage.
    2. **Spread acceptable** — spread cost is less than 20 % of
       expected TP profit so we are not giving it all away in fees.
    3. **Ruin probability** — delegated to :class:`MarginSurvival`,
       must be below ``max_ruin_prob``.
    """

    def __init__(self, max_ruin_prob: float = 0.5):
        self.max_ruin_prob = float(np.clip(max_ruin_prob, 0.01, 1.0))
        self._survival = MarginSurvival()

    def check(self, level: int, equity: float, base_size: float,
              multiplier: float, price: float, leverage: float,
              spread: float, atr: float,
              tp_distance: float) -> tuple[bool, str]:
        """Evaluate whether it is safe to open the next hedge level.

        Parameters
        ----------
        level : int
            Current hedge level (0-based).  The *next* level would be
            ``level + 1``.
        equity : float
            Account equity (balance + unrealised PnL).
        base_size : float
            Base position size (units / lots).
        multiplier : float
            Geometric sizing multiplier (e.g. 2.0 for classic martingale).
        price : float
            Current instrument price.
        leverage : float
            Account leverage (e.g. 30 for 30:1).
        spread : float
            Current bid-ask spread in price units.
        atr : float
            Recent ATR (same unit as price).
        tp_distance : float
            Distance to take-profit in price units.

        Returns
        -------
        (safe, reason)
            ``safe=True`` means all checks passed.
        """
        if equity <= 0 or price <= 0:
            return False, 'zero_equity_or_price'

        # Ensure sensible defaults for degenerate inputs
        multiplier = max(multiplier, 1.0)
        leverage = max(leverage, 1.0)
        base_size = max(base_size, 0.0)

        # 1. Affordability — can we fund the next position?
        next_size = base_size * multiplier ** (level + 1)
        margin_required = (next_size * price) / leverage
        available_margin = equity  # conservative: use full equity as upper bound
        if margin_required > available_margin:
            return False, 'insufficient_margin'

        # 2. Spread cost vs expected profit
        if tp_distance > 0:
            spread_cost = next_size * spread
            expected_profit = next_size * tp_distance
            if expected_profit > 0 and spread_cost > expected_profit * 0.2:
                return False, 'spread_too_high'

        # 3. Ruin probability
        ruin_p = self._survival.ruin_probability(
            level=level, equity=equity, base_size=base_size,
            multiplier=multiplier, atr=atr,
        )
        if ruin_p > self.max_ruin_prob:
            return False, f'ruin_prob_{ruin_p:.3f}'

        return True, 'ok'


# ===================================================================
# 4c  Margin Survival Model
# ===================================================================

class MarginSurvival:
    """Simple exposure-based ruin probability estimator.

    ``P(ruin) ~ total_exposure * 3-sigma move / equity``

    This is not a rigorous analytical model but a fast, conservative
    heuristic that stays under O(1) per call.
    """

    def ruin_probability(self, level: int, equity: float,
                         base_size: float, multiplier: float,
                         atr: float) -> float:
        """Estimate ruin probability given current exposure.

        Parameters
        ----------
        level : int
            Current hedge level.  The calculation assumes we may open
            one *more* level (``level + 2`` total positions from L0).
        equity : float
            Current account equity.
        base_size : float
            Base position size.
        multiplier : float
            Geometric sizing multiplier.
        atr : float
            Recent ATR in price units.

        Returns
        -------
        float
            Probability estimate clipped to [0, 1].
        """
        if equity <= 0:
            return 1.0

        multiplier = max(multiplier, 1.0)
        total_exposure = sum(
            base_size * multiplier ** i for i in range(level + 2)
        )
        max_adverse = total_exposure * atr * 3.0
        return float(np.clip(max_adverse / max(equity, 1e-12), 0.0, 1.0))


# ===================================================================
# Main RiskShield orchestrator
# ===================================================================

class RiskShield:
    """Orchestrates all three risk sub-components.

    Called every candle while a position is open.  Extracts the relevant
    strategy state internally so callers do not need to pre-extract.

    Parameters
    ----------
    config : dict, optional
        Override defaults.  Recognised keys::

            conformal_alpha       (float, default 0.1)
            conformal_safety      (float, default 0.8)
            fallback_level        (int,   default 6)
            max_ruin_prob         (float, default 0.5)
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}

        self.conformal = ConformalKill(
            alpha=cfg.get('conformal_alpha', 0.1),
            safety_factor=cfg.get('conformal_safety', 0.8),
            fallback_level=cfg.get('fallback_level', 6),
        )
        self.liquidity = LiquidityGate(
            max_ruin_prob=cfg.get('max_ruin_prob', 0.5),
        )
        self.survival = MarginSurvival()
        self._max_cycle_bars = int(cfg.get('max_cycle_bars', _MAX_CYCLE_BARS))
        self._danger_abort_threshold = float(cfg.get('danger_abort_threshold', 0.8))
        self._stress_abort_threshold = float(cfg.get('stress_abort_threshold', 1.5))
        self._stress_abort_min_level = int(cfg.get('stress_abort_min_level', 2))

        # Per-cycle tracking for the Observer
        self._ruin_probs: list[float] = []
        self._last_reason: str = ''
        self._cycle_bar_count: int = 0
        self._total_checks: int = 0

    # ----- main entry point -----

    def check(self, strategy, market_state: Optional[dict] = None,
              stress_velocity: float = 0.0) -> Optional[dict]:
        """Evaluate whether to abort the current cycle.

        Called every candle while a position is open.

        Parameters
        ----------
        strategy
            The live strategy object — we read ``vars``, ``balance``,
            ``position``, ``price``, ``leverage``, ``fee_rate``, and ``hp``
            from it.
        market_state : dict, optional
            Additional market data.  Currently unused but reserved for
            future sub-components (e.g. order-book depth).

        Returns
        -------
        dict or None
            ``{'action': 'close_all', 'reason': ...}`` to abort, or
            ``None`` to continue.
        """
        # --- extract strategy state ---
        sv = getattr(strategy, 'vars', {})
        level = int(sv.get('level', 0))
        cycle_active = bool(sv.get('cycle_active', False))

        if not cycle_active:
            self._cycle_bar_count = 0
            return None

        self._cycle_bar_count += 1
        self._total_checks += 1

        # --- Duration abort: kill stuck cycles ONLY if losing ---
        # Aborting profitable positions destroys edge.  Shadow data showed
        # 62% of aborts killed cycles that would have recovered to TP.
        if self._cycle_bar_count > self._max_cycle_bars:
            session_pnl = float(getattr(strategy, 'balance', 0)) - \
                          float(sv.get('session_start_balance', getattr(strategy, 'balance', 0)))
            floating = getattr(strategy, 'position', None)
            floating_pnl = float(getattr(floating, 'pnl', 0)) if floating else 0
            total_pnl = session_pnl + floating_pnl
            if total_pnl <= 0:
                self._last_reason = 'duration_abort'
                return {'action': 'close_all', 'reason': f'duration:{self._cycle_bar_count}_bars_pnl_{total_pnl:.0f}'}
            # Profitable — extend, but hard-cap at 2x to prevent infinite runs
            elif self._cycle_bar_count > self._max_cycle_bars * 2:
                self._last_reason = 'duration_max'
                return {'action': 'close_all', 'reason': f'duration_max:{self._cycle_bar_count}_bars'}

        # --- High danger abort: kill at extreme danger when deep in levels ---
        # Level-proportional threshold: deeper levels get stricter thresholds
        # L3: base, L4: base-0.10, L5: base-0.20, L6+: max(0.35, ...)
        danger = (market_state or {}).get('danger', 0.5)
        level_threshold = max(0.35, self._danger_abort_threshold - (level - 3) * 0.10)
        if level >= 3 and danger > level_threshold:
            self._last_reason = 'danger_abort'
            return {'action': 'close_all', 'reason': f'danger:{danger:.3f}_at_L{level}_thresh_{level_threshold:.2f}'}

        # --- Structural stress abort (Chen 2026 R(t)) ---
        if level >= self._stress_abort_min_level and stress_velocity > self._stress_abort_threshold:
            self._last_reason = 'structural_stress'
            return {'action': 'close_all', 'reason': f'structural_stress:{stress_velocity:.3f}_at_L{level}'}

        equity = float(getattr(strategy, 'balance', 0.0))
        price = float(getattr(strategy, 'price', 0.0))
        leverage = float(getattr(strategy, 'leverage', 1.0))
        fee_rate = float(getattr(strategy, 'fee_rate', 0.0))

        hp = getattr(strategy, 'hp', {})
        multiplier = float(hp.get('sizing_factor', 2.0))
        base_size = float(hp.get('base_size_value', 1.0))
        max_levels = int(hp.get('max_levels', 6))

        # Estimate ATR from candles if available, else fall back to
        # fee_rate * price as a rough volatility proxy.
        atr = self._estimate_atr(strategy)

        # Estimate spread and TP distance
        spread = fee_rate * price  # fee_rate as spread proxy
        tp_distance = self._estimate_tp_distance(strategy, atr)

        # Estimate margin used: sum of all open level notionals / leverage
        margin_used = self._estimate_margin_used(
            level, base_size, multiplier, price, leverage,
        )

        # --- 4a: Conformal Kill ---
        kill, kill_reason = self.conformal.should_kill(level, equity, margin_used)
        if kill:
            self._last_reason = kill_reason
            return {'action': 'close_all', 'reason': f'conformal:{kill_reason}'}

        # --- 4b: Liquidity Gate (check next level affordability) ---
        if level < max_levels - 1:
            safe, gate_reason = self.liquidity.check(
                level=level, equity=equity, base_size=base_size,
                multiplier=multiplier, price=price, leverage=leverage,
                spread=spread, atr=atr, tp_distance=tp_distance,
            )
            if not safe:
                self._last_reason = gate_reason
                return {'action': 'close_all', 'reason': f'liquidity:{gate_reason}'}

        # --- 4c: Margin Survival (track ruin prob) ---
        ruin_p = self.survival.ruin_probability(
            level=level, equity=equity, base_size=base_size,
            multiplier=multiplier, atr=atr,
        )
        self._ruin_probs.append(ruin_p)

        self._last_reason = 'ok'
        return None

    # ----- cycle lifecycle -----

    def record_cycle(self, level_reached: int, pnl: float) -> None:
        """Called on cycle end to update calibration data and reset per-cycle state."""
        self.conformal.record_cycle(level_reached, pnl)
        self._ruin_probs = []
        self._cycle_bar_count = 0
        self._total_checks = 0

    @property
    def ruin_probs_this_cycle(self) -> list[float]:
        """Ruin probabilities computed at each candle this cycle."""
        return list(self._ruin_probs)

    # ----- serialisation -----

    def state_dict(self) -> dict:
        return {
            'conformal': self.conformal.state_dict(),
            'max_ruin_prob': self.liquidity.max_ruin_prob,
            'ruin_probs': list(self._ruin_probs),
        }

    def load_state_dict(self, d: dict) -> None:
        if 'conformal' in d:
            self.conformal.load_state_dict(d['conformal'])
        if 'max_ruin_prob' in d:
            self.liquidity.max_ruin_prob = float(d['max_ruin_prob'])
        self._ruin_probs = list(d.get('ruin_probs', []))

    # ----- internal helpers -----

    @staticmethod
    def _estimate_atr(strategy, period: int = 14) -> float:
        """Compute a simple ATR from the strategy's candle array.

        Falls back to ``fee_rate * price`` if candles are unavailable.
        """
        candles = getattr(strategy, 'candles', None)
        if candles is None or len(candles) < period + 1:
            price = float(getattr(strategy, 'price', 1.0))
            fee_rate = float(getattr(strategy, 'fee_rate', 0.0001))
            return max(fee_rate * price, 1e-12)

        # candle format: [timestamp, open, close, high, low, volume]
        tail = candles[-(period + 1):]
        highs = tail[:, 3].astype(np.float64)
        lows = tail[:, 4].astype(np.float64)
        closes = tail[:, 2].astype(np.float64)

        prev_close = closes[:-1]
        cur_high = highs[1:]
        cur_low = lows[1:]

        tr = np.maximum(
            cur_high - cur_low,
            np.maximum(
                np.abs(cur_high - prev_close),
                np.abs(cur_low - prev_close),
            ),
        )
        atr = float(np.mean(tr))
        return max(atr, 1e-12)

    @staticmethod
    def _estimate_tp_distance(strategy, atr: float) -> float:
        """Estimate take-profit distance from strategy HP or fall back to ATR."""
        hp = getattr(strategy, 'hp', {})

        # Try explicit TP pips
        tp_pips = hp.get('tp_pips')
        if tp_pips is not None:
            price = float(getattr(strategy, 'price', 1.0))
            # tp_pips is in pips (0.0001 for FX)
            pip_size = 0.0001 if price < 50 else 0.01
            return float(tp_pips) * pip_size

        # Try ATR-based TP
        tp_atr_mult = hp.get('tp_distance_atr_mult')
        if tp_atr_mult is not None:
            return float(tp_atr_mult) * atr

        # Default: 1x ATR
        return atr

    @staticmethod
    def _estimate_margin_used(level: int, base_size: float,
                              multiplier: float, price: float,
                              leverage: float) -> float:
        """Sum of margin across all open levels (0..level inclusive)."""
        multiplier = max(multiplier, 1.0)
        leverage = max(leverage, 1.0)
        total_notional = sum(
            base_size * multiplier ** i * price for i in range(level + 1)
        )
        return total_notional / leverage
