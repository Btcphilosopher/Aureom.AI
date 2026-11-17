"""Lint and synthesis hygiene of the generated RTL (Verilator -Wall, Yosys)."""

import os
import re
import subprocess
import unittest

from helpers import ALBION, KS_DEF, SOC_DEF, TmpCase, model, need, run
from albion_reggen.generate import build_outputs


def write_rtl(m, d):
    outs = build_outputs(m)
    paths = []
    for rel, text in outs.items():
        if rel.startswith("rtl/"):
            p = os.path.join(d, os.path.basename(rel))
            open(p, "w").write(text)
            paths.append(p)
    order = ["sf_reg_pkg.sv", "sf_reg_decoder.sv", "sf_reg_interface.sv", "sf_reg_bank.sv"]
    return [os.path.join(d, n) for n in order]


class Lint(TmpCase):
    @need("verilator")
    def test_verilator_wall_is_clean(self):
        for path in (SOC_DEF, KS_DEF):
            with self.subTest(path=os.path.basename(path)):
                d = os.path.join(self.tmp, os.path.basename(path))
                os.makedirs(d)
                rtl = write_rtl(model(path), d)
                r = run(["verilator", "--lint-only", "-Wall", "--top-module", "sf_reg_bank",
                         os.path.join(ALBION, "sf_albion_pkg.sv")] + rtl)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual((r.stdout + r.stderr).strip(), "", "Verilator -Wall reported warnings")


class Synthesis(TmpCase):
    def synth(self, path, script_tail):
        d = os.path.join(self.tmp, os.path.basename(path))
        os.makedirs(d, exist_ok=True)
        rtl = write_rtl(model(path), d)
        script = (f"read_verilog -sv {os.path.join(ALBION, 'sf_albion_pkg.sv')} {' '.join(rtl)}; "
                  "hierarchy -check -top sf_reg_bank; proc; flatten; opt; " + script_tail)
        return run(["yosys", "-q", "-p", script], timeout=900)

    @need("yosys")
    def test_elaborates_without_latches_or_loops(self):
        for path in (SOC_DEF, KS_DEF):
            with self.subTest(path=os.path.basename(path)):
                r = self.synth(path, "check -assert; select -assert-none t:$dlatch t:$_DLATCH_* t:$adlatch; ")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    @need("yosys")
    def test_maps_to_gates(self):
        r = self.synth(KS_DEF, "synth -top sf_reg_bank; check -assert; tee -o " + os.path.join(self.tmp, "stat.txt") + " stat")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        txt = open(os.path.join(self.tmp, "stat.txt")).read()
        self.assertRegex(txt, r"Number of cells:\s+\d+")
        self.assertNotIn("$_DLATCH", txt)
        self.assertRegex(txt, r"\$_DFF_PN0_|\$_SDFF|\$_DFFE_PN0P_|\$_DFF_P_|\$_DFFE_P")

    @need("yosys")
    def test_all_state_has_asynchronous_reset(self):
        """Every flip-flop of the bank is async-reset: after proc no plain $dff remains."""
        r = self.synth(KS_DEF, "tee -o " + os.path.join(self.tmp, "cells.txt") + " stat")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        txt = open(os.path.join(self.tmp, "cells.txt")).read()
        self.assertIn("$adff", txt)
        self.assertNotRegex(txt, r"\$dff\b", "a flip-flop without asynchronous reset was generated")


if __name__ == "__main__":
    unittest.main()
