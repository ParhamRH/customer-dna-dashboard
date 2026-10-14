"""Shared, session-scoped fixture: a richly populated brand in customer C (search + context tests)."""
from __future__ import annotations

import pytest

from app.jobs.queue import drain
from tests.media_fixtures import upload


@pytest.fixture(scope="session")
def world(customers):
    """A fresh brand in customer C with assets, concepts, principles and guidelines."""
    c = customers["C"]
    cd = c.users["creative_director"]
    brand = cd.post("/v1/brands", headers={}, json={"name": "Search Lab"})
    if brand.status_code == 403:  # creative directors can manage brands
        raise AssertionError(brand.text)
    bid = brand.json()["id"]
    ids = {}
    for name, title in [("organic.jpg", "Soft forms study"), ("organic2.jpg", "Second soft forms study"),
                        ("architectural.jpg", "Concrete grid facade"), ("dramatic.jpg", "Night lamp"),
                        ("vibrant.png", "Festival poster"), ("material.jpg", "Linen texture close-up"),
                        ("film.mp4", "Studio film"), ("guidelines.pdf", "Photography rules")]:
        r = upload(cd, bid, name, title=title)
        assert r.status_code == 201, r.text
        ids[name] = r.json()["id"]
    base = f"/v1/brands/{bid}/knowledge/concepts"
    organic = cd.post(base, json={"name": "Organic geometry", "definition": "Curvilinear, biomorphic, flowing forms.",
                                  "synonyms": ["biomorphic forms"], "example_asset_ids": [ids["organic.jpg"], ids["organic2.jpg"]]}).json()
    material = cd.post(base, json={"name": "Material expression", "definition": "Tactile surfaces, visible grain and texture.",
                                   "example_asset_ids": [ids["material.jpg"]]}).json()
    for cid in (organic["id"], material["id"]):
        cd.post(f"/v1/knowledge/concepts/{cid}/approve")
    p = cd.post(f"/v1/brands/{bid}/knowledge/principles", json={
        "title": "Let forms breathe", "statement": "Organic forms need generous negative space.", "classification": "preferred",
        "concept_ids": [organic["id"]], "scope": {"project_types": ["website_design"]}}).json()
    cd.post(f"/v1/knowledge/principles/{p['id']}/approve")
    g = cd.post(f"/v1/brands/{bid}/knowledge/guidelines", json={
        "title": "Web layout guideline", "domain_key": "design_language", "summary": "How pages are composed.",
        "body": "Use a 12-column grid with wide margins. Hero imagery is full-bleed.", "applies_to": {"project_types": ["website_design"]}}).json()
    cd.post(f"/v1/knowledge/guidelines/{g['id']}/approve")
    cd.post(f"/v1/brands/{bid}/knowledge/guidelines", json={"title": "Packaging guideline", "domain_key": "visual_identity",
                                                              "body": "Boxes use uncoated stock.", "applies_to": {"project_types": ["packaging"]}})
    cd.post("/v1/assets/bulk", json={"asset_ids": [ids["organic.jpg"], ids["material.jpg"], ids["film.mp4"]], "action": "set_approval", "value": "approved"})
    drain()
    return {"c": c, "brand_id": bid, "ids": ids, "organic": organic, "principle": p, "guideline": g}


