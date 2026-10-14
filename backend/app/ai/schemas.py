"""Versioned output schemas for AI analyses. Every provider's output is validated against these
before it is stored; violations are recorded on the analysis (``validation_errors``)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ANALYSIS_SCHEMA_VERSION = 1


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="allow")


class ColorObs(_Lenient):
    hex: str
    name: str | None = None
    proportion: float | None = None


class Composition(_Lenient):
    framing: str | None = None
    layout: str | None = None
    focal_point: str | None = None
    symmetry: str | None = None
    negative_space: str | None = None


class Lighting(_Lenient):
    quality: str | None = None
    direction: str | None = None
    key: str | None = None
    contrast: str | None = None


class Camera(_Lenient):
    perspective: str | None = None
    shot_type: str | None = None
    depth_of_field: str | None = None


class ObjectiveObservation(_Lenient):
    """What is verifiably in the image — no taste judgements."""

    description: str = ""
    subjects: list[str] = Field(default_factory=list)
    composition: Composition = Field(default_factory=Composition)
    lighting: Lighting = Field(default_factory=Lighting)
    colors: list[ColorObs] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    textures: list[str] = Field(default_factory=list)
    geometry: list[str] = Field(default_factory=list)
    camera: Camera = Field(default_factory=Camera)
    text_present: str | None = None


class ConceptMatch(_Lenient):
    name: str
    confidence: float = Field(0.5, ge=0, le=1)
    evidence: str | None = None


class BrandRelevance(_Lenient):
    assessment: Literal["core", "supporting", "peripheral", "off_brand", "unassessed"] = "unassessed"
    rationale: str | None = None


class Interpretation(_Lenient):
    """Subjective aesthetic reading — always a proposal for human review."""

    summary: str = ""
    atmosphere: list[str] = Field(default_factory=list)
    visual_style: list[str] = Field(default_factory=list)
    photography_characteristics: list[str] = Field(default_factory=list)
    aesthetic_concepts: list[ConceptMatch] = Field(default_factory=list)
    brand_relevance: BrandRelevance = Field(default_factory=BrandRelevance)
    potential_applications: list[str] = Field(default_factory=list)
    suggested_tags: list[str] = Field(default_factory=list)


class ImageAnalysisOutput(_Lenient):
    objective: ObjectiveObservation = Field(default_factory=ObjectiveObservation)
    interpretive: Interpretation = Field(default_factory=Interpretation)
    confidence: float = Field(0.5, ge=0, le=1)


class SceneObs(_Lenient):
    index: int
    start_s: float
    end_s: float
    description: str = ""
    camera_movement: str | None = None
    shot_type: str | None = None


class VideoAnalysisOutput(_Lenient):
    objective: dict[str, Any] = Field(default_factory=dict)  # scenes, pacing, camera movement, palette
    interpretive: Interpretation = Field(default_factory=Interpretation)
    scenes: list[SceneObs] = Field(default_factory=list)
    temporal_description: str = ""
    confidence: float = Field(0.5, ge=0, le=1)


class PrincipleCandidate(_Lenient):
    title: str
    statement: str
    classification: Literal["mandatory", "preferred", "optional", "prohibited", "context_dependent", "experimental"]
    rationale: str | None = None
    domain_key: str | None = None
    source_page: int | None = None
    source_excerpt: str | None = None
    confidence: float = Field(0.5, ge=0, le=1)


class DocumentAnalysisOutput(_Lenient):
    objective: dict[str, Any] = Field(default_factory=dict)  # structure, headings, metadata
    interpretive: Interpretation = Field(default_factory=Interpretation)
    principle_candidates: list[PrincipleCandidate] = Field(default_factory=list)
    confidence: float = Field(0.5, ge=0, le=1)


def validate(model: type[BaseModel], data: dict[str, Any]) -> tuple[BaseModel, list[dict[str, Any]]]:
    """Validate; on failure keep what validates and report errors (never crash ingestion)."""
    try:
        return model.model_validate(data), []
    except ValidationError as e:
        errors = [{"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()]
        cleaned = dict(data)
        for err in e.errors():
            if err["loc"]:
                top = err["loc"][0]
                cleaned.pop(top, None)
        try:
            return model.model_validate(cleaned), errors
        except ValidationError:
            return model(), errors
