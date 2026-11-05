# SilicaFlux MemoryFlow - engineering report

Generated 2026-11-03T19:45:17 by memoryflow 1.0.0. Node 40 nm, 500 MHz, budget 12.0 mm2 / 1.5 W.

Provenance tags: THEORETICAL ceilings, ANALYTICAL models, PY_SIMULATION, RTL_SIMULATION. No silicon or FPGA MEASURED data exists yet.

## Recommended prototype memory configurations

| tier | SPM KiB | banks | width b | tensor | vec lanes | burst | DMA FIFO | DRAM | dense Gop/s | stream Gop/s | geomean | mm2 | W |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Minimal | 128 | 4 | 128 | 16x16 | 8 | 16 | 64 | DDR4-2400 x16 | 180.5 | 2.18 | 12.76 | 3.45 | 0.48 |
| Recommended | 128 | 8 | 128 | 16x16 | 8 | 16 | 64 | DDR4-3200 x32 | 193.4 | 3.63 | 17.80 | 4.70 | 1.04 |
| Stretch | 1024 | 16 | 128 | 16x16 | 8 | 16 | 64 | DDR4-3200 x32 | 205.3 | 4.01 | 19.36 | 7.24 | 1.11 |


* 864 of 1440 evaluated configurations fit the mature-node budget.
* Best feasible suite geomean: 19.36 Gop/s (1024KiB/16b/128w T16x16 V8 B16/F64 DDR4-3200 x32, 7.2 mm2).
* Recommended = smallest-area point within 90 % of that: 17.80 Gop/s in 4.7 mm2.
* DMA path 7.53 GB/s vs DRAM sustained 8.96 GB/s.

### RTL parameter mapping (recommended tier)

| item | value | sf_memflow_top parameters |
|---|---|---|
| SPM capacity | 128 KiB | SPM_NBANKS=8, SPM_BANK_DEPTH=1024 |
| datapath width | 128 b | DW=128 |
| interleave | XOR | SPM_INTERLEAVE=1 |
| ECC | SECDED | SPM_ECC=2 (137-bit stored word) |
| tensor array | 16x16 | TEN_TR=16, TEN_TC=16, TEN_ACC_DBUF=1 |
| vector lanes | 8 | VEC_EW=16 (lanes = DW/16 = 8) |
| DMA | burst 16, 64 outstanding | DMA_MAXBURST=4, DMA_DFIFO=64, DMA_NCH=4 |
| operand FIFOs | >= burst | VEC_IN_FIFO=16, TEN_IN_FIFO=16 |
| macros | foundry | SPM_IMPL=1 + compiler views (MACRO_W/MACRO_D per bank) |


## Key findings

**DMA outstanding capacity, not DRAM, limits streaming kernels in the RTL reference.** With 16 outstanding 64-bit beats and ~90 ns DRAM latency the DMA path sustains 1.23 GB/s against 8.96 GB/s of DDR4-3200 x32. Covering the bandwidth-delay product of the recommended memory needs >= 51 128-bit beats in flight; the recommendation uses 64.

**A single shared DMA engine deadlocks against its own accelerator.** tb_system hung when an accelerator->SRAM (S2MM) channel occupied the only read engine while the operands it was waiting for were queued behind it. sf_dma now has independent MM2S/MEM2MEM and S2MM engines sharing one channel table; tb_dma, tb_system and tb_deadlock pass on the fixed RTL.

**Joined operand streams need FIFO depth >= DMA burst length (or sequenced loads).** tb_deadlock: with a 4-entry vector-unit FIFO and 16-beat bursts the DMA stalls after 4 beats and the watchdog fires; with 16 entries all 256 result beats complete. Predicate joined_stream_deadlock(4,16)=True.

**Bank-aligned SRAM-to-SRAM copies resonate into read/write bank conflicts.** RTL: a 4 KiB SPM->SPM copy with 16-beat bursts takes 652 cycles, but 556 cycles when the destination is skewed by one beat. XOR interleave or buffer skew removes it; the Python cycle model matches the skewed case but not the aligned resonance (listed as a model limitation).

**Power-of-two strides: XOR interleave fixes strides up to the fold width only.** RTL tb_spm (4 banks, 3 ports): stride 4 throughput 1.50 (modulo) -> 2.39 (XOR); stride 16 gives 1.00 with the 2-bit XOR fold. Block interleave is worst for streaming (1.23 at stride 1, 8 banks) and best for random traffic (2.63 requests/cycle).

**Accumulator double-buffering is worth ~1.8x on the tensor array when K equals the drain length.** RTL tb_accel, K=32: 88.6 % vs 49.7 % MAC utilisation. The analytical tile model (per tile max(K, drain) with double-buffering, K + drain without) reproduces RTL to 0.0 % after fitting its 1-3 cycle pipeline fill to these runs; the per-tile slope is not fitted.

**Response-credit depth must cover the 4-cycle SPM round trip.** RTL: RSP_DEPTH=2 gives 0.50 vs 1.00 requests/cycle single-port throughput with RSP_DEPTH=4, exactly as Little's law predicts (credits / round trip).

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


## SPM size x external memory (suite geomean Gop/s; * = infeasible at 40 nm)

| SPM \ ext. memory | DDR3-1600 x16 | DDR4-2400 x16 | DDR4-3200 x32 | LPDDR4X-4266 x32 | LPDDR5-6400 x32 | HBM2E 1 stack | HBM3 1 stack |
|---|---|---|---|---|---|---|---|
| 128 KiB | 10.8 | 13.1 | 17.8 | 17.8* | 17.8* | 17.8* | 17.8* |
| 256 KiB | 11.0 | 13.3 | 18.1 | 18.1* | 18.1* | 18.1* | 18.1* |
| 512 KiB | 11.2 | 13.5 | 18.4 | 18.4* | 18.4* | 18.4* | 18.4* |
| 1024 KiB | 11.6 | 14.1 | 19.1 | 19.1* | 19.1* | 19.1* | 19.1* |


## Banks x width

| banks \ width (Gop/s / mm2) | 32 b | 64 b | 128 b | 256 b |
|---|---|---|---|---|
| 2 banks | 2.3 / 3.9 | 6.0 / 4.0 | 15.1 / 4.6 | 21.0 / 4.9 |
| 4 banks | 2.6 / 3.9 | 6.7 / 4.1 | 17.0 / 4.7 | 21.0 / 4.9 |
| 8 banks | 2.7 / 3.9 | 7.0 / 4.1 | 17.8 / 4.7 | 21.0 / 5.0 |
| 16 banks | 2.8 / 4.0 | 7.1 / 4.2 | 18.1 / 4.8 | 21.0 / 5.2 |


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


Figures: see `figures/`. Matrices: `*.csv`. Inventory: `inventory.md`.
