"""Output generation is deterministic and a pure function of the validated definition."""

import hashlib
import os
import re
import subprocess
import sys
import unittest

from helpers import GENERATED, KS_DEF, SOC_DEF, TOOL, TmpCase, model, run
from albion_reggen.generate import build_outputs, check_outputs, manifest_text
from albion_reggen.loader import load
from albion_reggen.validate import validate


def digest_tree(root):
    out = {}
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


class Determinism(TmpCase):
    def test_two_generations_identical(self):
        for path in (SOC_DEF, KS_DEF):
            a = build_outputs(validate(load(path)))
            b = build_outputs(validate(load(path)))
            self.assertEqual(a, b)

    def test_independent_processes_agree(self):
        """Different PYTHONHASHSEED, different working directory, different output directory -> same bytes."""
        trees = []
        for k, (seed, cwd) in enumerate((("0", TOOL), ("12345", self.tmp), ("random", "/"))):
            out = os.path.join(self.tmp, f"out{k}")
            r = run([sys.executable, "-m", "albion_reggen", "generate", SOC_DEF, "--out", out], cwd=cwd,
                    env={"PYTHONHASHSEED": seed, "PYTHONPATH": TOOL})
            self.assertEqual(r.returncode, 0, r.stderr)
            trees.append(digest_tree(out))
        self.assertEqual(trees[0], trees[1])
        self.assertEqual(trees[0], trees[2])

    def test_committed_outputs_are_up_to_date(self):
        self.assertTrue(os.path.isdir(GENERATED), "run `make gen` to create generated/")
        self.assertEqual(check_outputs(model(SOC_DEF), GENERATED), [])

    def test_check_detects_tampering_and_staleness(self):
        out = os.path.join(self.tmp, "o")
        r = run([sys.executable, "-m", "albion_reggen", "generate", KS_DEF, "--out", out], env={"PYTHONPATH": TOOL})
        self.assertEqual(r.returncode, 0, r.stderr)
        m = model(KS_DEF)
        self.assertEqual(check_outputs(m, out), [])
        p = os.path.join(out, "rtl", "sf_reg_bank.sv")
        txt = open(p).read()
        open(p, "w").write(txt.replace("8'h11", "8'h10", 1))
        probs = check_outputs(m, out)
        self.assertTrue(any("rtl/sf_reg_bank.sv" in x for x in probs), probs)
        open(p, "w").write(txt)
        os.remove(os.path.join(out, "fw", "c", "sf_regs.h"))
        self.assertTrue(any("missing: fw/c/sf_regs.h" in x for x in check_outputs(m, out)))

    def test_source_order_does_not_matter(self):
        """Reordering peripherals, registers and fields in the source changes neither the hashes nor any output."""
        for path in (KS_DEF, SOC_DEF):
            ref = validate(load(path))
            src = load(path)
            src.root["peripherals"].reverse()
            for p in src.root["peripherals"]:
                p["registers"].reverse()
                for r in p["registers"]:
                    if "fields" in r:
                        r["fields"].reverse()
            alt = validate(src)
            self.assertEqual(alt.semantic_hash, ref.semantic_hash)
            self.assertEqual(alt.definition_hash, ref.definition_hash)
            self.assertEqual(build_outputs(alt), build_outputs(ref))

    def test_hash_semantics(self):
        """Prose does not change the hardware fingerprint; behaviour does."""
        a = load(KS_DEF)
        base = validate(a)
        a = load(KS_DEF); a.root["peripherals"][0]["description"] = "different prose"
        a.root["peripherals"][0]["registers"][0]["description"] = "other words"
        prose = validate(a)
        self.assertEqual(prose.semantic_hash, base.semantic_hash)
        self.assertNotEqual(prose.definition_hash, base.definition_hash)
        a = load(KS_DEF); a.root["peripherals"][0]["registers"][0]["fields"][0]["reset"] = 0x12
        beh = validate(a)
        self.assertNotEqual(beh.semantic_hash, base.semantic_hash)

    def test_no_environment_leakage(self):
        outs = build_outputs(model(SOC_DEF))
        for rel, text in outs.items():
            self.assertNotRegex(text, r"/home/|/tmp/|/root/|[A-Za-z]:\\\\", rel)
            self.assertNotRegex(text, r"\b20\d\d-\d\d-\d\d\b", rel)
            self.assertNotIn("\r", text, rel)
            self.assertTrue(text.endswith("\n"), rel)
            if rel.startswith(("rtl/", "fw/", "verif/")):
                text.encode("ascii")             # code is plain ASCII

    def test_hash_is_embedded_everywhere(self):
        m = model(SOC_DEF)
        outs = build_outputs(m)
        for rel, text in outs.items():
            self.assertIn(m.semantic_hash, text, rel)
            self.assertIn(m.definition_hash, text, rel)
        self.assertIn(f"{m.hash64:016x}", outs["fw/c/sf_regs.h"])
        self.assertIn(f"{m.hash64:016x}", outs["fw/rust/sf_regs.rs"])
        self.assertIn(f"{m.hash64:016x}", outs["rtl/sf_reg_pkg.sv"])
        sysid_reset = [i for i in m.instances if i.name == "sysid_regmap_hash"][0].reg.reset
        self.assertEqual(sysid_reset, m.hash64)


if __name__ == "__main__":
    unittest.main()
