"""Customer (organization) management — platform administrator endpoints.

GET /v1/organizations is dual-purpose: platform admins get every customer with operational
stats; ordinary users get the workspaces they belong to.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.common import jsonable, row_to_dict
from app.api.deps import IdentityDep, PlatformAdminDep
from app.api.errors import NotFound, ValidationFailed
from app.api.types import Email
from app.db.session import system_session
from app.models import AuditLog, Organization, ProcessingJob
from app.services import accounts, platform

router = APIRouter(tags=["organizations"])


class OrgProfile(BaseModel):
    legal_name: str | None = Field(None, max_length=300)
    contact_name: str | None = Field(None, max_length=200)
    contact_email: Email | None = None
    website: str | None = Field(None, max_length=500)
    industry: str | None = Field(None, max_length=120)
    country: str | None = Field(None, max_length=80)
    notes: str | None = None
    storage_quota_bytes: int | None = Field(None, ge=0)
    retention_days_after_archive: int | None = Field(None, ge=0, le=3650)


class OrgCreateIn(OrgProfile):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(None, max_length=80)
    first_brand_name: str | None = Field(None, max_length=200)
    admin_email: Email | None = None
    admin_name: str | None = None
    admin_password: str | None = Field(None, min_length=10)


class OrgUpdateIn(OrgProfile):
    name: str | None = Field(None, min_length=1, max_length=200)
    settings: dict[str, Any] | None = None


def _platform_audit(identity, org_id: uuid.UUID, action: str, details: dict | None = None) -> None:
    with system_session() as s:
        s.add(
            AuditLog(
                organization_id=org_id,
                actor_user_id=identity.user_id,
                actor_type="user",
                actor_label=identity.label,
                action=action,
                entity_type="organization",
                entity_id=str(org_id),
                details=details or {},
            )
        )


@router.get("/organizations")
def list_organizations(
    identity: IdentityDep,
    search: str | None = Query(None, max_length=100),
    status: str | None = Query(None, pattern="^(active|archived|pending_deletion)$"),
) -> dict:
    if identity.kind == "user" and identity.is_platform_admin:
        items = platform.customer_list(search, status)
        return {"items": items, "total": len(items)}
    if identity.kind == "api_token":
        return {"items": [{"id": str(identity.token_org_id)}], "total": 1}
    items = accounts.memberships_for_user(identity.user_id, False)
    return {"items": items, "total": len(items)}


@router.post("/organizations", status_code=201)
def create_organization(body: OrgCreateIn, identity: PlatformAdminDep) -> dict:
    profile = body.model_dump(
        include={
            "legal_name", "contact_name", "contact_email", "website", "industry", "country", "notes",
            "storage_quota_bytes", "retention_days_after_archive",
        }
    )
    return accounts.create_organization(
        name=body.name,
        slug=body.slug,
        profile=profile,
        first_brand_name=body.first_brand_name,
        admin_email=body.admin_email,
        admin_name=body.admin_name,
        admin_password=body.admin_password,
        actor_id=identity.user_id,
        actor_label=identity.label,
    )


def _get_org(s, org_id: uuid.UUID) -> Organization:
    org = s.scalar(select(Organization).where(Organization.id == org_id))
    if org is None:
        raise NotFound("Organization not found")
    return org


@router.get("/organizations/{org_id}")
def get_organization(org_id: uuid.UUID, identity: IdentityDep) -> dict:
    if not (identity.kind == "user" and identity.is_platform_admin):
        mine = {m["organization_id"] for m in accounts.memberships_for_user(identity.user_id, False)} if identity.user_id else set()
        if identity.kind == "api_token":
            mine = {str(identity.token_org_id)}
        if str(org_id) not in mine:
            raise NotFound("Organization not found")
    with system_session() as s:
        org = row_to_dict(_get_org(s, org_id))
    stats = next((c for c in platform.customer_list() if c["id"] == str(org_id)), {}) if identity.is_platform_admin else {}
    return {**org, "stats": stats}


@router.patch("/organizations/{org_id}")
def update_organization(org_id: uuid.UUID, body: OrgUpdateIn, identity: PlatformAdminDep) -> dict:
    changes = body.model_dump(exclude_unset=True)
    with system_session() as s:
        org = _get_org(s, org_id)
        for k, v in changes.items():
            setattr(org, k, v)
        s.flush()
        out = row_to_dict(org)
    _platform_audit(identity, org_id, "organization.updated", {"fields": sorted(changes)})
    return out


@router.post("/organizations/{org_id}/archive")
def archive_organization(org_id: uuid.UUID, identity: PlatformAdminDep) -> dict:
    with system_session() as s:
        org = _get_org(s, org_id)
        if org.status == "pending_deletion":
            raise ValidationFailed("Organization is pending deletion")
        org.status, org.archived_at = "archived", dt.datetime.now(dt.UTC)
    _platform_audit(identity, org_id, "organization.archived")
    return {"id": str(org_id), "status": "archived"}


@router.post("/organizations/{org_id}/reactivate")
def reactivate_organization(org_id: uuid.UUID, identity: PlatformAdminDep) -> dict:
    with system_session() as s:
        org = _get_org(s, org_id)
        org.status, org.archived_at, org.deletion_requested_at = "active", None, None
        # cancel any scheduled purge
        for job in s.scalars(
            select(ProcessingJob).where(
                ProcessingJob.organization_id == org_id,
                ProcessingJob.job_type == "organization.purge",
                ProcessingJob.status == "queued",
            )
        ):
            job.status = "cancelled"
    _platform_audit(identity, org_id, "organization.reactivated")
    return {"id": str(org_id), "status": "active"}


class DeletionIn(BaseModel):
    confirm_slug: str
    grace_days: int = Field(30, ge=0, le=365)


@router.post("/organizations/{org_id}/request-deletion")
def request_deletion(org_id: uuid.UUID, body: DeletionIn, identity: PlatformAdminDep) -> dict:
    """Retention workflow: the org is locked immediately and purged after the grace period.
    Reactivating before then cancels the purge."""
    now = dt.datetime.now(dt.UTC)
    with system_session() as s:
        org = _get_org(s, org_id)
        if body.confirm_slug != org.slug:
            raise ValidationFailed("confirm_slug does not match the organization slug")
        org.status, org.deletion_requested_at = "pending_deletion", now
        org.archived_at = org.archived_at or now
        purge_at = now + dt.timedelta(days=body.grace_days)
        s.add(
            ProcessingJob(
                organization_id=org_id,
                job_type="organization.purge",
                entity_type="organization",
                entity_id=org_id,
                run_after=purge_at,
                max_attempts=5,
                created_by=identity.user_id,
            )
        )
    _platform_audit(identity, org_id, "organization.deletion_requested", {"purge_at": purge_at.isoformat()})
    return {"id": str(org_id), "status": "pending_deletion", "purge_at": purge_at.isoformat()}


# --- Platform dashboards ---------------------------------------------------------------------
@router.get("/platform/overview")
def platform_overview(_: PlatformAdminDep) -> dict:
    return platform.overview()


@router.get("/platform/activity")
def platform_activity(
    _: PlatformAdminDep, limit: int = Query(50, ge=1, le=500), organization_id: uuid.UUID | None = None
) -> dict:
    return {"items": platform.recent_activity(limit, organization_id)}


@router.get("/platform/jobs")
def platform_jobs(
    _: PlatformAdminDep,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    return platform.jobs(status, limit, offset)


@router.get("/platform/roles")
def platform_roles(_: IdentityDep) -> dict:
    from app.security.permissions import permissions_for_role

    roles = accounts.assignable_roles()
    for r in roles:
        r["permissions"] = sorted(permissions_for_role(r["key"]))
    return {"items": roles}


_ = jsonable
