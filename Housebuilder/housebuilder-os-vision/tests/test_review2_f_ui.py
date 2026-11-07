"""Review round 2, group F (UI side): the shared annotation contract (stable ids, edit history, opening /
roof / floor-plan attributes), calibration safety, twin status, header flags, simulation widgets,
BoQ trace selection, overlay hover and the applied-message wording.

Findings covered: VIS-1, SPEC-5, VIS-11, UI-10, UI-1, UI-5, LOW-1, UI-3, UI-4, UI-11, UI-12, UI-13,
UI-15, UI-16, UI-17, SEC-3 (markdown rendering of untrusted text).
"""

from __future__ import annotations

import io
import logging

import pytest
from PIL import Image, ImageDraw

st_testing = pytest.importorskip("streamlit.testing.v1", reason="Streamlit AppTest is not available")
AppTest = st_testing.AppTest

from housebuilder_vision.core.models import ImageKind, ReferenceMeasurement, ViewDirection  # noqa: E402
from housebuilder_vision.ui import state as S  # noqa: E402

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HBV_DATA_DIR", str(tmp_path / "hbv"))
    monkeypatch.delenv("HBV_ENABLE_VLM", raising=False)
    logging.getLogger("streamlit").setLevel(logging.ERROR)


def _png(w=1000, h=700) -> bytes:
    im = Image.new("RGB", (w, h), (200, 200, 200))
    ImageDraw.Draw(im).rectangle((200, 250, 800, 650), outline=(0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


ROWS = [
    {"type": "window", "x0": 260, "y0": 500, "x1": 360, "y1": 590, "storey": 0, "block": "main"},
    {"type": "facade", "x0": 200, "y0": 250, "x1": 800, "y1": 650, "block": "main"},
    {"type": "window", "x0": 640, "y0": 500, "x1": 740, "y1": 590, "storey": 0},
    {"type": "ground_line", "x0": 200, "y0": 650, "x1": 800, "y1": 650},
    {"type": "eaves_line", "x0": 200, "y0": 300, "x1": 800, "y1": 300},
    {"type": "ridge_line", "x0": 220, "y0": 160, "x1": 780, "y1": 160},
    {"type": "door", "x0": 450, "y0": 480, "x1": 550, "y1": 650, "storey": 0},
    {"type": "window", "x0": 260, "y0": 340, "x1": 360, "y1": 430, "storey": 1},
    {"type": "window", "x0": 640, "y0": 340, "x1": 740, "y1": 430, "storey": 1},
]


def _annotated_ws(kind=ImageKind.PHOTOGRAPH):
    ws = S.Workspace(store_dir=str(S.image_store_dir()))
    S.new_project(ws, "Plot 12")
    added, rejected = S.ingest_uploads(ws, [("house.png", _png(), kind, ViewDirection.FRONT)])
    assert added and not rejected
    iid = ws.project.images[0].image_id
    assert S.set_annotations(ws, iid, ROWS) == []
    return ws, iid


# =============================================================================
# VIS-1 / SPEC-5: stable annotation ids, edit history, reference guard
# =============================================================================
def test_annotation_ids_are_stable_and_deleting_a_row_keeps_the_reference():
    ws, iid = _annotated_ws()
    rows = S.annotation_rows(ws, iid)
    assert all(r["id"].startswith(f"usr:{iid}:") and len(r["id"]) == len(f"usr:{iid}:") + 8 for r in rows)
    fac = rows[1]
    assert fac["type"] == "facade"
    assert S.set_reference(ws, ReferenceMeasurement(image_id=iid, feature_id=fac["id"], real_length=9.6,
                                                    tolerance=0.02, description="frontage")) is None
    ref = ws.project.references[0]
    assert ref.feature_type == "facade" and ref.feature_span_px == pytest.approx(600)
    mpp = ws.project.calibration.metres_per_pixel.value
    assert mpp == pytest.approx(0.016)
    # the user deletes the first row in the editor (the hidden id column travels with each row)
    assert S.set_annotations(ws, iid, rows[1:]) == []
    assert ws.calibration_error is None
    assert ws.project.calibration.method == "reference_measurement"
    assert ws.project.calibration.metres_per_pixel.value == pytest.approx(mpp)
    assert ws.project.twin.block("main").width.value == pytest.approx(9.6)
    assert [r["id"] for r in S.annotation_rows(ws, iid)] == [r["id"] for r in rows[1:]]


def test_editing_the_reference_box_is_reported_not_silently_rescaled():
    ws, iid = _annotated_ws()
    rows = S.annotation_rows(ws, iid)
    fid = rows[1]["id"]
    S.set_reference(ws, ReferenceMeasurement(image_id=iid, feature_id=fid, real_length=9.6, tolerance=0.02,
                                             description="frontage"))
    rows[1] = dict(rows[1], x1=700)  # 600 px -> 500 px
    assert S.set_annotations(ws, iid, rows) == []
    assert ws.calibration_error and "changed since the reference was confirmed" in ws.calibration_error
    assert ws.project.calibration.method != "reference_measurement"
    hist = next(f for f in ws.manual[iid] if f.feature_id == fid).history
    assert [h.reason for h in hist] == ["annotation created", "annotation edited"]
    assert hist[1].field == "bbox" and hist[1].old_value == [200.0, 250.0, 800.0, 650.0]
    assert hist[1].new_value == [200.0, 250.0, 700.0, 650.0] and hist[1].actor == "user"
    # deleting the reference feature is reported too
    assert S.set_annotations(ws, iid, [r for r in rows if r["id"] != fid]) == []
    assert ws.calibration_error  # no facade left or the reference feature no longer exists


def test_untick_in_editor_records_rejection_and_keeps_basis():
    ws, iid = _annotated_ws()
    rows = S.annotation_rows(ws, iid)
    rows[0] = dict(rows[0], active=False)
    assert S.set_annotations(ws, iid, rows) == []
    f = next(f for f in ws.manual[iid] if f.feature_id == rows[0]["id"])
    assert not f.active and f.basis.value == "user_confirmed"
    assert f.history[-1].reason == S.UI_REJECT_REASON == "rejected" and f.history[-1].actor == "user"


def test_ids_from_another_image_or_duplicates_are_replaced():
    ws, iid = _annotated_ws()
    asset = ws.image(iid)
    rows = [dict(ROWS[1], id="usr:img_ffffffffffffffff:12345678"), dict(ROWS[0], id="evil id with spaces"),
            dict(ROWS[2], id=f"usr:{iid}:abcdef01"), dict(ROWS[3], id=f"usr:{iid}:abcdef01")]
    feats, errors = S.annotations_to_features(asset, rows)
    assert not errors
    ids = [f.feature_id for f in feats]
    assert len(set(ids)) == 4 and ids[2] == f"usr:{iid}:abcdef01"
    assert all(i.startswith(f"usr:{iid}:") for i in ids)


# =============================================================================
# VIS-11 / UI-10: roof rows carry roof form, ridge and gable visibility; attributes refused elsewhere
# =============================================================================
def test_roof_attributes_belong_on_roof_rows():
    ws, iid = _annotated_ws()
    asset = ws.image(iid)
    feats, errors = S.annotations_to_features(asset, [
        {"type": "roof", "x0": 200, "y0": 100, "x1": 800, "y1": 250, "roof_form": "gable", "ridge": "perpendicular",
         "gable_visible": True, "block": "main"},
        {"type": "facade", "x0": 200, "y0": 250, "x1": 800, "y1": 650, "roof_form": "hip"},
        {"type": "window", "x0": 260, "y0": 500, "x1": 360, "y1": 590, "roof_form": "hip"},
        {"type": "facade", "x0": 200, "y0": 250, "x1": 800, "y1": 650, "ridge": "parallel"},
        {"type": "facade", "x0": 200, "y0": 250, "x1": 800, "y1": 650, "storey": 1},
        {"type": "roof", "x0": 200, "y0": 100, "x1": 800, "y1": 250, "roof_form": "hip", "gable_visible": True},
        {"type": "roof", "x0": 200, "y0": 100, "x1": 800, "y1": 250, "ridge": "parallel", "gable_visible": True},
    ])
    assert len(feats) == 2 and len(errors) == 5
    assert feats[0].attributes == {"block": "main", "roof_form": "gable", "ridge": "perpendicular",
                                   "gable_visible": True}
    assert feats[1].attributes == {"block": "main", "roof_form": "hip"}  # a facade may carry its roof form
    assert "belong on a roof row" in errors[0] and "belong on a roof row" in errors[1]
    assert "opening rows" in errors[2]
    assert "needs roof form 'gable'" in errors[3] and "perpendicular" in errors[4]


# =============================================================================
# Floor-plan workflow (shared contract): outline boxes and dimension lines
# =============================================================================
def test_floor_plan_rows_validate_outline_and_dimensions():
    ws = S.Workspace(store_dir=str(S.image_store_dir()))
    S.new_project(ws, "Plan")
    S.ingest_uploads(ws, [("plan.png", _png(), ImageKind.FLOOR_PLAN, ViewDirection.PLAN)])
    asset = ws.project.images[0]
    assert S.is_plan_image(asset)
    feats, errors = S.annotations_to_features(asset, [
        {"type": "building_outline", "x0": 200, "y0": 250, "x1": 800, "y1": 650, "block": "main", "storeys": 2,
         "front": "top"},
        {"type": "dimension", "x0": 200, "y0": 660, "x1": 800, "y1": 660, "length_m": 9.6, "axis": "width"},
        {"type": "dimension", "x0": 810, "y0": 250, "x1": 810, "y1": 650, "length_m": 8.4, "axis": "depth",
         "block": "main", "tolerance_m": 0.01},
        {"type": "building_outline", "x0": 190, "y0": 240, "x1": 810, "y1": 660},
        {"type": "dimension", "x0": 200, "y0": 660, "x1": 800, "y1": 660},
        {"type": "dimension", "x0": 200, "y0": 660, "x1": 800, "y1": 660, "length_m": 9.6, "axis": "diagonal"},
        {"type": "window", "x0": 10, "y0": 10, "x1": 50, "y1": 50},
        {"type": "building_outline", "x0": 200, "y0": 250, "x1": 800, "y1": 650, "storeys": 9},
        {"type": "dimension", "x0": 200, "y0": 660, "x1": 800, "y1": 660, "length_m": 9.6, "axis": "width",
         "front": "top"},
    ])
    assert len(feats) == 4 and len(errors) == 5
    outline, dw, dd, whole = feats
    assert outline.feature_type.value == "building_outline" and outline.bbox
    assert outline.attributes == {"block": "main", "storeys": 2, "front": "top"}
    assert whole.attributes == {}  # an outline without a block only transfers the scale (engine contract)
    assert dw.line == (200, 660, 800, 660) and dw.attributes == {"block": "main", "length_m": 9.6, "axis": "width"}
    assert dd.attributes == {"block": "main", "length_m": 8.4, "axis": "depth", "tolerance_m": 0.01}
    assert "length_m > 0" in errors[0] and "axis" in errors[1] and "floor plan" in errors[2]
    assert "storeys must be an integer 1-6" in errors[3] and "building_outline row" in errors[4]
    # plan columns are offered by the editor for plan images
    assert {"length_m", "axis", "block", "front", "id"} <= set(S.PLAN_COLUMNS) and "roof_form" not in S.PLAN_COLUMNS


# =============================================================================
# UI-1: a reference far from the prior cues is refused unless confirmed; then no silent rebuild
# =============================================================================
def test_conflicting_reference_is_refused_then_never_auto_rebuilds_the_twin():
    ws = S.Workspace(store_dir=str(S.image_store_dir()))
    S.load_demo(ws)
    iid = ws.project.images[0].image_id
    before = S.kpis(S.evaluate(ws))
    placeholder = ReferenceMeasurement(image_id=iid, p0=(0, 0), p1=(100, 0), real_length=9.6, tolerance=0.02,
                                       description="x")
    err = S.set_reference(ws, placeholder)
    assert err and "apart" in err
    assert S.kpis(S.evaluate(ws))["construction"] == pytest.approx(before["construction"])
    assert S.set_reference(ws, placeholder, allow_conflict=True) is None
    assert S.reference_conflict(ws.project.calibration)[0] > 5
    assert S.twin_status(ws) == "stale"  # the conflicting scale did not silently rebuild the twin
    assert S.kpis(S.evaluate(ws))["construction"] == pytest.approx(before["construction"])
    assert any("not rebuilt automatically" in t for _, t in ws.flash)


# =============================================================================
# UI-13 / UI-12: orphaned twin, concept-only twin
# =============================================================================
def test_removing_the_last_image_marks_the_twin_orphaned():
    ws = S.Workspace(store_dir=str(S.image_store_dir()))
    S.load_demo(ws)
    S.remove_image(ws, ws.project.images[0].image_id)
    assert S.twin_status(ws) == "orphaned"
    assert any("manual model" in t for _, t in ws.flash)


def test_concept_only_project_is_flagged():
    ws, iid = _annotated_ws(kind=ImageKind.AI_CONCEPT)
    assert S.concept_source(ws) == "all"
    from housebuilder_vision.io.export import concept_reference_warning

    assert "Concept reference only" in concept_reference_warning(ws.project)
    ws2, _ = _annotated_ws(kind=ImageKind.PHOTOGRAPH)
    assert S.concept_source(ws2) is None


# =============================================================================
# UI-15: the applied message reports layer-9 changes
# =============================================================================
def test_applied_message_reports_total_development_cost():
    from housebuilder_vision.ui.views import costs

    ws = S.Workspace(store_dir=str(S.image_store_dir()))
    S.load_demo(ws)
    ev = S.evaluate(ws)
    before = ws.project.cost_parameters
    assert S.update_cost_parameters(ws, {"land_cost": 120000.0, "sales_value": 450000.0, "finance_rate_annual": 0.07,
                                         "finance_months": 12.0, "sales_cost_fraction": 0.025}) is None
    level, msg = costs._applied_message(ws, ev, before, costs._rates_in_force(ws))
    assert level == "success"
    assert "total development cost none → £" in msg and "contract sum unchanged" in msg
    assert "sales value (GDV) none → £450,000" in msg


# =============================================================================
# UI-4: BoQ trace selection follows the line id
# =============================================================================
def test_boq_selection_is_resolved_by_line_id():
    from housebuilder_vision.ui.views.quantities import resolve_selection

    ids = ["a", "b", "c", "d"]
    assert resolve_selection(None, None, "k1", [3], ids) == "d"
    # filters changed (new table key, selection reset): the previously chosen line is kept by id ...
    assert resolve_selection("d", "k1", "k2", [], ["x", "d"]) == "d"
    # ... and dropped when it is filtered out - never re-targeted to the row at the same position
    assert resolve_selection("d", "k1", "k2", [], ["p", "q", "r", "s"]) is None
    assert resolve_selection("d", "k2", "k2", [], ids) is None  # user cleared the selection


# =============================================================================
# UI-11: hover details for windows and doors inside big shapes
# =============================================================================
def test_overlay_hover_reaches_openings():
    from housebuilder_vision.ui import charts

    ws = S.Workspace(store_dir=str(S.image_store_dir()))
    S.load_demo(ws)
    a = ws.project.images[0]
    feats = ws.project.analysis.analyses[0].features
    fig = charts.overlay_figure(a.width_px, a.height_px, feats)
    outlines = [t for t in fig.data if t.type == "scatter" and t.mode == "lines"]
    assert outlines and all(t.hoverinfo == "skip" for t in outlines)
    hover = next(t for t in fig.data if t.name == "evidence details")
    win = next(f for f in feats if f.feature_type.value == "window" and f.active)
    cx, cy = (win.bbox[0] + win.bbox[2]) / 2, (win.bbox[1] + win.bbox[3]) / 2
    pts = list(zip(hover.x, hover.y, hover.hovertext))
    nearest = min(pts, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    assert win.feature_id in nearest[2] and "window" in nearest[2]


# =============================================================================
# SEC-3: untrusted text never renders as markdown links / images
# =============================================================================
def test_md_escape_neutralises_links_and_images():
    from housebuilder_vision.ui.theme import md_escape

    out = md_escape("[click](http://evil.example) ![x](http://evil.example/a.png) **b**")
    assert "](" not in out and "![" not in out and "**" not in out
    assert "http\\://evil\\.example" in out


# =============================================================================
# UI-17: a rejected upload does not stay in the uploader
# =============================================================================
def test_rejected_upload_clears_the_uploader(monkeypatch):
    import streamlit as st

    from housebuilder_vision.ui.views import images

    ws = S.Workspace(store_dir=str(S.image_store_dir()))
    S.new_project(ws, "x")
    monkeypatch.setattr(S, "get_workspace", lambda: ws)
    st.session_state["uploader_gen"] = 3
    images._cb_ingest([("not_an_image.png", b"definitely not a png", "f1")])
    assert st.session_state["uploader_gen"] == 4
    assert any(level == "error" and "Rejected" in t for level, t in ws.flash)


# =============================================================================
# AppTest: simulation widgets (UI-3 / UI-16) and the calibration form (UI-1 / UI-5 / LOW-1)
# =============================================================================
def _app() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=240)
    at.run()
    return at


def _no_exceptions(at: AppTest, where: str) -> None:
    assert not at.exception, f"{where}: {[e.value for e in at.exception]}"


def test_second_simulation_uses_the_submitted_seed_and_samples_survive_tab_switch():
    at = _app()
    at.button(key="load_demo").click().run()
    at.session_state["main_tab"] = "Costs"
    at.run()
    pid = at.session_state["hbv_workspace"].project.project_id
    at.number_input(key=f"sim_n_{pid}").set_value(40)
    at.number_input(key=f"sim_seed_{pid}").set_value(1)
    next(b for b in at.button if b.label == "Run simulation").click().run()
    _no_exceptions(at, "first run")
    assert at.session_state["hbv_workspace"].simulation.config.seed == 1
    at.number_input(key=f"sim_seed_{pid}").set_value(2)
    next(b for b in at.button if b.label == "Run simulation").click().run()
    _no_exceptions(at, "second run")
    sim = at.session_state["hbv_workspace"].simulation
    assert sim.config.seed == 2 and sim.n_samples == 40
    assert at.number_input(key=f"sim_seed_{pid}").value == 2
    # leave the tab and come back: the widgets show the last run's config (no silent 300 cap / reset)
    at.session_state["main_tab"] = "Quantities"
    at.run()
    at.session_state["main_tab"] = "Costs"
    at.run()
    assert at.number_input(key=f"sim_n_{pid}").value == 40 and at.number_input(key=f"sim_seed_{pid}").value == 2


def test_calibration_form_follows_the_image_and_refuses_empty_endpoints():
    at = _app()
    at.checkbox(key="demo_side").check()
    at.button(key="load_demo").click().run()
    ws = at.session_state["hbv_workspace"]
    front, side = (a.image_id for a in ws.project.images)
    before = dict(ws.cur_kpis)
    # pixel endpoints start empty: submitting them unfilled is refused
    at.radio(key="ref_mode").set_value("Pixel endpoints").run()
    next(b for b in at.button if b.label == "Apply calibration").click().run()
    _no_exceptions(at, "endpoints")
    assert any("enter all four pixel coordinates" in e.value for e in at.error)
    assert at.session_state["hbv_workspace"].cur_kpis["construction"] == pytest.approx(before["construction"])
    # the feature list follows the selected image immediately (image chosen outside the form)
    at.radio(key="ref_mode").set_value("Feature width (box)").run()
    at.selectbox(key="ref_img").set_value(side).run()
    feat_box = at.selectbox(key=f"ref_feat_{side}")
    assert feat_box.options and all(side in o or "facade" in o or "·" in o for o in feat_box.options)
    assert str(feat_box.value).startswith(side)
    at.number_input(key=f"ref_len_{side}").set_value(8.4)
    at.text_input(key=f"ref_desc_{side}").input("measured side wall length")
    next(b for b in at.button if b.label == "Apply calibration").click().run()
    _no_exceptions(at, "side reference")
    ref = at.session_state["hbv_workspace"].project.references[0]
    assert ref.image_id == side and ref.feature_id == feat_box.value and ref.real_length == pytest.approx(8.4)


def test_new_project_reference_form_has_no_fictional_defaults():
    ws, iid = _annotated_ws()
    at = AppTest.from_file(str(APP), default_timeout=240)
    at.session_state["hbv_workspace"] = ws
    at.run()
    _no_exceptions(at, "new project")
    assert at.number_input(key=f"ref_len_{iid}").value is None
    assert at.number_input(key=f"ref_tol_{iid}").value is None
    assert at.text_input(key=f"ref_desc_{iid}").value == ""
    next(b for b in at.button if b.label == "Apply calibration").click().run()
    assert any("enter the real length" in e.value for e in at.error)
    assert not at.session_state["hbv_workspace"].project.references


# =============================================================================
# Shared contract end to end through the UI state (engine side by group D)
# =============================================================================
def test_ui_front_gable_annotation_gives_a_measured_pitch_and_front_to_rear_ridge():
    ws = S.Workspace(store_dir=str(S.image_store_dir()))
    S.new_project(ws, "Front gable")
    S.ingest_uploads(ws, [("gable.png", _png(1000, 800), ImageKind.PHOTOGRAPH, ViewDirection.FRONT)])
    iid = ws.project.images[0].image_id
    rows = [
        {"type": "facade", "x0": 300, "y0": 250, "x1": 900, "y1": 700, "block": "main"},
        {"type": "roof", "x0": 300, "y0": 250, "x1": 900, "y1": 550, "roof_form": "gable", "ridge": "perpendicular",
         "gable_visible": True, "block": "main"},
        {"type": "ground_line", "x0": 300, "y0": 700, "x1": 900, "y1": 700},
        {"type": "eaves_line", "x0": 300, "y0": 550, "x1": 900, "y1": 550},
        {"type": "door", "x0": 560, "y0": 490, "x1": 650, "y1": 700, "storey": 0},
        {"type": "window", "x0": 360, "y0": 590, "x1": 460, "y1": 660, "storey": 0},
    ]
    assert S.set_annotations(ws, iid, rows) == []
    fo = next(f for f in ws.project.analysis.facades if f.block_hint == "main")
    assert fo.ridge_axis_hint == "perpendicular_to_view"
    assert fo.apparent_pitch_deg.value == pytest.approx(45.0, abs=0.5)
    assert fo.apparent_pitch_deg.basis.value == "user_confirmed"
    assert ws.project.twin.block("main").roof.ridge_axis == "y"


def test_ui_floor_plan_annotations_make_the_depth_evidence_based():
    ws = S.Workspace(store_dir=str(S.image_store_dir()))
    S.new_project(ws, "Plan")
    S.ingest_uploads(ws, [("front.png", _png(), ImageKind.PHOTOGRAPH, ViewDirection.FRONT)])
    fid = ws.project.images[0].image_id
    assert S.set_annotations(ws, fid, [ROWS[1], ROWS[3], ROWS[4], ROWS[5], ROWS[6], ROWS[7]]) == []
    assert ws.project.twin.block("main").depth.basis.value == "assumed"
    plan = Image.new("RGB", (900, 900), (255, 255, 255))
    buf = io.BytesIO()
    plan.save(buf, "PNG")
    S.ingest_uploads(ws, [("plan.png", buf.getvalue(), ImageKind.FLOOR_PLAN, ViewDirection.PLAN)])
    pid = ws.project.images[1].image_id
    assert S.set_annotations(ws, pid, [
        {"type": "building_outline", "x0": 100, "y0": 200, "x1": 700, "y1": 700, "block": "main"},
        {"type": "dimension", "x0": 100, "y0": 720, "x1": 700, "y1": 720, "length_m": 9.6, "axis": "width"},
    ]) == []
    main = ws.project.twin.block("main")
    assert main.depth.basis.value in ("inferred", "user_confirmed")
    assert main.depth.value == pytest.approx(8.0, rel=0.02)  # 500 px x (9.6 m / 600 px)
    assert main.width.value == pytest.approx(9.6) and main.width.basis.value == "user_confirmed"
