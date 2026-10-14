from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.common import row_to_dict, slugify
from app.api.deps import TenantDep
from app.api.errors import Conflict, NotFound
from app.api.v1.brands import get_brand_or_404
from app.jobs.queue import enqueue
from app.models import Asset, ContextPackage, Project
from app.models.base import DOMAIN_KEYS
from app.models.knowledge import PROJECT_TYPES
from app.services.assets import load_summaries
from app.services.graph import create_relationship, entity_relationships

router = APIRouter(tags=["projects"])
PT_RX = "^(" + "|".join(PROJECT_TYPES) + ")$"


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project_type: str = Field(pattern=PT_RX)
    status: str = Field("planning", pattern="^(planning|active|completed|archived)$")
    description: str | None = None
    objectives: str | None = None
    audience: str | None = None
    deliverables: list[Any] = Field(default_factory=list)
    selected_domains: list[str] = Field(default_factory=list)
    brief: dict[str, Any] = Field(default_factory=dict)
    start_date: dt.date | None = None
    due_date: dt.date | None = None
    asset_ids: list[uuid.UUID] = Field(default_factory=list, description="Reference assets used by the project")
    concept_ids: list[uuid.UUID] = Field(default_factory=list)
    principle_ids: list[uuid.UUID] = Field(default_factory=list)


def _project(tenant, project_id: uuid.UUID) -> Project:  # noqa: ANN001
    p = tenant.db.scalar(select(Project).where(Project.id == project_id))
    if p is None:
        raise NotFound("Project not found")
    tenant.check_brand(p.brand_id)
    return p


def _link(tenant, p: Project, asset_ids, concept_ids, principle_ids) -> None:  # noqa: ANN001
    for aid in asset_ids or []:
        create_relationship(tenant.db, org_id=tenant.org_id, source_type="project", source_id=p.id, relation_type="uses",
                            target_type="asset", target_id=aid, created_by=tenant.user_id)
    for cid in concept_ids or []:
        create_relationship(tenant.db, org_id=tenant.org_id, source_type="project", source_id=p.id, relation_type="uses",
                            target_type="aesthetic_concept", target_id=cid, created_by=tenant.user_id)
    for pid in principle_ids or []:
        create_relationship(tenant.db, org_id=tenant.org_id, source_type="principle", source_id=pid, relation_type="applies_to",
                            target_type="project", target_id=p.id, created_by=tenant.user_id)


def project_detail(tenant, p: Project) -> dict[str, Any]:  # noqa: ANN001
    d = row_to_dict(p)
    rels = entity_relationships(tenant.db, "project", p.id)
    d["relationships"] = rels
    aids = [uuid.UUID(r["other_id"]) for r in rels if r["other_type"] == "asset"]
    assets = tenant.db.scalars(select(Asset).where(Asset.id.in_(aids), Asset.deleted_at.is_(None))).all() if aids else []
    d["assets"] = load_summaries(tenant.db, list(assets), tenant.org_id)
    d["context_packages"] = [
        {"id": str(c.id), "title": c.title, "task_type": c.task_type, "mode": c.mode, "created_at": c.created_at.isoformat()}
        for c in tenant.db.scalars(select(ContextPackage).where(ContextPackage.project_id == p.id).order_by(ContextPackage.created_at.desc()))
    ]
    return d


@router.get("/brands/{brand_id}/projects")
def list_projects(brand_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("knowledge.read")
    get_brand_or_404(tenant, brand_id)
    return {"items": [row_to_dict(p) for p in tenant.db.scalars(select(Project).where(Project.brand_id == brand_id).order_by(Project.created_at.desc()))],
            "project_types": PROJECT_TYPES}


@router.post("/brands/{brand_id}/projects", status_code=201)
def create_project(brand_id: uuid.UUID, body: ProjectIn, tenant: TenantDep) -> dict:
    tenant.require("projects.manage")
    get_brand_or_404(tenant, brand_id)
    bad = [d for d in body.selected_domains if d not in DOMAIN_KEYS]
    if bad:
        from app.api.errors import ValidationFailed

        raise ValidationFailed("Unknown domains", details=bad)
    slug = slugify(body.name, 120)
    if tenant.db.scalar(select(Project.id).where(Project.brand_id == brand_id, Project.slug == slug)):
        raise Conflict("A project with this name already exists")
    data = body.model_dump(exclude={"asset_ids", "concept_ids", "principle_ids"})
    p = Project(organization_id=tenant.org_id, brand_id=brand_id, slug=slug, created_by=tenant.user_id, **data)
    tenant.db.add(p)
    tenant.db.flush()
    _link(tenant, p, body.asset_ids, body.concept_ids, body.principle_ids)
    enqueue(tenant.db, tenant.org_id, "knowledge.embed", brand_id=brand_id, entity_type="project", entity_id=p.id, priority=150)
    tenant.audit("project.created", "project", p.id, {"name": p.name, "type": p.project_type})
    return project_detail(tenant, p)


@router.get("/projects/{project_id}")
def get_project(project_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("knowledge.read")
    return project_detail(tenant, _project(tenant, project_id))


@router.patch("/projects/{project_id}")
def update_project(project_id: uuid.UUID, body: dict[str, Any], tenant: TenantDep) -> dict:
    tenant.require("projects.manage")
    p = _project(tenant, project_id)
    merged = ProjectIn.model_validate({**row_to_dict(p), **body})
    data = merged.model_dump(exclude={"asset_ids", "concept_ids", "principle_ids"})
    for k in body:
        if k in data:
            setattr(p, k, data[k])
    _link(tenant, p, body.get("asset_ids") and merged.asset_ids, body.get("concept_ids") and merged.concept_ids,
          body.get("principle_ids") and merged.principle_ids)
    enqueue(tenant.db, tenant.org_id, "knowledge.embed", brand_id=p.brand_id, entity_type="project", entity_id=p.id, priority=150)
    tenant.db.flush()
    return project_detail(tenant, p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, tenant: TenantDep) -> None:
    tenant.require("projects.manage")
    p = _project(tenant, project_id)
    tenant.audit("project.deleted", "project", p.id, {"name": p.name})
    tenant.db.delete(p)
