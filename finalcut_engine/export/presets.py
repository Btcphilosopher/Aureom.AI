"""Named export presets bundling video codec, resolution, frame rate, audio
format, and colour space into one selectable unit (spec section 21).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from finalcut_engine.core.timebase import FPS_24, FrameRate
from finalcut_engine.export.h264 import H264_MASTER_COMPAT, H264_SOCIAL, H264_WEB, H264Preset
from finalcut_engine.export.hevc import HEVC_ARCHIVE, HEVCPreset
from finalcut_engine.export.prores import PRORES_422_HQ, PRORES_4444, ProResProfile
from finalcut_engine.media.metadata import ColourSpace

CodecProfile = Union[ProResProfile, H264Preset, HEVCPreset, None]


@dataclass(frozen=True)
class AudioFormat:
    codec: str = "pcm"  # "pcm" | "aac"
    sample_rate: int = 48000
    bit_depth: int = 24
    channels: int = 2


@dataclass(frozen=True)
class ExportPreset:
    name: str
    container: str
    video_codec: CodecProfile
    width: int
    height: int
    frame_rate: FrameRate
    audio: Optional[AudioFormat]
    colour_space: ColourSpace = ColourSpace.REC709

    def with_resolution(self, width: int, height: int) -> "ExportPreset":
        return ExportPreset(
            name=self.name,
            container=self.container,
            video_codec=self.video_codec,
            width=width,
            height=height,
            frame_rate=self.frame_rate,
            audio=self.audio,
            colour_space=self.colour_space,
        )


STANDARD_PRESETS: dict[str, ExportPreset] = {
    "Master": ExportPreset("Master", "mov", PRORES_4444, 3840, 2160, FPS_24, AudioFormat(bit_depth=24)),
    "ProRes": ExportPreset("ProRes", "mov", PRORES_422_HQ, 1920, 1080, FPS_24, AudioFormat(bit_depth=24)),
    "H.264": ExportPreset("H.264", "mp4", H264_MASTER_COMPAT, 1920, 1080, FPS_24, AudioFormat(codec="aac")),
    "HEVC": ExportPreset("HEVC", "mp4", HEVC_ARCHIVE, 1920, 1080, FPS_24, AudioFormat(codec="aac")),
    "Web": ExportPreset("Web", "mp4", H264_WEB, 1280, 720, FPS_24, AudioFormat(codec="aac", sample_rate=44100)),
    "Social": ExportPreset("Social", "mp4", H264_SOCIAL, 1080, 1080, FPS_24, AudioFormat(codec="aac", sample_rate=44100)),
    "Archive": ExportPreset("Archive", "mov", PRORES_4444, 3840, 2160, FPS_24, AudioFormat(bit_depth=24)),
    "Audio-only": ExportPreset("Audio-only", "wav", None, 0, 0, FPS_24, AudioFormat(bit_depth=24)),
}
