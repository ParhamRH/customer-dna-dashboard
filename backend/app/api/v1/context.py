"""Creative Context Generator endpoints."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ai.prompts import get_prompt
from app.api.common import jsonable, row_to_dict
from app.api.deps import TenantDep
from app.api.errors import NotFound
from app.api.v1.brands import get_brand_or_404
from app.context.generator import ContextRequest, build_package, select_context, to_yaml, to_zip
from app.context.templates import MODE_LIMITS, TEMPLATES
from app.models import ContextPackage

router = APIRouter(prefix="/context", tags=["context"])


class ContextIn(BaseModel):
    brand_id: uuid.UUID
    task_type: str = Field(description="One of GET /v1/context/templates")
    project_id: uuid.UUID | None = None
    output_medium: str | None = Field(None, max_length=120)
    mode: str = Field("standard", pattern="^(compact|standard|comprehensive)$")
    domains: list[str] | None = None
    concept_ids: list[uuid.UUID] = Field(default_factory=list)
    creative_direction: str | None = Field(None, max_length=2000)
    reference_asset_ids: list[uuid.UUID] = Field(default_factory=list)
    collection_ids: list[uuid.UUID] = Field(default_factory=list)
    auto_references: bool = True
    use_published_version: bool = False
    title: str | None = Field(None, max_length=300)


def _req(body: ContextIn) -> ContextRequest:
    return ContextRequest(**body.model_dump())


@router.get("/templates")
def templates(tenant: TenantDep) -> dict:
    tenant.require("knowledge.read")
    return {"templates": [{"key": k, "label": v["label"], "domains": v["domains"], "instructions": v["instructions"],
                           "deliverable_checklist": v["deliverable_checklist"], "prompt_ready": bool(v.get("prompt_ready")),
                           "include_tokens": bool(v.get("include_tokens"))} for k, v in TEMPLATES.items()],
            "modes": MODE_LIMITS}


@router.post("/preview")
def preview(body: ContextIn, tenant: TenantDep) -> dict:
    """What will be included — rules, documents and assets — before anything is generated."""
    tenant.require("knowledge.read", "assets.read")
    get_brand_or_404(tenant, body.brand_id)
    sel = select_context(tenant.db, tenant.org_id, _req(body))
    by_type: dict[str, list[dict]] = {}
    for s in sel["sources"]:
        by_type.setdefault(s["type"], []).append(s)
    return {
        "domains": sel["domains"],
        "counts": {k: len(v) for k, v in by_type.items()},
        "sources": by_type,
        "principles_by_classification": {k: len(v) for k, v in sel["principles"].items()},
        "references": [{"id": r["id"], "title": r["title"], "selected_because": r["selected_because"],
                        "interpretation_status": r["interpretation_status"]} for r in sel["references"]],
        "prohibited_count": len(sel["prohibited"]),
        "brand_version": sel["version"].version_number if sel["version"] else None,
    }


@router.post("/generate", status_code=201)
def generate(body: ContextIn, tenant: TenantDep) -> dict:
    tenant.require("context.generate", "knowledge.read")
    brand = get_brand_or_404(tenant, body.brand_id)
    preamble_tpl = get_prompt(tenant.db, "context_task_preamble")
    tpl = TEMPLATES.get(body.task_type, TEMPLATES["other"])
    preamble = preamble_tpl.render(task_label=tpl["label"], output_medium=body.output_medium or "unspecified medium")
    out = build_package(tenant.db, tenant.org_id, _req(body), preamble,
                        {"key": preamble_tpl.key, "version": preamble_tpl.version})
    pkg = ContextPackage(
        organization_id=tenant.org_id, brand_id=brand.id, project_id=body.project_id, brand_version_id=out["brand_version_id"],
        title=body.title or f"{brand.name} — {tpl['label']} ({body.mode})", task_type=body.task_type,
        output_medium=body.output_medium, mode=body.mode, request=jsonable(body.model_dump()), content=out["content"],
        content_markdown=out["markdown"], sources=out["sources"], token_estimate=out["token_estimate"], checksum=out["checksum"],
        created_by=tenant.user_id,
    )
    tenant.db.add(pkg)
    tenant.db.flush()
    tenant.audit("context.generated", "context_package", pkg.id, {"task": body.task_type, "mode": body.mode, "sources": len(out["sources"])})
    return {**row_to_dict(pkg), "markdown": pkg.content_markdown}


@router.get("/packages")
def list_packages(tenant: TenantDep, brand_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None) -> dict:
    tenant.require("knowledge.read")
    q = select(ContextPackage).order_by(ContextPackage.created_at.desc()).limit(200)
    if brand_id:
        q = q.where(ContextPackage.brand_id == brand_id)
    if project_id:
        q = q.where(ContextPackage.project_id == project_id)
    return {"items": [row_to_dict(p, {"content", "content_markdown", "sources", "request"}) for p in tenant.db.scalars(q)]}


def _pkg(tenant, pid: uuid.UUID) -> ContextPackage:  # noqa: ANN001
    p = tenant.db.scalar(select(ContextPackage).where(ContextPackage.id == pid))
    if p is None:
        raise NotFound("Context package not found")
    tenant.check_brand(p.brand_id)
    return p


@router.get("/packages/{package_id}")
def get_package(package_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("knowledge.read")
    p = _pkg(tenant, package_id)
    return {**row_to_dict(p), "markdown": p.content_markdown}


@router.get("/packages/{package_id}/download")
def download_package(package_id: uuid.UUID, tenant: TenantDep, format: str = Query("md", pattern="^(md|json|yaml|zip)$"),
                     include_media: bool = True):
    tenant.require("knowledge.read")
    p = _pkg(tenant, package_id)
    name = f"context-{p.task_type}-{str(p.id)[:8]}"
    if format == "md":
        return PlainTextResponse(p.content_markdown, media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="{name}.md"'})
    if format == "yaml":
        return PlainTextResponse(to_yaml(p.content), media_type="application/yaml",
                                 headers={"Content-Disposition": f'attachment; filename="{name}.yaml"'})
    if format == "json":
        return Response(json.dumps(p.content, indent=2, ensure_ascii=False), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{name}.json"'})
    if include_media:
        tenant.require("assets.read")
    data = to_zip(tenant.db, tenant.org_id, p, include_media)
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})
