"""Extensible media import pipeline (spec section 6).

``MediaProbe`` is the abstraction point: a native build swaps in an
AVFoundation/AVAsset-backed prober without touching ``MediaImporter`` or
anything downstream. Two probes ship here:

* :class:`FFprobeMediaProbe` — reads container/stream headers via `ffprobe`
  when it is available on ``PATH``. This never decodes frame data, matching
  the spec's "do not decode an entire media file simply to display its
  metadata".
* :class:`SyntheticMediaProbe` — a deterministic, dependency-free prober used
  by tests and the demo project so the engine can be exercised without real
  ProRes/H.264 sample files.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from finalcut_engine.media.asset import MediaAsset
from finalcut_engine.media.media_file import MediaFile, MediaRepresentationKind, MediaRepresentations
from finalcut_engine.media.metadata import AudioCodec, ColourSpace, MediaMetadata, VideoCodec

_CODEC_MAP = {
    "h264": VideoCodec.H264,
    "hevc": VideoCodec.HEVC,
    "h265": VideoCodec.HEVC,
    "prores": VideoCodec.PRORES_422,
}


class MediaProbe(ABC):
    """Reads technical metadata from a file header without full decode."""

    @abstractmethod
    def probe(self, path: Path) -> MediaMetadata: ...

    def supports(self, path: Path) -> bool:
        return True


def quick_checksum(path: Path, sample_bytes: int = 1 << 16) -> str:
    """A fast content fingerprint: file size + hashes of the head and tail.

    Deliberately avoids hashing the whole file (which for professional camera
    footage can be tens of gigabytes) — good enough to detect duplicate
    imports and to key render/proxy caches.
    """
    h = hashlib.blake2b(digest_size=16)
    size = path.stat().st_size
    h.update(size.to_bytes(8, "little"))
    with path.open("rb") as f:
        h.update(f.read(sample_bytes))
        if size > sample_bytes:
            f.seek(max(0, size - sample_bytes))
            h.update(f.read(sample_bytes))
    return h.hexdigest()


class FFprobeMediaProbe(MediaProbe):
    """Probes real media files via the `ffprobe` CLI, if installed."""

    def __init__(self) -> None:
        self._binary = shutil.which("ffprobe")

    def available(self) -> bool:
        return self._binary is not None

    def supports(self, path: Path) -> bool:
        return self.available()

    def probe(self, path: Path) -> MediaMetadata:
        if not self._binary:
            raise RuntimeError("ffprobe is not available on PATH")
        cmd = [self._binary, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
        data = json.loads(out.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        vstream = next((s for s in streams if s.get("codec_type") == "video"), None)
        astream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        md = MediaMetadata(
            filename=path.name,
            file_size_bytes=int(fmt.get("size", path.stat().st_size)),
            container=fmt.get("format_name", "unknown").split(",")[0],
            duration_seconds=float(fmt.get("duration", 0.0)),
            checksum=quick_checksum(path),
        )
        if vstream is not None:
            codec_name = (vstream.get("codec_name") or "").lower()
            tag = "prores" if "prores" in codec_name else codec_name
            md.video_codec = _CODEC_MAP.get(tag, VideoCodec.UNKNOWN)
            md.width = int(vstream.get("width", 0))
            md.height = int(vstream.get("height", 0))
            rate = vstream.get("r_frame_rate", "24/1")
            num, _, den = rate.partition("/")
            md.frame_rate_num, md.frame_rate_den = int(num), int(den or 1)
            md.colour_space = ColourSpace.REC709
        if astream is not None:
            codec_name = (astream.get("codec_name") or "").lower()
            md.audio_codec = {"pcm_s16le": AudioCodec.PCM, "aac": AudioCodec.AAC, "mp3": AudioCodec.MP3}.get(
                codec_name, AudioCodec.UNKNOWN
            )
            md.audio_channels = int(astream.get("channels", 0))
            md.audio_sample_rate = int(astream.get("sample_rate", 0))
        return md


@dataclass
class SyntheticSpec:
    """Describes a piece of synthetic footage for tests/demo generation."""

    filename: str
    width: int = 1920
    height: int = 1080
    fps_num: int = 24
    fps_den: int = 1
    duration_seconds: float = 5.0
    video_codec: VideoCodec = VideoCodec.PRORES_422
    audio_channels: int = 2
    audio_sample_rate: int = 48000
    camera_reel: Optional[str] = None
    creation_date: Optional[datetime] = None
    seed: int = 0


class SyntheticMediaProbe(MediaProbe):
    """Deterministically produces metadata for :class:`SyntheticSpec` entries.

    Used so the whole engine — import through export — is exercisable and
    testable without shipping real video assets (spec section 26/27).
    """

    def __init__(self) -> None:
        self._specs: dict[str, SyntheticSpec] = {}

    def register(self, spec: SyntheticSpec) -> None:
        self._specs[spec.filename] = spec

    def supports(self, path: Path) -> bool:
        return path.name in self._specs

    def probe(self, path: Path) -> MediaMetadata:
        spec = self._specs[path.name]
        checksum = hashlib.blake2b(spec.filename.encode(), digest_size=16).hexdigest()
        return MediaMetadata(
            filename=spec.filename,
            file_size_bytes=int(spec.width * spec.height * spec.duration_seconds * 0.1),
            container="mov",
            video_codec=spec.video_codec,
            width=spec.width,
            height=spec.height,
            frame_rate_num=spec.fps_num,
            frame_rate_den=spec.fps_den,
            duration_seconds=spec.duration_seconds,
            colour_space=ColourSpace.REC709,
            audio_codec=AudioCodec.PCM if spec.audio_channels else AudioCodec.NONE,
            audio_channels=spec.audio_channels,
            audio_sample_rate=spec.audio_sample_rate,
            creation_date=spec.creation_date,
            checksum=checksum,
        )


@dataclass
class MediaImporter:
    """Turns files on disk into indexed :class:`MediaAsset` objects."""

    probes: list = field(default_factory=lambda: [SyntheticMediaProbe()])

    def _probe_for(self, path: Path) -> MediaProbe:
        for probe in self.probes:
            if probe.supports(path):
                return probe
        raise RuntimeError(f"No MediaProbe can handle {path}")

    def import_file(self, path: Path) -> MediaAsset:
        probe = self._probe_for(path)
        metadata = probe.probe(path)
        media_file = MediaFile(path=path, metadata=metadata, kind=MediaRepresentationKind.ORIGINAL)
        asset = MediaAsset(name=path.stem, representations=MediaRepresentations(original=media_file))
        return asset

    def import_batch(self, paths: list[Path]) -> list[MediaAsset]:
        return [self.import_file(p) for p in paths]
