"""Erreurs métier structurées."""
from __future__ import annotations

from typing import Any


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


class NotFound(DomainError):
    def __init__(self, what: str, ident: Any = None):
        super().__init__("NOT_FOUND", f"{what} introuvable", 404, {"id": str(ident) if ident else None})


class Forbidden(DomainError):
    def __init__(self, message: str = "Permission refusée", details: Any = None, code: str = "FORBIDDEN"):
        super().__init__(code, message, 403, details)


class Conflict(DomainError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(code, message, 409, details)


class Unauthorized(DomainError):
    def __init__(self, message: str = "Authentification requise", code: str = "UNAUTHENTICATED"):
        super().__init__(code, message, 401)
