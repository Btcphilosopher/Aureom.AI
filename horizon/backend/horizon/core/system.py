"""Principal technique pour les scripts (données de démonstration, démo scriptée)."""
from __future__ import annotations

from horizon.core import clock
from horizon.core.context import Principal
from horizon.modules.identity.models import User, UserSession
from horizon.modules.organizations.permissions import Authz


def principal_for(db, user: User, step_up: bool = True) -> Principal:
    sess = UserSession(user_id=user.id, token_hash="script", expires_at=clock.now(), mfa_verified_at=clock.now(),
                       step_up_at=clock.now() if step_up else None)
    return Principal(user=user, session=sess, authz=Authz.load(db, user.id, user.organization_id), db=db,
                     request_id="script")
