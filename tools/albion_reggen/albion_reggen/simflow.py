"""Model-driven simulation of the generated RTL with Verilator.

``simulate`` writes the generated RTL and the self-checking testbench, generates
stimulus + expected values with the independent reference model, builds with
Verilator (assertions on, so the AlbionCore ALP link checker is live) and
runs.  A run passes only if every masked output bit matched in every cycle, no
ALP rule assertion fired, *and* the stimulus covered every required point.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import emit_tb
from .generate import build_outputs
from .model import RegMap
from .refmodel import missing_coverage

THIRD_PARTY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "third_party", "albioncore")
ALBION_FILES = ["sf_albion_pkg.sv", "sf_albion_chan_checker.sv", "sf_albion_link_checker.sv"]


@dataclass
class SimResult:
    passed: bool
    cycles: int = 0
    checks: int = 0
    log: str = ""
    cov: Counter = field(default_factory=Counter)
    missing: List[str] = field(default_factory=list)
    stage: str = ""          # where it failed: build | run | coverage | ""

    @property
    def ok(self) -> bool:
        return self.passed and not self.missing


def have_verilator() -> bool:
    return shutil.which("verilator") is not None


def simulate(m: RegMap, work_dir: str, seed: int = 1, cycles: int = 4000,
             mutate: Optional[Callable[[Dict[str, str]], Dict[str, str]]] = None,
             resets: int = 3, tb_edit: Optional[Callable[[str], str]] = None) -> SimResult:
    """Run one model-driven simulation.  ``mutate`` may rewrite the generated
    RTL files (name -> text) to inject a bug; the testbench and the vectors stay
    those of the unmutated definition."""
    os.makedirs(work_dir, exist_ok=True)
    outs = build_outputs(m)
    rtl = {os.path.basename(k): v for k, v in outs.items() if k.startswith("rtl/")}
    if mutate is not None:
        rtl = mutate(dict(rtl))
    files: List[str] = []
    for name, text in rtl.items():
        path = os.path.join(work_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    tb = os.path.join(work_dir, "tb_sf_reg_bank.sv")
    with open(tb, "w", encoding="utf-8") as fh:
        fh.write(tb_edit(outs["verif/tb_sf_reg_bank.sv"]) if tb_edit else outs["verif/tb_sf_reg_bank.sv"])
    g = emit_tb.generate_vectors(m, seed=seed, n_cycles=cycles, resets=resets)
    for name, text in g.files().items():
        with open(os.path.join(work_dir, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    srcs = [os.path.join(THIRD_PARTY, f) for f in ALBION_FILES]
    srcs += [os.path.join(work_dir, n) for n in ("sf_reg_pkg.sv", "sf_reg_decoder.sv", "sf_reg_interface.sv", "sf_reg_bank.sv")]
    srcs.append(tb)
    obj = os.path.join(work_dir, "obj")
    shutil.rmtree(obj, ignore_errors=True)
    b = subprocess.run(["verilator", "--binary", "--timing", "--assert", "-Wno-fatal", "-Wno-lint", "-Wno-style",
                        f"-GNCYC={g.cycles}", "--top-module", "tb_sf_reg_bank", "-Mdir", obj] + srcs,
                       capture_output=True, text=True)
    if b.returncode != 0:
        return SimResult(False, g.cycles, 0, (b.stdout + b.stderr)[-4000:], g.model.cov, [], "build")
    r = subprocess.run([os.path.join(obj, "Vtb_sf_reg_bank"),
                        f"+STIM={work_dir}/stim.hex", f"+EXP={work_dir}/exp.hex", f"+MASK={work_dir}/mask.hex"],
                       capture_output=True, text=True)
    log = (r.stdout + r.stderr)
    passed = ("TB_RESULT: PASS" in log) and ("%Error" not in log) and r.returncode == 0
    checks = 0
    for line in log.splitlines():
        if line.startswith("TB_RESULT: PASS"):
            for tok in line.split():
                if tok.startswith("checks="):
                    checks = int(tok.split("=")[1])
    miss = missing_coverage(m, g.model.cov)
    return SimResult(passed, g.cycles, checks, log[-4000:], g.model.cov, miss,
                     "" if passed else "run")
