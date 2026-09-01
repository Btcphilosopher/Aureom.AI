# Verification plan and what actually ran (section 45)

This document maps section 45's checklist to what this project actually
executed. Every "done" item below has a corresponding testbench file and
was run via `python -m silicaflux_bitcoin.verify` — see
`reports/verification_report.txt` for the literal output of the most
recent full run, not a paraphrase of it.

| # | Checklist item | Status | Evidence |
|---|---|---|---|
| 1 | Generate the RTL | done | `silicaflux/generators/sv_emitter.py`; hand-written RTL in `rtl/` (see `docs/silicaflux_ir.md` for the split) |
| 2 | Compile it | done | Every testbench run compiles all its RTL deps via `iverilog -g2012` first; `scripts/run_lint.sh` (verilator) additionally elaborates the whole tree |
| 3 | Run unit tests | done | `tb/unit/*.sv`: Ch/Maj/Sigma/round/schedule/schedule_step/nonce_allocator/target_compare |
| 4 | SHA-256 known-answer tests | done | empty string, "abc", NIST 2-block vector, multi-block random — `tb_sha256_compressor.sv` |
| 5 | Bitcoin double-SHA-256 tests | done | 151 real headers incl. the actual genesis block (fields from Bitcoin Core's `chainparams.cpp`; resulting hash independently reproduced: `000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f`) — `tb_sha256_double_hash.sv` |
| 6 | Randomised RTL-vs-Python | done | every `tb/unit` and `tb/integration` testbench compares RTL against vectors generated fresh from the Python golden model each run — see counts below |
| 7 | Test nonce allocation | done | `tb_nonce_allocator.sv`: init/step formulas + no-duplicate check (6 scenarios × 6 rounds), at 6 different `NUM_CORES` values incl. a 32-bit-wraparound case |
| 8 | Test target comparison | done | `tb_target_compare.sv`: nbits_expand (157 cases, incl. deliberately unrealistic exponents that caught a real width bug — see below) + target_compare (154 cases) |
| 9 | Test pipeline reset | done | `tb_miner_top.sv` scenario 3: reset asserted mid-search, FSM returns to clean IDLE, re-verified fully usable afterward |
| 10 | Test multiple cores | done | `tb_hash_core_array.sv` (4-core real parallel search + search_exhausted), `tb_miner_top.sv` (full stack), `tb_nonce_allocator.sv` up to 64 cores |
| 11 | Run the synthetic mining simulator | done | `python/silicaflux_bitcoin/simulator/mining_simulator.py`, driven from `benchmark.py`; also exercised end-to-end through real RTL in `tb_miner_top.sv` scenario 1 |
| 12 | Run performance benchmarks | done | `python -m silicaflux_bitcoin.benchmark` → `reports/benchmark_report.txt`, built on RTL-simulation-measured cycle counts (`reports/cycle_measurement.txt`) |
| 13 | Run available synthesis/lint checks | done | `scripts/run_lint.sh` (verilator, clean); `python -m silicaflux_bitcoin.explore` (real yosys synthesis, `reports/design_space_sweep.csv`) |
| 14 | Fix failures | done | see "Bugs this verification process actually caught" below — every one was fixed and re-verified, not worked around |
| 15 | Re-run the complete test suite | done | `reports/verification_report.txt` reflects the state *after* every fix below, not before |

## Vector counts (section 28's 10/100/1,000/10,000/100,000+ scaling)

Two genuinely different things are scaled, and this project is careful
not to blur them into one number (section 30/35's rule):

- **Python-only golden-model-vs-hashlib self-consistency** (cheap: no
  RTL simulator involved) — run at the full 10 / 100 / 1,000 / 10,000 /
  100,000 progression. `python -m silicaflux_bitcoin.verify` stage 1;
  ~40s for the 100,000 tier.
- **RTL-vs-Python** (each vector costs real Icarus Verilog wall-clock
  time) — run at hundreds to low thousands per module: Ch/Maj/Sigma/
  round ~5,000 each, message-schedule 40 blocks × 64 rounds = 2,560
  checks, compressor ~3,950, double-hash ~800, hash_core 6 full search
  scenarios (2–46 trials each, chosen to be deterministic rather than
  padded), hash_core_array/miner_top 1 full end-to-end scenario each
  (deterministic, computed by simulating every core's own sequence in
  Python, not assumed).

## Bugs this verification process actually caught

Stated here because "we tested it and it was already correct" would be
a less useful record than what verification is actually *for*:

1. **nBits shift-amount register too narrow** (`target_compare.sv`):
   an 8-bit `shift_bytes` register silently wrapped for
   unrealistic-but-possible exponent values ≥35. Caught by
   `gen_nbits_expand_vectors()` deliberately sweeping the full byte
   range rather than only realistic Bitcoin difficulties. Fixed by
   widening to 16 bits.
2. **Nonce byte-order** (`hash_core.sv`): the arithmetic nonce counter
   was fed directly into the hashing datapath without the byte-swap
   every other wire-sourced input already gets "for free" from being
   sliced out of a real serialized byte string. Caught by
   `tb_hash_core.sv` finding a real-but-wrong nonce at a different trial
   count than the Python model predicted. See
   `docs/sha256_spec_notes.md` §5 for the full writeup — kept as the
   canonical example of why every byte-order boundary here is vector-
   tested rather than "obviously correct."
3. **Two test-generation bugs** (not RTL bugs, but worth recording
   since they produced real, confusing failures before being traced):
   a target-compare edge case computed its Python expectation via a
   different digest byte-order convention than the RTL vector used
   (§gen_target_compare_vectors' fix comment has the full trace); an
   early hash_core vector generator set a target equal to a specific
   trial's own hash value and wrongly assumed no *earlier* trial could
   also satisfy it (a target that's just "a typical hash value" is met
   by roughly half of independent random hashes, not "extremely
   unlikely") — replaced with genuinely small targets and a real
   forward search for the true first match.

None of these were left as "known issues" — each has a fix in the RTL
or vector-generation code and a clean re-run recorded in
`reports/verification_report.txt`.

## What was NOT run, stated plainly

- No formal (proof) tool, e.g. SymbiYosys/an SVA model checker — see
  `formal/sha256_properties.sv`'s header comment for why (Icarus
  Verilog 12.0, this project's simulator, does not parse concurrent SVA
  at all) and what was done instead (immediate-assertion checks,
  self-tested for non-vacuousness in `tb_formal_checker_selftest.sv`).
- No place-and-route / static timing analysis against a real standard-
  cell library — `performance_model.post_layout_estimate()` raises
  `NotImplementedError` rather than fabricate a number.
- No silicon — this design has not been fabricated.
- `sha256_pipeline.sv` at `PIPELINE_DEPTH` 1/2/4 is verified at a
  smaller vector count (8 cases) than depths 8/16/32/64 (404 cases),
  for the Icarus-performance reason documented in
  `docs/architecture.md` §6, not a correctness concern (all 7 depths
  produce bit-exact-matching results on every case actually run).
