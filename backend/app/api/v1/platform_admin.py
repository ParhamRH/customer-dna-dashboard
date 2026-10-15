"""Platform administrator console: users across customers, export registry, integration and
token inventory, system settings.

Like ``app.services.platform`` these endpoints use the privileged role but only ever return
identity records, metadata and counts — never brand knowledge or asset content. Opening a
customer's content always goes through the RLS-enforced workspace endpoints.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import secrets
import shutil
import uuid
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update

from app import __version__
from app.api.common import jsonable
from app.api.deps import PlatformAdminDep
from app.api.errors import NotFound, ValidationFailed
from app.api.types import Email
from app.config import get_settings
from app.db.session import system_session
from app.models import (
    ApiToken,
    AuditLog,
    AuthSession,
    Brand,
    ExportJob,
    ImportJob,
    Integration,
    Organization,
    OrganizationUser,
    ProcessingJob,
    User,
)
from app.security.credentials import hash_password

router = APIRouter(prefix="/platform", tags=["platform"])


def _audit(identity, action: str, entity_type: str, entity_id: Any, details: dict | None = None,
           org_id: uuid.UUID | None = None) -> None:  # noqa: ANN001
    with system_session() as s:
        s.add(AuditLog(organization_id=org_id, actor_user_id=identity.user_id, actor_type="user", actor_label=identity.label,
                       action=action, entity_type=entity_type, entity_id=str(entity_id), details=details or {}))


# --- Users ---------------------------------------------------------------------------------------
def _user_out(u: User, memberships: list[dict[str, Any]], active_sessions: int) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "email": u.email,
        "full_name": u.full_name,
        "is_platform_admin": u.is_platform_admin,
        "is_active": u.is_active,
        "last_login_at": jsonable(u.last_login_at),
        "created_at": u.created_at.isoformat(),
        "active_sessions": active_sessions,
        "memberships": memberships,
    }


@router.get("/users")
def list_users(
    _: PlatformAdminDep,
    search: str | None = Query(None, max_length=200),
    organization_id: uuid.UUID | None = None,
    platform_admins_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    now = dt.datetime.now(dt.UTC)
    with system_session() as s:
        q = select(User)
        if search:
            like = f"%{search.lower()}%"
            q = q.where(or_(func.lower(User.email).like(like), func.lower(User.full_name).like(like)))
        if platform_admins_only:
            q = q.where(User.is_platform_admin.is_(True))
        if organization_id:
            q = q.where(User.id.in_(select(OrganizationUser.user_id).where(OrganizationUser.organization_id == organization_id)))
        total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
        users = s.scalars(q.order_by(User.is_platform_admin.desc(), User.email).limit(limit).offset(offset)).all()
        ids = [u.id for u in users]
        mem: dict[uuid.UUID, list[dict[str, Any]]] = {}
        if ids:
            for m, oname, oslug, ostatus in s.execute(
                select(OrganizationUser, Organization.name, Organization.slug, Organization.status)
                .join(Organization, Organization.id == OrganizationUser.organization_id)
                .where(OrganizationUser.user_id.in_(ids))
                .order_by(Organization.name)
            ).all():
                mem.setdefault(m.user_id, []).append({
                    "membership_id": str(m.id), "organization_id": str(m.organization_id), "organization_name": oname,
                    "organization_slug": oslug, "organization_status": ostatus, "role": m.role_key, "status": m.status,
                })
        sess = dict(s.execute(
            select(AuthSession.user_id, func.count())
            .where(AuthSession.user_id.in_(ids), AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
            .group_by(AuthSession.user_id)
        ).all()) if ids else {}
        return {"items": [_user_out(u, mem.get(u.id, []), int(sess.get(u.id, 0))) for u in users],
                "total": total, "limit": limit, "offset": offset}


class PlatformUserIn(BaseModel):
    email: Email
    full_name: str = Field("", max_length=200)
    password: str | None = Field(None, min_length=10, max_length=500)
    is_platform_admin: bool = True


@router.post("/users", status_code=201)
def create_user(body: PlatformUserIn, identity: PlatformAdminDep) -> dict:
    """Create a platform-level user (typically another platform administrator).
    Customer users are normally invited from inside a workspace."""
    temp = None
    with system_session() as s:
        if s.scalar(select(User.id).where(func.lower(User.email) == body.email.lower())):
            raise ValidationFailed("A user with this e-mail already exists")
        pw = body.password
        if not pw:
            temp = pw = secrets.token_urlsafe(12)
        u = User(email=body.email, full_name=body.full_name or body.email.split("@")[0], password_hash=hash_password(pw),
                 is_platform_admin=body.is_platform_admin)
        s.add(u)
        s.flush()
        out = _user_out(u, [], 0)
    _audit(identity, "platform.user_created", "user", out["id"], {"email": body.email, "platform_admin": body.is_platform_admin})
    return {**out, "temporary_password": temp}


class PlatformUserUpdateIn(BaseModel):
    full_name: str | None = Field(None, max_length=200)
    is_active: bool | None = None
    is_platform_admin: bool | None = None


@router.patch("/users/{user_id}")
def update_user(user_id: uuid.UUID, body: PlatformUserUpdateIn, identity: PlatformAdminDep) -> dict:
    changes = body.model_dump(exclude_unset=True)
    with system_session() as s:
        u = s.scalar(select(User).where(User.id == user_id))
        if u is None:
            raise NotFound("User not found")
        if user_id == identity.user_id and (changes.get("is_active") is False or changes.get("is_platform_admin") is False):
            raise ValidationFailed("You cannot deactivate yourself or remove your own administrator access")
        demoting = (changes.get("is_platform_admin") is False or changes.get("is_active") is False) and u.is_platform_admin
        if demoting:
            admins = s.scalar(select(func.count()).select_from(User).where(User.is_platform_admin.is_(True), User.is_active.is_(True))) or 0
            if admins <= 1:
                raise ValidationFailed("The platform must keep at least one active platform administrator")
        for k, v in changes.items():
            setattr(u, k, v)
        if changes.get("is_active") is False:
            s.execute(update(AuthSession).where(AuthSession.user_id == u.id, AuthSession.revoked_at.is_(None)).values(revoked_at=func.now()))
        s.flush()
        out = _user_out(u, [], 0)
    _audit(identity, "platform.user_updated", "user", user_id, changes)
    return out


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: uuid.UUID, identity: PlatformAdminDep) -> dict:
    """Issue a one-time temporary password and revoke every session of the user.
    (No e-mail service is configured; the administrator hands the password over securely.)"""
    temp = secrets.token_urlsafe(12)
    with system_session() as s:
        u = s.scalar(select(User).where(User.id == user_id))
        if u is None:
            raise NotFound("User not found")
        u.password_hash = hash_password(temp)
        s.execute(update(AuthSession).where(AuthSession.user_id == u.id, AuthSession.revoked_at.is_(None)).values(revoked_at=func.now()))
        email = u.email
    _audit(identity, "platform.password_reset", "user", user_id, {"email": email})
    return {"id": str(user_id), "temporary_password": temp}


@router.post("/users/{user_id}/revoke-sessions")
def revoke_sessions(user_id: uuid.UUID, identity: PlatformAdminDep) -> dict:
    with system_session() as s:
        n = s.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
                      .values(revoked_at=func.now())).rowcount
    _audit(identity, "platform.sessions_revoked", "user", user_id, {"count": n})
    return {"revoked": n}


# --- Exports / imports registry ------------------------------------------------------------------
@router.get("/exports")
def list_exports(
    _: PlatformAdminDep,
    organization_id: uuid.UUID | None = None,
    status: str | None = Query(None, pattern="^(queued|running|completed|failed|expired)$"),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    with system_session() as s:
        q = select(ExportJob, Organization.name, Organization.slug).join(Organization, Organization.id == ExportJob.organization_id)
        if organization_id:
            q = q.where(ExportJob.organization_id == organization_id)
        if status:
            q = q.where(ExportJob.status == status)
        rows = s.execute(q.order_by(ExportJob.created_at.desc()).limit(limit)).all()
        brand_ids = {b for e, _, _ in rows for b in (e.brand_ids or [])}
        names = dict(s.execute(select(Brand.id, Brand.name).where(Brand.id.in_(brand_ids))).all()) if brand_ids else {}
        items = [{
            "id": str(e.id), "organization_id": str(e.organization_id), "organization_name": oname, "organization_slug": oslug,
            "mode": e.mode, "status": e.status, "brand_names": [names.get(b) for b in e.brand_ids or [] if b in names],
            "domains": ((e.options or {}).get("selection") or {}).get("domains") or [],
            "include_originals": (e.options or {}).get("include_originals"),
            "file_count": e.file_count, "size_bytes": e.size_bytes, "archive_checksum": e.archive_checksum,
            "error": (e.error or "")[:300] or None, "created_at": e.created_at.isoformat(),
            "completed_at": jsonable(e.completed_at), "expires_at": jsonable(e.expires_at),
            "download_available": e.status == "completed" and e.storage_uri is not None,
        } for e, oname, oslug in rows]
        imports = [{
            "id": str(i.id), "organization_id": str(i.organization_id), "organization_name": oname, "status": i.status,
            "filename": (i.options or {}).get("filename"), "created_at": i.created_at.isoformat(),
        } for i, oname in s.execute(
            select(ImportJob, Organization.name).join(Organization, Organization.id == ImportJob.organization_id)
            .order_by(ImportJob.created_at.desc()).limit(50)
        ).all()]
    return {"items": items, "imports": imports}


# --- Integrations & tokens inventory -------------------------------------------------------------
@router.get("/integrations")
def integrations_inventory(_: PlatformAdminDep) -> dict:
    now = dt.datetime.now(dt.UTC)
    with system_session() as s:
        orgs = {o.id: o for o in s.scalars(select(Organization).order_by(Organization.name))}
        per: dict[uuid.UUID, dict[str, Any]] = {
            oid: {"organization_id": str(oid), "organization_name": o.name, "organization_slug": o.slug, "status": o.status,
                  "integrations": {}, "active_tokens": 0, "tokens_used_last_7_days": 0, "last_token_use_at": None}
            for oid, o in orgs.items()
        }
        for oid, kind, status, n in s.execute(
            select(Integration.organization_id, Integration.kind, Integration.status, func.count())
            .group_by(Integration.organization_id, Integration.kind, Integration.status)
        ).all():
            if oid in per:
                per[oid]["integrations"].setdefault(kind, {})[status] = n
        active = (ApiToken.revoked_at.is_(None)) & (or_(ApiToken.expires_at.is_(None), ApiToken.expires_at > now))
        for oid, n, last in s.execute(
            select(ApiToken.organization_id, func.count(), func.max(ApiToken.last_used_at)).where(active).group_by(ApiToken.organization_id)
        ).all():
            if oid in per:
                per[oid]["active_tokens"] = n
                per[oid]["last_token_use_at"] = jsonable(last)
        for oid, n in s.execute(
            select(ApiToken.organization_id, func.count()).where(active, ApiToken.last_used_at >= now - dt.timedelta(days=7))
            .group_by(ApiToken.organization_id)
        ).all():
            if oid in per:
                per[oid]["tokens_used_last_7_days"] = n
        webhook_failures = s.scalar(select(func.count()).select_from(ProcessingJob).where(
            ProcessingJob.job_type == "webhook.deliver", ProcessingJob.status.in_(["failed", "dead"]))) or 0
    from app.ai import registry

    return {"customers": list(per.values()), "ai": registry.describe(), "webhook_delivery_failures": webhook_failures,
            "mcp": _mcp_info()}


def _mcp_info() -> dict[str, Any]:
    from app.api.v1.integrations import mcp_info

    return mcp_info()


# --- System settings (read-only, no secrets) ------------------------------------------------------
def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


@router.get("/settings")
def system_settings(_: PlatformAdminDep) -> dict:
    s = get_settings()
    from app.ai import registry

    ai = registry.describe()
    warnings: list[str] = []
    if s.secret_key.startswith("dev-insecure") or s.secret_key.startswith("test-"):
        warnings.append("BDNA_SECRET_KEY is a development value — set a strong secret before production use.")
    if not s.encryption_key:
        warnings.append("BDNA_ENCRYPTION_KEY is not set — integration secrets are encrypted with a key derived from the secret key.")
    if not s.cookie_secure:
        warnings.append("BDNA_COOKIE_SECURE is false — enable it when the dashboard is served over HTTPS.")
    if s.storage_backend == "local":
        warnings.append("Local file storage is in use — configure S3-compatible storage (e.g. Cloudflare R2) for production.")
    dev_caps = [k for k, v in ai.items() if v.get("development_adapter")]
    if dev_caps:
        warnings.append("Development AI adapters are active for: " + ", ".join(dev_caps) +
                        ". Their output is heuristic and labelled as such; configure a provider key for real analysis.")
    tools = {
        "ffmpeg": bool(shutil.which(s.ffmpeg_binary)),
        "ffprobe": bool(shutil.which(s.ffprobe_binary)),
        "tesseract": bool(shutil.which(s.tesseract_binary)),
        "pymupdf": _has_module("pymupdf") or _has_module("fitz"),
        "scenedetect": _has_module("scenedetect"),
        "opencv": _has_module("cv2"),
        "trimesh": _has_module("trimesh"),
        "docling": _has_module("docling"),
    }
    with system_session() as db:
        queue = dict(db.execute(select(ProcessingJob.status, func.count()).group_by(ProcessingJob.status)).all())
        oldest = db.scalar(select(func.min(ProcessingJob.created_at)).where(ProcessingJob.status == "queued",
                                                                            ProcessingJob.run_after <= func.now()))
    return {
        "version": __version__,
        "environment": s.environment,
        "security": {
            "session_ttl_hours": s.session_ttl_hours, "cookie_secure": s.cookie_secure, "cors_origins": s.cors_origins,
            "encryption_key_configured": bool(s.encryption_key), "csrf": "double-submit header X-BDNA-CSRF on cookie sessions",
            "database_roles": {"app": s.db_app_role, "system": s.db_system_role, "rls": "forced on every tenant table"},
        },
        "storage": {
            "backend": s.storage_backend, "bucket": s.s3_bucket or None,
            "endpoint": (s.s3_endpoint_url.split("://", 1)[-1].split("/", 1)[0] if s.s3_endpoint_url else None),
            "signed_url_ttl_seconds": s.signed_url_ttl_seconds, "max_upload_bytes": s.max_upload_bytes,
            "public_base_url": s.public_base_url,
        },
        "ai": {**ai, "keys_configured": {"anthropic": bool(s.anthropic_api_key), "openai": bool(s.openai_api_key),
                                         "visual_embedding_service": bool(s.visual_embedding_url)},
               "max_images_per_asset": s.ai_max_images_per_asset},
        "media": {"tools": tools, "max_video_keyframes": s.max_video_keyframes, "max_document_pages_rendered": s.max_document_pages_rendered},
        "workers": {"concurrency": s.worker_concurrency, "poll_seconds": s.worker_poll_seconds,
                    "job_lock_timeout_seconds": s.job_lock_timeout_seconds, "queue": queue,
                    "oldest_runnable_job_at": jsonable(oldest)},
        "exports": {"ttl_days": s.export_ttl_days},
        "mcp": _mcp_info(),
        "warnings": warnings,
    }
