#!/usr/bin/env python3
"""FINALCUT ENGINE -- DEMO FILM

An end-to-end walkthrough of every subsystem, using deterministic synthetic
media (no real video/audio files required) so it runs anywhere:

    IMPORT -> ANALYSE -> ORGANISE -> EDIT -> MAGNETIC TIMELINE -> MULTICAM
    -> AUDIO MIX -> COLOUR -> EFFECTS -> AI ASSISTANCE -> RENDER -> EXPORT

Run with: python -m finalcut_engine.examples.demo_film
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import numpy as np

from finalcut_engine.ai.auto_edit import AutoEditAssistant
from finalcut_engine.ai.colour_matching import AIColourMatcher
from finalcut_engine.ai.highlight_detection import ShotFeatures
from finalcut_engine.ai.scene_detection import SceneDetector
from finalcut_engine.ai.semantic_search import SemanticSearchIndex
from finalcut_engine.api.engine_api import EngineAPI
from finalcut_engine.audio.compressor import Compressor
from finalcut_engine.audio.equalizer import EQBand, Equalizer, FilterType
from finalcut_engine.audio.mixer import AudioGraph
from finalcut_engine.audio.track import AudioTrack
from finalcut_engine.colour.colour_board import ColourBoard
from finalcut_engine.colour.colour_pipeline import ColourPipeline
from finalcut_engine.colour.colour_wheels import ColourWheel
from finalcut_engine.colour.exposure import ExposureParams
from finalcut_engine.core.engine import FinalCutEngine
from finalcut_engine.core.timebase import Time, TimeRange
from finalcut_engine.effects.filters import VignetteEffect
from finalcut_engine.effects.sharpen import SharpenEffect
from finalcut_engine.export.exporter import ExportJob, Exporter
from finalcut_engine.export.presets import STANDARD_PRESETS
from finalcut_engine.library.collection import SmartCollection, rule_keyword
from finalcut_engine.media.importer import SyntheticMediaProbe, SyntheticSpec
from finalcut_engine.motion.animation import AnimatedTransform
from finalcut_engine.motion.keyframes import Easing
from finalcut_engine.motion.titles import Title
from finalcut_engine.multicam.angle_switching import AngleSwitcher
from finalcut_engine.multicam.camera_angle import CameraAngle
from finalcut_engine.multicam.multicam_clip import MulticamClip
from finalcut_engine.multicam.synchronizer import MulticamSynchronizer
from finalcut_engine.persistence.autosave import AutosaveManager
from finalcut_engine.persistence.database import Database
from finalcut_engine.persistence.project_store import ProjectStore
from finalcut_engine.persistence.versioning import VersionManager
from finalcut_engine.timeline.clip import Clip
from finalcut_engine.timeline.roles import Role
from finalcut_engine.timeline.transitions import TransitionKind

FRAME_SIZE = (90, 160)  # (height, width) -- kept small so the demo runs in seconds


def _section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# -- synthetic media: deterministic, dependency-free "footage" ---------------
def synthetic_frame(asset_id: str, t: Time, size: tuple[int, int] = FRAME_SIZE) -> np.ndarray:
    """A stable colour per asset, with a gentle animated brightness pulse."""
    digest = int(hashlib.md5(asset_id.encode()).hexdigest(), 16)
    colour = np.array([(digest & 0xFF), (digest >> 8) & 0xFF, (digest >> 16) & 0xFF]) / 255.0
    pulse = 0.85 + 0.15 * np.sin(t.seconds() * 2 * np.pi * 0.4)
    h, w = size
    return np.clip(np.tile(colour, (h, w, 1)) * pulse, 0.0, 1.0)


def synthetic_audio(seed: int, seconds: float, sample_rate: int = 48000) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (0.2 * rng.standard_normal(int(seconds * sample_rate))).astype(np.float32)


def build_library(engine: FinalCutEngine):
    probe: SyntheticMediaProbe = engine.importer.probes[0]
    specs = [
        SyntheticSpec("cam_a_interview.mov", duration_seconds=8.0, camera_reel="A001"),
        SyntheticSpec("cam_b_interview.mov", duration_seconds=8.0, camera_reel="B001"),
        SyntheticSpec("cam_c_interview.mov", duration_seconds=8.0, camera_reel="C001"),
        SyntheticSpec("drone_opening.mov", duration_seconds=4.0),
        SyntheticSpec("street_walk.mov", duration_seconds=3.0),
        SyntheticSpec("product_closeup_1.mov", duration_seconds=2.0),
        SyntheticSpec("product_closeup_2.mov", duration_seconds=2.0),
        SyntheticSpec("city_timelapse.mov", duration_seconds=5.0),
        SyntheticSpec("team_meeting.mov", duration_seconds=4.0),
        SyntheticSpec("establishing_shot.mov", duration_seconds=3.0),
        SyntheticSpec("office_broll.mov", duration_seconds=2.0),
        SyntheticSpec("coffee_broll.mov", duration_seconds=2.0),
        SyntheticSpec("sunset_broll.mov", duration_seconds=3.0),
        SyntheticSpec("closing_card.mov", duration_seconds=3.0),
        SyntheticSpec("music_bed.wav", duration_seconds=30.0, video_codec=None, audio_channels=2),
        SyntheticSpec("voiceover.wav", duration_seconds=10.0, video_codec=None, audio_channels=1),
        SyntheticSpec("street_ambience.wav", duration_seconds=10.0, video_codec=None, audio_channels=2),
    ]
    for i, spec in enumerate(specs):
        if spec.video_codec is None:
            from finalcut_engine.media.metadata import VideoCodec

            spec.video_codec = VideoCodec.UNKNOWN
        probe.register(spec)

    event = engine.library.create_event("Demo Shoot Day 1")
    paths = [Path(s.filename) for s in specs]
    assets = engine.library.import_media(event, paths, engine.importer)
    print(f"Imported {len(assets)} media assets into event {event.name!r}.")
    return event, {a.name: a for a in assets}


def main() -> None:
    _section("IMPORT")
    engine = FinalCutEngine.new("FinalCut Engine Demo Library", frame_loader=synthetic_frame)
    event, assets = build_library(engine)

    _section("ANALYSE")
    scene_detector = SceneDetector(threshold=0.2)
    sample_frames = [synthetic_frame("cam_a_interview", Time.from_seconds(s)) for s in range(4)] + [
        synthetic_frame("street_walk", Time.from_seconds(s)) for s in range(4)
    ]
    suggestions = scene_detector.suggest_cuts(sample_frames)
    print(f"Scene detector found {len(suggestions)} likely shot boundary in the sample reel.")
    for s in suggestions:
        print(f"  - {s.summary} (confidence {s.confidence:.2f})")

    _section("ORGANISE")
    engine.library.tag(assets["sunset_broll"], "sunset")
    engine.library.tag(assets["sunset_broll"], "golden hour")
    engine.library.tag(assets["street_walk"], "b-roll")
    engine.library.tag(assets["office_broll"], "b-roll")
    engine.library.tag(assets["coffee_broll"], "b-roll")
    engine.library.tag(assets["cam_a_interview"], "interview")
    from finalcut_engine.library.ratings import Rating

    engine.library.ratings.set(assets["drone_opening"].id, Rating.FAVOURITE)
    engine.library.ratings.set(assets["product_closeup_1"].id, Rating.FAVOURITE)
    broll_collection = engine.library.add_smart_collection(SmartCollection("B-Roll", [rule_keyword("b-roll")]))
    print(f"Smart collection 'B-Roll' matches: {[a.name for a in broll_collection.evaluate(engine.library)]}")
    print(f"Favourites: {[a.name for a in engine.library.all_assets() if engine.library.ratings.get(a.id).name == 'FAVOURITE']}")

    _section("MULTICAM")
    sync = MulticamSynchronizer()
    audio_by_angle = {"A": synthetic_audio(1, 8.0), "B": synthetic_audio(1, 8.0), "C": synthetic_audio(1, 8.0)}
    # Simulate real recorder drift: B and C started fractionally after A.
    audio_by_angle["B"] = np.concatenate([np.zeros(int(0.3 * 48000), dtype=np.float32), audio_by_angle["B"]])[: len(audio_by_angle["A"])]
    audio_by_angle["C"] = np.concatenate([np.zeros(int(0.6 * 48000), dtype=np.float32), audio_by_angle["C"]])[: len(audio_by_angle["A"])]
    sync_result = sync.sync_by_waveform(audio_by_angle, 48000)
    print(f"Multicam sync offsets: { {k: round(v.seconds(), 2) for k, v in sync_result.offsets.items()} }")

    angles = {
        name: CameraAngle(name, f"cam_{name.lower()}_interview", offset, TimeRange(Time.zero(), Time.from_seconds(8.0)))
        for name, offset in sync_result.offsets.items()
    }
    multicam = MulticamClip("Interview Multicam", angles, AngleSwitcher(default_angle="A"))
    multicam.switch_angle(Time.from_seconds(2.5), "B")
    multicam.switch_angle(Time.from_seconds(5.0), "C")
    flattened = multicam.flatten()
    print(f"Multicam clip duration: {multicam.duration.seconds():.2f}s, flattened into {len(flattened.items)} cuts.")

    _section("EDIT / MAGNETIC TIMELINE")
    api = EngineAPI(engine)
    project = engine.create_project("Demo Film")
    timeline = project.create_timeline("Main Sequence")

    def clip_for(asset_name: str, duration: float | None = None, role: Role | None = None) -> Clip:
        asset = assets[asset_name]
        dur = duration if duration is not None else asset.metadata.duration_seconds
        kwargs = {"role": role} if role is not None else {}
        return Clip(asset_id=asset_name, source_range=TimeRange(Time.zero(), Time.from_seconds(dur)), name=asset_name, **kwargs)

    drone = api.append_clip(timeline, clip_for("drone_opening"))
    for item in flattened.items:  # the multicam interview, already cut A->B->C
        api.append_clip(timeline, item)
    meeting = api.append_clip(timeline, clip_for("team_meeting"))
    establishing = api.append_clip(timeline, clip_for("establishing_shot"))
    closing = api.append_clip(timeline, clip_for("closing_card"))

    api.add_transition(timeline, drone.id, Time.from_seconds(0.75), kind=TransitionKind.CROSS_DISSOLVE)
    api.add_transition(timeline, establishing.id, Time.from_seconds(1.0), kind=TransitionKind.CROSS_DISSOLVE)

    api.connect_clip(timeline, meeting.id, clip_for("street_walk"), Time.from_seconds(0.5), lane=1)
    api.connect_clip(timeline, meeting.id, clip_for("office_broll"), Time.from_seconds(2.5), lane=1)
    api.connect_clip(timeline, establishing.id, clip_for("coffee_broll"), Time.zero(), lane=2)

    voiceover_clip = clip_for("voiceover", role=Role("Dialogue", "Narration"))
    music_clip = clip_for("music_bed", 12.0, role=Role("Music"))
    ambience_clip = clip_for("street_ambience", 6.0, role=Role("Ambience"))
    api.connect_clip(timeline, drone.id, voiceover_clip, Time.zero(), lane=-1)
    api.connect_clip(timeline, drone.id, music_clip, Time.zero(), lane=-2)
    api.connect_clip(timeline, meeting.id, ambience_clip, Time.zero(), lane=-1)

    intro_ids = [drone.id] + [i.id for i in timeline.primary.items[1 : 1 + len(flattened.items)]]
    compound = api.create_compound_clip(timeline, intro_ids, name="Cold Open")
    print(f"Timeline built: {len(timeline.primary.items)} primary item(s), {len(timeline.connected)} connected clip(s).")
    print(f"Total programme duration: {timeline.duration.seconds():.2f}s")

    _section("COLOUR")
    warm_look = ColourPipeline(
        name="Warm Interview Look",
        colour=ColourBoard(exposure=ExposureParams(exposure_stops=0.15, saturation=1.1), wheels=ColourWheel(lift=(0.02, 0.0, -0.02))),
    )
    compound.nested.items[1].colour_grade = warm_look  # the first interview angle cut

    matcher = AIColourMatcher(min_confidence=0.0)
    reference_frame = synthetic_frame("cam_a_interview", Time.zero())
    target_frame = synthetic_frame("street_walk", Time.zero())
    match_suggestion = matcher.suggest(reference_frame, target_frame, target_clip_name="street_walk")
    if match_suggestion:
        print(f"AI colour match suggestion: {match_suggestion.summary} (confidence {match_suggestion.confidence:.2f})")
        match_suggestion.accept()
        for connected in timeline.connected.values():
            if isinstance(connected.item, Clip) and connected.item.asset_id == "street_walk":
                connected.item.colour_grade = ColourPipeline(colour=ColourBoard(wheels=ColourWheel(**match_suggestion.payload)))

    _section("EFFECTS")
    for connected in timeline.connected.values():
        if isinstance(connected.item, Clip) and connected.item.asset_id in ("office_broll", "coffee_broll"):
            connected.item.effects = [VignetteEffect(strength=0.4), SharpenEffect(amount=0.3)]

    ken_burns = AnimatedTransform()
    ken_burns.scale_x.default = ken_burns.scale_y.default = 1.0
    ken_burns.scale_x.add(Time.zero(), 1.0, Easing.LINEAR)
    ken_burns.scale_x.add(Time.from_seconds(3.0), 1.15, Easing.LINEAR)
    ken_burns.scale_y.add(Time.zero(), 1.0, Easing.LINEAR)
    ken_burns.scale_y.add(Time.from_seconds(3.0), 1.15, Easing.LINEAR)
    closing.transform = ken_burns.as_callable()

    lower_third = Title(text="DEMO FILM 2026", position=(0.5, 0.88))
    lower_third.opacity_track.add(Time.zero(), 0.0, Easing.EASE_OUT)
    lower_third.opacity_track.add(Time.from_seconds(0.5), 1.0, Easing.LINEAR)
    print("Applied vignette/sharpen to b-roll, a Ken Burns move to the closing card, and a lower-third title.")

    _section("AUDIO MIX")
    graph = AudioGraph()
    dialogue_track = AudioTrack("Dialogue", role=Role("Dialogue"))
    dialogue_eq = Equalizer().add_band(EQBand(FilterType.HIGH_PASS, 90))
    graph.add_track(dialogue_track, eq=dialogue_eq, compressor=Compressor(threshold_db=-20, ratio=3.0))

    music_track = AudioTrack("Music", role=Role("Music"))
    music_track.fade_out = Time.from_seconds(1.5)
    music_track.add_keyframe(Time.zero(), -6.0)
    graph.add_track(music_track)

    ambience_track = AudioTrack("Ambience", role=Role("Ambience"))
    ambience_track.add_keyframe(Time.zero(), -12.0)
    graph.add_track(ambience_track)

    dialogue_samples = synthetic_audio(2, 8.0)
    music_samples = synthetic_audio(3, 12.0)
    ambience_samples = synthetic_audio(4, 6.0)
    processed = {
        "Dialogue": graph.process_channel("Dialogue", dialogue_samples, 48000, Time.zero()),
        "Music": graph.process_channel("Music", music_samples, 48000, Time.zero()),
        "Ambience": graph.process_channel("Ambience", ambience_samples, 48000, Time.zero()),
    }
    master = graph.mix(processed, 48000)
    print(f"Mixed {len(processed)} tracks -> master bus, {master.shape[0]} samples, peak={np.abs(master).max():.3f}")

    _section("AI ASSISTANCE")
    shots = [
        ShotFeatures("drone_opening", 0.6, 0.3, False, 4.0, content_group="drone_opening"),
        ShotFeatures("interview_A", 0.2, 0.7, True, 2.5, content_group="interview"),
        ShotFeatures("interview_B", 0.3, 0.75, True, 2.5, content_group="interview"),
        ShotFeatures("team_meeting", 0.4, 0.5, True, 4.0, content_group="team_meeting"),
        ShotFeatures("establishing_shot", 0.1, 0.2, False, 3.0, content_group="establishing_shot"),
        ShotFeatures("closing_card", 0.05, 0.1, False, 3.0, content_group="closing_card"),
    ]
    assistant = AutoEditAssistant()
    plan = assistant.propose_edit(shots, target_duration_seconds=14.0)
    print(f"AI Auto-Edit proposes: {plan.shot_ids} (total {plan.total_duration_seconds:.1f}s)")
    for suggestion in plan.suggestions:
        print(f"  AI SUGGESTION: {suggestion.summary}\n  Reason: {suggestion.reason}\n  [ACCEPT] [REJECT]")

    search_index = SemanticSearchIndex()
    for asset in engine.library.all_assets():
        search_index.add_document(asset.id, asset.searchable_text() + " " + " ".join(engine.library.keywords.keywords_for(asset.id)))
    results = search_index.search("sunset footage", top_k=3)
    named_results = [(engine.library.find_asset(aid).name, round(score, 3)) for aid, score in results]
    print(f"Semantic search 'sunset footage' -> {named_results}")

    _section("RENDER")
    render_engine = engine.render_engine
    render_engine.frame_size = FRAME_SIZE
    sample_times = [0.0, 2.0, 6.0, 12.0, timeline.duration.seconds() - 0.1]
    for t in sample_times:
        frame = render_engine.render_frame(timeline, Time.from_seconds(max(0.0, t)))
        print(f"  rendered frame @ {t:5.2f}s -> shape={frame.shape}, mean colour={frame.mean(axis=(0, 1)).round(2)}")
    print(f"Render cache: {render_engine.cache.stats.hits} hits / {render_engine.cache.stats.misses} misses")

    _section("EXPORT")
    output_dir = Path("/tmp/finalcut_engine_demo_export")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    exporter = Exporter(render_engine=render_engine)
    preset = STANDARD_PRESETS["Web"]
    job = ExportJob(timeline=timeline, preset=preset, output_dir=output_dir, end=Time.from_seconds(2.0))
    manifest = exporter.export(job)
    print(f"Exported {manifest.frame_count} frames ({manifest.preset_name}, {manifest.width}x{manifest.height}) to {manifest.output_dir}")

    _section("PERSISTENCE")
    db_dir = Path("/tmp/finalcut_engine_demo_project")
    if db_dir.exists():
        shutil.rmtree(db_dir)
    db = Database(db_dir / "project.db")
    store = ProjectStore(db)
    store.save(project)
    versions = VersionManager(db)
    versions.snapshot(project, label="After first cut")
    autosave = AutosaveManager(recovery_dir=db_dir / "recovery", interval_seconds=0)
    autosave.maybe_autosave(project)
    print(f"Project saved to {db_dir/'project.db'} (integrity check: {db.integrity_check()})")
    print(f"Version snapshots on file: {len(versions.list_versions(project.id))}")
    db.close()

    engine.shutdown()
    _section("DONE")
    print("FinalCut Engine demo film pipeline completed successfully.")


if __name__ == "__main__":
    main()
