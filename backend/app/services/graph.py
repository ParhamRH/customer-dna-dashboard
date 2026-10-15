"""Knowledge graph helpers: typed relationships between brand entities."""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.common import jsonable
from app.api.errors import NotFound, ValidationFailed
from app.models import (
    AestheticConcept,
    Asset,
    AssetSegment,
    Collection,
    ColorToken,
    DesignToken,
    ExternalReference,
    Guideline,
    KnowledgeEntry,
    Palette,
    Principle,
    Project,
    Relationship,
    TypographySystem,
)
from app.models.knowledge import RELATION_TYPES

ENTITY_MODELS = {
    "asset": (Asset, "title"),
    "asset_segment": (AssetSegment, "title"),
    "principle": (Principle, "title"),
    "guideline": (Guideline, "title"),
    "aesthetic_concept": (AestheticConcept, "name"),
    "knowledge_entry": (KnowledgeEntry, "title"),
    "project": (Project, "name"),
    "collection": (Collection, "name"),
    "palette": (Palette, "name"),
    "color_token": (ColorToken, "name"),
    "typography_system": (TypographySystem, "name"),
    "design_token": (DesignToken, "path"),
    "external_reference": (ExternalReference, "title"),
}

SYMMETRIC = {"related_to", "opposes"}


def entity_labels(db: Session, refs: list[tuple[str, uuid.UUID]]) -> dict[tuple[str, uuid.UUID], dict[str, Any]]:
    by_type: dict[str, set[uuid.UUID]] = defaultdict(set)
    for t, i in refs:
        by_type[t].add(i)
    out: dict[tuple[str, uuid.UUID], dict[str, Any]] = {}
    for t, ids in by_type.items():
        model, label_attr = ENTITY_MODELS[t]
        cols = [model.id, getattr(model, label_attr)]
        status_col = getattr(model, "status", None) or getattr(model, "approval_status", None)
        if status_col is not None:
            cols.append(status_col)
        for row in db.execute(select(*cols).where(model.id.in_(ids))).all():
            out[(t, row[0])] = {"label": row[1], "status": row[2] if len(row) > 2 else None}
    return out


def entity_relationships(db: Session, entity_type: str, entity_id: uuid.UUID, include_suggested: bool = True) -> list[dict[str, Any]]:
    q = select(Relationship).where(
        or_(
            (Relationship.source_type == entity_type) & (Relationship.source_id == entity_id),
            (Relationship.target_type == entity_type) & (Relationship.target_id == entity_id),
        )
    )
    if not include_suggested:
        q = q.where(Relationship.status == "approved")
    rels = db.scalars(q.order_by(Relationship.created_at)).all()
    others = []
    for r in rels:
        outgoing = r.source_type == entity_type and r.source_id == entity_id
        others.append((r.target_type, r.target_id) if outgoing else (r.source_type, r.source_id))
    labels = entity_labels(db, others)
    out = []
    for r, other in zip(rels, others, strict=True):
        outgoing = r.source_type == entity_type and r.source_id == entity_id
        info = labels.get(other, {})
        out.append(
            {
                "id": str(r.id),
                "relation_type": r.relation_type,
                "direction": "outgoing" if outgoing else "incoming",
                "other_type": other[0],
                "other_id": str(other[1]),
                "other_label": info.get("label"),
                "other_status": info.get("status"),
                "status": r.status,
                "origin": r.origin,
                "weight": jsonable(r.weight),
                "confidence": jsonable(r.confidence),
                "note": r.note,
            }
        )
    return out


def get_entity(db: Session, entity_type: str, entity_id: uuid.UUID):
    if entity_type not in ENTITY_MODELS:
        raise ValidationFailed(f"Unknown entity type {entity_type!r}")
    model, _ = ENTITY_MODELS[entity_type]
    obj = db.scalar(select(model).where(model.id == entity_id))
    if obj is None:
        raise NotFound(f"{entity_type} not found")
    return obj


def _brand_of(db: Session, entity_type: str, obj) -> uuid.UUID:  # noqa: ANN001
    if entity_type == "asset_segment":
        return db.scalar(select(Asset.brand_id).where(Asset.id == obj.asset_id))
    return obj.brand_id


def create_relationship(
    db: Session,
    *,
    org_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    relation_type: str,
    target_type: str,
    target_id: uuid.UUID,
    origin: str = "human",
    status: str = "approved",
    weight: float = 1.0,
    confidence: float | None = None,
    note: str | None = None,
    created_by: uuid.UUID | None = None,
    source_suggestion_id: uuid.UUID | None = None,
) -> Relationship:
    if relation_type not in RELATION_TYPES:
        raise ValidationFailed(f"Unknown relation type {relation_type!r}")
    src = get_entity(db, source_type, source_id)
    tgt = get_entity(db, target_type, target_id)
    b1, b2 = _brand_of(db, source_type, src), _brand_of(db, target_type, tgt)
    if b1 != b2:
        raise ValidationFailed("Both entities must belong to the same brand")
    if relation_type in SYMMETRIC and (source_type, str(source_id)) > (target_type, str(target_id)):
        source_type, source_id, target_type, target_id = target_type, target_id, source_type, source_id
    existing = db.scalar(
        select(Relationship).where(
            Relationship.source_type == source_type,
            Relationship.source_id == source_id,
            Relationship.relation_type == relation_type,
            Relationship.target_type == target_type,
            Relationship.target_id == target_id,
        )
    )
    if existing:
        if status == "approved" and existing.status != "approved":
            existing.status, existing.origin = "approved", origin
        return existing
    rel = Relationship(
        organization_id=org_id,
        brand_id=b1,
        source_type=source_type,
        source_id=source_id,
        relation_type=relation_type,
        target_type=target_type,
        target_id=target_id,
        origin=origin,
        status=status,
        weight=weight,
        confidence=confidence,
        note=note,
        created_by=created_by,
        source_suggestion_id=source_suggestion_id,
    )
    db.add(rel)
    db.flush()
    return rel


def brand_graph(db: Session, brand_id: uuid.UUID, include_suggested: bool = False, limit: int = 2000) -> dict[str, Any]:
    # Rejected relationships never appear; suggested ones only when explicitly requested (and are flagged).
    q = select(Relationship).where(
        Relationship.brand_id == brand_id,
        Relationship.status.in_(("approved", "suggested") if include_suggested else ("approved",)),
    )
    rels = db.scalars(q.limit(limit)).all()
    refs = {(r.source_type, r.source_id) for r in rels} | {(r.target_type, r.target_id) for r in rels}
    # Always include concepts and approved principles as nodes even when unconnected
    for c in db.scalars(select(AestheticConcept.id).where(AestheticConcept.brand_id == brand_id)):
        refs.add(("aesthetic_concept", c))
    for p in db.scalars(select(Principle.id).where(Principle.brand_id == brand_id, Principle.status == "approved")):
        refs.add(("principle", p))
    labels = entity_labels(db, list(refs))
    nodes = [
        {"id": f"{t}:{i}", "type": t, "entity_id": str(i), "label": labels.get((t, i), {}).get("label"),
         "status": labels.get((t, i), {}).get("status")}
        for t, i in refs
        if (t, i) in labels
    ]
    edges = [
        {
            "id": str(r.id),
            "source": f"{r.source_type}:{r.source_id}",
            "target": f"{r.target_type}:{r.target_id}",
            "relation_type": r.relation_type,
            "status": r.status,
            "origin": r.origin,
            "weight": jsonable(r.weight),
        }
        for r in rels
    ]
    return {"nodes": nodes, "edges": edges}
