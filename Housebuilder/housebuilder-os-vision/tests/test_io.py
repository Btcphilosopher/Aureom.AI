"""Tests for export (JSON / GLB / CSV / manifest), the optional IFC adapter and the SQLite store.

The project is built by hand: a hypothesis with a two-storey main block, a lower
unheated garage and a hidden flat-roofed rear extension, turned into a twin with
``twin.builder`` (hidden facades rule-filled) and quantified with ``quantities``.
Cost / simulation / repeat-build results are hand-made model objects so the tests
do not depend on the costing or simulation engines.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sqlite3
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import trimesh

from housebuilder_vision.core.models import (
    Block,
    BlockRole,
    CostBoundary,
    CostEstimate,
    CostLayer,
    CostLine,
    DistributionSummary,
    GeometryHypothesis,
    HiddenSideAssumptions,
    ImageAsset,
    ImageKind,
    Opening,
    OpeningKind,
    Project,
    QuantityLine,
    Rate,
    RateBook,
    RateSourceType,
    RepeatBuildResult,
    RepeatBuildRow,
    RoofForm,
    RoofSpec,
    RunRecord,
    ScenarioComparison,
    ScenarioOutcome,
    Side,
    SimulationConfig,
    SimulationResult,
    ViewDirection,
    VisualFinish,
)
from housebuilder_vision.core.provenance import Basis, assumed, confirmed, inferred, observed
from housebuilder_vision.io import (
    FICTIONAL_LABEL,
    IFC_INFORMATION_LEVEL,
    IFC_INSTALL_HINT,
    INFORMATION_PSET,
    STORE_SCHEMA_VERSION,
    AdapterUnavailable,
    ExportManifest,
    ProjectNotFound,
    ProjectStore,
    StoreError,
    canonical_sha256,
    csv_bytes,
    default_db_path,
    engine_version,
    export_ifc,
    export_project,
    provenance_counts,
    sanitize_cell,
)
from housebuilder_vision.io.export import _Out
from housebuilder_vision.quantities import calculate_quantities, default_library, default_selection
from housebuilder_vision.twin import build_mesh, build_parametric_twin, twin_hash

LIB = default_library()
IMG_BYTES = b"not really an image - only its sha256 matters here"
IMG_SHA = hashlib.sha256(IMG_BYTES).hexdigest()


# =============================================================================
# Fixtures
# =============================================================================
def _block(bid, x0, y0, w, d, *, storeys=2, form=RoofForm.GABLE, pitch=35.0, axis="x", eo=0.3, vo=0.2,
           heated=True, role=BlockRole.MAIN, visible=(Side.FRONT,), depth_basis="assumed"):
    depth = (assumed(d, "m", low=0.8 * d, high=1.2 * d, source="test prior") if depth_basis == "assumed"
             else confirmed(d, "m"))
    pitch_tv = (observed(pitch, "deg", low=pitch - 2, high=pitch + 2, source="gable") if form != RoofForm.FLAT
                else assumed(0.0, "deg"))
    return Block(
        block_id=bid, name=bid, role=role,
        origin_x=confirmed(x0, "m"), origin_y=confirmed(y0, "m"),
        width=inferred(w, "m", low=w - 0.05, high=w + 0.05, source="scaled from image"), depth=depth,
        storeys=observed(storeys, "storeys"), floor_to_floor=assumed(2.7, "m", low=2.5, high=3.0),
        ground_floor_level=assumed(0.15, "m", low=0.1, high=0.25),
        roof=RoofSpec(form=form, pitch_deg=pitch_tv, ridge_axis=axis, eaves_overhang_m=assumed(eo, "m"),
                      verge_overhang_m=assumed(vo, "m")),
        heated=heated, visible_sides=list(visible))


def _opening(oid, bid, side, kind, storey, off, w, h, sill):
    return Opening(opening_id=oid, block_id=bid, side=side, kind=kind, storey=storey,
                   offset_m=observed(off, "m"), width_m=observed(w, "m"), height_m=observed(h, "m"),
                   sill_m=observed(sill, "m"), feature_id=f"f_{oid}")


def make_twin():
    blocks = [
        _block("main", 0.0, 0.0, 9.6, 8.4),
        _block("garage", 9.6, 0.0, 3.2, 6.0, storeys=1, pitch=30.0, axis="y", heated=False, role=BlockRole.GARAGE),
        _block("ext", 0.0, 8.4, 4.8, 3.6, storeys=1, form=RoofForm.FLAT, eo=0.15, vo=0.15, role=BlockRole.EXTENSION,
               visible=()),
    ]
    openings = [
        _opening("W1", "main", Side.FRONT, OpeningKind.WINDOW, 0, 1.0, 1.8, 1.2, 0.9),
        _opening("D1", "main", Side.FRONT, OpeningKind.DOOR, 0, 4.3, 1.0, 2.1, 0.0),
        _opening("W2", "main", Side.FRONT, OpeningKind.WINDOW, 0, 6.8, 1.8, 1.2, 0.9),
        _opening("W3", "main", Side.FRONT, OpeningKind.WINDOW, 1, 1.3, 1.2, 1.2, 0.9),
        _opening("W4", "main", Side.FRONT, OpeningKind.WINDOW, 1, 4.2, 1.2, 1.2, 0.9),
        _opening("W5", "main", Side.FRONT, OpeningKind.WINDOW, 1, 7.1, 1.2, 1.2, 0.9),
        _opening("G1", "garage", Side.FRONT, OpeningKind.GARAGE_DOOR, 0, 0.4, 2.4, 2.13, 0.0),
    ]
    hyp = GeometryHypothesis(
        hypothesis_id="H-L", name="L-shaped with rear extension", blocks=blocks, openings=openings,
        hidden=HiddenSideAssumptions(rear_glazing_ratio=assumed(0.2, "fraction", low=0.12, high=0.35),
                                     side_glazing_ratio=assumed(0.04, "fraction", low=0.0, high=0.1)),
        calibration_method="reference_measurement")
    finishes = [VisualFinish(element="walls", appearance="red-brown brick-like", colour_hex="#8B4A3A"),
                VisualFinish(element="roof", appearance="dark grey tile-like", colour_hex="#3C3F44")]
    return build_parametric_twin(hyp, selection=default_selection(LIB), visual_finishes=finishes, twin_id="twin_io")


FICTIONAL_RATE = Rate(rate_id="r_brick", cost_key="mat:facing_brick", description="Facing brick",
                      layer=CostLayer.MATERIALS, unit="nr", value=0.62, effective_date=date(2026, 6, 1),
                      source="FICTIONAL demo price list", source_type=RateSourceType.FICTIONAL_DEMO)
QUOTE_RATE = Rate(rate_id="r_quote", cost_key="lab:bricklaying", layer=CostLayer.LABOUR, unit="hr", value=41.0,
                  effective_date=date(2026, 9, 1), source="Quote Q-123", source_type=RateSourceType.SUPPLIER_QUOTE)


def make_project(twin=None):
    twin = twin if twin is not None else make_twin()
    image = ImageAsset(image_id="img_" + IMG_SHA[:16], sha256=IMG_SHA, original_filename="=front elevation.png",
                       media_type="image/png", width_px=1600, height_px=1000, size_bytes=len(IMG_BYTES),
                       kind=ImageKind.ELEVATION_DRAWING, view=ViewDirection.FRONT,
                       stored_path=f"/data/images/{IMG_SHA}.png")
    return Project(project_id="proj_io", name="IO test house (fictional)", twin=twin, library=LIB, images=[image],
                   rate_book=RateBook(name="FICTIONAL demo + quote", rates=[FICTIONAL_RATE, QUOTE_RATE]))


def make_estimate():
    lines = [
        CostLine(line_id="c1", layer=CostLayer.MATERIALS, description="=HYPERLINK(\"http://evil\",\"x\")",
                 cost_key="mat:facing_brick", quantity=12000.0, unit="nr", rate_value=0.62, rate_id="r_brick",
                 amount=7440.0, quantity_line_id="2.5.main.ew_masonry_cavity.0", basis=Basis.ASSUMED,
                 formula="12000 nr x 0.62"),
        CostLine(line_id="c2", layer=CostLayer.LABOUR, description="Bricklaying labour", cost_key="lab:bricklaying",
                 quantity=300.0, unit="hr", rate_value=41.0, rate_id="r_quote", amount=12300.0,
                 basis=Basis.USER_CONFIRMED),
        CostLine(line_id="c3", layer=CostLayer.CONTINGENCY, description="-Risk credit (test negative)",
                 amount=-120.5, basis=Basis.ASSUMED, uncertainty_low=-0.1, uncertainty_high=0.2,
                 notes="@mention test"),
    ]
    boundaries = [CostBoundary(key="direct", name="Direct cost", layers=[CostLayer.MATERIALS, CostLayer.LABOUR],
                               amount=19740.0, definition="Layers 1-2"),
                  CostBoundary(key="construction_incl_contingency", name="Construction incl. contingency",
                               layers=[CostLayer.MATERIALS, CostLayer.LABOUR, CostLayer.CONTINGENCY],
                               amount=19619.5, definition="+Layer 7", excludes="Land, finance, VAT")]
    return CostEstimate(currency="GBP", pricing_date=date(2026, 11, 1), location="Plot 7 (fictional)",
                        rate_book_name="FICTIONAL demo + quote", lines=lines,
                        layer_totals={CostLayer.MATERIALS.value: 7440.0, CostLayer.LABOUR.value: 12300.0,
                                      CostLayer.CONTINGENCY.value: -120.5},
                        boundaries=boundaries, gia_m2=150.0,
                        warnings=["1 of 2 rates used are labelled FICTIONAL (demo data) - not market prices."])


def make_simulation():
    summary = DistributionSummary(metric="construction_cost", unit="GBP", mean=1.0e5, std=1.0e4, p5=8.5e4,
                                  p10=8.8e4, p50=1.0e5, p80=1.08e5, p90=1.12e5, p95=1.16e5, min=7.0e4, max=1.4e5)
    return SimulationResult(scenario_id="base", config=SimulationConfig(n_samples=100, seed=42), n_samples=100,
                            metrics=[summary], samples={"construction_cost": [1.0e5, float("nan"), 1.1e5]})


def make_repeat():
    rows = [RepeatBuildRow(n=n, total_cost=1e5 * n ** 0.9, average_cost=1e5 * n ** -0.1,
                           incremental_cost=9e4, components={"materials": 5e4 * n, "labour": 4e4 * n})
            for n in (1, 2, 3)]
    return RepeatBuildResult(scenario_id="site_built", boundary="installed", boundary_definition="Installed cost",
                             currency="GBP", rows=rows, comparison_ns=[1, 3])


def make_comparison():
    o = ScenarioOutcome(scenario_id="base", name="=Masonry", hypothesis_id="H-L", gia_m2=150.0,
                        external_wall_thickness_m=0.316, construction_cost=2e5, contract_sum=2.3e5,
                        cost_per_m2_gia=1333.0, labour_hours=2000.0, programme_weeks=26.0,
                        embodied_carbon_kgco2e=5e4, heat_loss_coefficient_w_k=150.0, peak_heat_load_kw=4.0,
                        key_assumptions=["depth assumed", "assemblies assumed"])
    return ScenarioComparison(outcomes=[o])


@pytest.fixture(scope="module")
def twin():
    return make_twin()


@pytest.fixture(scope="module")
def project(twin):
    return make_project(twin)


@pytest.fixture(scope="module")
def boq(twin):
    return calculate_quantities(twin, LIB)


@pytest.fixture(scope="module")
def export_dir(tmp_path_factory, project, boq):
    out = tmp_path_factory.mktemp("export")
    manifest = export_project(project, out, boq=boq, estimate=make_estimate(), simulation=make_simulation(),
                              repeat=make_repeat(), comparison=make_comparison())
    return out, manifest


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# =============================================================================
# JSON
# =============================================================================
def test_json_round_trip_equality(export_dir, project, twin, boq):
    out, manifest = export_dir
    reloaded = Project.model_validate_json((out / "project.json").read_text(encoding="utf-8"))
    # Exports carry store-relative image file names, never absolute local paths (security: a reloaded
    # project must not be able to point the app at arbitrary files); everything else round-trips exactly.
    for im in reloaded.images:
        assert im.stored_path is None or ("/" not in im.stored_path and im.stored_path.startswith(im.sha256))

    def portable(p):
        return p.model_copy(update={"images": [i.model_copy(update={"stored_path": None}) for i in p.images]})

    assert portable(reloaded) == portable(project)
    assert reloaded.twin == twin
    assert twin_hash(reloaded.twin) == twin_hash(twin)

    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert results["engine"]["engine"].endswith(engine_version())
    assert results["engine"]["model_schema"] == project.schema_version
    assert [im["sha256"] for im in results["source_images"]] == [IMG_SHA]
    assert results["twin"]["hash"] == twin_hash(twin)
    assert results["project_json_sha256"] == hashlib.sha256((out / "project.json").read_bytes()).hexdigest()
    assert results["project_state_sha256"] == canonical_sha256(project)
    assert "weakest basis" in results["provenance"]["note"]
    assert results["provenance"]["parameter_counts"] == provenance_counts(twin)
    assert results["pricing"]["uses_fictional_rates"] is True
    assert results["seeds"]["simulation_result"] == 42
    res = results["results"]
    assert res["boq_source"] == "supplied by caller"
    assert len(res["bill_of_quantities"]["lines"]) == len(boq.lines)
    assert len(res["cost_estimate"]["lines"]) == 3
    assert res["simulation"]["samples"]["construction_cost"][1] is None  # NaN -> null (strict JSON)
    assert [r["n"] for r in res["repeat_build"][0]["rows"]] == [1, 2, 3]
    assert res["scenario_comparison"]["outcomes"][0]["scenario_id"] == "base"
    # result objects re-validate through their models
    est = CostEstimate.model_validate(res["cost_estimate"])
    assert est.model_dump(exclude={"created_at"}) == make_estimate().model_dump(exclude={"created_at"})


def test_boq_computed_when_not_supplied(tmp_path, project):
    m = export_project(project, tmp_path, formats=("json", "csv"))
    results = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert results["results"]["boq_source"].startswith("computed at export")
    assert any("computed at export" in n for n in m.notes)
    assert (tmp_path / "quantities.csv").exists()
    assert any("costs.csv" in w for w in m.warnings)  # no estimate -> warning, not an error


# =============================================================================
# GLB
# =============================================================================
def test_glb_reloads_with_nodes_and_y_up_extents(export_dir, twin, boq):
    out, manifest = export_dir
    scene = trimesh.load(out / "twin.glb", file_type="glb", force="scene")
    nodes = set(scene.graph.nodes_geometry)
    roofs = [b for b in twin.blocks]  # every block has a drawable roof
    assert len(nodes) == len(twin.blocks) + len(roofs) + len(twin.openings)
    assert {f"{b.block_id}/walls" for b in twin.blocks} <= nodes
    assert {f"{b.block_id}/roof" for b in twin.blocks} <= nodes
    assert {f"opening/{o.opening_id}" for o in twin.openings} <= nodes

    (xmin, ymin, zmin), (xmax, ymax, zmax) = scene.bounds
    g = boq.geometry
    # height is glTF +y: ground (0) to the highest ridge
    assert ymin == pytest.approx(0.0, abs=1e-4)
    assert ymax == pytest.approx(max(r.ridge_height_m for r in g.roofs), abs=1e-3)
    # plan x is glTF x; plan y (front -> rear) is glTF -z. Footprint 0..12.8 x 0..12.0 plus overhangs.
    assert xmin == pytest.approx(-0.2, abs=1e-4)   # main verge overhang
    assert xmax == pytest.approx(12.8 + 0.3, abs=1e-4)  # garage eaves overhang (ridge along y)
    assert -zmax == pytest.approx(-0.3, abs=1e-4)   # main front eaves overhang
    assert -zmin == pytest.approx(12.0 + 0.15, abs=1e-4)  # flat extension edge overhang
    # same extents as the z-up mesh rotated into y-up
    zb = build_mesh(twin).bounds
    assert np.allclose([xmin, ymin, zmin, xmax, ymax, zmax],
                       [zb[0][0], zb[0][2], -zb[1][1], zb[1][0], zb[1][2], -zb[0][1]], atol=1e-4)
    # the visual-only notice travels inside the file (scene extras)
    assert "Visual geometry only" in scene.metadata.get("notice", "")
    assert "Visual geometry only" in manifest.file("twin.glb").description


# =============================================================================
# CSV
# =============================================================================
@pytest.mark.parametrize("text", ["=1+1", "+SUM(A1)", "-2+3", "@cmd", "\tx", "\rx", "=cmd|' /C calc'!A0"])
def test_sanitize_cell_prefixes_formula_starts(text):
    assert sanitize_cell(text) == "'" + text


@pytest.mark.parametrize("value", [-5, -0.25, 0, 3.5, 12000.0])
def test_sanitize_cell_leaves_numbers(value):
    assert sanitize_cell(value) == value and type(sanitize_cell(value)) is type(value)


def test_sanitize_cell_other_values():
    assert sanitize_cell(None) == ""
    assert sanitize_cell(True) == "true"
    assert sanitize_cell("brick - facing") == "brick - facing"
    assert sanitize_cell(Basis.ASSUMED) == "assumed"
    raw = csv_bytes(["a", "b"], [{"a": "=evil()", "b": -1.5}]).decode("utf-8")
    rows = list(csv.reader(io.StringIO(raw)))
    assert rows[1] == ["'=evil()", "-1.5"]


def test_csv_files_guarded_and_complete(export_dir, boq):
    out, _ = export_dir
    costs = _read_csv(out / "costs.csv")
    by_id = {r["line_id"]: r for r in costs}
    assert by_id["c1"]["description"].startswith("'=HYPERLINK")
    assert by_id["c3"]["description"] == "'-Risk credit (test negative)"
    assert by_id["c3"]["notes"] == "'@mention test"
    assert by_id["c3"]["amount"] == "-120.5"  # numbers untouched
    assert float(by_id["c3"]["uncertainty_low"]) == -0.1
    assert by_id["c1"]["price_label"] == FICTIONAL_LABEL
    assert by_id["c1"]["rate_source_type"] == "fictional_demo"
    assert by_id["c2"]["price_label"] == "" and by_id["c2"]["rate_source_type"] == "supplier_quote"
    assert "FICTIONAL" in by_id["c3"]["price_label"]  # derived line in an estimate using fictional rates
    assert by_id["c1"]["layer_name"] == "Purchased materials"

    bounds = _read_csv(out / "cost_boundaries.csv")
    assert [b["key"] for b in bounds] == ["direct", "construction_incl_contingency"]
    assert bounds[1]["definition"] == "'+Layer 7"
    assert "FICTIONAL" in bounds[0]["price_label"]
    assert float(bounds[0]["per_m2_gia"]) == pytest.approx(19740.0 / 150.0)

    qty = _read_csv(out / "quantities.csv")
    assert len(qty) == len(boq.lines)
    assert set(QuantityLine.model_fields) <= set(qty[0])
    first = boq.lines[0]
    assert qty[0]["line_id"] == first.line_id
    assert qty[0]["status"] == first.status.value and qty[0]["basis"] == first.basis.value
    assert all(r["basis"] in {b.value for b in Basis} for r in qty)
    traced = [r for r in qty if r["trace"]]
    assert traced and all(not r["trace"].startswith(("=", "+", "-", "@")) for r in traced)
    assert any("geometry:" in r["trace"] for r in traced)
    for r, ln in zip(qty, boq.lines):
        if ln.installed_qty is not None:
            assert float(r["installed_qty"]) == pytest.approx(ln.installed_qty, rel=1e-12)

    rep = _read_csv(out / "repeat_build.csv")
    assert [int(r["n"]) for r in rep] == [1, 2, 3]
    assert rep[0]["is_comparison_n"] == "true" and rep[1]["is_comparison_n"] == "false"
    cmp_rows = _read_csv(out / "scenario_comparison.csv")
    assert cmp_rows[0]["name"] == "'=Masonry"
    sim = _read_csv(out / "simulation_summary.csv")
    assert sim[0]["metric"] == "construction_cost" and sim[0]["seed"] == "42"


# =============================================================================
# Manifest and paths
# =============================================================================
def test_manifest_sha256_and_contents(export_dir):
    out, manifest = export_dir
    on_disk = ExportManifest.model_validate_json((out / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk == manifest
    assert manifest.verify(out) == []
    paths = {f.path for f in manifest.files}
    assert "manifest.json" not in paths
    expected = {"project.json", "results.json", "twin.glb", "quantities.csv", "costs.csv", "cost_boundaries.csv",
                "repeat_build.csv", "simulation_summary.csv", "scenario_comparison.csv", "README.txt"}
    assert expected <= paths
    for f in manifest.files:
        data = (out / f.path).read_bytes()
        assert f.sha256 == hashlib.sha256(data).hexdigest()
        assert f.size_bytes == len(data)
        assert f.description
    assert manifest.source_images[0]["sha256"] == IMG_SHA
    assert manifest.twin["hash"] == twin_hash(manifest_twin := make_twin()) and manifest_twin.twin_id == "twin_io"
    assert "not construction-ready BIM" in manifest.information_level
    readme = (out / "README.txt").read_text(encoding="utf-8")
    assert "FICTIONAL" in readme and "Visual geometry only" in readme
    # tampering is detected
    (out / "README.txt").write_bytes(b"changed")
    assert any("README.txt" in p for p in manifest.verify(out))


def test_export_paths_stay_inside_out_dir(tmp_path, project):
    out = _Out(tmp_path / "x")
    for bad in ("../evil.json", "/etc/passwd", "a/b.csv", ".hidden", "..", ""):
        with pytest.raises(ValueError):
            out.target(bad)
    # a symlink planted at a target name is never written through
    victim = tmp_path / "victim.txt"
    victim.write_text("original")
    od = tmp_path / "linked"
    od.mkdir()
    (od / "project.json").symlink_to(victim)
    with pytest.raises(ValueError):
        export_project(project, od, formats=("json",))
    assert victim.read_text() == "original"
    # project text never becomes a path
    hostile = project.model_copy(update={"name": "../../../../tmp/evil", "notes": "=cmd"})
    clean = tmp_path / "clean"
    m = export_project(hostile, clean, formats=("json", "csv"))
    for f in m.files:
        assert (clean / f.path).resolve().parent == clean.resolve()
    assert sorted(p.name for p in clean.iterdir()) == sorted([*(f.path for f in m.files), "manifest.json"])


def test_unknown_format_rejected(tmp_path, project):
    with pytest.raises(ValueError):
        export_project(project, tmp_path, formats=("json", "dwg"))


def test_project_without_twin_exports_with_warnings(tmp_path):
    p = Project(project_id="empty_proj", name="Nothing yet")
    m = export_project(p, tmp_path)
    paths = {f.path for f in m.files}
    assert {"project.json", "results.json", "README.txt"} <= paths
    assert "twin.glb" not in paths and "twin.ifc" not in paths
    assert any("GLB" in w for w in m.warnings) and any("IFC" in w for w in m.warnings)
    assert m.twin is None
    assert Project.model_validate_json((tmp_path / "project.json").read_text(encoding="utf-8")) == p


def test_unknown_dimension_exports_with_warnings(tmp_path, project):
    from housebuilder_vision.core.models import QuantityStatus
    from housebuilder_vision.core.provenance import unknown

    twin = project.twin.model_copy(deep=True)
    twin.blocks[2].depth = unknown("m", note="hidden extension depth")
    m = export_project(project.model_copy(update={"twin": twin}), tmp_path)
    paths = {f.path for f in m.files}
    assert {"project.json", "results.json", "quantities.csv"} <= paths and "twin.ifc" not in paths
    assert any(w.startswith("IFC not written") and "unknown" in w for w in m.warnings)
    qty = _read_csv(tmp_path / "quantities.csv")
    assert any(r["status"] == QuantityStatus.UNRESOLVED.value for r in qty)  # never invented
    assert m.verify(tmp_path) == []


def test_missing_ifcopenshell_is_a_warning(tmp_path, project, boq, monkeypatch):
    monkeypatch.setitem(sys.modules, "ifcopenshell", None)  # makes `import ifcopenshell...` fail
    m = export_project(project, tmp_path, boq=boq, formats=("json", "ifc"))
    assert not (tmp_path / "twin.ifc").exists()
    assert any("ifcopenshell" in w for w in m.warnings)
    assert m.ifc is None
    with pytest.raises(AdapterUnavailable) as exc:
        export_ifc(project.twin, boq.geometry, tmp_path / "direct.ifc")
    assert "pip install" in str(exc.value) and IFC_INSTALL_HINT in str(exc.value)


# =============================================================================
# IFC
# =============================================================================
def test_ifc_export_reopens_with_expected_entities(tmp_path, twin, boq):
    ifcopenshell = pytest.importorskip("ifcopenshell")
    import ifcopenshell.util.element as ue

    path = tmp_path / "twin.ifc"
    report = export_ifc(twin, boq.geometry, path, library=LIB)
    model = ifcopenshell.open(str(path))
    assert model.schema == "IFC4"

    ext_pieces = [p for p in boq.geometry.pieces if p.exposure == "external"]
    assert len(model.by_type("IfcWall")) == len(ext_pieces) == report.entity_counts["IfcWall"]
    assert {w.Name for w in model.by_type("IfcWall")} == {f"External wall {p.piece_id}" for p in ext_pieces}
    storeys = model.by_type("IfcBuildingStorey")
    assert len(storeys) == max(int(b.storeys.value) for b in twin.blocks) == 2
    assert sorted(round(s.Elevation, 3) for s in storeys) == [0.15, 2.85]
    assert len(model.by_type("IfcRoof")) == len(twin.blocks)
    slabs = model.by_type("IfcSlab")
    assert sum(s.PredefinedType == "FLOOR" for s in slabs) == len(twin.blocks)
    assert sum(s.PredefinedType == "ROOF" for s in slabs) == len(twin.blocks)
    assert len(model.by_type("IfcWindow")) + len(model.by_type("IfcDoor")) == len(twin.openings)
    assert len(model.by_type("IfcOpeningElement")) == 0  # no voids (declared omission)
    assert len(model.by_type("IfcTriangulatedFaceSet")) == len(twin.blocks)

    units = model.by_type("IfcUnitAssignment")[0].Units
    length = [u for u in units if u.is_a("IfcSIUnit") and u.UnitType == "LENGTHUNIT"][0]
    assert length.Name == "METRE" and length.Prefix is None

    building = model.by_type("IfcBuilding")[0]
    pset = ue.get_psets(building)[INFORMATION_PSET]
    assert pset["InformationLevel"] == IFC_INFORMATION_LEVEL
    assert "opening voids" in pset["Omissions"].lower() and "structural" in pset["Omissions"].lower()
    assert pset["SourceTwinId"] == twin.twin_id and pset["SourceTwinVersion"] == twin.version
    assert pset["SourceTwinHash"] == twin_hash(twin)
    counts = provenance_counts(twin)
    assert pset["ObservedParameters"] == counts["observed"] > 0
    assert pset["AssumedParameters"] == counts["assumed"] > 0
    assert pset["InferredParameters"] == counts["inferred"] > 0
    assert pset["UserConfirmedParameters"] == counts["user_confirmed"]
    assert report.information_level == IFC_INFORMATION_LEVEL and report.omissions
    assert report.source_twin == {"id": twin.twin_id, "version": twin.version, "hash": twin_hash(twin)}

    # walls never claim to be load-bearing; assemblies are named hypotheses
    wall = model.by_type("IfcWall")[0]
    wpsets = ue.get_psets(wall)
    assert wpsets["Pset_WallCommon"]["IsExternal"] is True
    assert "LoadBearing" not in wpsets["Pset_WallCommon"]
    assert wpsets["Aureom_Construction"]["AssemblyId"] == twin.assemblies.external_wall
    assert wpsets["Aureom_Construction"]["SelectionBasis"] == "assumed"
    # rule-generated openings say so
    rule = [o for o in twin.openings if o.hidden_side_rule]
    assert rule
    el = [e for e in model.by_type("IfcWindow") + model.by_type("IfcDoor")
          if ue.get_psets(e)["Aureom_Provenance"]["OpeningId"] == rule[0].opening_id][0]
    assert ue.get_psets(el)["Aureom_Provenance"]["GeometryBasis"] == "assumed"

    # deterministic GlobalIds across exports
    report2 = export_ifc(twin, boq.geometry, tmp_path / "again.ifc", library=LIB)
    model2 = ifcopenshell.open(report2.path)
    assert {e.GlobalId for e in model.by_type("IfcRoot")} == {e.GlobalId for e in model2.by_type("IfcRoot")}


def test_ifc_geometry_placement(tmp_path, twin, boq):
    ifcopenshell = pytest.importorskip("ifcopenshell")
    try:
        import ifcopenshell.geom
    except Exception:  # pragma: no cover - geometry kernel not built
        pytest.skip("ifcopenshell.geom unavailable")
    path = tmp_path / "geom.ifc"
    export_ifc(twin, boq.geometry, path, library=LIB)
    model = ifcopenshell.open(str(path))
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)

    def bbox(name):
        el = [e for e in model.by_type("IfcProduct") if e.Name == name][0]
        v = np.array(ifcopenshell.geom.create_shape(settings, el).geometry.verts).reshape(-1, 3)
        return v.min(0), v.max(0)

    t_ext = LIB.assembly(twin.assemblies.external_wall).total_thickness_m
    lo, hi = bbox("External wall main:front:0")
    assert np.allclose(lo, [0.0, 0.0, 0.15], atol=1e-6) and np.allclose(hi, [9.6, t_ext, 5.55], atol=1e-6)
    lo, hi = bbox("External wall main:left:0")  # traversed rear -> front, thickness inward (+x)
    assert np.allclose(lo, [0.0, 0.0, 0.15], atol=1e-6) and np.allclose(hi, [t_ext, 8.4, 5.55], atol=1e-6)
    lo, hi = bbox("Window W3")  # first floor, 1.3 m from the left end of the front wall
    assert np.allclose(lo, [1.3, -0.04, 0.15 + 2.7 + 0.9], atol=1e-6)
    assert np.allclose(hi, [2.5, 0.0, 0.15 + 2.7 + 0.9 + 1.2], atol=1e-6)
    lo, hi = bbox("Ground floor main")
    assert hi[2] == pytest.approx(0.15) and lo[2] < 0.15
    lo, hi = bbox("Roof envelope main")
    assert hi[2] == pytest.approx(max(r.ridge_height_m for r in boq.geometry.roofs if r.block_id == "main"),
                                  abs=1e-6)


def test_export_project_writes_ifc(export_dir, twin):
    pytest.importorskip("ifcopenshell")
    out, manifest = export_dir
    f = manifest.file("twin.ifc")
    assert f.format == "ifc" and manifest.ifc is not None
    assert manifest.ifc.path == "twin.ifc"
    assert f.sha256 == hashlib.sha256((out / "twin.ifc").read_bytes()).hexdigest()


def test_provenance_counts(twin):
    c = provenance_counts(twin)
    assert sum(c[k] for k in ("observed", "inferred", "user_confirmed", "assumed", "unknown")) == c["total"]
    assert c["assembly_selection_assumed"] == 11  # default selection: every choice assumed


# =============================================================================
# Persistence
# =============================================================================
def test_store_save_load_list_delete(tmp_path, project):
    db = tmp_path / "store" / "hb.db"
    with ProjectStore(db) as store:
        assert store.journal_mode == "wal"
        assert store.schema_version() == STORE_SCHEMA_VERSION
        saved = store.save_project(project)
        assert saved.updated_at >= project.updated_at and project.updated_at == project.updated_at  # input intact
        loaded = store.load_project(project.project_id)
        assert loaded == saved
        assert loaded.twin == project.twin
        other = Project(project_id="proj_b", name="'); DROP TABLE projects; --")
        store.save_project(other)
        summaries = store.list_projects()
        assert [s.project_id for s in summaries] == ["proj_b", project.project_id]  # newest first
        assert summaries[1].image_count == 1
        assert store.load_project("proj_b").name == other.name  # stored verbatim, not executed
        with pytest.raises(ProjectNotFound):
            store.load_project("x' OR '1'='1")
        # re-save keeps created_at, replaces state
        renamed = store.save_project(saved.model_copy(update={"name": "Renamed"}))
        assert store.load_project(project.project_id).name == "Renamed"
        assert renamed.created_at == saved.created_at
        assert store.delete_project("proj_b") is True
        assert store.delete_project("proj_b") is False
        assert [s.project_id for s in store.list_projects()] == [project.project_id]
    with pytest.raises(StoreError):
        store.list_projects()  # closed by the context manager
    # data persists across connections and migrations are not re-applied
    with ProjectStore(db) as again:
        assert again.load_project(project.project_id).name == "Renamed"
        rows = again.conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        assert rows == STORE_SCHEMA_VERSION


def test_store_images_and_run_log(tmp_path, project):
    with ProjectStore(tmp_path / "hb.db") as store:
        store.save_project(project)
        imgs = store.images(project.project_id)
        assert [i.sha256 for i in imgs] == [IMG_SHA]
        assert imgs[0].filename == "=front elevation.png" and imgs[0].kind == "elevation_drawing"
        assert imgs[0].stored_path == project.images[0].stored_path
        rec = store.register_image(project.images[0], project_id=project.project_id)  # idempotent
        assert rec.sha256 == IMG_SHA and len(store.images()) == 1
        with pytest.raises(ProjectNotFound):
            store.register_image(project.images[0], project_id="not_saved")

        rid = store.log_run(RunRecord(function="calculate_quantities", inputs_sha256="a" * 64,
                                      outputs_sha256="b" * 64, seed=None, versions={"engine": "x"}, note="test"),
                            project_id=project.project_id)
        rid2 = store.log_call("simulate_uncertainty", inputs={"twin": project.twin, "n": 100}, outputs=[1.0, 2.0],
                              seed=20261107, project_id=project.project_id)
        store.log_call("other", project_id="elsewhere")
        assert rid2 > rid
        runs = store.runs(project.project_id)
        assert [r.function for r in runs] == ["calculate_quantities", "simulate_uncertainty"]
        assert runs[0].to_record().versions == {"engine": "x"} and runs[0].note == "test"
        assert runs[1].seed == 20261107
        assert runs[1].inputs_sha256 == canonical_sha256({"twin": project.twin, "n": 100})
        assert runs[1].outputs_sha256 == canonical_sha256([1.0, 2.0])
        assert "engine" in runs[1].versions and "model_schema" in runs[1].versions
        assert [r.function for r in store.runs(function="other")] == ["other"]
        assert len(store.runs(limit=1)) == 1
        assert store.list_projects()[0].run_count == 2
        store.delete_project(project.project_id)
        assert store.runs(project.project_id) == []
        assert store.images(project.project_id) == []
        assert store.image(IMG_SHA) is not None  # registry kept


def test_store_rejects_invalid_state_and_newer_schema(tmp_path, project):
    db = tmp_path / "hb.db"
    with ProjectStore(db) as store:
        store.save_project(project)
        store.conn.execute("UPDATE projects SET state_json = ? WHERE project_id = ?",
                           ('{"project_id": "proj_io", "name": 5, "evil": true}', project.project_id))
        with pytest.raises(StoreError):
            store.load_project(project.project_id)
        store.conn.execute("UPDATE projects SET schema_version = '9.0.0'")
        with pytest.raises(StoreError):
            store.load_project(project.project_id)
    raw = sqlite3.connect(str(db))
    raw.execute("INSERT INTO schema_version(version, applied_at, description) VALUES (99, 'x', 'future')")
    raw.commit()
    raw.close()
    with pytest.raises(StoreError):
        ProjectStore(db)


def test_store_default_path_and_memory(tmp_path, monkeypatch, project):
    monkeypatch.setenv("HBV_DATA_DIR", str(tmp_path / "data"))
    assert default_db_path() == tmp_path / "data" / "housebuilder.db"
    with ProjectStore() as store:
        assert Path(store.path) == tmp_path / "data" / "housebuilder.db"
        assert Path(store.path).exists()
    monkeypatch.delenv("HBV_DATA_DIR")
    monkeypatch.chdir(tmp_path)
    assert default_db_path() == tmp_path / ".hbv" / "housebuilder.db"
    with ProjectStore(":memory:") as mem:
        mem.save_project(project)
        assert mem.load_project(project.project_id).project_id == project.project_id


# =============================================================================
# Optional integration with the real costing engine
# =============================================================================
def test_export_with_real_costing_engine(tmp_path, project, boq):
    try:
        from housebuilder_vision.costing import demo_rate_book, estimate_construction_cost
    except Exception:  # pragma: no cover - costing module not available
        pytest.skip("costing module not available")
    book = demo_rate_book()
    est = estimate_construction_cost(boq, book, project.cost_parameters, settings=project.settings, library=LIB)
    p = project.model_copy(update={"rate_book": book})
    m = export_project(p, tmp_path, boq=boq, estimate=est, formats=("csv",))
    costs = _read_csv(tmp_path / "costs.csv")
    assert len(costs) == len(est.lines)
    priced = [r for r in costs if r["rate_id"]]
    assert priced and all(r["price_label"] == FICTIONAL_LABEL for r in priced)
    assert all(not r["description"].startswith(("=", "+", "-", "@")) for r in costs)
    total = sum(float(r["amount"]) for r in costs)
    assert math.isclose(total, sum(ln.amount for ln in est.lines), rel_tol=1e-9, abs_tol=1e-6)
    assert any("FICTIONAL" in n for n in m.notes)
