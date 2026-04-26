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
