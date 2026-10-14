"""Customer-specific exports and validated imports."""
from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.common import row_to_dict
from app.api.deps import TenantDep
from app.api.errors import ApiError, NotFound, ValidationFailed
from app.config import get_settings
from app.jobs.queue import enqueue
from app.models import Brand, ExportJob, ImportJob
from app.storage.backends import TenantStorage

router = APIRouter(tags=["exports"])


class ExportSelection(BaseModel):
    brand_id: uuid.UUID
    domains: list[str] = Field(default_factory=list)
    collection_ids: list[uuid.UUID] = Field(default_factory=list)
    asset_ids: list[uuid.UUID] = Field(default_factory=list)
    project_id: uuid.UUID | None = None
    task_type: str | None = None


class ExportIn(BaseModel):
    mode: str = Field("full", pattern="^(full|selective)$")
    brand_ids: list[uuid.UUID] = Field(default_factory=list, description="full mode: limit to these brands (default: all)")
    selection: ExportSelection | None = None
    include_originals: bool = True
    include_derivatives: bool = True
    include_embeddings: bool = False
    include_ai_knowledge: bool = True
    include_pending: bool | None = None


def _export_out(tenant, e: ExportJob) -> dict[str, Any]:  # noqa: ANN001
    d = row_to_dict(e)
    d["download_available"] = e.status == "completed" and e.storage_uri is not None
    brands = tenant.db.scalars(select(Brand.name).where(Brand.id.in_(e.brand_ids or []))).all() if e.brand_ids else []
    d["brand_names"] = list(brands)
    return d


@router.post("/exports", status_code=202)
def create_export(body: ExportIn, tenant: TenantDep) -> dict:
    tenant.require("export.create")
    if body.mode == "selective" and body.selection is None:
        raise ValidationFailed("selective exports need a selection")
    brand_ids = [body.selection.brand_id] if body.mode == "selective" else body.brand_ids
    for b in brand_ids:
        tenant.check_brand(b)
        if not tenant.db.scalar(select(Brand.id).where(Brand.id == b)):
            raise NotFound("Brand not found")
    if not brand_ids:
        brand_ids = list(tenant.db.scalars(select(Brand.id)))
    if tenant.brand_restriction:
        brand_ids = [b for b in brand_ids if b == tenant.brand_restriction]
    options = body.model_dump(mode="json", exclude={"mode"})
    options["brand_ids"] = [str(b) for b in brand_ids]
    if body.include_pending is None:
        options["include_pending"] = body.mode == "full"
    e = ExportJob(organization_id=tenant.org_id, brand_ids=brand_ids, mode=body.mode, options=options, created_by=tenant.user_id)
    tenant.db.add(e)
    tenant.db.flush()
    job = enqueue(tenant.db, tenant.org_id, "export.build", entity_type="export", entity_id=e.id, created_by=tenant.user_id,
                  priority=80, max_attempts=2)
    e.job_id = job.id
    tenant.audit("export.requested", "export", e.id, {"mode": body.mode, "brands": [str(b) for b in brand_ids]})
    return _export_out(tenant, e)


@router.get("/exports")
def list_exports(tenant: TenantDep) -> dict:
    tenant.require("export.create")
    rows = tenant.db.scalars(select(ExportJob).order_by(ExportJob.created_at.desc()).limit(200)).all()
    return {"items": [_export_out(tenant, e) for e in rows]}


@router.get("/exports/{export_id}")
def get_export(export_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("export.create")
    e = tenant.db.scalar(select(ExportJob).where(ExportJob.id == export_id))
    if e is None:
        raise NotFound("Export not found")
    return _export_out(tenant, e)


@router.get("/exports/{export_id}/download")
def download_export(export_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("export.download")
    e = tenant.db.scalar(select(ExportJob).where(ExportJob.id == export_id))
    if e is None:
        raise NotFound("Export not found")
    if e.status != "completed" or not e.storage_uri:
        raise ValidationFailed(f"Export is {e.status}")
    store = TenantStorage(tenant.org_id)
    tenant.audit("export.downloaded", "export", e.id)
    filename = f"{tenant.org_slug}-library-{e.mode}-{e.created_at:%Y%m%d}.zip"
    return {"url": store.signed_url(store.key_for_uri(e.storage_uri), filename=filename, content_type="application/zip", inline=False),
            "expires_at": store.signed_url_expiry(), "sha256": e.archive_checksum, "size_bytes": e.size_bytes}


# --- Imports -------------------------------------------------------------------------------------
@router.post("/imports", status_code=202)
def upload_import(tenant: TenantDep, file: UploadFile = File(...)) -> dict:
    """Stage an export archive for validation (nothing is written to the library yet)."""
    tenant.require("import.run")
    tmp = Path(tempfile.mkdtemp(prefix="bdna-imp-"))
    try:
        p = tmp / "upload.zip"
        size = 0
        with p.open("wb") as out:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > get_settings().max_upload_bytes * 4:
                    raise ApiError("Archive too large", status_code=413, code="too_large")
                out.write(chunk)
        with p.open("rb") as f:
            if f.read(2) != b"PK":
                raise ValidationFailed("Upload a .zip export archive")
        ij_id = uuid.uuid4()
        store = TenantStorage(tenant.org_id)
        obj = store.put_file(store.import_key(ij_id), p, "application/zip", create_only=True)
        ij = ImportJob(id=ij_id, organization_id=tenant.org_id, staging_uri=obj.uri, created_by=tenant.user_id,
                       options={"filename": file.filename, "size": size})
        tenant.db.add(ij)
        tenant.db.flush()
        job = enqueue(tenant.db, tenant.org_id, "import.validate", entity_type="import", entity_id=ij.id, created_by=tenant.user_id,
                      priority=70, max_attempts=1)
        ij.job_id, ij.status = job.id, "validating"
        tenant.audit("import.uploaded", "import", ij.id, {"filename": file.filename, "size": size})
        return row_to_dict(ij)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@router.get("/imports")
def list_imports(tenant: TenantDep) -> dict:
    tenant.require("import.run")
    return {"items": [row_to_dict(i, {"id_map"}) for i in tenant.db.scalars(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(100))]}


@router.get("/imports/{import_id}")
def get_import(import_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("import.run")
    ij = tenant.db.scalar(select(ImportJob).where(ImportJob.id == import_id))
    if ij is None:
        raise NotFound("Import not found")
    return row_to_dict(ij, {"id_map"})


class CommitIn(BaseModel):
    brand_mapping: dict[str, str] = Field(default_factory=dict, description='source_brand_id -> "create" | "merge:<target_brand_id>"')
    skip_duplicate_assets: bool = True
    import_ai_knowledge: bool = True
    preserve_approvals: bool = True
    regenerate_embeddings: bool = True


@router.post("/imports/{import_id}/commit", status_code=202)
def commit_import(import_id: uuid.UUID, body: CommitIn, tenant: TenantDep) -> dict:
    tenant.require("import.run")
    ij = tenant.db.scalar(select(ImportJob).where(ImportJob.id == import_id))
    if ij is None:
        raise NotFound("Import not found")
    if ij.status != "validated":
        raise ValidationFailed(f"Import must be validated before commit (status: {ij.status})")
    for v in body.brand_mapping.values():
        if v != "create" and not v.startswith("merge:"):
            raise ValidationFailed("brand_mapping values must be 'create' or 'merge:<brand_id>'")
        if v.startswith("merge:"):
            target = uuid.UUID(v.split(":", 1)[1])
            tenant.check_brand(target)
            if not tenant.db.scalar(select(Brand.id).where(Brand.id == target)):
                raise NotFound("Merge target brand not found")
    ij.options = {**(ij.options or {}), **body.model_dump()}
    job = enqueue(tenant.db, tenant.org_id, "import.commit", entity_type="import", entity_id=ij.id, created_by=tenant.user_id,
                  priority=70, max_attempts=1)
    ij.job_id, ij.status = job.id, "committing"
    tenant.audit("import.commit_requested", "import", ij.id, body.model_dump())
    return row_to_dict(ij, {"id_map"})


@router.delete("/imports/{import_id}")
def discard_import(import_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("import.run")
    ij = tenant.db.scalar(select(ImportJob).where(ImportJob.id == import_id))
    if ij is None:
        raise NotFound("Import not found")
    if ij.status in ("committing", "committed"):
        raise ValidationFailed("Committed imports cannot be discarded")
    store = TenantStorage(tenant.org_id)
    store.delete(store.key_for_uri(ij.staging_uri))
    ij.status = "discarded"
    return {"id": str(ij.id), "status": ij.status}
