"""Provenance tagging: every number MemoryFlow reports says where it came from.

The four classes are kept strictly separate in data structures and reports:

THEORETICAL     closed-form ceilings (peak FLOP/s, pin bandwidth, roofline bound)
ANALYTICAL      model estimates with stated assumptions (tiling traffic, energy,
                area, efficiency factors)
PY_SIMULATION   Python discrete-event / trace-driven simulation (cache sim,
                bank-conflict sim, dataflow pipeline sim)
RTL_SIMULATION  cycle counts measured from the SystemVerilog RTL in Verilator
MEASURED        silicon / FPGA lab measurement -- none exist yet for
                SilicaFlux-V; the slot exists so the report format never changes
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Provenance(str, Enum):
    THEORETICAL = "THEORETICAL"
    ANALYTICAL = "ANALYTICAL"
    PY_SIMULATION = "PY_SIMULATION"
    RTL_SIMULATION = "RTL_SIMULATION"
    MEASURED = "MEASURED"


@dataclass(frozen=True)
class Quantity:
    """A value with unit, provenance and a short note on its origin."""

    value: float
    unit: str
    provenance: Provenance
    note: str = ""

    def __float__(self) -> float:
        return float(self.value)

    def fmt(self, digits: int = 3) -> str:
        return f"{self.value:.{digits}g} {self.unit} [{self.provenance.value}]"
