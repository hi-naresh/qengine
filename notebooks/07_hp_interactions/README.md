# 07 — HP Interactions

## Question
How do HPs co-constrain each other? What is the safe region of (sizing_factor × max_levels × equity)? Is there a degenerate case when hedge_distance ≈ tp_distance? What are the pairwise sensitivity maps for pipeline gene bounds?

## Approach
Math-informed empirical. Use margin trajectory formula from 03 to define the feasible region, then validate with backtester sweeps.

## Scripts
| Script | Question |
|--------|----------|
| `01_sizing_x_levels.py` | Co-constraint surface: which (sizing_factor, max_levels) pairs are safe at given equity? |
| `02_hedge_x_tp.py` | Degenerate case: hedge == TP and near-degenerate behavior |
| `03_equity_sensitivity.py` | How sensitive is survivability to starting equity across configs? |
| `04_interaction_heatmaps.py` | Pairwise interaction heatmaps for all gene-bound-relevant params |

## Key Output
- Feasibility surface: safe (sizing_factor, max_levels) pairs as a function of equity
- Degenerate region map: hedge_distance / tp_distance ratio → strategy behavior
- Updated gene bounds for IslandPilot (mathematically justified, not empirically guessed)
- Equity sensitivity curve: minimum equity required per config class

## Findings
<!-- Filled in as research progresses -->
