"""Phase 6: Creative Context Generator."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

import yaml


def test_preview_shows_selection_before_generation(world):
    v = world["c"].users["viewer"]
    r = v.post("/v1/context/preview", json={"brand_id": world["brand_id"], "task_type": "website_design",
                                            "creative_direction": "organic geometry, soft forms"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["counts"]["principle"] >= 1 and p["counts"]["aesthetic_concept"] >= 2 and p["counts"]["guideline"] == 1
    assert any(x["id"] == world["ids"]["organic.jpg"] for x in p["references"])
    titles = [s["label"] for s in p["sources"]["guideline"]]
    assert titles == ["Web layout guideline"]  # the packaging guideline is out of scope for website design


def test_generate_website_package_is_traceable(world):
    cd = world["c"].users["creative_director"]
    assert world["c"].users["viewer"].post("/v1/context/generate", json={"brand_id": world["brand_id"], "task_type": "website_design"}).status_code == 403
    # a draft principle must never leak into context
    cd.post(f"/v1/brands/{world['brand_id']}/knowledge/principles",
            json={"title": "Unapproved idea", "statement": "Use glitter everywhere.", "classification": "mandatory"})
    cd.post(f"/v1/brands/{world['brand_id']}/knowledge/concepts",
            json={"name": "Neon maximalism", "definition": "Loud neon clutter.", "brand_relevance": "avoid"})
    avoid = cd.get(f"/v1/brands/{world['brand_id']}/knowledge/concepts").json()["items"]
    neon = next(c for c in avoid if c["name"] == "Neon maximalism")
    cd.post(f"/v1/knowledge/concepts/{neon['id']}/approve")
    r = cd.post("/v1/context/generate", json={"brand_id": world["brand_id"], "task_type": "website_design", "mode": "standard",
                                              "output_medium": "Responsive marketing site", "creative_direction": "calm organic forms",
                                              "concept_ids": [world["organic"]["id"]]})
    assert r.status_code == 201, r.text
    pkg = r.json()
    c = pkg["content"]
    assert c["brand"]["id"] == world["brand_id"]
    statements = json.dumps(c)
    assert "glitter" not in statements
    assert any("Neon maximalism" in p["statement"] for p in c["prohibited_directions"])
    assert [x["name"] for x in c["aesthetic_language"]][0] == "Organic geometry"
    assert c["guidelines"][0]["title"] == "Web layout guideline"
    assert "design_tokens" in c
    refs = {r["source"] for r in c["references"]}
    src = {s["ref"] for s in c["sources"]}
    assert refs <= src and f"principle:{world['principle']['id']}" in src
    assert all(s["status"] in ("approved", "official") or s["type"] == "asset" for s in c["sources"])
    md = pkg["markdown"]
    assert "## Mandatory constraints" in md and "## Sources" in md and world["principle"]["code"] in md
    canonical = json.dumps(c, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == pkg["checksum"]
    assert pkg["token_estimate"] > 100


def test_compact_mode_is_smaller_than_comprehensive(world):
    cd = world["c"].users["creative_director"]
    sizes = {}
    for mode in ("compact", "standard", "comprehensive"):
        r = cd.post("/v1/context/generate", json={"brand_id": world["brand_id"], "task_type": "website_design", "mode": mode})
        sizes[mode] = r.json()["token_estimate"]
    assert sizes["compact"] <= sizes["standard"] <= sizes["comprehensive"] and sizes["compact"] < sizes["comprehensive"]


def test_image_and_video_generation_packages(world):
    cd = world["c"].users["creative_director"]
    img = cd.post("/v1/context/generate", json={"brand_id": world["brand_id"], "task_type": "image_generation",
                                                "concept_ids": [world["organic"]["id"]]}).json()["content"]
    gp = img["generation_prompt"]
    assert "organic geometry" in gp["positive_descriptors"] and any("Neon" in n or "neon" in n.lower() for n in gp["negative_descriptors"])
    vid = cd.post("/v1/context/generate", json={"brand_id": world["brand_id"], "task_type": "video_generation"}).json()["content"]
    motion_refs = [r for r in vid["references"] if r.get("motion")]
    assert motion_refs and motion_refs[0]["id"] == world["ids"]["film.mp4"]
    assert motion_refs[0]["scenes"][0]["camera_movement"]


def test_downloads_and_zip_integrity(world, client):
    cd = world["c"].users["creative_director"]
    pkg = cd.post("/v1/context/generate", json={"brand_id": world["brand_id"], "task_type": "website_development",
                                                "reference_asset_ids": [world["ids"]["material.jpg"]]}).json()
    pid = pkg["id"]
    assert cd.get(f"/v1/context/packages/{pid}/download", params={"format": "md"}).text.startswith("# Brand context")
    y = yaml.safe_load(cd.get(f"/v1/context/packages/{pid}/download", params={"format": "yaml"}).text)
    assert y["task"]["type"] == "website_development"
    r = cd.get(f"/v1/context/packages/{pid}/download", params={"format": "zip"})
    z = zipfile.ZipFile(io.BytesIO(r.content))
    manifest = json.loads(z.read("manifest.json"))
    assert {"context.md", "context.json", "context.yaml", "tokens.css"} <= set(manifest["files"])
    assert f"references/{world['ids']['material.jpg']}.webp" in manifest["files"]
    for name, digest in manifest["files"].items():
        assert hashlib.sha256(z.read(name)).hexdigest() == digest
    assert manifest["content_checksum"] == pkg["checksum"]
    listed = cd.get("/v1/context/packages", params={"brand_id": world["brand_id"]}).json()["items"]
    assert pid in {p["id"] for p in listed}


def test_published_version_basis(world):
    cd = world["c"].users["creative_director"]
    assert cd.post("/v1/context/generate", json={"brand_id": world["brand_id"], "task_type": "copywriting",
                                                 "use_published_version": True}).status_code == 422
    cd.post(f"/v1/brands/{world['brand_id']}/versions", json={"label": "Search Lab v1"})
    c = cd.post("/v1/context/generate", json={"brand_id": world["brand_id"], "task_type": "copywriting",
                                              "use_published_version": True}).json()["content"]
    assert c["brand"]["version"]["number"] == 1 and c["brand"]["knowledge_basis"] == "published brand version snapshot"


def test_validation_and_isolation(world, customers):
    cd = world["c"].users["creative_director"]
    draft = cd.post(f"/v1/brands/{world['brand_id']}/knowledge/concepts", json={"name": "Draft concept", "definition": "x"}).json()
    r = cd.post("/v1/context/generate", json={"brand_id": world["brand_id"], "task_type": "graphic_design", "concept_ids": [draft["id"]]})
    assert r.status_code == 422
    assert cd.post("/v1/context/generate", json={"brand_id": world["brand_id"], "task_type": "nope"}).status_code == 422
    a = customers["A"].admin
    assert a.post("/v1/context/generate", json={"brand_id": world["brand_id"], "task_type": "website_design"}).status_code == 404
    assert a.post("/v1/context/preview", json={"brand_id": world["brand_id"], "task_type": "website_design"}).status_code == 404
