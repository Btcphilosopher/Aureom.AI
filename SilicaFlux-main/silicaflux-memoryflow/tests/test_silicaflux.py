"""Repository-evidence layer: sources, HDL parsing, inventory, documented targets,
characterisation of the existing SilicaFlux RTL, baselines - and the v2 model terms
(block tensor dataflow, result drain, DMA write path, budgets, tiles, balance)."""
import math
import os
import shutil
from pathlib import Path

import pytest

from conftest import needs_verilator
from memoryflow.models.balance import cpu_orchestration, kernel_balance, machine_balance
from memoryflow.models.dma import dma_write_bw
from memoryflow.models.explore import BUDGETS, baseline, evaluate, joint_grid, mk
from memoryflow.models.hardware import ComputeConfig, SystemConfig
from memoryflow.models.roofline import Roofline
from memoryflow.models.workloads import Gemm, VecAdd, default_suite
from memoryflow.silicaflux import hdl
from memoryflow.silicaflux.sources import silicaflux_root

HAVE_SF = silicaflux_root() is not None
needs_sf = pytest.mark.skipif(not HAVE_SF, reason="SilicaFlux sources not next to this checkout")


# ------------------------------------------------------------------ HDL parser (synthetic)
SYN = """
package p_pkg; typedef logic [7:0] sf_byte_t; endpackage
module leaf #(parameter int W = 8) (input logic clk, input logic [W-1:0] d, output logic [W-1:0] q);
  always_ff @(posedge clk) q <= d;
endmodule
module top import p_pkg::*; (input logic clk, output sf_byte_t o, output sf_missing_t m);
  logic [7:0] a;
  end_of_line_keyword_check: assert property (@(posedge clk) 1);
  leaf #(.W(8)) u_ok (.clk(clk), .d(a), .q(o));
  leaf #(.WIDTH(8)) u_drift (.clk(clk), .din(a), .q());
  ghost u_ghost (.clk(clk));
  assign a = f(o);
endmodule
"""


def test_hdl_parser_on_synthetic_source(tmp_path):
    f = tmp_path / "syn.sv"
    f.write_text(SYN)
    mods, pkgs = hdl.parse_file(f, "syn.sv", "syn.sv")
    m = {x.name: x for x in mods}
    assert m["leaf"].params == ["W"] and m["leaf"].ports == ["clk", "d", "q"]
    insts = {i.name: i for i in m["top"].instances}
    assert set(insts) == {"u_ok", "u_drift", "u_ghost"}          # f(o) is not an instance
    assert insts["u_drift"].params == ["WIDTH"] and "din" in insts["u_drift"].ports
    assert pkgs[0].types == {"sf_byte_t"}
    assert {"sf_byte_t", "sf_missing_t"} <= m["top"].used_types


def test_static_checks_find_missing_definition_drift_and_types(tmp_path):
    from memoryflow.silicaflux import inventory as inv
    f = tmp_path / "syn.sv"
    f.write_text(SYN)
    mods, pkgs = hdl.parse_file(f, "syn.sv", "syn.sv")
    ix = inv.Index({})
    for md in mods:
        ix.modules[md.name].append(md)
        ix.set_of[md.file] = "sf25"
    ix.packages["sf25"] = pkgs
    kinds = {(x.kind, x.module) for x in inv.static_checks(ix)}
    assert ("REFERENCED_ONLY", "top") in kinds
    assert ("INTERFACE_DRIFT", "top") in kinds
    assert ("MISSING_TYPES", "top") in kinds


# ------------------------------------------------------------------ real repository
@needs_sf
def test_sources_extract_with_provenance():
    from memoryflow.silicaflux.sources import find_file, materialise
    m = materialise("sf25")
    f = find_file(m, "SilicaFlux2.0/SilicaFlux2.5/memory_controller.sf")
    assert len(f.sha256) == 64 and f.lines > 1000
    g = materialise("sf1")
    assert any(x.origin == "silicaflux.zip::silicaflux/rtl/memory_controller.sv" for x in g.files)


@needs_sf
def test_inventory_static_evidence():
    from memoryflow.silicaflux import inventory as inv
    res = inv.run(lint=False)
    assert res["available"] and res["files"] > 200
    missing = [(b["block"]["name"], a["what"]) for b in res["blocks"] for a in b["anchors"] if not a["found"]]
    assert not missing, f"evidence anchors no longer resolve: {missing}"
    det = [(f["kind"], f["module"], f["detail"]) for f in res["findings"]]
    assert any(k == "REFERENCED_ONLY" and m == "silicaflux_top" and "sf_l2_cache" in d for k, m, d in det)
    assert any(k == "INTERFACE_DRIFT" and m == "compute_tile" and "memory_controller" in d for k, m, d in det)
    assert any(k == "MISSING_TYPES" and m == "compute_tile" for k, m, _ in det)
    cats = {b["block"]["category"] for b in res["blocks"]}
    assert set(inv.CATEGORIES) <= cats                         # all ten (+2) categories covered


@needs_sf
@needs_verilator
def test_inventory_claims_agree_with_elaboration():
    from memoryflow.silicaflux import inventory as inv
    res = inv.run(lint=True)
    contradictions = [b["block"]["name"] for b in res["blocks"] if b["note"].startswith("curated as")]
    assert not contradictions, contradictions
    st = {b["block"]["name"]: (b["status"], b["lint_ok"]) for b in res["blocks"]}
    assert st["Gen-2.5 banked scratchpad controller"] == ("IMPLEMENTED", True)
    assert st["Gen-2.5 pipelined tensor unit (4x4x4 INT8 / cycle)"] == ("IMPLEMENTED", True)
    assert st["Tile-local crossbar (compute_tile.sf)"] == ("NOT_ELABORABLE", False)
    assert st["Gen-1 per-tile scratchpad (4 x 1 KiB)"][1] is True


@needs_sf
@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext not installed")
def test_documented_quotes_are_on_the_cited_pages():
    from memoryflow.silicaflux.doc_targets import verify_quotes
    res = verify_quotes()
    bad = [k for k, v in res.items() if v is False]
    assert not bad, f"quotes not found on their cited page: {bad}"


@needs_sf
@needs_verilator
@pytest.mark.rtl
@pytest.mark.parametrize("name", ["sf1_memctrl", "sf25_dma_bridge"] +
                         (["sf25_memctrl", "sf25_tensor", "sf1_tensor"] if os.environ.get("MF_FULL_RTL") else []))
def test_characterisation_of_existing_rtl(name, tmp_path):
    from memoryflow.silicaflux.characterise import CHAR_TBS, run_char
    r = run_char(CHAR_TBS[name], tmp_path)
    assert r.ok, f"{name}: {r.status} (expected {r.expected}) errors={r.errors}; log {r.log_path}"
    if name == "sf1_memctrl":
        assert r.metrics["sf1_dfstore8_words_not_written"] == 4
    if name == "sf25_dma_bridge":
        # Little's law on write acks (8 outstanding, 20-cycle memory) within 2 %
        assert r.metrics["sf25_dma_spm_to_ext_bytes_per_cycle"] == pytest.approx(dma_write_bw(16, 1, 20, 8, 0),
                                                                                    rel=0.02)
        assert r.metrics["sf25_bridge_strobe_errors"] == 1


def test_baselines_rank_as_expected():
    from memoryflow.silicaflux.baselines import all_baselines, evaluate_baseline
    pts = {b.key: (b, evaluate_baseline(b)) for b in all_baselines()}
    for k, (b, p) in pts.items():
        assert p.feasible, (k, p.reasons)
    b, p = pts["sf25_int"]
    g = next(k for k in p.perf if k.startswith("GEMM 512"))
    assert p.bound[g] in ("spm", "drain")                     # starved, not compute bound
    assert p.perf[g] < 0.2 * Roofline(b.cfg).peak("tensor")
    assert pts["sfv_doc_dram"][1].geomean_gops > 3 * pts["sfv_doc"][1].geomean_gops   # no-DRAM penalty
    rec = evaluate(mk(baseline(), 128, 4, 128, 16, 16, 8, (16, 16), "DDR3-1600 x16"))
    assert rec.dense_gops > 10 * p.dense_gops


# ------------------------------------------------------------------ v2 model terms
def test_block_tensor_traffic_and_drain_ceiling():
    c = ComputeConfig(clock_hz=200e6, tensor_rows=4, tensor_cols=4, tensor_depth=4, tensor_dataflow="block",
                      tensor_drain_bytes_per_cycle=16.0)
    cfg = SystemConfig(compute=c, node_nm=65)
    g = Gemm(64, 64, 64)
    blocks = 64 ** 3 / 64
    assert g.onchip_bytes(cfg) == pytest.approx(blocks * (16 + 16 + 2 * 16 * 4))
    assert c.tensor_macs_per_cycle == 64
    pt = Roofline(cfg).evaluate(g)
    drain = g.ops / g.result_bytes(cfg) * 16 * 200e6
    assert pt.perf <= drain * 1.0001


def test_phy_must_exist_at_the_node_even_for_full_chip_budgets():
    b = BUDGETS["full-28"]
    assert not evaluate(mk(baseline(b), extmem="HBM2E 1 stack"), budget=b).feasible
    assert evaluate(mk(baseline(BUDGETS["full-16"]), extmem="HBM2E 1 stack", tiles=8),
                    budget=BUDGETS["full-16"]).feasible


def test_130nm_cannot_hold_the_documented_256kib():
    b = BUDGETS["silicaflux-v-130"]
    pts = joint_grid(baseline(b), budget=b, spm_kib=(128, 256), banks=(4,), width=(64,), dfifo=(16,),
                     lanes=(4,), tensor=((4, 4),))
    assert any(p.feasible for p in pts if p.cfg["spm_kib"] == 128)
    assert not any(p.feasible for p in pts if p.cfg["spm_kib"] == 256)


def test_tiles_scale_peaks_and_area_not_the_phy():
    b = BUDGETS["full-28"]
    one, eight = mk(baseline(b), tiles=1), mk(baseline(b), tiles=8)
    assert Roofline(eight).peak("tensor") == pytest.approx(8 * Roofline(one).peak("tensor"))
    a1, a8 = evaluate(one, budget=b).area_mm2, evaluate(eight, budget=b).area_mm2
    assert a8["spm_sram"] == pytest.approx(8 * a1["spm_sram"]) and a8["dram_phy"] == a1["dram_phy"]


def test_balance_and_cpu_orchestration():
    cfg = baseline()
    mb = machine_balance(cfg, default_suite())
    assert sum(mb.bound_share.values()) == pytest.approx(1.0)
    assert all(k.headroom >= 1.0 for k in mb.kernels)
    kb = kernel_balance(cfg, VecAdd(1 << 20))
    assert kb.bound in ("dram", "dma") and kb.ai_dram == pytest.approx(1 / 6, rel=1e-6)
    cl = cpu_orchestration(cfg, Gemm(512, 512, 512))
    assert cl.cpu_busy > 0 and math.isfinite(cl.max_tiles_per_core)


@needs_sf
def test_cli_sf_inventory(capsys):
    from memoryflow.cli import main
    assert main(["sf-inventory", "--no-lint"]) == 0
    assert "REFERENCED_ONLY" in capsys.readouterr().out
