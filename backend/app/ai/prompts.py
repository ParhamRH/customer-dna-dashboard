"""Versioned prompt templates. Platform defaults live here and are synced into
``prompt_templates`` (organization_id NULL) at start-up; customers can override a key with their
own higher-priority version. Every analysis records the prompt key + version it used."""
from __future__ import annotations

import string
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import system_session
from app.models import PromptTemplate


@dataclass(frozen=True)
class Prompt:
    key: str
    version: int
    template: str
    organization_id: str | None = None

    def render(self, **kw: object) -> str:
        return string.Template(self.template).safe_substitute({k: str(v) for k, v in kw.items()})


IMAGE_ANALYSIS_V1 = """You are a senior art director cataloguing creative references for the brand "$brand_name".
Brand context (approved knowledge, may be empty):
$brand_context

Known aesthetic concepts in this brand's controlled vocabulary (prefer these names when they apply):
$concept_vocabulary

Objective measurements computed from the pixels (trust these for colors / tonal values):
$measurements

Analyse the image(s). Separate OBJECTIVE observation (what is verifiably there) from INTERPRETATION
(aesthetic reading). Do not invent brand rules. Respond with ONLY a JSON object of this shape:
{
  "objective": {
    "description": "literal description of what is depicted",
    "subjects": [], "materials": [], "textures": [], "geometry": [],
    "composition": {"framing": "", "layout": "", "focal_point": "", "symmetry": "", "negative_space": ""},
    "lighting": {"quality": "", "direction": "", "key": "", "contrast": ""},
    "camera": {"perspective": "", "shot_type": "", "depth_of_field": ""},
    "colors": [{"hex": "#rrggbb", "name": "", "proportion": 0.0}],
    "text_present": null
  },
  "interpretive": {
    "summary": "one or two sentences",
    "atmosphere": [], "visual_style": [], "photography_characteristics": [],
    "aesthetic_concepts": [{"name": "", "confidence": 0.0, "evidence": ""}],
    "brand_relevance": {"assessment": "core|supporting|peripheral|off_brand|unassessed", "rationale": ""},
    "potential_applications": [], "suggested_tags": []
  },
  "confidence": 0.0
}"""

VIDEO_SYNTHESIS_V1 = """You are a senior film director and art director cataloguing a video reference for "$brand_name".
Scene-level observations (keyframe analyses and measured camera motion):
$scene_observations

Measured, objective technical data:
$measurements

Known aesthetic concepts: $concept_vocabulary

Write a temporal description of the video. Keep measured facts (durations, camera movement, pace) as
given. Respond with ONLY JSON:
{"temporal_description": "", "scenes": [{"index": 0, "start_s": 0, "end_s": 0, "description": "", "camera_movement": "", "shot_type": ""}],
 "interpretive": {"summary": "", "atmosphere": [], "visual_style": [], "photography_characteristics": [],
   "aesthetic_concepts": [{"name": "", "confidence": 0.0, "evidence": ""}],
   "brand_relevance": {"assessment": "unassessed", "rationale": ""}, "potential_applications": [], "suggested_tags": []},
 "confidence": 0.0}"""

DOCUMENT_PRINCIPLES_V1 = """You are a brand strategist extracting candidate creative principles from a brand document
for "$brand_name". The candidates will be REVIEWED BY HUMANS before becoming official; quote the source.

Document title: $title
Headings: $headings
Text (may be truncated):
$text

Respond with ONLY JSON:
{"interpretive": {"summary": "", "atmosphere": [], "visual_style": [], "aesthetic_concepts": [{"name": "", "confidence": 0.0, "evidence": ""}],
   "brand_relevance": {"assessment": "unassessed", "rationale": ""}, "potential_applications": [], "suggested_tags": []},
 "principle_candidates": [{"title": "", "statement": "", "classification": "mandatory|preferred|optional|prohibited|context_dependent|experimental",
   "rationale": "", "domain_key": "visual_identity|art_direction|design_language|brand_language|brand_foundation|principles_guidelines",
   "source_page": 1, "source_excerpt": "", "confidence": 0.0}],
 "confidence": 0.0}"""

CONTEXT_TASK_V1 = """You are briefing an AI system that will produce: $task_label ($output_medium).
Work strictly within the brand knowledge below. Mandatory rules are non-negotiable; prohibited directions
must never appear. When the brief and the brand rules conflict, follow the brand rules and say so.
Cite source identifiers (e.g. [P-003], [asset:…]) when you rely on a specific rule or reference."""

DEFAULTS: list[tuple[str, str, str, int, str]] = [
    ("image_analysis", "Image analysis", "analysis", 1, IMAGE_ANALYSIS_V1),
    ("video_synthesis", "Video temporal synthesis", "analysis", 1, VIDEO_SYNTHESIS_V1),
    ("document_principles", "Document principle extraction", "suggestion", 1, DOCUMENT_PRINCIPLES_V1),
    ("context_task_preamble", "Context package task preamble", "context", 1, CONTEXT_TASK_V1),
]


def ensure_default_prompts() -> None:
    with system_session() as s:
        for key, name, purpose, version, template in DEFAULTS:
            exists = s.scalar(
                select(PromptTemplate.id).where(
                    PromptTemplate.organization_id.is_(None), PromptTemplate.key == key, PromptTemplate.version == version
                )
            )
            if not exists:
                s.add(PromptTemplate(organization_id=None, key=key, name=name, purpose=purpose, version=version, template=template))


def get_prompt(db: Session, key: str) -> Prompt:
    """Active prompt for the current tenant: its own override first, else the platform default."""
    rows = db.scalars(
        select(PromptTemplate)
        .where(PromptTemplate.key == key, PromptTemplate.is_active.is_(True))
        .order_by(PromptTemplate.organization_id.is_(None), PromptTemplate.version.desc())
    ).all()
    if rows:
        r = rows[0]
        return Prompt(r.key, r.version, r.template, str(r.organization_id) if r.organization_id else None)
    for k, _, _, v, t in DEFAULTS:
        if k == key:
            return Prompt(k, v, t)
    raise KeyError(key)
