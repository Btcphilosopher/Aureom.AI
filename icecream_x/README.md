# ICECREAM-X

A physics-informed ice cream manufacturing simulator and digital twin,
written in Python 3.13+.

ICECREAM-X is **not a recipe calculator**. It models an ice cream product
as a multi-phase thermodynamic food system (water, fat, milk-solids-non-fat,
sugars, proteins, stabilisers, emulsifiers, air, ice) whose state evolves
through the full manufacturing chain:

```
FORMULATION -> MIXING -> PASTEURISATION -> HOMOGENISATION -> AGEING
    -> FREEZING -> AIR INCORPORATION -> HARDENING -> COLD STORAGE
    -> DISTRIBUTION -> FINAL PRODUCT
```

## Quick start

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python -m icecream_x.main --recipe vanilla --storage-days 14
python -m icecream_x.main --list-recipes

pytest icecream_x/tests
uvicorn icecream_x.api.server:app --reload   # optional HTTP API
```

## Architecture

| Layer | Purpose |
|---|---|
| `formulation/` | Ingredients, composition/mass-balance, recipes |
| `thermodynamics/` | Freezing-point depression, ice fraction, enthalpy, Choi-Okos heat capacity/conductivity |
| `rheology/` | Viscosity (Krieger-Dougherty + serum thickening), shear-thinning, pipe flow |
| `equipment/` | Pasteuriser, homogeniser, heat exchanger, freezer, hardening tunnel |
| `processing/` | Mixing, pasteurisation, homogenisation, ageing, freezing, aeration, hardening |
| `microstructure/` | Ice crystals, air cells, fat network, unified `MicrostructureState` |
| `storage/` | Temperature histories, cold-chain simulation, recrystallisation |
| `core/` | `ProductState`, the production-line engine, and the generic timestep simulation loop |
| `economics/` | Ingredient/energy/manufacturing cost, unit economics |
| `analytics/` | Quality index, energy/production analytics, Monte Carlo statistics |
| `optimisation/` | Formulation/process/freezer/energy/quality optimisers (SciPy) |
| `digital_twin/` | Telemetry, state estimation, calibration, the `DigitalTwin` object |
| `scenarios/` | Example recipes, process profiles, storage profiles, experiments |
| `visualisation/` | Plotly dashboard and individual chart builders |
| `database/` | Optional SQLAlchemy persistence (never required by the engine) |
| `api/` | Optional FastAPI HTTP interface |

## Physical model notes

Every non-trivial physical model in this codebase documents, in its own
module docstring, exactly which assumptions it makes and where a more
sophisticated model should be substituted. The most important ones:

- **Freezing point / ice fraction** (`thermodynamics/freezing_point.py`,
  `ice_fraction.py`): ideal-solution (Raoult's law / van't Hoff) colligative
  freezing-point depression, with a closed-form freezing curve derived from
  conservation of solute moles. Known to under-predict depression at the
  sugar concentrations typical of ice cream mix; documented as the
  intentional baseline.
- **Heat capacity / thermal conductivity / density**
  (`thermodynamics/heat_capacity.py`, `thermal_conductivity.py`): the
  published Choi & Okos (1986) food-component correlations.
- **Enthalpy / apparent specific heat** (`thermodynamics/enthalpy.py`):
  the standard "apparent specific heat method" for simulating heat transfer
  through a phase change, integrated once into a fast interpolation table
  (`EnthalpyTable`) per process step for both speed and numerical stability.
- **Viscosity** (`rheology/viscosity.py`): Krieger-Dougherty suspension
  viscosity for the fat+ice dispersed phase, layered on an Arrhenius/VFT
  serum viscosity with empirical sugar/stabiliser thickening terms.
- **Ice crystals / recrystallisation**
  (`microstructure/ice_crystals.py`): empirical nucleation-size-vs-freezing-
  rate power law, and LSW-type cube-law Ostwald-ripening kinetics during
  storage, accelerated by temperature and temperature cycling.
- **Quality score** (`analytics/quality.py`): an explicitly-labelled
  engineering proxy, not a validated sensory model -- see its docstring.

All such constants are grouped at module level specifically so they can be
recalibrated against real plant/lab data via
`icecream_x.digital_twin.calibration` without restructuring the models.

## Numerical approach

Temperature is never integrated directly through the freezing point (where
apparent specific heat spikes sharply); every thermal process step
integrates **specific enthalpy** instead (`core/timestep.py`) and inverts to
temperature only when needed, which is what makes the freezer/hardening
tunnel simulations stable across the ice-fraction phase transition.

## Tests

`icecream_x/tests` covers mass conservation, monotonicity of the freezing
curve and enthalpy, unit-conversion round-trips, numerical stability of the
enthalpy stepper, storage-excursion vs. uninterrupted-storage crystal
growth, and end-to-end pipeline smoke tests.
