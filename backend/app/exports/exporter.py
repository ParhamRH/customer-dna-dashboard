"""Customer library export (full or selective) → a self-describing, checksummed ZIP.

Runs in a tenant (RLS) session, so it physically cannot read another customer's rows; before
the archive is sealed, ``verify_tenant_purity`` additionally scans every JSON document and
fails the export if any ``organization_id`` differs from the exporting customer.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import __version__
from app.api.common import jsonable, row_to_dict
from app.models import (
    SCHEMA_VERSION,
    AestheticConcept,
    AiSuggestion,
    Asset,
    AssetAnalysis,
    AssetDerivative,
    AssetSegment,
    AssetTag,
    Brand,
    BrandVersion,
    Collection,
    CollectionAsset,
    ColorToken,
    ContextPackage,
    DesignToken,
    Embedding,
    ExternalReference,
    Guideline,
    KnowledgeEntry,
    KnowledgeRevision,
    Organization,
    Palette,
    Principle,
    Project,
    PromptTemplate,
    Relationship,
    Review,
    TypographySystem,
)
from app.services.embeddings import as_floats
from app.storage.backends import TenantStorage

FORMAT = "brand-dna-library-export"
DOMAIN_DIRS = {
    "brand_foundation": "foundation",
    "visual_identity": "visual-identity",
    "art_direction": "art-direction",
    "aesthetic_language": "aesthetic-language",
    "design_language": "design-language",
    "brand_language": "brand-language",
    "principles_guidelines": "guidelines",
}
ALL_DOMAINS = list(DOMAIN_DIRS) + ["creative_assets", "projects_applications", "ai_knowledge"]
STRIP = {"search_tsv"}


class ExportError(Exception):
    pass


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(data), indent=2, ensure_ascii=False, sort_keys=False))


def _rows(db: Session, model, *where) -> list[dict[str, Any]]:  # noqa: ANN001
    return [row_to_dict(r, STRIP) for r in db.scalars(select(model).where(*where))]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_tenant_purity(root: Path, org_id: uuid.UUID) -> int:
    """Every organization_id anywhere in the export must be this customer's. Returns docs checked."""
    expected = str(org_id)
    checked = 0

    def walk(node: Any, where: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "organization_id" and v is not None and str(v) != expected:
                    raise ExportError(f"foreign organization_id {v} found in {where}")
                walk(v, where)
        elif isinstance(node, list):
            for v in node:
                walk(v, where)

    for p in root.rglob("*.json"):
        walk(json.loads(p.read_text()), str(p.relative_to(root)))
        checked += 1
    for p in root.rglob("*.jsonl"):
        for line in p.read_text().splitlines():
            if line.strip():
                walk(json.loads(line), str(p.relative_to(root)))
        checked += 1
    return checked


def build_export(db: Session, org_id: uuid.UUID, export_id: uuid.UUID, mode: str, options: dict[str, Any],
                 selection: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    include_originals = options.get("include_originals", True)
    include_derivatives = options.get("include_derivatives", True)
    include_embeddings = options.get("include_embeddings", False)
    include_ai = options.get("include_ai_knowledge", True)
    include_pending = options.get("include_pending", mode == "full")
    store = TenantStorage(org_id)

    work = Path(tempfile.mkdtemp(prefix="bdna-export-"))
    root = work / "customer-export"
    root.mkdir()

    org = db.scalar(select(Organization).where(Organization.id == org_id))
    brand_q = select(Brand)
    if mode == "selective":
        if not selection.get("brand_id"):
            raise ExportError("selective export requires brand_id")
        brand_q = brand_q.where(Brand.id == uuid.UUID(str(selection["brand_id"])))
    elif options.get("brand_ids"):
        brand_q = brand_q.where(Brand.id.in_([uuid.UUID(str(b)) for b in options["brand_ids"]]))
    brands = db.scalars(brand_q.order_by(Brand.created_at)).all()
    if not brands:
        raise ExportError("no brands selected")
    brand_ids = [b.id for b in brands]
    domains = list(ALL_DOMAINS) if mode == "full" else list(selection.get("domains") or ALL_DOMAINS)
    governed_status = None if include_pending else ["approved", "deprecated"]

    _dump(root / "customer" / "profile.json", row_to_dict(org))
    _dump(root / "brand" / "brand.json", [row_to_dict(b) for b in brands])
    exported_ids: set[str] = set()
    counts: dict[str, int] = {}

    def track(rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        for r in rows:
            exported_ids.add(str(r["id"]))
        counts[kind] = counts.get(kind, 0) + len(rows)
        return rows

    for b in brands:
        slug = b.slug
        _dump(root / "brand" / "versions" / slug / "versions.json", track(_rows(db, BrandVersion, BrandVersion.brand_id == b.id), "brand_versions"))
        for dk, d in DOMAIN_DIRS.items():
            if dk not in domains:
                continue
            ent = select(KnowledgeEntry).where(KnowledgeEntry.brand_id == b.id, KnowledgeEntry.domain_key == dk)
            if governed_status:
                ent = ent.where(KnowledgeEntry.status.in_(governed_status))
            _dump(root / "brand" / d / slug / "entries.json", track([row_to_dict(r, STRIP) for r in db.scalars(ent)], "knowledge_entries"))
        if "visual_identity" in domains:
            pals = _rows(db, Palette, Palette.brand_id == b.id)
            _dump(root / "brand" / "visual-identity" / slug / "palettes.json", track(pals, "palettes"))
            _dump(root / "brand" / "visual-identity" / slug / "colors.json", track(_rows(db, ColorToken, ColorToken.brand_id == b.id), "color_tokens"))
            _dump(root / "brand" / "visual-identity" / slug / "typography.json",
                  track(_rows(db, TypographySystem, TypographySystem.brand_id == b.id), "typography_systems"))
            from app.api.v1.visual_identity import collect_tokens, to_css, to_dtcg

            toks = collect_tokens(db, b.id, approved_only=not include_pending)
            (root / "brand" / "visual-identity" / slug).mkdir(parents=True, exist_ok=True)
            (root / "brand" / "visual-identity" / slug / "tokens.css").write_text(to_css(toks))
            _dump(root / "brand" / "visual-identity" / slug / "tokens.dtcg.json", to_dtcg(toks))
        if "visual_identity" in domains or "design_language" in domains:
            tq = select(DesignToken).where(DesignToken.brand_id == b.id)
            _dump(root / "brand" / "design-language" / slug / "design-tokens.json", track([row_to_dict(r, STRIP) for r in db.scalars(tq)], "design_tokens"))
        if "aesthetic_language" in domains:
            cq = select(AestheticConcept).where(AestheticConcept.brand_id == b.id)
            if governed_status:
                cq = cq.where(AestheticConcept.status.in_(governed_status))
            _dump(root / "brand" / "aesthetic-language" / slug / "concepts.json", track([row_to_dict(r, STRIP) for r in db.scalars(cq)], "aesthetic_concepts"))
        if "principles_guidelines" in domains or mode == "selective":
            pq = select(Principle).where(Principle.brand_id == b.id)
            gq = select(Guideline).where(Guideline.brand_id == b.id)
            if mode == "selective":
                pq = pq.where(or_(Principle.domain_key.in_(domains), Principle.domain_key.is_(None)))
                gq = gq.where(Guideline.domain_key.in_(domains))
            if governed_status:
                pq, gq = pq.where(Principle.status.in_(governed_status)), gq.where(Guideline.status.in_(governed_status))
            _dump(root / "brand" / "guidelines" / slug / "principles.json", track([row_to_dict(r, STRIP) for r in db.scalars(pq)], "principles"))
            _dump(root / "brand" / "guidelines" / slug / "guidelines.json", track([row_to_dict(r, STRIP) for r in db.scalars(gq)], "guidelines"))
        revs = [r for r in _rows(db, KnowledgeRevision, KnowledgeRevision.brand_id == b.id) if str(r["entity_id"]) in exported_ids]
        _dump(root / "brand" / "guidelines" / slug / "revisions.json", revs)
        counts["knowledge_revisions"] = counts.get("knowledge_revisions", 0) + len(revs)

    # --- Assets ---------------------------------------------------------------------------
    aq = select(Asset).where(Asset.brand_id.in_(brand_ids), Asset.deleted_at.is_(None))
    if mode == "selective":
        wanted: set[uuid.UUID] = {uuid.UUID(str(a)) for a in selection.get("asset_ids") or []}
        for cid in selection.get("collection_ids") or []:
            wanted |= set(db.scalars(select(CollectionAsset.asset_id).where(CollectionAsset.collection_id == uuid.UUID(str(cid)))))
        if selection.get("project_id"):
            wanted |= {r.target_id for r in db.scalars(select(Relationship).where(
                Relationship.source_type == "project", Relationship.source_id == uuid.UUID(str(selection["project_id"])),
                Relationship.target_type == "asset"))}
        if wanted:
            aq = aq.where(Asset.id.in_(wanted))
        elif "creative_assets" not in domains:
            aq = aq.where(Asset.id.is_(None))
    assets = db.scalars(aq.order_by(Asset.created_at)).all()
    asset_ids = [a.id for a in assets]
    file_entries = 0
    for a in assets:
        rec = row_to_dict(a, STRIP)
        rec["tags"] = _rows(db, AssetTag, AssetTag.asset_id == a.id)
        rec["segments"] = _rows(db, AssetSegment, AssetSegment.asset_id == a.id)
        derivs = db.scalars(select(AssetDerivative).where(AssetDerivative.asset_id == a.id)).all()
        rec["derivatives"] = []
        for d in derivs:
            drec = row_to_dict(d, STRIP)
            if include_derivatives:
                ext = (d.storage_uri.rsplit(".", 1)[-1] if "." in d.storage_uri.rsplit("/", 1)[-1] else "bin")[:8]
                rel = f"assets/derivatives/{a.id}/{d.kind}-{d.id}.{ext}"
                store.download_to(store.key_for_uri(d.storage_uri), _mk(root / rel))
                drec["export_path"] = rel
                file_entries += 1
            rec["derivatives"].append(drec)
        if include_originals and a.storage_uri:
            rel = f"assets/originals/{a.id}/{a.original_filename or 'original'}"
            dest = _mk(root / rel)
            store.download_to(store.key_for_uri(a.storage_uri), dest)
            if sha256_file(dest) != a.checksum:
                raise ExportError(f"stored original for asset {a.id} failed checksum verification")
            rec["export_path"] = rel
            file_entries += 1
        rec["external_references"] = _rows(db, ExternalReference, ExternalReference.asset_id == a.id)
        _dump(root / "assets" / "metadata" / f"{a.id}.json", rec)
        exported_ids.add(str(a.id))
        exported_ids.update(str(s["id"]) for s in rec["segments"])
    counts["assets"] = len(assets)
    cq = select(Collection).where(Collection.brand_id.in_(brand_ids))
    if mode == "selective" and selection.get("collection_ids"):
        cq = cq.where(Collection.id.in_([uuid.UUID(str(c)) for c in selection["collection_ids"]]))
    elif mode == "selective":
        cq = cq.where(Collection.id.is_(None))
    cols = []
    for c in db.scalars(cq):
        d = row_to_dict(c, STRIP)
        d["assets"] = [row_to_dict(x) for x in db.scalars(select(CollectionAsset).where(
            CollectionAsset.collection_id == c.id, CollectionAsset.asset_id.in_(asset_ids or [uuid.uuid4()])))]
        cols.append(d)
    _dump(root / "assets" / "collections" / "collections.json", track(cols, "collections"))
    refs_free = [r for r in _rows(db, ExternalReference, ExternalReference.brand_id.in_(brand_ids), ExternalReference.asset_id.is_(None))]
    _dump(root / "assets" / "metadata" / "_external_references.json", refs_free)

    # --- Projects -------------------------------------------------------------------------
    pq = select(Project).where(Project.brand_id.in_(brand_ids))
    if mode == "selective":
        pq = pq.where(Project.id == uuid.UUID(str(selection["project_id"]))) if selection.get("project_id") else pq.where(Project.id.is_(None))
    _dump(root / "projects" / "projects.json", track([row_to_dict(r, STRIP) for r in db.scalars(pq)], "projects"))

    # --- Relationships (both ends exported) ------------------------------------------------
    rels = [r for r in _rows(db, Relationship, Relationship.brand_id.in_(brand_ids))
            if str(r["source_id"]) in exported_ids and str(r["target_id"]) in exported_ids]
    _dump(root / "relationships" / "relationships.json", rels)
    counts["relationships"] = len(rels)

    # --- AI knowledge -----------------------------------------------------------------------
    if include_ai and ("ai_knowledge" in domains or mode == "full"):
        an = [r for r in _rows(db, AssetAnalysis, AssetAnalysis.asset_id.in_(asset_ids or [uuid.uuid4()]))]
        _dump(root / "ai-knowledge" / "asset-analyses.json", an)
        sg = _rows(db, AiSuggestion, AiSuggestion.brand_id.in_(brand_ids))
        _dump(root / "ai-knowledge" / "suggestions.json", sg)
        rv = _rows(db, Review, or_(Review.brand_id.in_(brand_ids), Review.brand_id.is_(None)))
        _dump(root / "ai-knowledge" / "reviews.json", rv)
        _dump(root / "ai-knowledge" / "prompt-templates.json",
              [row_to_dict(p) for p in db.scalars(select(PromptTemplate).where(PromptTemplate.organization_id == org_id))])
        cp = _rows(db, ContextPackage, ContextPackage.brand_id.in_(brand_ids))
        _dump(root / "ai-knowledge" / "context-packages.json", cp)
        counts.update({"asset_analyses": len(an), "ai_suggestions": len(sg), "reviews": len(rv), "context_packages": len(cp)})
    if mode == "selective" and selection.get("task_type"):
        from app.context.generator import ContextRequest, build_package

        pkg = build_package(db, org_id, ContextRequest(brand_id=brand_ids[0], task_type=selection["task_type"],
                                                       project_id=uuid.UUID(str(selection["project_id"])) if selection.get("project_id") else None,
                                                       reference_asset_ids=asset_ids[:16]), "Task context generated at export time.")
        _dump(root / "ai-knowledge" / "task-context.json", pkg["content"])
        (root / "ai-knowledge" / "task-context.md").write_text(pkg["markdown"])

    # --- Embeddings (optional; model-specific, not assumed portable) -----------------------
    emb_info: list[dict[str, Any]] = []
    if include_embeddings:
        by_model: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        for e in db.scalars(select(Embedding).where(Embedding.brand_id.in_(brand_ids))):
            if str(e.entity_id) not in exported_ids:
                continue
            by_model.setdefault((e.modality, e.model, e.dimensions), []).append({
                "organization_id": str(e.organization_id), "brand_id": str(e.brand_id), "entity_type": e.entity_type,
                "entity_id": str(e.entity_id), "segment": e.segment, "content_hash": e.content_hash, "vector": as_floats(e.embedding)})
        for (modality, model, dims), items in by_model.items():
            fname = f"{modality}-{model.replace('/', '_')}-{dims}.jsonl"
            p = _mk(root / "embeddings" / fname)
            p.write_text("\n".join(json.dumps(i) for i in items) + "\n")
            emb_info.append({"file": f"embeddings/{fname}", "modality": modality, "model": model, "dimensions": dims, "count": len(items),
                             "provider": db.scalar(select(Embedding.provider).where(Embedding.model == model).limit(1))})
    _dump(root / "embeddings" / "README.json", {
        "note": "Vectors are only meaningful for the exact model + dimensionality listed. On import into an installation using a "
                "different embedding model, choose 'regenerate embeddings' (the default) instead of importing vectors.",
        "models": emb_info, "included": include_embeddings})

    # --- Documentation ----------------------------------------------------------------------
    _write_docs(root, org, brands, mode, domains)

    checked = verify_tenant_purity(root, org_id)
    checksums = {str(p.relative_to(root)): sha256_file(p) for p in sorted(root.rglob("*")) if p.is_file()}
    manifest = {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "platform_version": __version__,
        "export_id": str(export_id),
        "export_date": dt.datetime.now(dt.UTC).isoformat(),
        "export_mode": mode,
        "customer_id": str(org_id),
        "customer_slug": org.slug,
        "brand_ids": [str(b) for b in brand_ids],
        "brand_versions": {str(b.id): (db.scalar(select(BrandVersion.version_number).where(BrandVersion.id == b.current_version_id))
                                       if b.current_version_id else None) for b in brands},
        "included_domains": domains,
        "selection": jsonable(selection) if mode == "selective" else None,
        "export_options": {"include_originals": include_originals, "include_derivatives": include_derivatives,
                           "include_embeddings": include_embeddings, "include_ai_knowledge": include_ai, "include_pending": include_pending},
        "counts": counts,
        "asset_count": len(assets),
        "file_count": len(checksums) + 1,
        "binary_file_count": file_entries,
        "embeddings": emb_info,
        "tenant_purity_check": {"documents_checked": checked, "passed": True},
        "checksum_algorithm": "sha256",
        "checksums": checksums,
    }
    _dump(root / "manifest.json", manifest)
    archive = work / "export.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                z.write(p, f"customer-export/{p.relative_to(root)}")
    shutil.rmtree(root)
    return archive, manifest


def _mk(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _write_docs(root: Path, org: Organization, brands: list[Brand], mode: str, domains: list[str]) -> None:
    readme = f"""# Brand DNA library export — {org.name}

This archive is an independent, portable copy of the brand knowledge of **{org.name}**
({', '.join(b.name for b in brands)}). It was produced by the Brand DNA & Creative Intelligence
Platform ({mode} export) and contains only this customer's data.

## Layout

| Path | Contents |
|---|---|
| `manifest.json` | export id, date, schema version, counts, options and a SHA-256 for every file |
| `customer/profile.json` | customer profile |
| `brand/brand.json` | brands; `brand/versions/<brand>/` published immutable snapshots |
| `brand/<domain>/<brand>/` | knowledge per domain (foundation, visual identity, art direction, aesthetic language, design language, brand language, guidelines) |
| `brand/visual-identity/<brand>/tokens.css`, `tokens.dtcg.json` | design tokens for developers and design tools |
| `assets/metadata/<asset-id>.json` | asset record, tags, segments (scenes/pages), derivative list, provenance |
| `assets/originals/`, `assets/derivatives/` | original files (byte-identical, checksum-verified) and previews |
| `assets/collections/` | collections and moodboards |
| `projects/`, `relationships/` | projects and the knowledge graph edges |
| `ai-knowledge/` | AI analyses (always labelled with provider/model/prompt version), suggestions, review history, context packages |
| `embeddings/` | optional vectors, *model-specific* — regenerate them when changing embedding model |

## Governance semantics

* `status = approved` on principles, guidelines, concepts and entries means a person approved it.
  Revisions in `brand/guidelines/<brand>/revisions.json` hold every content version.
* AI analyses are *interpretations*; they are never official rules. An asset's accepted
  interpretation is referenced by `approved_analysis_id`.

## Verifying

```bash
cd customer-export
python3 - <<'PY'
import hashlib, json, pathlib
m = json.load(open("manifest.json"))
bad = [p for p, h in m["checksums"].items() if hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() != h]
print("OK" if not bad else f"MISMATCH: {{bad}}")
PY
```

Included domains: {', '.join(domains)}
"""
    (root / "README.md").write_text(readme)
    _dump(root / "documentation" / "data-dictionary.json", {
        "schema_version": SCHEMA_VERSION,
        "entities": {
            "principle": "Creative principle. classification ∈ mandatory|preferred|optional|prohibited|context_dependent|experimental",
            "guideline": "Rich-text guideline for a domain; applies_to.project_types scopes it",
            "aesthetic_concept": "Controlled vocabulary entry; related/opposing concepts are relationships",
            "knowledge_entry": "Structured + rich-text record of a domain (entry_type defines the structured fields)",
            "asset": "Original creative material; media_metadata = objective machine measurements",
            "asset_analysis": "AI interpretation: objective vs interpretive parts, provider, model, prompt version, confidence",
            "relationship": "Typed edge between two exported entities (source_type/source_id → target_type/target_id)",
        },
    })
