"""
Cell assembly (spec item 11): abstract process modules so cylindrical,
prismatic and pouch cell architectures can all be represented by composing
the same building blocks in a different order/selection.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from batteryfactory.datamodel.models import Cell, CellFormat, Chemistry, ElectrodeBatch, next_serial


@dataclass
class ProcessOutcome:
    ok: bool
    scrap: bool
    energy_kwh: float
    notes: str = ""


class ProcessModule(ABC):
    """One physical operation in cell assembly."""

    name: str = "process"

    def __init__(self, base_defect_rate: float, energy_kwh: float, rng: np.random.Generator) -> None:
        self.base_defect_rate = base_defect_rate
        self.energy_kwh = energy_kwh
        self.rng = rng

    @abstractmethod
    def run(self) -> ProcessOutcome:
        ...


class SimpleDefectModule(ProcessModule):
    def run(self) -> ProcessOutcome:
        failed = self.rng.random() < self.base_defect_rate
        return ProcessOutcome(ok=not failed, scrap=failed, energy_kwh=self.energy_kwh, notes=self.name)


class ElectrodeHandling(SimpleDefectModule):
    name = "electrode_handling"


class Stacking(SimpleDefectModule):
    name = "stacking"


class Winding(SimpleDefectModule):
    name = "winding"


class TabWelding(SimpleDefectModule):
    name = "tab_welding"


class Casing(SimpleDefectModule):
    name = "casing"


class ElectrolyteFilling(SimpleDefectModule):
    name = "electrolyte_filling"


class Sealing(SimpleDefectModule):
    name = "sealing"


# Format -> ordered process chain. This is the "abstract process module"
# mechanism the spec calls for: swapping the format swaps the recipe, not
# the code.
_FORMAT_RECIPES: dict[CellFormat, list[type[ProcessModule]]] = {
    CellFormat.CYLINDRICAL: [ElectrodeHandling, Winding, TabWelding, Casing, ElectrolyteFilling, Sealing],
    CellFormat.PRISMATIC: [ElectrodeHandling, Stacking, TabWelding, Casing, ElectrolyteFilling, Sealing],
    CellFormat.POUCH: [ElectrodeHandling, Stacking, TabWelding, ElectrolyteFilling, Sealing],
}

_DEFAULT_DEFECT_RATES: dict[str, float] = {
    "electrode_handling": 0.003,
    "stacking": 0.006,
    "winding": 0.008,
    "tab_welding": 0.010,
    "casing": 0.004,
    "electrolyte_filling": 0.007,
    "sealing": 0.005,
}

_DEFAULT_ENERGY_KWH: dict[str, float] = {
    "electrode_handling": 0.02,
    "stacking": 0.05,
    "winding": 0.04,
    "tab_welding": 0.08,
    "casing": 0.03,
    "electrolyte_filling": 0.06,
    "sealing": 0.05,
}


@dataclass
class CellAssemblyResult:
    cell: Cell | None
    scrapped_at_step: str | None
    total_energy_kwh: float


class CellAssemblyLine:
    def __init__(self, cell_format: CellFormat, chemistry: Chemistry, line_id: str, rng: np.random.Generator | None = None) -> None:
        self.cell_format = cell_format
        self.chemistry = chemistry
        self.line_id = line_id
        self.rng = rng or np.random.default_rng()
        module_types = _FORMAT_RECIPES[cell_format]
        self.chain: list[ProcessModule] = [
            mtype(_DEFAULT_DEFECT_RATES[mtype.name], _DEFAULT_ENERGY_KWH[mtype.name], self.rng)
            for mtype in module_types
        ]

    def assemble(self, electrode_batches: list[ElectrodeBatch]) -> CellAssemblyResult:
        total_energy = 0.0
        for step in self.chain:
            outcome = step.run()
            total_energy += outcome.energy_kwh
            if outcome.scrap:
                return CellAssemblyResult(cell=None, scrapped_at_step=step.name, total_energy_kwh=total_energy)

        cell = Cell(
            serial_number=next_serial("CELL"),
            cell_format=self.cell_format,
            chemistry=self.chemistry,
            electrode_batch_ids=[b.batch_id for b in electrode_batches],
            line_id=self.line_id,
        )
        return CellAssemblyResult(cell=cell, scrapped_at_step=None, total_energy_kwh=total_energy)
