"""Phase 4/5: human review of AI output and governed brand knowledge."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.jobs.queue import drain
from tests.conftest import Api
from tests.media_fixtures import upload


@pytest.fixture(scope="module")
def b(customers):
    return customers["B"]


@pytest.fixture(scope="module")
def processed(b):
    ids = {}
    for name in ("organic.jpg", "guidelines.pdf", "architectural.jpg"):
        r = upload(b.users["editor"], b.brand_id, name)
        assert r.status_code == 201, r.text
        ids[name] = r.json()["id"]
    drain()
    return ids


def test_reviewer_approves_analysis_with_edits(b, processed):
    rv = b.users["reviewer"]
    q = rv.get("/v1/review/analyses", params={"asset_id": processed["organic.jpg"]}).json()
    assert q["total"] == 1
    analysis = q["items"][0]
    edited = {**analysis["interpretive"], "summary": "Warm, calm organic study — approved reference."}
    r = rv.post(f"/v1/review/analyses/{analysis['id']}",
                json={"decision": "approve", "interpretive": edited, "brand_relevance": "core", "accept_suggested_tags": True})
    assert r.status_code == 200, r.text
    asset = rv.get(f"/v1/assets/{processed['organic.jpg']}").json()
    assert asset["approved_analysis_id"] == analysis["id"]
    assert asset["brand_relevance"] == "core"
    assert all(t["status"] == "approved" for t in asset["tag_details"] if t["source"] == "ai")
    hist = b.admin.get("/v1/review/history", params={"subject_type": "asset_analysis"}).json()["items"]
    assert hist[0]["decision"] == "edited_and_accepted" and "interpretive_before" in hist[0]["changes"]
    # the original AI output is preserved separately from the human-edited interpretation
    assert b.users["viewer"].get("/v1/review/analyses").status_code == 403


def test_reject_analysis(b, processed):
    rv = b.users["reviewer"]
    a = rv.get("/v1/review/analyses", params={"asset_id": processed["architectural.jpg"]}).json()["items"][0]
    assert rv.post(f"/v1/review/analyses/{a['id']}", json={"decision": "reject", "notes": "too generic"}).json()["status"] == "rejected"


def test_principle_suggestion_becomes_draft_then_human_approval(b, processed, client):
    cd, rv = b.users["creative_director"], b.users["reviewer"]
    sug = rv.get("/v1/review/suggestions", params={"suggestion_type": "principle", "asset_id": processed["guidelines.pdf"]}).json()["items"]
    target = next(s for s in sug if s["payload"]["classification"] == "prohibited")
    # reviewer may decide suggestions but lacks knowledge.write → creating a principle is forbidden
    assert rv.post(f"/v1/review/suggestions/{target['id']}", json={"decision": "accept"}).status_code == 403
    r = cd.post(f"/v1/review/suggestions/{target['id']}", json={"decision": "accept", "edits": {"title": "No harsh flash"}})
    assert r.status_code == 200, r.text
    assert r.json()["resolved_entity_type"] == "principle"
    pid = r.json()["resolved_entity_id"]
    p = cd.get(f"/v1/knowledge/principles/{pid}").json()
    assert p["status"] == "draft" and p["origin"] == "ai_suggestion" and p["title"] == "No harsh flash"
    assert p["code"].startswith("P-")
    assert any(rel["relation_type"] == "derived_from" and rel["other_id"] == processed["guidelines.pdf"] for rel in p["relationships"])
    # not official yet → absent from the official bundle
    bundle = cd.get(f"/v1/brands/{b.brand_id}/guidelines").json()
    assert pid not in {x["id"] for x in bundle["principles"]}
    # reviewers cannot make official knowledge; API tokens cannot either (human-only)
    assert rv.post(f"/v1/knowledge/principles/{pid}/approve").status_code == 403
    tok = b.admin.post("/v1/workspace/api-tokens", json={"name": "cd-token", "role": "creative_director"}).json()["token"]
    assert Api(client, tok).post(f"/v1/knowledge/principles/{pid}/approve").status_code == 403
    r = cd.post(f"/v1/knowledge/principles/{pid}/approve", json={"notes": "agreed"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    bundle = cd.get(f"/v1/brands/{b.brand_id}/guidelines").json()
    assert pid in {x["id"] for x in bundle["principles"]}


def test_versioning_keeps_last_approved_version_official(b):
    cd = b.users["creative_director"]
    r = cd.post(f"/v1/brands/{b.brand_id}/knowledge/principles",
                json={"title": "Daylight first", "statement": "Use natural daylight.", "classification": "mandatory",
                      "domain_key": "art_direction", "examples": {"do": ["window light"], "dont": ["ring lights"]}})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    cd.post(f"/v1/knowledge/principles/{pid}/approve")
    r = cd.patch(f"/v1/knowledge/principles/{pid}", json={"statement": "Use natural daylight or daylight-balanced LEDs.", "change_note": "allow LEDs"})
    p = r.json()
    assert p["version"] == 2 and p["status"] == "draft" and p["official_version"] == 1
    bundle = cd.get(f"/v1/brands/{b.brand_id}/guidelines").json()
    official = next(x for x in bundle["principles"] if x["id"] == pid)
    assert official["statement"] == "Use natural daylight." and official["has_newer_draft"] is True
    revs = cd.get(f"/v1/knowledge/principles/{pid}/revisions").json()["items"]
    assert [(r["version"], r["approved"]) for r in revs] == [(2, False), (1, True)]
    cd.post(f"/v1/knowledge/principles/{pid}/approve")
    official = next(x for x in cd.get(f"/v1/brands/{b.brand_id}/guidelines").json()["principles"] if x["id"] == pid)
    assert "LEDs" in official["statement"]
    assert cd.delete(f"/v1/knowledge/principles/{pid}").status_code == 422  # approved knowledge keeps its history


def test_concepts_ontology(b, processed):
    cd, editor = b.users["creative_director"], b.users["editor"]
    assert editor.post(f"/v1/brands/{b.brand_id}/knowledge/concepts", json={"name": "x", "definition": "y"}).status_code == 403
    base = f"/v1/brands/{b.brand_id}/knowledge/concepts"
    brutal = cd.post(base, json={"name": "Brutalist aesthetics", "definition": "Raw, heavy, monumental concrete forms."}).json()
    minimal = cd.post(base, json={"name": "Sculptural minimalism", "definition": "Reduced, calm, sculptural volumes."}).json()
    organic = cd.post(base, json={
        "name": "Organic geometry", "definition": "Curvilinear, biomorphic forms derived from nature, soft-edged and flowing.",
        "synonyms": ["biomorphic forms", "curvilinear geometry"], "attributes": [{"name": "curvature", "description": "soft"}],
        "brand_relevance": "core", "related_concept_ids": [minimal["id"]], "opposing_concept_ids": [brutal["id"]],
        "example_asset_ids": [processed["organic.jpg"]],
    }).json()
    assert organic["slug"] == "organic-geometry"
    assert [c["other_label"] for c in organic["related_concepts"]] == ["Sculptural minimalism"]
    assert [c["other_label"] for c in organic["opposing_concepts"]] == ["Brutalist aesthetics"]
    assert [a["id"] for a in organic["example_assets"]] == [processed["organic.jpg"]]
    listed = b.users["viewer"].get("/v1/assets", params={"concept_id": organic["id"]}).json()
    assert [i["id"] for i in listed["items"]] == [processed["organic.jpg"]]
    r = cd.post(f"/v1/knowledge/concepts/{organic['id']}/approve")
    assert r.json()["status"] == "approved"


def test_concept_link_suggestion_creates_relationship(b, processed):
    cd = b.users["creative_director"]
    # re-run ingestion now that the vocabulary exists → concept-link suggestions appear
    cd.post(f"/v1/assets/{processed['architectural.jpg']}/reprocess", json={})
    cd.post(f"/v1/assets/{processed['organic.jpg']}/reprocess", json={})
    drain()
    sug = cd.get("/v1/review/suggestions", params={"suggestion_type": "concept_link"}).json()["items"]
    assert sug, "expected concept-link suggestions"
    s = sug[0]
    r = cd.post(f"/v1/review/suggestions/{s['id']}", json={"decision": "accept"})
    assert r.status_code == 200 and r.json()["resolved_entity_type"] == "relationship"
    rels = cd.get(f"/v1/entities/aesthetic_concept/{s['payload']['concept_id']}/relationships").json()["items"]
    assert any(x["other_id"] == s["payload"]["asset_id"] and x["origin"] == "ai_suggestion" and x["status"] == "approved" for x in rels)


def test_knowledge_entries_and_structured_validation(b):
    cd = b.users["creative_director"]
    base = f"/v1/brands/{b.brand_id}/knowledge/entries"
    bad = cd.post(base, json={"domain_key": "brand_language", "entry_type": "tone_of_voice", "title": "Tone", "structured": {"traits": "warm"}})
    assert bad.status_code == 422
    bad = cd.post(base, json={"domain_key": "brand_language", "entry_type": "no_such_type", "title": "x"})
    assert bad.status_code == 422
    ok = cd.post(base, json={"domain_key": "brand_language", "entry_type": "tone_of_voice", "title": "Tone of voice",
                             "body": "Warm, precise, never shouty.",
                             "structured": {"traits": [{"trait": "warm", "is": "generous", "is_not": "saccharine"}]}})
    assert ok.status_code == 201, ok.text
    ok = cd.post(base, json={"domain_key": "art_direction", "entry_type": "lighting", "title": "Lighting",
                             "structured": {"objective_observations": ["soft side light"], "aesthetic_interpretation": "calm, intimate"}})
    assert ok.status_code == 201
    view = cd.get(f"/v1/brands/{b.brand_id}/domains/art_direction").json()
    assert view["entries"][0]["structured"]["objective_observations"] == ["soft side light"]
    y = cd.get(f"/v1/knowledge/entries/{ok.json()['id']}/export", params={"format": "yaml"})
    assert y.status_code == 200 and "objective_observations" in y.text


def test_visual_identity_colors_typography_tokens(b):
    cd = b.users["creative_director"]
    pal = cd.post(f"/v1/brands/{b.brand_id}/palettes", json={"name": "Core", "role": "primary", "status": "approved"}).json()
    ink = cd.post(f"/v1/palettes/{pal['id']}/colors", json={"name": "Ink", "hex": "#1B1F2A", "usage": "Text and logo"}).json()
    sand = cd.post(f"/v1/palettes/{pal['id']}/colors", json={"name": "Sand", "hex": "#E9E1D4", "cmyk": {"c": 0, "m": 4, "y": 12, "k": 9}}).json()
    assert ink["oklch"]["css"].startswith("oklch(") and ink["token_key"] == "color.primary.ink"
    assert sand["cmyk_is_manual"] is True and sand["cmyk"]["approximate"] is False
    assert b.users["editor"].post(f"/v1/brands/{b.brand_id}/palettes", json={"name": "x", "role": "accent", "status": "approved"}).status_code == 403
    acc = cd.get(f"/v1/brands/{b.brand_id}/palettes").json()["accessibility"]
    assert acc[0]["ratio"] > 10 and acc[0]["AAA_normal"] is True
    cd.post(f"/v1/brands/{b.brand_id}/typography", json={
        "name": "Display", "role": "display", "family": "Canela", "fallback_stack": "Georgia, serif", "status": "approved",
        "weights": [300, 400], "hierarchy": [{"level": "h1", "size_px": 64, "line_height": 1.05, "weight": 300}]})
    cd.post(f"/v1/brands/{b.brand_id}/design-tokens", json={"path": "spacing.4", "token_type": "dimension", "value": "16px",
                                                              "category": "spacing", "status": "approved"})
    css = cd.get(f"/v1/brands/{b.brand_id}/design-tokens/export", params={"format": "css"}).text
    assert "--color-primary-ink: #1b1f2a;" in css and "--spacing-4: 16px;" in css and "--typography-h1-font-size: 64px;" in css
    dtcg = cd.get(f"/v1/brands/{b.brand_id}/design-tokens/export").json()
    assert dtcg["color"]["primary"]["ink"]["$type"] == "color"
    tw = cd.get(f"/v1/brands/{b.brand_id}/design-tokens/export", params={"format": "tailwind"}).text
    assert '"ink": "#1b1f2a"' in tw


def test_brand_version_snapshot_is_immutable(b):
    cd = b.users["creative_director"]
    r = cd.post(f"/v1/brands/{b.brand_id}/versions", json={"label": "2026 launch"})
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["version_number"] == 1 and v["counts"]["principles"] >= 1 and len(v["snapshot_checksum"]) == 64
    assert b.users["editor"].post(f"/v1/brands/{b.brand_id}/versions", json={}).status_code == 403
    brand = cd.get(f"/v1/brands/{b.brand_id}").json()
    assert brand["overview"]["current_version"]["version_number"] == 1
    from app.db.session import TenantContext, tenant_session

    with pytest.raises(ProgrammingError):
        with tenant_session(TenantContext(uuid.UUID(b.org_id))) as db:
            db.execute(text("UPDATE brand_versions SET snapshot = '{}'::jsonb"))


def test_projects_and_graph(b, processed):
    cd = b.users["creative_director"]
    concepts = cd.get(f"/v1/brands/{b.brand_id}/knowledge/concepts").json()["items"]
    r = cd.post(f"/v1/brands/{b.brand_id}/projects", json={
        "name": "Website relaunch", "project_type": "website_design", "selected_domains": ["visual_identity", "design_language"],
        "asset_ids": [processed["organic.jpg"]], "concept_ids": [concepts[0]["id"]]})
    assert r.status_code == 201, r.text
    assert [a["id"] for a in r.json()["assets"]] == [processed["organic.jpg"]]
    g = cd.get(f"/v1/brands/{b.brand_id}/graph").json()
    types = {n["type"] for n in g["nodes"]}
    assert {"aesthetic_concept", "asset", "project"} <= types and g["edges"]


def test_knowledge_is_tenant_isolated(customers, b):
    a = customers["A"]
    pid = b.users["creative_director"].get(f"/v1/brands/{b.brand_id}/knowledge/principles").json()["items"][0]["id"]
    assert a.admin.get(f"/v1/knowledge/principles/{pid}").status_code == 404
    assert a.admin.post(f"/v1/knowledge/principles/{pid}/approve").status_code == 404
    assert a.admin.get(f"/v1/brands/{b.brand_id}/knowledge/principles").status_code == 404
