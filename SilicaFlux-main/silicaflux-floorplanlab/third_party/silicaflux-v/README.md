# SilicaFlux-V — minimal commercially meaningful SilicaFlux processor

SilicaFlux-V is a synthesis-ready RTL release of the smallest SilicaFlux
configuration that keeps the architecture's identity — **CPU + vector engine +
tensor engine + on-chip memory + interconnect** — for a first multi-project-
wafer (MPW) tape-out:

* RV32I_Zicsr control processor (2-stage, precise traps, MEI/MTI/MSI)
* 4-lane 32-bit SIMD vector engine (ADD…DOT) and 4×4 INT8 tensor MAC engine,
  deterministic latency, sharing a 16 KiB banked tile scratchpad
* 128 KiB SRAM in 4 banks, 4 KiB boot ROM, 3×7 SFB crossbar with bus-error
  reporting and execute-never peripheral window
* UART, SPI (flash boot), 8 GPIO, CLINT-style timer, interrupt controller,
  JTAG TAP with system-bus access, March C- MBIST, test mode, ICG clock gating
* 21 mandatory signal pins, single clock, no PLL, no third-party IP

Status of this release: **synthesis-ready RTL with verified firmware boot in
simulation; NOT tape-out ready** (physical signoff, foundry IP and production
test remain — see [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) and
[docs/ISSUE_REGISTER.md](docs/ISSUE_REGISTER.md)).

## Repository layout
```
rtl/        synthesizable SystemVerilog (files.f = compile order)
  pkg/ common/ cpu/ bus/ mem/ periph/ accel/ debug/ top/
tb/         cpu/ (riscv-tests harness)  soc/ (firmware-level SoC testbench)
            unit/ (cocotb tests)  models/ (Python golden models)
formal/     SymbiYosys harnesses (.sby)
firmware/   boot ROM, acceptance app, common library, linker scripts
fpga/ulx3s/ ECP5 top, constraints, Makefile
asic/       configs/ (sky130hd, ihp_sg13g2, commercial 130/65 nm templates)
            tech/<pdk>/ (ICG + SRAM macro wrappers)  scripts/  constraints/
pdk/        how to fetch public PDK collateral (nothing committed)
scripts/    lint, regression, ROM/image generators, intake, summaries
docs/       specifications and reports (index below)
reports/    tool output of this release (lint, sim, formal, fpga, synth)
ci/         CI workflow
```

## Prerequisites (versions used: [docs/TOOL_VERSIONS.md](docs/TOOL_VERSIONS.md))
Verilator ≥ 5.020, Icarus 12, Yosys 0.33, clang/lld ≥ 16 (RISC-V target),
Python 3 + cocotb 1.9, SymbiYosys (tag `yosys-0.33`) + z3; optional
nextpnr-ecp5 + Trellis (FPGA), OpenROAD/OpenSTA (ASIC),
riscv-tests (`pdk/fetch_open_pdks.sh` fetches tests + PDK collateral).

## Build and test commands
```bash
make fw                                   # firmware + generated ROM RTL
make lint                                 # Verilator -Wall + Yosys elaboration/latch check
make cpu-tests RISCV_TESTS=<riscv-tests>  # official ISA tests on the CPU
make soc-sim                              # 6 end-to-end firmware scenarios
make unit                                 # cocotb: tile, xbar, peripherals, MBIST
make formal                               # SymbiYosys proofs
make regress RISCV_TESTS=…                # all of the above -> reports/REGRESSION_SUMMARY.md
make fpga                                 # ULX3S bitstream -> build/fpga/sfv_ulx3s.bit
PLATFORMS=<orfs>/flow/platforms STA=<sta> asic/scripts/run_asic.sh ihp_sg13g2   # synth + STA
PLATFORMS=… OPENROAD=<openroad> asic/scripts/run_place.sh ihp_sg13g2           # placement estimate
```
Single SoC simulation: `build/soc/obj/vtb_soc +boot=0 +flash=build/fw/app_flash.hex`
(boot 0 SPI, 1 JTAG with `+jtag=1 +sram=…`, 2 POST, 3 SRAM with `+sram=…`).

## Parameter configuration (`rtl/top/sfv_soc.sv`)
| Parameter | Default | Notes |
|---|---|---|
| `SRAM_BANKS` × `SRAM_BANK_WORDS` | 4 × 8192 | 128 KiB; firmware linker scripts assume 128 KiB |
| `TSPM_WORDS` | 4096 | 16 KiB tile scratchpad |
| `ROM_WORDS` | 1024 | 4 KiB ROM window |
| `LANES`, `MUL_W` | 4, 32 | vector width / multiplier width (LANES = 4 required by the tensor engine) |
| `GPIO_N` | 8 | |
| `UART_BAUD_RESET` | 217 | bit period after reset (115200 Bd @ 25 MHz) |
| `sfv_cpu.RV32E` | 0 | 1 = 16 registers (area option) |
Defines: `SFV_SRAM_MACRO` (foundry macro wrappers), `SFV_NO_CLOCK_GATE` (FPGA),
`SYNTHESIS` (excludes simulation-only fault injection).

## Documentation index
| Document | Content |
|---|---|
| [REPO_INTAKE.md](docs/REPO_INTAKE.md) | forensic intake of the SilicaFlux repository, module reuse matrix |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | block diagram, configuration, pin list |
| [ISA_AND_EXCEPTIONS.md](docs/ISA_AND_EXCEPTIONS.md) | ISA, CSRs, exception and interrupt model, CPI |
| [BUS.md](docs/BUS.md) | SFB protocol and register bus |
| [MEMORY_MAP.md](docs/MEMORY_MAP.md) | memory map and register maps |
| [ACCELERATORS.md](docs/ACCELERATORS.md) | vector/tensor programming model, latency formulas |
| [CLOCK_RESET.md](docs/CLOCK_RESET.md) | clocks, resets, CDC |
| [DFT.md](docs/DFT.md) | JTAG, MBIST, test mode, scan readiness, remaining DFT work |
| [FIRMWARE.md](docs/FIRMWARE.md) | toolchain, boot ROM, boot image format, acceptance app |
| [VERIFICATION_REPORT.md](docs/VERIFICATION_REPORT.md) | test inventory and results |
| [FPGA.md](docs/FPGA.md) | ULX3S build, pins, bring-up/diagnostics |
| [ASIC_FLOW.md](docs/ASIC_FLOW.md) | Yosys/OpenROAD flow and results (sky130, IHP SG13G2) |
| [PROCESS_NODE_COMPARISON.md](docs/PROCESS_NODE_COMPARISON.md) | 130 nm vs 65 nm |
| [ISSUE_REGISTER.md](docs/ISSUE_REGISTER.md) | open blockers and resolved defects |
| [RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) | acceptance criteria status |
| [RTL_CODING_RULES.md](docs/RTL_CODING_RULES.md) | coding rules |
| [TOOL_VERSIONS.md](docs/TOOL_VERSIONS.md) | tool versions used |

## Provenance
Derived, with attribution in the source headers, from the SilicaFlux
repository (`btcphilosopher/Aureom.AI`, `SilicaFlux-main/`): `cpu_core`
(decode tables), `silicaflux-memoryflow` (SRAM abstraction, March C- MBIST,
tensor MAC array), `silicaflux-testcore` (TAP), `soc_integration` (UART
register map).  Everything else is new.
