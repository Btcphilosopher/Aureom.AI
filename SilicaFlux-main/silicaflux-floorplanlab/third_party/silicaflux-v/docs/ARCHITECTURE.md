# SilicaFlux-V architecture

SilicaFlux-V is the minimum SilicaFlux configuration that keeps the
architectural identity **CPU + vector engine + tensor engine + on-chip memory +
interconnect** while minimising area, complexity, external IP, pins and
verification risk.

```
            JTAG (TCK TMS TDI TDO)
                 │
          ┌──────┴──────┐  SBA master (M0, highest priority)
          │ sfv_jtag_dbg│──────────────────────────┐
          └─────────────┘                          │
  ┌──────────────────────┐ I (M2)                  │
  │ sfv_cpu RV32I_Zicsr  │─────────┐               │
  │ 2-stage, M-mode      │ D (M1)  │               │
  └──────────────────────┘────┐    │               │
              ▲ MEI MTI MSI   ▼    ▼               ▼
              │        ┌──────────────────────────────────┐
              │        │  sfv_xbar 3 x 7, fixed priority,  │
              │        │  1 outstanding / master & slave,  │
              │        │  decode errors, execute-never     │
              │        └─┬────┬────┬────┬────┬────┬────┬──┘
              │          │    │    │    │    │    │    │
              │       ROM  SRAM0 SRAM1 SRAM2 SRAM3 TSPM  PERIPH bridge
              │       4KiB 32KiB ×4 (128 KiB)    16KiB  │ register bus (4 KiB pages)
              │                                   │     ├─ SYSCTRL (IDs, boot, test status,
              │        ┌──────────────────────────┴──┐  │   soft reset, bus-error, MBIST)
              │        │ sfv_tile (compute tile)      │  ├─ INTC ──► MEI
              │        │  TSPM 4 banks, engine-first  │  ├─ TIMER ─► MTI, MSI
              │        │  VE: 4×32b SIMD  (ICG)       │◄─┤─ VE / TE register pages
              │        │  TE: 4×4 INT8 MAC (ICG)      │  ├─ UART, SPI, GPIO
              │        └──────────────────────────────┘  └─ ...
              └──────────── interrupt sources (8) ────────────┘
         sfv_mbist (March C-) ── collars on SRAM0..3 and TSPM banks
```

## 1. Configuration (release baseline)

| Item | Value | Parameter |
|---|---|---|
| CPU | RV32I + Zicsr, M-mode, 2-stage in-order | `sfv_cpu` (`RV32E` option) |
| Boot ROM | 4 KiB window (image 2.8 KiB) | `ROM_WORDS` |
| SRAM | 4 banks × 32 KiB = 128 KiB, single-port | `SRAM_BANKS`, `SRAM_BANK_WORDS` |
| Tile scratchpad | 16 KiB, 4 word-interleaved banks | `TSPM_WORDS` |
| Vector engine | 4 lanes × 32 bit, 32×32→32 multiply | `LANES`, `MUL_W` |
| Tensor engine | 4×4 INT8/UINT8, 32-bit accumulators | fixed DIM = 4 |
| I/O | UART, SPI master (1 CS), 8 GPIO, JTAG | `GPIO_N` |
| Clocks | 1 functional clock + TCK | — |
| Pins (signal) | 23 (see §7) | — |

## 2. CPU (`rtl/cpu/sfv_cpu.sv`)
See [ISA_AND_EXCEPTIONS.md](ISA_AND_EXCEPTIONS.md).  Two stages: IF (single
outstanding prefetch + 2-entry buffer, registered redirect) and EX (decode,
RF read, ALU/branch/CSR, blocking load/store, trap entry, write-back).  No
forwarding network or hazard unit is needed — the EX stage writes back before
the next instruction reads, which removes the largest class of pipeline bugs.
CPI: 1 (ALU), 2 (load/store, zero wait), 3 (taken branch/jump).  No M
extension: firmware uses `__mulsi3`; vector/tensor engines provide hardware
multiply (area saving, see process-node report).

## 3. Interconnect (`rtl/bus/`)
SFB protocol (docs/BUS.md).  `sfv_xbar` connects 3 masters (JTAG SBA, CPU-D,
CPU-I; fixed priority in that order) to 7 slaves via base/mask decoding
parameters.  At most one outstanding transaction per master and per slave (a
new one may be granted in the cycle the previous response returns), so
responses are in order without IDs.  Unmapped addresses and masked accesses
(the instruction port may not reach the peripheral window — execute-never)
return a bus error one cycle after grant and are captured in
`SYSCTRL.BUSERR_*` (interrupt source 6).  Peripherals sit behind
`sfv_periph_bridge` on a single-cycle register bus; sub-word writes to
peripheral registers are rejected with a bus error.

## 4. Memories (`rtl/mem/`)
`sfv_sram_sp` is the single SRAM abstraction (1RW, 32-bit, byte enables,
1-cycle read).  Default: inference template (simulation, FPGA EBR).  With
`SFV_SRAM_MACRO` it instantiates `sfv_sram_macro_bank` from
`asic/tech/<pdk>/`, which tiles the foundry/OpenRAM macros (word folding,
depth tiling, registered output select).  Each bank has an MBIST collar
(`sfv_sram_slave`).  The boot ROM is a generated combinational image module
behind a registered address (`sfv_bootrom`), replaceable by a ROM macro.

## 5. Compute tile (`rtl/accel/`)
See [ACCELERATORS.md](ACCELERATORS.md).  TSPM banks are shared by the vector
engine (VE), the tensor engine (TE) and the fabric port.  One engine holds the
TSPM lock per command; per bank and cycle the lock holder has priority over
the fabric, so engine latency is a function of the command only.

## 6. Clocks, resets, DFT
See [CLOCK_RESET.md](CLOCK_RESET.md) and [DFT.md](DFT.md).

## 7. Pin list (package budget)

| Pin | Dir | Function |
|---|---|---|
| CLK | in | functional clock (50 MHz target @130 nm) |
| RST_N | in | asynchronous reset / POR |
| TEST_MODE | in | DFT: reset bypass, clock-gate override |
| TCK TMS TDI TDO | in/in/in/out | JTAG |
| UART_TX UART_RX | out/in | console |
| SPI_SCK SPI_MOSI SPI_MISO SPI_CS0_N | out/out/in/out | boot flash |
| GPIO[7:0] | io | GPIO; [1:0] boot straps at reset; [7:6] status LEDs by convention |
| TEST_PASS, TEST_FAIL | out | optional status (can be bonded out or left internal) |

21 mandatory signal pins + 2 optional + power (≥2 core, ≥2 I/O pairs) → fits
a 32–40 lead package; scan in/out/enable are multiplexed on GPIO in test mode
(scan insertion step, docs/DFT.md).

## 8. Architectural lineage
SilicaFlux-V reduces SilicaFlux 1.0/2.x: 8→1 cores, OoO→in-order,
custom ISA→RV32I (C toolchain), NoC→crossbar, 4 tiles→1 tile, 128-bit lanes
kept (4×32), 4×4 tensor kept (now a true INT8 MAC array).
