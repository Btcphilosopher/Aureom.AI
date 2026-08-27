"""Saving/loading :class:`~finalcut_engine.core.project.Project` to the database."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from finalcut_engine.core.project import Project, project_from_dict, project_to_dict
from finalcut_engine.persistence.database import Database


@dataclass
class ProjectStore:
    db: Database

    def save(self, project: Project, library_id: Optional[str] = None) -> None:
        payload = json.dumps(project_to_dict(project))
        now = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, library_id, name, data, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET library_id=excluded.library_id, name=excluded.name,
                    data=excluded.data, updated_at=excluded.updated_at
                """,
                (project.id, library_id, project.name, payload, now),
            )

    def load(self, project_id: str) -> Project:
        row = self.db.conn.execute("SELECT data FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"no project with id {project_id!r}")
        return project_from_dict(json.loads(row[0]))

    def delete(self, project_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def list_projects(self) -> List[tuple[str, str, str]]:
        """Returns (id, name, updated_at) for every stored project."""
        rows = self.db.conn.execute("SELECT id, name, updated_at FROM projects ORDER BY updated_at DESC").fetchall()
        return [tuple(r) for r in rows]
