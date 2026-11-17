"""Validation and normalisation: raw document -> :class:`RegMap`.

All problems are collected (never fail-fast) and reported with a stable
``E_*`` code and a location such as ``dma.registers[CTRL].fields[GO]``.
Nothing is generated from a definition that has any error.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from . import SCHEMA_VERSION
from .errors import Collector, RegDefError
from .loader import Source
from .model import (ACCESS_TYPES, HW_OPTIONS, MEM_TYPES, READABLE, WRITABLE, Field,
                    HwPort, Peripheral, RegInst, RegMap, Register, Region, RtlModule,
                    build_hw_ports, build_instances, canonical_dict, digest)
from .regions import (NAME_RE as LOWER_NAME_RE, check_region, is_pow2, load_catalogue)

UPPER_NAME_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
MAX_NAME = 40
SYMBOLS = ("regmap_hash",)

RUST_KEYWORDS = {
    "as", "break", "const", "continue", "crate", "else", "enum", "extern", "false", "fn",
    "for", "if", "impl", "in", "let", "loop", "match", "mod", "move", "mut", "pub", "ref",
    "return", "self", "static", "struct", "super", "trait", "true", "type", "unsafe",
    "use", "where", "while", "async", "await", "dyn", "abstract", "become", "box", "do",
    "final", "macro", "override", "priv", "typeof", "unsized", "virtual", "yield", "try",
    "gen",
}

TOP_KEYS = {"regdef_version", "map", "peripherals", "_source"}
MAP_KEYS = {"name", "version", "description", "extra_regions"}
REGION_KEYS = {"name", "base", "size", "asid", "owner", "attr"}
PERIPH_KEYS = {"name", "description", "region", "base", "size", "priv_only",
               "secure_only", "rtl", "registers", "examples", "connect",
               "regdef_version", "_source"}
RTL_KEYS = {"status", "summary", "modules"}
RTL_MODULE_KEYS = {"module", "archive", "path", "sha256", "ports", "role"}
REG_KEYS = {"name", "offset", "width", "count", "stride", "description", "fields",
            "access", "reset", "hw", "precedence", "interrupt", "connect",
            "wr_strobe", "rd_strobe", "write_gate", "reserved"}
FIELD_KEYS = {"name", "bit", "bits", "width", "access", "reset", "hw", "precedence",
              "interrupt", "description", "connect", "repeat"}
RTL_STATUSES = ("bound", "register_compatible", "constants")
EX_OPS = ("write", "read", "expect", "poll", "set", "trigger", "clear", "comment")
EX_KEYS = set(EX_OPS) | {"value", "until", "max", "index"}
CONNECT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)(\[[^\]\s]+\])?$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
#: connect kinds that belong to the register rather than to a field
REG_KINDS = ("wr_strobe", "rd_strobe", "gate")


class _V:
    def __init__(self) -> None:
        self.col = Collector()

    # ---- primitives -------------------------------------------------
    def err(self, code: str, msg: str, where: str = "") -> None:
        self.col.add(code, msg, where)

    def mapping(self, v: Any, allowed: Set[str], where: str) -> Optional[Dict[str, Any]]:
        if not isinstance(v, dict):
            self.err("E_SCHEMA", f"expected a mapping, got {type(v).__name__}", where)
            return None
        for k in v:
            if k not in allowed:
                self.err("E_UNKNOWN_KEY", f"unknown key {k!r} (allowed: {', '.join(sorted(allowed - {'_source'}))})", where)
        return v

    def integer(self, v: Any, where: str, lo: Optional[int] = None, hi: Optional[int] = None,
                code: str = "E_INT") -> Optional[int]:
        if isinstance(v, bool):
            self.err(code, f"expected an integer, got boolean {v!r}", where)
            return None
        if isinstance(v, str):
            try:
                if re.fullmatch(r"[-+]?(0b[01_]+|0x[0-9a-fA-F_]+|0|[1-9][0-9_]*)", v):
                    v = int(v.replace("_", ""), 0)
                else:
                    raise ValueError
            except ValueError:
                self.err(code, f"expected an integer, got {v!r}", where)
                return None
        if not isinstance(v, int):
            self.err(code, f"expected an integer, got {type(v).__name__}", where)
            return None
        if lo is not None and v < lo:
            self.err(code, f"{v} is below the minimum {lo}", where)
            return None
        if hi is not None and v > hi:
            self.err(code, f"{v} is above the maximum {hi}", where)
            return None
        return v

    def boolean(self, v: Any, where: str, default: bool = False) -> bool:
        if v is None:
            return default
        if not isinstance(v, bool):
            self.err("E_SCHEMA", f"expected true/false, got {v!r}", where)
            return default
        return v

    def text(self, v: Any, where: str) -> str:
        if v is None:
            return ""
        if not isinstance(v, str):
            self.err("E_SCHEMA", f"expected text, got {type(v).__name__}", where)
            return ""
        return " ".join(v.split())

    def name(self, v: Any, rx: "re.Pattern[str]", where: str, kind: str) -> Optional[str]:
        if not isinstance(v, str) or not rx.match(v):
            self.err("E_NAME", f"{kind} name {v!r} is invalid (expected {'UPPER' if rx is UPPER_NAME_RE else 'lower'}_snake_case)", where)
            return None
        if len(v) > MAX_NAME:
            self.err("E_NAME", f"{kind} name {v!r} is longer than {MAX_NAME} characters", where)
            return None
        if v.lower() in RUST_KEYWORDS:
            self.err("E_KEYWORD", f"{kind} name {v!r} collides with a Rust keyword", where)
            return None
        return v


# --------------------------------------------------------------------------
# Fields
# --------------------------------------------------------------------------
def _parse_bits(v: "_V", fd: Dict[str, Any], where: str, regwidth: int) -> Optional[Tuple[int, int]]:
    if "bit" in fd and "bits" in fd:
        v.err("E_FIELD_BITS", "give either 'bit' or 'bits', not both", where)
        return None
    lsb: Optional[int] = None
    msb: Optional[int] = None
    if "bit" in fd:
        b = v.integer(fd["bit"], where + ".bit", 0, code="E_FIELD_BITS")
        if b is None:
            return None
        lsb = msb = b
    elif "bits" in fd:
        b = fd["bits"]
        if isinstance(b, str):
            m = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*", b) or re.fullmatch(r"\s*(\d+)\s*", b)
            if not m:
                v.err("E_FIELD_BITS", f"cannot parse bits {b!r}; use 'hi:lo' or [hi, lo]", where)
                return None
            msb = int(m.group(1))
            lsb = int(m.group(2)) if m.lastindex == 2 else msb
        elif isinstance(b, list) and len(b) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in b):
            msb, lsb = b
        elif isinstance(b, int) and not isinstance(b, bool):
            msb = lsb = b
        else:
            v.err("E_FIELD_BITS", f"cannot parse bits {b!r}; use 'hi:lo' or [hi, lo]", where)
            return None
    else:
        v.err("E_FIELD_BITS", "field needs 'bit' or 'bits'", where)
        return None
    if lsb < 0 or msb < lsb:
        v.err("E_FIELD_BITS", f"bit range [{msb}:{lsb}] is empty or negative (write 'hi:lo' with hi >= lo)", where)
        return None
    if msb >= regwidth:
        v.err("E_FIELD_BITS", f"bit range [{msb}:{lsb}] does not fit a {regwidth}-bit register", where)
        return None
    if "width" in fd:
        w = v.integer(fd["width"], where + ".width", 1, code="E_FIELD_WIDTH")
        if w is not None and w != msb - lsb + 1:
            v.err("E_FIELD_WIDTH", f"declared width {w} does not match bit range [{msb}:{lsb}] ({msb - lsb + 1} bits)", where)
            return None
    return lsb, msb - lsb + 1


def _parse_ref(v: "_V", ref: Any, where: str) -> Optional[Tuple[str, str]]:
    if isinstance(ref, dict):
        if set(ref) != {"enable"}:
            v.err("E_INTERRUPT", "interrupt mapping must have exactly the key 'enable'", where)
            return None
        ref = ref["enable"]
    if not isinstance(ref, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*", ref):
        v.err("E_INTERRUPT", f"interrupt enable must be 'REGISTER.FIELD', got {ref!r}", where)
        return None
    a, b = ref.split(".")
    return a, b


def _parse_connect(v: "_V", c: Any, where: str) -> Tuple[Tuple[str, str], ...]:
    if c is None:
        return ()
    if not isinstance(c, dict):
        v.err("E_SCHEMA", "connect must be a mapping of <kind>: 'module.port[slice]'", where)
        return ()
    out = []
    for k in sorted(c):
        val = c[k]
        if not isinstance(val, str) or not CONNECT_RE.match(val):
            v.err("E_BIND_SYNTAX", f"connect {k!r}: {val!r} is not 'module.port' or 'module.port[hi:lo]'", where)
            continue
        out.append((str(k), val))
    return tuple(out)


def _build_field(v: "_V", fd: Dict[str, Any], where: str, regwidth: int, tmpl_i: Optional[int] = None) -> Optional[Field]:
    name = fd.get("name")
    if tmpl_i is not None and isinstance(name, str):
        name = name.replace("{i}", str(tmpl_i))
    if v.name(name, UPPER_NAME_RE, where + ".name", "field") is None:
        return None
    where = f"{where[:where.rfind('[')]}[{name}]" if "[" in where else where
    pos = _parse_bits(v, fd, where, regwidth)
    access = fd.get("access")
    if access not in ACCESS_TYPES:
        v.err("E_FIELD_ACCESS", f"access {access!r} is not one of {', '.join(ACCESS_TYPES)}", where)
        return None
    if pos is None:
        return None
    lsb, width = pos
    opts = HW_OPTIONS[access]
    hw = fd.get("hw", opts[0])
    if hw not in opts:
        v.err("E_FIELD_HW", f"hw option {hw!r} is not valid for access '{access}' (valid: {', '.join(opts)})", where)
        return None
    precedence = fd.get("precedence", "")
    can_conflict = (access == "rw" and hw == "update") or (access in ("w1c", "w1s") and hw == "event")
    if precedence:
        if precedence not in ("hw", "sw"):
            v.err("E_PRECEDENCE", f"precedence {precedence!r} must be 'hw' or 'sw'", where)
            return None
        if not can_conflict:
            v.err("E_PRECEDENCE", "precedence only applies where hardware and software can update the same bit "
                  "(rw+hw:update, w1c/w1s+hw:event)", where)
            return None
    elif can_conflict:
        precedence = "hw"

    # reset
    reset, symbol = 0, None
    if "reset" in fd:
        r = fd["reset"]
        if isinstance(r, str) and r.startswith("$"):
            sym = r[1:]
            if sym not in SYMBOLS:
                v.err("E_RESET_SYMBOL", f"unknown reset symbol {r!r} (known: {', '.join('$' + s for s in SYMBOLS)})", where)
                return None
            if not (access == "ro" and hw == "const"):
                v.err("E_RESET_SYMBOL", "a symbolic reset is only allowed on ro fields with hw: const", where)
                return None
            if width not in (32, 64):
                v.err("E_RESET_SYMBOL", f"{r!r} needs a 32- or 64-bit field, not {width}", where)
                return None
            symbol = sym
        else:
            ri = v.integer(r, where + ".reset", code="E_RESET_RANGE")
            if ri is None:
                return None
            if ri < 0 or ri >= (1 << width):
                v.err("E_RESET_RANGE", f"reset value {ri:#x} does not fit the {width}-bit field [{lsb + width - 1}:{lsb}]", where)
                return None
            reset = ri
        if reset and (access == "w1p" or (access == "wo" and hw == "none") or (access == "ro" and hw == "input")):
            why = {"w1p": "a pulse field holds no state", "wo": "a hw:none write-only field holds no state",
                   "ro": "a live hardware input has no reset value"}[access]
            v.err("E_RESET_INVALID", f"non-zero reset on '{access}/{hw}': {why}", where)
            return None

    # interrupt
    ie = None
    if "interrupt" in fd:
        if not (access == "w1c" or (access == "ro" and hw in ("input", "update"))):
            v.err("E_INTERRUPT", "interrupt is only allowed on w1c fields and on ro fields with hw input/update", where)
            return None
        ie = _parse_ref(v, fd["interrupt"], where + ".interrupt")
        if ie is None:
            return None

    return Field(name=name, lsb=lsb, width=width, access=access, hw=hw, reset=reset,
                 reset_symbol=symbol, precedence=precedence, interrupt_enable=ie,
                 description=v.text(fd.get("description"), where + ".description"),
                 connect=_parse_connect(v, fd.get("connect"), where + ".connect"))


def _expand_fields(v: "_V", raw: Any, where: str, regwidth: int) -> List[Field]:
    out: List[Field] = []
    if not isinstance(raw, list) or not raw:
        v.err("E_NO_FIELDS", "a register needs a non-empty 'fields' list", where)
        return out
    for idx, fd in enumerate(raw):
        fw = f"{where}.fields[{idx}]"
        fd = v.mapping(fd, FIELD_KEYS, fw)
        if fd is None:
            continue
        rep = fd.get("repeat")
        if rep is None:
            f = _build_field(v, fd, fw, regwidth)
            if f:
                out.append(f)
            continue
        rep = v.mapping(rep, {"count", "stride", "first"}, fw + ".repeat")
        if rep is None:
            continue
        cnt = v.integer(rep.get("count"), fw + ".repeat.count", 1, code="E_FIELD_BITS")
        stp = v.integer(rep.get("stride"), fw + ".repeat.stride", 1, code="E_FIELD_BITS")
        first = v.integer(rep.get("first", 0), fw + ".repeat.first", 0, code="E_FIELD_BITS")
        if cnt is None or stp is None or first is None:
            continue
        if "{i}" not in str(fd.get("name", "")):
            v.err("E_NAME", "a repeated field name must contain '{i}'", fw)
            continue
        base = _parse_bits(v, fd, fw, 1 << 20)
        if base is None:
            continue
        for i in range(cnt):
            d2 = {k: x for k, x in fd.items() if k not in ("bit", "bits", "repeat", "width")}
            lsb = base[0] + i * stp
            d2["bits"] = [lsb + base[1] - 1, lsb]
            if isinstance(d2.get("description"), str):
                d2["description"] = d2["description"].replace("{i}", str(first + i))
            f = _build_field(v, d2, fw, regwidth, tmpl_i=first + i)
            if f:
                out.append(f)
    return out


# --------------------------------------------------------------------------
# Registers
# --------------------------------------------------------------------------
def _build_register(v: "_V", rd: Any, where: str) -> Optional[Register]:
    rd = v.mapping(rd, REG_KEYS, where)
    if rd is None:
        return None
    name = rd.get("name")
    if v.name(name, UPPER_NAME_RE, where + ".name", "register") is None:
        return None
    where = f"{where[:where.rfind('[')]}[{name}]"
    width = v.integer(rd.get("width", 32), where + ".width", code="E_REG_WIDTH")
    if width is None:
        return None
    if width not in (32, 64):
        v.err("E_REG_WIDTH", f"register width {width} is not supported (32 or 64)", where)
        return None
    offset = v.integer(rd.get("offset"), where + ".offset", 0, code="E_REG_ALIGN")
    if offset is None:
        return None
    nb = width // 8
    if offset % nb:
        v.err("E_REG_ALIGN", f"offset {offset:#x} is not aligned to the {width}-bit register size ({nb} bytes)", where)
        return None
    count = v.integer(rd.get("count", 1), where + ".count", 1, code="E_REG_COUNT")
    if count is None:
        return None
    stride = v.integer(rd.get("stride", nb), where + ".stride", 1, code="E_REG_STRIDE")
    if stride is None:
        return None
    if count > 1 and (stride < nb or stride % nb):
        v.err("E_REG_STRIDE", f"stride {stride} must be a multiple of the register size {nb} and >= {nb}", where)
        return None
    if count == 1:
        stride = nb

    # fields (explicit list or shorthand single field)
    if "fields" in rd:
        for k in ("access", "reset", "hw", "precedence", "interrupt"):
            if k in rd:
                v.err("E_SCHEMA", f"'{k}' at register level is shorthand for a single-field register; "
                      "do not combine it with 'fields'", where)
        fields = _expand_fields(v, rd["fields"], where, width)
    elif "access" in rd:
        fd = {"name": "VALUE", "bits": [width - 1, 0], "access": rd["access"]}
        for k in ("reset", "hw", "precedence", "interrupt"):
            if k in rd:
                fd[k] = rd[k]
        rc = rd.get("connect")
        if isinstance(rc, dict):
            # shorthand: field-kind entries bind the VALUE field, register-kind entries the register
            fd["connect"] = {k: x for k, x in rc.items() if k not in REG_KINDS} or None
            rd = dict(rd)
            rd["connect"] = {k: x for k, x in rc.items() if k in REG_KINDS} or None
        f = _build_field(v, fd, where + ".fields[VALUE]", width)
        fields = [f] if f else []
    else:
        v.err("E_NO_FIELDS", "register needs 'fields' or a single-field shorthand ('access')", where)
        return None
    if not fields:
        return None

    # field-level checks: duplicate names, overlap
    fields.sort(key=lambda f: f.lsb)
    seen: Dict[str, Field] = {}
    for f in fields:
        if f.name in seen:
            v.err("E_DUP_NAME", f"field name {f.name!r} used twice in register {name}", where)
        seen[f.name] = f
    for a, b in zip(fields, fields[1:]):
        if b.lsb <= a.msb:
            v.err("E_FIELD_OVERLAP", f"fields {a.name} [{a.msb}:{a.lsb}] and {b.name} [{b.msb}:{b.lsb}] overlap", where)

    # explicit reserved documentation
    reserved: List[Tuple[int, int]] = []
    for i, rr in enumerate(rd.get("reserved", []) or []):
        rw = f"{where}.reserved[{i}]"
        pos = _parse_bits(v, {"bits": rr}, rw, width)
        if pos is None:
            continue
        lo, w = pos
        m = ((1 << w) - 1) << lo
        for f in fields:
            if f.mask & m:
                v.err("E_RESERVED", f"reserved bits [{lo + w - 1}:{lo}] overlap field {f.name}", rw)
        reserved.append((lo + w - 1, lo))

    wr_strobe = v.boolean(rd.get("wr_strobe"), where + ".wr_strobe")
    rd_strobe = v.boolean(rd.get("rd_strobe"), where + ".rd_strobe")
    gate = v.boolean(rd.get("write_gate"), where + ".write_gate")
    reg = Register(name=name, offset=offset, width=width, count=count, stride=stride,
                   fields=tuple(fields), wr_strobe=wr_strobe, rd_strobe=rd_strobe,
                   write_gate=gate, description=v.text(rd.get("description"), where + ".description"),
                   reserved_doc=tuple(sorted(reserved, reverse=True)),
                   connect=_parse_connect(v, rd.get("connect"), where + ".connect"))
    if gate and not reg.writable:
        v.err("E_GATE", "write_gate on a register with no writable field", where)
    if wr_strobe and not reg.writable:
        v.err("E_STROBE", "wr_strobe on a register with no writable field", where)
    if rd_strobe and not reg.readable:
        v.err("E_STROBE", "rd_strobe on a register with no readable field", where)
    if count > 1 and any(f.interrupt_enable for f in fields):
        v.err("E_INTERRUPT", "interrupt fields are not allowed in register arrays", where)
    return reg


# --------------------------------------------------------------------------
# Peripherals
# --------------------------------------------------------------------------
def _build_rtl(v: "_V", rd: Any, where: str) -> Tuple[str, str, Tuple[RtlModule, ...]]:
    if rd is None:
        return "register_compatible", "", ()
    rd = v.mapping(rd, RTL_KEYS, where)
    if rd is None:
        return "register_compatible", "", ()
    status = rd.get("status")
    if status not in RTL_STATUSES:
        v.err("E_SCHEMA", f"rtl.status must be one of {', '.join(RTL_STATUSES)}", where)
        status = "register_compatible"
    mods: List[RtlModule] = []
    seen: Set[str] = set()
    for i, md in enumerate(rd.get("modules", []) or []):
        mw = f"{where}.modules[{i}]"
        md = v.mapping(md, RTL_MODULE_KEYS, mw)
        if md is None:
            continue
        mname = md.get("module")
        if not isinstance(mname, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", mname):
            v.err("E_NAME", f"invalid RTL module name {mname!r}", mw)
            continue
        if mname in seen:
            v.err("E_DUP_NAME", f"RTL module {mname!r} listed twice", mw)
        seen.add(mname)
        sha = md.get("sha256", "")
        if sha and (not isinstance(sha, str) or not SHA_RE.match(sha)):
            v.err("E_SCHEMA", "sha256 must be 64 lower-case hex digits", mw)
            sha = ""
        ports: List[Tuple[str, str]] = []
        pd = md.get("ports", {}) or {}
        if not isinstance(pd, dict):
            v.err("E_SCHEMA", "ports must be a mapping port -> input|output", mw)
            pd = {}
        for pn in sorted(pd):
            if pd[pn] not in ("input", "output"):
                v.err("E_SCHEMA", f"port {pn!r}: direction must be input or output", mw)
                continue
            ports.append((str(pn), pd[pn]))
        role = md.get("role", "attach")
        if role not in ("attach", "replace"):
            v.err("E_SCHEMA", "rtl module role must be 'attach' or 'replace'", mw)
            role = "attach"
        mods.append(RtlModule(mname, str(md.get("archive", "")), str(md.get("path", "")), sha or "", tuple(ports), role))
    return status, v.text(rd.get("summary"), where + ".summary"), tuple(mods)


def _validate_examples(v: "_V", raw: Any, p_name: str, regs: Sequence[Register], where: str) -> Tuple[Any, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        v.err("E_SCHEMA", "examples must be a list", where)
        return ()
    by_name = {r.name: r for r in regs}
    out: List[Any] = []
    for i, ex in enumerate(raw):
        ew = f"{where}[{i}]"
        ex = v.mapping(ex, {"title", "description", "steps"}, ew)
        if ex is None:
            continue
        title = v.text(ex.get("title"), ew + ".title")
        if not title:
            v.err("E_EXAMPLE", "example needs a title", ew)
        steps_out: List[Dict[str, Any]] = []
        for j, st in enumerate(ex.get("steps") or []):
            sw = f"{ew}.steps[{j}]"
            st = v.mapping(st, EX_KEYS, sw)
            if st is None:
                continue
            ops = [k for k in st if k in EX_OPS]
            if len(ops) != 1:
                v.err("E_EXAMPLE", f"a step needs exactly one of {', '.join(EX_OPS)}", sw)
                continue
            op = ops[0]
            if op == "comment":
                steps_out.append({"op": "comment", "text": v.text(st["comment"], sw)})
                continue
            target = st[op]
            if not isinstance(target, str):
                v.err("E_EXAMPLE", f"{op}: expected REGISTER or REGISTER.FIELD", sw)
                continue
            rn, _, fn = target.partition(".")
            reg = by_name.get(rn)
            if reg is None:
                v.err("E_EXAMPLE", f"{op}: unknown register {rn!r} in peripheral {p_name}", sw)
                continue
            fld = None
            if fn:
                fld = next((f for f in reg.fields if f.name == fn), None)
                if fld is None:
                    v.err("E_EXAMPLE", f"{op}: unknown field {fn!r} in register {rn}", sw)
                    continue
            elif op in ("set", "trigger", "clear", "expect", "poll"):
                v.err("E_EXAMPLE", f"{op}: needs REGISTER.FIELD", sw)
                continue
            idx = 0
            if "index" in st:
                idx = v.integer(st["index"], sw + ".index", 0, code="E_EXAMPLE")
                if idx is None:
                    continue
            if idx >= reg.count:
                v.err("E_EXAMPLE", f"index {idx} out of range for {rn} (count {reg.count})", sw)
                continue
            if "index" not in st and reg.count > 1:
                v.err("E_EXAMPLE", f"{rn} is an array of {reg.count}: give 'index'", sw)
                continue
            width = fld.width if fld else reg.width
            val = None
            if op in ("write", "set", "expect"):
                if "value" not in st:
                    v.err("E_EXAMPLE", f"{op}: needs 'value'", sw)
                    continue
                val = v.integer(st["value"], sw + ".value", 0, (1 << width) - 1, code="E_EXAMPLE")
                if val is None:
                    continue
            if op == "poll":
                val = v.integer(st.get("until"), sw + ".until", 0, (1 << width) - 1, code="E_EXAMPLE")
                if val is None:
                    continue
            # access compatibility
            if op == "write" and not reg.writable:
                v.err("E_EXAMPLE", f"write: register {rn} is not writable", sw)
                continue
            if op == "read" and not reg.readable:
                v.err("E_EXAMPLE", f"read: register {rn} is not readable", sw)
                continue
            if op in ("expect", "poll") and fld.access not in READABLE:
                v.err("E_EXAMPLE", f"{op}: field {target} is not readable", sw)
                continue
            if op in ("set", "trigger", "clear") and not reg.rmw_safe:
                v.err("E_EXAMPLE", f"{op}: register {rn} has read side effects or stored write-only fields, so no "
                      "read-modify-write helper exists; use 'write' with an explicit value", sw)
                continue
            if op == "set" and fld.access != "rw":
                v.err("E_EXAMPLE", f"set: field {target} must be 'rw' (use trigger/clear for w1p/w1s/w1c)", sw)
                continue
            if op == "trigger" and fld.access not in ("w1p", "w1s"):
                v.err("E_EXAMPLE", f"trigger: field {target} must be w1p or w1s", sw)
                continue
            if op == "clear" and fld.access != "w1c":
                v.err("E_EXAMPLE", f"clear: field {target} must be w1c", sw)
                continue
            d: Dict[str, Any] = {"op": op, "reg": rn, "index": idx}
            if fn:
                d["field"] = fn
            if val is not None:
                d["value"] = val
            if op == "poll":
                d["max"] = v.integer(st.get("max", 1000), sw + ".max", 1, 1000000, code="E_EXAMPLE") or 1000
            steps_out.append(d)
        if not steps_out:
            v.err("E_EXAMPLE", "example has no steps", ew)
        out.append({"title": title, "description": v.text(ex.get("description"), ew),
                    "steps": steps_out})
    return tuple(out)


def _build_peripheral(v: "_V", pd: Any, idx: int, regions: Dict[str, Region]) -> Optional[Peripheral]:
    where = f"peripherals[{idx}]"
    pd = v.mapping(pd, PERIPH_KEYS, where)
    if pd is None:
        return None
    name = pd.get("name")
    if v.name(name, LOWER_NAME_RE, where + ".name", "peripheral") is None:
        return None
    where = f"{name}"
    src = str(pd.get("_source", ""))
    base = v.integer(pd.get("base"), where + ".base", 0, (1 << 64) - 1)
    size = v.integer(pd.get("size"), where + ".size", 1, code="E_WINDOW_SIZE")
    region_name = pd.get("region")
    if base is None or size is None:
        return None
    if not is_pow2(size) or size < 16:
        v.err("E_WINDOW_SIZE", f"window size {size:#x} must be a power of two >= 16 bytes", where)
        return None
    if base % size:
        v.err("E_WINDOW_ALIGN", f"window base {base:#x} is not aligned to its size {size:#x}", where)
        return None
    reg_obj = regions.get(region_name) if isinstance(region_name, str) else None
    if reg_obj is None:
        v.err("E_REGION_UNKNOWN", f"region {region_name!r} is not in the ALP catalogue or the map's extra_regions", where)
        return None
    if not (reg_obj.base <= base and base + size <= reg_obj.base + reg_obj.size):
        v.err("E_REGION_RANGE", f"window {base:#x}+{size:#x} is outside region {reg_obj.name} "
              f"({reg_obj.base:#x}+{reg_obj.size:#x})", where)
        return None
    priv = v.boolean(pd.get("priv_only"), where + ".priv_only")
    sec = v.boolean(pd.get("secure_only"), where + ".secure_only")
    if reg_obj.priv_only and "priv_only" in pd and not priv:
        v.err("E_RELAX", f"peripheral cannot relax priv_only of region {reg_obj.name}", where)
    if reg_obj.secure_only and "secure_only" in pd and not sec:
        v.err("E_RELAX", f"peripheral cannot relax secure_only of region {reg_obj.name}", where)

    regs: List[Register] = []
    raw_regs = pd.get("registers")
    if not isinstance(raw_regs, list) or not raw_regs:
        v.err("E_SCHEMA", "a peripheral needs a non-empty 'registers' list", where)
        return None
    for i, rr in enumerate(raw_regs):
        r = _build_register(v, rr, f"{where}.registers[{i}]")
        if r:
            regs.append(r)
    names: Set[str] = set()
    for r in regs:
        if r.name in names:
            v.err("E_DUP_NAME", f"register {r.name!r} defined twice", where)
        names.add(r.name)

    # extents, window membership and overlap (byte ranges, array elements expanded)
    spans: List[Tuple[int, int, str]] = []
    for r in regs:
        last = r.offset + (r.count - 1) * r.stride + r.nbytes
        if last > size:
            v.err("E_REG_RANGE", f"register {r.name} extends to offset {last:#x}, beyond the {size:#x}-byte window", where)
        for e in range(r.count):
            o = r.offset + e * r.stride
            spans.append((o, o + r.nbytes, r.name if r.count == 1 else f"{r.name}[{e}]"))
    spans.sort()
    for (a0, a1, an), (b0, b1, bn) in zip(spans, spans[1:]):
        if b0 < a1:
            v.err("E_REG_OVERLAP", f"registers {an} ({a0:#x}..{a1 - 1:#x}) and {bn} ({b0:#x}..{b1 - 1:#x}) overlap", where)

    # region attribute compatibility
    if any(r.writable for r in regs) and not reg_obj.write:
        v.err("E_REGION_ATTR", f"region {reg_obj.name} forbids writes but the peripheral has writable registers", where)
    if any(r.readable for r in regs) and not reg_obj.read:
        v.err("E_REGION_ATTR", f"region {reg_obj.name} forbids reads but the peripheral has readable registers", where)

    status, summary, mods = _build_rtl(v, pd.get("rtl"), where + ".rtl")
    examples = _validate_examples(v, pd.get("examples"), name, regs, where + ".examples")
    return Peripheral(name=name, description=v.text(pd.get("description"), where + ".description"),
                      region=reg_obj.name, base=base, size=size, priv_only=priv, secure_only=sec,
                      registers=tuple(sorted(regs, key=lambda r: r.offset)),
                      rtl_status=status, rtl_summary=summary, rtl_modules=mods,
                      examples=examples, source=src,
                      connect=_parse_connect(v, pd.get("connect"), where + ".connect"))


# --------------------------------------------------------------------------
# Cross-checks
# --------------------------------------------------------------------------
def _check_interrupts(v: "_V", periphs: Sequence[Peripheral]) -> None:
    for p in periphs:
        regs = {r.name: r for r in p.registers}
        for r in p.registers:
            for f in r.fields:
                if f.interrupt_enable is None:
                    continue
                where = f"{p.name}.{r.name}.{f.name}"
                rn, fn = f.interrupt_enable
                er = regs.get(rn)
                ef = next((x for x in er.fields if x.name == fn), None) if er else None
                if er is None or ef is None:
                    v.err("E_INTERRUPT", f"interrupt enable {rn}.{fn} does not exist in peripheral {p.name}", where)
                elif er.count != 1:
                    v.err("E_INTERRUPT", f"interrupt enable {rn}.{fn} must not be in a register array", where)
                elif ef.access != "rw":
                    v.err("E_INTERRUPT", f"interrupt enable {rn}.{fn} must be an 'rw' field, is '{ef.access}'", where)
                elif ef.width != f.width:
                    v.err("E_INTERRUPT", f"interrupt enable {rn}.{fn} is {ef.width} bits, status is {f.width}", where)


def _check_collisions(v: "_V", insts: Sequence[RegInst], ports: Sequence[HwPort]) -> None:
    seen: Dict[str, str] = {}
    for i in insts:
        if i.name in seen:
            v.err("E_IDENT_COLLISION", f"flattened register name {i.name!r} is produced by both "
                  f"{seen[i.name]} and {i.periph.name}.{i.reg.name}")
        seen[i.name] = f"{i.periph.name}.{i.reg.name}"
    pseen: Dict[str, str] = {}
    for q in ports:
        if q.name in pseen:
            v.err("E_IDENT_COLLISION", f"hardware port name {q.name!r} is produced twice "
                  f"({pseen[q.name]} and {q.periph}.{q.reg}.{q.field})")
        pseen[q.name] = f"{q.periph}.{q.reg}.{q.field}"
    # field-level C/Rust identifier collisions: SF_<P>_<REG>_<FIELD> vs register names
    cn: Dict[str, str] = {}
    for p in {i.periph.name: i.periph for i in insts}.values():
        for r in p.registers:
            for key in [f"{p.name}_{r.name.lower()}"] + [f"{p.name}_{r.name.lower()}_{f.name.lower()}" for f in r.fields]:
                if key in cn and cn[key] != f"{p.name}.{r.name}":
                    v.err("E_IDENT_COLLISION", f"identifier {key!r} is produced by {cn[key]} and {p.name}.{r.name}")
                cn.setdefault(key, f"{p.name}.{r.name}")


def _check_binding(v: "_V", periphs: Sequence[Peripheral], ports: Sequence[HwPort]) -> None:
    by_key: Dict[Tuple[str, str, str, str], HwPort] = {}
    for q in ports:
        by_key[(q.periph, q.reg, q.field, q.kind)] = q
    for p in periphs:
        declared = {m.module: dict(m.ports) for m in p.rtl_modules}
        roles = {m.module: m.role for m in p.rtl_modules}

        def check(kind: str, expr: str, reg: str, fld: str, where: str) -> None:
            m = CONNECT_RE.match(expr)
            mod, port = m.group(1), m.group(2)
            hp = by_key.get((p.name, reg, fld, kind))
            if hp is None:
                v.err("E_BIND_KIND", f"{where}: this item has no hardware signal of kind {kind!r}", where)
                return
            if mod not in declared:
                v.err("E_BIND_MODULE", f"{where}: module {mod!r} is not listed in {p.name}.rtl.modules", where)
                return
            if port not in declared[mod]:
                v.err("E_BIND_PORT", f"{where}: port {mod}.{port} is not declared in rtl.modules", where)
                return
            # attach: the bank sits beside the block, so a bank output drives a block input.
            # replace: the bank takes over the block's register slave, so it has the block's own hardware-side directions.
            if roles[mod] == "replace":
                want = hp.direction
            else:
                want = "output" if hp.direction == "input" else "input"
            if declared[mod][port] != want:
                v.err("E_BIND_DIR", f"{where}: bank port {hp.name} is an {hp.direction} and the module role is "
                      f"'{roles[mod]}', so {mod}.{port} must be an {want}, but it is declared {declared[mod][port]}", where)

        for r in p.registers:
            for k, e in r.connect:
                check(k, e, r.name, "", f"{p.name}.{r.name}")
            for f in r.fields:
                for k, e in f.connect:
                    check(k, e, r.name, f.name, f"{p.name}.{r.name}.{f.name}")
        for k, e in p.connect:
            check(k, e, "", "", f"{p.name}")


def _resolve_symbols(periphs: Sequence[Peripheral], hash64: int) -> Tuple[Peripheral, ...]:
    out = []
    for p in periphs:
        regs = []
        for r in p.registers:
            fl = []
            for f in r.fields:
                if f.reset_symbol == "regmap_hash":
                    val = hash64 if f.width == 64 else hash64 >> 32
                    f = dataclasses.replace(f, reset=val)
                fl.append(f)
            regs.append(dataclasses.replace(r, fields=tuple(fl)))
        out.append(dataclasses.replace(p, registers=tuple(regs)))
    return tuple(out)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def validate(src: Source, catalogue_path: Optional[str] = None) -> RegMap:
    v = _V()
    doc = v.mapping(src.root, TOP_KEYS, "document")
    if doc is None:
        v.col.raise_if_any()
        raise AssertionError("unreachable")
    ver = doc.get("regdef_version")
    if ver != SCHEMA_VERSION:
        v.err("E_VERSION", f"regdef_version must be {SCHEMA_VERSION}, got {ver!r}", "document")
    md = v.mapping(doc.get("map"), MAP_KEYS, "map") or {}
    map_name = v.name(md.get("name"), LOWER_NAME_RE, "map.name", "map") or "regmap"
    version = (1, 0)
    vs = md.get("version", "1.0")
    m = re.fullmatch(r"(\d{1,5})\.(\d{1,5})", vs) if isinstance(vs, str) else None
    if m and int(m.group(1)) < 65536 and int(m.group(2)) < 65536:
        version = (int(m.group(1)), int(m.group(2)))
    else:
        v.err("E_VERSION", f"map.version must be 'MAJOR.MINOR' (each < 65536), got {vs!r}", "map")

    # region catalogue + proposals
    cat, reserved, min_bytes = load_catalogue(catalogue_path) if catalogue_path else load_catalogue()
    regions: Dict[str, Region] = {r.name: r for r in cat}
    for i, rd in enumerate(md.get("extra_regions", []) or []):
        rw = f"map.extra_regions[{i}]"
        rd = v.mapping(rd, REGION_KEYS, rw)
        if rd is None:
            continue
        rname = rd.get("name")
        if rname in regions:
            v.err("E_DUP_NAME", f"region {rname!r} already exists in the catalogue", rw)
            continue
        base = v.integer(rd.get("base"), rw + ".base", 0)
        size = v.integer(rd.get("size"), rw + ".size", 1, code="E_REGION_SIZE")
        if base is None or size is None:
            continue
        attr = rd.get("attr")
        attr = v.mapping(attr, {"read", "write", "exec", "priv_only", "secure_only", "cacheable", "mem_type"}, rw + ".attr") or {}
        reg = Region(name=str(rname), base=base, size=size, asid=str(rd.get("asid", "config")),
                     read=bool(attr.get("read", False)), write=bool(attr.get("write", False)),
                     exec=bool(attr.get("exec", False)), priv_only=bool(attr.get("priv_only", False)),
                     secure_only=bool(attr.get("secure_only", False)),
                     cacheable=bool(attr.get("cacheable", False)),
                     mem_type=str(attr.get("mem_type", "device")), owner=v.text(rd.get("owner"), rw),
                     proposed=True)
        check_region(reg, reserved, min_bytes, list(regions.values()), v.col, rw)
        regions[reg.name] = reg

    raw_periphs = doc.get("peripherals")
    periphs: List[Peripheral] = []
    if not isinstance(raw_periphs, list) or not raw_periphs:
        v.err("E_SCHEMA", "'peripherals' must be a non-empty list", "document")
    else:
        for i, pd in enumerate(raw_periphs):
            p = _build_peripheral(v, pd, i, regions)
            if p:
                periphs.append(p)

    # peripheral-level cross checks
    names: Set[str] = set()
    for p in periphs:
        if p.name in names:
            v.err("E_DUP_NAME", f"peripheral {p.name!r} defined twice", p.name)
        names.add(p.name)
    srt = sorted(periphs, key=lambda p: p.base)
    for a, b in zip(srt, srt[1:]):
        if b.base < a.end:
            v.err("E_WINDOW_OVERLAP", f"peripheral windows overlap: {a.name} ({a.base:#x}..{a.end - 1:#x}) and "
                  f"{b.name} ({b.base:#x}..{b.end - 1:#x})", f"{a.name}/{b.name}")

    if not v.col:
        _check_interrupts(v, periphs)
        pt = tuple(srt)
        insts = build_instances(pt)
        ports = build_hw_ports(pt)
        _check_collisions(v, insts, ports)
        _check_binding(v, pt, ports)

    v.col.raise_if_any()

    pt = tuple(srt)
    region_tuple = tuple(sorted(regions.values(), key=lambda r: r.base))
    files = tuple(sorted(src.files.items()))
    m0 = RegMap(name=map_name, version=version, description=v.text(md.get("description"), "map.description"),
                regions=region_tuple, peripherals=pt, source_files=files)
    sem = digest(canonical_dict(m0, semantic=True))
    m1 = dataclasses.replace(m0, semantic_hash=sem)
    resolved = _resolve_symbols(pt, m1.hash64)
    m2 = dataclasses.replace(m1, peripherals=resolved)
    full = digest(canonical_dict(m2, semantic=False))
    insts = build_instances(resolved)
    ports = build_hw_ports(resolved)
    return dataclasses.replace(m2, definition_hash=full, instances=insts, hw_ports=ports)
