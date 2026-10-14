"""Creative asset repository: upload, browse/filter, detail, tags, approvals, downloads, bulk ops."""
from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Select, and_, delete, func, or_, select, text
from sqlalchemy.orm import Session

from app.api.common import PageParams, page_params
from app.api.deps import TenantDep
from app.api.errors import NotFound, ValidationFailed
from app.api.v1.brands import get_brand_or_404
from app.jobs.queue import enqueue
from app.models import (
    AiSuggestion,
    Asset,
    AssetAnalysis,
    AssetDerivative,
    AssetTag,
    CollectionAsset,
    Relationship,
)
from app.models.assets import ASSET_TYPES, REFERENCE_ROLES
from app.services import assets as svc
from app.services.events import emit
from app.storage.backends import StorageError, TenantStorage, backend, decode_signed_token

router = APIRouter(tags=["assets"])


def get_asset_or_404(tenant, asset_id: uuid.UUID, include_deleted: bool = False) -> Asset:
    a = tenant.db.scalar(select(Asset).where(Asset.id == asset_id))
    if a is None or (a.deleted_at is not None and not include_deleted):
        raise NotFound("Asset not found")
    tenant.check_brand(a.brand_id)
    return a


def _meta_from_form(**kw: Any) -> dict[str, Any]:
    meta = {k: v for k, v in kw.items() if v not in (None, "")}
    for key in ("tags",):
        if isinstance(meta.get(key), str):
            meta[key] = [t for t in (s.strip() for s in meta[key].split(",")) if t]
    for key in ("license", "curated_metadata"):
        if isinstance(meta.get(key), str):
            try:
                meta[key] = json.loads(meta[key])
            except json.JSONDecodeError as e:
                raise ValidationFailed(f"{key} must be JSON") from e
    if meta.get("asset_type") and meta["asset_type"] not in ASSET_TYPES:
        raise ValidationFailed("invalid asset_type", details={"allowed": ASSET_TYPES})
    if meta.get("reference_role") and meta["reference_role"] not in REFERENCE_ROLES:
        raise ValidationFailed("invalid reference_role", details={"allowed": REFERENCE_ROLES})
    return meta


@router.post("/brands/{brand_id}/assets", status_code=201)
def upload_asset(
    brand_id: uuid.UUID,
    tenant: TenantDep,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    description: str | None = Form(None),
    asset_type: str | None = Form(None),
    category: str | None = Form(None),
    subcategory: str | None = Form(None),
    folder_path: str | None = Form(None),
    reference_role: str | None = Form(None),
    source_type: str | None = Form(None),
    source_url: str | None = Form(None),
    tags: str | None = Form(None, description="comma-separated"),
    license: str | None = Form(None, description="JSON object"),
    curated_metadata: str | None = Form(None, description="JSON object"),
    allow_duplicate: bool = Form(False),
) -> dict:
    tenant.require("assets.write")
    get_brand_or_404(tenant, brand_id)
    meta = _meta_from_form(
        title=title, description=description, asset_type=asset_type, category=category, subcategory=subcategory,
        folder_path=folder_path, reference_role=reference_role, source_type=source_type, source_url=source_url,
        tags=tags, license=license, curated_metadata=curated_metadata,
    )
    a = svc.register_upload(
        tenant.db, org_id=tenant.org_id, brand_id=brand_id, upload=file, meta=meta, created_by=tenant.user_id,
        allow_duplicate=allow_duplicate,
    )
    tenant.audit("asset.uploaded", "asset", a.id, {"filename": a.original_filename, "size": a.file_size, "checksum": a.checksum})
    emit(tenant.db, tenant.org_id, "asset.created", {"asset_id": str(a.id), "brand_id": str(brand_id), "title": a.title})
    return svc.asset_detail(tenant.db, a, tenant.org_id)


@router.post("/assets", status_code=201, summary="Upload an asset (brand_id as form field)")
def upload_asset_flat(
    tenant: TenantDep,
    brand_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    title: str | None = Form(None),
    description: str | None = Form(None),
    asset_type: str | None = Form(None),
    category: str | None = Form(None),
    tags: str | None = Form(None),
    reference_role: str | None = Form(None),
    allow_duplicate: bool = Form(False),
) -> dict:
    return upload_asset(
        brand_id, tenant, file, title, description, asset_type, category, None, None, reference_role, None, None,
        tags, None, None, allow_duplicate,
    )


class ExternalRefIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: str | None = Field(None, max_length=2000)
    description: str | None = None
    source_name: str | None = None
    creator: str | None = None
    license: str | None = None
    notes: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    reference_role: str = Field("external", pattern="^(official|inspiration|historical|external|work_in_progress)$")


@router.post("/brands/{brand_id}/references", status_code=201)
def create_external_reference(brand_id: uuid.UUID, body: ExternalRefIn, tenant: TenantDep) -> dict:
    tenant.require("assets.write")
    get_brand_or_404(tenant, brand_id)
    a = svc.register_external_reference(tenant.db, org_id=tenant.org_id, brand_id=brand_id, data=body.model_dump(), created_by=tenant.user_id)
    tenant.audit("asset.reference_created", "asset", a.id, {"url": body.url})
    return svc.asset_detail(tenant.db, a, tenant.org_id)


# --- Listing / filtering ----------------------------------------------------------------------
def build_asset_query(
    *,
    brand_id: uuid.UUID | None,
    q: str | None,
    asset_types: list[str] | None,
    approval: list[str] | None,
    roles: list[str] | None,
    tags: list[str] | None,
    collection_id: uuid.UUID | None,
    concept_id: uuid.UUID | None,
    principle_id: uuid.UUID | None,
    folder: str | None,
    processing: str | None,
    deleted: bool,
    sort: str,
) -> Select:
    stmt = select(Asset)
    stmt = stmt.where(Asset.deleted_at.is_not(None) if deleted else Asset.deleted_at.is_(None))
    if brand_id:
        stmt = stmt.where(Asset.brand_id == brand_id)
    if asset_types:
        stmt = stmt.where(Asset.asset_type.in_(asset_types))
    if approval:
        stmt = stmt.where(Asset.approval_status.in_(approval))
    if roles:
        stmt = stmt.where(Asset.reference_role.in_(roles))
    if processing:
        stmt = stmt.where(Asset.processing_status == processing)
    if folder:
        stmt = stmt.where(or_(Asset.folder_path == folder, Asset.folder_path.like(folder.rstrip("/") + "/%")))
    for t in tags or []:
        stmt = stmt.where(
            Asset.id.in_(select(AssetTag.asset_id).where(AssetTag.tag == svc.normalize_tag(t), AssetTag.status == "approved"))
        )
    if collection_id:
        stmt = stmt.where(Asset.id.in_(select(CollectionAsset.asset_id).where(CollectionAsset.collection_id == collection_id)))
    for etype, eid in (("aesthetic_concept", concept_id), ("principle", principle_id)):
        if eid:
            stmt = stmt.where(
                Asset.id.in_(
                    select(Relationship.source_id).where(
                        Relationship.source_type == "asset", Relationship.target_type == etype,
                        Relationship.target_id == eid, Relationship.status == "approved",
                    )
                )
            )
    if q:
        tsq = func.bdna_tsq(q)
        stmt = stmt.where(
            or_(
                Asset.search_tsv.op("@@")(tsq),
                Asset.title.ilike(f"%{q}%"),
                Asset.id.in_(select(AssetTag.asset_id).where(AssetTag.tag.ilike(f"%{q.lower()}%"), AssetTag.status == "approved")),
            )
        )
        if sort == "relevance":
            stmt = stmt.order_by(func.ts_rank(Asset.search_tsv, tsq).desc(), Asset.created_at.desc())
    order = {
        "newest": Asset.created_at.desc(),
        "oldest": Asset.created_at.asc(),
        "title": Asset.title.asc(),
        "size": Asset.file_size.desc().nulls_last(),
        "updated": Asset.updated_at.desc(),
    }
    if sort != "relevance" or not q:
        stmt = stmt.order_by(order.get(sort, Asset.created_at.desc()), Asset.id)
    return stmt


@router.get("/assets")
def list_assets(
    tenant: TenantDep,
    params: PageParams = Depends(page_params),
    brand_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=300),
    asset_type: list[str] | None = Query(None),
    approval_status: list[str] | None = Query(None),
    reference_role: list[str] | None = Query(None),
    tag: list[str] | None = Query(None),
    collection_id: uuid.UUID | None = None,
    concept_id: uuid.UUID | None = None,
    principle_id: uuid.UUID | None = None,
    folder: str | None = None,
    processing_status: str | None = None,
    deleted: bool = False,
    sort: str = Query("newest", pattern="^(newest|oldest|title|size|updated|relevance)$"),
) -> dict:
    tenant.require("assets.read")
    if tenant.brand_restriction:
        brand_id = tenant.brand_restriction
    stmt = build_asset_query(
        brand_id=brand_id, q=q, asset_types=asset_type, approval=approval_status, roles=reference_role, tags=tag,
        collection_id=collection_id, concept_id=concept_id, principle_id=principle_id, folder=folder,
        processing=processing_status, deleted=deleted, sort=sort,
    )
    total = tenant.db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = tenant.db.scalars(stmt.limit(params.limit).offset(params.offset)).all()
    facets = _facets(tenant.db, brand_id, deleted)
    return {"items": svc.load_summaries(tenant.db, list(rows), tenant.org_id), "total": total,
            "limit": params.limit, "offset": params.offset, "facets": facets}


def _facets(db: Session, brand_id: uuid.UUID | None, deleted: bool) -> dict[str, Any]:
    base = [Asset.deleted_at.is_not(None) if deleted else Asset.deleted_at.is_(None)]
    if brand_id:
        base.append(Asset.brand_id == brand_id)
    def grp(col):  # noqa: ANN001
        return dict(db.execute(select(col, func.count()).where(*base).group_by(col)).all())
    top_tags = db.execute(
        select(AssetTag.tag, func.count())
        .join(Asset, Asset.id == AssetTag.asset_id)
        .where(*base, AssetTag.status == "approved")
        .group_by(AssetTag.tag)
        .order_by(func.count().desc())
        .limit(40)
    ).all()
    return {
        "asset_type": grp(Asset.asset_type),
        "approval_status": grp(Asset.approval_status),
        "reference_role": grp(Asset.reference_role),
        "processing_status": grp(Asset.processing_status),
        "tags": [{"tag": t, "count": c} for t, c in top_tags],
    }


@router.get("/brands/{brand_id}/folders")
def list_folders(brand_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("assets.read")
    get_brand_or_404(tenant, brand_id)
    rows = tenant.db.execute(
        select(Asset.folder_path, func.count())
        .where(Asset.brand_id == brand_id, Asset.deleted_at.is_(None))
        .group_by(Asset.folder_path)
        .order_by(Asset.folder_path)
    ).all()
    return {"items": [{"path": p, "count": c} for p, c in rows]}


@router.get("/assets/{asset_id}")
def get_asset(asset_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("assets.read")
    a = get_asset_or_404(tenant, asset_id, include_deleted=True)
    out = svc.asset_detail(tenant.db, a, tenant.org_id)
    out["pending_suggestions"] = tenant.db.scalar(
        select(func.count()).select_from(AiSuggestion).where(AiSuggestion.source_asset_id == a.id, AiSuggestion.status == "pending")
    )
    return out


class AssetUpdateIn(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = None
    asset_type: str | None = None
    category: str | None = None
    subcategory: str | None = None
    folder_path: str | None = Field(None, max_length=500)
    reference_role: str | None = Field(None, pattern="^(official|inspiration|historical|external|work_in_progress)$")
    brand_relevance: str | None = Field(None, pattern="^(core|supporting|peripheral|off_brand|unassessed)$")
    source_url: str | None = None
    license: dict[str, Any] | None = None
    curated_metadata: dict[str, Any] | None = None


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: uuid.UUID, body: AssetUpdateIn, tenant: TenantDep) -> dict:
    tenant.require("assets.write")
    a = get_asset_or_404(tenant, asset_id)
    changes = body.model_dump(exclude_unset=True)
    if "asset_type" in changes and changes["asset_type"] not in ASSET_TYPES:
        raise ValidationFailed("invalid asset_type")
    if changes.get("folder_path") and not changes["folder_path"].startswith("/"):
        changes["folder_path"] = "/" + changes["folder_path"]
    for k, v in changes.items():
        setattr(a, k, v)
    tenant.audit("asset.updated", "asset", a.id, {"fields": sorted(changes)})
    enqueue(tenant.db, tenant.org_id, "asset.embed", brand_id=a.brand_id, entity_type="asset", entity_id=a.id, priority=150)
    tenant.db.flush()
    return svc.asset_detail(tenant.db, a, tenant.org_id)


class ApprovalIn(BaseModel):
    status: str = Field(pattern="^(approved|rejected|archived|pending)$")
    notes: str | None = None


@router.post("/assets/{asset_id}/approval")
def set_asset_approval(asset_id: uuid.UUID, body: ApprovalIn, tenant: TenantDep) -> dict:
    tenant.require("review.decide")
    a = get_asset_or_404(tenant, asset_id)
    _set_approval(tenant, a, body.status, body.notes)
    return svc.asset_detail(tenant.db, a, tenant.org_id)


def _set_approval(tenant, a: Asset, status: str, notes: str | None) -> None:
    from app.models import Review

    a.approval_status = status
    a.approved_by = tenant.user_id if status == "approved" else None
    a.approved_at = dt.datetime.now(dt.UTC) if status == "approved" else None
    tenant.db.add(Review(organization_id=tenant.org_id, brand_id=a.brand_id, subject_type="asset", subject_id=a.id,
                         decision="approved" if status == "approved" else "rejected" if status == "rejected" else "changes_requested",
                         notes=notes, reviewer_id=tenant.user_id, changes={"approval_status": status}))
    tenant.audit("asset.approval_changed", "asset", a.id, {"status": status})


# --- Tags ------------------------------------------------------------------------------------
class TagsIn(BaseModel):
    tags: list[str] = Field(min_length=1, max_length=50)


@router.post("/assets/{asset_id}/tags")
def add_tags(asset_id: uuid.UUID, body: TagsIn, tenant: TenantDep) -> dict:
    tenant.require("assets.write")
    a = get_asset_or_404(tenant, asset_id)
    _add_tags(tenant, a, body.tags)
    return {"tags": _tags(tenant.db, a.id)}


def _add_tags(tenant, a: Asset, tags: list[str]) -> None:
    for raw in tags:
        t = svc.normalize_tag(raw)
        if not t:
            continue
        existing = tenant.db.scalar(select(AssetTag).where(AssetTag.asset_id == a.id, AssetTag.tag == t))
        if existing:
            existing.status, existing.source = "approved", existing.source
        else:
            tenant.db.add(AssetTag(organization_id=tenant.org_id, asset_id=a.id, tag=t, source="human", created_by=tenant.user_id))
    tenant.db.flush()
    enqueue(tenant.db, tenant.org_id, "asset.embed", brand_id=a.brand_id, entity_type="asset", entity_id=a.id, priority=150)


def _tags(db: Session, asset_id: uuid.UUID) -> list[dict[str, Any]]:
    return [
        {"tag": t.tag, "source": t.source, "status": t.status, "confidence": float(t.confidence) if t.confidence is not None else None}
        for t in db.scalars(select(AssetTag).where(AssetTag.asset_id == asset_id).order_by(AssetTag.tag))
    ]


@router.post("/assets/{asset_id}/tags/{tag}/{decision}")
def decide_tag(asset_id: uuid.UUID, tag: str, decision: str, tenant: TenantDep) -> dict:
    if decision not in ("accept", "reject"):
        raise NotFound("Unknown action")
    tenant.require("assets.write")
    a = get_asset_or_404(tenant, asset_id)
    t = tenant.db.scalar(select(AssetTag).where(AssetTag.asset_id == a.id, AssetTag.tag == svc.normalize_tag(tag)))
    if t is None:
        raise NotFound("Tag not found")
    t.status = "approved" if decision == "accept" else "rejected"
    tenant.db.flush()
    enqueue(tenant.db, tenant.org_id, "asset.embed", brand_id=a.brand_id, entity_type="asset", entity_id=a.id, priority=150)
    return {"tags": _tags(tenant.db, a.id)}


@router.delete("/assets/{asset_id}/tags/{tag}")
def remove_tag(asset_id: uuid.UUID, tag: str, tenant: TenantDep) -> dict:
    tenant.require("assets.write")
    a = get_asset_or_404(tenant, asset_id)
    tenant.db.execute(delete(AssetTag).where(AssetTag.asset_id == a.id, AssetTag.tag == svc.normalize_tag(tag)))
    return {"tags": _tags(tenant.db, a.id)}


# --- Downloads & files ------------------------------------------------------------------------
@router.get("/assets/{asset_id}/download")
def download_url(
    asset_id: uuid.UUID,
    tenant: TenantDep,
    variant: str = Query("original", pattern="^(original|preview|thumbnail|poster|contact_sheet)$"),
    derivative_id: uuid.UUID | None = None,
) -> dict:
    tenant.require("assets.read")
    a = get_asset_or_404(tenant, asset_id)
    store = TenantStorage(tenant.org_id)
    if derivative_id or variant != "original":
        q = select(AssetDerivative).where(AssetDerivative.asset_id == a.id)
        q = q.where(AssetDerivative.id == derivative_id) if derivative_id else q.where(AssetDerivative.kind == variant)
        d = tenant.db.scalar(q.limit(1))
        if d is None:
            raise NotFound("Derivative not found")
        return {"url": store.signed_url(store.key_for_uri(d.storage_uri), content_type=d.mime_type), "expires_at": store.signed_url_expiry(),
                "mime_type": d.mime_type}
    tenant.require("assets.download_original")
    if not a.storage_uri:
        raise NotFound("This asset has no stored original (external reference)")
    tenant.audit("asset.original_downloaded", "asset", a.id)
    return {
        "url": store.signed_url(store.key_for_uri(a.storage_uri), filename=a.original_filename, content_type=a.mime_type, inline=False),
        "expires_at": store.signed_url_expiry(),
        "mime_type": a.mime_type,
        "checksum_sha256": a.checksum,
    }


files_router = APIRouter(tags=["files"])


@files_router.get("/files/{token}", include_in_schema=False)
def serve_file(token: str):
    """Signed-URL file delivery for the local storage backend (S3 uses presigned URLs instead)."""
    try:
        payload = decode_signed_token(token)
    except (StorageError, ValueError, KeyError) as e:
        raise NotFound("Link expired or invalid") from e
    b = backend()
    key = payload["k"]
    if not hasattr(b, "local_path") or not b.exists(key):
        raise NotFound("File not found")
    path = b.local_path(key)
    disposition = "inline" if payload.get("i") else "attachment"
    headers = {
        "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=600",
    }
    if payload.get("f"):
        from urllib.parse import quote

        headers["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{quote(payload['f'])}"
    return StreamingResponse(b.iter_chunks(key), media_type=payload.get("t") or "application/octet-stream",
                             headers={**headers, "Content-Length": str(path.stat().st_size)})


# --- Lifecycle --------------------------------------------------------------------------------
class ReprocessIn(BaseModel):
    media: bool = True
    ai: bool = True
    embed: bool = True


@router.post("/assets/{asset_id}/reprocess", status_code=202)
def reprocess(asset_id: uuid.UUID, body: ReprocessIn, tenant: TenantDep) -> dict:
    tenant.require("assets.write")
    a = get_asset_or_404(tenant, asset_id)
    job = enqueue(tenant.db, tenant.org_id, "asset.ingest", brand_id=a.brand_id, entity_type="asset", entity_id=a.id,
                  payload=body.model_dump(), created_by=tenant.user_id, priority=60)
    a.processing_status = "pending"
    tenant.audit("asset.reprocess_requested", "asset", a.id, body.model_dump())
    return {"job_id": str(job.id)}


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: uuid.UUID, tenant: TenantDep, grace_days: int = Query(30, ge=0, le=365)) -> dict:
    tenant.require("assets.delete")
    a = get_asset_or_404(tenant, asset_id)
    out = svc.soft_delete(tenant.db, a, tenant.user_id, grace_days)
    tenant.audit("asset.deleted", "asset", a.id, out)
    return out


@router.post("/assets/{asset_id}/restore")
def restore_asset(asset_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("assets.delete")
    a = get_asset_or_404(tenant, asset_id, include_deleted=True)
    a.deleted_at = None
    tenant.audit("asset.restored", "asset", a.id)
    return {"id": str(a.id), "restored": True}


class BulkIn(BaseModel):
    asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(add_tags|remove_tags|set_approval|set_role|move_folder|add_to_collection|remove_from_collection|reprocess|delete)$")
    value: Any = None


@router.post("/assets/bulk")
def bulk(body: BulkIn, tenant: TenantDep) -> dict:
    perm = {"set_approval": "review.decide", "delete": "assets.delete", "add_to_collection": "collections.manage",
            "remove_from_collection": "collections.manage"}.get(body.action, "assets.write")
    tenant.require(perm)
    assets = tenant.db.scalars(select(Asset).where(Asset.id.in_(body.asset_ids), Asset.deleted_at.is_(None))).all()
    if tenant.brand_restriction:
        assets = [a for a in assets if a.brand_id == tenant.brand_restriction]
    done = 0
    for a in assets:
        if body.action == "add_tags":
            _add_tags(tenant, a, list(body.value or []))
        elif body.action == "remove_tags":
            tenant.db.execute(delete(AssetTag).where(AssetTag.asset_id == a.id, AssetTag.tag.in_([svc.normalize_tag(t) for t in body.value or []])))
        elif body.action == "set_approval":
            if body.value not in ("approved", "rejected", "archived", "pending"):
                raise ValidationFailed("invalid approval value")
            _set_approval(tenant, a, body.value, "bulk")
        elif body.action == "set_role":
            if body.value not in REFERENCE_ROLES:
                raise ValidationFailed("invalid reference role")
            a.reference_role = body.value
        elif body.action == "move_folder":
            a.folder_path = "/" + str(body.value or "").strip("/")
        elif body.action in ("add_to_collection", "remove_from_collection"):
            from app.services.collections import add_assets, remove_asset

            cid = uuid.UUID(str(body.value))
            add_assets(tenant, cid, [a.id]) if body.action == "add_to_collection" else remove_asset(tenant, cid, a.id)
        elif body.action == "reprocess":
            enqueue(tenant.db, tenant.org_id, "asset.ingest", brand_id=a.brand_id, entity_type="asset", entity_id=a.id, created_by=tenant.user_id)
        elif body.action == "delete":
            svc.soft_delete(tenant.db, a, tenant.user_id)
        done += 1
    tenant.audit(f"asset.bulk_{body.action}", "asset", None, {"count": done, "value": body.value if not isinstance(body.value, dict) else None})
    return {"updated": done, "requested": len(body.asset_ids)}


@router.get("/assets/{asset_id}/similar")
def similar_assets(asset_id: uuid.UUID, tenant: TenantDep, modality: str = Query("visual", pattern="^(visual|text)$"),
                   limit: int = Query(12, ge=1, le=50)) -> dict:
    tenant.require("assets.read", "search.use")
    a = get_asset_or_404(tenant, asset_id)
    from app.search.engine import similar_to_asset

    return {"items": similar_to_asset(tenant.db, tenant.org_id, a, modality, limit)}


_ = (and_, text, AssetAnalysis)
