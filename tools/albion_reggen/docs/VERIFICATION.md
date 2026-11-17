# Verification

`make test` (78 tests, ~1.5 min) and `make test-slow` (5 tests, ~7 min) run everything below. All figures are from
the recorded run of this release; seeds are fixed, so a rerun reproduces them. Tools used: Verilator 5.020,
Yosys 0.33, gcc 13.3, clang 18.1, rustc 1.97, Python 3.13 (the only Python version it was run with).

## The claim being checked

> The RTL, C, Rust and documentation outputs are derived from the same validated register definition, and the
> generated RTL implements the documented semantics on the real SilicaFlux bus protocol.

| Part of the claim | Evidence |
|---|---|
| "validated" | 33 negative/positive tests, one per error code, each a minimal bad definition (`test_validation.py`); every problem is reported together; 14 structural errors also rejected by the JSON Schema (`test_schema.py`) |
| "same definition → every output" | every emitter takes only the validated `RegMap`; `check` regenerates and compares byte-for-byte; the definition/semantic hash is in every output file (`test_determinism.py`) |
| "provably consistent across languages" | C, Rust, SystemVerilog and Markdown outputs are compiled/parsed back and compared with the model and each other for **every** address, width, reset, field shift/mask, `RW_MASK`, array count/stride/bound, and the map hash (`test_crosslang.py`: the SilicaFlux map has 78 register definitions = 193 register instances and 302 field instances; plus the kitchen sink) |
| "implements the documented semantics" | cycle-accurate comparison with an independent reference model, ALP link checker live (below) |
| "on the real bus protocol" | compiled against the real `sf_albion_pkg`; the real `sf_albion_link_checker` asserts every ALP rule in every cycle; generator constants proved equal to the package (`alpcheck`) |
| "integrated only with implemented RTL" | `bindcheck` opens the repository archives and verifies SHA-256 and every declared port/direction of 8 RTL files; differential test against 3 real register slaves |
| "deterministic" | byte-identical output across runs, `PYTHONHASHSEED`s, working directories and source orderings; no timestamps/paths in any output |

## 1. Model-driven RTL simulation (`test_simulation.py`, `albion_reggen simulate`)

`sf_reg_bank` is built with Verilator (assertions on) with a generated self-checking testbench. A Python **reference model
written from the specification, not from the generated SystemVerilog**, produces stimulus and the expected value of every output in every
cycle (ready, response valid/payload, every hardware output, every interrupt); the testbench compares all masked output bits each cycle.
Stimulus is directed (every register after reset; every pattern and every single byte lane written then read back; every
permission violation; every illegal ALP request; holes; unmapped addresses; attribute/privilege/security/memory-type
perturbation; hardware gate low/high on every gated register; hardware event coinciding with a software write on every
conflict-capable field) followed by constrained-random traffic with response stalls, request gaps, random hardware inputs and
**mid-run asynchronous resets**.

| Map | Run | Cycles | Output bits compared | Coverage points missing |
|---|---|---|---|---|
| SilicaFlux (193 registers) | seed 1 / seed 2 | 5004 / 5004 | 5,142,852 / 5,148,180 | 0 of 366 |
| kitchen sink (28 registers) | seeds 1 / 2 / 3 | 5004 / 5005 / 5004 | 3,263,640 / 3,287,100 / 3,269,116 | 0 of 133 |

**Coverage is measured, not assumed.** The model counts, and the test requires: all 8 status codes; every error cause per
peripheral (region, hole, permission, gate, unmapped); a successful read of every readable register and write of every writable
register; every write/clear/set/pulse operation of every field; every hardware-update event; every hardware/software conflict with
its precedence; every gate refusal; every strobe; request and response stalls; a reset during operation. Complete coverage was
checked over 72 (map, length, seed) combinations. A test run fails if any point is missing.

**What the testbench enforces on the link** (AlbionCore `sf_albion_link_checker`, immediate assertions every cycle): request and
response held until accepted, outstanding limit, tag uniqueness and echo, no response before its request, in-order completion,
response operation echo, well-formed responses (non-OKAY ⇒ zero data), zero data in lanes not enabled, legality-precedence of illegal
requests, valids low in reset. Capacity 2 is accepted and capacity 1 is rejected (`a_alp_out_01`) — see ARCHITECTURE.md.

## 2. Mutation testing of the verification (`test_mutation.py`)

29 realistic bugs are injected one at a time into the generated RTL of the kitchen sink; **29/29 are detected**, and the unmutated
design passes. They cover the handshake (ready always high, ready ignoring `rsp_ready`, data returned on error, wrong `is_write`,
tag not echoed, response dropped early, legality skipped), the decoder (holes ignored, permissions ignored, region check off,
lane mask too short, wrong word compare), and the bank (side effect on an error response, gate ignored, no lane mask on read,
byte enables ignored, wrong reset value, rw / w1c / w1s precedence flipped, W1C that clears zeros, sticky pulse, write strobe on
read, read strobe on write, missing strobe, hardware update ignored, field misplaced, interrupt term dropped, async reset removed).
A harness that reports `BADPATTERN`/`BUILDFAIL` separately from `SURVIVED` makes a broken mutant visible instead of counting it.
Two early candidates *survived* and were analysed rather than ignored: a write strobe that also fires on read of a register that
has no readable field cannot differ, because that read is refused and never commits — equivalent mutants. They were replaced by
mutants on a register that is both readable and writable (the kitchen sink gained such a register for this purpose).

## 3. Differential test against the real register slaves (`test_differential.py`)

The generated bank (whole SilicaFlux map) and the **unmodified hand-written slave** are driven with identical accesses and
identical hardware inputs; for every access the refusal outcome, the read data, every hardware output (pulses one cycle later for
the bank, levels, interrupt) are compared, and the full readable register file is compared every 8 accesses.

| Block | Real RTL | Accesses (2 seeds) | Pulse comparisons | Result |
|---|---|---|---|---|
| vector command interface | `hpc_cq_mmio` | 2 × 13,804 | 2 × 55,216 | identical |
| tensor command interface | `tsu_regs` | 2 × 23,852 | 2 × 119,260 | identical |
| interrupt controller | `mcu_intc` (via its probed registers) | 2 × 5,012 | – | identical |

Two differences are **by design** and asserted explicitly in the harness rather than excluded: a read of a write-only register
(`DOORBELL`, `CPL_POP`) returns 0 without error in the slaves and is refused (`ACCESS_DENIED`) by the bank; the bank's pulses are
registered. One input had to be constrained to what the hardware can drive: `tsu_regs.status` bit 7 and bits 15:12 are constant 0
in `silicaflux_tensor_unit`, so they are not randomised (a first run without that constraint reported them as differences; reading the
unit's RTL showed the hardware never produces them). The flow itself is proven to fail: an injected inverted interrupt-status
precedence and a wrong reset value are both caught.

## 4. Binding and protocol conformance (`test_bind_alp.py`)

* `bindcheck`: 8 modules (`sf_sram_subsystem`, `hpc_dma_adapter`, `tsu_regs`, `hpc_cq_mmio`, `mcu_intc`, `hpc_perf_counters`,
  `sf_crt_regs`, package `sf_albion_pkg`) found in the repository archives, SHA-256 equal to the recorded one, every declared port
  present with the declared direction. Tampering (wrong hash, missing port, wrong direction, phantom module) is detected.
* `alpcheck`: opcode, status, domain, attribute, region-attribute and request/response layout constants of the generator equal
  `sf_albion_pkg.sv`; `SYSID.ALP_VERSION`, `LIB_VERSION` and every field of `ALP_CAPS` equal the package's `sf_caps_t` layout and
  constants. 14 kinds of drift (renumbered status, moved field, changed opcode, bumped version, changed features, changed layout…) are detected.
* The four vendored AlbionCore files are byte-identical to the archive members (`third_party/albioncore/PROVENANCE.md`).
* Fidelity decisions taken from the RTL are asserted: DMA `ABORT` is a level, SRAM `flush` is a level, SRAM sticky status is read-only,
  gated strobes have a gate, `mcu_intc` is declared `register_compatible` (not falsely port-bound).

## 5. RTL hygiene (`test_rtl_quality.py`)

Verilator `-Wall`: **0 warnings** (SilicaFlux map and kitchen sink). Yosys 0.33: elaborates, `check -assert` passes (no combinational loops),
no latches, **every flip-flop is asynchronous-reset** (`$adff` only), maps to generic gates (`sf_reg_bank` of the SilicaFlux map: 883 storage flip-flops, plus the response register in `sf_reg_interface`; the numbers
are technology-independent and are not an area or timing claim).

## 6. Firmware (`test_firmware.py`)

* C: compiles clean as C99, C11 and C++17 under `-Wall -Wextra -Werror -Wpedantic` (+ `-Wconversion -Wshadow` for C11) with gcc and
  `-Weverything` with clang (this found two real nits in the first version of the access primitives, fixed).
* C behaviour on a logging mock bus under AddressSanitizer + UBSan, built for both 32-bit (split 64-bit access) and 64-bit initiators: an
  `rw` field update does not write back a set W1C flag; clearing a W1C flag preserves `rw` bits; write-one-only registers are never read back;
  a rw+pulse register keeps data when pulsing and does not pulse when setting data; 64-bit write order is low-then-high; a counter that rolls
  over between the halves is read without tearing (high-low-high); out-of-range array indices fault; **every logged access is naturally
  aligned and of the register's width**.
* Rust: 12 behaviour tests on a mock `RegBus` (same RMW-safety, `FieldOverflow` instead of truncation and nothing written on
  rejection, `IndexError`, 64-bit ordering and tearing, alignment) and `Mmio` panics on a misaligned address before touching memory.
* `sf_regs_hardware_matches()` / `hardware_matches()` accept the hash they were built from and reject a one-bit difference.
* Unsafe helpers are *absent*: registers with read side effects or stored write-only fields have no RMW helpers.
* Every firmware example of the definition compiles in C and Rust.

## What is not verified (and why it matters)

* **Simulation only.** No formal proof of the ALP rules, no equivalence check; Verilator is two-state, so X-propagation and metastability are
  not modelled. Reset behaviour is verified against the model including asynchronous mid-run resets, but not with a CDC/reset-domain tool.
* **No FPGA, place-and-route, timing, area or power result, and no silicon.** Yosys figures are generic gate counts.
* **Not integrated into a full SilicaFlux top level.** The bank is verified standalone, against the models of the blocks' control surfaces and (for `hpc_cq_mmio`,
  `tsu_regs`, `mcu_intc`) against the real slaves — not wired to the real `sf_sram_subsystem`, `hpc_dma_adapter`, `hpc_perf_counters` or
  `sf_crt_regs` in simulation. The binding to those four is a checked *interface* binding (signal names, directions, SHA-256), not a co-simulation.
* **`mcu_intc` is not port-bound**: it embeds its register file, so using the bank for it needs that RTL split first (not done; implemented RTL is not modified).
* **Not described** because the generator cannot model them: keyed commands (`SW_RST`, `WDOG_KICK`), CDC command channels (`CAUSE` clear,
  `WDOG_CTRL`), `hpc_perf_counters`' own register page (`CNT_EN`, `SAT`, `OVF`, snapshot/latched windows, preload).
* **Register slaves differ in two documented ways** (reads of write-only registers; registered pulses) — see section 3.
* **Icarus Verilog** cannot parse `sf_albion_pkg.sv` (an upstream package, unmodified), so the flow is Verilator + Yosys, as AlbionCore's own.
* The proposed `sysctl` region is **not yet in AlbionCore's `regions.yaml`**; the addresses of `sysid`, `intc`, `clkrst`, `sramc` are therefore
  provisional until the owner of that catalogue accepts or moves it. The other four peripherals use catalogue regions.
