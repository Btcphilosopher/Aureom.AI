import numpy as np

from batteryfactory.datamodel.models import MachineState
from batteryfactory.energy.energy_optimiser import EnergyOptimiser, FlexibleLoad
from batteryfactory.energy.renewables import BatteryStorageSpec, RenewableDispatchSimulator
from batteryfactory.energy.water_utilities import WaterUtilitiesModel
from batteryfactory.machines.machine_twin import MachineTwin, MachineTwinConfig
from batteryfactory.maintenance.maintenance_engine import PredictiveMaintenanceEngine
from batteryfactory.traceability.genealogy import GenealogyGraph


def test_maintenance_prediction_rises_with_runtime_and_anomaly():
    engine = PredictiveMaintenanceEngine()
    fresh = MachineTwin(MachineTwinConfig("M1", "Fresh", "test", 1.0, 10.0))
    fresh.transition(MachineState.STARTING)
    fresh.transition(MachineState.RUNNING)
    fresh.runtime_hours = 100.0

    worn = MachineTwin(MachineTwinConfig("M2", "Worn", "test", 1.0, 10.0))
    worn.transition(MachineState.STARTING)
    worn.transition(MachineState.RUNNING)
    worn.runtime_hours = 18000.0
    worn.telemetry.vibration_mm_s = 3.0
    worn.telemetry.temperature_c = 70.0

    fresh_pred = engine.predict(fresh)
    worn_pred = engine.predict(worn)
    assert worn_pred.failure_probability_next_week > fresh_pred.failure_probability_next_week
    assert worn_pred.remaining_useful_life_hours < fresh_pred.remaining_useful_life_hours


def test_energy_optimiser_reduces_cost_vs_baseline():
    hourly_price = np.array([0.10, 0.30, 0.35, 0.05, 0.06, 0.40, 0.38, 0.10] * 3)
    loads = [
        FlexibleLoad("formation_batch", energy_kwh=200.0, duration_hours=2, earliest_start_hour=0, latest_finish_hour=len(hourly_price)),
        FlexibleLoad("hvac_boost", energy_kwh=50.0, duration_hours=1, earliest_start_hour=0, latest_finish_hour=len(hourly_price)),
    ]
    result = EnergyOptimiser().optimise(loads, hourly_price)
    assert result.optimised_cost <= result.baseline_cost


def test_renewable_dispatch_reduces_grid_import_vs_no_solar():
    n = 24
    load = np.full(n, 500.0)
    solar = np.array([0]*6 + [200, 400, 600, 700, 700, 600, 500, 400, 300, 100] + [0]*8)
    wind = np.zeros(n)
    battery = BatteryStorageSpec(capacity_kwh=1000, max_charge_kw=300, max_discharge_kw=300)
    price = np.full(n, 0.15)

    sim = RenewableDispatchSimulator()
    with_solar = sim.dispatch(load, solar, wind, battery, price)
    without_solar = sim.dispatch(load, np.zeros(n), wind, battery, price)
    assert float(np.sum(with_solar.grid_import_kwh)) < float(np.sum(without_solar.grid_import_kwh))


def test_water_utilities_intensity_scales_with_output():
    model = WaterUtilitiesModel()
    consumption = model.estimate_consumption(cells_produced=10_000)
    intensity = model.compute_intensity(consumption, cells_produced=10_000)
    assert intensity.process_water_l_per_cell > 0


def test_genealogy_traces_forward_and_backward():
    graph = GenealogyGraph()
    graph.add_node("MAT-1", "material_batch")
    graph.add_node("ELEC-1", "electrode_batch")
    graph.add_node("CELL-1", "cell")
    graph.add_node("MOD-1", "module")
    graph.add_node("PACK-1", "pack")
    graph.link("MAT-1", "ELEC-1")
    graph.link("ELEC-1", "CELL-1")
    graph.link("CELL-1", "MOD-1")
    graph.link("MOD-1", "PACK-1")

    assert "PACK-1" in graph.trace_forward("MAT-1")
    assert "MAT-1" in graph.trace_backward("PACK-1")
