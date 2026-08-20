"""
Configuration objects for HydroFlux.

Everything the engine needs is expressed as a configuration object rather
than hard-coded constants, and every configuration can be built in Python,
or loaded from YAML/JSON (see :meth:`HydroSystemConfig.from_yaml` /
:meth:`HydroSystemConfig.from_json`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml


class SystemType(str, Enum):
    RESERVOIR = "reservoir"
    RUN_OF_RIVER = "run_of_river"
    PUMPED_STORAGE = "pumped_storage"
    TIDAL_RANGE = "tidal_range"
    TIDAL_BARRAGE = "tidal_barrage"
    TIDAL_LAGOON = "tidal_lagoon"
    TIDAL_STREAM = "tidal_stream"
    HYBRID = "hybrid"


class TurbineType(str, Enum):
    KAPLAN = "kaplan"
    FRANCIS = "francis"
    PELTON = "pelton"
    BULB = "bulb"
    TIDAL_STREAM = "tidal_stream"
    CUSTOM = "custom"


def _from_dict(cls, data: dict[str, Any]):
    """Best-effort dataclass construction that ignores unknown keys and
    recurses into nested dataclass fields where possible."""

    if data is None:
        return None
    kwargs = {}
    for f in cls.__dataclass_fields__.values():  # type: ignore[attr-defined]
        if f.name not in data:
            continue
        value = data[f.name]
        kwargs[f.name] = value
    return cls(**kwargs)


@dataclass
class SimulationConfig:
    """Top-level simulation clock / reproducibility settings."""

    start: str = "2025-01-01"
    periods: int = 24 * 365
    freq: str = "1h"
    seed: int = 42
    currency: str = "GBP"


@dataclass
class EfficiencyCurveConfig:
    """Sampled efficiency-vs-flow (and optionally vs-head) curve.

    ``flow_fraction`` is flow as a fraction of rated flow in [0, 1];
    ``efficiency`` is the corresponding total (turbine) efficiency in
    [0, 1]. If omitted, a sensible default curve is generated per
    turbine type (see :mod:`hydroflux.turbines.turbines`).
    """

    flow_fraction: Optional[list[float]] = None
    efficiency: Optional[list[float]] = None


@dataclass
class MaintenanceWindowConfig:
    start: str
    duration_hours: float


@dataclass
class TurbineConfig:
    id: str
    type: TurbineType = TurbineType.FRANCIS
    rated_power_mw: float = 100.0
    rated_flow_m3s: float = 100.0
    minimum_flow_m3s: float = 10.0
    maximum_flow_m3s: Optional[float] = None
    minimum_head_m: float = 1.0
    maximum_head_m: Optional[float] = None
    generator_efficiency: float = 0.98
    transmission_efficiency: float = 0.99
    availability: float = 0.97
    efficiency_curve: EfficiencyCurveConfig = field(default_factory=EfficiencyCurveConfig)
    maintenance_windows: list[MaintenanceWindowConfig] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = TurbineType(self.type)
        if self.maximum_flow_m3s is None:
            self.maximum_flow_m3s = self.rated_flow_m3s * 1.1
        if isinstance(self.efficiency_curve, dict):
            self.efficiency_curve = EfficiencyCurveConfig(**self.efficiency_curve)
        self.maintenance_windows = [
            m if isinstance(m, MaintenanceWindowConfig) else MaintenanceWindowConfig(**m)
            for m in self.maintenance_windows
        ]


@dataclass
class ReservoirConfig:
    """``*_level_m`` fields are absolute elevation (m above datum) of the
    reservoir water surface -- the same quantity used directly in the head
    calculation, not a separate storage measure. Storage volume is derived
    from elevation via a linear elevation-storage relationship between
    ``minimum_level_m``/``dead_storage_mcm`` and
    ``maximum_level_m``/``capacity_mcm`` (see :class:`Reservoir`)."""

    name: str = "reservoir"
    capacity_mcm: float = 100.0  # million cubic metres, storage at maximum_level_m
    minimum_level_m: float = 200.0
    maximum_level_m: float = 260.0
    initial_level_m: float = 250.0
    dead_storage_mcm: float = 5.0  # storage at minimum_level_m
    surface_area_km2: float = 5.0
    evaporation_mm_per_day: float = 0.0
    tailwater_elevation_m: float = 150.0
    penstock_length_m: float = 500.0
    penstock_diameter_m: float = 6.0
    penstock_friction_factor: float = 0.015
    intake_loss_coefficient: float = 0.15


@dataclass
class PumpConfig:
    rated_power_mw: float = 50.0
    rated_flow_m3s: float = 40.0
    efficiency: float = 0.88
    minimum_load_fraction: float = 0.4


@dataclass
class PumpedTurbineConfig:
    rated_power_mw: float = 50.0
    efficiency: float = 0.90


@dataclass
class PumpedStorageConfig:
    upper_reservoir: ReservoirConfig = field(
        default_factory=lambda: ReservoirConfig(name="upper", capacity_mcm=20.0)
    )
    lower_reservoir: ReservoirConfig = field(
        default_factory=lambda: ReservoirConfig(name="lower", capacity_mcm=20.0)
    )
    pump: PumpConfig = field(default_factory=PumpConfig)
    turbine: PumpedTurbineConfig = field(default_factory=PumpedTurbineConfig)
    pump_price_threshold: Optional[float] = None
    generate_price_threshold: Optional[float] = None

    def __post_init__(self):
        if isinstance(self.upper_reservoir, dict):
            self.upper_reservoir = ReservoirConfig(**self.upper_reservoir)
        if isinstance(self.lower_reservoir, dict):
            self.lower_reservoir = ReservoirConfig(**self.lower_reservoir)
        if isinstance(self.pump, dict):
            self.pump = PumpConfig(**self.pump)
        if isinstance(self.turbine, dict):
            self.turbine = PumpedTurbineConfig(**self.turbine)


@dataclass
class TidalConfig:
    mode: str = "two_way"  # ebb_generation | flood_generation | two_way | pump_assisted
    mean_sea_level_m: float = 0.0
    tidal_amplitude_m: float = 4.0
    tidal_period_hours: float = 12.42  # M2 semi-diurnal constituent
    phase_rad: float = 0.0
    basin_area_km2: float = 10.0
    basin_volume_mcm: float = 40.0
    sluice_capacity_m3s: float = 2000.0
    minimum_generating_head_m: float = 1.0
    initial_basin_level_m: float = 0.0
    seawater_density_kgm3: float = 1025.0


@dataclass
class TidalStreamConfig:
    rotor_diameter_m: float = 20.0
    rated_power_mw: float = 1.5
    cut_in_speed_ms: float = 0.7
    rated_speed_ms: float = 2.65
    cut_out_speed_ms: float = 4.0
    power_coefficient: float = 0.42
    drivetrain_efficiency: float = 0.93
    seawater_density_kgm3: float = 1025.0
    turbine_count: int = 1
    spacing_diameters: float = 5.0
    wake_decay_constant: float = 0.05


@dataclass
class EconomicConfig:
    capex_total: float = 500_000_000.0
    opex_fixed_annual: float = 8_000_000.0
    opex_variable_per_mwh: float = 1.5
    replacement_cost: float = 0.0
    replacement_year: Optional[int] = None
    decommissioning_cost: float = 0.0
    discount_rate: float = 0.07
    inflation_rate: float = 0.02
    project_lifetime_years: int = 40
    degradation_rate_annual: float = 0.002
    construction_years: int = 0


@dataclass
class EnvironmentalConfig:
    minimum_ecological_flow_m3s: float = 0.0
    maximum_flow_alteration_pct: float = 100.0
    restricted_periods: list[dict] = field(default_factory=list)  # [{"start":..., "end":..., "max_flow_m3s":...}]
    minimum_reservoir_level_m: Optional[float] = None
    maximum_reservoir_level_m: Optional[float] = None


@dataclass
class GridConfig:
    objective: str = "max_revenue"
    grid_export_capacity_mw: Optional[float] = None
    peak_demand_weight: float = 0.0


@dataclass
class HydroSystemConfig:
    """Top-level system description: the single object the optimiser and
    simulator both consume."""

    name: str = "hydroflux-system"
    system_type: SystemType = SystemType.RESERVOIR
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    turbines: list[TurbineConfig] = field(default_factory=list)
    reservoir: Optional[ReservoirConfig] = None
    pumped_storage: Optional[PumpedStorageConfig] = None
    tidal: Optional[TidalConfig] = None
    tidal_stream: Optional[TidalStreamConfig] = None
    economics: EconomicConfig = field(default_factory=EconomicConfig)
    environmental: EnvironmentalConfig = field(default_factory=EnvironmentalConfig)
    grid: GridConfig = field(default_factory=GridConfig)

    def __post_init__(self):
        if isinstance(self.system_type, str):
            self.system_type = SystemType(self.system_type)
        if isinstance(self.simulation, dict):
            self.simulation = SimulationConfig(**self.simulation)
        if isinstance(self.economics, dict):
            self.economics = EconomicConfig(**self.economics)
        if isinstance(self.environmental, dict):
            self.environmental = EnvironmentalConfig(**self.environmental)
        if isinstance(self.grid, dict):
            self.grid = GridConfig(**self.grid)
        if isinstance(self.reservoir, dict):
            self.reservoir = ReservoirConfig(**self.reservoir)
        if isinstance(self.pumped_storage, dict):
            self.pumped_storage = PumpedStorageConfig(**self.pumped_storage)
        if isinstance(self.tidal, dict):
            self.tidal = TidalConfig(**self.tidal)
        if isinstance(self.tidal_stream, dict):
            self.tidal_stream = TidalStreamConfig(**self.tidal_stream)
        self.turbines = [
            t if isinstance(t, TurbineConfig) else TurbineConfig(**t) for t in self.turbines
        ]

    @property
    def rated_power_mw(self) -> float:
        return sum(t.rated_power_mw for t in self.turbines)

    def to_dict(self) -> dict[str, Any]:
        def convert(obj):
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [convert(v) for v in obj]
            return obj

        return convert(asdict(self))

    def to_yaml(self, path: str | Path) -> None:
        Path(path).write_text(yaml.safe_dump(self.to_dict(), sort_keys=False))

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HydroSystemConfig":
        return cls(**data)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "HydroSystemConfig":
        data = yaml.safe_load(Path(path).read_text())
        return cls.from_dict(data)

    @classmethod
    def from_json(cls, path: str | Path) -> "HydroSystemConfig":
        data = json.loads(Path(path).read_text())
        return cls.from_dict(data)
