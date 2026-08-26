# APEX HORIZON ENGINE

A modular, headless, **pure-Python** simulation core for an open-world
American-futurist racing game -- vehicle dynamics, a seamless multi-zone
world, weather, AI racers and traffic, police pursuits, procedural
events, progression/economy, and a lightweight adaptive ("ML-style")
player-style model, all wired together so that speed, grip, wheelspin,
drift, damage, and race outcomes **emerge from the simulation** instead
of being scripted.

This is not a renderer and it does not ship 100,000 lines of hand-tuned
content -- see [Scope](#scope-and-honesty-about-scale) below for what that
means and why. What it is: a real, runnable, fully-interconnected engine
core (~4,900 lines across 70 modules, 59 passing tests, zero third-party
runtime dependencies) built exactly to the architecture in the design
brief, ready to grow.

## Why nothing is hard-coded

* **Vehicle physics** is a planar rigid body with a two-axle tire model.
  Each axle has its own rotational wheel-speed state, integrated from
  drive/brake torque against the tire's reaction force -- wheelspin,
  lockup, and traction loss are not special-cased, they *emerge* when
  drive torque outruns available grip (see
  [`vehicles/vehicle_model.py`](apex_horizon_engine/vehicles/vehicle_model.py)).
  Tire force comes from a magic-formula slip curve combined through a
  friction ellipse ([`vehicles/tire_model.py`](apex_horizon_engine/vehicles/tire_model.py)),
  fed by weight transfer + body roll from a real spring/damper/anti-roll-bar
  model ([`vehicles/suspension.py`](apex_horizon_engine/vehicles/suspension.py))
  and v²-scaling drag/downforce ([`vehicles/aero_system.py`](apex_horizon_engine/vehicles/aero_system.py)).
* **Drift** is read out of the same rigid-body state (heading vs.
  velocity-vector angle + rear slip severity) -- it is a classifier over
  physics, not a separate mode.
* **AI racers** ([`ai/racer_ai.py`](apex_horizon_engine/ai/racer_ai.py))
  drive the identical `Vehicle` physics the player does, choosing
  throttle/brake/steer fresh every tick from live race state (corner
  geometry, gap to rivals, their own skill/aggression/mistake roll).
  Nobody's lap is scripted.
* **The adaptive AI** ([`ai/adaptive_ai.py`](apex_horizon_engine/ai/adaptive_ai.py))
  is a dependency-free, online exponential-moving-average behavioural
  model plus a softmax sampler -- no external AI APIs. It reads real
  telemetry every tick and slowly reshapes which events the world offers
  and which AI rival archetypes get spawned, so a player who drifts a lot
  genuinely sees more drift events and more drift-focused rivals.
* **Weather, traffic density, event difficulty, sponsorship income, and
  festival influence** all read from the same handful of state objects
  (`ReputationBook`, `WeatherSystem`, `ZoneSpec`) that every other system
  shares -- see [`core/engine.py`](apex_horizon_engine/core/engine.py),
  the one module allowed to wire subsystems together.

## Install

```bash
pip install -r requirements.txt      # only pytest -- the engine itself has zero deps
pip install -e .                     # optional, for the `apex-horizon-engine` console script
```

## Quick start

```bash
# Free-roam a hot hatch through the megacity for two minutes
python -m apex_horizon_engine.main --zone meridian_city --vehicle meridian_gt_hatch --duration 120

# Take a hypercar out to the desert dry lake, exporting full telemetry
python -m apex_horizon_engine.main --zone silica_flats --vehicle solace_hypercar --duration 90 --csv out.csv

# Verify the simulation is bit-for-bit deterministic under a fixed seed
python -m apex_horizon_engine.main --determinism-check
```

Or drive it directly from Python:

```python
from apex_horizon_engine.core.engine import ApexHorizonEngine
from apex_horizon_engine.core.simulation_loop import run_simulation
from apex_horizon_engine.utils.config import EngineConfig

engine = ApexHorizonEngine(EngineConfig(seed=7, starting_zone="pinegrade_range",
                                         starting_vehicle="outrider_rally"))
frames = run_simulation(engine, ticks=3600, log_interval=300)  # 60s at 60Hz
print(frames[-1].reputation, frames[-1].credits)
```

Run the test suite:

```bash
pytest -q
```

## Architecture

```
apex_horizon_engine/
├── core/          engine.py (top-level wiring), world_streaming.py,
│                  simulation_loop.py, state_manager.py (save/load)
├── vehicles/      vehicle_model.py, drivetrain.py, tire_model.py,
│                  suspension.py, aero_system.py
├── physics/       traction_model.py, collision.py, drift_system.py,
│                  damage_model.py
├── world/         weather_system.py, traffic_system.py, npc_drivers.py,
│                  event_generation.py, police_system.py
├── ai/            racer_ai.py, traffic_ai.py, adaptive_ai.py,
│                  crowd_simulation.py
├── progression/   reputation.py, unlock_tree.py, festival_system.py
├── economy/       credits.py, vehicle_market.py, sponsorships.py
├── multiplayer/   session_manager.py, convoy_system.py, sync_system.py
├── rendering/     terrain_renderer.py, lighting_system.py,
│                  weather_renderer.py, reflection_system.py
├── ui/            hud.py, minimap.py, telemetry_overlay.py, garage_ui.py
├── audio/         engine_audio.py, environmental_audio.py, radio_system.py
├── utils/         config.py (presets/dataclasses), logging.py
├── main.py        CLI entry point
└── tests/         59 pytest tests across every subsystem above
```

`core/engine.py` is the only module that reaches "across the grain" --
every other package only depends on the ones logically underneath it
(`physics` never imports `progression`, `ai` never imports `economy`,
etc.), so each subsystem can be read, tested, and swapped independently.

### World

One continuous coordinate space, five zone types placed in it as labelled
circular regions (`utils/config.py: WORLD_ZONES`) -- Meridian Megacity,
Silica Flats (industrial desert), Pinegrade Range (forest mountain),
Azurewake Coast, Harborline Yards (logistics). "Streaming"
(`core/world_streaming.py`) is a radius test against always-resident
zone data, never a hard cut or a loading screen.

### Vehicles

Seven starter vehicles spanning hot hatch, muscle, hypercar, drift,
rally, electric hypercar, and prototype classes, each a real
`VehicleSpec` (engine torque curve, drivetrain layout, tire compound,
suspension, aero) rather than a stat block. A twelve-part upgrade
catalogue (`progression/unlock_tree.py`) modifies those same dataclasses.

### Presentation, without a renderer

`rendering/`, `ui/`, and `audio/` produce the *structured numeric data* a
real front end would consume (light color temperature, particle density,
HUD frames, engine sound-layer mix weights) rather than pixels or audio
buffers -- the engine is headless by design so it can run in CI, in a
test, or embedded in a future graphical client without change.

## Scope and honesty about scale

The design brief asks for a 20,000-100,000+ line AAA production engine.
That figure describes a multi-year, multi-discipline team effort (art,
netcode, a real renderer, licensed audio, content at scale) -- not
something that can be honestly produced, reviewed, and kept correct in a
single build. What's here instead is the **complete architecture** from
the brief, **fully implemented and wired end-to-end**: every package in
the tree above is real, working code that the others actually call, not
a stub. It is deliberately positioned to grow -- a new vehicle is a
`VehicleSpec` entry, a new zone is a `ZoneSpec` entry, a new event type is
an `EventType` + a weight table, a real renderer is a client that reads
the `rendering`/`ui` output instead of a `print()` -- rather than a
prototype that would need re-architecting to scale up.

## Tech

Python 3.11+, dataclasses/enums throughout, deterministic fixed-timestep
simulation (`EngineConfig.deterministic`, verified by
`multiplayer/sync_system.py` lockstep checksums and
`tests/test_determinism.py`), zero third-party runtime dependencies.
