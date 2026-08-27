from __future__ import annotations

from finalcut_engine.core.project import Project
from finalcut_engine.core.timebase import Time, TimeRange
from finalcut_engine.persistence.autosave import AutosaveManager
from finalcut_engine.persistence.database import Database
from finalcut_engine.persistence.project_store import ProjectStore
from finalcut_engine.persistence.versioning import VersionManager
from finalcut_engine.timeline.clip import Clip


def _project_with_a_clip(name: str, duration: float) -> Project:
    project = Project(name=name)
    tl = project.create_timeline("Main")
    tl.append_clip(Clip(asset_id="A", source_range=TimeRange(Time.zero(), Time.from_seconds(duration))))
    return project


def test_database_integrity_check_passes_on_fresh_db(tmp_path):
    db = Database(tmp_path / "p.db")
    assert db.integrity_check()
    db.close()


def test_project_save_and_load_round_trips_timeline_state(tmp_path):
    db = Database(tmp_path / "p.db")
    store = ProjectStore(db)
    project = _project_with_a_clip("Round Trip", 3.0)

    store.save(project)
    loaded = store.load(project.id)

    assert loaded.name == project.name
    assert list(loaded.timelines.values())[0].duration.seconds() == 3.0
    db.close()


def test_project_save_is_atomic_via_transaction(tmp_path):
    db = Database(tmp_path / "p.db")
    store = ProjectStore(db)
    project = _project_with_a_clip("Atomic", 1.0)
    store.save(project)

    # Re-saving with a mutated timeline should fully replace the row (upsert),
    # never leave a partial/mixed state.
    list(project.timelines.values())[0].append_clip(Clip(asset_id="B", source_range=TimeRange(Time.zero(), Time.from_seconds(1))))
    store.save(project)
    reloaded = store.load(project.id)
    assert list(reloaded.timelines.values())[0].duration.seconds() == 2.0
    db.close()


def test_version_snapshot_and_restore(tmp_path):
    db = Database(tmp_path / "p.db")
    store = ProjectStore(db)
    versions = VersionManager(db)

    project = _project_with_a_clip("Versioned", 2.0)
    store.save(project)
    v1 = versions.snapshot(project, label="v1")

    list(project.timelines.values())[0].append_clip(Clip(asset_id="B", source_range=TimeRange(Time.zero(), Time.from_seconds(3))))
    store.save(project)
    v2 = versions.snapshot(project, label="v2")

    assert len(versions.list_versions(project.id)) == 2
    restored_v1 = versions.restore(v1.id)
    restored_v2 = versions.restore(v2.id)
    assert list(restored_v1.timelines.values())[0].duration.seconds() == 2.0
    assert list(restored_v2.timelines.values())[0].duration.seconds() == 5.0
    db.close()


def test_autosave_writes_and_crash_recovery_reads_it_back(tmp_path):
    autosave = AutosaveManager(recovery_dir=tmp_path / "recovery", interval_seconds=0)
    project = _project_with_a_clip("Crashy", 4.0)

    assert not autosave.has_recovery(project.id)
    assert autosave.maybe_autosave(project) is True
    assert autosave.has_recovery(project.id)

    recovered = autosave.recover(project.id)
    assert recovered is not None
    assert list(recovered.timelines.values())[0].duration.seconds() == 4.0

    autosave.clear_recovery(project.id)
    assert not autosave.has_recovery(project.id)
    assert autosave.recover(project.id) is None


def test_autosave_respects_interval(tmp_path):
    autosave = AutosaveManager(recovery_dir=tmp_path / "recovery", interval_seconds=100.0)
    project = _project_with_a_clip("Throttled", 1.0)

    assert autosave.maybe_autosave(project, now=1000.0) is True
    assert autosave.maybe_autosave(project, now=1010.0) is False  # too soon
    assert autosave.maybe_autosave(project, now=1101.0) is True  # interval elapsed
