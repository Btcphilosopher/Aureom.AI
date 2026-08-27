"""Example cold-chain storage profiles."""

from __future__ import annotations

from icecream_x.storage.cold_chain import ColdChainStage
from icecream_x.storage.freezer import COLD_STORE, HOME_FREEZER, RETAIL_CABINET, REFRIGERATED_TRANSPORT
from icecream_x.storage.temperature_history import TemperatureProfile, uninterrupted


def standard_distribution() -> list[ColdChainStage]:
    """Factory cold store -> transport -> retail cabinet -> home freezer, no excursions."""
    return [
        ColdChainStage("Factory Cold Store", COLD_STORE, duration_s=14 * 24 * 3600),
        ColdChainStage("Refrigerated Transport", REFRIGERATED_TRANSPORT, duration_s=2 * 24 * 3600),
        ColdChainStage("Retail Cabinet", RETAIL_CABINET, duration_s=21 * 24 * 3600),
        ColdChainStage("Home Freezer", HOME_FREEZER, duration_s=7 * 24 * 3600),
    ]


def distribution_with_transport_excursion() -> list[ColdChainStage]:
    """Same as standard distribution, but the truck suffers a 4-hour cooling failure."""
    transport_profile = TemperatureProfile(baseline_temperature_c=REFRIGERATED_TRANSPORT.setpoint_temperature_c)
    transport_profile.add_excursion(
        start_time_s=6 * 3600, duration_s=4 * 3600, peak_temperature_c=-8.0, label="reefer unit failure"
    )
    return [
        ColdChainStage("Factory Cold Store", COLD_STORE, duration_s=14 * 24 * 3600),
        ColdChainStage(
            "Refrigerated Transport (excursion)",
            REFRIGERATED_TRANSPORT,
            duration_s=2 * 24 * 3600,
            temperature_profile=transport_profile,
        ),
        ColdChainStage("Retail Cabinet", RETAIL_CABINET, duration_s=21 * 24 * 3600),
        ColdChainStage("Home Freezer", HOME_FREEZER, duration_s=7 * 24 * 3600),
    ]


def distribution_with_frequent_door_openings() -> list[ColdChainStage]:
    """Retail cabinet subject to repeated door-opening excursions."""
    profile = TemperatureProfile(baseline_temperature_c=RETAIL_CABINET.setpoint_temperature_c)
    for day in range(0, 21):
        profile.add_excursion(
            start_time_s=day * 24 * 3600 + 12 * 3600,
            duration_s=900,
            peak_temperature_c=-9.0,
            label=f"door open day {day}",
        )
    return [
        ColdChainStage("Factory Cold Store", COLD_STORE, duration_s=14 * 24 * 3600),
        ColdChainStage("Refrigerated Transport", REFRIGERATED_TRANSPORT, duration_s=2 * 24 * 3600),
        ColdChainStage(
            "Retail Cabinet (frequent openings)",
            RETAIL_CABINET,
            duration_s=21 * 24 * 3600,
            temperature_profile=profile,
        ),
        ColdChainStage("Home Freezer", HOME_FREEZER, duration_s=7 * 24 * 3600),
    ]


STORAGE_PROFILE_LIBRARY = {
    "standard_distribution": standard_distribution,
    "distribution_with_transport_excursion": distribution_with_transport_excursion,
    "distribution_with_frequent_door_openings": distribution_with_frequent_door_openings,
}
