import numpy as np
import pytest

from hydroflux.core.config import TurbineConfig, TurbineType
from hydroflux.turbines.dispatch import optimise_dispatch
from hydroflux.turbines.turbines import default_efficiency_curve, make_turbine_from_config


def make_turbine(id="T1", rated_power_mw=100.0, rated_flow_m3s=100.0, min_flow=10.0, turbine_type=TurbineType.FRANCIS):
    config = TurbineConfig(id=id, type=turbine_type, rated_power_mw=rated_power_mw, rated_flow_m3s=rated_flow_m3s, minimum_flow_m3s=min_flow)
    return make_turbine_from_config(config)


def test_efficiency_curve_zero_at_zero_flow():
    curve = default_efficiency_curve(TurbineType.FRANCIS)
    assert curve.efficiency_at(0.0) == pytest.approx(0.0)


def test_efficiency_curve_peaks_within_bounds():
    curve = default_efficiency_curve(TurbineType.FRANCIS)
    assert 0.0 <= np.max(curve.efficiency) <= 1.0


def test_turbine_output_zero_below_minimum_flow():
    turbine = make_turbine(min_flow=20.0)
    power = turbine.output_power_mw(5.0, turbine.design_head_m)
    assert power == 0.0


def test_turbine_output_zero_below_minimum_head():
    turbine = make_turbine()
    power = turbine.output_power_mw(50.0, turbine.minimum_head_m - 0.1)
    assert power == 0.0


def test_turbine_output_positive_within_envelope():
    turbine = make_turbine()
    power = turbine.output_power_mw(turbine.rated_flow_m3s, turbine.design_head_m)
    assert power > 0.0
    # Should be close to (but not exceed) rated power at design conditions.
    assert power <= turbine.rated_power_mw * 1.05


def test_turbine_output_is_vectorised():
    turbine = make_turbine()
    flows = np.array([0.0, 20.0, 50.0, 100.0])
    powers = turbine.output_power_mw(flows, turbine.design_head_m)
    assert powers.shape == flows.shape
    assert powers[0] == 0.0


def test_best_operating_point_within_bounds():
    turbine = make_turbine(min_flow=10.0, rated_flow_m3s=100.0)
    flow, power = turbine.best_operating_point(available_flow_m3s=60.0, head_m=turbine.design_head_m)
    assert turbine.minimum_flow_m3s <= flow <= 60.0
    assert power > 0.0


def test_best_operating_point_zero_when_starved():
    turbine = make_turbine(min_flow=20.0)
    flow, power = turbine.best_operating_point(available_flow_m3s=5.0, head_m=turbine.design_head_m)
    assert flow == 0.0
    assert power == 0.0


def test_dispatch_commits_fewer_turbines_when_flow_is_limited():
    turbines = [make_turbine(id=f"T{i}", rated_power_mw=100, rated_flow_m3s=100, min_flow=20) for i in range(4)]
    head = turbines[0].design_head_m
    # Only enough flow for ~1.5 turbines worth -- dispatch should not spread
    # this thinly across all four (which would push every unit below its
    # efficient operating range).
    result = optimise_dispatch(turbines, available_flow_m3s=150.0, head_m=head)
    committed = [tid for tid, q in result.turbine_flows.items() if q > 0]
    assert len(committed) < 4
    assert result.total_flow_m3s <= 150.0 + 1e-6


def test_dispatch_spills_when_flow_exceeds_fleet_capacity():
    turbines = [make_turbine(id="T1", rated_power_mw=100, rated_flow_m3s=100, min_flow=10)]
    result = optimise_dispatch(turbines, available_flow_m3s=500.0, head_m=turbines[0].design_head_m)
    assert result.spill_m3s > 0.0
    assert result.total_flow_m3s <= turbines[0].maximum_flow_m3s + 1e-6


def test_dispatch_empty_when_no_flow():
    turbines = [make_turbine()]
    result = optimise_dispatch(turbines, available_flow_m3s=0.0, head_m=50.0)
    assert result.total_power_mw == 0.0
    assert result.spill_m3s == 0.0


def test_exact_dispatch_never_worse_than_greedy():
    turbines = [make_turbine(id=f"T{i}", rated_power_mw=50 + i * 10, rated_flow_m3s=50 + i * 10, min_flow=10) for i in range(3)]
    head = turbines[0].design_head_m
    greedy = optimise_dispatch(turbines, available_flow_m3s=120.0, head_m=head, exact=False)
    exact = optimise_dispatch(turbines, available_flow_m3s=120.0, head_m=head, exact=True)
    assert exact.total_power_mw >= greedy.total_power_mw - 1e-6
