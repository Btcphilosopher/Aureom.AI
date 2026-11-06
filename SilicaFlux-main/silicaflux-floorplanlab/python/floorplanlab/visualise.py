"""Floorplan pictures from exported OpenDB geometry (PNG + SVG).

Everything drawn comes from geometry.json / route outputs written by the
OpenROAD scripts.  Logical groups (CPU, vector, tensor, ...) are shown only as
labelled centroid markers + dashed extent boxes of where the placer put their
cells: the mapped netlist has no block outlines, so none are invented.

Colour roles (dataviz reference palette): sequential blue = std-cell density,
sequential orange = global-route overflow, categorical slots 2/3 = VDD/VSS
straps (with legend), neutral grey = hard macros (identified by label),
status 'critical' red = worst setup path (labelled).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8984"
SURFACE = "#fcfcfb"
SEQ_BLUE = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ_ORANGE = ["#fdeee6", "#f9c9b2", "#f3a07d", "#eb6834", "#c4501f", "#8f3a16"]
VDD_C = "#eb6834"     # categorical slot 2
VSS_C = "#1baf7a"     # categorical slot 3
MACRO_FILL = "#d9d8d3"
CRIT = "#d03b3b"      # status: critical

DENSITY_CMAP = LinearSegmentedColormap.from_list("flp_density", SEQ_BLUE)
OVERFLOW_CMAP = LinearSegmentedColormap.from_list("flp_overflow", SEQ_ORANGE)


def _short(name: str) -> str:
    n = name.replace("\\", "")
    m = re.search(r"g_sram\[(\d+)\].*g_m\[(\d+)\]", n)
    if m:
        return f"SRAM b{m.group(1)}.{m.group(2)}"
    m = re.search(r"u_tile.*g_bank\[(\d+)\]", n)
    if m:
        return f"TSPM {m.group(1)}"
    return n.split("/")[-1]


def parse_congestion_report(path: Path) -> list[tuple[list[float], float]]:
    """(bbox_um, overflow) from the OpenROAD GRT congestion report, if any."""
    if not path.is_file():
        return []
    out = []
    txt = path.read_text(errors="replace")
    for blk in re.split(r"violation type:", txt)[1:]:
        b = re.search(r"bbox = \(\s*([-\d.]+),\s*([-\d.]+)\s*\) - \(\s*([-\d.]+),\s*([-\d.]+)\s*\)", blk)
        if not b:
            continue
        ov = re.search(r"overflow[^\d]*(\d+)", blk, re.I)
        out.append(([float(x) for x in b.groups()], float(ov.group(1)) if ov else 1.0))
    return out


def draw_floorplan(geo: dict, title: str, out_base: Path, *, congestion=None, crit_points=None,
                   cell_xy: dict | None = None, labels: dict | None = None, ax=None, legend=True) -> list[Path]:
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(9, 9), dpi=130)
        fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    die, core = geo["die_um"], geo["core_um"]
    # density heat map (std-cell area / bin area)
    dg = geo.get("density_grid")
    if dg and dg.get("utilisation"):
        import numpy as np
        grid = np.array(dg["utilisation"], dtype=float)
        ox, oy = dg["origin_um"]
        ext = [ox, ox + dg["bins"] * dg["bin_w_um"], oy, oy + dg["bins"] * dg["bin_h_um"]]
        im = ax.imshow(np.clip(grid, 0, 1.0), origin="lower", extent=ext, cmap=DENSITY_CMAP, vmin=0, vmax=1.0,
                       interpolation="nearest", zorder=1)
        if legend:
            cb = plt.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
            cb.set_label("std-cell area / bin area (placement density)", color=INK2, fontsize=8)
            cb.ax.tick_params(labelsize=7, colors=INK2)
            cb.outline.set_visible(False)
    ax.add_patch(Rectangle((die[0], die[1]), die[2] - die[0], die[3] - die[1], fill=False, ec=INK, lw=1.2, zorder=5))
    ax.add_patch(Rectangle((core[0], core[1]), core[2] - core[0], core[3] - core[1], fill=False, ec=INK2, lw=0.8,
                           ls="--", zorder=5))
    # PDN straps (non-followpin special wires) -- thin, VDD/VSS by categorical slots
    seen = set()
    for s in geo.get("pdn_stripes", [])[:6000]:
        b = s["bbox"]
        c = VDD_C if s["net"] in ("VDD", "VPWR") else VSS_C
        lab = None
        if s["net"] not in seen:
            lab = f"{s['net']} strap/ring"
            seen.add(s["net"])
        ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], color=c, lw=0, alpha=0.55, zorder=3, label=lab))
    # macros: neutral fill, identity by label; pin edge marked with a tick line
    for m in geo.get("macros", []):
        b = m["bbox"]
        ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], fc=MACRO_FILL, ec=INK, lw=0.8, zorder=4))
        ax.text((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, f"{_short(m['name'])}\n{m['orient']}", ha="center", va="center",
                fontsize=6.5, color=INK, zorder=6)
        pin_y = b[1] if m["orient"] in ("R0", "MY") else b[3]      # RM_IHPSG13 pins: bottom edge in R0
        ax.plot([b[0], b[2]], [pin_y, pin_y], color=INK, lw=2.2, solid_capstyle="butt", zorder=6)
    # congestion overlay (GRT report)
    if congestion:
        mx = max(o for _, o in congestion) or 1
        for b, o in congestion:
            ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], color=OVERFLOW_CMAP(0.3 + 0.7 * o / mx),
                                   lw=0, alpha=0.8, zorder=7))
    # I/O pins
    for p in geo.get("io_pins", []):
        b = p["bbox"]
        ax.plot([(b[0] + b[2]) / 2], [(b[1] + b[3]) / 2], marker="s", ms=2.5, color=INK, zorder=8)
    cp = geo.get("clock_pin")
    if cp:
        b = cp["bbox"]
        ax.annotate("clk (clock source pin)", ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), xytext=(0, 18),
                    textcoords="offset points", ha="center", fontsize=7, color=INK,
                    arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8), zorder=9)
    # logical groups: centroid + extent (annotation only)
    for g, v in (geo.get("groups") or {}).items():
        if g in ("top", "macro") or v.get("cells", 0) < 50:
            continue
        c = v["centroid_um"]
        ax.plot([c[0]], [c[1]], marker="o", ms=5, mfc=SURFACE, mec=INK, mew=1.0, zorder=9)
        ax.text(c[0], c[1] + 30, (labels or {}).get(g, g), fontsize=7, color=INK, ha="center", zorder=9,
                bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none", alpha=0.8))
    # critical path
    if crit_points and cell_xy:
        xs, ys = [], []
        for pt in crit_points:
            inst = pt["pin"].rsplit("/", 1)[0]
            xy = cell_xy.get(inst)
            if xy:
                xs.append(xy[0])
                ys.append(xy[1])
        if len(xs) >= 2:
            ax.plot(xs, ys, color=CRIT, lw=1.6, zorder=10, label="worst setup path (pre-route)")
            ax.plot(xs[:1], ys[:1], marker="o", ms=6, color=CRIT, zorder=10)
            ax.plot(xs[-1:], ys[-1:], marker="^", ms=7, color=CRIT, zorder=10)
    ax.set_xlim(die[0] - 20, die[2] + 20)
    ax.set_ylim(die[1] - 20, die[3] + 20)
    ax.set_aspect("equal")
    ax.set_title(title, color=INK, fontsize=10, loc="left")
    ax.tick_params(labelsize=7, colors=INK2)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlabel("x (um)", color=INK2, fontsize=8)
    ax.set_ylabel("y (um)", color=INK2, fontsize=8)
    if legend:
        h, l = ax.get_legend_handles_labels()
        h.append(Rectangle((0, 0), 1, 1, fc=MACRO_FILL, ec=INK))
        l.append("SRAM macro (thick edge = signal pins)")
        ax.legend(h, l, loc="upper left", bbox_to_anchor=(0, -0.07), ncol=3, fontsize=7, frameon=False)
    files = []
    if own:
        fig.tight_layout()
        for ext in ("png", "svg"):
            p = out_base.with_suffix(f".{ext}")
            fig.savefig(p, facecolor=SURFACE)
            files.append(p)
        plt.close(fig)
    return files


def load_cell_xy(cells_csv_gz: Path) -> dict:
    import csv
    import gzip
    xy = {}
    if not cells_csv_gz.is_file():
        return xy
    with gzip.open(cells_csv_gz, "rt") as fh:
        for r in csv.DictReader(fh):
            try:
                x, y, w, h = float(r["x_um"]), float(r["y_um"]), float(r["w_um"]), float(r["h_um"])
            except ValueError:
                continue
            xy[r["name"].replace("\\", "").replace(";", ",")] = (x + w / 2, y + h / 2)
    return xy


def side_by_side(geos: list[tuple[str, dict]], out_base: Path, labels: dict | None = None) -> list[Path]:
    n = len(geos)
    cols = min(3, n)
    rows = (n + cols - 1) // cols
    fig, axs = plt.subplots(rows, cols, figsize=(5.2 * cols, 5.4 * rows), dpi=110, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    for i, (title, g) in enumerate(geos):
        draw_floorplan(g, title, out_base, ax=axs[i // cols][i % cols], legend=False, labels=labels)
    for j in range(n, rows * cols):
        axs[j // cols][j % cols].axis("off")
    fig.suptitle("SilicaFlux-V floorplans (OpenROAD placement data; blue = std-cell density 0..1)", color=INK, fontsize=11)
    fig.tight_layout()
    files = []
    for ext in ("png", "svg"):
        p = out_base.with_suffix(f".{ext}")
        fig.savefig(p, facecolor=SURFACE)
        files.append(p)
    plt.close(fig)
    return files


def render_run(run_dir: Path, labels: dict | None = None) -> list[Path]:
    exp = run_dir / "export"
    geo_f = exp / "geometry.json"
    if not geo_f.is_file():
        return []
    geo = json.loads(geo_f.read_text())
    rec = json.loads((run_dir / "run.json").read_text())
    cong = parse_congestion_report(run_dir / "analysis" / "grt_congestion.rpt")
    crit = (rec.get("metrics", {}).get("timing_preroute") or {}).get("critical_path_points") or []
    xy = load_cell_xy(exp / "cells.csv.gz") if crit else None
    t = rec.get("metrics", {}).get("timing_preroute") or {}
    title = (f"{rec['run_id']} -- die {geo['die_um'][2]:.0f} x {geo['die_um'][3]:.0f} um; "
             f"pre-route WNS {t.get('wns_ns')} ns")
    files = draw_floorplan(geo, title, exp / "floorplan", congestion=cong, crit_points=crit, cell_xy=xy, labels=labels)
    return files
