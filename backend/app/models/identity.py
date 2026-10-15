from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    TenantMixin,
    created_at_col,
    enum_check,
    same_org_fk,
    updated_at_col,
    uuid_pk,
)


class User(Base):
    """Global identity. A user may be a member of several organizations."""

    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", text("lower(email)"), unique=True),)

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    password_hash: Mapped[str | None] = mapped_column(Text)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[dt.datetime] = created_at_col()
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))


class Organization(Base):
    """A customer. The root of tenant isolation."""

    __tablename__ = "organizations"
    __table_args__ = (enum_check("status", ("active", "archived", "pending_deletion")),)

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    website: Mapped[str | None] = mapped_column(String(500))
    industry: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    storage_quota_bytes: Mapped[int | None] = mapped_column(BigInteger)
    retention_days_after_archive: Mapped[int | None] = mapped_column(BigInteger)
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_requested_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class Role(Base):
    """Reference table, seeded by migration. key is the stable identifier."""

    __tablename__ = "roles"
    __table_args__ = (enum_check("scope", ("platform", "organization")),)

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    rank: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class Permission(Base):
    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_key: Mapped[str] = mapped_column(String(64), ForeignKey("roles.key", ondelete="CASCADE"), primary_key=True)
    permission_key: Mapped[str] = mapped_column(
        String(64), ForeignKey("permissions.key", ondelete="CASCADE"), primary_key=True
    )


class OrganizationUser(TenantMixin, Base):
    __tablename__ = "organization_users"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        enum_check("status", ("active", "invited", "suspended")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_key: Mapped[str] = mapped_column(String(64), ForeignKey("roles.key"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class ApiToken(TenantMixin, Base):
    """Long-lived credential for REST/MCP clients. Only a SHA-256 hash is stored."""

    __tablename__ = "api_tokens"
    __table_args__ = (same_org_fk("brand_id", "brands"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # optional brand restriction
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    role_key: Mapped[str] = mapped_column(String(64), ForeignKey("roles.key"), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, server_default=text("'{}'"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = created_at_col()


class AuditLog(Base):
    """Append-only. The app role may INSERT and SELECT, never UPDATE/DELETE (enforced by grants)."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_created", "organization_id", "created_at"),
        # login throttling looks up recent failures by e-mail and by IP (migration 0003)
        Index("ix_audit_logs_login_failed_email", func.lower(text("actor_label")), "created_at",
              postgresql_where=text("action = 'auth.login_failed'")),
        Index("ix_audit_logs_login_failed_ip", "ip_address", "created_at", postgresql_where=text("action = 'auth.login_failed'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)  # user | api_token | system
    actor_label: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
