"""HEVC (H.265) export presets — roughly half the bitrate of H.264 for similar quality."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HEVCPreset:
    name: str
    target_bitrate_mbps: float
    max_bitrate_mbps: float
    ten_bit: bool = False
    hdr: bool = False


HEVC_WEB = HEVCPreset(name="Web (HEVC)", target_bitrate_mbps=6, max_bitrate_mbps=9)
HEVC_ARCHIVE = HEVCPreset(name="Archive (HEVC)", target_bitrate_mbps=25, max_bitrate_mbps=35, ten_bit=True)
HEVC_HDR = HEVCPreset(name="HDR (HEVC)", target_bitrate_mbps=30, max_bitrate_mbps=45, ten_bit=True, hdr=True)
