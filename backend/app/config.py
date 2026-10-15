"""Runtime configuration. Every value comes from the environment (see .env.example)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Later files win: backend/.env (native development) overrides the repository-level .env
    # (Docker Compose deployment). Real environment variables override both.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_prefix="BDNA_", extra="ignore")

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
    # Sign-in throttling: failed attempts within the window, per e-mail address and per client IP.
    login_window_minutes: int = 15
    login_max_failures_per_email: int = 8
    login_max_failures_per_ip: int = 40
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- Storage
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: Path = Path("./var/storage")
    s3_bucket: str = ""
    s3_endpoint_url: str = ""  # e.g. https://<account>.r2.cloudflarestorage.com
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    # Endpoint browsers use for signed download URLs when it differs from the one the API uses
    # (e.g. MinIO reached as http://minio:9000 inside Compose but http://localhost:9000 outside).
    s3_public_endpoint_url: str = ""
    s3_addressing_style: Literal["auto", "path", "virtual"] = "auto"  # MinIO needs "path"
    signed_url_ttl_seconds: int = 900
    public_base_url: str = "http://localhost:8000"
    mcp_public_url: str = "http://localhost:8001"  # where external AI clients reach the MCP server (Streamable HTTP)
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

    # --- Outbound requests to customer-supplied URLs (webhooks, AI base URLs)
    # None = allow private/internal targets only outside production.
    outbound_allow_private: bool | None = None
    outbound_allowed_hosts: list[str] = []  # e.g. ["n8n"] for the Compose-internal n8n

    # --- Exports
    export_ttl_days: int = 14

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production:
        problems = []
        if s.secret_key.startswith(("dev-insecure", "dev-only")) or "CHANGE-ME" in s.secret_key or len(s.secret_key) < 32:
            problems.append("BDNA_SECRET_KEY must be a random secret of at least 32 characters")
        if not s.encryption_key or "CHANGE-ME" in s.encryption_key:
            problems.append("BDNA_ENCRYPTION_KEY must be set (a Fernet key) so integration secrets are encrypted with a dedicated key")
        if problems:
            raise RuntimeError("Refusing to start in production: " + "; ".join(problems))
    return s
