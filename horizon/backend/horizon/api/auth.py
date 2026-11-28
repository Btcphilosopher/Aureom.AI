from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from horizon.api.schemas import LoginIn, MfaIn, StepUpIn
from horizon.core.config import get_settings
from horizon.core.context import SESSION_COOKIE, Principal, get_principal
from horizon.core.crypto import decrypt, totp_now
from horizon.core.db import get_db
from horizon.modules.identity import service as identity
from horizon.modules.identity.models import User
from horizon.modules.organizations.models import ROLE_LABELS, LegalEntity, Organization
from horizon.modules.organizations.permissions import ROLE_PERMISSIONS

router = APIRouter(prefix="/v1/auth", tags=["Identité"])


@router.post("/login", summary="Étape 1 : identifiants (fictifs) → défi MFA")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ch = identity.login(db, body.email, body.password, request.client.host if request.client else None)
    return {"mfa_required": True, "challenge_id": str(ch.id), "expires_at": ch.expires_at.isoformat(),
            "method": "TOTP (RFC 6238)"}


@router.post("/mfa", summary="Étape 2 : code TOTP → session")
def mfa(body: MfaIn, request: Request, response: Response, db: Session = Depends(get_db)):
    token, sess, user = identity.verify_mfa(db, body.challenge_id, body.code, request.client.host if request.client else None)
    st = get_settings()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=st.cookie_secure, samesite="strict",
                        max_age=st.session_ttl_minutes * 60, path="/")
    return {"token": token, "token_type": "Bearer", "expires_at": sess.expires_at.isoformat(), "user_id": str(user.id)}


@router.post("/step-up", summary="Réauthentification pour action sensible")
def step_up(body: StepUpIn, p: Principal = Depends(get_principal)):
    identity.step_up(p.db, p.session, p.user, body.code, p.ip)
    return {"step_up_at": p.session.step_up_at.isoformat(), "valid_seconds": get_settings().step_up_ttl_seconds}


@router.post("/logout")
def logout(response: Response, p: Principal = Depends(get_principal)):
    identity.logout(p.db, p.session, p.user)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"logged_out": True}


@router.get("/demo-users", summary="Utilisateurs fictifs (environnement de démonstration uniquement)")
def demo_users(db: Session = Depends(get_db)):
    st = get_settings()
    if not st.demo_show_totp:
        return {"enabled": False, "users": []}
    out = []
    for u in db.scalars(select(User).where(User.is_demo.is_(True)).order_by(User.full_name)):
        org = db.get(Organization, u.organization_id)
        out.append({"email": u.email, "full_name": u.full_name, "title": u.title, "organization": org.name,
                    "current_totp": totp_now(decrypt(u.totp_secret_enc))})
    return {"enabled": True, "password_hint": "Horizon-Demo-2026!", "users": out,
            "notice": "Identifiants fictifs. Ne saisissez jamais de véritables identifiants bancaires."}


me_router = APIRouter(prefix="/v1", tags=["Identité"])


@me_router.get("/directory", summary="Annuaire minimal de l'organisation (nom, fonction) — sans rôles ni coordonnées")
def directory(p: Principal = Depends(get_principal)):
    rows = p.db.scalars(select(User).where(User.organization_id == p.org_id, User.is_active.is_(True))
                        .order_by(User.full_name)).all()
    return {"data": [{"id": str(u.id), "full_name": u.full_name, "title": u.title} for u in rows]}


@me_router.get("/me")
def me(p: Principal = Depends(get_principal)):
    db = p.db
    org = db.get(Organization, p.org_id)
    ents = {e.id: e for e in db.scalars(select(LegalEntity).where(LegalEntity.organization_id == p.org_id))}
    roles = []
    for a in p.authz.assignments:
        roles.append({"role": a.role, "label": ROLE_LABELS[a.role],
                      "entity": ents[a.entity_id].name if a.entity_id else "Toutes les entités",
                      "entity_id": str(a.entity_id) if a.entity_id else None,
                      "account_id": str(a.account_id) if a.account_id else None,
                      "approval_limit": (str(a.approval_limit_minor / 100) if a.approval_limit_minor else None),
                      "mandate_reference": a.mandate_reference})
    return {
        "user": {"id": str(p.user.id), "email": p.user.email, "full_name": p.user.full_name, "title": p.user.title},
        "organization": {"id": str(org.id), "name": org.name, "base_currency": org.base_currency},
        "entities": [{"id": str(e.id), "name": e.name, "country_code": e.country_code, "country_name": e.country_name}
                     for e in ents.values()],
        "roles": roles, "permissions": sorted(p.authz.permissions()),
        "step_up_valid": p.session.step_up_at is not None,
        "step_up_at": p.session.step_up_at.isoformat() if p.session.step_up_at else None,
        "environment": "DÉMONSTRATION",
        "role_permissions": {k: sorted(v) for k, v in ROLE_PERMISSIONS.items()},
    }
