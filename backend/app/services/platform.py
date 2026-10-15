"""Cross-tenant, aggregate-only views for the platform administrator dashboard.

Uses the privileged role, but returns only counts/metadata — never tenant content. Opening
a customer's actual content always goes through the RLS-enforced tenant session.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import case, func, or_, select

from app.api.common import jsonable
from app.db.session import system_session
from app.models import (
    AiSuggestion,
    Asset,
    AssetAnalysis,
    AssetDerivative,
    AuditLog,
    Brand,
    ColorToken,
    ExportJob,
    Organization,
    OrganizationUser,
    Palette,
    ProcessingJob,
)


def _per_org(s, stmt) -> dict[uuid.UUID, Any]:
    return {row[0]: row[1] for row in s.execute(stmt).all()}


def customer_list(search: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    with system_session() as s:
        q = select(Organization).order_by(Organization.name)
        if status:
            q = q.where(Organization.status == status)
        if search:
            like = f"%{search.lower()}%"
            q = q.where(or_(func.lower(Organization.name).like(like), func.lower(Organization.slug).like(like)))
        orgs = s.scalars(q).all()
        live = Asset.deleted_at.is_(None)
        assets = _per_org(s, select(Asset.organization_id, func.count()).where(live).group_by(Asset.organization_id))
        orig_bytes = _per_org(
            s, select(Asset.organization_id, func.coalesce(func.sum(Asset.file_size), 0)).group_by(Asset.organization_id)
        )
        deriv_bytes = _per_org(
            s,
            select(AssetDerivative.organization_id, func.coalesce(func.sum(AssetDerivative.file_size), 0)).group_by(
                AssetDerivative.organization_id
            ),
        )
        brands = _per_org(s, select(Brand.organization_id, func.count()).group_by(Brand.organization_id))
        members = _per_org(
            s,
            select(OrganizationUser.organization_id, func.count())
            .where(OrganizationUser.status == "active")
            .group_by(OrganizationUser.organization_id),
        )
        pending_an = _per_org(
            s,
            select(AssetAnalysis.organization_id, func.count())
            .where(AssetAnalysis.status == "pending_review")
            .group_by(AssetAnalysis.organization_id),
        )
        pending_sg = _per_org(
            s,
            select(AiSuggestion.organization_id, func.count())
            .where(AiSuggestion.status == "pending")
            .group_by(AiSuggestion.organization_id),
        )
        last_act = _per_org(
            s, select(AuditLog.organization_id, func.max(AuditLog.created_at)).group_by(AuditLog.organization_id)
        )
        # Approved palette swatches (first brand) for the customer list's color strip — display metadata only.
        swatches: dict[uuid.UUID, list[dict[str, Any]]] = {}
        first_brand: dict[uuid.UUID, str] = {}
        for org_id, brand_id in s.execute(
            select(Brand.organization_id, Brand.id).where(Brand.status == "active").order_by(Brand.created_at)
        ).all():
            first_brand.setdefault(org_id, str(brand_id))
        if orgs:
            rows = s.execute(
                select(ColorToken.organization_id, ColorToken.brand_id, ColorToken.hex, ColorToken.name, Palette.role)
                .join(Palette, Palette.id == ColorToken.palette_id)
                .where(Palette.status == "approved", ColorToken.organization_id.in_([o.id for o in orgs]))
                .order_by(Palette.sort_order, Palette.created_at, Palette.id, ColorToken.sort_order)
            ).all()
            for org_id, brand_id, hexv, name, role in rows:
                if str(brand_id) != first_brand.get(org_id):
                    continue
                lst = swatches.setdefault(org_id, [])
                if len(lst) < 16:
                    lst.append({"hex": hexv, "name": name, "role": role})
        out = []
        for o in orgs:
            out.append(
                {
                    "id": str(o.id),
                    "slug": o.slug,
                    "name": o.name,
                    "status": o.status,
                    "industry": o.industry,
                    "country": o.country,
                    "contact_email": o.contact_email,
                    "created_at": o.created_at.isoformat(),
                    "archived_at": o.archived_at.isoformat() if o.archived_at else None,
                    "brand_count": brands.get(o.id, 0),
                    "member_count": members.get(o.id, 0),
                    "asset_count": assets.get(o.id, 0),
                    "storage_bytes": int(orig_bytes.get(o.id, 0)) + int(deriv_bytes.get(o.id, 0)),
                    "storage_quota_bytes": o.storage_quota_bytes,
                    "pending_reviews": pending_an.get(o.id, 0) + pending_sg.get(o.id, 0),
                    "last_activity_at": jsonable(last_act.get(o.id)),
                    "palette": swatches.get(o.id, []),
                }
            )
        return out


def overview() -> dict[str, Any]:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=7)
    with system_session() as s:
        orgs = dict(s.execute(select(Organization.status, func.count()).group_by(Organization.status)).all())
        jobs = dict(s.execute(select(ProcessingJob.status, func.count()).group_by(ProcessingJob.status)).all())
        jobs_by_type = [
            {"job_type": jt, "succeeded": int(ok or 0), "failed": int(bad or 0), "total": int(tot)}
            for jt, ok, bad, tot in s.execute(
                select(
                    ProcessingJob.job_type,
                    func.sum(case((ProcessingJob.status == "succeeded", 1), else_=0)),
                    func.sum(case((ProcessingJob.status.in_(["failed", "dead"]), 1), else_=0)),
                    func.count(),
                ).group_by(ProcessingJob.job_type)
            ).all()
        ]
        avg_ms = s.scalar(
            select(
                func.avg(func.extract("epoch", ProcessingJob.finished_at - ProcessingJob.started_at) * 1000)
            ).where(ProcessingJob.status == "succeeded")
        )
        total_assets = s.scalar(select(func.count()).select_from(Asset).where(Asset.deleted_at.is_(None))) or 0
        total_bytes = (s.scalar(select(func.coalesce(func.sum(Asset.file_size), 0))) or 0) + (
            s.scalar(select(func.coalesce(func.sum(AssetDerivative.file_size), 0))) or 0
        )
        assets_by_type = dict(
            s.execute(
                select(Asset.asset_type, func.count()).where(Asset.deleted_at.is_(None)).group_by(Asset.asset_type)
            ).all()
        )
        pending = (s.scalar(select(func.count()).select_from(AssetAnalysis).where(AssetAnalysis.status == "pending_review")) or 0) + (
            s.scalar(select(func.count()).select_from(AiSuggestion).where(AiSuggestion.status == "pending")) or 0
        )
        uploads_week = s.scalar(select(func.count()).select_from(Asset).where(Asset.created_at >= since)) or 0
        exports = dict(s.execute(select(ExportJob.status, func.count()).group_by(ExportJob.status)).all())
        daily = [
            {"day": d.isoformat(), "count": c}
            for d, c in s.execute(
                select(func.date_trunc("day", AuditLog.created_at).label("d"), func.count())
                .where(AuditLog.created_at >= dt.datetime.now(dt.UTC) - dt.timedelta(days=14))
                .group_by("d")
                .order_by("d")
            ).all()
        ]
        return {
            "customers": {"total": sum(orgs.values()), **orgs},
            "assets": {"total": total_assets, "by_type": assets_by_type, "uploaded_last_7_days": uploads_week},
            "storage_bytes": int(total_bytes),
            "pending_reviews": pending,
            "jobs": {"by_status": jobs, "by_type": jobs_by_type, "avg_duration_ms": float(avg_ms) if avg_ms else None},
            "exports": exports,
            "activity_last_14_days": daily,
        }


def recent_activity(limit: int = 50, organization_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
    with system_session() as s:
        q = (
            select(AuditLog, Organization.name, Organization.slug)
            .outerjoin(Organization, Organization.id == AuditLog.organization_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        if organization_id:
            q = q.where(AuditLog.organization_id == organization_id)
        return [
            {
                "id": a.id,
                "organization_id": jsonable(a.organization_id),
                "organization_name": name,
                "organization_slug": slug,
                "actor": a.actor_label,
                "actor_type": a.actor_type,
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "details": a.details,
                "created_at": a.created_at.isoformat(),
            }
            for a, name, slug in s.execute(q).all()
        ]


def jobs(status: str | None, limit: int, offset: int) -> dict[str, Any]:
    with system_session() as s:
        q = select(ProcessingJob, Organization.name).join(Organization, Organization.id == ProcessingJob.organization_id)
        if status:
            q = q.where(ProcessingJob.status == status)
        total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
        rows = s.execute(q.order_by(ProcessingJob.created_at.desc()).limit(limit).offset(offset)).all()
        return {
            "items": [
                {
                    "id": str(j.id),
                    "organization_id": str(j.organization_id),
                    "organization_name": name,
                    "job_type": j.job_type,
                    "entity_type": j.entity_type,
                    "entity_id": jsonable(j.entity_id),
                    "status": j.status,
                    "attempts": j.attempts,
                    "max_attempts": j.max_attempts,
                    "progress": j.progress,
                    "error": (j.error or "")[:500] or None,
                    "created_at": j.created_at.isoformat(),
                    "started_at": jsonable(j.started_at),
                    "finished_at": jsonable(j.finished_at),
                }
                for j, name in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
