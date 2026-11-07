"""Tests for the digital simulations: thermal, carbon, programme, logistics and adapters.

Test twins are built by hand; quantities come from ``calculate_quantities``.
"""

from __future__ import annotations

import json
import math

import pytest

from housebuilder_vision.core.models import (
    Assembly,
    AssemblyLayer,
    AssemblyLibrary,
    Block,
    BlockRole,
    BuildingTwin,
    ElementType,
    HiddenSideAssumptions,
    LayerBridging,
    LayerRole,
    MaterialSpec,
    Opening,
    OpeningKind,
    ProgrammeResult,
    QuantityLine,
    QuantityStatus,
    RoofForm,
    RoofSpec,
    Side,
    TaskSpec,
)
from housebuilder_vision.core.provenance import Basis, TrackedValue, assumed
from housebuilder_vision.core.settings import ProjectSettings
from housebuilder_vision.quantities import (
    apply_construction_assemblies,
    calculate_quantities,
    default_library,
    default_selection,
    wall_thicknesses,
)
from housebuilder_vision.simulation import (
    AdapterNotConfigured,
    EmbodiedCarbonDataAdapter,
    EnergyAnalysisAdapter,
    NotConfiguredCarbonDataAdapter,
    NotConfiguredEnergyAdapter,
    NotConfiguredStructuralAdapter,
    StaticCarbonFactorAdapter,
    StructuralAnalysisAdapter,
    ThermalDataError,
    apply_carbon_factors,
    assign_lines_to_tasks,
    build_programme,
    critical_path_method,
    default_engineering_adapters,
    embodied_carbon,
    ground_floor_u,
    heat_loss,
    plan_deliveries,
    u_value,
)

LIB = default_library()
FFL, FTF = 0.15, 2.7


# ----------------------------------------------------------------- helpers
def tv(v, unit="m", basis=Basis.USER_CONFIRMED):
    return TrackedValue(value=v, unit=unit, basis=basis)


def blk(bid, x0, y0, w, d, storeys=2, form=RoofForm.GABLE, pitch=35.0, axis="x", eo=0.3, vo=0.2, heated=True,
        role=BlockRole.MAIN):
    return Block(block_id=bid, role=role, origin_x=tv(x0), origin_y=tv(y0), width=tv(w), depth=tv(d),
                 storeys=tv(storeys, "storeys"), floor_to_floor=tv(FTF), ground_floor_level=tv(FFL),
                 roof=RoofSpec(form=form, pitch_deg=tv(pitch, "deg"), ridge_axis=axis, eaves_overhang_m=tv(eo),
                               verge_overhang_m=tv(vo)),
                 heated=heated)


def op(oid, bid, side, kind, storey, off, w, h, sill):
    return Opening(opening_id=oid, block_id=bid, side=side, kind=kind, storey=storey, offset_m=tv(off),
                   width_m=tv(w), height_m=tv(h), sill_m=tv(sill))


def make_twin(blocks, openings=()):
    return BuildingTwin(
        twin_id="t_sim", blocks=list(blocks), openings=list(openings),
        hidden=HiddenSideAssumptions(rear_glazing_ratio=assumed(0.2, "fraction"),
                                     side_glazing_ratio=assumed(0.04, "fraction")),
        assemblies=default_selection(LIB))


def box_twin():
    return make_twin([blk("B1", 0, 0, 10, 8)], [
        op("W1", "B1", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.2, 1.2, 0.9),
        op("D1", "B1", Side.FRONT, OpeningKind.DOOR, 0, 5.0, 1.0, 2.1, 0.0),
    ])


def demo_twin():
    """Main house + lower unheated garage (right) + flat-roofed heated rear extension."""
    blocks = [
        blk("main", 0, 0, 9.6, 8.4),
        blk("garage", 9.6, 0, 3.2, 6.0, storeys=1, pitch=30.0, axis="y", heated=False, role=BlockRole.GARAGE),
        blk("ext", 0, 8.4, 4.8, 3.6, storeys=1, form=RoofForm.FLAT, pitch=0.0, eo=0.15, vo=0.15,
            role=BlockRole.EXTENSION),
    ]
    ops = [
        op("W1", "main", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.8, 1.2, 0.9),
        op("D1", "main", Side.FRONT, OpeningKind.DOOR, 0, 4.3, 1.0, 2.1, 0.0),
        op("W2", "main", Side.FRONT, OpeningKind.WINDOW, 0, 6.8, 1.8, 1.2, 0.9),
        op("W3", "main", Side.FRONT, OpeningKind.WINDOW, 1, 1.3, 1.2, 1.2, 0.9),
        op("W4", "main", Side.REAR, OpeningKind.WINDOW, 1, 1.0, 1.2, 1.2, 0.9),
        op("G1", "garage", Side.FRONT, OpeningKind.GARAGE_DOOR, 0, 0.4, 2.4, 2.13, 0.0),
    ]
    return make_twin(blocks, ops)


def mat(mid, k, **kw):
    return MaterialSpec(material_id=mid, name=mid, installed_unit="m2", purchase_unit="m2", conductivity_w_mk=k,
                        **kw)


def three_layer_library(bridge_fraction=None):
    mats = [mat("brick", 0.8), mat("ins", 0.04), mat("block", 0.5), mat("timber", 0.13)]
    bridging = LayerBridging(material_id="timber", fraction=bridge_fraction) if bridge_fraction else None
    layers = [
        AssemblyLayer(name="brick", material_id="brick", role=LayerRole.EXTERNAL_FINISH, thickness_m=0.1),
        AssemblyLayer(name="insulation", material_id="ins", role=LayerRole.INSULATION, thickness_m=0.1,
                      bridging=bridging),
        AssemblyLayer(name="block", material_id="block", role=LayerRole.STRUCTURE, thickness_m=0.1),
    ]
    asm = Assembly(assembly_id="w3", name="3-layer wall", element=ElementType.EXTERNAL_WALL, layers=layers,
                   rsi=0.13, rse=0.04)
    return AssemblyLibrary(name="test", materials=mats, assemblies=[asm]), asm


def hand_programme(tasks):
    return ProgrammeResult(tasks=tasks, duration_days=max(t.earliest_finish for t in tasks),
                           duration_weeks=max(t.earliest_finish for t in tasks) / 5, critical_path=[],
                           total_labour_hours=0.0, labour_hours_by_trade={})


def task(tid, es, ef, lead=0.0):
    return TaskSpec(task_id=tid, name=tid, trade="general", labour_hours=0.0, crew_size=1.0, duration_days=ef - es,
                    earliest_start=es, earliest_finish=ef, material_lead_time_days=lead)


def qline(line_id, material_id, unit, qty, *, code="2.5", assembly_id=None, layer_index=None, cutting=0.0,
          waste=0.0, purchased=None, status=QuantityStatus.DERIVED, allowance_id=None, trade="general"):
    return QuantityLine(line_id=line_id, element_code=code, element_name=f"element {code}", description=line_id,
                        status=status, assembly_id=assembly_id, layer_index=layer_index, material_id=material_id,
                        allowance_id=allowance_id, unit=unit, installed_qty=qty, cutting_loss_qty=cutting,
                        waste_qty=waste, purchased_qty=purchased if purchased is not None else qty,
                        trade=trade, labour_hours=0.0)


def layer_idx(assembly_id, material_id):
    return [i for i, layer in enumerate(LIB.assembly(assembly_id).layers) if layer.material_id == material_id][0]


@pytest.fixture(scope="module")
def demo():
    twin = demo_twin()
    boq = calculate_quantities(twin, LIB)
    return twin, boq


# =============================================================================
# Thermal
# =============================================================================
def test_u_value_three_layer_hand_calculation():
    lib, asm = three_layer_library()
    r = 0.13 + 0.1 / 0.8 + 0.1 / 0.04 + 0.1 / 0.5 + 0.04  # = 2.995
    u, d = u_value(asm, lib, return_detail=True)
    assert u == pytest.approx(1.0 / r)
    assert d["r_total"] == pytest.approx(r)
    assert d["r_upper_m2k_w"] == pytest.approx(d["r_lower_m2k_w"])
    assert [row["r_m2k_w"] for row in d["layers"]] == pytest.approx([0.125, 2.5, 0.2])
    assert u_value("w3", lib) == pytest.approx(u)  # by id


def test_bridged_layer_between_extremes_and_combined_formula():
    f = 0.15
    lib_b, asm_b = three_layer_library(bridge_fraction=f)
    rsi, rse, r_brick, r_block = 0.13, 0.04, 0.1 / 0.8, 0.1 / 0.5
    r_ins, r_tim = 0.1 / 0.04, 0.1 / 0.13
    ra = rsi + r_brick + r_ins + r_block + rse
    rb = rsi + r_brick + r_tim + r_block + rse
    r_upper = 1.0 / ((1 - f) / ra + f / rb)
    lam_eq = (1 - f) * 0.04 + f * 0.13
    r_lower = rsi + r_brick + 0.1 / lam_eq + r_block + rse
    u, d = u_value(asm_b, lib_b, return_detail=True)
    assert d["r_upper_m2k_w"] == pytest.approx(r_upper)
    assert d["r_lower_m2k_w"] == pytest.approx(r_lower)
    assert u == pytest.approx(1.0 / (0.5 * (r_upper + r_lower)))
    assert r_lower < r_upper
    # lies between the unbridged extremes (all insulation / all timber)
    assert 1.0 / ra < u < 1.0 / rb
    assert d["relative_error_estimate"] == pytest.approx((r_upper - r_lower) / (r_upper + r_lower))


def test_window_override_ignores_layers():
    u, d = u_value("win_upvc_dg", LIB, return_detail=True)
    assert u == pytest.approx(1.4)
    assert d["method"] == "u_value_override"
    assert u_value(LIB.assembly("win_alu_tg"), LIB) == pytest.approx(1.2)
    assert u_value("door_composite", LIB) == pytest.approx(1.4)


def test_bundled_wall_u_values_hand_check_and_masonry_vs_timber_frame():
    # masonry cavity: brick / 100 mm mineral wool / aircrete / plaster + skim (series layers)
    r_m = 0.13 + 0.1025 / 0.77 + 0.10 / 0.037 + 0.10 / 0.15 + 0.011 / 0.40 + 0.002 / 0.40 + 0.04
    u_mas = u_value("ew_masonry_cavity", LIB)
    assert u_mas == pytest.approx(1.0 / r_m)
    # timber frame + brick: cavity R 0.18, studs bridging 15 % of the mineral wool
    u_tf, d = u_value("ew_timber_frame_brick", LIB, return_detail=True)
    common = 0.13 + 0.1025 / 0.77 + 0.18 + 0.009 / 0.13 + 0.0125 / 0.21 + 0.04
    ra, rb = common + 0.14 / 0.036, common + 0.14 / 0.13
    r_up = 1 / (0.85 / ra + 0.15 / rb)
    r_lo = common + 0.14 / (0.85 * 0.036 + 0.15 * 0.13)
    assert u_tf == pytest.approx(2.0 / (r_up + r_lo))
    assert abs(u_tf - u_mas) > 0.01  # the two brick-looking walls differ thermally


def test_ventilated_cavity_layers_ignored_and_rse_equals_rsi():
    u, d = u_value("ew_timber_frame_clad", LIB, return_detail=True)
    asm = LIB.assembly("ew_timber_frame_clad")
    assert d["rse"] == pytest.approx(asm.rsi)
    vi = d["ventilated_layer_index"]
    assert vi == 1
    assert all(not row["included"] for row in d["layers"][: vi + 1])
    # a heavy outer layer beyond the ventilated cavity does not change U
    heavy = asm.layers[0].model_copy(update={"thickness_m": 0.2, "in_thermal_calc": True})
    asm2 = asm.model_copy(update={"layers": [heavy] + asm.layers[1:]})
    assert u_value(asm2, LIB) == pytest.approx(u)


def test_missing_conductivity_and_no_thermal_layers_raise():
    lib, asm = three_layer_library()
    lib2 = lib.model_copy(update={"materials": [m if m.material_id != "ins" else m.model_copy(
        update={"conductivity_w_mk": None}) for m in lib.materials]})
    with pytest.raises(ThermalDataError):
        u_value(asm, lib2)
    empty = Assembly(assembly_id="e", name="e", element=ElementType.EXTERNAL_WALL, layers=[])
    with pytest.raises(ThermalDataError):
        u_value(empty, lib)
    with pytest.raises(ThermalDataError):
        u_value("no_such_assembly", lib)


def _slab_with_pir(thickness):
    a = LIB.assembly("gf_concrete_slab")
    layers = [l.model_copy(update={"thickness_m": thickness}) if l.material_id == "pir_100" else l
              for l in a.layers]
    return a.model_copy(update={"layers": layers})


def test_iso13370_hand_values_both_branches():
    lam, w = 2.0, 0.3
    # insulated slab, small floor: d_t >= B'
    a = LIB.assembly("gf_concrete_slab")
    rf = 0.10 / 0.022 + 0.10 / 1.65 + 0.065 / 1.4
    dt = w + lam * (0.17 + rf + 0.04)
    A, P = 70.0, 36.0
    B = A / (0.5 * P)
    assert dt >= B
    u, d = ground_floor_u(a, LIB, A, P, lambda_ground=lam, wall_thickness_m=w, return_detail=True)
    assert d["r_floor_m2k_w"] == pytest.approx(rf)
    assert u == pytest.approx(lam / (0.457 * B + dt))
    # uninsulated slab, large floor: d_t < B'
    un = a.model_copy(update={"layers": [l for l in a.layers if l.material_id != "pir_100"]})
    rf0 = 0.10 / 1.65 + 0.065 / 1.4
    dt0 = w + lam * (0.17 + rf0 + 0.04)
    A2, P2 = 400.0, 80.0
    B2 = A2 / (0.5 * P2)
    assert dt0 < B2
    u0 = ground_floor_u(un, LIB, A2, P2, lambda_ground=lam, wall_thickness_m=w)
    assert u0 == pytest.approx(2 * lam * math.log(math.pi * B2 / dt0 + 1) / (math.pi * B2 + dt0))
    assert 0.3 < u0 < 0.6  # sane range for a large uninsulated slab


def test_iso13370_decreases_with_insulation_and_size():
    us = [ground_floor_u(_slab_with_pir(t), LIB, 70.0, 36.0) for t in (0.0001, 0.05, 0.10, 0.15, 0.20)]
    assert all(a > b for a, b in zip(us, us[1:]))
    assert all(0.05 < u < 1.5 for u in us)
    # larger floor for the same perimeter (larger B') loses less per m2
    assert ground_floor_u("gf_concrete_slab", LIB, 140.0, 36.0) < ground_floor_u("gf_concrete_slab", LIB, 70.0, 36.0)
    assert ground_floor_u("gf_concrete_slab", LIB, 70.0, 0.0) == 0.0
    with pytest.raises(ValueError):
        ground_floor_u("gf_concrete_slab", LIB, 0.0, 36.0)


def test_heat_loss_box_hand_calculation():
    twin = box_twin()
    boq = calculate_quantities(twin, LIB)
    m = boq.geometry
    st = ProjectSettings(internal_design_temp_c=21.0, external_design_temp_c=-3.0, heating_degree_days=2200.0)
    hl = heat_loss(twin, m, LIB, st, thermal_bridging_y=0.1, air_change_rate=0.6)
    t = m.external_wall_thickness_m
    gia = (10 - 2 * t) * (8 - 2 * t)
    els = {e.element: e for e in hl.elements}
    assert set(els) == {"external_wall:B1", "window", "external_door", "pitched_roof:B1", "ground_floor"}
    assert els["external_wall:B1"].area_m2 == pytest.approx(36 * 2 * FTF - 1.44 - 2.1)
    assert els["window"].area_m2 == pytest.approx(1.44)
    assert els["external_door"].area_m2 == pytest.approx(2.1)
    assert els["pitched_roof:B1"].area_m2 == pytest.approx(gia)
    assert els["pitched_roof:B1"].u_value == pytest.approx(u_value("pr_tiled_cold", LIB))
    assert els["ground_floor"].area_m2 == pytest.approx(gia)
    assert els["ground_floor"].u_value == pytest.approx(ground_floor_u("gf_concrete_slab", LIB, gia, 36.0,
                                                                       wall_thickness_m=t))
    fabric = sum(e.u_value * e.area_m2 for e in hl.elements)
    exposed = sum(e.area_m2 for e in hl.elements)
    vent = 0.33 * 0.6 * 2 * gia * FTF
    assert hl.fabric_ua_w_k == pytest.approx(fabric)
    assert hl.thermal_bridging_w_k == pytest.approx(0.1 * exposed)
    assert hl.ventilation_w_k == pytest.approx(vent)
    assert hl.heat_loss_coefficient_w_k == pytest.approx(fabric + 0.1 * exposed + vent)
    assert hl.design_delta_t_k == pytest.approx(24.0)
    assert hl.peak_heat_load_kw == pytest.approx(hl.heat_loss_coefficient_w_k * 24.0 / 1000)
    assert hl.annual_space_heat_kwh == pytest.approx(hl.heat_loss_coefficient_w_k * 2200 * 24 / 1000)
    assert hl.hlp_w_m2k == pytest.approx(hl.heat_loss_coefficient_w_k / (2 * gia))
    assert hl.basis == Basis.ASSUMED
    assert any("not SAP" in c for c in hl.caveats) and any("compliance" in c for c in hl.caveats)


def test_heat_loss_demo_heated_blocks_and_unheated_garage(demo):
    twin, boq = demo
    hl = heat_loss(twin, boq.geometry, LIB, twin.settings)
    names = [e.element for e in hl.elements]
    assert not any("garage" in n and not n.startswith("wall_to_unheated") for n in names)
    assert "garage_door" not in names  # garage door is on the unheated block
    sep = [e for e in hl.elements if e.element.startswith("wall_to_unheated")]
    assert len(sep) == 1 and sep[0].b_factor == pytest.approx(0.5)
    assert sep[0].area_m2 == pytest.approx(6.0 * FTF)  # garage depth x garage storey height
    asm = LIB.assembly("sw_masonry_separating")
    assert sep[0].u_value == pytest.approx(u_value(asm, LIB, rse_override=asm.rsi))
    assert sep[0].ua_w_k == pytest.approx(sep[0].u_value * sep[0].area_m2 * 0.5)
    assert {"flat_roof:ext", "pitched_roof:main", "external_wall:ext"} <= set(names)
    fabric = sum(e.u_value * e.area_m2 * e.b_factor for e in hl.elements)
    exposed = sum(e.area_m2 for e in hl.elements)
    assert hl.heat_loss_coefficient_w_k == pytest.approx(fabric + 0.15 * exposed
                                                         + 0.33 * 0.5 * boq.geometry.heated_volume_m3)
    dt = twin.settings.internal_design_temp_c - twin.settings.external_design_temp_c
    assert hl.peak_heat_load_kw == pytest.approx(hl.heat_loss_coefficient_w_k * dt / 1000)
    # ground floor uses the heated exposed perimeter incl. the wall to the garage
    assert hl.assumptions["ground_floor_exposed_perimeter_m"] == pytest.approx(
        (9.6 + 8.4 + 8.4 + (9.6 - 4.8)) + (3.6 + 4.8 + 3.6))
    # unheated block outside the envelope: volume / GIA from heated blocks only
    assert hl.assumptions["heated_gia_m2"] == pytest.approx(boq.geometry.heated_gia_m2)
    # y and n scale linearly
    hl2 = heat_loss(twin, boq.geometry, LIB, twin.settings, thermal_bridging_y=0.0, air_change_rate=0.0)
    assert hl2.heat_loss_coefficient_w_k == pytest.approx(hl.fabric_ua_w_k)


def test_heat_loss_masonry_vs_timber_frame_and_metrics_none():
    twin = box_twin()
    tf = apply_construction_assemblies(twin, {"external_wall": "ew_timber_frame_brick"}, LIB)
    a = heat_loss(twin, None, LIB)
    b = heat_loss(tf, None, LIB)
    wa = next(e for e in a.elements if e.element == "external_wall:B1")
    wb = next(e for e in b.elements if e.element == "external_wall:B1")
    assert wa.assembly_id == "ew_masonry_cavity" and wb.assembly_id == "ew_timber_frame_brick"
    assert wa.u_value != pytest.approx(wb.u_value)
    assert a.heat_loss_coefficient_w_k != pytest.approx(b.heat_loss_coefficient_w_k)
    assert wb.basis == Basis.ASSUMED  # user-confirmed selection, but U from illustrative data
    with pytest.raises(ValueError):
        heat_loss(twin, None, LIB, thermal_bridging_y=-0.1)


# =============================================================================
# Carbon
# =============================================================================
def _carbon_boq(boq, lines):
    return boq.model_copy(update={"lines": lines})


def test_carbon_mass_conversions_per_unit_type(demo):
    _, boq = demo
    lib = LIB.model_copy(update={"materials": [m if m.material_id != "dpm_1200g" else m.model_copy(
        update={"carbon_kgco2e_per_kg": None}) for m in LIB.materials]})
    wool_i = layer_idx("ew_timber_frame_brick", "mineral_wool_140_stud")
    lines = [
        qline("conc", "concrete_c25", "m3", 2.0, code="1", assembly_id="fdn_trench_fill", layer_index=3, waste=0.1),
        qline("pb", "plasterboard_12_5", "m2", 10.0, code="2.7", assembly_id="ip_timber_stud", layer_index=0,
              cutting=0.8, waste=0.5),
        qline("mem", "breather_membrane", "m2", 50.0, assembly_id="ew_timber_frame_brick",
              layer_index=layer_idx("ew_timber_frame_brick", "breather_membrane")),
        qline("brk", "facing_brick", "nr", 100.0, assembly_id="ew_masonry_cavity", layer_index=0, waste=5.0),
        qline("stud", "timber_stud_140x38", "m", 48.0, assembly_id="ew_timber_frame_brick",
              layer_index=layer_idx("ew_timber_frame_brick", "timber_stud_140x38")),
        qline("steel", "steel_beam", "kg", 50.0, code="2.1", status=QuantityStatus.ALLOWANCE,
              allowance_id="structural_steel"),
        qline("wool", "mineral_wool_140_stud", "m2", 10.0, assembly_id="ew_timber_frame_brick", layer_index=wool_i),
        qline("air", "air_cavity_50", "m2", 10.0, assembly_id="ew_timber_frame_brick",
              layer_index=layer_idx("ew_timber_frame_brick", "air_cavity_50")),
        qline("nofactor", "dpm_1200g", "m2", 10.0, code="1"),
        qline("unknown", "unobtainium", "m2", 10.0),
        qline("unres", "facing_brick", "nr", None, status=QuantityStatus.UNRESOLVED),
        qline("kitchen", None, "nr", 1.0, code="4", status=QuantityStatus.ALLOWANCE, allowance_id="kitchen"),
    ]
    r = embodied_carbon(_carbon_boq(boq, lines), lib)
    cl = {c.quantity_line_id: c for c in r.lines}
    assert cl["conc"].mass_kg == pytest.approx(2.0 * 2400)
    assert cl["conc"].a1_a3_kgco2e == pytest.approx(2.0 * 2400 * 0.10)
    assert cl["conc"].a5_waste_kgco2e == pytest.approx(0.1 * 2400 * 0.10)
    assert cl["pb"].mass_kg == pytest.approx(10 * 0.0125 * 700)  # m2 x layer thickness x density
    assert cl["pb"].waste_mass_kg == pytest.approx(1.3 * 0.0125 * 700)
    assert cl["mem"].mass_kg == pytest.approx(50 * 6.5 / 50)  # zero-thickness layer -> roll mass x ppi
    assert cl["brk"].mass_kg == pytest.approx(100 * 2.5)  # nr x unit mass
    assert cl["brk"].a5_waste_kgco2e == pytest.approx(5 * 2.5 * 0.22)
    assert cl["stud"].mass_kg == pytest.approx(48 * 12.0 / 4.8)  # m x length mass / length
    assert cl["steel"].mass_kg == pytest.approx(50.0)  # kg direct
    assert cl["wool"].mass_kg == pytest.approx(10 * 0.14 * 18 * (1 - 0.15))  # unbridged fraction only
    assert "air" not in cl  # thermal-only pseudo-material skipped
    um = " | ".join(r.unmatched)
    for lid in ("nofactor", "unknown", "unres", "kitchen"):
        assert lid in um
    assert "air" not in um
    assert r.total_a1_a3_kgco2e == pytest.approx(sum(c.a1_a3_kgco2e for c in r.lines))
    assert r.total_a5_waste_kgco2e == pytest.approx(sum(c.a5_waste_kgco2e for c in r.lines))
    assert sum(r.by_element.values()) == pytest.approx(r.total_a1_a3_kgco2e + r.total_a5_waste_kgco2e)
    assert r.a4_transport_kgco2e == 0.0
    assert any("A4" in c for c in r.caveats)


def test_carbon_demo_totals_per_m2_and_a4(demo):
    twin, boq = demo
    r = embodied_carbon(boq, LIB)
    assert r.total_a1_a3_kgco2e > 0 and r.total_a5_waste_kgco2e > 0
    assert r.per_m2_gia_kgco2e == pytest.approx(r.total_kgco2e / boq.geometry.gia_m2)
    assert any("placeholder" in c.lower() or "illustrative" in c.lower() for c in r.caveats)
    assert "illustrative" in r.factor_source.lower()
    assert r.basis == Basis.ASSUMED
    assert any("allow.kitchen" in u for u in r.unmatched)
    prog = build_programme(boq, LIB)
    lg = plan_deliveries(boq, LIB, prog)
    r4 = embodied_carbon(boq, LIB, logistics=lg, a4_kgco2e_per_load_km=0.9, distance_km=25.0)
    assert r4.a4_transport_kgco2e == pytest.approx(lg.total_loads * 25.0 * 0.9)
    assert r4.total_kgco2e == pytest.approx(r.total_kgco2e + r4.a4_transport_kgco2e)
    assert "A4" in r4.boundary
    with pytest.raises(ValueError):
        embodied_carbon(boq, LIB, a4_kgco2e_per_load_km=-1.0)


def test_carbon_timber_frame_differs_from_masonry():
    twin = box_twin()
    tf = apply_construction_assemblies(twin, {"external_wall": "ew_timber_frame_brick"}, LIB)
    a = embodied_carbon(calculate_quantities(twin, LIB), LIB)
    b = embodied_carbon(calculate_quantities(tf, LIB), LIB)
    assert a.by_element["2.5 External walls"] != pytest.approx(b.by_element["2.5 External walls"])


# =============================================================================
# Programme (CPM)
# =============================================================================
def _t(tid, dur, preds=(), lag=0.0, lead=0.0):
    return TaskSpec(task_id=tid, name=tid, trade="general", labour_hours=0.0, crew_size=1.0, duration_days=dur,
                    predecessors=list(preds), lag_days=lag, material_lead_time_days=lead)


def test_cpm_hand_network():
    tasks = [_t("A", 3), _t("B", 2, ["A"]), _t("C", 4, ["A"]), _t("D", 1, ["B", "C"])]
    out, dur, crit = critical_path_method(tasks)
    s = {t.task_id: t for t in out}
    assert dur == pytest.approx(8.0)
    assert (s["A"].earliest_start, s["A"].earliest_finish) == (0.0, 3.0)
    assert (s["B"].earliest_start, s["B"].earliest_finish) == (3.0, 5.0)
    assert (s["C"].earliest_start, s["C"].earliest_finish) == (3.0, 7.0)
    assert (s["D"].earliest_start, s["D"].earliest_finish) == (7.0, 8.0)
    assert (s["B"].latest_start, s["B"].latest_finish) == (5.0, 7.0)
    assert s["B"].total_float == pytest.approx(2.0)
    assert all(s[i].total_float == 0.0 and s[i].critical for i in ("A", "C", "D"))
    assert not s["B"].critical
    assert crit == ["A", "C", "D"]
    assert [t.task_id for t in out] == ["A", "B", "C", "D"]  # input order kept


def test_cpm_lag_lead_and_errors():
    out, dur, crit = critical_path_method([_t("A", 3), _t("B", 2, ["A"], lag=1.0), _t("L", 0, lead=10.0),
                                           _t("C", 1, ["B", "L"])])
    s = {t.task_id: t for t in out}
    assert s["B"].earliest_start == pytest.approx(4.0)
    assert s["L"].earliest_start == pytest.approx(10.0)  # start-no-earlier-than (lead time from day 0)
    assert s["C"].earliest_start == pytest.approx(10.0)
    assert dur == pytest.approx(11.0)
    assert s["A"].total_float == pytest.approx(4.0) and s["B"].total_float == pytest.approx(4.0)
    assert crit == ["L", "C"]
    with pytest.raises(ValueError):
        critical_path_method([_t("A", 1, ["B"]), _t("B", 1, ["A"])])
    with pytest.raises(ValueError):
        critical_path_method([_t("A", 1, ["X"])])
    with pytest.raises(ValueError):
        critical_path_method([_t("A", 1), _t("A", 2)])


def test_programme_structure_and_labour(demo):
    _, boq = demo
    p = build_programme(boq, LIB)
    ids = [t.task_id for t in p.tasks]
    assert ids[0] == "setup" and ids[-1] == "externals_handover"
    s = {t.task_id: t for t in p.tasks}
    resolved_hours = sum(ln.labour_hours or 0.0 for ln in boq.lines)
    assert p.total_labour_hours == pytest.approx(resolved_hours)
    assert sum(p.labour_hours_by_trade.values()) == pytest.approx(p.total_labour_hours)
    assert sum(t.labour_hours for t in p.tasks) == pytest.approx(p.total_labour_hours)
    for t in p.tasks:
        if t.labour_hours > 0 and t.task_id not in ("setup", "externals_handover"):
            assert t.duration_days == pytest.approx(max(1.0, t.labour_hours / (t.crew_size * 8)))
    # sequencing constraints from the network
    assert s["superstructure"].earliest_start >= s["ground_slab"].earliest_finish - 1e-9
    assert s["first_fix"].earliest_start >= max(s["roof"].earliest_finish, s["windows_doors"].earliest_finish) - 1e-9
    assert s["plaster_drylining"].earliest_start >= max(s["first_fix"].earliest_finish,
                                                        s["partitions"].earliest_finish) - 1e-9
    assert p.duration_days == pytest.approx(s["externals_handover"].earliest_finish)
    assert p.duration_weeks == pytest.approx(p.duration_days / 5)
    assert p.critical_path[-1] == "externals_handover"
    assert any("not a validated programme" in c for c in p.caveats)
    # mapping: services split 50/50, screed with the wet trades, slab with groundworks
    sh = assign_lines_to_tasks(boq, LIB)
    assert sh["5.allow.plumbing_heating"] == [("first_fix", 0.5), ("second_fix", 0.5)]
    screed = next(ln for ln in boq.lines if ln.material_id == "screed_sand_cement")
    assert sh[screed.line_id] == [("plaster_drylining", 1.0)]
    slab = next(ln for ln in boq.lines if ln.material_id == "concrete_c25" and ln.assembly_id == "gf_concrete_slab")
    assert sh[slab.line_id] == [("ground_slab", 1.0)]
    assert slab.line_id in s["ground_slab"].line_ids


def test_programme_multipliers_and_crews(demo):
    _, boq = demo
    base = build_programme(boq, LIB, lead_time_weeks={"window_upvc_dg": 0, "door_composite": 0,
                                                      "garage_door_sectional": 0})
    slow = build_programme(boq, LIB, labour_multipliers={"bricklaying": 2.0},
                           lead_time_weeks={"window_upvc_dg": 0, "door_composite": 0, "garage_door_sectional": 0})
    b, s = base.task("superstructure"), slow.task("superstructure")
    assert s.labour_hours > b.labour_hours
    assert slow.labour_hours_by_trade["bricklaying"] == pytest.approx(2 * base.labour_hours_by_trade["bricklaying"])
    assert slow.duration_days > base.duration_days
    big = build_programme(boq, LIB, crew_sizes={"superstructure": 8})
    assert big.task("superstructure").duration_days == pytest.approx(
        build_programme(boq, LIB).task("superstructure").labour_hours / (8 * 8))
    with pytest.raises(ValueError):
        build_programme(boq, LIB, crew_sizes={"roof": 0})


def test_window_lead_time_delays_windows_and_end_date(demo):
    _, boq = demo
    zero = {"window_upvc_dg": 0, "door_composite": 0, "garage_door_sectional": 0}
    p0 = build_programme(boq, LIB, lead_time_weeks=zero)
    p8 = build_programme(boq, LIB, lead_time_weeks={**zero, "window_upvc_dg": 8})
    p20 = build_programme(boq, LIB, lead_time_weeks={**zero, "window_upvc_dg": 20})
    w0, w8, w20 = (p.task("windows_doors") for p in (p0, p8, p20))
    # without lead time windows follow the roof
    assert w0.earliest_start == pytest.approx(p0.task("roof").earliest_finish)
    assert w8.material_lead_time_days == pytest.approx(40.0)
    assert w8.earliest_start == pytest.approx(max(40.0, p8.task("roof").earliest_finish))
    assert w20.earliest_start == pytest.approx(100.0)
    assert w20.earliest_start > w8.earliest_start >= w0.earliest_start
    # lead time on the critical path delays the end date one-for-one
    assert "procure_windows_doors" in p20.critical_path and w20.critical
    assert p20.duration_days - p8.duration_days == pytest.approx(w20.earliest_start - w8.earliest_start)
    assert p20.duration_days > p0.duration_days
    assert p0.task("procure_windows_doors").duration_days == 0.0
    # library default lead time (8 weeks) is used without overrides
    assert build_programme(boq, LIB).task("windows_doors").material_lead_time_days == pytest.approx(40.0)
    # ARCHITECTURE alias keyword
    alias = build_programme(boq, LIB, lead_times={**zero, "window_upvc_dg": 20})
    assert alias.duration_days == pytest.approx(p20.duration_days)
    with pytest.raises(ValueError):
        build_programme(boq, LIB, lead_times=zero, lead_time_weeks=zero)


# =============================================================================
# Logistics
# =============================================================================
def test_logistics_hand_loads_storage_and_peak(demo):
    _, boq = demo
    roof_i = layer_idx("pr_tiled_cold", "roof_tile_concrete")
    lines = [
        qline("conc", "concrete_c25", "m3", 12.5, code="1", assembly_id="fdn_trench_fill", layer_index=3,
              waste=0.5, purchased=13.0),
        qline("brk", "facing_brick", "nr", 4800.0, assembly_id="ew_masonry_cavity", layer_index=0, waste=200.0,
              purchased=5000.0),
        qline("tile", "roof_tile_concrete", "nr", 1000.0, code="2.3", assembly_id="pr_tiled_cold",
              layer_index=roof_i, purchased=1200.0),
    ]
    hb = _carbon_boq(boq, lines)
    prog = hand_programme([task("substructure", 0, 5), task("superstructure", 5, 20), task("roof", 18, 25)])
    lg = plan_deliveries(hb, LIB, prog, lead_time_weeks={"facing_brick": 4})
    b = {x.batch_id: x for x in lg.batches}
    rm = b["substructure:ready_mix_concrete"]
    assert rm.ready_mix and rm.loads == 3  # ceil(13 / 6)
    assert rm.storage_area_m2 == 0.0 and rm.delivery_day == 0.0
    brk = b["superstructure:masonry"]
    assert brk.mass_kg == pytest.approx(5000 * 2.5)
    assert brk.volume_m3 == pytest.approx(5000 * 0.00143)
    assert brk.loads == 2  # ceil(12.5 t / 10 t)
    assert brk.required_by_day == 5.0 and brk.delivery_day == 3.0
    assert brk.order_by_day == pytest.approx(3.0 - 20.0)  # 4 weeks x 5 days lead time
    assert brk.storage_area_m2 == pytest.approx(5000 * 0.00143 / 1.5 * 1.3)
    tile = b["roof:roofing"]
    assert tile.loads == math.ceil(max(1200 * 4.4 / 10000, 1200 * 0.0035 / 30) - 1e-9)
    # bricks (day 3-20) and tiles (day 16-25) overlap -> peak is their sum
    assert lg.peak_storage_area_m2 == pytest.approx(brk.storage_area_m2 + tile.storage_area_m2)
    assert lg.total_loads == 3 + 2 + tile.loads
    assert lg.total_mass_t == pytest.approx((13 * 2400 + 5000 * 2.5 + 1200 * 4.4) / 1000)
    solid = 0.5 + 200 * 0.00143
    assert lg.assumptions["waste_solid_volume_m3"] == pytest.approx(solid)
    assert lg.waste_volume_m3 == pytest.approx(solid * 1.6)
    assert lg.skips == math.ceil(solid * 1.6 / 6.0)
    assert any("before the programme start" in w for w in lg.warnings)
    # non-overlapping windows: peak is the larger single batch
    prog2 = hand_programme([task("substructure", 0, 5), task("superstructure", 5, 10), task("roof", 30, 35)])
    lg2 = plan_deliveries(hb, LIB, prog2)
    b2 = {x.batch_id: x for x in lg2.batches}
    assert lg2.peak_storage_area_m2 == pytest.approx(max(b2["superstructure:masonry"].storage_area_m2,
                                                         b2["roof:roofing"].storage_area_m2))


def test_logistics_demo_invariants(demo):
    _, boq = demo
    prog = build_programme(boq, LIB)
    lg = plan_deliveries(boq, LIB, prog)
    assert lg.total_loads == sum(b.loads for b in lg.batches)
    for b in lg.batches:
        if b.ready_mix:
            assert b.loads == math.ceil(b.volume_m3 / 6.0 - 1e-9)
            assert b.storage_area_m2 == 0.0
        elif b.delivery_category != "allowance_items":
            assert b.loads == max(1, math.ceil(max(b.mass_kg / 10000, b.volume_m3 / 30) - 1e-9))
            assert b.storage_area_m2 == pytest.approx(b.volume_m3 / 1.5 * 1.3)
        assert b.order_by_day == pytest.approx(b.delivery_day - b.lead_time_days)
        assert b.delivery_day <= b.required_by_day + 1e-9
    # windows ordered at day 0 cannot arrive before their lead time
    win = next(b for b in lg.batches if b.task_id == "windows_doors" and not b.delivery_category.startswith("allow"))
    assert win.delivery_day >= prog.task("windows_doors").material_lead_time_days - 1e-9
    assert win.order_by_day >= -1e-9
    stor = [b.storage_area_m2 for b in lg.batches]
    assert max(stor) - 1e-9 <= lg.peak_storage_area_m2 <= sum(stor) + 1e-9
    assert lg.skips == math.ceil(lg.waste_volume_m3 / 6.0 - 1e-9)
    assert lg.total_mass_t > 50
    assert lg.caveats
    with pytest.raises(ValueError):
        plan_deliveries(boq, LIB, prog, vehicle_payload_t=0)


# =============================================================================
# Adapters
# =============================================================================
def test_not_configured_adapters_raise_with_guidance(demo):
    twin, boq = demo
    s, e, c = NotConfiguredStructuralAdapter(), NotConfiguredEnergyAdapter(), NotConfiguredCarbonDataAdapter()
    assert isinstance(s, StructuralAnalysisAdapter)
    assert isinstance(e, EnergyAnalysisAdapter)
    assert isinstance(c, EmbodiedCarbonDataAdapter)
    assert not (s.is_available() or e.is_available() or c.is_available())
    with pytest.raises(AdapterNotConfigured, match="structural engineer"):
        s.analyse(twin, boq.geometry, LIB)
    with pytest.raises(AdapterNotConfigured, match="SAP"):
        e.calculate(twin, boq.geometry, LIB, twin.settings)
    with pytest.raises(AdapterNotConfigured):
        c.factor_for(LIB.material("facing_brick"))
    with pytest.raises(AdapterNotConfigured):
        apply_carbon_factors(LIB, c)
    assert default_engineering_adapters().status() == {"structural": False, "energy": False, "carbon_data": False}


def test_static_carbon_adapter_applies_factors_without_mutation(demo):
    _, boq = demo
    ad = StaticCarbonFactorAdapter({"facing_brick": 0.30}, source="User-verified dataset extract", dataset_version="v1")
    assert isinstance(ad, EmbodiedCarbonDataAdapter)
    lib2, rep = apply_carbon_factors(LIB, ad)
    assert rep["matched"] == ["facing_brick"] and "concrete_c25" in rep["unmatched"]
    assert lib2.material("facing_brick").carbon_kgco2e_per_kg == pytest.approx(0.30)
    assert "User-verified" in lib2.material("facing_brick").carbon_source
    assert LIB.material("facing_brick").carbon_kgco2e_per_kg == pytest.approx(0.22)  # input unchanged
    a, b = embodied_carbon(boq, LIB), embodied_carbon(boq, lib2)
    assert b.total_a1_a3_kgco2e > a.total_a1_a3_kgco2e
    # provenance of factors is reported honestly: mixed sources -> placeholders still flagged
    assert "User-verified" in b.factor_source and "placeholder" in b.factor_source
    all_mats = {m.material_id: 0.1 for m in LIB.materials}
    lib3, _ = apply_carbon_factors(LIB, StaticCarbonFactorAdapter(all_mats, source="User dataset"))
    c = embodied_carbon(boq, lib3)
    assert "placeholder" not in c.factor_source and c.factor_source.startswith("Carbon factors from")
    with pytest.raises(ValueError):
        StaticCarbonFactorAdapter({"x": -1.0}, source="s")
    with pytest.raises(ValueError):
        StaticCarbonFactorAdapter({"x": 1.0}, source=" ")


# =============================================================================
# Determinism
# =============================================================================
def test_simulations_are_deterministic():
    def run():
        twin = demo_twin()
        boq = calculate_quantities(twin, LIB)
        hl = heat_loss(twin, boq.geometry, LIB, twin.settings)
        c = embodied_carbon(boq, LIB)
        p = build_programme(boq, LIB)
        lg = plan_deliveries(boq, LIB, p)
        return [json.dumps(x.model_dump(mode="json"), sort_keys=True) for x in (hl, c, p, lg)]

    assert run() == run()


def test_wall_thickness_consistency_for_metrics_none():
    twin = demo_twin()
    t_ext, t_sep = wall_thicknesses(twin, LIB)
    boq = calculate_quantities(twin, LIB)
    assert boq.geometry.external_wall_thickness_m == pytest.approx(t_ext)
    a = heat_loss(twin, boq.geometry, LIB)
    b = heat_loss(twin, None, LIB)
    assert a.heat_loss_coefficient_w_k == pytest.approx(b.heat_loss_coefficient_w_k)
