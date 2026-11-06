# ASIC implementation flow and baseline results

## Flow
```
rtl/ + asic/tech/<pdk>/ (ICG cell, SRAM macro tiling) + build/sfv_bootrom_image.sv
   │  asic/scripts/run_asic.sh <pdk>     Yosys 0.33: synth -flatten, dfflibmap,
   ▼                                     abc -liberty -D <period>, hilomap, insbuf
build/asic/<pdk>/sfv_soc.netlist.v       + OpenSTA raw pre-layout STA (unbuffered)
   │  asic/scripts/run_place.sh <pdk>    OpenROAD: floorplan (die sized from macro +
   ▼                                     std-cell area), deterministic macro grid with
build/asic/<pdk>/or_*.rpt, *.def         halos, pin placement, global placement,
                                         placement parasitics, repair_design,
                                         repair_tie_fanout, repair_timing, reports
```
Constraints: `asic/constraints/sfv_soc.sdc` — 20 ns (50 MHz) `clk`, 100 ns
`tck`, asynchronous clock groups, 0.25 ns uncertainty, 30 % I/O budgets,
static `rst_ni`/`test_mode`.  Corner: typical (sky130 tt_025C_1v80, IHP
typ_1p20V_25C).  **Ideal clocks, no CTS, no detailed routing: the numbers below
are post-placement estimates, not signoff** (ISS-001).

Configs: `asic/configs/sky130hd.cfg`, `ihp_sg13g2.cfg` (open PDKs, runnable);
`commercial_130nm.cfg.template`, `commercial_65nm.cfg.template` (structure
only — foundry kit paths, cells, SRAM compiler instances to be filled; no
foundry IP supplied).

## Results (tool reports in `reports/synth/<pdk>/`)

| Metric | IHP SG13G2 (130 nm) | SkyWater SKY130 hd (130 nm) | Source |
|---|---|---|---|
| synthesized cells (total / flops / ICG) | 50 482 / 3 832 / 2 | 48 077 / 3 843 / 2 | Yosys stat |
| standard-cell area (synthesis) | 0.684 mm² (≈ 94 k NAND2-eq.) | 0.398 mm² (≈ 106 k NAND2-eq.) | Yosys stat -liberty |
| SRAM macro inventory | 8 × RM_IHPSG13_1P_2048x64 (0.4916 mm²) + 4 × RM_IHPSG13_1P_512x64 (0.1501 mm²) | 36 × sky130_sram_1rw1r_128x256_8 (0.7221 mm²) | Yosys stat + liberty |
| SRAM macro area (144 KiB) | 4.53 mm² (3.8 µm²/bit) | 26.0 mm² (22 µm²/bit) | liberty |
| buffers inserted / cells resized | 8 873 / 11 917 | 33 071 / 28 159 | OpenROAD repair_design |
| placed design area / core utilisation | 5.39 mm² / 78 % | 26.99 mm² / 81 % | OpenROAD report_design_area |
| die (core + 40 µm margin, no pad ring) | 2.71 × 2.71 mm = 7.34 mm² | 5.84 × 5.84 mm = 34.15 mm² | OpenROAD floorplan |
| reg-to-reg worst slack @ 20 ns | **+6.58 ns** | **−6.76 ns** | OpenSTA (in OpenROAD) |
| estimated Fmax (typical, ideal clocks) | **74.5 MHz** | **37.4 MHz** | DERIVED 1/(T − slack) |
| critical path | TSPM SRAM Q (3.9 ns) → vector-lane multiplier | TSPM SRAM Q (launched on the **falling** clock edge) → vector-lane multiplier | OpenSTA |
| reset recovery worst slack (after buffering) | +16.6 ns | +15.6 ns | OpenSTA |
| worst hold slack (ideal clocks) | −0.14 ns (fixed by post-CTS hold repair) | +0.13 ns | OpenSTA |
| logic power @ 50 MHz, 10 % input activity | 11.1 mW (leakage 26 µW) | 5.3 mW (leakage 0.5 µW) | OpenSTA |
| SRAM power | not characterised (IHP SRAM liberty has no power tables) | 325 mW from OpenRAM liberty (deselected macros charged per clock; not credible) | OpenSTA |

Findings
1. **SRAM dominates area on both PDKs** (84 % of placed area on IHP, 96 % on
   sky130).  OpenRAM sky130 macros are ≈ 6× less dense than IHP's compiled
   macros and launch read data on the falling clock edge, halving the time
   for every SRAM-read path → the sky130 build misses 50 MHz.  IHP SG13G2 is
   the preferred open 130 nm baseline (ISS-005).
2. The critical path is the vector engine's 32×32 multiplier fed directly
   from TSPM read data.  If a faster corner target is needed: register the
   SRAM output in the VE (one more cycle per beat, no throughput loss in the
   2-/3-access schedules) or use `MUL_W = 16`.
3. Raw (unbuffered) synthesis STA showed −185 ns because `sys_rst_n` drives
   2 045 reset pins from one gate: reset-tree buffering is mandatory
   (`repair_design` here; balanced reset tree at CTS — ISS-006).
4. Power numbers exclude clock-tree power (ideal clocks) and reliable SRAM
   power; they bound the logic contribution only.

### Reduced-SRAM SKY130 variant (tool-derived; synthesis/placement only)
`SRAM_BANK_WORDS=2048` → 32 KiB SRAM + 16 KiB TSPM (firmware linker scripts
would have to be rebuilt for 32 KiB; not simulated).

| Metric | SKY130, 48 KiB total | SKY130, 144 KiB (baseline) |
|---|---|---|
| SRAM macros | 12 × 0.7221 mm² = 8.67 mm² | 36 × 0.7221 mm² = 26.0 mm² |
| standard-cell area (synthesis) | 0.386 mm² | 0.398 mm² |
| die (no pad ring) | 3.48 × 3.48 mm = 12.1 mm² | 5.84 × 5.84 mm = 34.2 mm² |
| reg-to-reg slack @ 20 ns / Fmax est. | −5.18 ns / 39.7 MHz | −6.76 ns / 37.4 MHz |
Area scales with SRAM as expected; timing does not improve because the
half-cycle SRAM read path (falling-edge macro output) remains
(`reports/synth/sky130hd_mini32k/`).

## Remaining to signoff
CTS (balanced clock and reset trees, ICG-aware), detailed placement/routing,
RC extraction, MCMM STA (ss/ff, −40…125 °C), SI, hold closure, DRC/LVS/antenna
(Magic/KLayout/Netgen for open PDKs; foundry decks for commercial), IR-drop/EM
(PDN — `silicaflux-powerlink` PDN scripts are a starting point), I/O ring,
seal ring, fill, and gate-level simulation of the firmware regression.
