"""Deterministic natural-language query understanding.

Turns "Find approved videos with slow cinematic camera movements" into structured intent:
entity/asset-type hints, approval scope, reference-role hints, measurable visual attributes
(muted, dramatic lighting, slow camera…) and leftover free text for keyword/semantic retrieval.
Concept names are matched later against the brand's own vocabulary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_ASSET_TYPE_WORDS = {
    r"\b(images?|photos?|photographs?|pictures?|stills?|imagery)\b": ["image", "photograph"],
    r"\b(videos?|films?|footage|clips?|motion pieces?)\b": ["video", "animation"],
    r"\b(documents?|pdfs?|decks?|presentations?|guidebooks?)\b": ["document", "presentation"],
    r"\b(3d|renders?|models?)\b": ["render_3d", "model_3d"],
    r"\b(logos?|wordmarks?)\b": ["logo"],
    r"\b(illustrations?|drawings?|sketches?)\b": ["illustration", "sketch"],
    r"\b(moodboards?)\b": ["moodboard"],
}
_ENTITY_WORDS = {
    r"\b(guidelines?|guides?)\b": "guideline",
    r"\b(principles?|rules?)\b": "principle",
    r"\b(aesthetic )?concepts?\b": "aesthetic_concept",
    r"\b(projects?)\b": "project",
    r"\b(collections?)\b": "collection",
}
# measurable attributes -> (metadata path, comparator, threshold)
_ATTRIBUTES = {
    r"\bmuted|desaturated|subdued|understated\b": ("image_stats.colorfulness", "<", 0.3, "muted palette"),
    r"\bvibrant|saturated|vivid|bold colou?rs?\b": ("image_stats.colorfulness", ">", 0.5, "vibrant palette"),
    r"\bdramatic light(ing)?|high[- ]contrast|chiaroscuro|hard light\b": ("image_stats.contrast", ">", 0.55, "high contrast"),
    r"\bsoft light(ing)?|low[- ]contrast|diffused\b": ("image_stats.contrast", "<", 0.35, "low contrast"),
    r"\b(dark|low[- ]key|moody|nocturnal)\b": ("image_stats.brightness", "<", 0.4, "low-key"),
    r"\b(bright|airy|high[- ]key|luminous)\b": ("image_stats.brightness", ">", 0.6, "high-key"),
    r"\bwarm\b": ("image_stats.warmth", ">", 0.15, "warm"),
    r"\bcool|cold|icy\b": ("image_stats.warmth", "<", -0.05, "cool"),
    r"\b(negative space|minimal|sparse|whitespace)\b": ("image_stats.negative_space_ratio", ">", 0.4, "negative space"),
    r"\bslow\b.*\b(camera|movement|motion|pan|pace)|\b(contemplative|long takes?|lingering)\b": ("motion.mean_motion", "<", 0.45, "slow motion"),
    r"\b(fast|rapid|kinetic|energetic)\b.*\b(camera|movement|motion|cuts?|pace)?": ("motion.mean_motion", ">", 0.6, "fast motion"),
    r"\bportrait\b": ("orientation", "=", "portrait", "portrait"),
    r"\blandscape|widescreen\b": ("orientation", "=", "landscape", "landscape"),
}
_PROJECT_TYPES = {
    r"\bwebsite design|web design|website\b": "website_design",
    r"\bwebsite development|front[- ]?end|developers?\b": "website_development",
    r"\bsocial( media)?|instagram|tiktok\b": "social_media",
    r"\bpackaging\b": "packaging",
    r"\bcampaigns?\b": "branding_campaign",
    r"\bpresentations?|slides?\b": "presentation",
    r"\bvideo production|brand film\b": "video_production",
    r"\bproduct design\b": "product_design",
    r"\badvertising|ads?\b": "advertising",
}
_STOP = re.compile(
    r"\b(find|show|me|all|any|some|the|a|an|with|that|which|have|has|for|of|in|on|and|or|to|demonstrating|showing|"
    r"featuring|relevant|related|associated|examples?|references?|assets?|please|our|brand|items?|things?)\b",
    re.I,
)


@dataclass
class ParsedQuery:
    raw: str
    text: str
    asset_types: list[str] = field(default_factory=list)
    entity_types: list[str] = field(default_factory=list)
    approved_only: bool = False
    pending_only: bool = False
    reference_roles: list[str] = field(default_factory=list)
    attributes: list[tuple[str, str, object, str]] = field(default_factory=list)
    project_types: list[str] = field(default_factory=list)


def parse(q: str) -> ParsedQuery:
    raw = q.strip()
    low = raw.lower()
    p = ParsedQuery(raw=raw, text=raw)
    for rx, types in _ASSET_TYPE_WORDS.items():
        if re.search(rx, low):
            p.asset_types += types
    for rx, et in _ENTITY_WORDS.items():
        if re.search(rx, low):
            p.entity_types.append(et)
    if re.search(r"\b(approved|official|signed[- ]off)\b", low):
        p.approved_only = True
    if re.search(r"\b(pending|unreviewed|awaiting review)\b", low):
        p.pending_only = True
    for role in ("inspiration", "historical", "external"):
        if role in low:
            p.reference_roles.append(role)
    for rx, attr in _ATTRIBUTES.items():
        if re.search(rx, low):
            p.attributes.append(attr)
    for rx, pt in _PROJECT_TYPES.items():
        if re.search(rx, low):
            p.project_types.append(pt)
    t = re.sub(r"\b(approved|official|pending|unreviewed)\b", " ", raw, flags=re.I)
    for rx in list(_ASSET_TYPE_WORDS) + list(_ENTITY_WORDS):
        t = re.sub(rx, " ", t, flags=re.I)
    t = _STOP.sub(" ", t)
    p.text = re.sub(r"\s+", " ", t).strip() or raw
    return p


def or_query(text: str) -> str:
    """websearch_to_tsquery syntax with OR between terms (ranking rewards documents matching more)."""
    words = [w for w in re.findall(r"[\w'-]+", text) if len(w) > 1]
    return " or ".join(words)
