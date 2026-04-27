# 05 — Market Structure

## Question
How does choppy vs volatile market structure change holding time per level? In choppy markets, multiple levels open simultaneously — what is the margin consumption rate? When is the configured hedge distance "wrong" for the current volatility regime?

## Approach
Empirical track. Classify market structure at cycle entry, measure holding times and margin consumption rates by structure type.

## Scripts
| Script | Question |
|--------|----------|
| `01_holding_time_by_structure.py` | Choppy vs trending: how long does each level stay open? |
| `02_margin_consumption_rate.py` | Choppy market drain rate: multiple levels open simultaneously |
| `03_volatility_vs_hedge.py` | Wrong hedge distance in volatile regime: exact failure mechanics |

## Key Output
- Holding time distribution per level, split by market structure (ATR/choppiness at entry)
- Margin consumption rate as function of structure type
- "Hedge distance viability window": range of ATR where configured hedge is appropriate

## Findings
<!-- Filled in as research progresses -->
