from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.common import PageParams, page_params, paginate, row_to_dict
from app.api.deps import TenantDep
from app.api.errors import NotFound, ValidationFailed
from app.jobs.queue import retry
from app.models import ProcessingJob

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    tenant: TenantDep,
    params: PageParams = Depends(page_params),
    status: list[str] | None = Query(None),
    job_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> dict:
    tenant.require("jobs.read")
    q = select(ProcessingJob).order_by(ProcessingJob.created_at.desc())
    if status:
        q = q.where(ProcessingJob.status.in_(status))
    if job_type:
        q = q.where(ProcessingJob.job_type == job_type)
    if entity_id:
        q = q.where(ProcessingJob.entity_id == entity_id)
    return paginate(tenant.db, q, params, lambda j: row_to_dict(j, {"payload"}))


@router.get("/{job_id}")
def get_job(job_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("jobs.read")
    j = tenant.db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
    if j is None:
        raise NotFound("Job not found")
    return row_to_dict(j)


@router.post("/{job_id}/retry")
def retry_job(job_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("jobs.manage")
    j = retry(tenant.db, job_id)
    if j is None:
        raise NotFound("Job not found")
    if j.status != "queued":
        raise ValidationFailed(f"Only failed, dead or cancelled jobs can be retried (status: {j.status})")
    tenant.audit("job.retried", "job", j.id, {"job_type": j.job_type})
    return row_to_dict(j)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("jobs.manage")
    j = tenant.db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
    if j is None:
        raise NotFound("Job not found")
    if j.status != "queued":
        raise ValidationFailed("Only queued jobs can be cancelled")
    j.status = "cancelled"
    tenant.audit("job.cancelled", "job", j.id, {"job_type": j.job_type})
    return row_to_dict(j)
