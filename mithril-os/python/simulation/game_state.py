"""
GameState — the canonical, authoritative simulation object.

Spec ref: 92 (canonical game state), 93 (simulation loop), 94 (state
validation), 62 (deterministic simulation).

GameState owns everything: the world, factions, all systems, the RNG.
Nothing outside `tick()` is allowed to mutate simulation state on its own
schedule — commands queue up and are drained at the start of a tick, which
is what makes replay (section 61) and multiplayer's authoritative-server
model (section 63) both trivially compatible with this same loop.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .ai.faction_ai import FactionAI
from .diplomacy.diplomacy import DiplomacyEngine
from .ecs.core import World
from .ecs.components import ArmyComp, Owner, PopulationComp, ProductionComp, ResourceStock, SettlementComp, Transform
from .economy.production import ProductionSystem
from .economy.trade import TradeEngine
from .events.bus import Event, EventBus
from .events import bus as event_types
from .history.chronicle import Chronicle
from .military.combat import resolve_round
from .military.movement import MovementSystem
from .military.units import UnitCatalogue
from .population.population import PopulationSystem
from .settlements.buildings import ConstructionSystem
from .technology.tech_tree import TechTree
from .time.calendar import Age, Calendar, SEASON_MODIFIERS, WeatherSystem, WEATHER_MODIFIERS
from .world.faction import Faction, FactionDefinition
from .world.regions import Region
from .world.terrain import Grid, TerrainType


@dataclass
class Command:
    """A player or AI intent, queued and applied deterministically at the
    start of the next tick (section 93: INPUT -> COMMAND QUEUE -> ...)."""
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)


class ValidationError(RuntimeError):
    pass


class GameState:
    def __init__(
        self,
        seed: int,
        age: Age,
        grid: Grid,
        unit_catalogue: UnitCatalogue,
        tech_tree: TechTree,
        start_year: int = 3000,
    ) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.grid = grid
        self.world = World()
        self.bus = EventBus()
        self.chronicle = Chronicle(self.bus)
        self.calendar = Calendar(age=age, year=start_year)
        self.weather = WeatherSystem(random.Random(seed ^ 0x5EED))
        self.regions: Dict[str, Region] = {}
        self.factions: Dict[str, Faction] = {}
        self.diplomacy = DiplomacyEngine()
        self.trade = TradeEngine()
        self.unit_catalogue = unit_catalogue
        self.tech_tree = tech_tree

        self.production = ProductionSystem(self.world, self.grid, self.bus)
        self.population = PopulationSystem(self.world, self.bus)
        self.movement = MovementSystem(self.world, self.grid)
        self.construction = ConstructionSystem()
        self.ai = FactionAI(self.world, random.Random(seed ^ 0xA1))

        self.command_queue: List[Command] = []
        self._ai_command_hooks: List[Callable[["GameState"], List[Command]]] = []

    # -- faction / entity setup helpers -----------------------------------

    def add_faction(self, definition: FactionDefinition, starting_treasury: Optional[Dict[str, float]] = None) -> Faction:
        faction = Faction(definition=definition, treasury=dict(starting_treasury or {}))
        for tech_id in definition.starting_technologies:
            faction.researched_technologies.append(tech_id)
            faction.tech_modifiers = self.tech_tree.apply_effects(tech_id, faction.tech_modifiers)
        self.factions[faction.faction_id] = faction
        return faction

    def submit_command(self, command: Command) -> None:
        self.command_queue.append(command)

    def register_ai_hook(self, hook: Callable[["GameState"], List[Command]]) -> None:
        """AI decision-making produces commands rather than mutating state
        directly, keeping AI and player input symmetric (both just enqueue
        Commands) per section 93's INPUT -> COMMAND QUEUE stage."""
        self._ai_command_hooks.append(hook)

    # -- the simulation loop (section 93) ----------------------------------

    def tick(self) -> None:
        tick_no = self.calendar.tick
        year, day = self.calendar.year, self.calendar.day_of_year
        season = self.calendar.season
        season_mods = SEASON_MODIFIERS[season]
        weather_mods = WEATHER_MODIFIERS[self.weather.state]

        # 1. INPUT / COMMAND QUEUE
        self._drain_commands(tick_no, year, day)

        # 2. ECONOMIC UPDATE
        self.production.tick(tick_no, year, day, season_mods["food"], weather_mods["movement"])

        # 3. POPULATION UPDATE
        self.population.tick(tick_no, year, day)

        # 4. RESOURCE UPDATE (trade / market)
        self.trade.market.reset_tick()
        self.trade.tick()

        # 5. AI UPDATE — AI hooks append Commands for *next* tick, keeping
        # this tick's outcome independent of hook execution order beyond
        # the deterministic order hooks were registered in.
        for hook in self._ai_command_hooks:
            for cmd in hook(self):
                self.command_queue.append(cmd)

        # 6. MOVEMENT
        self.movement.tick(season_mods["movement"] * weather_mods["movement"])

        # 7. COMBAT — armies of warring factions sharing a cell fight.
        self._resolve_combats(tick_no, year, day, weather_mods["ranged_accuracy"])

        # 8. DIPLOMACY — handled reactively via commands (declare_war,
        # sign_peace); nothing periodic required at vertical-slice scope.

        # 9. WEATHER
        self.weather.step(season)

        # 10. WORLD EVENTS — hook point for section 59's large-scale
        # events; none scripted at vertical-slice scope.

        # 11. HISTORY — the Chronicle already recorded everything above via
        # its EventBus subscription; nothing to do here explicitly.

        # 12. STATE VALIDATION
        self.validate()

        # 13. RENDER — headless in this prototype; a rendering client would
        # read GameState/World here without mutating it.

        self.calendar.advance(hours=24)  # one simulation tick == one day at strategic scale

    def _drain_commands(self, tick_no: int, year: int, day: int) -> None:
        queue, self.command_queue = self.command_queue, []
        for cmd in queue:
            self._apply_command(cmd, tick_no, year, day)

    def _apply_command(self, cmd: Command, tick_no: int, year: int, day: int) -> None:
        if cmd.type == "MOVE_ARMY":
            eid = cmd.payload["army_id"]
            dest = tuple(cmd.payload["destination"])
            self.movement.set_destination(eid, dest)
        elif cmd.type == "DECLARE_WAR":
            a, b = cmd.payload["a"], cmd.payload["b"]
            self.diplomacy.declare_war(a, b)
            fa, fb = self.factions[a], self.factions[b]
            if b not in fa.at_war_with:
                fa.at_war_with.append(b)
            if a not in fb.at_war_with:
                fb.at_war_with.append(a)
            self.bus.publish(Event(event_types.WAR_DECLARED, {"faction": a, "enemy": b}, tick_no, year, day))
        elif cmd.type == "SIGN_PEACE":
            a, b = cmd.payload["a"], cmd.payload["b"]
            self.diplomacy.sign_peace(a, b)
            fa, fb = self.factions[a], self.factions[b]
            if b in fa.at_war_with:
                fa.at_war_with.remove(b)
            if a in fb.at_war_with:
                fb.at_war_with.remove(a)
            self.bus.publish(Event(event_types.PEACE_SIGNED, {"faction": a, "enemy": b}, tick_no, year, day))
        else:
            raise ValidationError(f"unknown command type: {cmd.type}")

    def _resolve_combats(self, tick_no: int, year: int, day: int, weather_accuracy_mult: float) -> None:
        armies_by_cell: Dict[Tuple[int, int], List[int]] = {}
        for eid, army, pos, owner in self.world.query(ArmyComp, Transform, Owner):
            armies_by_cell.setdefault((pos.x, pos.y), []).append(eid)

        for cell, eids in armies_by_cell.items():
            if len(eids) < 2:
                continue
            factions_present = {self.world.require(e, Owner).faction_id for e in eids}
            warring_pairs = [
                (a, b) for a in factions_present for b in factions_present
                if a < b and self.diplomacy.at_war(a, b)
            ]
            if not warring_pairs:
                continue

            terrain = self.grid.at(*cell).terrain
            eids_by_faction: Dict[str, List[int]] = {}
            for e in eids:
                eids_by_faction.setdefault(self.world.require(e, Owner).faction_id, []).append(e)

            for a, b in warring_pairs:
                for aid in eids_by_faction.get(a, []):
                    for bid in eids_by_faction.get(b, []):
                        attacker = self.world.get(aid, ArmyComp)
                        defender = self.world.get(bid, ArmyComp)
                        if attacker is None or defender is None:
                            continue
                        if not attacker.stacks or not defender.stacks:
                            continue
                        self.bus.publish(Event(event_types.BATTLE_STARTED, {"location": str(cell)}, tick_no, year, day))
                        result = resolve_round(attacker, defender, self.unit_catalogue, terrain, weather_accuracy_mult, self.rng)
                        if result.winner in ("attacker", "defender", "draw"):
                            self.bus.publish(Event(
                                event_types.BATTLE_ENDED,
                                {"location": str(cell), "outcome": result.winner},
                                tick_no, year, day,
                            ))
                            if result.winner == "attacker" and not defender.stacks:
                                self.world.destroy_entity(bid)
                                self.bus.publish(Event(event_types.ARMY_DESTROYED, {"army": defender.name, "faction": b}, tick_no, year, day))
                            elif result.winner == "defender" and not attacker.stacks:
                                self.world.destroy_entity(aid)
                                self.bus.publish(Event(event_types.ARMY_DESTROYED, {"army": attacker.name, "faction": a}, tick_no, year, day))
                            else:
                                # A rout that didn't wipe out the losing
                                # side still has to end the engagement —
                                # otherwise a routed-but-alive army would
                                # refight the same battle every tick
                                # forever. Break contact by displacing the
                                # routed side(s) to a free neighbouring
                                # cell and letting morale begin recovering.
                                if result.attacker_routed and attacker.stacks:
                                    self._break_contact(aid, cell)
                                    attacker.morale = 20.0
                                if result.defender_routed and defender.stacks:
                                    self._break_contact(bid, cell)
                                    defender.morale = 20.0

    def _break_contact(self, army_eid: int, cell: Tuple[int, int]) -> None:
        pos = self.world.get(army_eid, Transform)
        if pos is None:
            return
        candidates = [
            c for c in self.grid.neighbors4(*cell)
            if self.grid.movement_cost(*c) != float("inf")
        ]
        if not candidates:
            return
        candidates.sort()  # deterministic ordering before the rng pick
        choice = self.rng.choice(candidates)
        pos.x, pos.y = choice
        army = self.world.get(army_eid, ArmyComp)
        if army is not None:
            army.path = []
            army.destination = None

    # -- validation (section 94) ------------------------------------------

    def validate(self) -> None:
        for eid, pop in self.world.query(PopulationComp):
            if pop.count < 0:
                raise ValidationError(f"population went negative on entity {eid}")
        for eid, stock in self.world.query(ResourceStock):
            for resource, qty in stock.amounts.items():
                if qty < -1e-6:
                    raise ValidationError(f"resource {resource} negative on entity {eid}")
        for eid, army in self.world.query(ArmyComp):
            if army.total_units() < 0:
                raise ValidationError(f"army {eid} has negative unit count")
        for a, faction in self.factions.items():
            for enemy in faction.at_war_with:
                if enemy not in self.factions:
                    raise ValidationError(f"faction {a} at war with unknown faction {enemy}")

    # -- serialization (section 60/62) -------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """A deterministic, JSON-serializable dict of the full state.
        Used both for save/load and for the determinism regression test
        (section 95: run N ticks twice with the same seed, states must
        match)."""
        from .persistence.save import world_to_dict

        grid_dict = {
            "width": self.grid.width, "height": self.grid.height,
            "cells": [c.to_dict() for c in self.grid.all_cells()],
        }
        return {
            "seed": self.seed,
            "calendar": {
                "age": self.calendar.age.value, "year": self.calendar.year,
                "day_of_year": self.calendar.day_of_year, "hour": self.calendar.hour,
                "tick": self.calendar.tick,
            },
            "weather": self.weather.state.value,
            "grid": grid_dict,
            "world": world_to_dict(self.world),
            "factions": {
                fid: {
                    "treasury": dict(f.treasury),
                    "researched_technologies": list(f.researched_technologies),
                    "at_war_with": sorted(f.at_war_with),
                    "allied_with": sorted(f.allied_with),
                    "is_alive": f.is_alive,
                }
                for fid, f in sorted(self.factions.items())
            },
            "chronicle": self.chronicle.to_dict(),
        }

    def canonical_json(self) -> str:
        return json.dumps(self.snapshot(), sort_keys=True)
