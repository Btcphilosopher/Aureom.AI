"""The production-line engine: wires the processing steps into one pipeline.

Implements the top-level chain from the spec:

    FORMULATION -> MIXING -> PASTEURISATION -> HOMOGENISATION -> AGEING
        -> FREEZING -> AIR INCORPORATION -> HARDENING -> [COLD STORAGE]

:class:`ProcessProfile` bundles every equipment choice and process
setpoint needed to run that chain; :func:`run_production_line` executes
it against a :class:`~icecream_x.formulation.recipe.Recipe` and returns
every intermediate result alongside the final
:class:`~icecream_x.core.state.ProductState`, so callers can inspect any
stage without re-running the pipeline (each processing-step result is
already keeping its own trajectory -- see
:mod:`icecream_x.processing`).

Cold storage/distribution is intentionally *not* part of this pipeline:
it is long-duration and driven by an external temperature history rather
than fixed equipment setpoints, and is run separately via
:mod:`icecream_x.storage.cold_chain` on the ``final_state`` this engine
produces.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.core.events import EventLog
from icecream_x.core.state import ProductState
from icecream_x.equipment.freezer import CONTINUOUS_FREEZER_DEFAULT, ScrapedSurfaceFreezer
from icecream_x.equipment.hardening_tunnel import BLAST_TUNNEL_DEFAULT, HardeningTunnel
from icecream_x.equipment.homogeniser import TWO_STAGE_DEFAULT, Homogeniser
from icecream_x.equipment.pasteuriser import HTST_DEFAULT, Pasteuriser
from icecream_x.formulation.recipe import Recipe
from icecream_x.processing.aeration import aerate
from icecream_x.processing.ageing import AgeingResult, age
from icecream_x.processing.freezing import FreezingResult, freeze
from icecream_x.processing.hardening import HardeningResult, harden
from icecream_x.processing.homogenisation import homogenise
from icecream_x.processing.mixing import mix
from icecream_x.processing.pasteurisation import PasteurisationResult, pasteurise


@dataclass(frozen=True, slots=True)
class ProcessProfile:
    """Every equipment choice and setpoint needed to run the production line."""

    mix_temperature_c: float = 4.0
    pasteuriser: Pasteuriser = HTST_DEFAULT
    homogeniser: Homogeniser = TWO_STAGE_DEFAULT
    homogeniser_mass_flow_kg_s: float = 0.5
    ageing_temperature_c: float = 4.0
    ageing_time_s: float = 4.0 * 3600.0
    freezer: ScrapedSurfaceFreezer = CONTINUOUS_FREEZER_DEFAULT
    freezer_outlet_temperature_c: float = -5.5
    overrun_pct: float = 90.0
    hardening_tunnel: HardeningTunnel = BLAST_TUNNEL_DEFAULT
    hardening_target_temperature_c: float = -20.0


@dataclass(slots=True)
class PipelineResult:
    recipe: Recipe
    mixed_state: ProductState
    pasteurisation: PasteurisationResult
    homogenised_state: ProductState
    ageing: AgeingResult
    freezing: FreezingResult
    aerated_state: ProductState
    hardening: HardeningResult
    final_state: ProductState
    event_log: EventLog

    def stage_summaries(self) -> list[dict]:
        return [
            {"stage": "mixed", **self.mixed_state.summary()},
            {"stage": "pasteurised", **self.pasteurisation.final_state.summary()},
            {"stage": "homogenised", **self.homogenised_state.summary()},
            {"stage": "aged", **self.ageing.final_state.summary()},
            {"stage": "frozen", **self.freezing.final_state.summary()},
            {"stage": "aerated", **self.aerated_state.summary()},
            {"stage": "hardened", **self.hardening.final_state.summary()},
        ]


def run_production_line(
    recipe: Recipe, profile: ProcessProfile = ProcessProfile(), *, event_log: EventLog | None = None
) -> PipelineResult:
    log = event_log if event_log is not None else EventLog()

    mixed = mix(recipe, mix_temperature_c=profile.mix_temperature_c)

    pasteurisation = pasteurise(
        mixed, profile.pasteuriser, post_cooling_temperature_c=profile.mix_temperature_c, event_log=log
    )

    homogenised = homogenise(
        pasteurisation.final_state,
        profile.homogeniser,
        mass_flow_kg_s=profile.homogeniser_mass_flow_kg_s,
        event_log=log,
    )

    ageing = age(
        homogenised, profile.ageing_temperature_c, profile.ageing_time_s, event_log=log
    )

    freezing = freeze(
        ageing.final_state,
        profile.freezer,
        profile.freezer_outlet_temperature_c,
        event_log=log,
    )

    aerated = aerate(
        freezing.final_state,
        profile.overrun_pct,
        wall_shear_rate_1_per_s=freezing.wall_shear_rate_1_per_s,
        event_log=log,
    )

    hardening = harden(
        aerated, profile.hardening_tunnel, profile.hardening_target_temperature_c, event_log=log
    )

    return PipelineResult(
        recipe=recipe,
        mixed_state=mixed,
        pasteurisation=pasteurisation,
        homogenised_state=homogenised,
        ageing=ageing,
        freezing=freezing,
        aerated_state=aerated,
        hardening=hardening,
        final_state=hardening.final_state,
        event_log=log,
    )
