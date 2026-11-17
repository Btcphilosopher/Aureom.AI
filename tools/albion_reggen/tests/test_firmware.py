"""Behaviour of the generated C and Rust APIs on mock buses, plus compile checks of every generated firmware file."""

import os
import re
import unittest

from helpers import KS_DEF, SOC_DEF, TOOL, TmpCase, model, need, run
from albion_reggen.generate import build_outputs

HERE = os.path.dirname(os.path.abspath(__file__))


def tree(m, d):
    for rel, text in build_outputs(m).items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(text)


class FirmwareC(TmpCase):
    @need("gcc")
    def test_behaviour_split_and_native64(self):
        tree(model(KS_DEF), self.tmp)
        for native in (0, 1):
            with self.subTest(native64=native):
                exe = os.path.join(self.tmp, f"fw_test{native}")
                r = run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-O1", "-fsanitize=address,undefined",
                         f"-DSF_REGS_NATIVE64={native}", "-I", os.path.join(self.tmp, "fw", "c"),
                         os.path.join(HERE, "c", "fw_test.c"), "-o", exe])
                self.assertEqual(r.returncode, 0, r.stderr)
                out = run([exe])
                self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
                self.assertIn("C TEST PASSED", out.stdout)

    @need("gcc")
    def test_sysid_hash_check(self):
        tree(model(SOC_DEF), self.tmp)
        for native in (0, 1):
            exe = os.path.join(self.tmp, f"sysid{native}")
            r = run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", f"-DSF_REGS_NATIVE64={native}",
                     "-I", os.path.join(self.tmp, "fw", "c"), os.path.join(HERE, "c", "sysid_test.c"), "-o", exe])
            self.assertEqual(r.returncode, 0, r.stderr)
            out = run([exe])
            self.assertIn("SYSID TEST PASSED", out.stdout, out.stdout)

    @need("gcc", "g++")
    def test_headers_compile_as_c_and_cpp_under_strict_flags(self):
        tree(model(SOC_DEF), self.tmp)
        inc = os.path.join(self.tmp, "fw", "c")
        prog = '#include "sf_regs.h"\n#include "sf_regs_examples.h"\nint main(void){return 0;}\n'
        open(os.path.join(self.tmp, "t.c"), "w").write(prog)
        for std, cc, flags in (("c11", "gcc", ["-Wconversion", "-Wshadow", "-Wpedantic"]), ("c99", "gcc", ["-Wpedantic"]),
                               ("c++17", "g++", ["-Wpedantic", "-x", "c++"])):
            with self.subTest(std=std):
                r = run([cc, f"-std={std}", "-Wall", "-Wextra", "-Werror", *flags, "-I", inc, "-fsyntax-only",
                         os.path.join(self.tmp, "t.c")])
                self.assertEqual(r.returncode, 0, r.stderr)

    @need("clang")
    def test_clang_accepts_the_headers(self):
        tree(model(SOC_DEF), self.tmp)
        open(os.path.join(self.tmp, "t.c"), "w").write('#include "sf_regs.h"\n#include "sf_regs_examples.h"\nint main(void){return 0;}\n')
        r = run(["clang", "-std=c11", "-Weverything", "-Wno-padded", "-Wno-unused-function", "-Wno-unused-macros",
                 "-Wno-declaration-after-statement", "-Wno-reserved-identifier", "-Wno-covered-switch-default",
                 "-Werror", "-I", os.path.join(self.tmp, "fw", "c"), "-fsyntax-only", os.path.join(self.tmp, "t.c")])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unsafe_helpers_are_not_generated(self):
        """Registers with read side effects or stored write-only fields get no read-modify-write helpers."""
        h = build_outputs(model(KS_DEF))["fw/c/sf_regs.h"]
        self.assertIn("sf_ks_a_cmd_write", h)                     # the raw write is there
        self.assertNotIn("sf_ks_a_cmd_pulse_go", h)               # wo/out field in the register: no RMW helper
        self.assertNotIn("sf_ks_a_both_set_v", h)                 # rd_strobe: a read-back has a side effect
        self.assertIn("sf_ks_a_mixed_set_en", h)                  # an ordinary rw/w1c register keeps them
        r = build_outputs(model(KS_DEF))["fw/rust/sf_regs.rs"]
        self.assertNotIn("pub fn pulse_go", r)
        self.assertNotIn("pub fn set_v<", r.split("pub mod both")[1].split("pub mod word")[0])

    def test_read_only_and_write_only_register_apis(self):
        h = build_outputs(model(KS_DEF))["fw/c/sf_regs.h"]
        self.assertNotIn("sf_ks_a_status_write", h)               # read-only register: no write function
        self.assertNotIn("sf_ks_a_cmd_read", h)                   # write-only register: no read function
        self.assertIn("sf_ks_a_status_read", h)


class FirmwareRust(TmpCase):
    def build(self, defpath, test_file):
        m = model(defpath)
        tree(m, self.tmp)
        root = os.path.join(self.tmp, "root.rs")
        open(root, "w").write(
            f'#[path = "{self.tmp}/fw/rust/sf_regs.rs"] mod sf_regs;\n'
            f'#[path = "{self.tmp}/fw/rust/sf_regs_examples.rs"] mod sf_regs_examples;\n'
            f'#[cfg(test)] #[path = "{test_file}"] mod fw_tests;\nfn main() {{}}\n')
        exe = os.path.join(self.tmp, "rt_" + os.path.basename(test_file))
        r = run(["rustc", "--edition", "2021", "--test", "-D", "warnings", "-o", exe, root])
        self.assertEqual(r.returncode, 0, r.stderr)
        return run([exe, "--test-threads=1"])

    @need("rustc")
    def test_behaviour(self):
        out = self.build(KS_DEF, os.path.join(HERE, "rust", "fw_tests.rs"))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertRegex(out.stdout, r"test result: ok\. \d+ passed; 0 failed")
        self.assertGreaterEqual(int(re.search(r"(\d+) passed", out.stdout).group(1)), 11)

    @need("rustc")
    def test_sysid_hash_check(self):
        out = self.build(SOC_DEF, os.path.join(HERE, "rust", "sysid_tests.rs"))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("1 passed", out.stdout)

    @need("rustc")
    def test_examples_and_everything_compile_for_the_silicaflux_map(self):
        m = model(SOC_DEF)
        tree(m, self.tmp)
        root = os.path.join(self.tmp, "all.rs")
        open(root, "w").write(f'#[path = "{self.tmp}/fw/rust/sf_regs.rs"] mod sf_regs;\n'
                              f'#[path = "{self.tmp}/fw/rust/sf_regs_examples.rs"] mod sf_regs_examples;\nfn main() {{}}\n')
        r = run(["rustc", "--edition", "2021", "-D", "warnings", "-o", os.path.join(self.tmp, "all"), root])
        self.assertEqual(r.returncode, 0, r.stderr)


class FirmwareExamples(TmpCase):
    def test_every_example_step_appears_in_all_three_renderings(self):
        m = model(SOC_DEF)
        outs = build_outputs(m)
        n = 0
        for p in m.peripherals:
            for k, ex in enumerate(p.examples):
                n += 1
                self.assertIn(f"sf_example_{p.name}_{k}", outs["fw/c/sf_regs_examples.h"])
                self.assertIn(f"example_{p.name}_{k}", outs["fw/rust/sf_regs_examples.rs"])
                self.assertIn(ex["title"], outs["docs/FIRMWARE_EXAMPLES.md"])
        self.assertGreaterEqual(n, 10)


if __name__ == "__main__":
    unittest.main()
