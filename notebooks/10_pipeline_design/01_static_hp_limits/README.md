# Pivot 01 — Static HP Limits

## Context

Anatomy research (`notebooks/01-09/`) characterized the underlying grid-hedged Martingale strategy on EUR-USD, 2006-2024, under real per-candle OANDA spread (mean 1.57 pips, p95 1.90 pips). The strategy was studied in two regimes:

- Canonical HP: sf=2.0, ml=6, hedge=20, tp=20
- Sweep across (sf ∈ {1.3, 1.5, 1.7, 2.0, 2.5, 3.0}, ml ∈ {3, 4, 5, 6, 8})

## Problem

Can *any* fixed parameter configuration produce positive expected value over the 18-year EUR-USD record? If yes, the pipeline question is "find that config and ship it"; if no, the strategy fundamentally requires *adaptation* and the pipeline must do something more interesting than parameter optimisation.

## What we tried

We evaluated all 25 (sf, ml) configurations against the break-even win rate. For each config the break-even rate is `p_min = |avg_bust| / (avg_win + |avg_bust|)`; the margin of safety is `actual_win_rate − p_min`. A config is *viable* iff margin of safety > 0.

The script `01_break_even_summary.py` reads the existing anatomy result `notebooks/01_finite_capital/results/break_even.csv` and renders the per-config margin-of-safety bar chart at `results/margin_of_safety_per_config.png`.

## Result

**0 of 25 configurations are viable.** Margins range from −0.073 (sf=1.3, ml=3) to −0.011 (sf=2.5, ml=6 — the least bad). The least-bad configuration still requires a 98.5% win rate it never achieves; the empirical rate is 97.4%.

For configs at sf ≤ 1.5 with ml ≥ 6, `p_min > 1.0` — the spread structure mathematically requires an impossible >100% win rate. These configs cannot be made viable by any directional improvement.

The marginal configs are statistically robust below break-even: the 95% margin of error on win-rate at n=3,771 sessions is ±0.40pp, and the smallest gap (sf=2.5 ml=6, −1.08pp) is **−4.3σ** below break-even. The directional conclusion is not a sampling artifact.

## Conclusion

Static HP cannot win on EUR-USD under real OANDA spread. The pipeline must adapt parameters to changing market conditions rather than optimise a single configuration. This conclusion is the load-bearing motivation for IslandPilot's existence.

## Next move

→ **Pivot 02 — Regime Detection Choice.** If parameters must adapt, *to what signal*? Two adaptation paradigms exist: sequential (HMM, regime persists across candles) and instantaneous (clustering, regime determined per-candle by feature vector). Pivot 02 documents why we tried HMM first and why it was rejected.

## Sources

- **Anatomy finding:** `notebooks/09_synthesis/01_novel_findings.md` Finding 7b (full break-even analysis).
- **Underlying data:** `notebooks/01_finite_capital/results/break_even.csv` (25-row CSV).
- **Statistical analysis:** Finding 7b "Sample-size caveat" subsection (σ counts per config).
- **Paper:** §1 (Introduction) and §7.2 (motivation for adaptive parameter management) draw on this conclusion. `papers/drafts/dist/7_discussion.md`.
- **Pipeline source:** none — this pivot motivates the pipeline's existence rather than landing in any specific module.
