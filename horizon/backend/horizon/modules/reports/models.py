from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class ReportExport(Base, TimestampMixin):
    __tablename__ = "report_exports"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    sha256: Mapped[str] = mapped_column(String(64))
    audit_event_count: Mapped[int]
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
