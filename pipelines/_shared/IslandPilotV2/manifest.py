"""Append-only JSONL event recorder for IslandPilotV2 verification harness.

Three modes:
- Closed (default): record() is a no-op. Training without preflight/audit pays nothing.
- Parent file-open: record() writes JSONL + fires tap.
- Worker buffer: record() appends to a per-process list (drained back to parent).

See docs/superpowers/specs/2026-04-26-islandpilotv2-preflight-design.md §4.1.
"""
from __future__ import annotations

import atexit
import builtins
import datetime as _dt
import gzip
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_SCHEMA_VERSION = 1

# Parent-process state
_path: Optional[Path] = None
_fp = None  # text-mode file handle
_tap: Optional[Callable[[dict], None]] = None
_dropped_events: int = 0
_records_since_flush: int = 0
_FLUSH_EVERY: int = 100
_signal_prev: dict = {}  # signum -> previous handler
_atexit_registered: bool = False

# Worker-process state
_worker_buffer: Optional[list[dict]] = None


def _reset_for_tests() -> None:
    """Reset all module-level state. Test-only helper."""
    global _path, _fp, _tap, _dropped_events, _records_since_flush, _worker_buffer
    global _atexit_registered
    if _fp is not None:
        try:
            _fp.close()
        except Exception:
            pass
    _path = None
    _fp = None
    _tap = None
    _dropped_events = 0
    _records_since_flush = 0
    _worker_buffer = None
    _atexit_registered = False


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=1,
            cwd=Path(__file__).resolve().parent,
        )
        if out.returncode == 0:
            return out.stdout.strip()[:12]
    except Exception:
        pass
    return "unknown"


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _install_signal_handlers() -> None:
    def _handler(signum, frame):
        try:
            close()
        finally:
            # Re-raise default disposition so exit code is correct
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            _signal_prev[sig] = signal.signal(sig, _handler)
        except (OSError, ValueError):
            # Some environments (worker threads, tests) won't allow this.
            pass


def open(path: Path) -> None:  # noqa: A001
    """Open the manifest at `path` for append-only writes. Idempotent re-open
    flushes the prior file and starts a new one."""
    global _path, _fp, _records_since_flush, _dropped_events, _atexit_registered
    prior_path_str = str(_path) if _fp is not None else None
    if _fp is not None:
        close()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _fp = path.open("a", encoding="utf-8")
    _path = path
    _records_since_flush = 0
    _dropped_events = 0
    header = {
        "event": "_header",
        "ts": _now_iso(),
        "schema_version": _SCHEMA_VERSION,
        "qengine_commit": _git_commit(),
    }
    _fp.write(json.dumps(header) + "\n")
    _fp.flush()
    _install_signal_handlers()
    if not _atexit_registered:
        atexit.register(close)
        _atexit_registered = True
    if prior_path_str is not None:
        record("_session_restart", prior_path=prior_path_str)


def record(event_type: str, **data) -> None:
    """Record an event. No-op if not opened and no worker buffer active."""
    global _dropped_events, _records_since_flush
    rec = {"event": event_type, "ts": _now_iso(), **data}

    # Worker buffer takes precedence when active
    if _worker_buffer is not None:
        if len(_worker_buffer) >= 100_000:
            _dropped_events += 1
            return
        try:
            json.dumps(rec)  # validate serializability
        except (TypeError, ValueError):
            _dropped_events += 1
            return
        _worker_buffer.append(rec)
        return

    if _fp is None:
        return  # closed mode

    try:
        line = json.dumps(rec)
    except (TypeError, ValueError):
        _dropped_events += 1
        sys.stderr.write(f"manifest: dropped unserializable event {event_type}\n")
        return

    try:
        _fp.write(line + "\n")
        _records_since_flush += 1
        if _records_since_flush >= _FLUSH_EVERY:
            _fp.flush()
            _records_since_flush = 0
    except OSError as e:
        _dropped_events += 1
        sys.stderr.write(f"manifest: write failed ({e}), dropping further events\n")
        return

    if _tap is not None:
        try:
            _tap(rec)
        except Exception as e:
            sys.stderr.write(f"manifest: tap callback raised {type(e).__name__}: {e}\n")


def tap(subscriber: Callable[[dict], None]) -> None:
    """Register an in-memory subscriber. Preflight only — synchronous fire after disk write."""
    global _tap
    _tap = subscriber


def untap() -> None:
    """Clear the subscriber."""
    global _tap
    _tap = None


def close() -> None:
    """Flush + gzip the manifest file. Idempotent."""
    global _fp, _path
    if _fp is None:
        return
    try:
        if _dropped_events > 0:
            _fp.write(json.dumps({
                "event": "_footer",
                "ts": _now_iso(),
                "dropped_events": _dropped_events,
            }) + "\n")
        _fp.flush()
        _fp.close()
    except Exception:
        pass
    _fp = None

    if _path is not None and _path.exists():
        gz_path = _path.with_suffix(_path.suffix + ".gz")
        try:
            with _path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            _path.unlink()
        except Exception as e:
            sys.stderr.write(f"manifest: gzip failed ({e}); leaving uncompressed\n")
    _path = None


# Worker API
def start_worker_buffer() -> None:
    """Begin per-process buffering. record() will append to a list rather than
    write to disk. Call drain_worker_buffer() at end to retrieve events."""
    global _worker_buffer
    _worker_buffer = []


def drain_worker_buffer() -> list[dict]:
    """Return accumulated worker events and reset the buffer to inactive."""
    global _worker_buffer
    if _worker_buffer is None:
        return []
    out = _worker_buffer
    _worker_buffer = None
    return out


def merge_worker_events(events: list[dict]) -> None:
    """Re-emit worker events into the parent's manifest. Each event already
    has its `ts` and `event` fields; we just write through."""
    global _records_since_flush
    if _fp is None:
        return
    for rec in events:
        try:
            line = json.dumps(rec)
        except (TypeError, ValueError):
            continue
        try:
            _fp.write(line + "\n")
            _records_since_flush += 1
        except OSError:
            return
        if _tap is not None:
            try:
                _tap(rec)
            except Exception:
                pass
    if _records_since_flush >= _FLUSH_EVERY:
        _fp.flush()
        _records_since_flush = 0


def load_manifest(path: Path) -> list[dict]:
    """Read all events from a gzipped JSONL manifest. Skips malformed lines.
    Raises ValueError if header schema_version mismatches."""
    path = Path(path)
    events: list[dict] = []
    skipped = 0
    opener = gzip.open if str(path).endswith(".gz") else builtins.open
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            events.append(rec)
    if skipped > 0:
        sys.stderr.write(f"manifest: skipped {skipped} malformed lines in {path}\n")
    if events and events[0].get("event") == "_header":
        sv = events[0].get("schema_version")
        if sv != _SCHEMA_VERSION:
            raise ValueError(
                f"manifest schema_version {sv} != current {_SCHEMA_VERSION}; "
                f"refusing to interpret {path}"
            )
    return events
