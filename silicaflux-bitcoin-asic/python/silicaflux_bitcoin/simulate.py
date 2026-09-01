"""
python -m silicaflux_bitcoin.simulate [--only NAME] [--json OUT]

Compiles and runs every SystemVerilog testbench in the project through
Icarus Verilog (iverilog + vvp), the simulator this project's toolchain
targets. Each testbench is self-checking (it reads Python-golden-model-
generated vectors and compares against the RTL DUT internally, printing
`[PASS] ...` or `[FAIL] ...`); this script's job is purely to compile,
run, capture, and aggregate -- it never re-derives expected values
itself. This is the "SV simulation" stage of the verification pipeline
in section 36; python -m silicaflux_bitcoin.verify chains vectors ->
simulate together and produces the final PASS/FAIL report.

Requires: `iverilog`/`vvp` on PATH (see the top-level README for the
apt package). If they are not available, this script says so plainly
and exits non-zero -- it does not fabricate results.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

RTL = "rtl"
TB = "tb"
FORMAL = "formal"

PKG = f"{RTL}/sha256/sha256_pkg.sv"
CH = f"{RTL}/sha256/sha256_ch.sv"
MAJ = f"{RTL}/sha256/sha256_maj.sv"
SIGMA = f"{RTL}/sha256/sha256_sigma.sv"
ROUND = f"{RTL}/sha256/sha256_round.sv"
SCHED = f"{RTL}/sha256/sha256_message_schedule.sv"
SCHED_STEP = f"{RTL}/sha256/sha256_schedule_step.sv"
COMPRESSOR = f"{RTL}/sha256/sha256_compressor.sv"
DOUBLE_HASH = f"{RTL}/sha256/sha256_double_hash.sv"
PIPELINE = f"{RTL}/pipeline/sha256_pipeline.sv"
NONCE_ALLOC = f"{RTL}/nonce/nonce_allocator.sv"
TARGET_CMP = f"{RTL}/target/target_compare.sv"
HASH_CORE = f"{RTL}/top/hash_core.sv"
HASH_CORE_ARR = f"{RTL}/top/hash_core_array.sv"
MINER_CTRL = f"{RTL}/control/miner_controller.sv"
TELEMETRY = f"{RTL}/telemetry/telemetry.sv"
MINER_TOP = f"{RTL}/top/miner_top.sv"
CHECKER = f"{FORMAL}/sha256_properties.sv"

SHA_CORE_FILES = [PKG, CH, MAJ, SIGMA, ROUND, SCHED, COMPRESSOR]
DOUBLE_HASH_FILES = SHA_CORE_FILES + [DOUBLE_HASH]
HASH_CORE_FILES = DOUBLE_HASH_FILES + [TARGET_CMP, HASH_CORE]
ARRAY_FILES = HASH_CORE_FILES + [NONCE_ALLOC, HASH_CORE_ARR]
MINER_TOP_FILES = ARRAY_FILES + [MINER_CTRL, TELEMETRY, MINER_TOP]

# Each entry: name, rtl file list, tb file, optional list of `-P` parameter
# override dicts (one simulation run per dict; omit/empty = one plain run),
# timeout in seconds.
MANIFEST = [
    dict(name="tb_sha256_ch_maj", rtl=[CH, MAJ], tb=f"{TB}/unit/tb_sha256_ch_maj.sv", timeout=30),
    dict(name="tb_sha256_sigma", rtl=[PKG, SIGMA], tb=f"{TB}/unit/tb_sha256_sigma.sv", timeout=30),
    dict(name="tb_sha256_round", rtl=[PKG, CH, MAJ, SIGMA, ROUND], tb=f"{TB}/unit/tb_sha256_round.sv", timeout=30),
    dict(name="tb_sha256_message_schedule", rtl=[PKG, SIGMA, SCHED],
         tb=f"{TB}/unit/tb_sha256_message_schedule.sv", timeout=60),
    # 64 sha256_schedule_step instances chained purely combinationally
    # (by design, to test the unregistered building block sha256_pipeline
    # .sv uses within a stage) -- same "deep unregistered combinational
    # chain" Icarus performance characteristic documented at length in
    # sha256_pipeline.sv/tb_sha256_pipeline.sv; genuinely takes ~35-40s
    # wall clock even though it's a tiny amount of simulated time (40000ps).
    dict(name="tb_sha256_schedule_step", rtl=[PKG, SIGMA, SCHED_STEP],
         tb=f"{TB}/unit/tb_sha256_schedule_step.sv", timeout=90),
    dict(name="tb_nonce_allocator", rtl=[NONCE_ALLOC], tb=f"{TB}/unit/tb_nonce_allocator.sv",
         params=[{"NUM_CORES": n} for n in (1, 3, 4, 8, 16, 64)], timeout=30),
    dict(name="tb_target_compare", rtl=[TARGET_CMP], tb=f"{TB}/unit/tb_target_compare.sv", timeout=30),
    dict(name="tb_sha256_compressor", rtl=SHA_CORE_FILES, tb=f"{TB}/integration/tb_sha256_compressor.sv", timeout=60),
    dict(name="tb_sha256_double_hash", rtl=DOUBLE_HASH_FILES, tb=f"{TB}/integration/tb_sha256_double_hash.sv", timeout=60),
    dict(name="tb_sha256_pipeline", rtl=[PKG, CH, MAJ, SIGMA, ROUND, SCHED_STEP, PIPELINE],
         tb=f"{TB}/integration/tb_sha256_pipeline.sv",
         params=[
             {"PIPELINE_DEPTH": 64, "NUM_CASES": 404}, {"PIPELINE_DEPTH": 32, "NUM_CASES": 404},
             {"PIPELINE_DEPTH": 16, "NUM_CASES": 404}, {"PIPELINE_DEPTH": 8, "NUM_CASES": 404},
             {"PIPELINE_DEPTH": 4, "NUM_CASES": 8}, {"PIPELINE_DEPTH": 2, "NUM_CASES": 8},
             {"PIPELINE_DEPTH": 1, "NUM_CASES": 8},
         ], timeout=300),
    dict(name="tb_hash_core", rtl=HASH_CORE_FILES, tb=f"{TB}/integration/tb_hash_core.sv", timeout=60),
    dict(name="tb_hash_core_array", rtl=ARRAY_FILES, tb=f"{TB}/system/tb_hash_core_array.sv", timeout=60),
    dict(name="tb_miner_top", rtl=MINER_TOP_FILES + [CHECKER], tb=f"{TB}/system/tb_miner_top.sv", timeout=60),
    dict(name="tb_formal_checker_selftest", rtl=[CHECKER], tb=f"{TB}/system/tb_formal_checker_selftest.sv", timeout=30),
]


def _run_one(files: list[str], top: str | None, timeout: int, params: dict | None = None) -> tuple[bool, str, float]:
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        return False, "iverilog/vvp not found on PATH -- cannot run RTL simulation", 0.0

    vvp_path = "/tmp/silicaflux_sim.vvp"
    cmd = ["iverilog", "-g2012", "-o", vvp_path]
    if params and top:
        for k, v in params.items():
            cmd += ["-P", f"{top}.{k}={v}"]
    cmd += files

    t0 = time.monotonic()
    comp = subprocess.run(cmd, capture_output=True, text=True)
    if comp.returncode != 0:
        return False, f"COMPILE FAILED:\n{comp.stdout}\n{comp.stderr}", time.monotonic() - t0

    try:
        run = subprocess.run(["vvp", vvp_path], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {timeout}s", time.monotonic() - t0

    out = run.stdout + run.stderr
    ok = ("[PASS]" in out) and ("[FAIL]" not in out)
    return ok, out, time.monotonic() - t0


def run_manifest(only: str | None = None) -> list[dict]:
    results = []
    for entry in MANIFEST:
        if only and entry["name"] != only:
            continue
        files = entry["rtl"] + [entry["tb"]]
        top = entry["name"]
        param_sets = entry.get("params") or [None]
        for params in param_sets:
            ok, out, dt = _run_one(files, top, entry["timeout"], params)
            label = entry["name"] + (f"({params})" if params else "")
            results.append(dict(name=label, ok=ok, seconds=round(dt, 2), output=out))
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {label}  ({dt:.2f}s)")
            if not ok:
                print(out[-2000:])
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run every SystemVerilog testbench through Icarus Verilog.")
    ap.add_argument("--only", type=str, default=None, help="Run only the named testbench entry.")
    ap.add_argument("--json", type=Path, default=None, help="Write full results as JSON to this path.")
    args = ap.parse_args(argv)

    results = run_manifest(args.only)
    n_pass = sum(1 for r in results if r["ok"])
    n_total = len(results)
    print(f"\n=== {n_pass}/{n_total} simulation runs passed ===")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=2))

    return 0 if n_pass == n_total and n_total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
