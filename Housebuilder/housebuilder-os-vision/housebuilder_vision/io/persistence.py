"""SQLite project store: validated project state, image registry and a reproducibility run log.

:class:`ProjectStore` keeps

* ``projects``  - one row per project with the complete state as JSON
  (``Project.model_dump_json``) and its model schema version;
* ``images``    - content-addressed image registry (``sha256`` primary key) with
  filename, media type, kind, view, stored path and size - the original bytes live
  wherever the ingest module stored them (``stored_path``);
* ``project_images`` - which project uses which image;
* ``runs``      - reproducibility log of engine calls (function, timestamp, input /
  output sha256, seed, library versions, note), mirroring :class:`RunRecord`;
* ``schema_version`` - applied store migrations.

Rules and boundaries
--------------------
* Only parameterised SQL is used; values never become SQL text.
* State read back from the database is untrusted: it is size-checked and
  validated with ``Project.model_validate_json`` before use; a project whose model
  schema has a different *major* version is refused (no silent reinterpretation).
* The database runs in WAL mode with foreign keys on; every write is one
  transaction.  The store is safe to share between threads of one process (a lock
  serialises access); separate processes rely on SQLite locking (``busy_timeout``).
* Default location: ``$HBV_DATA_DIR/housebuilder.db``, else ``./.hbv/housebuilder.db``.
  ``":memory:"`` gives a throw-away store (useful in tests).
* The store records what was computed; it does not certify anything and holds no
  credentials.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..core.models import SCHEMA_VERSION, ImageAsset, Project, RunRecord
from ..core.provenance import utcnow

DATA_DIR_ENV = "HBV_DATA_DIR"
DEFAULT_DIR_NAME = ".hbv"
DEFAULT_DB_NAME = "housebuilder.db"
#: Largest project state accepted from the database (bytes of JSON).
MAX_STATE_BYTES = 256 * 1024 * 1024


class StoreError(RuntimeError):
    """The store cannot be opened / migrated, or stored data is invalid."""


class ProjectNotFound(KeyError):
    """No project with this id is stored."""


# =============================================================================
# Migrations
# =============================================================================
def _m1(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE projects (
            project_id     TEXT PRIMARY KEY,
            name           TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            state_json     TEXT NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE images (
            sha256      TEXT PRIMARY KEY CHECK (length(sha256) = 64),
            image_id    TEXT NOT NULL,
            filename    TEXT NOT NULL DEFAULT '',
            media_type  TEXT NOT NULL DEFAULT '',
            kind        TEXT NOT NULL DEFAULT 'unknown',
            view        TEXT NOT NULL DEFAULT 'unknown',
            stored_path TEXT,
            size_bytes  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL
        )""")
    conn.execute("CREATE INDEX idx_images_image_id ON images(image_id)")
    conn.execute("""
        CREATE TABLE project_images (
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            image_id   TEXT NOT NULL,
            PRIMARY KEY (project_id, image_id)
        )""")
    conn.execute("""
        CREATE TABLE runs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id     TEXT,
            function       TEXT NOT NULL,
            timestamp      TEXT NOT NULL,
            inputs_sha256  TEXT NOT NULL DEFAULT '',
            outputs_sha256 TEXT NOT NULL DEFAULT '',
            seed           INTEGER,
            versions_json  TEXT NOT NULL DEFAULT '{}',
            note           TEXT NOT NULL DEFAULT ''
        )""")
    conn.execute("CREATE INDEX idx_runs_project ON runs(project_id, id)")


#: Ordered store migrations: (version, description, function).  Append only.
MIGRATIONS: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "initial schema: projects, images, project_images, runs", _m1),
]
STORE_SCHEMA_VERSION = MIGRATIONS[-1][0]


# =============================================================================
# Records
# =============================================================================
class ProjectSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    name: str
    schema_version: str
    created_at: datetime
    updated_at: datetime
    image_count: int = 0
    run_count: int = 0


class ImageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: str
    image_id: str
    filename: str = ""
    media_type: str = ""
    kind: str = "unknown"
    view: str = "unknown"
    stored_path: Optional[str] = None
    size_bytes: int = 0
    created_at: datetime


class StoredRun(BaseModel):
    """A logged engine call (``runs`` row)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: Optional[str] = None
    function: str
    timestamp: datetime
    inputs_sha256: str = ""
    outputs_sha256: str = ""
    seed: Optional[int] = None
    versions: dict[str, str] = Field(default_factory=dict)
    note: str = ""

    def to_record(self) -> RunRecord:
        return RunRecord(function=self.function, timestamp=self.timestamp, inputs_sha256=self.inputs_sha256,
                         outputs_sha256=self.outputs_sha256, seed=self.seed, versions=dict(self.versions),
                         note=self.note)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _major(version: str) -> str:
    return str(version).split(".", 1)[0]


def default_db_path() -> Path:
    """``$HBV_DATA_DIR/housebuilder.db`` or ``./.hbv/housebuilder.db``."""
    base = os.environ.get(DATA_DIR_ENV)
    return (Path(base) if base else Path.cwd() / DEFAULT_DIR_NAME) / DEFAULT_DB_NAME


# =============================================================================
# Store
# =============================================================================
class ProjectStore:
    """SQLite-backed project store (see module docstring).  Use as a context manager."""

    def __init__(self, db_path: Union[str, Path, None] = None, *, timeout_s: float = 10.0):
        if db_path is None:
            db_path = default_db_path()
        self.memory = str(db_path) == ":memory:"
        self.path: Union[Path, str] = ":memory:" if self.memory else Path(db_path)
        if not self.memory:
            assert isinstance(self.path, Path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        try:
            self._conn: Optional[sqlite3.Connection] = sqlite3.connect(
                str(self.path), timeout=timeout_s, isolation_level=None, check_same_thread=False)
        except sqlite3.Error as e:
            raise StoreError(f"cannot open project store: {e}") from e
        conn = self._conn
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {int(timeout_s * 1000)}")
        mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        self.journal_mode = str(mode).lower()
        conn.execute("PRAGMA synchronous = NORMAL")
        self._migrate()

    # ------------------------------------------------------------- lifecycle
    def __enter__(self) -> "ProjectStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise StoreError("project store is closed")
        return self._conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """One serialised write transaction (BEGIN IMMEDIATE ... COMMIT, ROLLBACK on any error)."""
        with self._lock:
            conn = self.conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            try:
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------- migrations
    def schema_version(self) -> int:
        rows = self._query("SELECT MAX(version) AS v FROM schema_version")
        return int(rows[0]["v"] or 0)

    def _migrate(self) -> None:
        with self._tx() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS schema_version (
                             version     INTEGER PRIMARY KEY,
                             applied_at  TEXT NOT NULL,
                             description TEXT NOT NULL DEFAULT '')""")
            current = int(c.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0])
            if current > STORE_SCHEMA_VERSION:
                raise StoreError(f"store schema version {current} is newer than this engine supports "
                                 f"({STORE_SCHEMA_VERSION}); upgrade Housebuilder.OS Vision")
            for version, description, fn in MIGRATIONS:
                if version <= current:
                    continue
                fn(c)
                c.execute("INSERT INTO schema_version(version, applied_at, description) VALUES (?, ?, ?)",
                          (version, _iso(utcnow()), description))

    # ---------------------------------------------------------------- projects
    def save_project(self, project: Project, *, touch: bool = True) -> Project:
        """Insert or replace a project; registers and links its images.

        Returns the saved copy (``updated_at`` set to now when ``touch``; the input is not mutated).
        ``created_at`` of an existing row is preserved.
        """
        if not isinstance(project, Project):
            raise TypeError("project must be a housebuilder_vision Project")
        saved = project.model_copy(update={"updated_at": utcnow()}) if touch else project
        # Round-trip through validation so only a valid state is ever written.
        state = saved.model_dump_json()
        Project.model_validate_json(state)
        with self._tx() as c:
            c.execute("""INSERT INTO projects(project_id, name, schema_version, created_at, updated_at, state_json)
                         VALUES (?, ?, ?, ?, ?, ?)
                         ON CONFLICT(project_id) DO UPDATE SET
                             name = excluded.name, schema_version = excluded.schema_version,
                             updated_at = excluded.updated_at, state_json = excluded.state_json""",
                      (saved.project_id, saved.name, saved.schema_version, _iso(saved.created_at),
                       _iso(saved.updated_at), state))
            c.execute("DELETE FROM project_images WHERE project_id = ?", (saved.project_id,))
            for im in saved.images:
                self._upsert_image(c, im)
                c.execute("INSERT OR IGNORE INTO project_images(project_id, image_id) VALUES (?, ?)",
                          (saved.project_id, im.image_id))
        return saved

    def load_project(self, project_id: str) -> Project:
        """Validated project state; raises :class:`ProjectNotFound` or :class:`StoreError`."""
        rows = self._query("SELECT length(CAST(state_json AS BLOB)) AS n, schema_version FROM projects "
                           "WHERE project_id = ?", (project_id,))
        if not rows:
            raise ProjectNotFound(project_id)
        if int(rows[0]["n"] or 0) > MAX_STATE_BYTES:
            raise StoreError(f"stored state of project {project_id!r} exceeds {MAX_STATE_BYTES} bytes")
        stored_version = str(rows[0]["schema_version"])
        if _major(stored_version) != _major(SCHEMA_VERSION):
            raise StoreError(f"project {project_id!r} uses model schema {stored_version}; this engine reads "
                             f"{SCHEMA_VERSION} (major versions differ - migrate before loading)")
        state = self._query("SELECT state_json FROM projects WHERE project_id = ?", (project_id,))[0]["state_json"]
        try:
            project = Project.model_validate_json(state)
        except ValidationError as e:
            raise StoreError(f"stored state of project {project_id!r} failed validation "
                             f"({e.error_count()} error(s))") from e
        if project.project_id != project_id:
            raise StoreError(f"stored state id {project.project_id!r} does not match row {project_id!r}")
        return project

    def has_project(self, project_id: str) -> bool:
        return bool(self._query("SELECT 1 FROM projects WHERE project_id = ?", (project_id,)))

    def list_projects(self) -> list[ProjectSummary]:
        """Summaries, most recently updated first (state JSON is not parsed)."""
        rows = self._query("""
            SELECT p.project_id, p.name, p.schema_version, p.created_at, p.updated_at,
                   (SELECT COUNT(*) FROM project_images pi WHERE pi.project_id = p.project_id) AS image_count,
                   (SELECT COUNT(*) FROM runs r WHERE r.project_id = p.project_id) AS run_count
            FROM projects p ORDER BY p.updated_at DESC, p.project_id""")
        return [ProjectSummary(project_id=r["project_id"], name=r["name"], schema_version=r["schema_version"],
                               created_at=_dt(r["created_at"]), updated_at=_dt(r["updated_at"]),
                               image_count=int(r["image_count"]), run_count=int(r["run_count"])) for r in rows]

    def delete_project(self, project_id: str) -> bool:
        """Delete a project, its image links and its run log (image registry rows are kept)."""
        with self._tx() as c:
            c.execute("DELETE FROM runs WHERE project_id = ?", (project_id,))
            cur = c.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            return cur.rowcount > 0

    # ------------------------------------------------------------------ images
    @staticmethod
    def _upsert_image(c: sqlite3.Connection, asset: ImageAsset) -> None:
        c.execute("""INSERT INTO images(sha256, image_id, filename, media_type, kind, view, stored_path, size_bytes,
                                        created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                     ON CONFLICT(sha256) DO UPDATE SET
                         stored_path = COALESCE(excluded.stored_path, images.stored_path),
                         kind = CASE WHEN excluded.kind != 'unknown' THEN excluded.kind ELSE images.kind END,
                         view = CASE WHEN excluded.view != 'unknown' THEN excluded.view ELSE images.view END""",
                  (asset.sha256, asset.image_id, asset.original_filename[:255], asset.media_type, asset.kind.value,
                   asset.view.value, asset.stored_path, int(asset.size_bytes), _iso(asset.uploaded_at)))

    def register_image(self, asset: ImageAsset, *, project_id: Optional[str] = None) -> ImageRecord:
        """Record an ingested image (idempotent by sha256); optionally link it to a stored project.

        Raises :class:`ProjectNotFound` when ``project_id`` is given but not stored.
        """
        if not isinstance(asset, ImageAsset):
            raise TypeError("asset must be an ImageAsset")
        with self._tx() as c:
            if project_id is not None:
                if not c.execute("SELECT 1 FROM projects WHERE project_id = ?", (project_id,)).fetchone():
                    raise ProjectNotFound(project_id)
            self._upsert_image(c, asset)
            if project_id is not None:
                c.execute("INSERT OR IGNORE INTO project_images(project_id, image_id) VALUES (?, ?)",
                          (project_id, asset.image_id))
        rec = self.image(asset.sha256)
        assert rec is not None
        return rec

    @staticmethod
    def _image_record(r: sqlite3.Row) -> ImageRecord:
        return ImageRecord(sha256=r["sha256"], image_id=r["image_id"], filename=r["filename"],
                           media_type=r["media_type"], kind=r["kind"], view=r["view"], stored_path=r["stored_path"],
                           size_bytes=int(r["size_bytes"]), created_at=_dt(r["created_at"]))

    def image(self, sha256: str) -> Optional[ImageRecord]:
        rows = self._query("SELECT * FROM images WHERE sha256 = ?", (sha256,))
        return self._image_record(rows[0]) if rows else None

    def images(self, project_id: Optional[str] = None) -> list[ImageRecord]:
        """All registered images, or those linked to ``project_id``."""
        if project_id is None:
            rows = self._query("SELECT * FROM images ORDER BY created_at, sha256")
        else:
            rows = self._query("""SELECT i.* FROM images i JOIN project_images pi ON pi.image_id = i.image_id
                                  WHERE pi.project_id = ? ORDER BY i.created_at, i.sha256""", (project_id,))
        return [self._image_record(r) for r in rows]

    # -------------------------------------------------------------------- runs
    def log_run(self, record: RunRecord, *, project_id: Optional[str] = None) -> int:
        """Append a :class:`RunRecord` to the run log; returns the row id.

        ``project_id`` may name a project that is not (yet) stored.
        """
        if not isinstance(record, RunRecord):
            raise TypeError("record must be a RunRecord")
        versions = json.dumps({str(k): str(v) for k, v in record.versions.items()}, sort_keys=True)
        seed = None if record.seed is None else int(record.seed)
        with self._tx() as c:
            cur = c.execute("""INSERT INTO runs(project_id, function, timestamp, inputs_sha256, outputs_sha256, seed,
                                                versions_json, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (project_id, record.function, _iso(record.timestamp), record.inputs_sha256,
                             record.outputs_sha256, seed, versions, record.note))
            return int(cur.lastrowid)

    def log_call(self, function: str, *, inputs: Any = None, outputs: Any = None, seed: Optional[int] = None,
                 project_id: Optional[str] = None, note: str = "",
                 versions: Optional[dict[str, str]] = None) -> int:
        """Convenience: hash ``inputs`` / ``outputs`` canonically and log the call with engine versions."""
        from .export import canonical_sha256, engine_versions

        rec = RunRecord(function=function, inputs_sha256=canonical_sha256(inputs) if inputs is not None else "",
                        outputs_sha256=canonical_sha256(outputs) if outputs is not None else "", seed=seed,
                        versions=versions if versions is not None else engine_versions(), note=note)
        return self.log_run(rec, project_id=project_id)

    def runs(self, project_id: Optional[str] = None, *, function: Optional[str] = None,
             limit: Optional[int] = None) -> list[StoredRun]:
        """Logged runs in insertion order, optionally filtered by project and function."""
        sql = "SELECT * FROM runs"
        cond: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            cond.append("project_id = ?")
            params.append(project_id)
        if function is not None:
            cond.append("function = ?")
            params.append(function)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(0, int(limit)))
        out: list[StoredRun] = []
        for r in self._query(sql, tuple(params)):
            try:
                versions = json.loads(r["versions_json"] or "{}")
                versions = {str(k): str(v) for k, v in versions.items()} if isinstance(versions, dict) else {}
            except json.JSONDecodeError:
                versions = {}
            out.append(StoredRun(id=int(r["id"]), project_id=r["project_id"], function=r["function"],
                                 timestamp=_dt(r["timestamp"]), inputs_sha256=r["inputs_sha256"],
                                 outputs_sha256=r["outputs_sha256"], seed=r["seed"], versions=versions,
                                 note=r["note"]))
        return out


__all__ = [
    "DATA_DIR_ENV",
    "MIGRATIONS",
    "STORE_SCHEMA_VERSION",
    "ImageRecord",
    "ProjectNotFound",
    "ProjectStore",
    "ProjectSummary",
    "StoreError",
    "StoredRun",
    "default_db_path",
]
