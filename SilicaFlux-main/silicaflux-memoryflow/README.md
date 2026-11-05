# SilicaFlux MemoryFlow

MemoryFlow is a toolkit for modelling, simulating and optimising the memory subsystem of the
**SilicaFlux** compute architecture. Its job is to find the best balance between CPU cores, vector
compute, tensor compute, SRAM and external-memory bandwidth for **SilicaFlux-V** (first silicon,
mature node) and for the full SilicaFlux processor.

Version 2 grounds everything in the SilicaFlux repository this tree lives in. v1 (the
`silicaflux-memoryflow.zip` next to this directory) was built without access to the SilicaFlux
sources or design documents and assumed a 40 nm / 500 MHz / 12 mm² / 1.5 W envelope. v2 reads the
real RTL, verifies it in simulation, and uses the documented 65 nm / 200 MHz / < 10 mm² / < 1 W target.

| Layer | What it is | Provenance tag |
|---|---|---|
| `memoryflow/silicaflux` | **Repository evidence**: extracts the SilicaFlux HDL from its archives and `.sf` files (sha256 provenance), classifies every memory-subsystem block with `origin:line` anchors confirmed by Verilator elaboration, quotes the design documents (page-verified), and runs testbenches on the unmodified SilicaFlux RTL | `DOCUMENTED`, `RTL_SIMULATION` |
| `rtl/` | Synthesizable SystemVerilog: parameterised SRAM (inferred / foundry-macro), ECC, MBIST, banked scratchpad, router, two-engine DMA, vector unit, tensor array, reuse buffer, subsystem top, and the bridge to the SilicaFlux 2.5 scratchpad | — |
| `tb/` + `memoryflow/verify` | Self-checking Verilator testbenches (MemoryFlow RTL in `tb/unit`, `tb/system`; existing SilicaFlux RTL in `tb/silicaflux`), Python golden models, mutation tests, Yosys synthesis | `RTL_SIMULATION` |
| `memoryflow/models` | Roofline (with DMA read *and* write paths and a tensor result-drain ceiling), workloads, tiling, cache, banking, DMA, dataflow, energy, area, balance and design-space exploration | `THEORETICAL` / `ANALYTICAL` / `PY_SIMULATION` |

Every number in the report carries one of these tags. There is still no `MEASURED` (silicon or FPGA) data.

## Quick start

```bash
pip install -e .[test]                 # numpy, matplotlib, pytest
# toolchain (Ubuntu): sudo apt-get install verilator iverilog yosys poppler-utils
memoryflow sf-inventory --md inv.md    # what the SilicaFlux repository actually implements
memoryflow sf-char                     # testbenches on the unmodified SilicaFlux RTL
memoryflow rtl                         # MemoryFlow's own 19 self-checking testbenches
memoryflow synth                       # Yosys synthesis of the MemoryFlow wrappers
memoryflow baselines                   # SilicaFlux as built / documented vs the recommendation
memoryflow explore --budget silicaflux-v-65      # also: silicaflux-v-130, v1-assumed-40, full-28, full-16
memoryflow balance --budget full-28    # binding resource and headroom per kernel, CPU orchestration load
memoryflow report                      # reports/report.html, REPORT.md, inventory.md, CSVs, figures
pytest -q                              # Python tests + fast RTL subset (MF_FULL_RTL=1 for everything)
```

The SilicaFlux sources are found in the parent directory (`SilicaFlux-main/`); set
`MF_SILICAFLUX_ROOT` to point elsewhere. Without them MemoryFlow still runs its own RTL and models.

## What the SilicaFlux repository contains (memory subsystem)

From `reports/inventory.md` (246 HDL files, 94.5 k lines, 11 source sets):

* **Implemented and elaborating:** the Gen-1 cluster (4 tiles × 1 KiB SPM, 2×2 NoC, sequential 4×4
  tensor unit), and the Gen-2.5 units `memory_controller.sf` (8 banks × 512 × 128 b banked SPM, three
  requesters, parity), `tensor_unit.sf` (4×4×4 INT8 per cycle, no accumulation buffer),
  `register_bank.sf`, `vector_engine.sf`.
* **Not elaborable:** the Gen-2.5 `compute_tile.sf` (its memory-controller and tensor-unit instances
  use interfaces the in-repo modules do not have; 29 of 30 package types are undefined) and the 2.5
  mesh router (its packet type is undefined).
* **Referenced only:** 26 of the 27 module types instantiated by the Gen-2.5 `silicaflux_top.sf`,
  including the L2, the LLC, the coherent fabric, the memory fabric / AXI edge and the DMA bridge.
* **Absent everywhere:** a DRAM controller and PHY.

## Key results (see `reports/REPORT.md`)

* The SilicaFlux 2.5 tensor unit sustains 63 MAC/cycle in isolation (RTL) but reaches ~9 % of its
  peak inside its tile, because it has no accumulation buffer behind a 16 B/cycle vector port and a
  single 128-bit register write port. MemoryFlow's outer-product array with in-array accumulators
  reaches ~30× the dense throughput in ~1.3× the area (4.6 vs 3.5 mm²).
* Recommended SilicaFlux-V (65 nm, 200 MHz): 128 KiB SPM in 4 banks × 128 b with XOR interleave and
  SECDED, 16×16 INT8 tensor array with double-buffered accumulators, 8 × 16-bit vector lanes, a DMA
  with 16 outstanding reads and 32 outstanding write acknowledgements, DDR3-1600 x16 (LPDDR2-800 x32
  equivalent). HyperRAM is the low-pin, digital-PHY alternative: one device gives ~30 % and two ~50 % of
  the DDR3 suite geomean. The documented no-DRAM part runs streaming kernels ~20× slower than the
  same machine with DDR3.
* 130 nm only works if SilicaFlux-V drops to 128 KiB: the documented 256 KiB costs ~6.9 mm² there.
* Full SilicaFlux (assumed envelopes): behind LPDDR the performance-per-area knee is ~8 tiles per
  memory interface (28 nm, LPDDR4X 2×32: ~127 Gop/s in 13 mm², 1.75 W); past 32 tiles each doubling adds
  under 10 %. At 16 nm, LPDDR5 4×32 reaches ~45 % of HBM2E's performance at ~40 % of its power without
  an interposer; behind HBM more tiles keep paying. HBM is the stretch option.

## Repository map

```
memoryflow/silicaflux  sources, hdl, inventory, doc_targets, characterise, baselines
rtl/common       sf_fifo, sf_skid_buffer, sf_rr_arbiter
rtl/ecc          sf_ecc_secded_enc/dec (+ constant functions, any K)
rtl/sram         sf_sram_1rw (inferred | foundry-macro tiling), *_inferred 1RW/1R1W/2RW, sf_sram_bank
rtl/macro_stubs  sf_macro_1rw_leaf: behavioural model + synthesis blackbox (foundry macro stand-in)
rtl/mbist        sf_mbist_march (March C-, parallel banks)
rtl/spm          sf_spm_banked (N ports x M banks, interleave, credits, ECC counters, MBIST)
rtl/interconnect sf_mem_router (address decode, in-order responses across unequal latencies)
rtl/bridge       sf_mc25_vport_bridge (SF-MEM -> the SilicaFlux 2.5 memory_controller vector port)
rtl/dma          sf_dma (APB regs, 4 channels, 1-D/2-D, IRQ, errors) + sf_dma_engine (x2: MM2S, S2MM)
rtl/accel        sf_vec_unit, sf_tensor_array (outer product, double-buffered accumulators), sf_reuse_buffer
rtl/top          sf_ctrl_regs, sf_memflow_top
tb/unit, tb/system   MemoryFlow testbenches; tb/silicaflux: testbenches for the existing SilicaFlux RTL
syn/             parameter-fixed synthesis wrappers
docs/            architecture, register map, verification, modelling, SilicaFlux evidence
reports/         generated engineering report (HTML, Markdown, CSV, figures, data/)
```

## Limits

* Area, energy, latency and PHY figures are indicative public-literature values, marked as such. Swap in
  memory-compiler CSVs (`CompilerTableAreaModel`) and vendor datasheets before relying on them.
* The as-built SilicaFlux machines' logic area is ANALYTICAL: Yosys 0.33 cannot parse the SilicaFlux
  packages (sv2v or a newer front end is needed for gate counts).
* Full-chip envelopes and CPU orchestration costs are MemoryFlow assumptions and are labelled as such.
* The full MemoryFlow regression runs at the reference parameterisation; the recommended one passes the
  parametric smoke test, lint and synthesis.

See `docs/verification.md` for every bug the testing found (in MemoryFlow, in the SilicaFlux RTL and in
the testbenches themselves) and `docs/silicaflux_evidence.md` for how the evidence layer works.
