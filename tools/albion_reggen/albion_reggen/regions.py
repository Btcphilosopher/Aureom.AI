"""ALP region catalogue: loading and legality rules (ALP-ADR-01).

The catalogue is the AlbionCore ``regions.yaml`` vendored unmodified under
``third_party/albioncore`` (its SHA-256 is recorded in PROVENANCE.md and
checked by the tests).  A register map may add *proposed* regions for
peripherals that have no catalogue region yet; proposed regions obey exactly
the same rules and are flagged as proposals in every generated document.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple

from .errors import Collector
from .loader import parse_text
from .model import MEM_TYPES, Region

CATALOGUE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "third_party", "albioncore", "regions.yaml")

NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
ASIDS = ("device", "config", "external", "host", "secure")
ATTR_KEYS = {"read", "write", "exec", "priv_only", "secure_only", "cacheable", "mem_type"}
ADDR_BITS = 64


def is_pow2(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _region_from(d: Dict[str, Any], proposed: bool) -> Region:
    a = d.get("attr", {}) or {}
    return Region(
        name=d["name"], base=int(d["base"]), size=int(d["size"]),
        asid=d.get("asid", "config"),
        read=bool(a.get("read", False)), write=bool(a.get("write", False)),
        exec=bool(a.get("exec", False)), priv_only=bool(a.get("priv_only", False)),
        secure_only=bool(a.get("secure_only", False)),
        cacheable=bool(a.get("cacheable", False)),
        mem_type=a.get("mem_type", "device"),
        owner=str(d.get("owner", "")), proposed=proposed)


def load_catalogue(path: str = CATALOGUE_PATH) -> Tuple[List[Region], List[Dict[str, Any]], int]:
    """Return (regions, reserved windows, min_region_bytes) of the ALP catalogue."""
    with open(path, "rb") as fh:
        doc = parse_text(fh.read().decode("utf-8"), path)
    regs = [_region_from(r, False) for r in doc["regions"]]
    reserved = [{"name": r["name"], "base": int(r["base"]), "size": int(r["size"])}
                for r in doc.get("reserved", [])]
    return regs, reserved, int(doc.get("min_region_bytes", 4096))


def check_region(r: Region, reserved: List[Dict[str, Any]], min_bytes: int,
                 others: List[Region], col: Collector, where: str) -> None:
    """ALP-ADR-01: pow2 size >= min, base aligned to size, inside the address
    space, no overlap with other regions or reserved windows."""
    if not NAME_RE.match(r.name):
        col.add("E_NAME", f"region name {r.name!r} must be lower_snake_case", where)
    if not is_pow2(r.size) or r.size < min_bytes:
        col.add("E_REGION_SIZE", f"region size {r.size:#x} must be a power of two >= {min_bytes:#x}", where)
        return
    if r.base % r.size:
        col.add("E_REGION_ALIGN", f"region base {r.base:#x} is not aligned to its size {r.size:#x}", where)
    if r.base < 0 or r.base + r.size > (1 << ADDR_BITS):
        col.add("E_REGION_RANGE", f"region {r.base:#x}+{r.size:#x} exceeds the {ADDR_BITS}-bit address space", where)
    if r.asid not in ASIDS:
        col.add("E_REGION_ATTR", f"unknown address space {r.asid!r}", where)
    if r.mem_type not in MEM_TYPES:
        col.add("E_REGION_ATTR", f"unknown mem_type {r.mem_type!r}", where)
    for o in others:
        if o.name != r.name and r.base < o.base + o.size and o.base < r.base + r.size:
            col.add("E_REGION_OVERLAP", f"region {r.name!r} overlaps region {o.name!r}", where)
    for w in reserved:
        if r.base < w["base"] + w["size"] and w["base"] < r.base + r.size:
            col.add("E_REGION_RESERVED", f"region {r.name!r} overlaps reserved window {w['name']!r}", where)
