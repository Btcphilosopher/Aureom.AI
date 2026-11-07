"""Tests for the uncertainty simulation (housebuilder_vision.simulation.uncertainty)."""

from __future__ import annotations

import math
import time

import numpy as np
import pytest
from scipy import stats

from housebuilder_vision.core.models import Side, SimulationConfig
from housebuilder_vision.core.provenance import Basis
from housebuilder_vision.demo.build_demo import build_demo_project, build_uncalibrated_demo_project
from housebuilder_vision.geometry import compute_metrics
from housebuilder_vision.geometry.metrics import roof_shape
from housebuilder_vision.quantities import apply_construction_assemblies
from housebuilder_vision.simulation import (
    GROUP_RHO,
    GROUPS,
    RESOLVING_ACTIONS,
    binned_variance_share,
    discover_inputs,
    simulate_uncertainty,
    summarize,
)
from housebuilder_vision.simulation import uncertainty as U
from housebuilder_vision.twin import build_parametric_twin


# =============================================================================
# Fixtures and helpers
# =============================================================================
@pytest.fixture(scope="module")
def cal(tmp_path_factory):
    return build_demo_project(tmp_path_factory.mktemp("cal"))


@pytest.fixture(scope="module")
def uncal(tmp_path_factory):
    return build_uncalibrated_demo_project(tmp_path_factory.mktemp("uncal"))


def run(project, twin=None, **cfg):
    config = SimulationConfig(**{"n_samples": 60, **cfg})
    return simulate_uncertainty(twin or project.twin, project.library, project.rate_book, project.cost_parameters,
                                project.settings, config=config, calibration=project.calibration,
                                assumptions=project.assumptions)


def metric(res, name):
    return next(m for m in res.metrics if m.metric == name)


def model_for(project, twin=None):
    from housebuilder_vision.quantities.measures import TakeoffAssumptions

    return U._HouseModel(twin or project.twin, project.library, project.rate_book, project.cost_parameters,
                         project.settings, takeoff=TakeoffAssumptions.from_assumption_library(project.assumptions),
                         crew_sizes=None)


# =============================================================================
# Marginals and statistics
# =============================================================================
def test_marginals_follow_their_definitions():
    u = np.array([0.0, 0.05, 0.5, 0.95, 1.0])
    tri = U._marginal("triangular", 1.0, 2.0, 4.0)
    assert tri(u)[0] == pytest.approx(1.0) and tri(u)[-1] == pytest.approx(4.0)
    # F(mode) = (m - a) / (b - a)
    assert tri(np.array([1 / 3]))[0] == pytest.approx(2.0)
    nor = U._marginal("normal", 9.0, 10.0, 11.0)
    assert nor(np.array([0.05, 0.5, 0.95])) == pytest.approx([9.0, 10.0, 11.0])
    logn = U._marginal("lognormal", 5.0, 10.0, 20.0)
    assert logn(np.array([0.05, 0.5, 0.95])) == pytest.approx([5.0, 10.0, 20.0])
    uni = U._marginal("uniform", 2.0, 3.0, 4.0)
    assert uni(np.array([0.25]))[0] == pytest.approx(2.5)
    pert = U._marginal("pert", 0.0, 1.0, 6.0)
    grid = (np.arange(20000) + 0.5) / 20000
    assert pert(grid).mean() == pytest.approx((0 + 4 * 1 + 6) / 6, rel=1e-3)
    assert U._marginal("fixed", 1.0, 2.0, 3.0) is None
    assert U._marginal("triangular", 2.0, 2.0, 2.0) is None
    assert U._marginal("triangular", None, 2.0, 3.0) is None
    disc = U._discrete_ppf([0.6, 0.3, 0.1])
    assert list(disc(np.array([0.1, 0.65, 0.95]))) == [0.0, 1.0, 2.0]


def test_binned_variance_share_estimator():
    rng = np.random.default_rng(1)
    x1, x2, z = rng.normal(size=(3, 4000))
    assert binned_variance_share(x1, x1) > 0.95
    assert binned_variance_share(x1, z) < 0.02
    y = x1 + x2
    assert binned_variance_share(x1, y) == pytest.approx(0.5, abs=0.06)
    cls = (rng.random(4000) < 0.3).astype(float)
    assert binned_variance_share(cls, 5 * cls + rng.normal(size=4000) * 0.1, categorical=True) > 0.95
    assert binned_variance_share(x1, np.ones(4000)) == 0.0


def test_summarize_quantiles():
    s = summarize("x", "m", np.arange(1, 101, dtype=float))
    assert s.p50 == pytest.approx(50.5) and s.min == 1 and s.max == 100
    assert s.p10 < s.p50 < s.p90 and s.p5 <= s.p10 and s.p90 <= s.p95


# =============================================================================
# Input discovery
# =============================================================================
def test_inputs_discovered_from_twin_and_rates(cal):
    inputs = discover_inputs(cal.twin, cal.library, cal.rate_book, cal.cost_parameters, cal.settings,
                             calibration=cal.calibration, assumptions=cal.assumptions)
    by_name = {i.name: i for i in inputs}
    assert set(GROUPS) == {i.group for i in inputs}
    assert set(GROUPS) == set(GROUP_RHO) == set(RESOLVING_ACTIONS)
    # scale: calibration + scale-group dimensions; the confirmed frontage is a (tight) measurement input
    mpp = next(i for i in inputs if i.name.startswith("calibration.metres_per_pixel"))
    assert mpp.group == "scale" and mpp.distribution == "normal"
    assert by_name["main.width"].basis == Basis.USER_CONFIRMED and by_name["main.width"].high - \
        by_name["main.width"].low == pytest.approx(0.04)
    assert by_name["garage.width"].group == "scale"
    # hidden geometry: the pitch prior is sampled, depth derived (observed rise); attached origin derived
    assert by_name["main.roof.pitch_deg"].group == "hidden_geometry"
    assert "main.depth" not in by_name and "garage.origin_x" not in by_name
    assert by_name["garage.depth"].group == "hidden_geometry"
    assert by_name["hidden.rear_glazing_ratio"].group == "hidden_geometry"
    shared = [i for i in inputs if "ground_floor_level" in i.name]
    assert len(shared) == 1 and "shared" in shared[0].name  # one FFL assumption for all blocks
    # commercial groups
    assert by_name["labour rate: lab:bricklaying"].group == "labour_rates"
    brick = by_name["unit price: mat:facing_brick"]
    assert brick.group == "unit_prices" and (brick.low, brick.mode, brick.high) == pytest.approx((0.98, 1.0, 1.05))
    prod = by_name["productivity: bricklaying"]
    assert (prod.low, prod.mode, prod.high) == (0.85, 1.0, 1.30) and prod.basis == Basis.ASSUMED
    assert all((i.low, i.high) == (0.6, 1.8) for i in inputs if i.group == "waste")
    ground = by_name["ground class"]
    assert ground.distribution == "discrete" and "fdn_piled_allowance" in ground.description
    lt = by_name["lead time: window_upvc_dg"]
    assert (lt.low, lt.mode, lt.high) == (6.0, 8.0, 10.0) and lt.unit == "week"


def test_include_groups_filters_inputs(cal):
    cfg = SimulationConfig(include_groups=["unit_prices", "nonsense"])
    inputs = discover_inputs(cal.twin, cal.library, cal.rate_book, cal.cost_parameters, cal.settings, config=cfg,
                             calibration=cal.calibration)
    assert inputs and {i.group for i in inputs} == {"unit_prices"}
    res = run(cal, include_groups=["unit_prices"], n_samples=30)
    assert metric(res, "gia_m2").std == 0.0  # geometry untouched
    assert metric(res, "construction_incl_contingency").std > 0
    assert [r["group"] for r in res.information_value] == ["unit_prices"]


# =============================================================================
# Coherent house per sample
# =============================================================================
def test_depth_pitch_coupling_keeps_the_observed_rise(cal):
    model = model_for(cal)
    main = model.block_index["main"]
    c = model.couplings[main]
    assert c.mode == "pitch_primary" and c.k == 0.5
    base_rise = roof_shape(model.base_bp[main])[2]
    for pitch in (30.0, 40.0):
        bps, _ = model._geometry(U._Sample(block={(main, "pitch_deg"): pitch}))
        bp = bps[main]
        assert bp.depth == pytest.approx(base_rise / (0.5 * math.tan(math.radians(pitch))), rel=1e-9)
        assert roof_shape(bp)[2] == pytest.approx(base_rise, rel=1e-9)
    # a steeper pitch prior means a shallower hidden depth
    d30 = model._geometry(U._Sample(block={(main, "pitch_deg"): 30.0}))[0][main].depth
    d40 = model._geometry(U._Sample(block={(main, "pitch_deg"): 40.0}))[0][main].depth
    assert d30 > d40
    # the rise scales with the sampled image scale of its correlation group
    bps, _ = model._geometry(U._Sample(scale_ratio={c.group: 1.02}))
    assert roof_shape(bps[main])[2] == pytest.approx(1.02 * base_rise, rel=1e-6)


def test_attached_blocks_stay_attached(cal):
    model = model_for(cal)
    main, garage = model.block_index["main"], model.block_index["garage"]
    bps, ops = model._geometry(U._Sample(block={(main, "width"): 9.0, (garage, "depth"): 5.2}))
    assert bps[garage].x0 == pytest.approx(bps[main].x0 + 9.0)
    assert bps[garage].y0 == pytest.approx(bps[main].y0)  # front faces flush
    compute_metrics(bps, ops, model.t_ext, model.t_sep)  # valid footprint
    # H-B: the rear extension follows the sampled main depth
    hb = next(h for h in cal.hypotheses if h.hypothesis_id == "H-B")
    twin_b = build_parametric_twin(hb, selection=cal.twin.assemblies, settings=cal.settings)
    mb = model_for(cal, twin_b)
    m, e = mb.block_index["main"], mb.block_index["rear_ext"]
    rel = next(a for a in mb.attachments if a.child == e)
    assert rel.relation == "behind" and rel.align == "left"
    for pitch in (30.0, 45.0):
        bps, ops = mb._geometry(U._Sample(block={(m, "pitch_deg"): pitch}))
        assert bps[e].y0 == pytest.approx(bps[m].y0 + bps[m].depth)
        assert bps[e].x0 == pytest.approx(bps[m].x0)
        compute_metrics(bps, ops, mb.t_ext, mb.t_sep)


def test_hidden_rule_openings_follow_the_glazing_ratio(cal):
    model = model_for(cal)
    rear = next(rs for rs in model.rule_sides if rs.side == Side.REAR)

    def rear_glazing(ratio):
        _, ops = model._geometry(U._Sample(ratios={"rear_glazing_ratio": ratio}))
        return sum(ops[k].width * ops[k].height for k in rear.windows)

    base = sum(model.base_op[k].width * model.base_op[k].height for k in rear.windows)
    assert rear_glazing(cal.twin.hidden.rear_glazing_ratio.value) == pytest.approx(base)
    lo, hi = rear_glazing(0.12), rear_glazing(0.35)
    assert lo < base < hi
    # rule-window area tracks (ratio x hidden wall area - rule doors), relative to the base
    r0 = cal.twin.hidden.rear_glazing_ratio.value
    wall = (rear.base_target + rear.door_area) / r0
    assert hi / lo == pytest.approx((0.35 * wall - rear.door_area) / (0.12 * wall - rear.door_area), rel=1e-9)


def test_ground_classes_switch_foundations(cal):
    res = run(cal, include_groups=["ground"], n_samples=60)
    cond = res.conditional_on_ground
    assert set(cond) == {"good_clay_or_gravel", "variable_made_ground", "poor_soft_ground"}
    assert cond["poor_soft_ground"].p50 > cond["good_clay_or_gravel"].p50
    assert "fdn_piled_allowance" in cond["poor_soft_ground"].metric
    assert set(res.samples["ground_class"]) <= {0.0, 1.0, 2.0}
    assert metric(res, "concrete_m3").std > 0
    # user-confirmed foundation: ground uncertainty resolved, not sampled
    confirmed = apply_construction_assemblies(cal.twin, {"foundation": "fdn_trench_fill"}, cal.library, actor="user")
    res2 = run(cal, twin=confirmed, include_groups=["ground", "unit_prices"], n_samples=20)
    assert not res2.conditional_on_ground
    assert all(i.group != "ground" for i in res2.inputs)
    assert any("user-confirmed" in n for n in res2.notes)


def test_scale_values_are_comonotonic_within_an_image(uncal):
    res = run(uncal, include_groups=["scale"], n_samples=40)
    w_main = np.array(res.samples["main.width_m"])
    w_gar = np.array(res.samples["garage.width_m"])
    assert stats.spearmanr(w_main, w_gar)[0] == pytest.approx(1.0)
    assert metric(res, "gia_m2").std > 0
    assert [r["group"] for r in res.information_value] == ["scale"]
    assert res.information_value[0]["variance_share"] > 0.8


# =============================================================================
# Reproducibility, sampling, outputs
# =============================================================================
def test_same_seed_reproduces_and_other_seed_differs(cal):
    a = run(cal, n_samples=30, seed=7)
    b = run(cal, n_samples=30, seed=7)
    c = run(cal, n_samples=30, seed=8)
    assert a.samples == b.samples
    assert [m.model_dump() for m in a.metrics] == [m.model_dump() for m in b.metrics]
    assert a.samples["construction_incl_contingency"] != c.samples["construction_incl_contingency"]
    mc1 = run(cal, n_samples=30, seed=7, method="mc")
    mc2 = run(cal, n_samples=30, seed=7, method="mc")
    assert mc1.samples == mc2.samples
    assert mc1.samples["construction_incl_contingency"] != a.samples["construction_incl_contingency"]


@pytest.fixture(scope="module")
def full500(cal):
    t0 = time.perf_counter()
    res = run(cal, n_samples=500)
    return res, time.perf_counter() - t0


def test_performance_500_samples_under_15_seconds(full500):
    res, elapsed = full500
    assert elapsed < 15.0
    assert res.n_samples == 500 and not any("invalid footprint" in n for n in res.notes)


def test_outputs_sensitivity_and_information_value(full500):
    res, _ = full500
    names = [m.metric for m in res.metrics]
    for m in ("construction_incl_contingency", "contract_sum", "gia_m2", "external_wall_net_m2", "roof_surface_m2",
              "concrete_m3", "labour_hours", "programme_weeks", "main.width_m", "main.depth_m"):
        assert m in names
    cost = metric(res, "construction_incl_contingency")
    assert cost.unit == "GBP" and cost.p10 < cost.p50 < cost.p90 and cost.min <= cost.p5
    assert len(res.samples["construction_incl_contingency"]) == res.n_samples == 500
    assert len(res.samples["gia_m2"]) == 500
    assert len(res.sensitivity) == len(res.inputs)
    assert all(-1.0 <= s.spearman_rho <= 1.0 and 0.0 <= s.variance_share <= 1.0 for s in res.sensitivity)
    pitch = next(s for s in res.sensitivity if s.input_name == "main.roof.pitch_deg")
    assert pitch.spearman_rho < -0.4  # steeper assumed pitch -> shallower hidden depth -> lower cost
    info = res.information_value
    assert [r["rank"] for r in info] == list(range(1, len(info) + 1))
    shares = [r["variance_share"] for r in info]
    assert shares == sorted(shares, reverse=True)
    assert info[0]["group"] == "hidden_geometry"
    assert info[0]["resolving_action"] == "Upload a side/rear elevation or a dimensioned floor plan"
    by_group = {r["group"]: r for r in info}
    assert by_group["scale"]["variance_share"] < 0.05  # frontage confirmed: scale is resolved
    for r in info:
        assert r["resolving_action"] == RESOLVING_ACTIONS[r["group"]]
        assert 0.0 <= r["p10_p90_width_accounted"] <= r["p10_p90_width"] + 1e-9
    assert "not statistically calibrated" in res.interval_type
    assert any("No averaging" in n for n in res.notes)
    assert any("rho = " in n and "unit_prices 0.5" in n for n in res.notes)


def test_group_correlations_are_repaired_or_reported(cal):
    res = run(cal, n_samples=20, group_correlations={
        "unit_prices|labour_rates": 0.95, "unit_prices|waste": 0.95, "labour_rates|waste": -0.95, "foo|bar": 0.3})
    assert any("repaired" in n for n in res.notes)
    assert any("'foo|bar' ignored" in n for n in res.notes)


def test_correlated_factors_raise_cross_group_rank_correlation():
    drivers = [U._Driver(spec=U.UncertainInput(name=f"p{i}", group="unit_prices", target="t", distribution="normal"),
                         ppf=lambda u: u, apply=lambda v, s: None, factor="unit_prices") for i in range(3)]
    drivers += [U._Driver(spec=U.UncertainInput(name="l", group="labour_rates", target="t", distribution="normal"),
                          ppf=lambda u: u, apply=lambda v, s: None, factor="labour_rates")]
    notes: list[str] = []
    x, f, keys, c = U._latents(drivers, SimulationConfig(n_samples=4000, seed=3), notes)
    assert keys == ["unit_prices", "labour_rates"] and c[0, 1] == pytest.approx(0.4)
    r = np.corrcoef(x.T)
    assert r[0, 1] == pytest.approx(GROUP_RHO["unit_prices"], abs=0.05)
    assert r[0, 3] == pytest.approx(0.4 * math.sqrt(0.5 * 0.7), abs=0.05)


def test_incomplete_geometry_is_rejected(cal):
    main = cal.twin.block("main")
    bad = cal.twin.model_copy(update={"blocks": [main.model_copy(update={"depth": main.depth.model_copy(
        update={"value": None, "basis": Basis.UNKNOWN, "low": None, "high": None})})] + cal.twin.blocks[1:]})
    with pytest.raises(ValueError):
        run(cal, twin=bad, n_samples=20)


def test_flat_or_fixed_twin_has_no_geometry_spread(cal):
    res = run(cal, include_groups=["labour_rates"], n_samples=20)
    assert metric(res, "external_wall_net_m2").std == 0.0
    assert metric(res, "labour_hours").std == 0.0  # productivity not sampled
    assert metric(res, "construction_incl_contingency").std > 0


def test_openings_with_unknown_size_are_excluded_not_invented(cal):
    ops = list(cal.twin.openings)
    k = next(i for i, o in enumerate(ops) if not o.hidden_side_rule)
    o = ops[k]
    ops[k] = o.model_copy(update={"width_m": o.width_m.model_copy(
        update={"value": None, "basis": Basis.UNKNOWN, "low": None, "high": None})})
    twin = cal.twin.model_copy(update={"openings": ops})
    res = run(cal, twin=twin, n_samples=20, include_groups=["scale"])
    assert any("excluded from the sampled geometry" in n and o.opening_id in n for n in res.notes)
    assert all(not i.name.startswith(o.opening_id) for i in res.inputs)
