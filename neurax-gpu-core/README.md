# NEURAX GPU CORE

A modular, production-grade Python simulation platform for GPU accelerator
**architecture R&D and performance analysis** -- compute cores, memory
hierarchy, scheduling/execution pipelines, thermal and power behaviour,
silicon layout/cost trade-offs, and workload-specific performance, all
wired together so that every reported number (TFLOPS, GB/s, latency,
occupancy, watts, degrees C, die cost) **emerges from the simulation**
rather than being assumed up front.

This is not a graphics renderer. It's a simulator of the bottlenecks that
define modern AI, gaming and compute hardware.

## Why nothing is hard-coded

* **Compute** is simulated at warp/instruction granularity: SMs are
  partitioned into SIMT processing blocks, warp schedulers pick ready warps
  each cycle, branch divergence shrinks active-lane masks, and FLOPs are
  only ever counted for lanes that actually executed.
* **Memory** is a real cache hierarchy (set-associative, LRU, per-SM L1 +
  shared L2) backed by a bandwidth-queued VRAM/HBM model -- hit rates and
  achieved bandwidth are measured, not configured.
* **Thermal & power** form a closed control loop: workload activity drives
  power draw, power drives die temperature (with per-SM hotspot diffusion
  across the physical floorplan), and temperature drives DVFS clock/voltage
  scaling for the *next* timestep -- which then changes how much work gets
  done. A hot chip really does get slower here.
* **Silicon** area, transistor count, wafer yield (Murphy's model) and
  cost-per-good-die are derived from the same architecture configuration
  driving the runtime simulation, so bigger/denser designs visibly cost
  more and yield worse.

See `ARCHITECTURE.md`-style documentation in each module's docstring for
the mechanics; the short version is in
[`neurax_gpu_core/core/engine.py`](neurax_gpu_core/core/engine.py).

## Install

```bash
pip install -r requirements.txt
# optional: pip install matplotlib torch   # plots / the AI tuner's MLP backend
```

## Quick start

```bash
# Run a mixed workload simulation on the mainstream preset
python -m neurax_gpu_core.main --preset mainstream --timesteps 300

# Bigger flagship die, HBM, custom SM count
python -m neurax_gpu_core.main --preset flagship --num-sms 100 --timesteps 500

# Export full per-timestep telemetry + summary plots
python -m neurax_gpu_core.main --timesteps 500 --csv out.csv --plot-dir plots/

# Run the AI architecture optimiser (SM count / core width / cache / TDP search)
python -m neurax_gpu_core.main --optimise --objective perf_per_watt --rounds 3
```

Or drive it directly from Python:

```python
from neurax_gpu_core.utils.config import get_preset
from neurax_gpu_core.workloads.ai_training import AITrainingWorkload
from neurax_gpu_core.workloads.gaming import GamingWorkload
from neurax_gpu_core.core.engine import SimulationEngine
from neurax_gpu_core.ui.dashboard import Dashboard

config = get_preset("flagship")
engine = SimulationEngine(config, [GamingWorkload(seed=1), AITrainingWorkload(seed=2)])
engine.run(500)

Dashboard(engine).print_summary()
df = engine.metrics_log.to_dataframe()   # full per-timestep telemetry
```

## Simulation loop

Each `SimulationEngine.step()` call advances one macro timestep
(`config.simulation.seconds_per_timestep`, default 1ms) through the pipeline
described in the spec:

```
dispatch_kernels() -> execute_warps() -> simulate_compute_units()
  -> process_memory_requests() -> update_cache_hierarchy()
  -> compute_performance_metrics() -> update_thermal_state()
  -> apply_power_constraints() -> optimise_gpu_architecture()
```

Internally, a short cycle-accurate "micro simulation" window
(`config.simulation.micro_cycles_per_timestep` core-clock cycles) measures
instantaneous rates -- IPC, cache hit rates, divergence, memory demand --
which are then extrapolated across the timestep's real duration at whatever
clock frequency the thermal/power control loop just decided on. This keeps
a multi-hundred-timestep run tractable in pure Python while still deriving
every throughput number from actually-simulated warp/cache/memory activity.

## Package layout

```
neurax_gpu_core/
├── core/            engine.py, simulation_loop.py, gpu_clock.py
├── compute/         sm_units.py, cuda_core_model.py, warp_scheduler.py, instruction_pipeline.py
├── memory/          vram_model.py, hbm_model.py, cache_hierarchy.py, memory_controller.py
├── architecture/    gpu_design.py, chip_layout.py, interconnect.py
├── workloads/       gaming.py, ai_training.py, rendering.py, physics_sim.py
├── execution/       kernel_dispatch.py, thread_model.py, warp_execution.py
├── performance/     throughput.py, latency.py, occupancy.py
├── thermal/         heat_model.py, cooling_system.py, throttling.py
├── power/           power_model.py, efficiency.py
├── silicon/         area_model.py, transistor_cost.py, yield_model.py
├── optimisation/    architecture_optimizer.py, scheduling_optimizer.py, memory_optimizer.py
├── ai/              gpu_tuner.py, workload_predictor.py
├── ui/              dashboard.py, gpu_visualizer.py
├── utils/           logging.py, config.py
├── main.py
└── tests/
```

## Testing

```bash
python -m pytest neurax_gpu_core/tests -q
```

## Tech stack

Python 3.11+, NumPy, Pandas, Matplotlib (optional), PyTorch (optional, AI
tuner surrogate model). No fixed GPU benchmarks or static performance
tables are used anywhere in the codebase -- every metric is read back out
of the subsystems after they run.
