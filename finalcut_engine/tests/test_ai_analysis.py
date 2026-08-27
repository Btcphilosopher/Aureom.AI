from __future__ import annotations

import numpy as np

from finalcut_engine.ai.auto_edit import AutoEditAssistant
from finalcut_engine.ai.highlight_detection import ShotFeatures, compute_audio_intensity, compute_motion_score
from finalcut_engine.ai.scene_detection import SceneDetector
from finalcut_engine.ai.semantic_search import SemanticSearchIndex
from finalcut_engine.ai.speech_to_text import VoiceActivityTranscriber
from finalcut_engine.media.analyzer import is_black_frame


def test_scene_detector_finds_hard_cut():
    frames = [np.zeros((8, 8, 3))] * 3 + [np.ones((8, 8, 3))] * 3
    suggestions = SceneDetector().suggest_cuts(frames)
    assert len(suggestions) == 1
    assert suggestions[0].payload["frame_index"] == 3
    assert suggestions[0].confidence > 0.9


def test_is_black_frame_handles_float_and_uint8_consistently():
    assert is_black_frame(np.zeros((4, 4, 3)))  # float [0,1]
    assert not is_black_frame(np.ones((4, 4, 3)))
    assert is_black_frame(np.zeros((4, 4, 3), dtype=np.uint8))
    assert not is_black_frame(np.full((4, 4, 3), 255, dtype=np.uint8))


def test_motion_score_is_zero_for_static_shot_and_positive_for_motion():
    static = [np.full((4, 4, 3), 0.5)] * 5
    moving = [np.random.default_rng(i).uniform(0, 1, (4, 4, 3)) for i in range(5)]
    assert compute_motion_score(static) == 0.0
    assert compute_motion_score(moving) > 0.0


def test_voice_activity_transcriber_finds_the_active_segment():
    sr = 16000
    rng = np.random.default_rng(0)
    silence = np.zeros(sr)
    speech = 0.3 * rng.standard_normal(sr)
    samples = np.concatenate([silence, speech, silence]).astype(np.float32)

    segments = VoiceActivityTranscriber().transcribe(samples, sr)
    assert len(segments) == 1
    assert 0.9 < segments[0]["start_seconds"] < 1.1
    assert 1.9 < segments[0]["end_seconds"] < 2.1


def test_auto_edit_prefers_stronger_take_and_fits_duration():
    shots = [
        ShotFeatures("weak_take", 0.2, 0.1, False, 3.0, content_group="intro"),
        ShotFeatures("strong_take", 0.8, 0.8, True, 3.0, content_group="intro"),
        ShotFeatures("filler", 0.1, 0.1, False, 20.0, content_group="filler"),
    ]
    plan = AutoEditAssistant().propose_edit(shots, target_duration_seconds=5.0)

    assert "strong_take" in plan.shot_ids
    assert "weak_take" not in plan.shot_ids
    assert plan.total_duration_seconds <= 5.0
    replace_suggestions = [s for s in plan.suggestions if s.kind == "replace_clip"]
    assert any(s.payload["keep_shot_id"] == "strong_take" for s in replace_suggestions)


def test_semantic_search_ranks_matching_document_first():
    index = SemanticSearchIndex()
    index.add_document("a", "a beautiful sunset over the ocean with orange sky")
    index.add_document("b", "two people talking in an interview about business")
    index.add_document("c", "a car driving fast down the highway at night")

    results = index.search("sunset")
    assert results[0][0] == "a"
