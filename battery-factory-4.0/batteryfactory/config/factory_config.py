"""
Factory configuration (spec item 2): factory size, lines, capacity, shifts,
operating hours, annual target, chemistry, cell format and module/pack
architecture are all user-configurable -- nothing about the factory design
is hard-coded.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from batteryfactory.datamodel.models import CellFormat, Chemistry


@dataclass
class ModuleArchitecture:
    cells_series: int = 14
    cells_parallel: int = 6

    @property
    def cells_per_module(self) -> int:
        return self.cells_series * self.cells_parallel


@dataclass
class PackArchitecture:
    modules_series: int = 8
    modules_parallel: int = 1

    @property
    def modules_per_pack(self) -> int:
        return self.modules_series * self.modules_parallel


@dataclass
class ShiftPattern:
    shifts_per_day: int = 3
    hours_per_shift: float = 8.0
    operating_days_per_year: int = 350

    @property
    def hours_per_day(self) -> float:
        return self.shifts_per_day * self.hours_per_shift

    @property
    def hours_per_year(self) -> float:
        return self.hours_per_day * self.operating_days_per_year


@dataclass
class FactoryConfig:
    name: str
    chemistry: Chemistry
    cell_format: CellFormat
    num_production_lines: int
    line_capacity_cells_per_hour: float
    shift_pattern: ShiftPattern = field(default_factory=ShiftPattern)
    module_architecture: ModuleArchitecture = field(default_factory=ModuleArchitecture)
    pack_architecture: PackArchitecture = field(default_factory=PackArchitecture)
    annual_production_target_cells: float = 0.0
    floor_area_m2: float = 40_000.0

    @property
    def theoretical_annual_capacity_cells(self) -> float:
        return (
            self.num_production_lines
            * self.line_capacity_cells_per_hour
            * self.shift_pattern.hours_per_year
        )

    @property
    def capacity_utilisation_vs_target(self) -> float:
        if self.annual_production_target_cells <= 0:
            return 0.0
        return self.theoretical_annual_capacity_cells / self.annual_production_target_cells

    def cells_per_pack(self) -> int:
        return self.module_architecture.cells_per_module * self.pack_architecture.modules_per_pack


def default_gigafactory_config() -> FactoryConfig:
    """A representative starting point -- fully overridable."""
    return FactoryConfig(
        name="BatteryFactory 4.0 - Gigafactory Alpha",
        chemistry=Chemistry.LFP,
        cell_format=CellFormat.PRISMATIC,
        num_production_lines=4,
        line_capacity_cells_per_hour=600.0,
        shift_pattern=ShiftPattern(shifts_per_day=3, hours_per_shift=8.0, operating_days_per_year=350),
        module_architecture=ModuleArchitecture(cells_series=14, cells_parallel=6),
        pack_architecture=PackArchitecture(modules_series=8, modules_parallel=1),
        annual_production_target_cells=4_800_000.0,
        floor_area_m2=60_000.0,
    )
