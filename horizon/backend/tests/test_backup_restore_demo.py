"""Sauvegarde/restauration testées de bout en bout, et démonstration complète en 12 étapes."""
import os
import shutil
import subprocess
import tempfile

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from horizon.modules.audit import service as audit
from tests.conftest import FR_LINES, URL, _recreate

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")


def _pgurl(db):
    return f"postgresql://{URL.username}:{URL.password}@{URL.host}:{URL.port}/{db}"


def _fingerprint(conn) -> dict:
    return {
        "trial": conn.execute(text("""SELECT currency, sum(debit_minor), sum(credit_minor) FROM journal_lines
                                      GROUP BY currency ORDER BY currency""")).all(),
        "entries": conn.execute(text("SELECT count(*), max(entry_number) FROM journal_entries")).one(),
        "payments": conn.execute(text("SELECT status, count(*) FROM payments GROUP BY status ORDER BY status")).all(),
        "audit_last": conn.execute(text("SELECT max(id), (SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1) "
                                        "FROM audit_events")).one(),
        "reservations": conn.execute(text("SELECT status, sum(amount_minor) FROM reservations GROUP BY status ORDER BY 1")).all(),
        "alembic": conn.execute(text("SELECT version_num FROM alembic_version")).scalar(),
    }


@pytest.mark.skipif(shutil.which("pg_dump") is None, reason="pg_dump absent")
def test_backup_and_restore_roundtrip(api):
    b = api.batch(FR_LINES)
    api.approve("sophie", b)
    api.approve("marc", b)
    api.run_jobs()
    tmp = tempfile.mkdtemp(prefix="horizon-backup-")
    env = {**os.environ, "PGURL": _pgurl(URL.database), "STORAGE_PATH": os.environ["HORIZON_STORAGE_PATH"]}
    out = subprocess.run([os.path.join(SCRIPTS, "backup.sh"), tmp], env=env, capture_output=True, text=True, check=True)
    backup_dir = out.stdout.strip().splitlines()[-1]
    assert os.path.exists(os.path.join(backup_dir, "database.dump"))
    restored = f"{URL.database}_restored"
    _recreate(restored)
    restore_storage = tempfile.mkdtemp(prefix="horizon-restored-objects-")
    env2 = {**os.environ, "PGURL": _pgurl(restored), "STORAGE_PATH": restore_storage}
    subprocess.run([os.path.join(SCRIPTS, "restore.sh"), backup_dir], env=env2, capture_output=True, text=True, check=True)
    src = create_engine(URL.render_as_string(hide_password=False))
    dst = create_engine(URL.set(database=restored).render_as_string(hide_password=False))
    with src.connect() as a, dst.connect() as d:
        assert _fingerprint(a) == _fingerprint(d)
    with Session(dst) as s:
        org = s.execute(text("SELECT id FROM organizations WHERE name = 'Groupe Lumière'")).scalar()
        assert audit.verify_chain(s, org)["valid"]
        # les garde-fous (triggers) sont restaurés eux aussi
        with pytest.raises(Exception, match="immuable"):
            s.execute(text("DELETE FROM journal_entries"))
    assert sorted(os.listdir(restore_storage)) == sorted(os.listdir(os.environ["HORIZON_STORAGE_PATH"]))
    # une sauvegarde altérée est refusée
    with open(os.path.join(backup_dir, "database.dump"), "ab") as f:
        f.write(b"corruption")
    _recreate(restored)
    r = subprocess.run([os.path.join(SCRIPTS, "restore.sh"), backup_dir], env=env2, capture_output=True, text=True)
    assert r.returncode != 0
    src.dispose()
    dst.dispose()
    with psycopg.connect(host=URL.host, port=URL.port, user=URL.username, password=URL.password, dbname="postgres",
                         autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{restored}" WITH (FORCE)')


def test_full_twelve_step_demo():
    from horizon.demo import run

    rep = run(None, 12, None)
    text_ = "\n".join(rep.lines)
    for n in range(1, 13):
        assert f"## Étape {n} " in text_
    assert text_.rstrip().endswith("Démonstration terminée avec succès.")
