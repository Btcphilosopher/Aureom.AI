"""
Configuration objects for NEURAX GPU CORE.

Every subsystem is parameterised from a small set of dataclasses defined
here. Nothing downstream hard-codes a GPU's performance numbers -- SM
counts, clocks, cache sizes, memory bandwidth and thermal/power envelopes
are all inputs, and the simulation derives behaviour (and therefore
performance) from how those inputs interact at runtime.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class ComputeConfig:
    """Parameters describing the compute core array of a single SM."""

    cuda_cores_per_sm: int = 128
    warp_size: int = 32
    max_warps_per_sm: int = 64
    max_blocks_per_sm: int = 32
    register_file_size_kb: int = 256          # per SM
    registers_per_thread: int = 32
    shared_memory_kb_per_sm: int = 128
    fp32_flops_per_core_per_cycle: int = 2     # FMA = 2 flops
    pipeline_stages: int = 5                   # fetch/decode/issue/exec/writeback


@dataclass
class MemoryConfig:
    """Parameters describing the memory hierarchy."""

    l1_cache_kb_per_sm: int = 128
    l1_line_bytes: int = 128
    l1_associativity: int = 4
    l1_latency_cycles: int = 28

    l2_cache_kb: int = 6144                    # shared, total
    l2_line_bytes: int = 128
    l2_associativity: int = 16
    l2_latency_cycles: int = 210

    vram_capacity_gb: float = 16.0
    vram_bandwidth_gbps: float = 504.0
    vram_latency_ns: float = 350.0

    use_hbm: bool = False
    hbm_stacks: int = 4
    hbm_channels_per_stack: int = 8
    hbm_bandwidth_per_stack_gbps: float = 460.0
    hbm_latency_ns: float = 120.0

    memory_controllers: int = 8


@dataclass
class ArchitectureConfig:
    """Physical / architectural parameters of the die."""

    num_sms: int = 84
    sms_per_gpc: int = 12                      # graphics processing cluster
    interconnect_bandwidth_gbps: float = 2048.0
    interconnect_topology: str = "crossbar"    # crossbar | ring | mesh
    process_node_nm: float = 5.0
    die_reticle_limit_mm2: float = 858.0


@dataclass
class ThermalConfig:
    tdp_watts: float = 320.0
    ambient_temp_c: float = 25.0
    max_safe_temp_c: float = 90.0
    throttle_temp_c: float = 83.0
    critical_temp_c: float = 100.0
    thermal_mass_j_per_c: float = 180.0        # heat capacity of the die+heatsink
    cooling_type: str = "air"                  # air | liquid | vapor_chamber


@dataclass
class PowerConfig:
    tdp_watts: float = 320.0
    voltage_nominal_v: float = 1.05
    base_clock_ghz: float = 1.5
    boost_clock_ghz: float = 2.52
    idle_power_watts: float = 25.0
    dvfs_enabled: bool = True
    min_voltage_v: float = 0.75
    max_voltage_v: float = 1.10


@dataclass
class SiliconConfig:
    process_node_nm: float = 5.0
    wafer_diameter_mm: float = 300.0
    wafer_cost_usd: float = 17000.0
    defect_density_per_cm2: float = 0.09
    transistor_density_mtr_per_mm2: float = 138.2  # million transistors/mm^2


@dataclass
class SimulationConfig:
    timesteps: int = 500
    seconds_per_timestep: float = 1.0e-3       # 1 ms per macro-timestep
    micro_cycles_per_timestep: int = 256       # cycle-accurate sample window
    random_seed: Optional[int] = 42
    enable_ai_optimisation: bool = True
    enable_dashboard: bool = True
    log_level: str = "INFO"


@dataclass
class GPUConfig:
    """Top level configuration bundle passed through the whole system."""

    name: str = "NEURAX-RTX-SIM-1"
    compute: ComputeConfig = field(default_factory=ComputeConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    architecture: ArchitectureConfig = field(default_factory=ArchitectureConfig)
    thermal: ThermalConfig = field(default_factory=ThermalConfig)
    power: PowerConfig = field(default_factory=PowerConfig)
    silicon: SiliconConfig = field(default_factory=SiliconConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GPUConfig":
        kwargs: Dict[str, Any] = {}
        section_types = {
            "compute": ComputeConfig,
            "memory": MemoryConfig,
            "architecture": ArchitectureConfig,
            "thermal": ThermalConfig,
            "power": PowerConfig,
            "silicon": SiliconConfig,
            "simulation": SimulationConfig,
        }
        for key, value in data.items():
            if key in section_types and isinstance(value, dict):
                valid = {f.name for f in fields(section_types[key])}
                kwargs[key] = section_types[key](**{k: v for k, v in value.items() if k in valid})
            elif key == "name":
                kwargs["name"] = value
        return cls(**kwargs)

    @classmethod
    def load(cls, path: str | Path) -> "GPUConfig":
        return cls.from_dict(json.loads(Path(path).read_text()))


# ---------------------------------------------------------------------------
# Convenience presets. These are starting points for the optimiser, not
# ground-truth performance claims -- every number below is an *input*
# to the simulation, never an output.
# ---------------------------------------------------------------------------

def preset_flagship() -> GPUConfig:
    """A large, high-power, high-SM-count die aimed at max throughput."""
    cfg = GPUConfig(name="NEURAX-FLAGSHIP")
    cfg.architecture.num_sms = 132
    cfg.compute.cuda_cores_per_sm = 128
    cfg.memory.use_hbm = True
    cfg.memory.vram_capacity_gb = 24.0
    cfg.memory.vram_bandwidth_gbps = 1008.0
    cfg.thermal.tdp_watts = 450.0
    cfg.power.tdp_watts = 450.0
    cfg.power.boost_clock_ghz = 2.75
    return cfg


def preset_mainstream() -> GPUConfig:
    """A balanced mid-range die."""
    return GPUConfig(name="NEURAX-MAINSTREAM")


def preset_efficiency() -> GPUConfig:
    """A small, power-constrained die aimed at perf/W."""
    cfg = GPUConfig(name="NEURAX-EFFICIENCY")
    cfg.architecture.num_sms = 30
    cfg.compute.cuda_cores_per_sm = 64
    cfg.thermal.tdp_watts = 115.0
    cfg.power.tdp_watts = 115.0
    cfg.power.boost_clock_ghz = 2.1
    cfg.memory.vram_capacity_gb = 8.0
    cfg.memory.vram_bandwidth_gbps = 256.0
    return cfg


PRESETS = {
    "flagship": preset_flagship,
    "mainstream": preset_mainstream,
    "efficiency": preset_efficiency,
}


def get_preset(name: str) -> GPUConfig:
    if name not in PRESETS:
        raise KeyError(f"Unknown preset '{name}'. Available: {sorted(PRESETS)}")
    return PRESETS[name]()
