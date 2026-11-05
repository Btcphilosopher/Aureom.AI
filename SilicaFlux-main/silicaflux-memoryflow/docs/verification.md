# Verification

## Testbenches (Verilator 5.020, `--timing --assert`)

| Name | Top | What it proves |
|---|---|---|
| ecc | tb_ecc | SECDED K=32/64 encoder is bit-identical to the Python golden model; every single-bit flip at every codeword position is corrected; every double-bit pair on 24 words per width is detected (≈108 k checks) |
| sram_prims | tb_sram_prims | `IMPL=0` (inferred) and `IMPL=1` (3×4 macro grid) give identical read data under 20 k random ops; 1R1W read-first; 2RW concurrent traffic |
| bank_secded / bank_parity / bank_noecc_macro | tb_sram_bank | random R/W with byte strobes vs a reference; exact 2-cycle latency; read-after-RMW hazard; injection → corrected / uncorrectable; RMW onto a 1-bit error scrubs it; RMW onto a 2-bit error is suppressed; MBIST raw port |
| spm_mod / spm_xor / spm_block_8b / spm_rsp2 | tb_spm | 3-port random traffic with per-port scoreboards, random response backpressure, address-overflow requests, deadlock watchdog; hot-bank fairness; stride sweep; throughput metrics |
| mbist_clean / mbist_fault | tb_mbist | March C- passes on clean banks (solid and checkerboard backgrounds); a stuck-at-1 cell is detected with the correct bank and first failing address |
| router | tb_router | in-order responses across slaves with 2 vs 25-cycle latency; decode errors for holes and the top of the address space |
| dma | tb_dma | ID/CAPS/reset, byte-granular 1-D copies with tail strobes, EXT↔SPM, 2-D tiles, every validation error, read/write bus errors, SPM-boundary crossing, abort, MEM→stream and stream→MEM with backpressure, four concurrent channels, burst sweep, IRQ set/clear, register lock |
| accel | tb_accel | tensor tiles vs Python golden (K=1, 8, 37) under random gaps/backpressure; double-buffer timing; vector ADD/MUL/AXPY/DOT; reuse-buffer replay and ping-pong overlap |
| system | tb_system | full subsystem: GEMM 16×8×32 with B reuse vs golden; vector ADD/AXPY/DOT vs golden; EXT prefetch; ECC injection and MBIST via registers; IRQ |
| param_recommended / param_reference | tb_param_smoke | the same system smoke test at the recommended (128-bit, 16×16, 8 banks XOR, FIFO 64) and reference parameterisations |
| deadlock_fifo4 (expect DEADLOCK) / deadlock_fifo16 | tb_deadlock | joined-stream deadlock is real and is detected by the watchdog; it disappears when FIFO depth ≥ burst |

**Mutation testing** (`memoryflow.verify.rtl_runner.MUTANTS`, `tests/test_rtl.py`): each test
copies the RTL, injects one bug (RMW merging raw instead of corrected data, SPM overflow
off-by-one, DMA tail strobe stuck at all-ones, ECC ignoring overall parity) and requires the
matching testbench to **fail**. A mutant that doesn't build counts as an error, not a kill.
Final result: 4/4 mutants killed (bank_secded 1 error, spm_mod 32, dma 8, ecc 64 688). The SPM
mutant survived on the first attempt; see bug 9.

**Synthesis**: `memoryflow synth` runs Yosys `synth -flatten` on seven wrappers. Foundry macros
are blackboxes read with `-lib`, and each instance carries `(* keep *)`.

## Bugs and issues found by testing

| # | Found by | Issue | Resolution |
|---|---|---|---|
| 1 | tb_system hang | **DMA self-deadlock.** With one shared engine, an accelerator→SRAM channel (stream source) held the read side waiting for results. Those results needed operand bursts that were queued behind it on the same engine. | `sf_dma` split into two `sf_dma_engine`s (MM2S/MEM2MEM and S2MM) sharing one channel table and an RR write arbiter. tb_dma regression re-run: 4-channel concurrent copy went from 810 to 674 cycles |
| 2 | tb_deadlock | **Joined-stream deadlock.** A 4-deep vector FIFO with 16-beat bursts stalls after exactly 4 beats | Architectural rule plus the Python predicate `joined_stream_deadlock()`. Operand FIFOs are sized ≥ burst at the top level |
| 3 | Yosys stat (implausibly few cells) | Parameterised macro blackboxes were optimised away by `synth`, along with all the SPM logic behind them | `(* keep *)` on macro instances, blackbox read with `read_verilog -lib` |
| 4 | tb_dma skew experiment | **Bank-conflict resonance.** Bank-aligned SPM→SPM copies run at 0.80 beat/cycle and skewed ones at 0.92 | Documented. XOR interleave or buffer skew fixes it. The DMA cycle model misses the aligned case (model limitation, see below) |
| 5 | tb_dma (first run) | A 2-D overflow test vector stayed inside 2³². The DMA was right to accept it and later fault on the hole | Test corrected. It now checks that a product above 32 bits **is** caught and that a large legal footprint is not |
| 6 | Verilator 5.020 | Unpacked arrays of queues mis-sized (`'{3,4,0}` for `'{3,1,0}`). Concurrent automatic tasks driving bits of one shared signal gave non-reproducible stimulus | TB rule: ring buffers instead of queue arrays, and exactly one process drives each DUT input (`tb_accel` and `tb_system` follow it; `tb_spm` results were cross-checked by the Python model to <1 %) |
| 7 | lint at recommended params | `sf_ctrl_regs` injection mask was only 96 bits, against a 137-bit stored word at DW=128 | Mask zero-extended through a generate branch |
| 8 | tb_param_smoke (reference run) | Smoke-test addresses were above a 32 KiB SPM | TB addresses fitted to the smallest configuration |
| 9 | **mutation testing** | The `spm_overflow_off_by_one` mutant (`>=` → `>` on the capacity check, which aliases address == CAPACITY onto word 0) **survived** the original tb_spm: random out-of-range addresses almost never landed exactly on the boundary | Directed boundary phase added to tb_spm: last valid word, first invalid byte, wrap-to-zero address, top of the 4 GiB space, then a check that word 0 is untouched. The mutant is now killed (32 errors) |
| 10 | the new boundary tests | The tb_spm scoreboard held addresses as signed `int`, so `0xFFFF_FFF8` read as −8 and was predicted in-range | Port task takes `logic [31:0]` with an unsigned compare |

## Model ↔ RTL calibration

| Model | Cases | Agreement |
|---|---|---|
| SPM banking cycle model (`banking.simulate_spm`) | 32 (4 RTL builds × 8 metrics) | max \|error\| < 1 % |
| DMA cycle model (`dma.simulate_dma_copy`) | EXT→SPM bursts 1–16, SPM→SPM bursts 1–4 and skewed 8/16 | < 0.5 % |
| DMA cycle model, bank-aligned SPM→SPM bursts 8/16 | 2 | −9 % / −14 % (it misses the conflict resonance) |
| Tensor tile model (`dataflow.tensor_tiles_cycles`) | K=8/32 × dbuf on/off | < 1.2 % |
| Deadlock predicate | FIFO 4 vs 16 at burst 16 | matches |

## v2: verification of the existing SilicaFlux RTL (`memoryflow sf-char`)

The DUT files are compiled byte-for-byte from the repository (`memoryflow.silicaflux.sources`
extracts them from the archives / loose `.sf` files with sha256 provenance); only the testbenches in
`tb/silicaflux/` are MemoryFlow's.

| Name | DUT (repository file) | Checks | What it proves / measures |
|---|---|---|---|
| sf25_memctrl | `memory_controller.sf` + `silicaflux_pkg (1).sf` | ~150 k | byte-accurate reference model on all three ports; 3-cycle load latency; ~1 req/cycle per port; burst-length sweep 1..256 (3 / 4 cycles overhead per store / load burst); bank contention (1.99 vs 1.00 req/cycle disjoint vs same bank); 3-port 29.9 B/cycle; random traffic with backpressure; range / domain / misalignment / page / aperture-overflow exceptions and that rejected stores write nothing; parity error detection via a corrupted bit; burst kill commits an exact beat count |
| sf25_tensor | `tensor_unit.sf` + `silicaflux_pkg.sf` | ~32 k | every result vs a golden model (wrap, saturate, element enables, overflow flags, tag order); 21-cycle latency; 63.4 MAC/cycle sustained; 15.9 MAC/cycle when results drain through one 128-bit port; flush kills in-flight work |
| sf1_memctrl (expect **DEFECT**) | `silicaflux.zip::silicaflux/rtl/memory_controller.sv` | ~300 | Gen-1 bandwidth (3 cycles/word, 2.29 B/cycle VLOAD); DFSTORE/DFLOAD of 8 words leave 4 words unwritten / re-read words 0..3; the write-back port and the FSM write the array in the same cycle |
| sf1_tensor | `silicaflux.zip::silicaflux/rtl/tensor_unit.sv` | ~3 k | golden results; 67 cycles per 4x4 product (0.94 MAC/cycle) |
| sf25_dma_bridge | `memory_controller.sf` + MemoryFlow `sf_dma`, `sf_mem_router`, `sf_mc25_vport_bridge` | ~4 k | byte-exact EXT→SPM→EXT and SPM→SPM round trips; the SilicaFlux controller's DOMAIN exceptions arrive at the DMA as RD/WR bus errors; a partial-lane write is poisoned and writes nothing; EXT→SPM 11.4, SPM→EXT 6.06 (write-ack bound), SPM→SPM 7.96 B/cycle |

`DEFECT` expectations make a future fix visible: if the Gen-1 burst defect is repaired, `sf1_memctrl`
reports PASS and the run is flagged until the expectation is updated.

## v2: issues found by testing

| # | Found by | Issue | Resolution |
|---|---|---|---|
| 11 | sf1_memctrl | **SilicaFlux Gen-1 DF bursts > 4 words are defective** (`burst_addr` never advances, buffer index wraps) and the tile SPM is written by two processes in one cycle | Reported (repository RTL is not modified); modelled as 4-word bursts in the Gen-1 baseline |
| 12 | sf-inventory | **SilicaFlux 2.5 integration drift**: compute_tile.sf instantiates memory_controller / tensor_unit with ports and parameters the in-repo modules lack; 29 of its 30 package types are undefined; tb_memory_controller.sf / tb_tensor_unit.sf target other interfaces; 26 of 27 module types in silicaflux_top.sf are undefined | Reported with origin:line evidence; units characterised individually |
| 13 | tb_sf25_memctrl first run | Every response showed tag 0 / RANGE: member-wise writes to a module-level packed struct from a suspended task did not propagate (Verilator 5.020, same family as bug 6) | Requests are built in a local variable and assigned as a whole struct |
| 14 | tb_sf25_memctrl review | A boundary check compared the reference model with itself (snapshot taken before a legal store to the same line) | Check removed; the scoreboard's data check on read-backs is the proof that rejected stores write nothing |
| 15 | tb_sf25_dma_bridge | The partial-lane test **passed vacuously**: the destination was exactly one byte past the SPM aperture, so the router, not the bridge, produced the error. Caught because the test also required the bridge's poison counter to move | Destination moved inside the aperture; read-back now proves the full beat landed and the poisoned beat wrote nothing |
| 16 | bridge design | The 2.5 vector port returns reads and writes in ONE in-order stream; a DMA that stops accepting read data until write acks return would deadlock behind it | `sf_mc25_vport_bridge` reserves response-FIFO credit before issuing and never back-pressures the controller (assertion on overflow) |
| 17 | tb_sf25_dma_bridge | The analytical DMA model had no write path: SPM→EXT ran at 6.06 vs 11.4 B/cycle EXT→SPM | `dma_write_bw` (Little's law on WOUT) added to the roofline; WOUT is an exploration dimension |
| 18 | sf-inventory | Elaboration "failures" of two library blocks were simulator limitations (Verilator BLKLOOPINIT, Icarus concurrent SVA), not design defects | Third outcome *inconclusive*; curated status kept, with the reason |
| 19 | Yosys 0.33 | The SilicaFlux packages (multi-dimensional packed typedefs) do not parse in the open flow the SilicaFlux update proposes | As-built logic area is ANALYTICAL (scaling laws); sv2v or a newer front end is needed for gate counts |

## v2: model ↔ RTL calibration against the existing SilicaFlux RTL

| Model | RTL measurement | Agreement |
|---|---|---|
| Burst-port efficiency `L/(L+3)` store, `L/(L+4)` load | tb_sf25_memctrl, L = 1..256 | exact at every L (the overhead is structural: descriptor, commit / read pipe, done handshake) |
| DMA write path `WOUT/(L+1)` | tb_sf25_dma_bridge SPM→EXT, WOUT 8, 20-cycle memory | 6.10 vs 6.06 B/cycle (+0.6 %) |
| DMA read path (outstanding / round trip) | tb_sf25_dma_bridge EXT→SPM, 16 outstanding | 12.2 vs 11.4 B/cycle (+7 %; router + bridge add ~1.4 cycles of round trip) |
| Tensor drain ceiling | tb_sf25_tensor, results accepted 1 cycle in 4 | 16 vs 15.9 MAC/cycle |
