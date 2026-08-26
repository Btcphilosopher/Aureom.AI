from apex_horizon_engine.core.world_streaming import WorldStreamer
from apex_horizon_engine.utils.config import WORLD_ZONES


def test_nearest_zone_matches_center():
    streamer = WorldStreamer(WORLD_ZONES)
    meridian = WORLD_ZONES["meridian_city"]
    zone = streamer.nearest_zone(*meridian.center_xy)
    assert zone.zone_id == "meridian_city"


def test_update_reports_zone_transition():
    streamer = WorldStreamer(WORLD_ZONES)
    meridian = WORLD_ZONES["meridian_city"]
    desert = WORLD_ZONES["silica_flats"]

    first = streamer.update(*meridian.center_xy)
    assert first.entered_zone is not None
    assert first.entered_zone.zone_id == "meridian_city"

    second = streamer.update(*meridian.center_xy)
    assert second.entered_zone is None  # no transition, still in the same zone

    third = streamer.update(*desert.center_xy)
    assert third.entered_zone.zone_id == "silica_flats"
    assert third.exited_zone.zone_id == "meridian_city"


def test_world_bounds_cover_every_zone():
    streamer = WorldStreamer(WORLD_ZONES)
    min_x, min_y, max_x, max_y = streamer.world_bounds()
    for zone in WORLD_ZONES.values():
        cx, cy = zone.center_xy
        assert min_x <= cx - zone.radius_m
        assert max_x >= cx + zone.radius_m
        assert min_y <= cy - zone.radius_m
        assert max_y >= cy + zone.radius_m
