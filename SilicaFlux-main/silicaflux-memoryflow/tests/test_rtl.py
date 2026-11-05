"""Verilator regression (fast subset by default; MF_FULL_RTL=1 runs everything)
plus mutation testing: deliberately broken RTL must be caught by its testbench."""
import os

import pytest

from conftest import needs_verilator, needs_yosys
from memoryflow.verify.rtl_runner import MUTANTS, TESTBENCHES, run_mutant, run_testbench
from memoryflow.verify.synth import synth

FAST = ["router", "bank_parity", "mbist_fault", "deadlock_fifo4"]
ALL = list(TESTBENCHES)


@needs_verilator
@pytest.mark.rtl
@pytest.mark.parametrize("name", ALL if os.environ.get("MF_FULL_RTL") else FAST)
def test_testbench(name, tmp_path):
    r = run_testbench(TESTBENCHES[name], tmp_path)
    assert r.ok, f"{name}: {r.status} (expected {r.expected}), errors={r.errors}; log {r.log_path}"
    assert r.checks > 0 or r.expected != "PASS"


@needs_verilator
@pytest.mark.rtl
@pytest.mark.slow
@pytest.mark.parametrize("mutant", ["rmw_merge_uses_raw_word", "spm_overflow_off_by_one"]
                         + (["dma_tail_strobe_off", "ecc_ignore_overall_parity"] if os.environ.get("MF_FULL_RTL") else []))
def test_mutant_is_killed(mutant, tmp_path):
    r = run_mutant(mutant, tmp_path)
    assert r.status == "FAIL" and r.errors > 0, f"mutant {mutant} survived ({MUTANTS[mutant][3]})"


@needs_yosys
@pytest.mark.slow
def test_ecc_synthesises():
    r = synth("syn_ecc64")
    assert r.ok and r.comb_ge > 500 and r.flops == 0
