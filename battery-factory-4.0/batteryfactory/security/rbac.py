"""
Enterprise security principles (spec item 65): role-based access control,
audit logging and API-key authentication for the platform's own API/data
surface. This governs access to the digital twin's analytical outputs --
it is explicitly not, and must never be wired up as, direct control of any
physical industrial equipment (spec item 65's "do not expose industrial
control systems directly to the public internet").
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from batteryfactory.database.db import FactoryDatabase


class Role(str, Enum):
    FACTORY_MANAGER = "factory_manager"
    OPERATIONS_MANAGER = "operations_manager"
    PROCESS_ENGINEER = "process_engineer"
    MAINTENANCE_ENGINEER = "maintenance_engineer"
    QUALITY_ENGINEER = "quality_engineer"
    ENERGY_MANAGER = "energy_manager"
    SUPPLY_CHAIN_MANAGER = "supply_chain_manager"
    FINANCE = "finance"
    EXECUTIVE = "executive"
    DATA_SCIENTIST = "data_scientist"


# resource -> roles allowed to read/act on it. EXECUTIVE and FACTORY_MANAGER
# get broad read access; everyone else is scoped to their domain, plus
# read-only access to the executive summary.
_PERMISSIONS: dict[str, set[Role]] = {
    "factory_state": {Role.FACTORY_MANAGER, Role.OPERATIONS_MANAGER, Role.EXECUTIVE},
    "production": {Role.FACTORY_MANAGER, Role.OPERATIONS_MANAGER, Role.PROCESS_ENGINEER, Role.EXECUTIVE},
    "machines": {Role.FACTORY_MANAGER, Role.OPERATIONS_MANAGER, Role.MAINTENANCE_ENGINEER, Role.PROCESS_ENGINEER},
    "materials": {Role.FACTORY_MANAGER, Role.SUPPLY_CHAIN_MANAGER, Role.OPERATIONS_MANAGER},
    "quality": {Role.FACTORY_MANAGER, Role.QUALITY_ENGINEER, Role.PROCESS_ENGINEER, Role.EXECUTIVE},
    "energy": {Role.FACTORY_MANAGER, Role.ENERGY_MANAGER, Role.EXECUTIVE},
    "maintenance": {Role.FACTORY_MANAGER, Role.MAINTENANCE_ENGINEER, Role.OPERATIONS_MANAGER},
    "economics": {Role.FACTORY_MANAGER, Role.FINANCE, Role.EXECUTIVE},
    "optimisation": {Role.FACTORY_MANAGER, Role.PROCESS_ENGINEER, Role.DATA_SCIENTIST, Role.EXECUTIVE},
    "ml_models": {Role.DATA_SCIENTIST, Role.FACTORY_MANAGER},
    "simulation": {Role.FACTORY_MANAGER, Role.PROCESS_ENGINEER, Role.DATA_SCIENTIST, Role.EXECUTIVE},
}


@dataclass
class User:
    username: str
    role: Role


class PermissionDenied(Exception):
    pass


class RBAC:
    def __init__(self, db: FactoryDatabase | None = None) -> None:
        self.db = db

    def is_allowed(self, user: User, resource: str) -> bool:
        return user.role in _PERMISSIONS.get(resource, set())

    def check(self, user: User, resource: str, action: str = "read") -> None:
        allowed = self.is_allowed(user, resource)
        if self.db is not None:
            self.db.log_audit(user.username, user.role.value, action, resource, allowed)
        if not allowed:
            raise PermissionDenied(f"{user.role.value} may not {action} {resource}")


class ApiKeyAuth:
    """HMAC-based API key issuance/verification -- input validation belongs
    to the API layer, this only proves "this caller holds a valid key"."""

    def __init__(self, secret: bytes | None = None) -> None:
        self.secret = secret or secrets.token_bytes(32)
        self._issued: dict[str, str] = {}  # api_key -> username

    def issue_key(self, username: str) -> str:
        token = secrets.token_hex(16)
        signature = hmac.new(self.secret, f"{username}:{token}".encode(), hashlib.sha256).hexdigest()[:16]
        api_key = f"{token}.{signature}"
        self._issued[api_key] = username
        return api_key

    def verify(self, api_key: str) -> str | None:
        if "." not in api_key:
            return None
        token, signature = api_key.split(".", 1)
        username = self._issued.get(api_key)
        if username is None:
            return None
        expected = hmac.new(self.secret, f"{username}:{token}".encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(signature, expected):
            return None
        return username


def validate_positive_number(value: float, field_name: str) -> float:
    """Basic API input validation helper (spec item 65)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return float(value)
