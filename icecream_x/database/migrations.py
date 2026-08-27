"""Schema creation.

For a project at this stage, straightforward ``metadata.create_all`` is
used rather than a full Alembic migration chain -- the natural upgrade
path once the schema needs versioned, incremental migrations in
production. :func:`create_schema` is idempotent (safe to call on every
app startup).
"""

from __future__ import annotations

from sqlalchemy import Engine

from icecream_x.database.models import Base


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def drop_schema(engine: Engine) -> None:
    Base.metadata.drop_all(engine)
