"""Cross-module hooks wired after the second review round."""

import json

from housebuilder_vision.core.models import Basis, TwinEdit
from housebuilder_vision.demo.build_demo import build_demo_project
from housebuilder_vision.io.export import export_project
from housebuilder_vision.quantities.takeoff import calculate_quantities
from housebuilder_vision.simulation import combined_information_value, scenario_spread_entries
from housebuilder_vision.twin.builder import apply_twin_edit


def _demo(tmp_path):
    return build_demo_project(tmp_path / "store")


def test_confirmed_edit_is_user_confirmed_with_tolerance(tmp_path):
    p = _demo(tmp_path)
    main = p.twin.block("main")
    assert (main.depth.correlation_group or "").startswith("scale:") or main.depth.basis != Basis.USER_CONFIRMED
    t2 = apply_twin_edit(p.twin, TwinEdit(target_type="block", target_id="main", field="depth", value=9.0,
                                          tolerance=0.05))
    d = t2.block("main").depth
    assert d.basis == Basis.USER_CONFIRMED
    assert d.low == 8.95 and d.high == 9.05
    # (the simulator samples USER_CONFIRMED values independently of the image scale -
    #  covered by tests/test_review2_e_uncertainty.py::test_unc4_*)


def test_unmodelled_elements_become_unresolved_lines(tmp_path):
    p = _demo(tmp_path)
    twin = p.twin.model_copy(update={"unmodelled_elements": ["balcony on front facade (feature f1)"]})
    boq = calculate_quantities(twin, p.library)
    lines = [ln for ln in boq.lines if ln.line_id.startswith("9.unmodelled.")]
    assert len(lines) == 1
    ln = lines[0]
    assert ln.status.value == "unresolved" and ln.installed_qty is None and ln.trace
    assert len({ln.line_id for ln in boq.lines}) == len(boq.lines)


def test_export_does_not_carry_absolute_image_paths(tmp_path):
    p = _demo(tmp_path)
    export_project(p, tmp_path / "out", formats=("json",))
    data = json.loads((tmp_path / "out" / "project.json").read_text())
    for im in data["images"]:
        assert im["stored_path"] is None or "/" not in im["stored_path"]
        assert im["stored_path"] is None or im["stored_path"].startswith(im["sha256"])


def test_scenario_spread_hook(tmp_path):
    from housebuilder_vision.pipeline import compare_build_scenarios

    p = _demo(tmp_path)
    comp = compare_build_scenarios(p.twin, p.hypotheses, p.build_scenarios, p.library, p.rate_book,
                                   p.cost_parameters, p.settings)
    entries = scenario_spread_entries(comp, currency="GBP")
    dims = {e["dimension"] for e in entries}
    assert "construction" in dims and "hypothesis" in dims
    combined = combined_information_value(None, comp)
    assert [e["combined_rank"] for e in combined] == list(range(1, len(combined) + 1))
