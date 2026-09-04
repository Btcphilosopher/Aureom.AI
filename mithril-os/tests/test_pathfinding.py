import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from simulation.pathfinding.astar import find_path, path_cost
from simulation.world.terrain import Grid, TerrainType


class PathfindingTests(unittest.TestCase):
    def test_straight_line_on_plains(self):
        grid = Grid(10, 10)
        path = find_path(grid, (0, 0), (5, 0))
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (5, 0))

    def test_avoids_impassable_water(self):
        grid = Grid(5, 5)
        # Block a column but leave a gap at the bottom so a route around
        # the water still exists.
        for y in range(4):
            grid.at(2, y).terrain = TerrainType.WATER
        path = find_path(grid, (0, 2), (4, 2))
        self.assertTrue(path, "should find a way around the water")
        for x, y in path:
            self.assertNotEqual(grid.at(x, y).terrain, TerrainType.WATER)

    def test_returns_empty_when_fully_blocked(self):
        grid = Grid(3, 3)
        for y in range(3):
            grid.at(1, y).terrain = TerrainType.WATER
        path = find_path(grid, (0, 1), (2, 1))
        self.assertEqual(path, [])

    def test_road_reduces_path_cost(self):
        grid = Grid(10, 1)
        no_road_cost = path_cost(grid, find_path(grid, (0, 0), (9, 0)))
        for x in range(10):
            grid.at(x, 0).has_road = True
        road_cost = path_cost(grid, find_path(grid, (0, 0), (9, 0)))
        self.assertLess(road_cost, no_road_cost)

    def test_mountains_cost_more_than_plains(self):
        grid = Grid(3, 1)
        grid.at(1, 0).terrain = TerrainType.MOUNTAINS
        mountain_cost = grid.movement_cost(1, 0)
        plains_cost = grid.movement_cost(0, 0)
        self.assertGreater(mountain_cost, plains_cost)


if __name__ == "__main__":
    unittest.main()
