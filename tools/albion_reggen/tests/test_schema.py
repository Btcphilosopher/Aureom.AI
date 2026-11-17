"""The JSON Schema accepts every definition in the repository and rejects structurally wrong ones."""

import copy
import json
import os
import unittest

from helpers import DEFS, KS_DEF, SOC_DEF, TOOL, base_doc
from albion_reggen.loader import load

try:
    import jsonschema
except Exception:  # pragma: no cover
    jsonschema = None

SCHEMA = json.load(open(os.path.join(TOOL, "schema", "regdef.schema.json")))


@unittest.skipIf(jsonschema is None, "jsonschema not installed")
class Schema(unittest.TestCase):
    def v(self, doc, ref=None):
        sch = SCHEMA if ref is None else {"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"], "$ref": ref}
        jsonschema.Draft202012Validator(sch).validate(doc)

    def bad(self, doc, ref=None):
        with self.assertRaises(jsonschema.ValidationError):
            self.v(doc, ref)

    def test_schema_itself_is_valid(self):
        jsonschema.Draft202012Validator.check_schema(SCHEMA)

    def test_all_repository_definitions_conform(self):
        top = load(SOC_DEF).root
        raw_top = [p for p in top["peripherals"]]
        # included files are validated as peripherals; the top document with includes unresolved
        import yaml
        from albion_reggen.loader import _LOADER
        self.v(yaml.load(open(SOC_DEF), Loader=_LOADER))
        for f in sorted(os.listdir(DEFS)):
            if f.endswith(".yaml") and f != "silicaflux_regs.yaml":
                d = yaml.load(open(os.path.join(DEFS, f)), Loader=_LOADER)
                self.v(d, "#/$defs/peripheral")
        self.v(yaml.load(open(KS_DEF), Loader=_LOADER))
        self.v(base_doc())

    def test_structural_errors_are_rejected(self):
        for label, edit in {
            "wrong version": lambda d: d.__setitem__("regdef_version", 2),
            "unknown top key": lambda d: d.__setitem__("bogus", 1),
            "bad map name": lambda d: d["map"].__setitem__("name", "Bad-Name"),
            "register without offset": lambda d: d["peripherals"][0]["registers"][0].pop("offset"),
            "lower-case register": lambda d: d["peripherals"][0]["registers"][0].__setitem__("name", "ctrl"),
            "register width 16": lambda d: d["peripherals"][0]["registers"][0].__setitem__("width", 16),
            "unknown access": lambda d: d["peripherals"][0]["registers"][0]["fields"][0].__setitem__("access", "rwx"),
            "field with neither bit nor bits": lambda d: d["peripherals"][0]["registers"][0]["fields"][0].pop("bit"),
            "fields and shorthand access together": lambda d: d["peripherals"][0]["registers"][0].__setitem__("access", "rw"),
            "bad connect syntax": lambda d: d["peripherals"][0]["registers"][0]["fields"][0].__setitem__("connect", {"value": "nodot"}),
            "bad rtl status": lambda d: d["peripherals"][0]["rtl"].__setitem__("status", "magic"),
            "bad sha": lambda d: d["peripherals"][0]["rtl"]["modules"][0].__setitem__("sha256", "xyz"),
            "float offset": lambda d: d["peripherals"][0]["registers"][0].__setitem__("offset", 1.5),
            "example step with two ops": lambda d: d["peripherals"][0].__setitem__("examples", [{"title": "t", "steps": [{"read": "A", "write": "B"}]}]),
        }.items():
            with self.subTest(label):
                d = copy.deepcopy(base_doc())
                edit(d)
                self.bad(d)


if __name__ == "__main__":
    unittest.main()
