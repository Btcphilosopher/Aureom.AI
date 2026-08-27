"""The export engine: a graph independent from the editing timeline.

An export walks a *snapshot* of timing (start/end, frame rate) and asks the
render engine for each frame in turn — it never touches the live
``MagneticTimeline`` structures beyond reading them, so exporting cannot be
affected by (or interfere with) concurrent editing. Actual muxing to a real
``.mov``/``.mp4`` container is a native-encoder concern
(AVAssetWriter/VideoToolbox); :class:`PPMSequenceEncoder` is an honest,
inspectable stand-in — a numbered image sequence plus a JSON manifest — that
demonstrates the full render-to-export pipeline without pretending to
produce a real, hardware-encoded container.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Protocol

import numpy as np

from finalcut_engine.core.timebase import Time
from finalcut_engine.export.presets import ExportPreset
from finalcut_engine.media.thumbnails import ThumbnailGenerator
from finalcut_engine.render.render_engine import RenderEngine
from finalcut_engine.timeline.magnetic_timeline import MagneticTimeline


class VideoEncoder(Protocol):
    def encode_frame(self, frame: np.ndarray, frame_index: int) -> None: ...
    def finish(self) -> None: ...


@dataclass
class PPMSequenceEncoder:
    output_dir: Path
    _writer: ThumbnailGenerator = field(default_factory=ThumbnailGenerator)

    def __post_init__(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def encode_frame(self, frame: np.ndarray, frame_index: int) -> None:
        self._writer.save_ppm(frame, self.output_dir / f"frame_{frame_index:06d}.ppm")

    def finish(self) -> None:
        pass


@dataclass
class ExportJob:
    timeline: MagneticTimeline
    preset: ExportPreset
    output_dir: Path
    start: Time = field(default_factory=Time.zero)
    end: Time | None = None

    def resolved_end(self) -> Time:
        return self.end if self.end is not None else self.timeline.duration


@dataclass
class ExportManifest:
    preset_name: str
    container: str
    width: int
    height: int
    frame_rate_fps: float
    frame_count: int
    duration_seconds: float
    output_dir: str

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.__dict__, indent=2))


@dataclass
class Exporter:
    render_engine: RenderEngine

    def export(self, job: ExportJob, encoder: VideoEncoder | None = None) -> ExportManifest:
        end = job.resolved_end()
        fps = job.preset.frame_rate
        frame_duration = fps.frame_duration()
        encoder = encoder or PPMSequenceEncoder(job.output_dir)

        frame_index = 0
        t = job.start
        while t < end:
            frame = self.render_engine.render_frame(job.timeline, t)
            frame_uint8 = frame if frame.dtype == np.uint8 else np.clip(frame * 255.0, 0, 255).astype(np.uint8)
            encoder.encode_frame(frame_uint8, frame_index)
            frame_index += 1
            t = t + frame_duration
        encoder.finish()

        manifest = ExportManifest(
            preset_name=job.preset.name,
            container=job.preset.container,
            width=job.preset.width,
            height=job.preset.height,
            frame_rate_fps=fps.fps,
            frame_count=frame_index,
            duration_seconds=(end - job.start).seconds(),
            output_dir=str(job.output_dir),
        )
        job.output_dir.mkdir(parents=True, exist_ok=True)
        manifest.write(job.output_dir / "manifest.json")
        return manifest

    def export_batch(self, jobs: List[ExportJob]) -> List[ExportManifest]:
        return [self.export(job) for job in jobs]
