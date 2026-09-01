"""
python -m silicaflux_bitcoin.benchmark [--config configs/default.yaml]
                                        [--rerun-sim] [--out reports/benchmark_report.txt]

Produces the section-40 SHA-256 ASIC DESIGN REPORT: runs the synthetic
mining simulator (section 42, artificially easy target) end to end,
combines it with the RTL-simulation-measured cycles/hash figure and a
THEORETICAL clock-frequency assumption to estimate hashrate, and
(optionally) re-runs the full RTL verification suite for a fresh
Vectors Passed/Failed count -- otherwise reuses the most recent
reports/verification_report.txt so this stays fast to iterate on.

Every figure in the emitted report is labelled with which of
THEORETICAL / RTL SIMULATION / SYNTHESIS ESTIMATE / (unavailable:
POST-LAYOUT ESTIMATE / SILICON MEASUREMENT) category it belongs to, per
section 35/40's explicit rule against mixing them.
"""
from __future__ import annotations

import argparse
import datetime
import random
import re
import sys
from pathlib import Path

from silicaflux_bitcoin.reference import block_header as bh
from silicaflux_bitcoin.simulator.mining_simulator import MiningSimulator
from silicaflux_bitcoin.benchmarks.performance_model import (
    MEASURED_CYCLES_PER_HASH_ITERATIVE, iterative_array_hashrate,
)
from silicaflux_bitcoin.analysis.area_energy_model import evaluate as area_energy_evaluate


def _demo_header(rng: random.Random) -> bh.BlockHeader:
    return bh.BlockHeader(
        version=rng.getrandbits(32),
        prev_block=bytes(rng.getrandbits(8) for _ in range(32)),
        merkle_root=bytes(rng.getrandbits(8) for _ in range(32)),
        timestamp=rng.getrandbits(32),
        bits=rng.getrandbits(32),
        nonce=0,
    )


def _read_last_verification(path: Path) -> tuple[str, str]:
    if not path.exists():
        return "not run in this invocation (see --rerun-sim, or run `python -m silicaflux_bitcoin.verify`)", ""
    text = path.read_text()
    m = re.search(r"RESULT: .*", text)
    ts = re.search(r"Generated: (.*)", text)
    result_line = m.group(0) if m else "(result line not found in report)"
    when = f" (from a run generated {ts.group(1)})" if ts else ""
    return result_line + when, text


def run_benchmark(config_name: str = "default", num_cores: int = 4, clock_mhz: float = 100.0,
                   assumed_power_watts: float | None = 0.5, seed: int = 7,
                   rerun_sim: bool = False) -> str:
    rng = random.Random(seed)

    # --- Synthetic mining demonstration (section 42) ---
    header = _demo_header(rng)
    k = 6  # ~1/64 probability per hash -> finds quickly, still a real search
    target = (1 << (256 - k)) - 1
    sim = MiningSimulator(header=header, num_cores=num_cores, nonce_start=rng.getrandbits(32) & 0xFFFFFF00,
                           nonce_stride=1, target=target, clock_mhz=clock_mhz)
    result = sim.run(max_trials_per_core=20_000)

    # --- Performance model (THEORETICAL, built on an RTL-measured cycles/hash) ---
    perf = iterative_array_hashrate(num_cores, clock_mhz, MEASURED_CYCLES_PER_HASH_ITERATIVE,
                                     power_watts=assumed_power_watts)

    # --- Area/energy (SYNTHESIS ESTIMATE for cell_count -- see design_space_explore.py;
    #     None here unless a synthesis run's output is supplied by the caller) ---
    ae = area_energy_evaluate("iterative array (%d cores)" % num_cores, perf.hashes_per_sec,
                               cell_count=None, power_watts=assumed_power_watts)

    # --- Verification status (RTL SIMULATION category) ---
    if rerun_sim:
        from silicaflux_bitcoin.verify import main as verify_main
        verify_main(["--out", "reports/verification_report.txt"])
    verif_summary, _ = _read_last_verification(Path("reports/verification_report.txt"))

    lines = []
    lines.append("SHA-256 ASIC DESIGN REPORT")
    lines.append("=" * 26)
    lines.append("")
    lines.append(f"Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}Z")
    lines.append(f"Architecture config: {config_name}")
    lines.append("")
    lines.append("Architecture: ITERATIVE core array (hash_core_array.sv), section 7/8")
    lines.append("Pipeline:     iterative (1 round/cycle); sha256_pipeline.sv (spatially")
    lines.append("              unrolled, 7 depths 1/2/4/8/16/32/64) verified standalone --")
    lines.append("              see docs/architecture.md for the integration scoping note.")
    lines.append(f"Core Count:   {num_cores}")
    lines.append("")
    lines.append("RTL: all 14 section-17 modules implemented (rtl/sha256, rtl/pipeline,")
    lines.append("     rtl/nonce, rtl/target, rtl/control, rtl/telemetry, rtl/top)")
    lines.append(f"Simulation Status: {verif_summary}")
    lines.append("")
    lines.append("Hash Throughput:")
    lines.append(f"  [THEORETICAL, built on RTL-SIMULATION-MEASURED cycles/hash] "
                  f"{perf.hashes_per_sec:,.0f} H/s at {clock_mhz:.0f} MHz assumed clock, {num_cores} cores")
    lines.append(f"  [SYNTHETIC DEMO, section 42] mining_simulator run: "
                  f"{'found' if result.found else 'NOT found'} nonce {result.nonce if result.found else '-'} "
                  f"after {result.total_hashes} total hashes "
                  f"(simulated HW time at {clock_mhz:.0f} MHz: {result.simulated_hw_seconds*1e3:.3f} ms, "
                  f"wall-clock Python time: {result.wall_clock_seconds*1e3:.3f} ms)")
    lines.append("")
    lines.append("Cycles / Hash:")
    lines.append(f"  [RTL SIMULATION, MEASURED] {MEASURED_CYCLES_PER_HASH_ITERATIVE} cycles/hash "
                  f"(iterative core, midstate-reuse path -- see reports/cycle_measurement.txt)")
    lines.append("")
    lines.append("Estimated Area:")
    lines.append("  [SYNTHESIS ESTIMATE] see reports/design_space_sweep.csv (yosys cell counts, "
                  "generic tech-independent proxy, NOT mm^2) if available; otherwise not run.")
    lines.append("")
    lines.append(f"Estimated Frequency: [THEORETICAL target, NOT a timing-closed Fmax claim] {clock_mhz:.0f} MHz")
    lines.append("")
    if assumed_power_watts:
        lines.append(f"Estimated Power: [ILLUSTRATIVE ASSUMPTION ONLY -- no technology-specific power "
                      f"analysis was run] {assumed_power_watts:.3f} W assumed")
        lines.append(f"Estimated Energy / Hash: [derived from the assumption above] "
                      f"{ae.energy_per_hash_joules:.3e} J/hash ({ae.hashes_per_watt:,.0f} H/W)")
    else:
        lines.append("Estimated Power: [not available -- no power assumption was supplied]")
        lines.append("Estimated Energy / Hash: [not available -- no power assumption was supplied]")
    lines.append("")
    lines.append("Verification:")
    lines.append(f"  {verif_summary}")
    lines.append("  (see reports/verification_report.txt for the full per-testbench breakdown,")
    lines.append("   including exact vector counts per module)")
    lines.append("")
    lines.append("IMPORTANT:")
    lines.append("These figures represent simulation/synthesis estimates unless")
    lines.append("explicitly identified as silicon measurements. No silicon measurements")
    lines.append("exist for this design -- it has not been fabricated.")

    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Produce the section-40 SHA-256 ASIC design report.")
    ap.add_argument("--config", type=str, default="default")
    ap.add_argument("--num-cores", type=int, default=4)
    ap.add_argument("--clock-mhz", type=float, default=100.0)
    ap.add_argument("--power-watts", type=float, default=0.5,
                     help="Illustrative power assumption; pass a negative value to omit power/energy figures.")
    ap.add_argument("--rerun-sim", action="store_true", help="Re-run the full RTL verification suite first.")
    ap.add_argument("--out", type=Path, default=Path("reports/benchmark_report.txt"))
    args = ap.parse_args(argv)

    power = args.power_watts if args.power_watts >= 0 else None
    report = run_benchmark(args.config, args.num_cores, args.clock_mhz, power, rerun_sim=args.rerun_sim)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report)
    print(report)
    print(f"[silicaflux.benchmark] report written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
