# MITHRIL.OS — Architecture & Spec Coverage

This document maps the 113-section design brief to what is actually
implemented in this repository, what is designed-but-deferred, and why —
in the spirit of the brief's own section 111 ("Do not fake persistence...
history must emerge from simulation") and this project's engineering
value of reporting outcomes faithfully rather than papering over gaps.

## Status legend

- ✅ **Implemented** — real, tested code; run it yourself.
- 🧩 **Partial** — a working subset that proves the architecture, not the
  full scope of that section.
- 🗺️ **Designed, deferred** — the interface/seam this would plug into
  exists and is documented, but no code yet.
- ⏭️ **Out of scope for this pass** — acknowledged, not attempted.

## Phase 1–27 coverage (spec section 110's development phases)

| Phase | System | Status | Where |
|---|---|---|---|
| 1–2 | Repo foundation, GameState | ✅ | `python/simulation/game_state.py` |
| 3 | ECS | ✅ | `python/simulation/ecs/` |
| 4–6 | World coordinates, terrain, procedural geography | ✅ | `python/simulation/world/terrain.py`, `worldgen.py` |
| 7 | Regions | 🧩 | `world/regions.py` — Region/Territory model; no political sub-simulation (rebellion, loyalty decay) beyond a `loyalty` field |
| 8 | Settlements | ✅ | `ecs/components.py: SettlementComp`, tier promotion in `population/population.py` |
| 9 | Buildings | 🧩 | `settlements/buildings.py` — definitions + construction queue; no procedural building meshes (that's a rendering concern, section 41) |
| 10 | Resources | ✅ | `economy/production.py`, node depletion on the terrain grid |
| 11 | Workers | 🧩 | Population's `workers_food`/`workers_industry` pools feed production directly (see README's "Known limitations"); no individual worker entities pathing to resource nodes — the design note in `production.py` explains the tradeoff |
| 12 | Population | ✅ | `population/population.py` — growth, consumption, happiness, starvation, tier promotion |
| 13 | Economy | ✅ | production + `economy/trade.py` market/route model |
| 14 | Technology | ✅ | `technology/tech_tree.py` — real multiplicative stat effects, loaded from YAML |
| 15 | Military | ✅ | `military/units.py`, `combat.py`, `movement.py` |
| 16 | Movement/Pathfinding | ✅ | `pathfinding/astar.py`, `military/movement.py` (supply/attrition) |
| 17 | Combat | ✅ | `military/combat.py` — attrition-model resolution with terrain/weather/formation modifiers |
| 18 | Sieges | ⏭️ | `SettlementComp.wall_health`/`wall_max` exist as fields; no breach/assault system yet |
| 19 | Heroes | 🧩 | `HeroComp` exists and is serializable; no ability system or hero-army linkage logic yet |
| 20 | AI | ✅ (rule-based) | `ai/faction_ai.py` — deterministic, observable strategic AI; see section 24/102 below |
| 21 | Diplomacy | 🧩 | `diplomacy/diplomacy.py` — war/peace/alliance state machine; no AI-driven diplomatic proposals yet (wars are scenario-scripted) |
| 22 | Trade | 🧩 | `economy/trade.py` — route + supply/demand market; not connected to AI trade-route creation |
| 23 | Weather | ✅ | `time/calendar.py: WeatherSystem` — seeded Markov chain, real movement/visibility/accuracy modifiers |
| 24 | History | ✅ | `history/chronicle.py` — subscribes to every notable `Event`, produces a readable timeline |
| 25 | Age transitions | ⏭️ | `Age` enum exists (`time/calendar.py`); no transition engine that transforms a settlement/world between ages yet |
| 26–27 | Campaigns, map/scenario editors | 🧩 / ⏭️ | One hand-authored scenario (`scenarios/rohan_frontier.py`) proves the campaign-assembly pattern; no visual editor |

## Why Python-first (section 65/66)

The brief itself specifies Python 3.13+ for the simulation/prototyping
layer and Rust/C++ for later performance-critical systems, with "clean
interfaces, don't prematurely rewrite." This repo follows that literally:

- `python/simulation/` is pure Python 3.11 (the available runtime) plus
  PyYAML for content loading — no numpy/pydantic/networkx dependency,
  deliberately, to keep the vertical slice runnable anywhere with zero
  friction. Swapping in numpy for `worldgen.py`'s elevation diffusion or
  Numba for `combat.py`'s hot loop is a localized change, not a rewrite,
  when the entity counts justify it.
- Every system is a plain class taking `World`/`Grid`/`EventBus` and
  exposing a `tick(...)` method with explicit, JSON-serializable
  component dataclasses. That is exactly the seam a native (Rust/C++)
  reimplementation of, say, `military/combat.py` or `pathfinding/astar.py`
  would need: same component shapes in, same component shapes out.

## What a rendering/multiplayer/editor layer would consume (🗺️ designed, deferred)

These are not implemented, but the simulation core is shaped so they can
attach without restructuring it:

- **Rendering** (`rendering/` — currently a placeholder). A renderer
  would read `World.query(Transform, ArmyComp, Owner)` etc. every frame
  and never write to it; `GameState.tick()` is the only writer, which is
  exactly the separation a GPU-instanced unit renderer or a settlement
  mesh generator needs. `TerrainCell` already carries everything a
  terrain mesh/heightmap generator would need (elevation, moisture,
  biome, resource nodes, roads).
- **Tactical battle rendering** (spec section 46 LEVEL 4/5). The seam is
  `military/combat.resolve_round`: it already takes the same
  terrain/weather context (section 78, terrain continuity) a tactical
  battle would need. A LEVEL 4/5 renderer would call into a richer
  per-unit combat resolver sharing that same terrain data instead of
  `resolve_round`'s aggregate attrition math.
- **Multiplayer** (`multiplayer/` — currently a placeholder). Section 63's
  architecture (CLIENT → COMMAND → AUTHORITATIVE SIMULATION → STATE
  REPLICATION) maps directly onto `GameState.submit_command` /
  `Command` / `GameState.tick()`: a network layer's only job would be
  serializing `Command` objects to/from clients and broadcasting
  `GameState.snapshot()` deltas — no simulation code would need to
  change.
- **Scenario/campaign editor** (spec sections 82-83). `scenarios/
  rohan_frontier.py` is what a scenario file *compiles to*; an editor
  would be a UI that writes the equivalent of that module's calls
  (`add_faction`, `_spawn_settlement`, region partitioning) from user
  input instead of Python source.
- **Native performance core** (spec section 66). `pathfinding/astar.py`
  and `military/combat.py` are the two obvious first candidates once
  entity counts grow past what pure Python handles at 60 FPS — both are
  self-contained, take only plain data in and out, and have no side
  effects beyond their return values (aside from mutating the
  ArmyComp/stack objects passed in), which is what makes them portable
  to a Rust extension without touching the rest of the engine.

## Determinism (section 62, tested in section 95)

`GameState` takes a single `seed`; every source of randomness in the
engine — worldgen, weather, AI tie-breaking, combat variance, retreat
direction — draws from `random.Random` instances seeded from that one
value (`GameState.rng`, `WeatherSystem`'s own seeded generator, etc.).
Nothing calls the global `random` module. `tests/test_determinism.py`
runs the full vertical-slice campaign for N ticks twice from the same
seed and asserts `GameState.canonical_json()` (a sorted-key JSON dump of
the full simulation state) is byte-identical, then does the same for a
long soak run to catch drift. This is what section 95 calls "the
critical test."

## Honest scope summary

Sections of the brief covering rendering fidelity (42-46, 74-80),
audio (80), modding UI (81-83), balance/Monte-Carlo tooling (84-85),
multiplayer netcode (63), and the Second/First/Fourth Age vertical
slices (97-99) are **not implemented**. They are acknowledged here rather
than silently dropped, and the simulation core's shape (data-driven
content, an event bus, deterministic ticks, plain serializable
components) was chosen specifically so none of that future work requires
rearchitecting what exists today.
