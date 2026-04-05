# Phase 3 Verdict: Chop-Focused Martingale Research

**Dataset**: EUR-USD 5m, 2006-01-03 to 2025-12-30 (~2.09M candles, ~13,600 cycles)

---

## Executive Summary

The grid/hedge martingale strategy is **structurally profitable** (PF 1.30, 99.5% win rate) but vulnerable to choppy markets. Phase 3 investigated whether chop detection and handling could eliminate this vulnerability. The answer: **partially**.

- Chop **avoidance** via single-indicator gates reduces busts by 35% (ER_100 gate: bust 0.35% -> PF 1.70)
- Chop **handling** mid-cycle (wider hedges) provides marginal benefit (+2% bust reduction)
- **N-regime switching** (8 data-driven regimes) boosts PF from 1.30 to 1.52
- On **2024-2025 validation** data, the strategy remains profitable (PF 1.05-1.14) but thinner margins
- Markets are getting **more choppy** over time (slope +0.004/era, 2024-2025 is 25% choppy vs 22% in 2009)

**Ship**: Efficiency Ratio gate (ER_100 > threshold) + EMA entry signals + regime-aware config switching.

---

## Script-by-Script Results

### 21. Chop Anatomy

**Question**: What does chop look like and which indicators detect it best?

| Indicator | AUC (bust prediction) | Cohen's d |
|---|---|---|
| efficiency_ratio_100 | **0.559** | 0.181 |
| atr_ratio | **0.558** | 0.206 |
| range_vs_atr_200 | 0.550 | 0.003 |
| adx_100 | 0.544 | 0.211 |
| choppiness_index_200 | 0.545 | 0.121 |

**Findings**:
- Best bust predictor: Efficiency Ratio at 100-bar window (AUC 0.559)
- ATR ratio (14/50) is a close second (AUC 0.558)
- The traditional Choppiness Index is mediocre (AUC 0.525-0.545)
- Early warning: best separation at 50 bars before bust (sep=0.039)
- Composite chop score at bust entries (0.253) vs wins (0.279) — counter-intuitive, meaning busts happen in low-chop entries too

**Implication**: No single indicator is a silver bullet (all AUCs < 0.6). Bust prediction is hard because busts are rare (0.54%) and not strongly regime-dependent.

---

### 22. Chop Avoidance

**Question**: Can we skip entries in choppy conditions to reduce busts?

| Filter | Bust Rate | Bust Reduction | PF | % Trades Kept |
|---|---|---|---|---|
| Baseline (none) | 0.54% | — | 1.30 | 100% |
| ER_100 gate | 0.35% | **-35%** | **1.70** | 60% |
| range_vs_atr_100 | 0.36% | -33% | 1.73 | 30% |
| CHOP_200 gate | 0.38% | -30% | 1.62 | 67% |
| ADX gate | 0.40% | -26% | 1.54 | 40% |
| Composite 0.6 + ER | 0.35% | **-35%** | **1.72** | 36% |

**Findings**:
- Composite chop score threshold sweep (0.25-0.9) alone does almost nothing — the score as calibrated doesn't separate bust entries well
- **Individual indicator gates work much better** than the composite score
- Best single gate: Efficiency Ratio at 100 bars → 35% bust reduction, PF jumps to 1.70
- Trade-off: keeping 60% of trades (40% skipped) for 35% fewer busts and 31% higher PF
- The composite + ER combo achieves similar results but keeps fewer trades (36%)

**Best approach**: Gate on ER_100 alone. Simple, effective, minimal signal loss.

---

### 23. Chop Handling (Mid-Cycle)

**Question**: If caught in chop during a cycle, can we limit damage?

| Strategy | Bust Rate | Change | PF |
|---|---|---|---|
| none (baseline) | 0.54% | — | 1.30 |
| wider_hedge | 0.53% | -2% | 1.31 |
| reduced_sizing | 0.54% | 0% | 1.30 |
| tighter_tp | 0.54% | 0% | 1.30 |
| early_abort | 4.78% | **+785%** | 1.19 |
| combined | 3.40% | +530% | 1.17 |

**Findings**:
- **Wider hedges provide marginal benefit** (+2% bust reduction, +0.01 PF)
- Early abort is **catastrophic** — aborting at level 2-3 in chop turns near-misses into realized losses
- Combined strategies also hurt — the abort component dominates negatively
- Mid-cycle chop handling is fundamentally limited because chop detection is noisy (AUC < 0.6)

**Verdict**: Mid-cycle handling is not worth the complexity. Avoidance (script 22) is far superior.

---

### 24. N-Regime Islands

**Question**: How many market regimes exist, and can we optimize per-regime?

**Discovered**: 8 regimes via GMM + BIC (on 100K subsample, applied to full 2M)

| Regime | Type | % Data | Chop Score | % Choppy |
|---|---|---|---|---|
| R0 | MIXED | 21.6% | 0.417 | 1% |
| R1 | TRENDING | 11.2% | 0.154 | 0% |
| R4 | TRENDING | 22.4% | 0.306 | 0% |
| R3 | TRENDING | 12.3% | 0.310 | 0% |
| R7 | MIXED | 1.7% | 0.524 | 28% |
| Others | TRENDING | 5.4% each | <0.25 | 0% |

| Approach | Bust Rate | PF | PnL |
|---|---|---|---|
| Static (one config) | 0.5% | 1.30 | 32,486 |
| Chop avoidance only | 0.5% | 1.30 | 32,310 |
| **N-regime switching** | **0.4%** | **1.52** | **103,858** |

**Findings**:
- Data says 8 regimes, not 3 — but most are trending variants
- Only R7 (1.7% of data) is meaningfully choppy (28% choppy bars)
- Regime-optimized configs boost PF from 1.30 to 1.52 (+17%)
- PnL triples because each regime gets its optimal sizing/hedge/TP parameters
- Fibonacci sizing with 12 levels dominates in most regimes

**Verdict**: Per-regime optimization is the biggest single improvement found.

---

### 25. Era Relevance

**Question**: Does old data (2006+) still apply to 2024-2026 markets?

| Era | Bust Rate | PF | Mean Chop | % Choppy |
|---|---|---|---|---|
| 2006-2008 | 0.0% | 4.07 | 0.398 | 23% |
| 2009-2011 | 0.5% | 1.35 | 0.395 | 22% |
| 2012-2014 | 0.0% | 2.97 | 0.409 | 24% |
| 2015-2017 | 1.1% | 0.91 | 0.418 | 25% |
| 2018-2020 | 0.8% | 1.19 | 0.418 | 25% |
| 2021-2023 | 0.3% | 1.57 | 0.417 | 25% |
| 2024-2025 | 0.6% | 1.25 | 0.420 | 25% |

| Data Window | Train PF | Test PF | Generalization |
|---|---|---|---|
| Last 3yr | 1.00 | 0.89 | 0.89 |
| **Last 5yr** | 0.97 | 1.03 | **1.06** |
| Last 7yr | 1.07 | 1.08 | 1.01 |
| Last 10yr | 1.10 | 1.10 | 1.00 |
| Last 20yr | 1.09 | 0.99 | 0.91 |

**Findings**:
- Markets are **slowly getting choppier** (slope +0.004 per era)
- 2006-2008 and 2012-2014 were golden eras (PF 4.07 and 2.97) — unlikely to repeat
- 2015-2017 was the worst era (PF 0.91, bust 1.1%) — coincides with extreme ECB policy
- **Best training window: last 5 years** (generalization ratio 1.06 — test outperforms train)
- Very old data (pre-2015) inflates training metrics but doesn't help out-of-sample
- 3 years is too short (overfits), 15-20 years is too long (stale patterns)

**Verdict**: Use 5-7 years of history for calibration. Older data adds noise, not signal.

---

### 26. Validation on 2024-2025

**Question**: Do these techniques actually work on the most recent data?

| Strategy | Cycles | Bust% | PF | PnL |
|---|---|---|---|---|
| baseline | 975 | 0.8% | 1.05 | 470 |
| chop_avoidance | 970 | 0.8% | 1.04 | 401 |
| strict_avoidance (0.5) | 958 | 0.8% | 1.04 | 334 |
| abort_at_6 | 1019 | **8.5%** | 0.99 | -66 |
| **ema_signals** | 1097 | 0.8% | **1.14** | **1,443** |
| ema_chop_avoid | 1095 | 0.8% | 1.14 | 1,409 |
| conservative | 908 | 2.4% | 1.11 | 845 |
| conservative_chop_avoid | 904 | 2.4% | 1.10 | 797 |

**Findings**:
- 2024-2025 is MORE choppy than historical (+1% shift in mean chop score)
- **EMA crossover signals beat random signals** (PF 1.14 vs 1.05) — entry quality matters
- Chop avoidance adds almost nothing on recent data (PF 1.04 vs 1.05)
- Abort strategies remain destructive (8.5% bust rate)
- Conservative config (fewer levels, wider hedges) helps modestly (PF 1.11)
- Overall PF on 2024-2025 (1.05-1.14) is lower than historical average (1.30) — margins are thinner

**Verdict**: The strategy works but is **thinner** in current markets. Signal quality (EMA > random) matters more than chop filtering on recent data.

---

### 27. Full Indicator Scan (160 of 174 indicators)

**Question**: Which of the 174 jesse-rust indicators best predict busts / work as entry gates?

**Dataset**: EUR-USD 5m, 2023-06 to 2025-12 (~270K candles, 1412 cycles, EMA signals)

| Indicator | AUC | Cohen's d | Gate PF | Bust Reduction | Kept% |
|---|---|---|---|---|---|
| **dm_14** (Directional Movement) | 0.7314 | 0.836 | **1.81** | **-44%** | 93% |
| safezonestop_14 | 0.7308 | 0.873 | 1.51 | -38% | 90% |
| chande_14 | 0.7244 | 0.841 | 1.51 | -38% | 90% |
| devstop_14 | 0.7238 | 0.837 | 1.51 | -38% | 90% |
| sar | 0.7237 | 0.842 | 1.52 | -38% | 90% |
| kaufmanstop_14 | 0.7235 | 0.844 | 1.51 | -38% | 90% |
| supertrend_14 | 0.7230 | 0.841 | 1.51 | -38% | 90% |

**AUC Distribution**: 159 indicators tested. Most cluster around 0.50-0.55 (useless), but ~30 indicators have AUC > 0.70.

**Findings**:
- **DM (Directional Movement) at period 14 is the single best bust predictor** — AUC 0.73, 44% bust reduction while keeping 93% of signals
- The top predictors are **trend-following** indicators (DM, SAR, stops), not chop detectors
- This confirms the volatility advantage thesis: trend direction matters more than chop avoidance
- Many moving averages (ALMA, DEMA, JMA, HMA, etc.) cluster at AUC ~0.72 — they all capture the same signal (price direction)
- All 30 tested gates beat baseline by >20% PF improvement
- The original ER_100 from script 22 (AUC 0.559) is **far inferior** to DM_14 (AUC 0.731)

**Verdict**: Use DM_14 as primary entry gate. It captures trend direction — the real predictor of bust vs win.

---

### 28. Volatility Advantage (THE KEY INSIGHT)

**Question**: Does the strategy actually benefit from volatile markets?

**Dataset**: EUR-USD 5m, 2020-2025 (~625K candles, EMA signals)

| Vol Bucket | Cycles | Win% | Bust% | L0+L1% | PF | Avg Bars to Win |
|---|---|---|---|---|---|---|
| very_low | 730 | 57.7% | **1.78%** | 31.1% | **0.52** | 162 |
| low | 729 | 56.5% | 0.41% | 32.0% | 1.48 | 135 |
| medium | 729 | 59.3% | 0.82% | 36.2% | 1.17 | 128 |
| **high** | 729 | 58.7% | **0.27%** | 33.2% | **1.83** | **86** |
| very_high | 729 | 59.5% | 0.55% | 33.7% | 1.32 | 45 |

**Trend x Volatility Matrix** (PF):

| | very_low | low | medium | high | very_high |
|---|---|---|---|---|---|
| no_trend | **0.33** | 4.09 | 1.59 | 2.99 | 3.70 |
| weak_trend | 0.62 | 1.26 | 1.50 | 1.15 | 1.01 |
| strong_trend | 1.02 | 0.99 | 0.55 | **4.35** | 1.19 |

**Confidence Score Gate**:

| Threshold | Bust% | PF | Kept% |
|---|---|---|---|
| 0.50 | 0.60% | 1.20 | 51% |
| 0.70 | 0.39% | 1.44 | 8.3% |
| 0.80 | **0.00%** | **3.54** | 1.6% |

**Critical Findings**:
- **3.5x PF improvement** from worst (very_low: PF 0.52) to best (high: PF 1.83) volatility
- Strategy **LOSES money in very low volatility** (PF 0.52) — this is the real enemy, not "chop"
- High vol wins resolve in **86 bars** vs 162 in low vol — **2x faster TP triggers**
- L0 wins in high vol: **43 bars** (3.5 hours!) vs 117 bars in low vol
- Sweet spot: **strong_trend + high_vol = PF 4.35** — that's the money cell
- At confidence >= 0.80: **zero busts, PF 3.54** (but only 1.6% of signals)
- The real edge isn't avoiding bad entries — it's **aggressively entering good ones**

**Verdict**: Stop thinking defensively (avoid chop). Think offensively: **seek high-vol trending conditions and enter aggressively**.

---

### 29. Complete Sizing Curve Comparison

**Question**: Which sizing curve is best, and does it depend on market conditions?

**Dataset**: EUR-USD 5m, 2020-2025, 504 configurations tested

| Sizing Curve | Avg PF | Best PF | Avg Bust% | Best Bust% |
|---|---|---|---|---|
| **geometric** | 4736 | 633,174 | 7.15% | **0.02%** |
| sqrt | 1.05 | 2.22 | 7.15% | 0.02% |
| fibonacci | 1.06 | 1.37 | 7.15% | 0.02% |
| linear | 1.04 | 1.18 | 7.15% | 0.02% |
| fixed | 1.00 | 1.07 | 7.15% | 0.02% |

**Top configs** (by PF, with >100 cycles):

| Config | Bust% | PF | Exposure |
|---|---|---|---|
| geom x3.0, 12L, h=15p, tp=15p | 0.02% | 633,174 | 265,720x |
| geom x2.0, 12L, h=15p, tp=15p | 0.02% | 9,984 | 4,095x |
| geom x3.0, 8L, h=15p, tp=10p | 0.03% | 3.51 | 3,280x |
| sqrt x3.0, 12L, h=15p, tp=20p | 0.06% | 2.22 | 995x |

**Risk-adjusted** (PnL / max exposure):

| Config | PF | Risk-Adj PnL | Bust% |
|---|---|---|---|
| geom x3.0, 4L, h=8p, tp=15p | 1.08 | 460 | 17.6% |
| fixed, 4L, h=15p, tp=20p | 1.05 | 396 | 10.8% |

**High-vol vs Low-vol best configs**: Geometric sizing dominates in both regimes.

**Findings**:
- **Geometric sizing is dramatically superior** to all other curves
- The extreme PF numbers (633K) reflect near-zero busts with massive position sizing — theoretically optimal but practically requires enormous capital
- 15-pip hedge distance is the sweet spot (gives room to breathe)
- **Risk-adjusted**: 4-level geometric with tight hedges is most capital-efficient
- sqrt is the best practical alternative (lower exposure, still good PF)
- fixed sizing performs worst — confirms that position scaling is essential

**Verdict**: Use geometric sizing for maximum edge, sqrt for practical risk management.

---

## Consolidated Verdict

### What Works (Ranked by Impact)

1. **Volatility-aware entry**: 3.5x PF improvement. High vol = fast TP. This is THE edge.
2. **DM_14 entry gate**: 44% bust reduction, PF 1.81, keeps 93% of signals. Best of 160 indicators.
3. **Geometric sizing**: Dramatically outperforms all other curves
4. **Per-regime config optimization**: +17% PF on full history (1.30 -> 1.52)
5. **Confidence score gate** (vol + trend + DM): At 0.70+ threshold, bust drops to 0.39%, PF 1.44
6. **EMA entry signals**: +9% PF over random entries
7. **5-year training window**: Best generalization ratio (1.06)

### What Doesn't Work

1. **Mid-cycle chop handling**: Marginal at best, destructive at worst
2. **Early abort / level caps**: Converts near-misses into losses
3. **Composite chop score gating**: Too noisy alone (AUC < 0.6)
4. **Fixed sizing**: Worst performer across all conditions
5. **Trading in very low vol**: Strategy LOSES money (PF 0.52)

### The Real Insight

The framing was wrong. We were asking "how to avoid chop?" when we should have asked "when does the strategy thrive?"

**Answer**: The strategy thrives in **high-volatility, trending markets**. In these conditions:
- TP triggers at L0 or L1 within hours
- Bust rate drops to near zero
- PF reaches 4.35 in the best cell (strong_trend + high_vol)

The correct approach is **NOT** defensive (avoid bad entries) but **offensive** (aggressively seek good ones). A confidence score combining NATR, ADX, and ER can identify these windows.

### What's Concerning

1. PF on 2024-2025 (1.05-1.14) is **much thinner** than historical (1.30)
2. Markets are getting **progressively choppier** (slope +0.004/era)
3. Very low vol periods are **strategy-killers** (PF 0.52 = net loss)
4. Geometric sizing has extreme exposure (265,720x at 12 levels) — practically dangerous

### Recommended Pipeline Config

```
Entry signal:     EMA 8/21 crossover
Entry gate 1:     DM_14 directional filter (44% bust reduction, keeps 93%)
Entry gate 2:     NATR vol filter — SKIP when NATR < 20th percentile
Confidence gate:  NATR + ADX + DM composite >= 0.50 (conservative)
                  or >= 0.70 (aggressive, fewer trades, much higher PF)
Sizing:           Geometric x2.0 (high edge) or sqrt x2.0 (practical)
Max levels:       12 (geometric) or 8 (risk-managed)
Hedge distance:   15 pips (proven optimal)
Take profit:      15-20 pips (regime-adjustable)
Abort:            DO NOT USE
Training window:  Last 5 years
Regime detection: GMM with BIC (retrain monthly)
Config switching: Per-regime optimized params
```

### 30. Practical Sizing with Real Capital

**Question**: What can you actually trade with real money?

**Max affordable levels** (bust DD < 20% of account, base = 1 micro lot):

| Curve | Factor | $5K | $10K | $25K | $50K | $100K |
|---|---|---|---|---|---|---|
| geometric | x1.5 | 10L | 10L | 12L | 12L | 12L |
| geometric | x2.0 | 6L | 6L | 8L | 10L | 10L |
| sqrt | x2.0 | 10L | 12L | 12L | 12L | 12L |
| fibonacci | x2.0 | 8L | 10L | 12L | 12L | 12L |

**Simulated 5yr returns** (micro lot base, h=15p, tp=15p):

| Account | Best Config | ROI | MaxDD | PF | Bust Recovery |
|---|---|---|---|---|---|
| **$10K** | fibo x2.0 10L | 3.1% | 15.4% | 1.08 | 59 wins |
| **$50K** | geom x2.0 10L | 4.5% | 17.7% | 2.10 | 456 wins |
| **$100K** | geom x2.0 10L | 2.2% | 9.5% | 2.10 | 456 wins |

**Bust recovery** (wins needed to recover 1 bust):

| Config | 6L | 8L | 10L |
|---|---|---|---|
| sqrt x2.0 | 12 | 23 | 35 |
| geometric x2.0 | 41 | 159 | **456** |
| fibonacci x2.0 | 12 | 31 | 59 |

**Critical findings**:
- Geometric x2.0 at 10L needs **456 wins to recover 1 bust** — extremely fragile
- Geometric x2.0 at 6L on $10K gives **negative ROI** (too few levels to win)
- Fibonacci x2.0 at 10L is the practical sweet spot: 59 wins recovery, 3.1% ROI, 15% DD
- sqrt x2.0 is safest: 12L on $10K, only 23 wins recovery at 8L
- Real ROI on micro lots is **modest** (1-4.5% over 5 years). Need larger base or leverage scaling.

**Verdict**: Geometric sizing's theoretical edge vanishes under capital constraints. Fibonacci at 10 levels is the practical optimum for $10K+. Scale base lot up as equity grows.

---

### 33. Validate ALL Gates on 2024-2025

**Question**: Do the gates actually work on recent data, or just on historical?

**Walk-forward test**: Train thresholds on 2020-2023, test on 2024-2025.

| Strategy | Test PF | Test Bust% | Kept% | vs Baseline |
|---|---|---|---|---|
| **baseline** | 1.15 | 0.08% | 100% | — |
| dm_only | 1.18 | 0.08% | 63% | +3% PF |
| natr_p20 | 1.15 | 0.08% | 100% | 0% |
| conf_0.4 | 1.19 | 0.08% | 85% | +3% PF |
| conf_0.5 | **1.21** | **0.00%** | 35% | +5% PF, zero busts |
| **combined** (DM+NATR+conf) | **1.22** | 0.08% | 62% | **+6% PF** |

**NATR vol filter by percentile cutoff**:

| Cutoff | Train PF | Test PF | Verdict |
|---|---|---|---|
| p10 | 1.04 | 1.15 | WORKS |
| p20 | 1.04 | 1.15 | WORKS |
| p30 | 1.06 | 1.18 | WORKS |
| p40 | 1.07 | 1.13 | FAILS |
| p50 | 1.10 | 1.08 | FAILS |

**DM gate generalization**: train PF=1.11 → test PF=1.18 (ratio=1.06, generalizes well)

**Critical findings**:
- Gates **DO work on 2024-2025** — 6% PF improvement for combined gate
- Confidence >= 0.5 achieves **zero busts** on test data (but only 35% of trades)
- NATR vol filter alone doesn't help (p20 cutoff barely changes anything)
- The combined gate (DM + NATR + confidence) is the best: PF 1.22, keeps 62%
- DM_14 generalizes well (test > train) — not overfit
- Bust rate on 2024-2025 is already very low (0.08%) making bust reduction hard to measure

**Verdict**: Gates provide real but modest improvement on recent data. The strategy is already decent on 2024-2025; gates help at the margin.

---

## Consolidated Verdict (Updated)

### What Works (Ranked by Impact)

1. **Volatility-aware entry**: 3.5x PF improvement. High vol = fast TP. This is THE edge.
2. **DM_14 entry gate**: 44% bust reduction, PF 1.81, keeps 93% of signals. Generalizes to 2024-2025.
3. **Per-regime config optimization**: +17% PF on full history (1.30 -> 1.52)
4. **Combined gate** (DM + confidence): +6% PF on walk-forward test. Validated.
5. **Fibonacci sizing at 10 levels**: Best practical config for $10K+ accounts
6. **5-year training window**: Best generalization ratio (1.06)

### What Doesn't Work

1. **Mid-cycle chop handling**: Marginal at best, destructive at worst
2. **Early abort / level caps**: Converts near-misses into losses
3. **Geometric sizing in practice**: 456 wins to recover 1 bust at 10L — unusable
4. **NATR filter alone**: Barely moves the needle on recent data
5. **Trading in very low vol**: Strategy LOSES money (PF 0.52)

### The Real Insight

The framing was wrong. We were asking "how to avoid chop?" when we should have asked "when does the strategy thrive?"

**Answer**: High-volatility trending markets. In these conditions, TP triggers at L0 or L1 within hours. The correct approach is **offensive** (seek good conditions) not **defensive** (avoid bad ones).

### Practical Reality Check

With $10K on micro lots:
- **Best realistic config**: Fibonacci x2.0, 10 levels, h=15p, tp=15p
- **Expected ROI**: ~3% over 5 years (modest)
- **Max drawdown**: 15%
- **One bust costs**: 59 winning cycles to recover
- To make meaningful returns: either scale lot size as equity grows, or diversify across instruments

### Recommended Pipeline Config

```
Entry signal:     EMA 8/21 crossover
Entry gate:       DM_14 directional filter (validated on 2024-2025)
Confidence gate:  NATR + ADX + ER composite >= 0.40
Sizing:           Fibonacci x2.0 (practical) or sqrt x2.0 (safest)
Max levels:       10 (for $10K+) or 8 (risk-managed)
Base lot:         Scale to keep bust DD < 20% of account
Hedge distance:   15 pips
Take profit:      15 pips
Abort:            DO NOT USE (or Q-learning policy from Phase 2)
Training window:  Last 5 years, retrain monthly
```

### 31. Q-Learning Mid-Cycle Exit (FAILED)

**Question**: Can a learned policy abort mid-cycle to avoid busts?

**Result**: Catastrophic failure. Q-agent aborts 43.5% of cycles, bust rate goes from 0.07% to 43.55%, PF drops from 1.08 to 1.01. Walk-forward: test PF drops from 1.18 to 1.03.

**Why it fails**: Baseline bust rate is 0.07% — there's almost nothing to predict. The agent can't distinguish "temporarily in drawdown" from "will bust" because 99.93% of drawdowns recover. Every abort is a realized loss.

**One useful insight**: The 15 states where abort IS preferred all share `high_vol + weak_trend` — volatile but directionless. This confirms chop is the enemy, but aborting mid-cycle is still not the answer.

**Verdict**: Mid-cycle abort is conclusively dead. Entry gating is the only viable approach.

---

### Remaining Gaps

1. **Multi-instrument** — only EUR-USD tested. Need data for GBP-USD, USD-JPY, XAU-USD to diversify regime risk.
2. **Lot scaling** — need adaptive position sizing as equity grows/shrinks.
3. **Live regime detection** — GMM retrain pipeline for production use.
