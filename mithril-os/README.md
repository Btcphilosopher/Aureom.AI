# MITHRIL.OS

A world-simulation engine for a real-time + grand strategy game set across
the Ages of a Tolkien-inspired Middle-earth — the map is not a background,
it is the simulation: geography drives resources, resources drive
population, population drives economy, economy drives military, military
and diplomacy drive territory, and territory changes become recorded
history.

## What this is, honestly

The design brief behind this repository (see the original task
description) specifies a full AAA game engine: native rendering, GPU
instancing, multiplayer netcode, a scenario/campaign editor suite, four
playable Ages, and dozens of interlocking simulation systems. That is a
multi-year, multi-discipline project. This repository does **not** claim
to be that finished product.

What it *is*: a working, deterministic **Python simulation core** that
implements the spec's central architectural claim — a causal chain from
geography through to history — end to end, for a real vertical slice
(section 96 of the brief explicitly calls for exactly this: *"Do NOT
attempt the entire game immediately. Build vertical slice."*). Every
system below is real code, not a stub: it runs, it's tested, and it
produces emergent behaviour (wars start, armies rout and rally, food
shortages depress happiness and growth, settlements grow through tiers).

Rendering, native performance layers, multiplayer replication, and the
in-editor tools are architected for (clean interfaces, a documented
extension path) but not implemented — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for exactly what's real
today versus what's designed-but-deferred, and why.

## Quick start

```bash
cd mithril-os
pip install pyyaml     # only third-party dependency
python3 tools/run_campaign.py --ticks 200 --seed 42
```

This runs the **Rohan / Gondor / Isengard frontier** vertical slice
headlessly: three factions, ten unit types, six buildings, five core
resources, procedurally generated terrain (mountains, rivers, forests,
roads), population growth, an economy, a rule-based strategic AI, and
real-time-abstracted combat — for 200 simulated days — then prints a
state report and the chronicle of everything that happened.

### Run the tests

```bash
cd mithril-os
python3 -m unittest discover -s tests -v
```

34 tests cover world generation, the ECS, pathfinding, the economy,
population, combat, diplomacy, save/load, and — the critical one per the
spec's own testing section — **determinism**: `tests/test_determinism.py`
runs the full campaign for N ticks twice from the same seed and asserts
the resulting world states are byte-identical. Tune the tick counts with
`MITHRIL_DETERMINISM_TICKS` / `MITHRIL_SOAK_TICKS` env vars to run the
full 10,000-tick soak test the spec calls for.

## Architecture at a glance

```
mithril-os/
  python/simulation/     # the real, working engine (pure Python 3.11 + PyYAML)
    ecs/                 # entities, components, World container
    events/               # EventBus — every state change is an Event
    world/                # terrain grid, procedural worldgen, regions, factions
    time/                 # calendar, ages, seasons, weather
    economy/               # production, resource depletion, trade/market
    population/            # growth, consumption, settlement tier promotion
    settlements/            # buildings, construction queue
    military/                # unit stats, formations, combat, movement/supply
    technology/               # data-driven tech tree with real stat effects
    diplomacy/                 # war/peace/alliance state machine
    ai/                         # rule-based strategic faction AI
    history/                     # the Chronicle — the world's memory
    pathfinding/                   # terrain- and road-aware A*
    persistence/                    # deterministic save/load
    scenarios/                       # the Rohan/Gondor/Isengard vertical slice
    game_state.py                     # GameState: the authoritative object + tick loop
  content/                # data-driven factions/units/buildings/technologies (YAML)
  tools/run_campaign.py   # headless CLI runner
  tests/                  # 34 unit + integration tests, incl. determinism
  docs/ARCHITECTURE.md    # full spec-to-implementation map + roadmap
  engine/ rendering/ multiplayer/   # placeholders documenting the native/
                                     # GPU/netcode layers this Python core
                                     # is designed to hand off to (not yet
                                     # implemented — see ARCHITECTURE.md)
```

## What's genuinely emergent right now

Play with `tools/run_campaign.py` and you'll see, without any of it being
scripted:

- Isengard's economy (iron-heavy, forced-labour modifiers) produces a
  different growth curve than Rohan's (food/horse-breeding) or Gondor's
  (stone/fortification) from the *same* engine code, driven entirely by
  their data-driven `FactionDefinition`s.
- Rivers generated by steepest-descent from mountain peaks raise
  moisture, which places forests, which sets fertility, which is what the
  settlement-siting algorithm actually optimises for — geography has
  downstream strategic consequences, not just a paint layer.
- A routed army's morale collapses, it breaks contact, and it recovers
  supply and morale over time before it can fight again — combat has
  consequences beyond the single tick it happens in.
- Every one of those events — wars declared, battles fought, settlements
  promoted, armies destroyed — is recorded in `gs.chronicle`, a
  chronological world history that a future "historical time machine" UI
  (spec section 88) would read directly.

## Known limitations (read before extending)

- **The economy is wired but not balance-tuned.** `PopulationSystem`
  allocates each settlement's population into `workers_food` /
  `workers_industry` pools, and `ProductionSystem` splits those pools
  across that settlement's buildings each tick — so production genuinely
  scales with population (a bigger town really does farm more), not a
  fixed per-building rate. What's still missing is the actual balance
  pass: run the vertical slice for a few hundred ticks today and every
  settlement's economy grows without bound once it hits the population
  housing cap (resources pile up with nothing spending them beyond
  upkeep and recruitment). That's expected — spec section 84's "Balance
  Laboratory" (Monte-Carlo tuning across thousands of runs) is exactly
  the tool this needs and is not built yet. The causal wiring is real;
  the numbers are not tuned.
- **Combat is strategic-fidelity only.** There is no LEVEL 4/5 tactical
  battle renderer (spec section 46); `military/combat.py` resolves an
  entire engagement via an attrition model. The seam for a future
  tactical layer is `resolve_round`'s terrain/weather context, which is
  the same data a tactical battle would need (spec section 78: terrain
  continuity).
- **AI is rule-based, not learned**, and only drives one army per
  faction. It is deliberately legible (spec section 102: AI
  observability) rather than sophisticated.
- **No rendering, no multiplayer, no editors.** See
  `docs/ARCHITECTURE.md` for what's designed and why those are
  deliberately out of scope for this pass.

## Content & legal note (spec section 112)

Faction/unit/building/technology data in `content/` uses original stat
values and original faction descriptions; it draws on Tolkien-inspired
place names and archetypes (Rohan, Gondor, Isengard) purely as
descriptive/geographic labels, the same way countless strategy games and
mods reference historical or literary settings. No film assets, film
music, or copyrighted text are embedded anywhere in this repository. The
engine (`python/simulation/`) is fully generic — nothing in it hard-codes
Middle-earth; a different `content/` directory produces a different
world.
