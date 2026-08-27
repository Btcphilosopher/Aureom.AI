"""Configurable quality index.

**This is an engineering proxy, not a validated sensory-panel model.**
It combines several physically-measurable microstructure/process
outputs into 0-1 sub-scores and takes a weighted sum. The sub-score
shapes (which direction is "better", roughly where diminishing returns
kick in) are chosen to match well-known qualitative sensory
relationships in ice cream science (e.g. smaller ice crystals read as
creamier up to the point they're imperceptible; too much overrun reads as
thin/airy rather than creamy), but neither the shapes nor the weights are
fitted to any lab or consumer panel dataset. Treat
:class:`QualityWeights` as the calibration surface: replace it (and, if
needed, the sub-score functions) with parameters fitted to real sensory
or QC data via :mod:`icecream_x.digital_twin.calibration` before using
scores for anything beyond relative, directional "did this experiment
help or hurt" comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.core.state import ProductState


@dataclass(frozen=True, slots=True)
class QualityWeights:
    creaminess: float = 0.25
    melting_resistance: float = 0.20
    air_cell_stability: float = 0.15
    hardness_at_serving: float = 0.15
    storage_stability: float = 0.15
    texture_uniformity: float = 0.10

    def normalised(self) -> "QualityWeights":
        total = (
            self.creaminess
            + self.melting_resistance
            + self.air_cell_stability
            + self.hardness_at_serving
            + self.storage_stability
            + self.texture_uniformity
        )
        if total <= 0:
            raise ValueError("Quality weights must sum to a positive value")
        return QualityWeights(
            creaminess=self.creaminess / total,
            melting_resistance=self.melting_resistance / total,
            air_cell_stability=self.air_cell_stability / total,
            hardness_at_serving=self.hardness_at_serving / total,
            storage_stability=self.storage_stability / total,
            texture_uniformity=self.texture_uniformity / total,
        )


DEFAULT_WEIGHTS = QualityWeights()

#: Ice-crystal diameter (um) below which creaminess is considered
#: essentially maximal (imperceptibly smooth), and above which it degrades.
CREAMINESS_SMALL_CRYSTAL_UM = 30.0
CREAMINESS_LARGE_CRYSTAL_UM = 100.0

SERVING_TEMPERATURE_C = -14.0
HARDNESS_IDEAL_ICE_FRACTION_PCT = 68.0
HARDNESS_TOLERANCE_PCT = 15.0


def _clamp01(x: float) -> float:
    return min(max(x, 0.0), 1.0)


def creaminess_subscore(mean_ice_crystal_diameter_um: float | None) -> float:
    if mean_ice_crystal_diameter_um is None:
        return 0.5
    if mean_ice_crystal_diameter_um <= CREAMINESS_SMALL_CRYSTAL_UM:
        return 1.0
    if mean_ice_crystal_diameter_um >= CREAMINESS_LARGE_CRYSTAL_UM:
        return 0.0
    span = CREAMINESS_LARGE_CRYSTAL_UM - CREAMINESS_SMALL_CRYSTAL_UM
    return 1.0 - (mean_ice_crystal_diameter_um - CREAMINESS_SMALL_CRYSTAL_UM) / span


def melting_resistance_subscore(fat_destabilisation_degree: float | None) -> float:
    if fat_destabilisation_degree is None:
        return 0.3
    return _clamp01(fat_destabilisation_degree / 0.7)


def air_cell_stability_subscore(stability_index: float | None) -> float:
    if stability_index is None:
        return 0.3
    return _clamp01(stability_index)


def hardness_subscore_at_serving(state: ProductState) -> float:
    from icecream_x.thermodynamics.phase_equilibrium import evaluate as evaluate_thermal
    from icecream_x.utils.units import celsius_to_kelvin

    serving_thermal = evaluate_thermal(state.composition, celsius_to_kelvin(SERVING_TEMPERATURE_C))
    ice_pct = 100 * serving_thermal.phase.ice_mass_fraction
    deviation = abs(ice_pct - HARDNESS_IDEAL_ICE_FRACTION_PCT)
    return _clamp01(1.0 - deviation / HARDNESS_TOLERANCE_PCT)


def storage_stability_subscore(mean_ice_crystal_diameter_um: float | None) -> float:
    """Uses current crystal size as a proxy for accumulated storage damage."""
    return creaminess_subscore(mean_ice_crystal_diameter_um)


def texture_uniformity_subscore(distribution_cv: float | None) -> float:
    if distribution_cv is None:
        return 0.5
    return _clamp01(1.0 - distribution_cv)


@dataclass(frozen=True, slots=True)
class QualityResult:
    overall_score: float  # 0-100
    subscores: dict[str, float]


def quality_score(state: ProductState, weights: QualityWeights = DEFAULT_WEIGHTS) -> QualityResult:
    w = weights.normalised()
    micro = state.microstructure
    crystal_diameter = micro.ice_crystals.mean_diameter_um if micro.ice_crystals else None
    distribution_cv = micro.ice_crystals.distribution_cv if micro.ice_crystals else None
    destab = micro.fat_network.destabilisation_degree if micro.fat_network else None
    air_stability = micro.air_cells.stability_index if micro.air_cells else None

    subscores = {
        "creaminess": creaminess_subscore(crystal_diameter),
        "melting_resistance": melting_resistance_subscore(destab),
        "air_cell_stability": air_cell_stability_subscore(air_stability),
        "hardness_at_serving": hardness_subscore_at_serving(state),
        "storage_stability": storage_stability_subscore(crystal_diameter),
        "texture_uniformity": texture_uniformity_subscore(distribution_cv),
    }
    overall = 100.0 * (
        w.creaminess * subscores["creaminess"]
        + w.melting_resistance * subscores["melting_resistance"]
        + w.air_cell_stability * subscores["air_cell_stability"]
        + w.hardness_at_serving * subscores["hardness_at_serving"]
        + w.storage_stability * subscores["storage_stability"]
        + w.texture_uniformity * subscores["texture_uniformity"]
    )
    return QualityResult(overall_score=overall, subscores=subscores)
