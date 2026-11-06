# SilicaFlux-V floorplan experiments -- measured results

All numbers are read from Yosys / OpenROAD / OpenSTA outputs of the runs listed (see `reports/runs/<id>/run.json`
for per-run provenance: git revision, tool versions, ORFS revision, netlist hash, config hash).
Timing is **PRE-ROUTE** (placement parasitics, ideal clocks, typical corner) -- not an achieved frequency.
Global routing is **PRELIMINARY** (FastRoute, pre-CTS). Power is a **vectorless estimate** and is not ranked.

Baseline for deltas: `A_baseline`.  Comparable = same netlist hash, tools, ORFS revision and clock period.

## Runs and status

| run_id | status | physically_valid | arrangement | target_util | failed_gates | failure_reason |
|---|---|---|---|---|---|---|
| A_baseline | completed_with_gate_failures | False | auto (macro_placement) | 0.500 | 12 | n/a |
| B_core_area_plus | running | False | auto (macro_placement) | 0.350 | 12 | n/a |
| C_sram_near_compute | running | False | tspm_center_2x2 | 0.500 | 9,10 | ORFS placement failed |
| D_logic_consolidated | running | False | top_cluster | 0.500 | 9,10 | ORFS placement failed |
| E_pdn_corridors | failed | False | periphery_rows | 0.500 | 10 | ORFS placement failed |
| L_periphery_rows | failed | False | periphery_rows | 0.500 | 10 | ORFS placement failed |
| L_west_east_columns | running | False | west_east_columns | 0.500 |  | n/a |
| S_sky130_baseline | failed | False | auto (macro_placement) | 0.500 |  | input validation failed: sky130_sram_1rw1r_128x256_8.vdd: longest met3 stripe 0.49 um < met4 pitch+width 28.74 um -- the pin is not guaranteed any PDN via; sky130_sram_1rw1r_128x256_8.gnd: longest met3 stripe 0.49 um < met4 pitch+width 28.74 um -- the pin is not guaranteed any PDN via |

## Area

| run_id | die_w_um | die_h_um | die_area_mm2 | core_area_mm2 | std_cell_area_placed_um2 | macro_area_um2 | std_cell_util_of_rows | core_util_incl_macros |
|---|---|---|---|---|---|---|---|---|
| A_baseline | 2819.040 | 2823.660 | 7.960 | 7.505 | 1107780.100 | 4533478.500 | 0.385 | 0.752 |
| B_core_area_plus | 2996.160 | 3001.320 | 8.992 | 8.508 | 1110752.100 | 4533478.500 | 0.287 | 0.663 |
| C_sram_near_compute | 3494.880 | 2279.340 | 7.966 | 7.498 | 1108952.200 | 4533478.500 | 0.388 | 0.752 |
| D_logic_consolidated | 3494.880 | 2279.340 | 7.966 | 7.498 | 1109618.100 | 4533478.500 | 0.388 | 0.753 |
| E_pdn_corridors | 3518.880 | 2362.500 | 8.313 | 7.837 | n/a | 4533478.500 | n/a | n/a |
| L_periphery_rows | 3494.880 | 2279.340 | 7.966 | 7.498 | n/a | 4533478.500 | n/a | n/a |
| L_west_east_columns | 3497.760 | 2967.300 | 10.379 | 9.855 | 1109966.500 | 4533478.500 | 0.213 | 0.573 |
| S_sky130_baseline | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## Performance (pre-route) and routability (preliminary)

| run_id | wns_ns | tns_ns | whs_ns | reg2reg_slack_ns | reg2reg_delay_ns | placed_hpwl_mm | inter_group_hpwl_mm | grt_completed | grt_overflow | grt_hotspot_near_macro_frac | grt_wirelength_mm | grt_wns_ns |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_baseline | 10.049 | 0.000 | -0.345 | n/a | n/a | 6791.960 | 5095.820 | 1.000 | 2339.000 | n/a | 9356.920 | 1.123 |
| B_core_area_plus | 9.877 | 0.000 | -0.373 | n/a | n/a | 7734.310 | 6431.230 | n/a | n/a | n/a | n/a | n/a |
| C_sram_near_compute | 9.740 | 0.000 | -0.320 | n/a | n/a | 6872.470 | n/a | n/a | n/a | n/a | n/a | n/a |
| D_logic_consolidated | 9.971 | 0.000 | -0.390 | n/a | n/a | 7051.030 | n/a | n/a | n/a | n/a | n/a | n/a |
| E_pdn_corridors | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| L_periphery_rows | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| L_west_east_columns | 9.812 | 0.000 | -0.295 | n/a | n/a | 7266.950 | n/a | n/a | n/a | n/a | n/a | n/a |
| S_sky130_baseline | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

Worst register-to-register path per run (pre-route):

| run_id | reg2reg_start | reg2reg_end | reg2reg_slack_ns |
|---|---|---|---|
| A_baseline |  |  | n/a |
| B_core_area_plus |  |  | n/a |
| C_sram_near_compute |  |  | n/a |
| D_logic_consolidated |  |  | n/a |
| E_pdn_corridors |  |  | n/a |
| L_periphery_rows |  |  | n/a |
| L_west_east_columns |  |  | n/a |
| S_sky130_baseline |  |  | n/a |

## Power (information only)

| run_id | pdn_connected | power_vectorless_mw |
|---|---|---|
| A_baseline | True | 8.340 |
| B_core_area_plus | True | 8.340 |
| C_sram_near_compute | True | 8.340 |
| D_logic_consolidated | True | 8.340 |
| E_pdn_corridors | True | n/a |
| L_periphery_rows | True | n/a |
| L_west_east_columns | True | 8.340 |
| S_sky130_baseline | False | n/a |

Power = OpenSTA `report_power` with **no switching-activity file** (input activity 0.1); IHP SRAM
Liberty power data are included as provided by the macro library; clock tree not built. Not used for ranking.

## Quality gates

| run_id | gate1 | gate2 | gate3 | gate4 | gate5 | gate6 | gate7 | gate8 | gate9 | gate10 | gate11 | gate12 | gate13 | gate14 | gate15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_baseline | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FAIL | PASS | PASS | PASS |
| B_core_area_plus | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FAIL | PASS | PASS | PASS |
| C_sram_near_compute | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | NOT_RUN | NOT_RUN | PASS | PASS |
| D_logic_consolidated | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | NOT_RUN | NOT_RUN | PASS | PASS |
| E_pdn_corridors | PASS | PASS | PASS | PASS | PASS | PASS | NOT_RUN | PASS | PASS | FAIL | NOT_RUN | NOT_RUN | NOT_RUN | PASS | PASS |
| L_periphery_rows | PASS | PASS | PASS | PASS | PASS | PASS | NOT_RUN | PASS | PASS | FAIL | NOT_RUN | NOT_RUN | NOT_RUN | PASS | PASS |
| L_west_east_columns | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| S_sky130_baseline | PASS | NOT_RUN | NOT_RUN | PASS | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |

## Deltas vs baseline (%)

| run_id | d_die_area_mm2_pct | d_core_area_mm2_pct | d_std_cell_area_placed_um2_pct | d_placed_hpwl_mm_pct | d_wns_ns_pct | d_reg2reg_delay_ns_pct | d_grt_overflow_pct | d_grt_wirelength_mm_pct | d_grt_wns_ns_pct | d_inter_group_hpwl_mm_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| A_baseline | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | n/a | 0.00 | 0.00 | 0.00 | 0.00 |
| B_core_area_plus | 12.97 | 13.37 | 0.27 | 13.87 | -1.71 | n/a | n/a | n/a | n/a | 26.21 |
| C_sram_near_compute | 0.08 | -0.08 | 0.11 | 1.19 | -3.08 | n/a | n/a | n/a | n/a | n/a |
| D_logic_consolidated | 0.08 | -0.08 | 0.17 | 3.81 | -0.78 | n/a | n/a | n/a | n/a | n/a |
| E_pdn_corridors | 4.44 | 4.43 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| L_periphery_rows | 0.08 | -0.08 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| L_west_east_columns | 30.39 | 31.33 | 0.20 | 6.99 | -2.36 | n/a | n/a | n/a | n/a | n/a |
| S_sky130_baseline | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## Pareto analysis

Rule: only physically valid, comparable runs with a completed global route are ranked; Pareto over die area, register-to-register critical-path delay (pre-route), GRT overflow, GRT wirelength.

Eligible runs: none

Non-dominated (Pareto) set: **none**

Invalid / failed runs (kept, never ranked):

- `A_baseline`: completed_with_gate_failures -- gates failed: 12; nan
- `B_core_area_plus`: running -- gates failed: 12; nan
- `C_sram_near_compute`: running -- gates failed: 9,10; ORFS placement failed
- `D_logic_consolidated`: running -- gates failed: 9,10; ORFS placement failed
- `E_pdn_corridors`: failed -- gates failed: 10; ORFS placement failed
- `L_periphery_rows`: failed -- gates failed: 10; ORFS placement failed
- `L_west_east_columns`: running -- gates failed: none; nan
- `S_sky130_baseline`: failed -- gates failed: none; input validation failed: sky130_sram_1rw1r_128x256_8.vdd: longest met3 stripe 0.49 um < met4 pitch+width 28.74 um -- the pin is not guaranteed any PDN via; sky130_sram_1rw1r_128x256_8.gnd: longest met3 stripe 0.49 um < met4 pitch+width 28.74 um -- the pin is not guaranteed any PDN via
