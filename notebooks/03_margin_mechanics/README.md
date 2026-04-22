# 03 — Margin Mechanics

## Question
How does free margin evolve as levels are added? At what point does the broker force-close you before you reach theoretical max_levels? Where is the implicit ruin threshold?

## Approach
Math track. Derive the margin trajectory formula as a function of (sizing_factor, max_levels, starting_equity, spread). Validate against backtester margin snapshots from bust events.

## Scripts
| Script | Question |
|--------|----------|
| `01_margin_trajectory.py` | Free margin at each level as function of (sizing, equity, spread) |
| `02_implicit_forced_close.py` | When does broker close before theoretical max_levels is reached? |
| `03_margin_cushion_map.py` | 2D heatmap: (sizing_factor, max_levels) → level at which broker actually closes |

## Key Output
- Margin trajectory formula per level
- "Implicit max levels" — the real max you can reach given equity and broker margin rules
- Heatmap showing which HP configurations are safe vs. implicitly ruin-prone below theoretical max

## Findings
<!-- Filled in as research progresses -->
