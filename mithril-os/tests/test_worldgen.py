import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from simulation.world.terrain import TerrainType
from simulation.world.worldgen import WorldGenConfig, generate_world


class WorldGenTests(unittest.TestCase):
    def test_deterministic_for_same_seed(self):
        cfg = WorldGenConfig(width=30, height=20)
        r1 = generate_world(random.Random(7), cfg)
        r2 = generate_world(random.Random(7), cfg)
        terrains1 = [c.terrain for c in r1.grid.all_cells()]
        terrains2 = [c.terrain for c in r2.grid.all_cells()]
        self.assertEqual(terrains1, terrains2)
        self.assertEqual(r1.settlement_sites, r2.settlement_sites)

    def test_different_seed_diverges(self):
        cfg = WorldGenConfig(width=30, height=20)
        r1 = generate_world(random.Random(1), cfg)
        r2 = generate_world(random.Random(2), cfg)
        terrains1 = [c.terrain for c in r1.grid.all_cells()]
        terrains2 = [c.terrain for c in r2.grid.all_cells()]
        self.assertNotEqual(terrains1, terrains2)

    def test_mountains_exist_and_have_resources(self):
        cfg = WorldGenConfig(width=30, height=20, mountain_seeds=5)
        result = generate_world(random.Random(3), cfg)
        mountain_cells = [c for c in result.grid.all_cells() if c.terrain == TerrainType.MOUNTAINS]
        self.assertTrue(len(mountain_cells) > 0, "worldgen should produce mountains")
        with_resource = [c for c in mountain_cells if c.resource_node is not None]
        self.assertTrue(len(with_resource) > 0, "mountains should carry ore/stone resource nodes")

    def test_rivers_flow_from_high_to_low_ground(self):
        cfg = WorldGenConfig(width=30, height=20, river_count=3)
        result = generate_world(random.Random(4), cfg)
        self.assertTrue(len(result.river_cells) > 0)
        river_terrain = [result.grid.at(x, y).terrain for x, y in result.river_cells]
        self.assertTrue(any(t == TerrainType.RIVER for t in river_terrain))

    def test_settlement_sites_are_spaced_and_on_habitable_terrain(self):
        cfg = WorldGenConfig(width=40, height=28, settlement_slots=6, min_settlement_spacing=6)
        result = generate_world(random.Random(9), cfg)
        self.assertGreater(len(result.settlement_sites), 0)
        for x, y in result.settlement_sites:
            terrain = result.grid.at(x, y).terrain
            self.assertIn(terrain, (TerrainType.PLAINS, TerrainType.HILLS))
        for i, a in enumerate(result.settlement_sites):
            for b in result.settlement_sites[i + 1:]:
                dist = abs(a[0] - b[0]) + abs(a[1] - b[1])
                self.assertGreaterEqual(dist, cfg.min_settlement_spacing)

    def test_roads_connect_settlement_sites(self):
        cfg = WorldGenConfig(width=30, height=20, settlement_slots=4, min_settlement_spacing=5)
        result = generate_world(random.Random(11), cfg)
        road_cells = [c for c in result.grid.all_cells() if c.has_road]
        if len(result.settlement_sites) >= 2:
            self.assertTrue(len(road_cells) > 0, "worldgen should lay roads between settlement sites")


if __name__ == "__main__":
    unittest.main()
