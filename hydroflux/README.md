# HydroFlux

A research-grade Python engine for **optimising** hydroelectric and tidal
power generation -- conventional reservoir hydro, run-of-river, pumped
storage, tidal range/lagoon/barrage and tidal stream arrays -- across a
common hydraulic, turbine, reservoir, grid, environmental and economic
modelling framework.

This is not a power calculator. Given a hydraulic/tidal resource, a turbine
fleet, a reservoir/basin configuration, a grid requirement and economic
assumptions, HydroFlux determines the **configuration and operating
strategy** that extracts the maximum useful energy and economic value while
respecting physical, environmental and operational constraints:

* How much electricity can this resource produce, and at what capacity factor?
* What turbine configuration and dispatch maximises output *or* revenue *or* minimises LCOE?
* When should water be stored, and when released?
* What is the optimal pumped-storage arbitrage strategy for a given price signal?
* When should a tidal basin sluice, hold, or generate -- and in which direction?
* What is the economic value of retaining one more cubic metre of stored water right now?

Every result keeps **OPTIMAL** and **PERMITTED** distinct (a
`SafetyGovernor` clips optimiser output to hard engineering/environmental
limits, it is never allowed to bypass them), and keeps the theoretical,
physical, available, environmentally-permitted and economically-optimal
generation potential distinct rather than conflating them into one number.

## Install

```bash
pip install -r requirements.txt
pip install -e .
# optional extras:
pip install -e ".[parquet]"   # Parquet I/O
pip install -e ".[netcdf]"    # NetCDF I/O
pip install -e ".[torch]"     # gradient-based optimisation backend
pip install -e ".[dev]"       # pytest, hypothesis
```

## Quick start

```python
import hydroflux
from hydroflux.core.config import HydroSystemConfig, TurbineConfig, ReservoirConfig
from hydroflux.core.timeseries import ResourceTimeSeries, make_time_index
from hydroflux.hydrology.hydrology import synthetic_river_inflow
import pandas as pd, numpy as np

index = make_time_index("2025-01-01", periods=24 * 365, freq="1h")
inflow = synthetic_river_inflow(index, mean_flow_m3s=220, seasonal_amplitude_m3s=90, noise_std_m3s=15, seed=42)
price = pd.Series(40 + 15 * np.sin(np.linspace(0, 730 * np.pi, len(index))), index=index).clip(lower=5)
resource = ResourceTimeSeries(index=index, inflow=inflow, price=price)

system = HydroSystemConfig(
    name="500 MW Reservoir Hydro",
    system_type="reservoir",
    turbines=[TurbineConfig(id=f"T{i+1}", type="francis", rated_power_mw=125, rated_flow_m3s=130, minimum_flow_m3s=20) for i in range(4)],
    reservoir=ReservoirConfig(capacity_mcm=900, dead_storage_mcm=80, minimum_level_m=200, maximum_level_m=260, initial_level_m=245, surface_area_km2=42),
)

result = hydroflux.simulate(system, resource)                       # evaluate a given/default operating policy
optimised = hydroflux.optimize(system, resource, objective="max_revenue")  # search for the best one
table = hydroflux.compare({"baseline": result, "optimised": optimised})
print(hydroflux.reporting.summarize(optimised))
```

Two complete, runnable examples matching the specification's worked
examples ship in `examples/`:

```bash
python -m examples.reservoir_hydro_example    # 500 MW reservoir, 4 turbines, variable inflow & price
python -m examples.tidal_barrage_example      # 300 MW two-way tidal barrage, 10 turbines
```

(Full-year hourly `optimize()` calls run a global metaheuristic search over
a physical simulation and can take a few minutes; reduce `periods`,
`maxiter`/`popsize`, or switch `algorithm="scipy"` for a faster local
search during iteration.)

## Package layout

```
hydroflux/
    core/           config objects, the simulate/optimise pipeline (engine.py),
                    the common time-series interface, safety governor, digital twin
    hydraulics/     P = rho g Q H eta, penstock/intake/channel losses, dynamic net head
    hydrology/      river inflow modelling, flow-duration curves, drought/flood scenarios
    tidal/          harmonic tide model, basin/barrage operating-mode optimiser,
                    tidal-stream turbine + power curve, modular wake-loss model
    turbines/       Kaplan/Francis/Pelton/bulb/tidal-stream/custom turbines,
                    flow x head efficiency surface, multi-turbine dispatch,
                    maintenance scheduling & failure-mode impact
    reservoirs/     elevation-storage mass balance, water-value engine (backward DP)
    pumped_storage/ price-threshold heuristic + exact LP arbitrage scheduler
    grid/           curtailment, grid-value scoring, hybrid (wind/solar/battery) dispatch
    environment/    environmental flow constraints, simplified sediment transport model
    economics/      CAPEX/OPEX, LCOE, NPV, IRR, payback
    optimisation/   pluggable algorithms (scipy, differential evolution, genetic,
                    Monte Carlo, a from-scratch Bayesian/GP optimiser, optional PyTorch
                    gradient descent, linear programming) + weighted multi-objective search
    scenarios/      named reproducible scenarios (drought/flood/climate/etc.) + Monte Carlo ensembles
    forecasting/    persistence / seasonal-naive / exponential-smoothing forecasts
    calibration/    RMSE/MAE/MAPE/R^2 + parameter calibration against observations
    data/           CSV / Parquet / JSON / NetCDF I/O (no embedded datasets)
    validation/     input/config validation
    reporting/      SimulationResult, human-readable summaries, scenario comparison,
                    sensitivity analysis, Monte Carlo P10/P50/P90 engine
    tests/          pytest suite
```

## The pipeline

```
INPUT DATA -> VALIDATION -> HYDROLOGICAL/TIDAL MODEL -> HYDRAULIC MODEL
-> TURBINE MODEL -> ENERGY MODEL -> GRID MODEL -> ENVIRONMENTAL CONSTRAINTS
-> ECONOMIC MODEL -> OPTIMISER -> OPTIMAL CONFIGURATION -> SIMULATION -> RESULTS
```

`hydroflux.simulate(system, resource_data)` runs this pipeline once for a
given (or default) operating policy. `hydroflux.optimize(system,
resource_data, objective=...)` searches a parametrised operating policy
(reservoir target level / release sensitivity to price, a tidal
generating-head threshold, ...) against a chosen objective -- or a weighted
combination of energy, revenue, efficiency, LCOE, NPV, grid value, water
security and environmental impact via `ObjectiveWeights` -- using a
pluggable global optimisation algorithm, then returns the fully simulated
result for the best policy found. Pumped storage instead solves an exact
linear program for price arbitrage directly (see
`hydroflux.pumped_storage`), since that problem is genuinely linear rather
than needing a metaheuristic search.

Every `SimulationResult` carries a `ReproducibilityRecord` (model version,
scenario, a hash of the configuration and input data, the random seed, and
the optimisation method/parameters used) so any result can be traced back
to exactly what produced it.

## Design principles this codebase follows

* **Theoretical power is never delivered power.** `hydraulics.hydraulics`
  keeps `theoretical_power` (rho g Q H) and `electrical_power` (chained
  through turbine/generator/transmission efficiency) as distinct functions;
  `SimulationResult` reports theoretical, physical, available and
  environmentally-permitted generation as separate numbers.
* **Efficiency is a curve, not a constant.** `EfficiencyCurve` maps flow
  fraction (and, via a head-derating curve, head fraction) to turbine
  efficiency; the multi-turbine dispatcher (`turbines.dispatch`) can commit
  fewer machines nearer their best efficiency point rather than always
  running the whole fleet.
* **Environmental constraints are hard constraints.** They clip the flow
  the optimiser is allowed to use, not a penalty term it can trade away.
* **OPTIMAL is not automatically PERMITTED.** `core.safety.SafetyGovernor`
  enforces dam-safety/turbine-protection/grid limits on optimiser output
  after the fact and reports what, if anything, was clipped.
* **Vectorised where it matters, honest where a loop is unavoidable.**
  Hydraulic/economic formulas operate on whole NumPy arrays; the
  reservoir/dispatch simulation loop is a genuine per-timestep state
  machine (storage depends on the previous step) implemented as a tight,
  profiled loop rather than falsely vectorised.
* **Machine learning only where it earns its keep.** The Bayesian
  optimiser is a real from-scratch Gaussian-process/UCB implementation for
  expensive low-dimensional searches; the optional PyTorch backend does
  genuine finite-difference-assisted gradient descent. Neither is
  decoration.

## Testing

```bash
pytest hydroflux/tests
```

The suite covers the core hydraulic equations, turbine efficiency/dispatch
behaviour, reservoir mass balance and water-value monotonicity, the tidal
cycle and barrage operating-mode logic, pumped-storage arbitrage economics
(including that the exact LP schedule never earns less than the threshold
heuristic on the same price series), every pluggable optimisation
algorithm against a known analytic optimum, economic formulas (NPV/IRR/
LCOE/payback) against hand-computable cases, scenario reproducibility, and
config/data validation, plus end-to-end integration tests through the
public `simulate` / `optimize` / `compare` API.
