# Grid-Hedged Martingale Anatomy Research

Research program studying each aspect of the Surefire Hedge strategy in isolation to find novel insights not present in the academic literature.

**Data:** OANDA EUR-USD 5m, 2006–2024 (18 years, ~2.1M candles)
**Engine:** Real qengine backtester with 2-pip spread, 30:1 leverage, proportional sizing
**Config:** Canonical HP = sf=2.0, ml=6, hedge=20, tp=20, random signal, 0.5% base size

## Executive Summary (2026-04-22)

### The Core Finding
**No static HP configuration produces positive EV with 2-pip spread.** Break-even win rate (99.58%) exceeds empirical win rate (98.41%) for canonical HP. 0/25 tested configurations across (sf, ml) space are viable. The parameter space has no feasible region for a random-signal strategy at OANDA EUR-USD spreads.

**What this means for pipelines:** The strategy value proposition is entirely in *adaptive HP selection*, not the static mechanical grid. IslandPilot's role is not optimization but regime-conditional adaptation — selecting configurations whose break-even threshold is achievable in the current market structure.

### Top 5 Novel Findings

1. **N-to-1 bifurcation at ml=5-6**: avg_win turns negative for sf≤1.5 at ml≥6 (spread erodes all win value). Range: N=7.4 to 4827 across the HP space. sf=2.0 is the only value with positive avg_win at all ml levels.

2. **Bust rate is sizing-factor-independent**: At each ml value, bust_rate is identical for all sf values (1.3 through 3.0). Only max_levels and hedge_distance determine bust probability. Adjusting sf is irrelevant for bust risk management.

3. **Configured max_levels ≠ effective max_levels for high sf**: The strategy applies `effective_max = min(configured, affordable)` at session start. sf=2.5 caps at effective ~6, sf=3.0 at ~5, regardless of configured value. Pipeline parameters silently become incorrect.

4. **PnL-optimal and bust-rate-optimal abort levels are maximally divergent**: K=1 (abort at first hedge) cuts total loss by 46% but increases bust frequency 33x. K=7 is a no-op. Bust rate is the wrong optimization objective when strategy EV is negative.

5. **Lot rounding imposes $5k minimum equity**: At $1k equity, OANDA integer unit rounding causes 10% position sizing error. At $5k+, this falls below 1.2%.

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

- F1: Structural negative EV (break-even 99.58% > actual 98.41%)
- F2: Deterministic bust structure (std=0 trade count, always level 6)
- F3: Margin not binding constraint (0/1200 bust events = margin call)
- F4: N-to-1 bifurcation at ml=5-6 — complete 25-config heatmap
- F5: Spread kills edge at level 1 for all configurations
- F6: EV negative at all levels — abort cannot rescue strategy EV
- F7: Margin consumption 8.4x higher in bust vs win sessions
- F7b: 0/25 HP configs viable with 2-pip spread
- F8: Wider hedge reduces bust 7x AND increases avg_win 5x
- F9: Higher max_levels decreases bust rate (counterintuitive)
- F10: TP>hedge monotonically increases bust rate
- F11: Bust rate equity-invariant
- F12: Two failure modes for hedge/TP ratio
- F13: Zero margin calls at any tested config
- F14: Sub-12-pip hedge mathematically unprofitable
- F15: Optimal abort K=1 (minimize total loss)
- F15b: Bust rate sizing-factor-independent
- F16: Lot rounding 10% error at $1k equity
- F17: NAV closeout triggers 22pp higher margin utilization
- F18: PnL-optimal vs bust-rate-optimal abort maximally divergent
- F19: Configured max_levels ≠ effective max_levels for high sf
- F20: Total PnL degrades monotonically with sf — sf=1.3 is Pareto-optimal

## Pipeline Implications

See `09_synthesis/02_pipeline_implications.md` for full details.

**IslandPilot:**
- Add effective_max_levels feasibility constraint
- Safe (sf, ml) region: sf=1.5→ml≤5, sf=2.0→ml≤7, sf=2.5→ml≤6, sf=3.0→ml≤5
- Reject individuals with N=nan (avg_win ≤ 0)

**ARIA:**
- Abort objective must shift from bust-rate to total-loss minimization
- K=6 recommended for live trading (eliminates catastrophic busts, minimal PnL sacrifice)
- Add equity_per_leg_pct as primary danger feature (>3% = elevated, >5% = abort territory)

**Live trading:**
- Minimum equity: $5k for accurate position sizing at OANDA
- NAV-based margin gap: monitor closer than equity-based models predict
