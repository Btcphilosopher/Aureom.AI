# FloorplanLab flow, configuration and quality gates

```
configs/<design>/experiments/X.yaml ──► validate (GATE 1, 4, run pre-checks)
        │
        ▼  shared synthesis (key = sha256 of RTL, defines, params, SDC, libs, tool versions)
ORFS synth ──► synthesis summary (Yosys stat/check, netlist scan) ──► GATE 2, 3
        │
        ▼  MODE A / MODE B geometry (geometry.py) + arrangement + I/O plan + PDN params
config.mk + hooks ──► do-2_1 … do-2_5 (init, I/O, tdms/macro, tapcell) ──► OpenDB metrics ──► GATE 5, 6, 8
        │
        ▼
do-2_6 PDN (PDN_TCL + POST_PDN_TCL: check_power_grid, macro PG pins) ──► GATE 9
        │
        ▼
do-3_1 … do-3_5 placement ──► check_placement, pins, pre-route STA, vectorless power ──► GATE 7, 10, 11
        │
        ▼
FastRoute global route (pre-CTS, -allow_congestion) ──► overflow, wirelength, GRT-parasitic STA ──► GATE 12
        │
        ▼
export: geometry/connectivity/cells/DEF (OpenDB), images, TwinLab JSON ──► GATE 13; metadata ──► GATE 14, 15
```

## Floorplan sizing

* **MODE A** — explicit `die_area` + `core_area`. Mixing MODE B keys is a configuration error.
* **MODE B** — automatic, from the *mapped* std-cell area, with separately accounted regions:
  std-cell region (`area × logic_growth / target_util`), macro area, macro halos, routing corridors,
  PDN overhead; grown to the macro arrangement's envelope; core snapped to the site/row grid, die =
  core + `core_margin_um` (PDN ring + pin keep-out; *no pad ring*). Utilisation targets 0.30–0.70
  are exploration values (sweep `util_grid`). The resulting breakdown is stored in
  `run.json → geometry.breakdown`.

## SRAM macro placement

| `macros.mode` | meaning | production-eligible |
|---|---|---|
| `physical` | real LEF/Liberty SRAM macros from the platform | yes (if all gates pass) |
| `logic_only` | SRAM black-boxed for logic-only studies -- **not implemented in this release; refused** (both enabled platforms have physical macros) | never (GATE 15) |
| `mock` | conceptual rectangles for visual exploration -- **not implemented; refused** | never (GATE 15) |

`macros.placement: auto` = OpenROAD `macro_placement` (halo/channel), `manual` = a named
arrangement or explicit positions. Arrangements (`geometry.ARRANGEMENTS`): `periphery_rows`
(memory-centric), `tspm_center_2x2` (tensor/tile-centric), `west_east_columns` (distributed),
`top_cluster` (memory-compact, contiguous logic). Each is checked before any tool runs:
inside core, legal orientation (LEF SYMMETRY ∩ profile), no overlap, spacing ≥ halo, pin edge
facing free space ≥ channel, macro channels ≥ vertical PDN strap pitch + width.
RM_IHPSG13 signal pins are all on the R0 bottom edge → rows facing up use `MX`, rows facing
down use `R0`.

## I/O pins

`set_io_pin_constraint` per design `io_plan` group and edge (clock/reset on the bottom-edge centre,
JTAG west, UART/SPI/GPIO east, status north), `place_pins` with min-distance in tracks and corner
avoidance; checked after placement (on boundary, no overlaps, correct edge, layer). These are core
pins; pads/ESD/power pads/seal ring are listed in FABRICATION_DEPENDENCIES.md.

## Tapcell / endcap

Platform script only. IHP SG13G2 has no well-tie/endcap cells → `cut_rows` (count reported).
SKY130 → `tapcell -distance 14 sky130_fd_sc_hd__tapvpwrvgnd_1`. No generic tap distance is applied.

## PDN

`platforms/ihp_sg13g2/pdn.tcl`: Metal1 follow-pin rails 0.44/7.56, Metal5/TopMetal1 ring,
Metal5 straps 2.2/75.6 (platform), **TopMetal1 straps 1.8/30.24** (macro pin coverage), SRAM macro
grid `-grid_over_boundary` with `add_pdn_connect Metal4 TopMetal1`. Checks: `check_power_grid` per
supply net, every macro PG pin on its mapped net, per-pin-name via landing count, LEF-derived
coverage rule, PDN warnings counted. Static IR drop is **not** reported: a pad-less core has no
physically defined supply sources (PDNSim would fall back to an invented checkerboard of virtual
bumps), and the vectorless power analysis attributes 0 W to the SRAM macros although their Liberty
contains leakage/internal power — the current map would be incomplete. Both are listed in
FABRICATION_DEPENDENCIES.md.

## Placement, timing, routing

ORFS placement (timing- and routability-driven global placement, `repair_design`,
`repair_tie_fanout`, detailed placement, `check_placement`). Pre-route STA with
`estimate_parasitics -placement`, ideal clocks, typical corner, all three path groups
(clk, tck, asynchronous) + an explicit register-to-register report. FastRoute global route on the
platform layer range (Metal2–Metal5) with the platform layer adjustments; overflow and wirelength
are measured, never hidden; timing re-estimated with global-route parasitics.

## Quality gates

| Gate | Passes when (evidence) |
|---|---|
| 1 RTL inputs valid | all RTL/include/SDC files exist, top declared, expected macros defined |
| 2 Synthesis succeeds | ORFS synth rc 0, stat present, `check` 0 problems, no unexpected latches |
| 3 No unexpected black boxes | no unresolved module / unknown cell; macro inventory = expected; macro paths resolved |
| 4 Technology inputs present | platform enabled; LEF/Liberty/RC/tapcell/PDN files exist; site, layers, tie/fill cells, macro LEF/LIB/PG pins consistent |
| 5 Geometry valid | die ⊇ core, margins ≥ ring, on grid, rows/sites integral, utilisation < 1 |
| 6 Macros legal | placed, fixed, inside core, legal orientation, no overlap/spacing/pin-access/PDN-channel errors |
| 7 I/O placement | all pins placed on the boundary, no overlaps, constrained edges respected |
| 8 Tapcell/endcap | stage completed, platform method applied, counts recorded |
| 9 PDN | pdngen rc 0, check_power_grid connected for every supply, macro PG pins mapped and via-connected |
| 10 Placement legal | check_placement passes, no unplaced instance |
| 11 Timing completes | STA ran with constrained paths and the design clock (violations are reported, not gate failures) |
| 12 Routing analysis | global route completed (overflow reported as warning) |
| 13 Export | geometry, connectivity, cells, DEF, images, TwinLab JSON written and validated |
| 14 Reproducible | git revision, tools, ORFS, netlist hash, config hash, seed recorded; optional re-run identical |
| 15 No fabricated metrics / substitutions | vendored RTL verified, physical macro mode, enabled platform |

`physically_valid = True` only when gates 2–11 pass in physical macro mode. Passing every gate
means "preliminary floorplan is self-consistent", **not** fabrication readiness.
