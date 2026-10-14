"""Asynchronous multimodal ingestion pipeline (runs in the worker).

Steps (each recorded on the job): download+verify → media processing & derivatives →
AI analysis (stored as pending_review interpretations) → structured validation → suggestions
(tags, concept links, new concepts, principle candidates) → embeddings (text + visual) →
semantic relationship suggestions → status. Nothing here ever creates *approved* knowledge.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session

from app.ai import registry
from app.ai.base import ImageInput, ProviderError
from app.ai.dev import DEV_PROVIDER, describe_measurements
from app.ai.prompts import get_prompt
from app.ai.schemas import (
    ANALYSIS_SCHEMA_VERSION,
    DocumentAnalysisOutput,
    ImageAnalysisOutput,
    VideoAnalysisOutput,
    validate,
)
from app.config import get_settings
from app.jobs.queue import JobContext, PermanentJobError
from app.media import documents as docs
from app.media import image as imgmod
from app.media import model3d, video
from app.models import (
    AestheticConcept,
    AiSuggestion,
    Asset,
    AssetAnalysis,
    AssetDerivative,
    AssetSegment,
    AssetTag,
    Brand,
    Embedding,
    KnowledgeEntry,
    Principle,
)
from app.services import embeddings as emb
from app.storage.backends import TenantStorage


@dataclass
class DerivSpec:
    kind: str
    data: bytes
    mime: str
    width: int | None = None
    height: int | None = None
    page_number: int | None = None
    timestamp_ms: int | None = None
    segment_index: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    ext: str = "webp"


@dataclass
class SegSpec:
    segment_type: str
    index: int
    start_ms: int | None = None
    end_ms: int | None = None
    page_number: int | None = None
    title: str | None = None
    text_content: str | None = None
    keyframe_ref: int | None = None  # index into derivatives list
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Processed:
    family: str
    media_metadata: dict[str, Any]
    derivatives: list[DerivSpec] = field(default_factory=list)
    segments: list[SegSpec] = field(default_factory=list)
    analysis_images: list[ImageInput] = field(default_factory=list)
    document: docs.ExtractedDocument | None = None
    scenes: list[video.Scene] = field(default_factory=list)
    motion: dict[str, Any] = field(default_factory=dict)
    visual_embed_images: list[tuple[int, Path, str]] = field(default_factory=list)


def family_for(mime: str, asset_type: str) -> str:
    if mime == "image/svg+xml":
        return "svg"
    if mime.startswith("image/") or mime == "image/vnd.adobe.photoshop":
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("model/") or "fbx" in mime:
        return "model_3d"
    if mime in ("application/pdf", "application/postscript") or "officedocument" in mime or mime.startswith("text/") or mime == "application/json":
        return "document"
    return "other"


# --- Media processors ----------------------------------------------------------------------------
def _image_derivatives(img: Image.Image, work: Path, label: str = "main") -> tuple[list[DerivSpec], Path]:
    thumb, tw, th = imgmod.render_derivative(img, 480)
    prev, pw, ph = imgmod.render_derivative(img, 1600, quality=86)
    prev_path = work / f"preview-{label}.webp"
    prev_path.write_bytes(prev)
    return [
        DerivSpec("thumbnail", thumb, "image/webp", tw, th),
        DerivSpec("preview", prev, "image/webp", pw, ph),
    ], prev_path


def _measure(img: Image.Image) -> dict[str, Any]:
    return {"palette": imgmod.extract_palette(img), "stats": imgmod.image_stats(img)}


def process_image(src: Path, work: Path) -> Processed:
    probe = imgmod.probe(src)
    img = imgmod.open_image(src)
    m = _measure(img)
    derivs, prev_path = _image_derivatives(img, work)
    meta = {**probe, "palette": m["palette"], "image_stats": m["stats"], "perceptual_hash": imgmod.ahash(img)}
    measurements = {"probe": probe, **m}
    return Processed(
        "image",
        meta,
        derivs,
        analysis_images=[ImageInput(prev_path, "image/webp", None, measurements)],
        visual_embed_images=[(0, prev_path, "image")],
    )


def process_svg(src: Path, work: Path) -> Processed:
    import pymupdf

    doc = pymupdf.open(stream=src.read_bytes(), filetype="svg")
    page = doc[0]
    pix = page.get_pixmap(dpi=int(144 * min(4.0, max(1.0, 1600 / max(page.rect.width, page.rect.height, 1)))))
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    img.load()
    m = _measure(img)
    derivs, prev_path = _image_derivatives(img, work)
    meta = {
        "format": "SVG", "vector": True, "width": int(page.rect.width), "height": int(page.rect.height),
        "palette": m["palette"], "image_stats": m["stats"],
        "orientation": "landscape" if page.rect.width > page.rect.height else "portrait" if page.rect.height > page.rect.width else "square",
    }
    return Processed("image", meta, derivs, analysis_images=[ImageInput(prev_path, "image/webp", None, {"probe": meta, **m})],
                     visual_embed_images=[(0, prev_path, "svg render")])


def process_video(src: Path, work: Path) -> Processed:
    s = get_settings()
    probe = video.ffprobe(src)
    if not probe.get("has_video"):
        raise PermanentJobError("file has no video stream")
    duration = probe.get("duration_seconds") or 0.0
    scenes = video.detect_scenes(src, duration)
    motion = video.analyze_motion(src, scenes)
    # keyframes: one per scene, evenly sub-sampled to the cap
    cap = max(1, s.max_video_keyframes)
    pick = scenes if len(scenes) <= cap else [scenes[round(i * (len(scenes) - 1) / (cap - 1))] for i in range(cap)]
    derivs: list[DerivSpec] = []
    segs: list[SegSpec] = []
    frame_paths: list[tuple[video.Scene, Path]] = []
    for sc in pick:
        fp = work / f"kf-{sc.index:04d}.jpg"
        try:
            video.extract_frame(src, sc.keyframe_s, fp)
        except video.MediaToolError:
            continue
        frame_paths.append((sc, fp))
    keyframe_ref: dict[int, int] = {}
    analysis_images: list[ImageInput] = []
    visual: list[tuple[int, Path, str]] = []
    for sc, fp in frame_paths:
        img = Image.open(fp)
        img.load()
        data, w, h = imgmod.render_derivative(img, 1280, quality=84)
        keyframe_ref[sc.index] = len(derivs)
        derivs.append(DerivSpec("keyframe", data, "image/webp", w, h, timestamp_ms=int(sc.keyframe_s * 1000),
                                segment_index=sc.index, meta={"scene": sc.index}))
        visual.append((sc.index + 1, fp, f"scene {sc.index} keyframe @ {sc.keyframe_s:.1f}s"))
    if frame_paths:
        longest = max(frame_paths, key=lambda x: x[0].duration_s)
        poster = Image.open(longest[1])
        poster.load()
        d, _ = _image_derivatives(poster, work, "poster")
        derivs += [DerivSpec("poster", d[1].data, "image/webp", d[1].width, d[1].height, timestamp_ms=int(longest[0].keyframe_s * 1000))]
        derivs += [d[0]]  # thumbnail
        visual.insert(0, (0, work / "preview-poster.webp", "poster"))
        sheet = video.contact_sheet([fp for _, fp in frame_paths[:16]], work / "contact.jpg")
        if sheet:
            derivs.append(DerivSpec("contact_sheet", sheet.read_bytes(), "image/jpeg", meta={"frames": min(16, len(frame_paths))}, ext="jpg"))
        # images for AI: evenly spaced keyframes
        n = min(len(frame_paths), s.ai_max_images_per_asset)
        chosen = [frame_paths[round(i * (len(frame_paths) - 1) / max(1, n - 1))] for i in range(n)] if n > 1 else frame_paths[:1]
        for sc, fp in chosen:
            img = Image.open(fp)
            img.load()
            analysis_images.append(
                ImageInput(fp, "image/jpeg", f"scene {sc.index} @ {sc.keyframe_s:.1f}s",
                           {"probe": {**probe, "width": img.width, "height": img.height}, **_measure(img), "scene_index": sc.index})
            )
    for sc in scenes:
        segs.append(
            SegSpec("scene", sc.index, int(sc.start_s * 1000), int(sc.end_s * 1000),
                    title=f"Scene {sc.index + 1} ({sc.start_s:.1f}s–{sc.end_s:.1f}s)",
                    keyframe_ref=keyframe_ref.get(sc.index),
                    meta={"duration_s": round(sc.duration_s, 3), "motion": sc.motion})
        )
    meta = {
        **probe,
        "scene_count": len(scenes),
        "scenes": [{"index": sc.index, "start_s": sc.start_s, "end_s": sc.end_s, "camera_movement": sc.motion.get("camera_movement")} for sc in scenes],
        "motion": motion,
        "keyframe_count": len(frame_paths),
    }
    if analysis_images:
        meta["palette"] = analysis_images[0].measurements.get("palette", [])
    return Processed("video", meta, derivs, segs, analysis_images, scenes=scenes, motion=motion, visual_embed_images=visual)


def process_document(src: Path, work: Path, mime: str) -> Processed:
    d = docs.extract(src, mime)
    derivs: list[DerivSpec] = []
    visual: list[tuple[int, Path, str]] = []
    images: list[ImageInput] = []
    for i, (page_no, png) in enumerate(d.renders):
        img = Image.open(io.BytesIO(png))
        img.load()
        data, w, h = imgmod.render_derivative(img, 1200, quality=82)
        derivs.append(DerivSpec("page_render", data, "image/webp", w, h, page_number=page_no))
        if i == 0:
            first, prev_path = _image_derivatives(img, work, "page1")
            derivs += first
            visual.append((0, prev_path, "page 1"))
            images.append(ImageInput(prev_path, "image/webp", "page 1", {"probe": {"width": img.width, "height": img.height}, **_measure(img)}))
    for j, (page_no, data, ext) in enumerate(d.images[:24]):
        mime_e = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext.lower(), f"image/{ext.lower()}")
        try:
            im = Image.open(io.BytesIO(data))
            w, h = im.size
        except Exception:  # noqa: BLE001
            continue
        derivs.append(DerivSpec("extracted_image", data, mime_e, w, h, page_number=page_no, meta={"index": j}, ext=ext.lower()))
    segs = [
        SegSpec("page", p.number - 1, page_number=p.number, title=(p.headings[0] if p.headings else f"Page {p.number}")[:300],
                text_content=p.text[:100000], meta={"ocr": p.ocr, "tables": p.tables[:3], "headings": p.headings[:10]})
        for p in d.pages
    ]
    meta = {
        **{k: v for k, v in d.metadata.items() if k != "docling_markdown"},
        "engine": d.engine,
        "headings": d.headings[:200],
        "extracted_text_chars": len(d.full_text),
        "embedded_image_count": len(d.images),
        "document_type": mime,
    }
    return Processed("document", meta, derivs, segs, images, document=d, visual_embed_images=visual)


def process_model_3d(src: Path, work: Path, mime: str) -> Processed:
    info = model3d.inspect(src, mime)
    derivs: list[DerivSpec] = []
    images: list[ImageInput] = []
    visual = []
    png = model3d.render_preview(src, mime)
    if png:
        img = Image.open(io.BytesIO(png))
        img.load()
        d, prev_path = _image_derivatives(img, work, "render")
        derivs += d
        images.append(ImageInput(prev_path, "image/webp", "3D preview render", {"probe": {"width": img.width, "height": img.height, "orientation": "square"}, **_measure(img)}))
        visual.append((0, prev_path, "3D render"))
    return Processed("model_3d", info, derivs, analysis_images=images, visual_embed_images=visual)


def process_audio(src: Path, work: Path) -> Processed:
    return Processed("audio", video.ffprobe(src))


def run_processor(family: str, src: Path, work: Path, mime: str) -> Processed:
    if family == "image":
        return process_image(src, work)
    if family == "svg":
        return process_svg(src, work)
    if family == "video":
        return process_video(src, work)
    if family == "document":
        if mime == "application/postscript":
            return Processed("document", {"note": "PostScript/EPS stored; no rasteriser configured"})
        return process_document(src, work, mime)
    if family == "model_3d":
        return process_model_3d(src, work, mime)
    if family == "audio":
        return process_audio(src, work)
    return Processed("other", {})


# --- Persistence helpers ----------------------------------------------------------------------
def replace_derivatives(db: Session, store: TenantStorage, asset: Asset, p: Processed) -> None:
    # Derivatives are regenerated on reprocessing; originals are never touched.
    store.delete_prefix(store.asset_derivatives_prefix(asset.brand_id, asset.id))
    db.execute(update(AssetSegment).where(AssetSegment.asset_id == asset.id).values(keyframe_derivative_id=None))
    db.execute(delete(AssetDerivative).where(AssetDerivative.asset_id == asset.id))
    db.execute(delete(AssetSegment).where(AssetSegment.asset_id == asset.id))
    db.flush()
    created: list[AssetDerivative] = []
    for i, d in enumerate(p.derivatives):
        did = uuid.uuid4()
        name = f"{d.page_number or d.segment_index or i:04d}-{did.hex[:8]}.{d.ext}"
        obj = store.put_bytes(store.derivative_key(asset.brand_id, asset.id, d.kind, name), d.data, d.mime)
        row = AssetDerivative(
            id=did, organization_id=asset.organization_id, asset_id=asset.id, kind=d.kind, storage_uri=obj.uri,
            mime_type=d.mime, width=d.width, height=d.height, file_size=obj.size, checksum=obj.sha256,
            page_number=d.page_number, timestamp_ms=d.timestamp_ms, segment_index=d.segment_index, meta=d.meta,
        )
        db.add(row)
        created.append(row)
    db.flush()
    for s in p.segments:
        db.add(
            AssetSegment(
                organization_id=asset.organization_id, asset_id=asset.id, segment_type=s.segment_type,
                segment_index=s.index, start_ms=s.start_ms, end_ms=s.end_ms, page_number=s.page_number,
                title=s.title, text_content=s.text_content, meta=s.meta,
                keyframe_derivative_id=created[s.keyframe_ref].id if s.keyframe_ref is not None and s.keyframe_ref < len(created) else None,
            )
        )
    db.flush()


def brand_context(db: Session, brand_id: uuid.UUID) -> tuple[str, list[dict[str, Any]], str]:
    brand = db.scalar(select(Brand).where(Brand.id == brand_id))
    concepts = [
        {"name": c.name, "slug": c.slug, "definition": c.definition, "synonyms": c.synonyms, "id": str(c.id)}
        for c in db.scalars(
            select(AestheticConcept).where(
                AestheticConcept.brand_id == brand_id, AestheticConcept.status.in_(["approved", "draft", "in_review"])
            )
        )
    ]
    principles = db.scalars(
        select(Principle).where(Principle.brand_id == brand_id, Principle.status == "approved").order_by(Principle.priority).limit(15)
    ).all()
    entries = db.scalars(
        select(KnowledgeEntry).where(
            KnowledgeEntry.brand_id == brand_id, KnowledgeEntry.status == "approved",
            KnowledgeEntry.domain_key.in_(["brand_foundation", "art_direction"]),
        ).limit(8)
    ).all()
    ctx = "\n".join(
        [f"- [{p.code}] ({p.classification}) {p.statement}" for p in principles]
        + [f"- {e.title}: {(e.summary or e.body or '')[:300]}" for e in entries]
    )
    return (brand.name if brand else "brand"), concepts, ctx


def _record_analysis(
    db: Session, asset: Asset, analysis_type: str, result, prompt, out_model, objective_extra: dict | None, job_id
) -> AssetAnalysis:  # noqa: ANN001
    parsed, errors = validate(out_model, result.data)
    data = parsed.model_dump()
    objective = data.get("objective", {}) or {}
    if objective_extra:
        objective = {**objective, **objective_extra}
    if out_model is VideoAnalysisOutput:
        objective["scenes"] = data.get("scenes", [])
        objective["temporal_description"] = data.get("temporal_description", "")
    if out_model is DocumentAnalysisOutput:
        objective["principle_candidates_found"] = len(data.get("principle_candidates", []))
    # supersede older pending analyses of the same type
    db.execute(
        update(AssetAnalysis)
        .where(AssetAnalysis.asset_id == asset.id, AssetAnalysis.analysis_type == analysis_type, AssetAnalysis.status == "pending_review")
        .values(status="superseded")
    )
    a = AssetAnalysis(
        organization_id=asset.organization_id,
        brand_id=asset.brand_id,
        asset_id=asset.id,
        analysis_type=analysis_type,
        provider=result.provider,
        model=result.model,
        prompt_key=prompt.key,
        prompt_version=prompt.version,
        schema_version=ANALYSIS_SCHEMA_VERSION,
        objective=objective,
        interpretive=data.get("interpretive", {}),
        raw_output={"data": result.data, "usage": result.usage},
        validation_errors=errors,
        confidence=data.get("confidence"),
        processing_ms=result.latency_ms,
        is_development_adapter=result.is_development_adapter,
        job_id=job_id,
    )
    db.add(a)
    db.flush()
    return a


def run_analysis(db: Session, asset: Asset, p: Processed, job_id: uuid.UUID) -> tuple[AssetAnalysis | None, Any]:
    brand_name, concepts, bctx = brand_context(db, asset.brand_id)
    vocab = ", ".join(c["name"] for c in concepts) or "(none defined yet)"
    if p.family in ("image", "model_3d") and p.analysis_images:
        prompt = get_prompt(db, "image_analysis")
        meas = p.analysis_images[0].measurements
        rendered = prompt.render(brand_name=brand_name, brand_context=bctx or "(none)", concept_vocabulary=vocab,
                                 measurements=json.dumps({"palette": meas.get("palette"), "stats": meas.get("stats")}, default=str)[:5000])
        result = registry.vision_provider(db).analyze_images(p.analysis_images, rendered, {"concepts": concepts, "measurements": meas})
        atype = "image_visual" if p.family == "image" else "model_3d_visual"
        return _record_analysis(db, asset, atype, result, prompt, ImageAnalysisOutput, None, job_id), result.data
    if p.family == "video" and p.analysis_images:
        prompt = get_prompt(db, "video_synthesis")
        vision = registry.vision_provider(db)
        scene_obs = []
        for sc in p.scenes:
            img = next((i for i in p.analysis_images if i.measurements.get("scene_index") == sc.index), None)
            obs: dict[str, Any] = {"index": sc.index, "start_s": sc.start_s, "end_s": sc.end_s, "motion": sc.motion}
            if img is not None and vision.name == DEV_PROVIDER:
                kf = vision.analyze_images([img], "", {"concepts": concepts}).data
                obs["keyframe_analysis"] = kf
                obs["families"] = describe_measurements(img.measurements)["families"]
            scene_obs.append(obs)
        objective_extra = {"motion": p.motion, "duration_seconds": p.media_metadata.get("duration_seconds"),
                           "frame_rate": p.media_metadata.get("frame_rate"), "resolution": [p.media_metadata.get("width"), p.media_metadata.get("height")],
                           "palette": p.media_metadata.get("palette", [])}
        if vision.name == DEV_PROVIDER:
            result = registry.text_provider(db).complete_json(
                "", {"task": "video_synthesis", "scenes": scene_obs, "motion": p.motion, "probe": p.media_metadata, "concepts": concepts}
            )
        else:
            rendered = prompt.render(
                brand_name=brand_name, concept_vocabulary=vocab,
                scene_observations=json.dumps([{k: v for k, v in o.items() if k != "families"} for o in scene_obs], default=str)[:8000],
                measurements=json.dumps(objective_extra, default=str)[:4000],
            )
            result = vision.analyze_images(p.analysis_images, rendered, {"concepts": concepts})
        a = _record_analysis(db, asset, "video_temporal", result, prompt, VideoAnalysisOutput, objective_extra, job_id)
        # write scene descriptions back onto the segments for scene-level retrieval
        for sc in (a.objective or {}).get("scenes", []):
            db.execute(
                update(AssetSegment)
                .where(AssetSegment.asset_id == asset.id, AssetSegment.segment_type == "scene", AssetSegment.segment_index == sc.get("index"))
                .values(text_content=sc.get("description"))
            )
        return a, result.data
    if p.family == "document" and p.document is not None:
        prompt = get_prompt(db, "document_principles")
        d = p.document
        rendered = prompt.render(
            brand_name=brand_name, title=d.metadata.get("title") or asset.title,
            headings=json.dumps([h["text"] for h in d.headings[:60]]), text=d.full_text[:60000],
        )
        result = registry.text_provider(db).complete_json(
            rendered,
            {"task": "document_principles", "title": d.metadata.get("title") or asset.title,
             "pages": [{"number": pg.number, "text": pg.text} for pg in d.pages], "concepts": concepts},
        )
        extra = {"structure": {"page_count": d.metadata.get("page_count"), "headings": d.headings[:100],
                               "table_count": d.metadata.get("table_count"), "word_count": d.metadata.get("word_count"),
                               "ocr_pages": d.metadata.get("ocr_pages", [])},
                 "document_metadata": {k: v for k, v in d.metadata.items() if k in ("title", "author", "subject", "keywords", "creator", "producer", "created", "creationDate")}}
        return _record_analysis(db, asset, "document_structure", result, prompt, DocumentAnalysisOutput, extra, job_id), result.data
    return None, None


def create_suggestions(db: Session, asset: Asset, analysis: AssetAnalysis, raw: dict[str, Any]) -> dict[str, int]:
    counts = {"tags": 0, "concept_links": 0, "new_concepts": 0, "principles": 0}
    interp = analysis.interpretive or {}
    existing_tags = set(db.scalars(select(AssetTag.tag).where(AssetTag.asset_id == asset.id)))
    for t in (interp.get("suggested_tags") or [])[:15]:
        tag = " ".join(str(t).strip().lower().split())[:80]
        if tag and tag not in existing_tags:
            db.add(AssetTag(organization_id=asset.organization_id, asset_id=asset.id, tag=tag, source="ai", status="suggested",
                            confidence=analysis.confidence, analysis_id=analysis.id))
            existing_tags.add(tag)
            counts["tags"] += 1
    concepts = db.scalars(select(AestheticConcept).where(AestheticConcept.brand_id == asset.brand_id)).all()
    by_name: dict[str, AestheticConcept] = {}
    for c in concepts:
        for n in [c.name, c.slug, *(c.synonyms or [])]:
            by_name[n.strip().lower()] = c
    pending_new = {
        s.title.lower()
        for s in db.scalars(select(AiSuggestion).where(AiSuggestion.brand_id == asset.brand_id,
                                                       AiSuggestion.suggestion_type == "aesthetic_concept", AiSuggestion.status == "pending"))
    }
    for cm in interp.get("aesthetic_concepts") or []:
        name = str(cm.get("name", "")).strip()
        if not name:
            continue
        conf = float(cm.get("confidence") or 0.5)
        c = by_name.get(name.lower())
        if c is not None:
            counts["concept_links"] += _suggest_concept_link(db, asset, c, conf, cm.get("evidence"), analysis.id)
        elif conf >= 0.55 and name.lower() not in pending_new:
            db.add(AiSuggestion(
                organization_id=asset.organization_id, brand_id=asset.brand_id, suggestion_type="aesthetic_concept",
                title=name[:300], payload={"name": name, "definition": cm.get("evidence") or "", "example_asset_id": str(asset.id)},
                rationale=f"Proposed by {analysis.provider} while analysing '{asset.title}'", confidence=conf,
                source_asset_id=asset.id, source_analysis_id=analysis.id,
            ))
            pending_new.add(name.lower())
            counts["new_concepts"] += 1
    for pc in (raw or {}).get("principle_candidates") or []:
        if not isinstance(pc, dict) or not pc.get("statement"):
            continue
        db.add(AiSuggestion(
            organization_id=asset.organization_id, brand_id=asset.brand_id, suggestion_type="principle",
            title=str(pc.get("title") or pc["statement"][:80])[:300], payload=pc,
            rationale=f"Extracted from '{asset.title}'" + (f", page {pc.get('source_page')}" if pc.get("source_page") else ""),
            confidence=pc.get("confidence"), source_asset_id=asset.id, source_analysis_id=analysis.id,
        ))
        counts["principles"] += 1
    db.flush()
    return counts


def _suggest_concept_link(db: Session, asset: Asset, concept: AestheticConcept, conf: float, evidence: str | None,
                          analysis_id: uuid.UUID | None, method: str = "analysis") -> int:
    dup = db.scalar(
        select(AiSuggestion.id).where(
            AiSuggestion.suggestion_type == "concept_link", AiSuggestion.source_asset_id == asset.id,
            AiSuggestion.payload["concept_id"].astext == str(concept.id), AiSuggestion.status.in_(["pending", "accepted"]),
        )
    )
    if dup:
        return 0
    db.add(AiSuggestion(
        organization_id=asset.organization_id, brand_id=asset.brand_id, suggestion_type="concept_link",
        title=f"'{asset.title}' exemplifies {concept.name}"[:300],
        payload={"asset_id": str(asset.id), "concept_id": str(concept.id), "concept_name": concept.name,
                 "relation_type": "exemplifies", "method": method},
        rationale=evidence, confidence=round(conf, 3), source_asset_id=asset.id, source_analysis_id=analysis_id,
    ))
    return 1


def semantic_concept_suggestions(db: Session, asset: Asset, analysis_id: uuid.UUID | None, threshold: float = 0.32, top: int = 3) -> int:
    """Nearest concepts to the asset's text embedding (same model) -> concept-link suggestions."""
    row = db.scalar(
        select(Embedding).where(Embedding.entity_type == "asset", Embedding.entity_id == asset.id,
                                Embedding.modality == "text", Embedding.segment == 0)
    )
    if row is None:
        return 0
    dims = row.dimensions
    rows = db.execute(
        text(
            f"""SELECT e.entity_id, 1 - ((e.embedding::vector({dims})) <=> CAST(:q AS vector({dims}))) AS sim
                  FROM embeddings e
                 WHERE e.entity_type = 'aesthetic_concept' AND e.brand_id = :b AND e.modality = 'text'
                   AND e.model = :m AND e.dimensions = :d
                 ORDER BY (e.embedding::vector({dims})) <=> CAST(:q AS vector({dims})) LIMIT :k"""
        ),
        {"q": emb.vec_literal(row.embedding), "b": asset.brand_id, "m": row.model, "d": dims, "k": top},
    ).all()
    n = 0
    for cid, sim in rows:
        if sim is None or sim < threshold:
            continue
        c = db.scalar(select(AestheticConcept).where(AestheticConcept.id == cid))
        if c is not None and c.brand_relevance != "avoid":
            n += _suggest_concept_link(db, asset, c, float(sim), f"semantic similarity {sim:.2f} ({row.model})", analysis_id, "embedding")
    return n


def embed_asset(db: Session, asset: Asset, p: Processed | None) -> dict[str, int]:
    out = {"text": emb.reindex_text(db, "asset", asset.id), "segments": 0, "visual": 0}
    for seg in db.scalars(select(AssetSegment).where(AssetSegment.asset_id == asset.id)):
        if seg.text_content and len(seg.text_content.strip()) > 20:
            out["segments"] += emb.reindex_text(db, "asset_segment", seg.id)
    if p and p.visual_embed_images:
        out["visual"] = emb.embed_images(db, org_id=asset.organization_id, brand_id=asset.brand_id, entity_type="asset",
                                         entity_id=asset.id, images=[i for i in p.visual_embed_images if i[1].exists()])
    return out


# --- Orchestration --------------------------------------------------------------------------------
def ingest(ctx: JobContext, *, do_media: bool = True, do_ai: bool = True, do_embed: bool = True) -> dict[str, Any]:
    asset_id = ctx.job.entity_id
    store = TenantStorage(ctx.org_id)
    with ctx.session() as db:
        a = db.scalar(select(Asset).where(Asset.id == asset_id))
        if a is None or a.deleted_at is not None:
            raise PermanentJobError("asset not found or deleted")
        a.processing_status, a.processing_error = "processing", None
        mime, atype, uri, checksum = a.mime_type or "", a.asset_type, a.storage_uri, a.checksum
    if not uri:
        with ctx.session() as db:
            a = db.scalar(select(Asset).where(Asset.id == asset_id))
            r = embed_asset(db, a, None) if do_embed else {}
            a.processing_status = "skipped"
        return {"embeddings": r}
    family = family_for(mime, atype)
    work = Path(tempfile.mkdtemp(prefix="bdna-ingest-"))
    failures: list[str] = []
    result: dict[str, Any] = {"family": family}
    try:
        t = time.perf_counter()
        src = work / "original"
        store.download_to(store.key_for_uri(uri), src)
        actual = hashlib.sha256(src.read_bytes()).hexdigest()
        if actual != checksum:
            raise PermanentJobError(f"original checksum mismatch (expected {checksum}, got {actual})")
        ctx.step("download_verify", "ok", t)
        ctx.progress(10)

        processed: Processed | None = None
        if do_media:
            t = time.perf_counter()
            try:
                processed = run_processor(family, src, work, mime)
                with ctx.session() as db:
                    a = db.scalar(select(Asset).where(Asset.id == asset_id))
                    replace_derivatives(db, store, a, processed)
                    a.media_metadata = json.loads(json.dumps(processed.media_metadata, default=str))
                ctx.step("media_processing", "ok", t, derivatives=len(processed.derivatives), segments=len(processed.segments))
            except PermanentJobError:
                raise
            except Exception as e:  # noqa: BLE001
                failures.append(f"media_processing: {type(e).__name__}: {e}")
                ctx.step("media_processing", "failed", t, error=str(e)[:500])
        ctx.progress(45)

        analysis_id = None
        if do_ai and processed is not None and processed.family != "audio":
            t = time.perf_counter()
            try:
                with ctx.session() as db:
                    a = db.scalar(select(Asset).where(Asset.id == asset_id))
                    analysis, raw = run_analysis(db, a, processed, ctx.job.id)
                    if analysis is not None:
                        analysis_id = analysis.id
                        counts = create_suggestions(db, a, analysis, raw)
                        ctx.step("ai_analysis", "ok", t, provider=analysis.provider, model=analysis.model,
                                 validation_errors=len(analysis.validation_errors), suggestions=counts)
                    else:
                        ctx.step("ai_analysis", "skipped", t)
            except ProviderError as e:
                failures.append(f"ai_analysis: {e}")
                ctx.step("ai_analysis", "failed", t, error=str(e)[:500])
        ctx.progress(70)

        if do_embed:
            t = time.perf_counter()
            try:
                with ctx.session() as db:
                    a = db.scalar(select(Asset).where(Asset.id == asset_id))
                    counts = embed_asset(db, a, processed)
                    counts["semantic_concept_suggestions"] = semantic_concept_suggestions(db, a, analysis_id)
                ctx.step("embeddings", "ok", t, **counts)
            except ProviderError as e:
                failures.append(f"embeddings: {e}")
                ctx.step("embeddings", "failed", t, error=str(e)[:500])
        ctx.progress(95)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    with ctx.session() as db:
        a = db.scalar(select(Asset).where(Asset.id == asset_id))
        a.processing_status = "partial" if failures else "processed"
        a.processing_error = "\n".join(failures) or None
        pending = db.scalar(select(func.count()).select_from(AiSuggestion).where(AiSuggestion.source_asset_id == asset_id, AiSuggestion.status == "pending"))
        from app.services.events import emit

        emit(db, ctx.org_id, "asset.processed", {"asset_id": str(asset_id), "status": a.processing_status, "pending_suggestions": pending})
    result["failures"] = failures
    return result
