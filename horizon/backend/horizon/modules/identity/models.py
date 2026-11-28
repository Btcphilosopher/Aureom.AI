from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horizon.core.db import Base, TimestampMixin, new_id


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    # Secret TOTP chiffré au repos (Fernet, clé dérivée de HORIZON_SECRET_KEY).
    totp_secret_enc: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(default=True)
    is_demo: Mapped[bool] = mapped_column(default=True)


class UserSession(Base, TimestampMixin):
    __tablename__ = "user_sessions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    mfa_verified_at: Mapped[datetime | None]
    step_up_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    ip: Mapped[str | None] = mapped_column(String(64))


class MfaChallenge(Base, TimestampMixin):
    __tablename__ = "mfa_challenges"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime]
    attempts: Mapped[int] = mapped_column(default=0)
    consumed_at: Mapped[datetime | None]
