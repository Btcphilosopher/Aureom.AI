"""Build and run the self-checking SystemVerilog testbenches with Verilator.

Each testbench prints ``MF_METRIC key=value`` lines and one
``MF_RESULT PASS|FAIL errors=N checks=M`` line (tb/common/tb_common.svh).
Results are returned as :class:`RtlResult` records tagged with
``Provenance.RTL_SIMULATION`` so reports never confuse them with analytical
model output or silicon measurements.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from memoryflow.provenance import Provenance
from memoryflow.verify.golden import write_vector_set

REPO = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TbSpec:
    name: str
    top: str
    files: tuple[str, ...]
    params: tuple[tuple[str, str], ...] = ()
    expect: str = "PASS"          # "PASS" or e.g. "DEADLOCK" (expected-failure scenario)
    description: str = ""
    timeout_s: int = 600


def _p(**kw: object) -> tuple[tuple[str, str], ...]:
    return tuple((k, str(v)) for k, v in kw.items())


U = "tb/unit/"
S = "tb/system/"
C = "tb/common/"

TESTBENCHES: dict[str, TbSpec] = {t.name: t for t in [
    TbSpec("ecc", "tb_ecc", (U + "tb_ecc.sv",),
           description="SECDED K=32/64 vs Python golden; exhaustive 1-bit and 2-bit injection"),
    TbSpec("sram_prims", "tb_sram_prims", (U + "tb_sram_prims.sv",),
           description="1RW inferred vs macro-tiled equivalence, 1R1W read-first, 2RW"),
    TbSpec("bank_secded", "tb_sram_bank", (U + "tb_sram_bank.sv",), _p(ECC_MODE=2),
           description="bank: SECDED, byte-enable RMW, injection, RMW-uncorrectable suppression"),
    TbSpec("bank_parity", "tb_sram_bank", (U + "tb_sram_bank.sv",), _p(ECC_MODE=1),
           description="bank: per-byte parity, native byte enables, detection"),
    TbSpec("bank_noecc_macro", "tb_sram_bank", (U + "tb_sram_bank.sv",), _p(ECC_MODE=0, IMPL=1),
           description="bank: no ECC on the foundry-macro abstraction (IMPL=1)"),
    TbSpec("spm_mod", "tb_spm", (U + "tb_spm.sv",), _p(INTERLEAVE=0),
           description="SPM random multi-port + contention + backpressure + overflow, modulo map"),
    TbSpec("spm_xor", "tb_spm", (U + "tb_spm.sv",), _p(INTERLEAVE=1),
           description="SPM same suite with XOR-hash interleave"),
    TbSpec("spm_block_8b", "tb_spm", (U + "tb_spm.sv",), _p(INTERLEAVE=2, NBANKS=8),
           description="SPM same suite, block interleave, 8 banks"),
    TbSpec("spm_rsp2", "tb_spm", (U + "tb_spm.sv",), _p(RSP_DEPTH=2),
           description="SPM with shallow response FIFO (credit-limited throughput)"),
    TbSpec("mbist_clean", "tb_mbist", (U + "tb_mbist.sv",), _p(SA_EN=0),
           description="March C- on fault-free SPM banks -> pass"),
    TbSpec("mbist_fault", "tb_mbist", (U + "tb_mbist.sv",), _p(SA_EN=1),
           description="March C- with injected stuck-at cell -> fail, bank/addr located"),
    TbSpec("router", "tb_router", (U + "tb_router.sv",),
           description="address router: ordering across unequal slave latencies, decode errors"),
    TbSpec("dma", "tb_dma", (U + "tb_dma.sv", C + "sf_extmem_model.sv"),
           description="DMA: mem2mem, ext<->SPM, 2-D, streams, boundaries, errors, IRQ, multi-channel"),
    TbSpec("accel", "tb_accel", (U + "tb_accel.sv",),
           description="tensor array vs golden (K=1,8,37), double-buffer timing, vec ops, reuse buffer"),
    TbSpec("system", "tb_system", (S + "tb_system.sv", C + "sf_extmem_model.sv"),
           description="full subsystem: GEMM with B reuse, vector add/axpy/dot, ECC + MBIST via regs"),
    TbSpec("deadlock_fifo4", "tb_deadlock", (S + "tb_deadlock.sv", C + "sf_extmem_model.sv"),
           _p(VEC_IN_FIFO=4), expect="DEADLOCK",
           description="joined-stream deadlock: operand FIFO (4) < DMA burst (16) -> watchdog fires"),
    TbSpec("param_recommended", "tb_param_smoke", (S + "tb_param_smoke.sv",),
           _p(DW=128, NBANKS=8, BDEPTH=1024, ILV=1, TR=16, TC=16, DFIFO=64),
           description="recommended prototype parameterisation: 128-bit, 8 banks XOR, 16x16 tensor, 8 lanes, FIFO 64"),
    TbSpec("param_reference", "tb_param_smoke", (S + "tb_param_smoke.sv",),
           _p(DW=64, NBANKS=4, BDEPTH=1024, ILV=0, TR=8, TC=8, DFIFO=16),
           description="same smoke test at the reference parameterisation (cross-check of the parametric TB)"),
    TbSpec("deadlock_fifo16", "tb_deadlock", (S + "tb_deadlock.sv", C + "sf_extmem_model.sv"),
           _p(VEC_IN_FIFO=16), expect="PASS",
           description="same scenario with FIFO >= burst -> completes"),
]}


@dataclass
class RtlResult:
    name: str
    status: str                 # PASS / FAIL / DEADLOCK / ERROR
    expected: str
    ok: bool
    errors: int
    checks: int
    metrics: dict[str, float] = field(default_factory=dict)
    seconds: float = 0.0
    log_path: str = ""
    description: str = ""
    provenance: str = Provenance.RTL_SIMULATION.value

    def to_dict(self) -> dict:
        return asdict(self)


_RES = re.compile(r"MF_RESULT (PASS|FAIL|DEADLOCK)(?: errors=(\d+))?(?: checks=(\d+))?")
_MET = re.compile(r"MF_METRIC (\S+)=([-+0-9.eE]+)")


def verilator_available() -> bool:
    return shutil.which("verilator") is not None


def parse_log(text: str) -> tuple[str, int, int, dict[str, float]]:
    status, errors, checks = "ERROR", -1, 0
    for m in _RES.finditer(text):
        status = m.group(1)
        errors = int(m.group(2) or 0)
        checks = int(m.group(3) or 0)
    metrics = {m.group(1): float(m.group(2)) for m in _MET.finditer(text)}
    return status, errors, checks, metrics


def build_cmd(spec: TbSpec, mdir: Path, root: Path | None = None) -> list[str]:
    root = Path(root or REPO)
    cmd = [
        "verilator", "--binary", "--timing", "--assert", "-j", str(os.cpu_count() or 2),
        "-Wno-fatal", "-Wno-lint", "-Wno-style", "-Wno-TIMESCALEMOD",
        "+incdir+" + str(root / "tb/common"), "+incdir+" + str(root / "tb/system"),
        "+incdir+" + str(root / "rtl/ecc"),
        "-f", str(root / "sim/rtl_files.f"),
        str(root / "rtl/macro_stubs/sf_macro_1rw_leaf.sv"),
    ]
    cmd += [str(root / f) for f in spec.files]
    cmd += ["--top-module", spec.top, "--Mdir", str(mdir), "-o", "Vtb"]
    for k, v in spec.params:
        cmd.append(f"-G{k}={v}")
    return cmd


def run_testbench(spec: TbSpec, build_root: Path | None = None, seed: int = 1,
                  rtl_root: Path | None = None) -> RtlResult:
    """Build + run one testbench.  ``rtl_root`` points at an alternative copy
    of the repository (used by mutation testing)."""
    root = Path(rtl_root or REPO).resolve()
    build_root = Path(build_root or REPO / "build" / "rtl").resolve()
    wd = build_root / (spec.name if seed == 1 else f"{spec.name}_s{seed}")
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True)
    write_vector_set(wd)
    t0 = time.time()
    # Verilator resolves the -f file list relative to the cwd -> run from repo.
    b = subprocess.run(build_cmd(spec, wd / "obj", root), cwd=root, capture_output=True, text=True)
    log = wd / "sim.log"
    if b.returncode != 0:
        log.write_text(b.stdout + b.stderr)
        return RtlResult(spec.name, "ERROR", spec.expect, False, -1, 0, {}, time.time() - t0,
                         str(log), spec.description)
    try:
        r = subprocess.run([str(wd / "obj" / "Vtb"), f"+verilator+seed+{seed}"], cwd=wd,
                           capture_output=True, text=True, timeout=spec.timeout_s)
        text = r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        text = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        text += "\nTIMEOUT\n"
    log.write_text(text)
    status, errors, checks, metrics = parse_log(text)
    ok = status == spec.expect and (errors == 0 or spec.expect != "PASS")
    return RtlResult(spec.name, status, spec.expect, ok, errors, checks, metrics,
                     round(time.time() - t0, 2), str(log), spec.description)


def run_all(names: list[str] | None = None, build_root: Path | None = None,
            out_json: Path | None = None) -> list[RtlResult]:
    results = []
    for n in names or list(TESTBENCHES):
        res = run_testbench(TESTBENCHES[n], build_root)
        results.append(res)
        print(f"  {n:<18} {res.status:<9} expect={res.expected:<8} "
              f"{'OK ' if res.ok else 'BAD'} checks={res.checks:<7} {res.seconds:6.1f}s")
    if out_json:
        Path(out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(out_json).write_text(json.dumps([r.to_dict() for r in results], indent=2))
    return results


# ---------------------------------------------------------------- mutation testing
MUTANTS: dict[str, tuple[str, str, str, str]] = {
    # name: (file, original text, mutated text, testbench expected to kill it)
    "rmw_merge_uses_raw_word": ("rtl/sram/sf_sram_bank.sv",
                                "s1_wdata[b*8 +: 8] : dec_data[b*8 +: 8];",
                                "s1_wdata[b*8 +: 8] : q[b*8 +: 8];", "bank_secded"),
    "spm_overflow_off_by_one": ("rtl/spm/sf_spm_banked.sv",
                                "assign p_oor[gd] = ({1'b0, a} >= (AW+1)'(CAPACITY));",
                                "assign p_oor[gd] = ({1'b0, a} > (AW+1)'(CAPACITY));", "spm_mod"),
    "dma_tail_strobe_off": ("rtl/dma/sf_dma.sv",
                            "tail_strb = (r == '0) ? {NB{1'b1}} : NB'((1 << r) - 1);",
                            "tail_strb = {NB{1'b1}};", "dma"),
    "ecc_ignore_overall_parity": ("rtl/ecc/sf_ecc_secded_dec.sv",
                                  "wire single = p_all & (~syn_nz | syn_in_rng);",
                                  "wire single = syn_nz & syn_in_rng;", "ecc"),
}


def run_mutant(name: str, workdir: Path) -> RtlResult:
    """Copy the repo, apply one mutation, run the testbench that must kill it."""
    f, orig, mut, tb = MUTANTS[name]
    workdir = Path(workdir).resolve()
    dst = workdir / f"mut_{name}"
    if dst.exists():
        shutil.rmtree(dst)
    for d in ("rtl", "tb", "sim"):
        shutil.copytree(REPO / d, dst / d)
    p = dst / f
    text = p.read_text()
    if orig not in text:
        raise ValueError(f"mutation anchor not found for {name}")
    p.write_text(text.replace(orig, mut, 1))
    res = run_testbench(TESTBENCHES[tb], workdir / "build", rtl_root=dst)
    if res.status == "ERROR":
        raise RuntimeError(f"mutant {name} did not build/run (not a kill): {res.log_path}")
    return res
