from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base


class AuditEvent(Base):
    """Événement d'audit chaîné (hash du précédent) et en ajout seul (trigger)."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    at: Mapped[datetime]
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_label: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100), index=True)
    object_type: Mapped[str | None] = mapped_column(String(50))
    object_id: Mapped[str | None] = mapped_column(String(100), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("legal_entities.id"))
    outcome: Mapped[str] = mapped_column(String(20), default="SUCCESS")
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
