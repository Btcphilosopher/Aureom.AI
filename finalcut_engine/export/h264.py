"""H.264 export presets."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class H264Preset:
    name: str
    target_bitrate_mbps: float
    max_bitrate_mbps: float
    profile: str = "high"  # baseline | main | high
    keyframe_interval_seconds: float = 2.0
    two_pass: bool = False


H264_WEB = H264Preset(name="Web (H.264)", target_bitrate_mbps=10, max_bitrate_mbps=14, two_pass=True)
H264_SOCIAL = H264Preset(name="Social (H.264)", target_bitrate_mbps=8, max_bitrate_mbps=12)
H264_MASTER_COMPAT = H264Preset(name="H.264 Master-compatible", target_bitrate_mbps=50, max_bitrate_mbps=65, two_pass=True)
