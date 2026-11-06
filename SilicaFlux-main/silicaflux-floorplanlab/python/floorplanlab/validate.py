"""Engineering checks behind the FloorplanLab quality gates.

Every check returns Findings; an 'error' finding fails its gate.  Nothing here
"passes" by default: a check that cannot run (missing data) is an error or is
reported as NOT_RUN by the gate evaluator, never as a pass.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import DesignConfig, PlatformProfile, RunSpec
from .geometry import Box, Geometry, MacroInst, Placement, pin_side
from .lef import LefLibrary, load_lefs
from .liberty import parse_liberty

PLACEHOLDER = re.compile(r"<UNSET:[A-Z_]+>|<[^<>/]+>")


@dataclass
class Finding:
    gate: int
    severity: str          # error | warning | info
    code: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def errors(fs: list[Finding]) -> list[Finding]:
    return [f for f in fs if f.severity == "error"]


def _path_ok(p: str | None, gate: int, what: str, out: list[Finding]) -> bool:
    if not p:
        out.append(Finding(gate, "error", "MISSING_PATH", f"{what}: no path configured"))
        return False
    if PLACEHOLDER.search(p):
        out.append(Finding(gate, "error", "UNFILLED_TEMPLATE", f"{what}: template placeholder not filled: {p}"))
        return False
    if not Path(p).is_file():
        out.append(Finding(gate, "error", "FILE_NOT_FOUND", f"{what}: file not found: {p}"))
        return False
    return True


# --------------------------------------------------------------------------- GATE 4
def check_platform(pf: PlatformProfile, need_macros: list[str] | None = None) -> tuple[list[Finding], LefLibrary | None]:
    out: list[Finding] = []
    if pf.status != "enabled":
        reason = pf.disabled_reason or ("commercial template: foundry kit data not supplied" if pf.status == "template" else "")
        out.append(Finding(4, "error", "PLATFORM_NOT_ENABLED", f"platform {pf.name} is {pf.status}: {reason}".strip()))
        for p in [pf.tech_lef, *pf.sc_lefs]:
            _path_ok(p, 4, "LEF", out)
        for c, corner in pf.corners.items():
            for lib in corner.liberty:
                _path_ok(lib, 4, f"Liberty ({c})", out)
        for m in pf.missing:
            out.append(Finding(4, "error", "MISSING_COLLATERAL", m))
        return out, None
    lefs_ok = _path_ok(pf.tech_lef, 4, "technology LEF", out)
    for p in pf.sc_lefs:
        lefs_ok &= _path_ok(p, 4, "standard-cell LEF", out)
    if pf.analysis_corner not in pf.corners:
        out.append(Finding(4, "error", "NO_CORNER", f"analysis corner '{pf.analysis_corner}' not defined"))
    for c, corner in pf.corners.items():
        if not corner.liberty:
            out.append(Finding(4, "error", "NO_LIBERTY", f"corner {c} has no Liberty"))
        for lib in corner.liberty:
            _path_ok(lib, 4, f"standard-cell Liberty ({c})", out)
    for mc in pf.missing_corners:
        out.append(Finding(4, "warning", "CORNER_UNAVAILABLE", f"{mc.get('corner')}: {mc.get('missing')}"))
    for key in ("set_rc_tcl",):
        if pf.rc.get(key):
            _path_ok(pf.rc[key], 4, f"RC ({key})", out)
        else:
            out.append(Finding(4, "error", "NO_RC", "no RC assumption (setRC) configured"))
    if pf.tapcell and pf.tapcell.script:
        _path_ok(pf.tapcell.script, 4, "tapcell script", out)
    _path_ok(pf.pdn.get("tcl"), 4, "PDN Tcl", out)
    if pf.routing:
        for k in ("fastroute_tcl", "make_tracks_tcl"):
            v = getattr(pf.routing, k, None)
            if v:
                _path_ok(v, 4, f"routing {k}", out)
    macro_paths = []
    for name, m in pf.macros.items():
        if need_macros is not None and name not in need_macros:
            continue
        if _path_ok(m.lef, 4, f"macro LEF {name}", out):
            macro_paths.append(m.lef)
        if pf.analysis_corner not in m.liberty:
            out.append(Finding(4, "error", "MACRO_NO_LIB", f"macro {name} has no Liberty for corner {pf.analysis_corner}"))
        for c, lib in m.liberty.items():
            _path_ok(lib, 4, f"macro Liberty {name} ({c})", out)
        if m.gds:
            if not Path(m.gds).is_file():
                out.append(Finding(4, "warning", "MACRO_NO_GDS", f"macro GDS missing for {name} (needed for final merge)"))
    if not lefs_ok:
        return out, None
    lef = load_lefs([pf.tech_lef, *pf.sc_lefs, *macro_paths])
    out += check_lef_facts(pf, lef, need_macros)
    return out, lef


def check_lef_facts(pf: PlatformProfile, lef: LefLibrary, need_macros: list[str] | None = None) -> list[Finding]:
    out: list[Finding] = []
    site = lef.sites.get(pf.place_site)
    if not site:
        out.append(Finding(4, "error", "INVALID_SITE", f"placement site '{pf.place_site}' not defined in LEF "
                                                          f"(sites: {', '.join(lef.sites) or 'none'})"))
    else:
        if pf.row_height_um and abs(site.height - pf.row_height_um) > 1e-6:
            out.append(Finding(4, "error", "ROW_HEIGHT_MISMATCH", f"profile row height {pf.row_height_um} != LEF site height {site.height}"))
        if pf.site_width_um and abs(site.width - pf.site_width_um) > 1e-6:
            out.append(Finding(4, "error", "SITE_WIDTH_MISMATCH", f"profile site width {pf.site_width_um} != LEF {site.width}"))
    routing = {l.name for l in lef.routing_layers()}
    if pf.routing:
        for k in ("min_layer", "max_layer", "io_h_layer", "io_v_layer"):
            v = getattr(pf.routing, k)
            if v not in routing:
                out.append(Finding(4, "error", "UNKNOWN_LAYER", f"routing.{k} = '{v}' is not a routing layer in the tech LEF ({sorted(routing)})"))
        for v in pf.routing.pdn_layers:
            if v not in routing:
                out.append(Finding(4, "error", "UNKNOWN_LAYER", f"PDN layer '{v}' is not a routing layer in the tech LEF"))
        if pf.routing.min_layer in routing and pf.routing.max_layer in routing:
            if lef.layer_index(pf.routing.min_layer) > lef.layer_index(pf.routing.max_layer):
                out.append(Finding(4, "error", "LAYER_ORDER", "min routing layer is above max routing layer"))
        for k, want in (("io_h_layer", "HORIZONTAL"), ("io_v_layer", "VERTICAL")):
            v = getattr(pf.routing, k)
            if v in lef.layers and lef.layers[v].direction and lef.layers[v].direction.upper() != want:
                out.append(Finding(4, "warning", "IO_LAYER_DIRECTION",
                                   f"routing.{k} = {v} has preferred direction {lef.layers[v].direction} (ORFS platform choice kept)"))
    for kind in ("hi", "lo"):
        cell = (pf.tie_cells.get(kind) or [None])[0]
        if cell and cell not in lef.macros:
            out.append(Finding(4, "error", "TIE_CELL_MISSING", f"tie-{kind} cell {cell} not in std-cell LEF"))
    for cell in pf.fill_cells:
        if cell not in lef.macros:
            out.append(Finding(4, "error", "FILL_CELL_MISSING", f"fill cell {cell} not in std-cell LEF"))
    if pf.tapcell:
        for k in ("tapcell_master", "endcap_master"):
            v = getattr(pf.tapcell, k, None)
            if v and v not in lef.macros:
                out.append(Finding(4, "error", "TAPCELL_MISSING", f"{k} {v} not in std-cell LEF"))
    for name, m in pf.macros.items():
        if need_macros is not None and name not in need_macros:
            continue
        lm = lef.macros.get(name)
        if not lm:
            out.append(Finding(4, "error", "MACRO_NOT_IN_LEF", f"macro {name} not found in its LEF"))
            continue
        if not lm.is_block:
            out.append(Finding(4, "error", "MACRO_NOT_BLOCK", f"{name} is CLASS {lm.cls}, expected BLOCK"))
        pg = lm.pg_pins()
        for pin in pf.macro_pg_pins:
            if pin not in pg:
                out.append(Finding(4, "error", "MACRO_PG_PIN", f"{name}: PG pin {pin} (profile) not in LEF"))
        for pin in pg:
            if pin not in pf.macro_pg_pins:
                out.append(Finding(4, "error", "MACRO_PG_UNMAPPED", f"{name}: LEF PG pin {pin} has no supply mapping in the profile"))
        for pin in pg.values():
            for layer in pin.layers:
                if layer not in lef.layers:
                    out.append(Finding(4, "error", "MACRO_PIN_LAYER", f"{name}.{pin.name} on unknown layer {layer}"))
        bad = [o for o in pf.macro_allowed_orients if o not in lm.legal_orients()]
        if bad:
            out.append(Finding(4, "error", "ILLEGAL_ORIENT", f"{name}: profile allows {bad} but LEF SYMMETRY {lm.symmetry} does not"))
        for c, libp in m.liberty.items():
            if Path(libp).is_file():
                lib = parse_liberty(libp)
                if name not in lib.cells:
                    out.append(Finding(4, "error", "MACRO_NOT_IN_LIB", f"{name} not in {Path(libp).name}"))
                elif not lib.cells[name].has_timing:
                    out.append(Finding(4, "error", "MACRO_NO_TIMING", f"{name} has no timing arcs in {Path(libp).name}"))
                else:
                    lp = lib.cells[name].pins
                    missing = [p for p in lm.signal_pins() if p.split("[")[0] not in lp and p not in lp]
                    if missing:
                        out.append(Finding(4, "error", "MACRO_PIN_MISMATCH",
                                           f"{name}: {len(missing)} LEF signal pins absent from {Path(libp).name} (e.g. {missing[:3]})"))
    return out


# --------------------------------------------------------------------------- GATE 1
def check_design(design: DesignConfig, pf: PlatformProfile) -> list[Finding]:
    out: list[Finding] = []
    try:
        files = design.resolved_files(pf)
    except Exception as e:
        return [Finding(1, "error", "RTL_TECH_FILE", str(e))]
    top_found = False
    for f in files:
        if not f.is_file():
            out.append(Finding(1, "error", "RTL_MISSING", f"RTL file not found: {f}"))
            continue
        if re.search(rf"^\s*module\s+{re.escape(design.top)}\b", f.read_text(errors="replace"), re.M):
            top_found = True
    if not top_found:
        out.append(Finding(1, "error", "TOP_NOT_FOUND", f"top module {design.top} not declared in the RTL file list"))
    from .config import PROJECT
    for d in design.rtl.include_dirs:
        if not (PROJECT / d).is_dir():
            out.append(Finding(1, "error", "INCLUDE_DIR", f"include dir not found: {d}"))
    sdc = PROJECT / design.sdc_template
    if not sdc.is_file():
        out.append(Finding(1, "error", "SDC_MISSING", f"SDC template not found: {sdc}"))
    else:
        out += check_sdc_text(sdc.read_text(), design)
    if pf.name not in design.expected_macros and pf.status == "enabled":
        out.append(Finding(1, "error", "NO_MACRO_EXPECTATION", f"design has no expected macro inventory for {pf.name}"))
    for m in design.expected_macros.get(pf.name, {}):
        if m not in pf.macros:
            out.append(Finding(1, "error", "MACRO_NOT_IN_PLATFORM", f"expected macro {m} not provided by platform {pf.name}"))
    return out


def check_sdc_text(sdc: str, design: DesignConfig) -> list[Finding]:
    out = []
    clocks = re.findall(r"create_clock\s+.*?-name\s+(\S+).*?\[get_ports\s+(\S+?)\]", sdc)
    if not clocks:
        out.append(Finding(11, "error", "NO_CLOCK", "SDC defines no clock (create_clock)"))
    elif design.clock.name not in [c[0] for c in clocks]:
        out.append(Finding(11, "error", "MISSING_CLOCK", f"design clock {design.clock.name} not created in SDC"))
    if "set_input_delay" not in sdc or "set_output_delay" not in sdc:
        out.append(Finding(11, "warning", "IO_DELAYS", "SDC lacks input or output delays"))
    return out


# --------------------------------------------------------------------------- run spec
def check_run(spec: RunSpec, pf: PlatformProfile, lef: LefLibrary | None) -> list[Finding]:
    out: list[Finding] = []
    if spec.platform != pf.name:
        out.append(Finding(5, "error", "PLATFORM_MISMATCH", f"run platform {spec.platform} != {pf.name}"))
    if spec.macros.mode != "physical":
        out.append(Finding(15, "warning", "NOT_PRODUCTION_MODE",
                           f"macro mode '{spec.macros.mode}': run is NOT eligible for physical readiness"))
    if lef is not None:
        params = {**pf.pdn.get("params", {}), **spec.pdn.params}
        for k, v in params.items():
            if k.endswith("_layer") and isinstance(v, str) and v not in lef.layers:
                out.append(Finding(9, "error", "PDN_UNKNOWN_LAYER", f"pdn {k} = {v} not in tech LEF"))
        for pre in ("rail", "strap1", "strap2", "ring"):
            layer = params.get(f"{pre}_layer") or (params.get("ring_layers") or [None])[0] if pre == "ring" else params.get(f"{pre}_layer")
            width = params.get(f"{pre}_width")
            if layer in lef.layers and width is not None:
                l = lef.layers[layer]
                mw = l.min_width or l.width
                if mw and float(width) < mw - 1e-9:
                    out.append(Finding(9, "error", "PDN_WIDTH_ILLEGAL", f"pdn {pre}_width {width} < {layer} minimum width {mw}"))
            pitch = params.get(f"{pre}_pitch")
            if pitch is not None and width is not None and float(pitch) <= 2 * float(width):
                out.append(Finding(9, "error", "PDN_PITCH", f"pdn {pre}_pitch {pitch} must exceed 2 x width {width} (VDD+VSS pair)"))
        out += check_macro_pin_coverage(params, pf, lef)
        for lst in ("ring_layers", "macro_connect"):
            for layer in params.get(lst, []) or []:
                if layer not in lef.layers:
                    out.append(Finding(9, "error", "PDN_UNKNOWN_LAYER", f"pdn {lst} layer {layer} not in tech LEF"))
    if spec.place.density is not None and not (0 < spec.place.density <= 1):
        out.append(Finding(10, "error", "PLACE_DENSITY", "placement density must be in (0, 1]"))
    return out


def check_macro_pin_coverage(params: dict, pf: PlatformProfile, lef: LefLibrary) -> list[Finding]:
    """PDN_MACRO_PIN_COVERAGE: the core straps on the macro-connect target layer
    must cross every macro PG pin shape.  For a strap layer whose preferred
    direction is perpendicular to the pin stripes, a strap of the right net
    crosses a pin stripe of length L only if pitch + width <= L (VDD and VSS
    alternate within one pitch).  L comes from the macro LEF."""
    out: list[Finding] = []
    conn = params.get("macro_connect") or []
    if len(conn) != 2 or not pf.macros:
        return out
    pin_layer, strap_layer = conn
    strap = next(((params.get(f"{k}_pitch"), params.get(f"{k}_width")) for k in ("strap1", "strap2", "rail")
                  if params.get(f"{k}_layer") == strap_layer), None)
    if strap is None or strap[0] is None:
        out.append(Finding(9, "error", "PDN_MACRO_CONNECT", f"macro_connect target layer {strap_layer} carries no core strap"))
        return out
    pitch, width = float(strap[0]), float(strap[1])
    sdir = (lef.layers.get(strap_layer).direction or "").upper() if strap_layer in lef.layers else ""
    for name in pf.macros:
        lm = lef.macros.get(name)
        if not lm:
            continue
        for pn, pin in lm.pg_pins().items():
            rects = [r for r in pin.rects if r.layer == pin_layer]
            if not rects:
                continue
            # stripe length along the axis the straps step across
            lens = [(r.y2 - r.y1) if sdir == "HORIZONTAL" else (r.x2 - r.x1) for r in rects]
            need = pitch + width
            if max(lens) < need - 1e-6:
                out.append(Finding(9, "error", "PDN_MACRO_PIN_COVERAGE",
                                   f"{name}.{pn}: longest {pin_layer} stripe {max(lens):.2f} um < {strap_layer} pitch+width "
                                   f"{need:.2f} um -- the pin is not guaranteed any PDN via"))
            elif min(lens) < need - 1e-6:
                short = sum(1 for x in lens if x < need - 1e-6)
                out.append(Finding(9, "warning", "PDN_MACRO_STRIPE_COVERAGE",
                                   f"{name}.{pn}: {short} {pin_layer} stripes of {min(lens):.2f} um may receive no via "
                                   f"({strap_layer} pitch+width {need:.2f} um); pin still connected through its longer stripes"))
    return out


def vertical_strap_window(params: dict, lef: LefLibrary) -> float:
    """Pitch + width of the core strap layer whose preferred direction is
    VERTICAL (the straps that can feed rails inside a side-by-side channel)."""
    best = 0.0
    for k in ("strap1", "strap2"):
        layer, p, w = params.get(f"{k}_layer"), params.get(f"{k}_pitch"), params.get(f"{k}_width")
        if layer in lef.layers and (lef.layers[layer].direction or "").upper() == "VERTICAL" and p and w:
            best = max(best, float(p) + float(w))
    return best


def check_macro_channels_pdn(pl: list[Placement], params: dict, lef: LefLibrary, severity: str = "error") -> list[Finding]:
    """PDN_CHANNEL: a horizontal gap between vertically-overlapping macros that is
    wider than 0 but narrower than the vertical strap pitch + width contains
    std-cell rows that no vertical strap is guaranteed to reach."""
    out: list[Finding] = []
    win = vertical_strap_window(params, lef)
    if win <= 0:
        return out
    for i, a in enumerate(pl):
        for b in pl[i + 1:]:
            A, B = a.box, b.box
            if min(A.y1, B.y1) - max(A.y0, B.y0) <= 1.0:
                continue                      # not side by side
            gap = max(B.x0 - A.x1, A.x0 - B.x1)
            if 0 < gap < win - 1e-6:
                out.append(Finding(6, severity, "PDN_CHANNEL",
                                   f"{a.inst} | {b.inst}: {gap:.2f} um channel < vertical strap pitch+width {win:.2f} um"))
    return out


# --------------------------------------------------------------------------- GATE 5
def check_geometry(g: Geometry, pf: PlatformProfile, lef: LefLibrary | None, ring_extent_um: float = 0.0) -> list[Finding]:
    out: list[Finding] = []
    die, core = g.die, g.core
    if die.w <= 0 or die.h <= 0 or core.w <= 0 or core.h <= 0:
        out.append(Finding(5, "error", "NONPOSITIVE", f"die/core must have positive size (die {die.as_list()}, core {core.as_list()})"))
        return out
    if not die.contains(core):
        out.append(Finding(5, "error", "CORE_OUTSIDE_DIE", f"core {core.as_list()} is not inside die {die.as_list()}"))
    margin = min(core.x0 - die.x0, core.y0 - die.y0, die.x1 - core.x1, die.y1 - core.y1)
    if ring_extent_um and margin < ring_extent_um - 1e-6:
        out.append(Finding(5, "error", "MARGIN_TOO_SMALL", f"core margin {margin:.2f} um < PDN ring extent {ring_extent_um:.2f} um"))
    mg = (lef.manufacturing_grid if lef else None) or 0.005
    for v in die.as_list() + core.as_list():
        if abs(round(v / mg) * mg - v) > 1e-6:
            out.append(Finding(5, "error", "OFF_GRID", f"coordinate {v} not on manufacturing grid {mg}"))
            break
    if pf.site_width_um and pf.row_height_um:
        rows = core.h / pf.row_height_um
        if abs(rows - round(rows)) > 1e-4:
            out.append(Finding(5, "warning", "CORE_HEIGHT_ROWS", f"core height {core.h} is not an integer number of rows ({rows:.3f}); top partial row unused"))
        sites = core.w / pf.site_width_um
        if abs(sites - round(sites)) > 1e-4:
            out.append(Finding(5, "warning", "CORE_WIDTH_SITES", f"core width {core.w} is not an integer number of sites"))
    util = g.breakdown.get("implied_std_cell_util")
    if util is None or util <= 0:
        out.append(Finding(5, "error", "NO_STD_REGION", "macros (with halos) leave no std-cell region in the core"))
    elif util >= 1.0:
        out.append(Finding(5, "error", "OVER_UTILISED", f"implied std-cell utilisation {util:.2f} >= 1"))
    elif util > 0.85:
        out.append(Finding(5, "warning", "HIGH_UTIL", f"implied std-cell utilisation {util:.2f} > 0.85"))
    return out


# --------------------------------------------------------------------------- GATE 6
def check_macro_placement(pl: list[Placement], core: Box, macros: list[MacroInst], halo: float, channel: float,
                          allowed: list[str], lef: LefLibrary | None, expected: dict[str, int] | None = None) -> list[Finding]:
    out: list[Finding] = []
    byname = {m.name: m for m in macros}
    placed = {p.inst for p in pl}
    for m in macros:
        if m.name not in placed:
            out.append(Finding(6, "error", "UNPLACED_MACRO", f"macro {m.name} ({m.master}) is not placed"))
    if expected is not None:
        cnt: dict[str, int] = {}
        for m in macros:
            cnt[m.master] = cnt.get(m.master, 0) + 1
        if cnt != expected:
            out.append(Finding(6, "error", "MACRO_INVENTORY", f"macro inventory {cnt} != expected {expected}"))
    for p in pl:
        if p.inst not in byname:
            out.append(Finding(6, "error", "UNKNOWN_MACRO", f"placement for unknown instance {p.inst}"))
            continue
        legal = set(allowed)
        if lef and p.master in lef.macros:
            legal &= lef.macros[p.master].legal_orients()
        if p.orient not in legal:
            out.append(Finding(6, "error", "ILLEGAL_ORIENT", f"{p.inst}: orientation {p.orient} not in {sorted(legal)}"))
        if not core.contains(p.box):
            out.append(Finding(6, "error", "MACRO_OUTSIDE_CORE", f"{p.inst} {p.box.as_list()} outside core {core.as_list()}"))
        elif not core.contains(p.box.inflate(halo)):
            out.append(Finding(6, "warning", "HALO_OUTSIDE_CORE", f"{p.inst}: halo of {halo} um crosses the core edge"))
    for i, a in enumerate(pl):
        for b in pl[i + 1:]:
            if a.box.overlap(b.box) > 0:
                out.append(Finding(6, "error", "MACRO_OVERLAP", f"{a.inst} overlaps {b.inst}"))
            elif a.box.gap(b.box) < halo - 1e-6:
                out.append(Finding(6, "error", "MACRO_SPACING", f"{a.inst} - {b.inst} spacing {a.box.gap(b.box):.2f} um < halo {halo} um"))
    # pin access: the strip in front of each macro's pin edge must be inside the
    # core and not blocked by another macro body (pins must be able to escape)
    for p in pl:
        m = byname.get(p.inst)
        if not m:
            continue
        side = pin_side(p, m.pin_side_r0)
        b = p.box
        d = max(channel, halo) - 1e-3       # required free pin-escape depth
        strip = {"bottom": Box(b.x0, b.y0 - d, b.x1, b.y0), "top": Box(b.x0, b.y1, b.x1, b.y1 + d),
                 "left": Box(b.x0 - d, b.y0, b.x0, b.y1), "right": Box(b.x1, b.y0, b.x1 + d, b.y1)}.get(side)
        if strip is None:
            out.append(Finding(6, "error", "PIN_SIDE_UNKNOWN", f"{p.inst}: cannot determine pin side for {p.orient}"))
            continue
        if not core.contains(strip):
            out.append(Finding(6, "error", "PIN_ACCESS_EDGE", f"{p.inst}: {side}-side pins face the core boundary (no escape)"))
        for q in pl:
            if q is not p and strip.overlap(q.box) > 0:
                out.append(Finding(6, "error", "PIN_ACCESS_BLOCKED", f"{p.inst}: {side}-side pin channel blocked by {q.inst}"))
    return out


# --------------------------------------------------------------------------- GATE 7 (pre)
def check_pin_plan(groups: list[tuple[str, str, list[str]]], ports: list[str], die: Box, layer_pitch: dict[str, float],
                   min_distance_tracks: int, corner_avoid: float) -> list[Finding]:
    """groups = [(group, edge, patterns)].  Detect overlapping/unknown/over-capacity constraints."""
    out: list[Finding] = []
    owner: dict[str, str] = {}
    per_edge: dict[str, int] = {}
    for g, edge, pats in groups:
        from .pins import pin_match
        matched = [p for p in ports if any(pin_match(p, pat) for pat in pats)]
        if not matched:
            out.append(Finding(7, "error", "PIN_UNKNOWN", f"pin group {g}: patterns {pats} match no top-level port"))
        for p in matched:
            if p in owner and owner[p] != g:
                out.append(Finding(7, "error", "PIN_CONFLICT", f"port {p} constrained by both {owner[p]} and {g}"))
            owner[p] = g
        per_edge[edge] = per_edge.get(edge, 0) + len(matched)
    for edge, n in per_edge.items():
        length = (die.w if edge in ("top", "bottom") else die.h) - 2 * corner_avoid
        pitch = layer_pitch.get(edge, 0.5) * max(1, min_distance_tracks)
        cap = int(length / pitch) if pitch > 0 else 0
        if n > cap:
            out.append(Finding(7, "error", "PIN_CAPACITY", f"{n} pins on {edge} edge exceed capacity {cap}"))
    unc = [p for p in ports if p not in owner]
    if unc:
        out.append(Finding(7, "info", "PIN_UNCONSTRAINED", f"{len(unc)} ports without edge constraint (placed by the tool)"))
    return out
