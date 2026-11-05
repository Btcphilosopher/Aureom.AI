# Performance-modelling notes

## Provenance

`memoryflow.provenance.Provenance` tags every quantity:

* **THEORETICAL**: peak compute (`lanes × ops × f`), pin bandwidth (`MT/s × width`) and datapath rates
* **ANALYTICAL**: roofline attainable performance, tiling traffic, energy, area, sustained DRAM
  (peak × efficiency), and the DMA path (Little's law)
* **PY_SIMULATION**: cycle models (banking, DMA, pipeline) and the trace-driven cache
* **RTL_SIMULATION**: Verilator cycle counts (`MF_METRIC`)
* **MEASURED**: reserved for silicon or FPGA; none exists yet

## Roofline

    attainable = min(peak_compute(unit), AI_dram × BW_dram_eff, AI_onchip × BW_spm→engine)

* `BW_dram_eff = min(DRAM sustained, DMA path)`
* `DMA path = beat × f × min(B/(B+1), outstanding/(L+6+1))`, with
  `outstanding = min(DFIFO, (DESC+1) × B)`
* `BW_spm→engine = beat × f × bank_efficiency(banks)`, where `bank_efficiency` is the expected
  distinct banks for the DMA's two concurrent streams
* AI uses tiled traffic (`tiling.best_gemm_tiling`, `best_conv_tiling`) for the SPM capacity, so
  it changes with SPM size

## Workloads (`default_suite`)

| Kernel | Unit | Notes |
|---|---|---|
| GEMM 512³, 64×4096×1024 | tensor | output-stationary tiling, A re-read N/tn times, B M/tm times |
| Conv 64×56², 256×14² (3×3) | tensor | input- or weight-stationary direct tiling with halo |
| Vector add, dot | vector | no reuse |
| FIR 64-tap | vector | register-blocked taps |
| FFT 4096-pt × 64 | vector | log-pass model when the transform doesn't fit on chip |
| Jacobi 2-D 5-point | vector | on-chip if the grid fits, otherwise streaming rows |
| SpMV CSR | vector | x on chip if it fits, otherwise irregular gather penalty |

## Design space

`explore.one_at_a_time` sweeps each requested dimension around the RTL reference:
SPM 128/256/512/1024 KiB, banks, bus width, DMA burst, DMA outstanding, vector lanes,
tensor-array dimensions, DDR3/DDR4/LPDDR4X/LPDDR5/HBM2E/HBM3 and CPU cores.
`explore.joint_grid` evaluates the factorial grid, keeping only points the RTL can build
(lanes × 16 ≤ width, TR × 8 ≤ width).

**Feasibility (Budget):** 40 nm, 500 MHz, ≤ 12 mm² core (logic + SRAM macros + DRAM PHY),
≤ 1.5 W. External-memory PHY availability by node is set in `ExtMemConfig.max_node_nm`
(DDR3 ≤130, DDR4-2400 ≤55, DDR4-3200 ≤40, LPDDR4X ≤28, LPDDR5 / HBM2E ≤16, HBM3 ≤7). All of
these are assumptions and can be overridden on the CLI.

**Recommendation rule:** the smallest-area feasible point within 90 % of the best feasible
suite geomean. *Minimal* is the smallest within 60 %; *stretch* is the best feasible.

## Area

* SRAM: each bank is mapped to a macro grid (`plan_macro_tiling`, identical to
  `sf_sram_1rw IMPL=1`). Macro area = bits × bitcell / efficiency(bits) × port factor.
  `CompilerTableAreaModel` takes real compiler CSVs.
* Logic: Yosys generic cells → NAND2-equivalents (flop = 5.33 GE) → mm², at 0.70 utilisation.
  Scaling laws in `area.scaled_logic_ge`; the reference GE values are replaced by this run's Yosys
  results when `build/syn/synth_results.json` exists.

## Energy

Horowitz (ISSCC 2014) 45 nm anchors, scaled by an indicative C·V² node table. SRAM access energy
is fitted exactly through (8 KiB, 10 pJ), (32 KiB, 20 pJ) and (1 MiB, 100 pJ) per 64-bit access.
DRAM pJ/bit comes from the external-memory preset. Memory power = energy per byte × bytes per second.
