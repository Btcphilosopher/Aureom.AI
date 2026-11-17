"""SystemVerilog emitters: sf_reg_pkg / sf_reg_decoder / sf_reg_interface / sf_reg_bank.

Architecture (see docs/ARCHITECTURE.md)
---------------------------------------
``sf_reg_bank`` is the module a designer instantiates.  It contains

* ``sf_reg_interface``  the ALP v1 target: request/response channels, ALP
  legality check, and a one-entry *response slice* that makes stalled
  transactions safe (side effects happen exactly once, at the cycle the
  request is accepted; a response that is not taken is simply held);
* ``sf_reg_decoder``    pure combinational address decode, region access
  check (the real ``sf_albion_pkg`` functions), hole / permission verdict;
* the register storage, field logic and the hardware-facing ports.

All hardware-facing outputs are registered: they change on the clock edge that
ends the accept cycle, never combinationally from the request.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from . import GENERATOR_NAME, SCHEMA_VERSION, __version__
from .model import Field, HwPort, RegInst, RegMap

ALP_REQ_W = 236
LINK_CAPACITY = 2  # outstanding capacity advertised (see ARCHITECTURE.md, ALP-OUT-01/02)


def header(m: RegMap, what: str) -> str:
    return (
        "// =============================================================================\n"
        f"//  {what}\n"
        "//  GENERATED FILE -- DO NOT EDIT.  Edit the register definition instead.\n"
        f"//  generator       : {GENERATOR_NAME} {__version__} (definition schema {SCHEMA_VERSION})\n"
        f"//  register map   : {m.name} v{m.version[0]}.{m.version[1]}\n"
        f"//  semantic hash  : {m.semantic_hash}\n"
        f"//  definition hash: {m.definition_hash}\n"
        "//  Bus protocol    : Albion Link Protocol v1 (AlbionCore sf_albion_pkg)\n"
        "// =============================================================================\n"
    )


def hexlit(width: int, value: int) -> str:
    return f"{width}'h{value:0{(width + 3) // 4}x}"


def upper(inst: RegInst) -> str:
    return inst.name.upper()


def _bit_vec_literal(n: int, bits: List[int]) -> str:
    v = 0
    for b in bits:
        v |= 1 << b
    return hexlit(n, v)


# --------------------------------------------------------------------------
# sf_reg_pkg
# --------------------------------------------------------------------------
def emit_pkg(m: RegMap) -> str:
    L: List[str] = [header(m, "sf_reg_pkg.sv -- address map constants"), "`default_nettype none\n",
                    "/* verilator lint_off UNUSEDPARAM */", "package sf_reg_pkg;\n"]
    L.append(f"  localparam int unsigned SF_REG_NUM_REGS    = {len(m.instances)};")
    L.append(f"  localparam int unsigned SF_REG_NUM_PERIPHS = {len(m.peripherals)};")
    L.append(f"  localparam int unsigned SF_REG_MAP_VERSION_MAJOR = {m.version[0]};")
    L.append(f"  localparam int unsigned SF_REG_MAP_VERSION_MINOR = {m.version[1]};")
    L.append(f"  localparam logic [63:0] SF_REG_MAP_HASH = {hexlit(64, m.hash64)};  // first 8 bytes of the semantic hash")
    L.append(f"  // ALP link capacity advertised by sf_reg_interface (accepts a request in the cycle its predecessor's response leaves)")
    L.append(f"  localparam int unsigned SF_REG_MAX_OUTSTANDING = {LINK_CAPACITY};\n")
    L.append("  // ---- peripheral windows")
    for p in m.peripherals:
        n = p.name.upper()
        L.append(f"  localparam logic [63:0] SF_{n}_BASE = {hexlit(64, p.base)};")
        L.append(f"  localparam logic [63:0] SF_{n}_SIZE = {hexlit(64, p.size)};")
        L.append(f"  localparam logic [7:0]  SF_{n}_REGION_ATTR = {hexlit(8, m.periph_attr_byte(p))};  // sf_region_attr_t (region {p.region})")
    L.append("\n  // ---- register instances: absolute address, width, reset value")
    for i in m.instances:
        u = upper(i)
        w = i.reg.width
        L.append(f"  localparam logic [63:0] SF_{u}_ADDR  = {hexlit(64, i.addr)};")
        L.append(f"  localparam logic [{w - 1}:0] SF_{u}_RESET = {hexlit(w, i.reg.reset)};")
    L.append("\nendpackage")
    L.append("/* verilator lint_on UNUSEDPARAM */\n")
    L.append("`default_nettype wire")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# sf_reg_decoder
# --------------------------------------------------------------------------
def emit_decoder(m: RegMap) -> str:
    n = len(m.instances)
    L: List[str] = [header(m, "sf_reg_decoder.sv -- address decode, region check, permission verdict"),
                    "`default_nettype none\n",
                    "// Pure combinational.  Inputs: the flat ALP request.  Outputs:",
                    "//   reg_sel_o  one bit per register instance whose byte lanes the request touches",
                    "//   status_o   verdict that does NOT depend on hardware state, in ALP precedence order:",
                    "//                1. address outside every peripheral window       -> DECODE_ERR",
                    "//                2. region/peripheral access check (sf_access_check_bits):",
                    "//                   read/write/exec, privilege, security          -> ACCESS_DENIED",
                    "//                                               device mem type  -> BAD_ATTR",
                    "//                3. an enabled byte lane that belongs to no register -> DECODE_ERR",
                    "//                4. write to a register with no writable field, or",
                    "//                   read of a register with no readable field     -> ACCESS_DENIED",
                    "// The ALP legality check (opcode, alignment, byte enables, attributes, domain) has",
                    "// precedence over all of this and is applied by sf_reg_interface.",
                    "/* verilator lint_off UNUSEDSIGNAL */",
                    "module sf_reg_decoder (",
                    "  input  wire logic [sf_albion_pkg::SF_REQ_W-1:0]    req_i,",
                    f"  output logic      [{n - 1}:0]                      reg_sel_o,",
                    "  output logic      [sf_albion_pkg::SF_STATUS_W-1:0] status_o",
                    ");",
                    "  logic [63:0] addr;",
                    "  logic [15:0] be;",
                    "  logic        is_write;",
                    "  logic        is_read;",
                    "  assign addr     = req_i[sf_albion_pkg::SF_REQ_ADDR_LSB +: sf_albion_pkg::SF_ADDR_W];",
                    "  assign be       = req_i[sf_albion_pkg::SF_REQ_BE_LSB   +: sf_albion_pkg::SF_BE_W];",
                    "  assign is_write = (req_i[sf_albion_pkg::SF_REQ_OP_LSB +: sf_albion_pkg::SF_OP_W] == sf_albion_pkg::SF_OP_WRITE);",
                    "  assign is_read  = (req_i[sf_albion_pkg::SF_REQ_OP_LSB +: sf_albion_pkg::SF_OP_W] == sf_albion_pkg::SF_OP_READ);",
                    ""]
    np_ = len(m.peripherals)
    L.append(f"  // ---- peripheral windows ({np_})")
    L.append(f"  logic [{np_ - 1}:0] p_hit;")
    for k, p in enumerate(m.peripherals):
        lsb = p.size.bit_length() - 1
        L.append(f"  assign p_hit[{k}] = (addr[63:{lsb}] == sf_reg_pkg::SF_{p.name.upper()}_BASE[63:{lsb}]);  // {p.name}")
    L.append("")
    L.append(f"  // ---- register instances ({n}): word hit and byte-lane touch")
    L.append(f"  logic [{n - 1}:0] word_hit;")
    L.append("  logic [15:0] covered;")
    for i in m.instances:
        L.append(f"  assign word_hit[{i.index}] = (addr[63:4] == sf_reg_pkg::SF_{upper(i)}_ADDR[63:4]);  // {i.periph.name}.{i.reg.name}"
                 + (f"[{i.elem}]" if i.reg.count > 1 else ""))
    for i in m.instances:
        L.append(f"  assign reg_sel_o[{i.index}] = word_hit[{i.index}] && (|(be & {hexlit(16, i.lanemask)}));")
    L.append("  always_comb begin")
    L.append("    covered = 16'h0000;")
    for i in m.instances:
        L.append(f"    if (word_hit[{i.index}]) covered = covered | {hexlit(16, i.lanemask)};")
    L.append("  end")
    L.append("")
    nw = [i.index for i in m.instances if not i.reg.writable]
    nr = [i.index for i in m.instances if not i.reg.readable]
    L.append(f"  localparam logic [{n - 1}:0] NOT_WRITABLE = {_bit_vec_literal(n, nw)};")
    L.append(f"  localparam logic [{n - 1}:0] NOT_READABLE = {_bit_vec_literal(n, nr)};")
    L.append("  logic hole, deny;")
    L.append("  assign hole = |(be & ~covered);")
    L.append("  assign deny = (is_write && (|(reg_sel_o & NOT_WRITABLE))) || (is_read && (|(reg_sel_o & NOT_READABLE)));")
    L.append("")
    L.append("  logic [sf_albion_pkg::SF_STATUS_W-1:0] region_status;")
    L.append("  always_comb begin")
    L.append("    region_status = sf_albion_pkg::SF_ST_OKAY;")
    for k, p in enumerate(m.peripherals):
        L.append(f"    if (p_hit[{k}]) region_status = sf_albion_pkg::sf_access_check_bits(sf_reg_pkg::SF_{p.name.upper()}_REGION_ATTR, req_i);")
    L.append("    if (!(|p_hit))                                       status_o = sf_albion_pkg::SF_ST_DECODE_ERR;")
    L.append("    else if (region_status != sf_albion_pkg::SF_ST_OKAY) status_o = region_status;")
    L.append("    else if (hole)                                       status_o = sf_albion_pkg::SF_ST_DECODE_ERR;")
    L.append("    else if (deny)                                       status_o = sf_albion_pkg::SF_ST_ACCESS_DENIED;")
    L.append("    else                                                 status_o = sf_albion_pkg::SF_ST_OKAY;")
    L.append("  end")
    L.append("endmodule")
    L.append("/* verilator lint_on UNUSEDSIGNAL */\n")
    L.append("`default_nettype wire")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# sf_reg_interface
# --------------------------------------------------------------------------
def emit_interface(m: RegMap) -> str:
    return header(m, "sf_reg_interface.sv -- ALP v1 target link with stall-safe response slice") + r"""`default_nettype none

// ALP v1 target front end for a register bank.
//
//   * req_ready_o = !rsp_valid_q || rsp_ready_i.  It depends only on registered state and on the
//     response channel's ready (a ready chain, ALP-REQ-03); never on req_valid_i or the payload.
//   * A request is ACCEPTED in the cycle req_valid_i && req_ready_o.  Accepting is the single commit
//     point: acc_valid_o is high for exactly that cycle, so register side effects occur exactly once.
//     A request that is stalled (valid && !ready) has no effect at all and is simply held by the
//     initiator (ALP-REQ-02).
//   * The response is registered: visible one cycle after acceptance at the earliest (ALP-RSP-03),
//     held with an unchanged payload until accepted (ALP-RSP-02).  A response that is not taken
//     therefore never re-triggers anything and never loses read data.
//   * Because a new request is accepted on the same edge on which the previous response leaves,
//     the link can have two requests in flight at the start of a cycle's accounting: the capacity
//     advertised to the fabric is sf_reg_pkg::SF_REG_MAX_OUTSTANDING (= 2).
//   * Response format (ALP-RSP-05): tag echo, meta.last = 1, meta.is_write from the request, data is
//     all-zero for writes and for every non-OKAY status, lanes not enabled by the request are zero.
module sf_reg_interface (
  input  wire logic                                  clk_i,
  input  wire logic                                  rst_ni,
  // ALP request channel
  input  wire logic                                  req_valid_i,
  output logic                                       req_ready_o,
  input  sf_albion_pkg::sf_req_t                     req_i,
  // ALP response channel
  output logic                                       rsp_valid_o,
  input  wire logic                                  rsp_ready_i,
  output sf_albion_pkg::sf_rsp_t                     rsp_o,
  // internal access port (to sf_reg_bank)
  output logic                                       acc_valid_o,   // request accepted this cycle
  output logic [sf_albion_pkg::SF_REQ_W-1:0]         acc_req_o,     // the request on the wire (valid with acc_valid_o)
  output logic [sf_albion_pkg::SF_STATUS_W-1:0]      acc_legal_o,   // ALP legality status of that request
  input  wire logic [sf_albion_pkg::SF_STATUS_W-1:0] acc_status_i,  // final status (combinational, same cycle)
  input  wire logic [sf_albion_pkg::SF_DATA_W-1:0]   acc_rdata_i    // read data, already lane-masked
);
  logic                   rsp_valid_q;
  sf_albion_pkg::sf_rsp_t rsp_q;
  sf_albion_pkg::sf_rsp_t rsp_d;

  assign req_ready_o = !rsp_valid_q || rsp_ready_i;
  assign acc_valid_o = req_valid_i && req_ready_o;
  assign acc_req_o   = req_i;
  assign acc_legal_o = sf_albion_pkg::sf_req_check_bits(acc_req_o);

  always_comb begin
    rsp_d               = '0;
    rsp_d.tag           = req_i.tag;
    rsp_d.status        = acc_status_i;
    rsp_d.meta.last     = 1'b1;
    rsp_d.meta.is_write = (req_i.op == sf_albion_pkg::SF_OP_WRITE);
    if ((acc_status_i == sf_albion_pkg::SF_ST_OKAY) && (req_i.op == sf_albion_pkg::SF_OP_READ))
      rsp_d.data = acc_rdata_i;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      rsp_valid_q <= 1'b0;
      rsp_q       <= '0;
    end else if (acc_valid_o) begin
      rsp_valid_q <= 1'b1;
      rsp_q       <= rsp_d;
    end else if (rsp_ready_i) begin
      rsp_valid_q <= 1'b0;
    end
  end

  assign rsp_valid_o = rsp_valid_q;
  assign rsp_o       = rsp_q;
endmodule

`default_nettype wire
"""


# --------------------------------------------------------------------------
# sf_reg_bank
# --------------------------------------------------------------------------
class _Names:
    def __init__(self, m: RegMap):
        self.by_key: Dict[Tuple[str, str, str, str], HwPort] = {}
        for q in m.hw_ports:
            self.by_key[(q.periph, q.reg, q.field, q.kind)] = q

    def port(self, inst: RegInst, field: str, kind: str) -> HwPort:
        return self.by_key[(inst.periph.name, inst.reg.name, field, kind)]


def _fq(inst: RegInst, f: Field) -> str:
    return f"r{inst.index}_{f.name.lower()}_q"


def _sl(port: HwPort, elem: int, fw: int) -> str:
    return f"{port.name}[{elem * fw} +: {fw}]"


def _decl(q: HwPort) -> str:
    d = "input  wire logic" if q.direction == "input" else "output logic     "
    return f"{d} [{q.width - 1}:0] {q.name}"


def emit_bank(m: RegMap) -> str:
    names = _Names(m)
    n = len(m.instances)
    L: List[str] = [header(m, "sf_reg_bank.sv -- register bank (ALP v1 target)"), "`default_nettype none\n"]
    L.append("// Instantiate this module.  It contains sf_reg_interface and sf_reg_decoder.")
    L.append("// Timing: every hardware output is a flip-flop; hardware inputs are sampled at the clock edge")
    L.append("// that ends the accept cycle of the transaction they influence.  Software/hardware update")
    L.append("// conflicts are resolved per field by its 'precedence' (see the generated register documentation).")
    L.append("/* verilator lint_off UNUSEDSIGNAL */")
    L.append("module sf_reg_bank (")
    L.append("  input  wire logic                   clk_i,")
    L.append("  input  wire logic                   rst_ni,")
    L.append("  // ---- ALP v1 link (target)")
    L.append("  input  wire logic                   req_valid_i,")
    L.append("  output logic                        req_ready_o,")
    L.append("  input  sf_albion_pkg::sf_req_t      req_i,")
    L.append("  output logic                        rsp_valid_o,")
    L.append("  input  wire logic                   rsp_ready_i,")
    L.append("  output sf_albion_pkg::sf_rsp_t      rsp_o,")
    cur = None
    decls: List[str] = []
    for q in m.hw_ports:
        if q.periph != cur:
            cur = q.periph
            decls.append(f"  // ---- hardware side: {cur}")
        decls.append("  " + _decl(q))
    # commas: every declaration line except comments gets one, last one none
    last = max(i for i, s in enumerate(decls) if not s.lstrip().startswith("//"))
    for i, s in enumerate(decls):
        L.append(s + ("," if (not s.lstrip().startswith("//") and i != last) else ""))
    L.append(");")
    L.append("")
    L.append("  // ---- ALP front end")
    L.append("  logic                                  acc_valid;")
    L.append("  logic [sf_albion_pkg::SF_REQ_W-1:0]    acc_req;")
    L.append("  logic [sf_albion_pkg::SF_STATUS_W-1:0] acc_legal;")
    L.append("  logic [sf_albion_pkg::SF_STATUS_W-1:0] acc_status;")
    L.append("  logic [sf_albion_pkg::SF_DATA_W-1:0]   acc_rdata;")
    L.append("  sf_reg_interface u_if (")
    L.append("    .clk_i, .rst_ni, .req_valid_i, .req_ready_o, .req_i, .rsp_valid_o, .rsp_ready_i, .rsp_o,")
    L.append("    .acc_valid_o(acc_valid), .acc_req_o(acc_req), .acc_legal_o(acc_legal),")
    L.append("    .acc_status_i(acc_status), .acc_rdata_i(acc_rdata)")
    L.append("  );")
    L.append("")
    L.append("  // ---- decode")
    L.append(f"  logic [{n - 1}:0] reg_sel;")
    L.append("  logic [sf_albion_pkg::SF_STATUS_W-1:0] dec_status;")
    L.append("  sf_reg_decoder u_dec (.req_i(acc_req), .reg_sel_o(reg_sel), .status_o(dec_status));")
    L.append("")
    L.append("  logic        acc_is_write;")
    L.append("  logic        acc_is_read;")
    L.append("  logic [15:0] acc_be;")
    L.append("  assign acc_is_write = (acc_req[sf_albion_pkg::SF_REQ_OP_LSB +: sf_albion_pkg::SF_OP_W] == sf_albion_pkg::SF_OP_WRITE);")
    L.append("  assign acc_is_read  = (acc_req[sf_albion_pkg::SF_REQ_OP_LSB +: sf_albion_pkg::SF_OP_W] == sf_albion_pkg::SF_OP_READ);")
    L.append("  assign acc_be       = acc_req[sf_albion_pkg::SF_REQ_BE_LSB +: sf_albion_pkg::SF_BE_W];")
    L.append("")
    # write gates
    gated = [i for i in m.instances if i.reg.write_gate]
    L.append("  // ---- write gates (hardware 'ready'): a gated write whose gate is low is refused with TARGET_ERR")
    L.append(f"  logic [{n - 1}:0] gate_ok;")
    L.append(f"  localparam logic [{n - 1}:0] GATED = {_bit_vec_literal(n, [i.index for i in gated])};")
    for i in m.instances:
        if i.reg.write_gate:
            q = names.port(i, "", "gate")
            L.append(f"  assign gate_ok[{i.index}] = {_sl(q, i.elem, 1)};")
        else:
            L.append(f"  assign gate_ok[{i.index}] = 1'b1;")
    L.append("  logic gate_fail;")
    L.append("  assign gate_fail = acc_is_write && (|(reg_sel & GATED & ~gate_ok));")
    L.append("")
    L.append("  // ---- final status: ALP legality > decode/region/permission > hardware gate")
    L.append("  always_comb begin")
    L.append("    if (acc_legal != sf_albion_pkg::SF_ST_OKAY)       acc_status = acc_legal;")
    L.append("    else if (dec_status != sf_albion_pkg::SF_ST_OKAY) acc_status = dec_status;")
    L.append("    else if (gate_fail)                               acc_status = sf_albion_pkg::SF_ST_TARGET_ERR;")
    L.append("    else                                              acc_status = sf_albion_pkg::SF_ST_OKAY;")
    L.append("  end")
    L.append("  logic wr_commit, rd_commit;")
    L.append("  assign wr_commit = acc_valid && (acc_status == sf_albion_pkg::SF_ST_OKAY) && acc_is_write;")
    L.append("  assign rd_commit = acc_valid && (acc_status == sf_albion_pkg::SF_ST_OKAY) && acc_is_read;")
    L.append("")
    L.append("  logic [127:0] rd_acc;")
    L.append("  logic [127:0] be_mask;")
    L.append("  always_comb begin")
    L.append("    for (int b = 0; b < 16; b++) be_mask[b*8 +: 8] = {8{acc_be[b]}};")
    L.append("  end")
    L.append("")

    # ---- per-instance logic
    for inst in m.instances:
        r = inst.reg
        w = r.width
        nb = r.nbytes
        i = inst.index
        elem = f"[{inst.elem}]" if r.count > 1 else ""
        L.append(f"  // ======================================================================")
        L.append(f"  // r{i}: {inst.periph.name}.{r.name}{elem} @ {hexlit(64, inst.addr)} ({w}-bit)")
        L.append(f"  // ======================================================================")
        L.append(f"  logic [{w - 1}:0] r{i}_wdata, r{i}_wmask, r{i}_rdata;")
        L.append(f"  logic             r{i}_wr, r{i}_rd;")
        L.append(f"  assign r{i}_wdata = acc_req[sf_albion_pkg::SF_REQ_DATA_LSB + {inst.lane0 * 8} +: {w}];")
        mask_bits = ", ".join(f"{{8{{acc_be[{inst.lane0 + b}]}}}}" for b in reversed(range(nb)))
        L.append(f"  assign r{i}_wmask = {{{mask_bits}}};")
        L.append(f"  assign r{i}_wr    = wr_commit && reg_sel[{i}];")
        L.append(f"  assign r{i}_rd    = rd_commit && reg_sel[{i}];")
        for f in r.fields:
            fw = f.width
            fq = _fq(inst, f)
            tag = f"{f.name} [{f.msb}:{f.lsb}] {f.access}" + (f"/{f.hw}" if f.access != "w1p" else "")
            L.append(f"  // field {tag}")
            wb = f"r{i}_{f.name.lower()}_wb"
            wm = f"r{i}_{f.name.lower()}_wm"
            L.append(f"  logic [{fw - 1}:0] {wb}, {wm};")
            L.append(f"  assign {wb} = r{i}_wdata[{f.lsb} +: {fw}];")
            L.append(f"  assign {wm} = r{i}_wmask[{f.lsb} +: {fw}];")
            rst = hexlit(fw, f.reset)
            if f.access in ("rw", "wo") and f.has_storage:
                L.append(f"  logic [{fw - 1}:0] {fq};")
                sw = f"(r{i}_wr && (|{wm}))"
                nxt = f"(({fq} & ~{wm}) | ({wb} & {wm}))"
                hwp = None
                if f.access == "rw" and f.hw == "update":
                    we = names.port(inst, f.name, "hw_we")
                    wd = names.port(inst, f.name, "hw_wdata")
                    hwp = (_sl(we, inst.elem, 1), _sl(wd, inst.elem, fw))
                L.append("  always_ff @(posedge clk_i or negedge rst_ni) begin")
                L.append(f"    if (!rst_ni) {fq} <= {rst};")
                if hwp and f.precedence == "hw":
                    L.append(f"    else if ({hwp[0]}) {fq} <= {hwp[1]};")
                    L.append(f"    else if {sw} {fq} <= {nxt};")
                elif hwp:
                    L.append(f"    else if {sw} {fq} <= {nxt};")
                    L.append(f"    else if ({hwp[0]}) {fq} <= {hwp[1]};")
                else:
                    L.append(f"    else if {sw} {fq} <= {nxt};")
                L.append("  end")
                q = names.port(inst, f.name, "value")
                L.append(f"  assign {_sl(q, inst.elem, fw)} = {fq};")
            elif f.access == "w1c":
                L.append(f"  logic [{fw - 1}:0] {fq};")
                clr = f"({{{fw}{{r{i}_wr}}}} & {wb} & {wm})"
                if f.hw == "event":
                    st = names.port(inst, f.name, "event")
                    setv = _sl(st, inst.elem, fw)
                    nxt = f"(({fq} & ~{clr}) | {setv})" if f.precedence == "hw" else f"(({fq} | {setv}) & ~{clr})"
                else:
                    nxt = f"({fq} & ~{clr})"
                L.append("  always_ff @(posedge clk_i or negedge rst_ni) begin")
                L.append(f"    if (!rst_ni) {fq} <= {rst};")
                L.append(f"    else {fq} <= {nxt};")
                L.append("  end")
                q = names.port(inst, f.name, "value")
                L.append(f"  assign {_sl(q, inst.elem, fw)} = {fq};")
            elif f.access == "w1s":
                L.append(f"  logic [{fw - 1}:0] {fq};")
                setb = f"({{{fw}{{r{i}_wr}}}} & {wb} & {wm})"
                if f.hw == "event":
                    cl = names.port(inst, f.name, "event")
                    clv = _sl(cl, inst.elem, fw)
                    nxt = f"(({fq} | {setb}) & ~{clv})" if f.precedence == "hw" else f"(({fq} & ~{clv}) | {setb})"
                else:
                    nxt = f"({fq} | {setb})"
                L.append("  always_ff @(posedge clk_i or negedge rst_ni) begin")
                L.append(f"    if (!rst_ni) {fq} <= {rst};")
                L.append(f"    else {fq} <= {nxt};")
                L.append("  end")
                q = names.port(inst, f.name, "value")
                L.append(f"  assign {_sl(q, inst.elem, fw)} = {fq};")
            elif f.access == "w1p":
                pq = f"r{i}_{f.name.lower()}_pulse_q"
                L.append(f"  logic [{fw - 1}:0] {pq};")
                L.append("  always_ff @(posedge clk_i or negedge rst_ni) begin")
                L.append(f"    if (!rst_ni) {pq} <= {fw}'h0;")
                L.append(f"    else {pq} <= {{{fw}{{r{i}_wr}}}} & {wb} & {wm};")
                L.append("  end")
                q = names.port(inst, f.name, "pulse")
                L.append(f"  assign {_sl(q, inst.elem, fw)} = {pq};")
            elif f.access == "ro" and f.hw == "update":
                L.append(f"  logic [{fw - 1}:0] {fq};")
                we = names.port(inst, f.name, "hw_we")
                wd = names.port(inst, f.name, "hw_wdata")
                L.append("  always_ff @(posedge clk_i or negedge rst_ni) begin")
                L.append(f"    if (!rst_ni) {fq} <= {rst};")
                L.append(f"    else if ({_sl(we, inst.elem, 1)}) {fq} <= {_sl(wd, inst.elem, fw)};")
                L.append("  end")
        # strobes
        if r.wr_strobe:
            q = names.port(inst, "", "wr_strobe")
            L.append(f"  logic r{i}_wr_q;")
            L.append("  always_ff @(posedge clk_i or negedge rst_ni) begin")
            L.append(f"    if (!rst_ni) r{i}_wr_q <= 1'b0;")
            L.append(f"    else r{i}_wr_q <= r{i}_wr;")
            L.append("  end")
            L.append(f"  assign {_sl(q, inst.elem, 1)} = r{i}_wr_q;")
        if r.rd_strobe:
            q = names.port(inst, "", "rd_strobe")
            L.append(f"  logic r{i}_rd_q;")
            L.append("  always_ff @(posedge clk_i or negedge rst_ni) begin")
            L.append(f"    if (!rst_ni) r{i}_rd_q <= 1'b0;")
            L.append(f"    else r{i}_rd_q <= r{i}_rd;")
            L.append("  end")
            L.append(f"  assign {_sl(q, inst.elem, 1)} = r{i}_rd_q;")
        # read value
        L.append("  always_comb begin")
        L.append(f"    r{i}_rdata = {w}'h0;")
        for f in r.fields:
            fw = f.width
            if f.access == "ro" and f.hw == "const":
                L.append(f"    r{i}_rdata[{f.lsb} +: {fw}] = {hexlit(fw, f.reset)};")
            elif f.access == "ro" and f.hw == "input":
                q = names.port(inst, f.name, "value")
                L.append(f"    r{i}_rdata[{f.lsb} +: {fw}] = {_sl(q, inst.elem, fw)};")
            elif f.access in ("ro", "rw", "w1c", "w1s"):
                L.append(f"    r{i}_rdata[{f.lsb} +: {fw}] = {_fq(inst, f)};")
        L.append("  end")
        L.append("")

    # ---- read mux
    L.append("  // ---- read data: OR of the selected registers, then lane-masked (ALP-RSP-07)")
    L.append("  logic [127:0] rd_raw;")
    L.append("  always_comb begin")
    L.append("    rd_raw = 128'h0;")
    for inst in m.instances:
        L.append(f"    if (reg_sel[{inst.index}]) rd_raw[{inst.lane0 * 8} +: {inst.reg.width}] = "
                 f"rd_raw[{inst.lane0 * 8} +: {inst.reg.width}] | r{inst.index}_rdata;")
    L.append("  end")
    L.append("  assign acc_rdata = rd_raw & be_mask;")
    L.append("")

    # ---- interrupts
    for p in m.peripherals:
        terms: List[str] = []
        for inst in m.instances:
            if inst.periph.name != p.name:
                continue
            for f in inst.reg.fields:
                if f.interrupt_enable is None:
                    continue
                en_reg, en_fld = f.interrupt_enable
                einst = next(x for x in m.instances if x.periph.name == p.name and x.reg.name == en_reg and x.elem == 0)
                ef = next(x for x in einst.reg.fields if x.name == en_fld)
                if f.access == "ro" and f.hw == "input":
                    sv = _sl(names.port(inst, f.name, "value"), inst.elem, f.width)
                else:
                    sv = _fq(inst, f)
                terms.append(f"(|({sv} & {_fq(einst, ef)}))")
        if terms:
            q = names.by_key[(p.name, "", "", "irq")]
            L.append(f"  assign {q.name} = " + " | ".join(terms) + ";  // " + p.name)
    L.append("endmodule")
    L.append("/* verilator lint_on UNUSEDSIGNAL */\n")
    L.append("`default_nettype wire")
    return "\n".join(L) + "\n"


def emit_all(m: RegMap) -> Dict[str, str]:
    return {
        "sf_reg_pkg.sv": emit_pkg(m),
        "sf_reg_decoder.sv": emit_decoder(m),
        "sf_reg_interface.sv": emit_interface(m),
        "sf_reg_bank.sv": emit_bank(m),
    }
