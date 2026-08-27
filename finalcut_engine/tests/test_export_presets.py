from __future__ import annotations

import json

import numpy as np

from finalcut_engine.core.timebase import FPS_24, Time, TimeRange
from finalcut_engine.export.exporter import ExportJob, Exporter
from finalcut_engine.export.presets import STANDARD_PRESETS
from finalcut_engine.render.render_engine import RenderEngine
from finalcut_engine.timeline.clip import Clip
from finalcut_engine.timeline.magnetic_timeline import MagneticTimeline


def test_all_standard_presets_are_present_and_well_formed():
    expected = {"Master", "ProRes", "H.264", "HEVC", "Web", "Social", "Archive", "Audio-only"}
    assert set(STANDARD_PRESETS) == expected
    for preset in STANDARD_PRESETS.values():
        assert preset.frame_rate.fps > 0
        assert preset.audio is not None


def test_export_writes_expected_frame_count_and_manifest(tmp_path, synthetic_frame_loader):
    tl = MagneticTimeline(frame_rate=FPS_24)
    tl.append_clip(Clip(asset_id="X", source_range=TimeRange(Time.zero(), Time.from_seconds(1.0))))
    engine = RenderEngine(frame_loader=synthetic_frame_loader, frame_size=(4, 4))
    exporter = Exporter(render_engine=engine)

    job = ExportJob(timeline=tl, preset=STANDARD_PRESETS["Web"], output_dir=tmp_path / "export")
    manifest = exporter.export(job)

    assert manifest.frame_count == 24  # 1 second at 24fps
    frame_files = sorted((tmp_path / "export").glob("*.ppm"))
    assert len(frame_files) == 24

    manifest_data = json.loads((tmp_path / "export" / "manifest.json").read_text())
    assert manifest_data["frame_count"] == 24
    assert manifest_data["preset_name"] == "Web"


def test_export_batch_runs_every_job(tmp_path, synthetic_frame_loader):
    tl = MagneticTimeline(frame_rate=FPS_24)
    tl.append_clip(Clip(asset_id="X", source_range=TimeRange(Time.zero(), Time.from_seconds(0.5))))
    engine = RenderEngine(frame_loader=synthetic_frame_loader, frame_size=(4, 4))
    exporter = Exporter(render_engine=engine)

    jobs = [
        ExportJob(timeline=tl, preset=STANDARD_PRESETS["Web"], output_dir=tmp_path / "a"),
        ExportJob(timeline=tl, preset=STANDARD_PRESETS["Social"], output_dir=tmp_path / "b"),
    ]
    manifests = exporter.export_batch(jobs)
    assert len(manifests) == 2
    assert {m.preset_name for m in manifests} == {"Web", "Social"}
