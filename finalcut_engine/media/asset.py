"""The library-facing wrapper around imported media: a :class:`MediaAsset`."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from finalcut_engine.media.media_file import MediaRepresentations


@dataclass
class MediaAsset:
    """One logical piece of footage/audio as it appears in the library.

    Wraps a :class:`MediaRepresentations` (original/optimised/proxy files) plus
    everything the library needs to index and search without re-scanning:
    thumbnail/waveform cache paths and AI analysis results.
    """

    name: str
    representations: MediaRepresentations
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    imported_at: datetime = field(default_factory=datetime.utcnow)

    thumbnail_path: Optional[str] = None
    waveform_cache_path: Optional[str] = None

    #: Free-form results from ai.* analyzers, keyed by analyzer name, e.g.
    #: {"scene_detection": [...], "transcript": [...]}. Populated lazily and
    #: never required for basic editing — see spec section 13.
    analysis: Dict[str, Any] = field(default_factory=dict)

    @property
    def metadata(self):
        return self.representations.original.metadata

    def is_analyzed(self, analyzer_name: str) -> bool:
        return analyzer_name in self.analysis

    def set_analysis(self, analyzer_name: str, result: Any) -> None:
        self.analysis[analyzer_name] = result

    def searchable_text(self) -> str:
        """Flattened text used by keyword/smart-collection search."""
        md = self.metadata
        parts = [self.name, md.container, md.video_codec.value, md.audio_codec.value]
        if md.camera.make:
            parts.append(md.camera.make)
        if md.camera.model:
            parts.append(md.camera.model)
        if md.camera.reel_name:
            parts.append(md.camera.reel_name)
        transcript = self.analysis.get("transcript")
        if transcript:
            parts.append(" ".join(seg.get("text", "") for seg in transcript))
        return " ".join(parts).lower()
