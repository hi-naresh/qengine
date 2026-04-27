# 06 — Abort Theory (Convergence Point)

## Question
Is aborting a cycle mid-way (before max_levels) good enough as the primary risk defense? Is the optimal abort level fixed, or a function of the current margin state? Does partial close (some tickets, not all) outperform full abort?

## Approach
Convergence of math and empirical tracks. Math derives the "point of no return" — the level beyond which expected recovery is negative. Empirical tests whether aborting at that level actually improves long-run EV in the backtester.

## Scripts
| Script | Question |
|--------|----------|
| `01_abort_vs_no_abort.py` | Empirical: does aborting at level K improve long-run EV? Sweep K=1..max_levels |
| `02_point_of_no_return.py` | Math: at what level is equity/margin too consumed to expect positive recovery? |
| `03_optimal_abort_level.py` | Fixed level vs margin-state-dependent: which produces better outcomes? |
| `04_partial_abort.py` | Partial close (close losing tickets, keep best) vs full abort comparison |

## Key Output
- Abort EV curve: EV(abort at level K) vs K — is there a clear optimum?
- Point-of-no-return formula from math track
- Whether abort should be a fixed rule or a dynamic margin-aware policy
- Whether partial close is a viable third option

## Findings
<!-- Filled in as research progresses -->
