# Pipeline Architecture

Pipelines wrap any strategy with intelligence layers — entry gating, position sizing, exit management, order filtering, and outcome learning — without modifying strategy code.

```
Strategy alone:       signal ──> entry ──────────> manage ──> exit
Strategy + Pipeline:  signal ──> [gate] ──> [size] ──> [filter] ──> entry ──> [exit ctrl] ──> manage ──> exit ──> [learn]
```

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Hook Reference](#2-hook-reference)
3. [Composition Rules (Stacking)](#3-composition-rules)
4. [Built-in Components](#4-built-in-components)
5. [Layering Guide](#5-layering-guide)
6. [AI Adapter Examples](#6-ai-adapter-examples)
7. [State Persistence](#7-state-persistence)
8. [Running Pipelines](#8-running-pipelines)
9. [Directory Layout](#9-directory-layout)
10. [Accessing Strategy Data](#10-accessing-strategy-data)
11. [PipelineStats Reference](#11-pipelinestats-reference)
12. [Complete Example: GridPilot](#12-complete-example-gridpilot)
13. [Autopilot](#13-autopilot)

---

## 1. Quick Start

Create `pipelines/{your_user_id}/MyPipeline/__init__.py`:

```python
from qengine.framework.base import Pipeline


class MyPipeline(Pipeline):
    name = 'MyPipeline'

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.blocked = 0

    def gate_entry(self, strategy) -> bool:
        # Block entries when price is below 200-bar moving average
        if len(strategy.candles) < 200:
            return True
        ma = strategy.candles[-200:, 2].mean()
        if strategy.price < ma:
            self.blocked += 1
            return False
        return True

    def get_stats(self) -> dict:
        return {'entries_blocked': self.blocked}
```

That's a complete pipeline. Attach it to any strategy via the dashboard or config.

---

## 2. Hook Reference

### Complete Hook Lifecycle

```
Every candle:
  1. on_before(strategy)                    ── observe, update internal state

Entry decision (when strategy wants to enter):
  2. gate_entry(strategy) -> bool           ── allow or block
  3. adjust_size(strategy, qty, side) -> qty ── scale position size
  4. filter_order(strategy, intent) -> intent ── modify or cancel individual orders

While position is open (every candle):
  5. suggest_exit(strategy) -> dict|None     ── graduated exit control

Position events:
  6. on_open_position(strategy)             ── track entry conditions
  7. on_cycle_end(pnl, strategy)            ── learn from outcome
```

### Hook Signatures

| Hook | Signature | Default | When |
|------|-----------|---------|------|
| `on_before` | `(strategy) -> None` | no-op | Every candle |
| `gate_entry` | `(strategy) -> bool` | `True` | Before entry |
| `adjust_size` | `(strategy, qty, side) -> float` | return qty | After gate allows |
| `suggest_exit` | `(strategy) -> dict\|None` | delegates to `should_abort` | Every candle while in position |
| `should_abort` | `(strategy) -> bool` | `False` | Called by default `suggest_exit` |
| `filter_order` | `(strategy, OrderIntent) -> OrderIntent\|None` | return intent | Before each order hits broker |
| `on_open_position` | `(strategy) -> None` | no-op | Position just opened |
| `on_cycle_end` | `(pnl, strategy) -> None` | no-op | Position just closed |

### `on_before(strategy)`

Called every candle after the strategy's `before()`. Use for updating scores, features, indicators.

```python
def on_before(self, strategy):
    self.danger = self.scorer.update(self.extract_features(strategy))
```

### `gate_entry(strategy) -> bool`

Called when the strategy wants to enter (`should_long` or `should_short` returned True). Return `True` to allow, `False` to block.

```python
def gate_entry(self, strategy) -> bool:
    return self.danger < self.threshold
```

### `adjust_size(strategy, qty, side) -> float`

Called after the gate allows entry, before orders are submitted. Receives total proposed quantity and trade direction (`'long'` or `'short'`). Return the adjusted quantity — return 0 to cancel the entry entirely.

```python
def adjust_size(self, strategy, qty: float, side: str) -> float:
    # Kelly criterion sizing
    win_rate = self.estimated_win_rate
    win_loss_ratio = self.avg_win / max(self.avg_loss, 1e-10)
    kelly_fraction = win_rate - (1 - win_rate) / win_loss_ratio
    kelly_fraction = max(0.0, min(kelly_fraction, 0.25))  # cap at 25%
    return qty * kelly_fraction / 0.25  # scale relative to max
```

### `suggest_exit(strategy) -> dict | None`

Called every candle while a position is open. Return `None` for no action, or a dict:

| Action | Dict | Effect |
|--------|------|--------|
| Close all | `{'action': 'close_all'}` | Force-close entire position |
| Partial close | `{'action': 'partial_close', 'pct': 0.5}` | Close 50% of position |
| Tighten SL | `{'action': 'tighten_sl', 'price': 1.234}` | Move stop loss |
| Set TP | `{'action': 'set_tp', 'price': 1.250}` | Move take profit |

```python
def suggest_exit(self, strategy) -> dict | None:
    if self.danger > 0.9:
        return {'action': 'close_all'}
    elif self.danger > 0.7 and strategy.position.pnl < 0:
        return {'action': 'partial_close', 'pct': 0.5}
    elif self.danger > 0.6:
        return {'action': 'tighten_sl', 'price': strategy.price - 0.001}
    return None
```

### `should_abort(strategy) -> bool`

Simple convenience method. The default `suggest_exit()` delegates to it. Override this for basic binary abort, or override `suggest_exit()` for richer control.

```python
def should_abort(self, strategy) -> bool:
    return strategy.vars.get('level', 0) >= 5 and self.danger > 0.8
```

### `filter_order(strategy, OrderIntent) -> OrderIntent | None`

Called before each order is submitted to the broker. The `OrderIntent` is a lightweight dataclass:

```python
@dataclass
class OrderIntent:
    qty: float       # order quantity
    price: float     # order price
    side: str        # 'buy' or 'sell'
    type: str        # 'market', 'limit', 'stop'
    is_entry: bool   # True for entry orders
    symbol: str
    exchange: str
```

Return the (possibly modified) intent, or `None` to cancel the order.

```python
def filter_order(self, strategy, intent):
    # Block orders during high-spread conditions
    if intent.is_entry and self.current_spread > self.max_spread:
        return None
    # Add slippage buffer to limit orders
    if intent.type == 'limit' and intent.side == 'buy':
        intent.price *= 0.999  # improve fill price
    return intent
```

### `on_open_position(strategy)` / `on_cycle_end(pnl, strategy)`

Lifecycle hooks for tracking entry conditions and learning from outcomes.

```python
def on_open_position(self, strategy):
    self.entry_danger = self.danger
    self.entry_index = strategy.index
    self.agent.start_episode()

def on_cycle_end(self, pnl: float, strategy):
    self.agent.end_episode(reward=pnl)
    self.outcomes.append({'pnl': pnl, 'danger': self.entry_danger})
```

---

## 3. Composition Rules

Multiple pipelines can be stacked. Each hook has a specific composition rule:

| Hook | Rule | Meaning |
|------|------|---------|
| `on_before` | All run | Every pipeline observes |
| `gate_entry` | **AND** | All must allow (any block = blocked) |
| `adjust_size` | **Chain** | Each scales previous output (multiplicative) |
| `filter_order` | **Chain** | Sequential, any `None` cancels |
| `suggest_exit` | **Most aggressive** | `close_all` > `partial_close` > `tighten_sl` > `set_tp` |
| `on_open_position` | All run | Every pipeline tracks |
| `on_cycle_end` | All run | Every pipeline learns |

```python
# Stacking example: danger-based gate + news filter + ML sizer
result = backtest(
    ...,
    pipeline_configs=[
        {'name': 'GridPilot', 'gate': {'percentile': 75}},
        {'name': 'NewsFilter', 'calendar_url': '...'},
        {'name': 'MLSizer', 'model_path': 'weights/sizer.pt'},
    ],
)
```

If GridPilot allows but NewsFilter blocks → entry blocked (AND).
If MLSizer scales qty to 0.5x and GridPilot's adjust_size returns qty unchanged → 0.5x (chain).

---

## 4. Built-in Components

Reusable building blocks in `qengine.framework.components`.

### DangerScorer

Real-time market risk scoring. 7 weighted features, Welford online normalization, output in [0, 1].

```python
from qengine.framework.components.danger_scorer import DangerScorer

scorer = DangerScorer({'warmup': 50})
score = scorer.update({'D1_range_atr': 3.2, '5m_chop': 65.0, '5m_adx': 18.0})
```

| Feature | Weight | Meaning |
|---------|--------|---------|
| `D1_range_atr` | 0.30 | Daily range / ATR (inverted) |
| `5m_chop` | 0.15 | 5-min choppiness |
| `15m_chop` | 0.15 | 15-min choppiness |
| `D1_chop` | 0.10 | Daily choppiness |
| `5m_adx` | 0.10 | ADX (inverted: low = choppy) |
| `5m_hurst` | 0.10 | Hurst exponent (inverted) |
| `1H_atr_ratio` | 0.10 | Short ATR / long ATR |

### EntryGate

Blocks entries when danger exceeds a rolling percentile threshold.

```python
from qengine.framework.components.entry_gate import EntryGate

gate = EntryGate({'percentile': 75, 'window': 500})
gate.observe(score)
if gate.should_allow(score):
    # entry allowed
```

### QAbort

Tabular Q-learning agent. 1,625 states (13 levels x 5 duration x 5 danger_entry x 5 danger_now), 2 actions (continue/abort).

```python
from qengine.framework.components.q_abort import QAbort

abort = QAbort({'alpha': 0.01, 'gamma': 0.95, 'epsilon': 0.0})
abort.start_episode()
action = abort.decide(level=3, duration_bars=15, danger_entry=0.4, danger_now=0.7)
abort.end_episode(reward=pnl)
```

---

## 5. Layering Guide

### Level 0: Pass-Through
```python
class NoOp(Pipeline):
    name = 'NoOp'
    def get_stats(self): return {}
```

### Level 1: Entry Filter
```python
class SpreadFilter(Pipeline):
    name = 'SpreadFilter'
    def __init__(self, config=None):
        self.max_spread = (config or {}).get('max_spread_pips', 3)
        self.blocked = 0
        self._spread = 0

    def on_before(self, strategy):
        self._spread = strategy.price_to_pips(strategy.spread) if hasattr(strategy, 'spread') else 0

    def gate_entry(self, strategy):
        if self._spread > self.max_spread:
            self.blocked += 1
            return False
        return True

    def get_stats(self): return {'blocked': self.blocked}
```

### Level 2: Danger + Gate
Compose DangerScorer + EntryGate. See [GridPilot](#12-complete-example-gridpilot).

### Level 3: Full Stack (Gate + Size + Abort + Learning)
All hooks active: gate entries, adjust sizing by danger, abort losing cycles, learn via Q-table.

### Level 4: ML Models
PyTorch/TensorFlow models for sizing, exit decisions, or feature extraction. See [AI Adapter Examples](#6-ai-adapter-examples).

### Level 5: Agentic Systems
LLM-powered analysis, MCP tool calling, multi-agent ensembles. See [AI Adapter Examples](#6-ai-adapter-examples).

---

## 6. AI Adapter Examples

The pipeline architecture is a universal adapter — any AI/ML technique maps onto the hook interface. Below are concrete examples showing how.

### Neural Network (PyTorch) — Sizing + Exit

```python
import os, torch
from qengine.framework.base import Pipeline


class NeuralPilot(Pipeline):
    name = 'NeuralPilot'

    def __init__(self, config=None):
        config = config or {}
        self.model = self._build_model()
        weights = os.path.join(os.path.dirname(__file__), 'weights', 'model.pt')
        if os.path.exists(weights):
            self.model.load_state_dict(torch.load(weights, weights_only=True))
        self.model.eval()
        self._features = None
        self._training_buffer = []

    def _build_model(self):
        return torch.nn.Sequential(
            torch.nn.Linear(20, 64), torch.nn.ReLU(),
            torch.nn.Linear(64, 32), torch.nn.ReLU(),
            torch.nn.Linear(32, 3),  # [size_scale, abort_prob, confidence]
        )

    def on_before(self, strategy):
        candles = strategy.candles
        if candles is None or len(candles) < 20:
            self._features = None
            return
        close = candles[-20:, 2]
        returns = (close[1:] / close[:-1]) - 1
        vol = returns.std()
        self._features = torch.tensor(
            list(returns) + [vol], dtype=torch.float32
        ).unsqueeze(0)

    def adjust_size(self, strategy, qty, side):
        if self._features is None:
            return qty
        with torch.no_grad():
            out = self.model(self._features)
        size_scale = torch.sigmoid(out[0, 0]).item()  # 0-1
        return qty * max(0.1, size_scale)

    def suggest_exit(self, strategy):
        if self._features is None or not strategy.position.is_open:
            return None
        with torch.no_grad():
            out = self.model(self._features)
        abort_prob = torch.sigmoid(out[0, 1]).item()
        if abort_prob > 0.8:
            return {'action': 'close_all'}
        elif abort_prob > 0.6:
            return {'action': 'partial_close', 'pct': abort_prob}
        return None

    def on_cycle_end(self, pnl, strategy):
        if self._features is not None:
            self._training_buffer.append((self._features.clone(), pnl))

    def save_state(self, path):
        os.makedirs(path, exist_ok=True)
        torch.save(self.model.state_dict(), os.path.join(path, 'model.pt'))

    def load_state(self, path):
        p = os.path.join(path, 'model.pt')
        if os.path.exists(p):
            self.model.load_state_dict(torch.load(p, weights_only=True))
            self.model.eval()

    def get_stats(self):
        return {'training_samples': len(self._training_buffer)}
```

### Genetic Algorithm — Evolved Filter Parameters

```python
import random, json, os
from qengine.framework.base import Pipeline


class GAFilter(Pipeline):
    name = 'GAFilter'

    def __init__(self, config=None):
        config = config or {}
        # Chromosome: [danger_threshold, min_adx, max_spread, size_scale]
        self.chromosome = config.get('chromosome', [0.7, 20.0, 3.0, 1.0])
        self.population = config.get('population', [])
        self.fitness_log = []
        self._danger = 0.5
        self._adx = 25.0

    def on_before(self, strategy):
        candles = strategy.candles
        if candles is not None and len(candles) >= 14:
            import qengine.indicators as ta
            self._adx = ta.adx(candles, 14) or 25.0

    def gate_entry(self, strategy):
        return self._danger < self.chromosome[0] and self._adx > self.chromosome[1]

    def adjust_size(self, strategy, qty, side):
        return qty * self.chromosome[3]

    def on_cycle_end(self, pnl, strategy):
        self.fitness_log.append(pnl)

    def save_state(self, path):
        os.makedirs(path, exist_ok=True)
        fitness = sum(self.fitness_log)
        # Add current chromosome + fitness to population
        self.population.append({'chromosome': self.chromosome, 'fitness': fitness})
        # Evolve: select top 50%, crossover + mutate
        self.population.sort(key=lambda x: x['fitness'], reverse=True)
        top = self.population[:max(len(self.population) // 2, 2)]
        new_pop = list(top)
        while len(new_pop) < 20:
            p1, p2 = random.sample(top, 2)
            child = [(a + b) / 2 for a, b in zip(p1['chromosome'], p2['chromosome'])]
            child = [g + random.gauss(0, 0.1) for g in child]  # mutation
            new_pop.append({'chromosome': child, 'fitness': 0})
        self.population = new_pop
        # Next iteration uses best chromosome
        self.chromosome = self.population[0]['chromosome']
        with open(os.path.join(path, 'population.json'), 'w') as f:
            json.dump({'population': self.population, 'chromosome': self.chromosome}, f)

    def load_state(self, path):
        p = os.path.join(path, 'population.json')
        if os.path.exists(p):
            with open(p) as f:
                data = json.load(f)
            self.population = data.get('population', [])
            self.chromosome = data.get('chromosome', self.chromosome)

    def get_stats(self):
        return {
            'chromosome': [round(g, 4) for g in self.chromosome],
            'population_size': len(self.population),
            'generation_fitness': round(sum(self.fitness_log), 4),
        }
```

### Bayesian Inference — Posterior-Updated Gate

```python
import math
from qengine.framework.base import Pipeline


class BayesianGate(Pipeline):
    name = 'BayesianGate'

    def __init__(self, config=None):
        config = config or {}
        # Beta distribution prior: P(win) ~ Beta(alpha, beta)
        self.alpha = config.get('prior_alpha', 2.0)  # prior wins
        self.beta = config.get('prior_beta', 2.0)     # prior losses
        self.min_prob = config.get('min_win_prob', 0.55)
        self._features = {}

    def gate_entry(self, strategy):
        # Block if posterior P(win) < threshold
        posterior_mean = self.alpha / (self.alpha + self.beta)
        # Also consider posterior uncertainty
        posterior_std = math.sqrt(
            (self.alpha * self.beta) /
            ((self.alpha + self.beta) ** 2 * (self.alpha + self.beta + 1))
        )
        # Conservative: use lower bound of 1-sigma interval
        conservative_estimate = posterior_mean - posterior_std
        return conservative_estimate >= self.min_prob

    def on_cycle_end(self, pnl, strategy):
        # Bayesian update: observed win/loss updates Beta posterior
        if pnl > 0:
            self.alpha += 1
        else:
            self.beta += 1

    def save_state(self, path):
        import os, json
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, 'posterior.json'), 'w') as f:
            json.dump({'alpha': self.alpha, 'beta': self.beta}, f)

    def load_state(self, path):
        import os, json
        p = os.path.join(path, 'posterior.json')
        if os.path.exists(p):
            with open(p) as f:
                d = json.load(f)
            self.alpha = d['alpha']
            self.beta = d['beta']

    def get_stats(self):
        mean = self.alpha / (self.alpha + self.beta)
        return {
            'posterior_mean': round(mean, 4),
            'alpha': round(self.alpha, 2),
            'beta': round(self.beta, 2),
            'observations': int(self.alpha + self.beta - 4),  # subtract prior
        }
```

### Fuzzy Logic — Entry + Exit

```python
from qengine.framework.base import Pipeline


class FuzzyPilot(Pipeline):
    name = 'FuzzyPilot'

    def __init__(self, config=None):
        self._danger = 0.5
        self._trend_strength = 0.5
        self._volatility = 0.5

    def on_before(self, strategy):
        candles = strategy.candles
        if candles is None or len(candles) < 50:
            return
        close = candles[-50:, 2]
        # Compute fuzzy inputs
        self._trend_strength = self._fuzzy_trend(close)
        self._volatility = self._fuzzy_volatility(close)
        self._danger = self._defuzzify_danger()

    def _fuzzy_trend(self, close):
        """Membership: 0=no trend, 1=strong trend"""
        ma_short = close[-10:].mean()
        ma_long = close.mean()
        diff = abs(ma_short - ma_long) / ma_long
        return min(diff * 50, 1.0)  # scale to [0, 1]

    def _fuzzy_volatility(self, close):
        """Membership: 0=calm, 1=volatile"""
        returns = close[1:] / close[:-1] - 1
        vol = returns.std() * 100
        return min(vol / 2.0, 1.0)  # scale to [0, 1]

    def _defuzzify_danger(self):
        """Combine fuzzy inputs using Mamdani inference."""
        # Rule 1: IF low_trend AND high_vol THEN high_danger
        r1 = min(1 - self._trend_strength, self._volatility)
        # Rule 2: IF high_trend AND low_vol THEN low_danger
        r2 = min(self._trend_strength, 1 - self._volatility)
        # Defuzzify: weighted average
        if r1 + r2 == 0:
            return 0.5
        return (r1 * 0.9 + r2 * 0.1) / (r1 + r2)

    def gate_entry(self, strategy):
        return self._danger < 0.7

    def suggest_exit(self, strategy):
        if self._danger > 0.9:
            return {'action': 'close_all'}
        elif self._danger > 0.75:
            return {'action': 'tighten_sl', 'price': strategy.price * 0.998}
        return None

    def get_stats(self):
        return {
            'danger': round(self._danger, 4),
            'trend': round(self._trend_strength, 4),
            'volatility': round(self._volatility, 4),
        }
```

### Multi-Agent Ensemble — Voting System

```python
from qengine.framework.base import Pipeline
from qengine.framework.components.danger_scorer import DangerScorer
from qengine.framework.components.q_abort import QAbort


class EnsemblePilot(Pipeline):
    name = 'EnsemblePilot'

    def __init__(self, config=None):
        config = config or {}
        # Multiple independent agents
        self.agents = {
            'danger': DangerScorer(config.get('scorer', {})),
            'q_abort': QAbort(config.get('abort', {})),
        }
        self._danger = 0.5
        self._votes = {}

    def on_before(self, strategy):
        features = self._extract_features(strategy)
        self._danger = self.agents['danger'].update(features)

    def gate_entry(self, strategy):
        # Majority vote: each agent votes allow/block
        votes = {
            'danger': self._danger < 0.7,
            'momentum': self._check_momentum(strategy),
            'volume': self._check_volume(strategy),
        }
        self._votes = votes
        allow_count = sum(1 for v in votes.values() if v)
        return allow_count > len(votes) / 2  # majority must allow

    def suggest_exit(self, strategy):
        if not self.agents['q_abort'].enabled:
            return None
        level = strategy.vars.get('level', 0)
        action = self.agents['q_abort'].decide(
            level=level, duration_bars=0,
            danger_entry=0.5, danger_now=self._danger,
        )
        if action == 'abort':
            return {'action': 'close_all'}
        return None

    def on_cycle_end(self, pnl, strategy):
        self.agents['q_abort'].end_episode(reward=pnl)

    def _check_momentum(self, strategy):
        candles = strategy.candles
        if candles is None or len(candles) < 20:
            return True
        return candles[-1, 2] > candles[-20:, 2].mean()

    def _check_volume(self, strategy):
        candles = strategy.candles
        if candles is None or len(candles) < 20:
            return True
        return candles[-1, 5] > candles[-20:, 5].mean() * 0.5

    def _extract_features(self, strategy):
        return {}

    def get_stats(self):
        return {'last_votes': self._votes, 'danger': round(self._danger, 4)}
```

### LLM / Agentic — API-Driven Exit Advisor

```python
import json
from qengine.framework.base import Pipeline


class LLMAdvisor(Pipeline):
    name = 'LLMAdvisor'

    def __init__(self, config=None):
        config = config or {}
        self.api_key = config.get('api_key', '')
        self.model = config.get('model', 'claude-sonnet-4-20250514')
        self._last_advice = None
        self._candle_count = 0
        self._check_interval = config.get('check_every_n_candles', 50)

    def suggest_exit(self, strategy):
        if not strategy.position.is_open:
            return None
        self._candle_count += 1
        if self._candle_count % self._check_interval != 0:
            return self._last_advice  # reuse cached advice between checks

        # Build context for LLM
        context = self._build_context(strategy)
        advice = self._query_llm(context)
        self._last_advice = advice
        return advice

    def _build_context(self, strategy):
        candles = strategy.candles[-20:] if strategy.candles is not None else []
        return {
            'symbol': strategy.symbol,
            'position_side': 'long' if strategy.is_long else 'short',
            'entry_price': strategy.position.entry_price,
            'current_price': strategy.price,
            'pnl_pct': round(strategy.position.pnl_percentage, 2),
            'bars_open': strategy.index,
            'recent_closes': [round(c[2], 5) for c in candles[-10:]],
        }

    def _query_llm(self, context):
        try:
            import httpx
            resp = httpx.post(
                'https://api.anthropic.com/v1/messages',
                headers={'x-api-key': self.api_key, 'anthropic-version': '2023-06-01'},
                json={
                    'model': self.model,
                    'max_tokens': 100,
                    'messages': [{'role': 'user', 'content':
                        f'Trading position context: {json.dumps(context)}. '
                        'Respond with ONLY a JSON object: '
                        '{"action": "none"} or {"action": "close_all"} or '
                        '{"action": "partial_close", "pct": 0.5} or '
                        '{"action": "tighten_sl", "price": 1.234}'}],
                },
                timeout=10.0,
            )
            text = resp.json()['content'][0]['text']
            result = json.loads(text)
            if result.get('action') == 'none':
                return None
            return result
        except Exception:
            return None

    def get_stats(self):
        return {'last_advice': self._last_advice, 'queries': self._candle_count // self._check_interval}
```

### MCP Tool-Use — External Analysis Pipeline

```python
import json
from qengine.framework.base import Pipeline


class MCPPipeline(Pipeline):
    name = 'MCPPipeline'

    def __init__(self, config=None):
        config = config or {}
        self.server_url = config.get('server_url', 'http://localhost:8080')
        self._client = None
        self._analysis = {}

    def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.Client(base_url=self.server_url, timeout=5.0)
        return self._client

    def on_before(self, strategy):
        # Call MCP tool for market analysis (throttled to every 10 candles)
        if strategy.index % 10 != 0:
            return
        try:
            client = self._get_client()
            resp = client.post('/tools/analyze_market', json={
                'symbol': strategy.symbol,
                'price': strategy.price,
                'candles': strategy.candles[-50:, 2].tolist() if strategy.candles is not None else [],
            })
            self._analysis = resp.json()
        except Exception:
            pass

    def gate_entry(self, strategy):
        risk_level = self._analysis.get('risk_level', 'medium')
        return risk_level != 'extreme'

    def adjust_size(self, strategy, qty, side):
        confidence = self._analysis.get('confidence', 0.5)
        return qty * max(0.1, confidence)

    def suggest_exit(self, strategy):
        action = self._analysis.get('exit_recommendation')
        if action and action != 'hold':
            return {'action': action, **self._analysis.get('exit_params', {})}
        return None

    def get_stats(self):
        return {'last_analysis': self._analysis}
```

### Reinforcement Learning (DQN/PPO) — Full Control

```python
import numpy as np
from qengine.framework.base import Pipeline


class RLPilot(Pipeline):
    name = 'RLPilot'

    def __init__(self, config=None):
        config = config or {}
        self.state_dim = config.get('state_dim', 30)
        self.action_space = ['hold', 'close_all', 'partial_25', 'partial_50', 'tighten_sl']
        self._state = None
        self._prev_state = None
        self._prev_action = None
        self._episode_states = []
        # Q-network (could be DQN, PPO, etc.)
        self.q_table = np.zeros((1000, len(self.action_space)))  # simplified
        self.epsilon = config.get('epsilon', 0.1)
        self.alpha = config.get('alpha', 0.01)

    def on_before(self, strategy):
        self._state = self._encode_state(strategy)

    def _encode_state(self, strategy):
        """Encode strategy state into fixed-size vector."""
        candles = strategy.candles
        if candles is None or len(candles) < 20:
            return np.zeros(self.state_dim)
        close = candles[-20:, 2]
        returns = np.diff(close) / close[:-1]
        vol = returns.std()
        pnl_pct = strategy.position.pnl_percentage if strategy.position.is_open else 0
        # Hash to table index
        features = np.concatenate([returns, [vol, pnl_pct]])
        return features[:self.state_dim]

    def _state_index(self):
        if self._state is None:
            return 0
        return int(abs(hash(self._state.tobytes())) % len(self.q_table))

    def suggest_exit(self, strategy):
        if not strategy.position.is_open or self._state is None:
            return None
        idx = self._state_index()

        # Epsilon-greedy action selection
        if np.random.random() < self.epsilon:
            action_idx = np.random.randint(len(self.action_space))
        else:
            action_idx = np.argmax(self.q_table[idx])

        action_name = self.action_space[action_idx]
        self._prev_state = idx
        self._prev_action = action_idx

        if action_name == 'close_all':
            return {'action': 'close_all'}
        elif action_name == 'partial_25':
            return {'action': 'partial_close', 'pct': 0.25}
        elif action_name == 'partial_50':
            return {'action': 'partial_close', 'pct': 0.50}
        elif action_name == 'tighten_sl':
            return {'action': 'tighten_sl', 'price': strategy.price * 0.998}
        return None  # 'hold'

    def on_cycle_end(self, pnl, strategy):
        # Q-learning update
        if self._prev_state is not None and self._prev_action is not None:
            old_q = self.q_table[self._prev_state, self._prev_action]
            self.q_table[self._prev_state, self._prev_action] = (
                old_q + self.alpha * (pnl - old_q)
            )
        self._prev_state = None
        self._prev_action = None

    def save_state(self, path):
        import os
        os.makedirs(path, exist_ok=True)
        np.save(os.path.join(path, 'q_table.npy'), self.q_table)

    def load_state(self, path):
        import os
        p = os.path.join(path, 'q_table.npy')
        if os.path.exists(p):
            self.q_table = np.load(p)

    def get_stats(self):
        nonzero = self.q_table[self.q_table != 0]
        return {
            'states_visited': int(np.sum(np.any(self.q_table != 0, axis=1))),
            'q_mean': round(float(np.mean(nonzero)), 6) if len(nonzero) > 0 else 0,
            'epsilon': self.epsilon,
        }
```

---

## 7. State Persistence

Pipelines that learn should implement `save_state` and `load_state`. Called by autopilot between iterations.

```python
def save_state(self, path: str):
    os.makedirs(path, exist_ok=True)
    np.save(os.path.join(path, 'weights.npy'), self.weights)
    with open(os.path.join(path, 'config.json'), 'w') as f:
        json.dump(self.params, f)

def load_state(self, path: str):
    w_path = os.path.join(path, 'weights.npy')
    if os.path.exists(w_path):
        self.weights = np.load(w_path)
```

---

## 8. Running Pipelines

### Dashboard
1. Open **Backtest** view
2. Click the **Pipeline** tab in the config panel
3. Select a pipeline from the dropdown
4. Run the backtest

### Programmatic API
```python
from qengine.research.backtest import backtest
from qengine.research.candles import get_candles

warmup, candles = get_candles('OANDA', 'EUR-USD', '2020-01-01', '2020-12-31')

result = backtest(
    config={'starting_balance': 10_000, 'fee': 0, 'type': 'cfd', 'exchange': 'OANDA', 'warm_up_candles': 240},
    routes=[{'exchange': 'OANDA', 'strategy': 'Surefire', 'symbol': 'EUR-USD', 'timeframe': '5m'}],
    data_routes=[],
    candles=candles,
    warmup_candles=warmup,
    generate_equity_curve=True,
    pipeline_configs=[
        {'name': 'GridPilot', 'gate': {'percentile': 80}},
    ],
)
```

### Live Trading
```json
{
  "pipelines": [
    {"name": "GridPilot", "gate": {"percentile": 75}, "abort": {"enabled": true}}
  ]
}
```

---

## 9. Directory Layout

```
pipelines/
    _shared/              # Available to ALL users (shipped with repo)
        GridPilot/
            __init__.py
    _admin/               # Admin-only (editable by admins)
        NeuralPilot/
            __init__.py
            model.py
            weights/
    {user_id}/            # User-specific
        MyExperiment/
            __init__.py
            data/
```

Pipelines are auto-discovered from the filesystem. Any directory containing an `__init__.py` with a class extending `Pipeline` is registered automatically.

---

## 10. Accessing Strategy Data

Inside hooks, the `strategy` argument gives full access:

```python
# Price and candles
strategy.candles              # 2D numpy [time, open, close, high, low, volume]
strategy.price                # current close
strategy.high / strategy.low  # current high/low

# Position
strategy.position.is_open
strategy.position.entry_price
strategy.position.pnl
strategy.position.pnl_percentage

# Strategy variables
strategy.vars.get('level', 0)
strategy.balance
strategy.index

# Multi-timeframe
strategy.get_candles(strategy.exchange, strategy.symbol, '4h')

# Indicators
import qengine.indicators as ta
rsi = ta.rsi(strategy.candles, 14)
atr = ta.atr(strategy.candles, 14)
```

---

## 11. PipelineStats Reference

Helper class for tracking pipeline decisions. Used by the frontend for charts and analytics.

```python
from qengine.framework.stats import PipelineStats

stats = PipelineStats()
stats.record_danger(timestamp, score)
stats.record_gate(timestamp, score, allowed, threshold=threshold)
stats.record_abort(timestamp, level, danger, action, q_values=[q_cont, q_abort])
stats.start_cycle(timestamp, danger_at_entry)
stats.end_cycle(pnl=pnl, exit_reason='tp_hit', level=3)
stats.record_size_adjustment(timestamp, original_qty, adjusted_qty, side)
stats.record_exit_suggestion(timestamp, action, details)
stats.record_order_filter(timestamp, side, cancelled)
```

---

## 12. Complete Example: GridPilot

The shipped `GridPilot` pipeline composes DangerScorer + EntryGate + QAbort:

```python
from qengine.framework.base import Pipeline
from qengine.framework.stats import PipelineStats
from qengine.framework.components.danger_scorer import DangerScorer
from qengine.framework.components.q_abort import QAbort
from qengine.framework.components.entry_gate import EntryGate


class GridPilot(Pipeline):
    name = 'GridPilot'

    def __init__(self, config=None):
        config = config or {}
        self.scorer = DangerScorer(config.get('scorer', {}))
        self.gate = EntryGate(config.get('gate', {}))
        self.abort = QAbort(config.get('abort', {}))
        self._stats = PipelineStats()

    def on_before(self, strategy):
        features = extract_features(strategy)
        score = self.scorer.update(features)
        self.gate.observe(score)
        self._stats.record_danger(strategy.current_candle[0], score)

    def gate_entry(self, strategy):
        score = self.scorer.current_score
        allowed = self.gate.should_allow(score)
        self._stats.record_gate(0, score, allowed, threshold=self.gate.current_threshold)
        return allowed

    def should_abort(self, strategy):
        if not self.abort.enabled:
            return False
        level = strategy.vars.get('level', 0)
        action = self.abort.decide(
            level=level, duration_bars=strategy.index,
            danger_entry=0.5, danger_now=self.scorer.current_score,
        )
        return action == 'abort'

    def on_cycle_end(self, pnl, strategy):
        self.abort.end_episode(reward=pnl)

    def get_stats(self):
        stats = self._stats.to_dict()
        stats['scorer'] = self.scorer.stats
        stats['gate'] = {**stats.get('gate', {}), **self.gate.stats}
        stats['abort'] = {**stats.get('abort', {}), **self.abort.stats}
        return stats

    @classmethod
    def default_config(cls):
        return {
            'scorer': {'warmup': 50},
            'gate': {'percentile': 75, 'window': 500, 'enabled': True},
            'abort': {'enabled': True, 'alpha': 0.01, 'gamma': 0.95, 'epsilon': 0.0},
        }
```

---

## 13. Autopilot

Autopilot runs repeated backtests, auto-tuning hyperparameters while pipelines learn:

```
Iteration 1: Brain suggests HP -> backtest with pipeline -> pipeline learns
Iteration 2: Brain suggests better HP -> pipeline carries forward state -> learns more
Iteration N: Convergence
```

Pipeline state persists across iterations via `save_state` / `load_state`.

---

Previous: [STRATEGY.md](./STRATEGY.md) | Next: [ARCHITECTURE.md](./ARCHITECTURE.md)
