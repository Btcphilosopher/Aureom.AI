"""Shared helpers for the RegisterWorks test-suite (standard library only)."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any, Dict, List, Optional

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(TOOL))
sys.path.insert(0, TOOL)

from albion_reggen.errors import RegDefError          # noqa: E402
from albion_reggen.loader import load                  # noqa: E402
from albion_reggen.validate import validate            # noqa: E402

DEFS = os.path.join(TOOL, "defs")
SOC_DEF = os.path.join(DEFS, "silicaflux_regs.yaml")
KS_DEF = os.path.join(TOOL, "tests", "defs", "kitchen_sink.yaml")
GENERATED = os.path.join(TOOL, "generated")
ALBION = os.path.join(TOOL, "third_party", "albioncore")


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def need(*tools: str):
    missing = [t for t in tools if not have(t)]
    return unittest.skipIf(bool(missing), "missing tool(s): " + ", ".join(missing))


_cache: Dict[str, Any] = {}


def model(path: str):
    """Validated model of a definition file (cached)."""
    if path not in _cache:
        _cache[path] = validate(load(path))
    return _cache[path]


def run(cmd: List[str], cwd: Optional[str] = None, timeout: int = 600, env: Optional[Dict[str, str]] = None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=e)


class TmpCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reggen_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# a known-good tiny definition, mutated by the validation tests
# ---------------------------------------------------------------------------
def base_doc() -> Dict[str, Any]:
    return {
        "regdef_version": 1,
        "map": {"name": "t", "version": "1.0"},
        "peripherals": [{
            "name": "dev", "region": "dma", "base": 0x1_2000_0000, "size": 0x1000,
            "rtl": {"status": "bound", "modules": [
                {"module": "blk", "role": "attach", "ports": {"go": "input", "done": "output", "pulse_in": "input"}}]},
            "registers": [
                {"name": "CTRL", "offset": 0, "fields": [
                    {"name": "EN", "bit": 0, "access": "rw", "reset": 1, "connect": {"value": "blk.go"}},
                    {"name": "ST", "bit": 1, "access": "w1c", "hw": "event"},
                    {"name": "MODE", "bits": "7:4", "access": "rw"}]},
                {"name": "STAT", "offset": 4, "fields": [
                    {"name": "DONE", "bit": 0, "access": "ro", "hw": "input", "connect": {"value": "blk.done"}}]},
                {"name": "IE", "offset": 8, "fields": [{"name": "EN", "bit": 0, "access": "rw"}]},
                {"name": "CNT", "offset": 0x10, "width": 64, "count": 2, "access": "ro", "hw": "input"},
            ],
        }],
    }


def codes_of(doc: Dict[str, Any], tmp: str, name: str = "d.json") -> List[str]:
    path = os.path.join(tmp, name)
    with open(path, "w") as fh:
        json.dump(doc, fh)
    try:
        validate(load(path))
    except RegDefError as e:
        return e.codes
    return []


def regs(doc):
    return doc["peripherals"][0]["registers"]
