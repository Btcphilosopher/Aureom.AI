"""
Configurable battery-chemistry profiles (spec item 3).

Every numeric field here is a *model assumption* (see
``datamodel.models.DataProvenance``) drawn from public engineering ranges
for the named chemistry family -- not a certified datasheet for any real
product. They exist so the rest of the platform (formation recipes, EOL
test thresholds, thermal models, cost engine) has something concrete and
*configurable* to compute against, instead of hard-coding one factory
design. Users can clone a profile and override any field.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from batteryfactory.datamodel.models import Chemistry, DataProvenance


@dataclass
class ChemistryProfile:
    chemistry: Chemistry
    nominal_voltage_v: float
    capacity_ah_reference: float           # reference cell capacity used for %-based test bands
    energy_density_wh_kg: float
    energy_density_wh_l: float
    material_composition_pct: dict[str, float]
    target_operating_temp_c: tuple[float, float]      # (min, max)
    thermal_runaway_onset_c: float
    max_charge_c_rate: float
    max_discharge_c_rate: float
    formation_voltage_window_v: tuple[float, float]
    expected_cycle_life_80pct: int
    coating_areal_density_target_mg_cm2: float
    self_discharge_pct_per_month: float
    provenance: DataProvenance = field(default=DataProvenance.MODEL_ASSUMPTION)

    def clone(self, **overrides) -> "ChemistryProfile":
        return replace(self, **overrides)


CHEMISTRY_PROFILES: dict[Chemistry, ChemistryProfile] = {
    Chemistry.LFP: ChemistryProfile(
        chemistry=Chemistry.LFP,
        nominal_voltage_v=3.2,
        capacity_ah_reference=100.0,
        energy_density_wh_kg=160.0,
        energy_density_wh_l=350.0,
        material_composition_pct={"LiFePO4": 96.0, "graphite": 95.0, "binder": 2.5, "conductive_additive": 1.5},
        target_operating_temp_c=(15.0, 35.0),
        thermal_runaway_onset_c=270.0,
        max_charge_c_rate=1.0,
        max_discharge_c_rate=2.0,
        formation_voltage_window_v=(2.5, 3.65),
        expected_cycle_life_80pct=4000,
        coating_areal_density_target_mg_cm2=18.0,
        self_discharge_pct_per_month=2.0,
    ),
    Chemistry.NMC: ChemistryProfile(
        chemistry=Chemistry.NMC,
        nominal_voltage_v=3.65,
        capacity_ah_reference=75.0,
        energy_density_wh_kg=240.0,
        energy_density_wh_l=600.0,
        material_composition_pct={"LiNiMnCoO2": 95.5, "graphite": 95.0, "binder": 2.5, "conductive_additive": 2.0},
        target_operating_temp_c=(10.0, 40.0),
        thermal_runaway_onset_c=210.0,
        max_charge_c_rate=1.5,
        max_discharge_c_rate=3.0,
        formation_voltage_window_v=(2.8, 4.2),
        expected_cycle_life_80pct=2000,
        coating_areal_density_target_mg_cm2=22.0,
        self_discharge_pct_per_month=2.5,
    ),
    Chemistry.NCA: ChemistryProfile(
        chemistry=Chemistry.NCA,
        nominal_voltage_v=3.6,
        capacity_ah_reference=75.0,
        energy_density_wh_kg=260.0,
        energy_density_wh_l=680.0,
        material_composition_pct={"LiNiCoAlO2": 95.5, "graphite": 95.0, "binder": 2.5, "conductive_additive": 2.0},
        target_operating_temp_c=(10.0, 40.0),
        thermal_runaway_onset_c=195.0,
        max_charge_c_rate=1.5,
        max_discharge_c_rate=3.5,
        formation_voltage_window_v=(2.8, 4.2),
        expected_cycle_life_80pct=1800,
        coating_areal_density_target_mg_cm2=21.0,
        self_discharge_pct_per_month=2.5,
    ),
    Chemistry.LMFP: ChemistryProfile(
        chemistry=Chemistry.LMFP,
        nominal_voltage_v=3.4,
        capacity_ah_reference=90.0,
        energy_density_wh_kg=195.0,
        energy_density_wh_l=430.0,
        material_composition_pct={"LiMnFePO4": 96.0, "graphite": 95.0, "binder": 2.5, "conductive_additive": 1.5},
        target_operating_temp_c=(15.0, 35.0),
        thermal_runaway_onset_c=250.0,
        max_charge_c_rate=1.2,
        max_discharge_c_rate=2.5,
        formation_voltage_window_v=(2.5, 4.0),
        expected_cycle_life_80pct=3200,
        coating_areal_density_target_mg_cm2=19.0,
        self_discharge_pct_per_month=2.0,
    ),
    Chemistry.NA_ION: ChemistryProfile(
        chemistry=Chemistry.NA_ION,
        nominal_voltage_v=3.1,
        capacity_ah_reference=60.0,
        energy_density_wh_kg=125.0,
        energy_density_wh_l=280.0,
        material_composition_pct={"NaFeMnO2_or_prussian_analog": 93.0, "hard_carbon": 92.0, "binder": 3.0, "conductive_additive": 2.0},
        target_operating_temp_c=(-10.0, 45.0),
        thermal_runaway_onset_c=290.0,
        max_charge_c_rate=1.0,
        max_discharge_c_rate=2.0,
        formation_voltage_window_v=(1.5, 4.0),
        expected_cycle_life_80pct=3000,
        coating_areal_density_target_mg_cm2=16.0,
        self_discharge_pct_per_month=3.0,
    ),
}


def get_profile(chemistry: Chemistry) -> ChemistryProfile:
    return CHEMISTRY_PROFILES[chemistry]
