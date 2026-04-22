# Martingale Anatomy Research — Design Spec

**Date:** 2026-04-22  
**Approach:** Option C — Dual-track (math spine + empirical anatomy)  
**Data boundary:** EUR-USD ≤ 2024-12-31 only. No 2025 data in any script.  
**Engine:** Real qengine backtester only. No toy simulators.

---

## Core Question

> Given finite capital, what are the exact mechanics that determine whether the grid-hedged Martingale is survivable — and is mid-cycle abort sufficient as the primary defense?

With infinite capital the strategy always wins (mathematical certainty). With finite capital, 1 bust erases N wins. The research maps exactly how that trade-off works under real broker constraints and real cost models, targeting findings that no academic paper has published.

---

## Firewall — Known Facts (never re-derive)

See `notebooks/facts.md`. Anything in that file is established literature. If an experiment would only confirm a fact already listed, it is skipped.

Known facts include:
- Gambler's ruin: infinite capital always converges
- Ruin probability with finite capital under IID Bernoulli = 1 as N→∞
- Kelly criterion for optimal sizing under known edge
- That spread/cost reduces expectancy
- That geometric sizing grows exposure exponentially with levels
- That busts are rare but wipe multiple wins (abstract N-to-1 ratio)

---

## Research Targets (novel territory)

1. The finite-capital boundary as a unified formula under real broker margin rules
2. How market structure (choppy vs volatile) changes holding time per level, and how holding time interacts with swap drag and margin consumption rate
3. Whether the N-to-1 ratio is stable across HP configurations or varies in exploitable ways
4. Whether mid-cycle abort is optimal, suboptimal, or regime-dependent
5. The "effective grid distance" after spread and how this shifts the break-even level count
6. When does the broker force-close you before theoretical max_levels (implicit ruin)

---

## Directory Structure

```
notebooks/
  facts.md              — known academic results (firewall)
  observed.md           — anomalies logged as found
  anomalies.md          — unexplained behaviors flagged for follow-up

  01_finite_capital/    — N-to-1 ratio, break-even formula, capital boundary
  02_bust_anatomy/      — dissect real bust paths from backtester
  03_margin_mechanics/  — margin consumption trajectory per level
  04_cost_model/        — spread + swap drag, effective grid distance
  05_market_structure/  — choppy vs volatile × margin consumption rate
  06_abort_theory/      — when does aborting help vs hurt (convergence point)
  07_hp_interactions/   — sizing × levels × equity co-constraint surface
  08_broker_mechanics/  — lot rounding, NAV closeout, OANDA vs generalized
  09_synthesis/         — novel findings, pipeline implications, open questions
```

---

## Dual-Track Flow

```
MATH TRACK                          EMPIRICAL TRACK
─────────────────────               ─────────────────────────────
01_finite_capital/                  02_bust_anatomy/
  Derive N-to-1 formula               Extract real bust events
  Break-even win rate                 Level-by-level cause of death
  Capital boundary condition          Common path patterns
         │                                    │
         ▼                                    ▼
03_margin_mechanics/                04_cost_model/
  Margin trajectory formula           Spread compounding per level
  Implicit forced-close threshold     Swap drag by holding time
  Margin cushion map                  Effective grid distance
         │                                    │
         └──────────────┬─────────────────────┘
                        ▼
              05_market_structure/
                Choppy vs volatile × holding time
                Margin consumption rate characterization
                Wrong hedge distance failure mechanics
                        │
                        ▼
              06_abort_theory/  ← CONVERGENCE POINT
                Math says: point of no return at level K
                Data says: does aborting at K improve EV?
                Together: optimal abort policy
                        │
                        ▼
              07_hp_interactions/
                Co-constraint surface (math-informed bounds)
                Pairwise sensitivity maps
                        │
                        ▼
              08_broker_mechanics/
                Generalized model → OANDA instantiation
                        │
                        ▼
              09_synthesis/
                Novel findings + pipeline implications
```

---

## Living Documents

- **`observed.md`** — any script result that contradicts the math-track prediction gets logged here immediately
- **`anomalies.md`** — results with no explanation yet; raw material for novel findings
- Both are amended as research progresses, not written once

---

## Script Inventory

### 01_finite_capital/
| Script | Question |
|--------|----------|
| `01_n_to_1_ratio.py` | For each HP config: how many wins does 1 bust erase? |
| `02_break_even_formula.py` | Derive minimum required win rate per config |
| `03_capital_boundary.py` | At what equity does the config become structurally ruin-prone? |

### 02_bust_anatomy/
| Script | Question |
|--------|----------|
| `01_bust_extraction.py` | Run backtester, extract all bust events ≤ 2024 |
| `02_level_cause_of_death.py` | Per bust: which level forced close, what triggered it |
| `03_bust_path_patterns.py` | Common sequences before bust (characterization, not prediction) |

### 03_margin_mechanics/
| Script | Question |
|--------|----------|
| `01_margin_trajectory.py` | Free margin at each level as function of (sizing, equity, spread) |
| `02_implicit_forced_close.py` | When does broker close before theoretical max_levels? |
| `03_margin_cushion_map.py` | 2D map: (sizing_factor, max_levels) → actual broker margin hit |

### 04_cost_model/
| Script | Question |
|--------|----------|
| `01_spread_per_level.py` | How spread cost compounds across levels (grows with position size) |
| `02_swap_drag.py` | Swap accumulates as holding time increases with level depth |
| `03_effective_grid_distance.py` | Configured hedge distance vs effective distance after spread shift |
| `04_cost_kills_edge.py` | At what level does cumulative cost exceed the strategy's edge? |

### 05_market_structure/
| Script | Question |
|--------|----------|
| `01_holding_time_by_structure.py` | Choppy vs trending: how long does each level stay open? |
| `02_margin_consumption_rate.py` | Multiple levels open simultaneously in choppy market: drain rate |
| `03_volatility_vs_hedge.py` | Wrong hedge distance in volatile regime: exact failure mechanics |

### 06_abort_theory/
| Script | Question |
|--------|----------|
| `01_abort_vs_no_abort.py` | Empirical: does aborting at level K improve long-run EV? |
| `02_point_of_no_return.py` | Math: at what level is equity too consumed to recover? |
| `03_optimal_abort_level.py` | Is the optimal abort level fixed or a function of margin state? |
| `04_partial_abort.py` | Can closing some tickets (not all) outperform full abort? |

### 07_hp_interactions/
| Script | Question |
|--------|----------|
| `01_sizing_x_levels.py` | Co-constraint surface: which (sizing_factor, max_levels) pairs are safe? |
| `02_hedge_x_tp.py` | Degenerate case: hedge == TP and near-degenerate behavior |
| `03_equity_sensitivity.py` | How sensitive is survivability to starting equity? |
| `04_interaction_heatmaps.py` | Full pairwise interaction maps for pipeline gene bounds |

### 08_broker_mechanics/
| Script | Question |
|--------|----------|
| `01_lot_rounding.py` | OANDA integer rounding: does systematic under/over-hedge matter? |
| `02_margin_closeout_model.py` | NAV-based vs equity-based closeout: exact difference in practice |
| `03_oanda_vs_generalized.py` | Generalized broker model instantiated with OANDA parameters |

### 09_synthesis/
| File | Purpose |
|------|---------|
| `01_novel_findings.md` | What we found that no paper says |
| `02_pipeline_implications.md` | Direct changes to IslandPilot gene bounds + ARIA danger thresholds |
| `03_open_questions.md` | What this research opens up for future work |

---

## Success Criteria

1. At least 3 findings that contradict or extend what's in `facts.md`
2. `06_abort_theory/` produces a concrete answer: optimal abort policy (fixed level, margin-state-dependent, or partial close)
3. `07_hp_interactions/` produces updated gene bounds for IslandPilot that are mathematically justified
4. `09_synthesis/` is citable as a standalone research contribution
