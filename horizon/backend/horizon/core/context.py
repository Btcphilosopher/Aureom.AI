"""Contexte d'une requête authentifiée : utilisateur, autorisations, audit."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.config import get_settings
from horizon.core.crypto import token_hash
from horizon.core.db import get_db
from horizon.core.errors import DomainError, Unauthorized
from horizon.modules.audit import service as audit
from horizon.modules.identity.models import User, UserSession
from horizon.modules.organizations.permissions import Authz

SESSION_COOKIE = "horizon_session"
CSRF_HEADER = "x-horizon-csrf"


@dataclass
class Principal:
    user: User
    session: UserSession
    authz: Authz
    db: Session
    request_id: str | None = None
    ip: str | None = None

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def org_id(self) -> uuid.UUID:
        return self.user.organization_id

    def audit(self, action: str, object_type: str | None = None, object_id=None, *, entity_id=None,
              outcome: str = "SUCCESS", details: dict | None = None):
        return audit.record(
            self.db,
            organization_id=self.org_id,
            actor_user_id=self.user_id,
            actor_label=self.user.full_name,
            action=action,
            object_type=object_type,
            object_id=object_id,
            entity_id=entity_id,
            outcome=outcome,
            details=details,
            request_id=self.request_id,
            ip=self.ip,
        )

    def denied(self, permission: str, entity_id=None, account_id=None, action: str = "access.denied", details=None):
        audit.record_independent(
            organization_id=self.org_id,
            actor_user_id=self.user_id,
            actor_label=self.user.full_name,
            action=action,
            object_type="permission",
            object_id=permission,
            entity_id=entity_id,
            outcome="DENIED",
            details={"account_id": str(account_id) if account_id else None, **(details or {})},
            request_id=self.request_id,
            ip=self.ip,
        )

    def require(self, perm: str, entity_id=None, account_id=None):
        return self.authz.require(perm, entity_id, account_id, audit_ctx=self)

    def require_any(self, perm: str):
        return self.authz.require_any(perm, audit_ctx=self)

    def require_step_up(self) -> None:
        """Réauthentification exigée pour les actions sensibles (approbation, etc.)."""
        ttl = get_settings().step_up_ttl_seconds
        at = self.session.step_up_at
        if at is None or clock.now() - at > timedelta(seconds=ttl):
            raise DomainError(
                "STEP_UP_REQUIRED",
                "Réauthentification requise : saisissez un code MFA pour confirmer cette action",
                401,
                {"step_up_ttl_seconds": ttl},
            )


def _extract_token(request: Request) -> tuple[str | None, bool]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip(), False
    cookie = request.cookies.get(SESSION_COOKIE)
    return cookie, cookie is not None


def get_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    token, via_cookie = _extract_token(request)
    if not token:
        raise Unauthorized()
    if via_cookie and request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get(CSRF_HEADER) != "1":
        raise DomainError("CSRF_HEADER_MISSING", "En-tête anti-CSRF manquant", 403)
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(token)))
    now = clock.now()
    if sess is None or sess.revoked_at is not None or sess.expires_at < now:
        raise Unauthorized("Session invalide ou expirée", "SESSION_INVALID")
    if sess.mfa_verified_at is None:
        raise Unauthorized("Vérification MFA requise", "MFA_REQUIRED")
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Compte désactivé", "USER_DISABLED")
    authz = Authz.load(db, user.id, user.organization_id)
    return Principal(
        user=user,
        session=sess,
        authz=authz,
        db=db,
        request_id=getattr(request.state, "request_id", None),
        ip=request.client.host if request.client else None,
    )
