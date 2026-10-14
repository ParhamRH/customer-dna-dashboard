"""Provider-independent AI interfaces.

The platform depends only on these protocols. Concrete adapters: ``dev`` (offline, deterministic,
clearly labelled development adapter), ``anthropic`` (Claude Messages API), ``openai`` /
``openai_compatible`` (OpenAI, Azure-compatible gateways, Ollama, vLLM, LM Studio …).
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ImageInput:
    path: Path
    mime: str = "image/jpeg"
    label: str | None = None  # e.g. "keyframe 3 @ 12.4s", "page 2"
    measurements: dict[str, Any] = field(default_factory=dict)  # objective stats for this image

    def b64(self) -> str:
        return base64.b64encode(self.path.read_bytes()).decode()


@dataclass
class AiResult:
    data: dict[str, Any]
    provider: str
    model: str
    latency_ms: int
    is_development_adapter: bool = False
    usage: dict[str, Any] = field(default_factory=dict)
    raw_text: str | None = None


class VisionProvider(Protocol):
    name: str
    model: str

    def analyze_images(self, images: list[ImageInput], prompt: str, context: dict[str, Any]) -> AiResult: ...


class TextProvider(Protocol):
    name: str
    model: str

    def complete_json(self, prompt: str, context: dict[str, Any]) -> AiResult: ...


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int
    modality: str  # "text" | "visual"
    is_development_adapter: bool

    def embed(self, inputs: list[Any]) -> list[list[float]]: ...


class OcrProvider(Protocol):
    name: str

    def ocr(self, png: bytes, lang: str = "eng") -> str: ...


class ProviderError(RuntimeError):
    pass


def parse_json_response(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a model response (handles ```json fences / prose)."""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    if fence:
        t = fence.group(1)
    else:
        start, end = t.find("{"), t.rfind("}")
        if start == -1 or end == -1:
            raise ProviderError("model did not return JSON")
        t = t[start : end + 1]
    try:
        data = json.loads(t)
    except json.JSONDecodeError as e:
        raise ProviderError(f"invalid JSON from model: {e}") from e
    if not isinstance(data, dict):
        raise ProviderError("model JSON is not an object")
    return data
