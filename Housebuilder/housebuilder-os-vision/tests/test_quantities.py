"""Tests for the assembly library, measures, procurement arithmetic and quantity take-off.

Test twins are built by hand (the twin builder is a separate module).
"""

from __future__ import annotations

import math
import re
import time

import pytest

from housebuilder_vision.core.models import (
    BillOfQuantities,
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
from housebuilder_vision.core.units import convert
from housebuilder_vision.geometry import compute_geometry_metrics
from housebuilder_vision.quantities import (
    ELEMENT_CODES,
    MEASURES,
    SUBSTRUCTURE_LINE_INDEX,
    TakeoffAssumptions,
    apply_construction_assemblies,
    calculate_quantities,
    cost_keys,
    default_library,
    default_selection,
    element_measures,
    procure,
    procurement_schedule,
    validate_library,
    wall_thicknesses,
)

LIB = default_library()
FFL, FTF = 0.15, 2.7
T35 = math.tan(math.radians(35.0))


# ----------------------------------------------------------------- helpers
def tv(v, unit="m", basis=Basis.USER_CONFIRMED):
    return TrackedValue(value=v, unit=unit, basis=basis)


def blk(bid, x0, y0, w, d, storeys=2, form=RoofForm.GABLE, pitch=35.0, axis="x", eo=0.3, vo=0.2, heated=True,
        role=BlockRole.MAIN, width_basis=Basis.USER_CONFIRMED, depth_basis=Basis.USER_CONFIRMED):
    return Block(block_id=bid, role=role, origin_x=tv(x0), origin_y=tv(y0), width=tv(w, basis=width_basis),
                 depth=tv(d, basis=depth_basis), storeys=tv(storeys, "storeys"), floor_to_floor=tv(FTF),
                 ground_floor_level=tv(FFL),
                 roof=RoofSpec(form=form, pitch_deg=tv(pitch, "deg"), ridge_axis=axis, eaves_overhang_m=tv(eo),
                               verge_overhang_m=tv(vo)),
                 heated=heated)


def op(oid, bid, side, kind, storey, off, w, h, sill, **kw):
    return Opening(opening_id=oid, block_id=bid, side=side, kind=kind, storey=storey, offset_m=tv(off),
                   width_m=tv(w), height_m=tv(h), sill_m=tv(sill), **kw)


def make_twin(blocks, openings=(), selection=None, **kw):
    return BuildingTwin(
        twin_id="t_test", blocks=list(blocks), openings=list(openings),
        hidden=HiddenSideAssumptions(rear_glazing_ratio=assumed(0.2, "fraction"),
                                     side_glazing_ratio=assumed(0.04, "fraction")),
        assemblies=selection or default_selection(LIB), **kw)


def box_twin(openings=(), **kw):
    return make_twin([blk("B1", 0, 0, 10, 8)], openings, **kw)


def demo_twin():
    """Main house + lower unheated garage (right) + flat-roofed rear extension (3 blocks)."""
    blocks = [
        blk("main", 0, 0, 9.6, 8.4),
        blk("garage", 9.6, 0, 3.2, 6.0, storeys=1, pitch=30.0, axis="y", heated=False, role=BlockRole.GARAGE),
        blk("ext", 0, 8.4, 4.8, 3.6, storeys=1, form=RoofForm.FLAT, pitch=0.0, eo=0.15, vo=0.15,
            role=BlockRole.EXTENSION),
    ]
    ops = [
        op("W1", "main", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.8, 1.2, 0.9, feature_id="f_w1"),
        op("D1", "main", Side.FRONT, OpeningKind.DOOR, 0, 4.3, 1.0, 2.1, 0.0),
        op("W2", "main", Side.FRONT, OpeningKind.WINDOW, 0, 6.8, 1.8, 1.2, 0.9),
        op("W3", "main", Side.FRONT, OpeningKind.WINDOW, 1, 1.3, 1.2, 1.2, 0.9),
        op("W4", "main", Side.REAR, OpeningKind.WINDOW, 1, 1.0, 1.2, 1.2, 0.9, hidden_side_rule="rear_glazing"),
        op("G1", "garage", Side.FRONT, OpeningKind.GARAGE_DOOR, 0, 0.4, 2.4, 2.13, 0.0),
    ]
    return make_twin(blocks, ops)


def layer_index(assembly_id, material_id, nth=0):
    idx = [i for i, layer in enumerate(LIB.assembly(assembly_id).layers) if layer.material_id == material_id]
    return idx[nth]


def lines_by_prefix(boq, prefix):
    return [ln for ln in boq.lines if ln.line_id.startswith(prefix)]


# ------------------------------------------------------------------ library
def test_library_is_consistent_and_illustrative():
    assert validate_library(LIB) == []
    assert 35 <= len(LIB.materials) <= 60
    for m in LIB.materials:
        assert m.carbon_source == "illustrative placeholder"
        assert "Illustrative" in m.notes
    ids = {a.assembly_id for a in LIB.assemblies}
    for required in ("ew_masonry_cavity", "ew_timber_frame_brick", "ew_timber_frame_clad", "sw_masonry_separating",
                     "ip_timber_stud", "gf_concrete_slab", "if_timber_joist", "pr_tiled_cold", "fr_warm_deck",
                     "win_upvc_dg", "win_alu_tg", "door_composite", "gdoor_steel_sectional"):
        assert required in ids
    assert {f.option_id for f in LIB.foundations} == {"fdn_trench_fill", "fdn_strip", "fdn_deep_trench_fill",
                                                      "fdn_raft", "fdn_piled_allowance"}
    for f in LIB.foundations:
        assert "site investigation" in f.notes and "engineer's design" in f.notes
    steel = next(a for a in LIB.allowances if a.allowance_id == "structural_steel")
    assert "no member sizing" in steel.description and steel.material_id == "steel_beam"
    assert {a.u_value_override for a in LIB.assemblies if a.assembly_id.startswith(("win_", "door", "gdoor"))} == {
        1.4, 1.2, 3.0}
    assert LIB.assembly("win_alu_tg").u_value_override == 1.2
    assert LIB.assembly("gdoor_steel_sectional").u_value_override == 3.0
    # timber stud bridging in the insulation layer; every layer has a trade
    tf = LIB.assembly("ew_timber_frame_brick")
    ins = [layer for layer in tf.layers if layer.bridging is not None]
    assert len(ins) == 1 and ins[0].bridging.fraction == pytest.approx(0.15)
    assert ins[0].bridging.material_id == "timber_stud_140x38"
    assert all(layer.trade for a in LIB.assemblies for layer in a.layers)
    # air cavity: equivalent conductivity 0.05 / 0.18
    assert LIB.material("air_cavity_50").conductivity_w_mk == pytest.approx(0.05 / 0.18)
    # lead times are labelled assumptions
    assert LIB.material("window_upvc_dg").lead_time_weeks.low == 6
    assert LIB.material("window_upvc_dg").lead_time_weeks.high == 10
    assert LIB.material("trussed_rafter").lead_time_weeks.basis == Basis.ASSUMED


def test_default_selection_is_assumed_everywhere():
    sel = default_selection(LIB)
    assert sel.external_wall == "ew_masonry_cavity" and sel.foundation == "fdn_trench_fill"
    assert sel.pitched_roof == "pr_tiled_cold"
    assert set(sel.basis.values()) == {Basis.ASSUMED}
    assert set(sel.basis) == {e.value for e in ElementType} | {"foundation"}


def test_measures_cover_all_elements():
    assert set(MEASURES) == set(ElementType)
    assert set(ELEMENT_CODES) == set(ElementType)


def test_cost_keys_listing():
    keys = cost_keys(LIB)
    assert keys["mat:facing_brick"] == "nr"
    assert keys["mat:pir_100"] == "board"
    assert keys["plant:excavation"] == "m3" and keys["log:spoil_disposal"] == "m3"
    assert keys["lab:bricklaying"] == "hr"
    assert keys["allow:piling"] == "m" and keys["allow:reinforcement"] == "kg"
    assert "mat:air_cavity_50" not in keys  # thermal only, never purchased


# -------------------------------------------------------------- procurement
def test_procure_bricks_packs_of_500():
    p = procure(1000, LIB.material("facing_brick"))
    assert p["cutting_loss_qty"] == pytest.approx(30)
    assert p["waste_qty"] == pytest.approx(50)
    assert p["required"] == pytest.approx(1080)
    assert p["packs"] == 3
    assert p["purchased"] == pytest.approx(1500)
    assert p["surplus"] == pytest.approx(420)
    assert p["installed_unit"] == "nr" and p["purchase_unit"] == "nr"


def test_procure_boards_in_packs():
    pir = LIB.material("pir_100")
    p = procure(30.0, pir)  # 30 m2 x 1.08 = 32.4 m2 -> 11.25 boards -> 2 packs of 6
    assert p["required"] == pytest.approx(32.4)
    assert p["purchase_required"] == pytest.approx(32.4 / 2.88)
    assert p["packs"] == 2
    assert p["purchased"] == pytest.approx(12)
    assert p["surplus"] == pytest.approx(12 - 11.25)
    pb = procure(28.8, LIB.material("plasterboard_12_5"))  # 28.8 x 1.13 / 2.88 = 11.3 sheets -> 12
    assert pb["packs"] == 12 and pb["purchased"] == pytest.approx(12)


def test_procure_concrete_increments_and_exact_multiples():
    c = LIB.material("concrete_c25")
    p = procure(2.0, c)  # 2.1 m3 -> 9 x 0.25
    assert p["packs"] == 9 and p["purchased"] == pytest.approx(2.25) and p["surplus"] == pytest.approx(0.15)
    exact = procure(2.5 / 1.05, c)  # required exactly 2.5 m3 (floating noise must not buy an extra 0.25)
    assert exact["packs"] == 10 and exact["purchased"] == pytest.approx(2.5)
    exact_bricks = procure(1000 / 1.08, LIB.material("facing_brick"))
    assert exact_bricks["packs"] == 2
    hc = procure(1.0, LIB.material("hardcore_type1"))  # 1.05 m3 x 2.1 t/m3 = 2.205 t -> 3 t
    assert hc["purchase_required"] == pytest.approx(2.205) and hc["packs"] == 3 and hc["purchase_unit"] == "tonne"


def test_procure_losses_are_additive_not_compounded():
    m = LIB.material("osb_9").model_copy(update={"cutting_loss_fraction": 0.1, "waste_fraction": 0.1})
    assert procure(100, m)["required"] == pytest.approx(120.0)


def test_procure_zero_and_invalid():
    p = procure(0.0, LIB.material("facing_brick"))
    assert p["packs"] == 0 and p["purchased"] == 0 and p["surplus"] == 0
    with pytest.raises(ValueError):
        procure(-1.0, LIB.material("facing_brick"))
    with pytest.raises(ValueError):
        procure(float("nan"), LIB.material("facing_brick"))


# ------------------------------------------------------------------- units
def test_volume_layers_from_mm_thickness_and_per_area_counts():
    twin = box_twin()
    boq = calculate_quantities(twin, LIB)
    gf_area = boq.geometry.ground_floor_area_m2
    conc = boq.line(f"1.B1.gf_concrete_slab.{layer_index('gf_concrete_slab', 'concrete_c25')}")
    assert conc.unit == "m3"
    assert conc.installed_qty == pytest.approx(gf_area * convert(100, "mm", "m"))
    hard = boq.line(f"1.B1.gf_concrete_slab.{layer_index('gf_concrete_slab', 'hardcore_type1')}")
    assert hard.installed_qty == pytest.approx(gf_area * convert(150, "mm", "m"))
    assert hard.purchase_unit == "tonne"
    assert hard.purchased_qty == pytest.approx(math.ceil(hard.installed_qty * 1.05 * 2.1 - 1e-9))
    bricks = boq.line(f"2.5.B1.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'facing_brick')}")
    assert bricks.unit == "nr" and bricks.installed_qty == pytest.approx(boq.geometry.external_wall_net_m2 * 60)
    tiles = boq.line(f"2.3.B1.pr_tiled_cold.{layer_index('pr_tiled_cold', 'roof_tile_concrete')}")
    assert tiles.installed_qty == pytest.approx(boq.geometry.roofs[0].surface_area_m2 * 9.7)
    assert tiles.purchased_qty % 240 == 0
    assert tiles.formula.startswith("element_area ") and "nr/m2" in tiles.formula


# ------------------------------------------------- walls, openings, finishes
def test_insulation_equals_net_wall_area_and_openings_deducted_once():
    win = op("W1", "B1", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.2, 1.2, 0.9)
    b0 = calculate_quantities(box_twin(), LIB)
    b1 = calculate_quantities(box_twin([win]), LIB)
    ins = f"2.5.B1.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'mineral_wool_100_cavity')}"
    assert b1.line(ins).installed_qty == pytest.approx(b1.geometry.external_wall_net_m2)
    assert b0.line(ins).installed_qty - b1.line(ins).installed_qty == pytest.approx(1.44, abs=1e-9)
    brick = f"2.5.B1.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'facing_brick')}"
    assert b0.line(brick).installed_qty - b1.line(brick).installed_qty == pytest.approx(1.44 * 60)
    assert b1.line("2.6.all.win_upvc_dg.0").installed_qty == pytest.approx(1.44)
    head = b1.line(f"2.5.B1.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'steel_lintel')}")
    assert head.installed_qty == pytest.approx(1.2)
    bearing = b1.line(f"2.5.B1.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'steel_lintel', 1)}")
    assert bearing.installed_qty == pytest.approx(0.30)
    # multi-block: insulation over all blocks equals metrics net area, windows reconcile with deductions
    demo = calculate_quantities(demo_twin(), LIB)
    tot = sum(ln.installed_qty for ln in demo.lines
              if ln.material_id == "mineral_wool_100_cavity" and ln.element_code == "2.5")
    assert tot == pytest.approx(demo.geometry.external_wall_net_m2)
    win_area = sum(ln.installed_qty for ln in lines_by_prefix(demo, "2.6.all.win_"))
    assert win_area == pytest.approx(demo.geometry.window_area_m2)


def test_separating_wall_counted_once():
    twin = make_twin([blk("main", 0, 0, 10, 8), blk("garage", 10, 0, 3, 6, storeys=1, pitch=30.0, axis="y",
                                                     heated=False)])
    boq = calculate_quantities(twin, LIB)
    sep = lines_by_prefix(boq, "2.8.")
    assert sep and all(ln.line_id.startswith("2.8.garage.") for ln in sep)  # owner = smaller id, once
    leaf = boq.line(f"2.8.garage.sw_masonry_separating.{layer_index('sw_masonry_separating', 'mineral_wool_100_cavity')}")
    assert leaf.installed_qty == pytest.approx(boq.geometry.separating_wall_area_m2)
    assert leaf.installed_qty == pytest.approx(6 * FTF)
    # the main block's wall above the garage is external, not separating
    main_ins = boq.line(f"2.5.main.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'mineral_wool_100_cavity')}")
    garage_ins = boq.line(f"2.5.garage.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'mineral_wool_100_cavity')}")
    assert main_ins.installed_qty + garage_ins.installed_qty == pytest.approx(boq.geometry.external_wall_net_m2)


def test_internal_face_area_excludes_gable_infill_and_unheated_blocks():
    win = op("W1", "B1", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.2, 1.2, 0.9)
    boq = calculate_quantities(box_twin([win]), LIB)
    rect = 36 * 2 * FTF
    infill = 2 * 0.5 * 8 * 4 * T35
    plaster = boq.line(f"2.5.B1.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'skim_plaster')}")
    assert plaster.measure_name == "internal_face_area"
    assert plaster.installed_qty == pytest.approx(rect - 1.44)
    block_leaf = boq.line(f"2.5.B1.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'mineral_wool_100_cavity')}")
    assert block_leaf.installed_qty - plaster.installed_qty == pytest.approx(infill)
    # an unheated block (garage) gets no internal wall finish and no ceiling finish
    g = calculate_quantities(make_twin([blk("G", 0, 0, 3, 6, storeys=1, heated=False)]), LIB)
    assert g.line(f"2.5.G.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'skim_plaster')}").installed_qty == 0
    assert g.line(f"2.3.G.pr_tiled_cold.{layer_index('pr_tiled_cold', 'mineral_wool_300_loft')}").installed_qty == 0
    assert not lines_by_prefix(g, "2.7.all.")  # no partitions in unheated volumes


def test_roof_linear_items():
    boq = calculate_quantities(box_twin(), LIB)
    r = boq.geometry.roofs[0]
    ridge = boq.line(f"2.3.B1.pr_tiled_cold.{layer_index('pr_tiled_cold', 'ridge_tile')}")
    assert ridge.installed_qty == pytest.approx(r.ridge_length_m / 0.45)
    trusses = boq.line(f"2.3.B1.pr_tiled_cold.{layer_index('pr_tiled_cold', 'trussed_rafter')}")
    assert trusses.installed_qty == pytest.approx(10.0 / 0.6)  # run along the ridge between gable walls
    fascia = boq.line(f"2.3.B1.pr_tiled_cold.{layer_index('pr_tiled_cold', 'fascia_soffit_timber')}")
    assert fascia.installed_qty == pytest.approx(r.eaves_length_m)
    loft = boq.line(f"2.3.B1.pr_tiled_cold.{layer_index('pr_tiled_cold', 'mineral_wool_300_loft')}")
    assert loft.installed_qty == pytest.approx(boq.geometry.top_ceiling_area_m2)


# -------------------------------------------------------------- partitions
def test_partitions_are_allowance_with_assumption_trace():
    twin = box_twin()
    boq = calculate_quantities(twin, LIB)
    lines = lines_by_prefix(boq, "2.7.all.ip_timber_stud.")
    assert len(lines) == len(LIB.assembly("ip_timber_stud").layers)
    zone = LIB.assembly("if_timber_joist").total_thickness_m
    expected = boq.geometry.heated_gia_m2 * 0.45 * (FTF - zone)
    for ln in lines:
        assert ln.status == QuantityStatus.ALLOWANCE
        assert ln.basis == Basis.ASSUMED
        assert any(t.kind == "assumption" and t.ref == "partition_length_per_m2_gia" for t in ln.trace)
    assert lines[0].installed_qty == pytest.approx(expected)
    more = calculate_quantities(twin, LIB, assumptions=TakeoffAssumptions(
        partition_length_per_m2_gia=assumed(0.6, "m/m2", low=0.4, high=0.8)))
    assert more.line(lines[0].line_id).installed_qty == pytest.approx(expected * 0.6 / 0.45)


# ------------------------------------------------------ traceability & ids
_LINE_ID = re.compile(r"^(\d+(\.\d+)?)\.(all|[A-Za-z0-9_.:\-]+)\.[A-Za-z0-9_.:\-]+\.(\d+)$")
_ALLOW_ID = re.compile(r"^(\d+(\.\d+)?)\.allow\.[A-Za-z0-9_\-]+$")


@pytest.mark.parametrize("foundation", ["fdn_trench_fill", "fdn_strip", "fdn_deep_trench_fill", "fdn_raft",
                                        "fdn_piled_allowance"])
def test_every_line_is_traceable_and_well_formed(foundation):
    twin = apply_construction_assemblies(demo_twin(), {"foundation": foundation}, LIB, actor="scenario:test")
    boq = calculate_quantities(twin, LIB)
    keys = cost_keys(LIB)
    ids = [ln.line_id for ln in boq.lines]
    assert len(ids) == len(set(ids))
    for ln in boq.lines:
        assert ln.trace, ln.line_id
        assert ln.geometry_refs or any(t.kind == "allowance" for t in ln.trace), ln.line_id
        assert _LINE_ID.match(ln.line_id) or _ALLOW_ID.match(ln.line_id), ln.line_id
        assert ln.formula and ln.measure_name
        assert ln.status != QuantityStatus.UNRESOLVED
        if ln.cost_key:
            assert ln.cost_key in keys, ln.cost_key
            assert keys[ln.cost_key] == (ln.purchase_unit or ln.unit), ln.line_id
            assert ln.labour_hours is not None and ln.trade
        if ln.cost_key and ln.cost_key.startswith("mat:"):
            assert ln.cost_key == f"mat:{ln.material_id}"
            mat = LIB.material(ln.material_id)
            assert ln.purchase_unit == mat.purchase_unit and ln.unit == mat.installed_unit
            assert ln.required_qty == pytest.approx(ln.installed_qty + ln.cutting_loss_qty + ln.waste_qty)
            assert ln.purchased_qty == pytest.approx(ln.packs * ln.pack_size)
            assert ln.purchased_qty + 1e-9 >= ln.required_qty * ln.purchase_per_installed
        if ln.status == QuantityStatus.ALLOWANCE and ln.allowance_id:
            assert ln.cost_key.startswith("allow:")
        if ln.element_code != "1" and ln.layer_index is not None:
            assert any(t.kind == "assembly_rule" for t in ln.trace)
    assert any(ln.line_id.startswith(f"1.all.{foundation}.") for ln in boq.lines)
    BillOfQuantities.model_validate_json(boq.model_dump_json())  # output is schema-valid


def test_line_ids_stable_across_recalculation():
    twin = demo_twin()
    a = calculate_quantities(twin, LIB)
    b = calculate_quantities(twin, LIB)
    assert [ln.line_id for ln in a.lines] == [ln.line_id for ln in b.lines]
    wider = twin.model_copy(update={"blocks": [twin.blocks[0].model_copy(update={"depth": tv(9.0)}),
                                               *twin.blocks[1:]]})
    wider = wider.model_copy(update={"blocks": [wider.blocks[0], wider.blocks[1],
                                                wider.blocks[2].model_copy(update={"origin_y": tv(9.0)})]})
    c = calculate_quantities(wider, LIB)
    assert [ln.line_id for ln in a.lines] == [ln.line_id for ln in c.lines]
    brick = f"2.5.main.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'facing_brick')}"
    assert c.line(brick).installed_qty > a.line(brick).installed_qty


def test_opening_traces_assembly_overrides_and_hidden_rules():
    twin = demo_twin()
    ops = [o.model_copy(update={"assembly_id": "win_alu_tg"}) if o.opening_id == "W3" else o for o in twin.openings]
    boq = calculate_quantities(twin.model_copy(update={"openings": ops}), LIB)
    upvc, alu = boq.line("2.6.all.win_upvc_dg.0"), boq.line("2.6.all.win_alu_tg.0")
    assert alu.installed_qty == pytest.approx(1.44) and alu.geometry_refs == ["W3"]
    assert upvc.installed_qty + alu.installed_qty == pytest.approx(boq.geometry.window_area_m2)
    assert any(t.kind == "evidence" and t.ref == "f_w1" for t in upvc.trace)
    assert any(t.kind == "assumption" and t.ref.startswith("hidden_side_rule:") for t in upvc.trace)
    assert boq.line("2.6.all.door_composite.0").installed_qty == 1
    assert boq.line("2.6.all.gdoor_steel_sectional.0").installed_qty == 1


# ------------------------------------------------- timber frame vs masonry
def test_timber_frame_vs_masonry_same_bricks_different_structure():
    masonry = demo_twin()
    tf = apply_construction_assemblies(masonry, {"external_wall": "ew_timber_frame_brick"}, LIB)
    bm, bt = calculate_quantities(masonry, LIB), calculate_quantities(tf, LIB)
    bricks_m = sum(ln.installed_qty for ln in bm.lines if ln.material_id == "facing_brick")
    bricks_t = sum(ln.installed_qty for ln in bt.lines if ln.material_id == "facing_brick")
    assert bricks_m == pytest.approx(bricks_t)
    struct_m = {ln.material_id for ln in bm.lines if ln.element_code == "2.5" and "Aircrete" in ln.description}
    assert struct_m == {"aerated_concrete_block_100"}
    mats_m = {ln.material_id for ln in bm.lines if ln.element_code == "2.5"}
    mats_t = {ln.material_id for ln in bt.lines if ln.element_code == "2.5"}
    assert "timber_stud_140x38" in mats_t and "timber_stud_140x38" not in mats_m
    assert "aerated_concrete_block_100" in mats_m and "aerated_concrete_block_100" not in mats_t
    t_m, _ = wall_thicknesses(masonry, LIB)
    t_t, _ = wall_thicknesses(tf, LIB)
    assert t_m == pytest.approx(0.3155) and t_t == pytest.approx(0.314)
    assert bt.geometry.gia_m2 > bm.geometry.gia_m2 + 0.01
    assert bt.geometry.external_wall_thickness_m == pytest.approx(t_t)
    cavity = next(ln for ln in bt.lines if ln.material_id == "air_cavity_50")
    assert cavity.cost_key is None and cavity.purchased_qty == 0 and "Thermal-only" in cavity.notes
    clad = calculate_quantities(apply_construction_assemblies(masonry, {"external_wall": "ew_timber_frame_clad"},
                                                              LIB), LIB)
    assert not any(ln.material_id == "facing_brick" for ln in clad.lines if ln.element_code == "2.5")


# ----------------------------------------------- apply_construction_assemblies
def test_apply_construction_assemblies_validation():
    twin = box_twin()
    with pytest.raises(ValueError):
        apply_construction_assemblies(twin, {"chimney": "ew_masonry_cavity"}, LIB)
    with pytest.raises(ValueError):
        apply_construction_assemblies(twin, {"external_wall": "ew_does_not_exist"}, LIB)
    with pytest.raises(ValueError):
        apply_construction_assemblies(twin, {"external_wall": "win_upvc_dg"}, LIB)  # wrong element type
    with pytest.raises(ValueError):
        apply_construction_assemblies(twin, {"foundation": "ew_masonry_cavity"}, LIB)
    with pytest.raises(ValueError):
        apply_construction_assemblies(twin, {"foundation": "fdn_strip"}, LIB, block_id="B1")
    with pytest.raises(ValueError):
        apply_construction_assemblies(twin, {"external_wall": "ew_timber_frame_brick"}, LIB, block_id="nope")
    with pytest.raises(ValueError):
        apply_construction_assemblies(twin, {"external_wall": ""}, LIB)


def test_apply_construction_assemblies_is_immutable_logged_and_sets_basis():
    twin = box_twin()
    before = twin.model_dump()
    new = apply_construction_assemblies(twin, {"external_wall": "ew_timber_frame_brick", "foundation": "fdn_strip"},
                                        LIB, reason="client confirmed")
    assert twin.model_dump() == before  # input untouched
    assert new is not twin and new.version == twin.version + 1
    assert new.assemblies.external_wall == "ew_timber_frame_brick" and new.assemblies.foundation == "fdn_strip"
    assert new.assemblies.basis["external_wall"] == Basis.USER_CONFIRMED
    assert new.assemblies.basis["foundation"] == Basis.USER_CONFIRMED
    recs = new.edit_log[-2:]
    assert {r.field for r in recs} == {"external_wall", "foundation"}
    r = next(r for r in recs if r.field == "external_wall")
    assert r.old_value == "ew_masonry_cavity" and r.new_value == "ew_timber_frame_brick"
    assert r.old_basis == Basis.ASSUMED and r.new_basis == Basis.USER_CONFIRMED and r.reason == "client confirmed"
    scen = apply_construction_assemblies(twin, {"external_wall": "ew_timber_frame_clad"}, LIB, actor="scenario:tf")
    assert scen.assemblies.basis["external_wall"] == Basis.ASSUMED
    assert apply_construction_assemblies(twin, {"window": "win_alu_tg"}, LIB,
                                         actor="system").assemblies.basis["window"] == Basis.ASSUMED
    # per-block override
    two = make_twin([blk("main", 0, 0, 10, 8), blk("garage", 10, 0, 3, 6, storeys=1, axis="y", pitch=30.0)])
    ov = apply_construction_assemblies(two, {"pitched_roof": "pr_tiled_cold", "ground_floor": "gf_concrete_slab"},
                                       LIB, block_id="garage")
    assert ov.assemblies.block_overrides["garage"]["pitched_roof"] == "pr_tiled_cold"
    assert ov.assemblies.basis["garage/pitched_roof"] == Basis.USER_CONFIRMED
    assert two.assemblies.block_overrides == {}
    boq = calculate_quantities(ov, LIB)
    assert boq.line("2.3.garage.pr_tiled_cold.0").trace[0].kind == "user_input"
    assert boq.line("2.3.main.pr_tiled_cold.0").trace[0].kind == "assumption"


def test_line_basis_is_weakest_of_measure_and_selection():
    twin = box_twin()
    brick = f"2.5.B1.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'facing_brick')}"
    assert calculate_quantities(twin, LIB).line(brick).basis == Basis.ASSUMED  # selection assumed
    conf = apply_construction_assemblies(twin, {"external_wall": "ew_masonry_cavity"}, LIB)
    assert calculate_quantities(conf, LIB).line(brick).basis == Basis.USER_CONFIRMED
    observed = conf.model_copy(update={"blocks": [blk("B1", 0, 0, 10, 8, width_basis=Basis.OBSERVED)]})
    assert calculate_quantities(observed, LIB).line(brick).basis == Basis.OBSERVED
    hidden_depth = conf.model_copy(update={"blocks": [blk("B1", 0, 0, 10, 8, depth_basis=Basis.ASSUMED)]})
    b = calculate_quantities(hidden_depth, LIB)
    assert b.line(brick).basis == Basis.ASSUMED
    # internal areas depend on the (assumed) wall thickness choice
    t_ext, t_sep = wall_thicknesses(twin, LIB)
    m = compute_geometry_metrics(twin, t_ext, t_sep)
    gf = next(i for i in element_measures(twin, m, LIB) if i.element == ElementType.GROUND_FLOOR)
    assert gf.measures["element_area"].basis == Basis.ASSUMED
    gf_c = next(i for i in element_measures(conf, m, LIB) if i.element == ElementType.GROUND_FLOOR)
    assert gf_c.measures["element_area"].basis == Basis.USER_CONFIRMED
    assert gf_c.measures["perimeter"].basis == Basis.USER_CONFIRMED


# ------------------------------------------------------------- substructure
def test_trench_length_and_foundation_quantities():
    twin = box_twin()
    t = wall_thicknesses(twin, LIB)[0]
    P = 36.0
    L = (P - 4 * t) + 0.2 * P
    boq = calculate_quantities(twin, LIB)
    exc = boq.line("1.all.fdn_trench_fill.0")
    assert exc.measure_value == pytest.approx(L) and exc.installed_qty == pytest.approx(L * 0.6 * 1.0)
    assert exc.cost_key == "plant:excavation" and exc.material_id is None and exc.trade == "groundworks"
    conc = boq.line(f"1.all.fdn_trench_fill.{SUBSTRUCTURE_LINE_INDEX['concrete']}")
    assert conc.installed_qty == pytest.approx(L * 0.6 * 0.85) and conc.cost_key == "mat:concrete_c25"
    assert conc.purchased_qty == pytest.approx(math.ceil(conc.installed_qty * 1.05 / 0.25 - 1e-9) * 0.25)
    over = boq.line("1.all.fdn_trench_fill.1")
    assert over.installed_qty == pytest.approx(boq.geometry.ground_floor_area_m2 * 0.25)
    disp = boq.line("1.all.fdn_trench_fill.2")
    assert disp.installed_qty == pytest.approx((exc.installed_qty + over.installed_qty) * 1.25)
    assert disp.cost_key == "log:spoil_disposal"
    blocks_tf = boq.line(f"1.all.fdn_trench_fill.{SUBSTRUCTURE_LINE_INDEX['below_ground_blockwork']}")
    leaf = 2 * (P - 4 * t) + 1 * 0.2 * P
    assert blocks_tf.measure_value == pytest.approx(leaf * (1.0 - 0.85 + FFL))
    assert blocks_tf.installed_qty == pytest.approx(leaf * 0.30 * 9.88)
    strip = calculate_quantities(apply_construction_assemblies(twin, {"foundation": "fdn_strip"}, LIB), LIB)
    blocks_strip = strip.line(f"1.all.fdn_strip.{SUBSTRUCTURE_LINE_INDEX['below_ground_blockwork']}")
    assert blocks_strip.measure_value == pytest.approx(leaf * (1.0 - 0.25 + FFL))
    assert strip.line("1.all.fdn_strip.3").installed_qty == pytest.approx(L * 0.6 * 0.25)
    for ln in lines_by_prefix(boq, "1.all."):
        assert any(t.kind == "assumption" and "internal_loadbearing_fraction" in t.ref for t in ln.trace)
        assert ln.basis == Basis.ASSUMED
    # separating walls between blocks get a foundation once
    two = make_twin([blk("main", 0, 0, 10, 8), blk("garage", 10, 0, 3, 6, storeys=1, axis="y", pitch=30.0)])
    b2 = calculate_quantities(two, LIB)
    P2 = 36 + 18 - 2 * 6
    L2 = (P2 - 4 * t) + 6.0 + 0.2 * P2
    assert b2.line("1.all.fdn_trench_fill.0").measure_value == pytest.approx(L2)


def test_piled_and_raft_options_are_allowances_without_schedules():
    twin = box_twin()
    piled = calculate_quantities(apply_construction_assemblies(twin, {"foundation": "fdn_piled_allowance"}, LIB), LIB)
    piles = piled.line(f"1.all.fdn_piled_allowance.{SUBSTRUCTURE_LINE_INDEX['piles']}")
    L = piled.line("1.all.fdn_piled_allowance.0").measure_value
    n = math.ceil(L * 0.4 - 1e-9)
    assert piles.status == QuantityStatus.ALLOWANCE and piles.cost_key == "allow:piling"
    assert piles.installed_qty == pytest.approx(n * 12.0) and piles.unit == "m"
    beams = piled.line(f"1.all.fdn_piled_allowance.{SUBSTRUCTURE_LINE_INDEX['concrete']}")
    assert beams.status == QuantityStatus.ALLOWANCE
    reinf = piled.line(f"1.all.fdn_piled_allowance.{SUBSTRUCTURE_LINE_INDEX['reinforcement_allowance']}")
    assert reinf.status == QuantityStatus.ALLOWANCE and "no reinforcement schedule" in reinf.description
    assert reinf.installed_qty == pytest.approx(beams.installed_qty * 60)
    raft = calculate_quantities(apply_construction_assemblies(twin, {"foundation": "fdn_raft"}, LIB), LIB)
    ids = {ln.line_id for ln in lines_by_prefix(raft, "1.all.fdn_raft.")}
    assert f"1.all.fdn_raft.{SUBSTRUCTURE_LINE_INDEX['below_ground_blockwork']}" not in ids
    extra = raft.line(f"1.all.fdn_raft.{SUBSTRUCTURE_LINE_INDEX['raft_extra_thickness']}")
    assert extra.installed_qty == pytest.approx(raft.geometry.ground_floor_area_m2 * (0.25 - 0.10))
    assert raft.line(f"1.all.fdn_raft.{SUBSTRUCTURE_LINE_INDEX['reinforcement_allowance']}").status == \
        QuantityStatus.ALLOWANCE


# ---------------------------------------------------------------- allowances
def test_allowances():
    two = calculate_quantities(box_twin(), LIB)
    one = calculate_quantities(make_twin([blk("B1", 0, 0, 10, 8, storeys=1)]), LIB)
    assert two.line("2.4.allow.staircase").installed_qty == 1
    assert "2.4.allow.staircase" not in {ln.line_id for ln in one.lines}  # only if > 1 storey
    assert two.line("5.allow.sanitaryware").installed_qty == 2  # twin default bathrooms (assumed)
    assert two.line("5.allow.sanitaryware").basis == Basis.ASSUMED
    assert two.line("5.allow.electrical_installation").installed_qty == pytest.approx(two.geometry.heated_gia_m2)
    steel = two.line("2.1.allow.structural_steel")
    assert steel.installed_qty == pytest.approx(3.0 * two.geometry.heated_gia_m2) and steel.material_id == "steel_beam"
    for ln in two.lines:
        if ln.allowance_id:
            assert ln.status == QuantityStatus.ALLOWANCE
            assert ln.cost_key == f"allow:{ln.allowance_id}"
            assert any(t.kind == "allowance" and t.ref == ln.allowance_id for t in ln.trace)
            assert ln.labour_hours == pytest.approx(
                ln.installed_qty * next(a for a in LIB.allowances
                                        if a.allowance_id == ln.allowance_id).labour_hours_per_unit)
    # decoration = finished wall faces + partitions both sides + ceilings of heated storeys
    deco = two.line("3.allow.decoration")
    walls = two.line(f"2.5.B1.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'skim_plaster')}").installed_qty
    parts = two.line("2.7.all.ip_timber_stud.0").installed_qty
    assert deco.installed_qty == pytest.approx(walls + 2 * parts + two.geometry.heated_gia_m2)
    garage_twin = make_twin([blk("G", 0, 0, 3, 6, storeys=1, heated=False)])
    g = calculate_quantities(garage_twin, LIB)
    assert g.line("5.allow.electrical_installation").installed_qty == 0  # heated GIA only


# ------------------------------------------------------------- unresolved
def test_unresolved_when_geometry_invalid():
    overlap = make_twin([blk("A", 0, 0, 5, 5), blk("B", 4, 4, 5, 5)])
    boq = calculate_quantities(overlap, LIB)  # must not raise
    assert boq.unresolved
    geom_lines = [ln for ln in boq.lines if not ln.allowance_id]
    assert geom_lines and all(ln.status == QuantityStatus.UNRESOLVED for ln in geom_lines)
    for ln in geom_lines:
        assert ln.installed_qty is None and ln.purchased_qty is None and ln.labour_hours is None
        assert ln.formula.startswith("UNRESOLVED:") and "overlap" in ln.formula
        assert ln.basis == Basis.UNKNOWN and ln.cost_key is None
        assert ln.trace and ln.geometry_refs
    assert boq.line("4.allow.kitchen").status == QuantityStatus.ALLOWANCE  # per dwelling, still known
    assert boq.line("5.allow.electrical_installation").status == QuantityStatus.UNRESOLVED
    assert any("overlap" in w for w in boq.warnings)
    assert boq.geometry.gia_m2 == 0
    BillOfQuantities.model_validate_json(boq.model_dump_json())


def test_unresolved_for_unknown_dimensions():
    twin = box_twin()
    no_width = twin.model_copy(update={"blocks": [twin.blocks[0].model_copy(update={"width": unknown("m")})]})
    b = calculate_quantities(no_width, LIB)
    assert all(ln.status == QuantityStatus.UNRESOLVED for ln in b.lines if not ln.allowance_id)
    assert any("width" in ln.notes for ln in b.unresolved)
    # an opening of unknown width: only the dependent quantities are unresolved
    good = op("W1", "B1", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.2, 1.2, 0.9)
    bad = op("W2", "B1", Side.REAR, OpeningKind.WINDOW, 0, 1.0, 1.2, 1.2, 0.9).model_copy(
        update={"width_m": unknown("m")})
    b2 = calculate_quantities(box_twin([good, bad]), LIB)
    unresolved = {ln.line_id for ln in b2.unresolved}
    assert f"2.5.B1.ew_masonry_cavity.{layer_index('ew_masonry_cavity', 'facing_brick')}" in unresolved
    assert "2.6.all.win_upvc_dg.0" in unresolved
    assert "W2" in b2.line("2.6.all.win_upvc_dg.0").formula
    assert b2.line(f"1.B1.gf_concrete_slab.{layer_index('gf_concrete_slab', 'concrete_c25')}").status == \
        QuantityStatus.DERIVED
    assert b2.line("2.3.B1.pr_tiled_cold.0").status == QuantityStatus.DERIVED
    assert any("W2" in w for w in b2.warnings)


def test_missing_assembly_is_unresolved_not_crash():
    twin = box_twin()
    sel = twin.assemblies.model_copy(update={"intermediate_floor": "if_missing"})
    boq = calculate_quantities(twin.model_copy(update={"assemblies": sel}), LIB)
    ln = boq.line("2.2.B1.if_missing.0")
    assert ln.status == QuantityStatus.UNRESOLVED and "not in library" in ln.formula
    part = lines_by_prefix(boq, "2.7.all.")  # clear height unknown
    assert part and all(x.status == QuantityStatus.UNRESOLVED for x in part)


# --------------------------------------------------- metrics fast path & perf
def test_precomputed_metrics_fast_path_matches_and_is_fast():
    twin = demo_twin()
    t_ext, t_sep = wall_thicknesses(twin, LIB)
    m = compute_geometry_metrics(twin, t_ext, t_sep)
    full = calculate_quantities(twin, LIB)
    fast = calculate_quantities(twin, LIB, metrics=m)
    assert [(ln.line_id, ln.installed_qty) for ln in full.lines] == [(ln.line_id, ln.installed_qty) for ln in fast.lines]
    assert fast.geometry is m  # no copy
    n = 20
    t0 = time.perf_counter()
    for _ in range(n):
        calculate_quantities(twin, LIB, metrics=m)
    per_call_ms = (time.perf_counter() - t0) / n * 1000
    assert per_call_ms < 50, f"calculate_quantities took {per_call_ms:.1f} ms"


def test_metrics_thickness_mismatch_is_flagged():
    twin = box_twin()
    m = compute_geometry_metrics(twin, 0.25, 0.2)
    boq = calculate_quantities(twin, LIB, metrics=m)
    assert any("wall thicknesses" in w for w in boq.warnings)


def test_procurement_schedule_aggregates_pack_rounding():
    boq = calculate_quantities(demo_twin(), LIB)
    sched = {row["material_id"]: row for row in procurement_schedule(boq, LIB)}
    ties = sched["wall_ties"]
    assert ties["purchased"] % 250 == 0 and ties["purchased"] + 1e-9 >= ties["purchase_required"]
    assert ties["line_level_purchased"] >= ties["purchased"]
    assert ties["rounding_saving"] == pytest.approx(ties["line_level_purchased"] - ties["purchased"])
    bricks = sched["facing_brick"]
    assert bricks["installed"] == pytest.approx(sum(ln.installed_qty for ln in boq.lines
                                                    if ln.material_id == "facing_brick"))
    assert "air_cavity_50" not in sched and "steel_beam" not in sched  # thermal-only / allowance excluded
