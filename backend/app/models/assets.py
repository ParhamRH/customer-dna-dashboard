"""Creative asset repository.

Three deliberately separate layers (never merged into one record):
  * ``Asset``          — the original material + objective technical metadata. Original bytes are immutable.
  * ``AssetAnalysis``  — an AI interpretation of an asset (provider, model, prompt version, confidence).
  * Official knowledge — principles/guidelines/concepts in app.models.brand, linked via ``relationships``.
``Asset.approved_analysis_id`` only *points* at the interpretation a human accepted.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    APPROVAL_STATUSES,
    SCHEMA_VERSION,
    Base,
    TenantMixin,
    created_at_col,
    enum_check,
    same_org_fk,
    updated_at_col,
    uuid_pk,
)
from app.models.brand import BrandScoped, tsv

ASSET_TYPES = (
    "image",
    "photograph",
    "video",
    "animation",
    "render_3d",
    "model_3d",
    "sketch",
    "illustration",
    "graphic_design",
    "logo",
    "document",
    "presentation",
    "text",
    "external_reference",
    "moodboard",
    "audio",
    "other",
)
REFERENCE_ROLES = ("official", "inspiration", "historical", "external", "work_in_progress")
SOURCE_TYPES = ("upload", "external_reference", "import", "generated", "client_supplied", "agency", "stock")
PROCESSING_STATUSES = ("pending", "processing", "processed", "partial", "failed", "skipped")


class Asset(BrandScoped, Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        same_org_fk("brand_id", "brands"),
        same_org_fk("approved_analysis_id", "asset_analyses", nullable_ref=True, use_alter=True),
        enum_check("asset_type", ASSET_TYPES),
        enum_check("approval_status", APPROVAL_STATUSES),
        enum_check("reference_role", REFERENCE_ROLES),
        enum_check("source_type", SOURCE_TYPES),
        enum_check("processing_status", PROCESSING_STATUSES),
        enum_check("brand_relevance", ("core", "supporting", "peripheral", "off_brand", "unassessed")),
        Index("ix_assets_brand_checksum", "brand_id", "checksum"),
        Index("ix_assets_brand_created", "brand_id", "created_at"),
        Index("ix_assets_tsv", "search_tsv", postgresql_using="gin"),
        Index("ix_assets_media_metadata", "media_metadata", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    subcategory: Mapped[str | None] = mapped_column(String(80))
    folder_path: Mapped[str] = mapped_column(String(500), nullable=False, server_default="/")
    original_filename: Mapped[str | None] = mapped_column(String(500))
    storage_uri: Mapped[str | None] = mapped_column(String(1000))  # null for pure external references
    mime_type: Mapped[str | None] = mapped_column(String(160))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(64))  # sha256 hex of the original bytes
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="upload")
    source_url: Mapped[str | None] = mapped_column(String(2000))
    reference_role: Mapped[str] = mapped_column(String(32), nullable=False, server_default="official")
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    brand_relevance: Mapped[str] = mapped_column(String(32), nullable=False, server_default="unassessed")
    license: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Objective, machine-measured technical metadata (dimensions, duration, page count, colors…)
    media_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Human-curated metadata (free-form fields added by editors)
    curated_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    approved_analysis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    processing_error: Mapped[str | None] = mapped_column(Text)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=str(SCHEMA_VERSION))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()
    search_tsv: Mapped[Any] = tsv(
        "coalesce(title,'') || ' ' || coalesce(description,'') || ' ' || coalesce(category,'') || ' ' "
        "|| coalesce(subcategory,'') || ' ' || coalesce(original_filename,'')"
    )


class AssetDerivative(TenantMixin, Base):
    """Generated file derived from an original: thumbnail, preview, keyframe, page render, poster…"""

    __tablename__ = "asset_derivatives"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        same_org_fk("asset_id", "assets"),
        enum_check(
            "kind",
            ("thumbnail", "preview", "poster", "keyframe", "page_render", "extracted_image", "proxy_video", "contact_sheet"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(64))
    page_number: Mapped[int | None] = mapped_column(Integer)
    timestamp_ms: Mapped[int | None] = mapped_column(BigInteger)
    segment_index: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[dt.datetime] = created_at_col()


class AssetSegment(TenantMixin, Base):
    """Time or page segment of an asset: a video scene, a document page/section."""

    __tablename__ = "asset_segments"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("asset_id", "segment_type", "segment_index"),
        same_org_fk("asset_id", "assets"),
        same_org_fk("keyframe_derivative_id", "asset_derivatives", nullable_ref=True),
        enum_check("segment_type", ("scene", "page", "section")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    segment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int | None] = mapped_column(BigInteger)
    end_ms: Mapped[int | None] = mapped_column(BigInteger)
    page_number: Mapped[int | None] = mapped_column(Integer)
    keyframe_derivative_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str | None] = mapped_column(String(300))
    text_content: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[dt.datetime] = created_at_col()


class AssetAnalysis(BrandScoped, Base):
    """One AI interpretation of an asset. Never an official brand rule by itself."""

    __tablename__ = "asset_analyses"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        same_org_fk("brand_id", "brands"),
        same_org_fk("asset_id", "assets"),
        enum_check("status", ("pending_review", "approved", "rejected", "superseded")),
        Index("ix_asset_analyses_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    analysis_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_key: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[int | None] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    objective: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    interpretive: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    raw_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    validation_errors: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    processing_ms: Mapped[int | None] = mapped_column(Integer)
    is_development_adapter: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending_review")
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = created_at_col()


class AssetTag(TenantMixin, Base):
    __tablename__ = "asset_tags"
    __table_args__ = (
        PrimaryKeyConstraint("asset_id", "tag"),
        same_org_fk("asset_id", "assets"),
        same_org_fk("analysis_id", "asset_analyses", nullable_ref=True),
        enum_check("source", ("human", "ai")),
        enum_check("status", ("approved", "suggested", "rejected")),
        Index("ix_asset_tags_org_tag", "organization_id", "tag"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tag: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="human")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="approved")
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()


class Collection(BrandScoped, Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("brand_id", "slug"),
        same_org_fk("brand_id", "brands"),
        same_org_fk("cover_asset_id", "assets", nullable_ref=True),
        enum_check("kind", ("collection", "moodboard", "curated_set", "project_board")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="collection")
    cover_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class CollectionAsset(TenantMixin, Base):
    __tablename__ = "collection_assets"
    __table_args__ = (
        PrimaryKeyConstraint("collection_id", "asset_id"),
        same_org_fk("collection_id", "collections"),
        same_org_fk("asset_id", "assets"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    note: Mapped[str | None] = mapped_column(Text)
    added_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    added_at: Mapped[dt.datetime] = created_at_col()


class ExternalReference(BrandScoped, Base):
    """Provenance record for external inspiration / references (`references` is reserved in SQL)."""

    __tablename__ = "external_references"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        same_org_fk("brand_id", "brands"),
        same_org_fk("asset_id", "assets", nullable_ref=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000))
    source_name: Mapped[str | None] = mapped_column(String(200))
    creator: Mapped[str | None] = mapped_column(String(200))
    license: Mapped[str | None] = mapped_column(String(200))
    accessed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()

