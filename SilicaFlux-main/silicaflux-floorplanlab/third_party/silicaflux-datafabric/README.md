# SilicaFlux DataFabric — Project 03

**Synthesizable bus interconnect + single-channel DMA for SilicaFlux-V**, built on the
real SilicaFlux repository (`btcphilosopher/Aureom.AI`, `SilicaFlux-main/`): it extends
SilicaFlux-V release 1's SFB bus, reuses its CPU / vector / tensor / peripheral RTL
unchanged, uses the SilicaFlux SRAM Wrapper Library (Project 01) and feeds measured
traces into SilicaFlux MemoryLab (Project 02).

> Status: **RTL verified in simulation, formally (interconnect: unbounded proofs;
> DMA: bounded proofs only) and at gate level; integrated into the SilicaFlux-V SoC
> and exercised by firmware on the real CPU. Not tape-out ready** — no PDK-based synthesis, STA, place-and-route, power or DFT signoff exists
> (see [docs/datafabric/ISSUES.md](docs/datafabric/ISSUES.md)).

## What is in the box

| Area | Files |
|---|---|
| Protocol | SFB2 = SFB + response back-pressure + DW parameter — [PROTOCOL.md](docs/datafabric/PROTOCOL.md) |
| Interconnect RTL | `rtl/interconnect/`: `sfb_crossbar` (decoder, arbiter, request mux, response router, error slave), `sfb_reg_slice`/`sfb_skid_buffer`, `sfb_v1_slave_adapter`, `sfb_shared_bus` (comparison), `sfb_perf_counters` |
| DMA RTL | `rtl/dma/`: `silicaflux_dma`, `dma_control_regs`, `dma_irq`, `dma_validate`, `dma_transfer_engine` (simple, default), `dma_burst_engine` + `dma_fifo` (buffered option) — [DMA.md](docs/datafabric/DMA.md) |
| SRAM library adapters | `rtl/mem/sfb_sram_slave.sv` (1RW), `sfb_sram_1r1w_slave.sv` |
| SoC integration | `rtl/soc/sfv_soc_df.sv` = SilicaFlux-V + DataFabric — [ARCHITECTURE.md](docs/datafabric/ARCHITECTURE.md) |
| Memory map | `memmap/silicaflux_v_datafabric.yaml` → `generated/` (SV, C, Python) + [MEMORY_MAP.md](docs/datafabric/MEMORY_MAP.md) via `python/datafabric/memmap_gen.py` |
| Verification | `tb/` (Verilator SV testbenches, cocotb + Python reference model, protocol checker, trace monitor), `formal/datafabric/` (yosys-smtbmc + ABC PDR) — [VERIFICATION.md](docs/datafabric/VERIFICATION.md) |
| Firmware | `firmware/drivers/silicaflux_dma.{h,c}`, `firmware/examples/dma_demo` — [FIRMWARE.md](docs/datafabric/FIRMWARE.md) |
| Analysis | `python/datafabric/` trace export, bandwidth analysis, MemoryLab adapter; `scripts/datafabric/` regressions, synthesis, GLS, benchmark, report |
| PPA | [PPA.md](docs/datafabric/PPA.md), `synth/asic/` node templates (no fabricated node results) |
| Audit | [AUDIT.md](docs/datafabric/AUDIT.md) — repository audit, `.sf` format verdict, reuse matrix |
| Results | `reports/datafabric/` — every number in the docs comes from these files ([SUMMARY.md](reports/datafabric/SUMMARY.md)) |
| Upstream sources | `third_party/silicaflux-v`, `third_party/silicaflux-sramlib` — vendored **unmodified** subsets with `SHA256SUMS` |

## Quick start

```bash
make datafabric-fw          # firmware (clang/lld RISC-V)
make datafabric-lint        # Verilator -Wall + Yosys elaboration/latch checks + memory-map checks
make datafabric-test        # unit, crossbar parameter, mutation and SoC firmware regressions
make datafabric-formal      # BMC + ABC PDR (unbounded for the interconnect; DMA bounded only) + non-vacuity mutants
make datafabric-synth       # Yosys generic synthesis of all configurations
make datafabric-gls         # gate-level simulation of synthesized crossbar / DMA
make datafabric-benchmark   # RTL performance sweep (+ MemoryLab comparison, MEMORYLAB_PY=...)
make datafabric-report      # reports/datafabric/SUMMARY.md
```

Tools used (exact versions in `reports/datafabric/SUMMARY.md`): Verilator 5.020,
Icarus 12, Yosys 0.33 with yosys-smtbmc/yosys-abc, z3, cocotb 2.1, clang/lld 18,
Python 3 (PyYAML; numpy/pandas for MemoryLab).

## SilicaFlux-V configuration (recommended for first silicon)

`sfv_soc_df` with `ARB_MODE = 1` (round robin), `DMA_ENGINE = 0` (simple engine),
`PERF = 0` (counters removed), SRAM banks from the SRAM Wrapper Library
(`SRAM_IMPL = 1`) once the ASIC macro flow is in place. The reasoning and measured
data are in [PPA.md](docs/datafabric/PPA.md).
