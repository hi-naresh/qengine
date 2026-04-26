# 10 — Pipeline Design Journey

## Purpose

This directory documents the design journey from "raw grid-hedged Martingale loses money on EUR-USD" to the current IslandPilot architecture. Each pivot folder records *one* load-bearing decision: the context entering it, the problem it addressed, what was tried, what stuck, and how it set up the next pivot. Together the 9 pivots in numeric order form a chronological design diary.

This is distinct from three sibling artifacts:

- `notebooks/01-09/` — anatomy of the underlying Martingale strategy (pre-pipeline). The findings there motivate Pivot 01.
- `pipelines/_shared/IslandPilot/DESIGN_RATIONALE.md` — numeric-choice catalog organized by source file, with citations. *What* the choices are, not *why* this one was chosen over alternatives.
- `papers/drafts/dist/` — formal dissertation presentation of the polished result.

The journey notebook fills the gap between the anatomy work and the polished paper: the chronological "lab notebook" of how the design actually evolved, including the load-bearing dead ends.

## Reading order

Read pivots in numeric order. Each pivot's "Next move" section sets up the following pivot, so the chain reads as a single argument from "static HP cannot win" through "current IslandPilot is the result of these 9 decisions."

For a 60-second summary, read `JOURNEY.md` instead.

## Pivots

| # | Folder | Pivot |
|---|--------|-------|
| 01 | [`01_static_hp_limits`](01_static_hp_limits/) | 0/25 static (sf, ml) configs cross break-even — strategy needs adaptation |
| 02 | [`02_regime_detection_choice`](02_regime_detection_choice/) | HMM regime gate rejected (busts IID) — pivot to instantaneous clustering |
| 03 | [`03_hierarchical_clustering`](03_hierarchical_clustering/) | BIC selects two-level GMM hierarchy over flat clustering |
| 04 | [`04_per_regime_evolution`](04_per_regime_evolution/) | Per-leaf populations (islands) instead of single global GA |
| 05 | [`05_island_migration_topology`](05_island_migration_topology/) | Sibling-only ring migration — topology derived from clustering hierarchy |
| 06 | [`06_real_engine_fitness`](06_real_engine_fitness/) | Surrogate simulator misled the GA — switch to full qengine evaluation |
| 07 | [`07_gene_space_expansion`](07_gene_space_expansion/) | Iteration 2 expanded 3 → 7 tunable groups (added Entry Signal etc.) |
| 08 | [`08_adaptive_sizing_runtime`](08_adaptive_sizing_runtime/) | Runtime sizing layer scales by GMM confidence and drawdown state |
| 09 | [`09_iteration_corrections`](09_iteration_corrections/) | Two bugs in Iteration 1 (categorical resolver, margin-state reset) — fixed |

## Cross-reference

| Pivot | Anatomy finding(s) | IslandPilot source | Paper section |
|-------|--------------------|--------------------|---------------|
| 01 | F7b (0/25 viable) | (motivates pipeline existence) | §1, §7.2 |
| 02 | (none — pipeline-internal) | regime_inferencer.py (no HMM) | §3.2, §7 |
| 03 | (none) | regime_tree.py | §3.2, App. A |
| 04 | (none) | island_evolver.py | §3.4 |
| 05 | (none) | island_evolver.py (migration) | §3.4, §7 |
| 06 | F7b (real-cost negative-EV) | run_backtest path | §5, §7.4 |
| 07 | F15b (sf-invariant bust_rate) | __init__.py:_TUNABLE_GROUPS | §3.6, §7 |
| 08 | F7 (8.4× margin consumption) | adaptive_sizer.py | §3.5, §6.6 |
| 09 | (none — engineering corrections) | __init__.py:_apply_genome; strategies/_admin/Martingale/__init__.py | §4.2, §7.5 |

## What's NOT here

- **Anatomy of why busts happen** — see `notebooks/01-09/` (especially `09_synthesis/01_novel_findings.md`).
- **Implementation details of the pipeline** — see `pipelines/_shared/IslandPilot/` source and `DESIGN_RATIONALE.md`.
- **Formal paper presentation** — see `papers/drafts/dist/`.
- **Future work / planned features** — see `notebooks/09_synthesis/03_open_questions.md` and the dissertation §7.6.

## Faithfulness caveat for empirical scripts

For Pivots 02, 06, and 09 the original evidence lived in deleted phase-research notebooks (`notebooks/phase2/`, `notebooks/phase4/`). Reproductions in this directory are **illustrative**, not full replays. Each affected pivot's README states this explicitly. The conclusions stand on the original evidence; the scripts in this directory let the reader confirm the underlying property (e.g., IID busts produce a uniform p-value distribution) without re-running 100,000-cycle sweeps.

## How to run a pivot's script

All scripts are runnable standalone from the repo root:

```bash
cd /Users/naresh/Documents/Research/qengine
/Users/naresh/miniconda3/bin/python3 notebooks/10_pipeline_design/01_static_hp_limits/01_break_even_summary.py
```

Output goes to the pivot's `results/` subdirectory.
