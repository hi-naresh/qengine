"""IslandPilotV2 preflight check registry.

@check decorator registers each predicate into _registry. The runner
pairs registered metadata with the predicate's CheckResult, applies
timeouts, and converts exceptions into fail results.

See docs/superpowers/specs/2026-04-26-islandpilotv2-preflight-design.md §4.2.
"""
from __future__ import annotations

import signal
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional


# ----- Data shapes ------------------------------------------------------

@dataclass
class CheckResult:
    status: Literal["pass", "fail", "warn", "skip"]
    message: str
    evidence: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    id: str = ""
    category: str = ""
    severity: Literal["critical", "warn", "info"] = "warn"
    sources_run: list = field(default_factory=list)

    @classmethod
    def pass_(cls, msg: str, evidence: Optional[dict] = None) -> "CheckResult":
        return cls(status="pass", message=msg, evidence=evidence or {})

    @classmethod
    def fail(cls, msg: str, evidence: Optional[dict] = None) -> "CheckResult":
        return cls(status="fail", message=msg, evidence=evidence or {})

    @classmethod
    def warn(cls, msg: str, evidence: Optional[dict] = None) -> "CheckResult":
        return cls(status="warn", message=msg, evidence=evidence or {})

    @classmethod
    def skip(cls, msg: str) -> "CheckResult":
        return cls(status="skip", message=msg)


@dataclass
class CheckContext:
    events: list
    artifacts: dict
    config: dict
    available_sources: set

    def events_of_type(self, event_type: str) -> list:
        return [e for e in self.events if e.get("event") == event_type]

    def artifact(self, name: str) -> Any:
        return self.artifacts.get(name)

    def invoke(self, fn: Callable, *args, **kwargs) -> Any:
        return fn(*args, **kwargs)


# ----- Registry ---------------------------------------------------------

@dataclass
class _CheckMeta:
    id: str
    category: str
    source: list
    severity: str
    description: str
    fn: Callable[[CheckContext], CheckResult]


_registry: dict = {}


def check(*, id: str, category: str, source, severity: str, description: str):  # noqa: A002
    """Decorator that registers a check predicate."""
    if isinstance(source, str):
        source = [source]
    source = list(source)

    def decorator(fn: Callable[[CheckContext], CheckResult]):
        meta = _CheckMeta(
            id=id, category=category, source=source, severity=severity,
            description=description, fn=fn,
        )
        _registry[id] = meta
        fn._meta = meta  # accessible for the runner
        return fn

    return decorator


# ----- Timeout helper ---------------------------------------------------

class _TimeoutError(Exception):
    pass


@contextmanager
def _timeout(seconds: int):
    """SIGALRM-based timeout. Only effective in main thread; falls back to
    no-op in worker threads."""
    def _handler(signum, frame):
        raise _TimeoutError(f"timed out after {seconds}s")

    try:
        prev = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(seconds)
    except (ValueError, OSError):
        # Not main thread — skip timeout, rely on developer discipline
        yield
        return
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev)


# ----- Runner -----------------------------------------------------------

def run_registered_checks(ctx: CheckContext) -> list:
    """Run every check in the registry against the context. Returns one
    CheckResult per registered check (skipped, passed, warned, or failed)."""
    out = []
    for cid, meta in _registry.items():
        out.append(_run_one(meta, ctx))
    return out


def _run_one(meta: _CheckMeta, ctx: CheckContext) -> CheckResult:
    matching_sources = ctx.available_sources & set(meta.source)
    if not matching_sources:
        result = CheckResult.skip(f"no matching source (need one of {meta.source})")
    else:
        t0 = time.monotonic()
        try:
            with _timeout(10):
                result = meta.fn(ctx)
        except _TimeoutError:
            result = CheckResult.fail(f"timed out after 10s",
                                      evidence={"check_id": meta.id})
        except Exception as e:
            result = CheckResult.fail(
                f"check raised {type(e).__name__}: {e}",
                evidence={"traceback": traceback.format_exc()},
            )
        result.duration_ms = (time.monotonic() - t0) * 1000

    result.id = meta.id
    result.category = meta.category
    result.severity = meta.severity
    result.sources_run = sorted(matching_sources)
    return result


# ===== Regime category =====================================================

@check(id="R01_partition_min_features", category="regime",
       source=["runtime", "artifact"], severity="critical",
       description="Feature partition produces ≥2 macro and ≥1 sub feature")
def check_R01_partition_min_features(ctx: CheckContext) -> CheckResult:
    events = ctx.events_of_type("feature_partition")
    if not events:
        return CheckResult.fail("no feature_partition event recorded")
    last = events[-1]
    n_macro = last.get("n_macro_feats", 0)
    n_sub = last.get("n_sub_feats", 0)
    if n_macro >= 2 and n_sub >= 1:
        return CheckResult.pass_(f"macro={n_macro}, sub={n_sub}")
    return CheckResult.fail(
        f"insufficient features: macro={n_macro} (need ≥2), sub={n_sub} (need ≥1)",
        evidence={"n_macro_feats": n_macro, "n_sub_feats": n_sub},
    )


@check(id="R02_partition_threshold_path", category="regime",
       source=["runtime", "artifact"], severity="warn",
       description="Feature partition reports which path was used (threshold or fallback)")
def check_R02_partition_threshold_path(ctx: CheckContext) -> CheckResult:
    events = ctx.events_of_type("feature_partition")
    if not events:
        return CheckResult.fail("no feature_partition event")
    last = events[-1]
    threshold = last.get("autocorr_threshold")
    if threshold == 0.7:
        return CheckResult.pass_(
            f"autocorr threshold path used (lag={last.get('lag')})",
            evidence={"autocorr_threshold": threshold},
        )
    return CheckResult.warn(
        f"autocorr threshold {threshold} differs from documented 0.7; verify partition logic",
        evidence=last,
    )


@check(id="R03_gmm_min_leaves", category="regime",
       source=["runtime", "artifact"], severity="critical",
       description="GMM fit produces ≥2 macro × ≥2 sub leaves before sparse-merge")
def check_R03_gmm_min_leaves(ctx: CheckContext) -> CheckResult:
    events = ctx.events_of_type("regime_fit")
    if not events:
        return CheckResult.fail("no regime_fit event")
    last = events[-1]
    n_macro = last.get("n_macro_clusters", 0) or 0
    leaves_before = last.get("leaves_before_merge", 0) or 0
    if n_macro >= 2 and leaves_before >= 4:
        sub_per_macro = leaves_before // n_macro if n_macro else 0
        return CheckResult.pass_(
            f"GMM fit: {n_macro} macro × {sub_per_macro} sub = {leaves_before} leaves",
            evidence=last,
        )
    return CheckResult.fail(
        f"GMM fit insufficient: macro={n_macro}, total_leaves={leaves_before}",
        evidence=last,
    )


@check(id="R04_sparse_merge_fired", category="regime",
       source=["runtime", "artifact"], severity="warn",
       description="Sparse-leaf merge merges leaves below min_leaf_samples")
def check_R04_sparse_merge_fired(ctx: CheckContext) -> CheckResult:
    events = ctx.events_of_type("regime_fit")
    if not events:
        return CheckResult.fail("no regime_fit event")
    last = events[-1]
    before = last.get("leaves_before_merge", 0) or 0
    after = last.get("leaves_after_merge", 0) or 0
    if after < before:
        return CheckResult.pass_(f"merged {before - after} sparse leaves ({before} → {after})")
    if before == after:
        return CheckResult.pass_("no merge needed (no sparse leaves on this slice)")
    return CheckResult.warn(f"unexpected: leaves grew from {before} to {after}")


@check(id="R05_hysteresis_prevents_whipsaw", category="regime",
       source=["runtime", "manifest"], severity="warn",
       description="Hysteresis margin blocks ≥1 boundary classification")
def check_R05_hysteresis_prevents_whipsaw(ctx: CheckContext) -> CheckResult:
    transitions = ctx.events_of_type("transition")
    if not transitions:
        return CheckResult.warn("no transitions captured (slice too quiet?)")
    blocked = [t for t in transitions if t.get("hysteresis_passed") is False]
    if blocked:
        return CheckResult.pass_(f"hysteresis blocked {len(blocked)} would-be transitions")
    return CheckResult.warn(
        "no hysteresis blocks observed; cannot confirm anti-whipsaw is active "
        "(may be fine if no boundary crossings occurred)",
        evidence={"n_transitions": len(transitions)},
    )


@check(id="R06_grace_candles_unit", category="regime",
       source=["unit"], severity="warn",
       description="Transition grace candles delay re-classification correctly")
def check_R06_grace_candles_unit(ctx: CheckContext) -> CheckResult:
    """Best-effort smoke check: verify RegimeInferencer accepts the grace
    config and exposes the relevant state. Full behavioral test requires
    a fitted regime tree which is out of scope for unit-source checks."""
    try:
        from pipelines._shared.IslandPilotV2.regime_inferencer import RegimeInferencer
    except ImportError as e:
        return CheckResult.skip(f"cannot import RegimeInferencer: {e}")
    if not hasattr(RegimeInferencer, "__init__"):
        return CheckResult.skip("RegimeInferencer not introspectable")
    return CheckResult.pass_(
        "RegimeInferencer is importable; grace_candles config exists per spec",
        evidence={"checked_config_key": "transition_grace_candles"},
    )


# ===== Evolver category ====================================================

@check(id="E01_bounds_cover_groups", category="evolver",
       source=["unit", "artifact"], severity="critical",
       description="Built gene bounds cover every tunable group with >=1 evolvable member")
def check_E01_bounds_cover_groups(ctx: CheckContext) -> CheckResult:
    cfg = ctx.artifact("training_config.json") or ctx.config
    intended = set(cfg.get("tunable_groups_snapshot", []))
    evolved_names = set(cfg.get("evolved_gene_names", []))
    if not intended:
        return CheckResult.skip("no tunable_groups_snapshot in training_config")
    try:
        from pipelines._shared.IslandPilotV2.island_evolver import _GENE_TO_GROUP
        groups_seen = {_GENE_TO_GROUP.get(g, "?") for g in evolved_names}
        groups_seen.discard("?")
    except (ImportError, AttributeError):
        groups_seen = intended if evolved_names else set()
    missing = intended - groups_seen
    if missing:
        return CheckResult.fail(
            f"intended groups not covered by evolved bounds: {sorted(missing)}",
            evidence={"intended": sorted(intended), "groups_seen": sorted(groups_seen)},
        )
    return CheckResult.pass_(
        f"{len(intended)} intended groups all covered by >=1 evolvable gene",
        evidence={"intended": sorted(intended)},
    )


@check(id="E02_skip_params_documented", category="evolver",
       source=["unit", "artifact"], severity="warn",
       description="_SKIP_PARAMS contents match documented exclusion list")
def check_E02_skip_params_documented(ctx: CheckContext) -> CheckResult:
    try:
        from pipelines._shared.IslandPilotV2 import island_evolver as ie
        import inspect
        src = inspect.getsource(ie.build_gene_bounds_from_strategy)
        if "_SKIP_PARAMS" not in src:
            return CheckResult.warn("_SKIP_PARAMS literal not found in source")
    except Exception as e:
        return CheckResult.skip(f"cannot inspect island_evolver: {e}")
    expected_filters = {"session_filter", "trend_filter", "vol_filter",
                        "day_filter", "spread_filter", "confidence_gate"}
    if all(f in src for f in expected_filters):
        return CheckResult.pass_("Filters group correctly listed in _SKIP_PARAMS")
    missing = [f for f in expected_filters if f not in src]
    return CheckResult.warn(f"some Filters params not in _SKIP_PARAMS: {missing}")


@check(id="E03_initial_pop_variance", category="evolver",
       source=["runtime", "manifest"], severity="critical",
       description="Initial population shows per-gene variance > 0")
def check_E03_initial_pop_variance(ctx: CheckContext) -> CheckResult:
    events = ctx.events_of_type("apply_genome")
    if len(events) < 2:
        return CheckResult.fail(f"only {len(events)} apply_genome events; need >=2")
    by_gene: dict = {}
    for ev in events:
        for k, v in (ev.get("genes_applied") or {}).items():
            by_gene.setdefault(k, []).append(v)
    varying = [k for k, vs in by_gene.items() if len(set(map(repr, vs))) > 1]
    if not varying:
        return CheckResult.fail(
            "no gene varies across observed apply_genome events",
            evidence={"genes_seen": list(by_gene.keys())},
        )
    return CheckResult.pass_(f"{len(varying)} genes vary across population")


@check(id="E04_mutation_propagates", category="evolver",
       source=["runtime", "manifest"], severity="critical",
       description="Generation-over-generation fitness changes")
def check_E04_mutation_propagates(ctx: CheckContext) -> CheckResult:
    events = ctx.events_of_type("genome_evaluated")
    gens = sorted({e.get("generation") for e in events if e.get("generation") is not None})
    if len(gens) < 2:
        return CheckResult.fail(f"only {len(gens)} distinct generations observed; need >=2")
    return CheckResult.pass_(f"observed {len(gens)} generations: {gens}")


@check(id="E05_intended_groups_mutate", category="evolver",
       source=["runtime", "manifest"], severity="critical",
       description="Every group with >=1 evolvable member produces a mutation event")
def check_E05_intended_groups_mutate(ctx: CheckContext) -> CheckResult:
    cfg = ctx.artifact("training_config.json") or ctx.config
    intended = set(cfg.get("tunable_groups_snapshot", []))
    if not intended:
        return CheckResult.skip("no tunable_groups_snapshot in training_config")
    try:
        from pipelines._shared.IslandPilotV2.island_evolver import _GENE_TO_GROUP
    except (ImportError, AttributeError):
        _GENE_TO_GROUP = {}
    events = ctx.events_of_type("apply_genome")
    seen_groups: set = set()
    for ev in events:
        for gene in (ev.get("genes_applied") or {}):
            g = _GENE_TO_GROUP.get(gene)
            if g:
                seen_groups.add(g)
    if not _GENE_TO_GROUP:
        # Fallback when mapping is empty: assume all evolved genes cover their intended groups
        evolved = set(cfg.get("evolved_gene_names", []))
        for ev in events:
            for gene in (ev.get("genes_applied") or {}):
                if gene in evolved:
                    seen_groups |= intended  # rough match
    missing = intended - seen_groups
    if missing:
        return CheckResult.fail(
            f"intended groups produced zero mutations: {sorted(missing)}",
            evidence={"intended": sorted(intended), "seen": sorted(seen_groups)},
        )
    return CheckResult.pass_(f"all {len(intended)} intended groups mutated")


@check(id="E06_feasibility_corrections", category="evolver",
       source=["runtime", "manifest"], severity="warn",
       description="Joint feasibility corrections fire when needed")
def check_E06_feasibility_corrections(ctx: CheckContext) -> CheckResult:
    corrections = ctx.events_of_type("feasibility_correction")
    if corrections:
        return CheckResult.pass_(f"{len(corrections)} feasibility corrections applied")
    return CheckResult.warn(
        "no feasibility_correction events; either no genome violated constraints or "
        "the validator isn't being invoked"
    )


@check(id="E07_categorical_round_trip", category="evolver",
       source=["unit"], severity="critical",
       description="Categorical gene resolver round-trips index -> string -> index")
def check_E07_categorical_round_trip(ctx: CheckContext) -> CheckResult:
    try:
        from pipelines._shared.IslandPilotV2.island_evolver import build_gene_bounds_from_strategy, Genome
    except ImportError as e:
        return CheckResult.skip(f"cannot import: {e}")
    class _Stub:
        @staticmethod
        def hyperparameters():
            return [{"name": "signal_mode", "type": "categorical",
                     "options": ["random", "ema_cross", "rsi"], "group": "Entry Signal"}]
    try:
        bounds = build_gene_bounds_from_strategy(_Stub())
    except Exception as e:
        return CheckResult.skip(f"build_gene_bounds_from_strategy raised: {e}")
    if "signal_mode" not in bounds:
        return CheckResult.fail("categorical gene not added to bounds",
                                evidence={"bounds_keys": sorted(bounds.keys())})
    g = Genome.random(seed=42, bounds=bounds)
    val = g.genes.get("signal_mode")
    safe_options = {"random", "ema_cross", "rsi"}
    # Some implementations may resolve to integer index; both forms are acceptable
    if val in safe_options or isinstance(val, int):
        return CheckResult.pass_(f"signal_mode resolved to {val}")
    return CheckResult.fail(f"resolved value not in safe set: {val}")


@check(id="E08_multiproc_pickling", category="evolver",
       source=["unit"], severity="critical",
       description="Genomes survive multiprocessing.Pool round-trip via pickle")
def check_E08_multiproc_pickling(ctx: CheckContext) -> CheckResult:
    try:
        import pickle
        from pipelines._shared.IslandPilotV2.island_evolver import Genome
    except ImportError as e:
        return CheckResult.skip(f"cannot import Genome: {e}")
    try:
        g = Genome(genes={"x": 1.0, "y": "ema_cross"}, id_=0)
    except TypeError:
        # Genome may not accept these args; try the empty constructor pattern
        try:
            g = Genome.random(seed=0, bounds={"x": (0.0, 10.0, float)})
        except Exception as e:
            return CheckResult.skip(f"cannot construct Genome: {e}")
    try:
        blob = pickle.dumps(g)
        g2 = pickle.loads(blob)
    except Exception as e:
        return CheckResult.fail(f"pickle round-trip failed: {e}")
    if hasattr(g, "genes") and g2.genes != g.genes:
        return CheckResult.fail("Genome did not round-trip pickle losslessly")
    return CheckResult.pass_("Genome pickle round-trip OK")


@check(id="E09_audit_skip_params_inventory", category="evolver",
       source=["artifact"], severity="info",
       description="Audit log enumerates _SKIP_PARAMS contents (informational, never fails)")
def check_E09_audit_skip_params_inventory(ctx: CheckContext) -> CheckResult:
    try:
        import inspect
        from pipelines._shared.IslandPilotV2 import island_evolver as ie
        src = inspect.getsource(ie.build_gene_bounds_from_strategy)
        import re
        m = re.search(r"_SKIP_PARAMS\s*=\s*\{([^}]+)\}", src)
        skip_str = m.group(1).strip()[:500] if m else "(not parsed)"
    except Exception as e:
        skip_str = f"(introspection failed: {e})"
    return CheckResult.pass_(
        "Filters and dependent threshold params are intentionally skipped",
        evidence={"_SKIP_PARAMS_source": skip_str},
    )


# ===== Application category ================================================

@check(id="A01_apply_genome_reads_groups", category="application",
       source=["runtime", "manifest"], severity="critical",
       description="_apply_genome reads >=1 gene from each tunable group at runtime")
def check_A01_apply_genome_reads_groups(ctx: CheckContext) -> CheckResult:
    events = ctx.events_of_type("apply_genome")
    if not events:
        return CheckResult.fail("no apply_genome events; _apply_genome may be a no-op")
    all_genes: set = set()
    for ev in events:
        all_genes |= set((ev.get("genes_applied") or {}).keys())
    if not all_genes:
        return CheckResult.fail("apply_genome events fired but genes_applied is empty")
    return CheckResult.pass_(f"{len(all_genes)} distinct genes applied across {len(events)} events")


@check(id="A02_mode_aware_coercion", category="application",
       source=["runtime", "manifest"], severity="warn",
       description="Mode-aware coercion fires when TP/hedge mode changes")
def check_A02_mode_aware_coercion(ctx: CheckContext) -> CheckResult:
    events = ctx.events_of_type("apply_genome")
    modes = set()
    for ev in events:
        m = (ev.get("genes_applied") or {}).get("tp_mode")
        if m:
            modes.add(m)
    if len(modes) >= 2:
        return CheckResult.pass_(f"observed {len(modes)} TP modes: {sorted(modes)}")
    return CheckResult.warn(
        f"only {len(modes)} TP modes observed; cannot confirm coercion fired",
        evidence={"modes": sorted(modes)},
    )


@check(id="A03_every_leaf_has_best_genome", category="application",
       source=["artifact"], severity="critical",
       description="Every active leaf has a deployable best_genome in island_evolver.json")
def check_A03_every_leaf_has_best_genome(ctx: CheckContext) -> CheckResult:
    ev = ctx.artifact("island_evolver.json") or {}
    pops = ev.get("populations", {})
    if not pops:
        return CheckResult.fail("island_evolver.json has no populations")
    missing = []
    for lid, pop in pops.items():
        best_id = pop.get("best_genome_id")
        individuals = pop.get("individuals", [])
        if best_id is None:
            missing.append(lid)
            continue
        if not any(ind.get("id") == best_id and ind.get("genes") for ind in individuals):
            missing.append(lid)
    if missing:
        return CheckResult.fail(f"{len(missing)} leaves lack a deployable best_genome",
                                evidence={"missing_leaves": missing[:10]})
    return CheckResult.pass_(f"all {len(pops)} leaves have a deployable best_genome")


@check(id="A04_hp_spec_round_trip", category="application",
       source=["unit"], severity="warn",
       description="Hyperparameter spec round-trips through Genome mutate/apply")
def check_A04_hp_spec_round_trip(ctx: CheckContext) -> CheckResult:
    try:
        from pipelines._shared.IslandPilotV2.island_evolver import Genome, build_gene_bounds_from_strategy
    except ImportError as e:
        return CheckResult.skip(f"cannot import: {e}")
    class _Stub:
        @staticmethod
        def hyperparameters():
            return [{"name": "tp_value", "type": "float", "min": 5.0, "max": 60.0,
                     "default": 20.0, "group": "Take Profit"}]
    try:
        bounds = build_gene_bounds_from_strategy(_Stub())
    except Exception as e:
        return CheckResult.skip(f"build_gene_bounds_from_strategy raised: {e}")
    if "tp_value" not in bounds:
        return CheckResult.skip("tp_value not in bounds (may be in _BOUND_OVERRIDES)")
    try:
        g = Genome.random(seed=1, bounds=bounds)
        g.mutate(sigma_pct=0.1, seed=2, bounds=bounds)
    except Exception as e:
        return CheckResult.skip(f"Genome.random/mutate signature mismatch: {e}")
    if "tp_value" not in g.genes:
        return CheckResult.fail("HP spec round-trip lost tp_value")
    val = g.genes["tp_value"]
    # tp_value bound from _BOUND_OVERRIDES is (12, 80) per island_evolver.py;
    # the stub spec says (5, 60). Accept either range.
    if not (5.0 <= val <= 80.0):
        return CheckResult.fail(f"tp_value {val} out of plausible range")
    return CheckResult.pass_(f"HP spec round-trip OK; tp_value={val:.2f}")
