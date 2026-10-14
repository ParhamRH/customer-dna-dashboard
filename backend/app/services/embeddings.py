"""Embedding generation and storage for every searchable entity (tenant session only)."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai import registry
from app.media.documents import chunk_text
from app.models import (
    AestheticConcept,
    Asset,
    AssetAnalysis,
    AssetSegment,
    AssetTag,
    Collection,
    Embedding,
    Guideline,
    KnowledgeEntry,
    Principle,
    Project,
)

TEXT_ENTITY_TYPES = ("asset", "principle", "guideline", "aesthetic_concept", "knowledge_entry", "project", "collection", "asset_segment")


def as_floats(v) -> list[float]:  # noqa: ANN001
    """Vector from the DB may arrive as numpy array (ORM) or '[...]' text (raw SQL)."""
    if isinstance(v, str):
        return [float(x) for x in json.loads(v)]
    return [float(x) for x in v]


def vec_literal(v) -> str:  # noqa: ANN001
    """pgvector text literal for a vector-like (list / numpy array / text)."""
    if isinstance(v, str):
        return v
    return "[" + ",".join(f"{float(x):.7g}" for x in v) + "]"


def _hash(text: str, model: str) -> str:
    return hashlib.sha256(f"{model}\x00{text}".encode()).hexdigest()


def store_vectors(
    db: Session,
    *,
    org_id: uuid.UUID,
    brand_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    modality: str,
    embedder,  # noqa: ANN001
    items: list[tuple[int, list[float], str, str | None]],  # (segment, vector, content_hash, preview)
    replace: bool = True,
) -> int:
    if replace:
        db.execute(
            delete(Embedding).where(
                Embedding.entity_type == entity_type,
                Embedding.entity_id == entity_id,
                Embedding.modality == modality,
                Embedding.model == embedder.model,
            )
        )
    for seg, vec, chash, preview in items:
        db.add(
            Embedding(
                organization_id=org_id,
                brand_id=brand_id,
                entity_type=entity_type,
                entity_id=entity_id,
                segment=seg,
                modality=modality,
                provider=embedder.name,
                model=embedder.model,
                dimensions=len(vec),
                embedding=vec,
                content_hash=chash,
                content_preview=(preview or "")[:500] or None,
                is_development_adapter=bool(getattr(embedder, "is_development_adapter", False)),
            )
        )
    db.flush()
    return len(items)


def embed_texts(db: Session, *, org_id, brand_id, entity_type, entity_id, texts: list[str]) -> int:
    texts = [t for t in texts if t and t.strip()]
    if not texts:
        return 0
    embedder = registry.text_embedder(db)
    existing = {
        (e.segment, e.content_hash)
        for e in db.scalars(
            select(Embedding).where(
                Embedding.entity_type == entity_type, Embedding.entity_id == entity_id,
                Embedding.modality == "text", Embedding.model == embedder.model,
            )
        )
    }
    hashes = [_hash(t, embedder.model) for t in texts]
    if existing == set(enumerate(hashes)):
        return 0  # unchanged
    vecs = embedder.embed(texts)
    return store_vectors(
        db, org_id=org_id, brand_id=brand_id, entity_type=entity_type, entity_id=entity_id, modality="text",
        embedder=embedder, items=[(i, v, h, t[:500]) for i, (v, h, t) in enumerate(zip(vecs, hashes, texts, strict=True))],
    )


def embed_images(db: Session, *, org_id, brand_id, entity_type, entity_id, images: list[tuple[int, Path, str]]) -> int:
    """images: (segment, path, preview label)."""
    if not images:
        return 0
    embedder = registry.visual_embedder(db)
    vecs = embedder.embed([p for _, p, _ in images])
    items = []
    for (seg, path, label), v in zip(images, vecs, strict=True):
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        items.append((seg, v, h, label))
    return store_vectors(
        db, org_id=org_id, brand_id=brand_id, entity_type=entity_type, entity_id=entity_id, modality="visual",
        embedder=embedder, items=items,
    )


# --- Text composition per entity --------------------------------------------------------------
def _analysis_text(a: AssetAnalysis | None) -> str:
    if a is None:
        return ""
    o, i = a.objective or {}, a.interpretive or {}
    parts = [
        i.get("summary", ""),
        o.get("description", ""),
        o.get("temporal_description", "") if isinstance(o.get("temporal_description"), str) else "",
        "Atmosphere: " + ", ".join(i.get("atmosphere", [])),
        "Style: " + ", ".join(i.get("visual_style", [])),
        "Photography: " + ", ".join(i.get("photography_characteristics", [])),
        "Concepts: " + ", ".join(c.get("name", "") for c in i.get("aesthetic_concepts", []) if isinstance(c, dict)),
        "Materials: " + ", ".join(o.get("materials", []) if isinstance(o.get("materials"), list) else []),
        "Textures: " + ", ".join(o.get("textures", []) if isinstance(o.get("textures"), list) else []),
        "Geometry: " + ", ".join(o.get("geometry", []) if isinstance(o.get("geometry"), list) else []),
    ]
    light = o.get("lighting") or {}
    if isinstance(light, dict):
        parts.append("Lighting: " + ", ".join(str(v) for v in light.values() if v))
    colors = o.get("colors") or []
    if isinstance(colors, list):
        parts.append("Colors: " + ", ".join(c.get("name", "") for c in colors if isinstance(c, dict)))
    motion = o.get("motion") or {}
    if isinstance(motion, dict) and motion.get("overall_camera_movement"):
        parts.append(f"Camera: {motion.get('overall_camera_movement')}; pace: {motion.get('pace')}")
    return ". ".join(p for p in parts if p and not p.endswith(": "))


def asset_text(db: Session, a: Asset) -> str:
    analysis = None
    if a.approved_analysis_id:
        analysis = db.scalar(select(AssetAnalysis).where(AssetAnalysis.id == a.approved_analysis_id))
    if analysis is None:
        analysis = db.scalar(
            select(AssetAnalysis)
            .where(AssetAnalysis.asset_id == a.id, AssetAnalysis.status.in_(["pending_review", "approved"]))
            .order_by(AssetAnalysis.created_at.desc())
            .limit(1)
        )
    tags = db.scalars(select(AssetTag.tag).where(AssetTag.asset_id == a.id, AssetTag.status == "approved")).all()
    parts = [
        a.title,
        a.description or "",
        f"Type: {a.asset_type}" + (f" / {a.category}" if a.category else "") + (f" / {a.subcategory}" if a.subcategory else ""),
        "Tags: " + ", ".join(tags) if tags else "",
        _analysis_text(analysis),
        json.dumps(a.curated_metadata) if a.curated_metadata else "",
    ]
    return "\n".join(p for p in parts if p)


def entity_texts(db: Session, entity_type: str, obj: Any) -> list[str]:
    if entity_type == "asset":
        return [asset_text(db, obj)]
    if entity_type == "principle":
        ex = obj.examples or {}
        return [
            f"{obj.code} {obj.title}. {obj.statement}\nRationale: {obj.rationale or ''}\n"
            f"Classification: {obj.classification}. Scope: {json.dumps(obj.scope)}\n"
            f"Do: {'; '.join(ex.get('do', []))}\nDon't: {'; '.join(ex.get('dont', []))}"
        ]
    if entity_type == "guideline":
        head = f"{obj.title}. {obj.summary or ''}"
        return [head] + chunk_text(obj.body or "")[:20] if obj.body else [head]
    if entity_type == "aesthetic_concept":
        attrs = ", ".join(
            (a.get("name", "") + (": " + a.get("description", "") if a.get("description") else "")) if isinstance(a, dict) else str(a)
            for a in (obj.attributes or [])
        )
        return [f"{obj.name}. {obj.definition}\nSynonyms: {', '.join(obj.synonyms or [])}\nAttributes: {attrs}"]
    if entity_type == "knowledge_entry":
        head = f"{obj.title}. {obj.summary or ''} {json.dumps(obj.structured) if obj.structured else ''}"
        return [head] + (chunk_text(obj.body)[:20] if obj.body else [])
    if entity_type == "project":
        return [f"{obj.name} ({obj.project_type}). {obj.description or ''} Objectives: {obj.objectives or ''} Audience: {obj.audience or ''}"]
    if entity_type == "collection":
        return [f"{obj.name}. {obj.description or ''}"]
    if entity_type == "asset_segment":
        return [f"{obj.title or ''}\n{obj.text_content or ''}"]
    return []


MODELS = {
    "asset": Asset, "principle": Principle, "guideline": Guideline, "aesthetic_concept": AestheticConcept,
    "knowledge_entry": KnowledgeEntry, "project": Project, "collection": Collection, "asset_segment": AssetSegment,
}


def reindex_text(db: Session, entity_type: str, entity_id: uuid.UUID) -> int:
    model = MODELS[entity_type]
    obj = db.scalar(select(model).where(model.id == entity_id))
    if obj is None:
        return 0
    brand_id = obj.brand_id if hasattr(obj, "brand_id") else db.scalar(select(Asset.brand_id).where(Asset.id == obj.asset_id))
    return embed_texts(
        db, org_id=obj.organization_id, brand_id=brand_id, entity_type=entity_type, entity_id=entity_id,
        texts=entity_texts(db, entity_type, obj),
    )
