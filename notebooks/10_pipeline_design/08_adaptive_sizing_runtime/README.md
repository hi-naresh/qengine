# Pivot 08 — Adaptive Sizing at Runtime

## Context

By Pivot 07 each leaf has its own genome covering 7 tunable groups, including `base_size_value` (the static base position size as % of equity). At runtime, the regime inferencer assigns the current candle to a leaf and applies that leaf's genome. The genome's `base_size_value` is constant within a leaf.

But two runtime states are *not* captured by leaf assignment alone:

1. **GMM posterior confidence.** The clustering produces a posterior probability per leaf. When confidence is high (one leaf has p ≈ 1.0), the regime call is reliable; when confidence is split across leaves (p ≈ 0.3 across three), the call is uncertain. A static genome cannot distinguish these cases.
2. **Current drawdown state.** Whether the strategy is currently in a drawdown is a feature of the *trajectory*, not the candle. A genome that's optimal on average may be too aggressive when drawdown has already accumulated.

Restricting adaptation to leaf-conditional genome selection ignores both signals.

## Problem

The pipeline needs a runtime layer that scales position size based on signals not available at training time. Constraints:

- Must not require re-training the genome.
- Must use signals computable per-candle without lookahead.
- Must be small enough that its scaling exponents can themselves be evolved as part of the genome.

## What we tried

The AdaptiveSizer applies three multiplicative factors to base position size:

```
position_size = base_size_value × f_conf × f_dd × f_base
```

- `f_conf = confidence ^ confidence_sensitivity` — convex when confidence_sensitivity > 1 (penalises low-confidence regimes more aggressively); linear at = 1; concave at < 1.
- `f_dd = max(0, 1 − recovery_aggression × drawdown)` — scales position down during drawdown periods. recovery_aggression of 0 disables drawdown scaling; values in (0, 1] increasingly suppress sizing during drawdowns.
- `f_base` — a static base multiplier (currently 1.0 in production).

Both `confidence_sensitivity` and `recovery_aggression` are themselves genes. They're evolved per-island like any other parameter.

Across the 63 trained islands, mean evolved values are:
- `confidence_sensitivity` ≈ 1.46 (convex)
- `recovery_aggression` ≈ 0.57 (moderate drawdown suppression)

The script `01_scaling_curve.py` plots both curves at representative values of their evolved exponents.

## Result

The AdaptiveSizer is the runtime layer described in `pipelines/_shared/IslandPilot/adaptive_sizer.py`. Its three factors compose multiplicatively on each cycle.

The convexity of the evolved `confidence_sensitivity` (mean 1.46 > 1) is non-trivial: it means the GA discovered that *low-confidence regime calls should be punished disproportionately*, not just linearly. When the regime label is uncertain, sizing falls fast. This is the discovered runtime contribution to the OOS peak-equity reduction (63.7% baseline → 10.3% pipeline; `papers/drafts/dist/6_results.md`).

## Conclusion

Adaptive runtime sizing is part of the pipeline, with two evolved exponents controlling its behaviour. The genome is no longer just a per-regime parameter set — it includes the runtime-layer's behaviour shape too.

## Next move

→ **Pivot 09 — Iteration Corrections.** With the architecture complete (regime tree, island evolver with sibling migration, real-engine fitness, 7-group gene space, AdaptiveSizer), Iteration 1 was trained. Two bugs in that pipeline produced statistically degenerate fitness signals that suppressed the apparent improvement. Pivot 09 documents both.

## Sources

- **Pipeline source:** `pipelines/_shared/IslandPilot/adaptive_sizer.py` (the three-factor scaling); genome fields `confidence_sensitivity` and `recovery_aggression` are defined here.
- **Mean evolved values:** `papers/drafts/dist/7_discussion.md` ("`confidence_sensitivity` exponent (mean ≈ 1.46 across islands)" and "`recovery_aggression` parameter (mean ≈ 0.57)").
- **Paper:** `3_system_architecture.md` §3.5 (AdaptiveSizer detail) and `6_results.md` §6.6 ("Mechanism 2: Position-size compression").
- **Anatomy connection:** the runtime layer is consistent with anatomy Finding 7 (margin consumption rate is 8.4× higher in busts) — scaling down at high confidence-uncertainty / drawdown is exactly the "early-warning down-scaling" the anatomy implies.
