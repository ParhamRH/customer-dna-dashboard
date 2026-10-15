"""Job handlers. Each runs inside a tenant (RLS) session for the job's organization, except
``organization.purge`` which by nature operates on a whole tenant via the privileged role."""
from __future__ import annotations

import json
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from app.db.session import system_session
from app.jobs.queue import JobContext, PermanentJobError, handler
from app.models import Asset, AssetDerivative, AuditLog, Organization
from app.services import embeddings as emb
from app.services import ingest
from app.storage.backends import TenantStorage, backend


@handler("asset.ingest")
def asset_ingest(ctx: JobContext) -> dict[str, Any]:
    p = ctx.job.payload or {}
    return ingest.ingest(ctx, do_media=p.get("media", True), do_ai=p.get("ai", True), do_embed=p.get("embed", True))

@handler("asset.embed")
def asset_embed(ctx: JobContext) -> dict[str, Any]:
    """Re-embed an asset from its stored derivatives (no media reprocessing, no AI calls)."""
    store = TenantStorage(ctx.org_id)
    with ctx.session() as db:
        a = db.scalar(select(Asset).where(Asset.id == ctx.job.entity_id))
        if a is None:
            raise PermanentJobError("asset not found")
        out = {"text": emb.reindex_text(db, "asset", a.id), "visual": 0}
        derivs = db.scalars(
            select(AssetDerivative).where(AssetDerivative.asset_id == a.id, AssetDerivative.kind.in_(["preview", "keyframe"]))
        ).all()
        if derivs:
            with tempfile.TemporaryDirectory() as d:
                imgs = []
                for i, dv in enumerate(derivs[:24]):
                    path = Path(d) / f"{i}.img"
                    store.download_to(store.key_for_uri(dv.storage_uri), path)
                    imgs.append((i, path, dv.kind))
                out["visual"] = emb.embed_images(db, org_id=a.organization_id, brand_id=a.brand_id, entity_type="asset", entity_id=a.id, images=imgs)
        return out

@handler("knowledge.embed")
def knowledge_embed(ctx: JobContext) -> dict[str, Any]:
    with ctx.session() as db:
        return {"embedded": emb.reindex_text(db, ctx.job.entity_type, ctx.job.entity_id)}

@handler("brand.reindex")
def brand_reindex(ctx: JobContext) -> dict[str, Any]:
    """Regenerate every text embedding of a brand (e.g. after switching embedding model or on import)."""
    from app.models import AestheticConcept, Collection, Guideline, KnowledgeEntry, Principle, Project

    brand_id = ctx.job.brand_id
    counts: dict[str, int] = {}
    with ctx.session() as db:
        for etype, model in (
            ("principle", Principle), ("guideline", Guideline), ("aesthetic_concept", AestheticConcept),
            ("knowledge_entry", KnowledgeEntry), ("project", Project), ("collection", Collection),
        ):
            ids = db.scalars(select(model.id).where(model.brand_id == brand_id)).all()
            counts[etype] = sum(emb.reindex_text(db, etype, i) for i in ids)
        asset_ids = db.scalars(select(Asset.id).where(Asset.brand_id == brand_id, Asset.deleted_at.is_(None))).all()
    from app.jobs.queue import enqueue

    with ctx.session() as db:
        for aid in asset_ids:
            enqueue(db, ctx.org_id, "asset.embed", brand_id=brand_id, entity_type="asset", entity_id=aid, priority=150)
    counts["assets_queued"] = len(asset_ids)
    return counts

@handler("asset.purge")
def asset_purge(ctx: JobContext) -> dict[str, Any]:
    """Retention workflow: permanently remove a soft-deleted asset (original + derivatives)."""
    store = TenantStorage(ctx.org_id)
    with ctx.session() as db:
        a = db.scalar(select(Asset).where(Asset.id == ctx.job.entity_id))
        if a is None:
            return {"skipped": "already removed"}
        if a.deleted_at is None:
            return {"skipped": "asset was restored"}
        n = store.delete_prefix(store.asset_prefix(a.brand_id, a.id))
        db.execute(delete(Asset).where(Asset.id == a.id))

        db.add(AuditLog(organization_id=ctx.org_id, actor_type="system", action="asset.purged",
                        entity_type="asset", entity_id=str(ctx.job.entity_id), details={"objects_deleted": n}))
        return {"objects_deleted": n}

@handler("organization.purge")
def organization_purge(ctx: JobContext) -> dict[str, Any]:
    org_id = ctx.org_id
    with system_session() as s:
        org = s.scalar(select(Organization).where(Organization.id == org_id))
        if org is None:
            return {"skipped": "already purged"}
        if org.status != "pending_deletion":
            return {"skipped": f"organization status is {org.status}"}
        slug = org.slug
    n = backend().delete_prefix(f"orgs/{org_id}/")
    with system_session() as s:
        s.execute(delete(Organization).where(Organization.id == org_id))  # cascades every tenant row
        s.add(AuditLog(organization_id=None, actor_type="system", action="organization.purged",
                       entity_type="organization", entity_id=str(org_id), details={"slug": slug, "objects_deleted": n}))
    return {"objects_deleted": n}

@handler("webhook.deliver")
def webhook_deliver(ctx: JobContext) -> dict[str, Any]:
    from app.services.events import deliver

    with ctx.session() as db:
        return deliver(db, ctx.job.payload)

@handler("noop")
def noop(ctx: JobContext) -> dict[str, Any]:
    time.sleep(float((ctx.job.payload or {}).get("sleep", 0)))
    if (ctx.job.payload or {}).get("fail"):
        raise RuntimeError("requested failure")
    return {"ok": True, "id": str(uuid.uuid4())}


# --- Exports / imports ---------------------------------------------------------------------------
@handler("export.build")
def export_build(ctx: JobContext) -> dict[str, Any]:
    import datetime as dt
    import hashlib
    import shutil

    from app.config import get_settings
    from app.exports.exporter import ExportError, build_export
    from app.models import ExportJob
    from app.services.events import emit

    store = TenantStorage(ctx.org_id)
    with ctx.session() as db:
        ej = db.scalar(select(ExportJob).where(ExportJob.id == ctx.job.entity_id))
        if ej is None:
            raise PermanentJobError("export job not found")
        ej.status = "running"
        mode, options = ej.mode, dict(ej.options or {})
    try:
        with ctx.session() as db:
            archive, manifest = build_export(db, ctx.org_id, ctx.job.entity_id, mode, options, options.get("selection") or {})
    except ExportError as e:
        with ctx.session() as db:
            ej = db.scalar(select(ExportJob).where(ExportJob.id == ctx.job.entity_id))
            ej.status, ej.error = "failed", str(e)
        raise PermanentJobError(str(e)) from e
    try:
        h = hashlib.sha256()
        with archive.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        obj = store.put_file(store.export_key(ctx.job.entity_id), archive, "application/zip")
        with ctx.session() as db:
            ej = db.scalar(select(ExportJob).where(ExportJob.id == ctx.job.entity_id))
            ej.status, ej.storage_uri, ej.size_bytes = "completed", obj.uri, obj.size
            ej.archive_checksum, ej.file_count = h.hexdigest(), manifest["file_count"]
            ej.manifest = {k: v for k, v in manifest.items() if k != "checksums"}
            ej.completed_at = dt.datetime.now(dt.UTC)
            ej.expires_at = ej.completed_at + dt.timedelta(days=get_settings().export_ttl_days)
            db.add(AuditLog(organization_id=ctx.org_id, actor_type="system", action="export.completed", entity_type="export",
                            entity_id=str(ej.id), details={"size": obj.size, "files": manifest["file_count"], "mode": mode}))
            emit(db, ctx.org_id, "export.completed", {"export_id": str(ej.id), "size_bytes": obj.size})
        return {"size_bytes": obj.size, "file_count": manifest["file_count"], "counts": manifest["counts"]}
    finally:
        shutil.rmtree(archive.parent, ignore_errors=True)


def _import_stage(ctx: JobContext):
    from app.exports import importer
    from app.models import ImportJob

    store = TenantStorage(ctx.org_id)
    with ctx.session() as db:
        ij = db.scalar(select(ImportJob).where(ImportJob.id == ctx.job.entity_id))
        if ij is None:
            raise PermanentJobError("import job not found")
        key = store.key_for_uri(ij.staging_uri)
    work = importer.stage_dir()
    zpath = work / "import.zip"
    store.download_to(key, zpath)
    return importer, work, importer.safe_extract(zpath, work / "x")


@handler("import.validate")
def import_validate(ctx: JobContext) -> dict[str, Any]:
    from app.exports.importer import ImportErrorReport
    from app.models import ImportJob

    try:
        importer, work, root = _import_stage(ctx)
    except ImportErrorReport as e:
        with ctx.session() as db:
            ij = db.scalar(select(ImportJob).where(ImportJob.id == ctx.job.entity_id))
            ij.status, ij.report = "invalid", {"errors": e.errors}
        return {"valid": False}
    try:
        with ctx.session() as db:
            try:
                preview = importer.validate(db, root)
            except ImportErrorReport as e:
                preview = {"errors": e.errors, "warnings": []}
            ij = db.scalar(select(ImportJob).where(ImportJob.id == ctx.job.entity_id))
            ij.preview = preview
            ij.source_manifest = {k: v for k, v in (json.loads((root / "manifest.json").read_text()) if (root / "manifest.json").exists() else {}).items() if k != "checksums"}
            ij.status = "invalid" if preview.get("errors") else "validated"
            ij.report = {"errors": preview.get("errors", []), "warnings": preview.get("warnings", [])}
        return {"valid": not preview.get("errors")}
    finally:
        importer.cleanup(work)


@handler("import.commit")
def import_commit(ctx: JobContext) -> dict[str, Any]:
    from app.exports.importer import ImportErrorReport
    from app.jobs.queue import enqueue
    from app.models import ImportJob
    from app.services.events import emit

    importer, work, root = _import_stage(ctx)
    try:
        with ctx.session() as db:
            ij = db.scalar(select(ImportJob).where(ImportJob.id == ctx.job.entity_id))
            options = dict(ij.options or {})
            ij.status = "committing"
        try:
            with ctx.session() as db:  # ONE transaction for the whole import
                out = importer.commit(db, ctx.org_id, root, options, ctx.job.created_by)
                ij = db.scalar(select(ImportJob).where(ImportJob.id == ctx.job.entity_id))
                ij.status, ij.report, ij.id_map = "committed", out["report"], out["id_map"]
                db.add(AuditLog(organization_id=ctx.org_id, actor_type="system", action="import.committed", entity_type="import",
                                entity_id=str(ij.id), details={"created": out["report"]["created"]}))
                emit(db, ctx.org_id, "import.committed", {"import_id": str(ij.id), "created": out["report"]["created"]})
                if options.get("regenerate_embeddings", True):
                    for b in out["report"]["target_brand_ids"]:
                        enqueue(db, ctx.org_id, "brand.reindex", brand_id=uuid.UUID(b), entity_type="brand", entity_id=uuid.UUID(b),
                                created_by=ctx.job.created_by, priority=140)
            return out["report"]
        except Exception as e:
            errors = e.errors if isinstance(e, ImportErrorReport) else [f"{type(e).__name__}: {e}"]
            with ctx.session() as db:
                ij = db.scalar(select(ImportJob).where(ImportJob.id == ctx.job.entity_id))
                ij.status, ij.report = "failed", {"errors": errors, "rolled_back": True}
            raise PermanentJobError("; ".join(errors)[:2000]) from e
    finally:
        importer.cleanup(work)
