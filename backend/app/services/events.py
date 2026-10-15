"""Outbound events → signed webhooks (e.g. n8n). Delivery is a retried background job."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.queue import enqueue
from app.models import Integration
from app.security.credentials import decrypt_secret

EVENT_TYPES = (
    "asset.created",
    "asset.processed",
    "review.decided",
    "knowledge.approved",
    "brand.version_published",
    "export.completed",
    "import.committed",
)


def emit(db: Session, org_id: uuid.UUID, event: str, data: dict[str, Any]) -> int:
    """Queue one delivery per active webhook subscribed to ``event`` (same transaction)."""
    hooks = db.scalars(select(Integration).where(Integration.kind == "webhook", Integration.status == "active")).all()
    n = 0
    for h in hooks:
        events = (h.config or {}).get("events") or ["*"]
        if "*" in events or event in events:
            enqueue(
                db, org_id, "webhook.deliver", entity_type=None, entity_id=None, max_attempts=6, priority=200,
                payload={"integration_id": str(h.id), "event": event, "data": data,
                         "event_id": str(uuid.uuid4()), "occurred_at": dt.datetime.now(dt.UTC).isoformat()},
            )
            n += 1
    return n


def sign(secret: str, body: bytes, timestamp: str) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def deliver(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    hook = db.scalar(select(Integration).where(Integration.id == uuid.UUID(payload["integration_id"])))
    if hook is None or hook.status != "active":
        return {"skipped": "integration missing or disabled"}
    url = (hook.config or {}).get("url")
    from app.jobs.queue import PermanentJobError
    from app.security.outbound import OutboundUrlError, check_outbound_url

    try:
        check_outbound_url(url)
    except OutboundUrlError as e:  # re-checked at delivery: DNS may have changed since saving
        raise PermanentJobError(f"webhook URL refused: {e}") from e
    body = json.dumps(
        {"id": payload["event_id"], "type": payload["event"], "occurred_at": payload["occurred_at"],
         "organization_id": str(hook.organization_id), "data": payload["data"]},
        separators=(",", ":"),
    ).encode()
    ts = str(int(dt.datetime.now(dt.UTC).timestamp()))
    headers = {"content-type": "application/json", "x-bdna-event": payload["event"], "x-bdna-timestamp": ts}
    if hook.secret_encrypted:
        headers["x-bdna-signature"] = "sha256=" + sign(decrypt_secret(hook.secret_encrypted), body, ts)
    r = httpx.post(url, content=body, headers=headers, timeout=15, follow_redirects=False)
    hook.last_event_at = dt.datetime.now(dt.UTC)
    if r.status_code >= 400:
        raise RuntimeError(f"webhook responded {r.status_code}")
    return {"status_code": r.status_code}
