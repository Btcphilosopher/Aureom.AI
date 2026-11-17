"""Integration with implemented RTL: ALP constants, SYSID registers, RTL bindings, vendored files."""

import copy
import hashlib
import os
import re
import unittest
import zipfile

from helpers import ALBION, REPO, SOC_DEF, TOOL, TmpCase, base_doc, model
from albion_reggen import alpcheck, bindcheck
from albion_reggen.errors import RegDefError
from albion_reggen.loader import load
from albion_reggen.validate import validate

ARCHIVE_DIR = "SilicaFlux-main/SilicaFlux2.0/SilicaFlux2.5/"
ALBION_ZIP = os.path.join(REPO, ARCHIVE_DIR, "albioncore-0.1.0.zip")
HAVE_ARCHIVES = os.path.isfile(ALBION_ZIP)
need_archives = unittest.skipUnless(HAVE_ARCHIVES, "repository RTL archives not found next to the tool")


class AlpConformance(TmpCase):
    def test_generator_constants_equal_the_real_package(self):
        self.assertEqual(alpcheck.check(model(SOC_DEF)), [])

    def pkg_copy(self, edit):
        text = open(os.path.join(ALBION, "sf_albion_pkg.sv")).read()
        new = edit(text)
        self.assertNotEqual(new, text, "edit did not change the package")
        p = os.path.join(self.tmp, "pkg.sv")
        open(p, "w").write(new)
        return p

    def test_drift_in_the_package_is_detected(self):
        cases = {
            "status code renumbered": lambda t: t.replace("SF_ST_ACCESS_DENIED = 4'h2", "SF_ST_ACCESS_DENIED = 4'hC"),
            "request field moved": lambda t: t.replace("SF_REQ_ADDR_LSB   = 144", "SF_REQ_ADDR_LSB   = 145"),
            "opcode changed": lambda t: t.replace("SF_OP_WRITE = 4'h2", "SF_OP_WRITE = 4'h3"),
            "invalid domain changed": lambda t: t.replace("SF_DOM_INVALID      = 8'hFF", "SF_DOM_INVALID      = 8'hFE"),
            "attribute bit moved": lambda t: t.replace("SF_ATTR_PRIV_BIT    = 2", "SF_ATTR_PRIV_BIT    = 5"),
            "protocol minor version bumped": lambda t: t.replace("SF_ALP_VERSION_MINOR  = 0", "SF_ALP_VERSION_MINOR  = 3"),
            "library patch bumped": lambda t: t.replace("SF_ALBION_LIB_PATCH   = 0", "SF_ALBION_LIB_PATCH   = 7"),
            "features changed": lambda t: t.replace("SF_FEATURES_ALP_V1 = 16'h0003", "SF_FEATURES_ALP_V1 = 16'h0007"),
            "caps layout changed": lambda t: t.replace("logic [15:0] max_outstanding;", "logic [11:0] max_outstanding;\n    logic [3:0] extra;"),
        }
        for label, edit in cases.items():
            with self.subTest(label):
                bad = alpcheck.check(model(SOC_DEF), self.pkg_copy(edit))
                self.assertTrue(bad, f"'{label}' was not detected")

    def test_sysid_value_errors_are_detected(self):
        for label, patch in {
            "wrong ALP major": ("ALP_VERSION", "MAJOR", 2),
            "wrong capacity": ("ALP_CAPS", "MAX_OUTSTANDING", 4),
            "wrong features": ("ALP_CAPS", "FEATURES", 0x000F),
            "wrong lib minor": ("LIB_VERSION", "MINOR", 9),
            "wrong address width": ("ALP_CAPS", "ADDR_W", 32),
        }.items():
            with self.subTest(label):
                src = load(SOC_DEF)
                p = next(x for x in src.root["peripherals"] if x["name"] == "sysid")
                reg = next(r for r in p["registers"] if r["name"] == patch[0])
                next(f for f in reg["fields"] if f["name"] == patch[1])["reset"] = patch[2]
                bad = alpcheck.check(validate(src))
                self.assertTrue(bad, label)

    def test_sysid_matches_the_map_version(self):
        m = model(SOC_DEF)
        sysid = m.periph("sysid")
        r = next(x for x in sysid.registers if x.name == "REGMAP_VERSION")
        f = {x.name: x.reset for x in r.fields}
        self.assertEqual((f["MAJOR"], f["MINOR"]), m.version)

    def test_link_capacity_matches_the_rtl_and_the_checker(self):
        m = model(SOC_DEF)
        caps = next(x for x in m.periph("sysid").registers if x.name == "ALP_CAPS")
        cap = next(f for f in caps.fields if f.name == "MAX_OUTSTANDING").reset
        pkg = open(os.path.join(TOOL, "albion_reggen", "emit_sv.py")).read()
        self.assertIn(f"LINK_CAPACITY = {cap}", pkg)


class BindingCheck(TmpCase):
    def test_parse_ports(self):
        src = """
        // module fake_decoy ( input wire a );
        module blk #(parameter int N = 4, parameter logic [3:0] M = 4'h1) (
          input  wire logic            clk_i,   // a comment, with a comma
          input  wire logic [N-1:0]    d_i,
          input  sf_albion_pkg::sf_req_t req_i,
          output logic [N*8-1:0]       q_o, r_o,
          inout  wire                  pad
        );
        endmodule
        """
        self.assertEqual(bindcheck.parse_ports(src, "blk"),
                         {"clk_i": "input", "d_i": "input", "req_i": "input", "q_o": "output", "r_o": "output", "pad": "inout"})
        self.assertIsNone(bindcheck.parse_ports(src, "missing"))
        self.assertEqual(bindcheck.parse_ports("module noports; endmodule", "noports"), {})

    @need_archives
    def test_every_rtl_module_in_the_map_is_verified(self):
        m = model(SOC_DEF)
        res = bindcheck.check(m, REPO, require=True)
        self.assertEqual([r for r in res if r.status != "ok"], [])
        self.assertEqual({r.module for r in res}, {md.module for p in m.peripherals for md in p.rtl_modules})
        self.assertGreaterEqual(len(res), 8)
        for p in m.peripherals:
            for md in p.rtl_modules:
                self.assertTrue(md.archive and md.path and len(md.sha256) == 64, f"{p.name}.{md.module} lacks provenance")

    @need_archives
    def test_tampering_is_detected(self):
        def mutated(edit):
            src = load(SOC_DEF)
            edit(src.root["peripherals"])
            return validate(src)

        def mod(ps, periph, module):
            p = next(x for x in ps if x["name"] == periph)
            return next(x for x in p["rtl"]["modules"] if x["module"] == module)

        def sha(ps):
            mod(ps, "dma", "hpc_dma_adapter")["sha256"] = "0" * 64

        res = bindcheck.check(mutated(sha), REPO)
        self.assertTrue(any(r.status == "error" and "SHA-256 differs" in r.detail for r in res))

        def port_dir(ps):    # claim a real input is an output: model-level direction rules also fire, so keep the role unchecked
            mod(ps, "sramc", "sf_sram_subsystem")["ports"]["flush"] = "output"
            for p in ps:
                if p["name"] == "sramc":
                    for r in p["registers"]:
                        for f in r.get("fields", []):
                            if f.get("name") == "FLUSH":
                                f["connect"] = {"value": "sf_sram_subsystem.flush"}   # rw output -> declared output: wrong
        with self.assertRaises(RegDefError) as cm:
            mutated(port_dir)
        self.assertIn("E_BIND_DIR", cm.exception.codes)           # the offline check already refuses it

        def fake_port(ps):   # a port that does not exist in the RTL: offline fine, RTL check must refuse
            mod(ps, "sramc", "sf_sram_subsystem")["ports"]["no_such_port"] = "input"
        res = bindcheck.check(mutated(fake_port), REPO)
        self.assertTrue(any(r.status == "error" and "no_such_port: not a port" in r.detail for r in res))

        def wrong_dir(ps):   # right port, wrong declared direction (offline-consistent: nothing connects to it)
            mod(ps, "sramc", "sf_sram_subsystem")["ports"]["m_req_valid"] = "output"
        res = bindcheck.check(mutated(wrong_dir), REPO)
        self.assertTrue(any(r.status == "error" and "m_req_valid: declared output, RTL has input" in r.detail for r in res))

        def renamed(ps):     # renaming a bound module is refused offline: the field connects still name the old one
            mod(ps, "perf", "hpc_perf_counters")["module"] = "hpc_perf_countersX"
        with self.assertRaises(RegDefError) as cm:
            mutated(renamed)
        self.assertIn("E_BIND_MODULE", cm.exception.codes)

        def phantom(ps):     # a module the RTL file does not declare (nothing connects to it, so offline checks pass)
            m = dict(mod(ps, "perf", "hpc_perf_counters"))
            m["module"] = "hpc_perf_countersX"
            m["ports"] = {}
            next(x for x in ps if x["name"] == "perf")["rtl"]["modules"].append(m)
        res = bindcheck.check(mutated(phantom), REPO)
        self.assertTrue(any(r.status == "error" and "not declared" in r.detail for r in res))

    @need_archives
    def test_missing_rtl_is_skipped_unless_required(self):
        m = model(SOC_DEF)
        res = bindcheck.check(m, self.tmp)
        self.assertTrue(all(r.status == "skipped" for r in res))
        res = bindcheck.check(m, self.tmp, require=True)
        self.assertTrue(all(r.status == "error" for r in res))

    def test_integration_status_is_honest(self):
        m = model(SOC_DEF)
        status = {p.name: p.rtl_status for p in m.peripherals}
        self.assertEqual(status["intc"], "register_compatible", "mcu_intc cannot be port-bound; do not claim it is")
        self.assertEqual(status["sysid"], "constants")
        for name in ("sramc", "dma", "tensor", "vector", "perf", "clkrst"):
            self.assertEqual(status[name], "bound")
            self.assertTrue(any(f.connect for r in m.periph(name).registers for f in r.fields) or
                            any(r.connect for r in m.periph(name).registers), name)

    def test_real_blocks_semantics_recorded_in_the_definitions(self):
        """Fidelity decisions that came from reading the RTL are visible in the model."""
        m = model(SOC_DEF)
        dma = {r.name: r for r in m.periph("dma").registers}
        abort = next(f for f in dma["CTRL"].fields if f.name == "ABORT")
        self.assertEqual(abort.access, "rw", "cmd_abort is level-sensitive in hpc_dma_adapter: must not be a pulse")
        sram = {r.name: r for r in m.periph("sramc").registers}
        flush = next(f for f in sram["CTRL"].fields if f.name == "FLUSH")
        self.assertEqual(flush.access, "rw", "flush is a level in sf_sram_subsystem")
        for fn in ("RSP_OVERFLOW", "BANK_PROTO"):
            f = next(x for x in sram["STATUS"].fields if x.name == fn)
            self.assertEqual(f.access, "ro", f"{fn} is sticky-until-reset in the RTL, so it cannot be W1C")
        for pn, rn in (("dma", "START"), ("dma", "CPL_POP"), ("vector", "DOORBELL"), ("vector", "CPL_POP"),
                       ("tensor", "DOORBELL"), ("tensor", "CPL_POP")):
            r = next(x for x in m.periph(pn).registers if x.name == rn)
            self.assertTrue(r.write_gate and r.wr_strobe, f"{pn}.{rn} is refused by hardware when it cannot be accepted")


class VendoredFiles(unittest.TestCase):
    @need_archives
    def test_vendored_albioncore_files_are_byte_identical_to_the_archive(self):
        members = {"regions.yaml": "albioncore-0.1.0/tools/albion/config/regions.yaml",
                   "sf_albion_pkg.sv": "albioncore-0.1.0/rtl/albion/sf_albion_pkg.sv",
                   "sf_albion_chan_checker.sv": "albioncore-0.1.0/tests/albion/common/sf_albion_chan_checker.sv",
                   "sf_albion_link_checker.sv": "albioncore-0.1.0/tests/albion/common/sf_albion_link_checker.sv"}
        prov = open(os.path.join(ALBION, "PROVENANCE.md")).read()
        with zipfile.ZipFile(ALBION_ZIP) as z:
            for f, mem in members.items():
                mine = open(os.path.join(ALBION, f), "rb").read()
                self.assertEqual(mine, z.read(mem), f"{f} differs from the archive")
                self.assertIn(hashlib.sha256(mine).hexdigest(), prov, f"{f} hash missing from PROVENANCE.md")

    def test_provenance_hashes_are_current(self):
        prov = open(os.path.join(ALBION, "PROVENANCE.md")).read()
        for f in os.listdir(ALBION):
            if f.endswith(".md"):
                continue
            self.assertIn(hashlib.sha256(open(os.path.join(ALBION, f), "rb").read()).hexdigest(), prov, f)


if __name__ == "__main__":
    unittest.main()
