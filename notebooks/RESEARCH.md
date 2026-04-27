# Grid-Hedged Martingale Anatomy Research

Research program studying each aspect of the Surefire Hedge strategy in isolation to find novel insights not present in the academic literature.

**Data:** OANDA EUR-USD 5m, 2006–2024 (18 years, ~2.1M candles)
**Engine:** Real qengine backtester with **real per-candle OANDA bid/ask spread** (2006-2024 stats: mean 1.57, median 1.50, p25 1.40, p75 1.60, p95 1.90 pips; verified hit_rate=100% on the full dataset), 30:1 leverage, proportional sizing
**Config:** Canonical HP = sf=2.0, ml=6, hedge=20, tp=20, random signal, 0.5% base size

**Spread model note:** Empirical backtests use real per-candle broker spread via `qengine/services/spread_data.py` (loaded automatically during candle loading). Previous drafts of the findings labeled results as "at 2-pip spread" — that label was incorrect. The 2-pip assumption appears only in the analytical cost-model scripts (`04_cost_model/*.py`, `08_broker_mechanics/02_margin_closeout_model.py`), not in the empirical backtest-derived findings.

## Executive Summary (2026-04-22)

### The Core Finding
**No static HP configuration produces positive EV in 2006-2024 EUR-USD under real OANDA spreads** (mean ~1.5 pips). Break-even win rate (99.58% for sf=2.0/ml=8, 98.98% for canonical sf=2.0/ml=6) exceeds empirical win rate (98.41% / 97.43% respectively). All 25 tested configurations across (sf, ml) space have negative margin of safety; the least marginal configs are statistically >4σ below break-even. The tested parameter space has no observed feasible region.

**What this means for pipelines:** The strategy's value proposition depends on *adaptive HP selection* or on a directional entry edge that adds ≥2pp to the level-0 win rate. IslandPilot's role is regime-conditional adaptation — selecting configurations (and/or entry filters) whose break-even threshold is achievable in the current market structure.

### Top 5 Novel Findings

1. **N-to-1 bifurcation at ml=5-6**: avg_win turns negative for sf≤1.5 at ml≥6 (spread erodes all win value). Range: N=7.4 to 4827 across the HP space. sf=2.0 is the only value with positive avg_win at all 5 tested ml points (ml=7 not directly tested).

2. **Bust rate is sizing-factor-independent**: At each ml value within effective_max, bust_rate is identical for all sf values. Only effective_max_levels and hedge_distance determine bust probability. Adjusting sf is irrelevant for bust frequency.

3. **Configured max_levels ≠ effective max_levels for high sf**: The strategy applies `effective_max = min(configured, affordable)` at session start. sf=2.0→7, sf=2.5→6, sf=3.0→5. Pipelines specifying max_levels independently of sf silently sample a smaller space than configured.

4. **`bust_rate` metric conflates aborts with catastrophic busts — K=1 is total-loss optimal**: `is_bust` in the backtester includes any terminal outcome (abort, max_level_bust, sl_hit, etc.). Active abort policies mechanically raise bust_rate by definition. The correct objectives are total dollar loss and max_level_bust count separately; both favor K=1 strongly.

5. **Lot rounding imposes $5k minimum equity (live only)**: At $1k equity, OANDA integer unit rounding causes 10% position sizing error. At $5k+, this falls below 1.2%. In simulation this effect is absent (fractional units).

## Research Structure

| Module | Question | Status |
|--------|----------|--------|
| `01_finite_capital/` | N-to-1 ratio, break-even win rate, capital boundary | Complete |
| `02_bust_anatomy/` | Bust structure, level distribution, path patterns | Complete |
| `03_margin_mechanics/` | Margin trajectory, implicit forced closes, cushion map | Complete |
| `04_cost_model/` | Spread per level, swap drag, effective grid distance | Complete |
| `05_market_structure/` | Holding time, margin consumption rate, volatility vs hedge | Complete |
| `06_abort_theory/` | Abort vs no-abort sweep, point-of-no-return, optimal K | Complete |
| `07_hp_interactions/` | Sizing×levels, hedge×TP, equity sensitivity, heatmaps | Complete |
| `08_broker_mechanics/` | Lot rounding, NAV closeout model, OANDA vs generalized | Complete |
| `09_synthesis/` | Novel findings, pipeline implications, open questions | Ongoing |

## Key Findings Index

See `09_synthesis/01_novel_findings.md` for detailed findings.

- F1: Structural negative EV at ml=8 override (break-even 99.58% > actual 98.41%); canonical ml=6 similar (98.98% > 97.43%)
- F2: Deterministic bust structure (std=0 position count; canonical ml=6 busts at level 5, ml=8 override at level 6)
- F3: Margin not binding at realistic 0.5% base sizing (cumulative utilization ≤ 8.5% at level 8)
- F4: N-to-1 bifurcation at ml=5-6 — complete 25-config heatmap
- F5: Methodological caveat — 04_cost_kills_edge.py compares costs at 22× stress-test sizing to strategy's real avg_win. The "level 1" crossover is an artifact; at consistent sizing, crossover is at level 5.
- F6: EV negative at all levels — abort cannot create positive EV, only caps downside
- F7: Peak-equity-per-leg ratio 8.4× higher in bust sessions (peak drawdown differential ~27×)
- F7b: 0/25 HP configs viable under real OANDA spread (~1.5 pips mean) — margins of safety −1pp to −7pp (−4σ to −100σ)
- F8: Wider hedge (5→40 pips) reduces bust_rate 7.3×; avg_win flips sign from −$0.11 to +$3.00
- F9: Higher max_levels decreases bust_rate by ~1.8× per added level (partly definitional)
- F10: TP<hedge gives lowest bust_rate but worst PnL (spread dominates); TP>hedge monotonically raises bust_rate
- F11: Bust rate equity-invariant in simulation; lot rounding breaks this below $5k in live
- F12: Two failure modes: TP<hedge (spread-dominated) vs TP>hedge (recovery-dominated)
- F13: Zero margin calls across 772 bust events tested
- F14: Hedge ≤ ~8-10 pips gives non-positive avg_win under real OANDA spread (~1.5 pips mean)
- F15/18 (merged): Optimal abort K=1 by total loss AND catastrophic-bust count (1 vs 60 baseline). Active aborts inflate "is_bust" metric because the flag absorbs abort outcomes by definition.
- F15b: Bust rate sizing-factor-independent within effective_max range
- F16: Lot rounding 10% error at $1k equity, <1.2% at $5k+
- F17: NAV closeout triggers 22pp higher margin utilization vs equity-based (at stress-test base sizing)
- F19: Configured max_levels silently capped by `_max_affordable_levels()` for high sf
- F20: Total PnL degrades monotonically with sf; sf=1.3 ml=3 is total-P&L-optimal (but NOT best by avg_win or margin of safety)

## Pipeline Implications

See `09_synthesis/02_pipeline_implications.md` for full details.

**IslandPilot:**
- Add effective_max_levels feasibility constraint
- Safe (sf, ml) region (combined avg_win>0 and effective_max filters):
  sf=1.3→ml≤4; sf=1.5→ml≤5; sf=1.7→ml≤5 (conservative); sf=2.0→ml≤7; sf=2.5→ml≤6; sf=3.0→ml≤5
- Reject individuals with N=nan (avg_win ≤ 0)

**ARIA:**
- Abort objective must shift from "is_bust rate" to (1) total dollar loss + (2) catastrophic (max_level_bust) count — tracked separately, since aborts inflate the aggregated is_bust metric
- K=1 is optimal on BOTH axes (cuts total loss 46% and catastrophic busts 60→1); K=6 is a compromise for session continuity (3 catastrophic busts remain, $2,202 more loss vs K=1 though still $729 better than baseline)
- Add `peak_equity_pct / trade_count` ratio as a within-session danger feature (>3 = elevated)

**Live trading:**
- Minimum equity: $5k for accurate position sizing at OANDA (lot rounding)
- NAV-based margin gap: immaterial at the strategy's 0.5% base sizing (Finding 3), but becomes material if base_pct is increased ≥10×
