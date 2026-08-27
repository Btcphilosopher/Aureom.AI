"""Representation of a single file on disk and its ProRes/proxy workflow state.

Kept deliberately separate from :class:`~finalcut_engine.media.asset.MediaAsset`:
a ``MediaFile`` is "a file plus its probed technical metadata"; an asset is the
*library* object built around one (or more, via proxy/optimised linking).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from finalcut_engine.media.metadata import MediaMetadata


class MediaRepresentationKind(str, Enum):
    """Which rung of the ProRes/proxy ladder a file represents (spec section 7)."""

    ORIGINAL = "original"
    OPTIMIZED = "optimized"  # transcoded to ProRes 422 for smooth original-quality editing
    PROXY = "proxy"  # lightweight ProRes Proxy/LT for fast editing


@dataclass
class MediaFile:
    """A single physical file plus its probed metadata."""

    path: Path
    metadata: MediaMetadata
    kind: MediaRepresentationKind = MediaRepresentationKind.ORIGINAL
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def exists(self) -> bool:
        return self.path.exists()

    @property
    def is_missing(self) -> bool:
        return not self.exists()


@dataclass
class MediaRepresentations:
    """The set of representations available for one logical piece of footage.

    Editing can transparently prefer proxy/optimised media and relink to the
    original for final render (spec section 7's "proxy switching").
    """

    original: MediaFile
    optimized: Optional[MediaFile] = None
    proxy: Optional[MediaFile] = None

    def best_for(self, prefer_proxy: bool) -> MediaFile:
        if prefer_proxy and self.proxy is not None and self.proxy.exists():
            return self.proxy
        if self.optimized is not None and self.optimized.exists():
            return self.optimized
        return self.original

    def relink_original(self, new_path: Path) -> None:
        """Repoint the original when source media has moved (spec section 7 relinking)."""
        self.original = MediaFile(
            path=new_path, metadata=self.original.metadata, kind=MediaRepresentationKind.ORIGINAL, id=self.original.id
        )

    def has_proxy(self) -> bool:
        return self.proxy is not None and self.proxy.exists()

    def is_online(self) -> bool:
        """Whether *any* representation is currently reachable on disk."""
        return any(mf is not None and mf.exists() for mf in (self.original, self.optimized, self.proxy))
