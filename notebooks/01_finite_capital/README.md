# 01 — Finite Capital

## Question
With infinite capital the strategy always wins. With finite capital, 1 bust erases N wins. What is N as a function of HPs, and at what equity level does the configuration become structurally ruin-prone?

## Approach
Math track. Derive formulas first, then validate against backtester output.

## Scripts
| Script | Question |
|--------|----------|
| `01_n_to_1_ratio.py` | For each HP config: how many wins does 1 bust erase? |
| `02_break_even_formula.py` | Minimum required win rate per config for positive expectancy |
| `03_capital_boundary.py` | At what equity does the config become structurally ruin-prone? |

## Key Output
- N-to-1 ratio surface across (sizing_factor, max_levels, hedge_distance)
- Break-even win rate formula (closed-form where possible)
- Capital boundary condition: minimum equity to sustain config safely

## Findings
<!-- Filled in as research progresses -->
