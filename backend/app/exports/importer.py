"""Validated, staged import of a library export into the CURRENT organization.

validate:  zip-safety → manifest/schema compatibility → per-file SHA-256 → parse → preview
           (counts, brand conflicts, duplicate assets, embedding-model compatibility).
commit:    one database transaction with full ID remapping; originals written create-only and
           re-verified; any failure rolls the transaction back AND deletes every object written.
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

from sqlalchemy import select, update
from sqlalchemy.orm import Session

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
    Palette,
    Principle,
    Project,
    PromptTemplate,
    Relationship,
    Review,
    TypographySystem,
)
from app.storage.backends import ObjectExists, TenantStorage

MAX_UNCOMPRESSED = 50 * 1024**3
MAX_RATIO = 200


class ImportErrorReport(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors[:5]))
        self.errors = errors


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_extract(zip_path: Path, dest: Path) -> Path:
    errors = []
    with zipfile.ZipFile(zip_path) as z:
        total = 0
        for info in z.infolist():
            name = info.filename
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                errors.append(f"unsafe path in archive: {name}")
            total += info.file_size
            if info.compress_size and info.file_size / max(1, info.compress_size) > MAX_RATIO and info.file_size > 50 * 1024**2:
                errors.append(f"suspicious compression ratio for {name}")
        if total > MAX_UNCOMPRESSED:
            errors.append("archive too large when uncompressed")
        if errors:
            raise ImportErrorReport(errors)
        z.extractall(dest)
    root = dest / "customer-export"
    if not (root / "manifest.json").exists():
        if (dest / "manifest.json").exists():
            return dest
        raise ImportErrorReport(["manifest.json not found — not a Brand DNA library export"])
    return root


def _load(root: Path, rel: str, default: Any = None) -> Any:
    p = root / rel
    return json.loads(p.read_text()) if p.exists() else default


def _glob_json(root: Path, pattern: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(root.glob(pattern)):
        data = json.loads(p.read_text())
        out += data if isinstance(data, list) else [data]
    return out


def read_export(root: Path) -> dict[str, Any]:
    return {
        "manifest": _load(root, "manifest.json"),
        "profile": _load(root, "customer/profile.json", {}),
        "brands": _load(root, "brand/brand.json", []),
        "versions": _glob_json(root, "brand/versions/*/versions.json"),
        "entries": [e for d in ("foundation", "visual-identity", "art-direction", "aesthetic-language", "design-language", "brand-language")
                    for e in _glob_json(root, f"brand/{d}/*/entries.json")],
        "palettes": _glob_json(root, "brand/visual-identity/*/palettes.json"),
        "colors": _glob_json(root, "brand/visual-identity/*/colors.json"),
        "typography": _glob_json(root, "brand/visual-identity/*/typography.json"),
        "design_tokens": _glob_json(root, "brand/design-language/*/design-tokens.json"),
        "concepts": _glob_json(root, "brand/aesthetic-language/*/concepts.json"),
        "principles": _glob_json(root, "brand/guidelines/*/principles.json"),
        "guidelines": _glob_json(root, "brand/guidelines/*/guidelines.json"),
        "revisions": _glob_json(root, "brand/guidelines/*/revisions.json"),
        "assets": [a for a in _glob_json(root, "assets/metadata/*.json") if "asset_type" in a],
        "free_references": _load(root, "assets/metadata/_external_references.json", []),
        "collections": _load(root, "assets/collections/collections.json", []),
        "projects": _load(root, "projects/projects.json", []),
        "relationships": _load(root, "relationships/relationships.json", []),
        "analyses": _load(root, "ai-knowledge/asset-analyses.json", []),
        "suggestions": _load(root, "ai-knowledge/suggestions.json", []),
        "reviews": _load(root, "ai-knowledge/reviews.json", []),
        "prompts": _load(root, "ai-knowledge/prompt-templates.json", []),
        "context_packages": _load(root, "ai-knowledge/context-packages.json", []),
    }


def validate(db: Session, root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    manifest = _load(root, "manifest.json")
    if not isinstance(manifest, dict) or manifest.get("format") != "brand-dna-library-export":
        raise ImportErrorReport(["manifest.json is missing or not a brand-dna-library-export"])
    sv = manifest.get("schema_version")
    if not isinstance(sv, int) or sv > SCHEMA_VERSION:
        errors.append(f"export schema_version {sv} is newer than this installation supports ({SCHEMA_VERSION})")
    listed = manifest.get("checksums") or {}
    bad = []
    for rel, digest in listed.items():
        p = root / rel
        if not p.exists():
            bad.append(f"missing file: {rel}")
        elif _sha(p) != digest:
            bad.append(f"checksum mismatch: {rel}")
    errors += bad
    present = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} - {"manifest.json"}
    extra = sorted(present - set(listed))
    if extra:
        errors.append(f"{len(extra)} file(s) not covered by the manifest (e.g. {extra[0]})")
    data = read_export(root) if not errors else None
    preview: dict[str, Any] = {
        "source": {k: manifest.get(k) for k in ("customer_id", "customer_slug", "export_id", "export_date", "export_mode",
                                               "schema_version", "platform_version", "included_domains")},
        "checksums_verified": len(listed) - len(bad),
        "errors": errors,
        "warnings": warnings,
    }
    if data is None:
        return preview
    existing_brands = {b.slug: b for b in db.scalars(select(Brand))}
    preview["brands"] = [
        {"source_id": b["id"], "name": b["name"], "slug": b["slug"],
         "conflict_brand_id": str(existing_brands[b["slug"]].id) if b["slug"] in existing_brands else None}
        for b in data["brands"]
    ]
    checks = {a["checksum"]: a for a in data["assets"] if a.get("checksum")}
    dups = []
    if checks:
        for a in db.scalars(select(Asset).where(Asset.checksum.in_(list(checks)), Asset.deleted_at.is_(None))):
            dups.append({"existing_asset_id": str(a.id), "title": a.title, "source_asset_id": checks[a.checksum]["id"]})
    preview["duplicates"] = {"assets": len(dups), "items": dups[:50]}
    preview["counts"] = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    missing_files = [a["id"] for a in data["assets"] if a.get("storage_uri") and not a.get("export_path")]
    if missing_files:
        warnings.append(f"{len(missing_files)} asset(s) were exported without original files (metadata only)")
    from app.ai import registry

    current = registry.text_embedder(db)
    emb = manifest.get("embeddings") or []
    preview["embeddings"] = {
        "included": bool(emb),
        "models": emb,
        "current_text_model": {"model": current.model, "dimensions": current.dimensions},
        "compatible": any(e["modality"] == "text" and e["model"] == current.model and e["dimensions"] == current.dimensions for e in emb),
        "recommendation": "regenerate",
    }
    if foreign := manifest.get("customer_id"):
        preview["source"]["note"] = f"Records will be re-keyed into this workspace (source customer {foreign})."
    return preview


# --- Commit ------------------------------------------------------------------------------------
class Mapper:
    def __init__(self) -> None:
        self.m: dict[str, uuid.UUID] = {}
        self.created: set[uuid.UUID] = set()

    def new(self, old: Any) -> uuid.UUID:
        key = str(old)
        if key not in self.m:
            self.m[key] = uuid.uuid4()
            self.created.add(self.m[key])
        return self.m[key]

    def set(self, old: Any, new: uuid.UUID) -> None:
        self.m[str(old)] = new

    def get(self, old: Any) -> uuid.UUID | None:
        return self.m.get(str(old)) if old is not None else None


def _dt(v: Any) -> dt.datetime | None:
    return dt.datetime.fromisoformat(v) if isinstance(v, str) else None


def _copy(rec: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {f: rec.get(f) for f in fields if f in rec}


GOV = ["status", "version", "approved_at"]


def commit(db: Session, org_id: uuid.UUID, root: Path, options: dict[str, Any], user_id: uuid.UUID | None) -> dict[str, Any]:
    data = read_export(root)
    store = TenantStorage(org_id)
    written: list[str] = []
    ids = Mapper()
    report: dict[str, Any] = {"created": {}, "skipped": {}, "mapped_existing": {}}

    def inc(bucket: str, kind: str, n: int = 1) -> None:
        report[bucket][kind] = report[bucket].get(kind, 0) + n

    strategies: dict[str, str] = options.get("brand_mapping") or {}
    skip_dups = options.get("skip_duplicate_assets", True)
    import_ai = options.get("import_ai_knowledge", True)
    preserve = options.get("preserve_approvals", True)
    regenerate = options.get("regenerate_embeddings", True)

    def gov(rec: dict[str, Any]) -> dict[str, Any]:
        st = rec.get("status", "draft")
        if not preserve and st == "approved":
            st = "draft"
        return {"status": st, "version": rec.get("version", 1), "approved_at": _dt(rec.get("approved_at")) if st == "approved" else None,
                "origin": "import", "created_by": user_id, "updated_by": user_id}

    try:
        # Brands -------------------------------------------------------------------------
        existing = {b.slug: b for b in db.scalars(select(Brand))}
        brand_cur_version: dict[uuid.UUID, Any] = {}
        for b in data["brands"]:
            strat = strategies.get(b["id"], "create")
            if strat.startswith("merge:"):
                target = db.scalar(select(Brand).where(Brand.id == uuid.UUID(strat.split(":", 1)[1])))
                if target is None:
                    raise ImportErrorReport([f"merge target brand {strat} not found"])
                ids.set(b["id"], target.id)
                inc("mapped_existing", "brands")
                continue
            slug, n = b["slug"], 2
            while slug in existing:
                slug, n = f"{b['slug']}-{n}", n + 1
            nb = Brand(id=ids.new(b["id"]), organization_id=org_id, slug=slug, created_by=user_id,
                       **_copy(b, ["name", "tagline", "description", "status", "primary_language", "settings"]))
            db.add(nb)
            existing[slug] = nb
            brand_cur_version[nb.id] = b.get("current_version_id")
            inc("created", "brands")
        db.flush()

        def bid(rec: dict[str, Any]) -> uuid.UUID:
            return ids.get(rec["brand_id"])

        for v in data["versions"]:
            last = db.scalar(select(BrandVersion.version_number).where(BrandVersion.brand_id == bid(v)).order_by(BrandVersion.version_number.desc()).limit(1)) or 0
            db.add(BrandVersion(id=ids.new(v["id"]), organization_id=org_id, brand_id=bid(v), version_number=max(last + 1, v["version_number"]) if last else v["version_number"],
                                label=v["label"], status=v.get("status", "superseded"), snapshot=v["snapshot"], snapshot_checksum=v["snapshot_checksum"],
                                counts=v.get("counts", {}), notes=(v.get("notes") or "") + f"\n[imported; source version {v['id']}]", published_by=None,
                                published_at=_dt(v.get("published_at")) or dt.datetime.now(dt.UTC)))
            inc("created", "brand_versions")
        db.flush()
        for nb_id, old in brand_cur_version.items():
            if old and ids.get(old):
                db.execute(update(Brand).where(Brand.id == nb_id).values(current_version_id=ids.get(old)))

        # Governed knowledge --------------------------------------------------------------
        for c in data["concepts"]:
            hit = db.scalar(select(AestheticConcept).where(AestheticConcept.brand_id == bid(c), AestheticConcept.slug == c["slug"]))
            if hit:
                ids.set(c["id"], hit.id)
                inc("mapped_existing", "aesthetic_concepts")
                continue
            db.add(AestheticConcept(id=ids.new(c["id"]), organization_id=org_id, brand_id=bid(c), **gov(c),
                                    **_copy(c, ["slug", "name", "definition", "attributes", "synonyms", "brand_relevance", "relevance_score"])))
            inc("created", "aesthetic_concepts")
        for p in data["principles"]:
            code = p["code"]
            same = db.scalar(select(Principle).where(Principle.brand_id == bid(p), Principle.code == code))
            if same is not None and (same.title == p["title"] or same.statement == p["statement"]):
                ids.set(p["id"], same.id)  # merge: the same principle already exists
                inc("mapped_existing", "principles")
                continue
            if same is not None:
                from app.services.knowledge import next_principle_code

                db.flush()
                code = next_principle_code(db, bid(p))
            db.add(Principle(id=ids.new(p["id"]), organization_id=org_id, brand_id=bid(p), code=code, **gov(p),
                             **_copy(p, ["title", "statement", "rationale", "classification", "domain_key", "scope", "examples", "priority"])))
            db.flush()
            inc("created", "principles")
        for g in data["guidelines"]:
            same = db.scalar(select(Guideline).where(Guideline.brand_id == bid(g), Guideline.slug == g["slug"], Guideline.title == g["title"]))
            if same is not None:
                ids.set(g["id"], same.id)
                inc("mapped_existing", "guidelines")
                continue
            slug, n = g["slug"], 2
            while db.scalar(select(Guideline.id).where(Guideline.brand_id == bid(g), Guideline.slug == slug)):
                slug, n = f"{g['slug']}-{n}", n + 1
            db.add(Guideline(id=ids.new(g["id"]), organization_id=org_id, brand_id=bid(g), slug=slug, **gov(g),
                             **_copy(g, ["domain_key", "title", "summary", "body", "applies_to"])))
            db.flush()
            inc("created", "guidelines")
        for e in data["entries"]:
            same = db.scalar(select(KnowledgeEntry.id).where(KnowledgeEntry.brand_id == bid(e), KnowledgeEntry.domain_key == e["domain_key"],
                                                             KnowledgeEntry.entry_type == e["entry_type"], KnowledgeEntry.title == e["title"]))
            if same is not None:
                ids.set(e["id"], same)
                inc("mapped_existing", "knowledge_entries")
                continue
            db.add(KnowledgeEntry(id=ids.new(e["id"]), organization_id=org_id, brand_id=bid(e), **gov(e),
                                  **_copy(e, ["domain_key", "entry_type", "title", "summary", "body", "structured", "tags", "sort_order"])))
            inc("created", "knowledge_entries")
        db.flush()
        for r in data["revisions"]:
            new_entity = ids.get(r["entity_id"])
            if new_entity is None or db.scalar(select(KnowledgeRevision.id).where(
                    KnowledgeRevision.entity_id == new_entity, KnowledgeRevision.version == r["version"])):
                continue
            db.add(KnowledgeRevision(organization_id=org_id, brand_id=bid(r), entity_type=r["entity_type"], entity_id=new_entity,
                                     version=r["version"], status=r["status"], data=r["data"],
                                     change_note=(r.get("change_note") or "") + " [imported]", created_by=user_id))
            inc("created", "knowledge_revisions")

        # Visual identity ----------------------------------------------------------------
        for p in data["palettes"]:
            same = db.scalar(select(Palette.id).where(Palette.brand_id == bid(p), Palette.name == p["name"], Palette.role == p["role"]))
            if same is not None:
                ids.set(p["id"], same)
                inc("mapped_existing", "palettes")
                continue
            db.add(Palette(id=ids.new(p["id"]), organization_id=org_id, brand_id=bid(p),
                           **_copy(p, ["name", "role", "description", "status", "sort_order"])))
            inc("created", "palettes")
        db.flush()
        for c in data["colors"]:
            key = c["token_key"]
            same = db.scalar(select(ColorToken).where(ColorToken.brand_id == bid(c), ColorToken.token_key == key))
            if same is not None and same.hex == c["hex"]:
                ids.set(c["id"], same.id)
                inc("mapped_existing", "color_tokens")
                continue
            if same is not None:
                key = f"{key}-imported"
            db.add(ColorToken(id=ids.new(c["id"]), organization_id=org_id, brand_id=bid(c), palette_id=ids.get(c["palette_id"]), token_key=key,
                              **_copy(c, ["name", "hex", "rgb", "hsl", "oklch", "cmyk", "cmyk_is_manual", "pantone", "semantic_role", "usage", "sort_order"])))
            inc("created", "color_tokens")
        for t in data["typography"]:
            same = db.scalar(select(TypographySystem.id).where(TypographySystem.brand_id == bid(t), TypographySystem.family == t["family"],
                                                               TypographySystem.role == t["role"]))
            if same is not None:
                ids.set(t["id"], same)
                inc("mapped_existing", "typography_systems")
                continue
            db.add(TypographySystem(id=ids.new(t["id"]), organization_id=org_id, brand_id=bid(t),
                                    **_copy(t, ["name", "role", "family", "fallback_stack", "source", "source_url", "license", "weights",
                                                "supports_italic", "hierarchy", "usage", "status", "sort_order"])))
            inc("created", "typography_systems")
        for t in data["design_tokens"]:
            if db.scalar(select(DesignToken.id).where(DesignToken.brand_id == bid(t), DesignToken.path == t["path"])):
                inc("skipped", "design_tokens")
                continue
            db.add(DesignToken(id=ids.new(t["id"]), organization_id=org_id, brand_id=bid(t),
                               **_copy(t, ["path", "token_type", "value", "description", "category", "domain_key", "status", "sort_order"])))
            inc("created", "design_tokens")
        db.flush()

        # Assets ---------------------------------------------------------------------------
        approved_analysis: dict[uuid.UUID, Any] = {}
        for a in data["assets"]:
            if skip_dups and a.get("checksum"):
                dup = db.scalar(select(Asset).where(Asset.brand_id == bid(a), Asset.checksum == a["checksum"], Asset.deleted_at.is_(None)))
                if dup:
                    ids.set(a["id"], dup.id)
                    for s in a.get("segments", []):
                        hit = db.scalar(select(AssetSegment.id).where(AssetSegment.asset_id == dup.id, AssetSegment.segment_type == s["segment_type"],
                                                                     AssetSegment.segment_index == s["segment_index"]))
                        if hit:
                            ids.set(s["id"], hit)
                    inc("mapped_existing", "assets")
                    continue
            new_id = ids.new(a["id"])
            uri = None
            if a.get("export_path"):
                src = root / a["export_path"]
                if _sha(src) != a["checksum"]:
                    raise ImportErrorReport([f"original for asset {a['id']} does not match its recorded checksum"])
                key = store.original_key(bid(a), new_id, a.get("original_filename") or "original")
                try:
                    uri = store.put_file(key, src, a.get("mime_type") or "application/octet-stream", create_only=True).uri
                except ObjectExists as e:
                    raise ImportErrorReport([f"storage object already exists for {key}"]) from e
                written.append(key)
            db.add(Asset(id=new_id, organization_id=org_id, brand_id=bid(a), storage_uri=uri, created_by=user_id,
                         approved_by=None, approved_at=_dt(a.get("approved_at")),
                         processing_status=a.get("processing_status", "processed") if uri or a.get("asset_type") == "external_reference" else "skipped",
                         **_copy(a, ["title", "description", "asset_type", "category", "subcategory", "folder_path", "original_filename",
                                     "mime_type", "file_size", "checksum", "source_type", "source_url", "reference_role", "approval_status",
                                     "brand_relevance", "license", "media_metadata", "curated_metadata", "schema_version"])))
            approved_analysis[new_id] = a.get("approved_analysis_id")
            db.flush()
            deriv_map: dict[str, uuid.UUID] = {}
            for d in a.get("derivatives", []):
                if not d.get("export_path"):
                    continue
                did = ids.new(d["id"])
                key = store.derivative_key(bid(a), new_id, d["kind"], Path(d["export_path"]).name)
                obj = store.put_bytes(key, (root / d["export_path"]).read_bytes(), d["mime_type"])
                written.append(key)
                deriv_map[d["id"]] = did
                db.add(AssetDerivative(id=did, organization_id=org_id, asset_id=new_id, storage_uri=obj.uri, file_size=obj.size, checksum=obj.sha256,
                                       **_copy(d, ["kind", "mime_type", "width", "height", "page_number", "timestamp_ms", "segment_index", "meta"])))
            db.flush()
            for s in a.get("segments", []):
                db.add(AssetSegment(id=ids.new(s["id"]), organization_id=org_id, asset_id=new_id,
                                    keyframe_derivative_id=deriv_map.get(s.get("keyframe_derivative_id")),
                                    **_copy(s, ["segment_type", "segment_index", "start_ms", "end_ms", "page_number", "title", "text_content", "meta"])))
            for t in a.get("tags", []):
                db.add(AssetTag(organization_id=org_id, asset_id=new_id, tag=t["tag"], source=t["source"],
                                status=t["status"] if import_ai or t["source"] == "human" else "approved", confidence=t.get("confidence")))
            for r in a.get("external_references", []):
                db.add(ExternalReference(id=ids.new(r["id"]), organization_id=org_id, brand_id=bid(a), asset_id=new_id,
                                         **_copy(r, ["title", "url", "source_name", "creator", "license", "notes", "provenance"]),
                                         accessed_at=_dt(r.get("accessed_at"))))
            inc("created", "assets")
        db.flush()
        for r in data["free_references"]:
            db.add(ExternalReference(id=ids.new(r["id"]), organization_id=org_id, brand_id=bid(r),
                                     **_copy(r, ["title", "url", "source_name", "creator", "license", "notes", "provenance"])))

        # Collections & projects -------------------------------------------------------------
        for c in data["collections"]:
            same = db.scalar(select(Collection).where(Collection.brand_id == bid(c), Collection.slug == c["slug"]))
            if same is not None:
                ids.set(c["id"], same.id)
                have = set(db.scalars(select(CollectionAsset.asset_id).where(CollectionAsset.collection_id == same.id)))
                for ca in c.get("assets", []):
                    aid = ids.get(ca["asset_id"])
                    if aid and aid not in have:
                        db.add(CollectionAsset(organization_id=org_id, collection_id=same.id, asset_id=aid, position=ca.get("position", 0)))
                inc("mapped_existing", "collections")
                continue
            slug, n = c["slug"], 2
            while db.scalar(select(Collection.id).where(Collection.brand_id == bid(c), Collection.slug == slug)):
                slug, n = f"{c['slug']}-{n}", n + 1
            col = Collection(id=ids.new(c["id"]), organization_id=org_id, brand_id=bid(c), slug=slug, created_by=user_id,
                             cover_asset_id=ids.get(c.get("cover_asset_id")), **_copy(c, ["name", "description", "kind"]))
            db.add(col)
            db.flush()
            for ca in c.get("assets", []):
                if ids.get(ca["asset_id"]):
                    db.add(CollectionAsset(organization_id=org_id, collection_id=col.id, asset_id=ids.get(ca["asset_id"]),
                                           position=ca.get("position", 0), note=ca.get("note"), added_by=user_id))
            inc("created", "collections")
        for p in data["projects"]:
            same = db.scalar(select(Project.id).where(Project.brand_id == bid(p), Project.slug == p["slug"], Project.name == p["name"]))
            if same is not None:
                ids.set(p["id"], same)
                inc("mapped_existing", "projects")
                continue
            slug, n = p["slug"], 2
            while db.scalar(select(Project.id).where(Project.brand_id == bid(p), Project.slug == slug)):
                slug, n = f"{p['slug']}-{n}", n + 1
            db.add(Project(id=ids.new(p["id"]), organization_id=org_id, brand_id=bid(p), slug=slug, created_by=user_id,
                           start_date=dt.date.fromisoformat(p["start_date"]) if p.get("start_date") else None,
                           due_date=dt.date.fromisoformat(p["due_date"]) if p.get("due_date") else None,
                           **_copy(p, ["name", "project_type", "status", "description", "objectives", "audience", "deliverables", "selected_domains", "brief"])))
            inc("created", "projects")
        db.flush()

        # AI knowledge ------------------------------------------------------------------------
        if import_ai:
            for x in data["analyses"]:
                if not ids.get(x["asset_id"]) or str(ids.get(x["asset_id"])) not in {str(k) for k in approved_analysis}:
                    continue
                db.add(AssetAnalysis(id=ids.new(x["id"]), organization_id=org_id, brand_id=bid(x), asset_id=ids.get(x["asset_id"]),
                                     reviewed_at=_dt(x.get("reviewed_at")),
                                     **_copy(x, ["analysis_type", "provider", "model", "prompt_key", "prompt_version", "schema_version", "objective",
                                                 "interpretive", "raw_output", "validation_errors", "confidence", "processing_ms",
                                                 "is_development_adapter", "status", "review_notes"])))
                inc("created", "asset_analyses")
            db.flush()
            for new_asset, old_an in approved_analysis.items():
                if old_an and ids.get(old_an):
                    db.execute(update(Asset).where(Asset.id == new_asset).values(approved_analysis_id=ids.get(old_an)))
            for s in data["suggestions"]:
                if s.get("status") != "pending":
                    continue
                db.add(AiSuggestion(id=ids.new(s["id"]), organization_id=org_id, brand_id=bid(s),
                                    source_asset_id=ids.get(s.get("source_asset_id")), source_analysis_id=ids.get(s.get("source_analysis_id")),
                                    payload=_remap_payload(s.get("payload") or {}, ids),
                                    **_copy(s, ["suggestion_type", "title", "rationale", "confidence", "status"])))
                inc("created", "ai_suggestions")
            for r in data["reviews"]:
                if ids.get(r["subject_id"]) is None:
                    continue
                db.add(Review(organization_id=org_id, brand_id=ids.get(r.get("brand_id")), subject_type=r["subject_type"],
                              subject_id=ids.get(r["subject_id"]), decision=r["decision"],
                              notes=((r.get("notes") or "") + " [imported review]").strip(), changes=r.get("changes") or {}))
                inc("created", "reviews")
            for p in data["prompts"]:
                if not db.scalar(select(PromptTemplate.id).where(PromptTemplate.organization_id == org_id, PromptTemplate.key == p["key"],
                                                                 PromptTemplate.version == p["version"])):
                    db.add(PromptTemplate(organization_id=org_id, **_copy(p, ["key", "name", "purpose", "version", "template", "output_schema", "is_active"])))
            existing_ck = set(db.scalars(select(ContextPackage.checksum)))
            for cp in data["context_packages"]:
                if cp["checksum"] in existing_ck:
                    continue
                db.add(ContextPackage(organization_id=org_id, brand_id=bid(cp), project_id=ids.get(cp.get("project_id")),
                                      brand_version_id=ids.get(cp.get("brand_version_id")), created_by=user_id,
                                      **_copy(cp, ["title", "task_type", "output_medium", "mode", "request", "content", "content_markdown",
                                                   "sources", "token_estimate", "checksum"])))
                inc("created", "context_packages")
        db.flush()

        # Relationships ---------------------------------------------------------------------------
        for r in data["relationships"]:
            s_id, t_id = ids.get(r["source_id"]), ids.get(r["target_id"])
            if not s_id or not t_id:
                inc("skipped", "relationships")
                continue
            if db.scalar(select(Relationship.id).where(Relationship.source_type == r["source_type"], Relationship.source_id == s_id,
                                                       Relationship.relation_type == r["relation_type"], Relationship.target_type == r["target_type"],
                                                       Relationship.target_id == t_id)):
                inc("skipped", "relationships")
                continue
            db.add(Relationship(id=ids.new(r["id"]), organization_id=org_id, brand_id=bid(r), source_id=s_id, target_id=t_id,
                                origin="import" if r.get("origin") == "human" else r.get("origin", "import"), created_by=user_id,
                                **_copy(r, ["source_type", "relation_type", "target_type", "weight", "status", "confidence", "note"])))
            inc("created", "relationships")
        db.flush()

        # Embeddings -------------------------------------------------------------------------------
        emb_report = {"imported": 0, "regenerate": regenerate}
        if not regenerate:
            from app.ai import registry

            cur_t, cur_v = registry.text_embedder(db), registry.visual_embedder(db)
            for e in (json.loads((root / "embeddings" / "README.json").read_text()).get("models", [])
                      if (root / "embeddings" / "README.json").exists() else []):
                compatible = (e["modality"] == "text" and e["model"] == cur_t.model and e["dimensions"] == cur_t.dimensions) or \
                             (e["modality"] == "visual" and e["model"] == cur_v.model and e["dimensions"] == cur_v.dimensions)
                if not compatible:
                    continue
                for line in (root / e["file"]).read_text().splitlines():
                    if not line.strip():
                        continue
                    v = json.loads(line)
                    eid = ids.get(v["entity_id"])
                    if not eid or eid not in ids.created:
                        continue  # only newly created entities; mapped duplicates keep their own vectors
                    db.add(Embedding(organization_id=org_id, brand_id=ids.get(v["brand_id"]), entity_type=v["entity_type"], entity_id=eid,
                                     segment=v["segment"], modality=e["modality"], provider=e.get("provider") or "imported", model=e["model"],
                                     dimensions=e["dimensions"], embedding=v["vector"], content_hash=v["content_hash"]))
                    emb_report["imported"] += 1
            db.flush()
        report["embeddings"] = emb_report
        report["target_brand_ids"] = sorted({str(ids.get(b["id"])) for b in data["brands"]})
        report["id_map_size"] = len(ids.m)
        return {"report": report, "id_map": {k: str(v) for k, v in ids.m.items()}, "written": written}
    except Exception:
        for key in written:
            try:
                store.delete(key)
            except Exception:  # noqa: BLE001
                pass
        raise


def _remap_payload(p: dict[str, Any], ids: Mapper) -> dict[str, Any]:
    out = dict(p)
    for k in ("asset_id", "concept_id", "example_asset_id", "source_id", "target_id"):
        if out.get(k) and ids.get(out[k]):
            out[k] = str(ids.get(out[k]))
    return out


def stage_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="bdna-import-"))


def cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
