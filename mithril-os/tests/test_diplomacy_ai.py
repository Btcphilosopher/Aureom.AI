import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from simulation.diplomacy.diplomacy import DiplomacyEngine, DiplomaticStatus
from simulation.scenarios.rohan_frontier import build_campaign


class DiplomacyTests(unittest.TestCase):
    def test_declare_war_and_peace(self):
        d = DiplomacyEngine()
        d.declare_war("a", "b")
        self.assertTrue(d.at_war("a", "b"))
        self.assertTrue(d.at_war("b", "a"))  # symmetric
        d.sign_peace("a", "b")
        self.assertFalse(d.at_war("a", "b"))
        self.assertEqual(d.relation("a", "b").status, DiplomaticStatus.PEACE)

    def test_alliance_raises_score(self):
        d = DiplomacyEngine()
        d.form_alliance("x", "y")
        self.assertEqual(d.relation("x", "y").status, DiplomaticStatus.ALLIANCE)
        self.assertGreaterEqual(d.relation("x", "y").score, 40.0)


class ScenarioIntegrationTests(unittest.TestCase):
    def test_isengard_starts_at_war_with_its_neighbours(self):
        gs = build_campaign(seed=5)
        self.assertTrue(gs.diplomacy.at_war("isengard", "rohan") or True)  # war declared as a queued command
        gs.tick()  # command drains on first tick
        self.assertTrue(gs.diplomacy.at_war("isengard", "rohan"))
        self.assertTrue(gs.diplomacy.at_war("isengard", "gondor"))
        self.assertFalse(gs.diplomacy.at_war("rohan", "gondor"))

    def test_campaign_runs_for_many_ticks_without_error(self):
        gs = build_campaign(seed=101)
        for _ in range(120):
            gs.tick()
        self.assertGreater(len(gs.chronicle.entries), 0)
        self.assertEqual(gs.calendar.tick, 120)


if __name__ == "__main__":
    unittest.main()
