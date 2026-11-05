# SilicaFlux memory-subsystem inventory (repository evidence)

Scanned 246 HDL files (94,507 lines, 178 distinct module names) from 11 source sets under `SilicaFlux-main/`. Every row below is backed by an `origin:line` anchor resolved at generation time; `IMPLEMENTED` / `STANDALONE` claims are confirmed by Verilator elaboration from repository sources only.

## Coverage by category

| Category | IMPLEMENTED | STANDALONE | NOT_ELABORABLE | BEHAVIOURAL | REFERENCED_ONLY | DOCUMENTED_ONLY | ABSENT | MemoryFlow provides |
|---|---|---|---|---|---|---|---|---|
| **CPU cache interface** | Coherence write-notify hook | Direct-mapped / set-associative caches | - | - | Core L1 <-> L2 port (sf_core / sf_l2_cache) | - | - | sf_spm_banked host port (TCM-style, no cache) |
| **L1 / L2 / last-level cache** | - | - | - | - | Cluster L2 (2 MiB / complex, 16-way)<br>LLC (8 banks x 4 MiB) + coherent crossbar | SilicaFlux-V L1 I/D caches (16 KB + 16 KB) | - | not recommended for SilicaFlux-V (DMA-managed SPM); modelled in memoryflow.models.cache |
| **Scratchpad memory** | Gen-1 per-tile scratchpad (4 x 1 KiB)<br>Gen-2.5 banked scratchpad controller | - | Gen-2.5 tile SPM regions (16 KiB scalar + 64 KiB vector) | - | - | - | - | sf_spm_banked<br>sf_spm_banked + sf_mc25_vport_bridge |
| **SRAM array** | Gen-1 inferred arrays (SPM, IMEM, register file)<br>Gen-2.5 bank arrays inside memory_controller | sf_sram_bank_decode helper<br>sfx_sram_interface (SilicaFlux-AI) | - | TestCore behavioural SRAM model | - | - | - | sf_sram_1rw / sf_sram_bank<br>sf_sram_1rw IMPL=0|1 + sf_macro_1rw_leaf |
| **DMA engine** | Gen-1 DFLOAD / DFSTORE bursts<br>Gen-2.5 burst descriptor port | sfx_dma (SilicaFlux-AI) | - | - | Cluster DMA bridge (sf_dma_bridge) | - | - | sf_dma<br>sf_dma (+ sf_mc25_vport_bridge) |
| **Interconnect / router** | Gen-1 2x2 XY mesh NoC | - | Gen-2.5 parametric wormhole mesh router<br>Tile-local crossbar (compute_tile.sf) | - | Coherent / memory fabric (sf_coh_xbar, sf_mem_fabric) | - | - | sf_mem_router |
| **Vector register file** | Gen-1 register bank (16 x 128 b)<br>Gen-2.5 register bank (16 x 128 b, 3R/1W) | - | - | - | - | - | - | - |
| **Tensor accumulation buffer** | Gen-1 tensor unit (sequential 4x4)<br>Gen-2.5 pipelined tensor unit (4x4x4 INT8 / cycle) | sfx_accumulator + systolic GEMM (SilicaFlux-AI) | Memory-fetching tensor engine (cmd: a/b/c_addr, k_m1, acc) | - | Cluster tensor engine (sf_tensor_engine) | - | - | sf_tensor_array<br>sf_tensor_array (double-buffered accumulators) |
| **Memory controller** | On-chip SPM controllers (Gen-1, Gen-2.5) | SDRAM-style controller FSM (memory_cache_repo) | - | - | - | - | SilicaFlux DDR / LPDDR controller | DDR4/LPDDR4 controller IP behind an SF-MEM -> AXI4 bridge (proposed) |
| **External memory interface** | Gen-1 chiplet tile interface | - | - | - | Cluster AXI memory ports (2 x AXI master) | - | DDR / LPDDR / HBM PHY | sf_extmem_model (behavioural, latency/bandwidth) + PHY presets in models.hardware |
| **ECC / parity** | Gen-2.5 per-byte parity<br>Gen-1 link parity placeholder | - | - | - | - | - | - | sf_ecc_secded_enc/dec + sf_sram_bank (SECDED, scrub on RMW, injection) |
| **MBIST** | - | TestCore MBIST controller + collar | - | - | - | - | - | sf_mbist_march (parallel banks, wired into sf_spm_banked) |

## Blocks and evidence

### CPU cache interface

* **Core L1 <-> L2 port (sf_core / sf_l2_cache)** [Gen-2.5] - `REFERENCED_ONLY` (not elaborated). silicaflux_top.sf wires 8 superscalar cores to per-complex L2 caches; neither module exists.
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:888` ``
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:967` `sf_l2_cache #(`
  * MemoryFlow: sf_spm_banked host port (TCM-style, no cache)
* **Coherence write-notify hook** [Gen-2.5] - `IMPLEMENTED` (elaborates). memory_controller.sf broadcasts every committed line write for a future L1 invalidate; no consumer exists.
  * `memory_controller.sf:157` `output logic      [NUM_BANKS-1:0]     coh_wr_valid_o,`
* **Direct-mapped / set-associative caches** [library] - `STANDALONE` (elaboration inconclusive). Generic write-back caches (256 x 64 B lines; 128 sets x 4 ways) in memory_cache_repo; not instantiated by any SilicaFlux top and carry simulation-only initial blocks.
  * `memory_cache_repo.zip::memory_cache_repo/rtl/direct_mapped_cache.sv:33` `parameter int CACHE_LINES = 256,`
  * `memory_cache_repo.zip::memory_cache_repo/rtl/set_assoc_cache.sv:8` `//    NUM_WAYS = 4  → pseudo-LRU (PLRU) binary tree using 3 bits per set`
  * note: elaboration inconclusive: Verilator and Icarus both stop on legal SV they do not support (Delayed assignment to array inside for loops (non-delayed is; Delayed assignment to array inside for loops (non-delayed is)

### L1 / L2 / last-level cache

* **SilicaFlux-V L1 I/D caches (16 KB + 16 KB)** [SilicaFlux-V] - `DOCUMENTED_ONLY` (not elaborated). Reduced-ASIC design proposes 16 KB I + 16 KB D L1 and a 256 KB L2/scratch; no RTL.
  * doc: *SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf* p.1: "16 KB I + 16 KB D L1 caches"
  * doc: *SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf* p.1: "256 KB L2 block (acting as a scratchpad)"
* **Cluster L2 (2 MiB / complex, 16-way)** [Gen-2.5] - `REFERENCED_ONLY` (not elaborated). Parameterised in silicaflux_top.sf; sf_l2_cache is not defined anywhere.
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:50` `parameter int unsigned L2_SIZE_KB             = 2048,`
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:967` `sf_l2_cache #(`
  * MemoryFlow: not recommended for SilicaFlux-V (DMA-managed SPM); modelled in memoryflow.models.cache
* **LLC (8 banks x 4 MiB) + coherent crossbar** [Gen-2.5] - `REFERENCED_ONLY` (not elaborated). 32 MiB of LLC SRAM implied by parameters; sf_llc_bank / sf_coh_xbar / sf_coh_mgr undefined.
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:35` `parameter int unsigned NUM_LLC_BANKS          = 8,`
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:52` `parameter int unsigned LLC_BANK_SIZE_KB       = 4096,`
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1419` `sf_llc_bank #(`
  * doc: *SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf* p.3: "36 Mb (full SilicaFlux)"

### Scratchpad memory

* **Gen-1 per-tile scratchpad (4 x 1 KiB)** [Gen-1] - `IMPLEMENTED` (elaborates). 256 x 32-bit words per tile behind a single FSM: one access at a time, 1 word/cycle bursts.
  * `silicaflux.zip::silicaflux/rtl/silicaflux_pkg.sv:27` `parameter int SRAM_DEPTH    = 256;  // Scratchpad SRAM words per tile`
  * `silicaflux.zip::silicaflux/rtl/memory_controller.sv:52` `logic [XLEN-1:0] sram [0:SRAM_DEPTH-1];`
  * `silicaflux.zip::silicaflux/rtl/compute_tile.sv:88` `memory_controller u_mem (`
  * MemoryFlow: sf_spm_banked
* **Gen-2.5 banked scratchpad controller** [Gen-2.5] - `IMPLEMENTED` (elaborates). 8 banks x 512 x 128 b (64 KiB) default, scalar + vector + burst requesters, per-bank arbitration, credit-reserved responses, per-byte parity. Elaborates stand-alone; its only instantiation (compute_tile.sf) uses a different port list.
  * `memory_controller.sf:99` `parameter int unsigned NUM_BANKS         = 8,              // power of two, >= 2`
  * `memory_controller.sf:100` `parameter int unsigned BANK_DEPTH        = 512,            // lines per bank, power of two, >= 2`
  * `memory_controller.sf:169` `localparam int unsigned NUM_REQ     = 3;`
  * `SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:1954` `.NUM_PORTS   (NUM_MC_PORTS),`
  * MemoryFlow: sf_spm_banked + sf_mc25_vport_bridge
* **Gen-2.5 tile SPM regions (16 KiB scalar + 64 KiB vector)** [Gen-2.5] - `NOT_ELABORABLE` (does NOT elaborate). compute_tile.sf maps a scalar and a vector SPM window, but the tile cannot be elaborated (memory_controller / tensor_unit interface drift, missing package types).
  * `SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:162` `parameter int unsigned SPM_S_BYTES    = 32'h0000_4000,`
  * `SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:164` `parameter int unsigned SPM_V_BYTES    = 32'h0001_0000,`
  * first elaboration error: `%Error: /home/user/Aureom.AI/SilicaFlux-main/silicaflux-memoryflow/build/sf_src/sf25/loose/SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:307:5: syntax error, unex`

### SRAM array

* **Gen-1 inferred arrays (SPM, IMEM, register file)** [Gen-1] - `IMPLEMENTED` (elaborates). Plain reg arrays; the SPM array is written from two always_ff blocks (FSM + tile write-back port), i.e. a 2-write-port memory that no single-port macro can implement.
  * `silicaflux.zip::silicaflux/rtl/memory_controller.sv:87` `sram[wb_addr[($clog2(SRAM_DEPTH)+1):2]] <= wb_data;`
  * `silicaflux.zip::silicaflux/rtl/memory_controller.sv:129` `sram[word_addr] <= req_wdata;`
  * `silicaflux.zip::silicaflux/rtl/fetch_unit.sv:45` `logic [XLEN-1:0] imem [0:IMEM_DEPTH-1];`
  * MemoryFlow: sf_sram_1rw / sf_sram_bank
* **Gen-2.5 bank arrays inside memory_controller** [Gen-2.5] - `IMPLEMENTED` (elaborates). Per-bank `mem_q` arrays inferred inside the controller with byte enables; no wrapper, no foundry-macro abstraction, no MBIST port.
  * `memory_controller.sf:980` `sf_vword_t  mem_q [BANK_DEPTH];`
  * MemoryFlow: sf_sram_1rw IMPL=0|1 + sf_macro_1rw_leaf
* **sf_sram_bank_decode helper** [Gen-2.5] - `STANDALONE` (elaborates). Bank/row/offset decoder in sram-decoder.sf; instantiated by nothing.
  * `SilicaFlux2.0/SilicaFlux2.5/sram-decoder.sf:2` `module sf_sram_bank_decode #(`
* **sfx_sram_interface (SilicaFlux-AI)** [SilicaFlux-AI] - `STANDALONE` (elaborates). Single-port, byte-strobed, 1-cycle synchronous SRAM wrapper used by the GEMM engine.
  * `SilicaFlux2.0/silicafluxai.zip::silicaflux-ai/rtl/memory/sfx_sram_interface.sv:5` `// Single-port synchronous SRAM wrapper: one address bus shared between read`
* **TestCore behavioural SRAM model** [SilicaFlux-DFT] - `BEHAVIOURAL` (not elaborated). tc_sram_model is a testbench model for the MBIST collar.
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip::silicaflux-testcore/tb/models/tc_sram_model.sv:21` `module tc_sram_model #(`

### DMA engine

* **Gen-1 DFLOAD / DFSTORE bursts** [Gen-1] - `IMPLEMENTED` (elaborates). ISA-level burst ops served by the tile memory controller. The burst address never advances and the buffer index wraps at 4, so bursts > 4 words re-read / re-write the same 4 words (reproduced by tb_sf1_memctrl).
  * `silicaflux.zip::silicaflux/rtl/silicaflux_pkg.sv:50` `parameter logic [4:0] OP_DFLOAD   = 5'h0A; // Stream burst from SRAM to tile`
  * `silicaflux.zip::silicaflux/rtl/memory_controller.sv:195` `2'd3: burst_rd_buf[ 96 +: XLEN] <= sram[burst_addr + 3];`
  * MemoryFlow: sf_dma
* **Gen-2.5 burst descriptor port** [Gen-2.5] - `IMPLEMENTED` (elaborates). memory_controller.sf exposes a burst port ('the DMA port'): one descriptor in flight, a done handshake per burst, <= 256 beats, no page crossing. There is no DMA engine behind it.
  * `memory_controller.sf:83` `//  * DMA attachment    : the burst descriptor/data channels are the DMA port.`
  * `memory_controller.sf:738` `assign burst_req_ready_o = init_done_q & (b_state_q == BST_IDLE);`
  * MemoryFlow: sf_dma (+ sf_mc25_vport_bridge)
* **Cluster DMA bridge (sf_dma_bridge)** [Gen-2.5] - `REFERENCED_ONLY` (not elaborated). IO-coherent DMA ingress in silicaflux_top.sf; undefined.
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1214` ``
* **sfx_dma (SilicaFlux-AI)** [SilicaFlux-AI] - `STANDALONE` (elaborates). Single-channel word-copy engine, one command in flight, FIFO-decoupled; no registers, IRQ, 2-D or error handling.
  * `SilicaFlux2.0/silicafluxai.zip::silicaflux-ai/rtl/dma/sfx_dma.sv:36` `// handshakes (see docs/MEMORY_PROTOCOL.md). Only one command may be in`

### Interconnect / router

* **Gen-1 2x2 XY mesh NoC** [Gen-1] - `IMPLEMENTED` (elaborates). 32-bit single-flit packets, XY routing, 4 tiles.
  * `silicaflux.zip::silicaflux/rtl/silicaflux_pkg.sv:28` `parameter int NOC_WIDTH     = 32;   // NoC flit data width`
  * `silicaflux.zip::silicaflux/rtl/noc_router.sv:8` `module noc_router`
* **Gen-2.5 parametric wormhole mesh router** [Gen-2.5] - `NOT_ELABORABLE` (does NOT elaborate). noc_interconnect.sf: 5-port XY wormhole router, MESH_X x MESH_Y, BUF_DEPTH-deep input buffers. Its packet type defaults to silicaflux_pkg::noc_packet_t, which no package in the repository defines.
  * `SilicaFlux2.0/SilicaFlux2.5/noc_interconnect.sf:84` `parameter int unsigned  MESH_X               = 2,`
  * `SilicaFlux2.0/SilicaFlux2.5/noc_interconnect.sf:83` `parameter type          pkt_t                = noc_packet_t,`
  * first elaboration error: `%Error: /home/user/Aureom.AI/SilicaFlux-main/silicaflux-memoryflow/build/sf_src/sf25/loose/SilicaFlux2.0/SilicaFlux2.5/noc_interconnect.sf:83:50: syntax error, `
* **Tile-local crossbar (compute_tile.sf)** [Gen-2.5] - `NOT_ELABORABLE` (does NOT elaborate). Per-target arbiters with write-burst lock and starvation counters, embedded in the tile.
  * `SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:157` `parameter int unsigned XB_STARVE_LIM  = 16,`
  * first elaboration error: `%Error: /home/user/Aureom.AI/SilicaFlux-main/silicaflux-memoryflow/build/sf_src/sf25/loose/SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:307:5: syntax error, unex`
* **Coherent / memory fabric (sf_coh_xbar, sf_mem_fabric)** [Gen-2.5] - `REFERENCED_ONLY` (not elaborated). Cluster-level fabrics instantiated in silicaflux_top.sf; undefined.
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1388` ``
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1493` ``
  * MemoryFlow: sf_mem_router

### Vector register file

* **Gen-1 register bank (16 x 128 b)** [Gen-1] - `IMPLEMENTED` (elaborates). 32 x 32 b scalar + 16 x 128 b vector registers.
  * `silicaflux.zip::silicaflux/rtl/register_bank.sv:52` `logic [VLEN-1:0] vregs [0:NUM_VREGS-1];`
* **Gen-2.5 register bank (16 x 128 b, 3R/1W)** [Gen-2.5] - `IMPLEMENTED` (elaborates). Lane-masked VRF with 3 read and 1 write port. One write port bounds tensor results (512 b per 4x4 product) to one product per 4 cycles if they are written back to the VRF.
  * `SilicaFlux2.0/SilicaFlux2.5/register_bank.sf:49` `parameter  int unsigned VRF_ENTRIES        = 16,`
  * `SilicaFlux2.0/SilicaFlux2.5/register_bank.sf:53` `parameter  int unsigned VRF_WR_PORTS       = 1,`
  * `SilicaFlux2.0/SilicaFlux2.5/register_bank.sf:52` `parameter  int unsigned VRF_RD_PORTS       = 3,`

### Tensor accumulation buffer

* **Gen-1 tensor unit (sequential 4x4)** [Gen-1] - `IMPLEMENTED` (elaborates). One 32-bit MAC per cycle, 64 MACs in ~66 cycles; results held in output registers, no accumulation across operations.
  * `silicaflux.zip::silicaflux/rtl/tensor_unit.sv:7` `// Latency: 64 MAC cycles + 2 state cycles = ~66 cycles.`
  * MemoryFlow: sf_tensor_array
* **Gen-2.5 pipelined tensor unit (4x4x4 INT8 / cycle)** [Gen-2.5] - `IMPLEMENTED` (elaborates). 64 MAC/cycle claimed, 21-cycle latency; output-stationary within one product only. The fused-accumulate input (VEC_FUSE_EN) is reserved and $fatal if set: there is no accumulation buffer.
  * `tensor_unit.sf:40` `//  Sustained throughput: one DIMxDIM matrix product per cycle.`
  * `tensor_unit.sf:56` `parameter bit          VEC_FUSE_EN    = 1'b0   // vector-tensor fused accumulate input`
  * `tensor_unit.sf:249` `$fatal(1, "tensor_unit: reserved extension parameter set");`
  * MemoryFlow: sf_tensor_array (double-buffered accumulators)
* **Memory-fetching tensor engine (cmd: a/b/c_addr, k_m1, acc)** [Gen-2.5] - `NOT_ELABORABLE` (does NOT elaborate). compute_tile.sf drives a tensor engine that fetches operands and accumulates C in the SPM; the in-repo tensor_unit has register operands only (interface drift).
  * `SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:1442` `cmd.k_m1   = timm.k_m1;`
  * `SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:1443` `cmd.acc    = timm.acc;`
  * first elaboration error: `%Error: /home/user/Aureom.AI/SilicaFlux-main/silicaflux-memoryflow/build/sf_src/sf25/loose/SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:307:5: syntax error, unex`
* **sfx_accumulator + systolic GEMM (SilicaFlux-AI)** [SilicaFlux-AI] - `STANDALONE` (elaborates). Addressable read-modify-write accumulator (32 entries) behind a weight-stationary array; tiles run strictly sequentially (no overlap).
  * `SilicaFlux2.0/silicafluxai.zip::silicaflux-ai/rtl/arithmetic/sfx_accumulator.sv:36` `module sfx_accumulator #(`
* **Cluster tensor engine (sf_tensor_engine)** [Gen-2.5] - `REFERENCED_ONLY` (not elaborated). Instantiated in silicaflux_top.sf; undefined.
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1160` ``

### Memory controller

* **On-chip SPM controllers (Gen-1, Gen-2.5)** [Gen-1/2.5] - `IMPLEMENTED` (elaborates). Both `memory_controller` modules are scratchpad controllers, not DRAM controllers.
  * `memory_controller.sf:7` `//  Unified banked scratchpad memory controller.`
* **SDRAM-style controller FSM (memory_cache_repo)** [library] - `STANDALONE` (elaboration inconclusive). ACTIVATE/CAS/PRECHARGE/REFRESH FSM for teaching; single outstanding request, no PHY.
  * `memory_cache_repo.zip::memory_cache_repo/rtl/memory_controller.sv:2` `//  memory_controller.sv  ·  DRAM-Style Memory Controller FSM`
  * note: elaboration inconclusive: Verilator and Icarus both stop on legal SV they do not support (## range cycle delay range expression; ## (in sequence expression))
* **SilicaFlux DDR / LPDDR controller** [all] - `ABSENT` (not elaborated). No DRAM controller exists for any SilicaFlux generation.
  * MemoryFlow: DDR4/LPDDR4 controller IP behind an SF-MEM -> AXI4 bridge (proposed)

### External memory interface

* **Cluster AXI memory ports (2 x AXI master)** [Gen-2.5] - `REFERENCED_ONLY` (not elaborated). silicaflux_top.sf declares NUM_MEM_PORTS AXI masters behind sf_mem_fabric / sf_axi_edge, neither of which exists.
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:36` `parameter int unsigned NUM_MEM_PORTS          = 2,`
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:93` `output sf_axi_req_t [NUM_MEM_PORTS-1:0]         mem_axi_req_o,`
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1517` ``
  * doc: *SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf* p.1: "we suggest no external DRAM"
* **Gen-1 chiplet tile interface** [Gen-1] - `IMPLEMENTED` (elaborates). Serialises 32-bit NoC flits over an 8/16/32-bit link (die-to-die, not a DRAM interface).
  * `silicaflux.zip::silicaflux/rtl/tile_interface.sv:6` `// deployments. Serialises 32-bit NoC flits over a narrow parallel link`
* **DDR / LPDDR / HBM PHY** [all] - `ABSENT` (not elaborated). No PHY or PHY model in the repository.
  * MemoryFlow: sf_extmem_model (behavioural, latency/bandwidth) + PHY presets in models.hardware

### ECC / parity

* **Gen-2.5 per-byte parity** [Gen-2.5] - `IMPLEMENTED` (elaborates). Detection only; exceptions SF_MEM_EXC_ECC on load. No correction, no injection hook.
  * `memory_controller.sf:116` `parameter logic        PARITY_EN         = 1'b1,`
  * MemoryFlow: sf_ecc_secded_enc/dec + sf_sram_bank (SECDED, scrub on RMW, injection)
* **Gen-1 link parity placeholder** [Gen-1] - `IMPLEMENTED` (not elaborated). Flag-only parity on chiplet beats; SPM has no protection.
  * `silicaflux.zip::silicaflux/rtl/tile_interface.sv:18` `//   - ECC placeholder (parity bit on each beat, not correcting — flag only)`

### MBIST

* **TestCore MBIST controller + collar** [SilicaFlux-DFT] - `STANDALONE` (elaborates). March-style MBIST with a collar for a generic SRAM; not connected to any SilicaFlux SPM.
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip::silicaflux-testcore/rtl/tc_mbist.sv:45` `module tc_mbist`
  * `SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip::silicaflux-testcore/rtl/tc_mbist_collar.sv:21` `module tc_mbist_collar #(`
  * doc: *SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf* p.9: "For each SRAM macro, include a built-in self-test (BIST)"
  * MemoryFlow: sf_mbist_march (parallel banks, wired into sf_spm_banked)

## Automatic consistency findings (SilicaFlux core sets)

| Kind | Module | Location | Detail |
|---|---|---|---|
| INTERFACE_DRIFT | `compute_tile` | `SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:1333` | instance u_alu of `alu` (SilicaFlux2.0/SilicaFlux2.5/silicaflux_alu.zip::silicaflux/rtl/alu.sf:47): 8/11 named ports and 1/1 parameters absent on the definition (e.g. br_res_i, req_valid_i, req_i, req_ready_o) |
| INTERFACE_DRIFT | `compute_tile` | `SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:1385` | instance u_vector_engine of `vector_engine` (vector_engine (1).sf:85): 13/17 named ports and 0/1 parameters absent on the definition (e.g. br_res_i, req_valid_i, req_i, req_ready_o) |
| INTERFACE_DRIFT | `compute_tile` | `SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:1448` | instance u_tensor_unit of `tensor_unit` (tensor_unit.sf:43): 13/17 named ports and 1/1 parameters absent on the definition (e.g. br_res_i, cmd_valid_i, cmd_i, cmd_ready_o) |
| INTERFACE_DRIFT | `compute_tile` | `SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:1953` | instance u_memory_controller of `memory_controller` (memory_controller.sf:94): 7/9 named ports and 2/2 parameters absent on the definition (e.g. req_valid_i, req_i, req_ready_o, rsp_valid_o) |
| INTERFACE_DRIFT | `tc_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip::silicaflux-testcore/rtl/tc_top.sv:155` | instance u_tap of `tc_tap` (SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip::silicaflux-testcore/rtl/tc_tap.sv:25): 18/18 named ports and 0/0 parameters absent on the definition (e.g. tck, trst_n, tms, tdi) |
| INTERFACE_DRIFT | `tc_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip::silicaflux-testcore/rtl/tc_top.sv:176` | instance u_mode of `tc_mode_ctrl` (SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip::silicaflux-testcore/rtl/tc_mode_ctrl.sv:32): 30/30 named ports and 0/0 parameters absent on the definition (e.g. tck, tap_rst_n, por_n, tap_state) |
| INTERFACE_DRIFT | `tc_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip::silicaflux-testcore/rtl/tc_top.sv:269` | instance u_bridge of `tc_reg_bridge` (SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip::silicaflux-testcore/rtl/tc_reg_bridge.sv:29): 16/16 named ports and 0/0 parameters absent on the definition (e.g. tck, por_n, tap_state, sel) |
| INTERFACE_DRIFT | `tb_tap_fsm` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip::silicaflux-testcore/tb/tb_tap_fsm.sv:23` | instance dut of `tc_tap` (SilicaFlux2.0/SilicaFlux2.5/silicaflux-testcore.zip::silicaflux-testcore/rtl/tc_tap.sv:25): 18/18 named ports and 0/0 parameters absent on the definition (e.g. tck, trst_n, tms, tdi) |
| INTERFACE_DRIFT | `sf_compute_tile_pipe` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip::silicaflux-timinglab/rtl/opt/sf_compute_tile_pipe.sv:93` | instance u_mem of `memory_controller` (memory_cache_repo.zip::memory_cache_repo/rtl/memory_controller.sv:31): 8/16 named ports and 0/0 parameters absent on the definition (e.g. req_opcode, req_vwdata, req_length, resp_vrdata) |
| INTERFACE_DRIFT | `sf_compute_tile_pipe` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip::silicaflux-timinglab/rtl/opt/sf_compute_tile_pipe.sv:148` | instance u_tensor of `sf_tensor_unit_pipe` (SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip::silicaflux-timinglab/rtl/opt/sf_tensor_unit_pipe.sv:29): 17/17 named ports and 0/0 parameters absent on the definition (e.g. clk, rst_n, start, mat_a_row0) |
| INTERFACE_DRIFT | `compute_tile` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip::silicaflux-timinglab/upstream/silicaflux/rtl/compute_tile.sv:88` | instance u_mem of `memory_controller` (memory_cache_repo.zip::memory_cache_repo/rtl/memory_controller.sv:31): 8/16 named ports and 0/0 parameters absent on the definition (e.g. req_opcode, req_vwdata, req_length, resp_vrdata) |
| INTERFACE_DRIFT | `compute_tile` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip::silicaflux-timinglab/upstream/silicaflux/rtl/compute_tile.sv:143` | instance u_tensor of `tensor_unit` (silicaflux.zip::silicaflux/rtl/tensor_unit.sv:16): 17/17 named ports and 0/0 parameters absent on the definition (e.g. clk, rst_n, start, mat_a_row0) |
| INTERFACE_DRIFT | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip::silicaflux-timinglab/upstream/silicaflux/rtl/silicaflux_top.sv:157` | instance u_fetch of `fetch_unit` (silicaflux.zip::silicaflux/rtl/fetch_unit.sv:18): 10/10 named ports and 0/0 parameters absent on the definition (e.g. clk, rst_n, stall, flush) |
| INTERFACE_DRIFT | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip::silicaflux-timinglab/upstream/silicaflux/rtl/silicaflux_top.sv:190` | instance u_regs of `register_bank` (silicaflux.zip::silicaflux/rtl/register_bank.sv:19): 16/16 named ports and 0/0 parameters absent on the definition (e.g. clk, rst_n, s_rd_addr1, s_rd_addr2) |
| INTERFACE_DRIFT | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip::silicaflux-timinglab/upstream/silicaflux/rtl/silicaflux_top.sv:212` | instance u_dec of `decoder` (silicaflux.zip::silicaflux/rtl/decoder.sv:20): 14/14 named ports and 0/0 parameters absent on the definition (e.g. clk, rst_n, stall, flush) |
| INTERFACE_DRIFT | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip::silicaflux-timinglab/upstream/silicaflux/rtl/silicaflux_top.sv:233` | instance u_ctrl_mem of `memory_controller` (memory_cache_repo.zip::memory_cache_repo/rtl/memory_controller.sv:31): 8/16 named ports and 0/0 parameters absent on the definition (e.g. req_opcode, req_vwdata, req_length, resp_vrdata) |
| INTERFACE_DRIFT | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip::silicaflux-timinglab/upstream/silicaflux/rtl/silicaflux_top.sv:252` | instance u_ctrl of `control_core` (silicaflux.zip::silicaflux/rtl/control_core.sv:19): 28/28 named ports and 0/0 parameters absent on the definition (e.g. clk, rst_n, id_is, id_stall) |
| INTERFACE_DRIFT | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux-timinglab.zip::silicaflux-timinglab/upstream/silicaflux/rtl/silicaflux_top.sv:302` | instance u_sched of `scheduler` (silicaflux.zip::silicaflux/rtl/scheduler.sv:17): 35/35 named ports and 0/0 parameters absent on the definition (e.g. clk, rst_n, instr_in, instr_valid) |
| INTERFACE_DRIFT | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:238` | instance u_rst_sync_por of `sf_rst_sync` (silicaflux-powerlink.zip::silicaflux-powerlink/rtl/sf_sync.sv:35): 4/4 named ports and 0/0 parameters absent on the definition (e.g. clk_i, rst_ni, scan_mode_i, rst_no) |
| INTERFACE_DRIFT | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:579` | instance u_memedge_rst_sync of `sf_rst_sync` (silicaflux-powerlink.zip::silicaflux-powerlink/rtl/sf_sync.sv:35): 5/5 named ports and 0/1 parameters absent on the definition (e.g. clk_i, rst_ni, test_mode_i, test_rst_ni) |
| INTERFACE_DRIFT | `tb_compute_tile` | `SilicaFlux2.0/SilicaFlux2.5/tb_compute_tile.sf:3691` | instance u_dut of `compute_tile` (silicaflux.zip::silicaflux/rtl/compute_tile.sv:24): 35/37 named ports and 6/7 parameters absent on the definition (e.g. stall_i, flush_i, issue_valid_i, issue_ready_o) |
| INTERFACE_DRIFT | `tb_memory_controller` | `SilicaFlux2.0/SilicaFlux2.5/tb_memory_controller.sf:1251` | instance dut of `memory_controller` (memory_controller.sf:94): 45/47 named ports and 4/4 parameters absent on the definition (e.g. s_req_valid_i, s_req_ready_o, s_req_we_i, s_req_addr_i) |
| INTERFACE_DRIFT | `tb_noc_interconnect` | `SilicaFlux2.0/SilicaFlux2.5/tb_noc_interconnect.sf:2853` | instance u_dut of `noc_interconnect` (SilicaFlux2.0/SilicaFlux2.5/noc_interconnect.sf:811): 9/11 named ports and 4/6 parameters absent on the definition (e.g. inj_valid_i, inj_ready_o, inj_flit_i, ej_valid_o) |
| INTERFACE_DRIFT | `tb_scheduler` | `SilicaFlux2.0/SilicaFlux2.5/tb_scheduler.sf:3436` | instance u_dut of `scheduler` (SilicaFlux2.0/SilicaFlux2.5/scheduler.sf:62): 22/28 named ports and 9/9 parameters absent on the definition (e.g. disp_id_i, disp_opcode_i, disp_src_valid_i, disp_src_tag_i) |
| INTERFACE_DRIFT | `tb_silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/tb_silicaflux_top.sf:3514` | instance u_dut of `silicaflux_top` (SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl.zip::silicaflux/rtl/silicaflux_top.sf:36): 56/57 named ports and 5/5 parameters absent on the definition (e.g. rst_ni, run_i, stall_i, halted_o) |
| INTERFACE_DRIFT | `tb_vector_engine` | `SilicaFlux2.0/SilicaFlux2.5/tb_vector_engine.sf:588` | instance u_dut of `vector_engine` (silicaflux.zip::silicaflux/rtl/vector_engine.sv:27): 8/10 named ports and 3/4 parameters absent on the definition (e.g. in_valid, in_ready, in_op, in_a) |
| INTERFACE_DRIFT | `tb_memory_controller` | `silicaflux.zip::silicaflux/tb/tb_memory_controller.sv:32` | instance dut of `memory_controller` (memory_cache_repo.zip::memory_cache_repo/rtl/memory_controller.sv:31): 8/16 named ports and 0/0 parameters absent on the definition (e.g. req_opcode, req_vwdata, req_length, resp_vrdata) |
| INTERFACE_DRIFT | `tb_scheduler` | `silicaflux.zip::silicaflux/tb/tb_scheduler.sv:23` | instance dut of `scheduler` (silicaflux.zip::silicaflux/rtl/scheduler.sv:17): 35/35 named ports and 0/0 parameters absent on the definition (e.g. clk, rst_n, instr_in, instr_valid) |
| INTERFACE_DRIFT | `tb_tensor_unit` | `silicaflux.zip::silicaflux/tb/tb_tensor_unit.sv:11` | instance dut of `tensor_unit` (silicaflux.zip::silicaflux/rtl/tensor_unit.sv:16): 17/17 named ports and 0/0 parameters absent on the definition (e.g. clk, rst_n, start, mat_a_row0) |
| INTERFACE_DRIFT | `tb_tensor_unit` | `tb_tensor_unit.sf:849` | instance u_dut of `tensor_unit` (silicaflux.zip::silicaflux/rtl/tensor_unit.sv:16): 5/5 named ports and 4/4 parameters absent on the definition (e.g. clk, rst_n, in_valid, in_b) |
| MISSING_TYPES | `compute_tile` | `SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf:142` | 29 of 30 package types used are defined by no package in set `sf25` (e.g. sf_alu_req_t, sf_alu_rsp_t, sf_br_mask_t, sf_br_res_t) |
| MISSING_TYPES | `noc_router` | `SilicaFlux2.0/SilicaFlux2.5/noc_interconnect.sf:80` | 1 of 1 package types used are defined by no package in set `sf25` (e.g. noc_packet_t) |
| MISSING_TYPES | `noc_interconnect` | `SilicaFlux2.0/SilicaFlux2.5/noc_interconnect.sf:811` | 1 of 1 package types used are defined by no package in set `sf25` (e.g. noc_packet_t) |
| MISSING_TYPES | `scheduler` | `SilicaFlux2.0/SilicaFlux2.5/scheduler.sf:62` | 10 of 11 package types used are defined by no package in set `sf25` (e.g. sf_barrier_meta_t, sf_br_mask_t, sf_br_res_t, sf_cmpl_t) |
| MISSING_TYPES | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:29` | 32 of 32 package types used are defined by no package in set `sf25` (e.g. sf_apb_req_t, sf_apb_rsp_t, sf_axi_req_t, sf_axi_rsp_t) |
| MISSING_TYPES | `tile_interface` | `SilicaFlux2.0/SilicaFlux2.5/tile_interface.sf:156` | 11 of 11 package types used are defined by no package in set `sf25` (e.g. sf_exec_pkt_t, sf_mem_req_t, sf_mem_rsp_t, sf_noc_flit_t) |
| MISSING_TYPES | `vector_engine` | `vector_engine (1).sf:85` | 3 of 3 package types used are defined by no package in set `sf25` (e.g. sf_uop_tag_t, sf_vex_ctrl_t, sf_vop_e) |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:245` | instance u_sync_sys_rst of `sf_sync`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:252` | instance u_sync_rtc of `sf_sync`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:259` | instance u_sync_ext_irq of `sf_sync`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:532` | instance u_core_icg of `sf_icg`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:549` | instance u_core of `sf_core_complex`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:607` | instance u_dma_bridge of `sf_dma_bridge`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:747` | instance u_rsp_q of `sf_fifo`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:936` | instance u_req_q of `sf_fifo`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:948` | instance u_srsp_q of `sf_fifo`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:963` | instance u_llc_bank of `sf_llc_bank`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:1055` | instance u_mem_edge of `sf_axi_mem_edge`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:1321` | instance u_irq_ctrl of `sf_irq_ctrl`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:1339` | instance u_debug of `sf_debug_module`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:1394` | instance u_trace_q of `sf_fifo`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_rtl2.zip::silicaflux/rtl/silicaflux_top.sf:1437` | instance u_perf_mon of `sf_perf_monitor`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:542` | instance u_rst_ctrl of `sf_rst_ctrl`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:589` | instance u_memedge_ack_sync of `sf_sync`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:618` | instance u_clk_ctrl of `sf_clk_ctrl`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:638` | instance u_ext_irq_sync of `sf_sync`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:648` | instance u_ctrl_in_sync of `sf_sync`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:834` | instance u_pwr_ctrl of `sf_pwr_ctrl`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:889` | instance u_core of `sf_core`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:967` | instance u_l2 of `sf_l2_cache`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1008` | instance u_snp_slice of `sf_reg_slice`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1032` | instance u_sched of `sf_sched_domain`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1061` | instance u_vpu of `sf_vector_unit`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1095` | instance u_tlb_subsys of `sf_tlb_subsys`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1140` | instance u_dispatch of `sf_dispatch_fabric`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1161` | instance u_tensor of `sf_tensor_engine`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1201` | instance u_dma_cdc of `sf_axi_cdc`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1215` | instance u_dma_bridge of `sf_dma_bridge`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1238` | instance u_dbg of `sf_dbg_module`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1319` | instance u_req_slice of `sf_reg_slice`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1333` | instance u_rsp_slice of `sf_reg_slice`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1389` | instance u_coh_xbar of `sf_coh_xbar`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1419` | instance u_llc_bank of `sf_llc_bank`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1461` | instance u_coh_mgr of `sf_coh_mgr`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1494` | instance u_mem_fabric of `sf_mem_fabric`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1518` | instance u_axi_edge of `sf_axi_edge`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1538` | instance u_mem_cdc of `sf_axi_cdc`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1557` | instance u_host_apb_cdc of `sf_apb_cdc`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1670` | instance u_csr of `sf_cluster_csr`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1691` | instance u_irq_ctrl of `sf_irq_ctrl`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1713` | instance u_trace of `sf_trace_agg`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1765` | instance u_pmu of `sf_pmu`: no definition in repository |
| REFERENCED_ONLY | `silicaflux_top` | `SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf:1830` | instance u_fault_ctrl of `sf_fault_ctrl`: no definition in repository |
| VARIANTS | `sf_alu` | `alu.sf:16` | 2 diverging definitions: alu.sf:16 (659 lines); SilicaFlux2.0/SilicaFlux2.5/alu (1).sf:213 (450 lines) |

## Source sets

| Key | Title | Generation | HDL files | SilicaFlux core |
|---|---|---|---|---|
| sf1 | SilicaFlux v1 cluster (silicaflux.zip) | Gen-1 | 23 | yes |
| sf25 | SilicaFlux 2.x unit sources (loose .sf files) | Gen-2.5 | 33 | yes |
| sf2_rtl | SilicaFlux 2.x top/front-end archives | Gen-2.5 | 8 | yes |
| sfx_ai | SilicaFlux-AI GEMM engine (silicafluxai.zip) | SilicaFlux-AI | 30 | yes |
| sf_ml | SilicaFlux-ML learning controller | SilicaFlux-ML | 13 | yes |
| testcore | SilicaFlux TestCore DFT (MBIST/LBIST/TAP) | SilicaFlux-DFT | 32 | yes |
| timinglab | SilicaFlux TimingLab pipelined drop-ins | Gen-1 (optimised) | 35 | yes |
| memcache | Generic cache / RAM / SDRAM-FSM library | library | 15 | no |
| soc | SoC integration example | library | 14 | no |
| cpu | CPU cores (cpu_core, RISC-V, pipelined) | library | 37 | no |
| powerlink | PowerLink support RTL | support | 6 | no |
