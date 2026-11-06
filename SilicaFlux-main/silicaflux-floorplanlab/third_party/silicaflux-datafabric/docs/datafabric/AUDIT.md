# Phase 1 — Repository audit (btcphilosopher/Aureom.AI, `SilicaFlux-main/`)

Audited on 2026-11-05/06 from the repository checkout (branch
`claude/awesome-albattani-y4t7ih`, HEAD `05183f2`). `SilicaFlux-main/` holds 14 loose
`.sf` files, 2 more directories of `.sf`/`.sfx` files (`SilicaFlux2.0/SilicaFlux2.5/`),
and **35 zip/tar archives**; every archive was extracted into its own directory and
searched (HDL files in 31 archives, ~800 `.sv/.v/.sf` files excluding the generated
`timinglab` content). Tools available for the audit and this project: Verilator
5.020, Icarus 12, Yosys 0.33 (+ yosys-smtbmc, yosys-abc), z3 4.8.12, boolector,
cocotb 2.1.0, clang/lld 18 (RISC-V); **not available**: SymbiYosys (installing from
source was not permitted in this environment), OpenROAD/OpenSTA, any PDK/Liberty.

Baseline reproduced before any change: SilicaFlux-V release 1 `make fw` and
`make soc-sim` → **6/6 scenarios PASS** in this environment (identical cycle counts
to the release's own report).

## 1. `.sf` format verdict

**`.sf` is plain SystemVerilog (IEEE 1800-2017) with a custom extension** — not a DSL
or IR, and there is no `.sf` compiler/translator in the repository.

* Content: packages, `typedef struct packed`, `always_ff/always_comb`, SVA under
  `ifndef SYNTHESIS`; the header line "Language: Silica Flux-2017" is a label.
* SilicaFlux2.5 `run_sim.sh` passes `*.sf` straight to `iverilog -g2012`;
  memoryflow's `hdl.py` runs `verilator +systemverilogext+sf` and states ".sf is
  SystemVerilog".
* Test: `silicaflux_pkg (1).sf` + `memory_controller.sf` copied to `.sv` →
  `verilator --lint-only -Wall` clean. Icarus/Yosys failures on some files are tool
  limits on standard SV (concurrent assertions, multi-dimensional packed typedefs),
  not foreign syntax. Two SF2.5 tops fail on *undefined types* (`noc_packet_t`,
  `sf_axi_req_t`), i.e. missing packages.
* `.sfx` files are assembly programs for `sfx_asm.py` (an assembler, not an HDL tool).
* Divergent duplicates: `package silicaflux_pkg` exists in 6 different versions;
  same-named modules with different content (`alu.sf` vs `alu (1).sf`, …); Gen-1
  `silicaflux.zip` reuses module names with different interfaces. A flat compile of
  the whole tree is therefore impossible — DataFabric builds against the
  self-consistent **SilicaFlux-V release 1** tree only.

## 2. Primary integration targets (audited directly)

Paths are archive members. `SFV` = `silicaflux-v-release1.zip/silicaflux-v`,
`SL` = `SilicaFlux2.0/SilicaFlux2.5/silicaflux-sramlib.zip/silicaflux-sramlib`,
`MF` = `…/silicaflux-memoryflow-v2.0.0.zip/silicaflux-memoryflow`,
`ML` = `silicaflux-memorylab.zip/silicaflux-memorylab`.

| Source path | Module | Interface | Bus protocol | Clock | Reset | Synthesizable | Reuse | Required modifications | Verification status |
|---|---|---|---|---|---|---|---|---|---|
| SFV/rtl/bus/sfv_xbar.sv | sfv_xbar | NM×NS req/gnt/addr/we/be/wdata, rvalid/rdata/err; err capture | SFB v1 (OBI subset): no response back-pressure; 1 outstanding per master & slave | clk | async low | yes (Yosys/Verilator clean in release) | **Adapt (superseded)** | add rsp_ready, DW param, RR arbitration (fixed priority only; fair only because JTAG is master 0), generated map → `sfb_crossbar` keeps its transaction model | release: cocotb random test + ABC-PDR proof; **its test re-run unmodified on sfb_crossbar here: PASS** |
| SFV/rtl/bus/sfv_periph_bridge.sv | sfv_periph_bridge | SFB slave → rb_sel[32 pages], rb_we/addr/wdata, rb_rdata/err | SFB v1 → register bus (1-cycle strobe, comb. read) | clk | async low | yes | **Reuse as-is** | none (behind sfb_v1_slave_adapter; DMA/DFPERF pages plug in) | release SoC regression |
| SFV/rtl/mem/sfv_mem_slaves.sv | sfv_sram_slave, sfv_bootrom | SFB v1 slave + MBIST collar | SFB v1, 1-cycle | clk | async low | yes (array via sfv_sram_sp / tech wrapper) | **Reuse as-is** | none (v1 adapter) | release SoC regression, MBIST fault tests |
| SFV/rtl/common/sfv_common.sv | sfv_sync, sfv_rst_sync, sfv_fifo | 2-FF sync; async-assert/sync-release reset with test bypass; FIFO | — | clk | async low | yes | **Reuse as-is** (reset scheme) | none | release |
| SFV/rtl/cpu/sfv_cpu.sv | sfv_cpu (RV32I_Zicsr) | I/D SFB v1 masters (word-aligned d_addr), irq_ext/timer/soft | SFB v1 master, always accepts responses | clk | async low | yes | **Reuse as-is** | rsp_ready tied 1 | release: 55/55 riscv-tests |
| SFV/rtl/debug/sfv_jtag.sv | sfv_jtag_dbg | TAP + system-bus-access SFB master | SFB v1 master | tck + clk (handshake CDC) | async low | yes | **Reuse as-is** | none | release JTAG boot scenario; passes on sfv_soc_df |
| SFV/rtl/accel/sfv_tile.sv (+vec/tensor engines) | sfv_tile | SFB v1 slave (TSPM) + VE/TE register pages | SFB v1; engine TSPM lock has priority | clk + ICG | async low | yes | **Reuse as-is** (production vector/tensor engines) | none: DMA reaches TSPM through the crossbar | release cocotb tile test; DMA end-to-end demo here |
| SFV/rtl/periph/sfv_periph_misc.sv | sfv_intc | N sources, ENABLE/CLAIM | register bus | clk | async low | yes | **Reuse as-is** | N 8 → 9 (DMA source 8) | release + demo D5 |
| SFV/rtl/top/sfv_soc.sv | sfv_soc | SoC top | — | clk, tck | sfv_rst_sync tree | yes | **Adapt → sfv_soc_df** | crossbar swap, 4th master, 2 pages, IRQ 8 | 6/6 release scenarios cycle-identical on sfv_soc_df |
| SFV/rtl/pkg/sfv_pkg.sv | sfv_pkg | map constants | — | — | — | yes | **Reference** (YAML cross-checked against it) | finding: `ROM_MASK` (16 KiB) / `TSPM_MASK` (64 KiB) are unused and differ from the decode in sfv_soc (4 KiB / 16 KiB) | — |
| SFV/docs/ISSUE_REGISTER.md ISS-015 | — | "No DMA engine; CPU moves accelerator operands; memoryflow sf_dma as reference" | — | — | — | — | **Requirement source** | — | — |
| SL/rtl/mem/sram_sp.sv, sram_1r1w.sv (+backends) | sram_sp, sram_1r1w | req_valid/ready/we/addr/wdata/wmask/id; rsp_valid/ready/rdata/err/we/id; MBIST tst_* | valid/ready with response FIFO (credit), READ_LATENCY param | clk | async low, control only | yes (generic/FPGA/ASIC backends) | **Reuse as-is** (vendored) | SFB2 adapters `sfb_sram_slave`, `sfb_sram_1r1w_slave` | library reports: 53 sim / 9 formal / 29 synth PASS; here: crossbar random test at latency 1–3 + SoC with MBIST |
| SL/rtl/mem/sram_bank_controller.sv | sram_bank_controller | N masters × N banks, RR/fixed | valid/ready + IDs | clk | async low | yes | **Reference** | not needed: banks are crossbar slave ports | library |
| MF/rtl/dma/sf_dma.sv | sf_dma | APB3 regs; separate rd/wr SF-MEM masters; streams | SF-MEM valid/ready, multi-outstanding, 2-D, multi-channel | clk | async low | yes | **Reference only** | too large for first silicon (task: simple single channel first); its error codes/validation informed DMA.md | memoryflow tb_dma / tb_system PASS (archive reports) |
| MF/rtl/common/sf_rr_arbiter.sv | sf_rr_arbiter | req[N], accept → one-hot grant | — | clk | async low | yes | **Adapt** | grant lock + fixed mode added → `sfb_arbiter` | memoryflow TBs; here formal PDR |
| MF/rtl/common/sf_skid_buffer.sv | sf_skid_buffer | 2-entry valid/ready slice | valid/ready | clk | async low | yes | **Reuse (logic unchanged)** | ports re-declared per SFV rules → `sfb_skid_buffer` | here: streaming TB + PDR proof |
| ML/python/memorylab/trace_import.py | read_trace, trace_metrics | canonical trace cycle/event/master/id/addr/op/size/bank | — | — | — | — | **Reuse as-is** | DataFabric traces exported in this format | here: real RTL traces analysed |
| ML/python/memorylab/calibration.py | dma_copy_cycles | event-driven DMA/IC/SRAM model | — | — | — | — | **Reuse as-is** | parameters mapped from DataFabric configs | compared with measured RTL |

## 3. Secondary modules (delegated audit)

These rows come from a sub-agent that read the sources and re-ran the archives' own
testbenches / small reproduction benches with the tools above. The defect findings
in this table (NoC flit duplication, `soc_sram` response loss, FSM arbiter failures,
`axi_lite_slave` read-back) were reproduced by that sub-agent; they were **not**
independently re-verified for this report because none of these modules is used by
DataFabric. Only the memoryflow `sf_rr_arbiter` / `sf_skid_buffer` facts were checked
first-hand (both are reused).

Prefixes: `SOC` soc_integration.tar.gz, `CP` comm_protocols.zip, `FSM` Finite State
Machines Library.zip, `AI` SilicaFlux2.0/silicafluxai.zip, `SF1` silicaflux.zip, `MC`
memory_cache_repo.zip, `TC` silicaflux-testcore.zip.

| Source path | Module | Interface | Bus protocol | Clock | Reset | Synthesizable | Reuse | Required modifications | Verification status |
|---|---|---|---|---|---|---|---|---|---|
| SOC/rtl/bus/soc_fabric.sv | soc_fabric | 1 master SSB req/rsp valid/ready, NS=6 | SSB, 1 outstanding (1 transfer / 2 cycles) | clk | async low | yes | Adapt | hard-coded decode; no multi-master | tb_soc_top 20/20 PASS on re-run |
| SOC/rtl/bus/soc_bus_if.sv | soc_bus_if | interface + modports | SSB | clk | — | yes | Reference (template) | never instantiated | none run |
| SOC/rtl/memory/soc_sram.sv | soc_sram | SSB slave | 1-cycle, req_ready = 1 | clk | async low | partly (initial fill) | Do not reuse | **loses/overwrites responses** without upstream gating | PASS only behind soc_fabric |
| SOC/rtl/cpu/cpu_if_adapter.sv | cpu_if_adapter | CPU I/D → SSB | SSB | clk | async low | Icarus fails to bind params | Reference | can switch request mid-handshake | not instantiated |
| CP/rtl/axi_lite/axi_lite_slave.sv | axi_lite_slave | AXI4-Lite, 8 regs | AXI4-Lite | aclk | async low | Verilator yes; Icarus fails | Reference | reads return reg_in, not written regs | TB, no results |
| CP/rtl/uart, spi | uart_top, spi_top | stream/pulse | — | clk | async low | yes | Do not reuse (SFV has its own UART/SPI) | — | TBs, no results |
| FSM/round_robin_arbiter.sv | round_robin_arbiter | req/gnt time slice | — | clk | async low | latch warnings | **Do not reuse** | breaks above 4 requesters (never grants at 8 in sim) | false README claim |
| FSM/priority_arbiter.sv | priority_arbiter | req/gnt/ack | — | clk | async low | yes | Reference | ≥3 cycles per grant | no results |
| AI/rtl/dma/sfx_dma.sv | sfx_dma | cmd/done valid/ready; en/we SRAM ports | no ready/gnt, fixed 1-cycle | clk | **sync** low | yes | Adapt (concept) | no back-pressure / errors; FIFO drops data if dst stalls | tb_sfx_dma PASS |
| MF/rtl/interconnect/sf_mem_router.sv | sf_mem_router | 1 master → NS, MAXOUT 8 | SF-MEM valid/ready, order FIFO | clk | async low | yes (676 GE) | Reference | single master | tb_router PASS |
| MF/rtl/bridge/sf_mc25_vport_bridge.sv | sf_mc25_vport_bridge | SF-MEM → SF2.5 vector port | valid/ready | clk | async low | yes | Reference | payload not held while waiting (no grant lock) | 4140 checks PASS |
| SF1/rtl/noc_interconnect.sv | noc_interconnect | 2×2 mesh | flit valid/ready | clk | async low | yes | **Do not reuse** | router **duplicates flits** (1 in, 2 out) though its TB passes | 6/6 TB PASS (blind to bug) |
| SF1/rtl/memory_controller.sv | memory_controller (Gen-1) | opcode req, resp_valid w/o ready | — | clk | async low | multi-driven array | Do not reuse | bursts > 4 words wrap | memoryflow records DEFECT |
| MC/rtl/async_fifo.sv | async_fifo | push/pop, Gray pointers | — | wclk/rclk | async low | yes (SVA rejected by tools) | Adapt (future CDC) | valid/ready wrapper, constraints, reset syncs | no results |
| MC/rtl/sync_fifo.sv | sync_fifo | push/pop + flags | — | clk | async | initial block drives flops | Reference | false-firing assertion | no results |
| TC/rtl/tc_reg_bridge.sv | tc_reg_bridge | JTAG DR → req/gnt master | toggle-handshake CDC | tck + clk | async low | yes | Adapt (debug) | wider address/data | 17/17 testcore regression |
| formal_verification.zip/sva_assertion_lib.sv | macros, checkers | handshake/Gray checkers | generic valid/ready | bind | disable iff | verification only | Adapt (concepts) | targets commercial formal tools; `##` SVA unsupported by Verilator/Yosys here | no results |

## 4. Findings that shaped the design

1. **SFB already exists** (SilicaFlux-V) and is the right base — it is extended, not
   replaced. The one missing feature for DMA and future stream masters was response
   back-pressure; arbitration was fixed-priority only.
2. **No DMA in the first-silicon SoC** (ISS-015); `sf_dma` is a high-end reference.
   The task requires the smallest correct engine first → a new simple engine, with a
   buffered option.
3. **No reusable multi-master arbiter in the FSM library** (defects above);
   memoryflow's `sf_rr_arbiter` is reused with a grant lock added (the memoryflow
   bridge shows what happens without one: payload changes while waiting).
4. **SRAM Wrapper Library is mature and verified** → reused unmodified.
5. **MemoryLab already defines a canonical trace format and a DMA model** → reused.
6. **Pre-existing inconsistencies reported, not silently fixed:** sfv_pkg
   `ROM_MASK`/`TSPM_MASK` vs actual decode; Gen-1 NoC flit duplication; soc_sram
   response loss; FSM-library RR arbiter defects; divergent `silicaflux_pkg` copies.
7. Feature branch `feature/silicaflux-datafabric` was **not created**: the request
   was to deliver a zip and not commit to GitHub; nothing was committed or pushed.
