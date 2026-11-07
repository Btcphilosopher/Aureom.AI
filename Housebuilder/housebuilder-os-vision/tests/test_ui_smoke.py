"""Smoke tests for the Streamlit UI (``app.py`` / ``housebuilder_vision.ui``).

* AppTest runs the real script: start page, fictional demo, all five tabs, a twin edit that
  changes the cost, and a small uncertainty simulation - without exceptions or error boxes.
* Bare-mode tests exercise the UI state layer and chart builders directly (feature rejection
  re-runs the analysis, annotation validation, display-unit conversion, figure construction).

Skipped gracefully when ``streamlit.testing`` (AppTest) is unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1", reason="Streamlit AppTest is not available")
AppTest = st_testing.AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
TABS = ("Images", "Twin", "Quantities", "Costs", "Scenarios")


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HBV_DATA_DIR", str(tmp_path / "hbv"))
    monkeypatch.delenv("HBV_ENABLE_VLM", raising=False)
    logging.getLogger("streamlit").setLevel(logging.ERROR)


def _app() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=180)
    at.run()
    return at


def _no_errors(at: AppTest, where: str) -> None:
    assert not at.exception, f"{where}: {[e.value for e in at.exception]}"
    errs = [e.value for e in at.error]
    assert not errs, f"{where}: error boxes {errs}"


def _ws(at: AppTest):
    return at.session_state["hbv_workspace"]


def _load_demo(at: AppTest) -> None:
    at.button(key="load_demo").click().run()
    _no_errors(at, "load demo")


# =============================================================================
# AppTest (real script)
# =============================================================================
def test_start_page_has_demo_button_and_no_errors():
    at = _app()
    _no_errors(at, "start")
    assert any(b.label == "Load fictional demo" for b in at.button)
    assert [t.label for t in at.tabs][:5] == list(TABS)


def test_demo_all_tabs_edit_and_simulation():
    at = _app()
    _load_demo(at)
    ws = _ws(at)
    assert ws.project is not None and ws.project.twin is not None
    assert ws.cur_kpis and ws.cur_kpis["construction"] > 0
    for tab in TABS:
        at.session_state["main_tab"] = tab
        at.run()
        _no_errors(at, tab)
    # basis legend / badges are rendered with their text labels (colour is never the only cue)
    at.session_state["main_tab"] = "Images"
    at.run()
    page_html = " ".join(str(getattr(h, "proto", "")) for h in at.get("html"))
    assert "USER-CONFIRMED" in page_html.upper() and "hbv-badge" in page_html

    # one edit: main block depth -> numbers change immediately
    at.session_state["main_tab"] = "Twin"
    at.run()
    depth = [n for n in at.number_input if str(n.key or "").endswith("_main_d")]
    assert depth, "main-block depth editor not found"
    before = dict(_ws(at).cur_kpis)
    depth[0].set_value(9.2).run()
    _no_errors(at, "after depth edit")
    ws = _ws(at)
    main = ws.project.twin.block("main")
    assert main.depth.value == pytest.approx(9.2)
    assert main.depth.basis.value == "user_confirmed"
    assert ws.cur_kpis["construction"] != pytest.approx(before["construction"])
    assert ws.cur_kpis["gia_m2"] > before["gia_m2"]

    # a small uncertainty simulation from the Costs tab
    at.session_state["main_tab"] = "Costs"
    at.run()
    samples = [n for n in at.number_input if n.label == "Samples"]
    assert samples
    samples[0].set_value(40)
    run_btn = [b for b in at.button if b.label == "Run simulation"]
    assert run_btn
    run_btn[0].click().run()
    _no_errors(at, "after simulation")
    sim = _ws(at).simulation
    assert sim is not None and sim.n_samples == 40
    assert "not statistically calibrated" in sim.interval_type or "not confidence" in sim.interval_type

    # scenarios still render after edits
    at.session_state["main_tab"] = "Scenarios"
    at.run()
    _no_errors(at, "scenarios after edit")


# =============================================================================
# Bare-mode state and chart tests
# =============================================================================
@pytest.fixture(scope="module")
def demo_ws(tmp_path_factory):
    import os

    from housebuilder_vision.ui import state as S

    old = os.environ.get("HBV_DATA_DIR")
    os.environ["HBV_DATA_DIR"] = str(tmp_path_factory.mktemp("hbv-bare"))
    try:
        ws = S.Workspace(store_dir=str(S.image_store_dir()))
        S.load_demo(ws)
        yield ws
    finally:
        if old is None:
            os.environ.pop("HBV_DATA_DIR", None)
        else:
            os.environ["HBV_DATA_DIR"] = old


def test_reject_and_restore_feature_reruns_analysis(demo_ws):
    from housebuilder_vision.ui import state as S

    ws = demo_ws
    a = ws.project.analysis
    img = a.analyses[0].image_id
    n_open = sum(len(f.openings) for f in a.facades)
    win = next(f for f in a.analyses[0].features if f.feature_type.value == "window" and f.active)
    S.set_feature_active(ws, img, win, False)
    a2 = ws.project.analysis
    assert sum(len(f.openings) for f in a2.facades) == n_open - 1
    rejected = next(f for f in a2.analyses[0].features if f.feature_id == win.feature_id)
    assert not rejected.active and any(h.reason == S.UI_REJECT_REASON for h in rejected.history)
    assert S.manual_from_analysis(a2)[img][0].feature_id == win.feature_id
    S.set_feature_active(ws, img, rejected, True)
    assert sum(len(f.openings) for f in ws.project.analysis.facades) == n_open
    assert S.twin_status(ws) == "ok"  # twin without geometry edits follows the evidence


def test_annotation_rows_are_validated(demo_ws):
    from housebuilder_vision.ui import state as S

    asset = demo_ws.project.images[0]
    feats, errors = S.annotations_to_features(asset, [
        {"type": "window", "x0": 100, "y0": 120, "x1": 40, "y1": 200, "storey": 0, "block": "main"},
        {"type": "eaves_line", "x0": 10, "y0": 300, "x1": 900, "y1": 300},
        {"type": "window", "x0": 1e9, "y0": 0, "x1": 2e9, "y1": 10},
        {"type": "not-a-type", "x0": 1, "y0": 1, "x1": 2, "y1": 2},
        {"type": "door", "x0": 10, "y0": 10, "x1": 20, "y1": 30, "storey": 1.5},
    ])
    assert len(feats) == 2 and len(errors) == 3
    win, eaves = feats
    assert win.bbox == (40, 120, 100, 200) and win.basis.value == "user_confirmed"
    assert win.method == S.UI_ANNOTATION_METHOD and win.attributes == {"block": "main", "storey": 0}
    assert eaves.line == (10, 300, 900, 300) and eaves.bbox is None
    assert any("outside the image" in e for e in errors)


def test_evaluation_is_cached_and_edit_reports_errors(demo_ws):
    from housebuilder_vision.core.models import TwinEdit
    from housebuilder_vision.ui import state as S

    ws = demo_ws
    ev1 = S.evaluate(ws)
    ev2 = S.evaluate(ws)
    assert ev1.key == ev2.key
    assert ev1.estimate.boundary("construction_incl_contingency").amount > 0
    err = S.edit_twin(ws, TwinEdit(target_type="block", target_id="main", field="width", value=-3))
    assert err and "not applied" in err
    err2 = S.set_assembly(ws, "external_wall", "no_such_assembly")
    assert err2 and "Assembly not applied" in err2


def test_display_units_round_trip():
    from housebuilder_vision.ui import fmt

    v, u = fmt.disp(9.6, "m", "imperial")
    assert u == "ft" and v == pytest.approx(31.496, rel=1e-4)
    assert fmt.to_si(v, u, "m") == pytest.approx(9.6)
    assert fmt.disp(10.0, "nr", "imperial") == (10.0, "nr")
    assert fmt.money(233184.4, "GBP") == "£233,184"
    assert fmt.money(float("nan")) == "–"


def test_chart_builders(demo_ws):
    from housebuilder_vision.twin.mesh import build_mesh, scene_to_plotly_meshes
    from housebuilder_vision.ui import charts, state as S
    from housebuilder_vision.ui.theme import BASIS_COLOURS

    ws = demo_ws
    ev = S.evaluate(ws)
    twin = ws.project.twin
    asset = ws.project.images[0]
    feats = ws.project.analysis.analyses[0].features
    fig = charts.overlay_figure(asset.width_px, asset.height_px, feats)
    assert len(fig.data) >= 10 and fig.layout.yaxis.range[0] == asset.height_px
    meshes = scene_to_plotly_meshes(build_mesh(twin))
    wall_line = next(ln for ln in ev.boq.lines if ln.element_code == "2.5" and ln.geometry_refs)
    hl = charts.resolve_refs(twin, ev.boq.geometry, wall_line.geometry_refs)
    assert hl["pieces"] and not hl["other"]
    f3 = charts.twin_figure(meshes, twin, highlight=hl, metrics=ev.boq.geometry)
    assert any(getattr(t, "name", "") == "referenced geometry" for t in f3.data)
    fb = charts.twin_figure(meshes, twin, mode="basis")
    colours = {t.color for t in fb.data if t.type == "mesh3d" and t.name != "ground"}
    assert colours <= set(BASIS_COLOURS.values())
    assert charts.layer_waterfall(ev.estimate).data
    assert charts.gantt(ev.programme).data
    assert charts.carbon_chart(ev.carbon).data and charts.heat_loss_chart(ev.heat_loss).data
    res = S.repeat_results(ws, ev, ws.project.production_scenarios[1])
    assert set(res) == {"factory_gate", "installed"}
    assert charts.repeat_chart(res).data
    comp = S.compare_scenarios(ws)
    assert len(comp.outcomes) == len(ws.project.build_scenarios)
    assert charts.scenario_multiples(comp.outcomes, "GBP").data
    xs = [100.0 + i for i in range(50)]
    assert charts.histogram_cdf(xs, p10=105, p50=125, p90=145, deterministic=120, currency="GBP").data


def test_basis_palette_is_distinct_and_labelled():
    from housebuilder_vision.core.provenance import Basis
    from housebuilder_vision.ui.theme import BASIS_COLOURS, BASIS_DASH, badge

    assert set(BASIS_COLOURS) == set(Basis) and len(set(BASIS_COLOURS.values())) == len(Basis)
    assert set(BASIS_DASH) == set(Basis)
    for b in Basis:
        assert b.value.replace("_", "-").split("-")[0].lower() in badge(b).lower() or "assumption" in badge(b).lower()
    assert "&lt;script&gt;" in badge(Basis.ASSUMED, label="<script>")


def test_streamlit_config_hides_tracebacks_and_sets_theme():
    import tomllib

    cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())
    assert cfg["client"]["showErrorDetails"] == "none"
    assert cfg["theme"]["base"] == "dark" and cfg["theme"]["primaryColor"].upper() == "#B39A62"
    assert cfg["server"]["maxUploadSize"] == 25


def test_ui_imports_no_optional_dependencies():
    import subprocess
    import sys

    code = ("import sys; import housebuilder_vision.ui.state, housebuilder_vision.ui.charts, "
            "housebuilder_vision.ui.views; bad = [m for m in ('cv2', 'ifcopenshell', 'anthropic', 'transformers', "
            "'torch') if m in sys.modules]; print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
