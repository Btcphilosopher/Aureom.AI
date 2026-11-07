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
pip install -r requirements.txt               # core engine, UI (Streamlit >= 1.55) and tests (Python >= 3.10)
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
tables at n = 1/10/25/50/100 for the factory-gate and installed boundaries (with the underlying
marginal, the steps between n and n+1 and a single-house reconciliation) - and writes
`project.json`, `results.json`, `twin.glb`, CSV tables (`quantities.csv`, `geometry_summary.csv` - gross /
net wall, glazing, door, roof and floor areas with their basis - `costs.csv`, `cost_boundaries.csv` with
each boundary's basis and completeness, `repeat_build.csv`, `simulation_summary.csv`,
`scenario_comparison.csv`; every cell formula-injection safe), `twin.ifc` (when `ifcopenshell` is
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

Annotation attributes the analysis reads (shared with the UI editor):

* openings: `storey` (int 0-9, 0 = ground floor) and `block` - a user storey is authoritative over
  window-row clustering, and the facade has at least max(storey) + 1 storeys (user-confirmed);
* roofs: `roof_form` (`gable` / `hip` / `flat` / `monopitch`; on the block's facade it is used when no
  roof says otherwise), `ridge` (`parallel` / `perpendicular` to the view) and `gable_visible` - a roof
  box with `gable_visible` is read as the gable triangle (base = box bottom, apex at the top centre), so
  its pitch is `atan(2 h / w)` with the annotation's basis;
* floor plans (`ImageKind.FLOOR_PLAN`): `building_outline` boxes per block (`block`, default `main`) and
  `dimension` lines with `length_m` (> 0), `axis` (`width` / `depth`) and `block`.  The dimensions set the
  plan scale; each outline then gives its block's width and depth (inferred, or user-confirmed when a
  `depth` dimension is the depth itself), which collapses the hidden-depth hypotheses: H-A only, plus
  H-B "as drawn on the plan" when the plan outlines an extension block (front of the building at the
  bottom of the sheet unless an outline has `front: top`);
* balconies, chimneys and garage / extension boxes are listed as observed but not modelled (warnings,
  unknowns, `AnalysisResult.unmodelled_features`, `BuildingTwin.unmodelled_elements`); annotate a
  garage or extension's front wall as a facade with that `block` to model it.

Manual features are validated like detector output (finite coordinates within 10 % of the image;
invalid ones are dropped with a warning naming them).  An inactive (unticked) feature never
supersedes, calibrates or contributes anything: an inactive copy of a detection is a rejection (the
detection keeps its basis), an inactive annotation keeps its basis and records the rejection.  A
reference whose feature was superseded by a user annotation follows that annotation (noted in the
calibration); a reference on a rejected feature is refused.

## Workflow

```
drop image(s) ─► evidence (detections, facades in pixels, unknowns, concept warnings)
             ─► hypotheses from labelled prior scale cues (H-A rectangular, H-B L-shaped, H-C deep plan;
                 a dimensioned floor plan or a side elevation shows the depth -> fewer hypotheses)
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
`run_pipeline(project, *, store_dir, simulate=True, n_samples=500, manual_features=None) -> PipelineResult`.  With
`run_log=project` (or a list) every call appends a `RunRecord`: function name, sha256 of the
canonical JSON of its inputs and outputs (timestamps removed, so equal inputs give equal hashes),
seed, and versions (package, model schema, Python and libraries, image-analysis adapters, rate book).
`run_pipeline` updates the project in place and never drops user evidence: without
`manual_features` it re-uses the annotations and rejected detections recorded in the stored
`project.analysis` (`pipeline.manual_from_analysis`, shared with the UI), so a re-run neither loses an
annotated facade nor restores a rejected detection.  A reference measurement whose target feature changed
type or span since it was confirmed raises `ValueError` (`pipeline.reference_target_problem`) instead of
calibrating from another feature.  The twin: each twin records the fingerprint of the hypothesis it was
built from (`BuildingTwin.source_fingerprint`).  When the regenerated hypothesis is unchanged the existing
twin is kept; when the evidence or calibration changed (a new reference, a side view, new annotations)
an unedited twin is rebuilt with its assembly selection (version + 1, `system:pipeline` record), while a
twin with user geometry edits is kept and `PipelineResult.warnings` says it is "based on earlier
evidence".

### Editing the twin

`twin.builder.apply_twin_edit(twin, TwinEdit(...), library=None)` returns a new twin version; the
edited value becomes `user_confirmed` (a `tolerance` gives it a range - uniform if it had none) and
the edit log records it.  Values the system changes as a consequence are logged after it with
actor `system:reflow`, `system:coupling` or `system:assembly-check`.

* **Attached blocks stay attached.**  Each block hangs from the block it was first attached to
  (the main block is the plan datum).  After a width / depth change every block is re-placed from
  its parent with the same contact side and alignment - a rear extension flush with the
  rear-right corner stays at that corner, a garage on the main block's left grows leftwards, a
  block hanging from an unmoved block is not dragged along.  An edit that would detach a block or
  make blocks overlap is refused with a message naming them.  The uncertainty simulation uses the
  same attachment tree.
* **Observed roof rise couples span and pitch.**  When the front view shows the roof band of a
  ridge parallel to the frontage, the rise is stored on the roof (`RoofSpec.observed_rise_m`,
  with its evidence).  Then `rise = span x tan(pitch) / 2` (monopitch `/ 1`; span = depth for a
  ridge parallel to the frontage, width for a front-to-rear ridge, the shorter side of a hip).
  Editing the span re-derives the pitch; editing the pitch re-derives the span (attached blocks
  follow); editing the rise or the roof form / ridge axis re-derives the pitch.  The re-derived
  value takes the weakest basis of the rise and the edited value.  A user-confirmed or observed
  value is never overwritten: if both are fixed, both are kept, the implied-vs-observed rise
  residual is logged and the Twin view shows a warning (`coupling_warnings(twin)`).
* **Storeys keep the wall plate on the observed eaves.**  A block whose wall-plate height was
  measured with a calibrated scale stores it (`Block.observed_eaves_m`).  A storeys edit re-derives a
  non-confirmed floor-to-floor `(eaves - FFL) / storeys` (`system:coupling`); when the floor-to-floor is
  user-confirmed / observed or the result is outside 2.0-4.5 m, both are kept, the residual is logged
  and `coupling_warnings(twin)` (Twin view) reports the plate that no longer matches the image.
* Reducing a block's storeys is refused while observed or user openings sit on a removed storey
  (they are named); rule-filled hidden-side openings are regenerated.
* An opening's assembly override is recorded as user-confirmed; with `library=` it must belong to
  the opening kind's element (window, external door, garage door).  Changing the opening kind to
  another element clears the override.

## Provenance legend

| Basis | Meaning | Examples |
|---|---|---|
| `observed` | Measured directly from image evidence | pixel widths, a pitch seen on a gable in elevation |
| `inferred` | Derived by a rule or model from observations | metres from pixels with a calibrated scale, storeys from window rows, depth from a dimensioned plan outline, every measurement and feature of a concept reference (AI concept / rendering / sketch), VLM output (always inferred, untrusted) |
| `user_confirmed` | Entered or confirmed by a person - the strongest basis | the reference frontage, annotations (and storey indices, roof forms, gable pitches, plan dimensions entered on them), edited dimensions, chosen assemblies, supplier quotes |
| `assumed` | A labelled default you may continue with | hidden depth, pitch prior, FFL (and the floor-to-floor and sill heights measured above it), hidden-facade glazing, assembly defaults, rate ranges |
| `unknown` | Not recoverable from the evidence | dependent quantities are left UNRESOLVED, never invented |

Derived values take the **weakest** basis of their inputs.  Visual finishes (what a surface *looks
like*) are stored separately from construction assemblies and never set them.  A detection's pixel
uncertainty is one sigma per edge; a length between two edges or endpoints (a reference, an
opening, a plan dimension) carries √2 × that, and ranges are ±2 sigma.

## Measurement conventions

* Internal units are SI (m, m2, m3, kg, hr); display may be imperial.  x runs along the frontage,
  y front to rear, z up from external ground.
* Block width/depth are external dimensions.  **GEA** = block footprints per storey; **GIA** = GEA
  minus external wall strips (selected external-wall assembly thickness) and half of each wall
  shared between blocks (internal partitions are inside GIA).  Per-m2 allowances use heated GIA.
* External wall area runs from finished ground-floor level (FFL) to the wall plate plus gable /
  monopitch / parapet infill; masonry below FFL is substructure.  Walls shared between blocks are
  counted once as separating walls up to the lower plate.
* Each opening is deducted once, from the wall piece containing it.  An opening on a separating
  wall, outside its wall or on a storey its block does not have (e.g. after reducing the storeys) is
  not deducted and is never counted or priced as a window / door; it is listed in the warnings.
* The part of a taller block's wall inside a lower neighbour's roof void (e.g. the main wall inside
  the garage loft) stays external wall area (conservative) and is reported separately as the
  external-wall measure `lower_roof_void_area`.
* Separating walls are plastered only on faces towards heated blocks (no finish on the garage side),
  consistent with unheated blocks getting no internal wall finish.
* Roof surface = plan area including external overhangs / cos(pitch) (exact for uniform pitch).
  Linear items follow the same exposure rule: a verge runs over the eaves overhang only where that
  eaves edge is exposed, ridges / monopitch top edges / eaves run over the verge overhang only at
  fully exposed corners, and the abutment of a lower roof against a taller wall is measured along
  the roof line (along the rake where a gable end meets the wall).  A hip roof's ridge follows the
  longer side; a `ridge_axis` that disagrees is flagged.
* Oversite dig = (ground-storey GIA - trench plan inside the GIA) x dig depth; trenches are measured
  in full, so no volume is excavated (or carted away) twice.
* Every BoQ line keeps the measure, formula, installed quantity, cutting and waste losses, pack
  rounding, purchased quantity, labour hours and trade, basis and trace links to geometry,
  assemblies, allowances and assumptions.  Line ids are stable and unique:
  `<element_code>.<block|all>.<assembly>.<layer>`, `<code>.allow.<allowance>`; a window / door group
  whose assembly belongs to another element (or is not in the library) uses `all-<element>` instead
  of `all` (e.g. `2.6.all-external_door.win_upvc_dg.0`, unresolved).  Element codes are
  NRM1-inspired groupings (not an NRM compliance claim).

## Cost layers and boundaries

| Layer | Content |
|---|---|
| 1 Materials | one order per material: the lines' unrounded needs are summed, rounded to whole packs once and priced with the `mat:` rate, then allocated to the lines pro rata (each cost line keeps its BoQ line id and shows its share; `CostEstimate.material_orders`); `allow:` supply allowances |
| 2 Labour | BoQ labour hours x `lab:<trade>` rates |
| 3 Plant | excavation, dumper, scaffold, telehandler (programme-dependent hires) |
| 4 Logistics & waste | delivery loads (from the logistics plan), skips, spoil disposal; delivery / collection charges of every rate used (materials, allowances, plant) once per order |
| 5 Preliminaries | setup + weekly x programme weeks (`prelim:` rates) |
| 6 Fees & allowances | fractions of layers 1-4 or 1-5 |
| 7 Contingency | fraction of layers 1-6 |
| 8 Overhead & margin | overhead on 1-7, margin on 1-7 + overhead |
| 9 Land, finance, taxes, sales | only items you enter; VAT only when `include_vat` |

Cumulative boundaries: `materials` (1), `direct_works` (1-4), `construction_before_contingency`
(1-6), `construction_incl_contingency` (1-7), `contract_sum` (1-8) and `total_development_cost`
(1-9, only with layer-9 entries).  Sales value is reported separately and never inside a cost.
Missing rates and unresolved quantities are listed in `unresolved_items` - never priced as zero;
so are ex-works, separately charged and collection rates without a `delivery_charge` (carriage not
priced).  `CostParameters` prelims weekly / set-up, cost per delivery load and cost per skip are
**fallbacks**, used only when the rate book has no `prelim:weekly` / `prelim:setup` /
`log:delivery_load` / `log:skip` rate (the Costs view shows which value is in force).  Their money
amounts (and land, taxes, sales value) are in `CostParameters.currency` (the project currency when the
project was created): after a currency change they are converted with `ProjectSettings.fx_rates`, and
without an FX rate they are not priced (unresolved) - a GBP 1,800 / week fallback is never re-labelled
EUR 1,800 / week.

Every `CostBoundary` carries the weakest `basis` of the cost lines it sums and `unresolved_count`, the
unresolved items in its layers.  When items of layers 1-5 are unpriced (e.g. every rate excluded by a
currency without FX rate or by a pricing date before the rates' dates), the estimate's first warning
starts with `INCOMPLETE ESTIMATE` and names the cause; the header, the boundary cards and
`cost_boundaries.csv` show such amounts as lower bounds (`≥`, "incomplete").

Rate resolution (`costing.rates.resolve_rate`; every adjustment is listed in its warnings):

* **Working time.** Labour, plant and preliminaries rates (`lab:`, `plant:`, `prelim:`) quoted per
  `day` / `week` are converted as *working* time - `ProjectSettings.hours_per_working_day` (8) and
  `working_days_per_week` (5), a labelled assumption with a warning - never as 24 h / 7 days.
  Calendar conversion is kept for other cost keys.
* **Escalation** applies to rates dated before the pricing date, except rates whose `valid_until`
  covers it (a firm quote or price list).  **Regional factor** applies to rates that are not local:
  a rate location is local when, normalised (lower case, punctuation removed), it equals the site
  location, the region or one comma-separated part of either; a supplier quote without a location
  is treated as quoted for the site (warned).  A rate changed by an assumed factor (escalation,
  regional factor, VAT stripped at the project rate, working-time conversion) is `assumed`.
* **Pricing date** defaults to today for a new project (the demo is pinned to 2026-11-01).  When a
  higher-priority rate (e.g. a new supplier quote) is excluded only because it is dated after the
  pricing date and a lower-priority / FICTIONAL rate is used instead, the estimate's first warning
  starts with `PRICING DATE` and the Costs view shows it prominently.

## Marginal vs average cost (repeat build)

For a `ProductionScenario` (`calculate_incremental_cost`): **total** C(n) is the cost of n houses,
**average** = C(n)/n spreads one-off and step costs (design, tooling, factory set-up, lines, site
establishment, capacity steps), and **incremental** = C(n+1) - C(n) is the cost of *one more*
house - it contains a step cost when house n+1 crosses a threshold (a new site, factory line or
capacity step), and all-units procurement tiers can make it drop sharply.  Each row therefore also
carries `step_events` (what happens between n and n+1) and the **underlying marginal** cost: the
cost of house n+1 without capacity steps, pack-rounding steps and the all-units re-pricing of
earlier houses (house n+1 at the tier in force for it; learning, scarcity and per-house items kept).
In the demo the comparison quantities 25 / 50 / 100 coincide with houses per site, so their
incremental cost includes a new site's establishment - the report and the UI flag it.

* **Learning** (`LearningCurve.model`): `unit` (default; unit-time, Crawford-style - each house's
  hours fall by 1 - rate per doubling) or `cumulative_average` (Wright - the average hours of the
  first n houses fall by 1 - rate per doubling, i.e. faster learning for the same rate); the floor
  applies to unit hours.  Labour scarcity can make costs rise with volume.
* **Materials** re-round the single-house material orders for n houses
  (`ceil(n x need / pack) x pack x rate`), so the single-house pack surplus is not multiplied by n.
* **Time-related site overhead** (`site_overhead`: supervision, welfare hire) per house = the
  scenario value, else the single-house time-related preliminaries x `site_overhead_share`
  (assumed 0.5 for PS-site, 0.35 for PS-offsite); site establishment per started site replaces the
  single-house set-up.  `single_house_reconciliation` (shown in the report and the UI) sets the
  single-house layers 1-5 next to the installed C(1), item by item.
* **Boundaries:** `factory_gate` (tooling, factory set-up and lines, factory labour and overhead,
  factory share of materials, factory capacity steps - `StepCost.boundary = "factory"`), `installed`
  (factory gate + design, transport, site labour and materials, plant, site logistics - with the
  factory share of material deliveries and skips removed - site works, establishment and overhead,
  infrastructure, site steps) and `development` (installed + fees, contingency, overhead and
  margin).  Recurring fees apply to a fee base of installed minus reusable design minus factory
  capex (tooling, set-up, lines; for `direct` fees also minus establishment and overhead); one-off
  fees (`FeeItem.recurs_per_house = False`, by default "Architectural & design") are covered by the
  scenario's reusable design cost, not charged per house.

The demo compares **PS-site** (site-built) with **PS-offsite** (off-site panelised timber frame,
per-house values from the timber-frame + brick variant); both are fictional.

## Uncertainty simulation

`simulate_uncertainty(twin, library, rate_book, cost_params, settings, *, config, calibration,
assumptions, fixed_foundation=None)` samples **one coherent house per sample** (one hypothesis, one
assembly set) and recomputes geometry -> quantities -> programme -> logistics -> cost each time.
Inputs are discovered from the twin and the rate book and grouped: `scale` (values from the same
image share one draw; a user-confirmed tolerance is an independent measurement error), `hidden_geometry`
(assumed depths, pitch priors, overhangs, FFL, hidden glazing, bathrooms, partitions; copies of one
prior are one input), `unit_prices` and `labour_rates` (each rate's own range), `labour_productivity`
(0.85-1.30), `waste` (0.6-1.8 x waste fractions), `ground` (ground classes -> foundation option; a
class the selected option suits keeps it) and `lead_time` (window/door lead times -> programme ->
preliminaries).  Latin hypercube or Monte Carlo sampling with one seeded stream per input (common
random numbers: scenarios simulated with the same seed share the draws of their common inputs),
Gaussian copula with within-group correlation and configurable between-group correlation (the notes
report the correlations in force).  Coherence: attached blocks stay attached; the stored observed roof
rise couples span and pitch (every sample starts from the observed rise, also after edits; a
confirmed pitch is never re-derived; a hip's span never exceeds its other side); the observed wall
plate couples floor-to-floor, FFL and sills (the FFL is not counted twice); hidden-facade openings
follow their glazing rule storey by storey.

Outputs: P5..P95 summaries (cost boundaries, GIA, wall and roof areas, concrete, labour hours,
programme weeks, block dimensions), samples, Spearman sensitivities, first-order variance shares,
results conditional on ground class, and an **information-value ranking** - for each group the
action that would resolve its dominant input (e.g. "Confirm the hidden plan depth: upload a side
elevation, or a floor plan with the building outline and one measured dimension, or enter the measured
depth" - exactly the evidence the engine uses for a hidden depth - "Upload a rear elevation" for an
assumed rear glazing ratio, "Commission a site/ground investigation", "Obtain supplier quotations",
"Add a second measured dimension ..." once a reference measurement sets the scale), the P10-P90 width
it accounts for, and a bootstrap standard error with the groups it is tied with (shares carry
2-3 points of sampling noise at n = 500, so close ranks can swap between seeds).  **Interval
meaning:** assumed scenario uncertainty - labelled engineering assumptions propagated through the
model, *not* statistics calibrated against outturn costs - and conditional on the twin's hypothesis
and assembly selection (stated in `interval_type`).  Details: [`docs/UNCERTAINTY.md`](docs/UNCERTAINTY.md).

`compare_build_scenarios` evaluates each `BuildScenario` (hypothesis + assembly overrides +
foundation option + price level) as a complete house with its own optional P10/P50/P90: a scenario's
foundation option is held in its simulation, and `rate_multiplier` scales every rate, delivery charge
and money fallback (prelims, delivery load, skip).  Results are never averaged across hypotheses or
assemblies; hypothesis plausibility is a subjective prior.  Because that uncertainty stays in separate
scenarios, `simulation.scenarios.scenario_spread_entries(comparison)` reports the cost spread between
scenarios that differ only in the hypothesis ("Confirm the footprint: ..."), the construction method
("Confirm the construction method / specification with the designer"), the foundation or the price
level, and `combined_information_value(simulation, comparison)` ranks those entries together with the
within-scenario groups by the money they account for.

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
    always `inferred`, parsed with a strict schema (out-of-range counts are discarded, not clamped), and
    only used as a cross-check: a disagreement is a warning, never a changed value or range.
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
  valid_until, notes`; required: `rate_id, cost_key, layer, unit, value, effective_date, source,
  source_type`).  Absent currency, tax treatment, delivery treatment, location or uncertainty is never
  silent: each absent column / empty cell is a load warning, every supplier-quote / price-list row
  without its currency or tax treatment is named, an absent tax treatment becomes `unknown` (not
  `ex_vat`), and the defaulted currency / tax / uncertainty are tagged on the rate's notes
  (`[assumed defaults: ...]`) so resolving it warns and gives an ASSUMED basis (remove the tag once
  confirmed).  Supplier quotes outrank manual, price-list, adapter and demo rates; expired quotes are
  deprioritised.  No network calls are made.
* **Structural / energy / carbon data** (`simulation.adapters`): `StructuralAnalysisAdapter`,
  `EnergyAnalysisAdapter`, `EmbodiedCarbonDataAdapter` protocols; the defaults raise
  `AdapterNotConfigured`.  `StaticCarbonFactorAdapter` + `apply_carbon_factors(library, adapter)`
  replace the placeholder carbon factors with your dataset.

## Security and untrusted input

* Uploads are validated before use: at most 25 MB and 50 megapixels, PNG / JPEG / WebP / TIFF / BMP
  only (a multi-picture JPEG - Pillow `MPO`, written by many phones - is a JPEG; its first frame is
  analysed), decoded with Pillow `verify()` and re-opened, content-addressed by sha256 (originals kept
  unchanged), a safe EXIF subset only, sanitised filenames.  16-bit / 32-bit images are scaled to 8 bits
  in row chunks, so decode memory stays bounded.  A preserved original is read only from a
  content-addressed `<sha256>.<ext>` file (inside the store folder when one is given; a stored path from
  a loaded project is otherwise ignored), with a size cap and a sha256 check.
* Detection fixtures, annotations, rate books (<= 5 MB, <= 20 000 rows, <= 64 columns / keys per record,
  JSON nesting errors reported, at most 20 unknown column names echoed) and model outputs are parsed
  with Pydantic, range-clamped and treated as data: nothing is `eval`'d or executed, and
  instructions found in images or model output are never followed.  Untrusted text shown in the UI
  (file names, rate-book warnings, feature labels) is HTML- or markdown-escaped, so a link or image in
  a supplier file never renders live.
* Exports use fixed file names checked to stay inside the output folder, atomic writes, and CSV
  formula-injection protection (`io.export.csv_bytes`, also used by the Costs view's "Download rate book
  (CSV)": a supplier cell starting with `= + - @` is prefixed with `'`).  The SQLite store uses parameterised SQL and re-validates state on load.
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
  For a front view the perspective estimate reports as oblique (5-60 deg), the one-sided
  foreshortening bias is removed with a weak-perspective `cos(theta)` correction (horizontal lengths
  for a vertical-cue scale, heights for a horizontal reference); views labelled `front_*_oblique` are
  still kept as evidence only (no facade measurements).
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
`.streamlit/config.toml`; code in `housebuilder_vision/ui/`; needs Streamlit >= 1.55, tested with 1.67 -
an older Streamlit gets a clear upgrade message).  The header shows live KPIs - GIA, construction cost
incl. contingency, contract sum, cost / m², programme, heat-loss coefficient, embodied carbon - with
the change caused by your last edit and, for GIA and the cost figures, a basis badge (the weakest basis
of what they are derived from: block dimensions and wall assembly for GIA, the boundary's cost lines for
costs); an incomplete estimate shows `≥` amounts.  Tags show the twin version, the scale method,
"from concept reference (indicative)" when every image the twin was measured from is an AI concept /
rendering / sketch, FICTIONAL prices, "incomplete - N item(s) unpriced", a reference that conflicts
with the prior scale cues, a twin based on earlier evidence, and "evidence removed - twin kept as a
manual model" after the last image is removed.  The provenance colours (user-confirmed, observed,
inferred, assumed, unknown) are the same in every view and always carry a text label.

| View | What you can do |
|---|---|
| **Images** | Drag and drop photos, renderings, AI concepts, sketches, floor plans or elevations and set each image's kind and view; uploads are validated by `vision.ingest` and rejections are shown once with their reason (the uploader is cleared after every attempt).  Evidence overlay (hover any window, door, facade or line: type, method + version, confidence, pixel uncertainty, evidence), feature table with an *active* toggle (rejecting a feature re-runs the analysis and is recorded in its history; re-ticking a detection your annotation superseded tells you which annotation to untick), manual annotation editor (or box-select on the image) - every row keeps a stable hidden id (`usr:<image>:<uuid8>`, never the row position, so deleting a row never moves a reference) and each edit appends an EditRecord: elevations take type, x0..y1, label, *storey* (openings, 0 = ground, used as entered), *block*, and on roof rows *roof form*, *ridge* (parallel / perpendicular to the view) and *gable visible* (the box is read as the gable triangle, so its pitch is measured); floor plans take `building_outline` boxes per block (optional storeys, `front: top`) and `dimension` lines with *length (m)*, *axis* (width / depth) and *block*, which make the hidden depth evidence-based; an *active* column keeps a row without using it.  Opt-in Claude cross-check (only shown when the adapter is available).  Calibration: the image and the measuring mode sit outside the form, so the feature list always belongs to the chosen image; nothing is pre-filled for a real project (only the fictional demo shows its 9.60 m survey value); pixel endpoints must be entered, lie inside the image and be at least 20 px apart; a reference 2x or more away from the prior scale cues is refused unless you tick "use anyway", and then the twin is not rebuilt automatically; the reference card shows its target, image and the span it was confirmed on, and a reference whose annotation was edited or deleted is reported as not in use.  Prompt for the most useful measurement and a "continue with labelled assumptions" option, unknowns and warnings (concept-reference caveat shown prominently), and hypothesis cards with dimension ranges, subjective plausibility and assumption labels → build the twin. |
| **Twin** | 3D massing coloured by visual finish or by evidence basis; information-level banner; editors for blocks, roofs, openings, hidden-side assumptions, construction assemblies ("appearance does not establish structure") and the foundation option - each value with its basis badge and range, and the observed roof rise where one couples span and pitch (a warning appears when a roof no longer reproduces it).  Every edit goes through `apply_twin_edit` / `apply_construction_assemblies` and recalculates quantities and costs at once; attached blocks follow their parent and coupled values are re-derived (see *Editing the twin*); the edit log lists every change, including system follow-ups.  Summary cards (GEA, GIA, footprint, gross and net external wall, roof surface, glazing, doors, separating walls) carry their basis; banners flag a twin built only from concept references and a twin whose evidence was removed. |
| **Quantities** | Bill of quantities with filters (element, status, basis, text); select a line to see its formula, measure and trace links while the 3D view highlights the wall pieces, blocks, roofs, openings or storeys it was measured from - the selection is remembered by line id, so changing a filter never moves the trace to another line (it is cleared when the line is filtered out).  Allowances and unresolved items are listed separately; a geometry summary (gross and net external wall, glazing, door and garage-door areas, separating walls, roof plan / surface, floor and ceiling areas, GEA / GIA, heated volume, each with its basis; also `geometry_summary.csv`); measurement conventions and GEA / GIA by storey. |
| **Costs** | Boundary cards (amount, basis badge, definition, exclusions; `≥` and "incomplete" when items in their layers are unpriced; GDV shown separately), layer waterfall, cost lines with rate provenance (source, type, date, location, tax, delivery, validity, range), rate book upload (CSV / JSON, validated, load warnings shown escaped) and inline editing, a formula-safe "Download rate book (CSV)", prominent warnings when the estimate is incomplete (with its cause) or the pricing date excludes newer higher-priority rates, a concept-reference notice, commercial parameters (shown in the currency they were entered in; prelim / log fallbacks labelled with the rate actually in force; fees with "recurs per house"; the "applied" message reports every boundary that changed, e.g. "total development cost none → £412,503; contract sum unchanged"), and the uncertainty simulation (samples, seed, method, groups as keyed widgets: every submission runs exactly what was entered, and returning to the tab shows the last run's settings - 300 samples only before the first run, with a note below 500 → histogram + CDF with P10 / P50 / P90, quantiles, tornado, "what to resolve next", results by ground class, interval-type statement). |
| **Scenarios** | Build-scenario comparison (table + small multiples: cost, cost / m², GIA, wall thickness, carbon, HLC, programme, labour; with P10 / P90 included the cost panel draws the P10-P90 range as a line with a P50 diamond next to the deterministic bar, which uses modal values and can sit below P10; "questions that choose between scenarios" lists the hypothesis / construction / foundation / price-level cost spreads and the action that resolves each - `simulation.scenarios.scenario_spread_entries`), repeat-build economics (editable learning model and rate, tiers, factory / site step costs, houses per site, site overhead share; average, incremental and underlying marginal cost for the factory-gate and installed boundaries with markers at n = 1 / 10 / 25 / 50 / 100, the steps between n and n+1, their definitions and the single house vs installed C(1) reconciliation), programme Gantt (critical path in gold), deliveries, carbon by element and heat-loss breakdown - each with its assumptions and boundary. |

The sidebar loads the fictional demo (optionally with the left elevation and an AI-concept
example), creates a new project, saves / loads projects through `io.persistence.ProjectStore`
(`$HBV_DATA_DIR/housebuilder.db`, preserved images in `$HBV_DATA_DIR/images`; default `./.hbv`),
holds the settings (location, currency with FX rates for foreign-currency rates, pricing date -
today for a new project, 2026-11-01 for the demo - metric / imperial display, VAT) and prepares
downloads (JSON, GLB, CSV and IFC when `ifcopenshell` is installed) through `io.export`.

Behaviour: only the open tab runs; heavy work is cached with explicit keys (`twin_hash` + rate
book + parameters), so an edit recalculates in well under a second and a 300-sample simulation
takes a few seconds.  Errors are shown in context, never as tracebacks
(`client.showErrorDetails = "none"`).  The app works without any optional dependency.  The Claude
cross-check toggle appears only when `anthropic` and `ANTHROPIC_API_KEY` are available; it is off
by default (on by default with `HBV_ENABLE_VLM=1`) because it sends the image to an external API.  Screenshots of the five
views are in [`docs/screenshots/`](docs/screenshots/).  `python -m pytest -q tests/test_ui_smoke.py`
runs the app headless (Streamlit AppTest): demo, all tabs, an edit and a simulation.
