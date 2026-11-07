"""Regression tests for the review fixes to twin edits, couplings and provenance (group A).

GEO-1  observed roof rise stored on the roof; editing depth / pitch / rise / roof shape re-derives the other
       value (system:coupling, weakest basis) unless it is user-confirmed or observed; residual reported.
GEO-2  a storey reduction is refused while observed / user openings sit on a removed storey.
GEO-3  reflow by attachment: a block hanging from an unmoved block is not dragged along.
GEO-4  a rear extension flush with the right corner follows width edits of its parent.
GEO-5  values that depend on the assumed FFL are ASSUMED; the hidden extension's storey height is ASSUMED.
GEO-6  opening assembly overrides are checked against the opening kind's element (with a library).
GEO-7  a user opening override is recorded as USER_CONFIRMED.
GEO-8  a tolerance entered on a FIXED value is sampled (UNIFORM).
GEO-13 pixel lengths between two endpoints carry sqrt(2) x the per-endpoint sigma.

Fixtures reuse the hand-built synthetic demo house of ``test_twin.py`` (92 px/m, no vision code).
"""

from __future__ import annotations

import math

import pytest

from housebuilder_vision.core.models import ReferenceMeasurement, RoofForm, Side, TwinEdit
from housebuilder_vision.core.provenance import Basis, Distribution, TrackedValue, assumed
from housebuilder_vision.geometry import compute_geometry_metrics
from housebuilder_vision.geometry.footprint import Rect
from housebuilder_vision.quantities import default_library
from housebuilder_vision.twin import build_parametric_twin, calibrate_scale, generate_geometry_hypotheses
from housebuilder_vision.twin.builder import (
    COUPLING_ACTOR,
    apply_twin_edit,
    attached_origin,
    block_coupling,
    coupling_warnings,
    footprint_attachments,
    roof_span_field,
)
from housebuilder_vision.twin.calibration import length_band, length_sigma, px_band
from test_twin import FTF, LX, MAIN_D, MAIN_W, PPM, RISE, frontage_ref, make_analysis, selection


# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture(scope="module")
def analysis():
    return make_analysis()


@pytest.fixture(scope="module")
def hyps(analysis):
    return {h.hypothesis_id: h for h in generate_geometry_hypotheses(analysis, calibrate_scale(analysis, frontage_ref()))}


@pytest.fixture
def twin_a(hyps):
    return build_parametric_twin(hyps["H-A"], selection=selection())


@pytest.fixture
def twin_b(hyps):
    return build_parametric_twin(hyps["H-B"], selection=selection())


def edit(twin, target_type, target_id, field, value, **kw):
    library = kw.pop("library", None)
    return apply_twin_edit(twin, TwinEdit(target_type=target_type, target_id=target_id, field=field, value=value,
                                          **kw), library=library)


def box(t, bid):
    b = t.block(bid)
    return (round(b.origin_x.value, 6), round(b.origin_y.value, 6), round(b.width.value, 6), round(b.depth.value, 6))


def rise_of(t, bid="main"):
    b = t.block(bid)
    span, f = roof_span_field(b)
    return getattr(b, span).value * math.tan(math.radians(b.roof.pitch_deg.value)) / f


def metrics(t):
    return compute_geometry_metrics(t, 0.30, 0.20)


# =============================================================================
# GEO-1 depth-pitch coupling
# =============================================================================
def test_hypotheses_store_the_observed_rise(hyps):
    for hid in ("H-A", "H-B"):
        m = next(b for b in hyps[hid].blocks if b.block_id == "main")
        r = m.roof.observed_rise_m
        assert r is not None and r.value == pytest.approx(RISE) and r.basis == Basis.INFERRED
        assert r.evidence_ids and r.low < r.value < r.high
        assert block_coupling(m).consistent  # the hypothesis roof reproduces the rise
    garage = next(b for b in hyps["H-A"].blocks if b.block_id == "garage")
    assert garage.roof.observed_rise_m is None  # pitch observed on its gable; no rise band


def test_pitch_edit_rederives_depth_from_the_observed_rise(twin_a):
    t = edit(twin_a, "roof", "main", "pitch_deg", 30.0, tolerance=1.0)
    m = t.block("main")
    expected = 2 * RISE / math.tan(math.radians(30.0))
    assert m.depth.value == pytest.approx(expected)  # 10.19 m, not the stale 8.40 m
    assert m.depth.basis == Basis.INFERRED  # weakest(rise INFERRED, pitch USER_CONFIRMED)
    assert m.depth.low < m.depth.value < m.depth.high
    assert m.roof.pitch_deg.basis == Basis.USER_CONFIRMED
    assert rise_of(t) == pytest.approx(RISE)
    user, sysrec = t.edit_log[-2], t.edit_log[-1]
    assert (user.actor, user.field) == ("user", "pitch_deg")
    assert (sysrec.actor, sysrec.target, sysrec.field) == (COUPLING_ACTOR, "block:main", "depth")
    assert sysrec.new_basis == Basis.INFERRED and m.depth.history[-1].actor == COUPLING_ACTOR
    assert t.version == twin_a.version + 1
    # the garage stays attached (right of main, front flush); hidden openings follow the new depth
    assert box(t, "garage")[:2] == (pytest.approx(MAIN_W), 0.0)
    for o in t.openings:
        if o.hidden_side_rule and o.block_id == "main" and o.side in (Side.LEFT, Side.RIGHT):
            assert o.offset_m.value + o.width_m.value <= expected + 1e-9
    assert not coupling_warnings(t)


def test_depth_edit_rederives_pitch_from_the_observed_rise(twin_a):
    t = edit(twin_a, "block", "main", "depth", 9.5, tolerance=0.05)
    p = t.block("main").roof.pitch_deg
    assert p.value == pytest.approx(math.degrees(math.atan(2 * RISE / 9.5)))  # 31.8 deg, not the stale 35
    assert p.basis == Basis.INFERRED and p.low < p.value < p.high
    assert p.source.startswith("depth-pitch coupling")
    assert t.edit_log[-1].actor == COUPLING_ACTOR and t.edit_log[-1].field == "pitch_deg"
    assert rise_of(t) == pytest.approx(RISE)
    # the width of a gable with ridge x is not its span: no coupling record
    t2 = edit(twin_a, "block", "main", "width", 10.0)
    assert t2.block("main").roof.pitch_deg.value == pytest.approx(35.0)
    assert all(r.actor != COUPLING_ACTOR for r in t2.edit_log)


def test_both_values_fixed_are_kept_and_the_residual_reported(twin_a):
    t = edit(twin_a, "block", "main", "depth", 9.5)
    t = edit(t, "roof", "main", "pitch_deg", 35.0)
    m = t.block("main")
    assert m.depth.value == 9.5 and m.roof.pitch_deg.value == 35.0
    rec = t.edit_log[-1]
    implied = 9.5 * math.tan(math.radians(35.0)) / 2
    assert (rec.actor, rec.field) == (COUPLING_ACTOR, "rise_residual_m")
    assert rec.new_value == pytest.approx(implied - RISE, abs=1e-4)
    assert "both values kept" in rec.reason
    warn = coupling_warnings(t)
    assert len(warn) == 1 and warn[0].startswith("Warning: 'main'") and "outside the observed range" in warn[0]


def test_observed_rise_edit_and_clear(twin_a):
    t = edit(twin_a, "roof", "main", "observed_rise_m", 3.2)
    m = t.block("main")
    assert m.roof.observed_rise_m.basis == Basis.USER_CONFIRMED
    assert m.depth.value == pytest.approx(MAIN_D)  # the pitch (an assumption) is re-derived, the footprint kept
    assert m.roof.pitch_deg.value == pytest.approx(math.degrees(math.atan(2 * 3.2 / MAIN_D)))
    t2 = edit(t, "roof", "main", "observed_rise_m", None)
    assert t2.block("main").roof.observed_rise_m is None and block_coupling(t2.block("main")) is None
    t3 = edit(t2, "block", "main", "depth", 9.0)
    assert t3.block("main").roof.pitch_deg.value == pytest.approx(m.roof.pitch_deg.value)  # decoupled
    with pytest.raises(ValueError):
        edit(twin_a, "roof", "main", "observed_rise_m", -1.0)


def test_roof_shape_edits_rederive_the_pitch(twin_a):
    t = edit(twin_a, "roof", "main", "ridge_axis", "y")  # the front view now shows a gable over the width
    assert t.block("main").roof.pitch_deg.value == pytest.approx(math.degrees(math.atan(2 * RISE / MAIN_W)))
    t = edit(twin_a, "roof", "main", "form", "monopitch")
    t = edit(t, "roof", "main", "high_side", "rear")  # span = depth, rise = span x tan(pitch)
    assert t.block("main").roof.pitch_deg.value == pytest.approx(math.degrees(math.atan(RISE / MAIN_D)))
    t2 = edit(t, "roof", "main", "pitch_deg", 25.0)
    assert t2.block("main").depth.value == pytest.approx(RISE / math.tan(math.radians(25.0)))


def test_roof_span_field():
    def blk(t, **roof):
        b = t.block("main")
        return b.model_copy(update={"roof": b.roof.model_copy(update=roof)})

    hyps = generate_geometry_hypotheses(make_analysis(), calibrate_scale(make_analysis(), frontage_ref()))
    t = build_parametric_twin(hyps[0], selection=selection())
    assert roof_span_field(blk(t, form=RoofForm.GABLE, ridge_axis="x")) == ("depth", 2.0)
    assert roof_span_field(blk(t, form=RoofForm.GABLE, ridge_axis="y")) == ("width", 2.0)
    assert roof_span_field(blk(t, form=RoofForm.HIP)) == ("depth", 2.0)  # 8.4 < 9.6
    assert roof_span_field(blk(t, form=RoofForm.MONOPITCH, high_side=Side.FRONT)) == ("depth", 1.0)
    assert roof_span_field(blk(t, form=RoofForm.MONOPITCH, high_side=Side.LEFT)) == ("width", 1.0)
    assert roof_span_field(blk(t, form=RoofForm.FLAT)) is None


def test_underivable_values_are_not_forced(twin_a):
    # hip: a shallow pitch would need a span longer than the other side -> both kept, residual logged
    t = edit(twin_a, "roof", "main", "form", "hip")
    assert block_coupling(t.block("main")).consistent
    t2 = edit(t, "roof", "main", "pitch_deg", 20.0)
    assert t2.block("main").depth.value == pytest.approx(MAIN_D)
    assert t2.edit_log[-1].field == "rise_residual_m" and "exceed" in t2.edit_log[-1].reason
    # a pitch above 75 deg is not derived from a tiny span
    t3 = edit(twin_a, "block", "main", "depth", 1.0)
    assert t3.block("main").roof.pitch_deg.value == pytest.approx(35.0)
    assert t3.edit_log[-1].field == "rise_residual_m" and "outside 0-75" in t3.edit_log[-1].reason


# =============================================================================
# GEO-2 storeys
# =============================================================================
def test_storey_reduction_refused_while_openings_on_removed_storeys(twin_a):
    with pytest.raises(ValueError) as exc:
        edit(twin_a, "block", "main", "storeys", 1)
    msg = str(exc.value)
    assert all(f"obs:o0{i}" in msg for i in (4, 5, 6)) and "obs:o01" not in msg
    t = twin_a
    for oid in ("obs:o04", "obs:o05", "obs:o06"):
        t = edit(t, "opening", oid, "delete", None)
    t = edit(t, "block", "main", "storeys", 1)
    assert t.block("main").storeys.value == 1
    assert all(o.storey == 0 for o in t.openings if o.block_id == "main")  # rule openings regenerated
    assert any(o.hidden_side_rule and o.block_id == "main" for o in t.openings)
    assert not any("storey" in w for w in metrics(t).warnings)


# =============================================================================
# GEO-3 / GEO-4 attachment-aware reflow
# =============================================================================
def _rear_right(twin_b):
    return edit(twin_b, "block", "rear_ext", "origin_x", MAIN_W - 4.8)


def test_attachment_tree_and_placement_round_trip(twin_b):
    rects = [(b.block_id, b.origin_x.value, b.origin_y.value, b.width.value, b.depth.value) for b in twin_b.blocks]
    atts, detached = footprint_attachments([Rect(i, x, y, x + w, y + d) for i, x, y, w, d in rects], 0)
    by_child = {rects[a.child][0]: (rects[a.parent][0], a.relation, a.align) for a in atts}
    assert by_child == {"garage": ("main", "right_of", "front"), "rear_ext": ("main", "behind", "left")}
    assert not detached
    for a in atts:
        _, x, y, w, d = rects[a.child]
        assert attached_origin(a, rects[a.parent][1:], w, d) == (pytest.approx(x), pytest.approx(y))


def test_rear_right_extension_follows_width_edits(twin_b):
    t = _rear_right(twin_b)
    for w in (8.0, 11.0):
        t2 = edit(t, "block", "main", "width", w)
        assert box(t2, "rear_ext")[0] == pytest.approx(w - 4.8)  # still flush with the rear-right corner
        assert box(t2, "garage")[0] == pytest.approx(w)
        front = [p for p in metrics(t2).pieces if p.block_id == "rear_ext" and p.side == Side.FRONT]
        assert [p.exposure for p in front] == ["shared"] and front[0].length_m == pytest.approx(4.8)
    # a rear-left extension keeps its corner too
    t3 = edit(twin_b, "block", "main", "width", 8.0)
    assert box(t3, "rear_ext")[0] == pytest.approx(0.0)


def test_block_hanging_from_an_unmoved_block_is_not_dragged(twin_b):
    t = edit(_rear_right(twin_b), "block", "main", "depth", 5.5)  # the 6 m garage now also touches rear_ext
    assert box(t, "rear_ext")[1] == pytest.approx(5.5)
    for w in (4.0, 5.5):
        t2 = edit(t, "block", "rear_ext", "width", w)
        assert box(t2, "garage")[0] == pytest.approx(MAIN_W)  # garage hangs from main: not moved
        assert box(t2, "rear_ext")[0] == pytest.approx(MAIN_W - w)  # extension keeps its right-corner alignment
        right = [p for p in metrics(t2).pieces if p.block_id == "main" and p.side == Side.RIGHT]
        assert [(p.exposure, p.neighbour_block_id) for p in right] == [("shared", "garage")]


def test_reflow_refuses_overlap_and_detachment(twin_b):
    t = edit(twin_b, "block", "rear_ext", "width", 12.0)  # rear-left, grows rightwards behind the garage
    with pytest.raises(ValueError, match="overlap"):
        edit(t, "block", "garage", "depth", 9.0)
    t2 = edit(twin_b, "block", "rear_ext", "origin_x", 2.0)  # offset behind main
    with pytest.raises(ValueError, match="detach 'rear_ext' from 'main'"):
        edit(t2, "block", "main", "width", 1.9)
    assert box(twin_b, "rear_ext")[0] == 0.0  # inputs never mutated


# =============================================================================
# GEO-5 provenance of FFL-dependent values
# =============================================================================
def test_ffl_dependent_values_are_assumed(hyps):
    for h in hyps.values():
        m = next(b for b in h.blocks if b.block_id == "main")
        assert m.ground_floor_level.basis == Basis.ASSUMED
        assert m.floor_to_floor.basis == Basis.ASSUMED and m.floor_to_floor.value == pytest.approx(FTF)
        assert "assumed FFL" in m.floor_to_floor.note and "inferred" in m.floor_to_floor.note
        for o in h.openings:
            assert o.sill_m.basis == Basis.ASSUMED, o.opening_id
            assert o.width_m.basis == Basis.INFERRED  # the scaled sizes stay inferred
    ext = next(b for b in hyps["H-B"].blocks if b.block_id == "rear_ext")
    for tv in (ext.floor_to_floor, ext.ground_floor_level):
        assert tv.basis == Basis.ASSUMED and tv.evidence_ids == []
    assert "main block" in ext.floor_to_floor.note


# =============================================================================
# GEO-6 / GEO-7 opening assembly overrides
# =============================================================================
def test_opening_assembly_override_checked_against_the_element(twin_a):
    lib = default_library()
    with pytest.raises(ValueError, match="external_door"):
        edit(twin_a, "opening", "obs:o02", "assembly_id", "win_upvc_dg", library=lib)  # door given a window
    with pytest.raises(ValueError, match="not in the library"):
        edit(twin_a, "opening", "obs:o01", "assembly_id", "no_such_assembly", library=lib)
    spec = {"block_id": "main", "side": "rear", "kind": "door", "width_m": 1.0, "height_m": 2.1,
            "assembly_id": "win_upvc_dg"}
    with pytest.raises(ValueError):
        edit(twin_a, "opening", None, "add", spec, library=lib)
    t = edit(twin_a, "opening", "obs:o02", "assembly_id", "door_composite", library=lib)
    assert next(o for o in t.openings if o.opening_id == "obs:o02").assembly_id == "door_composite"


def test_user_opening_override_is_user_confirmed(twin_a):
    t = edit(twin_a, "opening", "obs:o01", "assembly_id", "win_alu_tg")
    assert t.assemblies.basis["opening/obs:o01"] == Basis.USER_CONFIRMED
    assert t.edit_log[-1].old_basis == Basis.ASSUMED
    t2 = edit(t, "opening", "obs:o01", "assembly_id", None)
    assert "opening/obs:o01" not in t2.assemblies.basis and t2.edit_log[-1].old_basis == Basis.USER_CONFIRMED
    t3 = edit(twin_a, "opening", None, "add", {"block_id": "main", "side": "rear", "kind": "window", "width_m": 1.0,
                                               "height_m": 1.0, "opening_id": "user:x", "assembly_id": "win_alu_tg"})
    assert t3.assemblies.basis["opening/user:x"] == Basis.USER_CONFIRMED
    t4 = edit(t3, "opening", "user:x", "delete", None)
    assert "opening/user:x" not in t4.assemblies.basis


def test_kind_change_to_another_element_clears_the_override(twin_a):
    t = edit(twin_a, "opening", "obs:o01", "assembly_id", "win_alu_tg")
    t2 = edit(t, "opening", "obs:o01", "kind", "patio_door")  # still a window-element opening: kept
    assert next(o for o in t2.openings if o.opening_id == "obs:o01").assembly_id == "win_alu_tg"
    t3 = edit(t2, "opening", "obs:o01", "kind", "door")
    o = next(o for o in t3.openings if o.opening_id == "obs:o01")
    assert o.assembly_id is None and "opening/obs:o01" not in t3.assemblies.basis
    rec = t3.edit_log[-1]
    assert (rec.actor, rec.field, rec.old_value, rec.new_value) == ("system:assembly-check", "assembly_id",
                                                                    "win_alu_tg", None)


# =============================================================================
# GEO-8 edit tolerances on FIXED values
# =============================================================================
def test_tolerance_on_a_fixed_value_is_sampled(twin_a):
    fixed = TrackedValue(value=1.2, unit="m", basis=Basis.ASSUMED, distribution=Distribution.FIXED)
    e = fixed.edited(1.5, tolerance=0.1)
    assert (e.low, e.high, e.distribution, e.is_uncertain) == (pytest.approx(1.4), pytest.approx(1.6),
                                                               Distribution.UNIFORM, True)
    assert fixed.edited(1.5, low=1.45, high=1.6).distribution == Distribution.UNIFORM
    assert fixed.edited(1.5).distribution == Distribution.FIXED
    tri = assumed(1.0, "m", low=0.8, high=1.2)
    assert tri.edited(1.1, tolerance=0.05).distribution == Distribution.TRIANGULAR  # shape kept
    rid = next(o.opening_id for o in twin_a.openings if o.hidden_side_rule)
    t = edit(twin_a, "opening", rid, "width_m", 1.5, tolerance=0.1)
    w = next(o for o in t.openings if o.opening_id == rid).width_m
    assert w.distribution == Distribution.UNIFORM and w.is_uncertain


# =============================================================================
# GEO-13 pixel error of a length between two endpoints
# =============================================================================
def test_endpoint_lengths_carry_sqrt2_sigma(analysis):
    assert length_sigma(3.0) == pytest.approx(3.0 * math.sqrt(2))
    assert length_band(3.0) == pytest.approx(6.0 * math.sqrt(2)) == px_band(None, 3.0)
    px = MAIN_W * PPM
    ref = ReferenceMeasurement(image_id=analysis.images[0].image_id, p0=(LX, 950.0), p1=(LX + px, 950.0),
                               real_length=MAIN_W, tolerance=0.02)
    s = calibrate_scale(analysis, ref).metres_per_pixel
    hw = math.sqrt((2 * math.sqrt(2) * 3.0 / px) ** 2 + (0.02 / MAIN_W) ** 2 + 0.02 ** 2)  # default sigma 3 px
    assert s.low == pytest.approx(s.value * (1 - hw)) and s.high == pytest.approx(s.value * (1 + hw))
    door = next(c for c in calibrate_scale(analysis).cues if c.name == "door leaf height")
    assert f"+/- {length_band(1.5):.1f} px" in door.implied_m_per_px.note  # door bbox: sigma 1.5 px per edge
