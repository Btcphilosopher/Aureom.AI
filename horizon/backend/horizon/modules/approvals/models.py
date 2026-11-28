from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class Approval(Base, TimestampMixin):
    """Décision d'un approbateur sur une version précise d'un lot."""

    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("decision IN ('APPROVE','REJECT')", name="decision_valid"),
        # Un approbateur ne compte qu'une fois par version (même en cas de double clic concurrent).
        Index(
            "uq_approvals_valid_per_user",
            "batch_id",
            "batch_version",
            "approver_user_id",
            unique=True,
            postgresql_where=text("invalidated_at IS NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_batches.id"), index=True)
    batch_version: Mapped[int]
    approver_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(10))
    comment: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime]
    step_up_at: Mapped[datetime]
    via_role_assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("role_assignments.id"))
    via_delegation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("delegations.id"))
    invalidated_at: Mapped[datetime | None]
    invalidation_reason: Mapped[str | None] = mapped_column(String(500))
