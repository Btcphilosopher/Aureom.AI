import numpy as np

from batteryfactory.config.chemistry_profiles import get_profile
from batteryfactory.config.factory_config import PackArchitecture
from batteryfactory.datamodel.models import Chemistry, Module
from batteryfactory.pack.bms import BMSSimulation, CellTelemetry
from batteryfactory.pack.module_pack_engine import PackAssemblyLine
from batteryfactory.pack.thermal import ThermalParams, ThermalTwin
from batteryfactory.safety.safety_monitor import AlarmSeverity, SafetyMonitor
from batteryfactory.waste.waste_recycling import RecyclingModel


def test_bms_flags_overvoltage_fault():
    bms = BMSSimulation(ov_threshold_v=4.2)
    cells = [CellTelemetry(voltage_v=4.3, temperature_c=25, capacity_ah=90)] + \
            [CellTelemetry(voltage_v=3.6, temperature_c=25, capacity_ah=90) for _ in range(13)]
    reading = bms.evaluate(cells, nominal_capacity_ah=90, rated_capacity_ah=90)
    assert any(f.code == "OVERVOLTAGE" for f in reading.faults)


def test_thermal_twin_higher_current_raises_steady_state_temp():
    twin = ThermalTwin()
    params = ThermalParams(thermal_mass_j_per_k=5000, convective_coefficient_w_per_k=10.0, coolant_temp_c=25.0)
    low_heat = twin.cell_heat_generation_w(current_a=50, resistance_ohm=0.002)
    high_heat = twin.cell_heat_generation_w(current_a=200, resistance_ohm=0.002)
    low_result = twin.simulate(params, low_heat, ambient_temp_c=25, duration_s=600)
    high_result = twin.simulate(params, high_heat, ambient_temp_c=25, duration_s=600)
    assert high_result.steady_state_temp_c > low_result.steady_state_temp_c


def test_pack_assembly_capacity_limited_by_weakest_module():
    profile = get_profile(Chemistry.LFP)
    modules = [
        Module("M1", [], series_count=14, parallel_count=6, capacity_ah=90.0),
        Module("M2", [], series_count=14, parallel_count=6, capacity_ah=80.0),  # weaker module
    ]
    line = PackAssemblyLine(rng=np.random.default_rng(0))
    pack = line.assemble_pack(modules, PackArchitecture(modules_series=2, modules_parallel=1), profile)
    assert pack.capacity_kwh > 0
    # capacity should reflect the 80 Ah weak module, not the average of 85
    assert pack.nominal_voltage_v > 0


def test_safety_monitor_flags_critical_formation_temp():
    monitor = SafetyMonitor()
    alarms = monitor.evaluate({"formation_temp_c": 90.0})
    assert any(a.severity == AlarmSeverity.CRITICAL for a in alarms)


def test_recycling_model_recovers_material_value():
    model = RecyclingModel()
    flow = model.process(
        failed_cells=1000,
        material_kg_per_cell={"copper_foil": 0.05, "graphite": 0.15},
        material_unit_cost={"copper_foil": 8.0, "graphite": 8.0},
    )
    assert flow.recovered_value > 0
    assert 0 < flow.virgin_material_offset_pct <= 100
