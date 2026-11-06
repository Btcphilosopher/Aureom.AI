# Clocks, resets and clock-domain crossings

## Clocks
| Clock | Source | Domain |
|---|---|---|
| `clk` | CLK pin (no PLL on chip: removes analog IP; the board supplies the frequency) | everything except the JTAG TAP/DRs |
| `tck` | TCK pin | `sfv_jtag_tap`, JTAG data registers (rising and falling edge, IEEE 1149.1) |
| `gclk_ve`, `gclk_te` | `sfv_clkgate` ICGs from `clk` | vector / tensor engines |

ICG enable = engine busy | its register page accessed | `CLK_CTRL.TILE_CG_OFF`;
`TEST_MODE` forces the gates open (`SCE`).  Engines qualify every state update,
so gating is a pure power optimisation: the complete firmware regression gives
identical results *and cycle counts* with gating compiled out
(`SFV_NO_CLOCK_GATE`, used on FPGA).

## Resets (all: asynchronous assert, synchronous de-assert, `sfv_rst_sync`)
| Reset | Composition | Resets |
|---|---|---|
| `por_rst_n` | RST_N pin | JTAG debug system side, SYSCTRL soft-reset generator and RESET_CAUSE.soft |
| `sys_rst_n` | por & !soft_reset & !jtag_sys_reset | crossbar, memories' control, peripherals, tile, MBIST |
| `cpu_rst_n` | sys & !jtag_cpu_hold | CPU only (JTAG can halt the CPU while loading memory) |
| TAP `trst_n` | RST_N pin (no TRST pin; 5×TMS=1 also resets, proven formally) | TCK domain |
In `TEST_MODE` every synchronised reset is bypassed to the RST_N pin so the
tester controls all asynchronous resets (DFT rule).  Soft reset is a keyed
write and an 8-cycle pulse generated in the pin-reset domain.

Pre-layout STA finding: `sys_rst_n` drives > 2000 asynchronous reset pins
from one gate; it must be buffered as a balanced tree (OpenROAD
`repair_design` does this in the baseline flow; the recovery check is then
reported separately as the `asynchronous` path group).

## Clock-domain crossings (clk ↔ tck)
| Crossing | Mechanism |
|---|---|
| SBA command (TCK → clk) | toggle request through `sfv_sync`; command registers quasi-static (TCK side refuses new commands while busy) |
| SBA result (clk → TCK) | toggle acknowledge through `sfv_sync`; result registers written in the same clk cycle as the toggle, sampled ≥ 2 TCK later |
| DBGCTRL bits (TCK → clk) | quasi-static levels, `sfv_sync` per bit |
| status bits (clk → TCK) | `sfv_sync` per bit |
| UART RX, GPIO inputs, boot straps | asynchronous inputs, `sfv_sync` |
No multi-bit value is synchronised directly.  `sfv_sync` must be replaced by
the library's characterised synchroniser cell (dont_touch) — see ISS-008.  SDC
declares `clk`/`tck` asynchronous (`set_clock_groups -asynchronous`).

## Simulation note
Async-reset flops whose clock never toggles (TCK domain) are only reset in an
event-driven simulator if the reset pin has a real edge.  The testbenches
assert reset with an edge at t = 1 ns (found when Icarus and Verilator
disagreed; documented in ISS-012).
