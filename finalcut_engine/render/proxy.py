"""ProRes/proxy ladder policy and (synthetic) proxy generation.

A real implementation transcodes via AVFoundation/VideoToolbox; this
prototype demonstrates the *policy and workflow* (which rung of the ladder to
use, how a generated proxy attaches to a :class:`MediaRepresentations`, how
"switch to original for final render" works) using a resolution-downscale
placeholder for the actual pixels.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from finalcut_engine.media.media_file import MediaFile, MediaRepresentationKind, MediaRepresentations
from finalcut_engine.media.metadata import MediaMetadata, VideoCodec


@dataclass(frozen=True)
class ProxyRung:
    codec: VideoCodec
    max_long_edge: int  # longest edge, in pixels
    label: str


#: From lightest to heaviest — spec section 7's ProRes ladder.
PRORES_LADDER = [
    ProxyRung(VideoCodec.PRORES_PROXY, 960, "ProRes Proxy"),
    ProxyRung(VideoCodec.PRORES_LT, 1280, "ProRes LT"),
    ProxyRung(VideoCodec.PRORES_422, 1920, "ProRes 422"),
    ProxyRung(VideoCodec.PRORES_422_HQ, 2560, "ProRes 422 HQ"),
    ProxyRung(VideoCodec.PRORES_4444, 3840, "ProRes 4444"),
    ProxyRung(VideoCodec.PRORES_4444_XQ, 4096, "ProRes 4444 XQ"),
]


def choose_proxy_rung(original: MediaMetadata, prefer_fast_editing: bool = True) -> ProxyRung:
    """Pick a proxy rung well below the original's resolution for smooth editing."""
    if prefer_fast_editing:
        return PRORES_LADDER[0]
    long_edge = max(original.width, original.height)
    for rung in PRORES_LADDER:
        if rung.max_long_edge >= long_edge / 2:
            return rung
    return PRORES_LADDER[-1]


def downscale_frame(frame: np.ndarray, max_long_edge: int) -> np.ndarray:
    h, w = frame.shape[:2]
    long_edge = max(h, w)
    if long_edge <= max_long_edge:
        return frame
    scale = max_long_edge / long_edge
    new_h, new_w = max(1, int(h * scale)), max(1, int(w * scale))
    row_idx = (np.arange(new_h) * h / new_h).astype(np.int64)
    col_idx = (np.arange(new_w) * w / new_w).astype(np.int64)
    return frame[row_idx][:, col_idx]


def generate_proxy(
    representations: MediaRepresentations, output_path: Path, rung: ProxyRung
) -> MediaFile:
    """Register a proxy representation. Pixel transcoding is out of scope for
    this prototype (see module docstring); this wires up the metadata and
    representation-switching workflow that a native transcoder plugs into.
    """
    original_md = representations.original.metadata
    scale = min(1.0, rung.max_long_edge / max(1, max(original_md.width, original_md.height)))
    proxy_md = original_md.model_copy(
        update={
            "video_codec": rung.codec,
            "width": max(1, int(original_md.width * scale)),
            "height": max(1, int(original_md.height * scale)),
            "filename": output_path.name,
        }
    )
    proxy_file = MediaFile(path=output_path, metadata=proxy_md, kind=MediaRepresentationKind.PROXY)
    representations.proxy = proxy_file
    return proxy_file
