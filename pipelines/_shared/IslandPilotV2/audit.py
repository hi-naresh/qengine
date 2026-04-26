"""IslandPilotV2 post-training audit.

Reads activation_manifest.jsonl.gz + final artifacts; runs all registered
@check predicates with source in {manifest, artifact}; writes audit_report.json
into the same directory as the artifacts.

Run: python -m pipelines._shared.IslandPilotV2.audit [models_dir]
     (default: pipelines/_shared/IslandPilotV2/models/)
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipelines._shared.IslandPilotV2 import manifest, preflight_checks as pc


def _load_artifact(path: Path):
    if not path.exists():
        return None
    try:
        if path.suffix == ".pkl":
            return pickle.loads(path.read_bytes())
        return json.loads(path.read_text())
    except Exception as e:
        print(f"audit: failed to load {path.name}: {e}", file=sys.stderr)
        return None


def main(models_dir: Path) -> int:
    models_dir = Path(models_dir)
    if not models_dir.is_dir():
        print(f"audit: {models_dir} is not a directory", file=sys.stderr)
        return 2

    manifest_path = models_dir / "activation_manifest.jsonl.gz"
    has_manifest = manifest_path.exists()
    available = {"artifact"} | ({"manifest"} if has_manifest else set())

    if not has_manifest:
        print(f"audit: no activation_manifest at {manifest_path} -- manifest-source checks will skip")

    events = []
    if has_manifest:
        try:
            events = manifest.load_manifest(manifest_path)
        except ValueError as e:
            print(f"audit: refusing to read manifest: {e}", file=sys.stderr)
            return 2

    artifacts = {
        "regime_tree.pkl": _load_artifact(models_dir / "regime_tree.pkl"),
        "island_evolver.json": _load_artifact(models_dir / "island_evolver.json"),
        "leaf_date_ranges.json": _load_artifact(models_dir / "leaf_date_ranges.json"),
        "training_config.json": _load_artifact(models_dir / "training_config.json"),
    }
    cfg = artifacts.get("training_config.json") or {}

    ctx = pc.CheckContext(
        events=events,
        artifacts=artifacts,
        config=cfg,
        available_sources=available,
    )
    t0 = time.monotonic()
    results = pc.run_registered_checks(ctx)
    wall = time.monotonic() - t0

    crit_fail = sum(1 for r in results if r.status == "fail" and r.severity == "critical")
    warns = sum(1 for r in results if r.status == "warn")
    if has_manifest and crit_fail == 0:
        verdict = "ok"
    elif not has_manifest and crit_fail == 0:
        verdict = "degraded"
    else:
        verdict = "broken"

    report = {
        "schema_version": 1,
        "kind": "audit",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_time_seconds": round(wall, 1),
        "verdict": verdict,
        "models_dir": str(models_dir),
        "manifest_present": has_manifest,
        "summary": {
            "critical_failures": crit_fail,
            "warnings": warns,
            "passes": sum(1 for r in results if r.status == "pass"),
            "skips": sum(1 for r in results if r.status == "skip"),
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
    out = models_dir / "audit_report.json"
    out.write_text(json.dumps(report, indent=2, default=str))

    print()
    print(f"=== IslandPilotV2 Audit Report ===")
    print(f"  models_dir: {models_dir}")
    print(f"  manifest:   {'present' if has_manifest else 'MISSING'}")
    print(f"  verdict:    {verdict.upper()}")
    print(f"  passes:     {report['summary']['passes']}")
    print(f"  warnings:   {report['summary']['warnings']}")
    print(f"  critical:   {report['summary']['critical_failures']}")
    print(f"  skips:      {report['summary']['skips']}")
    print(f"  report:     {out}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "models_dir", nargs="?",
        default=str(Path(__file__).resolve().parent / "models"),
    )
    args = parser.parse_args()
    sys.exit(main(Path(args.models_dir)))
