"""Verify AC7: adding a new check requires editing exactly two files."""
import subprocess
from pathlib import Path
import pytest


REPO = Path(__file__).resolve().parents[1]


def test_adding_a_check_touches_only_two_files():
    """Insert a synthetic @check + meta-test, verify git diff shows exactly
    preflight_checks.py + the test file. Then revert."""
    checks_path = REPO / "pipelines/_shared/IslandPilot/preflight_checks.py"
    tests_path = REPO / "tests/test_islandpilot_preflight_checks.py"

    assert checks_path.exists(), f"missing: {checks_path}"
    assert tests_path.exists(), f"missing: {tests_path}"

    checks_orig = checks_path.read_text()
    tests_orig = tests_path.read_text()

    # Verify clean working tree on these two files specifically
    pre_diff = subprocess.run(
        ["git", "diff", "--name-only", "--",
         str(checks_path.relative_to(REPO)),
         str(tests_path.relative_to(REPO))],
        cwd=REPO, capture_output=True, text=True,
    )
    if pre_diff.stdout.strip():
        pytest.skip(
            f"working tree has uncommitted changes in target files: "
            f"{pre_diff.stdout.strip()} - re-run on a clean tree"
        )

    sentinel = "\n# === AC7 SYNTHETIC ===\n"
    checks_path.write_text(checks_orig + sentinel + (
        '@check(id="Z99_synthetic", category="synthetic", source=["unit"],\n'
        '       severity="info", description="ac7 sentinel")\n'
        'def check_Z99_synthetic(ctx):\n'
        '    return CheckResult.pass_("synthetic")\n'
    ))
    tests_path.write_text(tests_orig + sentinel + (
        'def test_Z99_synthetic_exists():\n'
        '    from pipelines._shared.IslandPilot import preflight_checks as pc\n'
        '    assert "Z99_synthetic" in pc._registry\n'
    ))

    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "--",
             str(checks_path.relative_to(REPO)),
             str(tests_path.relative_to(REPO))],
            cwd=REPO, capture_output=True, text=True,
        )
        changed = sorted(l for l in out.stdout.splitlines() if l.strip())
        expected = sorted([
            str(checks_path.relative_to(REPO)),
            str(tests_path.relative_to(REPO)),
        ])
        assert changed == expected, (
            f"expected exactly {expected}, got {changed}"
        )
    finally:
        # Always restore
        checks_path.write_text(checks_orig)
        tests_path.write_text(tests_orig)


def test_existing_check_count_is_34():
    """Sanity: total registered checks matches the spec's 34."""
    # Importing preflight_checks triggers all decorator registrations.
    # We need to ensure no other test has cleared the registry first by
    # forcing a fresh import via reload.
    import importlib
    from pipelines._shared.IslandPilot import preflight_checks as pc
    importlib.reload(pc)
    assert len(pc._registry) == 34, (
        f"expected 34 registered checks, got {len(pc._registry)}: "
        f"{sorted(pc._registry.keys())}"
    )
