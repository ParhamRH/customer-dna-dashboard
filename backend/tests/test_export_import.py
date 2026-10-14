"""Phase 7: customer-specific export (full + selective) and validated, staged import."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from app.jobs.queue import drain
from tests.conftest import PASSWORD, Api, login


def _export(api, body) -> tuple[dict, bytes]:
    r = api.post("/v1/exports", json=body)
    assert r.status_code == 202, r.text
    drain()
    e = api.get(f"/v1/exports/{r.json()['id']}").json()
    assert e["status"] == "completed", e
    d = api.get(f"/v1/exports/{e['id']}/download").json()
    data = api.client.get(d["url"].replace("http://localhost:8000", "")).content
    assert hashlib.sha256(data).hexdigest() == d["sha256"] == e["archive_checksum"]
    return e, data


def _zip(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


def _all_text(z: zipfile.ZipFile) -> str:
    return "\n".join(z.read(n).decode(errors="ignore") for n in z.namelist() if n.endswith((".json", ".jsonl", ".md", ".css")))


@pytest.fixture(scope="module")
def c_full(world):
    c = world["c"]
    e, data = _export(c.admin, {"mode": "full", "include_embeddings": True})
    return e, data


def test_full_export_structure_and_checksums(c_full, world):
    e, data = c_full
    z = _zip(data)
    names = set(z.namelist())
    for required in ("customer-export/manifest.json", "customer-export/README.md", "customer-export/customer/profile.json",
                     "customer-export/brand/brand.json", "customer-export/relationships/relationships.json",
                     "customer-export/projects/projects.json", "customer-export/documentation/data-dictionary.json"):
        assert required in names
    m = json.loads(z.read("customer-export/manifest.json"))
    assert m["customer_id"] == world["c"].org_id and m["schema_version"] == 1 and m["export_id"] == e["id"]
    assert world["brand_id"] in m["brand_ids"] and m["asset_count"] >= 8
    assert m["tenant_purity_check"]["passed"] is True
    for rel, digest in m["checksums"].items():
        assert hashlib.sha256(z.read(f"customer-export/{rel}")).hexdigest() == digest, rel
    assert m["file_count"] == len([n for n in names if not n.endswith("/")])
    originals = [n for n in names if "/assets/originals/" in n]
    assert originals and m["embeddings"] and all(x["dimensions"] in (256, 384) for x in m["embeddings"])


def test_export_contains_no_other_customer_data(c_full, customers):
    _, data = c_full
    text = _all_text(_zip(data))
    for other in ("A", "B"):
        o = customers[other]
        assert o.org_id not in text and o.brand_id not in text and o.slug not in text
    # and the reverse direction: A's export holds nothing of B or C
    _, a_data = _export(customers["A"].admin, {"mode": "full"})
    a_text = _all_text(_zip(a_data))
    for other in ("B", "C"):
        o = customers[other]
        assert o.org_id not in a_text and o.brand_id not in a_text
    assert customers["B"].admin.get("/v1/exports").json()["items"] == [] or all(
        i["organization_id"] == customers["B"].org_id for i in customers["B"].admin.get("/v1/exports").json()["items"])


def test_selective_export(world):
    c = world["c"]
    col = c.users["creative_director"].post(f"/v1/brands/{world['brand_id']}/collections",
                                            json={"name": "Export pick", "asset_ids": [world["ids"]["material.jpg"]]}).json()
    _, data = _export(c.admin, {"mode": "selective", "selection": {"brand_id": world["brand_id"], "domains": ["aesthetic_language"],
                                                                     "collection_ids": [col["id"]], "task_type": "image_generation"}})
    z = _zip(data)
    m = json.loads(z.read("customer-export/manifest.json"))
    assert m["export_mode"] == "selective" and m["asset_count"] == 1
    assert m["included_domains"] == ["aesthetic_language"]
    names = z.namelist()
    assert any("aesthetic-language" in n and n.endswith("concepts.json") for n in names)
    assert not any("/foundation/" in n for n in names)
    assert "customer-export/ai-knowledge/task-context.md" in names
    concepts = json.loads(next(z.read(n) for n in names if n.endswith("concepts.json")))
    assert all(x["status"] in ("approved", "deprecated") for x in concepts)  # pending excluded by default in selective mode


def test_export_permissions(world):
    c = world["c"]
    assert c.users["editor"].post("/v1/exports", json={"mode": "full"}).status_code == 403
    assert c.users["viewer"].get("/v1/exports").status_code == 403


@pytest.fixture(scope="module")
def customer_d(client, platform_admin):
    r = platform_admin.post("/v1/organizations", json={"name": "Customer D (import target)", "admin_email": "admin@customer-d.test",
                                                       "admin_password": PASSWORD})
    org = r.json()
    return Api(client, login(client, "admin@customer-d.test", PASSWORD), org["organization_id"])


def _stage(api, data: bytes) -> dict:
    r = api.post("/v1/imports", files={"file": ("library.zip", data, "application/zip")})
    assert r.status_code == 202, r.text
    drain()
    return api.get(f"/v1/imports/{r.json()['id']}").json()


def test_import_rejects_tampered_archive(c_full, customer_d):
    _, data = c_full
    src = _zip(data)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for n in src.namelist():
            body = src.read(n)
            if n.endswith("brand/brand.json"):
                body = body.replace(b"Search Lab", b"Hacked Lab")
            out.writestr(n, body)
    ij = _stage(customer_d, buf.getvalue())
    assert ij["status"] == "invalid"
    assert any("checksum mismatch" in e for e in ij["report"]["errors"])
    assert customer_d.post(f"/v1/imports/{ij['id']}/commit", json={}).status_code == 422


def test_import_roundtrip_reconstructs_library(c_full, customer_d, world, client):
    _, data = c_full
    ij = _stage(customer_d, data)
    assert ij["status"] == "validated", ij["report"]
    pv = ij["preview"]
    assert pv["checksums_verified"] > 10 and pv["errors"] == []
    assert pv["counts"]["assets"] >= 8 and pv["duplicates"]["assets"] == 0
    r = customer_d.post(f"/v1/imports/{ij['id']}/commit", json={"regenerate_embeddings": True})
    assert r.status_code == 202
    drain()
    done = customer_d.get(f"/v1/imports/{ij['id']}").json()
    assert done["status"] == "committed", done["report"]
    created = done["report"]["created"]
    assert created["assets"] >= 8 and created["relationships"] >= 3 and created["principles"] >= 1
    brands = customer_d.get("/v1/brands").json()["items"]
    lab = next(b for b in brands if b["slug"] == "search-lab")
    concepts = customer_d.get(f"/v1/brands/{lab['id']}/knowledge/concepts").json()["items"]
    organic = next(c for c in concepts if c["name"] == "Organic geometry")
    assert organic["status"] == "approved" and organic["origin"] == "import"
    detail = customer_d.get(f"/v1/knowledge/concepts/{organic['id']}").json()
    assert {a["title"] for a in detail["example_assets"]} == {"Soft forms study", "Second soft forms study"}
    # originals are byte-identical after the round trip
    assets = customer_d.get("/v1/assets", params={"brand_id": lab["id"], "q": "Linen"}).json()["items"]
    a = assets[0]
    url = customer_d.get(f"/v1/assets/{a['id']}/download").json()["url"]
    body = client.get(url.replace("http://localhost:8000", "")).content
    assert hashlib.sha256(body).hexdigest() == customer_d.get(f"/v1/assets/{a['id']}").json()["checksum"]
    # embeddings were regenerated → search works in the new workspace
    res = customer_d.post("/v1/search", json={"query": "organic geometry", "brand_id": lab["id"]}).json()
    assert res["items"] and res["items"][0]["entity_type"] in ("aesthetic_concept", "asset")
    # the source customer is untouched and still isolated
    assert customer_d.get(f"/v1/brands/{world['brand_id']}").status_code == 404


def test_reimport_detects_duplicates_and_merges(c_full, customer_d):
    """Importing the same library again into D (which already holds it) merges instead of duplicating."""
    _, data = c_full
    target = next(b for b in customer_d.get("/v1/brands").json()["items"] if b["slug"] == "search-lab")
    ij = _stage(customer_d, data)
    assert ij["preview"]["duplicates"]["assets"] >= 8
    src_brand = next(b for b in ij["preview"]["brands"] if b["slug"] == "search-lab")
    assert src_brand["conflict_brand_id"] == target["id"]
    def counts():
        return (customer_d.get("/v1/assets", params={"brand_id": target["id"], "limit": 500}).json()["total"],
                len(customer_d.get(f"/v1/brands/{target['id']}/knowledge/principles").json()["items"]),
                len(customer_d.get(f"/v1/brands/{target['id']}/knowledge/guidelines").json()["items"]))
    before = counts()
    customer_d.post(f"/v1/imports/{ij['id']}/commit", json={"brand_mapping": {src_brand["source_id"]: f"merge:{target['id']}"},
                                                            "regenerate_embeddings": False})
    drain()
    done = customer_d.get(f"/v1/imports/{ij['id']}").json()
    assert done["status"] == "committed", done["report"]
    assert done["report"]["mapped_existing"]["assets"] >= 8 and done["report"]["mapped_existing"]["principles"] >= 1
    assert counts() == before


def test_failed_commit_rolls_back_everything(c_full, customer_d, platform_admin, client):
    _, data = c_full
    src = _zip(data)
    manifest = json.loads(src.read("customer-export/manifest.json"))
    victim = sorted(n for n in src.namelist() if "/assets/originals/" in n)[-1]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for n in src.namelist():
            body = src.read(n)
            if n == victim:
                body = body + b"corrupted"
                manifest["checksums"][n.removeprefix("customer-export/")] = hashlib.sha256(body).hexdigest()
            if n.endswith("manifest.json"):
                continue
            out.writestr(n, body)
        out.writestr("customer-export/manifest.json", json.dumps(manifest))
    # fresh target so counts are unambiguous
    r = platform_admin.post("/v1/organizations", json={"name": "Customer E", "admin_email": "admin@customer-e.test", "admin_password": PASSWORD})
    e_api = Api(client, login(client, "admin@customer-e.test", PASSWORD), r.json()["organization_id"])
    ij = _stage(e_api, buf.getvalue())
    assert ij["status"] == "validated"  # manifest is self-consistent; the asset record checksum is not
    e_api.post(f"/v1/imports/{ij['id']}/commit", json={})
    drain()
    done = e_api.get(f"/v1/imports/{ij['id']}").json()
    assert done["status"] == "failed" and done["report"]["rolled_back"] is True
    assert e_api.get("/v1/brands").json()["items"] == []
    assert e_api.get("/v1/assets").json()["total"] == 0
    from app.config import get_settings

    org_dir = Path(get_settings().storage_local_root) / "orgs" / r.json()["organization_id"] / "brands"
    assert not org_dir.exists() or not any(p.is_file() for p in org_dir.rglob("*"))
