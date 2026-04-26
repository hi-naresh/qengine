# IslandPilotV2 — Preflight & Audit Harness

**Date:** 2026-04-26
**Author:** Claude (brainstormed with user, sneha@botwot.io)
**Goal:** Before committing to 12+ hour cloud training runs, prove the IslandPilotV2 pipeline is exercising every layer it claims to. After training, produce a structured log of what fired and what didn't.

> **Scope guard:** This spec covers verification only. Strategy-logic improvements (regime taxonomy, transition matrix, per-regime tactics, abort probabilities) are explicitly out of scope and tracked for a follow-on spec. **IslandPilot V1 is not touched.** All changes land inside `pipelines/_shared/IslandPilotV2/`.

---

## 1. Problem Statement

The current IslandPilotV2 preflight (`preflight.py`) is a 4-check smoke test on synthetic GBM data. It runs in ~2 min and confirms the code does not crash. It does **not** confirm:

1. Every tunable hyperparameter group that the design intends to evolve is actually being mutated, **and** every group that is intentionally excluded (e.g. the Filters group is in `_SKIP_PARAMS` because >99% of evolved filter combinations block all entries — see comment at `island_evolver.py:184–187`) is documented as such in the audit log so the exclusion is visible rather than silent.
2. Every regime leaf gets HP variation across the population.
3. Strategy actually reads the evolved HPs at decision time.
4. Per-regime online-learning state (`_regime_wins/losses/cycles/busts`, `_recent_pnls`) updates after each cycle.
5. Online gating, drift detection, unknown-regime gate, proven-fitness gate, abort-volatility, and session-halt all fire when their conditions are met.
6. Migration between sibling islands actually moves genes (acceptance ratio > 0).
7. Every island produces a deployable best-genome artifact.
8. Validate-model OOS path round-trips cleanly.

The cost of missing any of these before a 12-hour cloud run is the cloud spend plus the wall-clock. The cost of building a stronger preflight is ~5 minutes per check at run-time and ~1 day to write.

A second gap: even when training completes successfully, there is no post-hoc record of which gates fired, which regimes received which genomes, which migrations were accepted, or which feasibility corrections were applied. This makes diagnosing "training ran but the model is bad" impossible without re-running training with debug prints.

---

## 2. Goals and Non-Goals

### Goals

- **G1.** Pre-training preflight that verifies all ~31 layers of the pipeline exercise themselves on bare-minimum real data, in **under 5 minutes** on an M-series laptop with all cores.
- **G2.** Post-training audit that, given a completed `models/` directory, produces a structured report of what fired, what did not, and what was applied per regime — answering "did training do what it should have done?" without re-running anything.
- **G3.** Both surfaces share the same check predicates so they cannot drift apart.
- **G4.** Adding a new check requires writing one decorated function and one meta-test. No registry edits, no orchestrator edits.
- **G5.** Cloud training has near-zero overhead from the new manifest writer (target: < 1% wall-time, < 10 MB gzipped manifest on the reference 12-hour EUR-USD 5m run).
- **G6.** Training code remains runnable without the verification harness — `manifest.record(...)` calls degrade to no-ops if the manifest is not opened.

### Non-Goals

- **N1.** Strategy logic improvements (regime taxonomy, transitions, per-regime tactics, abort probabilities, per-regime entry/exit timers, bucket profit-taking). These belong to a follow-on spec.
- **N2.** Changes to fitness function, regime feature pool, or evolutionary operators.
- **N3.** Touching IslandPilot V1.
- **N4.** A web UI for the report. Terminal pretty-print + JSON sidecar only.
- **N5.** CI integration. Local-only invocation; CI is a future concern.
- **N6.** Backwards compatibility with old `models/` artifacts that lack a manifest. Audit on those will skip manifest-source checks and report `n/a` rather than fail.

---

## 3. Architecture

### 3.1 Files

```
pipelines/_shared/IslandPilotV2/
├── manifest.py              [NEW]      ~80 LOC   global event recorder
├── preflight_checks.py      [NEW]      ~1000 LOC ~31 @check functions
├── preflight.py             [REWRITE]  ~250 LOC  smoke (30s) + comprehensive (≤4.5 min)
├── audit.py                 [NEW]      ~150 LOC  post-training auditor
├── train.py                 [PATCH]    +20 lines manifest.record() at event sites
├── __init__.py              [PATCH]    +20 lines manifest.record() at event sites
├── island_evolver.py        [PATCH]    +5 lines  manifest.record() at migration accept/reject
├── regime_inferencer.py     [PATCH]    +5 lines  manifest.record() at transition + unknown-regime
└── tests/
    └── test_preflight_checks.py  [NEW] ~150 LOC  meta-tests for each check
```

Outputs (all under existing `models/`):
```
models/
├── activation_manifest.jsonl.gz   [training output]
├── preflight_report.json          [preflight output]
├── audit_report.json              [audit output]
```

### 3.2 Three execution paths, one shared registry

```
Path 1: Preflight (pre-training)              Path 2: Training (cloud)                   Path 3: Audit (post-training)
─────────────────────────────────             ─────────────────────────                  ─────────────────────────────
$ python preflight.py                         $ python train.py --workers 60             $ python audit.py models/

  ├─ Phase 1: Smoke (~30s)                      ├─ manifest.open(models/...)               ├─ load activation_manifest.jsonl.gz
  │   gene bounds, genome variety,              ├─ regime tree fit                          ├─ load island_evolver.json
  │   one synthetic backtest, one gen           │   → manifest.record('regime_fit', ...)    ├─ load regime_tree.pkl
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

Most checks register two sources, e.g. `source=["runtime", "manifest"]`, so the same predicate runs in both contexts against different evidence streams.

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
manifest.open(path: Path) -> None
manifest.record(event_type: str, **data) -> None
manifest.close() -> None
manifest.tap(subscriber: Callable[[dict], None]) -> None  # preflight-only
```

Implementation notes:
- Module-level singleton. Re-opening overwrites prior path.
- `record()` is no-op if not opened. No exception, no warning.
- Events are flushed every N records (N=100) and on close.
- `close()` gzips the file in place, leaves `.jsonl.gz` artifact.
- On training exit (atexit), automatically calls `close()` if open.
- Subscriber callback is fired synchronously inside `record()` after disk write.
- Records are JSON-serializable dicts with mandatory keys: `ts` (ISO8601), `event` (str). Caller passes additional keys via `**data`.

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

### 4.3 `preflight.py` (rewrite)

```python
def main():
    args = parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="qengine_preflight_"))
    manifest.open(tmp / "preflight_manifest.jsonl")
    captured: list[dict] = []
    manifest.tap(captured.append)

    # Phase 1 — Smoke (fail-fast, ~30s)
    smoke_results = run_smoke_phase()
    if any(r.status == "fail" and r.severity == "critical"
           for r in smoke_results):
        write_report(smoke_results, tmp, exit_code=1)
        sys.exit(1)

    # Phase 2 — Comprehensive (~4.5 min, runs all even on failure)
    cfg = preflight_config()  # see §5 for exact knobs
    train(
        candles_file=ensure_minislice_cached(),
        pop_size=cfg.pop_size,
        generations=cfg.generations,
        max_macro=cfg.max_macro,
        max_sub=cfg.max_sub,
        min_leaf_samples=cfg.min_leaf_samples,
        n_workers=cpu_count(),
        preflight_mode=True,    # NEW: lowers gate thresholds, accepts manifest_tap
    )

    # Phase 2b — Force-trigger gates G01–G06 in isolation (~5s)
    force_trigger_results = run_gate_unit_checks()

    # Run all registered checks against captured events + artifacts
    ctx = CheckContext(
        events=captured,
        artifacts=load_artifacts(),
        config=load_config(),
        available_sources={"unit", "runtime", "artifact"},
    )
    all_results = run_registered_checks(ctx)

    write_report(smoke_results + all_results + force_trigger_results,
                 tmp, exit_code=0 if all_pass(...) else 1)
```

The `--preflight-mode` flag added to `train()` does three things and only three things:
1. Lowers `online_gate.min_cycles_for_gate` from 8 to 2.
2. Lowers `safety.min_genome_fitness` from 55.0 to 0.0.
3. Sets a context-local flag readable by gate-firing call sites so they can elect to fire even when underlying conditions are not naturally met (used by force-trigger checks).

Otherwise training is unchanged.

### 4.4 `audit.py`

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
        },
        config=load_config(models_dir),
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

Preflight first checks `~/.qengine_preflight_cache/eurusd_5m_30d.npy`. If missing, exports from local Postgres via existing `get_candles()`. One-time cost ~10s; cached forever after. Cache file is invalidated by deleting it manually (no automatic invalidation — preflight is a verification harness, not a data freshness checker).

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
| `train.py` | ~8 | `regime_fit, feature_partition, genome_evaluated` |
| `__init__.py` | ~6 | `apply_genome, gate_fire, cycle_complete` |
| `island_evolver.py` | ~3 | `migration, feasibility_correction, categorical_resolve` |
| `regime_inferencer.py` | ~3 | `transition, gate_fire (unknown_regime)` |

Each addition is a single line: `manifest.record("event_name", key=value, ...)`. No control-flow changes in any patched file.

---

## 6. Check Catalog

The ~31 checks fall into 7 categories. Full predicates are written in `preflight_checks.py`; this section is the index.

### Regime (R01–R06)

| ID | Description | Source | Severity |
|---|---|---|---|
| R01 | Feature partition produces ≥2 macro and ≥1 sub feature | runtime, artifact | critical |
| R02 | Lag-10 autocorrelation threshold respected (≥0.7 macro, <0.7 sub) | runtime, artifact | warn |
| R03 | GMM fit completes; ≥2 macro × ≥2 sub leaves before sparse-merge | runtime, artifact | critical |
| R04 | Sparse-leaf merge fires; merges leaves below `min_leaf_samples` | runtime, artifact | warn |
| R05 | Hysteresis margin prevents whipsaw (≥1 boundary classification did not switch) | runtime, manifest | warn |
| R06 | Transition grace candles delay re-classification correctly | unit | warn |

### Evolver (E01–E08)

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

**Total: 32 checks.**

Severity counts: 19 critical, 12 warn, 1 info.

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
═══ IslandPilotV2 Preflight Report ═══
Phase 1 — Smoke (32s)            ✓ 4/4 passed
Phase 2 — Comprehensive (3m 47s)
  Regime         R01–R06         ✓ 6/6
  Evolver        E01–E08         ✗ 7/8 — E05 (Filters group never mutated)
  Application    A01–A04         ✓ 4/4
  Gates          G01–G06         ✓ 6/6 (all force-triggered)
  Migration      M01–M02         ⚠ 1/2 — M01 (only 1/3 sibling pairs accepted)
  Outcomes       O01–O04         ✓ 4/4
  Roundtrip      V01–V03         ✓ 3/3

VERDICT: ✗ FAIL  (1 critical, 1 warning)
First critical: E05 — see preflight_report.json:checks[12].evidence

Do NOT commit to cloud training until critical issues are resolved.
```

Audit terminal output uses the same shape with header `═══ IslandPilotV2 Audit Report ═══` and verdict variants `OK / DEGRADED / BROKEN`.

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
      "id": "E05_filters_group_mutates",
      "category": "evolver",
      "status": "fail",
      "severity": "critical",
      "message": "No Filters genes ever applied. _SKIP list likely dropped them.",
      "evidence": {"filters_keys": [...], "n_events": 24},
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
def test_E05_filters_group_mutates_fails_when_no_filters_events():
    ctx = make_synthetic_ctx(events=[
        {"event": "apply_genome", "genes_applied": {"signal_mode": "ema_cross"}}
    ])
    result = check_filters_group_mutates(ctx)
    assert result.status == "fail"
    assert "Filters" in result.message

def test_E05_filters_group_mutates_passes_when_filters_seen():
    ctx = make_synthetic_ctx(events=[
        {"event": "apply_genome", "genes_applied": {"session_filter": True}}
    ])
    result = check_filters_group_mutates(ctx)
    assert result.status == "pass"
```

This guards against the failure mode where someone refactors `manifest.record()` and breaks every check silently — meta-tests catch the regression.

### 8.2 Self-test mode

`python preflight.py --self-test` runs only the meta-tests (no training). Target: <5s. Suitable for pre-commit hooks if the user wants them later.

### 8.3 Manual verification on first run

After implementation, before relying on preflight:
1. Run `preflight.py` once; expect green or specific known issues.
2. Manually break the Filters skip in `island_evolver._SKIP` (remove one filter param), re-run, expect E05 to fail.
3. Restore, run again, expect green.

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
Audit refuses to run if `schema_version` does not match its own (currently 1). This prevents silently misinterpreting old manifests when the schema evolves.

### 9.3 `manifest.record()` call discipline

Call `manifest.record(...)` only at points that meaningfully advance the pipeline. Do not call it inside per-candle loops (too noisy, blows up manifest size). Per-cycle / per-generation / per-decision is the right granularity.

Estimated event volume on the reference 12-hour cloud run:
- `apply_genome`: ~1 per cycle × ~10k cycles = 10k events
- `cycle_complete`: 10k events
- `gate_fire`: ~1k events
- `transition`: ~5k events
- `genome_evaluated`: 30 pop × 100 gen × 63 islands = ~189k events
- Migration, feasibility, categorical: ~1k each

Total: ~220k events. JSONL line ~200 bytes avg → ~44 MB raw. Gzipped: ~5–8 MB. Within the <10 MB target in G5.

### 9.4 Backwards compatibility

`manifest.record()` is no-op when manifest is not opened. Existing entry points (`train.py`, validate_model.py, anything calling `IslandPilotPipeline` from a strategy) continue to work without opening a manifest. No surprise behavior.

Old `models/` directories (from cloud runs before this change) lack `activation_manifest.jsonl.gz`. Audit runs only artifact-source checks against them, returns `skip` with reason `"no manifest"` for manifest-source checks. Audit verdict is `degraded` rather than `broken` if all artifact checks pass.

### 9.5 Preflight-mode flag in `train()`

The new `preflight_mode: bool = False` kwarg on `train.train()`:
- When `True`: applies the threshold overrides in §5.1 *before* config is finalized.
- When `False`: zero behavioral change. Existing call sites need no edit.

Adds one line near the top of `train()`: `if preflight_mode: cfg = apply_preflight_overrides(cfg)`.

---

## 10. Acceptance Criteria

A successful implementation of this spec satisfies:

- **AC1.** All 31 checks implemented; each has at least one passing and one failing meta-test.
- **AC2.** `python preflight.py` exits within 5 minutes on M-series laptop (`time` ≤ 300s) when the pipeline is healthy.
- **AC3.** `python preflight.py` exits 1 with a clear message identifying the cause if any of the following are deliberately broken (one at a time):
  - Move a currently-evolved General/TP/Grid param into `_SKIP_PARAMS` so its group goes silent → E05 fails.
  - Set `min_leaf_samples` so high that no leaf survives merge → R03 fails.
  - Disable migration → M01 warns.
  - Force `_apply_genome` to short-circuit → A01 fails.
- **AC4.** `python audit.py models/` exits 0 with a structured report on a freshly cloud-trained `models/` directory.
- **AC5.** Cloud training run wall-time increases by <1% after manifest.record() patches.
- **AC6.** Manifest from a 12-hour reference run is ≤10 MB gzipped.
- **AC7.** Adding a new check requires editing exactly two files (`preflight_checks.py` + `test_preflight_checks.py`); no orchestrator edits.
- **AC8.** `python preflight.py --self-test` exits 0 within 5 seconds.

---

## 11. Risks and Open Questions

### Risks

- **R-1.** Postgres dependency in preflight: the data-acquisition step requires a running local Postgres on first run. If the cache is lost and Postgres is unavailable (e.g. on a fresh laptop), preflight cannot run. *Mitigation:* check the cache exists first, error with a clear "run `python -m qengine.research.export_eurusd_5m_30d` first" message rather than silently failing.
- **R-2.** Force-triggered gate checks may diverge from natural-trigger conditions if gate code is later refactored. *Mitigation:* unit checks in G01–G06 directly invoke the gate function with synthetic inputs — same code path as production, just hand-fed state.
- **R-3.** Manifest size could exceed 10 MB on runs with denser cycle activity. *Mitigation:* if violated in practice, add per-event-type sampling (e.g. emit only every 10th `genome_evaluated`).
- **R-4.** Bare-minimum config (3 leaves × 4 pop × 2 gen) may not produce ≥3 regimes-with-cycles on every 30-day window. *Mitigation:* preflight cache fixes the slice; pick a 30-day window known to span multiple regime types (will be selected once, locked in).

### Open Questions

- **OQ-1.** Should the Filters group ever be evolved? Currently every Filters param is in `_SKIP_PARAMS` (island_evolver.py:188–195) with the rationale "so >99% of genomes have some filter blocking all entries → zero sessions." User's brainstorming intent ("all our tunable groups… being tried in all kinds of regime") implies Filters should be tried; existing code disables them deliberately. **This spec preserves the current exclusion** and surfaces it as an audit-log info entry (E09). Whether to redesign Filters with smarter evolution (e.g. low-probability activation) is a strategy-design question that belongs to the follow-on robustness spec, not this verification spec.

---

## 12. Out of Scope (tracked for follow-on)

These will be addressed in a separate spec after this preflight harness is in place and surfacing real issues:

- Strategy-logic robustness: regime taxonomy with named types (volatile / trending / choppy / breakout), transition probability matrix from logged transitions, transition-importance scoring, probabilistic abort decisions per regime.
- Per-regime tactical parameters: hedge depth, TP style, entry-wait timer, exit-wait timer, bucket profit targets.
- Q-learning abort policy (referenced in user's prior research but not present in V2).
- IslandPilot V1 untouched throughout this work.
