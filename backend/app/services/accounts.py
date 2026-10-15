"""Privileged account operations.

This is one of the few modules allowed to use ``system_session()`` (BYPASSRLS). Each function
is narrow and never returns tenant content: identity lookups, membership listing for the
signed-in user, user provisioning by e-mail, and organization creation.
"""
from __future__ import annotations

import datetime as dt
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update

from app.api.common import slugify
from app.api.errors import Conflict, TooManyRequests, Unauthorized, ValidationFailed
from app.config import get_settings
from app.db.session import system_session
from app.models import (
    AuditLog,
    AuthSession,
    Brand,
    Organization,
    OrganizationUser,
    Role,
    User,
)
from app.security.credentials import hash_password, issue_session_jwt, verify_password


@dataclass
class LoginResult:
    token: str
    expires_at: dt.datetime
    user: dict[str, Any]


def _throttle(s, email: str, ip: str | None, now: dt.datetime, cfg) -> None:  # noqa: ANN001
    """Refuse further attempts after too many recent failures for this e-mail or this IP. Counting
    uses the audit log, so throttling works across API processes without extra infrastructure."""
    since = now - dt.timedelta(minutes=cfg.login_window_minutes)
    base = select(func.count()).select_from(AuditLog).where(AuditLog.action == "auth.login_failed", AuditLog.created_at >= since)
    by_email = s.scalar(base.where(func.lower(AuditLog.actor_label) == email.strip().lower()[:320])) or 0
    by_ip = s.scalar(base.where(AuditLog.ip_address == ip)) if ip else 0
    if by_email >= cfg.login_max_failures_per_email or (by_ip or 0) >= cfg.login_max_failures_per_ip:
        raise TooManyRequests(f"Too many failed sign-in attempts. Try again in {cfg.login_window_minutes} minutes.",
                              details={"retry_after_seconds": cfg.login_window_minutes * 60})


def login(email: str, password: str, ip: str | None, user_agent: str | None) -> LoginResult:
    now = dt.datetime.now(dt.UTC)
    cfg = get_settings()
    result: LoginResult | None = None
    with system_session() as s:
        _throttle(s, email, ip, now, cfg)
        user = s.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
        ok = verify_password(user.password_hash if user else None, password)
        if user and ok and user.is_active:
            expires = now + dt.timedelta(hours=cfg.session_ttl_hours)
            sess = AuthSession(user_id=user.id, expires_at=expires, ip_address=ip, user_agent=(user_agent or "")[:400])
            s.add(sess)
            user.last_login_at = now
            s.flush()
            s.add(AuditLog(actor_user_id=user.id, actor_type="user", actor_label=user.email, action="auth.login", ip_address=ip))
            result = LoginResult(issue_session_jwt(user.id, sess.id, expires), expires, user_public(user))
    if result is None:
        # Recorded in its own committed transaction (raising inside the session would roll it back);
        # these rows drive sign-in throttling and appear in the platform activity log.
        with system_session() as s:
            s.add(AuditLog(actor_type="user", actor_label=email.strip().lower()[:320], action="auth.login_failed", ip_address=ip))
        raise Unauthorized("Invalid email or password")
    return result


def revoke_session(session_id: uuid.UUID) -> None:
    with system_session() as s:
        s.execute(update(AuthSession).where(AuthSession.id == session_id).values(revoked_at=func.now()))


def user_public(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "is_platform_admin": user.is_platform_admin,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def memberships_for_user(user_id: uuid.UUID, is_platform_admin: bool) -> list[dict[str, Any]]:
    """Workspaces the signed-in user can open (all active+archived ones for platform admins)."""
    with system_session() as s:
        if is_platform_admin:
            rows = s.execute(select(Organization).order_by(Organization.name)).scalars().all()
            return [
                {"organization_id": str(o.id), "slug": o.slug, "name": o.name, "status": o.status, "role": "platform_super_admin"}
                for o in rows
            ]
        rows = s.execute(
            select(Organization, OrganizationUser.role_key)
            .join(OrganizationUser, OrganizationUser.organization_id == Organization.id)
            .where(
                OrganizationUser.user_id == user_id,
                OrganizationUser.status == "active",
                Organization.status == "active",
            )
            .order_by(Organization.name)
        ).all()
        return [
            {"organization_id": str(o.id), "slug": o.slug, "name": o.name, "status": o.status, "role": role}
            for o, role in rows
        ]


def find_or_create_user(email: str, full_name: str, password: str | None) -> tuple[uuid.UUID, str | None, bool]:
    """Return (user_id, temporary_password_if_generated, created). Existing users keep their password."""
    email = email.strip()
    with system_session() as s:
        existing = s.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if existing:
            return existing.id, None, False
        temp = None
        if not password:
            temp = secrets.token_urlsafe(12)
            password = temp
        try:
            pw_hash = hash_password(password)
        except ValueError as e:
            raise ValidationFailed(str(e)) from e
        user = User(email=email, full_name=full_name or email.split("@")[0], password_hash=pw_hash)
        s.add(user)
        s.flush()
        return user.id, temp, True


def create_platform_admin(email: str, full_name: str, password: str) -> uuid.UUID:
    with system_session() as s:
        existing = s.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if existing:
            existing.is_platform_admin = True
            return existing.id
        user = User(email=email, full_name=full_name, password_hash=hash_password(password), is_platform_admin=True)
        s.add(user)
        s.flush()
        return user.id


def create_organization(
    *,
    name: str,
    slug: str | None,
    profile: dict[str, Any],
    first_brand_name: str | None,
    admin_email: str | None,
    admin_name: str | None,
    admin_password: str | None,
    actor_id: uuid.UUID | None,
    actor_label: str | None,
) -> dict[str, Any]:
    slug = slugify(slug or name)
    with system_session() as s:
        if s.scalar(select(Organization.id).where(Organization.slug == slug)):
            raise Conflict(f"An organization with slug '{slug}' already exists")
        org = Organization(name=name, slug=slug, **profile)
        s.add(org)
        s.flush()
        brand_id = None
        if first_brand_name:
            brand = Brand(organization_id=org.id, name=first_brand_name, slug=slugify(first_brand_name), created_by=actor_id)
            s.add(brand)
            s.flush()
            brand_id = brand.id
        s.add(
            AuditLog(
                organization_id=org.id,
                actor_user_id=actor_id,
                actor_type="user",
                actor_label=actor_label,
                action="organization.created",
                entity_type="organization",
                entity_id=str(org.id),
                details={"name": name, "slug": slug},
            )
        )
    temp_password = None
    admin_user_id = None
    if admin_email:
        admin_user_id, temp_password, _ = find_or_create_user(admin_email, admin_name or "", admin_password)
        with system_session() as s:
            s.add(OrganizationUser(organization_id=org.id, user_id=admin_user_id, role_key="customer_admin", invited_by=actor_id))
    return {
        "organization_id": str(org.id),
        "slug": slug,
        "brand_id": str(brand_id) if brand_id else None,
        "admin_user_id": str(admin_user_id) if admin_user_id else None,
        "admin_temporary_password": temp_password,
    }


def assignable_roles() -> list[dict[str, Any]]:
    with system_session() as s:
        rows = s.scalars(select(Role).where(Role.scope == "organization").order_by(Role.rank.desc())).all()
        return [{"key": r.key, "name": r.name, "rank": r.rank} for r in rows]
