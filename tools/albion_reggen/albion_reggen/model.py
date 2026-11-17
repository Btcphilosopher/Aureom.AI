"""Normalised, immutable register model.

The validator produces a :class:`RegMap`; every emitter and the independent
reference model consume *only* this object.  That single funnel is what makes
"RTL, C, Rust and documentation derive from the same validated definition" a
structural property rather than a promise.

Terminology
-----------
register      one named register entry of a peripheral (possibly an array)
instance      one concrete register (array element) at a concrete address
field         a bit range of a register with an access type
hw port       a signal of the generated ``sf_reg_bank`` on the hardware side
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Access types
# --------------------------------------------------------------------------
#: ro   software read-only
#: rw   software read/write
#: wo   software write-only (reads 0)
#: w1c  write-one-to-clear
#: w1s  write-one-to-set
#: w1p  write-one-to-pulse: a 1 written produces a one-cycle hardware pulse,
#:      reads 0, holds no state
ACCESS_TYPES = ("ro", "rw", "wo", "w1c", "w1s", "w1p")
READABLE = ("ro", "rw", "w1c", "w1s")
WRITABLE = ("rw", "wo", "w1c", "w1s", "w1p")

#: hardware-interface option per access type (first entry is the default)
HW_OPTIONS = {
    "ro": ("const", "input", "update"),
    "rw": ("none", "update"),
    "wo": ("out", "none"),
    "w1c": ("event", "none"),
    "w1s": ("event", "none"),
    "w1p": ("pulse",),
}

#: ALP v1 memory types (sf_mem_type_e)
MEM_TYPES = {"normal_wb": 0, "normal_nc": 1, "device": 2}


@dataclass(frozen=True)
class Field:
    name: str
    lsb: int
    width: int
    access: str
    hw: str
    reset: int
    reset_symbol: Optional[str]
    precedence: str                      # 'hw' | 'sw' | '' (not applicable)
    interrupt_enable: Optional[Tuple[str, str]]   # (REG, FIELD) in same peripheral
    description: str
    connect: Tuple[Tuple[str, str], ...] = ()

    @property
    def msb(self) -> int:
        return self.lsb + self.width - 1

    @property
    def mask(self) -> int:
        return ((1 << self.width) - 1) << self.lsb

    @property
    def has_storage(self) -> bool:
        if self.access in ("rw", "w1c", "w1s"):
            return True
        if self.access == "wo":
            return self.hw == "out"
        if self.access == "ro":
            return self.hw == "update"
        return False


@dataclass(frozen=True)
class Register:
    name: str
    offset: int
    width: int
    count: int
    stride: int
    fields: Tuple[Field, ...]
    wr_strobe: bool
    rd_strobe: bool
    write_gate: bool
    description: str
    reserved_doc: Tuple[Tuple[int, int], ...] = ()
    connect: Tuple[Tuple[str, str], ...] = ()

    @property
    def nbytes(self) -> int:
        return self.width // 8

    @property
    def readable(self) -> bool:
        return any(f.access in READABLE for f in self.fields)

    @property
    def writable(self) -> bool:
        return any(f.access in WRITABLE for f in self.fields)

    @property
    def reset(self) -> int:
        v = 0
        for f in self.fields:
            if f.access == "ro" and f.hw == "input":
                continue
            if f.access == "w1p" or (f.access == "wo" and f.hw == "none"):
                continue
            v |= (f.reset << f.lsb)
        return v

    @property
    def field_mask(self) -> int:
        m = 0
        for f in self.fields:
            m |= f.mask
        return m

    @property
    def rmw_safe(self) -> bool:
        """True if firmware may use read-modify-write helpers on this register.

        Not safe when a read has a side effect (rd_strobe) or when a stored
        write-only field exists (it reads back 0, so a read-back cannot
        reproduce it)."""
        return (not self.rd_strobe) and not any(f.access == "wo" and f.hw == "out" for f in self.fields)

    @property
    def reserved_mask(self) -> int:
        return ((1 << self.width) - 1) & ~self.field_mask

    def mask_of(self, *accesses: str) -> int:
        m = 0
        for f in self.fields:
            if f.access in accesses:
                m |= f.mask
        return m


@dataclass(frozen=True)
class Region:
    name: str
    base: int
    size: int
    asid: str
    read: bool
    write: bool
    exec: bool
    priv_only: bool
    secure_only: bool
    cacheable: bool
    mem_type: str
    owner: str
    proposed: bool                       # defined by this map, not by the ALP catalogue

    @property
    def attr_byte(self) -> int:
        """sf_region_attr_t as laid out in sf_albion_pkg (SF_RATTR_*)."""
        return ((MEM_TYPES[self.mem_type] << 6) | (int(self.cacheable) << 5)
                | (int(self.secure_only) << 4) | (int(self.priv_only) << 3)
                | (int(self.exec) << 2) | (int(self.write) << 1) | int(self.read))


@dataclass(frozen=True)
class RtlModule:
    module: str
    archive: str
    path: str
    sha256: str
    ports: Tuple[Tuple[str, str], ...]   # (port, 'input'|'output')
    role: str = "attach"                 # 'attach': bank sits beside the block; 'replace': bank replaces its register slave


@dataclass(frozen=True)
class Peripheral:
    name: str
    description: str
    region: str
    base: int
    size: int
    priv_only: bool
    secure_only: bool
    registers: Tuple[Register, ...]
    rtl_status: str
    rtl_summary: str
    rtl_modules: Tuple[RtlModule, ...]
    examples: Tuple[Any, ...]
    source: str
    connect: Tuple[Tuple[str, str], ...] = ()

    @property
    def end(self) -> int:
        return self.base + self.size


@dataclass(frozen=True)
class RegInst:
    index: int
    periph: Peripheral
    reg: Register
    elem: int
    offset: int            # relative to the peripheral base
    addr: int              # absolute bus address

    @property
    def name(self) -> str:
        """Flat lower-case identifier, e.g. ``sramc_ctrl`` or ``vector_desc_3``."""
        base = f"{self.periph.name}_{self.reg.name.lower()}"
        return f"{base}_{self.elem}" if self.reg.count > 1 else base

    @property
    def word_addr(self) -> int:
        return self.addr & ~0xF

    @property
    def lane0(self) -> int:
        return self.addr & 0xF

    @property
    def lanemask(self) -> int:
        return ((1 << self.reg.nbytes) - 1) << self.lane0


@dataclass(frozen=True)
class HwPort:
    name: str
    direction: str         # 'input' | 'output' (as seen by sf_reg_bank)
    width: int
    kind: str              # value|hw_we|hw_wdata|event|pulse|wr_strobe|rd_strobe|gate|irq
    periph: str
    reg: str               # '' for peripheral-level ports
    field: str             # '' for register-level ports
    count: int
    doc: str


@dataclass(frozen=True)
class RegMap:
    name: str
    version: Tuple[int, int]
    description: str
    regions: Tuple[Region, ...]
    peripherals: Tuple[Peripheral, ...]
    source_files: Tuple[Tuple[str, str], ...]
    semantic_hash: str = ""
    definition_hash: str = ""
    instances: Tuple[RegInst, ...] = dc_field(default=(), compare=False)
    hw_ports: Tuple[HwPort, ...] = dc_field(default=(), compare=False)

    def region(self, name: str) -> Region:
        for r in self.regions:
            if r.name == name:
                return r
        raise KeyError(name)

    def periph(self, name: str) -> Peripheral:
        for p in self.peripherals:
            if p.name == name:
                return p
        raise KeyError(name)

    def periph_attr_byte(self, p: Peripheral) -> int:
        """Effective region attribute byte for a peripheral (region + tightening)."""
        r = self.region(p.region)
        return Region(r.name, r.base, r.size, r.asid, r.read, r.write, r.exec,
                      r.priv_only or p.priv_only, r.secure_only or p.secure_only,
                      r.cacheable, r.mem_type, r.owner, r.proposed).attr_byte

    @property
    def hash64(self) -> int:
        """First 8 bytes of the semantic hash, big-endian: the value firmware
        reads from the SYSID REGMAP_HASH register."""
        return int(self.semantic_hash[:16], 16)

    @property
    def max_end(self) -> int:
        return max(p.end for p in self.peripherals)


# --------------------------------------------------------------------------
# Derived structures
# --------------------------------------------------------------------------
def build_instances(periphs: Tuple[Peripheral, ...]) -> Tuple[RegInst, ...]:
    out: List[RegInst] = []
    for p in sorted(periphs, key=lambda x: x.base):
        items = []
        for r in p.registers:
            for e in range(r.count):
                items.append((r.offset + e * r.stride, r, e))
        items.sort(key=lambda t: (t[0], t[2]))
        for off, r, e in items:
            out.append(RegInst(len(out), p, r, e, off, p.base + off))
    return tuple(out)


def build_hw_ports(periphs: Tuple[Peripheral, ...]) -> Tuple[HwPort, ...]:
    ports: List[HwPort] = []
    for p in sorted(periphs, key=lambda x: x.base):
        has_irq = False
        for r in sorted(p.registers, key=lambda x: x.offset):
            n = r.count
            base = f"{p.name}_{r.name.lower()}"
            for f in r.fields:
                fb = f"{base}_{f.name.lower()}"
                w = f.width * n
                tag = f"{p.name}.{r.name}.{f.name}"
                if f.interrupt_enable is not None:
                    has_irq = True
                a, h = f.access, f.hw
                if a == "ro" and h == "input":
                    ports.append(HwPort(fb + "_i", "input", w, "value", p.name, r.name, f.name, n,
                                        f"live status value read by software ({tag})"))
                elif a == "ro" and h == "update":
                    ports.append(HwPort(fb + "_hw_we_i", "input", n, "hw_we", p.name, r.name, f.name, n,
                                        f"hardware write enable ({tag})"))
                    ports.append(HwPort(fb + "_hw_wdata_i", "input", w, "hw_wdata", p.name, r.name, f.name, n,
                                        f"hardware write data ({tag})"))
                elif a == "rw":
                    ports.append(HwPort(fb + "_o", "output", w, "value", p.name, r.name, f.name, n,
                                        f"software-controlled value ({tag})"))
                    if h == "update":
                        ports.append(HwPort(fb + "_hw_we_i", "input", n, "hw_we", p.name, r.name, f.name, n,
                                            f"hardware write enable ({tag})"))
                        ports.append(HwPort(fb + "_hw_wdata_i", "input", w, "hw_wdata", p.name, r.name, f.name, n,
                                            f"hardware write data ({tag})"))
                elif a == "wo" and h == "out":
                    ports.append(HwPort(fb + "_o", "output", w, "value", p.name, r.name, f.name, n,
                                        f"last value written by software ({tag})"))
                elif a == "w1c":
                    ports.append(HwPort(fb + "_o", "output", w, "value", p.name, r.name, f.name, n,
                                        f"sticky flag level ({tag})"))
                    if h == "event":
                        ports.append(HwPort(fb + "_set_i", "input", w, "event", p.name, r.name, f.name, n,
                                            f"per-bit hardware set event ({tag})"))
                elif a == "w1s":
                    ports.append(HwPort(fb + "_o", "output", w, "value", p.name, r.name, f.name, n,
                                        f"flag level ({tag})"))
                    if h == "event":
                        ports.append(HwPort(fb + "_clr_i", "input", w, "event", p.name, r.name, f.name, n,
                                            f"per-bit hardware clear event ({tag})"))
                elif a == "w1p":
                    ports.append(HwPort(fb + "_pulse_o", "output", w, "pulse", p.name, r.name, f.name, n,
                                        f"one-cycle pulse per written 1 ({tag})"))
            if r.wr_strobe:
                ports.append(HwPort(base + "_wr_o", "output", n, "wr_strobe", p.name, r.name, "", n,
                                    f"one-cycle strobe per accepted write ({p.name}.{r.name})"))
            if r.rd_strobe:
                ports.append(HwPort(base + "_rd_o", "output", n, "rd_strobe", p.name, r.name, "", n,
                                    f"one-cycle strobe per accepted read ({p.name}.{r.name})"))
            if r.write_gate:
                ports.append(HwPort(base + "_wgate_i", "input", n, "gate", p.name, r.name, "", n,
                                    f"write gate: low refuses the write with TARGET_ERR ({p.name}.{r.name})"))
        if has_irq:
            ports.append(HwPort(f"{p.name}_irq_o", "output", 1, "irq", p.name, "", "", 1,
                                f"level interrupt: OR of enabled interrupt fields ({p.name})"))
    return tuple(ports)


# --------------------------------------------------------------------------
# Canonical form and hashes
# --------------------------------------------------------------------------
def _field_dict(f: Field, semantic: bool) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "name": f.name, "lsb": f.lsb, "width": f.width, "access": f.access,
        "hw": f.hw, "reset": f.reset if f.reset_symbol is None else "$" + f.reset_symbol,
        "precedence": f.precedence,
        "interrupt_enable": list(f.interrupt_enable) if f.interrupt_enable else None,
    }
    if not semantic:
        d["description"] = f.description
        d["connect"] = [list(c) for c in f.connect]
    return d


def _reg_dict(r: Register, semantic: bool) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "name": r.name, "offset": r.offset, "width": r.width, "count": r.count,
        "stride": r.stride, "wr_strobe": r.wr_strobe, "rd_strobe": r.rd_strobe,
        "write_gate": r.write_gate,
        "fields": [_field_dict(f, semantic) for f in r.fields],
    }
    if not semantic:
        d["description"] = r.description
        d["reserved_doc"] = [list(x) for x in r.reserved_doc]
        d["connect"] = [list(c) for c in r.connect]
    return d


def canonical_dict(m: "RegMap", semantic: bool) -> Dict[str, Any]:
    """Canonical content.  ``semantic=True`` keeps only what changes hardware
    behaviour or firmware-visible numbers (addresses, widths, access, reset,
    hardware options, region attributes); descriptions, examples and RTL
    provenance are excluded so editing prose never changes the ID register."""
    regions = []
    used = {p.region for p in m.peripherals}
    for r in sorted(m.regions, key=lambda x: x.base):
        if semantic and r.name not in used:
            continue
        regions.append({"name": r.name, "base": r.base, "size": r.size, "attr": r.attr_byte})
    periphs = []
    for p in sorted(m.peripherals, key=lambda x: x.base):
        pd: Dict[str, Any] = {
            "name": p.name, "region": p.region, "base": p.base, "size": p.size,
            "attr": m.periph_attr_byte(p),
            "registers": [_reg_dict(r, semantic) for r in sorted(p.registers, key=lambda x: x.offset)],
        }
        if not semantic:
            pd["description"] = p.description
            pd["rtl"] = {
                "status": p.rtl_status, "summary": p.rtl_summary,
                "modules": [{"module": x.module, "archive": x.archive, "path": x.path,
                             "sha256": x.sha256, "role": x.role, "ports": [list(q) for q in x.ports]}
                            for x in p.rtl_modules],
            }
            pd["examples"] = list(p.examples)
            pd["connect"] = [list(c) for c in p.connect]
        periphs.append(pd)
    d: Dict[str, Any] = {"map": m.name, "version": list(m.version),
                         "regions": regions, "peripherals": periphs}
    if not semantic:
        d["description"] = m.description
    return d


def digest(obj: Any) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()
