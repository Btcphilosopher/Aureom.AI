"""Speech-to-text: transcript, captions, and subtitle timing.

The dependency-free reference implementation detects *when* speech is
happening (energy-gated voice activity detection) and honestly labels those
spans as ``"[speech]"`` rather than fabricating word-level text — inventing
plausible-looking transcript words with no real speech model behind them
would be a worse prototype than being explicit about the gap. Swap in
``WhisperTranscriber`` (or any real ASR engine) for actual word-level text;
callers only depend on the ``SpeechToText`` protocol.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol, TypedDict

import numpy as np

from finalcut_engine.media.analyzer import measure_audio_levels


class TranscriptSegment(TypedDict):
    start_seconds: float
    end_seconds: float
    text: str
    confidence: float


class SpeechToText(Protocol):
    def transcribe(self, samples: np.ndarray, sample_rate: int) -> List[TranscriptSegment]: ...


@dataclass
class VoiceActivityTranscriber:
    """Energy-gated voice-activity detector, framed as a (word-less) transcript."""

    frame_ms: float = 30.0
    silence_threshold_dbfs: float = -40.0
    min_segment_ms: float = 200.0

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> List[TranscriptSegment]:
        frame_len = max(1, int(sample_rate * self.frame_ms / 1000))
        n_frames = len(samples) // frame_len
        active = []
        for i in range(n_frames):
            chunk = samples[i * frame_len : (i + 1) * frame_len]
            levels = measure_audio_levels(chunk.astype(np.float32))
            active.append(levels.rms_dbfs > self.silence_threshold_dbfs)

        segments: List[TranscriptSegment] = []
        start = None
        for i, is_active in enumerate(active + [False]):
            if is_active and start is None:
                start = i
            elif not is_active and start is not None:
                start_s = start * self.frame_ms / 1000
                end_s = i * self.frame_ms / 1000
                if (end_s - start_s) * 1000 >= self.min_segment_ms:
                    segments.append(TranscriptSegment(start_seconds=start_s, end_seconds=end_s, text="[speech]", confidence=0.5))
                start = None
        return segments


def load_whisper_transcriber(model_size: str = "base") -> SpeechToText:
    """Extension point for a real ASR engine; raises clearly if unavailable."""
    try:
        import whisper  # type: ignore  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            f"Loading a Whisper('{model_size}') model requires the 'openai-whisper' package, which is not "
            "installed. Use VoiceActivityTranscriber for the dependency-free reference path."
        ) from exc
    raise NotImplementedError("Native model loading is an integration point for a real deployment.")
