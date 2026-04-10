"""ContextBuilder — assembles enriched prompts for the LLM agent."""
from __future__ import annotations
import math
import numpy as np
import qengine.indicators as ta

_TAIL = 300


class ContextBuilder:
    """
    Builds system + user prompts for LLM consultations.
    Two modes: full (cloud APIs) and compact (local models).
    """

    SYSTEM_PROMPT = """You are a forex trader brain for a Martingale grid-hedge strategy.
Respond with ONLY a JSON object. No markdown, no explanation outside JSON.

JSON FORMAT:
{"signal":"long"|"short"|"hold"|"close_all"|"no_action","confidence":0.0-1.0,"sizing_pct":0.01-0.10,"tp_pips":null|number,"sl_pips":null|number,"hp_overrides":{},"standing_orders":[],"reasoning":"1-2 sentences","ttl_bars":120-480}

HP OVERRIDES: max_levels(1-12), sizing_factor(1.0-3.0), tp_value(pips), signal_mode(ema_rsi|ema_cross|rsi_only)

STRATEGY: Martingale/Surefire hedge. Opens position, if wrong opens larger hedges. Risk=bust at max levels. Your job: pick entries, adjust params per regime, manage risk, exit early if needed."""

    SYSTEM_PROMPT_FULL = """You are an expert forex/CFD trader operating as the brain of a Martingale grid-hedging strategy.

You make ALL trading decisions: entry timing, direction, position sizing, take-profit/stop-loss levels,
strategy hyperparameter adjustments, and exit timing.

RULES:
1. You will receive market data, indicators, position state, and your own trading journal.
2. You MUST respond with a valid JSON object (no markdown, no explanation outside JSON).
3. You are backtesting — you have NO knowledge of future prices. Decide based only on what you see.
4. Your decisions persist as "standing orders" until your next consultation.
5. Be concise in reasoning (max 2-3 sentences).

RESPONSE FORMAT (strict JSON):
{
  "signal": "long" | "short" | "hold" | "close_all" | "no_action",
  "confidence": 0.0-1.0,
  "sizing_pct": 0.01-0.10,
  "tp_pips": null or number,
  "sl_pips": null or number,
  "hp_overrides": {},
  "standing_orders": [],
  "reasoning": "brief explanation",
  "ttl_bars": 120-480
}

HYPERPARAMETERS YOU CAN ADJUST (hp_overrides):
- "max_levels": int (1-12) — max hedge levels before bust
- "sizing_factor": float (1.0-3.0) — multiplier between hedge levels (1.414=sqrt2, 2.0=martingale)
- "tp_value": float — take-profit in pips
- "signal_mode": "ema_rsi" | "ema_cross" | "rsi_only" — entry signal type
- "ema_fast": int — fast EMA period
- "ema_slow": int — slow EMA period

STRATEGY CONTEXT:
This is a Martingale/Surefire hedge strategy. It opens an initial position, and if price moves
against it, opens increasingly larger hedge positions at defined intervals. The key risk is
"busting" — reaching max levels and taking a large loss. Your job is to:
- Pick good entry points (direction + timing)
- Adjust parameters based on market regime (trending vs choppy)
- Manage risk by adjusting max_levels and sizing_factor
- Exit early (close_all) when you detect adverse conditions
- Let profitable cycles run (hold with appropriate TP)"""

    def __init__(self, compact: bool = False):
        self._compact = compact

    def build(self, strategy, trigger_reason: str, journal_context: str,
              danger_score: float = 0.5) -> tuple[str, str]:
        """Build (system_prompt, user_prompt) for the LLM."""
        if self._compact:
            return self._build_compact(strategy, trigger_reason, journal_context, danger_score)
        return self._build_full(strategy, trigger_reason, journal_context, danger_score)

    def _build_compact(self, strategy, trigger: str, journal_ctx: str,
                       danger: float) -> tuple[str, str]:
        """Compact prompt for local models — ~400 tokens user prompt."""
        parts = []

        # One-line trigger + price
        parts.append(f'TRIGGER:{trigger} PRICE:{strategy.price:.5f} DANGER:{danger:.2f}')

        # Compact indicators
        candles = strategy.candles
        if candles is not None and len(candles) >= 50:
            tail = candles[-_TAIL:] if len(candles) > _TAIL else candles
            parts.append(self._compact_indicators(tail))

        # Position (one line)
        if strategy.is_open:
            level = strategy.vars.get('level', 0) if hasattr(strategy, 'vars') else 0
            direction = 'LONG' if strategy.is_long else 'SHORT'
            parts.append(f'POS:{direction} L{level} PnL:{strategy.position.pnl:.2f} Entry:{strategy.position.entry_price:.5f}')
        else:
            parts.append('POS:FLAT')

        # Account (one line)
        parts.append(f'BAL:{strategy.balance:.0f} Trades:{strategy.trades_count}')

        # Key HPs
        if hasattr(strategy, 'hp'):
            hp = strategy.hp
            parts.append(f'HP: levels={hp.get("max_levels","?")} factor={hp.get("sizing_factor","?")} tp={hp.get("tp_value","?")}')

        # Journal (last 3 decisions only)
        if journal_ctx:
            lines = journal_ctx.split('\n')
            # Just thesis + last 3 decision lines
            compact_journal = []
            for line in lines:
                if line.startswith('Current thesis:') or line.startswith('Streak:'):
                    compact_journal.append(line)
                elif line.strip().startswith('Bar '):
                    compact_journal.append(line.strip())
            parts.append('JOURNAL: ' + ' | '.join(compact_journal[-4:]))

        return self.SYSTEM_PROMPT, '\n'.join(parts)

    def _compact_indicators(self, tail: np.ndarray) -> str:
        """One-line indicator summary."""
        sf = _safe_float
        atr = sf(ta.atr(tail, period=14))
        rsi = sf(ta.rsi(tail, period=14))
        adx = sf(ta.adx(tail, period=14))
        ema8 = sf(ta.ema(tail, period=8))
        ema21 = sf(ta.ema(tail, period=21))
        trend = 'UP' if ema8 > ema21 else 'DOWN'
        return f'ATR:{atr:.5f} RSI:{rsi:.0f} ADX:{adx:.0f} EMA:{trend}(8={ema8:.5f},21={ema21:.5f})'

    def _build_full(self, strategy, trigger: str, journal_ctx: str,
                    danger: float) -> tuple[str, str]:
        """Full prompt for cloud APIs."""
        parts = []
        parts.append(f'=== TRIGGER: {trigger} ===\n')
        parts.append(self._price_summary(strategy))
        parts.append(self._indicators(strategy))
        parts.append(f'\n=== DANGER SCORE: {danger:.3f} (0=safe, 1=dangerous) ===\n')
        parts.append(self._position_state(strategy))
        parts.append(self._account_state(strategy))
        parts.append(self._hp_state(strategy))
        if journal_ctx:
            parts.append(f'\n=== TRADING JOURNAL ===\n{journal_ctx}\n')
        parts.append('\nRespond with a JSON object. No markdown fences.')
        return self.SYSTEM_PROMPT_FULL, '\n'.join(parts)

    def _price_summary(self, strategy) -> str:
        candles = strategy.candles
        if candles is None or len(candles) < 2:
            return '=== PRICE: insufficient ===\n'
        lines = ['=== RECENT PRICE (last 8 candles) ===']
        tail = candles[-8:]
        for c in tail:
            lines.append(f'  O={c[1]:.5f} H={c[3]:.5f} L={c[4]:.5f} C={c[2]:.5f}')
        lines.append(f'Current: {strategy.price:.5f}')
        return '\n'.join(lines) + '\n'

    def _indicators(self, strategy) -> str:
        candles = strategy.candles
        if candles is None or len(candles) < 50:
            return '=== INDICATORS: insufficient ===\n'
        tail = candles[-_TAIL:] if len(candles) > _TAIL else candles
        sf = _safe_float

        atr_14 = sf(ta.atr(tail, period=14))
        atr_50 = sf(ta.atr(tail, period=50))
        rsi = sf(ta.rsi(tail, period=14))
        adx = sf(ta.adx(tail, period=14))
        ema8 = sf(ta.ema(tail, period=8))
        ema21 = sf(ta.ema(tail, period=21))
        ema50 = sf(ta.ema(tail, period=50))

        try:
            macd_r = ta.macd(tail)
            macd_h = sf(macd_r[2]) if hasattr(macd_r, '__getitem__') else 0.0
        except Exception:
            macd_h = 0.0

        trend = 'BULLISH' if ema8 > ema21 > ema50 else ('BEARISH' if ema8 < ema21 < ema50 else 'MIXED')

        lines = [
            '=== INDICATORS ===',
            f'ATR(14):{atr_14:.6f} ATR(50):{atr_50:.6f} Ratio:{atr_14/(atr_50+1e-12):.2f}',
            f'RSI:{rsi:.1f} ADX:{adx:.1f} MACD_hist:{macd_h:.6f}',
            f'EMA(8):{ema8:.5f} EMA(21):{ema21:.5f} EMA(50):{ema50:.5f} Trend:{trend}',
        ]
        return '\n'.join(lines) + '\n'

    def _position_state(self, strategy) -> str:
        lines = ['=== POSITION ===']
        if not strategy.is_open:
            lines.append('FLAT')
            return '\n'.join(lines) + '\n'

        d = 'LONG' if strategy.is_long else 'SHORT'
        lines.append(f'{d} entry={strategy.position.entry_price:.5f} pnl={strategy.position.pnl:.2f} qty={strategy.position.qty:.4f}')
        if hasattr(strategy, 'vars'):
            level = strategy.vars.get('level', 0)
            legs = strategy.vars.get('legs', [])
            lines.append(f'Level:{level} Legs:{len(legs)}')
        return '\n'.join(lines) + '\n'

    def _account_state(self, strategy) -> str:
        return f'=== ACCOUNT === Balance:{strategy.balance:.2f} Trades:{strategy.trades_count}\n'

    def _hp_state(self, strategy) -> str:
        if not hasattr(strategy, 'hp') or not strategy.hp:
            return ''
        hp = strategy.hp
        keys = ['max_levels', 'sizing_factor', 'tp_value', 'signal_mode', 'ema_fast', 'ema_slow']
        items = [f'{k}={hp[k]}' for k in keys if k in hp]
        return f'=== HPs === {", ".join(items)}\n' if items else ''


def _safe_float(x) -> float:
    if x is None:
        return 0.0
    f = float(x)
    return 0.0 if (math.isnan(f) or math.isinf(f)) else f
