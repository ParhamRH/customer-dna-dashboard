"""Integration settings: webhooks (n8n etc.), per-customer AI provider overrides, prompt templates."""
from __future__ import annotations

import datetime as dt
import functools
import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ai import registry
from app.ai.prompts import DEFAULTS
from app.api.common import row_to_dict
from app.api.deps import TenantDep
from app.api.errors import NotFound, ValidationFailed
from app.config import get_settings
from app.jobs.queue import enqueue, public_error
from app.models import Integration, ProcessingJob, PromptTemplate
from app.security.credentials import encrypt_secret
from app.security.outbound import OutboundUrlError, check_outbound_url
from app.services.events import EVENT_TYPES

router = APIRouter(tags=["integrations"])


def _out(i: Integration) -> dict[str, Any]:
    d = row_to_dict(i, {"secret_encrypted"})
    d["has_secret"] = bool(i.secret_encrypted)
    return d


class IntegrationIn(BaseModel):
    kind: str = Field(pattern="^(webhook|ai_provider|mcp_client|rest_client)$")
    name: str = Field(min_length=1, max_length=200)
    brand_id: uuid.UUID | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    secret: str | None = Field(None, description="Webhook signing secret or AI provider API key (stored encrypted, never returned)")
    status: str = Field("active", pattern="^(active|disabled)$")


def _validate(body: IntegrationIn) -> None:
    c = body.config
    for key in ("url", "base_url"):
        if c.get(key):
            try:
                check_outbound_url(str(c[key]))
            except OutboundUrlError as e:
                raise ValidationFailed(f"config.{key}: {e}") from e
    if body.kind == "webhook":
        if not str(c.get("url", "")).startswith(("https://", "http://")):
            raise ValidationFailed("webhook config.url must be an http(s) URL")
        bad = [e for e in c.get("events", ["*"]) if e != "*" and e not in EVENT_TYPES]
        if bad:
            raise ValidationFailed("unknown events", details={"invalid": bad, "allowed": EVENT_TYPES})
    if body.kind == "ai_provider":
        if c.get("capability") not in ("vision", "text", "embedding"):
            raise ValidationFailed("ai_provider config.capability must be vision | text | embedding")
        if c.get("provider") not in ("anthropic", "openai", "openai_compatible", "dev"):
            raise ValidationFailed("ai_provider config.provider must be anthropic | openai | openai_compatible | dev")


@functools.lru_cache(maxsize=1)
def _mcp_tools() -> tuple[tuple[str, str], ...]:
    """Tool names and descriptions, read from the MCP server definition itself (never hand-copied)."""
    try:
        import asyncio

        from app.mcp.server import build_server

        tools = asyncio.run(build_server().list_tools())
        return tuple((t.name, t.description or "") for t in tools)
    except Exception:  # noqa: BLE001 - the MCP package is optional for the REST API
        return ()


def mcp_info() -> dict[str, Any]:
    """How an external AI client connects to the read-only MCP server. Contains no secrets."""
    s = get_settings()
    url = s.mcp_public_url.rstrip("/")
    return {
        "transports": ["stdio", "streamable-http"],
        "http_url": f"{url}/mcp",
        "stdio_command": "BDNA_MCP_TOKEN=bdna_… python -m app.mcp",
        "http_command": "python -m app.mcp --transport streamable-http --host 0.0.0.0 --port 8001",
        "auth": "Each MCP client uses a workspace API token (Authorization: Bearer bdna_…), bound to one customer and optionally one brand.",
        "read_only": True,
        "public_base_url": s.public_base_url,
        "tools": [{"name": n, "description": d} for n, d in _mcp_tools()],
    }


@router.get("/integrations")
def list_integrations(tenant: TenantDep) -> dict:
    tenant.require("integrations.manage")
    rows = tenant.db.scalars(select(Integration).order_by(Integration.created_at)).all()
    return {"items": [_out(i) for i in rows], "event_types": EVENT_TYPES, "ai": registry.describe(tenant.db), "mcp": mcp_info()}


@router.get("/integrations/{integration_id}/deliveries")
def webhook_deliveries(integration_id: uuid.UUID, tenant: TenantDep, limit: int = 20) -> dict:
    """Recent delivery attempts for one webhook (from the job queue; payload bodies are not returned)."""
    tenant.require("integrations.manage")
    i = tenant.db.scalar(select(Integration).where(Integration.id == integration_id))
    if i is None or i.kind != "webhook":
        raise NotFound("Webhook not found")
    jobs = tenant.db.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.job_type == "webhook.deliver", ProcessingJob.payload["integration_id"].astext == str(i.id))
        .order_by(ProcessingJob.created_at.desc())
        .limit(max(1, min(limit, 100)))
    ).all()
    return {"items": [{
        "job_id": str(j.id), "event": (j.payload or {}).get("event"), "status": j.status, "attempts": j.attempts,
        "max_attempts": j.max_attempts, "status_code": (j.result or {}).get("status_code"), "error": public_error(j.error),
        "created_at": j.created_at.isoformat(), "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    } for j in jobs]}


@router.post("/integrations", status_code=201)
def create_integration(body: IntegrationIn, tenant: TenantDep) -> dict:
    tenant.require("integrations.manage")
    _validate(body)
    i = Integration(organization_id=tenant.org_id, brand_id=body.brand_id, kind=body.kind, name=body.name, config=body.config,
                    status=body.status, secret_encrypted=encrypt_secret(body.secret) if body.secret else None, created_by=tenant.user_id)
    tenant.db.add(i)
    tenant.db.flush()
    tenant.audit("integration.created", "integration", i.id, {"kind": body.kind, "name": body.name})
    return _out(i)


@router.patch("/integrations/{integration_id}")
def update_integration(integration_id: uuid.UUID, body: dict[str, Any], tenant: TenantDep) -> dict:
    tenant.require("integrations.manage")
    i = tenant.db.scalar(select(Integration).where(Integration.id == integration_id))
    if i is None:
        raise NotFound("Integration not found")
    merged = IntegrationIn.model_validate({"kind": i.kind, "name": i.name, "brand_id": i.brand_id, "config": i.config, "status": i.status,
                                           **{k: v for k, v in body.items() if k != "secret"}})
    _validate(merged)
    i.name, i.config, i.status = merged.name, merged.config, merged.status
    if body.get("secret"):
        i.secret_encrypted = encrypt_secret(body["secret"])
    tenant.audit("integration.updated", "integration", i.id, {"fields": sorted(body)})
    return _out(i)


@router.delete("/integrations/{integration_id}", status_code=204)
def delete_integration(integration_id: uuid.UUID, tenant: TenantDep) -> None:
    tenant.require("integrations.manage")
    i = tenant.db.scalar(select(Integration).where(Integration.id == integration_id))
    if i is None:
        raise NotFound("Integration not found")
    tenant.audit("integration.deleted", "integration", i.id, {"kind": i.kind})
    tenant.db.delete(i)


@router.post("/integrations/{integration_id}/test", status_code=202)
def test_webhook(integration_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("integrations.manage")
    i = tenant.db.scalar(select(Integration).where(Integration.id == integration_id))
    if i is None or i.kind != "webhook":
        raise NotFound("Webhook not found")
    job = enqueue(tenant.db, tenant.org_id, "webhook.deliver", max_attempts=1, payload={
        "integration_id": str(i.id), "event": "integration.test", "data": {"message": "Test event from Brand DNA"},
        "event_id": str(uuid.uuid4()), "occurred_at": dt.datetime.now(dt.UTC).isoformat()})
    return {"job_id": str(job.id)}


# --- Prompt templates (Domain 10) --------------------------------------------------------------
@router.get("/prompts")
def list_prompts(tenant: TenantDep) -> dict:
    tenant.require("knowledge.read")
    rows = tenant.db.scalars(select(PromptTemplate).order_by(PromptTemplate.key, PromptTemplate.version.desc())).all()
    return {"items": [{**row_to_dict(r), "scope": "platform default" if r.organization_id is None else "customer override"} for r in rows],
            "keys": [d[0] for d in DEFAULTS]}


class PromptIn(BaseModel):
    key: str
    template: str = Field(min_length=20)
    name: str | None = None


@router.post("/prompts", status_code=201)
def create_prompt_override(body: PromptIn, tenant: TenantDep) -> dict:
    """Create a new customer-specific version of a prompt; analyses record the version they used."""
    tenant.require("integrations.manage")
    default = next((d for d in DEFAULTS if d[0] == body.key), None)
    if default is None:
        raise ValidationFailed("Unknown prompt key", details={"allowed": [d[0] for d in DEFAULTS]})
    last = tenant.db.scalar(select(PromptTemplate.version).where(PromptTemplate.key == body.key)
                            .order_by(PromptTemplate.version.desc()).limit(1)) or 0
    for old in tenant.db.scalars(select(PromptTemplate).where(PromptTemplate.key == body.key, PromptTemplate.organization_id == tenant.org_id)):
        old.is_active = False
    p = PromptTemplate(organization_id=tenant.org_id, key=body.key, name=body.name or default[1], purpose=default[2],
                       version=last + 1, template=body.template)
    tenant.db.add(p)
    tenant.db.flush()
    tenant.audit("prompt.created", "prompt_template", p.id, {"key": p.key, "version": p.version})
    return row_to_dict(p)


@router.post("/prompts/{key}/reset")
def reset_prompt_override(key: str, tenant: TenantDep) -> dict:
    """Go back to the platform default prompt. Override versions are kept (inactive) for provenance."""
    tenant.require("integrations.manage")
    if key not in [d[0] for d in DEFAULTS]:
        raise NotFound("Unknown prompt key")
    n = 0
    for old in tenant.db.scalars(select(PromptTemplate).where(PromptTemplate.key == key, PromptTemplate.organization_id == tenant.org_id,
                                                               PromptTemplate.is_active.is_(True))):
        old.is_active = False
        n += 1
    tenant.audit("prompt.reset", "prompt_template", None, {"key": key, "deactivated": n})
    return {"key": key, "deactivated": n}
