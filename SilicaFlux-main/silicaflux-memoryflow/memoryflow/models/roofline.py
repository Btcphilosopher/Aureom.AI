"""Roofline model.

    attainable = min(peak_compute, AI x sustained_bandwidth)

Ceilings are THEORETICAL (pin / datapath rates) or ANALYTICAL (sustained =
peak x efficiency).  Workload points carry their own provenance so RTL-
measured points can be overlaid without being confused with model output.
A hierarchical variant also applies the on-chip SPM -> engine operand ceiling.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from memoryflow.models.dma import dma_path_bw
from memoryflow.models.hardware import SystemConfig
from memoryflow.models.workloads import Workload
from memoryflow.provenance import Provenance


def attainable(ai: float, peak: float, bw: float) -> float:
    """Achievable performance <= min(peak compute, AI x sustained bandwidth)."""
    if ai < 0 or peak < 0 or bw < 0:
        raise ValueError("negative roofline input")
    return min(peak, ai * bw)


def spm_bank_efficiency(banks: int, streams: int = 2) -> float:
    """Fraction of SPM port bandwidth left after bank conflicts between the
    DMA read and write streams (expected distinct banks / streams; validated
    by the cycle-level banking model against RTL)."""
    return banks * (1.0 - (1.0 - 1.0 / banks) ** streams) / streams


def ridge_point(peak: float, bw: float) -> float:
    """Arithmetic intensity (op/B) where the machine becomes compute bound."""
    return peak / bw


@dataclass(frozen=True)
class RooflinePoint:
    name: str
    unit: str
    ai: float
    perf: float                    # op/s
    bound: str                     # compute | dram | spm
    provenance: Provenance
    peak: float
    utilisation: float             # perf / unit peak
    note: str = ""


@dataclass
class Roofline:
    cfg: SystemConfig
    ceilings: dict[str, tuple[float, Provenance]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        em = self.cfg.extmem
        c, d = self.cfg.compute, self.cfg.dma
        dma = dma_path_bw(self.cfg.spm.bank_width_bits // 8, c.clock_hz, em.latency_cycles(c.clock_hz),
                          d.burst_beats, d.dfifo_depth, d.desc_depth)
        self.ceilings = {
            "DRAM peak": (em.peak_bw().value, Provenance.THEORETICAL),
            "DRAM sustained": (em.sustained_bw().value, Provenance.ANALYTICAL),
            "DMA path": (dma, Provenance.ANALYTICAL),
            "SPM->engine": (self.cfg.spm_to_accel_bw().value * spm_bank_efficiency(self.cfg.spm.banks),
                            Provenance.ANALYTICAL),
            "SPM aggregate": (self.cfg.spm_peak_bw().value, Provenance.THEORETICAL),
        }

    def peak(self, unit: str) -> float:
        return self.cfg.compute.peak_ops(unit).value

    def evaluate(self, w: Workload, unit: str | None = None) -> RooflinePoint:
        u = unit or w.unit
        pk = self.peak(u)
        dram_b = w.dram_bytes(self.cfg)
        ai = w.ops / max(dram_b, 1.0)
        bw = self.effective_dram_bw()
        p_dram = ai * bw
        # on-chip ceiling: operand bytes the engine pulls from the SPM path
        ai_onchip = w.ops / max(w.onchip_bytes(self.cfg), 1.0)
        p_spm = ai_onchip * self.ceilings["SPM->engine"][0]
        perf = min(pk, p_dram, p_spm)
        if perf == pk:
            bound = "compute"
        elif perf == p_dram:
            bound = "dma" if self.ceilings["DMA path"][0] < self.ceilings["DRAM sustained"][0] else "dram"
        else:
            bound = "spm"
        return RooflinePoint(w.name, u, ai, perf, bound, Provenance.ANALYTICAL, pk, perf / pk,
                             f"AI_onchip={ai_onchip:.2f}")

    def effective_dram_bw(self) -> float:
        """DRAM bandwidth the engines actually see: min(sustained DRAM, DMA path)."""
        return min(self.ceilings["DRAM sustained"][0], self.ceilings["DMA path"][0])

    def ridge(self, unit: str, ceiling: str = "DRAM sustained") -> float:
        return ridge_point(self.peak(unit), self.ceilings[ceiling][0])


def measured_point(name: str, unit: str, ops: float, bytes_moved: float, cycles: float,
                   clock_hz: float, peak: float, provenance: Provenance = Provenance.RTL_SIMULATION) -> RooflinePoint:
    """Turn a cycle-counted run (RTL or silicon) into a roofline point."""
    perf = ops / (cycles / clock_hz)
    ai = ops / max(bytes_moved, 1.0)
    return RooflinePoint(name, unit, ai, perf, "measured", provenance, peak, perf / peak,
                         f"{ops:.0f} ops in {cycles:.0f} cycles")
