# SILICAFLUX PV SPECTRAL

A modular, deterministic Python simulation and optimisation engine for
**photovoltaic UV/visible/NIR spectral response** -- solar spectrum and
atmosphere, front-surface optics, semiconductor absorption, quantum
efficiency, recombination, single-diode electrical conversion, thermal
behaviour, UV degradation, tandem architectures, and a machine-learning
optimisation layer, all wired into one pipeline so that every reported
number (efficiency, UV power fraction, annual energy, degradation rate)
**emerges from the simulation** rather than being assumed up front.

This is a computational research/design tool, not a manufacturing system:
it simulates, optimises and explores PV architectures digitally.

The central question it answers, for a given solar spectrum and PV cell
architecture:

1. **How much UV energy can the cell actually convert?**
2. **Where is that UV energy being lost?**
3. **Which material / optical / semiconductor changes would increase
   useful UV response?**
4. **Do those changes increase total *lifetime* electrical energy output
   -- not just UV absorption?**

## Why nothing is hard-coded

* **The atmosphere is a real filter**, not a fudge factor: extraterrestrial
  irradiance is generated from Planck's law for a 5778 K blackbody sun,
  then attenuated by a clear-sky model (Rayleigh scattering, ozone
  Hartley/Huggins/Chappuis absorption, water vapour, aerosol Angstrom
  turbidity, mixed-gas bands) with an explicit direct/diffuse split -- UVB
  really does come out far more attenuated than UVA, which comes out more
  attenuated than visible/NIR, because that's what the physics gives.
* **Front-surface optics** are a genuine transfer-matrix (characteristic
  matrix) calculation over an anti-reflection coating and encapsulant
  stack terminating on a complex-refractive-index semiconductor substrate
  -- R + T + A = 1 to floating-point precision, checked in tests. The
  encapsulant models a real, well-documented effect: conventional
  UV-stabilised EVA is strongly absorbing below ~360-380 nm, which is why
  standard silicon modules have almost no UV response even though silicon
  itself absorbs deep-UV photons extremely well -- switching to a
  UV-transparent encapsulant (POE, or UV-transmitting EVA) is the single
  highest-leverage lever this engine finds for UV response, and its
  optimiser rediscovers this on its own every time.
* **Absorption coefficients** follow real Tauc band-edge relations (direct
  vs indirect), an Urbach sub-gap tail, and a deep-UV interband-transition
  boost (virtually every semiconductor's absorption coefficient climbs
  toward ~10^5-10^6 cm^-1 in the deep UV, regardless of its fundamental
  gap's character) -- so UV photons really are absorbed within tens of
  nanometres of the front surface, which is exactly what makes front-
  surface recombination disproportionately costly for UV response.
* **EQE/IQE** fold in a real recombination model (radiative + SRH + Auger
  + surface, combined by Matthiessen's rule) and a phenomenological but
  correctly-behaved surface-recombination penalty built from the
  generation-depth-vs-diffusion-length reach probability and the standard
  dimensionless `S*L/D` surface "sink strength" group.
* **Electrical output** is an exact closed-form single-diode
  maximum-power-point solve (Lambert-W), so Voc/Vmp/fill factor emerge
  from the actual simulated short-circuit current and the material's
  Varshni-shifted bandgap at the actual cell temperature -- not a flat
  percentage.
* **Cell temperature** comes from a Faiman heat-balance model
  (ambient + irradiance/(U0 + U1*wind)), and that temperature genuinely
  propagates through Eg(T), the dark saturation current, and carrier
  lifetime.
* **Tandem cells** are solved as real series-connected two-terminal
  devices: sweep a shared operating current, sum each subcell's voltage at
  that current (inverting its diode equation) -- current mismatch between
  subcells is a real, visible penalty on device power, not a bolt-on
  correction.
* **The ML layer** is a deterministic closed-form ridge regression trained
  on real physics-simulated data, and its recommendation is only ever
  reported after being validated against a real physics evaluation --
  never a raw, unverified prediction.

## Honesty note on material constants

Per-material parameters in `materials.py` (absorption prefactors, Urbach
energies, surface recombination velocities, carrier lifetimes, Varshni
coefficients, ...) are illustrative, physically-motivated defaults
representative of literature-typical orders of magnitude for each material
family. They are **not** fitted to any specific measured device or
datasheet. What's guaranteed to be physically consistent is the *model
form* connecting them (Tauc relations, Beer-Lambert absorption, Matthiessen
recombination, the diode equation, Varshni shift, the Faiman thermal
model): swap in measured constants for a real device and every downstream
number updates consistently. Likewise the atmospheric model is a
simplified clear-sky approximation (in the spirit of Bird & Hulstrom 1981),
not a line-by-line radiative-transfer code -- it gets the *qualitative*
UV/visible/NIR attenuation pattern right without claiming ASTM-G173-grade
absolute accuracy.

## Install

```bash
pip install -r requirements.txt
# optional: pip install matplotlib   # spectral graph rendering
# optional: pip install pandas       # convenient sweep-table post-processing
```

## Quick start

```bash
# Baseline pipeline evaluation
python -m silicaflux_pv_spectral.main --material SILICON --mode baseline

# Baseline vs optimised comparison report
python -m silicaflux_pv_spectral.main --material PEROVSKITE --mode report

# Full SILICAFLUX.PV.SPECTRAL.OPTIMISE, with machine-readable JSON output
python -m silicaflux_pv_spectral.main --material SILICON --mode optimise --json-out result.json

# Tandem architecture (bandgap/thickness co-optimised, current-matching reported)
python -m silicaflux_pv_spectral.main --material SILICON --mode optimise --architecture tandem

# Ranked parameter sweep
python -m silicaflux_pv_spectral.main --material CIGS --mode sweep --max-sweep-configs 500

# Render the seven spectral graphs (requires matplotlib)
python -m silicaflux_pv_spectral.main --material SILICON --plot-dir plots/
```

Or drive it directly from Python:

```python
from silicaflux_pv_spectral import SILICAFLUX, MATERIAL_LIBRARY, terrestrial_spectrum, run_pipeline

spectrum = terrestrial_spectrum()                       # AM0 blackbody spectrum x atmospheric transmission
material = MATERIAL_LIBRARY["SILICON"]

baseline = run_pipeline(spectrum, material)              # full 15-stage physics pipeline
print(baseline.efficiency, baseline.spectral_response.uv_power_fraction)

result = SILICAFLUX.PV.SPECTRAL.OPTIMISE(spectrum, material)   # front-surface + encapsulant optimiser
print(result.optimised_parameters, result.predicted_energy_gain)
```

Or explore a digital twin interactively:

```python
from silicaflux_pv_spectral import PVCellDigitalTwin, MATERIAL_LIBRARY, terrestrial_spectrum

twin = PVCellDigitalTwin(material=MATERIAL_LIBRARY["SILICON"], spectrum=terrestrial_spectrum())
twin.set_parameter("encapsulant_uv_blocking", False)      # swap to a UV-transparent encapsulant
twin.set_parameter("bandgap_eV", 1.3)                      # or dial in any material property
print(twin.summary())                                      # recomputed lazily, on first access after a change
```

## The pipeline

```
SOLAR SPECTRUM (Planck blackbody, 280-2500 nm, 1 nm grid)
      |
ATMOSPHERIC MODEL (Rayleigh + ozone + water vapour + aerosol + mixed-gas Beer-Lambert)
      |
PHOTON ENERGY / FLUX  (E = hc/lambda; flux = irradiance / E)
      |
OPTICAL STACK  (transfer-matrix AR coating + encapsulant -> R(lambda), T(lambda))
      |
UV / VISIBLE / NIR ABSORPTION  (Beer-Lambert within the absorber, Tauc + Urbach + deep-UV boost alpha(lambda))
      |
QUANTUM EFFICIENCY  (EQE = optical absorption x IQE; IQE = ceiling x bulk collection x (1 - surface loss))
      |
CARRIER GENERATION / RECOMBINATION  (radiative + SRH + Auger + surface, Matthiessen's rule)
      |
CARRIER COLLECTION  (diffusion-length-vs-thickness bulk collection efficiency)
      |
ELECTRICAL CONVERSION  (single-diode Lambert-W closed-form Voc/Vmp/fill-factor solve)
      |
THERMAL MODEL  (Faiman cell temperature -> Varshni Eg(T) -> dark saturation current -> Voc)
      |
DEGRADATION MODEL  (Arrhenius UV-dose-driven degradation rate -> lifetime energy loss)
      |
MACHINE LEARNING  (ridge-regression surrogate over a physics-generated parameter sweep)
      |
SILICAFLUX OPTIMISER  (front-surface + encapsulant search, tandem bandgap/thickness search)
      |
OPTIMISED PV CELL
```

Machine learning and the top-level optimiser are not literal pipeline
*stages* run on every call -- they are search processes built on top of
repeated pipeline evaluations (see `pipeline.py`'s module docstring).

## Package layout

```
silicaflux_pv_spectral/
    constants.py          physical constants, wavelength grid, spectral bands
    spectrum.py            SolarSpectrum, Planck blackbody AM0 spectrum, atmospheric transmission model
    photon.py                photon energy / flux
    materials.py               PVMaterial, MATERIAL_LIBRARY (6 materials + tandem-top variant), Tauc absorption, Varshni
    optics.py                    transfer-matrix optical stack, UV absorption engine, front-surface optimiser
    recombination.py               radiative / SRH / Auger / surface recombination -> carrier lifetime
    response.py                      EQE / IQE, single-diode Lambert-W power conversion
    spectral_converter.py             UV down-shifting layer, full-loss-accounted conversion gain
    tandem.py                          series-connected two-terminal tandem cell + optimiser
    degradation.py                       UV/thermal Arrhenius degradation model, lifetime energy loss
    thermal.py                            Faiman cell temperature model
    pipeline.py                            full end-to-end orchestration
    ml_optimiser.py                          ridge-regression surrogate, physics-validated recommendations
    parameter_sweep.py                        ranked configuration sweep
    engine.py                                  SILICAFLUX.PV.SPECTRAL.OPTIMISE, RESULT, SIMULATION_OUTPUT
    digital_twin.py                              mutable PVCellDigitalTwin, lazy recompute
    graphs.py                                     spectral graph data (+ optional matplotlib rendering)
    io_utils.py                                    JSON-serialise any result (dataclasses + numpy arrays)
    main.py                                          CLI
    tests/                                            one test module per source module
examples/
    baseline_report.py        every material in the library, one-line summary each
    optimise_and_compare.py     full baseline/optimise/sweep/ML-surrogate walkthrough for silicon
```

## Testing

```bash
pytest
```

Tests assert physics sanity properties rather than pinned magic numbers
wherever possible: energy conservation (R+T+A=1), monotonicity (more
diffusion length -> better collection; higher temperature -> lower Voc;
more UV-transparent encapsulant -> more UV power), and known limiting
cases (Fresnel reflectance at normal incidence, zero-degradation-rate
means zero lifetime loss, a series tandem's Voc exceeds either subcell's
alone). Everything is deterministic -- no random seeds anywhere in the
physics or optimisation code -- so a test failure means something in the
model actually changed.
