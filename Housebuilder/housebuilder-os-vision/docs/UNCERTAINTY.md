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
masonry vs timber frame) are separate `BuildScenario`s, each with its own P10/P50/P90.

## 2. Inputs and groups

| Group | Inputs (discovered, never invented) | Distribution | rho within group | Resolving action |
|---|---|---|---|---|
| `scale` | twin values with `correlation_group = "scale:<image>"`, the calibration `metres_per_pixel`, measurement errors of evidence-derived values | their own `TrackedValue` distribution | 1.0 within one image (comonotonic: one latent draw); errors without a group independent | Confirm a reference dimension such as the measured frontage |
| `hidden_geometry` | `ASSUMED` geometry (hidden depths, pitch priors, overhangs, FFL, extension sizes), hidden-facade glazing ratios, bathrooms, partition allowance | own distribution | 0.0 | Upload a side/rear elevation or a dimensioned floor plan |
| `unit_prices` | one multiplier per non-labour rate used (all foundation options) | triangular(1+low, 1, 1+high) from the rate | 0.5 | Obtain supplier quotations |
| `labour_rates` | one multiplier per `lab:<trade>` rate used | triangular(1+low, 1, 1+high) | 0.7 | Agree contractor labour rates |
| `labour_productivity` | hours multiplier per trade | triangular(0.85, 1.0, 1.30) - assumption | 0.6 | Agree a contractor programme / productivity data |
| `waste` | multiplier per material category on `waste_fraction` | triangular(0.6, 1.0, 1.8) - assumption | 0.5 | Confirm waste management plan |
| `ground` | ground class from `SimulationConfig.ground_classes` | discrete | - | Commission a site/ground investigation |
| `lead_time` | lead time of window / door / garage-door materials | the material's `lead_time_weeks` | 0.5 | Confirm window/door lead times with suppliers |

Ground classes map to foundation options: `good_clay_or_gravel` -> the selected option,
`variable_made_ground` -> `fdn_deep_trench_fill`, `poor_soft_ground` -> `fdn_piled_allowance`
(other class names: the first library option listing them in `suitable_ground`).  A user-confirmed
foundation removes the ground group.  `config.include_groups` limits the sampled groups.

Held fixed inside one simulation (stated in the result notes): storey counts, the hypothesis and
the assembly selection, library allowance quantities, take-off substructure priors (spoil bulking,
oversite dig, reinforcement) and the commercial fractions (fees, contingency, overhead, margin).

Identical prior copies (e.g. the FFL or eaves-overhang prior copied to every block) are one shared
input, because the hypothesis states one assumption for all blocks.

## 3. Coherence rules

* **Attached blocks stay attached.**  The base footprint is analysed once; every block touching an
  already placed block keeps its contact side and alignment (flush front/rear or left/right, else
  the base offset).  Their origins are derived per sample.
* **Depth-pitch coupling.**  For a gable with its ridge parallel to the frontage (or a hip) whose
  front elevation shows the roof rise (the depth or pitch carries image evidence), the rise is an
  observation: `rise = 0.5 x depth x tan(pitch)`.  An assumed depth is *derived* from the sampled
  pitch prior, `depth = rise / (0.5 tan(pitch))`, clipped to the depth range; an evidence-derived
  depth is sampled and the pitch derived.  The rise scales with the sampled `metres_per_pixel` of
  its image.  When both depth and pitch are evidence (a side view), both are sampled independently.
* **Hidden-facade openings follow their rule.**  Rule-generated windows keep their count; their
  widths scale so the glazed area tracks `ratio x hidden wall area - rule doors` relative to the
  base, positions scale with the wall length.
* An invalid sampled footprint (should not occur with the rules above) falls back to the base
  footprint for that sample and is counted in the notes.

## 4. Sampling and dependence

* `method="lhs"`: `scipy.stats.qmc.LatinHypercube(d, rng=PCG64(seed))` on the independent
  normal drivers; `method="mc"`: `numpy.random.Generator(PCG64(seed))`.  Same seed -> identical
  samples.
* Gaussian copula, one-factor model per group:
  `x_i = a_g F_g + sqrt(1 - a_g^2) e_i`, `a_g = sqrt(rho_g)` (`GROUP_RHO`).  Group factors are
  correlated with `config.group_correlations` (default `unit_prices|labour_rates = 0.4`) through a
  Cholesky factor; a non-positive-definite matrix is repaired to the nearest valid correlation
  matrix (eigenvalue clipping) and the repair is noted.
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
* Group shares use the group's latent factor (one common factor), the class for `ground`, otherwise
  the correlation-weighted sum of the group's latents (a linear projection; exact for independent
  additive inputs).  Shares may sum to more than one when groups are correlated.
* `information_value`: groups ranked by variance share with the resolving action, the current
  P10-P90 width `W` and the width the group accounts for, `W (1 - sqrt(1 - share))` - the expected
  narrowing if it were resolved, under a normal approximation.
* `conditional_on_ground`: construction-cost summary per ground class (and its foundation option).

The binned estimator has sampling noise of roughly `sqrt(2(k - 1)) / n` on each share (about 1 %
at n = 500 with 11 bins, 3 % at n = 160); use n >= 500 for rankings.  A 500-sample run on the demo
twin takes about 5 s.

## 6. What the intervals mean

**Assumed scenario uncertainty.**  The P-values propagate labelled engineering assumptions and
assumed ranges (scale cues and pixel errors, priors for hidden geometry, rate ranges, productivity,
waste, ground classes, lead times) through one coherent house per sample.  They are *not*
statistically calibrated against outturn costs and are not confidence intervals.  Assumed ranges
are often skewed (e.g. productivity 0.85-1.30, ground classes), so the deterministic estimate (all
inputs at their mode) usually sits below the simulated median.  With the bundled fictional rates the
distributions illustrate the method only.
