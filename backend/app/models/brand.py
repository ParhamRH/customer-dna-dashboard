"""Brands, brand versions and the structured (authoritative) brand knowledge domains."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    DOMAIN_KEYS,
    KNOWLEDGE_STATUSES,
    ORIGINS,
    Base,
    TenantMixin,
    created_at_col,
    enum_check,
    same_org_fk,
    updated_at_col,
    uuid_pk,
)


def tsv(expr: str) -> Mapped[Any]:
    """Generated full-text column using the immutable bdna_tsv() helper (english stems + simple tokens)."""
    return mapped_column(TSVECTOR, Computed(f"bdna_tsv({expr})", persisted=True))


class Brand(TenantMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "slug"),
        enum_check("status", ("active", "archived")),
        ForeignKeyConstraint(
            ["organization_id", "current_version_id"],
            ["brand_versions.organization_id", "brand_versions.id"],
            use_alter=True,
            name="fk_brands_current_version_same_org",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    primary_language: Mapped[str] = mapped_column(String(16), nullable=False, server_default="en")
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class BrandScoped(TenantMixin):
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)


class BrandVersion(BrandScoped, Base):
    """Immutable published snapshot of the approved brand knowledge at a point in time."""

    __tablename__ = "brand_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("brand_id", "version_number"),
        same_org_fk("brand_id", "brands"),
        enum_check("status", ("published", "superseded")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="published")
    notes: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    snapshot_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    published_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    published_at: Mapped[dt.datetime] = created_at_col()


class KnowledgeDomain(Base):
    """Reference table of the ten knowledge domains (seeded by migration)."""

    __tablename__ = "knowledge_domains"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    entry_types: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))


class _Governed:
    """Fields shared by every piece of governed (human-approved) brand knowledge."""

    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    origin: Mapped[str] = mapped_column(String(32), nullable=False, server_default="human")
    source_suggestion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


def governed_checks() -> tuple:
    return (enum_check("status", KNOWLEDGE_STATUSES), enum_check("origin", ORIGINS))


class KnowledgeEntry(BrandScoped, _Governed, Base):
    """Rich-text + structured record inside a domain (mission, tone of voice, lighting direction…).

    ``entry_type`` is validated against the per-domain registry in app/knowledge/entry_types.py,
    so new entry types never need a schema migration.
    """

    __tablename__ = "knowledge_entries"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        same_org_fk("brand_id", "brands"),
        enum_check("domain_key", DOMAIN_KEYS),
        *governed_checks(),
        Index("ix_knowledge_entries_tsv", "search_tsv", postgresql_using="gin"),
        Index("ix_knowledge_entries_brand_domain", "brand_id", "domain_key"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    domain_key: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_domains.key"), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")  # Markdown
    structured: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(80)), nullable=False, server_default=text("'{}'"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    search_tsv: Mapped[Any] = tsv("coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(body,'')")


class Principle(BrandScoped, _Governed, Base):
    __tablename__ = "principles"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("brand_id", "code"),
        same_org_fk("brand_id", "brands"),
        enum_check(
            "classification",
            ("mandatory", "preferred", "optional", "prohibited", "context_dependent", "experimental"),
        ),
        *governed_checks(),
        Index("ix_principles_tsv", "search_tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)  # the definition
    rationale: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    domain_key: Mapped[str | None] = mapped_column(String(64), ForeignKey("knowledge_domains.key"))
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    examples: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    search_tsv: Mapped[Any] = tsv("coalesce(title,'') || ' ' || coalesce(statement,'') || ' ' || coalesce(rationale,'')")


class Guideline(BrandScoped, _Governed, Base):
    __tablename__ = "guidelines"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("brand_id", "slug"),
        same_org_fk("brand_id", "brands"),
        enum_check("domain_key", DOMAIN_KEYS),
        *governed_checks(),
        Index("ix_guidelines_tsv", "search_tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    domain_key: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_domains.key"), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    applies_to: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    search_tsv: Mapped[Any] = tsv("coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(body,'')")


class AestheticConcept(BrandScoped, _Governed, Base):
    """Controlled vocabulary entry. Related / opposing concepts and example assets live in `relationships`."""

    __tablename__ = "aesthetic_concepts"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("brand_id", "slug"),
        same_org_fk("brand_id", "brands"),
        enum_check("brand_relevance", ("core", "supporting", "peripheral", "neutral", "avoid")),
        *governed_checks(),
        Index("ix_aesthetic_concepts_tsv", "search_tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    attributes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    synonyms: Mapped[list[str]] = mapped_column(ARRAY(String(120)), nullable=False, server_default=text("'{}'"))
    brand_relevance: Mapped[str] = mapped_column(String(32), nullable=False, server_default="supporting")
    relevance_score: Mapped[float | None] = mapped_column(Numeric(4, 3))
    search_tsv: Mapped[Any] = tsv(
        "coalesce(name,'') || ' ' || coalesce(definition,'') || ' ' || bdna_join(synonyms)"
    )


class Palette(BrandScoped, Base):
    __tablename__ = "palettes"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        same_org_fk("brand_id", "brands"),
        enum_check("role", ("primary", "secondary", "accent", "neutral", "semantic", "extended")),
        enum_check("status", KNOWLEDGE_STATUSES),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class ColorToken(BrandScoped, Base):
    __tablename__ = "color_tokens"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("brand_id", "token_key"),
        same_org_fk("brand_id", "brands"),
        same_org_fk("palette_id", "palettes"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    palette_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    token_key: Mapped[str] = mapped_column(String(160), nullable=False)  # e.g. color.primary.ink
    hex: Mapped[str] = mapped_column(String(9), nullable=False)
    rgb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    hsl: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    oklch: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    cmyk: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    cmyk_is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    pantone: Mapped[str | None] = mapped_column(String(64))
    semantic_role: Mapped[str | None] = mapped_column(String(64))
    usage: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class TypographySystem(BrandScoped, Base):
    __tablename__ = "typography_systems"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        same_org_fk("brand_id", "brands"),
        enum_check("role", ("primary", "secondary", "display", "body", "mono", "accent")),
        enum_check("status", KNOWLEDGE_STATUSES),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    family: Mapped[str] = mapped_column(String(200), nullable=False)
    fallback_stack: Mapped[str] = mapped_column(String(400), nullable=False, server_default="sans-serif")
    source: Mapped[str | None] = mapped_column(String(64))  # google | adobe | custom | system | foundry
    source_url: Mapped[str | None] = mapped_column(String(500))
    license: Mapped[str | None] = mapped_column(String(200))
    weights: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, server_default=text("'{}'"))
    supports_italic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    hierarchy: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    usage: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class DesignToken(BrandScoped, Base):
    """W3C Design Tokens (DTCG) compatible token. Exported as JSON / CSS custom properties / Tailwind."""

    __tablename__ = "design_tokens"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("brand_id", "path"),
        same_org_fk("brand_id", "brands"),
        enum_check("domain_key", ("visual_identity", "design_language")),
        enum_check("status", KNOWLEDGE_STATUSES),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    path: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g. spacing.4, motion.duration.base
    token_type: Mapped[str] = mapped_column(String(32), nullable=False)  # DTCG $type
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_key: Mapped[str] = mapped_column(String(64), nullable=False, server_default="design_language")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class KnowledgeRevision(BrandScoped, Base):
    """Immutable history row written on every change to governed knowledge."""

    __tablename__ = "knowledge_revisions"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "version"),
        same_org_fk("brand_id", "brands"),
        Index("ix_knowledge_revisions_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()
