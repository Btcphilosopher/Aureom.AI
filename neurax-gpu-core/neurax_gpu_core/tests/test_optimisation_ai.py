from neurax_gpu_core.ai.workload_predictor import PerformancePredictor
from neurax_gpu_core.optimisation.memory_optimizer import MemoryOptimizer
from neurax_gpu_core.optimisation.scheduling_optimizer import SchedulingOptimizer
from neurax_gpu_core.utils.config import GPUConfig
from neurax_gpu_core.architecture.gpu_design import GPUDesign
from neurax_gpu_core.compute.warp_scheduler import SchedulingPolicy


def test_scheduling_optimizer_switches_to_gto_under_high_divergence():
    cfg = GPUConfig()
    cfg.architecture.num_sms = 2
    design = GPUDesign(cfg, scheduling_policy=SchedulingPolicy.ROUND_ROBIN)
    optimizer = SchedulingOptimizer(evaluation_interval=1, min_samples=3)

    optimizer.observe(divergence_rate=0.4, occupancy=0.8)
    optimizer.observe(divergence_rate=0.35, occupancy=0.8)
    optimizer.observe(divergence_rate=0.5, occupancy=0.8)
    rec = optimizer.maybe_retune(timestep=3, sms=design.sms, apply=True)

    assert rec is not None
    assert rec.new_policy == SchedulingPolicy.GREEDY_THEN_OLDEST
    assert design.sms[0].schedulers[0].policy == SchedulingPolicy.GREEDY_THEN_OLDEST


def test_scheduling_optimizer_does_not_fire_before_interval():
    optimizer = SchedulingOptimizer(evaluation_interval=25, min_samples=3)
    optimizer.observe(0.4, 0.8)
    optimizer.observe(0.4, 0.8)
    optimizer.observe(0.4, 0.8)
    assert optimizer.maybe_retune(timestep=3, sms=[]) is None


def test_memory_optimizer_flags_bandwidth_saturation():
    optimizer = MemoryOptimizer(evaluation_interval=1)
    recs = optimizer.evaluate(timestep=0, l1_hit_rate=0.9, l2_hit_rate=0.9,
                               bandwidth_utilisation=0.97, mem_access_fraction=0.5)
    severities = {r.severity for r in recs}
    assert "critical" in severities


def test_memory_optimizer_flags_low_hit_rate():
    optimizer = MemoryOptimizer(evaluation_interval=1)
    recs = optimizer.evaluate(timestep=0, l1_hit_rate=0.2, l2_hit_rate=0.2,
                               bandwidth_utilisation=0.5, mem_access_fraction=0.4)
    assert any("L1 hit rate is low" in r.message for r in recs)


def test_performance_predictor_fits_linear_relationship():
    predictor = PerformancePredictor(prefer_torch=False)  # deterministic path for the test
    X = [[i] for i in range(10)]
    y = [3.0 * i + 1.0 for i in range(10)]
    report = predictor.fit(X, y)
    assert report.train_r2 > 0.99
    pred = predictor.predict([[20]])
    assert abs(pred[0] - 61.0) < 2.0
