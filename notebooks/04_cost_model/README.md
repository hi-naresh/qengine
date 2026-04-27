# 04 — Cost Model

## Question
How do spread and swap actually compound across levels? At what level does cumulative cost exceed the strategy's edge? What is the "effective grid distance" after accounting for spread shift?

## Approach
Empirical track. Extract real cost data from backtester at each level. Fit cost accumulation model.

## Scripts
| Script | Question |
|--------|----------|
| `01_spread_per_level.py` | Spread cost per level — grows with position size, not flat |
| `02_swap_drag.py` | Swap accumulation as holding time increases with level depth |
| `03_effective_grid_distance.py` | Configured hedge distance vs effective distance after spread shift |
| `04_cost_kills_edge.py` | At what level does cumulative cost exceed the strategy's edge? |

## Key Output
- Cost accumulation curve per level (spread + swap combined)
- "Break-even level" — the level beyond which the cost model guarantees a loss regardless of outcome
- Effective grid distance formula: configured_pips - spread_pips → real hedge trigger location

## Findings
<!-- Filled in as research progresses -->
