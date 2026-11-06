# Source change summary

## Repository changes (branch `claude/silicaflux-floorplan-pipeline-a0lz8j`)

| Path | Change |
|---|---|
| `SilicaFlux-main/silicaflux-floorplanlab/` | **new** — Project 05 source tree (this project) |
| `SilicaFlux-main/silicaflux-floorplanlab.zip` | **new** — the deliverable archive (same tree, without `results/`) |

No existing file in the repository was modified. SilicaFlux RTL is **vendored unmodified**
(`third_party/`, 66 files from `silicaflux-v-release1.zip` and `silicaflux-datafabric.zip`,
SHA-256 per file in `third_party/SHA256SUMS` and `PROVENANCE.json`); `tools/import_sources.py
--check` proves equality with the archives and runs at the start of every flow run (GATE 15).

## New components

| Area | Files |
|---|---|
| Toolchain pinning | `env/tools.lock.yaml`, `env/install_toolchain.sh` (sha256-verified micromamba, litex-hub OpenROAD/Yosys, ORFS sparse checkout, IHP SRAM collateral), `env/tools.env` |
| Configuration | `configs/silicaflux_v/{design,floorplan_base}.yaml`, `experiments/{A..E,L_*}.yaml`, `sweeps/{experiments,experiments_rerun,util_grid,random_search,anneal}.yaml`; `configs/{mcu_i,full_silicaflux}/design.yaml` (refusals) |
| Technology profiles | `platforms/{ihp_sg13g2,sky130hd}/{profile.yaml,pdn.tcl}`, `platforms/gf180mcu/profile.yaml` (disabled), `platforms/commercial_{130,65,28}/profile.yaml` (templates) |
| Constraints | `constraints/sfv_soc_df.sdc.tmpl` |
| ORFS hooks | `scripts/orfs_hooks/macro_placement_lib.tcl` (MACRO_PLACEMENT_TCL), `post_pdn.tcl` (POST_PDN_TCL) |
| OpenROAD analysis | `scripts/analysis/{flp_lib,stage_metrics,route_estimate,export_geometry}.tcl` |
| Python package | `python/floorplanlab/`: `config` (Pydantic), `lef`, `liberty`, `validate` (gate checks, LEF-driven PDN rules), `geometry` (MODE A/B, arrangements), `pins`, `orfs` (driver, shared synthesis), `pipeline` (stages, gates, retries, snapshots), `metrics` (tool-output parsers), `connectivity`, `experiment_runner` (list/grid/random/anneal, repro), `optimiser` (surrogate annealing, Pareto), `compare`, `report`, `visualise`, `twinlab`, `audit`, `__main__` (CLI) |
| Build | `Makefile` (`floorplan-*` targets), `pytest.ini` |
| Tests | `tests/` (config/inputs, geometry/macros/pins/PDN rules, gate findings/parsers/Pareto/TwinLab, tool integration incl. ORFS reference `gcd`) |
| Viewer | `viewer/twinlab_viewer.html` |
| Documentation | `README.md`, `docs/{AUDIT,ORFS_INTEGRATION,FLOW,TECHNOLOGY_PROFILES,TWINLAB_INTEGRATION,FABRICATION_DEPENDENCIES,RESULTS,CHANGES}.md`, `docs/twinlab_floorplan.schema.json` |
| Curated results | `reports/{audit,synthesis,experiments,runs,logs}/` |

## Engineering decisions recorded in code (with the evidence that forced them)

1. TopMetal1 strap pitch 30.24 µm and `add_pdn_connect Metal4 TopMetal1` for the SRAM grid —
   PSM-0069 / PDN-0110 in A attempt 1, island via stacks in A attempt 2.
2. Side-by-side macro gap ≥ vertical strap pitch + width — PDN-0179 in C/D attempt 1.
3. `PLACE_DENSITY_LB_ADDON` instead of a fixed density — GPL-0302 in A attempt 1.
4. One recorded `-max_phi_coef 1.02` retry on GPL-0307 — E / L_periphery_rows attempt 1.
5. Single-threaded global route (ORFS default) — OpenSTA SIGSEGV in B attempt 1.
6. Per-run script snapshots — script edited during A's route stage corrupted its tail.
7. Bus-bit-safe pin pattern matching (fnmatch treated `[0]` as a character class) — unit test.
