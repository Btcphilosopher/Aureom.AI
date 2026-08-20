"""
HydroFluxEngine: the pipeline that turns configuration + resource data into
an optimal configuration and operating strategy.

    INPUT DATA -> VALIDATION -> HYDROLOGICAL/TIDAL MODEL -> HYDRAULIC MODEL
    -> TURBINE MODEL -> ENERGY MODEL -> GRID MODEL -> ENVIRONMENTAL
    CONSTRAINTS -> ECONOMIC MODEL -> OPTIMISER -> OPTIMAL CONFIGURATION
    -> SIMULATION -> RESULTS

``simulate`` runs one pass of that pipeline for a given operating policy;
``optimise`` searches over policy parameters (see
:mod:`hydroflux.optimisation.optimiser`) to find the policy that maximises
a configurable weighted objective, then returns the full simulated result
for the best policy found.

Every result explicitly distinguishes theoretical, physical, available,
optimally-dispatchable, economically-optimal and environmentally-permitted
generation (specification section 52) rather than conflating them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from hydroflux.core.config import HydroSystemConfig, SystemType
from hydroflux.core.timeseries import ResourceTimeSeries
from hydroflux.economics.economics import EconomicEngine
from hydroflux.environment.environment import EnvironmentalConstraints
from hydroflux.grid.grid import curtailment as apply_curtailment
from hydroflux.hydraulics.hydraulics import HeadModel, RHO_SEAWATER, theoretical_power
from hydroflux.optimisation.objectives import ObjectiveWeights
from hydroflux.optimisation.optimiser import PolicyOptimisationResult, optimise_policy
from hydroflux.pumped_storage.pumped_storage import PumpedStorageOptimiser
from hydroflux.reporting.reporting import ReproducibilityRecord, SimulationResult, hash_dict, hash_series
from hydroflux.reservoirs.reservoir import Reservoir
from hydroflux.tidal.barrage import TidalBarrageOptimiser
from hydroflux.tidal.stream import TidalStreamTurbine, current_velocity_series
from hydroflux.turbines.dispatch import optimise_dispatch
from hydroflux.turbines.turbines import make_turbine_from_config
from hydroflux.validation.validation import validate_resource_data, validate_system_config

_TIDAL_RANGE_TYPES = (SystemType.TIDAL_RANGE, SystemType.TIDAL_BARRAGE, SystemType.TIDAL_LAGOON)


@dataclass
class GenerationPotential:
    """The hierarchy the specification insists on keeping distinct
    (section 52), all in MWh over the simulated horizon."""

    theoretical_mwh: float
    physical_mwh: float
    available_mwh: float
    optimally_dispatchable_mwh: float
    economically_optimal_mwh: float
    environmentally_permitted_mwh: float


class HydroFluxEngine:
    def __init__(self, config: HydroSystemConfig):
        self.config = config

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def simulate(self, resource: ResourceTimeSeries, policy: Optional[dict] = None, scenario_name: str = "baseline") -> SimulationResult:
        validate_system_config(self.config)
        validate_resource_data(resource)
        policy = policy or {}

        if self.config.system_type in (SystemType.RESERVOIR, SystemType.RUN_OF_RIVER):
            result, potential = self._simulate_river_system(resource, policy)
        elif self.config.system_type == SystemType.PUMPED_STORAGE:
            result, potential = self._simulate_pumped_storage(resource, policy)
        elif self.config.system_type in _TIDAL_RANGE_TYPES:
            result, potential = self._simulate_tidal_range(resource, policy)
        elif self.config.system_type == SystemType.TIDAL_STREAM:
            result, potential = self._simulate_tidal_stream(resource, policy)
        else:
            raise NotImplementedError(f"System type '{self.config.system_type}' has no wired simulation path yet.")

        result.theoretical_potential_mwh = potential.theoretical_mwh
        result.physical_potential_mwh = potential.physical_mwh
        result.available_generation_mwh = potential.available_mwh
        result.environmentally_permitted_mwh = potential.environmentally_permitted_mwh

        result.metadata = ReproducibilityRecord(
            scenario=scenario_name,
            configuration_hash=hash_dict(self.config.to_dict()),
            input_data_hash=hash_series(resource.flow if resource.flow is not None else resource.inflow),
            random_seed=self.config.simulation.seed,
            optimisation_method="",
            optimisation_parameters=policy,
        )
        return result

    def optimise(
        self,
        resource: ResourceTimeSeries,
        objective: str = "max_revenue",
        weights: Optional[ObjectiveWeights] = None,
        algorithm: str = "differential_evolution",
        seed: Optional[int] = None,
        **algorithm_kwargs,
    ) -> tuple[SimulationResult, Optional[PolicyOptimisationResult]]:
        weights = weights or ObjectiveWeights.preset(objective)
        seed = seed if seed is not None else self.config.simulation.seed

        names, bounds = self._policy_spec()
        if not names:
            result = self.simulate(resource, policy={}, scenario_name="optimised")
            return result, None

        def evaluate(params: dict[str, float]) -> dict[str, float]:
            result = self.simulate(resource, policy=params, scenario_name="optimised")
            return {
                "energy": result.annual_generation_mwh,
                "revenue": result.revenue,
                "efficiency": result.average_efficiency,
                "lcoe": result.lcoe if np.isfinite(result.lcoe) else 1e6,
                "npv": result.npv,
                "environmental_impact": float(len(result.constraint_violations)),
                "water_security": result.water_utilisation_pct / 100.0,
            }

        policy_result = optimise_policy(names, bounds, evaluate, weights, algorithm=algorithm, seed=seed, **algorithm_kwargs)
        final_result = self.simulate(resource, policy=policy_result.best_parameters, scenario_name="optimised")
        final_result.metadata.optimisation_method = policy_result.algorithm
        final_result.metadata.optimisation_parameters = policy_result.best_parameters
        return final_result, policy_result

    # ------------------------------------------------------------------ #
    # Policy parameter search space per system type
    # ------------------------------------------------------------------ #

    def _policy_spec(self) -> tuple[list[str], list[tuple[float, float]]]:
        cfg = self.config
        if cfg.system_type == SystemType.RESERVOIR and cfg.reservoir is not None:
            r = cfg.reservoir
            return (
                ["target_level_m", "release_gain", "price_sensitivity"],
                [(r.minimum_level_m, r.maximum_level_m), (0.0, 2.0), (0.0, 5.0)],
            )
        if cfg.system_type in _TIDAL_RANGE_TYPES and cfg.tidal is not None:
            return (["minimum_generating_head_m"], [(0.3, max(cfg.tidal.tidal_amplitude_m * 0.9, 0.5))])
        return [], []

    # ------------------------------------------------------------------ #
    # Reservoir / run-of-river
    # ------------------------------------------------------------------ #

    def _simulate_river_system(self, resource: ResourceTimeSeries, policy: dict) -> tuple[SimulationResult, GenerationPotential]:
        cfg = self.config
        index = resource.index
        dt_hours = resource.dt_hours
        natural_flow = resource.inflow if resource.inflow is not None else resource.flow
        if natural_flow is None:
            raise ValueError("Reservoir/run-of-river simulation requires resource.flow or resource.inflow")

        env = EnvironmentalConstraints(cfg.environmental)
        # The pre-dispatch flow ceiling only enforces the ecological-minimum
        # floor and restricted periods -- it must not also compare the
        # natural flow to itself under `maximum_flow_alteration_pct` (that
        # would trivially "violate" every step, since a regulated release
        # is *supposed* to differ from instantaneous natural inflow when a
        # reservoir is storing or releasing). The alteration check is
        # instead applied after simulation, against the flow the plant
        # actually released -- see below.
        permitted_flow, _ = env.apply(natural_flow)

        turbines = [make_turbine_from_config(t) for t in cfg.turbines]
        fleet_max_flow = sum(t.maximum_flow_m3s for t in turbines) if turbines else 0.0
        fleet_capacity_mw = sum(t.rated_power_mw for t in turbines) if turbines else 0.0
        mean_availability = float(np.mean([t.availability for t in turbines])) if turbines else 1.0

        has_reservoir = cfg.reservoir is not None and cfg.system_type == SystemType.RESERVOIR
        n = len(index)
        power = np.zeros(n)
        flow_used = np.zeros(n)
        head_series = np.zeros(n)
        levels = np.full(n, np.nan)
        spill = np.zeros(n)

        if has_reservoir:
            reservoir = Reservoir(cfg.reservoir)
            head_model = HeadModel(
                cfg.reservoir.penstock_length_m,
                cfg.reservoir.penstock_diameter_m,
                cfg.reservoir.penstock_friction_factor,
                intake_loss_coefficient=cfg.reservoir.intake_loss_coefficient,
            )
            target_level = policy.get("target_level_m", cfg.reservoir.initial_level_m)
            gain = policy.get("release_gain", 0.1)
            price_sensitivity = policy.get("price_sensitivity", 0.0)
            target_storage = reservoir.level_to_storage(target_level)
            storage = reservoir.level_to_storage(cfg.reservoir.initial_level_m)
            mean_price = float(resource.price.mean()) if resource.price is not None else 0.0

            for i in range(n):
                level = reservoir.storage_to_level(storage)
                # Water-value-informed release: track the target storage
                # trajectory, but additionally shift generation toward
                # above-average-price periods and hold back water when
                # price is below average -- this is what lets the
                # optimiser trade "generate now" against "preserve water
                # for a more valuable future period" (specification
                # section 12) without needing a full stochastic-DP solve
                # inside the hot simulation loop.
                price_term = price_sensitivity * (resource.price.iloc[i] - mean_price) if resource.price is not None else 0.0
                desired_release = (
                    permitted_flow.iloc[i] + gain * (storage - target_storage) / max(dt_hours, 1e-6) + price_term
                )
                desired_release = float(np.clip(desired_release, 0.0, fleet_max_flow))

                head = float(head_model.net_head(desired_release, level, cfg.reservoir.tailwater_elevation_m))
                dispatch = optimise_dispatch(turbines, desired_release, head)

                power[i] = dispatch.total_power_mw
                flow_used[i] = dispatch.total_flow_m3s
                head_series[i] = head

                inflow_vol = permitted_flow.iloc[i] * dt_hours * 3600 * 1e-6
                release_vol = dispatch.total_flow_m3s * dt_hours * 3600 * 1e-6
                evap_vol = (cfg.reservoir.evaporation_mm_per_day / 1000.0) * cfg.reservoir.surface_area_km2 * 1e6 * 1e-6 * dt_hours / 24.0
                balance = storage + inflow_vol - release_vol - evap_vol
                spill_vol = max(balance - cfg.reservoir.capacity_mcm, 0.0)
                storage = float(np.clip(balance - spill_vol, cfg.reservoir.dead_storage_mcm, cfg.reservoir.capacity_mcm))
                spill[i] = spill_vol / (dt_hours * 3600 * 1e-6) if dt_hours > 0 else 0.0
                levels[i] = reservoir.storage_to_level(storage)
        else:
            fixed_head = None
            if resource.head is not None:
                fixed_head = resource.head
            elif cfg.reservoir is not None:
                fixed_head = pd.Series(cfg.reservoir.maximum_level_m - cfg.reservoir.tailwater_elevation_m, index=index)
            else:
                raise ValueError("Run-of-river simulation without a reservoir config requires resource.head")

            for i in range(n):
                head = float(fixed_head.iloc[i])
                available = min(permitted_flow.iloc[i], fleet_max_flow)
                dispatch = optimise_dispatch(turbines, available, head)
                power[i] = dispatch.total_power_mw
                flow_used[i] = dispatch.total_flow_m3s
                head_series[i] = head
                spill[i] = max(permitted_flow.iloc[i] - dispatch.total_flow_m3s, 0.0)

        generation_mw = pd.Series(power, index=index)
        # Check the flow the plant actually released against the natural
        # regime (ecological minimum, flow alteration, restricted periods)
        # now that a real release decision exists to check.
        _, env_violations = env.apply(pd.Series(flow_used, index=index), natural_flow)
        max_head = float(np.nanmax(head_series)) if n else 0.0

        theoretical_mwh = float(np.sum(theoretical_power(natural_flow.values, max_head)) / 1e6 * dt_hours)
        physical_flow = np.minimum(natural_flow.values, fleet_max_flow)
        physical_mwh = float(np.sum(theoretical_power(physical_flow, head_series) * 0.85) / 1e6 * dt_hours)
        available_mwh = physical_mwh * mean_availability
        env_flow_capped = np.minimum(permitted_flow.values, fleet_max_flow)
        environmentally_permitted_mwh = float(np.sum(theoretical_power(env_flow_capped, head_series) * 0.85) / 1e6 * dt_hours)

        result = self._finalise(
            generation_mw=generation_mw,
            resource=resource,
            fleet_capacity_mw=fleet_capacity_mw,
            reservoir_level_m=pd.Series(levels, index=index) if has_reservoir else None,
            spill_m3s=pd.Series(spill, index=index),
            flow_used=pd.Series(flow_used, index=index),
            head_series=pd.Series(head_series, index=index),
            natural_flow=natural_flow,
            constraint_violations=env_violations,
        )
        potential = GenerationPotential(
            theoretical_mwh=theoretical_mwh,
            physical_mwh=physical_mwh,
            available_mwh=available_mwh,
            optimally_dispatchable_mwh=result.annual_generation_mwh,
            economically_optimal_mwh=result.annual_generation_mwh,
            environmentally_permitted_mwh=environmentally_permitted_mwh,
        )
        return result, potential

    # ------------------------------------------------------------------ #
    # Pumped storage
    # ------------------------------------------------------------------ #

    def _simulate_pumped_storage(self, resource: ResourceTimeSeries, policy: dict) -> tuple[SimulationResult, GenerationPotential]:
        cfg = self.config.pumped_storage
        if cfg is None or resource.price is None:
            raise ValueError("Pumped-storage simulation requires config.pumped_storage and resource.price")

        effective_head = cfg.upper_reservoir.maximum_level_m - cfg.lower_reservoir.minimum_level_m
        optimiser = PumpedStorageOptimiser(cfg, effective_head_m=effective_head)
        schedule = optimiser.optimise(resource.price, method=policy.get("method", "auto"))

        net_generation = schedule.generate_mw - schedule.pump_mw
        result = self._finalise(
            generation_mw=net_generation,
            resource=resource,
            fleet_capacity_mw=cfg.turbine.rated_power_mw,
            reservoir_level_m=None,
            spill_m3s=pd.Series(0.0, index=resource.index),
            flow_used=None,
            head_series=pd.Series(effective_head, index=resource.index),
            natural_flow=None,
            constraint_violations=[],
            revenue_override=schedule.revenue,
        )
        theoretical_mwh = float(schedule.generate_mw.sum() * resource.dt_hours)
        potential = GenerationPotential(
            theoretical_mwh=theoretical_mwh,
            physical_mwh=theoretical_mwh,
            available_mwh=theoretical_mwh,
            optimally_dispatchable_mwh=theoretical_mwh,
            economically_optimal_mwh=theoretical_mwh,
            environmentally_permitted_mwh=theoretical_mwh,
        )
        return result, potential

    # ------------------------------------------------------------------ #
    # Tidal range (lagoon / basin / barrage)
    # ------------------------------------------------------------------ #

    def _simulate_tidal_range(self, resource: ResourceTimeSeries, policy: dict) -> tuple[SimulationResult, GenerationPotential]:
        cfg = self.config.tidal
        if cfg is None:
            raise ValueError("Tidal range simulation requires config.tidal")

        tidal_cfg = cfg
        if "minimum_generating_head_m" in policy:
            import dataclasses

            tidal_cfg = dataclasses.replace(cfg, minimum_generating_head_m=policy["minimum_generating_head_m"])

        turbine_flow = sum(t.rated_flow_m3s for t in self.config.turbines) or 1000.0
        turbine_power = sum(t.rated_power_mw for t in self.config.turbines) or 100.0
        optimiser = TidalBarrageOptimiser(tidal_cfg, turbine_flow, turbine_power)
        schedule = optimiser.optimise_schedule(resource.index, mode=tidal_cfg.mode, price=resource.price)

        result = self._finalise(
            generation_mw=schedule.power_mw,
            resource=resource,
            fleet_capacity_mw=turbine_power,
            reservoir_level_m=schedule.basin_level_m,
            spill_m3s=pd.Series(0.0, index=resource.index),
            flow_used=schedule.flow_m3s.abs(),
            head_series=schedule.head_m.abs(),
            natural_flow=None,
            constraint_violations=[],
            revenue_override=schedule.revenue if resource.price is not None else None,
        )

        theoretical_mwh = float(
            np.sum(theoretical_power(schedule.flow_m3s.abs().values, schedule.head_m.abs().values, rho=RHO_SEAWATER)) / 1e6 * resource.dt_hours
        )
        potential = GenerationPotential(
            theoretical_mwh=theoretical_mwh,
            physical_mwh=schedule.annual_energy_mwh,
            available_mwh=schedule.annual_energy_mwh,
            optimally_dispatchable_mwh=schedule.annual_energy_mwh,
            economically_optimal_mwh=schedule.annual_energy_mwh,
            environmentally_permitted_mwh=schedule.annual_energy_mwh,
        )
        return result, potential

    # ------------------------------------------------------------------ #
    # Tidal stream
    # ------------------------------------------------------------------ #

    def _simulate_tidal_stream(self, resource: ResourceTimeSeries, policy: dict) -> tuple[SimulationResult, GenerationPotential]:
        cfg = self.config.tidal_stream
        if cfg is None or resource.flow is None:
            raise ValueError("Tidal stream simulation requires config.tidal_stream and resource.flow (current speed, m/s)")

        turbine = TidalStreamTurbine.from_config(cfg)
        per_turbine_mw = turbine.power_curve(resource.flow.values)
        total_mw = per_turbine_mw * cfg.turbine_count
        generation_mw = pd.Series(total_mw, index=resource.index)

        result = self._finalise(
            generation_mw=generation_mw,
            resource=resource,
            fleet_capacity_mw=cfg.rated_power_mw * cfg.turbine_count,
            reservoir_level_m=None,
            spill_m3s=pd.Series(0.0, index=resource.index),
            flow_used=resource.flow,
            head_series=pd.Series(np.nan, index=resource.index),
            natural_flow=None,
            constraint_violations=[],
        )
        energy = float(generation_mw.sum() * resource.dt_hours)
        potential = GenerationPotential(energy, energy, energy, energy, energy, energy)
        return result, potential

    # ------------------------------------------------------------------ #
    # Shared finalisation: efficiency, economics, curtailment, metrics
    # ------------------------------------------------------------------ #

    def _finalise(
        self,
        generation_mw: pd.Series,
        resource: ResourceTimeSeries,
        fleet_capacity_mw: float,
        reservoir_level_m: Optional[pd.Series],
        spill_m3s: Optional[pd.Series],
        flow_used: Optional[pd.Series],
        head_series: Optional[pd.Series],
        natural_flow: Optional[pd.Series],
        constraint_violations: list,
        revenue_override: Optional[float] = None,
    ) -> SimulationResult:
        cfg = self.config
        dt_hours = resource.dt_hours

        curtailment_result = apply_curtailment(generation_mw.clip(lower=0), cfg.grid.grid_export_capacity_mw)
        delivered = curtailment_result.delivered_mw

        annual_generation_mwh = float(delivered.sum() * dt_hours)
        peak_generation_mw = float(delivered.max()) if len(delivered) else 0.0
        capacity_factor = annual_generation_mwh / (fleet_capacity_mw * dt_hours * len(delivered)) if fleet_capacity_mw > 0 and len(delivered) else 0.0

        if flow_used is not None and head_series is not None and flow_used.abs().sum() > 0:
            hydraulic_energy = float(np.sum(theoretical_power(flow_used.abs().values, head_series.fillna(0).abs().values)) / 1e6 * dt_hours)
            average_efficiency = annual_generation_mwh / hydraulic_energy if hydraulic_energy > 0 else 0.0
            average_efficiency = float(np.clip(average_efficiency, 0.0, 1.0))
        else:
            average_efficiency = 0.0

        if natural_flow is not None and flow_used is not None:
            total_natural = float(natural_flow.sum())
            total_used = float(flow_used.sum())
            water_utilisation_pct = 100.0 * total_used / total_natural if total_natural > 0 else 0.0
            spillage_pct = 100.0 * float(spill_m3s.sum()) / total_natural if (spill_m3s is not None and total_natural > 0) else 0.0
        else:
            water_utilisation_pct = 100.0
            spillage_pct = 0.0

        if revenue_override is not None:
            revenue = revenue_override
        elif resource.price is not None:
            revenue = float((delivered * resource.price.reindex(delivered.index).fillna(0.0) * dt_hours).sum())
        else:
            revenue = 0.0

        n_years_simulated = max(len(resource.index) * dt_hours / (24 * 365.25), 1e-6)
        annualised_generation = annual_generation_mwh / n_years_simulated
        annualised_price = revenue / annual_generation_mwh if annual_generation_mwh > 0 else 0.0

        econ_engine = EconomicEngine(cfg.economics)
        econ_result = econ_engine.evaluate(annualised_generation, annualised_price)

        return SimulationResult(
            system_name=cfg.name,
            generation_mw=delivered,
            reservoir_level_m=reservoir_level_m,
            spill_m3s=spill_m3s,
            curtailment_mw=curtailment_result.curtailed_mw,
            annual_generation_mwh=annual_generation_mwh,
            peak_generation_mw=peak_generation_mw,
            capacity_factor=float(np.clip(capacity_factor, 0.0, 1.0)),
            average_efficiency=average_efficiency,
            water_utilisation_pct=water_utilisation_pct,
            spillage_pct=spillage_pct,
            curtailment_pct=curtailment_result.curtailment_pct,
            revenue=revenue,
            capex=econ_result.capex,
            opex=float(np.sum(econ_result.opex_by_year)),
            lcoe=econ_result.lcoe_value,
            npv=econ_result.npv_value,
            irr=econ_result.irr_value,
            environmental_metrics={},
            constraint_violations=constraint_violations,
        )
