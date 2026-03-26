#!/usr/bin/env python3
"""
Phase 2 Pipeline Orchestrator
==============================
Master script that runs all phase 2 research phases sequentially (or selectively).

Usage:
    python run_pipeline.py --phase all
    python run_pipeline.py --phase A
    python run_pipeline.py --phase B --skip-gate
    python run_pipeline.py --phase C,D,E
    python run_pipeline.py --phase F

Phases:
    A  — Data + Feature Engineering  (15_data_features.py)
    B  — Online Bayesian HMM         (16_online_hmm.py)        [GATE]
    C  — Per-Regime Config Opt        (17_regime_configs.py)     [parallel with D, E]
    D  — Contextual Bandit Entry      (18_entry_bandit.py)       [parallel with C, E]
    E  — Tabular Q-Learning Abort     (19_abort_rl.py)           [parallel with C, D]
    F  — Full Validation              (20_full_validation.py)

Dependency graph:
    A -> B -> [C, D, E] (parallel) -> F
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PYTHON = '/Users/naresh/miniconda3/bin/python3'
PHASE2_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PHASE2_DIR, 'data')
RESULTS_DIR = os.path.join(PHASE2_DIR, 'results')

# Phase script mapping
PHASE_SCRIPTS = {
    'A': '15_data_features.py',
    'B': '16_online_hmm.py',
    'C': '17_regime_configs.py',
    'D': '18_entry_bandit.py',
    'E': '19_abort_rl.py',
    'F': '20_full_validation.py',
}

PHASE_DESCRIPTIONS = {
    'A': 'Data + Feature Engineering',
    'B': 'Online Bayesian HMM (Gate)',
    'C': 'Per-Regime Config Optimization',
    'D': 'Contextual Bandit Entry',
    'E': 'Tabular Q-Learning Abort',
    'F': 'Full Validation',
}

# Expected output files for verification
PHASE_OUTPUTS = {
    'A': ['feature_matrix.parquet', 'cycle_labels.parquet'],
    'B': ['hmm_regimes.pkl', 'gate_result.json'],
    'C': ['regime_configs.json'],
    'D': ['bandit_policy.pkl'],
    'E': ['q_table.pkl'],
    'F': ['validation_report.json'],
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _ts() -> str:
    """Current timestamp string."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def log(msg: str, level: str = 'INFO') -> None:
    """Print a timestamped log line."""
    print(f'[{_ts()}] {level:>7}  {msg}', flush=True)


def log_header(text: str) -> None:
    """Print a section header."""
    border = '=' * 70
    print(f'\n{border}')
    print(f'  {text}')
    print(f'{border}')


def log_phase_start(phase: str) -> None:
    log_header(f'PHASE {phase}: {PHASE_DESCRIPTIONS[phase]}')
    log(f'Starting phase {phase} ...')


def log_phase_end(phase: str, elapsed: float, success: bool) -> None:
    status = 'COMPLETED' if success else 'FAILED'
    log(f'Phase {phase} {status} in {elapsed:.1f}s')


# ---------------------------------------------------------------------------
# Phase Execution
# ---------------------------------------------------------------------------
class PhaseResult:
    """Stores the result of running one phase."""

    def __init__(self, phase: str):
        self.phase = phase
        self.success = False
        self.elapsed = 0.0
        self.return_code = -1
        self.error_msg = ''
        self.metrics: Dict = {}
        self.output_verified = False

    def to_dict(self) -> dict:
        return {
            'phase': self.phase,
            'description': PHASE_DESCRIPTIONS.get(self.phase, '?'),
            'success': self.success,
            'elapsed_seconds': round(self.elapsed, 1),
            'return_code': self.return_code,
            'error_msg': self.error_msg,
            'metrics': self.metrics,
            'output_verified': self.output_verified,
        }


def run_phase(phase: str, timeout: int = 7200) -> PhaseResult:
    """Execute one phase script as a subprocess.

    Parameters
    ----------
    phase : str
        Phase letter (A-F).
    timeout : int
        Maximum seconds to allow the script to run (default 2 hours).

    Returns
    -------
    PhaseResult with success/failure info.
    """
    result = PhaseResult(phase)
    script = PHASE_SCRIPTS.get(phase)
    if script is None:
        result.error_msg = f'Unknown phase: {phase}'
        return result

    script_path = os.path.join(PHASE2_DIR, script)
    if not os.path.exists(script_path):
        result.error_msg = f'Script not found: {script_path}'
        log(f'SKIP phase {phase}: {result.error_msg}', level='WARN')
        return result

    log_phase_start(phase)
    t0 = time.time()

    try:
        proc = subprocess.run(
            [PYTHON, script_path],
            cwd=PHASE2_DIR,
            capture_output=False,  # stream output to terminal
            timeout=timeout,
        )
        result.return_code = proc.returncode
        result.success = proc.returncode == 0

        if not result.success:
            result.error_msg = f'Script exited with code {proc.returncode}'

    except subprocess.TimeoutExpired:
        result.error_msg = f'Timed out after {timeout}s'
        log(result.error_msg, level='ERROR')
    except Exception as e:
        result.error_msg = str(e)
        log(f'Exception running phase {phase}: {e}', level='ERROR')

    result.elapsed = time.time() - t0
    log_phase_end(phase, result.elapsed, result.success)

    # Verify expected outputs exist
    result.output_verified = verify_phase_outputs(phase)
    if result.success and not result.output_verified:
        log(f'Phase {phase} completed but expected output files not found', level='WARN')

    # Try to load metrics if available
    result.metrics = load_phase_metrics(phase)

    return result


def run_phases_parallel(phases: List[str], timeout: int = 7200) -> Dict[str, PhaseResult]:
    """Run multiple phases in parallel using subprocess.

    Returns dict mapping phase letter to PhaseResult.
    """
    log(f'Starting phases {", ".join(phases)} in parallel ...')
    processes = {}
    results = {}
    t0 = time.time()

    # Launch all
    for phase in phases:
        script = PHASE_SCRIPTS.get(phase)
        if script is None:
            r = PhaseResult(phase)
            r.error_msg = f'Unknown phase: {phase}'
            results[phase] = r
            continue

        script_path = os.path.join(PHASE2_DIR, script)
        if not os.path.exists(script_path):
            r = PhaseResult(phase)
            r.error_msg = f'Script not found: {script_path}'
            log(f'SKIP phase {phase}: {r.error_msg}', level='WARN')
            results[phase] = r
            continue

        log(f'  Launching phase {phase}: {script}')
        log_path = os.path.join(RESULTS_DIR, f'phase_{phase}.log')
        os.makedirs(RESULTS_DIR, exist_ok=True)
        log_file = open(log_path, 'w')
        proc = subprocess.Popen(
            [PYTHON, script_path],
            cwd=PHASE2_DIR,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        processes[phase] = (proc, log_file, time.time())

    # Wait for all to finish
    for phase, (proc, log_file, start_t) in processes.items():
        result = PhaseResult(phase)
        try:
            remaining = max(1, timeout - (time.time() - t0))
            proc.wait(timeout=remaining)
            result.return_code = proc.returncode
            result.success = proc.returncode == 0
            if not result.success:
                result.error_msg = f'Script exited with code {proc.returncode}'
        except subprocess.TimeoutExpired:
            proc.kill()
            result.error_msg = f'Timed out after {timeout}s'
            log(f'Phase {phase}: {result.error_msg}', level='ERROR')
        except Exception as e:
            result.error_msg = str(e)
        finally:
            log_file.close()

        result.elapsed = time.time() - start_t
        result.output_verified = verify_phase_outputs(phase)
        result.metrics = load_phase_metrics(phase)
        results[phase] = result

        log_phase_end(phase, result.elapsed, result.success)

    return results


# ---------------------------------------------------------------------------
# Output Verification
# ---------------------------------------------------------------------------
def verify_phase_outputs(phase: str) -> bool:
    """Check whether expected output files for a phase exist."""
    expected = PHASE_OUTPUTS.get(phase, [])
    if not expected:
        return True

    for fname in expected:
        # Check in both data/ and results/
        found = (
            os.path.exists(os.path.join(DATA_DIR, fname))
            or os.path.exists(os.path.join(RESULTS_DIR, fname))
        )
        if not found:
            return False
    return True


def load_phase_metrics(phase: str) -> Dict:
    """Try to load key metrics from a phase's output.

    Looks for gate_result.json (Phase B) or validation_report.json (Phase F).
    """
    metrics = {}
    if phase == 'B':
        gate_path = os.path.join(DATA_DIR, 'gate_result.json')
        if not os.path.exists(gate_path):
            gate_path = os.path.join(RESULTS_DIR, 'gate_result.json')
        if os.path.exists(gate_path):
            try:
                with open(gate_path) as f:
                    metrics = json.load(f)
            except Exception:
                pass
    elif phase == 'F':
        report_path = os.path.join(DATA_DIR, 'validation_report.json')
        if not os.path.exists(report_path):
            report_path = os.path.join(RESULTS_DIR, 'validation_report.json')
        if os.path.exists(report_path):
            try:
                with open(report_path) as f:
                    metrics = json.load(f)
            except Exception:
                pass
    return metrics


# ---------------------------------------------------------------------------
# Gate Check (Phase B)
# ---------------------------------------------------------------------------
def check_gate(result_b: PhaseResult, skip_gate: bool) -> bool:
    """Check whether Phase B passed the regime significance gate.

    The gate passes if the permutation p-value < 0.01 (regime detection
    has real signal). If --skip-gate is set, always passes.

    Returns True if the pipeline should continue to phases C/D/E.
    """
    if skip_gate:
        log('--skip-gate set: forcing pipeline past Phase B gate', level='WARN')
        return True

    if not result_b.success:
        log('Phase B FAILED. Cannot proceed past gate.', level='ERROR')
        return False

    metrics = result_b.metrics
    p_value = metrics.get('permutation_p_value')

    if p_value is None:
        log('Phase B output missing permutation_p_value. '
            'Cannot evaluate gate. Stopping.', level='ERROR')
        return False

    passed = p_value < 0.01
    if passed:
        log(f'GATE PASSED: permutation p-value = {p_value:.4f} (< 0.01)')
        log('Regime detection has real signal. Proceeding to phases C/D/E.')
    else:
        log(f'GATE FAILED: permutation p-value = {p_value:.4f} (>= 0.01)', level='ERROR')
        log('Regime detection does NOT show significant signal.')
        log('Recommendation: ship structural solution (no adaptive pipeline).')

    return passed


# ---------------------------------------------------------------------------
# Summary Report
# ---------------------------------------------------------------------------
def print_summary(all_results: Dict[str, PhaseResult], gate_passed: Optional[bool]) -> None:
    """Print a final summary of all phase results."""
    log_header('PIPELINE SUMMARY')

    # Phase status table
    print(f'\n  {"Phase":<8} {"Description":<35} {"Status":<12} {"Time":>8}  {"Outputs":<10}')
    print(f'  {"-" * 85}')

    for phase in 'ABCDEF':
        if phase not in all_results:
            print(f'  {phase:<8} {PHASE_DESCRIPTIONS[phase]:<35} {"SKIPPED":<12} {"--":>8}  {"--":<10}')
            continue

        r = all_results[phase]
        status = 'OK' if r.success else 'FAILED'
        if r.error_msg and 'not found' in r.error_msg:
            status = 'NOT IMPL'
        time_str = f'{r.elapsed:.0f}s'
        out_str = 'verified' if r.output_verified else 'missing'
        print(f'  {phase:<8} {PHASE_DESCRIPTIONS[phase]:<35} {status:<12} {time_str:>8}  {out_str:<10}')

    # Gate result
    if gate_passed is not None:
        print(f'\n  Gate (Phase B): {"PASSED" if gate_passed else "FAILED"}')
        result_b = all_results.get('B')
        if result_b and result_b.metrics:
            p = result_b.metrics.get('permutation_p_value', '?')
            print(f'  Permutation p-value: {p}')

    # Final metrics (Phase F)
    result_f = all_results.get('F')
    if result_f and result_f.metrics:
        print(f'\n  Final Validation Metrics:')
        for k, v in result_f.metrics.items():
            if isinstance(v, float):
                print(f'    {k}: {v:.4f}')
            else:
                print(f'    {k}: {v}')

    # Total elapsed
    total_elapsed = sum(r.elapsed for r in all_results.values())
    print(f'\n  Total elapsed: {total_elapsed:.0f}s ({total_elapsed / 60:.1f} min)')

    # Save summary to JSON
    summary_path = os.path.join(RESULTS_DIR, 'pipeline_summary.json')
    os.makedirs(RESULTS_DIR, exist_ok=True)
    summary = {
        'timestamp': _ts(),
        'gate_passed': gate_passed,
        'total_elapsed_seconds': round(total_elapsed, 1),
        'phases': {p: r.to_dict() for p, r in all_results.items()},
    }
    try:
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        log(f'Summary saved to {summary_path}')
    except Exception as e:
        log(f'Failed to save summary: {e}', level='WARN')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Phase 2 Pipeline Orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--phase', type=str, default='all',
        help='Which phase(s) to run. Options: A, B, C, D, E, F, all, '
             'or comma-separated like C,D,E. Default: all',
    )
    parser.add_argument(
        '--skip-gate', action='store_true',
        help='Force continue past Phase B gate even if permutation test fails.',
    )
    parser.add_argument(
        '--timeout', type=int, default=7200,
        help='Max seconds per phase script (default: 7200 = 2 hours).',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    log_header('PHASE 2 PIPELINE — Grid Tail Risk Mitigation')
    log(f'Python: {PYTHON}')
    log(f'Working dir: {PHASE2_DIR}')
    log(f'Phase(s): {args.phase}')
    log(f'Skip gate: {args.skip_gate}')
    log(f'Timeout: {args.timeout}s per phase')

    all_results: Dict[str, PhaseResult] = {}
    gate_passed: Optional[bool] = None

    # Determine which phases to run
    if args.phase.lower() == 'all':
        phases_requested = list('ABCDEF')
    else:
        phases_requested = [p.strip().upper() for p in args.phase.split(',')]

    # Validate
    for p in phases_requested:
        if p not in PHASE_SCRIPTS:
            log(f'Unknown phase: {p}. Valid: A, B, C, D, E, F, all', level='ERROR')
            sys.exit(1)

    # ------------------------------------------------------------------
    # Execute phases respecting the dependency graph:
    #   A -> B -> [C, D, E] (parallel) -> F
    # ------------------------------------------------------------------

    # If running 'all', enforce the full pipeline order
    if args.phase.lower() == 'all':
        # Phase A
        result_a = run_phase('A', timeout=args.timeout)
        all_results['A'] = result_a

        if not result_a.success:
            log('Phase A failed. Attempting to continue ...', level='WARN')

        # Phase B
        result_b = run_phase('B', timeout=args.timeout)
        all_results['B'] = result_b

        # Gate check
        gate_passed = check_gate(result_b, args.skip_gate)

        if not gate_passed:
            log('Pipeline stopped at Phase B gate.')
            print_summary(all_results, gate_passed)
            sys.exit(0 if result_b.success else 1)

        # Phases C, D, E in parallel
        parallel_phases = ['C', 'D', 'E']
        parallel_results = run_phases_parallel(parallel_phases, timeout=args.timeout)
        all_results.update(parallel_results)

        # Check if at least some parallel phases succeeded
        any_parallel_ok = any(r.success for r in parallel_results.values())
        if not any_parallel_ok:
            log('All parallel phases (C, D, E) failed. '
                'Attempting Phase F anyway ...', level='WARN')

        # Phase F
        result_f = run_phase('F', timeout=args.timeout)
        all_results['F'] = result_f

    else:
        # Running specific phases — respect dependencies where obvious
        for phase in phases_requested:
            if phase in ('C', 'D', 'E'):
                # These can run in parallel if multiple requested
                continue  # handled below
            result = run_phase(phase, timeout=args.timeout)
            all_results[phase] = result

            # Gate check after B
            if phase == 'B':
                gate_passed = check_gate(result, args.skip_gate)
                if not gate_passed and not args.skip_gate:
                    log('Pipeline stopped at Phase B gate.')
                    break

        # Run C, D, E in parallel if any were requested
        parallel_requested = [p for p in phases_requested if p in ('C', 'D', 'E')]
        if parallel_requested:
            if len(parallel_requested) > 1:
                parallel_results = run_phases_parallel(
                    parallel_requested, timeout=args.timeout
                )
                all_results.update(parallel_results)
            else:
                r = run_phase(parallel_requested[0], timeout=args.timeout)
                all_results[parallel_requested[0]] = r

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print_summary(all_results, gate_passed)

    # Exit code: 0 if all requested phases succeeded
    all_ok = all(r.success for r in all_results.values() if r.error_msg != 'Script not found')
    # Treat "not found" as non-fatal (scripts not yet written)
    sys.exit(0 if all_ok or all(
        'not found' in r.error_msg or 'Not found' in r.error_msg or r.success
        for r in all_results.values()
    ) else 1)


if __name__ == '__main__':
    main()
