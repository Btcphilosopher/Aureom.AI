"""Horloge injectable : permet aux tests de geler ou d'avancer le temps.

Toutes les règles temporelles (expiration des approbations, devis de change,
fraîcheur des données, liens de documents) passent par ce module.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

_offset = timedelta(0)
_frozen: datetime | None = None


def now() -> datetime:
    if _frozen is not None:
        return _frozen
    return datetime.now(timezone.utc) + _offset


def today() -> date:
    return now().date()


def advance(delta: timedelta) -> None:
    global _offset, _frozen
    if _frozen is not None:
        _frozen = _frozen + delta
    else:
        _offset += delta


def freeze(at: datetime | None = None) -> None:
    global _frozen
    _frozen = at or now()


def reset() -> None:
    global _offset, _frozen
    _offset = timedelta(0)
    _frozen = None
