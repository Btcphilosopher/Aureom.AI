"""An Event: the organisational unit inside a Library grouping media + projects.

Mirrors Final Cut Pro's Library > Event > Project hierarchy (spec section 5).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List

from finalcut_engine.media.asset import MediaAsset

if TYPE_CHECKING:  # pragma: no cover
    from finalcut_engine.core.project import Project


@dataclass
class Event:
    name: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = field(default_factory=datetime.utcnow)
    assets: Dict[str, MediaAsset] = field(default_factory=dict)
    projects: Dict[str, "Project"] = field(default_factory=dict)

    def add_asset(self, asset: MediaAsset) -> MediaAsset:
        self.assets[asset.id] = asset
        return asset

    def add_project(self, project: "Project") -> "Project":
        self.projects[project.id] = project
        return project

    def asset_list(self) -> List[MediaAsset]:
        return list(self.assets.values())
