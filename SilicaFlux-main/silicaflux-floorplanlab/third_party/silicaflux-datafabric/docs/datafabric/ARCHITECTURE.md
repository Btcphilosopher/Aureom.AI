# DataFabric architecture

## 1. Topology in SilicaFlux-V (`rtl/soc/sfv_soc_df.sv`)

```
  masters (SFB2)                      sfb_crossbar 4 x 7, round robin                 slaves
  ─────────────                  ┌──────────────────────────────────────┐
  0 DBG  (JTAG SBA)  ──────────► │ per master: decoder + access matrix  │──► 0 BOOT_ROM ── v1 adapter ── sfv_bootrom
  1 CPUD (CPU data)  ──────────► │   + decode-error slave               │──► 1..4 SRAM_BANK0..3 (32 KiB each)
  2 CPUI (CPU fetch) ──────────► │ per slave: arbiter (lock) + req mux  │      ├ SRAM_IMPL=0: v1 adapter ── sfv_sram_slave (+MBIST collar)
  3 DMA  (silicaflux_dma) ─────► │ response router (owner per slave)    │      └ SRAM_IMPL=1: sfb_sram_slave ── sramlib sram_sp (+MBIST tst port)
                                 └──────────────────────────────────────┘──► 5 TSPM ── v1 adapter ── sfv_tile (VE + TE + 4-bank scratchpad)
                                                                         └─► 6 PERIPH ── v1 adapter ── sfv_periph_bridge ── register bus pages:
                                                                               SYSCTRL INTC TIMER UART SPI GPIO | DMA (6) DFPERF (7) | VE TE
```

* **Why a crossbar, not a shared bus:** with a single shared slot the DMA and the
  CPU serialise even when they use different banks, and the per-master access
  matrix (execute-never peripherals for CPUI, peripheral denial for the DMA) cannot
  be applied after arbitration. A 4x7 crossbar costs ~7.3 k NAND2-eq versus ~2.2 k
  for a shared bus (generic gates, `reports/datafabric/synth.md`) — about 6 % of the
  SoC logic — and keeps the original release-1 cycle behaviour bit-exact.
* **Partial crossbar:** disabled master/slave pairs (`MST_SLV_EN`) are removed by
  constant propagation (no mux input, no arbiter request).
* **Single outstanding per port** (SFB2 R6) keeps responses ordered without IDs.
  With 1-cycle SRAM a port still sustains one transaction per cycle because a slave
  is re-granted in the cycle its response is accepted.

## 2. Components

| Module | Role | Key facts |
|---|---|---|
| `sfb_addr_decoder` | per-master decode | mask decode, first match, access-matrix bit, alignment check |
| `sfb_arbiter` | per-slave arbitration | fixed / round robin, grant lock, non-power-of-two N; RR search from memoryflow `sf_rr_arbiter` |
| `sfb_req_mux` | request payload | AND-OR one-hot mux |
| `sfb_rsp_router` | response steering | slave response only to its recorded owner |
| `sfb_error_slave` | decode errors | error response 1 cycle after acceptance, held under back-pressure |
| `sfb_crossbar` | the fabric | composes the above; event outputs for counters/traces |
| `sfb_reg_slice` / `sfb_skid_buffer` | timing slices | 2-entry skid (memoryflow `sf_skid_buffer` logic) |
| `sfb_v1_slave_adapter` | legacy slaves | response holding register for SFB v1 slaves |
| `sfb_shared_bus` | comparison topology | NMx1 + 1xNS crossbars |
| `sfb_perf_counters` | optional DFPERF page | saturating counters, atomic snapshot |
| `silicaflux_dma` | DMA | see [DMA.md](DMA.md) |
| `sfb_sram_slave`, `sfb_sram_1r1w_slave` | SRAM Wrapper Library adapters | see §5 |

## 3. Clock and reset

* **One functional clock** (`clk`) for the whole fabric, DMA, SRAM and peripherals
  (+ TCK inside the JTAG TAP, unchanged from release 1). No clock-domain crossing is
  introduced by DataFabric, so no CDC bridge or asynchronous FIFO is instantiated.
  If a future peripheral needs its own clock, the rule is: a valid/ready
  asynchronous FIFO with Gray-coded pointers (candidate: `memory_cache_repo`
  `async_fifo`, which needs a valid/ready wrapper, reset synchronisers and
  `set_max_delay -datapath_only` constraints — see AUDIT.md), never per-bit
  synchronisation of a multi-bit bus.
* **Resets** (unchanged structure): asynchronous assert, synchronous de-assert by
  `sfv_rst_sync`; DataFabric is in `sys_rst_n` (pin, soft reset, JTAG system reset),
  so the CPU, crossbar, DMA and slaves are reset together — the precondition for
  SFB2 R11 (in-flight transactions are cancelled consistently on both sides). The
  CPU-only reset (`cpu_rst_n`, JTAG hold) leaves the fabric running; a CPU held in
  reset drives `req_valid = 0`.
* No reset-generated writes: every master's `req_valid` is a reset flop; the fabric
  forwards nothing during reset (verified: `tb_dma +test=reset`, `tb_sfb_xbar +resets`).
* Clock gating is unchanged (tile engines only); DataFabric adds no gated clocks.
* `CLOCK_FREQUENCY` lives in the SDC (`third_party/silicaflux-v` constraints), not in RTL.

## 4. Vector / tensor integration

The production engines of release 1 (`sfv_vec_engine`, `sfv_tensor_engine` in
`sfv_tile`) are used unchanged. They operate on the tile scratchpad (TSPM), which is
an SFB slave of the crossbar, so the DMA reaches them without new ports:

```
CPU init → SRAM ──DMA──► TSPM ──► tensor/vector engine ──► TSPM ──DMA──► SRAM → CPU verify
```

* **Busy/ready handshake:** firmware starts an engine only after the DMA reported
  completion and fetches results only after the engine reported DONE (STATUS/IRQ of
  both blocks), so active input buffers are never overwritten. Hardware still
  guarantees determinism: an engine holding the TSPM lock has priority on every
  bank; fabric (DMA/CPU) accesses wait on bank conflicts (silicaflux-v
  `sfv_tile`).
* Demonstrated in the SoC (`firmware/examples/dma_demo`, D6/D7): 4x4 INT8 MATMUL
  with K = 4, 16, 64, 256 (signed and unsigned) and VE ADD/XOR/MUL/DOT, every result
  equal to the C golden models of silicaflux-v.
* Not done: the engines are not DMA *masters* themselves (no "tensor result → SRAM"
  initiated by the engine); a stream interface between DMA and engines was not
  added because the TSPM path already serves the 4x4 engine without extra hardware.

## 5. SRAM Wrapper Library integration (Project 01)

`third_party/silicaflux-sramlib` (vendored unmodified) is used through:

* `sfb_sram_slave` — SFB2 → `sram_sp` (1RW), `WRITE_ACK = 1`, any READ_LATENCY,
  response FIFO = READ_LATENCY + 1 (credit based), MBIST test port passed through;
* `sfb_sram_1r1w_slave` — SFB2 → `sram_1r1w`; posted library writes are acknowledged
  one cycle after the array accepted them.

Verified with the crossbar random testbench at READ_LATENCY 1, 2 and 3, 32/64 bit,
both macro types, resets (`tb_sfb_xbar -GSLAVES=1|2`), and in the SoC
(`-GSRAM_IMPL=1`: DMA demo, boot-ROM POST with **MBIST running on the library
banks**, release-1 acceptance app). Bank conflicts are arbitrated per slave port by
the crossbar (four SRAM banks = four ports); the library's own multi-master
`sram_bank_controller` was not needed for this topology.

## 6. Performance counters and traces

* `sfb_perf_counters` (DFPERF page): per master reads, writes, request-stall cycles,
  arbitration-loss cycles, response-stall cycles, error responses; DMA bytes,
  busy/idle cycles, max FIFO occupancy, 64-bit cycle counter. Saturating 32-bit
  counters, CTRL.SNAPSHOT copies all counters atomically (consistent 64-bit reads).
  ~7.0 k NAND2-eq: remove (`PERF = 0`) in an area-minimised first-silicon build.
* `tb/common/sfb_trace_monitor.sv`: simulation-only CSV trace (cycle, event, master,
  id, addr, op, size, slave, error, stall cycles) consumed by MemoryLab.
