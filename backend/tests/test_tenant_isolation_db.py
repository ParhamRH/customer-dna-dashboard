"""Database-level tenant isolation: Row Level Security, grants, composite FKs, triggers.

These tests talk to PostgreSQL directly as the runtime role (bdna_app) — the same role the
API uses — so they prove isolation holds even if application code forgot a WHERE clause.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.db.session import TenantContext, system_session, tenant_session
from app.models import Asset, AuditLog, Brand, Organization, Relationship, User


def _ids(customers):
    return {k: (uuid.UUID(c.org_id), uuid.UUID(c.brand_id)) for k, c in customers.items()}


def test_no_context_sees_nothing(customers):
    with tenant_session(TenantContext(org_id=None)) as db:
        assert db.scalars(select(Brand)).all() == []
        assert db.scalars(select(Organization)).all() == []


def test_select_without_where_is_scoped(customers):
    ids = _ids(customers)
    for _letter, (org, brand) in ids.items():
        with tenant_session(TenantContext(org_id=org)) as db:
            brands = db.scalars(select(Brand)).all()
            assert {b.organization_id for b in brands} == {org}
            assert brand in {b.id for b in brands}
            orgs = db.scalars(select(Organization)).all()
            assert [o.id for o in orgs] == [org]


def test_cannot_insert_into_other_tenant(customers):
    ids = _ids(customers)
    org_a, _ = ids["A"]
    org_b, _ = ids["B"]
    with pytest.raises(DBAPIError) as exc:
        with tenant_session(TenantContext(org_id=org_a)) as db:
            db.add(Brand(organization_id=org_b, name="Injected", slug=f"inj-{uuid.uuid4().hex[:6]}"))
            db.flush()
    assert "row-level security" in str(exc.value).lower()


def test_cannot_update_or_delete_other_tenant(customers):
    ids = _ids(customers)
    org_a, _ = ids["A"]
    _, brand_b = ids["B"]
    with tenant_session(TenantContext(org_id=org_a)) as db:
        r1 = db.execute(text("UPDATE brands SET name = 'pwned' WHERE id = :id"), {"id": brand_b})
        r2 = db.execute(text("DELETE FROM brands WHERE id = :id"), {"id": brand_b})
        assert r1.rowcount == 0 and r2.rowcount == 0
    with system_session() as s:
        assert s.scalar(select(Brand.name).where(Brand.id == brand_b)) == "Brand B"


def test_composite_fk_blocks_cross_tenant_reference(customers):
    """Even the privileged role cannot attach a child row to another organization's parent."""
    ids = _ids(customers)
    org_a, _ = ids["A"]
    _, brand_b = ids["B"]
    with pytest.raises(DBAPIError) as exc:
        with system_session() as s:
            s.add(Asset(organization_id=org_a, brand_id=brand_b, title="x", asset_type="image"))
            s.flush()
    assert "foreign key" in str(exc.value).lower()


def test_relationship_trigger_blocks_cross_tenant_edges(customers):
    ids = _ids(customers)
    org_a, brand_a = ids["A"]
    org_b, brand_b = ids["B"]
    with system_session() as s:
        a1 = Asset(organization_id=org_a, brand_id=brand_a, title="A asset", asset_type="image", source_type="generated")
        b1 = Asset(organization_id=org_b, brand_id=brand_b, title="B asset", asset_type="image", source_type="generated")
        s.add_all([a1, b1])
        s.flush()
        a1_id, b1_id = a1.id, b1.id
    with pytest.raises(DBAPIError) as exc:
        with system_session() as s:
            s.add(
                Relationship(
                    organization_id=org_a, brand_id=brand_a, source_type="asset", source_id=a1_id,
                    relation_type="related_to", target_type="asset", target_id=b1_id,
                )
            )
            s.flush()
    assert "not found in organization" in str(exc.value)


def test_runtime_role_cannot_escalate_privileges(customers):
    org_a, _ = _ids(customers)["A"]
    admin_id = None
    with system_session() as s:
        admin_id = s.scalar(select(User.id).where(User.email == f"admin@{customers['A'].slug}.test"))
    with pytest.raises(ProgrammingError) as exc:
        with tenant_session(TenantContext(org_id=org_a, user_id=admin_id)) as db:
            db.execute(text("UPDATE users SET is_platform_admin = true WHERE id = :id"), {"id": admin_id})
    assert "permission denied" in str(exc.value).lower()


def test_audit_log_is_append_only_for_runtime_role(customers):
    org_a, _ = _ids(customers)["A"]
    with tenant_session(TenantContext(org_id=org_a)) as db:
        db.add(AuditLog(organization_id=org_a, actor_type="system", action="test.event"))
    with pytest.raises(ProgrammingError):
        with tenant_session(TenantContext(org_id=org_a)) as db:
            db.execute(text("DELETE FROM audit_logs"))
    with pytest.raises(ProgrammingError):
        with tenant_session(TenantContext(org_id=org_a)) as db:
            db.execute(text("UPDATE audit_logs SET action = 'tampered'"))


def test_runtime_role_cannot_create_organizations(customers):
    org_a, _ = _ids(customers)["A"]
    with pytest.raises(ProgrammingError):
        with tenant_session(TenantContext(org_id=org_a)) as db:
            db.execute(text("INSERT INTO organizations (slug, name) VALUES ('evil', 'Evil')"))


def test_original_asset_metadata_is_immutable(customers):
    org_a, brand_a = _ids(customers)["A"]
    with tenant_session(TenantContext(org_id=org_a)) as db:
        a = Asset(
            organization_id=org_a, brand_id=brand_a, title="orig", asset_type="image",
            storage_uri="local://x/original.png", checksum="a" * 64, file_size=10, mime_type="image/png",
            original_filename="o.png",
        )
        db.add(a)
        db.flush()
        aid = a.id
    with pytest.raises(DBAPIError) as exc:
        with tenant_session(TenantContext(org_id=org_a)) as db:
            db.execute(text("UPDATE assets SET checksum = :c WHERE id = :id"), {"c": "b" * 64, "id": aid})
    assert "immutable" in str(exc.value)
    # Editorial fields remain editable
    with tenant_session(TenantContext(org_id=org_a)) as db:
        db.execute(text("UPDATE assets SET title = 'renamed' WHERE id = :id"), {"id": aid})


def test_every_tenant_table_has_forced_rls():
    from app.models import Base

    with system_session() as s:
        rows = s.execute(
            text("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace")
        ).all()
    flags = {r[0]: (r[1], r[2]) for r in rows}
    tenant_tables = [t.name for t in Base.metadata.sorted_tables if "organization_id" in t.c and not t.c.organization_id.nullable]
    assert tenant_tables, "expected tenant tables"
    missing = [t for t in tenant_tables if flags.get(t) != (True, True)]
    assert missing == [], f"tenant tables without forced RLS: {missing}"
