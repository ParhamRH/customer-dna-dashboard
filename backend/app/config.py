"""Runtime configuration. Every value comes from the environment (see .env.example)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_prefix="BDNA_", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    secret_key: str = Field("dev-insecure-secret-change-me", min_length=16)
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt integration secrets at rest.
    # When empty, a key is derived from secret_key (acceptable for development only).
    encryption_key: str = ""

    # --- Database: three separate roles (see docs/adr/0002-tenant-isolation.md)
    # owner  -> migrations only (owns schema objects)
    # app    -> every tenant-scoped request; Row Level Security is enforced
    # system -> BYPASSRLS; used only by narrowly scoped platform functions
    database_owner_url: str = "postgresql+psycopg://bdna_owner:bdna_owner@localhost:5432/bdna"
    database_app_url: str = "postgresql+psycopg://bdna_app:bdna_app@localhost:5432/bdna"
    database_system_url: str = "postgresql+psycopg://bdna_system:bdna_system@localhost:5432/bdna"
    db_app_role: str = "bdna_app"
    db_system_role: str = "bdna_system"
    db_pool_size: int = 10

    # --- Auth
    session_ttl_hours: int = 24 * 7
    cookie_name: str = "bdna_session"
    cookie_secure: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- Storage
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: Path = Path("./var/storage")
    s3_bucket: str = ""
    s3_endpoint_url: str = ""  # e.g. https://<account>.r2.cloudflarestorage.com
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    signed_url_ttl_seconds: int = 900
    public_base_url: str = "http://localhost:8000"
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GiB

    # --- AI providers (provider-independent; see app/ai)
    ai_vision_provider: str = "dev"  # dev | anthropic | openai | openai_compatible
    ai_text_provider: str = "dev"
    ai_embedding_provider: str = "dev"  # dev | openai | openai_compatible
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_vision_model: str = "gpt-4.1-mini"
    openai_text_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    ai_request_timeout_seconds: float = 120.0
    # Visual (image) embeddings: "dev" descriptor, or "http" = self-hosted CLIP/SigLIP-style service
    # that accepts {"image_base64": "..."} and returns {"embedding": [...]}.
    ai_visual_embedding_provider: str = "dev"
    visual_embedding_url: str = ""
    visual_embedding_model: str = "clip-http"
    visual_embedding_dimensions: int = 512
    # Cap on images sent to a vision model per asset (cost control)
    ai_max_images_per_asset: int = 6

    # --- Media processing
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    tesseract_binary: str = "tesseract"
    max_video_keyframes: int = 24
    max_document_pages_rendered: int = 30

    # --- Workers
    worker_poll_seconds: float = 1.0
    worker_concurrency: int = 2
    job_lock_timeout_seconds: int = 1800

    # --- Exports
    export_ttl_days: int = 14

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and s.secret_key.startswith("dev-insecure"):
        raise RuntimeError("BDNA_SECRET_KEY must be set to a strong secret in production")
    return s
