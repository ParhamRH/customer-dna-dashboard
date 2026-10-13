"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import __version__
from app.api.errors import install_error_handlers
from app.api.v1 import router as v1_router
from app.config import get_settings
from app.db.session import system_session

log = logging.getLogger("bdna")


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.services.bootstrap import ensure_reference_data

    ensure_reference_data()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Brand DNA & Creative Intelligence Platform API",
        version=__version__,
        description=(
            "Multi-tenant brand knowledge API. Authenticate with a session (dashboard) or an API token "
            "(`Authorization: Bearer bdna_…`). Session users select a workspace with `X-Organization-Id` "
            "(UUID or slug); API tokens are bound to one organization."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(v1_router, prefix="/v1")

    @app.get("/health", tags=["ops"])
    def health() -> dict:
        with system_session() as s:
            s.execute(text("SELECT 1"))
        return {"status": "ok", "version": __version__, "environment": settings.environment}

    return app


app = create_app()
