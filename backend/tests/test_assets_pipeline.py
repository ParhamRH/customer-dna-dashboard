"""Phase 3 + 4: asset ingestion, storage isolation, derivatives, AI analysis, retries."""
from __future__ import annotations

import hashlib

import httpx
import pytest

from app.jobs.queue import drain
from tests.media_fixtures import path, upload


@pytest.fixture(scope="module")
def a(customers):
    return customers["A"]


@pytest.fixture(scope="module")
def ingested(a):
    """Upload one of each media family into customer A and run the worker queue."""
    editor = a.users["editor"]
    out = {}
    for name, extra in [
        ("organic.jpg", {"tags": "organic, warm", "title": "Organic study"}),
        ("architectural.jpg", {"title": "Concrete grid"}),
        ("film.mp4", {"title": "Brand film cut"}),
        ("guidelines.pdf", {"title": "Brand guidelines PDF"}),
        ("logo.svg", {"asset_type": "logo", "category": "logo", "subcategory": "primary"}),
        ("model.obj", {"title": "Torus study"}),
        ("notes.md", {}),
    ]:
        r = upload(editor, a.brand_id, name, **extra)
        assert r.status_code == 201, r.text
        out[name] = r.json()
        assert out[name]["processing_status"] == "pending"
    drain()
    return {k: editor.get(f"/v1/assets/{v['id']}").json() for k, v in out.items()}


def test_all_media_processed(ingested):
    for name, asset in ingested.items():
        assert asset["processing_status"] == "processed", (name, asset["processing_error"])


def test_image_pipeline_outputs(ingested):
    img = ingested["organic.jpg"]
    kinds = {d["kind"] for d in img["derivatives"]}
    assert {"thumbnail", "preview"} <= kinds
    mm = img["media_metadata"]
    assert mm["width"] == 1600 and mm["height"] == 1067 and len(mm["palette"]) >= 3
    assert img["thumbnail_url"].startswith("http")
    analysis = img["analyses"][0]
    assert analysis["status"] == "pending_review"
    assert analysis["provider"] == "dev-heuristic" and analysis["is_development_adapter"] is True
    assert analysis["model"] and analysis["prompt_key"] == "image_analysis" and analysis["prompt_version"] == 1
    assert analysis["objective"]["lighting"]["key"] in ("high-key", "mid-key", "low-key")
    assert analysis["interpretive"]["summary"]
    # human tags are approved, AI tags only suggested
    details = {t["tag"]: t for t in img["tag_details"]}
    assert details["organic"]["source"] == "human" and details["organic"]["status"] == "approved"
    assert any(t["source"] == "ai" and t["status"] == "suggested" for t in img["tag_details"])
    assert img["approval_status"] == "pending"


def test_video_pipeline_outputs(ingested):
    v = ingested["film.mp4"]
    mm = v["media_metadata"]
    assert mm["scene_count"] == 3 and mm["frame_rate"] == 24 and mm["duration_seconds"] == pytest.approx(7.5, abs=0.2)
    scenes = [s for s in v["segments"] if s["segment_type"] == "scene"]
    assert len(scenes) == 3 and all(s["keyframe_derivative_id"] for s in scenes)
    assert sum(1 for d in v["derivatives"] if d["kind"] == "keyframe") == 3
    moves = [s["meta"]["motion"]["camera_movement"] for s in scenes]
    assert "zoom in" in moves[0] and "static" in moves[1] and "pan right" in moves[2]
    temporal = next(x for x in v["analyses"] if x["analysis_type"] == "video_temporal")
    assert temporal["objective"]["scenes"] and temporal["objective"]["temporal_description"]


def test_document_pipeline_extracts_principle_candidates(ingested, a):
    d = ingested["guidelines.pdf"]
    assert d["media_metadata"]["page_count"] == 1
    assert [s for s in d["segments"] if s["segment_type"] == "page"]
    assert d["pending_suggestions"] >= 5
    sug = a.users["reviewer"].get("/v1/review/suggestions", params={"suggestion_type": "principle", "brand_id": a.brand_id}).json()
    classes = {s["payload"]["classification"] for s in sug["items"] if s["source_asset_id"] == d["id"]}
    assert {"mandatory", "prohibited"} <= classes


def test_svg_and_3d(ingested):
    assert ingested["logo.svg"]["media_metadata"]["vector"] is True
    assert ingested["logo.svg"]["thumbnail_url"]
    m = ingested["model.obj"]["media_metadata"]
    assert m["vertex_count"] == 1152 and m["face_count"] == 2304
    assert ingested["model.obj"]["thumbnail_url"]


def test_original_download_is_byte_identical(ingested, a, client):
    asset = ingested["organic.jpg"]
    assert a.users["viewer"].get(f"/v1/assets/{asset['id']}/download").status_code == 403
    r = a.users["editor"].get(f"/v1/assets/{asset['id']}/download")
    assert r.status_code == 200
    body = client.get(r.json()["url"].replace("http://localhost:8000", "")).content
    assert hashlib.sha256(body).hexdigest() == asset["checksum"] == hashlib.sha256(path("organic.jpg").read_bytes()).hexdigest()


def test_signed_urls_cannot_be_tampered(ingested, client):
    url = ingested["organic.jpg"]["thumbnail_url"].replace("http://localhost:8000", "")
    assert client.get(url).status_code == 200
    token = url.rsplit("/", 1)[1]
    body, sig = token.rsplit(".", 1)
    forged = body[:-2] + ("AA" if body[-2:] != "AA" else "BB")
    assert client.get(f"/v1/files/{forged}.{sig}").status_code == 404


def test_duplicate_detection(ingested, a):
    r = upload(a.users["editor"], a.brand_id, "organic.jpg")
    assert r.status_code == 409 and r.json()["error"]["details"]["existing_asset_id"] == ingested["organic.jpg"]["id"]
    r = upload(a.users["editor"], a.brand_id, "organic.jpg", allow_duplicate=True)
    assert r.status_code == 201


def test_rejects_unsupported_files(a):
    assert upload(a.users["editor"], a.brand_id, "evil.exe").status_code == 415


def test_viewer_cannot_upload(a):
    assert upload(a.users["viewer"], a.brand_id, "dramatic.jpg").status_code == 403


def test_cross_tenant_asset_access_is_impossible(ingested, customers):
    b = customers["B"]
    aid = ingested["organic.jpg"]["id"]
    assert b.admin.get(f"/v1/assets/{aid}").status_code == 404
    assert b.admin.get(f"/v1/assets/{aid}/download").status_code == 404
    listed = b.admin.get("/v1/assets", params={"limit": 500}).json()
    assert aid not in {i["id"] for i in listed["items"]}
    # B cannot upload into A's brand either
    assert upload(b.admin, customers["A"].brand_id, "vibrant.png").status_code == 404


def test_listing_filters_and_facets(ingested, a):
    api = a.users["viewer"]
    r = api.get("/v1/assets", params={"brand_id": a.brand_id, "asset_type": "video"}).json()
    assert [i["asset_type"] for i in r["items"]] == ["video"]
    r = api.get("/v1/assets", params={"brand_id": a.brand_id, "tag": "organic"}).json()
    assert {i["id"] for i in r["items"]} == {ingested["organic.jpg"]["id"]}
    r = api.get("/v1/assets", params={"brand_id": a.brand_id, "q": "concrete"}).json()
    assert ingested["architectural.jpg"]["id"] in {i["id"] for i in r["items"]}
    assert r["facets"]["asset_type"]["video"] >= 1


def test_collections_and_bulk(ingested, a):
    cd = a.users["creative_director"]
    ids = [ingested["organic.jpg"]["id"], ingested["architectural.jpg"]["id"]]
    r = cd.post(f"/v1/brands/{a.brand_id}/collections", json={"name": "Moodboard SS27", "kind": "moodboard", "asset_ids": ids})
    assert r.status_code == 201, r.text
    col = r.json()
    assert col["asset_count"] == 2 and [x["id"] for x in col["assets"]] == ids
    listed = cd.get("/v1/assets", params={"collection_id": col["id"]}).json()
    assert {i["id"] for i in listed["items"]} == set(ids)
    r = cd.post("/v1/assets/bulk", json={"asset_ids": ids, "action": "add_tags", "value": ["ss27"]})
    assert r.json()["updated"] == 2
    r = cd.post("/v1/assets/bulk", json={"asset_ids": ids, "action": "set_approval", "value": "approved"})
    assert r.json()["updated"] == 2
    assert cd.get(f"/v1/assets/{ids[0]}").json()["approval_status"] == "approved"
    assert a.users["editor"].post("/v1/assets/bulk", json={"asset_ids": ids, "action": "set_approval", "value": "approved"}).status_code == 403


def test_soft_delete_restore_and_purge(a, client):
    editor, cd = a.users["editor"], a.users["creative_director"]
    r = upload(editor, a.brand_id, "dramatic.jpg")
    aid = r.json()["id"]
    drain()
    thumb = editor.get(f"/v1/assets/{aid}").json()["thumbnail_url"].replace("http://localhost:8000", "")
    assert editor.delete(f"/v1/assets/{aid}").status_code == 403  # editors cannot delete
    assert cd.delete(f"/v1/assets/{aid}").status_code == 200
    assert cd.get("/v1/assets", params={"q": "dramatic"}).json()["total"] == 0
    assert cd.post(f"/v1/assets/{aid}/restore").status_code == 200
    assert cd.delete(f"/v1/assets/{aid}", params={"grace_days": 0}).status_code == 200
    drain()
    assert cd.get(f"/v1/assets/{aid}").status_code == 404
    assert client.get(thumb).status_code == 404  # storage objects removed


def test_failed_jobs_can_be_retried(a):
    import uuid as _uuid

    from app.db.session import TenantContext, tenant_session
    from app.jobs.queue import enqueue

    with tenant_session(TenantContext(_uuid.UUID(a.org_id))) as db:
        job = enqueue(db, _uuid.UUID(a.org_id), "noop", payload={"fail": True}, max_attempts=1)
        jid = str(job.id)
    drain(job_types=["noop"])
    j = a.admin.get(f"/v1/jobs/{jid}").json()
    assert j["status"] == "dead" and "requested failure" in j["error"]
    r = a.admin.post(f"/v1/jobs/{jid}/retry")
    assert r.status_code == 200 and r.json()["status"] == "queued"
    drain(job_types=["noop"])
    j = a.admin.get(f"/v1/jobs/{jid}").json()
    assert j["status"] == "dead" and j["attempts"] == 2


def test_reprocess_supersedes_previous_analysis(ingested, a):
    aid = ingested["architectural.jpg"]["id"]
    r = a.users["editor"].post(f"/v1/assets/{aid}/reprocess", json={"media": True, "ai": True, "embed": True})
    assert r.status_code == 202
    drain()
    analyses = a.users["editor"].get(f"/v1/assets/{aid}").json()["analyses"]
    statuses = sorted(x["status"] for x in analyses)
    assert statuses == ["pending_review", "superseded"]


_ = httpx
