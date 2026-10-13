"""Authentication, workspace resolution and role-based access control through the API."""
from __future__ import annotations

from tests.conftest import PASSWORD, Api, login


def test_login_rejects_bad_password(client):
    r = client.post("/v1/auth/login", json={"email": "root@platform.test", "password": "nope-nope-nope"})
    assert r.status_code == 401


def test_unauthenticated_requests_are_rejected(client):
    assert client.get("/v1/workspace", headers={"X-Organization-Id": "x"}).status_code == 401


def test_me_lists_only_own_memberships(customers):
    me = customers["A"].admin.get("/v1/auth/me").json()
    slugs = {m["slug"] for m in me["memberships"]}
    assert slugs == {customers["A"].slug}


def test_customer_cannot_open_other_workspace(customers):
    a, b = customers["A"], customers["B"]
    r = a.admin.for_org(b.org_id).get("/v1/workspace")
    assert r.status_code == 404  # existence is not revealed
    r = a.admin.for_org(b.slug).get("/v1/brands")
    assert r.status_code == 404
    r = a.admin.get(f"/v1/brands/{b.brand_id}")
    assert r.status_code == 404  # B's brand id is invisible inside A's workspace


def test_platform_admin_can_open_any_workspace(platform_admin, customers):
    for c in customers.values():
        r = platform_admin.for_org(c.slug).get("/v1/workspace")
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "platform_super_admin"
        assert [b["id"] for b in r.json()["brands"]] == [c.brand_id]


def test_platform_endpoints_require_platform_admin(customers, platform_admin):
    assert customers["A"].admin.get("/v1/platform/overview").status_code == 403
    assert customers["A"].admin.post("/v1/organizations", json={"name": "x"}).status_code == 403
    r = platform_admin.get("/v1/organizations")
    assert r.status_code == 200
    listed = {o["slug"] for o in r.json()["items"]}
    assert {c.slug for c in customers.values()} <= listed


def test_role_permissions_enforced(customers):
    c = customers["A"]
    viewer, editor, reviewer, cd = (c.users[k] for k in ("viewer", "editor", "reviewer", "creative_director"))
    assert viewer.get("/v1/brands").status_code == 200
    assert viewer.post("/v1/brands", json={"name": "Nope"}).status_code == 403
    assert editor.post("/v1/brands", json={"name": "Nope"}).status_code == 403
    assert reviewer.patch(f"/v1/brands/{c.brand_id}", json={"tagline": "x"}).status_code == 403
    assert editor.post("/v1/workspace/members", json={"email": "x@y.test", "role": "viewer"}).status_code == 403
    assert viewer.get("/v1/workspace/audit-log").status_code == 403
    r = cd.patch(f"/v1/brands/{c.brand_id}", json={"tagline": "Quiet confidence"})
    assert r.status_code == 200 and r.json()["tagline"] == "Quiet confidence"


def test_creative_director_cannot_grant_admin(customers):
    # creative directors lack users.manage entirely
    r = customers["A"].users["creative_director"].post(
        "/v1/workspace/members", json={"email": "cd-made@x.test", "role": "customer_admin"}
    )
    assert r.status_code == 403


def test_last_admin_protection(customers):
    c = customers["C"]
    members = c.admin.get("/v1/workspace/members").json()["items"]
    me = next(m for m in members if m["role"] == "customer_admin")
    r = c.admin.patch(f"/v1/workspace/members/{me['id']}", json={"role": "viewer"})
    assert r.status_code == 422


def test_member_invite_returns_temporary_password_once(customers, client):
    c = customers["B"]
    r = c.admin.post("/v1/workspace/members", json={"email": "new.person@customer-b.test", "role": "editor"})
    assert r.status_code == 201, r.text
    temp = r.json()["temporary_password"]
    assert temp
    token = login(client, "new.person@customer-b.test", temp)
    assert Api(client, token, c.org_id).get("/v1/workspace").json()["role"] == "editor"


def test_api_token_is_bound_to_its_organization(customers, client):
    a, b = customers["A"], customers["B"]
    r = a.admin.post("/v1/workspace/api-tokens", json={"name": "MCP client", "role": "viewer"})
    assert r.status_code == 201, r.text
    tok = r.json()["token"]
    api = Api(client, tok)
    assert api.get("/v1/workspace").json()["organization"]["id"] == a.org_id
    assert api.for_org(b.org_id).get("/v1/workspace").status_code == 403
    assert api.post("/v1/brands", json={"name": "x"}).status_code == 403  # viewer token
    # revoke
    a.admin.post(f"/v1/workspace/api-tokens/{r.json()['id']}/revoke")
    assert api.get("/v1/workspace").status_code == 401


def test_token_cannot_exceed_creator_role(customers):
    cd = customers["A"].users["creative_director"]
    # creative directors cannot manage tokens at all
    assert cd.post("/v1/workspace/api-tokens", json={"name": "x", "role": "viewer"}).status_code == 403


def test_token_scopes_narrow_permissions(customers, client):
    a = customers["A"]
    r = a.admin.post(
        "/v1/workspace/api-tokens", json={"name": "read-only brand", "role": "editor", "scopes": ["brand.read"]}
    )
    tok = Api(client, r.json()["token"])
    assert tok.get("/v1/brands").status_code == 200
    assert tok.get("/v1/workspace/overview").status_code == 403  # org.read not in scopes


def test_cookie_auth_requires_csrf_header(client, customers):
    c = customers["A"]
    r = client.post("/v1/auth/login", json={"email": f"admin@{c.slug}.test", "password": PASSWORD})
    assert r.status_code == 200
    h = {"X-Organization-Id": c.org_id}
    assert client.get("/v1/workspace", headers=h).status_code == 200
    assert client.post("/v1/brands", json={"name": "Via cookie"}, headers=h).status_code == 403
    r = client.post("/v1/brands", json={"name": "Via cookie"}, headers={**h, "X-BDNA-CSRF": "1"})
    assert r.status_code == 201, r.text
    client.cookies.clear()


def test_archived_customer_is_locked_for_customers_but_not_admin(client, platform_admin):
    r = platform_admin.post(
        "/v1/organizations",
        json={"name": "Archivable", "admin_email": "admin@archivable.test", "admin_password": PASSWORD},
    )
    org = r.json()
    user = Api(client, login(client, "admin@archivable.test", PASSWORD), org["organization_id"])
    assert user.get("/v1/workspace").status_code == 200
    assert platform_admin.post(f"/v1/organizations/{org['organization_id']}/archive").status_code == 200
    assert user.get("/v1/workspace").status_code == 403
    assert platform_admin.for_org(org["organization_id"]).get("/v1/workspace").status_code == 200
    assert platform_admin.post(f"/v1/organizations/{org['organization_id']}/reactivate").status_code == 200
    assert user.get("/v1/workspace").status_code == 200


def test_audit_log_records_actions(customers):
    c = customers["A"]
    items = c.admin.get("/v1/workspace/audit-log", params={"limit": 200}).json()["items"]
    actions = {i["action"] for i in items}
    assert "member.added" in actions and "organization.created" in actions
    # Another customer's actions never appear
    assert all(i["details"].get("email", "").find(customers["B"].slug) == -1 for i in items)
