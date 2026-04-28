# IslandPilot — Preflight & Audit Harness

**Date:** 2026-04-26
**Author:** Claude (brainstormed with user, sneha@botwot.io)
**Goal:** Before committing to a ~10+ hour cloud training run (Iteration 1 reference: 10h 33m on `c2-standard-60`, per CLOUD_TRAINING.md:31), prove the IslandPilot pipeline is exercising every layer it claims to. After training, produce a structured log of what fired and what didn't.

> **Scope guard:** This spec covers verification only. Strategy-logic improvements (regime taxonomy, transition matrix, per-regime tactics, abort probabilities) are explicitly out of scope and tracked for a follow-on spec. **IslandPilot V1 is not touched.** All changes land inside `pipelines/_shared/IslandPilot/`.

---

## 1. Problem Statement

The current IslandPilot preflight (`preflight.py`) is a 4-check smoke test on synthetic GBM data. It runs in ~2 min and confirms the code does not crash. **It also has a pre-existing bug**: every import path inside it points at V1 (`pipelines._shared.IslandPilot.*`, verified at lines 11, 35, 81, 101–103, 158), not V2 — the file was duplicated when V2 was forked and the imports were never updated. So even what it checks today is checking the wrong codebase.

The current preflight does **not** confirm:

1. Every tunable hyperparameter group that the design intends to evolve is actually being mutated, **and** every group that is intentionally excluded (e.g. the Filters group is in `_SKIP_PARAMS` because >99% of evolved filter combinations block all entries — see comment at `island_evolver.py:184–187`) is documented as such in the audit log so the exclusion is visible rather than silent.
2. Every regime leaf gets HP variation across the population.
3. Strategy actually reads the evolved HPs at decision time.
4. Per-regime online-learning state (`_regime_wins/losses/cycles/busts`, `_recent_pnls`) updates after each cycle.
5. Online gating, drift detection, unknown-regime gate, proven-fitness gate, abort-volatility, and session-halt all fire when their conditions are met.
6. Migration between sibling islands actually moves genes (acceptance ratio > 0).
7. Every island produces a deployable best-genome artifact.
8. Validate-model OOS path round-trips cleanly.

The cost of missing any of these before a ~10-hour cloud run is the cloud spend plus the wall-clock. The cost of building a stronger preflight is ~5 minutes per run at preflight-time and ~1 day to write.

A second gap: even when training completes successfully, there is no post-hoc record of which gates fired, which regimes received which genomes, which migrations were accepted, or which feasibility corrections were applied. This makes diagnosing "training ran but the model is bad" impossible without re-running training with debug prints.

---

## 2. Goals and Non-Goals

### Goals

- **G1.** Pre-training preflight that runs 34 layer checks against the pipeline on bare-minimum real data, in **under 5 minutes** on an M-series laptop with all cores.
- **G2.** Post-training audit that, given a completed `models/` directory, produces a structured report of what fired, what did not, and what was applied per regime — answering "did training do what it should have done?" without re-running anything.
- **G3.** Both surfaces share the same check predicates so they cannot drift apart.
- **G4.** Adding a new check requires writing one decorated function and one meta-test. No registry edits, no orchestrator edits.
- **G5.** Cloud training has near-zero overhead from the new manifest writer (target: < 1% wall-time, < 10 MB gzipped manifest on the reference 10h 33m EUR-USD 5m run with 12,600 evaluations).
- **G6.** Training code remains runnable without the verification harness — `manifest.record(...)` calls degrade to no-ops if the manifest is not opened.

### Non-Goals

- **N1.** Strategy logic improvements (regime taxonomy, transitions, per-regime tactics, abort probabilities, per-regime entry/exit timers, bucket profit-taking). These belong to a follow-on spec.
- **N2.** Changes to fitness function, regime feature pool, or evolutionary operators.
- **N3.** Touching IslandPilot V1.
- **N4.** A web UI for the report. Terminal pretty-print + JSON sidecar only.
- **N5.** CI integration. Local-only invocation; CI is a future concern.
- **N6.** Strict backwards compatibility with old `models/` artifacts that pre-date the manifest. Audit *gracefully degrades* on these (skips manifest-source checks, returns verdict `degraded`; see §9.5), but the spec does not promise feature parity with audits run on a manifest-bearing artifact. Re-run training to get full audit fidelity.

---

## 3. Architecture

### 3.1 Files

```
pipelines/_shared/IslandPilot/
├── manifest.py              [NEW]      ~80 LOC   global event recorder
├── preflight_checks.py      [NEW]      ~1000 LOC ~34 @check functions
├── preflight.py             [REWRITE]  ~250 LOC  smoke (30s) + comprehensive (≤4.5 min)
├── audit.py                 [NEW]      ~150 LOC  post-training auditor
├── train.py                 [PATCH]    +17 lines manifest.record() + worker-result unpack + output_dir kwarg
├── __init__.py              [PATCH]    +20 lines manifest.record() at event sites
├── island_evolver.py        [PATCH]    +5 lines  manifest.record() at migration accept/reject
├── regime_inferencer.py     [PATCH]    +2 lines  manifest.record('transition', ...) only
```
tests/                                              [top-level repo dir, existing convention]
└── test_islandpilotv2_preflight_checks.py  [NEW]  ~150 LOC  meta-tests for each check
```

Outputs (new files added by this spec marked **NEW**; existing artifacts the pipeline already writes are listed for completeness):

```
pipelines/_shared/IslandPilot/models/         [cloud training writes here by default]
├── regime_tree.pkl                             [pre-existing]
├── island_evolver.json                         [pre-existing]
├── leaf_date_ranges.json                       [pre-existing]
├── activation_manifest.jsonl.gz                [NEW: training output]
├── training_config.json                        [NEW: training output, snapshot of what governed run]
├── audit_report.json                           [NEW: audit writes here next to the artifacts it audits]

$TMPDIR/qengine_preflight_<random>/             [preflight writes everything here — never touches models/]
├── regime_tree.pkl                             [isolated copy from preflight's tiny train() invocation]
├── island_evolver.json                         [isolated]
├── leaf_date_ranges.json                       [isolated]
├── activation_manifest.jsonl.gz                [isolated]
├── training_config.json                        [isolated]
├── preflight_report.json                       [NEW: preflight output]
├── audit_report.json                           [NEW: written if audit.py is invoked on this tmpdir]
```

Preflight uses `tempfile.mkdtemp(prefix="qengine_preflight_")`. The tmpdir path is printed at the end of preflight so the user can inspect reports or re-run audit against it. The tmpdir is **not** auto-cleaned (so reports survive); manual cleanup via OS tmp expiry or explicit `rm -rf`.

### 3.2 Three execution paths, one shared registry

```
Path 1: Preflight (pre-training)              Path 2: Training (cloud)                   Path 3: Audit (post-training)
─────────────────────────────────             ─────────────────────────                  ─────────────────────────────
$ python preflight.py                         $ python train.py --workers 60             $ python audit.py models/

  ├─ Phase 1: Smoke (~5s, fail-fast)             ├─ manifest.open(models/...)               ├─ load activation_manifest.jsonl.gz
  │   7 unit-source @check predicates:          ├─ regime tree fit                          ├─ load island_evolver.json
  │   R06,E01,E02,E07,E08,A04,V03               │   → manifest.record('regime_fit', ...)    ├─ load regime_tree.pkl
  │                                             ├─ evolution loop                           │
  ├─ Phase 2: Comprehensive (~4.5 min)          │   → manifest.record('apply_genome',…)     ├─ run all @check(source ∈
  │   30d real EUR-USD 5m, max workers          │   → manifest.record('migration', …)       │       {artifact, manifest})
  │   2 gen × 4 pop × 3 leaves                  │   → manifest.record('gate_fire', …)       │
  │   inject probes, capture events live        │   → manifest.record('transition', …)      └─ write audit_report.json
  │   force-trigger gates G01–G06               └─ manifest.close() + gzip                       (+ pretty terminal output)
  │
  └─ write preflight_report.json
```

The `@check` decorator stamps each check with `source ∈ {unit, runtime, artifact, manifest}`:
- `unit` — call function directly with controlled inputs (preflight only)
- `runtime` — assert against events captured by live in-memory tap (preflight only)
- `artifact` — read final pkl/json files (audit only)
- `manifest` — read events from gzipped JSONL (audit only)

Most checks register two sources, e.g. `source=["runtime", "manifest"]`. At runtime the check inspects `ctx.available_sources` and runs against whichever source is present (preflight contributes `runtime`+`unit`+`artifact`; audit contributes `manifest`+`artifact`). The predicate body is identical; only the evidence stream differs.

### 3.3 Coupling via `manifest.py`

`manifest.py` is the single coupling point between training code and the verification harness. Training calls `manifest.record(event_type, **data)` blindly. The recorder is a global singleton with three modes:

- **Closed** (default) — `record()` is a no-op. Training without preflight or audit incurs zero overhead.
- **File-open** — `record()` writes JSONL to disk. Used by cloud training.
- **File-open + tap** — `record()` writes JSONL to disk **and** notifies an in-memory subscriber. Used by preflight to capture events live.

This makes `manifest.record(...)` calls in training code safe to leave in always: in production they are essentially free; in preflight and cloud they capture evidence.

---

## 4. Components

### 4.1 `manifest.py`

Public API:

```python
# Parent-process API
manifest.open(path: Path) -> None
manifest.record(event_type: str, **data) -> None
manifest.close() -> None
manifest.tap(subscriber: Callable[[dict], None]) -> None     # preflight-only

# Worker-process API (fork children)
manifest.start_worker_buffer() -> None                       # call at top of worker fn
manifest.drain_worker_buffer() -> list[dict]                 # call at end of worker fn
manifest.merge_worker_events(events: list[dict]) -> None     # parent re-emits each event
```

Implementation notes:
- Module-level singleton. Re-opening overwrites prior path.
- `record()` is no-op if not opened in parent **and** no worker buffer active. No exception, no warning.
- In parent process: `record()` writes JSONL to disk and fires the tap (if subscribed).
- In worker process (after `start_worker_buffer()`): `record()` appends to a thread-local list. **No disk writes from workers.** This avoids file-handle interleaving and the cost of cross-process file locking.
- Events are flushed to disk every N records (N=100) and on close.
- `close()` gzips the file in place, leaves `.jsonl.gz` artifact.
- On parent process exit (atexit), automatically calls `close()` if open.
- Subscriber callback is fired synchronously inside `record()` after disk write.
- Records are JSON-serializable dicts with mandatory keys: `ts` (ISO8601), `event` (str). Caller passes additional keys via `**data`.

#### Multiprocessing aggregation

`train.py` evaluates fitness via `multiprocessing.Pool` with `'fork'` context (train.py:809). The `_run_backtest_fitness` worker function is invoked in child processes which inherit a fresh copy of the manifest singleton via copy-on-write but cannot write to the parent's open file handle without race conditions.

The aggregation pattern:

```python
# Worker side (in _run_backtest_fitness)
def _run_backtest_fitness(genes, *args) -> tuple[float, list[dict]]:
    manifest.start_worker_buffer()
    fitness = ... # existing backtest logic; manifest.record() inside this
                  # appends to the worker buffer
    return fitness, manifest.drain_worker_buffer()

# Parent side (in train.py main loop)
results = pool.starmap(_run_backtest_fitness, tasks)
for (lid, idx), (fitness, worker_events) in zip(task_keys, results):
    evolver.populations[lid].individuals[idx].fitness = fitness
    manifest.merge_worker_events(worker_events)  # re-emits each event in parent
```

The events the worker emits (`apply_genome`, `gate_fire`, `cycle_complete`, `transition`) are exactly the bulk-volume events. By batching them into the per-task return value, IPC cost stays at one transfer per backtest (~10 KB) rather than per `record()` call.

Sequential mode (`n_workers == 1`) skips the worker-buffer dance: `record()` writes to the parent file directly, since the "worker" is the parent.

#### Robustness rules

The recorder must never crash training. Specifically:

1. **Re-open without close** — `manifest.open()` called twice without an intervening `close()` flushes the current file, gzips it, then opens the new path. Emits a `_session_restart` header into the new file pointing at the prior path. (Should not happen in practice; documented for completeness.)
2. **Double-close** — `manifest.close()` is idempotent; the second call is a no-op.
3. **Serialization failure** — if `json.dumps(record)` raises (e.g. unhandled numpy type), the offending record is dropped, a single line is written to stderr, and a counter `_dropped_events` is incremented. A header check at audit time reports the dropped count.
4. **Disk full / IO error** — same handling as serialization failure; manifest enters a degraded "dropping further events" mode rather than raising. Subsequent `record()` calls become no-ops.
5. **Worker buffer cap** — each worker's buffer is capped at 100,000 events. Beyond the cap, additional `record()` calls in that worker are dropped with the same `_dropped_events` accounting. This bounds memory in the case of a buggy backtest loop.
6. **Non-monotonic timestamps** — events are merged into the parent's manifest in worker-completion order, not creation order. `ts` may not be monotonically increasing. Audit checks must not assume order; use the `island, generation` fields on `genome_evaluated` and the implicit cycle counter on `cycle_complete` if ordering matters.
7. **SIGTERM / KeyboardInterrupt** — at `manifest.open()` time the parent registers a signal handler that calls `close()` on SIGTERM or SIGINT. Forked workers inherit this handler and **must immediately reset signal disposition to default** at the top of `_run_backtest_fitness()` (before `manifest.start_worker_buffer()`); otherwise a worker receiving SIGTERM would attempt to gzip a file it doesn't own and corrupt the parent's state. The reset uses `signal.signal(signal.SIGTERM, signal.SIG_DFL)` and the same for SIGINT — workers die normally on signals; their unflushed buffers are lost (acceptable: the parent's manifest is preserved with everything up to the last completed worker result).
8. **Malformed JSONL on read** — audit's `load_manifest()` skips malformed lines (logs the count) rather than refusing to read. A partially-truncated gzip file (training crashed before clean close) is decoded with `gzip.open(..., mode='rt', errors='replace')` and lines after the truncation are skipped.

Event schema (full list in §5).

### 4.2 `preflight_checks.py`

The check registry. Decorator:

```python
@check(
    id="E05_intended_groups_mutate",
    category="evolver",
    source=["runtime", "manifest"],
    severity="critical",
    description="Every group with ≥1 non-_SKIP_PARAMS member must produce mutation events."
)
def check_intended_groups_mutate(ctx: CheckContext) -> CheckResult:
    """Filters is allowed to be silent: all 6 of its members live in _SKIP_PARAMS
    by design (see island_evolver.py:184). What we forbid is a group that has
    evolvable members yet produces no mutations — that signals a regression."""
    bounds = ctx.invoke(build_gene_bounds_from_strategy, ctx.strategy_class)
    events = ctx.events_of_type("apply_genome")
    intended_groups = {g for g in TUNABLE_GROUPS
                       if any(name in bounds for name in group_members(g))}
    seen_groups = set()
    for ev in events:
        for gene in ev["genes_applied"]:
            seen_groups.add(group_for_gene(gene))
    missing = intended_groups - seen_groups
    if missing:
        return CheckResult.fail(
            f"Intended groups produced zero mutations: {sorted(missing)}",
            evidence={"intended": sorted(intended_groups),
                      "seen": sorted(seen_groups)},
        )
    return CheckResult.pass_(
        f"All {len(intended_groups)} intended groups mutated.",
        evidence={"intended": sorted(intended_groups)},
    )
```

The decorator registers the check into a module-level dict keyed by `id`. Categories are free strings; convention uses 7 (regime, evolver, application, gates, migration, outcomes, roundtrip).

`CheckContext` shape:

```python
@dataclass
class CheckContext:
    events: list[dict]                      # captured live (preflight) or read from gz (audit)
    artifacts: dict[str, Any]               # lazy-loaded pkl/json
    config: dict                            # current pipeline config
    available_sources: set[str]             # {"runtime", "manifest", "artifact", "unit"}

    def events_of_type(self, event_type: str) -> list[dict]: ...
    def artifact(self, name: str) -> Any: ...
    def invoke(self, fn: Callable, *args, **kwargs) -> Any: ...  # for unit-source checks
```

`CheckResult` shape:

```python
@dataclass
class CheckResult:
    status: Literal["pass", "fail", "warn", "skip"]
    message: str
    evidence: dict = field(default_factory=dict)
    duration_ms: float = 0.0

    # Populated by the runner from the @check decorator metadata, NOT by the
    # check function itself. Available on the result object for downstream
    # severity filtering (e.g. exit-code logic in preflight.py).
    id: str = ""
    category: str = ""
    severity: Literal["critical", "warn", "info"] = "warn"
    sources_run: list[str] = field(default_factory=list)

    @classmethod
    def pass_(cls, msg, evidence=None): ...
    @classmethod
    def fail(cls, msg, evidence=None): ...
    @classmethod
    def warn(cls, msg, evidence=None): ...
    @classmethod
    def skip(cls, msg): ...
```

Each check is responsible for returning `skip` if its required source is not in `ctx.available_sources` (e.g. an `artifact`-only check returns `skip` during preflight if artifact wasn't written yet).

#### Check error handling

The runner wraps every check invocation:

```python
def _run_one_check(check_fn, ctx) -> CheckResult:
    t0 = time.monotonic()
    try:
        with timeout(seconds=10):       # per-check hard cap
            result = check_fn(ctx)
    except TimeoutError:
        result = CheckResult.fail(f"timed out after 10s",
                                  evidence={"check_id": check_fn._meta.id})
    except Exception as e:
        result = CheckResult.fail(f"check raised {type(e).__name__}: {e}",
                                  evidence={"traceback": traceback.format_exc()})
    result.duration_ms = (time.monotonic() - t0) * 1000
    # Stamp metadata from the @check decorator onto the result
    result.id = check_fn._meta.id
    result.category = check_fn._meta.category
    result.severity = check_fn._meta.severity
    result.sources_run = list(ctx.available_sources & set(check_fn._meta.source))
    return result
```

This guarantees:
- A buggy check function can never crash the runner — its failure surfaces as a `fail` result for that single check.
- A check that hangs (e.g. accidental infinite loop on bad evidence) is killed at 10 seconds and marked failed.
- All checks always run; the report always shows all 34 results.

### 4.3 `preflight.py` (rewrite)

> **Pre-existing bug to fix during rewrite:** the current `pipelines/_shared/IslandPilot/preflight.py` was duplicated from V1 and still imports from `pipelines._shared.IslandPilot.*` paths (verified via grep at lines 35, 81, 101–103, 158, plus the docstring at line 11). The rewrite must change every `IslandPilot` to `IslandPilot` so V2 preflight tests V2 code, not V1.

```python
def main():
    args = parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="qengine_preflight_"))
    manifest.open(tmp / "preflight_manifest.jsonl")
    captured_smoke: list[dict] = []
    captured_comprehensive: list[dict] = []

    # Phase 1 — Smoke (fail-fast, ~5s)
    # Smoke = the 7 @check predicates with 'unit' in their source list:
    #   R06 (transition grace candles), E01 (gene bounds cover groups),
    #   E02 (_SKIP_PARAMS shape), E07 (categorical resolver round-trip),
    #   E08 (multiprocess pickling), A04 (HP spec round-trip),
    #   V03 (manifest gzip round-trip).
    # No training, no data acquisition. The four existing smoke checks
    # (gene bounds present, genome variety, one synthetic backtest, one
    # generation) are NOT re-implemented as smoke — checks (a) and (b)
    # become E01 (unit) and E03 (runtime); checks (c) and (d) are subsumed
    # by phase 2's bare-minimum real run.
    smoke_results = run_unit_source_checks()  # only ['unit'] in source list
    if any(r.status == "fail" and r.severity == "critical"
           for r in smoke_results):
        write_report(smoke_results, tmp, exit_code=1)
        sys.exit(1)

    # Phase 2 — Comprehensive (~4.5 min, runs all even on failure)
    manifest.tap(captured_comprehensive.append)
    cfg = preflight_config()  # see §5 for exact knobs
    train(
        candles_file=ensure_minislice_cached(),
        pop_size=cfg.pop_size,
        generations=cfg.generations,
        max_macro=cfg.max_macro,
        max_sub=cfg.max_sub,
        min_leaf_samples=cfg.min_leaf_samples,
        n_workers=cpu_count(),
        preflight_mode=True,    # NEW: lowers gate thresholds; see §9.6
        output_dir=tmp,         # NEW: redirect artifacts away from real models/
    )
    manifest.untap()

    # Phase 2b — Force-trigger gates G01–G06 in isolation (~5s)
    force_trigger_results = run_gate_unit_checks()

    # Run all registered checks against captured events + artifacts
    ctx = CheckContext(
        events=captured_comprehensive,           # NOT captured_smoke
        artifacts=load_artifacts(),
        config=load_preflight_config(tmp),
        available_sources={"unit", "runtime", "artifact"},
    )
    all_results = run_registered_checks(ctx)

    write_report(smoke_results + all_results + force_trigger_results,
                 tmp, exit_code=0 if all_critical_passed(...) else 1)
```

Phase separation: smoke and comprehensive events are captured into separate lists. The check-running step uses only `captured_comprehensive` so smoke's synthetic-data noise (from the existing 4 smoke checks that run a tiny synthetic backtest) cannot accidentally satisfy outcome checks like O01 ("≥3 regimes have ≥1 cycle").

The `preflight_mode: bool` kwarg added to `train()` does three things and only three things:
1. Lowers `online_gate.min_cycles_for_gate` from 8 to 2 (so the natural-trigger path can fire within the bare-min 24-backtest budget; the unit-source G01 check still independently force-triggers).
2. Lowers `safety.min_genome_fitness` from 55.0 to 0.0 (don't gate deployment in preflight where every genome's fitness will be low on 30 days of data).
3. Sets a context-local flag readable by gate-firing call sites so phase 2b's force-trigger checks can elect to fire gates even when underlying conditions are not naturally met.

Manifest opening, tap subscription, and worker-buffer aggregation are independent of `preflight_mode` — they always happen if `manifest.open()` was called. Otherwise training is unchanged.

### 4.4 `audit.py`

CLI: `python audit.py <models_dir>` — `models_dir` is positional, defaults to `pipelines/_shared/IslandPilot/models/` if omitted, accepts any path. Audit writes its report into the same directory as the artifacts so the report travels with what it audits.

```python
def main(models_dir: Path):
    manifest_path = models_dir / "activation_manifest.jsonl.gz"
    available_sources = {"manifest", "artifact"} if manifest_path.exists() else {"artifact"}
    if not manifest_path.exists():
        print(f"WARN: no activation_manifest found; manifest checks will be skipped.")

    ctx = CheckContext(
        events=load_manifest(manifest_path) if manifest_path.exists() else [],
        artifacts={
            "island_evolver.json":    load_evolver(models_dir),
            "regime_tree.pkl":        load_tree(models_dir),
            "leaf_date_ranges.json":  load_ranges(models_dir),
            "training_config.json":   load_training_config(models_dir),
        },
        config=load_training_config(models_dir),  # the snapshot from training time
        available_sources=available_sources,
    )
    results = run_registered_checks(ctx, sources=available_sources)
    write_audit_report(results, models_dir)
```

Audit is read-only. It cannot fail the build because there is no build to fail at this point — it is diagnostic.

---

## 5. Data Flow & Bare-Minimum Preflight Config

### 5.1 Knobs

| Knob | Preflight value | Cloud-train value | Why |
|---|---|---|---|
| Data slice | 30 days OANDA EUR-USD 5m (~8.6k candles) | 36 months | Enough for ≥3 regimes to receive cycles |
| `pop_size` | 4 | 30 | Min for crossover offspring to differ from parents |
| `generations` | 2 | 100 | Min to fire migration once + observe gen-over-gen variance |
| `max_macro` | 3 | 10 | Min for hierarchical macro × sub > 1 |
| `max_sub` | 2 | 8 | Min for hierarchy depth |
| `min_leaf_samples` | 50 | 200 | Scaled to data slice |
| `n_workers` | `cpu_count()` | 60 (cloud) | "Max workers" per user request |
| `min_cycles_for_gate` | 2 (override) | 8 | Force online gate to be triggerable |
| `min_genome_fitness` | 0 (override) | 55 | Don't block deployment in preflight |

Total backtests in phase 2: ~3 leaves × 4 pop × 2 gen ≈ 24 backtests on 30d data. Estimated wall-time on M-series laptop with all cores: **3–4 min**. Plus 30s smoke = **<5 min total**.

### 5.2 Data acquisition

Preflight uses a fixed slice from within the **training period** (not OOS, to keep the OOS evaluation window uncontaminated): **2024-06-01 to 2024-06-30** OANDA EUR-USD 5m. This window is chosen once and locked in; preflight is reproducible because the slice is deterministic.

Preflight first checks `~/.qengine_preflight_cache/eurusd_5m_2024-06-01_2024-06-30.npy`. If missing, exports from local Postgres via existing `get_candles()`. One-time cost ~10s; cached forever after. Cache invalidation is manual — delete the file. Preflight is a verification harness, not a data freshness checker.

If Postgres is unavailable on a fresh laptop, preflight prints a single-line instruction with the cache path and exits 2.

### 5.3 Manifest event schema

| event_type | data fields |
|---|---|
| `regime_fit` | `n_macro_clusters, n_sub_per_macro (dict), leaves_before_merge, leaves_after_merge, separation_dict` (the dict returned by `_validate_regime_separation`, fields: `n_leaves, min_samples, max_samples, mean_samples, cv, threshold, valid, recommendation`) |
| `feature_partition` | `n_macro_feats, n_sub_feats, autocorr_threshold, lag` |
| `apply_genome` | `regime, genes_applied (dict), position_open` |
| `migration` | `macro, donor_island, recipient_island, donor_fitness, recipient_mean, accepted` |
| `transition` | `from_regime, to_regime, confidence, hysteresis_passed` |
| `gate_fire` | `gate, regime, reason, blocked` (gate ∈ `{online, drift, unknown_regime, proven_fitness, abort_volatility, session_halt}`) |
| `cycle_complete` | `regime, pnl, n_legs, was_bust, regime_pf_after, regime_cycles_after` |
| `genome_evaluated` | `island, generation, genome_id, fitness, n_sessions, pf, dd, bust_rate` |
| `feasibility_correction` | `gene, original, corrected, reason` |
| `categorical_resolve` | `gene, index, resolved_to` |

All events carry `ts` (ISO8601) and `event` (str) in addition to listed fields.

### 5.4 Patch sites

| File | Lines added | Event type emitted |
|---|---|---|
| `train.py` | ~17 | `regime_fit, feature_partition, genome_evaluated`, worker-result unpacking, plus `output_dir` kwarg threading (replace ~5 `_MODELS_DIR` occurrences with `models_dir = output_dir or _MODELS_DIR`) |
| `__init__.py` | ~7 | `apply_genome, gate_fire (all 6 gates incl. unknown_regime decided here), cycle_complete` |
| `island_evolver.py` | ~3 | `migration, feasibility_correction, categorical_resolve` |
| `regime_inferencer.py` | ~2 | `transition` only |

Most additions are single lines: `manifest.record("event_name", key=value, ...)`. The `train.py` patch is slightly larger because it must also (a) call `manifest.start_worker_buffer()` at the top of `_run_backtest_fitness`, (b) change the return type to `(fitness, events)`, and (c) call `manifest.merge_worker_events(events)` for each result in the parent loop. No control-flow changes; same evaluation order, same fitness values.

---

## 6. Check Catalog

The 34 checks fall into 7 categories. Full predicates are written in `preflight_checks.py`; this section is the index.

### Regime (R01–R06)

| ID | Description | Source | Severity |
|---|---|---|---|
| R01 | Feature partition produces ≥2 macro and ≥1 sub feature | runtime, artifact | critical |
| R02 | Feature partition reports whether the lag-10 autocorrelation threshold (≥0.7 macro, <0.7 sub) was met or fell back to top-half/bottom-half rank split (informational which path was taken) | runtime, artifact | warn |
| R03 | GMM fit completes; ≥2 macro × ≥2 sub leaves before sparse-merge | runtime, artifact | critical |
| R04 | Sparse-leaf merge fires; merges leaves below `min_leaf_samples` | runtime, artifact | warn |
| R05 | Hysteresis margin prevents whipsaw (≥1 boundary classification did not switch) | runtime, manifest | warn |
| R06 | Transition grace candles delay re-classification correctly | unit | warn |

### Evolver (E01–E09)

| ID | Description | Source | Severity |
|---|---|---|---|
| E01 | Built gene bounds cover every tunable group that has ≥1 evolvable member (post `_SKIP_PARAMS` filter) | unit, artifact | critical |
| E02 | `_SKIP_PARAMS` content matches the documented exclusion list; new skips trigger info-level audit entry | unit, artifact | warn |
| E03 | Initial population shows per-gene variance > 0 across the seed pool | runtime, manifest | critical |
| E04 | Mutation produces offspring differing from parents on ≥1 gene per generation | runtime, manifest | critical |
| E05 | Every "intended" group (≥1 evolvable member) produces at least one mutation event at runtime | runtime, manifest | critical |
| E06 | Joint feasibility corrections fire (TP ≥ hedge×1.5, max_ticket cap) | runtime, manifest | warn |
| E07 | Categorical gene resolver round-trips (index → string → index) | unit | critical |
| E08 | Multiprocessing pickling: genomes survive worker round-trip | unit | critical |
| E09 | Audit log enumerates `_SKIP_PARAMS` content with the source-comment rationale (informational, never fails) | artifact | info |

### Application (A01–A04)

| ID | Description | Source | Severity |
|---|---|---|---|
| A01 | `_apply_genome` reads ≥1 gene from each tunable group at runtime | runtime, manifest | critical |
| A02 | Mode-aware coercion fires when TP/hedge mode changes | runtime, manifest | warn |
| A03 | Every active leaf has a deployable best_genome in `island_evolver.json` | artifact | critical |
| A04 | Hyperparameter spec round-trips (read → mutate → write → read matches) | unit | warn |

### Gates (G01–G06, all force-triggered in preflight)

| ID | Description | Source | Severity |
|---|---|---|---|
| G01 | Online PF gate blocks when configured to (force-trigger with synthetic stats) | unit, manifest | critical |
| G02 | Drift gate blocks when recent PF < drop_ratio × lifetime PF | unit, manifest | critical |
| G03 | Unknown-regime gate blocks when max prob < `unknown_threshold` | unit, manifest | critical |
| G04 | Proven-fitness gate blocks genomes below `min_genome_fitness` | unit, manifest | critical |
| G05 | Abort-volatility fires when danger > (1 − abort_aggressiveness) | unit, manifest | critical |
| G06 | Session-halt fires when float P&L < −`session_loss_pct_halt × balance` | unit, manifest | critical |

### Migration (M01–M02)

| ID | Description | Source | Severity |
|---|---|---|---|
| M01 | Sibling acceptance ratio > 0 on ≥1 sibling pair | runtime, manifest | warn |
| M02 | Migration interval respected (`fires every gen // 5`) | runtime, manifest | warn |

### Outcomes (O01–O04)

| ID | Description | Source | Severity |
|---|---|---|---|
| O01 | ≥3 regimes have ≥1 cycle in the bare-min run | runtime, manifest | critical |
| O02 | Fitness dispersion: std(fitness across genomes) > 0 | runtime, manifest | critical |
| O03 | Per-regime stats counters increment after each cycle (`_regime_wins/losses/cycles/busts`) | runtime, manifest | critical |
| O04 | `_recent_pnls` window updates with each cycle | runtime, manifest | warn |

### Roundtrip (V01–V03)

| ID | Description | Source | Severity |
|---|---|---|---|
| V01 | Preflight artifacts (`island_evolver.json`, `regime_tree.pkl`, `leaf_date_ranges.json`) load cleanly | artifact | critical |
| V02 | `validate_model.py` runs OOS on ≥1 island, returns parseable verdict | runtime | warn |
| V03 | Manifest gzips and re-reads losslessly | unit | critical |

**Total: 34 checks.**

Severity counts: 21 critical, 12 warn, 1 info.

---

## 7. Error Handling

### 7.1 Severity levels

- `critical` — pipeline will produce broken models. Preflight exits 1. Audit flags loudly.
- `warn` — degraded behavior, training may still produce usable models. Preflight exits 0 with warnings in report. Audit flags but does not error.
- `info` — context only, never affects exit code.

### 7.2 Failure aggregation

- Phase 1 (smoke) is **fail-fast** on critical: stop immediately, do not run phase 2. Smoke is a 30s investment — running phase 2 on broken pipeline wastes 4 minutes.
- Phase 2 (comprehensive) **runs all checks even on failure** within the phase. Collect everything, report aggregate.
- Audit always runs all checks. Never gates anything.

### 7.3 Report format

Terminal pretty-print (preflight):

```
═══ IslandPilot Preflight Report ═══
Phase 1 — Smoke (32s)            ✓ 4/4 passed
Phase 2 — Comprehensive (3m 47s)
  Regime         R01–R06         ✓ 6/6
  Evolver        E01–E09         ✗ 8/9 — E05 (Take Profit group produced 0 mutations)
  Application    A01–A04         ✓ 4/4
  Gates          G01–G06         ✓ 6/6 (all force-triggered)
  Migration      M01–M02         ⚠ 1/2 — M01 (only 1/3 sibling pairs accepted)
  Outcomes       O01–O04         ✓ 4/4
  Roundtrip      V01–V03         ✓ 3/3

VERDICT: ✗ FAIL  (1 critical, 1 warning)
First critical: E05 — see preflight_report.json:checks[id=E05_intended_groups_mutate].evidence

Do NOT commit to cloud training until critical issues are resolved.
```

Audit terminal output uses the same shape with header `═══ IslandPilot Audit Report ═══` and verdict variants `OK / DEGRADED / BROKEN`.

JSON sidecar shape (`preflight_report.json` and `audit_report.json` share the same schema):

```json
{
  "schema_version": 1,
  "kind": "preflight" | "audit",
  "timestamp": "2026-04-26T17:42:13Z",
  "wall_time_seconds": 287.3,
  "verdict": "pass" | "fail" | "warn" | "ok" | "degraded" | "broken",
  "summary": {"critical_failures": 1, "warnings": 1, "passes": 28, "skips": 1},
  "checks": [
    {
      "id": "E05_intended_groups_mutate",
      "category": "evolver",
      "status": "fail",
      "severity": "critical",
      "message": "Intended groups produced zero mutations: ['Take Profit']",
      "evidence": {"intended": ["General","Grid / Hedge","Take Profit","Entry Signal","Risk Management","Position Management"], "seen": ["General","Grid / Hedge","Entry Signal","Risk Management","Position Management"]},
      "duration_ms": 4.2,
      "sources_run": ["runtime"]
    },
    ...
  ]
}
```

### 7.4 Exit codes

| Tool | Code | Meaning |
|---|---|---|
| `preflight.py` | 0 | All critical passed (warnings allowed) |
| `preflight.py` | 1 | ≥1 critical failed |
| `preflight.py` | 2 | Harness itself crashed (uncaught exception, missing data, etc.) |
| `audit.py` | 0 | Always (audit never gates) |
| `audit.py` | 2 | Harness itself crashed |

---

## 8. Testing Strategy

### 8.1 Meta-tests

`tests/test_preflight_checks.py` contains one test per check. Each builds a synthetic `CheckContext` that *should* fail and asserts the check returns `fail`. Plus one matching context that *should* pass.

```python
def test_E05_fails_when_intended_group_silent():
    # Intended groups derived from synthetic bounds covering 'General' + 'Take Profit'
    # but events only show 'General' genes applied.
    ctx = make_synthetic_ctx(
        bounds={"max_levels": (2, 8, int), "tp_value": (12, 80, float)},
        events=[{"event": "apply_genome",
                 "genes_applied": {"max_levels": 5}}],  # tp_value missing
    )
    result = check_intended_groups_mutate(ctx)
    assert result.status == "fail"
    assert "Take Profit" in result.message

def test_E05_passes_when_all_intended_groups_seen():
    ctx = make_synthetic_ctx(
        bounds={"max_levels": (2, 8, int), "tp_value": (12, 80, float)},
        events=[{"event": "apply_genome",
                 "genes_applied": {"max_levels": 5, "tp_value": 24.0}}],
    )
    result = check_intended_groups_mutate(ctx)
    assert result.status == "pass"
```

This guards against the failure mode where someone refactors `manifest.record()` and breaks every check silently — meta-tests catch the regression.

### 8.2 Self-test mode

`python preflight.py --self-test` exec's `pytest tests/test_islandpilotv2_preflight_checks.py -q` and exits with pytest's exit code. No training, no manifest, no data acquisition. Target: <5s. Suitable for pre-commit hooks if the user wants them later.

### 8.3 Manual verification on first run

After implementation, before relying on preflight:
1. Run `preflight.py` once; expect green or specific known issues.
2. Manually move a currently-evolved parameter (e.g. `tp_value`) into `island_evolver._SKIP_PARAMS`, re-run, expect E05 to fail with "Take Profit produced zero mutations". Restore.
3. Manually short-circuit `_apply_genome` to return early, re-run, expect A01 to fail. Restore.
4. Run again, expect green.

This confirms the harness actually catches what it claims to catch.

---

## 9. Implementation Notes

### 9.1 Adding a new check

1. Add a function to `preflight_checks.py` decorated with `@check(...)`.
2. Add a meta-test pair to `tests/test_preflight_checks.py`.
3. (If the check needs a new event type) add the emitter at the relevant code site in `train.py` / `__init__.py` / etc., and document the event in §5.3 of this spec.

No edits to `preflight.py`, `audit.py`, or any registry file.

### 9.2 Manifest schema versioning

Each manifest file's first line is a header record:
```json
{"event": "_header", "schema_version": 1, "qengine_commit": "abc1234", "ts": "..."}
```

`qengine_commit` is captured via `subprocess.run(['git', 'rev-parse', 'HEAD'])` at `manifest.open()` time, with a 1-second timeout; falls back to `"unknown"` if git is unavailable or the working tree isn't a repo. Best-effort, never blocks training.

Audit refuses to run if `schema_version` does not match its own (currently 1). This prevents silently misinterpreting old manifests when the schema evolves.

### 9.3 Training config snapshot

Training writes `models/training_config.json` at the start of `train()`:
```json
{
  "schema_version": 1,
  "qengine_commit": "abc1234",
  "started_at": "2026-04-26T17:42:13Z",
  "args": {"exchange": "OANDA", "symbol": "EUR-USD", "timeframe": "5m", ...},
  "resolved_config": { ... merged DEFAULT_CONFIG with any preflight_mode overrides ... },
  "tunable_groups_snapshot": ["General", "Grid / Hedge", "Take Profit", "Entry Signal", "Risk Management", "Position Management"],
  "evolved_gene_names": ["max_levels", "sizing_factor", "hedge_value", "tp_value", "..."]
}
```

Audit reads this to know what config — and what set of evolvable groups/genes — governed training. Without `tunable_groups_snapshot` and `evolved_gene_names`, audit cannot distinguish "Iteration 1" cloud artifacts (3 groups, 20 genes) from "Iteration 2" artifacts (~6 evolvable groups, ~50 genes), and would falsely fail E05 on Iteration-1 artifacts by expecting current-source groups. Add ~5 lines to `train.py` to write this file.

E05's artifact-source check uses `tunable_groups_snapshot` from this file as the ground truth for "what was intended at training time", not the live `_TUNABLE_GROUPS` from current source. Same for E01.

### 9.4 `manifest.record()` call discipline

Call `manifest.record(...)` only at points that meaningfully advance the pipeline. Do not call it inside per-candle loops (too noisy, blows up manifest size). Per-cycle / per-generation / per-decision is the right granularity.

Estimated event volume on the Iteration-1 reference cloud run (10h 33m, `c2-standard-60`, 10 pop × 20 gen × 63 islands = 12,600 evaluations, per CLOUD_TRAINING.md:26):
- `genome_evaluated`: 12,600 events (one per backtest)
- `apply_genome`: ~1–5 per backtest × 12,600 ≈ 30k events
- `cycle_complete`: ~1–5 per backtest × 12,600 ≈ 30k events
- `gate_fire`: ~10% of decisions = ~3k events
- `transition`: ~2k events (regime switches across all evaluations)
- `migration`: ≤ 63 × (20 // 5) = 252 events
- `feasibility_correction, categorical_resolve`: ~1k each at init + sporadic during mutation

Total: ~95k events. JSONL line ~200 bytes avg → ~19 MB raw. Gzipped: ~2–4 MB. Comfortably within the <10 MB G5 target.

For Iteration 2 (planned 30 pop × 100 gen × 63 islands ≈ 189k evals, per CLOUD_TRAINING.md), estimate would scale roughly linearly: ~1.4M events, ~280 MB raw, ~30–50 MB gzipped. **Exceeds G5 target by 3–5×.** When Iteration 2 lands, sample down per-event-type emission (e.g. emit only every 10th `genome_evaluated`) to stay within budget. Tracked as R-3.

### 9.5 Backwards compatibility

`manifest.record()` is no-op when manifest is not opened. Existing entry points (`train.py`, validate_model.py, anything calling `IslandPilotPipeline` from a strategy) continue to work without opening a manifest. No surprise behavior.

Old `models/` directories (from cloud runs before this change) lack `activation_manifest.jsonl.gz`. Audit runs only artifact-source checks against them, returns `skip` with reason `"no manifest"` for manifest-source checks. Audit verdict is `degraded` rather than `broken` if all artifact checks pass.

### 9.6 Preflight-mode flag and output redirect in `train()`

Two new kwargs on `train.train()`:

- `preflight_mode: bool = False` — when `True`, applies the threshold overrides documented in §5.1 *before* config is finalized.
- `output_dir: Path | None = None` — when set, writes `regime_tree.pkl`, `island_evolver.json`, `leaf_date_ranges.json`, `training_config.json`, and `activation_manifest.jsonl.gz` to this dir instead of the hardcoded `_MODELS_DIR` (currently `pipelines/_shared/IslandPilot/models/`, train.py:159). When `None`, behavior is unchanged.

Required because `_MODELS_DIR` is hardcoded; without an override, preflight invoking `train()` would clobber real cloud-trained artifacts. Preflight always passes its tmpdir; cloud training leaves the kwarg unset.

Implementation: add `models_dir = output_dir or _MODELS_DIR` near the top of `train()`, then replace every `_MODELS_DIR` reference inside `train()` with `models_dir` (~5 occurrences per train.py grep).

Existing call sites (CLI `python -m pipelines._shared.IslandPilot.train`, validate_model.py) do not pass either kwarg and see zero behavioral change.

---

## 10. Acceptance Criteria

Each AC includes its **verification method** so the implementer can prove satisfaction without ambiguity.

- **AC1.** All 34 checks implemented; each has at least one passing and one failing meta-test (informational E09 needs only a passing test since it never fails).
  *Verification:* `pytest tests/test_islandpilotv2_preflight_checks.py -q` reports ≥ 67 tests passing (34 pass-cases + 33 fail-cases; E09 has no fail-case).

- **AC2.** `python preflight.py` exits 0 within 5 minutes on a 10-core M-series laptop when the pipeline is healthy ("healthy" = a fresh checkout of `pipelines/_shared/IslandPilot/` with no manual breakage). On other hardware, scale the budget by `(10 / cpu_count())` minutes and the implementer documents the actual wall-time in their PR.
  *Verification:* `time python preflight.py` on a 10-core M-series, with `echo $?` reporting 0 and elapsed time < 300s.

- **AC3.** `python preflight.py` exits 1 and prints the failing check's `id` and `category` in the terminal report when any of the following are deliberately broken (one at a time):
  - Move a currently-evolved General/Grid/TP param into `_SKIP_PARAMS` so its group goes silent → E05 fails.
  - Set `min_leaf_samples` so high (e.g. 10,000) that no leaf survives merge → R03 fails.
  - Comment out the body of `island_evolver.migrate_siblings()` → M01 warns.
  - Add an early `return` at the top of `_apply_genome` → A01 fails.
  *Verification:* a manual run of each break-and-restore in §8.3, captured as four short shell snippets in the PR description.

- **AC4.** `python audit.py <dir>` accepts any directory containing the five expected artifact files and exits 0 with a JSON report written to `<dir>/audit_report.json`. Verdict ∈ {ok, degraded, broken}.
  *Verification:* run `python preflight.py`, capture the printed tmpdir path, run `python audit.py <that_path>`, parse `<that_path>/audit_report.json`, assert verdict ∈ {ok, degraded}. No copy step needed because audit accepts arbitrary paths.

- **AC5.** Sequential backtest overhead from `manifest.record()` calls is ≤ 1% measured wall-time on the preflight slice. Cloud-scale extrapolation of this proxy is sufficient; the spec does not require re-running cloud training to verify.
  *Verification:* `pytest tests/test_islandpilotv2_manifest_overhead.py` (one new test) runs the preflight backtest twice — once with `manifest.open()`, once without — and asserts the open-case is ≤ 101% of the closed-case wall-time, averaged over 5 trials.

- **AC6.** For Iteration-1-scale runs (10p × 20g × 63i = 12,600 evals), the projected gzipped manifest size from the preflight slice is ≤ 10 MB.
  *Verification:* the same `pytest` test as AC5 also measures bytes-per-event during preflight and computes `bytes_per_event × estimated_iter1_event_count × gzip_ratio`. Asserts ≤ 10 MB. Gzip-ratio is measured by gzipping the preflight manifest itself.

- **AC7.** Adding a new check requires editing exactly two files. *Verification:* a meta-test in `tests/test_islandpilotv2_check_addition.py` programmatically copies a synthetic check into `preflight_checks.py`, copies a synthetic test into the test file, runs `git diff --name-only`, asserts exactly two files appear. Reverts both edits.

- **AC8.** `python preflight.py --self-test` exits 0 within 5 seconds.
  *Verification:* `time python preflight.py --self-test` with `echo $?` reporting 0 and elapsed time < 5s.

---

## 11. Risks and Open Questions

### Risks

- **R-1.** Postgres dependency in preflight: the data-acquisition step requires a running local Postgres on first run. The cache miss path uses the existing `qengine.research.candles.get_candles()` API directly — no separate export script. If Postgres is unreachable on a fresh laptop with no cache, preflight prints the cache path it expected, the connection string it tried, and the underlying psycopg error, then exits 2. No phantom scripts referenced.
- **R-2.** Force-triggered gate checks may diverge from natural-trigger conditions if gate code is later refactored. *Mitigation:* unit checks in G01–G06 directly invoke the gate function with synthetic inputs — same code path as production, just hand-fed state.
- **R-3.** Manifest size could exceed 10 MB on runs with denser cycle activity. *Mitigation:* if violated in practice, add per-event-type sampling (e.g. emit only every 10th `genome_evaluated`).
- **R-4.** Bare-minimum config (3 leaves × 4 pop × 2 gen) may not produce ≥3 regimes-with-cycles on every 30-day window. *Mitigation:* preflight cache fixes the slice; pick a 30-day window known to span multiple regime types (will be selected once, locked in).
- **R-5.** Multiprocessing aggregation correctness: if a worker raises before reaching `drain_worker_buffer()`, its events are lost (process-local). *Mitigation:* wrap the worker body in `try/finally` so the buffer is drained and returned even on exception (with the exception itself recorded as a `worker_error` event). Lost-events rate must be 0 in steady state — preflight check E08 (multiprocessing pickling round-trip) extended to also assert that an artificially raised exception in the worker still surfaces its events.
- **R-6.** Sequential-mode parity: when `n_workers == 1`, the worker-buffer dance is bypassed and `record()` writes to the parent file directly. The two paths must produce identical event sequences. *Mitigation:* one of the meta-tests runs the same backtest sequentially and in parallel and asserts the merged manifest matches.

### Open Questions

- **OQ-1.** Should the Filters group ever be evolved? Currently every Filters param is in `_SKIP_PARAMS` (island_evolver.py:188–195) with the rationale "so >99% of genomes have some filter blocking all entries → zero sessions." User's brainstorming intent ("all our tunable groups… being tried in all kinds of regime") implies Filters should be tried; existing code disables them deliberately. **This spec preserves the current exclusion** and surfaces it as an audit-log info entry (E09). Whether to redesign Filters with smarter evolution (e.g. low-probability activation) is a strategy-design question that belongs to the follow-on robustness spec, not this verification spec.

---

## 12. Out of Scope (tracked for follow-on)

These will be addressed in a separate spec after this preflight harness is in place and surfacing real issues:

- Strategy-logic robustness: regime taxonomy with named types (volatile / trending / choppy / breakout), transition probability matrix from logged transitions, transition-importance scoring, probabilistic abort decisions per regime.
- Per-regime tactical parameters: hedge depth, TP style, entry-wait timer, exit-wait timer, bucket profit targets.
- Q-learning abort policy (referenced in user's prior research but not present in V2).
- IslandPilot V1 untouched throughout this work.
