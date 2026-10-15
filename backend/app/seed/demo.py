"""DEMO DATA — three fictional customers, generated through the real API (development only).

Every name, brand, rule and asset here is invented. Media files are synthesised on the fly
(app/seed/media.py). Run:  python -m app.cli seed-demo
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.jobs.queue import drain
from app.seed import media as m

log = logging.getLogger("bdna.seed")
DEMO_PASSWORD = "demo-password-2026"  # DEVELOPMENT ONLY — printed by the seed command


class Api:
    def __init__(self, client: TestClient, token: str, org: str | None = None):
        self.c, self.t, self.org = client, token, org

    def _h(self) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.t}"}
        if self.org:
            h["X-Organization-Id"] = self.org
        return h

    def get(self, url: str, **kw: Any) -> Any:
        r = self.c.get(url, headers=self._h(), **kw)
        r.raise_for_status()
        return r.json()

    def post(self, url: str, ok=(200, 201, 202), **kw: Any) -> Any:
        r = self.c.post(url, headers=self._h(), **kw)
        if r.status_code not in ok:
            raise RuntimeError(f"POST {url} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else None


def _login(client: TestClient, email: str, password: str) -> str:
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    client.cookies.clear()
    return r.json()["access_token"]


CUSTOMERS: list[dict[str, Any]] = [
    {
        "slug": "aurora-atelier",
        "name": "Aurora Atelier",
        "industry": "Skincare & wellbeing",
        "country": "Germany",
        "brand": {"name": "Aurora", "tagline": "Quiet rituals, sculpted by nature.",
                  "description": "A fictional premium skincare house whose identity is built on organic geometry, tactile materials and soft northern daylight."},
        "palette": [("Primary", "primary", [("Sand", "#E9E1D4", "Backgrounds, packaging base"), ("Clay", "#C9B79C", "Secondary surfaces"),
                                            ("Moss", "#5B6B4E", "Accents, botanical cues"), ("Ink", "#1B1F2A", "Text and logo")]),
                    ("Accent", "accent", [("Ember", "#B4623A", "Sparing highlights, CTAs")])],
        "type": [("Display", "display", "Cormorant Garamond", "Georgia, serif", [300, 500],
                  [("h1", 64, 1.05, 300), ("h2", 44, 1.1, 300), ("h3", 28, 1.2, 500)]),
                 ("Body", "body", "Inter", "Helvetica Neue, Arial, sans-serif", [400, 600], [("body", 17, 1.6, 400), ("caption", 13, 1.4, 400)])],
        "concepts": [
            ("Organic geometry", "Curvilinear, biomorphic forms derived from nature — soft-edged, flowing, never mechanical.", "core", ["biomorphic forms", "curvilinear geometry"]),
            ("Sculptural minimalism", "Few, calm, volumetric elements arranged with generous negative space.", "core", ["quiet minimalism"]),
            ("Material expression", "Tactile surfaces with visible grain: honed stone, raw linen, unglazed clay.", "supporting", ["tactile materiality"]),
            ("Cinematic atmosphere", "Slow, contemplative moving image with soft directional light.", "supporting", ["filmic calm"]),
            ("Brutalist aesthetics", "Raw, heavy, monumental concrete forms with harsh contrast.", "avoid", []),
            ("Neon maximalism", "Saturated neon colour, dense layering and loud graphics.", "avoid", []),
        ],
        "related": [("Organic geometry", "Sculptural minimalism"), ("Material expression", "Organic geometry")],
        "opposes": [("Organic geometry", "Brutalist aesthetics"), ("Sculptural minimalism", "Neon maximalism")],
        "principles": [
            ("Daylight first", "Photograph in natural, diffused daylight; no on-camera flash.", "mandatory", "art_direction", [], ["Window light at 45°"], ["Ring lights", "Hard flash"]),
            ("Let forms breathe", "Every layout keeps at least 40% negative space around the hero form.", "preferred", "design_language", ["website_design", "presentation"], [], []),
            ("Palette discipline", "Use only the approved palette; Ember appears on at most 5% of any surface.", "mandatory", "visual_identity", [], [], []),
            ("No neon, no gloss", "Never use neon colours, chrome, or high-gloss plastic finishes.", "prohibited", "art_direction", [], [], ["Neon gradients", "Chrome type"]),
            ("Human, quiet copy", "Headlines are short, warm and declarative; no exclamation marks.", "mandatory", "brand_language", [], ["“Made for slow mornings.”"], ["“Glow like never before!!!”"]),
            ("Motion is slow", "Camera moves are slow pushes or drifts; average shot length above 3 seconds.", "preferred", "art_direction", ["video_production", "social_media"], [], []),
            ("Seasonal accents", "For seasonal campaigns, one additional accent colour may be introduced with creative director sign-off.", "context_dependent", "visual_identity", ["branding_campaign"], [], []),
            ("Explore 3D clay renders", "Test soft clay-like 3D renders of product forms for digital channels.", "experimental", "art_direction", ["social_media"], [], []),
        ],
        "guidelines": [
            ("Web layout", "design_language", ["website_design", "website_development"], "How Aurora pages are composed.",
             "Use a 12-column grid with 120px outer margins on desktop. Hero sections are full-bleed imagery with a single serif headline. Body copy never exceeds 68 characters per line. Motion: fade-and-rise, 600ms, ease-out."),
            ("Product photography", "art_direction", ["product_design", "advertising", "social_media"], "Shooting product.",
             "Products sit on honed stone or raw linen. Shoot at eye level or slightly above with a 50–85mm lens. Shadows are soft and fall to the right."),
            ("Packaging", "visual_identity", ["packaging"], "Packaging system.", "Uncoated Sand stock, debossed logo, Ink typography. No foils."),
        ],
        "entries": [
            ("brand_foundation", "mission", "Mission", "Make daily care a quiet, sensory ritual.", {}),
            ("brand_foundation", "vision", "Vision", "A calmer relationship between people and their skin.", {}),
            ("brand_foundation", "positioning", "Positioning", "Premium, nature-derived skincare for people who value calm over hype.",
             {"statement": "For mindful adults, Aurora is the skincare ritual that feels like stepping into soft daylight.", "category": "Premium skincare"}),
            ("brand_foundation", "personality", "Personality", "Calm, precise, generous.",
             {"traits": [{"trait": "Calm", "is": "unhurried", "is_not": "sleepy"}, {"trait": "Precise", "is": "exact", "is_not": "clinical"}]}),
            ("brand_foundation", "core_values", "Core values", "What we will not compromise.",
             {"values": [{"name": "Care", "description": "For skin and for the planet."}, {"name": "Clarity", "description": "Honest ingredients, honest words."}]}),
            ("brand_foundation", "target_audience", "Target audience", "Who Aurora is for.",
             {"segments": [{"name": "Mindful professionals", "description": "30–55, urban, value rituals", "needs": "Calm, efficacy"}]}),
            ("art_direction", "lighting", "Lighting", "Soft, directional northern daylight.",
             {"objective_observations": ["single soft key light", "shadow falls to the right", "high-key exposure"], "aesthetic_interpretation": "calm, intimate, morning"}),
            ("art_direction", "materials", "Materials", "Honed stone, raw linen, unglazed clay.",
             {"objective_observations": ["matte surfaces", "visible grain"], "aesthetic_interpretation": "tactile, grounded", "dont": ["gloss", "chrome"]}),
            ("design_language", "animation_motion", "Motion", "Slow and confident.", {"rules": ["600ms fade-and-rise", "no bounce easing"]}),
            ("brand_language", "tone_of_voice", "Tone of voice", "Warm, precise, unhurried.",
             {"traits": [{"trait": "Warm", "is": "generous", "is_not": "saccharine"}, {"trait": "Precise", "is": "specific", "is_not": "technical"}]}),
            ("brand_language", "restricted_expressions", "Restricted expressions", "Words we never use.",
             {"expressions": [{"term": "anti-aging", "use_instead": "skin longevity", "reason": "fear-based"}, {"term": "miracle", "use_instead": "considered", "reason": "overclaiming"}]}),
            ("brand_language", "approved_examples", "Approved examples", "Copy that sounds like us.",
             {"examples": [{"text": "Made for slow mornings.", "context": "hero headline"}, {"text": "Clay, oat and time.", "context": "product name line"}]}),
        ],
        "tokens": [("spacing.4", "dimension", "16px", "spacing"), ("spacing.8", "dimension", "32px", "spacing"), ("radius.soft", "dimension", "14px", "radius"),
                   ("motion.duration.base", "duration", "600ms", "motion"), ("motion.easing.calm", "cubicBezier", [0.22, 1, 0.36, 1], "motion")],
        "media": "aurora",
        "project": ("Website relaunch 2027", "website_design", "A calmer, image-led website for the new ritual collection."),
    },
    {
        "slug": "northwind-mobility",
        "name": "Northwind Mobility",
        "industry": "Urban mobility",
        "country": "Netherlands",
        "brand": {"name": "Northwind", "tagline": "Engineered for the city.",
                  "description": "A fictional e-bike maker with an industrial, architectural identity and bold signal colours."},
        "palette": [("Core", "primary", [("Graphite", "#1F2A33", "Primary surfaces"), ("Steel", "#7AA6C2", "Secondary"), ("Fog", "#E8EDF0", "Backgrounds")]),
                    ("Signal", "accent", [("Signal Orange", "#FF6A13", "Calls to action"), ("Volt", "#D4FF3A", "Data highlights")])],
        "type": [("Display", "display", "Space Grotesk", "Arial, sans-serif", [500, 700], [("h1", 72, 1.0, 700), ("h2", 48, 1.05, 700)]),
                 ("Body", "body", "IBM Plex Sans", "Arial, sans-serif", [400, 500], [("body", 16, 1.55, 400)])],
        "concepts": [
            ("Industrial elegance", "Precision engineering made beautiful: machined edges, visible structure, restrained colour.", "core", ["engineered beauty"]),
            ("Architectural composition", "Strong verticals and horizontals, grids, and urban structure framing the subject.", "core", ["grid composition"]),
            ("Kinetic energy", "Fast cuts, motion blur and dynamic diagonals that express speed.", "supporting", ["dynamic motion"]),
            ("Organic geometry", "Soft biomorphic forms.", "neutral", []),
        ],
        "related": [("Industrial elegance", "Architectural composition")],
        "opposes": [("Architectural composition", "Organic geometry")],
        "principles": [
            ("Structure is visible", "Show the frame, welds and mechanics — never hide engineering.", "mandatory", "art_direction", [], [], []),
            ("Signal colour sparingly", "Signal Orange marks interaction only; never as a background.", "mandatory", "visual_identity", [], [], []),
            ("City as stage", "Shoot in real urban architecture at blue hour or overcast daylight.", "preferred", "art_direction", [], [], []),
            ("No lifestyle clichés", "Avoid sunset silhouettes and staged laughing riders.", "prohibited", "art_direction", [], [], []),
        ],
        "guidelines": [("App interface", "design_language", ["digital_application", "website_design"], "Ride app UI.",
                        "Dark Graphite UI, 8px grid, data in IBM Plex Sans tabular numerals, Volt for live metrics only.")],
        "entries": [
            ("brand_foundation", "mission", "Mission", "Make the city faster to move through, beautifully.", {}),
            ("brand_language", "tone_of_voice", "Tone of voice", "Direct, technical, confident.", {"traits": [{"trait": "Direct", "is": "short", "is_not": "rude"}]}),
        ],
        "tokens": [("spacing.2", "dimension", "8px", "spacing"), ("motion.duration.fast", "duration", "180ms", "motion")],
        "media": "northwind",
        "project": ("Spring campaign", "branding_campaign", "Launch of the N3 commuter bike."),
    },
    {
        "slug": "kiln-and-thread",
        "name": "Kiln & Thread",
        "industry": "Craft homeware",
        "country": "Portugal",
        "brand": {"name": "Kiln & Thread", "tagline": "Made slowly, by hand.",
                  "description": "A fictional ceramics and textiles studio celebrating material, warmth and editorial storytelling."},
        "palette": [("Earth", "primary", [("Terracotta", "#B65F3C", "Signature colour"), ("Oat", "#EDE3D1", "Backgrounds"), ("Walnut", "#4A3428", "Text")])],
        "type": [("Editorial", "display", "Fraunces", "Georgia, serif", [400, 700], [("h1", 56, 1.1, 400)]),
                 ("Text", "body", "Source Serif 4", "Georgia, serif", [400], [("body", 18, 1.65, 400)])],
        "concepts": [
            ("Material expression", "The material is the hero: clay, glaze, woven fibre, close and tactile.", "core", ["tactile materiality"]),
            ("Editorial visual language", "Magazine-like layouts, generous margins, serif typography and captions.", "core", ["editorial layout"]),
            ("Warm atmosphere", "Late-afternoon warmth, amber light, lived-in interiors.", "supporting", []),
        ],
        "related": [("Material expression", "Warm atmosphere")],
        "opposes": [],
        "principles": [
            ("Show the hand", "Every product story shows the maker's hand or tool marks.", "mandatory", "art_direction", [], [], []),
            ("Captions tell provenance", "Product images carry a caption naming material and maker.", "preferred", "brand_language", [], [], []),
        ],
        "guidelines": [("Journal layout", "design_language", ["website_design", "presentation"], "Editorial journal pages.",
                        "Two-column serif text, full-width images with captions, 1:1.414 page proportions.")],
        "entries": [("brand_foundation", "story", "Brand story", "Founded in a Porto courtyard by a potter and a weaver.", {})],
        "tokens": [],
        "media": "kiln",
        "project": ("Autumn journal", "presentation", "Seasonal lookbook."),
    },
]


def _media(kind: str, d: Path) -> list[tuple[Path, dict[str, Any]]]:
    out: list[tuple[Path, dict[str, Any]]] = []
    if kind == "aurora":
        pal = ("#ece4d7", "#d2c3a8", "#8f7d62", "#5b6b4e")
        for i in range(4):
            out.append((m.image_organic(d / f"aurora-ritual-{i + 1}.jpg", palette=pal, seed=40 + i),
                        {"title": f"Ritual still life {i + 1}", "category": "photography", "tags": "ritual, still life", "reference_role": "official"}))
        out.append((m.image_material(d / "aurora-linen.jpg", base="#b9a88e", seed=7), {"title": "Raw linen texture", "category": "material study", "tags": "linen, texture"}))
        out.append((m.image_material(d / "aurora-stone.jpg", base="#9d968c", seed=9), {"title": "Honed stone surface", "category": "material study", "tags": "stone"}))
        out.append((m.image_dramatic(d / "aurora-evening.jpg", key="#d9a441"), {"title": "Evening ritual (inspiration)", "reference_role": "inspiration"}))
        out.append((m.image_architectural(d / "aurora-brutal.jpg", bg="#3a3a3a", line="#bdbdbd", accent="#777777"), {"title": "Concrete stairwell (off-brand)", "reference_role": "inspiration"}))
        out.append((m.image_vibrant(d / "aurora-neon.png", colors=("#ff2bd6", "#00f0ff", "#faff00", "#7a00ff", "#ff5e00")), {"title": "Neon festival poster (do not use)", "reference_role": "external"}))
        out.append((m.svg_logo(d / "aurora-logo.svg", "Aurora", "#1B1F2A", "#5B6B4E"), {"title": "Aurora primary logo", "asset_type": "logo", "category": "logo", "subcategory": "primary"}))
        out.append((m.obj_model(d / "aurora-vessel.obj", "torus"), {"title": "Ritual vessel form study", "category": "product form", "asset_type": "model_3d"}))
        # slow push-in, slow pan, locked-off — the shots a calm brand film is made of
        out.append((m.video_from_images(d / "aurora-film.mp4", [out[0][0], out[1][0], out[5][0]], ["zoom_in", "pan_right", "static"], seconds=3.5),
                    {"title": "Morning ritual film", "category": "brand film", "tags": "film, ritual"}))
        out.append((m.pdf_guidelines(d / "aurora-guidelines.pdf", "Aurora — Photography & Voice Notes", [
            ("Photography", ["Always photograph in natural, diffused daylight.", "Never use on-camera flash or ring lights.",
                             "Compositions should leave generous negative space around the product."]),
            ("Materials", ["We prefer honed stone, raw linen and unglazed clay as surfaces.", "Avoid chrome, gloss and plastic props."]),
            ("Voice", ["Headlines must be short and warm.", "Do not use exclamation marks.", "When writing for social media, captions may be playful but stay calm."]),
        ], author="Aurora Atelier (fictional)"), {"title": "Photography & voice notes", "category": "guidelines"}))
    elif kind == "northwind":
        for i in range(3):
            out.append((m.image_architectural(d / f"nw-city-{i + 1}.jpg", bg=["#1f2a33", "#26333d", "#18222a"][i], seed=60 + i),
                        {"title": f"City structure {i + 1}", "category": "photography", "tags": "city, architecture"}))
        out.append((m.image_vibrant(d / "nw-signal.png", colors=("#ff6a13", "#1f2a33", "#d4ff3a", "#7aa6c2", "#e8edf0")), {"title": "Signal poster", "category": "campaign"}))
        out.append((m.svg_logo(d / "nw-logo.svg", "Northwind", "#1F2A33", "#FF6A13"), {"title": "Northwind wordmark", "asset_type": "logo", "category": "logo", "subcategory": "primary"}))
        out.append((m.obj_model(d / "nw-frame.obj", "stepped"), {"title": "Frame junction study", "asset_type": "model_3d"}))
        out.append((m.video_from_images(d / "nw-ride.mp4", [out[0][0], out[1][0], out[3][0], out[2][0]], ["pan_left", "pan_right", "static", "tilt_up"], seconds=1.5),
                    {"title": "Commute cut-down", "category": "social video"}))
    else:
        for i, base in enumerate(["#b65f3c", "#8c6b4f", "#c9a27e"]):
            out.append((m.image_material(d / f"kt-clay-{i + 1}.jpg", base=base, seed=80 + i), {"title": f"Glaze study {i + 1}", "category": "material study", "tags": "clay, glaze"}))
        out.append((m.image_organic(d / "kt-studio.jpg", palette=("#ede3d1", "#d8b48f", "#b65f3c", "#4a3428"), seed=90), {"title": "Studio afternoon", "category": "photography"}))
        out.append((m.pdf_guidelines(d / "kt-journal.pdf", "Kiln & Thread — Journal Style", [
            ("Images", ["Always show the maker's hand or tool marks.", "Prefer warm afternoon light."]),
            ("Words", ["Captions must name the material and the maker.", "Avoid superlatives such as 'best' or 'perfect'."]),
        ], author="Kiln & Thread (fictional)"), {"title": "Journal style notes", "category": "guidelines"}))
    return out


def seed(admin_email: str, admin_password: str, process_jobs: bool = True) -> dict[str, Any]:
    from app.main import create_app
    from app.services.accounts import create_platform_admin

    create_platform_admin(admin_email, "Platform Administrator", admin_password)
    app = create_app()
    summary: dict[str, Any] = {"platform_admin": admin_email, "customers": []}
    with TestClient(app) as client:
        root = Api(client, _login(client, admin_email, admin_password))
        existing = {o["slug"] for o in root.get("/v1/organizations")["items"]}
        work = Path(tempfile.mkdtemp(prefix="bdna-demo-"))
        for spec in CUSTOMERS:
            if spec["slug"] in existing:
                log.info("customer %s exists — skipping", spec["slug"])
                continue
            info = _seed_customer(client, root, spec, work)
            summary["customers"].append(info)
            if process_jobs:
                drain()
                _post_process(client, spec, info)
                drain()
    return summary


def _seed_customer(client: TestClient, root: Api, spec: dict[str, Any], work: Path) -> dict[str, Any]:
    slug = spec["slug"]
    org = root.post("/v1/organizations", json={
        "name": spec["name"], "slug": slug, "industry": spec["industry"], "country": spec["country"],
        "first_brand_name": spec["brand"]["name"], "admin_email": f"admin@{slug}.example", "admin_password": DEMO_PASSWORD,
        "contact_email": f"studio@{slug}.example", "legal_name": f"{spec['name']} (fictional demo customer)",
        "notes": "DEMO DATA — fictional customer generated by `python -m app.cli seed-demo`.",
    })
    admin = Api(client, _login(client, f"admin@{slug}.example", DEMO_PASSWORD), org["organization_id"])
    for role in ("creative_director", "editor", "reviewer", "viewer"):
        admin.post("/v1/workspace/members", json={"email": f"{role.replace('_', '.')}@{slug}.example", "role": role,
                                                  "password": DEMO_PASSWORD, "full_name": role.replace("_", " ").title()})
    cd = Api(client, _login(client, f"creative.director@{slug}.example", DEMO_PASSWORD), org["organization_id"])
    bid = org["brand_id"]
    client.patch(f"/v1/brands/{bid}", headers=cd._h(), json={"tagline": spec["brand"]["tagline"], "description": spec["brand"]["description"]})

    # Visual identity
    for pname, role, colors in spec["palette"]:
        pal = cd.post(f"/v1/brands/{bid}/palettes", json={"name": pname, "role": role, "status": "approved"})
        for i, (cname, hexv, usage) in enumerate(colors):
            cd.post(f"/v1/palettes/{pal['id']}/colors", json={"name": cname, "hex": hexv, "usage": usage, "sort_order": i})
    for i, (name, role, fam, fb, weights, levels) in enumerate(spec["type"]):
        cd.post(f"/v1/brands/{bid}/typography", json={
            "name": name, "role": role, "family": fam, "fallback_stack": fb, "weights": weights, "status": "approved", "sort_order": i,
            "source": "google", "license": "SIL Open Font License",
            "hierarchy": [{"level": lv, "size_px": sz, "line_height": lh, "weight": w} for lv, sz, lh, w in levels]})
    for path, ttype, value, cat in spec["tokens"]:
        cd.post(f"/v1/brands/{bid}/design-tokens", json={"path": path, "token_type": ttype, "value": value, "category": cat, "status": "approved"})

    # Ontology
    concept_ids: dict[str, str] = {}
    for name, definition, relevance, synonyms in spec["concepts"]:
        c = cd.post(f"/v1/brands/{bid}/knowledge/concepts", json={"name": name, "definition": definition, "brand_relevance": relevance, "synonyms": synonyms})
        concept_ids[name] = c["id"]
        cd.post(f"/v1/knowledge/concepts/{c['id']}/approve")
    for a, b in spec["related"]:
        client.patch(f"/v1/knowledge/concepts/{concept_ids[a]}", headers=cd._h(), json={"related_concept_ids": [concept_ids[b]]})
        cd.post(f"/v1/knowledge/concepts/{concept_ids[a]}/approve", ok=(200, 422))
    for a, b in spec["opposes"]:
        client.patch(f"/v1/knowledge/concepts/{concept_ids[a]}", headers=cd._h(), json={"opposing_concept_ids": [concept_ids[b]]})
        cd.post(f"/v1/knowledge/concepts/{concept_ids[a]}/approve", ok=(200, 422))

    # Knowledge
    for domain, etype, title, summary, structured in spec["entries"]:
        e = cd.post(f"/v1/brands/{bid}/knowledge/entries", json={"domain_key": domain, "entry_type": etype, "title": title,
                                                                  "summary": summary, "body": summary, "structured": structured})
        cd.post(f"/v1/knowledge/entries/{e['id']}/approve")
    for i, (title, stmt, cls, domain, pts, do, dont) in enumerate(spec["principles"]):
        p = cd.post(f"/v1/brands/{bid}/knowledge/principles", json={
            "title": title, "statement": stmt, "classification": cls, "domain_key": domain, "priority": 10 + i * 5,
            "scope": {"project_types": pts} if pts else {}, "examples": {"do": do, "dont": dont},
            "rationale": "Defined with the creative director during the brand DNA workshop (fictional)."})
        if cls != "experimental":
            cd.post(f"/v1/knowledge/principles/{p['id']}/approve")
    for title, domain, pts, summary, body in spec["guidelines"]:
        g = cd.post(f"/v1/brands/{bid}/knowledge/guidelines", json={"title": title, "domain_key": domain, "summary": summary,
                                                                     "body": body, "applies_to": {"project_types": pts}})
        cd.post(f"/v1/knowledge/guidelines/{g['id']}/approve")

    # Assets
    editor = Api(client, _login(client, f"editor@{slug}.example", DEMO_PASSWORD), org["organization_id"])
    media_dir = work / slug
    media_dir.mkdir(parents=True, exist_ok=True)
    asset_ids: dict[str, str] = {}
    for path, meta in _media(spec["media"], media_dir):
        r = client.post(f"/v1/brands/{bid}/assets", headers=editor._h(), files={"file": (path.name, path.read_bytes())},
                        data={k: v for k, v in meta.items()})
        if r.status_code != 201:
            raise RuntimeError(f"upload {path.name}: {r.status_code} {r.text[:300]}")
        asset_ids[meta["title"]] = r.json()["id"]
    name, ptype, desc = spec["project"]
    cd.post(f"/v1/brands/{bid}/projects", json={"name": name, "project_type": ptype, "description": desc, "status": "active",
                                                "concept_ids": [v for k, v in concept_ids.items() if k in [c[0] for c in spec["concepts"] if c[2] == "core"]]})
    return {"slug": slug, "organization_id": org["organization_id"], "brand_id": bid, "concepts": concept_ids, "assets": asset_ids,
            "login": f"admin@{slug}.example"}


def _post_process(client: TestClient, spec: dict[str, Any], info: dict[str, Any]) -> None:
    """Simulate a realistic review state: some interpretations approved, examples linked, a version published,
    while leaving a healthy review queue for the demo."""
    slug, org, bid = info["slug"], info["organization_id"], info["brand_id"]
    cd = Api(client, _login(client, f"creative.director@{slug}.example", DEMO_PASSWORD), org)
    rv = Api(client, _login(client, f"reviewer@{slug}.example", DEMO_PASSWORD), org)
    assets = cd.get("/v1/assets", params={"brand_id": bid, "limit": 200})["items"]
    good = [a for a in assets if a["reference_role"] == "official"]
    # approve official references and half of the AI interpretations
    if good:
        cd.post("/v1/assets/bulk", json={"asset_ids": [a["id"] for a in good], "action": "set_approval", "value": "approved"})
    analyses = rv.get("/v1/review/analyses", params={"brand_id": bid, "limit": 100})["items"]
    for x in analyses[: max(1, len(analyses) // 2)]:
        rv.post(f"/v1/review/analyses/{x['id']}", json={"decision": "approve", "accept_suggested_tags": True})
    # accept the most confident concept links, keep the rest pending
    links = rv.get("/v1/review/suggestions", params={"brand_id": bid, "suggestion_type": "concept_link", "limit": 100})["items"]
    # a reviewer would only accept links for the brand's own official material; links proposed for
    # inspiration or off-brand references stay in the queue for a human to judge
    official_ids = {a["id"] for a in good}
    on_brand = [s for s in links if (s.get("payload") or {}).get("asset_id") in official_ids]
    for s in on_brand[: max(1, len(on_brand) // 2)]:
        cd.post(f"/v1/review/suggestions/{s['id']}", json={"decision": "accept"})
    # ensure each core concept has at least one approved example
    concepts = info["concepts"]
    examples = {
        "aurora": {"Organic geometry": ["Ritual still life 1", "Ritual still life 2"], "Material expression": ["Raw linen texture", "Honed stone surface"],
                   "Sculptural minimalism": ["Ritual still life 3", "Ritual vessel form study"], "Cinematic atmosphere": ["Morning ritual film"]},
        "northwind": {"Architectural composition": ["City structure 1", "City structure 2"], "Industrial elegance": ["Frame junction study"],
                      "Kinetic energy": ["Commute cut-down", "Signal poster"]},
        "kiln": {"Material expression": ["Glaze study 1", "Glaze study 2"], "Warm atmosphere": ["Studio afternoon"]},
    }[spec["media"]]
    for cname, titles in examples.items():
        for t in titles:
            aid = info["assets"].get(t)
            if aid and cname in concepts:
                client.post("/v1/relationships", headers=cd._h(), json={"source_type": "asset", "source_id": aid, "relation_type": "exemplifies",
                                                                         "target_type": "aesthetic_concept", "target_id": concepts[cname]})
    # Collections: a curated set of approved references and a moodboard of inspiration material
    by_role: dict[str, list[str]] = {}
    for a in assets:
        by_role.setdefault(a["reference_role"], []).append(a["id"])
    if by_role.get("official"):
        hero = cd.post(f"/v1/brands/{bid}/collections", json={
            "name": "Hero references", "kind": "curated_set", "asset_ids": by_role["official"][:8],
            "description": "Approved references that best express the brand. Start every brief here."})
        images = [a["id"] for a in assets if a["reference_role"] == "official" and a["asset_type"] == "image"]
        if images:
            client.patch(f"/v1/collections/{hero['id']}", headers=cd._h(), json={"cover_asset_id": images[0]})
        projects = cd.get(f"/v1/brands/{bid}/projects")["items"]
        if projects:
            client.patch(f"/v1/projects/{projects[0]['id']}", headers=cd._h(), json={"asset_ids": by_role["official"][:4]})
    loose = by_role.get("inspiration", []) + by_role.get("external", [])
    if loose:
        cd.post(f"/v1/brands/{bid}/collections", json={
            "name": "Moodboard — next season", "kind": "moodboard", "asset_ids": loose[:8],
            "description": "Inspiration only. Not official brand material."})
    cd.post(f"/v1/brands/{bid}/versions", json={"label": "Brand DNA v1 (demo)", "notes": "Initial published brand knowledge."})
