from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException

from qengine.services import auth as authenticator


@dataclass
class CurrentUser:
    id: str                  # actual user_id from JWT
    role: str                # 'admin' or 'user'
    username: str
    effective_user_id: str   # impersonated user_id if set, else id
    is_admin: bool
    is_impersonating: bool
    impersonating_username: str = ''


def get_current_user(authorization: Optional[str] = Header(None)) -> CurrentUser:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization")

    # Try JWT decode
    payload = authenticator.decode_jwt(authorization)
    if payload:
        user_id = payload['user_id']
        role = payload.get('role', 'user')
        username = payload.get('username', '')
        imp = payload.get('imp')
        imp_username = payload.get('imp_username', '')

        # Verify the user still exists and is active
        from qengine.models.User import get_user_by_id
        db_user = get_user_by_id(user_id)
        if not db_user or db_user.is_deleted or not db_user.is_active:
            raise HTTPException(status_code=401, detail="Account has been deleted or deactivated")

        return CurrentUser(
            id=user_id,
            role=role,
            username=username,
            effective_user_id=imp if imp else user_id,
            is_admin=(role == 'admin'),
            is_impersonating=bool(imp),
            impersonating_username=imp_username,
        )

    # Legacy token support — treat as admin (existing single-password users)
    if authenticator._legacy_is_valid_token(authorization):
        from qengine.models.User import get_admin_user
        admin = get_admin_user()
        if admin:
            return CurrentUser(
                id=str(admin.id),
                role='admin',
                username=admin.username,
                effective_user_id=str(admin.id),
                is_admin=True,
                is_impersonating=False,
            )
        # No admin user in DB yet (pre-migration) — create a temporary admin context
        return CurrentUser(
            id='legacy',
            role='admin',
            username='admin',
            effective_user_id='legacy',
            is_admin=True,
            is_impersonating=False,
        )

    raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_admin(authorization: Optional[str] = Header(None)) -> CurrentUser:
    current_user = get_current_user(authorization)
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
