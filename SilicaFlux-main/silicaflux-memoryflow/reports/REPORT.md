# SilicaFlux MemoryFlow - engineering report

Generated 2026-11-05T14:07:45 by memoryflow 2.0.0. Budget `silicaflux-v-65`: node 65 nm, 200 MHz, 8.0 mm2 core / 1.0 W (DOCUMENTED: SilicaFlux-V reduced-ASIC p.1/p.3, 03-11-26 update p.7-9).

Provenance tags: THEORETICAL ceilings, ANALYTICAL models, PY_SIMULATION, RTL_SIMULATION. No silicon or FPGA MEASURED data exists yet.

## Recommended prototype memory configurations

| tier | SPM KiB | banks | width b | tensor | vec lanes | burst | DMA rd out | DMA wr acks | ext. memory | dense Gop/s | stream Gop/s | geomean | mm2 | W |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Minimal | 128 | 4 | 128 | 8x8 | 8 | 16 | 16 | 8 | DDR3-1600 x16 | 25.6 | 1.14 | 3.96 | 3.74 | 0.48 |
| Recommended | 128 | 4 | 128 | 16x16 | 8 | 16 | 16 | 32 | DDR3-1600 x16 | 72.2 | 1.15 | 6.02 | 4.64 | 0.48 |
| Stretch | 512 | 16 | 128 | 16x16 | 8 | 16 | 64 | 32 | LPDDR2-800 x32 | 82.1 | 1.21 | 6.54 | 7.77 | 0.25 |


* 2484 of 2880 evaluated configurations fit the budget.
* Best feasible suite geomean: 6.54 Gop/s (512KiB/16b/128w T16x16 V8 B16/F64 LPDDR2-800 x32, 7.8 mm2).
* Recommended = smallest-area point within 90 % of that: 6.02 Gop/s in 4.6 mm2.
* DMA path 1.97 GB/s vs DRAM sustained 2.08 GB/s.

### RTL parameter mapping (recommended tier)

| item | value | sf_memflow_top parameters |
|---|---|---|
| SPM capacity | 128 KiB | SPM_NBANKS=4, SPM_BANK_DEPTH=2048 |
| datapath width | 128 b | DW=128 |
| interleave | XOR | SPM_INTERLEAVE=1 |
| ECC | SECDED | SPM_ECC=2 (137-bit stored word) |
| tensor array | 16x16 | TEN_TR=16, TEN_TC=16, TEN_ACC_DBUF=1 |
| vector lanes | 8 | VEC_EW=16 (lanes = DW/16 = 8) |
| DMA | burst 16, 16 outstanding reads, 32 write acks | DMA_MAXBURST=4, DMA_DFIFO=16, DMA_NCH=4 (sf_dma WOUT=32) |
| operand FIFOs | >= burst | VEC_IN_FIFO=16, TEN_IN_FIFO=16 |
| macros | foundry | SPM_IMPL=1 + compiler views (MACRO_W/MACRO_D per bank) |


## Key findings

**The SilicaFlux 2.5 tensor unit is starved by its own memory system.** In isolation it sustains 63.4 MAC/cycle (RTL_SIMULATION). It has no accumulation buffer, so every 4x4x4 product moves 32 B of operands in and 64 B of INT32 partials out; the tile's 16 B/cycle vector port and single 128-bit register write port cap it at 9 % of peak on a 512^3 GEMM even with MemoryFlow's DMA and DDR3 (2.40 of 25.3 Gop/s; bound: spm). The recommended outer-product array with in-array accumulators reaches 71.7 Gop/s (30x) in 4.6 mm^2.

**The SilicaFlux 2.x hierarchy above the tile exists only as instantiations.** silicaflux_top.sf (Gen-2.5) instantiates 27 module types; 26 of them (31 of 32 instances) are defined nowhere in the repository, including the L2 (sf_l2_cache, 2 MiB/complex), the LLC (sf_llc_bank, 8 x 4 MiB), the coherent crossbar, the memory fabric / AXI edge and the DMA bridge; the earlier silicaflux_rtl*.zip tops leave 10 of 11 types undefined. Only the Gen-1 top is complete. No SilicaFlux generation has a DRAM controller or PHY, so the external-memory side of the processor has to be designed, not integrated; MemoryFlow supplies the DMA, router, SPM, bridge and models for it.

**The Gen-2.5 compute tile cannot be elaborated from repository sources.** instance u_memory_controller of `memory_controller` (memory_controller.sf:94): 7/9 named ports and 2/2 parameters absent on the definition (e.g. req_valid_i, req_i, req_ready_o, rsp_valid_o). 29 of 30 package types used are defined by no package in set `sf25` (e.g. sf_alu_req_t, sf_alu_rsp_t, sf_br_mask_t, sf_br_res_t). The 2.5 testbenches tb_memory_controller.sf and tb_tensor_unit.sf also target interfaces the in-repo modules do not have. The individual units (memory_controller.sf, tensor_unit.sf, vector_engine.sf, register_bank.sf) do elaborate and were characterised directly.

**The documented SRAM area is about 3x optimistic.** The reduced-ASIC plan prices 256 KB at ~0.5 mm^2 using a 0.12 um^2 bitcell at 65 nm, about 4x smaller than published 65 nm high-density 6T cells (~0.52 um^2); with macro periphery MemoryFlow estimates 1.46 mm^2 at 65 nm and 6.89 mm^2 at 130 nm (ANALYTICAL, replace with memory-compiler data). At 130 nm the documented 256 KiB alone exceeds the 8 mm^2 core budget.

**The Gen-2.5 scratchpad controller is sound; its burst port is the weak link.** 150k+ self-checks pass on the unmodified memory_controller.sf (random traffic with backpressure, range/domain/overflow protection, parity detection, burst kill). Each port sustains ~1 request/cycle with a 3-cycle load latency; three requesters together move 29.9 B/cycle. The burst ('DMA') port allows one descriptor in flight with a done handshake, costing 3 (store) / 4 (load) cycles per burst: 0.20 beats/cycle at 1 beat, 0.80 at 16. A second descriptor slot would hide it.

**Gen-1 DFLOAD/DFSTORE bursts longer than 4 words are broken, and its SPM needs two write ports.** tb_sf1_memctrl: a DFSTORE of 8 words leaves 4 words unwritten and a DFLOAD of 8 re-reads words 0..3 (burst_addr never advances; the 128-bit buffer index wraps). The tile write-back port and the FSM write the array in the same cycle (2 writes measured), which no single-port SRAM macro can implement. Gen-1 bandwidth: 2.29 B/cycle per tile.

**DMA write acknowledgements, not reads, limit write-back to memory.** MemoryFlow sf_dma driving the unmodified 2.5 SPM through sf_mc25_vport_bridge: EXT->SPM 11.4 B/cycle, but SPM->EXT only 6.06 B/cycle: 8 outstanding write acks against a 20-cycle memory (Little's law: 8/21 x 16 B = 6.10). The models now carry this DMA write path (WOUT is an exploration dimension). SPM->SPM copies reach 8.0 B/cycle because reads and writes share the controller's single vector port.

**130 nm is a fallback only if SilicaFlux-V shrinks to 128 KiB.** At 130 nm / 100 MHz no configuration with more than 128 KiB of SPM fits the 8 mm^2 core budget, and the best point reaches 1.28 Gop/s (vs 6.02 at 65 nm). DDR-class PHYs are not assumed at 130 nm; HyperRAM is the practical external memory there.

**For the full SilicaFlux, multi-channel LPDDR is the commercial sweet spot; HBM is a stretch option.** At 28 nm (no HBM PHY assumed) the recommended full chip is 32x 256KiB/4b/128w T16x16 V8 B16/F16 LPDDR4X-4266 2x32: 193 Gop/s suite geomean in 37 mm^2, 3.2 W; a single LPDDR4X x32 channel caps any configuration at 109 Gop/s. At 16 nm, LPDDR5 4x32 reaches 539 Gop/s (45 % of HBM2E's 1197) at 5.6 W vs 14.7 W, on an organic package instead of a 2.5D interposer. Tile scaling: 32 -> 64 tiles behind LPDDR4X-4266 2x32: +9 % performance for +83 % area (80 % of kernels bound by external memory or the DMA); 32 -> 64 tiles behind HBM2E 1 stack: +54 % performance for +45 % area (40 % of kernels bound by external memory or the DMA). Behind LPDDR the knee is well below the recommendation rule's pick (see the best-Gop/s-per-mm^2 rows); behind HBM more tiles keep paying. Full-chip envelopes are ASSUMPTIONS.

**A no-DRAM SilicaFlux-V demonstrates the core but starves the accelerators.** The documented no-DRAM target reaches 0.208 Gop/s suite geomean (QSPI-class link); the same machine with DDR3-1600 x16 reaches 1.55. On the 65 nm budget the best points per external memory are: QSPI 104 MHz (no DRAM) 0.25 Gop/s in 7.3 mm^2; HyperRAM 200 MHz x8 1.92 Gop/s in 5.5 mm^2; 2x HyperRAM 200 MHz x8 3.18 Gop/s in 5.5 mm^2; LPDDR2-800 x32 6.54 Gop/s in 7.8 mm^2; DDR3-1600 x16 6.54 Gop/s in 7.4 mm^2. HyperRAM (digital PHY, ~12 pins) is the low-cost, mature-node option; DDR3/LPDDR2 buys ~2-3x more.

**Outstanding DMA capacity must cover the external memory's bandwidth-delay product.** RTL reference (16 outstanding 64-bit beats, LPDDR2-800 x32, ~100 ns at 200 MHz): DMA read path 0.95 GB/s, write path 0.47 GB/s, DRAM sustained 2.08 GB/s. Covering the bandwidth-delay product of the recommended memory (DDR3-1600 x16) needs >= 13 128-bit beats in flight; the recommendation uses 16 outstanding reads and 32 outstanding write acks.

**A single shared DMA engine deadlocks against its own accelerator.** tb_system hung when an accelerator->SRAM (S2MM) channel occupied the only read engine while the operands it was waiting for were queued behind it. sf_dma now has independent MM2S/MEM2MEM and S2MM engines sharing one channel table; tb_dma, tb_system and tb_deadlock pass on the fixed RTL.

**Joined operand streams need FIFO depth >= DMA burst length (or sequenced loads).** tb_deadlock: with a 4-entry vector-unit FIFO and 16-beat bursts the DMA stalls after 4 beats and the watchdog fires; with 16 entries all 256 result beats complete. Predicate joined_stream_deadlock(4,16)=True.

**Bank-aligned SRAM-to-SRAM copies resonate into read/write bank conflicts.** RTL: a 4 KiB SPM->SPM copy with 16-beat bursts takes 652 cycles, but 556 cycles when the destination is skewed by one beat. XOR interleave or buffer skew removes it; the Python cycle model matches the skewed case but not the aligned resonance (listed as a model limitation).

**Power-of-two strides: XOR interleave fixes strides up to the fold width only.** RTL tb_spm (4 banks, 3 ports): stride 4 throughput 1.50 (modulo) -> 2.39 (XOR); stride 16 gives 1.00 with the 2-bit XOR fold. Block interleave is worst for streaming (1.23 at stride 1, 8 banks) and best for random traffic (2.63 requests/cycle).

**Accumulator double-buffering is worth ~1.8x on the tensor array when K equals the drain length.** RTL tb_accel, K=32: 88.6 % vs 49.7 % MAC utilisation. The analytical tile model (per tile max(K, drain) with double-buffering, K + drain without) reproduces RTL to 0.0 % after fitting its 1-3 cycle pipeline fill to these runs; the per-tile slope is not fitted.

**Response-credit depth must cover the 4-cycle SPM round trip.** RTL: RSP_DEPTH=2 gives 0.50 vs 1.00 requests/cycle single-port throughput with RSP_DEPTH=4, exactly as Little's law predicts (credits / round trip).

## SilicaFlux repository inventory (evidence)

246 HDL files / 94,507 lines from 11 source sets. Full evidence with origin:line anchors: `inventory.md`.

| category | IMPLEMENTED | STANDALONE | NOT_ELABORABLE | BEHAVIOURAL | REFERENCED_ONLY | DOCUMENTED_ONLY | ABSENT | MEMORYFLOW |
|---|---|---|---|---|---|---|---|---|
| CPU cache interface | Coherence write-notify hook | Direct-mapped / set-associative caches | - | - | Core L1 <-> L2 port (sf_core / sf_l2_cache) | - | - | sf_spm_banked host port (TCM-style, no cache) |
| L1 / L2 / last-level cache | - | - | - | - | Cluster L2 (2 MiB / complex, 16-way), LLC (8 banks x 4 MiB) + coherent crossbar | SilicaFlux-V L1 I/D caches (16 KB + 16 KB) | - | not recommended for SilicaFlux-V (DMA-managed SPM); modelled in memoryflow.models.cache |
| Scratchpad memory | Gen-1 per-tile scratchpad (4 x 1 KiB), Gen-2.5 banked scratchpad controller | - | Gen-2.5 tile SPM regions (16 KiB scalar + 64 KiB vector) | - | - | - | - | sf_spm_banked, sf_spm_banked + sf_mc25_vport_bridge |
| SRAM array | Gen-1 inferred arrays (SPM, IMEM, register file), Gen-2.5 bank arrays inside memory_controller | sf_sram_bank_decode helper, sfx_sram_interface (SilicaFlux-AI) | - | TestCore behavioural SRAM model | - | - | - | sf_sram_1rw / sf_sram_bank, sf_sram_1rw IMPL=0|1 + sf_macro_1rw_leaf |
| DMA engine | Gen-1 DFLOAD / DFSTORE bursts, Gen-2.5 burst descriptor port | sfx_dma (SilicaFlux-AI) | - | - | Cluster DMA bridge (sf_dma_bridge) | - | - | sf_dma, sf_dma (+ sf_mc25_vport_bridge) |
| Interconnect / router | Gen-1 2x2 XY mesh NoC | - | Gen-2.5 parametric wormhole mesh router, Tile-local crossbar (compute_tile.sf) | - | Coherent / memory fabric (sf_coh_xbar, sf_mem_fabric) | - | - | sf_mem_router |
| Vector register file | Gen-1 register bank (16 x 128 b), Gen-2.5 register bank (16 x 128 b, 3R/1W) | - | - | - | - | - | - | - |
| Tensor accumulation buffer | Gen-1 tensor unit (sequential 4x4), Gen-2.5 pipelined tensor unit (4x4x4 INT8 / cycle) | sfx_accumulator + systolic GEMM (SilicaFlux-AI) | Memory-fetching tensor engine (cmd: a/b/c_addr, k_m1, acc) | - | Cluster tensor engine (sf_tensor_engine) | - | - | sf_tensor_array, sf_tensor_array (double-buffered accumulators) |
| Memory controller | On-chip SPM controllers (Gen-1, Gen-2.5) | SDRAM-style controller FSM (memory_cache_repo) | - | - | - | - | SilicaFlux DDR / LPDDR controller | DDR4/LPDDR4 controller IP behind an SF-MEM -> AXI4 bridge (proposed) |
| External memory interface | Gen-1 chiplet tile interface | - | - | - | Cluster AXI memory ports (2 x AXI master) | - | DDR / LPDDR / HBM PHY | sf_extmem_model (behavioural, latency/bandwidth) + PHY presets in models.hardware |
| ECC / parity | Gen-2.5 per-byte parity, Gen-1 link parity placeholder | - | - | - | - | - | - | sf_ecc_secded_enc/dec + sf_sram_bank (SECDED, scrub on RMW, injection) |
| MBIST | - | TestCore MBIST controller + collar | - | - | - | - | - | sf_mbist_march (parallel banks, wired into sf_spm_banked) |


## Documented SilicaFlux-V targets

| key | quote | source | check |
|---|---|---|---|
| sfv_perf | ~20 MIPS at 100 MHz | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.1 | verified |
| sfv_die | &lt;10 mm² die | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.1 | verified |
| sfv_power | &lt;1 W) | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.1 | verified |
| sfv_cores | Reduce from 8 cores to 1 core | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.1 | verified |
| sfv_l1 | 16 KB I + 16 KB D L1 caches | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.1 | verified |
| sfv_l2 | 256 KB L2 block (acting as a scratchpad) | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.1 | verified |
| sfv_no_dram | we suggest no external DRAM | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.1 | verified |
| sfv_no_vector | no vector unit | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.1 | verified |
| sfv_node | We lean toward 65 nm as a sweet spot; 130 nm is a fallback | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.3 | verified |
| sfv_l2_macro | 32K * 64 * bitcell_area (~0.12 µm² each at 65 nm) ≈ 0.5 mm² | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.7 | verified |
| sfv_mbist | For each SRAM macro, include a built-in self-test (BIST) | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.9 | verified |
| full_sram | 36 Mb (full SilicaFlux) | SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf p.3 | verified |
| upd_params | 4 lanes, 128-bit width, 200 MHz | SilicaFlux_Update 03-11-26.pdf p.7 | verified |
| upd_soc | four-vector lane SIMD unit, 4×4 INT8 MAC tensor unit, and ~256 KiB of on-chip SRAM | SilicaFlux_Update 03-11-26.pdf p.8 | verified |
| upd_clock | 200 MHz CPU clock | SilicaFlux_Update 03-11-26.pdf p.9 | verified |
| node_65 | 65 nm emerges as the best compromise for SilicaFlux‑V | Process Node Comparison for SilicaFlux‑V.pdf p.3 | verified |
| node_130 | 130 nm is a solid fallback | Process Node Comparison for SilicaFlux‑V.pdf p.3 | verified |
| research_tensor_lat | documented latency in source is about 66 cycles | SilicaFlux Codebase Research Report.pdf p.1 | verified |


* **vector/tensor units**: The reduced-ASIC plan drops vector/tensor units for first silicon; the 03-11-26 update specifies a 4-lane SIMD unit and a 4x4 INT8 tensor unit. MemoryFlow evaluates both and recommends the latter only where the memory system can feed it.
* **clock**: 100 MHz (reduced-ASIC) vs 200 MHz (update). MemoryFlow uses 200 MHz at 65 nm and 100 MHz at 130 nm.
* **SRAM density**: The 0.12 um^2 / 65 nm bitcell (0.5 mm^2 for 256 KB) is ~4x denser than published 65 nm high-density 6T cells (~0.5 um^2); MemoryFlow's area model uses the published value, so 256 KiB costs ~1.5 mm^2 at 65 nm including macro periphery (about 3x the documented estimate).

## Characterisation of the existing SilicaFlux RTL (RTL_SIMULATION)

| testbench | result | expected | ok | checks | scope |
|---|---|---|---|---|---|
| sf25_memctrl | PASS | PASS | OK | 150843 | SilicaFlux 2.5 banked SPM controller: latency, streaming, burst-length sweep, bank contention, random traffic + backpressure, boundaries/overflow, parity, burst kill |
| sf25_tensor | PASS | PASS | OK | 32016 | SilicaFlux 2.5 tensor unit (4x4x4 INT8): golden results, wrap/saturate, latency, sustained issue rate with and without result backpressure |
| sf1_memctrl | DEFECT | DEFECT | OK | 302 | SilicaFlux v1 tile memory controller: latency / bandwidth; reproduces the DFLOAD/DFSTORE > 4-word burst defect |
| sf1_tensor | PASS | PASS | OK | 3216 | SilicaFlux v1 sequential tensor unit: golden results and start-to-done latency |
| sf25_dma_bridge | PASS | PASS | OK | 4140 | MemoryFlow sf_dma moving data DRAM <-> the unmodified SilicaFlux 2.5 SPM through sf_mc25_vport_bridge; read back through the SilicaFlux scalar port |


| measurement | value | unit | testbench |
|---|---|---|---|
| 2.5 SPM scalar / vector load latency | 3 | cycles | tb_sf25_memctrl |
| 2.5 SPM vector-port stream | 15.98 | B/cycle | tb_sf25_memctrl |
| 2.5 SPM scalar+vector, disjoint banks | 1.99 | req/cycle | tb_sf25_memctrl |
| 2.5 SPM scalar+vector, same bank | 1.00 | req/cycle | tb_sf25_memctrl |
| 2.5 SPM all three requesters streaming | 29.87 | B/cycle | tb_sf25_memctrl |
| 2.5 burst port, 1-beat bursts (load) | 0.20 | beats/cycle | tb_sf25_memctrl |
| 2.5 burst port, 16-beat bursts (load) | 0.80 | beats/cycle | tb_sf25_memctrl |
| 2.5 burst port, 256-beat bursts (load) | 0.98 | beats/cycle | tb_sf25_memctrl |
| 2.5 tensor unit latency | 21 | cycles | tb_sf25_tensor |
| 2.5 tensor unit sustained | 63.4 | MAC/cycle | tb_sf25_tensor |
| 2.5 tensor unit, results drained through one 128-bit port | 15.9 | MAC/cycle | tb_sf25_tensor |
| MemoryFlow DMA -> 2.5 SPM (EXT->SPM) | 11.43 | B/cycle | tb_sf25_dma_bridge |
| 2.5 SPM -> EXT (WOUT = 8, 20-cycle memory) | 6.06 | B/cycle | tb_sf25_dma_bridge |
| 2.5 SPM -> SPM via the single vector port | 7.96 | B/cycle | tb_sf25_dma_bridge |
| Gen-1 SPM scalar loads | 1.33 | B/cycle | tb_sf1_memctrl |
| Gen-1 SPM VLOAD | 2.29 | B/cycle | tb_sf1_memctrl |
| Gen-1 DFSTORE of 8 words: words never written | 4 | words | tb_sf1_memctrl |
| Gen-1 tensor unit | 0.94 | MAC/cycle | tb_sf1_tensor |


## SilicaFlux as built vs documented vs recommended (ANALYTICAL, RTL-measured inputs)

| machine | kind | tensor peak Gop/s | vector peak Gop/s | SPM->engine GB/s | ext. memory GB/s | dense Gop/s | stream Gop/s | geomean | mm2 | W |
|---|---|---|---|---|---|---|---|---|---|---|
| SilicaFlux v1 cluster (as built) | AS-BUILT | 0.8 | 1.6 | 0.46 | 0.080 | 0.72 | 0.053 | 0.151 | 0.95 | 0.02 |
| SilicaFlux 2.5 tile (as built) | AS-BUILT | 25.3 | 0.8 | 3.00 | 0.026 | 1.87 | 0.028 | 0.150 | 1.71 | 0.02 |
| SilicaFlux 2.5 tile + MemoryFlow DMA + DDR3 | INTEGRATED | 25.3 | 0.8 | 3.00 | 2.080 | 2.40 | 0.572 | 1.015 | 3.49 | 0.47 |
| SilicaFlux-V documented target (no DRAM) | DOCUMENTED | 6.4 | 1.6 | 1.40 | 0.026 | 4.14 | 0.028 | 0.208 | 2.19 | 0.02 |
| SilicaFlux-V documented target + DDR3 | DOCUMENTED | 6.4 | 1.6 | 1.40 | 2.080 | 6.40 | 0.605 | 1.555 | 3.97 | 0.33 |
| MemoryFlow recommended (128KiB/4b/128w T16x16 V8 B16/F16 DDR3-1600 x16) | RECOMMENDED | 102.4 | 3.2 | 2.80 | 2.080 | 72.19 | 1.150 | 6.022 | 4.64 | 0.48 |


## Node and external-memory comparison

| budget | envelope | basis | feasible | largest SPM | recommended | geomean | mm2 | W |
|---|---|---|---|---|---|---|---|---|
| silicaflux-v-65 | 65 nm / 200 MHz / 8.0 mm2 / 1.0 W | DOCUMENTED | 2484/2880 | 1024 KiB | 128KiB/4b/128w T16x16 V8 B16/F16 DDR3-1600 x16 | 6.02 | 4.64 | 0.48 |
| silicaflux-v-130 | 130 nm / 100 MHz / 8.0 mm2 / 1.0 W | DOCUMENTED fallback node (reduced-ASIC p.3, node comparison p.3); 100 MHz per reduced-ASIC p.1 | 102/2304 | 128 KiB | 128KiB/4b/64w T8x8 V4 B16/F16 2x HyperRAM 200 MHz x8 | 1.16 | 7.52 | 0.10 |
| v1-assumed-40 | 40 nm / 500 MHz / 12.0 mm2 / 1.5 W | ASSUMPTION of MemoryFlow v1 (made without the repository documents) - kept for comparison | 4032/4032 | 1024 KiB | 128KiB/8b/128w T16x16 V8 B16/F64 DDR4-3200 x32 | 17.80 | 4.70 | 1.04 |
| full-28 | 28 nm / 800 MHz / 60.0 mm2 / 8.0 W | ASSUMPTION for the full 8-core SilicaFlux (core count DOCUMENTED, silicaflux_top.sf); area / power / clock are MemoryFlow assumptions | 19966/20736 | 1024 KiB | 32x 256KiB/4b/128w T16x16 V8 B16/F16 LPDDR4X-4266 2x32 | 193.44 | 36.79 | 3.22 |
| full-16 | 16 nm / 1200 MHz / 80.0 mm2 / 15.0 W | ASSUMPTION | 29892/29952 | 1024 KiB | 32x 128KiB/8b/128w T16x16 V8 B16/F64 HBM2E 1 stack | 1091.51 | 27.75 | 13.39 |


## Full SilicaFlux processor (ASSUMED envelopes)

| budget | tier | configuration | dense | stream | geomean | mm2 | W |
|---|---|---|---|---|---|---|---|
| full-28 | minimal | 8x 128KiB/4b/128w T16x16 V8 B16/F64 LPDDR4X-4266 2x32 | 2283.4 | 18.46 | 126.8 | 13.0 | 1.75 |
| full-28 | recommended | 32x 256KiB/4b/128w T16x16 V8 B16/F16 LPDDR4X-4266 2x32 | 4566.0 | 23.51 | 193.4 | 36.8 | 3.22 |
| full-28 | stretch | 32x 512KiB/16b/128w T16x16 V8 B16/F16 LPDDR4X-4266 2x32 | 4866.6 | 24.09 | 201.4 | 51.4 | 3.35 |
| full-28 | best Gop/s per mm2 | 8x 128KiB/4b/128w T16x16 V8 B16/F64 LPDDR4X-4266 2x32 | 2283.4 | 18.46 | 126.8 | 13.0 | 1.75 |
| full-28 | best on LPDDR4X-4266 x32 | 32x 512KiB/4b/128w T16x16 V8 B16/F16 LPDDR4X-4266 x32 | 2545.5 | 13.36 | 109.1 | 45.7 | 2.42 |
| full-28 | best on LPDDR4X-4266 2x32 | 32x 512KiB/16b/128w T16x16 V8 B16/F16 LPDDR4X-4266 2x32 | 4866.6 | 24.09 | 201.4 | 51.4 | 3.35 |
| full-16 | minimal | 32x 128KiB/4b/128w T16x16 V4 B16/F64 HBM2E 1 stack | 13860.8 | 146.27 | 903.2 | 26.9 | 13.73 |
| full-16 | recommended | 32x 128KiB/8b/128w T16x16 V8 B16/F64 HBM2E 1 stack | 14850.8 | 191.52 | 1091.5 | 27.7 | 13.39 |
| full-16 | stretch | 32x 1024KiB/16b/128w T16x16 V8 B16/F128 HBM2E 1 stack | 15766.2 | 214.69 | 1197.2 | 53.6 | 14.71 |
| full-16 | best Gop/s per mm2 | 32x 128KiB/8b/128w T16x16 V8 B16/F64 HBM2E 1 stack | 14850.8 | 191.52 | 1091.5 | 27.7 | 13.39 |
| full-16 | best on LPDDR4X-4266 x32 | 32x 1024KiB/4b/128w T16x16 V8 B16/F16 LPDDR4X-4266 x32 | 2656.2 | 14.23 | 115.2 | 38.2 | 2.25 |
| full-16 | best on LPDDR4X-4266 2x32 | 32x 1024KiB/4b/128w T16x16 V8 B16/F16 LPDDR4X-4266 2x32 | 5312.3 | 27.44 | 225.5 | 41.0 | 4.49 |
| full-16 | best on LPDDR5-6400 x32 | 32x 1024KiB/4b/128w T16x16 V8 B16/F16 LPDDR5-6400 x32 | 3984.9 | 21.35 | 172.9 | 38.4 | 3.20 |
| full-16 | best on LPDDR5-6400 2x32 | 32x 1024KiB/16b/128w T16x16 V8 B16/F16 LPDDR5-6400 2x32 | 7571.5 | 38.48 | 318.3 | 42.8 | 4.22 |
| full-16 | best on LPDDR5-6400 4x32 | 32x 1024KiB/16b/128w T16x16 V8 B16/F64 LPDDR5-6400 4x32 | 11882.2 | 68.55 | 539.0 | 49.6 | 5.64 |
| full-16 | best on HBM2E 1 stack | 32x 1024KiB/16b/128w T16x16 V8 B16/F128 HBM2E 1 stack | 15766.2 | 214.69 | 1197.2 | 53.6 | 14.71 |


## Compute / bandwidth balance (recommended SilicaFlux-V)

| kernel | unit | AI DRAM | AI on-chip | bound | headroom | next |
|---|---|---|---|---|---|---|
| GEMM 512x512x512 int8 | tensor | 93.09 | 25.60 | spm | 1.43x | compute |
| GEMM 64x4096x1024 int8 | tensor | 90.02 | 24.38 | spm | 1.50x | compute |
| CONV 64x56x56->64 k3 | tensor | 444.80 | 25.04 | spm | 1.46x | compute |
| CONV 256x14x14->256 k3 | tensor | 177.65 | 28.27 | spm | 1.29x | compute |
| VADD n=1048576 int16 | vector | 0.17 | 0.17 | dram | 1.35x | spm |
| DOT n=1048576 int16 | vector | 0.50 | 0.50 | dma | 1.06x | dram |
| FIR 64-tap n=1048576 | vector | 32.00 | 32.00 | compute | 20.80x | dram |
| FFT 4096-pt x64 | vector | 3.75 | 3.75 | compute | 2.44x | dram |
| JACOBI2D 5pt 2048x2048 x10 | vector | 1.25 | 1.25 | dram | 1.23x | compute |
| SpMV 131072 rows nnz/row=16 | vector | 0.13 | 0.13 | dma | 1.04x | dram |


| kernel | DMA transfers | tile cmds | core busy | tiles/core |
|---|---|---|---|---|
| GEMM 512x512x512 int8 | 44 | 8192 | 26.6 % | 3.8 |
| GEMM 64x4096x1024 int8 | 91 | 16384 | 25.4 % | 3.9 |
| CONV 64x56x56->64 k3 | 8 | 7056 | 25.8 % | 3.9 |
| CONV 256x14x14->256 k3 | 20 | 7056 | 29.2 % | 3.4 |
| VADD n=1048576 int16 | 96 | 0 | 1.0 % | 98.5 |
| DOT n=1048576 int16 | 64 | 0 | 1.0 % | 104.0 |
| FIR 64-tap n=1048576 | 64 | 0 | 0.0 % | 2047.9 |
| FFT 4096-pt x64 | 64 | 0 | 0.4 % | 240.0 |
| JACOBI2D 5pt 2048x2048 x10 | 5120 | 0 | 1.0 % | 98.5 |
| SpMV 131072 rows nnz/row=16 | 504 | 0 | 1.0 % | 102.3 |


## Verification

| testbench | result | expected | ok | checks | scope |
|---|---|---|---|---|---|
| ecc | PASS | PASS | OK | 108568 | SECDED K=32/64 vs Python golden; exhaustive 1-bit and 2-bit injection |
| sram_prims | PASS | PASS | OK | 44956 | 1RW inferred vs macro-tiled equivalence, 1R1W read-first, 2RW |
| bank_secded | PASS | PASS | OK | 37514 | bank: SECDED, byte-enable RMW, injection, RMW-uncorrectable suppression |
| bank_parity | PASS | PASS | OK | 35508 | bank: per-byte parity, native byte enables, detection |
| bank_noecc_macro | PASS | PASS | OK | 35475 | bank: no ECC on the foundry-macro abstraction (IMPL=1) |
| spm_mod | PASS | PASS | OK | 46643 | SPM random multi-port + contention + backpressure + overflow, modulo map |
| spm_xor | PASS | PASS | OK | 46618 | SPM same suite with XOR-hash interleave |
| spm_block_8b | PASS | PASS | OK | 47729 | SPM same suite, block interleave, 8 banks |
| spm_rsp2 | PASS | PASS | OK | 46678 | SPM with shallow response FIFO (credit-limited throughput) |
| mbist_clean | PASS | PASS | OK | 6 | March C- on fault-free SPM banks -> pass |
| mbist_fault | PASS | PASS | OK | 8 | March C- with injected stuck-at cell -> fail, bank/addr located |
| router | PASS | PASS | OK | 14243 | address router: ordering across unequal slave latencies, decode errors |
| dma | PASS | PASS | OK | 56285 | DMA: mem2mem, ext<->SPM, 2-D, streams, boundaries, errors, IRQ, multi-channel |
| accel | PASS | PASS | OK | 2572 | tensor array vs golden (K=1,8,37), double-buffer timing, vec ops, reuse buffer |
| system | PASS | PASS | OK | 33 | full subsystem: GEMM with B reuse, vector add/axpy/dot, ECC + MBIST via regs |
| deadlock_fifo4 | DEADLOCK | DEADLOCK | OK | 0 | joined-stream deadlock: operand FIFO (4) < DMA burst (16) -> watchdog fires |
| param_recommended | PASS | PASS | OK | 200 | recommended prototype parameterisation: 128-bit, 8 banks XOR, 16x16 tensor, 8 lanes, FIFO 64 |
| param_reference | PASS | PASS | OK | 312 | same smoke test at the reference parameterisation (cross-check of the parametric TB) |
| deadlock_fifo16 | PASS | PASS | OK | 1 | same scenario with FIFO >= burst -> completes |


## Mutation testing

| mutant | testbench | result | errors | verdict |
|---|---|---|---|---|
| rmw_merge_uses_raw_word | bank_secded | FAIL | 1 | killed |
| spm_overflow_off_by_one | spm_mod | FAIL | 32 | killed |
| dma_tail_strobe_off | dma | FAIL | 8 | killed |
| ecc_ignore_overall_parity | ecc | FAIL | 64688 | killed |


## Synthesis (Yosys generic, SRAM as blackbox macros)

| wrapper | ok | flops | comb GE | total GE | macros |
|---|---|---|---|---|---|
| syn_ecc64 | OK | 0 | 1211 | 1211 | 0 |
| syn_router2 | OK | 26 | 537 | 676 | 0 |
| syn_vec4x16 | OK | 2286 | 26318 | 38502 | 0 |
| syn_tensor_8x8 | OK | 6375 | 111522 | 145501 | 0 |
| syn_dma | OK | 4142 | 44148 | 66224 | 0 |
| syn_spm_256k | OK | 812 | 17295 | 21623 | 16 |
| syn_memflow_top | OK | 22608 | 226370 | 346870 | 64 |


## SPM size x external memory (suite geomean Gop/s; * = infeasible at 65 nm)

| SPM \ ext. memory | QSPI 104 MHz (no DRAM) | HyperRAM 200 MHz x8 | 2x HyperRAM 200 MHz x8 | LPDDR2-800 x32 | DDR3-1600 x16 |
|---|---|---|---|---|---|
| 128 KiB | 0.21 | 1.68 | 2.91 | 5.98 | 6.02 |
| 256 KiB | 0.23 | 1.85 | 3.02 | 6.07 | 6.11 |
| 512 KiB | 0.24 | 1.90 | 3.11 | 6.17 | 6.22 |
| 1024 KiB | 0.25* | 2.01* | 3.28* | 6.42* | 6.46* |


## Banks x width

| banks \ width (Gop/s / mm2) | 32 b | 64 b | 128 b | 256 b |
|---|---|---|---|---|
| 2 banks | 0.9 / 3.2 | 2.3 / 3.5 | 5.7 / 4.6 | 7.0 / 4.9 |
| 4 banks | 1.0 / 3.3 | 2.5 / 3.5 | 6.0 / 4.6 | 7.0 / 5.0 |
| 8 banks | 1.0 / 3.3 | 2.6 / 3.6 | 6.2 / 4.7 | 7.0 / 5.2 |
| 16 banks | 1.0 / 3.5 | 2.6 / 3.8 | 6.3 / 5.0 | 7.0 / 5.6 |


## Model calibration

SPM banking model: 32 cases, max |error| 1.65 %.

| DMA case | RTL cycles | cycle model | err | analytic | err |
|---|---|---|---|---|---|
| dma_ext2spm_4k_burst1_cycles | 2480.0 | 2482 | +0.1% | 2279 | -8.1% |
| dma_spm2spm_4k_burst1_cycles | 1036.0 | 1037 | +0.1% | 1033 | -0.3% |
| dma_ext2spm_4k_burst2_cycles | 1306.0 | 1308 | +0.2% | 1152 | -11.8% |
| dma_spm2spm_4k_burst2_cycles | 780.0 | 781 | +0.1% | 777 | -0.4% |
| dma_ext2spm_4k_burst4_cycles | 730.0 | 732 | +0.3% | 730 | +0.0% |
| dma_spm2spm_4k_burst4_cycles | 652.0 | 653 | +0.2% | 649 | -0.5% |
| dma_ext2spm_4k_burst8_cycles | 728.0 | 730 | +0.3% | 730 | +0.3% |
| dma_spm2spm_4k_burst8_cycles | 652.0 | 591 | -9.4% | 585 | -10.3% |
| dma_ext2spm_4k_burst16_cycles | 728.0 | 729 | +0.1% | 730 | +0.3% |
| dma_spm2spm_4k_burst16_cycles | 652.0 | 559 | -14.3% | 553 | -15.2% |


Figures: see `figures/`. Matrices: `*.csv`. SilicaFlux inventory: `inventory.md`; MemoryFlow self-inventory: `memoryflow_inventory.md`.
