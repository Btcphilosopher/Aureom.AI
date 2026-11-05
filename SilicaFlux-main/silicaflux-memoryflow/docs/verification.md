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
