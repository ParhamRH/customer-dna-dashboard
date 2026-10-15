"""Platform administrator console: users, export registry, integrations inventory, settings,
maintenance (export expiry) and the operations CLI health check."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import update

from app.jobs.queue import drain
from tests.conftest import PASSWORD, Api, login

ADMIN_ONLY = ("/v1/platform/users", "/v1/platform/exports", "/v1/platform/integrations", "/v1/platform/settings")


def test_platform_console_requires_platform_admin(customers):
    for url in ADMIN_ONLY:
        assert customers["A"].admin.get(url).status_code == 403, url


def test_users_list_shows_memberships(platform_admin, customers):
    a = customers["A"]
    r = platform_admin.get("/v1/platform/users", params={"search": a.slug})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    admin = next(u for u in items if u["email"] == f"admin@{a.slug}.test")
    assert [m["organization_slug"] for m in admin["memberships"]] == [a.slug]
    assert admin["memberships"][0]["role"] == "customer_admin"
    # filtering by organization returns only that customer's members
    r = platform_admin.get("/v1/platform/users", params={"organization_id": customers["B"].org_id})
    assert all(any(m["organization_id"] == customers["B"].org_id for m in u["memberships"]) for u in r.json()["items"])


def test_create_deactivate_and_reset_platform_user(platform_admin, client):
    email = f"ops-{uuid.uuid4().hex[:6]}@platform.test"
    r = platform_admin.post("/v1/platform/users", json={"email": email, "full_name": "Ops", "password": PASSWORD})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    ops = Api(client, login(client, email, PASSWORD))
    assert ops.get("/v1/platform/overview").status_code == 200  # new user is a platform admin
    # duplicate e-mail
    assert platform_admin.post("/v1/platform/users", json={"email": email}).status_code == 422
    # reset password revokes sessions and issues a working temporary password
    r = platform_admin.post(f"/v1/platform/users/{uid}/reset-password")
    temp = r.json()["temporary_password"]
    assert ops.get("/v1/auth/me").status_code == 401
    ops = Api(client, login(client, email, temp))
    assert ops.get("/v1/auth/me").status_code == 200
    # deactivation revokes access immediately
    r = platform_admin.patch(f"/v1/platform/users/{uid}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert ops.get("/v1/auth/me").status_code == 401
    assert client.post("/v1/auth/login", json={"email": email, "password": temp}).status_code == 401


def test_admin_cannot_lock_themselves_out(platform_admin):
    me = platform_admin.get("/v1/auth/me").json()["user"]["id"]
    assert platform_admin.patch(f"/v1/platform/users/{me}", json={"is_active": False}).status_code == 422
    assert platform_admin.patch(f"/v1/platform/users/{me}", json={"is_platform_admin": False}).status_code == 422


def test_settings_expose_no_secrets(platform_admin):
    r = platform_admin.get("/v1/platform/settings")
    assert r.status_code == 200, r.text
    body = r.text
    assert "test-secret-key-for-unit-tests-only" not in body
    data = r.json()
    assert data["storage"]["backend"] == "local"
    assert data["media"]["tools"]["ffmpeg"] in (True, False)
    assert any("Development AI adapters" in w for w in data["warnings"])
    assert data["ai"]["keys_configured"] == {"anthropic": False, "openai": False, "visual_embedding_service": False}


def test_integrations_inventory_counts_tokens(platform_admin, customers):
    a = customers["A"]
    a.admin.post("/v1/workspace/api-tokens", json={"name": "inventory test", "role": "viewer"})
    r = platform_admin.get("/v1/platform/integrations")
    assert r.status_code == 200
    row = next(c for c in r.json()["customers"] if c["organization_id"] == a.org_id)
    assert row["active_tokens"] >= 1
    assert "stdio" in r.json()["mcp"]["transports"]


def test_export_registry_and_expiry(platform_admin, customers):
    from app.db.session import system_session
    from app.models import ExportJob
    from app.services.maintenance import expire_exports

    b = customers["B"]
    # the platform admin generates an export for one customer through the workspace API
    admin_in_b = platform_admin.for_org(b.org_id)
    r = admin_in_b.post("/v1/exports", json={"mode": "full", "include_originals": False})
    assert r.status_code == 202, r.text
    eid = r.json()["id"]
    drain()
    reg = platform_admin.get("/v1/platform/exports", params={"organization_id": b.org_id}).json()["items"]
    row = next(e for e in reg if e["id"] == eid)
    assert row["status"] == "completed" and row["organization_slug"] == b.slug and row["download_available"]
    assert all(e["organization_id"] == b.org_id for e in reg)
    # expire it
    with system_session() as s:
        s.execute(update(ExportJob).where(ExportJob.id == uuid.UUID(eid))
                  .values(expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)))
    assert expire_exports() >= 1
    e = admin_in_b.get(f"/v1/exports/{eid}").json()
    assert e["status"] == "expired" and e["download_available"] is False
    assert admin_in_b.get(f"/v1/exports/{eid}/download").status_code == 422


def test_cli_check_passes(capsys):
    from app.cli import main

    assert main(["check"]) == 0
    out = capsys.readouterr().out
    assert "cannot bypass RLS" in out and "fails closed" in out
