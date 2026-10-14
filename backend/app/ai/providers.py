"""Production AI adapters over plain HTTP (no vendor SDK lock-in).

AnthropicProvider        Claude Messages API — vision + text.
OpenAICompatibleProvider Chat Completions + Embeddings — OpenAI, or any compatible server
                         (Ollama, vLLM, LM Studio, LiteLLM gateways…) via base_url.
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.ai.base import AiResult, ImageInput, ProviderError, parse_json_response
from app.config import get_settings

SYSTEM_JSON = (
    "You are a meticulous creative-intelligence analyst. Always answer with a single valid JSON object "
    "and nothing else. Separate objective observation from interpretation. Never present guesses as facts."
)


def _context_text(context: dict[str, Any]) -> str:
    extra = {k: v for k, v in context.items() if k in ("measurements",) and v}
    return f"\n\nAdditional machine measurements (JSON):\n{json.dumps(extra, default=str)[:6000]}" if extra else ""


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, base_url: str | None = None, timeout: float | None = None):
        if not api_key:
            raise ProviderError("Anthropic API key missing")
        self.api_key, self.model = api_key, model
        self.base_url = (base_url or get_settings().anthropic_base_url).rstrip("/")
        self.timeout = timeout or get_settings().ai_request_timeout_seconds

    def _call(self, content: list[dict[str, Any]], max_tokens: int = 4000) -> tuple[str, dict[str, Any], int]:
        t0 = time.perf_counter()
        try:
            r = httpx.post(
                f"{self.base_url}/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "system": SYSTEM_JSON,
                    "messages": [{"role": "user", "content": content}],
                },
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise ProviderError(f"Anthropic request failed: {e}") from e
        if r.status_code >= 400:
            raise ProviderError(f"Anthropic API error {r.status_code}: {r.text[:500]}")
        body = r.json()
        text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
        return text, body.get("usage", {}), int((time.perf_counter() - t0) * 1000)

    def analyze_images(self, images: list[ImageInput], prompt: str, context: dict[str, Any]) -> AiResult:
        content: list[dict[str, Any]] = []
        for img in images[:8]:
            if img.label:
                content.append({"type": "text", "text": f"[{img.label}]"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": img.mime, "data": img.b64()}})
        content.append({"type": "text", "text": prompt + _context_text(context)})
        text, usage, ms = self._call(content)
        return AiResult(parse_json_response(text), self.name, self.model, ms, False, usage, text)

    def complete_json(self, prompt: str, context: dict[str, Any]) -> AiResult:
        text, usage, ms = self._call([{"type": "text", "text": prompt}])
        return AiResult(parse_json_response(text), self.name, self.model, ms, False, usage, text)


class OpenAICompatibleProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        name: str = "openai",
        embedding_model: str | None = None,
        embedding_dimensions: int | None = None,
        timeout: float | None = None,
    ):
        self.api_key, self.model, self.name = api_key, model, name
        self.base_url = base_url.rstrip("/")
        self.embedding_model = embedding_model
        self.timeout = timeout or get_settings().ai_request_timeout_seconds
        self.dimensions = embedding_dimensions or 0
        self.modality = "text"
        self.is_development_adapter = False

    def _headers(self) -> dict[str, str]:
        h = {"content-type": "application/json"}
        if self.api_key:
            h["authorization"] = f"Bearer {self.api_key}"
        return h

    def _chat(self, messages: list[dict[str, Any]]) -> tuple[str, dict[str, Any], int]:
        t0 = time.perf_counter()
        try:
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json={"model": self.model, "messages": messages, "response_format": {"type": "json_object"}, "temperature": 0.2},
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name} request failed: {e}") from e
        if r.status_code >= 400:
            raise ProviderError(f"{self.name} API error {r.status_code}: {r.text[:500]}")
        body = r.json()
        return body["choices"][0]["message"]["content"] or "", body.get("usage", {}), int((time.perf_counter() - t0) * 1000)

    def analyze_images(self, images: list[ImageInput], prompt: str, context: dict[str, Any]) -> AiResult:
        parts: list[dict[str, Any]] = []
        for img in images[:8]:
            if img.label:
                parts.append({"type": "text", "text": f"[{img.label}]"})
            parts.append({"type": "image_url", "image_url": {"url": f"data:{img.mime};base64,{img.b64()}"}})
        parts.append({"type": "text", "text": prompt + _context_text(context)})
        text, usage, ms = self._chat([{"role": "system", "content": SYSTEM_JSON}, {"role": "user", "content": parts}])
        return AiResult(parse_json_response(text), self.name, self.model, ms, False, usage, text)

    def complete_json(self, prompt: str, context: dict[str, Any]) -> AiResult:
        text, usage, ms = self._chat([{"role": "system", "content": SYSTEM_JSON}, {"role": "user", "content": prompt}])
        return AiResult(parse_json_response(text), self.name, self.model, ms, False, usage, text)

    def embed(self, inputs: list[str]) -> list[list[float]]:
        if not self.embedding_model:
            raise ProviderError("no embedding model configured")
        payload: dict[str, Any] = {"model": self.embedding_model, "input": [i[:24000] for i in inputs]}
        if self.dimensions:
            payload["dimensions"] = self.dimensions
        try:
            r = httpx.post(f"{self.base_url}/embeddings", headers=self._headers(), json=payload, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name} embeddings failed: {e}") from e
        if r.status_code >= 400:
            raise ProviderError(f"{self.name} embeddings error {r.status_code}: {r.text[:500]}")
        data = sorted(r.json()["data"], key=lambda d: d["index"])
        vecs = [d["embedding"] for d in data]
        if vecs and not self.dimensions:
            self.dimensions = len(vecs[0])
        return vecs


class OpenAIEmbedder:
    """Embedding-only facade exposing the EmbeddingProvider protocol."""

    modality = "text"
    is_development_adapter = False

    def __init__(self, inner: OpenAICompatibleProvider):
        self.inner = inner
        self.name = inner.name
        self.model = inner.embedding_model or "unknown"
        self.dimensions = inner.dimensions

    def embed(self, inputs: list[str]) -> list[list[float]]:
        vecs = self.inner.embed(inputs)
        self.dimensions = self.inner.dimensions
        return vecs
