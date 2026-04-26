import pytest
from pipelines._shared.IslandPilotV2 import preflight_checks as pc


def test_check_decorator_registers():
    pc._registry.clear()

    @pc.check(id="X01_demo", category="demo", source=["unit"], severity="warn",
              description="demo")
    def check_demo(ctx):
        return pc.CheckResult.pass_("ok")

    assert "X01_demo" in pc._registry


def test_check_result_pass_factory():
    r = pc.CheckResult.pass_("looks good", evidence={"k": 1})
    assert r.status == "pass"
    assert r.message == "looks good"
    assert r.evidence == {"k": 1}


def test_check_result_fail_factory():
    r = pc.CheckResult.fail("broken")
    assert r.status == "fail"


def test_check_context_events_of_type():
    ctx = pc.CheckContext(
        events=[
            {"event": "apply_genome", "regime": "r1"},
            {"event": "cycle_complete", "regime": "r1"},
            {"event": "apply_genome", "regime": "r2"},
        ],
        artifacts={},
        config={},
        available_sources={"runtime"},
    )
    apg = ctx.events_of_type("apply_genome")
    assert len(apg) == 2
    assert all(e["event"] == "apply_genome" for e in apg)


def test_runner_invokes_check_and_stamps_metadata():
    pc._registry.clear()

    @pc.check(id="X02_meta", category="demo", source=["unit"], severity="critical",
              description="metadata test")
    def check_x02(ctx):
        return pc.CheckResult.pass_("ok")

    ctx = pc.CheckContext(events=[], artifacts={}, config={},
                          available_sources={"unit"})
    results = pc.run_registered_checks(ctx)
    assert len(results) == 1
    r = results[0]
    assert r.id == "X02_meta"
    assert r.category == "demo"
    assert r.severity == "critical"
    assert r.sources_run == ["unit"]


def test_runner_skips_checks_without_matching_source():
    pc._registry.clear()

    @pc.check(id="X03_artifact_only", category="demo", source=["artifact"],
              severity="warn", description="artifact only")
    def check_x03(ctx):
        return pc.CheckResult.pass_("ok")

    ctx = pc.CheckContext(events=[], artifacts={}, config={},
                          available_sources={"unit"})  # no artifact
    results = pc.run_registered_checks(ctx)
    assert len(results) == 1
    assert results[0].status == "skip"


def test_runner_catches_check_exception_as_fail():
    pc._registry.clear()

    @pc.check(id="X04_buggy", category="demo", source=["unit"], severity="warn",
              description="buggy")
    def check_x04(ctx):
        raise ValueError("oops")

    ctx = pc.CheckContext(events=[], artifacts={}, config={},
                          available_sources={"unit"})
    results = pc.run_registered_checks(ctx)
    assert results[0].status == "fail"
    assert "ValueError" in results[0].message
    assert "oops" in results[0].message
