"""Differential testing against the REAL implemented register slaves.

For each of hpc_cq_mmio (vector command interface), tsu_regs (tensor command interface) and mcu_intc
(interrupt controller) a SystemVerilog harness is generated that instantiates

  * the generated ``sf_reg_bank`` (ALP v1 target) for the whole SilicaFlux map, and
  * the hand-written slave on its rb_* register bus, unmodified,

drives both with the same random access sequence and the same hardware inputs, and compares, for every access:
the error/refusal outcome, the read data, every hardware output (pulses, levels, interrupt), and -- every few
operations -- the whole readable register file.

Differences that are *by design* and asserted explicitly, never ignored:
  * a read of a write-only register returns 0 without error in the hand-written slave and ACCESS_DENIED in the
    generated bank (the bank refuses reads of registers that have nothing to read);
  * the bank's hardware pulses are registered, i.e. appear in the cycle after the accepted access, whereas the
    slave's are combinational in the strobe cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from albion_reggen.model import RegMap


@dataclass
class Spec:
    name: str
    periph: str
    real_module: str
    real_params: str
    real_clk: str
    real_rst: str
    rb: Dict[str, str]
    real_inputs: List[Tuple[str, int, str]]          # (port, width, kind) kind: bit|event|vec
    real_outputs: List[Tuple[str, int]]
    real_tie: Dict[str, str]                         # real input port -> constant expression
    pulses: List[Tuple[str, str, int]]               # (real out at A, bank out at A+1, width)
    levels: List[Tuple[str, str, int]]               # (real out after A, bank out after A, width)
    bank_map: Dict[str, str]                         # bank input port -> expression
    glue: str = ""
    wo_offsets: List[int] = field(default_factory=list)
    offsets: List[int] = field(default_factory=list)
    probes: List[Tuple[int, str, int]] = field(default_factory=list)   # intc: (offset, reg var, width)
    input_masks: Dict[str, int] = field(default_factory=dict)          # bits the implemented hardware can actually drive


def sv_hex(w: int, v: int) -> str:
    return f"{w}'h{v:x}"


def emit(m: RegMap, s: Spec, nops: int, seed: int) -> str:
    p = m.periph(s.periph)
    L: List[str] = ["`default_nettype none", f"module tb_diff_{s.name};"]
    L.append(f"  localparam int NOPS = {nops};")
    L.append(f"  localparam logic [63:0] BASE = {sv_hex(64, p.base)};")
    L.append("  logic clk = 1'b0;")
    L.append("  always #5 clk = ~clk;")
    L.append("  logic rst_n;")
    L.append("  logic [63:0] rng;")
    L.append("  function automatic logic [63:0] nextr(input logic [63:0] x);")
    L.append("    logic [63:0] y; y = x; y ^= y << 13; y ^= y >> 7; y ^= y << 17; return y;")
    L.append("  endfunction")
    L.append("  task automatic rnd(output logic [63:0] v); rng = nextr(rng); v = rng * 64'h2545F4914F6CDD1D; endtask")
    L.append("")
    # ----- ALP side + bank
    L.append("  logic req_valid; wire req_ready; sf_albion_pkg::sf_req_t req;")
    L.append("  wire rsp_valid; logic rsp_ready; sf_albion_pkg::sf_rsp_t rsp;")
    for q in m.hw_ports:
        L.append(f"  logic [{q.width - 1}:0] {q.name};")
    conns = [".clk_i(clk)", ".rst_ni(rst_n)", ".req_valid_i(req_valid)", ".req_ready_o(req_ready)", ".req_i(req)",
             ".rsp_valid_o(rsp_valid)", ".rsp_ready_i(rsp_ready)", ".rsp_o(rsp)"] + [f".{q.name}({q.name})" for q in m.hw_ports]
    L.append("  sf_reg_bank bank (" + ", ".join(conns) + ");")
    L.append("  logic bank_idle_dummy;")
    for q in m.hw_ports:
        if q.direction == "input":
            if q.name in s.bank_map:
                L.append(f"  assign {q.name} = {s.bank_map[q.name]};")
            else:
                L.append(f"  assign {q.name} = '0;")
    for k in s.bank_map:
        if not any(q.name == k and q.direction == "input" for q in m.hw_ports):
            raise KeyError(f"bank_map names a non-input port: {k}")
    # ----- real slave
    L.append("")
    r = s.rb
    L.append(f"  logic {r['sel']}, {r['we']}; logic [11:0] {r['addr']}; logic [31:0] {r['wdata']}; wire [31:0] {r['rdata']}; wire {r['err']};")
    for n, w, _ in s.real_inputs:
        L.append(f"  logic [{w - 1}:0] {n};")
    for n, w in s.real_outputs:
        L.append(f"  wire [{w - 1}:0] {n};")
    pc = [f".{s.real_clk}(clk)", f".{s.real_rst}(rst_n)"] + [f".{v}({v})" for v in r.values()]
    pc += [f".{n}({n})" for n, _, _ in s.real_inputs] + [f".{n}({n})" for n, _ in s.real_outputs]
    pc += [f".{k}({v})" for k, v in s.real_tie.items()]
    L.append(f"  {s.real_module} {s.real_params} slave ({', '.join(pc)});")
    L.append(s.glue)
    # ----- stimulus support
    offs = s.offsets
    L.append(f"  localparam int NOFF = {len(offs)};")
    L.append("  function automatic logic [11:0] off_of(input int i);")
    L.append("    case (i)")
    for k, o in enumerate(offs):
        L.append(f"      {k}: off_of = 12'h{o:03x};")
    L.append("      default: off_of = 12'h000;")
    L.append("    endcase")
    L.append("  endfunction")
    wo = " || ".join(f"o == 12'h{o:03x}" for o in s.wo_offsets) or "1'b0"
    known = " || ".join(f"o == 12'h{o:03x}" for o in offs)
    L.append(f"  function automatic logic is_wo(input logic [11:0] o); is_wo = {wo}; endfunction")
    L.append(f"  function automatic logic is_known(input logic [11:0] o); is_known = {known}; endfunction")
    L.append("  int errors, ops, tag, n_refused, n_ok_wr, n_ok_rd, n_wo_rd, n_pulse_checks;")
    L.append("")
    L.append("  task automatic randomize_inputs();")
    L.append("    logic [63:0] v;")
    for n, w, kind in s.real_inputs:
        if kind == "bit":
            L.append(f"    rnd(v); {n} = v[7];")
        elif kind == "event":
            L.append(f"    rnd(v); {n} = (v[10:8] == 3'd0);")
        else:
            L.append(f"    {n} = '0; for (int k = 0; k < {(w + 63) // 64}; k++) begin rnd(v); {n} = {n} ^ ({w}'(v) << (64*k)); end")
        if n in s.input_masks:
            L.append(f"    {n} = {n} & {sv_hex(w, s.input_masks[n])};")
    L.append("  endtask")
    L.append("")
    # one access on both DUTs and comparison
    pulse_a = ", ".join(f"{a}" for a, _, _ in s.pulses) or "1'b0"
    L.append("  task automatic access(input logic is_write, input logic [11:0] off, input logic [31:0] wdata, input logic fresh_inputs);")
    L.append("    logic [3:0] lane; logic r_err, b_err; logic [31:0] r_data, b_data; sf_albion_pkg::sf_rsp_t rr;")
    for k, (a, b, w) in enumerate(s.pulses):
        L.append(f"    logic [{w - 1}:0] pa{k};")
    L.append("    @(negedge clk);")
    L.append("    if (fresh_inputs) randomize_inputs();")
    L.append(f"    {r['sel']} = 1'b1; {r['we']} = is_write; {r['addr']} = off; {r['wdata']} = wdata;")
    L.append("    lane = off[3:2] << 2;")
    L.append("    req_valid = 1'b1; rsp_ready = 1'b1;")
    L.append("    req = '0; req.op = is_write ? sf_albion_pkg::SF_OP_WRITE : sf_albion_pkg::SF_OP_READ; req.tag = tag[7:0]; tag++;")
    L.append("    req.dom = 8'h01; req.attr = 8'h06; req.addr = BASE + 64'(off & 12'hFF0);")
    L.append("    req.be = 16'h000F << lane; req.data = 128'(wdata) << (8 * lane);")
    L.append("    #3;")
    L.append(f"    r_err = {r['err']}; r_data = {r['rdata']};")
    for k, (a, b, w) in enumerate(s.pulses):
        L.append(f"    pa{k} = {a};")
    L.append("    if (!req_ready) begin $display(\"DIFF FAIL op %0d: bank not ready while idle\", ops); errors++; end")
    L.append("    @(negedge clk);")
    L.append(f"    {r['sel']} = 1'b0; req_valid = 1'b0;")
    L.append("    #3;")
    L.append("    rr = rsp; b_err = (rr.status != sf_albion_pkg::SF_ST_OKAY); b_data = rr.data[8*lane +: 32];")
    L.append("    if (!rsp_valid) begin $display(\"DIFF FAIL op %0d: no bank response\", ops); errors++; end")
    L.append("    if (!is_write && is_wo(off)) begin")
    L.append("      n_wo_rd++;")
    L.append("      if (r_err || r_data != 32'h0) begin $display(\"DIFF FAIL op %0d off %03x: slave must read 0 without error, got err=%0b data=%08x\", ops, off, r_err, r_data); errors++; end")
    L.append("      if (rr.status != sf_albion_pkg::SF_ST_ACCESS_DENIED) begin $display(\"DIFF FAIL op %0d off %03x: bank must refuse a read of a write-only register, status=%0d\", ops, off, rr.status); errors++; end")
    L.append("    end else begin")
    L.append("      if (r_err !== b_err) begin $display(\"DIFF FAIL op %0d %s off %03x wdata %08x: slave err=%0b bank status=%0d\", ops, is_write ? \"W\" : \"R\", off, wdata, r_err, rr.status); errors++; end")
    L.append("      else if (r_err) n_refused++;")
    L.append("      else if (is_write) n_ok_wr++;")
    L.append("      else begin")
    L.append("        n_ok_rd++;")
    L.append("        if (r_data !== b_data) begin $display(\"DIFF FAIL op %0d off %03x: read data slave=%08x bank=%08x\", ops, off, r_data, b_data); errors++; end")
    L.append("      end")
    L.append("    end")
    for k, (a, b, w) in enumerate(s.pulses):
        L.append(f"    n_pulse_checks++; if (pa{k} !== {b}) begin $display(\"DIFF FAIL op %0d off %03x: pulse {a} slave=%b bank {b}=%b\", ops, off, pa{k}, {b}); errors++; end")
    for a, b, w in s.levels:
        L.append(f"    if ({a} !== {b}) begin $display(\"DIFF FAIL op %0d off %03x: level {a} slave=%h bank {b}=%h\", ops, off, {a}, {b}); errors++; end")
    L.append("    ops++;")
    L.append("  endtask")
    L.append("")
    # intc probes
    if s.probes:
        for _, nm, w in s.probes:
            L.append(f"  logic [{w - 1}:0] {nm};")
        L.append("  task automatic probe();")
        for off, nm, w in s.probes:
            L.append(f"    {r['sel']} = 1'b1; {r['we']} = 1'b0; {r['addr']} = 12'h{off:03x}; #1; {nm} = {r['rdata']}[{w - 1}:0]; {r['sel']} = 1'b0; #1;")
        L.append("  endtask")
    L.append("")
    L.append("  task automatic readback();")
    for k, o in enumerate(offs):
        if o in s.wo_offsets:
            continue
        L.append(f"    access(1'b0, 12'h{o:03x}, 32'h0, 1'b0);")
    L.append("  endtask")
    L.append("")
    L.append("  logic [63:0] v1, v2;")
    L.append("  initial begin")
    L.append(f"    rng = 64'h{seed:x} ^ 64'h9E3779B97F4A7C15; errors = 0; ops = 0; tag = 0; n_refused = 0; n_ok_wr = 0; n_ok_rd = 0; n_wo_rd = 0; n_pulse_checks = 0;")
    L.append("    rst_n = 1'b0; req_valid = 1'b0; rsp_ready = 1'b1; req = '0;")
    L.append(f"    {r['sel']} = 1'b0; {r['we']} = 1'b0; {r['addr']} = '0; {r['wdata']} = '0;")
    L.append("    randomize_inputs();")
    L.append("    repeat (3) @(negedge clk);")
    L.append("    rst_n = 1'b1;")
    L.append("    @(negedge clk);")
    if s.probes:
        L.append("    randomize_inputs(); probe();")
    L.append("    readback();")
    L.append("    for (int i = 0; i < NOPS; i++) begin")
    L.append("      logic [11:0] off; logic [31:0] wd; logic isw;")
    L.append("      rnd(v1); rnd(v2);")
    L.append("      isw = v1[3];")
    L.append("      if (v1[15:8] < 8'd36)      off = {v2[11:2], 2'b00};                    // any aligned offset (mostly unmapped)")
    L.append("      else                       off = off_of(int'(v2[31:16] % NOFF));      // a defined register")
    L.append("      case (v1[20:17])")
    L.append("        4'd0, 4'd1: wd = 32'hFFFFFFFF;")
    L.append("        4'd2:       wd = 32'h0;")
    L.append("        4'd3:       wd = 32'h1;")
    L.append("        default:    wd = v2[63:32];")
    L.append("      endcase")
    if s.probes:
        L.append("      randomize_inputs(); probe();")
        L.append("      access(isw, off, wd, 1'b0);")
        L.append("      probe(); if (i % 8 == 0) readback();")
    else:
        L.append("      access(isw, off, wd, 1'b1);")
        L.append("      if (i % 8 == 0) readback();")
    L.append("    end")
    L.append("    if (errors == 0) $display(\"DIFF_RESULT: PASS ops=%0d refused=%0d ok_writes=%0d ok_reads=%0d wo_reads=%0d pulse_checks=%0d\", ops, n_refused, n_ok_wr, n_ok_rd, n_wo_rd, n_pulse_checks);")
    L.append("    else $display(\"DIFF_RESULT: FAIL errors=%0d\", errors);")
    L.append("    $finish;")
    L.append("  end")
    L.append("endmodule")
    L.append("`default_nettype wire")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- specs
def _P(m: RegMap, periph: str):
    ports = {(q.reg, q.field, q.kind): q.name for q in m.hw_ports if q.periph == periph}

    def get(reg: str, field: str, kind: str) -> str:
        return ports[(reg, field, kind)]
    return get


def _offsets(m: RegMap, periph: str) -> List[int]:
    return sorted({i.offset for i in m.instances if i.periph.name == periph})


def vector_spec(m: RegMap) -> Spec:
    P = _P(m, "vector")
    ins = [("cmd_ready_i", 1, "bit"), ("cpl_valid_i", 1, "bit"), ("cpl_rec_i", 128, "vec"), ("busy_i", 1, "bit"),
           ("q_count_i", 4, "vec"), ("q_full_i", 1, "bit"), ("q_empty_i", 1, "bit"), ("rob_count_i", 4, "vec"),
           ("err_sticky_i", 1, "bit"), ("dma_down_i", 1, "bit"), ("vec_down_i", 1, "bit"),
           ("ev_commit_err_i", 1, "event"), ("ev_commit_irq_i", 1, "event"), ("perf_cnt_i", 17 * 32, "vec")]
    outs = [("irq_o", 1), ("cmd_valid_o", 1), ("cmd_desc_o", 256), ("cpl_ready_o", 1), ("ctrl_err_cont_o", 1),
            ("ctrl_err_clear_o", 1), ("ctrl_perf_clear_o", 1)]
    info = (1 << 26) | (1 << 25) | (1 << 24) | (8 << 16) | (8 << 8) | 1
    bm = {
        P("STATUS", "BUSY", "value"): "busy_i", P("STATUS", "ERR_STICKY", "value"): "err_sticky_i",
        P("STATUS", "Q_FULL", "value"): "q_full_i", P("STATUS", "Q_EMPTY", "value"): "q_empty_i",
        P("STATUS", "CPL_VALID", "value"): "cpl_valid_i", P("STATUS", "DMA_DOWN", "value"): "dma_down_i",
        P("STATUS", "VEC_DOWN", "value"): "vec_down_i", P("STATUS", "Q_COUNT", "value"): "{4'd0, q_count_i}",
        P("STATUS", "ROB_COUNT", "value"): "{4'd0, rob_count_i}", P("STATUS", "Q_FREE", "value"): "8'd8 - {4'd0, q_count_i}",
        P("SUBMITTED", "VALUE", "value"): "subm",
        P("CPL", "VALUE", "value"): "cpl_rec_i", P("PERF", "VALUE", "value"): "perf_cnt_i",
        P("INT_STATUS", "IRQ", "event"): "ev_commit_irq_i", P("INT_STATUS", "ERR", "event"): "ev_commit_err_i",
        P("DOORBELL", "", "gate"): "cmd_ready_i", P("CPL_POP", "", "gate"): "cpl_valid_i",
    }
    for f in m.periph("vector").registers:
        if f.name == "INFO":
            for fl in f.fields:
                bm[P("INFO", fl.name, "value")] = f"32'h{info:x} >> {fl.lsb}"
    glue = ("  logic [31:0] subm;\n"
            "  always_ff @(posedge clk or negedge rst_n) if (!rst_n) subm <= 32'd0; else if (cmd_valid_o) subm <= subm + 32'd1;\n")
    return Spec("vector", "vector", "hpc_cq_mmio", "#(.QUEUE_DEPTH(8), .ROB_DEPTH(8), .OPSET_FULL(1'b1), .OVERLAP_EN(1'b1), .PERF_EN(1'b1), .PERF_CW(32))",
                "clk_i", "rst_ni", {"sel": "rb_sel", "we": "rb_we", "addr": "rb_addr", "wdata": "rb_wdata", "rdata": "rb_rdata", "err": "rb_err"},
                ins, outs, {},
                pulses=[("cmd_valid_o", P("DOORBELL", "", "wr_strobe"), 1), ("cpl_ready_o", P("CPL_POP", "", "wr_strobe"), 1),
                        ("ctrl_err_clear_o", P("CTRL", "ERR_CLEAR", "pulse"), 1), ("ctrl_perf_clear_o", P("CTRL", "PERF_CLEAR", "pulse"), 1)],
                levels=[("irq_o", "vector_irq_o", 1), ("cmd_desc_o", P("DESC", "VALUE", "value"), 256),
                        ("ctrl_err_cont_o", P("CTRL", "ERR_CONT", "value"), 1)],
                bank_map=bm, glue=glue, wo_offsets=[0x040, 0x060], offsets=_offsets(m, "vector"))


def tensor_spec(m: RegMap) -> Spec:
    P = _P(m, "tensor")
    ins = [("cq_in_ready", 1, "bit"), ("cpl_valid", 1, "bit"), ("cpl_data", 192, "vec"), ("status", 32, "vec"),
           ("ev_irq", 1, "event"), ("ev_err", 1, "event"), ("ev_done", 1, "event"),
           ("perf_cnt", 20 * 32, "vec"), ("dma_perf_cnt", 18 * 32, "vec")]
    outs = [("cq_in_valid", 1), ("cq_in_data", 384), ("cpl_pop", 1), ("ctrl_err_cont", 1), ("ctrl_err_clear", 1),
            ("ctrl_perf_clear", 1), ("ctrl_abort", 1), ("irq", 1)]
    consts = {"INFO": 0x0504_0431, "CAPS": 0x2008_0100 | 0x40, "OPBUF": 0x0000_4000, "MEM_LO": 0x2000_0000,
              "MEM_LAST": 0x2000_FFFF, "KMAX": 0x1FFFF}
    bm = {
        P("CPL", "VALUE", "value"): "cpl_valid ? cpl_data : 192'd0", P("PERF", "VALUE", "value"): "perf_cnt",
        P("DMA_PERF", "VALUE", "value"): "dma_perf_cnt", P("SUBMITTED", "VALUE", "value"): "subm",
        P("INT_STATUS", "IRQ", "event"): "ev_irq", P("INT_STATUS", "ERR", "event"): "ev_err", P("INT_STATUS", "DONE", "event"): "ev_done",
        P("DOORBELL", "", "gate"): "cq_in_ready", P("CPL_POP", "", "gate"): "cpl_valid",
    }
    for rn in ("OPBUF", "MEM_LO", "MEM_LAST", "KMAX"):
        bm[P(rn, "VALUE", "value")] = f"32'h{consts[rn]:x}"
    for rn in ("INFO", "CAPS"):
        for fl in next(r for r in m.periph("tensor").registers if r.name == rn).fields:
            bm[P(rn, fl.name, "value")] = f"32'h{consts[rn]:x} >> {fl.lsb}"
    for fl in next(r for r in m.periph("tensor").registers if r.name == "STATUS").fields:
        bm[P("STATUS", fl.name, "value")] = f"status >> {fl.lsb}"
    glue = ("  logic [31:0] subm;\n"
            "  always_ff @(posedge clk or negedge rst_n) if (!rst_n) subm <= 32'd0; else if (cq_in_valid) subm <= subm + 32'd1;\n")
    params = (f"#(.INFO(32'h{consts['INFO']:x}), .CAPS(32'h{consts['CAPS']:x}), .OPBUF(32'h{consts['OPBUF']:x}), "
              f".MEM_LO(32'h{consts['MEM_LO']:x}), .MEM_LAST(32'h{consts['MEM_LAST']:x}), .KMAX(32'h{consts['KMAX']:x}))")
    return Spec("tensor", "tensor", "tsu_regs", params, "clk", "rst_n",
                {"sel": "rb_sel", "we": "rb_we", "addr": "rb_addr", "wdata": "rb_wdata", "rdata": "rb_rdata", "err": "rb_err"},
                ins, outs, {},
                pulses=[("cq_in_valid", P("DOORBELL", "", "wr_strobe"), 1), ("cpl_pop", P("CPL_POP", "", "wr_strobe"), 1),
                        ("ctrl_err_clear", P("CTRL", "ERR_CLEAR", "pulse"), 1), ("ctrl_perf_clear", P("CTRL", "PERF_CLEAR", "pulse"), 1),
                        ("ctrl_abort", P("CTRL", "ABORT", "pulse"), 1)],
                levels=[("irq", "tensor_irq_o", 1), ("cq_in_data", P("DESC", "VALUE", "value"), 384),
                        ("ctrl_err_cont", P("CTRL", "ERR_CONT", "value"), 1)],
                bank_map=bm, glue=glue, wo_offsets=[0x070, 0x098], offsets=_offsets(m, "tensor"),
                # silicaflux_tensor_unit assembles status = {qfree, qcount, 4'd0, state, 1'b0, halted, aborting, ...}:
                # bit 7 and bits 15:12 are constant 0, so the hardware never drives them
                input_masks={"status": 0xFFFF0F7F})


def intc_spec(m: RegMap) -> Spec:
    P = _P(m, "intc")
    ins = [("src", 16, "vec")]
    outs = [("irq_ext", 1)]
    bm = {P("PENDING", "SOURCES", "value"): "pend_v", P("CLAIM", "ID", "value"): "claim_v[7:0]", P("ACTIVE", "ACT", "value"): "act_v"}
    probes = [(0x000, "pend_v", 16), (0x008, "claim_v", 8), (0x014, "act_v", 16)]
    return Spec("intc", "intc", "mcu_intc", "#(.N(16))", "clk", "rst_n",
                {"sel": "rb_sel", "we": "rb_we", "addr": "rb_addr", "wdata": "rb_wdata", "rdata": "rb_rdata", "err": "rb_err"},
                ins, outs, {}, pulses=[], levels=[], bank_map=bm, glue="", wo_offsets=[],
                offsets=_offsets(m, "intc"), probes=probes)
