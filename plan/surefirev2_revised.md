# SurefireHedge V2 — Revised Research Plan

## What We Proved (Phase 1 — Complete)

### The strategy has high win rate. That's not the problem.

The surefire hedge mechanism works as designed:
- TP > hedge distance (TP = ATR * 0.8, hedge = TP / 2)
- Each level doubles size and reverses direction
- When ANY level hits TP, the cycle is profitable (covers all previous losses + net gain)
- **Cycle win rate is ~86%** — most sessions close green

### What kills the account: tail risk.

The ~14% of cycles that bust (all 5 levels lose) create catastrophic losses:
- Level sizes: 1x, 2x, 4x, 8x, 16x
- A bust at Level 5 loses the sum of ALL legs — exponentially larger than any single win
- One bust erases 20-50+ winning cycles
- Finite balance means you can't always open the next leg (margin constraint)

### What we ruled out:

| Approach | Result | Why |
|----------|--------|-----|
| Momentum indicators for L0 direction | Zero edge | All indicators (EMA, RSI, MACD, ADX, SMA) perform at random-walk baseline |
| Indicator combinations | Worse | Fewer signals, same win rate |
| L0 win rate optimization | Wrong metric | L0 losing is expected and handled by the hedge. The problem is ALL levels losing |
| Cooldown after losses | No effect | P(loss\|previous loss) unchanged regardless of wait time |

### What partially holds:

| Finding | Status |
|---------|--------|
| Session matters (Off Hours is worst) | Tested on L0 only — needs retest on bust rate |
| ATR/volatility filtering | Tested on L0 only — needs retest on bust rate |

---

## The Real Problem Statement

> With 86% cycle win rate, the strategy is profitable UNLESS a bust occurs at the wrong time
> (when balance can't absorb it) or busts cluster (two in a row = account death).
>
> **The only question: can we reduce P(bust) or P(bust impact) enough to survive indefinitely?**

---

## Phase 2: Tail-Risk Research (Current)

### Study 1: Full Cycle Simulation on Real Prices

**Status**: Running (scripts 05, 06)

Simulate complete hedge cycles on 2+ years of EUR-USD 5m data:
- Enter at EMA crossover events (non-overlapping cycles)
- Walk through all levels on real price action (not coin flips)
- Record: level reached, duration, P&L, market conditions at entry

**Metrics**:
- P(bust) on real data vs theoretical 13.5%
- Distribution of max level reached per cycle
- Average P&L per level (L0 win, L1 win, ..., bust)
- "One bust erases N wins" — the exact ratio

### Study 2: Bust Condition Profiling

**Status**: Running (script 05)

For every cycle that reached Level 3+, capture the market state at cycle entry:
- ATR value and ATR percentile (vs trailing 1000 bars)
- Trading session (Tokyo/London/Overlap/NY/Off)
- Recent price action: range width of last 50 bars vs ATR
- Spread conditions
- Time since last bust

**Goal**: Find if busts cluster in identifiable conditions (chop, low liquidity, extreme vol).

### Study 3: Entry Filters vs Bust Rate

**Status**: Running (script 05)

Test filters against the metric that matters — P(cycle reaches Level 4+):

| Filter | What it tests |
|--------|--------------|
| Session filter | Only enter during London/Overlap/NY. Does bust rate drop? |
| ATR sweet spot | Only enter when ATR percentile is 20-80. Avoids dead and wild markets |
| Range filter | Only enter when recent range suggests trending (not chopping) |
| Combined | Best session + best volatility filter together |

**Success criteria**: A filter that reduces P(bust) by 50%+ while keeping enough cycles for profitability.

---

## Phase 3: Tail-Risk Mitigation (Next)

Based on Phase 2 findings, implement and test:

### 3A: Smart Entry Timing

If Phase 2 shows bust conditions are identifiable:
- Build a `should_enter_cycle()` gate that checks conditions before starting
- Not about direction — about "is NOW a safe time to run a cycle?"
- Test: does filtered entry reduce P(bust) from ~14% to <5%?

### 3B: Early Cycle Abort

Sometimes cutting a cycle short at L2-L3 with a controlled loss beats doubling into L4-L5:
- At Level N, check: has momentum completely reversed? Is ATR spiking (news event)?
- If abort signals fire: close all positions, take the known loss
- Compare: abort loss at L3 (~15x base) vs bust loss at L5 (~63x base)
- **This turns catastrophic tail events into manageable losses**

### 3C: Dynamic Sizing

Instead of fixed 2x multiplier:
- Reduce multiplier at deeper levels (2x, 1.8x, 1.5x, 1.3x) — slower growth, more headroom
- Or: cap total exposure as % of balance — if next level would exceed X%, abort
- Margin-aware: calculate if the account can physically open the next leg BEFORE entering the cycle

### 3D: Cycle Spacing

Even if cooldown doesn't help L0, it may help tail risk:
- After a bust, the market condition that caused it likely persists
- Mandatory longer cooldown after deep cycles (not after L0 losses)
- After L3+ cycle: wait 100+ bars. After bust: wait 500+ bars.

---

## Phase 4: Validation

### Monte Carlo (Corrected)

Re-run Monte Carlo using:
- Real cycle outcome distribution from Phase 2 (not independent coin flips)
- Include serial correlation (if busts cluster in real data)
- Test with Phase 3 mitigations applied
- Measure: P(ruin over 1000 cycles), expected time-to-ruin, growth rate

### Walk-Forward

- Split data: 2024 for training filters, 2025-2026 for validation
- Confirm filters/abort rules work out-of-sample
- Check for overfitting (filter works in-sample but not out-of-sample)

### Paper Trade

- Run on OANDA demo for 2+ weeks with best configuration
- Compare: actual bust rate vs backtested bust rate
- Verify margin calculations match live environment

---

## Decision Framework

After Phase 2-4:

```
IF P(bust) can be reduced to <5% with simple filters:
    → Ship V2 with timing filters + safety sizing
    → Monitor live, add complexity only if needed

ELIF P(bust) drops to 5-10% with filters + early abort:
    → Ship V2 with filters + abort rules
    → Begin ML pipeline in parallel for further improvement

ELIF P(bust) stays >10% despite all mitigations:
    → Simple approach is dead
    → Full ML pipeline required:
        - Regime detection (predict chop vs trend)
        - Entry timing classifier
        - Dynamic distance/multiplier optimization
    → OR pivot to a different strategy architecture entirely
```

---

## File Reference

| File | What |
|------|------|
| `notebooks/surefire_v2/01_momentum_indicators.ipynb` | Phase 1: Indicators provide zero edge (proven) |
| `notebooks/surefire_v2/02_atr_distance_sweep.py` | Phase 1: Distance ratio determines win rate (proven) |
| `notebooks/surefire_v2/03_cooldown_session.py` | Phase 1: Cooldown has no effect (proven) |
| `notebooks/surefire_v2/04_monte_carlo.py` | Phase 1: Ruin probability vs win rate (proven) |
| `notebooks/surefire_v2/05_full_cycle_simulation.py` | Phase 2: Bust rate under filters (running) |
| `notebooks/surefire_v2/06_cycle_pnl_analysis.py` | Phase 2: P&L distribution, equity curve (running) |
| `notebooks/surefire_v2/RESEARCH_CONCLUSIONS.md` | Phase 1 conclusions |

---

## Key Insight

> **Win rate is not the problem. The strategy wins 86% of cycles.**
>
> **The problem is that the 14% losses are 20-50x larger than the wins.**
>
> **The solution is not "win more often" — it's "never let a cycle reach the last leg."**
>
> Timing is everything. Not timing of direction. Timing of WHEN TO PLAY.
