"""
Spec ref: 62 (deterministic simulation), 95 (critical test — run N
simulation ticks twice, same seed, same commands, states must match).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from simulation.scenarios.rohan_frontier import build_campaign

TICKS = int(os.environ.get("MITHRIL_DETERMINISM_TICKS", "150"))


class DeterminismTests(unittest.TestCase):
    def test_same_seed_same_ticks_produces_identical_state(self):
        gs1 = build_campaign(seed=12345)
        gs2 = build_campaign(seed=12345)

        for _ in range(TICKS):
            gs1.tick()
        for _ in range(TICKS):
            gs2.tick()

        self.assertEqual(gs1.canonical_json(), gs2.canonical_json())

    def test_different_seed_diverges(self):
        gs1 = build_campaign(seed=1)
        gs2 = build_campaign(seed=2)
        for _ in range(50):
            gs1.tick()
            gs2.tick()
        self.assertNotEqual(gs1.canonical_json(), gs2.canonical_json())

    def test_long_run_stays_internally_consistent(self):
        """10,000-tick soak per section 95's determinism stress test,
        scaled down by default to keep CI fast; validate() runs every
        tick regardless, so this mainly guards against invariant
        violations (negative population/resources/etc) over a long run."""
        gs = build_campaign(seed=777)
        long_ticks = int(os.environ.get("MITHRIL_SOAK_TICKS", "500"))
        for _ in range(long_ticks):
            gs.tick()  # raises ValidationError internally if anything breaks


if __name__ == "__main__":
    unittest.main()
