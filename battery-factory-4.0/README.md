# BATTERYFACTORY 4.0

An industrial battery gigafactory **digital twin, discrete-event simulator
and optimisation platform** -- raw materials, electrode manufacturing, cell
assembly, formation, testing, module/pack assembly, quality, energy,
maintenance and factory economics, all wired into one simulation so that
every reported number (throughput, yield, kWh/cell, £/kWh, EBITDA, Cpk,
bottleneck ranking) **emerges from the underlying engines** rather than
being assumed up front.

```
RAW MATERIALS -> ELECTRODE PRODUCTION -> CELL ASSEMBLY -> FORMATION -> TESTING
    -> MODULE ASSEMBLY -> PACK ASSEMBLY -> QUALITY CONTROL -> WAREHOUSE -> SHIPPING
```

This is a simulator of a *factory*, not a model of one battery cell: the
core deliverable is the discrete-event simulation and data architecture in
`batteryfactory/`, with the CLI/dashboards/API as thin views onto it.

## Why nothing is hard-coded

* **Factory design is configurable, not assumed.** `config.factory_config`
  takes line count, line capacity, shift pattern, cell format (cylindrical
  / prismatic / pouch) and module/pack architecture as inputs; nothing
  downstream special-cases one factory layout.
* **Chemistry is a swappable profile, not baked into the physics.**
  `config.chemistry_profiles` ships LFP / NMC / NCA / LMFP / sodium-ion
  profiles as data, each tagged `DataProvenance.MODEL_ASSUMPTION` --
  formation recipes, EOL test acceptance bands and thermal limits all read
  from the active profile, so changing chemistry changes what the line
  accepts.
* **Production numbers come from physics-shaped process models, not
  constants.** Coating defect rates rise with line speed and slurry
  quality; calendering density follows a compaction curve under roller
  pressure; formation capacity is scaled by a coulombic-efficiency model
  that improves with gentler, longer recipes; EOL test bands are
  calibrated against what formation can actually deliver, not an
  unreachable 100% figure.
* **Machines are real state machines with real physics**, not throughput
  multipliers: `machines.machine_twin.MachineTwin` only allows the
  transitions a real controller would (`OFFLINE -> STARTING -> RUNNING ->
  {IDLE, CHANGEOVER, MAINTENANCE, FAULT}`), accrues runtime/energy only
  while `RUNNING`, and faults from a runtime-dependent hazard rate.
* **The factory itself is a discrete-event simulation**, not a
  spreadsheet: `simulation.events` is a small dependency-free DES kernel
  (generator-based processes, `yield env.timeout(...)`, a priority-queue
  calendar) and `simulation.des_engine` runs materials through every stage
  of the line using shared WIP buffers (`machines.conveyor.Buffer`) that
  can starve or block a stage exactly like a real line.
* **Costs, energy and quality are all read off the simulation's own
  output** -- `energy.energy_engine` sums the same per-stage energy the DES
  engine metered; `economics.cost_engine` divides real cost inputs by
  cells/kWh/modules/packs *actually produced* in the run; Cp/Cpk in
  `quality.quality_engine` are computed from generated sample
  distributions, not looked up.

## Architecture

```
                     BATTERYFACTORY 4.0
                             |
                     DIGITAL TWIN CORE  (core.factory_twin)
               MATERIALS - MACHINES - PRODUCTS
                       PRODUCTION MODEL  (simulation.des_engine)
              QUALITY - ENERGY - MAINTENANCE
                          OPTIMISER
                     FACTORY ECONOMICS
                        MANAGEMENT
```

Independently-testable service packages (spec-numbered where relevant):

| Package | Responsibility |
|---|---|
| `config` | Factory configuration + chemistry profiles |
| `datamodel` | Plain dataclasses for every domain object (Factory, Machine, Cell, Module, Pack, ...) |
| `materials` | Raw material catalogue, inventory (FIFO batches), supply-chain simulation, inventory optimiser (EOQ/safety stock/supplier mix) |
| `production` | Mixing, coating, calendering, electrode line, cell assembly (per-format process modules), dry room, formation, EOL testing |
| `quality` | SPC (Cp/Cpk/defect rate/FPY), correlated quality-distribution generator, cell-matching engine |
| `machines` | Machine digital twin (state machine + telemetry), robotics, conveyor/buffer material-flow model |
| `simulation` | The DES kernel, the factory pipeline built on it, bottleneck scoring, production scheduler + changeover optimiser |
| `maintenance` | Weibull-based predictive maintenance / RUL |
| `energy` | Energy digital twin + KPIs, load-shifting optimiser, renewables/battery-storage dispatch, water/utilities |
| `traceability` | Genealogy graph (material batch -> ... -> pack), battery passport |
| `pack` | Module/pack assembly, high-level BMS simulation, lumped-mass thermal twin |
| `safety` | Threshold-based alarms for operator attention (never autonomous control) |
| `waste` | Scrap tracking, disassembly/material-recovery recycling model |
| `economics` | Unit-cost engine, CAPEX/OPEX, factory profitability |
| `optimisation` | Weighted multi-objective optimiser, Monte Carlo engine, capacity optimiser |
| `ml` | Quality-rejection and predictive-maintenance models (sklearn if available, numpy fallback) trained on **simulated** data |
| `scenario` | Predefined scenarios (high demand, energy shock, ...) and a what-if simulator |
| `telemetry` | Event bus + sensor-reading schema with realistic timestamps |
| `database` | sqlite3 schema for telemetry/batches/products/quality/maintenance, indexed for high-volume writes |
| `security` | RBAC (10 factory roles), audit logging, API-key auth |
| `api` | FastAPI surface over the same engines (optional `api` extra) |
| `core` | `FactoryDigitalTwin` -- wires everything above into one run |
| `ui` | Management / Operations / Engineering / Finance dashboards |

## Install & run

```bash
cd battery-factory-4.0
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # or: pip install -e ".[full]"

# Run the four dashboards over a 48-hour simulated window
python -m batteryfactory.main --hours 48 --report

# Monte Carlo over material/energy price uncertainty
python -m batteryfactory.main --hours 24 --monte-carlo 300

# A predefined what-if scenario vs. the base case
python -m batteryfactory.main --hours 24 --scenario ENERGY_SHOCK

# Tests
pytest -q

# Optional HTTP API (requires the `api` extra)
uvicorn batteryfactory.api.app:app --reload
```

## Honesty notes (please read before treating any number as real)

* **Chemistry profiles, cost benchmarks and utility-intensity factors are
  model assumptions** (`DataProvenance.MODEL_ASSUMPTION`), drawn from
  public engineering ranges -- not a certified datasheet for any real
  product or factory.
* **The ML models train on this platform's own simulated telemetry**, not
  validated industrial data (spec item 45); they demonstrate the
  feature -> train -> predict -> feature-importance pipeline, not a
  production-ready predictor.
* **The BMS simulation (`pack.bms`) is a conceptual, informational model**,
  explicitly not certified safety-critical control software, and must
  never be used to make real charge/discharge/protection decisions.
* **The safety monitor (`safety.safety_monitor`) only raises alarms for
  operator attention** -- it never autonomously actuates anything.
* **This API/RBAC layer governs the digital twin's own analytical data**,
  never a physical industrial control system, which must never be exposed
  directly to the public internet.

## Testing

53 pytest tests cover every engine package plus a full end-to-end
integration run (`tests/test_integration.py`) that exercises the whole
DESIGN -> SIMULATE -> MEASURE -> OPTIMISE loop and checks the results are
internally consistent (unit conservation through the line, deterministic
given a seed, dashboards render without error).
