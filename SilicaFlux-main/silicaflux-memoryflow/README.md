# SilicaFlux MemoryFlow

MemoryFlow is a toolkit for modelling, simulating and optimising the memory subsystem of the
**SilicaFlux** compute architecture. Its job is to work out the best balance between CPU cores,
vector compute, tensor compute and memory bandwidth for **SilicaFlux-V**, the first-silicon,
mature-node ASIC.

It has three layers that check each other:

| Layer | What it is | Provenance tag |
|---|---|---|
| `rtl/` | Synthesizable SystemVerilog: parameterised SRAM, ECC, MBIST, banked scratchpad, router, two-engine DMA, vector unit, tensor array, reuse buffer, subsystem top | — |
| `tb/` + `memoryflow/verify` | Self-checking Verilator testbenches, Python golden models, mutation tests and Yosys synthesis | `RTL_SIMULATION` |
| `memoryflow/models` | Roofline, workloads, tiling, cache, banking, DMA, dataflow, energy and area models, plus design-space exploration | `THEORETICAL` / `ANALYTICAL` / `PY_SIMULATION` |

Every number in the report carries one of these tags. There is no `MEASURED` (silicon or FPGA)
data yet, and the reports say so.

## Quick start

```bash
pip install -e .[test]            # numpy, matplotlib, pytest
# toolchain (Ubuntu): sudo apt-get install verilator iverilog yosys   (Verilator >= 5.020, Yosys >= 0.33)

memoryflow rtl                    # 19 self-checking testbenches  -> build/rtl_results.json
memoryflow synth                  # Yosys synthesis of 7 wrappers -> build/syn/synth_results.json
memoryflow report                 # figures, CSV matrices, reports/report.html + REPORT.md
memoryflow explore                # design-space recommendation (prints the three tiers)
memoryflow roofline --config recommended
memoryflow inspect /path/to/silicaflux --yosys --md inventory.md   # classify an existing RTL repo
pytest -q                         # Python tests + fast RTL subset + mutation tests
MF_FULL_RTL=1 pytest -q           # also the full RTL regression and all four mutants
```

## Repository map

```
rtl/common       sf_fifo, sf_skid_buffer, sf_rr_arbiter
rtl/ecc          sf_ecc_secded_enc/dec (+ constant functions, any K)
rtl/sram         sf_sram_1rw (inferred | foundry-macro tiling), *_inferred 1RW/1R1W/2RW, sf_sram_bank
rtl/macro_stubs  sf_macro_1rw_leaf: behavioural model + synthesis blackbox (foundry macro stand-in)
rtl/mbist        sf_mbist_march (March C-, parallel banks)
rtl/spm          sf_spm_banked (N ports x M banks, interleave, credits, ECC counters, MBIST)
rtl/interconnect sf_mem_router (address decode, in-order responses across unequal latencies)
rtl/dma          sf_dma (APB regs, 4 channels, 1-D/2-D, IRQ, errors) + sf_dma_engine (x2: MM2S, S2MM)
rtl/accel        sf_vec_unit, sf_tensor_array (outer product, double-buffered accumulators), sf_reuse_buffer
rtl/top          sf_ctrl_regs, sf_memflow_top
tb/unit, tb/system   self-checking testbenches; tb/common: tb_common.svh, sf_extmem_model (behavioural)
syn/             parameter-fixed synthesis wrappers
memoryflow/      Python package (models, verify, report, inspect_rtl, cli)
docs/            architecture, register map, verification, modelling notes
reports/         generated engineering report (HTML, Markdown, CSV, figures)
```

## Where things stand

* **Original SilicaFlux repo.** It wasn't available to the session that built this. So
  `reports/inventory.md` classifies the MemoryFlow tree, and `memoryflow inspect` is the tool to run
  on the SilicaFlux tree. Inferred SRAM never becomes a hard macro by default: macros are an
  explicit `IMPL=1` choice, mapped through `plan_macro_tiling()`.
* **Area, energy, latency and PHY figures** are indicative, from public sources, and are marked
  that way. Swap in memory-compiler CSVs (`CompilerTableAreaModel`) and vendor datasheets before
  anyone relies on them.
* **Recommended parameterisation.** The full regression runs at the reference parameterisation.
  The recommended one passes `tb_param_smoke` plus lint and synthesis.

See `docs/verification.md` for the bugs that testing found, and `reports/report.html` for results.
