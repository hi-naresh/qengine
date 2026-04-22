# 02 — Bust Anatomy

## Question
What actually causes a bust? At which level does forced close happen, what market condition preceded it, and are there structural patterns in the path to bust?

## Approach
Empirical track. Run backtester on EUR-USD ≤ 2024-12-31, extract all bust events, dissect each one. No prediction — pure characterization.

## Scripts
| Script | Question |
|--------|----------|
| `01_bust_extraction.py` | Run backtester, extract all bust events with full state snapshots |
| `02_level_cause_of_death.py` | Per bust: which level forced close, margin state, cost accumulated |
| `03_bust_path_patterns.py` | Common level-entry sequences before bust (characterization only) |

## Key Output
- Bust database: (bust_id, level_at_close, margin_at_close, cost_accumulated, hold_times_per_level, market_ATR_at_entry)
- Level-conditional cause-of-death distribution
- Whether bust paths are structurally uniform or show distinguishable sub-types

## Findings
<!-- Filled in as research progresses -->
