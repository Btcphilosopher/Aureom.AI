"""Structured, strongly typed media metadata.

Metadata is captured once at import/probe time and indexed by the library —
see spec section 6 ("Do not decode an entire media file simply to display its
metadata."). Everything downstream (library search, multicam sync, proxy
generation, colour pipeline defaults) reads from this model rather than
re-probing the file.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from finalcut_engine.core.timebase import FrameRate


class VideoCodec(str, Enum):
    H264 = "h264"
    HEVC = "hevc"
    PRORES_PROXY = "prores_proxy"
    PRORES_LT = "prores_lt"
    PRORES_422 = "prores_422"
    PRORES_422_HQ = "prores_422_hq"
    PRORES_4444 = "prores_4444"
    PRORES_4444_XQ = "prores_4444_xq"
    IMAGE_SEQUENCE = "image_sequence"
    UNKNOWN = "unknown"


class AudioCodec(str, Enum):
    PCM = "pcm"
    AAC = "aac"
    MP3 = "mp3"
    NONE = "none"
    UNKNOWN = "unknown"


class ColourSpace(str, Enum):
    REC709 = "rec709"
    REC2020 = "rec2020"
    REC2020_PQ = "rec2020_pq"  # HDR10 / Dolby Vision base layer
    SRGB = "srgb"
    APPLE_LOG = "apple_log"
    UNKNOWN = "unknown"


class CameraMetadata(BaseModel):
    make: Optional[str] = None
    model: Optional[str] = None
    lens: Optional[str] = None
    iso: Optional[int] = None
    shutter_angle: Optional[float] = None
    white_balance_kelvin: Optional[int] = None
    reel_name: Optional[str] = None
    start_timecode: Optional[str] = None


class MediaMetadata(BaseModel):
    """Everything the library needs to know about a media file without decoding it."""

    filename: str
    file_size_bytes: int = 0
    container: str = "unknown"

    video_codec: VideoCodec = VideoCodec.UNKNOWN
    width: int = 0
    height: int = 0
    frame_rate_num: int = 0
    frame_rate_den: int = 1
    duration_seconds: float = 0.0
    colour_space: ColourSpace = ColourSpace.UNKNOWN
    has_alpha: bool = False

    audio_codec: AudioCodec = AudioCodec.NONE
    audio_channels: int = 0
    audio_sample_rate: int = 0

    camera: CameraMetadata = Field(default_factory=CameraMetadata)
    creation_date: Optional[datetime] = None

    checksum: Optional[str] = None  # content hash, used for de-dup and cache keys

    @property
    def frame_rate(self) -> FrameRate:
        if self.frame_rate_num <= 0:
            return FrameRate(24, 1)
        drop = self.frame_rate_den == 1001
        return FrameRate(self.frame_rate_num, self.frame_rate_den, drop_frame=drop)

    @property
    def is_video(self) -> bool:
        return self.video_codec not in (VideoCodec.UNKNOWN,) and self.width > 0

    @property
    def is_audio_only(self) -> bool:
        return not self.is_video and self.audio_codec != AudioCodec.NONE

    @property
    def is_prores(self) -> bool:
        return self.video_codec.value.startswith("prores")

    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 0.0
