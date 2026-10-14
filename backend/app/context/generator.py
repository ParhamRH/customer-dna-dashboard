"""Creative Context Generator: assembles task-specific, traceable brand context packages.

Only official (human-approved) knowledge is used for rules. Reference assets may be pending —
they are then labelled explicitly. Every item carries its source id + version, and the package
records the brand version it was built against.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import jsonable
from app.api.errors import NotFound, ValidationFailed
from app.context.templates import MODE_LIMITS, TEMPLATES
from app.models import (
    Asset,
    AssetAnalysis,
    Brand,
    BrandVersion,
    CollectionAsset,
    ContextPackage,
    Project,
    Relationship,
)
from app.services import knowledge as ks


@dataclass
class ContextRequest:
    brand_id: uuid.UUID
    task_type: str
    project_id: uuid.UUID | None = None
    output_medium: str | None = None
    mode: str = "standard"
    domains: list[str] | None = None
    concept_ids: list[uuid.UUID] = field(default_factory=list)
    creative_direction: str | None = None
    reference_asset_ids: list[uuid.UUID] = field(default_factory=list)
    collection_ids: list[uuid.UUID] = field(default_factory=list)
    auto_references: bool = True
    title: str | None = None
    use_published_version: bool = False


def _src(sources: list[dict[str, Any]], etype: str, obj: dict[str, Any], label: str) -> str:
    sid = f"{etype}:{obj['id']}"
    if not any(s["ref"] == sid for s in sources):
        sources.append({"ref": sid, "type": etype, "id": str(obj["id"]), "version": obj.get("official_version") or obj.get("version"),
                        "status": obj.get("status"), "label": label})
    return sid


def _trim(text: str | None, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _matches_task(scope_types: list[str], template: dict[str, Any], project: Project | None) -> bool:
    if not scope_types:
        return True
    wanted = set(template.get("project_types", [])) | ({project.project_type} if project else set())
    return bool(set(scope_types) & wanted)


def _official(db: Session, brand_id: uuid.UUID, use_snapshot: bool) -> tuple[dict[str, list[dict[str, Any]]], BrandVersion | None]:
    brand = db.scalar(select(Brand).where(Brand.id == brand_id))
    version = db.scalar(select(BrandVersion).where(BrandVersion.id == brand.current_version_id)) if brand.current_version_id else None
    if use_snapshot:
        if version is None:
            raise ValidationFailed("This brand has no published version yet")
        snap = version.snapshot
        return {
            "principle": snap.get("principles", []), "guideline": snap.get("guidelines", []),
            "aesthetic_concept": snap.get("aesthetic_concepts", []), "knowledge_entry": snap.get("knowledge_entries", []),
            "palettes": snap.get("palettes", []), "typography": snap.get("typography_systems", []),
            "design_tokens": snap.get("design_tokens", []),
        }, version
    from app.api.v1.visual_identity import palettes_payload, typography_payload

    data = {et: ks.official_items(db, et, brand_id) for et in ("principle", "guideline", "aesthetic_concept", "knowledge_entry")}
    data["palettes"] = palettes_payload(db, brand_id, approved_only=True)
    data["typography"] = typography_payload(db, brand_id, approved_only=True)
    return data, version


def _asset_reference(db: Session, a: Asset, reason: str, body_chars: int) -> dict[str, Any]:
    analysis = None
    if a.approved_analysis_id:
        analysis = db.scalar(select(AssetAnalysis).where(AssetAnalysis.id == a.approved_analysis_id))
    interp_status = "approved interpretation" if analysis else None
    if analysis is None:
        analysis = db.scalar(select(AssetAnalysis).where(AssetAnalysis.asset_id == a.id, AssetAnalysis.status == "pending_review")
                             .order_by(AssetAnalysis.created_at.desc()).limit(1))
        interp_status = "UNREVIEWED AI interpretation" if analysis else "no interpretation"
    mm = a.media_metadata or {}
    o, i = (analysis.objective if analysis else {}) or {}, (analysis.interpretive if analysis else {}) or {}
    ref = {
        "id": str(a.id), "title": a.title, "asset_type": a.asset_type, "reference_role": a.reference_role,
        "approval_status": a.approval_status, "selected_because": reason,
        "palette": [c.get("hex") for c in mm.get("palette", [])[:6]],
        "dimensions": [mm.get("width"), mm.get("height")] if mm.get("width") else None,
        "interpretation_status": interp_status,
        "summary": _trim(i.get("summary") or o.get("description"), body_chars),
        "atmosphere": i.get("atmosphere", [])[:6], "visual_style": i.get("visual_style", [])[:6],
        "lighting": o.get("lighting") if isinstance(o.get("lighting"), dict) else None,
        "composition": o.get("composition") if isinstance(o.get("composition"), dict) else None,
    }
    if a.asset_type in ("video", "animation") and mm.get("motion"):
        ref["motion"] = {k: mm["motion"].get(k) for k in ("overall_camera_movement", "pace", "average_shot_length_s", "cuts_per_minute")}
        ref["scenes"] = [{"start_s": s["start_s"], "end_s": s["end_s"], "camera_movement": s.get("camera_movement")} for s in mm.get("scenes", [])[:12]]
        ref["duration_seconds"] = mm.get("duration_seconds")
    return ref


def select_context(db: Session, org_id: uuid.UUID, req: ContextRequest) -> dict[str, Any]:
    if req.task_type not in TEMPLATES:
        raise ValidationFailed("Unknown task type", details={"allowed": list(TEMPLATES)})
    if req.mode not in MODE_LIMITS:
        raise ValidationFailed("Unknown mode")
    tpl = TEMPLATES[req.task_type]
    lim = MODE_LIMITS[req.mode]
    brand = db.scalar(select(Brand).where(Brand.id == req.brand_id))
    if brand is None:
        raise NotFound("Brand not found")
    project = None
    if req.project_id:
        project = db.scalar(select(Project).where(Project.id == req.project_id, Project.brand_id == brand.id))
        if project is None:
            raise NotFound("Project not found")
    domains = req.domains or (project.selected_domains if project and project.selected_domains else None) or tpl["domains"]
    data, version = _official(db, brand.id, req.use_published_version)
    sources: list[dict[str, Any]] = []
    body = lim["body_chars"]

    # Foundation & domain entries
    entries_by_domain: dict[str, list[dict[str, Any]]] = {}
    for e in sorted(data["knowledge_entry"], key=lambda x: (x.get("domain_key"), x.get("sort_order", 0))):
        if e.get("domain_key") in domains:
            entries_by_domain.setdefault(e["domain_key"], []).append(e)
    entry_items: dict[str, list[dict[str, Any]]] = {}
    n = 0
    for d, items in entries_by_domain.items():
        for e in items:
            if n >= lim["entries"]:
                break
            entry_items.setdefault(d, []).append({
                "source": _src(sources, "knowledge_entry", e, e["title"]), "type": e["entry_type"], "title": e["title"],
                "summary": _trim(e.get("summary"), body), "body": _trim(e.get("body"), body) if req.mode != "compact" else None,
                "structured": e.get("structured") if req.mode != "compact" else None,
            })
            n += 1

    # Principles grouped by classification
    principles = [p for p in data["principle"] if (p.get("domain_key") in domains or p.get("domain_key") in (None, "principles_guidelines"))
                  and _matches_task((p.get("scope") or {}).get("project_types", []), tpl, project)]
    principles.sort(key=lambda p: (p.get("priority", 50), p.get("code", "")))
    groups: dict[str, list[dict[str, Any]]] = {}
    for p in principles[: lim["principles"]]:
        groups.setdefault(p["classification"], []).append({
            "source": _src(sources, "principle", p, f"{p['code']} {p['title']}"), "code": p["code"], "title": p["title"],
            "statement": p["statement"], "rationale": _trim(p.get("rationale"), body) if req.mode != "compact" else None,
            "examples": p.get("examples") if req.mode == "comprehensive" else None,
            "context": (p.get("scope") or {}) if p["classification"] == "context_dependent" else None,
        })

    guidelines = [g for g in data["guideline"] if g.get("domain_key") in domains
                  and _matches_task((g.get("applies_to") or {}).get("project_types", []), tpl, project)][: lim["guidelines"]]
    guideline_items = [{"source": _src(sources, "guideline", g, g["title"]), "title": g["title"], "domain": g["domain_key"],
                        "summary": _trim(g.get("summary"), body), "body": _trim(g.get("body"), body if req.mode != "compact" else 200)}
                       for g in guidelines]

    # Aesthetic concepts
    concepts = data["aesthetic_concept"]
    chosen: list[dict[str, Any]]
    if req.concept_ids:
        wanted = {str(c) for c in req.concept_ids}
        chosen = [c for c in concepts if str(c["id"]) in wanted]
        missing = wanted - {str(c["id"]) for c in chosen}
        if missing:
            raise ValidationFailed("Some concepts are not approved (only official concepts can drive context)", details=sorted(missing))
        rel_ids = set()
        for r in db.scalars(select(Relationship).where(Relationship.status == "approved", Relationship.relation_type == "related_to",
                                                       Relationship.source_type == "aesthetic_concept", Relationship.target_type == "aesthetic_concept")):
            if str(r.source_id) in wanted:
                rel_ids.add(str(r.target_id))
            if str(r.target_id) in wanted:
                rel_ids.add(str(r.source_id))
        chosen += [c for c in concepts if str(c["id"]) in rel_ids - wanted]
    else:
        chosen = [c for c in concepts if c.get("brand_relevance") in ("core", "supporting")]
    chosen.sort(key=lambda c: ({"core": 0, "supporting": 1}.get(c.get("brand_relevance"), 2), c["name"]))
    concept_items = [{"source": _src(sources, "aesthetic_concept", c, c["name"]), "name": c["name"], "definition": _trim(c["definition"], body),
                      "relevance": c.get("brand_relevance"), "synonyms": c.get("synonyms", []),
                      "attributes": c.get("attributes") if req.mode != "compact" else None}
                     for c in chosen[: lim["concepts"]]]
    avoid = [c for c in concepts if c.get("brand_relevance") == "avoid"]
    chosen_ids = {str(c["id"]) for c in chosen}
    for r in db.scalars(select(Relationship).where(Relationship.status == "approved", Relationship.relation_type == "opposes")):
        a, b = str(r.source_id), str(r.target_id)
        other = b if a in chosen_ids else a if b in chosen_ids else None
        if other:
            c = next((x for x in concepts if str(x["id"]) == other), None)
            if c and c not in avoid:
                avoid.append(c)
    prohibited = [{"source": x["source"], "statement": f"{x['code']}: {x['statement']}"} for x in groups.get("prohibited", [])]
    prohibited += [{"source": _src(sources, "aesthetic_concept", c, c["name"]), "statement": f"Avoid “{c['name']}”: {_trim(c['definition'], 200)}"} for c in avoid]
    for d in ("brand_language",):
        for e in entry_items.get(d, []):
            if e["type"] == "restricted_expressions" and e.get("structured"):
                for ex in (e["structured"] or {}).get("expressions", [])[:20]:
                    prohibited.append({"source": e["source"], "statement": f"Do not write “{ex.get('term')}”" + (f" — use “{ex['use_instead']}”" if ex.get("use_instead") else "")})

    # Visual identity
    palettes = [{"name": p["name"], "role": p["role"], "colors": [
        {"name": c["name"], "hex": c["hex"], "token": c["token_key"], "oklch": c["oklch"].get("css") if isinstance(c.get("oklch"), dict) else None,
         "usage": c.get("usage")} for c in p.get("colors", [])]} for p in data["palettes"]] if "visual_identity" in domains else []
    for p in data["palettes"]:
        if "visual_identity" in domains:
            _src(sources, "palette", {**p, "status": "approved"}, p["name"])
    typography = [{"name": t["name"], "role": t["role"], "family": t["family"], "fallback": t["fallback_stack"], "weights": t["weights"],
                   "hierarchy": t["hierarchy"] if req.mode != "compact" else None} for t in data["typography"]] if "visual_identity" in domains else []
    for t in data["typography"]:
        if "visual_identity" in domains:
            _src(sources, "typography_system", {**t, "status": "approved"}, t["name"])

    # References
    refs: list[dict[str, Any]] = []
    picked: list[tuple[Asset, str]] = []
    explicit = list(req.reference_asset_ids)
    for cid in req.collection_ids:
        explicit += list(db.scalars(select(CollectionAsset.asset_id).where(CollectionAsset.collection_id == cid).order_by(CollectionAsset.position)))
    if project:
        explicit += [r.target_id for r in db.scalars(select(Relationship).where(
            Relationship.source_type == "project", Relationship.source_id == project.id, Relationship.target_type == "asset",
            Relationship.status == "approved"))]
    seen: set[uuid.UUID] = set()
    for aid in explicit:
        if aid in seen:
            continue
        a = db.scalar(select(Asset).where(Asset.id == aid, Asset.brand_id == brand.id, Asset.deleted_at.is_(None)))
        if a is None:
            raise NotFound(f"Reference asset {aid} not found in this brand")
        seen.add(aid)
        picked.append((a, "selected by user"))
    if req.auto_references and len(picked) < lim["refs"]:
        for c in chosen[:4]:
            for r in db.scalars(select(Relationship).where(Relationship.status == "approved", Relationship.relation_type == "exemplifies",
                                                           Relationship.target_type == "aesthetic_concept", Relationship.target_id == uuid.UUID(str(c["id"])))):
                if r.source_id in seen or len(picked) >= lim["refs"]:
                    continue
                a = db.scalar(select(Asset).where(Asset.id == r.source_id, Asset.deleted_at.is_(None), Asset.approval_status == "approved"))
                if a:
                    seen.add(a.id)
                    picked.append((a, f"approved example of “{c['name']}”"))
        if req.creative_direction and len(picked) < lim["refs"]:
            from app.search.engine import SearchRequest, search

            res = search(db, org_id, SearchRequest(query=req.creative_direction, brand_id=brand.id, entity_types=["asset"],
                                                   scope="official", limit=lim["refs"]))
            for it in res["items"]:
                aid = uuid.UUID(it["id"])
                if aid in seen or len(picked) >= lim["refs"]:
                    continue
                a = db.scalar(select(Asset).where(Asset.id == aid))
                seen.add(aid)
                picked.append((a, "matched the creative direction"))
        if tpl.get("include_motion") and len(picked) < lim["refs"]:
            for a in db.scalars(select(Asset).where(Asset.brand_id == brand.id, Asset.asset_type.in_(["video", "animation"]),
                                                    Asset.approval_status == "approved", Asset.deleted_at.is_(None)).limit(3)):
                if a.id not in seen:
                    seen.add(a.id)
                    picked.append((a, "approved motion reference"))
    for a, reason in picked[: max(lim["refs"], len(req.reference_asset_ids))]:
        ref = _asset_reference(db, a, reason, body)
        ref["source"] = _src(sources, "asset", {"id": a.id, "status": a.approval_status, "version": a.schema_version}, a.title)
        refs.append(ref)

    foundation = entry_items.pop("brand_foundation", [])
    return {
        "brand": brand, "project": project, "template": tpl, "domains": domains, "version": version,
        "foundation": foundation, "entries": entry_items, "principles": groups, "guidelines": guideline_items,
        "concepts": concept_items, "prohibited": prohibited, "palettes": palettes, "typography": typography,
        "references": refs, "sources": sources,
    }


def _image_prompt(sel: dict[str, Any]) -> dict[str, Any]:
    pos: list[str] = []
    for c in sel["concepts"]:
        pos.append(c["name"].lower())
    for d in ("art_direction",):
        for e in sel["entries"].get(d, []):
            st = e.get("structured") or {}
            pos += [o for o in st.get("objective_observations", [])][:4]
            if st.get("aesthetic_interpretation"):
                pos.append(st["aesthetic_interpretation"])
    for r in sel["references"][:4]:
        pos += r.get("atmosphere", [])[:2] + r.get("visual_style", [])[:2]
    hues = [c["hex"] for p in sel["palettes"] for c in p["colors"]][:6]
    neg = [p["statement"].split(": ", 1)[-1] for p in sel["prohibited"]]
    return {
        "positive_descriptors": list(dict.fromkeys(x.strip() for x in pos if x and x.strip()))[:24],
        "negative_descriptors": list(dict.fromkeys(neg))[:20],
        "palette_hint": hues,
        "prompt": ", ".join(list(dict.fromkeys(x.strip() for x in pos if x and x.strip()))[:16])
                  + (f"; colour grade within {', '.join(hues)}" if hues else ""),
    }


def build_package(db: Session, org_id: uuid.UUID, req: ContextRequest, preamble: str,
                  prompt_ref: dict[str, Any] | None = None) -> dict[str, Any]:
    sel = select_context(db, org_id, req)
    tpl, brand, project = sel["template"], sel["brand"], sel["project"]
    content: dict[str, Any] = {
        "schema": "brand-dna/context-package@1",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "task": {"type": req.task_type, "label": tpl["label"], "output_medium": req.output_medium, "mode": req.mode,
                 "creative_direction": req.creative_direction},
        "brand": {"id": str(brand.id), "name": brand.name, "tagline": brand.tagline, "description": _trim(brand.description, 1200),
                  "version": {"id": str(sel["version"].id), "number": sel["version"].version_number, "label": sel["version"].label}
                  if sel["version"] else None,
                  "knowledge_basis": "published brand version snapshot" if req.use_published_version else "live official (approved) knowledge"},
        "project": {"id": str(project.id), "name": project.name, "type": project.project_type, "objectives": project.objectives,
                    "audience": project.audience, "brief": project.brief} if project else None,
        "domains": sel["domains"],
        "core_identity": sel["foundation"],
        "mandatory_constraints": sel["principles"].get("mandatory", []),
        "prohibited_directions": sel["prohibited"],
        "preferred_principles": sel["principles"].get("preferred", []),
        "context_dependent_principles": sel["principles"].get("context_dependent", []),
        "optional_principles": sel["principles"].get("optional", []) if req.mode != "compact" else [],
        "experimental_principles": sel["principles"].get("experimental", []) if req.mode == "comprehensive" else [],
        "aesthetic_language": sel["concepts"],
        "domain_knowledge": sel["entries"],
        "guidelines": sel["guidelines"],
        "visual_identity": {"palettes": sel["palettes"], "typography": sel["typography"]},
        "references": sel["references"],
        "ai_task_instructions": {"preamble": preamble, "instructions": tpl["instructions"], "deliverable_checklist": tpl["deliverable_checklist"],
                                 "prompt_template": prompt_ref},
        "sources": sel["sources"],
    }
    if tpl.get("include_tokens") and req.mode != "compact":
        from app.api.v1.visual_identity import collect_tokens, to_css, to_dtcg

        tokens = collect_tokens(db, brand.id, approved_only=True)
        content["design_tokens"] = to_dtcg(tokens)
        if tpl.get("include_css"):
            content["design_tokens_css"] = to_css(tokens)
    if tpl.get("prompt_ready"):
        content["generation_prompt"] = _image_prompt(sel)
    content = jsonable(content)
    md = render_markdown(content)
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return {"content": content, "markdown": md, "sources": sel["sources"], "checksum": hashlib.sha256(canonical.encode()).hexdigest(),
            "token_estimate": len(md) // 4, "brand_version_id": sel["version"].id if sel["version"] else None}


def _md_list(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items if i) + "\n"


def render_markdown(c: dict[str, Any]) -> str:
    b, t = c["brand"], c["task"]
    out = [f"# Brand context — {b['name']}: {t['label']}", ""]
    meta = [f"**Mode:** {t['mode']}", f"**Knowledge basis:** {b['knowledge_basis']}"]
    if b.get("version"):
        meta.append(f"**Brand version:** v{b['version']['number']} ({b['version']['label']})")
    if t.get("output_medium"):
        meta.append(f"**Output medium:** {t['output_medium']}")
    out += [" · ".join(meta), ""]
    out += ["## Task instructions", "", c["ai_task_instructions"]["preamble"], "", _md_list(c["ai_task_instructions"]["instructions"])]
    if t.get("creative_direction"):
        out += ["**Creative direction:** " + t["creative_direction"], ""]
    if c.get("project"):
        p = c["project"]
        out += ["## Project", "", f"**{p['name']}** ({p['type']})", p.get("objectives") or "", ""]
    out += ["## Core identity", ""]
    if b.get("tagline"):
        out.append(f"*{b['tagline']}*\n")
    if b.get("description"):
        out.append(b["description"] + "\n")
    for e in c["core_identity"]:
        out.append(f"**{e['title']}** [{e['source']}] — {e.get('summary') or ''} {e.get('body') or ''}".strip() + "\n")
    out += ["## Mandatory constraints", ""]
    out.append(_md_list([f"**{p['code']}** {p['statement']} [{p['source']}]" for p in c["mandatory_constraints"]]) if c["mandatory_constraints"] else "_None recorded._\n")
    out += ["## Prohibited directions", ""]
    out.append(_md_list([f"{p['statement']} [{p['source']}]" for p in c["prohibited_directions"]]) if c["prohibited_directions"] else "_None recorded._\n")
    for key, title in (("preferred_principles", "Preferred"), ("context_dependent_principles", "Context-dependent"),
                       ("optional_principles", "Optional"), ("experimental_principles", "Experimental")):
        if c.get(key):
            out += [f"## {title} principles", "", _md_list([f"**{p['code']}** {p['statement']} [{p['source']}]" for p in c[key]])]
    if c["aesthetic_language"]:
        out += ["## Aesthetic language", ""]
        out.append(_md_list([f"**{x['name']}** ({x['relevance']}) — {x['definition']} [{x['source']}]" for x in c["aesthetic_language"]]))
    vi = c["visual_identity"]
    if vi["palettes"] or vi["typography"]:
        out += ["## Visual identity", ""]
        for p in vi["palettes"]:
            out.append(f"**{p['name']}** ({p['role']}): " + ", ".join(f"{x['name']} `{x['hex']}`" for x in p["colors"]) + "\n")
        for ty in vi["typography"]:
            out.append(f"**{ty['role'].capitalize()} type:** {ty['family']} ({', '.join(map(str, ty['weights']))}), fallback {ty['fallback']}\n")
    for d, entries in (c.get("domain_knowledge") or {}).items():
        out += [f"## {d.replace('_', ' ').capitalize()}", ""]
        for e in entries:
            line = f"**{e['title']}** [{e['source']}] — {e.get('summary') or ''}"
            if e.get("body"):
                line += f"\n\n{e['body']}"
            st = e.get("structured") or {}
            if st.get("objective_observations"):
                line += "\n\n_Observed:_ " + "; ".join(st["objective_observations"])
            if st.get("aesthetic_interpretation"):
                line += "\n\n_Interpretation:_ " + st["aesthetic_interpretation"]
            out.append(line + "\n")
    if c["guidelines"]:
        out += ["## Guidelines", ""]
        for g in c["guidelines"]:
            out.append(f"### {g['title']} [{g['source']}]\n\n{g.get('summary') or ''}\n\n{g.get('body') or ''}\n")
    if c["references"]:
        out += ["## Visual references", ""]
        for r in c["references"]:
            flag = "" if r["interpretation_status"] == "approved interpretation" else f" ⚠ {r['interpretation_status']}"
            line = f"- **{r['title']}** ({r['asset_type']}, {r['approval_status']}) [{r['source']}] — {r['selected_because']}.{flag}\n  {r.get('summary') or ''}"
            if r.get("palette"):
                line += f"\n  Palette: {' '.join(r['palette'])}"
            if r.get("motion"):
                line += f"\n  Motion: {r['motion'].get('overall_camera_movement')}; pace {r['motion'].get('pace')}"
            out.append(line)
        out.append("")
    if c.get("generation_prompt"):
        gp = c["generation_prompt"]
        out += ["## Generation prompt", "", f"**Prompt:** {gp['prompt']}", "", f"**Negative:** {', '.join(gp['negative_descriptors'])}", ""]
    if c.get("design_tokens_css"):
        out += ["## Design tokens (CSS)", "", "```css", c["design_tokens_css"].rstrip(), "```", ""]
    out += ["## Deliverable checklist", "", _md_list(c["ai_task_instructions"]["deliverable_checklist"]) or "_—_\n"]
    out += ["## Sources", "", _md_list([f"`{s['ref']}` v{s.get('version')} ({s.get('status')}) — {s['label']}" for s in c["sources"]])]
    return "\n".join(out).replace("\n\n\n", "\n\n")


def to_yaml(content: dict[str, Any]) -> str:
    return yaml.safe_dump(content, sort_keys=False, allow_unicode=True, width=120)


def to_zip(db: Session, org_id: uuid.UUID, pkg: ContextPackage, include_media: bool) -> bytes:
    from app.models import AssetDerivative
    from app.storage.backends import TenantStorage

    files: dict[str, bytes] = {
        "context.md": pkg.content_markdown.encode(),
        "context.json": json.dumps(pkg.content, indent=2, ensure_ascii=False).encode(),
        "context.yaml": to_yaml(pkg.content).encode(),
    }
    if pkg.content.get("design_tokens_css"):
        files["tokens.css"] = pkg.content["design_tokens_css"].encode()
    if pkg.content.get("design_tokens"):
        files["tokens.json"] = json.dumps(pkg.content["design_tokens"], indent=2).encode()
    if include_media:
        store = TenantStorage(org_id)
        for r in pkg.content.get("references", []):
            d = db.scalar(select(AssetDerivative).where(AssetDerivative.asset_id == uuid.UUID(r["id"]),
                                                        AssetDerivative.kind.in_(["preview", "poster"])).limit(1))
            if d:
                files[f"references/{r['id']}.webp"] = store.read_bytes(store.key_for_uri(d.storage_uri))
    manifest = {
        "package_id": str(pkg.id), "brand_id": str(pkg.brand_id), "task_type": pkg.task_type, "mode": pkg.mode,
        "brand_version_id": jsonable(pkg.brand_version_id), "content_checksum": pkg.checksum, "created_at": pkg.created_at.isoformat(),
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()
