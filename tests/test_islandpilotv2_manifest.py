import json
import gzip
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
