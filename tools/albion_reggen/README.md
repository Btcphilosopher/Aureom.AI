# RegisterWorks — `tools/albion_reggen`

**Define hardware control/status registers once; generate matching RTL, firmware interfaces and documentation.**

One validated register definition (YAML/JSON) is the only source of

| Output | Files | What it is |
|---|---|---|
| SystemVerilog | `rtl/sf_reg_bank.sv` `sf_reg_decoder.sv` `sf_reg_interface.sv` `sf_reg_pkg.sv` | synthesizable **Albion Link Protocol v1** register target: byte-enable writes, decode, reset, access permissions, bus errors, hardware/software update precedence, stall-safe response handling |
| C | `fw/c/sf_regs.h`, `sf_regs_examples.h` | address map, field masks, aligned single-access helpers, RMW that cannot clear a W1C flag or fire a pulse |
| Rust | `fw/rust/sf_regs.rs`, `sf_regs_examples.rs` | register newtypes, checked field builders, a `RegBus` trait with one alignment-checked `unsafe` `Mmio` |
| Documentation | `docs/MEMORY_MAP.md` `REGISTERS.md` `RESET_VALUES.md` `HARDWARE_PORTS.md` `FIRMWARE_EXAMPLES.md` | memory map, register/field tables with side-effect semantics, reset values, port↔RTL binding, examples |
| Verification | `verif/tb_sf_reg_bank.sv`, `tb_addr_dump.sv`, `MANIFEST.json` | self-checking testbench; SHA-256 of every input and output |

The files in `generated/` are produced from `defs/silicaflux_regs.yaml` and checked in; `make check` proves they are
current (every file carries the definition's hashes and is compared byte-for-byte).

## Quick start

```bash
pip install pyyaml                      # the only runtime dependency (JSON definitions need nothing)
make validate                           # definition valid? ALP constants = sf_albion_pkg.sv? RTL bindings real?
make gen                                # regenerate generated/
make check                              # fail if generated/ is stale
make test                               # fast verification tier
make test-slow                          # RTL mutation suite + differential tests against the real register slaves
python -m albion_reggen --help
```

```text
validate   check a definition and print a summary        check      compare generated output with disk
generate   write RTL, C, Rust, docs, MANIFEST.json       bindcheck  verify RTL bindings against the repository archives
alpcheck   verify ALP constants against sf_albion_pkg    simulate   build the RTL in Verilator and check it against the model
vectors    write model-driven test vectors
```

Tools: Python 3 (run with 3.13 only), Verilator ≥ 5.020 (simulation, lint), Yosys (synthesis checks), gcc, clang, rustc. Tests skip what is missing.

## The SilicaFlux register map

`defs/silicaflux_regs.yaml` → 8 peripherals, 193 registers, 184 hardware ports. **Each block is bound only to RTL that exists in
this repository**, with archive path, SHA-256 and real port names recorded and machine-checked (`make bind`).

| Block | Base | RTL it binds to | Integration |
|---|---|---|---|
| `sysid` System identification | `0x1_8000_0000` | `sf_albion_pkg` (ALP version, `sf_caps_t`) | **constants**, checked against the package by `alpcheck`; `REGMAP_HASH` fingerprints the map |
| `intc` Interrupt controller | `0x1_8000_1000` | `mcu_intc` | **register-compatible only** — `mcu_intc` embeds its register file, so it cannot be port-bound without splitting it (not done: implemented RTL is not modified). Proven register-equivalent by a differential test |
| `clkrst` Clock/reset status | `0x1_8000_2000` | `sf_crt_regs` | **bound** (status registers, `CLK_EN`); the keyed commands are not modelled |
| `sramc` SRAM controller | `0x1_8000_3000` | `sf_sram_subsystem` | **bound** (`src_en`, `flush`, `idle`, `sts_*`, `perf_*`) |
| `dma` DMA controller | `0x1_2000_0000` | `hpc_dma_adapter` | **bound** (descriptor, completion, status, events, 16 counters) |
| `tensor` Tensor command interface | `0x1_5000_0000` | `tsu_regs` (TENSORCORE 08) | **replaces** the hand-written slave; differential-tested against it |
| `vector` Vector command interface | `0x1_5000_1000` | `hpc_cq_mmio` (HPC command queue) | **replaces** the hand-written slave; differential-tested against it |
| `perf` Performance counters | `0x1_7000_0000` | `hpc_perf_counters` | **bound** to its `freeze_i`/`snap_i`/`irq_o`/`frozen_o`/`cnt_o` ports (23 × 64-bit live counters) |

Addresses sit in the ALP region map (`dma`, `tensor_vector`, `perf` are catalogue regions). The catalogue has no region for platform
control registers, so `sysctl` (`0x1_8000_0000`, 1 MiB, privileged, device) is **proposed by this map** — it obeys ALP-ADR-01 and is
flagged as a proposal in every document; adding it to AlbionCore's `regions.yaml` is a decision for the owner of that catalogue.

Fidelity decisions that came from reading the RTL (each has a test): the DMA `cmd_abort` is level-sensitive in the RTL so `ABORT` is a held `rw` bit,
not a pulse; SRAM `flush` is a level; SRAM `sts_*` are sticky-until-reset so they are read-only, not W1C; `DOORBELL`/`START`/`CPL_POP` are
write strobes that the hardware refuses when it cannot accept them.

## Where to read next

* [`docs/SCHEMA.md`](docs/SCHEMA.md) — the definition format and every validation rule/error code
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — ALP target design, stall handling, conflicts, firmware safety
* [`docs/VERIFICATION.md`](docs/VERIFICATION.md) — what is verified, how, with results, and what is *not* verified
* [`generated/docs/`](generated/docs/) — the generated memory map, register reference, reset values, ports, examples
* `third_party/albioncore/PROVENANCE.md` — the four vendored, unmodified AlbionCore files and their hashes

## Limits (read before relying on it)

Verification is by simulation (Verilator, two-state), the AlbionCore link checker, differential comparison with the real register slaves,
mutation testing and Yosys elaboration/synthesis checks. There is **no formal proof, no FPGA or place-and-route run, no timing, area or
power result, and no silicon**; the RTL has not been integrated into a full SilicaFlux top level. Details and the exact numbers are in
`docs/VERIFICATION.md`.
