"""Customer workspace: profile, members, API tokens, audit log. All RLS-scoped via TenantDep."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.common import PageParams, jsonable, page_params, paginate, row_to_dict
from app.api.deps import TenantDep
from app.api.errors import Forbidden, NotFound, ValidationFailed
from app.api.types import Email
from app.models import (
    AiSuggestion,
    ApiToken,
    Asset,
    AssetAnalysis,
    AssetDerivative,
    AuditLog,
    Brand,
    Collection,
    ContextPackage,
    ExportJob,
    Organization,
    OrganizationUser,
    Principle,
    ProcessingJob,
    Project,
    User,
)
from app.security.credentials import generate_api_token
from app.security.permissions import permissions_for_role, role_rank
from app.services import accounts

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("")
def get_workspace(tenant: TenantDep) -> dict:
    org = tenant.db.scalar(select(Organization).where(Organization.id == tenant.org_id))
    brands = tenant.db.scalars(select(Brand).order_by(Brand.created_at)).all()
    if tenant.brand_restriction:
        brands = [b for b in brands if b.id == tenant.brand_restriction]
    return {
        "organization": row_to_dict(org) if tenant.can("org.read") else {"id": str(org.id), "name": org.name, "slug": org.slug},
        "role": tenant.role_key,
        "permissions": sorted(tenant.permissions),
        "brands": [row_to_dict(b) for b in brands],
    }


class WorkspaceUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    legal_name: str | None = None
    contact_name: str | None = None
    contact_email: Email | None = None
    website: str | None = None
    industry: str | None = None
    country: str | None = None
    notes: str | None = None


@router.patch("")
def update_workspace(body: WorkspaceUpdateIn, tenant: TenantDep) -> dict:
    tenant.require("org.manage")
    org = tenant.db.scalar(select(Organization).where(Organization.id == tenant.org_id))
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(org, k, v)
    tenant.audit("organization.profile_updated", "organization", org.id, {"fields": sorted(changes)})
    tenant.db.flush()
    return row_to_dict(org)


@router.get("/overview")
def workspace_overview(tenant: TenantDep) -> dict:
    """Counts for the workspace overview. No organization filter is written here on purpose:
    Row Level Security scopes every query to the current organization."""
    tenant.require("org.read")
    db = tenant.db
    live = Asset.deleted_at.is_(None)

    def count(model, *where) -> int:
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    assets_by_type = dict(db.execute(select(Asset.asset_type, func.count()).where(live).group_by(Asset.asset_type)).all())
    assets_by_status = dict(
        db.execute(select(Asset.approval_status, func.count()).where(live).group_by(Asset.approval_status)).all()
    )
    storage = (db.scalar(select(func.coalesce(func.sum(Asset.file_size), 0))) or 0) + (
        db.scalar(select(func.coalesce(func.sum(AssetDerivative.file_size), 0))) or 0
    )
    recent = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(15)).all()
    return {
        "counts": {
            "brands": count(Brand),
            "assets": count(Asset, live),
            "collections": count(Collection),
            "projects": count(Project),
            "approved_principles": count(Principle, Principle.status == "approved"),
            "pending_analyses": count(AssetAnalysis, AssetAnalysis.status == "pending_review"),
            "pending_suggestions": count(AiSuggestion, AiSuggestion.status == "pending"),
            "context_packages": count(ContextPackage),
            "exports": count(ExportJob),
            "jobs_running": count(ProcessingJob, ProcessingJob.status.in_(["queued", "running"])),
            "jobs_failed": count(ProcessingJob, ProcessingJob.status.in_(["failed", "dead"])),
        },
        "assets_by_type": assets_by_type,
        "assets_by_status": assets_by_status,
        "storage_bytes": int(storage),
        "recent_activity": [
            {
                "action": a.action,
                "actor": a.actor_label,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "details": a.details,
                "created_at": a.created_at.isoformat(),
            }
            for a in recent
        ],
    }


# --- Members ---------------------------------------------------------------------------------
ORG_ROLES = ("customer_admin", "creative_director", "editor", "reviewer", "viewer")


def _member_out(m: OrganizationUser, u: User) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "user_id": str(u.id),
        "email": u.email,
        "full_name": u.full_name,
        "role": m.role_key,
        "status": m.status,
        "last_login_at": jsonable(u.last_login_at),
        "created_at": m.created_at.isoformat(),
    }


@router.get("/members")
def list_members(tenant: TenantDep) -> dict:
    tenant.require("users.read")
    rows = tenant.db.execute(
        select(OrganizationUser, User).join(User, User.id == OrganizationUser.user_id).order_by(User.email)
    ).all()
    return {"items": [_member_out(m, u) for m, u in rows], "roles": [
        {"key": r, "permissions": sorted(permissions_for_role(r))} for r in ORG_ROLES
    ]}


class MemberIn(BaseModel):
    email: Email
    full_name: str = ""
    role: str = Field(pattern="^(customer_admin|creative_director|editor|reviewer|viewer)$")
    password: str | None = Field(None, min_length=10)


def _check_can_assign(tenant, role: str) -> None:
    tenant.require("users.manage")
    if tenant.role_key not in ("platform_super_admin", "customer_admin") and role_rank(role) >= role_rank(tenant.role_key):
        raise Forbidden("You cannot assign a role equal to or above your own")


@router.post("/members", status_code=201)
def add_member(body: MemberIn, tenant: TenantDep) -> dict:
    _check_can_assign(tenant, body.role)
    user_id, temp_pw, created = accounts.find_or_create_user(body.email, body.full_name, body.password)
    existing = tenant.db.scalar(select(OrganizationUser).where(OrganizationUser.user_id == user_id))
    if existing:
        raise ValidationFailed("This user is already a member of the workspace")
    m = OrganizationUser(organization_id=tenant.org_id, user_id=user_id, role_key=body.role, invited_by=tenant.user_id)
    tenant.db.add(m)
    tenant.db.flush()
    tenant.audit("member.added", "user", user_id, {"email": body.email, "role": body.role, "new_user": created})
    u = tenant.db.scalar(select(User).where(User.id == user_id))
    out = _member_out(m, u)
    # Development-grade invitation: no e-mail service is configured, so a one-time temporary
    # password is returned to the administrator exactly once.
    out["temporary_password"] = temp_pw
    return out


class MemberUpdateIn(BaseModel):
    role: str | None = Field(None, pattern="^(customer_admin|creative_director|editor|reviewer|viewer)$")
    status: str | None = Field(None, pattern="^(active|suspended)$")


def _ensure_not_last_admin(tenant, member: OrganizationUser) -> None:
    if member.role_key != "customer_admin":
        return
    admins = tenant.db.scalar(
        select(func.count()).select_from(OrganizationUser).where(
            OrganizationUser.role_key == "customer_admin", OrganizationUser.status == "active"
        )
    )
    if admins <= 1:
        raise ValidationFailed("A workspace must keep at least one active customer administrator")


@router.patch("/members/{member_id}")
def update_member(member_id: uuid.UUID, body: MemberUpdateIn, tenant: TenantDep) -> dict:
    tenant.require("users.manage")
    m = tenant.db.scalar(select(OrganizationUser).where(OrganizationUser.id == member_id))
    if m is None:
        raise NotFound("Member not found")
    if body.role and body.role != m.role_key:
        _check_can_assign(tenant, body.role)
        _ensure_not_last_admin(tenant, m)
        m.role_key = body.role
    if body.status and body.status != m.status:
        if body.status == "suspended":
            _ensure_not_last_admin(tenant, m)
        m.status = body.status
    tenant.audit("member.updated", "user", m.user_id, body.model_dump(exclude_none=True))
    tenant.db.flush()
    u = tenant.db.scalar(select(User).where(User.id == m.user_id))
    return _member_out(m, u)


@router.delete("/members/{member_id}", status_code=204)
def remove_member(member_id: uuid.UUID, tenant: TenantDep) -> None:
    tenant.require("users.manage")
    m = tenant.db.scalar(select(OrganizationUser).where(OrganizationUser.id == member_id))
    if m is None:
        raise NotFound("Member not found")
    _ensure_not_last_admin(tenant, m)
    tenant.audit("member.removed", "user", m.user_id)
    tenant.db.delete(m)


# --- API tokens ------------------------------------------------------------------------------
class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field("viewer", pattern="^(customer_admin|creative_director|editor|reviewer|viewer)$")
    brand_id: uuid.UUID | None = None
    scopes: list[str] = Field(default_factory=list, description="Optional subset of the role's permissions")
    expires_in_days: int | None = Field(None, ge=1, le=3650)


def _token_out(t: ApiToken) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "name": t.name,
        "token_prefix": t.token_prefix,
        "role": t.role_key,
        "brand_id": jsonable(t.brand_id),
        "scopes": t.scopes,
        "created_at": t.created_at.isoformat(),
        "expires_at": jsonable(t.expires_at),
        "last_used_at": jsonable(t.last_used_at),
        "revoked_at": jsonable(t.revoked_at),
    }


@router.get("/api-tokens")
def list_tokens(tenant: TenantDep) -> dict:
    tenant.require("api_tokens.manage")
    return {"items": [_token_out(t) for t in tenant.db.scalars(select(ApiToken).order_by(ApiToken.created_at.desc()))]}


@router.post("/api-tokens", status_code=201)
def create_token(body: TokenIn, tenant: TenantDep) -> dict:
    tenant.require("api_tokens.manage")
    if tenant.role_key != "platform_super_admin" and role_rank(body.role) > role_rank(tenant.role_key):
        raise Forbidden("A token cannot have more privileges than its creator")
    allowed = permissions_for_role(body.role)
    unknown = [s for s in body.scopes if s not in allowed]
    if unknown:
        raise ValidationFailed("Scopes must be a subset of the role's permissions", details={"invalid": unknown})
    if body.brand_id and not tenant.db.scalar(select(Brand.id).where(Brand.id == body.brand_id)):
        raise NotFound("Brand not found")
    plaintext, prefix, digest = generate_api_token()
    t = ApiToken(
        organization_id=tenant.org_id,
        brand_id=body.brand_id,
        name=body.name,
        token_prefix=prefix,
        token_hash=digest,
        role_key=body.role,
        scopes=body.scopes,
        created_by=tenant.user_id,
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=body.expires_in_days) if body.expires_in_days else None,
    )
    tenant.db.add(t)
    tenant.db.flush()
    tenant.audit("api_token.created", "api_token", t.id, {"name": body.name, "role": body.role})
    return {**_token_out(t), "token": plaintext}


@router.post("/api-tokens/{token_id}/revoke")
def revoke_token(token_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("api_tokens.manage")
    t = tenant.db.scalar(select(ApiToken).where(ApiToken.id == token_id))
    if t is None:
        raise NotFound("Token not found")
    t.revoked_at = dt.datetime.now(dt.UTC)
    tenant.audit("api_token.revoked", "api_token", t.id)
    return _token_out(t)


# --- Audit log -------------------------------------------------------------------------------
@router.get("/audit-log")
def audit_log(
    tenant: TenantDep,
    params: PageParams = Depends(page_params),
    action: str | None = Query(None, max_length=120),
) -> dict:
    tenant.require("audit.read")
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        q = q.where(AuditLog.action.like(f"{action}%"))
    return paginate(
        tenant.db,
        q,
        params,
        lambda a: {
            "id": a.id,
            "actor": a.actor_label,
            "actor_type": a.actor_type,
            "action": a.action,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "ip_address": a.ip_address,
            "details": a.details,
            "created_at": a.created_at.isoformat(),
        },
    )
