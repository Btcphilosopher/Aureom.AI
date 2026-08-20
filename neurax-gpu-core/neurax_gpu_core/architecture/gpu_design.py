"""
GPUDesign: assembles every subsystem (compute, memory, interconnect) from a
:class:`~utils.config.GPUConfig` into one coherent object graph. This is the
single "blueprint" the rest of the simulation (execution, thermal, power,
silicon, optimisation) operates on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..compute.sm_units import StreamingMultiprocessor
from ..compute.warp_scheduler import SchedulingPolicy
from ..execution.kernel_dispatch import KernelDispatcher
from ..memory.cache_hierarchy import CacheHierarchy
from ..memory.hbm_model import HBMModel
from ..memory.memory_controller import MemoryController
from ..memory.vram_model import BandwidthLimitedMemory, VRAMModel
from ..utils.config import GPUConfig
from .chip_layout import ChipLayout
from .interconnect import Interconnect


class GPUDesign:
    def __init__(self, config: GPUConfig, scheduling_policy: SchedulingPolicy =
                 SchedulingPolicy.GREEDY_THEN_OLDEST):
        self.config = config

        self.sms: List[StreamingMultiprocessor] = [
            StreamingMultiprocessor(sm_id=i, config=config.compute, policy=scheduling_policy)
            for i in range(config.architecture.num_sms)
        ]

        self.cache_hierarchy = CacheHierarchy(
            num_sms=config.architecture.num_sms,
            l1_kb=config.memory.l1_cache_kb_per_sm, l1_line=config.memory.l1_line_bytes,
            l1_assoc=config.memory.l1_associativity, l1_latency=config.memory.l1_latency_cycles,
            l2_kb=config.memory.l2_cache_kb, l2_line=config.memory.l2_line_bytes,
            l2_assoc=config.memory.l2_associativity, l2_latency=config.memory.l2_latency_cycles,
        )

        self.backing_store: BandwidthLimitedMemory
        if config.memory.use_hbm:
            self.backing_store = HBMModel(
                stacks=config.memory.hbm_stacks, channels_per_stack=config.memory.hbm_channels_per_stack,
                bandwidth_per_stack_gbps=config.memory.hbm_bandwidth_per_stack_gbps,
                latency_ns=config.memory.hbm_latency_ns,
            )
        else:
            self.backing_store = VRAMModel(
                capacity_gb=config.memory.vram_capacity_gb, bandwidth_gbps=config.memory.vram_bandwidth_gbps,
                latency_ns=config.memory.vram_latency_ns, num_channels=max(4, config.memory.memory_controllers),
            )

        self.memory_controller = MemoryController(
            cache_hierarchy=self.cache_hierarchy, backing_store=self.backing_store,
            num_memory_controllers=config.memory.memory_controllers,
        )

        self.dispatcher = KernelDispatcher(sms=self.sms, warp_size=config.compute.warp_size)

        self.chip_layout = ChipLayout(
            num_sms=config.architecture.num_sms, sms_per_gpc=config.architecture.sms_per_gpc,
        )
        self.interconnect = Interconnect(
            bandwidth_gbps=config.architecture.interconnect_bandwidth_gbps,
            topology=config.architecture.interconnect_topology,
        )

    # -- derived, purely descriptive quantities (not performance claims) ---

    def total_cuda_cores(self) -> int:
        return self.config.architecture.num_sms * self.config.compute.cuda_cores_per_sm

    def peak_flops_at_clock(self, clock_ghz: float) -> float:
        """Theoretical peak (never achieved in practice) used only as a
        denominator for utilisation %, not reported as achieved throughput."""
        return self.total_cuda_cores() * self.config.compute.fp32_flops_per_core_per_cycle * clock_ghz * 1e9

    def total_l1_capacity_kb(self) -> int:
        return self.config.memory.l1_cache_kb_per_sm * self.config.architecture.num_sms

    def summary(self) -> dict:
        return {
            "name": self.config.name,
            "num_sms": self.config.architecture.num_sms,
            "cuda_cores_total": self.total_cuda_cores(),
            "l1_total_kb": self.total_l1_capacity_kb(),
            "l2_kb": self.config.memory.l2_cache_kb,
            "memory_type": "HBM" if self.config.memory.use_hbm else "GDDR/VRAM",
            "memory_capacity_gb": self.backing_store.capacity_bytes / (1024 ** 3),
            "memory_bandwidth_gbps": self.backing_store.total_bandwidth_gbps,
            "die_sm_area_mm2": self.chip_layout.total_sm_area_mm2(),
        }
