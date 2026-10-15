from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.common import row_to_dict, slugify
from app.api.deps import TenantDep
from app.api.errors import Conflict, NotFound
from app.models import (
    AestheticConcept,
    Asset,
    Brand,
    BrandVersion,
    ColorToken,
    DesignToken,
    Guideline,
    KnowledgeDomain,
    KnowledgeEntry,
    Principle,
    Project,
    TypographySystem,
)

router = APIRouter(prefix="/brands", tags=["brands"])


def get_brand_or_404(tenant, brand_id: uuid.UUID) -> Brand:
    tenant.check_brand(brand_id)
    brand = tenant.db.scalar(select(Brand).where(Brand.id == brand_id))
    if brand is None:
        raise NotFound("Brand not found")
    return brand


@router.get("")
def list_brands(tenant: TenantDep) -> dict:
    tenant.require("brand.read")
    q = select(Brand).order_by(Brand.created_at)
    if tenant.brand_restriction:
        q = q.where(Brand.id == tenant.brand_restriction)
    return {"items": [row_to_dict(b) for b in tenant.db.scalars(q)]}


class BrandIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(None, max_length=80)
    tagline: str | None = Field(None, max_length=300)
    description: str | None = None
    primary_language: str = Field("en", max_length=16)


@router.post("", status_code=201)
def create_brand(body: BrandIn, tenant: TenantDep) -> dict:
    tenant.require("brand.manage")
    slug = slugify(body.slug or body.name)
    if tenant.db.scalar(select(Brand.id).where(Brand.slug == slug)):
        raise Conflict(f"Brand slug '{slug}' already exists in this workspace")
    b = Brand(
        organization_id=tenant.org_id,
        name=body.name,
        slug=slug,
        tagline=body.tagline,
        description=body.description,
        primary_language=body.primary_language,
        created_by=tenant.user_id,
    )
    tenant.db.add(b)
    tenant.db.flush()
    tenant.audit("brand.created", "brand", b.id, {"name": b.name})
    return row_to_dict(b)


class BrandUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    tagline: str | None = None
    description: str | None = None
    primary_language: str | None = None
    status: str | None = Field(None, pattern="^(active|archived)$")
    settings: dict[str, Any] | None = None


@router.get("/{brand_id}")
def get_brand(brand_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("brand.read")
    brand = get_brand_or_404(tenant, brand_id)
    return {**row_to_dict(brand), "overview": brand_overview(tenant, brand)}


@router.patch("/{brand_id}")
def update_brand(brand_id: uuid.UUID, body: BrandUpdateIn, tenant: TenantDep) -> dict:
    tenant.require("brand.manage")
    brand = get_brand_or_404(tenant, brand_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(brand, k, v)
    tenant.audit("brand.updated", "brand", brand.id, {"fields": sorted(changes)})
    tenant.db.flush()
    return row_to_dict(brand)


@router.post("/{brand_id}/reindex", status_code=202)
def reindex_brand(brand_id: uuid.UUID, tenant: TenantDep) -> dict:
    """Rebuild search embeddings for the whole brand, e.g. after changing the embedding provider."""
    tenant.require("brand.manage")
    brand = get_brand_or_404(tenant, brand_id)
    from app.jobs.queue import enqueue

    job = enqueue(tenant.db, tenant.org_id, "brand.reindex", brand_id=brand.id, entity_type="brand", entity_id=brand.id,
                  created_by=tenant.user_id, priority=90)
    tenant.audit("brand.reindex_requested", "brand", brand.id)
    return {"job_id": str(job.id)}


def brand_overview(tenant, brand: Brand) -> dict[str, Any]:
    db = tenant.db

    def by_status(model) -> dict[str, int]:
        return dict(
            db.execute(select(model.status, func.count()).where(model.brand_id == brand.id).group_by(model.status)).all()
        )

    entries = db.execute(
        select(KnowledgeEntry.domain_key, KnowledgeEntry.status, func.count())
        .where(KnowledgeEntry.brand_id == brand.id)
        .group_by(KnowledgeEntry.domain_key, KnowledgeEntry.status)
    ).all()
    per_domain: dict[str, dict[str, int]] = {}
    for dk, st, n in entries:
        per_domain.setdefault(dk, {})[st] = n
    domains = db.scalars(select(KnowledgeDomain).order_by(KnowledgeDomain.number)).all()
    version = None
    if brand.current_version_id:
        v = db.scalar(select(BrandVersion).where(BrandVersion.id == brand.current_version_id))
        version = {"id": str(v.id), "version_number": v.version_number, "label": v.label, "published_at": v.published_at.isoformat()}
    return {
        "current_version": version,
        "domains": [
            {"key": d.key, "number": d.number, "name": d.name, "entries": per_domain.get(d.key, {})} for d in domains
        ],
        "principles": by_status(Principle),
        "guidelines": by_status(Guideline),
        "aesthetic_concepts": by_status(AestheticConcept),
        "typography_systems": by_status(TypographySystem),
        "design_tokens": by_status(DesignToken),
        "color_tokens": db.scalar(select(func.count()).select_from(ColorToken).where(ColorToken.brand_id == brand.id)) or 0,
        "assets": dict(
            db.execute(
                select(Asset.approval_status, func.count())
                .where(Asset.brand_id == brand.id, Asset.deleted_at.is_(None))
                .group_by(Asset.approval_status)
            ).all()
        ),
        "projects": db.scalar(select(func.count()).select_from(Project).where(Project.brand_id == brand.id)) or 0,
    }
