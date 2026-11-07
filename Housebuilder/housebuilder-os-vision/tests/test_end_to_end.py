"""End-to-end tests: image -> analysis -> calibration -> hypotheses -> twin -> quantities -> cost ->
simulations -> scenarios -> repeat build -> exports, on the fictional bundled demo."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import numpy as np
import pytest

import housebuilder_vision
from housebuilder_vision import pipeline as P
from housebuilder_vision.core.models import (
    ImageKind,
    QuantityStatus,
    RunRecord,
    SimulationConfig,
    TwinEdit,
    ViewDirection,
)
from housebuilder_vision.core.provenance import Basis
from housebuilder_vision.demo.build_demo import (
    FRONTAGE_M,
    REFERENCE_DESCRIPTION,
    build_demo_project,
    build_uncalibrated_demo_project,
)
from housebuilder_vision.demo.run_demo import main as demo_main
from housebuilder_vision.io.ifc_adapter import ifc_available
from housebuilder_vision.twin import apply_twin_edit

HEX64 = re.compile(r"^[0-9a-f]{64}$")


# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    store = tmp_path_factory.mktemp("store")
    out = tmp_path_factory.mktemp("exports")
    project = build_demo_project(store)
    result = P.run_pipeline(project, store_dir=store, simulate=True, n_samples=60, scenario_samples=30)
    manifest = P.export_project(project, out, boq=result.boq, estimate=result.estimate,
                                simulation=result.simulation, repeat=result.repeat_results(),
                                comparison=result.comparison, library=project.library, rate_book=project.rate_book,
                                run_log=project)
    return project, result, manifest, out


@pytest.fixture(scope="module")
def uncal(tmp_path_factory):
    return build_uncalibrated_demo_project(tmp_path_factory.mktemp("uncal"))


@pytest.fixture(scope="module")
def side(tmp_path_factory):
    return build_demo_project(tmp_path_factory.mktemp("side"), include_side_view=True)


def simulate(project, n=150, seed=20261107, **kw):
    return P.simulate_uncertainty(project.twin, project.library, project.rate_book, project.cost_parameters,
                                  project.settings, config=SimulationConfig(n_samples=n, seed=seed, **kw),
                                  calibration=project.calibration, assumptions=project.assumptions)


def metric(sim, name):
    return next(m for m in sim.metrics if m.metric == name)


def construction(estimate):
    return estimate.boundary("construction_incl_contingency").amount


# =============================================================================
# Full path
# =============================================================================
def test_full_path_from_image_to_exports(demo):
    project, result, manifest, out = demo
    assert len(project.images) == 1
    img = project.images[0]
    assert img.kind == ImageKind.ELEVATION_DRAWING and img.view == ViewDirection.FRONT
    assert {f.block_hint for f in result.analysis.facades} == {"main", "garage"}
    assert result.calibration.method == "reference_measurement"
    assert result.calibration.reference.real_length == FRONTAGE_M
    assert result.calibration.reference.description == REFERENCE_DESCRIPTION
    assert [h.hypothesis_id for h in result.hypotheses] == ["H-A", "H-B"]
    assert result.selected_hypothesis_id == "H-A" and result.twin.source_hypothesis_id == "H-A"
    assert project.twin is result.twin and project.analysis is result.analysis
    assert result.boq.twin_id == result.twin.twin_id
    assert result.programme.duration_weeks > 0 and result.logistics.total_loads > 0
    assert result.carbon.total_kgco2e > 0 and result.heat_loss.heat_loss_coefficient_w_k > 0
    assert result.estimate.programme_weeks == pytest.approx(result.programme.duration_weeks)
    assert result.simulation is not None and result.simulation.n_samples == 60
    paths = {f.path for f in manifest.files}
    for name in ("project.json", "results.json", "twin.glb", "quantities.csv", "costs.csv", "cost_boundaries.csv",
                 "repeat_build.csv", "simulation_summary.csv", "scenario_comparison.csv", "README.txt"):
        assert name in paths, name
    assert ("twin.ifc" in paths) == ifc_available()
    assert manifest.verify(out) == []
    saved = json.loads((Path(out) / "project.json").read_text(encoding="utf-8"))
    assert saved["twin"]["twin_id"] == result.twin.twin_id
    # the pipeline result is serialisable and round-trips
    again = P.PipelineResult.model_validate_json(result.model_dump_json())
    assert construction(again.estimate) == pytest.approx(construction(result.estimate))


def test_calibrated_main_width_is_user_confirmed(demo):
    _, result, _, _ = demo
    w = result.twin.block("main").width
    assert w.basis == Basis.USER_CONFIRMED and w.value == pytest.approx(FRONTAGE_M)
    assert (w.low, w.high) == pytest.approx((9.58, 9.62))
    # the hidden depth stays an assumption, the garage depth too
    assert result.twin.block("main").depth.basis == Basis.ASSUMED
    assert result.twin.block("garage").depth.basis == Basis.ASSUMED
    # appearance never sets structure: assemblies are assumed library defaults
    sel = result.twin.assemblies
    assert sel.basis["external_wall"] == Basis.ASSUMED and sel.external_wall == "ew_masonry_cavity"


def test_every_boq_line_is_traceable(demo):
    _, result, _, _ = demo
    boq, est = result.boq, result.estimate
    ids = [ln.line_id for ln in boq.lines]
    assert len(ids) == len(set(ids))
    for ln in boq.lines:
        assert ln.trace, ln.line_id
        assert ln.formula and ln.description, ln.line_id
        assert isinstance(ln.basis, Basis)
        if ln.status == QuantityStatus.DERIVED:
            assert ln.geometry_refs or any(t.kind == "geometry" for t in ln.trace), ln.line_id
    by_id = set(ids)
    priced = {cl.quantity_line_id for cl in est.lines if cl.quantity_line_id}
    assert priced <= by_id
    for ln in boq.lines:
        if ln.cost_key and (ln.purchased_qty or ln.installed_qty):
            assert ln.line_id in priced, ln.line_id
    for cl in est.lines:
        assert cl.formula, cl.line_id


def test_demo_has_no_unresolved_or_missing_rate_items(demo):
    _, result, _, _ = demo
    assert result.boq.unresolved == []
    assert result.estimate.unresolved_items == []
    assert not any("missing rate" in w for w in result.warnings)
    assert any("FICTIONAL" in w for w in result.estimate.warnings)


def test_run_log_records_every_engine_call(demo):
    project, result, _, _ = demo
    functions = {r.function for r in project.run_log}
    for fn in P.ENGINE_FUNCTIONS:
        assert fn in functions, fn
    for fn in ("build_programme", "plan_deliveries", "embodied_carbon", "heat_loss"):
        assert fn in functions
    for r in project.run_log:
        assert HEX64.match(r.inputs_sha256) and HEX64.match(r.outputs_sha256)
        assert r.versions["housebuilder_vision"] == housebuilder_vision.__version__
        assert "model_schema" in r.versions and "python" in r.versions
    sim = next(r for r in project.run_log if r.function == "simulate_uncertainty")
    assert sim.seed == project.simulation_config.seed
    ana = next(r for r in project.run_log if r.function == "analyse_images")
    assert any(k.startswith("adapter:") for k in ana.versions)
    assert result.run_records and all(r in project.run_log for r in result.run_records)


def test_run_record_hashes_are_reproducible(demo):
    project, result, _, _ = demo
    log: list[RunRecord] = []
    for _ in range(2):
        P.calculate_quantities(result.twin, project.library, assumptions=project.assumptions, run_log=log)
    assert log[0].inputs_sha256 == log[1].inputs_sha256
    assert log[0].outputs_sha256 == log[1].outputs_sha256
    other = P.apply_construction_assemblies(result.twin, {"external_wall": "ew_timber_frame_clad"}, project.library,
                                            actor="scenario:test", run_log=log)
    P.calculate_quantities(other, project.library, assumptions=project.assumptions, run_log=log)
    assert log[-1].outputs_sha256 != log[0].outputs_sha256


# =============================================================================
# Scenarios and repeat build
# =============================================================================
def test_scenario_comparison_four_coherent_outcomes(demo):
    _, result, _, _ = demo
    comp = result.comparison
    assert comp is not None and [o.scenario_id for o in comp.outcomes] == ["S1", "S2", "S3", "S4"]
    o = {x.scenario_id: x for x in comp.outcomes}
    assert [o[s].hypothesis_id for s in ("S1", "S2", "S3", "S4")] == ["H-A", "H-A", "H-A", "H-B"]
    # S1 is the selected house itself: identical to the pipeline estimate (no averaging anywhere)
    assert o["S1"].construction_cost == pytest.approx(construction(result.estimate))
    assert o["S1"].gia_m2 == pytest.approx(result.boq.geometry.gia_m2)
    # timber frame vs masonry: wall thickness, GIA and carbon differ
    for tf in ("S2", "S3"):
        assert o[tf].external_wall_thickness_m != pytest.approx(o["S1"].external_wall_thickness_m, abs=1e-4)
        assert o[tf].gia_m2 != pytest.approx(o["S1"].gia_m2, abs=1e-3)
        assert o[tf].embodied_carbon_kgco2e != pytest.approx(o["S1"].embodied_carbon_kgco2e, rel=1e-3)
    assert o["S3"].external_wall_thickness_m < o["S1"].external_wall_thickness_m
    assert o["S3"].gia_m2 > o["S1"].gia_m2  # thinner walls, more internal area on the same footprint
    assert o["S4"].gia_m2 != pytest.approx(o["S1"].gia_m2)  # a different hidden footprint
    for x in comp.outcomes:
        assert x.cost_p10 is not None and x.cost_p10 <= x.cost_p50 <= x.cost_p90
        assert x.cost_per_m2_gia == pytest.approx(x.construction_cost / x.gia_m2)
        assert x.key_assumptions
    assert any("never averaged" in n for n in comp.notes)


def test_repeat_build_average_vs_incremental(demo):
    project, result, _, _ = demo
    assert set(result.repeat_build) == {"PS-site", "PS-offsite"}
    for sid, by_b in result.repeat_build.items():
        assert set(by_b) == set(P.REPEAT_BOUNDARIES)
        rb = by_b["installed"]
        assert rb.comparison_ns == [1, 10, 25, 50, 100]
        rows = {r.n: r for r in rb.rows}
        for n in range(1, max(rows)):
            assert rows[n].incremental_cost == pytest.approx(rows[n + 1].total_cost - rows[n].total_cost)
            assert rows[n].average_cost == pytest.approx(rows[n].total_cost / n)
        assert any(abs(rows[n].average_cost - rows[n].incremental_cost) > 1.0 for n in rb.comparison_ns)
    offsite = result.repeat_build["PS-offsite"]
    fg = {r.n: r for r in offsite["factory_gate"].rows}
    assert fg[1].total_cost > 0 and fg[1].average_cost > fg[100].average_cost  # set-up spread over volume
    ps = {p.scenario_id: p for p in project.production_scenarios}
    assert ps["PS-offsite"].method == "offsite_panelised" and ps["PS-offsite"].step_costs
    assert "FICTIONAL" in ps["PS-offsite"].name and "FICTIONAL" in ps["PS-site"].name


# =============================================================================
# Uncertainty behaviour on the demo
# =============================================================================
def test_simulation_reproducible_for_a_seed(demo):
    project, _, _, _ = demo
    a, b, c = simulate(project, n=30, seed=11), simulate(project, n=30, seed=11), simulate(project, n=30, seed=12)
    assert a.samples == b.samples
    assert a.samples["construction_incl_contingency"] != c.samples["construction_incl_contingency"]


def test_uncertainty_preserved_when_dimensions_are_missing(demo, uncal):
    cal_project = demo[0]
    w = uncal.twin.block("main").width
    assert uncal.calibration.method == "prior_cues"
    assert w.basis == Basis.ASSUMED and w.correlation_group and w.correlation_group.startswith("scale:")
    assert w.high / w.low > 1.15  # the assumed scale range is kept, not collapsed
    assert "H-C" in [h.hypothesis_id for h in uncal.hypotheses]
    s_unc, s_cal = simulate(uncal), simulate(cal_project)
    wu = metric(s_unc, "main.width_m")
    widths = np.array(s_unc.samples["main.width_m"])
    # triangular prior-cue range (8.71-10.63 m): P90/P10 ~ 1.12, sampled range > 1.15
    assert wu.p90 / wu.p10 > 1.10 and widths.max() / widths.min() > 1.15
    wc = metric(s_cal, "main.width_m")
    assert wc.p90 / wc.p10 < 1.01
    cv = lambda s: metric(s, "construction_incl_contingency").std / metric(s, "construction_incl_contingency").mean
    assert cv(s_unc) > cv(s_cal)
    share = {r["group"]: r["variance_share"] for r in s_unc.information_value}
    share_cal = {r["group"]: r["variance_share"] for r in s_cal.information_value}
    assert share["scale"] > share_cal["scale"]


def test_side_view_narrows_depth_uncertainty(demo, side):
    front = demo[0]
    d_front, d_side = front.twin.block("main").depth, side.twin.block("main").depth
    assert len(side.images) == 2 and side.images[1].view == ViewDirection.LEFT
    assert side.analysis.multiview is not None
    assert d_side.basis == Basis.INFERRED and d_side.value == pytest.approx(8.40, abs=0.15)
    assert (d_side.high - d_side.low) < 0.25 * (d_front.high - d_front.low)
    s_side, s_front = simulate(side, n=100), simulate(front, n=100)
    spread = lambda s: metric(s, "main.depth_m").p90 - metric(s, "main.depth_m").p10
    assert spread(s_side) < 0.25 * spread(s_front)
    assert metric(s_side, "gia_m2").std < metric(s_front, "gia_m2").std


# =============================================================================
# Pipeline behaviour and CLI
# =============================================================================
def test_pipeline_keeps_an_edited_twin(tmp_path):
    project = build_demo_project(tmp_path / "s")
    edited = apply_twin_edit(project.twin, TwinEdit(target_type="block", target_id="main", field="depth", value=8.4,
                                                    tolerance=0.05, reason="fictional measured depth"))
    project.twin = edited
    result = P.run_pipeline(project, store_dir=tmp_path / "s", simulate=False)
    assert result.twin.version == edited.version and result.twin.block("main").depth.basis == Basis.USER_CONFIRMED
    assert result.simulation is None and result.comparison is not None
    assert all(o.cost_p10 is None for o in result.comparison.outcomes)
    assert any("kept" in n for n in result.notes)


def test_pipeline_requires_evidence():
    from housebuilder_vision.core.models import Project

    with pytest.raises(ValueError):
        P.run_pipeline(Project(project_id="empty", name="empty"), store_dir=None, simulate=False)


def test_package_root_exports_pipeline():
    assert housebuilder_vision.__version__ == "0.1.0"
    for name in P.ENGINE_FUNCTIONS + ("run_pipeline", "run_digital_simulations"):
        assert callable(getattr(housebuilder_vision, name))
    with pytest.raises(AttributeError):
        getattr(housebuilder_vision, "no_such_function")


def test_run_demo_main_writes_exports(tmp_path):
    buf = io.StringIO()
    out = tmp_path / "demo"
    assert demo_main(["--out", str(out), "--samples", "20", "--formats", "json,csv,glb"], stream=buf) == 0
    text = buf.getvalue()
    for section in ("1. Evidence", "2. Calibration", "3. Geometry hypotheses", "6. Cost boundaries",
                    "7. Uncertainty", "next-best evidence", "8. Build scenarios", "9. Repeat build", "10. Exports"):
        assert section in text, section
    assert "FICTIONAL" in text
    for name in ("project.json", "results.json", "quantities.csv", "twin.glb", "manifest.json"):
        assert (out / name).exists(), name
    assert (out / "source_images").is_dir()
