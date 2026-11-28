"""Journal d'audit chaîné.

Chaque événement contient le hash du précédent (par organisation) : toute
altération ou suppression rompt la chaîne, ce que ``verify_chain`` détecte.
Les refus d'accès sont journalisés dans une transaction autonome afin de
survivre au rollback de la requête refusée.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.db import SessionLocal
from horizon.core.redaction import redact
from horizon.modules.audit.models import AuditEvent

GENESIS = "0" * 64


def _canonical(ev: dict) -> str:
    return json.dumps(ev, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def _payload(e: AuditEvent) -> dict:
    return {
        "organization_id": str(e.organization_id) if e.organization_id else None,
        "at": e.at.isoformat(),
        "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
        "actor_label": e.actor_label,
        "action": e.action,
        "object_type": e.object_type,
        "object_id": e.object_id,
        "entity_id": str(e.entity_id) if e.entity_id else None,
        "outcome": e.outcome,
        "details": e.details,
    }


def compute_hash(prev_hash: str, e: AuditEvent) -> str:
    return hashlib.sha256((prev_hash + _canonical(_payload(e))).encode()).hexdigest()


def record(
    db: Session,
    *,
    organization_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    actor_label: str,
    action: str,
    object_type: str | None = None,
    object_id: Any = None,
    entity_id: uuid.UUID | None = None,
    outcome: str = "SUCCESS",
    details: dict | None = None,
    request_id: str | None = None,
    ip: str | None = None,
) -> AuditEvent:
    # Sérialise l'écriture de la chaîne pour une organisation donnée.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"audit:{organization_id}"})
    prev = db.scalar(
        select(AuditEvent.hash)
        .where(AuditEvent.organization_id == organization_id if organization_id else AuditEvent.organization_id.is_(None))
        .order_by(AuditEvent.id.desc())
        .limit(1)
    )
    ev = AuditEvent(
        organization_id=organization_id,
        at=clock.now(),
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        entity_id=entity_id,
        outcome=outcome,
        details=json.loads(_canonical(redact(details or {}))),
        request_id=request_id,
        ip=ip,
        prev_hash=prev or GENESIS,
        hash="",
    )
    ev.hash = compute_hash(ev.prev_hash, ev)
    db.add(ev)
    db.flush()
    return ev


def record_independent(**kwargs) -> None:
    """Écrit un événement dans sa propre transaction (refus, échecs d'authentification)."""
    s = SessionLocal()
    try:
        record(s, **kwargs)
        s.commit()
    finally:
        s.close()


def verify_chain(db: Session, organization_id: uuid.UUID) -> dict:
    prev = GENESIS
    count = 0
    for e in db.scalars(
        select(AuditEvent).where(AuditEvent.organization_id == organization_id).order_by(AuditEvent.id)
    ):
        if e.prev_hash != prev or compute_hash(prev, e) != e.hash:
            return {"valid": False, "checked": count, "broken_at_event_id": e.id}
        prev = e.hash
        count += 1
    return {"valid": True, "checked": count, "last_hash": prev}


def serialize(e: AuditEvent) -> dict:
    return {
        "id": e.id,
        "at": e.at.isoformat(),
        "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
        "actor": e.actor_label,
        "action": e.action,
        "object_type": e.object_type,
        "object_id": e.object_id,
        "entity_id": str(e.entity_id) if e.entity_id else None,
        "outcome": e.outcome,
        "details": e.details,
        "request_id": e.request_id,
        "hash": e.hash,
        "prev_hash": e.prev_hash,
    }
