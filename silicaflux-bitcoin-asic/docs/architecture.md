# SilicaFlux Bitcoin SHA-256 ASIC — Architecture

## 1. Layered view

```
SilicaFlux architecture spec (silicaflux/architecture/spec.py)
        |  MinerArchitecture: num_cores, pipeline config, nonce config,
        |  telemetry config, clock config -- one Python dataclass tree
        v
SilicaFlux compiler (silicaflux/compiler/lower.py)
        |  validates the spec, lowers it to a small hardware IR
        |  (silicaflux/ir/nodes.py: IRParam tagged DATAFLOW/PIPELINE/
        |  REGISTER/COMBINATIONAL/MEMORY/CONTROL/CLOCK/INTERFACE)
        v
SilicaFlux generator (silicaflux/generators/sv_emitter.py)
        |  deterministic IRDesign -> SystemVerilog text
        v
rtl/generated/silicaflux_config_pkg.sv
        |  `` `included by hand-written, independently-verified RTL
        v
rtl/{sha256,pipeline,nonce,target,control,telemetry,top}/*.sv
        |
tb/{unit,integration,system}/*.sv  <-- self-checking against
formal/sha256_properties.sv            python/silicaflux_bitcoin/reference
```

The SilicaFlux layer does **not** generate the hashing datapath itself.
It generates *configuration* (which core architecture, how many cores,
which pipeline depth, which message-schedule storage strategy) that the
hand-written, independently-verified RTL consumes as parameters. See
`docs/silicaflux_ir.md` for why, and section 16's "do not generate
opaque SystemVerilog" rule is the reason the generated package is a
short, commented, human-readable file rather than a wall of templated
text.

## 2. Module map (matches section 17's file list exactly)

| File | Role |
|---|---|
| `rtl/sha256/sha256_pkg.sv` | H0/K constants, `rotr32()` |
| `rtl/sha256/sha256_ch.sv`, `sha256_maj.sv`, `sha256_sigma.sv` | the six SHA-256 logical functions |
| `rtl/sha256/sha256_message_schedule.sv` | SLIDING_WINDOW schedule (registered, 16-word) |
| `rtl/sha256/sha256_schedule_step.sv` | one schedule round, purely combinational (pipeline building block) |
| `rtl/sha256/sha256_round.sv` | one compression round (T1/T2), shared by both core architectures |
| `rtl/sha256/sha256_compressor.sv` | ITERATIVE core: 1 round/cycle, round-counter FSM |
| `rtl/pipeline/sha256_pipeline.sv` | PIPELINED core: spatially unrolled, configurable depth |
| `rtl/sha256/sha256_double_hash.sv` | SHA256(SHA256(header)) + midstate reuse |
| `rtl/nonce/nonce_allocator.sv` | deterministic, duplicate-free per-core nonce ranges |
| `rtl/target/target_compare.sv` | nBits→target expansion + PoW comparison |
| `rtl/top/hash_core.sv` | one nonce-search engine (job load → search → found/exhausted) |
| `rtl/top/hash_core_array.sv` | NUM_CORES `hash_core`s + result aggregation |
| `rtl/control/miner_controller.sv` | job-level control FSM + header-loading interface |
| `rtl/telemetry/telemetry.sv` | counters/proxies, no datapath feedback |
| `rtl/top/miner_top.sv` | the design root |

## 3. Core architectures (section 7)

Two independently-verified core micro-architectures exist:

- **ITERATIVE** (`sha256_compressor.sv`): one `sha256_round` instance,
  reused 64 times via a round-counter FSM. Minimum area per core
  (measured: **11,607 generic cells**, yosys synthesis — see
  `reports/design_space_sweep.csv`), ~64 cycles per block compression
  (measured via RTL simulation: exactly 64 cycles start-to-done — see
  `reports/cycle_measurement.txt`). This is the architecture actually
  integrated into `hash_core.sv`/`miner_top.sv` and driving every
  end-to-end result in this project.

- **PIPELINED** (`sha256_pipeline.sv`): all 64 rounds spatially
  unrolled; `PIPELINE_DEPTH` (1/2/4/8/16/32/64, must divide 64) chooses
  where pipeline registers are inserted. Verified correct via RTL
  simulation at **all 7** supported depths (`reports/
  sha256_pipeline_sweep.log`). Measured area (yosys) *decreases* as
  depth decreases — fewer registers — from 341,729 cells at depth 64
  down to 280,229 cells at depth 4, while steady-state block-compression
  throughput stays depth-independent (1 new block accepted per cycle;
  only latency, `PIPELINE_DEPTH+1` cycles, changes). This is exactly the
  register-count/combinational-depth tradeoff section 7 asks for,
  measured rather than assumed.

  **Scoping decision, stated plainly**: this pipelined engine is *not*
  wired into `hash_core.sv`'s nonce search. Exploiting its 1-block/cycle
  throughput for full double-SHA-256 mining would need a multi-nonce-
  in-flight scoreboard (matching results back to the nonce that produced
  them across two data-dependent pipeline passes) that this project did
  not have the verification budget to build *and prove correct*. Per
  this project's stated priority order — correctness, then
  verification, then architecture, then throughput — shipping that
  integration unverified was judged worse than not shipping it. It
  remains a standalone, fully verified, drop-in-compatible-at-the-
  {state_in,block_bits}→state_out-level module, documented here as the
  clear next step for anyone extending this work.

## 4. Message-schedule architectures (section 6)

Three strategies are named in `silicaflux.architecture.spec.
ScheduleArchitecture`:

- `SLIDING_WINDOW` — 16-word circular register, one new word/cycle.
  Used by the ITERATIVE core. Minimum storage (16 vs. 64 words).
- `REGISTER_PIPELINED` — the same recurrence, but chained
  combinationally within a pipeline stage (`sha256_schedule_step.sv`)
  and registered only at stage boundaries. Used by the PIPELINED core.
- `FULL_COMBINATIONAL` — all of W[16..63] from W[0..15] in one
  unregistered block; this is exactly what `PIPELINE_DEPTH=1` exercises,
  and it's *why* that configuration is the slowest to simulate (see §6
  below) — a real, measured signal that it is not a realistic synthesis
  target either, not just a documentation claim.

`sha256_schedule_step.sv`'s combinational recurrence was independently
verified to agree, round-by-round, with the registered
`sha256_message_schedule.sv` implementation (`tb_sha256_schedule_step.sv`
vs. `tb_sha256_message_schedule.sv`, same 2,560 checks, same source
vectors) — two different circuit shapes computing the identical
sequence, cross-checked against each other *and* against the Python
model.

## 5. Double-SHA-256 optimisation (section 13) and midstate (section 14)

A full 80-byte header needs three 64-byte block compressions (block1,
block2, digest). Block1 depends only on fields that are constant for an
entire mining round (not the nonce) — its output, the **midstate**, is
computed once per job and reused for every nonce trial
(`sha256_double_hash.sv`'s `use_midstate`/`midstate_in`/`midstate_out`
ports, matching section 14's `midstate_load`/`midstate_valid` ask). That
cuts the per-nonce-trial cost from 3 block compressions to 2 — measured
directly: **198 cycles** cold (3-block) vs. **132 cycles** warm
(2-block, midstate reuse) — a 33% reduction, exactly the number a naive
"drop one of three sequential blocks" argument predicts, now backed by
an actual simulation run rather than just that argument.

Both remaining blocks (header block2's tail, and the digest pass's
input) have SHA-256 padding words that are **compile-time constants**
for every hash this design will ever compute (an 80-byte header and a
32-byte digest are fixed lengths) — those words are hardwired literals
in `sha256_double_hash.sv`, not registers loaded from a port. This
project verified that tie-off is *functionally* correct
(`tb_sha256_double_hash.sv`, 151 real headers including the genesis
block) and is explicit that it did **not** hand-derive the resulting
reduced boolean equations — that reduction is a synthesis-tool job, and
this project's synthesis estimates (yosys generic `synth`) reflect
whatever constant propagation yosys itself performs, not a claimed
manual optimisation.

## 6. A real, load-bearing tool limitation: Icarus Verilog and deep combinational chains

Confirmed during bring-up and load-bearing on several testbench design
choices in this repo: Icarus Verilog 12.0's event-driven simulator
becomes **very slow** (tens of seconds to minutes of wall-clock time for
microseconds of simulated time) on netlists containing one large,
**unregistered** combinational block spanning many chained SHA-256
rounds — `sha256_pipeline.sv` at `PIPELINE_DEPTH` 1/2/4 (16/32/64 rounds
chained per stage with zero intermediate flops) and the standalone
64-round combinational chain in `tb_sha256_schedule_step.sv`. This is a
**simulator performance characteristic**, not a design bug:

- `verilator --lint-only` elaborates the same `PIPELINE_DEPTH=1`
  configuration cleanly with no structural errors.
- Once run to completion (patience required, up to ~1 minute for a
  small vector count), `PIPELINE_DEPTH=1/2/4` produce bit-exact correct
  results, matching depths 8/16/32/64 exactly.

The practical consequence, stated honestly rather than hidden: depths
8/16/32/64 are verified against the **full** 404-case compressor vector
set; depths 1/2/4 are verified against a smaller (8-case) set, chosen so
the full RTL verification suite (`python -m silicaflux_bitcoin.verify`)
completes in a few minutes rather than tens of minutes. See
`tb/integration/tb_sha256_pipeline.sv`'s header comment and `reports/
sha256_pipeline_sweep.log` for exactly what ran.

Other confirmed Icarus 12.0 gaps this project designed around (all with
a comment at the affected RTL site): unpacked-array **output** ports
don't propagate values through instantiation (inputs do) — every
module boundary in `rtl/` uses packed vectors instead; `localparam
<type> name[dim] = '{...}` (array-typed localparam with a pattern
initializer) doesn't parse — `sha256_pkg.sv`'s `K` constants are a
`case`-statement lookup function instead; `property`/`assert property`/
`bind` (concurrent SVA) don't parse — `formal/sha256_properties.sv` uses
plain `always_ff` + immediate `assert (expr) else ...` instead, with a
self-test (`tb_formal_checker_selftest.sv`) proving the checks are not
vacuous; `inside {...}` doesn't parse either.

## 7. Performance-figure categories (sections 30/35/40) — never mixed

| Category | Meaning in this project | Where |
|---|---|---|
| **THEORETICAL** | A formula, given an assumed clock frequency | `performance_model.iterative_array_hashrate()` |
| **RTL SIMULATION** | An actual measured value from an Icarus Verilog run | `reports/cycle_measurement.txt`, `reports/verification_report.txt` |
| **SYNTHESIS ESTIMATE** | Actual yosys/verilator tool output against this RTL | `reports/design_space_sweep.csv` |
| **POST-LAYOUT ESTIMATE** | Not available — no place-and-route flow was run | `performance_model.post_layout_estimate()` raises `NotImplementedError` |
| **SILICON MEASUREMENT** | Not available — this design has not been fabricated | `performance_model.silicon_measurement()` raises `NotImplementedError` |

Every number in `reports/benchmark_report.txt` is explicitly tagged with
one of these. A "cycles/hash" figure being RTL-SIMULATION-measured does
not make a hashrate built on it and an assumed clock frequency anything
other than THEORETICAL overall — see `performance_model.py`'s docstring.

## 8. Technology independence (section 23)

No RTL file references a process node, standard-cell library, voltage,
or temperature. `silicaflux.architecture.spec.MinerArchitecture.
process_node` is a pure metadata string carried into the generated
package as a comment; nothing reads it. `CLOCK_FREQUENCY_TARGET_MHZ` is
documented, at its point of generation, as "abstract target only — NOT a
timing constraint." Synthesis in this project targets yosys's generic
internal cell library (`$_AND_`, `$_MUX_`, ...) specifically because it
requires no PDK — swapping in a real standard-cell library is a yosys
flow change (`synth -liberty <file>` / a different `synth_*` command
family), not an RTL change.

## 9. Power/clock gating (section 20)

`ENABLE_CLOCK_GATING` is threaded through the SilicaFlux config and
`silicaflux_config_pkg.sv` as a **research switch**; no RTL module in
this repo currently gates a clock based on it (a genuine gap, stated
plainly rather than glossed over). The architectural opportunity is
real and documented at its natural site: `sha256_message_schedule.sv`'s
sigma-function inputs are computed **every cycle regardless of whether
the schedule module is at t<15 (where the computed word is unused)** —
an operand-isolation or clock-gate on that combinational path is a
concrete, low-risk candidate for a follow-up change, left undone here
rather than implemented without the matching verification pass.
