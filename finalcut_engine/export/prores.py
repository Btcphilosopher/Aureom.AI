"""ProRes export profiles and Apple's published approximate bitrate ladder."""
from __future__ import annotations

from dataclasses import dataclass

from finalcut_engine.media.metadata import VideoCodec

#: Approximate Mbps at 1920x1080, 29.97fps, per Apple's published ProRes
#: whitepaper figures — scaled by resolution/frame-rate for other formats.
_BASE_MBPS_1080P30 = {
    VideoCodec.PRORES_PROXY: 45,
    VideoCodec.PRORES_LT: 102,
    VideoCodec.PRORES_422: 147,
    VideoCodec.PRORES_422_HQ: 220,
    VideoCodec.PRORES_4444: 330,
    VideoCodec.PRORES_4444_XQ: 500,
}


@dataclass(frozen=True)
class ProResProfile:
    codec: VideoCodec
    has_alpha: bool = False

    def estimate_bitrate_mbps(self, width: int, height: int, fps: float) -> float:
        base = _BASE_MBPS_1080P30[self.codec]
        area_ratio = (width * height) / (1920 * 1080)
        fps_ratio = fps / 29.97
        alpha_multiplier = 1.3 if self.has_alpha and self.codec in (VideoCodec.PRORES_4444, VideoCodec.PRORES_4444_XQ) else 1.0
        return base * area_ratio * fps_ratio * alpha_multiplier


PRORES_PROXY = ProResProfile(VideoCodec.PRORES_PROXY)
PRORES_LT = ProResProfile(VideoCodec.PRORES_LT)
PRORES_422 = ProResProfile(VideoCodec.PRORES_422)
PRORES_422_HQ = ProResProfile(VideoCodec.PRORES_422_HQ)
PRORES_4444 = ProResProfile(VideoCodec.PRORES_4444, has_alpha=True)
PRORES_4444_XQ = ProResProfile(VideoCodec.PRORES_4444_XQ, has_alpha=True)
