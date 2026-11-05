"""Design-space exploration, recommendation logic and the RTL inventory scanner."""
from pathlib import Path

import pytest

from memoryflow.inspect_rtl import inspect, scan_repo, summarise, to_markdown
from memoryflow.models.explore import (BUDGETS, Budget, baseline, evaluate, joint_grid, mk, one_at_a_time,
                                       pareto, recommend)

V1 = BUDGETS["v1-assumed-40"]           # the envelope MemoryFlow v1 assumed

ROOT = Path(__file__).resolve().parents[1]


def test_evaluate_baseline_point():
    p = evaluate(baseline())
    assert p.feasible and p.total_area_mm2 > 0 and p.geomean_gops > 0
    assert set(p.area_mm2) >= {"spm_sram", "tensor", "dma", "dram_phy"}


def test_default_budget_is_the_documented_silicaflux_v_target():
    b = Budget()
    assert (b.node_nm, b.clock_hz, b.max_power_w) == (65, 200e6, 1.0) and b.name == "silicaflux-v-65"
    assert b.max_core_area_mm2 < 10.0                  # < 10 mm2 die (reduced-ASIC p.1)


def test_hbm_infeasible_at_silicaflux_v_node_but_ok_at_7nm():
    assert not evaluate(mk(baseline(), extmem="HBM3 1 stack")).feasible
    assert not evaluate(mk(baseline(V1), extmem="HBM3 1 stack"), budget=V1).feasible
    b7 = Budget(node_nm=7, max_core_area_mm2=40.0)   # HBM PHY alone is ~18 mm2
    assert evaluate(mk(baseline(b7), extmem="HBM3 1 stack"), budget=b7).feasible


def test_outstanding_depth_raises_streaming_perf():
    # v1 envelope, write acks generous so the read path is what varies
    s16 = evaluate(mk(baseline(V1), dfifo=16, wout=64), budget=V1).stream_gops
    s64 = evaluate(mk(baseline(V1), dfifo=64, wout=64), budget=V1).stream_gops
    assert s64 > 1.3 * s16


def test_write_acks_matter_when_the_write_path_binds():
    lo = evaluate(mk(baseline(V1), dfifo=64, wout=4), budget=V1).stream_gops
    hi = evaluate(mk(baseline(V1), dfifo=64, wout=32), budget=V1).stream_gops
    assert hi > 1.2 * lo


def test_one_at_a_time_covers_requested_dimensions():
    oat = one_at_a_time()
    assert set(oat) >= {"scratchpad", "banks", "bus_width", "dma_burst", "vector_lanes", "tensor_array", "extmem"}
    assert [p.cfg["spm_kib"] for p in oat["scratchpad"]] == [128, 256, 512, 1024]


def test_recommendation_is_feasible_and_pareto_sane():
    pts = joint_grid(baseline(V1), budget=V1, spm_kib=(128, 512), banks=(4, 8), width=(64, 128), dfifo=(16, 64),
                     lanes=(4, 8), tensor=((8, 8), (16, 16)), extmem=("DDR4-3200 x32", "HBM2E 1 stack"))
    assert all(p.cfg["extmem"] == "DDR4-3200 x32" for p in pts)        # no HBM PHY at 40 nm
    rec = recommend(pts)
    assert rec.recommended.feasible and rec.minimal.feasible and rec.stretch.feasible
    assert rec.recommended.geomean_gops >= 0.9 * rec.stretch.geomean_gops
    front = pareto([p for p in pts if p.feasible])
    areas = [p.total_area_mm2 for p in front]
    perfs = [p.geomean_gops for p in front]
    assert areas == sorted(areas) and perfs == sorted(perfs)
    for p in pts:
        assert all(p.lanes * 16 <= p.cfg["width"] for _ in [0]) if hasattr(p, "lanes") else True
        assert p.cfg["lanes"] * 16 <= p.cfg["width"]


def test_inventory_classifies_this_repo():
    mods, summ = inspect(ROOT)
    by = {(m.name, m.classification) for m in mods}
    assert ("sf_spm_banked", "SYNTHESIZABLE") in by
    assert ("sf_dma", "SYNTHESIZABLE") in by
    assert ("sf_macro_1rw_leaf", "BEHAVIOURAL") in by
    assert ("sf_macro_1rw_leaf", "BLACKBOX") in by
    assert ("sf_extmem_model", "BEHAVIOURAL") in by
    assert ("tb_dma", "TESTBENCH") in by
    assert "Memory controller" in summ["proposed"]
    assert "Scratchpad memory" not in summ["proposed"]


def test_inventory_on_synthetic_repo(tmp_path):
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "l2_cache.sv").write_text(
        "module l2_cache(input logic clk, output logic q);\n always_ff @(posedge clk) q <= ~q;\nendmodule\n")
    (tmp_path / "rtl" / "ddr_model.sv").write_text(
        "module ddr_model(input logic clk);\n initial begin #10; $display(\"x\"); end\nendmodule\n")
    (tmp_path / "rtl" / "sram_bb.v").write_text("(* blackbox *)\nmodule sram_macro(input clk, output [7:0] q);\nendmodule\n")
    mods = scan_repo(tmp_path)
    c = {m.name: (m.category, m.classification) for m in mods}
    assert c["l2_cache"] == ("L2 / last-level cache", "SYNTHESIZABLE")
    assert c["ddr_model"][1] == "BEHAVIOURAL"
    assert c["sram_macro"] == ("SRAM array / macro", "BLACKBOX")
    md = to_markdown(mods, str(tmp_path))
    assert "PROPOSED" in md
