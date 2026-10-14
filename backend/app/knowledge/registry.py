"""Knowledge entry types per domain (code-defined, so new types need no migration).

Each type declares optional structured fields. ``kind``: text | list (of strings) | records
(list of objects with the listed ``fields``) | object. Art-direction types separate objective
observations from subjective interpretation, as required for Domain 03.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import update

from app.db.session import system_session
from app.models import KnowledgeDomain


def F(key: str, label: str, kind: str = "text", fields: list[str] | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"key": key, "label": label, "kind": kind}
    if fields:
        d["fields"] = fields
    return d


_ART = [F("objective_observations", "Objective observations", "list"), F("aesthetic_interpretation", "Aesthetic interpretation"),
        F("do", "Do", "list"), F("dont", "Don't", "list")]

ENTRY_TYPES: dict[str, dict[str, dict[str, Any]]] = {
    "brand_foundation": {
        "philosophy": {"label": "Brand philosophy", "fields": []},
        "mission": {"label": "Mission", "fields": []},
        "vision": {"label": "Vision", "fields": []},
        "story": {"label": "Brand story", "fields": []},
        "positioning": {"label": "Positioning", "fields": [F("statement", "Positioning statement"), F("category", "Category"), F("competitors", "Competitive set", "list")]},
        "personality": {"label": "Personality", "fields": [F("traits", "Traits", "records", ["trait", "is", "is_not"])]},
        "archetype": {"label": "Archetypes", "fields": [F("primary", "Primary archetype"), F("secondary", "Secondary archetype")]},
        "core_values": {"label": "Core values", "fields": [F("values", "Values", "records", ["name", "description"])]},
        "target_audience": {"label": "Target audience", "fields": [F("segments", "Segments", "records", ["name", "description", "needs"])]},
        "promise": {"label": "Brand promise", "fields": []},
        "differentiation": {"label": "Differentiation", "fields": [F("differentiators", "Differentiators", "list")]},
        "attributes": {"label": "Brand attributes", "fields": [F("attributes", "Attributes", "list")]},
    },
    "visual_identity": {
        "logo_usage": {"label": "Logo usage rules", "fields": [F("clear_space", "Clear space"), F("minimum_size", "Minimum size"), F("do", "Do", "list"), F("dont", "Don't", "list")]},
        "color_usage": {"label": "Color usage", "fields": [F("ratios", "Usage ratios")]},
        "typography_usage": {"label": "Typography usage", "fields": []},
        "iconography": {"label": "Iconography", "fields": [F("style", "Style"), F("stroke", "Stroke"), F("grid", "Grid")]},
        "graphic_elements": {"label": "Graphic elements", "fields": []},
        "patterns": {"label": "Patterns", "fields": []},
        "shapes": {"label": "Shapes", "fields": []},
        "grid_system": {"label": "Grid system", "fields": [F("columns", "Columns"), F("gutter", "Gutter"), F("margins", "Margins")]},
        "composition_rules": {"label": "Composition rules", "fields": [F("rules", "Rules", "list")]},
        "accessibility": {"label": "Accessibility & contrast", "fields": [F("minimum_contrast", "Minimum contrast"), F("rules", "Rules", "list")]},
    },
    "art_direction": {k: {"label": v, "fields": _ART} for k, v in {
        "photography_direction": "Photography direction", "lighting": "Lighting characteristics", "composition": "Composition",
        "framing": "Framing", "camera_perspective": "Camera perspectives", "materials": "Materials", "textures": "Textures",
        "geometry": "Geometry", "spatial": "Spatial characteristics", "atmosphere": "Atmosphere", "color_behavior": "Color behavior",
        "motion": "Motion", "visual_storytelling": "Visual storytelling", "rendering_style": "Rendering style",
        "image_treatment": "Image treatments",
    }.items()},
    "aesthetic_language": {
        "ontology_overview": {"label": "Ontology overview", "fields": []},
        "concept_family": {"label": "Concept family", "fields": [F("concepts", "Concepts", "list")]},
    },
    "design_language": {k: {"label": v, "fields": [F("rules", "Rules", "list"), F("values", "Values / tokens", "object")]} for k, v in {
        "layout_principles": "Layout principles", "grid_system": "Grid system", "spacing": "Spacing", "proportions": "Proportions",
        "visual_hierarchy": "Visual hierarchy", "component_spec": "Component specification", "navigation_patterns": "Navigation patterns",
        "interaction_principles": "Interaction principles", "animation_motion": "Animation & motion", "scroll_behavior": "Scroll behavior",
        "responsive_behavior": "Responsive behavior", "design_conventions": "Design conventions",
    }.items()},
    "brand_language": {
        "tone_of_voice": {"label": "Tone of voice", "fields": [F("traits", "Traits", "records", ["trait", "is", "is_not"])]},
        "brand_voice": {"label": "Brand voice", "fields": []},
        "vocabulary": {"label": "Vocabulary", "fields": [F("terms", "Terms", "records", ["term", "meaning"])]},
        "preferred_expressions": {"label": "Preferred expressions", "fields": [F("expressions", "Expressions", "list")]},
        "restricted_expressions": {"label": "Restricted expressions", "fields": [F("expressions", "Expressions", "records", ["term", "use_instead", "reason"])]},
        "writing_style": {"label": "Writing style", "fields": [F("rules", "Rules", "list")]},
        "sentence_structure": {"label": "Sentence structure", "fields": [F("rules", "Rules", "list")]},
        "storytelling": {"label": "Storytelling principles", "fields": [F("principles", "Principles", "list")]},
        "copywriting_guidelines": {"label": "Copywriting guidelines", "fields": [F("rules", "Rules", "list")]},
        "audience_communication": {"label": "Audience-specific communication", "fields": [F("audiences", "Audiences", "records", ["audience", "guidance"])]},
        "approved_examples": {"label": "Approved writing examples", "fields": [F("examples", "Examples", "records", ["text", "context"])]},
        "incorrect_examples": {"label": "Incorrect writing examples", "fields": [F("examples", "Examples", "records", ["text", "why", "better"])]},
    },
    "creative_assets": {"asset_policy": {"label": "Asset policy", "fields": []}},
    "principles_guidelines": {"overview": {"label": "Principles overview", "fields": []}},
    "projects_applications": {"application_note": {"label": "Application note", "fields": []}},
    "ai_knowledge": {
        "retrieval_config": {"label": "Retrieval configuration", "fields": [F("settings", "Settings", "object")]},
        "evaluation_note": {"label": "Evaluation note", "fields": []},
        "model_configuration": {"label": "Model configuration note", "fields": []},
    },
}


def validate_structured(domain: str, entry_type: str, structured: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    spec = ENTRY_TYPES.get(domain, {}).get(entry_type)
    if spec is None:
        return [f"unknown entry_type {entry_type!r} for domain {domain!r}"]
    if not isinstance(structured, dict):
        return ["structured must be an object"]
    for f in spec["fields"]:
        v = structured.get(f["key"])
        if v is None:
            continue
        if f["kind"] == "text" and not isinstance(v, str):
            errors.append(f"{f['key']} must be text")
        elif f["kind"] == "list" and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            errors.append(f"{f['key']} must be a list of strings")
        elif f["kind"] == "records" and not (isinstance(v, list) and all(isinstance(x, dict) for x in v)):
            errors.append(f"{f['key']} must be a list of objects")
        elif f["kind"] == "object" and not isinstance(v, dict):
            errors.append(f"{f['key']} must be an object")
    return errors


def registry_payload() -> dict[str, Any]:
    return {d: [{"key": k, **v} for k, v in types.items()] for d, types in ENTRY_TYPES.items()}


def sync_domain_entry_types() -> None:
    with system_session() as s:
        for d, types in ENTRY_TYPES.items():
            s.execute(update(KnowledgeDomain).where(KnowledgeDomain.key == d).values(
                entry_types=[{"key": k, "label": v["label"]} for k, v in types.items()]
            ))
