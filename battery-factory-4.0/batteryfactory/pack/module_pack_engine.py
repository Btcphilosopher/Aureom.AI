"""Pack assembly (spec item 32): modules -> pack -> BMS -> final test."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from batteryfactory.config.chemistry_profiles import ChemistryProfile
from batteryfactory.config.factory_config import PackArchitecture
from batteryfactory.datamodel.models import Module, Pack, TestResult, next_serial
from batteryfactory.pack.bms import BMSSimulation, CellTelemetry


@dataclass
class PackTestResult:
    pack: Pack
    bms_reading_summary: dict


class PackAssemblyLine:
    def __init__(self, bms: BMSSimulation | None = None, rng: np.random.Generator | None = None) -> None:
        self.bms = bms or BMSSimulation()
        self.rng = rng or np.random.default_rng()

    def assemble_pack(self, modules: list[Module], architecture: PackArchitecture, profile: ChemistryProfile) -> Pack:
        # Series-connected modules: pack capacity is set by the weakest module,
        # same weakest-link logic as cell matching one level up.
        capacities = np.array([m.capacity_ah for m in modules])
        pack_capacity_ah = float(capacities.min()) * architecture.modules_parallel if len(capacities) else 0.0
        pack_voltage = profile.nominal_voltage_v * (modules[0].series_count if modules else 0) * architecture.modules_series
        capacity_kwh = pack_voltage * pack_capacity_ah / 1000.0

        return Pack(
            pack_id=next_serial("PACK"),
            module_ids=[m.module_id for m in modules],
            series_count=architecture.modules_series,
            parallel_count=architecture.modules_parallel,
            nominal_voltage_v=pack_voltage,
            capacity_kwh=capacity_kwh,
            bms_id=next_serial("BMS"),
        )

    def final_test(self, pack: Pack, modules: list[Module], profile: ChemistryProfile) -> PackTestResult:
        cells = [
            CellTelemetry(
                voltage_v=float(self.rng.normal(profile.nominal_voltage_v, 0.02)),
                temperature_c=float(self.rng.normal(28.0, 2.0)),
                capacity_ah=float(self.rng.normal(m.capacity_ah / max(m.parallel_count, 1), m.capacity_ah * 0.01)),
            )
            for m in modules
        ]
        reading = self.bms.evaluate(cells, profile.capacity_ah_reference, profile.capacity_ah_reference)

        pack.test_result = TestResult.PASS if not any(f.severity == "critical" for f in reading.faults) else TestResult.FAIL

        return PackTestResult(
            pack=pack,
            bms_reading_summary={
                "soc_pct": reading.soc_pct, "soh_pct": reading.soh_pct,
                "voltage_imbalance_v": reading.voltage_imbalance_v,
                "max_cell_temp_c": reading.max_cell_temp_c,
                "faults": [f.code for f in reading.faults],
            },
        )
