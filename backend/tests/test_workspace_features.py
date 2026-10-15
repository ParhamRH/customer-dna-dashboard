"""Workspace features behind the customer UI: knowledge graph payload, collection mosaics, project
references, integrations (MCP info, webhook delivery log), prompt overrides, brand re-index and the
sanitising of job errors shown to workspace users."""
from __future__ import annotations

import uuid

from app.jobs.queue import drain, public_error


def test_graph_carries_asset_thumbnails_and_hides_rejected_edges(world):
    import uuid as _uuid

    from app.db.session import TenantContext, tenant_session
    from app.models import Relationship

    c = world["c"]
    cd = c.users["creative_director"]
    bid = world["brand_id"]
    g = cd.get(f"/v1/brands/{bid}/graph").json()
    assets = [n for n in g["nodes"] if n["type"] == "asset"]
    assert assets, "concept examples should appear as asset nodes"
    assert all(n.get("thumbnail_url") for n in assets if n.get("asset_type") == "image")
    assert all(n.get("reference_role") for n in assets)

    # one AI-suggested and one rejected relationship between two concepts
    concepts = cd.get(f"/v1/brands/{bid}/knowledge/concepts").json()["items"]
    a, b = concepts[0]["id"], concepts[1]["id"]
    with tenant_session(TenantContext(_uuid.UUID(c.org_id))) as db:
        for status, rel in (("suggested", "supports"), ("rejected", "derived_from")):
            db.add(Relationship(organization_id=_uuid.UUID(c.org_id), brand_id=_uuid.UUID(bid), source_type="aesthetic_concept",
                                source_id=_uuid.UUID(a), relation_type=rel, target_type="aesthetic_concept", target_id=_uuid.UUID(b),
                                origin="ai_suggestion", status=status, weight=0.5))
    plain = {e["relation_type"] for e in cd.get(f"/v1/brands/{bid}/graph").json()["edges"]}
    assert "supports" not in plain and "derived_from" not in plain
    full = cd.get(f"/v1/brands/{bid}/graph", params={"include_suggested": True}).json()["edges"]
    by_type = {e["relation_type"]: e for e in full}
    assert by_type["supports"]["status"] == "suggested" and by_type["supports"]["origin"] == "ai_suggestion"
    assert "derived_from" not in by_type  # rejected suggestions never come back


def test_collection_list_preview_and_cover(world, customers):
    cd = world["c"].users["creative_director"]
    bid = world["brand_id"]
    ids = list(world["ids"].values())[:5]
    col = cd.post(f"/v1/brands/{bid}/collections", json={"name": f"Mosaic {uuid.uuid4().hex[:4]}", "kind": "moodboard", "asset_ids": ids}).json()
    assert col["cover_asset_id"] == ids[0]  # first asset becomes the cover
    cd.patch(f"/v1/collections/{col['id']}", json={"cover_asset_id": ids[2]})
    listed = next(x for x in cd.get(f"/v1/brands/{bid}/collections").json()["items"] if x["id"] == col["id"])
    assert [a["id"] for a in listed["preview"]][:1] == [ids[2]]  # cover first
    assert len(listed["preview"]) == 4 and len({a["id"] for a in listed["preview"]}) == 4
    assert "assets" not in listed  # the list stays light
    # reorder and remove keep the detail consistent
    cd.put(f"/v1/collections/{col['id']}/order", json={"asset_ids": list(reversed(ids))})
    assert [a["id"] for a in cd.get(f"/v1/collections/{col['id']}").json()["assets"]] == list(reversed(ids))
    cd.delete(f"/v1/collections/{col['id']}/assets/{ids[2]}")
    detail = cd.get(f"/v1/collections/{col['id']}").json()
    assert ids[2] not in [a["id"] for a in detail["assets"]] and detail["cover_asset_id"] is None
    # another customer cannot see or change it
    assert customers["A"].admin.get(f"/v1/collections/{col['id']}").status_code == 404
    assert customers["A"].admin.patch(f"/v1/collections/{col['id']}", json={"name": "x"}).status_code == 404


def test_project_reference_assets_are_linked_once(world):
    cd = world["c"].users["creative_director"]
    bid = world["brand_id"]
    p = cd.post(f"/v1/brands/{bid}/projects", json={"name": f"Refs {uuid.uuid4().hex[:4]}", "project_type": "website_design"}).json()
    ids = list(world["ids"].values())[:2]
    r = cd.patch(f"/v1/projects/{p['id']}", json={"asset_ids": ids})
    assert r.status_code == 200, r.text
    assert sorted(a["id"] for a in r.json()["assets"]) == sorted(ids)
    again = cd.patch(f"/v1/projects/{p['id']}", json={"asset_ids": ids}).json()  # idempotent
    assert len([x for x in again["relationships"] if x["other_type"] == "asset"]) == 2
    assert world["c"].users["viewer"].patch(f"/v1/projects/{p['id']}", json={"asset_ids": ids}).status_code == 403


def test_integrations_payload_has_mcp_info_and_no_secrets(customers):
    a = customers["A"]
    r = a.admin.get("/v1/integrations")
    assert r.status_code == 200, r.text
    mcp = r.json()["mcp"]
    assert mcp["read_only"] is True and mcp["http_url"].endswith("/mcp")
    names = {t["name"] for t in mcp["tools"]}
    assert {"search_brand_assets", "generate_brand_context", "get_visual_identity"} <= names
    hook = a.admin.post("/v1/integrations", json={"kind": "webhook", "name": "n8n", "secret": "s3cret-value",
                                                  "config": {"url": "http://127.0.0.1:9/hook", "events": ["asset.created"]}})
    assert hook.status_code == 201, hook.text
    body = a.admin.get("/v1/integrations").text
    assert "s3cret-value" not in body and "secret_encrypted" not in body
    assert '"has_secret":true' in body.replace(" ", "")
    assert a.users["viewer"].get("/v1/integrations").status_code == 403
    assert a.users["creative_director"].get("/v1/integrations").status_code == 403
    assert a.admin.delete(f"/v1/integrations/{hook.json()['id']}").status_code == 204


def test_webhook_delivery_log_is_tenant_scoped_and_sanitised(customers):
    a, b = customers["A"], customers["B"]
    hook = a.admin.post("/v1/integrations", json={"kind": "webhook", "name": "Unreachable", "config": {"url": "http://127.0.0.1:9/x"}}).json()
    assert a.admin.post(f"/v1/integrations/{hook['id']}/test").status_code == 202
    drain(job_types=["webhook.deliver"])
    items = a.admin.get(f"/v1/integrations/{hook['id']}/deliveries").json()["items"]
    assert items and items[0]["event"] == "integration.test"
    assert items[0]["status"] in ("failed", "dead")
    err = items[0]["error"]
    assert err and "Traceback" not in err and "site-packages" not in err and "\n" not in err
    # the same failure through the jobs API is sanitised too
    job = a.admin.get(f"/v1/jobs/{items[0]['job_id']}").json()
    assert "Traceback" not in (job["error"] or "") and "locked_by" not in job
    # another customer cannot read the log, test the hook or see it in their integrations
    assert b.admin.get(f"/v1/integrations/{hook['id']}/deliveries").status_code == 404
    assert b.admin.post(f"/v1/integrations/{hook['id']}/test").status_code == 404
    assert hook["id"] not in b.admin.get("/v1/integrations").text
    a.admin.delete(f"/v1/integrations/{hook['id']}")


def test_public_error_keeps_only_the_exception_line():
    tb = "ConnectError: [Errno 111] refused\nTraceback (most recent call last):\n  File \"/srv/app/.venv/lib/python3.13/site-packages/x.py\"\n"
    assert public_error(tb) == "ConnectError: [Errno 111] refused"
    assert public_error(None) is None and public_error("") is None
    assert len(public_error("x" * 5000)) == 500


def test_prompt_override_and_reset_are_per_customer(customers):
    from app.ai.prompts import get_prompt
    from app.db.session import TenantContext, tenant_session

    a, b = customers["A"], customers["B"]
    base = next(p for p in a.admin.get("/v1/prompts").json()["items"] if p["key"] == "image_analysis" and p["organization_id"] is None)
    r = a.admin.post("/v1/prompts", json={"key": "image_analysis", "template": base["template"] + "\nPrefer British spelling."})
    assert r.status_code == 201, r.text
    assert a.users["creative_director"].post("/v1/prompts", json={"key": "image_analysis", "template": "x" * 30}).status_code == 403
    with tenant_session(TenantContext(uuid.UUID(a.org_id))) as db:
        assert get_prompt(db, "image_analysis").organization_id == a.org_id
    with tenant_session(TenantContext(uuid.UUID(b.org_id))) as db:
        assert get_prompt(db, "image_analysis").organization_id is None  # B keeps the platform default
    assert a.admin.post("/v1/prompts/image_analysis/reset").json()["deactivated"] == 1
    with tenant_session(TenantContext(uuid.UUID(a.org_id))) as db:
        assert get_prompt(db, "image_analysis").organization_id is None
    kept = [p for p in a.admin.get("/v1/prompts").json()["items"] if p["organization_id"] == a.org_id]
    assert kept and not any(p["is_active"] for p in kept)  # history is kept for provenance
    assert a.admin.post("/v1/prompts/not_a_prompt/reset").status_code == 404


def test_brand_reindex_endpoint(customers):
    a, b = customers["A"], customers["B"]
    r = a.users["creative_director"].post(f"/v1/brands/{a.brand_id}/reindex")
    assert r.status_code == 202, r.text
    job = a.admin.get(f"/v1/jobs/{r.json()['job_id']}").json()
    assert job["job_type"] == "brand.reindex" and job["entity_id"] == a.brand_id
    assert a.users["viewer"].post(f"/v1/brands/{a.brand_id}/reindex").status_code == 403
    assert b.admin.post(f"/v1/brands/{a.brand_id}/reindex").status_code == 404


def test_outbound_urls_to_internal_addresses_are_refused(customers, monkeypatch):
    from app.config import get_settings
    from app.security.outbound import OutboundUrlError, check_outbound_url

    cfg = get_settings()
    monkeypatch.setattr(cfg, "outbound_allow_private", False)
    monkeypatch.setattr(cfg, "outbound_allowed_hosts", ["n8n"])
    for bad in ("http://127.0.0.1:8000/v1", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/hook",
                "http://localhost/hook", "ftp://example.com/x", "https://user:pw@example.com/x"):
        try:
            check_outbound_url(bad)
        except OutboundUrlError:
            continue
        raise AssertionError(f"{bad} should be refused")
    assert check_outbound_url("http://n8n:5678/webhook/brand-dna")  # explicitly allowed internal host
    a = customers["A"].admin
    r = a.post("/v1/integrations", json={"kind": "webhook", "name": "internal", "config": {"url": "http://127.0.0.1:5432/"}})
    assert r.status_code == 422 and "non-public" in r.text
    r = a.post("/v1/integrations", json={"kind": "ai_provider", "name": "sneaky", "secret": "k",
                                        "config": {"capability": "vision", "provider": "openai_compatible", "base_url": "http://10.1.2.3/v1"}})
    assert r.status_code == 422


def test_ai_override_with_own_base_url_never_receives_platform_key(customers, monkeypatch):
    import uuid as _uuid

    from app.ai import registry
    from app.config import get_settings
    from app.db.session import TenantContext, tenant_session

    cfg = get_settings()
    monkeypatch.setattr(cfg, "openai_api_key", "sk-platform-secret")
    a = customers["A"].admin
    r = a.post("/v1/integrations", json={"kind": "ai_provider", "name": "no key", "config": {
        "capability": "vision", "provider": "openai_compatible", "base_url": "http://127.0.0.1:9/v1", "model": "m"}})
    assert r.status_code == 201, r.text
    try:
        with tenant_session(TenantContext(_uuid.UUID(customers["A"].org_id))) as db:
            p = registry.vision_provider(db)
            assert getattr(p, "base_url", "").startswith("http://127.0.0.1:9")
            assert getattr(p, "api_key", None) in ("", None)  # the platform key is not forwarded
    finally:
        a.delete(f"/v1/integrations/{r.json()['id']}")
