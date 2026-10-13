"""Database engines and tenant-aware sessions.

Three engines, three Postgres roles:

* ``app``    — the only engine used for tenant data. Row Level Security is FORCED on every
               tenant table; the role is not the table owner and has NOBYPASSRLS.
               Every transaction starts by setting ``app.org_id`` / ``app.user_id`` (transaction
               local), so a missing context fails closed (zero rows, inserts rejected).
* ``system`` — BYPASSRLS. Used only through ``system_session()`` by a small, audited set of
               platform functions: login lookups, API-token resolution, organization
               creation, cross-tenant admin aggregates and job claiming.
* ``owner``  — migrations only (Alembic). Never used by the running application.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@dataclass(frozen=True)
class TenantContext:
    org_id: uuid.UUID | None
    user_id: uuid.UUID | None = None

    def as_settings(self) -> tuple[str, str]:
        return (str(self.org_id) if self.org_id else "", str(self.user_id) if self.user_id else "")


_engines: dict[str, Engine] = {}


def _engine(kind: str) -> Engine:
    if kind not in _engines:
        s = get_settings()
        url = {"app": s.database_app_url, "system": s.database_system_url, "owner": s.database_owner_url}[kind]
        _engines[kind] = create_engine(
            url,
            pool_size=s.db_pool_size,
            max_overflow=s.db_pool_size,
            pool_pre_ping=True,
            future=True,
        )
    return _engines[kind]


def dispose_engines() -> None:
    for e in _engines.values():
        e.dispose()
    _engines.clear()


_AppSession = sessionmaker(expire_on_commit=False, autoflush=True)
_SystemSession = sessionmaker(expire_on_commit=False, autoflush=True)


def _install_context(session: Session, ctx: TenantContext) -> None:
    session.info["tenant_ctx"] = ctx

    @event.listens_for(session, "after_begin")
    def _set_tenant(sess: Session, transaction, connection) -> None:  # noqa: ANN001
        c: TenantContext = sess.info["tenant_ctx"]
        org, user = c.as_settings()
        connection.exec_driver_sql(
            "SELECT set_config('app.org_id', %s, true), set_config('app.user_id', %s, true)",
            (org, user),
        )


def new_tenant_session(ctx: TenantContext) -> Session:
    """A session bound to the RLS-enforced role, scoped to one organization."""
    session = _AppSession(bind=_engine("app"))
    _install_context(session, ctx)
    return session


@contextmanager
def tenant_session(ctx: TenantContext) -> Iterator[Session]:
    session = new_tenant_session(ctx)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def system_session() -> Iterator[Session]:
    """Privileged (BYPASSRLS) session. Only for the narrow platform functions listed above."""
    session = _SystemSession(bind=_engine("system"))
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def owner_engine() -> Engine:
    return _engine("owner")
