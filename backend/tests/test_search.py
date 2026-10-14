"""Phase 6: hybrid, approval-aware, tenant-scoped retrieval."""
from __future__ import annotations

from tests.media_fixtures import path


def _search(world, query, **kw):
    r = world["c"].users["viewer"].post("/v1/search", json={"query": query, "brand_id": world["brand_id"], "explain": True, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_organic_geometry_approved(world):
    res = _search(world, "Find approved references with organic geometry")
    assert res["interpreted"]["approved_only"] is True
    ids = [i["id"] for i in res["items"]]
    assert world["ids"]["organic.jpg"] in ids[:3]
    assert world["ids"]["organic2.jpg"] not in ids  # not approved → excluded in approved scope
    assert all(i["knowledge_status"] == "official" for i in res["items"])
    assert any(m["label"] == "Organic geometry" for m in res["interpreted"]["matched_entities"])


def test_material_expression_images(world):
    res = _search(world, "Find images demonstrating material expression")
    assets = [i for i in res["items"] if i["entity_type"] == "asset"]
    assert assets and assets[0]["id"] == world["ids"]["material.jpg"]
    assert all(i["asset"]["asset_type"] in ("image", "photograph") for i in assets)


def test_videos_slow_cinematic(world):
    res = _search(world, "Find videos with slow cinematic camera movements")
    assert [i["id"] for i in res["items"]][:1] == [world["ids"]["film.mp4"]]
    assert "slow motion" in res["interpreted"]["attributes"]


def test_muted_palettes_dramatic_lighting(world):
    res = _search(world, "Find references with muted palettes and dramatic lighting")
    top = [i["id"] for i in res["items"][:4]]
    assert world["ids"]["dramatic.jpg"] in top or world["ids"]["architectural.jpg"] in top
    assert world["ids"]["vibrant.png"] not in top[:2]


def test_guidelines_for_website_design(world):
    res = _search(world, "Find guidelines relevant to website design")
    assert res["items"][0]["id"] == world["guideline"]["id"]
    assert all(i["entity_type"] in ("guideline", "principle") for i in res["items"])


def test_assets_associated_with_principle(world):
    v = world["c"].users["viewer"]
    r = v.get("/v1/search/related", params={"entity_type": "principle", "entity_id": world["principle"]["id"], "depth": 2}).json()
    linked = {i["id"] for i in r["items"] if i["entity_type"] == "asset"}
    assert {world["ids"]["organic.jpg"], world["ids"]["organic2.jpg"]} <= linked


def test_visual_similarity(world, client):
    v = world["c"].users["viewer"]
    r = v.post("/v1/search/visual", data={"asset_id": world["ids"]["organic.jpg"], "brand_id": world["brand_id"]}).json()
    assert r["items"][0]["id"] == world["ids"]["organic2.jpg"]
    with open(path("organic2.jpg"), "rb") as f:
        r = v.post("/v1/search/visual", files={"image": ("q.jpg", f.read(), "image/jpeg")}, data={"brand_id": world["brand_id"]}).json()
    assert r["items"][0]["id"] == world["ids"]["organic2.jpg"]
    sim = v.get(f"/v1/assets/{world['ids']['organic.jpg']}/similar").json()["items"]
    assert sim[0]["id"] == world["ids"]["organic2.jpg"]


def test_document_segments_are_retrievable(world):
    res = _search(world, "harsh on-camera flash")
    hit = next(i for i in res["items"] if i["entity_type"] == "asset" and i["asset"]["asset_type"] == "document")
    assert hit["id"] == world["ids"]["guidelines.pdf"]
    assert hit["matched_segments"] and hit["matched_segments"][0]["page_number"] == 1


def test_search_never_crosses_tenants(world, customers):
    queries = ["organic geometry", "material expression texture", "concrete grid facade", "website layout guideline"]
    world_ids = set(world["ids"].values()) | {world["guideline"]["id"], world["principle"]["id"], world["organic"]["id"]}
    for other in ("A", "B"):
        api = customers[other].admin
        for q in queries:
            res = api.post("/v1/search", json={"query": q, "limit": 100}).json()
            assert not ({i["id"] for i in res["items"]} & world_ids)
        # explicitly targeting C's brand from another tenant yields nothing
        res = api.post("/v1/search", json={"query": "organic", "brand_id": world["brand_id"]}).json()
        assert res["items"] == []
        r = api.post("/v1/search/visual", data={"asset_id": world["ids"]["organic.jpg"]}).json()
        assert not ({i["id"] for i in r["items"]} & world_ids)
