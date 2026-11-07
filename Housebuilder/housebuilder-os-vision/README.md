# Housebuilder.OS Vision

**Aureom.AI's housebuilding digital twin.**  Housebuilder.OS Vision turns photos, renderings,
elevation drawings and plans of a house into an **editable parametric building model**, a
**traceable bill of quantities**, **layered cost estimates**, **digital simulations** (programme,
logistics, embodied carbon, heat loss) and an **uncertainty simulation** that says which missing
evidence would reduce the uncertainty most.  Python package: `housebuilder_vision`.

Every number carries its provenance (**observed / inferred / user-confirmed / assumed / unknown**),
and derived results keep the weakest basis of their inputs.

## What it is - and what it is not

| It is | It is not |
|---|---|
| A *conceptual reconstruction* of a house from image evidence plus labelled assumptions | A measured survey, a photogrammetric model or a site investigation |
| An editable parametric twin (blocks, roofs, openings) with stated hidden-side rules | A design, construction-ready BIM or a set of drawings (IFC export is approx. LOD 100-200 with declared omissions) |
| Construction *hypotheses* (assembly choices) you compare side by side | Identification of structure, insulation, foundations or services from appearance - a brick-like facade can be masonry cavity or timber frame with a brick outer leaf |
| Concept-stage quantities and costs with explicit layers, boundaries and missing items | A tender price, valuation or cost plan for contract |
| Indicative thermal, carbon and programme figures | A SAP / SBEM / PHPP assessment, an EPD, a validated programme or any compliance / structural-adequacy statement |
| Assumed-scenario uncertainty ranges | Statistically calibrated confidence intervals |

All prices, supplier quotes and production economics bundled with the demo are **FICTIONAL**
(`source_type=fictional_demo`, source text contains "FICTIONAL") and are never market prices.

## Quick start

```bash
cd Housebuilder/housebuilder-os-vision
pip install -r requirements.txt               # core engine, UI and tests (Python >= 3.10)
pip install -r requirements-optional.txt      # optional: OpenCV, IFC export, Claude VLM adapter

python -m housebuilder_vision.demo.run_demo   # full fictional demo -> exports/demo (offline, < 1 min)
python -m housebuilder_vision.demo.run_demo --side-view --samples 1000 --out exports/demo-side
streamlit run app.py                          # UI: Images · Twin · Quantities · Costs · Scenarios
python -m pytest -q                           # test suite
```

Run the commands from the project root (or `pip install -e .`, which also installs the `hbv-demo`
command).  `run_demo` options: `--out DIR` (default `exports/demo`), `--samples N` (default 500,
`0` skips the simulations), `--side-view` (adds the left elevation), `--seed`, `--store DIR`
(where the original images are preserved; default `<out>/source_images`), `--formats json,glb,csv,ifc`.

The demo prints a compact report - evidence with basis counts, calibration, hypotheses with
dimension ranges, the twin, the top bill-of-quantities lines, cost boundaries, P10/P50/P90, the
top uncertainty drivers and the next-best evidence, the build-scenario comparison and repeat-build
tables at n = 1/10/25/50/100 for the factory-gate and installed boundaries - and writes
`project.json`, `results.json`, `twin.glb`, CSV tables, `twin.ifc` (when `ifcopenshell` is
installed), `README.txt` and a sha256 `manifest.json`.

The UI (`streamlit run app.py`) has five views: **Images** (upload, evidence, annotations,
calibration), **Twin** (3D massing, hypotheses, parameter edits with provenance), **Quantities**,
**Costs** (layers, boundaries, uncertainty) and **Scenarios** (build scenarios, repeat build).

### Python API

```python
from housebuilder_vision import run_pipeline, __version__
from housebuilder_vision.demo.build_demo import build_demo_project

project = build_demo_project("data/images")            # fictional demo project (H-A selected)
result = run_pipeline(project, store_dir="data/images", n_samples=500)
cost = result.estimate.boundary("construction_incl_contingency").amount
p = {m.metric: m for m in result.simulation.metrics}["construction_incl_contingency"]
print(cost, p.p10, p.p50, p.p90, result.simulation.information_value[0]["resolving_action"])
```

Your own image, step by step (every call can append a `RunRecord` to `project.run_log`):

```python
from housebuilder_vision import pipeline as P
from housebuilder_vision.core.models import ImageKind, Project, ReferenceMeasurement, ViewDirection
from housebuilder_vision.quantities import default_library, default_selection
from housebuilder_vision.vision import ingest_path

project = Project(project_id="plot-12", name="Plot 12")
img = ingest_path("front.jpg", kind=ImageKind.PHOTOGRAPH, view=ViewDirection.FRONT, store_dir="data/images")
my_annotations = [...]  # DetectedFeature list: facade box, ground / eaves / ridge lines, openings
analysis = P.analyse_images([img], store_dir="data/images", registry=P.registry_from_env(),
                            manual_features={img.image_id: my_annotations}, run_log=project)
# without feature_id / p0-p1 the reference spans the main front facade width
ref = ReferenceMeasurement(image_id=img.image_id, real_length=9.6, tolerance=0.02,
                           description="measured frontage")
cal = P.calibrate_scale(analysis, ref, run_log=project)
hyps = P.generate_geometry_hypotheses(analysis, cal, run_log=project)
lib = default_library()
twin = P.build_parametric_twin(hyps[0], selection=default_selection(lib), run_log=project)
boq = P.calculate_quantities(twin, lib, run_log=project)
```

Nothing is fabricated from an image: an upload without a matching detection fixture, detector
output or manual annotation produces warnings, not geometry.  The bundled fixtures cover the demo
images; for other images annotate the facade, ground/eaves/ridge lines and openings (UI or
`manual_features`, recorded as user-confirmed) or plug in a detector adapter (below).

## Workflow

```
drop image(s) ─► evidence (detections, facades in pixels, unknowns, concept warnings)
             ─► hypotheses from labelled prior scale cues (H-A rectangular, H-B L-shaped, H-C deep plan)
             ─► calibrate: one confirmed dimension (e.g. the measured frontage) - hypotheses regenerate
             ─► choose a hypothesis ─► editable twin (hidden facades rule-filled, every value with a basis)
             ─► construction assemblies (assumed until confirmed) ─► quantities (traceable BoQ)
             ─► costs (9 layers, cumulative boundaries) ─► programme / logistics / carbon / heat loss
             ─► uncertainty (P10/P50/P90, drivers, next-best evidence) ─► build scenarios ─► repeat build
             ─► exports (JSON, GLB, CSV, IFC) + run log
```

`housebuilder_vision.pipeline` exposes the 11 engine functions with one calling convention -
`analyse_images`, `calibrate_scale`, `generate_geometry_hypotheses`, `build_parametric_twin`,
`apply_construction_assemblies`, `calculate_quantities`, `estimate_construction_cost`,
`calculate_incremental_cost`, `simulate_uncertainty`, `compare_build_scenarios`, `export_project` -
plus `run_digital_simulations(twin, boq, library, settings)` and
`run_pipeline(project, *, store_dir, simulate=True, n_samples=500) -> PipelineResult`.  With
`run_log=project` (or a list) every call appends a `RunRecord`: function name, sha256 of the
canonical JSON of its inputs and outputs (timestamps removed, so equal inputs give equal hashes),
seed, and versions (package, model schema, Python and libraries, image-analysis adapters, rate book).
`run_pipeline` keeps an existing twin built from the selected hypothesis (with its edits) and
updates the project in place.

## Provenance legend

| Basis | Meaning | Examples |
|---|---|---|
| `observed` | Measured directly from image evidence | pixel widths, a pitch seen on a gable in elevation |
| `inferred` | Derived by a rule or model from observations | metres from pixels with a calibrated scale, storeys from window rows, VLM output (always inferred, untrusted) |
| `user_confirmed` | Entered or confirmed by a person - the strongest basis | the reference frontage, edited dimensions, chosen assemblies, supplier quotes |
| `assumed` | A labelled default you may continue with | hidden depth, pitch prior, FFL, hidden-facade glazing, assembly defaults, rate ranges |
| `unknown` | Not recoverable from the evidence | dependent quantities are left UNRESOLVED, never invented |

Derived values take the **weakest** basis of their inputs.  Visual finishes (what a surface *looks
like*) are stored separately from construction assemblies and never set them.

## Measurement conventions

* Internal units are SI (m, m2, m3, kg, hr); display may be imperial.  x runs along the frontage,
  y front to rear, z up from external ground.
* Block width/depth are external dimensions.  **GEA** = block footprints per storey; **GIA** = GEA
  minus external wall strips (selected external-wall assembly thickness) and half of each wall
  shared between blocks (internal partitions are inside GIA).  Per-m2 allowances use heated GIA.
* External wall area runs from finished ground-floor level (FFL) to the wall plate plus gable /
  monopitch / parapet infill; masonry below FFL is substructure.  Walls shared between blocks are
  counted once as separating walls up to the lower plate.
* Each opening is deducted once, from the wall piece containing it.
* Roof surface = plan area including external overhangs / cos(pitch) (exact for uniform pitch).
* Every BoQ line keeps the measure, formula, installed quantity, cutting and waste losses, pack
  rounding, purchased quantity, labour hours and trade, basis and trace links to geometry,
  assemblies, allowances and assumptions.  Line ids are stable:
  `<element_code>.<block|all>.<assembly>.<layer>`, `<code>.allow.<allowance>`; element codes are
  NRM1-inspired groupings (not an NRM compliance claim).

## Cost layers and boundaries

| Layer | Content |
|---|---|
| 1 Materials | purchased quantities (pack-rounded) x `mat:` rates; `allow:` supply allowances |
| 2 Labour | BoQ labour hours x `lab:<trade>` rates |
| 3 Plant | excavation, dumper, scaffold, telehandler (programme-dependent hires) |
| 4 Logistics & waste | delivery loads (from the logistics plan), skips, spoil disposal |
| 5 Preliminaries | setup + weekly x programme weeks |
| 6 Fees & allowances | fractions of layers 1-4 or 1-5 |
| 7 Contingency | fraction of layers 1-6 |
| 8 Overhead & margin | overhead on 1-7, margin on 1-7 + overhead |
| 9 Land, finance, taxes, sales | only items you enter; VAT only when `include_vat` |

Cumulative boundaries: `materials` (1), `direct_works` (1-4), `construction_before_contingency`
(1-6), `construction_incl_contingency` (1-7), `contract_sum` (1-8) and `total_development_cost`
(1-9, only with layer-9 entries).  Sales value is reported separately and never inside a cost.
Missing rates and unresolved quantities are listed in `unresolved_items` - never priced as zero.

## Marginal vs average cost (repeat build)

For a `ProductionScenario` (`calculate_incremental_cost`): **total** C(n) is the cost of n houses,
**average** = C(n)/n spreads one-off and step costs (design, tooling, factory set-up, lines, site
establishment, capacity steps), and **incremental** = C(n+1) - C(n) is the cost of *one more*
house - it only contains a step cost when a threshold is crossed, and all-units procurement tiers
can make it drop sharply.  Learning follows a Wright curve with a floor; labour scarcity can make
costs rise with volume.  Boundaries: `factory_gate` (factory components), `installed` (factory gate
+ transport, site labour and materials, plant, logistics, site works and establishment,
infrastructure) and `development` (installed + fees, contingency, overhead and margin).  The demo
compares **PS-site** (site-built) with **PS-offsite** (off-site panelised timber frame); both are
fictional.

## Uncertainty simulation

`simulate_uncertainty(twin, library, rate_book, cost_params, settings, *, config, calibration,
assumptions)` samples **one coherent house per sample** (one hypothesis, one assembly set) and
recomputes geometry -> quantities -> programme -> logistics -> cost each time.  Inputs are
discovered from the twin and the rate book and grouped: `scale` (values from the same image share
one draw), `hidden_geometry` (assumed depths, pitch priors, overhangs, hidden glazing, bathrooms,
partitions), `unit_prices` and `labour_rates` (each rate's own range), `labour_productivity`
(0.85-1.30), `waste` (0.6-1.8 x waste fractions), `ground` (ground classes -> foundation option)
and `lead_time` (window/door lead times -> programme -> preliminaries).  Latin hypercube or Monte
Carlo sampling (seeded, reproducible), Gaussian copula with within-group correlation and
configurable between-group correlation.  Coherence: attached blocks stay attached, an observed
roof rise couples depth and pitch, hidden-facade openings follow their glazing rule.

Outputs: P5..P95 summaries (cost boundaries, GIA, wall and roof areas, concrete, labour hours,
programme weeks, block dimensions), samples, Spearman sensitivities, first-order variance shares,
results conditional on ground class, and an **information-value ranking** - for each group the
action that would resolve it (e.g. "Upload a side/rear elevation or a dimensioned floor plan",
"Commission a site/ground investigation", "Obtain supplier quotations") and the P10-P90 width it
accounts for.  **Interval meaning:** assumed scenario uncertainty - labelled engineering
assumptions propagated through the model, *not* statistics calibrated against outturn costs.
Details: [`docs/UNCERTAINTY.md`](docs/UNCERTAINTY.md).

`compare_build_scenarios` evaluates each `BuildScenario` (hypothesis + assembly overrides +
foundation option + price level) as a complete house with its own optional P10/P50/P90.  Results
are never averaged across hypotheses or assemblies; hypothesis plausibility is a subjective prior.

## Simulations and their boundaries

* **Thermal** (`simulation.thermal`): ISO 6946-style U-values (combined upper/lower-bound method with
  bridging), ISO 13370-style ground floors, simplified steady-state heat-loss coefficient, peak load
  and degree-day space heat.  Not SAP / SBEM / PHPP; no compliance or certified-performance claim.
* **Embodied carbon** (`simulation.carbon`): A1-A3 + A5 waste share (+ A4 when transport inputs are
  given) with illustrative placeholder factors - replace them through a carbon-data adapter.
* **Programme** (`simulation.programme`): indicative task network and critical path from library
  labour hours and assumed crews; windows/doors gated by lead time.  Not a validated programme.
* **Logistics** (`simulation.logistics`): delivery batches, loads, order-by days, storage peak,
  waste volume and skips.

## Adapters - how to plug in

Optional dependencies are imported lazily inside adapters; the core and the demo run without them.

* **Vision** (`vision.adapters`): protocols `SegmentationAdapter`, `ElementDetector`,
  `PerspectiveEstimator`, `DepthEstimator`, `VisionLanguageExtractor`, `MultiViewReconstructor`
  (each with `name`, `version`, `capability`, `is_available()`) in an `AdapterRegistry`; the first
  available adapter per capability wins and every attempt is recorded as an `AdapterRun`.
  Bundled: detection fixtures (demo), NumPy line detection + RANSAC vanishing points, optional
  **OpenCV** line segments (`opencv-python-headless`), orthogonal multi-view combination, a COLMAP
  SfM interface (not configured by default).
  * **Claude VLM** (`vision.vlm_adapter.ClaudeVLMExtractor`, model `claude-opus-5-5`, structured
    JSON output, refusal handling): needs `pip install anthropic`, `ANTHROPIC_API_KEY` and the opt-in
    **`HBV_ENABLE_VLM=1`** (read by `pipeline.registry_from_env()`; or
    `default_registry(enable_vlm=True)`).  It sends the image to an external API.  Its output is
    always `inferred`, parsed with a strict schema, clamped, and only used as a cross-check.
  * **Depth / zero-shot detection** via `transformers` + `torch` (not in the requirements; install
    them yourself): `HuggingFaceZeroShotDetector` (openings only, no facade extents) and
    `TransformersDepthAdapter` (relative depth for context only).  They may download model weights,
    so the demo registry (`demo.build_demo.demo_registry()`) leaves them out.
  * Your own adapter: implement the protocol and `registry.register(MyDetector(), first=True)`, then
    `run_pipeline(project, store_dir=..., registry=registry)`.
* **IFC** (`io.ifc_adapter.export_ifc`, `pip install ifcopenshell`): conceptual IFC4 (approx. LOD
  100-200) with provenance property sets and declared omissions; a missing `ifcopenshell` becomes an
  export warning.
* **Pricing** (`costing`): `PricingAdapter` protocol (`fetch_rates(cost_keys, settings)`),
  `ManualCSVPricingAdapter`, `FictionalDemoPricingAdapter`, `fetch_rate_book(adapters, ...)`,
  `load_rate_book_csv/json` (columns = `Rate` fields: `rate_id, cost_key, description, layer, unit,
  currency, value, location, effective_date, source, source_type, supplier, tax_treatment, vat_rate,
  delivery_treatment, delivery_charge, uncertainty_low, uncertainty_high, quote_reference,
  valid_until, notes`).  Supplier quotes outrank manual, price-list, adapter and demo rates;
  expired quotes are deprioritised.  No network calls are made.
* **Structural / energy / carbon data** (`simulation.adapters`): `StructuralAnalysisAdapter`,
  `EnergyAnalysisAdapter`, `EmbodiedCarbonDataAdapter` protocols; the defaults raise
  `AdapterNotConfigured`.  `StaticCarbonFactorAdapter` + `apply_carbon_factors(library, adapter)`
  replace the placeholder carbon factors with your dataset.

## Security and untrusted input

* Uploads are validated before use: at most 25 MB and 50 megapixels, PNG / JPEG / WebP / TIFF / BMP
  only, decoded with Pillow `verify()` and re-opened, content-addressed by sha256 (originals kept
  unchanged), a safe EXIF subset only, sanitised filenames.
* Detection fixtures, annotations, rate books (<= 5 MB, <= 20 000 rows) and model outputs are parsed
  with Pydantic, range-clamped and treated as data: nothing is `eval`'d or executed, and
  instructions found in images or model output are never followed.
* Exports use fixed file names checked to stay inside the output folder, atomic writes, and CSV
  formula-injection protection.  The SQLite store uses parameterised SQL and re-validates state on load.
* Network access happens only through opt-in optional adapters: the Claude adapter
  (`HBV_ENABLE_VLM=1`) and, if you install `transformers`, model-weight downloads by the transformers
  adapters.  The engine, pricing, exports and the demo make no network calls.

## Data and persistence

`io.persistence.ProjectStore` keeps validated project state (JSON + schema version), the image
registry and a run log in SQLite at **`$HBV_DATA_DIR/housebuilder.db`** (default
`./.hbv/housebuilder.db`; `":memory:"` for tests):

```python
from housebuilder_vision.io import ProjectStore
with ProjectStore() as store:
    store.save_project(project)
    again = store.load_project(project.project_id)
```

`Project.run_log` and the store's `runs` table are not synchronised automatically - log to the one
you use.  Exports carry engine versions, source-image sha256s, the twin hash and the simulation seed
so a result can be reproduced.

## Testing

```bash
python -m pytest -q                         # full suite (under a minute)
python -m pytest -q tests/test_end_to_end.py tests/test_uncertainty.py
```

The end-to-end tests run image -> exports on the demo and check provenance (the confirmed frontage is
`user_confirmed`), traceability of every BoQ line, no unresolved items in the demo, run-log hashes,
reproducibility for a seed, that missing dimensions keep their uncertainty, that a side view narrows
the depth uncertainty, the four coherent build scenarios, average vs incremental repeat-build cost
and the `run_demo` CLI.

## Project layout

```
housebuilder_vision/
  core/          provenance (Basis, TrackedValue), units, settings, validated data models (contract)
  geometry/      exact rectilinear footprints and analytic metrics (GEA/GIA, walls, roofs)
  vision/        ingest, adapters, fixtures, perspective, OpenCV, VLM, multi-view, analysis
  twin/          calibration, hypotheses, parametric twin + edits, 3D mesh
  quantities/    assembly library, measures, take-off, procurement
  costing/       rate books, cost engine, repeat-build economics, pricing adapters
  simulation/    thermal, carbon, programme, logistics, engineering adapters, uncertainty, scenarios
  io/            export (JSON/GLB/CSV), IFC adapter, SQLite persistence
  pipeline.py    the 11 logged engine functions, run_digital_simulations, run_pipeline
  demo/          fictional demo assets, build_demo, run_demo
tests/           pytest suite
docs/            ARCHITECTURE.md (module contracts), UNCERTAINTY.md (simulation method)
```

## Limitations

* Single-front-view geometry is near-fronto-parallel elevation modelling, not photogrammetry; hidden
  depth, rear and side facades come from labelled hypotheses and rules until evidence replaces them.
* Footprints are unions of axis-aligned rectangular blocks; roofs are gable, hip, monopitch or flat
  with uniform pitch; valleys are not measured as separate linear items.
* Assemblies, allowances, carbon factors, labour hours and crews are generic illustrative data.
* The uncertainty ranges are assumptions; storey counts, the hypothesis and the assembly selection
  are held fixed inside one simulation (compare those as scenarios).
* Heat loss, carbon and programme outputs are indicative and make no compliance claims; foundations
  always require a site investigation and an engineer's design.
* Bundled demo data - images, the "survey" dimension, rates and production economics - are fictional.

## User interface

```bash
streamlit run app.py          # from the project root; opens http://localhost:8501
```

A compact upload-and-inspect app (Streamlit, Aureom.AI graphite / ivory / gold theme in
`.streamlit/config.toml`; code in `housebuilder_vision/ui/`).  The header shows live KPIs - GIA,
construction cost incl. contingency, contract sum, cost / m², programme, heat-loss coefficient,
embodied carbon - with the change caused by your last edit, plus tags for the twin version, the
scale method, FICTIONAL prices and anything unresolved.  The provenance colours (user-confirmed,
observed, inferred, assumed, unknown) are the same in every view and always carry a text label.

| View | What you can do |
|---|---|
| **Images** | Drag and drop photos, renderings, AI concepts, sketches, floor plans or elevations and set each image's kind and view; uploads are validated by `vision.ingest` and rejections are shown with their reason.  Evidence overlay (hover: type, method + version, confidence, pixel uncertainty, evidence), feature table with an *active* toggle (rejecting a feature re-runs the analysis), manual annotation editor (type, x0..y1, label, storey, block, roof form; or box-select on the image), opt-in Claude cross-check (only shown when the adapter is available), calibration (feature width or pixel endpoints + real length, unit and tolerance) with a prompt for the most useful measurement and a "continue with labelled assumptions" option, unknowns and warnings (concept-reference caveat shown prominently), and hypothesis cards with dimension ranges, subjective plausibility and assumption labels → build the twin. |
| **Twin** | 3D massing coloured by visual finish or by evidence basis; information-level banner; editors for blocks, roofs, openings, hidden-side assumptions, construction assemblies ("appearance does not establish structure") and the foundation option - each value with its basis badge and range.  Every edit goes through `apply_twin_edit` / `apply_construction_assemblies` and recalculates quantities and costs at once; the edit log lists every change. |
| **Quantities** | Bill of quantities with filters (element, status, basis, text); select a line to see its formula, measure and trace links while the 3D view highlights the wall pieces, blocks, roofs, openings or storeys it was measured from.  Allowances and unresolved items are listed separately; measurement conventions and GEA / GIA by storey. |
| **Costs** | Boundary cards (amount, definition, exclusions; GDV shown separately), layer waterfall, cost lines with rate provenance (source, type, date, location, tax, delivery, validity, range), rate book upload (CSV / JSON, validated, warnings shown) and inline editing, commercial parameters, and the uncertainty simulation (samples, seed, groups → histogram + CDF with P10 / P50 / P90, quantiles, tornado, "what to resolve next", results by ground class, interval-type statement). |
| **Scenarios** | Build-scenario comparison (table + small multiples: cost, cost / m², GIA, wall thickness, carbon, HLC, programme, labour), repeat-build economics (editable learning, tiers, step costs, houses per site; average vs incremental cost for the factory-gate and installed boundaries with markers at n = 1 / 10 / 25 / 50 / 100 and their definitions), programme Gantt (critical path in gold), deliveries, carbon by element and heat-loss breakdown - each with its assumptions and boundary. |

The sidebar loads the fictional demo (optionally with the left elevation and an AI-concept
example), creates a new project, saves / loads projects through `io.persistence.ProjectStore`
(`$HBV_DATA_DIR/housebuilder.db`, preserved images in `$HBV_DATA_DIR/images`; default `./.hbv`),
holds the settings (location, currency with FX rates for foreign-currency rates, pricing date,
metric / imperial display, VAT) and prepares downloads (JSON, GLB, CSV and IFC when
`ifcopenshell` is installed) through `io.export`.

Behaviour: only the open tab runs; heavy work is cached with explicit keys (`twin_hash` + rate
book + parameters), so an edit recalculates in well under a second and a 300-sample simulation
takes a few seconds.  Errors are shown in context, never as tracebacks
(`client.showErrorDetails = "none"`).  The app works without any optional dependency.  The Claude
cross-check toggle appears only when `anthropic` and `ANTHROPIC_API_KEY` are available; it is off
by default (on by default with `HBV_ENABLE_VLM=1`) because it sends the image to an external API.  Screenshots of the five
views are in [`docs/screenshots/`](docs/screenshots/).  `python -m pytest -q tests/test_ui_smoke.py`
runs the app headless (Streamlit AppTest): demo, all tabs, an edit and a simulation.
