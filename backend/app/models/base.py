from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    MetaData,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Bumped whenever the export/record schema changes in a way consumers must know about.
SCHEMA_VERSION = 1


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def created_at_col() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at_col() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


def enum_check(column: str, values: list[str] | tuple[str, ...], name: str | None = None) -> CheckConstraint:
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name or f"{column}_valid")


class TenantMixin:
    """Every tenant-owned row carries organization_id; RLS keys off it."""

    @declared_attr
    def organization_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


def brand_fk(nullable: bool = False) -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), nullable=nullable, index=True)


def same_org_fk(
    local_col: str, remote_table: str, ondelete: str = "CASCADE", nullable_ref: bool = False, use_alter: bool = False
) -> ForeignKeyConstraint:
    """Composite FK (organization_id, <x>_id) -> <table>(organization_id, id).

    Guarantees at the database level that a child row can only reference a parent in the
    SAME organization — cross-tenant references are structurally impossible.
    """
    if nullable_ref:
        # Only null the reference column, never organization_id (PostgreSQL 15+ syntax).
        ondelete = f"SET NULL ({local_col})"
    return ForeignKeyConstraint(
        ["organization_id", local_col],
        [f"{remote_table}.organization_id", f"{remote_table}.id"],
        ondelete=ondelete,
        use_alter=use_alter,
        name=f"fk_{local_col}_{remote_table}_same_org"[:63],
    )


# Shared vocabularies -------------------------------------------------------------------------
KNOWLEDGE_STATUSES = ("draft", "in_review", "approved", "deprecated", "rejected", "archived")
APPROVAL_STATUSES = ("pending", "approved", "rejected", "archived")
ORIGINS = ("human", "ai_suggestion", "import")

DOMAIN_KEYS = (
    "brand_foundation",
    "visual_identity",
    "art_direction",
    "aesthetic_language",
    "design_language",
    "brand_language",
    "creative_assets",
    "principles_guidelines",
    "projects_applications",
    "ai_knowledge",
)
