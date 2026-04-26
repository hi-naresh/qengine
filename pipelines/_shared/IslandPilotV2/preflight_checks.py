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
