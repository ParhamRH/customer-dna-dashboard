"""Resolve the AI providers for an organization.

Precedence: an active ``integrations`` row (kind ``ai_provider``) for the organization, whose
``config.capability`` is vision | text | embedding, then the platform defaults from the environment,
then the development adapter. The resolved provider/model is recorded on every analysis.
"""
from __future__ import annotations

import base64
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import ProviderError
from app.ai.dev import DevTextEmbedder, DevTextProvider, DevVisionProvider, DevVisualEmbedder
from app.ai.providers import AnthropicProvider, OpenAICompatibleProvider, OpenAIEmbedder
from app.config import get_settings
from app.models import Integration
from app.security.credentials import decrypt_secret


def _org_override(db: Session | None, capability: str) -> tuple[dict[str, Any], str] | None:
    if db is None:
        return None
    rows = db.scalars(
        select(Integration).where(Integration.kind == "ai_provider", Integration.status == "active")
    ).all()
    for r in rows:
        if (r.config or {}).get("capability") == capability:
            secret = decrypt_secret(r.secret_encrypted) if r.secret_encrypted else ""
            return r.config, secret
    return None


def _build_chat(provider: str, model: str | None, api_key: str, base_url: str | None):
    s = get_settings()
    if provider == "anthropic":
        return AnthropicProvider(api_key or s.anthropic_api_key, model or s.anthropic_model, base_url or s.anthropic_base_url)
    if provider in ("openai", "openai_compatible"):
        return OpenAICompatibleProvider(
            api_key or s.openai_api_key, model or s.openai_vision_model, base_url or s.openai_base_url, name=provider
        )
    return None


def vision_provider(db: Session | None = None):
    s = get_settings()
    o = _org_override(db, "vision")
    try:
        if o:
            cfg, key = o
            p = _build_chat(cfg.get("provider", "dev"), cfg.get("model"), key, cfg.get("base_url"))
            if p:
                return p
        if s.ai_vision_provider == "anthropic" and s.anthropic_api_key:
            return AnthropicProvider(s.anthropic_api_key, s.anthropic_model)
        if s.ai_vision_provider in ("openai", "openai_compatible"):
            return OpenAICompatibleProvider(s.openai_api_key, s.openai_vision_model, s.openai_base_url, name=s.ai_vision_provider)
    except ProviderError:
        pass
    return DevVisionProvider()


def text_provider(db: Session | None = None):
    s = get_settings()
    o = _org_override(db, "text")
    try:
        if o:
            cfg, key = o
            p = _build_chat(cfg.get("provider", "dev"), cfg.get("model"), key, cfg.get("base_url"))
            if p:
                return p
        if s.ai_text_provider == "anthropic" and s.anthropic_api_key:
            return AnthropicProvider(s.anthropic_api_key, s.anthropic_model)
        if s.ai_text_provider in ("openai", "openai_compatible"):
            return OpenAICompatibleProvider(s.openai_api_key, s.openai_text_model, s.openai_base_url, name=s.ai_text_provider)
    except ProviderError:
        pass
    return DevTextProvider()


def text_embedder(db: Session | None = None):
    """NOTE: search always embeds the query with the same model that indexed the content."""
    s = get_settings()
    o = _org_override(db, "embedding")
    if o:
        cfg, key = o
        if cfg.get("provider") in ("openai", "openai_compatible"):
            return OpenAIEmbedder(
                OpenAICompatibleProvider(
                    key or s.openai_api_key, cfg.get("model") or s.openai_text_model,
                    cfg.get("base_url") or s.openai_base_url, name=cfg["provider"],
                    embedding_model=cfg.get("model") or s.openai_embedding_model,
                    embedding_dimensions=cfg.get("dimensions") or s.openai_embedding_dimensions,
                )
            )
    if s.ai_embedding_provider in ("openai", "openai_compatible"):
        return OpenAIEmbedder(
            OpenAICompatibleProvider(
                s.openai_api_key, s.openai_text_model, s.openai_base_url, name=s.ai_embedding_provider,
                embedding_model=s.openai_embedding_model, embedding_dimensions=s.openai_embedding_dimensions,
            )
        )
    return DevTextEmbedder()


class HttpVisualEmbedder:
    """Adapter for a self-hosted image-embedding service (CLIP, SigLIP, …)."""

    name = "http-visual"
    modality = "visual"
    is_development_adapter = False

    def __init__(self, url: str, model: str, dimensions: int):
        self.url, self.model, self.dimensions = url, model, dimensions

    def embed(self, inputs: list[Path]) -> list[list[float]]:
        out = []
        for p in inputs:
            t0 = time.perf_counter()
            r = httpx.post(self.url, json={"image_base64": base64.b64encode(Path(p).read_bytes()).decode()}, timeout=60)
            if r.status_code >= 400:
                raise ProviderError(f"visual embedding service error {r.status_code}")
            vec = r.json()["embedding"]
            if len(vec) != self.dimensions:
                raise ProviderError(f"visual embedding has {len(vec)} dims, expected {self.dimensions}")
            out.append(vec)
            _ = t0
        return out


def visual_embedder(db: Session | None = None):
    s = get_settings()
    if s.ai_visual_embedding_provider == "http" and s.visual_embedding_url:
        return HttpVisualEmbedder(s.visual_embedding_url, s.visual_embedding_model, s.visual_embedding_dimensions)
    return DevVisualEmbedder()


def describe(db: Session | None = None) -> dict[str, Any]:
    """Human-readable summary for the settings page."""
    v, t, te, ve = vision_provider(db), text_provider(db), text_embedder(db), visual_embedder(db)
    def info(p) -> dict[str, Any]:  # noqa: ANN001
        return {
            "provider": p.name,
            "model": getattr(p, "model", None),
            "dimensions": getattr(p, "dimensions", None),
            "development_adapter": p.name == "dev-heuristic",
        }
    return {"vision": info(v), "text": info(t), "text_embedding": info(te), "visual_embedding": info(ve)}


_ = uuid
