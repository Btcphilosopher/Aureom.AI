"""Authentification organisationnelle : mot de passe + MFA TOTP, étape de
réauthentification pour les actions sensibles.

L'adaptateur ``IdentityProvider`` isole le mécanisme ; la démonstration utilise
un fournisseur local. Un fournisseur OIDC d'entreprise est prévu (reporté).
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.core import clock
from horizon.core.config import get_settings
from horizon.core.crypto import decrypt, new_token, token_hash, verify_password, verify_totp
from horizon.core.errors import DomainError, Unauthorized
from horizon.modules.audit import service as audit
from horizon.modules.identity.models import MfaChallenge, User, UserSession


class IdentityProvider(Protocol):
    def authenticate(self, db: Session, email: str, password: str) -> User | None: ...
    def verify_second_factor(self, user: User, code: str) -> bool: ...


class LocalDemoIdentityProvider:
    """Identifiants fictifs stockés localement (scrypt) + TOTP RFC 6238."""

    def authenticate(self, db: Session, email: str, password: str) -> User | None:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            return None
        return user

    def verify_second_factor(self, user: User, code: str) -> bool:
        return verify_totp(decrypt(user.totp_secret_enc), code)


provider: IdentityProvider = LocalDemoIdentityProvider()


def login(db: Session, email: str, password: str, ip: str | None) -> MfaChallenge:
    user = provider.authenticate(db, email, password)
    if user is None:
        audit.record_independent(
            organization_id=None, actor_user_id=None, actor_label="anonyme", action="auth.login_failed",
            outcome="DENIED", details={"email": email[:200]}, ip=ip,
        )
        raise Unauthorized("Identifiants invalides", "INVALID_CREDENTIALS")
    ch = MfaChallenge(user_id=user.id, expires_at=clock.now() + timedelta(minutes=5))
    db.add(ch)
    db.flush()
    return ch


def verify_mfa(db: Session, challenge_id: uuid.UUID, code: str, ip: str | None) -> tuple[str, UserSession, User]:
    ch = db.get(MfaChallenge, challenge_id, with_for_update=True)
    if ch is None or ch.consumed_at is not None or ch.expires_at < clock.now():
        raise Unauthorized("Défi MFA invalide ou expiré", "MFA_CHALLENGE_INVALID")
    user = db.get(User, ch.user_id)
    ch.attempts += 1
    if ch.attempts > 5:
        ch.consumed_at = clock.now()
        raise Unauthorized("Trop de tentatives", "MFA_LOCKED")
    if not provider.verify_second_factor(user, code):
        db.commit()  # conserve le compteur de tentatives
        audit.record_independent(
            organization_id=user.organization_id, actor_user_id=user.id, actor_label=user.full_name,
            action="auth.mfa_failed", outcome="DENIED", ip=ip,
        )
        raise Unauthorized("Code MFA invalide", "MFA_INVALID")
    ch.consumed_at = clock.now()
    token = new_token()
    now = clock.now()
    sess = UserSession(
        user_id=user.id,
        token_hash=token_hash(token),
        expires_at=now + timedelta(minutes=get_settings().session_ttl_minutes),
        mfa_verified_at=now,
        step_up_at=None,
        ip=ip,
    )
    db.add(sess)
    db.flush()
    audit.record(db, organization_id=user.organization_id, actor_user_id=user.id, actor_label=user.full_name,
                 action="auth.login", object_type="session", object_id=sess.id, ip=ip)
    return token, sess, user


def step_up(db: Session, sess: UserSession, user: User, code: str, ip: str | None) -> None:
    if not provider.verify_second_factor(user, code):
        audit.record_independent(
            organization_id=user.organization_id, actor_user_id=user.id, actor_label=user.full_name,
            action="auth.step_up_failed", outcome="DENIED", ip=ip,
        )
        raise DomainError("STEP_UP_INVALID", "Code de réauthentification invalide", 401)
    sess.step_up_at = clock.now()
    audit.record(db, organization_id=user.organization_id, actor_user_id=user.id, actor_label=user.full_name,
                 action="auth.step_up", object_type="session", object_id=sess.id, ip=ip)


def logout(db: Session, sess: UserSession, user: User) -> None:
    sess.revoked_at = clock.now()
    audit.record(db, organization_id=user.organization_id, actor_user_id=user.id, actor_label=user.full_name,
                 action="auth.logout", object_type="session", object_id=sess.id)
