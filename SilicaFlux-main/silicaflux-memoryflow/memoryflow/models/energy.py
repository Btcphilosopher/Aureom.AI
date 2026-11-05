"""Energy-per-byte and memory-power model (ANALYTICAL).

Baseline values are the widely used 45 nm figures (M. Horowitz, "Computing's
energy problem", ISSCC 2014): 8-bit add 0.03 pJ, 8-bit mult 0.2 pJ, 32-bit
add 0.1 pJ, 32-bit mult 3.1 pJ, 64-bit SRAM read 10 pJ (8 KiB) / 20 pJ
(32 KiB) / 100 pJ (1 MiB).  They are scaled to other nodes with an
indicative C*V^2 factor table.  DRAM energy per bit comes from the
ExtMemConfig preset.  Replace with foundry/memory-compiler data for sign-off.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from memoryflow.models.hardware import SystemConfig
from memoryflow.models.workloads import Workload
from memoryflow.provenance import Provenance, Quantity

# dynamic-energy scale factor relative to 45 nm (indicative C*V^2 trend)
NODE_ENERGY_SCALE: dict[int, float] = {180: 6.0, 130: 3.2, 90: 2.0, 65: 1.45, 55: 1.25, 45: 1.0,
                                       40: 0.9, 28: 0.6, 22: 0.5, 16: 0.4, 12: 0.35, 7: 0.25}


def node_scale(node_nm: int) -> float:
    if node_nm in NODE_ENERGY_SCALE:
        return NODE_ENERGY_SCALE[node_nm]
    xs = sorted(NODE_ENERGY_SCALE)
    lo = max(x for x in xs if x <= node_nm) if node_nm >= xs[0] else xs[0]
    hi = min(x for x in xs if x >= node_nm) if node_nm <= xs[-1] else xs[-1]
    if lo == hi:
        return NODE_ENERGY_SCALE[lo]
    f = (node_nm - lo) / (hi - lo)
    return NODE_ENERGY_SCALE[lo] * (1 - f) + NODE_ENERGY_SCALE[hi] * f


def sram_read_pj_per_64b(macro_kib: float, node_nm: int = 45) -> float:
    """64-bit access energy vs macro size: exact fit through (8 KiB, 10 pJ),
    (32 KiB, 20 pJ), (1 MiB, 100 pJ) at 45 nm -> E = 4.628 * KiB^0.4458 - 1.693."""
    e45 = max(4.628 * max(macro_kib, 0.25) ** 0.4458 - 1.693, 1.0)
    return e45 * node_scale(node_nm)


def sram_pj_per_byte(macro_kib: float, node_nm: int = 45) -> float:
    return sram_read_pj_per_64b(macro_kib, node_nm) / 8.0


def mac_pj(bits: int = 8, node_nm: int = 45) -> float:
    """Integer MAC (multiply + accumulate into 4x wider adder)."""
    mult = {8: 0.2, 16: 0.8, 32: 3.1}[bits]
    add = {8: 0.03, 16: 0.05, 32: 0.1}[bits] * 4
    return (mult + add) * node_scale(node_nm)


def interconnect_pj_per_byte_mm(node_nm: int = 45) -> float:
    """On-chip wire energy ~0.1 pJ/bit/mm at 45 nm (indicative)."""
    return 0.8 * node_scale(node_nm)


@dataclass(frozen=True)
class EnergyBreakdown:
    compute_pj: float
    spm_pj: float
    dram_pj: float
    wire_pj: float
    ops: float
    seconds: float

    @property
    def total_pj(self) -> float:
        return self.compute_pj + self.spm_pj + self.dram_pj + self.wire_pj

    @property
    def pj_per_op(self) -> float:
        return self.total_pj / max(self.ops, 1.0)

    @property
    def memory_power_w(self) -> float:
        return (self.spm_pj + self.dram_pj + self.wire_pj) * 1e-12 / max(self.seconds, 1e-12)

    @property
    def total_power_w(self) -> float:
        return self.total_pj * 1e-12 / max(self.seconds, 1e-12)

    def as_quantities(self) -> dict[str, Quantity]:
        a = Provenance.ANALYTICAL
        return {"pJ/op": Quantity(self.pj_per_op, "pJ/op", a),
                "memory power": Quantity(self.memory_power_w, "W", a),
                "total power": Quantity(self.total_power_w, "W", a)}


def workload_energy(w: Workload, cfg: SystemConfig, seconds: float) -> EnergyBreakdown:
    node = cfg.node_nm
    macro_kib = cfg.spm.capacity_bytes / 1024 / cfg.spm.banks
    bits = 8 if w.unit == "tensor" else 16
    compute = (w.ops / 2.0) * mac_pj(bits, node)
    onchip = w.onchip_bytes(cfg)
    dram = w.dram_bytes(cfg)
    # every DRAM byte is written into and read out of the SPM once more
    spm = (onchip + 2 * dram) * sram_pj_per_byte(macro_kib, node)
    side_mm = math.sqrt(max(cfg.spm.capacity_bytes / (256 * 1024), 0.25)) * 1.5
    wire = (onchip + dram) * interconnect_pj_per_byte_mm(node) * side_mm
    dram_pj = dram * 8 * cfg.extmem.pj_per_bit
    return EnergyBreakdown(compute, spm, dram_pj, wire, w.ops, seconds)


def dram_power_at_bw(bytes_per_s: float, pj_per_bit: float) -> Quantity:
    return Quantity(bytes_per_s * 8 * pj_per_bit * 1e-12, "W", Provenance.ANALYTICAL, "BW x pJ/bit")
