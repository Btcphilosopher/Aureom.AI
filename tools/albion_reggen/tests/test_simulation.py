"""The generated RTL matches the independent reference model, cycle by cycle, with the ALP link checker live."""

import os
import unittest

from helpers import KS_DEF, SOC_DEF, TmpCase, model, need
from albion_reggen import simflow


@need("verilator")
class Simulation(TmpCase):
    def go(self, path, seed, cycles):
        m = model(path)
        r = simflow.simulate(m, os.path.join(self.tmp, "w"), seed=seed, cycles=cycles)
        self.assertTrue(r.passed, f"stage={r.stage}\n{r.log}")
        self.assertEqual(r.missing, [], "stimulus did not reach: " + ", ".join(r.missing[:10]))
        self.assertGreater(r.checks, 100000)
        return r

    def test_kitchen_sink_seeds(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                self.go(KS_DEF, seed, 6000)

    def test_silicaflux_map(self):
        for seed in (1, 2):
            with self.subTest(seed=seed):
                self.go(SOC_DEF, seed, 5000)

    def test_link_capacity_two_is_necessary_and_sufficient(self):
        """The design accepts a request on the edge its predecessor's response leaves, so it needs capacity 2:
        the AlbionCore link checker must accept 2 and reject 1 (ALP-OUT-01 counts at the start of the cycle)."""
        m = model(KS_DEF)
        ok = simflow.simulate(m, os.path.join(self.tmp, "cap2"), seed=1, cycles=2000)
        self.assertTrue(ok.passed, ok.log)
        one = simflow.simulate(m, os.path.join(self.tmp, "cap1"), seed=1, cycles=2000,
                               tb_edit=lambda t: t.replace("#(.MAX_OUTSTANDING(sf_reg_pkg::SF_REG_MAX_OUTSTANDING))", "#(.MAX_OUTSTANDING(1))"))
        self.assertFalse(one.passed)
        self.assertIn("a_alp_out_01", one.log)

    def test_coverage_space_is_substantial(self):
        from albion_reggen.refmodel import required_coverage
        self.assertGreater(len(required_coverage(model(KS_DEF))), 100)
        self.assertGreater(len(required_coverage(model(SOC_DEF))), 300)


if __name__ == "__main__":
    unittest.main()
