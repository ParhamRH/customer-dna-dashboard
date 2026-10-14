"""Hybrid, tenant-scoped, approval-aware retrieval.

Signals (each produces a ranked list; fused with weighted Reciprocal Rank Fusion):
  keyword       PostgreSQL full-text (english stems + simple tokens), trigram titles, tags
  semantic      pgvector cosine over text embeddings (same model as the indexed content)
  relationship  entities linked (approved edges) to concepts/principles named in the query
  metadata      objective measurements matching attributes in the query (muted, slow camera…)
  visual        image-embedding similarity (query-by-example)
Tenant isolation: every query runs on the RLS-enforced session (no cross-tenant rows can exist
in any candidate list); brand filters are additionally applied explicitly.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.ai import registry
from app.models import (
    AestheticConcept,
    Asset,
    AssetSegment,
    AssetTag,
    Collection,
    Guideline,
    KnowledgeEntry,
    Principle,
    Project,
    Relationship,
)
from app.search.query_parser import ParsedQuery, or_query, parse
from app.services.embeddings import as_floats, vec_literal

RRF_K = 60
WEIGHTS = {"keyword": 1.0, "semantic": 1.25, "relationship": 1.1, "metadata": 0.7, "visual": 1.25}
# Approval-aware ranking is a *mild* preference: official knowledge wins ties, it never
# outranks a clearly more relevant item. Use scope="official" to exclude non-approved content.
STATUS_WEIGHT = {"official": 1.0, "inspiration": 0.99, "external": 0.99, "pending": 0.985, "historical": 0.9}
ENTITY_TYPES = ("asset", "principle", "guideline", "aesthetic_concept", "knowledge_entry", "project", "collection")

MODELS = {
    "asset": Asset, "principle": Principle, "guideline": Guideline, "aesthetic_concept": AestheticConcept,
    "knowledge_entry": KnowledgeEntry, "project": Project, "collection": Collection,
}


@dataclass
class SearchRequest:
    query: str = ""
    brand_id: uuid.UUID | None = None
    entity_types: list[str] = field(default_factory=lambda: list(ENTITY_TYPES))
    asset_types: list[str] = field(default_factory=list)
    reference_roles: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    concept_ids: list[uuid.UUID] = field(default_factory=list)
    principle_ids: list[uuid.UUID] = field(default_factory=list)
    domain_keys: list[str] = field(default_factory=list)
    scope: str = "all"  # all | official | pending
    include_historical: bool = True
    limit: int = 20
    explain: bool = False
    parse_query: bool = True


@dataclass
class Candidate:
    entity_type: str
    entity_id: uuid.UUID
    signals: dict[str, dict[str, Any]] = field(default_factory=dict)
    matched_segments: list[dict[str, Any]] = field(default_factory=list)


def _set_ef(db: Session) -> None:
    db.execute(text("SET LOCAL hnsw.ef_search = 200"))


# --- Signal generators ---------------------------------------------------------------------------
def keyword_hits(db: Session, req: SearchRequest, terms: str, limit: int = 60) -> list[tuple[str, uuid.UUID, float]]:
    if not terms.strip():
        return []
    tsq = func.bdna_tsq(or_query(terms) or terms)
    hits: list[tuple[str, uuid.UUID, float]] = []
    for etype in req.entity_types:
        model = MODELS[etype]
        if etype == "collection":
            q = select(model.id, func.similarity(model.name, terms)).where(
                or_(model.name.ilike(f"%{terms}%"), model.description.ilike(f"%{terms}%"))
            )
        else:
            q = select(model.id, func.ts_rank_cd(model.search_tsv, tsq)).where(model.search_tsv.op("@@")(tsq))
        if req.brand_id:
            q = q.where(model.brand_id == req.brand_id)
        if etype == "asset":
            q = q.where(Asset.deleted_at.is_(None))
        hits += [(etype, i, float(s or 0)) for i, s in db.execute(q.order_by(text("2 DESC")).limit(limit)).all()]
    if "asset" in req.entity_types:
        tag_q = (
            select(AssetTag.asset_id, func.max(func.similarity(AssetTag.tag, terms)))
            .join(Asset, Asset.id == AssetTag.asset_id)
            .where(AssetTag.status == "approved", Asset.deleted_at.is_(None),
                   or_(*[AssetTag.tag.ilike(f"%{w}%") for w in terms.lower().split()[:8]]))
            .group_by(AssetTag.asset_id)
        )
        if req.brand_id:
            tag_q = tag_q.where(Asset.brand_id == req.brand_id)
        hits += [("asset", i, float(s or 0) * 0.5) for i, s in db.execute(tag_q.limit(limit)).all()]
    hits.sort(key=lambda h: -h[2])
    return hits


def semantic_hits(db: Session, req: SearchRequest, query_text: str, limit: int = 80) -> list[tuple[str, uuid.UUID, float, int, str]]:
    if not query_text.strip():
        return []
    embedder = registry.text_embedder(db)
    vec = embedder.embed([query_text])[0]
    d = len(vec)
    types = list(req.entity_types) + (["asset_segment"] if "asset" in req.entity_types else [])
    _set_ef(db)
    sql = f"""
        SELECT entity_type, entity_id, segment, 1 - ((embedding::vector({d})) <=> CAST(:q AS vector({d}))) AS sim
          FROM embeddings
         WHERE modality = 'text' AND model = :model AND dimensions = :d AND entity_type = ANY(:types)
               {"AND brand_id = :brand" if req.brand_id else ""}
         ORDER BY (embedding::vector({d})) <=> CAST(:q AS vector({d}))
         LIMIT :k"""
    rows = db.execute(
        text(sql), {"q": vec_literal(vec), "model": embedder.model, "d": d, "types": types, "brand": req.brand_id, "k": limit}
    ).all()
    return [(r[0], r[1], float(r[3]), r[2], embedder.model) for r in rows]


def relationship_hits(db: Session, req: SearchRequest, pq: ParsedQuery) -> tuple[list[tuple[str, uuid.UUID, float]], list[dict[str, Any]]]:
    """Concepts/principles named in the query (or given as filters) -> entities linked to them."""
    matched: list[tuple[str, uuid.UUID, str]] = []
    low = f" {pq.raw.lower()} "
    q = select(AestheticConcept).where(AestheticConcept.status.not_in(["rejected", "archived"]))
    if req.brand_id:
        q = q.where(AestheticConcept.brand_id == req.brand_id)
    for c in db.scalars(q):
        names = [c.name, *(c.synonyms or [])]
        if any(f" {n.lower()} " in low or (len(n) > 5 and n.lower() in low) for n in names if n):
            matched.append(("aesthetic_concept", c.id, c.name))
    pq_codes = [w.upper() for w in pq.raw.replace(",", " ").split() if w.upper().startswith("P-")]
    if pq_codes:
        pr = select(Principle).where(Principle.code.in_(pq_codes))
        if req.brand_id:
            pr = pr.where(Principle.brand_id == req.brand_id)
        matched += [("principle", p.id, p.code) for p in db.scalars(pr)]
    matched += [("aesthetic_concept", i, "filter") for i in req.concept_ids]
    matched += [("principle", i, "filter") for i in req.principle_ids]
    if not matched:
        return [], []
    hits: dict[tuple[str, uuid.UUID], float] = {}
    for etype, eid, _ in matched:
        hits[(etype, eid)] = max(hits.get((etype, eid), 0), 1.0)
        rels = db.scalars(
            select(Relationship).where(
                Relationship.status == "approved",
                or_(
                    (Relationship.target_type == etype) & (Relationship.target_id == eid),
                    (Relationship.source_type == etype) & (Relationship.source_id == eid),
                ),
            )
        ).all()
        for r in rels:
            other = (r.source_type, r.source_id) if r.target_id == eid else (r.target_type, r.target_id)
            if other[0] in req.entity_types:
                w = float(r.weight or 1) * (0.6 if r.relation_type == "opposes" else 1.0)
                if r.relation_type == "opposes":
                    continue
                hits[other] = max(hits.get(other, 0), w)
    ranked = sorted(((t, i, s) for (t, i), s in hits.items()), key=lambda h: -h[2])
    return ranked, [{"type": t, "id": str(i), "label": label} for t, i, label in matched]


def _metric(meta: dict[str, Any], path: str) -> Any:
    cur: Any = meta
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def metadata_hits(db: Session, req: SearchRequest, pq: ParsedQuery, limit: int = 400) -> list[tuple[str, uuid.UUID, float]]:
    if not pq.attributes or "asset" not in req.entity_types:
        return []
    q = select(Asset.id, Asset.media_metadata).where(Asset.deleted_at.is_(None))
    if req.brand_id:
        q = q.where(Asset.brand_id == req.brand_id)
    if req.asset_types:
        q = q.where(Asset.asset_type.in_(req.asset_types))
    out = []
    for aid, meta in db.execute(q.limit(5000)).all():
        score = 0.0
        for path, op, thr, _label in pq.attributes:
            v = _metric(meta or {}, path)
            if v is None:
                continue
            if op == "=" and v == thr:
                score += 1
            elif op == "<" and isinstance(v, int | float) and v < thr:
                score += 1 + min(1.0, (thr - v) / (abs(thr) + 0.2))
            elif op == ">" and isinstance(v, int | float) and v > thr:
                score += 1 + min(1.0, (v - thr) / (abs(thr) + 0.2))
        if score > 0:
            out.append(("asset", aid, score))
    out.sort(key=lambda h: -h[2])
    return out[:limit]


def visual_hits(db: Session, req: SearchRequest, vector: list[float], model: str, exclude: uuid.UUID | None = None,
                limit: int = 60) -> list[tuple[str, uuid.UUID, float]]:
    d = len(vector)
    _set_ef(db)
    sql = f"""
        SELECT entity_id, max(1 - ((embedding::vector({d})) <=> CAST(:q AS vector({d})))) AS sim
          FROM embeddings
         WHERE modality = 'visual' AND model = :model AND dimensions = :d AND entity_type = 'asset'
               {"AND brand_id = :brand" if req.brand_id else ""} {"AND entity_id <> :ex" if exclude else ""}
         GROUP BY entity_id ORDER BY sim DESC LIMIT :k"""
    rows = db.execute(text(sql), {"q": vec_literal(vector), "model": model, "d": d, "brand": req.brand_id, "ex": exclude, "k": limit}).all()
    return [("asset", r[0], float(r[1])) for r in rows]


# --- Fusion & hydration --------------------------------------------------------------------------
def _fuse(lists: dict[str, list[tuple[str, uuid.UUID, float]]], segs: dict[tuple[str, uuid.UUID], list[dict[str, Any]]]) -> dict[tuple[str, uuid.UUID], Candidate]:
    """Hybrid fusion: per signal, half reciprocal-rank (robust across heterogeneous scorers) and half
    max-normalised score (keeps genuine score gaps, e.g. an exact visual match)."""
    cands: dict[tuple[str, uuid.UUID], Candidate] = {}
    for signal, hits in lists.items():
        seen: set[tuple[str, uuid.UUID]] = set()
        rank = 0
        top = max((h[2] for h in hits), default=0.0) or 1.0
        for etype, eid, score in hits:
            key = (etype, eid)
            if key in seen:
                continue
            seen.add(key)
            rank += 1
            c = cands.setdefault(key, Candidate(etype, eid))
            fused = 0.5 * (RRF_K + 1) / (RRF_K + rank) + 0.5 * max(0.0, score) / top
            c.signals[signal] = {"rank": rank, "score": round(score, 4), "fused": round(fused, 4)}
    for key, s in segs.items():
        if key in cands:
            cands[key].matched_segments = s
    return cands


def _knowledge_status(etype: str, row: Any) -> str:
    if etype == "asset":
        if row.reference_role == "historical":
            return "historical"
        if row.approval_status == "approved":
            return {"official": "official", "inspiration": "inspiration", "external": "external"}.get(row.reference_role, "official")
        return "pending"
    st = getattr(row, "status", None)
    if st in ("approved", "active", "completed"):
        return "official"
    if st in ("deprecated", "archived"):
        return "historical"
    return "pending"


def _passes(etype: str, row: Any, req: SearchRequest, pq: ParsedQuery, tag_map: dict[uuid.UUID, set[str]]) -> bool:
    status = getattr(row, "status", None) or getattr(row, "approval_status", None)
    if status in ("rejected",):
        return False
    if etype == "asset":
        if row.deleted_at is not None:
            return False
        types = req.asset_types or pq.asset_types
        if types and row.asset_type not in types:
            return False
        roles = req.reference_roles or pq.reference_roles
        if roles and row.reference_role not in roles:
            return False
        if req.tags and not set(req.tags) <= tag_map.get(row.id, set()):
            return False
    if req.domain_keys and hasattr(row, "domain_key") and row.domain_key not in req.domain_keys:
        return False
    ks = _knowledge_status(etype, row)
    scope = "official" if (req.scope == "official" or pq.approved_only) else "pending" if (req.scope == "pending" or pq.pending_only) else "all"
    if scope == "official" and ks == "pending":
        return False
    if scope == "pending" and ks != "pending":
        return False
    if not req.include_historical and ks == "historical":
        return False
    return True


def _snippet(etype: str, row: Any) -> str:
    for attr in ("statement", "definition", "summary", "description", "body"):
        v = getattr(row, attr, None)
        if v:
            return str(v)[:280]
    return ""


def _title(etype: str, row: Any) -> str:
    if etype == "principle":
        return f"{row.code} · {row.title}"
    return getattr(row, "title", None) or getattr(row, "name", None) or ""


def search(db: Session, org_id: uuid.UUID, req: SearchRequest, *, query_image: Path | None = None,
           example_asset_id: uuid.UUID | None = None) -> dict[str, Any]:
    pq = parse(req.query) if (req.parse_query and req.query) else ParsedQuery(raw=req.query, text=req.query)
    if req.parse_query and pq.entity_types and req.entity_types == list(ENTITY_TYPES):
        req.entity_types = list(dict.fromkeys(pq.entity_types + (["asset"] if pq.asset_types else [])))
    if req.parse_query and (pq.asset_types or pq.reference_roles) and req.entity_types == list(ENTITY_TYPES):
        req.entity_types = ["asset"]
    lists: dict[str, list[tuple[str, uuid.UUID, float]]] = {}
    seg_matches: dict[tuple[str, uuid.UUID], list[dict[str, Any]]] = defaultdict(list)
    matched_entities: list[dict[str, Any]] = []
    model_used = None
    if req.query:
        lists["keyword"] = keyword_hits(db, req, pq.text)
        sem = semantic_hits(db, req, pq.text if len(pq.text) > 2 else req.query)
        model_used = sem[0][4] if sem else None
        sem_list: list[tuple[str, uuid.UUID, float]] = []
        seg_ids = [eid for t, eid, *_ in sem if t == "asset_segment"]
        seg_parent = {}
        if seg_ids:
            for s in db.scalars(select(AssetSegment).where(AssetSegment.id.in_(seg_ids))):
                seg_parent[s.id] = s
        for etype, eid, sim, segment, _ in sem:
            if etype == "asset_segment":
                s = seg_parent.get(eid)
                if s is None:
                    continue
                seg_matches[("asset", s.asset_id)].append(
                    {"segment_type": s.segment_type, "index": s.segment_index, "page_number": s.page_number,
                     "start_ms": s.start_ms, "title": s.title, "excerpt": (s.text_content or "")[:240], "similarity": round(sim, 4)}
                )
                sem_list.append(("asset", s.asset_id, sim))
            else:
                sem_list.append((etype, eid, sim))
        lists["semantic"] = sorted(sem_list, key=lambda h: -h[2])
        rel, matched_entities = relationship_hits(db, req, pq)
        lists["relationship"] = rel
        lists["metadata"] = metadata_hits(db, req, pq)
        if pq.project_types and "guideline" in req.entity_types:
            gl = []
            for g in db.scalars(select(Guideline).where(Guideline.brand_id == req.brand_id) if req.brand_id else select(Guideline)):
                pts = (g.applies_to or {}).get("project_types", [])
                if set(pts) & set(pq.project_types):
                    gl.append(("guideline", g.id, 1.0))
            for p in db.scalars(select(Principle).where(Principle.brand_id == req.brand_id) if req.brand_id else select(Principle)):
                pts = (p.scope or {}).get("project_types", [])
                if set(pts) & set(pq.project_types):
                    gl.append(("principle", p.id, 0.9))
            lists["metadata"] = lists["metadata"] + gl
    elif req.concept_ids or req.principle_ids:
        lists["relationship"], matched_entities = relationship_hits(db, req, pq)
    if query_image is not None or example_asset_id is not None:
        embedder = registry.visual_embedder(db)
        if query_image is not None:
            vec = embedder.embed([query_image])[0]
        else:
            row = db.execute(
                text("SELECT embedding FROM embeddings WHERE entity_type='asset' AND entity_id=:i AND modality='visual' AND model=:m ORDER BY segment LIMIT 1"),
                {"i": example_asset_id, "m": embedder.model},
            ).first()
            vec = as_floats(row[0]) if row else None
        if vec is not None:
            lists["visual"] = visual_hits(db, req, vec, embedder.model, exclude=example_asset_id)
    cands = _fuse(lists, seg_matches)
    # hydrate
    by_type: dict[str, list[uuid.UUID]] = defaultdict(list)
    for (t, i) in cands:
        if t in MODELS:
            by_type[t].append(i)
    rows: dict[tuple[str, uuid.UUID], Any] = {}
    for t, ids in by_type.items():
        for r in db.scalars(select(MODELS[t]).where(MODELS[t].id.in_(ids))):
            rows[(t, r.id)] = r
    asset_ids = [i for (t, i) in rows if t == "asset"]
    tag_map: dict[uuid.UUID, set[str]] = defaultdict(set)
    if asset_ids:
        for aid, tag in db.execute(select(AssetTag.asset_id, AssetTag.tag).where(AssetTag.asset_id.in_(asset_ids), AssetTag.status == "approved")):
            tag_map[aid].add(tag)
    results = []
    for key, c in cands.items():
        row = rows.get(key)
        if row is None or c.entity_type not in req.entity_types:
            continue
        if req.brand_id and getattr(row, "brand_id", None) != req.brand_id:
            continue
        if not _passes(c.entity_type, row, req, pq, tag_map):
            continue
        fused = sum(WEIGHTS[s] * v["fused"] for s, v in c.signals.items())
        ks = _knowledge_status(c.entity_type, row)
        score = fused * STATUS_WEIGHT.get(ks, 0.7)
        results.append((score, c, row, ks))
    results.sort(key=lambda r: -r[0])
    top = results[: req.limit]
    max_score = top[0][0] if top else 1.0
    from app.services.assets import load_summaries

    asset_cards = {s["id"]: s for s in load_summaries(db, [r for _, c, r, _ in top if c.entity_type == "asset"], org_id)}
    items = []
    for score, c, row, ks in top:
        item = {
            "entity_type": c.entity_type,
            "id": str(c.entity_id),
            "brand_id": str(row.brand_id),
            "title": _title(c.entity_type, row),
            "snippet": _snippet(c.entity_type, row),
            "score": round(score / max_score, 4),
            "knowledge_status": ks,
            "status": getattr(row, "status", None) or getattr(row, "approval_status", None),
            "matched_segments": sorted(c.matched_segments, key=lambda s: -s["similarity"])[:3],
        }
        if c.entity_type == "asset":
            item["asset"] = asset_cards.get(str(c.entity_id))
        if c.entity_type == "principle":
            item["classification"] = row.classification
        if req.explain:
            item["signals"] = c.signals
        items.append(item)
    return {
        "query": req.query,
        "interpreted": {
            "text": pq.text,
            "asset_types": pq.asset_types,
            "entity_types": req.entity_types,
            "approved_only": pq.approved_only or req.scope == "official",
            "attributes": [a[3] for a in pq.attributes],
            "project_types": pq.project_types,
            "matched_entities": matched_entities,
        },
        "embedding_model": model_used,
        "signals_used": [k for k, v in lists.items() if v],
        "total_candidates": len(results),
        "items": items,
    }


def similar_to_asset(db: Session, org_id: uuid.UUID, asset: Asset, modality: str, limit: int) -> list[dict[str, Any]]:
    req = SearchRequest(brand_id=asset.brand_id, entity_types=["asset"], limit=limit)
    if modality == "visual":
        res = search(db, org_id, req, example_asset_id=asset.id)
        return res["items"]
    embedder = registry.text_embedder(db)
    row = db.execute(
        text("SELECT embedding, dimensions FROM embeddings WHERE entity_type='asset' AND entity_id=:i AND modality='text' AND model=:m AND segment=0"),
        {"i": asset.id, "m": embedder.model},
    ).first()
    if row is None:
        return []
    d = row[1]
    rows = db.execute(
        text(f"""SELECT entity_id, 1 - ((embedding::vector({d})) <=> CAST(:q AS vector({d}))) AS sim FROM embeddings
                 WHERE entity_type='asset' AND modality='text' AND model=:m AND dimensions=:d AND brand_id=:b AND entity_id<>:i AND segment=0
                 ORDER BY (embedding::vector({d})) <=> CAST(:q AS vector({d})) LIMIT :k"""),
        {"q": vec_literal(row[0]), "m": embedder.model, "d": d, "b": asset.brand_id, "i": asset.id, "k": limit},
    ).all()
    assets = {a.id: a for a in db.scalars(select(Asset).where(Asset.id.in_([r[0] for r in rows]), Asset.deleted_at.is_(None)))}
    from app.services.assets import load_summaries

    cards = {c["id"]: c for c in load_summaries(db, list(assets.values()), org_id)}
    return [
        {"entity_type": "asset", "id": str(i), "title": assets[i].title, "score": round(float(s), 4), "asset": cards.get(str(i)),
         "knowledge_status": _knowledge_status("asset", assets[i])}
        for i, s in rows if i in assets
    ]


def related_entities(db: Session, entity_type: str, entity_id: uuid.UUID, depth: int = 1,
                     relation_types: list[str] | None = None) -> list[dict[str, Any]]:
    """Breadth-first walk over approved relationships (depth 1 or 2)."""
    from app.services.graph import entity_labels

    frontier = {(entity_type, entity_id)}
    seen = {(entity_type, entity_id)}
    found: dict[tuple[str, uuid.UUID], dict[str, Any]] = {}
    for hop in range(1, max(1, min(depth, 3)) + 1):
        nxt = set()
        for t, i in frontier:
            q = select(Relationship).where(
                Relationship.status == "approved",
                or_((Relationship.source_type == t) & (Relationship.source_id == i),
                    (Relationship.target_type == t) & (Relationship.target_id == i)),
            )
            if relation_types:
                q = q.where(Relationship.relation_type.in_(relation_types))
            for r in db.scalars(q):
                other = (r.target_type, r.target_id) if (r.source_type, r.source_id) == (t, i) else (r.source_type, r.source_id)
                if other in seen:
                    continue
                seen.add(other)
                nxt.add(other)
                found[other] = {"hop": hop, "via": r.relation_type, "from": f"{t}:{i}"}
        frontier = nxt
    labels = entity_labels(db, list(found))
    return [
        {"entity_type": t, "id": str(i), "label": labels.get((t, i), {}).get("label"),
         "status": labels.get((t, i), {}).get("status"), **meta}
        for (t, i), meta in sorted(found.items(), key=lambda kv: kv[1]["hop"])
        if (t, i) in labels
    ]
