"""Governed brand knowledge: create → (submit) → approve / reject → deprecate, with immutable
revisions for every content version and approvals recorded as reviews.

Invariants
* Only an authenticated *human* with the approve permission can make knowledge official.
* Editing approved knowledge creates a new draft version; the last approved version stays
  available through ``official_view`` until the new draft is approved.
* AI suggestions can only ever create *drafts* (origin = ai_suggestion).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import jsonable, row_to_dict, slugify
from app.api.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.jobs.queue import enqueue
from app.knowledge.registry import ENTRY_TYPES, validate_structured
from app.models import (
    AestheticConcept,
    Brand,
    BrandVersion,
    ColorToken,
    DesignToken,
    Guideline,
    KnowledgeEntry,
    KnowledgeRevision,
    Palette,
    Principle,
    Relationship,
    Review,
    TypographySystem,
)
from app.services.events import emit

GOVERNED: dict[str, dict[str, Any]] = {
    "principle": {
        "model": Principle,
        "fields": ["title", "statement", "rationale", "classification", "domain_key", "scope", "examples", "priority"],
        "write": "knowledge.write",
        "approve": "knowledge.approve",
    },
    "guideline": {
        "model": Guideline,
        "fields": ["title", "summary", "body", "domain_key", "applies_to"],
        "write": "knowledge.write",
        "approve": "knowledge.approve",
    },
    "aesthetic_concept": {
        "model": AestheticConcept,
        "fields": ["name", "definition", "attributes", "synonyms", "brand_relevance", "relevance_score"],
        "write": "concepts.manage",
        "approve": "concepts.manage",
    },
    "knowledge_entry": {
        "model": KnowledgeEntry,
        "fields": ["title", "summary", "body", "structured", "tags", "sort_order", "entry_type", "domain_key"],
        "write": "knowledge.write",
        "approve": "knowledge.approve",
    },
}
SNAPSHOT_EXCLUDE = {"organization_id", "search_tsv", "created_at", "updated_at"}


def spec(etype: str) -> dict[str, Any]:
    if etype not in GOVERNED:
        raise NotFound(f"Unknown knowledge type {etype!r}")
    return GOVERNED[etype]


def get(tenant, etype: str, entity_id: uuid.UUID):  # noqa: ANN001
    model = spec(etype)["model"]
    obj = tenant.db.scalar(select(model).where(model.id == entity_id))
    if obj is None:
        raise NotFound(f"{etype.replace('_', ' ').capitalize()} not found")
    tenant.check_brand(obj.brand_id)
    return obj


def _revision(db: Session, etype: str, obj: Any, note: str | None, user_id: uuid.UUID | None) -> None:
    db.add(
        KnowledgeRevision(
            organization_id=obj.organization_id, brand_id=obj.brand_id, entity_type=etype, entity_id=obj.id,
            version=obj.version, status=obj.status, data=row_to_dict(obj, SNAPSHOT_EXCLUDE), change_note=note,
            created_by=user_id,
        )
    )


def next_principle_code(db: Session, brand_id: uuid.UUID) -> str:
    codes = db.scalars(select(Principle.code).where(Principle.brand_id == brand_id)).all()
    nums = [int(m.group(1)) for c in codes if (m := re.match(r"^P-(\d+)$", c or ""))]
    return f"P-{(max(nums) + 1) if nums else 1:03d}"


def _validate(etype: str, data: dict[str, Any], db: Session, brand_id: uuid.UUID, obj: Any = None) -> None:
    if etype == "knowledge_entry":
        domain = data.get("domain_key", getattr(obj, "domain_key", None))
        etype_key = data.get("entry_type", getattr(obj, "entry_type", None))
        if domain not in ENTRY_TYPES or etype_key not in ENTRY_TYPES[domain]:
            raise ValidationFailed(f"Unknown entry type {etype_key!r} for domain {domain!r}",
                                   details={"allowed": sorted(ENTRY_TYPES.get(domain, {}))})
        errs = validate_structured(domain, etype_key, data.get("structured", getattr(obj, "structured", {}) or {}))
        if errs:
            raise ValidationFailed("Invalid structured fields", details=errs)
    if etype == "principle" and data.get("examples") is not None:
        ex = data["examples"]
        if not isinstance(ex, dict) or any(k not in ("do", "dont", "notes") for k in ex):
            raise ValidationFailed("examples must be an object with 'do' / 'dont' lists")


def create(tenant, etype: str, brand_id: uuid.UUID, data: dict[str, Any], *, origin: str = "human",
           suggestion_id: uuid.UUID | None = None, submit: bool = False):  # noqa: ANN001
    s = spec(etype)
    tenant.require(s["write"])
    if not tenant.db.scalar(select(Brand.id).where(Brand.id == brand_id)):
        raise NotFound("Brand not found")
    tenant.check_brand(brand_id)
    _validate(etype, data, tenant.db, brand_id)
    model = s["model"]
    kwargs = {k: v for k, v in data.items() if k in s["fields"] and v is not None}
    if etype == "principle":
        kwargs["code"] = data.get("code") or next_principle_code(tenant.db, brand_id)
        if tenant.db.scalar(select(Principle.id).where(Principle.brand_id == brand_id, Principle.code == kwargs["code"])):
            raise Conflict(f"Principle code {kwargs['code']} already exists")
    if etype in ("guideline", "aesthetic_concept"):
        base = slugify(data.get("slug") or data.get("title") or data.get("name"), 120)
        slug, n = base, 2
        while tenant.db.scalar(select(model.id).where(model.brand_id == brand_id, model.slug == slug)):
            slug, n = f"{base}-{n}", n + 1
        kwargs["slug"] = slug
    obj = model(
        organization_id=tenant.org_id, brand_id=brand_id, status="in_review" if submit else "draft", version=1,
        origin=origin, source_suggestion_id=suggestion_id, created_by=tenant.user_id, updated_by=tenant.user_id, **kwargs,
    )
    tenant.db.add(obj)
    tenant.db.flush()
    _revision(tenant.db, etype, obj, "created" if origin == "human" else f"created from {origin}", tenant.user_id)
    enqueue(tenant.db, tenant.org_id, "knowledge.embed", brand_id=brand_id, entity_type=etype, entity_id=obj.id, priority=120)
    tenant.audit(f"{etype}.created", etype, obj.id, {"origin": origin})
    return obj


def update(tenant, etype: str, obj: Any, changes: dict[str, Any], note: str | None = None):  # noqa: ANN001
    s = spec(etype)
    tenant.require(s["write"])
    changes = {k: v for k, v in changes.items() if k in s["fields"]}
    _validate(etype, changes, tenant.db, obj.brand_id, obj)
    real = {k: v for k, v in changes.items() if jsonable(getattr(obj, k)) != jsonable(v)}
    if not real:
        return obj
    was_approved = obj.status == "approved"
    for k, v in real.items():
        setattr(obj, k, v)
    obj.version += 1
    obj.updated_by = tenant.user_id
    if was_approved or obj.status in ("rejected", "deprecated"):
        obj.status = "draft"  # previous approved version remains the official one until re-approval
        obj.approved_by = obj.approved_at = None
    tenant.db.flush()
    _revision(tenant.db, etype, obj, note or "edited", tenant.user_id)
    enqueue(tenant.db, tenant.org_id, "knowledge.embed", brand_id=obj.brand_id, entity_type=etype, entity_id=obj.id, priority=120)
    tenant.audit(f"{etype}.updated", etype, obj.id, {"fields": sorted(real), "version": obj.version})
    return obj


TRANSITIONS = {
    "submit": ({"draft", "rejected"}, "in_review"),
    "approve": ({"draft", "in_review", "rejected", "deprecated"}, "approved"),
    "reject": ({"draft", "in_review"}, "rejected"),
    "deprecate": ({"approved"}, "deprecated"),
    "archive": ({"draft", "in_review", "rejected", "deprecated", "approved"}, "archived"),
    "restore": ({"archived", "rejected", "deprecated"}, "draft"),
}


def transition(tenant, etype: str, obj: Any, action: str, notes: str | None = None):  # noqa: ANN001
    s = spec(etype)
    if action not in TRANSITIONS:
        raise ValidationFailed(f"Unknown action {action!r}")
    allowed_from, to = TRANSITIONS[action]
    if action in ("approve", "reject", "deprecate"):
        tenant.require(s["approve"])
        if tenant.identity.kind != "user":
            raise Forbidden("Official brand knowledge can only be approved by a person, not an API token")
    else:
        tenant.require(s["write"])
    if obj.status not in allowed_from:
        raise ValidationFailed(f"Cannot {action} a {obj.status} {etype.replace('_', ' ')}")
    obj.status = to
    if to == "approved":
        obj.approved_by, obj.approved_at = tenant.user_id, dt.datetime.now(dt.UTC)
    tenant.db.add(
        Review(
            organization_id=tenant.org_id, brand_id=obj.brand_id, subject_type=etype, subject_id=obj.id,
            decision={"approve": "approved", "reject": "rejected"}.get(action, "changes_requested"),
            notes=notes, reviewer_id=tenant.user_id, changes={"action": action, "version": obj.version, "status": to},
        )
    )
    tenant.audit(f"{etype}.{action}", etype, obj.id, {"version": obj.version})
    if to == "approved":
        emit(tenant.db, tenant.org_id, "knowledge.approved", {"entity_type": etype, "entity_id": str(obj.id), "version": obj.version})
    tenant.db.flush()
    return obj


def revisions(db: Session, etype: str, entity_id: uuid.UUID) -> list[dict[str, Any]]:
    approvals = {
        (r.changes or {}).get("version"): r
        for r in db.scalars(
            select(Review).where(Review.subject_type == etype, Review.subject_id == entity_id, Review.decision == "approved")
        )
    }
    out = []
    for r in db.scalars(
        select(KnowledgeRevision).where(KnowledgeRevision.entity_type == etype, KnowledgeRevision.entity_id == entity_id)
        .order_by(KnowledgeRevision.version.desc())
    ):
        ap = approvals.get(r.version)
        out.append({
            "version": r.version, "status_at_creation": r.status, "change_note": r.change_note, "data": r.data,
            "created_by": jsonable(r.created_by), "created_at": r.created_at.isoformat(),
            "approved": ap is not None, "approved_at": ap.created_at.isoformat() if ap else None,
            "approved_by": jsonable(ap.reviewer_id) if ap else None,
        })
    return out


def official_view(db: Session, etype: str, obj: Any) -> dict[str, Any] | None:
    """The officially approved content: current row if approved, else the last approved version."""
    if obj.status == "approved":
        return {**row_to_dict(obj, SNAPSHOT_EXCLUDE), "official_version": obj.version, "has_newer_draft": False}
    if obj.status in ("deprecated", "archived"):
        return None
    reviews = db.scalars(
        select(Review).where(Review.subject_type == etype, Review.subject_id == obj.id, Review.decision == "approved")
        .order_by(Review.created_at.desc())
    ).all()
    for rv in reviews:
        ver = (rv.changes or {}).get("version")
        if ver is None or ver >= obj.version:
            continue
        rev = db.scalar(select(KnowledgeRevision).where(
            KnowledgeRevision.entity_type == etype, KnowledgeRevision.entity_id == obj.id, KnowledgeRevision.version == ver))
        if rev:
            return {**rev.data, "status": "approved", "official_version": ver, "has_newer_draft": True}
    return None


def official_items(db: Session, etype: str, brand_id: uuid.UUID) -> list[dict[str, Any]]:
    model = spec(etype)["model"]
    out = []
    for obj in db.scalars(select(model).where(model.brand_id == brand_id)):
        view = official_view(db, etype, obj)
        if view:
            out.append(view)
    return out


# --- Concept relations -----------------------------------------------------------------------
def set_concept_relations(tenant, concept: AestheticConcept, related: list[uuid.UUID] | None,
                          opposing: list[uuid.UUID] | None, broader: list[uuid.UUID] | None = None) -> None:  # noqa: ANN001
    from app.services.graph import create_relationship

    for rel_type, ids in (("related_to", related), ("opposes", opposing), ("broader_than", broader)):
        if ids is None:
            continue
        existing = tenant.db.scalars(
            select(Relationship).where(
                Relationship.relation_type == rel_type,
                ((Relationship.source_type == "aesthetic_concept") & (Relationship.source_id == concept.id))
                | ((Relationship.target_type == "aesthetic_concept") & (Relationship.target_id == concept.id)),
            )
        ).all()
        if rel_type == "broader_than":
            existing = [r for r in existing if r.target_id == concept.id]
        keep = set(ids)
        for r in existing:
            other = r.target_id if r.source_id == concept.id else r.source_id
            if other not in keep:
                tenant.db.delete(r)
        tenant.db.flush()
        for oid in ids:
            if oid == concept.id:
                continue
            if rel_type == "broader_than":
                create_relationship(tenant.db, org_id=tenant.org_id, source_type="aesthetic_concept", source_id=oid,
                                    relation_type=rel_type, target_type="aesthetic_concept", target_id=concept.id, created_by=tenant.user_id)
            else:
                create_relationship(tenant.db, org_id=tenant.org_id, source_type="aesthetic_concept", source_id=concept.id,
                                    relation_type=rel_type, target_type="aesthetic_concept", target_id=oid, created_by=tenant.user_id)


def concept_detail(db: Session, c: AestheticConcept, org_id: uuid.UUID) -> dict[str, Any]:
    from app.models import Asset
    from app.services.assets import load_summaries
    from app.services.graph import entity_relationships

    rels = entity_relationships(db, "aesthetic_concept", c.id)
    out = row_to_dict(c)
    out["related_concepts"] = [r for r in rels if r["relation_type"] == "related_to" and r["other_type"] == "aesthetic_concept"]
    out["opposing_concepts"] = [r for r in rels if r["relation_type"] == "opposes" and r["other_type"] == "aesthetic_concept"]
    out["broader_concepts"] = [r for r in rels if r["relation_type"] == "broader_than" and r["direction"] == "incoming"]
    out["narrower_concepts"] = [r for r in rels if r["relation_type"] == "broader_than" and r["direction"] == "outgoing"]
    ex_ids = [uuid.UUID(r["other_id"]) for r in rels if r["other_type"] == "asset" and r["relation_type"] == "exemplifies"]
    assets = db.scalars(select(Asset).where(Asset.id.in_(ex_ids), Asset.deleted_at.is_(None))).all() if ex_ids else []
    out["example_assets"] = load_summaries(db, list(assets), org_id)
    out["suggested_example_count"] = sum(1 for r in rels if r["other_type"] == "asset" and r["status"] == "suggested")
    return out


# --- Brand versions --------------------------------------------------------------------------
def build_snapshot(db: Session, brand_id: uuid.UUID) -> dict[str, Any]:
    brand = db.scalar(select(Brand).where(Brand.id == brand_id))
    snap: dict[str, Any] = {"brand": row_to_dict(brand, {"organization_id", "current_version_id", "updated_at"})}
    for etype in GOVERNED:
        snap[etype + "s"] = sorted(official_items(db, etype, brand_id), key=lambda x: str(x.get("id")))
    snap["palettes"] = []
    for p in db.scalars(select(Palette).where(Palette.brand_id == brand_id, Palette.status == "approved").order_by(Palette.sort_order)):
        d = row_to_dict(p, SNAPSHOT_EXCLUDE)
        d["colors"] = [row_to_dict(c, SNAPSHOT_EXCLUDE) for c in db.scalars(
            select(ColorToken).where(ColorToken.palette_id == p.id).order_by(ColorToken.sort_order))]
        snap["palettes"].append(d)
    snap["typography_systems"] = [row_to_dict(t, SNAPSHOT_EXCLUDE) for t in db.scalars(
        select(TypographySystem).where(TypographySystem.brand_id == brand_id, TypographySystem.status == "approved").order_by(TypographySystem.sort_order))]
    snap["design_tokens"] = [row_to_dict(t, SNAPSHOT_EXCLUDE) for t in db.scalars(
        select(DesignToken).where(DesignToken.brand_id == brand_id, DesignToken.status == "approved").order_by(DesignToken.path))]
    ids = {str(x["id"]) for k in ("principles", "guidelines", "aesthetic_concepts", "knowledge_entrys") for x in snap[k]}
    snap["relationships"] = [
        row_to_dict(r, SNAPSHOT_EXCLUDE) for r in db.scalars(select(Relationship).where(Relationship.brand_id == brand_id, Relationship.status == "approved"))
        if str(r.source_id) in ids or str(r.target_id) in ids
    ]
    snap["knowledge_entries"] = snap.pop("knowledge_entrys")
    return snap


def publish_version(tenant, brand: Brand, label: str | None, notes: str | None) -> BrandVersion:  # noqa: ANN001
    tenant.require("brand.publish")
    if tenant.identity.kind != "user":
        raise Forbidden("Brand versions can only be published by a person")
    snap = build_snapshot(tenant.db, brand.id)
    body = json.dumps(snap, sort_keys=True, default=str)
    checksum = hashlib.sha256(body.encode()).hexdigest()
    last = tenant.db.scalar(select(func.max(BrandVersion.version_number)).where(BrandVersion.brand_id == brand.id)) or 0
    for v in tenant.db.scalars(select(BrandVersion).where(BrandVersion.brand_id == brand.id, BrandVersion.status == "published")):
        v.status = "superseded"
    counts = {k: len(v) for k, v in snap.items() if isinstance(v, list)}
    ver = BrandVersion(
        organization_id=tenant.org_id, brand_id=brand.id, version_number=last + 1, label=label or f"v{last + 1}",
        notes=notes, snapshot=json.loads(body), snapshot_checksum=checksum, counts=counts, published_by=tenant.user_id,
    )
    tenant.db.add(ver)
    tenant.db.flush()
    brand.current_version_id = ver.id
    tenant.audit("brand.version_published", "brand_version", ver.id, {"version": ver.version_number, "checksum": checksum})
    emit(tenant.db, tenant.org_id, "brand.version_published", {"brand_id": str(brand.id), "version": ver.version_number})
    return ver


_ = (hashlib,)
