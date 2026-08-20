from neurax_gpu_core.architecture.chip_layout import ChipLayout
from neurax_gpu_core.power.power_model import PowerModel
from neurax_gpu_core.thermal.heat_model import HeatModel
from neurax_gpu_core.thermal.throttling import ThrottlingController
from neurax_gpu_core.utils.config import PowerConfig, ThermalConfig


def test_throttling_scales_down_above_threshold():
    cfg = ThermalConfig(throttle_temp_c=80.0, critical_temp_c=100.0)
    controller = ThrottlingController(cfg)
    cool = controller.evaluate(60.0)
    hot = controller.evaluate(95.0)
    critical = controller.evaluate(110.0)
    assert cool.scaling_factor == 1.0
    assert cool.is_throttling is False
    assert 0.0 < hot.scaling_factor < 1.0
    assert hot.is_throttling is True
    assert critical.is_critical is True
    assert critical.scaling_factor <= hot.scaling_factor


def test_throttle_events_counted_once_per_episode():
    cfg = ThermalConfig(throttle_temp_c=80.0, critical_temp_c=100.0)
    controller = ThrottlingController(cfg)
    for temp in [60, 90, 92, 91, 60, 93]:
        controller.evaluate(float(temp))
    # Two separate throttling episodes: [90,92,91] and [93].
    assert controller.throttle_events == 2


def test_heat_model_rises_under_sustained_power():
    thermal_cfg = ThermalConfig(thermal_mass_j_per_c=50.0, cooling_type="air")
    layout = ChipLayout(num_sms=4, sms_per_gpc=4)
    heat = HeatModel(thermal_cfg, layout)
    start_temp = heat.die_temp_c
    for _ in range(200):
        state = heat.step(sm_power_watts=[80.0, 80.0, 80.0, 80.0], total_power_watts=320.0, dt_seconds=0.01)
    assert state.die_temp_c > start_temp


def test_heat_model_cools_toward_ambient_when_idle():
    thermal_cfg = ThermalConfig(thermal_mass_j_per_c=50.0, ambient_temp_c=25.0)
    layout = ChipLayout(num_sms=4, sms_per_gpc=4)
    heat = HeatModel(thermal_cfg, layout)
    for _ in range(50):
        heat.step(sm_power_watts=[100.0] * 4, total_power_watts=400.0, dt_seconds=0.01)
    hot_temp = heat.die_temp_c
    for _ in range(400):
        state = heat.step(sm_power_watts=[0.0] * 4, total_power_watts=0.0, dt_seconds=0.01)
    assert state.die_temp_c < hot_temp


def test_power_model_higher_freq_draws_more_power():
    cfg = PowerConfig()
    model = PowerModel(cfg, num_sms=8)
    low = model.compute_power(freq_ghz=cfg.base_clock_ghz, activity_factor=1.0,
                               sm_activity_fractions=[1.0] * 8, bandwidth_utilisation=0.0)
    high = model.compute_power(freq_ghz=cfg.boost_clock_ghz, activity_factor=1.0,
                                sm_activity_fractions=[1.0] * 8, bandwidth_utilisation=0.0)
    assert high.total_power_watts > low.total_power_watts


def test_power_budget_solver_respects_tdp():
    cfg = PowerConfig(tdp_watts=150.0)
    model = PowerModel(cfg, num_sms=8)
    freq = model.max_freq_for_power_budget(activity_factor=1.0, bandwidth_utilisation=0.0,
                                            upper_bound_ghz=cfg.boost_clock_ghz)
    power = model.compute_power(freq, 1.0, [1.0] * 8, 0.0)
    assert power.total_power_watts <= cfg.tdp_watts + 1e-6
