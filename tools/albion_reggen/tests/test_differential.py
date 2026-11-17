"""Differential test: generated register bank vs the real hand-written register slaves (hpc_cq_mmio, tsu_regs,
mcu_intc), driven with identical accesses and hardware inputs.  See diff_harness.py for what is compared."""

import os
import re
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor

from helpers import ALBION, REPO, SOC_DEF, TmpCase, model, need, run
from diff_harness import emit, intc_spec, tensor_spec, vector_spec
from albion_reggen.generate import build_outputs

R = os.path.join(REPO, "SilicaFlux-main", "SilicaFlux2.0", "SilicaFlux2.5")
SOURCES = {
    "vector": (os.path.join(R, "silicaflux-hpc-m06-command-queue.zip"),
               ["silicaflux-hpc-m06-command-queue/rtl/hpc_cq_pkg.sv", "silicaflux-hpc-m06-command-queue/rtl/hpc_cq_mmio.sv"]),
    "tensor": (os.path.join(REPO, "SilicaFlux-main", "silicaflux-tensorcore08.zip"),
               ["silicaflux-tensorcore08/rtl/tsu_defs.svh", "silicaflux-tensorcore08/rtl/tsu_regs.sv"]),
    "intc": (os.path.join(R, "silicaflux-mcu-i.zip"),
             ["silicaflux-mcu-i/rtl/generated/mcu_memmap_pkg.sv", "silicaflux-mcu-i/rtl/interrupts/mcu_intc.sv"]),
}
SPECS = {"vector": vector_spec, "tensor": tensor_spec, "intc": intc_spec}


def available(key):
    return os.path.isfile(SOURCES[key][0])


@need("verilator")
class Differential(TmpCase):
    def build_and_run(self, key, nops=3000, seed=1, mutate=None):
        zpath, members = SOURCES[key]
        d = os.path.join(self.tmp, f"{key}_{seed}{'_mut' if mutate else ''}")
        os.makedirs(d, exist_ok=True)
        with zipfile.ZipFile(zpath) as z:
            files = []
            for mem in members:
                p = os.path.join(d, os.path.basename(mem))
                open(p, "wb").write(z.read(mem))
                if p.endswith(".sv"):
                    files.append(p)
        m = model(SOC_DEF)
        rtl = {os.path.basename(k): v for k, v in build_outputs(m).items() if k.startswith("rtl/")}
        if mutate:
            rtl = mutate(rtl)
        for n, text in rtl.items():
            open(os.path.join(d, n), "w").write(text)
        rtl_files = [os.path.join(d, n) for n in ("sf_reg_pkg.sv", "sf_reg_decoder.sv", "sf_reg_interface.sv", "sf_reg_bank.sv")]
        tb = os.path.join(d, f"tb_diff_{key}.sv")
        open(tb, "w").write(emit(m, SPECS[key](m), nops, seed))
        obj = os.path.join(d, "obj")
        b = run(["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-lint", "-Wno-style", f"-I{d}",
                 "--top-module", f"tb_diff_{key}", "-Mdir", obj, os.path.join(ALBION, "sf_albion_pkg.sv")] + files + rtl_files + [tb])
        self.assertEqual(b.returncode, 0, (b.stdout + b.stderr)[-3000:])
        r = run([os.path.join(obj, f"Vtb_diff_{key}")])
        return r.stdout + r.stderr

    def run_block(self, key, nops=3000, seed=1):
        out = self.build_and_run(key, nops, seed)
        self.assertIn("DIFF_RESULT: PASS", out, out[-3000:])
        return {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", out.split("DIFF_RESULT: PASS")[1])}

    def run_all(self, key, seeds, floor):
        res = [self.run_block(key, 2500, sd) for sd in seeds]
        for st in res:
            for k, lo in floor.items():
                self.assertGreater(st[k], lo, f"{key}: {k}")
        return res

    def test_all_three_blocks_in_parallel(self):
        jobs = {"vector": {"ok_writes": 150, "ok_reads": 150, "refused": 150, "wo_reads": 5, "pulse_checks": 2000},
                "tensor": {"ok_writes": 150, "ok_reads": 150, "refused": 150, "wo_reads": 5, "pulse_checks": 2000},
                "intc":   {"ok_writes": 150, "ok_reads": 150, "refused": 150}}
        jobs = {k: v for k, v in jobs.items() if available(k)}
        if not jobs:
            self.skipTest("RTL archives missing")
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = {k: ex.submit(self.run_all, k, (1, 2), floor) for k, floor in jobs.items()}
            results = {k: f.result() for k, f in futs.items()}
        for k, r in results.items():
            print(f"\n{k}: {r}")

    @unittest.skipUnless(available("vector"), "RTL archive missing")
    def test_the_differential_flow_catches_an_injected_bug(self):
        """Flip the interrupt-status precedence ('set wins' -> 'clear wins') in the generated bank."""
        def flip(files):
            t = files["sf_reg_bank.sv"]
            m = re.search(r"(r\d+_irq_q) <= \(\((r\d+_irq_q) & ~(\([^;]*?\))\) \| (vector_int_status_irq_set_i\[0 \+: 1\])\);", t)
            self.assertIsNotNone(m, "mutation target not found")
            new = f"{m.group(1)} <= (({m.group(2)} | {m.group(4)}) & ~{m.group(3)});"
            files["sf_reg_bank.sv"] = t.replace(m.group(0), new)
            return files
        out = self.build_and_run("vector", 2500, 1, mutate=flip)
        self.assertIn("DIFF_RESULT: FAIL", out)
        self.assertRegex(out, r"DIFF FAIL")

    @unittest.skipUnless(available("tensor"), "RTL archive missing")
    def test_a_wrong_reset_value_is_caught(self):
        def wrong_reset(files):
            t = files["sf_reg_bank.sv"]
            m = re.search(r"if \(!rst_ni\) (r\d+_ok_q|r\d+_irq_q) <= 1'h0;", t)
            # make a stateful interrupt-enable field reset to 1
            m = re.search(r"if \(!rst_ni\) (r\d+_irq_q) <= 1'h0;", t)
            self.assertIsNotNone(m)
            files["sf_reg_bank.sv"] = t.replace(m.group(0), f"if (!rst_ni) {m.group(1)} <= 1'h1;", 1)
            return files
        out = self.build_and_run("tensor", 1500, 1, mutate=wrong_reset)
        self.assertIn("DIFF_RESULT: FAIL", out)


if __name__ == "__main__":
    unittest.main()
