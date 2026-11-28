"""File de tâches persistante et idempotente (PostgreSQL).

* ``enqueue`` : idempotent grâce à ``dedup_key`` (ON CONFLICT DO NOTHING).
* ``claim`` : ``FOR UPDATE SKIP LOCKED`` + bail (lease) ; une tâche RUNNING dont
  le bail a expiré (travailleur interrompu) est reprise automatiquement.
* Chaque gestionnaire doit être idempotent : il revérifie l'état métier avant d'agir.
"""
from __future__ import annotations

import logging
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.db import SessionLocal
from horizon.modules.jobs.models import Job

log = logging.getLogger("horizon.jobs")
HANDLERS: dict[str, Callable[[Session, dict], None]] = {}
LEASE = timedelta(minutes=2)


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn

    return deco


def enqueue(db: Session, kind: str, payload: dict, dedup_key: str, *, run_after: datetime | None = None,
            organization_id: uuid.UUID | None = None, max_attempts: int = 5) -> None:
    stmt = insert(Job).values(
        id=uuid.uuid4(), kind=kind, payload=payload, dedup_key=dedup_key, status="PENDING", attempts=0,
        max_attempts=max_attempts, run_after=run_after or clock.now(), organization_id=organization_id,
        created_at=clock.now(),
    ).on_conflict_do_nothing(index_elements=["dedup_key"])
    db.execute(stmt)


def claim(db: Session) -> Job | None:
    now = clock.now()
    job = db.scalar(
        select(Job)
        .where(
            or_(
                (Job.status == "PENDING") & (Job.run_after <= now),
                (Job.status == "RUNNING") & (Job.lease_until < now),  # reprise après interruption
            )
        )
        .order_by(Job.run_after, Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = "RUNNING"
    job.attempts += 1
    job.lease_until = now + LEASE
    return job


def run_one() -> bool:
    """Réclame et exécute une tâche. Retourne False si la file est vide."""
    with SessionLocal() as s:
        job = claim(s)
        if job is None:
            s.rollback()
            return False
        job_id, kind, payload = job.id, job.kind, dict(job.payload)
        s.commit()
    try:
        with SessionLocal() as s:
            HANDLERS[kind](s, payload)
            j = s.get(Job, job_id)
            j.status = "DONE"
            j.finished_at = clock.now()
            j.lease_until = None
            s.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("Tâche %s (%s) en échec : %s", kind, job_id, exc)
        with SessionLocal() as s:
            j = s.get(Job, job_id)
            j.last_error = "".join(traceback.format_exception_only(type(exc), exc))[:2000]
            if j.attempts >= j.max_attempts:
                j.status = "FAILED"
                j.finished_at = clock.now()
            else:
                j.status = "PENDING"
                j.run_after = clock.now() + timedelta(seconds=2 ** j.attempts)
            j.lease_until = None
            s.commit()
    return True


def drain(max_jobs: int = 500) -> int:
    """Exécute les tâches prêtes jusqu'à épuisement (tests et démonstration)."""
    n = 0
    while n < max_jobs and run_one():
        n += 1
    return n


def serialize(j: Job) -> dict:
    return {"id": str(j.id), "kind": j.kind, "status": j.status, "attempts": j.attempts, "dedup_key": j.dedup_key,
            "run_after": j.run_after.isoformat(), "last_error": j.last_error,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None}
