from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class DecisionAcknowledgement(Base, TimestampMixin):
    """Accusé de réception d'une alerte : trace qui l'a vue, ne résout rien."""

    __tablename__ = "decision_acknowledgements"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(200), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(String(500))
