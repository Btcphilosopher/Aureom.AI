"""Run self-checking testbenches against the EXISTING SilicaFlux RTL.

    memoryflow sf-char [NAME ...]

Every DUT file is taken byte-for-byte from the repository (via
:mod:`memoryflow.silicaflux.sources`); the testbenches live in
``tb/silicaflux/``.  Results are ``RTL_SIMULATION`` records, exactly like the
MemoryFlow regression, and feed :mod:`memoryflow.silicaflux.baselines`.

``expect`` may be ``DEFECT``: the testbench reproduces a functional defect of
the repository RTL and reports ``MF_RESULT DEFECT``; the run is OK when the
defect is reproduced (so a future fix shows up as a changed expectation, not
as silence).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from memoryflow.silicaflux.sources import MF_ROOT, find_file, materialise, silicaflux_root
from memoryflow.verify.rtl_runner import RtlResult, parse_log

TB = "tb/silicaflux/"


@dataclass(frozen=True)
class SfTbSpec:
    name: str
    top: str
    tb_files: tuple[str, ...]
    sf_files: tuple[tuple[str, str], ...]          # (source set, origin suffix), compile order
    mf_rtl: bool = False                           # also compile MemoryFlow's own RTL
    mf_files: tuple[str, ...] = ()                 # extra MemoryFlow files (beyond sim/rtl_files.f)
    params: tuple[tuple[str, str], ...] = ()
    expect: str = "PASS"
    description: str = ""
    timeout_s: int = 900


G1 = "silicaflux.zip::silicaflux/rtl/"
PKG_MC = ("sf25", "silicaflux_pkg (1).sf")          # memory-subsystem types (memory_controller.sf)
PKG_FULL = ("sf25", "silicaflux_pkg.sf")            # architectural package (tensor / vector units)

CHAR_TBS: dict[str, SfTbSpec] = {t.name: t for t in [
    SfTbSpec("sf25_memctrl", "tb_sf25_memctrl", (TB + "tb_sf25_memctrl.sv",),
             (PKG_MC, ("sf25", "memory_controller.sf")),
             description="SilicaFlux 2.5 banked SPM controller: latency, streaming, burst-length sweep, bank "
                         "contention, random traffic + backpressure, boundaries/overflow, parity, burst kill"),
    SfTbSpec("sf25_tensor", "tb_sf25_tensor", (TB + "tb_sf25_tensor.sv",),
             (PKG_FULL, ("sf25", "tensor_unit.sf")),
             description="SilicaFlux 2.5 tensor unit (4x4x4 INT8): golden results, wrap/saturate, latency, "
                         "sustained issue rate with and without result backpressure"),
    SfTbSpec("sf1_memctrl", "tb_sf1_memctrl", (TB + "tb_sf1_memctrl.sv",),
             (("sf1", G1 + "memory_controller.sv"),), expect="DEFECT",
             description="SilicaFlux v1 tile memory controller: latency / bandwidth; reproduces the DFLOAD/"
                         "DFSTORE > 4-word burst defect"),
    SfTbSpec("sf1_tensor", "tb_sf1_tensor", (TB + "tb_sf1_tensor.sv",),
             (("sf1", G1 + "tensor_unit.sv"),),
             description="SilicaFlux v1 sequential tensor unit: golden results and start-to-done latency"),
    SfTbSpec("sf25_dma_bridge", "tb_sf25_dma_bridge", (TB + "tb_sf25_dma_bridge.sv", "tb/common/sf_extmem_model.sv"),
             (PKG_MC, ("sf25", "memory_controller.sf")), mf_rtl=True,
             mf_files=("rtl/bridge/sf_mc25_vport_bridge.sv",),
             description="MemoryFlow sf_dma moving data DRAM <-> the unmodified SilicaFlux 2.5 SPM through "
                         "sf_mc25_vport_bridge; read back through the SilicaFlux scalar port"),
]}


_SETS: dict[str, object] = {}


def _sf_path(set_key: str, origin: str) -> Path:
    if set_key not in _SETS:
        _SETS[set_key] = materialise(set_key)
    m = _SETS[set_key]
    exact = [f for f in m.files if f.origin == origin]
    f = exact[0] if exact else find_file(m, origin)
    return MF_ROOT / f.path


def available() -> bool:
    return silicaflux_root() is not None and shutil.which("verilator") is not None


def build_cmd(spec: SfTbSpec, mdir: Path) -> list[str]:
    sf = [_sf_path(k, o) for k, o in spec.sf_files]
    inc = sorted({str(p.parent) for p in sf})
    cmd = ["verilator", "--binary", "--timing", "--assert", "-j", str(os.cpu_count() or 2),
           "-Wno-fatal", "-Wno-lint", "-Wno-style", "-Wno-TIMESCALEMOD", "+systemverilogext+sf",
           "+incdir+" + str(MF_ROOT / "tb/common"), "+incdir+" + str(MF_ROOT / "rtl/ecc")]
    cmd += ["+incdir+" + d for d in inc]
    if spec.mf_rtl:
        cmd += ["-f", str(MF_ROOT / "sim/rtl_files.f"), str(MF_ROOT / "rtl/macro_stubs/sf_macro_1rw_leaf.sv")]
    cmd += [str(p) for p in sf]                       # repository packages/RTL first ...
    cmd += [str(MF_ROOT / f) for f in spec.mf_files]  # ... then MemoryFlow blocks that import them
    cmd += [str(MF_ROOT / f) for f in spec.tb_files]
    cmd += ["--top-module", spec.top, "--Mdir", str(mdir), "-o", "Vtb"]
    cmd += [f"-G{k}={v}" for k, v in spec.params]
    return cmd


def run_char(spec: SfTbSpec, build_root: Path | None = None, seed: int = 1) -> RtlResult:
    wd = Path(build_root or MF_ROOT / "build" / "sf_char").resolve() / spec.name
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True)
    t0 = time.time()
    b = subprocess.run(build_cmd(spec, wd / "obj"), cwd=MF_ROOT, capture_output=True, text=True)
    log = wd / "sim.log"
    if b.returncode != 0:
        log.write_text(b.stdout + b.stderr)
        return RtlResult(spec.name, "ERROR", spec.expect, False, -1, 0, {}, time.time() - t0, str(log),
                         spec.description)
    try:
        r = subprocess.run([str(wd / "obj" / "Vtb"), f"+verilator+seed+{seed}", f"+seed={seed}"], cwd=wd,
                           capture_output=True, text=True, timeout=spec.timeout_s)
        text = r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        text = (e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")) + "\nTIMEOUT\n"
    log.write_text(text)
    status, errors, checks, metrics = parse_log(text.replace("MF_RESULT DEFECT", "MF_RESULT DEADLOCK"))
    status = "DEFECT" if "MF_RESULT DEFECT" in text else status
    ok = status == spec.expect and (errors == 0 or spec.expect != "PASS")
    return RtlResult(spec.name, status, spec.expect, ok, errors, checks, metrics, round(time.time() - t0, 2),
                     str(log), spec.description)


def run_all(names: list[str] | None = None, out_json: Path | None = None, verbose: bool = True) -> list[RtlResult]:
    res = []
    for n in names or list(CHAR_TBS):
        r = run_char(CHAR_TBS[n])
        res.append(r)
        if verbose:
            print(f"  {n:<18} {r.status:<8} expect={r.expected:<7} {'OK ' if r.ok else 'BAD'} "
                  f"checks={r.checks:<7} {r.seconds:6.1f}s")
    if out_json:
        Path(out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(out_json).write_text(json.dumps([r.to_dict() for r in res], indent=1))
    return res


def load_results(path: Path | None = None) -> dict[str, dict]:
    p = Path(path or MF_ROOT / "build" / "sf_char_results.json")
    if not p.exists():
        p = MF_ROOT / "reports" / "data" / "sf_char_results.json"
    if not p.exists():
        return {}
    return {d["name"]: d for d in json.loads(p.read_text())}
