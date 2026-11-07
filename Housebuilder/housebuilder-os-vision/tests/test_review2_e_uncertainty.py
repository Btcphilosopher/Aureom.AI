"""Regression tests for review 2, group E: uncertainty simulation, scenario comparison, information value.

One test (or a small group) per finding: UNC-1 .. UNC-13, SPEC-4 / UI-9 (resolving action for hidden
geometry matches the evidence the engine can use) and SPEC-9 (between-scenario spread as information value).
"""

from __future__ import annotations

import io
import math

import numpy as np
import pytest
from PIL import Image
from scipy import stats

from housebuilder_vision import pipeline as P
from housebuilder_vision.core.models import (
    BuildScenario,
    DetectedFeature,
    FeatureType,
    ImageKind,
    Side,
    SimulationConfig,
    TwinEdit,
    UncertainInput,
    ViewDirection,
)
from housebuilder_vision.core.provenance import Basis
from housebuilder_vision.demo.build_demo import (
    FRONT_IMAGE,
    build_demo_project,
    build_uncalibrated_demo_project,
    demo_build_scenarios,
    demo_registry,
)
from housebuilder_vision.geometry.metrics import roof_shape
from housebuilder_vision.quantities import apply_construction_assemblies
from housebuilder_vision.quantities.library import default_selection
from housebuilder_vision.simulation import uncertainty as U
from housebuilder_vision.simulation.scenarios import (
    SCENARIO_SPREAD_ACTIONS,
    _scenario_twin,
    combined_information_value,
    compare_build_scenarios,
    evaluate_build_scenario,
    scale_cost_parameters,
    scale_rate_book,
    scenario_spread_entries,
)
from housebuilder_vision.twin import apply_twin_edit, build_parametric_twin
from housebuilder_vision.vision.ingest import ingest_image, ingest_path


# =============================================================================
# Fixtures and helpers
# =============================================================================
@pytest.fixture(scope="module")
def cal(tmp_path_factory):
    return build_demo_project(tmp_path_factory.mktemp("e_cal"))


@pytest.fixture(scope="module")
def uncal(tmp_path_factory):
    return build_uncalibrated_demo_project(tmp_path_factory.mktemp("e_uncal"))


@pytest.fixture(scope="module")
def s4_twin(cal):
    sc = {s.scenario_id: s for s in demo_build_scenarios()}
    return _scenario_twin(cal.twin, cal.hypotheses, sc["S4"], cal.library)[0]


def edit(twin, target_type, target_id, field, value, **kw):
    return apply_twin_edit(twin, TwinEdit(target_type=target_type, target_id=target_id, field=field, value=value,
                                          **kw))


def simulate(project, twin=None, *, book=None, calibration="project", **cfg):
    config = SimulationConfig(**{"n_samples": 100, **cfg})
    return U.simulate_uncertainty(twin or project.twin, project.library, book or project.rate_book,
                                  project.cost_parameters, project.settings, config=config,
                                  calibration=project.calibration if calibration == "project" else calibration,
                                  assumptions=project.assumptions)


def sampled(project, twin=None, n=300, **model_kw):
    """(model, drivers, values, samples) exactly as simulate_uncertainty draws them."""
    cfg = SimulationConfig(n_samples=n)
    model = U._HouseModel(twin or project.twin, project.library, project.rate_book, project.cost_parameters,
                          project.settings, takeoff=U._takeoff(project.assumptions), crew_sizes=None, **model_kw)
    notes: list[str] = []
    drivers, _ = U._all_drivers(model, cfg, project.calibration, notes)
    x, _, _, _ = U._latents(drivers, cfg, notes)
    u = stats.norm.cdf(x)
    values = np.empty_like(u)
    for j, d in enumerate(drivers):
        v = np.clip(np.asarray(d.ppf(np.clip(u[:, j], 1e-12, 1 - 1e-12)), dtype=float), *d.clip)
        values[:, j] = np.round(v) if d.integer and d.spec.group != "ground" else v
    states = []
    for i in range(n):
        s = U._Sample()
        for j, d in enumerate(drivers):
            d.apply(float(values[i, j]), s)
        states.append(s)
    return model, drivers, values, states


def cost(res):
    return next(m for m in res.metrics if m.metric == U.COST_METRIC)


def mpp_ratio(project, drivers, values):
    j = next(j for j, d in enumerate(drivers) if d.spec.name.startswith("calibration.metres_per_pixel"))
    return values[:, j] / float(project.calibration.metres_per_pixel.value)


# =============================================================================
# UNC-1: a build scenario's foundation option is held, not resampled by ground class
# =============================================================================
def test_unc1_scenario_foundation_is_held_in_its_simulation(cal):
    sc = BuildScenario(scenario_id="SP", name="piled", hypothesis_id="H-A", foundation_option="fdn_piled_allowance")
    cfg = SimulationConfig(n_samples=80)
    ev = evaluate_build_scenario(cal.twin, cal.hypotheses, sc, cal.library, cal.rate_book, cal.cost_parameters,
                                 cal.settings, simulate=True, config=cfg, calibration=cal.calibration,
                                 assumptions=cal.assumptions)
    sim = ev.simulation
    assert ev.twin.assemblies.foundation == "fdn_piled_allowance"
    assert ev.twin.assemblies.basis["foundation"] == Basis.ASSUMED  # still a scenario hypothesis
    assert all(i.group != "ground" for i in sim.inputs)
    assert not sim.conditional_on_ground and "ground_class" not in sim.samples
    assert any("fixed by build scenario SP" in n for n in sim.notes)
    assert any("foundation held at 'fdn_piled_allowance'" in k for k in ev.outcome.key_assumptions)
    assert "fixed by build scenario SP" in sim.interval_type
    # every sample keeps the piled foundation: identical to a simulation of the same house with that foundation
    # confirmed (common random numbers make the draws identical)
    held = ev.twin.model_copy(deep=True)
    held.assemblies.basis["foundation"] = Basis.USER_CONFIRMED
    ref = U.simulate_uncertainty(held, cal.library, cal.rate_book, cal.cost_parameters, cal.settings, config=cfg,
                                 calibration=cal.calibration, assumptions=cal.assumptions)
    assert sim.samples[U.COST_METRIC] == ref.samples[U.COST_METRIC]
    # the piled scenario never samples the cheaper deep trench fill: no sample below the deterministic estimate
    # by more than the non-foundation spread of the same house
    assert cost(sim).p10 > ev.outcome.construction_cost - 0.1 * ev.outcome.construction_cost


def test_unc1_selected_option_keeps_the_classes_it_suits(cal):
    raft = apply_construction_assemblies(cal.twin, {"foundation": "fdn_raft"}, cal.library, actor="scenario")
    assert raft.assemblies.basis["foundation"] == Basis.ASSUMED
    model = U._HouseModel(raft, cal.library, cal.rate_book, cal.cost_parameters, cal.settings,
                          takeoff=U._takeoff(cal.assumptions), crew_sizes=None)
    notes: list[str] = []
    drv = U._ground_driver(model, SimulationConfig(), notes)
    assert drv is not None
    opts = dict(zip(drv.classes, model.ground_options))
    # fdn_raft lists poor_soft_ground and variable_made_ground: it is kept there (not swapped for trench / piles)
    assert opts["variable_made_ground"] == "fdn_raft" and opts["poor_soft_ground"] == "fdn_raft"
    assert opts["good_clay_or_gravel"] == "fdn_raft"  # good ground: the selected option (GROUND_FOUNDATIONS None)
    # the default trench fill suits good ground only: other classes still switch
    model0 = U._HouseModel(cal.twin, cal.library, cal.rate_book, cal.cost_parameters, cal.settings,
                           takeoff=U._takeoff(cal.assumptions), crew_sizes=None)
    d0 = U._ground_driver(model0, SimulationConfig(), [])
    assert dict(zip(d0.classes, model0.ground_options)) == {
        "good_clay_or_gravel": "fdn_trench_fill", "variable_made_ground": "fdn_deep_trench_fill",
        "poor_soft_ground": "fdn_piled_allowance"}
    # discover_inputs honours the same switch
    names = [i.group for i in U.discover_inputs(cal.twin, cal.library, cal.rate_book, cal.cost_parameters,
                                                cal.settings, calibration=cal.calibration,
                                                fixed_foundation="build scenario X")]
    assert "ground" not in names


# =============================================================================
# UNC-2: a hip's coupled span never exceeds its other side
# =============================================================================
def test_unc2_hip_span_capped_at_the_other_side(cal):
    hip = edit(cal.twin, "roof", "main", "form", "hip", reason="hip test")
    model, _, _, states = sampled(cal, hip, n=400)
    main = model.block_index["main"]
    c = model.couplings[main]
    assert c.hip and c.span == "depth" and c.mode == "pitch_primary"
    assert c.depth_hi > model.base_bp[main].width  # the prior range alone would allow depth > width
    for s in states:
        bp = model._geometry(s)[0][main]
        assert bp.depth <= bp.width + 1e-9
        rise = c.base_rise * s.scale_ratio.get(c.group or "", 1.0)
        assert abs(roof_shape(bp)[2] - rise) < 1e-6


# =============================================================================
# UNC-3: common random numbers across scenarios
# =============================================================================
def test_unc3_scenarios_share_random_numbers(cal):
    # scenario B = same house, but one used rate has no uncertainty (one input fewer, every other input shared)
    model = U._HouseModel(cal.twin, cal.library, cal.rate_book, cal.cost_parameters, cal.settings,
                          takeoff=U._takeoff(cal.assumptions), crew_sizes=None)
    base = model.evaluate(U._Sample(), keep=True)
    rid = next(ln.rate_id for ln in base["_estimate"].lines if ln.rate_id and ln.cost_key.startswith("mat:"))
    book_b = cal.rate_book.model_copy(update={"rates": [
        r.model_copy(update={"uncertainty_low": 0.0, "uncertainty_high": 0.0}) if r.rate_id == rid else r
        for r in cal.rate_book.rates]})
    a = simulate(cal, n_samples=60, seed=3)
    b = simulate(cal, book=book_b, n_samples=60, seed=3)
    assert len(b.inputs) == len(a.inputs) - 1
    ya, yb = np.array(a.samples[U.COST_METRIC]), np.array(b.samples[U.COST_METRIC])
    assert np.corrcoef(ya, yb)[0, 1] > 0.9
    # masonry vs timber frame + brick (different input sets): paired samples, stable P50 gap across seeds
    sc = {s.scenario_id: s for s in demo_build_scenarios()}
    tw = {k: _scenario_twin(cal.twin, cal.hypotheses, sc[k], cal.library)[0] for k in ("S1", "S2")}
    gaps = []
    for seed in (1, 3):
        r1, r2 = (simulate(cal, tw[k], n_samples=60, seed=seed) for k in ("S1", "S2"))
        y1, y2 = np.array(r1.samples[U.COST_METRIC]), np.array(r2.samples[U.COST_METRIC])
        assert np.corrcoef(y1, y2)[0, 1] > 0.9
        gaps.append(cost(r1).p50 - cost(r2).p50)
    assert all(g > 0 for g in gaps)  # sign of the comparison no longer flips with the seed


def test_unc3_stream_is_keyed_by_the_input_not_its_column():
    u1 = U._uniform_column(U._stream(5, "input:rate:x"), 50, "lhs")
    u2 = U._uniform_column(U._stream(5, "input:rate:x"), 50, "lhs")
    u3 = U._uniform_column(U._stream(5, "input:rate:y"), 50, "lhs")
    assert np.array_equal(u1, u2) and not np.array_equal(u1, u3)
    # a Latin hypercube column: exactly one point per stratum
    assert sorted(np.floor(u1 * 50).astype(int)) == list(range(50))


# =============================================================================
# UNC-4 / UNC-12: user-confirmed values are independent errors with their own action
# =============================================================================
def test_unc4_user_confirmed_tolerance_is_independent_of_the_image_scale(cal):
    t = edit(cal.twin, "block", "main", "depth", 8.0, tolerance=1.0, reason="paced on site")
    assert t.block("main").depth.correlation_group  # the edit keeps the image group (twin.builder)
    _, drivers, values, _ = sampled(cal, t, n=300)
    j = next(j for j, d in enumerate(drivers) if d.spec.name.startswith("main.depth"))
    assert drivers[j].factor is None and drivers[j].spec.basis == Basis.USER_CONFIRMED
    assert abs(stats.spearmanr(values[:, j], mpp_ratio(cal, drivers, values))[0]) < 0.15
    # (n large enough for the scale share to be clear of its sampling error; below that the action falls back
    # to the calibration-aware default)
    res = simulate(cal, t, n_samples=500)
    scale = next(r for r in res.information_value if r["group"] == "scale")
    assert scale["variance_share"] > 2 * scale["variance_share_se"]
    assert scale["resolving_action"].startswith("Measure main.depth more precisely")
    assert "frontage" not in scale["resolving_action"]
    # comonotonic stacking is gone: the group no longer moves every image dimension with the paced depth
    members = [it for it in res.sensitivity if it.group == "scale"]
    assert members[0].input_name == "main.depth" and members[1].variance_share < 0.5 * members[0].variance_share


def test_unc12_scale_action_follows_the_calibration(cal, uncal):
    a = next(r for r in simulate(cal, n_samples=60).information_value if r["group"] == "scale")
    assert a["resolving_action"] == U.SCALE_ACTION_CALIBRATED and "frontage" not in a["resolving_action"]
    b = next(r for r in simulate(uncal, n_samples=60).information_value if r["group"] == "scale")
    assert b["resolving_action"] == U.RESOLVING_ACTIONS["scale"]


# =============================================================================
# UNC-5: floor-to-floor and sills follow the observed wall plate and the sampled FFL
# =============================================================================
def test_unc5_ftf_derived_from_the_observed_eaves_and_ffl(cal):
    model, drivers, values, states = sampled(cal, n=400)
    main = model.block_index["main"]
    link = model.eaves_links[main]
    eaves = cal.twin.block("main").observed_eaves_m
    assert link.plate0 == pytest.approx(float(eaves.value), abs=1e-9)
    assert all("floor_to_floor" not in d.spec.name for d in drivers if d.spec.name.startswith("main."))
    ratio = mpp_ratio(cal, drivers, values)
    ffl, ftf = [], []
    for s, r in zip(states, ratio):
        bp = model._geometry(s)[0][main]
        assert abs(bp.ffl + bp.storeys * bp.floor_to_floor - link.plate0 * r) < 1e-9
        ffl.append(bp.ffl)
        ftf.append(bp.floor_to_floor)
    assert np.corrcoef(ffl, ftf)[0, 1] < -0.2  # higher floor level -> shorter storeys
    # an observed window sill is its observed bottom (scaled) minus FFL (and storeys below it)
    sl = next(sl for sl in model.sill_links if sl.block == main and sl.storey == 1)
    for s, r in list(zip(states, ratio))[:50]:
        bps, ops = model._geometry(s)
        bp = bps[main]
        assert ops[sl.opening].sill == pytest.approx(sl.z0 * r - bp.ffl - bp.floor_to_floor, abs=1e-9)
    assert not any(d.spec.target.endswith(f"{cal.twin.openings[sl.opening].opening_id}.sill_m") for d in drivers)


def test_unc5_confirmed_ftf_is_not_derived(cal):
    t = edit(cal.twin, "block", "main", "floor_to_floor", 2.6, reason="measured")
    model = U._HouseModel(t, cal.library, cal.rate_book, cal.cost_parameters, cal.settings,
                          takeoff=U._takeoff(cal.assumptions), crew_sizes=None)
    assert model.block_index["main"] not in model.eaves_links
    assert any("main: floor-to-floor is user_confirmed" in n for n in model.coupling_notes)


# =============================================================================
# UNC-6: a fixed user-confirmed pitch is never re-derived
# =============================================================================
def test_unc6_fixed_user_pitch_is_kept_in_every_sample(cal):
    t = edit(cal.twin, "roof", "main", "pitch_deg", 40.0, reason="measured")
    assert t.block("main").roof.pitch_deg.distribution.value == "fixed"
    model, _, _, states = sampled(cal, t, n=2000)
    main = model.block_index["main"]
    c = model.couplings[main]
    assert c.mode == "pitch_primary" and c.pitch_fixed
    pitches = np.array([model._geometry(s)[0][main].pitch_deg for s in states])
    assert np.all(pitches == 40.0)
    # the span follows the (scaled) rise exactly
    s = states[int(np.argmax([st.scale_ratio.get(c.group, 1.0) for st in states]))]
    bp = model._geometry(s)[0][main]
    assert roof_shape(bp)[2] == pytest.approx(c.base_rise * s.scale_ratio[c.group], rel=1e-9)


# =============================================================================
# UNC-7: one shared FFL prior across blocks (also the H-B extension's "assumed equal" copy)
# =============================================================================
def test_unc7_extension_ffl_is_the_shared_prior(cal, s4_twin):
    model, drivers, _, states = sampled(cal, s4_twin, n=100)
    ffl = [d for d in drivers if "ground_floor_level" in d.spec.target]
    assert len(ffl) == 1
    for b in ("main", "garage", "rear_ext"):
        assert f"block:{b}.ground_floor_level" in ffl[0].spec.target
    for s in states[:30]:
        levels = {bp.block_id: bp.ffl for bp in model._geometry(s)[0]}
        assert levels["rear_ext"] == levels["main"] == levels["garage"]


# =============================================================================
# UNC-8 / UNC-9: group shares include independent members; standard errors and ties
# =============================================================================
def test_unc8_scale_share_includes_independent_members(cal):
    t = edit(cal.twin, "block", "main", "width", 9.6, tolerance=0.5, reason="tape, rough")
    res = simulate(cal, t, n_samples=400, group_correlations={})
    scale = next(r for r in res.information_value if r["group"] == "scale")
    width = next(it for it in res.sensitivity if it.input_name == "main.width")
    assert "independent input latent" in scale["estimator"]
    assert scale["variance_share"] >= width.variance_share - 3 * scale["variance_share_se"]
    assert scale["variance_share"] > 0.01


def test_unc9_information_value_reports_its_sampling_error(cal):
    res = simulate(cal, n_samples=200)
    info = res.information_value
    assert all(r["variance_share_se"] > 0 for r in info)
    by = {r["group"]: r for r in info}
    for r in info:
        lo, hi = r["rank_range"]
        assert 1 <= lo <= r["rank"] <= hi <= len(info)
        for g in r["tied_with"]:
            assert r["group"] in by[g]["tied_with"]  # symmetric
    assert any("bootstrap standard error" in n for n in res.notes)


# =============================================================================
# UNC-10: first-floor rule glazing does not vanish behind a wider single-storey extension
# =============================================================================
def test_unc10_first_floor_rule_windows_survive_a_wide_extension(cal, s4_twin):
    model, _, _, _ = sampled(cal, s4_twin, n=20)
    main, ext = model.block_index["main"], model.block_index["rear_ext"]
    first = [k for k, o in enumerate(model.twin.openings)
             if o.hidden_side_rule and o.block_id == "main" and o.side.value == "rear" and o.kind.value == "window"
             and o.storey >= 1]
    assert first
    bps, ops = model._geometry(U._Sample(block={(ext, "width"): 6.5}))
    assert bps[ext].width == 6.5
    for k in first:
        assert ops[k].width > 0
    # the main rear wall above the single-storey extension is exposed on the first floor
    exposure = model._storey_exposure(bps)[(main, Side.REAR)]
    assert exposure[1] == pytest.approx(bps[main].width * bps[main].floor_to_floor, rel=1e-9)


# =============================================================================
# UNC-11: the scenario price level scales every money input
# =============================================================================
def _layers(est):
    out: dict = {}
    for ln in est.lines:
        out[ln.layer] = out.get(ln.layer, 0.0) + ln.amount
    return out


@pytest.mark.parametrize("strip_fallback_rates", [False, True])
def test_unc11_rate_multiplier_scales_every_cost_layer(cal, strip_fallback_rates):
    book = cal.rate_book
    if strip_fallback_rates:  # prelims / logistics then come from the CostParameters fallbacks
        book = book.model_copy(update={"rates": [r for r in book.rates
                                                 if not r.cost_key.startswith(("prelim:", "log:"))]})
    ests = {m: evaluate_build_scenario(cal.twin, cal.hypotheses, BuildScenario(scenario_id="SX", name="x",
                                                                               rate_multiplier=m),
                                       cal.library, book, cal.cost_parameters, cal.settings).estimate
            for m in (1.0, 1.2)}
    a, b = _layers(ests[1.0]), _layers(ests[1.2])
    for layer, v in a.items():
        if v:
            assert b[layer] / v == pytest.approx(1.2, rel=1e-9), layer


def test_unc11_scaling_helpers(cal):
    book = scale_rate_book(cal.rate_book, 1.5)
    for r0, r1 in zip(cal.rate_book.rates, book.rates):
        assert r1.value == pytest.approx(1.5 * r0.value)
        assert (r1.delivery_charge is None) == (r0.delivery_charge is None)
        if r0.delivery_charge is not None:
            assert r1.delivery_charge == pytest.approx(1.5 * r0.delivery_charge)
    cp = scale_cost_parameters(cal.cost_parameters, 1.5)
    for k in ("prelims_weekly_cost", "prelims_fixed_setup", "cost_per_delivery_load", "cost_per_skip"):
        assert getattr(cp, k) == pytest.approx(1.5 * getattr(cal.cost_parameters, k))
    assert cp.contingency_fraction == cal.cost_parameters.contingency_fraction
    assert scale_rate_book(cal.rate_book, 1.0) is cal.rate_book
    with pytest.raises(ValueError):
        scale_cost_parameters(cal.cost_parameters, 0.0)


# =============================================================================
# UNC-13: the correlation note reports the matrix in force
# =============================================================================
def test_unc13_note_reports_the_repaired_correlations(cal):
    gc = {"unit_prices|labour_rates": 0.99, "labour_rates|labour_productivity": 0.99,
          "unit_prices|labour_productivity": -0.99}
    res = simulate(cal, n_samples=20, group_correlations=gc)
    note = next(n for n in res.notes if n.startswith("Between-group factor correlations in force"))
    assert "unit_prices|labour_rates=+0.50 (requested +0.99)" in note
    assert "=+0.99" not in note
    plain = simulate(cal, n_samples=20)
    assert any("in force: unit_prices|labour_rates=+0.40." in n for n in plain.notes)


# =============================================================================
# SPEC-4 / UI-9: the hidden-geometry action names evidence the engine can use - and it works
# =============================================================================
def test_spec4_input_actions_match_the_engine():
    def spec(group, target, basis=Basis.ASSUMED, name="x"):
        return UncertainInput(name=name, group=group, target=target, distribution="triangular", basis=basis,
                              low=1.0, mode=1.5, high=2.0, unit="m")

    depth = U.input_action(spec("hidden_geometry", "block:main.depth"))
    assert depth == U.RESOLVING_ACTIONS["hidden_geometry"]
    assert "side elevation" in depth and "floor plan with the building outline" in depth and "rear" not in depth
    assert "rear elevation" in U.input_action(spec("hidden_geometry", "hidden.rear_glazing_ratio"))
    assert "floor level" in U.input_action(spec("hidden_geometry", "block:main.ground_floor_level"))
    assert U.input_action(spec("scale", "block:main.depth", Basis.USER_CONFIRMED, "main.depth")).startswith(
        "Measure main.depth more precisely")
    assert U.input_action(spec("scale", "block:main.width", Basis.INFERRED), "reference_measurement") == \
        U.SCALE_ACTION_CALIBRATED
    assert U.input_action(spec("unit_prices", "rate:r1")) == U.RESOLVING_ACTIONS["unit_prices"]


def _png(w=1000, h=800) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, "PNG")
    return buf.getvalue()


def test_spec4_the_recommended_floor_plan_narrows_hidden_geometry(cal, tmp_path):
    """Following the top recommendation (a floor plan with outlines and one measured dimension) removes most of
    the hidden-geometry spread - the action is something the engine can actually use."""
    base = simulate(cal, n_samples=150)
    hg0 = next(r for r in base.information_value if r["group"] == "hidden_geometry")
    assert hg0["rank"] == 1 and hg0["resolving_action"] == U.RESOLVING_ACTIONS["hidden_geometry"]

    store = tmp_path / "store"
    front = ingest_path(FRONT_IMAGE, kind=ImageKind.ELEVATION_DRAWING, view=ViewDirection.FRONT, store_dir=store)
    plan = ingest_image(_png(), "plan.png", kind=ImageKind.FLOOR_PLAN, view=ViewDirection.PLAN, store_dir=store)
    s, x0, yf = 50.0, 100.0, 600.0  # 50 px/m; front of the building at the bottom edge (y = 600)
    feats = [
        DetectedFeature(feature_id="pl_main", image_id=plan.image_id, feature_type=FeatureType.BUILDING_OUTLINE,
                        bbox=(x0, yf - 8.4 * s, x0 + 9.6 * s, yf), attributes={"block": "main"}),
        DetectedFeature(feature_id="pl_garage", image_id=plan.image_id, feature_type=FeatureType.BUILDING_OUTLINE,
                        bbox=(x0 + 9.6 * s, yf - 6.0 * s, x0 + 12.8 * s, yf), attributes={"block": "garage"}),
        DetectedFeature(feature_id="pl_dim", image_id=plan.image_id, feature_type=FeatureType.DIMENSION,
                        line=(x0, yf + 20, x0 + 9.6 * s, yf + 20),
                        attributes={"length_m": 9.6, "axis": "width", "block": "main"}),
    ]
    analysis = P.analyse_images([front, plan], store_dir=store, registry=demo_registry(),
                                manual_features={plan.image_id: feats})
    calib = P.calibrate_scale(analysis, None)
    assert calib.method == "dimensioned_plan"
    hyps = P.generate_geometry_hypotheses(analysis, calib)
    twin = build_parametric_twin(hyps[0], selection=default_selection(cal.library), settings=cal.settings)
    d = twin.block("main").depth
    assert d.basis == Basis.INFERRED and d.value == pytest.approx(8.4, rel=0.02)
    res = U.simulate_uncertainty(twin, cal.library, cal.rate_book, cal.cost_parameters, cal.settings,
                                 config=SimulationConfig(n_samples=150), calibration=calib,
                                 assumptions=cal.assumptions)
    hg = next(r for r in res.information_value if r["group"] == "hidden_geometry")
    assert hg["variance_share"] < 0.5 * hg0["variance_share"]
    dm = next(m for m in res.metrics if m.metric == "main.depth_m")
    dm0 = next(m for m in base.metrics if m.metric == "main.depth_m")
    assert dm.p95 - dm.p5 < 0.25 * (dm0.p95 - dm0.p5)


# =============================================================================
# SPEC-9: hypothesis / assembly uncertainty as separate scenario-spread entries
# =============================================================================
@pytest.fixture(scope="module")
def comparison(cal):
    return compare_build_scenarios(cal.twin, cal.hypotheses, demo_build_scenarios(), cal.library, cal.rate_book,
                                   cal.cost_parameters, cal.settings, calibration=cal.calibration,
                                   assumptions=cal.assumptions)


def test_spec9_scenario_spread_entries(comparison):
    o = {x.scenario_id: x for x in comparison.outcomes}
    assert o["S1"].assemblies["external_wall"] == "ew_masonry_cavity" and o["S1"].rate_multiplier == 1.0
    entries = {e["dimension"]: e for e in scenario_spread_entries(comparison, currency="GBP")}
    assert set(entries) == {"hypothesis", "construction"}
    hyp = entries["hypothesis"]  # S1 (H-A) vs S4 (H-B): same assemblies, different hypothesis
    assert sorted(hyp["scenarios"]) == ["S1", "S4"]
    assert hyp["spread"] == pytest.approx(abs(o["S4"].construction_cost - o["S1"].construction_cost))
    assert hyp["measure"] == "deterministic construction cost" and hyp["variance_share"] is None
    assert hyp["resolving_action"] == SCENARIO_SPREAD_ACTIONS["hypothesis"] and "floor plan" in hyp["resolving_action"]
    con = entries["construction"]  # S1 / S2 / S3: H-A with three wall systems
    costs = [o[k].construction_cost for k in ("S1", "S2", "S3")]
    assert sorted(con["scenarios"]) == ["S1", "S2", "S3"] and con["n_alternatives"] == 3
    assert con["spread"] == pytest.approx(max(costs) - min(costs))
    assert "construction method" in con["resolving_action"]
    assert all(e["kind"] == "scenario_spread" and "not averaged" in e["label"] for e in entries.values())
    # outcomes saved before ScenarioOutcome.assemblies existed fall back to the key-assumption lines
    legacy = comparison.model_copy(update={"outcomes": [x.model_copy(update={"assemblies": {}})
                                                        for x in comparison.outcomes]})
    assert {e["dimension"]: round(e["spread"], 6) for e in scenario_spread_entries(legacy)} == \
        {k: round(v["spread"], 6) for k, v in entries.items()}


def test_spec9_combined_ranking_and_conditional_interval(cal, comparison):
    sim = simulate(cal, n_samples=60)
    assert "conditional on geometry hypothesis H-A" in sim.interval_type
    assert "external wall 'ew_masonry_cavity'" in sim.interval_type
    combined = combined_information_value(sim, comparison)
    kinds = {e["kind"] for e in combined}
    assert kinds == {"within_scenario", "scenario_spread"}
    impacts = [e["impact"] for e in combined]
    assert impacts == sorted(impacts, reverse=True)
    assert [e["combined_rank"] for e in combined] == list(range(1, len(combined) + 1))
    assert len(combined) == len(sim.information_value) + 2
    assert sim.information_value[0].get("combined_rank") is None  # the simulation result is not mutated
    assert combined_information_value(None, None) == []
    one = comparison.model_copy(update={"outcomes": comparison.outcomes[:1]})
    assert scenario_spread_entries(one) == []


def test_spec9_simulated_scenarios_use_p50(cal):
    comp = compare_build_scenarios(cal.twin, cal.hypotheses, demo_build_scenarios()[:2], cal.library, cal.rate_book,
                                   cal.cost_parameters, cal.settings, simulate=True,
                                   config=SimulationConfig(n_samples=40), calibration=cal.calibration,
                                   assumptions=cal.assumptions)
    e = scenario_spread_entries(comp)
    assert [x["dimension"] for x in e] == ["construction"] and e[0]["measure"] == "cost P50"
    p50 = [o.cost_p50 for o in comp.outcomes]
    assert e[0]["spread"] == pytest.approx(max(p50) - min(p50))
    assert any("Common random numbers" in n for n in comp.notes)
    assert any("Only 40 samples per scenario" in n for n in comp.notes)
    assert math.isfinite(e[0]["spread"])
