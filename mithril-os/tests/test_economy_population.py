import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from simulation.ecs.core import World
from simulation.ecs.components import PopulationComp, ProductionComp, ResourceStock, SettlementComp, SettlementTier
from simulation.economy.production import ProductionSystem
from simulation.events.bus import EventBus
from simulation.population.population import PopulationSystem
from simulation.world.terrain import Grid


class ProductionTests(unittest.TestCase):
    def test_production_accumulates_into_settlement_stock(self):
        world = World()
        bus = EventBus()
        grid = Grid(5, 5)
        settlement = world.create_entity("settlement")
        world.add(settlement, ResourceStock(amounts={"FOOD": 0.0}))
        farm = world.create_entity("building")
        world.add(farm, ProductionComp(building_type="farm", output_resource="FOOD", base_rate=1.0, settlement_id=settlement, workers_assigned=10.0))

        system = ProductionSystem(world, grid, bus)
        system.tick(tick_no=0, year=0, day=0, season_food_mult=1.0, weather_construction_mult=1.0)

        stock = world.get(settlement, ResourceStock)
        self.assertAlmostEqual(stock.get("FOOD"), 10.0)

    def test_resource_node_depletes_and_publishes_event(self):
        world = World()
        bus = EventBus()
        grid = Grid(3, 3)
        cell = grid.at(1, 1)
        cell.resource_node = "IRON"
        cell.resource_quantity = 5.0

        events = []
        bus.subscribe_all(lambda e: events.append(e))

        system = ProductionSystem(world, grid, bus)
        system.deplete_node(1, 1, 3.0, tick_no=0, year=0, day=0)
        self.assertEqual(cell.resource_quantity, 2.0)
        system.deplete_node(1, 1, 10.0, tick_no=0, year=0, day=0)
        self.assertIsNone(cell.resource_node)
        self.assertTrue(any(e.type == "RESOURCE_DEPLETED" for e in events))


class PopulationTests(unittest.TestCase):
    def _make_settlement(self, world, food):
        eid = world.create_entity("settlement")
        world.add(eid, SettlementComp(name="Test Town", tier=SettlementTier.VILLAGE, happiness=60.0))
        world.add(eid, PopulationComp(count=100.0, growth_rate=0.05, housing_capacity=1000.0))
        world.add(eid, ResourceStock(amounts={"FOOD": food}))
        return eid

    def test_population_grows_with_food_surplus(self):
        world = World()
        bus = EventBus()
        eid = self._make_settlement(world, food=1000.0)
        system = PopulationSystem(world, bus)
        before = world.get(eid, PopulationComp).count
        for _ in range(5):
            system.tick(tick_no=0, year=0, day=0)
        after = world.get(eid, PopulationComp).count
        self.assertGreater(after, before)

    def test_population_starves_without_food(self):
        world = World()
        bus = EventBus()
        eid = self._make_settlement(world, food=0.0)
        system = PopulationSystem(world, bus)
        before = world.get(eid, PopulationComp).count
        for _ in range(10):
            system.tick(tick_no=0, year=0, day=0)
        after = world.get(eid, PopulationComp).count
        settlement = world.get(eid, SettlementComp)
        self.assertLess(after, before)
        self.assertLess(settlement.happiness, 60.0)

    def test_settlement_promotes_tier_on_population_growth(self):
        world = World()
        bus = EventBus()
        eid = world.create_entity("settlement")
        world.add(eid, SettlementComp(name="Growing Town", tier=SettlementTier.VILLAGE, happiness=90.0))
        world.add(eid, PopulationComp(count=290.0, growth_rate=0.05, housing_capacity=5000.0))
        world.add(eid, ResourceStock(amounts={"FOOD": 5000.0}))
        system = PopulationSystem(world, bus)
        for _ in range(5):
            system.tick(tick_no=0, year=0, day=0)
        settlement = world.get(eid, SettlementComp)
        self.assertNotEqual(settlement.tier, SettlementTier.VILLAGE)


if __name__ == "__main__":
    unittest.main()
