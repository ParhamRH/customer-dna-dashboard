"""AI review queue: interpretations (asset analyses) and suggestions await a human decision.

Approving an analysis makes it the asset's accepted interpretation (asset.approved_analysis_id)
— it never edits official principles. Accepting a suggestion creates a *separate* record
(relationship, draft principle, draft concept…), linked back to the suggestion for provenance.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.api.common import PageParams, jsonable, page_params, paginate, row_to_dict
from app.api.deps import TenantDep
from app.api.errors import NotFound, ValidationFailed
from app.jobs.queue import enqueue
from app.models import AiSuggestion, Asset, AssetAnalysis, AssetTag, Review
from app.services import knowledge as ks
from app.services.assets import load_summaries
from app.services.events import emit
from app.services.graph import create_relationship

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/summary")
def summary(tenant: TenantDep, brand_id: uuid.UUID | None = None) -> dict:
    tenant.require("review.read")
    a = select(AssetAnalysis.analysis_type, func.count()).where(AssetAnalysis.status == "pending_review")
    s = select(AiSuggestion.suggestion_type, func.count()).where(AiSuggestion.status == "pending")
    t = select(func.count()).select_from(AssetTag).where(AssetTag.status == "suggested")
    if brand_id:
        a, s = a.where(AssetAnalysis.brand_id == brand_id), s.where(AiSuggestion.brand_id == brand_id)
        t = t.join(Asset, Asset.id == AssetTag.asset_id).where(Asset.brand_id == brand_id)
    return {
        "analyses": dict(tenant.db.execute(a.group_by(AssetAnalysis.analysis_type)).all()),
        "suggestions": dict(tenant.db.execute(s.group_by(AiSuggestion.suggestion_type)).all()),
        "suggested_tags": tenant.db.scalar(t) or 0,
    }


def _analysis_out(tenant, x: AssetAnalysis, asset_cards: dict[str, Any]) -> dict[str, Any]:  # noqa: ANN001
    d = row_to_dict(x, {"raw_output"})
    d["asset"] = asset_cards.get(str(x.asset_id))
    return d


@router.get("/analyses")
def list_analyses(
    tenant: TenantDep,
    params: PageParams = Depends(page_params),
    status: str = Query("pending_review", pattern="^(pending_review|approved|rejected|superseded)$"),
    brand_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
) -> dict:
    tenant.require("review.read")
    q = select(AssetAnalysis).where(AssetAnalysis.status == status).order_by(AssetAnalysis.created_at.desc())
    if brand_id:
        q = q.where(AssetAnalysis.brand_id == brand_id)
    if asset_id:
        q = q.where(AssetAnalysis.asset_id == asset_id)
    page = paginate(tenant.db, q, params)
    assets = tenant.db.scalars(select(Asset).where(Asset.id.in_([x.asset_id for x in page["items"]]))).all()
    cards = {c["id"]: c for c in load_summaries(tenant.db, list(assets), tenant.org_id)}
    page["items"] = [_analysis_out(tenant, x, cards) for x in page["items"]]
    return page


class AnalysisDecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    notes: str | None = None
    interpretive: dict[str, Any] | None = Field(None, description="Edited interpretation (approve with edits)")
    objective: dict[str, Any] | None = None
    brand_relevance: str | None = Field(None, pattern="^(core|supporting|peripheral|off_brand|unassessed)$")
    accept_suggested_tags: bool = False


@router.post("/analyses/{analysis_id}")
def decide_analysis(analysis_id: uuid.UUID, body: AnalysisDecisionIn, tenant: TenantDep) -> dict:
    tenant.require("review.decide")
    x = tenant.db.scalar(select(AssetAnalysis).where(AssetAnalysis.id == analysis_id))
    if x is None:
        raise NotFound("Analysis not found")
    tenant.check_brand(x.brand_id)
    if x.status not in ("pending_review", "approved", "rejected"):
        raise ValidationFailed(f"Cannot decide a {x.status} analysis")
    asset = tenant.db.scalar(select(Asset).where(Asset.id == x.asset_id))
    edited = bool(body.interpretive or body.objective)
    changes: dict[str, Any] = {}
    now = dt.datetime.now(dt.UTC)
    if body.decision == "approve":
        if body.interpretive:
            changes["interpretive_before"] = x.interpretive
            x.interpretive = body.interpretive
        if body.objective:
            changes["objective_before"] = x.objective
            x.objective = body.objective
        # only one approved interpretation per asset+type
        tenant.db.execute(
            update(AssetAnalysis)
            .where(AssetAnalysis.asset_id == x.asset_id, AssetAnalysis.analysis_type == x.analysis_type,
                   AssetAnalysis.status == "approved", AssetAnalysis.id != x.id)
            .values(status="superseded")
        )
        x.status = "approved"
        asset.approved_analysis_id = x.id
        relevance = body.brand_relevance or (x.interpretive or {}).get("brand_relevance", {}).get("assessment")
        if relevance in ("core", "supporting", "peripheral", "off_brand"):
            asset.brand_relevance = relevance
        if body.accept_suggested_tags:
            tenant.db.execute(update(AssetTag).where(AssetTag.asset_id == asset.id, AssetTag.analysis_id == x.id,
                                                     AssetTag.status == "suggested").values(status="approved"))
    else:
        x.status = "rejected"
        if asset.approved_analysis_id == x.id:
            asset.approved_analysis_id = None
        tenant.db.execute(update(AssetTag).where(AssetTag.asset_id == asset.id, AssetTag.analysis_id == x.id,
                                                 AssetTag.status == "suggested").values(status="rejected"))
    x.reviewed_by, x.reviewed_at, x.review_notes = tenant.user_id, now, body.notes
    decision = "edited_and_accepted" if (edited and body.decision == "approve") else ("approved" if body.decision == "approve" else "rejected")
    tenant.db.add(Review(organization_id=tenant.org_id, brand_id=x.brand_id, subject_type="asset_analysis", subject_id=x.id,
                         decision=decision, notes=body.notes, reviewer_id=tenant.user_id, changes=changes))
    enqueue(tenant.db, tenant.org_id, "asset.embed", brand_id=x.brand_id, entity_type="asset", entity_id=asset.id, priority=120)
    tenant.audit(f"analysis.{body.decision}", "asset_analysis", x.id, {"asset_id": str(asset.id), "edited": edited})
    emit(tenant.db, tenant.org_id, "review.decided", {"subject_type": "asset_analysis", "subject_id": str(x.id), "decision": decision})
    tenant.db.flush()
    return row_to_dict(x, {"raw_output"})


# --- Suggestions --------------------------------------------------------------------------------
@router.get("/suggestions")
def list_suggestions(
    tenant: TenantDep,
    params: PageParams = Depends(page_params),
    status: str = Query("pending", pattern="^(pending|accepted|rejected|superseded)$"),
    suggestion_type: str | None = None,
    brand_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
) -> dict:
    tenant.require("review.read")
    q = select(AiSuggestion).where(AiSuggestion.status == status)
    if suggestion_type:
        q = q.where(AiSuggestion.suggestion_type == suggestion_type)
    if brand_id:
        q = q.where(AiSuggestion.brand_id == brand_id)
    if asset_id:
        q = q.where(AiSuggestion.source_asset_id == asset_id)
    q = q.order_by(AiSuggestion.confidence.desc().nulls_last(), AiSuggestion.created_at.desc())
    page = paginate(tenant.db, q, params, lambda x: row_to_dict(x))
    ids = {i["source_asset_id"] for i in page["items"] if i["source_asset_id"]}
    assets = tenant.db.scalars(select(Asset).where(Asset.id.in_([uuid.UUID(i) for i in ids]))).all() if ids else []
    cards = {c["id"]: c for c in load_summaries(tenant.db, list(assets), tenant.org_id)}
    for i in page["items"]:
        i["asset"] = cards.get(i["source_asset_id"])
    return page


class SuggestionDecisionIn(BaseModel):
    decision: str = Field(pattern="^(accept|reject)$")
    notes: str | None = None
    edits: dict[str, Any] = Field(default_factory=dict, description="Override payload fields before accepting")


def _accept(tenant, s: AiSuggestion, payload: dict[str, Any]) -> tuple[str | None, uuid.UUID | None]:  # noqa: ANN001
    t = s.suggestion_type
    if t == "concept_link":
        tenant.require("knowledge.write")
        rel = create_relationship(
            tenant.db, org_id=tenant.org_id, source_type="asset", source_id=uuid.UUID(payload["asset_id"]),
            relation_type=payload.get("relation_type", "exemplifies"), target_type="aesthetic_concept",
            target_id=uuid.UUID(payload["concept_id"]), origin="ai_suggestion", confidence=float(s.confidence or 0.5),
            created_by=tenant.user_id, source_suggestion_id=s.id,
        )
        return "relationship", rel.id
    if t == "relationship":
        tenant.require("knowledge.write")
        rel = create_relationship(
            tenant.db, org_id=tenant.org_id, source_type=payload["source_type"], source_id=uuid.UUID(payload["source_id"]),
            relation_type=payload["relation_type"], target_type=payload["target_type"], target_id=uuid.UUID(payload["target_id"]),
            origin="ai_suggestion", confidence=float(s.confidence or 0.5), created_by=tenant.user_id, source_suggestion_id=s.id,
        )
        return "relationship", rel.id
    if t == "principle":
        data = {
            "title": payload.get("title") or payload["statement"][:80], "statement": payload["statement"],
            "rationale": payload.get("rationale") or (f"Source: “{payload.get('source_excerpt')}”" if payload.get("source_excerpt") else None),
            "classification": payload.get("classification", "preferred"), "domain_key": payload.get("domain_key"),
            "scope": payload.get("scope") or {}, "examples": payload.get("examples") or {},
        }
        obj = ks.create(tenant, "principle", s.brand_id, data, origin="ai_suggestion", suggestion_id=s.id)
        if s.source_asset_id:
            create_relationship(tenant.db, org_id=tenant.org_id, source_type="principle", source_id=obj.id, relation_type="derived_from",
                                target_type="asset", target_id=s.source_asset_id, origin="ai_suggestion", created_by=tenant.user_id)
        return "principle", obj.id
    if t == "aesthetic_concept":
        data = {"name": payload["name"], "definition": payload.get("definition") or payload["name"],
                "synonyms": payload.get("synonyms") or [], "attributes": payload.get("attributes") or []}
        obj = ks.create(tenant, "aesthetic_concept", s.brand_id, data, origin="ai_suggestion", suggestion_id=s.id)
        if payload.get("example_asset_id"):
            create_relationship(tenant.db, org_id=tenant.org_id, source_type="asset", source_id=uuid.UUID(payload["example_asset_id"]),
                                relation_type="exemplifies", target_type="aesthetic_concept", target_id=obj.id,
                                origin="ai_suggestion", created_by=tenant.user_id, source_suggestion_id=s.id)
        return "aesthetic_concept", obj.id
    if t in ("guideline", "knowledge_entry"):
        obj = ks.create(tenant, t, s.brand_id, payload, origin="ai_suggestion", suggestion_id=s.id)
        return t, obj.id
    if t == "tag":
        tenant.require("assets.write")
        tag = " ".join(str(payload["tag"]).lower().split())[:80]
        existing = tenant.db.scalar(select(AssetTag).where(AssetTag.asset_id == s.source_asset_id, AssetTag.tag == tag))
        if existing:
            existing.status = "approved"
        else:
            tenant.db.add(AssetTag(organization_id=tenant.org_id, asset_id=s.source_asset_id, tag=tag, source="ai", status="approved"))
        return None, None
    raise ValidationFailed(f"Suggestions of type {t!r} cannot be accepted automatically")


@router.post("/suggestions/{suggestion_id}")
def decide_suggestion(suggestion_id: uuid.UUID, body: SuggestionDecisionIn, tenant: TenantDep) -> dict:
    tenant.require("review.decide")
    s = tenant.db.scalar(select(AiSuggestion).where(AiSuggestion.id == suggestion_id))
    if s is None:
        raise NotFound("Suggestion not found")
    tenant.check_brand(s.brand_id)
    if s.status != "pending":
        raise ValidationFailed(f"Suggestion already {s.status}")
    payload = {**(s.payload or {}), **body.edits}
    if body.decision == "accept":
        etype, eid = _accept(tenant, s, payload)
        s.status, s.resolved_entity_type, s.resolved_entity_id = "accepted", etype, eid
    else:
        s.status = "rejected"
    s.reviewed_by, s.reviewed_at = tenant.user_id, dt.datetime.now(dt.UTC)
    decision = "edited_and_accepted" if (body.edits and body.decision == "accept") else ("accepted" if body.decision == "accept" else "rejected")
    tenant.db.add(Review(organization_id=tenant.org_id, brand_id=s.brand_id, subject_type="ai_suggestion", subject_id=s.id,
                         decision=decision, notes=body.notes, reviewer_id=tenant.user_id, changes={"edits": body.edits}))
    tenant.audit(f"suggestion.{body.decision}", "ai_suggestion", s.id, {"type": s.suggestion_type, "resolved": jsonable(s.resolved_entity_id)})
    emit(tenant.db, tenant.org_id, "review.decided", {"subject_type": "ai_suggestion", "subject_id": str(s.id), "decision": decision})
    tenant.db.flush()
    return row_to_dict(s)


class BulkDecisionIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    decision: str = Field(pattern="^(accept|reject)$")


@router.post("/suggestions-bulk")
def bulk_decide(body: BulkDecisionIn, tenant: TenantDep) -> dict:
    results = {"accepted": 0, "rejected": 0, "skipped": 0}
    for sid in body.ids:
        try:
            decide_suggestion(sid, SuggestionDecisionIn(decision=body.decision), tenant)
            results["accepted" if body.decision == "accept" else "rejected"] += 1
        except (ValidationFailed, NotFound):
            results["skipped"] += 1
    return results


@router.get("/history")
def history(tenant: TenantDep, params: PageParams = Depends(page_params), subject_type: str | None = None) -> dict:
    tenant.require("review.read")
    q = select(Review).order_by(Review.created_at.desc())
    if subject_type:
        q = q.where(Review.subject_type == subject_type)
    return paginate(tenant.db, q, params, lambda r: row_to_dict(r))
