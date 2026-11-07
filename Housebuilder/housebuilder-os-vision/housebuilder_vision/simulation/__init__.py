"""Digital simulations on the parametric twin (indicative, concept-stage).

* :mod:`.thermal` - ISO 6946-style U-values, ISO 13370 ground floors and a simplified
  steady-state heat-loss coefficient (not SAP / SBEM / PHPP; no compliance claim).
* :mod:`.carbon` - indicative A1-A3 (+ A5 waste share, optional A4) embodied carbon from
  the BoQ with illustrative placeholder factors.
* :mod:`.programme` - indicative task network and critical path (not a validated programme).
* :mod:`.logistics` - delivery batches, loads, order-by days, storage peak, waste skips.
* :mod:`.adapters` - protocols for connecting detailed structural / energy / carbon-data
  tools later (defaults raise :class:`AdapterNotConfigured`).
* :mod:`.uncertainty` - Latin-hypercube / Monte Carlo simulation of one coherent house
  (assumed scenario uncertainty, sensitivity, value of information).
* :mod:`.scenarios` - side-by-side build scenarios, each one coherent house (no averaging).
"""

from .adapters import (
    AdapterNotConfigured,
    CarbonFactor,
    EmbodiedCarbonDataAdapter,
    EnergyAnalysisAdapter,
    EnergyAnalysisReport,
    EngineeringAdapters,
    NotConfiguredCarbonDataAdapter,
    NotConfiguredEnergyAdapter,
    NotConfiguredStructuralAdapter,
    StaticCarbonFactorAdapter,
    StructuralAnalysisAdapter,
    StructuralAnalysisReport,
    apply_carbon_factors,
    default_engineering_adapters,
)
from .carbon import embodied_carbon, installed_mass_per_unit
from .logistics import plan_deliveries
from .programme import (
    TASK_DEFINITIONS,
    assign_lines_to_tasks,
    build_programme,
    critical_path_method,
    material_lead_time_weeks,
)
from .thermal import ThermalDataError, ground_floor_u, heat_loss, is_ventilated_layer, u_value
from .uncertainty import (
    GROUP_RHO,
    GROUPS,
    RESOLVING_ACTIONS,
    binned_variance_share,
    discover_inputs,
    simulate_uncertainty,
    summarize,
)
from .scenarios import (
    DEFAULT_SCENARIO_SAMPLES,
    ScenarioEvaluation,
    combined_information_value,
    compare_build_scenarios,
    evaluate_build_scenario,
    scale_rate_book,
    scenario_spread_entries,
)
from .uncertainty import input_action

__all__ = [
    "DEFAULT_SCENARIO_SAMPLES", "combined_information_value", "scenario_spread_entries", "input_action",
    "AdapterNotConfigured", "CarbonFactor", "EmbodiedCarbonDataAdapter", "EnergyAnalysisAdapter",
    "EnergyAnalysisReport", "EngineeringAdapters", "NotConfiguredCarbonDataAdapter", "NotConfiguredEnergyAdapter",
    "NotConfiguredStructuralAdapter", "StaticCarbonFactorAdapter", "StructuralAnalysisAdapter",
    "StructuralAnalysisReport", "apply_carbon_factors", "default_engineering_adapters",
    "embodied_carbon", "installed_mass_per_unit",
    "plan_deliveries",
    "TASK_DEFINITIONS", "assign_lines_to_tasks", "build_programme", "critical_path_method",
    "material_lead_time_weeks",
    "ThermalDataError", "ground_floor_u", "heat_loss", "is_ventilated_layer", "u_value",
    "GROUP_RHO", "GROUPS", "RESOLVING_ACTIONS", "binned_variance_share", "discover_inputs", "simulate_uncertainty",
    "summarize",
    "ScenarioEvaluation", "compare_build_scenarios", "evaluate_build_scenario", "scale_rate_book",
]
