"""Verification collateral generated from the validated model.

* ``generate_vectors``  deterministic stimulus + expected outputs from the
  independent reference model (directed phases, then constrained-random with
  stalls, illegal requests, hardware events and mid-run resets);
* ``emit_tb``           a self-checking SystemVerilog testbench for any
  register map; it instantiates the real AlbionCore ``sf_albion_link_checker``
  so ALP protocol rules are asserted every cycle;
* ``emit_addr_dump``    a tiny SV program that prints every address/reset
  constant of ``sf_reg_pkg`` for cross-language comparison.
"""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

from . import GENERATOR_NAME, __version__
from .emit_sv import header, hexlit
from .model import HwPort, RegInst, RegMap
from .refmodel import (OP_READ, OP_WRITE, Inputs, Outputs, RefModel, Req, expand_be)

REQ_W = 236
RSP_W = 148
# attribute bytes: [7] rsvd [6:5] qos [4] instr [3] secure [2] priv [1:0] mem_type
ATTR_PRIV_DEV = 0x06


def in_layout(m: RegMap) -> List[Tuple[str, int]]:
    lay = [("rst_n", 1), ("req_valid", 1), ("rsp_ready", 1), ("req", REQ_W)]
    lay += [(p.name, p.width) for p in m.hw_ports if p.direction == "input"]
    return lay


def out_layout(m: RegMap) -> List[Tuple[str, int]]:
    lay = [("req_ready", 1), ("rsp_valid", 1), ("rsp", RSP_W)]
    lay += [(p.name, p.width) for p in m.hw_ports if p.direction == "output"]
    return lay


def _pack(layout: List[Tuple[str, int]], vals: Dict[str, int]) -> int:
    v, off = 0, 0
    for name, w in layout:
        v |= (vals.get(name, 0) & ((1 << w) - 1)) << off
        off += w
    return v


def _hexline(v: int, width: int) -> str:
    return f"{v:0{(width + 3) // 4}x}"


class Generator:
    """Builds a cycle-by-cycle test of one register map."""

    def __init__(self, m: RegMap, seed: int):
        self.m = m
        self.rng = random.Random(seed)
        self.model = RefModel(m)
        self.in_lay = in_layout(m)
        self.out_lay = out_layout(m)
        self.in_ports = [p for p in m.hw_ports if p.direction == "input"]
        self.tag = 0
        self.rows: List[Tuple[int, int, int]] = []     # (stim, exp, mask)
        self.pending: "Req | None" = None
        self.pending_directed = False
        self.queue: List[Req] = []
        self.cycles = 0
        self.mode_ready = 0.7
        self.mode_event = 0.2
        self.mode_gate = 0.7

    # ---------------------------------------------------------------- hw inputs
    def _hw_inputs(self) -> Dict[str, int]:
        r = self.rng
        out: Dict[str, int] = {}
        for p in self.in_ports:
            if p.kind in ("event", "hw_we"):
                v = 0
                for b in range(p.width):
                    if r.random() < self.mode_event:
                        v |= 1 << b
                out[p.name] = v
            elif p.kind == "gate":
                v = 0
                for b in range(p.width):
                    if r.random() < self.mode_gate:
                        v |= 1 << b
                out[p.name] = v
            else:
                out[p.name] = r.getrandbits(p.width)
        return out

    # ------------------------------------------------------------- requests
    def _next_tag(self) -> int:
        t = self.tag
        self.tag = (self.tag + 1) & 0xFF
        return t

    def _data(self) -> int:
        r = self.rng
        c = r.random()
        if c < 0.2:
            return (1 << 128) - 1
        if c < 0.3:
            return 0
        if c < 0.4:
            return int("a5" * 16, 16)
        return r.getrandbits(128)

    def _be_for(self, i: RegInst) -> int:
        r = self.rng
        c = r.random()
        if c < 0.55:
            return i.lanemask
        if c < 0.75:
            sub = 0
            for b in range(i.reg.nbytes):
                if r.random() < 0.5:
                    sub |= 1 << (i.lane0 + b)
            return sub or (1 << i.lane0)
        if c < 0.85:
            return 0xFFFF
        return r.getrandbits(16) or 1

    def good_attr(self, p) -> int:
        """Attribute byte that satisfies the peripheral's region (device memory, privileged, secure if required)."""
        ab = self.m.periph_attr_byte(p)
        return ATTR_PRIV_DEV | (0x08 if ab & 0x10 else 0)

    def bad_attrs(self, p) -> List[int]:
        """Attribute bytes that differ from good_attr in exactly one way the region check looks at."""
        g = self.good_attr(p)
        return [g ^ 0x04, g ^ 0x08, (g & ~3) | 1, (g & ~3) | 0, g | 0x10, g | 0x20, g | 0x40]

    def reg_req(self, i: RegInst, op: int, be: "int | None" = None, data: "int | None" = None,
                attr: "int | None" = None) -> Req:
        return Req(op=op, tag=self._next_tag(), dom=0x01, attr=self.good_attr(i.periph) if attr is None else attr,
                   addr=i.word_addr, be=i.lanemask if be is None else be,
                   data=self._data() if data is None else data)

    def _holes(self) -> List[int]:
        """Word addresses inside peripheral windows that contain no register."""
        words = {i.word_addr for i in self.m.instances}
        out: List[int] = []
        for p in self.m.peripherals:
            n = 0
            for off in range(0, p.size, 16):
                if p.base + off not in words:
                    out.append(p.base + off)
                    n += 1
                    if n >= 4:
                        break
        return out

    def random_req(self) -> Req:
        r = self.rng
        c = r.random()
        insts = self.m.instances
        if c < 0.70:
            i = r.choice(insts)
            attr = self.good_attr(i.periph)
            if r.random() < 0.06:
                attr = r.choice(self.bad_attrs(i.periph))
            return Req(op=r.choice([OP_READ, OP_WRITE]), tag=self._next_tag(), dom=r.choice([1, 1, 1, 0, 0x10]),
                       attr=attr, addr=i.word_addr, be=self._be_for(i), data=self._data())
        if c < 0.80:  # word-wide access touching several registers / holes
            i = r.choice(insts)
            return Req(op=r.choice([OP_READ, OP_WRITE]), tag=self._next_tag(), addr=i.word_addr,
                       be=r.choice([0xFFFF, r.getrandbits(16) or 1]), data=self._data(), attr=self.good_attr(i.periph))
        if c < 0.88:  # in-window hole or unmapped address
            holes = self._holes()
            if holes and r.random() < 0.6:
                a = r.choice(holes)
            else:
                a = r.choice([0, 0x10, 1 << 32, (1 << 40) + 0x100, (1 << 63), 0xFFFF_FFFF_FFFF_FFF0,
                              self.m.max_end, self.m.max_end + 0x1000,
                              min(p.base for p in self.m.peripherals) - 16])
                a &= ~0xF
            per = next((p for p in self.m.peripherals if p.base <= a < p.end), self.m.peripherals[0])
            return Req(op=r.choice([OP_READ, OP_WRITE]), tag=self._next_tag(), addr=a,
                       be=r.getrandbits(16) or 1, data=self._data(), attr=self.good_attr(per))
        # illegal at the ALP level
        i = r.choice(insts)
        q = self.reg_req(i, r.choice([OP_READ, OP_WRITE]))
        kind = r.choice(["op", "align", "be", "attr_rsvd", "attr_mem3", "dom"])
        if kind == "op":
            q.op = r.choice([0, 3, 4, 5, 6, 7, 8, 15])
        elif kind == "align":
            q.addr |= r.randint(1, 15)
        elif kind == "be":
            q.be = 0
        elif kind == "attr_rsvd":
            q.attr |= 0x80
        elif kind == "attr_mem3":
            q.attr = (q.attr & ~3) | 3
        else:
            q.dom = 0xFF
        return q

    # ------------------------------------------------------------ directed
    def directed(self) -> List[Req]:
        q: List[Req] = []
        insts = self.m.instances
        for i in insts:                                # reset values of every register
            q.append(self.reg_req(i, OP_READ))
        full = (1 << 128) - 1
        for i in insts:                                # write patterns then read back
            if i.reg.writable:
                for pat in (full, 0, int("5a" * 16, 16), int("a5" * 16, 16)):
                    q.append(self.reg_req(i, OP_WRITE, data=pat))
                    if i.reg.readable:
                        q.append(self.reg_req(i, OP_READ))
                for b in range(i.reg.nbytes):          # one byte lane at a time (byte strobes)
                    q.append(self.reg_req(i, OP_WRITE, be=1 << (i.lane0 + b), data=full))
                    if i.reg.readable:
                        q.append(self.reg_req(i, OP_READ))
                    q.append(self.reg_req(i, OP_WRITE, be=1 << (i.lane0 + b), data=0))
                    if i.reg.readable:
                        q.append(self.reg_req(i, OP_READ))
        for i in insts:                                # permission checks
            if not i.reg.writable:
                q.append(self.reg_req(i, OP_WRITE, data=full))
            if not i.reg.readable:
                q.append(self.reg_req(i, OP_READ))
        # hardware gates and hardware/software conflicts, directed (not left to chance)
        port = {(q.periph, q.reg, q.field, q.kind): q for q in self.m.hw_ports}
        for i in insts:
            pn, rn = i.periph.name, i.reg.name
            if i.reg.write_gate:
                for g in (0, 1, 0):
                    x = self.reg_req(i, OP_WRITE, data=full)
                    x.force = ((port[(pn, rn, "", "gate")].name, i.elem, 1, g),)
                    q.append(x)
            for f in i.reg.fields:
                ones = (1 << f.width) - 1
                if f.access == "w1c" and f.hw == "event":
                    ev = port[(pn, rn, f.name, "event")].name
                    x = self.reg_req(i, OP_WRITE, data=0); x.force = ((ev, i.elem * f.width, f.width, ones),); q.append(x)   # hardware sets the flag
                    q.append(self.reg_req(i, OP_WRITE, data=full))                                                         # software clears it
                    x = self.reg_req(i, OP_WRITE, data=full); x.force = ((ev, i.elem * f.width, f.width, ones),); q.append(x)  # both in one cycle
                elif f.access == "w1s" and f.hw == "event":
                    ev = port[(pn, rn, f.name, "event")].name
                    q.append(self.reg_req(i, OP_WRITE, data=full))                                                         # software sets
                    x = self.reg_req(i, OP_WRITE, data=full); x.force = ((ev, i.elem * f.width, f.width, ones),); q.append(x)  # both in one cycle
                    x = self.reg_req(i, OP_WRITE, data=0); x.force = ((ev, i.elem * f.width, f.width, ones),); q.append(x)     # hardware clears
                elif f.access == "rw" and f.hw == "update":
                    we = port[(pn, rn, f.name, "hw_we")].name
                    wd = port[(pn, rn, f.name, "hw_wdata")].name
                    x = self.reg_req(i, OP_WRITE, data=full)
                    x.force = ((we, i.elem, 1, 1), (wd, i.elem * f.width, f.width, 0x5a5a5a5a5a5a5a5a & ones))
                    q.append(x)
        i0 = insts[0]
        for op in (0, 3, 4, 7, 15):
            x = self.reg_req(i0, OP_READ)
            x.op = op
            q.append(x)
        x = self.reg_req(i0, OP_READ); x.addr |= 4; q.append(x)
        x = self.reg_req(i0, OP_READ); x.be = 0; q.append(x)
        x = self.reg_req(i0, OP_READ); x.attr |= 0x80; q.append(x)
        x = self.reg_req(i0, OP_READ); x.attr = (x.attr & ~3) | 3; q.append(x)
        x = self.reg_req(i0, OP_READ); x.dom = 0xFF; q.append(x)
        x = self.reg_req(i0, OP_READ); x.addr |= 1 << 63; x.addr &= ~0xF; q.append(x)
        for a in self._holes():
            per = next(p for p in self.m.peripherals if p.base <= a < p.end)
            q.append(Req(op=OP_READ, tag=self._next_tag(), addr=a, be=0xFFFF, attr=self.good_attr(per)))
            q.append(Req(op=OP_WRITE, tag=self._next_tag(), addr=a, be=0xFFFF, data=full, attr=self.good_attr(per)))
        for a in (0, 1 << 32, self.m.max_end, (1 << 63)):
            q.append(Req(op=OP_READ, tag=self._next_tag(), addr=a, be=0xFFFF, attr=ATTR_PRIV_DEV))
        # attribute / privilege / security / memory-type perturbation on every peripheral, reads and writes
        for p in self.m.peripherals:
            for i in (x for x in insts if x.periph.name == p.name):
                if i.reg.readable:
                    for attr in self.bad_attrs(p):
                        q.append(self.reg_req(i, OP_READ, attr=attr))
                    break
            for i in (x for x in insts if x.periph.name == p.name):
                if i.reg.writable:
                    for attr in self.bad_attrs(p):
                        q.append(self.reg_req(i, OP_WRITE, attr=attr))
                    break
        # whole-word accesses (several registers at once, refused atomically on holes)
        for i in insts[:: max(1, len(insts) // 12)]:
            g = self.good_attr(i.periph)
            q.append(Req(op=OP_READ, tag=self._next_tag(), addr=i.word_addr, be=0xFFFF, attr=g))
            q.append(Req(op=OP_WRITE, tag=self._next_tag(), addr=i.word_addr, be=0xFFFF, data=full, attr=g))
        return q

    # ----------------------------------------------------- conflict injection
    def _inject(self, hw: Dict[str, int], req: Req) -> None:
        """If ``req`` is a write that is about to be accepted, make hardware update the same fields in the
        same cycle (hardware/software conflict), so both precedence settings are exercised on purpose."""
        if req.op != OP_WRITE or (req.addr & 0xF) or req.be == 0 or self.rng.random() > 0.6:
            return
        port = {(q.periph, q.reg, q.field, q.kind): q for q in self.m.hw_ports}
        for i in self.m.instances:
            if i.word_addr != req.addr or not (i.lanemask & req.be):
                continue
            wd = (req.data >> (8 * i.lane0)) & ((1 << i.reg.width) - 1)
            for f in i.reg.fields:
                fbits = (wd >> f.lsb) & ((1 << f.width) - 1)
                sh = i.elem * f.width
                if f.access == "w1c" and f.hw == "event":
                    q = port[(i.periph.name, i.reg.name, f.name, "event")]
                    hw[q.name] = (hw[q.name] & ~(((1 << f.width) - 1) << sh)) | (((fbits | self.rng.getrandbits(f.width)) & ((1 << f.width) - 1)) << sh)
                elif f.access == "w1s" and f.hw == "event":
                    q = port[(i.periph.name, i.reg.name, f.name, "event")]
                    hw[q.name] = (hw[q.name] & ~(((1 << f.width) - 1) << sh)) | (((fbits | self.rng.getrandbits(f.width)) & ((1 << f.width) - 1)) << sh)
                elif f.access == "rw" and f.hw == "update":
                    q = port[(i.periph.name, i.reg.name, f.name, "hw_we")]
                    hw[q.name] |= 1 << i.elem
            if i.reg.write_gate:
                q = port[(i.periph.name, i.reg.name, "", "gate")]
                if self.rng.random() < 0.5:
                    hw[q.name] |= 1 << i.elem

    # ------------------------------------------------------------------ run
    def _cycle(self, rst_n: int, hw: Dict[str, int], rsp_ready: int) -> None:
        if rst_n and self.pending is not None and ((not self.model.rsp_valid) or rsp_ready):
            self._inject(hw, self.pending)
        if rst_n and self.pending is not None and self.pending.force and ((not self.model.rsp_valid) or rsp_ready):
            for port, off, w, val in self.pending.force:       # directed hardware behaviour on this accepted request
                hw[port] = (hw.get(port, 0) & ~(((1 << w) - 1) << off)) | ((val & ((1 << w) - 1)) << off)
        inp = Inputs(rst_n=rst_n, rsp_ready=rsp_ready, hw=hw)
        if rst_n and self.pending is not None:
            inp.req_valid = 1
            inp.req = self.pending
        out = self.model.comb(inp)
        accepted = bool(inp.req_valid and out.req_ready)
        stim = _pack(self.in_lay, {"rst_n": rst_n, "req_valid": inp.req_valid,
                                   "rsp_ready": rsp_ready, "req": inp.req.pack() if inp.req_valid else 0, **hw})
        vals = {"req_ready": out.req_ready, "rsp_valid": out.rsp_valid, "rsp": out.rsp.pack(), **out.hw}
        exp = _pack(self.out_lay, vals)
        mask = 0
        off = 0
        for name, w in self.out_lay:
            if name == "rsp" and not out.rsp_valid:
                pass                                     # payload undefined while rsp_valid is low
            else:
                mask |= ((1 << w) - 1) << off
            off += w
        self.rows.append((stim, exp, mask))
        self.model.step(inp)
        if accepted:
            self.pending = None
        if not rst_n:
            if self.pending is not None and self.pending_directed:
                self.queue.insert(0, self.pending)          # reset abandoned it: the directed scenario must still run
            self.pending = None
        self.cycles += 1

    def run(self, n_cycles: int, resets: int = 3) -> None:
        r = self.rng
        reset_at = sorted(r.sample(range(max(10, n_cycles // 4), max(11, n_cycles - 10)), min(resets, 3))) if resets else []
        for _ in range(3):                               # initial reset with noisy inputs
            self._cycle(0, self._hw_inputs(), 1)
        self.queue = self.directed()
        rst_left = 0
        # ``n_cycles`` is a minimum: the directed scenarios always run to completion
        while self.cycles < n_cycles or self.queue or self.pending is not None:
            if self.cycles in reset_at:
                rst_left = r.randint(1, 3)
            if rst_left:
                rst_left -= 1
                self._cycle(0, self._hw_inputs(), r.randint(0, 1))
                continue
            if self.pending is None and (self.queue or (self.cycles < n_cycles and r.random() < 0.8)):
                self.pending_directed = bool(self.queue)
                self.pending = self.queue.pop(0) if self.queue else self.random_req()
            # vary the environment now and then so that quiet and busy phases both occur
            if r.random() < 0.02:
                self.mode_ready = r.choice([0.2, 0.5, 0.9, 1.0])
                self.mode_event = r.choice([0.0, 0.05, 0.3, 0.6])
                self.mode_gate = r.choice([0.1, 0.5, 0.9, 1.0])
            self._cycle(1, self._hw_inputs(), 1 if r.random() < self.mode_ready else 0)
        # drain: let the last response leave
        for _ in range(4):
            self._cycle(1, self._hw_inputs(), 1)

    # ---------------------------------------------------------------- output
    def files(self) -> Dict[str, str]:
        iw = sum(w for _, w in self.in_lay)
        ow = sum(w for _, w in self.out_lay)
        return {
            "stim.hex": "\n".join(_hexline(s, iw) for s, _, _ in self.rows) + "\n",
            "exp.hex": "\n".join(_hexline(e, ow) for _, e, _ in self.rows) + "\n",
            "mask.hex": "\n".join(_hexline(k, ow) for _, _, k in self.rows) + "\n",
        }


def generate_vectors(m: RegMap, seed: int = 1, n_cycles: int = 4000, resets: int = 3):
    g = Generator(m, seed)
    g.run(n_cycles, resets)
    return g


# --------------------------------------------------------------------------
# Testbench
# --------------------------------------------------------------------------
def emit_tb(m: RegMap) -> str:
    in_lay = in_layout(m)
    out_lay = out_layout(m)
    iw = sum(w for _, w in in_lay)
    ow = sum(w for _, w in out_lay)
    L: List[str] = [header(m, "tb_sf_reg_bank.sv -- self-checking testbench (model-driven)"), "`default_nettype none\n"]
    L.append("// Applies stim.hex and compares every output of sf_reg_bank, in every cycle, against exp.hex")
    L.append("// (produced by the independent Python reference model).  The AlbionCore link checker watches the")
    L.append("// ALP link throughout.  Plusargs: +STIM=<file> +EXP=<file> +MASK=<file>; parameter NCYC = number of cycles.")
    L.append("module tb_sf_reg_bank;")
    L.append("  parameter int NCYC = 1;")
    L.append(f"  localparam int IN_W  = {iw};")
    L.append(f"  localparam int OUT_W = {ow};")
    L.append("  logic clk_i;")
    L.append("  logic rst_ni;")
    L.append("  logic req_valid_i;")
    L.append("  logic req_ready_o;")
    L.append("  sf_albion_pkg::sf_req_t req_i;")
    L.append("  logic rsp_valid_o;")
    L.append("  logic rsp_ready_i;")
    L.append("  sf_albion_pkg::sf_rsp_t rsp_o;")
    for p in m.hw_ports:
        L.append(f"  logic [{p.width - 1}:0] {p.name};")
    L.append("")
    conns = [".clk_i(clk_i)", ".rst_ni(rst_ni)", ".req_valid_i(req_valid_i)", ".req_ready_o(req_ready_o)",
             ".req_i(req_i)", ".rsp_valid_o(rsp_valid_o)", ".rsp_ready_i(rsp_ready_i)", ".rsp_o(rsp_o)"]
    conns += [f".{p.name}({p.name})" for p in m.hw_ports]
    L.append("  sf_reg_bank dut (")
    L.append("    " + ",\n    ".join(conns))
    L.append("  );")
    L.append("")
    L.append("  logic [15:0] outstanding;")
    L.append("  sf_albion_link_checker #(.MAX_OUTSTANDING(sf_reg_pkg::SF_REG_MAX_OUTSTANDING)) u_chk (")
    L.append("    .clk_i, .rst_ni, .req_valid_i, .req_ready_i(req_ready_o), .req_i,")
    L.append("    .rsp_valid_i(rsp_valid_o), .rsp_ready_i, .rsp_i(rsp_o), .waive_req_i(1'b0), .outstanding_o(outstanding)")
    L.append("  );")
    L.append("")
    L.append("  logic [IN_W-1:0]  stim_mem [0:NCYC-1];")
    L.append("  logic [OUT_W-1:0] exp_mem  [0:NCYC-1];")
    L.append("  logic [OUT_W-1:0] msk_mem  [0:NCYC-1];")
    L.append("  logic [IN_W-1:0]  stim;")
    L.append("  logic [OUT_W-1:0] got, exp, msk;")
    L.append("  int errors, checks, cyc;")
    L.append("  string f_stim, f_exp, f_msk;")
    L.append("")
    L.append("  initial begin clk_i = 1'b0; forever #5 clk_i = ~clk_i; end")
    L.append("")
    L.append("  task automatic apply(input logic [IN_W-1:0] s);")
    off = 0
    for name, w in in_lay:
        tgt = {"rst_n": "rst_ni", "req_valid": "req_valid_i", "rsp_ready": "rsp_ready_i", "req": "req_i"}.get(name, name)
        L.append(f"    {tgt} = s[{off} +: {w}];")
        off += w
    L.append("  endtask")
    L.append("")
    L.append("  always_comb begin")
    off = 0
    for name, w in out_lay:
        src = {"req_ready": "req_ready_o", "rsp_valid": "rsp_valid_o", "rsp": "rsp_o"}.get(name, name)
        L.append(f"    got[{off} +: {w}] = {src};")
        off += w
    L.append("  end")
    L.append("")
    L.append("  task automatic compare(input int c);")
    L.append("    logic [OUT_W-1:0] diff;")
    L.append("    diff = (got ^ exp) & msk;")
    L.append("    checks += $countones(msk);")
    L.append("    if (diff != '0) begin")
    L.append("      errors++;")
    off = 0
    for name, w in out_lay:
        L.append(f"      if (diff[{off} +: {w}] != '0) $display(\"MISMATCH cycle %0d {name}: got=%h exp=%h\", c, got[{off} +: {w}], exp[{off} +: {w}]);")
        off += w
    L.append("    end")
    L.append("  endtask")
    L.append("")
    L.append("  initial begin")
    L.append("    errors = 0; checks = 0;")
    L.append("    rst_ni = 1'b0; req_valid_i = 1'b0; rsp_ready_i = 1'b1; req_i = '0;")
    for p in m.hw_ports:
        if p.direction == "input":
            L.append(f"    {p.name} = '0;")
    L.append("    if (!$value$plusargs(\"STIM=%s\", f_stim)) $fatal(1, \"missing +STIM\");")
    L.append("    if (!$value$plusargs(\"EXP=%s\",  f_exp))  $fatal(1, \"missing +EXP\");")
    L.append("    if (!$value$plusargs(\"MASK=%s\", f_msk))  $fatal(1, \"missing +MASK\");")
    L.append("    $readmemh(f_stim, stim_mem);")
    L.append("    $readmemh(f_exp,  exp_mem);")
    L.append("    $readmemh(f_msk,  msk_mem);")
    L.append("    for (cyc = 0; cyc < NCYC; cyc++) begin")
    L.append("      @(negedge clk_i);")
    L.append("      stim = stim_mem[cyc];")
    L.append("      exp  = exp_mem[cyc];")
    L.append("      msk  = msk_mem[cyc];")
    L.append("      apply(stim);")
    L.append("      #3;")
    L.append("      compare(cyc);")
    L.append("    end")
    L.append("    @(negedge clk_i);")
    L.append("    if (errors == 0) $display(\"TB_RESULT: PASS cycles=%0d checks=%0d\", NCYC, checks);")
    L.append("    else             $display(\"TB_RESULT: FAIL cycles=%0d errors=%0d\", NCYC, errors);")
    L.append("    $finish;")
    L.append("  end")
    L.append("endmodule")
    L.append("")
    L.append("`default_nettype wire")
    return "\n".join(L) + "\n"


def emit_addr_dump(m: RegMap) -> str:
    L = [header(m, "tb_addr_dump.sv -- prints every address-map constant of sf_reg_pkg"), "`default_nettype none",
         "module tb_addr_dump;", "  initial begin"]
    L.append(f"    $display(\"SV_MAP_HASH %016h\", sf_reg_pkg::SF_REG_MAP_HASH);")
    for p in m.peripherals:
        n = p.name.upper()
        L.append(f"    $display(\"SV_PERIPH {p.name} %016h %016h %02h\", sf_reg_pkg::SF_{n}_BASE, sf_reg_pkg::SF_{n}_SIZE, sf_reg_pkg::SF_{n}_REGION_ATTR);")
    for i in m.instances:
        u = i.name.upper()
        L.append(f"    $display(\"SV_REG {i.name} %016h {i.reg.width} %0h\", sf_reg_pkg::SF_{u}_ADDR, sf_reg_pkg::SF_{u}_RESET);")
    L.append("    $finish;")
    L.append("  end")
    L.append("endmodule")
    L.append("`default_nettype wire")
    return "\n".join(L) + "\n"
