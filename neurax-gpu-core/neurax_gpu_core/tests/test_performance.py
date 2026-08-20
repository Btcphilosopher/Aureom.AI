from neurax_gpu_core.performance.latency import LatencyTracker
from neurax_gpu_core.performance.occupancy import OccupancyAnalyzer
from neurax_gpu_core.performance.throughput import ThroughputTracker
from neurax_gpu_core.architecture.gpu_design import GPUDesign
from neurax_gpu_core.utils.config import GPUConfig


class _FakeKernel:
    def __init__(self, name, tag):
        self.name = name
        self.workload_tag = tag


class _FakeRun:
    def __init__(self, run_id, launch, completion, tag="test"):
        self.run_id = run_id
        self.launch_cycle = launch
        self.completion_cycle = completion
        self.kernel = _FakeKernel(f"kernel_{run_id}", tag)

    def latency_cycles(self):
        return self.completion_cycle - self.launch_cycle


def test_throughput_tracker_average_matches_manual_calc():
    tracker = ThroughputTracker()
    tracker.update(flops=1e12, int_ops=0, issued_instructions=1000, cycles_elapsed=1000, seconds_elapsed=0.5)
    tracker.update(flops=1e12, int_ops=0, issued_instructions=1000, cycles_elapsed=1000, seconds_elapsed=0.5)
    # 2e12 flops over 1.0s -> 2 TFLOPS
    assert abs(tracker.average_tflops() - 2.0) < 1e-9


def test_latency_tracker_records_each_run_once():
    tracker = LatencyTracker()
    run = _FakeRun(run_id=1, launch=0, completion=1000)
    tracker.record_completion(run, avg_ghz_over_run=1.0)
    tracker.record_completion(run, avg_ghz_over_run=1.0)  # duplicate call: should be ignored
    assert len(tracker.records) == 1
    stats = tracker.stats()
    assert stats["count"] == 1
    assert stats["mean_ms"] > 0


def test_latency_tracker_by_workload_groups_correctly():
    tracker = LatencyTracker()
    tracker.record_completion(_FakeRun(1, 0, 500, tag="gaming"), avg_ghz_over_run=1.0)
    tracker.record_completion(_FakeRun(2, 0, 1500, tag="ai_training"), avg_ghz_over_run=1.0)
    grouped = tracker.by_workload()
    assert set(grouped.keys()) == {"gaming", "ai_training"}
    assert grouped["ai_training"]["mean_ms"] > grouped["gaming"]["mean_ms"]


def test_occupancy_theoretical_bounded_by_config_max():
    cfg = GPUConfig()
    cfg.architecture.num_sms = 4
    design = GPUDesign(cfg)
    analyzer = OccupancyAnalyzer(design.sms, cfg.compute.max_warps_per_sm)
    theoretical = analyzer.theoretical_occupancy()
    assert 0.0 <= theoretical <= 1.0


def test_simt_efficiency_decreases_with_divergence():
    full = OccupancyAnalyzer.simt_efficiency(divergence_events=0, issued_instructions=100)
    degraded = OccupancyAnalyzer.simt_efficiency(divergence_events=50, issued_instructions=100)
    assert full == 1.0
    assert degraded < full
