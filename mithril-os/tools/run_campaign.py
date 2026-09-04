#!/usr/bin/env python3
"""
Headless campaign runner.

Spec ref: 96 (first playable build), 101 (debug mode — this is the
text-console ancestor of a future in-engine debug overlay).

Usage:
    python3 tools/run_campaign.py --ticks 200 --seed 42
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from simulation.scenarios.rohan_frontier import build_campaign  # noqa: E402
from simulation.ecs.components import ArmyComp, Owner, PopulationComp, ResourceStock, SettlementComp, Transform  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MITHRIL.OS Rohan/Gondor/Isengard frontier vertical slice headlessly.")
    parser.add_argument("--ticks", type=int, default=200)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--report-every", type=int, default=50)
    args = parser.parse_args()

    gs = build_campaign(seed=args.seed) if args.seed is not None else build_campaign()

    print(f"=== MITHRIL.OS :: Rohan/Gondor/Isengard Frontier (seed={gs.seed}) ===")
    print(f"World: {gs.grid.width}x{gs.grid.height} | Age: {gs.calendar.age.value} | Year: {gs.calendar.year}")
    print(f"Factions: {', '.join(sorted(gs.factions))}")
    print()

    for i in range(args.ticks):
        gs.tick()
        if (i + 1) % args.report_every == 0:
            _report(gs)

    print("\n=== Final report ===")
    _report(gs)

    print("\n=== Chronicle (last 20 entries) ===")
    for entry in gs.chronicle.entries[-20:]:
        print(f"[Year {entry.year}, Day {entry.day}] {entry.description}")


def _report(gs) -> None:
    print(f"-- Tick {gs.calendar.tick} | Year {gs.calendar.year} Day {gs.calendar.day_of_year} | "
          f"Season {gs.calendar.season.value} | Weather {gs.weather.state.value} --")
    for eid, settlement, pop, stock, owner in gs.world.query(SettlementComp, PopulationComp, ResourceStock, Owner):
        print(
            f"  [{owner.faction_id:9s}] {settlement.name:16s} tier={settlement.tier.value:14s} "
            f"pop={pop.count:7.1f} happiness={settlement.happiness:5.1f} "
            f"food={stock.get('FOOD'):7.1f} wood={stock.get('WOOD'):7.1f} "
            f"stone={stock.get('STONE'):7.1f} iron={stock.get('IRON'):7.1f} gold={stock.get('GOLD'):7.1f}"
        )
    for eid, army, pos, owner in gs.world.query(ArmyComp, Transform, Owner):
        print(f"  [{owner.faction_id:9s}] Army '{army.name}' at ({pos.x},{pos.y}) units={army.total_units()} morale={army.morale:5.1f} supply={army.supply:5.1f}")


if __name__ == "__main__":
    main()
