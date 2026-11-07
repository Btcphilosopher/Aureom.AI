"""Tests for twin.calibration / hypotheses / builder / mesh.

Fixtures are built by hand (no dependency on the vision implementation) and
reproduce the fictional demo house of ARCHITECTURE section 4 at 92 px/m,
ground line y = 900 px, main facade left edge x = 160 px.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from housebuilder_vision.core.models import (
    AnalysisResult,
    AssemblySelection,
    Block,
    BlockRole,
    BuildingTwin,
    DetectedFeature,
    FacadeObservation,
    FeatureType,
    HiddenSideAssumptions,
    ImageAnalysis,
    ImageAsset,
    ImageKind,
    MultiViewResult,
    ObservedFinish,
    ObservedOpening,
    PerspectiveEstimate,
    ReferenceMeasurement,
    RoofForm,
    RoofSpec,
    Side,
    TwinEdit,
    ViewDirection,
)
from housebuilder_vision.core.provenance import Basis, Distribution, TrackedValue, assumed, inferred, observed
from housebuilder_vision.geometry import compute_geometry_metrics
from housebuilder_vision.geometry.footprint import Rect, side_pieces
from housebuilder_vision.twin import (
    apply_twin_edit,
    build_mesh,
    build_parametric_twin,
    calibrate_scale,
    generate_geometry_hypotheses,
    piece_outline_polylines,
    regenerate_hidden_openings,
    scene_for_gltf,
    scene_to_plotly_meshes,
    twin_hash,
    visual_finishes_from_analysis,
)
from housebuilder_vision.twin.mesh import DEFAULT_WALL_HEX

PPM, GY, LX = 92.0, 900.0, 160.0
IMG, IMG_L, IMG_P = "img_front0000000001", "img_left00000000002", "img_plan00000000003"
FFL, FTF, PLATE = 0.15, 2.70, 5.55
MAIN_W, MAIN_D, PITCH = 9.60, 8.40, 35.0
RISE = 0.5 * MAIN_D * math.tan(math.radians(PITCH))
GAR_W, GAR_PITCH = 3.20, 30.0
GAR_RISE = 0.5 * GAR_W * math.tan(math.radians(GAR_PITCH))
GAR_LX = LX + MAIN_W * PPM + 0.3  # 0.3 px detection gap -> snapped
GROUP = f"scale:{IMG}"


# =============================================================================
# Fixtures
# =============================================================================
def pxv(v: float, sigma: float = 2.0, basis: Basis = Basis.OBSERVED) -> TrackedValue:
    return TrackedValue(value=v, unit="px", basis=basis, low=v - 2 * sigma, high=v + 2 * sigma)


def bb(left: float, off: float, w: float, h: float, z_bottom: float, ppm: float = PPM, gy: float = GY):
    return (left + off * ppm, gy - (z_bottom + h) * ppm, left + (off + w) * ppm, gy - z_bottom * ppm)


MAIN_OPENINGS = [  # id, kind, storey, offset, width, height, sill
    ("o01", "window", 0, 1.00, 1.80, 1.20, 0.90),
    ("o02", "door", 0, 4.30, 1.00, 2.10, 0.00),
    ("o03", "window", 0, 6.80, 1.80, 1.20, 0.90),
    ("o04", "window", 1, 1.30, 1.20, 1.20, 0.90),
    ("o05", "window", 1, 4.20, 1.20, 1.20, 0.90),
    ("o06", "window", 1, 7.10, 1.20, 1.20, 0.90),
]
GARAGE_OPENING = ("o07", "garage_door", 0, 0.40, 2.40, 2.13, 0.00)
FT = {"window": FeatureType.WINDOW, "door": FeatureType.DOOR, "garage_door": FeatureType.GARAGE_DOOR}


def _opening_bbox(left, op):
    _, _, storey, off, w, h, sill = op
    return bb(left, off, w, h, FFL + storey * FTF + sill)


def make_analysis(*, door_scale: float = 1.0, with_doors: bool = True, with_eaves: bool = True,
                  multiview: bool = False, plan: bool = False) -> AnalysisResult:
    feats: list[DetectedFeature] = [
        DetectedFeature(feature_id="f_main", image_id=IMG, feature_type=FeatureType.FACADE,
                        bbox=(LX, GY - PLATE * PPM, LX + MAIN_W * PPM, GY), pixel_uncertainty=2.0,
                        attributes={"block": "main"}),
        DetectedFeature(feature_id="f_garage", image_id=IMG, feature_type=FeatureType.FACADE,
                        bbox=(GAR_LX, GY - 2.85 * PPM, GAR_LX + GAR_W * PPM, GY), pixel_uncertainty=2.0,
                        attributes={"block": "garage"}),
        DetectedFeature(feature_id="f_roof_main", image_id=IMG, feature_type=FeatureType.ROOF,
                        polygon=[(LX - 0.2 * PPM, GY - PLATE * PPM), (LX - 0.2 * PPM, GY - (PLATE + RISE) * PPM),
                                 (LX + 9.8 * PPM, GY - (PLATE + RISE) * PPM), (LX + 9.8 * PPM, GY - PLATE * PPM)],
                        pixel_uncertainty=2.0, attributes={"roof_form": "gable"}),
    ]
    main_ops, gar_ops = [], []
    for op in MAIN_OPENINGS:
        if op[1] == "door" and not with_doors:
            continue
        box = _opening_bbox(LX, op)
        if op[1] == "door" and door_scale != 1.0:
            h = (box[3] - box[1]) * door_scale
            box = (box[0], box[3] - h, box[2], box[3])
        feats.append(DetectedFeature(feature_id=op[0], image_id=IMG, feature_type=FT[op[1]], bbox=box,
                                     pixel_uncertainty=1.5))
        main_ops.append(ObservedOpening(feature_id=op[0], kind=op[1], bbox_px=box, storey_index=op[2],
                                        block_hint="main"))
    if with_doors:
        box = _opening_bbox(GAR_LX, GARAGE_OPENING)
        feats.append(DetectedFeature(feature_id="o07", image_id=IMG, feature_type=FeatureType.GARAGE_DOOR,
                                     bbox=box, pixel_uncertainty=1.5))
        gar_ops.append(ObservedOpening(feature_id="o07", kind="garage_door", bbox_px=box, storey_index=0,
                                       block_hint="garage"))
    unknown_px = TrackedValue(value=None, unit="px", basis=Basis.UNKNOWN)
    main = FacadeObservation(
        image_id=IMG, view=ViewDirection.FRONT, block_hint="main",
        storeys=inferred(2.0, "storeys") if with_eaves else TrackedValue(value=None, unit="storeys"),
        width_px=pxv(MAIN_W * PPM),
        eaves_height_px=pxv(PLATE * PPM) if with_eaves else unknown_px,
        ridge_height_px=pxv((PLATE + RISE) * PPM) if with_eaves else unknown_px,
        ground_y_px=GY, left_x_px=LX, roof_form="gable", roof_form_basis=Basis.INFERRED,
        ridge_axis_hint="parallel_to_view", openings=main_ops,
        finishes=[ObservedFinish(element="walls", appearance="red-brown brick-like", feature_ids=["r01"]),
                  ObservedFinish(element="roof", appearance="dark grey tile-like", feature_ids=["r03"])],
        feature_ids=["f_main", "f_roof_main"] + [o.feature_id for o in main_ops])
    garage = FacadeObservation(
        image_id=IMG, view=ViewDirection.FRONT, block_hint="garage", storeys=inferred(1.0, "storeys"),
        width_px=pxv(GAR_W * PPM), eaves_height_px=pxv(2.85 * PPM), ridge_height_px=pxv((2.85 + GAR_RISE) * PPM),
        ground_y_px=GY, left_x_px=GAR_LX, roof_form="gable", roof_form_basis=Basis.OBSERVED,
        apparent_pitch_deg=observed(GAR_PITCH, "deg", low=28.5, high=31.5),
        ridge_axis_hint="perpendicular_to_view", openings=gar_ops,
        finishes=[ObservedFinish(element="walls", appearance="red-brown brick-like", feature_ids=["r02"]),
                  ObservedFinish(element="garage_door", appearance="white panel-like", feature_ids=["r05"])],
        feature_ids=["f_garage"] + [o.feature_id for o in gar_ops])
    images = [ImageAsset(image_id=IMG, sha256="a" * 64, original_filename="front.png", media_type="image/png",
                         width_px=1600, height_px=1000, size_bytes=1, kind=ImageKind.ELEVATION_DRAWING,
                         view=ViewDirection.FRONT)]
    analyses = [ImageAnalysis(image_id=IMG, features=feats,
                              perspective=PerspectiveEstimate(method="test", foreshortening_uncertainty=0.02))]
    facades = [main, garage]
    mv = None
    if multiview:
        lppm, lgy, llx = 78.0, 800.0, 372.0
        lops = [("l01", "window", 0, 5.70, 0.90, 1.20, 0.90), ("l02", "window", 1, 3.90, 0.60, 0.90, 1.10)]
        lobs = []
        lfeats = []
        for op in lops:
            box = bb(llx, op[3], op[4], op[5], FFL + op[2] * FTF + op[6], ppm=lppm, gy=lgy)
            lfeats.append(DetectedFeature(feature_id=op[0], image_id=IMG_L, feature_type=FeatureType.WINDOW,
                                          bbox=box, pixel_uncertainty=1.5))
            lobs.append(ObservedOpening(feature_id=op[0], kind="window", bbox_px=box, storey_index=op[2],
                                        block_hint="main"))
        facades.append(FacadeObservation(
            image_id=IMG_L, view=ViewDirection.LEFT, block_hint="main", storeys=inferred(2.0, "storeys"),
            width_px=pxv(MAIN_D * lppm), eaves_height_px=pxv(PLATE * lppm),
            ridge_height_px=pxv((PLATE + RISE) * lppm), ground_y_px=lgy, left_x_px=llx, roof_form="gable",
            apparent_pitch_deg=observed(PITCH, "deg", low=33.9, high=36.1),
            ridge_axis_hint="perpendicular_to_view", openings=lobs, feature_ids=["l_facade"]))
        images.append(ImageAsset(image_id=IMG_L, sha256="b" * 64, original_filename="left.png",
                                 media_type="image/png", width_px=1400, height_px=900, size_bytes=1,
                                 kind=ImageKind.ELEVATION_DRAWING, view=ViewDirection.LEFT))
        analyses.append(ImageAnalysis(image_id=IMG_L, features=lfeats))
        k = PPM / lppm
        mv = MultiViewResult(
            method="test-orthogonal", image_ids=[IMG, IMG_L],
            linked_measurements={
                "main.depth_front_px_equiv": inferred(MAIN_D * PPM, "px", low=MAIN_D * PPM - 6,
                                                      high=MAIN_D * PPM + 6),
                "main.pitch_side_view_deg": observed(PITCH, "deg", low=33.9, high=36.1)},
            relative_scales={IMG_L: inferred(k, "ratio", low=k * 0.995, high=k * 1.005)})
    if plan:
        pppm = 50.0
        images.append(ImageAsset(image_id=IMG_P, sha256="c" * 64, original_filename="plan.png",
                                 media_type="image/png", width_px=1000, height_px=1000, size_bytes=1,
                                 kind=ImageKind.FLOOR_PLAN, view=ViewDirection.PLAN))
        analyses.append(ImageAnalysis(image_id=IMG_P, features=[
            DetectedFeature(feature_id="d1", image_id=IMG_P, feature_type=FeatureType.DIMENSION,
                            line=(100, 900, 100 + MAIN_W * pppm, 900), pixel_uncertainty=1.0,
                            attributes={"length_m": MAIN_W}),
            DetectedFeature(feature_id="d2", image_id=IMG_P, feature_type=FeatureType.DIMENSION,
                            line=(60, 100, 60, 100 + MAIN_D * pppm), pixel_uncertainty=1.0,
                            attributes={"length_m": MAIN_D}),
            DetectedFeature(feature_id="d_bad", image_id=IMG_P, feature_type=FeatureType.DIMENSION,
                            line=(0, 0, 10, 0), attributes={"length_m": "not a number"}),
            DetectedFeature(feature_id="outline", image_id=IMG_P, feature_type=FeatureType.BUILDING_OUTLINE,
                            bbox=(100, 100, 100 + (MAIN_W + GAR_W) * pppm, 100 + MAIN_D * pppm),
                            pixel_uncertainty=1.0),
        ]))
    return AnalysisResult(images=images, analyses=analyses, facades=facades, multiview=mv, primary_image_id=IMG)


def frontage_ref(**kw) -> ReferenceMeasurement:
    args = dict(image_id=IMG, feature_id="f_main", real_length=MAIN_W, tolerance=0.02,
                description="Frontage confirmed from a fictional measured survey")
    args.update(kw)
    return ReferenceMeasurement(**args)


def selection() -> AssemblySelection:
    return AssemblySelection(external_wall="ew_test", separating_wall="sw_test", internal_partition="ip_test",
                             ground_floor="gf_test", intermediate_floor="if_test", pitched_roof="pr_test",
                             flat_roof="fr_test", window="win_test", external_door="door_test",
                             garage_door="gdoor_test", foundation="fdn_test")


@pytest.fixture
def analysis():
    return make_analysis()


@pytest.fixture
def cal_ref(analysis):
    return calibrate_scale(analysis, frontage_ref())


@pytest.fixture
def hyps_ref(analysis, cal_ref):
    return {h.hypothesis_id: h for h in generate_geometry_hypotheses(analysis, cal_ref)}


@pytest.fixture
def hyps_uncal(analysis):
    return {h.hypothesis_id: h for h in generate_geometry_hypotheses(analysis, calibrate_scale(analysis))}


@pytest.fixture
def twin_a(hyps_ref, analysis):
    return build_parametric_twin(hyps_ref["H-A"], selection=selection(),
                                 visual_finishes=visual_finishes_from_analysis(analysis))


@pytest.fixture
def twin_b(hyps_ref):
    return build_parametric_twin(hyps_ref["H-B"], selection=selection())


def block(h, bid):
    return next(b for b in h.blocks if b.block_id == bid)


def metrics(twin):
    return compute_geometry_metrics(twin, 0.30, 0.20)


# =============================================================================
# Calibration
# =============================================================================
def test_reference_calibration_exact_scale_and_range(analysis, cal_ref):
    s = cal_ref.metres_per_pixel
    assert cal_ref.method == "reference_measurement"
    assert cal_ref.image_id == IMG
    assert s.value == pytest.approx(1.0 / PPM, rel=1e-12)
    px = MAIN_W * PPM
    hw = math.sqrt((2 * 2.0 / px) ** 2 + (0.02 / MAIN_W) ** 2 + 0.02 ** 2)
    assert s.low == pytest.approx(s.value * (1 - hw))
    assert s.high == pytest.approx(s.value * (1 + hw))
    assert s.basis == Basis.INFERRED
    assert s.correlation_group == GROUP
    assert s.distribution in (Distribution.NORMAL, Distribution.TRIANGULAR)
    assert 0.0 < s.relative_spread() < 0.06
    assert any("Cross-check" in n and "consistent" in n for n in cal_ref.notes)
    assert any("most useful" in n.lower() for n in cal_ref.notes)


def test_reference_by_points_in_millimetres(analysis):
    ref = ReferenceMeasurement(image_id=IMG, p0=(LX, 950.0), p1=(LX + MAIN_W * PPM, 950.0), real_length=9600,
                               unit="mm", tolerance=20)
    cal = calibrate_scale(analysis, ref)
    assert cal.metres_per_pixel.value == pytest.approx(1 / PPM)
    hyps = generate_geometry_hypotheses(analysis, cal)
    # endpoints span the main facade -> main width confirmed
    assert block(hyps[0], "main").width.basis == Basis.USER_CONFIRMED


@pytest.mark.parametrize("kw", [dict(unit="kg"), dict(feature_id="nope"), dict(image_id="img_missing"),
                                dict(real_length=5000.0), dict(tolerance=20.0)])
def test_reference_validation(analysis, kw):
    with pytest.raises(ValueError):
        calibrate_scale(analysis, frontage_ref(**kw))


def test_prior_cues_range_contains_truth_and_is_wider(analysis, cal_ref):
    cal = calibrate_scale(analysis)
    s = cal.metres_per_pixel
    assert cal.method == "prior_cues"
    assert s.basis == Basis.ASSUMED
    assert s.correlation_group == GROUP
    assert s.low <= 1 / PPM <= s.high
    assert s.relative_spread() > cal_ref.metres_per_pixel.relative_spread()
    names = {c.name for c in cal.cues}
    assert {"door leaf height", "garage door height"} <= names and any("wall plate" in n for n in names)
    for c in cal.cues:
        t = c.implied_m_per_px
        assert t.low < t.value < t.high and t.basis == Basis.ASSUMED
        assert c.assumed_real.basis == Basis.ASSUMED
    assert any("confirm the frontage width" in n for n in cal.notes)


def test_prior_cues_disagree_uses_union(analysis):
    a = make_analysis(door_scale=1.6)  # door detected 60% too tall
    cal = calibrate_scale(a)
    s = cal.metres_per_pixel
    assert any("scale cues disagree" in n for n in cal.notes)
    assert s.low == pytest.approx(min(c.implied_m_per_px.low for c in cal.cues))
    assert s.high == pytest.approx(max(c.implied_m_per_px.high for c in cal.cues))


def test_no_cues_gives_unknown_scale():
    a = make_analysis(with_doors=False, with_eaves=False)
    cal = calibrate_scale(a)
    assert cal.method == "none"
    assert cal.metres_per_pixel.value is None
    assert cal.metres_per_pixel.basis == Basis.UNKNOWN
    assert any("calibration measurement" in n for n in cal.notes)
    with pytest.raises(ValueError):
        generate_geometry_hypotheses(a, cal)


def test_dimensioned_plan_scale_transferred_to_front():
    a = make_analysis(plan=True)
    cal = calibrate_scale(a)
    assert cal.method == "dimensioned_plan"
    assert cal.image_id == IMG
    assert cal.metres_per_pixel.value == pytest.approx(1 / PPM, rel=2e-3)
    assert cal.metres_per_pixel.basis == Basis.INFERRED
    assert {c.feature_id for c in cal.cues} == {"d1", "d2"}
    assert any("invalid length_m" in n for n in cal.notes)
    hyps = generate_geometry_hypotheses(a, cal)
    assert len(hyps) == 2
    assert block(hyps[0], "main").width.basis == Basis.INFERRED


# =============================================================================
# Hypotheses
# =============================================================================
def test_calibrated_hypotheses_count_and_main_width_confirmed(hyps_ref):
    assert list(hyps_ref) == ["H-A", "H-B"]
    for h in hyps_ref.values():
        w = block(h, "main").width
        assert w.basis == Basis.USER_CONFIRMED
        assert w.value == pytest.approx(MAIN_W)
        assert (w.low, w.high) == (pytest.approx(MAIN_W - 0.02), pytest.approx(MAIN_W + 0.02))
        assert 0 < h.plausibility < 1 and h.calibration_method == "reference_measurement"
        assert any("assumed" in n.lower() for n in h.notes)


def test_h_a_depth_pitch_coupling(hyps_ref):
    m = block(hyps_ref["H-A"], "main")
    assert m.roof.ridge_axis == "x" and m.roof.form == RoofForm.GABLE
    assert m.roof.pitch_deg.basis == Basis.ASSUMED and m.roof.pitch_deg.value == pytest.approx(35.0)
    assert m.depth.value * math.tan(math.radians(m.roof.pitch_deg.value)) / 2 == pytest.approx(RISE, rel=1e-9)
    assert m.depth.value == pytest.approx(MAIN_D, abs=1e-6)
    assert m.depth.basis == Basis.ASSUMED
    assert 0.6 * MAIN_W - 1e-9 <= m.depth.low < m.depth.value < m.depth.high <= 1.2 * MAIN_W + 1e-9
    assert any("coupling" in n.lower() for n in hyps_ref["H-A"].notes)
    assert m.floor_to_floor.value == pytest.approx(FTF) and m.floor_to_floor.basis == Basis.INFERRED
    assert m.storeys.value == 2
    assert m.roof.verge_overhang_m.value == pytest.approx(0.20, abs=0.01)


def test_h_b_extension_rear_left_touching(hyps_ref):
    h = hyps_ref["H-B"]
    m = block(h, "main")
    ext = next(b for b in h.blocks if b.role == BlockRole.EXTENSION)
    assert m.depth.value == pytest.approx(7.20, abs=1e-6)
    assert m.roof.pitch_deg.value == pytest.approx(math.degrees(math.atan(2 * RISE / 7.20)))
    assert m.roof.pitch_deg.basis == Basis.ASSUMED
    assert ext.width.value == pytest.approx(4.80) and ext.depth.value == pytest.approx(3.60)
    assert (ext.depth.low, ext.depth.high) == (3.0, 4.5)
    assert ext.origin_x.value == pytest.approx(m.origin_x.value)
    assert ext.origin_y.value == pytest.approx(m.origin_y.value + m.depth.value)
    assert ext.storeys.value == 1 and ext.heated and ext.roof.form == RoofForm.FLAT
    assert ext.roof.parapet_height_m.value == 0.0
    assert ext.visible_sides == [] and ext.width.basis == Basis.ASSUMED
    rects = [Rect(b.block_id, b.origin_x.value, b.origin_y.value, b.origin_x.value + b.width.value,
                  b.origin_y.value + b.depth.value) for b in h.blocks]
    shared = [p for p in side_pieces(rects) if p.rid == "main" and p.neighbour == ext.block_id]
    assert shared and shared[0].side == Side.REAR


def test_garage_block(hyps_ref):
    g = block(hyps_ref["H-A"], "garage")
    assert g.role == BlockRole.GARAGE and g.heated is False
    assert g.width.value == pytest.approx(GAR_W) and g.width.basis == Basis.INFERRED
    assert g.origin_x.value == pytest.approx(MAIN_W)  # snapped (0.3 px gap)
    assert g.roof.ridge_axis == "y" and g.roof.pitch_deg.basis == Basis.OBSERVED
    assert g.roof.pitch_deg.value == pytest.approx(GAR_PITCH)
    assert g.depth.value == 6.0 and (g.depth.low, g.depth.high) == (5.0, 7.0) and g.depth.basis == Basis.ASSUMED
    assert g.visible_sides == [Side.FRONT]


def test_observed_openings(hyps_ref):
    ops = {o.feature_id: o for o in hyps_ref["H-A"].openings}
    assert set(ops) == {f"o0{i}" for i in range(1, 8)}
    for fid, kind, storey, off, w, h, sill in MAIN_OPENINGS + [GARAGE_OPENING]:
        o = ops[fid]
        assert o.kind.value == kind and o.storey == storey and o.side == Side.FRONT
        assert o.block_id == ("garage" if fid == "o07" else "main")
        assert o.offset_m.value == pytest.approx(off, abs=1e-6)
        assert o.width_m.value == pytest.approx(w, abs=1e-6)
        assert o.height_m.value == pytest.approx(h, abs=1e-6)
        assert o.sill_m.value == pytest.approx(sill, abs=1e-6)
        assert o.width_m.basis == Basis.INFERRED and o.hidden_side_rule is None


def test_uncalibrated_three_hypotheses(hyps_uncal):
    assert list(hyps_uncal) == ["H-A", "H-B", "H-C"]
    a, c = block(hyps_uncal["H-A"], "main"), block(hyps_uncal["H-C"], "main")
    assert c.depth.value > a.depth.value and c.roof.pitch_deg.value < a.roof.pitch_deg.value
    w = a.width
    assert w.basis == Basis.ASSUMED and w.relative_spread() > 0.10
    assert sum(h.plausibility for h in hyps_uncal.values()) == pytest.approx(1.0)
    assert a.floor_to_floor.basis == Basis.ASSUMED  # prior when uncalibrated


def test_scale_derived_dims_share_correlation_group(hyps_uncal, hyps_ref):
    for hyps in (hyps_uncal, hyps_ref):
        h = hyps["H-A"]
        g = block(h, "garage")
        dims = [g.width, g.origin_x, block(h, "main").depth]
        if block(h, "main").width.basis != Basis.USER_CONFIRMED:
            dims.append(block(h, "main").width)
        for o in h.openings:
            dims += [o.offset_m, o.width_m, o.height_m, o.sill_m]
        assert all(tv.correlation_group == GROUP for tv in dims)
    assert block(hyps_ref["H-A"], "main").floor_to_floor.correlation_group == GROUP


def test_multiview_narrows_depth_and_reduces_hypotheses(hyps_uncal):
    a = make_analysis(multiview=True)
    hyps = generate_geometry_hypotheses(a, calibrate_scale(a))  # uncalibrated, but depth observed
    assert [h.hypothesis_id for h in hyps] == ["H-A", "H-B"]
    m = block(hyps[0], "main")
    assert m.depth.value == pytest.approx(MAIN_D, rel=0.02)
    assert m.depth.relative_spread() < block(hyps_uncal["H-A"], "main").depth.relative_spread()
    assert m.roof.pitch_deg.basis == Basis.OBSERVED and m.roof.pitch_deg.value == pytest.approx(PITCH)
    assert Side.LEFT in m.visible_sides
    left = [o for o in hyps[0].openings if o.side == Side.LEFT]
    assert len(left) == 2
    gf = next(o for o in left if o.storey == 0)
    assert gf.offset_m.value == pytest.approx(5.70, rel=0.02) and gf.width_m.value == pytest.approx(0.90, rel=0.02)
    ext = next(b for b in hyps[1].blocks if b.role == BlockRole.EXTENSION)
    assert ext.origin_x.value + ext.width.value == pytest.approx(m.origin_x.value + m.width.value)  # rear-right


def test_hypotheses_deterministic_and_need_front(analysis, cal_ref):
    h1 = [h.model_dump(mode="json") for h in generate_geometry_hypotheses(analysis, cal_ref)]
    h2 = [h.model_dump(mode="json") for h in generate_geometry_hypotheses(analysis, cal_ref)]
    assert h1 == h2
    no_front = analysis.model_copy(update={"facades": []})
    with pytest.raises(ValueError):
        generate_geometry_hypotheses(no_front, cal_ref)


# =============================================================================
# Builder
# =============================================================================
def test_build_twin_valid_and_hidden_openings(twin_a, hyps_ref):
    assert twin_a.source_hypothesis_id == "H-A" and twin_a.version == 1
    m = metrics(twin_a)
    assert m.gia_m2 > 0 and not any("separating wall" in w for w in m.warnings)
    hidden = [o for o in twin_a.openings if o.hidden_side_rule]
    assert hidden
    assert all(o.width_m.basis == Basis.ASSUMED and o.width_m.source == "hidden-side rule" for o in hidden)
    assert not any(o.block_id == "garage" for o in hidden)  # unheated
    assert not any(o.side == Side.FRONT for o in hidden)
    patio = [o for o in hidden if o.kind.value == "patio_door"]
    assert len(patio) == 1 and patio[0].side == Side.REAR and patio[0].block_id == "main" and patio[0].storey == 0
    assert (patio[0].width_m.value, patio[0].height_m.value) == (1.8, 2.1)
    rear_area = sum(p.external_rect_area_m2 for p in m.pieces
                    if p.block_id == "main" and p.side == Side.REAR and p.exposure == "external")
    glazed = sum(o.width_m.value * o.height_m.value for o in hidden if o.block_id == "main" and o.side == Side.REAR)
    assert glazed == pytest.approx(0.20 * rear_area, abs=1.44)
    # never on shared pieces; every rule opening deducted from an external piece
    piece_of = {oid: p for p in m.pieces for oid in p.opening_ids}
    for o in hidden:
        assert piece_of[o.opening_id].exposure == "external"
    # observed openings kept untouched
    assert {o.feature_id for o in twin_a.openings if o.feature_id} == {o.feature_id for o in hyps_ref["H-A"].openings}


def test_hidden_openings_never_on_shared_pieces_l_shape(twin_b):
    m = metrics(twin_b)
    piece_of = {oid: p for p in m.pieces for oid in p.opening_ids}
    hidden = [o for o in twin_b.openings if o.hidden_side_rule]
    assert hidden and all(piece_of[o.opening_id].exposure == "external" for o in hidden)
    assert any(o.block_id == "rear_ext" for o in hidden)
    assert not any("separating wall" in w for w in m.warnings)


def test_visual_finishes(analysis, twin_a):
    vf = {v.element: v for v in visual_finishes_from_analysis(analysis)}
    assert set(vf) == {"walls", "roof", "garage_door"}
    assert vf["walls"].colour_hex == "#8B4A36" and vf["roof"].colour_hex == "#4A4D53"
    assert vf["garage_door"].colour_hex == "#ECEBE5"
    assert all(v.basis == Basis.INFERRED and "does not establish" in v.caveat for v in vf.values())
    assert sorted(vf["walls"].feature_ids) == ["r01", "r02"]
    assert twin_a.assemblies == selection()  # finishes never change assemblies


# =============================================================================
# Edits
# =============================================================================
def edit(twin, target_type, target_id, field, value, **kw):
    return apply_twin_edit(twin, TwinEdit(target_type=target_type, target_id=target_id, field=field, value=value,
                                          **kw))


def test_width_edit_reflows_garage_and_never_mutates(twin_a):
    before = twin_a.model_dump(mode="json")
    t2 = edit(twin_a, "block", "main", "width", 10.0, reason="measured")
    assert twin_a.model_dump(mode="json") == before
    assert t2.version == twin_a.version + 1 and len(t2.edit_log) == 1
    rec = t2.edit_log[0]
    assert rec.target == "block:main" and rec.old_value == pytest.approx(MAIN_W) and rec.new_value == 10.0
    assert rec.new_basis == Basis.USER_CONFIRMED and rec.old_basis == Basis.USER_CONFIRMED
    w = t2.block("main").width
    assert w.value == 10.0 and w.basis == Basis.USER_CONFIRMED and w.history[-1].new_value == 10.0
    g = t2.block("garage")
    assert g.origin_x.value == pytest.approx(10.0) and g.origin_x.history[-1].actor == "system:reflow"
    metrics(t2)
    t3 = edit(t2, "block", "main", "width", "9 m", tolerance=0.05)
    assert t3.block("garage").origin_x.value == pytest.approx(9.0)
    assert (t3.block("main").width.low, t3.block("main").width.high) == (pytest.approx(8.95), pytest.approx(9.05))
    assert t3.version == 3


def test_width_and_depth_edits_on_l_shape(twin_b):
    t2 = edit(twin_b, "block", "main", "width", 11.0)
    assert t2.block("rear_ext").origin_x.value == pytest.approx(0.0)  # attached at rear-left: keeps position
    assert t2.block("garage").origin_x.value == pytest.approx(11.0)
    t3 = edit(t2, "block", "main", "depth", 8.0)
    assert t3.block("rear_ext").origin_y.value == pytest.approx(8.0)  # attached at rear: moves
    assert t3.block("garage").origin_y.value == pytest.approx(0.0)
    metrics(t3)


def test_depth_edit_regenerates_hidden_openings(twin_a):
    t2 = edit(twin_a, "block", "main", "depth", 11.0)
    left0 = sorted(o.offset_m.value for o in twin_a.openings if o.hidden_side_rule and o.side == Side.LEFT)
    left1 = sorted(o.offset_m.value for o in t2.openings if o.hidden_side_rule and o.side == Side.LEFT)
    assert left0 and left1 and left0 != left1
    for o in t2.openings:
        if o.hidden_side_rule and o.side in (Side.LEFT, Side.RIGHT):
            assert o.offset_m.value + o.width_m.value <= 11.0
    assert not any("beyond" in w for w in metrics(t2).warnings)


@pytest.mark.parametrize("target_type,target_id,field,value", [
    ("block", "main", "width", -1.0),
    ("block", "main", "width", 0.0),
    ("block", "main", "width", "abc"),
    ("block", "main", "width", True),
    ("block", "main", "depth", float("nan")),
    ("block", "main", "storeys", 2.5),
    ("block", "main", "storeys", 7),
    ("block", "main", "storeys", 0),
    ("block", "main", "colour", "red"),
    ("block", "nope", "width", 5.0),
    ("block", "garage", "origin_x", 5.0),  # would overlap the main block
    ("roof", "main", "pitch_deg", 80.0),
    ("roof", "main", "pitch_deg", 0.0),
    ("roof", "main", "form", "dome"),
    ("roof", "main", "ridge_axis", "z"),
    ("hidden", None, "rear_glazing_ratio", 0.95),
    ("hidden", None, "side_glazing_ratio", -0.1),
    ("hidden", None, "rear_door_count", 1.5),
    ("opening", "obs:o01", "width_m", 50.0),
    ("opening", "obs:o01", "width_m", 9.0),  # does not fit on the wall
    ("opening", "obs:o01", "storey", 3),
    ("opening", "missing", "width_m", 1.0),
    ("opening", None, "add", {"block_id": "main", "side": "rear", "kind": "window", "width_m": 1.0,
                              "height_m": 1.0, "evil": "x"}),
    ("assembly", None, "roof_colour", "x"),
    ("assembly", None, "external_wall", "bad id with spaces"),
    ("assembly", "garage", "foundation", "fdn_x"),
    ("twin", None, "dwellings", 0),
    ("twin", None, "unknown", 1),
])
def test_invalid_edits_raise(twin_a, target_type, target_id, field, value):
    with pytest.raises(ValueError):
        edit(twin_a, target_type, target_id, field, value)


def test_roof_edits(twin_a):
    t = edit(twin_a, "roof", "main", "pitch_deg", 40.0)
    assert t.block("main").roof.pitch_deg.value == 40.0 and t.block("main").roof.pitch_deg.basis == Basis.USER_CONFIRMED
    t = edit(t, "roof", "main", "form", "hip")
    assert t.block("main").roof.form == RoofForm.HIP
    t = edit(t, "roof", "garage", "form", "flat")
    t = edit(t, "roof", "garage", "parapet_height_m", 0.4)
    g = t.block("garage").roof
    assert g.form == RoofForm.FLAT and g.parapet_height_m.value == 0.4
    t = edit(t, "roof", "garage", "form", "monopitch")
    t = edit(t, "roof", "garage", "high_side", "front")
    assert t.block("garage").roof.high_side == Side.FRONT
    assert 0 < t.block("garage").roof.pitch_deg.value < 75
    t = edit(t, "roof", "main", "eaves_overhang_m", 0.4)
    t = edit(t, "roof", "main", "ridge_axis", "y")
    assert t.version == 9
    metrics(t)


def test_opening_edits_add_delete(twin_a):
    t = edit(twin_a, "opening", "obs:o01", "width_m", 2.0)
    o = next(o for o in t.openings if o.opening_id == "obs:o01")
    assert o.width_m.value == 2.0 and o.width_m.basis == Basis.USER_CONFIRMED
    t = edit(t, "opening", "obs:o02", "kind", "patio_door")
    t = edit(t, "opening", "obs:o01", "assembly_id", "win_triple")
    t = edit(t, "opening", None, "add", {"block_id": "garage", "side": "right", "kind": "door", "width_m": 0.9,
                                         "height_m": 2.0, "offset_m": 1.0})
    added = [o for o in t.openings if o.opening_id.startswith("user:garage")]
    assert len(added) == 1 and added[0].sill_m.value == 0.0 and added[0].offset_m.basis == Basis.USER_CONFIRMED
    assert "garage:right" in t.hidden.specified_sides
    t = edit(t, "opening", "obs:o07", "delete", True)
    assert not any(o.opening_id == "obs:o07" for o in t.openings)
    assert t.edit_log[-1].old_value["opening_id"] == "obs:o07"
    metrics(t)


def test_editing_rule_opening_freezes_side(twin_a):
    rid = next(o.opening_id for o in twin_a.openings if o.hidden_side_rule and o.side == Side.LEFT)
    t = edit(twin_a, "opening", rid, "width_m", 1.0)
    assert "main:left" in t.hidden.specified_sides
    o = next(o for o in t.openings if o.opening_id == rid)
    assert o.hidden_side_rule is None and o.width_m.basis == Basis.USER_CONFIRMED
    t2 = edit(t, "block", "main", "depth", 10.0)  # regenerates, but main:left stays as specified
    assert any(o.opening_id == rid for o in t2.openings)
    assert not any(o.hidden_side_rule and o.block_id == "main" and o.side == Side.LEFT for o in t2.openings)
    # deleting the only rule window of a side stays deleted after regeneration
    t3 = edit(twin_a, "opening", rid, "delete", None)
    t4 = edit(t3, "block", "main", "depth", 10.0)
    assert not any(o.block_id == "main" and o.side == Side.LEFT for o in t4.openings)


def test_hidden_edits_regenerate(twin_a):
    def rear_glazed(t):
        return sum(o.width_m.value * o.height_m.value for o in t.openings
                   if o.hidden_side_rule and o.block_id == "main" and o.side == Side.REAR)

    t = edit(twin_a, "hidden", None, "rear_glazing_ratio", 0.35)
    assert t.hidden.rear_glazing_ratio.basis == Basis.USER_CONFIRMED
    assert rear_glazed(t) > rear_glazed(twin_a)
    t = edit(t, "hidden", None, "rear_door_count", 0)
    assert not any(o.kind.value == "patio_door" for o in t.openings)
    t = edit(t, "hidden", None, "typical_window_width_m", 0.9)
    assert all(o.width_m.value == 0.9 for o in t.openings if o.hidden_side_rule)
    t = edit(t, "hidden", None, "side_glazing_ratio", 0.0)
    assert not any(o.hidden_side_rule and o.side in (Side.LEFT, Side.RIGHT) for o in t.openings)


def test_assembly_and_twin_edits(twin_a):
    t = edit(twin_a, "assembly", None, "external_wall", "ew_timber_frame_brick")
    assert t.assemblies.external_wall == "ew_timber_frame_brick"
    assert t.assemblies.basis["external_wall"] == Basis.USER_CONFIRMED
    assert [o.opening_id for o in t.openings] == [o.opening_id for o in twin_a.openings]
    t = edit(t, "assembly", "garage", "external_wall", "ew_single_skin")
    assert t.assemblies.block_overrides["garage"]["external_wall"] == "ew_single_skin"
    assert t.assemblies.basis["garage/external_wall"] == Basis.USER_CONFIRMED
    t = edit(t, "twin", None, "name", "Plot 7 (fictional)")
    t = edit(t, "twin", None, "dwellings", 2)
    t = edit(t, "twin", None, "bathrooms", 3)
    assert (t.name, t.dwellings, t.bathrooms.value, t.bathrooms.basis) == ("Plot 7 (fictional)", 2, 3,
                                                                           Basis.USER_CONFIRMED)
    t = edit(t, "block", "garage", "heated", True)
    assert any(o.hidden_side_rule and o.block_id == "garage" for o in t.openings)
    assert t.version == 7 and len(t.edit_log) == 6


def test_storeys_edit(twin_a):
    t = edit(twin_a, "block", "garage", "storeys", 2)
    assert t.block("garage").storeys.value == 2 and t.block("garage").storeys.basis == Basis.USER_CONFIRMED
    metrics(t)


def test_twin_hash(twin_a):
    h = twin_hash(twin_a)
    assert len(h) == 64 and h == twin_hash(twin_a.model_copy(deep=True))
    t2 = edit(twin_a, "block", "main", "width", 10.0)
    assert twin_hash(t2) != h
    # edit_log and value histories are excluded
    t3 = twin_a.model_copy(deep=True)
    t3.edit_log.append(t2.edit_log[0])
    t3.blocks[0].width = t3.blocks[0].width.model_copy(update={"history": list(t2.blocks[0].width.history)})
    assert twin_hash(t3) == h
    # regenerating unchanged hidden openings is a no-op
    assert twin_hash(regenerate_hidden_openings(twin_a)) == h


# =============================================================================
# Mesh
# =============================================================================
def simple_twin(form=RoofForm.GABLE, axis="x", w=10.0, d=8.0, pitch=35.0, eo=0.0, vo=0.0, high=None, parapet=0.0,
                storeys=2, openings=(), finishes=()):
    b = Block(block_id="B1", role=BlockRole.MAIN, origin_x=assumed(0.0, "m"), origin_y=assumed(0.0, "m"),
              width=assumed(w, "m"), depth=assumed(d, "m"), storeys=assumed(float(storeys), "storeys"),
              floor_to_floor=assumed(FTF, "m"), ground_floor_level=assumed(FFL, "m"),
              roof=RoofSpec(form=form, pitch_deg=assumed(pitch, "deg"), ridge_axis=axis,
                            eaves_overhang_m=assumed(eo, "m"), verge_overhang_m=assumed(vo, "m"), high_side=high,
                            parapet_height_m=assumed(parapet, "m")),
              visible_sides=[Side.FRONT])
    return BuildingTwin(twin_id="t1", blocks=[b], openings=list(openings),
                        hidden=HiddenSideAssumptions(rear_glazing_ratio=assumed(0.2, "fraction"),
                                                     side_glazing_ratio=assumed(0.04, "fraction")),
                        assemblies=selection(), visual_finishes=list(finishes))


def node_mesh(scene, name):
    return scene.geometry[scene.graph[name][1]]


def test_wall_box_and_gable_volumes():
    w, d, p = 10.0, 8.0, 35.0
    plate = FFL + 2 * FTF
    for axis, span, length in (("x", d, w), ("y", w, d)):
        sc = build_mesh(simple_twin(axis=axis))
        walls = node_mesh(sc, "B1/walls")
        assert walls.volume == pytest.approx(w * d * plate)
        assert walls.metadata["block_id"] == "B1" and walls.metadata["kind"] == "walls"
        rise = 0.5 * span * math.tan(math.radians(p))
        roof = node_mesh(sc, "B1/roof")
        assert roof.is_watertight
        assert roof.volume == pytest.approx(0.5 * span * rise * length)
        assert roof.bounds[1][2] == pytest.approx(plate + rise)


def test_gable_overhang_extents():
    eo, vo, p = 0.3, 0.2, 35.0
    roof = node_mesh(build_mesh(simple_twin(eo=eo, vo=vo)), "B1/roof")
    (x0, y0, z0), (x1, y1, _) = roof.bounds
    assert (x0, x1) == (pytest.approx(-vo), pytest.approx(10 + vo))
    assert (y0, y1) == (pytest.approx(-eo), pytest.approx(8 + eo))
    assert z0 == pytest.approx(FFL + 2 * FTF - eo * math.tan(math.radians(p)))


def test_hip_and_monopitch_and_flat_volumes():
    w, d = 10.0, 8.0
    rise = 0.5 * d * math.tan(math.radians(30.0))
    hip = node_mesh(build_mesh(simple_twin(form=RoofForm.HIP, pitch=30.0)), "B1/roof")
    assert hip.volume == pytest.approx(d * rise * (3 * w - d) / 6.0)
    sq = node_mesh(build_mesh(simple_twin(form=RoofForm.HIP, w=8.0, d=8.0, pitch=30.0)), "B1/roof")
    assert sq.volume == pytest.approx(8.0 * rise * (3 * 8.0 - 8.0) / 6.0)  # pyramid: span^2 rise / 3
    for high, span, length in ((Side.FRONT, d, w), (Side.LEFT, w, d)):
        mono = node_mesh(build_mesh(simple_twin(form=RoofForm.MONOPITCH, pitch=10.0, high=high, storeys=1)),
                         "B1/roof")
        r = span * math.tan(math.radians(10.0))
        assert mono.volume == pytest.approx(0.5 * span * r * length)
    flat = node_mesh(build_mesh(simple_twin(form=RoofForm.FLAT, pitch=0.0, storeys=1)), "B1/roof")
    assert flat.volume == pytest.approx(w * d * 0.25)
    par = node_mesh(build_mesh(simple_twin(form=RoofForm.FLAT, pitch=0.0, storeys=1, parapet=0.6)), "B1/roof")
    assert par.bounds[1][2] == pytest.approx(FFL + FTF + 0.6)


def test_mesh_of_demo_twin_nodes_colours_and_openings(twin_a):
    sc = build_mesh(twin_a)
    names = set(sc.graph.nodes_geometry)
    assert {"main/walls", "main/roof", "garage/walls", "garage/roof"} <= names
    assert {f"opening/{o.opening_id}" for o in twin_a.openings} <= names
    walls = node_mesh(sc, "main/walls")
    assert walls.metadata["colour_hex"] == "#8B4A36"  # from visual finishes only
    door = node_mesh(sc, "opening/obs:o07")
    assert door.metadata["kind"] == "garage_door" and door.metadata["opening_id"] == "obs:o07"
    assert door.metadata["colour_hex"] == "#ECEBE5"
    # opening box stands 0.04 m proud of the front facade (y = 0)
    assert door.bounds[0][1] == pytest.approx(-0.04) and door.bounds[1][1] == pytest.approx(0.0)
    g = twin_a.block("garage")
    o7 = next(o for o in twin_a.openings if o.opening_id == "obs:o07")
    assert door.bounds[0][0] == pytest.approx(g.origin_x.value + o7.offset_m.value)
    assert door.bounds[0][2] == pytest.approx(FFL + o7.sill_m.value)
    hid = next(o for o in twin_a.openings if o.hidden_side_rule and o.side == Side.REAR)
    hm = node_mesh(sc, f"opening/{hid.opening_id}")
    assert hm.metadata["opacity"] < 1.0 and hm.bounds[0][1] == pytest.approx(twin_a.block("main").depth.value)
    # without visual finishes: neutral defaults
    plain = build_mesh(twin_a.model_copy(update={"visual_finishes": []}))
    assert node_mesh(plain, "main/walls").metadata["colour_hex"] == DEFAULT_WALL_HEX


def test_gltf_orientation_and_export(twin_a):
    sc = build_mesh(twin_a)
    g = scene_for_gltf(sc)
    (x0, y0, z0), (x1, y1, z1) = sc.bounds
    (gx0, gy0, gz0), (gx1, gy1, gz1) = g.bounds
    assert (gy0, gy1) == (pytest.approx(z0), pytest.approx(z1))  # y-up
    assert (gz0, gz1) == (pytest.approx(-y1), pytest.approx(-y0))
    assert (gx0, gx1) == (pytest.approx(x0), pytest.approx(x1))
    assert sc.bounds[1][2] == pytest.approx(z1)  # original untouched
    data = g.export(file_type="glb")
    assert isinstance(data, (bytes, bytearray)) and data[:4] == b"glTF"


def test_plotly_meshes_valid(twin_a):
    sc = build_mesh(twin_a)
    meshes = scene_to_plotly_meshes(sc)
    assert len(meshes) == len(sc.graph.nodes_geometry)
    for m in meshes:
        n = len(m["x"])
        assert n == len(m["y"]) == len(m["z"]) > 0
        assert len(m["i"]) == len(m["j"]) == len(m["k"]) > 0
        idx = np.array([m["i"], m["j"], m["k"]])
        assert idx.min() >= 0 and idx.max() < n
        assert m["color"].startswith("#") and 0 < m["opacity"] <= 1
        assert "block_id" in m["meta"] and "kind" in m["meta"]
    import json

    json.dumps(meshes)  # serialisable for the UI


def test_piece_outline_polylines(twin_b):
    m = metrics(twin_b)
    lines = piece_outline_polylines(twin_b, m)
    assert len(lines) == len(m.pieces)
    for ln in lines:
        assert len(ln["x"]) == len(ln["y"]) == len(ln["z"]) == 5
        assert (ln["x"][0], ln["y"][0], ln["z"][0]) == (ln["x"][-1], ln["y"][-1], ln["z"][-1])
    assert {ln["exposure"] for ln in lines} == {"external", "shared"}


# =============================================================================
# Additional branches
# =============================================================================
def _garage_on_left(a: AnalysisResult) -> AnalysisResult:
    g = a.facades[1]
    dx = (LX - g.width_px.value - 0.2) - g.left_x_px
    ops = [o.model_copy(update={"bbox_px": (o.bbox_px[0] + dx, o.bbox_px[1], o.bbox_px[2] + dx, o.bbox_px[3])})
           for o in g.openings]
    return a.model_copy(update={"facades": [a.facades[0], g.model_copy(update={"left_x_px": g.left_x_px + dx,
                                                                               "openings": ops})]})


def test_garage_on_left_placement_and_reflow(analysis):
    a = _garage_on_left(analysis)
    hyps = {h.hypothesis_id: h for h in generate_geometry_hypotheses(a, calibrate_scale(a, frontage_ref()))}
    g = block(hyps["H-B"], "garage")
    assert g.origin_x.value == pytest.approx(-GAR_W)  # snapped to the main block's left wall
    t = build_parametric_twin(hyps["H-B"], selection=selection())
    assert not metrics(t).warnings
    t2 = edit(t, "block", "garage", "width", 4.0)  # grows rightwards: main + its rear extension follow
    assert t2.block("garage").origin_x.value == pytest.approx(-GAR_W)
    assert t2.block("main").origin_x.value == pytest.approx(0.8)
    assert t2.block("rear_ext").origin_x.value == pytest.approx(0.8)
    metrics(t2)


def test_front_facing_main_gable_uses_observed_pitch(analysis):
    m0 = analysis.facades[0].model_copy(update={"apparent_pitch_deg": observed(40.0, "deg", low=38.0, high=42.0),
                                                "ridge_axis_hint": "perpendicular_to_view"})
    a = analysis.model_copy(update={"facades": [m0, analysis.facades[1]]})
    h = generate_geometry_hypotheses(a, calibrate_scale(a, frontage_ref()))[0]
    m = block(h, "main")
    assert m.roof.ridge_axis == "y" and m.roof.pitch_deg.basis == Basis.OBSERVED
    assert m.roof.pitch_deg.value == pytest.approx(40.0)
    assert m.depth.value == pytest.approx(0.85 * MAIN_W) and m.depth.basis == Basis.ASSUMED


def test_patio_door_moves_to_extension_when_main_rear_covered(twin_b):
    t = edit(twin_b, "block", "rear_ext", "width", MAIN_W)  # extension now covers the whole main rear
    patio = [o for o in t.openings if o.kind.value == "patio_door"]
    assert len(patio) == 1 and patio[0].block_id == "rear_ext" and patio[0].side == Side.REAR
    assert not any(o.hidden_side_rule and o.block_id == "main" and o.side == Side.REAR for o in t.openings)
    metrics(t)


def test_inputs_not_mutated(analysis, cal_ref):
    a0, c0 = analysis.model_dump(mode="json"), cal_ref.model_dump(mode="json")
    hyps = generate_geometry_hypotheses(analysis, cal_ref)
    h0 = hyps[0].model_dump(mode="json")
    build_parametric_twin(hyps[0], selection=selection())
    assert analysis.model_dump(mode="json") == a0 and cal_ref.model_dump(mode="json") == c0
    assert hyps[0].model_dump(mode="json") == h0
