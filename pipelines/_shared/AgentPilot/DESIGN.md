# AgentPilot — LLM-as-Trader Pipeline

## Overview

AgentPilot is a pipeline where an LLM (Claude, Gemini, GPT, or any provider) acts as the
full trading brain. The strategy becomes a pure executor — all decisions about entry, exit,
sizing, HP adjustment, and position management are made by the LLM agent.

## Architecture

```
AgentPilot (Pipeline)
├── MarketScanner          # Pre-filter: detects trigger events worth consulting the LLM
├── ContextBuilder         # Assembles enriched prompt from market state + journal
├── AgentBrain             # LLM API calls, caching, response parsing
├── Journal                # Structured memory across consultations
└── DecisionExecutor       # Applies LLM decisions to strategy (orders, HPs, standing orders)
```

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| LLM authority | Full autonomy | Strategy is pure executor; LLM decides everything |
| Call frequency | Event-driven + pre-filter | Structural triggers + market scanner + scheduled check-in |
| Context level | Enriched | Pre-computed indicators, regime, danger — LLM focuses on decisions |
| Memory model | Structured journal | JSON trading journal persists across calls within a backtest |
| Reproducibility | Low temp + cache | temperature=0.2 default, cache (state_hash -> decision), configurable |
| Decision format | Structured JSON | Signal, sizing, TP/SL, confidence, reasoning, HPs, standing orders |
| HP control | Dynamic | LLM can adjust strategy HPs per-cycle or on indicator shifts |
| Live mode | Pre-positioned | Standing orders set in advance; no blocking on API latency |
| LLM provider | Swappable | Reuses LLMEngine pattern: Claude, Gemini, OpenAI, any compatible |
| Target strategy | Martingale | First integration target |

## Data Flow Per Candle

```
Candle arrives
  |
  v
MarketScanner.scan(strategy)
  -> structural triggers: position opened, level-up, N bars elapsed, cycle ended
  -> market triggers: ATR breakout, EMA regime shift, volume spike, trend reversal
  -> scheduled: min_interval bars since last consult
  -> returns: (consult: bool, trigger_reason: str)
  |
  v
If consult=False -> DecisionExecutor.apply_standing(strategy)
  -> execute standing orders, enforce current signal
  -> DONE for this candle
  |
If consult=True:
  v
ContextBuilder.build(strategy, trigger_reason, journal)
  -> last N candles (OHLCV summary, not raw array)
  -> pre-computed indicators: ATR, EMA 8/21, RSI, ADX, MACD, Bollinger, Hurst
  -> position state: is_open, direction, tickets, unrealized PnL, level, legs
  -> account: balance, equity, drawdown
  -> journal: last N entries (LLM's past reasoning/thesis)
  -> current HPs, active standing orders
  -> trigger reason
  -> returns: (system_prompt, user_prompt)
  |
  v
AgentBrain.consult(system_prompt, user_prompt)
  -> compute state_hash from prompt content
  -> check cache: if hit, return cached decision
  -> call LLM API (provider-agnostic via LLMEngine pattern)
  -> parse JSON response into AgentDecision
  -> cache (state_hash -> decision)
  -> returns: AgentDecision
  |
  v
Journal.record(decision, trigger_reason, market_snapshot)
  -> append entry with timestamp, decision, reasoning, market state
  -> trim to max_entries window
  |
  v
DecisionExecutor.apply(decision, strategy)
  -> set signal (long/short/hold/close_all)
  -> adjust HPs on strategy.hp if decision includes hp_overrides
  -> set TP/SL prices
  -> update standing orders
  -> set sizing (confidence-scaled)
```

## Pipeline Hook Mapping

| Pipeline Hook | AgentPilot Behavior |
|---|---|
| `on_before()` | Scanner checks triggers. If fired -> full consult cycle. Else apply standing plan. |
| `gate_entry()` | Return True only if LLM's current signal matches entry direction. |
| `adjust_size()` | Return LLM's sizing * confidence scaling. |
| `filter_order()` | Pass through (decisions already encoded in gate + sizing). |
| `suggest_exit()` | If LLM said close_all, or standing TP/SL logic triggers -> return exit. |
| `on_open_position()` | Structural trigger -> consult LLM for position management plan. |
| `on_cycle_end()` | Record outcome in Journal. Consult LLM for post-mortem + next cycle HP. |

## AgentDecision Schema

```python
@dataclass
class AgentDecision:
    signal: str            # 'long', 'short', 'hold', 'close_all', 'no_action'
    confidence: float      # 0.0 - 1.0 (used to scale position size)
    sizing_pct: float      # position size as % of balance (e.g. 0.02 = 2%)
    tp_pips: float | None  # take-profit in pips (None = let me manage dynamically)
    sl_pips: float | None  # stop-loss in pips
    hp_overrides: dict     # strategy HP changes (e.g. {'max_levels': 3, 'sizing_factor': 1.5})
    standing_orders: list  # orders valid until next consultation
    reasoning: str         # free-text explanation (stored in journal + dashboard)
    ttl_bars: int          # how many bars this decision is valid for
```

## Trigger System

### Structural Triggers (always fire)
- Position just opened (`on_open_position`)
- Cycle just ended (`on_cycle_end`)
- Level-up detected (hedge filled, level increased)
- Position duration > `max_hold_bars` without consultation

### Market Triggers (pre-filter)
- ATR spike: current ATR > 1.5x rolling mean ATR
- Trend shift: EMA 8/21 crossover
- Momentum divergence: RSI crosses 30/70
- Volume anomaly: volume > 2x rolling mean
- Regime change: danger score crosses threshold (0.3 or 0.7)

### Scheduled Check-in
- Minimum `min_consult_interval` bars between consultations (default 240 = 4h on 1m)
- Ensures LLM reassesses even in quiet markets

## Journal Structure

```json
{
  "entries": [
    {
      "bar_index": 1234,
      "timestamp": "2024-01-15T14:30:00",
      "trigger": "ema_crossover",
      "decision": { ... AgentDecision ... },
      "market_snapshot": {
        "price": 1.0875,
        "atr": 0.0012,
        "rsi": 65.3,
        "trend": "bullish",
        "danger": 0.35
      },
      "outcome": null  // filled on cycle_end
    }
  ],
  "thesis": "Bullish momentum building, EMA alignment strong",
  "lessons": ["Last short was premature - wait for confirmation"],
  "regime_assessment": "trending-bullish",
  "consecutive_wins": 3,
  "consecutive_losses": 0
}
```

## Configuration

```python
DEFAULT_CONFIG = {
    'warmup': 50,                    # bars before pipeline activates
    'llm': {
        'provider': None,            # 'anthropic', 'openai', 'gemini' (auto-detect from env)
        'model': None,               # model name (provider default if None)
        'temperature': 0.2,          # low for reproducibility
        'max_tokens': 2048,
    },
    'scanner': {
        'min_consult_interval': 240, # min bars between consultations
        'atr_spike_mult': 1.5,       # ATR > mult * rolling_mean triggers consult
        'rsi_thresholds': [30, 70],  # RSI crossing these triggers consult
        'danger_thresholds': [0.3, 0.7],
        'max_hold_bars': 480,        # consult if position held this long without check
        'enabled': True,
    },
    'journal': {
        'max_entries': 50,           # rolling window of past decisions
        'include_in_prompt': 10,     # last N entries sent to LLM
    },
    'sizing': {
        'confidence_scaling': True,  # scale size by confidence score
        'min_confidence': 0.3,       # block entry below this confidence
        'max_sizing_pct': 0.05,      # cap at 5% of balance per entry
    },
    'cache': {
        'enabled': True,
        'max_size': 10000,           # max cached decisions
    },
}
```

## File Structure

```
pipelines/_shared/AgentPilot/
  __init__.py              # Main AgentPilot class (Pipeline subclass)
  config.py                # DEFAULT_CONFIG + deep merge
  market_scanner.py        # Trigger detection (structural + market + scheduled)
  context_builder.py       # Prompt assembly from market state + journal
  agent_brain.py           # LLM API calls, caching, response parsing
  journal.py               # Structured memory persistence
  decision.py              # AgentDecision dataclass + DecisionExecutor
  DESIGN.md                # This document
  models/                  # Reserved for cached decisions / model artifacts
```

## Backtesting Constraints

The LLM MUST NOT receive any information about future price paths. The context builder
enforces this by only providing:
- Historical candles up to current bar (candles[:index+1])
- Indicators computed from historical data only
- Account/position state at current bar
- Its own past reasoning (journal)

The system prompt explicitly instructs the LLM that it is backtesting and must not
assume knowledge of future prices.

## Provider Switching

Reuses the `LLMEngine` pattern from `qengine/services/llm_engine.py`:
- Auto-detect from env vars (ANTHROPIC_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY)
- Override via config: `{'llm': {'provider': 'gemini', 'model': 'gemini-2.5-flash'}}`
- Any OpenAI-compatible API supported via openai provider + custom base_url
