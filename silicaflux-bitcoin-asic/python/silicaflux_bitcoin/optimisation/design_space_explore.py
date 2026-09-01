"""
python -m silicaflux_bitcoin.explore [--out reports/design_space_sweep.csv] [--skip-synth]

Design-space exploration (sections 21/31/43): sweeps pipeline depth,
core count, and core architecture, and for each point runs REAL yosys
synthesis (generic technology-independent cell library -- yosys's
default `synth` flow, not any real ASIC/FPGA PDK) to get an actual,
tool-measured cell count. This is a SYNTHESIS ESTIMATE in the section-35
sense: real tool output, not a guess -- but "cell count" is not mm^2,
and there is no real standard-cell library behind it (section 23:
technology independence). If yosys is not installed, this script says so
plainly and produces no fabricated numbers (--skip-synth explicitly
opts out and marks every area column "not run").

Writes reports/design_space_sweep.csv (raw data) and prints the
section-21 area/performance tradeoff matrix via
silicaflux_bitcoin.analysis.area_energy_model.tradeoff_table().
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from silicaflux_bitcoin.benchmarks.performance_model import (
    MEASURED_CYCLES_PER_HASH_ITERATIVE, iterative_array_hashrate,
    pipelined_block_throughput_per_sec,
)
from silicaflux_bitcoin.analysis.area_energy_model import evaluate as area_energy_evaluate, tradeoff_table

RTL = "rtl"
PKG = f"{RTL}/sha256/sha256_pkg.sv"
SHA_PRIMS = [PKG, f"{RTL}/sha256/sha256_ch.sv", f"{RTL}/sha256/sha256_maj.sv", f"{RTL}/sha256/sha256_sigma.sv",
             f"{RTL}/sha256/sha256_round.sv"]
COMPRESSOR_FILES = SHA_PRIMS + [f"{RTL}/sha256/sha256_message_schedule.sv", f"{RTL}/sha256/sha256_compressor.sv"]
PIPELINE_FILES = SHA_PRIMS + [f"{RTL}/sha256/sha256_schedule_step.sv", f"{RTL}/pipeline/sha256_pipeline.sv"]
MINER_TOP_FILES = (COMPRESSOR_FILES + [f"{RTL}/sha256/sha256_double_hash.sv", f"{RTL}/target/target_compare.sv",
                    f"{RTL}/nonce/nonce_allocator.sv", f"{RTL}/top/hash_core.sv", f"{RTL}/top/hash_core_array.sv",
                    f"{RTL}/control/miner_controller.sv", f"{RTL}/telemetry/telemetry.sv", f"{RTL}/top/miner_top.sv"])

_CELL_RE = re.compile(r"Number of cells:\s+(\d+)")


def _yosys_cell_count(files: list[str], top: str, chparams: dict | None = None, timeout: int = 180) -> tuple[int | None, float]:
    if shutil.which("yosys") is None:
        return None, 0.0
    script = f"read_verilog -sv {' '.join(files)};"
    if chparams:
        for k, v in chparams.items():
            script += f" chparam -set {k} {v} {top};"
    script += f" synth -top {top}; stat"
    t0 = time.monotonic()
    try:
        proc = subprocess.run(["yosys", "-p", script], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, time.monotonic() - t0
    dt = time.monotonic() - t0
    if proc.returncode != 0:
        print(f"  yosys FAILED for top={top} chparams={chparams}:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
        return None, dt
    matches = _CELL_RE.findall(proc.stdout)
    cells = int(matches[-1]) if matches else None
    return cells, dt


def run_sweep(skip_synth: bool = False, clock_mhz: float = 100.0) -> list[dict]:
    rows = []

    def add_row(architecture: str, num_cores: int, pipeline_depth: int | None, cells: int | None,
                synth_seconds: float, hashrate_hz: float, note: str = ""):
        ae = area_energy_evaluate(architecture, hashrate_hz, cell_count=cells)
        rows.append(dict(architecture=architecture, num_cores=num_cores, pipeline_depth=pipeline_depth,
                          cells=cells, synth_seconds=round(synth_seconds, 2), hashrate_hz=hashrate_hz,
                          hashes_per_cell=ae.hashes_per_cell, note=note))

    print("[explore] ITERATIVE compressor (1 core building block) ...")
    cells, dt = (None, 0.0) if skip_synth else _yosys_cell_count(COMPRESSOR_FILES, "sha256_compressor")
    print(f"  cells={cells} ({dt:.1f}s)")
    hr = iterative_array_hashrate(1, clock_mhz, MEASURED_CYCLES_PER_HASH_ITERATIVE).hashes_per_sec
    add_row("sha256_compressor (iterative, 1x)", 1, None, cells, dt, hr,
             "cells = one round + one 16-word schedule window; area building block for the array")

    for depth in (64, 32, 16, 8, 4):
        print(f"[explore] sha256_pipeline PIPELINE_DEPTH={depth} ...")
        cells, dt = (None, 0.0) if skip_synth else _yosys_cell_count(
            PIPELINE_FILES, "sha256_pipeline", {"PIPELINE_DEPTH": depth}, timeout=180)
        print(f"  cells={cells} ({dt:.1f}s)")
        block_hz = pipelined_block_throughput_per_sec(clock_mhz)
        add_row(f"sha256_pipeline (depth={depth})", 1, depth, cells, dt, block_hz,
                 "hashrate column here is BLOCK-compression throughput, not full-hash search throughput -- see docstring")

    for num_cores in (1, 4):
        print(f"[explore] miner_top NUM_CORES={num_cores} ...")
        cells, dt = (None, 0.0) if skip_synth else _yosys_cell_count(
            MINER_TOP_FILES, "miner_top", {"NUM_CORES": num_cores}, timeout=240)
        print(f"  cells={cells} ({dt:.1f}s)")
        hr = iterative_array_hashrate(num_cores, clock_mhz, MEASURED_CYCLES_PER_HASH_ITERATIVE).hashes_per_sec
        add_row(f"miner_top (iterative array, {num_cores} cores)", num_cores, None, cells, dt, hr)

    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Design-space exploration: pipeline depth x core count x real yosys synthesis.")
    ap.add_argument("--out", type=Path, default=Path("reports/design_space_sweep.csv"))
    ap.add_argument("--skip-synth", action="store_true", help="Skip yosys entirely; area columns come back as None.")
    ap.add_argument("--clock-mhz", type=float, default=100.0)
    args = ap.parse_args(argv)

    if not args.skip_synth and shutil.which("yosys") is None:
        print("yosys not found on PATH -- area columns will be None. Pass --skip-synth to silence this, "
              "or install yosys (e.g. 'apt-get install yosys').")

    rows = run_sweep(skip_synth=args.skip_synth, clock_mhz=args.clock_mhz)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n[explore] wrote {args.out}")

    from silicaflux_bitcoin.analysis.area_energy_model import AreaEnergyResult
    results = [AreaEnergyResult(r["architecture"], r["cells"], r["hashrate_hz"], None,
                                 r["hashes_per_cell"], None, None) for r in rows]
    table = tradeoff_table(results)
    print("\n" + table)
    (args.out.parent / "design_space_tradeoff_table.txt").write_text(table + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
