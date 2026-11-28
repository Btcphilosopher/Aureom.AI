"""Pagination par curseur opaque (décalage encodé) avec total."""
from __future__ import annotations

import base64
import json
from typing import Any, Callable

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from horizon.core.errors import DomainError


class PageParams:
    def __init__(
        self,
        limit: int = Query(50, ge=1, le=200, description="Nombre d'éléments (1-200)"),
        cursor: str | None = Query(None, description="Curseur opaque renvoyé par la page précédente"),
    ):
        self.limit = limit
        self.offset = decode_cursor(cursor) if cursor else 0


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        off = int(data["o"])
        if off < 0:
            raise ValueError
        return off
    except Exception as exc:  # noqa: BLE001
        raise DomainError("INVALID_CURSOR", "Curseur de pagination invalide", 400) from exc


def paginate(db: Session, stmt: Select, page: PageParams, serialize: Callable[[Any], dict]) -> dict:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    nxt = page.offset + len(rows)
    return {
        "data": [serialize(r) for r in rows],
        "page": {
            "limit": page.limit,
            "total": total,
            "next_cursor": encode_cursor(nxt) if nxt < (total or 0) else None,
        },
    }


def paginate_list(items: list, page: PageParams) -> dict:
    chunk = items[page.offset : page.offset + page.limit]
    nxt = page.offset + len(chunk)
    return {
        "data": chunk,
        "page": {"limit": page.limit, "total": len(items), "next_cursor": encode_cursor(nxt) if nxt < len(items) else None},
    }
