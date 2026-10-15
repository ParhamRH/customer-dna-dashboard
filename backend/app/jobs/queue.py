"""Durable job queue on PostgreSQL (no extra infrastructure).

* ``enqueue`` inserts in the caller's (tenant) transaction, so a job exists iff the triggering
  change committed. ``pg_notify`` wakes idle workers at commit.
* Workers ``claim`` with ``FOR UPDATE SKIP LOCKED`` via the privileged role (jobs from all
  tenants), then execute each handler inside a tenant session for the job's organization.
* Failures retry with exponential backoff; after ``max_attempts`` a job is ``dead`` and can be
  retried manually (API: POST /v1/jobs/{id}/retry).
"""
from __future__ import annotations

import datetime as dt
import logging
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import TenantContext, system_session, tenant_session
from app.models import ProcessingJob

log = logging.getLogger("bdna.jobs")
NOTIFY_CHANNEL = "bdna_jobs"


def enqueue(
    db: Session,
    org_id: uuid.UUID,
    job_type: str,
    *,
    brand_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    priority: int = 100,
    run_after: dt.datetime | None = None,
    max_attempts: int = 3,
    created_by: uuid.UUID | None = None,
    parent_job_id: uuid.UUID | None = None,
) -> ProcessingJob:
    job = ProcessingJob(
        id=uuid.uuid4(),
        organization_id=org_id,
        brand_id=brand_id,
        job_type=job_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
        priority=priority,
        max_attempts=max_attempts,
        created_by=created_by,
        parent_job_id=parent_job_id,
    )
    if run_after:
        job.run_after = run_after
    db.add(job)
    db.flush()
    db.execute(text("SELECT pg_notify(:c, :p)"), {"c": NOTIFY_CHANNEL, "p": job_type})
    return job


@dataclass
class ClaimedJob:
    id: uuid.UUID
    organization_id: uuid.UUID
    brand_id: uuid.UUID | None
    job_type: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    created_by: uuid.UUID | None
    result: dict[str, Any] = field(default_factory=dict)


def claim(worker_id: str, job_types: list[str] | None = None) -> ClaimedJob | None:
    type_filter = "AND job_type = ANY(:types)" if job_types else ""
    with system_session() as s:
        row = s.execute(
            text(
                f"""
                UPDATE processing_jobs j
                   SET status = 'running', locked_by = :w, locked_at = now(),
                       started_at = coalesce(j.started_at, now()), attempts = j.attempts + 1, error = NULL
                 WHERE j.id = (
                     SELECT id FROM processing_jobs
                      WHERE status = 'queued' AND run_after <= now() {type_filter}
                      ORDER BY priority, run_after, created_at
                      FOR UPDATE SKIP LOCKED
                      LIMIT 1)
                RETURNING j.id, j.organization_id, j.brand_id, j.job_type, j.entity_type, j.entity_id,
                          j.payload, j.attempts, j.max_attempts, j.created_by
                """
            ),
            {"w": worker_id, "types": job_types},
        ).first()
        if row is None:
            return None
        return ClaimedJob(*row)


def requeue_stale() -> int:
    """Return jobs whose worker died (lock older than the timeout) to the queue."""
    timeout = get_settings().job_lock_timeout_seconds
    with system_session() as s:
        res = s.execute(
            text(
                """
                UPDATE processing_jobs
                   SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
                       locked_by = NULL, locked_at = NULL,
                       error = coalesce(error, '') || 'worker lock expired; '
                 WHERE status = 'running' AND locked_at < now() - make_interval(secs => :t)
                """
            ),
            {"t": timeout},
        )
        return res.rowcount or 0


def complete(job_id: uuid.UUID, result: dict[str, Any]) -> None:
    with system_session() as s:
        s.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .values(status="succeeded", result=result, progress=100, finished_at=dt.datetime.now(dt.UTC),
                    locked_by=None, locked_at=None)
        )


def fail(job: ClaimedJob, error: str, result: dict[str, Any] | None = None, *, permanent: bool = False) -> str:
    now = dt.datetime.now(dt.UTC)
    exhausted = permanent or job.attempts >= job.max_attempts
    status = "dead" if exhausted else "queued"
    backoff = dt.timedelta(seconds=min(3600, 15 * 2 ** (job.attempts - 1)))
    with system_session() as s:
        s.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job.id)
            .values(
                status=status,
                error=error[:20000],
                result=result or {},
                run_after=now + backoff,
                finished_at=now if exhausted else None,
                locked_by=None,
                locked_at=None,
            )
        )
    return status


def set_progress(job_id: uuid.UUID, progress: int, result: dict[str, Any] | None = None) -> None:
    values: dict[str, Any] = {"progress": max(0, min(100, progress))}
    if result is not None:
        values["result"] = result
    with system_session() as s:
        s.execute(update(ProcessingJob).where(ProcessingJob.id == job_id).values(**values))


# --- Handler registry ------------------------------------------------------------------------
class PermanentJobError(Exception):
    """Raise from a handler when retrying cannot help (bad input, missing entity)."""


@dataclass
class JobContext:
    job: ClaimedJob
    steps: list[dict[str, Any]] = field(default_factory=list)

    @property
    def org_id(self) -> uuid.UUID:
        return self.job.organization_id

    def session(self):
        """Tenant (RLS) session for the job's organization."""
        return tenant_session(TenantContext(org_id=self.job.organization_id, user_id=self.job.created_by))

    def progress(self, pct: int) -> None:
        set_progress(self.job.id, pct, {"steps": self.steps})

    def step(self, name: str, status: str, started: float | None = None, **info: Any) -> None:
        import time

        entry = {"step": name, "status": status, **info}
        if started is not None:
            entry["duration_ms"] = int((time.perf_counter() - started) * 1000)
        self.steps.append(entry)


HANDLERS: dict[str, Callable[[JobContext], dict[str, Any] | None]] = {}


def handler(job_type: str):
    def deco(fn: Callable[[JobContext], dict[str, Any] | None]):
        HANDLERS[job_type] = fn
        return fn

    return deco


def public_error(error: str | None) -> str | None:
    """What a workspace user may see of a job failure: the exception line only. Stack traces (server
    paths, library internals) stay in the database and the logs for platform operators."""
    if not error:
        return None
    first = error.strip().split("\n", 1)[0].strip()
    return first[:500] or None


def run_job(job: ClaimedJob) -> str:
    from app.jobs import handlers  # noqa: F401  (registers handlers)

    fn = HANDLERS.get(job.job_type)
    ctx = JobContext(job)
    if fn is None:
        return fail(job, f"no handler for job type {job.job_type!r}", permanent=True)
    try:
        result = fn(ctx) or {}
        result.setdefault("steps", ctx.steps)
        complete(job.id, result)
        return "succeeded"
    except PermanentJobError as e:
        log.warning("job %s permanent failure: %s", job.id, e)
        return fail(job, str(e), {"steps": ctx.steps}, permanent=True)
    except Exception as e:  # noqa: BLE001
        log.exception("job %s failed", job.id)
        return fail(job, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-4000:]}", {"steps": ctx.steps})


def drain(max_jobs: int = 1000, job_types: list[str] | None = None, worker_id: str = "inline") -> int:
    """Run queued jobs synchronously until the queue is empty (tests, CLI, small deployments)."""
    n = 0
    while n < max_jobs:
        job = claim(worker_id, job_types)
        if job is None:
            break
        run_job(job)
        n += 1
    return n


def retry(db: Session, job_id: uuid.UUID) -> ProcessingJob | None:
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
    if job is None:
        return None
    if job.status in ("failed", "dead", "cancelled"):
        job.status = "queued"
        job.run_after = dt.datetime.now(dt.UTC)
        job.max_attempts = max(job.max_attempts, job.attempts + 1)
        job.finished_at = None
        db.flush()
        db.execute(text("SELECT pg_notify(:c, :p)"), {"c": NOTIFY_CHANNEL, "p": job.job_type})
    return job
