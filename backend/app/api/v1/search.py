"""Search & retrieval endpoints (hybrid, visual, relationship)."""
from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import TenantDep
from app.api.errors import ValidationFailed
from app.media.filetypes import sniff
from app.search.engine import ENTITY_TYPES, SearchRequest, related_entities, search

router = APIRouter(prefix="/search", tags=["search"])


class SearchIn(BaseModel):
    query: str = Field("", max_length=1000)
    brand_id: uuid.UUID | None = None
    entity_types: list[str] = Field(default_factory=lambda: list(ENTITY_TYPES))
    asset_types: list[str] = Field(default_factory=list)
    reference_roles: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    concept_ids: list[uuid.UUID] = Field(default_factory=list)
    principle_ids: list[uuid.UUID] = Field(default_factory=list)
    domain_keys: list[str] = Field(default_factory=list)
    scope: str = Field("all", pattern="^(all|official|pending)$")
    include_historical: bool = True
    limit: int = Field(20, ge=1, le=100)
    explain: bool = False
    parse_query: bool = True


@router.post("")
def search_endpoint(body: SearchIn, tenant: TenantDep) -> dict:
    """Natural-language hybrid search. Example: {"query": "Find approved references with organic geometry"}."""
    tenant.require("search.use")
    bad = [t for t in body.entity_types if t not in ENTITY_TYPES]
    if bad:
        raise ValidationFailed("Unknown entity types", details={"invalid": bad, "allowed": ENTITY_TYPES})
    if tenant.brand_restriction:
        body.brand_id = tenant.brand_restriction
    req = SearchRequest(**body.model_dump())
    return search(tenant.db, tenant.org_id, req)


@router.post("/visual")
def visual_search(
    tenant: TenantDep,
    image: UploadFile | None = File(None),
    asset_id: uuid.UUID | None = Form(None),
    brand_id: uuid.UUID | None = Form(None),
    limit: int = Form(20),
) -> dict:
    """Query-by-example: upload an image, or reference an existing asset."""
    tenant.require("search.use")
    if not image and not asset_id:
        raise ValidationFailed("Provide an image file or an asset_id")
    if tenant.brand_restriction:
        brand_id = tenant.brand_restriction
    req = SearchRequest(brand_id=brand_id, entity_types=["asset"], limit=max(1, min(limit, 100)))
    if asset_id:
        return search(tenant.db, tenant.org_id, req, example_asset_id=asset_id)
    tmp = Path(tempfile.mkdtemp(prefix="bdna-vq-"))
    try:
        p = tmp / "query"
        with p.open("wb") as f:
            shutil.copyfileobj(image.file, f, length=1 << 20)
        kind = sniff(p, image.filename)
        if kind is None or not kind.mime.startswith("image/") or kind.mime == "image/svg+xml":
            raise ValidationFailed("Query image must be a raster image (JPEG, PNG, WebP, TIFF…)")
        return search(tenant.db, tenant.org_id, req, query_image=p)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@router.get("/related")
def related(
    tenant: TenantDep,
    entity_type: str,
    entity_id: uuid.UUID,
    depth: int = Query(1, ge=1, le=3),
    relation_type: list[str] | None = Query(None),
) -> dict:
    """Relationship-based retrieval, e.g. every asset associated with a principle (depth 2 walks via concepts)."""
    tenant.require("search.use", "knowledge.read")
    return {"items": related_entities(tenant.db, entity_type, entity_id, depth, relation_type)}
