import math

from neurax_gpu_core.core.engine import SimulationEngine
from neurax_gpu_core.utils.config import GPUConfig
from neurax_gpu_core.workloads.ai_training import AITrainingWorkload
from neurax_gpu_core.workloads.gaming import GamingWorkload
from neurax_gpu_core.workloads.physics_sim import PhysicsSimWorkload
from neurax_gpu_core.workloads.rendering import RenderingWorkload


def _small_config() -> GPUConfig:
    cfg = GPUConfig()
    cfg.architecture.num_sms = 4
    cfg.simulation.timesteps = 40
    cfg.simulation.micro_cycles_per_timestep = 48
    cfg.simulation.random_seed = 7
    return cfg


def test_engine_runs_and_produces_finite_metrics():
    cfg = _small_config()
    workloads = [GamingWorkload(seed=1), AITrainingWorkload(seed=2),
                 RenderingWorkload(seed=3), PhysicsSimWorkload(seed=4)]
    engine = SimulationEngine(cfg, workloads)
    results = engine.run(cfg.simulation.timesteps)

    assert len(results) == cfg.simulation.timesteps
    for r in results:
        for value in (r.tflops, r.gips, r.utilisation_fraction, r.achieved_bandwidth_gbps,
                      r.l1_hit_rate, r.l2_hit_rate, r.occupancy_achieved, r.freq_ghz,
                      r.total_power_watts, r.die_temp_c, r.max_sm_temp_c):
            assert math.isfinite(value), f"non-finite metric: {value}"
            assert value >= 0 or value == value  # no NaNs slipped through isfinite check above
        assert 0.0 <= r.utilisation_fraction <= 1.0 + 1e-6
        assert 0.0 <= r.occupancy_achieved <= 1.0 + 1e-6
        assert 0.0 <= r.l1_hit_rate <= 1.0
        assert 0.0 <= r.l2_hit_rate <= 1.0
        assert r.freq_ghz > 0


def test_engine_eventually_does_real_work():
    cfg = _small_config()
    cfg.simulation.timesteps = 60
    engine = SimulationEngine(cfg, [AITrainingWorkload(seed=1)])
    results = engine.run(cfg.simulation.timesteps)
    assert any(r.tflops > 0 for r in results)
    assert any(r.total_power_watts > cfg.power.idle_power_watts for r in results)


def test_kernel_completion_produces_latency_record():
    cfg = _small_config()
    cfg.simulation.timesteps = 60
    engine = SimulationEngine(cfg, [GamingWorkload(seed=1)])
    engine.run(cfg.simulation.timesteps)
    stats = engine.latency_tracker.stats()
    assert stats["count"] >= 1
    assert stats["mean_ms"] > 0.0


def test_no_nan_after_thermal_throttling_kicks_in():
    cfg = _small_config()
    cfg.thermal.thermal_mass_j_per_c = 2.0     # tiny thermal mass -> heats up fast
    cfg.thermal.ambient_temp_c = 25.0
    cfg.thermal.throttle_temp_c = 26.0         # just above ambient: any sustained load crosses it
    cfg.thermal.critical_temp_c = 35.0
    cfg.simulation.timesteps = 150
    engine = SimulationEngine(cfg, [AITrainingWorkload(seed=1)])
    results = engine.run(cfg.simulation.timesteps)
    assert any(r.is_throttling for r in results)
    assert all(math.isfinite(r.freq_ghz) and r.freq_ghz > 0 for r in results)


def test_summary_keys_present():
    cfg = _small_config()
    engine = SimulationEngine(cfg, [GamingWorkload(seed=1)])
    engine.run(cfg.simulation.timesteps)
    summary = engine.summary()
    for key in ("avg_tflops", "peak_tflops", "avg_utilisation", "avg_bandwidth_gbps",
                "avg_occupancy", "avg_power_watts", "avg_gflops_per_watt", "max_die_temp_c",
                "throttle_events", "kernel_latency"):
        assert key in summary
