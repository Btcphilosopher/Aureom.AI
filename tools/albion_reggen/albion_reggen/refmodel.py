"""Independent cycle-level reference model of the generated register bank.

This is a second implementation of the register semantics, written from the
specification (docs/ARCHITECTURE.md, docs/SCHEMA.md) against the *validated
model* -- it never reads generated SystemVerilog.  The verification flow uses
it twice: to generate stimulus whose acceptance behaviour is correct by
construction, and to produce the expected value of every output in every cycle.
If the generated RTL and this model agree on millions of checked values, the
RTL implements the documented semantics; if either is wrong the two diverge.

Cycle semantics (all values are those seen just before the rising edge)
----------------------------------------------------------------------
* ``req_ready = !rsp_valid || rsp_ready``
* a request is accepted when ``req_valid && req_ready``; its whole effect
  (field updates, pulses, strobes, response contents) is decided in that cycle
  from the state *before* the edge and the hardware inputs of that cycle;
* hardware outputs are the flip-flop values, so an effect is visible to
  hardware in the cycle after acceptance; ``irq`` is combinational from those
  flip-flops (and from live ``ro`` input fields used as interrupt sources).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .model import RegInst, RegMap

# ALP v1 constants (cross-checked against sf_albion_pkg.sv by alpcheck.py)
OP_NONE, OP_READ, OP_WRITE = 0, 1, 2
ST = {"OKAY": 0, "DECODE_ERR": 1, "ACCESS_DENIED": 2, "BAD_OPCODE": 3, "BAD_BE": 4,
      "ALIGN_ERR": 5, "BAD_ATTR": 6, "TARGET_ERR": 7}
ST_NAME = {v: k for k, v in ST.items()}
DOM_INVALID = 0xFF
MEM_DEVICE = 2


def expand_be(be: int) -> int:
    m = 0
    for b in range(16):
        if (be >> b) & 1:
            m |= 0xFF << (8 * b)
    return m


@dataclass
class Req:
    op: int = OP_READ
    tag: int = 0
    dom: int = 0x01
    attr: int = 0x06        # priv=1, mem_type=DEVICE(2): a well-formed privileged device access
    addr: int = 0
    be: int = 0xFFFF
    data: int = 0
    #: hardware inputs to force in the cycle this request is accepted: ((port, bit offset, width, value), ...)
    force: tuple = ()

    def pack(self) -> int:
        """Flat 236-bit sf_req_t: op[235:232] tag dom attr addr be data."""
        return ((self.op & 0xF) << 232 | (self.tag & 0xFF) << 224 | (self.dom & 0xFF) << 216
                | (self.attr & 0xFF) << 208 | (self.addr & ((1 << 64) - 1)) << 144
                | (self.be & 0xFFFF) << 128 | (self.data & ((1 << 128) - 1)))


@dataclass
class Inputs:
    rst_n: int = 1
    req_valid: int = 0
    req: Req = field(default_factory=Req)
    rsp_ready: int = 1
    hw: Dict[str, int] = field(default_factory=dict)


@dataclass
class Rsp:
    tag: int = 0
    status: int = 0
    is_write: int = 0
    data: int = 0

    def pack(self) -> int:
        """Flat 148-bit sf_rsp_t: tag[147:140] status[139:136] meta[135:128] data."""
        meta = 0x2 | (self.is_write & 1)          # last=1
        return (self.tag & 0xFF) << 140 | (self.status & 0xF) << 136 | meta << 128 | (self.data & ((1 << 128) - 1))


@dataclass
class Outputs:
    req_ready: int
    rsp_valid: int
    rsp: Rsp
    hw: Dict[str, int]


def legality(r: Req) -> int:
    if r.op not in (OP_READ, OP_WRITE):
        return ST["BAD_OPCODE"]
    if r.addr & 0xF:
        return ST["ALIGN_ERR"]
    if r.be == 0:
        return ST["BAD_BE"]
    if (r.attr & 0x80) or (r.attr & 3) == 3:
        return ST["BAD_ATTR"]
    if r.dom == DOM_INVALID:
        return ST["ACCESS_DENIED"]
    return ST["OKAY"]


def region_check(attr_byte: int, r: Req) -> int:
    """sf_access_check_bits: permission, exec, privilege, security, then memory type."""
    ra_read, ra_write, ra_exec = attr_byte & 1, (attr_byte >> 1) & 1, (attr_byte >> 2) & 1
    ra_priv, ra_sec, ra_mem = (attr_byte >> 3) & 1, (attr_byte >> 4) & 1, (attr_byte >> 6) & 3
    a_mem, a_priv, a_sec, a_instr = r.attr & 3, (r.attr >> 2) & 1, (r.attr >> 3) & 1, (r.attr >> 4) & 1
    if r.op == OP_READ and not ra_read:
        return ST["ACCESS_DENIED"]
    if r.op == OP_WRITE and not ra_write:
        return ST["ACCESS_DENIED"]
    if a_instr and not ra_exec:
        return ST["ACCESS_DENIED"]
    if ra_priv and not a_priv:
        return ST["ACCESS_DENIED"]
    if ra_sec and not a_sec:
        return ST["ACCESS_DENIED"]
    if ra_mem == MEM_DEVICE and a_mem != MEM_DEVICE:
        return ST["BAD_ATTR"]
    return ST["OKAY"]


class RefModel:
    def __init__(self, m: RegMap):
        self.m = m
        self.running = False
        self.why = ""
        self.pname = ""
        self.cov: Counter = Counter()
        self._by_word: Dict[int, List[RegInst]] = {}
        for i in m.instances:
            self._by_word.setdefault(i.word_addr, []).append(i)
        self._ports = {p.name: p for p in m.hw_ports}
        self._attr = {p.name: m.periph_attr_byte(p) for p in m.peripherals}
        self.reset()

    # ---------------------------------------------------------------- state
    def reset(self) -> None:
        self.q: Dict[Tuple[int, str], int] = {}       # (inst, field) -> flop value
        self.pulse: Dict[Tuple[int, str], int] = {}   # w1p pulse flops
        self.wr_q: Dict[int, int] = {}
        self.rd_q: Dict[int, int] = {}
        for i in self.m.instances:
            for f in i.reg.fields:
                if f.has_storage:
                    self.q[(i.index, f.name)] = f.reset
                if f.access == "w1p":
                    self.pulse[(i.index, f.name)] = 0
            self.wr_q[i.index] = 0
            self.rd_q[i.index] = 0
        self.rsp_valid = 0
        self.rsp = Rsp()

    # ----------------------------------------------------------- hw helpers
    def _hw(self, inp: Inputs, port: str) -> int:
        return inp.hw.get(port, 0)

    def _slice(self, inp: Inputs, port: str, elem: int, width: int) -> int:
        return (self._hw(inp, port) >> (elem * width)) & ((1 << width) - 1)

    def _port(self, i: RegInst, fld: str, kind: str) -> str:
        for p in self.m.hw_ports:
            if (p.periph, p.reg, p.field, p.kind) == (i.periph.name, i.reg.name, fld, kind):
                return p.name
        raise KeyError((i.name, fld, kind))

    def _field_read(self, i: RegInst, f, inp: Inputs) -> int:
        if f.access == "ro" and f.hw == "const":
            return f.reset
        if f.access == "ro" and f.hw == "input":
            return self._slice(inp, self._port(i, f.name, "value"), i.elem, f.width)
        if f.access in ("ro", "rw", "w1c", "w1s"):
            return self.q[(i.index, f.name)]
        return 0   # wo, w1p

    def _reg_read(self, i: RegInst, inp: Inputs) -> int:
        v = 0
        for f in i.reg.fields:
            v |= self._field_read(i, f, inp) << f.lsb
        return v

    # -------------------------------------------------------------- outputs
    def comb(self, inp: Inputs) -> Outputs:
        if not inp.rst_n:
            self.reset()
        hw: Dict[str, int] = {}
        for p in self.m.hw_ports:
            if p.direction == "output":
                hw[p.name] = 0
        for i in self.m.instances:
            for f in i.reg.fields:
                sh = i.elem * f.width
                if f.access in ("rw", "w1c", "w1s") or (f.access == "wo" and f.hw == "out"):
                    hw[self._port(i, f.name, "value")] |= self.q[(i.index, f.name)] << sh
                elif f.access == "w1p":
                    hw[self._port(i, f.name, "pulse")] |= self.pulse[(i.index, f.name)] << sh
            if i.reg.wr_strobe:
                hw[self._port(i, "", "wr_strobe")] |= self.wr_q[i.index] << i.elem
            if i.reg.rd_strobe:
                hw[self._port(i, "", "rd_strobe")] |= self.rd_q[i.index] << i.elem
        for p in self.m.peripherals:
            terms = 0
            for i in self.m.instances:
                if i.periph.name != p.name:
                    continue
                for f in i.reg.fields:
                    if f.interrupt_enable is None:
                        continue
                    er, ef = f.interrupt_enable
                    ei = next(x for x in self.m.instances if x.periph.name == p.name and x.reg.name == er and x.elem == 0)
                    s = self._field_read(i, f, inp) if not (f.access == "ro" and f.hw == "input") else \
                        self._slice(inp, self._port(i, f.name, "value"), i.elem, f.width)
                    terms |= s & self.q[(ei.index, ef)]
            if any(q.kind == "irq" and q.periph == p.name for q in self.m.hw_ports):
                hw[f"{p.name}_irq_o"] = 1 if terms else 0
        return Outputs(req_ready=1 if (not self.rsp_valid or inp.rsp_ready) else 0,
                       rsp_valid=self.rsp_valid, rsp=self.rsp, hw=hw)

    # ------------------------------------------------------------ evaluation
    def evaluate(self, r: Req, inp: Inputs) -> Tuple[int, int, List[RegInst]]:
        """Decide status and read data for a request (state before the edge)."""
        self.why = "legality"
        st = legality(r)
        if st != 0:
            return st, 0, []
        per = next((p for p in self.m.peripherals if p.base <= r.addr < p.end), None)
        if per is None:
            self.why = "unmapped"
            return ST["DECODE_ERR"], 0, []
        self.pname = per.name
        st = region_check(self._attr[per.name], r)
        if st != 0:
            self.why = "region"
            return st, 0, []
        word = self._by_word.get(r.addr, [])
        touched = [i for i in word if i.lanemask & r.be]
        covered = 0
        for i in word:
            covered |= i.lanemask
        if r.be & ~covered & 0xFFFF:
            self.why = "hole"
            return ST["DECODE_ERR"], 0, []
        if r.op == OP_WRITE and any(not i.reg.writable for i in touched):
            self.why = "perm"
            return ST["ACCESS_DENIED"], 0, []
        if r.op == OP_READ and any(not i.reg.readable for i in touched):
            self.why = "perm"
            return ST["ACCESS_DENIED"], 0, []
        if r.op == OP_WRITE:
            for i in touched:
                if i.reg.write_gate and not self._slice(inp, self._port(i, "", "gate"), i.elem, 1):
                    self.why = "gate"
                    for j in touched:
                        if j.reg.write_gate and not self._slice(inp, self._port(j, "", "gate"), j.elem, 1):
                            self.cov[f"gate_refused:{j.name}"] += 1
                    return ST["TARGET_ERR"], 0, touched
        self.why = "ok"
        data = 0
        if r.op == OP_READ:
            for i in touched:
                data |= self._reg_read(i, inp) << (8 * i.lane0)
            data &= expand_be(r.be)
        return ST["OKAY"], data, touched

    # ------------------------------------------------------------------ edge
    def step(self, inp: Inputs) -> None:
        if not inp.rst_n:
            if self.running:
                self.cov["reset:mid_run"] += 1
            self.running = False
            self.reset()
            return
        self.running = True
        out_ready = (not self.rsp_valid) or inp.rsp_ready
        accept = bool(inp.req_valid and out_ready)
        status, rdata, touched = 0, 0, []
        wr_ok = rd_ok = False
        if accept:
            status, rdata, touched = self.evaluate(inp.req, inp)
            wr_ok = status == 0 and inp.req.op == OP_WRITE
            rd_ok = status == 0 and inp.req.op == OP_READ
            self.cov[f"status:{ST_NAME[status]}"] += 1
            if self.why in ("region", "hole", "perm", "gate"):
                self.cov[f"why:{self.why}:{self.pname}"] += 1
            elif self.why == "unmapped":
                self.cov["why:unmapped"] += 1
            for ti in touched:
                if status == 0:
                    self.cov[("readreg:" if inp.req.op == OP_READ else "writereg:") + ti.name] += 1
            self.cov["op:write" if inp.req.op == OP_WRITE else "op:read" if inp.req.op == OP_READ else "op:other"] += 1
        touched_idx = {i.index for i in touched}
        wdata_all = inp.req.data
        be = inp.req.be
        newq = dict(self.q)
        newpulse: Dict[Tuple[int, str], int] = {}
        for i in self.m.instances:
            sw_here = wr_ok and i.index in touched_idx
            w = i.reg.width
            wd = (wdata_all >> (8 * i.lane0)) & ((1 << w) - 1)
            wm = (expand_be(be) >> (8 * i.lane0)) & ((1 << w) - 1)
            for f in i.reg.fields:
                fm = (1 << f.width) - 1
                wb = (wd >> f.lsb) & fm
                fmk = (wm >> f.lsb) & fm
                key = (i.index, f.name)
                if f.access == "w1p":
                    newpulse[key] = (wb & fmk) if sw_here else 0
                    if sw_here and (wb & fmk):
                        self.cov[f"fieldop:{i.periph.name}.{i.reg.name}.{f.name}:pulse"] += 1
                    continue
                if not f.has_storage:
                    continue
                q = self.q[key]
                if f.access in ("rw", "wo"):
                    swe = sw_here and fmk != 0
                    nxt_sw = (q & ~fmk) | (wb & fmk)
                    hwe, hwd = 0, 0
                    if f.access == "rw" and f.hw == "update":
                        hwe = self._slice(inp, self._port(i, f.name, "hw_we"), i.elem, 1)
                        hwd = self._slice(inp, self._port(i, f.name, "hw_wdata"), i.elem, f.width)
                    nxt = q
                    if hwe:
                        self.cov[f"hwupd:{i.periph.name}.{i.reg.name}.{f.name}"] += 1
                    if hwe and swe:
                        self.cov[f"conflict:{i.periph.name}.{i.reg.name}.{f.name}:{f.precedence}"] += 1
                    if f.precedence == "sw":
                        nxt = nxt_sw if swe else (hwd if hwe else q)
                    else:
                        nxt = hwd if hwe else (nxt_sw if swe else q)
                    if swe:
                        self.cov[f"fieldop:{i.periph.name}.{i.reg.name}.{f.name}:write"] += 1
                    newq[key] = nxt
                elif f.access == "w1c":
                    clr = (wb & fmk) if sw_here else 0
                    st_ = self._slice(inp, self._port(i, f.name, "event"), i.elem, f.width) if f.hw == "event" else 0
                    if st_:
                        self.cov[f"hwupd:{i.periph.name}.{i.reg.name}.{f.name}"] += 1
                    if clr & st_:
                        self.cov[f"conflict:{i.periph.name}.{i.reg.name}.{f.name}:{f.precedence}"] += 1
                    if clr & q:
                        self.cov[f"fieldop:{i.periph.name}.{i.reg.name}.{f.name}:clear"] += 1
                    newq[key] = ((q & ~clr) | st_) if f.precedence != "sw" else ((q | st_) & ~clr)
                elif f.access == "w1s":
                    setb = (wb & fmk) if sw_here else 0
                    clv = self._slice(inp, self._port(i, f.name, "event"), i.elem, f.width) if f.hw == "event" else 0
                    if clv:
                        self.cov[f"hwupd:{i.periph.name}.{i.reg.name}.{f.name}"] += 1
                    if setb & clv:
                        self.cov[f"conflict:{i.periph.name}.{i.reg.name}.{f.name}:{f.precedence}"] += 1
                    if setb:
                        self.cov[f"fieldop:{i.periph.name}.{i.reg.name}.{f.name}:set"] += 1
                    newq[key] = ((q | setb) & ~clv) if f.precedence != "sw" else ((q & ~clv) | setb)
                elif f.access == "ro" and f.hw == "update":
                    if self._slice(inp, self._port(i, f.name, "hw_we"), i.elem, 1):
                        self.cov[f"hwupd:{i.periph.name}.{i.reg.name}.{f.name}"] += 1
                        newq[key] = self._slice(inp, self._port(i, f.name, "hw_wdata"), i.elem, f.width)
        for i in self.m.instances:
            self.wr_q[i.index] = 1 if (wr_ok and i.index in touched_idx) else 0
            self.rd_q[i.index] = 1 if (rd_ok and i.index in touched_idx) else 0
            if self.wr_q[i.index] and i.reg.wr_strobe:
                self.cov[f"strobe:{i.periph.name}.{i.reg.name}:wr"] += 1
            if self.rd_q[i.index] and i.reg.rd_strobe:
                self.cov[f"strobe:{i.periph.name}.{i.reg.name}:rd"] += 1
        self.q = newq
        self.pulse = newpulse
        if accept:
            self.rsp_valid = 1
            self.rsp = Rsp(tag=inp.req.tag, status=status,
                           is_write=1 if inp.req.op == OP_WRITE else 0,
                           data=rdata if (status == 0 and inp.req.op == OP_READ) else 0)
        elif inp.rsp_ready:
            self.rsp_valid = 0
        if self.rsp_valid and not inp.rsp_ready:
            self.cov["stall:response_held"] += 1
        if inp.req_valid and not out_ready:
            self.cov["stall:request_held"] += 1


def required_coverage(m: RegMap) -> List[str]:
    """Every coverage point a complete run must hit.  Anything listed by
    :func:`missing_coverage` after a run is behaviour the stimulus never reached."""
    req: List[str] = [f"status:{k}" for k in ST] + ["op:read", "op:write", "op:other", "stall:request_held",
                                                   "stall:response_held", "reset:mid_run", "why:unmapped"]
    for p in m.peripherals:
        req.append(f"why:region:{p.name}")
        insts = [i for i in m.instances if i.periph.name == p.name]
        words = {i.word_addr for i in insts}
        if any(p.base + off not in words for off in range(0, p.size, 16)):
            req.append(f"why:hole:{p.name}")
        if any((not i.reg.writable) or (not i.reg.readable) for i in insts):
            req.append(f"why:perm:{p.name}")
        if any(i.reg.write_gate for i in insts):
            req.append(f"why:gate:{p.name}")
    for i in m.instances:
        if i.reg.readable:
            req.append(f"readreg:{i.name}")
        if i.reg.writable:
            req.append(f"writereg:{i.name}")
        if i.reg.write_gate:
            req.append(f"gate_refused:{i.name}")
        if i.reg.wr_strobe:
            req.append(f"strobe:{i.periph.name}.{i.reg.name}:wr")
        if i.reg.rd_strobe:
            req.append(f"strobe:{i.periph.name}.{i.reg.name}:rd")
    seen = set()
    for i in m.instances:
        for f in i.reg.fields:
            key = f"{i.periph.name}.{i.reg.name}.{f.name}"
            if key in seen:
                continue
            seen.add(key)
            if f.access in ("rw", "wo") and f.has_storage:
                req.append(f"fieldop:{key}:write")
            elif f.access == "w1c":
                req.append(f"fieldop:{key}:clear")
            elif f.access == "w1s":
                req.append(f"fieldop:{key}:set")
            elif f.access == "w1p":
                req.append(f"fieldop:{key}:pulse")
            if f.access in ("w1c", "w1s") and f.hw == "event":
                req.append(f"hwupd:{key}")
            if f.access == "w1c" and f.hw == "event":
                req.append(f"conflict:{key}:{f.precedence}")
            if f.access == "w1s" and f.hw == "event":
                req.append(f"conflict:{key}:{f.precedence}")
            if (f.access == "rw" and f.hw == "update"):
                req.append(f"hwupd:{key}")
                req.append(f"conflict:{key}:{f.precedence}")
            if f.access == "ro" and f.hw == "update":
                req.append(f"hwupd:{key}")
    return sorted(set(req))


def missing_coverage(m: RegMap, cov: Counter) -> List[str]:
    return [k for k in required_coverage(m) if cov.get(k, 0) == 0]
