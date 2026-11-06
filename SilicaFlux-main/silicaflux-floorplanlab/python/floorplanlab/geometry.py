"""Die/core geometry (MODE A / MODE B) and macro arrangements.

MODE B does NOT divide (macro + logic) area by a std-cell utilisation.  The
core is the sum of separately accounted regions:

  std-cell region  = mapped std-cell area x logic_growth / target_util
  macro region     = sum over macros of (w + 2 halo) x (h + 2 halo)
  routing corridor = corridor_um x (w + h) per macro (one long + one short side,
                     shared with the neighbour)
  PDN overhead     = pdn_overhead / (1 - pdn_overhead) x (everything above)

and is then grown, if necessary, to the envelope the chosen macro arrangement
physically needs.  The die adds core_margin_um on every side for the PDN ring
and the I/O pin keep-out (logical pins only; a pad ring is NOT included -- see
docs/FABRICATION_DEPENDENCIES.md).  All coordinates are snapped: core width to
the placement-site width, core height to the row height, everything to the
manufacturing grid.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .config import ConfigError, FloorplanSpec


def snap_up(v: float, grid: float) -> float:
    return math.ceil(round(v / grid, 6)) * grid


def snap_down(v: float, grid: float) -> float:
    return math.floor(round(v / grid, 6)) * grid


def r6(v: float) -> float:
    return round(v, 6)


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.w * self.h

    def inflate(self, d: float) -> "Box":
        return Box(self.x0 - d, self.y0 - d, self.x1 + d, self.y1 + d)

    def contains(self, o: "Box", tol: float = 1e-6) -> bool:
        return o.x0 >= self.x0 - tol and o.y0 >= self.y0 - tol and o.x1 <= self.x1 + tol and o.y1 <= self.y1 + tol

    def overlap(self, o: "Box") -> float:
        dx = min(self.x1, o.x1) - max(self.x0, o.x0)
        dy = min(self.y1, o.y1) - max(self.y0, o.y0)
        return dx * dy if dx > 1e-9 and dy > 1e-9 else 0.0

    def gap(self, o: "Box") -> float:
        """Edge-to-edge distance (0 if touching/overlapping)."""
        dx = max(o.x0 - self.x1, self.x0 - o.x1, 0.0)
        dy = max(o.y0 - self.y1, self.y0 - o.y1, 0.0)
        return math.hypot(dx, dy) if dx > 0 and dy > 0 else max(dx, dy)

    def as_list(self) -> list[float]:
        return [r6(self.x0), r6(self.y0), r6(self.x1), r6(self.y1)]


@dataclass
class MacroInst:
    name: str
    master: str
    width: float
    height: float
    group: str = ""          # main_sram / tspm / other
    key: tuple = ()          # e.g. (bank, index) or (lane,)
    pin_side_r0: str = "bottom"


@dataclass
class Placement:
    inst: str
    master: str
    x: float
    y: float
    orient: str
    width: float
    height: float

    @property
    def box(self) -> Box:
        if self.orient in ("R90", "R270", "MXR90", "MYR90"):
            return Box(self.x, self.y, self.x + self.height, self.y + self.width)
        return Box(self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass
class Geometry:
    die: Box
    core: Box
    mode: str
    breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "die_area_um": self.die.as_list(), "core_area_um": self.core.as_list(),
                "die_w_um": r6(self.die.w), "die_h_um": r6(self.die.h), "core_w_um": r6(self.core.w),
                "core_h_um": r6(self.core.h), "die_area_mm2": r6(self.die.area / 1e6),
                "core_area_mm2": r6(self.core.area / 1e6), "breakdown": self.breakdown}


# --------------------------------------------------------------------------- orientation
FLIP_SIDE = {  # where an R0-frame pin edge ends up after an orientation
    "R0": {"bottom": "bottom", "top": "top", "left": "left", "right": "right"},
    "MX": {"bottom": "top", "top": "bottom", "left": "left", "right": "right"},
    "MY": {"bottom": "bottom", "top": "top", "left": "right", "right": "left"},
    "R180": {"bottom": "top", "top": "bottom", "left": "right", "right": "left"},
}


def orient_facing(pin_side_r0: str, want: str, allowed: list[str]) -> str:
    """Orientation (among `allowed`) that puts the pin edge on side `want`."""
    for o in ("R0", "MX", "MY", "R180"):
        if o in allowed and FLIP_SIDE[o].get(pin_side_r0) == want:
            return o
    raise ConfigError(f"no allowed orientation {allowed} puts {pin_side_r0}-edge pins on the {want} side")


def pin_side(p: Placement, pin_side_r0: str) -> str:
    return FLIP_SIDE.get(p.orient, {}).get(pin_side_r0, "unknown")


# --------------------------------------------------------------------------- arrangements
@dataclass
class ArrangementResult:
    name: str
    description: str
    placements: list[Placement]
    envelope_w: float
    envelope_h: float


def _groups(macros: list[MacroInst]):
    main = sorted([m for m in macros if m.group == "main_sram"], key=lambda m: m.key)
    tspm = sorted([m for m in macros if m.group == "tspm"], key=lambda m: m.key)
    other = [m for m in macros if m.group not in ("main_sram", "tspm")]
    if other:
        raise ConfigError(f"arrangement cannot place ungrouped macros: {[m.name for m in other]}")
    return main, tspm


def _row(ms: list[MacroInst], y: float, cx: float, gap: float, orient: str) -> list[Placement]:
    if not ms:
        return []
    total = sum(m.width for m in ms) + gap * (len(ms) - 1)
    x = cx - total / 2
    out = []
    for m in ms:
        out.append(Placement(m.name, m.master, x, y, orient, m.width, m.height))
        x += m.width + gap
    return out


def _row_w(ms, gap):
    return sum(m.width for m in ms) + gap * (len(ms) - 1) if ms else 0.0


ARRANGEMENTS: dict[str, str] = {
    "periphery_rows": "Memory-centric: main SRAM banks 0-1 along the top edge (pins down) and 2-3 along the "
                      "bottom edge (pins up); the 4 tile-scratchpad (TSPM) macros as a row across the core centre "
                      "(pins down). Logic fills the two bands between the rows.",
    "tspm_center_2x2": "Tensor/tile-centric: main SRAM rows on the top and bottom edges as in periphery_rows; the "
                       "TSPM macros as a 2x2 cluster in the core centre, upper pair pins up and lower pair pins down, "
                       "so the vector/tensor logic can surround its scratchpad.",
    "west_east_columns": "Distributed: banks 0-1 in a column on the west edge and 2-3 on the east edge (each macro "
                         "pins down with a pin channel below it); TSPM 2x2 cluster in the centre. Compute logic "
                         "occupies the central region between the memory columns.",
    "top_cluster": "Memory-compact / CPU-centric: all main SRAM in two stacked rows at the top (pins down, a pin "
                   "channel between the rows); TSPM row on the bottom edge (pins up); one contiguous logic region "
                   "in between for CPU, fabric, DMA and peripherals.",
}


def arrange(name: str, core: Box, macros: list[MacroInst], halo: float, channel: float,
            allowed: list[str], pin_side_r0: str, side_gap_min: float = 0.0) -> ArrangementResult:
    """Place macros by a named arrangement inside `core` (bbox lower-left coords)."""
    if name not in ARRANGEMENTS:
        raise ConfigError(f"unknown arrangement '{name}' (known: {', '.join(ARRANGEMENTS)})")
    main, tspm = _groups(macros)
    # side-by-side spacing: the channel between two macros in a row holds std-cell
    # rows, so it must also be wide enough to contain a vertical PDN strap of
    # each net (side_gap_min = vertical strap pitch + width, from the PDN config);
    # a narrower channel left rails unpowered (PDN-0179 in experiment C, attempt 1)
    gap = max(channel, 2 * halo, side_gap_min)
    pin_gap = channel + 2 * halo + 4.0        # stacked: pin channel + both halos + row-snap allowance
    down = orient_facing(pin_side_r0, "bottom", allowed)
    up = orient_facing(pin_side_r0, "top", allowed)
    cx = (core.x0 + core.x1) / 2
    cy = (core.y0 + core.y1) / 2
    band = max(channel, 2 * halo)          # minimum logic / pin-escape band
    pl: list[Placement] = []
    half = len(main) // 2
    top_main, bot_main = main[:half], main[half:]
    mh = max((m.height for m in main), default=0.0)
    th = max((m.height for m in tspm), default=0.0)
    if name == "periphery_rows":
        pl += _row(top_main, core.y1 - halo - mh, cx, gap, down)
        pl += _row(bot_main, core.y0 + halo, cx, gap, up)
        pl += _row(tspm, cy - th / 2, cx, gap, down)
        env_w = max(_row_w(top_main, gap), _row_w(bot_main, gap), _row_w(tspm, gap)) + 2 * halo
        env_h = 2 * mh + th + 2 * halo + 2 * (band + 2 * halo)
    elif name == "tspm_center_2x2":
        pl += _row(top_main, core.y1 - halo - mh, cx, gap, down)
        pl += _row(bot_main, core.y0 + halo, cx, gap, up)
        upper, lower = tspm[: len(tspm) // 2], tspm[len(tspm) // 2:]
        pl += _row(upper, cy + halo, cx, gap, up)
        pl += _row(lower, cy - halo - th, cx, gap, down)
        env_w = max(_row_w(top_main, gap), _row_w(bot_main, gap), _row_w(upper, gap)) + 2 * halo
        env_h = 2 * mh + 2 * th + 2 * halo + 2 * halo + 2 * (band + 2 * halo)
    elif name == "west_east_columns":
        west, east = main[:half], main[half:]
        mw = max(m.width for m in main)
        for col, x in ((west, core.x0 + halo), (east, core.x1 - halo - mw)):
            y = core.y1 - halo - mh
            for m in col:
                pl.append(Placement(m.name, m.master, x, y, down, m.width, m.height))
                y -= mh + pin_gap
        upper, lower = tspm[: len(tspm) // 2], tspm[len(tspm) // 2:]
        pl += _row(upper, cy + halo, cx, gap, up)
        pl += _row(lower, cy - halo - th, cx, gap, down)
        env_w = 2 * (mw + halo) + _row_w(upper, gap) + 2 * (band + 2 * halo)
        env_h = max(len(west), len(east)) * (mh + pin_gap) + 2 * halo
    elif name == "top_cluster":
        pl += _row(top_main, core.y1 - halo - mh, cx, gap, down)
        pl += _row(bot_main, core.y1 - halo - 2 * mh - pin_gap, cx, gap, down)
        pl += _row(tspm, core.y0 + halo, cx, gap, up)
        env_w = max(_row_w(top_main, gap), _row_w(bot_main, gap), _row_w(tspm, gap)) + 2 * halo
        env_h = 2 * mh + pin_gap + th + 2 * halo + band + 2 * halo
    else:  # pragma: no cover
        raise ConfigError(name)
    return ArrangementResult(name, ARRANGEMENTS[name], pl, env_w, env_h)


def snap_placements(pl: list[Placement], core: Box, site_w: float, row_h: float, mgrid: float) -> list[Placement]:
    """Snap macro origins to the site/row grid of the core (and manufacturing grid)."""
    out = []
    for p in pl:
        x = core.x0 + round((p.x - core.x0) / site_w) * site_w
        y = core.y0 + round((p.y - core.y0) / row_h) * row_h
        x = round(round(x / mgrid) * mgrid, 6)
        y = round(round(y / mgrid) * mgrid, 6)
        out.append(Placement(p.inst, p.master, x, y, p.orient, p.width, p.height))
    return out


# --------------------------------------------------------------------------- sizing
def size_mode_b(spec: FloorplanSpec, std_cell_area_um2: float, macros: list[MacroInst], halo: float,
                site_w: float, row_h: float, mgrid: float, envelope: tuple[float, float] | None = None) -> Geometry:
    if spec.mode != "B":
        raise ConfigError("size_mode_b called for a MODE A spec")
    if std_cell_area_um2 <= 0:
        raise ConfigError("mapped std-cell area must be > 0 (synthesis report missing?)")
    a_std = std_cell_area_um2 * spec.logic_growth / spec.target_util
    a_mac = sum(m.width * m.height for m in macros)
    a_halo = sum((m.width + 2 * halo) * (m.height + 2 * halo) for m in macros) - a_mac
    a_corr = sum(spec.corridor_um * (m.width + m.height) for m in macros)
    subtotal = a_std + a_mac + a_halo + a_corr
    a_pdn = subtotal * spec.pdn_overhead / (1 - spec.pdn_overhead)
    a_core = subtotal + a_pdn
    w = math.sqrt(a_core / spec.aspect_ratio)
    h = a_core / w
    grown = False
    if envelope:
        ew, eh = envelope
        if w < ew:
            w, h, grown = ew, max(a_core / ew, eh), True
        if h < eh:
            h, w, grown = eh, max(a_core / eh, w), True
    w = snap_up(w, site_w)
    h = snap_up(h, row_h)
    # core origin on the site grid (x) and row grid (y) so OpenROAD does not snap it
    mx = r6(snap_up(spec.core_margin_um, site_w))
    my = r6(snap_up(spec.core_margin_um, row_h))
    core = Box(mx, my, r6(mx + w), r6(my + h))
    die = Box(0.0, 0.0, r6(snap_up(core.x1 + mx, mgrid)), r6(snap_up(core.y1 + my, mgrid)))
    m = min(mx, my)
    std_region = core.area - a_mac - a_halo - a_corr - a_pdn
    bd = {
        "std_cell_area_mapped_um2": r6(std_cell_area_um2),
        "logic_growth": spec.logic_growth,
        "target_util": spec.target_util,
        "std_cell_region_required_um2": r6(a_std),
        "macro_area_um2": r6(a_mac),
        "macro_halo_area_um2": r6(a_halo),
        "routing_corridor_area_um2": r6(a_corr),
        "pdn_overhead_area_um2": r6(a_pdn),
        "core_area_required_um2": r6(a_core),
        "core_area_um2": r6(core.area),
        "std_cell_region_available_um2": r6(std_region),
        "implied_std_cell_util": r6(std_cell_area_um2 * spec.logic_growth / std_region) if std_region > 0 else None,
        "grown_to_arrangement_envelope": grown,
        "envelope_um": [r6(envelope[0]), r6(envelope[1])] if envelope else None,
        "core_margin_um": [mx, my],
        "io_ring": "not included (logical pins only)",
    }
    return Geometry(die, core, "B", bd)


def mode_a(spec: FloorplanSpec, std_cell_area_um2: float, macros: list[MacroInst], halo: float) -> Geometry:
    die = Box(*spec.die_area)
    core = Box(*spec.core_area)
    a_mac = sum(m.width * m.height for m in macros)
    a_halo = sum((m.width + 2 * halo) * (m.height + 2 * halo) for m in macros) - a_mac
    std_region = core.area - a_mac - a_halo
    bd = {"std_cell_area_mapped_um2": r6(std_cell_area_um2), "macro_area_um2": r6(a_mac),
          "macro_halo_area_um2": r6(a_halo), "core_area_um2": r6(core.area),
          "std_cell_region_available_um2": r6(std_region),
          "implied_std_cell_util": r6(std_cell_area_um2 / std_region) if std_region > 0 else None,
          "io_ring": "not included (logical pins only)"}
    return Geometry(die, core, "A", bd)


# --------------------------------------------------------------------------- macro grouping
def classify_macros(insts: list[tuple[str, str]], lef_macros: dict, groups: dict[str, str]) -> list[MacroInst]:
    """insts = [(instance_name, master)] -> MacroInst with group/key from design regexes."""
    out = []
    for name, master in insts:
        name = name.replace("\\", "")      # OpenDB escapes [ ] in hierarchical names
        if master not in lef_macros:
            raise ConfigError(f"macro master {master} of {name} has no LEF abstract")
        lm = lef_macros[master]
        grp, key = "", ()
        for gname, rx in groups.items():
            mm = re.search(rx, name)
            if mm:
                grp, key = gname, tuple(int(g) for g in mm.groups() if g is not None)
                break
        out.append(MacroInst(name, master, lm.width, lm.height, grp, key, lm.pin_side_r0()))
    return out
