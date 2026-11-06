"""Minimal, dependency-free LEF reader for the facts FloorplanLab validates.

Only what the flow needs is parsed: units, SITE, LAYER properties and MACRO
class / size / symmetry / pins (use, direction, layer, rectangles) /
obstruction layers.  It is a reader for validation, not a database: the
physical database of record is always OpenROAD/OpenDB.

LEF definitions (SITE / LAYER / MACRO / PIN) are a keyword plus a name alone
on a line and are closed by ``END <name>``; references such as ``LAYER m1 ;``
inside VIA or PORT blocks end with ';' and are therefore not matched as
definitions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"


@dataclass
class Site:
    name: str
    cls: str = ""
    width: float = 0.0
    height: float = 0.0
    symmetry: list[str] = field(default_factory=list)


@dataclass
class Layer:
    name: str
    type: str = ""
    direction: str = ""
    pitch: float | None = None
    width: float | None = None
    min_width: float | None = None
    spacing: float | None = None
    offset: float | None = None


@dataclass
class Rect:
    layer: str
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class Pin:
    name: str
    direction: str = ""
    use: str = "SIGNAL"
    rects: list[Rect] = field(default_factory=list)

    @property
    def layers(self) -> set[str]:
        return {r.layer for r in self.rects}


@dataclass
class Macro:
    name: str
    cls: str = ""
    width: float = 0.0
    height: float = 0.0
    symmetry: list[str] = field(default_factory=list)
    site: str = ""
    pins: dict[str, Pin] = field(default_factory=dict)
    obs_layers: set[str] = field(default_factory=set)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def is_block(self) -> bool:
        return self.cls.upper().startswith("BLOCK")

    def pg_pins(self) -> dict[str, Pin]:
        return {n: p for n, p in self.pins.items() if p.use.upper() in ("POWER", "GROUND")}

    def signal_pins(self) -> dict[str, Pin]:
        return {n: p for n, p in self.pins.items() if p.use.upper() not in ("POWER", "GROUND")}

    def legal_orients(self) -> set[str]:
        """Orientations allowed by LEF SYMMETRY (LEF/DEF 5.8 semantics)."""
        sym = {s.upper() for s in self.symmetry}
        o = {"R0"}
        if "X" in sym:
            o.add("MX")
        if "Y" in sym:
            o.add("MY")
        if "X" in sym and "Y" in sym:
            o.add("R180")
        if "R90" in sym:
            o |= {"R90", "R270"}
            if "X" in sym or "Y" in sym:
                o |= {"MXR90", "MYR90"}
        return o

    def pin_edges(self, tol: float = 1.0) -> dict[str, int]:
        """Count signal pins by the macro edge they touch (R0 frame)."""
        out = {"bottom": 0, "top": 0, "left": 0, "right": 0, "interior": 0}
        for p in self.signal_pins().values():
            if not p.rects:
                continue
            x1 = min(r.x1 for r in p.rects)
            y1 = min(r.y1 for r in p.rects)
            x2 = max(r.x2 for r in p.rects)
            y2 = max(r.y2 for r in p.rects)
            if y1 <= tol:
                out["bottom"] += 1
            elif y2 >= self.height - tol:
                out["top"] += 1
            elif x1 <= tol:
                out["left"] += 1
            elif x2 >= self.width - tol:
                out["right"] += 1
            else:
                out["interior"] += 1
        return out

    def pin_side_r0(self) -> str:
        """Dominant signal-pin edge in the R0 frame ('bottom', 'top', ...)."""
        e = self.pin_edges()
        e.pop("interior")
        return max(e, key=e.get) if any(e.values()) else "interior"


@dataclass
class LefLibrary:
    units_dbu: int | None = None
    manufacturing_grid: float | None = None
    sites: dict[str, Site] = field(default_factory=dict)
    layers: dict[str, Layer] = field(default_factory=dict)
    macros: dict[str, Macro] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)

    def routing_layers(self) -> list[Layer]:
        return [l for l in self.layers.values() if l.type.upper() == "ROUTING"]

    def layer_index(self, name: str) -> int:
        names = [l.name for l in self.routing_layers()]
        return names.index(name) if name in names else -1

    def merge(self, other: "LefLibrary") -> None:
        if other.units_dbu and not self.units_dbu:
            self.units_dbu = other.units_dbu
        if other.manufacturing_grid and not self.manufacturing_grid:
            self.manufacturing_grid = other.manufacturing_grid
        self.sites.update(other.sites)
        self.layers.update(other.layers)
        self.macros.update(other.macros)
        self.files += other.files


def _block(keyword: str, text: str):
    pat = re.compile(rf"^[ \t]*{keyword}[ \t]+(\S+)[ \t]*$", re.M)
    pos = 0
    while True:
        m = pat.search(text, pos)
        if not m:
            return
        name = m.group(1)
        end = re.compile(rf"^[ \t]*END[ \t]+{re.escape(name)}[ \t]*$", re.M).search(text, m.end())
        if not end:
            return
        yield name, text[m.end():end.start()]
        pos = end.end()


def _stmt(body: str, key: str) -> list[str] | None:
    m = re.search(rf"^[ \t]*{key}\b([^;]*);", body, re.M)
    return m.group(1).split() if m else None


def _first_float(body: str, key: str) -> float | None:
    s = _stmt(body, key)
    if s and re.fullmatch(_NUM, s[0]):
        return float(s[0])
    return None


def parse_lef_text(text: str, source: str = "<text>") -> LefLibrary:
    text = re.sub(r"#[^\n]*", "", text)
    lib = LefLibrary(files=[source])
    m = re.search(r"DATABASE\s+MICRONS\s+(\d+)", text)
    if m:
        lib.units_dbu = int(m.group(1))
    m = re.search(rf"MANUFACTURINGGRID\s+({_NUM})\s*;", text)
    if m:
        lib.manufacturing_grid = float(m.group(1))
    for name, body in _block("SITE", text):
        s = Site(name)
        c = _stmt(body, "CLASS")
        s.cls = c[0] if c else ""
        sz = _stmt(body, "SIZE")
        if sz and len(sz) >= 3:
            s.width, s.height = float(sz[0]), float(sz[2])
        sy = _stmt(body, "SYMMETRY")
        s.symmetry = sy or []
        lib.sites[name] = s
    # strip macros before scanning layers (macro bodies contain no LAYER defs,
    # but stripping keeps the scan fast on large SRAM LEFs)
    macro_blocks = list(_block("MACRO", text))
    for name, body in _block("LAYER", text):
        l = Layer(name)
        t = _stmt(body, "TYPE")
        l.type = t[0] if t else ""
        d = _stmt(body, "DIRECTION")
        l.direction = d[0] if d else ""
        l.pitch = _first_float(body, "PITCH")
        l.width = _first_float(body, "WIDTH")
        l.min_width = _first_float(body, "MINWIDTH")
        l.spacing = _first_float(body, "SPACING")
        l.offset = _first_float(body, "OFFSET")
        lib.layers[name] = l
    for name, body in macro_blocks:
        mac = Macro(name)
        c = _stmt(body, "CLASS")
        mac.cls = " ".join(c) if c else ""
        sz = _stmt(body, "SIZE")
        if sz and len(sz) >= 3:
            mac.width, mac.height = float(sz[0]), float(sz[2])
        sy = _stmt(body, "SYMMETRY")
        mac.symmetry = sy or []
        st = _stmt(body, "SITE")
        mac.site = st[0] if st else ""
        for pname, pbody in _block("PIN", body):
            pin = Pin(pname)
            d = _stmt(pbody, "DIRECTION")
            pin.direction = d[0] if d else ""
            u = _stmt(pbody, "USE")
            pin.use = u[0] if u else "SIGNAL"
            layer = ""
            for tok in re.finditer(rf"\b(LAYER)\s+(\S+)\s*;|\b(RECT)\s+((?:{_NUM}\s+){{3}}{_NUM})\s*;", pbody):
                if tok.group(1):
                    layer = tok.group(2)
                elif tok.group(3) and layer:
                    v = [float(x) for x in tok.group(4).split()]
                    pin.rects.append(Rect(layer, *v))
            mac.pins[pname] = pin
        om = re.search(r"^[ \t]*OBS[ \t]*$(.*?)^[ \t]*END[ \t]*$", body, re.M | re.S)
        if om:
            mac.obs_layers = set(re.findall(r"LAYER\s+(\S+)\s*;", om.group(1)))
        lib.macros[name] = mac
    return lib


def parse_lef(path: str | Path) -> LefLibrary:
    path = Path(path)
    return parse_lef_text(path.read_text(errors="replace"), str(path))


def load_lefs(paths) -> LefLibrary:
    lib = LefLibrary()
    for p in paths:
        lib.merge(parse_lef(p))
    return lib
