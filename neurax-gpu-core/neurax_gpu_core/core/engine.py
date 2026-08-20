"""
SimulationEngine: the top-level orchestrator implementing the pipeline
described in the project spec::

    dispatch_kernels() -> execute_warps() -> simulate_compute_units()
    -> process_memory_requests() -> update_cache_hierarchy()
    -> compute_performance_metrics() -> update_thermal_state()
    -> apply_power_constraints() -> optimise_gpu_architecture()

Each call to :meth:`SimulationEngine.step` advances the simulation by one
macro timestep (``config.simulation.seconds_per_timestep`` of wall-clock
time). Internally it runs a short cycle-accurate "micro simulation" window
(``config.simulation.micro_cycles_per_timestep`` core-clock cycles) to
*measure* instantaneous rates -- IPC, cache hit rates, divergence, memory
demand -- and extrapolates those measured rates across the timestep's real
duration at whatever clock frequency the thermal/power control loop just
decided on. Nothing about TFLOPS, bandwidth or latency is assumed; all of
it is read back out of the subsystems after they've actually run.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from ..architecture.gpu_design import GPUDesign
from ..compute.warp_scheduler import SchedulingPolicy
from ..execution.warp_execution import WarpExecutionEngine
from ..optimisation.memory_optimizer import MemoryOptimizer
from ..optimisation.scheduling_optimizer import SchedulingOptimizer
from ..performance.latency import LatencyTracker
from ..performance.occupancy import OccupancyAnalyzer
from ..performance.throughput import ThroughputTracker
from ..power.efficiency import EfficiencyTracker
from ..power.power_model import PowerModel
from ..thermal.heat_model import HeatModel
from ..thermal.throttling import ThrottlingController
from ..utils.config import GPUConfig
from ..utils.logging import MetricsLog, get_logger
from ..workloads.base import Workload
from .gpu_clock import GPUClock

logger = get_logger("engine")


@dataclass
class TimestepResult:
    timestep: int
    tflops: float
    gips: float
    ipc_per_sm: float
    utilisation_fraction: float
    achieved_bandwidth_gbps: float
    bandwidth_utilisation: float
    l1_hit_rate: float
    l2_hit_rate: float
    occupancy_achieved: float
    occupancy_theoretical: float
    simt_efficiency: float
    freq_ghz: float
    voltage_v: float
    total_power_watts: float
    die_temp_c: float
    max_sm_temp_c: float
    is_throttling: bool
    is_power_capped: bool
    gflops_per_watt: float
    active_kernel: str
    queue_depth: int


class SimulationEngine:
    def __init__(self, config: GPUConfig, workloads: List[Workload],
                 scheduling_policy: SchedulingPolicy = SchedulingPolicy.GREEDY_THEN_OLDEST):
        self.config = config
        self.workloads = workloads
        self.rng = random.Random(config.simulation.random_seed)

        self.gpu = GPUDesign(config, scheduling_policy)
        self.throttling = ThrottlingController(config.thermal)
        self.power_model = PowerModel(config.power, config.architecture.num_sms)
        self.clock = GPUClock(config.power, self.throttling, self.power_model)
        self.heat_model = HeatModel(config.thermal, self.gpu.chip_layout)
        self.warp_engine = WarpExecutionEngine(
            self.gpu.sms, self.gpu.dispatcher, self.gpu.memory_controller, self.rng,
        )

        self.throughput_tracker = ThroughputTracker()
        self.latency_tracker = LatencyTracker()
        self.efficiency_tracker = EfficiencyTracker()
        self.occupancy_analyzer = OccupancyAnalyzer(self.gpu.sms, config.compute.max_warps_per_sm)
        self.scheduling_optimizer = SchedulingOptimizer()
        self.memory_optimizer = MemoryOptimizer()
        self.metrics_log = MetricsLog()

        self.timestep = 0
        self.core_cycle = 0
        self._workload_cursor = 0
        self._active_run = None
        self._prev_activity_factor = 0.75
        self._prev_bandwidth_utilisation = 0.0
        self._recorded_run_ids: set = set()

        self.history: List[TimestepResult] = []

    # -- kernel launch cadence ------------------------------------------------

    def _next_workload(self) -> Workload:
        w = self.workloads[self._workload_cursor % len(self.workloads)]
        self._workload_cursor += 1
        return w

    def _ensure_kernel_launched(self) -> None:
        if self._active_run is not None and not self._active_run.is_complete:
            return
        if not self.workloads:
            return
        workload = self._next_workload()
        shared_mem = getattr(workload, "shared_mem_bytes_per_block", 0)
        kernel = workload.generate_kernel(self.gpu, block_size=256, shared_mem_bytes_per_block=shared_mem)
        self._active_run = self.gpu.dispatcher.launch(kernel, self.core_cycle)

    def _current_divergence_probability(self) -> float:
        if self._active_run is not None:
            return self._active_run.kernel.divergence_probability
        return 0.05

    # -- main loop --------------------------------------------------------

    def step(self) -> TimestepResult:
        cfg = self.config
        dt_seconds = cfg.simulation.seconds_per_timestep
        micro_cycles = max(1, cfg.simulation.micro_cycles_per_timestep)

        # dispatch_kernels()
        self._ensure_kernel_launched()

        # DVFS decision, informed by the *previous* timestep's thermal/activity
        # readings (a realistic one-step control-loop lag).
        prev_max_temp = max(self.heat_model.sm_temps_c) if self.heat_model.sm_temps_c else cfg.thermal.ambient_temp_c
        clock_decision = self.clock.decide(
            desired_activity_factor=self._prev_activity_factor, max_temp_c=prev_max_temp,
            bandwidth_utilisation=self._prev_bandwidth_utilisation,
        )
        freq_ghz = clock_decision.freq_ghz
        divergence_probability = self._current_divergence_probability()

        # execute_warps() / simulate_compute_units()
        prev_sm_issued = [sm.cumulative_issued_instructions for sm in self.gpu.sms]
        agg_flops = 0.0
        agg_int_ops = 0
        agg_issued = 0
        agg_active_warps_sum = 0
        agg_resident_warps_sum = 0
        agg_divergence = 0
        for _ in range(micro_cycles):
            cyc = self.warp_engine.run_cycle(self.core_cycle, freq_ghz, divergence_probability)
            agg_flops += cyc.flops
            agg_int_ops += cyc.int_ops
            agg_issued += cyc.issued_instructions
            agg_active_warps_sum += cyc.active_warps
            agg_resident_warps_sum += cyc.resident_warps
            agg_divergence += cyc.divergence_events
            self.core_cycle += 1
        sm_issued_delta = [
            sm.cumulative_issued_instructions - prev for sm, prev in zip(self.gpu.sms, prev_sm_issued)
        ]

        actual_cycles_this_timestep = max(float(micro_cycles), freq_ghz * 1e9 * dt_seconds)
        scale = actual_cycles_this_timestep / micro_cycles

        # The micro-loop above only *samples* the first `micro_cycles` cycles
        # of this timestep at cycle-accurate granularity; the timestep's real
        # duration covers many more cycles than we can afford to simulate one
        # by one. Jump the (purely relative/ordering) cycle counter forward to
        # the timestep's true end-of-window cycle count and drain the memory
        # controller there, so in-flight memory requests -- whose latency is
        # real nanoseconds, not sample-cycles -- correctly resolve within the
        # timestep instead of appearing to take dozens of *timesteps*.
        remaining_cycles = int(actual_cycles_this_timestep) - micro_cycles
        if remaining_cycles > 0:
            self.core_cycle += remaining_cycles
            for req in self.gpu.memory_controller.drain_completed(self.core_cycle):
                self.gpu.sms[req.sm_id].wake_warp(req.warp_id, self.core_cycle)

        flops_ts = agg_flops * scale
        int_ops_ts = agg_int_ops * scale
        issued_ts = agg_issued * scale

        # process_memory_requests() / update_cache_hierarchy()
        mem_bytes_sample = self.gpu.memory_controller._mem_bytes_since_resolve
        extrapolated_bytes = int(mem_bytes_sample * scale)
        bw_result = self.gpu.memory_controller.resolve_bandwidth(extrapolated_bytes, dt_seconds * 1e9)
        cache_summary = self.gpu.memory_controller.summary()

        # compute_performance_metrics()
        avg_active_warps = agg_active_warps_sum / micro_cycles
        avg_resident_warps = agg_resident_warps_sum / micro_cycles
        occ_snapshot = self.occupancy_analyzer.snapshot(avg_active_warps, avg_resident_warps)
        simt_eff = self.occupancy_analyzer.simt_efficiency(agg_divergence, agg_issued)

        for run in list(self.gpu.dispatcher.runs.values()):
            if run.completion_cycle is not None and run.run_id not in self._recorded_run_ids:
                self.latency_tracker.record_completion(run, freq_ghz)
                self._recorded_run_ids.add(run.run_id)

        peak_flops_now = self.gpu.peak_flops_at_clock(freq_ghz)
        total_partitions = sum(len(sm.core_array.blocks) for sm in self.gpu.sms) or 1
        activity_factor = min(1.0, (agg_issued / micro_cycles) / total_partitions)
        tflops = flops_ts / dt_seconds / 1e12
        utilisation = min(1.0, (flops_ts / dt_seconds) / peak_flops_now) if peak_flops_now > 0 else 0.0
        gips = int_ops_ts / dt_seconds / 1e9
        ipc_per_sm = (agg_issued / micro_cycles) / max(1, len(self.gpu.sms))

        # update_thermal_state() / apply_power_constraints()
        power_state = self.power_model.compute_power(
            freq_ghz=freq_ghz, activity_factor=activity_factor,
            sm_activity_fractions=sm_issued_delta, bandwidth_utilisation=bw_result.utilisation_fraction,
        )
        thermal_state = self.heat_model.step(power_state.sm_power_watts, power_state.total_power_watts, dt_seconds)

        # optimise_gpu_architecture() (runtime scheduling/memory advisories)
        divergence_rate = (agg_divergence / agg_issued) if agg_issued else 0.0
        self.scheduling_optimizer.observe(divergence_rate=divergence_rate, occupancy=occ_snapshot.achieved_occupancy)
        self.scheduling_optimizer.maybe_retune(self.timestep, self.gpu.sms, apply=cfg.simulation.enable_ai_optimisation)
        self.memory_optimizer.evaluate(
            self.timestep, cache_summary["l1_hit_rate"], cache_summary["l2_hit_rate"],
            bw_result.utilisation_fraction, cache_summary["mem_access_fraction"],
        )

        self.throughput_tracker.update(flops_ts, int_ops_ts, issued_ts, actual_cycles_this_timestep, dt_seconds)
        eff_sample = self.efficiency_tracker.record(self.timestep, tflops, power_state.total_power_watts)

        result = TimestepResult(
            timestep=self.timestep, tflops=tflops, gips=gips, ipc_per_sm=ipc_per_sm,
            utilisation_fraction=utilisation, achieved_bandwidth_gbps=bw_result.achieved_bandwidth_gbps,
            bandwidth_utilisation=bw_result.utilisation_fraction, l1_hit_rate=cache_summary["l1_hit_rate"],
            l2_hit_rate=cache_summary["l2_hit_rate"], occupancy_achieved=occ_snapshot.achieved_occupancy,
            occupancy_theoretical=occ_snapshot.theoretical_occupancy, simt_efficiency=simt_eff,
            freq_ghz=freq_ghz, voltage_v=clock_decision.voltage_v, total_power_watts=power_state.total_power_watts,
            die_temp_c=thermal_state.die_temp_c, max_sm_temp_c=thermal_state.max_sm_temp_c,
            is_throttling=clock_decision.throttle.is_throttling, is_power_capped=clock_decision.power_capped,
            gflops_per_watt=eff_sample.gflops_per_watt,
            active_kernel=self._active_run.kernel.name if self._active_run else "-",
            queue_depth=self.gpu.dispatcher.queue_depth(),
        )
        self.history.append(result)
        self.metrics_log.record(**result.__dict__)

        self._prev_activity_factor = activity_factor
        self._prev_bandwidth_utilisation = bw_result.utilisation_fraction
        self.timestep += 1
        return result

    def run(self, num_timesteps: Optional[int] = None) -> List[TimestepResult]:
        n = num_timesteps if num_timesteps is not None else self.config.simulation.timesteps
        results = []
        for _ in range(n):
            results.append(self.step())
        return results

    def summary(self) -> dict:
        if not self.history:
            return {}
        recent = self.history[-min(len(self.history), 50):]
        return {
            "timesteps_run": len(self.history),
            "avg_tflops": sum(r.tflops for r in recent) / len(recent),
            "peak_tflops": max(r.tflops for r in self.history),
            "avg_utilisation": sum(r.utilisation_fraction for r in recent) / len(recent),
            "avg_bandwidth_gbps": sum(r.achieved_bandwidth_gbps for r in recent) / len(recent),
            "avg_occupancy": sum(r.occupancy_achieved for r in recent) / len(recent),
            "avg_power_watts": sum(r.total_power_watts for r in recent) / len(recent),
            "avg_gflops_per_watt": self.efficiency_tracker.average_gflops_per_watt(),
            "max_die_temp_c": max(r.die_temp_c for r in self.history),
            "throttle_events": self.throttling.throttle_events,
            "kernel_latency": self.latency_tracker.stats(),
        }
