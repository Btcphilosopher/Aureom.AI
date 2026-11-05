"""Engineering-report figures (matplotlib, PNG + SVG).

Every figure states its provenance in the subtitle or legend; RTL-simulated
points are diamonds, Python-simulated squares, analytical circles, and
theoretical ceilings are lines.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np

from memoryflow.models import area as A
from memoryflow.models.banking import MODES, simulate_spm, stride_streams
from memoryflow.models.dma import dma_path_bw
from memoryflow.models.hardware import EXTMEM_PRESETS, SystemConfig
from memoryflow.models.roofline import Roofline
from memoryflow.models.workloads import Workload
from memoryflow.report import style as S
from memoryflow.verify.golden import bank_map


def _sub(ax, text: str) -> None:
    ax.text(0, 1.015, text, transform=ax.transAxes, fontsize=7.5, color=S.MUTED, va="bottom")


def roofline_chart(cfgs: Sequence[tuple[str, SystemConfig]], suite: Sequence[Workload],
                   measured: Sequence[dict], out: str) -> list[str]:
    S.apply()
    fig, axes = plt.subplots(1, len(cfgs), figsize=(6.2 * len(cfgs), 4.6), sharey=True)
    axes = np.atleast_1d(axes)
    ai = np.logspace(-2, 3.3, 300)
    for ax, (title, cfg) in zip(axes, cfgs):
        r = Roofline(cfg)
        bw = r.effective_dram_bw()
        for unit, col in (("tensor", S.SERIES[0]), ("vector", S.SERIES[1])):
            pk = r.peak(unit)
            ax.plot(ai, np.minimum(pk, ai * bw) / 1e9, color=col, lw=2, label=f"{unit} roof")
            ax.text(ai[-1], pk / 1e9 * 1.08, f"{unit} peak {pk / 1e9:.0f} Gop/s", ha="right",
                    color=S.TEXT2, fontsize=7.5)
        for name, ls in (("DRAM sustained", "--"), ("DMA path", ":"), ("SPM->engine", "-.")):
            v = r.ceilings[name][0]
            ax.plot(ai, ai * v / 1e9, color=S.NEUTRAL, lw=1.1, ls=ls)
        offs = [(6, -12), (-76, -13), (6, -24), (-76, -26)]
        k = 0
        for i, w in enumerate(suite):
            pt = r.evaluate(w)
            col = S.SERIES[0] if w.unit == "tensor" else S.SERIES[1]
            ax.scatter(pt.ai, pt.perf / 1e9, s=42, color=col, edgecolor=S.SURFACE, linewidth=1.6, zorder=5)
            if w.unit == "tensor":
                lab = w.name.replace(" int8", "").replace("GEMM ", "G ").replace("CONV ", "C ")
                ax.annotate(lab, (pt.ai, pt.perf / 1e9), xytext=offs[k % 4], textcoords="offset points",
                            fontsize=6.2, color=S.TEXT2)
                k += 1
            elif i % 2 == 0:
                ax.annotate(w.name.split(" ")[0], (pt.ai, pt.perf / 1e9), xytext=(5, -10),
                            textcoords="offset points", fontsize=6.5, color=S.TEXT2)
        for m in measured:
            if m.get("config") != title:
                continue
            ax.scatter(m["ai"], m["perf"] / 1e9, marker="D", s=46, color=S.SERIES[2],
                       edgecolor=S.SURFACE, linewidth=1.6, zorder=6)
            ax.annotate(m["name"] + "\nSPM-resident: AI vs SPM bytes", (m["ai"], m["perf"] / 1e9),
                        xytext=(-150, 6) if m["unit"] == "tensor" else (8, 6),
                        textcoords="offset points", fontsize=6.3, color=S.TEXT2)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlim(0.01, 2000)
        ax.set_ylim(0.05, 600)
        ax.set_xlabel("arithmetic intensity  (op / DRAM byte)")
        ax.set_title(title, pad=26)
        _sub(ax, cfg.label() + f"\nDRAM {r.ceilings['DRAM sustained'][0] / 1e9:.1f} GB/s  |  DMA path "
                 f"{r.ceilings['DMA path'][0] / 1e9:.1f} GB/s  |  SPM->engine {r.ceilings['SPM->engine'][0] / 1e9:.1f} GB/s")
    axes[0].set_ylabel("attainable performance  (Gop/s)")
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=S.SERIES[0], lw=2, label="tensor roof / workloads"),
               Line2D([], [], color=S.SERIES[1], lw=2, label="vector roof / workloads"),
               Line2D([], [], color=S.NEUTRAL, lw=1.2, ls="--", label="DRAM sustained (analytical)"),
               Line2D([], [], color=S.NEUTRAL, lw=1.2, ls=":", label="DMA path (analytical, RTL-validated)"),
               Line2D([], [], color=S.NEUTRAL, lw=1.2, ls="-.", label="SPM->engine"),
               Line2D([], [], marker="D", color=S.SERIES[2], lw=0, label="RTL simulation")]
    fig.legend(handles=handles, loc="lower center", ncol=6, bbox_to_anchor=(0.5, -0.07))
    fig.suptitle("Roofline: achievable <= min(peak compute, AI x sustained bandwidth)", x=0.01, y=1.04, ha="left",
                 color=S.GOLD, fontsize=12, fontweight="bold")
    return S.save(fig, out)


def banking_map_chart(out: str, nbanks: int = 4, rows: int = 8, cols: int = 16) -> list[str]:
    S.apply()
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.4))
    cmap = plt.matplotlib.colors.ListedColormap(S.SERIES[:nbanks])
    for ax, mode in zip(axes, ("modulo", "xor", "block")):
        bd = (rows * cols) // nbanks
        grid = np.zeros((rows, cols), dtype=int)
        for w in range(rows * cols):
            grid[w // cols, w % cols] = bank_map(w, nbanks, bd, MODES[mode])[0]
        ax.imshow(grid, cmap=cmap, vmin=-0.5, vmax=nbanks - 0.5, aspect="auto")
        for y in range(rows):
            for x in range(cols):
                ax.text(x, y, str(grid[y, x]), ha="center", va="center", fontsize=6.5, color=S.SURFACE,
                        fontweight="bold")
        ax.set_xticks(range(0, cols, 4))
        ax.set_yticks(range(rows))
        ax.set_yticklabels([f"{r * cols}" for r in range(rows)])
        ax.grid(False)
        ax.set_title(f"{mode} interleave")
        ax.set_xlabel("word offset in row")
        for sp in ax.spines.values():
            sp.set_visible(False)
    axes[0].set_ylabel("first word of row")
    fig.suptitle(f"Banking maps: word address -> bank ({nbanks} banks; cell = bank id)", x=0.01, y=1.06, ha="left",
                 color=S.GOLD, fontsize=12, fontweight="bold")
    return S.save(fig, out)


def stride_conflict_chart(out: str, strides=(1, 2, 4, 8, 16, 32), banks=(4, 8, 16)) -> list[str]:
    S.apply()
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.2), sharey=True)
    seq = plt.matplotlib.colors.LinearSegmentedColormap.from_list(
        "b", ["#0d366b", "#1c5cab", "#3987e5", "#86b6ef", "#cde2fb"])
    for ax, mode in zip(axes, ("modulo", "xor", "block")):
        mat = np.zeros((len(banks), len(strides)))
        for i, nb in enumerate(banks):
            for j, s in enumerate(strides):
                mat[i, j] = simulate_spm(stride_streams(3, 256, s, nb * 256), nb, 256, mode).throughput
        ax.imshow(mat, cmap=seq, vmin=0, vmax=3, aspect="auto")
        for i in range(len(banks)):
            for j in range(len(strides)):
                ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center", fontsize=7.5,
                        color=S.SURFACE if mat[i, j] > 1.8 else S.TEXT)
        ax.set_xticks(range(len(strides)))
        ax.set_xticklabels([str(s) for s in strides])
        ax.set_yticks(range(len(banks)))
        ax.set_yticklabels([f"{b} banks" for b in banks])
        ax.set_xlabel("stride (words), 3 streaming ports")
        ax.set_title(f"{mode}")
        ax.grid(False)
    fig.suptitle("SPM throughput (requests/cycle, max 3) - cycle model, RTL-calibrated (<1 % error)",
                 x=0.01, y=1.06, ha="left", color=S.GOLD, fontsize=12, fontweight="bold")
    return S.save(fig, out)


def dma_burst_chart(rows: Sequence[dict], out: str, skew: dict | None = None) -> list[str]:
    S.apply()
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    for ax, path, ttl in zip(axes, ("ext2spm", "spm2spm"), ("EXT (latency 20) -> SPM", "SPM -> SPM")):
        rr = [r for r in rows if r["path"] == path]
        b = [r["burst"] for r in rr]
        beats = 512
        for key, lab, mk, col in (("rtl", "RTL simulation", "D", S.SERIES[2]), ("sim", "cycle model (Python)", "s", S.SERIES[0]),
                                  ("analytic", "analytical (Little's law)", "o", S.SERIES[1])):
            y = [beats / r[key] for r in rr]
            ax.plot(b, y, marker=mk, color=col, lw=2 if key == "rtl" else 1.4, label=lab,
                    markeredgecolor=S.SURFACE, markeredgewidth=1.5, zorder=6 if key == "rtl" else 3,
                    markersize=8 if key == "rtl" else 6)
        if skew and path == "spm2spm":
            ys = [beats / skew[bb] for bb in b if bb in skew]
            ax.plot([bb for bb in b if bb in skew], ys, marker="D", color=S.SERIES[4], lw=1.4, ls="--",
                    label="RTL, dst skewed +1 beat", markeredgecolor=S.SURFACE)
        ax.set_xscale("log", base=2)
        ax.set_xticks(b)
        ax.set_xticklabels([str(x) for x in b])
        ax.set_xlabel("DMA burst length (beats)")
        ax.set_ylim(0, 1.05)
        ax.set_title(ttl)
        _sub(ax, "4 KiB copy, 64-bit beats, 16-deep data FIFO, 4-deep descriptor FIFO")
    axes[0].set_ylabel("throughput (beats / cycle)")
    axes[1].legend(loc="lower right")
    fig.suptitle("DMA bandwidth vs burst length", x=0.01, y=1.07, ha="left", color=S.GOLD, fontsize=12, fontweight="bold")
    return S.save(fig, out)


def dma_outstanding_chart(out: str, clock_hz: float = 500e6) -> list[str]:
    S.apply()
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    depths = [8, 16, 32, 64, 128, 256]
    i = 0
    for em_name in ("DDR4-3200 x32", "LPDDR4X-4266 x32"):
        em = EXTMEM_PRESETS[em_name]
        for width in (64, 128):
            bw = [min(em.sustained_bw().value, dma_path_bw(width // 8, clock_hz, em.latency_cycles(clock_hz), 16, d, 8)) / 1e9
                  for d in depths]
            ax.plot(depths, bw, marker="o", color=S.SERIES[i], label=f"{em_name}, {width}-bit beat",
                    markeredgecolor=S.SURFACE, markeredgewidth=1.5)
            i += 1
        ax.axhline(em.sustained_bw().value / 1e9, color=S.NEUTRAL, lw=1, ls="--")
        ax.text(depths[0], em.sustained_bw().value / 1e9 * 1.03, f"{em_name} sustained", fontsize=7, color=S.MUTED)
    ax.set_xscale("log", base=2)
    ax.set_xticks(depths)
    ax.set_xticklabels([str(d) for d in depths])
    ax.set_xlabel("DMA outstanding read beats (data-FIFO depth)")
    ax.set_ylabel("effective DRAM bandwidth (GB/s)")
    ax.legend(loc="lower right")
    ax.set_title("Bandwidth-delay product: outstanding beats needed to reach DRAM bandwidth")
    _sub(ax, f"analytical (Little's law, validated vs RTL burst sweep); {clock_hz / 1e6:.0f} MHz, 90-110 ns DRAM latency")
    return S.save(fig, out)


def tensor_util_chart(rtl: dict[str, float], model: dict[str, float], out: str) -> list[str]:
    S.apply()
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    cases = [("K=8, single acc. buffer", "tensor_dbuf0_k8_mac_util"), ("K=8, double-buffered", "tensor_dbuf1_k8_mac_util"),
             ("K=32, single acc. buffer", "tensor_dbuf0_k32_mac_util"), ("K=32, double-buffered", "tensor_dbuf1_k32_mac_util")]
    y = np.arange(len(cases))
    h = 0.36
    r = [rtl.get(k, 0) * 100 for _, k in cases]
    m = [model.get(k, 0) * 100 for _, k in cases]
    ax.barh(y - h / 2 - 0.01, r, h, color=S.SERIES[2], label="RTL simulation", edgecolor=S.SURFACE, linewidth=2)
    ax.barh(y + h / 2 + 0.01, m, h, color=S.SERIES[0], label="analytical model", edgecolor=S.SURFACE, linewidth=2)
    for yi, v in zip(y, r):
        ax.text(v + 1, yi - h / 2, f"{v:.1f} %", va="center", fontsize=7.5, color=S.TEXT2)
    ax.set_yticks(y)
    ax.set_yticklabels([c for c, _ in cases])
    ax.set_xlim(0, 105)
    ax.set_xlabel("MAC-array utilisation, 8 back-to-back tiles (%)")
    ax.invert_yaxis()
    ax.legend(loc="lower right")
    ax.set_title("Tensor accumulation double-buffering")
    _sub(ax, "8x8 int8 outer-product array; drain = 32 beats per tile")
    return S.save(fig, out)


def utilisation_chart(points: Sequence, title: str, out: str) -> list[str]:
    S.apply()
    fig, ax = plt.subplots(figsize=(8.5, 0.34 * len(points) + 1.2))
    names = [p.name for p in points]
    u = [p.utilisation * 100 for p in points]
    cols = [S.SERIES[0] if p.unit == "tensor" else S.SERIES[1] for p in points]
    y = np.arange(len(points))
    ax.barh(y, u, 0.62, color=cols, edgecolor=S.SURFACE, linewidth=2)
    for yi, p, v in zip(y, points, u):
        ax.text(v + 1, yi, f"{v:.0f} %  ({p.bound}-bound)", va="center", fontsize=7.5, color=S.TEXT2)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=7.5)
    ax.set_xlim(0, 125)
    ax.invert_yaxis()
    ax.set_xlabel("utilisation of the executing engine's peak (%)")
    ax.set_title(title)
    _sub(ax, "analytical roofline; blue = tensor array, orange = vector unit")
    return S.save(fig, out)


def calibration_chart(rows: Sequence[dict], out: str) -> list[str]:
    S.apply()
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    tests = sorted({r["test"] for r in rows})
    for i, t in enumerate(tests):
        rr = [r for r in rows if r["test"] == t]
        ax.scatter([r["rtl"] for r in rr], [r["model"] for r in rr], s=44, color=S.SERIES[i], label=t,
                   edgecolor=S.SURFACE, linewidth=1.5, zorder=3)
    ax.plot([0, 3.1], [0, 3.1], color=S.NEUTRAL, lw=1, ls="--")
    ax.set_xlabel("RTL simulation (requests / cycle)")
    ax.set_ylabel("Python cycle model (requests / cycle)")
    ax.set_xlim(0, 3.1)
    ax.set_ylim(0, 3.1)
    ax.legend(loc="upper left")
    errs = [abs(r["error_pct"]) for r in rows]
    ax.set_title("SPM banking model vs RTL")
    _sub(ax, f"{len(rows)} cases, max |error| {max(errs):.2f} %")
    return S.save(fig, out)


def sweeps_chart(oat: dict, base_values: dict, out: str) -> list[str]:
    S.apply()
    names = list(oat)
    n = len(names)
    cols = 3
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(12.5, 3.0 * rows))
    axes = axes.ravel()
    labels = {"scratchpad": ("SPM KiB", [128, 256, 512, 1024]), "banks": ("banks", [2, 4, 8, 16]),
              "bus_width": ("bank / DMA width (bits)", [32, 64, 128, 256]),
              "dma_burst": ("DMA burst (beats)", [1, 2, 4, 8, 16]),
              "dma_outstanding": ("DMA outstanding beats", [16, 32, 64, 128, 256]),
              "vector_lanes": ("vector lanes", [2, 4, 8, 16, 32]),
              "tensor_array": ("tensor array", ["4x4", "8x8", "16x16", "32x32"]),
              "extmem": ("external memory", None), "cpu_cores": ("CPU cores", [1, 2, 4])}
    for ax, nm in zip(axes, names):
        pts = oat[nm]
        xl, xs = labels.get(nm, (nm, None))
        xs = xs or [p.cfg["extmem"].split(" ")[0].replace("-", "\n") for p in pts]
        x = np.arange(len(pts))
        dense = [p.dense_gops for p in pts]
        stream = [p.stream_gops for p in pts]
        ax.plot(x, dense, marker="o", color=S.SERIES[0], label="dense (tensor) geomean", markeredgecolor=S.SURFACE)
        ax.plot(x, stream, marker="o", color=S.SERIES[1], label="streaming (vector) geomean", markeredgecolor=S.SURFACE)
        for xi, p in zip(x, pts):
            if not p.feasible:
                ax.scatter([xi], [p.dense_gops], marker="x", color=S.MUTED, s=30, zorder=6)
        ax.set_yscale("log")
        ax.set_xticks(x)
        ax.set_xticklabels([str(v) for v in xs], fontsize=7)
        ax.set_xlabel(xl)
        ax.set_title(nm.replace("_", " "))
    for ax in axes[n:]:
        ax.axis("off")
    axes[0].set_ylabel("Gop/s")
    axes[0].legend(loc="lower right", fontsize=7)
    fig.suptitle("One-at-a-time sweeps around the baseline (256 KiB, 8 banks, 64 b, 8x8, 4 lanes, burst 16, "
                 "FIFO 16, DDR4-3200 x32; x = infeasible at 40 nm)",
                 x=0.01, ha="left", color=S.GOLD, fontsize=12, fontweight="bold")
    fig.tight_layout()
    return S.save(fig, out)


def pareto_chart(points: Sequence, front: Sequence, rec, out: str) -> list[str]:
    S.apply()
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    inf = [p for p in points if not p.feasible]
    feas = [p for p in points if p.feasible]
    ax.scatter([p.total_area_mm2 for p in inf], [p.geomean_gops for p in inf], s=8, color=S.NEUTRAL, alpha=0.5,
               label=f"infeasible at 40 nm ({len(inf)})", linewidth=0)
    ax.scatter([p.total_area_mm2 for p in feas], [p.geomean_gops for p in feas], s=10, color=S.SERIES[0], alpha=0.6,
               label=f"feasible ({len(feas)})", linewidth=0)
    ax.plot([p.total_area_mm2 for p in front], [p.geomean_gops for p in front], color=S.SERIES[1], lw=2,
            label="Pareto front (feasible)")
    ax.scatter([rec.total_area_mm2], [rec.geomean_gops], s=140, facecolor="none", edgecolor=S.GOLD, linewidth=2.2,
               zorder=8)
    ax.annotate("recommended\n" + rec.label, (rec.total_area_mm2, rec.geomean_gops), xytext=(20, -38),
                textcoords="offset points", fontsize=7.5, color=S.GOLD,
                arrowprops=dict(arrowstyle="-", color=S.GOLD, lw=1))
    ax.set_xlabel("core area estimate (mm2, 40 nm: logic + SRAM macros + DRAM PHY)")
    ax.set_ylabel("suite geomean (Gop/s)")
    ax.set_yscale("log")
    ax.legend(loc="lower right")
    ax.set_title("Design space: performance vs area")
    _sub(ax, "analytical; each point = one memory/compute configuration")
    return S.save(fig, out)


def area_breakdown_chart(tiers: Sequence[tuple[str, object]], out: str) -> list[str]:
    S.apply()
    keys = ["spm_sram", "dram_phy", "tensor", "vector", "dma", "spm_logic", "cpu", "cpu_l1"]
    names = {"spm_sram": "SPM SRAM macros", "dram_phy": "DRAM PHY+ctrl IP", "tensor": "tensor array",
             "vector": "vector unit", "dma": "DMA", "spm_logic": "SPM logic (ECC, arb.)", "cpu": "CPU core(s)",
             "cpu_l1": "CPU L1 SRAM"}
    fig, ax = plt.subplots(figsize=(9, 0.6 * len(tiers) + 1.6))
    for i, (lab, p) in enumerate(tiers):
        left = 0.0
        for j, k in enumerate(keys):
            v = p.area_mm2.get(k, 0.0)
            ax.barh(i, v, 0.55, left=left, color=S.SERIES[j], edgecolor=S.SURFACE, linewidth=2,
                    label=names[k] if i == 0 else None)
            left += v
        ax.text(left + 0.08, i, f"{left:.2f} mm2", va="center", fontsize=8, color=S.TEXT2)
    ax.set_yticks(range(len(tiers)))
    ax.set_yticklabels([t for t, _ in tiers])
    ax.invert_yaxis()
    ax.set_xlabel("area (mm2, 40 nm, analytical)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=4, fontsize=7.5)
    ax.set_title("Area breakdown of the recommended prototype tiers")
    _sub(ax, "logic from Yosys NAND2-equivalents x library area / 0.70 utilisation; SRAM from macro tiling plan")
    return S.save(fig, out)


def sram_area_chart(out: str) -> list[str]:
    S.apply()
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    caps = [64, 128, 256, 512, 1024]
    for i, node in enumerate((65, 40, 28)):
        ys = [A.spm_area_mm2(c * 1024, 8, 64, 72, node)[0] for c in caps]
        ax.plot(caps, ys, marker="o", color=S.SERIES[i], label=f"{node} nm, 8 banks, SECDED 72/64",
                markeredgecolor=S.SURFACE)
        ax.text(caps[-1] * 1.04, ys[-1], f"{ys[-1]:.2f}", fontsize=7.5, color=S.TEXT2, va="center")
    ax.set_xscale("log", base=2)
    ax.set_xticks(caps)
    ax.set_xticklabels([f"{c}K" for c in caps])
    ax.set_xlabel("scratchpad capacity (KiB)")
    ax.set_ylabel("SRAM macro area (mm2)")
    ax.legend(loc="upper left")
    ax.set_title("SRAM area estimation interface (analytical model)")
    _sub(ax, "indicative HD 6T bitcell areas; replace with memory-compiler CSV via CompilerTableAreaModel")
    return S.save(fig, out)
