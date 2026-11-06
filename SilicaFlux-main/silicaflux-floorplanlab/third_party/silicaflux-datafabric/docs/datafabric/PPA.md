# PPA experiments, architecture sweep and recommendation

## 0. What these numbers are (and are not)

* **Performance numbers are measured** in RTL simulation (Verilator): cycles from
  the START register write until software sees BUSY = 0, 4 KiB copies
  (`reports/datafabric/benchmark.md`), plus firmware measurements on the real CPU
  (`reports/datafabric/soc_logs/`).
* **Area numbers are technology-independent**: Yosys 0.33 generic synthesis to a
  2-input CMOS gate set (NAND/NOR/NOT + flops), reported as NAND2-equivalents
  (estimated transistors / 4), flip-flops and logic depth in gate levels
  (`reports/datafabric/synth.md`). They are good for *relative* comparisons between
  configurations. **No PDK or Liberty was available**: there are no node-specific
  area, timing, congestion or power numbers here, and none are claimed. The
  130/65/28 nm configuration points are prepared as templates (`synth/asic/`).
* Every synthesized configuration has **zero inferred latches**; the crossbar and
  both DMA engines were re-simulated at gate level with the same self-checking
  testbenches (`reports/datafabric/gls.md`).

## 1. Interconnect topology

| Configuration (32-bit, 7 slaves) | NAND2-eq | flops | logic depth | concurrent transfers | notes |
|---|---|---|---|---|---|
| direct bus (1 master) | 1,340 | 30 | 21 | 1 | no arbitration |
| shared bus 3 masters, RR | 2,050 | 45 | 52 | **1 in total** | no per-master access matrix |
| shared bus 4 masters, RR | 2,217 | 48 | 51 | 1 in total | |
| SilicaFlux-V `sfv_xbar` 3×7, fixed (release 1) | 4,646 | 27 | 19 | up to 3 | no response back-pressure |
| `sfb_crossbar` 3×7, fixed | 4,954 | 55 | 28 | up to 3 | +7 % vs sfv_xbar for back-pressure + alignment check |
| `sfb_crossbar` 3×7, RR | 5,632 | 69 | 35 | up to 3 | |
| `sfb_crossbar` 4×7, fixed | 6,520 | 64 | 28 | up to 4 | |
| **`sfb_crossbar` 4×7, RR (SilicaFlux-V + DMA)** | **7,340** | **78** | **34** | up to 4 | chosen |
| registered crossbar 4×7 (slices on all slave ports) | 9,136 | 1,534 | 34 | up to 4 | +1 cycle each way; depth unchanged: the critical path is master-side decode → arbitration → ready, not the slave wires |

Observations:

* The shared bus is ~3.3× smaller but serialises *all* masters (one transaction in
  flight in the whole fabric), its combinational path is the deepest (two
  arbitration/decode stages chained), and it cannot apply the per-master access
  matrix that SilicaFlux-V relies on (execute-never peripherals, DMA denied MMIO).
  With fixed priority it also starved a master in random traffic (benchmark
  fairness table: master 3 received 1 transaction in 20 k cycles).
* Round robin costs 12–14 % of the crossbar (6.5 k → 7.3 k at 4×7) and buys
  starvation freedom: sustained contention gives equal shares (2,501 / 2,501 /
  2,501 / 2,500, max wait 7 cycles) versus `[10000, 1, 1, 1]` with fixed priority.
* Register slices are not free (≈ +1.8 k NAND2-eq and +1,450 flops for 7 ports at
  32 bit) and do not shorten the measured critical path; keep them for physical
  needs (long wires to SRAM macros) found in place-and-route, not by default.

## 2. Master count and data width

| Crossbar ×7, RR | NAND2-eq | flops | depth |
|---|---|---|---|
| 2 masters | 2,987 | 46 | 24 |
| 3 masters | 5,632 | 69 | 35 |
| 4 masters | 7,340 | 78 | 34 |
| 5 masters | 9,928 | 101 | 46 |

| 4×7 RR crossbar | 32-bit | 64-bit | 128-bit |
|---|---|---|---|
| NAND2-eq | 7,340 | 11,526 | 19,765 |

Each extra master costs ~2–2.6 k NAND2-eq at 32 bit (muxes on every slave port,
one more arbiter input) and deepens the arbitration path. Doubling the width costs
+57 % / +169 % (the data muxes dominate). Widening is only useful if the SRAM and
the other masters are widened too; SilicaFlux-V's CPU, SRAM banks and peripherals
are 32-bit.

## 3. DMA configurations (measured cycles for 4 KiB, ideal conditions)

| DMA | NAND2-eq | flops | two-slave copy | same-slave copy | speed-up | Δ area | speed-up per +1 k NAND2-eq |
|---|---|---|---|---|---|---|---|
| **simple, 32-bit (default)** | **3,638** | 437 | **4,100** (1.00 B/cyc) | 4,100 | 1.00 | — | — |
| simple, 32-bit, no perf registers | 2,972 | 341 | 4,100 | 4,100 | 1.00 | −666 | — |
| simple, 64-bit | 3,610 | 473 | 2,052 | 2,052 | 2.00 | ≈0 (needs 64-bit fabric) | — |
| simple, 128-bit | 3,684 | 545 | 1,028 | 1,028 | 3.99 | ≈0 (needs 128-bit fabric) | — |
| buffered FIFO 2 / burst 2 | 7,664 | 764 | 4,099 | 4,099 | 1.00 | +4,026 | 0.00 |
| buffered FIFO 4 / burst 4 | 7,838 | 830 | 3,075 | 3,075 | 1.33 | +4,200 | 0.08 |
| buffered FIFO 8 / burst 1 | — | — | 6,147 | 6,147 | 0.67 | | negative |
| buffered FIFO 8 / burst 8 | 8,243 | 960 | 2,563 | 2,563 | 1.60 | +4,605 | 0.13 |
| buffered FIFO 16 / burst 16 | 9,040 | 1,218 | 2,307 | 2,307 | 1.78 | +5,402 | 0.14 |
| **buffered FIFO 8, dual port** | 7,926 | 962 | **1,031** (3.97 B/cyc) | 2,053 | **3.98** | +4,288 (+1 crossbar port ≈ +2.6 k) | 0.70 (0.43 incl. port) |
| buffered FIFO 8 / burst 8, 64-bit | 8,960 | 1,219 | 1,283 | 1,283 | 3.20 | +5,322 (+64-bit fabric) | 0.41 |

* The simple engine moves one word every 4 cycles (read handshake + response,
  write handshake + response; all outputs registered) — exactly as designed.
* A single-port buffered engine can at best approach 2 cycles/word (B/(2B+2)):
  phases must alternate on one port. FIFO depth beyond the burst length buys
  nothing; burst 1 is *slower* than the simple engine (phase-switch overhead).
* The dual-port engine reaches one word per cycle between two SRAM banks, but only
  2 cycles/word within one bank (the bank's single port serves both streams).
* Under contention (1–4 competing masters at 70 % request rate on the same SRAM
  slaves, round robin) the simple engine slowed by 4–23 % (4,277–5,027 cycles)
  and the buffered FIFO-8 engine by 34–173 % (3,432–7,006 cycles), while the
  competing masters received correspondingly more bandwidth. With fixed priority (DMA highest) the DMA was
  unaffected and the other masters were throttled — a policy choice, not a free
  gain.

## 4. In the SoC (firmware on the real CPU)

| Measurement (dma_demo, `reports/datafabric/soc_logs/`) | Cycles |
|---|---|
| CPU word-copy loop, 4 KiB SRAM→SRAM | 9,219 |
| DMA 4 KiB incl. driver setup and completion polling | 4,334 (2.1× faster; CPU free during the copy) |
| 16 KiB DMA copy concurrent with a CPU checksum on the same bank: DMA arbitration-loss cycles (perf counter = trace) | 2,040 of 18,426 busy cycles |
| tensor engine K = 256 latency while the DMA streams into the same TSPM banks | 519 = 3 + 2K + 4 (unchanged; the DMA absorbs the conflicts) |
| 4 KiB SRAM→TSPM DMA, engine idle vs concurrent with the tensor engine | 4,337 vs 4,390 (+1.2 %) |
| same demo, buffered engine (`DMA_ENGINE = 1`, FIFO 8 / burst 8): 4 KiB copy / 16 KiB concurrent copy busy / DMA arbitration loss | 2,794 / 10,751 / 510 cycles |
| same demo, fixed priority (`ARB_MODE = 0`) | cycle-identical to round robin (3,853,563 total) |

The fixed-priority and round-robin SoC runs are identical because in this
workload the CPU never loses arbitration under either policy (perf counters: CPUD
`arb_loss = 0` in both runs, DMA `arb_loss = 2,040` in both). The likely reason is
that the DMA was the last master granted whenever the CPU's sparse requests
collided with it, so the RR pointer also favoured the CPU. The policies differ only under sustained contention
from several bursty masters (benchmark fairness table, §1).

SoC-level area: see §5.

## 5. SoC-level area

Two synthesis methods, both generic gates, SRAM/ROM arrays as macros (1,179,648
SRAM bits are identical in both SoCs and not included):

| Method | sfv_soc (release 1) | sfv_soc_df, PERF = 1 | sfv_soc_df, PERF = 0 |
|---|---|---|---|
| module boundaries kept (`synth_soc_hier.md`) | 108.0 k | 125.5 k (**+16.2 %**) | ≈ 118.5 k (**≈ +9.7 %**, PERF=1 minus the 7.0 k counter page) |
| flattened (`synth.md`, rows `soc_*`) | 90.9 k | 121.7 k (+33.8 %) | 113.6 k (+25.0 %) |

Attribution (module boundaries kept): crossbar 8.0 k (response router 2.8 k,
seven request muxes 3.6 k, arbiters 0.7 k, decoders/error slaves 0.3 k, glue 0.6 k)
replacing `sfv_xbar` 1.8 k; seven legacy-slave adapters 0.75 k; simple DMA 3.6 k;
perf counters 7.0 k; INTC and peripheral bridge ≈ −0.4 k. The flattened totals
differ by a lot (flattening let Yosys remove ≈ 17 k of cross-boundary logic from
the baseline but only ≈ 4 k from the DataFabric SoC, whose crossbar/DMA boundaries
carry fewer constants); the hierarchical numbers are the ones used for attribution,
and both are reported unedited. The true overhead in a real flow is expected
between the two figures and must be measured with a PDK. A PDK-based flow is required for a
real area figure (ISSUES DF-01).

## 6. Recommendation for SilicaFlux-V

1. **Crossbar 4×7, round robin, 32 bit** (`sfb_crossbar`) — backward compatible
   (release-1 firmware is cycle-identical), starvation-free with a DMA master, keeps
   the per-master access matrix; ~6 % of the SoC logic.
2. **Simple single-channel DMA** (`ENGINE = 0`, ~3.6 k NAND2-eq, ~3 % of the SoC
   logic): it frees the CPU for every operand transfer (the CPU loop is 2.1×
   slower and blocks the core), meets the 4×4 tensor engine's needs (a K = 256
   operand pair is 2 KiB ≈ 2 k cycles of DMA), and is the easiest block to verify
   (one transaction in flight, one data register). Its formal properties are
   currently proven only to a bounded depth (23 cycles); see ISSUES DF-05.
3. **No performance counters in silicon** (`PERF = 0`): ~7 k NAND2-eq, about the
   size of the crossbar. Keep them for FPGA bring-up builds.
4. **No register slices by default**; add them only where place-and-route shows
   long wires to SRAM macros.
5. **If a product needs more DMA bandwidth**, the measured marginal gains rank:
   dual-port buffered engine (≈ 4× between banks for ≈ +6.9 k NAND2-eq including
   the extra crossbar port) ≫ single-port buffered engines (≤ 1.8× for +4.0–5.4 k)
   — a single-port FIFO DMA is not worth its area. Widening to 64 bit doubles
   bandwidth only together with a 64-bit SRAM and fabric (+4.2 k for the crossbar
   alone).
6. Keep SFB2 at one outstanding transaction until a measured workload needs
   pipelined slaves (READ_LATENCY ≥ 2) at full bandwidth.
