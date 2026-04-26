"""IslandPilotV2 preflight harness.

Two phases:
  Phase 1 (Smoke, ~5s): runs unit-source @check predicates only.
                        Fast fail if pipeline static contracts are broken.
  Phase 2 (Comprehensive, ~4.5min): runs a bare-minimum real backtest on a
                        30-day OANDA EUR-USD slice, captures events via the
                        manifest tap, runs all registered checks.

Outputs everything to a tempdir; never touches real models/.

Run: python -m pipelines._shared.IslandPilotV2.preflight
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from multiprocessing import cpu_count
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipelines._shared.IslandPilotV2 import manifest, preflight_checks as pc


_PREFLIGHT_SLICE_START = "2024-06-01"
_PREFLIGHT_SLICE_END = "2024-06-30"
_CACHE_DIR = Path.home() / ".qengine_preflight_cache"
_CACHE_FILE = _CACHE_DIR / f"eurusd_5m_{_PREFLIGHT_SLICE_START}_{_PREFLIGHT_SLICE_END}.npy"


def _ensure_minislice_cached() -> str:
    """Return path to a 30-day OANDA EUR-USD 5m candles file.
    Cached at ~/.qengine_preflight_cache/."""
    if _CACHE_FILE.exists():
        return str(_CACHE_FILE)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[preflight] cache miss; exporting 30-day slice from Postgres...")
    try:
        import numpy as np
        from qengine.research.candles import get_candles
        warmup, candles = get_candles(
            exchange="OANDA", symbol="EUR-USD", timeframe="5m",
            start_date=_PREFLIGHT_SLICE_START, finish_date=_PREFLIGHT_SLICE_END,
        )
        if candles.size == 0:
            raise RuntimeError("get_candles returned empty array")
        np.save(_CACHE_FILE, candles)
        print(f"[preflight] cached {candles.shape[0]} candles -> {_CACHE_FILE}")
    except Exception as e:
        print(f"[preflight] FATAL: cache miss + Postgres unavailable.\n"
              f"  Cache path: {_CACHE_FILE}\n"
              f"  Error: {type(e).__name__}: {e}\n"
              f"  Fix: ensure local Postgres is running with OANDA EUR-USD 5m data.",
              file=sys.stderr)
        sys.exit(2)
    return str(_CACHE_FILE)


def _run_smoke_phase() -> list:
    """Run the cohort of @check predicates with 'unit' in source list."""
    ctx = pc.CheckContext(events=[], artifacts={}, config={},
                          available_sources={"unit"})
    return pc.run_registered_checks(ctx)


def _self_test() -> int:
    """Exec pytest on the meta-tests."""
    import subprocess
    r = subprocess.run(
        ["pytest", "tests/test_islandpilotv2_preflight_checks.py", "-q"],
        cwd=_REPO_ROOT,
    )
    return r.returncode


def _all_critical_passed(results: list) -> bool:
    return not any(
        r.status == "fail" and r.severity == "critical"
        for r in results
    )


def _write_report(results: list, tmpdir: Path, exit_code: int, wall_time: float) -> None:
    """Write JSON sidecar + pretty terminal report."""
    crit_fail = sum(1 for r in results if r.status == "fail" and r.severity == "critical")
    warns = sum(1 for r in results if r.status == "warn" or
                (r.status == "fail" and r.severity == "warn"))
    passes = sum(1 for r in results if r.status == "pass")
    skips = sum(1 for r in results if r.status == "skip")

    verdict = "fail" if crit_fail > 0 else ("warn" if warns > 0 else "pass")
    report = {
        "schema_version": 1,
        "kind": "preflight",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_time_seconds": round(wall_time, 1),
        "verdict": verdict,
        "summary": {
            "critical_failures": crit_fail,
            "warnings": warns,
            "passes": passes,
            "skips": skips,
        },
        "checks": [
            {
                "id": r.id, "category": r.category, "status": r.status,
                "severity": r.severity, "message": r.message,
                "evidence": r.evidence, "duration_ms": r.duration_ms,
                "sources_run": r.sources_run,
            }
            for r in results
        ],
    }
    out = tmpdir / "preflight_report.json"
    out.write_text(json.dumps(report, indent=2, default=str))

    # Terminal pretty-print
    print()
    print("=== IslandPilotV2 Preflight Report ===")
    by_cat: dict = {}
    for r in results:
        by_cat.setdefault(r.category or "other", []).append(r)
    for cat, items in sorted(by_cat.items()):
        n = len(items)
        ok = sum(1 for r in items if r.status == "pass")
        bad = [r for r in items if r.status == "fail"]
        warn = [r for r in items if r.status == "warn"]
        symbol = "OK" if not bad else ("WARN" if not any(r.severity == "critical" for r in bad) else "FAIL")
        line = f"  {cat.title():15s} {symbol:4s} {ok}/{n}"
        if bad:
            line += f" -- {bad[0].id} ({bad[0].message[:60]})"
        elif warn:
            line += f" warn {warn[0].id} ({warn[0].message[:60]})"
        print(line)

    print()
    print(f"VERDICT: {verdict.upper()}  ({crit_fail} critical, {warns} warnings)")
    print(f"Report:  {out}")
    print(f"Tmpdir:  {tmpdir}")
    if exit_code != 0:
        print("\nDo NOT commit to cloud training until critical issues are resolved.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true",
                        help="Run meta-tests only and exit")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    t_start = time.monotonic()
    tmp = Path(tempfile.mkdtemp(prefix="qengine_preflight_"))
    print(f"[preflight] tmpdir: {tmp}")

    manifest.open(tmp / "preflight_manifest.jsonl")

    # Phase 1 -- Smoke
    print("[preflight] Phase 1 -- Smoke...")
    smoke_results = _run_smoke_phase()
    if not _all_critical_passed(smoke_results):
        manifest.close()
        wall = time.monotonic() - t_start
        _write_report(smoke_results, tmp, exit_code=1, wall_time=wall)
        return 1

    # Phase 2 -- Comprehensive
    print("[preflight] Phase 2 -- Comprehensive (bare-minimum real run)...")
    captured: list = []
    manifest.tap(captured.append)

    candles_file = _ensure_minislice_cached()
    os.environ["QENGINE_TRAINING_MODE"] = "1"

    try:
        from pipelines._shared.IslandPilotV2 import train as tm
        tm.train(
            exchange="OANDA", symbol="EUR-USD", timeframe="5m",
            train_start=_PREFLIGHT_SLICE_START, train_end=_PREFLIGHT_SLICE_END,
            strategy_name="Martingale",
            pop_size=4, generations=2,
            max_macro=3, max_sub=2, min_leaf_samples=50,
            n_workers=cpu_count(),
            candles_file=candles_file,
            output_dir=tmp,
            preflight_mode=True,
            verbose=False,
        )
    except Exception as e:
        manifest.untap()
        manifest.close()
        print(f"[preflight] FATAL: training raised {type(e).__name__}: {e}", file=sys.stderr)
        wall = time.monotonic() - t_start
        # Still write a partial report
        _write_report(smoke_results, tmp, exit_code=2, wall_time=wall)
        return 2
    manifest.untap()

    # Run all registered checks against captured events + artifacts
    artifacts = {}
    for fname in ("regime_tree.pkl", "island_evolver.json", "leaf_date_ranges.json"):
        p = tmp / fname
        if p.exists():
            try:
                if fname.endswith(".pkl"):
                    import pickle
                    artifacts[fname] = pickle.loads(p.read_bytes())
                else:
                    artifacts[fname] = json.loads(p.read_text())
            except Exception as e:
                artifacts[fname] = None
                print(f"[preflight] failed to load {fname}: {e}")
    cfg_path = tmp / "training_config.json"
    if cfg_path.exists():
        try:
            artifacts["training_config.json"] = json.loads(cfg_path.read_text())
        except Exception:
            artifacts["training_config.json"] = {}

    ctx = pc.CheckContext(
        events=captured,
        artifacts=artifacts,
        config=artifacts.get("training_config.json", {}),
        available_sources={"unit", "runtime", "artifact"},
    )
    all_results = pc.run_registered_checks(ctx)
    manifest.close()
    wall = time.monotonic() - t_start
    exit_code = 0 if _all_critical_passed(all_results) else 1
    _write_report(smoke_results + all_results, tmp, exit_code=exit_code, wall_time=wall)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
