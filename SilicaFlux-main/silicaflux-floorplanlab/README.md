# SilicaFlux FloorplanLab (Project 05)

**RTL-to-physical floorplanning, SRAM macro placement, power distribution and PPA exploration for
SilicaFlux-V, on OpenROAD-flow-scripts.**  Aureom.AI | SilicaFlux Semiconductor Systems

FloorplanLab takes the real SilicaFlux-V RTL (release 1 + DataFabric DMA, vendored unmodified with
SHA-256 provenance), synthesises it with Yosys through ORFS, and drives the ORFS floorplan → PDN →
placement stages with FloorplanLab's own die/core sizing, SRAM macro arrangements, I/O plan, PDN
configuration and checks. It then runs pre-route STA and a preliminary global route, extracts
geometry/metrics from OpenDB, evaluates 15 quality gates, compares experiments (PPA + Pareto) and
exports a TwinLab exchange file.

> **Status: preliminary physical exploration — not fabrication-ready.** Every result is
> pre-CTS, pre-detailed-route, typical-corner only, on an open 130 nm PDK (IHP SG13G2). See
> [docs/FABRICATION_DEPENDENCIES.md](docs/FABRICATION_DEPENDENCIES.md).

## Results at a glance

Measured numbers, run records and logs: [docs/RESULTS.md](docs/RESULTS.md),
[reports/experiments/summary.md](reports/experiments/summary.md),
[reports/synthesis/SYNTHESIS_REPORT.md](reports/synthesis/SYNTHESIS_REPORT.md),
[reports/experiments/index.html](reports/experiments/index.html) (interactive).

## Quick start

```bash
env/install_toolchain.sh                 # pinned OpenROAD/Yosys/ORFS + IHP SRAM collateral (/opt/eda)
make floorplan-check                     # validate configs, platforms, tools, vendored RTL
make floorplan-route-estimate            # baseline (CFG=configs/silicaflux_v/experiments/A_baseline.yaml)
make floorplan-sweep JOBS=3              # experiments A-E + locality study
make floorplan-report                    # reports/experiments/*, side-by-side floorplans
make floorplan-test                      # pytest (add -m slow for the ORFS reference flow)
```

| Command | What it runs (ORFS stage order) |
|---|---|
| `make floorplan-check` | input validation only: platforms, LEF/Liberty facts, RTL, SDC, vendored sources, tools |
| `make floorplan-synth` | ORFS `synth` (Yosys, shared and hashed) + synthesis gates 2/3 |
| `make floorplan-run` | + `do-2_1_floorplan … do-2_5_floorplan_tapcell` (die/core, pins, SRAM macros, tapcell) |
| `make floorplan-pdn` | + `do-2_6_floorplan_pdn` with FloorplanLab PDN + `check_power_grid` hook |
| `make floorplan-place` | + `do-3_1 … do-3_5` placement, `check_placement`, pre-route STA |
| `make floorplan-timing` | re-run pre-route STA on the placed database |
| `make floorplan-route-estimate` | + preliminary FastRoute global route / congestion |
| `make floorplan-sweep SWEEP=…` | experiment list, grid, random (seeded) or annealing-proposed runs |
| `make floorplan-report` | export (OpenDB geometry, DEF, images, TwinLab JSON) + comparison reports |
| `make floorplan-gui STAGE=place` | OpenROAD GUI on the run's ODB via ORFS `gui_place` (needs a display) |

All targets take `CFG=<run yaml>`; every run writes `results/<id>/run.json` (provenance, stages,
exit codes, timings, metrics, gates) and exits non-zero on a failed stage or gate.

## Layout

```
configs/silicaflux_v/      design.yaml (RTL list, top, defines, clocks, groups, I/O plan),
                           floorplan_base.yaml, experiments/*.yaml, sweeps/*.yaml
configs/mcu_i, full_silicaflux/   explicit "not available" entries (audit)
platforms/<pdk>/           profile.yaml (+ pdn.tcl): ihp_sg13g2, sky130hd (enabled),
                           gf180mcu (disabled: no SRAM path), commercial_{130,65,28} (templates)
constraints/               sfv_soc_df.sdc.tmpl (from release-1 sfv_soc.sdc)
scripts/orfs_hooks/        MACRO_PLACEMENT_TCL library, POST_PDN_TCL checks
scripts/analysis/          OpenDB/OpenSTA extraction: stage metrics, route estimate, geometry export
python/floorplanlab/       config, lef/liberty readers, validate (gates), geometry (Mode A/B,
                           arrangements), orfs driver, pipeline, metrics, experiment_runner,
                           optimiser (annealing + Pareto), compare, report, visualise, twinlab, audit
tests/                     pytest (unit + tool integration + ORFS reference design)
third_party/               vendored, unmodified SilicaFlux-V + DataFabric RTL (PROVENANCE.json)
env/                       tools.lock.yaml, install_toolchain.sh, tools.env
reports/                   curated results (audit, synthesis, experiments, per-run data, logs)
results/                   full run directories incl. ODB/DEF (git-ignored, regenerated)
viewer/twinlab_viewer.html standalone viewer for the TwinLab exchange JSON
docs/                      AUDIT, ORFS_INTEGRATION, FLOW, TECHNOLOGY_PROFILES, TWINLAB_INTEGRATION,
                           FABRICATION_DEPENDENCIES, RESULTS, CHANGES
```

## Ground rules implemented in code

* No invented data: metrics are parsed from tool outputs; missing data → `None` → gate FAIL/NOT_RUN.
* No substitution: the design is `sfv_soc_df` from the repository; MCU-I / full SilicaFlux are
  refused with reasons; GF180 and commercial nodes are rejected (no SRAM path / no foundry kit);
  no node scaling anywhere.
* Logic-only and mock-macro modes are flagged by `macros.mode` and fail GATE 15 (never production).
* Failed runs stay in every report with their failure reasons; they are never ranked.
* Logical groups (CPU, vector, tensor, …) are annotations from instance names, not block outlines.

Branch note: the brief asked for `feature/silicaflux-openroad-floorplan`; this session is
restricted to pushing `claude/silicaflux-floorplan-pipeline-a0lz8j`, which carries the work.
