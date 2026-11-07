"""Review round 2, group D: vision interpretation, calibration, hypotheses and twin-builder provenance.

Regression tests for VIS-2 / UI-2 (user storey indices), VIS-3 / VIS-7 / VIS-10 (manual feature merge),
VIS-5 (VLM cross-check only), VIS-6 (superseded reference), VIS-8 / VIS-9 / LOW-2 / SPEC-1 (concept
references), VIS-11 / UI-10 (roof annotations), SPEC-3 (calibration label), SPEC-6 (unmodelled elements),
SPEC-10 (oblique bias), UI-6 (storeys-eaves coupling), UI-7 (H-B never deeper than H-A), SEC-2 / LOW-3 /
LOW-4 (ingest) and the floor-plan side of the shared annotation contract.
"""

from __future__ import annotations

import io
import json
import math
import tracemalloc
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from housebuilder_vision.core.models import (
    AnalysisResult,
    DetectedFeature,
    FacadeObservation,
    FeatureType,
    ImageAnalysis,
    ImageAsset,
    ImageKind,
    ObservedOpening,
    PerspectiveEstimate,
    ReferenceMeasurement,
    TwinEdit,
    ViewDirection,
)
from housebuilder_vision.core.provenance import Basis, EditRecord, TrackedValue
from housebuilder_vision.demo.build_demo import (
    DATA_DIR,
    FRONT_IMAGE,
    LEFT_IMAGE,
    build_demo_project,
    demo_registry,
    main_facade_feature_id,
)
from housebuilder_vision.quantities import calculate_quantities, default_library, default_selection
from housebuilder_vision.twin.builder import (
    apply_twin_edit,
    build_parametric_twin,
    coupling_warnings,
    plate_height,
    visual_finishes_from_analysis,
)
from housebuilder_vision.twin.calibration import calibrate_scale, plan_evidence, resolve_reference
from housebuilder_vision.twin.hypotheses import FTF_PLAUSIBLE, generate_geometry_hypotheses
from housebuilder_vision.vision.adapters import default_registry
from housebuilder_vision.vision.analysis import CONCEPT_CAP_REASON, analyse_images
from housebuilder_vision.vision.ingest import (
    ImageRejected,
    decode_rgb,
    ingest_image,
    ingest_path,
    load_image_array,
    stored_image_path,
)
from housebuilder_vision.vision.vlm_adapter import parse_vlm_json

CONCEPT_IMAGE = DATA_DIR / "concept_render_example.jpg"


# =============================================================================
# Helpers
# =============================================================================
@pytest.fixture(scope="module")
def store(tmp_path_factory):
    return tmp_path_factory.mktemp("review2_store")


@pytest.fixture(scope="module")
def reg():
    return demo_registry()


@pytest.fixture(scope="module")
def front(store):
    return ingest_path(FRONT_IMAGE, kind=ImageKind.ELEVATION_DRAWING, view=ViewDirection.FRONT, store_dir=store)


@pytest.fixture(scope="module")
def front_base(front, store, reg):
    return analyse_images([front], store_dir=store, registry=reg)


def blank(store, w, h, name, kind=ImageKind.PHOTOGRAPH, view=ViewDirection.FRONT, colour=(205, 205, 205)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, "PNG")
    return ingest_image(buf.getvalue(), name, kind=kind, view=view, store_dir=store)


def feat(img, fid, t, *, basis=Basis.OBSERVED, **kw) -> DetectedFeature:
    return DetectedFeature(feature_id=fid, image_id=img.image_id, feature_type=FeatureType(t), basis=basis,
                           method="manual-annotation", method_version="user", **kw)


def facade_of(res, block="main", image_id=None):
    return next(f for f in res.facades if f.block_hint == block and (image_id is None or f.image_id == image_id))


def feature(res, fid):
    return next(f for a in res.analyses for f in a.features if f.feature_id == fid)


def townhouse_rows(img):
    """3-storey townhouse 6 m wide at 100 px/m: integral garage + door on the ground floor."""
    return [
        feat(img, "t_fac", "facade", bbox=(100, 175, 700, 1000), attributes={"block": "main"}),
        feat(img, "t_gnd", "ground_line", line=(100, 1000, 700, 1000)),
        feat(img, "t_eav", "eaves_line", line=(100, 175, 700, 175)),
        feat(img, "t_rdg", "ridge_line", line=(100, 50, 700, 50)),
        feat(img, "t_gd", "garage_door", bbox=(130, 790, 380, 1000), attributes={"storey": 0}),
        feat(img, "t_d", "door", bbox=(500, 790, 600, 1000), attributes={"storey": 0}),
        feat(img, "t_w1", "window", bbox=(150, 600, 300, 730), attributes={"storey": 1}),
        feat(img, "t_w2", "window", bbox=(450, 600, 600, 730), attributes={"storey": 1}),
        feat(img, "t_w3", "window", bbox=(150, 330, 300, 460), attributes={"storey": 2}),
        feat(img, "t_w4", "window", bbox=(450, 330, 600, 460), attributes={"storey": 2}),
    ]


# =============================================================================
# VIS-2 / UI-2: user storey indices are authoritative
# =============================================================================
def test_user_storeys_townhouse_three_storeys(store, reg):
    img = blank(store, 800, 1100, "townhouse.png")
    res = analyse_images([img], store_dir=store, registry=reg, manual_features={img.image_id: townhouse_rows(img)})
    fo = facade_of(res)
    assert fo.storeys.value == 3 and fo.storeys.basis == Basis.USER_CONFIRMED
    assert "storey indices entered by the user" in fo.storeys.note
    assert sorted((o.feature_id, o.storey_index) for o in fo.openings) == [
        ("t_d", 0), ("t_gd", 0), ("t_w1", 1), ("t_w2", 1), ("t_w3", 2), ("t_w4", 2)]
    ref = ReferenceMeasurement(image_id=img.image_id, real_length=6.0, tolerance=0.02)
    hyp = generate_geometry_hypotheses(res, calibrate_scale(res, ref))[0]
    main = hyp.blocks[0]
    assert main.storeys.value == 3
    assert sorted(o.storey for o in hyp.openings if o.side.value == "front") == [0, 0, 1, 1, 2, 2]


@pytest.mark.parametrize("kind", [ImageKind.PHOTOGRAPH, ImageKind.AI_CONCEPT])
def test_doors_only_ground_floor_with_user_storeys(store, reg, kind):
    img = blank(store, 1000, 700, f"house_{kind.value}.png", kind=kind, colour=(200, 200, 201 + len(kind.value)))
    rows = [
        feat(img, "h_fac", "facade", bbox=(200, 250, 800, 650), attributes={"block": "main"}),
        feat(img, "h_gnd", "ground_line", line=(200, 650, 800, 650)),
        feat(img, "h_eav", "eaves_line", line=(200, 300, 800, 300)),
        feat(img, "h_door", "door", bbox=(450, 520, 510, 650), attributes={"storey": 0}),
        feat(img, "h_w1", "window", bbox=(260, 360, 360, 440), attributes={"storey": 1}),
        feat(img, "h_w2", "window", bbox=(640, 360, 740, 440), attributes={"storey": 1}),
    ]
    res = analyse_images([img], store_dir=store, registry=reg, manual_features={img.image_id: rows})
    fo = facade_of(res)
    assert fo.storeys.value == 2
    # user-confirmed, but a concept reference is capped at inferred
    assert fo.storeys.basis == (Basis.INFERRED if kind == ImageKind.AI_CONCEPT else Basis.USER_CONFIRMED)
    assert {o.feature_id: o.storey_index for o in fo.openings} == {"h_door": 0, "h_w1": 1, "h_w2": 1}


def test_door_row_below_windows_counts_as_a_storey_without_user_storeys(store, reg):
    img = blank(store, 1000, 700, "doorrow.png", colour=(190, 200, 210))
    rows = [feat(img, "r_fac", "facade", bbox=(200, 250, 800, 650), attributes={"block": "main"}),
            feat(img, "r_gnd", "ground_line", line=(200, 650, 800, 650)),
            feat(img, "r_eav", "eaves_line", line=(200, 300, 800, 300)),
            feat(img, "r_door", "door", bbox=(450, 520, 510, 650)),
            feat(img, "r_w1", "window", bbox=(260, 360, 360, 440)),
            feat(img, "r_w2", "window", bbox=(640, 360, 740, 440))]
    res = analyse_images([img], store_dir=store, registry=reg, manual_features={img.image_id: rows})
    fo = facade_of(res)
    assert fo.storeys.value == 2 and fo.storeys.basis == Basis.INFERRED and "door row" in fo.storeys.note
    assert {o.feature_id: o.storey_index for o in fo.openings} == {"r_door": 0, "r_w1": 1, "r_w2": 1}


def test_demo_storeys_unchanged(front_base):
    main = facade_of(front_base, "main")
    assert main.storeys.value == 2 and main.storeys.basis == Basis.INFERRED
    assert facade_of(front_base, "garage").storeys.value == 1


# =============================================================================
# VIS-3 / VIS-7 / VIS-10: manual feature merge
# =============================================================================
def test_inactive_annotation_never_supersedes(front, store, reg, front_base):
    det = feature(front_base, main_facade_feature_id(front_base, front.image_id))
    ann = feat(front, "usr:ann1", "facade", bbox=det.bbox, attributes={"block": "main"}, basis=Basis.USER_CONFIRMED,
               active=False)
    res = analyse_images([front], store_dir=store, registry=reg, manual_features={front.image_id: [ann]})
    assert feature(res, det.feature_id).active
    assert sorted(f.block_hint for f in res.facades) == ["garage", "main"]
    a = feature(res, "usr:ann1")
    assert a.active is False and a.basis == Basis.USER_CONFIRMED
    assert [(h.actor, h.field, h.reason) for h in a.history] == [("user", "active", "rejected")]


def test_rejected_detection_keeps_its_basis(front, store, reg, front_base):
    win = next(f for f in front_base.analyses[0].features if f.feature_type == FeatureType.WINDOW)
    rec = EditRecord(actor="user", target=win.feature_id, field="active", old_value=True, new_value=False,
                     old_basis=win.basis, new_basis=win.basis, reason="rejected")
    rej = win.model_copy(update={"active": False, "history": [rec]}, deep=True)
    res = analyse_images([front], store_dir=store, registry=reg, manual_features={front.image_id: [rej]})
    w = feature(res, win.feature_id)
    assert w.active is False and w.basis == Basis.OBSERVED and w.method == win.method
    assert len(w.history) == len(win.history) + 1 and w.history[-1].reason == "rejected"
    assert w.feature_id not in {o.feature_id for f in res.facades for o in f.openings}


def test_invalid_manual_geometry_is_dropped(front, store, reg):
    with pytest.raises(ValueError):
        DetectedFeature(feature_id="x", image_id=front.image_id, feature_type=FeatureType.FACADE,
                        bbox=(float("nan"), 250, 800, 650))
    with pytest.raises(ValueError):
        DetectedFeature(feature_id="x", image_id=front.image_id, feature_type=FeatureType.EAVES_LINE,
                        line=(0, float("inf"), 10, 10))
    nan_fac = DetectedFeature.model_construct(
        feature_id="m_nan", image_id=front.image_id, feature_type=FeatureType.FACADE, bbox=(float("nan"), 250, 800, 650),
        polygon=None, line=None, basis=Basis.OBSERVED, method="unknown", method_version="0", confidence=None,
        pixel_uncertainty=3.0, attributes={"block": "nanblock"}, evidence="", active=True, history=[], label="")
    huge = feat(front, "m_huge", "facade", bbox=(-1e9, -1e9, 1e9, 1e9), attributes={"block": "hugeblock"})
    res = analyse_images([front], store_dir=store, registry=reg, manual_features={front.image_id: [nan_fac, huge]})
    assert not any(f.block_hint in ("nanblock", "hugeblock") for f in res.facades)
    assert any("m_nan" in w and "m_huge" in w and "invalid" in w for w in res.warnings)
    assert sorted(f.block_hint for f in res.facades) == ["garage", "main"]


# =============================================================================
# VIS-5: VLM output is a cross-check only
# =============================================================================
def _vlm_client(payload):
    text = json.dumps(payload)

    class Messages:
        @staticmethod
        def create(**kw):
            return SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5",
                                   content=[SimpleNamespace(type="text", text=text)])

    return SimpleNamespace(beta=SimpleNamespace(messages=Messages()))


_VLM = {"roof_form": "gable", "has_garage": True, "has_balcony": None, "has_extension": None,
        "likely_external_finishes": [], "window_count_visible": 6, "door_count_visible": 2,
        "image_appears_ai_generated": False, "geometry_inconsistencies": [], "caveats": []}


def test_vlm_out_of_range_storeys_discarded():
    ext = parse_vlm_json(json.dumps(dict(_VLM, storeys=99)))
    assert ext.storeys is None and any("99" in c and "discarded" in c for c in ext.caveats)


@pytest.mark.parametrize("storeys", [3, 99])
def test_vlm_never_changes_measurements_or_hypotheses(front, store, front_base, storeys):
    reg = default_registry(enable_optional=False, enable_vlm=True, vlm_client=_vlm_client(dict(_VLM, storeys=storeys)))
    res = analyse_images([front], store_dir=store, registry=reg)
    a, b = facade_of(front_base), facade_of(res)
    assert (b.storeys.value, b.storeys.low, b.storeys.high, b.storeys.distribution) == \
        (a.storeys.value, a.storeys.low, a.storeys.high, a.storeys.distribution)
    ref = lambda r: ReferenceMeasurement(image_id=front.image_id, feature_id=main_facade_feature_id(r, front.image_id),
                                         real_length=9.6, tolerance=0.02)  # noqa: E731
    ha = generate_geometry_hypotheses(front_base, calibrate_scale(front_base, ref(front_base)))[0]
    hb = generate_geometry_hypotheses(res, calibrate_scale(res, ref(res)))[0]
    for x, y in zip(ha.blocks, hb.blocks):
        for name in ("width", "depth", "storeys", "floor_to_floor"):
            tx, ty = getattr(x, name), getattr(y, name)
            assert (tx.value, tx.low, tx.high, tx.basis) == (ty.value, ty.low, ty.high, ty.basis)


def test_floor_to_floor_range_at_nominal_storeys_and_plausible(front_base, front):
    # a facade storey range 2-10 (as an untrusted cross-check once produced) must not reach the floor-to-floor
    fo = facade_of(front_base)
    wide = fo.model_copy(update={"storeys": fo.storeys.model_copy(update={"low": 2.0, "high": 10.0})})
    an = front_base.model_copy(update={"facades": [wide if f is fo else f for f in front_base.facades]})
    ref = ReferenceMeasurement(image_id=front.image_id, feature_id=main_facade_feature_id(an, front.image_id),
                               real_length=9.6, tolerance=0.02)
    main = generate_geometry_hypotheses(an, calibrate_scale(an, ref))[0].blocks[0]
    ftf = main.floor_to_floor
    assert FTF_PLAUSIBLE[0] <= ftf.low < ftf.value < ftf.high <= FTF_PLAUSIBLE[1]
    assert ftf.low > 2.5  # computed at the nominal 2 storeys, not plate / 10


# =============================================================================
# VIS-6: a reference follows the user annotation that superseded its feature
# =============================================================================
def test_superseded_reference_retargets_to_annotation(front, store, reg, front_base):
    fid = main_facade_feature_id(front_base, front.image_id)
    x0, y0, x1, y1 = feature(front_base, fid).bbox
    ann = feat(front, "usr:corrected", "facade", bbox=(x0, y0, x1 - 30, y1), attributes={"block": "main"})
    res = analyse_images([front], store_dir=store, registry=reg, manual_features={front.image_id: [ann]})
    assert feature(res, fid).active is False
    ref = ReferenceMeasurement(image_id=front.image_id, feature_id=fid, real_length=9.6, tolerance=0.02)
    rr = resolve_reference(res, ref)
    assert rr.pixels == pytest.approx(x1 - 30 - x0) and rr.facade_block_hint == "main"
    cal = calibrate_scale(res, ref)
    assert any("superseded by user annotation usr:corrected" in n for n in cal.notes)
    main = generate_geometry_hypotheses(res, cal)[0].blocks[0]
    assert main.width.value == pytest.approx(9.6) and main.width.basis == Basis.USER_CONFIRMED


def test_reference_on_rejected_feature_is_refused(front, store, reg, front_base):
    fid = main_facade_feature_id(front_base, front.image_id)
    det = feature(front_base, fid)
    rec = EditRecord(actor="user", target=fid, field="active", old_value=True, new_value=False, reason="rejected")
    rej = det.model_copy(update={"active": False, "history": [rec]}, deep=True)
    res = analyse_images([front], store_dir=store, registry=reg, manual_features={front.image_id: [rej]})
    with pytest.raises(ValueError, match="no longer in use"):
        calibrate_scale(res, ReferenceMeasurement(image_id=front.image_id, feature_id=fid, real_length=9.6))


# =============================================================================
# Concept references: VIS-8, VIS-9, LOW-2, SPEC-1
# =============================================================================
@pytest.fixture(scope="module")
def with_concept(front, store, reg):
    concept = ingest_path(CONCEPT_IMAGE, kind=ImageKind.AI_CONCEPT, view=ViewDirection.FRONT, store_dir=store)
    return concept, analyse_images([front, concept], store_dir=store, registry=reg)


def test_concept_features_are_capped_at_inferred(with_concept, front):
    concept, res = with_concept
    feats = next(a for a in res.analyses if a.image_id == concept.image_id).features
    assert feats and all(f.basis == Basis.INFERRED for f in feats)
    assert all(any(h.reason == CONCEPT_CAP_REASON for h in f.history) for f in feats if f.feature_type != "other")
    assert res.concept_image_ids == [concept.image_id] and res.is_concept_image(concept.image_id)
    assert any(f.basis == Basis.OBSERVED for a in res.analyses if a.image_id == front.image_id for f in a.features)


def test_concept_finishes_not_on_the_twin(with_concept, front):
    concept, res = with_concept
    finishes = visual_finishes_from_analysis(res)
    ids = {fid for vf in finishes for fid in vf.feature_ids}
    assert finishes and all(i.startswith(front.image_id) for i in ids)
    assert not any("cladding" in vf.appearance or "black-framed" in vf.appearance for vf in finishes)


def test_reference_on_concept_does_not_make_it_the_geometry_source(with_concept, front):
    concept, res = with_concept
    assert res.primary_image_id == front.image_id
    cfid = next(f.feature_ids[0] for f in res.facades if f.image_id == concept.image_id and f.block_hint == "main")
    cal = calibrate_scale(res, ReferenceMeasurement(image_id=concept.image_id, feature_id=cfid, real_length=9.6,
                                                    tolerance=0.02))
    assert cal.image_id == concept.image_id
    hyp = generate_geometry_hypotheses(res, cal)[0]
    assert not any((o.feature_id or "").startswith(concept.image_id) for o in hyp.openings)
    assert not any(e.startswith(concept.image_id) for e in hyp.evidence_ids if e.startswith("img_"))
    assert any(n.startswith("Warning: the reference measurement is on the concept reference") for n in hyp.notes)
    assert hyp.blocks[0].width.basis != Basis.USER_CONFIRMED
    assert hyp.calibration_method == "prior_cues"  # the concept's calibration does not reach the front image


def test_concept_side_view_is_not_depth_evidence(front, store, reg):
    left = ingest_path(LEFT_IMAGE, kind=ImageKind.SKETCH, view=ViewDirection.LEFT, store_dir=store)
    res = analyse_images([front, left], store_dir=store, registry=reg)
    linked = res.multiview.linked_measurements if res.multiview is not None else {}
    assert "main.depth_front_px_equiv" not in linked and "main.pitch_side_view_deg" not in linked
    assert any(u.startswith("Plan depth of block 'main'") for u in res.unknowns)
    assert any("not scale-linked" in w for w in res.warnings)
    # the same image as a measured elevation is linked
    left_real = ingest_path(LEFT_IMAGE, kind=ImageKind.ELEVATION_DRAWING, view=ViewDirection.LEFT, store_dir=store)
    real = analyse_images([front, left_real], store_dir=store, registry=reg)
    assert "main.depth_front_px_equiv" in real.multiview.linked_measurements


# =============================================================================
# VIS-11 / UI-10: roof annotations
# =============================================================================
def _cottage(store, reg, roof_attrs, facade_attrs=None, extra=()):
    n_roof = -1 if roof_attrs is None else len(roof_attrs)
    img = blank(store, 1000, 800, f"cottage_{n_roof}_{len(facade_attrs or {})}_{len(extra)}.png",
                colour=(210, 200 - n_roof, 200 + len(extra)))
    rows = [feat(img, "c_fac", "facade", bbox=(300, 250, 900, 700), attributes={"block": "main", **(facade_attrs or {})}),
            feat(img, "c_gnd", "ground_line", line=(300, 700, 900, 700)),
            feat(img, "c_eav", "eaves_line", line=(300, 550, 900, 550)),
            feat(img, "c_door", "door", bbox=(560, 490, 650, 700)), *[e(img) for e in extra]]
    if roof_attrs is not None:
        rows.append(feat(img, "c_roof", "roof", bbox=(300, 250, 900, 550), attributes={"block": "main", **roof_attrs}))
    res = analyse_images([img], store_dir=store, registry=reg, manual_features={img.image_id: rows})
    return img, res


def test_front_gable_box_gives_user_confirmed_pitch(store, reg):
    img, res = _cottage(store, reg, {"roof_form": "gable", "gable_visible": True})
    fo = facade_of(res)
    assert fo.apparent_pitch_deg.value == pytest.approx(45.0, abs=0.01)
    assert fo.apparent_pitch_deg.basis == Basis.USER_CONFIRMED
    assert fo.ridge_axis_hint == "perpendicular_to_view"
    hyp = generate_geometry_hypotheses(res, calibrate_scale(res, ReferenceMeasurement(image_id=img.image_id,
                                                                                      real_length=6.0)))[0]
    roof = hyp.blocks[0].roof
    assert roof.ridge_axis == "y" and roof.pitch_deg.value == pytest.approx(45.0, abs=0.01)


def test_ridge_attribute_sets_orientation(store, reg):
    _, res = _cottage(store, reg, {"roof_form": "gable", "ridge": "perpendicular"})
    fo = facade_of(res)
    assert fo.ridge_axis_hint == "perpendicular_to_view" and fo.apparent_pitch_deg is None


def test_roof_form_on_facade_annotation_is_used(store, reg):
    _, res = _cottage(store, reg, None, {"roof_form": "hip"},
                      extra=[lambda img: feat(img, "c_win", "window", bbox=(350, 600, 450, 660),
                                              attributes={"roof_form": "flat"})])
    fo = facade_of(res)
    assert fo.roof_form == "hip" and fo.roof_form_basis == Basis.USER_CONFIRMED
    assert any("Roof form on window c_win is ignored" in w for w in res.warnings)


# =============================================================================
# SPEC-6: observed but unmodelled elements
# =============================================================================
def test_chimney_and_garage_box_are_reported(front, store, reg):
    chim = feat(front, "m_chim", "chimney", bbox=(400, 250, 440, 330), attributes={"block": "main"})
    bal = feat(front, "m_bal", "balcony", bbox=(500, 520, 700, 560), attributes={"block": "main"})
    gar = feat(front, "m_gar", "garage", bbox=(1420, 640, 1590, 900), attributes={"block": "carport"})
    res = analyse_images([front], store_dir=store, registry=reg, manual_features={front.image_id: [chim, bal, gar]})
    assert any("chimney m_chim observed - not modelled" in w for w in res.warnings)
    assert any("balcony m_bal" in u for u in res.unknowns)
    assert len(res.unmodelled_features) == 3
    assert any("garage m_gar" in u and "facade with block 'carport'" in u for u in res.unmodelled_features)
    ref = ReferenceMeasurement(image_id=front.image_id, feature_id=main_facade_feature_id(res, front.image_id),
                               real_length=9.6, tolerance=0.02)
    hyp = generate_geometry_hypotheses(res, calibrate_scale(res, ref))[0]
    assert hyp.unmodelled_elements == res.unmodelled_features
    twin = build_parametric_twin(hyp, selection=default_selection(default_library()))
    assert twin.unmodelled_elements == res.unmodelled_features
    # a garage box on the modelled garage (same block name or overlapping its facade box) is not reported
    gfac = next(f for f in res.analyses[0].features if f.feature_type == FeatureType.FACADE
                and f.attributes.get("block") == "garage")
    covered = feat(front, "m_gar2", "garage", bbox=gfac.bbox)
    res2 = analyse_images([front], store_dir=store, registry=reg, manual_features={front.image_id: [covered]})
    assert res2.unmodelled_features == []


# =============================================================================
# SPEC-3: the calibration label follows the scale actually in force
# =============================================================================
def _plan_image(store, name, colour=(255, 255, 254)):
    return blank(store, 1000, 800, name, kind=ImageKind.FLOOR_PLAN, view=ViewDirection.PLAN, colour=colour)


def test_reference_on_unlinked_plan_is_labelled_prior_cues(front, store, reg):
    plan = _plan_image(store, "plan_nolink.png", colour=(250, 251, 252))
    dim = feat(plan, "p_dim", "dimension", line=(100, 650, 580, 650))
    res = analyse_images([front, plan], store_dir=store, registry=reg, manual_features={plan.image_id: [dim]})
    cal = calibrate_scale(res, ReferenceMeasurement(image_id=plan.image_id, feature_id="p_dim", real_length=9.6))
    assert cal.method == "reference_measurement" and cal.image_id == plan.image_id
    hyp = generate_geometry_hypotheses(res, cal)[0]
    assert hyp.calibration_method == "prior_cues"
    lib = default_library()
    twin = build_parametric_twin(hyp, selection=default_selection(lib))
    assert twin.calibration_method == "prior_cues"
    boq = calculate_quantities(twin, lib)
    refs = {t.ref for ln in boq.lines for t in ln.trace if t.kind == "calibration"}
    assert refs and all("prior_cues" in r for r in refs)


# =============================================================================
# Floor-plan contract: outline + dimension -> width / depth -> fewer hypotheses (end to end)
# =============================================================================
PLAN_PPM = 50.0


def _plan_features(plan, *, extension=False, depth_dimension=True):
    s = PLAN_PPM
    fs = [feat(plan, "pl_main", "building_outline", bbox=(100, 200, 100 + 9.6 * s, 200 + 8.4 * s),
               attributes={"block": "main"}),
          feat(plan, "pl_garage", "building_outline", bbox=(100 + 9.6 * s, 200 + 2.4 * s, 100 + 12.8 * s, 620),
               attributes={"block": "garage"}),
          feat(plan, "pl_w", "dimension", line=(100, 660, 100 + 9.6 * s, 660),
               attributes={"length_m": 9.6, "axis": "width", "block": "main"})]
    if depth_dimension:
        fs.append(feat(plan, "pl_d", "dimension", line=(60, 200, 60, 200 + 8.4 * s),
                       attributes={"length_m": 8.4, "axis": "depth", "block": "main"}))
    if extension:
        fs.append(feat(plan, "pl_ext", "building_outline", bbox=(100, 200 - 3.6 * s, 100 + 4.8 * s, 200),
                       attributes={"block": "rear_ext"}))
    return fs


@pytest.mark.parametrize("extension", [False, True])
def test_dimensioned_floor_plan_end_to_end(front, store, reg, extension):
    plan = _plan_image(store, f"plan_{extension}.png", colour=(255, 254, 250 + int(extension)))
    res = analyse_images([front, plan], store_dir=store, registry=reg,
                         manual_features={plan.image_id: _plan_features(plan, extension=extension)})
    assert not any(u.startswith("Plan depth of block 'main'") for u in res.unknowns)
    assert not any(u.startswith("Plan depth of block 'garage'") for u in res.unknowns)
    ev = plan_evidence(res)
    assert ev is not None and ev.scale.value == pytest.approx(1 / PLAN_PPM, rel=1e-3)
    assert ev.blocks["main"].depth.basis == Basis.USER_CONFIRMED  # the depth dimension itself
    assert ev.blocks["garage"].depth.value == pytest.approx(6.0, rel=1e-3)
    assert ev.blocks["garage"].depth.basis == Basis.INFERRED
    cal = calibrate_scale(res)
    assert cal.method == "dimensioned_plan" and cal.image_id == front.image_id
    assert cal.metres_per_pixel.value == pytest.approx(1 / 92.0, rel=0.01)
    hyps = generate_geometry_hypotheses(res, cal)
    assert [h.hypothesis_id for h in hyps] == (["H-B", "H-A"] if extension else ["H-A"])
    best = hyps[0]
    main = best.blocks[0]
    assert main.depth.value == pytest.approx(8.4) and main.depth.basis == Basis.USER_CONFIRMED
    assert main.width.value == pytest.approx(9.6) and main.width.basis == Basis.USER_CONFIRMED
    assert main.roof.pitch_deg.value == pytest.approx(35.0, abs=1.0)
    assert main.roof.pitch_deg.basis == Basis.INFERRED
    garage = next(b for b in best.blocks if b.block_id == "garage")
    assert garage.depth.value == pytest.approx(6.0, rel=1e-3) and garage.depth.basis == Basis.INFERRED
    if extension:
        ext = next(b for b in best.blocks if b.block_id == "rear_ext")
        assert (ext.width.value, ext.depth.value) == (pytest.approx(4.8), pytest.approx(3.6))
        assert (ext.origin_x.value, ext.origin_y.value) == (pytest.approx(0.0), pytest.approx(8.4))
        assert best.plausibility > hyps[1].plausibility
    lib = default_library()
    twin = build_parametric_twin(best, selection=default_selection(lib))
    boq = calculate_quantities(twin, lib)
    assert boq.lines and twin.calibration_method == "dimensioned_plan"


def test_plan_without_depth_dimension_gives_inferred_depth(front, store, reg):
    plan = _plan_image(store, "plan_nodepth.png", colour=(253, 254, 255))
    res = analyse_images([front, plan], store_dir=store, registry=reg,
                         manual_features={plan.image_id: _plan_features(plan, depth_dimension=False)})
    hyps = generate_geometry_hypotheses(res, calibrate_scale(res))
    assert [h.hypothesis_id for h in hyps] == ["H-A"]
    d = hyps[0].blocks[0].depth
    assert d.value == pytest.approx(8.4, rel=0.01) and d.basis == Basis.INFERRED and d.low < d.value < d.high


def test_inactive_plan_features_contribute_nothing(front, store, reg):
    plan = _plan_image(store, "plan_inactive.png", colour=(240, 250, 255))
    fs = [f.model_copy(update={"active": False}) for f in _plan_features(plan)]
    res = analyse_images([front, plan], store_dir=store, registry=reg, manual_features={plan.image_id: fs})
    assert plan_evidence(res) is None
    assert calibrate_scale(res).method == "prior_cues"
    assert len(generate_geometry_hypotheses(res, calibrate_scale(res))) == 3


# =============================================================================
# SPEC-10: oblique-view foreshortening bias
# =============================================================================
def _oblique_analysis(theta_deg: float, *, near_fp: bool) -> AnalysisResult:
    """Synthetic weak-perspective view of a 9.6 m frontage turned by theta (verticals unscaled)."""
    ppm, gy, x0 = 100.0, 900.0, 100.0
    c = math.cos(math.radians(theta_deg))
    w_px = 9.6 * ppm * c
    pxv = lambda v, s=2.0: TrackedValue(value=v, unit="px", basis=Basis.OBSERVED, low=v - 2 * s, high=v + 2 * s)  # noqa
    door = (x0 + 4.3 * ppm * c, gy - (0.15 + 2.1) * ppm, x0 + 5.3 * ppm * c, gy - 0.15 * ppm)
    obs = FacadeObservation(
        image_id="img_obl", view=ViewDirection.FRONT, block_hint="main",
        storeys=TrackedValue(value=2.0, unit="storeys", basis=Basis.INFERRED), width_px=pxv(w_px),
        eaves_height_px=pxv(5.55 * ppm), ridge_height_px=pxv(8.49 * ppm), ground_y_px=gy, left_x_px=x0,
        roof_form="gable", ridge_axis_hint="parallel_to_view",
        openings=[ObservedOpening(feature_id="o_door", kind="door", bbox_px=door, storey_index=0, block_hint="main")],
        feature_ids=["f_obl"])
    img = ImageAsset(image_id="img_obl", sha256="d" * 64, original_filename="oblique.jpg", media_type="image/jpeg",
                     width_px=1400, height_px=1000, size_bytes=1, kind=ImageKind.PHOTOGRAPH, view=ViewDirection.FRONT)
    persp = PerspectiveEstimate(method="test", facade_obliqueness_deg=theta_deg, is_near_fronto_parallel=near_fp,
                                foreshortening_uncertainty=0.02 + (1 - c))
    feats = [DetectedFeature(feature_id="o_door", image_id="img_obl", feature_type=FeatureType.DOOR, bbox=door,
                             pixel_uncertainty=1.0)]
    return AnalysisResult(images=[img], analyses=[ImageAnalysis(image_id="img_obl", features=feats, perspective=persp)],
                          facades=[obs], primary_image_id="img_obl")


def test_oblique_view_bias_is_corrected_for_vertical_cue_scale():
    an = _oblique_analysis(35.0, near_fp=False)
    cal = calibrate_scale(an)
    assert cal.method == "prior_cues"
    hyp = generate_geometry_hypotheses(an, cal)[0]
    w = hyp.blocks[0].width
    assert w.value == pytest.approx(9.6, rel=0.04)  # without the correction: 9.6 x cos 35 = 7.9 m
    assert w.low < 9.6 < w.high
    assert any(n.startswith("Oblique view: facade obliqueness 35.0 deg") for n in hyp.notes)
    flat = generate_geometry_hypotheses(_oblique_analysis(35.0, near_fp=True), cal)[0].blocks[0].width
    assert flat.value == pytest.approx(9.6 * math.cos(math.radians(35.0)), rel=0.04)


def test_oblique_view_heights_corrected_for_horizontal_reference():
    an = _oblique_analysis(35.0, near_fp=False)
    cal = calibrate_scale(an, ReferenceMeasurement(image_id="img_obl", real_length=9.6, tolerance=0.02))
    hyp = generate_geometry_hypotheses(an, cal)[0]
    main = hyp.blocks[0]
    assert main.width.value == pytest.approx(9.6) and main.width.basis == Basis.USER_CONFIRMED
    plate = main.ground_floor_level.value + main.storeys.value * main.floor_to_floor.value
    assert plate == pytest.approx(5.55, rel=0.03)  # without the correction: 5.55 / cos 35 = 6.8 m


# =============================================================================
# UI-6: storeys edits keep the wall plate on the observed eaves (or warn)
# =============================================================================
@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return build_demo_project(tmp_path_factory.mktemp("demo_r2"))


def test_demo_blocks_record_observed_eaves(demo):
    main = demo.twin.block("main")
    assert main.observed_eaves_m is not None and main.observed_eaves_m.value == pytest.approx(5.54, abs=0.05)
    assert plate_height(main) == pytest.approx(main.observed_eaves_m.value, abs=1e-6)
    assert coupling_warnings(demo.twin) == []


def test_implausible_storeys_edit_keeps_ftf_and_warns(demo):
    t = apply_twin_edit(demo.twin, TwinEdit(target_type="block", target_id="main", field="storeys", value=3))
    main = t.block("main")
    assert main.floor_to_floor.value == pytest.approx(demo.twin.block("main").floor_to_floor.value)
    assert any(r.field == "eaves_residual_m" and r.actor == "system:coupling" for r in t.edit_log)
    assert any("'main' wall plate" in w and "Warning" in w for w in coupling_warnings(t))


def test_storeys_edit_rederives_floor_to_floor(demo):
    twin = demo.twin.model_copy(deep=True)
    main = twin.block("main")
    main.observed_eaves_m = main.observed_eaves_m.model_copy(update={"value": 7.0, "low": 6.9, "high": 7.1})
    main.floor_to_floor = main.floor_to_floor.model_copy(update={"value": (7.0 - 0.15) / 2, "low": None,
                                                                 "high": None})
    t = apply_twin_edit(twin, TwinEdit(target_type="block", target_id="main", field="storeys", value=3))
    m = t.block("main")
    assert m.storeys.value == 3 and m.storeys.basis == Basis.USER_CONFIRMED
    assert m.floor_to_floor.value == pytest.approx((7.0 - 0.15) / 3)
    assert m.floor_to_floor.basis == Basis.ASSUMED  # weakest of eaves, assumed FFL and the count
    assert plate_height(m) == pytest.approx(7.0)
    assert [r.field for r in t.edit_log[-1:]] == ["floor_to_floor"] and t.edit_log[-1].actor == "system:coupling"
    assert not any("wall plate" in w for w in coupling_warnings(t))


# =============================================================================
# UI-7: H-B is never deeper than H-A and its assumed depth has a range
# =============================================================================
def _wide_house(store, reg, rise_px, name):
    img = blank(store, 2200, 900, name, colour=(200, 210, 200 + rise_px % 50))
    rows = [feat(img, "w_fac", "facade", bbox=(200, 340, 2000, 800), attributes={"block": "main"}),
            feat(img, "w_gnd", "ground_line", line=(200, 800, 2000, 800)),
            feat(img, "w_eav", "eaves_line", line=(200, 340, 2000, 340)),
            feat(img, "w_rdg", "ridge_line", line=(220, 340 - rise_px, 1980, 340 - rise_px)),
            feat(img, "w_door", "door", bbox=(900, 575, 1000, 785))]
    return img, analyse_images([img], store_dir=store, registry=reg, manual_features={img.image_id: rows})


@pytest.mark.parametrize("rise_px", [60, 250, 400])
def test_h_b_never_deeper_than_h_a(store, reg, rise_px):
    img, res = _wide_house(store, reg, rise_px, f"wide_{rise_px}.png")
    for cal in (calibrate_scale(res), calibrate_scale(res, ReferenceMeasurement(image_id=img.image_id,
                                                                                real_length=18.0))):
        hyps = {h.hypothesis_id: h for h in generate_geometry_hypotheses(res, cal)}
        a, b = hyps["H-A"].blocks[0], hyps["H-B"].blocks[0]
        assert b.depth.value <= a.depth.value + 1e-9
        assert b.depth.low is not None and b.depth.low < b.depth.high
        if b.depth.value < a.depth.value - 1e-6:
            assert hyps["H-B"].name.startswith("L-shaped: shallower") and "Shallower" in hyps["H-B"].description
        else:
            assert hyps["H-B"].name.startswith("Rectangular main + hidden")
            assert "Shallower" not in hyps["H-B"].description
        if "H-C" in hyps:
            assert hyps["H-C"].blocks[0].depth.value > a.depth.value


# =============================================================================
# Ingest: SEC-2 (MPO), LOW-3 (>8-bit decode memory), LOW-4 (stored path confinement)
# =============================================================================
def test_mpo_jpeg_is_accepted(tmp_path):
    first = Image.new("RGB", (400, 300), (200, 30, 30))
    buf = io.BytesIO()
    first.save(buf, "MPO", save_all=True, append_images=[Image.new("RGB", (160, 120), (0, 0, 255))])
    data = buf.getvalue()
    assert data[:2] == b"\xff\xd8" and Image.open(io.BytesIO(data)).format == "MPO"
    asset = ingest_image(data, "phone.jpg", store_dir=tmp_path)
    assert asset.media_type == "image/jpeg" and (asset.width_px, asset.height_px) == (400, 300)
    assert stored_image_path(asset, tmp_path).read_bytes() == data  # original bytes kept
    rgb = load_image_array(asset, tmp_path)
    assert rgb.shape == (300, 400, 3) and abs(int(rgb[10, 10, 0]) - 200) < 8


def test_16bit_decode_is_correct_and_bounded():
    a = np.zeros((2000, 2000), np.uint16)
    a[::3, ::2] = 65535
    a[1, 1] = 32768
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, "PNG")
    tracemalloc.start()
    try:
        rgb = decode_rgb(buf.getvalue())
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert rgb.dtype == np.uint8 and rgb.shape == (2000, 2000, 3)
    assert rgb[0, 0, 0] == 255 and rgb[1, 1, 0] == 127 and rgb[1, 0, 0] == 0
    # a float64 copy alone would be 32 MB; the old path peaked at ~23 bytes/pixel (~92 MB)
    assert peak < 10 * 2000 * 2000


def test_stored_path_outside_the_store_is_never_read(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (20, 10), (1, 2, 3)).save(buf, "PNG")
    store = tmp_path / "store"
    asset = ingest_image(buf.getvalue(), "a.png", store_dir=store)
    secret = tmp_path / "secret.txt"
    secret.write_text("not an image")
    crafted = asset.model_copy(update={"stored_path": str(secret)})
    with pytest.raises(FileNotFoundError):
        stored_image_path(crafted)
    with pytest.raises(FileNotFoundError):
        load_image_array(crafted, tmp_path / "elsewhere")
    # a content-addressed copy outside the configured store is ignored when a store is given
    other = tmp_path / "other"
    other.mkdir()
    copy = other / f"{asset.sha256}.png"
    copy.write_bytes(buf.getvalue())
    moved = asset.model_copy(update={"stored_path": str(copy)})
    assert stored_image_path(moved) == copy  # no store configured: the content-addressed name is accepted
    with pytest.raises(FileNotFoundError):
        stored_image_path(moved, tmp_path / "empty_store")
    assert load_image_array(asset, store).shape == (10, 20, 3)
    with pytest.raises(ImageRejected):  # right name, wrong content
        copy.write_bytes(b"\x89PNG" + b"0" * 20)
        load_image_array(moved)


# =============================================================================
# Round trips of the merge rules (stored analyses are re-fed as manual features by the UI)
# =============================================================================
def test_superseded_by_names_the_annotation(front, store, reg, front_base):
    from housebuilder_vision.vision.analysis import superseded_by

    fid = main_facade_feature_id(front_base, front.image_id)
    ann = feat(front, "usr:sup", "facade", bbox=feature(front_base, fid).bbox, attributes={"block": "main"})
    res = analyse_images([front], store_dir=store, registry=reg, manual_features={front.image_id: [ann]})
    assert superseded_by(feature(res, fid)) == "usr:sup" and superseded_by(feature(res, "usr:sup")) is None


def test_stored_concept_annotation_is_restored_to_user_confirmed(store, reg):
    img = blank(store, 1000, 700, "concept_rt.png", kind=ImageKind.AI_CONCEPT, colour=(201, 199, 197))
    rows = [feat(img, "k_fac", "facade", bbox=(200, 250, 800, 650), attributes={"block": "main"},
                 basis=Basis.USER_CONFIRMED),
            feat(img, "k_gnd", "ground_line", line=(200, 650, 800, 650), basis=Basis.USER_CONFIRMED),
            feat(img, "k_door", "door", bbox=(450, 520, 510, 650), attributes={"storey": 0}, basis=Basis.USER_CONFIRMED),
            feat(img, "k_w", "window", bbox=(260, 360, 360, 440), attributes={"storey": 1}, basis=Basis.USER_CONFIRMED)]
    first = analyse_images([img], store_dir=store, registry=reg, manual_features={img.image_id: rows})
    stored = [f for f in first.analyses[0].features if f.feature_id.startswith("k_")]
    assert all(f.basis == Basis.INFERRED for f in stored)  # capped on output
    again = analyse_images([img], store_dir=store, registry=reg, manual_features={img.image_id: stored})
    fo = facade_of(again)
    assert fo.storeys.value == 2 and {o.feature_id: o.storey_index for o in fo.openings} == {"k_door": 0, "k_w": 1}
    hist = feature(again, "k_w").history
    assert sum(1 for h in hist if h.reason == CONCEPT_CAP_REASON) == 1  # no accumulation over round trips
