"""Brand knowledge: domains, principles, guidelines, aesthetic ontology, knowledge entries,
relationships, revisions, approvals and brand versions."""
from __future__ import annotations

import uuid
from typing import Any

import yaml
from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.api.common import row_to_dict
from app.api.deps import TenantDep
from app.api.errors import NotFound, ValidationFailed
from app.api.v1.brands import get_brand_or_404
from app.knowledge.registry import ENTRY_TYPES, registry_payload
from app.models import (
    AestheticConcept,
    Asset,
    BrandVersion,
    Guideline,
    KnowledgeDomain,
    KnowledgeEntry,
    Principle,
    Relationship,
)
from app.models.base import DOMAIN_KEYS
from app.services import knowledge as ks
from app.services.graph import brand_graph, create_relationship, entity_relationships

router = APIRouter(tags=["knowledge"])

COLLECTIONS = {"principles": "principle", "guidelines": "guideline", "concepts": "aesthetic_concept", "entries": "knowledge_entry"}
CLASSIFICATIONS = "^(mandatory|preferred|optional|prohibited|context_dependent|experimental)$"
DOMAIN_RX = "^(" + "|".join(DOMAIN_KEYS) + ")$"


def _etype(collection: str) -> str:
    if collection not in COLLECTIONS:
        raise NotFound("Unknown knowledge collection")
    return COLLECTIONS[collection]


# --- Schemas ---------------------------------------------------------------------------------
class PrincipleIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    statement: str = Field(min_length=1)
    rationale: str | None = None
    classification: str = Field(pattern=CLASSIFICATIONS)
    domain_key: str | None = Field(None, pattern=DOMAIN_RX)
    scope: dict[str, Any] = Field(default_factory=dict, description='e.g. {"project_types": ["website_design"], "media": ["photography"]}')
    examples: dict[str, Any] = Field(default_factory=dict, description='{"do": [...], "dont": [...]}')
    priority: int = Field(50, ge=0, le=100)
    code: str | None = Field(None, pattern=r"^P-\d{3,}$")
    related_asset_ids: list[uuid.UUID] = Field(default_factory=list)
    concept_ids: list[uuid.UUID] = Field(default_factory=list)


class GuidelineIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    domain_key: str = Field(pattern=DOMAIN_RX)
    summary: str | None = None
    body: str = ""
    applies_to: dict[str, Any] = Field(default_factory=dict, description='e.g. {"project_types": ["website_design"]}')
    principle_ids: list[uuid.UUID] = Field(default_factory=list)


class ConceptIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    definition: str = Field(min_length=1)
    attributes: list[Any] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    brand_relevance: str = Field("supporting", pattern="^(core|supporting|peripheral|neutral|avoid)$")
    relevance_score: float | None = Field(None, ge=0, le=1)
    related_concept_ids: list[uuid.UUID] | None = None
    opposing_concept_ids: list[uuid.UUID] | None = None
    broader_concept_ids: list[uuid.UUID] | None = None
    example_asset_ids: list[uuid.UUID] = Field(default_factory=list)


class EntryIn(BaseModel):
    domain_key: str = Field(pattern=DOMAIN_RX)
    entry_type: str
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = None
    body: str = ""
    structured: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    sort_order: int = 0


SCHEMAS = {"principle": PrincipleIn, "guideline": GuidelineIn, "aesthetic_concept": ConceptIn, "knowledge_entry": EntryIn}


# --- Registry / domains ----------------------------------------------------------------------
@router.get("/knowledge/registry")
def registry(tenant: TenantDep) -> dict:
    tenant.require("knowledge.read")
    domains = tenant.db.scalars(select(KnowledgeDomain).order_by(KnowledgeDomain.number)).all()
    return {"domains": [{"key": d.key, "number": d.number, "name": d.name, "description": d.description} for d in domains],
            "entry_types": registry_payload()}


@router.get("/brands/{brand_id}/domains/{domain_key}")
def domain_view(brand_id: uuid.UUID, domain_key: str, tenant: TenantDep) -> dict:
    """Everything in one knowledge domain for a brand (entries, principles, guidelines, + domain-specific data)."""
    tenant.require("knowledge.read")
    get_brand_or_404(tenant, brand_id)
    if domain_key not in DOMAIN_KEYS:
        raise NotFound("Unknown domain")
    db = tenant.db
    d = db.scalar(select(KnowledgeDomain).where(KnowledgeDomain.key == domain_key))
    out: dict[str, Any] = {
        "domain": {"key": d.key, "number": d.number, "name": d.name, "description": d.description},
        "entry_types": [{"key": k, **v} for k, v in ENTRY_TYPES.get(domain_key, {}).items()],
        "entries": [row_to_dict(e) for e in db.scalars(select(KnowledgeEntry).where(
            KnowledgeEntry.brand_id == brand_id, KnowledgeEntry.domain_key == domain_key).order_by(KnowledgeEntry.sort_order, KnowledgeEntry.title))],
        "principles": [row_to_dict(p) for p in db.scalars(select(Principle).where(
            Principle.brand_id == brand_id, Principle.domain_key == domain_key).order_by(Principle.priority, Principle.code))],
        "guidelines": [row_to_dict(g) for g in db.scalars(select(Guideline).where(
            Guideline.brand_id == brand_id, Guideline.domain_key == domain_key).order_by(Guideline.title))],
    }
    if domain_key == "visual_identity":
        from app.api.v1.visual_identity import palettes_payload, typography_payload

        out["palettes"] = palettes_payload(db, brand_id)
        out["typography"] = typography_payload(db, brand_id)
        logos = db.scalars(select(Asset).where(Asset.brand_id == brand_id, Asset.deleted_at.is_(None),
                                               or_(Asset.asset_type == "logo", Asset.category == "logo"))).all()
        from app.services.assets import load_summaries

        out["logos"] = load_summaries(db, list(logos), tenant.org_id)
    if domain_key == "aesthetic_language":
        out["concepts"] = [row_to_dict(c) for c in db.scalars(select(AestheticConcept).where(AestheticConcept.brand_id == brand_id).order_by(AestheticConcept.name))]
    return out


# --- Generic governed CRUD -------------------------------------------------------------------
@router.get("/brands/{brand_id}/knowledge/{collection}")
def list_items(
    brand_id: uuid.UUID,
    collection: str,
    tenant: TenantDep,
    status: list[str] | None = Query(None),
    domain_key: str | None = None,
    classification: str | None = None,
    entry_type: str | None = None,
    q: str | None = Query(None, max_length=200),
) -> dict:
    etype = _etype(collection)
    tenant.require("knowledge.read")
    get_brand_or_404(tenant, brand_id)
    model = ks.spec(etype)["model"]
    stmt = select(model).where(model.brand_id == brand_id)
    if status:
        stmt = stmt.where(model.status.in_(status))
    if domain_key and hasattr(model, "domain_key"):
        stmt = stmt.where(model.domain_key == domain_key)
    if classification and etype == "principle":
        stmt = stmt.where(Principle.classification == classification)
    if entry_type and etype == "knowledge_entry":
        stmt = stmt.where(KnowledgeEntry.entry_type == entry_type)
    if q:
        stmt = stmt.where(model.search_tsv.op("@@")(func.bdna_tsq(q)))
    order = {"principle": (Principle.priority, Principle.code), "guideline": (Guideline.title,),
             "aesthetic_concept": (AestheticConcept.name,), "knowledge_entry": (KnowledgeEntry.domain_key, KnowledgeEntry.sort_order, KnowledgeEntry.title)}[etype]
    items = [row_to_dict(x) for x in tenant.db.scalars(stmt.order_by(*order))]
    return {"items": items, "total": len(items)}


def _after_create(tenant, etype: str, obj: Any, body: BaseModel) -> None:  # noqa: ANN001
    data = body.model_dump()
    if etype == "aesthetic_concept":
        ks.set_concept_relations(tenant, obj, data.get("related_concept_ids"), data.get("opposing_concept_ids"), data.get("broader_concept_ids"))
        for aid in data.get("example_asset_ids") or []:
            create_relationship(tenant.db, org_id=tenant.org_id, source_type="asset", source_id=aid, relation_type="exemplifies",
                                target_type="aesthetic_concept", target_id=obj.id, created_by=tenant.user_id)
    if etype == "principle":
        for aid in data.get("related_asset_ids") or []:
            create_relationship(tenant.db, org_id=tenant.org_id, source_type="asset", source_id=aid, relation_type="exemplifies",
                                target_type="principle", target_id=obj.id, created_by=tenant.user_id)
        for cid in data.get("concept_ids") or []:
            create_relationship(tenant.db, org_id=tenant.org_id, source_type="principle", source_id=obj.id, relation_type="related_to",
                                target_type="aesthetic_concept", target_id=cid, created_by=tenant.user_id)
    if etype == "guideline":
        for pid in data.get("principle_ids") or []:
            create_relationship(tenant.db, org_id=tenant.org_id, source_type="guideline", source_id=obj.id, relation_type="supports",
                                target_type="principle", target_id=pid, created_by=tenant.user_id)


@router.post("/brands/{brand_id}/knowledge/{collection}", status_code=201)
def create_item(brand_id: uuid.UUID, collection: str, body: dict[str, Any], tenant: TenantDep, submit: bool = False) -> dict:
    etype = _etype(collection)
    parsed = SCHEMAS[etype].model_validate(body)
    obj = ks.create(tenant, etype, brand_id, parsed.model_dump(), submit=submit)
    _after_create(tenant, etype, obj, parsed)
    return item_detail(tenant, etype, obj)


def item_detail(tenant, etype: str, obj: Any) -> dict:  # noqa: ANN001
    if etype == "aesthetic_concept":
        out = ks.concept_detail(tenant.db, obj, tenant.org_id)
    else:
        out = row_to_dict(obj)
        out["relationships"] = entity_relationships(tenant.db, etype, obj.id)
    off = ks.official_view(tenant.db, etype, obj)
    out["official_version"] = off.get("official_version") if off else None
    out["has_official_version"] = off is not None
    out["can_approve"] = tenant.can(ks.spec(etype)["approve"]) and tenant.identity.kind == "user"
    return out


@router.get("/knowledge/{collection}/{entity_id}")
def get_item(collection: str, entity_id: uuid.UUID, tenant: TenantDep) -> dict:
    etype = _etype(collection)
    tenant.require("knowledge.read")
    return item_detail(tenant, etype, ks.get(tenant, etype, entity_id))


@router.patch("/knowledge/{collection}/{entity_id}")
def update_item(collection: str, entity_id: uuid.UUID, body: dict[str, Any], tenant: TenantDep) -> dict:
    etype = _etype(collection)
    obj = ks.get(tenant, etype, entity_id)
    note = body.pop("change_note", None)
    schema = SCHEMAS[etype]
    allowed = set(schema.model_fields)
    unknown = set(body) - allowed
    if unknown:
        raise ValidationFailed("Unknown fields", details=sorted(unknown))
    merged = {**{k: getattr(obj, k) for k in ks.spec(etype)["fields"] if hasattr(obj, k)}, **body}
    for k in ("code",):
        merged.pop(k, None)
    parsed = schema.model_validate({**merged})
    changes = {k: v for k, v in parsed.model_dump().items() if k in body}
    ks.update(tenant, etype, obj, changes, note)
    if etype == "aesthetic_concept" and any(k in body for k in ("related_concept_ids", "opposing_concept_ids", "broader_concept_ids")):
        ks.set_concept_relations(tenant, obj, body.get("related_concept_ids"), body.get("opposing_concept_ids"), body.get("broader_concept_ids"))
    return item_detail(tenant, etype, obj)


class TransitionIn(BaseModel):
    notes: str | None = None


@router.post("/knowledge/{collection}/{entity_id}/{action}")
def transition_item(collection: str, entity_id: uuid.UUID, action: str, tenant: TenantDep, body: TransitionIn | None = None) -> dict:
    etype = _etype(collection)
    if action not in ks.TRANSITIONS:
        raise NotFound("Unknown action")
    obj = ks.get(tenant, etype, entity_id)
    ks.transition(tenant, etype, obj, action, body.notes if body else None)
    return item_detail(tenant, etype, obj)


@router.get("/knowledge/{collection}/{entity_id}/revisions")
def item_revisions(collection: str, entity_id: uuid.UUID, tenant: TenantDep) -> dict:
    etype = _etype(collection)
    tenant.require("knowledge.read")
    ks.get(tenant, etype, entity_id)
    return {"items": ks.revisions(tenant.db, etype, entity_id)}


@router.get("/knowledge/{collection}/{entity_id}/export")
def export_item(collection: str, entity_id: uuid.UUID, tenant: TenantDep, format: str = Query("json", pattern="^(json|yaml)$")):
    etype = _etype(collection)
    tenant.require("knowledge.read")
    obj = ks.get(tenant, etype, entity_id)
    data = {"type": etype, **row_to_dict(obj), "relationships": entity_relationships(tenant.db, etype, obj.id, include_suggested=False)}
    if format == "yaml":
        return PlainTextResponse(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), media_type="application/yaml")
    return data


@router.delete("/knowledge/{collection}/{entity_id}", status_code=204)
def delete_item(collection: str, entity_id: uuid.UUID, tenant: TenantDep) -> None:
    etype = _etype(collection)
    obj = ks.get(tenant, etype, entity_id)
    tenant.require(ks.spec(etype)["write"])
    if ks.official_view(tenant.db, etype, obj) is not None or obj.status == "approved":
        raise ValidationFailed("Approved knowledge cannot be deleted — deprecate or archive it to keep its history")
    tenant.audit(f"{etype}.deleted", etype, obj.id)
    tenant.db.delete(obj)


# --- Spec-style flat endpoints ----------------------------------------------------------------
@router.get("/principles", summary="List principles (brand_id query param)")
def flat_principles(tenant: TenantDep, brand_id: uuid.UUID, status: list[str] | None = Query(None)) -> dict:
    return list_items(brand_id, "principles", tenant, status, None, None, None, None)


# --- Relationships & graph ----------------------------------------------------------------------
class RelationshipIn(BaseModel):
    source_type: str
    source_id: uuid.UUID
    relation_type: str
    target_type: str
    target_id: uuid.UUID
    weight: float = Field(1.0, ge=0, le=1)
    note: str | None = None


@router.post("/relationships", status_code=201)
def add_relationship(body: RelationshipIn, tenant: TenantDep) -> dict:
    tenant.require("knowledge.write")
    rel = create_relationship(tenant.db, org_id=tenant.org_id, created_by=tenant.user_id, **body.model_dump())
    tenant.check_brand(rel.brand_id)
    tenant.audit("relationship.created", "relationship", rel.id, body.model_dump(mode="json"))
    return row_to_dict(rel)


@router.delete("/relationships/{rel_id}", status_code=204)
def delete_relationship(rel_id: uuid.UUID, tenant: TenantDep) -> None:
    tenant.require("knowledge.write")
    rel = tenant.db.scalar(select(Relationship).where(Relationship.id == rel_id))
    if rel is None:
        raise NotFound("Relationship not found")
    tenant.check_brand(rel.brand_id)
    tenant.audit("relationship.deleted", "relationship", rel.id)
    tenant.db.delete(rel)


@router.get("/brands/{brand_id}/graph")
def graph(brand_id: uuid.UUID, tenant: TenantDep, include_suggested: bool = False) -> dict:
    tenant.require("knowledge.read")
    get_brand_or_404(tenant, brand_id)
    return brand_graph(tenant.db, brand_id, include_suggested)


@router.get("/entities/{entity_type}/{entity_id}/relationships")
def relationships_of(entity_type: str, entity_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("knowledge.read")
    return {"items": entity_relationships(tenant.db, entity_type, entity_id)}


# --- Brand versions ---------------------------------------------------------------------------
class PublishIn(BaseModel):
    label: str | None = Field(None, max_length=120)
    notes: str | None = None


@router.get("/brands/{brand_id}/versions")
def list_versions(brand_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("brand.read")
    get_brand_or_404(tenant, brand_id)
    rows = tenant.db.scalars(select(BrandVersion).where(BrandVersion.brand_id == brand_id).order_by(BrandVersion.version_number.desc())).all()
    return {"items": [row_to_dict(v, {"snapshot"}) for v in rows]}


@router.post("/brands/{brand_id}/versions", status_code=201)
def publish(brand_id: uuid.UUID, body: PublishIn, tenant: TenantDep) -> dict:
    brand = get_brand_or_404(tenant, brand_id)
    v = ks.publish_version(tenant, brand, body.label, body.notes)
    return row_to_dict(v, {"snapshot"})


@router.get("/brand-versions/{version_id}")
def get_version(version_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("brand.read")
    v = tenant.db.scalar(select(BrandVersion).where(BrandVersion.id == version_id))
    if v is None:
        raise NotFound("Version not found")
    tenant.check_brand(v.brand_id)
    return row_to_dict(v)


@router.get("/brands/{brand_id}/guidelines", summary="Official (approved) guidelines and principles of a brand")
def guidelines_bundle(brand_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("knowledge.read")
    get_brand_or_404(tenant, brand_id)
    return {
        "guidelines": ks.official_items(tenant.db, "guideline", brand_id),
        "principles": ks.official_items(tenant.db, "principle", brand_id),
    }
