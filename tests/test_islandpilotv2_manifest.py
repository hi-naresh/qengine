import json
import gzip
import multiprocessing as mp
from pathlib import Path
import pytest
from pipelines._shared.IslandPilotV2 import manifest


@pytest.fixture(autouse=True)
def reset_manifest():
    """Reset module-level state between tests."""
    manifest._reset_for_tests()
    yield
    manifest._reset_for_tests()


def test_record_is_noop_when_closed(tmp_path):
    # No exception, no file created
    manifest.record("test_event", value=1)
    assert not (tmp_path / "manifest.jsonl").exists()


def test_open_creates_file_and_writes_header(tmp_path):
    p = tmp_path / "m.jsonl"
    manifest.open(p)
    manifest.close()
    # After close, file is gzipped
    assert (tmp_path / "m.jsonl.gz").exists()
    with gzip.open(tmp_path / "m.jsonl.gz", "rt") as f:
        first = json.loads(f.readline())
    assert first["event"] == "_header"
    assert first["schema_version"] == 1


def test_record_appends_event(tmp_path):
    manifest.open(tmp_path / "m.jsonl")
    manifest.record("apply_genome", regime="r1", genes_applied={"x": 1})
    manifest.close()
    with gzip.open(tmp_path / "m.jsonl.gz", "rt") as f:
        lines = [json.loads(l) for l in f if l.strip()]
    events = [e for e in lines if e["event"] == "apply_genome"]
    assert len(events) == 1
    assert events[0]["regime"] == "r1"
    assert events[0]["genes_applied"] == {"x": 1}
    assert "ts" in events[0]


def test_tap_receives_events(tmp_path):
    manifest.open(tmp_path / "m.jsonl")
    captured = []
    manifest.tap(captured.append)
    manifest.record("e1", x=1)
    manifest.record("e2", y=2)
    manifest.close()
    types = [e["event"] for e in captured]
    assert "e1" in types
    assert "e2" in types


def test_untap_stops_subscription(tmp_path):
    manifest.open(tmp_path / "m.jsonl")
    captured = []
    manifest.tap(captured.append)
    manifest.record("e1", x=1)
    manifest.untap()
    manifest.record("e2", y=2)
    manifest.close()
    types = [e["event"] for e in captured]
    assert "e1" in types
    assert "e2" not in types


def test_double_close_is_idempotent(tmp_path):
    manifest.open(tmp_path / "m.jsonl")
    manifest.close()
    manifest.close()  # must not raise


def test_reopen_writes_session_restart_to_new_file(tmp_path):
    p1 = tmp_path / "first.jsonl"
    p2 = tmp_path / "second.jsonl"
    manifest.open(p1)
    manifest.record("e1", x=1)
    # Re-open without explicit close
    manifest.open(p2)
    manifest.record("e2", y=2)
    manifest.close()
    # The first file should be gzipped (closed by the re-open) and NOT contain _session_restart
    with gzip.open(tmp_path / "first.jsonl.gz", "rt") as f:
        first_events = [json.loads(l) for l in f if l.strip()]
    assert all(e["event"] != "_session_restart" for e in first_events), \
        "_session_restart should NOT appear in prior file"
    # The second (new) file should contain _session_restart with prior_path
    with gzip.open(tmp_path / "second.jsonl.gz", "rt") as f:
        second_events = [json.loads(l) for l in f if l.strip()]
    restarts = [e for e in second_events if e["event"] == "_session_restart"]
    assert len(restarts) == 1
    assert "first.jsonl" in restarts[0]["prior_path"]


def test_worker_buffer_collects_records(tmp_path):
    manifest.open(tmp_path / "m.jsonl")
    manifest.start_worker_buffer()
    manifest.record("apply_genome", regime="r1", genes_applied={})
    manifest.record("cycle_complete", regime="r1", pnl=1.0)
    events = manifest.drain_worker_buffer()
    assert len(events) == 2
    assert events[0]["event"] == "apply_genome"
    assert events[1]["event"] == "cycle_complete"


def test_worker_buffer_drain_clears(tmp_path):
    manifest.open(tmp_path / "m.jsonl")
    manifest.start_worker_buffer()
    manifest.record("e1")
    first = manifest.drain_worker_buffer()
    assert len(first) == 1
    second = manifest.drain_worker_buffer()
    # After drain, buffer is None (worker context ended); subsequent record
    # would no-op or write to file. We expect drain to return [] on a
    # second call since the buffer is no longer active.
    assert second == []


def test_merge_worker_events_writes_to_parent(tmp_path):
    manifest.open(tmp_path / "m.jsonl")
    manifest.merge_worker_events([
        {"event": "apply_genome", "ts": "2026-01-01T00:00:00Z", "regime": "r1"},
        {"event": "cycle_complete", "ts": "2026-01-01T00:00:01Z", "regime": "r1"},
    ])
    manifest.close()
    with gzip.open(tmp_path / "m.jsonl.gz", "rt") as f:
        events = [json.loads(l) for l in f if l.strip()]
    types = [e["event"] for e in events]
    assert "apply_genome" in types
    assert "cycle_complete" in types


def _worker_fn(_unused):
    """Module-level worker for pickle compat."""
    manifest.start_worker_buffer()
    manifest.record("apply_genome", regime="r1", genes_applied={"k": 1})
    return manifest.drain_worker_buffer()


def test_pool_round_trip(tmp_path):
    """Worker emits events; parent merges them; final manifest contains them."""
    manifest.open(tmp_path / "m.jsonl")
    ctx = mp.get_context("fork")
    with ctx.Pool(processes=2) as pool:
        results = pool.map(_worker_fn, [0, 1])
    for events in results:
        manifest.merge_worker_events(events)
    manifest.close()
    with gzip.open(tmp_path / "m.jsonl.gz", "rt") as f:
        lines = [json.loads(l) for l in f if l.strip()]
    apply_events = [l for l in lines if l["event"] == "apply_genome"]
    assert len(apply_events) == 2  # one per worker


def test_worker_buffer_caps_at_100k(tmp_path):
    manifest.open(tmp_path / "m.jsonl")
    manifest.start_worker_buffer()
    for i in range(100_001):
        manifest.record("evt", i=i)
    events = manifest.drain_worker_buffer()
    assert len(events) == 100_000
