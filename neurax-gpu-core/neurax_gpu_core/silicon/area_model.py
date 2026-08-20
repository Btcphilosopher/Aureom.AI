"""
Die area estimation.

Builds a bottom-up transistor-count estimate from the architecture's actual
configuration (core count, register file, cache sizes, uncore blocks) and
converts it to die area via the configured process node's transistor
density. The per-component transistor coefficients below are engineering
order-of-magnitude estimates (clearly documented as such) used to make area
*respond correctly* to architectural choices -- they are not a claim about
any specific real silicon's exact transistor count.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..utils.config import GPUConfig

# Order-of-magnitude calibration constants (millions of transistors), used
# purely so die area scales sensibly with architectural choices.
MTR_PER_CUDA_CORE = 4.0              # ALU slice + its share of tensor/RT cores, L0 I-cache, control
MTR_SM_FIXED_OVERHEAD = 15.0         # warp schedulers, dispatch units, SFU
MTR_PER_SRAM_BIT = 6.0 / 1_000_000   # classic 6T SRAM cell, expressed in millions/bit
MTR_PER_MEMORY_CONTROLLER = 6.0
MTR_UNCORE_FIXED = 1500.0            # display engine, video codecs, PCIe/NVLink, misc I/O


@dataclass
class AreaBreakdown:
    sm_logic_mm2: float
    register_file_mm2: float
    l1_cache_mm2: float
    l2_cache_mm2: float
    memory_controllers_mm2: float
    uncore_mm2: float
    total_die_mm2: float
    total_transistors_millions: float
    fits_reticle_limit: bool


class AreaModel:
    def __init__(self, config: GPUConfig):
        self.config = config

    def estimate(self) -> AreaBreakdown:
        cfg = self.config
        density = max(1e-6, cfg.silicon.transistor_density_mtr_per_mm2)

        core_mtr = cfg.architecture.num_sms * cfg.compute.cuda_cores_per_sm * MTR_PER_CUDA_CORE
        sm_overhead_mtr = cfg.architecture.num_sms * MTR_SM_FIXED_OVERHEAD
        sm_logic_mtr = core_mtr + sm_overhead_mtr

        reg_bits = cfg.architecture.num_sms * cfg.compute.register_file_size_kb * 1024 * 8
        reg_mtr = reg_bits * MTR_PER_SRAM_BIT

        l1_bits = cfg.architecture.num_sms * cfg.memory.l1_cache_kb_per_sm * 1024 * 8
        l1_mtr = l1_bits * MTR_PER_SRAM_BIT

        l2_bits = cfg.memory.l2_cache_kb * 1024 * 8
        l2_mtr = l2_bits * MTR_PER_SRAM_BIT

        mc_mtr = cfg.memory.memory_controllers * MTR_PER_MEMORY_CONTROLLER

        total_mtr = sm_logic_mtr + reg_mtr + l1_mtr + l2_mtr + mc_mtr + MTR_UNCORE_FIXED

        sm_logic_mm2 = sm_logic_mtr / density
        reg_mm2 = reg_mtr / density
        l1_mm2 = l1_mtr / density
        l2_mm2 = l2_mtr / density
        mc_mm2 = mc_mtr / density
        uncore_mm2 = MTR_UNCORE_FIXED / density
        total_mm2 = sm_logic_mm2 + reg_mm2 + l1_mm2 + l2_mm2 + mc_mm2 + uncore_mm2

        return AreaBreakdown(
            sm_logic_mm2=sm_logic_mm2, register_file_mm2=reg_mm2, l1_cache_mm2=l1_mm2,
            l2_cache_mm2=l2_mm2, memory_controllers_mm2=mc_mm2, uncore_mm2=uncore_mm2,
            total_die_mm2=total_mm2, total_transistors_millions=total_mtr,
            fits_reticle_limit=total_mm2 <= cfg.architecture.die_reticle_limit_mm2,
        )
