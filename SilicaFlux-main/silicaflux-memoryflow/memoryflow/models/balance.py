"""Compute / bandwidth balance of a design point (ANALYTICAL).

The roofline says *what* bounds each kernel; this module says *what to buy
next* and whether the CPU cores can keep the accelerators fed.

* :func:`kernel_balance`  per workload: every ceiling (compute, DRAM/DMA, SPM
  operand path, tensor result drain), the binding one, and the *headroom* -
  how much faster the kernel would run if only the binding resource were
  unlimited (ratio of the next-lowest ceiling to the binding one).  A
  headroom of 1.0x means two resources bind together (balanced).
* :func:`machine_balance` the suite-level view: bytes/op provisioned at each
  level versus bytes/op demanded, and the share of kernels each resource binds.
* :func:`cpu_orchestration` CPU-core load of programming DMA transfers and
  accelerator commands (the "CPU cores" axis of the balance).  Constants are
  explicit ASSUMPTIONS: an sf_dma transfer costs ~8 APB register accesses plus
  address arithmetic (``CYCLES_PER_DMA``), a tensor tile command ``CYCLES_PER_TILE``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from memoryflow.models.hardware import SystemConfig
from memoryflow.models.roofline import Roofline
from memoryflow.models.workloads import Workload

CYCLES_PER_DMA = 64.0         # ASSUMPTION: 8 APB accesses x ~3 cycles + ~40 instructions
CYCLES_PER_TILE = 24.0        # ASSUMPTION: one tensor tile command + completion check


@dataclass(frozen=True)
class KernelBalance:
    name: str
    unit: str
    ceilings: dict[str, float]       # resource -> op/s it allows
    bound: str
    perf: float
    headroom: float                  # next ceiling / binding ceiling
    next_bound: str
    ai_dram: float
    ai_onchip: float


def kernel_balance(cfg: SystemConfig, w: Workload) -> KernelBalance:
    r = Roofline(cfg)
    u = w.unit
    c = cfg.compute
    ai = w.ops / max(w.dram_bytes(cfg), 1.0)
    ai_on = w.ops / max(w.onchip_bytes(cfg), 1.0)
    ceil = {"compute": r.peak(u),
            "dram": ai * r.ceilings["DRAM sustained"][0],
            "dma": ai * r.effective_dram_bw_for(w),
            "spm": ai_on * r.ceilings["SPM->engine"][0]}
    rb = w.result_bytes(cfg) if u == "tensor" else 0.0
    if rb > 0 and c.tensor_drain_bytes_per_cycle > 0:
        ceil["drain"] = w.ops / rb * c.tensor_drain_bytes_per_cycle * c.clock_hz * cfg.tiles
    if ceil["dma"] >= ceil["dram"] * 0.999:
        ceil.pop("dma")                      # the DMA does not bind below DRAM
    order = sorted(ceil.items(), key=lambda kv: kv[1])
    (b, v), (nb, nv) = order[0], (order[1] if len(order) > 1 else (order[0][0], math.inf))
    return KernelBalance(w.name, u, ceil, b, v, nv / v if v > 0 else math.inf, nb, ai, ai_on)


@dataclass(frozen=True)
class MachineBalance:
    bytes_per_op_provisioned: dict[str, float]   # level -> sustained B/s / peak op/s (all engines)
    bound_share: dict[str, float]                # resource -> fraction of kernels it binds
    geomean_headroom: float
    kernels: list[KernelBalance]


def machine_balance(cfg: SystemConfig, suite: list[Workload]) -> MachineBalance:
    r = Roofline(cfg)
    peak = sum(r.peak(u) for u in ("tensor", "vector", "cpu"))
    prov = {"DRAM sustained": r.ceilings["DRAM sustained"][0] / peak,
            "DMA read path": r.ceilings["DMA path"][0] / peak,
            "DMA write path": r.ceilings["DMA write path"][0] / peak,
            "SPM -> engine": r.ceilings["SPM->engine"][0] / peak}
    ks = [kernel_balance(cfg, w) for w in suite]
    share: dict[str, float] = {}
    for k in ks:
        share[k.bound] = share.get(k.bound, 0.0) + 1.0 / len(ks)
    hr = [min(k.headroom, 1e6) for k in ks]
    gm = math.exp(sum(math.log(h) for h in hr) / len(hr)) if hr else 1.0
    return MachineBalance(prov, share, gm, ks)


@dataclass(frozen=True)
class CpuLoad:
    name: str
    dma_transfers: float
    tensor_tiles: float
    runtime_cycles: float
    cpu_busy: float                 # fraction of the available core cycles
    max_tiles_per_core: float       # accelerator tiles one core can orchestrate at this load


def cpu_orchestration(cfg: SystemConfig, w: Workload) -> CpuLoad:
    """Core cycles needed to program the data movement of one kernel run."""
    r = Roofline(cfg)
    pt = r.evaluate(w)
    cycles = w.ops / pt.perf * cfg.compute.clock_hz
    # double-buffered transfers of half an SPM per tile
    chunk = max(cfg.spm.capacity_bytes / 2, 1.0)
    transfers = w.dram_bytes(cfg) / chunk
    tiles = 0.0
    if w.unit == "tensor":
        c = cfg.compute
        tiles = w.ops / (2.0 * c.tensor_macs_per_cycle * 64)       # one command per 64-step tile
    work = transfers * CYCLES_PER_DMA + tiles * CYCLES_PER_TILE
    busy = work / max(cycles * cfg.compute.cpu_cores, 1.0)
    per_tile = work / max(cycles * cfg.tiles, 1.0)
    return CpuLoad(w.name, transfers, tiles, cycles, busy, (1.0 / per_tile) if per_tile > 0 else math.inf)
