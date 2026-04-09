# ARIA Pipeline Design — Adaptive Regime-Intelligent Architecture

**Date:** 2026-04-09
**Status:** Approved
**Build approach:** Online-only learning (no pre-training), phased delivery

---

## Overview

ARIA is a new pipeline (`pipelines/_shared/ARIA/`) implementing the `Pipeline` ABC. It is a fresh build — no IslandPilot code reused. Strategy-agnostic: reads any strategy's `hyperparameters()` schema and governs it.

**Core principle:** Strategy = fixed execution logic. ARIA = intelligence layer sitting above it. ARIA controls which hyperparameters to set before each cycle, when to allow/block a cycle, and when to intervene mid-cycle.

---

## Architecture

```
┌───────────────────────────────────────────────────────┐
│                    ARIAPipeline                        │
│              (implements Pipeline ABC)                 │
│                                                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │ Market  │→ │  Cycle  │→ │   HP    │→ │  Risk   │ │
│  │ Brain   │  │  Gate   │  │ Engine  │  │ Shield  │ │
│  │ (L1)    │  │ (L2)    │  │ (L3)    │  │ (L4)    │ │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘ │
│       │                          │                    │
│       ↓                          ↓                    │
│  ┌─────────┐              strategy.hp                 │
│  │Observer │              (injected)                  │
│  │ (L5)    │                                          │
│  └─────────┘                                          │
│       │                                               │
│       ↓                                               │
│  ┌──────────┐                                         │
│  │  Meta-   │                                         │
│  │Evaluator │                                         │
│  │ (L6)     │                                         │
│  └──────────┘                                         │
└───────────────────────────────────────────────────────┘
```

### Hook Mapping to Pipeline ABC

| Pipeline Hook | ARIA Layers Active |
|---|---|
| `on_before(strategy)` | L1 updates MarketState |
| `gate_entry(strategy)` | L2 classifies allow/block |
| `filter_order(strategy, intent)` | L3 injects HP-derived TP/hedge values |
| `suggest_exit(strategy)` | L4 checks conformal kill + liquidity + margin |
| `on_open_position(strategy)` | L5 captures entry snapshot |
| `on_cycle_end(pnl, strategy)` | L5 records enriched outcome → L2/L3/L6 update |

---

## Layer 1 — MarketBrain

**Purpose:** What is the market doing right now?

**Method:** Feature vector + Welford online normalization + incremental k-means clustering

**Features (10-12):**
- Volatility: NATR(14), NATR(50), ATR ratio (short/long)
- Trend: ADX(14), EMA slope (8, 21)
- Structure: Hurst exponent (R/S, 100-bar), Choppiness Index (5m, 15m)
- Context: spread (normalised), session flag (Asian/London/NY/Overlap)

All computed from strategy's candle data via 300-bar tail window. O(1) per candle.

**Output — MarketState:**
```python
MarketState = {
    'danger': float,          # [0, 1] composite danger score
    'trend_strength': float,  # ADX normalised [0, 1]
    'volatility': float,      # NATR normalised [0, 1]
    'efficiency': float,      # Hurst-based [0, 1]
    'regime_id': int,         # online cluster assignment
    'regime_confidence': float,  # distance-based [0, 1]
    'features': dict,         # raw feature values for Observer
}
```

**Online clustering:** Incremental k-means with k=5 (starts with 1 cluster, splits when variance exceeds threshold, caps at k_max). No pre-training — discovers regimes as data arrives. First 50 candles are warmup (returns regime_id=0, confidence=0.5).

---

## Layer 2 — CycleGate

**Purpose:** Should a new cycle start at all?

**Method:** Online logistic regression with SGD

**Features (input vector):**
- MarketState: danger, trend_strength, volatility, efficiency, regime_id (one-hot)
- Account state: equity drawdown %, consecutive busts, cycles since last bust
- Time: session (one-hot), day of week (one-hot)

**Learning:**
- Binary target: 1 = cycle ended in TP (profitable), 0 = cycle ended in bust/abort
- SGD update after each `on_cycle_end` with learning rate 0.01, L2 regularisation
- Prediction: P(profitable | features) — block if P < threshold
- Threshold starts at 0.0 (allow everything), increases as model accumulates evidence
- Minimum 30 cycles before gate starts blocking (warmup period)

**Output:** `bool` — True = allow entry, False = block

---

## Layer 3 — HPEngine

**Purpose:** What parameters should this cycle run with?

**Method:** Contextual bandit (Thompson Sampling) per HP group

**HP Schema Reading:**
- At init, reads strategy's `hyperparameters()` list
- Groups by `group` field: General, Entry Signal, Grid/Hedge, Take Profit, Filters, Risk, Position Management
- For each group, identifies tuneable parameters (respecting `depends_on` constraints)

**Arm Construction:**
- Categorical HPs: each option is an arm dimension
- Continuous HPs: discretised into 5 bins (uniform between min/max)
- Integer HPs: discretised into min(5, max-min+1) bins
- Per-group arms = cartesian product of parameter bins (capped at 50 arms per group via random sampling if combinatorial explosion)

**Context:** MarketState regime_id (bandits maintain separate posteriors per regime)

**Thompson Sampling:**
- Each arm maintains Beta(alpha, beta) posterior per regime
- On cycle start: sample from posteriors, pick arm with highest sample
- On cycle end: update winning arm's posterior — success if PnL > 0, failure otherwise
- Exploration: natural via Thompson Sampling (no epsilon needed)

**HP Injection:**
- Between cycles only (not mid-cycle)
- Injects via `filter_order()`: modifies TP distance, hedge distance on order intents
- General HPs (sizing_curve, sizing_factor, max_levels) set on strategy.hp directly in `on_before()` when no cycle is active

**Warmup:** First 20 cycles use strategy defaults (no HP injection). After 20 cycles, bandits start exploring.

---

## Layer 4 — RiskShield

**Purpose:** Is this cycle about to destroy the account?

### 4a — Conformal Kill Switch

**Method:** Split conformal prediction on loss sequences

- Calibration set: last N cycle losses (N grows as cycles accumulate, min 20)
- Before each hedge level, predict loss if we continue:
  ```
  predicted_loss = median(calibration_losses_at_this_level)
  bound = quantile(calibration_residuals, 1 - alpha)  # alpha = 0.1
  ```
- Kill if `predicted_loss + bound > available_margin * safety_factor`
- Before 20 calibration cycles: fall back to simple level threshold (abort at level 6)
- Updates calibration set after each cycle end

### 4b — Liquidity Gate

Checked before each hedge level (via `suggest_exit`):

1. **Margin check:** Can we afford next position? `next_margin = calc_size(level+1) * price / leverage`. Block if `next_margin > equity * 0.8`
2. **Spread check:** `spread_cost = spread * next_size`. Block if `spread_cost > expected_tp_profit * 0.2`
3. **Ruin probability:** `P(ruin) = f(remaining_capacity, expected_adverse_moves)`. Block if `P(ruin) > 0.15`

### 4c — Margin Survival Model

```python
def ruin_probability(level, equity, base_size, multiplier, atr):
    total_exposure = sum(base_size * multiplier**i for i in range(level + 1))
    max_adverse = total_exposure * atr * 3  # 3-sigma move
    return min(1.0, max_adverse / equity)
```

**Output:** `suggest_exit()` returns `{'action': 'close_all'}` when any kill condition triggers, else `None`.

---

## Layer 5 — Observer

**Purpose:** What just happened and why?

**Method:** Pure data collection — no ML

Enriches every session record (from strategy's `_end_cycle`) with ARIA context:

```python
aria_record = {
    # From strategy session_record
    'number', 'direction', 'levels', 'legs', 'pnl', 'reason', 'bars',
    
    # ARIA enrichment
    'market_state_at_entry': MarketState snapshot,
    'market_state_at_exit': MarketState snapshot,
    'hp_used': dict,              # HP values active during this cycle
    'regime_id_at_entry': int,
    'danger_at_entry': float,
    'danger_at_exit': float,
    'gate_confidence': float,     # P(profitable) from CycleGate
    'conformal_bound_at_kill': float or None,
    'ruin_prob_at_each_level': list[float],
    'aria_score_at_entry': float,  # MetaEvaluator score
}
```

Stored in `self._enriched_sessions` list. Becomes training data for L2, L3, L6.

---

## Layer 6 — MetaEvaluator

**Purpose:** Is the whole system improving?

**Method:** Rolling window score formula (no ML)

```python
def aria_score(enriched_sessions, window=100):
    recent = enriched_sessions[-window:]
    
    # 1. Survival efficiency: shallow wins / total cycles
    shallow_wins = [s for s in recent if s['reason'] == 'tp_hit' and s['levels'] <= 2]
    survival_efficiency = len(shallow_wins) / max(len(recent), 1)
    
    # 2. Bust penalty: busts in confident regimes (bad) / total
    bad_busts = [s for s in recent 
                 if s['reason'] in ('abort', 'max_level_bust', 'margin_call', 'sl_hit')
                 and s.get('gate_confidence', 0) > 0.5]
    bust_penalty = len(bad_busts) / max(len(recent), 1)
    
    # 3. Capital preservation: CVaR 95
    pnls = [s['pnl'] for s in recent]
    cvar_95 = np.percentile(pnls, 5) if len(pnls) >= 10 else 0
    initial_capital = recent[0].get('equity_at_entry', 10000)
    
    score = (
        survival_efficiency * 0.4
        - bust_penalty * 0.3
        + (cvar_95 / initial_capital) * 0.3
    )
    return score
```

**Reward loop:**
- After each cycle end, compute ARIA score
- If score drops below rolling average by > 1 std: boost L3 exploration (reset bandit alpha/beta closer to priors)
- Score is the reward signal for L2 gate updates (not just raw PnL)

---

## Build Phases

### Phase 1 — Core Loop (L5 + L1 + L4)
- `ARIAPipeline` shell implementing Pipeline ABC
- `MarketBrain`: feature extraction + online clustering
- `RiskShield`: conformal kill + liquidity gate + margin survival
- `Observer`: enriched session recording
- Gate always allows, HPs stay at strategy defaults
- **Testable immediately** with backtester

### Phase 2 — Intelligence (L2 + L3)
- `CycleGate`: online logistic regression
- `HPEngine`: contextual bandits per HP group
- Starts learning from cycle 1 of backtest (but warmup periods before acting)

### Phase 3 — Meta (L6)
- `MetaEvaluator`: ARIA score formula
- Reward loop wired to L2/L3
- Exploration boost on degradation

---

## File Structure

```
pipelines/_shared/ARIA/
├── __init__.py          # ARIAPipeline class (Pipeline ABC)
├── config.py            # default_config, HP schema reading utilities
├── market_brain.py      # L1: features + online clustering
├── cycle_gate.py        # L2: online logistic regression
├── hp_engine.py         # L3: contextual bandits
├── risk_shield.py       # L4: conformal + liquidity + margin
├── observer.py          # L5: enriched session recording
├── meta_evaluator.py    # L6: ARIA score + reward
└── models/              # serialized state (bandit posteriors, gate weights, etc.)
```

---

## Design Decisions

1. **Online-only learning** — No pre-training phase. All models learn from cycle outcomes during backtest/live runs. Upgrade to offline pre-training (Option A) if online convergence is too slow.

2. **Contextual bandits over neural networks** — Thompson Sampling works from cycle 1, explores naturally, and has theoretical convergence guarantees. Neural nets need thousands of examples.

3. **No mid-cycle HP adjustment** — Pipeline hooks don't support safe mid-cycle HP mutation. TP/hedge values can be injected per-order via `filter_order()`, but structural HPs (sizing, max_levels) are fixed at cycle start.

4. **Conformal prediction for kill switch** — Distribution-free uncertainty bounds. Works with as few as 20 calibration points. Phase 2 research confirmed busts are IID, so exchangeability assumption holds.

5. **No IslandPilot reuse** — IslandPilot's GMM regime tree and GA evolution didn't perform in testing. ARIA uses simpler online methods that can be upgraded later.

6. **HP groups, not individual params** — Bandits over per-group configurations avoid the curse of dimensionality (65 individual params → 7 group-level decisions).

---

## What's NOT In This Design

- Transformer / attention networks (need offline training)
- Mid-cycle HP mutation (requires Strategy base class changes)
- Multi-timeframe features beyond strategy's candle data
- IslandPilot code reuse
- Frontend UI (will follow existing PipelineIntelligence.vue patterns once pipeline works)
