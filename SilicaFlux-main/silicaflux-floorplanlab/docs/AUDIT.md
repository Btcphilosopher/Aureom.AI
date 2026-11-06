# PHASE 1 — Repository and EDA-environment audit

Scope: repository `btcphilosopher/Aureom.AI`, branch `claude/silicaflux-floorplan-pipeline-a0lz8j`,
directory `SilicaFlux-main/` including every nested archive. Machine-generated inventory:
[`reports/audit/REPOSITORY_INVENTORY.md`](../reports/audit/REPOSITORY_INVENTORY.md) and
`reports/audit/repository_audit.json` (`python -m floorplanlab audit`, reads archives in memory,
nothing executed). Paths below use `archive!member`.

## 1. What the repository contains

| Fact | Value (source) |
|---|---|
| Files scanned (incl. nested zips / tar.gz) | 5 469 (`repository_audit.json`) |
| HDL files (.sv/.v/.svh/.vh) | 705 |
| `.sf` files | 90 — **all plain SystemVerilog** (module/package declarations; no `.sf` compiler or translator exists; agrees with `silicaflux-datafabric.zip!…/docs/datafabric/AUDIT.md` §1) |
| `.sfx` files | assembly programs for SilicaFlux 2.5 (`SilicaFlux2.0/SilicaFlux2.5/*.sfx`, assembler `sfx_asm.py`) — not hardware |
| Module declarations | 506 distinct names |
| LEF / Liberty / DEF / GDS / SPEF / ODB | **none** in the repository |
| SDC | 10 (listed in the inventory; e.g. `silicaflux-v-release1.zip!silicaflux-v/asic/constraints/sfv_soc.sdc`) |
| MCU-I implementation | **not found** (no RTL, config or document mentions it) |

Projects are delivered as zip files next to each other in `SilicaFlux-main/` (DataFabric README:
"vendored unmodified subsets with SHA256SUMS"). FloorplanLab follows that convention
(`SilicaFlux-main/silicaflux-floorplanlab/` + `silicaflux-floorplanlab.zip`).

## 2. Components found (exact paths)

| Component | Implementation used by FloorplanLab | Other occurrences |
|---|---|---|
| **SoC top (PD top)** | `silicaflux-datafabric.zip!silicaflux-datafabric/rtl/soc/sfv_soc_df.sv` (`sfv_soc_df`) | `silicaflux-v-release1.zip!silicaflux-v/rtl/top/sfv_soc.sv` (`sfv_soc`, no DMA); `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf` (2.5 architecture, behavioural memories) |
| CPU | `silicaflux-v-release1.zip!silicaflux-v/rtl/cpu/sfv_cpu.sv` (RV32I_Zicsr, 2-stage) | `cpu_core.zip`, `pipelined_cpu.zip`, `RISC-V CPU.zip` (older, not integrated) |
| Vector engine | `…/rtl/accel/sfv_vec_engine.sv` (4 lanes × 32 bit, 32×32 multipliers) | `vector_engine.sf` (2.5) |
| Tensor engine | `…/rtl/accel/sfv_tensor_engine.sv` + `sfv_mac_array` (4×4 INT8) | `tensor_unit.sf`, `silicafluxai.zip!…/rtl/tensor/sfx_systolic_array.sv` |
| Tile + scratchpad | `…/rtl/accel/sfv_tile.sv` (TSPM 16 KiB = 4 × `sfv_sram_sp` DEPTH 1024) | |
| SRAM abstraction | `…/rtl/mem/sfv_sram_sp.sv` (`SFV_SRAM_MACRO` → `sfv_sram_macro_bank`) | |
| SRAM macro wrappers | `…/asic/tech/ihp_sg13g2/sfv_sram_macro_bank.sv` (RM_IHPSG13_1P_{2048,1024,512,256}x64), `…/asic/tech/sky130/sfv_sram_macro_bank.sv` (sky130_sram_1rw1r_128x256_8) | |
| **SRAM Wrapper Library** (Project 01) | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-sramlib.zip!silicaflux-sramlib/rtl/mem/*` — ASIC leaves for SKY130, GF180MCU, IHP 1P/2P (equivalence-checked against vendor models) | reachable from `sfv_soc_df` only with `SRAM_IMPL=1`, see §4 |
| DataFabric DMA + interconnect | `silicaflux-datafabric.zip!…/rtl/dma/*.sv`, `…/rtl/interconnect/*.sv`, memory map `…/generated/sfb_memmap_pkg.sv` | |
| Boot ROM | `…/rtl/mem/sfv_mem_slaves.sv` (`sfv_bootrom`) + generated image `…/reports/firmware/sfv_bootrom_image.sv` | DataFabric builds the same image from the vendored identical firmware |
| Debug / test | `…/rtl/debug/sfv_jtag.sv`, `…/rtl/mem/sfv_mbist.sv` (March C-) | |
| Peripherals | `…/rtl/periph/sfv_{uart,spi,periph_misc,sysctrl}.sv` | |
| Clock / reset | one functional clock `clk` + JTAG `tck`; `sfv_rst_sync` ×3 (async assert / sync de-assert); `sfv_clkgate` ICG ×2 in the tile (`asic/tech/<pdk>/sfv_clkgate.sv`) — `…/docs/CLOCK_RESET.md` | |
| Existing floorplans | **none** (no DEF / floorplan Tcl). Release 1 has a placement *estimate* script `…/asic/scripts/or_place.tcl` (fixed macro grid, no PDN, no routing) | |
| Synthesis constraints | `…/asic/constraints/sfv_soc.sdc` (20 ns clk, 100 ns tck, async groups, 30 % I/O budgets) | timinglab SDCs for `silicaflux_top` / `tensor_unit`; testcore DFT SDC |
| Existing OpenROAD / Yosys scripts | release 1: `asic/scripts/run_asic.sh`, `run_place.sh`, `or_place.tcl`, `reports/synth/*/synth.ys`; timinglab: `flow/openroad/pnr.tcl`, `flow/sta/*.tcl`; PowerLink: `openroad/pdn_silicaflux_v_{generic,sky130,gf180mcu}.tcl` (header: "EXAMPLE SCRIPT - planning values only"; references a PLL SilicaFlux-V does not have) | |
| FPGA implementations | release 1 `fpga/ulx3s/` (ECP5, bitstream + nextpnr report); sramlib Arty-A7 self-test | |
| Technology dependencies | release 1 `asic/configs/{sky130hd,ihp_sg13g2}.cfg` (open PDKs via ORFS platforms), `commercial_{130,65}nm.cfg.template` (structure only, no foundry IP) | |
| TwinLab | `silicaflux-twinlab.zip` — Angular app; floorplan blocks hard-coded in `src/app/services/twinlab-state.ts`; annealing/`Math.random` physics in `semiconductor-physics.ts`; **no data import** | |

`silicaflux-datafabric.zip!…/third_party/silicaflux-v` was verified **byte-identical** to
`silicaflux-v-release1.zip!silicaflux-v` for `rtl/` and `firmware/bootrom/` (FloorplanLab
re-checks its own vendored copies on every run: `tools/import_sources.py --check`).

## 3. Can SilicaFlux-V be elaborated and synthesised? — **Yes**

`sfv_soc_df` (`PERF=0, ARB_MODE=1, DMA_ENGINE=0, SRAM_IMPL=0`, define `SFV_SRAM_MACRO`, IHP
SG13G2 wrappers) elaborates with **no unresolved module** under Yosys 0.38+92 and synthesises
through the ORFS `synth` target (hierarchical, ABC speed script) with `check`: **0 problems**.
Measured (reports/synthesis/SYNTHESIS_REPORT.md): 95 096 cells incl. 12 SRAM macros
(8 × `RM_IHPSG13_1P_2048x64_c2_bm_bist`, 4 × `RM_IHPSG13_1P_512x64_c2_bm_bist`), 4 512 flip-flops
(all asynchronous-reset), 2 ICG latch cells, 0 other latches, standard-cell area 1.168 mm²
(0.980 mm² after ORFS removes the 18 211 ABC buffers at floorplan), SRAM Liberty area 4.533 mm².
Only two Yosys warnings, both benign (a 2-entry wire array in the IHP wrapper converted to
registers; an unsupported Liberty expression on an unused scan flop).

## 4. Findings that shaped the implementation

1. **Physical-design top = `sfv_soc_df`**, not `sfv_soc`: the brief requires the DMA/DataFabric;
   `sfv_soc_df` is the integrated SoC and DataFabric's recommended first-silicon configuration.
2. **`SRAM_IMPL=1` cannot reach hard macros**: `sfv_soc_df` instantiates `sfb_sram_slave` without
   passing `BACKEND`/`MACRO`, so the SRAM Wrapper Library defaults to its GENERIC (behavioural →
   flip-flop) backend. `SRAM_IMPL=0` routes through `sfv_sram_sp` + `SFV_SRAM_MACRO` to the real
   macros. The Wrapper Library is therefore *not* on the implemented path (its IHP leaves also
   target 32-bit macros, e.g. RM_IHPSG13_1P_2048x32, that ORFS does not ship). Recorded, not hidden.
3. **No MCU-I**: `configs/mcu_i/design.yaml` refuses with that reason; no substitute is used.
4. **No floorplan, LEF, Liberty or GDS in the repository**: all technology data comes from pinned
   ORFS platforms (open PDKs); commercial profiles are templates that fail validation.
5. **2.5 `silicaflux_top`** has behavioural memories and no technology wrappers →
   `configs/full_silicaflux/design.yaml` marks it not available.

## 5. Recommended physical-design hierarchy

```
sfv_chip (FUTURE, not in repo): pad ring, ESD, power pads, seal ring  -> FABRICATION_DEPENDENCIES.md
└── sfv_soc_df                         core, pad-less; 73 logical I/O pins (FloorplanLab top)
    ├── u_cpu            sfv_cpu                 RV32I_Zicsr
    ├── u_tile           sfv_tile                compute tile
    │   ├── u_ve         sfv_vec_engine          4-lane SIMD (largest logic with u_te)
    │   ├── u_te         sfv_tensor_engine / u_mac sfv_mac_array
    │   ├── u_cg_ve/te   sfv_clkgate (ICG)
    │   └── g_bank[0..3].u_ram ... u_mac   4 x RM_IHPSG13_1P_512x64   (TSPM, tile-local)
    ├── g_sram[0..3].g_sfv.u_bank ... g_m[0..1] u_mac  8 x RM_IHPSG13_1P_2048x64 (main SRAM)
    ├── u_xbar sfb_crossbar, g_v1[*].g_ad.u_ad adapters, u_pbr periph bridge   (DataFabric)
    ├── u_dma            silicaflux_dma
    ├── u_rom, u_mbist, u_dbg (JTAG), u_rs_* reset synchronisers
    └── u_uart, u_spi, u_gpio, u_timer, u_intc, u_sysctrl
```
Hierarchy above 1 000 µm² is kept through synthesis (`SYNTH_HIERARCHICAL=1`,
`MAX_UNGROUP_SIZE=1000`) so OpenROAD instance names carry these prefixes; FloorplanLab uses them
for logical-group annotation and connectivity analysis only (no physical fences are claimed).

## 6. EDA environment audit

Nothing EDA-related was installed in the container. Installed and pinned
(`env/tools.lock.yaml`, reproducible with `env/install_toolchain.sh`):

| Tool | Version | Source / reason |
|---|---|---|
| OpenROAD (+ OpenSTA 2.4.0) | 2.0-12331-g6011bbe77 | litex-hub conda; the exact commit ORFS `ab2aaf0f` pins in `tools/OpenROAD` |
| Yosys (flow) | 0.38+92 (84116c9a3) | litex-hub conda; contemporaneous with ORFS `ab2aaf0f` |
| ORFS | `ab2aaf0fb8513f6f6fa8898ba65ae9599a26e621` (2024-02-23) | sparse checkout; the newest ORFS whose flow scripts match an installable OpenROAD build |
| IHP SRAM collateral | ORFS `d0e5b3c` (the revision SilicaFlux-V release 1 used) | SG13G2 SRAM LEF/LIB/GDS were added to ORFS after `ab2aaf0f`; tech-LEF layer stacks verified identical |
| Yosys (aux) | 0.33 (2584903a060) | Ubuntu apt; identical to SilicaFlux-V release 1 |
| KLayout / Icarus / Verilator | 0.28.16 / 12.0 / 5.020 | Ubuntu apt |
| Python | 3.13.18 + numpy 2.5.3, pandas 3.0.5, pydantic 2.13.5, matplotlib 3.10.7, plotly 6.3.1, pytest 8.4.2 | |

Not available: Docker daemon (no `openroad/orfs` image), any OpenROAD newer than Feb 2024 on
an installable channel, foundry PDKs. ORFS inspection results (targets, `do-*` steps, variables,
hooks) are documented in [ORFS_INTEGRATION.md](ORFS_INTEGRATION.md).
