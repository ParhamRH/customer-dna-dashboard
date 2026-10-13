"""Projects, the polymorphic relationship graph, AI operations and platform operations."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
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
from app.models.brand import BrandScoped, tsv

PROJECT_TYPES = (
    "website_design",
    "website_development",
    "branding_campaign",
    "social_media",
    "product_design",
    "packaging",
    "advertising",
    "presentation",
    "digital_application",
    "video_production",
    "graphic_design",
    "image_generation",
    "copywriting",
    "other",
)

# Entity types that can participate in the relationship graph, mapped to their tables.
GRAPH_ENTITY_TABLES = {
    "asset": "assets",
    "asset_segment": "asset_segments",
    "principle": "principles",
    "guideline": "guidelines",
    "aesthetic_concept": "aesthetic_concepts",
    "knowledge_entry": "knowledge_entries",
    "project": "projects",
    "collection": "collections",
    "palette": "palettes",
    "color_token": "color_tokens",
    "typography_system": "typography_systems",
    "design_token": "design_tokens",
    "external_reference": "external_references",
}

RELATION_TYPES = (
    "exemplifies",  # asset -> concept/principle: the asset is an example of it
    "violates",  # asset -> principle: counter-example
    "related_to",  # symmetric association
    "opposes",  # concept <-> concept
    "broader_than",  # concept hierarchy
    "applies_to",  # principle/guideline -> project / domain entity
    "uses",  # project -> asset/palette/typography
    "derived_from",  # entity -> source asset/document
    "supports",  # guideline -> principle
    "references",  # generic citation
    "part_of",  # asset -> moodboard/collection-like grouping
)


class Project(BrandScoped, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("brand_id", "slug"),
        same_org_fk("brand_id", "brands"),
        enum_check("project_type", PROJECT_TYPES),
        enum_check("status", ("planning", "active", "completed", "archived")),
        Index("ix_projects_tsv", "search_tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="planning")
    description: Mapped[str | None] = mapped_column(Text)
    objectives: Mapped[str | None] = mapped_column(Text)
    audience: Mapped[str | None] = mapped_column(Text)
    deliverables: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    selected_domains: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, server_default=text("'{}'"))
    brief: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    due_date: Mapped[dt.date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()
    search_tsv: Mapped[Any] = tsv(
        "coalesce(name,'') || ' ' || coalesce(description,'') || ' ' || coalesce(objectives,'')"
    )


class Relationship(BrandScoped, Base):
    """Typed edge between two brand entities. Endpoints are validated by a trigger to exist
    in the SAME organization (see migration 0002), so cross-tenant edges are impossible."""

    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("source_type", "source_id", "relation_type", "target_type", "target_id"),
        same_org_fk("brand_id", "brands"),
        enum_check("relation_type", RELATION_TYPES),
        enum_check("source_type", tuple(GRAPH_ENTITY_TABLES)),
        enum_check("target_type", tuple(GRAPH_ENTITY_TABLES)),
        enum_check("origin", ("human", "ai_suggestion", "import")),
        enum_check("status", ("approved", "suggested", "rejected")),
        Index("ix_relationships_source", "source_type", "source_id"),
        Index("ix_relationships_target", "target_type", "target_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, server_default="1")
    origin: Mapped[str] = mapped_column(String(32), nullable=False, server_default="human")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="approved")
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    note: Mapped[str | None] = mapped_column(Text)
    source_suggestion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()


class Embedding(BrandScoped, Base):
    """Vector for any entity. The vector column has no fixed dimension so several embedding
    models can coexist; per-(model, dimension) HNSW expression indexes keep search fast."""

    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "segment", "modality", "model"),
        same_org_fk("brand_id", "brands"),
        enum_check("modality", ("text", "visual")),
        Index("ix_embeddings_lookup", "organization_id", "brand_id", "modality", "model"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    segment: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    modality: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_preview: Mapped[str | None] = mapped_column(Text)
    is_development_adapter: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[dt.datetime] = created_at_col()


class ProcessingJob(TenantMixin, Base):
    """Durable job queue row. Claimed with SELECT … FOR UPDATE SKIP LOCKED."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        same_org_fk("brand_id", "brands"),
        enum_check("status", ("queued", "running", "succeeded", "failed", "dead", "cancelled")),
        Index("ix_processing_jobs_claim", "status", "run_after", "priority"),
        Index("ix_processing_jobs_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="queued")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    run_after: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    locked_by: Mapped[str | None] = mapped_column(String(120))
    locked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class AiSuggestion(BrandScoped, Base):
    """A proposal produced by AI (principle, concept link, tag, relationship…). It becomes
    official knowledge only when a human accepts it, which creates a separate governed record."""

    __tablename__ = "ai_suggestions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        same_org_fk("brand_id", "brands"),
        same_org_fk("source_asset_id", "assets", nullable_ref=True),
        same_org_fk("source_analysis_id", "asset_analyses", nullable_ref=True),
        enum_check(
            "suggestion_type",
            ("principle", "aesthetic_concept", "concept_link", "tag", "relationship", "guideline", "knowledge_entry", "color"),
        ),
        enum_check("status", ("pending", "accepted", "rejected", "superseded")),
        Index("ix_ai_suggestions_queue", "organization_id", "brand_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    suggestion_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    source_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    source_analysis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    resolved_entity_type: Mapped[str | None] = mapped_column(String(64))
    resolved_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = created_at_col()


class Review(TenantMixin, Base):
    """Immutable review decision history (analyses, suggestions, knowledge approvals)."""

    __tablename__ = "reviews"
    __table_args__ = (
        same_org_fk("brand_id", "brands"),
        enum_check("decision", ("approved", "rejected", "changes_requested", "accepted", "edited_and_accepted")),
        Index("ix_reviews_subject", "subject_type", "subject_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()


class PromptTemplate(Base):
    """Versioned prompt. organization_id NULL = platform default visible to every tenant."""

    __tablename__ = "prompt_templates"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", "version", postgresql_nulls_not_distinct=True),
        enum_check("purpose", ("analysis", "context", "suggestion", "evaluation")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[dt.datetime] = created_at_col()


class ContextPackage(BrandScoped, Base):
    __tablename__ = "context_packages"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        same_org_fk("brand_id", "brands"),
        same_org_fk("project_id", "projects", nullable_ref=True),
        same_org_fk("brand_version_id", "brand_versions", nullable_ref=True),
        enum_check("mode", ("compact", "standard", "comprehensive")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    brand_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    output_medium: Mapped[str | None] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()


class ExportJob(TenantMixin, Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        enum_check("mode", ("full", "selective")),
        enum_check("status", ("queued", "running", "completed", "failed", "expired")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    brand_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("'{}'"))
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="queued")
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    storage_uri: Mapped[str | None] = mapped_column(String(1000))
    file_count: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    archive_checksum: Mapped[str | None] = mapped_column(String(64))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ImportJob(TenantMixin, Base):
    """Staged import: upload -> validate -> preview -> commit (single transaction) or discard."""

    __tablename__ = "import_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        enum_check(
            "status",
            ("uploaded", "validating", "validated", "invalid", "committing", "committed", "failed", "discarded"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="uploaded")
    staging_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    source_manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    preview: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    id_map: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class Integration(TenantMixin, Base):
    """Per-customer integration: webhook (n8n), MCP client registration, AI provider override."""

    __tablename__ = "integrations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        same_org_fk("brand_id", "brands"),
        enum_check("kind", ("webhook", "mcp_client", "ai_provider", "rest_client")),
        enum_check("status", ("active", "disabled")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    brand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    last_event_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()

