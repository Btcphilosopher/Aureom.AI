"""Regression tests for the review fixes to geometry and quantity take-off (group B).

GEO-2  openings on a storey the block does not have: not deducted, never counted as windows/doors.
GEO-6  opening groups whose assembly belongs to another element keep unique, stable line ids.
GEO-9  roof linear items where a roof meets a taller block (half-verge eaves overhang, monopitch
       verge / ridge / eaves ends, abutment along the rake, taller wall inside a lower roof void).
GEO-10 hip ridge_axis that disagrees with the longer side is flagged in both directions.
GEO-11 oversite dig excludes the trench plan inside the GIA (no double-counted excavation).
GEO-12 separating-wall finishes only on faces towards heated blocks.

All expected values are hand calculations.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from housebuilder_vision.core.models import (
    Block,
    BlockRole,
    BuildingTwin,
    ElementType,
    HiddenSideAssumptions,
    Opening,
    OpeningKind,
    QuantityStatus,
    RoofForm,
    RoofSpec,
    Side,
)
from housebuilder_vision.core.provenance import Basis, TrackedValue, assumed, unknown
from housebuilder_vision.geometry import BlockParams, OpeningParams, compute_metrics
from housebuilder_vision.geometry.metrics import ground_internal_area, roof_void_wall_areas
from housebuilder_vision.quantities import (
    apply_construction_assemblies,
    calculate_quantities,
    default_library,
    default_selection,
    element_measures,
    wall_thicknesses,
)
from housebuilder_vision.quantities.measures import MEASURES, opening_instance_id, unresolved_instances

LIB = default_library()
FFL, FTF = 0.15, 2.7
C30 = math.cos(math.radians(30.0))


# ---------------------------------------------------------------- helpers
def bp(bid, x0, y0, w, d, storeys=2, form=RoofForm.GABLE, pitch=35.0, axis="x", eo=0.0, vo=0.0, high=None,
       parapet=0.0, heated=True, ftf=FTF):
    return BlockParams(bid, x0, y0, w, d, storeys, ftf, FFL, form, pitch, axis, eo, vo, high, parapet, heated)


def tv(v, unit="m", basis=Basis.USER_CONFIRMED):
    return TrackedValue(value=v, unit=unit, basis=basis)


def blk(bid, x0, y0, w, d, storeys=2, form=RoofForm.GABLE, pitch=35.0, axis="x", eo=0.3, vo=0.2, heated=True,
        role=BlockRole.MAIN):
    return Block(block_id=bid, role=role, origin_x=tv(x0), origin_y=tv(y0), width=tv(w), depth=tv(d),
                 storeys=tv(storeys, "storeys"), floor_to_floor=tv(FTF), ground_floor_level=tv(FFL),
                 roof=RoofSpec(form=form, pitch_deg=tv(pitch, "deg"), ridge_axis=axis, eaves_overhang_m=tv(eo),
                               verge_overhang_m=tv(vo)),
                 heated=heated)


def op(oid, bid, side, kind, storey, off, w, h, sill, **kw):
    return Opening(opening_id=oid, block_id=bid, side=side, kind=kind, storey=storey, offset_m=tv(off),
                   width_m=tv(w), height_m=tv(h), sill_m=tv(sill), **kw)


def make_twin(blocks, openings=()):
    return BuildingTwin(
        twin_id="t_review", blocks=list(blocks), openings=list(openings),
        hidden=HiddenSideAssumptions(rear_glazing_ratio=assumed(0.2, "fraction"),
                                     side_glazing_ratio=assumed(0.04, "fraction")),
        assemblies=default_selection(LIB))


def demo_twin(main_storeys=2, garage_axis="y"):
    blocks = [
        blk("main", 0, 0, 9.6, 8.4, storeys=main_storeys),
        blk("garage", 9.6, 0, 3.2, 6.0, storeys=1, pitch=30.0, axis=garage_axis, heated=False,
            role=BlockRole.GARAGE),
    ]
    ops = [
        op("W1", "main", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.8, 1.2, 0.9),
        op("D1", "main", Side.FRONT, OpeningKind.DOOR, 0, 4.3, 1.0, 2.1, 0.0),
        op("W2", "main", Side.FRONT, OpeningKind.WINDOW, 0, 6.8, 1.8, 1.2, 0.9),
        op("W3", "main", Side.FRONT, OpeningKind.WINDOW, 1, 1.3, 1.2, 1.2, 0.9),
        op("W4", "main", Side.REAR, OpeningKind.WINDOW, 1, 1.0, 1.2, 1.2, 0.9, hidden_side_rule="rear_glazing"),
        op("G1", "garage", Side.FRONT, OpeningKind.GARAGE_DOOR, 0, 0.4, 2.4, 2.13, 0.0),
    ]
    return make_twin(blocks, ops)


def layer_index(assembly_id, material_id, nth=0):
    return [i for i, layer in enumerate(LIB.assembly(assembly_id).layers) if layer.material_id == material_id][nth]


def roof(m, bid):
    return next(r for r in m.roofs if r.block_id == bid)


def measures_of(twin, element, block_id=None):
    boq = calculate_quantities(twin, LIB)
    insts = element_measures(twin, boq.geometry, LIB)
    return next(i for i in insts if i.element == element and (block_id is None or i.block_id == block_id))


def assert_unique_line_ids(boq):
    dup = [k for k, n in Counter(ln.line_id for ln in boq.lines).items() if n > 1]
    assert not dup, f"duplicate line ids: {dup}"


# ===================================================================== GEO-2
def test_metrics_do_not_deduct_openings_on_missing_storeys():
    ops = [OpeningParams("W0", "B1", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.2, 1.2, 0.9),
           OpeningParams("W1", "B1", Side.FRONT, OpeningKind.WINDOW, 1, 1.0, 1.2, 1.2, 0.9)]
    m = compute_metrics([bp("B1", 0, 0, 10, 8, storeys=1)], ops, 0.3, 0.2)
    front = next(p for p in m.pieces if p.side == Side.FRONT)
    assert front.opening_ids == ["W0"]
    assert m.window_area_m2 == pytest.approx(1.44)
    assert m.external_wall_gross_m2 - m.external_wall_net_m2 == pytest.approx(1.44)
    assert any("W1" in w and "not deducted" in w for w in m.warnings)
    assert not any("W1" in w and "above the wall/roof line" in w for w in m.warnings)


def test_reducing_storeys_excludes_upper_openings_from_windows_and_walls():
    two, one = calculate_quantities(demo_twin(2), LIB), calculate_quantities(demo_twin(1), LIB)
    g = one.geometry
    # W3 (front, storey 1) and W4 (rear, storey 1) cannot exist on a one-storey block
    assert not any(oid in p.opening_ids for p in g.pieces for oid in ("W3", "W4"))
    assert g.window_area_m2 == pytest.approx(2 * 1.8 * 1.2)
    win = one.line("2.6.all.win_upvc_dg.0")
    assert win.installed_qty == pytest.approx(g.window_area_m2)
    assert set(win.geometry_refs) == {"W1", "W2"}
    assert two.line("2.6.all.win_upvc_dg.0").installed_qty == pytest.approx(2 * 2.16 + 2 * 1.44)
    # walls are no longer under-measured: net = gross - storey-0 openings only
    main_wall = next(i for i in element_measures(demo_twin(1), g, LIB)
                     if i.element == ElementType.EXTERNAL_WALL and i.block_id == "main")
    assert main_wall.measures["opening_count"].value == 3  # W1, D1, W2
    assert main_wall.measures["element_area"].value == pytest.approx(
        main_wall.measures["gross_area"].value - (2 * 2.16 + 2.1))
    brick = one.line(f"2.5.main.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'facing_brick')}")
    assert brick.installed_qty == pytest.approx(main_wall.measures["element_area"].value * 60)
    # one warning per excluded opening (from metrics), naming it
    for oid in ("W3", "W4"):
        assert sum(oid in w for w in one.warnings) == 1


def test_unknown_size_opening_on_missing_storey_is_excluded_not_unresolved():
    twin = demo_twin(1)
    ops = [o.model_copy(update={"width_m": unknown("m")}) if o.opening_id == "W3" else o for o in twin.openings]
    boq = calculate_quantities(twin.model_copy(update={"openings": ops}), LIB)
    assert boq.line("2.6.all.win_upvc_dg.0").status == QuantityStatus.DERIVED
    brick = f"2.5.main.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'facing_brick')}"
    assert boq.line(brick).status == QuantityStatus.DERIVED
    assert any("W3" in w and "storey" in w for w in boq.warnings)
    assert not any("W3" in w and "dependent quantities are unresolved" in w for w in boq.warnings)


# ===================================================================== GEO-6
def test_wrong_element_assembly_override_keeps_line_ids_unique():
    twin = demo_twin()
    ops = [o.model_copy(update={"assembly_id": "win_upvc_dg"}) if o.opening_id == "D1" else o for o in twin.openings]
    boq = calculate_quantities(twin.model_copy(update={"openings": ops}), LIB)
    assert_unique_line_ids(boq)
    win = boq.line("2.6.all.win_upvc_dg.0")
    assert win.status == QuantityStatus.DERIVED and set(win.geometry_refs) == {"W1", "W2", "W3", "W4"}
    door = boq.line("2.6.all-external_door.win_upvc_dg.0")
    assert door.status == QuantityStatus.UNRESOLVED and "not a external_door assembly" in door.formula
    # ids of the other groups do not depend on the override
    base = {ln.line_id for ln in calculate_quantities(twin, LIB).lines}
    assert "2.6.all.win_upvc_dg.0" in base and "2.6.all.gdoor_steel_sectional.0" in base


def test_opening_instance_id_rule():
    assert opening_instance_id(ElementType.WINDOW, "win_upvc_dg", LIB) == "all"
    assert opening_instance_id(ElementType.EXTERNAL_DOOR, "win_upvc_dg", LIB) == "all-external_door"
    assert opening_instance_id(ElementType.WINDOW, "win_not_in_library", LIB) == "all-window"


def test_unknown_opening_assemblies_stay_unique_in_both_paths():
    twin = demo_twin()
    ops = [o.model_copy(update={"assembly_id": "custom_unit"}) if o.opening_id in ("W1", "D1") else o
           for o in twin.openings]
    t2 = twin.model_copy(update={"openings": ops})
    boq = calculate_quantities(t2, LIB)
    assert_unique_line_ids(boq)
    assert boq.line("2.6.all-window.custom_unit.0").status == QuantityStatus.UNRESOLVED
    assert boq.line("2.6.all-external_door.custom_unit.0").status == QuantityStatus.UNRESOLVED
    # geometry-unresolved path enumerates the same instance ids
    ids = {(i.element, i.instance_id, i.assembly_id) for i in unresolved_instances(t2, LIB, "test")}
    assert (ElementType.WINDOW, "all-window", "custom_unit") in ids
    assert (ElementType.EXTERNAL_DOOR, "all-external_door", "custom_unit") in ids


@pytest.mark.parametrize("variant", ["demo", "one_storey", "garage_x", "door_override", "piled", "overlap"])
def test_all_boq_line_ids_are_unique(variant):
    twin = demo_twin(1 if variant == "one_storey" else 2, garage_axis="x" if variant == "garage_x" else "y")
    if variant == "door_override":
        twin = twin.model_copy(update={"openings": [
            o.model_copy(update={"assembly_id": "win_alu_tg"}) if o.kind == OpeningKind.DOOR else o
            for o in twin.openings]})
    if variant == "piled":
        twin = apply_construction_assemblies(twin, {"foundation": "fdn_piled_allowance"}, LIB)
    if variant == "overlap":
        twin = twin.model_copy(update={"blocks": [twin.blocks[0], blk("garage", 9.0, 0, 3.2, 6.0, storeys=1)]})
    assert_unique_line_ids(calculate_quantities(twin, LIB))


# ===================================================================== GEO-9
def test_half_verge_eaves_overhang_only_at_exposed_eaves():
    eo, vo = 0.3, 0.15
    m = compute_metrics([bp("main", 0, 0, 10, 8, eo=eo, vo=0.2),
                         bp("garage", 10, 0, 3, 6, storeys=1, pitch=30.0, axis="y", eo=eo, vo=vo)], [], 0.3, 0.2)
    g = roof(m, "garage")
    # front and rear verges: the half towards the main block has no eaves overhang
    assert g.verge_length_m == pytest.approx(2 * 1.5 / C30 + 2 * (1.5 + eo) / C30)
    # ridge over both verge overhangs; eaves on the exposed right side, over its two corners
    assert g.ridge_length_m == pytest.approx(6 + 2 * vo)
    assert g.eaves_length_m == pytest.approx(6 + 2 * vo)
    assert g.abutment_length_m == pytest.approx(6.0)  # eaves side against the wall: horizontal


def test_gable_end_against_taller_wall_abutment_along_rake_and_roof_void():
    eo, vo = 0.3, 0.15
    blocks = [bp("main", 0, 0, 10, 8, eo=eo, vo=0.2),
              bp("garage", 10, 0, 3, 6, storeys=1, pitch=30.0, axis="x", eo=eo, vo=vo)]
    m = compute_metrics(blocks, [], 0.3, 0.2)
    g = roof(m, "garage")
    assert g.abutment_length_m == pytest.approx(2 * 3.0 / C30)  # along both rakes of the gable end
    assert g.verge_length_m == pytest.approx(2 * (3.0 + eo) / C30)  # right gable only, both eaves exposed
    assert g.ridge_length_m == pytest.approx(3.0 + vo)
    assert g.eaves_length_m == pytest.approx(2 * (3.0 + vo))
    # the garage gable triangle against the main wall stays external wall (conservative) ...
    t30 = math.tan(math.radians(30.0))
    void = roof_void_wall_areas(blocks)
    assert void == {"main:right:0": pytest.approx(0.5 * 6.0 * 3.0 * t30)}
    m_y = compute_metrics([blocks[0], bp("garage", 10, 0, 3, 6, storeys=1, pitch=30.0, axis="y")], [], 0.3, 0.2)
    gross = lambda mm: sum(p.external_gross_area_m2 for p in mm.pieces if p.block_id == "main")  # noqa: E731
    assert gross(m) == pytest.approx(gross(m_y))
    # ... and is reported as a separate external-wall measure
    assert "lower_roof_void_area" in MEASURES[ElementType.EXTERNAL_WALL]
    twin = demo_twin(garage_axis="x")
    wall = measures_of(twin, ElementType.EXTERNAL_WALL, "main")
    # demo garage 3.2 x 6.0 m with ridge along x: its 6.0 m gable end (rise 3 tan 30) faces the main block
    assert wall.measures["lower_roof_void_area"].value == pytest.approx(0.5 * 6.0 * 3.0 * t30)
    assert "inside a lower neighbour's roof void" in wall.measures["gross_area"].formula
    assert measures_of(demo_twin(), ElementType.EXTERNAL_WALL, "main").measures["lower_roof_void_area"].value == 0


def test_roof_void_is_capped_at_the_taller_wall_top():
    # taller flat-roofed block (plate 2.85); lower block plate 2.15 with a 45 deg gable end (rise 3 m)
    blocks = [bp("tall", 0, 0, 6, 6, storeys=1, form=RoofForm.FLAT, pitch=0.0),
              bp("low", 6, 0, 4, 6, storeys=1, pitch=45.0, axis="x", ftf=2.0)]
    void = roof_void_wall_areas(blocks)
    h = 2.85 - 2.15  # only the part of the gable below the taller wall top is against that wall
    assert void["tall:right:0"] == pytest.approx(6.0 * (h - h * h / 6.0))


def test_monopitch_ridge_eaves_and_verge_overhang_ends():
    eo, vo, p = 0.3, 0.2, 10.0
    m = compute_metrics([bp("m", 0, 0, 8, 6, storeys=1, form=RoofForm.MONOPITCH, pitch=p, high=Side.FRONT, eo=eo,
                            vo=vo)], [], 0.3, 0.2)
    r = m.roofs[0]
    assert r.ridge_length_m == pytest.approx(8 + 2 * vo)
    assert r.eaves_length_m == pytest.approx(8 + 2 * vo)
    assert r.verge_length_m == pytest.approx(2 * (6 + vo + eo) / math.cos(math.radians(p)))
    assert r.plan_area_m2 == pytest.approx((8 + 2 * vo) * (6 + vo + eo))


def test_lean_to_against_taller_wall():
    eo, vo, p = 0.3, 0.2, 15.0
    blocks = [bp("main", 0, 0, 10, 8),
              bp("lean", 2, 8, 4, 3, storeys=1, form=RoofForm.MONOPITCH, pitch=p, high=Side.FRONT, eo=eo, vo=vo)]
    m = compute_metrics(blocks, [], 0.3, 0.2)
    r = roof(m, "lean")
    assert r.ridge_length_m == pytest.approx(0.0)  # the high edge is an abutment, not an exposed top edge
    assert r.abutment_length_m == pytest.approx(4.0)
    assert r.eaves_length_m == pytest.approx(4 + 2 * vo)
    assert r.verge_length_m == pytest.approx(2 * (3 + eo) / math.cos(math.radians(p)))  # no high overhang
    assert r.plan_area_m2 == pytest.approx(4 * 3 + 2 * vo * 3 + eo * 4 + 2 * vo * eo)
    assert roof_void_wall_areas(blocks) == {"main:rear:1": pytest.approx(4 * 3 * math.tan(math.radians(p)))}


# ==================================================================== GEO-10
@pytest.mark.parametrize("w,d,axis,warned", [(6, 10, "x", True), (6, 10, "y", False), (10, 6, "y", True),
                                             (10, 6, "x", False), (8, 8, "x", False), (8, 8, "y", False)])
def test_hip_ridge_axis_disagreeing_with_longer_side_is_flagged(w, d, axis, warned):
    m = compute_metrics([bp("h", 0, 0, w, d, form=RoofForm.HIP, axis=axis)], [], 0.3, 0.2)
    assert any("hip roof ridge follows the longer side" in x for x in m.warnings) == warned
    assert m.roofs[0].ridge_length_m == pytest.approx(abs(w - d))


# ==================================================================== GEO-11
def test_ground_internal_area_matches_gia_and_strips():
    m = compute_metrics([bp("main", 0, 0, 10, 8), bp("garage", 10, 0, 3, 6, storeys=1)], [], 0.3, 0.2)
    assert ground_internal_area(m, 0.3, 0.1) == pytest.approx(m.storeys[0].gia_m2)
    e, s = 0.45, 0.3
    main = (10 - e) * (8 - 2 * e) - (s * (6 - e) + e * (8 - e - 6))
    garage = (3 - e - s) * (6 - 2 * e)
    assert ground_internal_area(m, e, s) == pytest.approx(main + garage)


def test_oversite_excludes_trench_plan_inside_gia_two_blocks():
    twin = make_twin([blk("main", 0, 0, 10, 8), blk("garage", 10, 0, 3, 6, storeys=1, axis="y", pitch=30.0)])
    t, t_sep = wall_thicknesses(twin, LIB)
    boq = calculate_quantities(twin, LIB)
    W, P = 0.6, 36 + 18 - 2 * 6
    e, s = (t + W) / 2, max(t_sep, W) / 2
    main = (10 - e) * (8 - 2 * e) - (s * (6 - e) + e * (8 - e - 6))
    garage = (3 - e - s) * (6 - 2 * e)
    area = main + garage - W * 0.2 * P
    over = boq.line("1.all.fdn_trench_fill.1")
    assert over.measure_value == pytest.approx(area)
    assert over.installed_qty == pytest.approx(area * 0.25)
    assert "less trench plan inside the GIA" in over.formula
    # disposal inherits the corrected volume
    exc = boq.line("1.all.fdn_trench_fill.0")
    assert boq.line("1.all.fdn_trench_fill.2").installed_qty == pytest.approx(
        (exc.installed_qty + over.installed_qty) * 1.25)
    # the excluded plan is the trench inside the GIA (~0.14 m x external walls, 0.27 m x separating
    # wall, 0.6 m x internal allowance), not the full slab
    assert 0 < boq.geometry.ground_floor_area_m2 - area < W * (P + 6.0)


def test_oversite_unresolved_when_trench_width_unknown():
    lib = LIB.model_copy(deep=True)
    f = lib.foundation("fdn_trench_fill")
    f.trench_width_m = unknown("m")
    boq = calculate_quantities(make_twin([blk("B1", 0, 0, 10, 8)]), lib)
    assert boq.line("1.all.fdn_trench_fill.1").status == QuantityStatus.UNRESOLVED


# ==================================================================== GEO-12
def _sep_plaster(boq, owner):
    a = layer_index("sw_masonry_separating", "plaster_hardwall_undercoat", 0)
    b = layer_index("sw_masonry_separating", "plaster_hardwall_undercoat", 1)
    return (boq.line(f"2.8.{owner}.sw_masonry_separating.{a}").installed_qty,
            boq.line(f"2.8.{owner}.sw_masonry_separating.{b}").installed_qty)


@pytest.mark.parametrize("owner_heated,neighbour_heated", [(False, True), (True, False), (True, True),
                                                           (False, False)])
def test_separating_wall_finishes_only_towards_heated_blocks(owner_heated, neighbour_heated):
    # "garage" < "main": the separating wall is measured on the garage block (side A faces it)
    twin = make_twin([blk("main", 0, 0, 10, 8, heated=neighbour_heated),
                      blk("garage", 10, 0, 3, 6, storeys=1, pitch=30.0, axis="y", heated=owner_heated)])
    boq = calculate_quantities(twin, LIB)
    area = 6 * FTF
    side_a, side_b = _sep_plaster(boq, "garage")
    assert side_a == pytest.approx(area if owner_heated else 0.0)
    assert side_b == pytest.approx(area if neighbour_heated else 0.0)
    # the walls themselves are measured whatever the heating
    leaf = boq.line(f"2.8.garage.sw_masonry_separating.{layer_index('sw_masonry_separating', 'mineral_wool_100_cavity')}")
    assert leaf.installed_qty == pytest.approx(area)
    # decoration counts the same separating faces as the plaster
    deco = boq.line("3.allow.decoration")
    if owner_heated or neighbour_heated:
        assert f"separating faces {side_a + side_b:.2f}" in deco.formula
    else:
        assert "separating faces" not in deco.formula
