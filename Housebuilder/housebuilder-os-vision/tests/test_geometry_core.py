"""Analytic verification of the exact geometry core."""

import math

import pytest

from housebuilder_vision.core.models import OpeningKind, RoofForm, Side
from housebuilder_vision.geometry import BlockParams, GeometryError, OpeningParams, compute_metrics, union_area

FFL, FTF = 0.15, 2.7


def blk(bid, x0, y0, w, d, storeys=2, form=RoofForm.GABLE, pitch=35.0, axis="x", eo=0.0, vo=0.0,
        high=None, parapet=0.0, heated=True):
    return BlockParams(bid, x0, y0, w, d, storeys, FTF, FFL, form, pitch, axis, eo, vo, high, parapet, heated)


def test_union_area_overlapping():
    assert union_area([(0, 0, 2, 2), (1, 1, 3, 3)]) == pytest.approx(7.0)
    assert union_area([(0, 0, 1, 1), (0, 0, 1, 1)]) == pytest.approx(1.0)


def test_rectangular_gable_box():
    m = compute_metrics([blk("B1", 0, 0, 10, 8)], [], 0.3, 0.2)
    t35 = math.tan(math.radians(35))
    rise = 4 * t35
    assert m.gea_m2 == pytest.approx(160.0)
    assert m.gia_m2 == pytest.approx(2 * 9.4 * 7.4)
    assert m.ground_perimeter_m == pytest.approx(36.0)
    # rectangular wall zone + two gable triangles
    assert m.external_wall_gross_m2 == pytest.approx(36 * 5.4 + 2 * 0.5 * 8 * rise)
    assert m.external_wall_net_m2 == pytest.approx(m.external_wall_gross_m2)
    r = m.roofs[0]
    assert r.rise_m == pytest.approx(rise)
    assert r.surface_area_m2 == pytest.approx(80 / math.cos(math.radians(35)))
    assert r.ridge_length_m == pytest.approx(10.0)
    assert r.roof_void_volume_m3 == pytest.approx(0.5 * 8 * rise * 10)
    assert r.ridge_height_m == pytest.approx(FFL + 5.4 + rise)
    assert m.ground_floor_area_m2 == pytest.approx(9.4 * 7.4)
    assert m.intermediate_floor_area_m2 == pytest.approx(9.4 * 7.4)
    assert m.top_ceiling_area_m2 == pytest.approx(9.4 * 7.4)
    assert m.heated_volume_m3 == pytest.approx(2 * 9.4 * 7.4 * FTF)


def test_gable_overhangs():
    m = compute_metrics([blk("B1", 0, 0, 10, 8, eo=0.3, vo=0.2)], [], 0.3, 0.2)
    r = m.roofs[0]
    c = math.cos(math.radians(35))
    assert r.plan_area_m2 == pytest.approx(10.4 * 8.6)
    assert r.surface_area_m2 == pytest.approx(10.4 * 8.6 / c)
    assert r.ridge_length_m == pytest.approx(10.4)
    assert r.eaves_length_m == pytest.approx(2 * 10.4)
    assert r.verge_length_m == pytest.approx(4 * (4 + 0.3) / c)


def test_hip_roof():
    m = compute_metrics([blk("B1", 0, 0, 10, 8, form=RoofForm.HIP, pitch=30.0)], [], 0.3, 0.2)
    r = m.roofs[0]
    rise = 4 * math.tan(math.radians(30))
    assert r.ridge_length_m == pytest.approx(2.0)
    assert r.surface_area_m2 == pytest.approx(80 / math.cos(math.radians(30)))
    assert r.hip_length_m == pytest.approx(4 * math.sqrt(2 * 16 + rise ** 2))
    assert r.roof_void_volume_m3 == pytest.approx(8 * rise * (30 - 8) / 6)
    # no gable infill on hip roofs
    assert m.external_wall_gross_m2 == pytest.approx(36 * 5.4)


def test_monopitch_infill():
    m = compute_metrics([blk("B1", 0, 0, 3, 4, storeys=1, form=RoofForm.MONOPITCH, pitch=10.0, high=Side.FRONT)],
                        [], 0.3, 0.2)
    rise = 4 * math.tan(math.radians(10))
    assert m.roofs[0].rise_m == pytest.approx(rise)
    assert m.external_wall_gross_m2 == pytest.approx(14 * 2.7 + 3 * rise + 2 * 0.5 * 4 * rise)


def test_l_shape_shared_wall_counted_once():
    blocks = [blk("B1", 0, 0, 10, 8), blk("B2", 0, 8, 4, 4)]
    m = compute_metrics(blocks, [], 0.3, 0.2)
    assert m.ground_perimeter_m == pytest.approx(44.0)
    assert m.footprint_area_m2 == pytest.approx(96.0)
    assert m.separating_wall_area_m2 == pytest.approx(4 * 5.4)
    gia_storey = 9.4 * 7.4 + 3.7 * 0.2 + 3.4 * 3.6
    assert m.storeys[0].gia_m2 == pytest.approx(gia_storey)
    assert m.gia_m2 == pytest.approx(2 * gia_storey)
    shared = [p for p in m.pieces if p.exposure == "shared"]
    assert len(shared) == 2  # one per side of the shared wall
    assert sum(p.shared_area_m2 for p in shared) == pytest.approx(4 * 5.4)


def test_lower_garage_composite_and_openings():
    main = blk("main", 0, 0, 10, 8)
    garage = blk("garage", 10, 0, 3, 6, storeys=1, form=RoofForm.GABLE, pitch=30.0, axis="y")
    ops = [
        OpeningParams("W1", "main", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.2, 1.2, 0.9),
        OpeningParams("W2", "main", Side.RIGHT, OpeningKind.WINDOW, 1, 2.0, 1.0, 1.0, 0.9),  # above garage roof
        OpeningParams("W3", "main", Side.RIGHT, OpeningKind.WINDOW, 0, 2.0, 1.0, 1.0, 0.9),  # on separating wall
        OpeningParams("D1", "garage", Side.FRONT, OpeningKind.GARAGE_DOOR, 0, 0.3, 2.4, 2.1, 0.0),
    ]
    m = compute_metrics([main, garage], ops, 0.3, 0.2)
    pieces = {p.piece_id: p for p in m.pieces}
    shared_main = [p for p in m.pieces if p.block_id == "main" and p.exposure == "shared"][0]
    shared_gar = [p for p in m.pieces if p.block_id == "garage" and p.exposure == "shared"][0]
    plate_main, plate_gar = FFL + 5.4, FFL + 2.7
    assert shared_main.external_rect_area_m2 == pytest.approx(6 * (plate_main - plate_gar))
    assert shared_gar.external_rect_area_m2 == pytest.approx(0.0)
    # separating wall counted once (on 'garage' piece, lexicographically smaller id)
    assert shared_gar.shared_area_m2 == pytest.approx(6 * 2.7)
    assert shared_main.shared_area_m2 == pytest.approx(0.0)
    assert m.separating_wall_area_m2 == pytest.approx(6 * 2.7)
    # main gable over the garage is external because the garage is lower
    assert shared_main.external_infill_area_m2 > 0
    # deductions: W1 + W2 (above garage) + garage door; W3 not deducted
    assert m.window_area_m2 == pytest.approx(1.44 + 1.0)
    assert m.garage_door_area_m2 == pytest.approx(2.4 * 2.1)
    assert any("W3" in w for w in m.warnings)
    assert m.external_wall_net_m2 == pytest.approx(m.external_wall_gross_m2 - (1.44 + 1.0 + 5.04))
    assert "W2" in shared_main.opening_ids
    # storey 1 has only the main block; its right side is fully external there
    assert m.storeys[1].block_ids == ["main"]
    assert m.storeys[1].external_perimeter_m == pytest.approx(36.0)
    assert len(pieces) == len(m.pieces)


def test_opening_deducted_exactly_once():
    ops = [OpeningParams("W1", "B1", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.2, 1.2, 0.9)]
    m0 = compute_metrics([blk("B1", 0, 0, 10, 8)], [], 0.3, 0.2)
    m1 = compute_metrics([blk("B1", 0, 0, 10, 8)], ops, 0.3, 0.2)
    assert m1.external_wall_gross_m2 == pytest.approx(m0.external_wall_gross_m2)
    assert m0.external_wall_net_m2 - m1.external_wall_net_m2 == pytest.approx(1.44)
    front = [p for p in m1.pieces if p.side == Side.FRONT][0]
    assert front.opening_head_length_m == pytest.approx(1.2)
    assert front.opening_reveal_length_m == pytest.approx(2.4)
    assert front.opening_sill_length_m == pytest.approx(1.2)


def test_overlap_rejected():
    with pytest.raises(GeometryError):
        compute_metrics([blk("A", 0, 0, 5, 5), blk("B", 4, 4, 5, 5)], [], 0.3, 0.2)


def test_l_shape_roof_overhang_not_double_counted():
    eo = 0.3
    blocks = [blk("B1", 0, 0, 10, 8, eo=eo, vo=eo), blk("B2", 0, 8, 4, 4, axis="y", eo=eo, vo=eo)]
    m = compute_metrics(blocks, [], 0.3, 0.2)
    # union of the footprint grown by 0.3 everywhere on external edges:
    expected = union_area([(-eo, -eo, 10 + eo, 8 + eo), (-eo, 8, 4 + eo, 12 + eo)])
    assert m.roof_plan_area_m2 == pytest.approx(expected)


def test_taller_block_keeps_verge_and_overhang_above_lower_neighbour():
    """The main gable above a lower garage keeps its verge, ridge extension and overhang."""
    eo, vo = 0.3, 0.2
    alone = compute_metrics([blk("main", 0, 0, 10, 8, eo=eo, vo=vo)], [], 0.3, 0.2)
    garage = blk("garage", 10, 0, 3, 6, storeys=1, pitch=30.0, axis="y", eo=eo, vo=vo)
    both = compute_metrics([blk("main", 0, 0, 10, 8, eo=eo, vo=vo), garage], [], 0.3, 0.2)
    ra = alone.roofs[0]
    rm = [r for r in both.roofs if r.block_id == "main"][0]
    rg = [r for r in both.roofs if r.block_id == "garage"][0]
    assert rm.verge_length_m == pytest.approx(ra.verge_length_m)
    assert rm.ridge_length_m == pytest.approx(ra.ridge_length_m)
    assert rm.eaves_length_m == pytest.approx(ra.eaves_length_m)
    assert rm.plan_area_m2 == pytest.approx(ra.plan_area_m2)  # verge strip over the garage still counts
    # the garage roof abuts the taller wall: no overhang into the main block, abutment recorded
    assert rg.abutment_length_m == pytest.approx(6.0)
    # ridge along y: eaves on the exposed right side only, verges front and rear
    assert rg.plan_area_m2 == pytest.approx((3 + eo) * (6 + 2 * vo))
