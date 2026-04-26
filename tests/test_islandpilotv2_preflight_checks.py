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


# ===== Regime category meta-tests (R01–R06) =================================

def _make_ctx(events=None, artifacts=None, config=None, sources=None):
    return pc.CheckContext(
        events=events or [],
        artifacts=artifacts or {},
        config=config or {},
        available_sources=sources or {"runtime", "manifest", "artifact", "unit"},
    )


def test_R01_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_R01_partition_min_features as fn
    ctx = _make_ctx(events=[{"event": "feature_partition",
                             "n_macro_feats": 5, "n_sub_feats": 3}])
    assert fn(ctx).status == "pass"


def test_R01_fail():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_R01_partition_min_features as fn
    ctx = _make_ctx(events=[{"event": "feature_partition",
                             "n_macro_feats": 1, "n_sub_feats": 0}])
    assert fn(ctx).status == "fail"


def test_R02_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_R02_partition_threshold_path as fn
    ctx = _make_ctx(events=[{"event": "feature_partition",
                             "n_macro_feats": 5, "n_sub_feats": 3,
                             "autocorr_threshold": 0.7}])
    assert fn(ctx).status in ("pass", "warn")


def test_R02_fail_no_event():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_R02_partition_threshold_path as fn
    ctx = _make_ctx(events=[])
    assert fn(ctx).status == "fail"


def test_R03_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_R03_gmm_min_leaves as fn
    ctx = _make_ctx(events=[{"event": "regime_fit",
                             "n_macro_clusters": 3, "leaves_before_merge": 6,
                             "leaves_after_merge": 5}])
    assert fn(ctx).status == "pass"


def test_R03_fail():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_R03_gmm_min_leaves as fn
    ctx = _make_ctx(events=[{"event": "regime_fit",
                             "n_macro_clusters": 1, "leaves_before_merge": 1,
                             "leaves_after_merge": 1}])
    assert fn(ctx).status == "fail"


def test_R04_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_R04_sparse_merge_fired as fn
    ctx = _make_ctx(events=[{"event": "regime_fit",
                             "leaves_before_merge": 8, "leaves_after_merge": 5}])
    assert fn(ctx).status == "pass"


def test_R04_warn_no_merge():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_R04_sparse_merge_fired as fn
    ctx = _make_ctx(events=[{"event": "regime_fit",
                             "leaves_before_merge": 5, "leaves_after_merge": 5}])
    assert fn(ctx).status in ("pass", "warn")


def test_R05_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_R05_hysteresis_prevents_whipsaw as fn
    ctx = _make_ctx(events=[
        {"event": "transition", "from_regime": "a", "to_regime": "b", "hysteresis_passed": True},
        {"event": "transition", "from_regime": "b", "to_regime": "b", "hysteresis_passed": False},  # blocked
    ])
    assert fn(ctx).status == "pass"


def test_R05_warn_no_blocks():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_R05_hysteresis_prevents_whipsaw as fn
    ctx = _make_ctx(events=[
        {"event": "transition", "from_regime": "a", "to_regime": "b", "hysteresis_passed": True},
    ])
    assert fn(ctx).status in ("pass", "warn")


def test_R06_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_R06_grace_candles_unit as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status in ("pass", "warn", "skip")
