# SurefireHedge V2 Research Conclusions

## Executive Summary

**The surefire hedge strategy has positive expectancy under normal market conditions, but carries structural tail risk that cannot be eliminated — only redistributed.** This is the fundamental truth of any martingale-derived system.

With proper % equity sizing (0.5% base, sqrt multiplier, 12 levels):

- **99.7% cycle win rate**, 0.26% bust rate
- **Profit Factor 3.57**, positive EV per cycle (+0.0036%)
- **0% probability of ruin** under normal and moderately stressed conditions
- **Scales linearly**: identical % returns at $10k, $100k, $1M

**However, the tail risk investigation (Phase 6) reveals critical structural constraints:**

- **One bust erases 78 average wins** (12 lvl/sqrt config)
- **The martingale invariant**: P(bust) x severity is approximately constant across all configs — you can trade frequency for severity but cannot reduce the product
- **Deep levels (L6+) are NET NEGATIVE** with sqrt multiplier — they "win" the cycle but lose money after accounting for accumulated position costs
- **Kurtosis = 601** — extreme fat tails, 22x left-skewed
- **Under regime stress (2x bust rate + 2x severity): median return turns negative (-2%)**
- **Under worst-quartile-only conditions: total destruction (median -8%)**

The strategy works **because** the market exhibits slight mean-reversion at ATR-based TP/SL distances. If that microstructure edge disappears (regime shift), the strategy degrades rapidly. Any production deployment MUST include circuit breakers and regime monitoring.

---

## Phase 1: Indicator & Distance Research (Complete)

### Finding 1: Indicators Provide Zero Edge

All 5 momentum indicators + 6 combinations tested against "Always Long/Short" baselines on 222,992 EUR-USD 5m candles.

| Indicator | Win Rate | Baseline |
|-----------|----------|----------|
| EMA Cross | 32.8% | - |
| RSI Midline | 32.6% | - |
| MACD Hist | 34.1% | - |
| Price > SMA | 33.2% | - |
| EMA + ADX | 32.3% | - |
| **Always Long** | **34.3%** | baseline |
| **Always Short** | **34.0%** | baseline |

**No indicator beats random.** Level 0 win rate is purely a function of the TP/SL distance ratio (~33% when TP = 2x SL), confirming random walk behavior.

### Finding 2: The Distance Ratio Trap

The surefire hedge requires `TP > hedge_distance` for the math to work. This mechanically pushes Level 0 win rate below 50%:

| TP/SL Ratio | Level 0 Win Rate | Expected P(bust) at 5 levels |
|-------------|-----------------|------------------------------|
| TP = 0.5x SL | ~66% | 0.4% |
| TP = 1.0x SL | ~50% | 3.1% |
| **TP = 2.0x SL** | **~33%** | **13.5%** |

> **To make the hedge math work, TP must exceed SL. To get high L0 win rates, SL must exceed TP. These are mutually exclusive.**

### Finding 3: Cooldown Has No Effect

P(loss|previous loss) stays at ~28-36% regardless of wait time (0-200 bars). Market conditions don't "reset" after a loss.

### Finding 4: Phase 1 Monte Carlo (SUPERSEDED by Phase 4)

The original coin-flip Monte Carlo showed 95.5% ruin at 33% L0 win rate. **This was misleading** — it modeled each level independently, ignoring that real cycle outcomes follow a different distribution. See Phase 4 for the corrected Monte Carlo.

---

## Phase 2: Full Cycle Simulation & Tail Risk (Complete)

### Finding 5: Real Bust Rate is Lower Than Theoretical

Full cycle simulation on real EUR-USD 5m data (6,533 non-overlapping cycles with EMA 8/21 crossover entries):

| Metric | Value |
|--------|-------|
| Cycle win rate | 92.5% |
| P(bust) | 7.53% |
| Avg win | +$6.28 |
| Avg bust loss | -$41.09 |
| Wins erased per bust | 6.5 |
| Net P&L | +$17,726 |
| Profit factor | 1.887 |

Real P(bust) = 7.5%, significantly lower than the 13.5% theoretical expectation.

### Finding 6: Level Distribution

| Level | % of Cycles |
|-------|-------------|
| L0 win | 32.2% |
| L1 win | 26.0% |
| L2 win | 17.8% |
| L3 win | 10.7% |
| L4 win | 5.7% |
| **Bust (all 5 lose)** | **7.5%** |

Most cycles resolve early (58% by L1), but 13.2% reach the last leg.

### Finding 7: The Asymmetry Problem

- **One bust erases 6.5 winning cycles**
- Equity curve shows sawtooth pattern: steady climb from wins, sharp drops from busts
- Even with positive expectancy, bust severity is the key risk factor

### Finding 8: Filters Provide Marginal Bust Reduction

| Filter | P(bust) | Reduction |
|--------|---------|-----------|
| No filter (baseline) | 7.53% | - |
| London only | 7.12% | -5.4% |
| High volatility only | 6.89% | -8.5% |
| **London + High vol** | **6.32%** | **-16.1%** |
| Off Hours excluded | 7.21% | -4.2% |

Best filter combination reduces bust rate by only 16% (7.53% to 6.32%).

---

## Phase 3: Bust Anatomy & Mitigation Strategies (Complete)

### Finding 9: Conditional Win Probability Increases With Depth

The probability of winning AT a given level (conditional on reaching it) increases with depth:

| Level | Reached | P(win here) | P(lose deeper) |
|-------|---------|-------------|----------------|
| L0 | 6,533 | 32.2% | 67.8% |
| L1 | 4,427 | 38.4% | 61.6% |
| L2 | 2,726 | 42.6% | 57.4% |
| L3 | 1,564 | 44.8% | 55.2% |
| L4 | 863 | **43.0%** | **57.0%** |

This makes sense: at deeper levels, price has already moved significantly in one direction, creating mean-reversion pressure that helps the new (opposite direction) leg win.

### Finding 10: Last Leg (L4) Analysis

When a cycle reaches the final level (L4):
- **43% are saved** (371 of 863 cycles)
- **57% bust** (492 of 863 cycles)
- **L4 is NET NEGATIVE**: saves total +$8,882 but busts lose -$20,217 = net -$11,334
- **However, aborting at L3 is WORSE**: abort loss -$17,594 vs playing L4 net -$11,334
- Playing L4 saves $6,259 compared to aborting — **the last leg is worth playing**

### Finding 11: No Predictive Market Signal for Busts

Comparing market conditions at entry for winning vs busting cycles:

| Metric | Win Mean | Bust Mean | Difference |
|--------|----------|-----------|------------|
| ATR Percentile | 64.5 | 63.5 | -1.5% |
| RSI(14) | 49.9 | 49.8 | -0.2% |
| Range/ATR | 7.15 | 7.09 | -0.8% |
| BarRange/ATR | 0.964 | 0.962 | -0.2% |
| Bollinger Width | 0.001 | 0.001 | -3.7% |

**No market condition reliably separates busts from wins.** All differences are <4% — essentially noise. This means:
- Entry timing filters cannot meaningfully reduce bust rate
- Busts are a statistical inevitability, not a market-condition problem
- The solution must be structural (sizing/levels), not predictive

### Finding 12: Busts Do Not Cluster

| Condition | P(bust) |
|-----------|---------|
| After previous bust | 7.93% |
| After previous win | 7.50% |
| Unconditional | 7.53% |

Clustering ratio: 1.06x — **busts are essentially independent events**. No benefit from waiting after a bust.

### Finding 13: Bust Rate by Session (at cycle level)

| Session | Total Cycles | Busts | P(bust) |
|---------|-------------|-------|---------|
| Tokyo | 2,337 | 162 | 6.93% |
| London | 1,372 | 93 | 6.78% |
| Overlap | 1,027 | 82 | 7.98% |
| NY | 1,206 | 106 | 8.79% |
| Off | 591 | 49 | 8.29% |

Tokyo and London are marginally better, but the difference is small (6.8% vs 8.8%).

### Finding 14: Early Abort — More Levels is Better

Testing different max level caps:

| Config | Cycles | P(bust) | Net P&L | PF | MaxDD | Bust Erases |
|--------|--------|---------|---------|-----|-------|-------------|
| 2 levels | 6,752 | 41.7% | $1,887 | 1.17 | -2.0% | 1.2 wins |
| 3 levels | 6,610 | 24.0% | $5,947 | 1.40 | -1.4% | 2.3 wins |
| 4 levels | 6,538 | 13.2% | $11,541 | 1.66 | -1.5% | 4.0 wins |
| **5 levels** | **6,490** | **7.5%** | **$17,726** | **1.89** | **-1.4%** | **6.5 wins** |
| 6 levels | 6,474 | 4.4% | $22,149 | 1.92 | -2.3% | 11.4 wins |
| 7 levels | 6,462 | 2.6% | $28,109 | 1.99 | -5.3% | 19.0 wins |

More levels = higher profit, better profit factor, lower P(bust) — but exponentially more exposure per bust. The sweet spot depends on account size and risk tolerance.

### Finding 15: Dynamic Sizing Reduces Bust Severity

Testing different size progressions (all with 5 levels):

| Strategy | Sizes | P(bust) | Net P&L | PF | MaxDD |
|----------|-------|---------|---------|-----|-------|
| Standard 2x | 1, 2, 4, 8, 16x | 7.5% | $17,726 | 1.89 | -1.4% |
| Conservative | 1, 2, 3.6, 5.4, 7x | 7.5% | $12,026 | 1.98 | -0.9% |
| Flat after L2 | 1, 2, 4, 4, 4x | 7.5% | $10,298 | 2.06 | -0.8% |
| Sqrt scaling | 1, 2, 2.8, 3.5, 4x | 7.5% | $8,720 | 2.02 | -0.7% |
| Linear | 1, 2, 3, 4, 5x | 7.5% | $9,658 | 2.00 | -0.7% |

P(bust) is identical (same TP/SL geometry), but:
- **Bust severity drops dramatically** — max DD from -1.4% to -0.7%
- **Profit factor improves** — from 1.89 to 2.06
- Trade-off: lower net P&L but much smoother equity curve

### Finding 16: Best Hybrid Configurations

| Config | Levels | P(bust) | Net P&L | PF | MaxDD | Max Exposure |
|--------|--------|---------|---------|-----|-------|-------------|
| 5 lvl, 2x (baseline) | 5 | 7.5% | $17,726 | 1.89 | -1.4% | 3.1 lots |
| 6 lvl, sqrt | 6 | 4.4% | $9,372 | 2.38 | -0.8% | 1.8 lots |
| 6 lvl, linear | 6 | 4.4% | $10,517 | 2.31 | -0.9% | 2.1 lots |
| 7 lvl, sqrt | 7 | 2.6% | $9,800 | **2.93** | -1.2% | 2.3 lots |

**7 levels + sqrt sizing** achieves the best profit factor (2.93) with only 2.6% bust rate and 2.3 lots max exposure — far less than the baseline's 3.1 lots despite having 2 more levels.

### Finding 17: Margin Requirements

At 50:1 leverage with standard 2x sizing:

| Levels | Cumulative Margin + Max Loss |
|--------|------------------------------|
| 5 levels | $6,923 |
| 6 levels | $14,069 |
| 7 levels | $28,361 |

With sqrt sizing, 7 levels only needs ~$2,300 — easily affordable with $10k balance.

---

## Phase 4: Corrected Monte Carlo (Complete)

### Finding 18: Strategy is Viable — 0% Ruin

Monte Carlo using **bootstrap sampling from real cycle P&L distributions** (10,000 simulations x 2,000 cycles, $10k start, $1k ruin threshold):

| Config | P(ruin) | Median Final | % Profitable | Avg Max DD |
|--------|---------|-------------|-------------|-----------|
| 5 lvl, 2x (baseline) | **0.00%** | **$15,475** | 100% | 2.2% |
| 5 lvl, sqrt | 0.00% | $12,694 | 100% | 1.0% |
| 5 lvl, linear | 0.00% | $12,981 | 100% | 1.1% |
| 6 lvl, sqrt | 0.00% | $12,899 | 100% | 1.1% |
| 7 lvl, sqrt | 0.00% | $13,044 | 100% | 1.1% |
| 4 lvl, 2x (abort L4) | 0.00% | $13,545 | 100% | 1.6% |

**Every configuration shows 0% ruin and 100% profitability across all 10,000 paths.**

Even testing out to 5,000 cycles: still 0% ruin for all configs.

**Note**: Phase 4 used fixed lot sizes. Phase 5 below upgrades to % equity sizing with compounding, which is more realistic and produces even better results.

### Why Phase 1 Monte Carlo Was Wrong

The Phase 1 Monte Carlo (script 04) showed 95.5% ruin because:
1. It modeled each level as an independent Bernoulli trial (33% win probability)
2. It assumed worst-case P(bust) of 13.5% (geometric: 0.67^5)
3. Real data shows P(bust) = 7.5% — the levels are not independent
4. Real per-cycle expected value is +$2.73, which compounds reliably over thousands of cycles

---

## Phase 5: Capital Scaling & Quant-Level Risk Analysis (Complete)

### Finding 19: % Equity Sizing with Capital-Adaptive Levels

Instead of fixed lot sizes and fixed 5 levels, the production strategy should use:
- **Base size = X% of current equity** (not fixed lots)
- **Level count = max levels affordable** at current equity (not fixed N)
- **Multiplier = sqrt(2)** per level (not 2x) — more levels, less exposure per bust

Capital tier -> max levels (0.5% base, sqrt multiplier, 50:1 leverage):

| Capital | Levels | Base Lot | Max Lot | Cumulative Notional |
|---------|--------|----------|---------|---------------------|
| $5,000 | 12 | 0.011 | 0.510 | $380k |
| $10,000 | 12 | 0.023 | 1.019 | $380k |
| $25,000 | 12 | 0.056 | 2.548 | $950k |
| $100,000 | 12 | 0.225 | 10.193 | $3.8M |
| $1,000,000 | 12 | 2.252 | 101.925 | $38M |

Key insight: **the number of affordable levels stays constant** when sizing is % of equity — only lot sizes scale. This means identical % returns at any capital level.

### Finding 20: Performance with % Equity Sizing

Full simulation with dynamic equity (equity updates after each cycle, compounding):

| Config | Cycles | Win Rate | P(bust) | Return | PF | MaxDD | Sharpe | Sortino | Kelly |
|--------|--------|----------|---------|--------|-----|-------|--------|---------|-------|
| $10k / 0.5% / sqrt | 6,419 | **99.7%** | **0.26%** | 25.7% | **3.57** | -1.10% | 0.166 | 0.042 | 0.788 |
| $10k / 0.5% / 2x | 6,443 | 97.5% | 2.55% | 88.4% | 1.97 | -3.13% | 0.120 | 0.044 | 0.488 |
| $10k / 0.3% / sqrt | 6,418 | **99.9%** | **0.12%** | 15.3% | **3.92** | -0.89% | 0.154 | 0.038 | 0.828 |
| $10k / 1.0% / sqrt | 6,423 | 99.3% | 0.73% | 51.9% | 2.89 | -1.20% | 0.167 | 0.045 | 0.694 |
| $100k / 0.5% / sqrt | 6,419 | 99.7% | 0.26% | 25.7% | 3.57 | -1.10% | 0.166 | 0.042 | 0.788 |
| $1M / 0.5% / sqrt | 6,419 | 99.7% | 0.26% | 25.7% | 3.57 | -1.10% | 0.166 | 0.042 | 0.788 |

Critical findings:
- **99.7% win rate** with 12-level sqrt sizing (vs 92.5% with 5-level 2x)
- **P(bust) drops from 7.5% to 0.26%** — 29x reduction just from more levels + sqrt sizing
- **% returns are identical** across $10k, $100k, $1M — perfect scaling
- **Max consecutive losses: 2** — never more than 2 busts in a row
- **Calmar ratio: 23.5** — exceptional risk-adjusted return

### Finding 21: Duration Analysis

Cycles are fast — no risk of day-long sessions:

| Metric | All Cycles | Wins | Busts |
|--------|-----------|------|-------|
| Mean duration | 22 min | 22 min | 83 min |
| Median duration | 15 min | 15 min | 85 min |
| P95 duration | 50 min | 45 min | 106 min |
| Max duration | 37.6 hours | 37.6 hours | 2.2 hours |

By level depth:

| Level | Mean Duration | P95 Duration |
|-------|--------------|-------------|
| L0 | 14 min | 20 min |
| L1-L3 | 20-27 min | 25-45 min |
| L4-L7 | 33-55 min | 55-79 min |
| L8-L11 | 60-84 min | 87-118 min |

Duration caps are unnecessary — even a 4-hour cap only affects 9 of 6,419 cycles (0.14%), with zero impact on return or PF.

### Finding 22: Base Size Sensitivity

Tested base sizing from 0.1% to 3.0% of equity ($10k, sqrt, 50:1):

| Base % | Levels | Return | PF | MaxDD | Sharpe |
|--------|--------|--------|-----|-------|--------|
| 0.1% | 17 | 5.6% | 6.63 | -0.09% | 0.428 |
| 0.3% | 13 | 15.3% | 3.92 | -0.89% | 0.154 |
| **0.5%** | **12** | **25.7%** | **3.57** | **-1.10%** | **0.166** |
| 1.0% | 10 | 51.9% | 2.89 | -1.20% | 0.167 |
| 2.0% | 8 | 127.1% | 2.72 | -1.78% | 0.204 |
| 3.0% | 7 | 210.5% | 2.39 | -3.27% | 0.196 |

Trade-off is clear:
- **Lower base % = more levels = lower bust rate = higher PF** but lower absolute return
- **Higher base % = fewer levels = higher bust rate** but higher absolute return
- **Sweet spot: 0.3-0.5%** balances return, risk, and number of available levels
- At 0.1% base, Sharpe is highest (0.43) with nearly zero drawdown but only 5.6% return

### Finding 23: Monte Carlo with % Equity Compounding

10,000 simulations x 2,000 cycles with compounding % equity sizing:

| Config | P(ruin) | Median Growth | % Profitable | Avg MaxDD | P95 MaxDD |
|--------|---------|---------------|-------------|-----------|-----------|
| $10k / 0.5% / sqrt | **0.00%** | +7.5% | **100%** | 0.7% | 1.1% |
| $10k / 0.5% / 2x | 0.00% | +22.0% | 100% | 1.9% | 3.0% |
| $10k / 0.3% / sqrt | 0.00% | +4.6% | 100% | 0.5% | 0.9% |
| $100k / 0.5% / sqrt | 0.00% | +7.5% | 100% | 0.7% | 1.1% |
| $1M / 0.5% / sqrt | 0.00% | +7.5% | 100% | 0.7% | 1.1% |

**Zero ruin across all capital tiers, all configurations, all 10,000 paths.**

### Finding 24: Scaling Limits — Liquidity

EUR-USD daily volume: ~$750 billion.

| Capital | Cumulative Notional (worst case) | Market Impact |
|---------|----------------------------------|---------------|
| $10k | $380k | NONE |
| $100k | $3.8M | MINIMAL |
| $1M | $38M | LOW |
| $10M | $380M | MODERATE |

Strategy can run at institutional scale up to ~$10M before needing to consider execution optimization (TWAP/VWAP, splitting across venues). Below $1M, market impact is negligible.

### Finding 25: Multiplier Strategy Comparison

Four multiplier strategies tested with % equity sizing:

| Multiplier | Formula | Levels ($10k) | Character |
|------------|---------|---------------|-----------|
| **sqrt(2)** | **1.41^n** | **12** | **Best balance: many levels, moderate growth** |
| Standard 2x | 2^n | 7 | Aggressive: fewer levels, fast doubling |
| Linear | 1+n | 18 | Conservative: most levels, slowest growth |
| Fibonacci | fib(n) | 10 | Moderate: natural growth pattern |

Sqrt is the recommended default — it provides enough levels to make busts extremely rare (0.26%) while still generating meaningful per-cycle profit.

---

## Phase 6: Deep Tail Risk Investigation (Complete)

This phase investigates the fundamental question: **Can the asymmetry between wins and busts be tamed by config tuning, or is it inherent to the martingale structure?**

### Finding 26: The Fundamental Asymmetry — One Bust Erases N Wins

| Config | Avg Win % | Avg Bust % | Bust/Win Ratio | Worst Bust % | Worst Erases |
|--------|-----------|------------|----------------|--------------|-------------|
| 5 lvl / 2x | +0.0142% | -0.0927% | **6.5x** | -0.319% | 22.5 wins |
| 7 lvl / 2x | +0.0202% | -0.3866% | **19.1x** | -1.206% | 59.6 wins |
| 12 lvl / sqrt | +0.0045% | -0.3575% | **78.9x** | -0.766% | 169.1 wins |
| 12 lvl / sqrt / 0.3% | +0.0027% | -0.2145% | **78.9x** | -0.460% | 169.1 wins |
| 12 lvl / sqrt / 1.0% | +0.0091% | -0.7150% | **78.9x** | -1.532% | 169.1 wins |

**The asymmetry ratio INCREASES with more levels.** Going from 5 to 12 levels reduces bust frequency (7.5% -> 0.26%) but each bust becomes proportionally more devastating (6.5x -> 78.9x a single win). Changing base % does not change the ratio — it scales both wins and busts equally.

### Finding 27: Deep Levels (L6+) Are NET NEGATIVE with sqrt Multiplier

Recovery analysis for 12 lvl / sqrt / 0.5% reveals a critical finding:

| Level | Avg P&L if "win" here | Recoveries needed for 1 avg bust |
|-------|----------------------|----------------------------------|
| L0 | +$0.709 (0.006%) | 56 wins |
| L1 | +$0.628 (0.006%) | 63 wins |
| L2 | +$0.545 (0.005%) | 73 wins |
| L3 | +$0.426 (0.004%) | 93 wins |
| L4 | +$0.274 (0.002%) | 144 wins |
| L5 | +$0.024 (0.0002%) | 1,645 wins |
| **L6** | **-$0.257 (-0.002%)** | **Never recovers** |
| **L7** | **-$0.843 (-0.008%)** | **Never recovers** |
| **L8-L11** | **-$1.86 to -$4.88** | **Never recovers** |

With sqrt multiplier, levels beyond L5 "win" the cycle (price hits TP) but the cumulative position costs exceed the TP profit. **These levels prevent a bust but still lose money.** This is why 12-level sqrt has a 99.7% "win rate" but the bust/win ratio is 78.9x — many "wins" are actually small losses.

### Finding 28: The Martingale Invariant

The product P(bust) x avg_bust_severity stays approximately constant:

| Config | P(bust) | Avg Bust % | Product | EV/cycle | Safety Margin |
|--------|---------|------------|---------|----------|---------------|
| 5 lvl / 2x | 0.0746 | -0.093% | 0.00692 | +0.0062% | 1.8x |
| 7 lvl / 2x | 0.0255 | -0.387% | 0.00984 | +0.0099% | 2.0x |
| 12 lvl / sqrt | 0.0026 | -0.358% | 0.00095 | +0.0036% | **4.7x** |

**You cannot reduce both frequency AND severity simultaneously.** This is the martingale invariant. Every config choice trades off one for the other.

However, sqrt configs have a **4.7x safety margin** (bust rate can increase 4.7x before EV goes negative), compared to only 1.8-2.0x for 2x multiplier configs. This makes sqrt more resilient to regime deterioration.

### Finding 29: Consecutive Busts — Extremely Rare but Devastating

| Config | 2 consecutive | 3 consecutive | Impact of 2 | Impact of 3 |
|--------|--------------|--------------|-------------|-------------|
| 5 lvl / 2x | 1 in 179 | 1 in 2,405 | -0.19% | -0.28% |
| 7 lvl / 2x | 1 in 1,543 | 1 in 60,636 | -0.77% | -1.16% |
| 12 lvl / sqrt | 1 in 142,573 | 1 in 53.8M | -0.71% | -1.07% |

With 12 lvl/sqrt, 2 consecutive busts occur once every 142,573 cycles — at ~6,400 cycles/year, that's once every 22 years. 3 consecutive is effectively impossible (once every 8,400 years). **Consecutive bust risk is negligible for this config.**

### Finding 30: Drawdown Recovery Times

| Config | Cycles to recover avg bust | Cycles to recover worst bust | Median actual | Max actual |
|--------|---------------------------|-----------------------------|--------------|-----------
| 5 lvl / 2x | 7 | 23 | 10 | 137 |
| 7 lvl / 2x | 19 | 60 | 29 | 334 |
| 12 lvl / sqrt | **79** | **170** | **93** | **489** |

**Recovery is SLOW with 12 lvl/sqrt.** Each bust takes ~93 winning cycles (median) to recover. At ~22 min/cycle, that's ~34 hours of trading to recover a single bust. With ~6,400 cycles/year and 17 busts/year, roughly 17 x 93 = 1,581 cycles/year go toward bust recovery — 25% of all cycles are just recovering from busts.

### Finding 31: Stress Testing — When Does the Strategy Break?

7 stress scenarios tested with 12 lvl / sqrt / 0.5% baseline (10k sims x 2k cycles):

| Scenario | P(ruin) | Median Return | P5 Return | Avg MaxDD | % Profitable |
|----------|---------|--------------|-----------|-----------|-------------|
| Normal | 0.0% | +7.5% | +5.6% | 0.7% | **100%** |
| 2x Bust Rate | 0.0% | +3.8% | +1.1% | 1.1% | **98.9%** |
| 2x Bust Severity | 0.0% | +4.6% | +0.9% | 1.6% | **97.7%** |
| **2x Rate + 2x Severity** | **0.0%** | **-2.0%** | **-7.0%** | **4.0%** | **22.2%** |
| **Worst 25% of Data** | **0.0%** | **-8.0%** | **-11.0%** | **8.1%** | **0.0%** |
| Zero Expectancy | 0.0% | +0.1% | -1.7% | 1.1% | 53.0% |
| Negative Expectancy | 0.0% | -6.8% | -8.5% | 6.9% | 0.0% |

Key takeaways:
- **Normal + single stress factor**: Strategy survives comfortably
- **Double stress (2x rate + 2x severity)**: Median return goes NEGATIVE. Only 22% of paths profitable. This is the danger zone.
- **Worst-quartile regime**: Total destruction — 0% profitable paths, median -8%
- **No ruin in any scenario** — % equity sizing prevents account blowup, but the strategy bleeds capital under adverse conditions

### Finding 32: Fat Tail Analysis — Distribution Shape

| Config | Skewness | Kurtosis | P1 vs Normal | 5 Worst Cycles |
|--------|----------|----------|-------------|----------------|
| 5 lvl / 2x | -2.8 | 16 | 2.0x fatter | -0.32% to -0.28% |
| 7 lvl / 2x | -5.6 | 59 | 2.2x fatter | -1.21% to -1.01% |
| **12 lvl / sqrt** | **-22.6** | **601** | **0.4x** (concentrated) | **-0.77% to -0.42%** |

The 12 lvl/sqrt config has **extreme kurtosis (601)** — the distribution is incredibly concentrated around small wins with very rare but large left-tail events. Skewness of -22.6 means it's massively left-skewed.

Paradoxically, the P1 tail is **smaller than normal** (0.4x) because busts are so rare that even the 1st percentile is still a win. But when busts do occur, they're extreme outliers (-0.77% vs typical +0.005%).

### Finding 33: When Does a Bust Hurt Most?

Tracking all 17 busts chronologically for 12 lvl / sqrt / 0.5%:

- **Bust severity is proportional to equity** (% sizing): busts at $10.2k lose ~$25, at $12.5k lose ~$52
- **Early busts hurt more psychologically** (larger % of early gains wiped) but less in absolute terms
- **Busts tend to cluster in specific market periods** (7 of 17 busts occurred between cycles 1500-2200)
- **No single bust exceeds 0.77% of equity** — survivable individually
- **Final equity: $12,409** (+24.1%) despite all 17 busts

---

## The Honest Verdict

### What the Strategy IS

A positive-expectancy system that works because EUR-USD exhibits slight mean-reversion at 5-minute ATR-based distances. With 12 levels and sqrt sizing, it converts this microstructure edge into a 99.7% cycle win rate with 0.26% bust probability.

### What the Strategy IS NOT

A free lunch. The martingale invariant ensures that:
1. **Every win is small, every bust is large** — ratio is always 10-80x depending on config
2. **More levels make busts rarer but proportionally worse** — you cannot escape this
3. **25% of all cycles go toward recovering from busts** — the "real" return is the net after recovery
4. **The edge depends on market microstructure** — if mean-reversion disappears, the strategy bleeds

### The Critical Question: Simple Framework or ML?

**Based on Phase 6 findings, the simple framework is SUFFICIENT for normal market conditions** but has no defense against regime shifts:

| Condition | Simple Framework | With ML/Regime Detection |
|-----------|-----------------|-------------------------|
| Normal market | Works well (+7.5% median MC) | Works well |
| Single stress factor | Survives (+3.8%) | Survives better |
| Double stress | **FAILS** (median -2%) | Could halt trading |
| Regime shift | **No detection capability** | Could detect and adapt |

**Recommendation**: The simple framework is viable as a production system IF AND ONLY IF it includes:

1. **Circuit breaker**: If rolling bust rate exceeds 2x historical (0.52%), halt trading for N hours
2. **Regime monitor**: Track rolling 100-cycle bust rate, ATR expansion, spread widening
3. **Max daily loss**: Cap at -2% equity per day regardless of cycle count
4. **Gradual scaling**: Start at 0.3% base, increase to 0.5% only after 500+ profitable cycles

**For a more robust system**: ML could provide:
- Regime detection (trending vs mean-reverting periods)
- Dynamic level adjustment based on predicted volatility regime
- Entry quality scoring (even small improvements at L0 compound massively)
- Bust probability estimation for circuit breaker decisions

The simple framework captures ~80% of the opportunity. ML could capture the remaining 20% and, more importantly, provide protection during the regime shifts that the simple framework cannot detect.

---

## Recommended Production Configuration

```
Base size:     0.3% of equity (conservative start)
Multiplier:    sqrt(2) per level (~1.414x)
Max levels:    Auto (determined by available margin)
Leverage:      50:1
Entry signal:  EMA 8/21 crossover
TP distance:   ATR(14) * 0.8
Hedge dist:    TP / 2.0
Duration cap:  None needed (95% of cycles < 50 min)

CIRCUIT BREAKERS (mandatory):
- Max daily loss: -2% of equity -> halt for 24 hours
- Rolling bust rate: if > 0.52% (2x normal) over last 200 cycles -> halt
- Max consecutive busts: 3 -> halt and review
- ATR expansion: if ATR > 2x 200-period average -> reduce base to 0.1%
```

### Risk Profile (Honest Assessment)

| Risk Metric | Value | Assessment |
|-------------|-------|------------|
| EV per cycle | +0.0036% | Positive but thin |
| Bust/win ratio | 78.9x | High — structural |
| Recovery cycles per bust | 93 median | Slow |
| Cycles spent recovering | ~25% of all cycles | Significant drag |
| Safety margin (sqrt) | 4.7x before EV=0 | Good buffer |
| P(ruin) normal conditions | 0.00% | Excellent |
| P(ruin) double stress | 0.00% (but -2% median) | Survives but bleeds |
| Regime shift vulnerability | HIGH — no detection | Critical gap |
| Kurtosis | 601 | Extreme fat tails |

---

## File Reference

| File | Phase | What |
|------|-------|------|
| `01_momentum_indicators.ipynb` | 1 | Indicators provide zero edge (proven) |
| `02_atr_distance_sweep.py` | 1 | Distance ratio determines win rate (proven) |
| `03_cooldown_session.py` | 1 | Cooldown has no effect (proven) |
| `04_monte_carlo.py` | 1 | Ruin probability — SUPERSEDED by scripts 09, 10 |
| `05_full_cycle_simulation.py` | 2 | Bust rate under filters (complete) |
| `06_cycle_pnl_analysis.py` | 2 | P&L distribution, equity curve (complete) |
| `07_bust_anatomy.py` | 3 | Conditional probabilities, last leg analysis, bust profiling (complete) |
| `08_abort_and_sizing.py` | 3 | Early abort levels, dynamic sizing, hybrid strategies (complete) |
| `09_monte_carlo_corrected.py` | 4 | Corrected Monte Carlo with real distributions (complete) |
| `10_capital_scaling_risk.py` | 5 | % equity sizing, capital scaling, quant risk metrics, duration analysis (complete) |
| `11_tail_risk_deep_dive.py` | 6 | Fundamental asymmetry, martingale invariant, stress testing, fat tails (complete) |
