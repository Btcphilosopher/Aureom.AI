from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class Job(Base, TimestampMixin):
    """File de tâches PostgreSQL (SELECT ... FOR UPDATE SKIP LOCKED).

    ``dedup_key`` rend l'enfilage idempotent ; ``lease_until`` permet de
    reprendre une tâche dont le travailleur a été interrompu.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("dedup_key"),
        Index("ix_jobs_ready", "status", "run_after"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    kind: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    dedup_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING/RUNNING/DONE/FAILED
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=5)
    run_after: Mapped[datetime]
    lease_until: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None]
