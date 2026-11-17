"""Conformance of the generator's ALP v1 constants to the real ``sf_albion_pkg.sv``.

The reference model and the testbench carry their own copy of the ALP numbers
(operation codes, status codes, request/response layout, attribute bits).  This
module parses the actual AlbionCore package and proves the copy equal, and it
checks the SYSID block's ALP version / capability words against the package
(``sf_caps_t`` layout and constants), so the identification registers are bound
to implemented RTL, not typed in from memory.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from . import emit_sv, refmodel
from .model import RegMap

DEFAULT_PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "third_party", "albioncore", "sf_albion_pkg.sv")


def _consts(text: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for m in re.finditer(r"localparam\s+(?:int\s+unsigned|int|logic\s*\[[^\]]*\]|sf_\w+)\s+(\w+)\s*=\s*"
                         r"(?:(\d+)'h([0-9A-Fa-f_]+)|(\d+))\s*;", text):
        name = m.group(1)
        out[name] = int(m.group(3).replace("_", ""), 16) if m.group(3) else int(m.group(4))
    # enumerators ("SF_OP_WRITE = 4'h2," possibly the last one without a comma)
    for m in re.finditer(r"^\s*(SF_\w+)\s*=\s*(\d+)'h([0-9A-Fa-f]+)\s*(?:[,/]|$)", text, re.M):
        out[m.group(1)] = int(m.group(3), 16)
    for m in re.finditer(r"^\s*(SF_\w+)\s*=\s*(\d+)'d(\d+)\s*(?:[,/]|$)", text, re.M):
        out[m.group(1)] = int(m.group(3))
    # widths the package derives by expression
    if "SF_DATA_W" in out:
        out.setdefault("SF_BE_W", out["SF_DATA_W"] // 8)
    return out


def _caps_layout(text: str) -> List[Tuple[str, int]]:
    m = re.search(r"typedef\s+struct\s+packed\s*\{([^{}]*)\}\s*sf_caps_t\s*;", text, re.S)
    out: List[Tuple[str, int]] = []
    for f in re.finditer(r"logic\s*(?:\[(\d+):0\])?\s*(\w+)\s*;", m.group(1)):
        out.append((f.group(2), int(f.group(1)) + 1 if f.group(1) else 1))
    return out


def check(m: Optional[RegMap] = None, pkg_path: str = DEFAULT_PKG) -> List[str]:
    """Return a list of mismatches (empty = conformant)."""
    with open(pkg_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    c = _consts(text)
    bad: List[str] = []

    def eq(what: str, got: int, want: Optional[int]) -> None:
        if want is None:
            bad.append(f"{what}: not found in sf_albion_pkg.sv")
        elif got != want:
            bad.append(f"{what}: generator has {got:#x}, sf_albion_pkg.sv has {want:#x}")

    st = {"OKAY": "SF_ST_OKAY", "DECODE_ERR": "SF_ST_DECODE_ERR", "ACCESS_DENIED": "SF_ST_ACCESS_DENIED",
          "BAD_OPCODE": "SF_ST_BAD_OPCODE", "BAD_BE": "SF_ST_BAD_BE", "ALIGN_ERR": "SF_ST_ALIGN_ERR",
          "BAD_ATTR": "SF_ST_BAD_ATTR", "TARGET_ERR": "SF_ST_TARGET_ERR"}
    for k, v in st.items():
        eq(f"status {k}", refmodel.ST[k], c.get(v))
    eq("op READ", refmodel.OP_READ, c.get("SF_OP_READ"))
    eq("op WRITE", refmodel.OP_WRITE, c.get("SF_OP_WRITE"))
    eq("op NONE", refmodel.OP_NONE, c.get("SF_OP_NONE"))
    eq("domain invalid", refmodel.DOM_INVALID, c.get("SF_DOM_INVALID"))
    eq("mem type DEVICE", refmodel.MEM_DEVICE, c.get("SF_MEM_DEVICE"))
    eq("request width", 236, c.get("SF_REQ_W") or (c.get("SF_OP_W", 0) + c.get("SF_TAG_W", 0) + c.get("SF_DOM_W", 0)
                                                    + c.get("SF_ATTR_W", 0) + c.get("SF_ADDR_W", 0) + c.get("SF_BE_W", 0) + c.get("SF_DATA_W", 0)))
    eq("op field LSB", 232, c.get("SF_REQ_OP_LSB"))
    eq("tag field LSB", 224, c.get("SF_REQ_TAG_LSB"))
    eq("dom field LSB", 216, c.get("SF_REQ_DOM_LSB"))
    eq("attr field LSB", 208, c.get("SF_REQ_ATTR_LSB"))
    eq("addr field LSB", 144, c.get("SF_REQ_ADDR_LSB"))
    eq("be field LSB", 128, c.get("SF_REQ_BE_LSB"))
    eq("data field LSB", 0, c.get("SF_REQ_DATA_LSB"))
    eq("response tag LSB", 140, c.get("SF_RSP_TAG_LSB"))
    eq("response status LSB", 136, c.get("SF_RSP_STATUS_LSB"))
    eq("response meta LSB", 128, c.get("SF_RSP_META_LSB"))
    eq("response is_write bit", 0, c.get("SF_CMETA_IS_WRITE_BIT"))
    eq("response last bit", 1, c.get("SF_CMETA_LAST_BIT"))
    eq("attr mem_type LSB", 0, c.get("SF_ATTR_MEMTYPE_LSB"))
    eq("attr priv bit", 2, c.get("SF_ATTR_PRIV_BIT"))
    eq("attr secure bit", 3, c.get("SF_ATTR_SECURE_BIT"))
    eq("attr instr bit", 4, c.get("SF_ATTR_INSTR_BIT"))
    eq("attr reserved bit", 7, c.get("SF_ATTR_RSVD_BIT"))
    eq("region read bit", 0, c.get("SF_RATTR_READ_BIT"))
    eq("region write bit", 1, c.get("SF_RATTR_WRITE_BIT"))
    eq("region exec bit", 2, c.get("SF_RATTR_EXEC_BIT"))
    eq("region priv-only bit", 3, c.get("SF_RATTR_PRIV_ONLY_BIT"))
    eq("region secure-only bit", 4, c.get("SF_RATTR_SECURE_ONLY_BIT"))
    eq("region cacheable bit", 5, c.get("SF_RATTR_CACHEABLE_BIT"))
    eq("region mem_type LSB", 6, c.get("SF_RATTR_MEMTYPE_LSB"))
    eq("response width", 148, (c.get("SF_TAG_W", 0) + c.get("SF_STATUS_W", 0) + c.get("SF_CMETA_W", 0) + c.get("SF_DATA_W", 0)) or None)
    eq("lane width", 4, c.get("SF_LANE_W"))
    eq("data width", 128, c.get("SF_DATA_W"))

    if m is not None:
        bad.extend(_check_sysid(m, text, c))
    return bad


def _check_sysid(m: RegMap, text: str, c: Dict[str, int]) -> List[str]:
    bad: List[str] = []
    p = next((x for x in m.peripherals if x.name == "sysid"), None)
    if p is None:
        return bad
    regs = {r.name: r for r in p.registers}

    def field(reg: str, name: str):
        r = regs.get(reg)
        if r is None:
            return None
        return next((f for f in r.fields if f.name == name), None)

    def expect(reg: str, name: str, want: Optional[int]) -> None:
        f = field(reg, name)
        if f is None:
            bad.append(f"sysid.{reg}.{name} is missing")
        elif want is None:
            bad.append(f"sysid.{reg}.{name}: value not found in sf_albion_pkg.sv")
        elif f.reset != want:
            bad.append(f"sysid.{reg}.{name} = {f.reset:#x}, sf_albion_pkg.sv says {want:#x}")

    if "ALP_VERSION" in regs:
        expect("ALP_VERSION", "MAJOR", c.get("SF_ALP_VERSION_MAJOR"))
        expect("ALP_VERSION", "MINOR", c.get("SF_ALP_VERSION_MINOR"))
    if "LIB_VERSION" in regs:
        expect("LIB_VERSION", "MAJOR", c.get("SF_ALBION_LIB_MAJOR"))
        expect("LIB_VERSION", "MINOR", c.get("SF_ALBION_LIB_MINOR"))
        expect("LIB_VERSION", "PATCH", c.get("SF_ALBION_LIB_PATCH"))
    if "ALP_CAPS" in regs:
        # sf_caps_t: layout MSB -> LSB from the package, values from its constants
        lay = _caps_layout(text)
        pos: Dict[str, Tuple[int, int]] = {}
        hi = sum(w for _, w in lay)
        for nm, w in lay:
            hi -= w
            pos[nm.upper()] = (hi, w)
        vals = {
            "PROTO_MAJOR": c.get("SF_ALP_VERSION_MAJOR"), "PROTO_MINOR": c.get("SF_ALP_VERSION_MINOR"),
            "ADDR_W": c.get("SF_ADDR_W"), "DATA_BYTES_LOG2": c.get("SF_LANE_W"), "TAG_W": c.get("SF_TAG_W"),
            "DOM_W": c.get("SF_DOM_W"), "RSVD": 0, "MAX_OUTSTANDING": emit_sv.LINK_CAPACITY,
            "FEATURES": 0x0003 if "SF_FEATURES_ALP_V1" in text else None,
        }
        # the package states SF_FEATURES_ALP_V1 as 16'h0003 (a logic [15:0] localparam)
        m2 = re.search(r"SF_FEATURES_ALP_V1\s*=\s*16'h([0-9A-Fa-f]+)", text)
        if m2:
            vals["FEATURES"] = int(m2.group(1), 16)
        for nm, (lsb, w) in pos.items():
            f = field("ALP_CAPS", nm)
            if f is None:
                bad.append(f"sysid.ALP_CAPS.{nm} is missing (sf_caps_t has it at [{lsb + w - 1}:{lsb}])")
                continue
            if (f.lsb, f.width) != (lsb, w):
                bad.append(f"sysid.ALP_CAPS.{nm} is [{f.msb}:{f.lsb}], sf_caps_t has [{lsb + w - 1}:{lsb}]")
            if vals.get(nm) is not None and f.reset != vals[nm]:
                bad.append(f"sysid.ALP_CAPS.{nm} = {f.reset:#x}, expected {vals[nm]:#x} from sf_albion_pkg.sv / the bank's link capacity")
        extra = [f.name for f in regs["ALP_CAPS"].fields if f.name not in pos]
        if extra:
            bad.append(f"sysid.ALP_CAPS has fields not in sf_caps_t: {extra}")
    return bad
