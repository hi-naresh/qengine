# Pipeline Comparison — Real Engine, Cost Model OFF

**Period:** 2026-01-01 → 2026-04-08 (~3.3 months, 139,440 1m candles, EUR-USD)
**Strategy:** `Martingale` strategy, preset `original` (long-only, geometric 2×, max 7 levels, 10 pip hedge, 20 pip TP, no entry signal — every-bar attempt)
**Engine:** Real `qengine.research.backtest.backtest()` with `cost_model=False` (spread + fee zeroed)
**Starting balance:** $10,000
**Excluded:** AgentPilot (per request)

> **Note on `total_closed_trades = 0`.** This is a CFD/ticket-mode artifact. In CFD mode the Martingale strategy opens cycles via `CFDTicket` objects, not classic positions, so the engine's classic-trade counter and Sharpe/Sortino/Calmar all read zero. The authoritative numbers are `net_profit`, `max_drawdown`, and the per-pipeline `cycles` block from `PipelineStats`. Both are tracked correctly.

## Headline numbers

| Run         | Cycles | Win % | Avg PnL | Net P&L | Net %  | Max DD | PF    | Block % | Notes |
|-------------|-------:|------:|--------:|--------:|-------:|-------:|------:|--------:|-------|
| Baseline    | 850 (raw) | — | — | **−$171.38** | −1.71% | **−6.09%** | 0.972 | — | No pipeline; pure martingale-on-tick |
| IslandPilot | 713 (raw) | — | — | **−$124.76** | −1.25% | **−3.67%** | 0.976 | — | Active across 73 regimes; cycle tracker not exposed |
| ARIA        | **15** | **66.7%** | +$1.72 | **+$25.77** | +0.26% | **−1.51%** | 1.203 | 0% | Aborted 9/15; conformal not yet active (needs ≥20 cycles) |
| GridPilot   | 1 | 0% | −$57.14 | −$57.14 | −0.57% | −1.53% | — | — | Scorer warmed but strategy entered once; pipeline didn't get exercised |
| GTSBotPilot | **295** | **82.7%** | +$0.53 | **+$155.92** | **+1.56%** | **−0.49%** | **1.333** | **95.2%** | Best raw P&L; trend gate blocked 5,876/6,170 attempts |

## Per-pipeline reading

### Baseline (no pipeline)
Martingale `original` with no entry signal opens 850 raw broker tickets across the window, finishes −1.71% with a −6.09% peak-to-trough drawdown. Even with cost model OFF, the strategy has no positive expectancy on this 3.3-month sample. This is the floor every pipeline must clear.

### IslandPilot
- Visits 73 regime islands; the inferencer is alive and switching genomes.
- −16% raw trade count vs baseline (713 vs 850) — the genome-switching changes execution but does not gate entries.
- **−40% drawdown** vs baseline (−3.67% vs −6.09%) and 27% better net P&L (−$124.76 vs −$171.38).
- Still net-negative; spread-free conditions are not enough by themselves to flip the strategy.
- **Headline claim it can support:** *"Regime-aware genetic execution-parameter evolution reduces drawdown by 40% on a baseline-losing martingale strategy without altering its entry logic."*

### ARIA
- Only **15 cycles** completed — the 6-layer pipeline is much more selective than the others.
- **Profitable: +0.26%** with the smallest drawdown of any pipeline that actually ran multiple cycles (−1.51%).
- 9/15 cycles aborted by RiskShield; 8 of the closed cycles ended in `margin_call` (which here means "abort triggered before deeper bust").
- **Conformal calibration did not activate** in this window (`conformal_active: false`, needs ≥20 cycles). The result is essentially the fallback rule + HP engine.
- HP engine warmed up and selected `signal_mode=random`, `sizing_curve=geometric`, max_levels=6 — the contextual bandit converged to a slightly more conservative variant of the preset.
- **Caveat:** 15-cycle sample is too small to claim significance. Re-run on 12-month window to let conformal layer activate.

### GridPilot
- Strategy opened **one** cycle that ran 19,883 bars (~70 days) and closed at session end at −$57.14. The Q-abort never fired because the duration bin saturated.
- Scorer warmed up but `seeded: false` — it built its own normalizer in-window rather than loading the pre-trained 60k-cycle stats. Pre-trained Q-table loaded correctly.
- 0 gate checks recorded — the strategy stopped attempting new entries after the first cycle locked open.
- **Not a fair test** — the underlying Martingale's interaction with this pipeline needs investigation. GridPilot's Phase-2 research validation was on the toy simulator, not the CFD-ticket engine.

### GTSBotPilot
- **Best raw performance: +1.56% net, −0.49% DD, 82.7% win rate over 295 cycles.**
- TrendFilter blocked 5,876 of 6,170 entry attempts (95.2% block rate) — the system trades only when the EMA-derivative trend filter confirms.
- BasketManager closed 244 cycles at profit-target, 51 at loss-cutoff — clean execution.
- **But the pipeline is a re-implementation of Rundo et al. 2019** (Appl. Sci., 9, 1796) and per the novelty review (`docs/novelty_gtsbot_pilot.md`), Yeh, Hsieh & Huang (2022, *Electronics*) already benchmarked the original GTSbot against 8 grid variants. So this strong result is a **validation of prior art**, not a novel finding.

## What this comparison shows

1. **Baseline loses even cost-free** — the `original` preset has no edge. So any positive number from a pipeline is contribution from the pipeline itself, not the strategy.
2. **IslandPilot's value is risk reduction**, not return generation. 40% DD cut is the cleanest claim.
3. **ARIA's profit is on a sample too small to be statistically defensible.** The 6-layer system is interesting but the test window starves the conformal layer of calibration data.
4. **GridPilot needs re-testing** — single-cycle run is a setup issue, not a pipeline failure.
5. **GTSBotPilot wins on the metric, loses on novelty** — confirmed in literature review.

## Recommended follow-ups before paper

- **Extend test window to 12 months** so ARIA's conformal layer activates and IslandPilot accumulates enough per-regime cycles.
- **Investigate GridPilot's single-cycle run** — likely interaction between the pipeline's `should_abort` hook and the Martingale strategy's CFD-ticket mode.
- **Add cost-on comparison** — the cost-free numbers are a "floor". A paper claim needs to show pipeline value persists with realistic spread (2 pips OANDA EUR-USD).
- **Statistical significance** — bootstrap the per-cycle PnL distribution and compute Diebold-Mariano vs baseline, otherwise reviewers will reject on N.

**Raw data:** `notebooks/phase4/results/51_pipeline_comparison.json`
**Runner:** `notebooks/phase4/51_pipeline_comparison.py`
