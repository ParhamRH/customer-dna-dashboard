"""Periodic housekeeping (run by the worker janitor and by ``python -m app.cli cleanup``).

* Expire completed export archives after ``BDNA_EXPORT_TTL_DAYS`` and delete their files.
* Delete staged import archives that were discarded, rejected as invalid, or abandoned.
* Revoke nothing and delete no tenant knowledge — retention of assets and organizations is
  handled by their own scheduled purge jobs (see the retention workflow in docs/operations.md).

Uses the privileged role because it walks every tenant; each file operation is done through a
``TenantStorage`` bound to the owning organization, so keys can never cross tenants.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from sqlalchemy import select

from app.db.session import system_session
from app.models import AuditLog, ExportJob, ImportJob
from app.storage.backends import StorageError, TenantStorage

log = logging.getLogger("bdna.maintenance")
ABANDONED_IMPORT_DAYS = 7


def expire_exports(now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.UTC)
    n = 0
    with system_session() as s:
        rows = s.scalars(select(ExportJob).where(ExportJob.status == "completed", ExportJob.expires_at.is_not(None),
                                                 ExportJob.expires_at < now).limit(500)).all()
        for e in rows:
            if e.storage_uri:
                store = TenantStorage(e.organization_id)
                try:
                    store.delete(store.key_for_uri(e.storage_uri))
                except StorageError:
                    log.exception("could not delete export archive %s", e.id)
                    continue
            e.status, e.storage_uri = "expired", None
            s.add(AuditLog(organization_id=e.organization_id, actor_type="system", action="export.expired",
                           entity_type="export", entity_id=str(e.id), details={}))
            n += 1
    return n


def clean_import_staging(now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.UTC)
    cutoff = now - dt.timedelta(days=ABANDONED_IMPORT_DAYS)
    n = 0
    with system_session() as s:
        rows = s.scalars(select(ImportJob).where(
            ((ImportJob.status.in_(["discarded", "invalid", "failed"])) | (ImportJob.status == "validated"))
            & (ImportJob.updated_at < cutoff)
        ).limit(500)).all()
        for ij in rows:
            if (ij.options or {}).get("staging_deleted"):
                continue
            store = TenantStorage(ij.organization_id)
            try:
                store.delete(store.key_for_uri(ij.staging_uri))
            except StorageError:
                log.exception("could not delete import staging %s", ij.id)
                continue
            if ij.status == "validated":
                ij.status = "discarded"
            ij.options = {**(ij.options or {}), "staging_deleted": True}
            n += 1
    return n


def run_all() -> dict[str, Any]:
    return {"exports_expired": expire_exports(), "import_staging_cleaned": clean_import_staging()}
