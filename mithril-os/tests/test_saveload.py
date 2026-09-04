"""
Spec ref: 60 (campaign save system).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from simulation.ecs.components import ArmyComp, Owner, PopulationComp, ResourceStock, SettlementComp, Transform
from simulation.persistence.save import world_from_dict, world_to_dict
from simulation.scenarios.rohan_frontier import build_campaign


class SaveLoadTests(unittest.TestCase):
    def test_world_round_trip_preserves_components(self):
        gs = build_campaign(seed=999)
        for _ in range(30):
            gs.tick()

        data = world_to_dict(gs.world)
        restored = world_from_dict(data)

        original_settlements = sorted(
            (eid, s.name, round(pop.count, 6))
            for eid, s, pop in gs.world.query(SettlementComp, PopulationComp)
        )
        restored_settlements = sorted(
            (eid, s.name, round(pop.count, 6))
            for eid, s, pop in restored.query(SettlementComp, PopulationComp)
        )
        self.assertEqual(original_settlements, restored_settlements)

        original_armies = sorted(
            (eid, a.name, a.total_units(), owner.faction_id)
            for eid, a, owner in gs.world.query(ArmyComp, Owner)
        )
        restored_armies = sorted(
            (eid, a.name, a.total_units(), owner.faction_id)
            for eid, a, owner in restored.query(ArmyComp, Owner)
        )
        self.assertEqual(original_armies, restored_armies)

    def test_snapshot_is_valid_json_and_stable(self):
        gs = build_campaign(seed=42)
        for _ in range(10):
            gs.tick()
        json_a = gs.canonical_json()
        json_b = gs.canonical_json()
        self.assertEqual(json_a, json_b)
        self.assertGreater(len(json_a), 100)


if __name__ == "__main__":
    unittest.main()
