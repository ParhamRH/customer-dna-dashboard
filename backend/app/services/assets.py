"""Asset registration (upload → validate → checksum → dedupe → immutable storage → queue)."""
from __future__ import annotations

import datetime as dt
import hashlib
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import jsonable
from app.api.errors import ApiError, Conflict, ValidationFailed
from app.config import get_settings
from app.jobs.queue import enqueue
from app.media.filetypes import ALLOWED_FAMILIES, safe_filename, sniff
from app.models import (
    Asset,
    AssetAnalysis,
    AssetDerivative,
    AssetSegment,
    AssetTag,
    Collection,
    CollectionAsset,
    ExternalReference,
    Organization,
    Relationship,
)
from app.models.assets import ASSET_TYPES
from app.storage.backends import ObjectExists, TenantStorage

PREVIEW_KINDS = ("thumbnail", "preview", "poster")


class UnsupportedMedia(ApiError):
    status_code = 415
    code = "unsupported_media_type"


def _spool(upload: UploadFile, max_bytes: int) -> tuple[Path, int, str]:
    tmpdir = Path(tempfile.mkdtemp(prefix="bdna-upload-"))
    path = tmpdir / "upload.bin"
    h = hashlib.sha256()
    size = 0
    with path.open("wb") as out:
        while chunk := upload.file.read(1 << 20):
            size += len(chunk)
            if size > max_bytes:
                shutil.rmtree(tmpdir, ignore_errors=True)
                raise ApiError(f"File exceeds the {max_bytes // (1024 * 1024)} MiB limit", status_code=413, code="too_large")
            h.update(chunk)
            out.write(chunk)
    if size == 0:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ValidationFailed("Empty file")
    return path, size, h.hexdigest()


def _check_quota(db: Session, org_id: uuid.UUID, incoming: int) -> None:
    quota = db.scalar(select(Organization.storage_quota_bytes).where(Organization.id == org_id))
    if quota:
        used = (db.scalar(select(func.coalesce(func.sum(Asset.file_size), 0))) or 0) + (
            db.scalar(select(func.coalesce(func.sum(AssetDerivative.file_size), 0))) or 0
        )
        if used + incoming > quota:
            raise ApiError("Storage quota exceeded for this customer", status_code=507, code="quota_exceeded")


def find_duplicate(db: Session, brand_id: uuid.UUID, checksum: str) -> Asset | None:
    return db.scalar(
        select(Asset).where(Asset.brand_id == brand_id, Asset.checksum == checksum, Asset.deleted_at.is_(None)).limit(1)
    )


def register_file(
    db: Session,
    *,
    org_id: uuid.UUID,
    brand_id: uuid.UUID,
    path: Path,
    size: int,
    checksum: str,
    original_filename: str,
    meta: dict[str, Any],
    created_by: uuid.UUID | None,
    allow_duplicate: bool = False,
    asset_id: uuid.UUID | None = None,
    enqueue_ingest: bool = True,
    extra_fields: dict[str, Any] | None = None,
) -> Asset:
    """Register an already-spooled local file as a new asset. Used by upload, import and seeding."""
    kind = sniff(path, original_filename)
    if kind is None or kind.family not in ALLOWED_FAMILIES:
        raise UnsupportedMedia(
            "Unsupported or unrecognised file type", details={"filename": original_filename}
        )
    if not allow_duplicate:
        dup = find_duplicate(db, brand_id, checksum)
        if dup:
            raise Conflict(
                "This file already exists in the brand library",
                details={"existing_asset_id": str(dup.id), "title": dup.title},
                code="duplicate_asset",
            )
    _check_quota(db, org_id, size)
    asset_type = meta.get("asset_type") or kind.asset_type
    if asset_type not in ASSET_TYPES:
        raise ValidationFailed(f"Unknown asset_type {asset_type!r}")
    asset_id = asset_id or uuid.uuid4()
    filename = safe_filename(original_filename)
    store = TenantStorage(org_id)
    key = store.original_key(brand_id, asset_id, filename)
    try:
        stored = store.put_file(key, path, kind.mime, create_only=True)
    except ObjectExists as e:
        raise Conflict("Original object already exists (immutable)") from e
    if stored.sha256 != checksum:
        store.delete(key)
        raise ApiError("Checksum mismatch after storage write", status_code=500, code="integrity_error")
    asset = Asset(
        id=asset_id,
        organization_id=org_id,
        brand_id=brand_id,
        title=(meta.get("title") or Path(original_filename).stem.replace("_", " ").replace("-", " ").strip() or filename)[:300],
        description=meta.get("description"),
        asset_type=asset_type,
        category=meta.get("category"),
        subcategory=meta.get("subcategory"),
        folder_path=meta.get("folder_path") or "/",
        original_filename=filename,
        storage_uri=stored.uri,
        mime_type=kind.mime,
        file_size=size,
        checksum=checksum,
        source_type=meta.get("source_type") or "upload",
        source_url=meta.get("source_url"),
        reference_role=meta.get("reference_role") or "official",
        license=meta.get("license") or {},
        curated_metadata=meta.get("curated_metadata") or {},
        created_by=created_by,
        **(extra_fields or {}),
    )
    try:
        db.add(asset)
        db.flush()
    except Exception:
        store.delete(key)  # compensate: do not leave an orphaned original
        raise
    for tag in meta.get("tags") or []:
        db.add(AssetTag(organization_id=org_id, asset_id=asset.id, tag=normalize_tag(tag), source="human", created_by=created_by))
    if enqueue_ingest:
        enqueue(db, org_id, "asset.ingest", brand_id=brand_id, entity_type="asset", entity_id=asset.id,
                created_by=created_by, priority=50)
    return asset


def register_upload(db: Session, *, org_id, brand_id, upload: UploadFile, meta, created_by, allow_duplicate=False) -> Asset:
    path, size, checksum = _spool(upload, get_settings().max_upload_bytes)
    try:
        return register_file(
            db, org_id=org_id, brand_id=brand_id, path=path, size=size, checksum=checksum,
            original_filename=upload.filename or "upload", meta=meta, created_by=created_by,
            allow_duplicate=allow_duplicate,
        )
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


def register_external_reference(db: Session, *, org_id, brand_id, data: dict[str, Any], created_by) -> Asset:
    """External inspiration without a file (provenance-only); a capture can be uploaded later."""
    asset = Asset(
        organization_id=org_id,
        brand_id=brand_id,
        title=data["title"],
        description=data.get("description"),
        asset_type="external_reference",
        category=data.get("category"),
        source_type="external_reference",
        source_url=data.get("url"),
        reference_role=data.get("reference_role") or "external",
        license={"license": data.get("license")} if data.get("license") else {},
        processing_status="skipped",
        created_by=created_by,
    )
    db.add(asset)
    db.flush()
    db.add(
        ExternalReference(
            organization_id=org_id,
            brand_id=brand_id,
            asset_id=asset.id,
            title=data["title"],
            url=data.get("url"),
            source_name=data.get("source_name"),
            creator=data.get("creator"),
            license=data.get("license"),
            accessed_at=dt.datetime.now(dt.UTC),
            notes=data.get("notes"),
            provenance={"recorded_by": str(created_by) if created_by else None, "method": "manual"},
            created_by=created_by,
        )
    )
    for tag in data.get("tags") or []:
        db.add(AssetTag(organization_id=org_id, asset_id=asset.id, tag=normalize_tag(tag), source="human", created_by=created_by))
    enqueue(db, org_id, "asset.embed", brand_id=brand_id, entity_type="asset", entity_id=asset.id, created_by=created_by)
    return asset


def normalize_tag(tag: str) -> str:
    return " ".join(tag.strip().lower().split())[:80]


# --- Serialization ---------------------------------------------------------------------------
def derivative_urls(store: TenantStorage, derivs: list[AssetDerivative]) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in derivs:
        if d.kind in PREVIEW_KINDS and d.kind not in out:
            out[d.kind] = store.signed_url(store.key_for_uri(d.storage_uri), content_type=d.mime_type)
    return out


def asset_summary(a: Asset, store: TenantStorage, derivs: list[AssetDerivative], tags: list[str]) -> dict[str, Any]:
    urls = derivative_urls(store, derivs)
    return {
        "id": str(a.id),
        "organization_id": str(a.organization_id),
        "brand_id": str(a.brand_id),
        "title": a.title,
        "description": a.description,
        "asset_type": a.asset_type,
        "category": a.category,
        "subcategory": a.subcategory,
        "folder_path": a.folder_path,
        "mime_type": a.mime_type,
        "file_size": a.file_size,
        "original_filename": a.original_filename,
        "approval_status": a.approval_status,
        "reference_role": a.reference_role,
        "brand_relevance": a.brand_relevance,
        "processing_status": a.processing_status,
        "source_type": a.source_type,
        "source_url": a.source_url,
        "tags": tags,
        "thumbnail_url": urls.get("thumbnail"),
        "preview_url": urls.get("preview") or urls.get("poster"),
        "width": (a.media_metadata or {}).get("width"),
        "height": (a.media_metadata or {}).get("height"),
        "duration_seconds": (a.media_metadata or {}).get("duration_seconds"),
        "dominant_colors": [c.get("hex") for c in (a.media_metadata or {}).get("palette", [])[:5]],
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def load_summaries(db: Session, assets: list[Asset], org_id: uuid.UUID) -> list[dict[str, Any]]:
    if not assets:
        return []
    ids = [a.id for a in assets]
    derivs: dict[uuid.UUID, list[AssetDerivative]] = {}
    for d in db.scalars(
        select(AssetDerivative).where(AssetDerivative.asset_id.in_(ids), AssetDerivative.kind.in_(PREVIEW_KINDS))
    ):
        derivs.setdefault(d.asset_id, []).append(d)
    tags: dict[uuid.UUID, list[str]] = {}
    for t in db.scalars(select(AssetTag).where(AssetTag.asset_id.in_(ids), AssetTag.status == "approved").order_by(AssetTag.tag)):
        tags.setdefault(t.asset_id, []).append(t.tag)
    store = TenantStorage(org_id)
    return [asset_summary(a, store, derivs.get(a.id, []), tags.get(a.id, [])) for a in assets]


def asset_detail(db: Session, a: Asset, org_id: uuid.UUID) -> dict[str, Any]:
    store = TenantStorage(org_id)
    derivs = db.scalars(
        select(AssetDerivative).where(AssetDerivative.asset_id == a.id).order_by(AssetDerivative.kind, AssetDerivative.page_number, AssetDerivative.timestamp_ms)
    ).all()
    out = asset_summary(a, store, list(derivs), [])
    tags = db.scalars(select(AssetTag).where(AssetTag.asset_id == a.id).order_by(AssetTag.tag)).all()
    out["tags"] = [t.tag for t in tags if t.status == "approved"]
    out["tag_details"] = [
        {"tag": t.tag, "source": t.source, "status": t.status, "confidence": jsonable(t.confidence)} for t in tags
    ]
    out["checksum"] = a.checksum
    out["schema_version"] = a.schema_version
    out["license"] = a.license
    out["media_metadata"] = a.media_metadata
    out["curated_metadata"] = a.curated_metadata
    out["processing_error"] = a.processing_error
    out["approved_analysis_id"] = jsonable(a.approved_analysis_id)
    out["approved_by"] = jsonable(a.approved_by)
    out["approved_at"] = jsonable(a.approved_at)
    out["deleted_at"] = jsonable(a.deleted_at)
    out["derivatives"] = [
        {
            "id": str(d.id),
            "kind": d.kind,
            "mime_type": d.mime_type,
            "width": d.width,
            "height": d.height,
            "file_size": d.file_size,
            "page_number": d.page_number,
            "timestamp_ms": d.timestamp_ms,
            "segment_index": d.segment_index,
            "url": store.signed_url(store.key_for_uri(d.storage_uri), content_type=d.mime_type),
        }
        for d in derivs
    ]
    out["segments"] = [
        {
            "id": str(s.id),
            "segment_type": s.segment_type,
            "index": s.segment_index,
            "start_ms": s.start_ms,
            "end_ms": s.end_ms,
            "page_number": s.page_number,
            "title": s.title,
            "text_excerpt": (s.text_content or "")[:600],
            "keyframe_derivative_id": jsonable(s.keyframe_derivative_id),
            "meta": s.meta,
        }
        for s in db.scalars(
            select(AssetSegment).where(AssetSegment.asset_id == a.id).order_by(AssetSegment.segment_type, AssetSegment.segment_index)
        )
    ]
    out["analyses"] = [
        {
            "id": str(x.id),
            "analysis_type": x.analysis_type,
            "provider": x.provider,
            "model": x.model,
            "prompt_key": x.prompt_key,
            "prompt_version": x.prompt_version,
            "schema_version": x.schema_version,
            "status": x.status,
            "confidence": jsonable(x.confidence),
            "processing_ms": x.processing_ms,
            "is_development_adapter": x.is_development_adapter,
            "objective": x.objective,
            "interpretive": x.interpretive,
            "validation_errors": x.validation_errors,
            "reviewed_by": jsonable(x.reviewed_by),
            "reviewed_at": jsonable(x.reviewed_at),
            "review_notes": x.review_notes,
            "created_at": x.created_at.isoformat(),
        }
        for x in db.scalars(select(AssetAnalysis).where(AssetAnalysis.asset_id == a.id).order_by(AssetAnalysis.created_at.desc()))
    ]
    out["collections"] = [
        {"id": str(c.id), "name": c.name, "slug": c.slug}
        for c in db.scalars(
            select(Collection).join(CollectionAsset, CollectionAsset.collection_id == Collection.id).where(CollectionAsset.asset_id == a.id)
        )
    ]
    out["references"] = [
        {
            "id": str(r.id),
            "title": r.title,
            "url": r.url,
            "source_name": r.source_name,
            "creator": r.creator,
            "license": r.license,
            "accessed_at": jsonable(r.accessed_at),
            "notes": r.notes,
            "provenance": r.provenance,
        }
        for r in db.scalars(select(ExternalReference).where(ExternalReference.asset_id == a.id))
    ]
    from app.services.graph import entity_relationships

    out["relationships"] = entity_relationships(db, "asset", a.id)
    out["original_download_available"] = a.storage_uri is not None
    return out


def soft_delete(db: Session, a: Asset, user_id: uuid.UUID | None, grace_days: int = 30) -> dict[str, Any]:
    now = dt.datetime.now(dt.UTC)
    a.deleted_at = now
    purge_at = now + dt.timedelta(days=grace_days)
    enqueue(db, a.organization_id, "asset.purge", brand_id=a.brand_id, entity_type="asset", entity_id=a.id,
            run_after=purge_at, created_by=user_id)
    return {"id": str(a.id), "deleted_at": now.isoformat(), "purge_at": purge_at.isoformat()}


_ = Relationship
