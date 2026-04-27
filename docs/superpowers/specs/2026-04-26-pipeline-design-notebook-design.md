# Pipeline-Design Notebook (`notebooks/10_pipeline_design/`) — Design Spec

**Date:** 2026-04-26
**Status:** draft for user review

## Purpose

Document the **design journey** from "raw grid-hedged Martingale loses money on EUR-USD" to the current IslandPilot architecture. This is a chronological design diary capturing the pivots — what was tried, what failed, why each architectural choice replaced its predecessor.

This is a different artifact from three existing artifacts and explicitly does not duplicate them:

- `notebooks/01-09/` — strategy *anatomy* (why the underlying Martingale strategy fails). Pre-pipeline.
- `pipelines/_shared/IslandPilot/DESIGN_RATIONALE.md` — *what* the numeric choices are, with citations. Source-code-ordered, not chronological.
- `papers/drafts/dist/` — formal paper presentation of the polished result.

The journey notebook fills the gap between the anatomy work and the polished paper: the chronological "lab notebook" of how the design actually evolved, including the load-bearing dead ends.

## Scope

**In scope:** Pipeline-era pivots only. Starts from "raw Martingale was shown structurally unprofitable in `notebooks/01-09`", ends with current IslandPilot Iteration 2.

**Out of scope:** pre-pipeline anatomy research (already in `notebooks/01-09/`); formal paper-style narrative (already in `papers/drafts/dist/`); detailed source-code documentation of IslandPilot internals (already in `DESIGN_RATIONALE.md` and module docstrings); future work / ideas not yet implemented.

## Location

`notebooks/10_pipeline_design/` — continues the existing `notebooks/01-09/` numbering. Pipeline work logically follows the anatomy work both temporally and intellectually.

## Directory layout

```
notebooks/10_pipeline_design/
  README.md                              master index + cross-reference table
  JOURNEY.md                             one-screen decision-tree summary
  shared/
    utils.py                             pipeline-research helpers
  01_static_hp_limits/
    README.md                            pivot narrative (template below)
    01_break_even_summary.py             empirical script
    results/
  02_regime_detection_choice/
    README.md
    01_iid_bust_test.py
    results/
  03_hierarchical_clustering/
    README.md
    01_bic_over_k.py
    results/
  04_per_regime_evolution/
    README.md
    (architectural; no scripts)
  05_island_migration_topology/
    README.md
    01_topology_diagram.py               graphviz / matplotlib diagram of sibling-only ring
    results/
  06_real_engine_fitness/
    README.md
    01_simulator_vs_engine_gap.py        empirical paired comparison
    results/
  07_gene_space_expansion/
    README.md
    01_gene_count_per_iteration.py
    results/
  08_adaptive_sizing_runtime/
    README.md
    01_scaling_curve.py                  plot of confidence × drawdown × base scaling
    results/
  09_iteration_corrections/
    README.md
    01_categorical_fix_demo.py           pre/post degeneracy demo
    results/
```

Mirrors `notebooks/01-09/`: each numbered folder is a self-contained pivot with a README, optional scripts, and a `results/` subdirectory for script output. `shared/utils.py` holds helpers used by multiple pivots.

## Per-pivot README template

Every per-pivot README follows the same 7-section structure:

1. **Context** — state of the design entering this pivot. What was settled, what was open?
2. **Problem** — what was wrong / what we wanted to improve / what observation forced reconsideration.
3. **What we tried** — the hypothesis that was tested, with experiment description (script reference if applicable) or reasoning chain (if architectural).
4. **Result** — what happened. Include a concrete number, plot reference, or source code line where the conclusion landed.
5. **Conclusion** — what stuck (became part of the final pipeline) and what was rejected.
6. **Next move** — how this pivot set up the following one.
7. **Sources** — cross-references to: (a) the anatomy finding(s) it builds on (e.g., `notebooks/09_synthesis/01_novel_findings.md` F7b); (b) IslandPilot source files where the conclusion landed; (c) paper section that cites it; (d) git commits, if specific commits are load-bearing; (e) MEMORY.md notes if the pivot is summarized there.

## The 9 pivots

| # | Folder | Pivot | Type |
|---|--------|-------|------|
| 01 | `01_static_hp_limits` | Anatomy showed 0/25 static configs cross break-even (real OANDA spread). Conclusion: a single fixed HP cannot win on EUR-USD; the strategy needs adaptation. | Empirical (re-runs anatomy F7b with summary plot) |
| 02 | `02_regime_detection_choice` | First adaptation attempt: HMM regime gating (Phase 2). Permutation test rejected at p=0.405 — busts are IID, not regime-clustered. Pivoted to instantaneous clustering instead of sequential HMM. | Empirical (synthetic IID test + reference to phase2 result) |
| 03 | `03_hierarchical_clustering` | Within instantaneous clustering: flat k-means vs hierarchical GMM. BIC-selected two-level GMM (macro + sub) chosen for granularity-vs-population trade-off. | Architectural-leaning (BIC over k script + paper §3.2 cite) |
| 04 | `04_per_regime_evolution` | Single GA over all regimes converged to a "middle" config that suited none well. Pivoted to per-regime populations (islands), each evolving independently for its own regime. | Architectural (narrative + ref to `island_evolver.py`) |
| 05 | `05_island_migration_topology` | If islands evolve independently, when do they share genomes? Random / fully-connected migration ungrounded; chose sibling-only ring migration (islands sharing the same macro-cluster). Topology derived from the clustering hierarchy itself. | Architectural (narrative + topology diagram) |
| 06 | `06_real_engine_fitness` | Initial fitness evaluations used a 120-line simulator (no spread, no margin). Genomes evolved on it produced extreme HPs that the production engine refused. Pivoted to full `qengine` for fitness despite ~25× slowdown. | Empirical (paired backtest: same genome on simulator vs full engine) |
| 07 | `07_gene_space_expansion` | Iteration 1 evolved 14 strategy params over 3 tunable groups. Iteration 2 added 4 more groups (Entry Signal, Filters, Risk Management, Position Management). Per-regime signal selection became the load-bearing source of OOS PF improvement. | Architectural (cite `_TUNABLE_GROUPS`; gene-count script) |
| 08 | `08_adaptive_sizing_runtime` | Even with per-regime genome, position size shouldn't be static within a regime. AdaptiveSizer applies confidence × drawdown × base scaling at runtime. The `confidence_sensitivity` exponent is itself an evolved gene. | Architectural (cite `adaptive_sizer.py` + scaling curve plot) |
| 09 | `09_iteration_corrections` | Two load-bearing bugs in Iteration 1 produced statistically degenerate fitness signals: (a) categorical-gene encoding silently coerced direction-bias to False; (b) CFD margin-bust path leaked state between sessions producing NaN trade records. Iteration 2 fixed both. The 86.6pp net-return improvement is post-correction. | Empirical (reproduce one fitness distribution before/after the categorical fix) |

## Empirical-script faithfulness caveat

For Pivots 02, 06, and 09 the original evidence lived in deleted phase notebooks. Reproductions in this directory are **illustrative**, not full replays of the original sweeps:

- **Pivot 02:** small synthetic test demonstrating that a known-IID process produces a permutation-test p-value distribution similar to what was observed; not a 100,000-cycle replay.
- **Pivot 06:** paired evaluation of *one* representative genome on simulator vs full engine to demonstrate the gap qualitatively; not a full GA run.
- **Pivot 09:** reproduction of the categorical-gene degeneracy on a small sweep to show the fitness-distribution narrowing pre-fix and the diversity post-fix.

The README for each affected pivot will say so explicitly, link to the original phase commits in git history if discoverable, and note that the conclusion stood on the original evidence (the script in this notebook is for the reader to confirm the property, not to re-derive the conclusion).

## Master `README.md` (top-level index)

1. **Purpose** (one paragraph)
2. **Reading order** — pivots in numeric order; each "Next move" sets up the following.
3. **Pivot table** — the 9-row table above, each row hyperlinked.
4. **Cross-reference table** — for each pivot: anatomy finding it builds on, IslandPilot source it landed in, paper section that cites it.
5. **What's NOT here** — explicit out-of-scope pointers (anatomy → `01-09/`, implementation → `pipelines/_shared/IslandPilot/`, paper → `papers/drafts/dist/`).

## `JOURNEY.md` (one-screen decision tree)

Compact decision-tree narrative readable in 60 seconds, each line linking to its pivot folder. Form:

```
Q: Can a static HP win? → No (Pivot 01) → need adaptation
   Q: Sequential or instantaneous? → HMM IID-rejected (Pivot 02) → instantaneous
      Q: Flat or hierarchical clustering? → BIC favours 2-level GMM (Pivot 03)
         Q: One GA or per-regime? → per-regime (Pivot 04)
            Q: Migration topology? → sibling-only ring (Pivot 05)
               Q: Simulator or real engine fitness? → real engine (Pivot 06)
                  Q: How wide a gene space? → 7 tunable groups (Pivot 07)
                     Q: Static genome or runtime scaling too? → both (Pivot 08)
                        Q: Why didn't Iteration 1 work? → 2 bugs (Pivot 09)
[end state: current IslandPilot]
```

## `shared/utils.py` contents

Pipeline-research helpers analogous to `notebooks/shared/utils.py`:

- `load_pipeline_artifacts()` — load trained `island_genomes.json`, `regime_tree.pkl`, `feature_selector.json` from `pipelines/_shared/IslandPilot/models/`. Returns a small dict.
- `simulator_fitness(genome, candles)` — minimal ~30-line cycle simulator without spread/margin (the surrogate for Pivot 06 contrast).
- `engine_fitness(genome, candles)` — thin wrapper around `notebooks/shared/utils.py:run_backtest()` so engine-fitness has one entry point.
- `summarize_genome(genome)` — pretty-prints a genome with field grouping (General / Grid / TP / Filter / etc.) for human inspection.

Domain-specific helpers stay inside the pivot folder that uses them.

## Script naming convention

Within each pivot folder, scripts are numbered by execution order: `01_<purpose>.py`, `02_<purpose>.py`. Each has a one-line module docstring stating what the script demonstrates. Output files go in the folder's `results/` subdir.

## Success criteria

1. The 9 pivots cover the load-bearing decisions that produced current IslandPilot. A reader who has not seen the source can answer, after reading this directory, *why* each major architectural element exists.
2. Each pivot's README maps cleanly to: an anatomy finding it builds on (where applicable), a current IslandPilot source file (where the conclusion landed), and (where applicable) a paper section.
3. Empirical scripts in each folder execute under `/Users/naresh/miniconda3/bin/python3 <script>` from the repo root and produce output in `results/` without errors.
4. `JOURNEY.md` is readable in under 60 seconds and is internally consistent with the per-pivot READMEs.
5. The directory does not duplicate `DESIGN_RATIONALE.md`'s numeric-choice catalog or the paper's polished narrative.

## Out of scope (explicit non-goals)

- Re-deriving the anatomy findings (they are already established in `notebooks/01-09/`).
- Re-running the original phase1-5 sweeps (the deleted notebooks). Empirical scripts are *illustrative* only — see the faithfulness caveat above.
- Documenting future work or planned features (this is a *what happened* artifact, not a roadmap).
- Source-code line-by-line documentation of `pipelines/_shared/IslandPilot/*.py` (their docstrings already do that).
- Replacing the formal paper sections — this notebook complements them.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Pivot count grows unbounded (every minor course correction becomes a folder) | Cap at the 9 listed; further work goes into "minor decisions" sub-section of an existing pivot's README, not a new folder. |
| Reproductions for Pivots 02/06/09 oversell themselves as full replays | Faithfulness caveat (see section above) is restated in each affected pivot README. |
| Cross-references rot as anatomy/source/paper change | Each cross-reference uses stable identifiers (Finding number, file path, paper section number) rather than line numbers. |
| Document overlaps `DESIGN_RATIONALE.md` (numeric catalog) | Different organizing principle: this directory is *chronological* and *narrative*; `DESIGN_RATIONALE.md` is *source-code-ordered* and *citation-keyed*. README explicitly states the distinction. |
