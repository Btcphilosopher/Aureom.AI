"""Constrained search helpers: simulated annealing on an explicit, documented
geometric surrogate, and Pareto-front analysis on MEASURED results.

The surrogate is only a candidate generator.  It never ranks designs: every
candidate it proposes must be run through ORFS (floorplan -> place -> route
estimate) and only measured, gate-passing runs enter the Pareto analysis.

Surrogate cost (lower is better), per candidate (arrangement, util, AR):
  die_area_mm2 * w_area
  + w_wire * sum_macros(signal_pins * manhattan(pin-edge midpoint, centroid of
                        the std-cell region)) / 1e6
  infeasible geometry (validators) -> rejected
The std-cell-region centroid stands in for "where the logic will be"; the
experiments show where this proxy is wrong (docs/RESULTS.md).
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import yaml

from .config import load_run
from .geometry import ARRANGEMENTS, Box, FLIP_SIDE, arrange, size_mode_b, snap_placements
from .validate import check_geometry, check_macro_placement, errors


def surrogate(spec_dict: dict, ctx) -> tuple[float | None, dict]:
    """ctx = dict(macros, lef, platform, std_area, design)."""
    from .config import FloorplanSpec
    fp = FloorplanSpec(**spec_dict["floorplan"])
    m = spec_dict["macros"]
    pf, lef, macros = ctx["platform"], ctx["lef"], ctx["macros"]
    halo, ch = m.get("halo_um", 20.0), m.get("channel_um", 40.0)
    from .validate import vertical_strap_window
    sg = vertical_strap_window(pf.pdn.get("params", {}), lef) + 2 * pf.site_width_um
    probe = arrange(m["arrangement"], Box(0, 0, 1e5, 1e5), macros, halo, ch, pf.macro_allowed_orients, "bottom", sg)
    g = size_mode_b(fp, ctx["std_area"], macros, halo, pf.site_width_um, pf.row_height_um, 0.005,
                    (probe.envelope_w, probe.envelope_h))
    pl = snap_placements(arrange(m["arrangement"], g.core, macros, halo, ch, pf.macro_allowed_orients, "bottom", sg).placements,
                         g.core, pf.site_width_um, pf.row_height_um, 0.005)
    errs = errors(check_geometry(g, pf, lef) + check_macro_placement(pl, g.core, macros, halo, ch, pf.macro_allowed_orients,
                                                                     lef, None))
    if errs:
        return None, {"infeasible": [e.message for e in errs[:3]]}
    # centroid of the std-cell region = core minus macro boxes (area-weighted)
    ca = g.core.area
    cx = (g.core.x0 + g.core.x1) / 2 * ca
    cy = (g.core.y0 + g.core.y1) / 2 * ca
    a = ca
    for p in pl:
        b = p.box
        cx -= (b.x0 + b.x1) / 2 * b.area
        cy -= (b.y0 + b.y1) / 2 * b.area
        a -= b.area
    cx, cy = cx / a, cy / a
    wire = 0.0
    for p in pl:
        b = p.box
        side = FLIP_SIDE[p.orient]["bottom"]
        px, py = (b.x0 + b.x1) / 2, (b.y0 if side == "bottom" else b.y1)
        npins = len(lef.macros[p.master].signal_pins())
        wire += npins * (abs(px - cx) + abs(py - cy))
    cost = g.die.area / 1e6 + 0.5 * wire / 1e6
    return cost, {"die_mm2": round(g.die.area / 1e6, 3), "macro_pin_wire_proxy_m": round(wire / 1e6, 3),
                  "cost": round(cost, 4)}


def anneal_candidates(cfg: dict, base: Path) -> list[dict]:
    """Simulated annealing over the configured discrete/continuous space; returns
    the `top_k` distinct best surrogate points as override dicts."""
    from .metrics import synthesis_summary
    from .orfs import synth_context
    from .pipeline import Run
    run = Run(load_run(base, {"id": "anneal_probe"}))
    run.rec["synthesis"] = synthesis_summary(synth_context(run.design, run.platform, run.period), run.design, run.platform)
    ctx = {"macros": run._macro_insts(), "lef": run._lef(), "platform": run.platform,
           "std_area": run.rec["synthesis"]["std_cell_area_um2"]}
    space = cfg["parameters"]
    rng = random.Random(cfg.get("seed", 1))
    base_doc = yaml.safe_load(Path(base).read_text())

    def to_spec(pt):
        d = {"floorplan": dict(base_doc["floorplan"]), "macros": dict(base_doc.get("macros", {}))}
        for k, v in pt.items():
            sect, key = k.split(".", 1)
            d[sect][key] = v
        d["macros"]["placement"] = "manual"
        return d

    def rand_pt():
        out = {}
        for k, s in space.items():
            out[k] = rng.choice(s["choice"]) if "choice" in s else round(rng.uniform(*s["uniform"]), 3)
        return out

    def neighbour(pt):
        q = dict(pt)
        k = rng.choice(list(space))
        s = space[k]
        if "choice" in s:
            q[k] = rng.choice(s["choice"])
        else:
            lo, hi = s["uniform"]
            q[k] = round(min(hi, max(lo, q[k] + rng.gauss(0, (hi - lo) / 6))), 3)
        return q

    cur = rand_pt()
    cur_c, _ = surrogate(to_spec(cur), ctx)
    while cur_c is None:
        cur = rand_pt()
        cur_c, _ = surrogate(to_spec(cur), ctx)
    T0, steps = cfg.get("t0", 0.5), cfg.get("steps", 300)
    seen: dict[str, tuple[float, dict]] = {}
    for i in range(steps):
        T = T0 * (1 - i / steps) + 1e-3
        cand = neighbour(cur)
        c, info = surrogate(to_spec(cand), ctx)
        if c is None:
            continue
        seen[yaml.safe_dump(cand, sort_keys=True)] = (c, cand)
        if c < cur_c or rng.random() < math.exp(-(c - cur_c) / T):
            cur, cur_c = cand, c
    best = sorted(seen.values(), key=lambda t: t[0])
    out, keys = [], set()
    for c, pt in best:
        key = (pt.get("macros.arrangement"), round(pt.get("floorplan.target_util", 0), 2))
        if key in keys:
            continue
        keys.add(key)
        out.append(pt)
        if len(out) >= cfg.get("top_k", 2):
            break
    from .orfs import RESULTS
    log = RESULTS / "sweeps" / cfg["id"] / "anneal_log.yaml"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(yaml.safe_dump({"evaluated": len(seen), "top": [{"cost": c, "point": p} for c, p in best[:10]]}))
    return out


def pareto_front(rows: list[dict], objectives: list[tuple[str, str]]) -> list[str]:
    """rows: dicts with 'run_id' + objective keys; objectives: [(key, 'min'|'max')].
    Rows with any missing objective are excluded (never assumed good)."""
    ok = [r for r in rows if all(r.get(k) is not None for k, _ in objectives)]

    def dominates(a, b):
        better = False
        for k, d in objectives:
            va, vb = (a[k], b[k]) if d == "min" else (-a[k], -b[k])
            if va > vb:
                return False
            if va < vb:
                better = True
        return better
    return [r["run_id"] for r in ok if not any(dominates(o, r) for o in ok if o is not r)]
