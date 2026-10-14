"""DEVELOPMENT ADAPTERS — offline, deterministic, no API key required.

Clearly labelled (`provider="dev-heuristic"`, `is_development_adapter=True` on every record).
They make the whole pipeline functional without credentials:

* DevVisionProvider   phrases *measured* image statistics (palette, tonal range, saliency,
                      line structure…) in art-direction vocabulary and matches them to the
                      brand's own concept vocabulary. It cannot recognise objects or materials.
* DevTextProvider     mines modal sentences ("must", "never", "prefer"…) from documents into
                      principle candidates — real, useful, but rule-based.
* DevTextEmbedder     hashed lexical embedding (unigrams, bigrams, char-trigrams + aesthetic
                      lexicon families), 384-d.
* DevVisualEmbedder   colour/layout/edge/texture descriptor, 256-d — real visual similarity for
                      palette and composition, not semantics.

Swap in a production provider with BDNA_AI_*_PROVIDER (see .env.example).
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.ai import lexicon
from app.ai.base import AiResult, ImageInput

DEV_PROVIDER = "dev-heuristic"


def _level(x: float, lo: float, hi: float, words: tuple[str, str, str]) -> str:
    return words[0] if x < lo else words[2] if x > hi else words[1]


# --- Vision --------------------------------------------------------------------------------------
def describe_measurements(m: dict[str, Any]) -> dict[str, Any]:
    """Turn objective measurements into objective + interpretive fields and descriptor families."""
    stats = m.get("stats", {})
    palette = m.get("palette", [])
    probe = m.get("probe", {})
    fams: dict[str, float] = {}

    def add(f: str, w: float = 1.0) -> None:
        fams[f] = fams.get(f, 0.0) + w

    contrast = _level(stats.get("contrast", 0.45), 0.32, 0.58, ("low", "medium", "high"))
    key = stats.get("key", "mid-key")
    quality = (
        "hard, directional" if contrast == "high" and key != "high-key"
        else "soft, diffused" if contrast == "low"
        else "balanced"
    )
    colorfulness = stats.get("colorfulness", 0.3)
    chroma_word = _level(colorfulness, 0.22, 0.55, ("muted", "balanced", "vibrant"))
    warmth = stats.get("warmth", 0.0)
    temp_word = "warm" if warmth > 0.15 else "cool" if warmth < -0.08 else "neutral"
    neg = stats.get("negative_space_ratio", 0.0)
    edge = stats.get("edge_density", 0.05)
    lines = stats.get("straight_lines", 0)
    curves = stats.get("curved_contours", 0)
    orient = stats.get("line_orientation", {})
    sym = stats.get("symmetry", 0.5)

    composition = {
        "framing": probe.get("orientation", "unknown") + " frame",
        "layout": "centered subject" if stats.get("focus_centered") else "rule-of-thirds placement" if stats.get("focus_near_thirds") else "off-centre focal weight",
        "focal_point": f"visual weight around x={stats.get('focus_point', [0.5, 0.5])[0]:.2f}, y={stats.get('focus_point', [0.5, 0.5])[1]:.2f}",
        "symmetry": "strong bilateral symmetry" if sym > 0.86 else "asymmetric balance" if sym < 0.7 else "loose symmetry",
        "negative_space": "generous negative space" if neg > 0.45 else "moderate negative space" if neg > 0.2 else "dense, filled frame",
    }
    geometry = []
    if lines > 20 and orient.get("horizontal", 0) + orient.get("vertical", 0) > orient.get("diagonal", 0):
        geometry.append("rectilinear structure (horizontal/vertical lines)")
        add("geometric")
        add("architectural", 0.7)
    if orient.get("diagonal", 0) > max(6, orient.get("horizontal", 0) + orient.get("vertical", 0)):
        geometry.append("dynamic diagonals")
        add("geometric", 0.5)
    if curves > max(8, lines * 0.6):
        geometry.append("curvilinear, rounded contours")
        add("organic", 1.2)
    textures = ["fine, detailed texture"] if edge > 0.12 else ["smooth, quiet surfaces"] if edge < 0.04 else ["moderate surface detail"]
    if edge > 0.12:
        add("material", 0.8)
    if neg > 0.45 and edge < 0.08:
        add("minimal", 1.5)
    if key == "high-key":
        add("bright")
    if key == "low-key":
        add("dark")
    if contrast == "high":
        add("contrast_high")
        if key != "high-key":
            add("cinematic", 0.8)
    if contrast == "low":
        add("contrast_low")
    add({"muted": "muted", "vibrant": "vibrant", "balanced": "muted"}[chroma_word], 1.0 if chroma_word != "balanced" else 0.3)
    if temp_word in ("warm", "cool"):
        add(temp_word)
    if sym > 0.86 and lines > 10:
        add("architectural", 0.5)
        add("elegant", 0.4)

    atmosphere = []
    if key == "high-key" and contrast != "high":
        atmosphere += ["airy", "calm"]
    if key == "low-key" or (contrast == "high" and key != "high-key"):
        atmosphere += ["dramatic", "moody"]
    if chroma_word == "muted":
        atmosphere += ["understated"]
    if chroma_word == "vibrant":
        atmosphere += ["energetic"]
    if temp_word == "warm":
        atmosphere += ["warm", "inviting"]
    if temp_word == "cool":
        atmosphere += ["cool", "composed"]
    if neg > 0.45:
        atmosphere += ["quiet"]

    style = []
    if fams.get("minimal"):
        style.append("minimal")
    if fams.get("architectural", 0) >= 0.7:
        style.append("architectural")
    if fams.get("organic"):
        style.append("organic")
    if fams.get("cinematic"):
        style.append("cinematic")
    if chroma_word == "vibrant" and contrast == "high":
        style.append("graphic")

    top = [p for p in palette if p.get("proportion", 0) >= 0.08][:4]
    color_words = ", ".join(dict.fromkeys(p["name"] for p in top)) or "mixed colours"
    w, h = probe.get("width"), probe.get("height")
    description = (
        f"{probe.get('orientation', 'image').capitalize()} image"
        + (f" ({w}×{h})" if w and h else "")
        + f" with a {chroma_word}, {temp_word} palette dominated by {color_words}; "
        f"{quality} {key} lighting {stats.get('light_direction', '')}; {composition['layout']}; {composition['negative_space']}."
        " [measurement-based description — the development adapter does not recognise objects]"
    )
    return {
        "families": fams,
        "objective": {
            "description": description,
            "subjects": [],
            "composition": composition,
            "lighting": {"quality": quality, "direction": stats.get("light_direction"), "key": key, "contrast": contrast},
            "colors": [{"hex": p["hex"], "name": p["name"], "proportion": p["proportion"]} for p in palette[:6]],
            "materials": [],
            "textures": textures,
            "geometry": geometry,
            "camera": {"perspective": None, "shot_type": None, "depth_of_field": None},
            "text_present": None,
        },
        "atmosphere": list(dict.fromkeys(atmosphere)),
        "style": style,
        "chroma_word": chroma_word,
        "temp_word": temp_word,
    }


def match_concepts(families: dict[str, float], concepts: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Score the brand's own vocabulary against descriptor families."""
    if not families:
        return []
    total = sum(families.values())
    scored = []
    for c in concepts:
        text = " ".join([c.get("name", ""), c.get("definition", ""), " ".join(c.get("synonyms", []) or [])])
        cf = lexicon.families_in(text)
        if not cf:
            continue
        overlap = sum(min(families.get(f, 0.0), 1.5) for f in cf)
        if overlap <= 0:
            continue
        conf = round(min(0.78, 0.3 + 0.45 * overlap / (total + 1.0)), 3)
        evidence = ", ".join(sorted(f for f in cf if f in families))
        scored.append({"name": c["name"], "confidence": conf, "evidence": f"measured descriptors: {evidence}"})
    scored.sort(key=lambda x: -x["confidence"])
    return scored[:limit]


def _applications(probe: dict[str, Any], neg: float) -> list[str]:
    o = probe.get("orientation")
    apps = {
        "landscape": ["website hero", "presentation background", "campaign banner"],
        "portrait": ["social stories / reels cover", "poster", "editorial full-page"],
        "square": ["social feed post", "product tile"],
    }.get(o, ["general reference"])
    if neg > 0.4:
        apps.append("layouts with text overlay")
    return apps


class DevVisionProvider:
    name = DEV_PROVIDER
    model = "dev-heuristic-vision-1"

    def analyze_images(self, images: list[ImageInput], prompt: str, context: dict[str, Any]) -> AiResult:
        t0 = time.perf_counter()
        img = images[0]
        d = describe_measurements(img.measurements)
        concepts = match_concepts(d["families"], context.get("concepts", []))
        probe = img.measurements.get("probe", {})
        stats = img.measurements.get("stats", {})
        tags = [c["name"] for c in d["objective"]["colors"][:3]] + d["atmosphere"][:3] + d["style"]
        tags += [stats.get("key", ""), probe.get("orientation", "")]
        summary = (
            f"{', '.join(d['atmosphere'][:3]).capitalize() or 'Neutral'} {d['chroma_word']} {d['temp_word']} "
            f"imagery{' with ' + ' and '.join(d['style']) + ' character' if d['style'] else ''}."
        )
        data = {
            "objective": d["objective"],
            "interpretive": {
                "summary": summary,
                "atmosphere": d["atmosphere"],
                "visual_style": d["style"],
                "photography_characteristics": [f"{d['objective']['lighting']['quality']} light", f"{stats.get('key', 'mid-key')} exposure"],
                "aesthetic_concepts": concepts,
                "brand_relevance": {
                    "assessment": "supporting" if concepts and concepts[0]["confidence"] >= 0.6 else "unassessed",
                    "rationale": "Heuristic match against the brand concept vocabulary; requires human review.",
                },
                "potential_applications": _applications(probe, stats.get("negative_space_ratio", 0)),
                "suggested_tags": sorted({t.lower() for t in tags if t}),
            },
            "confidence": 0.45,
        }
        return AiResult(data, self.name, self.model, int((time.perf_counter() - t0) * 1000), True)


# --- Text ----------------------------------------------------------------------------------------
_RULES = [
    ("prohibited", re.compile(r"\b(never|do not|don't|must not|mustn't|avoid|prohibited|forbidden|not allowed)\b|^no\s", re.I), 0.62),
    ("mandatory", re.compile(r"\b(must|always|required|shall|mandatory|is required to)\b", re.I), 0.6),
    ("experimental", re.compile(r"\b(experiment|explore|try out|test new)\b", re.I), 0.45),
    ("preferred", re.compile(r"\b(should|prefer|preferably|ideally|recommended|favou?r)\b", re.I), 0.5),
    ("optional", re.compile(r"\b(may|can optionally|optional(ly)?|is allowed to)\b", re.I), 0.4),
]
_CONTEXT = re.compile(r"^(when|if|for|in|on)\b", re.I)
_DOMAIN_HINTS = [
    ("visual_identity", r"\b(logo|colou?r|palette|typeface|font|type|icon|clear ?space|contrast ratio|wordmark)\b"),
    ("art_direction", r"\b(photo|photograph|lighting|light|image|imagery|composition|camera|shot|frame|film|video|render)\b"),
    ("design_language", r"\b(grid|layout|spacing|margin|component|button|motion|animation|ui|interface|scroll|responsive)\b"),
    ("brand_language", r"\b(tone|voice|copy|word|words|writing|headline|sentence|language|exclamation|jargon)\b"),
    ("brand_foundation", r"\b(mission|vision|value|values|purpose|promise|audience|positioning)\b"),
]


def _sentences(text: str) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+|\n+(?=[-•*\d]|\s*[A-Z])", text)
    out = []
    for p in parts:
        p = p.strip(" -•*\t")
        if 25 <= len(p) <= 400 and not p.isupper():
            out.append(p)
    return out


def extract_principles(pages: list[dict[str, Any]], limit: int = 25) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for page in pages:
        for s in _sentences(page.get("text", "")):
            for cls, rx, conf in _RULES:
                if rx.search(s):
                    if _CONTEXT.match(s) and cls in ("mandatory", "preferred"):
                        cls, conf = "context_dependent", 0.48
                    key = re.sub(r"\W+", " ", s.lower()).strip()[:120]
                    if key in seen:
                        break
                    seen.add(key)
                    domain = next((d for d, rx2 in _DOMAIN_HINTS if re.search(rx2, s, re.I)), "principles_guidelines")
                    title_words = re.sub(r"\b(always|never|must|should|do not|don't|avoid|we|our|you|please)\b", "", s, flags=re.I)
                    title_words = re.sub(r"\s+", " ", title_words).strip(" ,.:;")
                    title = " ".join(title_words.split()[:8]).rstrip(",.;:")
                    out.append(
                        {
                            "title": (title[:1].upper() + title[1:]) if title else s[:60],
                            "statement": s,
                            "classification": cls,
                            "rationale": None,
                            "domain_key": domain,
                            "source_page": page.get("number"),
                            "source_excerpt": s[:300],
                            "confidence": conf,
                        }
                    )
                    break
            if len(out) >= limit:
                return out
    return out


class DevTextProvider:
    name = DEV_PROVIDER
    model = "dev-heuristic-text-1"

    def complete_json(self, prompt: str, context: dict[str, Any]) -> AiResult:
        t0 = time.perf_counter()
        task = context.get("task")
        if task == "document_principles":
            pages = context.get("pages", [])
            full = "\n".join(p.get("text", "") for p in pages)
            fams = lexicon.families_in(full)
            concepts = match_concepts({k: float(v) for k, v in fams.items()}, context.get("concepts", []))
            first = next((s for s in _sentences(full)), "")
            data = {
                "interpretive": {
                    "summary": (context.get("title") or "Document") + (f": {first[:200]}" if first else ""),
                    "atmosphere": [],
                    "visual_style": sorted(fams, key=lambda f: -fams[f])[:5],
                    "aesthetic_concepts": concepts,
                    "brand_relevance": {"assessment": "unassessed", "rationale": None},
                    "potential_applications": [],
                    "suggested_tags": sorted(fams, key=lambda f: -fams[f])[:6],
                },
                "principle_candidates": extract_principles(pages),
                "confidence": 0.4,
            }
        elif task == "video_synthesis":
            data = _synthesize_video(context)
        else:
            data = {"note": "development text adapter has no generative capability for this task", "confidence": 0.0}
        return AiResult(data, self.name, self.model, int((time.perf_counter() - t0) * 1000), True)


def _synthesize_video(ctx: dict[str, Any]) -> dict[str, Any]:
    scenes_in = ctx.get("scenes", [])
    motion = ctx.get("motion", {})
    probe = ctx.get("probe", {})
    scenes = []
    fams: dict[str, float] = {}
    for sc in scenes_in:
        kf = sc.get("keyframe_analysis") or {}
        summ = (kf.get("interpretive") or {}).get("summary", "")
        desc = (kf.get("objective") or {}).get("description", "")
        scenes.append(
            {
                "index": sc["index"],
                "start_s": sc["start_s"],
                "end_s": sc["end_s"],
                "description": summ or desc[:200],
                "camera_movement": (sc.get("motion") or {}).get("camera_movement"),
                "shot_type": None,
            }
        )
        for f, v in (sc.get("families") or {}).items():
            fams[f] = fams.get(f, 0.0) + v
    pace = motion.get("pace", "unknown pace")
    if "contemplative" in pace or (motion.get("mean_motion", 1) < 0.35):
        fams["slow_motion"] = fams.get("slow_motion", 0) + 1.5
    if pace in ("energetic", "rapid-cut"):
        fams["fast_motion"] = fams.get("fast_motion", 0) + 1.5
    if motion.get("overall_camera_movement", "").startswith(("slow", "moderate")):
        fams["cinematic"] = fams.get("cinematic", 0) + 0.8
    concepts = match_concepts(fams, ctx.get("concepts", []))
    dur = probe.get("duration_seconds", 0)
    temporal = (
        f"{len(scenes)} scene(s) over {dur:.1f}s — {pace}; average shot {motion.get('average_shot_length_s', dur)}s. "
        f"Overall camera: {motion.get('overall_camera_movement', 'n/a')}. "
        + " → ".join(f"[{s['start_s']:.1f}s] {s['description'][:80]}" for s in scenes[:6])
    )
    atmos = sorted({a for sc in scenes_in for a in ((sc.get("keyframe_analysis") or {}).get("interpretive") or {}).get("atmosphere", [])})
    return {
        "temporal_description": temporal,
        "scenes": scenes,
        "interpretive": {
            "summary": f"{pace.capitalize()} footage; {motion.get('overall_camera_movement', 'camera n/a')}.",
            "atmosphere": atmos[:6],
            "visual_style": sorted(fams, key=lambda f: -fams[f])[:4],
            "photography_characteristics": [f"camera: {motion.get('overall_camera_movement', 'n/a')}", f"pace: {pace}"],
            "aesthetic_concepts": concepts,
            "brand_relevance": {"assessment": "unassessed", "rationale": None},
            "potential_applications": ["website background video", "social cut-downs"] if dur and dur < 60 else ["brand film"],
            "suggested_tags": sorted({pace.split(" ")[0], *atmos[:3]}),
        },
        "confidence": 0.42,
    }


# --- Embeddings ----------------------------------------------------------------------------------
def _hash_index(token: str, dims: int) -> tuple[int, float]:
    h = hashlib.blake2b(token.encode(), digest_size=8).digest()
    v = int.from_bytes(h, "little")
    return v % dims, 1.0 if (v >> 63) & 1 else -1.0


class DevTextEmbedder:
    name = DEV_PROVIDER
    model = "dev-hash-text-384"
    dimensions = 384
    modality = "text"
    is_development_adapter = True

    def embed(self, inputs: list[str]) -> list[list[float]]:
        return [self._one(t or "") for t in inputs]

    def _one(self, text: str) -> list[float]:
        vec = np.zeros(self.dimensions, dtype=np.float64)
        toks = lexicon.tokens(text)
        feats: dict[str, float] = {}
        for t in toks:
            feats[f"w:{t}"] = feats.get(f"w:{t}", 0) + 1
            if len(t) >= 5:
                for i in range(len(t) - 2):
                    g = f"c:{t[i:i+3]}"
                    feats[g] = feats.get(g, 0) + 0.25
        for a, b in zip(toks, toks[1:], strict=False):
            feats[f"b:{a}_{b}"] = feats.get(f"b:{a}_{b}", 0) + 1
        for fam, n in lexicon.families_in(text).items():
            feats[f"f:{fam}"] = feats.get(f"f:{fam}", 0) + 2.5 * n
        for f, tf in feats.items():
            i, s = _hash_index(f, self.dimensions)
            vec[i] += s * (1 + math.log(tf)) if tf >= 1 else s * tf
        n = np.linalg.norm(vec)
        return (vec / n).round(6).tolist() if n else vec.tolist()


class DevVisualEmbedder:
    name = DEV_PROVIDER
    model = "dev-visual-descriptor-256"
    dimensions = 256
    modality = "visual"
    is_development_adapter = True

    def embed(self, inputs: list[Path]) -> list[list[float]]:
        return [self._one(Path(p)) for p in inputs]

    def _one(self, path: Path) -> list[float]:
        from app.media.image import open_image, to_rgb

        rgb = np.asarray(to_rgb(open_image(path), 256))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        feats = []
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 3, 3], [0, 180, 0, 256, 0, 256]).flatten()
        feats.append(np.sqrt(hist / (hist.sum() + 1e-9)) * 1.0)  # 72: colour distribution
        lab = cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
        small = cv2.resize(lab, (4, 4), interpolation=cv2.INTER_AREA).reshape(-1)
        feats.append(small / np.array([100.0, 128.0, 128.0] * 16) * 0.9)  # 48: colour layout
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        g8 = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA).astype(np.float32).reshape(-1)
        feats.append((g8 - g8.mean()) / (g8.std() + 1e-6) * 0.12)  # 64: luminance layout / composition
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
        mag, ang = cv2.cartToPolar(gx, gy, angleInDegrees=True)
        h, w = gray.shape
        quads = []
        for qy in (slice(0, h // 2), slice(h // 2, h)):
            for qx in (slice(0, w // 2), slice(w // 2, w)):
                hq, _ = np.histogram(ang[qy, qx] % 180, bins=8, range=(0, 180), weights=mag[qy, qx])
                quads.append(np.sqrt(hq / (hq.sum() + 1e-9)))
        feats.append(np.concatenate(quads) * 0.6)  # 32: edge orientation per quadrant
        lap = cv2.Laplacian(gray, cv2.CV_32F)
        tex, _ = np.histogram(np.abs(lap), bins=16, range=(0, 64))
        feats.append(np.sqrt(tex / (tex.sum() + 1e-9)) * 0.5)  # 16: texture energy
        v = np.concatenate(feats)
        v = np.pad(v, (0, self.dimensions - len(v)))[: self.dimensions]
        n = np.linalg.norm(v)
        return (v / n).round(6).tolist() if n else v.tolist()
