"""Gate findings from tool outputs: synthesis, PDN, placement, timing, route,
reproducibility metadata, Pareto, TwinLab schema."""
import json

import pytest

from floorplanlab import metrics as M
from floorplanlab.config import load_design, load_platform
from floorplanlab.optimiser import pareto_front


def codes(fs):
    return {f.code for f in fs if f.severity == "error"}


def test_failed_synthesis_and_black_boxes():
    syn = {"total_cells": 10, "check_problems": 3, "latch_cells": 2, "latch_cell_types": {"dlhq": 2}, "warnings": []}
    assert {"CHECK_PROBLEMS", "UNEXPECTED_LATCH"} <= codes(M.synth_findings_gate2(syn))
    assert "NO_STAT" in codes(M.synth_findings_gate2({"check_problems": None}))
    d, pf = load_design("silicaflux_v"), load_platform("ihp_sg13g2")
    syn3 = {"unresolved_modules": ["sfv_sram_macro_bank"], "unknown_cell_types": {"FOO": 1},
            "macros": {"RM_IHPSG13_1P_2048x64_c2_bm_bist": 7}, "macro_instances": []}
    c = codes(M.synth_findings_gate3(syn3, d, pf))
    assert {"UNRESOLVED_BLACKBOX", "UNKNOWN_CELL", "MACRO_INVENTORY", "MACRO_PATHS"} <= c


def test_yosys_stat_parser():
    txt = """=== sub ===

   Number of cells:                  3
     AND                             2
     RAM                             1

   Chip area for module '\\sub': 110.000000

=== top ===

   Number of cells:                  2
     sub                             2
     INV                             1

   Chip area for module '\\top': 1.000000

=== design hierarchy ===

   top                               1
     sub                             2

   Number of wires:                 10
   Number of cells:                  7
     AND                             4
     INV                             1
     RAM                             2

   Chip area for top module '\\top': 221.000000
"""
    st = M.parse_yosys_stat(txt)
    assert st["total"]["cells"] == 7 and st["total"]["chip_area"] == 221.0
    std, mac = M._subtree_area(st["modules"], "top", {"RAM": 100.0}, {})
    assert mac == 200.0 and std == pytest.approx(21.0)


def test_missing_power_connections(tmp_path):
    p = tmp_path / "pdn.json"
    p.write_text(json.dumps({"nets": [{"net": "VDD", "type": "POWER", "check_rc": 1, "result": "PSM-0069",
                                       "unconnected_report": "x", "unconnected_lines": 12, "connected": 0}],
                             "macro_pg": [], "macro_pg_errors": 2,
                             "macro_pin_access": [{"inst": "m", "pin": "VDD!", "layer": "Metal4", "vias": 0, "ok": 0}],
                             "macro_pin_access_errors": 1}))
    c = codes(M.pdn_findings(p))
    assert {"PDN_DISCONNECTED", "MACRO_PG", "MACRO_PG_NO_VIA"} <= c
    assert "NO_PDN_CHECK" in codes(M.pdn_findings(tmp_path / "absent.json"))


def test_incomplete_reports():
    assert "GRT_FAILED" in codes(M.route_findings({"completed": 0}, 1))
    assert "STA_NOT_RUN" in codes(M.timing_findings({}, load_design("silicaflux_v"), __import__("pathlib").Path("/x")))
    assert "NOT_CHECKED" in codes(M.placement_findings({}))
    assert "ILLEGAL_PLACEMENT" in codes(M.placement_findings({"placement_check": {"legal": 0, "message": "overlap"}}))


def test_grt_log_parser():
    log = """[INFO GRT-0096] Final congestion report:
Layer         Resource        Demand        Usage (%)    Max H / Max V / Total Overflow
---------------------------------------------------------------------------------------
Metal2          1000           500           50.00%             0 /  2 /  2
Metal3          2000           600           30.00%             1 /  0 /  1
---------------------------------------------------------------------------------------
Total           3000          1100           36.67%             1 /  2 /  3

[INFO GRT-0018] Total wirelength: 123456 um
"""
    r = M.parse_grt_log(log)
    assert r["total"]["overflow_total"] == 3 and r["layers"]["Metal2"]["overflow_v"] == 2
    assert r["routed_wirelength_um"] == 123456


def test_unreproducible_metadata():
    class R:
        rec = {"git_revision": "", "tools": {"openroad": "MISSING"}, "netlist_sha256": None,
               "config_mk_sha256": "x", "platform": {}, "spec": {"seed": 1}}
    c = codes(M.repro_findings(R))
    assert "MISSING_METADATA" in c and "TOOL_UNKNOWN" in c
    R.rec = dict(R.rec, git_revision="abc", tools={"openroad": "2.0", "yosys": "0.38", "orfs": "ab2"},
                 netlist_sha256="n", platform={"provenance": {"x": 1}},
                 repro_check={"identical": False, "differences": ["floorplan.macros"]})
    assert "NOT_REPRODUCED" in codes(M.repro_findings(R))


def test_pareto_excludes_missing_and_dominated():
    rows = [{"run_id": "a", "x": 1, "y": 5}, {"run_id": "b", "x": 2, "y": 2}, {"run_id": "c", "x": 3, "y": 3},
            {"run_id": "d", "x": None, "y": 0}]
    assert set(pareto_front(rows, [("x", "min"), ("y", "min")])) == {"a", "b"}


def test_twinlab_schema_roundtrip(tmp_path, project):
    from floorplanlab import twinlab
    s = twinlab.write_schema(tmp_path / "schema.json")
    schema = json.loads(s.read_text())
    assert "twinlab_blocks" in schema["properties"]
    for f in sorted((project / "results").glob("*/export/twinlab_floorplan.json")) + \
            sorted((project / "reports/runs").glob("*/twinlab_floorplan.json")):
        ex = twinlab.load_export(f)
        assert ex.schema_version == twinlab.SCHEMA_VERSION
        assert all(b.dynamicPowerMw is None for b in ex.twinlab_blocks)     # never invented
        assert any(b.type == "SRAM_BANK" for b in ex.twinlab_blocks)
        break
    else:
        pytest.skip("no exported run available")
