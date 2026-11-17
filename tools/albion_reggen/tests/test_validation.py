"""Every validation rule fires on a minimal bad definition, and a good one passes."""

import copy
import json
import os
import unittest

from helpers import TmpCase, base_doc, codes_of, regs, TOOL
from albion_reggen.errors import RegDefError
from albion_reggen.loader import load, parse_text
from albion_reggen.validate import validate


def per(doc):
    return doc["peripherals"][0]


class Validation(TmpCase):
    def expect(self, doc, code, label=""):
        got = codes_of(doc, self.tmp)
        self.assertIn(code, got, f"{label or code}: expected {code}, got {got}")

    def test_base_is_valid(self):
        self.assertEqual(codes_of(base_doc(), self.tmp), [])

    # ---------------------------------------------------------------- structure
    def test_schema_version(self):
        d = base_doc(); d["regdef_version"] = 2
        self.expect(d, "E_VERSION")

    def test_map_version_format(self):
        d = base_doc(); d["map"]["version"] = "1"
        self.expect(d, "E_VERSION")

    def test_unknown_keys(self):
        for where in ("top", "map", "periph", "reg", "field"):
            d = base_doc()
            {"top": d, "map": d["map"], "periph": per(d), "reg": regs(d)[0], "field": regs(d)[0]["fields"][0]}[where]["bogus"] = 1
            self.expect(d, "E_UNKNOWN_KEY", where)

    def test_duplicate_yaml_key_is_a_parse_error(self):
        with self.assertRaises(RegDefError) as cm:
            parse_text("a: 1\na: 2\n", "x.yaml")
        self.assertIn("E_PARSE", cm.exception.codes)

    def test_leading_zero_integer_rejected(self):
        with self.assertRaises(RegDefError) as cm:
            parse_text("offset: 010\n", "x.yaml")
        self.assertIn("E_PARSE", cm.exception.codes)

    def test_yaml_traps_are_neutralised(self):
        d = parse_text("bits: 7:0\nname: no\nflag: on\nx: 0x1_0000\n", "x.yaml")
        self.assertEqual(d, {"bits": "7:0", "name": "no", "flag": "on", "x": 0x10000})

    # ---------------------------------------------------------------- names
    def test_names(self):
        d = base_doc(); regs(d)[0]["name"] = "ctrl"
        self.expect(d, "E_NAME", "lower-case register")
        d = base_doc(); per(d)["name"] = "Dev"
        self.expect(d, "E_NAME", "upper-case peripheral")
        d = base_doc(); regs(d)[0]["fields"][0]["name"] = "9X"
        self.expect(d, "E_NAME", "field starting with digit")
        d = base_doc(); regs(d)[0]["fields"][0]["name"] = "TYPE"
        self.expect(d, "E_KEYWORD", "Rust keyword")

    def test_duplicates(self):
        d = base_doc(); regs(d)[1]["name"] = "CTRL"
        self.expect(d, "E_DUP_NAME", "register")
        d = base_doc(); regs(d)[0]["fields"][2]["name"] = "EN"
        self.expect(d, "E_DUP_NAME", "field")
        d = base_doc(); d["peripherals"].append(copy.deepcopy(per(d))); d["peripherals"][1]["base"] = 0x1_2000_1000
        self.expect(d, "E_DUP_NAME", "peripheral")

    # ---------------------------------------------------------------- addresses
    def test_register_widths_and_alignment(self):
        d = base_doc(); regs(d)[0]["width"] = 16
        self.expect(d, "E_REG_WIDTH")
        d = base_doc(); regs(d)[1]["offset"] = 6
        self.expect(d, "E_REG_ALIGN", "32-bit at offset 6")
        d = base_doc(); regs(d)[3]["offset"] = 0x14
        self.expect(d, "E_REG_ALIGN", "64-bit at offset 0x14")

    def test_register_overlap(self):
        d = base_doc(); regs(d)[1]["offset"] = 0
        self.expect(d, "E_REG_OVERLAP", "same offset")
        d = base_doc(); regs(d)[3]["offset"] = 0x0  # 64-bit over CTRL and STAT
        self.expect(d, "E_REG_OVERLAP", "64-bit over two 32-bit")
        d = base_doc(); regs(d)[3].update({"offset": 8, "count": 2, "stride": 8})   # array element 0 overlaps IE
        self.expect(d, "E_REG_OVERLAP", "array element")

    def test_register_range(self):
        d = base_doc(); regs(d)[1]["offset"] = 0x1000
        self.expect(d, "E_REG_RANGE")
        d = base_doc(); regs(d)[3].update({"offset": 0xFF8, "count": 2})
        self.expect(d, "E_REG_RANGE", "array runs off the window")

    def test_array_parameters(self):
        d = base_doc(); regs(d)[3]["count"] = 0
        self.expect(d, "E_REG_COUNT")
        d = base_doc(); regs(d)[3]["stride"] = 4
        self.expect(d, "E_REG_STRIDE", "stride smaller than element")
        d = base_doc(); regs(d)[3]["stride"] = 12
        self.expect(d, "E_REG_STRIDE", "stride not a multiple")

    def test_window_rules(self):
        d = base_doc(); per(d)["size"] = 0x1800
        self.expect(d, "E_WINDOW_SIZE", "not a power of two")
        d = base_doc(); per(d)["size"] = 8
        self.expect(d, "E_WINDOW_SIZE", "smaller than an ALP word")
        d = base_doc(); per(d)["base"] = 0x1_2000_0800
        self.expect(d, "E_WINDOW_ALIGN")
        d = base_doc(); d["peripherals"].append(copy.deepcopy(per(d))); d["peripherals"][1]["name"] = "dev2"
        d["peripherals"][1]["base"] = 0x1_2000_0000
        self.expect(d, "E_WINDOW_OVERLAP")

    def test_region_rules(self):
        d = base_doc(); per(d)["region"] = "nope"
        self.expect(d, "E_REGION_UNKNOWN")
        d = base_doc(); per(d)["base"] = 0x1_2010_0000     # just past the 1 MiB dma region
        self.expect(d, "E_REGION_RANGE")
        d = base_doc(); per(d)["region"] = "perf"           # region is priv_only, so cannot be relaxed
        per(d)["base"] = 0x1_7000_0000; per(d)["priv_only"] = False
        self.expect(d, "E_RELAX")
        d = base_doc(); per(d)["region"] = "extmem"; per(d)["base"] = 0x40_0000_0000
        regs(d)[0]["fields"][0]["access"] = "ro"
        # extmem allows read+write: use an extra read-only region to hit E_REGION_ATTR
        d = base_doc()
        d["map"]["extra_regions"] = [{"name": "rom", "base": 0x1_9000_0000, "size": 0x1000,
                                      "attr": {"read": True, "write": False, "mem_type": "device"}}]
        per(d)["region"] = "rom"; per(d)["base"] = 0x1_9000_0000
        self.expect(d, "E_REGION_ATTR", "writable registers in a read-only region")

    def test_extra_region_legality(self):
        base = {"name": "x", "base": 0x1_9000_0000, "size": 0x1000, "attr": {"read": True, "write": True}}
        for label, patch, code in [
            ("non-pow2 size", {"size": 0x1800}, "E_REGION_SIZE"),
            ("too small", {"size": 0x100}, "E_REGION_SIZE"),
            ("misaligned base", {"base": 0x1_9000_0800}, "E_REGION_ALIGN"),
            ("overlaps catalogue", {"base": 0x1_2000_0000}, "E_REGION_OVERLAP"),
            ("inside the reserved legacy window", {"base": 0x8000_0000, "size": 0x1000}, "E_REGION_RESERVED"),
            ("beyond 64 bits", {"base": (1 << 64) - 0x1000, "size": 0x2000}, "E_REGION_RANGE"),
            ("duplicate name", {"name": "dma"}, "E_DUP_NAME"),
        ]:
            d = base_doc(); r = dict(base); r.update(patch); d["map"]["extra_regions"] = [r]
            self.expect(d, code, label)

    # ---------------------------------------------------------------- fields
    def test_field_bits(self):
        d = base_doc(); regs(d)[0]["fields"][2]["bits"] = "4:7"
        self.expect(d, "E_FIELD_BITS", "hi < lo")
        d = base_doc(); regs(d)[0]["fields"][2]["bits"] = "40:36"
        self.expect(d, "E_FIELD_BITS", "beyond a 32-bit register")
        d = base_doc(); regs(d)[0]["fields"][0].pop("bit")
        self.expect(d, "E_FIELD_BITS", "no position")
        d = base_doc(); regs(d)[0]["fields"][0]["bits"] = "3:2"
        self.expect(d, "E_FIELD_BITS", "bit and bits")
        d = base_doc(); regs(d)[0]["fields"][0]["bit"] = -1
        self.expect(d, "E_FIELD_BITS", "negative")

    def test_field_width_mismatch(self):
        d = base_doc(); regs(d)[0]["fields"][2].update({"bits": "7:4", "width": 5})
        self.expect(d, "E_FIELD_WIDTH")
        d = base_doc(); regs(d)[0]["fields"][2].update({"bits": "7:4", "width": 4})
        self.assertEqual(codes_of(d, self.tmp), [])

    def test_field_overlap(self):
        d = base_doc(); regs(d)[0]["fields"][2]["bits"] = "5:0"
        self.expect(d, "E_FIELD_OVERLAP")

    def test_field_access_and_hw_options(self):
        d = base_doc(); regs(d)[0]["fields"][0]["access"] = "rwx"
        self.expect(d, "E_FIELD_ACCESS")
        for access, hw in [("rw", "event"), ("ro", "event"), ("w1c", "update"), ("w1p", "none"), ("wo", "update")]:
            d = base_doc(); regs(d)[0]["fields"][2].update({"access": access, "hw": hw, "reset": 0})
            self.expect(d, "E_FIELD_HW", f"{access}/{hw}")

    def test_registers_without_fields(self):
        d = base_doc(); regs(d)[0].pop("fields")
        self.expect(d, "E_NO_FIELDS")
        d = base_doc(); regs(d)[0]["fields"] = []
        self.expect(d, "E_NO_FIELDS", "empty list")

    # ---------------------------------------------------------------- reset values
    def test_reset_ranges(self):
        d = base_doc(); regs(d)[0]["fields"][0]["reset"] = 2      # 1-bit field
        self.expect(d, "E_RESET_RANGE", "too wide for 1 bit")
        d = base_doc(); regs(d)[0]["fields"][2]["reset"] = 16     # 4-bit field
        self.expect(d, "E_RESET_RANGE", "too wide for 4 bits")
        d = base_doc(); regs(d)[0]["fields"][2]["reset"] = -1
        self.expect(d, "E_RESET_RANGE", "negative")
        d = base_doc(); regs(d)[0]["fields"][2]["reset"] = "banana"
        self.expect(d, "E_RESET_RANGE", "not a number")
        d = base_doc(); regs(d)[3]["reset"] = 1 << 64
        self.expect(d, "E_RESET_RANGE", "64-bit register, 65-bit value")

    def test_reset_boundaries_accepted(self):
        d = base_doc(); regs(d)[0]["fields"][0]["reset"] = 1; regs(d)[0]["fields"][2]["reset"] = 15
        self.assertEqual(codes_of(d, self.tmp), [])
        d = base_doc(); regs(d)[3].pop("hw"); regs(d)[3]["hw"] = "const"; regs(d)[3]["reset"] = (1 << 64) - 1
        self.assertEqual(codes_of(d, self.tmp), [])

    def test_reset_on_stateless_fields(self):
        d = base_doc(); regs(d)[0]["fields"][1].update({"access": "w1p"}); regs(d)[0]["fields"][1].pop("hw"); regs(d)[0]["fields"][1]["reset"] = 1
        self.expect(d, "E_RESET_INVALID", "w1p")
        d = base_doc(); regs(d)[1]["fields"][0]["reset"] = 1
        self.expect(d, "E_RESET_INVALID", "live ro input")
        d = base_doc(); regs(d)[0]["fields"][2].update({"access": "wo", "hw": "none", "reset": 3})
        self.expect(d, "E_RESET_INVALID", "wo/none")

    def test_reset_symbols(self):
        d = base_doc(); regs(d)[3].pop("hw"); regs(d)[3]["hw"] = "const"; regs(d)[3]["reset"] = "$bogus"
        self.expect(d, "E_RESET_SYMBOL", "unknown symbol")
        d = base_doc(); regs(d)[0]["fields"][2]["reset"] = "$regmap_hash"
        self.expect(d, "E_RESET_SYMBOL", "symbol on a writable field")
        d = base_doc(); regs(d)[1].pop("fields"); regs(d)[1].update({"access": "ro", "width": 32, "hw": "const", "reset": "$regmap_hash"})
        self.assertEqual(codes_of(d, self.tmp), [], "32-bit hash allowed")

    # ---------------------------------------------------------------- semantics
    def test_precedence(self):
        d = base_doc(); regs(d)[0]["fields"][2]["precedence"] = "hw"
        self.expect(d, "E_PRECEDENCE", "nothing to conflict with")
        d = base_doc(); regs(d)[0]["fields"][1]["precedence"] = "both"
        self.expect(d, "E_PRECEDENCE", "bad value")

    def test_interrupts(self):
        d = base_doc(); regs(d)[0]["fields"][1]["interrupt"] = "IE.EN"
        self.assertEqual(codes_of(d, self.tmp), [])
        for label, patch in [("missing target", "IE.NOPE"), ("bad syntax", "ie.en"), ("unknown reg", "NOPE.EN")]:
            d = base_doc(); regs(d)[0]["fields"][1]["interrupt"] = patch
            self.expect(d, "E_INTERRUPT", label)
        d = base_doc(); regs(d)[2]["fields"][0]["access"] = "ro"; regs(d)[2]["fields"][0]["hw"] = "input"
        regs(d)[0]["fields"][1]["interrupt"] = "IE.EN"
        self.expect(d, "E_INTERRUPT", "enable is not rw")
        d = base_doc(); regs(d)[2]["fields"][0].pop("bit"); regs(d)[2]["fields"][0]["bits"] = "1:0"
        regs(d)[0]["fields"][1]["interrupt"] = "IE.EN"
        self.expect(d, "E_INTERRUPT", "width mismatch")
        d = base_doc(); regs(d)[0]["fields"][2]["interrupt"] = "IE.EN"
        self.expect(d, "E_INTERRUPT", "interrupt on an rw field")

    def test_strobes_and_gates(self):
        d = base_doc(); regs(d)[1]["write_gate"] = True
        self.expect(d, "E_GATE", "gate on a read-only register")
        d = base_doc(); regs(d)[1]["wr_strobe"] = True
        self.expect(d, "E_STROBE", "write strobe on read-only")
        d = base_doc(); regs(d)[0]["fields"] = [{"name": "GO", "bit": 0, "access": "w1p"}]; regs(d)[0]["rd_strobe"] = True
        self.expect(d, "E_STROBE", "read strobe on write-only")

    def test_identifier_collisions(self):
        d = base_doc()
        regs(d).append({"name": "CNT_0", "offset": 0x40, "access": "ro", "hw": "input"})   # collides with CNT[0]
        self.expect(d, "E_IDENT_COLLISION")
        d = base_doc()
        d["peripherals"].append({"name": "dev_x", "region": "dma", "base": 0x1_2000_1000, "size": 0x1000,
                                 "registers": [{"name": "A", "offset": 0, "access": "ro"}]})
        regs(d).append({"name": "X_A", "offset": 0x60, "access": "ro"})                  # dev_x_a == dev + X_A
        self.expect(d, "E_IDENT_COLLISION", "flattened names from different peripherals")

    # ---------------------------------------------------------------- binding
    def test_binding_rules(self):
        d = base_doc(); regs(d)[0]["fields"][0]["connect"] = {"value": "blk.go[3:0]"}
        self.assertEqual(codes_of(d, self.tmp), [], "slice accepted")
        d = base_doc(); regs(d)[0]["fields"][0]["connect"] = {"value": "blk"}
        self.expect(d, "E_BIND_SYNTAX")
        d = base_doc(); regs(d)[0]["fields"][0]["connect"] = {"value": "other.go"}
        self.expect(d, "E_BIND_MODULE")
        d = base_doc(); regs(d)[0]["fields"][0]["connect"] = {"value": "blk.nope"}
        self.expect(d, "E_BIND_PORT")
        d = base_doc(); regs(d)[0]["fields"][0]["connect"] = {"value": "blk.done"}      # bank output -> RTL output
        self.expect(d, "E_BIND_DIR", "attach: output must meet an input")
        d = base_doc(); per(d)["rtl"]["modules"][0]["role"] = "replace"
        self.expect(d, "E_BIND_DIR", "replace: directions must be equal (go is an input but the bank port is an output)")
        d = base_doc(); regs(d)[0]["fields"][0]["connect"] = {"event": "blk.go"}
        self.expect(d, "E_BIND_KIND", "rw field has no event signal")

    # ---------------------------------------------------------------- examples
    def test_examples(self):
        def ex(*steps):
            d = base_doc(); per(d)["examples"] = [{"title": "t", "steps": list(steps)}]
            return d
        self.assertEqual(codes_of(ex({"set": "CTRL.MODE", "value": 3}, {"clear": "CTRL.ST"}, {"expect": "STAT.DONE", "value": 1},
                                     {"poll": "STAT.DONE", "until": 1}, {"write": "CTRL", "value": 5},
                                     {"read": "CNT", "index": 1}), self.tmp), [])
        self.expect(ex({"set": "NOPE.X", "value": 1}), "E_EXAMPLE", "unknown register")
        self.expect(ex({"set": "STAT.DONE", "value": 1}), "E_EXAMPLE", "set on ro")
        self.expect(ex({"set": "CTRL.MODE", "value": 16}), "E_EXAMPLE", "value too wide for field")
        self.expect(ex({"clear": "CTRL.EN"}), "E_EXAMPLE", "clear on rw")
        self.expect(ex({"write": "STAT", "value": 1}), "E_EXAMPLE", "write to ro register")
        self.expect(ex({"read": "CNT"}), "E_EXAMPLE", "array without index")
        self.expect(ex({"read": "CNT", "index": 2}), "E_EXAMPLE", "index out of range")
        self.expect(ex({"set": "CTRL.MODE", "value": 1, "extra": 1}), "E_UNKNOWN_KEY")

    # ---------------------------------------------------------------- collect-all
    def test_all_problems_are_reported_together(self):
        d = base_doc()
        regs(d)[0]["fields"][2]["reset"] = 99          # E_RESET_RANGE
        regs(d)[1]["offset"] = 6                       # E_REG_ALIGN
        regs(d)[2]["fields"][0]["bits"] = "40:36"      # E_FIELD_BITS
        got = codes_of(d, self.tmp)
        for c in ("E_RESET_RANGE", "E_REG_ALIGN", "E_FIELD_BITS"):
            self.assertIn(c, got)

    def test_good_definitions_in_repo_validate(self):
        from helpers import SOC_DEF, KS_DEF
        for p in (SOC_DEF, KS_DEF):
            validate(load(p))


if __name__ == "__main__":
    unittest.main()
