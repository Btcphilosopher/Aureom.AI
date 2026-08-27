"""Project versioning: named snapshots you can list and restore."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from finalcut_engine.core.project import Project, project_from_dict, project_to_dict
from finalcut_engine.persistence.database import Database


@dataclass(frozen=True)
class VersionInfo:
    id: str
    project_id: str
    label: Optional[str]
    created_at: str


@dataclass
class VersionManager:
    db: Database

    def snapshot(self, project: Project, label: Optional[str] = None) -> VersionInfo:
        version_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(project_to_dict(project))
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO project_versions (id, project_id, label, data, created_at) VALUES (?, ?, ?, ?, ?)",
                (version_id, project.id, label, payload, now),
            )
        return VersionInfo(id=version_id, project_id=project.id, label=label, created_at=now)

    def list_versions(self, project_id: str) -> List[VersionInfo]:
        rows = self.db.conn.execute(
            "SELECT id, project_id, label, created_at FROM project_versions WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        return [VersionInfo(*row) for row in rows]

    def restore(self, version_id: str) -> Project:
        row = self.db.conn.execute("SELECT data FROM project_versions WHERE id = ?", (version_id,)).fetchone()
        if row is None:
            raise KeyError(f"no version with id {version_id!r}")
        return project_from_dict(json.loads(row[0]))
