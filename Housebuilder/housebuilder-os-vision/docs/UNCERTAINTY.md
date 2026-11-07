# Uncertainty simulation - method and interpretation

Module: `housebuilder_vision/simulation/uncertainty.py` (`simulate_uncertainty`), scenario
comparison in `simulation/scenarios.py` (`compare_build_scenarios`).

## 1. What a sample is

Each sample is **one coherent house**: the twin's own geometry hypothesis, its assembly selection,
one foundation option and one draw of every uncertain input.  The sample is evaluated through the
same engine chain as the deterministic estimate:

```
sampled parameters
  -> geometry.metrics.compute_metrics (fast path on BlockParams / OpeningParams)
  -> quantities.calculate_quantities(twin copy with updated TrackedValue.value, metrics=...)
  -> labour productivity (hours per trade)
  -> simulation.build_programme (lead times gate windows & doors)
  -> simulation.plan_deliveries
  -> costing.estimate_construction_cost(programme_weeks=..., logistics=...)
```

Nothing is averaged across hypotheses or construction assemblies.  Alternatives (H-A vs H-B,
masonry vs timber frame) are separate `BuildScenario`s, each with its own P10/P50/P90, so every
interval is **conditional on one hypothesis and one assembly selection** (`SimulationResult.interval_type`
names them).  A scenario's own `foundation_option` is part of its house: its simulation holds that
foundation (`simulate_uncertainty(fixed_foundation=...)`, ground classes not sampled).  The spread
*between* scenarios is reported separately as information value (section 7).

## 2. Inputs and groups

| Group | Inputs (discovered, never invented) | Distribution | rho within group | Resolving action |
|---|---|---|---|---|
| `scale` | twin values with `correlation_group = "scale:<image>"`, the calibration `metres_per_pixel`, measurement errors of evidence-derived values | their own `TrackedValue` distribution | 1.0 within one image (comonotonic: one latent draw); errors without a group and every `USER_CONFIRMED` tolerance independent | Confirm a reference dimension such as the measured frontage; once a reference measurement / dimensioned plan sets the scale: *Add a second measured dimension (e.g. the eaves height or the overall depth) or a less oblique photo*; a dominant user-confirmed value: *Measure <field> more precisely* |
| `hidden_geometry` | `ASSUMED` geometry (hidden depths, pitch priors, overhangs, FFL, extension sizes), hidden-facade glazing ratios, bathrooms, partition allowance | own distribution | 0.0 | Confirm the hidden plan depth: upload a side elevation, or a floor plan with the building outline and one measured dimension, or enter the measured depth (per input: rear / side glazing ratio -> the rear / side elevations; FFL, overhangs, bathrooms, partitions -> their own measurement) |
| `unit_prices` | one multiplier per non-labour rate used (all foundation options) | triangular(1+low, 1, 1+high) from the rate | 0.5 | Obtain supplier quotations |
| `labour_rates` | one multiplier per `lab:<trade>` rate used | triangular(1+low, 1, 1+high) | 0.7 | Agree contractor labour rates |
| `labour_productivity` | hours multiplier per trade | triangular(0.85, 1.0, 1.30) - assumption | 0.6 | Agree a contractor programme / productivity data |
| `waste` | multiplier per material category on `waste_fraction` | triangular(0.6, 1.0, 1.8) - assumption | 0.5 | Confirm waste management plan |
| `ground` | ground class from `SimulationConfig.ground_classes` | discrete | - | Commission a site/ground investigation |
| `lead_time` | lead time of window / door / garage-door materials | the material's `lead_time_weeks` | 0.5 | Confirm window/door lead times with suppliers |

Ground classes map to foundation options: a class the **selected** option lists in its
`suitable_ground` keeps the selected option (e.g. an assumed `fdn_raft` stays a raft on variable and
poor ground); otherwise `good_clay_or_gravel` -> the selected option, `variable_made_ground` ->
`fdn_deep_trench_fill`, `poor_soft_ground` -> `fdn_piled_allowance` (`GROUND_FOUNDATIONS`; other
class names: the first library option listing them in `suitable_ground`).  A user-confirmed foundation,
or one fixed by a build scenario (`fixed_foundation`), removes the ground group.
`config.include_groups` limits the sampled groups.

The resolving action shown for a group is that of its dominant input (`input_action`): the
hidden-geometry entry names the evidence for its strongest input, and the scale entry names a
user-confirmed value only when the group clearly matters (share above 1 % and two standard errors) and
that value carries most of it.  The hidden-depth action lists exactly the evidence the engine can use:
a scale-linked **side** (left / right) elevation (`vision.multiview`; a rear view only cross-checks the
width), a `FLOOR_PLAN` image with a `BUILDING_OUTLINE` per block and a `DIMENSION` carrying `length_m`
(`twin.calibration.plan_evidence`), or a depth entered in the twin editor.

Held fixed inside one simulation (stated in the result notes): storey counts, the hypothesis and
the assembly selection, library allowance quantities, take-off substructure priors (spoil bulking,
oversite dig, reinforcement) and the commercial fractions (fees, contingency, overhead, margin).

Identical prior copies (e.g. the FFL or eaves-overhang prior copied to every block, also a hidden
extension's FFL "assumed equal to the main block's FFL") are one shared input, because the hypothesis
states one assumption for all blocks: `ASSUMED` values without a correlation group merge on field,
value, range and distribution, whatever their source / note text.

## 3. Coherence rules

* **Attached blocks stay attached.**  The base footprint is analysed once with
  `twin.builder.footprint_attachments` - the same attachment tree the twin editor reflows with -
  so every block touching an already placed block keeps its contact side and alignment (flush
  front/rear or left/right, else the base offset).  Their origins are derived per sample.
* **Depth-pitch coupling.**  A pitched roof that stores an observed rise (`RoofSpec.observed_rise_m`,
  set by the hypotheses when the front view shows the roof band) keeps
  `rise = k x span x tan(pitch)` exact in every sample (k = 0.5 gable / hip, 1 monopitch; span =
  depth for a ridge parallel to the frontage, width for a front-to-rear ridge, the shorter side of
  a hip).  Every sample starts from the *stored* observed rise - never from the rise recomputed from
  an edited depth or pitch - scaled by the sampled `metres_per_pixel` of its image (unless the rise
  itself was user-confirmed).  A user-confirmed / observed span is sampled and the pitch derived; a
  user-confirmed / observed pitch is sampled (held when fixed) and the span derived exactly,
  `span = rise / (k tan(pitch))` - that pitch is **never re-derived**, so a fixed confirmed pitch
  is the same in every sample; with neither fixed, an image-derived span is sampled, otherwise the
  pitch prior, and the span derived from the prior is clipped to the span range (the pitch is then
  re-derived so the relation stays exact).  A **hip** spans its shorter side, so its coupled span is
  capped at the other plan dimension in every sample (a front view of a hip's ridge band implies
  depth <= width); with a fixed pitch the capped samples are counted in the notes.  Not coupled, and
  stated in the notes: span and pitch both user-confirmed / observed (sampled independently), or a
  roof that no longer reproduces its observed rise.  Twins saved before the rise was stored fall
  back to the rise of their current geometry.
* **Wall plate and FFL.**  A block whose wall-plate height was measured (`Block.observed_eaves_m`)
  and whose floor-to-floor is not user-confirmed / observed derives, per sample,
  `floor_to_floor = (plate x image scale - FFL) / storeys`: the hypotheses fold the assumed FFL range
  into the floor-to-floor, so sampling both independently would count the FFL twice and lose the
  offset between substructure and wall height.  Observed sills measured from the ground line follow
  the same rule (`bottom x image scale - FFL - storey x floor-to-floor`, clamped at 0).  Both are
  listed as derived in the notes.
* **Hidden-facade openings follow their rule, storey by storey.**  Rule-generated windows keep their
  count; the widths of each storey's rule windows scale so their glazed area tracks
  `ratio x that storey's exposed wall area - the rule doors on that storey` relative to the base
  (a wall shared in plan with a lower neighbour is exposed above the neighbour's wall plate, so the
  first floor above a single-storey extension keeps its glazing); positions scale with the wall
  length.  A storey whose base target is not positive falls back to the whole-side rule.
* An invalid sampled footprint (should not occur with the rules above) falls back to the base
  footprint for that sample and is counted in the notes.

## 4. Sampling and dependence

* One random stream per input and per group factor:
  `Generator(PCG64(SeedSequence([seed, SHA-256(stable key)])))`, keyed by the input's target
  (`rate:<id>`, `productivity:<trade>`, `block:main.depth`, ...).  `method="lhs"` draws a Latin
  hypercube column from it (a random stratum permutation plus a uniform jitter - the construction of
  `scipy.stats.qmc.LatinHypercube`); `method="mc"` plain uniforms.  Same seed -> identical samples.
* **Common random numbers.**  Because streams are keyed by input, not by column position, two build
  scenarios simulated with the same seed share the draws of every input they have in common, even
  when their input sets differ (e.g. masonry vs timber frame: paired cost-sample correlation about
  0.99 on the demo, against about 0 with positional columns).  Differences between scenario P-values
  then reflect the scenarios; each P-value is still a marginal estimate with its own sampling error.
* Gaussian copula, one-factor model per group:
  `x_i = a_g F_g + sqrt(1 - a_g^2) e_i`, `a_g = sqrt(rho_g)` (`GROUP_RHO`).  Group factors are
  correlated with `config.group_correlations` (default `unit_prices|labour_rates = 0.4`) through a
  Cholesky factor (factors in a canonical order); a non-positive-definite matrix is repaired to the
  nearest valid correlation matrix (eigenvalue clipping) and the repair is noted.  The note
  "Between-group factor correlations in force" reports the correlations of the matrix actually used,
  with the requested value where the repair changed it.
* Latents map to marginals with `scipy.stats`: uniform; triangular(low, mode, high); PERT as
  beta(1 + 4(m-a)/(b-a), 1 + 4(b-m)/(b-a)); normal (mean = value, low/high = P5/P95); lognormal
  (median = value, low/high = P5/P95).

## 5. Outputs

* `DistributionSummary` (mean, std, P5, P10, P50, P80, P90, P95, min, max) for
  `construction_incl_contingency`, `contract_sum`, `gia_m2`, `external_wall_net_m2`,
  `roof_surface_m2`, `concrete_m3`, `labour_hours`, `programme_weeks` and every block's
  `<block>.width_m` / `<block>.depth_m`; `samples` for the cost boundaries, GIA, programme weeks,
  block dimensions and the ground class index.
* `sensitivity`: Spearman rank correlation of each input with construction cost and its first-order
  variance share `Var(E[Y | bin]) / Var(Y)` by equal-count quantile binning (10-20 bins, bias
  corrected: `(SS_between - (k - 1) MS_within) / SS_total`).  Shares of inputs in a correlated
  group include effects transmitted through the shared factor.
* Group shares are built from the group's independent latent sources: each common factor once plus
  the own latent of every member without a factor (independent measurement errors such as a
  user-confirmed tolerance; every member of the rho = 0 `hidden_geometry` group).  One source is
  binned as is; several are combined by their correlation with the cost (a linear projection; exact
  for independent additive inputs) and the in-sample bias of the `p` estimated weights,
  `(p - 1)(1 - share) / n`, is subtracted.  The class is used for `ground`.  For a group with
  rho < 1 only the common factor is credited, not each member's idiosyncratic part, so its share is a
  lower bound.  Shares may sum to more than one when groups are correlated.
* `information_value`: groups ranked by variance share with the resolving action (`resolving_action`,
  of the dominant input; `group_action` is the group default; `other_actions` those of the other top
  inputs), the bootstrap standard error of the share (`variance_share_se`, 60 resamples of the rows),
  the ranks the group could take (`rank_range`) and the groups it is not distinguishable from
  (`tied_with`: share difference within two standard errors), the current P10-P90 width `W` and the
  width the group accounts for, `W (1 - sqrt(1 - share))` - the expected narrowing if it were
  resolved, under a normal approximation.
* `conditional_on_ground`: construction-cost summary per ground class (and its foundation option).

Sampling noise of the shares: `sqrt(2(k - 1)) / n` (about 1 % at n = 500 with 11 bins) is the noise
of an input **without** effect only.  For groups with real effects the seed-to-seed spread is larger:
about 2-3 percentage points at n = 500 on the demo (hidden geometry, ground, unit prices, labour
productivity and labour rates), roughly 4 points at n = 200 (it scales with 1 / sqrt(n)).  Groups
within a few points of each other can therefore swap ranks between seeds - `tied_with` /
`rank_range` say which (the bootstrap error is somewhat conservative under Latin hypercube
sampling).  Use n >= 500 for rankings and read ties as ties.  A 500-sample run on the demo twin
takes about 5-6 s.

## 6. What the intervals mean

**Assumed scenario uncertainty.**  The P-values propagate labelled engineering assumptions and
assumed ranges (scale cues and pixel errors, priors for hidden geometry, rate ranges, productivity,
waste, ground classes, lead times) through one coherent house per sample.  They are *not*
statistically calibrated against outturn costs and are not confidence intervals.  Assumed ranges
are often skewed (e.g. productivity 0.85-1.30, ground classes), so the deterministic estimate (all
inputs at their mode) usually sits below the simulated median.  With the bundled fictional rates the
distributions illustrate the method only.

## 7. Between-scenario spread (hypotheses and assemblies)

Hypothesis and assembly-selection uncertainty is kept as explicit scenarios and never sampled into
one house, so it cannot appear among the within-scenario groups.  `simulation.scenarios` reports it:

* `scenario_spread_entries(comparison)` compares, for each dimension - `hypothesis`, `construction`
  (the non-foundation assemblies), `foundation`, `price_level` - the scenarios that differ **only** in
  that dimension and reports the largest cost spread (`spread`, of the simulated P50 when every
  scenario was simulated, else of the deterministic construction cost), the low / high scenario and an
  action: *Confirm the footprint: upload a floor plan with the building outline (one box per block)
  and one measured dimension, or a side elevation, or enter the measured depth* (hypotheses),
  *Confirm the construction method / specification with the designer* (construction), a site
  investigation and engineer's design (foundation), quotations (price level).  Scenarios differing in
  several dimensions at once are not used (the spread could not be attributed).
* `combined_information_value(simulation, comparison)` ranks those entries together with the
  within-scenario groups by `impact` in money: the P10-P90 width a group accounts for, or the spread
  between scenarios.  They are different measures (narrowing one house's interval vs choosing which
  house is priced); every entry keeps its `kind` (`within_scenario` / `scenario_spread`).

On the demo (S1-S4, deterministic; fictional prices) the construction spread (masonry cavity vs
timber frame + cladding, H-A) is about GBP 7k and the hypothesis spread (H-A vs H-B, masonry) about
GBP 4k.  Against a 500-sample simulation of the base twin they rank 2nd and 5th: below hidden
geometry (about GBP 19k of P10-P90 width), level with ground conditions and unit prices, above
labour productivity and rates - which is why they belong in the same "what to resolve next" list.
