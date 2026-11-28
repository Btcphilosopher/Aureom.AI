from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"), index=True)
    trade_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trade_files.id"), index=True)
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("financing_facilities.id"))
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(100), default="UPLOAD")
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
