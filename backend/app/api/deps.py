"""Authentication, tenant resolution and permission dependencies.

Every tenant-scoped endpoint depends on ``get_tenant`` which:
  1. authenticates the caller (session cookie / bearer JWT / API token),
  2. resolves the organization (API token's org, or the ``X-Organization-Id`` header),
  3. verifies membership (or platform-admin status),
  4. opens a database session on the RLS-enforced role with ``app.org_id`` set.
Authorization is then checked with ``tenant.require("perm.key")``. Even if a check were
forgotten, Row Level Security still prevents any cross-tenant read or write.
"""
from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from fastapi import Depends, Header, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.errors import Forbidden, NotFound, Unauthorized
from app.config import get_settings
from app.db.session import (
    TenantContext,
    new_tenant_session,
    system_session,
    tenant_session,
)
from app.models import (
    ApiToken,
    AuditLog,
    AuthSession,
    Organization,
    OrganizationUser,
    User,
)
from app.security.credentials import decode_session_jwt, hash_api_token, is_api_token
from app.security.permissions import all_permissions, permissions_for_role

CSRF_HEADER = "x-bdna-csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class Identity:
    kind: Literal["user", "api_token"]
    user_id: uuid.UUID | None = None
    email: str | None = None
    full_name: str | None = None
    is_platform_admin: bool = False
    session_id: uuid.UUID | None = None
    via_cookie: bool = False
    token_id: uuid.UUID | None = None
    token_name: str | None = None
    token_org_id: uuid.UUID | None = None
    token_brand_id: uuid.UUID | None = None
    token_role_key: str | None = None
    token_scopes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.email or f"api_token:{self.token_name}"


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _resolve_api_token(raw: str) -> Identity:
    now = dt.datetime.now(dt.UTC)
    with system_session() as s:  # narrow privileged lookup: token hash -> owning organization
        tok = s.scalar(select(ApiToken).where(ApiToken.token_hash == hash_api_token(raw)))
        if tok is None or tok.revoked_at is not None or (tok.expires_at and tok.expires_at < now):
            raise Unauthorized("Invalid or expired API token")
        org_status = s.scalar(select(Organization.status).where(Organization.id == tok.organization_id))
        if org_status != "active":
            raise Forbidden("Organization is not active")
        if tok.last_used_at is None or (now - tok.last_used_at).total_seconds() > 60:
            s.execute(update(ApiToken).where(ApiToken.id == tok.id).values(last_used_at=now))
        return Identity(
            kind="api_token",
            user_id=tok.created_by,
            token_id=tok.id,
            token_name=tok.name,
            token_org_id=tok.organization_id,
            token_brand_id=tok.brand_id,
            token_role_key=tok.role_key,
            token_scopes=list(tok.scopes or []),
        )


def _resolve_session(raw: str, via_cookie: bool) -> Identity:
    claims = decode_session_jwt(raw)
    if claims is None:
        raise Unauthorized("Invalid or expired session")
    now = dt.datetime.now(dt.UTC)
    # Runs on the RLS role with only the user in context: can see only its own session/user row.
    with tenant_session(TenantContext(org_id=None, user_id=claims.user_id)) as s:
        sess = s.scalar(select(AuthSession).where(AuthSession.id == claims.session_id))
        if sess is None or sess.revoked_at is not None or sess.expires_at < now:
            raise Unauthorized("Session expired or revoked")
        user = s.scalar(select(User).where(User.id == claims.user_id))
        if user is None or not user.is_active:
            raise Unauthorized("User is inactive")
        if sess.last_seen_at is None or (now - sess.last_seen_at).total_seconds() > 300:
            sess.last_seen_at = now
        return Identity(
            kind="user",
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_platform_admin=user.is_platform_admin,
            session_id=sess.id,
            via_cookie=via_cookie,
        )


def get_identity(request: Request, authorization: Annotated[str | None, Header()] = None) -> Identity:
    raw, via_cookie = None, False
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    elif cookie := request.cookies.get(get_settings().cookie_name):
        raw, via_cookie = cookie, True
    if not raw:
        raise Unauthorized("Authentication required")
    identity = _resolve_api_token(raw) if is_api_token(raw) else _resolve_session(raw, via_cookie)
    if identity.via_cookie and request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != "1":
        raise Forbidden("Missing CSRF header", code="csrf_failed")
    return identity


IdentityDep = Annotated[Identity, Depends(get_identity)]


def require_platform_admin(identity: IdentityDep) -> Identity:
    if identity.kind != "user" or not identity.is_platform_admin:
        raise Forbidden("Platform administrator access required")
    return identity


PlatformAdminDep = Annotated[Identity, Depends(require_platform_admin)]


@dataclass
class Tenant:
    identity: Identity
    org_id: uuid.UUID
    org_slug: str
    org_name: str
    org_status: str
    role_key: str
    permissions: frozenset[str]
    brand_restriction: uuid.UUID | None
    db: Session
    ip: str | None = None

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.identity.user_id

    def can(self, perm: str) -> bool:
        return perm in self.permissions

    def require(self, *perms: str) -> None:
        missing = [p for p in perms if p not in self.permissions]
        if missing:
            raise Forbidden("Missing permission", details={"required": missing, "role": self.role_key})

    def check_brand(self, brand_id: uuid.UUID) -> None:
        if self.brand_restriction and brand_id != self.brand_restriction:
            raise NotFound("Brand not found")

    def audit(
        self, action: str, entity_type: str | None = None, entity_id: Any = None, details: dict | None = None
    ) -> None:
        self.db.add(
            AuditLog(
                organization_id=self.org_id,
                actor_user_id=self.identity.user_id,
                actor_type=self.identity.kind,
                actor_label=self.identity.label,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                ip_address=self.ip,
                details=details or {},
            )
        )


def _resolve_org_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        pass
    with system_session() as s:  # narrow privileged lookup: slug -> id (no tenant data)
        org_id = s.scalar(select(Organization.id).where(Organization.slug == value))
    if org_id is None:
        raise NotFound("Organization not found")
    return org_id


def get_tenant(
    request: Request,
    identity: IdentityDep,
    x_organization_id: Annotated[str | None, Header()] = None,
) -> Iterator[Tenant]:
    if identity.kind == "api_token":
        org_id = identity.token_org_id
        if x_organization_id and _resolve_org_id(x_organization_id) != org_id:
            raise Forbidden("API token is not valid for this organization")
    else:
        if not x_organization_id:
            raise Forbidden("X-Organization-Id header is required", code="organization_required")
        org_id = _resolve_org_id(x_organization_id)
    assert org_id is not None

    session = new_tenant_session(TenantContext(org_id=org_id, user_id=identity.user_id))
    try:
        org = session.scalar(select(Organization).where(Organization.id == org_id))
        if org is None:
            raise NotFound("Organization not found")
        if identity.kind == "api_token":
            role_key = identity.token_role_key or "viewer"
            perms = permissions_for_role(role_key)
            if identity.token_scopes:
                perms = perms & frozenset(identity.token_scopes)
            brand_restriction = identity.token_brand_id
        elif identity.is_platform_admin:
            role_key, perms, brand_restriction = "platform_super_admin", all_permissions(), None
        else:
            membership = session.scalar(
                select(OrganizationUser).where(
                    OrganizationUser.user_id == identity.user_id, OrganizationUser.status == "active"
                )
            )
            if membership is None:
                # Do not reveal whether the organization exists.
                raise NotFound("Organization not found")
            role_key, perms, brand_restriction = membership.role_key, permissions_for_role(membership.role_key), None
        if org.status != "active" and not identity.is_platform_admin:
            raise Forbidden("This customer workspace is archived")
        tenant = Tenant(
            identity=identity,
            org_id=org.id,
            org_slug=org.slug,
            org_name=org.name,
            org_status=org.status,
            role_key=role_key,
            permissions=perms,
            brand_restriction=brand_restriction,
            db=session,
            ip=_client_ip(request),
        )
        yield tenant
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


TenantDep = Annotated[Tenant, Depends(get_tenant, scope="function")]
