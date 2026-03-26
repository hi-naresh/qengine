---
name: surefire-research
description: Knowledge base for SurefireHedge V2 research. Use when working on surefire strategy analysis, notebooks, ML targets, or next-phase planning. Prevents hallucination by grounding all claims in validated findings.
---

# SurefireHedge V2 Research — Validated Knowledge Base

> RULE: Every claim must trace to a specific script and finding number. If you cannot cite the source, say "not validated" instead of guessing.

## Strategy Mechanics

- Grid-hedged martingale on EUR-USD 5m candles
- Entry: EMA 8/21 crossover (placeholder — proven to provide zero edge, exists only as a trigger)
- TP distance: ATR(14) * 0.8
- Hedge distance: TP / 2.0 (hedge is CLOSER than TP)
- On hedge hit: open opposite position at multiplier * previous size
- On TP hit: close all positions — cycle wins
- If all levels exhausted: bust — close all at loss
- Leverage: 30:1 (parameterized, can use 20:1)

## Proven Facts (DO NOT contradict these)

### What DOES NOT work (scripts 01-03, 05, 07)
- **No indicator improves L0 win rate** — EMA, RSI, MACD, SMA, ADX, all combinations tested. All ~33%. L0 win rate is mechanically set by TP/hedge distance ratio (1/(RR+1) for random walk). Script 01.
- **Cooldown has zero effect** — P(loss|prev loss) = P(loss). Market is memoryless at this timescale. Script 03.
- **Session filters are marginal** — Best combo reduces bust rate 16% (7.53%→6.32%). Not enough to change risk profile. Scripts 03, 05.
- **No pre-entry feature predicts busts** — Cohen's d < 0.1 for ALL features (ATR, RSI, trend, momentum, range, Bollinger). Busts begin AFTER entry. Scripts 07, 14.
- **Busts do not cluster** — P(bust|prev bust) ≈ P(bust). Clustering ratio 1.06x. Script 07.

### What DOES work (scripts 08, 10, 12, 13)
- **sqrt(2) multiplier** — PF 1.89→2.93 vs 2x. Mathematical proof: p*m = 0.80 < 1 (adding levels HELPS). Script 12.
- **More levels** — P(bust) 7.5% at 5 levels → 0.26% at 12 levels. But asymmetry grows (78.9x bust/win ratio). Script 08, 10.
- **% equity sizing** — Replaces fixed lots. Auto-adapts levels to capital. Identical % returns at any capital tier. Script 10.
- **Base size 0.3-0.5%** — Sweet spot. Lower = more levels + higher PF but lower return. Script 10.
- **Blind test outperforms train** — No overfitting. Mean-reversion edge is real and persistent. Script 13.

### Mathematical constraints (scripts 11, 12, 14)
- **P(bust) > 0 always** — finite capital guarantees max level count. INHERENT.
- **Asymmetry ratio > 1 always** — one bust erases 78.9 average wins at 12 lvl/sqrt. INHERENT.
- **Martingale invariant** — Risk = (p*m)^N / (m-1). Cannot reduce both frequency AND severity. INHERENT.
- **Average P(lose per level) = 0.566** — stable across train/test periods (L0: 0.623 train, 0.634 test). Script 12, 13.
- **Critical multiplier m* = 1/p = 1.768** — sqrt(2)=1.414 < m* (HELPS), 2.0 > m* (HURTS). Script 12.
- **Deep levels (L6+) are NET NEGATIVE** with sqrt — they prevent bust but lose money. Script 12.
- **98.7% of busts are choppy range** — oscillation between h and tp. INHERENT geometric vulnerability. Script 14.
- **41.8% of random market windows are bust-like** — but most don't align with hedge distances. Script 14.

### Production numbers at 30:1 leverage (scripts 10, 11, 13)
- Win rate: 99.7%, Bust rate: 0.26%, PF: 3.56
- Return: 14.7% (0.5% base), MaxDD: -0.66%
- Calmar: 22.4, Kelly: 0.788, Max consecutive losses: 2
- 0% ruin across all MC scenarios (10k paths x 2k cycles)
- Safety margin: 4.7x (bust rate can increase 4.7x before EV=0)
- Under 2x stress: median return -1.8%, only 14.6% profitable
- Blind test: train return 2.90%, test return 7.48% (test BETTER)

## The Two Validated ML Targets

### P5: Entry Quality (HIGHEST impact)
- Current: P(L0 lose) = 0.63
- If reduced to 0.50: +12% EV improvement, p*m drops from 0.80→0.71
- Simple indicators CANNOT do this (all tested, Cohen's d < 0.1)
- Requires: non-linear classifier on high-dimensional features
- This is the #1 priority for ML

### P6: Regime Detection (CRITICAL for survival)
- A 10% increase in P(lose) → 3.1x increase in P(bust)
- A 20% increase → 8.7x increase in P(bust)
- Simple framework has NO regime detection capability
- Under double stress: strategy bleeds silently
- Requires: HMM, change-point detection, or online Bayesian estimation
- This is #2 priority but CRITICAL for not blowing up

## Parameter Tuning: What the Research Proved

### Static optimization is SOLVED (script 12)
- The MINLP (5 variables: base, multiplier, levels, TP dist, hedge dist) is trivially solvable
- Exhaustive search over N=2..20 finds optimal configs
- Current config (12 lvl, sqrt, 0.5%, TP=0.8*ATR, RR=2.0) is near the Pareto frontier
- Adding levels has diminishing returns (+1.9% EV per level)
- Sensitivity: TP distance +10% → +32.3% EV, P(lose) -10% → +26.6% EV

### Dynamic optimization REQUIRES regime detection
- The optimal multiplier depends on p: m* = 1/p
- If p changes (regime shift), optimal config changes
- But you can't know p has changed without detecting the regime shift first
- This is P6 — an ML problem, not a parameter tuning problem
- Without regime detection, static config with circuit breakers is the best simple approach

## What NOT to do in next phase research
- Do NOT test more simple indicators — proven useless (script 01)
- Do NOT add cooldown logic — proven useless (script 03)
- Do NOT try to predict individual busts from pre-entry features — proven impossible (Cohen's d < 0.1, scripts 07, 14)
- Do NOT change the fundamental hedge geometry (TP > h) — this is what makes the strategy work
- Do NOT assume 2x multiplier is viable — mathematically proven inferior (p*m > 1, script 12)
- Do NOT confuse "win rate" with "profitability" — 99.7% win rate includes net-negative "wins" at L6+
