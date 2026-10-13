from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import IdentityDep
from app.api.errors import Unauthorized, ValidationFailed
from app.api.types import Email
from app.config import get_settings
from app.db.session import TenantContext, tenant_session
from app.models import User
from app.security.credentials import hash_password, verify_password
from app.services import accounts

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=500)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    s = get_settings()
    result = accounts.login(
        body.email, body.password, request.client.host if request.client else None, request.headers.get("user-agent")
    )
    response.set_cookie(
        s.cookie_name,
        result.token,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        max_age=s.session_ttl_hours * 3600,
        path="/",
    )
    memberships = accounts.memberships_for_user(uuid.UUID(result.user["id"]), result.user["is_platform_admin"])
    return {
        "user": result.user,
        "memberships": memberships,
        "access_token": result.token,
        "token_type": "bearer",
        "expires_at": result.expires_at.isoformat(),
    }


@router.post("/logout")
def logout(identity: IdentityDep, response: Response) -> dict:
    if identity.session_id:
        accounts.revoke_session(identity.session_id)
    response.delete_cookie(get_settings().cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(identity: IdentityDep) -> dict:
    if identity.kind == "api_token":
        return {
            "kind": "api_token",
            "token": {
                "id": str(identity.token_id),
                "name": identity.token_name,
                "organization_id": str(identity.token_org_id),
                "brand_id": str(identity.token_brand_id) if identity.token_brand_id else None,
                "role": identity.token_role_key,
                "scopes": identity.token_scopes,
            },
        }
    return {
        "kind": "user",
        "user": {
            "id": str(identity.user_id),
            "email": identity.email,
            "full_name": identity.full_name,
            "is_platform_admin": identity.is_platform_admin,
        },
        "memberships": accounts.memberships_for_user(identity.user_id, identity.is_platform_admin),
    }


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=500)


@router.post("/password")
def change_password(body: PasswordChangeIn, identity: IdentityDep) -> dict:
    if identity.kind != "user":
        raise Unauthorized("Only users can change passwords")
    with tenant_session(TenantContext(org_id=None, user_id=identity.user_id)) as db:
        user = db.scalar(select(User).where(User.id == identity.user_id))
        if not user or not verify_password(user.password_hash, body.current_password):
            raise Unauthorized("Current password is incorrect")
        try:
            user.password_hash = hash_password(body.new_password)
        except ValueError as e:
            raise ValidationFailed(str(e)) from e
    return {"ok": True}
