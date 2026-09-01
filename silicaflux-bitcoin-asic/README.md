# SilicaFlux Bitcoin SHA-256 ASIC

A Bitcoin-proof-of-work-specific SHA-256 mining ASIC research platform:
a small declarative architecture layer (**SilicaFlux**) above
independently-verified, synthesizable **SystemVerilog** RTL, with a
**Python** golden model, test-vector generator, RTL simulation runner,
synthetic mining simulator, and design-space explorer.

```
SilicaFlux architecture spec  ->  IR  ->  SystemVerilog generator
                                              |
                          hand-written, independently-verified RTL
                     (SHA-256 core, pipeline, nonce, target, control, telemetry)
                                              |
                    Icarus Verilog simulation  <-  Python golden model
                                              |
                         yosys synthesis (generic cells) + verilator lint
```

Every performance figure this project reports is explicitly tagged
THEORETICAL / RTL SIMULATION / SYNTHESIS ESTIMATE — see
`docs/architecture.md` §7. **No silicon has been fabricated; no
place-and-route was run.** Nothing here should be read as a claim about
real chip performance.

## Quick start

```bash
# Requires: python3, iverilog+vvp (Icarus Verilog), verilator, yosys
#   apt-get install iverilog verilator yosys

make verify      # vectors -> RTL simulation -> reports/verification_report.txt
make lint        # verilator --lint-only over the synthesizable RTL tree
make benchmark   # reports/benchmark_report.txt (section 40 template)
make explore     # design-space sweep + real yosys synthesis -> reports/design_space_sweep.csv
```

or directly:

```bash
export PYTHONPATH=.:python
python -m silicaflux_bitcoin.generate   # SilicaFlux config -> rtl/generated/*.sv
python -m silicaflux_bitcoin.vectors    # Python golden model -> tb/vectors/*.hex
python -m silicaflux_bitcoin.simulate   # compile+run every SV testbench (Icarus Verilog)
python -m silicaflux_bitcoin.verify     # the above two, chained, + a report
python -m silicaflux_bitcoin.benchmark  # section-40 report
python -m silicaflux_bitcoin.explore    # design-space sweep + synthesis
```

## What's actually verified

Every claim below has a corresponding, re-runnable testbench — see
`docs/verification_plan.md` for the full section-45 checklist mapping
and `reports/verification_report.txt` for the literal output of the
most recent run.

- The from-scratch Python SHA-256 model reproduces `hashlib.sha256` on
  500+ NIST/random vectors and, at a separately-run larger scale,
  100,000 random messages.
- It reproduces the **real Bitcoin genesis block hash**
  (`000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f`,
  fields sourced from Bitcoin Core's `chainparams.cpp`) end-to-end
  through header serialization, double-SHA-256, and target comparison.
- The SystemVerilog RTL — Ch/Maj/Sigma, message schedule (two
  independent circuit shapes, cross-checked against each other),
  round function, iterative compressor, all 7 supported pipeline
  depths, double-hash with midstate reuse, nonce allocator (up to 64
  cores), target comparison, a full multi-core array, the top-level
  control FSM (including error handling and mid-search reset), and a
  set of protocol-invariant checks (proven non-vacuous by a deliberate
  bug-injection self-test) — matches the Python golden model bit-exactly
  on every vector actually run. **25/25** simulation runs pass as of the
  last full `make verify`.
- Two real bugs (a register-width bug in the nBits→target expansion, and
  a nonce byte-order bug in the per-core search datapath) were caught by
  this process, fixed, and re-verified — see `docs/verification_plan.md`
  for the full trace of each.

## Repository layout

```
silicaflux/          SilicaFlux architecture spec -> IR -> SV generator
rtl/                 hand-written, synthesizable SystemVerilog RTL
python/               silicaflux_bitcoin: golden model, vectors, simulator,
                       benchmarks, optimisation, analysis, CLI entry points
tb/                   SystemVerilog testbenches (unit/integration/system)
formal/               protocol-invariant checker + non-vacuousness self-test
scripts/              iverilog/verilator/yosys flow wrappers
configs/              named SilicaFlux architecture configs (YAML)
reports/              generated: verification/benchmark/design-space reports
docs/                 architecture, byte-order notes, verification plan, IR
```

## Design highlights

- **Midstate reuse** (section 14): the header's first 64 bytes are
  compressed once per job, not once per nonce trial — measured to cut
  the per-nonce cost from 198 to 132 RTL-simulated cycles (`reports/
  cycle_measurement.txt`).
- **Two core architectures**, both independently verified: an
  area-minimal ITERATIVE core (replicate many, `hash_core_array.sv`)
  and a throughput-oriented spatially-unrolled PIPELINED core
  (`sha256_pipeline.sv`, configurable depth) — see `docs/architecture.md`
  §3 for the measured area/depth tradeoff and an honest statement of
  what is and isn't integrated yet.
- **Real synthesis numbers**, not guesses: `make explore` drives actual
  yosys `synth` runs and records real cell counts (generic technology-
  independent library — see `docs/architecture.md` §8 on technology
  independence).

## A note on tooling limitations

Several real Icarus Verilog 12.0 parser/performance limitations were
found and designed around during this project (unpacked-array output
ports, array-typed `localparam` initializers, concurrent SVA,
`inside {}`, and a real performance cliff on deep unregistered
combinational chains) — each is documented at its exact RTL/testbench
site and summarized in `docs/architecture.md` §6, rather than silently
worked around with no record of why the code looks the way it does.
