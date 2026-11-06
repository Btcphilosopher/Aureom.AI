"""Minimal Liberty reader: library name, nominal PVT, cell names/areas, and
whether a cell carries timing arcs and power tables (used to decide what may
legitimately be reported -- e.g. no SRAM power number without power tables)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LibCell:
    name: str
    area: float | None = None
    has_timing: bool = False
    has_power: bool = False
    is_ff: bool = False
    is_latch: bool = False
    is_icg: bool = False
    async_reset: bool = False
    pins: set[str] = field(default_factory=set)


@dataclass
class Liberty:
    path: str
    name: str = ""
    nom_voltage: float | None = None
    nom_temperature: float | None = None
    cells: dict[str, LibCell] = field(default_factory=dict)


def _nonzero_power(body: str) -> bool:
    """True only if the cell has a non-zero leakage value or a non-zero number in
    an internal_power table (IHP SRAM Liberty has power groups filled with 0)."""
    for m in re.finditer(r"\bcell_leakage_power\s*:\s*([-\d.eE+]+)", body):
        if float(m.group(1)) != 0.0:
            return True
    for m in re.finditer(r"\binternal_power\s*\(\s*\)\s*\{", body):
        depth, i = 1, m.end()
        while i < len(body) and depth:
            depth += {"{": 1, "}": -1}.get(body[i], 0)
            i += 1
        for v in re.findall(r"values\s*\(([^;]*)\)\s*;", body[m.end():i]):
            if any(float(x) != 0.0 for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", v)):
                return True
    return False


def parse_liberty(path: str | Path) -> Liberty:
    path = Path(path)
    text = path.read_text(errors="replace")
    lib = Liberty(str(path))
    m = re.search(r"\blibrary\s*\(\s*\"?([^\")\s]+)", text)
    lib.name = m.group(1) if m else ""
    m = re.search(r"\bnom_voltage\s*:\s*([-\d.eE+]+)", text)
    lib.nom_voltage = float(m.group(1)) if m else None
    m = re.search(r"\bnom_temperature\s*:\s*([-\d.eE+]+)", text)
    lib.nom_temperature = float(m.group(1)) if m else None
    starts = [(mm.start(), mm.group(1)) for mm in re.finditer(r"\bcell\s*\(\s*\"?([^\")\s]+)\"?\s*\)", text)]
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        body = text[pos:end]
        c = LibCell(name)
        a = re.search(r"\barea\s*:\s*([-\d.eE+]+)", body)
        c.area = float(a.group(1)) if a else None
        c.has_timing = bool(re.search(r"\btiming\s*\(", body))
        c.has_power = _nonzero_power(body)
        c.is_ff = bool(re.search(r"\bff\s*\(", body))
        c.is_latch = bool(re.search(r"\blatch\s*\(", body))
        c.is_icg = bool(re.search(r"clock_gating_integrated_cell", body))
        c.async_reset = c.is_ff and bool(re.search(r"\b(clear|preset)\s*:", body))
        c.pins = set(re.findall(r"\bpin\s*\(\s*\"?([^\")\s]+)", body)) | set(re.findall(r"\bbus\s*\(\s*\"?([^\")\s]+)", body))
        lib.cells[name] = c
    return lib
