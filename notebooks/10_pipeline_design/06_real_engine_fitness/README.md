# Pivot 06 — Real-Engine Fitness

## Context

By Pivot 05 we had per-leaf populations evolving with sibling-only ring migration. The remaining choice was the fitness function: given a genome, what number does the GA optimise?

Two approaches were considered:

1. **Surrogate simulator.** A small (~120-line) cycle simulator that takes a genome's parameters and returns approximate session P&L. No spread shift, no swap, no margin enforcement, no per-candle backtest cost — just a closed-form approximation. Cheap (~ms per evaluation) so the GA can do thousands of fitness calls per generation.
2. **Full production engine.** Run a real `qengine` backtest under the genome's HP on a representative time slice. Real per-candle OANDA spread, real swap, real margin closeout, real strategy state machine. Expensive (~30 seconds per evaluation on 6 months) but identical to the live execution path.

## Problem

The surrogate is faster by ~25× but loses fidelity. The question was whether the speed/fidelity trade-off is favourable.

Phase 4 training revealed that genomes evolved on the surrogate produced extreme HPs that the production engine refused: 50-pip hedges with ATR-based TP modes that created sessions lasting weeks, reducing annual throughput to 2-3 cycles. The surrogate's missing cost terms left an exploitable gap — the GA found configurations that score well on a fitness function that pretends costs don't exist, then those configurations fall apart when costs return.

## What we tried

The script `01_simulator_vs_engine_gap.py` evaluates the canonical HP (sf=2.0, ml=6, hedge=20, tp=20) under both regimes:

- Surrogate (`pipeline_utils.simulator_fitness`): IID Bernoulli wins/busts at the empirical 97.4% rate, no spread cost.
- Engine (`pipeline_utils.engine_fitness`): full `qengine` backtest, real per-candle OANDA spread (mean 1.57 pips), 6-month slice.

The script produces the two numbers and confirms the sign discrepancy where present.

## Result

The surrogate reports positive total P&L (~ +5,000 in toy units). The engine reports negative total P&L (~ −1,000 USD on the 6-month slice). The strategy is structurally negative-EV under real costs (anatomy Finding 7b) but the surrogate hides this because it doesn't apply spread.

The Phase 4 finding (recorded in `papers/drafts/dist/7_discussion.md` §7.4): GA optimisation against the surrogate evolved unreproducible genomes — when the same genome was re-evaluated on the engine, the surrogate-reported improvements over baseline were not reproduced. The surrogate's optimum was an artifact.

## Conclusion

The pipeline uses **full `qengine` production engine for all fitness evaluations.** The 25× slowdown is paid; the surrogate is not used for any fitness call in production training. This is the load-bearing reason Iteration 1 cloud training took ~10 hours 33 minutes for ~12,600 evaluations rather than minutes.

A subtler related correction: real-engine evaluation also surfaces correctness bugs that the surrogate hides. Two such bugs (categorical-gene resolution and CFD margin-bust state reset) are documented in Pivot 09 — they would not have been caught by surrogate evaluation.

## Next move

→ **Pivot 07 — Gene-Space Expansion.** With fitness evaluation on the real engine settled, the next dimension is gene space breadth: which strategy parameters does the GA evolve? Iteration 1 covered 14 strategy params over 3 tunable groups; Iteration 2 expanded to 7 groups.

## Sources

- **Pipeline source:** `pipelines/_shared/IslandPilot/island_evolver.py` (calls `qengine.research.backtest.backtest()` for every fitness evaluation; no surrogate path).
- **Paper:** `papers/drafts/dist/7_discussion.md` §7.4 ("the discrepancy between simplified simulation and full-engine evaluation turned out to be substantial") and `5_experimental_setup.md` (training procedure detail).
- **Original notebooks (deleted):** `notebooks/phase4/` housed the surrogate-vs-engine comparison and the unreproducibility finding. Faithfulness caveat: this folder's script is illustrative, not a replay.
- **Engine entry point:** `qengine.research.backtest.backtest()` invoked via `notebooks/shared/utils.py:run_backtest()`.
