# TwinLab integration

## Status: export ready, **integration not complete**

The SilicaFlux TwinLab in the repository (`SilicaFlux-main/silicaflux-twinlab.zip`, Angular app,
generated with AI Studio) keeps its floorplan as a hard-coded `signal<SemiconductorBlock[]>` in
`src/app/services/twinlab-state.ts`; its physics service (`semiconductor-physics.ts`) uses
`Math.random()` for annealing moves and wafer defects. It has **no file/HTTP import path**, so no
FloorplanLab result is displayed by TwinLab today. FloorplanLab therefore provides:

1. **Exchange schema** — `docs/twinlab_floorplan.schema.json` (JSON Schema generated from the
   Pydantic models in `python/floorplanlab/twinlab.py`, schema version 1.0.0).
2. **Exporter** — every run writes `results/<id>/export/twinlab_floorplan.json` (copied to
   `reports/runs/<id>/`), validated by round-trip against the schema (GATE 13).
3. **TwinLab-shaped blocks** — `twinlab_blocks[]` has exactly the fields of TwinLab's
   `SemiconductorBlock` interface (`models/semiconductor.models.ts`). Quantities FloorplanLab does
   not establish (per-block dynamic/leakage power, activity, temperature, IR drop, z level, metal
   density) are `null` — not placeholders. Logical-group blocks carry
   `provenanceNote: "ANNOTATION ONLY…"` because they are bounding boxes of interleaved cells, not
   physical blocks.
4. **Standalone viewer** — `viewer/twinlab_viewer.html` (no build, no network) loads any export
   and renders die/core, macros (pin edge marked), density grid, pins, PDN straps, group
   annotations, and the TwinLab block table.
5. **Tests** — `tests/test_gates_and_reports.py::test_twinlab_schema_roundtrip`.

## Exported content

| Field | Source |
|---|---|
| `provenance` (run id, tools, ORFS revision, netlist sha256, source ODB, fidelity `OPENROAD_PRELIMINARY`) | run record |
| `technology` (site, row height, routing layers with direction/pitch/width, signal layer range, supply, corner) | profile + tech LEF |
| `die_um`, `core_um` | OpenDB |
| `macros[]` (name, master, bbox, orient, status, words, bits, signal pin edge) | OpenDB + LEF |
| `std_cell_groups[]` (cells, area, centroid, extent; annotation only) | OpenDB instance names |
| `density_grid` (64 × 64 std-cell area per bin) | OpenDB |
| `io_pins[]`, `clock_source_pin` | OpenDB BTerms |
| `power_grid.stripes[]` (non-follow-pin special wires), `followpin_rails`, connectivity check | OpenDB + `pdn_checks.json` |
| `timing` (pre-route WNS/TNS/WHS, critical paths) | OpenSTA reports |
| `routing` (completion, overflow, wirelength, per-layer usage) | FastRoute log |

## What TwinLab needs to finish the integration

* an import action (file upload or `fetch` of the JSON) that maps `twinlab_blocks` into its
  `blocks` signal and `die_um`/`core_um` into its die model;
* handling of `null` quantities as "not established" (today every field is a required number);
* a provenance badge — TwinLab's `ProvenanceTag` has `VERIFIED_PDK`/`ANALYTICAL`/`DEMO_DATA`; the
  closest honest value for these files is a new `OPENROAD_PRELIMINARY` tag;
* overlays from `density_grid`, `power_grid.stripes` and `timing.critical_paths` instead of its
  analytical/random models.
Until TwinLab imports a file, the integration must be reported as **not complete**.
