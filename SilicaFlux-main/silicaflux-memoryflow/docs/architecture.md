# MemoryFlow architecture

## Protocols

**SF-MEM** — the memory request/response protocol used by every memory-mapped port:

* request: `valid, ready, we, addr[AW] (byte), wdata[DW], wstrb[DW/8]`
* response: `valid, ready, rdata[DW], err` (+ `corr` on SPM ports)
* every request gets exactly one response, in order per port; writes are acknowledged

**Streams** — DMA ⇄ accelerators use `valid, ready, data[DW], strb, last`.

**APB3** — control registers (see `register_map.md`).

## Blocks

| Block | Role | Key parameters |
|---|---|---|
| `sf_sram_1rw` | Logical SRAM abstraction; `IMPL=0` inferred (FPGA/RTL sim), `IMPL=1` grid of `sf_macro_1rw_leaf` macros (`MACRO_W × MACRO_D`) with a registered row mux | `LANE_W, LANES, DEPTH, IMPL` |
| `sf_sram_1r1w/2rw_inferred` | Two-port / true dual-port arrays (read-first) | |
| `sf_sram_bank` | SRAM + protection + byte enables + MBIST port + error injection. ECC_MODE 0 none, 1 parity per byte (byte writes native), 2 SECDED per word (partial writes do read-modify-write; an uncorrectable RMW read suppresses the write) | `DW, DEPTH, ECC_MODE` |
| `sf_spm_banked` | NPORTS × NBANKS scratchpad: interleave (modulo / XOR / block), round-robin per bank, per-port response FIFOs + credits (no dropped responses under backpressure), address-overflow error path at matched latency, ECC counters, injection, parallel March C- MBIST, perf counters | `NPORTS, NBANKS, BANK_DEPTH, INTERLEAVE, RSP_DEPTH` |
| `sf_mem_router` | 1→N address router; slaves see offsets; decode errors generated locally; an ordering FIFO keeps responses in order across slaves with different latencies | `NS, BASES, SIZES, MAXOUT` |
| `sf_dma` | Channel table (APB registers, validation, progress, IRQ) + two `sf_dma_engine`s: engine 0 serves memory-sourced channels (MEM→MEM, MEM→stream), engine 1 serves stream-sourced channels (stream→MEM). The engines share the write master through a round-robin arbiter | `NCH, DFIFO_DEPTH, DESC_DEPTH, MAX_BURST_LOG2` |
| `sf_dma_engine` | RR burst scheduler, read side (memory reads with credit, or stream ingest), descriptor FIFO, data FIFO, write side (memory writes or stream out with tail strobes and `last`) | |
| `sf_vec_unit` | DW/16 int16 lanes: ADD, MUL, DOT (64-bit accumulate), AXPY; two joined input FIFOs | `IN_FIFO` |
| `sf_tensor_array` | TR × TC int8 outer-product MAC array; int32 accumulation buffer, optional double-buffering (computes tile n+1 while tile n drains) | `TR, TC, ACC_DBUF` |
| `sf_reuse_buffer` | Ping-pong operand buffer in one 1R1W SRAM; replays a sealed tile `cfg_replay` times (B-operand reuse), fills the other bank meanwhile | `DEPTH` |
| `sf_mc25_vport_bridge` (v2) | SF-MEM read + write slave → the **existing SilicaFlux 2.5** `memory_controller` vector port: adds the SPM base, round-robins reads/writes onto the single port, reserves response-FIFO credit before issuing (the port's single in-order response stream would otherwise head-of-line block and deadlock a DMA), maps lane-granular strobes to the lane mask and poisons partial-lane writes. Verified in `tb_sf25_dma_bridge` | `SPM_BASE, RD_DEPTH, WR_DEPTH` |
| `sf_memflow_top` | Integration: APB split (DMA / control), 3-port SPM (DMA rd, DMA wr, CPU host TCM port), two routers (SPM at 0x0, EXT at 0x8000_0000), DMA stream ports wired to the vector unit, tensor array and reuse buffer | all of the above |

## Address map (`sf_memflow_top`)

| Range | Target |
|---|---|
| `0x0000_0000 – SPM_BYTES-1` | scratchpad (DMA ports 0/1; CPU host port 2) |
| `0x8000_0000 – 0xFFFF_FFFF` | external memory master ports `xr_*` / `xw_*` (to the DDR controller) |
| other | decode error → DMA `ERR_CODE` 4/5 |

## Stream port allocation

| DMA port | Connected to |
|---|---|
| `so0`, `so1` | vector unit A, B |
| `so2` | tensor array A (column beats) |
| `so3` | reuse buffer → tensor array B (row beats) |
| `si0` | vector unit result |
| `si1` | tensor array C (row-major int32, DW/32 per beat) |

## Data layout for GEMM

A tiles are stored column-major (one beat = column `A[:, k]`, TR int8). B is stored row-major
(one beat = row `B[k, :]`). C comes back row-major. `memoryflow.verify.golden.pack_tensor_*`
generate these layouts.

## Rules learned in verification (they apply to anything that uses this subsystem)

1. Joined operand streams need FIFO depth ≥ DMA burst length, or must be sequenced. This is
   demonstrated by `tb_deadlock`.
2. Stream-sourced (S2MM) and memory-sourced (MM2S) transfers need independent engines. The single
   shared engine deadlocked in `tb_system`.
3. SPM response credit depth must be ≥ the 4-cycle round trip for 1 request/cycle/port.
4. DMA outstanding beats must cover the external memory's bandwidth-delay product.
5. Avoid bank-aligned source/destination buffers for SPM→SPM copies, or use XOR interleave.
