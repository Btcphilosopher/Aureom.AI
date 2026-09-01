"""
Relational persistence layer (spec item 64): sqlite3 (stdlib -- no extra
dependency) schema for historical telemetry, batches, products, machines,
maintenance, quality and production orders, with indexes sized for
high-volume telemetry writes.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS machines (
    machine_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    stage TEXT NOT NULL,
    line_id TEXT NOT NULL,
    state TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetry_machine_time ON telemetry (machine_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_telemetry_metric_time ON telemetry (metric, timestamp);

CREATE TABLE IF NOT EXISTS material_batches (
    batch_id TEXT PRIMARY KEY,
    material_id TEXT NOT NULL,
    supplier_id TEXT NOT NULL,
    quantity REAL NOT NULL,
    cost_per_unit REAL NOT NULL,
    received_at TEXT NOT NULL,
    moisture_pct REAL,
    purity_pct REAL,
    quality_score REAL
);
CREATE INDEX IF NOT EXISTS idx_material_batches_material ON material_batches (material_id);

CREATE TABLE IF NOT EXISTS cells (
    serial_number TEXT PRIMARY KEY,
    cell_format TEXT,
    chemistry TEXT,
    line_id TEXT,
    capacity_ah REAL,
    internal_resistance_mohm REAL,
    voltage_v REAL,
    test_result TEXT
);

CREATE TABLE IF NOT EXISTS modules (
    module_id TEXT PRIMARY KEY,
    series_count INTEGER,
    parallel_count INTEGER,
    capacity_ah REAL,
    resistance_mohm REAL,
    mismatch_score REAL
);

CREATE TABLE IF NOT EXISTS packs (
    pack_id TEXT PRIMARY KEY,
    series_count INTEGER,
    parallel_count INTEGER,
    nominal_voltage_v REAL,
    capacity_kwh REAL,
    test_result TEXT
);

CREATE TABLE IF NOT EXISTS quality_results (
    result_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    result TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quality_subject ON quality_results (subject_id);
CREATE INDEX IF NOT EXISTS idx_quality_time ON quality_results (timestamp);

CREATE TABLE IF NOT EXISTS maintenance_events (
    event_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    remaining_useful_life_hours REAL,
    failure_probability REAL,
    resolved INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_maintenance_machine ON maintenance_events (machine_id);

CREATE TABLE IF NOT EXISTS production_orders (
    order_id TEXT PRIMARY KEY,
    product_spec TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    priority INTEGER,
    completed_quantity INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS factory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_type_time ON factory_events (event_type, timestamp);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    username TEXT NOT NULL,
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    allowed INTEGER NOT NULL
);
"""


class FactoryDatabase:
    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL;") if path != ":memory:" else None
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        cur = self.conn.cursor()
        try:
            yield cur
            self.conn.commit()
        finally:
            cur.close()

    def bulk_insert_telemetry(self, rows: Iterable[tuple[str, str, float, str, str]]) -> None:
        """rows: (machine_id, metric, value, unit, timestamp_iso)"""
        with self.cursor() as cur:
            cur.executemany(
                "INSERT INTO telemetry (machine_id, metric, value, unit, timestamp) VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    def insert_quality_result(self, result_id: str, subject_id: str, stage: str, result: str, timestamp: datetime) -> None:
        with self.cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO quality_results (result_id, subject_id, stage, result, timestamp) VALUES (?, ?, ?, ?, ?)",
                (result_id, subject_id, stage, result, timestamp.isoformat()),
            )

    def query_telemetry(self, machine_id: str, metric: str, limit: int = 1000) -> list[tuple]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT value, unit, timestamp FROM telemetry WHERE machine_id=? AND metric=? ORDER BY timestamp DESC LIMIT ?",
                (machine_id, metric, limit),
            )
            return cur.fetchall()

    def log_audit(self, username: str, role: str, action: str, resource: str, allowed: bool) -> None:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log (timestamp, username, role, action, resource, allowed) VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.utcnow().isoformat(), username, role, action, resource, int(allowed)),
            )

    def close(self) -> None:
        self.conn.close()
