"""
python -m silicaflux_bitcoin.verify [--out reports/verification_report.txt]

The full verification pipeline (section 36):

    Python reference (silicaflux_bitcoin.reference)
        -> test vector generator (silicaflux_bitcoin.vectors)
        -> SystemVerilog simulation (silicaflux_bitcoin.simulate, via Icarus Verilog)
        -> RTL output compared against the Python-derived expected values
           (inside each self-checking testbench, at full vector-file
           granularity -- not summarised/sampled)
        -> PASS/FAIL (this script's exit code + report)

Run end-to-end, automatically, on every invocation. Writes a
timestamped, plain-text report to reports/ and never claims a step
succeeded that it did not actually execute.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import random
import sys
import time
from pathlib import Path

from silicaflux_bitcoin.vectors.generate_vectors import generate_all
from silicaflux_bitcoin.simulate import run_manifest
from silicaflux_bitcoin.reference import sha256_model as m


def python_scale_check(scales=(10, 100, 1_000, 10_000, 100_000), seed: int = 99) -> list[dict]:
    """Section 28's 10/100/1,000/10,000/100,000+ scaling, run as a PURE
    PYTHON self-consistency check: the from-scratch golden model
    (sha256_model.sha256, never itself compared to the RTL here) against
    hashlib.sha256, an independent third-party implementation. This is
    cheap enough to genuinely reach 100,000+ vectors in seconds; the
    RTL-vs-Python comparison (silicaflux_bitcoin.simulate, via Icarus
    Verilog) is run at a smaller but still substantial scale (hundreds to
    low thousands per module -- see reports/verification_report.txt)
    because each RTL vector costs real simulator wall-clock time. Keeping
    these two counts, and what each one actually proves, clearly
    separate is deliberate -- see section 30/35's rule against mixing
    result categories.
    """
    rng = random.Random(seed)
    results = []
    for n in scales:
        t0 = time.monotonic()
        fails = 0
        for _ in range(n):
            data = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 200)))
            if m.sha256(data) != hashlib.sha256(data).digest():
                fails += 1
        dt = time.monotonic() - t0
        results.append(dict(n=n, fails=fails, seconds=round(dt, 3)))
        print(f"  [{'PASS' if fails == 0 else 'FAIL'}] {n} vectors, {fails} mismatches ({dt:.3f}s)")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the full vectors -> simulate -> PASS/FAIL verification pipeline.")
    ap.add_argument("--vectors-dir", type=Path, default=Path("tb/vectors"))
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out", type=Path, default=Path("reports/verification_report.txt"))
    args = ap.parse_args(argv)

    lines = []
    lines.append("SilicaFlux Bitcoin SHA-256 ASIC -- Verification Report")
    lines.append("=" * 56)
    lines.append(f"Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}Z")
    lines.append("")

    print("[1/3] Python golden-model self-consistency at scale (section 28: 10/100/1,000/10,000/100,000+) ...")
    scale_results = python_scale_check()
    lines.append("Stage 1: Python-only golden-model-vs-hashlib self-consistency (PYTHON scale, not RTL)")
    for r in scale_results:
        lines.append(f"  {r['n']} vectors: {r['fails']} mismatches ({r['seconds']}s)")
    scale_ok = all(r["fails"] == 0 for r in scale_results)
    lines.append("")

    print("\n[2/3] Generating test vectors from the Python golden model ...")
    counts = generate_all(args.vectors_dir, args.seed)
    lines.append("Stage 2: test-vector generation (Python golden model) for RTL simulation")
    for k, v in counts.items():
        lines.append(f"  {k}: {v} cases")
    lines.append("")

    print("\n[3/3] Compiling and running every SystemVerilog testbench (Icarus Verilog) ...")
    results = run_manifest()
    n_pass = sum(1 for r in results if r["ok"])
    n_total = len(results)
    lines.append("Stage 3: SystemVerilog simulation (Icarus Verilog) -- RTL vs Python-derived vectors")
    for r in results:
        lines.append(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['name']}  ({r['seconds']}s)")
    lines.append("")
    overall_ok = scale_ok and n_pass == n_total and n_total > 0
    lines.append(f"RESULT: Python-scale self-check {'PASS' if scale_ok else 'FAIL'}; "
                  f"RTL simulation {n_pass}/{n_total} passed; overall {'PASS' if overall_ok else 'FAIL'}")
    lines.append("")
    lines.append("These figures are SIMULATION results (Icarus Verilog), not synthesis")
    lines.append("or silicon measurements -- see reports/benchmark_report.txt and")
    lines.append("docs/architecture.md for the THEORETICAL / SIMULATION / SYNTHESIS")
    lines.append("ESTIMATE category distinctions this project maintains throughout.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n")
    print(f"\nReport written to {args.out}")
    print(f"RESULT: Python-scale self-check {'PASS' if scale_ok else 'FAIL'}; "
          f"RTL simulation {n_pass}/{n_total} passed")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
