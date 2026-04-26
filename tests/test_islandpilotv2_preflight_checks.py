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


# ===== Evolver category meta-tests (E01–E09) ===============================

def _seed_gene_to_group():
    """Populate _GENE_TO_GROUP with known mappings so E01/E05 can resolve genes."""
    from pipelines._shared.IslandPilotV2 import island_evolver as ie
    ie._GENE_TO_GROUP.update({
        "max_levels": "General",
        "hedge_value": "Grid / Hedge",
        "tp_value": "Take Profit",
    })


def test_E01_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E01_bounds_cover_groups as fn
    _seed_gene_to_group()
    ctx = _make_ctx(
        artifacts={"training_config.json": {
            "tunable_groups_snapshot": ["General", "Grid / Hedge", "Take Profit"],
            "evolved_gene_names": ["max_levels", "hedge_value", "tp_value"],
        }},
        sources={"artifact"},
    )
    assert fn(ctx).status == "pass"


def test_E01_fail_missing_group():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E01_bounds_cover_groups as fn
    _seed_gene_to_group()
    ctx = _make_ctx(
        artifacts={"training_config.json": {
            "tunable_groups_snapshot": ["General", "Grid / Hedge", "Take Profit"],
            "evolved_gene_names": ["max_levels"],  # only General covered
        }},
        sources={"artifact"},
    )
    assert fn(ctx).status == "fail"


def test_E02_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E02_skip_params_documented as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status in ("pass", "warn")


def test_E03_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E03_initial_pop_variance as fn
    ctx = _make_ctx(events=[
        {"event": "apply_genome", "genes_applied": {"max_levels": 3}},
        {"event": "apply_genome", "genes_applied": {"max_levels": 5}},
        {"event": "apply_genome", "genes_applied": {"max_levels": 7}},
    ])
    assert fn(ctx).status == "pass"


def test_E03_fail_no_variance():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E03_initial_pop_variance as fn
    ctx = _make_ctx(events=[
        {"event": "apply_genome", "genes_applied": {"max_levels": 3}},
        {"event": "apply_genome", "genes_applied": {"max_levels": 3}},
        {"event": "apply_genome", "genes_applied": {"max_levels": 3}},
    ])
    assert fn(ctx).status == "fail"


def test_E04_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E04_mutation_propagates as fn
    ctx = _make_ctx(events=[
        {"event": "genome_evaluated", "generation": 0, "fitness": 50.0},
        {"event": "genome_evaluated", "generation": 1, "fitness": 60.0},
    ])
    assert fn(ctx).status == "pass"


def test_E04_fail_no_gen_progress():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E04_mutation_propagates as fn
    ctx = _make_ctx(events=[
        {"event": "genome_evaluated", "generation": 0, "fitness": 50.0},
    ])
    assert fn(ctx).status == "fail"


def test_E05_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E05_intended_groups_mutate as fn
    _seed_gene_to_group()
    ctx = _make_ctx(
        events=[{"event": "apply_genome",
                 "genes_applied": {"max_levels": 3, "tp_value": 24.0}}],
        artifacts={"training_config.json": {
            "tunable_groups_snapshot": ["General", "Take Profit"],
            "evolved_gene_names": ["max_levels", "tp_value"],
        }},
    )
    assert fn(ctx).status == "pass"


def test_E05_fail_silent_group():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E05_intended_groups_mutate as fn
    _seed_gene_to_group()
    ctx = _make_ctx(
        events=[{"event": "apply_genome",
                 "genes_applied": {"max_levels": 3}}],  # tp_value missing
        artifacts={"training_config.json": {
            "tunable_groups_snapshot": ["General", "Take Profit"],
            "evolved_gene_names": ["max_levels", "tp_value"],
        }},
    )
    assert fn(ctx).status == "fail"


def test_E06_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E06_feasibility_corrections as fn
    ctx = _make_ctx(events=[
        {"event": "feasibility_correction", "gene": "tp_value",
         "original": 5, "corrected": 12, "reason": "tp < hedge*1.5"},
    ])
    assert fn(ctx).status == "pass"


def test_E06_warn_no_corrections():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E06_feasibility_corrections as fn
    ctx = _make_ctx(events=[])
    assert fn(ctx).status in ("pass", "warn")


def test_E07_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E07_categorical_round_trip as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status in ("pass", "skip")


def test_E08_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E08_multiproc_pickling as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status in ("pass", "skip")


def test_E09_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_E09_audit_skip_params_inventory as fn
    ctx = _make_ctx(sources={"artifact"})
    assert fn(ctx).status in ("pass", "skip")


def test_A01_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_A01_apply_genome_reads_groups as fn
    ctx = _make_ctx(events=[
        {"event": "apply_genome",
         "genes_applied": {"max_levels": 3, "tp_value": 24.0, "hedge_value": 12.0}},
    ])
    assert fn(ctx).status == "pass"


def test_A01_fail_no_apply_events():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_A01_apply_genome_reads_groups as fn
    ctx = _make_ctx(events=[])
    assert fn(ctx).status == "fail"


def test_A02_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_A02_mode_aware_coercion as fn
    ctx = _make_ctx(events=[
        {"event": "apply_genome",
         "genes_applied": {"tp_mode": "fixed_pips", "tp_value": 24.0}},
        {"event": "apply_genome",
         "genes_applied": {"tp_mode": "atr_based", "tp_value": 1.5}},
    ])
    assert fn(ctx).status in ("pass", "warn")


def test_A03_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_A03_every_leaf_has_best_genome as fn
    ctx = _make_ctx(
        artifacts={"island_evolver.json": {
            "populations": {
                "macro1_sub1": {"best_genome_id": 5, "individuals": [{"id": 5, "fitness": 60.0, "genes": {"x": 1}}]},
                "macro2_sub1": {"best_genome_id": 3, "individuals": [{"id": 3, "fitness": 55.0, "genes": {"x": 2}}]},
            }
        }},
        sources={"artifact"},
    )
    assert fn(ctx).status == "pass"


def test_A03_fail_missing_best():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_A03_every_leaf_has_best_genome as fn
    ctx = _make_ctx(
        artifacts={"island_evolver.json": {
            "populations": {
                "macro1_sub1": {"best_genome_id": None, "individuals": []},
            }
        }},
        sources={"artifact"},
    )
    assert fn(ctx).status == "fail"


def test_A04_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_A04_hp_spec_round_trip as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status in ("pass", "warn", "skip")


def test_G01_pass_force_trigger():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_G01_online_gate as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status in ("pass", "skip")


def test_G02_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_G02_drift_gate as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status in ("pass", "skip")


def test_G03_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_G03_unknown_regime_gate as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status in ("pass", "skip")


def test_G04_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_G04_proven_fitness_gate as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status in ("pass", "skip")


def test_G05_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_G05_abort_volatility as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status == "pass"


def test_G06_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_G06_session_halt as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status == "pass"


def test_G01_manifest_path():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_G01_online_gate as fn
    ctx = _make_ctx(
        events=[{"event": "gate_fire", "gate": "online", "blocked": True}],
        sources={"manifest"},
    )
    assert fn(ctx).status == "pass"


# ===== Migration / Outcomes / Roundtrip meta-tests (M, O, V) ===============

def test_M01_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_M01_acceptance_ratio as fn
    ctx = _make_ctx(events=[
        {"event": "migration", "donor_island": "a", "recipient_island": "b", "accepted": True},
        {"event": "migration", "donor_island": "b", "recipient_island": "c", "accepted": False},
        {"event": "migration", "donor_island": "c", "recipient_island": "a", "accepted": True},
    ])
    assert fn(ctx).status == "pass"


def test_M01_warn_no_accepts():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_M01_acceptance_ratio as fn
    ctx = _make_ctx(events=[
        {"event": "migration", "donor_island": "a", "recipient_island": "b", "accepted": False},
    ])
    assert fn(ctx).status in ("warn", "fail")


def test_M02_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_M02_migration_interval as fn
    ctx = _make_ctx(events=[
        {"event": "migration", "accepted": True},
        {"event": "genome_evaluated", "generation": 0},
        {"event": "genome_evaluated", "generation": 1},
        {"event": "migration", "accepted": True},
    ])
    assert fn(ctx).status in ("pass", "warn")


def test_O01_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_O01_three_regimes_with_cycles as fn
    ctx = _make_ctx(events=[
        {"event": "cycle_complete", "regime": "r1"},
        {"event": "cycle_complete", "regime": "r2"},
        {"event": "cycle_complete", "regime": "r3"},
    ])
    assert fn(ctx).status == "pass"


def test_O01_fail():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_O01_three_regimes_with_cycles as fn
    ctx = _make_ctx(events=[{"event": "cycle_complete", "regime": "r1"}])
    assert fn(ctx).status == "fail"


def test_O02_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_O02_fitness_dispersion as fn
    ctx = _make_ctx(events=[
        {"event": "genome_evaluated", "fitness": 50.0},
        {"event": "genome_evaluated", "fitness": 60.0},
        {"event": "genome_evaluated", "fitness": 55.0},
    ])
    assert fn(ctx).status == "pass"


def test_O02_fail_zero_dispersion():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_O02_fitness_dispersion as fn
    ctx = _make_ctx(events=[
        {"event": "genome_evaluated", "fitness": 0.0},
        {"event": "genome_evaluated", "fitness": 0.0},
    ])
    assert fn(ctx).status == "fail"


def test_O03_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_O03_per_regime_stats_increment as fn
    ctx = _make_ctx(events=[
        {"event": "cycle_complete", "regime": "r1", "regime_cycles_after": 1},
        {"event": "cycle_complete", "regime": "r1", "regime_cycles_after": 2},
    ])
    assert fn(ctx).status == "pass"


def test_O04_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_O04_recent_pnls_window as fn
    ctx = _make_ctx(events=[{"event": "cycle_complete", "regime": "r1", "pnl": 5.0}])
    assert fn(ctx).status in ("pass", "warn")


def test_V01_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_V01_artifacts_load_clean as fn
    ctx = _make_ctx(
        artifacts={
            "regime_tree.pkl": {},
            "island_evolver.json": {"populations": {}},
            "leaf_date_ranges.json": {},
        },
        sources={"artifact"},
    )
    assert fn(ctx).status == "pass"


def test_V01_fail_missing():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_V01_artifacts_load_clean as fn
    ctx = _make_ctx(artifacts={"regime_tree.pkl": None}, sources={"artifact"})
    assert fn(ctx).status == "fail"


def test_V02_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_V02_validate_model_runs_oos as fn
    ctx = _make_ctx(sources={"runtime"})
    assert fn(ctx).status in ("pass", "warn", "skip")


def test_V03_pass():
    from pipelines._shared.IslandPilotV2.preflight_checks import check_V03_manifest_gzip_round_trip as fn
    ctx = _make_ctx(sources={"unit"})
    assert fn(ctx).status == "pass"
