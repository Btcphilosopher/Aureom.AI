"""Design-space exploration of SilicaFlux memory configurations.

Every evaluated point is ANALYTICAL (roofline + tiling + area + energy
models), with the underlying ceilings validated against RTL simulation where
the RTL exists (SPM banking, DMA Little's-law behaviour, tensor-array tile
timing -- see the calibration tables).  Area budgets and the definition of
a "modest mature-node ASIC" are explicit, overridable assumptions.
"""
from __future__ import annotations

import functools
import itertools
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Iterable, Sequence

from memoryflow.models import area as A
from memoryflow.models.energy import workload_energy
from memoryflow.models.hardware import (EXTMEM_PRESETS, ComputeConfig, DmaConfig, ExtMemConfig,
                                        ScratchpadConfig, SystemConfig)
from memoryflow.models.roofline import Roofline
from memoryflow.models.workloads import Workload, default_suite
from memoryflow.provenance import Provenance

KIB = 1024


@dataclass(frozen=True)
class Budget:
    """Assumed envelope of the first-silicon SilicaFlux-V prototype."""

    node_nm: int = 40
    clock_hz: float = 500e6
    max_core_area_mm2: float = 12.0        # logic + SRAM + DRAM PHY, excluding pad ring
    max_power_w: float = 1.5
    require_mature_dram: bool = True
    min_cpu_cores: int = 1


@dataclass
class DesignPoint:
    label: str
    cfg: dict
    perf: dict[str, float]               # workload -> op/s
    bound: dict[str, str]
    util: dict[str, float]
    geomean_gops: float
    dense_gops: float                    # geomean over tensor workloads
    stream_gops: float                   # geomean over vector/memory workloads
    area_mm2: dict[str, float]
    total_area_mm2: float
    power_w: float                       # worst-case workload power
    pj_per_op: float                     # suite average
    dma_bw_gbs: float
    dram_bw_gbs: float
    feasible: bool
    reasons: list[str] = field(default_factory=list)
    provenance: str = Provenance.ANALYTICAL.value

    @property
    def perf_per_mm2(self) -> float:
        return self.geomean_gops / self.total_area_mm2

    def to_row(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if k not in ("perf", "bound", "util", "cfg", "area_mm2")}
        d.update({f"area_{k}": v for k, v in self.area_mm2.items()})
        d["perf_per_mm2"] = self.perf_per_mm2
        d.update({f"cfg_{k}": v for k, v in self.cfg.items()})
        return d


def _gm(vals: Iterable[float]) -> float:
    v = [max(x, 1e-30) for x in vals]
    return math.exp(sum(math.log(x) for x in v) / len(v)) if v else 0.0


def load_synth_ge(path: Path | None) -> dict[str, float] | None:
    """Replace the reference gate counts with this run's Yosys results."""
    if not path or not Path(path).exists():
        return None
    data = {d["top"]: d for d in json.loads(Path(path).read_text()) if d.get("ok")}
    ref = dict(A.REF_GE)
    m = {"syn_tensor_8x8": "tensor_8x8", "syn_vec4x16": "vec_4x16", "syn_dma": "dma_4ch",
         "syn_spm_256k": "spm_ctrl_8b", "syn_router2": "router", "syn_ecc64": "ecc64"}
    for top, key in m.items():
        if top in data:
            ref[key] = data[top]["total_ge"]
    return ref


def area_breakdown(cfg: SystemConfig, ref_ge: dict[str, float] | None = None) -> dict[str, float]:
    c, s, node = cfg.compute, cfg.spm, cfg.node_nm
    spm, _ = A.spm_area_mm2(s.capacity_bytes, s.banks, s.bank_width_bits, s.stored_bits_per_word(), node)
    ge = A.scaled_logic_ge(c.tensor_rows, c.tensor_cols, c.vec_lanes, s.banks, s.bank_width_bits,
                           cfg.dma.channels, ref_ge, c.cpu_cores)
    # DMA data FIFOs beyond 16 beats are SRAM/register-file, cost ~ flops
    extra_fifo_bits = max(cfg.dma.dfifo_depth - 16, 0) * s.bank_width_bits * cfg.dma.engines
    ge["dma"] += extra_fifo_bits * 6.5
    l1 = c.cpu_cores * A.spm_area_mm2(32 * KIB, 2, 64, 72, node)[0]       # 16 KiB I + 16 KiB D per core
    out = {k: A.logic_area_mm2(v, node) for k, v in ge.items()}
    out["spm_sram"] = spm
    out["cpu_l1"] = l1
    out["dram_phy"] = cfg.extmem.phy_area_mm2      # hard IP, quoted at its own node
    return out


@functools.lru_cache(maxsize=None)
def _eval_cached(cfg: SystemConfig, suite_key: tuple, ref_key: tuple | None) -> tuple:
    suite = _SUITES[suite_key]
    ref = dict(ref_key) if ref_key else None
    roof = Roofline(cfg)
    perf, bound, util, energy_pj, ops, worst_p = {}, {}, {}, 0.0, 0.0, 0.0
    for w in suite:
        pt = roof.evaluate(w)
        perf[w.name], bound[w.name], util[w.name] = pt.perf, pt.bound, pt.utilisation
        sec = w.ops / pt.perf
        e = workload_energy(w, cfg, sec)
        energy_pj += e.total_pj
        ops += w.ops
        worst_p = max(worst_p, e.total_power_w)
    return perf, bound, util, energy_pj / ops, worst_p, roof.ceilings["DMA path"][0], \
        roof.ceilings["DRAM sustained"][0], area_breakdown(cfg, ref)


_SUITES: dict[tuple, list[Workload]] = {}


def evaluate(cfg: SystemConfig, suite: Sequence[Workload] | None = None, budget: Budget | None = None,
             ref_ge: dict[str, float] | None = None) -> DesignPoint:
    suite = list(suite or default_suite())
    key = tuple(w.name for w in suite)
    _SUITES.setdefault(key, suite)
    budget = budget or Budget()
    perf, bound, util, pj_op, power, dma_bw, dram_bw, area = _eval_cached(
        cfg, key, tuple(sorted(ref_ge.items())) if ref_ge else None)
    leak = 0.10 * power                              # indicative static share at 40 nm LP
    power_total = power + leak
    total_area = sum(area.values())
    dense = [perf[w.name] for w in suite if w.unit == "tensor"]
    stream = [perf[w.name] for w in suite if w.unit != "tensor"]
    reasons = []
    if total_area > budget.max_core_area_mm2:
        reasons.append(f"area {total_area:.1f} > {budget.max_core_area_mm2} mm2")
    if power_total > budget.max_power_w:
        reasons.append(f"power {power_total:.2f} > {budget.max_power_w} W")
    if budget.require_mature_dram and not cfg.extmem.available_at(cfg.node_nm):
        reasons.append(f"{cfg.extmem.kind} PHY not assumed available at {cfg.node_nm} nm "
                       f"(needs <= {cfg.extmem.max_node_nm} nm)")
    c = cfg.compute
    cfgd = {"spm_kib": cfg.spm.capacity_bytes // KIB, "banks": cfg.spm.banks, "width": cfg.spm.bank_width_bits,
            "burst": cfg.dma.burst_beats, "dfifo": cfg.dma.dfifo_depth, "lanes": c.vec_lanes,
            "tensor": f"{c.tensor_rows}x{c.tensor_cols}", "cores": c.cpu_cores, "extmem": cfg.extmem.name,
            "node": cfg.node_nm, "clock_mhz": c.clock_hz / 1e6}
    return DesignPoint(cfg.label(), cfgd, perf, bound, util, _gm(perf.values()) / 1e9,
                       _gm(dense) / 1e9 if dense else 0.0, _gm(stream) / 1e9 if stream else 0.0,
                       area, total_area, power_total, pj_op, dma_bw / 1e9, dram_bw / 1e9,
                       not reasons, reasons)


def baseline(budget: Budget | None = None) -> SystemConfig:
    b = budget or Budget()
    return SystemConfig(ComputeConfig(clock_hz=b.clock_hz), ScratchpadConfig(), DmaConfig(),
                        EXTMEM_PRESETS["DDR4-3200 x32"], b.node_nm)


def mk(base: SystemConfig, spm_kib: int | None = None, banks: int | None = None, width: int | None = None,
       burst: int | None = None, dfifo: int | None = None, lanes: int | None = None,
       tensor: tuple[int, int] | None = None, extmem: str | None = None, cores: int | None = None) -> SystemConfig:
    s, c, d = base.spm, base.compute, base.dma
    if spm_kib or banks or width:
        s = replace(s, capacity_bytes=(spm_kib or s.capacity_bytes // KIB) * KIB, banks=banks or s.banks,
                    bank_width_bits=width or s.bank_width_bits)
    if burst or dfifo or width:
        d = replace(d, burst_beats=burst or d.burst_beats, dfifo_depth=dfifo or d.dfifo_depth,
                    beat_bytes=(width or s.bank_width_bits) // 8)
    if lanes or tensor or cores:
        c = replace(c, vec_lanes=lanes or c.vec_lanes, tensor_rows=(tensor or (c.tensor_rows,))[0],
                    tensor_cols=(tensor or (0, c.tensor_cols))[1], cpu_cores=cores or c.cpu_cores)
    em = EXTMEM_PRESETS[extmem] if extmem else base.extmem
    return replace(base, spm=s, dma=d, compute=c, extmem=em)


SWEEPS: dict[str, dict] = {
    "scratchpad": {"spm_kib": [128, 256, 512, 1024]},
    "banks": {"banks": [2, 4, 8, 16]},
    "bus_width": {"width": [32, 64, 128, 256]},
    "dma_burst": {"burst": [1, 2, 4, 8, 16]},
    "dma_outstanding": {"dfifo": [16, 32, 64, 128, 256]},
    "vector_lanes": {"lanes": [2, 4, 8, 16, 32]},      # (one-at-a-time: datapath width not co-scaled)
    "tensor_array": {"tensor": [(4, 4), (8, 8), (16, 16), (32, 32)]},
    "extmem": {"extmem": list(EXTMEM_PRESETS)},
    "cpu_cores": {"cores": [1, 2, 4]},
}


def one_at_a_time(base: SystemConfig | None = None, suite: Sequence[Workload] | None = None,
                  budget: Budget | None = None, ref_ge: dict | None = None) -> dict[str, list[DesignPoint]]:
    base = base or baseline(budget)
    out = {}
    for name, sweep in SWEEPS.items():
        (k, vals), = sweep.items()
        out[name] = [evaluate(mk(base, **{k: v}), suite, budget, ref_ge) for v in vals]
    return out


def joint_grid(base: SystemConfig | None = None, suite: Sequence[Workload] | None = None,
               budget: Budget | None = None, ref_ge: dict | None = None,
               spm_kib: Sequence[int] = (128, 256, 512, 1024), banks: Sequence[int] = (4, 8, 16),
               width: Sequence[int] = (64, 128), dfifo: Sequence[int] = (16, 64, 128),
               lanes: Sequence[int] = (4, 8, 16),
               tensor: Sequence[tuple[int, int]] = ((4, 4), (8, 8), (16, 16)),
               extmem: Sequence[str] = ("DDR3-1600 x16", "DDR4-2400 x16", "DDR4-3200 x32",
                                        "LPDDR4X-4266 x32", "HBM2E 1 stack"),
               burst: Sequence[int] = (16,)) -> list[DesignPoint]:
    base = base or baseline(budget)
    pts = []
    for sk, b, wd, df, ln, tn, em, bu in itertools.product(spm_kib, banks, width, dfifo, lanes, tensor, extmem, burst):
        # implementability with the MemoryFlow RTL: the vector unit's lanes and
        # the tensor array's A-beat (TR x int8) are carried by one DMA beat
        if ln * 16 > wd or tn[0] * 8 > wd:
            continue
        pts.append(evaluate(mk(base, sk, b, wd, bu, df, ln, tn, em), suite, budget, ref_ge))
    return pts


def pareto(points: Sequence[DesignPoint]) -> list[DesignPoint]:
    """Non-dominated set on (maximise geomean perf, minimise area)."""
    pts = sorted(points, key=lambda p: (p.total_area_mm2, -p.geomean_gops))
    front, best = [], -1.0
    for p in pts:
        if p.geomean_gops > best:
            front.append(p)
            best = p.geomean_gops
    return front


@dataclass
class Recommendation:
    recommended: DesignPoint
    minimal: DesignPoint
    stretch: DesignPoint
    rationale: list[str]


def recommend(points: Sequence[DesignPoint], target_fraction: float = 0.90,
              minimal_fraction: float = 0.60) -> Recommendation:
    feas = [p for p in points if p.feasible]
    if not feas:
        raise ValueError("no feasible design point under the budget")
    best = max(feas, key=lambda p: p.geomean_gops)
    good = [p for p in feas if p.geomean_gops >= target_fraction * best.geomean_gops]
    rec = min(good, key=lambda p: (p.total_area_mm2, -p.geomean_gops))
    ok_min = [p for p in feas if p.geomean_gops >= minimal_fraction * best.geomean_gops]
    minimal = min(ok_min, key=lambda p: p.total_area_mm2)
    rationale = [
        f"{len(feas)} of {len(points)} evaluated configurations fit the mature-node budget.",
        f"Best feasible suite geomean: {best.geomean_gops:.2f} Gop/s ({best.label}, {best.total_area_mm2:.1f} mm2).",
        f"Recommended = smallest-area point within {int(target_fraction * 100)} % of that: "
        f"{rec.geomean_gops:.2f} Gop/s in {rec.total_area_mm2:.1f} mm2.",
        f"DMA path {rec.dma_bw_gbs:.2f} GB/s vs DRAM sustained {rec.dram_bw_gbs:.2f} GB/s.",
    ]
    return Recommendation(rec, minimal, best, rationale)
