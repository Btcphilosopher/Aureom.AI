"""Metric extraction from tool outputs and gate findings.

Sources (only): Yosys stat/check/log, the mapped netlist, OpenDB JSON written by
scripts/analysis/*.tcl, OpenSTA text reports, OpenROAD logs.  When a source is
missing the metric is None and the gate that needs it fails or is NOT_RUN.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .config import DesignConfig, PlatformProfile
from .liberty import parse_liberty
from .validate import Finding

ICG_CELLS = {"sg13g2_slgcp_1", "sg13g2_lgcp_1", "sky130_fd_sc_hd__dlclkp_1", "sky130_fd_sc_hd__sdlclkp_1"}


# =========================================================================== synthesis
def parse_yosys_stat(text: str) -> dict:
    """Per-module own area/cells and the whole-design totals of a Yosys stat."""
    mods: dict[str, dict] = {}
    for m in re.finditer(r"^=== (.+?) ===\s*$(.*?)(?=^=== |\Z)", text, re.M | re.S):
        name, body = m.group(1).strip(), m.group(2)
        if name == "design hierarchy":
            continue
        cells = {c: int(n) for c, n in re.findall(r"^\s{5}(\S+)\s+(\d+)\s*$", body, re.M)}
        a = re.search(r"Chip area for module '\\?(.+?)': ([\d.]+)", body)
        mods[name] = {"cells": cells, "own_area": float(a.group(2)) if a else 0.0}
    tot = {}
    h = re.search(r"=== design hierarchy ===(.*)", text, re.S)
    if h:
        body = h.group(1)
        hier = re.findall(r"^(\s+)(\S.*?)\s+(\d+)\s*$", body.split("Number of wires")[0], re.M)
        tot["hierarchy"] = [(len(ind), n, int(c)) for ind, n, c in hier]
        cm = re.search(r"Number of cells:\s+(\d+)(.*?)\n\n", body, re.S)
        if cm:
            tot["cells"] = int(cm.group(1))
            tot["cell_types"] = {c: int(n) for c, n in re.findall(r"^\s+(\S+)\s+(\d+)\s*$", cm.group(2), re.M)}
        a = re.search(r"Chip area for top module '\\?(.+?)': ([\d.]+)", body)
        tot["chip_area"] = float(a.group(2)) if a else None
        s = re.search(r"of which used for sequential elements: ([\d.]+)", body)
        tot["seq_area"] = float(s.group(1)) if s else None
    return {"modules": mods, "total": tot}


def _subtree_area(mods: dict, name: str, macro_area: dict[str, float], memo: dict) -> tuple[float, float]:
    """(std-cell area, macro area) of a module including its children."""
    if name in memo:
        return memo[name]
    m = mods.get(name)
    if not m:
        return (0.0, 0.0)
    std, mac = 0.0, 0.0
    for cell, n in m["cells"].items():
        if cell in macro_area:
            mac += n * macro_area[cell]
        elif cell in mods:
            s, a = _subtree_area(mods, cell, macro_area, memo)
            std += n * s
            mac += n * a
    own_mac = sum(n * macro_area[c] for c, n in m["cells"].items() if c in macro_area)
    std += m["own_area"] - own_mac
    memo[name] = (std, mac)
    return memo[name]


def netlist_instances(netlist: Path, top: str) -> dict:
    """Cell types instantiated per module + macro instance paths (hierarchical)."""
    text = netlist.read_text(errors="replace")
    modules = {}
    for m in re.finditer(r"^module\s+(\\\S+|\S+?)\s*\((.*?)^endmodule", text, re.S | re.M):
        name = m.group(1).lstrip("\\")
        insts = re.findall(r"^\s+(\\?\S+)\s+(\\\S+|[A-Za-z_][\w$]*)\s*\(", m.group(2), re.M)
        modules[name] = [(t.lstrip("\\"), i.lstrip("\\")) for t, i in insts
                         if t not in ("module", "input", "output", "wire", "assign", "inout", "reg")]
    return modules


def macro_paths(modules: dict, top: str, macro_masters: set[str]) -> list[dict]:
    out = []

    def walk(mod, prefix):
        for typ, inst in modules.get(mod, []):
            if typ in macro_masters:
                out.append({"name": prefix + inst, "master": typ})
            elif typ in modules:
                walk(typ, prefix + inst + "/")
    walk(top, "")
    return out


def synthesis_summary(sctx, design: DesignConfig, pf: PlatformProfile) -> dict:
    rep = sctx.reports_dir
    stat_text = (rep / "synth_stat.txt").read_text()
    st = parse_yosys_stat(stat_text)
    tot = st["total"]
    macro_area: dict[str, float] = {}
    for mname, lib in pf.macro_liberty().items():
        c = parse_liberty(lib).cells.get(mname)
        if c and c.area:
            macro_area[mname] = c.area
    std_lib = {}
    for lib in pf.liberty_files():
        std_lib.update(parse_liberty(lib).cells)
    types = tot.get("cell_types", {})
    macros = {c: n for c, n in types.items() if c in pf.macros}
    mac_area = sum(n * macro_area.get(c, 0.0) for c, n in macros.items())
    seq = sum(n for c, n in types.items() if c in std_lib and std_lib[c].is_ff)
    latch = sum(n for c, n in types.items() if c in std_lib and std_lib[c].is_latch)
    icg = sum(n for c, n in types.items() if c in std_lib and (std_lib[c].is_icg or c in ICG_CELLS))
    async_ff = sum(n for c, n in types.items() if c in std_lib and std_lib[c].async_reset)
    known = set(std_lib) | set(pf.macros)
    unknown_types = {c: n for c, n in types.items() if c not in known}
    tie = sum(n for c, n in types.items() if "tie" in c or "conb" in c)
    buf = sum(n for c, n in types.items() if re.search(r"_(buf|inv|dlygate)", c))
    std_cells = sum(n for c, n in types.items() if c not in pf.macros)
    # unresolved modules: instantiated types that are neither modules nor library cells
    netlist = sctx.results_dir / "1_synth.v"
    mods = netlist_instances(netlist, design.top)
    inst_types = {t for lst in mods.values() for t, _ in lst}
    unresolved = sorted(t for t in inst_types if t not in mods and t not in known)
    paths = macro_paths(mods, design.top, set(pf.macros))
    # area per top-level instance (hierarchy kept above MAX_UNGROUP_SIZE)
    memo: dict = {}
    top_mod = st["modules"].get(design.top, {"cells": {}})
    per_inst = []
    for typ, inst in mods.get(design.top, []):
        if typ in st["modules"]:
            s, a = _subtree_area(st["modules"], typ, macro_area, memo)
            per_inst.append({"instance": inst, "module": typ, "std_cell_area_um2": round(s, 1), "macro_area_um2": round(a, 1)})
    top_glue = st["modules"].get(design.top, {}).get("own_area", 0.0)
    log = (sctx.logs_dir / "1_1_yosys.log")
    warnings = []
    if log.is_file():
        cnt = defaultdict(int)
        for w in re.findall(r"^Warning: (.*)$", log.read_text(errors="replace"), re.M):
            cnt[re.sub(r"/\S+/", "", w)[:200]] += 1
        warnings = [{"message": k, "count": v} for k, v in cnt.items()]
    check = (rep / "synth_check.txt").read_text() if (rep / "synth_check.txt").is_file() else ""
    probs = re.search(r"Found and reported (\d+) problems", check)
    lat_cells = {c: n for c, n in types.items() if c in std_lib and std_lib[c].is_latch}
    return {
        "netlist": str(netlist),
        "total_cells": tot.get("cells"),
        "std_cells": std_cells,
        "sequential_cells": seq,
        "latch_cells": latch,
        "latch_cell_types": lat_cells,
        "icg_cells": icg,
        "async_reset_flops": async_ff,
        "combinational_cells": std_cells - seq - latch - icg,
        "tie_cells": tie,
        "buffer_inverter_cells": buf,
        "chip_area_incl_macros_um2": tot.get("chip_area"),
        "macro_area_um2": round(mac_area, 3),
        "std_cell_area_um2": round((tot.get("chip_area") or 0) - mac_area, 3),
        "sequential_area_um2": tot.get("seq_area"),
        "macros": macros,
        "macro_instances": paths,
        "unknown_cell_types": unknown_types,
        "unresolved_modules": unresolved,
        "check_problems": int(probs.group(1)) if probs else None,
        "warnings": warnings,
        "area_by_instance": sorted(per_inst, key=lambda d: -d["std_cell_area_um2"]),
        "top_glue_area_um2": round(top_glue, 1),
        "clock_reset_observations": {
            "icg_instances": icg,
            "flops_with_async_reset": async_ff,
            "flops_total": seq,
            "note": "single functional clock clk + JTAG tck (SDC); resets async-assert/sync-deassert via "
                    "sfv_rst_sync (u_rs_por/u_rs_sys/u_rs_cpu); the reset tree is unbuffered after synthesis "
                    "(repair_design buffers it; balanced tree only at CTS)",
        },
        "stat_report": str(rep / "synth_stat.txt"),
    }


def synth_findings_gate2(s: dict) -> list[Finding]:
    out = []
    if not s.get("total_cells"):
        out.append(Finding(2, "error", "NO_STAT", "synthesis statistics missing"))
    if s.get("check_problems") is None:
        out.append(Finding(2, "error", "NO_CHECK", "yosys check report missing"))
    elif s["check_problems"] > 0:
        out.append(Finding(2, "error", "CHECK_PROBLEMS", f"yosys check reported {s['check_problems']} problems"))
    if s.get("latch_cells"):
        out.append(Finding(2, "error", "UNEXPECTED_LATCH", f"latch cells inferred: {s['latch_cell_types']}"))
    for w in s.get("warnings", []):
        out.append(Finding(2, "info", "YOSYS_WARNING", f"{w['count']}x {w['message']}"))
    return out


def synth_findings_gate3(s: dict, design: DesignConfig, pf: PlatformProfile) -> list[Finding]:
    out = []
    for u in s.get("unresolved_modules", []):
        if u not in design.allowed_blackboxes:
            out.append(Finding(3, "error", "UNRESOLVED_BLACKBOX", f"unresolved module/black box in netlist: {u}"))
    for c, n in s.get("unknown_cell_types", {}).items():
        out.append(Finding(3, "error", "UNKNOWN_CELL", f"{n}x {c}: not a std cell, macro, or netlist module"))
    exp = design.expected_macros.get(pf.name)
    if exp is None:
        out.append(Finding(3, "error", "NO_EXPECTATION", f"no expected macro inventory for {pf.name}"))
    elif s.get("macros") != exp:
        out.append(Finding(3, "error", "MACRO_INVENTORY", f"synthesised hard macros {s.get('macros')} != expected {exp}"))
    if len(s.get("macro_instances", [])) != sum((s.get("macros") or {}).values()):
        out.append(Finding(3, "error", "MACRO_PATHS", "macro instance paths do not match the macro count"))
    return out


# =========================================================================== stage JSON
def compact_stage(fm: dict) -> dict:
    kinds = fm.get("instance_kinds", {})
    die = fm.get("die_um")
    core = fm.get("core_um")
    std_area = kinds.get("std", {}).get("area_um2", 0.0)
    for k in ("tie", "tapcell", "endcap"):
        std_area += kinds.get(k, {}).get("area_um2", 0.0)
    mac_area = kinds.get("macro", {}).get("area_um2", 0.0)
    core_area = (core[2] - core[0]) * (core[3] - core[1]) if core else None
    die_area = (die[2] - die[0]) * (die[3] - die[1]) if die else None
    row_area = fm.get("row_area_um2")
    return {
        "die_um": die, "core_um": core,
        "die_area_mm2": round(die_area / 1e6, 4) if die_area else None,
        "core_area_mm2": round(core_area / 1e6, 4) if core_area else None,
        "std_cell_area_um2": round(std_area, 1), "macro_area_um2": round(mac_area, 1),
        "instances": {k: v.get("count") for k, v in kinds.items()},
        "placement_rows": fm.get("rows"), "row_area_um2": row_area,
        "std_cell_util_of_rows": round(std_area / row_area, 4) if row_area else None,
        "core_util_incl_macros": round((std_area + mac_area) / core_area, 4) if core_area else None,
        "hpwl_um": fm.get("hpwl_um"),
        "std_cell_area_by_group_um2": {g: v.get("area_um2") for g, v in fm.get("std_cell_groups", {}).items()},
        "placement_status": fm.get("placement_status"),
        "io_pins_total": fm.get("io_pins_total"), "io_pins_placed": fm.get("io_pins_placed"),
        "high_fanout_nets": fm.get("high_fanout_nets", [])[:10],
        "macros": [{k: m[k] for k in ("name", "master", "bbox", "orient", "status")} for m in fm.get("macros", [])],
    }


def macro_findings(fm: dict, run, lef) -> list[Finding]:
    from .geometry import Box, Placement, classify_macros
    from .validate import check_macro_placement
    out = []
    core = Box(*fm["core_um"])
    pl = []
    for m in fm.get("macros", []):
        b = m["bbox"]
        lm = lef.macros.get(m["master"])
        w, h = (lm.width, lm.height) if lm else (b[2] - b[0], b[3] - b[1])
        pl.append(Placement(m["name"].replace("\\", ""), m["master"], b[0], b[1], m["orient"], w, h))
        if m["status"] not in ("FIRM", "LOCKED", "PLACED", "COVER"):
            out.append(Finding(6, "error", "MACRO_NOT_FIXED", f"{m['name']} status {m['status']}"))
        if m["signal_pins_total"] and m["signal_pins_connected"] == 0:
            out.append(Finding(6, "error", "MACRO_UNCONNECTED", f"{m['name']}: no signal pin connected"))
    macros = classify_macros([(m["name"], m["master"]) for m in fm.get("macros", [])], lef.macros, run.design.macro_groups)
    sp = run.spec.macros
    # manual: full halo + pin channel; automatic: the halo requested from macro_placement
    out += check_macro_placement(pl, core, macros, sp.halo_um,
                                 sp.channel_um if sp.placement == "manual" else sp.halo_um,
                                 run.platform.macro_allowed_orients, lef, run.design.expected_macros.get(run.platform.name))
    from .validate import check_macro_channels_pdn
    params = {**run.platform.pdn.get("params", {}), **run.spec.pdn.params}
    # automatic placement: narrow channels are reported as warnings; the
    # measured check_power_grid result (GATE 9) is authoritative
    out += check_macro_channels_pdn(pl, params, lef, "error" if sp.placement == "manual" else "warning")
    if sp.placement == "auto":
        out.append(Finding(6, "info", "AUTO_MACRO", "automatic placement (OpenROAD macro_placement): halo/channel "
                           "clearances were requested from the tool; legality checked for overlap/containment/orientation/pin-side"))
    return out


def tapcell_findings(fm: dict, pf: PlatformProfile, ctx) -> list[Finding]:
    out = []
    log = ctx.logs_dir / "2_5_floorplan_tapcell.log"
    if not log.is_file():
        return [Finding(8, "error", "NO_TAPCELL_LOG", "tapcell stage log missing")]
    txt = log.read_text(errors="replace")
    if "Elapsed time" not in txt:
        out.append(Finding(8, "error", "TAPCELL_INCOMPLETE", "tapcell stage did not finish"))
    kinds = fm.get("instance_kinds", {})
    taps = kinds.get("tapcell", {}).get("count", 0)
    ends = kinds.get("endcap", {}).get("count", 0)
    method = pf.tapcell.method if pf.tapcell else "none"
    if method == "tapcell" and taps == 0:
        out.append(Finding(8, "error", "NO_TAPS", "platform requires tap cells but none were inserted"))
    if method == "cut_rows" and taps:
        out.append(Finding(8, "warning", "UNEXPECTED_TAPS", "tap cells found on a cut_rows-only platform"))
    m = re.findall(r"\[INFO (?:TAP|ODB)-\d+\] (.*(?:row|tap|cap|cut).*)", txt)
    out.append(Finding(8, "info", "TAPCELL_RESULT", f"method={method} tapcells={taps} endcaps={ends}; " + "; ".join(m[:4])))
    for w in re.findall(r"\[WARNING [A-Z]+-\d+\].*", txt)[:10]:
        out.append(Finding(8, "warning", "TAPCELL_WARNING", w))
    return out


def pdn_findings(path: Path) -> list[Finding]:
    if not path.is_file():
        return [Finding(9, "error", "NO_PDN_CHECK", f"PDN check output missing ({path}): check not run")]
    d = json.loads(path.read_text())
    out = []
    if not d.get("nets"):
        out.append(Finding(9, "error", "NO_SUPPLY_NETS", "no POWER/GROUND nets found"))
    for n in d.get("nets", []):
        if not n.get("connected"):
            out.append(Finding(9, "error", "PDN_DISCONNECTED", f"check_power_grid {n['net']}: rc={n['check_rc']} result={n['result']} "
                                                                  f"({n['unconnected_lines']} unconnected-node lines in {Path(n['unconnected_report']).name})"))
        else:
            out.append(Finding(9, "info", "PDN_CONNECTED", f"check_power_grid {n['net']}: connected"))
    pa = d.get("macro_pin_access") or []
    if not pa:
        out.append(Finding(9, "error", "NO_PIN_ACCESS_CHECK", "per-pin macro power access check missing"))
    for e in pa:
        if not e.get("ok"):
            out.append(Finding(9, "error", "MACRO_PG_NO_VIA", f"{e['inst'].replace(chr(92), '')}: PG pin {e['pin']} ({e['layer']}) has no PDN via"))
    if pa and not d.get("macro_pin_access_errors"):
        out.append(Finding(9, "info", "MACRO_PG_VIAS", f"all {len(pa)} macro PG pins have PDN vias (min {min(e['vias'] for e in pa)} per pin)"))
    if d.get("macro_pg_errors"):
        out.append(Finding(9, "error", "MACRO_PG", f"{d['macro_pg_errors']} macro PG pins not on their supply net"))
    else:
        out.append(Finding(9, "info", "MACRO_PG_OK", f"{len(d.get('macro_pg', []))} macro PG pins on the expected nets"))
    return out


def placement_findings(pm: dict) -> list[Finding]:
    out = []
    pc = pm.get("placement_check")
    if not pc:
        return [Finding(10, "error", "NOT_CHECKED", "check_placement did not run")]
    if not pc.get("legal"):
        out.append(Finding(10, "error", "ILLEGAL_PLACEMENT", f"check_placement: {pc.get('message')}"))
    st = pm.get("placement_status", {})
    if st.get("NONE") or st.get("UNPLACED"):
        out.append(Finding(10, "error", "UNPLACED", f"unplaced instances: {st}"))
    if not out:
        out.append(Finding(10, "info", "LEGAL", "check_placement passed; all instances placed"))
    return out


def pin_findings(pm: dict, run) -> list[Finding]:
    from .pins import expand, pin_groups
    out = []
    die = pm["die_um"]
    pins = pm.get("io_pins", [])
    if pm.get("io_pins_placed") != pm.get("io_pins_total"):
        out.append(Finding(7, "error", "PINS_UNPLACED", f"{pm.get('io_pins_total', 0) - pm.get('io_pins_placed', 0)} I/O pins unplaced"))
    pf = run.platform
    want_layer = {"left": pf.routing.io_h_layer, "right": pf.routing.io_h_layer,
                  "top": pf.routing.io_v_layer, "bottom": pf.routing.io_v_layer}
    boxes = []
    for p in pins:
        for b in p["boxes"]:
            on_edge = abs(b[0] - die[0]) < 1e-3 or abs(b[2] - die[2]) < 1e-3 or abs(b[1] - die[1]) < 1e-3 or abs(b[3] - die[3]) < 1e-3
            if not on_edge:
                out.append(Finding(7, "error", "PIN_OFF_BOUNDARY", f"pin {p['name']} not on the die boundary"))
            boxes.append((p["name"], b))
        if p["boxes"] and p["layer"] != want_layer.get(p["edge"]):
            out.append(Finding(7, "warning", "PIN_LAYER", f"pin {p['name']} on {p['layer']} at {p['edge']} edge (expected {want_layer.get(p['edge'])})"))
    boxes.sort(key=lambda t: (t[1][0], t[1][1]))
    for i in range(len(boxes)):
        for j in range(i + 1, min(i + 8, len(boxes))):
            a, b = boxes[i][1], boxes[j][1]
            if min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]):
                out.append(Finding(7, "error", "PIN_OVERLAP", f"pins {boxes[i][0]} and {boxes[j][0]} overlap"))
    if run.spec.pins.mode == "plan":
        names = [p["name"] for p in pins]
        edge_of = {p["name"]: p["edge"] for p in pins}
        for g, edge, pats in pin_groups(run.design, run.spec.pins):
            for n in expand(names, pats):
                if edge_of.get(n) != edge:
                    out.append(Finding(7, "error", "PIN_EDGE", f"pin {n} (group {g}) on {edge_of.get(n)} edge, constraint {edge}"))
    if not [f for f in out if f.severity == "error"]:
        out.append(Finding(7, "info", "PINS_OK", f"{len(pins)} pins placed on the boundary, no overlaps, edge constraints met"))
    return out


def timing_findings(pm: dict, design: DesignConfig, setup_rpt: Path) -> list[Finding]:
    out = []
    t = pm.get("timing")
    if not t:
        return [Finding(11, "error", "STA_NOT_RUN", "pre-route STA did not run")]
    if t.get("wns_ns") is None:
        out.append(Finding(11, "error", "NO_SLACK", "STA returned no slack (unconstrained design?)"))
    if not setup_rpt.is_file() or "Startpoint" not in setup_rpt.read_text(errors="replace"):
        out.append(Finding(11, "error", "NO_PATHS", "no constrained timing paths reported"))
    if t.get("clock_period_ns") is None:
        out.append(Finding(11, "error", "NO_CLOCK", f"clock {design.clock.name} not found by STA"))
    out.append(Finding(11, "info", "PRE_ROUTE", f"{t.get('label')}: WNS {t.get('wns_ns')} ns, TNS {t.get('tns_ns')} ns, WHS {t.get('whs_ns')} ns"))
    if t.get("whs_ns") is not None and t["whs_ns"] < 0:
        out.append(Finding(11, "warning", "HOLD_PRE_CTS", f"hold WHS {t['whs_ns']} ns / THS {t.get('ths_ns')} ns with ideal "
                                                           "clocks: to be repaired after CTS (repair_timing -hold)"))
    if t.get("wns_ns") is not None and t["wns_ns"] < 0:
        out.append(Finding(11, "warning", "SETUP_VIOLATED", f"pre-route setup WNS {t['wns_ns']} ns at the target period"))
    drv = parse_drv(setup_rpt.parent / setup_rpt.name.replace("_timing_setup.rpt", "_drv.rpt"))
    if drv["max_slew"] or drv["max_capacitance"] or drv["max_fanout"]:
        out.append(Finding(11, "warning", "DRV", f"design-rule violators after repair_design: slew {drv['max_slew']}, "
                                                 f"cap {drv['max_capacitance']}, fanout {drv['max_fanout']} ({'; '.join(drv['examples'][:3])})"))
    return out


def parse_paths(rpt: Path, limit: int = 10) -> list[dict]:
    if not rpt.is_file():
        return []
    txt = rpt.read_text(errors="replace")
    out = []
    for blk in txt.split("Startpoint: ")[1:limit + 1]:
        sp = blk.split("\n")[0].strip()
        ep = re.search(r"Endpoint: (.*)", blk)
        sl = re.search(r"^\s*([-\d.]+)\s+slack", blk, re.M)
        arr = re.search(r"^\s*([-\d.]+)\s+data arrival time", blk, re.M)
        req = re.search(r"^\s*([-\d.]+)\s+data required time", blk, re.M)
        grp = re.search(r"Path Group: (\S+)", blk)
        pins = re.findall(r"^\s+(?:[-\d.]+\s+){2,6}[\^v]\s+(\S+)\s+\((\S+)\)", blk, re.M)
        out.append({"startpoint": sp, "endpoint": ep.group(1).strip() if ep else None, "group": grp.group(1) if grp else None,
                    "slack_ns": float(sl.group(1)) if sl else None, "arrival_ns": float(arr.group(1)) if arr else None,
                    "required_ns": float(req.group(1)) if req else None,
                    "points": [{"pin": p, "cell": c} for p, c in pins]})
    return out


def parse_drv(rpt: Path) -> dict:
    """Counts of max slew / capacitance / fanout violators (report_check_types -violators)."""
    out = {"max_slew": 0, "max_capacitance": 0, "max_fanout": 0, "examples": []}
    if not rpt.is_file():
        return out
    sect = None
    for line in rpt.read_text(errors="replace").splitlines():
        l = line.strip()
        if l in ("max slew", "max capacitance", "max fanout"):
            sect = l.replace(" ", "_")
        elif "(VIOLATED)" in l and sect:
            out[sect] += 1
            if len(out["examples"]) < 6:
                out["examples"].append(f"{sect}: {l.split()[0]}")
    return out


def timing_summary(pm: dict, out_dir: Path, stage: str, clock: str = "clk") -> dict:
    t = pm.get("timing") or {}
    allp = parse_paths(out_dir / f"{stage}_timing_setup.rpt", 200)
    hold = parse_paths(out_dir / f"{stage}_timing_hold.rpt", 50)
    period = t.get("clock_period_ns")
    clk_paths = [p for p in allp if p["group"] == clock]
    setup = clk_paths + [p for p in allp if p["group"] != clock]
    worst_clk = min((p["slack_ns"] for p in clk_paths if p["slack_ns"] is not None), default=None)
    drv = parse_drv(out_dir / f"{stage}_drv.rpt")
    r2r = [p for p in parse_paths(out_dir / f"{stage}_timing_reg2reg.rpt", 50) if p["group"] == clock]
    r2r_slack = min((p["slack_ns"] for p in r2r if p["slack_ns"] is not None), default=None)
    groups = {}
    for p in allp:
        g = p["group"]
        if p["slack_ns"] is not None and (g not in groups or p["slack_ns"] < groups[g]):
            groups[g] = p["slack_ns"]
    return {
        "worst_slack_by_group_ns": groups,
        "label": t.get("label"), "wns_ns": t.get("wns_ns"), "tns_ns": t.get("tns_ns"), "whs_ns": t.get("whs_ns"),
        "ths_ns": t.get("ths_ns"), "clock_period_ns": period,
        "clk_group_worst_slack_ns": worst_clk,
        "reg2reg_worst_slack_ns": r2r_slack,
        "reg2reg_path_delay_ns": round(period - r2r_slack, 4) if (period and r2r_slack is not None) else None,
        "reg2reg_critical_paths": [{k: p[k] for k in ("startpoint", "endpoint", "slack_ns", "arrival_ns")} for p in r2r[:10]],
        "reg2reg_critical_path_points": r2r[0]["points"] if r2r else [],
        "clk_critical_path_delay_ns": round(period - worst_clk, 4) if (period and worst_clk is not None) else None,
        "critical_paths": [{k: p[k] for k in ("startpoint", "endpoint", "group", "slack_ns", "arrival_ns")} for p in setup[:12]],
        "critical_path_points": clk_paths[0]["points"] if clk_paths else [],
        "hold_paths": sorted([{k: p[k] for k in ("startpoint", "endpoint", "group", "slack_ns")} for p in hold],
                             key=lambda x: x["slack_ns"] if x["slack_ns"] is not None else 1e9)[:8],
        "drv": drv,
        "note": "Pre-route, pre-CTS (ideal clocks). Not an achieved frequency.",
    }


def power_summary(rpt: Path, pf: PlatformProfile) -> dict | None:
    if not rpt.is_file():
        return None
    txt = rpt.read_text(errors="replace")
    rows = {}
    for name in ("Sequential", "Combinational", "Clock", "Macro", "Pad", "Total"):
        m = re.search(rf"^{name}\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt, re.M)
        if m:
            rows[name.lower()] = {"internal_w": float(m.group(1)), "switching_w": float(m.group(2)),
                                  "leakage_w": float(m.group(3)), "total_w": float(m.group(4))}
    sram_power = {}
    for mname, lib in pf.macro_liberty().items():
        c = parse_liberty(lib).cells.get(mname)
        sram_power[mname] = bool(c and c.has_power)
    notes = []
    mac = rows.get("macro", {}).get("total_w")
    if mac == 0.0 and any(sram_power.values()):
        notes.append("OpenSTA attributed 0 W to the hard macros although their Liberty contains non-zero leakage / "
                     "internal power: SRAM power is NOT captured; totals cover standard cells only")
    if (rows.get("clock") or {}).get("total_w", 1) < 1e-4:
        notes.append("no clock tree exists before CTS: clock-network power is essentially absent")
    return {"label": "VECTORLESS ESTIMATE -- no switching activity (VCD/SAIF) available; OpenSTA default propagation "
                     "from input activity 0.1; ideal clocks. NOT used for ranking.",
            "groups": rows, "macro_liberty_has_power_data": sram_power, "notes": notes}


def orfs_log_metrics(ctx) -> dict:
    out = {}
    for f in sorted(ctx.logs_dir.glob("*.log")):
        txt = f.read_text(errors="replace")
        e = re.search(r"Elapsed time: (\S+)\[h:\]min:sec.*Peak memory: (\d+)KB", txt)
        d = {}
        if e:
            d["elapsed"] = e.group(1)
            d["peak_mem_mb"] = round(int(e.group(2)) / 1024, 1)
        ins = re.search(r"Inserted (\d+) buffers", txt)
        if ins:
            d["buffers_inserted"] = int(ins.group(1))
        rsz = re.search(r"Resized (\d+) instances", txt)
        if rsz:
            d["instances_resized"] = int(rsz.group(1))
        ov = re.findall(r"overflow:\s*([\d.]+)", txt)
        if ov:
            d["gpl_final_overflow"] = float(ov[-1])
        warns = re.findall(r"\[WARNING ([A-Z]+-\d+)\]", txt)
        if warns:
            cnt = defaultdict(int)
            for w in warns:
                cnt[w] += 1
            d["warnings"] = dict(cnt)
        errs = re.findall(r"\[ERROR ([A-Z]+-\d+)\].*", txt)
        if errs:
            d["errors"] = errs[:5]
        out[f.stem] = d
    return out


# =========================================================================== route
def parse_grt_log(txt: str) -> dict:
    out: dict = {}
    blocks = txt.split("Final congestion report:")
    if len(blocks) > 1:
        tbl = blocks[-1]
        layers = {}
        for m in re.finditer(r"^(\S+)\s+(\d+)\s+(\d+)\s+([\d.]+)%\s+(\d+)\s*/\s*(\d+)\s*/\s*(\d+)", tbl, re.M):
            layers[m.group(1)] = {"resource": int(m.group(2)), "demand": int(m.group(3)), "usage_pct": float(m.group(4)),
                                  "overflow_h": int(m.group(5)), "overflow_v": int(m.group(6)), "overflow_total": int(m.group(7))}
        out["layers"] = {k: v for k, v in layers.items() if k != "Total"}
        if "Total" in layers:
            out["total"] = layers["Total"]
    wl = re.findall(r"Total wirelength:\s*([\d.]+)\s*um", txt)
    if wl:
        out["routed_wirelength_um"] = float(wl[-1])
    ov = re.findall(r"\[INFO GRT-\d+\] Final number of overflows?: (\d+)|Final overflow\s*:?\s*(\d+)", txt)
    nets = re.search(r"Number of routed nets\s*:\s*(\d+)|\[INFO GRT-0001\] Minimum degree: \d+|Routed nets: (\d+)", txt)
    if nets and nets.group(1):
        out["routed_nets"] = int(nets.group(1))
    if ov:
        vals = [int(a or b) for a, b in ov]
        out["final_overflow"] = vals[-1]
    crit = re.findall(r"\[WARNING GRT-\d+\].*", txt)
    out["grt_warnings"] = crit[:10]
    return out


def route_summary(out_dir: Path, log: Path) -> dict:
    rm = {}
    f = out_dir / "route_metrics.json"
    if f.is_file():
        rm = json.loads(f.read_text())
    if log.is_file():
        rm.update(parse_grt_log(log.read_text(errors="replace")))
    cg = out_dir / "grt_congestion.rpt"
    rm["congestion_report_lines"] = sum(1 for _ in open(cg)) if cg.is_file() else 0
    return rm


def congestion_hotspots(rpt: Path, geo: dict, near_um: float = 60.0) -> dict | None:
    """Classify FastRoute overflowed GCells (congestion report) by location:
    adjacent to a hard macro (within near_um of its outline) or in the open logic
    region, and list the densest 200 um windows.  Report data only."""
    from .visualise import parse_congestion_report
    ent = parse_congestion_report(rpt)
    if not rpt.is_file():
        return None
    macros = [m["bbox"] for m in geo.get("macros", [])]

    def near(b):
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        return any(m[0] - near_um <= cx <= m[2] + near_um and m[1] - near_um <= cy <= m[3] + near_um for m in macros)
    tot = sum(o for _, o in ent)
    nm = [o for b, o in ent if near(b)]
    win: dict = {}
    for b, o in ent:
        k = (int(b[0] // 200), int(b[1] // 200))
        win[k] = win.get(k, 0) + o
    top = sorted(win.items(), key=lambda kv: -kv[1])[:5]
    kinds = {}
    for blk in rpt.read_text(errors="replace").split("violation type:")[1:]:
        k = blk.split("\n")[0].strip()
        kinds[k] = kinds.get(k, 0) + 1
    return {"overflowed_gcells": len(ent), "overflow_sum": tot, "by_type": kinds,
            "near_macro_gcells": len(nm), "near_macro_overflow": sum(nm),
            "near_macro_fraction": round(sum(nm) / tot, 3) if tot else None,
            "top_windows_200um": [{"x0_um": k[0] * 200, "y0_um": k[1] * 200, "overflow": v} for k, v in top],
            "label": "from grt_congestion.rpt (FastRoute, preliminary)"}


def route_findings(rm: dict, rc: int) -> list[Finding]:
    out = []
    if rc != 0 or not rm.get("completed"):
        return [Finding(12, "error", "GRT_FAILED", f"global routing did not complete (rc {rc}): {rm.get('message', '')}")]
    tot = rm.get("total", {})
    of = tot.get("overflow_total")
    if of is None:
        out.append(Finding(12, "warning", "NO_OVERFLOW_DATA", "congestion table not found in the log"))
    elif of > 0:
        out.append(Finding(12, "warning", "CONGESTION", f"global-route overflow {of} (H {tot.get('overflow_h')}, V {tot.get('overflow_v')}); see grt_congestion.rpt"))
    else:
        out.append(Finding(12, "info", "NO_OVERFLOW", "global route completed with zero overflow"))
    return out


# =========================================================================== gates 14/15
def repro_findings(run) -> list[Finding]:
    rec = run.rec
    out = []
    need = {"git_revision": rec.get("git_revision"), "tools": rec.get("tools"), "netlist_sha256": rec.get("netlist_sha256"),
            "config_mk_sha256": rec.get("config_mk_sha256"), "platform provenance": rec.get("platform", {}).get("provenance"),
            "seed": rec.get("spec", {}).get("seed")}
    for k, v in need.items():
        if not v:
            out.append(Finding(14, "error", "MISSING_METADATA", f"run metadata missing: {k}"))
    tools = rec.get("tools") or {}
    for k in ("openroad", "yosys", "orfs"):
        if "MISSING" in str(tools.get(k, "MISSING")):
            out.append(Finding(14, "error", "TOOL_UNKNOWN", f"{k} version not recorded"))
    if str(rec.get("git_revision", "")).endswith("+dirty"):
        out.append(Finding(14, "warning", "DIRTY_TREE", "FloorplanLab sources had uncommitted changes when the run started"))
    rp = rec.get("repro_check")
    if rp:
        if rp.get("identical"):
            out.append(Finding(14, "info", "REPRODUCED", f"re-run reproduced: {rp.get('compared')}"))
        else:
            out.append(Finding(14, "error", "NOT_REPRODUCED", f"re-run differs: {rp.get('differences')}"))
    else:
        out.append(Finding(14, "info", "REPRO_METADATA_ONLY", "metadata complete; bit-exact re-run not performed for this run"))
    return out


def integrity_findings(run) -> list[Finding]:
    rec = run.rec
    out = []
    if "OK" not in str(rec.get("vendored_sources_check", "")):
        out.append(Finding(15, "error", "SOURCES", f"vendored RTL not verified against repository archives: {rec.get('vendored_sources_check')}"))
    if run.spec.macros.mode != "physical":
        out.append(Finding(15, "error", "SUBSTITUTION", f"macro mode {run.spec.macros.mode}: not a physical SRAM implementation"))
    if run.platform.status != "enabled":
        out.append(Finding(15, "error", "PLATFORM", f"platform {run.platform.name} is {run.platform.status}"))
    if rec.get("design", {}).get("top") != run.design.top:
        out.append(Finding(15, "error", "TOP", "design top mismatch"))
    out.append(Finding(15, "info", "PROVENANCE", "all metrics in run.json are parsed from Yosys/OpenROAD/OpenSTA outputs listed in 'stages'"))
    return out
