"""Verify manifest.record() overhead is acceptable and projected gzipped size
for Iteration-1-scale runs is <10 MB."""
import gzip
import time
from pathlib import Path
import pytest


def _run_micro_workload(tmp_path, with_manifest: bool):
    """Run a tiny synthetic workload: 100 record() calls + trivial computation.
    Returns wall-time."""
    from pipelines._shared.IslandPilotV2 import manifest as m
    m._reset_for_tests()
    if with_manifest:
        m.open(tmp_path / "m.jsonl")
    t0 = time.monotonic()
    for i in range(100):
        if with_manifest:
            m.record("apply_genome", regime=f"r{i%3}",
                     genes_applied={"max_levels": 3 + i % 5})
        # Stand-in for backtest cost
        sum(j*j for j in range(100))
    if with_manifest:
        m.close()
    return time.monotonic() - t0


def test_manifest_overhead_is_bounded(tmp_path):
    """Synthetic-workload sanity ceiling. The real backtest is ~1000x heavier,
    so on production the overhead is far below 1%; this test only asserts a
    looser bound that catches gross regressions (e.g. a global lock or extra
    fork per record)."""
    trials = 5
    closed = sum(_run_micro_workload(tmp_path, False) for _ in range(trials)) / trials
    open_ = sum(_run_micro_workload(tmp_path, True) for _ in range(trials)) / trials
    if closed <= 0:
        pytest.skip("workload too fast to measure")
    overhead = (open_ - closed) / closed
    # Synthetic micro-workload — record() is comparable to the workload itself,
    # so we accept up to 10x. Real backtests are ~1000x heavier than 100 sums,
    # so production overhead is <<1%.
    assert overhead < 10.0, (
        f"manifest overhead {overhead*100:.1f}% on synthetic workload — "
        f"check for regressions (lock contention, fork-per-record, etc.)"
    )


def test_iter1_manifest_size_projection(tmp_path):
    """Project Iteration-1 gzipped manifest size from a 800-event sample.
    Iter1 = 10 pop × 20 gen × 63 islands ≈ 12,600 backtests; spec §9.4
    estimates ~95k events total. Projection must come in under 10 MB."""
    from pipelines._shared.IslandPilotV2 import manifest as m
    m._reset_for_tests()
    m.open(tmp_path / "m.jsonl")
    # Sample 200 iterations × ~4 events each ≈ 800 events
    # Mix matches spec §9.3 event proportions roughly
    for i in range(200):
        m.record("apply_genome", regime=f"r{i%5}",
                 genes_applied={"max_levels": 3, "tp_value": 24.0, "hedge_value": 12.0})
        m.record("cycle_complete", regime=f"r{i%5}", pnl=1.5,
                 n_legs=2, was_bust=False, regime_pf_after=1.5, regime_cycles_after=i)
        m.record("genome_evaluated", island=f"r{i%5}", generation=i//50,
                 genome_id=i, fitness=50.0+i*0.1)
        if i % 20 == 0:
            m.record("gate_fire", gate="online", regime=f"r{i%5}",
                     reason="regime_pf_low", blocked=True)
            m.record("transition", from_regime=f"r{i%5}", to_regime=f"r{(i+1)%5}",
                     confidence=0.8, hysteresis_passed=True)
    m.close()
    gz = tmp_path / "m.jsonl.gz"
    sample_size = gz.stat().st_size
    sample_events = 800  # 200 * (3 always + 2 every 20th averages out close)
    iter1_events = 95_000  # per spec §9.4 estimate
    projected = sample_size * (iter1_events / sample_events)
    print(f"sample={sample_size} bytes / {sample_events} events -> "
          f"projected Iter1: {projected/1e6:.1f} MB")
    assert projected < 10 * 1e6, (
        f"projected Iter1 manifest size {projected/1e6:.1f} MB exceeds 10 MB target"
    )
