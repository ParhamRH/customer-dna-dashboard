from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.common import row_to_dict, slugify
from app.api.deps import TenantDep
from app.api.errors import Conflict
from app.api.v1.brands import get_brand_or_404
from app.jobs.queue import enqueue
from app.models import Asset, Collection, CollectionAsset
from app.services import assets as asset_svc
from app.services.collections import add_assets, get_collection, remove_asset, reorder

router = APIRouter(tags=["collections"])


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    kind: str = Field("collection", pattern="^(collection|moodboard|curated_set|project_board)$")
    asset_ids: list[uuid.UUID] = Field(default_factory=list)


def _out(tenant, c: Collection, with_assets: bool = False) -> dict:  # noqa: ANN001
    d = row_to_dict(c)
    d["asset_count"] = tenant.db.scalar(select(func.count()).select_from(CollectionAsset).where(CollectionAsset.collection_id == c.id))
    cover = None
    if c.cover_asset_id:
        a = tenant.db.scalar(select(Asset).where(Asset.id == c.cover_asset_id))
        if a:
            cover = asset_svc.load_summaries(tenant.db, [a], tenant.org_id)[0]
    d["cover"] = cover
    if with_assets:
        rows = tenant.db.execute(
            select(Asset, CollectionAsset.note)
            .join(CollectionAsset, CollectionAsset.asset_id == Asset.id)
            .where(CollectionAsset.collection_id == c.id, Asset.deleted_at.is_(None))
            .order_by(CollectionAsset.position)
        ).all()
        items = asset_svc.load_summaries(tenant.db, [a for a, _ in rows], tenant.org_id)
        for item, (_, note) in zip(items, rows, strict=True):
            item["collection_note"] = note
        d["assets"] = items
    return d


@router.get("/brands/{brand_id}/collections")
def list_collections(brand_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("assets.read")
    get_brand_or_404(tenant, brand_id)
    rows = tenant.db.scalars(select(Collection).where(Collection.brand_id == brand_id).order_by(Collection.name)).all()
    return {"items": [_out(tenant, c) for c in rows]}


@router.post("/brands/{brand_id}/collections", status_code=201)
def create_collection(brand_id: uuid.UUID, body: CollectionIn, tenant: TenantDep) -> dict:
    tenant.require("collections.manage")
    get_brand_or_404(tenant, brand_id)
    slug = slugify(body.name, 120)
    if tenant.db.scalar(select(Collection.id).where(Collection.brand_id == brand_id, Collection.slug == slug)):
        raise Conflict("A collection with this name already exists")
    c = Collection(organization_id=tenant.org_id, brand_id=brand_id, name=body.name, slug=slug,
                   description=body.description, kind=body.kind, created_by=tenant.user_id)
    tenant.db.add(c)
    tenant.db.flush()
    if body.asset_ids:
        add_assets(tenant, c.id, body.asset_ids)
    enqueue(tenant.db, tenant.org_id, "knowledge.embed", brand_id=brand_id, entity_type="collection", entity_id=c.id, priority=150)
    tenant.audit("collection.created", "collection", c.id, {"name": c.name})
    return _out(tenant, c, True)


@router.get("/collections/{collection_id}")
def get_collection_detail(collection_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("assets.read")
    return _out(tenant, get_collection(tenant, collection_id), True)


class CollectionUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    kind: str | None = Field(None, pattern="^(collection|moodboard|curated_set|project_board)$")
    cover_asset_id: uuid.UUID | None = None


@router.patch("/collections/{collection_id}")
def update_collection(collection_id: uuid.UUID, body: CollectionUpdateIn, tenant: TenantDep) -> dict:
    tenant.require("collections.manage")
    c = get_collection(tenant, collection_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    enqueue(tenant.db, tenant.org_id, "knowledge.embed", brand_id=c.brand_id, entity_type="collection", entity_id=c.id, priority=150)
    tenant.db.flush()
    return _out(tenant, c, True)


@router.delete("/collections/{collection_id}", status_code=204)
def delete_collection(collection_id: uuid.UUID, tenant: TenantDep) -> None:
    tenant.require("collections.manage")
    c = get_collection(tenant, collection_id)
    tenant.audit("collection.deleted", "collection", c.id, {"name": c.name})
    tenant.db.delete(c)


class AssetsIn(BaseModel):
    asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    note: str | None = None


@router.post("/collections/{collection_id}/assets")
def add_to_collection(collection_id: uuid.UUID, body: AssetsIn, tenant: TenantDep) -> dict:
    tenant.require("collections.manage")
    n = add_assets(tenant, collection_id, body.asset_ids, body.note)
    return {"added": n}


@router.delete("/collections/{collection_id}/assets/{asset_id}")
def remove_from_collection(collection_id: uuid.UUID, asset_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("collections.manage")
    remove_asset(tenant, collection_id, asset_id)
    return {"removed": True}


@router.put("/collections/{collection_id}/order")
def reorder_collection(collection_id: uuid.UUID, body: AssetsIn, tenant: TenantDep) -> dict:
    tenant.require("collections.manage")
    reorder(tenant, collection_id, body.asset_ids)
    return {"ok": True}
