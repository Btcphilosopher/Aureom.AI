import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from simulation.ecs.components import ArmyComp, UnitStack
from simulation.military.combat import resolve_round
from simulation.military.units import UnitCatalogue, UnitDefinition
from simulation.world.terrain import TerrainType


def _catalogue():
    return UnitCatalogue([
        UnitDefinition(unit_id="strong", name="Strong", category="INFANTRY", health=50, armour=10,
                       attack=20, defence=15, speed=2.0, attack_range=0, accuracy=0.7, morale=70),
        UnitDefinition(unit_id="weak", name="Weak", category="INFANTRY", health=20, armour=2,
                       attack=5, defence=3, speed=2.0, attack_range=0, accuracy=0.5, morale=40),
        UnitDefinition(unit_id="cavalry", name="Cavalry", category="CAVALRY", health=60, armour=8,
                       attack=16, defence=10, speed=4.0, attack_range=0, accuracy=0.6, morale=70,
                       is_cavalry=True),
    ])


class CombatTests(unittest.TestCase):
    def test_stronger_army_tends_to_win(self):
        catalogue = _catalogue()
        rng = random.Random(1)
        attacker = ArmyComp(name="A", stacks=[UnitStack(unit_type="strong", count=40)])
        defender = ArmyComp(name="B", stacks=[UnitStack(unit_type="weak", count=40)])

        winner = None
        for _ in range(50):
            result = resolve_round(attacker, defender, catalogue, TerrainType.PLAINS, 1.0, rng)
            if result.winner in ("attacker", "defender", "draw"):
                winner = result.winner
                break
        self.assertEqual(winner, "attacker")

    def test_terrain_defence_bonus_helps_defender(self):
        catalogue = _catalogue()

        def run_on(terrain):
            rng = random.Random(5)
            attacker = ArmyComp(name="A", stacks=[UnitStack(unit_type="strong", count=25)])
            defender = ArmyComp(name="B", stacks=[UnitStack(unit_type="strong", count=25)])
            for _ in range(30):
                result = resolve_round(attacker, defender, catalogue, terrain, 1.0, rng)
                if result.winner != "ongoing":
                    break
            return defender.total_units()

        plains_survivors = run_on(TerrainType.PLAINS)
        mountain_survivors = run_on(TerrainType.MOUNTAINS)
        self.assertGreaterEqual(mountain_survivors, plains_survivors)

    def test_cavalry_penalised_in_mountains(self):
        catalogue = _catalogue()

        def defender_units_after_one_round(terrain):
            attacker = ArmyComp(name="A", stacks=[UnitStack(unit_type="cavalry", count=30)])
            defender = ArmyComp(name="B", stacks=[UnitStack(unit_type="weak", count=30)])
            resolve_round(attacker, defender, catalogue, terrain, 1.0, random.Random(3))
            return defender.total_units()

        survivors_mountains = defender_units_after_one_round(TerrainType.MOUNTAINS)
        survivors_plains = defender_units_after_one_round(TerrainType.PLAINS)
        # Cavalry's attack power is scaled down in mountains, so the
        # defender should come out of one round better off there than on
        # open plains.
        self.assertGreaterEqual(survivors_mountains, survivors_plains)

    def test_losses_never_negative(self):
        catalogue = _catalogue()
        rng = random.Random(2)
        attacker = ArmyComp(name="A", stacks=[UnitStack(unit_type="strong", count=5)])
        defender = ArmyComp(name="B", stacks=[UnitStack(unit_type="weak", count=5)])
        for _ in range(20):
            resolve_round(attacker, defender, catalogue, TerrainType.PLAINS, 1.0, rng)
            for stack in attacker.stacks + defender.stacks:
                self.assertGreaterEqual(stack.count, 0)


if __name__ == "__main__":
    unittest.main()
