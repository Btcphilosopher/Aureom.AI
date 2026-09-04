import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from simulation.ecs.core import World
from simulation.ecs.components import Health, Owner, Transform


class ECSTests(unittest.TestCase):
    def test_create_add_get(self):
        world = World()
        eid = world.create_entity("unit")
        world.add(eid, Transform(x=1, y=2))
        world.add(eid, Health(current=10, maximum=10))
        self.assertEqual(world.get(eid, Transform).x, 1)
        self.assertTrue(world.has(eid, Health))
        self.assertFalse(world.has(eid, Owner))

    def test_query_requires_all_components(self):
        world = World()
        a = world.create_entity("unit")
        b = world.create_entity("unit")
        world.add(a, Transform(x=0, y=0))
        world.add(a, Health(current=5, maximum=5))
        world.add(b, Transform(x=1, y=1))  # no Health

        results = list(world.query(Transform, Health))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], a)

    def test_query_ordered_by_entity_id(self):
        world = World()
        ids = [world.create_entity("unit") for _ in range(5)]
        for eid in reversed(ids):
            world.add(eid, Transform(x=eid, y=eid))
        result_ids = [row[0] for row in world.query(Transform)]
        self.assertEqual(result_ids, sorted(result_ids))

    def test_destroy_entity_removes_components(self):
        world = World()
        eid = world.create_entity("unit")
        world.add(eid, Transform(x=0, y=0))
        world.destroy_entity(eid)
        self.assertFalse(world.is_alive(eid))
        self.assertIsNone(world.get(eid, Transform))
        self.assertEqual(list(world.query(Transform)), [])

    def test_require_raises_when_missing(self):
        world = World()
        eid = world.create_entity("unit")
        with self.assertRaises(KeyError):
            world.require(eid, Transform)


if __name__ == "__main__":
    unittest.main()
