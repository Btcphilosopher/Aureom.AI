"""
Factory digital twin core (spec items 1, 61): the top-level object that
wires config + chemistry + materials + machines + the DES engine + quality
+ energy + maintenance + economics + traceability + safety + waste into one
coherent twin, matching the architecture:

                 BATTERYFACTORY 4.0
                         |
                 DIGITAL TWIN CORE
           MATERIALS - MACHINES - PRODUCTS
                 PRODUCTION MODEL
        QUALITY - ENERGY - MAINTENANCE
                     OPTIMISER
                FACTORY ECONOMICS
                    MANAGEMENT
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from batteryfactory.config.chemistry_profiles import ChemistryProfile, get_profile
from batteryfactory.config.factory_config import FactoryConfig, default_gigafactory_config
from batteryfactory.economics.capex_opex import CapexInputs, OpexInputs
from batteryfactory.economics.cost_engine import CostEngine, CostInputs, UnitCostResult
from batteryfactory.economics.profitability import FactoryFinancials, FinancialResult
from batteryfactory.energy.energy_engine import EnergyDigitalTwin, EnergyKPIs
from batteryfactory.energy.water_utilities import UtilityIntensity, WaterUtilitiesModel
from batteryfactory.maintenance.maintenance_engine import MaintenancePrediction, PredictiveMaintenanceEngine
from batteryfactory.quality.quality_engine import ProcessCapability, QualityDistributionGenerator
from batteryfactory.safety.safety_monitor import SafetyAlarm, SafetyMonitor
from batteryfactory.simulation.bottleneck import BottleneckAnalyzer, BottleneckScore
from batteryfactory.simulation.des_engine import FactorySimulationEngine, FactorySimulationResult
from batteryfactory.traceability.genealogy import GenealogyGraph
from batteryfactory.waste.waste_recycling import WasteSummary, WasteTracker


@dataclass
class FactoryTwinResult:
    simulation: FactorySimulationResult
    energy: EnergyKPIs
    utility_intensity: UtilityIntensity
    unit_cost: UnitCostResult
    financials: FinancialResult
    bottlenecks: list[BottleneckScore]
    quality_capability: dict[str, ProcessCapability]
    maintenance_predictions: list[MaintenancePrediction]
    safety_alarms: list[SafetyAlarm]
    waste: WasteSummary


class FactoryDigitalTwin:
    def __init__(self, config: FactoryConfig, rng: np.random.Generator | None = None) -> None:
        self.config = config
        self.profile: ChemistryProfile = get_profile(config.chemistry)
        self.rng = rng or np.random.default_rng()

        self.genealogy = GenealogyGraph()
        self.energy_twin = EnergyDigitalTwin()
        self.water_model = WaterUtilitiesModel()
        self.cost_engine = CostEngine()
        self.financials = FactoryFinancials()
        self.bottleneck_analyzer = BottleneckAnalyzer()
        self.quality_generator = QualityDistributionGenerator(rng=self.rng)
        self.maintenance_engine = PredictiveMaintenanceEngine()
        self.safety_monitor = SafetyMonitor()
        self.waste_tracker = WasteTracker()

        self.simulation_engine = FactorySimulationEngine(config, self.profile, rng=self.rng)

    @classmethod
    def build_default(cls, seed: int | None = None) -> "FactoryDigitalTwin":
        return cls(default_gigafactory_config(), rng=np.random.default_rng(seed))

    def run_simulation(
        self,
        hours: float = 24.0,
        material_cost_per_cell: float = 6.5,
        selling_price_per_kwh: float = 95.0,
        electricity_price_per_kwh: float = 0.12,
        capex: CapexInputs | None = None,
    ) -> FactoryTwinResult:
        sim_result = self.simulation_engine.run(hours=hours)

        energy_breakdown = self.energy_twin.compute_breakdown(sim_result)
        energy_kpis = self.energy_twin.compute_kpis(sim_result, self.profile, energy_breakdown)

        utility_consumption = self.water_model.estimate_consumption(sim_result.cells_completed)
        utility_intensity = self.water_model.compute_intensity(utility_consumption, sim_result.cells_completed)

        cell_energy_kwh = self.profile.capacity_ah_reference * self.profile.nominal_voltage_v / 1000.0
        kwh_produced = sim_result.cells_completed * cell_energy_kwh

        cost_inputs = CostInputs(
            material_cost=material_cost_per_cell * sim_result.cells_completed,
            energy_cost=energy_kpis.total_factory_kwh * electricity_price_per_kwh,
            labour_cost=hours * self.config.num_production_lines * 3 * 35.0,  # ~3 operators/line/hr, model assumption
            maintenance_cost=hours * self.config.num_production_lines * 12.0,
            depreciation_cost=(capex.annual_depreciation / (365 * 24) * hours) if capex else 0.0,
            scrap_cost=sim_result.cells_scrapped_or_rejected * material_cost_per_cell,
            logistics_cost=sim_result.packs_completed * 25.0,
            overhead_cost=hours * 500.0,
        )
        unit_cost = self.cost_engine.compute_unit_costs(
            cost_inputs, sim_result.cells_completed, max(kwh_produced, 1e-6),
            sim_result.modules_completed, sim_result.packs_completed,
        )

        opex = OpexInputs(
            materials=cost_inputs.material_cost, electricity=cost_inputs.energy_cost, labour=cost_inputs.labour_cost,
            maintenance=cost_inputs.maintenance_cost, logistics=cost_inputs.logistics_cost,
            consumables=cost_inputs.overhead_cost * 0.1, waste=cost_inputs.scrap_cost,
        )
        annual_scale = (8760.0 / hours) if hours > 0 else 0.0
        financial_result = self.financials.compute(
            selling_price_per_kwh, kwh_produced * annual_scale,
            OpexInputs(*(getattr(opex, f) * annual_scale for f in
                         ["materials", "electricity", "labour", "maintenance", "logistics", "consumables", "waste"])),
            capex or CapexInputs(0, 0, 0, 0, 0, 0, 0, 0, 0),
        )

        bottlenecks = self.bottleneck_analyzer.analyze(sim_result)

        quality_capability: dict[str, ProcessCapability] = {}
        if sim_result.cells_completed > 5:
            nominal = {
                "capacity_ah": self.profile.capacity_ah_reference * 0.93,
                "resistance_mohm": 1.5, "voltage_v": self.profile.nominal_voltage_v,
                "weight_g": 900.0, "thickness_um": 15000.0,
            }
            samples = self.quality_generator.generate(nominal, n=min(500, sim_result.cells_completed * 5))
            quality_capability["capacity_ah"] = self.quality_generator.capability(
                "capacity_ah", samples["capacity_ah"], usl=nominal["capacity_ah"] * 1.05, lsl=nominal["capacity_ah"] * 0.9)
            quality_capability["resistance_mohm"] = self.quality_generator.capability(
                "resistance_mohm", samples["resistance_mohm"], usl=3.0, lsl=0.0)

        maintenance_predictions = [self.maintenance_engine.predict(m) for m in self.simulation_engine.machines.values()]

        safety_readings = {
            "process_temp_c": max((m.telemetry.temperature_c for m in self.simulation_engine.machines.values()), default=25.0),
            "formation_temp_c": max((m.telemetry.temperature_c for m in self.simulation_engine.formation_machines), default=25.0),
        }
        machine_faults = {mid: (m.fault_count > 0) for mid, m in self.simulation_engine.machines.items()}
        safety_alarms = self.safety_monitor.evaluate(safety_readings, machine_faults)

        waste_summary = self.waste_tracker.summarise(sim_result, material_cost_per_cell)

        return FactoryTwinResult(
            simulation=sim_result, energy=energy_kpis, utility_intensity=utility_intensity,
            unit_cost=unit_cost, financials=financial_result, bottlenecks=bottlenecks,
            quality_capability=quality_capability, maintenance_predictions=maintenance_predictions,
            safety_alarms=safety_alarms, waste=waste_summary,
        )

    def current_state(self) -> dict:
        """A JSON-serialisable snapshot for the API/dashboard layers."""
        return {
            "factory_name": self.config.name,
            "chemistry": self.config.chemistry.value,
            "cell_format": self.config.cell_format.value,
            "num_production_lines": self.config.num_production_lines,
            "annual_capacity_cells": self.config.theoretical_annual_capacity_cells,
            "machines": {
                mid: {"state": m.state.value, "utilisation_pct": m.utilisation_pct, "fault_count": m.fault_count}
                for mid, m in self.simulation_engine.machines.items()
            },
        }
