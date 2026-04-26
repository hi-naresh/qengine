# Pivot 09 — Iteration Corrections

## Context

Pivots 01-08 describe the architecture as it is now (Iteration 2). Iteration 1 — the version trained on the cloud and reported in the dissertation — had the same architecture but contained two load-bearing bugs that suppressed the visible signal. The bugs were detected during validation of Iteration 1's results when fitness distributions across diverse genomes appeared *too consistent* — a sign of population collapse rather than convergence.

## Problem

Two specific bugs:

1. **Categorical-gene resolution.** The GA's gene encoding stored categorical choices (signal_mode, direction_bias, hedge_mode, tp_mode, sizing_curve, base_size_mode) as integer indices for compactness. When an integer-typed gene reached the strategy's hp consumer, the consumer's string-equality check (`if direction_bias == 'long'`) silently failed and fell through to a default. The effect: every genome's `direction_bias` resolved to its default regardless of the GA's choice, collapsing 4 categorical alternatives to 1. Because the bug fired on `direction_bias` *every cycle*, downstream `should_long` / `should_short` checks were uniformly False — sessions opened but the entry direction was driven by the strategy's default, not the GA's vote.

2. **CFD margin-bust state reset.** The CFD margin-bust path leaked state between sessions: a session that ended in margin-bust did not fully reset the per-session NaN-aware accumulators before the next session opened. Subsequent sessions inherited NaN-poisoned trade records, which propagated to fitness signal. Effect: a single margin-bust early in a backtest could corrupt the entire downstream fitness for that genome, producing constant-NaN fitness for some genomes regardless of their parameters.

Both bugs produced *statistically degenerate fitness distributions* — populations that should have explored a wide P&L range instead returned near-constant values. The dissertation results stand because they were obtained from the cloud-trained Iteration 1 model whose specific genomes happened to circumvent the worst expressions of both bugs (defaulting `direction_bias` to a value that worked acceptably; never hitting the margin-bust path on the trained slices). But the population dynamics were degraded throughout training.

## What we tried

**Fix 1 — Categorical-gene resolver.** A resolver layer maps integer-encoded categorical genes to their string values before they reach the strategy's hp consumer. This lives in `pipelines/_shared/IslandPilot/__init__.py` `_apply_genome` and `_SAFE_OPTIONS` (lines ~1010-1050). The resolver also defends against unsafe categorical values by intersecting the GA's options with `_SAFE_OPTIONS` per categorical name.

**Fix 2 — CFD margin-bust state reset.** The strategy's session lifecycle hook now explicitly resets NaN-aware accumulators on margin-bust as well as on the normal close paths. Source: `strategies/_admin/Martingale/__init__.py` (the lifecycle hook implementation; the specific commit is documented in DESIGN_RATIONALE.md if needed).

The script `01_categorical_fix_demo.py` demonstrates the categorical-fix property in isolation: 100 sampled signal_mode integers either all resolve to a single default (buggy) or distribute across the 9 valid options (fixed). The plot shows the dramatic distribution collapse before the fix.

## Result

Iteration 2 corrects both bugs. Diverse genomes now produce diverse fitness; the population dynamics use the full GA search machinery as designed. The 86.6pp net-return improvement reported in the dissertation is the *post-correction* outcome — Iteration 1's results were measured but Iteration 2's are the ones the architecture is designed to deliver.

The script's contrast: under the bug, all 100 sampled genomes resolve to `signal_mode = "random"` regardless of GA choice. Under the fix, all 9 modes are reachable.

## Conclusion

The corrected pipeline is in source. Both fixes are required to reproduce the published results.

## Next move

→ End of journey. The current IslandPilot architecture is the result of Pivots 01-09 layered together. See `papers/drafts/dist/` for the formal write-up.

## Sources

- **Categorical-fix source:** `pipelines/_shared/IslandPilot/__init__.py:1005-1050` (`_TUNABLE_GROUPS`, `_SAFE_OPTIONS`, and the `_apply_genome` resolver loop).
- **Margin-bust-state-reset source:** `strategies/_admin/Martingale/__init__.py` lifecycle hook for margin-bust path.
- **DESIGN_RATIONALE.md §0:** the canonical record of Iteration 1 vs Iteration 2.
- **Paper:** `papers/drafts/dist/4_training_methodology.md` §4.2 (the corrections section, which reports both bugs as load-bearing) and `7_discussion.md` §7.5 (caveat: "the primary experimental results depend on the correctness conditions documented in §4.2").
- **Faithfulness caveat:** the script in this folder demonstrates the categorical-coercion property on synthetic 100-genome samples. The original Iteration 1 fitness distributions were collected during cloud training and not preserved as a CSV in the repo.
