"""pytest entry point for the SilicaFlux NANDLab reference verification suite.

The test bodies live in nand_flash_twin.py (REFERENCE_TESTS) so that the same
checks run with or without pytest (`python nand_flash_twin.py verify`).
The SystemVerilog regression runs when Verilator or Icarus Verilog is on PATH.
"""
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import nand_flash_twin as N  # noqa: E402


@pytest.mark.parametrize("name,area,fn", N.REFERENCE_TESTS, ids=[t[0] for t in N.REFERENCE_TESTS])
def test_reference(name, area, fn, tmp_path):
    fn(str(tmp_path))


def test_numpy_and_pure_python_paths_agree():
    if N.np is None:
        pytest.skip("numpy not installed")
    cfg = N.load_config(None, profile="stress")
    fm = N.FaultModel(cfg, 0)
    stored = bytes(range(256)) * 2 + bytes(16)
    args = (stored, 1, 7, 3, 12345, 400, True, 5000.0, 2, True)
    a = fm.sense(*args)
    saved, N.np = N.np, None
    try:
        b = fm.sense(*args)
    finally:
        N.np = saved
    assert a == b


@pytest.mark.parametrize("sim", ["verilator", "iverilog"])
def test_sv_regression(sim, tmp_path):
    if shutil.which(sim) is None or (sim == "iverilog" and shutil.which("vvp") is None):
        pytest.skip(f"{sim} not installed")
    rep = N.sv_regress(sim, str(tmp_path / f"sv_{sim}"), verbose=False)
    bad = [(p["phase"], p["cosim"]["mismatches"][:3],
            [c["name"] for c in p["tb"]["checks"] if not c["pass"]]) for p in rep["phases"] if not p["ok"]]
    assert rep["ok"], bad
