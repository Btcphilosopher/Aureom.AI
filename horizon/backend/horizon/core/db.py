"""Moteur SQLAlchemy, base déclarative et gestion des sessions."""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from sqlalchemy import DateTime, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from horizon.core import clock
from horizon.core.config import get_settings

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {datetime: DateTime(timezone=True)}


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=lambda: clock.now())


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=True)
    return _engine


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def SessionLocal() -> Session:  # noqa: N802 - fabrique de sessions
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transaction unitaire : commit si succès, rollback sinon."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête, commit explicite en fin."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
