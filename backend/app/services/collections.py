from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.api.errors import NotFound, ValidationFailed
from app.models import Asset, Collection, CollectionAsset


def get_collection(tenant, collection_id: uuid.UUID) -> Collection:  # noqa: ANN001
    c = tenant.db.scalar(select(Collection).where(Collection.id == collection_id))
    if c is None:
        raise NotFound("Collection not found")
    tenant.check_brand(c.brand_id)
    return c


def add_assets(tenant, collection_id: uuid.UUID, asset_ids: list[uuid.UUID], note: str | None = None) -> int:  # noqa: ANN001
    c = get_collection(tenant, collection_id)
    assets = tenant.db.scalars(select(Asset).where(Asset.id.in_(asset_ids), Asset.deleted_at.is_(None))).all()
    if any(a.brand_id != c.brand_id for a in assets):
        raise ValidationFailed("Assets must belong to the collection's brand")
    pos = tenant.db.scalar(select(func.coalesce(func.max(CollectionAsset.position), -1)).where(CollectionAsset.collection_id == c.id))
    existing = set(tenant.db.scalars(select(CollectionAsset.asset_id).where(CollectionAsset.collection_id == c.id)))
    n = 0
    for a in assets:
        if a.id in existing:
            continue
        pos += 1
        tenant.db.add(CollectionAsset(organization_id=tenant.org_id, collection_id=c.id, asset_id=a.id, position=pos,
                                      note=note, added_by=tenant.user_id))
        n += 1
    if c.cover_asset_id is None and assets:
        c.cover_asset_id = assets[0].id
    tenant.db.flush()
    return n


def remove_asset(tenant, collection_id: uuid.UUID, asset_id: uuid.UUID) -> None:  # noqa: ANN001
    c = get_collection(tenant, collection_id)
    row = tenant.db.scalar(select(CollectionAsset).where(CollectionAsset.collection_id == c.id, CollectionAsset.asset_id == asset_id))
    if row:
        tenant.db.delete(row)
    if c.cover_asset_id == asset_id:
        c.cover_asset_id = None
    tenant.db.flush()


def reorder(tenant, collection_id: uuid.UUID, asset_ids: list[uuid.UUID]) -> None:  # noqa: ANN001
    c = get_collection(tenant, collection_id)
    rows = {r.asset_id: r for r in tenant.db.scalars(select(CollectionAsset).where(CollectionAsset.collection_id == c.id))}
    for i, aid in enumerate(asset_ids):
        if aid in rows:
            rows[aid].position = i
    tenant.db.flush()
