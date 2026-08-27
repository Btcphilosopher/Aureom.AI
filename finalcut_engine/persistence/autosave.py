"""Autosave and crash recovery.

Writes to a location separate from the user's explicit saves, so an
in-progress (possibly mid-edit, not-yet-saved) state can be recovered after a
crash without clobbering the last deliberate save. Poll-based (call
``maybe_autosave`` periodically, e.g. from a UI tick or timer) rather than a
background thread, so behaviour stays deterministic and easy to test.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from finalcut_engine.core.project import Project, project_from_dict, project_to_dict


@dataclass
class AutosaveManager:
    recovery_dir: Path
    interval_seconds: float = 120.0
    _last_save_time: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.recovery_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, project_id: str) -> Path:
        return self.recovery_dir / f"{project_id}.recovery.json"

    def maybe_autosave(self, project: Project, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.time()
        last = self._last_save_time.get(project.id, 0.0)
        if now - last < self.interval_seconds:
            return False
        self.force_autosave(project)
        self._last_save_time[project.id] = now
        return True

    def force_autosave(self, project: Project) -> Path:
        path = self._path_for(project.id)
        path.write_text(json.dumps(project_to_dict(project)))
        return path

    def has_recovery(self, project_id: str) -> bool:
        return self._path_for(project_id).exists()

    def recover(self, project_id: str) -> Optional[Project]:
        path = self._path_for(project_id)
        if not path.exists():
            return None
        return project_from_dict(json.loads(path.read_text()))

    def clear_recovery(self, project_id: str) -> None:
        path = self._path_for(project_id)
        if path.exists():
            path.unlink()
