"""
run_pipeline.py — Phase 4 Research Pipeline Orchestrator

Runs scripts 40-47 sequentially via subprocess. Stops on first failure.

Usage:
    python run_pipeline.py              # run all scripts 40-47
    python run_pipeline.py 40 41        # run specific scripts
    python run_pipeline.py --from 43    # run from script 43 onwards
"""

import subprocess
import sys
import time
from pathlib import Path

PYTHON = sys.executable
PHASE4_DIR = Path(__file__).resolve().parent

SCRIPTS = [
    (40, '40_regime_discovery.py',       'Regime tree discovery & feature selection'),
    (41, '41_island_evolution.py',       'Island-model genetic evolution'),
    (42, '42_inference_validation.py',   'Inference validation on 2018-2021'),
    (43, '43_full_pipeline_backtest.py', 'Full pipeline backtest on 2021-2025'),
    (44, '44_ablation_study.py',         'Ablation study (8 variants)'),
    (45, '45_statistical_tests.py',      'Statistical significance tests'),
    (46, '46_walk_forward.py',           'Walk-forward validation (3 windows)'),
    (47, '47_comparison_baselines.py',   'Comparison baselines & summary'),
]


def run_script(num: int, filename: str, desc: str, timeout: int = 3600):
    """Run a single script via subprocess.

    Returns:
        (success: bool, elapsed_seconds: float)
    """
    script_path = PHASE4_DIR / filename
    if not script_path.exists():
        print(f"  [SKIP] {filename} not found")
        return False, 0.0

    print(f"\n{'='*70}")
    print(f"  [{num}] {desc}")
    print(f"  File: {filename}")
    print(f"{'='*70}\n")

    start = time.time()
    try:
        result = subprocess.run(
            [PYTHON, str(script_path)],
            cwd=str(PHASE4_DIR),
            timeout=timeout,
        )
        elapsed = time.time() - start
        success = result.returncode == 0
        status = "OK" if success else f"FAILED (exit code {result.returncode})"
        print(f"\n  [{num}] {status} ({elapsed:.1f}s)")
        return success, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"\n  [{num}] TIMEOUT after {elapsed:.1f}s")
        return False, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  [{num}] ERROR: {e} ({elapsed:.1f}s)")
        return False, elapsed


def main():
    args = sys.argv[1:]

    # Determine which scripts to run
    if '--from' in args:
        idx = args.index('--from')
        if idx + 1 < len(args):
            from_num = int(args[idx + 1])
            scripts_to_run = [(n, f, d) for n, f, d in SCRIPTS if n >= from_num]
        else:
            print("Error: --from requires a script number")
            sys.exit(1)
    elif args:
        # Specific script numbers
        requested = set(int(a) for a in args if a.isdigit())
        scripts_to_run = [(n, f, d) for n, f, d in SCRIPTS if n in requested]
    else:
        scripts_to_run = SCRIPTS

    if not scripts_to_run:
        print("No scripts to run.")
        sys.exit(0)

    print(f"Phase 4 IslandPilot Research Pipeline")
    print(f"Running {len(scripts_to_run)} script(s): "
          f"{', '.join(str(n) for n, _, _ in scripts_to_run)}")
    print(f"Python: {PYTHON}")

    # Run scripts
    results = []
    total_start = time.time()

    for num, filename, desc in scripts_to_run:
        success, elapsed = run_script(num, filename, desc)
        results.append((num, filename, desc, success, elapsed))
        if not success:
            print(f"\n*** Pipeline stopped: script {num} failed ***")
            break

    total_elapsed = time.time() - total_start

    # Summary table
    print(f"\n{'='*70}")
    print(f"  PIPELINE SUMMARY")
    print(f"{'='*70}")
    print(f"{'Script':<8} {'File':<35} {'Status':<10} {'Time':>8}")
    print(f"{'-'*70}")

    n_ok = 0
    n_fail = 0
    for num, filename, desc, success, elapsed in results:
        status = "OK" if success else "FAILED"
        if success:
            n_ok += 1
        else:
            n_fail += 1
        print(f"  {num:<6} {filename:<35} {status:<10} {elapsed:>7.1f}s")

    print(f"{'-'*70}")
    print(f"  Total: {n_ok} passed, {n_fail} failed, {total_elapsed:.1f}s elapsed")

    sys.exit(0 if n_fail == 0 else 1)


if __name__ == '__main__':
    main()
