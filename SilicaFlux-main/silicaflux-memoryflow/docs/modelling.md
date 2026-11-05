# Performance-modelling notes

## Provenance

`memoryflow.provenance.Provenance` tags every quantity:

* **THEORETICAL**: peak compute (`lanes × ops × f`), pin bandwidth (`MT/s × width`) and datapath rates
* **ANALYTICAL**: roofline attainable performance, tiling traffic, energy, area, sustained DRAM
  (peak × efficiency), and the DMA path (Little's law)
* **PY_SIMULATION**: cycle models (banking, DMA, pipeline) and the trace-driven cache
* **RTL_SIMULATION**: Verilator cycle counts (`MF_METRIC`), of MemoryFlow's RTL *and* of the existing
  SilicaFlux RTL (`memoryflow sf-char`)
* **DOCUMENTED** (v2): targets quoted from the repository's design documents, page-verified
  (`memoryflow.silicaflux.doc_targets`); inputs, never results
* **MEASURED**: reserved for silicon or FPGA; none exists yet

## Roofline

    attainable = min(peak_compute(unit), AI_dram × BW_dram_eff(w), AI_onchip × BW_spm→engine, drain(w))

* `BW_dram_eff(w) = min(DRAM sustained, 1 / max((1-ws)/DMA_read, ws/DMA_write))`, where `ws` is the
  workload's DRAM write share (`Workload.write_share`): reads and writes move concurrently on the
  DMA's two paths (v2)
* `DMA read path = beat × f × min(B/(B+1), outstanding/(L+6+1))`, with
  `outstanding = min(DFIFO, (DESC+1) × B)`
* `DMA write path = beat × f × min(1, WOUT/(L+6+1))` (v2): Little's law on write acknowledgements.
  Calibrated by `tb_sf25_dma_bridge`: SPM→EXT with WOUT = 8 and a 20-cycle memory runs at 6.06 B/cycle;
  the model gives 8/21 × 16 = 6.10 (0.6 %)
* `drain(w)` (v2, tensor only): `ops / result_bytes × drain_B/cycle × f` when the tensor result path is
  narrow (`ComputeConfig.tensor_drain_bytes_per_cycle`; SilicaFlux 2.5: one 128-bit VRF write port)
* `tiles` (v2): vector/tensor peaks, the SPM→engine path and the per-tile DMA paths scale with
  `SystemConfig.tiles`; the external memory is shared
* `BW_spm→engine = beat × f × bank_efficiency(banks)`, where `bank_efficiency` is the expected
  distinct banks for the DMA's two concurrent streams
* AI uses tiled traffic (`tiling.best_gemm_tiling`, `best_conv_tiling`) for the SPM capacity, so
  it changes with SPM size

### Tensor dataflows (v2)

| `tensor_dataflow` | Engine | MACs/cycle | On-chip bytes per GEMM |
|---|---|---|---|
| `outer_product` | MemoryFlow `sf_tensor_array` (accumulators in the array, A streamed, B replayed from the reuse buffer) | TR × TC | A beats + B once per tile column + C once |
| `block` | SilicaFlux 2.5 `tensor_unit` (one DIM×DIM×DIM product per cycle, no accumulation buffer) | DIM³ | per block: A + B tiles in, DIM² partials out **and back** (accumulated elsewhere) |

For DIM = 4, INT8 → INT32 the block dataflow needs 160 B per 128 ops (0.8 op/B on chip); this is why the
2.5 tile reaches ~9 % of its tensor peak even with a DRAM path.

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
SPM 128/256/512/1024 KiB, banks, bus width, DMA burst, DMA outstanding reads, DMA write acks (v2),
vector lanes, tensor-array dimensions, external memories and CPU cores.
`explore.joint_grid` evaluates the factorial grid (plus `wout` ∈ {8, 32} and, for full-chip budgets,
`tiles` ∈ {4, 8, 16, 32}), keeping only points the RTL can build (lanes × 16 ≤ width, TR × 8 ≤ width) and
external memories whose PHY exists at the node.

**Budgets (v2, `explore.BUDGETS`, `--budget` on the CLI):**

| Name | Envelope | Basis |
|---|---|---|
| `silicaflux-v-65` (default) | 65 nm, 200 MHz, 8 mm² core (< 10 mm² die less an assumed 20 % pad ring), 1 W | DOCUMENTED (reduced-ASIC p.1/p.3, update p.7-9) |
| `silicaflux-v-130` | 130 nm, 100 MHz, 8 mm², 1 W | DOCUMENTED fallback node |
| `v1-assumed-40` | 40 nm, 500 MHz, 12 mm², 1.5 W | MemoryFlow v1 assumption, kept for comparison |
| `full-28`, `full-16` | 28 nm / 800 MHz / 60 mm² / 8 W; 16 nm / 1.2 GHz / 80 mm² / 15 W; 8 cores | ASSUMPTION (core count DOCUMENTED) |

External-memory PHY availability by node is `ExtMemConfig.max_node_nm` and is always enforced:
QSPI / HyperRAM ≤180 (digital PHY), DDR3 ≤130, LPDDR2 ≤65, DDR4-2400 ≤55, DDR4-3200 ≤40,
LPDDR4X ≤28, LPDDR5 / HBM2E ≤16, HBM3 ≤7. Multi-channel LPDDR4X/LPDDR5 presets (2×32, 4×32) scale
bandwidth and PHY area per channel. All of these are assumptions and can be overridden.

**Recommendation rule:** the smallest-area feasible point within 90 % of the best feasible
suite geomean. *Minimal* is the smallest within 60 %; *stretch* is the best feasible.

## Area

* SRAM: each bank is mapped to a macro grid (`plan_macro_tiling`, identical to
  `sf_sram_1rw IMPL=1`). Macro area = bits × bitcell / efficiency(bits) × port factor.
  `CompilerTableAreaModel` takes real compiler CSVs.
* Logic: Yosys generic cells → NAND2-equivalents (flop = 5.33 GE) → mm², at 0.70 utilisation.
  Scaling laws in `area.scaled_logic_ge`; the reference GE values are replaced by this run's Yosys
  results when `build/syn/synth_results.json` exists.

## Balance (v2, `memoryflow.models.balance`, `memoryflow balance`)

* `kernel_balance`: every ceiling of a kernel (compute, DRAM, DMA, SPM path, drain), the binding one,
  and its **headroom**: next ceiling / binding ceiling, i.e. how much faster the kernel gets if only the
  binding resource were unlimited. 1.0× means two resources bind together (balanced).
* `machine_balance`: provisioned bytes per peak op at each level, the share of kernels each resource
  binds, geomean headroom.
* `cpu_orchestration`: core cycles to program DMA transfers (double-buffered half-SPM chunks,
  ASSUMPTION 64 cycles each) and tensor tile commands (ASSUMPTION 24 cycles), as a share of the cores,
  and the number of accelerator tiles one core can keep fed: the CPU axis of the balance.

## Energy

Horowitz (ISSCC 2014) 45 nm anchors, scaled by an indicative C·V² node table. SRAM access energy
is fitted exactly through (8 KiB, 10 pJ), (32 KiB, 20 pJ) and (1 MiB, 100 pJ) per 64-bit access.
DRAM pJ/bit comes from the external-memory preset. Memory power = energy per byte × bytes per second.
Static power is `leakage_share(node)` × dynamic (indicative LP trend: 4 % at 130 nm, 8 % at 65 nm,
10 % at 40 nm, 15 % at 28 nm, 20 % at 16 nm).
