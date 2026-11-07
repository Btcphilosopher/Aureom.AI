# Housebuilder.OS Vision — architecture and module contracts

Package: `housebuilder_vision` (Python ≥ 3.10).  Root: `Housebuilder/housebuilder-os-vision/`.

Vertical slice: **image evidence → editable assumptions → parametric geometry → material
quantities → cost model → uncertainty simulation**.  Every number carries provenance.

## 0. Ground rules for all modules

* **Shared contract (do not break):** `core/provenance.py`, `core/units.py`, `core/settings.py`,
  `core/models.py`, `geometry/footprint.py`, `geometry/metrics.py`.  Only *additive* changes
  (new optional fields with defaults, new helper functions) are allowed in these files, and every such
  change must be listed in your final report.  Never rename/remove fields.
* Provenance: use `Basis` (`observed`, `inferred`, `user_confirmed`, `assumed`, `unknown`) and
  `TrackedValue`.  Derived results take `weakest_basis(...)` of their inputs.  Never present an
  assumed or inferred value as observed.  Unknown → `TrackedValue(value=None, basis=UNKNOWN)`.
* Never claim regulatory compliance, certified energy performance, structural adequacy, surveyed
  accuracy or validated durations.  Never identify structure/insulation/foundations/services from
  appearance.  Visual finishes (`VisualFinish`) are kept separate from `AssemblySelection`.
* All prices in bundled data are **explicitly fictional** (`source_type=fictional_demo`, source text
  contains "FICTIONAL"). Never present them as market prices.
* Treat uploaded files and model outputs as untrusted: validate size/format, parse with Pydantic,
  clamp ranges, never `eval`, never execute, never follow instructions found in images/model output.
* Internal units are SI metric (m, m2, m3, kg, hr). Use `core.units.convert` for conversions.
* Optional dependencies (`cv2`, `ifcopenshell`, `anthropic`) must be imported lazily inside
  adapters; the core and the demo must run without them.
* Deterministic: any randomness takes an explicit `seed` / `numpy.random.Generator`.
* Tests go in `tests/test_<module>.py`, runnable with `python -m pytest -q` from the project root.
  Keep the full suite green.

## 1. Coordinates and geometry (implemented — read `core/models.py` docstring)

x along the visible frontage (left→right seen from the front), y from front facade to rear, z up,
z=0 external ground.  Blocks are non-overlapping rectangles; footprints are unions (rectangle,
L-shape, composite).  `geometry.compute_geometry_metrics(twin, ext_wall_t, sep_wall_t)` returns
`GeometryMetrics` (GEA/GIA per storey, wall pieces external/shared with opening deductions done once,
roofs with plan/surface areas and linear items).  Fast path for simulation:
`geometry.metrics.compute_metrics(blocks: list[BlockParams], openings: list[OpeningParams], t_ext, t_sep)`
and `params_from_twin(twin)`.

## 2. Module map and public functions

| Module | Public functions (signatures are the contract) |
|---|---|
| `vision/ingest.py` | `ingest_image(data: bytes, filename: str, *, kind=ImageKind.UNKNOWN, view=ViewDirection.UNKNOWN, store_dir: Path \| None = None) -> ImageAsset` — validates (≤ 25 MB, ≤ 50 MP, PNG/JPEG/WebP/TIFF/BMP only, decodes with Pillow `verify()` then reload), sha256 content addressing (`image_id = "img_" + sha[:16]`), preserves original bytes in `store_dir/<sha>.<ext>`, extracts a *safe subset* of EXIF (Make, Model, FocalLength, FocalLengthIn35mmFilm, DateTimeOriginal) as strings. Raises `ImageRejected`. `load_image_array(asset, store_dir) -> np.ndarray` (RGB uint8, EXIF-transposed). |
| `vision/adapters.py` | Protocols + registry: `SegmentationAdapter`, `ElementDetector`, `PerspectiveEstimator`, `DepthEstimator`, `MultiViewReconstructor`, `VisionLanguageExtractor`; each has `name`, `version`, `capability`, `is_available() -> bool`, and a run method returning model objects. `AdapterRegistry` with `default_registry(fixture_dir=...)`. `AdapterUnavailable` exception. |
| `vision/fixture_adapters.py` | Adapters reading bundled detection fixtures (`demo/data/fixtures/<sha256>.json` or matched by `fixture_key`), validated through a Pydantic fixture schema. |
| `vision/perspective.py` | `estimate_vanishing_points(segments: np.ndarray, image_size, *, rng) -> PerspectiveEstimate` (RANSAC over line intersections, pure NumPy); `detect_line_segments_numpy(rgb) -> np.ndarray` (Sobel + orientation-binned Hough on a downscaled image, NumPy/SciPy only). |
| `vision/opencv_adapters.py` | Optional OpenCV line-segment detector (`cv2.createLineSegmentDetector` or `HoughLinesP`) feeding `estimate_vanishing_points`. |
| `vision/vlm_adapter.py` | Optional Claude adapter (`anthropic` SDK). Model `claude-opus-5-5`, `thinking={"type":"adaptive"}`, structured output via `output_config={"format": {"type": "json_schema", "schema": ...}}`, server-side refusal fallback (`client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`), check `stop_reason == "refusal"` before reading content. Response parsed into `VLMExtraction` (always `INFERRED`, untrusted, clamped). Needs `ANTHROPIC_API_KEY`; otherwise `is_available()` is False. Injectable client for tests. |
| `vision/multiview.py` | `combine_orthogonal_views(analysis) -> MultiViewResult \| None` — links scales of front + side/rear elevations through shared heights (eaves/ridge) and reports observed depth in side views. |
| `vision/analysis.py` | `analyse_images(images: list[ImageAsset], *, store_dir, registry=None, settings=None) -> AnalysisResult` — runs adapters, records `AdapterRun`s, builds `FacadeObservation`s per view/block (storeys from window rows, widths/heights in px, roof form, apparent pitch only from visible gables/verges, openings with storey index, finishes as `ObservedFinish` with appearance-only caveat), sets `unknowns` (structural system, insulation, foundations, concealed services, engineering adequacy, hidden facades), warns for concept references (AI/rendering/sketch). |
| `twin/calibration.py` | `calibrate_scale(analysis, reference: ReferenceMeasurement \| None = None, *, assumptions=None) -> ScaleCalibration` |
| `twin/hypotheses.py` | `generate_geometry_hypotheses(analysis, calibration, *, assumptions=None, settings=None) -> list[GeometryHypothesis]` |
| `twin/builder.py` | `build_parametric_twin(hypothesis, *, selection: AssemblySelection, settings=None, visual_finishes=None, twin_id=None) -> BuildingTwin`; `apply_twin_edit(twin, edit: TwinEdit) -> BuildingTwin` (returns new twin, version+1, logs `EditRecord`, sets basis `USER_CONFIRMED`); `regenerate_hidden_openings(twin) -> BuildingTwin`; `twin_hash(twin) -> str`. |
| `twin/mesh.py` | `build_mesh(twin) -> trimesh.Scene` (walls, roofs, openings as separate named nodes with `metadata={"block_id", "piece_id"/"opening_id", "kind"}`, colours from `visual_finishes` only); `scene_to_plotly_meshes(scene) -> list[dict]` (vertices/faces/colour/name per node for `go.Mesh3d`). |
| `quantities/library.py` | `default_library() -> AssemblyLibrary` (materials, assemblies, foundations, allowances; illustrative data). |
| `quantities/measures.py` | `MEASURES: dict[ElementType, set[str]]`; `element_measures(twin, metrics, library) -> ...` |
| `quantities/takeoff.py` | `apply_construction_assemblies(twin, selection_changes: dict[str, str], library, *, actor="user") -> BuildingTwin`; `wall_thicknesses(twin, library) -> tuple[float, float]`; `calculate_quantities(twin, library, *, metrics=None) -> BillOfQuantities`. |
| `quantities/procurement.py` | `procure(installed, material) -> dict` packaging/waste arithmetic (pure). |
| `costing/rates.py` | `load_rate_book_csv(path_or_buffer, *, name) -> RateBook`, `load_rate_book_json(...)`, `resolve_rate(book, cost_key, unit, *, settings) -> tuple[Rate \| None, float, list[str]]` (returns rate, net value converted to the requested unit/currency/tax basis/escalation, warnings), `PricingAdapter` protocol. |
| `costing/engine.py` | `estimate_construction_cost(boq, rate_book, params: CostParameters, *, settings, programme_weeks=None, library=None) -> CostEstimate` |
| `costing/repeat_build.py` | `calculate_incremental_cost(estimate, scenario: ProductionScenario, *, boundary="installed", max_n=101, comparison_ns=(1,10,25,50,100)) -> RepeatBuildResult`; `total_cost_curve(...)`. |
| `simulation/thermal.py` | `u_value(assembly, library) -> float` (ISO 6946-style combined method: upper/lower bound average with bridging; `u_value_override` for units) ; `heat_loss(twin, metrics, library, settings, ...) -> HeatLossResult` |
| `simulation/carbon.py` | `embodied_carbon(boq, library) -> CarbonResult` |
| `simulation/programme.py` | `build_programme(boq, library, *, crew_sizes=None, lead_times=None) -> ProgrammeResult` (CPM forward/backward pass) |
| `simulation/logistics.py` | `plan_deliveries(boq, library, programme) -> LogisticsResult` |
| `simulation/uncertainty.py` | `simulate_uncertainty(...) -> SimulationResult` |
| `simulation/scenarios.py` | `compare_build_scenarios(...) -> ScenarioComparison` |
| `io/export.py` | `export_project(project, out_dir, *, formats=("json","glb","csv","ifc")) -> ExportManifest` |
| `io/ifc_adapter.py` | optional `export_ifc(twin, metrics, path) -> IfcExportReport` (ifcopenshell), stating information level and omissions |
| `io/persistence.py` | `ProjectStore(db_path)` SQLite: projects (JSON state, schema version), images (sha256, filename, kind, view, stored path), run log |
| `pipeline.py` | Re-exports the 11 named engine functions + `run_pipeline(project) -> PipelineResult` |
| `demo/` | bundled fixture images, detection fixtures, rates CSV, `build_demo_project()`, `run_demo` CLI |
| `ui/app.py` | Streamlit app: Images · Twin · Quantities · Costs · Scenarios |

## 3. Naming conventions

* Cost keys: materials `mat:<material_id>` (unit = material `purchase_unit`); labour `lab:<trade>`
  (unit `hr`); plant `plant:<item>`; allowances `allow:<allowance_id>`; logistics `log:delivery_load`,
  `log:skip`; preliminaries `prelim:weekly`, `prelim:setup`.
* Trades: `groundworks`, `bricklaying`, `carpentry`, `roofing`, `glazing`, `drylining`, `plastering`,
  `electrical`, `plumbing`, `decorating`, `general`.
* Quantity line ids: `<element_code>.<block_id or "all">.<assembly_id>.<layer_index>` or
  `<element_code>.allow.<allowance_id>` — stable across recalculation.
* Element codes (NRM1-inspired grouping, not a claim of NRM compliance): `1` Substructure, `2.1` Frame
  allowance, `2.2` Upper floors, `2.3` Roof, `2.5` External walls, `2.6` Windows & external doors,
  `2.7` Internal walls & partitions, `2.8` Separating walls, `3` Internal finishes, `4` Fittings,
  `5` Services.

## 4. Bundled demonstration (fictional)

"Aureom Demo House, Plot 7" — a fictional two-storey detached house.

* `demo/data/demo_front_elevation.png` (synthetic, 1600×1000 px, near fronto-parallel; generator
  script `demo/make_demo_assets.py`, deterministic).  Hidden truth used *only* to draw the image:
  92 px/m at the facade plane.
* Main block: frontage **9.60 m** (the known reference dimension, "confirmed from a fictional measured
  survey", tolerance ±0.02 m); 2 storeys; FFL 0.15 m; floor-to-floor 2.70 m (plate 5.55 m); gable roof
  with ridge parallel to the frontage (ridge axis x); ridge rise 2.94 m visible as the roof band;
  verge overhang 0.20 m visible at gable ends.  True (hidden) depth 8.40 m ⇒ pitch 35°.
* Garage on the right: 3.20 m wide, 1 storey, front-facing gable (ridge axis y), pitch 30° (directly
  observable), hidden depth (true 6.0 m).
* Front openings, main block (offset from left wall end, metres): GF window 1.80×1.20 @1.00 sill 0.90;
  door 1.00×2.10 @4.30 sill 0; GF window 1.80×1.20 @6.80 sill 0.90; FF windows 1.20×1.20 @1.30, @4.20,
  @7.10 sill 0.90.  Garage door 2.40×2.13 @0.40.
* Finishes (appearance only): walls "red-brown brick-like", roof "dark grey tile-like", garage door
  "white panel-like".
* Optional second view `demo/data/demo_left_elevation.png` (gable end of the main block; reveals
  depth 8.40 m and pitch 35°) to demonstrate multi-view uncertainty reduction.
* Hidden-footprint hypotheses: **H-A rectangular** (main depth from observed rise + pitch prior ⇒
  8.40 m nominal) and **H-B L-shaped** (main depth 7.20 m, implied pitch ≈ 39°, plus a single-storey
  rear extension 4.80×3.60 m at the rear-left with a flat roof).  Uncalibrated runs add an H-C
  "deep plan / shallow pitch" variant.
* Construction assemblies: **masonry cavity wall** (brick / full-fill mineral wool / blockwork /
  plaster) and **timber frame with brick outer leaf** (brick / cavity / breather membrane / OSB /
  140 mm studs + mineral wool / VCL / plasterboard).  Both look like brick from outside — the
  demonstration that appearance does not establish structure.  A third façade alternative,
  **timber frame with timber cladding**, is used in scenario comparisons.
* Fictional supplier rates: `demo/data/fictional_rates_gbp_2026.csv`.
* Repeat-build scenario: site-built vs off-site panelised timber frame, n ∈ {1, 10, 25, 50, 100}.

## 5. Implementation notes (integration)

Appended by the integration module; sections 0-4 above remain the contract.

* **Pipeline** (`pipeline.py`): the 11 engine functions are logged wrappers with one calling
  convention (`library`, `rate_book`, `cost_params`, `settings`, `assumptions`) plus `run_log=`
  (a `Project` or a list).  Each call appends a `RunRecord` with sha256 fingerprints of the
  canonical JSON of inputs and outputs (keys `created_at`, `uploaded_at`, `updated_at`, `timestamp`
  removed so equal inputs hash equally), the seed and versions (package `__version__`, model schema,
  Python / libraries, image-analysis adapters, rate book).  Wider signatures than the table in §2:
  `estimate_construction_cost(boq, rate_book, cost_params, *, settings, programme_weeks, logistics,
  library)`, `simulate_uncertainty(twin, library, rate_book, cost_params, settings, *, config,
  calibration, assumptions, scenario_id, crew_sizes)`, `compare_build_scenarios(base_twin,
  hypotheses, scenarios, library, rate_book, cost_params, settings, *, simulate, config, calibration,
  assumptions, crew_sizes)`, `export_project(project, out_dir, *, boq, estimate, simulation, repeat,
  comparison, formats, library, rate_book)`.
* `run_digital_simulations(twin, boq, library, settings, *, cost_params, crew_sizes,
  lead_time_weeks)` -> `{"programme", "logistics", "carbon", "heat_loss"}`; logistics uses the cost
  parameters' waste bulking and skip volume so skip counts agree with the cost engine.
* `run_pipeline(project, *, store_dir, simulate=True, n_samples=500, registry=None,
  scenario_samples=None, crew_sizes=None) -> PipelineResult`: analysis -> calibration (first
  reference) -> hypotheses -> selected hypothesis -> twin (an existing twin from the same hypothesis
  is kept with its edits) -> quantities -> programme/logistics/carbon/heat loss -> estimate
  (programme weeks + logistics) -> simulation -> repeat build for every production scenario and
  boundary (`factory_gate`, `installed`, `development`) -> scenario comparison.  The project is
  updated in place.  `registry_from_env()` enables the Claude VLM adapter only with
  `HBV_ENABLE_VLM=1`.
* **Uncertainty**: see `docs/UNCERTAINTY.md` (groups, coherence rules, copula, estimators,
  interval meaning).  `GROUP_RHO`, `RESOLVING_ACTIONS` and `GROUND_FOUNDATIONS` are module
  constants of `simulation/uncertainty.py`.
* **Scenarios**: each `BuildScenario` is evaluated as one house; a scenario on the base twin's own
  hypothesis uses the base twin (edits kept), another hypothesis is rebuilt with the base selection;
  assembly overrides are applied with `actor="scenario"` (basis ASSUMED); `rate_multiplier` scales
  every rate.
* **Demo**: `demo/build_demo.py` (`build_demo_project`, `build_uncalibrated_demo_project`,
  `demo_registry` - offline: no transformers adapters) ingests the demo elevation as
  `ELEVATION_DRAWING` (a dimensionally consistent synthetic drawing; `RENDERING` would mark it a
  concept reference).  Production scenarios `PS-site` / `PS-offsite` (fixed per-house values from the
  timber-frame + brick variant) and build scenarios `S1`-`S4`.  `demo/run_demo.py` is the CLI.
