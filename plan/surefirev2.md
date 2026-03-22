# SurefireHedge: The Timing + Momentum Thesis

## The One-Line Problem Statement

> With infinite balance, martingale always wins. We have finite balance.
> Therefore the only question is: **can we win enough cycles before a losing streak ruins us?**

---

## 1. Why Most Cycles Fail

The current SurefireHedge strategy enters **every bar, blindly, in a fixed direction**. This means:

```
Bar 1: Open long → price drops 5 pips → hedge fires → Level 1
Bar 2: Short (Level 1, 2x size) → price chops → hedge fires → Level 2
Bar 3: Long (Level 2, 4x size) → still chopping → Level 3
...
Level 5: 32x initial size, account margin exhausted, cycle fails

The market didn't crash. It just chopped sideways for 20 minutes.
You entered at the worst possible moment.
```

**The strategy doesn't have a signal problem. It has a TIMING problem.**

If you had waited 30 minutes for the chop to resolve, the cycle would have completed at Level 0 or Level 1. The hedge mechanism works — it just can't survive being started during noise.

---

## 2. The Two Things That Matter

### 2.1 TIMING: When to Start a Cycle

A hedge cycle started at the wrong moment is the thing that kills you:
- **Before a major reversal** — your first leg loses immediately, you're climbing levels
- **During low liquidity** — price noise triggers hedges on meaningless moves
- **Into a news spike** — volatility overwhelms your TP/hedge distances
- **During a chop/range** — price oscillates through your hedge triggers repeatedly

A hedge cycle started at the right moment barely needs the hedge:
- **At the start of a trending move** — first leg hits TP, cycle done at Level 0
- **After a consolidation breakout** — momentum carries price to TP quickly
- **During high-liquidity sessions** — smooth directional moves, less noise

**The win rate of Level 0 (first leg hits TP) determines everything.** If Level 0 wins 70% of the time, you rarely reach Level 2+, and finite balance survives indefinitely.

### 2.2 MOMENTUM: Which Direction with Conviction

`direction = 'long'` is a static hyperparameter. But the market has direction at any given moment. If you enter long into bearish momentum:

```
Your first leg: LONG (smallest size, 1x)
Market momentum: BEARISH
Result: SL hit almost immediately → hedge fires

Your hedge leg: SHORT (larger size, 2x)
Market momentum: still BEARISH
Result: the hedge leg IS aligned with momentum → hits TP

But you've already committed to Level 1 (2x size) unnecessarily.
```

If you had just entered SHORT in the first place:
```
Your first leg: SHORT (smallest size, 1x)
Market momentum: BEARISH
Result: TP hit at Level 0 → cycle complete, minimal exposure
```

**The direction of the first leg must match current momentum.** This maximises the probability of a Level 0 win, which is the cheapest possible cycle.

---

## 3. The Math: Why Timing Changes Everything

### With blind entry (current strategy):
```
Assume: P(Level 0 TP hit) = 50% (coin flip, no edge)

P(reaching Level N) = 0.5^N
P(Level 5, ruin)    = 0.5^5 = 3.1%

Expected cycles before ruin = 1/0.031 = ~32 cycles
With 10 cycles/day = blown in 3 days
```

### With timing + momentum (upgraded strategy):
```
Assume: P(Level 0 TP hit) = 75% (momentum-aligned, good timing)

P(reaching Level N) = 0.25^N
P(Level 5, ruin)    = 0.25^5 = 0.098%

Expected cycles before ruin = 1/0.00098 = ~1024 cycles
With 5 cycles/day = ~200 trading days before a ruin event
(and each winning cycle profits, so balance grows, pushing ruin further away)
```

**Going from 50% to 75% Level 0 win rate changes survival from 3 days to 200+ days.** That's not a linear improvement — it's the difference between a gambling strategy and a viable one.

### The compounding effect:
```
Each winning cycle adds profit to balance.
Larger balance → can survive deeper levels.
Deeper survival → even lower ruin probability.
This is a positive feedback loop IF the base win rate is high enough.

Critical threshold: ~65-70% Level 0 win rate
Below this: balance erodes over time (negative expectancy despite wins)
Above this: balance grows, ruin probability shrinks, strategy is viable
```

---

## 4. What the Strategy Needs

### Current (broken):
```
Every bar → open cycle → pray for TP → hedge if wrong → pray harder
```

### Target (viable):
```
Wait for timing + momentum signal
       │
       ▼
Confirm: volatility suitable? session active? spread OK?
       │ NO → wait
       │ YES
       ▼
Start cycle in direction of momentum
       │
       ├── Level 0 TP hit (75%+ of the time) → profit, reset, wait for next signal
       │
       └── Level 0 SL hit (25%- of the time) → hedge fires
              │
              ├── Re-check momentum for hedge direction (don't blindly reverse)
              │
              └── Level 1 TP hit (most of the time) → smaller profit, reset
                     │
                     └── Rarely reaches Level 2+
                            │
                            └── Safety sizing prevents ruin even at deep levels
```

### The filters() Method

The strategy needs exactly 4 checks before entering a cycle:

```python
def filters(self):
    return [
        self._momentum_is_aligned,    # Is there directional conviction?
        self._volatility_is_suitable,  # Not too dead, not too wild?
        self._can_afford_cycle,        # Can balance survive worst case?
        self._cooldown_elapsed,        # Enough time since last failed cycle?
    ]
```

#### Filter 1: Momentum Alignment
**Question:** Is the market moving directionally right now?

```
Candidates (test in research notebook):
- EMA crossover (fast > slow = long, fast < slow = short)
- RSI above/below 50
- ADX > threshold (confirms trend exists, not directionless)
- Price above/below N-period moving average
- MACD histogram sign

What we need: direction (long/short) + strength (0-1)
Only enter if strength > threshold
```

#### Filter 2: Volatility Suitability
**Question:** Are TP/hedge distances achievable but not trivially small?

```
Use ATR to measure current volatility:
- ATR too low (<5 pips): market is dead, distances are noise → WAIT
- ATR too high (>100 pips): distances might work but swings are violent → WAIT
- ATR in sweet spot: distances match daily range → ENTER

This is also where ATR-scaled distances come in:
  tp_pips = ATR * tp_atr_multiple
  hedge_pips = tp_pips / risk_reward

If ATR = 40 pips and tp_atr_multiple = 0.8:
  tp_pips = 32 pips (achievable in one move)
  hedge_pips = 16 pips (only fires on genuine reversal, not noise)
```

#### Filter 3: Affordability
**Question:** If this cycle goes to max_levels, will I survive?

```
worst_case = initial_size * (multiplier^max_levels - 1) / (multiplier - 1) * hedge_pips * pip_value

if worst_case > balance * max_risk_pct:
    # Scale down initial_size
    # OR skip this cycle entirely
```

#### Filter 4: Cooldown
**Question:** Has enough time passed since the last failed cycle?

```
After a failed cycle (SL hit at max_levels or deep level):
- The market condition that caused the failure may still persist
- Entering immediately = likely to fail again
- Wait N bars (optimisable) before allowing a new cycle

This prevents:
- Revenge trading after a loss
- Re-entering the same choppy conditions
- Rapid-fire cycles that drain balance through fees
```

---

## 5. ATR-Scaled Distances: Why Fixed Pips Fail

This deserves its own section because it's crucial.

### The problem with fixed distances:

```
You set: TP = 10 pips, Hedge = 5 pips

Monday (ATR = 20 pips):
  TP = 10 pips = 50% of daily range → reasonable
  Hedge = 5 pips = 25% of daily range → fires on real moves
  Result: cycles complete normally

Friday news day (ATR = 80 pips):
  TP = 10 pips = 12.5% of daily range → hit easily BUT...
  Hedge = 5 pips = 6.25% of daily range → FIRES ON EVERY CANDLE
  Result: Level 5 in minutes, blown account

Overnight (ATR = 8 pips):
  TP = 10 pips = 125% of daily range → NEVER HIT
  Hedge = 5 pips = 62.5% of daily range → fires occasionally
  Result: cycles stuck open forever, capital locked
```

### The fix: ATR-relative distances

```
tp_pips = ATR * tp_atr_multiple     (e.g., ATR * 0.8)
hedge_pips = tp_pips / risk_reward  (e.g., tp_pips / 2.0)

Monday (ATR = 20 pips):
  TP = 16 pips, Hedge = 8 pips → scaled appropriately

Friday news (ATR = 80 pips):
  TP = 64 pips, Hedge = 32 pips → wider distances match volatility
  Hedge fires only on GENUINE reversals, not noise

Overnight (ATR = 8 pips):
  TP = 6.4 pips, Hedge = 3.2 pips → tight distances match low vol
  Cycles resolve quickly in smaller moves
```

**ATR scaling is regime-awareness without the complexity.** One indicator, one multiplication, and your distances automatically adapt to any market condition.

### Regime-aware distances close sooner

This is the key insight: properly calibrated distances mean:
1. TP is reachable within the current volatility range
2. Hedge fires only on real adverse moves (not noise)
3. When hedge fires, the larger leg catches a real move and hits TP
4. Cycles resolve at Level 0-1, rarely reaching deep levels
5. Finite balance survives

---

## 6. Momentum-Directed Hedging

### Current: blind reversal
```
Level 0: LONG  → SL hit → Level 1: SHORT (why? just because long lost)
Level 1: SHORT → SL hit → Level 2: LONG  (oscillating blindly)
```

### Proposed: momentum-checked hedging
```
Level 0: LONG (momentum was bullish) → SL hit
  → Re-check momentum:
     If now BEARISH → SHORT (hedge aligns with new momentum) → likely TP hit
     If still BULLISH → LONG again with wider distance (SL was noise trigger)
```

**Why this matters:**
- The hedge leg is the LARGEST position in the cycle (multiplier^level)
- This is your biggest bet
- If it's aligned with momentum, it has the highest probability of hitting TP
- One momentum-aligned hedge leg recovers all previous losses
- Cycle resolves at Level 1-2 instead of spiraling to Level 5

---

## 7. The Hyperparameters That Actually Matter

```python
def hyperparameters(self):
    return [
        # === TIMING (primary — these determine win rate) ===
        {'name': 'momentum_period',    'type': int,   'min': 5,    'max': 200,
         'doc': 'Lookback for momentum indicator. Shorter = more signals, noisier.'},

        {'name': 'momentum_threshold', 'type': float, 'min': 0.1,  'max': 5.0,
         'doc': 'Minimum momentum strength to enter. Higher = fewer but better entries.'},

        {'name': 'cooldown_bars',      'type': int,   'min': 5,    'max': 500,
         'doc': 'Wait this many bars after a failed cycle before re-entering.'},

        {'name': 'session_filter',     'type': str,   'options': ['london', 'ny', 'overlap', 'any'],
         'doc': 'Which trading sessions to allow entries in.'},

        # === DISTANCE CALIBRATION (critical — match distances to volatility) ===
        {'name': 'atr_period',         'type': int,   'min': 7,    'max': 50,
         'doc': 'ATR lookback period for distance calculation.'},

        {'name': 'tp_atr_multiple',    'type': float, 'min': 0.3,  'max': 1.5,
         'doc': 'TP = ATR * this. 0.8 = TP is 80% of daily range.'},

        {'name': 'risk_reward',        'type': float, 'min': 1.2,  'max': 3.5,
         'doc': 'Hedge distance = TP / this. Higher = tighter hedge trigger.'},

        # === VOLATILITY FILTER ===
        {'name': 'min_atr_pips',       'type': float, 'min': 1.0,  'max': 30.0,
         'doc': 'Skip if ATR below this (dead market).'},

        {'name': 'max_atr_pips',       'type': float, 'min': 30.0, 'max': 300.0,
         'doc': 'Skip if ATR above this (too wild).'},

        # === HEDGE MECHANICS (secondary — narrow ranges) ===
        {'name': 'multiplier',         'type': float, 'min': 1.5,  'max': 2.5,
         'doc': 'Size multiplier per hedge level. 2.0 = double each level.'},

        {'name': 'max_levels',         'type': int,   'min': 3,    'max': 6,
         'doc': 'Maximum hedge depth. Safety cap on exponential growth.'},
    ]

# Total: 11 parameters
# Optuna + Ray handles this comfortably — no exotic optimisers needed
```

### What's NOT a hyperparameter anymore:
- `direction` — determined by momentum at cycle start, not a fixed param
- `tp_upper` / `tp_lower` — replaced by `tp_atr_multiple` (one param, auto-scales)
- `initial_size` — computed by Safety Sizing based on balance, not optimised

---

## 8. Research Questions (Notebook Investigation)

Before building, we need data-driven answers to:

### Q1: Which momentum indicator best predicts "first leg wins"?
```
Test candidates:
  a) EMA(8) vs EMA(21) crossover
  b) RSI(14) above/below 50
  c) ADX(14) > 20 as confirmation
  d) MACD histogram sign
  e) Simple: price > SMA(20)

Metric: P(price moves tp_pips in momentum direction within N bars)
Test on: 2+ years EUR-USD 1m/5m candles
```

### Q2: What ATR multiple produces the best TP/hedge distance?
```
Sweep tp_atr_multiple from 0.3 to 1.5 in 0.1 steps
For each: measure cycle completion rate, average level reached, P(ruin)
Find the sweet spot where cycles resolve fast but TP is achievable
```

### Q3: How long should cooldown be after a failed cycle?
```
Measure: if a cycle fails at Level N, what's the P(next cycle also fails)
  as a function of bars waited between cycles?
Find: the minimum cooldown where P(consecutive failure) drops below baseline
```

### Q4: Which sessions have the best cycle completion rates?
```
Bucket all historical cycle simulations by session:
  London, New York, London-NY overlap, Tokyo, Sydney
Measure: Level 0 win rate, average max level, P(ruin) per session
```

### Q5: What's the actual ruin probability for calibrated params?
```
Take best params from Q1-Q4
Run 10,000 Monte Carlo simulations of 1000-cycle sequences
Measure: P(balance reaches 0), expected time-to-ruin, growth rate
```

---

## 9. Build Plan

| Step | What | Why | Depends On | Effort |
|------|------|-----|------------|--------|
| **1** | Safety Sizing module | Prevents ruin. Pure math. Must exist before anything else. | — | 1-2 days |
| **2** | Research notebook: momentum indicators | Data-driven answer to "which indicator?" | Historical candle data | 3-4 days |
| **3** | Research notebook: ATR distance sweep | Data-driven answer to "what multiple?" | Historical candle data | 2-3 days |
| **4** | Research notebook: cooldown + session analysis | Data-driven answer to "when to enter?" | Historical candle data | 2-3 days |
| **5** | Upgrade SurefireHedge with filters() | The actual fix. Implement findings from steps 2-4. | Steps 1-4 | 2-3 days |
| **6** | Optimise with existing Optuna + Ray | Find best combo of the 11 hyperparams. | Step 5 | 1-2 days |
| **7** | Walk-forward validation | Confirm params aren't overfit. | Step 6 | 2-3 days |
| **8** | Monte Carlo stress test | Confirm ruin probability is acceptable. | Step 7 | 1-2 days |
| **9** | Paper trade on OANDA demo | Real market validation. Minimum 2 weeks. | Step 8 | 2+ weeks |
| **10** | Decision: go live or add complexity? | If paper results are good → live. If not → investigate advanced modules (M5-M11 from framework.md). | Step 9 | — |

**Total to first paper trade: ~3 weeks**

---

## 10. Success Criteria

Before going live, the strategy must demonstrate:

| Metric | Target | Measured By |
|--------|--------|-------------|
| Level 0 win rate | > 65% | Backtest + walk-forward |
| Max drawdown (2yr backtest) | < 25% | Backtest |
| Sharpe ratio | > 1.0 | Backtest + walk-forward |
| Walk-forward pass rate | > 70% of windows profitable | Walk-forward validation |
| Monte Carlo P(ruin) over 1000 cycles | < 1% | Monte Carlo simulation |
| Paper trade vs backtest divergence | < 1σ on key metrics | 2-week paper trade |
| Average max hedge level per cycle | < 1.5 | Backtest + paper trade |

**If any metric fails, do not go live.** Return to research notebooks and iterate.

---

## 11. What We're NOT Building (Yet)

| Component | Status | Condition to Revisit |
|-----------|--------|---------------------|
| Multi-Island GA | Not needed | If Optuna can't find good params in 11-dim space (unlikely) |
| Quantum Optimizer | Not needed | If both Optuna and GA plateau (very unlikely for 11 params) |
| Probabilistic Regime Detection | Not needed | If ATR scaling can't handle regime changes (test first) |
| Fuzzy Logic Gate | Not needed | If hard thresholds in filters() are too rigid (test first) |
| Dynamic Regime Islands | Not needed | If static params can't handle market evolution (months of live data needed) |
| Online Parameter Tuning | Not needed | If params decay over time (months of live data needed) |

**All of these are documented in `docs/framework.md` as optional modules (M5-M11) that can be activated if the simple approach proves insufficient.** The modular design means adding them later requires zero changes to the core strategy.

---

## 12. Summary

The SurefireHedge strategy's exponential risk comes from **deep hedge levels**. Deep levels come from **bad cycle starts**. Bad cycle starts come from **no timing or momentum awareness**.

Fix the entry, and the hedge math works itself out:
1. **Momentum** sets direction → first leg wins most of the time
2. **ATR scaling** sets distances → cycles resolve within daily range
3. **Filters** block bad moments → cycles don't start during noise/news/chop
4. **Safety sizing** survives the rest → even rare deep levels don't kill you

Four things. Not twelve. Start simple, measure, add complexity only when proven necessary.
