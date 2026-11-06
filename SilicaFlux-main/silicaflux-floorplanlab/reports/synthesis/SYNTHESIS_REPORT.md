# SilicaFlux-V synthesis report (ORFS / Yosys)

* Design: `sfv_soc_df` (SilicaFlux-V + DataFabric (sfv_soc_df, PERF=0, ARB_MODE=1, DMA_ENGINE=0, SRAM_IMPL=0))
* Platform: ihp_sg13g2 (IHP SG13G2 130 nm SiGe:C BiCMOS, 7 metal (Metal1-5, TopMetal1-2), open PDK), corner: typical
* Tools: Yosys `Yosys 0.38+92`, OpenROAD `2.0-12331-g6011bbe77`, ORFS `ab2aaf0fb8513f6f6fa8898ba65ae9599a26e621`
* Netlist: sha256 `14a43bb27555e29cdc70e873c7b87b9ef1ed0b43717c1e94470441b9b627fd08` (synthesis key `silicaflux_v__ihp_sg13g2__b8f5a2cee7ec`)
* Flow: ORFS `synth` target, `SYNTH_HIERARCHICAL=1` (`MAX_UNGROUP_SIZE=1000`), ABC speed script, clock period 20 ns from the SDC; defines `SYNTHESIS` (Yosys) + `SFV_SRAM_MACRO`; top parameters `PERF=0 ARB_MODE=1 DMA_ENGINE=0 SRAM_IMPL=0`

## Required figures

| Item | Value | Source |
|---|---|---|
| Total mapped cells (incl. macros) | 95,096 | synth_stat.txt |
| Standard cells | 95,084 | stat minus hard macros |
| Sequential cells (flip-flops) | 4,512 (all async-reset: 4,512) | Liberty `ff` groups |
| Latch cells | 0 | Liberty `latch` groups |
| Integrated clock-gating cells | 2 | Liberty `clock_gating_integrated_cell` |
| Combinational cells | 90,570 | remainder |
| of which buffers/inverters/delay | 20,322 | ABC buffering; ORFS `remove_buffers` drops most at floorplan |
| Tie cells | 46 | hilomap |
| Std-cell area (synthesis) | 1,168,348 um2 = 1.168 mm2 | chip area - macro Liberty area |
| Sequential area | 200,727 um2 | stat |
| Hard-macro area (Liberty) | 4,533,479 um2 = 4.533 mm2 | macro `area` |
| Identified macro instances | 12: 8 x RM_IHPSG13_1P_2048x64_c2_bm_bist, 4 x RM_IHPSG13_1P_512x64_c2_bm_bist | netlist |
| Unresolved black boxes | 0  | netlist scan |
| Unknown cell types | 0 | netlist vs Liberty |
| Yosys `check` problems | 0 | synth_check.txt |

## Macro instances

* `g_sram[0].g_sfv.u_bank/u_ram/u_macro/g_m[0].g2k.u_mac` -> `RM_IHPSG13_1P_2048x64_c2_bm_bist`
* `g_sram[0].g_sfv.u_bank/u_ram/u_macro/g_m[1].g2k.u_mac` -> `RM_IHPSG13_1P_2048x64_c2_bm_bist`
* `g_sram[1].g_sfv.u_bank/u_ram/u_macro/g_m[0].g2k.u_mac` -> `RM_IHPSG13_1P_2048x64_c2_bm_bist`
* `g_sram[1].g_sfv.u_bank/u_ram/u_macro/g_m[1].g2k.u_mac` -> `RM_IHPSG13_1P_2048x64_c2_bm_bist`
* `g_sram[2].g_sfv.u_bank/u_ram/u_macro/g_m[0].g2k.u_mac` -> `RM_IHPSG13_1P_2048x64_c2_bm_bist`
* `g_sram[2].g_sfv.u_bank/u_ram/u_macro/g_m[1].g2k.u_mac` -> `RM_IHPSG13_1P_2048x64_c2_bm_bist`
* `g_sram[3].g_sfv.u_bank/u_ram/u_macro/g_m[0].g2k.u_mac` -> `RM_IHPSG13_1P_2048x64_c2_bm_bist`
* `g_sram[3].g_sfv.u_bank/u_ram/u_macro/g_m[1].g2k.u_mac` -> `RM_IHPSG13_1P_2048x64_c2_bm_bist`
* `u_tile/g_bank[0].u_ram/u_macro/g_m[0].genblk1.genblk1.g512.u_mac` -> `RM_IHPSG13_1P_512x64_c2_bm_bist`
* `u_tile/g_bank[1].u_ram/u_macro/g_m[0].genblk1.genblk1.g512.u_mac` -> `RM_IHPSG13_1P_512x64_c2_bm_bist`
* `u_tile/g_bank[2].u_ram/u_macro/g_m[0].genblk1.genblk1.g512.u_mac` -> `RM_IHPSG13_1P_512x64_c2_bm_bist`
* `u_tile/g_bank[3].u_ram/u_macro/g_m[0].genblk1.genblk1.g512.u_mac` -> `RM_IHPSG13_1P_512x64_c2_bm_bist`

## Synthesis warnings

* 1x Replacing memory \dout with list of registers. See sfv_sram_macro_bank.sv:0
* 1x Found unsupported expression 'SCE*SCD+SCE'*D' in pin attribute of cell 'sg13g2_sdfbbp_1' - skipping.

Interpretation: the `\dout` memory conversion is the 2-entry 64-bit read-mux array inside the IHP macro wrapper (not a RAM); the Liberty expression warning concerns `sg13g2_sdfbbp_1`, a scan flop the design does not use.

## Clock and reset observations

* single functional clock clk + JTAG tck (SDC); resets async-assert/sync-deassert via sfv_rst_sync (u_rs_por/u_rs_sys/u_rs_cpu); the reset tree is unbuffered after synthesis (repair_design buffers it; balanced tree only at CTS)
* flip-flops 4512, all with asynchronous reset/set; ICG instances 2 (`u_tile/u_cg_ve`, `u_tile/u_cg_te`, `sg13g2_slgcp_1`, kept although the platform lists it dont_use -- explicit instances are not remapped)
* high-fanout nets after floorplan (OpenDB): `clk` and `sys_rst_n` (thousands of sinks) -> buffered by `repair_design` at placement; a balanced clock/reset tree is a CTS task (not done here)

## Std-cell area by top-level instance (hierarchy kept above 1000 um2)

| instance | module | std-cell area um2 | macro area um2 |
|---|---|---|---|
| `u_tile` | `$paramod$e1e19d502aed204329de22e3343ebff334944d0d\sfv_tile` | 700,039 | 600,410 |
| `u_cpu` | `$paramod\sfv_cpu\BOOT_ADDR=32'000000000000000000000000000000` | 190,760 | 0 |
| `u_xbar` | `$paramod$d0d0579aeb7dfe7712dc4ea92f85da45153431d9\sfb_crossb` | 55,390 | 0 |
| `u_dma` | `$paramod$d3254a828e9b042b9ccdb73122c5e4123e1bedb4\silicaflux` | 51,073 | 0 |
| `u_rom` | `$paramod\sfv_bootrom\WORDS=s32'00000000000000000000010000000` | 37,783 | 0 |
| `u_dbg` | `sfv_jtag_dbg` | 18,525 | 0 |
| `u_timer` | `sfv_timer` | 17,748 | 0 |
| `u_uart` | `$paramod\sfv_uart\BAUD_RESET=16'0000000011011001` | 16,290 | 0 |
| `u_sysctrl` | `sfv_sysctrl` | 13,022 | 0 |
| `u_pbr` | `$paramod$8e72d3f19b6e9757518038b7ed8ba6faaae46fbe\sfv_periph` | 7,172 | 0 |
| `u_mbist` | `$paramod$55d1b07e6438e37a99a1d3357b9d18fc602eac84\sfv_mbist` | 6,942 | 0 |
| `u_spi` | `sfv_spi` | 5,920 | 0 |
| `u_gpio` | `$paramod\sfv_gpio\N=s32'00000000000000000000000000001000` | 5,278 | 0 |
| `g_v1[0].g_ad.u_ad` | `sfb_v1_slave_adapter` | 3,484 | 0 |
| `g_v1[1].g_ad.u_ad` | `sfb_v1_slave_adapter` | 3,484 | 0 |
| `g_v1[2].g_ad.u_ad` | `sfb_v1_slave_adapter` | 3,484 | 0 |
| `g_v1[3].g_ad.u_ad` | `sfb_v1_slave_adapter` | 3,484 | 0 |
| `g_v1[4].g_ad.u_ad` | `sfb_v1_slave_adapter` | 3,484 | 0 |
| `g_v1[5].g_ad.u_ad` | `sfb_v1_slave_adapter` | 3,484 | 0 |
| `g_v1[6].g_ad.u_ad` | `sfb_v1_slave_adapter` | 3,484 | 0 |
| `g_sram[0].g_sfv.u_bank` | `$paramod\sfv_sram_slave\DEPTH=s32'00000000000000000010000000` | 3,328 | 983,267 |
| `g_sram[1].g_sfv.u_bank` | `$paramod\sfv_sram_slave\DEPTH=s32'00000000000000000010000000` | 3,328 | 983,267 |
| `g_sram[2].g_sfv.u_bank` | `$paramod\sfv_sram_slave\DEPTH=s32'00000000000000000010000000` | 3,328 | 983,267 |
| `g_sram[3].g_sfv.u_bank` | `$paramod\sfv_sram_slave\DEPTH=s32'00000000000000000010000000` | 3,328 | 983,267 |
| `u_intc` | `$paramod\sfv_intc\N=s32'00000000000000000000000000001001` | 1,426 | 0 |
| (top-level glue) | `sfv_soc_df` | 3,284 | 0 |
